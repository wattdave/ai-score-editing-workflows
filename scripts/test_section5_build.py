import xml.etree.ElementTree as ET
import copy
from pathlib import Path
from scripts.assemble_clamavi import (
    add_measure,
    make_pitch_note,
    make_rest_note,
    clean_standard_note,
    demix_measure_notes,
    DIVISIONS,
)
import scripts.test_section4_build as s4

parts = s4.parts
root = s4.root
tree_raw = ET.parse('/Users/wattd/Downloads/Clamavi de tribulatione mea 12pp - 2021-06-23 b.xml')
root_raw = tree_raw.getroot()
parts_raw = {p.attrib.get("id"): p for p in root_raw.findall("part")}

def get_raw_notes(pid, m_idx):
    m = parts_raw[pid].findall("measure")[m_idx]
    return m.findall("note")

print("Assembling Section 5 (mm. 46-54)...")

# =========================================================================
# m46 (4/4 = 15360) - Choir 1 rests, Choir 2 sings "ter-rae vec-tes..."
# =========================================================================
r46 = [make_rest_note(15360, is_measure_rest=True)]
c2_s_46 = [clean_standard_note(n) for n in get_raw_notes("P7", 46)]
c2_a_46 = [clean_standard_note(n) for n in get_raw_notes("P8", 46)]
c2_t_46 = [clean_standard_note(n) for n in get_raw_notes("P9", 46)]
c2_b_top_46, c2_b_bot_46 = demix_measure_notes(get_raw_notes("P10", 46))

v_map_46 = {
    "P1": r46, "P2": r46, "P3": r46, "P4": r46,
    "P5": r46, "P6": r46, "P7": r46, "P8": r46,
    "P9": c2_s_46, "P10": c2_s_46, "P11": c2_a_46, "P12": c2_a_46,
    "P13": c2_t_46, "P14": c2_t_46, "P15": c2_b_top_46, "P16": c2_b_bot_46,
}
add_measure(parts, 46, "46", v_map_46, time_sig=(4, 4))

# =========================================================================
# m47 (2/4 = 7680) - Choir 1 rests, Choir 2 sings "me in ae -"
# =========================================================================
r47 = [make_rest_note(7680, is_measure_rest=True)]
c2_s_47 = [clean_standard_note(n) for n in get_raw_notes("P7", 47)]
c2_a_47 = [clean_standard_note(n) for n in get_raw_notes("P8", 47)]
c2_t_47 = [clean_standard_note(n) for n in get_raw_notes("P9", 47)]
c2_b_47 = [clean_standard_note(n) for n in get_raw_notes("P10", 47)]

v_map_47 = {
    "P1": r47, "P2": r47, "P3": r47, "P4": r47,
    "P5": r47, "P6": r47, "P7": r47, "P8": r47,
    "P9": c2_s_47, "P10": c2_s_47, "P11": c2_a_47, "P12": c2_a_47,
    "P13": c2_t_47, "P14": c2_t_47, "P15": c2_b_47, "P16": c2_b_47,
}
add_measure(parts, 47, "47", v_map_47, time_sig=(2, 4))

# =========================================================================
# m48 (3/8 = 5760) - Choir 1 rests, Choir 2 sings "- ter -"
# =========================================================================
r48 = [make_rest_note(5760, is_measure_rest=True)]
c2_s_48 = [clean_standard_note(n) for n in get_raw_notes("P7", 48)]
c2_a_48 = [clean_standard_note(n) for n in get_raw_notes("P8", 48)]
c2_t_48 = [clean_standard_note(n) for n in get_raw_notes("P9", 48)]
c2_b_48 = [clean_standard_note(n) for n in get_raw_notes("P10", 48)]

v_map_48 = {
    "P1": r48, "P2": r48, "P3": r48, "P4": r48,
    "P5": r48, "P6": r48, "P7": r48, "P8": r48,
    "P9": c2_s_48, "P10": c2_s_48, "P11": c2_a_48, "P12": c2_a_48,
    "P13": c2_t_48, "P14": c2_t_48, "P15": c2_b_48, "P16": c2_b_48,
}
add_measure(parts, 48, "48", v_map_48, time_sig=(3, 8))

