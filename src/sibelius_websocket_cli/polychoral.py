"""Polychoral and multi-voice choral demixing engine.

Audits, splits, and demixes complex choral scores (including 2-choir, 16-voice
scores with alternating open-score and short-score layouts) into 16 discrete vocal
staves with independent MIDI channels, appropriate choral clefs, and preserved lyrics.
"""

from __future__ import annotations

import copy
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any

SEMITONES = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}

# 16-voice target metadata: (ID, Name, Abbr, Clef_Sign, Clef_Line, Clef_Octave, Sound_ID, MIDI_Channel)
PARTS_16_META = [
    # Choir 1
    ("C1_S1", "Choir 1 Soprano 1", "C1 S1", "G", "2", None, "voice.soprano", "1"),
    ("C1_S2", "Choir 1 Soprano 2", "C1 S2", "G", "2", None, "voice.soprano", "2"),
    ("C1_A1", "Choir 1 Alto 1", "C1 A1", "G", "2", None, "voice.alto", "3"),
    ("C1_A2", "Choir 1 Alto 2", "C1 A2", "G", "2", None, "voice.alto", "4"),
    ("C1_T1", "Choir 1 Tenor 1", "C1 T1", "G", "2", "-1", "voice.tenor", "5"),
    ("C1_T2", "Choir 1 Tenor 2", "C1 T2", "G", "2", "-1", "voice.tenor", "6"),
    ("C1_B1", "Choir 1 Bass 1", "C1 B1", "F", "4", None, "voice.bass", "7"),
    ("C1_B2", "Choir 1 Bass 2", "C1 B2", "F", "4", None, "voice.bass", "8"),
    # Choir 2
    ("C2_S1", "Choir 2 Soprano 1", "C2 S1", "G", "2", None, "voice.soprano", "9"),
    ("C2_S2", "Choir 2 Soprano 2", "C2 S2", "G", "2", None, "voice.soprano", "10"),
    ("C2_A1", "Choir 2 Alto 1", "C2 A1", "G", "2", None, "voice.alto", "11"),
    ("C2_A2", "Choir 2 Alto 2", "C2 A2", "G", "2", None, "voice.alto", "12"),
    ("C2_T1", "Choir 2 Tenor 1", "C2 T1", "G", "2", "-1", "voice.tenor", "13"),
    ("C2_T2", "Choir 2 Tenor 2", "C2 T2", "G", "2", "-1", "voice.tenor", "14"),
    ("C2_B1", "Choir 2 Bass 1", "C2 B1", "F", "4", None, "voice.bass", "15"),
    ("C2_B2", "Choir 2 Bass 2", "C2 B2", "F", "4", None, "voice.bass", "16"),
]


def get_midi(note: ET.Element) -> int:
    """Calculate MIDI pitch from a MusicXML note element. Returns -1 for rests."""
    p = note.find("pitch")
    if p is None:
        return -1
    step_elem = p.find("step")
    octave_elem = p.find("octave")
    if step_elem is None or octave_elem is None or not step_elem.text or not octave_elem.text:
        return -1
    step = step_elem.text
    octave = int(octave_elem.text)
    alter_elem = p.find("alter")
    alter = int(alter_elem.text) if (alter_elem is not None and alter_elem.text) else 0
    return 12 * (octave + 1) + SEMITONES.get(step, 0) + alter


NOTE_TAG_ORDER = [
    "grace",
    "cue",
    "chord",
    "pitch",
    "rest",
    "unpitched",
    "duration",
    "tie",
    "instrument",
    "footnote",
    "level",
    "voice",
    "type",
    "dot",
    "accidental",
    "time-modification",
    "stem",
    "notehead",
    "notehead-text",
    "staff",
    "beam",
    "notations",
    "lyric",
    "play",
    "listen",
]


def insert_note_child(note: ET.Element, child: ET.Element) -> None:
    """Insert a child into a note element respecting strict MusicXML schema order."""
    child_rank = NOTE_TAG_ORDER.index(child.tag) if child.tag in NOTE_TAG_ORDER else 999
    insert_idx = len(note)
    for idx, existing in enumerate(note):
        existing_rank = (
            NOTE_TAG_ORDER.index(existing.tag) if existing.tag in NOTE_TAG_ORDER else 999
        )
        if existing_rank > child_rank:
            insert_idx = idx
            break
    note.insert(insert_idx, child)


