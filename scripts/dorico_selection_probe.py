#!/usr/bin/env python3
"""Measure what a Dorico selection recipe does, on a scratch project.

Run with a COPY of a project open in Dorico (never a real score). Every
trial selects, runs the command under test, reads the events through Lua (no
MusicXML export), then undoes until the events match the baseline. The
script never saves. See docs/dorico-selection-research-plan.md.

    uv run python scripts/dorico_selection_probe.py bars [--staff N] [--bars 5,20] [--steps 8]
    uv run python scripts/dorico_selection_probe.py copy [--ranges 5-8,7-10] [--dest-bar 20]
    uv run python scripts/dorico_selection_probe.py run --anchor 1:5 --extend 2 \\
        --cmd Edit.TransposeSelection --measure changed

`bars` selects a note with k extend steps, runs Edit.DeleteBars and compares
the bars removed with the model's prediction (docs/dorico.md, "Selecting
bars"). `copy` copies planned selections and compares the notes pasted with
the notes that start in the bars. `run` is the general recipe for new
commands: select the anchor (staff:bar), extend, run --cmd, then report
removed or added events, changed properties, or the undo steps needed.
Without a subcommand it runs the PR #88 checks and exits 1 on any mismatch,
so a Dorico update that changes selection behaviour is noticed.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

from ai_score_editing.dorico import score, service
from ai_score_editing.dorico.bridge import BarMap, DoricoBridge
from ai_score_editing.dorico.client import DoricoClient, DoricoError

EXTEND = "EventEdit.NavigateRightExtendBar"
ITEM_TYPES = ("NoteEvent", "RestEvent", "BarRestEvent")
#: Event keys compared for "changed properties" (everything but the id).
PROPERTY_KEYS = ("position", "duration", "pitch", "type", "stream")
MAX_RESTORE_STEPS = 40


def signature(events: list[dict[str, Any]]) -> list[tuple[Any, ...]]:
    return sorted((e["id"], e["position"]) for e in events if "id" in e)


def parse_ranges(text: str) -> list[tuple[int, int]]:
    out = []
    for part in text.split(","):
        first, _, last = part.partition("-")
        out.append((int(first), int(last or first)))
    return out


class Lab:
    """A project snapshot plus select / run / measure / restore."""

    def __init__(self, client: DoricoClient) -> None:
        self.client = client
        self.bridge = DoricoBridge(client)

    async def setup(self, flow: int = 1) -> None:
        self.flow = flow
        snap = await service.snapshot(self.bridge, flow)
        self.located: list[dict[str, Any]] = snap.located
        self.bars: BarMap = snap.bars
        self.staves = snap.staves
        self.blocks = (await self.bridge.overview(flow))["layout"]["blocks"]
        self.flow_id = (await self.client.flows())[flow - 1]["flowID"]
        self.base, _ = await self.bridge.read_partial(flow)
        self.base_by_id = {e["id"]: e for e in self.base if "id" in e}
        self.base_sig = signature(self.base)

    def item(self, staff: int, bar: int, *, note: bool = True) -> dict[str, Any] | None:
        """The first item starting in the bar on the staff (a note first)."""
        pool = [e for e in self.located if e["staff"] == staff and e["bar"] == bar and e["type"] in ITEM_TYPES and e.get("voice")]
        pool.sort(key=lambda e: (e["type"] != "NoteEvent" if note else 0, e["flowPosition"], e["voice"], e["id"]))
        return pool[0] if pool else None

    def select(self, event: dict[str, Any]) -> str:
        return (f"EventEdit.Select?FlowID={self.flow_id}&EventID={event['id']}"
                f"&EventBlockID={self.blocks[str(event['stream'])]}")

    async def read(self) -> list[dict[str, Any]]:
        return (await self.bridge.read_partial(self.flow))[0]

    async def restore(self) -> int | None:
        """Undo until the events match the baseline; the steps taken, or None."""
        for steps in range(MAX_RESTORE_STEPS):
            if signature(await self.read()) == self.base_sig:
                return steps
            await self.client.command("Edit.Undo")
        return None

    def bar_of(self, position: int) -> int:
        return self.bars.locate(position)[0]

    async def delete_bars_trial(self, commands: list[str]) -> dict[str, Any]:
        """Run commands then Edit.DeleteBars; the bars removed."""
        out: dict[str, Any] = {}
        try:
            for command in commands:
                await self.client.command(command)
            try:
                await self.client.command("Edit.DeleteBars")
            except DoricoError as exc:
                out["error"] = str(exc).split(":")[-1].strip()
            else:
                now = {e["id"] for e in await self.read() if "id" in e}
                gone = [self.base_by_id[i]["position"] for i in self.base_by_id if i not in now]
                out["bars"] = (self.bar_of(min(gone)), self.bar_of(max(gone))) if gone else None
        except DoricoError as exc:
            out["error"] = f"ERR {str(exc)[:80]}"
        out["undo_steps"] = await self.restore()
        return out


def predict_bars(lab: Lab, staff: int, anchor: dict[str, Any], steps: int) -> tuple[int, int]:
    """Bars Edit.DeleteBars touches after `steps` extend steps from `anchor`.

    The rule: a step moves the end to the next barline after it, then pulls
    in every item of the staff that starts before that barline, whole.
    """
    items = [e for e in lab.located if e["staff"] == staff and e["type"] in ITEM_TYPES and e.get("voice")]
    spans = [(e["flowPosition"], e["flowPosition"] + (e.get("duration") or 0)) for e in items]
    end = anchor["flowPosition"] + (anchor.get("duration") or 0)
    for _ in range(steps):
        target = lab.bars.position(lab.bar_of(end) + 1, 0)
        end = max([target] + [e for s, e in spans if s < target])
    return anchor["bar"], lab.bar_of(end - 1)


async def run_bars(lab: Lab, args: argparse.Namespace) -> int:
    """Model versus measured Edit.DeleteBars extents. Returns the misses."""
    wanted_staves = [args.staff] if args.staff else [s["staff"] for s in lab.staves]
    total = misses = 0
    for staff in wanted_staves:
        for bar in args.bars:
            anchor = lab.item(staff, bar)
            if anchor is None or anchor["type"] != "NoteEvent":
                continue
            for k in range(1, args.steps + 1):
                try:
                    predicted = predict_bars(lab, staff, anchor, k)
                except Exception as exc:  # past the end of the flow
                    print(f"staff {staff} bar {bar} k={k}: no prediction ({exc})")
                    break
                result = await lab.delete_bars_trial([lab.select(anchor)] + [EXTEND] * k)
                if result["undo_steps"] is None:
                    print("!! could not restore the baseline; stopping")
                    return misses + 1
                measured = result.get("bars")
                ok = measured == predicted
                total += 1
                misses += not ok
                print(f"{'ok  ' if ok else 'MISS'} staff {staff} bar {bar} k={k}: "
                      f"predicted {predicted[0]}-{predicted[1]}, measured {measured}"
                      f"{' ' + result['error'] if 'error' in result else ''}, undo {result['undo_steps']}", flush=True)
    print(f"bars: {total - misses}/{total} predicted")
    return misses


async def paste_trial(lab: Lab, recipe: list[str], anchor: dict[str, Any], dest: dict[str, Any],
                      dest_staff: int, want: list[tuple[int, int]], base_start: int) -> tuple[int, int] | None:
    """Select, copy, paste at dest in overwrite mode; (missing, extra) notes, or None if not restored."""
    client = lab.client
    mode = (await client.status()).get("noteInputMode")
    await client.command(lab.select(anchor))
    for command in recipe:
        await client.command(command)
    await client.command("Edit.Copy")
    await client.command(lab.select(dest))
    if mode != "kOverwrite":
        await client.command("NoteInput.Mode?NoteInputMode=kOverwrite")
    try:
        await client.command("Edit.Paste")
    finally:
        if mode and mode != "kOverwrite":
            await client.command(f"NoteInput.Mode?NoteInputMode={mode}")
    streams = {e["stream"] for e in lab.located if e["staff"] == dest_staff}
    new = [e for e in await lab.read() if e["type"] == "NoteEvent" and e["id"] not in lab.base_by_id and e["stream"] in streams]
    got = sorted((e["position"] - dest["flowPosition"], e["pitch"]) for e in new)
    missing = sum(1 for w in want if w not in got)
    extra = sum(1 for g in got if g not in want)
    return (missing, extra) if await lab.restore() is not None else None


async def run_copy(lab: Lab, args: argparse.Namespace) -> int:
    """Copy-passage recipes against the notes that start in the bars. Returns the misses."""
    staff = args.staff or 1
    dest_staff = args.dest_staff or next((s["staff"] for s in lab.staves if s["staff"] != staff), staff)
    dest = next((e for e in lab.located if e["staff"] == dest_staff and e["bar"] == args.dest_bar
                 and e["type"] == "NoteEvent" and e["position"] == 0), None)
    if dest is None:
        print(f"no note at the start of bar {args.dest_bar} on staff {dest_staff}")
        return 1
    misses = 0
    for first, last in args.ranges:
        start, end = lab.bars.position(first, 0), lab.bars.position(last, 0) + lab.bars.bar_length(last)
        items = [e for e in lab.located if e["staff"] == staff and e["type"] in ITEM_TYPES and e.get("voice")
                 and start <= e["flowPosition"] < end]
        notes = [e for e in items if e["type"] == "NoteEvent"]
        if not notes:
            print(f"bars {first}-{last}: no notes on staff {staff}")
            continue
        origin = min(e["flowPosition"] for e in notes)  # paste lines the first note up with the target
        want = sorted((e["flowPosition"] - origin, e["pitch"]) for e in notes)
        plan = score._extension_plan(lab.located, lab.bars, first, last, staff=staff, cover=True)
        recipes = [(f"planned (extend x{plan['extend']})", [EXTEND] * plan["extend"], plan["select"])] if plan else []
        if args.old:
            anchor = min((e for e in notes if e["bar"] == first), key=lambda e: (e["flowPosition"], e["voice"], e["id"]), default=None)
            if anchor:
                recipes.append((f"old (SelectMore + extend x{last - first})", ["Edit.SelectMore"] + [EXTEND] * (last - first), anchor))
        if not recipes:
            print(f"bars {first}-{last}: no plan")
            misses += 1
        for label, recipe, anchor in recipes:
            anchor_event = next(e for e in lab.located if e["id"] == anchor["id"])
            outcome = await paste_trial(lab, recipe, anchor_event, dest, dest_staff, want, origin)
            if outcome is None:
                print("!! could not restore the baseline; stopping")
                return misses + 1
            missing, extra = outcome
            bad = (missing or extra) and label.startswith("planned")
            misses += bool(bad)
            print(f"{'MISS' if bad else 'ok  ' if label.startswith('planned') else 'info'} bars {first}-{last} {label}: want {len(want)} missing {missing} extra {extra}", flush=True)
    print(f"copy: {misses} planned recipe(s) off")
    return misses


async def run_recipe(lab: Lab, args: argparse.Namespace) -> int:
    """Select (staff:bar), extend, run commands, report the effect, restore."""
    staff, _, bar = args.anchor.partition(":")
    anchor = lab.item(int(staff), int(bar))
    if anchor is None:
        print(f"no item in bar {bar} of staff {staff}")
        return 1
    client = lab.client
    result: dict[str, Any] = {}
    try:
        await client.command(lab.select(anchor))
        for _ in range(args.extend):
            await client.command(EXTEND)
        for command in args.cmd:
            await client.command(command)
        now = await lab.read()
        now_by_id = {e["id"]: e for e in now if "id" in e}
        removed = [e for i, e in lab.base_by_id.items() if i not in now_by_id]
        added = [e for i, e in now_by_id.items() if i not in lab.base_by_id]
        changed = [i for i, e in now_by_id.items() if i in lab.base_by_id
                   and any(e.get(k) != lab.base_by_id[i].get(k) for k in PROPERTY_KEYS)]
        if args.measure == "removed":
            result["removed"] = len(removed)
            result["bars"] = sorted({lab.bar_of(e["position"]) for e in removed})
        elif args.measure == "added":
            result["added"] = len(added)
            result["bars"] = sorted({lab.bar_of(e["position"]) for e in added})
        else:
            result["changed"] = len(changed)
            result["bars"] = sorted({lab.bar_of(now_by_id[i]["position"]) for i in changed})
    except DoricoError as exc:
        result["error"] = str(exc)[:120]
    result["undo_steps"] = await lab.restore()
    print(json.dumps(result))
    return 0 if result["undo_steps"] is not None else 1


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--flow", type=int, default=1)
    sub = parser.add_subparsers(dest="mode")
    bars = sub.add_parser("bars")
    bars.add_argument("--staff", type=int)
    bars.add_argument("--bars", type=lambda t: [int(x) for x in t.split(",")], default=[5, 20])
    bars.add_argument("--steps", type=int, default=8)
    copy = sub.add_parser("copy")
    copy.add_argument("--staff", type=int)
    copy.add_argument("--dest-staff", type=int)
    copy.add_argument("--dest-bar", type=int, default=20)
    copy.add_argument("--ranges", type=parse_ranges, default=parse_ranges("5-8,7-10,8-10,6-9,5-12"))
    copy.add_argument("--old", action="store_true", help="also try the old Edit.SelectMore recipe")
    run = sub.add_parser("run")
    run.add_argument("--anchor", required=True, help="staff:bar of the item to select")
    run.add_argument("--extend", type=int, default=0)
    run.add_argument("--cmd", action="append", default=[], help="command to run (repeatable)")
    run.add_argument("--measure", choices=("removed", "added", "changed"), default="changed")
    args = parser.parse_args()

    async with DoricoClient() as client:
        lab = Lab(client)
        await lab.setup(args.flow)
        if args.mode == "bars":
            return int(await run_bars(lab, args) > 0)
        if args.mode == "copy":
            return int(await run_copy(lab, args) > 0)
        if args.mode == "run":
            return await run_recipe(lab, args)
        # Default: the PR #88 checks.
        defaults = parser.parse_args(["bars"])
        misses = await run_bars(lab, defaults)
        copy_defaults = parser.parse_args(["copy"])
        misses += await run_copy(lab, copy_defaults)
        return int(misses > 0)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
