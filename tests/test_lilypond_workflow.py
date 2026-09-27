"""Tests for the lilypond-to-sibelius skill scripts."""

from __future__ import annotations

import importlib.util
import struct
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / ".claude" / "skills" / "lilypond-to-sibelius" / "scripts"


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclasses look their module up here
    spec.loader.exec_module(module)
    return module


prepare = load("lilypond_prepare")
rebar = load("rebar")
add_lyrics = load("add_lyrics")
midi_info = load("midi_info")


def part_xml(notes: str, divisions: int = 1) -> ET.Element:
    """A one-part score whose first measure holds `notes` (as <note> XML)."""
    return ET.fromstring(
        "<score-partwise><part-list><score-part id='P1'><part-name>S</part-name></score-part></part-list>"
        f"<part id='P1'><measure number='1'><attributes><divisions>{divisions}</divisions>"
        "<time><beats>4</beats><beat-type>4</beat-type></time><clef><sign>G</sign><line>2</line></clef>"
        f"</attributes>{notes}</measure></part></score-partwise>"
    )


def note(step: str, duration: int, tie: str | None = None) -> str:
    tie_xml = f"<tie type='{tie}'/>" if tie else ""
    return f"<note><pitch><step>{step}</step><octave>4</octave></pitch><duration>{duration}</duration>{tie_xml}</note>"


def rest(duration: int) -> str:
    return f"<note><rest/><duration>{duration}</duration></note>"


# --- lilypond_prepare ---------------------------------------------------------

def test_clean_strips_engraving_code_and_bar_checks() -> None:
    body = r"""{
      \incipitStart \clef "petrucci-c1" d\breve \incipitEnd
      \set Staff.instrumentName = #"[Cantus]"
      \set suggestAccidentals = ##t
      \once \override Staff.TimeSignature #'style = #'mensural
      s1*0 _\markup "Fortuna" \colorBr f2. \colorBrBegin g4 \colorBrEnd | \[ e1 d \] | R | f\longa*1/2 \bar "|."
    }"""
    out = prepare.clean(body, drop=["colorBrBegin", "colorBrEnd", "colorBr"], replace={})
    for gone in ("incipit", "petrucci", "instrumentName", "suggest", "override", "markup",
                 "colorBr", "\\[", "\\]", "|", "\\longa", "\\bar"):
        assert gone not in out
    assert "f2." in out and "g4" in out and "\\breve" in out
    assert " r " in f" {out} "


def test_replace_substitutes_a_macro() -> None:
    out = prepare.clean(r"{ \fourTwoCutTime f\breve }", drop=[], replace={"fourTwoCutTime": r"\time 4/2"})
    assert r"\time 4/2" in out and "fourTwoCutTime" not in out


def test_find_block_keeps_relative_prefix() -> None:
    prefix, body = prepare.find_block("x = 1\ncantoI = \\relative c' { c4 { d } }\n", "cantoI")
    assert prefix == "\\relative c'"
    assert body == "{ c4 { d } }"


# --- rebar ----------------------------------------------------------------------

def test_rebar_splits_a_note_across_the_barline_with_a_tie() -> None:
    # In 2/2 (16 sixteenths a bar): half, whole, half -> [half, half~] [half, half]
    root = part_xml(note("C", 2) + note("D", 4) + note("E", 2))
    part = root.find("part")
    assert part is not None
    assert rebar.rebar_part(part, 2, 2, "treble8") == 2
    measures = part.findall("measure")
    lengths = [sum(int(n.findtext("duration") or 0) for n in m.findall("note")) for m in measures]
    assert lengths == [16, 16]
    d_notes = [n for n in part.iter("note") if n.findtext("pitch/step") == "D"]
    assert [tuple(t.get("type") for t in n.findall("tie")) for n in d_notes] == [("start",), ("stop",)]
    clef = measures[0].find("attributes/clef")
    assert clef is not None and clef.findtext("clef-octave-change") == "-1"


def test_rebar_merges_existing_ties_before_rebarring() -> None:
    # Two tied quarters are one half note, not two attacks.
    root = part_xml(note("C", 1, "start") + note("C", 1, "stop") + rest(2), divisions=1)
    part = root.find("part")
    assert part is not None
    rebar.rebar_part(part, 4, 4, None)
    sounding = [n for n in part.iter("note") if n.find("pitch") is not None]
    assert len(sounding) == 1 and sounding[0].findtext("type") == "half"


def test_rebar_splits_uneven_values_into_notatable_pieces() -> None:
    assert rebar.split_units(28) == [24, 4]  # dotted whole + quarter
    assert rebar.split_units(5) == [4, 1]


def test_rebar_rejects_chords() -> None:
    root = part_xml(note("C", 4) + "<note><chord/><pitch><step>E</step><octave>4</octave></pitch>"
                    "<duration>4</duration></note>")
    part = root.find("part")
    assert part is not None
    with pytest.raises(SystemExit):
        rebar.rebar_part(part, 4, 4, None)


# --- add_lyrics -------------------------------------------------------------------

def test_slurred_notes_marks_notes_after_the_first_in_a_slur() -> None:
    assert add_lyrics.slurred_notes(r"\clef bass \key g \minor \relative c' { c4( d) e r f\breve }") == [
        False, True, False, False]


def test_syllables_reads_hyphens_extenders_and_skips() -> None:
    syls = add_lyrics.syllables(r"\skip \breve Du tout plon -- giet __ _ au")
    assert [s["text"] for s in syls] == ["Du", "tout", "plon", "giet", "_", "au"]
    assert syls[2]["hyphen"] and syls[3]["extend"]


def test_attach_sets_syllabic_and_skips_ties_and_melismas() -> None:
    root = part_xml(note("C", 1) + note("D", 1, "start") + note("D", 1, "stop") + note("E", 1) + note("F", 1))
    part = root.find("part")
    assert part is not None
    syls = add_lyrics.syllables("plon -- giet _ au")
    # Source notes: C, D, E, F (the tied D is one note); no slurs.
    assert add_lyrics.attach(part, [False, False, False, False], syls) == 3
    lyrics = [(n.findtext("pitch/step"), n.findtext("lyric/text"), n.findtext("lyric/syllabic"))
              for n in part.iter("note") if n.find("lyric") is not None]
    assert lyrics == [("C", "plon", "begin"), ("D", "giet", "end"), ("F", "au", "single")]


def test_attach_refuses_a_mismatched_count() -> None:
    root = part_xml(note("C", 1) + note("D", 1))
    part = root.find("part")
    assert part is not None
    with pytest.raises(SystemExit):
        add_lyrics.attach(part, [False, False], add_lyrics.syllables("one two three"))


# --- midi_info --------------------------------------------------------------------

def test_midi_info_counts_notes_per_track() -> None:
    def track(events: bytes) -> bytes:
        return b"MTrk" + struct.pack(">I", len(events)) + events

    name = b"\x00\xff\x03\x04Alto"
    notes = (b"\x00\x90\x3c\x40" b"\x83\x60\x80\x3c\x00"   # C4 for 480 ticks
             b"\x00\x90\x43\x40" b"\x83\x60\x80\x43\x00")  # G4
    data = b"MThd" + struct.pack(">IHHH", 6, 1, 1, 480) + track(name + notes + b"\x00\xff\x2f\x00")
    [t] = midi_info.read_tracks(data)
    assert (t.name, t.notes, t.low, t.high, t.first, t.last) == ("Alto", 2, 60, 67, 0.0, 1.0)