def clean_note(
    note: ET.Element,
    base_dur: str | None = None,
    is_grace: bool = False,
    voice: str = "1",
) -> ET.Element:
    """Clean a note for a discrete single-voice staff, removing chord, staff, and instrument tags."""
    n = copy.deepcopy(note)
    for tag in ("staff", "chord", "stem", "instrument"):
        el = n.find(tag)
        if el is not None:
            n.remove(el)
    if is_grace or n.find("grace") is not None:
        if n.find("grace") is None:
            g = ET.Element("grace")
            n.insert(0, g)
        else:
            g = n.find("grace")
            if list(n).index(g) != 0:
                n.remove(g)
                n.insert(0, g)
        d = n.find("duration")
        if d is not None:
            n.remove(d)
    elif base_dur is not None:
        d = n.find("duration")
        if d is not None:
            d.text = base_dur
    v = n.find("voice")
    if v is not None:
        v.text = voice
    else:
        v_elem = ET.Element("voice")
        v_elem.text = voice
        insert_note_child(n, v_elem)
    return n


def make_rest(measure_dur: int, voice: str = "1") -> ET.Element:
    """Create a whole-measure rest element matching measure_dur."""
    note = ET.Element("note")
    rest = ET.SubElement(note, "rest")
    rest.attrib["measure"] = "yes"
    dur = ET.SubElement(note, "duration")
    dur.text = str(measure_dur)
    v = ET.SubElement(note, "voice")
    v.text = voice
    return note


def get_chord_clusters(notes: list[ET.Element]) -> list[list[ET.Element]]:
    """Group contiguous notes sharing a rhythmic onset into chord clusters and clone lyrics."""
    clusters: list[list[ET.Element]] = []
    curr: list[ET.Element] = []
    for n in notes:
        if n.find("chord") is not None:
            curr.append(n)
        else:
            if curr:
                clusters.append(curr)
            curr = [n]
    if curr:
        clusters.append(curr)

    # Propagate lyrics across all chord notes in the cluster and harmonize grace attributes
    for c in clusters:
        is_grace = any(n.find("grace") is not None for n in c)
        if is_grace:
            for n in c:
                if n.find("grace") is None:
                    g = ET.Element("grace")
                    n.insert(0, g)
                else:
                    g = n.find("grace")
                    if list(n).index(g) != 0:
                        n.remove(g)
                        n.insert(0, g)
                d = n.find("duration")
                if d is not None:
                    n.remove(d)

        lyrics = []
        for n in c:
            for lyr in n.findall("lyric"):
                lyrics.append(copy.deepcopy(lyr))
        if lyrics:
            for n in c:
                if not n.findall("lyric"):
                    for lyr in lyrics:
                        n.append(copy.deepcopy(lyr))
    return clusters


def pad_or_trim_duration(notes: list[ET.Element], expected_dur: int) -> list[ET.Element]:
    """Ensure that the total note/rest duration in a measure precisely matches expected_dur."""
    if not notes:
        return [make_rest(expected_dur)]

    dur_sum = sum(
        int(n.find("duration").text)
        for n in notes
        if n.find("grace") is None and n.find("duration") is not None and n.find("duration").text
    )

    if dur_sum == expected_dur:
        return notes
    elif dur_sum < expected_dur:
        diff = expected_dur - dur_sum
        r = ET.Element("note")
        ET.SubElement(r, "rest")
        d = ET.SubElement(r, "duration")
        d.text = str(diff)
        ET.SubElement(r, "voice").text = "1"
        return notes + [r]
    else:
        # Slight overflow from rounding or tuplet discrepancies: trim excess
        diff = dur_sum - expected_dur
        for n in reversed(notes):
            if n.find("grace") is not None:
                continue
            d = n.find("duration")
            if d is not None and d.text:
                val = int(d.text)
                if val > diff:
                    d.text = str(val - diff)
                    diff = 0
                    break
                elif val == diff and n.find("rest") is not None:
                    # remove exact match rest
                    notes.remove(n)
                    diff = 0
                    break
        return notes


