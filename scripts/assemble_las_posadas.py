#!/usr/bin/env python3
"""Assemble Las Posadas into a publication-ready 5-staff score.

Splits Soprano and Alto into discrete staves:
1. Soprano (Treble)
2. Alto (Treble)
3. Bass (Bass)
4. Guitar (Treble with chord symbols)
5. String Bass (Bass)

Prunes Halbestunde's 289 dummy measures (48-336) and maps measures 337-354
to measures 48-65, correcting all pitch, metric, and engraving defects
against the original PDF ground truth.
"""

from __future__ import annotations

import copy
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


SEMITONES = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def get_midi(note: ET.Element) -> int:
    p = note.find("pitch")
    if p is None:
        return -1
    step = p.findtext("step")
    octave = int(float(p.findtext("octave", 0)))
    alter = int(float(p.findtext("alter", 0)))
    return 12 * (octave + 1) + SEMITONES.get(step, 0) + alter


def make_pitch_note(
    step: str,
    octave: int,
    dur: int,
    note_type: str,
    alter: int = 0,
    is_dotted: bool = False,
    voice: str = "1",
    tie: str | None = None,
    accent: bool = False,
    fermata: bool = False,
) -> ET.Element:
    n = ET.Element("note")
    p = ET.SubElement(n, "pitch")
    ET.SubElement(p, "step").text = step
    if alter != 0:
        ET.SubElement(p, "alter").text = str(alter)
    ET.SubElement(p, "octave").text = str(octave)
    ET.SubElement(n, "duration").text = str(dur)
    if tie in ("stop", "both"):
        ET.SubElement(n, "tie", type="stop")
    if tie in ("start", "both"):
        ET.SubElement(n, "tie", type="start")
    ET.SubElement(n, "voice").text = voice
    ET.SubElement(n, "type").text = note_type
    if is_dotted:
        ET.SubElement(n, "dot")
    if accent or tie or fermata:
        notations = ET.SubElement(n, "notations")
        if tie in ("stop", "both"):
            ET.SubElement(notations, "tied", type="stop")
        if tie in ("start", "both"):
            ET.SubElement(notations, "tied", type="start")
        if accent:
            articulations = ET.SubElement(notations, "articulations")
            ET.SubElement(articulations, "accent")
        if fermata:
            ET.SubElement(notations, "fermata", type="upright")
    return n


def make_rest_note(
    dur: int,
    note_type: str | None = None,
    voice: str = "1",
    measure_rest: bool = False,
) -> ET.Element:
    n = ET.Element("note")
    r = ET.SubElement(n, "rest")
    if measure_rest:
        r.attrib["measure"] = "yes"
    ET.SubElement(n, "duration").text = str(dur)
    ET.SubElement(n, "voice").text = voice
    if note_type:
        ET.SubElement(n, "type").text = note_type
    return n


def clean_note_element(note: ET.Element, voice: str = "1") -> ET.Element:
    n = copy.deepcopy(note)
    for tag in ("staff", "chord", "stem"):
        el = n.find(tag)
        if el is not None:
            n.remove(el)
    v = n.find("voice")
    if v is not None:
        v.text = voice
    else:
        v = ET.SubElement(n, "voice")
        v.text = voice
    return n


def add_lyric(note: ET.Element, text: str, syllabic: str = "single", number: str = "1", name: str | None = None, print_object: str | None = None) -> None:
    attribs = {"number": number}
    if name:
        attribs["name"] = name
    if print_object:
        attribs["print-object"] = print_object
    lyr = ET.SubElement(note, "lyric", **attribs)
    ET.SubElement(lyr, "syllabic").text = syllabic
    ET.SubElement(lyr, "text").text = text


def make_harmony(root_step: str, kind: str, bass_step: str | None = None) -> ET.Element:
    h = ET.Element("harmony")
    r = ET.SubElement(h, "root")
    ET.SubElement(r, "root-step").text = root_step
    ET.SubElement(h, "kind").text = kind
    if bass_step:
        b = ET.SubElement(h, "bass")
        ET.SubElement(b, "bass-step").text = bass_step
    return h


