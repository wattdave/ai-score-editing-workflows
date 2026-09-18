#!/usr/bin/env python3
"""Assemble Mary at the Tomb from Halbestunde 3-part MusicXML into 4-staff SATB MusicXML."""

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


def clean_note_element(note: ET.Element, voice: str = "1") -> ET.Element:
    n = copy.deepcopy(note)
    for tag in ("staff", "chord", "stem"):
        elem = n.find(tag)
        if elem is not None:
            n.remove(elem)
    # Remove existing lyrics to attach clean ones
    for lyr in n.findall("lyric"):
        n.remove(lyr)
    # Remove existing tuplet notations and time-modifications
    tmod = n.find("time-modification")
    if tmod is not None:
        n.remove(tmod)
    notations = n.find("notations")
    if notations is not None:
        for tup in notations.findall("tuplet"):
            notations.remove(tup)
        if len(notations) == 0:
            n.remove(notations)
    v = n.find("voice")
    if v is not None:
        v.text = voice
    else:
        v = ET.SubElement(n, "voice")
        v.text = voice
    return n


def make_pitch_note(step: str, octave: int, dur: int, note_type: str, alter: int = 0, is_dotted: bool = False, voice: str = "1") -> ET.Element:
    n = ET.Element("note")
    p = ET.SubElement(n, "pitch")
    ET.SubElement(p, "step").text = step
    if alter != 0:
        ET.SubElement(p, "alter").text = str(alter)
    ET.SubElement(p, "octave").text = str(octave)
    ET.SubElement(n, "duration").text = str(dur)
    ET.SubElement(n, "voice").text = voice
    ET.SubElement(n, "type").text = note_type
    if is_dotted:
        ET.SubElement(n, "dot")
    return n


def make_rest_note(dur: int, note_type: str | None = None, voice: str = "1") -> ET.Element:
    n = ET.Element("note")
    ET.SubElement(n, "rest")
    ET.SubElement(n, "duration").text = str(dur)
    ET.SubElement(n, "voice").text = voice
    if note_type:
        ET.SubElement(n, "type").text = note_type
    return n


def parse_measure_clusters(measure: ET.Element) -> list[list[ET.Element]]:
    """Group consecutive note elements into chord clusters, ignoring voice 2 unison duplicates."""
    clusters = []
    current_cluster = []
    for el in measure:
        if el.tag == "backup":
            if current_cluster:
                clusters.append(current_cluster)
                current_cluster = []
            continue
        if el.tag == "forward":
            continue
        if el.tag == "note":
            v = el.findtext("voice", "1")
            # Ignore voice 2 unison duplicates
            if v != "1":
                continue
            if el.find("chord") is not None:
                if current_cluster:
                    current_cluster.append(el)
                else:
                    current_cluster = [el]
            else:
                if current_cluster:
                    clusters.append(current_cluster)
                current_cluster = [el]
    if current_cluster:
        clusters.append(current_cluster)
    return clusters


# Lyric syllable ground truth corrections based on visual PDF inspection
LYRIC_TEXT_CORRECTIONS = {
    (13, "Wo"): '"Wo',
    (15, "Be"): '"Be',
    (19, "him."): 'him."',
    (26, "Wo"): '"Wo',
    (27, "Whem"): 'Whom',
    (28, "seek?"): 'seek?"',
    (31, "Sir,"): '"Sir,',
    (37, "way."): 'way."',
    (39, "Ma"): '"Ma',
    (39, "ry."): 'ry."',
    (40, "Rab"): '"Rab',
    (42, "ni!"): 'ni!"',
    (43, "Do"): '"Do',
    (46, "ther"): 'ther;',
    (54, "God."): 'God."',
    (58, "I"): '"I',
    (59, "Lords"): 'Lord";',
}