def demix_single_staff(notes: list[ET.Element], m_dur: int) -> tuple[list[ET.Element], list[ET.Element]]:
    """Demix a staff into upper (Part 1) and lower (Part 2) parts."""
    if not notes or all(n.find("rest") is not None for n in notes):
        r1, r2 = [make_rest(m_dur)], [make_rest(m_dur)]
        return r1, r2

    v1 = [n for n in notes if n.find("voice") is not None and n.find("voice").text == "1"]
    v2 = [n for n in notes if n.find("voice") is not None and n.find("voice").text in ("2", "3", "4")]

    if v1 and v2:
        c1 = get_chord_clusters(v1)
        c2 = get_chord_clusters(v2)
        p1 = [
            clean_note(c[-1], c[0].find("duration").text if c[0].find("duration") is not None else None)
            for c in c1
        ]
        p2 = [
            clean_note(c[0], c[0].find("duration").text if c[0].find("duration") is not None else None)
            for c in c2
        ]
        return pad_or_trim_duration(p1, m_dur), pad_or_trim_duration(p2, m_dur)

    clusters = get_chord_clusters(notes)
    has_chords = any(len(c) > 1 for c in clusters)
    if has_chords:
        p1 = []
        p2 = []
        for c in clusters:
            base_dur = c[0].find("duration").text if c[0].find("duration") is not None else None
            if len(c) > 1:
                c.sort(key=get_midi)
                p1.append(clean_note(c[-1], base_dur))
                p2.append(clean_note(c[0], base_dur))
            else:
                p1.append(clean_note(c[0], base_dur))
                p2.append(clean_note(c[0], base_dur))
        return pad_or_trim_duration(p1, m_dur), pad_or_trim_duration(p2, m_dur)
    else:
        # Unison melody
        p1 = [
            clean_note(c[0], c[0].find("duration").text if c[0].find("duration") is not None else None)
            for c in clusters
        ]
        p2 = [
            clean_note(c[0], c[0].find("duration").text if c[0].find("duration") is not None else None)
            for c in clusters
        ]
        return pad_or_trim_duration(p1, m_dur), pad_or_trim_duration(p2, m_dur)


def demix_reduction_staff(
    notes: list[ET.Element], m_dur: int
) -> tuple[list[ET.Element], list[ET.Element], list[ET.Element], list[ET.Element]]:
    """Demix a 2-part reduction staff (SA or TB) into 4 parts:
    e.g. S1, S2, A1, A2 from Treble staff, or T1, T2, B1, B2 from Bass staff.
    """
    if not notes or all(n.find("rest") is not None for n in notes):
        r = [make_rest(m_dur)]
        return copy.deepcopy(r), copy.deepcopy(r), copy.deepcopy(r), copy.deepcopy(r)

    voices = sorted(
        list(
            set(
                n.find("voice").text
                for n in notes
                if n.find("voice") is not None and n.find("voice").text
            )
        )
    )

    if len(voices) >= 2:
        v_upper = [n for n in notes if n.find("voice") is not None and n.find("voice").text == voices[0]]
        v_lower = [n for n in notes if n.find("voice") is not None and n.find("voice").text == voices[-1]]
        v_mid = [
            n
            for n in notes
            if n.find("voice") is not None and n.find("voice").text not in (voices[0], voices[-1])
        ]

        if v_mid:
            p1 = [
                clean_note(
                    c[-1], c[0].find("duration").text if c[0].find("duration") is not None else None
                )
                for c in get_chord_clusters(v_upper)
            ]
            p2 = [
                clean_note(
                    c[-1], c[0].find("duration").text if c[0].find("duration") is not None else None
                )
                for c in get_chord_clusters(v_mid)
            ]
            p3_c, p4_c = demix_single_staff(v_lower, m_dur)
            return (
                pad_or_trim_duration(p1, m_dur),
                pad_or_trim_duration(p2, m_dur),
                pad_or_trim_duration(p3_c, m_dur),
                pad_or_trim_duration(p4_c, m_dur),
            )
        else:
            p1, p2 = demix_single_staff(v_upper, m_dur)
            p3, p4 = demix_single_staff(v_lower, m_dur)
            return p1, p2, p3, p4
    else:
        clusters = get_chord_clusters(notes)
        p1, p2, p3, p4 = [], [], [], []
        for c in clusters:
            base_dur = c[0].find("duration").text if c[0].find("duration") is not None else None
            if n_rest := [n for n in c if n.find("rest") is not None]:
                for p in (p1, p2, p3, p4):
                    p.append(clean_note(n_rest[0], base_dur))
                continue
            c.sort(key=get_midi)
            if len(c) >= 4:
                p1.append(clean_note(c[-1], base_dur))
                p2.append(clean_note(c[-2], base_dur))
                p3.append(clean_note(c[1], base_dur))
                p4.append(clean_note(c[0], base_dur))
            elif len(c) == 3:
                p1.append(clean_note(c[-1], base_dur))
                p2.append(clean_note(c[-2], base_dur))
                p3.append(clean_note(c[0], base_dur))
                p4.append(clean_note(c[0], base_dur))
            elif len(c) == 2:
                p1.append(clean_note(c[1], base_dur))
                p2.append(clean_note(c[1], base_dur))
                p3.append(clean_note(c[0], base_dur))
                p4.append(clean_note(c[0], base_dur))
            else:
                for p in (p1, p2, p3, p4):
                    p.append(clean_note(c[0], base_dur))
        return (
            pad_or_trim_duration(p1, m_dur),
            pad_or_trim_duration(p2, m_dur),
            pad_or_trim_duration(p3, m_dur),
            pad_or_trim_duration(p4, m_dur),
        )


