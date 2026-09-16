#!/usr/bin/env python3
"""Conservatively repair invalid durations in Audiveris MusicXML output.

OMR can occasionally emit a duplicate note or a too-long measure rest.  This
tool repairs only two unambiguous cases: a measure rest longer than its meter,
and an immediately repeated pitch whose duration exactly equals a voice's
overrun.  Every applied repair is printed for score-review traceability.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from xml.etree import ElementTree as ET

from musicxml_to_abc import read_musicxml


def note_pitch(note: ET.Element) -> tuple[str, str, str] | None:
    pitch = note.find("pitch")
    if pitch is None:
        return None
    return (
        pitch.findtext("step", ""),
        pitch.findtext("alter", "0"),
        pitch.findtext("octave", ""),
    )


def sanitize(root: ET.Element) -> list[str]:
    repairs: list[str] = []
    for part in root.findall("part"):
        divisions, beats, beat_type = 1, 4, 4
        for measure in part.findall("measure"):
            attributes = measure.find("attributes")
            if attributes is not None:
                divisions = int(attributes.findtext("divisions", str(divisions)))
                beats = int(attributes.findtext("time/beats", str(beats)))
                beat_type = int(attributes.findtext("time/beat-type", str(beat_type)))
            expected = divisions * beats * 4 // beat_type
            by_voice: dict[str, list[ET.Element]] = {}
            for note in measure.findall("note"):
                if note.find("chord") is None:
                    by_voice.setdefault(note.findtext("voice", "1"), []).append(note)
            for voice, notes in by_voice.items():
                total = sum(int(note.findtext("duration", "0")) for note in notes)
                if total <= expected:
                    continue
                excess = total - expected
                if len(notes) == 1 and notes[0].find("rest[@measure='yes']") is not None:
                    notes[0].find("duration").text = str(expected)
                    repairs.append(f"{part.get('id')} bar {measure.get('number')} voice {voice}: clamped measure rest by {excess}")
                    continue
                for index, note in enumerate(notes[:-1]):
                    following = notes[index + 1]
                    if (
                        int(note.findtext("duration", "0")) == excess
                        and note_pitch(note) is not None
                        and note_pitch(note) == note_pitch(following)
                    ):
                        measure.remove(note)
                        repairs.append(f"{part.get('id')} bar {measure.get('number')} voice {voice}: removed duplicate {note_pitch(note)[0]} event of {excess}")
                        break
                else:
                    raise ValueError(
                        f"Cannot safely repair {part.get('id')} bar {measure.get('number')} "
                        f"voice {voice}: duration {total} exceeds expected {expected}."
                    )
    return repairs


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    root = read_musicxml(args.input)
    for repair in sanitize(root):
        print(repair)
    ET.indent(root, space="  ")
    ET.ElementTree(root).write(args.output, encoding="utf-8", xml_declaration=True)


if __name__ == "__main__":
    main()