# Ground truth tuplet specification per measure: mapping measure_number -> list of (start_note_idx, stop_note_idx)
TUPLET_SPEC: dict[int, list[tuple[int, int]]] = {
    13: [(0, 1), (2, 4)],
    14: [(0, 1)],
    16: [(0, 2), (3, 5)],
    18: [(0, 2), (3, 5)],
    20: [(3, 5)],
    23: [(0, 2), (3, 5)],
    26: [(0, 1), (2, 4)],
    27: [(0, 1), (2, 4)],
    32: [(0, 2)],
    34: [(0, 2)],
    36: [(2, 4)],
    38: [(2, 4)],
    45: [(0, 2)],
    47: [(0, 2), (3, 5)],
    48: [(0, 2)],
    55: [(2, 4)],
    59: [(1, 3)],
    60: [(0, 2)],
}


def apply_tuplet_spec_to_notes(notes: list[ET.Element], specs: list[tuple[int, int]]) -> None:
    """Apply exact tuplet bounds and time modifications to a list of notes."""
    for start_idx, stop_idx in specs:
        for idx in range(start_idx, stop_idx + 1):
            n = notes[idx]
            tmod = ET.Element("time-modification")
            ET.SubElement(tmod, "actual-notes").text = "3"
            ET.SubElement(tmod, "normal-notes").text = "2"

            insert_pos = len(n)
            for i, child in enumerate(n):
                if child.tag in ("stem", "notehead", "notations", "lyric"):
                    insert_pos = i
                    break
            n.insert(insert_pos, tmod)

            if idx == start_idx or idx == stop_idx:
                notations = n.find("notations")
                if notations is None:
                    lyr = n.find("lyric")
                    if lyr is not None:
                        l_idx = list(n).index(lyr)
                        notations = ET.Element("notations")
                        n.insert(l_idx, notations)
                    else:
                        notations = ET.SubElement(n, "notations")
                if idx == start_idx:
                    ET.SubElement(notations, "tuplet", bracket="yes", type="start")
                if idx == stop_idx:
                    ET.SubElement(notations, "tuplet", type="stop")


def extract_directions(m: ET.Element) -> list[tuple[int, ET.Element]]:
    """Extract (cluster_index, direction_element) from measure."""
    results = []
    c_idx = 0
    for el in m:
        if el.tag == "direction":
            results.append((c_idx, copy.deepcopy(el)))
        elif el.tag == "note":
            if el.find("chord") is None and el.findtext("voice", "1") == "1":
                c_idx += 1
    return results


def get_measure_directions(
    mnum: int, m_treble_src: ET.Element, m_bass_src: ET.Element
) -> tuple[dict[int, list[ET.Element]], dict[int, list[ET.Element]]]:
    """Return dict of {note_idx: [direction_elements]} for P1 (above) and P3 (below)."""
    p1_dirs: dict[int, list[ET.Element]] = {}
    p3_dirs: dict[int, list[ET.Element]] = {}

    def add_dir(target_dict: dict[int, list[ET.Element]], idx: int, elem: ET.Element, placement: str) -> None:
        e = copy.deepcopy(elem)
        s = e.find("staff")
        if s is not None:
            e.remove(s)
        e.attrib["placement"] = placement
        target_dict.setdefault(idx, []).append(e)

    def make_dynamic_dir(dyn_name: str, placement: str) -> ET.Element:
        d = ET.Element("direction", placement=placement)
        dt = ET.SubElement(d, "direction-type")
        dyn = ET.SubElement(dt, "dynamics")
        ET.SubElement(dyn, dyn_name)
        return d

    if mnum == 1:
        # Treble has tempo, Bass has mp
        for idx, el in extract_directions(m_treble_src):
            add_dir(p1_dirs, idx, el, "above")
        add_dir(p1_dirs, 0, make_dynamic_dir("mp", "above"), "above")
        add_dir(p3_dirs, 0, make_dynamic_dir("mp", "below"), "below")

    elif mnum == 22:
        # Beat 1 'stand' gets f, beat 4/pickup 'but' (idx 3) gets p
        add_dir(p1_dirs, 0, make_dynamic_dir("f", "above"), "above")
        add_dir(p1_dirs, 3, make_dynamic_dir("p", "above"), "above")
        add_dir(p3_dirs, 0, make_dynamic_dir("f", "below"), "below")
        add_dir(p3_dirs, 3, make_dynamic_dir("p", "below"), "below")

    elif mnum == 59:
        # Note 0 is 'Lord";', Note 1 is quarter rest: mp starts on the rest
        add_dir(p1_dirs, 1, make_dynamic_dir("mp", "above"), "above")
        add_dir(p3_dirs, 1, make_dynamic_dir("mp", "below"), "below")

    else:
        for idx, el in extract_directions(m_treble_src):
            add_dir(p1_dirs, idx, el, "above")
        for idx, el in extract_directions(m_bass_src):
            has_dyn = (
                el.find(".//dynamics") is not None
                or el.find(".//wedge") is not None
                or el.find(".//words") is not None
            )
            if has_dyn:
                add_dir(p3_dirs, idx, el, "below")

    return p1_dirs, p3_dirs


