#!/usr/bin/env python3
"""Write a conservative, importer-safe MusicXML score from Audiveris output.

Audiveris emits layout-oriented MusicXML which can include malformed backup
positions and secondary voices.  This tool keeps the primary voice of every
recognized part, writes sequential measures with explicit rests, and leaves
the original OMR file untouched.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from xml.etree import ElementTree as ET

from musicxml_to_abc import read_musicxml


PART_NAMES = ("Soprano I", "Soprano II", "Alto I", "Alto II", "Tenor", "Bass")
LYRICS = (
    "Oh fare you well, my own true love, and leave you for a while.\n"
    "Where-ever I go, I will return, if I go ten thousand miles.\n"
    "Ten thousand miles it is so far to leave me here alone.\n"
    "Well, I may lie, lament and cry, and you'll not hear my mourn.\n"
    "Oh don't you see that lonesome dove upon an ivy tree.\n"
    "She's weeping for her own true love, just as I shall weep for mine.\n"
    "The rivers never will run dry, nor rocks melt with the sun.\n"
    "I'll never prove false to the one I love, till all these things be done."
)


def text(parent: ET.Element, tag: str, value: str) -> ET.Element:
    child = ET.SubElement(parent, tag)
    child.text = value
    return child


def source_events(measure: ET.Element, target_voice: str = "1") -> list[tuple[int, int, list[ET.Element]]]:
    """Return primary-voice events as (offset, duration, note/chord tones)."""
    cursor = 0
    events: list[tuple[int, int, list[ET.Element]]] = []
    for child in measure:
        if child.tag == "backup":
            cursor -= int(child.findtext("duration", "0"))
        elif child.tag == "forward":
            cursor += int(child.findtext("duration", "0"))
        elif child.tag == "note":
            duration = int(child.findtext("duration", "0"))
            is_chord = child.find("chord") is not None
            if child.findtext("voice", "1") == target_voice:
                if is_chord and events:
                    events[-1][2].append(child)
                else:
                    events.append((cursor, duration, [child]))
            # All voices occupy time in the source stream.  In particular,
            # when extracting voice 2, advance through voice 1 before the
            # source's <backup> returns the cursor to the start of the bar.
            if not is_chord:
                cursor += duration
    return sorted(events, key=lambda event: event[0])


def append_rest(measure: ET.Element, duration: int, voice: str = "1") -> None:
    note = ET.SubElement(measure, "note")
    ET.SubElement(note, "rest")
    text(note, "duration", str(duration))
    text(note, "voice", voice)


def append_note(
    measure: ET.Element,
    duration: int,
    tones: list[ET.Element],
    scale: int,
    voice: str = "1",
    octave_shift: int = 0,
) -> None:
    for index, source_note in enumerate(tones):
        note = ET.SubElement(measure, "note")
        if index:
            ET.SubElement(note, "chord")
        source_pitch = source_note.find("pitch")
        if source_pitch is None:
            ET.SubElement(note, "rest")
        else:
            pitch = ET.SubElement(note, "pitch")
            for name in ("step", "alter", "octave"):
                value = source_pitch.findtext(name)
                if value is not None and name == "octave":
                    value = str(int(value) + octave_shift)
                if value is not None:
                    text(pitch, name, value)
        text(note, "duration", str(duration * scale))
        text(note, "voice", voice)


def literal_tone(step: str, octave: int, alter: int | None = None) -> ET.Element:
    """Create a minimal source-like note for a manually verified pitch."""
    note = ET.Element("note")
    pitch = ET.SubElement(note, "pitch")
    text(pitch, "step", step)
    if alter is not None:
        text(pitch, "alter", str(alter))
    text(pitch, "octave", str(octave))
    return note


def normalize(root: ET.Element) -> ET.Element:
    output = ET.Element("score-partwise", version="4.0")
    work = ET.SubElement(output, "work")
    text(work, "work-title", "10,000 Miles")
    text(output, "movement-title", "10,000 Miles")
    identification = ET.SubElement(output, "identification")
    creator = text(identification, "creator", "arr. SK")
    creator.set("type", "arranger")
    title_credit = ET.SubElement(output, "credit", page="1")
    title_words = ET.SubElement(
        title_credit,
        "credit-words",
        {"default-x": "830", "default-y": "1880", "justify": "center", "halign": "center"},
    )
    title_words.set("font-size", "24")
    title_words.text = "10,000 Miles"
    part_list = ET.SubElement(output, "part-list")
    source_parts = root.findall("part")
    for index, _ in enumerate(source_parts, 1):
        score_part = ET.SubElement(part_list, "score-part", id=f"P{index}")
        name = PART_NAMES[index - 1] if index <= len(PART_NAMES) else f"OMR Voice {index}"
        text(score_part, "part-name", name)
        text(score_part, "part-abbreviation", name.replace("Soprano", "S.").replace("Alto", "A.").replace("Tenor", "T.").replace("Bass", "B."))

    for part_index, source_part in enumerate(source_parts, 1):
        result_part = ET.SubElement(output, "part", id=f"P{part_index}")
        source_divisions, beats, beat_type = 1, 4, 4
        for measure_index, source_measure in enumerate(source_part.findall("measure")):
            result_measure = ET.SubElement(result_part, "measure", number=str(measure_index))
            if measure_index == 0:
                result_measure.set("implicit", "yes")
            attributes = source_measure.find("attributes")
            if attributes is not None:
                source_divisions = int(attributes.findtext("divisions", str(source_divisions)))
                beats = int(attributes.findtext("time/beats", str(beats)))
                beat_type = int(attributes.findtext("time/beat-type", str(beat_type)))
            # Six divisions per quarter preserves both ordinary notes and the
            # triplet-like durations emitted by Audiveris.
            scale = 6 // source_divisions if 6 % source_divisions == 0 else 6
            expected = source_divisions * beats * 4 // beat_type
            if measure_index == 0 or attributes is not None:
                out_attributes = ET.SubElement(result_measure, "attributes")
                text(out_attributes, "divisions", str(source_divisions * scale))
                key = ET.SubElement(out_attributes, "key")
                text(key, "fifths", "1")
                meter = ET.SubElement(out_attributes, "time")
                text(meter, "beats", str(beats))
                text(meter, "beat-type", str(beat_type))
                clef = ET.SubElement(out_attributes, "clef")
                if part_index == len(source_parts):
                    text(clef, "sign", "F")
                    text(clef, "line", "4")
                else:
                    text(clef, "sign", "G")
                    text(clef, "line", "2")
                    if part_index == len(source_parts) - 1:
                        text(clef, "clef-octave-change", "-1")

            reassigned_upper_block = 20 <= measure_index <= 26
            tenor_divisi_block = 33 <= measure_index <= 38
            bass_divisi_block = 40 <= measure_index <= 45
            final_soprano_block = measure_index >= 53
            # In bars 20–26, Audiveris assigned the four singing upper
            # parts two staves too low: P3/P4/P5/P6 are S1/S2/A1/A2.
            if final_soprano_block and part_index == 1:
                primary_events = source_events(
                    source_parts[1].findall("measure")[measure_index]
                )
            elif final_soprano_block and part_index == 2:
                primary_events = source_events(
                    source_parts[2].findall("measure")[measure_index]
                )
            elif final_soprano_block and part_index == 3:
                primary_events = []
            elif bass_divisi_block and part_index in (3, 4):
                primary_events = []
            elif bass_divisi_block and part_index == 5:
                # Former A1 is Tenor I.
                primary_events = source_events(
                    source_parts[2].findall("measure")[measure_index]
                )
            elif bass_divisi_block and part_index == 6:
                # Former Tenor is Bass I.
                primary_events = source_events(
                    source_parts[4].findall("measure")[measure_index]
                )
            elif tenor_divisi_block and part_index == 3:
                # A1 moves to A2 in this passage.
                primary_events = []
                if measure_index == 38:
                    # The original engraves this extra A1 phrase on the A2
                    # staff.  Restore it as independent A1 material:
                    # ABC (L:1/8) = D2 E2 ^F4.
                    primary_events = [
                        (0, 2, [literal_tone("D", 4)]),
                        (2, 2, [literal_tone("E", 4)]),
                        (4, 4, [literal_tone("F", 4, alter=1)]),
                    ]
            elif tenor_divisi_block and part_index == 4:
                primary_events = source_events(
                    source_parts[2].findall("measure")[measure_index]
                )
            elif reassigned_upper_block and part_index <= 4:
                primary_events = source_events(
                    source_parts[part_index + 1].findall("measure")[measure_index]
                )
            elif reassigned_upper_block:
                primary_events = []
            # The OMR split the Soprano II line into Alto I for bars 9–12.
            # Restore it to the otherwise-resting S2 staff and leave Alto I
            # silent there.  (The two Alto parts resume their normal roles
            # in bar 13.)
            elif part_index == 2 and 9 <= measure_index <= 12:
                primary_events = source_events(
                    source_parts[2].findall("measure")[measure_index]
                )
            elif part_index == 3 and 9 <= measure_index <= 12:
                primary_events = []
            else:
                primary_events = source_events(source_measure)
            if part_index == 3 and measure_index == 13:
                # The OMR shortened A1's opening G and started the G–F#
                # eighth-note pair two beats early.  The printed rhythm is
                # G for beats 1–3, then G–F# on beat 4.
                opening, first_eighth, second_eighth = primary_events[:3]
                primary_events = [
                    (0, 6, opening[2]),
                    (6, 1, first_eighth[2]),
                    (7, 1, second_eighth[2]),
                ]
            if part_index == 4 and measure_index == 15:
                # A2's final eighth is a pickup on the second half of beat
                # 4, not an attack on beat 4 itself.
                first, pickup, *following = primary_events
                primary_events = [first, (7, pickup[1], pickup[2]), *following]
            if part_index == 4 and measure_index == 30:
                # A2 repeats D as an eighth-note pickup on the second half
                # of beat 4 after the three-beat opening D.
                pickup_d = source_events(
                    source_parts[2].findall("measure")[measure_index]
                )[0]
                primary_events = [
                    *primary_events[:-1],
                    (7, 1, pickup_d[2]),
                ]
            if measure_index == 39:
                # Manually verified from the score.  Durations are expressed
                # in ABC L:1/8 units, converted for this measure's active
                # MusicXML divisions.
                eighth = source_divisions // 2
                if part_index == 2:  # S2: z8
                    primary_events = []
                elif part_index == 3:  # A1: ^F4 z4
                    primary_events = [(0, 4 * eighth, [literal_tone("F", 4, alter=1)])]
                elif part_index == 4:  # A2: B,4 z4
                    primary_events = [(0, 4 * eighth, [literal_tone("B", 3)])]
                elif part_index == 5:  # T1: d4 z2 D2
                    primary_events = [
                        (0, 4 * eighth, [literal_tone("D", 4)]),
                        (6 * eighth, 2 * eighth, [literal_tone("D", 3)]),
                    ]
            if part_index == 2 and measure_index == 45:
                # The apparent S2 pickup belongs to A2 instead.
                primary_events = []
            elif part_index == 4 and measure_index == 45:
                # A2's D pickup is an eighth on the second half of beat 4.
                eighth = source_divisions // 2
                primary_events = [
                    (expected - eighth, eighth, [literal_tone("D", 4)])
                ]
            elif part_index == 5 and measure_index == 47:
                # The tenor pickup begins on the second half of beat 4, not
                # on the beat itself.
                leading_rest, pickup, *following = primary_events
                primary_events = [
                    leading_rest,
                    (
                        pickup[0] + source_divisions // 2,
                        pickup[1],
                        pickup[2],
                    ),
                    *following,
                ]
            if part_index == 6 and measure_index == 57:
                # Both basses take G–D as eighths on beat 4.
                eighth = source_divisions // 2
                primary_events = [
                    (0, expected - 2 * eighth, [literal_tone("G", 3)]),
                    (expected - 2 * eighth, eighth, [literal_tone("G", 2)]),
                    (expected - eighth, eighth, [literal_tone("D", 3)]),
                ]
            if part_index == len(source_parts) and measure_index == 12:
                # PDF review: both bass voices share the G-D eighth-note
                # figure on beat 4. Audiveris assigned it only to voice 2.
                primary_events.extend(source_events(source_measure, "2")[1:])
                primary_events.sort(key=lambda event: event[0])

            cursor = 0
            for offset, duration, tones in primary_events:
                # PDF review: the first Tenor B is a pickup on the second
                # half of beat 4 in bar 2, not on beat 4 itself.
                if part_index == len(source_parts) - 1 and measure_index == 2 and tones[0].find("pitch") is not None:
                    offset += 1
                if offset > cursor:
                    append_rest(result_measure, (offset - cursor) * scale)
                    cursor = offset
                if offset < cursor:
                    # OMR overlap in a single primary voice: omit the later
                    # duplicate rather than inventing a polyphonic placement.
                    continue
                duration = min(duration, expected - cursor)
                if duration <= 0:
                    continue
                # Measures 13–15 and 31–39 already carry the tenor's
                # intended register in the OMR pitch data. Applying the
                # usual tenor-octave normalization there makes them sound
                # an octave too low.
                tenor_shift = -1 if (
                    part_index == len(source_parts) - 1
                    and measure_index not in (*range(13, 16), *range(31, 40))
                ) else 0
                octave_shift = tenor_shift
                if bass_divisi_block and part_index in (5, 6):
                    # In this divisi passage the two tenor lines and the
                    # lower bass line retain their source octave.
                    octave_shift = 0
                append_note(
                    result_measure,
                    duration,
                    tones,
                    scale,
                    octave_shift=octave_shift,
                )
                cursor += duration
            # Measure 0 is the printed one-eighth anacrusis. Filling it to a
            # full bar was the source of the wrong pickup in the first import.
            if measure_index != 0 and cursor < expected:
                append_rest(result_measure, (expected - cursor) * scale)

            # The source has short Tenor and Bass divisi passages. Preserve
            # their second voices within the existing lower staves; secondary
            # voices elsewhere are OMR artifacts.
            if part_index >= len(source_parts) - 1:
                if part_index == 6 and measure_index == 56:
                    # Bass II: ABC C2 D2 E2 ^F2.
                    quarter = source_divisions
                    lower_two = [
                        (0, quarter, [literal_tone("C", 3)]),
                        (quarter, quarter, [literal_tone("D", 3)]),
                        (2 * quarter, quarter, [literal_tone("E", 3)]),
                        (3 * quarter, quarter, [literal_tone("F", 3, alter=1)]),
                    ]
                elif bass_divisi_block and part_index == 5:
                    # Former A2 is Tenor II.
                    lower_two = source_events(
                        source_parts[3].findall("measure")[measure_index]
                    )
                elif bass_divisi_block and part_index == 6:
                    # Former Bass is Bass II.
                    lower_two = source_events(
                        source_parts[5].findall("measure")[measure_index]
                    )
                elif measure_index == 39 and part_index == 5:
                    # T2: ^F4 z2 D2
                    eighth = source_divisions // 2
                    lower_two = [
                        (0, 4 * eighth, [literal_tone("F", 3, alter=1)]),
                        (6 * eighth, 2 * eighth, [literal_tone("D", 3)]),
                    ]
                elif tenor_divisi_block and part_index == 5:
                    # The former A2 line is Tenor II.  Preserve it as a
                    # separate voice beneath the existing Tenor I line.
                    lower_two = source_events(
                        source_parts[3].findall("measure")[measure_index]
                    )
                elif reassigned_upper_block:
                    lower_two = []
                else:
                    lower_two = source_events(source_measure, "2")
                if lower_two:
                    backup = ET.SubElement(result_measure, "backup")
                    text(backup, "duration", str((cursor if measure_index == 0 else expected) * scale))
                    bass_cursor = 0
                    for offset, duration, tones in lower_two:
                        if offset > bass_cursor:
                            append_rest(result_measure, (offset - bass_cursor) * scale, voice="2")
                            bass_cursor = offset
                        if offset < bass_cursor:
                            continue
                        duration = min(duration, expected - bass_cursor)
                        if duration <= 0:
                            continue
                        append_note(
                            result_measure,
                            duration,
                            tones,
                            scale,
                            voice="2",
                            # The imported A2 material becomes Tenor II in
                            # bars 33–38, so lower its written pitch to the
                            # tenor register while retaining the 8vb clef.
                            octave_shift=-1 if (
                                part_index == 5
                                and tenor_divisi_block
                            ) else 0,
                        )
                        bass_cursor += duration
                    if measure_index != 0 and bass_cursor < expected:
                        append_rest(result_measure, (expected - bass_cursor) * scale, voice="2")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    output = normalize(read_musicxml(args.input))
    ET.indent(output, space="  ")
    ET.ElementTree(output).write(args.output, encoding="utf-8", xml_declaration=True)


if __name__ == "__main__":
    main()