# =========================================================================
# m49 (2/4 = 7680) - Choir 1 rests, Choir 2 sings "num"
# =========================================================================
r49 = [make_rest_note(7680, is_measure_rest=True)]
c2_s_49 = [clean_standard_note(n) for n in get_raw_notes("P7", 49)]
c2_a_49 = [clean_standard_note(n) for n in get_raw_notes("P8", 49)]
c2_t_49 = [clean_standard_note(n) for n in get_raw_notes("P9", 49)]
c2_b_49 = [clean_standard_note(n) for n in get_raw_notes("P10", 49)]

v_map_49 = {
    "P1": r49, "P2": r49, "P3": r49, "P4": r49,
    "P5": r49, "P6": r49, "P7": r49, "P8": r49,
    "P9": c2_s_49, "P10": c2_s_49, "P11": c2_a_49, "P12": c2_a_49,
    "P13": c2_t_49, "P14": c2_t_49, "P15": c2_b_49, "P16": c2_b_49,
}
add_measure(parts, 49, "49", v_map_49, time_sig=(2, 4))

# =========================================================================
# m50 (4/4 = 15360) - Both choirs sing
# =========================================================================
c1_s_top_50, c1_s_bot_50 = demix_measure_notes(get_raw_notes("P1", 50))
c1_a_50 = [clean_standard_note(n) for n in get_raw_notes("P2", 50)]
c1_t_top_50, c1_t_bot_50 = demix_measure_notes(get_raw_notes("P3", 50))
c1_b_top_50, c1_b_bot_50 = demix_measure_notes(get_raw_notes("P4", 50))

c2_s_top_50, c2_s_bot_50 = demix_measure_notes(get_raw_notes("P7", 50))
c2_a_50 = [clean_standard_note(n) for n in get_raw_notes("P8", 50)]
c2_t_top_50, c2_t_bot_50 = demix_measure_notes(get_raw_notes("P9", 50))
c2_b_top_50, c2_b_bot_50 = demix_measure_notes(get_raw_notes("P10", 50))

v_map_50 = {
    "P1": c1_s_top_50, "P2": c1_s_bot_50, "P3": c1_a_50, "P4": c1_a_50,
    "P5": c1_t_top_50, "P6": c1_t_bot_50, "P7": c1_b_top_50, "P8": c1_b_bot_50,
    "P9": c2_s_top_50, "P10": c2_s_bot_50, "P11": c2_a_50, "P12": c2_a_50,
    "P13": c2_t_top_50, "P14": c2_t_bot_50, "P15": c2_b_top_50, "P16": c2_b_bot_50,
}
add_measure(parts, 50, "50", v_map_50, time_sig=(4, 4))

# =========================================================================
# m51 (4/4 = 15360) - Both choirs sing
# =========================================================================
c1_s_top_51, c1_s_bot_51 = demix_measure_notes(get_raw_notes("P1", 51))
c1_a_top_51, c1_a_bot_51 = demix_measure_notes(get_raw_notes("P2", 51))
c1_t_top_51, c1_t_bot_51 = demix_measure_notes(get_raw_notes("P3", 51))
c1_b_top_51, c1_b_bot_51 = demix_measure_notes(get_raw_notes("P4", 51))

c2_s_top_51, c2_s_bot_51 = demix_measure_notes(get_raw_notes("P7", 51))
c2_a_top_51, c2_a_bot_51 = demix_measure_notes(get_raw_notes("P8", 51))
c2_t_top_51, c2_t_bot_51 = demix_measure_notes(get_raw_notes("P9", 51))
c2_b_top_51, c2_b_bot_51 = demix_measure_notes(get_raw_notes("P10", 51))

v_map_51 = {
    "P1": c1_s_top_51, "P2": c1_s_bot_51, "P3": c1_a_top_51, "P4": c1_a_bot_51,
    "P5": c1_t_top_51, "P6": c1_t_bot_51, "P7": c1_b_top_51, "P8": c1_b_bot_51,
    "P9": c2_s_top_51, "P10": c2_s_bot_51, "P11": c2_a_top_51, "P12": c2_a_bot_51,
    "P13": c2_t_top_51, "P14": c2_t_bot_51, "P15": c2_b_top_51, "P16": c2_b_bot_51,
}
add_measure(parts, 51, "51", v_map_51, time_sig=None)

