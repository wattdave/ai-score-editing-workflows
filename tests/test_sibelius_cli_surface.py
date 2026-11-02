"""Golden record of the sibelius-cli command line surface.

Walks ``build_parser()`` and records every subcommand (aliases included) with
its option strings, defaults, choices, arity and types. Moving handlers into
other modules must not change this file's golden JSON.

Regenerate after an intended change with ``UPDATE_GOLDEN=1 uv run pytest
tests/test_sibelius_cli_surface.py``.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from ai_score_editing.sibelius.cli import build_parser

GOLDEN = Path(__file__).parent / "fixtures" / "golden" / "sibelius_cli_surface.json"


def _plain(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_plain(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, Path):
        return str(value)
    if callable(value):
        return f"<callable {getattr(value, '__name__', type(value).__name__)}>"
    return f"<{type(value).__name__}>"


def _action(action: argparse.Action) -> dict[str, Any]:
    return {
        "dest": action.dest,
        "kind": type(action).__name__,
        "options": list(action.option_strings),
        "default": _plain(action.default),
        "choices": _plain(list(action.choices)) if action.choices is not None else None,
        "nargs": action.nargs,
        "type": getattr(action.type, "__name__", None) if action.type else None,
        "required": action.required,
        "const": _plain(action.const),
        "metavar": _plain(action.metavar),
    }


def _walk(parser: argparse.ArgumentParser) -> dict[str, Any]:
    arguments: list[dict[str, Any]] = []
    subcommands: dict[str, Any] = {}
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for name, sub in action.choices.items():
                subcommands[name] = _walk(sub)
        elif not isinstance(action, argparse._HelpAction):
            arguments.append(_action(action))
    result: dict[str, Any] = {"arguments": arguments}
    if subcommands:
        result["subcommands"] = subcommands
    return result


def _surface() -> dict[str, Any]:
    return _walk(build_parser())


def test_cli_surface_matches_golden() -> None:
    surface = json.loads(json.dumps(_surface()))
    if os.environ.get("UPDATE_GOLDEN"):
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(json.dumps(surface, indent=1, sort_keys=True) + "\n")
    expected = json.loads(GOLDEN.read_text())
    assert surface == expected, "CLI surface changed; if intended, rerun with UPDATE_GOLDEN=1"


def test_surface_includes_known_aliases() -> None:
    names = set(_surface()["subcommands"])
    assert {"create-staff", "add-note", "demix"} <= names
    assert len(names) > 50
