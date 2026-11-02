"""Interval and spelling math shared by the back ends.

compute_transposition gives ManuScript's Transpose(degree, interval type).
Degree is 0-based diatonic steps, signed for direction. Interval type is the
quality constant from the ManuScript guide's Global Constants: 5 = major/perfect
(reference), each semitone of narrowing/widening subtracts/adds 1 (4 = minor
or diminished, 6 = augmented, ...), valid range 0-10.

The spelling helpers move spelled notes for back ends that transpose note by
note (Dorico, MuseScore). They raise BatchError (a ValueError), which every
back end already reports as a batch error.
"""

from __future__ import annotations

from typing import Any

from ai_score_editing.core.errors import BatchError

_LETTER_STEPS = {"C": 0, "D": 1, "E": 2, "F": 3, "G": 4, "A": 5, "B": 6}
_LETTER_SEMITONES = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
_ACCIDENTAL_SEMITONES = {"": 0, "#": 1, "##": 2, "x": 2, "b": -1, "bb": -2}
#: Semitones in the major/perfect interval for each 0-based diatonic step,
#: which are also the natural notes' pitch classes from C.
REFERENCE_SEMITONES = [0, 2, 4, 5, 7, 9, 11]
LETTERS = "CDEFGAB"
#: Spelling for a pitch class when none is given.
DEFAULT_SPELLING = {0: "C", 1: "C#", 2: "D", 3: "Eb", 4: "E", 5: "F", 6: "F#", 7: "G", 8: "Ab", 9: "A", 10: "Bb", 11: "B"}


def parse_note(name: str) -> tuple[int, int]:
    """Return (diatonic step 0-6, pitch class 0-11) for a note name like 'F#'."""
    letter, accidental = name[:1].upper(), name[1:].replace("♯", "#").replace("♭", "b")
    if letter not in _LETTER_STEPS or accidental not in _ACCIDENTAL_SEMITONES:
        raise BatchError(f"unrecognized note name: {name!r}")
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
    interval_type = 5 + (semitones - REFERENCE_SEMITONES[steps])
    if not 0 <= interval_type <= 10:
        raise BatchError(
            f"interval {from_note}->{to_note} ({'up' if up else 'down'}) is not "
            f"expressible as a ManuScript interval type (got {interval_type})"
        )
    return (steps if up else -steps), interval_type


def spelling_letter(pitch: int, spelling: str | None = None) -> str:
    """The letter name to spell `pitch` with, checking an explicit spelling fits."""
    name = spelling or DEFAULT_SPELLING[pitch % 12]
    step, semitones = parse_note(name)
    if semitones != pitch % 12:
        raise BatchError(f"spelling {name} does not match MIDI pitch {pitch}")
    return LETTERS[step]


def alteration(pitch: int, letter: str) -> int:
    """Semitones from `letter`'s natural note to `pitch`, from -6 to 5."""
    return (pitch % 12 - REFERENCE_SEMITONES[LETTERS.index(letter)] + 6) % 12 - 6


def transpose_spelled(name: str | None, pitch: int, steps: int, semitones: int) -> tuple[int, str]:
    """(new pitch, new letter) for a note moved by diatonic steps and semitones."""
    new_pitch = pitch + semitones
    if not 0 <= new_pitch <= 127:
        raise BatchError(f"transposing {pitch} by {semitones} leaves the MIDI range")
    if not name:
        return new_pitch, spelling_letter(new_pitch)
    letter = LETTERS[(LETTERS.index(name[0]) + steps) % 7]
    if abs(alteration(new_pitch, letter)) > 2:
        raise BatchError(f"{name} transposed would need more than a double accidental")
    return new_pitch, letter


def interval_of(operation: dict[str, Any], label: str) -> tuple[int, int]:
    """(signed diatonic steps, signed semitones) for a transpose operation.

    It takes "semitones" (with optional "steps"), or "fromNote", "toNote",
    "direction" and optional "octaves", as apply_batch's transpose does.
    """
    if "semitones" in operation:
        semitones = _int(operation, "semitones", label, -36, 36)
        steps = operation.get("steps")
        if steps is None:
            steps = round(semitones * 7 / 12)
        elif not isinstance(steps, int) or isinstance(steps, bool):
            raise BatchError(f"{label}.steps must be an integer")
        return steps, semitones
    direction = operation.get("direction")
    if direction not in {"up", "down"}:
        raise BatchError(f"{label}.direction must be 'up' or 'down'")
    octaves = _int({"octaves": 0, **operation}, "octaves", label, 0, 2)
    try:
        degree, interval_type = compute_transposition(
            _str(operation, "fromNote", label), _str(operation, "toNote", label), direction == "up"
        )
    except (KeyError, ValueError) as exc:
        raise BatchError(f"{label}: {exc}") from exc
    sign = 1 if direction == "up" else -1
    semitones = REFERENCE_SEMITONES[abs(degree)] + interval_type - 5
    return degree + 7 * octaves * sign, sign * (semitones + 12 * octaves)


def _int(operation: dict[str, Any], field: str, label: str, minimum: int, maximum: int) -> int:
    value = operation.get(field)
    if not isinstance(value, int) or isinstance(value, bool):
        raise BatchError(f"{label}.{field} must be an integer")
    if not minimum <= value <= maximum:
        raise BatchError(f"{label}.{field} must be {minimum}-{maximum}")
    return value


def _str(operation: dict[str, Any], field: str, label: str) -> str:
    value = operation.get(field)
    if not isinstance(value, str) or not value:
        raise BatchError(f"{label}.{field} must be a non-empty string")
    return value
