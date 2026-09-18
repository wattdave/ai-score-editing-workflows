#!/usr/bin/env python3
"""Build Section 12 (mm. 122-125, Page 13) and complete full 16-voice assembly.

All 4 measures on Page 13 are transcribed directly from high-resolution crops
of the authoritative PDF scan.
Completes the full 125-measure score (mm. 0-125) of Ann Callaway's
'Clamavi de tribulatione mea' for double chorus SSAATTBB.SSAATTBB.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from scripts.assemble_clamavi import (
    add_measure,
    make_pitch_note,
    make_rest_note,
)
import scripts.test_section11_build as s11

parts = s11.parts
root = s11.root

print("Assembling Section 12 (mm. 122-125, Page 13 - Final Section)...")

r15360 = [make_rest_note(15360, is_measure_rest=True)]
r7680  = [make_rest_note(7680)]
r3840  = [make_rest_note(3840)]
r1920  = [make_rest_note(1920)]

# =========================================================================
# m122 (4/4 = 15360) - printed 121
# Key: 4 flats (Ab major)
# Choir 1: half chord "tu", dotted quarter chord "um,", eighth rest
# Choir 2: eighth chord (tied from m.121 "plum"), eighth rest,
#          half chord "sanc -", quarter chord "tum,"
# =========================================================================
c1_s1_122 = [
    make_pitch_note("G", 5, 7680, "half", alter=-1, lyric_text="tu", lyric_syl="begin"),
    make_pitch_note("D", 5, 5760, "quarter", alter=-1, is_dotted=True, lyric_text="um,", lyric_syl="end"),
    make_rest_note(1920, "eighth"),
]
c1_s2_122 = [
    make_pitch_note("D", 5, 7680, "half", alter=-1, lyric_text="tu", lyric_syl="begin"),
    make_pitch_note("B", 4, 5760, "quarter", alter=-1, is_dotted=True, lyric_text="um,", lyric_syl="end"),
    make_rest_note(1920, "eighth"),
]
c1_a_122 = [
    make_pitch_note("B", 4, 7680, "half", alter=-1, lyric_text="tu", lyric_syl="begin"),
    make_pitch_note("G", 4, 5760, "quarter", alter=-1, is_dotted=True, lyric_text="um,", lyric_syl="end"),
    make_rest_note(1920, "eighth"),
]
c1_t1_122 = [
    make_pitch_note("B", 3, 7680, "half", alter=-1, lyric_text="tu", lyric_syl="begin"),
    make_pitch_note("B", 3, 5760, "quarter", alter=-1, is_dotted=True, lyric_text="um,", lyric_syl="end"),
    make_rest_note(1920, "eighth"),
]
c1_t2_122 = [
    make_pitch_note("D", 3, 7680, "half", alter=-1),
    make_pitch_note("D", 3, 5760, "quarter", alter=-1, is_dotted=True),
    make_rest_note(1920, "eighth"),
]
c1_b_122 = [
    make_pitch_note("G", 2, 7680, "half", alter=-1, lyric_text="tu", lyric_syl="begin"),
    make_pitch_note("G", 2, 5760, "quarter", alter=-1, is_dotted=True, lyric_text="um,", lyric_syl="end"),
    make_rest_note(1920, "eighth"),
]

c2_s1_122 = [
    make_pitch_note("F", 5, 1920, "eighth", tie="stop"),
    make_rest_note(1920, "eighth"),
    make_pitch_note("G", 5, 7680, "half", alter=-1, lyric_text="sanc", lyric_syl="begin"),
    make_pitch_note("F", 5, 3840, "quarter", lyric_text="tum,", lyric_syl="end"),
]
c2_s2_122 = [
    make_pitch_note("D", 5, 1920, "eighth", alter=-1, tie="stop"),
    make_rest_note(1920, "eighth"),
    make_pitch_note("D", 5, 7680, "half", alter=-1, lyric_text="sanc", lyric_syl="begin"),
    make_pitch_note("D", 5, 3840, "quarter", alter=-1, lyric_text="tum,", lyric_syl="end"),
]
c2_a_122 = [
    make_pitch_note("B", 4, 1920, "eighth", alter=-1, tie="stop"),
    make_rest_note(1920, "eighth"),
    make_pitch_note("B", 4, 7680, "half", alter=-1, lyric_text="sanc", lyric_syl="begin"),
    make_pitch_note("B", 4, 3840, "quarter", alter=-1, lyric_text="tum,", lyric_syl="end"),
]
c2_t1_122 = [
    make_pitch_note("B", 3, 1920, "eighth", alter=-1, tie="stop"),
    make_rest_note(1920, "eighth"),
    make_pitch_note("B", 3, 7680, "half", alter=-1, lyric_text="sanc", lyric_syl="begin"),
    make_pitch_note("B", 3, 3840, "quarter", alter=-1, lyric_text="tum,", lyric_syl="end"),
]
c2_t2_122 = [
    make_pitch_note("B", 3, 1920, "eighth", alter=-1, tie="stop"),
    make_rest_note(1920, "eighth"),
    make_pitch_note("D", 3, 7680, "half", alter=-1, lyric_text="sanc", lyric_syl="begin"),
    make_pitch_note("D", 3, 3840, "quarter", alter=-1, lyric_text="tum,", lyric_syl="end"),
]
c2_b_122 = [
    make_pitch_note("B", 2, 1920, "eighth", alter=-1, tie="stop"),
    make_rest_note(1920, "eighth"),
    make_pitch_note("G", 2, 7680, "half", alter=-1, lyric_text="sanc", lyric_syl="begin"),
    make_pitch_note("G", 2, 3840, "quarter", alter=-1, lyric_text="tum,", lyric_syl="end"),
]

v_map_122 = {
    "P1": c1_s1_122, "P2": c1_s2_122, "P3": c1_a_122, "P4": c1_a_122,
    "P5": c1_t1_122, "P6": c1_t2_122, "P7": c1_b_122, "P8": c1_b_122,
    "P9": c2_s1_122, "P10": c2_s2_122, "P11": c2_a_122, "P12": c2_a_122,
    "P13": c2_t1_122, "P14": c2_t2_122, "P15": c2_b_122, "P16": c2_b_122,
}
add_measure(parts, 122, "122", v_map_122, time_sig=None)

# =========================================================================
# m123 (4/4 = 15360) - printed 122
# Choir 1: quarter chords "sanc - tum tu - " (tied to m.124)
# Choir 2 SSAA: rest
# Choir 2 TB: quarter rest, half chord "sanc -", quarter chord "tum,"
# =========================================================================
c1_s1_123 = [
    make_pitch_note("A", 5, 3840, "quarter", alter=-1, lyric_text="sanc", lyric_syl="begin"),
    make_pitch_note("F", 5, 3840, "quarter", lyric_text="tum", lyric_syl="end"),
    make_pitch_note("A", 5, 3840, "quarter", alter=-1, lyric_text="tu", lyric_syl="begin"),
    make_pitch_note("A", 5, 3840, "quarter", alter=-1, tie="start"),
]
c1_s2_123 = [
    make_pitch_note("E", 5, 3840, "quarter", alter=-1, lyric_text="sanc", lyric_syl="begin"),
    make_pitch_note("D", 5, 3840, "quarter", alter=-1, lyric_text="tum", lyric_syl="end"),
    make_pitch_note("E", 5, 3840, "quarter", alter=-1, lyric_text="tu", lyric_syl="begin"),
    make_pitch_note("E", 5, 3840, "quarter", alter=-1, tie="start"),
]
c1_a_123 = [
    make_pitch_note("C", 5, 3840, "quarter", lyric_text="sanc", lyric_syl="begin"),
    make_pitch_note("B", 4, 3840, "quarter", alter=-1, lyric_text="tum", lyric_syl="end"),
    make_pitch_note("C", 5, 3840, "quarter", lyric_text="tu", lyric_syl="begin"),
    make_pitch_note("C", 5, 3840, "quarter", tie="start"),
]
c1_t1_123 = [
    make_rest_note(3840, "quarter"),
    make_pitch_note("F", 4, 7680, "half", lyric_text="sanc", lyric_syl="begin"),
    make_pitch_note("G", 4, 3840, "quarter", lyric_text="tum", lyric_syl="end"),
]
c1_t2_123 = [
    make_rest_note(3840, "quarter"),
    make_pitch_note("D", 4, 7680, "half", alter=-1, lyric_text="sanc", lyric_syl="begin"),
    make_pitch_note("E", 4, 3840, "quarter", alter=-1, lyric_text="tum", lyric_syl="end"),
]
c1_b1_123 = [
    make_rest_note(3840, "quarter"),
    make_pitch_note("A", 3, 7680, "half", alter=-1, lyric_text="sanc", lyric_syl="begin"),
    make_pitch_note("B", 3, 3840, "quarter", alter=-1, lyric_text="tum", lyric_syl="end"),
]
c1_b2_123 = [
    make_rest_note(3840, "quarter"),
    make_pitch_note("D", 3, 7680, "half", alter=-1, lyric_text="sanc", lyric_syl="begin"),
    make_pitch_note("E", 3, 3840, "quarter", alter=-1, lyric_text="tum", lyric_syl="end"),
]

v_map_123 = {
    "P1": c1_s1_123, "P2": c1_s2_123, "P3": c1_a_123, "P4": c1_a_123,
    "P5": c1_t1_123, "P6": c1_t2_123, "P7": c1_b1_123, "P8": c1_b2_123,
    "P9": r15360, "P10": r15360, "P11": r15360, "P12": r15360,
    "P13": c1_t1_123, "P14": c1_t2_123, "P15": c1_b1_123, "P16": c1_b2_123,
}
add_measure(parts, 123, "123", v_map_123, time_sig=None)

# =========================================================================
# m124 (4/4 = 15360) - printed 123
# Choir 1 SSAA: whole note chord (tied from m.123 and into m.125) "um."
# Choir 1 TB: whole note chord (tied into m.125) "tu - - - - um."
# Choir 2: quarter rest, quarter chord "sanc -" (tied), eighth chord,
#          quarter chord "tum", eighth chord "tu" (tied into m.125)
# =========================================================================
c1_s1_124 = [make_pitch_note("A", 5, 15360, "whole", alter=-1, tie="both", lyric_text="um.", lyric_syl="end")]
c1_s2_124 = [make_pitch_note("E", 5, 15360, "whole", alter=-1, tie="both", lyric_text="um.", lyric_syl="end")]
c1_a_124  = [make_pitch_note("C", 5, 15360, "whole", tie="both", lyric_text="um.", lyric_syl="end")]

c1_t1_124 = [make_pitch_note("C", 4, 15360, "whole", tie="start", lyric_text="tu", lyric_syl="begin")]
c1_t2_124 = [make_pitch_note("A", 3, 15360, "whole", alter=-1, tie="start", lyric_text="tu", lyric_syl="begin")]
c1_b1_124 = [make_pitch_note("E", 3, 15360, "whole", alter=-1, tie="start", lyric_text="tu", lyric_syl="begin")]
c1_b2_124 = [make_pitch_note("A", 2, 15360, "whole", alter=-1, tie="start", lyric_text="tu", lyric_syl="begin")]

c2_s1_124 = [
    make_rest_note(3840, "quarter"),
    make_pitch_note("E", 5, 3840, "quarter", alter=-1, tie="start", lyric_text="sanc", lyric_syl="begin"),
    make_pitch_note("E", 5, 1920, "eighth", alter=-1, tie="stop"),
    make_pitch_note("D", 5, 3840, "quarter", alter=-1, lyric_text="tum", lyric_syl="end"),
    make_pitch_note("E", 5, 1920, "eighth", alter=-1, tie="start", lyric_text="tu", lyric_syl="begin"),
]
c2_s2_124 = [
    make_rest_note(3840, "quarter"),
    make_pitch_note("C", 5, 3840, "quarter", tie="start", lyric_text="sanc", lyric_syl="begin"),
    make_pitch_note("C", 5, 1920, "eighth", tie="stop"),
    make_pitch_note("B", 4, 3840, "quarter", alter=-1, lyric_text="tum", lyric_syl="end"),
    make_pitch_note("C", 5, 1920, "eighth", tie="start", lyric_text="tu", lyric_syl="begin"),
]
c2_a_124 = [
    make_rest_note(3840, "quarter"),
    make_pitch_note("C", 5, 3840, "quarter", tie="start", lyric_text="sanc", lyric_syl="begin"),
    make_pitch_note("C", 5, 1920, "eighth", tie="stop"),
    make_pitch_note("B", 4, 3840, "quarter", alter=-1, lyric_text="tum", lyric_syl="end"),
    make_pitch_note("C", 5, 1920, "eighth", tie="start", lyric_text="tu", lyric_syl="begin"),
]
c2_t1_124 = [
    make_rest_note(3840, "quarter"),
    make_pitch_note("C", 4, 3840, "quarter", tie="start", lyric_text="sanc", lyric_syl="begin"),
    make_pitch_note("C", 4, 1920, "eighth", tie="stop"),
    make_pitch_note("D", 4, 3840, "quarter", alter=-1, lyric_text="tum", lyric_syl="end"),
    make_pitch_note("C", 4, 1920, "eighth", tie="start", lyric_text="tu", lyric_syl="begin"),
]
c2_t2_124 = [
    make_rest_note(3840, "quarter"),
    make_pitch_note("A", 3, 3840, "quarter", alter=-1, tie="start", lyric_text="sanc", lyric_syl="begin"),
    make_pitch_note("A", 3, 1920, "eighth", alter=-1, tie="stop"),
    make_pitch_note("B", 3, 3840, "quarter", alter=-1, lyric_text="tum", lyric_syl="end"),
    make_pitch_note("A", 3, 1920, "eighth", alter=-1, tie="start", lyric_text="tu", lyric_syl="begin"),
]
c2_b1_124 = [
    make_rest_note(3840, "quarter"),
    make_pitch_note("E", 3, 3840, "quarter", alter=-1, tie="start", lyric_text="sanc", lyric_syl="begin"),
    make_pitch_note("E", 3, 1920, "eighth", alter=-1, tie="stop"),
    make_pitch_note("F", 3, 3840, "quarter", lyric_text="tum", lyric_syl="end"),
    make_pitch_note("E", 3, 1920, "eighth", alter=-1, tie="start", lyric_text="tu", lyric_syl="begin"),
]
c2_b2_124 = [
    make_rest_note(3840, "quarter"),
    make_pitch_note("A", 2, 3840, "quarter", alter=-1, tie="start", lyric_text="sanc", lyric_syl="begin"),
    make_pitch_note("A", 2, 1920, "eighth", alter=-1, tie="stop"),
    make_pitch_note("B", 2, 3840, "quarter", alter=-1, lyric_text="tum,", lyric_syl="end"),
    make_pitch_note("A", 2, 1920, "eighth", alter=-1, tie="start", lyric_text="tu", lyric_syl="begin"),
]

v_map_124 = {
    "P1": c1_s1_124, "P2": c1_s2_124, "P3": c1_a_124, "P4": c1_a_124,
    "P5": c1_t1_124, "P6": c1_t2_124, "P7": c1_b1_124, "P8": c1_b2_124,
    "P9": c2_s1_124, "P10": c2_s2_124, "P11": c2_a_124, "P12": c2_a_124,
    "P13": c2_t1_124, "P14": c2_t2_124, "P15": c2_b1_124, "P16": c2_b2_124,
}
add_measure(parts, 124, "124", v_map_124, time_sig=None)

# =========================================================================
# m125 (4/4 = 15360) - printed 124 (Final Measure)
# Choir 1 SSAA: whole note chord (tied from m.124)
# Choir 1 TB: quarter note chord (tied), dotted half chord "um."
# Choir 2: quarter note chord (tied), dotted half chord "um."
# Barline: light-heavy final barline!
# =========================================================================
c1_s1_125 = [make_pitch_note("A", 5, 15360, "whole", alter=-1, tie="stop")]
c1_s2_125 = [make_pitch_note("E", 5, 15360, "whole", alter=-1, tie="stop")]
c1_a_125  = [make_pitch_note("C", 5, 15360, "whole", tie="stop")]

c1_t1_125 = [
    make_pitch_note("C", 4, 3840, "quarter", tie="stop"),
    make_pitch_note("C", 4, 11520, "half", is_dotted=True, lyric_text="um.", lyric_syl="end"),
]
c1_t2_125 = [
    make_pitch_note("A", 3, 3840, "quarter", alter=-1, tie="stop"),
    make_pitch_note("A", 3, 11520, "half", alter=-1, is_dotted=True, lyric_text="um.", lyric_syl="end"),
]
c1_b1_125 = [
    make_pitch_note("E", 3, 3840, "quarter", alter=-1, tie="stop"),
    make_pitch_note("E", 3, 11520, "half", alter=-1, is_dotted=True, lyric_text="um.", lyric_syl="end"),
]
c1_b2_125 = [
    make_pitch_note("A", 2, 3840, "quarter", alter=-1, tie="stop"),
    make_pitch_note("A", 2, 11520, "half", alter=-1, is_dotted=True, lyric_text="um.", lyric_syl="end"),
]

c2_s1_125 = [
    make_pitch_note("E", 5, 3840, "quarter", alter=-1, tie="stop"),
    make_pitch_note("E", 5, 11520, "half", alter=-1, is_dotted=True, lyric_text="um.", lyric_syl="end"),
]
c2_s2_125 = [
    make_pitch_note("C", 5, 3840, "quarter", tie="stop"),
    make_pitch_note("C", 5, 11520, "half", is_dotted=True, lyric_text="um.", lyric_syl="end"),
]
c2_a_125 = [
    make_pitch_note("C", 5, 3840, "quarter", tie="stop"),
    make_pitch_note("C", 5, 11520, "half", is_dotted=True, lyric_text="um.", lyric_syl="end"),
]
c2_t1_125 = [
    make_pitch_note("C", 4, 3840, "quarter", tie="stop"),
    make_pitch_note("C", 4, 11520, "half", is_dotted=True, lyric_text="um.", lyric_syl="end"),
]
c2_t2_125 = [
    make_pitch_note("A", 3, 3840, "quarter", alter=-1, tie="stop"),
    make_pitch_note("A", 3, 11520, "half", alter=-1, is_dotted=True, lyric_text="um.", lyric_syl="end"),
]
c2_b1_125 = [
    make_pitch_note("E", 3, 3840, "quarter", alter=-1, tie="stop"),
    make_pitch_note("E", 3, 11520, "half", alter=-1, is_dotted=True, lyric_text="um.", lyric_syl="end"),
]
c2_b2_125 = [
    make_pitch_note("A", 2, 3840, "quarter", alter=-1, tie="stop"),
    make_pitch_note("A", 2, 11520, "half", alter=-1, is_dotted=True, lyric_text="um.", lyric_syl="end"),
]

v_map_125 = {
    "P1": c1_s1_125, "P2": c1_s2_125, "P3": c1_a_125, "P4": c1_a_125,
    "P5": c1_t1_125, "P6": c1_t2_125, "P7": c1_b1_125, "P8": c1_b2_125,
    "P9": c2_s1_125, "P10": c2_s2_125, "P11": c2_a_125, "P12": c2_a_125,
    "P13": c2_t1_125, "P14": c2_t2_125, "P15": c2_b1_125, "P16": c2_b2_125,
}
add_measure(parts, 125, "125", v_map_125, time_sig=None)

# Add final light-heavy barline to m125 across all 16 parts
for pid, p in parts.items():
    m125 = p.findall("measure")[-1]
    bl = ET.SubElement(m125, "barline", location="right")
    bstyle = ET.SubElement(bl, "bar-style")
    bstyle.text = "light-heavy"

def sanitize_score_ties(root_elem: ET.Element):
    """Ensure all tie starts and stops are bidirectional and valid."""
    def get_pitch_key(n):
        p = n.find("pitch")
        if p is None:
            return None
        return (p.findtext("step"), p.findtext("alter", "0"), p.findtext("octave"))

    for p in root_elem.findall("part"):
        notes = []
        for m in p.findall("measure"):
            mnum = int(m.attrib.get("number", 0))
            for n in m.findall("note"):
                notes.append((mnum, n))
        
        sounding = [(m, n) for m, n in notes if n.find("rest") is None]
        for i in range(len(sounding) - 1):
            m1, n1 = sounding[i]
            m2, n2 = sounding[i+1]
            p1 = get_pitch_key(n1)
            p2 = get_pitch_key(n2)
            t1 = [t.attrib.get("type") for t in n1.findall("tie")]
            t2 = [t.attrib.get("type") for t in n2.findall("tie")]
            
            # Forward linking
            if p1 == p2 and "start" in t1 and "stop" not in t2:
                if m2 in (m1, m1 + 1):
                    ET.SubElement(n2, "tie", type="stop")
                    notat = n2.find("notations")
                    if notat is None:
                        notat = ET.SubElement(n2, "notations")
                    ET.SubElement(notat, "tied", type="stop")

            # Backward linking
            if p1 == p2 and "stop" in t2 and "start" not in t1:
                if m2 in (m1, m1 + 1):
                    ET.SubElement(n1, "tie", type="start")
                    notat = n1.find("notations")
                    if notat is None:
                        notat = ET.SubElement(n1, "notations")
                    ET.SubElement(notat, "tied", type="start")
            
            # Remove invalid tie start across different pitches
            if "start" in t1 and p1 != p2:
                for tie in list(n1.findall("tie")):
                    if tie.attrib.get("type") == "start":
                        n1.remove(tie)
                notat = n1.find("notations")
                if notat is not None:
                    for tied in list(notat.findall("tied")):
                        if tied.attrib.get("type") == "start":
                            notat.remove(tied)

            # Remove invalid tie stop across different pitches
            if "stop" in t2 and p1 != p2:
                for tie in list(n2.findall("tie")):
                    if tie.attrib.get("type") == "stop":
                        n2.remove(tie)
                notat = n2.find("notations")
                if notat is not None:
                    for tied in list(notat.findall("tied")):
                        if tied.attrib.get("type") == "stop":
                            notat.remove(tied)

print("Sanitizing score ties...")
sanitize_score_ties(root)

# Purge any internal build attributes (e.g. _scaled)
for elem in root.iter():
    if "_scaled" in elem.attrib:
        del elem.attrib["_scaled"]

# Ensure strict MusicXML schema element ordering
NOTE_CHILD_ORDER = [
    "grace", "cue", "chord",
    "pitch", "unpitched", "rest",
    "duration",
    "tie",
    "instrument",
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
note_order_map = {tag: i for i, tag in enumerate(NOTE_CHILD_ORDER)}

NOTATIONS_CHILD_ORDER = [
    "tied", "slur", "tuplet", "glissando", "slide", "ornaments",
    "technical", "articulations", "dynamics", "fermata", "arpeggiate",
    "non-arpeggiate", "accidental-mark", "other-notation"
]
notat_order_map = {tag: i for i, tag in enumerate(NOTATIONS_CHILD_ORDER)}

for n in root.iter("note"):
    children = list(n)
    children.sort(key=lambda c: note_order_map.get(c.tag, 999))
    n[:] = children

for notat in root.iter("notations"):
    children = list(notat)
    children.sort(key=lambda c: notat_order_map.get(c.tag, 999))
    notat[:] = children

print("MusicXML schema conformance applied.")
print("Section 12 complete.")

# Write intermediate test score
out_path_test = Path("output/test_clamavi_mm0_125.xml")
ET.indent(root, space="  ")
tree_out = ET.ElementTree(root)
tree_out.write(out_path_test, encoding="utf-8", xml_declaration=True)
print(f"Written test score to {out_path_test}")

# Write full final score
out_path_final = Path("output/Clamavi_de_tribulatione_mea_16voices.xml")
tree_out.write(out_path_final, encoding="utf-8", xml_declaration=True)
print(f"Written FINAL 16-voice score to {out_path_final}")
