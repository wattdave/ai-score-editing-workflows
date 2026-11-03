"""Tests for the playback-divisi-split skill's MusicXML splitter."""

from __future__ import annotations

from pathlib import Path
import xml.etree.ElementTree as ET

import pytest
from helpers import load_script

SCRIPT_PATH = (Path(__file__).resolve().parent.parent
               / ".claude" / "skills" / "playback-divisi-split" / "scripts" / "playback_split.py")
playback_split = load_script(SCRIPT_PATH)


def _note(pitch: str | None, duration: int, chord: bool = False) -> str:
    if pitch is None:
        return f"<note><rest/><duration>{duration}</duration></note>"
    step, octave = pitch[0], pitch[-1]
    alter = "<alter>1</alter>" if "#" in pitch else ""
    return (f"<note>{'<chord/>' if chord else ''}<pitch><step>{step}</step>{alter}"
            f"<octave>{octave}</octave></pitch><duration>{duration}</duration></note>")


def _score(*parts: list[str]) -> ET.Element:
    """Build a score; each part is a list of measure bodies (strings of <note>s)."""
    body = "".join(
        f'<part id="P{i}">'
        + "".join(f'<measure number="{n}">'
                  + ("<attributes><divisions>1</divisions></attributes>" if n == 1 else "")
                  + m + "</measure>" for n, m in enumerate(measures, 1))
        + "</part>"
        for i, measures in enumerate(parts, 1)
    )
    return ET.fromstring(f"<score-partwise><work><work-title>T</work-title></work>{body}</score-partwise>")


def _pitches(root: ET.Element, part: str) -> list[list[str]]:
    out = []
    for measure in root.find(f"part[@id='{part}']").findall("measure"):
        bar = []
        for n in measure.findall("note"):
            bar.append("r" if n.find("rest") is not None else playback_split.name(n))
        out.append(bar)
    return out


def test_unison_and_melody_chord_split() -> None:
    melody = [_note("G3", 2), _note("D3", 1) + _note("A3", 1, True) + _note("D4", 1, True) + _note("C4", 1)]
    rest = [_note(None, 2), _note(None, 2)]
    root = _score(melody, rest, rest)

    log = playback_split.split(root, "P1", unison_until=1, double_rests=True)

    assert _pitches(root, "P1") == [["G3"], ["D4", "C4"]]
    assert _pitches(root, "P2") == [["G3"], ["A3", "C4"]]
    assert _pitches(root, "P3") == [["G3"], ["D3", "C4"]]
    assert not root.findall(".//chord")
    assert log == ["bar 2 @0: melody chord D4/A3/D3 -> P1=D4, P2=A3, P3=D3"]


def test_two_note_melody_chord_gives_middle_voice_the_melody() -> None:
    melody = [_note("B3", 2) + _note("G3", 2, True)]
    rest = [_note(None, 2)]
    root = _score(melody, rest, rest)

    playback_split.split(root, "P1", unison_until=0, double_rests=True)

    assert [_pitches(root, p)[0] for p in ("P1", "P2", "P3")] == [["B3"], ["B3"], ["G3"]]


def test_split_rests_are_merged_before_doubling_the_melody() -> None:
    melody = [_note("G3", 3)]
    root = _score(melody, [_note(None, 2) + _note(None, 1)])

    playback_split.split(root, "P1", unison_until=0, double_rests=True)

    assert _pitches(root, "P2") == [["G3"]]


def test_no_double_rests_leaves_rests() -> None:
    root = _score([_note("G3", 2)], [_note(None, 2)])

    playback_split.split(root, "P1", unison_until=0, double_rests=False)

    assert _pitches(root, "P2") == [["r"]]


def test_inner_part_chord_extra_goes_to_non_melody_neighbour() -> None:
    melody = [_note("D4", 2)]
    tenor2 = [_note("F#3", 2) + _note("A3", 2, True)]
    bass = [_note("D3", 2)]
    root = _score(melody, tenor2, bass)

    log = playback_split.split(root, "P1", unison_until=0, double_rests=True)

    assert _pitches(root, "P1") == [["D4"]]  # melody untouched
    assert _pitches(root, "P2") == [["A3"]]
    assert _pitches(root, "P3") == [["F#3"]]
    assert "F#3 -> P3 (replacing D3)" in log[0]


def test_inner_part_chord_note_already_sounding_is_dropped() -> None:
    melody = [_note("G3", 1) + _note("G3", 1)]
    tenor2 = [_note("B3", 1) + _note("G3", 1) + _note("B3", 1, True)]
    bass = [_note("G2", 2)]
    root = _score(melody, tenor2, bass)

    log = playback_split.split(root, "P1", unison_until=0, double_rests=True)

    assert _pitches(root, "P2") == [["B3", "B3"]]
    assert "G3 already sounds, dropped" in log[0]


def test_multiple_voices_per_staff_are_refused() -> None:
    root = _score([_note("G3", 2) + "<backup><duration>2</duration></backup>" + _note("B3", 2)])

    with pytest.raises(SystemExit, match="multiple voices"):
        playback_split.split(root, "P1", unison_until=0, double_rests=True)
