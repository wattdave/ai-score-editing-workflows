#!/usr/bin/env python3
"""Measure what a Dorico selection recipe does, on a scratch project.

Run with a COPY of a project open in Dorico (never a real score). Every
trial selects, runs the command under test, reads the events through Lua (no
MusicXML export), then undoes until the events match the baseline. The
script never saves. See docs/dorico-selection-research-plan.md.

    uv run python scripts/dorico_selection_probe.py bars [--staff N] [--bars 5,20] [--steps 8]
    uv run python scripts/dorico_selection_probe.py plan [--span 3]
    uv run python scripts/dorico_selection_probe.py copy [--ranges 5-8,7-10] [--dest-bar 20]
    uv run python scripts/dorico_selection_probe.py run --anchor 1:5 --extend 2 \\
        --cmd Edit.TransposeSelection --measure changed

`plan` checks that score._extension_plan (what delete-bars uses) removes exactly
the bars it was asked for. `bars` selects a note with k extend steps, runs Edit.DeleteBars and compares
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
        self.ties: set[tuple[int, int]] = set()
        self.tie_offset = 0
        self.slurs: list[tuple[int, int, int, int, int]] = []

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

    async def delete_bars_trial(self, commands: list[str], first: int | None = None) -> dict[str, Any]:
        """Run commands then Edit.DeleteBars; the bars removed. `first` is the bar the selection
        starts in: with it, empty bars (which hold no events) are counted by how far the events
        after them moved up."""
        out: dict[str, Any] = {}
        try:
            for command in commands:
                await self.client.command(command)
            try:
                await self.client.command("Edit.DeleteBars")
            except DoricoError as exc:
                out["error"] = str(exc).split(":")[-1].strip()
            else:
                after = {e["id"]: e for e in await self.read() if "id" in e}
                now = set(after)
                moved = [self.bar_of(self.base_by_id[i]["position"]) - self.bar_of(e["position"])
                         for i, e in after.items() if i in self.base_by_id and e["position"] != self.base_by_id[i]["position"]]
                # Lines and slurs crossing the edit get new ids, so only notes and rests count.
                gone = [e["position"] for i, e in self.base_by_id.items() if i not in now and e["type"] in ITEM_TYPES]
                out["bars"] = (self.bar_of(min(gone)), self.bar_of(max(gone))) if gone else None
                if first is not None and moved and min(moved) > 0:
                    shift = min(moved)  # every later event moves up by the bars removed
                    out["bars"] = (first, max(first + shift - 1, out["bars"][1] if out["bars"] else 0))
        except DoricoError as exc:
            out["error"] = f"ERR {str(exc)[:80]}"
        out["undo_steps"] = await self.restore()
        return out


def scope_staves(lab: Lab, staff: int, scope: str) -> set[int]:
    """The staves whose items a step pulls in: the anchor's staff, its instrument's, or all."""
    if scope == "all":
        return {s["staff"] for s in lab.staves}
    if scope == "instrument":
        name = next((s.get("name") for s in lab.staves if s["staff"] == staff), None)
        return {s["staff"] for s in lab.staves if s.get("name") == name}
    return {staff}


async def barline_ties(client: DoricoClient, flow: int) -> set[tuple[int, int]]:
    """(measure, MIDI pitch) of every note whose tie starts in that bar and goes on
    into the next. Neither Lua nor dump() report ties, so this exports MusicXML once
    (slow, visible); it cannot tell voices of one staff apart."""
    import xml.etree.ElementTree as ET

    from ai_score_editing.dorico.export import export_musicxml

    root = ET.parse(await export_musicxml(client, flow)).getroot()
    step = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
    out: set[tuple[int, int]] = set()
    for part in root.iter("part"):
        for index, measure in enumerate(part.iter("measure"), 1):
            for note in measure.iter("note"):
                pitch = note.find("pitch")
                if pitch is None or not any(t.get("type") == "start" for t in note.findall("tie")):
                    continue
                midi = 12 * (int(pitch.findtext("octave")) + 1) + step[pitch.findtext("step")] + int(float(pitch.findtext("alter") or 0))
                out.add((index, midi))
    return out


def _plain_name(name: str) -> str:
    """Dorico writes a flat as {@flat@} in staff names and 'Flat' in the export's part names."""
    return " ".join(name.replace("{@flat@}", " Flat").replace("{@sharp@}", " Sharp").split()).lower()


