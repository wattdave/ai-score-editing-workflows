"""Unit tests for ABC notation parsing and formatting."""

from __future__ import annotations

from ai_score_editing.abc_notation import (
    abc_pitch_to_midi,
    midi_to_abc_pitch,
    parse_abc_duration,
    parse_abc_snippet,
    score_to_abc,
    ticks_to_abc_duration,
)


def test_pitch_conversion() -> None:
    # Key of C
    assert midi_to_abc_pitch(60, "C") == "C"
    assert midi_to_abc_pitch(62, "C") == "D"
    assert midi_to_abc_pitch(72, "C") == "c"
    assert midi_to_abc_pitch(84, "C") == "c'"
    assert midi_to_abc_pitch(48, "C") == "C,"
    assert midi_to_abc_pitch(61, "C") == "^C"
    assert midi_to_abc_pitch(58, "C") == "_B,"

    # In key of Bb (B and E are flatted by default)
    assert midi_to_abc_pitch(58, "Bb") == "B,"
    assert midi_to_abc_pitch(70, "Bb") == "B"
    assert midi_to_abc_pitch(71, "Bb") == "=B"
    assert midi_to_abc_pitch(82, "Bb") == "b"
    assert midi_to_abc_pitch(83, "Bb") == "=b"

    # ABC to MIDI
    assert abc_pitch_to_midi("C", "C") == 60
    assert abc_pitch_to_midi("c", "C") == 72
    assert abc_pitch_to_midi("c'", "C") == 84
    assert abc_pitch_to_midi("C,", "C") == 48
    assert abc_pitch_to_midi("^C", "C") == 61
    assert abc_pitch_to_midi("_B", "C") == 70
    assert abc_pitch_to_midi("B,", "Bb") == 58


def test_duration_conversion() -> None:
    assert ticks_to_abc_duration(256) == ""
    assert ticks_to_abc_duration(512) == "2"
    assert ticks_to_abc_duration(1024) == "4"
    assert ticks_to_abc_duration(128) == "/"
    assert ticks_to_abc_duration(64) == "/4"
    assert ticks_to_abc_duration(384) == "3/2"

    assert parse_abc_duration("") == 256
    assert parse_abc_duration("2") == 512
    assert parse_abc_duration("4") == 1024
    assert parse_abc_duration("/") == 128
    assert parse_abc_duration("/2") == 128
    assert parse_abc_duration("/4") == 64
    assert parse_abc_duration("3/2") == 384


def test_score_to_abc() -> None:
    bars = [
        {
            "barNumber": 1,
            "objects": [
                {
                    "type": "NoteRest",
                    "position": 0,
                    "duration": 256,
                    "notes": [{"pitch": 58, "tied": False}],
                },
                {
                    "type": "NoteRest",
                    "position": 256,
                    "duration": 512,
                    "notes": [{"pitch": 62, "tied": False}],
                },
            ],
        },
        {
            "barNumber": 2,
            "objects": [
                {
                    "type": "NoteRest",
                    "position": 0,
                    "duration": 768,
                    "notes": [{"pitch": 65, "tied": True}],
                }
            ],
        },
    ]
    lyrics = [
        {"bar": 1, "position": 0, "text": "Hal", "syllableType": "middle"},
        {"bar": 1, "position": 256, "text": "le", "syllableType": "middle"},
        {"bar": 2, "position": 0, "text": "lujah!", "syllableType": "end"},
    ]

    abc = score_to_abc(bars, lyrics=lyrics, time_sig=(3, 4), key="Bb", staff_num=1, instrument_name="Soprano")
    assert "M:3/4" in abc
    assert "K:Bb" in abc
    assert "T:Soprano" in abc
    assert "B, D2 | F3- |" in abc
    assert "w: Hal- le- lujah!" in abc


def test_parse_abc_snippet() -> None:
    snippet = """
    M:6/4
    L:1/4
    K:Bb
    B, D F2 G2 | F4 D2
    w: And when my life I've
    """
    res = parse_abc_snippet(snippet)
    assert res["key"] == "Bb"
    assert res["meter"] == "6/4"
    assert len(res["notes"]) == 6
    # First bar
    assert res["notes"][0] == {"bar": 1, "position": 0, "duration": 256, "pitches": [58], "tied": False, "isRest": False}
    assert res["notes"][1] == {"bar": 1, "position": 256, "duration": 256, "pitches": [62], "tied": False, "isRest": False}
    assert res["notes"][2] == {"bar": 1, "position": 512, "duration": 512, "pitches": [65], "tied": False, "isRest": False}
    assert res["notes"][3] == {"bar": 1, "position": 1024, "duration": 512, "pitches": [67], "tied": False, "isRest": False}
    # Second bar (starts after |)
    assert res["notes"][4] == {"bar": 2, "position": 0, "duration": 1024, "pitches": [65], "tied": False, "isRest": False}
    assert res["notes"][5] == {"bar": 2, "position": 1024, "duration": 512, "pitches": [62], "tied": False, "isRest": False}

    # Lyrics
    assert len(res["lyrics"]) == 5
    assert res["lyrics"][0] == {"bar": 1, "position": 0, "duration": 256, "text": "And", "syllableType": "end"}
    assert res["lyrics"][1] == {"bar": 1, "position": 256, "duration": 256, "text": "when", "syllableType": "end"}
    assert res["lyrics"][2] == {"bar": 1, "position": 512, "duration": 512, "text": "my", "syllableType": "end"}
    assert res["lyrics"][3] == {"bar": 1, "position": 1024, "duration": 512, "text": "life", "syllableType": "end"}
    assert res["lyrics"][4] == {"bar": 2, "position": 0, "duration": 1024, "text": "I've", "syllableType": "end"}
