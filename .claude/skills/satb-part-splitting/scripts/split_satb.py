#!/usr/bin/env python3
"""Audit, split, and validate 2-staff choral/piano scores into 4-staff SATB scores.

Supports both uncompressed .xml and compressed .mxl MusicXML files.
"""

from __future__ import annotations

import argparse
import copy
import os
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any

# The skill remains runnable with plain ``python3`` from a source checkout.
REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))


SEMITONES = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


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


def make_rest_measure(measure_num: str | int, divisions: int, beats: int, beat_type: int) -> ET.Element:
    """Create a whole-measure rest note element."""
    total_dur = int(beats * (4.0 / beat_type) * divisions)
    note = ET.Element("note")
    rest = ET.SubElement(note, "rest")
    rest.attrib["measure"] = "yes"
    dur = ET.SubElement(note, "duration")
    dur.text = str(total_dur)
    v = ET.SubElement(note, "voice")
    v.text = "1"
    return note


def clean_note_element(note: ET.Element) -> ET.Element:
    """Strip staff, chord, and stem direction tags, normalizing voice to 1."""
    n = copy.deepcopy(note)
    for tag in ("staff", "chord", "stem"):
        elem = n.find(tag)
        if elem is not None:
            n.remove(elem)
    v = n.find("voice")
    if v is not None:
        v.text = "1"
    else:
        v = ET.SubElement(n, "voice")
        v.text = "1"
    return n


def flatten_voice_chords(notes: list[ET.Element], select_top: bool = True) -> list[ET.Element]:
    """Given a list of note elements for a single voice stream, flatten any chord clusters."""
    result = []
    i = 0
    while i < len(notes):
        n = notes[i]
        cluster = [n]
        j = i + 1
        while j < len(notes) and notes[j].find("chord") is not None:
            cluster.append(notes[j])
            j += 1

        if len(cluster) == 1:
            result.append(clean_note_element(n))
        else:
            cluster.sort(key=get_midi)
            chosen = copy.deepcopy(cluster[-1] if select_top else cluster[0])
            ch = chosen.find("chord")
            if ch is not None:
                chosen.remove(ch)
            if not chosen.findall("lyric"):
                for other in cluster:
                    if other.findall("lyric"):
                        for lyr in other.findall("lyric"):
                            chosen.append(copy.deepcopy(lyr))
                        break
            result.append(clean_note_element(chosen))
        i = j
    return result


def load_english_lexicon() -> set[str]:
    """Load standard words from macOS dictionary plus common choral terms."""
    words = set()
    dict_path = Path("/usr/share/dict/words")
    if dict_path.exists():
        with open(dict_path, "r", errors="ignore") as f:
            for line in f:
                w = line.strip().lower()
                if len(w) > 1:
                    words.add(w)
    words.update([
        "stories", "scenes", "dreams", "weaving", "perfect", "precious",
        "lonely", "pretty", "shining", "children", "forever", "together",
        "loneliness", "inside", "plenty", "delight", "treasure", "concerned",
        "spending", "pleasing", "collected", "guitar", "fairy", "after", "ago"
    ])
    return words