# =========================================================================
# m52 (4/4 = 15360)
# =========================================================================
c1_s1_52 = [
    make_pitch_note("G", 5, 7680, "half", alter=0, lyric_text="ter-", lyric_syl="begin"),
    make_pitch_note("E", 5, 1920, "eighth", alter=0),
    make_pitch_note("G", 5, 3840, "quarter", alter=0),
    make_pitch_note("E", 5, 1920, "eighth", alter=0, tie="start"),
]
c1_s2_52 = [
    make_pitch_note("E", 5, 15360, "whole", alter=0, lyric_text="ter-", lyric_syl="begin", tie="start"),
]
c1_a1_52 = [
    make_pitch_note("B", 4, 3840, "quarter", alter=0, lyric_text="in", lyric_syl="single"),
    make_pitch_note("A", 4, 3840, "quarter", alter=0, lyric_text="ae-", lyric_syl="begin"),
    make_pitch_note("G", 4, 7680, "half", alter=0, lyric_text="num,", lyric_syl="end", tie="start"),
]
c1_a2_52 = [
    make_pitch_note("G", 4, 3840, "quarter", alter=0, lyric_text="in", lyric_syl="single"),
    make_pitch_note("F", 4, 3840, "quarter", alter=1, lyric_text="ae-", lyric_syl="begin"),
    make_pitch_note("E", 4, 3840, "quarter", alter=0, lyric_text="ter-", lyric_syl="middle"),
    make_pitch_note("G", 4, 3840, "quarter", alter=0, lyric_text="num,", lyric_syl="end"),
]
c1_t1_52 = [
    make_pitch_note("E", 4, 3840, "quarter", alter=0, lyric_text="in", lyric_syl="single"),
    make_pitch_note("D", 4, 3840, "quarter", alter=1, lyric_text="ae-", lyric_syl="begin"),
    make_pitch_note("B", 3, 3840, "quarter", alter=0, lyric_text="num,", lyric_syl="end"),
    make_rest_note(3840, "quarter"),
]
c1_t2_52 = [
    make_pitch_note("B", 3, 3840, "quarter", alter=0, lyric_text="in", lyric_syl="single"),
    make_pitch_note("A", 3, 3840, "quarter", alter=1, lyric_text="ae-", lyric_syl="begin"),
    make_pitch_note("G", 3, 3840, "quarter", alter=0, lyric_text="num,", lyric_syl="end"),
    make_rest_note(3840, "quarter"),
]
c1_b1_52 = [
    make_pitch_note("E", 3, 7680, "half", alter=0, lyric_text="ter-", lyric_syl="begin", tie="start"),
    make_pitch_note("B", 3, 7680, "half", alter=0, tie="both"),
]
c1_b2_52 = [
    make_pitch_note("B", 2, 15360, "whole", alter=0, lyric_text="ter-", lyric_syl="begin", tie="start"),
]

c2_s1_52 = [
    make_pitch_note("G", 5, 3840, "quarter", alter=0, lyric_text="in", lyric_syl="single"),
    make_pitch_note("F", 5, 3840, "quarter", alter=1, lyric_text="ae-", lyric_syl="begin"),
    make_pitch_note("E", 5, 1920, "eighth", alter=0, lyric_text="num,", lyric_syl="end"),
    make_rest_note(1920, "eighth"),
    make_rest_note(1920, "eighth"),
    make_pitch_note("E", 5, 1920, "eighth", alter=0, lyric_text="in", lyric_syl="single", tie="start"),
]
c2_s2_52 = [
    make_pitch_note("E", 5, 3840, "quarter", alter=0, lyric_text="in", lyric_syl="single"),
    make_pitch_note("D", 5, 3840, "quarter", alter=1, lyric_text="ae-", lyric_syl="begin"),
    make_pitch_note("B", 4, 3840, "quarter", alter=0, lyric_text="num,", lyric_syl="end"),
    make_pitch_note("A", 4, 3840, "quarter", alter=1, lyric_text="in", lyric_syl="single"),
]
c2_a1_52 = [
    make_pitch_note("B", 4, 3840, "quarter", alter=0, lyric_text="in", lyric_syl="single"),
    make_pitch_note("A", 4, 3840, "quarter", alter=0, lyric_text="ae-", lyric_syl="begin"),
    make_pitch_note("G", 4, 3840, "quarter", alter=0, lyric_text="ter-", lyric_syl="middle"),
    make_pitch_note("F", 4, 3840, "quarter", alter=1, lyric_text="num,", lyric_syl="end"),
]
c2_a2_52 = [
    make_pitch_note("G", 4, 3840, "quarter", alter=0, lyric_text="in", lyric_syl="single"),
    make_pitch_note("F", 4, 3840, "quarter", alter=1, lyric_text="ae-", lyric_syl="begin"),
    make_pitch_note("E", 4, 3840, "quarter", alter=0, lyric_text="ter-", lyric_syl="middle"),
    make_pitch_note("D", 4, 3840, "quarter", alter=1, lyric_text="num,", lyric_syl="end"),
]
c2_t1_52 = [clean_standard_note(n) for n in c1_t1_52]
c2_t2_52 = [clean_standard_note(n) for n in c1_t2_52]
c2_b1_52 = [clean_standard_note(n) for n in c1_b1_52]
c2_b2_52 = [clean_standard_note(n) for n in c1_b2_52]

