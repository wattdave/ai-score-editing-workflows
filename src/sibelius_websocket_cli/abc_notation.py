"""ABC notation parsing and formatting for Sibelius scores.

Provides bidirectional conversion between Sibelius score structures
(bars, notes, lyrics) and standard ABC notation.
"""

from __future__ import annotations

import re
from typing import Any

# Default unit note length in ticks (1/4 note = 256 ticks)
DEFAULT_UNIT_TICKS = 256


# Key signature accidentals for standard major keys
KEY_ACCIDENTALS: dict[str, dict[str, int]] = {
    "C": {},
    "G": {"F": 1},
    "D": {"F": 1, "C": 1},
    "A": {"F": 1, "C": 1, "G": 1},
    "E": {"F": 1, "C": 1, "G": 1, "D": 1},
    "B": {"F": 1, "C": 1, "G": 1, "D": 1, "A": 1},
    "F#": {"F": 1, "C": 1, "G": 1, "D": 1, "A": 1, "E": 1},
    "F": {"B": -1},
    "Bb": {"B": -1, "E": -1},
    "Eb": {"B": -1, "E": -1, "A": -1},
    "Ab": {"B": -1, "E": -1, "A": -1, "D": -1},
    "Db": {"B": -1, "E": -1, "A": -1, "D": -1, "G": -1},
    "Gb": {"B": -1, "E": -1, "A": -1, "D": -1, "G": -1, "C": -1},
}


