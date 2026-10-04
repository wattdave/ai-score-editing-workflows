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

from sibelius_websocket_cli.batch_ops import BatchError
from sibelius_websocket_cli.cli import parse_bar_range
from sibelius_websocket_cli.query import QueryError

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
    return parser


async def run(args: argparse.Namespace) -> Any:
    async with MuseScoreClient(port=args.port) as client:
        bridge = MuseScoreBridge(client)
        if args.command == "overview":
            return await service.overview(bridge)
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
