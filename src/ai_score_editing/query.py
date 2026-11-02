"""Old home of Sibelius's query selector code; the names live on here.

The shared engine is core/query.py and Sibelius's property vocabulary is
sibelius/query_props.py. parse_where, parse_fields, resolve_staves and
build_selector here are bound to Sibelius's vocabulary, as before.
"""

from __future__ import annotations

from ai_score_editing.cli_common import DEFAULT_LIMIT
from ai_score_editing.core.errors import QueryError
from ai_score_editing.core.query import OPERATORS
from ai_score_editing.sibelius.query_props import (
    COMMON_PROPS,
    CONTAINER_KINDS,
    FONT_FIELDS,
    PSEUDO_PROPS,
    READABLE_PROPS,
    build_selector,
    known_props,
    parse_fields,
    parse_where,
    resolve_staves,
)

__all__ = [
    "COMMON_PROPS",
    "CONTAINER_KINDS",
    "DEFAULT_LIMIT",
    "FONT_FIELDS",
    "OPERATORS",
    "PSEUDO_PROPS",
    "QueryError",
    "READABLE_PROPS",
    "build_selector",
    "known_props",
    "parse_fields",
    "parse_where",
    "resolve_staves",
]