def midi_to_abc_pitch(pitch: int, key: str = "C", name: str | None = None) -> str:
    """Convert a MIDI pitch (0-127) to an ABC pitch symbol, honoring key signature and optional note name."""
    octave = (pitch // 12) - 1
    key_mods = KEY_ACCIDENTALS.get(key, {})

    if name:
        m = re.match(r"^([a-gA-G])([#♯b♭xX]{0,2})(-?\d+)$", name.strip())
        if m:
            letter = m.group(1).upper()
            acc_part = m.group(2).replace("♯", "#").replace("♭", "b").replace("X", "x")
            octave = int(m.group(3))
            acc_map = {"": 0, "#": 1, "##": 2, "x": 2, "b": -1, "bb": -2}
            actual_acc = acc_map.get(acc_part, 0)
            expected_acc = key_mods.get(letter, 0)
            prefix = ""
            if actual_acc != expected_acc:
                if actual_acc == 1:
                    prefix = "^"
                elif actual_acc == 2:
                    prefix = "^^"
                elif actual_acc == -1:
                    prefix = "_"
                elif actual_acc == -2:
                    prefix = "__"
                elif actual_acc == 0:
                    prefix = "="

            if octave == 4:
                letter_str = letter.upper()
            elif octave == 5:
                letter_str = letter.lower()
            elif octave > 5:
                letter_str = letter.lower() + ("'" * (octave - 5))
            else:
                letter_str = letter.upper() + ("," * (4 - octave))
            return f"{prefix}{letter_str}"

    semi = pitch % 12
    # In flat keys, prefer flats; in sharp keys, prefer sharps. In C major, standard accidental spelling:
    # 0:C, 1:C#, 2:D, 3:Eb, 4:E, 5:F, 6:F#, 7:G, 8:Ab, 9:A, 10:Bb, 11:B
    standard_spelling = [
        ("C", 0), ("C", 1), ("D", 0), ("E", -1), ("E", 0),
        ("F", 0), ("F", 1), ("G", 0), ("A", -1), ("A", 0),
        ("B", -1), ("B", 0),
    ]
    letter, actual_acc = standard_spelling[semi]
    expected_acc = key_mods.get(letter, 0)
    prefix = ""
    if actual_acc != expected_acc:
        if actual_acc == 1:
            prefix = "^"
        elif actual_acc == 2:
            prefix = "^^"
        elif actual_acc == -1:
            prefix = "_"
        elif actual_acc == -2:
            prefix = "__"
        elif actual_acc == 0:
            prefix = "="

    if octave == 4:
        letter_str = letter.upper()
    elif octave == 5:
        letter_str = letter.lower()
    elif octave > 5:
        letter_str = letter.lower() + ("'" * (octave - 5))
    else:
        letter_str = letter.upper() + ("," * (4 - octave))

    return f"{prefix}{letter_str}"


def ticks_to_abc_duration(ticks: int, unit_ticks: int = DEFAULT_UNIT_TICKS) -> str:
    """Format duration ticks relative to ABC unit note length (L:1/4)."""
    if ticks == unit_ticks:
        return ""
    if ticks % unit_ticks == 0:
        return str(ticks // unit_ticks)
    if unit_ticks % ticks == 0:
        ratio = unit_ticks // ticks
        return f"/{ratio}" if ratio > 2 else "/"
    # Fraction
    from math import gcd

    g = gcd(ticks, unit_ticks)
    return f"{ticks // g}/{unit_ticks // g}"


def abc_pitch_to_midi(symbol: str, key: str = "C") -> int:
    """Parse an ABC pitch token (e.g. '^c', 'B,', '_e\'', '=F') into a MIDI number."""
    m = re.match(r"^(\^{1,2}|_{1,2}|=)?([a-gA-G])([,']*)", symbol)
    if not m:
        raise ValueError(f"Invalid ABC pitch symbol: {symbol!r}")

    acc_str, letter, oct_mod = m.groups()
    key_mods = KEY_ACCIDENTALS.get(key, {})

    base_semi = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}[letter.upper()]
    if acc_str == "^":
        acc = 1
    elif acc_str == "^^":
        acc = 2
    elif acc_str == "_":
        acc = -1
    elif acc_str == "__":
        acc = -2
    elif acc_str == "=":
        acc = 0
    else:
        acc = key_mods.get(letter.upper(), 0)

    # Base octave
    octave = 5 if letter.islower() else 4
    for char in oct_mod:
        if char == "'":
            octave += 1
        elif char == ",":
            octave -= 1

    return (octave + 1) * 12 + base_semi + acc


def parse_abc_duration(dur_str: str, unit_ticks: int = DEFAULT_UNIT_TICKS) -> int:
    """Parse ABC duration multiplier/fraction into 1/256th-quarter ticks."""
    if not dur_str:
        return unit_ticks

    s = dur_str.strip()
    if s == "/":
        return unit_ticks // 2
    if s.startswith("/"):
        denom = int(s[1:])
        return unit_ticks // denom
    if "/" in s:
        parts = s.split("/")
        num = int(parts[0]) if parts[0] else 1
        denom = int(parts[1]) if parts[1] else 2
        return int((num / denom) * unit_ticks)
    if s.isdigit():
        return int(s) * unit_ticks

    return unit_ticks


def score_to_abc(
    bars: list[dict[str, Any]],
    lyrics: list[dict[str, Any]] | None = None,
    time_sig: tuple[int, int] | None = None,
    key: str = "C",
    staff_num: int = 1,
    instrument_name: str | None = None,
) -> str:
    """Format bars and optional lyrics into standard ABC notation."""
    lines: list[str] = []
    lines.append(f"X:{staff_num}")
    if instrument_name:
        lines.append(f"T:{instrument_name}")
    if time_sig:
        lines.append(f"M:{time_sig[0]}/{time_sig[1]}")
    lines.append("L:1/4")
    lines.append(f"K:{key}")
    lines.append(f'V:{staff_num} name="{instrument_name or f"Staff {staff_num}"}"')

    # Index lyrics by (bar, position)
    lyrics_by_pos: dict[tuple[int, int], list[dict[str, Any]]] = {}
    if lyrics:
        for lyr in lyrics:
            b = lyr.get("bar", 0)
            p = lyr.get("position", 0)
            lyrics_by_pos.setdefault((b, p), []).append(lyr)

    music_tokens: list[str] = []
    lyric_tokens: list[str] = []

    for bar in bars:
        bar_num = bar.get("barNumber", 0)
        objects = bar.get("objects", [])

        bar_has_notes = False
        for obj in objects:
            obj_type = obj.get("type")
            if obj_type != "NoteRest":
                continue

            bar_has_notes = True
            pos = obj.get("position", 0)
            dur = obj.get("duration", 256)
            dur_abc = ticks_to_abc_duration(dur, DEFAULT_UNIT_TICKS)
            notes = obj.get("notes", [])

            # Music representation
            if not notes:
                # Rest
                music_tokens.append(f"z{dur_abc}")
                lyric_tokens.append("*")
            elif len(notes) == 1:
                n = notes[0]
                p_abc = midi_to_abc_pitch(n["pitch"], key=key, name=n.get("name"))
                tie = "-" if n.get("tied") else ""
                music_tokens.append(f"{p_abc}{dur_abc}{tie}")
            else:
                chord_notes = "".join(midi_to_abc_pitch(n["pitch"], key=key, name=n.get("name")) for n in notes)
                tie = "-" if any(n.get("tied") for n in notes) else ""
                music_tokens.append(f"[{chord_notes}]{dur_abc}{tie}")

            # Lyric alignment
            if notes:
                lyrs = lyrics_by_pos.get((bar_num, pos), [])
                if lyrs:
                    txt = lyrs[0].get("text", "")
                    st = lyrs[0].get("syllableType", "end")
                    lyric_tokens.append(f"{txt}-" if st == "middle" else txt)
                else:
                    lyric_tokens.append("*")

        if bar_has_notes or not objects:
            music_tokens.append("|")

    # Assemble into lines
    music_line = " ".join(music_tokens)
    lines.append(music_line)

    # Check if lyrics were found
    non_rest_lyrics = [t for t in lyric_tokens if t != "*"]
    if non_rest_lyrics:
        lyric_line = "w: " + " ".join(lyric_tokens)
        lines.append(lyric_line)

    return "\n".join(lines)


def parse_abc_snippet(
    abc_text: str,
    default_key: str = "C",
    unit_ticks: int = DEFAULT_UNIT_TICKS,
) -> dict[str, Any]:
    """Parse an ABC snippet (music and optional w: lyrics) into note and lyric events.

    Returns:
        {
            'key': str,
            'meter': str | None,
            'notes': list of {bar, position, duration, pitches, tied},
            'lyrics': list of {bar, position, duration, text, syllableType}
        }
    """
    key = default_key
    meter = None
    music_chunks: list[str] = []
    lyric_chunks: list[str] = []

    for raw_line in abc_text.strip().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("%"):
            continue
        if line.startswith("K:"):
            key = line[2:].strip()
        elif line.startswith("M:"):
            meter = line[2:].strip()
        elif line.startswith("L:"):
            l_val = line[2:].strip()
            if l_val == "1/8":
                unit_ticks = 128
            elif l_val == "1/4":
                unit_ticks = 256
            elif l_val == "1/2":
                unit_ticks = 512
        elif line.startswith("w:"):
            lyric_chunks.append(line[2:].strip())
        elif not re.match(r"^[A-Za-z]:", line):
            music_chunks.append(line)

    full_music = " ".join(music_chunks)
    full_lyrics = " ".join(lyric_chunks)

    # Regex for ABC tokens:
    # 1. Bar lines: |], ||, |:, :|, |
    # 2. Chords: \[[^\]]+\]([0-9/]*)(-)
    # 3. Rests: (z|x)([0-9/]*)
    # 4. Notes: (\^{1,2}|_{1,2}|=)?([a-gA-G])([,']*)([0-9/]*)(-)
    token_re = re.compile(
        r"(\|{1,2}:?|:?\|{1,2}|\[\||\|\])"  # barlines
        r"|\[([a-gA-G\^_,=\s\d/]+)\]([0-9/]*)(-?)"  # chords
        r"|([zxZX])([0-9/]*)"  # rests
        r"|(\^{1,2}|_{1,2}|=)?([a-gA-G])([,']*)([0-9/]*)(-?)"  # single notes
    )

    bar_num = 1
    pos = 0
    note_events: list[dict[str, Any]] = []

    for m in token_re.finditer(full_music):
        if m.group(1):  # Barline
            bar_num += 1
            pos = 0
        elif m.group(2) is not None:  # Chord [CEG]
            chord_content = m.group(2)
            dur_str = m.group(3)
            tie = m.group(4) == "-"
            dur = parse_abc_duration(dur_str, unit_ticks)

            # Extract individual notes in chord
            note_matches = re.findall(r"(\^{1,2}|_{1,2}|=)?[a-gA-G][,']*", chord_content)
            pitches = [abc_pitch_to_midi(n, key=key) for n in note_matches]
            note_events.append({
                "bar": bar_num,
                "position": pos,
                "duration": dur,
                "pitches": pitches,
                "tied": tie,
                "isRest": False,
            })
            pos += dur
        elif m.group(5):  # Rest
            dur_str = m.group(6)
            dur = parse_abc_duration(dur_str, unit_ticks)
            note_events.append({
                "bar": bar_num,
                "position": pos,
                "duration": dur,
                "pitches": [],
                "tied": False,
                "isRest": True,
            })
            pos += dur
        elif m.group(8):  # Single note
            acc = m.group(7) or ""
            letter = m.group(8)
            oct_mod = m.group(9) or ""
            dur_str = m.group(10) or ""
            tie = m.group(11) == "-"
            dur = parse_abc_duration(dur_str, unit_ticks)
            pitch = abc_pitch_to_midi(f"{acc}{letter}{oct_mod}", key=key)
            note_events.append({
                "bar": bar_num,
                "position": pos,
                "duration": dur,
                "pitches": [pitch],
                "tied": tie,
                "isRest": False,
            })
            pos += dur

    # Parse lyrics and align with non-rest note events
    lyric_events: list[dict[str, Any]] = []
    if full_lyrics:
        # Split into words/syllables
        # Words connected by '-' mean middle-of-word syllables
        raw_words = full_lyrics.split()
        syllables: list[tuple[str, str]] = []  # (text, syllable_type)
        for w in raw_words:
            if w == "*":
                syllables.append(("", "skip"))
            elif "-" in w:
                parts = w.split("-")
                for idx, part in enumerate(parts):
                    if part:
                        st = "middle" if idx < len(parts) - 1 else "end"
                        syllables.append((part, st))
            else:
                syllables.append((w, "end"))

        # Align with non-rest notes
        non_rest_notes = [n for n in note_events if not n["isRest"]]
        for syl, note in zip(syllables, non_rest_notes):
            txt, st = syl
            if st != "skip" and txt:
                lyric_events.append({
                    "bar": note["bar"],
                    "position": note["position"],
                    "duration": note["duration"],
                    "text": txt,
                    "syllableType": st,
                })

    return {
        "key": key,
        "meter": meter,
        "notes": note_events,
        "lyrics": lyric_events,
    }