def build_las_posadas_score(in_xml: Path, out_xml: Path) -> None:
    tree = ET.parse(in_xml)
    root = tree.getroot()

    orig_parts = {p.get("id"): p for p in root.findall("part")}

    new_root = ET.Element("score-partwise", version="3.1")
    new_root.append(copy.deepcopy(root.find("work")) if root.find("work") is not None else ET.Element("work"))
    
    # Metadata
    work = new_root.find("work")
    if work is not None:
        wt = work.find("work-title")
        if wt is None:
            wt = ET.SubElement(work, "work-title")
        wt.text = '"Las Posadas" Spanish Carol Medley'

    # Identification
    ident = ET.SubElement(new_root, "identification")
    creator_arr = ET.SubElement(ident, "creator", type="arranger")
    creator_arr.text = "Joel Jacklich"
    creator_comp = ET.SubElement(ident, "creator", type="composer")
    creator_comp.text = "Traditional Spanish Carols"
    rights = ET.SubElement(ident, "rights")
    rights.text = "© 1992, Joel Jacklich"
    encoding = ET.SubElement(ident, "encoding")
    ET.SubElement(encoding, "software").text = "Antigravity OMR Repair & Assembly"

    # Part List: 5 Staves
    part_list = ET.SubElement(new_root, "part-list")

    part_defs = [
        ("P1", "Soprano", "S.", "voice.soprano", 1, 53),
        ("P2", "Alto", "A.", "voice.alto", 2, 53),
        ("P3", "Bass", "B.", "voice.bass", 3, 53),
        ("P4", "Guitar", "Gtr.", "pluck.guitar.nylon-string", 4, 25),
        ("P5", "String Bass", "St. B.", "strings.contrabass", 5, 44),
    ]

    for pid, name, abbr, sound_id, ch, prog in part_defs:
        sp = ET.SubElement(part_list, "score-part", id=pid)
        ET.SubElement(sp, "part-name").text = name
        ET.SubElement(sp, "part-abbreviation").text = abbr
        si = ET.SubElement(sp, "score-instrument", id=f"{pid}-I1")
        ET.SubElement(si, "instrument-name").text = name
        ET.SubElement(sp, "midi-device", id=f"{pid}-I1", port="1")
        mi = ET.SubElement(sp, "midi-instrument", id=f"{pid}-I1")
        ET.SubElement(mi, "midi-channel").text = str(ch)
        ET.SubElement(mi, "midi-program").text = str(prog)
        ET.SubElement(mi, "volume").text = "78.7402"
        ET.SubElement(mi, "pan").text = "0"

    # Create target parts
    target_parts = {pid: ET.SubElement(new_root, "part", id=pid) for pid, _, _, _, _, _ in part_defs}

    def get_orig_measure(pid: str, bar_num: int) -> ET.Element | None:
        xml_bar = bar_num if bar_num <= 47 else (bar_num - 48 + 337)
        return orig_parts[pid].find(f"measure[@number='{xml_bar}']")

    # Layout breaks: Omitted hardcoded <print> elements so Sibelius calculates clean 5-staff page layouts without collisions
    # Iterate through all 65 measures
    for bar_num in range(1, 66):
        # Create measure container in each target part
        t_measures = {pid: ET.SubElement(target_parts[pid], "measure", number=str(bar_num)) for pid in target_parts}

        # Attributes: Key, Time, Divisions, Clefs
        attrs = ET.Element("attributes")
        if bar_num == 1:
            ET.SubElement(attrs, "divisions").text = "4"
            key = ET.SubElement(attrs, "key")
            ET.SubElement(key, "fifths").text = "2"
            time = ET.SubElement(attrs, "time")
            ET.SubElement(time, "beats").text = "3"
            ET.SubElement(time, "beat-type").text = "4"

            clef_defs = {"P1": ("G", "2"), "P2": ("G", "2"), "P3": ("F", "4"), "P4": ("G", "2"), "P5": ("F", "4")}
            for pid, (sign, line) in clef_defs.items():
                m_attr = copy.deepcopy(attrs)
                clef = ET.SubElement(m_attr, "clef")
                ET.SubElement(clef, "sign").text = sign
                ET.SubElement(clef, "line").text = line
                t_measures[pid].append(m_attr)
        else:
            has_time_change = False
            time = ET.Element("time")
            if bar_num == 37:
                ET.SubElement(time, "beats").text = "2"
                ET.SubElement(time, "beat-type").text = "4"
                has_time_change = True
            elif bar_num == 44:
                ET.SubElement(time, "beats").text = "6"
                ET.SubElement(time, "beat-type").text = "8"
                has_time_change = True
            elif bar_num == 48:
                ET.SubElement(time, "beats").text = "6"
                ET.SubElement(time, "beat-type").text = "8"
                has_time_change = True
            elif bar_num == 49:
                ET.SubElement(time, "beats").text = "2"
                ET.SubElement(time, "beat-type").text = "4"
                has_time_change = True

            if has_time_change:
                attrs.append(time)
                for pid in target_parts:
                    t_measures[pid].append(copy.deepcopy(attrs))

        # Repeat & Ending Barlines
        def apply_barline(loc: str, style: str | None = None, repeat_dir: str | None = None, ending_num: str | None = None, ending_type: str | None = None):
            bl = ET.Element("barline", location=loc)
            if style:
                ET.SubElement(bl, "bar-style").text = style
            if ending_num and ending_type:
                ET.SubElement(bl, "ending", number=ending_num, type=ending_type)
            if repeat_dir:
                ET.SubElement(bl, "repeat", direction=repeat_dir)
            for pid in target_parts:
                t_measures[pid].append(copy.deepcopy(bl))

        if bar_num == 36:
            apply_barline(loc="right", style="light-heavy", repeat_dir="backward")
        elif bar_num == 37:
            apply_barline(loc="left", style="heavy-light", repeat_dir="forward")
        elif bar_num == 42:
            # 1st ending start at left, stop + repeat at right
            apply_barline(loc="left", ending_num="1", ending_type="start")
            apply_barline(loc="right", style="light-heavy", repeat_dir="backward", ending_num="1", ending_type="stop")
        elif bar_num == 43:
            # 2nd ending start at left, discontinue + double bar at right
            apply_barline(loc="left", ending_num="2", ending_type="start")
            apply_barline(loc="right", style="light-light", ending_num="2", ending_type="discontinue")
        elif bar_num == 44:
            apply_barline(loc="left", style="heavy-light", repeat_dir="forward")
        elif bar_num == 47:
            apply_barline(loc="left", ending_num="1", ending_type="start")
            apply_barline(loc="right", style="light-heavy", repeat_dir="backward", ending_num="1", ending_type="stop")
        elif bar_num == 48:
            apply_barline(loc="left", ending_num="2", ending_type="start")
            apply_barline(loc="right", ending_num="2", ending_type="discontinue")
        elif bar_num == 65:
            apply_barline(loc="right", style="light-heavy")

        # Source measures
        m_src_vocal_upper = get_orig_measure("P1", bar_num)
        m_src_bass = get_orig_measure("P2", bar_num)
        m_src_gtr = get_orig_measure("P3", bar_num)
        m_src_stbass = get_orig_measure("P4", bar_num)

        # Build Notes for each part
        # 2. Bass (built first so vocal lyrics can attach to bass notes for playback)
        bass_notes = build_bass_notes(bar_num, m_src_bass)
        for n in bass_notes:
            t_measures["P3"].append(n)

        # 1. Soprano & Alto
        sop_notes, alt_notes = build_soprano_alto_notes(bar_num, m_src_vocal_upper, bass_notes=bass_notes)
        for n in sop_notes:
            t_measures["P1"].append(n)
        for n in alt_notes:
            t_measures["P2"].append(n)

        # 3. Guitar
        gtr_elements = build_guitar_elements(bar_num, m_src_gtr)
        for el in gtr_elements:
            t_measures["P4"].append(el)

        # 4. String Bass
        stb_notes = build_string_bass_notes(bar_num, m_src_stbass)
        for n in stb_notes:
            t_measures["P5"].append(n)

    # Save output
    out_xml.parent.mkdir(parents=True, exist_ok=True)
    xml_bytes = ET.tostring(new_root, encoding="utf-8", xml_declaration=True)
    with open(out_xml, "wb") as f:
        f.write(xml_bytes)
    print(f"Successfully generated 5-staff MusicXML: {out_xml}")


