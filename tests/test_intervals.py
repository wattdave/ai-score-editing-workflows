"""Shared interval, spelling and lyric-splitting helpers."""

import pytest

from ai_score_editing.intervals import (
    alteration,
    compute_transposition,
    interval_of,
    spelling_letter,
    transpose_spelled,
)
from ai_score_editing.lyrics import split_syllables


def test_compute_transposition_major_second_up() -> None:
    assert compute_transposition("C", "D", True) == (1, 5)


def test_spelling_letter_defaults_and_checks() -> None:
    assert spelling_letter(70) == "B"          # Bb by default
    assert spelling_letter(70, "A#") == "A"
    with pytest.raises(ValueError, match="does not match"):
        spelling_letter(70, "B")


def test_alteration_is_signed_from_the_natural() -> None:
    assert alteration(70, "B") == -1
    assert alteration(70, "A") == 1
    assert alteration(60, "B") == 1            # B#


def test_transpose_spelled_and_interval_of() -> None:
    steps, semis = interval_of({"fromNote": "C", "toNote": "D", "direction": "up"}, "op")
    assert transpose_spelled("B4", 71, steps, semis) == (73, "C")
    assert interval_of({"semitones": -12}, "op") == (-7, -12)
    with pytest.raises(ValueError, match="double accidental"):
        transpose_spelled("Bx4", 73, 0, 2)
    with pytest.raises(ValueError, match="MIDI range"):
        transpose_spelled("C9", 120, 7, 12)
    with pytest.raises(ValueError, match="op.direction"):
        interval_of({"fromNote": "C", "toNote": "D"}, "op")


def test_split_syllables_kinds() -> None:
    assert split_syllables("ma-king lyr-i-cal _ now") == [
        ("ma", "begin"), ("king", "end"),
        ("lyr", "begin"), ("i", "middle"), ("cal", "end"),
        ("", "melisma"), ("now", "single"),
    ]
    with pytest.raises(ValueError):
        split_syllables("  ")
    with pytest.raises(ValueError):
        split_syllables("--")
