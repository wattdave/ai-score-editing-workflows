"""Build a staggered-entry playback score from a single-part round."""

from __future__ import annotations

import copy
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from fractions import Fraction


class RoundError(ValueError):
    """The source score cannot be arranged as a round."""


# General MIDI program 53 (1-based) is Choir Aahs.
DEFAULT_PROGRAM = 53
_ENTRY_MARK = re.compile(r"^\s*(\d+)\.\s*$")
_NOTE_TYPES = {
    Fraction(4): ("whole", 0), Fraction(6): ("whole", 1),
    Fraction(2): ("half", 0), Fraction(3): ("half", 1),
    Fraction(1): ("quarter", 0), Fraction(3, 2): ("quarter", 1),
}


@dataclass(frozen=True)
class RoundOptions:
    voices: int | None = None
    gap: int | None = None
    passes: int = 2
    program: int = DEFAULT_PROGRAM
    hold_final: bool = True


@dataclass(frozen=True)
class RoundResult:
    root: ET.Element
    voices: int
    gap: int
    passes: int
    song_bars: int
    total_bars: int

    def as_dict(self) -> dict[str, int]:
        return {
            "voices": self.voices, "gap": self.gap, "passes": self.passes,
            "songBars": self.song_bars, "totalBars": self.total_bars,
        }


def entry_marks(song: list[ET.Element]) -> dict[int, int]:
    """Map each "N." entry mark to the 1-based song bar it sits in."""
    marks: dict[int, int] = {}
    for bar, measure in enumerate(song, start=1):
        for words in measure.findall("direction/direction-type/words"):
            match = _ENTRY_MARK.match(words.text or "")
            if match:
                marks.setdefault(int(match.group(1)), bar)
    return marks


def build_round(source: ET.Element, options: RoundOptions) -> RoundResult:
    """Return a new score with one part per voice, each entering in turn.

    Voice k (from 0) enters at bar 1 + k * gap, sings the song `passes`
    times, then rests until the last voice finishes.
    """
    parts = source.findall("part")
    if len(parts) != 1:
        raise RoundError(f"expected a single-part round, found {len(parts)} parts")
    song = parts[0].findall("measure")
    if not song:
        raise RoundError("source part has no measures")
    _reject_mid_song_attributes(song)

    voices, gap = _layout(song, options)
    if options.passes < 1:
        raise RoundError("passes must be at least 1")
    if not 1 <= options.program <= 128:
        raise RoundError("program must be a General MIDI program from 1 to 128")

    attributes = song[0].find("attributes")
    if attributes is None:
        raise RoundError("first measure has no attributes (divisions, key, time)")
    bar_length = _bar_length(attributes)
    divisions = int(attributes.findtext("divisions"))

    sung = options.passes * len(song)
    total = gap * (voices - 1) + sung
    root, part_list = _empty_score(source)
    for v in range(voices):
        pid = f"P{v + 1}"
        _add_score_part(part_list, pid, v, voices, options.program)
        part = ET.SubElement(root, "part", id=pid)
        start = 1 + gap * v
        for bar in range(1, total + 1):
            offset = bar - start
            if offset < 0 or offset >= sung:
                measure = _rest_measure(bar_length)
            elif offset == sung - 1 and options.hold_final:
                measure = _final_measure(song[-1], bar_length, divisions, fermata=bar == total)
            else:
                measure = _clean(song[offset % len(song)])
            measure.set("number", str(bar))
            if bar == 1:
                measure.insert(0, copy.deepcopy(attributes))
            if bar == total:
                barline = ET.SubElement(measure, "barline", location="right")
                ET.SubElement(barline, "bar-style").text = "light-heavy"
            part.append(measure)

    ET.indent(root)
    return RoundResult(root, voices, gap, options.passes, len(song), total)


def _layout(song: list[ET.Element], options: RoundOptions) -> tuple[int, int]:
    marks = entry_marks(song)
    voices = options.voices if options.voices is not None else (max(marks) if marks else None)
    if voices is None:
        raise RoundError('no "1." "2." entry marks found; pass --voices and --gap')
    if not 1 <= voices <= 15:
        raise RoundError("voices must be from 1 to 15 (one MIDI channel each, skipping drums)")
    gap = options.gap
    if gap is None:
        if 1 not in marks or 2 not in marks:
            raise RoundError('cannot infer --gap without "1." and "2." entry marks')
        gap = marks[2] - marks[1]
    if gap < 1:
        raise RoundError("gap must be at least one bar")
    return voices, gap


def _reject_mid_song_attributes(song: list[ET.Element]) -> None:
    for measure in song[1:]:
        attributes = measure.find("attributes")
        if attributes is not None and any(
            attributes.find(tag) is not None for tag in ("divisions", "key", "time", "clef")
        ):
            number = measure.get("number")
            raise RoundError(f"measure {number} changes key, time, clef or divisions; not supported")