def build_soprano_alto_notes(bar_num: int, m_src: ET.Element, bass_notes: list[ET.Element] | None = None) -> tuple[list[ET.Element], list[ET.Element]]:
    """Return (soprano_notes, alto_notes) for bar_num with ground truth corrections and lyrics."""
    sop_notes = []
    alt_notes = []

    # Section 1: Measures 1 to 36 ("Las Posadas")
    # Measures 1-18 and 19-36 are identical musically!
    norm_m = bar_num if bar_num <= 18 else (bar_num - 18 if bar_num <= 36 else bar_num)

    if 1 <= bar_num <= 36:
        if norm_m == 1:
            # Quarter notes: D4/A4, D4/F#4, D4/F#4
            sop_notes = [
                make_pitch_note("A", 4, 4, "quarter"),
                make_pitch_note("F", 4, 4, "quarter", alter=1),
                make_pitch_note("F", 4, 4, "quarter", alter=1),
            ]
            alt_notes = [
                make_pitch_note("D", 4, 4, "quarter"),
                make_pitch_note("D", 4, 4, "quarter"),
                make_pitch_note("D", 4, 4, "quarter"),
            ]
        elif norm_m == 2:
            # Quarter notes: D4/F#4, E4/G4, F#4/A4
            sop_notes = [
                make_pitch_note("F", 4, 4, "quarter", alter=1),
                make_pitch_note("G", 4, 4, "quarter"),
                make_pitch_note("A", 4, 4, "quarter"),
            ]
            alt_notes = [
                make_pitch_note("D", 4, 4, "quarter"),
                make_pitch_note("E", 4, 4, "quarter"),
                make_pitch_note("F", 4, 4, "quarter", alter=1),
            ]
        elif norm_m == 3:
            # Alto: C#4 dotted half; Soprano: E4(q), G4(e), F#4(e), G4(e), A4(e)
            sop_notes = [
                make_pitch_note("E", 4, 4, "quarter"),
                make_pitch_note("G", 4, 2, "eighth"),
                make_pitch_note("F", 4, 2, "eighth", alter=1),
                make_pitch_note("G", 4, 2, "eighth"),
                make_pitch_note("A", 4, 2, "eighth"),
            ]
            alt_notes = [make_pitch_note("C", 4, 12, "half", alter=1, is_dotted=True)]
        elif norm_m == 4:
            # Dotted half: C#4/G4
            sop_notes = [make_pitch_note("G", 4, 12, "half", is_dotted=True)]
            alt_notes = [make_pitch_note("C", 4, 12, "half", alter=1, is_dotted=True)]
        elif norm_m == 5:
            # Quarter notes: E4/G4, C#4/E4, A3/C#4
            sop_notes = [
                make_pitch_note("G", 4, 4, "quarter"),
                make_pitch_note("E", 4, 4, "quarter"),
                make_pitch_note("C", 4, 4, "quarter", alter=1),
            ]
            alt_notes = [
                make_pitch_note("E", 4, 4, "quarter"),
                make_pitch_note("C", 4, 4, "quarter", alter=1),
                make_pitch_note("A", 3, 4, "quarter"),
            ]
        elif norm_m == 6:
            # Quarter notes: A3/C#4, C#4/E4, E4/G4
            sop_notes = [
                make_pitch_note("C", 4, 4, "quarter", alter=1),
                make_pitch_note("E", 4, 4, "quarter"),
                make_pitch_note("G", 4, 4, "quarter"),
            ]
            alt_notes = [
                make_pitch_note("A", 3, 4, "quarter"),
                make_pitch_note("C", 4, 4, "quarter", alter=1),
                make_pitch_note("E", 4, 4, "quarter"),
            ]
        elif norm_m == 7:
            # Alto: D4 dotted half; Soprano: F#4(q), A4(e), G#4(e), A4(e), B4(e)
            sop_notes = [
                make_pitch_note("F", 4, 4, "quarter", alter=1),
                make_pitch_note("A", 4, 2, "eighth"),
                make_pitch_note("G", 4, 2, "eighth", alter=1),
                make_pitch_note("A", 4, 2, "eighth"),
                make_pitch_note("B", 4, 2, "eighth"),
            ]
            alt_notes = [make_pitch_note("D", 4, 12, "half", is_dotted=True)]
        elif norm_m == 8:
            # Dotted half: D4/A4
            sop_notes = [make_pitch_note("A", 4, 12, "half", is_dotted=True)]
            alt_notes = [make_pitch_note("D", 4, 12, "half", is_dotted=True)]
        elif norm_m == 9:
            # Quarter notes: D4/B4, D4/A4, D4/F#4
            sop_notes = [
                make_pitch_note("B", 4, 4, "quarter"),
                make_pitch_note("A", 4, 4, "quarter"),
                make_pitch_note("F", 4, 4, "quarter", alter=1),
            ]
            alt_notes = [
                make_pitch_note("D", 4, 4, "quarter"),
                make_pitch_note("D", 4, 4, "quarter"),
                make_pitch_note("D", 4, 4, "quarter"),
            ]
        elif norm_m == 10:
            # D4/G4 (half), C#4/E4 (quarter)
            sop_notes = [
                make_pitch_note("G", 4, 8, "half"),
                make_pitch_note("E", 4, 4, "quarter"),
            ]
            alt_notes = [
                make_pitch_note("D", 4, 8, "half"),
                make_pitch_note("C", 4, 4, "quarter", alter=1),
            ]
        elif norm_m == 11:
            # Alto: D4 dotted half; Soprano: B4(d.q), A#4(e), B4(e), A#4(e)
            sop_notes = [
                make_pitch_note("B", 4, 6, "quarter", is_dotted=True),
                make_pitch_note("A", 4, 2, "eighth", alter=1),
                make_pitch_note("B", 4, 2, "eighth"),
                make_pitch_note("A", 4, 2, "eighth", alter=1),
            ]
            alt_notes = [make_pitch_note("D", 4, 12, "half", is_dotted=True)]
        elif norm_m == 12:
            # Dotted half: D4/B4
            sop_notes = [make_pitch_note("B", 4, 12, "half", is_dotted=True)]
            alt_notes = [make_pitch_note("D", 4, 12, "half", is_dotted=True)]
        elif norm_m == 13:
            # Soprano: C5(q), D5(q), B4(q); Alto: D4(half), D4(quarter)
            sop_notes = [
                make_pitch_note("C", 5, 4, "quarter"),
                make_pitch_note("D", 5, 4, "quarter"),
                make_pitch_note("B", 4, 4, "quarter"),
            ]
            alt_notes = [
                make_pitch_note("D", 4, 8, "half"),
                make_pitch_note("D", 4, 4, "quarter"),
            ]
        elif norm_m == 14:
            # Quarter notes: D4/A4, D4/B4, C#4/G4
            sop_notes = [
                make_pitch_note("A", 4, 4, "quarter"),
                make_pitch_note("B", 4, 4, "quarter"),
                make_pitch_note("G", 4, 4, "quarter"),
            ]
            alt_notes = [
                make_pitch_note("D", 4, 4, "quarter"),
                make_pitch_note("D", 4, 4, "quarter"),
                make_pitch_note("C", 4, 4, "quarter", alter=1),
            ]
        elif norm_m == 15:
            # Alto: D4 dotted half; Soprano: F#4(q), A4(e), G#4(e), B4(e), A4(e)
            sop_notes = [
                make_pitch_note("F", 4, 4, "quarter", alter=1),
                make_pitch_note("A", 4, 2, "eighth"),
                make_pitch_note("G", 4, 2, "eighth", alter=1),
                make_pitch_note("B", 4, 2, "eighth"),
                make_pitch_note("A", 4, 2, "eighth"),
            ]
            alt_notes = [make_pitch_note("D", 4, 12, "half", is_dotted=True)]
        elif norm_m == 16:
            # Alto: C#4 dotted half; Soprano: E4(q), G4(e), F#4(e), A4(e), G4(e)
            sop_notes = [
                make_pitch_note("E", 4, 4, "quarter"),
                make_pitch_note("G", 4, 2, "eighth"),
                make_pitch_note("F", 4, 2, "eighth", alter=1),
                make_pitch_note("A", 4, 2, "eighth"),
                make_pitch_note("G", 4, 2, "eighth"),
            ]
            alt_notes = [make_pitch_note("C", 4, 12, "half", alter=1, is_dotted=True)]
        elif norm_m == 17:
            # Dotted half: D4/F#4 tied to m18
            sop_notes = [make_pitch_note("F", 4, 12, "half", alter=1, is_dotted=True, tie="start")]
            alt_notes = [make_pitch_note("D", 4, 12, "half", is_dotted=True, tie="start")]
        elif norm_m == 18:
            # Half note tied from m17, quarter rest
            sop_notes = [
                make_pitch_note("F", 4, 8, "half", alter=1, tie="stop"),
                make_rest_note(4, "quarter"),
            ]
            alt_notes = [
                make_pitch_note("D", 4, 8, "half", tie="stop"),
                make_rest_note(4, "quarter"),
            ]

    # Section 2: Measures 37 to 43 ("Entren, Santos Peregrinos")
    elif bar_num == 37:
        # Pickup: 1 eighth note D4/F#4
        sop_notes = [make_pitch_note("F", 4, 2, "eighth", alter=1)]
        alt_notes = [make_pitch_note("D", 4, 2, "eighth")]
    elif bar_num == 38:
        # Eighth notes: D4/F#4, D4/G4, D4/A4, D4/B4
        sop_notes = [
            make_pitch_note("F", 4, 2, "eighth", alter=1),
            make_pitch_note("G", 4, 2, "eighth"),
            make_pitch_note("A", 4, 2, "eighth"),
            make_pitch_note("B", 4, 2, "eighth"),
        ]
        alt_notes = [
            make_pitch_note("D", 4, 2, "eighth"),
            make_pitch_note("D", 4, 2, "eighth"),
            make_pitch_note("D", 4, 2, "eighth"),
            make_pitch_note("D", 4, 2, "eighth"),
        ]
    elif bar_num == 39:
        # D4/A4(e), D4/F#4(e), D4/G4(d.e), D4/A4(16th)
        sop_notes = [
            make_pitch_note("A", 4, 2, "eighth"),
            make_pitch_note("F", 4, 2, "eighth", alter=1),
            make_pitch_note("G", 4, 3, "eighth", is_dotted=True),
            make_pitch_note("A", 4, 1, "16th"),
        ]
        alt_notes = [
            make_pitch_note("D", 4, 2, "eighth"),
            make_pitch_note("D", 4, 2, "eighth"),
            make_pitch_note("D", 4, 3, "eighth", is_dotted=True),
            make_pitch_note("D", 4, 1, "16th"),
        ]
    elif bar_num == 40:
        # D4/B4(e), D4/A4(e), D4/F#4(e), eighth rest
        sop_notes = [
            make_pitch_note("B", 4, 2, "eighth"),
            make_pitch_note("A", 4, 2, "eighth"),
            make_pitch_note("F", 4, 2, "eighth", alter=1),
            make_rest_note(2, "eighth"),
        ]
        alt_notes = [
            make_pitch_note("D", 4, 2, "eighth"),
            make_pitch_note("D", 4, 2, "eighth"),
            make_pitch_note("D", 4, 2, "eighth"),
            make_rest_note(2, "eighth"),
        ]
    elif bar_num == 41:
        # D4/F#4(e), D4/G4(e), D4/A4(e), D4/B4(e)
        sop_notes = [
            make_pitch_note("F", 4, 2, "eighth", alter=1),
            make_pitch_note("G", 4, 2, "eighth"),
            make_pitch_note("A", 4, 2, "eighth"),
            make_pitch_note("B", 4, 2, "eighth"),
        ]
        alt_notes = [
            make_pitch_note("D", 4, 2, "eighth"),
            make_pitch_note("D", 4, 2, "eighth"),
            make_pitch_note("D", 4, 2, "eighth"),
            make_pitch_note("D", 4, 2, "eighth"),
        ]
    elif bar_num == 42:
        # 1st ending: 3 eighth notes (D4/A4, D4/F#4, D4/F#4)
        sop_notes = [
            make_pitch_note("A", 4, 2, "eighth"),
            make_pitch_note("F", 4, 2, "eighth", alter=1),
            make_pitch_note("F", 4, 2, "eighth", alter=1),
        ]
        alt_notes = [
            make_pitch_note("D", 4, 2, "eighth"),
            make_pitch_note("D", 4, 2, "eighth"),
            make_pitch_note("D", 4, 2, "eighth"),
        ]
    elif bar_num == 43:
        # 2nd ending: D4/F#4 quarter, quarter rest
        sop_notes = [
            make_pitch_note("F", 4, 4, "quarter", alter=1),
            make_rest_note(4, "quarter"),
        ]
        alt_notes = [
            make_pitch_note("D", 4, 4, "quarter"),
            make_rest_note(4, "quarter"),
        ]

    # Section 3: Measures 44 to 48 ("¡Ándale, Juana!", 6/8)
    elif bar_num == 44:
        # Unison: D4(e), D4(e), F#4(e), A4(e), A4(q)
        sop_notes = [
            make_pitch_note("D", 4, 2, "eighth"),
            make_pitch_note("D", 4, 2, "eighth"),
            make_pitch_note("F", 4, 2, "eighth", alter=1),
            make_pitch_note("A", 4, 2, "eighth"),
            make_pitch_note("A", 4, 4, "quarter"),
        ]
        alt_notes = [
            make_pitch_note("D", 4, 2, "eighth"),
            make_pitch_note("D", 4, 2, "eighth"),
            make_pitch_note("F", 4, 2, "eighth", alter=1),
            make_pitch_note("A", 4, 2, "eighth"),
            make_pitch_note("A", 4, 4, "quarter"),
        ]
    elif bar_num == 45:
        # Soprano: B4(e), A4(e), B4(e), A4(e), F#4(q); Alto: D4(e x 4), D4(q)
        sop_notes = [
            make_pitch_note("B", 4, 2, "eighth"),
            make_pitch_note("A", 4, 2, "eighth"),
            make_pitch_note("B", 4, 2, "eighth"),
            make_pitch_note("A", 4, 2, "eighth"),
            make_pitch_note("F", 4, 4, "quarter", alter=1),
        ]
        alt_notes = [
            make_pitch_note("D", 4, 2, "eighth"),
            make_pitch_note("D", 4, 2, "eighth"),
            make_pitch_note("D", 4, 2, "eighth"),
            make_pitch_note("D", 4, 2, "eighth"),
            make_pitch_note("D", 4, 4, "quarter"),
        ]
    elif bar_num == 46:
        # Soprano: F#4(e), F#4(e), G4(e), A4(e), A4(e), A4(e)
        # Alto:    D4(e),  D4(e),  E4(e), F#4(e), F#4(e), F#4(e)
        sop_notes = [
            make_pitch_note("F", 4, 2, "eighth", alter=1),
            make_pitch_note("F", 4, 2, "eighth", alter=1),
            make_pitch_note("G", 4, 2, "eighth"),
            make_pitch_note("A", 4, 2, "eighth"),
            make_pitch_note("A", 4, 2, "eighth"),
            make_pitch_note("A", 4, 2, "eighth"),
        ]
        alt_notes = [
            make_pitch_note("D", 4, 2, "eighth"),
            make_pitch_note("D", 4, 2, "eighth"),
            make_pitch_note("E", 4, 2, "eighth"),
            make_pitch_note("F", 4, 2, "eighth", alter=1),
            make_pitch_note("F", 4, 2, "eighth", alter=1),
            make_pitch_note("F", 4, 2, "eighth", alter=1),
        ]
    elif bar_num == 47:
        # 1st ending:
        # Soprano: G4(e), A4(e), G4(e), F#4(e), F#4(q)
        # Alto:    E4(e), F#4(e), E4(e), D4(e), D4(q)
        sop_notes = [
            make_pitch_note("G", 4, 2, "eighth"),
            make_pitch_note("A", 4, 2, "eighth"),
            make_pitch_note("G", 4, 2, "eighth"),
            make_pitch_note("F", 4, 2, "eighth", alter=1),
            make_pitch_note("F", 4, 4, "quarter", alter=1),
        ]
        alt_notes = [
            make_pitch_note("E", 4, 2, "eighth"),
            make_pitch_note("F", 4, 2, "eighth", alter=1),
            make_pitch_note("E", 4, 2, "eighth"),
            make_pitch_note("D", 4, 2, "eighth"),
            make_pitch_note("D", 4, 4, "quarter"),
        ]
    elif bar_num == 48:
        # 2nd ending:
        # Soprano: A4(e), B4(e), A4(e), G4(e), F#4(q)
        # Alto:    F#4(e), G4(e), F#4(e), E4(e), D4(q)
        sop_notes = [
            make_pitch_note("A", 4, 2, "eighth"),
            make_pitch_note("B", 4, 2, "eighth"),
            make_pitch_note("A", 4, 2, "eighth"),
            make_pitch_note("G", 4, 2, "eighth"),
            make_pitch_note("F", 4, 4, "quarter", alter=1),
        ]
        alt_notes = [
            make_pitch_note("F", 4, 2, "eighth", alter=1),
            make_pitch_note("G", 4, 2, "eighth"),
            make_pitch_note("F", 4, 2, "eighth", alter=1),
            make_pitch_note("E", 4, 2, "eighth"),
            make_pitch_note("D", 4, 4, "quarter"),
        ]

    # Section 4: Measures 49 to 65 ("Dale, dale, dale", 2/4)
    elif bar_num in (49, 53, 57, 61):
        # 4 eighth notes: F#4/A4 x 4
        sop_notes = [make_pitch_note("A", 4, 2, "eighth") for _ in range(4)]
        alt_notes = [make_pitch_note("F", 4, 2, "eighth", alter=1) for _ in range(4)]
    elif bar_num in (50, 54, 58, 62):
        # 2 quarter notes: D4/B4 x 2
        sop_notes = [make_pitch_note("B", 4, 4, "quarter"), make_pitch_note("B", 4, 4, "quarter")]
        alt_notes = [make_pitch_note("D", 4, 4, "quarter"), make_pitch_note("D", 4, 4, "quarter")]
    elif bar_num in (51, 55, 59, 63):
        # 4 eighth notes: G4/C#5 x 4
        sop_notes = [make_pitch_note("C", 5, 2, "eighth", alter=1) for _ in range(4)]
        alt_notes = [make_pitch_note("G", 4, 2, "eighth") for _ in range(4)]
    elif bar_num in (52, 56):
        # 2 quarter notes: F#4/D5 x 2
        sop_notes = [make_pitch_note("D", 5, 4, "quarter"), make_pitch_note("D", 5, 4, "quarter")]
        alt_notes = [make_pitch_note("F", 4, 4, "quarter", alter=1), make_pitch_note("F", 4, 4, "quarter", alter=1)]
    elif bar_num == 60:
        # F#4/D5 quarter, quarter rest
        sop_notes = [make_pitch_note("D", 5, 4, "quarter"), make_rest_note(4, "quarter")]
        alt_notes = [make_pitch_note("F", 4, 4, "quarter", alter=1), make_rest_note(4, "quarter")]
    elif bar_num == 64:
        # F#4/D5 quarter with accent, quarter rest
        sop_notes = [make_pitch_note("D", 5, 4, "quarter", accent=True), make_rest_note(4, "quarter")]
        alt_notes = [make_pitch_note("F", 4, 4, "quarter", alter=1, accent=True), make_rest_note(4, "quarter")]
    elif bar_num == 65:
        # Whole measure rest
        sop_notes = [make_rest_note(8, "half", measure_rest=True)]
        alt_notes = [make_rest_note(8, "half", measure_rest=True)]

    # Attach Lyrics
    attach_lyrics_to_notes(bar_num, sop_notes, alt_notes, bass_notes=bass_notes)

    return sop_notes, alt_notes


