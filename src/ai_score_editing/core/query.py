"""The query engine all three back ends share: where clauses, staff names, selectors.

A back end supplies only its property vocabulary (a Vocabulary) and, for staff
names, which keys of its staff records hold the number and the names. Parsing,
comparison and selector building live here once.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from ai_score_editing.cli_common import DEFAULT_LIMIT
from ai_score_editing.core.errors import QueryError, ScoreEditingError

__all__ = [
    "DEFAULT_LIMIT",
    "OPERATORS",
    "QueryError",
    "Vocabulary",
    "build_selector",
    "compare",
    "holds",
    "parse_fields",
    "parse_value",
    "parse_where",
    "resolve_staves",
]

OPERATORS = ("<=", ">=", "!=", "=", "<", ">")
_WHERE = re.compile(r"^\s*(\w+)\s*(<=|>=|!=|=|<|>)\s*(.*?)\s*$")
_INT = re.compile(r"-?\d+")


@dataclass(frozen=True)
class Vocabulary:
    """The properties one back end can filter on, and how it words its errors.

    `properties` maps each name usable in a where clause to the type of its
    values: int, str or bool make the value parser read the right-hand side as
    that type (a str field keeps `true` and `12` as text), None accepts any of
    int, true/false or string. `fields` names the properties a query may return
    (default: all of `properties`). The message templates take {expression},
    {prop} and {names}.
    """

    properties: Mapping[str, type | None]
    fields: frozenset[str] | None = None
    error: type[ScoreEditingError] = QueryError
    sort_names: bool = True
    unparsable: str = "cannot parse condition {expression!r}; expected e.g. 'Pitch>=72'"
    unknown: str = "unknown property {prop!r} in where condition; readable: {names}"
    missing: str = "missing value in where condition"
    names: str = field(init=False, default="")

    def __post_init__(self) -> None:
        listed = sorted(self.properties) if self.sort_names else list(self.properties)
        object.__setattr__(self, "names", ", ".join(listed))

    @property
    def readable(self) -> frozenset[str]:
        return self.fields if self.fields is not None else frozenset(self.properties)


def parse_value(raw: str, kind: type | None = None) -> Any:
    """Read the right-hand side of a condition: a quoted string, an int, true/false, or text.

    A quoted value is always a string, except that an int field still reads a
    quoted whole number. `kind` str keeps everything else as text too.
    """
    quoted = len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "'\""
    if quoted:
        inner = raw[1:-1]
        return int(inner) if kind is int and _INT.fullmatch(inner) else inner
    if kind is str:
        return raw
    if kind is not bool and _INT.fullmatch(raw):
        return int(raw)
    if kind is not int and raw.lower() in {"true", "false"}:
        return raw.lower() == "true"
    return raw


def parse_where(expression: str, vocabulary: Vocabulary) -> dict[str, Any]:
    """Parse 'Prop OP value' into a {"prop", "op", "value"} condition."""
    match = _WHERE.match(expression)
    if not match:
        raise vocabulary.error(
            vocabulary.unparsable.format(expression=expression, prop="", names=vocabulary.names)
        )
    prop, op, raw = match.groups()
    if prop not in vocabulary.properties:
        raise vocabulary.error(
            vocabulary.unknown.format(expression=expression, prop=prop, names=vocabulary.names)
        )
    if raw == "":
        raise vocabulary.error(
            vocabulary.missing.format(expression=expression, prop=prop, names=vocabulary.names)
        )
    return {"prop": prop, "op": op, "value": parse_value(raw, vocabulary.properties[prop])}


def parse_fields(values: list[str], vocabulary: Vocabulary) -> list[str]:
    """Split comma-separated field names and check them against what the back end can return."""
    fields = [name.strip() for value in values for name in value.split(",") if name.strip()]
    unknown = sorted(set(fields) - vocabulary.readable)
    if unknown:
        raise vocabulary.error(f"unknown field(s) {', '.join(unknown)}")
    return fields


def compare(actual: Any, op: str, value: Any) -> bool:
    """actual OP value; values that cannot be ordered against each other never match."""
    try:
        return {
            "=": actual == value, "!=": actual != value, ">": actual > value,
            "<": actual < value, ">=": actual >= value, "<=": actual <= value,
        }[op]
    except TypeError:
        return False


def holds(
    values: Mapping[str, Any],
    condition: Mapping[str, Any],
    multi: Mapping[str, Iterable[Any]] | None = None,
) -> bool:
    """Whether an object satisfies one condition.

    `values` maps property names to the object's value. A property in `multi`
    has several values (a chord's notes) and matches if any one does; an
    object without a value for a property matches only "!=".
    """
    prop, op, value = condition["prop"], condition["op"], condition["value"]
    if multi is not None and prop in multi:
        return any(compare(each, op, value) for each in multi[prop])
    actual = values.get(prop)
    if actual is None:
        return op == "!="
    return compare(actual, op, value)


def resolve_staves(
    requested: Iterable[Any],
    staves: list[dict[str, Any]],
    *,
    number_key: str,
    name_keys: tuple[str, ...],
    error: type[ScoreEditingError] = QueryError,
) -> list[int]:
    """Map staff numbers or names (case-insensitive) to staff numbers.

    "0" or "system" is the system staff, which holds tempo and other system
    text and system lines. A name matches every staff that has it.
    """
    result: list[int] = []
    for item in requested:
        text = str(item).strip()
        if text == "0" or text.casefold() == "system":
            result.append(0)
        elif text.isdigit():
            number = int(text)
            if not any(staff[number_key] == number for staff in staves):
                raise error(f"no staff {number}; staves are 1-{len(staves)}")
            result.append(number)
        else:
            wanted = text.casefold()
            matches = [
                staff[number_key]
                for staff in staves
                if any(str(staff.get(key) or "").casefold() == wanted for key in name_keys)
            ]
            if not matches:
                names = sorted({str(staff[key]) for staff in staves for key in name_keys if staff.get(key)})
                raise error(f"no staff named {text!r}; names: {', '.join(names) or 'none'}")
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
    vocabulary: Vocabulary,
    limit: int = DEFAULT_LIMIT,
) -> dict[str, Any]:
    """The selector dict a Query takes; raises the vocabulary's error for a bad one."""
    if voice is not None and not 1 <= voice <= 4:
        raise vocabulary.error("--voice must be 1-4")
    if limit < 1:
        raise vocabulary.error("--limit must be positive")
    selector: dict[str, Any] = {
        "staves": staves,
        "types": [t.strip() for value in types for t in value.split(",") if t.strip()],
        "where": [parse_where(expression, vocabulary) for expression in where],
        "fields": parse_fields(fields, vocabulary),
        "voice": voice or 0,
        "limit": limit,
    }
    if from_bar is not None:
        selector["fromBar"] = from_bar
    if to_bar is not None:
        selector["toBar"] = to_bar
    return selector