v_map_52 = {
    "P1": c1_s1_52, "P2": c1_s2_52, "P3": c1_a1_52, "P4": c1_a2_52,
    "P5": c1_t1_52, "P6": c1_t2_52, "P7": c1_b1_52, "P8": c1_b2_52,
    "P9": c2_s1_52, "P10": c2_s2_52, "P11": c2_a1_52, "P12": c2_a2_52,
    "P13": c2_t1_52, "P14": c2_t2_52, "P15": c2_b1_52, "P16": c2_b2_52,
}
add_measure(parts, 52, "52", v_map_52, time_sig=None)

# =========================================================================
# m53 (4/4 = 15360)
# =========================================================================
c1_s1_53 = [
    make_pitch_note("E", 5, 3840, "quarter", alter=0, tie="stop"),
    make_pitch_note("B", 4, 3840, "quarter", alter=0),
    make_pitch_note("G", 4, 3840, "quarter", alter=0, lyric_text="num,", lyric_syl="end"),
    make_rest_note(1920, "eighth"),
    make_pitch_note("B", 4, 1920, "eighth", alter=0, lyric_text="in", lyric_syl="single", tie="start"),
]
c1_s2_53 = [
    make_pitch_note("B", 4, 7680, "half", alter=0, tie="stop"),
    make_pitch_note("G", 4, 5760, "quarter", is_dotted=True, alter=0, lyric_text="num,", lyric_syl="end"),
    make_rest_note(1920, "eighth"),
]
c1_a1_53 = [
    make_pitch_note("G", 4, 7680, "half", alter=0, lyric_text="in", lyric_syl="single", tie="stop"),
    make_pitch_note("E", 4, 3840, "quarter", alter=0, lyric_text="ae-", lyric_syl="begin"),
    make_pitch_note("D", 4, 3840, "quarter", alter=1, lyric_text="ter-", lyric_syl="middle"),
]
c1_a2_53 = [
    make_pitch_note("E", 4, 7680, "half", alter=0, lyric_text="in", lyric_syl="single"),
    make_pitch_note("B", 3, 1920, "eighth", alter=0, lyric_text="ae-", lyric_syl="begin"),
    make_pitch_note("A", 3, 5760, "quarter", is_dotted=True, alter=1, lyric_text="ter-", lyric_syl="middle"),
]
c1_t1_53 = [
    make_pitch_note("B", 3, 3840, "quarter", alter=0, lyric_text="in", lyric_syl="single"),
    make_pitch_note("A", 3, 3840, "quarter", alter=1, lyric_text="ae-", lyric_syl="begin"),
    make_pitch_note("G", 3, 3840, "quarter", alter=0, lyric_text="ter-", lyric_syl="middle"),
    make_pitch_note("F", 3, 3840, "quarter", alter=1, lyric_text="num,", lyric_syl="end", tie="start"),
]
c1_t2_53 = [
    make_pitch_note("G", 3, 7680, "half", alter=0, lyric_text="in", lyric_syl="single"),
    make_pitch_note("E", 3, 3840, "quarter", alter=0, lyric_text="ter-", lyric_syl="middle"),
    make_pitch_note("D", 3, 3840, "quarter", alter=1, lyric_text="num,", lyric_syl="end"),
]
c1_b1_53 = [
    make_pitch_note("B", 3, 5760, "quarter", is_dotted=True, alter=0, tie="stop"),
    make_pitch_note("G", 3, 1920, "eighth", alter=0),
    make_pitch_note("E", 3, 3840, "quarter", alter=0),
    make_pitch_note("B", 2, 3840, "quarter", alter=0, lyric_text="num,", lyric_syl="end"),
]
c1_b2_53 = [
    make_pitch_note("B", 2, 15360, "whole", alter=0, lyric_text="num,", lyric_syl="end", tie="stop"),
]

