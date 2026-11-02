"""Characterization of where-clause and staff-name handling on all three back ends.

Written against the code before the shared query engine (core/query.py), so
the refactor shows exactly which behaviour changed: any edit to an expected
value here is an intentional behaviour change.
"""

from __future__ import annotations

from typing import Any

import pytest

from ai_score_editing import query as sibelius_query
from ai_score_editing.dorico import score as dorico
from ai_score_editing.dorico.bridge import BarMap
from ai_score_editing.musescore import score as musescore
from ai_score_editing.musescore import service as musescore_service

# ------------------------------------------------------------------ Sibelius

SIBELIUS_STAVES = [
    {"staffNum": 1, "instrumentName": "S.", "fullInstrumentName": "Soprano"},
    {"staffNum": 2, "instrumentName": "T.", "fullInstrumentName": "Tenor"},
]


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("Pitch>=72", {"prop": "Pitch", "op": ">=", "value": 72}),
        ("Dx != -32", {"prop": "Dx", "op": "!=", "value": -32}),
        ("Hidden=TRUE", {"prop": "Hidden", "op": "=", "value": True}),
        ("Text=true", {"prop": "Text", "op": "=", "value": True}),
        ("Text='3'", {"prop": "Text", "op": "=", "value": "3"}),
        ("Text=\"la la\"", {"prop": "Text", "op": "=", "value": "la la"}),
        ("Text=la", {"prop": "Text", "op": "=", "value": "la"}),
    ],
)
def test_sibelius_where_values(expression, expected) -> None:
    assert sibelius_query.parse_where(expression) == expected


@pytest.mark.parametrize(
    ("expression", "message"),
    [
        ("Pitch", r"cannot parse condition 'Pitch'; expected e\.g\. 'Pitch>=72'"),
        ("Pitch>=", "missing value in where condition"),
        ("pitch>=72", r"unknown property 'pitch' in where condition; readable: AllowCautionary,"),
        ("NoSuchProp=1", r"unknown property 'NoSuchProp' in where condition; readable: "),
    ],
)
def test_sibelius_where_errors(expression, message) -> None:
    with pytest.raises(sibelius_query.QueryError, match=message):
        sibelius_query.parse_where(expression)


def test_sibelius_staff_resolution() -> None:
    resolve = sibelius_query.resolve_staves
    assert resolve(["2", "soprano", "T."], SIBELIUS_STAVES) == [2, 1, 2]
    assert resolve(["0", "System"], SIBELIUS_STAVES) == [0, 0]
    with pytest.raises(sibelius_query.QueryError, match="^staff 3 does not exist$"):
        resolve(["3"], SIBELIUS_STAVES)
    with pytest.raises(sibelius_query.QueryError, match="^no staff named 'Alto'$"):
        resolve(["Alto"], SIBELIUS_STAVES)


def test_sibelius_fields() -> None:
    assert sibelius_query.parse_fields(["Dx,Dy", "Text"]) == ["Dx", "Dy", "Text"]
    with pytest.raises(sibelius_query.QueryError, match="^unknown field.s. Aa, Zed$"):
        sibelius_query.parse_fields(["Dx,Zed,Aa"])
    with pytest.raises(sibelius_query.QueryError, match="^unknown field.s. Pitch$"):
        sibelius_query.parse_fields(["Pitch"])


# ------------------------------------------------------------------ Dorico

DORICO_STAVES = [{"staff": 1, "name": "Piano"}, {"staff": 2, "name": "Piano"}]
DORICO_EVENTS = [
    {"id": 3, "type": "NoteEvent", "stream": 2, "staff": 1, "voice": 1, "position": 0, "duration": 256,
     "pitch": 72, "name": "C5"},
    {"id": 4, "type": "NoteEvent", "stream": 2, "staff": 1, "voice": 1, "position": 256, "duration": 256,
     "pitch": 64, "name": "E4"},
    {"id": 5, "type": "TextEvent", "stream": 2, "staff": 1, "voice": 1, "position": 512, "duration": 0,
     "text": "true"},
]


def _dorico_ids(*where: str, **kw: Any) -> list[int]:
    located = dorico.locate_events(DORICO_EVENTS, BarMap([(0, 1024)]))
    return [o["id"] for o in dorico.query(located, where=list(where), **kw)["objects"]]


@pytest.mark.parametrize(
    ("where", "ids"),
    [
        (["Pitch>=70"], [3]),
        (["Pitch<70"], [4]),
        (["Pitch!=72"], [4, 5]),  # an event without a pitch is not equal to anything
        (["Pitch>=60", "Name=E4"], [4]),
        (["Name='E4'"], [4]),
        (["Name=\"E4\""], [4]),
        (["Name=E4"], [4]),
        (["Id=5"], [5]),
        (["Voice=1", "Position>=256"], [4, 5]),
        (["Type=NoteEvent"], [3, 4]),
        (["Type=NoteRest"], [3, 4]),  # type aliases
        (["Type!=NoteRest"], [5]),
        (["Type=Text"], [5]),
        (["Type>NoteRest"], []),
        (["Text=true"], [5]),  # Dorico text stays a string even when it reads "true"
        (["Text=1"], []),
        (["Text!=x"], [3, 4, 5]),
        (["Pitch=C5"], []),
    ],
)
def test_dorico_where(where, ids) -> None:
    assert _dorico_ids(*where) == ids


