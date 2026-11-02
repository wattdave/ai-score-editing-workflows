"""Live check of the MuseScore back end against the score open in MuseScore.

Runs a fixed scenario through the same service calls the MCP tools use and
prints PASS/FAIL per step: reads, a dry run of a batch of every kind of op
(nothing may change), the same batch for real (one undo step, undone
exactly), lyrics read/edit/undo, every export format, metadata, adding an
instrument and staff playback. A marker text added first must survive every
undo, and is removed at the end, so the score ends as it started.

It edits the score, so it only runs on a score whose name contains
"Scratch" unless --force is given. Needs at least 8 bars and 2 staves; it
works in the last four bars of staff 2 (which should be empty).

    uv run python scripts/dev/musescore_live_check.py [--port 8766] [--force]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from ai_score_editing.musescore import install, service
from ai_score_editing.musescore.bridge import MuseScoreBridge
from ai_score_editing.musescore.client import MuseScoreClient

MARKER = "live-check marker"
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail else ''}", flush=True)
    return ok


async def state(bridge: MuseScoreBridge) -> str:
    """Everything the read tools report, as one comparable string."""
    objects = await service.query(bridge, limit=100000)
    structure = await service.structure(bridge)
    staves = await bridge.call("GetStaves")
    return json.dumps([objects, structure, staves], sort_keys=True)


def every_op_batch(staff: int, first: int) -> list[dict[str, Any]]:
    """Adding and structural ops in four empty bars (first..first+3) of one staff."""
    b1, b2, b3, b4 = first, first + 1, first + 2, first + 3
    return [
        {"op": "add-note", "staff": staff, "bar": b1, "position": 0, "duration": 256, "pitches": [72, 76]},
        {"op": "add-note", "staff": staff, "bar": b1, "position": 256, "duration": 256, "pitches": [74],
         "tied": True},
        {"op": "add-note", "staff": staff, "bar": b1, "position": 512, "duration": 256, "pitches": [74]},
        {"op": "add-rest", "staff": staff, "bar": b1, "position": 768, "duration": 256},
        {"op": "add-tuplet", "staff": staff, "bar": b2, "position": 0, "duration": 512, "actual": 3,
         "normal": 2, "notes": [[67], [], [69, 72]]},
        {"op": "add-note", "staff": staff, "bar": b2, "position": 512, "duration": 512, "pitches": [71],
         "spellings": ["Cb"]},
        {"op": "add-text", "staff": staff, "bar": b2, "position": 0, "text": "dolce"},
        {"op": "add-lyric", "staff": staff, "bar": b2, "position": 512, "duration": 512, "text": "la"},
        {"op": "add-line", "staff": staff, "bar": b3, "position": 0, "duration": 1024,
         "styleId": "line.staff.octava.plus8"},
        {"op": "add-clef", "staff": staff, "bar": b4, "position": 0, "clef": "alto"},
        {"op": "set-key", "bar": b3, "key": "Eb"},
        {"op": "set-break", "bar": b2, "type": "system"},
        {"op": "set-barline", "bar": b3, "type": "double"},
        {"op": "set-bar-number", "bar": b4, "number": 100},
    ]


async def run(port: int, force: bool) -> int:
    async with MuseScoreClient(port=port) as client:
        bridge = MuseScoreBridge(client)
        overview = await service.overview(bridge)
        name, bars = overview["score"]["name"], overview["bars"]
        print(f"MuseScore {overview['mscore']}, bridge {overview['bridge']}, score {name!r}, {bars} bars")
        if "scratch" not in name.lower() and not force:
            print("refusing: the score's name does not contain 'Scratch' (use --force)")
            return 2
        if bars < 8 or overview["score"]["staves"] < 2:
            print("refusing: the check needs at least 8 bars and 2 staves")
            return 2
        staff, first = 2, bars - 3

        start = await state(bridge)
        marker = await service.apply(bridge, [{"op": "add-text", "staff": 1, "bar": 1, "position": 0,
                                               "text": MARKER}])
        check("marker added (one undo step)", marker["undoSteps"] == 1)
        baseline = await state(bridge)

        batch = every_op_batch(staff, first)
        dry = await service.apply(bridge, batch, dry_run=True)
        check("dry run of every kind of op", dry["applied"] >= len(batch), f"{dry['applied']} primitives")
        check("dry run left the score unchanged", await state(bridge) == baseline)

        real = await service.apply(bridge, batch)
        after = await state(bridge)
        check("real run changed the score", after != baseline)
        notes = await service.query(bridge, staves=[str(staff)], from_bar=first, to_bar=first + 3, types=["Chord"])
        check("real run added the notes", notes["count"] >= 6, f"{notes['count']} chords")
        await service.undo(bridge, real["undoSteps"])
        check("one undo restored the score, marker kept", await state(bridge) == baseline)

        lyric_batch = [{"op": "add-lyric", "staff": staff, "bar": first, "position": p, "duration": 256,
                        "text": t, "syllableType": s}
                       for p, t, s in ((0, "Ma", "middle"), (256, "king", "end"), (512, "joy", "end"))]
        notes_first = [{"op": "add-note", "staff": staff, "bar": first, "position": p, "duration": 256,
                        "pitches": [72]} for p in (0, 256, 512)]
        await service.apply(bridge, notes_first + lyric_batch)
        read = await service.read_lyrics(bridge, str(staff))
        check("read_lyrics", read["text"] == "Ma-king joy", read["text"])
        edited = await service.edit_lyrics(bridge, str(staff), "Mak-ing joy")
        check("edit_lyrics", edited["after"] == "Mak-ing joy" and edited["undoSteps"] == 1, edited["after"])
        await service.undo(bridge, 2)
        check("lyrics undone, marker kept", await state(bridge) == baseline)

        with tempfile.TemporaryDirectory() as tmp:
            for fmt, suffix in (("pdf", ".pdf"), ("png", ".png"), ("svg", ".svg"), ("musicxml", ".musicxml"),
                                ("musicxml", ".xml"), ("mxl", ".mxl"), ("mid", ".mid"), ("mp3", ".mp3"),
                                ("wav", ".wav"), ("flac", ".flac"), ("ogg", ".ogg")):
                began = time.monotonic()
                out = await service.export(bridge, fmt, str(Path(tmp) / f"check{suffix}"))
                sizes = [Path(f).stat().st_size for f in out["files"]]
                check(f"export {fmt} ({suffix})", all(sizes),
                      f"{len(sizes)} file(s), {sum(sizes)} bytes, {time.monotonic() - began:.1f} s")
        check("exports left the score unchanged", await state(bridge) == baseline)

        info = await service.project_info(bridge)
        old = info["fields"]["subtitle"]
        changed = await service.set_project_info(bridge, {"subtitle": "live check"})
        check("set_project_info", changed["after"]["subtitle"] == "live check")
        await service.set_project_info(bridge, {"subtitle": old})
        check("metadata restored", (await service.project_info(bridge))["fields"]["subtitle"] == old)

        dry_part = await service.add_instrument(bridge, "violin", dry_run=True)
        check("add_instrument dry run", dry_part["added"]["instrumentId"] == "violin"
              and await state(bridge) == baseline)
        part = await service.add_instrument(bridge, "soprano")
        check("add_instrument", part["staves"][0]["partName"] == "Soprano")
        await service.undo(bridge, part["undoSteps"])
        playback = await service.set_staff_playback(bridge, ["1"], False)
        check("set_staff_playback off", playback["staves"][0]["playback"] == [False] * 4)
        await service.undo(bridge, playback["undoSteps"])
        check("instrument and playback undone, marker kept", await state(bridge) == baseline)

        await service.undo(bridge, 1)
        check("marker undone: the score is as it started", await state(bridge) == start)

    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} passed")
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=install.DEFAULT_PORT)
    parser.add_argument("--force", action="store_true", help="run on a score not named Scratch...")
    args = parser.parse_args()
    return asyncio.run(run(args.port, args.force))


if __name__ == "__main__":
    sys.exit(main())