def _bar_length(attributes: ET.Element) -> int:
    divisions = int(attributes.findtext("divisions") or 0)
    beats = attributes.findtext("time/beats")
    beat_type = attributes.findtext("time/beat-type")
    if not divisions or beats is None or beat_type is None:
        raise RoundError("first measure needs divisions and a time signature")
    length = Fraction(divisions * 4 * int(beats), int(beat_type))
    if length.denominator != 1:
        raise RoundError("bar length is not a whole number of divisions")
    return int(length)


def _empty_score(source: ET.Element) -> tuple[ET.Element, ET.Element]:
    root = copy.deepcopy(source)
    for part in root.findall("part"):
        root.remove(part)
    part_list = root.find("part-list")
    if part_list is None:
        raise RoundError("source score has no part-list")
    for child in list(part_list):
        part_list.remove(child)
    for path in ("work/work-title", "movement-title"):
        title = root.find(path)
        if title is not None and title.text:
            title.text = f"{title.text} (round)"
    return root, part_list


def _add_score_part(part_list: ET.Element, pid: str, v: int, voices: int, program: int) -> None:
    score_part = ET.SubElement(part_list, "score-part", id=pid)
    ET.SubElement(score_part, "part-name").text = f"Voice {v + 1}"
    instrument = ET.SubElement(score_part, "score-instrument", id=f"{pid}-I1")
    ET.SubElement(instrument, "instrument-name").text = f"Voice {v + 1}"
    midi = ET.SubElement(score_part, "midi-instrument", id=f"{pid}-I1")
    channel = v + 1 if v < 9 else v + 2  # channel 10 is reserved for drums
    ET.SubElement(midi, "midi-channel").text = str(channel)
    ET.SubElement(midi, "midi-program").text = str(program)
    pan = 0 if voices == 1 else round(-45 + 90 * v / (voices - 1))
    ET.SubElement(midi, "pan").text = str(pan)


def _clean(measure: ET.Element) -> ET.Element:
    """Copy a song bar without its attributes, entry marks, barlines or fermatas."""
    result = copy.deepcopy(measure)
    for child in list(result):
        if child.tag in ("attributes", "barline", "print"):
            result.remove(child)
        elif child.tag == "direction" and _is_entry_mark(child):
            result.remove(child)
    for notations in result.iter("notations"):
        for fermata in notations.findall("fermata"):
            notations.remove(fermata)
    return result


def _is_entry_mark(direction: ET.Element) -> bool:
    words = direction.findall("direction-type/words")
    return bool(words) and all(_ENTRY_MARK.match(w.text or "") for w in words)


def _rest_measure(bar_length: int) -> ET.Element:
    measure = ET.Element("measure")
    note = ET.SubElement(measure, "note")
    ET.SubElement(note, "rest", measure="yes")
    ET.SubElement(note, "duration").text = str(bar_length)
    ET.SubElement(note, "voice").text = "1"
    return measure


def _final_measure(last: ET.Element, bar_length: int, divisions: int, *, fermata: bool) -> ET.Element:
    """Hold the last bar's first note for the whole bar, dropping any pickup.

    The pickup leads into another verse; a voice's final pass has none. If
    the whole-bar value has no single note type, the bar is kept as written.
    """
    measure = _clean(last)
    notes = [n for n in measure.findall("note") if n.find("chord") is None]
    held = _NOTE_TYPES.get(Fraction(bar_length, divisions))
    if notes and held is not None and notes[0].find("rest") is None:
        _hold(measure, notes[0], bar_length, held)
        for note in notes[1:]:
            _remove_with_chord(measure, note)
    if fermata and notes:
        notations = notes[0].find("notations")
        if notations is None:
            notations = ET.SubElement(notes[0], "notations")
        ET.SubElement(notations, "fermata", type="upright")
    return measure


def _hold(measure: ET.Element, first: ET.Element, bar_length: int, held: tuple[str, int]) -> None:
    note_type, dots = held
    chord_tones = _chord_tones(measure, first)
    for note in [first, *chord_tones]:
        duration = note.find("duration")
        if duration is None:
            raise RoundError("final note has no duration")
        duration.text = str(bar_length)
        type_element = note.find("type")
        if type_element is not None:
            type_element.text = note_type
        for dot in note.findall("dot"):
            note.remove(dot)
        index = list(note).index(type_element) + 1 if type_element is not None else len(note)
        for _ in range(dots):
            note.insert(index, ET.Element("dot"))
        for tag in ("stem", "beam"):
            for element in note.findall(tag):
                note.remove(element)


def _chord_tones(measure: ET.Element, first: ET.Element) -> list[ET.Element]:
    children = list(measure)
    tones = []
    for child in children[children.index(first) + 1:]:
        if child.tag != "note":
            continue
        if child.find("chord") is None:
            break
        tones.append(child)
    return tones


def _remove_with_chord(measure: ET.Element, note: ET.Element) -> None:
    for tone in _chord_tones(measure, note):
        measure.remove(tone)
    measure.remove(note)