async def slur_spans(client: DoricoClient, flow: int, lab_staves: list[dict[str, Any]] | None = None) -> list[tuple[int, int, int, int, int]]:
    """(staff, start measure, start offset, end measure, end offset) of every slur and hairpin, from a
    MusicXML export (slurs are not readable from Lua). The export lists parts in score order and
    Dorico's staves are in creation order, so with `lab_staves` each part is matched to the staff
    of the same name (a second staff of the part follows the first); without them staves are
    numbered through the parts in order. Offsets are in 1/256 quarter."""
    import xml.etree.ElementTree as ET

    from ai_score_editing.dorico.export import export_musicxml

    root = ET.parse(await export_musicxml(client, flow)).getroot()
    out: list[tuple[int, int, int, int, int]] = []
    names = {sp.get("id"): sp.findtext("part-name") for sp in root.iter("score-part")}
    by_name = {}
    for st in lab_staves or []:
        if st.get("name"):
            by_name.setdefault(_plain_name(st["name"]), st["staff"])
    first_staff = 0
    for part in root.iter("part"):
        if lab_staves:
            found = by_name.get(_plain_name(names.get(part.get("id")) or ""))
            if found is None:
                first_staff = -10_000  # no staff of that name: its slurs go nowhere
            else:
                first_staff = found - 1
        divisions = 1
        staves = 1
        open_slurs: dict[tuple[int, str], tuple[int, int]] = {}
        for index, measure in enumerate(part.iter("measure"), 1):
            cursor = 0
            for child in measure:
                if child.tag == "attributes":
                    divisions = int(child.findtext("divisions") or divisions)
                    staves = int(child.findtext("staves") or staves)
                elif child.tag in ("backup", "forward"):
                    cursor += (-1 if child.tag == "backup" else 1) * int(child.findtext("duration") or 0)
                elif child.tag == "direction":
                    for wedge in child.iter("wedge"):
                        staff = first_staff + int(child.findtext("staff") or 1)
                        key = (staff, "wedge")
                        if wedge.get("type") in ("crescendo", "diminuendo"):
                            open_slurs[key] = (index, int(cursor * 256 / divisions))
                        elif wedge.get("type") == "stop" and key in open_slurs:
                            m1, o1 = open_slurs.pop(key)
                            out.append((staff, m1, o1, index, int(cursor * 256 / divisions)))
                elif child.tag == "note":
                    chord = child.find("chord") is not None
                    start = cursor
                    dur = int(child.findtext("duration") or 0)
                    staff = first_staff + int(child.findtext("staff") or 1)
                    scale = 256 / divisions
                    for slur in child.iter("slur"):
                        key = (staff, slur.get("number", "1"))
                        if slur.get("type") == "start":
                            open_slurs[key] = (index, int(start * scale))
                        elif slur.get("type") == "stop" and key in open_slurs:
                            m1, o1 = open_slurs.pop(key)
                            out.append((staff, m1, o1, index, int(start * scale)))  # a slur ends where its last note starts
                    if not chord and child.find("grace") is None:
                        cursor += dur
        if not lab_staves:
            first_staff += staves
    return out


def tie_chains(lab: Lab, items: list[dict[str, Any]]) -> list[tuple[int, int]]:
    """Item spans where a note tied over a barline reaches to the end of the note it
    is tied to. Ties come from lab.ties (the events do not carry them)."""
    notes = {(e["stream"], e["pitch"], e["flowPosition"]): e for e in items if e["type"] == "NoteEvent"}

    def end_of(e: dict[str, Any]) -> int:
        end = e["flowPosition"] + (e.get("duration") or 0)
        tied = e["type"] == "NoteEvent" and (e["bar"] + lab.tie_offset, e["pitch"]) in lab.ties and lab.bars.locate(end)[1] == 0
        nxt = notes.get((e["stream"], e["pitch"], end)) if tied else None
        return end_of(nxt) if nxt is not None else end

    return [(e["flowPosition"], end_of(e)) for e in items]


