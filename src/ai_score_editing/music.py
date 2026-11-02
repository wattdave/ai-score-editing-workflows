"""Music parsing and formatting utilities for pitches, durations, and instruments."""

from __future__ import annotations

import re
from typing import Any

from ai_score_editing.units import UNITS_PER_WHOLE

# Standard semitone mappings
_LETTER_SEMITONES: dict[str, int] = {
    "C": 0,
    "D": 2,
    "E": 4,
    "F": 5,
    "G": 7,
    "A": 9,
    "B": 11,
}

_ACCIDENTAL_SEMITONES: dict[str, int] = {
    "": 0,
    "#": 1,
    "♯": 1,
    "##": 2,
    "x": 2,
    "b": -1,
    "♭": -1,
    "bb": -2,
}

_SEMITONE_NAMES: list[str] = [
    "C",
    "C#",
    "D",
    "Eb",
    "E",
    "F",
    "F#",
    "G",
    "Ab",
    "A",
    "Bb",
    "B",
]

_DURATION_NAMES: dict[str, int] = {
    "whole": 1024,
    "1": 1024,
    "1/1": 1024,
    "whole.": 1536,
    "dotted-whole": 1536,
    "half": 512,
    "2": 512,
    "1/2": 512,
    "half.": 768,
    "dotted-half": 768,
    "quarter": 256,
    "4": 256,
    "1/4": 256,
    "quarter.": 384,
    "dotted-quarter": 384,
    "eighth": 128,
    "8": 128,
    "1/8": 128,
    "eighth.": 192,
    "dotted-eighth": 192,
    "16th": 64,
    "sixteenth": 64,
    "16": 64,
    "1/16": 64,
    "16th.": 96,
    "dotted-16th": 96,
    "32nd": 32,
    "thirty-second": 32,
    "32": 32,
    "1/32": 32,
}

_INSTRUMENT_ALIASES: dict[str, str] = {
    # Voice / Singers
    "soprano": "instrument.singers.soprano",
    "solo-soprano": "instrument.singers.soprano.solo",
    "alto": "instrument.singers.alto",
    "solo-alto": "instrument.singers.alto.solo",
    "tenor": "instrument.singers.tenor",
    "solo-tenor": "instrument.singers.tenor.solo",
    "bass": "instrument.singers.bass",
    "solo-bass": "instrument.singers.bass.solo",
    "baritone": "instrument.singers.baritone",
    "mezzo": "instrument.singers.mezzo-soprano",
    "mezzo-soprano": "instrument.singers.mezzo-soprano",
    "contralto": "instrument.singers.contralto",
    "countertenor": "instrument.singers.counter-tenor",
    "choir": "instrument.singers.choir",
    "voice": "instrument.singers.voice",
    # Keyboards
    "piano": "instrument.keyboard.piano",
    "grand-piano": "instrument.keyboard.piano.grand",
    "organ": "instrument.keyboard.organ",
    "harpsichord": "instrument.keyboard.harpsichord",
    "celesta": "instrument.keyboard.celesta",
    # Strings
    "violin": "instrument.strings.violin",
    "violin-1": "instrument.strings.violin.1",
    "violin-2": "instrument.strings.violin.2",
    "viola": "instrument.strings.viola",
    "cello": "instrument.strings.violoncello",
    "violoncello": "instrument.strings.violoncello",
    "contrabass": "instrument.strings.contrabass",
    "double-bass": "instrument.strings.contrabass",
    "double_bass": "instrument.strings.contrabass",
    # Woodwinds
    "flute": "instrument.wind.flute",
    "piccolo": "instrument.wind.piccolo",
    "oboe": "instrument.wind.oboe",
    "english-horn": "instrument.wind.cor-anglais",
    "cor-anglais": "instrument.wind.cor-anglais",
    "clarinet": "instrument.wind.clarinet.bflat",
    "bass-clarinet": "instrument.wind.clarinet.bass.bflat",
    "bassoon": "instrument.wind.bassoon",
    "recorder": "instrument.wind.recorder.soprano",
    # Brass
    "trumpet": "instrument.brass.trumpet.bflat",
    "cornet": "instrument.brass.cornet.bflat",
    "horn": "instrument.brass.horn.f",
    "french-horn": "instrument.brass.horn.f",
    "trombone": "instrument.brass.trombone",
    "bass-trombone": "instrument.brass.trombone.bass",
    "euphonium": "instrument.brass.euphonium",
    "tuba": "instrument.brass.tuba",
    # Plucked & Percussion
    "guitar": "instrument.guitar.acoustic",
    "acoustic-guitar": "instrument.guitar.acoustic",
    "classical-guitar": "instrument.guitar.nylon",
    "electric-guitar": "instrument.guitar.electric",
    "bass-guitar": "instrument.guitar.bass",
    "harp": "instrument.harp",
    "timpani": "instrument.pitchedpercussion.timpani",
    "glockenspiel": "instrument.pitchedpercussion.glockenspiel",
    "xylophone": "instrument.pitchedpercussion.xylophone",
    "marimba": "instrument.pitchedpercussion.marimba",
}


