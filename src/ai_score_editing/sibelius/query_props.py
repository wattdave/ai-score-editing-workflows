"""Sibelius's query vocabulary: the properties the bridge may read through obj.@name.

The source of truth is ../query_props.json, which scripts/dev/gen_query_props.py
turns into QueryPropTable in ScoreBridge.plg (a test runs it with --check). The
plug-in enforces its own copy; this one turns typos into errors before
connecting, since an unknown name there would silently match nothing.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ai_score_editing.core import query as core_query
from ai_score_editing.core.query import Vocabulary

PROPS_FILE = Path(__file__).resolve().parent.parent / "query_props.json"
_PROPS = json.loads(PROPS_FILE.read_text())
COMMON_PROPS = frozenset(_PROPS["common"])
READABLE_PROPS: dict[str, frozenset[str]] = {
    kind: frozenset(names) for kind, names in _PROPS["types"].items()
}
# Enumerated from NthBar / NthStaff rather than from bar objects; they take
# only their own properties, not COMMON_PROPS.
CONTAINER_KINDS = frozenset(_PROPS["containers"])
FONT_FIELDS = frozenset({"InitialFontName", "InitialFontSize"})
# Note-level properties; match if any note of a NoteRest chord matches.
# Handled specially by the bridge, and filter-only: results list every
# note's pitch and bracketed state anyway.
PSEUDO_PROPS = frozenset({"Pitch", "Bracketed"})

#: Staff records from GetStaves: the number, and the short and full instrument names.
NUMBER_KEY = "staffNum"
NAME_KEYS = ("instrumentName", "fullInstrumentName")


def known_props() -> frozenset[str]:
    names = set(COMMON_PROPS) | PSEUDO_PROPS
    for props in READABLE_PROPS.values():
        names |= props
    return frozenset(names)


VOCABULARY = Vocabulary(
    properties={name: None for name in known_props()},
    fields=known_props() - PSEUDO_PROPS,
)


def parse_where(expression: str) -> dict[str, Any]:
    """Parse 'Prop OP value' into a bridge condition."""
    return core_query.parse_where(expression, VOCABULARY)


def parse_fields(values: list[str]) -> list[str]:
    return core_query.parse_fields(values, VOCABULARY)


def resolve_staves(requested: list[str], staves: list[dict[str, Any]]) -> list[int]:
    """Map staff numbers or instrument names (case-insensitive) to numbers."""
    return core_query.resolve_staves(requested, staves, number_key=NUMBER_KEY, name_keys=NAME_KEYS)


def build_selector(**kwargs: Any) -> dict[str, Any]:
    """core.query.build_selector with Sibelius's vocabulary (same keyword arguments)."""
    return core_query.build_selector(vocabulary=VOCABULARY, **kwargs)
