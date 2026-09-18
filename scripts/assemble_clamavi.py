#!/usr/bin/env python3
"""Assemble Clamavi de tribulatione mea into a pristine 16-voice MusicXML score.

Double chorus SSAATTBB.SSAATTBB (Choir 1: P1-P8, Choir 2: P9-P16).
Total: Pickup (m. 0, anacrusis 1/8) + 124 full measures.
Visual ground truth: PDF 'Clamavi de tribulatione mea 12pp - 2021-06-23 b.pdf'
"""

from __future__ import annotations

import copy
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

SEMITONES = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
DIVISIONS = 3840  # quarter = 3840, eighth = 1920, 16th = 960, triplet eighth = 1280


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
    tie: str | None = None,  # "start", "stop", "both"
    lyric_text: str | None = None,
    lyric_syl: str = "single",  # "single", "begin", "middle", "end"
    accent: bool = False,
    fermata: bool = False,
    tuplet: str | None = None,  # "start", "stop"
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

    if tuplet:
        tmod = ET.SubElement(n, "time-modification")
        ET.SubElement(tmod, "actual-notes").text = "3"
        ET.SubElement(tmod, "normal-notes").text = "2"

    notations = None
    if tie in ("stop", "both"):
        if notations is None:
            notations = ET.SubElement(n, "notations")
        ET.SubElement(notations, "tied", type="stop")
    if tie in ("start", "both"):
        if notations is None:
            notations = ET.SubElement(n, "notations")
        ET.SubElement(notations, "tied", type="start")
    if tuplet:
        if notations is None:
            notations = ET.SubElement(n, "notations")
        ET.SubElement(notations, "tuplet", type=tuplet)
    if accent:
        if notations is None:
            notations = ET.SubElement(n, "notations")
        art = ET.SubElement(notations, "articulations")
        ET.SubElement(art, "accent")
    if fermata:
        if notations is None:
            notations = ET.SubElement(n, "notations")
        ET.SubElement(notations, "fermata", type="upright")

    if lyric_text:
        lyr = ET.SubElement(n, "lyric", number="1")
        ET.SubElement(lyr, "syllabic").text = lyric_syl
        ET.SubElement(lyr, "text").text = lyric_text

    return n


def make_rest_note(
    dur: int,
    note_type: str | None = None,
    is_measure_rest: bool = False,
    voice: str = "1",
    is_dotted: bool = False,
) -> ET.Element:
    n = ET.Element("note")
    rest = ET.SubElement(n, "rest")
    if is_measure_rest:
        rest.set("measure", "yes")
    ET.SubElement(n, "duration").text = str(dur)
    ET.SubElement(n, "voice").text = voice
    if note_type:
        ET.SubElement(n, "type").text = note_type
    if is_dotted:
        ET.SubElement(n, "dot")
    return n


