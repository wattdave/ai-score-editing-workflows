"""Command line for the Dorico back end: `uv run dorico-cli <command>`.

Prints JSON. The first connection shows an approval prompt in Dorico; the
session token is then stored in ~/.config/ai-score-editing/dorico-token.json.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from ai_score_editing.barrange import parse_bar_range
from ai_score_editing.cli_common import (
    DEFAULT_LIMIT,
    EXIT_COMMAND_FAILED,
    EXIT_CONNECTION_FAILED,
    EXIT_OK,
    add_path_or_positional,
    canonical_format,
    resolve_path,
)

from . import lyrics_dialog, project_info, service
from .bridge import DoricoBridge
from .client import DEFAULT_PORT, DoricoClient, DoricoConnectionError, DoricoError
from .score import DoricoBatchError


def add_staff_or_player(parser: argparse.ArgumentParser) -> None:
    """--staff (number or player name), or the old positional player name."""
    parser.add_argument("player", nargs="?", help="player name (deprecated positional; use --staff)")
    parser.add_argument("--staff", help="staff number or player name")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dorico-cli", description="Drive the project open in Dorico.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--client-name", help="name Dorico approves (default ai-score-editing)")
    parser.add_argument("--no-approval", action="store_true", help="fail rather than show an approval prompt")
    parser.add_argument("--flow", type=int, default=1)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("overview", help="title, flows, staves, layouts")
    sub.add_parser("structure", help="bar lengths and key signature positions")
    query = sub.add_parser("query", help="find events")
    query.add_argument("--staff", action="append", dest="staves")
    query.add_argument("--bars")
    query.add_argument("--type", action="append", dest="types")
    query.add_argument("--voice", type=int)
    query.add_argument("--where", action="append")
    query.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    query.add_argument("--lyrics", action="store_true", help="add lyric text (exports MusicXML)")
    apply = sub.add_parser("apply", help="apply a JSON batch as one undo step")
    source = apply.add_mutually_exclusive_group(required=True)
    source.add_argument("--file")
    source.add_argument("--json")
    apply.add_argument("--dry-run", action="store_true")
    apply.add_argument("--no-backup", action="store_true", help="do not save a copy of the project before a real run")
    apply.add_argument("--backup-dir", help="where the copy goes (else $DORICO_BACKUP_DIR, $SCORE_BACKUP_DIR, the cache)")
    lyrics = sub.add_parser("lyrics", help="read a player's line of lyrics")
    add_staff_or_player(lyrics)
    lyrics.add_argument("--verse", type=int, default=1)
    edit_lyrics = sub.add_parser("edit-lyrics", help="replace a player's line of lyrics (same syllable count)")
    add_staff_or_player(edit_lyrics)
    edit_lyrics.add_argument("positional_text", nargs="?", metavar="text", help="the new line of lyrics")
    edit_lyrics.add_argument("--text", help="the new line of lyrics")
    edit_lyrics.add_argument("--verse", type=int, default=1)
    sub.add_parser("info", help="read the Project Info fields")
    set_info = sub.add_parser("set-info", help="set Project Info fields, e.g. Composer=Traditional")
    set_info.add_argument("fields", nargs="*", metavar="NAME=VALUE")
    set_info.add_argument("--field", action="append", default=[], metavar="NAME=VALUE", help="same as the positionals")
    undo = sub.add_parser("undo")
    undo.add_argument("--steps", type=int, default=1)
    save = sub.add_parser("save", help="save the project (to its own file, or a copy at path)")
    add_path_or_positional(save, "save a copy to this .dorico file instead")
    export = sub.add_parser("export", help="export as pdf, musicxml or a first-page preview")
    add_path_or_positional(export, "where to write the export (required in Dorico)")
    export.add_argument("--format", type=canonical_format, choices=service.EXPORT_FORMATS, default="pdf")
    return parser


async def run(args: argparse.Namespace) -> Any:
    client = DoricoClient(port=args.port, client_name=args.client_name, allow_approval=not args.no_approval)
    async with client:
        bridge = DoricoBridge(client)
        if args.command == "overview":
            return await service.overview(bridge, args.flow)
        if args.command == "structure":
            return await service.structure(bridge, args.flow)
        if args.command == "query":
            first, last = parse_bar_range(bars=args.bars) if args.bars else (None, None)
            return await service.query(
                bridge, flow=args.flow, staves=args.staves, from_bar=first, to_bar=last,
                types=args.types, voice=args.voice, where=args.where, limit=args.limit, lyrics=args.lyrics,
            )
        if args.command == "apply":
            text = Path(args.file).expanduser().read_text() if args.file else args.json
            return await service.apply(bridge, json.loads(text), flow=args.flow, dry_run=args.dry_run,
                                      backup_copy=not args.no_backup, backup_dir=args.backup_dir)
        if args.command == "lyrics":
            player = await service.resolve_player(bridge, args.staff, args.player, args.flow)
            return await lyrics_dialog.read_lyrics(bridge, player, args.verse)
        if args.command == "edit-lyrics":
            if args.staff is not None and args.player is not None and args.positional_text is None:
                args.player, args.positional_text = None, args.player  # edit-lyrics --staff 1 "text"
            if args.text is not None and args.positional_text is not None:
                raise ValueError("pass the text once: positionally or with --text")
            text = args.text if args.text is not None else args.positional_text
            if text is None:
                raise ValueError("edit-lyrics needs the new text (--text)")
            player = await service.resolve_player(bridge, args.staff, args.player, args.flow)
            return await lyrics_dialog.edit_lyrics(bridge, player, text, args.verse)
        if args.command == "info":
            return await project_info.read_project_info(bridge)
        if args.command == "set-info":
            pairs = [f.split("=", 1) for f in [*args.fields, *args.field]]
            if not pairs:
                raise ValueError("set-info needs at least one NAME=VALUE (--field)")
            if any(len(p) != 2 for p in pairs):
                raise ValueError("fields must be NAME=VALUE")
            return await project_info.set_project_info(bridge, dict(pairs))
        if args.command == "undo":
            return await service.undo(bridge, args.steps)
        if args.command == "save":
            return await service.save(bridge, resolve_path(args))
        if args.command == "export":
            return await service.export(bridge, args.format, resolve_path(args))
    raise AssertionError(args.command)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = asyncio.run(run(args))
    except DoricoConnectionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_CONNECTION_FAILED
    except (DoricoError, DoricoBatchError, json.JSONDecodeError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_COMMAND_FAILED
    print(json.dumps(result, indent=2))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