def reconnect_lyrics_in_root(root: ET.Element) -> int:
    """Reconnect shattered OMR syllables across all parts into begin/middle/end words."""
    import re
    dict_words = load_english_lexicon()
    stopwords = {"to", "be", "in", "on", "at", "as", "is", "it", "so", "no", "we", "he", "me", "my", "of", "and", "the", "a", "all", "one", "for", "her", "was", "long"}
    total_reconnected = 0

    for part in root.findall("part"):
        tokens = []
        for m in part.findall("measure"):
            for n in m.findall(".//note"):
                lyrs = n.findall("lyric")
                if lyrs:
                    lyr = lyrs[0]
                    t_elem = lyr.find("text")
                    txt = t_elem.text if (t_elem is not None and t_elem.text) else ""
                    clean = re.sub(r"[^a-zA-Z]", "", txt).lower()
                    tokens.append((lyr, txt, clean))

        i = 0
        while i < len(tokens):
            # Try 3-syllables (e.g. won-der-ful, lone-li-ness, for-e-ver)
            if i + 2 < len(tokens):
                t1, t2, t3 = tokens[i][2], tokens[i+1][2], tokens[i+2][2]
                c3 = t1 + t2 + t3
                if t1.isalpha() and t2.isalpha() and t3.isalpha():
                    if len(c3) > 3 and c3 in dict_words and t1 not in stopwords:
                        s1 = tokens[i][0].find("syllabic")
                        if s1 is None:
                            s1 = ET.SubElement(tokens[i][0], "syllabic")
                        s1.text = "begin"

                        s2 = tokens[i+1][0].find("syllabic")
                        if s2 is None:
                            s2 = ET.SubElement(tokens[i+1][0], "syllabic")
                        s2.text = "middle"

                        s3 = tokens[i+2][0].find("syllabic")
                        if s3 is None:
                            s3 = ET.SubElement(tokens[i+2][0], "syllabic")
                        s3.text = "end"

                        total_reconnected += 1
                        i += 3
                        continue

            # Try 2-syllables (e.g. wea-ving, sto-ries, per-fect, con-cerned)
            if i + 1 < len(tokens):
                t1, t2 = tokens[i][2], tokens[i+1][2]
                c2 = t1 + t2
                if t1.isalpha() and t2.isalpha():
                    is_w1 = t1 in dict_words and len(t1) > 2 and t1 not in stopwords
                    is_w2 = t2 in dict_words and len(t2) > 2 and t2 not in stopwords
                    if c2 in dict_words and not (t1 in stopwords or t2 in stopwords):
                        if not (is_w1 and is_w2) or c2 in ("forever", "together", "cannot", "maybe", "into", "without", "inside", "ago", "alone"):
                            s1 = tokens[i][0].find("syllabic")
                            if s1 is None:
                                s1 = ET.SubElement(tokens[i][0], "syllabic")
                            s1.text = "begin"

                            s2 = tokens[i+1][0].find("syllabic")
                            if s2 is None:
                                s2 = ET.SubElement(tokens[i+1][0], "syllabic")
                            s2.text = "end"

                            total_reconnected += 1
                            i += 2
                            continue
            i += 1

    return total_reconnected


def parse_musicxml(path: Path) -> tuple[ET.ElementTree, ET.Element]:
    """Load MusicXML from .xml or .mxl."""
    if path.suffix.lower() == ".mxl":
        with zipfile.ZipFile(path, "r") as z:
            # Find rootfile in META-INF/container.xml if available
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


def parse_bar_ranges(range_str: str) -> set[int]:
    """Parse comma-separated bar numbers and ranges, e.g. '8-15,20-27,41'."""
    bars = set()
    if not range_str.strip():
        return bars
    for part in range_str.split(","):
        part = part.strip()
        if "-" in part:
            start, end = part.split("-", 1)
            bars.update(range(int(start), int(end) + 1))
        elif part:
            bars.add(int(part))
    return bars


def cmd_audit(args: argparse.Namespace) -> int:
    """Audit a 2-staff score for voices, chord clusters, and lyrics."""
    path = Path(args.input)
    if not path.exists():
        print(f"error: file not found: {path}", file=sys.stderr)
        return 1

    _, root = parse_musicxml(path)
    parts = root.findall("part")
    print(f"File: {path.name}")
    print(f"Parts found: {len(parts)}")

    for p in parts:
        pid = p.attrib.get("id")
        measures = p.findall("measure")
        print(f"\n--- Part {pid} ({len(measures)} measures) ---")

        s1_voices = set()
        s2_voices = set()
        chords_s1 = 0
        chords_s2 = 0
        lyrics_count = 0

        for m in measures:
            for elem in m:
                if elem.tag == "note":
                    s = elem.find("staff")
                    v = elem.find("voice")
                    s_val = s.text if (s is not None and s.text) else "1"
                    v_val = v.text if (v is not None and v.text) else "1"
                    if s_val == "1":
                        s1_voices.add(v_val)
                        if elem.find("chord") is not None:
                            chords_s1 += 1
                    else:
                        s2_voices.add(v_val)
                        if elem.find("chord") is not None:
                            chords_s2 += 1
                    if elem.findall("lyric"):
                        lyrics_count += len(elem.findall("lyric"))

        print(f"  Staff 1 Voices: {sorted(list(s1_voices))}")
        print(f"  Staff 1 Chord Note Elements: {chords_s1}")
        print(f"  Staff 2 Voices: {sorted(list(s2_voices))}")
        print(f"  Staff 2 Chord Note Elements: {chords_s2}")
        print(f"  Total Lyrics Found: {lyrics_count}")

    return 0