def build_satb_score(input_xml: Path, output_xml: Path) -> None:
    tree = ET.parse(input_xml)
    root = tree.getroot()

    parts_dict = {p.attrib.get("id"): p for p in root.findall("part")}
    p1_m = parts_dict["P1"].findall("measure")
    p2_m = parts_dict["P2"].findall("measure")
    p3_m = parts_dict["P3"].findall("measure")

    num_bars = len(p1_m)

    # Extract clean lyric syllable sequence per measure from P1
    lyrics_by_measure: dict[int, list[tuple[str, str]]] = {}
    for i, m in enumerate(p1_m):
        mnum = i + 1
        syls = []
        for n in m.findall("note"):
            lyr = n.find("lyric")
            if lyr is not None:
                txt = lyr.findtext("text", "")
                syllabic = lyr.findtext("syllabic", "single")
                # Apply ground-truth text correction
                if (mnum, txt) in LYRIC_TEXT_CORRECTIONS:
                    txt = LYRIC_TEXT_CORRECTIONS[(mnum, txt)]
                syls.append((txt, syllabic))
        lyrics_by_measure[mnum] = syls

    # Create fresh root
    new_root = ET.Element("score-partwise", version="3.1")

    # Score information / metadata
    work = ET.SubElement(new_root, "work")
    ET.SubElement(work, "work-title").text = "Mary at the Tomb"

    ident = ET.SubElement(new_root, "identification")
    creator_comp = ET.SubElement(ident, "creator", type="composer")
    creator_comp.text = "Ann Callaway / 7 March 2026"
    creator_lyr = ET.SubElement(ident, "creator", type="lyricist")
    creator_lyr.text = "John 20:11-18"
    rights = ET.SubElement(ident, "rights")
    rights.text = "Copyright © Ann Callaway 2026"

    encoding = ET.SubElement(ident, "encoding")
    ET.SubElement(encoding, "software").text = "Sibelius WebSocket CLI SATB Assembler"

    # Part-List definition
    plist = ET.SubElement(new_root, "part-list")
    pg_start = ET.SubElement(plist, "part-group", number="1", type="start")
    ET.SubElement(pg_start, "group-symbol").text = "bracket"
    ET.SubElement(pg_start, "group-barline").text = "yes"

    parts_meta = [
        ("P1", "Soprano", "S.", "voice.soprano", "1"),
        ("P2", "Alto", "A.", "voice.alto", "2"),
        ("P3", "Tenor", "T.", "voice.tenor", "3"),
        ("P4", "Bass", "B.", "voice.bass", "4"),
    ]

    for pid, pname, abbr, sound_id, chan in parts_meta:
        sp = ET.SubElement(plist, "score-part", id=pid)
        ET.SubElement(sp, "part-name").text = pname
        ET.SubElement(sp, "part-abbreviation").text = abbr
        instr = ET.SubElement(sp, "score-instrument", id=f"{pid}-I1")
        ET.SubElement(instr, "instrument-name").text = pname
        ET.SubElement(instr, "instrument-sound").text = sound_id
        midi = ET.SubElement(sp, "midi-instrument", id=f"{pid}-I1")
        ET.SubElement(midi, "midi-channel").text = chan
        ET.SubElement(midi, "midi-program").text = "53"  # Choir Aahs

    ET.SubElement(plist, "part-group", number="1", type="stop")

    # Parts containers
    satb_parts = {
        "P1": ET.SubElement(new_root, "part", id="P1"),
        "P2": ET.SubElement(new_root, "part", id="P2"),
        "P3": ET.SubElement(new_root, "part", id="P3"),
        "P4": ET.SubElement(new_root, "part", id="P4"),
    }

    # Iterate through all 62 measures
    for i in range(num_bars):
        mnum = i + 1
        mnum_str = str(mnum)

        m_treble_src = p1_m[i]
        m_bass_src = p2_m[i] if i < 39 else p3_m[i]

        m_targets = {pid: ET.SubElement(satb_parts[pid], "measure", number=mnum_str) for pid in satb_parts}

        # Handle attributes
        if mnum == 1:
            divs = 384

            # Soprano Attributes (Treble G2)
            a1 = ET.SubElement(m_targets["P1"], "attributes")
            ET.SubElement(a1, "divisions").text = str(divs)
            k1 = ET.SubElement(a1, "key")
            ET.SubElement(k1, "fifths").text = "0"
            c1 = ET.SubElement(a1, "clef")
            ET.SubElement(c1, "sign").text = "G"
            ET.SubElement(c1, "line").text = "2"

            # Alto Attributes (Treble G2)
            a2 = ET.SubElement(m_targets["P2"], "attributes")
            ET.SubElement(a2, "divisions").text = str(divs)
            k2 = ET.SubElement(a2, "key")
            ET.SubElement(k2, "fifths").text = "0"
            c2 = ET.SubElement(a2, "clef")
            ET.SubElement(c2, "sign").text = "G"
            ET.SubElement(c2, "line").text = "2"

            # Tenor Attributes (Treble-8vb G2 / octave -1)
            a3 = ET.SubElement(m_targets["P3"], "attributes")
            ET.SubElement(a3, "divisions").text = str(divs)
            k3 = ET.SubElement(a3, "key")
            ET.SubElement(k3, "fifths").text = "0"
            c3 = ET.SubElement(a3, "clef")
            ET.SubElement(c3, "sign").text = "G"
            ET.SubElement(c3, "line").text = "2"
            ET.SubElement(c3, "clef-octave-change").text = "-1"

            # Bass Attributes (Bass F4)
            a4 = ET.SubElement(m_targets["P4"], "attributes")
            ET.SubElement(a4, "divisions").text = str(divs)
            k4 = ET.SubElement(a4, "key")
            ET.SubElement(k4, "fifths").text = "0"
            c4 = ET.SubElement(a4, "clef")
            ET.SubElement(c4, "sign").text = "F"
            ET.SubElement(c4, "line").text = "4"

        # ========================================================
        # NOTE DEMIXING
        # ========================================================
        # Special Bar 19:
        if mnum == 19:
            # Soprano: E4 (384), E4 (768), rest (384), G4 (384), G4 (384)
            # Alto:    C4 (384), D4 (768), rest (384), E4 (384), E4 (384)
            sop_notes = [
                make_pitch_note("E", 4, 384, "quarter"),
                make_pitch_note("E", 4, 768, "half"),
                make_rest_note(384, "quarter"),
                make_pitch_note("G", 4, 384, "quarter"),
                make_pitch_note("G", 4, 384, "quarter"),
            ]
            alt_notes = [
                make_pitch_note("C", 4, 384, "quarter"),
                make_pitch_note("D", 4, 768, "half"),
                make_rest_note(384, "quarter"),
                make_pitch_note("E", 4, 384, "quarter"),
                make_pitch_note("E", 4, 384, "quarter"),
            ]
            # Tenor & Bass from bass clusters
            ten_notes = [
                make_pitch_note("G", 3, 384, "quarter"),
                make_pitch_note("B", 3, 768, "half"),
                make_rest_note(384, "quarter"),
                make_pitch_note("B", 3, 384, "quarter"),
                make_pitch_note("B", 3, 384, "quarter"),
            ]
            bas_notes = [
                make_pitch_note("E", 3, 384, "quarter"),
                make_pitch_note("G", 3, 768, "half"),
                make_rest_note(384, "quarter"),
                make_pitch_note("E", 3, 384, "quarter"),
                make_pitch_note("E", 3, 384, "quarter"),
            ]

        # Special Bar 41:
        elif mnum == 41:
            # Soprano: F5 (1152, dotted half), E5 (384, quarter) with slur
            n_f5 = make_pitch_note("F", 5, 1152, "half", is_dotted=True)
            notations_f5 = ET.SubElement(n_f5, "notations")
            ET.SubElement(notations_f5, "slur", number="1", type="start")

            n_e5 = make_pitch_note("E", 5, 384, "quarter")
            notations_e5 = ET.SubElement(n_e5, "notations")
            ET.SubElement(notations_e5, "slur", number="1", type="stop")

            sop_notes = [n_f5, n_e5]

            # Alto: A4 (768, half), C5 (768, half)
            alt_notes = [
                make_pitch_note("A", 4, 768, "half"),
                make_pitch_note("C", 5, 768, "half"),
            ]

            # Tenor: F4 (768, half), G4 (768, half)
            ten_notes = [
                make_pitch_note("F", 4, 768, "half"),
                make_pitch_note("G", 4, 768, "half"),
            ]

            # Bass: D4 (768, half), C4 (768, half)
            bas_notes = [
                make_pitch_note("D", 4, 768, "half"),
                make_pitch_note("C", 4, 768, "half"),
            ]

        else:
            # Standard Demixing from clusters
            treble_clusters = parse_measure_clusters(m_treble_src)
            bass_clusters = parse_measure_clusters(m_bass_src)

            sop_notes = []
            alt_notes = []
            for cl in treble_clusters:
                if len(cl) == 1:
                    n = cl[0]
                    sop_notes.append(clean_note_element(n))
                    alt_notes.append(clean_note_element(n))
                else:
                    cl.sort(key=get_midi)
                    alt_notes.append(clean_note_element(cl[0]))
                    sop_notes.append(clean_note_element(cl[-1]))

            ten_notes = []
            bas_notes = []
            for cl in bass_clusters:
                if len(cl) == 1:
                    n = cl[0]
                    ten_notes.append(clean_note_element(n))
                    bas_notes.append(clean_note_element(n))
                else:
                    cl.sort(key=get_midi)
                    bas_notes.append(clean_note_element(cl[0]))
                    ten_notes.append(clean_note_element(cl[-1]))

        # Apply Tuplets across ALL 4 parts
        if mnum in TUPLET_SPEC:
            for n_list in (sop_notes, alt_notes, ten_notes, bas_notes):
                apply_tuplet_spec_to_notes(n_list, TUPLET_SPEC[mnum])

        # Preserve Ties on Bar 51
        if mnum == 51:
            for n_list in (sop_notes, alt_notes, ten_notes, bas_notes):
                if len(n_list) >= 4:
                    n2 = n_list[2]
                    n3 = n_list[3]

                    dur_idx2 = None
                    for idx, ch in enumerate(n2):
                        if ch.tag == "duration":
                            dur_idx2 = idx
                            break
                    if dur_idx2 is not None:
                        n2.insert(dur_idx2 + 1, ET.Element("tie", type="start"))
                    else:
                        n2.append(ET.Element("tie", type="start"))

                    dur_idx3 = None
                    for idx, ch in enumerate(n3):
                        if ch.tag == "duration":
                            dur_idx3 = idx
                            break
                    if dur_idx3 is not None:
                        n3.insert(dur_idx3 + 1, ET.Element("tie", type="stop"))
                    else:
                        n3.append(ET.Element("tie", type="stop"))

                    notations2 = n2.find("notations")
                    if notations2 is None:
                        notations2 = ET.SubElement(n2, "notations")
                    ET.SubElement(notations2, "tied", type="start")

                    notations3 = n3.find("notations")
                    if notations3 is None:
                        notations3 = ET.SubElement(n3, "notations")
                    ET.SubElement(notations3, "tied", type="stop")

        # Fermatas on Bars 42, 44, 54
        if mnum in (42, 44, 54):
            for n_list in (sop_notes, alt_notes, ten_notes, bas_notes):
                target_note = None
                if mnum == 42 and n_list:
                    target_note = n_list[0]
                elif mnum == 44 and len(n_list) >= 2:
                    target_note = n_list[1]
                elif mnum == 54 and n_list:
                    target_note = n_list[0]

                if target_note is not None:
                    notations = target_note.find("notations")
                    if notations is None:
                        notations = ET.SubElement(target_note, "notations")
                    if notations.find("fermata") is None:
                        ET.SubElement(notations, "fermata", type="upright")

        # Attach Lyrics to ALL 4 parts
        measure_syls = lyrics_by_measure.get(mnum, [])
        if mnum == 41:
            # S, A, T, B get "bo" on first note
            for n_list in (sop_notes, alt_notes, ten_notes, bas_notes):
                n = n_list[0]
                lyr = ET.SubElement(n, "lyric", number="1")
                ET.SubElement(lyr, "syllabic").text = "middle"
                ET.SubElement(lyr, "text").text = "bo"
        else:
            # Pair sung notes with syllables
            for n_list in (sop_notes, alt_notes, ten_notes, bas_notes):
                sung_notes = [n for n in n_list if n.find("rest") is None]
                if len(sung_notes) == len(measure_syls):
                    for n, (txt, syl) in zip(sung_notes, measure_syls):
                        lyr = ET.SubElement(n, "lyric", number="1")
                        ET.SubElement(lyr, "syllabic").text = syl
                        ET.SubElement(lyr, "text").text = txt
                elif sung_notes:
                    # Fallback zip if count slightly differs
                    for n, (txt, syl) in zip(sung_notes[: len(measure_syls)], measure_syls):
                        lyr = ET.SubElement(n, "lyric", number="1")
                        ET.SubElement(lyr, "syllabic").text = syl
                        ET.SubElement(lyr, "text").text = txt

        # Directions and measure assembly
        p1_dirs, p3_dirs = get_measure_directions(mnum, m_treble_src, m_bass_src)
        part_dirs = {"P1": p1_dirs, "P2": {}, "P3": p3_dirs, "P4": {}}
        part_notes = {"P1": sop_notes, "P2": alt_notes, "P3": ten_notes, "P4": bas_notes}

        for pid in ("P1", "P2", "P3", "P4"):
            p_notes = part_notes[pid]
            p_dirs = part_dirs[pid]
            for idx in range(len(p_notes)):
                if idx in p_dirs:
                    for d in p_dirs[idx]:
                        m_targets[pid].append(copy.deepcopy(d))
                m_targets[pid].append(p_notes[idx])
            if len(p_notes) in p_dirs:
                for d in p_dirs[len(p_notes)]:
                    m_targets[pid].append(copy.deepcopy(d))

            for bl in m_treble_src.findall("barline"):
                m_targets[pid].append(copy.deepcopy(bl))

    # Save output XML
    output_xml.parent.mkdir(parents=True, exist_ok=True)
    xml_bytes = ET.tostring(new_root, encoding="utf-8", xml_declaration=True)
    with open(output_xml, "wb") as f:
        f.write(xml_bytes)
    print(f"Successfully generated SATB MusicXML: {output_xml}")


if __name__ == "__main__":
    in_file = Path(sys.argv[1] if len(sys.argv) > 1 else "~/Downloads/Mary at the Tomb (Callaway) - 2026-03-09.xml").expanduser()
    out_file = Path(sys.argv[2] if len(sys.argv) > 2 else "~/Downloads/Mary at the Tomb (Callaway) - SATB.xml").expanduser()
    build_satb_score(in_file, out_file)
