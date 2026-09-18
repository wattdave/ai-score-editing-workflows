#!/usr/bin/env python3
"""Build Section 11 (mm. 111-121, Page 12) of Clamavi de tribulatione mea.

All 11 measures on Page 12 are transcribed directly from high-resolution crops
of the authoritative PDF scan.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from scripts.assemble_clamavi import (
    add_measure,
    make_pitch_note,
    make_rest_note,
)
import scripts.test_section10_build as s10

parts = s10.parts
root = s10.root

print("Assembling Section 11 (mm. 111-121, Page 12)...")

r15360 = [make_rest_note(15360, is_measure_rest=True)]
r7680  = [make_rest_note(7680)]
r3840  = [make_rest_note(3840)]

# =========================================================================
# m111 (4/4 = 15360) - printed 110: "rit. - - - tu - - - um."
# Homophonic SSAA & TB in both choirs
# =========================================================================
c1_s_111 = [
    make_pitch_note("C", 5, 5760, "quarter", alter=1, is_dotted=True, tie="stop"),
    make_pitch_note("B", 4, 1920, "eighth", tie="start", lyric_text="tu", lyric_syl="begin"),
    make_pitch_note("B", 4, 5760, "quarter", is_dotted=True, tie="stop"),
    make_pitch_note("D", 5, 1920, "eighth", alter=1, lyric_text="um.", lyric_syl="end"),
]
c1_a_111 = [
    make_pitch_note("A", 4, 1920, "eighth", tie="stop"),
    make_pitch_note("F", 4, 3840, "quarter", alter=1, lyric_text="tum", lyric_syl="end"),
    make_pitch_note("G", 4, 1920, "eighth", alter=1, tie="start", lyric_text="tu", lyric_syl="begin"),
    make_pitch_note("G", 4, 1920, "eighth", alter=1, tie="stop"),
    make_pitch_note("G", 4, 3840, "quarter", alter=1),
    make_pitch_note("C", 4, 1920, "eighth", alter=1, lyric_text="um.", lyric_syl="end"),
]
c1_t_111 = [
    make_pitch_note("G", 3, 1920, "eighth", alter=1, tie="stop"),
    make_pitch_note("E", 3, 3840, "quarter", lyric_text="tum", lyric_syl="end"),
    make_pitch_note("E", 3, 1920, "eighth", tie="start", lyric_text="tu", lyric_syl="begin"),
    make_pitch_note("E", 3, 1920, "eighth", tie="stop"),
    make_pitch_note("F", 3, 3840, "quarter", alter=1),
    make_pitch_note("A", 3, 1920, "eighth", lyric_text="um.", lyric_syl="end"),
]
c1_b_111 = [
    make_pitch_note("C", 3, 1920, "eighth", alter=1, tie="stop"),
    make_pitch_note("B", 2, 3840, "quarter", lyric_text="tum", lyric_syl="end"),
    make_pitch_note("C", 3, 1920, "eighth", alter=1, tie="start", lyric_text="tu", lyric_syl="begin"),
    make_pitch_note("C", 3, 1920, "eighth", alter=1, tie="stop"),
    make_pitch_note("D", 3, 1920, "eighth"),
    make_pitch_note("E", 3, 1920, "eighth", alter=1),
    make_pitch_note("F", 3, 1920, "eighth", alter=1, lyric_text="um.", lyric_syl="end"),
]

v_map_111 = {
    "P1": c1_s_111, "P2": c1_s_111, "P3": c1_a_111, "P4": c1_a_111,
    "P5": c1_t_111, "P6": c1_t_111, "P7": c1_b_111, "P8": c1_b_111,
    "P9": c1_s_111, "P10": c1_s_111, "P11": c1_a_111, "P12": c1_a_111,
    "P13": c1_t_111, "P14": c1_t_111, "P15": c1_b_111, "P16": c1_b_111,
}
add_measure(parts, 111, "111", v_map_111, time_sig=(4, 4))

# =========================================================================
# m112 (4/4 = 15360): Dotted half chord "um." + quarter rest
# =========================================================================
c1_s_112 = [make_pitch_note("C", 5, 11520, "half", alter=1, is_dotted=True, lyric_text="um.", lyric_syl="end"), make_rest_note(3840, "quarter")]
c1_a_112 = [make_pitch_note("C", 4, 11520, "half", alter=1, is_dotted=True, lyric_text="um.", lyric_syl="end"), make_rest_note(3840, "quarter")]
c1_t_112 = [make_pitch_note("E", 3, 11520, "half", is_dotted=True, lyric_text="um.", lyric_syl="end"), make_rest_note(3840, "quarter")]
c1_b_112 = [make_pitch_note("A", 2, 11520, "half", is_dotted=True, lyric_text="um.", lyric_syl="end"), make_rest_note(3840, "quarter")]

v_map_112 = {
    "P1": c1_s_112, "P2": c1_s_112, "P3": c1_a_112, "P4": c1_a_112,
    "P5": c1_t_112, "P6": c1_t_112, "P7": c1_b_112, "P8": c1_b_112,
    "P9": c1_s_112, "P10": c1_s_112, "P11": c1_a_112, "P12": c1_a_112,
    "P13": c1_t_112, "P14": c1_t_112, "P15": c1_b_112, "P16": c1_b_112,
}
add_measure(parts, 112, "112", v_map_112, time_sig=None)

# =========================================================================
# m113 (4/4 = 15360) - printed 111: "a tempo quarter=66", p
# =========================================================================
c1_s_113 = [make_rest_note(7680, "half"), make_pitch_note("D", 4, 7680, "half", alter=1, lyric_text="ad", lyric_syl="single")]
c1_t1_113 = [make_pitch_note("F", 3, 15360, "whole", tie="start", lyric_text="ad", lyric_syl="begin")]
c1_t2_113 = [make_pitch_note("D", 3, 15360, "whole", tie="start", lyric_text="ad", lyric_syl="begin")]
c1_b_113  = [make_pitch_note("B", 2, 15360, "whole", alter=-1, tie="start", lyric_text="ad", lyric_syl="begin")]

v_map_113 = {
    "P1": c1_s_113, "P2": c1_s_113, "P3": r15360, "P4": r15360,
    "P5": c1_t1_113, "P6": c1_t2_113, "P7": c1_b_113, "P8": c1_b_113,
    "P9": r15360, "P10": r15360, "P11": r15360, "P12": r15360,
    "P13": c1_t1_113, "P14": c1_t2_113, "P15": c1_b_113, "P16": c1_b_113,
}
add_measure(parts, 113, "113", v_map_113, time_sig=None)

# =========================================================================
# m114 (4/4 = 15360) - printed 112
# =========================================================================
c1_s_114 = [make_pitch_note("G", 5, 15360, "whole", tie="start", lyric_text="tem", lyric_syl="begin")]
c1_a_114 = [make_rest_note(7680, "half"), make_pitch_note("B", 3, 7680, "half", alter=-1, lyric_text="ad", lyric_syl="single")]
c1_t1_114 = [make_pitch_note("F", 3, 7680, "half", tie="stop"), make_pitch_note("A", 3, 7680, "half", alter=-1)]
c1_t2_114 = [make_pitch_note("D", 3, 7680, "half", tie="stop"), make_pitch_note("F", 3, 7680, "half")]
c1_b_114  = [make_pitch_note("B", 2, 7680, "half", alter=-1, tie="stop"), make_pitch_note("D", 3, 7680, "half", alter=-1)]

v_map_114 = {
    "P1": c1_s_114, "P2": c1_s_114, "P3": c1_a_114, "P4": c1_a_114,
    "P5": c1_t1_114, "P6": c1_t2_114, "P7": c1_b_114, "P8": c1_b_114,
    "P9": r15360, "P10": r15360, "P11": c1_a_114, "P12": c1_a_114,
    "P13": c1_t1_114, "P14": c1_t2_114, "P15": c1_b_114, "P16": c1_b_114,
}
add_measure(parts, 114, "114", v_map_114, time_sig=None)

# =========================================================================
# m115 (4/4 = 15360) - printed 113
# =========================================================================
c1_s_115 = [make_pitch_note("G", 5, 15360, "whole", tie="both")]
c1_a_115 = [make_pitch_note("B", 3, 15360, "whole", alter=0, lyric_text="tem", lyric_syl="begin")]
c1_t_115 = [make_pitch_note("C", 4, 15360, "whole", tie="start", lyric_text="tem", lyric_syl="begin")]
c1_b_115 = [make_pitch_note("F", 3, 15360, "whole", tie="start", lyric_text="tem", lyric_syl="begin")]
c2_s_115 = [make_rest_note(7680, "half"), make_pitch_note("B", 4, 7680, "half", alter=0, lyric_text="ad", lyric_syl="single")]

v_map_115 = {
    "P1": c1_s_115, "P2": c1_s_115, "P3": c1_a_115, "P4": c1_a_115,
    "P5": c1_t_115, "P6": c1_t_115, "P7": c1_b_115, "P8": c1_b_115,
    "P9": c2_s_115, "P10": c2_s_115, "P11": c1_a_115, "P12": c1_a_115,
    "P13": c1_t_115, "P14": c1_t_115, "P15": c1_b_115, "P16": c1_b_115,
}
add_measure(parts, 115, "115", v_map_115, time_sig=None)

# =========================================================================
# m116 (4/4 = 15360) - printed 114
# =========================================================================
c1_s_116 = [make_pitch_note("G", 5, 15360, "whole", tie="stop")]
c1_a_116 = [
    make_pitch_note("C", 4, 7680, "half"),
    make_pitch_note("C", 4, 7680, "half", tie="start", lyric_text="plum", lyric_syl="single"),
]
c1_t_116 = [
    make_pitch_note("C", 4, 7680, "half", tie="stop"),
    make_pitch_note("E", 4, 7680, "half", alter=-1, tie="start", lyric_text="plum", lyric_syl="single"),
]
c1_b_116 = [
    make_pitch_note("F", 3, 7680, "half", tie="stop"),
    make_pitch_note("A", 3, 7680, "half", alter=-1, tie="start", lyric_text="plum", lyric_syl="single"),
]
c2_s_116 = [
    make_pitch_note("D", 5, 11520, "half", alter=-1, is_dotted=True, lyric_text="tem", lyric_syl="begin"),
    make_pitch_note("B", 4, 3840, "quarter", alter=-1, lyric_text="plum", lyric_syl="single"),
]

v_map_116 = {
    "P1": c1_s_116, "P2": c1_s_116, "P3": c1_a_116, "P4": c1_a_116,
    "P5": c1_t_116, "P6": c1_t_116, "P7": c1_b_116, "P8": c1_b_116,
    "P9": c2_s_116, "P10": c2_s_116, "P11": c1_a_116, "P12": c1_a_116,
    "P13": c1_t_116, "P14": c1_t_116, "P15": c1_b_116, "P16": c1_b_116,
}
add_measure(parts, 116, "116", v_map_116, time_sig=None)

# =========================================================================
# m117 (4/4 = 15360) - printed 115
# =========================================================================
c1_s_117 = [
    make_pitch_note("F", 5, 3840, "quarter", lyric_text="plum", lyric_syl="end"),
    make_pitch_note("E", 5, 3840, "quarter", alter=-1),
    make_pitch_note("F", 5, 7680, "half", tie="start", lyric_text="sanc", lyric_syl="begin"),
]
c1_a_117 = [
    make_pitch_note("C", 4, 7680, "half", tie="stop"),
    make_pitch_note("D", 5, 7680, "half", tie="start", lyric_text="sanc", lyric_syl="begin"),
]
c1_t_117 = [
    make_pitch_note("E", 4, 7680, "half", alter=-1, tie="stop"),
    make_pitch_note("D", 4, 7680, "half", tie="start", lyric_text="sanc", lyric_syl="begin"),
]
c1_b_117 = [
    make_pitch_note("A", 3, 7680, "half", alter=-1, tie="stop"),
    make_pitch_note("G", 3, 7680, "half", tie="start", lyric_text="sanc", lyric_syl="begin"),
]
c2_s_117 = [
    make_pitch_note("A", 4, 11520, "half", is_dotted=True, lyric_text="sanc", lyric_syl="begin"),
    make_pitch_note("B", 4, 3840, "quarter", alter=0),
]

v_map_117 = {
    "P1": c1_s_117, "P2": c1_s_117, "P3": c1_a_117, "P4": c1_a_117,
    "P5": c1_t_117, "P6": c1_t_117, "P7": c1_b_117, "P8": c1_b_117,
    "P9": c2_s_117, "P10": c2_s_117, "P11": c1_a_117, "P12": c1_a_117,
    "P13": c1_t_117, "P14": c1_t_117, "P15": c1_b_117, "P16": c1_b_117,
}
add_measure(parts, 117, "117", v_map_117, time_sig=None)

# =========================================================================
# m118 (4/4 = 15360) - printed 117
# =========================================================================
c1_s_118 = [
    make_pitch_note("F", 5, 7680, "half", tie="stop"),
    make_pitch_note("E", 5, 7680, "half", alter=-1, lyric_text="tum", lyric_syl="end"),
]
c1_a_118 = [
    make_pitch_note("D", 5, 7680, "half", tie="stop"),
    make_pitch_note("B", 4, 7680, "half", alter=-1, lyric_text="tum", lyric_syl="end"),
]
c1_t1_118 = [
    make_pitch_note("D", 4, 7680, "half", tie="stop"),
    make_pitch_note("E", 4, 7680, "half", alter=-1, lyric_text="tum", lyric_syl="end"),
]
c1_t2_118 = [
    make_pitch_note("D", 4, 7680, "half", tie="stop"),
    make_pitch_note("B", 3, 7680, "half", alter=-1, lyric_text="tum", lyric_syl="end"),
]
c1_b_118 = [
    make_pitch_note("G", 3, 7680, "half", tie="stop"),
    make_pitch_note("E", 3, 7680, "half", alter=-1, lyric_text="tum", lyric_syl="end"),
]
c2_s_118 = [
    make_pitch_note("C", 5, 7680, "half"),
    make_pitch_note("B", 4, 7680, "half", alter=-1, lyric_text="tum", lyric_syl="end"),
]

v_map_118 = {
    "P1": c1_s_118, "P2": c1_s_118, "P3": c1_a_118, "P4": c1_a_118,
    "P5": c1_t1_118, "P6": c1_t2_118, "P7": c1_b_118, "P8": c1_b_118,
    "P9": c2_s_118, "P10": c2_s_118, "P11": c1_a_118, "P12": c1_a_118,
    "P13": c1_t1_118, "P14": c1_t2_118, "P15": c1_b_118, "P16": c1_b_118,
}
add_measure(parts, 118, "118", v_map_118, time_sig=None)

# =========================================================================
# m119 (4/4 = 15360) - printed 118
# =========================================================================
c_s_119 = [
    make_pitch_note("D", 5, 3840, "quarter", alter=-1, tie="start", lyric_text="tu", lyric_syl="begin"),
    make_pitch_note("D", 5, 11520, "half", alter=-1, is_dotted=True, tie="stop"),
]
c_a_119 = [
    make_pitch_note("A", 4, 15360, "whole", alter=-1, lyric_text="tu", lyric_syl="begin"),
]
c_t1_119 = [
    make_pitch_note("D", 4, 15360, "whole", alter=-1, lyric_text="tu", lyric_syl="begin"),
]
c_t2_119 = [
    make_pitch_note("A", 3, 15360, "whole", alter=-1, lyric_text="tu", lyric_syl="begin"),
]
c_b_119 = [
    make_pitch_note("D", 3, 15360, "whole", alter=-1, lyric_text="tu", lyric_syl="begin"),
]

v_map_119 = {
    "P1": c_s_119, "P2": c_s_119, "P3": c_a_119, "P4": c_a_119,
    "P5": c_t1_119, "P6": c_t2_119, "P7": c_b_119, "P8": c_b_119,
    "P9": c_s_119, "P10": c_s_119, "P11": c_a_119, "P12": c_a_119,
    "P13": c_t1_119, "P14": c_t2_119, "P15": c_b_119, "P16": c_b_119,
}
add_measure(parts, 119, "119", v_map_119, time_sig=None)

# =========================================================================
# m120 (4/4 = 15360) - printed 119
# =========================================================================
c1_s1_120 = [
    make_pitch_note("F", 5, 7680, "half", lyric_text="um,", lyric_syl="end"),
    make_pitch_note("F", 5, 7680, "half", lyric_text="ad", lyric_syl="single"),
]
c1_s2_120 = [
    make_pitch_note("C", 5, 7680, "half", lyric_text="um,", lyric_syl="end"),
    make_pitch_note("D", 5, 7680, "half", alter=-1, lyric_text="ad", lyric_syl="single"),
]
c1_a_120 = [
    make_pitch_note("C", 5, 7680, "half", lyric_text="um,", lyric_syl="end"),
    make_pitch_note("B", 4, 7680, "half", alter=-1, lyric_text="ad", lyric_syl="single"),
]
c1_t1_120 = [
    make_pitch_note("C", 4, 7680, "half", lyric_text="um,", lyric_syl="end"),
    make_pitch_note("B", 3, 7680, "half", alter=-1, lyric_text="ad", lyric_syl="single"),
]
c1_t2_120 = [
    make_pitch_note("F", 3, 7680, "half", lyric_text="um,", lyric_syl="end"),
    make_pitch_note("F", 3, 7680, "half", lyric_text="ad", lyric_syl="single"),
]
c1_b_120 = [
    make_pitch_note("F", 3, 7680, "half", lyric_text="um,", lyric_syl="end"),
    make_pitch_note("B", 2, 7680, "half", alter=-1, lyric_text="ad", lyric_syl="single"),
]
c2_s1_120 = [
    make_pitch_note("F", 5, 7680, "half", lyric_text="um,", lyric_syl="end"),
    make_rest_note(7680, "half"),
]
c2_s2_120 = [
    make_pitch_note("C", 5, 7680, "half", lyric_text="um,", lyric_syl="end"),
    make_rest_note(7680, "half"),
]
c2_a_120 = [
    make_pitch_note("C", 5, 7680, "half", lyric_text="um,", lyric_syl="end"),
    make_rest_note(7680, "half"),
]
c2_t1_120 = [
    make_pitch_note("C", 4, 7680, "half", lyric_text="um,", lyric_syl="end"),
    make_rest_note(7680, "half"),
]
c2_t2_120 = [
    make_pitch_note("F", 3, 7680, "half", lyric_text="um,", lyric_syl="end"),
    make_rest_note(7680, "half"),
]
c2_b_120 = [
    make_pitch_note("F", 3, 7680, "half", lyric_text="um,", lyric_syl="end"),
    make_rest_note(7680, "half"),
]

v_map_120 = {
    "P1": c1_s1_120, "P2": c1_s2_120, "P3": c1_a_120, "P4": c1_a_120,
    "P5": c1_t1_120, "P6": c1_t2_120, "P7": c1_b_120, "P8": c1_b_120,
    "P9": c2_s1_120, "P10": c2_s2_120, "P11": c2_a_120, "P12": c2_a_120,
    "P13": c2_t1_120, "P14": c2_t2_120, "P15": c2_b_120, "P16": c2_b_120,
}
add_measure(parts, 120, "120", v_map_120, time_sig=None)

# =========================================================================
# m121 (4/4 = 15360) - printed 120
# =========================================================================
c1_s1_121 = [
    make_pitch_note("F", 5, 7680, "half", lyric_text="tem", lyric_syl="begin"),
    make_pitch_note("E", 5, 1920, "eighth", alter=-1, lyric_text="plum", lyric_syl="end"),
    make_pitch_note("F", 5, 3840, "quarter", lyric_text="sanc", lyric_syl="begin"),
    make_pitch_note("E", 5, 1920, "eighth", alter=-1, lyric_text="tum", lyric_syl="end"),
]
c1_s2_121 = [
    make_pitch_note("D", 5, 7680, "half", alter=-1, lyric_text="tem", lyric_syl="begin"),
    make_pitch_note("C", 5, 1920, "eighth", lyric_text="plum", lyric_syl="end"),
    make_pitch_note("D", 5, 3840, "quarter", alter=-1, lyric_text="sanc", lyric_syl="begin"),
    make_pitch_note("C", 5, 1920, "eighth", lyric_text="tum", lyric_syl="end"),
]
c1_a_121 = [
    make_pitch_note("B", 4, 7680, "half", alter=-1, lyric_text="tem", lyric_syl="begin"),
    make_pitch_note("A", 4, 1920, "eighth", alter=-1, lyric_text="plum", lyric_syl="end"),
    make_pitch_note("B", 4, 3840, "quarter", alter=-1, lyric_text="sanc", lyric_syl="begin"),
    make_pitch_note("A", 4, 1920, "eighth", alter=-1, lyric_text="tum", lyric_syl="end"),
]
c1_t_121 = [
    make_pitch_note("B", 3, 7680, "half", alter=-1, lyric_text="tem", lyric_syl="begin"),
    make_pitch_note("A", 3, 1920, "eighth", alter=-1, lyric_text="plum", lyric_syl="end"),
    make_pitch_note("B", 3, 3840, "quarter", alter=-1, lyric_text="sanc", lyric_syl="begin"),
    make_pitch_note("A", 3, 1920, "eighth", alter=-1, lyric_text="tum", lyric_syl="end"),
]
c1_b_121 = [
    make_pitch_note("B", 2, 7680, "half", alter=-1, lyric_text="tem", lyric_syl="begin"),
    make_pitch_note("A", 2, 1920, "eighth", alter=-1, lyric_text="plum", lyric_syl="end"),
    make_pitch_note("B", 2, 3840, "quarter", alter=-1, lyric_text="sanc", lyric_syl="begin"),
    make_pitch_note("A", 2, 1920, "eighth", alter=-1, lyric_text="tum", lyric_syl="end"),
]
c2_s1_121 = [
    make_rest_note(3840, "quarter"),
    make_pitch_note("F", 5, 7680, "half", lyric_text="tem", lyric_syl="begin"),
    make_pitch_note("F", 5, 3840, "quarter", tie="start", lyric_text="plum", lyric_syl="single"),
]
c2_s2_121 = [
    make_rest_note(3840, "quarter"),
    make_pitch_note("D", 5, 7680, "half", alter=-1, lyric_text="tem", lyric_syl="begin"),
    make_pitch_note("D", 5, 3840, "quarter", alter=-1, tie="start", lyric_text="plum", lyric_syl="single"),
]
c2_a_121 = [
    make_rest_note(3840, "quarter"),
    make_pitch_note("B", 4, 7680, "half", alter=-1, lyric_text="tem", lyric_syl="begin"),
    make_pitch_note("B", 4, 3840, "quarter", alter=-1, tie="start", lyric_text="plum", lyric_syl="single"),
]
c2_t_121 = [
    make_rest_note(3840, "quarter"),
    make_pitch_note("B", 3, 7680, "half", alter=-1, lyric_text="tem", lyric_syl="begin"),
    make_pitch_note("B", 3, 3840, "quarter", alter=-1, tie="start", lyric_text="plum", lyric_syl="single"),
]
c2_b_121 = [
    make_rest_note(3840, "quarter"),
    make_pitch_note("B", 2, 7680, "half", alter=-1, lyric_text="tem", lyric_syl="begin"),
    make_pitch_note("B", 2, 3840, "quarter", alter=-1, tie="start", lyric_text="plum", lyric_syl="single"),
]

v_map_121 = {
    "P1": c1_s1_121, "P2": c1_s2_121, "P3": c1_a_121, "P4": c1_a_121,
    "P5": c1_t_121, "P6": c1_t_121, "P7": c1_b_121, "P8": c1_b_121,
    "P9": c2_s1_121, "P10": c2_s2_121, "P11": c2_a_121, "P12": c2_a_121,
    "P13": c2_t_121, "P14": c2_t_121, "P15": c2_b_121, "P16": c2_b_121,
}
add_measure(parts, 121, "121", v_map_121, time_sig=None)

print("Section 11 complete.")

out_path = Path("output/test_clamavi_mm0_121.xml")
ET.indent(root, space="  ")
tree_out = ET.ElementTree(root)
tree_out.write(out_path, encoding="utf-8", xml_declaration=True)
print(f"Written test score to {out_path}")