def _copy_soprano_lyrics_to_tb(root: ET.Element) -> None:
    """Copy only missing lyrics when source and target note streams align."""
    parts = {part.attrib.get("id"): part for part in root.findall("part")}
    soprano, tenor, bass = parts.get("P1"), parts.get("P3"), parts.get("P4")
    if soprano is None or tenor is None or bass is None:
        return
    for s_measure, t_measure, b_measure in zip(
        soprano.findall("measure"), tenor.findall("measure"), bass.findall("measure"), strict=True
    ):
        source = [copy.deepcopy(note.findall("lyric")[0]) if note.findall("lyric") else None for note in s_measure.findall("note")]
        for measure in (t_measure, b_measure):
            notes = measure.findall("note")
            if len(notes) == len(source):
                for note, lyric in zip(notes, source, strict=True):
                    if lyric is not None and not note.findall("lyric"):
                        note.append(lyric)


def cmd_split(args: argparse.Namespace) -> int:
    """Split a 2-staff score into 4 discrete SATB parts."""
    in_path = Path(args.input)
    out_path = Path(args.output)
    if not in_path.exists():
        print(f"error: file not found: {in_path}", file=sys.stderr)
        return 1

    # All musical routing now lives in the shared onset-based engine.  This
    # wrapper deliberately keeps SATB-only lyric repair as post-processing.
    from sibelius_websocket_cli.musicxml_split.profiles.satb import SATBOptions, split_satb

    options = SATBOptions(
        soprano_solo_bars=frozenset(parse_bar_ranges(args.soprano_solo or "")),
        tenor_solo_bars=frozenset(parse_bar_ranges(args.tenor_solo or "")),
        bass_solo_bars=frozenset(parse_bar_ranges(args.bass_solo or "")),
    )
    result = split_satb(in_path, out_path, options)
    if result.issues:
        for issue in result.issues:
            print(f"[{issue.severity}] {issue.code}: {issue.message}", file=sys.stderr)
    if args.copy_lyrics_to_tb or args.reconnect_lyrics:
        _, output_root = parse_musicxml(out_path)
        if args.copy_lyrics_to_tb:
            _copy_soprano_lyrics_to_tb(output_root)
        if args.reconnect_lyrics:
            count = reconnect_lyrics_in_root(output_root)
            print(f"Reconnected {count} multi-syllable words across parts.")
        save_musicxml(output_root, out_path)
    print(f"Successfully split into 4-staff score: {out_path}")
    return 0

    tree, root = parse_musicxml(in_path)

    # Clean existing parts and part-list
    for child in list(root):
        if child.tag in ("part-list", "part"):
            root.remove(child)

    # Build SATB Part-List
    plist = ET.Element("part-list")
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
    root.append(plist)

    # Re-read original part measures
    _, orig_root = parse_musicxml(in_path)
    orig_part = orig_root.find("part")
    if orig_part is None:
        print("error: no part found in input MusicXML", file=sys.stderr)
        return 1
    orig_measures = orig_part.findall("measure")

    satb_parts = {
        "P1": ET.Element("part", id="P1"),
        "P2": ET.Element("part", id="P2"),
        "P3": ET.Element("part", id="P3"),
        "P4": ET.Element("part", id="P4"),
    }

    tenor_solo_bars = parse_bar_ranges(args.tenor_solo or "")
    bass_solo_bars = parse_bar_ranges(args.bass_solo or "")
    soprano_solo_bars = parse_bar_ranges(args.soprano_solo or "")

    current_divisions = 1
    current_beats = 4
    current_beat_type = 4

    for m in orig_measures:
        mnum_str = m.attrib.get("number", "1")
        try:
            mnum = int(mnum_str)
        except ValueError:
            mnum = 0

        div_elem = m.find(".//divisions")
        if div_elem is not None and div_elem.text:
            current_divisions = int(div_elem.text)
        time_elem = m.find(".//time")
        if time_elem is not None:
            beats_e = time_elem.find("beats")
            bt_e = time_elem.find("beat-type")
            if beats_e is not None and bt_e is not None and beats_e.text and bt_e.text:
                current_beats = int(beats_e.text)
                current_beat_type = int(bt_e.text)

        m_targets = {}
        for pid in ("P1", "P2", "P3", "P4"):
            m_new = ET.SubElement(satb_parts[pid], "measure", number=mnum_str)
            if "implicit" in m.attrib:
                m_new.attrib["implicit"] = m.attrib["implicit"]
            m_targets[pid] = m_new

        # Assign SATB Clefs & Attributes
        orig_attr = m.find("attributes")
        if orig_attr is not None or mnum == 1:
            a_base = copy.deepcopy(orig_attr) if orig_attr is not None else ET.Element("attributes")
            for tag in ("clef", "staves"):
                for el in list(a_base.findall(tag)):
                    a_base.remove(el)

            # P1: Soprano (Treble G2)
            a1 = copy.deepcopy(a_base)
            c1 = ET.SubElement(a1, "clef")
            ET.SubElement(c1, "sign").text = "G"
            ET.SubElement(c1, "line").text = "2"
            m_targets["P1"].append(a1)

            # P2: Alto (Treble G2)
            a2 = copy.deepcopy(a_base)
            c2 = ET.SubElement(a2, "clef")
            ET.SubElement(c2, "sign").text = "G"
            ET.SubElement(c2, "line").text = "2"
            m_targets["P2"].append(a2)

            # P3: Tenor (Octave Treble G2 / -1)
            a3 = copy.deepcopy(a_base)
            c3 = ET.SubElement(a3, "clef")
            ET.SubElement(c3, "sign").text = "G"
            ET.SubElement(c3, "line").text = "2"
            ET.SubElement(c3, "clef-octave-change").text = "-1"
            m_targets["P3"].append(a3)

            # P4: Bass (Bass F4)
            a4 = copy.deepcopy(a_base)
            c4 = ET.SubElement(a4, "clef")
            ET.SubElement(c4, "sign").text = "F"
            ET.SubElement(c4, "line").text = "4"
            m_targets["P4"].append(a4)

        # Distribute shared elements (omit <print> to allow Sibelius reflow)
        for elem in m:
            if elem.tag == "print":
                continue
            elif elem.tag == "barline":
                for pid in ("P1", "P2", "P3", "P4"):
                    m_targets[pid].append(copy.deepcopy(elem))
            elif elem.tag == "direction":
                s_elem = elem.find("staff")
                target = "P3" if (s_elem is not None and s_elem.text == "2") else "P1"
                d_copy = copy.deepcopy(elem)
                s_copy = d_copy.find("staff")
                if s_copy is not None:
                    d_copy.remove(s_copy)
                m_targets[target].append(d_copy)
            elif elem.tag == "harmony":
                h_copy = copy.deepcopy(elem)
                s_copy = h_copy.find("staff")
                if s_copy is not None:
                    h_copy.remove(s_copy)
                m_targets["P1"].append(h_copy)

        s1_elements = []
        s2_elements = []
        for elem in m:
            if elem.tag in ("note", "backup", "forward"):
                s = elem.find("staff")
                s_val = s.text if (s is not None and s.text) else "1"
                if s_val == "1":
                    s1_elements.append(elem)
                else:
                    s2_elements.append(elem)

        # ==========================================
        # DEMIX UPPER STAFF -> P1 (Soprano) & P2 (Alto)
        # ==========================================
        if mnum in soprano_solo_bars:
            for elem in s1_elements:
                if elem.tag == "note":
                    m_targets["P1"].append(clean_note_element(elem))
            m_targets["P2"].append(make_rest_measure(mnum, current_divisions, current_beats, current_beat_type))
        else:
            v1_notes = [e for e in s1_elements if e.tag == "note" and e.find("voice") is not None and e.find("voice").text == "1"]
            v2_notes = [e for e in s1_elements if e.tag == "note" and e.find("voice") is not None and e.find("voice").text in ("2", "3", "4")]
            has_chords = any(e.tag == "note" and e.find("chord") is not None for e in s1_elements)

            if v1_notes and v2_notes:
                p1_notes = flatten_voice_chords(v1_notes, select_top=True)
                p2_notes = flatten_voice_chords(v2_notes, select_top=False)
                for n in p1_notes:
                    m_targets["P1"].append(n)
                for n in p2_notes:
                    m_targets["P2"].append(n)
            elif has_chords:
                i = 0
                while i < len(s1_elements):
                    elem = s1_elements[i]
                    if elem.tag == "note":
                        if i + 1 < len(s1_elements) and s1_elements[i+1].tag == "note" and s1_elements[i+1].find("chord") is not None:
                            base_n = elem
                            chord_n = s1_elements[i+1]
                            n_alto = clean_note_element(base_n)
                            n_sop = clean_note_element(chord_n)

                            if base_n.findall("lyric") and not chord_n.findall("lyric"):
                                for lyr in base_n.findall("lyric"):
                                    n_sop.append(copy.deepcopy(lyr))

                            m_targets["P1"].append(n_sop)
                            m_targets["P2"].append(n_alto)
                            i += 2
                            continue
                        else:
                            m_targets["P1"].append(clean_note_element(elem))
                            m_targets["P2"].append(clean_note_element(elem))
                    i += 1
            else:
                has_pitches = any(e.tag == "note" and e.find("pitch") is not None for e in s1_elements)
                if has_pitches:
                    for elem in s1_elements:
                        if elem.tag == "note":
                            m_targets["P1"].append(clean_note_element(elem))
                            m_targets["P2"].append(clean_note_element(elem))
                else:
                    m_targets["P1"].append(make_rest_measure(mnum, current_divisions, current_beats, current_beat_type))
                    m_targets["P2"].append(make_rest_measure(mnum, current_divisions, current_beats, current_beat_type))

        # ==========================================
        # DEMIX LOWER STAFF -> P3 (Tenor) & P4 (Bass)
        # ==========================================
        if mnum in tenor_solo_bars:
            v_upper = [e for e in s2_elements if e.tag == "note" and (e.find("voice") is None or e.find("voice").text in ("1", "5"))]
            p3_notes = flatten_voice_chords(v_upper if v_upper else [e for e in s2_elements if e.tag == "note"], select_top=True)
            for n in p3_notes:
                m_targets["P3"].append(n)
            m_targets["P4"].append(make_rest_measure(mnum, current_divisions, current_beats, current_beat_type))
        elif mnum in bass_solo_bars:
            m_targets["P3"].append(make_rest_measure(mnum, current_divisions, current_beats, current_beat_type))
            v_lower = [e for e in s2_elements if e.tag == "note" and (e.find("voice") is None or e.find("voice").text in ("2", "6"))]
            p4_notes = flatten_voice_chords(v_lower if v_lower else [e for e in s2_elements if e.tag == "note"], select_top=False)
            for n in p4_notes:
                m_targets["P4"].append(n)

        else:
            v_upper = [e for e in s2_elements if e.tag == "note" and e.find("voice") is not None and e.find("voice").text in ("1", "5")]
            v_lower = [e for e in s2_elements if e.tag == "note" and e.find("voice") is not None and e.find("voice").text in ("2", "6")]
            has_chords = any(e.tag == "note" and e.find("chord") is not None for e in s2_elements)

            if v_upper and v_lower:
                p3_notes = flatten_voice_chords(v_upper, select_top=True)
                p4_notes = flatten_voice_chords(v_lower, select_top=False)
                for n in p3_notes:
                    m_targets["P3"].append(n)
                for n in p4_notes:
                    m_targets["P4"].append(n)
            elif has_chords:
                i = 0
                while i < len(s2_elements):
                    elem = s2_elements[i]
                    if elem.tag == "note":
                        if i + 1 < len(s2_elements) and s2_elements[i+1].tag == "note" and s2_elements[i+1].find("chord") is not None:
                            base_n = elem
                            chord_n = s2_elements[i+1]
                            n_bass = clean_note_element(base_n)
                            n_tenor = clean_note_element(chord_n)

                            if base_n.findall("lyric"):
                                for lyr in base_n.findall("lyric"):
                                    n_tenor.append(copy.deepcopy(lyr))

                            m_targets["P3"].append(n_tenor)
                            m_targets["P4"].append(n_bass)
                            i += 2
                            continue
                        else:
                            m_targets["P3"].append(clean_note_element(elem))
                            m_targets["P4"].append(clean_note_element(elem))
                    i += 1
            else:
                has_pitches = any(e.tag == "note" and e.find("pitch") is not None for e in s2_elements)
                if has_pitches:
                    for elem in s2_elements:
                        if elem.tag == "note":
                            m_targets["P3"].append(clean_note_element(elem))
                            m_targets["P4"].append(clean_note_element(elem))
                else:
                    m_targets["P3"].append(make_rest_measure(mnum, current_divisions, current_beats, current_beat_type))
                    m_targets["P4"].append(make_rest_measure(mnum, current_divisions, current_beats, current_beat_type))

    # Append all 4 parts to score root
    for pid in ("P1", "P2", "P3", "P4"):
        root.append(satb_parts[pid])

    # Optional lyric cloning from Soprano to Tenor/Bass in choral passages
    if args.copy_lyrics_to_tb:
        print("Synthesizing missing choral lyrics on Tenor and Bass...")
        p1_measures = satb_parts["P1"].findall("measure")
        p3_measures = satb_parts["P3"].findall("measure")
        p4_measures = satb_parts["P4"].findall("measure")

        for idx, m_sop in enumerate(p1_measures):
            m_ten = p3_measures[idx]
            m_bas = p4_measures[idx]

            sop_lyrics = []
            for n in m_sop.findall("note"):
                lyrs = n.findall("lyric")
                sop_lyrics.append(copy.deepcopy(lyrs[0]) if lyrs else None)

            ten_notes = m_ten.findall("note")
            if len(ten_notes) == len(sop_lyrics):
                for n, lyr in zip(ten_notes, sop_lyrics):
                    if lyr is not None and not n.findall("lyric"):
                        n.append(copy.deepcopy(lyr))

            bas_notes = m_bas.findall("note")
            if len(bas_notes) == len(sop_lyrics):
                for n, lyr in zip(bas_notes, sop_lyrics):
                    if lyr is not None and not n.findall("lyric"):
                        n.append(copy.deepcopy(lyr))

    # Reconnect shattered OMR syllables into begin/middle/end words
    if args.reconnect_lyrics:
        count = reconnect_lyrics_in_root(root)
        print(f"Reconnected {count} multi-syllable words across parts.")

    save_musicxml(root, out_path)
    print(f"Successfully split into 4-staff score: {out_path}")
    return 0


