#!/usr/bin/env python3
"""Copy every lyric verse from one staff onto other staves of the open Sibelius score.

split_satb.py copies only verse 1 and only where the note counts match. This copies
all verses, onto the target note that starts at the same moment as each source
syllable (or the note that is sounding there), so the lower voices of a split
hymn sing the same words. Run it with the score open:

  uv run python .claude/skills/satb-part-splitting/scripts/copy_lyrics_to_staves.py \
      --expect-file "/path/score.sib" --target-staff 3 --target-staff 4 --hide

Existing lyrics on the target staves in the bar range are replaced (a backup is
made first; --keep-existing leaves them). A syllable with no note to sit on, for
example a passing note the target does not have, is reported and skipped.
--dry-run prints the plan and changes nothing.
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from ai_score_editing.sibelius.cli import BRIDGE_PLUGIN, _apply_batch, _backup, _bridge
from ai_score_editing.sibelius.client import SibeliusClient

STYLE = "text.staff.space.hypen.lyrics.verse%d"
CHUNK = 150  # larger batches have dropped the Sibelius connection


def verse_of(style_id: str) -> int | None:
    match = re.search(r"lyrics\.verse(\d)$", style_id)
    return int(match.group(1)) if match else None


def verse_dy(verse: int) -> int:
    return -192 - 80 * (verse - 1)


def objects(bars: list[dict[str, Any]]):
    for bar in bars:
        for obj in bar["objects"]:
            yield bar["barNumber"], obj


async def apply_ops(client: SibeliusClient, ops: list[dict[str, Any]]) -> None:
    for start in range(0, len(ops), CHUNK):
        result = await _apply_batch(client, ops[start:start + CHUNK], False)
        if "error" in result:
            raise SystemExit(f"error: {result['error']} (applied {result.get('applied', 0)} op(s); run 'invoke undo')")


async def read_source(client, staff: int, first: int, last: int):
    """(bar, position) -> {verse: (text, syllableType)}."""
    source: dict[tuple[int, int], dict[int, tuple[str, str]]] = defaultdict(dict)
    skipped = 0
    for bar, obj in objects(await _bridge(client, "ReadBars", [staff, first, last])):
        if obj["type"] != "LyricItem":
            continue
        verse = verse_of(obj["styleId"])
        if verse is None:
            skipped += 1
            continue
        source[(bar, obj["position"])][verse] = (obj["text"], obj["syllableType"])
    if skipped:
        print(f"warning: skipped {skipped} source lyric(s) outside verses 1-5", file=sys.stderr)
    return source


async def plan_staff(client, staff: int, source, first: int, last: int, keep_existing: bool, strip_numbers: bool):
    notes: dict[int, list[tuple[int, int]]] = defaultdict(list)
    old: list[tuple[int, int]] = []
    for bar, obj in objects(await _bridge(client, "ReadBars", [staff, first, last])):
        if obj["type"] == "NoteRest" and obj.get("notes"):
            notes[bar].append((obj["position"], obj["duration"]))
        elif obj["type"] == "LyricItem" and not keep_existing:
            old.append((bar, obj["index"]))
    adds: list[dict[str, Any]] = []
    unplaced: list[tuple[int, int, dict[int, str]]] = []
    used: set[tuple[int, int]] = set()
    for (bar, position), verses in sorted(source.items()):
        candidates = sorted(notes.get(bar, []))
        target = next((p for p, _ in candidates if p == position), None)
        if target is None:  # a note held through the syllable change
            holding = [p for p, d in candidates if p <= position < p + d]
            target = holding[-1] if holding else None
        if target is None or (bar, target) in used:
            unplaced.append((bar, position, {v: t for v, (t, _) in verses.items()}))
            continue
        used.add((bar, target))
        duration = next(d for p, d in candidates if p == target)
        for verse in sorted(verses):  # creation order is later used to give each its verse line
            text, syllable = verses[verse]
            op: dict[str, Any] = {
                "op": "add-lyric", "staff": staff, "bar": bar, "position": target, "duration": duration,
                "text": re.sub(r"^\d+\.\s*", "", text) if strip_numbers else text,
            }
            if syllable == "middle":
                op["syllableType"] = "middle"
            adds.append({"op": op, "verse": verse})
    return old, adds, unplaced


async def restyle(client, staff: int, adds: list[dict[str, Any]]) -> int:
    """New lyrics all land on verse 1; the last-created item at a position takes the highest verse."""
    wanted: dict[tuple[int, int], list[int]] = defaultdict(list)
    for add in adds:
        wanted[(add["op"]["bar"], add["op"]["position"])].append(add["verse"])
    moved = 0
    for (bar, position), verses in sorted(wanted.items()):
        for verse in sorted(verses, reverse=True):
            if verse == 1:
                continue
            bars = await _bridge(client, "ReadBars", [staff, bar, bar])
            on_line_one = [o for _, o in objects(bars) if o["type"] == "LyricItem"
                           and o["position"] == position and verse_of(o["styleId"]) == 1]
            if not on_line_one:
                raise SystemExit(f"error: no lyric left to restyle at staff {staff} bar {bar} position {position}")
            top = max(on_line_one, key=lambda o: o["index"])
            await _bridge(client, "SetLyricStyle", [staff, bar, top["index"], STYLE % verse])
            moved += 1
    return moved


async def set_offsets(client, staff: int, first: int, last: int, hide: bool) -> int:
    ops = []
    for bar, obj in objects(await _bridge(client, "ReadBars", [staff, first, last])):
        if obj["type"] != "LyricItem":
            continue
        verse = verse_of(obj["styleId"]) or 1
        base = {"staff": staff, "bar": bar, "index": obj["index"], "type": "LyricItem"}
        # hidden copies keep a compact offset so they cannot widen the staff spacing
        dy = -192 if hide else verse_dy(verse)
        if obj["dy"] != dy:
            ops.append({"op": "set", "prop": "Dy", "value": dy, **base})
        if hide and not obj["hidden"]:
            ops.append({"op": "set", "prop": "Hidden", "value": True, **base})
    await apply_ops(client, ops)
    return len(ops)


async def words(client, staff: int, first: int, last: int) -> dict[tuple[int, int], str]:
    """(verse, bar) -> the bar's syllables run together, ignoring hyphens and verse numbers."""
    syllables: dict[tuple[int, int], list[tuple[int, int, str]]] = defaultdict(list)
    for bar, obj in objects(await _bridge(client, "ReadBars", [staff, first, last])):
        if obj["type"] == "LyricItem" and verse_of(obj["styleId"]):
            text = re.sub(r"^\d+\.\s*", "", obj["text"])
            syllables[(verse_of(obj["styleId"]), bar)].append((obj["position"], obj["index"], text))
    return {key: "".join(t for _, _, t in sorted(items)) for key, items in syllables.items()}


