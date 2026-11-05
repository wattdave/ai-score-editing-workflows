"""The ficta lister and its address resolver (core/ficta.py)."""

import pytest

from ai_score_editing.core.errors import BatchError
from ai_score_editing.core.ficta import list_ficta, resolve

XML = """<score-partwise version="3.1">
<part-list><score-part id="P1"><part-name>Top</part-name></score-part>
<score-part id="P2"><part-name>Pno</part-name></score-part></part-list>
<part id="P1">
<measure number="0"><attributes><divisions>2</divisions></attributes>
<note><pitch><step>C</step><octave>5</octave></pitch><duration>2</duration></note></measure>
<measure number="1">
<note><pitch><step>E</step><alter>-1</alter><octave>4</octave></pitch><duration>2</duration>
<notations><accidental-mark placement="above">flat</accidental-mark></notations></note>
<note><rest/><duration>2</duration></note>
<note><pitch><step>B</step><octave>4</octave></pitch><duration>4</duration></note>
<note><chord/><pitch><step>F</step><alter>1</alter><octave>5</octave></pitch><duration>4</duration>
<notations><accidental-mark placement="above">sharp</accidental-mark></notations></note>
<note><pitch><step>B</step><octave>4</octave></pitch><duration>4</duration>
<notations><accidental-mark placement="below">flat</accidental-mark></notations></note>
</measure></part>
<part id="P2">
<measure number="0"><attributes><divisions>2</divisions><staves>2</staves></attributes>
<note><pitch><step>C</step><octave>3</octave></pitch><duration>2</duration><staff>2</staff></note>
</measure>
<measure number="1">
<note><pitch><step>B</step><octave>3</octave></pitch><duration>8</duration><staff>2</staff>
<notations><accidental-mark placement="above">natural</accidental-mark></notations></note>
</measure></part></score-partwise>"""


def test_lists_only_above_marks_with_addresses() -> None:
    rows = list_ficta(XML)
    assert [(r["staff"], r["bar"], r["barNumber"], r["position"], r["noteIndex"], r["pitch"], r["accidental"])
            for r in rows] == [
        (1, 2, "1", 0, 0, 63, "flat"),
        (1, 2, "1", 512, 2, 78, "sharp"),  # a chord counts once, on the chord's start
        (3, 2, "1", 0, 0, 59, "natural"),  # part 2's second staff is staff 3 of the score
    ]


def test_resolve_matches_by_staff_bar_position_and_pitch() -> None:
    rows = list_ficta(XML)
    objects = [
        {"staff": 1, "bar": 2, "type": "NoteRest", "position": 0, "index": 3, "notes": [{"pitch": 63}]},
        {"staff": 1, "bar": 2, "type": "NoteRest", "position": 512, "index": 6, "notes": [{"pitch": 71}, {"pitch": 78}]},
        {"staff": 3, "bar": 2, "type": "NoteRest", "position": 0, "index": 1, "notes": [{"pitch": 59}]},
    ]
    ops = resolve(rows, objects, "sibelius")
    assert ops[0] == {"op": "ficta", "staff": 1, "bar": 2, "index": 3, "type": "NoteRest", "position": 0,
                      "accidental": "flat"}
    assert ops[1]["index"] == 6 and ops[2]["staff"] == 3


def test_resolve_dorico_uses_ids_and_reports_unplaced() -> None:
    rows = list_ficta(XML)[:1]
    events = [{"id": 77, "staff": 1, "bar": 2, "position": 0, "pitch": 63, "type": "NoteEvent"}]
    assert resolve(rows, events, "dorico") == [{"op": "ficta", "id": 77, "accidental": "flat"}]
    with pytest.raises(BatchError, match="0 matching"):
        resolve(rows, [], "dorico")
    with pytest.raises(BatchError, match="unknown editor"):
        resolve(rows, events, "finale")
