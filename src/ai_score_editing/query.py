"""Selector parsing and validation for the bridge's generic Query handler."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ai_score_editing.core.errors import ScoreEditingError

# Properties the bridge may read through obj.@name, per object kind. The
# source of truth is query_props.json, which scripts/dev/gen_query_props.py turns
# into QueryPropTable in ScoreBridge.plg (a test runs it with --check). The
# plug-in enforces its own copy; this one turns typos into errors before
# connecting, since an unknown name there would silently match nothing.
_PROPS = json.loads((Path(__file__).with_name("query_props.json")).read_text())
COMMON_PROPS = frozenset(_PROPS["common"])
READABLE_PROPS: dict[str, frozenset[str]] = {
    kind: frozenset(names) for kind, names in _PROPS["types"].items()
}
# Note-level properties; match if any note of a NoteRest chord matches.
# Handled specially by the bridge, and filter-only: results list every
# note's pitch and bracketed state anyway.
# Enumerated from NthBar / NthStaff rather than from bar objects; they take
# only their own properties, not COMMON_PROPS.
CONTAINER_KINDS = frozenset(_PROPS["containers"])
FONT_FIELDS = frozenset({"InitialFontName", "InitialFontSize"})
PSEUDO_PROPS = frozenset({"Pitch", "Bracketed"})
OPERATORS = ("<=", ">=", "!=", "=", "<", ">")
DEFAULT_LIMIT = 500

_WHERE = re.compile(r"^\s*([A-Za-z]+)\s*(<=|>=|!=|=|<|>)\s*(.*?)\s*$")


class QueryError(ScoreEditingError):
    """A query selector is malformed or names an unreadable property."""


def known_props() -> frozenset[str]:
    names = set(COMMON_PROPS) | PSEUDO_PROPS
    for props in READABLE_PROPS.values():
        names |= props
    return frozenset(names)


def parse_where(expression: str) -> dict[str, Any]:
    """Parse 'Prop OP value' into a bridge condition.

    Values are integers, true/false, or strings (optionally quoted).
    """
    match = _WHERE.match(expression)
    if not match:
        raise QueryError(f"cannot parse condition {expression!r}; expected e.g. 'Pitch>=72'")
    prop, op, raw = match.groups()
    if prop not in known_props():
        raise QueryError(f"unknown property {prop!r} in where condition; readable: {', '.join(sorted(known_props()))}")
    return {"prop": prop, "op": op, "value": _parse_value(raw)}


def _parse_value(raw: str) -> Any:
    if raw == "":
        raise QueryError("missing value in where condition")
    if raw.lower() in {"true", "false"}:
        return raw.lower() == "true"
    if re.fullmatch(r"-?\d+", raw):
        return int(raw)
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "'\"":
        return raw[1:-1]
    return raw


def parse_fields(values: list[str]) -> list[str]:
    fields = [name.strip() for value in values for name in value.split(",") if name.strip()]
    unknown = sorted(set(fields) - (known_props() - PSEUDO_PROPS))
    if unknown:
        raise QueryError(f"unknown field(s) {', '.join(unknown)}")
    return fields


def resolve_staves(requested: list[str], staves: list[dict[str, Any]]) -> list[int]:
    """Map staff numbers or instrument names (case-insensitive) to numbers.

    "0" or "system" is the system staff, which holds tempo and other system
    text and system lines.
    """
    result: list[int] = []
    for item in requested:
        if item == "0" or item.casefold() == "system":
            result.append(0)
            continue
        if item.isdigit():
            number = int(item)
            if not any(staff["staffNum"] == number for staff in staves):
                raise QueryError(f"staff {number} does not exist")
            result.append(number)
            continue
        wanted = item.casefold()
        matches = [
            staff["staffNum"]
            for staff in staves
            if wanted in {
                str(staff.get("instrumentName", "")).casefold(),
                str(staff.get("fullInstrumentName", "")).casefold(),
            }
        ]
        if not matches:
            raise QueryError(f"no staff named {item!r}")
        result.extend(matches)
    return result


def build_selector(
    *,
    staves: list[int],
    from_bar: int | None,
    to_bar: int | None,
    types: list[str],
    voice: int | None,
    where: list[str],
    fields: list[str],
    limit: int = DEFAULT_LIMIT,
) -> dict[str, Any]:
    if voice is not None and not 1 <= voice <= 4:
        raise QueryError("--voice must be 1-4")
    if limit < 1:
        raise QueryError("--limit must be positive")
    selector: dict[str, Any] = {
        "staves": staves,
        "types": [t.strip() for value in types for t in value.split(",") if t.strip()],
        "where": [parse_where(expression) for expression in where],
        "fields": parse_fields(fields),
        "voice": voice or 0,
        "limit": limit,
    }
    if from_bar is not None:
        selector["fromBar"] = from_bar
    if to_bar is not None:
        selector["toBar"] = to_bar
    return selector
