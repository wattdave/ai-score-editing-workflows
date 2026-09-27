"""Command line for the Dorico back end: `uv run dorico-cli <command>`.

Prints JSON. The first connection shows an approval prompt in Dorico; the
session token is then stored in ~/.config/sibelius-websocket-cli/dorico-token.json.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from sibelius_websocket_cli.cli import parse_bar_range

from . import service
from .bridge import DoricoBridge
from .client import DEFAULT_PORT, DoricoClient, DoricoError
from .score import DoricoBatchError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dorico-cli", description="Drive the project open in Dorico.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--client-name", help="name Dorico approves (default sibelius-websocket-cli)")
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
    query.add_argument("--limit", type=int, default=200)
    apply = sub.add_parser("apply", help="apply a JSON batch as one undo step")
    source = apply.add_mutually_exclusive_group(required=True)
    source.add_argument("--file")
    source.add_argument("--json")
    apply.add_argument("--dry-run", action="store_true")
    undo = sub.add_parser("undo")
    undo.add_argument("--steps", type=int, default=1)
    save = sub.add_parser("save", help="save the project to a .dorico file")
    save.add_argument("path")
    export = sub.add_parser("export", help="export the first-page preview")
    export.add_argument("path")
    export.add_argument("--format", choices=sorted(service.EXPORT_FORMATS), default="preview-pdf")
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
                types=args.types, voice=args.voice, where=args.where, limit=args.limit,
            )
        if args.command == "apply":
            text = Path(args.file).expanduser().read_text() if args.file else args.json
            return await service.apply(bridge, json.loads(text), flow=args.flow, dry_run=args.dry_run)
        if args.command == "undo":
            return await service.undo(bridge, args.steps)
        if args.command == "save":
            return await service.save(bridge, args.path)
        if args.command == "export":
            return await service.export(bridge, args.format, args.path)
    raise AssertionError(args.command)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = asyncio.run(run(args))
    except (DoricoError, DoricoBatchError, json.JSONDecodeError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
