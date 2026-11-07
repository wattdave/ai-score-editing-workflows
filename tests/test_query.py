"""Tests for generic Query selector parsing and the property allow-list."""

import re
import subprocess
import sys
from pathlib import Path

import pytest

from ai_score_editing.cli_common import DEFAULT_LIMIT
from ai_score_editing.core.errors import QueryError
from ai_score_editing.sibelius.query_props import COMMON_PROPS, READABLE_PROPS, build_selector, parse_fields, parse_where, resolve_staves

PLUGIN = Path(__file__).parent.parent / "src/ai_score_editing/sibelius/manuscript/ScoreBridge.plg"

STAVES = [
    {"staffNum": 1, "instrumentName": "S.", "fullInstrumentName": "Soprano"},
    {"staffNum": 2, "instrumentName": "T.", "fullInstrumentName": "Tenor"},
]


def _plugin_prop_table() -> tuple[set[str], dict[str, set[str]]]:
    source = PLUGIN.read_text()
    start = source.index('QueryPropTable "() {')
    body = source[start:source.index('}"', start)]
    common = set(re.findall(r"common\['(\w+)'\] = True", body))
    types: dict[str, set[str]] = {}
    for block in body.split("props = CreateDictionary();")[1:]:
        kind = re.search(r"types\['(\w+)'\] = props;", block).group(1)
        types[kind] = set(re.findall(r"props\['(\w+)'\] = True", block))
    return common, types


def test_python_allow_list_matches_plugin() -> None:
    common, types = _plugin_prop_table()
    assert common == set(COMMON_PROPS)
    assert types == {kind: set(props) for kind, props in READABLE_PROPS.items()}


def test_generated_plugin_table_is_current() -> None:
    script = Path(__file__).resolve().parent.parent / "scripts" / "dev" / "gen_query_props.py"
    result = subprocess.run([sys.executable, str(script), "--check"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("Pitch>=72", {"prop": "Pitch", "op": ">=", "value": 72}),
        ("Bracketed=true", {"prop": "Bracketed", "op": "=", "value": True}),
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


def test_resolve_staves_system_staff() -> None:
    assert resolve_staves(["0", "System", "1"], STAVES) == [0, 0, 1]


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
    assert selector["voice"] == 0 and selector["limit"] == DEFAULT_LIMIT


@pytest.mark.parametrize(("voice", "limit"), [(5, 10), (1, 0)])
def test_build_selector_rejects_bad_voice_or_limit(voice, limit) -> None:
    with pytest.raises(QueryError):
        build_selector(
            staves=[], from_bar=None, to_bar=None, types=[], voice=voice,
            where=[], fields=[], limit=limit,
        )


def test_container_kinds_take_only_their_own_props() -> None:
    from ai_score_editing.sibelius.query_props import CONTAINER_KINDS

    assert CONTAINER_KINDS == {"Bar", "Staff"}
    assert {"Length", "BreakType"} <= READABLE_PROPS["Bar"]
    assert {"InstrumentName", "StaffNum"} <= READABLE_PROPS["Staff"]
    source = PLUGIN.read_text()
    guard = source[source.index('QueryIsReadable "('):]
    guard = guard[:guard.index('}"')]
    assert "kind != 'Bar' and kind != 'Staff'" in guard
    # Bar and Staff rows are built by their own helper, never by DescribeObject
    assert "QueryContainerRow(staff, 'Staff'" in source
    assert "QueryContainerRow(staff.NthBar(barNum), 'Bar'" in source
    assert "('version', 64)" in source


def test_bar_and_staff_query_selector() -> None:
    selector = build_selector(
        staves=[1], from_bar=2, to_bar=4, types=["Bar,Staff"], voice=None,
        where=["Length>1024"], fields=["Length,BreakType"],
    )
    assert selector["types"] == ["Bar", "Staff"]
    assert selector["fields"] == ["Length", "BreakType"]
    assert selector["where"] == [{"prop": "Length", "op": ">", "value": 1024}]


# ------------------------------------------------------------------ shared engine (core/query.py)

from ai_score_editing.core import query as core  # noqa: E402

VOCAB = core.Vocabulary(properties={"Pitch": int, "Text": str, "Hidden": bool, "Any": None})


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("Pitch>=72", {"prop": "Pitch", "op": ">=", "value": 72}),
        ("Pitch = -3", {"prop": "Pitch", "op": "=", "value": -3}),
        ("Pitch='72'", {"prop": "Pitch", "op": "=", "value": 72}),   # an int field reads a quoted number
        ("Text=true", {"prop": "Text", "op": "=", "value": "true"}),  # a str field keeps text
        ("Text=12", {"prop": "Text", "op": "=", "value": "12"}),
        ("Text='12'", {"prop": "Text", "op": "=", "value": "12"}),
        ("Hidden=TRUE", {"prop": "Hidden", "op": "=", "value": True}),
        ("Any=true", {"prop": "Any", "op": "=", "value": True}),
        ("Any=12", {"prop": "Any", "op": "=", "value": 12}),
        ("Any='12'", {"prop": "Any", "op": "=", "value": "12"}),
        ("Any=\"la la\"", {"prop": "Any", "op": "=", "value": "la la"}),
        ("Any=la", {"prop": "Any", "op": "=", "value": "la"}),
        ("Pitch!=C5", {"prop": "Pitch", "op": "!=", "value": "C5"}),
    ],
)
def test_core_parse_where(expression, expected) -> None:
    assert core.parse_where(expression, VOCAB) == expected


@pytest.mark.parametrize(
    ("expression", "message"),
    [
        ("Pitch", "cannot parse condition 'Pitch'"),
        ("Pitch>=", "missing value in where condition"),
        ("pitch>=1", "unknown property 'pitch' in where condition; readable: Any, Hidden, Pitch, Text"),
    ],
)
def test_core_parse_where_errors(expression, message) -> None:
    with pytest.raises(QueryError, match=message):
        core.parse_where(expression, VOCAB)


