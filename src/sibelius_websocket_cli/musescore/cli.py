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
from typing import Any

from . import install
from .bridge import MuseScoreBridge
from .client import MuseScoreClient, MuseScoreError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="musescore-cli", description="Drive the score open in MuseScore 4.")
    parser.add_argument("--port", type=int, default=install.DEFAULT_PORT)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("install-plugin", help="write the bridge plug-in into MuseScore's plug-in folder")
    sub.add_parser("overview", help="versions, score name, metadata and staves")
    undo = sub.add_parser("undo", help="undo the last change(s) in MuseScore")
    undo.add_argument("--steps", type=int, default=1)
    return parser


async def run(args: argparse.Namespace) -> Any:
    async with MuseScoreClient(port=args.port) as client:
        bridge = MuseScoreBridge(client)
        if args.command == "overview":
            return await bridge.overview()
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
    except (MuseScoreError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