def attach_lyrics_to_notes(bar_num: int, sop_notes: list[ET.Element], alt_notes: list[ET.Element], bass_notes: list[ET.Element] | None = None) -> None:
    """Attach proper lyrics and syllables to Soprano, Alto, and Bass notes."""
    # We will copy existing lyrics from the source or inject ground truth
    # 1. Section 1 (bars 1-36): 6 verses
    # Lyrics mapping: measure -> {verse_num: [(syllabic, text)]}
    LYRICS_SECTION_1 = {
        1: {
            1: [("single", "En"), ("single", "el")],
            2: [("single", "No"), ("begin", "se")],
            3: [("begin", "Ve"), ("middle", "ni")],
            4: [("begin", "Po"), ("middle", "sa")],
            5: [("single", "Mi"), ("begin", "es")],
            6: [("single", "Dios"), ("begin", "pa")],
        },
        2: {
            1: [("begin", "nom"), ("end", "bre"), ("single", "del")],
            2: [("end", "as"), ("begin", "in"), ("middle", "hu")],
            3: [("end", "mos"), ("begin", "ren"), ("middle", "di")],
            4: [("end", "da"), ("single", "te"), ("begin", "pi")],
            5: [("middle", "po"), ("middle", "sa es"), ("begin", "Ma")],
            6: [("end", "gue,"), ("begin", "se"), ("middle", "ñor")],
        },
        3: {
            1: [("begin", "Cie")],
            2: [("end", "ma")],
            3: [("end", "dos")],
            4: [("end", "do,")],
            5: [("middle", "rí")],
            6: [("middle", "es,")],
        },
        4: {
            1: [("end", "lo,")],
            2: [("end", "no;")],
            3: [("end", "des")],
            4: [("end", "a")],
            5: [("end", "a.")],
            6: [("end", "vues")],
        },
        5: {
            1: [("single", "os"), ("begin", "pi")],
            2: [("begin", "ten"), ("end", "nos")],
            3: [("single", "des"), ("single", "de")],
            4: [("single", "a"), ("middle", "ma")],
            5: [("begin", "Es"), ("begin", "Rei")],
            6: [("begin", "tra"), ("single", "ca")],
        },
        6: {
            1: [("end", "do"), ("begin", "po"), ("middle", "sa")],
            2: [("begin", "ca"), ("middle", "ri"), ("end", "dad.")],
            3: [("begin", "Na"), ("middle", "za"), ("end", "reth.")],
            4: [("end", "do"), ("begin", "ca"), ("middle", "se")],
            5: [("end", "na"), ("single", "del"), ("begin", "Cie")],
            6: [("middle", "ri"), ("end", "dad,"), ("single", "")],
        },
        7: {
            1: [("end", "da.")],
            4: [("end", "ro,")],
            5: [("end", "lo")],
        },
        9: {
            1: [("single", "Pues"), ("single", "no"), ("begin", "pue")],
            2: [("single", "que el"), ("single", "Dios"), ("single", "de")],
            3: [("single", "Yo"), ("single", "soy"), ("begin", "car")],
            4: [("single", "por"), ("single", "so"), ("middle", "lo u")],
            5: [("single", "y"), ("begin", "Ma"), ("end", "dre")],
            6: [("single", "y"), ("single", "os"), ("begin", "col")],
        },
        10: {
            1: [("middle", "de an"), ("end", "dar")],
            2: [("single", "los"), ("begin", "Cie")],
            3: [("middle", "pin"), ("end", "te")],
            4: [("single", "na"), ("single", "no")],
            5: [("single", "va a"), ("single", "ser")],
            6: [("middle", "me el"), ("begin", "Cie")],
        },
        11: {
            2: [("end", "los")],
            3: [("end", "ro")],
            4: [("end", "che")],
            6: [("end", "lo")],
        },
        13: {
            1: [("single", "mi"), ("begin", "es"), ("middle", "po")],
            2: [("single", "os"), ("single", "lo"), ("begin", "pre")],
            3: [("single", "de"), ("single", "nom"), ("begin", "bre")],
            4: [("single", "la"), ("begin", "Rei"), ("end", "na")],
            5: [("single", "del"), ("begin", "Di"), ("middle", "vi")],
            6: [("single", "de"), ("begin", "fe"), ("middle", "li")],
        },
        14: {
            1: [("end", "sa"), ("begin", "a"), ("middle", "ma")],
            2: [("middle", "mia"), ("end", "rá."), ("single", "")],
            3: [("single", "Jo"), ("end", "sé."), ("single", "")],
            4: [("single", "del"), ("begin", "Cie"), ("end", "lo.")],
            5: [("end", "no"), ("begin", "Ver"), ("end", "bo.")],
            6: [("middle", "ci"), ("end", "dad."), ("single", "")],
        },
        17: {
            1: [("end", "da.")],
        },
        # Measures 19-36: Innkeeper responses
        19: {
            1: [("single", "A"), ("begin", "quí"), ("single", "no")],
            2: [("single", "Ya"), ("single", "se"), ("begin", "pue")],
            3: [("single", "No"), ("single", "me im"), ("begin", "por")],
            4: [("single", "Pues,"), ("single", "si"), ("single", "es")],
            5: [("begin", "¿E"), ("end", "res"), ("single", "tu")],
            6: [("begin", "Di"), ("middle", "cho"), ("middle", "sa")],
        },
        20: {
            1: [("single", "es"), ("begin", "me"), ("end", "són.")],
            2: [("end", "den"), ("single", "ir"), ("single", "y")],
            3: [("middle", "ta el"), ("single", "nom"), ("end", "bre;")],
            4: [("single", "u"), ("single", "na"), ("begin", "rei")],
            5: [("single", "Jo"), ("end", "sé?"), ("single", "")],
            6: [("single", "la"), ("begin", "ca"), ("end", "sa")],
        },
        21: {
            2: [("single", "no")],
            3: [("begin", "dé")],
            4: [("end", "na,")],
        },
        23: {
            1: [("begin", "Si"), ("end", "gan"), ("begin", "a")],
            2: [("begin", "mo"), ("middle", "les"), ("end", "tar,")],
            3: [("middle", "jen"), ("end", "me"), ("begin", "dor")],
            4: [("single", "quien"), ("single", "lo"), ("begin", "so")],
            5: [("single", "¿Tu"), ("begin", "es"), ("middle", "po")],
            6: [("single", "que"), ("single", "al"), ("begin", "ber")],
        },
        24: {
            1: [("middle", "de"), ("begin", "lan"), ("end", "te.")],
            3: [("end", "mir."), ("single", ""), ("single", "")],
            4: [("middle", "li"), ("middle", "ci"), ("end", "ta,")],
            5: [("end", "sa es"), ("begin", "Ma"), ("middle", "rí")],
            6: [("middle", "ga es"), ("middle", "ta"), ("begin", "dí")],
        },
        25: {
            5: [("end", "a?")],
            6: [("end", "a")],
        },
        27: {
            1: [("single", "Yo"), ("single", "no"), ("begin", "pue")],
            2: [("single", "por"), ("single", "que"), ("single", "si")],
            3: [("single", "Pues"), ("single", "que"), ("single", "ya")],
            4: [("begin", "¿có"), ("middle", "mo"), ("single", "es")],
            5: [("single", "En"), ("end", "tren,"), ("single", "")],
            6: [("single", "a"), ("single", "la"), ("begin", "Vir")],
        },
        28: {
            1: [("end", "do a"), ("begin", "brir,")],
            2: [("single", "me in"), ("begin", "fa")],
            3: [("single", "les"), ("begin", "di")],
            4: [("single", "de"), ("single", "no")],
            5: [("begin", "pe"), ("middle", "re")],
            6: [("end", "gen"), ("begin", "pu")],
        },
        29: {
            2: [("end", "do,")],
            3: [("end", "go")],
            4: [("end", "che")],
            5: [("end", "gri")],
            6: [("end", "ra,")],
        },
        31: {
            1: [("single", "no"), ("single", "se a al"), ("begin", "gun")],
            2: [("single", "os"), ("single", "voy"), ("single", "a a")],
            3: [("single", "que"), ("single", "no"), ("begin", "he")],
            4: [("single", "an"), ("single", "da"), ("begin", "tan")],
            5: [("single", "No"), ("single", "los"), ("begin", "co")],
            6: [("single", "la"), ("single", "her"), ("begin", "mo")],
        },
        32: {
            1: [("begin", "tu"), ("middle", "nan"), ("end", "te.")],
            2: [("begin", "pa"), ("middle", "le"), ("end", "ar.")],
            3: [("middle", "mos"), ("single", "de"), ("begin", "a")],
            4: [("middle", "so"), ("middle", "li"), ("end", "ta?")],
            5: [("middle", "no"), ("middle", "cí"), ("end", "a.")],
            6: [("end", "sa"), ("begin", "Ma"), ("middle", "rí")],
        },
        35: {
            3: [("end", "brir.")],
            6: [("end", "a.")],
        },
    }

    # Section 2 (bars 37-43)
    LYRICS_SECTION_2 = {
        37: {1: [("begin", "En")], 2: [("begin", "Aun")]},
        38: {
            1: [("end", "tren,"), ("begin", "San"), ("end", "tos"), ("begin", "Pe")],
            2: [("end", "que es"), ("begin", "po"), ("end", "bre"), ("single", "la")],
        },
        39: {
            1: [("middle", "re"), ("middle", "gri"), ("end", "nos,"), ("begin", "(Pe")],
            2: [("begin", "mo"), ("middle", "ra"), ("end", "da,"), ("begin", "(la")],
        },
        40: {
            1: [("middle", "re"), ("middle", "gri"), ("end", "nos,)")],
            2: [("begin", "mo"), ("middle", "ra"), ("end", "da,)")],
        },
        41: {
            1: [("begin", "re"), ("middle", "ci"), ("end", "ban"), ("single", "es")],
            2: [("single", "os"), ("single", "la"), ("single", "doy"), ("single", "de")],
        },
        42: {
            1: [("single", "te"), ("begin", "rin"), ("end", "cón;")],
            2: [("single", "co"), ("middle", "ra"), ("end", "-")],
        },
        43: {
            2: [("end", "zón.")],
        },
    }

    # Section 3 (bars 44-48)
    LYRICS_SECTION_3 = {
        44: {
            1: [("begin", "An"), ("middle", "da"), ("end", "le,"), ("begin", "Jua"), ("end", "na,")],
            2: [("begin", "Ca"), ("middle", "sta"), ("end", "ña"), ("begin", "cru"), ("end", "da,")],
        },
        45: {
            1: [("single", "no"), ("single", "te"), ("begin", "di"), ("middle", "la"), ("end", "tes")],
            2: [("begin", "ca"), ("middle", "sta"), ("middle", "ña a"), ("middle", "sa"), ("end", "da,")],
        },
        46: {
            1: [("single", "con"), ("single", "la"), ("begin", "ca"), ("middle", "na"), ("middle", "sta"), ("single", "de")],
            2: [("single", "den"), ("single", "le"), ("single", "de"), ("single", "pa"), ("single", "lo"), ("single", "al")],
        },
        47: {
            1: [("single", "los"), ("begin", "ca"), ("middle", "ca"), ("middle", "hua"), ("end", "tes.")],
        },
        48: {
            1: [("single", "de"), ("single", "la"), ("begin", "Po"), ("middle", "sa"), ("end", "da.")],
        },
    }

    # Section 4 (bars 49-64)
    LYRICS_SECTION_4 = {
        49: [("begin", "Da"), ("end", "le,"), ("begin", "da"), ("end", "le,")],
        50: [("begin", "da"), ("end", "le.")],
        51: [("single", "No"), ("begin", "pier"), ("end", "das"), ("single", "el")],
        52: [("begin", "ti"), ("end", "no;")],
        53: [("single", "Por"), ("single", "que"), ("single", "si"), ("single", "lo")],
        54: [("begin", "pier"), ("end", "des,")],
        55: [("begin", "pier"), ("end", "des"), ("single", "el"), ("begin", "ca")],
        56: [("middle", "mi"), ("end", "no.")],
        57: [("begin", "Da"), ("end", "le,"), ("begin", "da"), ("end", "le")],
        58: [("begin", "da"), ("end", "le.")],
        59: [("begin", "Da"), ("end", "le‿y"), ("single", "no"), ("single", "le")],
        60: [("end", "dió.")],
        61: [("begin", "Pon"), ("middle", "ga"), ("single", "me"), ("single", "la")],
        62: [("begin", "ven"), ("end", "da,")],
        63: [("single", "¡por"), ("single", "que"), ("single", "si"), ("end", "go")],
        64: [("end", "yo!")],
    }

    # Helper to attach verses dict to note lists
    def attach_multiverse(m_dict: dict[int, list[tuple[str, str]]], target_notes: list[list[ET.Element]], print_object: str | None = None, verse_filter: int | None = None):
        for v_num, syl_list in m_dict.items():
            if verse_filter is not None and v_num != verse_filter:
                continue
            for n_list in target_notes:
                sung_notes = [n for n in n_list if n.find("rest") is None]
                for n, (syl, txt) in zip(sung_notes, syl_list):
                    if txt:
                        add_lyric(n, txt, syllabic=syl, number=str(v_num), print_object=print_object)

    if bar_num in LYRICS_SECTION_1:
        # For section 1 (6 verses), attach all to Soprano (verse 6 in standard Roman font)
        attach_multiverse(LYRICS_SECTION_1[bar_num], [sop_notes])
        # Alto gets hidden Verse 1 for playback articulation
        attach_multiverse(LYRICS_SECTION_1[bar_num], [alt_notes], print_object="no", verse_filter=1)
        # Bass gets hidden Verse 6 for playback articulation
        if bass_notes:
            attach_multiverse(LYRICS_SECTION_1[bar_num], [bass_notes], print_object="no", verse_filter=6)
    elif bar_num in LYRICS_SECTION_2:
        attach_multiverse(LYRICS_SECTION_2[bar_num], [sop_notes, alt_notes])
        if bass_notes:
            attach_multiverse(LYRICS_SECTION_2[bar_num], [bass_notes], print_object="no", verse_filter=1)
    elif bar_num in LYRICS_SECTION_3:
        attach_multiverse(LYRICS_SECTION_3[bar_num], [sop_notes, alt_notes])
        if bass_notes:
            attach_multiverse(LYRICS_SECTION_3[bar_num], [bass_notes], print_object="no", verse_filter=1)
    elif bar_num in LYRICS_SECTION_4:
        syl_list = LYRICS_SECTION_4[bar_num]
        for n_list in (sop_notes, alt_notes):
            sung_notes = [n for n in n_list if n.find("rest") is None]
            for n, (syl, txt) in zip(sung_notes, syl_list):
                if txt:
                    add_lyric(n, txt, syllabic=syl, number="1")
        if bass_notes:
            sung_bass = [n for n in bass_notes if n.find("rest") is None]
            for n, (syl, txt) in zip(sung_bass, syl_list):
                if txt:
                    add_lyric(n, txt, syllabic=syl, number="1", print_object="no")


