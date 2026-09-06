"""Interval math for ManuScript's Transpose(degree, interval type).

Degree is 0-based diatonic steps, signed for direction. Interval type is the
quality constant from docs/manuscript-constants.md: 5 = major/perfect
(reference), each semitone of narrowing/widening subtracts/adds 1 (4 = minor
or diminished, 6 = augmented, ...), valid range 0-10.
"""

from __future__ import annotations

_LETTER_STEPS = {"C": 0, "D": 1, "E": 2, "F": 3, "G": 4, "A": 5, "B": 6}
_LETTER_SEMITONES = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
_ACCIDENTAL_SEMITONES = {"": 0, "#": 1, "##": 2, "x": 2, "b": -1, "bb": -2}
#: Semitones in the major/perfect interval for each 0-based diatonic step.
_REFERENCE_SEMITONES = [0, 2, 4, 5, 7, 9, 11]


def parse_note(name: str) -> tuple[int, int]:
    """Return (diatonic step 0-6, pitch class 0-11) for a note name like 'F#'."""
    letter, accidental = name[:1].upper(), name[1:].replace("♯", "#").replace("♭", "b")
    if letter not in _LETTER_STEPS or accidental not in _ACCIDENTAL_SEMITONES:
        raise ValueError(f"unrecognized note name: {name!r}")
    step = _LETTER_STEPS[letter]
    semitones = (_LETTER_SEMITONES[letter] + _ACCIDENTAL_SEMITONES[accidental]) % 12
    return step, semitones


def compute_transposition(from_note: str, to_note: str, up: bool) -> tuple[int, int]:
    """Return (signed degree, interval type) for Selection.Transpose."""
    from_step, from_semi = parse_note(from_note)
    to_step, to_semi = parse_note(to_note)
    if up:
        steps = (to_step - from_step) % 7
        semitones = (to_semi - from_semi) % 12
    else:
        steps = (from_step - to_step) % 7
        semitones = (from_semi - to_semi) % 12
    interval_type = 5 + (semitones - _REFERENCE_SEMITONES[steps])
    if not 0 <= interval_type <= 10:
        raise ValueError(
            f"interval {from_note}->{to_note} ({'up' if up else 'down'}) is not "
            f"expressible as a ManuScript interval type (got {interval_type})"
        )
    return (steps if up else -steps), interval_type
