"""Tests for extra_staves.py (playback-divisi-split) and check_musicxml.py (omr-score-repair)."""

from __future__ import annotations

import copy
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from helpers import load_script

SKILLS = Path(__file__).resolve().parent.parent / ".claude" / "skills"
extra = load_script(SKILLS / "playback-divisi-split" / "scripts" / "extra_staves.py")
check_xml = load_script(SKILLS / "omr-score-repair" / "scripts" / "check_musicxml.py")


def _note(step: str | None, octave: int = 4, chord: bool = False, lyric: str | None = None) -> str:
    body = "<rest/>" if step is None else f"<pitch><step>{step}</step><octave>{octave}</octave></pitch>"
    text = f"<lyric><syllabic>single</syllabic><text>{lyric}</text></lyric>" if lyric else ""
    return f"<note>{'<chord/>' if chord else ''}{body}<duration>4</duration>{text}</note>"


def _score(*bars: str) -> ET.Element:
    measures = "".join(
        f'<measure number="{i}">'
        + ("<attributes><divisions>4</divisions><time><beats>4</beats><beat-type>4</beat-type></time>"
           "</attributes>" if i == 1 else "")
        + bar + "</measure>" for i, bar in enumerate(bars, 1))
    return ET.fromstring(
        '<score-partwise><work><work-title>T</work-title></work><part-list>'
        '<score-part id="P1"><part-name>Alto</part-name><part-abbreviation>A.</part-abbreviation>'
        f'</score-part></part-list><part id="P1">{measures}</part></score-partwise>')


def _pitches(root: ET.Element, pid: str) -> list[list[str]]:
    return [[n.findtext("pitch/step") or "rest" for n in m.findall("note")]
            for m in root.find(f"part[@id='{pid}']").findall("measure")]


def test_div_staff_duplicates_single_notes_and_takes_the_lower_chord_note() -> None:
    root = _score(_note("C"), _note("E", chord=False, lyric="la") + _note("C", chord=True))
    assert extra.build(root, " div", " d.") == 1
    assert _pitches(root, "P1") == [["C"], ["E"]]
    assert _pitches(root, "P1d") == [["C"], ["C"]]
    lyrics = [n.findtext("lyric/text") for n in root.find("part[@id='P1d']/measure[2]").findall("note")]
    assert lyrics == ["la"]
    assert [s.findtext("part-name") for s in root.findall("part-list/score-part")] == ["Alto", "Alto div"]


def test_check_reports_nothing_missing_for_a_clean_split() -> None:
    source = _score(_note("C"), _note("E") + _note("C", chord=True))
    split = copy.deepcopy(source)
    extra.build(split, " div", " d.")
    assert extra.check(source, split) == []


def test_check_finds_a_dropped_note() -> None:
    source = _score(_note("E") + _note("C", chord=True))
    split = copy.deepcopy(source)
    extra.build(split, " div", " d.")
    split.find("part[@id='P1d']/measure/note/pitch/step").text = "D"
    assert extra.check(source, split)


def test_three_note_chord_is_refused() -> None:
    root = _score(_note("E") + _note("C", chord=True) + _note("G", chord=True))
    with pytest.raises(SystemExit):
        extra.build(root, " div", " d.")


def test_checker_accepts_a_clean_score() -> None:
    bar = _note("C") + _note("D") + _note("E") + _note("F")
    assert check_xml.check(_score(bar, bar, bar), True) == []


def test_checker_flags_transpose_before_clef() -> None:
    root = _score(_note("C") * 4)
    attributes = root.find(".//attributes")
    ET.SubElement(attributes, "transpose").append(ET.Element("octave-change"))
    ET.SubElement(attributes, "clef")
    assert any("clef" in p for p in check_xml.check(root, False))


def test_checker_flags_a_doubled_rest() -> None:
    root = _score(_note(None) + _note("C") * 3)
    root.find(".//note").append(ET.Element("rest"))
    assert any("rest" in p for p in check_xml.check(root, False))


def test_checker_flags_a_short_bar() -> None:
    problems = check_xml.check(_score(_note("C") * 4, _note("C") * 3), True)
    assert any("bar 2" in p and "lasts 12" in p for p in problems)


def test_checker_flags_parts_with_unequal_bars() -> None:
    root = _score(_note("C") * 4, _note("C") * 4)
    other = _score(_note("C") * 4).find("part")
    other.set("id", "P2")
    root.append(other)
    assert any("differ" in p for p in check_xml.check(root, False))