def create_base_score() -> tuple[ET.Element, dict[str, ET.Element]]:
    root = ET.Element("score-partwise", version="3.1")

    # Work & Identification
    work = ET.SubElement(root, "work")
    ET.SubElement(work, "work-title").text = "Clamavi de tribulatione mea"

    ident = ET.SubElement(root, "identification")
    ET.SubElement(ident, "creator", type="composer").text = "Ann Callaway"
    ET.SubElement(ident, "rights").text = "Copyright © 2021 Ann Callaway"
    encoding = ET.SubElement(ident, "encoding")
    ET.SubElement(encoding, "software").text = "Antigravity 16-voice Score Assembler"

    # Part list
    plist = ET.SubElement(root, "part-list")

    # Group 1: Choir 1
    pg1 = ET.SubElement(plist, "part-group", number="1", type="start")
    ET.SubElement(pg1, "group-name").text = "Choir 1"
    ET.SubElement(pg1, "group-symbol").text = "bracket"
    ET.SubElement(pg1, "group-barline").text = "yes"

    parts_c1 = [
        ("P1", "Choir 1 Soprano 1", "C1 S1", "voice.soprano", "1"),
        ("P2", "Choir 1 Soprano 2", "C1 S2", "voice.soprano", "2"),
        ("P3", "Choir 1 Alto 1", "C1 A1", "voice.alto", "3"),
        ("P4", "Choir 1 Alto 2", "C1 A2", "voice.alto", "4"),
        ("P5", "Choir 1 Tenor 1", "C1 T1", "voice.tenor", "5"),
        ("P6", "Choir 1 Tenor 2", "C1 T2", "voice.tenor", "6"),
        ("P7", "Choir 1 Bass 1", "C1 B1", "voice.bass", "7"),
        ("P8", "Choir 1 Bass 2", "C1 B2", "voice.bass", "8"),
    ]

    for pid, pname, abbr, sound_id, chan in parts_c1:
        sp = ET.SubElement(plist, "score-part", id=pid)
        ET.SubElement(sp, "part-name").text = pname
        ET.SubElement(sp, "part-abbreviation").text = abbr
        instr = ET.SubElement(sp, "score-instrument", id=f"{pid}-I1")
        ET.SubElement(instr, "instrument-name").text = pname
        ET.SubElement(instr, "instrument-sound").text = sound_id
        midi = ET.SubElement(sp, "midi-instrument", id=f"{pid}-I1")
        ET.SubElement(midi, "midi-channel").text = chan
        ET.SubElement(midi, "midi-program").text = "53"

    ET.SubElement(plist, "part-group", number="1", type="stop")

    # Group 2: Choir 2
    pg2 = ET.SubElement(plist, "part-group", number="2", type="start")
    ET.SubElement(pg2, "group-name").text = "Choir 2"
    ET.SubElement(pg2, "group-symbol").text = "bracket"
    ET.SubElement(pg2, "group-barline").text = "yes"

    parts_c2 = [
        ("P9", "Choir 2 Soprano 1", "C2 S1", "voice.soprano", "9"),
        ("P10", "Choir 2 Soprano 2", "C2 S2", "voice.soprano", "10"),
        ("P11", "Choir 2 Alto 1", "C2 A1", "voice.alto", "11"),
        ("P12", "Choir 2 Alto 2", "C2 A2", "voice.alto", "12"),
        ("P13", "Choir 2 Tenor 1", "C2 T1", "voice.tenor", "13"),
        ("P14", "Choir 2 Tenor 2", "C2 T2", "voice.tenor", "14"),
        ("P15", "Choir 2 Bass 1", "C2 B1", "voice.bass", "15"),
        ("P16", "Choir 2 Bass 2", "C2 B2", "voice.bass", "16"),
    ]

    for pid, pname, abbr, sound_id, chan in parts_c2:
        sp = ET.SubElement(plist, "score-part", id=pid)
        ET.SubElement(sp, "part-name").text = pname
        ET.SubElement(sp, "part-abbreviation").text = abbr
        instr = ET.SubElement(sp, "score-instrument", id=f"{pid}-I1")
        ET.SubElement(instr, "instrument-name").text = pname
        ET.SubElement(instr, "instrument-sound").text = sound_id
        midi = ET.SubElement(sp, "midi-instrument", id=f"{pid}-I1")
        ET.SubElement(midi, "midi-channel").text = chan
        ET.SubElement(midi, "midi-program").text = "53"

    ET.SubElement(plist, "part-group", number="2", type="stop")

    # Parts containers
    parts = {}
    for pid in [f"P{i}" for i in range(1, 17)]:
        parts[pid] = ET.SubElement(root, "part", id=pid)

    return root, parts


def add_attributes(
    measure_elem: ET.Element,
    pid: str,
    divisions: int = DIVISIONS,
    fifths: int = 0,
    time_sig: tuple[int, int] | None = None,
    include_clef: bool = False,
):
    attr = ET.SubElement(measure_elem, "attributes")
    ET.SubElement(attr, "divisions").text = str(divisions)
    if fifths is not None:
        k = ET.SubElement(attr, "key")
        ET.SubElement(k, "fifths").text = str(fifths)
    if time_sig:
        t = ET.SubElement(attr, "time")
        ET.SubElement(t, "beats").text = str(time_sig[0])
        ET.SubElement(t, "beat-type").text = str(time_sig[1])
    if include_clef:
        c = ET.SubElement(attr, "clef")
        if pid in ("P1", "P2", "P3", "P4", "P9", "P10", "P11", "P12"):
            ET.SubElement(c, "sign").text = "G"
            ET.SubElement(c, "line").text = "2"
        elif pid in ("P5", "P6", "P13", "P14"):
            ET.SubElement(c, "sign").text = "G"
            ET.SubElement(c, "line").text = "2"
            ET.SubElement(c, "clef-octave-change").text = "-1"
        else:  # P7, P8, P15, P16 (Bass)
            ET.SubElement(c, "sign").text = "F"
            ET.SubElement(c, "line").text = "4"


def add_tutti_unison_measure(
    parts: dict[str, ET.Element],
    mnum: int,
    mnum_str: str,
    time_sig: tuple[int, int] | None,
    s_notes: list[ET.Element],
    a_notes: list[ET.Element],
    t_notes: list[ET.Element],
    b_notes: list[ET.Element],
    is_pickup: bool = False,
):
    """Add a measure where both choirs sing in unison:

    Soprano -> P1, P2, P9, P10
    Alto    -> P3, P4, P11, P12
    Tenor   -> P5, P6, P13, P14
    Bass    -> P7, P8, P15, P16
    """
    m_elems = {}
    for pid in parts:
        m = ET.SubElement(parts[pid], "measure", number=mnum_str)
        if is_pickup:
            m.set("implicit", "yes")
        m_elems[pid] = m

    # Attributes
    for pid in parts:
        include_clef = (mnum == 0 if is_pickup else mnum == 1)
        add_attributes(
            m_elems[pid],
            pid,
            divisions=DIVISIONS,
            fifths=0 if include_clef else None,
            time_sig=time_sig,
            include_clef=include_clef,
        )

    # Note lists mapping
    voice_map = {
        "P1": s_notes, "P2": s_notes, "P9": s_notes, "P10": s_notes,
        "P3": a_notes, "P4": a_notes, "P11": a_notes, "P12": a_notes,
        "P5": t_notes, "P6": t_notes, "P13": t_notes, "P14": t_notes,
        "P7": b_notes, "P8": b_notes, "P15": b_notes, "P16": b_notes,
    }

    for pid, n_list in voice_map.items():
        for n in n_list:
            m_elems[pid].append(copy.deepcopy(n))


