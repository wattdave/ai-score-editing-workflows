"""Unit tests for music utilities."""

from __future__ import annotations

import pytest

from ai_score_editing.music import (
    duration_to_name,
    parse_duration,
    parse_note_sequence,
    parse_pitch,
    pitch_to_name,
    resolve_instrument_style,
)


def test_parse_pitch() -> None:
    assert parse_pitch(60) == 60
    assert parse_pitch("60") == 60
    assert parse_pitch("C4") == 60
    assert parse_pitch("c4") == 60
    assert parse_pitch("A4") == 69
    assert parse_pitch("F#4") == 66
    assert parse_pitch("F♯4") == 66
    assert parse_pitch("Bb3") == 58
    assert parse_pitch("B♭3") == 58
    assert parse_pitch("C-1") == 0
    assert parse_pitch("G9") == 127

    with pytest.raises(ValueError, match="Invalid pitch name"):
        parse_pitch("H4")
    with pytest.raises(ValueError, match="outside 0-127"):
        parse_pitch("C10")


def test_pitch_to_name() -> None:
    assert pitch_to_name(60) == "C4"
    assert pitch_to_name(69) == "A4"
    assert pitch_to_name(58) == "Bb3"
    assert pitch_to_name(0) == "C-1"


def test_parse_duration() -> None:
    assert parse_duration(256) == 256
    assert parse_duration("256") == 256
    assert parse_duration("quarter") == 256
    assert parse_duration("half") == 512
    assert parse_duration("whole") == 1024
    assert parse_duration("eighth") == 128
    assert parse_duration("16th") == 64
    assert parse_duration("quarter.") == 384
    assert parse_duration("half.") == 768
    assert parse_duration("1/4") == 256
    assert parse_duration("1/8") == 128
    assert parse_duration("1/2") == 512

    with pytest.raises(ValueError, match="Invalid duration"):
        parse_duration("bogus")


def test_duration_to_name() -> None:
    assert duration_to_name(256) == "quarter"
    assert duration_to_name(512) == "half"
    assert duration_to_name(384) == "quarter."
    assert duration_to_name(1234) == "1234"


def test_resolve_instrument_style() -> None:
    assert resolve_instrument_style("soprano") == "instrument.singers.soprano"
    assert resolve_instrument_style("alto") == "instrument.singers.alto"
    assert resolve_instrument_style("tenor") == "instrument.singers.tenor"
    assert resolve_instrument_style("bass") == "instrument.singers.bass"
    assert resolve_instrument_style("piano") == "instrument.keyboard.piano"
    assert resolve_instrument_style("violin") == "instrument.strings.violin"
    assert resolve_instrument_style("flute") == "instrument.wind.flute"
    assert resolve_instrument_style("instrument.custom.id") == "instrument.custom.id"
    assert resolve_instrument_style("something.else") == "something.else"


def test_parse_note_sequence() -> None:
    seq = parse_note_sequence("C4:quarter D4:quarter E4:half")
    assert len(seq) == 3
    assert seq[0] == {"pitches": [60], "duration": 256, "tied": False}
    assert seq[1] == {"pitches": [62], "duration": 256, "tied": False}
    assert seq[2] == {"pitches": [64], "duration": 512, "tied": False}

    chord_seq = parse_note_sequence("C4,E4,G4:half:tied")
    assert len(chord_seq) == 1
    assert chord_seq[0] == {"pitches": [60, 64, 67], "duration": 512, "tied": True}

    rest_seq = parse_note_sequence("rest:quarter C4:quarter")
    assert len(rest_seq) == 2
    assert rest_seq[0] == {"pitches": [], "duration": 256, "tied": False}
    assert rest_seq[1] == {"pitches": [60], "duration": 256, "tied": False}
