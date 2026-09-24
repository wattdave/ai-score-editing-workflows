"""Tests for generic Query selector parsing and the property allow-list."""

import re
from pathlib import Path

import pytest

from sibelius_websocket_cli.query import (
    COMMON_PROPS,
    READABLE_PROPS,
    QueryError,
    build_selector,
    parse_fields,
    parse_where,
    resolve_staves,
)

PLUGIN = Path(__file__).parent.parent / "src/sibelius_websocket_cli/manuscript/sibwscli.plg"

STAVES = [
    {"staffNum": 1, "instrumentName": "S.", "fullInstrumentName": "Soprano"},
    {"staffNum": 2, "instrumentName": "T.", "fullInstrumentName": "Tenor"},
]


def _plugin_prop_table() -> tuple[set[str], dict[str, set[str]]]:
    source = PLUGIN.read_text()
    start = source.index('QueryPropTable "() {')
    body = source[start:source.index('}"', start)]
    common_part, types_part = body.split("types = CreateDictionary(", 1)
    common = set(re.findall(r"'(\w+)', True", common_part))
    types: dict[str, set[str]] = {}
    for kind, props in re.findall(r"'(\w+)', CreateDictionary\(([^)]*)\)", types_part):
        types[kind] = set(re.findall(r"'(\w+)', True", props))
    return common, types


def test_python_allow_list_matches_plugin() -> None:
    common, types = _plugin_prop_table()
    assert common == set(COMMON_PROPS)
    assert types == {kind: set(props) for kind, props in READABLE_PROPS.items()}


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("Pitch>=72", {"prop": "Pitch", "op": ">=", "value": 72}),
        ("Hidden = true", {"prop": "Hidden", "op": "=", "value": True}),
        ("Dx!=-32", {"prop": "Dx", "op": "!=", "value": -32}),
        ("Text='la la'", {"prop": "Text", "op": "=", "value": "la la"}),
        ("StyleId=text.staff.expression", {"prop": "StyleId", "op": "=", "value": "text.staff.expression"}),
    ],
)
def test_parse_where(expression, expected) -> None:
    assert parse_where(expression) == expected


@pytest.mark.parametrize("expression", ["Pitch", "Pitch>=", "NoSuchProp=1", "pitch>=72"])
def test_parse_where_rejects(expression) -> None:
    with pytest.raises(QueryError):
        parse_where(expression)


def test_parse_fields_splits_commas_and_rejects_unknown() -> None:
    assert parse_fields(["Dx,Dy", "Text"]) == ["Dx", "Dy", "Text"]
    with pytest.raises(QueryError, match="NoSuchProp"):
        parse_fields(["Dx,NoSuchProp"])
    # Pitch is a filter-only pseudo-property; notes are always returned.
    with pytest.raises(QueryError):
        parse_fields(["Pitch"])


def test_resolve_staves_by_number_and_name() -> None:
    assert resolve_staves(["2", "soprano", "T."], STAVES) == [2, 1, 2]
    with pytest.raises(QueryError):
        resolve_staves(["3"], STAVES)
    with pytest.raises(QueryError):
        resolve_staves(["Alto"], STAVES)


def test_build_selector() -> None:
    selector = build_selector(
        staves=[2], from_bar=12, to_bar=20, types=["NoteRest,Text"], voice=1,
        where=["Pitch>=72"], fields=["Dx"], limit=50,
    )
    assert selector == {
        "staves": [2], "types": ["NoteRest", "Text"],
        "where": [{"prop": "Pitch", "op": ">=", "value": 72}],
        "fields": ["Dx"], "voice": 1, "limit": 50, "fromBar": 12, "toBar": 20,
    }


def test_build_selector_defaults_omit_bars() -> None:
    selector = build_selector(
        staves=[], from_bar=None, to_bar=None, types=[], voice=None, where=[], fields=[],
    )
    assert "fromBar" not in selector and "toBar" not in selector
    assert selector["voice"] == 0 and selector["limit"] == 500


@pytest.mark.parametrize(("voice", "limit"), [(5, 10), (1, 0)])
def test_build_selector_rejects_bad_voice_or_limit(voice, limit) -> None:
    with pytest.raises(QueryError):
        build_selector(
            staves=[], from_bar=None, to_bar=None, types=[], voice=voice,
            where=[], fields=[], limit=limit,
        )