def cmd_reconnect_lyrics(args: argparse.Namespace) -> int:
    """Scan and reconnect shattered OMR lyric syllables in an existing MusicXML file."""
    in_path = Path(args.input)
    out_path = Path(args.output) if args.output else in_path
    if not in_path.exists():
        print(f"error: file not found: {in_path}", file=sys.stderr)
        return 1

    tree, root = parse_musicxml(in_path)
    count = reconnect_lyrics_in_root(root)
    save_musicxml(root, out_path)
    print(f"Successfully reconnected {count} words in {out_path}")
    return 0



def cmd_validate(args: argparse.Namespace) -> int:
    """Validate measure durations across all 4 parts of an SATB score."""
    path = Path(args.input)
    if not path.exists():
        print(f"error: file not found: {path}", file=sys.stderr)
        return 1

    _, root = parse_musicxml(path)
    parts = root.findall("part")
    if len(parts) != 4:
        print(f"[!] Warning: Expected 4 parts, found {len(parts)}", file=sys.stderr)

    issues = 0
    current_div = 1
    current_beats = 4
    current_beat_type = 4

    for p in parts:
        pid = p.attrib.get("id", "unknown")
        for m in p.findall("measure"):
            mnum = m.attrib.get("number", "?")
            div_elem = m.find(".//divisions")
            if div_elem is not None and div_elem.text:
                current_div = int(div_elem.text)
            time_elem = m.find(".//time")
            if time_elem is not None:
                beats_e = time_elem.find("beats")
                bt_e = time_elem.find("beat-type")
                if beats_e is not None and bt_e is not None and beats_e.text and bt_e.text:
                    current_beats = int(beats_e.text)
                    current_beat_type = int(bt_e.text)

            expected_dur = int(current_beats * (4.0 / current_beat_type) * current_div)
            actual_dur = 0
            for n in m.findall("note"):
                if n.find("chord") is None:
                    d_elem = n.find("duration")
                    if d_elem is not None and d_elem.text:
                        actual_dur += int(d_elem.text)

            if actual_dur != expected_dur and expected_dur > 0:
                print(f"  [!] Duration mismatch in Part {pid} Bar {mnum}: expected {expected_dur}, got {actual_dur}")
                issues += 1

    if issues == 0:
        print(f"Clean validation: all {len(parts)} parts have consistent measure durations across {path.name}.")
        return 0
    else:
        print(f"Validation finished: {issues} issue(s) found.")
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit, split, and validate 2-staff scores into 4-staff SATB.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # audit
    p_audit = subparsers.add_parser("audit", help="Audit a 2-staff score for voices, chords, and lyrics")
    p_audit.add_argument("input", help="Path to input .xml or .mxl")
    p_audit.set_defaults(func=cmd_audit)

    # split
    p_split = subparsers.add_parser("split", help="Split 2-staff score into 4-staff SATB")
    p_split.add_argument("input", help="Path to input 2-staff .xml or .mxl")
    p_split.add_argument("--output", "-o", required=True, help="Path to output 4-staff .xml or .mxl")
    p_split.add_argument("--tenor-solo", help="Comma-separated bar numbers or ranges for Tenor solo (e.g. '8-15,20-27')")
    p_split.add_argument("--bass-solo", help="Comma-separated bar numbers or ranges for Bass solo")
    p_split.add_argument("--soprano-solo", help="Comma-separated bar numbers or ranges for Soprano solo")
    p_split.add_argument("--copy-lyrics-to-tb", action="store_true", help="Copy choral lyrics to homophonic Tenor/Bass lines")
    p_split.add_argument("--reconnect-lyrics", action="store_true", default=True, help="Automatically reconnect shattered OMR syllables into begin/middle/end words (default: True)")
    p_split.add_argument("--no-reconnect-lyrics", dest="reconnect_lyrics", action="store_false", help="Disable automatic syllable reconnection")
    p_split.set_defaults(func=cmd_split)

    # reconnect-lyrics
    p_rec = subparsers.add_parser("reconnect-lyrics", help="Scan and reconnect shattered OMR syllables in an XML or MXL file")
    p_rec.add_argument("input", help="Path to input .xml or .mxl")
    p_rec.add_argument("--output", "-o", help="Path to output .xml or .mxl (defaults to overwriting input)")
    p_rec.set_defaults(func=cmd_reconnect_lyrics)

    # validate
    p_val = subparsers.add_parser("validate", help="Validate measure durations in an SATB score")
    p_val.add_argument("input", help="Path to 4-staff .xml or .mxl")
    p_val.set_defaults(func=cmd_validate)

    args = parser.parse_args()
    return args.func(args)



if __name__ == "__main__":
    sys.exit(main())