def clean_standard_note(n: ET.Element) -> ET.Element:
    """Standardize note element: scale dur / 10, voice 1, strip layout, fix alter & typos."""
    note = copy.deepcopy(n)
    if note.get("_scaled") != "yes":
        dur_elem = note.find("duration")
        if dur_elem is not None and dur_elem.text:
            dur_elem.text = str(int(float(dur_elem.text)))
        note.set("_scaled", "yes")

    
    # Strip layout attributes
    for k in list(note.attrib.keys()):
        if k in ("default-x", "default-y", "relative-x", "relative-y"):
            del note.attrib[k]
            
    v = note.find("voice")
    if v is None:
        v = ET.SubElement(note, "voice")
    v.text = "1"
    
    p = note.find("pitch")
    if p is not None:
        alt = p.find("alter")
        if alt is not None and alt.text:
            alt.text = str(int(float(alt.text)))
            
    # Fix common Halbestunde OCR typos in lyrics
    for lyr in note.findall("lyric"):
        txt = lyr.find("text")
        if txt is not None and txt.text:
            t = txt.text.strip()
            if t == "pc":
                txt.text = "pe"
            elif t == "rac":
                txt.text = "rae"
            elif t == "sc":
                txt.text = "se"
            elif t == "ac":
                txt.text = "ae"
            elif t == "mam":
                txt.text = "mam:"
    return note



def demix_measure_notes(raw_notes: list[ET.Element]) -> tuple[list[ET.Element], list[ET.Element]]:
    """Demix a list of raw notes (with possible chords) into (top_notes, bot_notes).
    
    If a note is single (no chord), both top and bot get a copy.
    If it's a 2-note chord, top gets higher pitch, bot gets lower pitch.
    Lyrics from the chord base note are cloned to the top note if missing.
    """
    clusters: list[list[ET.Element]] = []
    current_cluster: list[ET.Element] = []
    for n in raw_notes:
        if n.find("chord") is not None:
            current_cluster.append(n)
        else:
            if current_cluster:
                clusters.append(current_cluster)
            current_cluster = [n]
    if current_cluster:
        clusters.append(current_cluster)

    top_notes: list[ET.Element] = []
    bot_notes: list[ET.Element] = []

    for cluster in clusters:
        if len(cluster) == 1:
            n = cluster[0]
            top_notes.append(clean_standard_note(n))
            bot_notes.append(clean_standard_note(n))
        else:
            sorted_cluster = sorted(cluster, key=get_midi)
            bot_n = clean_standard_note(sorted_cluster[0])
            top_n = clean_standard_note(sorted_cluster[-1])
            # Ensure chord tag is removed
            for elem in (top_n, bot_n):
                ch = elem.find("chord")
                if ch is not None:
                    elem.remove(ch)
            # Propagate lyrics from cluster if top_n lacks them
            cluster_lyrics = None
            for item in cluster:
                lyr = item.find("lyric")
                if lyr is not None:
                    cluster_lyrics = lyr
                    break
            if cluster_lyrics is not None:
                if top_n.find("lyric") is None:
                    top_n.append(copy.deepcopy(cluster_lyrics))
                if bot_n.find("lyric") is None:
                    bot_n.append(copy.deepcopy(cluster_lyrics))
            top_notes.append(top_n)
            bot_notes.append(bot_n)

    return top_notes, bot_notes


def add_measure(
    parts: dict[str, ET.Element],
    mnum: int,
    mnum_str: str,
    voice_map: dict[str, list[ET.Element]],
    time_sig: tuple[int, int] | None = None,
    is_pickup: bool = False,
):
    """Add a measure to all 16 parts using an explicit voice_map {pid: [notes]}."""
    m_elems = {}
    for pid in parts:
        m = ET.SubElement(parts[pid], "measure", number=mnum_str)
        if is_pickup:
            m.set("implicit", "yes")
        m_elems[pid] = m

    for pid in parts:
        include_clef = (mnum == 0 if is_pickup else mnum == 1)
        add_attributes(
            m_elems[pid],
            pid,
            divisions=DIVISIONS,
            fifths=0 if include_clef else None,
            time_sig=time_sig,
            include_clef=include_clef,
        )

    for pid, n_list in voice_map.items():
        for n in n_list:
            note_copy = copy.deepcopy(n)
            if "_scaled" in note_copy.attrib:
                del note_copy.attrib["_scaled"]
            m_elems[pid].append(note_copy)