def build_bass_notes(bar_num: int, m_src: ET.Element) -> list[ET.Element]:
    """Return Bass vocal notes for bar_num with ground truth corrections."""
    norm_m = bar_num if bar_num <= 18 else (bar_num - 18 if bar_num <= 36 else bar_num)

    if 1 <= bar_num <= 36:
        if norm_m == 1:
            return [
                make_pitch_note("F", 3, 4, "quarter", alter=1),
                make_pitch_note("D", 3, 4, "quarter"),
                make_pitch_note("F", 3, 4, "quarter", alter=1),
            ]
        elif norm_m == 2:
            return [
                make_pitch_note("F", 3, 4, "quarter", alter=1),
                make_pitch_note("G", 3, 4, "quarter"),
                make_pitch_note("A", 3, 4, "quarter"),
            ]
        elif norm_m == 3:
            return [
                make_pitch_note("A", 3, 4, "quarter"),
                make_pitch_note("E", 3, 2, "eighth"),
                make_pitch_note("D", 3, 2, "eighth", alter=1),
                make_pitch_note("E", 3, 2, "eighth"),
                make_pitch_note("F", 3, 2, "eighth", alter=1),
            ]
        elif norm_m == 4:
            return [make_pitch_note("E", 3, 12, "half", is_dotted=True)]
        elif norm_m == 5:
            return [
                make_pitch_note("A", 3, 8, "half"),
                make_pitch_note("E", 3, 4, "quarter"),
            ]
        elif norm_m == 6:
            return [
                make_pitch_note("E", 3, 4, "quarter"),
                make_pitch_note("A", 3, 4, "quarter"),
                make_pitch_note("A", 3, 4, "quarter"),
            ]
        elif norm_m == 7:
            return [
                make_pitch_note("D", 3, 4, "quarter"),
                make_pitch_note("F", 3, 2, "eighth", alter=1),
                make_pitch_note("E", 3, 2, "eighth", alter=1),
                make_pitch_note("F", 3, 2, "eighth", alter=1),
                make_pitch_note("G", 3, 2, "eighth"),
            ]
        elif norm_m == 8:
            return [make_pitch_note("F", 3, 12, "half", alter=1, is_dotted=True)]
        elif norm_m == 9:
            return [
                make_pitch_note("A", 3, 4, "quarter"),
                make_pitch_note("F", 3, 4, "quarter", alter=1),
                make_pitch_note("D", 3, 4, "quarter"),
            ]
        elif norm_m == 10:
            return [
                make_pitch_note("F", 3, 8, "half", alter=1),
                make_pitch_note("F", 3, 4, "quarter", alter=1),
            ]
        elif norm_m == 11:
            return [
                make_pitch_note("G", 3, 6, "quarter", is_dotted=True),
                make_pitch_note("F", 3, 2, "eighth", alter=1),
                make_pitch_note("G", 3, 2, "eighth"),
                make_pitch_note("F", 3, 2, "eighth", alter=1),
            ]
        elif norm_m == 12:
            return [make_pitch_note("G", 3, 12, "half", is_dotted=True)]
        elif norm_m == 13:
            return [
                make_pitch_note("B", 3, 4, "quarter"),
                make_pitch_note("A", 3, 4, "quarter"),
                make_pitch_note("G", 3, 4, "quarter"),
            ]
        elif norm_m == 14:
            return [
                make_pitch_note("F", 3, 4, "quarter", alter=1),
                make_pitch_note("G", 3, 4, "quarter"),
                make_pitch_note("E", 3, 4, "quarter"),
            ]
        elif norm_m == 15:
            return [
                make_pitch_note("D", 3, 4, "quarter"),
                make_pitch_note("F", 3, 2, "eighth", alter=1),
                make_pitch_note("E", 3, 2, "eighth", alter=1),
                make_pitch_note("G", 3, 2, "eighth"),
                make_pitch_note("F", 3, 2, "eighth", alter=1),
            ]
        elif norm_m == 16:
            return [
                make_pitch_note("C", 3, 4, "quarter", alter=1),
                make_pitch_note("E", 3, 2, "eighth"),
                make_pitch_note("D", 3, 2, "eighth", alter=1),
                make_pitch_note("F", 3, 2, "eighth", alter=1),
                make_pitch_note("E", 3, 2, "eighth"),
            ]
        elif norm_m == 17:
            return [make_pitch_note("D", 3, 12, "half", is_dotted=True, tie="start")]
        elif norm_m == 18:
            return [
                make_pitch_note("D", 3, 8, "half", tie="stop"),
                make_rest_note(4, "quarter"),
            ]

    elif bar_num == 37:
        return [make_pitch_note("D", 3, 2, "eighth")]
    elif bar_num == 38:
        return [
            make_pitch_note("D", 3, 2, "eighth"),
            make_pitch_note("G", 3, 2, "eighth"),
            make_pitch_note("F", 3, 2, "eighth", alter=1),
            make_pitch_note("G", 3, 2, "eighth"),
        ]
    elif bar_num == 39:
        return [
            make_pitch_note("F", 3, 2, "eighth", alter=1),
            make_pitch_note("D", 3, 2, "eighth"),
            make_pitch_note("G", 3, 3, "eighth", is_dotted=True),
            make_pitch_note("A", 3, 1, "16th"),
        ]
    elif bar_num == 40:
        return [
            make_pitch_note("B", 3, 2, "eighth"),
            make_pitch_note("A", 3, 2, "eighth"),
            make_pitch_note("F", 3, 2, "eighth", alter=1),
            make_rest_note(2, "eighth"),
        ]
    elif bar_num == 41:
        return [
            make_pitch_note("D", 3, 2, "eighth"),
            make_pitch_note("E", 3, 2, "eighth"),
            make_pitch_note("F", 3, 2, "eighth", alter=1),
            make_pitch_note("G", 3, 2, "eighth"),
        ]
    elif bar_num == 42:
        return [
            make_pitch_note("F", 3, 2, "eighth", alter=1),
            make_pitch_note("D", 3, 2, "eighth"),
            make_pitch_note("D", 3, 2, "eighth"),
        ]
    elif bar_num == 43:
        return [
            make_pitch_note("D", 3, 4, "quarter"),
            make_rest_note(4, "quarter"),
        ]

    elif bar_num == 44:
        return [
            make_pitch_note("D", 3, 2, "eighth"),
            make_pitch_note("D", 3, 2, "eighth"),
            make_pitch_note("F", 3, 2, "eighth", alter=1),
            make_pitch_note("G", 3, 2, "eighth"),
            make_pitch_note("F", 3, 4, "quarter", alter=1),
        ]
    elif bar_num == 45:
        return [
            make_pitch_note("G", 3, 2, "eighth"),
            make_pitch_note("F", 3, 2, "eighth", alter=1),
            make_pitch_note("G", 3, 2, "eighth"),
            make_pitch_note("F", 3, 2, "eighth", alter=1),
            make_pitch_note("D", 3, 4, "quarter"),
        ]
    elif bar_num == 46:
        return [
            make_pitch_note("D", 3, 2, "eighth"),
            make_pitch_note("D", 3, 2, "eighth"),
            make_pitch_note("E", 3, 2, "eighth"),
            make_pitch_note("F", 3, 2, "eighth", alter=1),
            make_pitch_note("F", 3, 2, "eighth", alter=1),
            make_pitch_note("F", 3, 2, "eighth", alter=1),
        ]
    elif bar_num == 47:
        return [
            make_pitch_note("G", 3, 2, "eighth"),
            make_pitch_note("A", 3, 2, "eighth"),
            make_pitch_note("G", 3, 2, "eighth"),
            make_pitch_note("F", 3, 2, "eighth", alter=1),
            make_pitch_note("D", 3, 4, "quarter"),
        ]
    elif bar_num == 48:
        return [
            make_pitch_note("D", 3, 2, "eighth"),
            make_pitch_note("G", 3, 2, "eighth"),
            make_pitch_note("F", 3, 2, "eighth", alter=1),
            make_pitch_note("E", 3, 2, "eighth"),
            make_pitch_note("D", 3, 4, "quarter"),
        ]

    elif bar_num in (49, 53, 57, 61):
        return [make_pitch_note("D", 3, 2, "eighth") for _ in range(4)]
    elif bar_num in (50, 54, 58, 62):
        return [make_pitch_note("G", 3, 4, "quarter"), make_pitch_note("G", 3, 4, "quarter")]
    elif bar_num in (51, 55, 59, 63):
        return [make_pitch_note("A", 3, 2, "eighth") for _ in range(4)]
    elif bar_num in (52, 56):
        return [make_pitch_note("D", 3, 4, "quarter"), make_pitch_note("D", 3, 4, "quarter")]
    elif bar_num == 60:
        return [make_pitch_note("D", 3, 4, "quarter"), make_rest_note(4, "quarter")]
    elif bar_num == 64:
        return [make_pitch_note("D", 3, 4, "quarter", accent=True), make_rest_note(4, "quarter")]
    elif bar_num == 65:
        return [make_rest_note(8, "half", measure_rest=True)]

    return []