def parse_pitch(val: str | int) -> int:
    """Parse a note string (e.g. 'C4', 'F#3', 'Bb5', '60') or int into a MIDI pitch."""
    if isinstance(val, int):
        if not 0 <= val <= 127:
            raise ValueError(f"MIDI pitch {val} out of range 0-127")
        return val

    s = str(val).strip()
    if s.isdigit() or (s.startswith("-") and s[1:].isdigit()):
        p = int(s)
        if not 0 <= p <= 127:
            raise ValueError(f"MIDI pitch {p} out of range 0-127")
        return p

    m = re.match(r"^([a-gA-G])([#♯b♭xX]{0,2})(-?\d+)$", s)
    if not m:
        raise ValueError(f"Invalid pitch name: {val!r} (expected e.g. 'C4', 'F#3', 'Bb5', '60')")

    letter = m.group(1).upper()
    accidental = m.group(2).replace("X", "x")
    octave = int(m.group(3))

    semitone = _LETTER_SEMITONES[letter] + _ACCIDENTAL_SEMITONES[accidental]
    midi_pitch = (octave + 1) * 12 + semitone
    if not 0 <= midi_pitch <= 127:
        raise ValueError(f"Pitch {val!r} evaluates to MIDI {midi_pitch}, outside 0-127")
    return midi_pitch


def pitch_to_name(pitch: int) -> str:
    """Convert a MIDI pitch number (0-127) to scientific pitch notation (e.g. 60 -> 'C4')."""
    if not 0 <= pitch <= 127:
        raise ValueError(f"MIDI pitch {pitch} out of range 0-127")
    octave = (pitch // 12) - 1
    semi = pitch % 12
    return f"{_SEMITONE_NAMES[semi]}{octave}"


def parse_duration(val: str | int) -> int:
    """Parse a duration string (e.g. 'quarter', 'half.', '256', '1/4') into 1/256th-quarter ticks."""
    if isinstance(val, int):
        if val <= 0:
            raise ValueError(f"Duration ticks must be positive, got {val}")
        return val

    s = str(val).strip().lower()
    if s.isdigit():
        ticks = int(s)
        if ticks <= 0:
            raise ValueError(f"Duration ticks must be positive, got {ticks}")
        return ticks

    if s in _DURATION_NAMES:
        return _DURATION_NAMES[s]

    # Try fraction
    if "/" in s:
        parts = s.split("/", 1)
        if parts[0].strip().isdigit() and parts[1].strip().isdigit():
            num = int(parts[0].strip())
            denom = int(parts[1].strip())
            if denom > 0:
                # 1/1 = 1024 ticks -> (num / denom) * 1024
                ticks = int((num / denom) * UNITS_PER_WHOLE)
                if ticks > 0:
                    return ticks

    raise ValueError(
        f"Invalid duration: {val!r} (expected e.g. 'quarter', 'half.', '1/8', '256')"
    )


def duration_to_name(ticks: int) -> str:
    """Return friendly name for duration ticks if common, else string tick count."""
    for name, t in _DURATION_NAMES.items():
        if t == ticks and not name.isdigit() and "/" not in name:
            return name
    return str(ticks)


def resolve_instrument_style(name_or_style: str) -> str:
    """Resolve a friendly instrument name or style ID to a Sibelius style ID."""
    s = name_or_style.strip()
    clean = s.lower().replace(" ", "-")
    if clean in _INSTRUMENT_ALIASES:
        return _INSTRUMENT_ALIASES[clean]
    if s.startswith("instrument.") or "." in s:
        return s
    return f"instrument.{clean}"


def parse_note_sequence(spec: str) -> list[dict[str, Any]]:
    """Parse shorthand note sequence string into list of note dictionaries.

    Format: space-separated items of 'pitch_spec:duration[:tied]'
    Examples:
        'C4:quarter D4:quarter E4:half'
        'C4,E4,G4:half:tied'
        '60:256 62:256 64:512'
        'rest:quarter C4:quarter'
    """
    tokens = spec.strip().split()
    results: list[dict[str, Any]] = []

    for token in tokens:
        parts = token.split(":")
        pitch_str = parts[0].strip()
        dur_str = parts[1].strip() if len(parts) > 1 else "quarter"
        tied_str = parts[2].strip().lower() if len(parts) > 2 else ""

        duration = parse_duration(dur_str)
        tied = tied_str in ("tied", "tie", "true", "1")

        if pitch_str.lower() in ("rest", "r", "z"):
            pitches: list[int] = []
        else:
            pitches = [parse_pitch(p.strip()) for p in pitch_str.split(",") if p.strip()]

        results.append({
            "pitches": pitches,
            "duration": duration,
            "tied": tied,
        })

    return results