def build_16voice_part_list() -> ET.Element:
    """Construct a clean 16-part MusicXML part-list element with two bracketed choir groups."""
    plist = ET.Element("part-list")

    # Choir 1 Group
    c1_group = ET.SubElement(plist, "part-group", number="1", type="start")
    ET.SubElement(c1_group, "group-name").text = "Choir 1"
    ET.SubElement(c1_group, "group-symbol").text = "bracket"
    ET.SubElement(c1_group, "group-barline").text = "yes"

    for pid, pname, abbr, _, _, _, sound_id, chan in PARTS_16_META[:8]:
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

    # Choir 2 Group
    c2_group = ET.SubElement(plist, "part-group", number="2", type="start")
    ET.SubElement(c2_group, "group-name").text = "Choir 2"
    ET.SubElement(c2_group, "group-symbol").text = "bracket"
    ET.SubElement(c2_group, "group-barline").text = "yes"

    for pid, pname, abbr, _, _, _, sound_id, chan in PARTS_16_META[8:]:
        sp = ET.SubElement(plist, "score-part", id=pid)
        ET.SubElement(sp, "part-name").text = pname
        ET.SubElement(sp, "part-abbreviation").text = abbr
        instr = ET.SubElement(sp, "score-instrument", id=f"{pid}-I1")
        ET.SubElement(instr, "instrument-name").text = pname
        ET.SubElement(instr, "instrument-sound").text = sound_id
        midi = ET.SubElement(sp, "midi-instrument", id=f"{pid}-I1")
        ET.SubElement(midi, "midi-channel").text = chan
        ET.SubElement(midi, "midi-program").text = "53"  # Choir Aahs

    ET.SubElement(plist, "part-group", number="2", type="stop")
    return plist


def parse_musicxml(path: Path) -> tuple[ET.ElementTree, ET.Element]:
    """Load MusicXML from .xml or .mxl."""
    if path.suffix.lower() == ".mxl":
        with zipfile.ZipFile(path, "r") as z:
            root_name = None
            if "META-INF/container.xml" in z.namelist():
                c_tree = ET.parse(z.open("META-INF/container.xml"))
                for rf in c_tree.findall(".//rootfile"):
                    root_name = rf.attrib.get("full-path")
                    break
            if not root_name:
                for name in z.namelist():
                    if name.endswith(".xml") and not name.startswith("META-INF"):
                        root_name = name
                        break
            if not root_name:
                raise ValueError(f"No score XML file found in archive {path}")
            with z.open(root_name) as f:
                tree = ET.parse(f)
                return tree, tree.getroot()
    else:
        tree = ET.parse(path)
        return tree, tree.getroot()


def save_musicxml(root: ET.Element, out_path: Path) -> None:
    """Save root Element to .xml or .mxl."""
    score_xml_bytes = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if out_path.suffix.lower() == ".mxl":
        container_xml = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="score.xml" media-type="application/vnd.recordare.musicxml+xml"/>
  </rootfiles>
