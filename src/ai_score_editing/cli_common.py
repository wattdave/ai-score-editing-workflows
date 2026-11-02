"""Pieces the three command lines and MCP servers share: exit codes, limits, format names."""

from __future__ import annotations

import argparse

EXIT_OK = 0
EXIT_COMMAND_FAILED = 1
EXIT_CONNECTION_FAILED = 2

#: Default maximum objects query_score and the query commands return.
DEFAULT_LIMIT = 200

#: Old export format spellings, accepted wherever a format is taken.
FORMAT_ALIASES = {"mid": "midi"}


def canonical_format(name: str) -> str:
    """The canonical export format name for name (case-insensitive; "mid" is "midi")."""
    lowered = name.strip().lower()
    return FORMAT_ALIASES.get(lowered, lowered)


def add_path_or_positional(parser: argparse.ArgumentParser, help: str) -> None:
    """An optional positional path that is mutually exclusive with --path.

    Both land in args.path (the positional's dest is "positional_path"; call
    resolve_path afterwards).
    """
    group = parser.add_mutually_exclusive_group()
    group.add_argument("positional_path", nargs="?", metavar="path", help=help)
    group.add_argument("--path", help=help)


def resolve_path(args: argparse.Namespace) -> str | None:
    """The path given positionally or with --path (None when neither)."""
    return getattr(args, "positional_path", None) or getattr(args, "path", None)
