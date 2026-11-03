"""Polychoral and multi-voice choral demixing engine.

Audits, splits, and demixes complex choral scores (including 2-choir, 16-voice
scores with alternating open-score and short-score layouts) into 16 discrete vocal
staves with independent MIDI channels, appropriate choral clefs, and preserved lyrics.
"""

from __future__ import annotations

import copy
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from .musicxml_split.io import parse_musicxml, save_musicxml
from .musicxml_split.routing import NOTE_TAG_ORDER, SEMITONES, insert_note_child, midi
from .musicxml_split.routing import clean_note as _clean_note
from .musicxml_split.routing import make_rest as _make_rest
from .musicxml_split.ties import heal_ties

__all__ = [
    "NOTE_TAG_ORDER", "SEMITONES", "build_16voice_part_list", "clean_note", "demix_16voices",
    "demix_reduction_staff", "demix_single_staff", "get_chord_clusters", "get_midi", "heal_ties",
    "insert_note_child", "make_rest", "pad_or_trim_duration", "parse_musicxml", "save_musicxml",
    "validate_16voices",
]


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


# Shared primitives live in ``musicxml_split``; these names stay importable here.
get_midi = midi
def clean_note(
    note: ET.Element,
    base_dur: str | None = None,
    is_grace: bool = False,
    voice: str = "1",
) -> ET.Element:
    """Clean a note for a discrete single-voice staff, removing chord, staff, and instrument tags."""
    n = _clean_note(note, voice)
    if is_grace or n.find("grace") is not None:
        g = n.find("grace")
        if g is None:
            n.insert(0, ET.Element("grace"))
        elif list(n).index(g) != 0:
            n.remove(g)
            n.insert(0, g)
        d = n.find("duration")
        if d is not None:
            n.remove(d)
    elif base_dur is not None:
        d = n.find("duration")
        if d is not None:
            d.text = base_dur
    return n


def make_rest(measure_dur: int, voice: str = "1") -> ET.Element:
    """Create a whole-measure rest element matching measure_dur."""
    note = _make_rest(measure_dur, whole_measure=True)
    note.find("voice").text = voice  # type: ignore[union-attr]
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


def demix_16voices(
    in_path: Path | str,
    out_path: Path | str,
    choir_unison_indices: set[int] | None = None,
) -> dict[str, Any]:
    """Demix a 12-staff polychoral score into 16 discrete parts.

    Handles alternating open score (P1-P8) and short score (P9, P11),
    clef configuration, tie preservation, lyric propagation, and duration normalization.
    """
    # The public function remains for callers of the original module.  The
    # deterministic onset-based package owns all new production routing.
    from .musicxml_split.profiles.polychoral_16 import Polychoral16Options, split_16voices

    in_p = Path(in_path)
    result = split_16voices(
        in_p,
        Path(out_path),
        Polychoral16Options(frozenset(choir_unison_indices)) if choir_unison_indices is not None else None,
    )
    return result.as_dict(in_p)


def validate_16voices(path: Path | str) -> list[str]:
    """Validate measure durations and consistency across all 16 parts in a score."""
    # Historical public API: report cross-part duration disagreement.  The
    # shared validator additionally diagnoses malformed rhythm and is used by
    # the CLI and profiles; retaining this narrow behavior avoids a breaking
    # change for callers that used it as a consistency-only check.
    from .musicxml_split.io import parse_musicxml as shared_parse

    p = Path(path)
    if not p.exists():
        return [f"File not found: {p}"]
    _, root = shared_parse(p)
    parts = root.findall("part")
    if len(parts) != 16:
        return [f"Expected 16 parts, found {len(parts)}"]
    count = len(parts[0].findall("measure"))
    problems: list[str] = []
    for index in range(count):
        durations = {}
        for part in parts:
            measures = part.findall("measure")
            if index >= len(measures):
                problems.append(f"Part {part.attrib.get('id', 'unknown')} missing measure index {index}")
                continue
            durations[part.attrib.get("id", "unknown")] = sum(
                int(note.findtext("duration") or "0")
                for note in measures[index].findall("note")
                if note.find("chord") is None
            )
        if len(set(durations.values())) > 1:
            problems.append(f"Measure index {index}: duration discrepancy across parts: {durations}")
    return problems
