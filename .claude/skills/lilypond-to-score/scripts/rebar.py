"""Rebuild the bars of a single-voice-per-part MusicXML file.

python-ly closes measures at bar checks and never splits a note that crosses
a barline, so its measures come out the wrong length. This pours each part's
notes into bars of the given time signature, splitting any note that crosses
a barline into tied notes. Ties already in the input are merged first, so a
tied pair is one attack, not two.

usage: rebar.py IN.xml OUT.xml BEATS BEAT_TYPE [PART=CLEF ...]
CLEF is treble, treble8 (treble sounding an octave lower) or bass.

Only plain notes and rests are supported: no chords, tuplets or grace notes.
"""

from __future__ import annotations

import copy
import sys
import xml.etree.ElementTree as ET

CLEFS = {"treble": ("G", "2", None), "treble8": ("G", "2", "-1"), "bass": ("F", "4", None)}
# Duration in 16ths -> (type name, dotted)
NOTE_TYPES = {32: ("breve", False), 24: ("whole", True), 16: ("whole", False), 12: ("half", True),
              8: ("half", False), 6: ("quarter", True), 4: ("quarter", False), 3: ("eighth", True),
              2: ("eighth", False), 1: ("16th", False)}


def text(el: ET.Element, path: str) -> str:
    value = el.findtext(path)
    if value is None:
        raise SystemExit(f"missing <{path}>")
    return value


def split_units(units: int) -> list[int]:
    """Break a length in 16ths into notatable values, longest first."""
    out = []
    for size in NOTE_TYPES:
        while units >= size:
            out.append(size)
            units -= size
    return out


def read_events(part: ET.Element) -> tuple[list[tuple[int, ET.Element | None]], ET.Element]:
    """Return ([(length in 16ths, pitch or None for a rest)], first <attributes>)."""
    measures = part.findall("measure")
    attrs = measures[0].find("attributes")
    if attrs is None:
        raise SystemExit(f"part {part.get('id')}: first measure has no <attributes>")
    divisions = int(text(attrs, "divisions"))
    events: list[tuple[int, ET.Element | None]] = []
    tied = False
    for measure in measures:
        for note in measure.findall("note"):
            if note.find("chord") is not None or note.find("grace") is not None:
                raise SystemExit(f"part {part.get('id')}: chords and grace notes are not supported")
            units, rem = divmod(int(text(note, "duration")) * 4, divisions)
            if rem:
                raise SystemExit(f"part {part.get('id')}: duration finer than a 16th (tuplet?)")
            pitch = note.find("pitch")
            if tied and pitch is not None:
                events[-1] = (events[-1][0] + units, events[-1][1])
            else:
                events.append((units, pitch))
            tied = any(t.get("type") == "start" for t in note.iter("tie")) or any(
                t.get("type") == "start" for t in note.iter("tied"))
        part.remove(measure)
    return events, attrs


def first_attributes(attrs: ET.Element, beats: int, beat_type: int, clef: str | None) -> ET.Element:
    new = copy.deepcopy(attrs)
    divisions = new.find("divisions")
    if divisions is not None:
        divisions.text = "4"
    time = new.find("time")
    if time is None:
        time = ET.SubElement(new, "time")
    for child in list(time):
        time.remove(child)
    ET.SubElement(time, "beats").text = str(beats)
    ET.SubElement(time, "beat-type").text = str(beat_type)
    if clef:
        sign, line, octave = CLEFS[clef]
        for old in new.findall("clef"):
            new.remove(old)
        el = ET.SubElement(new, "clef")
        ET.SubElement(el, "sign").text = sign
        ET.SubElement(el, "line").text = line
        if octave:
            ET.SubElement(el, "clef-octave-change").text = octave
    return new


def add_note(measure: ET.Element, size: int, pitch: ET.Element | None, tie_in: bool, tie_out: bool) -> None:
    note = ET.SubElement(measure, "note")
    if pitch is None:
        ET.SubElement(note, "rest")
    else:
        note.append(copy.deepcopy(pitch))
    ET.SubElement(note, "duration").text = str(size)
    if pitch is not None:
        if tie_in:
            ET.SubElement(note, "tie", type="stop")
        if tie_out:
            ET.SubElement(note, "tie", type="start")
    name, dotted = NOTE_TYPES[size]
    ET.SubElement(note, "type").text = name
    if dotted:
        ET.SubElement(note, "dot")
    if pitch is not None and (tie_in or tie_out):
        notations = ET.SubElement(note, "notations")
        if tie_in:
            ET.SubElement(notations, "tied", type="stop")
        if tie_out:
            ET.SubElement(notations, "tied", type="start")


def rebar_part(part: ET.Element, beats: int, beat_type: int, clef: str | None) -> int:
    events, attrs = read_events(part)
    bar = beats * 16 // beat_type
    measures: list[ET.Element] = []
    fill = bar  # force a new measure first

    for units, pitch in events:
        pieces: list[tuple[int, bool]] = []  # (size, starts a new measure)
        for_measure = fill
        while units:
            if for_measure == bar:
                pieces.append((0, True))
                for_measure = 0
            take = min(units, bar - for_measure)
            pieces.extend((size, False) for size in split_units(take))
            units -= take
            for_measure += take
        sounding = [p for p in pieces if not p[1]]
        index = 0
        for size, new_bar in pieces:
            if new_bar:
                measure = ET.SubElement(part, "measure", number=str(len(measures) + 1))
                if not measures:
                    measure.append(first_attributes(attrs, beats, beat_type, clef))
                measures.append(measure)
                fill = 0
                continue
            add_note(measures[-1], size, pitch, index > 0, index < len(sounding) - 1)
            index += 1
            fill += size
    if fill and fill < bar:
        print(f"warning: part {part.get('id')}: last bar is {fill} of {bar} 16ths long", file=sys.stderr)
    return len(measures)


def main() -> None:
    if len(sys.argv) < 5:
        raise SystemExit(__doc__)
    src, dst, beats, beat_type = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
    clefs = dict(arg.split("=", 1) for arg in sys.argv[5:])
    tree = ET.parse(src)
    for part in tree.getroot().iter("part"):
        count = rebar_part(part, beats, beat_type, clefs.get(part.get("id") or ""))
        print(f"{part.get('id')}: {count} bars of {beats}/{beat_type}")
    tree.write(dst, encoding="UTF-8", xml_declaration=True)


if __name__ == "__main__":
    main()
