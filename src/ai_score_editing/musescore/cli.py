"""Command line for the MuseScore back end: `uv run musescore-cli <command>`.

Prints JSON. Run `install-plugin` once, restart MuseScore, then choose
Plugins > sibwscli bridge in the window of the score to work on (each
MuseScore window is its own process, and the bridge serves its own window).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from ai_score_editing.batch_ops import BatchError
from ai_score_editing.barrange import parse_bar_range
from ai_score_editing.query import QueryError

from . import install, service
from .bridge import MuseScoreBridge
from .client import MuseScoreClient, MuseScoreError
from .score import MuseScoreBatchError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="musescore-cli", description="Drive the score open in MuseScore 4.")
    parser.add_argument("--port", type=int, default=install.DEFAULT_PORT)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("install-plugin", help="write the bridge plug-in into MuseScore's plug-in folder")
    sub.add_parser("overview", help="versions, score name, metadata, staves and bar count")
    structure = sub.add_parser("structure", help="key and time signatures, barlines, breaks, bar numbers, layout")
    structure.add_argument("--bars", help="e.g. 1-40 (default all)")
    query = sub.add_parser("query", help="find objects by staff, bars, type, voice and conditions")
    query.add_argument("--staff", action="append", dest="staves", help="number, part name, or 0/system")
    query.add_argument("--bars", help="e.g. 5 or 12-20")
    query.add_argument("--type", action="append", dest="types")
    query.add_argument("--voice", type=int)
    query.add_argument("--where", action="append", help="e.g. 'Pitch>=72'")
    query.add_argument("--field", action="append", dest="fields")
    query.add_argument("--limit", type=int, default=200)
    apply = sub.add_parser("apply", help="apply a JSON batch as one undo step")
    source = apply.add_mutually_exclusive_group(required=True)
    source.add_argument("--file")
    source.add_argument("--json")
    apply.add_argument("--dry-run", action="store_true", help="run the batch, report it, and roll it back")
    undo = sub.add_parser("undo", help="undo the last change(s) in MuseScore")
    undo.add_argument("--steps", type=int, default=1)
    save = sub.add_parser("save", help="save the score to its own file (File > Save)")
    save.add_argument("--path", help="also copy the saved file here")
    export = sub.add_parser("export", help="export the score as pdf, png, svg, musicxml, mxl, mid or audio")
    export.add_argument("--format", required=True, choices=list(service.EXPORT_FORMATS))
    export.add_argument("--path", required=True)
    sub.add_parser("info", help="the score's metadata (title, composer, lyricist, ...)")
    set_info = sub.add_parser("set-info", help="set metadata fields (not undoable)")
    set_info.add_argument("--field", action="append", required=True, metavar="NAME=VALUE")
    lyrics = sub.add_parser("lyrics", help="a staff's verse as one line of text")
    lyrics.add_argument("--staff", required=True, help="number or part name")
    lyrics.add_argument("--verse", type=int, default=1)
    edit = sub.add_parser("edit-lyrics", help="replace a staff's verse (same syllable count)")
    edit.add_argument("--staff", required=True, help="number or part name")
    edit.add_argument("--verse", type=int, default=1)
    edit.add_argument("--text", required=True)
    instrument = sub.add_parser("add-instrument", help="append a part by MuseScore instrument id or name")
    instrument.add_argument("instrument", help="e.g. violin, soprano, bb-clarinet")
    instrument.add_argument("--dry-run", action="store_true")
    playback = sub.add_parser("playback", help="silence or restore staves in playback")
    playback.add_argument("--staff", action="append", dest="staves", required=True, help="number or part name")
    playback.add_argument("--voice", action="append", type=int, dest="voices", help="1-4 (default all)")
    state = playback.add_mutually_exclusive_group(required=True)
    state.add_argument("--off", action="store_false", dest="play")
    state.add_argument("--on", action="store_true", dest="play")
    return parser


async def run(args: argparse.Namespace) -> Any:
    async with MuseScoreClient(port=args.port) as client:
        bridge = MuseScoreBridge(client)
        if args.command == "overview":
            return await service.overview(bridge)
        if args.command == "structure":
            first, last = parse_bar_range(bars=args.bars) if args.bars else (None, None)
            return await service.structure(bridge, first, last)
        if args.command == "query":
            first, last = parse_bar_range(bars=args.bars) if args.bars else (None, None)
            return await service.query(
                bridge, staves=args.staves, from_bar=first, to_bar=last, types=args.types,
                voice=args.voice, where=args.where, fields=args.fields, limit=args.limit,
            )
        if args.command == "apply":
            text = Path(args.file).expanduser().read_text() if args.file else args.json
            return await service.apply(bridge, json.loads(text), dry_run=args.dry_run)
        if args.command == "undo":
            return await bridge.undo(args.steps)
        if args.command == "save":
            return await service.save(bridge, args.path)
        if args.command == "export":
            return await service.export(bridge, args.format, args.path)
        if args.command == "info":
            return await service.project_info(bridge)
        if args.command == "set-info":
            fields = dict(item.split("=", 1) for item in args.field if "=" in item)
            if len(fields) != len(args.field):
                raise ValueError("each --field is NAME=VALUE")
            return await service.set_project_info(bridge, fields)
        if args.command == "add-instrument":
            return await service.add_instrument(bridge, args.instrument, dry_run=args.dry_run)
        if args.command == "playback":
            return await service.set_staff_playback(bridge, args.staves, args.play, args.voices)
        if args.command == "lyrics":
            return await service.read_lyrics(bridge, args.staff, args.verse)
        if args.command == "edit-lyrics":
            return await service.edit_lyrics(bridge, args.staff, args.text, args.verse)
    raise AssertionError(args.command)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "install-plugin":
        path = install.install(args.port)
        print(json.dumps({
            "installed": str(path),
            "next": [
                "Restart MuseScore (a changed plug-in is only loaded at startup).",
                f"Plugins > Manage plugins: enable '{install.PLUGIN_TITLE}' (once).",
                f"Plugins > {install.PLUGIN_TITLE}, in the window of the score to work on.",
            ],
        }, indent=2))
        return 0
    try:
        result = asyncio.run(run(args))
    except (MuseScoreError, MuseScoreBatchError, BatchError, QueryError, json.JSONDecodeError,
            OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