</container>"""
        with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr("META-INF/container.xml", container_xml)
            z.writestr("score.xml", score_xml_bytes)
    else:
        with open(out_path, "wb") as f:
            f.write(score_xml_bytes)


def build_attributes(
    orig_attr: ET.Element | None, sign: str, line: str, octave: str | None
) -> ET.Element:
    """Build a schema-compliant attributes element with clef placed in proper order."""
    attr = ET.Element("attributes")
    clef_elem = ET.Element("clef")
    ET.SubElement(clef_elem, "sign").text = sign
    ET.SubElement(clef_elem, "line").text = line
    if octave is not None:
        ET.SubElement(clef_elem, "clef-octave-change").text = octave

    if orig_attr is None:
        attr.append(clef_elem)
        return attr

    clef_inserted = False
    for child in orig_attr:
        if child.tag in ("clef", "staves"):
            continue
        if not clef_inserted and child.tag in (
            "staff-details",
            "transpose",
            "for-part",
            "directive",
            "measure-style",
        ):
            attr.append(clef_elem)
            clef_inserted = True
        attr.append(copy.deepcopy(child))

    if not clef_inserted:
        attr.append(clef_elem)

    return attr


def heal_ties(root: ET.Element) -> tuple[int, int]:
    """Ensure every start tie connects to a matching pitch and prune dangling ties."""
    stops_added = 0
    dangling_removed = 0
    for part in root.findall("part"):
        notes = []
        for m in part.findall("measure"):
            for n in m.findall("note"):
                if n.find("grace") is None and n.find("rest") is None:
                    notes.append((m.attrib.get("number"), n))
        for i in range(len(notes) - 1):
            _, n1 = notes[i]
            _, n2 = notes[i + 1]
            p1 = get_midi(n1)
            p2 = get_midi(n2)
            has_start = any(
                t.attrib.get("type") == "start"
                for t in n1.findall("tie") + n1.findall(".//tied")
            )
            if has_start:
                if p1 == p2:
                    if not any(t.attrib.get("type") == "stop" for t in n2.findall("tie")):
                        tie_elem = ET.Element("tie", type="stop")
                        insert_note_child(n2, tie_elem)
                        notations = n2.find("notations")
                        if notations is None:
                            notations = ET.Element("notations")
                            insert_note_child(n2, notations)
                        ET.SubElement(notations, "tied", type="stop")
                        stops_added += 1
                else:
                    for t in list(n1.findall("tie")):
                        if t.attrib.get("type") == "start":
                            n1.remove(t)
                            dangling_removed += 1
                    notations = n1.find("notations")
                    if notations is not None:
                        for td in list(notations.findall("tied")):
                            if td.attrib.get("type") == "start":
                                notations.remove(td)
        if notes:
            _, last_n = notes[-1]
            for t in list(last_n.findall("tie")):
                if t.attrib.get("type") == "start":
                    last_n.remove(t)
                    dangling_removed += 1
            notations = last_n.find("notations")
            if notations is not None:
                for td in list(notations.findall("tied")):
                    if td.attrib.get("type") == "start":
                        notations.remove(td)

    return stops_added, dangling_removed


def demix_16voices(
    in_path: Path | str,
    out_path: Path | str,
    choir_unison_indices: set[int] | None = None,
) -> dict[str, Any]:
    """Demix a 12-staff polychoral score into 16 discrete parts.

    Handles alternating open score (P1-P8) and short score (P9, P11),
    clef configuration, tie preservation, lyric propagation, and duration normalization.
    """
    in_p = Path(in_path)
    out_p = Path(out_path)

    tree, root = parse_musicxml(in_p)
    parts = {p.attrib["id"]: p for p in root.findall("part")}

    if not parts:
        raise ValueError("No parts found in input MusicXML")

    p1_measures = list(parts.values())[0].findall("measure")
    total_measures = len(p1_measures)

    # Precompute actual measure duration per measure index
    measure_durations = []
    for i in range(total_measures):
        dur = None
        for p in parts.values():
            m = p.findall("measure")[i]
            notes = [
                n
                for n in m.findall("note")
                if n.find("chord") is None
                and (n.find("voice") is None or n.find("voice").text in ("1", "4"))
            ]
            if notes:
                d = sum(int(n.find("duration").text) for n in notes if n.find("duration") is not None)
                if d > 0:
                    dur = d
                    break
        measure_durations.append(dur if dur is not None else 1024)

    # Initialize 16 target parts
    target_parts: dict[str, ET.Element] = {
        meta[0]: ET.Element("part", id=meta[0]) for meta in PARTS_16_META
    }

    # Default unison doubling ranges if not provided:
    # 0-26 (Bars 1-27) and 36-39 (Bars 37-40) in Clamavi
    if choir_unison_indices is None:
        choir_unison_indices = set(range(0, 27)) | set(range(36, 40))

    meta_by_id = {meta[0]: meta for meta in PARTS_16_META}

    for i in range(total_measures):
        m_dur = measure_durations[i]
        sample_measure = p1_measures[i]
        mnum_str = sample_measure.attrib.get("number", str(i))

        # Check for short layout
        p9 = parts.get("P9")
        p11 = parts.get("P11")
        p9_m = p9.findall("measure")[i] if p9 is not None else None
        p11_m = p11.findall("measure")[i] if p11 is not None else None

        p9_notes = [n for n in p9_m.findall("note") if n.find("rest") is None] if p9_m is not None else []
        p11_notes = [n for n in p11_m.findall("note") if n.find("rest") is None] if p11_m is not None else []
        is_short = bool(p9_notes or p11_notes)

        step_res: dict[str, list[ET.Element]] = {}

        if is_short and p9_m is not None and p11_m is not None:
            # Demix Choir 1 from P9
            s1_p9 = [
                n
                for n in p9_m.findall("note")
                if (n.find("staff") is not None and n.find("staff").text == "1") or n.find("staff") is None
            ]
            s2_p9 = [
                n
                for n in p9_m.findall("note")
                if n.find("staff") is not None and n.find("staff").text == "2"
            ]
            c1_s1, c1_s2, c1_a1, c1_a2 = demix_reduction_staff(s1_p9, m_dur)
            c1_t1, c1_t2, c1_b1, c1_b2 = demix_reduction_staff(s2_p9, m_dur)
            step_res["C1_S1"], step_res["C1_S2"], step_res["C1_A1"], step_res["C1_A2"] = (
                c1_s1,
                c1_s2,
                c1_a1,
                c1_a2,
            )
            step_res["C1_T1"], step_res["C1_T2"], step_res["C1_B1"], step_res["C1_B2"] = (
                c1_t1,
                c1_t2,
                c1_b1,
                c1_b2,
            )

            # Demix Choir 2 from P11
            if i in choir_unison_indices or i == 35:
                for k in ["S1", "S2", "A1", "A2", "T1", "T2", "B1", "B2"]:
                    step_res[f"C2_{k}"] = copy.deepcopy(step_res[f"C1_{k}"])
            else:
                s1_p11 = [
                    n
                    for n in p11_m.findall("note")
                    if (n.find("staff") is not None and n.find("staff").text == "1")
                    or n.find("staff") is None
                ]
                s2_p11 = [
                    n
                    for n in p11_m.findall("note")
                    if n.find("staff") is not None and n.find("staff").text == "2"
                ]
                c2_s1, c2_s2, c2_a1, c2_a2 = demix_reduction_staff(s1_p11, m_dur)
                c2_t1, c2_t2, c2_b1, c2_b2 = demix_reduction_staff(s2_p11, m_dur)
                step_res["C2_S1"], step_res["C2_S2"], step_res["C2_A1"], step_res["C2_A2"] = (
                    c2_s1,
                    c2_s2,
                    c2_a1,
                    c2_a2,
                )
                step_res["C2_T1"], step_res["C2_T2"], step_res["C2_B1"], step_res["C2_B2"] = (
                    c2_t1,
                    c2_t2,
                    c2_b1,
                    c2_b2,
                )
        else:
            # Open layout from P1-P8
            p1_m = parts["P1"].findall("measure")[i]
            p2_m = parts["P2"].findall("measure")[i]
            p3_m = parts["P3"].findall("measure")[i]
            p4_m = parts["P4"].findall("measure")[i]

            step_res["C1_S1"], step_res["C1_S2"] = demix_single_staff(p1_m.findall("note"), m_dur)
            step_res["C1_A1"], step_res["C1_A2"] = demix_single_staff(p2_m.findall("note"), m_dur)
            step_res["C1_T1"], step_res["C1_T2"] = demix_single_staff(p3_m.findall("note"), m_dur)
            step_res["C1_B1"], step_res["C1_B2"] = demix_single_staff(p4_m.findall("note"), m_dur)

            p5_8_notes = any(
                [
                    n
                    for n in parts[f"P{j}"].findall("measure")[i].findall("note")
                    if n.find("rest") is None
                ]
                for j in range(5, 9)
                if f"P{j}" in parts
            )

            if p5_8_notes:
                step_res["C2_S1"], step_res["C2_S2"] = demix_single_staff(
                    parts["P5"].findall("measure")[i].findall("note"), m_dur
                )
                step_res["C2_A1"], step_res["C2_A2"] = demix_single_staff(
                    parts["P6"].findall("measure")[i].findall("note"), m_dur
                )
                step_res["C2_T1"], step_res["C2_T2"] = demix_single_staff(
                    parts["P7"].findall("measure")[i].findall("note"), m_dur
                )
                step_res["C2_B1"], step_res["C2_B2"] = demix_single_staff(
                    parts["P8"].findall("measure")[i].findall("note"), m_dur
                )
            elif i in choir_unison_indices:
                for k in ["S1", "S2", "A1", "A2", "T1", "T2", "B1", "B2"]:
                    step_res[f"C2_{k}"] = copy.deepcopy(step_res[f"C1_{k}"])
            else:
                for k in ["S1", "S2", "A1", "A2", "T1", "T2", "B1", "B2"]:
                    step_res[f"C2_{k}"] = [make_rest(m_dur)]

        # Append measures to target parts with clef and attributes
        for meta in PARTS_16_META:
            pid = meta[0]
            m_new = ET.SubElement(target_parts[pid], "measure", number=mnum_str)
            if "implicit" in sample_measure.attrib:
                m_new.attrib["implicit"] = sample_measure.attrib["implicit"]

            # Attributes & Clefs
            orig_attr = sample_measure.find("attributes")
            if orig_attr is not None or i == 0:
                m_new.append(build_attributes(orig_attr, meta[3], meta[4], meta[5]))

            # Copy non-print measure children (barlines, directions)
            for el in sample_measure:
                if el.tag == "barline":
                    m_new.append(copy.deepcopy(el))
                elif el.tag == "direction" and pid in ("C1_S1", "C2_S1"):
                    d_copy = copy.deepcopy(el)
                    s_copy = d_copy.find("staff")
                    if s_copy is not None:
                        d_copy.remove(s_copy)
                    m_new.append(d_copy)

            # Append demixed notes
            notes = step_res.get(pid, [make_rest(m_dur)])
            for n in notes:
                m_new.append(n)

    # Build new score root
    for child in list(root):
        if child.tag in ("part-list", "part"):
            root.remove(child)

    root.append(build_16voice_part_list())
    for pid, part_elem in target_parts.items():
        root.append(part_elem)

    heal_ties(root)

    save_musicxml(root, out_p)

    return {
        "inputFile": str(in_p),
        "outputFile": str(out_p),
        "totalMeasures": total_measures,
        "partsCount": len(target_parts),
        "parts": list(target_parts.keys()),
    }


def validate_16voices(path: Path | str) -> list[str]:
    """Validate measure durations and consistency across all 16 parts in a score."""
    p = Path(path)
    if not p.exists():
        return [f"File not found: {p}"]

    _, root = parse_musicxml(p)
    parts = root.findall("part")
    if len(parts) != 16:
        return [f"Expected 16 parts, found {len(parts)}"]

    issues: list[str] = []
    p0_measures = parts[0].findall("measure")
    total_m = len(p0_measures)

    for i in range(total_m):
        m_durs = {}
        for part in parts:
            pid = part.attrib.get("id", "unknown")
            measures = part.findall("measure")
            if len(measures) <= i:
                issues.append(f"Part {pid} missing measure index {i}")
                continue
            m = measures[i]
            dur_sum = 0
            for n in m.findall("note"):
                if n.find("chord") is not None:
                    continue
                d = n.find("duration")
                if d is not None and d.text:
                    dur_sum += int(d.text)
            m_durs[pid] = dur_sum

        # Check consistency
        distinct = set(m_durs.values())
        if len(distinct) > 1:
            issues.append(
                f"Measure index {i} (num {p0_measures[i].attrib.get('number')}): duration discrepancy across parts: {m_durs}"
            )

    return issues