def test_core_vocabulary_picks_the_error_and_wording() -> None:
    class Mine(ValueError):
        pass

    vocab = core.Vocabulary(
        properties={"B": None, "A": None}, error=Mine, sort_names=False,
        unparsable="bad {expression!r} ({names})", unknown="no {prop} ({names})",
    )
    with pytest.raises(Mine, match=r"bad 'x' \(B, A\)"):
        core.parse_where("x", vocab)
    with pytest.raises(Mine, match=r"no C \(B, A\)"):
        core.parse_where("C=1", vocab)


def test_core_parse_fields_uses_readable_subset() -> None:
    vocab = core.Vocabulary(properties={"Pitch": int, "Dx": int}, fields=frozenset({"Dx"}))
    assert core.parse_fields(["Dx, Dx"], vocab) == ["Dx", "Dx"]
    with pytest.raises(QueryError, match=r"unknown field\(s\) Pitch"):
        core.parse_fields(["Pitch"], vocab)


@pytest.mark.parametrize(
    ("actual", "op", "value", "result"),
    [
        (3, "=", 3, True), (3, "!=", 3, False), (3, "<", 4, True), (3, ">", 4, False),
        (3, ">=", 3, True), (3, "<=", 2, False),
        ("a", "<", 3, False),   # unorderable: never matches
        ("a", "!=", 3, True),   # different types are not equal
    ],
)
def test_core_compare(actual, op, value, result) -> None:
    assert core.compare(actual, op, value) is result


_ALL = {"=": False, "!=": True, "<": False, ">": False, "<=": False, ">=": False}


@pytest.mark.parametrize("op", ["=", "!=", "<", ">", "<=", ">="])
@pytest.mark.parametrize(
    ("actual", "value", "expected"),
    [
        (3, 3, {"=": True, "!=": False, "<": False, ">": False, "<=": True, ">=": True}),
        (3, 4, {"=": False, "!=": True, "<": True, ">": False, "<=": True, ">=": False}),
        ("a", "b", {"=": False, "!=": True, "<": True, ">": False, "<=": True, ">=": False}),
        ("a", "a", {"=": True, "!=": False, "<": False, ">": False, "<=": True, ">=": True}),
        # mixed types: == False, != True, ordering False and never an exception
        ("a", 3, _ALL),
        (3, "a", _ALL),
        (60, "C5", _ALL),
    ],
)
def test_core_compare_every_operator(actual, value, expected, op) -> None:
    assert core.compare(actual, op, value) is expected[op]


def test_core_holds_chord_not_equal_means_any_note_differs() -> None:
    notes = {"Pitch": [60, 72]}
    ne = {"prop": "Pitch", "op": "!=", "value": 60}
    assert core.holds({}, ne, notes)                                  # 72 differs
    assert not core.holds({}, ne, {"Pitch": [60]})
    assert core.holds({}, {**ne, "value": "C5"}, notes)               # mixed types: all differ
    assert not core.holds({}, {**ne, "op": "=", "value": "C5"}, notes)


def test_core_holds_single_missing_and_multi() -> None:
    cond = {"prop": "Pitch", "op": "=", "value": 60}
    assert core.holds({"Pitch": 60}, cond)
    assert not core.holds({"Pitch": 61}, cond)
    assert not core.holds({}, cond)                                  # no value matches nothing ...
    assert core.holds({}, {**cond, "op": "!="})                      # ... except "not equal"
    assert core.holds({"Pitch": None}, {**cond, "op": "!="})
    assert core.holds({}, cond, {"Pitch": [48, 60]})                 # any note
    assert not core.holds({}, cond, {"Pitch": []})                   # no notes: never, not even !=
    assert not core.holds({}, {**cond, "op": "!="}, {"Pitch": []})
    assert core.holds({"Pitch": 1}, cond, {"Other": [60]}) is False  # multi covers only its names


NAMED = [
    {"n": 1, "short": "Pno.", "long": "Piano"},
    {"n": 2, "short": "Pno.", "long": "Piano"},
    {"n": 3, "short": "Vn.", "long": "Violin"},
]


def test_core_resolve_staves() -> None:
    def resolve(requested):
        return core.resolve_staves(requested, NAMED, number_key="n", name_keys=("short", "long"))

    assert resolve(["PIANO", "3"]) == [1, 2, 3]
    assert resolve(["vn.", " violin "]) == [3, 3]
    assert resolve(["0", "System", "SYSTEM"]) == [0, 0, 0]
    assert resolve([2]) == [2]
    assert isinstance(resolve(["1"]), list)
    with pytest.raises(QueryError, match=r"^no staff 4; staves are 1-3$"):
        resolve(["4"])
    with pytest.raises(QueryError, match=r"^no staff named 'Oboe'; names: Piano, Pno\., Violin, Vn\.$"):
        resolve(["Oboe"])


def test_core_resolve_staves_raises_the_given_error() -> None:
    class Mine(ValueError):
        pass

    with pytest.raises(Mine):
        core.resolve_staves(["x"], NAMED, number_key="n", name_keys=("short",), error=Mine)


def test_core_build_selector_default_limit_is_the_shared_one() -> None:
    selector = core.build_selector(
        staves=[], from_bar=None, to_bar=None, types=["A, B"], voice=None, where=["Pitch>1"], fields=[],
        vocabulary=VOCAB,
    )
    assert selector["limit"] == DEFAULT_LIMIT == core.DEFAULT_LIMIT
    assert selector["types"] == ["A", "B"] and selector["where"][0]["value"] == 1