def build_guitar_elements(bar_num: int, m_src: ET.Element) -> list[ET.Element]:
    """Return Guitar elements (notes + harmonies) for bar_num."""
    elements = []

    # Ground truth chords for Page 5 (bars 48-65)
    PAGE_5_HARMONIES = {
        48: [("A", "dominant"), ("D", "major")],
        49: [("D", "major")],
        50: [("G", "major")],
        51: [("A", "dominant")],
        52: [("D", "major")],
        53: [("D", "major")],
        54: [("G", "major")],
        55: [("A", "dominant")],
        56: [("D", "major")],
        57: [("D", "major")],
        58: [("G", "major")],
        59: [("A", "dominant")],
        60: [("D", "major")],
        61: [("D", "major")],
        62: [("G", "major")],
        63: [("A", "dominant")],
        64: [("D", "major"), ("A", "dominant")],
        65: [("D", "major")],
    }

    if bar_num in PAGE_5_HARMONIES:
        for r_step, kind in PAGE_5_HARMONIES[bar_num]:
            elements.append(make_harmony(r_step, kind))
    else:
        # Copy harmonies from m_src
        for h in m_src.findall("harmony"):
            elements.append(copy.deepcopy(h))

    # Notes
    for el in m_src:
        if el.tag == "note":
            n = copy.deepcopy(el)
            # Remove lyric elements mistakenly placed on guitar
            for lyr in n.findall("lyric"):
                n.remove(lyr)
            elements.append(n)
        elif el.tag == "backup":
            elements.append(copy.deepcopy(el))

    return elements


def build_string_bass_notes(bar_num: int, m_src: ET.Element) -> list[ET.Element]:
    """Return String Bass notes for bar_num."""
    notes = []
    if bar_num == 65:
        # D2 half note with accent
        return [make_pitch_note("D", 2, 8, "half", accent=True)]
    for n in m_src.findall("note"):
        n_clean = clean_note_element(n)
        for lyr in n_clean.findall("lyric"):
            n_clean.remove(lyr)
        notes.append(n_clean)
    return notes


if __name__ == "__main__":
    in_f = Path(sys.argv[1] if len(sys.argv) > 1 else "~/Downloads/Las Posadas.xml").expanduser()
    out_f = Path(sys.argv[2] if len(sys.argv) > 2 else "~/Downloads/Las Posadas - 5 Staff.xml").expanduser()
    build_las_posadas_score(in_f, out_f)
