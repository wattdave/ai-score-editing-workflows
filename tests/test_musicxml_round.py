"""Tests for arranging a single-part round as staggered playback voices."""

import xml.etree.ElementTree as ET

import pytest

from ai_score_editing.musicxml_round import RoundError, RoundOptions, build_round


def _note(step: str, duration: int, note_type: str, lyric: str | None = None) -> str:
    text = f"<lyric><text>{lyric}</text></lyric>" if lyric else ""
    return (
        f"<note><pitch><step>{step}</step><octave>4</octave></pitch>"
        f"<duration>{duration}</duration><voice>1</voice><type>{note_type}</type>{text}</note>"
    )


def _mark(number: int) -> str:
    return f"<direction><direction-type><words>{number}.</words></direction-type></direction>"


def _round(beats: int = 2, beat_type: int = 2, marks: bool = True, parts: int = 1) -> ET.Element:
    """A 4-bar round, entries every bar; the last bar ends with a pickup."""
    bar = 4 * beats // beat_type
    half = bar // 2
    measures = []
    for n, step in enumerate("CDEF", start=1):
        body = (_mark(n) if marks else "") + (
            _note("G", half, "half", "end") + _note("C", bar - half, "half", "O")
            if n == 4 else _note(step, bar, "whole", step.lower())
        )
        attributes = (
            f"<attributes><divisions>1</divisions><key><fifths>0</fifths></key>"
            f"<time><beats>{beats}</beats><beat-type>{beat_type}</beat-type></time>"
            f"<clef><sign>G</sign><line>2</line></clef></attributes>"
            if n == 1 else ""
        )
        measures.append(f'<measure number="{n}">{attributes}{body}</measure>')
    part_ids = [f"P{i + 1}" for i in range(parts)]
    return ET.fromstring(
        '<score-partwise version="3.0"><work><work-title>Song</work-title></work><part-list>'
        + "".join(f'<score-part id="{p}"><part-name>V</part-name></score-part>' for p in part_ids)
        + "</part-list>"
        + "".join(f'<part id="{p}">{"".join(measures)}</part>' for p in part_ids)
        + "</score-partwise>"
    )


def _lyrics(part: ET.Element) -> list[str]:
    return [" ".join(n.findtext("lyric/text") or "" for n in m.findall("note")).strip() or "-"
            for m in part.findall("measure")]


def test_infers_layout_from_entry_marks_and_staggers_voices() -> None:
    result = build_round(_round(), RoundOptions())

    assert result.as_dict() == {"voices": 4, "gap": 1, "passes": 2, "songBars": 4, "totalBars": 11}
    parts = result.root.findall("part")
    assert _lyrics(parts[0]) == ["c", "d", "e", "end O", "c", "d", "e", "end", "-", "-", "-"]
    assert _lyrics(parts[3]) == ["-", "-", "-", "c", "d", "e", "end O", "c", "d", "e", "end"]
    assert result.root.findtext("work/work-title") == "Song (round)"


def test_final_bar_holds_first_note_and_only_last_voice_gets_fermata() -> None:
    parts = build_round(_round(), RoundOptions()).root.findall("part")

    first_end = parts[0].findall("measure")[7].findall("note")
    assert [(n.findtext("duration"), n.findtext("type")) for n in first_end] == [("4", "whole")]
    assert parts[0].find(".//fermata") is None
    last = parts[3].findall("measure")[-1]
    assert last.find("note/notations/fermata") is not None
    assert last.find("barline/bar-style").text == "light-heavy"


def test_strips_entry_marks_and_rests_fill_whole_bars() -> None:
    parts = build_round(_round(), RoundOptions()).root.findall("part")

    assert not [w for w in parts[0].iter("words")]
    rest = parts[1].findall("measure")[0].find("note")
    assert rest.find("rest").get("measure") == "yes"
    assert rest.findtext("duration") == "4"


def test_explicit_layout_overrides_marks() -> None:
    result = build_round(_round(marks=False), RoundOptions(voices=2, gap=2, passes=1))

    assert result.as_dict()["totalBars"] == 6
    assert _lyrics(result.root.findall("part")[1]) == ["-", "-", "c", "d", "e", "end"]


def test_holds_with_a_dotted_value_in_triple_time() -> None:
    parts = build_round(_round(beats=3, beat_type=4), RoundOptions()).root.findall("part")

    held = parts[0].findall("measure")[7].find("note")
    assert (held.findtext("duration"), held.findtext("type"), held.find("dot") is not None) == ("3", "half", True)


def test_assigns_channels_skipping_drums_and_spreads_pan() -> None:
    root = build_round(_round(), RoundOptions(voices=11, gap=1, passes=1)).root

    channels = [int(c.text) for c in root.iter("midi-channel")]
    assert channels == [1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12]
    pans = [int(p.text) for p in root.iter("pan")]
    assert (pans[0], pans[-1]) == (-45, 45)


@pytest.mark.parametrize(
    "source, options, message",
    [
        (_round(parts=2), RoundOptions(), "single-part"),
        (_round(marks=False), RoundOptions(), "entry marks"),
        (_round(marks=False), RoundOptions(voices=2), "infer --gap"),
        (_round(), RoundOptions(passes=0), "passes"),
        (_round(), RoundOptions(voices=16, gap=1), "voices must be"),
    ],
)
def test_rejects_unusable_sources_and_options(source, options, message) -> None:
    with pytest.raises(RoundError, match=message):
        build_round(source, options)