async def main_async(args: argparse.Namespace) -> int:
    async with SibeliusClient(plugins=[BRIDGE_PLUGIN]) as client:
        info = await _bridge(client, "GetScoreInfo")
        actual = Path(info.get("fileName") or "").expanduser().resolve()
        if args.expect_file and actual != Path(args.expect_file).expanduser().resolve():
            raise SystemExit(f"error: active score is {actual}, expected {args.expect_file}")
        if not args.dry_run and not args.expect_file:
            raise SystemExit("error: --expect-file is required unless --dry-run")
        first, last = args.from_bar, args.to_bar or info["barCount"]
        source = await read_source(client, args.source_staff, first, last)
        if not source:
            raise SystemExit(f"error: staff {args.source_staff} has no lyrics in bars {first}-{last}")

        plans = {}
        for staff in args.target_staff:
            old, adds, unplaced = await plan_staff(
                client, staff, source, first, last, args.keep_existing, not args.keep_numbers)
            plans[staff] = (old, adds, unplaced)
            print(f"staff {staff}: replace {len(old)}, add {len(adds)}, unplaced {len(unplaced)}")
            for bar, position, texts in unplaced:
                print(f"   no note for bar {bar} position {position}: {texts}")
        if args.dry_run:
            return 0

        backup = await _backup(client, "before copy lyrics")
        print("backup:", backup.get("copy"))
        for staff, (old, adds, _) in plans.items():
            # addresses only stay valid inside one batch, so delete highest index first within each bar
            await apply_ops(client, [{"op": "delete", "staff": staff, "bar": bar, "index": index, "type": "LyricItem"}
                                     for bar, index in sorted(old, reverse=True)])
            await apply_ops(client, [a["op"] for a in adds])
            moved = await restyle(client, staff, adds)
            changed = await set_offsets(client, staff, first, last, args.hide)
            print(f"staff {staff}: restyled {moved}, adjusted {changed} offset/hidden settings")

        reference = await words(client, args.source_staff, first, last)
        status = 0
        for staff in args.target_staff:
            got = await words(client, staff, first, last)
            diff = [(k, reference[k], got.get(k)) for k in sorted(reference) if reference[k] != got.get(k)]
            print(f"staff {staff}: {len(reference) - len(diff)} of {len(reference)} verse-bars match the source")
            for key, want, have in diff:
                print(f"   verse {key[0]} bar {key[1]}: source {want!r}, copy {have!r}")
        if args.save:
            await _bridge(client, "Save")
            print("saved")
        return status


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--source-staff", type=int, default=1)
    ap.add_argument("--target-staff", type=int, action="append", required=True)
    ap.add_argument("--from-bar", type=int, default=1)
    ap.add_argument("--to-bar", type=int, help="default: last bar")
    ap.add_argument("--keep-existing", action="store_true", help="do not delete lyrics already on the target staves")
    ap.add_argument("--keep-numbers", action="store_true", help='keep verse numbers such as "1." in the text')
    ap.add_argument("--hide", action="store_true", help="hide the copies (they still drive playback)")
    ap.add_argument("--expect-file", help="refuse to run unless this is the active score")
    ap.add_argument("--dry-run", action="store_true", help="print the plan, change nothing")
    ap.add_argument("--save", action="store_true")
    return asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