def predict_bars(lab: Lab, staff: int, anchor: dict[str, Any], steps: int, scope: str = "staff", ties: bool = False,
                 slurs: bool = False) -> tuple[int, int]:
    """Bars Edit.DeleteBars touches after `steps` extend steps from `anchor`.

    The rule: a step moves the end to the next barline after it, then pulls
    in every item of the staff that starts before that barline, whole.
    """
    staves = scope_staves(lab, staff, scope)
    # Lyrics are items of the stream too: a melisma runs past the barline.
    items = [e for e in lab.located if e["staff"] in staves and e["type"] in ITEM_TYPES + ("LyricEvent",) and e.get("voice")]
    spans = [(e["flowPosition"], e["flowPosition"] + (e.get("duration") or 0)) for e in items]
    if ties:
        spans = tie_chains(lab, items)
    item_spans = list(spans)
    slur_spans_: list[tuple[int, int, int]] = []
    if slurs:  # a slur is an item too: it is pulled in when it starts inside the selection
        for st, m1, o1, m2, o2 in lab.slurs:
            if st in staves:
                a = lab.bars.position(m1 + lab.tie_offset, 0) + o1
                b = lab.bars.position(m2 + lab.tie_offset, 0) + o2
                # The export splits a note tied over a barline; the slur ends at the start of the whole note.
                held = [(s, e) for s, e in item_spans if s <= b < e]
                last = max(held) if held else (b, b)
                slur_spans_.append((a, last[0], last[1]))
    end = anchor["flowPosition"] + (anchor.get("duration") or 0)
    reach = end - 1  # the last position touched; a slur touches the bar of its last note
    for _ in range(steps):
        target = lab.bars.position(lab.bar_of(end) + 1, 0)
        pulled = [(s, e) for s, e in spans if anchor["flowPosition"] <= s < target]
        caught = [(r, e) for s, r, e in slur_spans_ if anchor["flowPosition"] <= s < target]
        notes_end = max([target] + [e for s, e in pulled])
        end = max([notes_end] + [e for r, e in caught])
        reach = max([reach, notes_end - 1] + [r for r, e in caught])
    last_bar = max(e["bar"] for e in lab.located)
    return anchor["bar"], min(lab.bar_of(reach), last_bar)  # a step past the last bar stops there


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
                    predicted = predict_bars(lab, staff, anchor, k, args.scope, args.ties, args.slurs)
                except Exception as exc:  # past the end of the flow
                    print(f"staff {staff} bar {bar} k={k}: no prediction ({exc})")
                    break
                result = await lab.delete_bars_trial([lab.select(anchor)] + [EXTEND] * k, anchor["bar"])
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


async def run_plan(lab: Lab, args: argparse.Namespace) -> int:
    """score._extension_plan against Edit.DeleteBars: does each planned selection remove
    exactly the bars asked for? Returns the misses."""
    last_bar = max(e["bar"] for e in lab.located)
    misses = total = 0
    for first in range(1, last_bar + 1):
        for last in range(first, min(first + args.span, last_bar + 1)):
            plan = score._extension_plan(lab.located, lab.bars, first, last)
            if plan is None:
                print(f"none bars {first}-{last}: no exact selection planned")
                continue
            anchor = next(e for e in lab.located if e["id"] == plan["select"]["id"])
            result = await lab.delete_bars_trial([lab.select(anchor)] + [EXTEND] * plan["extend"], first)
            if result["undo_steps"] is None:
                print("!! could not restore the baseline; stopping")
                return misses + 1
            total += 1
            ok = result.get("bars") == (first, last)
            misses += not ok
            print(f"{'ok  ' if ok else 'MISS'} bars {first}-{last}: staff {plan['staff']} extend {plan['extend']}, "
                  f"measured {result.get('bars')}", flush=True)
    print(f"plan: {total - misses}/{total} exact")
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
    bars.add_argument("--slurs", action="store_true", help="model slurs starting inside the selection as items (needs a MusicXML export)")
    bars.add_argument("--ties", action="store_true", help="model same-pitch notes meeting on a barline as tied")
    bars.add_argument("--tie-offset", type=int, default=0, help="MusicXML measure index minus bar number")
    bars.add_argument("--scope", choices=("staff", "instrument", "all"), default="staff",
                      help="whose items a step pulls in, for the model")
    plan = sub.add_parser("plan")
    plan.add_argument("--span", type=int, default=3, help="longest range of bars to plan")
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
        if getattr(args, "ties", False):
            lab.tie_offset = args.tie_offset
            lab.ties = await barline_ties(client, args.flow)
            print(f"{len(lab.ties)} (measure, pitch) ties start in a bar and go on")
        if getattr(args, "slurs", False):
            lab.tie_offset = args.tie_offset
            lab.slurs = await slur_spans(client, args.flow, lab.staves)
            print(f"{len(lab.slurs)} slurs")
        if args.mode == "bars":
            return int(await run_bars(lab, args) > 0)
        if args.mode == "plan":
            return int(await run_plan(lab, args) > 0)
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