c2_s1_53 = [
    make_pitch_note("E", 5, 1920, "eighth", alter=0, tie="stop"),
    make_pitch_note("B", 4, 1920, "eighth", alter=0, lyric_text="ae-", lyric_syl="begin"),
    make_pitch_note("A", 4, 3840, "quarter", alter=1, lyric_text="ter-", lyric_syl="middle"),
    make_pitch_note("G", 4, 3840, "quarter", alter=0, lyric_text="num,", lyric_syl="end"),
    make_rest_note(3840, "quarter"),
]
c2_s2_53 = [
    make_pitch_note("G", 4, 3840, "quarter", alter=0, lyric_text="in", lyric_syl="single"),
    make_pitch_note("F", 4, 3840, "quarter", alter=1, lyric_text="ae-", lyric_syl="begin"),
    make_pitch_note("E", 4, 3840, "quarter", alter=0, lyric_text="ter-", lyric_syl="middle"),
    make_pitch_note("E", 4, 3840, "quarter", alter=0, lyric_text="num,", lyric_syl="end"),
]
c2_a1_53 = [
    make_rest_note(3840, "quarter"),
    make_pitch_note("F", 4, 3840, "quarter", alter=1, lyric_text="ae-", lyric_syl="begin"),
    make_pitch_note("E", 4, 3840, "quarter", alter=0, lyric_text="ter-", lyric_syl="middle"),
    make_pitch_note("D", 4, 3840, "quarter", alter=1, lyric_text="num,", lyric_syl="end"),
]
c2_a2_53 = [
    make_pitch_note("D", 4, 3840, "quarter", alter=1, lyric_text="ae-", lyric_syl="begin"),
    make_pitch_note("B", 3, 1920, "eighth", alter=0, lyric_text="ter-", lyric_syl="middle"),
    make_pitch_note("A", 3, 5760, "quarter", is_dotted=True, alter=1, lyric_text="num,", lyric_syl="end"),
    make_rest_note(3840, "quarter"),
]
c2_t1_53 = [clean_standard_note(n) for n in c1_t1_53]
c2_t2_53 = [clean_standard_note(n) for n in c1_t2_53]
c2_b1_53 = [clean_standard_note(n) for n in c1_b1_53]
c2_b2_53 = [clean_standard_note(n) for n in c1_b2_53]

v_map_53 = {
    "P1": c1_s1_53, "P2": c1_s2_53, "P3": c1_a1_53, "P4": c1_a2_53,
    "P5": c1_t1_53, "P6": c1_t2_53, "P7": c1_b1_53, "P8": c1_b2_53,
    "P9": c2_s1_53, "P10": c2_s2_53, "P11": c2_a1_53, "P12": c2_a2_53,
    "P13": c2_t1_53, "P14": c2_t2_53, "P15": c2_b1_53, "P16": c2_b2_53,
}
add_measure(parts, 53, "53", v_map_53, time_sig=None)