@pytest.mark.parametrize("where", ["Pitch", "Nope=1", "pitch>=1", "Pitch="])
def test_dorico_where_errors(where) -> None:
    fields = "Pitch, Position, FlowPosition, Duration, Voice, Type, Text, Name, Id, Bar, Staff"
    with pytest.raises(dorico.DoricoBatchError) as info:
        _dorico_ids(where)
    assert str(info.value) == f"bad condition {where!r}; use Field op value with fields {fields}"


def test_dorico_staff_resolution() -> None:
    resolve = dorico.resolve_staves
    assert resolve(["PIANO"], DORICO_STAVES) == {1, 2}
    assert resolve(["2", "system"], DORICO_STAVES) == {0, 2}
    assert resolve(["0"], DORICO_STAVES) == {0}
    with pytest.raises(dorico.DoricoBatchError, match="^no staff 3; staves are 1-2$"):
        resolve(["3"], DORICO_STAVES)
    with pytest.raises(dorico.DoricoBatchError, match="^no staff named 'Flute'; names: Piano$"):
        resolve(["Flute"], DORICO_STAVES)


# ------------------------------------------------------------------ MuseScore

MUSESCORE_STAVES = [
    {"staff": 1, "partName": "Clarinet", "shortName": "Cl."},
    {"staff": 2, "partName": "Piano", "shortName": "Pno."},
]


def _selector(*where: str, fields: list[str] | None = None) -> dict[str, Any]:
    return musescore_service.build_selector(
        staves=[], from_bar=None, to_bar=None, types=[], voice=None, where=list(where), fields=fields or [],
    )


def test_musescore_staff_resolution() -> None:
    resolve = musescore_service.resolve_staves
    assert resolve(["PIANO", "cl."], MUSESCORE_STAVES) == [2, 1]
    assert resolve(["0", "System"], MUSESCORE_STAVES) == [0, 0]
    with pytest.raises(musescore.MuseScoreBatchError, match="^no staff 3; staves are 1-2$"):
        resolve(["3"], MUSESCORE_STAVES)
    with pytest.raises(musescore.MuseScoreBatchError, match="^no staff named 'Oboe'; parts: Clarinet, Piano$"):
        resolve(["Oboe"], MUSESCORE_STAVES)


def test_musescore_where_names_are_checked_against_sibelius_today() -> None:
    assert _selector("Pitch>=60")["where"] == [{"prop": "Pitch", "op": ">=", "value": 60}]
    assert _selector("VoiceNumber=1")["where"] == [{"prop": "VoiceNumber", "op": "=", "value": 1}]
    # Sibelius-only names are accepted although MuseScore reports no such value.
    assert _selector("InitialFontName=x")["where"][0]["prop"] == "InitialFontName"
    with pytest.raises(sibelius_query.QueryError, match="unknown property 'Nope'"):
        _selector("Nope=1")


def _chord(pitches: list[int], position: int = 0) -> dict[str, Any]:
    return {
        "type": "NoteRest", "msType": "Chord", "staff": 1, "bar": 1, "index": 0, "position": position,
        "hidden": False, "voice": 1, "duration": 256, "rest": False, "cueSize": False, "beam": 0,
        "stemDirection": 0,
        "notes": [{"pitch": p, "bracketed": False} for p in pitches],
    }


@pytest.mark.parametrize(
    ("where", "count"),
    [
        ({"prop": "Pitch", "op": ">=", "value": 70}, 1),     # any note of the chord
        ({"prop": "Pitch", "op": "=", "value": 60}, 2),
        ({"prop": "Pitch", "op": "!=", "value": 60}, 1),     # any note differing
        ({"prop": "Bracketed", "op": "=", "value": False}, 2),
        ({"prop": "NoteCount", "op": ">", "value": 1}, 1),
        ({"prop": "Type", "op": "=", "value": "NoteRest"}, 2),
        ({"prop": "Text", "op": "=", "value": "x"}, 0),      # no such value: matches nothing
        ({"prop": "Text", "op": "!=", "value": "x"}, 2),     # ... except "not equal"
        ({"prop": "Position", "op": "<", "value": "a"}, 0),  # incomparable types never match
    ],
)
def test_musescore_where_conditions(where, count) -> None:
    objects = [_chord([60, 72]), _chord([60])]
    selector = {"staves": [1], "types": [], "where": [where], "fields": [], "voice": 0, "limit": 10}
    assert musescore.query(objects, selector)["count"] == count


def test_musescore_set_validated_against_sibelius_table() -> None:
    def prepare(op: dict[str, Any]) -> None:
        musescore.prepare_batch([op], [], MUSESCORE_STAVES, 480, {})

    base = {"op": "set", "staff": 1, "bar": 1, "index": 0}
    with pytest.raises(musescore.MuseScoreBatchError, match=r"'Nope' is not writable; writable: .*Beam.*Text"):
        prepare({**base, "prop": "Nope", "value": 1})
    with pytest.raises(musescore.MuseScoreBatchError, match=r"Dx"):
        prepare({**base, "prop": "Dx", "value": "wide"})
