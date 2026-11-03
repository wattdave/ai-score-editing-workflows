"""Command-line interface (docs/sibelius-protocol.md 2.2)."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from collections.abc import Callable
from inspect import isawaitable
from typing import Any

from ai_score_editing.cli_common import EXIT_COMMAND_FAILED, EXIT_CONNECTION_FAILED
from ai_score_editing.sibelius import commands, protocol, service
from ai_score_editing.sibelius.bridge import BridgeError
from ai_score_editing.sibelius.client import ConnectionFailed, run_sync

# Handlers of the areas already moved into ``sibelius/commands/``; filled by build_parser().
_MIGRATED: dict[str, Callable[..., Any]] = {}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sibelius-cli",
        description="Drive Sibelius via its Sibelius Connect WebSocket interface.",
    )
    parser.add_argument("--host", default=protocol.DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=protocol.DEFAULT_PORT)
    parser.add_argument("--client-name", default=protocol.DEFAULT_CLIENT_NAME)
    parser.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        help="seconds to wait for connection approval in Sibelius",
    )
    parser.add_argument(
        "--launch",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="start Sibelius if not already running (default: True)",
    )
    parser.add_argument(
        "--launch-timeout",
        type=float,
        default=30.0,
        help="seconds to wait for Sibelius to start and open port (default: 30)",
    )
    parser.add_argument(
        "--sibelius-path",
        help="custom path to Sibelius application or executable",
    )
    parser.add_argument("--json", action="store_true", help="print raw JSON responses")
    parser.add_argument(
        "--expect-file",
        help="refuse writes unless the active score resolves to this path",
    )
    parser.add_argument(
        "--backup-dir",
        help="put the timestamped .sib backups of write commands in this folder instead of "
        "beside the score (default: the SIBELIUS_BACKUP_DIR environment variable, else beside the score)",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="log the wire traffic")

    sub = parser.add_subparsers(dest="subcommand", required=True)
    _MIGRATED.clear()
    _MIGRATED.update(commands.register_all(sub))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    # Resolve the backup folder once; every backup (CLI, skill scripts) reads it back
    # through service.backup_folder().
    folder = service.backup_folder(args.backup_dir)
    if folder is not None:
        os.environ[service.BACKUP_DIR_ENV] = str(folder)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(message)s",
    )

    handler = _MIGRATED[args.subcommand]
    try:
        result = handler(args)
        if isawaitable(result):
            result = run_sync(result)
        return int(result)
    except BridgeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_COMMAND_FAILED
    except ConnectionFailed as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_CONNECTION_FAILED
    except TimeoutError:
        print("error: timed out waiting for a response from Sibelius", file=sys.stderr)
        return EXIT_CONNECTION_FAILED