# =========================================================================
# m54 (4/4 = 15360)
# =========================================================================
c1_s1_54 = [
    make_pitch_note("B", 4, 7680, "half", alter=0, tie="stop"),
    make_pitch_note("B", 4, 3840, "quarter", alter=0),
    make_pitch_note("G", 4, 3840, "quarter", alter=1),
]
c1_s2_54 = [
    make_pitch_note("B", 4, 3840, "quarter", alter=0, lyric_text="in", lyric_syl="single"),
    make_pitch_note("A", 4, 3840, "quarter", alter=1, lyric_text="ae-", lyric_syl="begin"),
    make_pitch_note("G", 4, 3840, "quarter", alter=0, lyric_text="ter-", lyric_syl="middle"),
    make_pitch_note("F", 4, 3840, "quarter", alter=1, tie="start"),
]
c1_a1_54 = [
    make_pitch_note("E", 4, 3840, "quarter", alter=0, lyric_text="num,", lyric_syl="end"),
    make_pitch_note("F", 4, 3840, "quarter", alter=1, lyric_text="in", lyric_syl="single"),
    make_pitch_note("E", 4, 1920, "eighth", alter=0, lyric_text="ae-", lyric_syl="begin"),
    make_pitch_note("D", 4, 5760, "quarter", is_dotted=True, alter=1, lyric_text="ter-", lyric_syl="middle"),
]
c1_a2_54 = [
    make_pitch_note("G", 3, 3840, "quarter", alter=0, lyric_text="num,", lyric_syl="end"),
    make_pitch_note("F", 4, 3840, "quarter", alter=1, lyric_text="in", lyric_syl="single"),
    make_pitch_note("E", 4, 1920, "eighth", alter=0, lyric_text="ae-", lyric_syl="begin"),
    make_pitch_note("D", 4, 5760, "quarter", is_dotted=True, alter=1, lyric_text="ter-", lyric_syl="middle"),
]
c1_t1_54 = [
    make_pitch_note("E", 3, 3840, "quarter", alter=0, lyric_text="num,", lyric_syl="end"),
    make_pitch_note("B", 3, 3840, "quarter", alter=0, lyric_text="in", lyric_syl="single"),
    make_pitch_note("B", 3, 3840, "quarter", alter=0, lyric_text="ae-", lyric_syl="begin"),
    make_pitch_note("B", 3, 3840, "quarter", alter=0, lyric_text="ter-", lyric_syl="middle"),
]
c1_t2_54 = [
    make_pitch_note("E", 3, 3840, "quarter", alter=0, lyric_text="num,", lyric_syl="end"),
    make_rest_note(3840, "quarter"),
    make_pitch_note("B", 3, 3840, "quarter", alter=0, lyric_text="in", lyric_syl="single"),
    make_pitch_note("A", 3, 3840, "quarter", alter=1, lyric_text="ae-", lyric_syl="begin"),
]
c1_b1_54 = [
    make_pitch_note("B", 2, 3840, "quarter", alter=0, lyric_text="num,", lyric_syl="end"),
    make_rest_note(7680, "half"),
    make_rest_note(1920, "eighth"),
    make_pitch_note("G", 3, 1920, "eighth", alter=0, lyric_text="in", lyric_syl="single"),
]
c1_b2_54 = [
    make_pitch_note("B", 2, 3840, "quarter", alter=0, lyric_text="num,", lyric_syl="end"),
    make_rest_note(3840, "quarter"),
    make_rest_note(7680, "half"),
]

c2_s_54 = [make_pitch_note("E", 5, 3840, "quarter", alter=0, lyric_text="num,", lyric_syl="end"), make_rest_note(3840, "quarter"), make_rest_note(7680, "half")]
c2_a_54 = [make_pitch_note("B", 3, 3840, "quarter", alter=0, lyric_text="num,", lyric_syl="end"), make_rest_note(3840, "quarter"), make_rest_note(7680, "half")]
c2_t_54 = [make_pitch_note("E", 3, 3840, "quarter", alter=0, lyric_text="num,", lyric_syl="end"), make_rest_note(3840, "quarter"), make_rest_note(7680, "half")]
c2_b_54 = [make_pitch_note("B", 2, 3840, "quarter", alter=0, lyric_text="num,", lyric_syl="end"), make_rest_note(3840, "quarter"), make_rest_note(7680, "half")]

v_map_54 = {
    "P1": c1_s1_54, "P2": c1_s2_54, "P3": c1_a1_54, "P4": c1_a2_54,
    "P5": c1_t1_54, "P6": c1_t2_54, "P7": c1_b1_54, "P8": c1_b2_54,
    "P9": c2_s_54, "P10": c2_s_54, "P11": c2_a_54, "P12": c2_a_54,
    "P13": c2_t_54, "P14": c2_t_54, "P15": c2_b_54, "P16": c2_b_54,
}
add_measure(parts, 54, "54", v_map_54, time_sig=None)

print("Section 5 complete.")

out_path = Path("output/test_clamavi_mm0_54.xml")
ET.indent(root, space="  ")
tree_out = ET.ElementTree(root)
tree_out.write(out_path, encoding="utf-8", xml_declaration=True)
print(f"Written test score to {out_path}")
