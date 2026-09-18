import xml.etree.ElementTree as ET
import copy
from pathlib import Path
from scripts.assemble_clamavi import (
    create_base_score,
    add_measure,
    add_tutti_unison_measure,
    make_pitch_note,
    make_rest_note,
    clean_standard_note,
    demix_measure_notes,
    DIVISIONS,
)
import scripts.test_section3_build as s3

parts = s3.parts
root = s3.root
tree_raw = ET.parse('/Users/wattd/Downloads/Clamavi de tribulatione mea 12pp - 2021-06-23 b.xml')
root_raw = tree_raw.getroot()
parts_raw = {p.attrib.get("id"): p for p in root_raw.findall("part")}

def get_raw_notes(pid, m_idx):
    m = parts_raw[pid].findall("measure")[m_idx]
    return m.findall("note")

print("Assembling Section 4 (mm. 37-45)...")

# =========================================================================
# m37 (4/4 = 15360) - Choirs 1 & 2 unis.
# =========================================================================
# S1: F#5(1920), F#5(1920), F#5(5760 dot-qtr), E5(1920), D5(1920), C#5(1920) = 15360
s1_37 = [
    make_pitch_note("F", 5, 1920, "eighth", alter=1, lyric_text="Ad", lyric_syl="begin", accent=True),
    make_pitch_note("F", 5, 1920, "eighth", alter=1, lyric_text="ex-", lyric_syl="middle"),
    make_pitch_note("F", 5, 5760, "quarter", alter=1, is_dotted=True, lyric_text="tre-", lyric_syl="middle"),
    make_pitch_note("E", 5, 1920, "eighth", alter=0),
    make_pitch_note("D", 5, 1920, "eighth", alter=0, lyric_text="ma_", lyric_syl="end"),
    make_pitch_note("C", 5, 1920, "eighth", alter=1),
]

# S2: C#5(1920), C#5(1920), C#5(3840 qtr), triplet: E5(1280), D5(1280), C#5(1280), B4(1920), A4(1920) = 15360
s2_37 = [
    make_pitch_note("C", 5, 1920, "eighth", alter=1, lyric_text="Ad", lyric_syl="begin", accent=True),
    make_pitch_note("C", 5, 1920, "eighth", alter=1, lyric_text="ex-", lyric_syl="middle"),
    make_pitch_note("C", 5, 3840, "quarter", alter=1, lyric_text="tre-", lyric_syl="middle"),
    make_pitch_note("E", 5, 1280, "eighth", alter=0, tuplet="start"),
    make_pitch_note("D", 5, 1280, "eighth", alter=0),
    make_pitch_note("C", 5, 1280, "eighth", alter=1, tuplet="stop"),
    make_pitch_note("B", 4, 1920, "eighth", alter=0, lyric_text="ma_", lyric_syl="end"),
    make_pitch_note("A", 4, 1920, "eighth", alter=0),
]

# Alto (from raw P2): F#4(1920), F#4(1920), F#4(3840), F4(3840), F#4(1920), E4(1920)
a_37 = [clean_standard_note(n) for n in get_raw_notes("P2", 37)]

# Tenor (from raw P3): F#4(1920), F#4(1920), triplet F#3/A3/B3 (1280x3), C4(3840), B3(1920), A3(1920)
t_37 = [clean_standard_note(n) for n in get_raw_notes("P3", 37)]

# Bass (from raw P4): F#3(1920), F#3(1920), F#2(3840), triplet A2/B2/C3 (1280x3), D3(1920), E3(1920)
b_37 = [clean_standard_note(n) for n in get_raw_notes("P4", 37)]

v_map_37 = {
    "P1": s1_37, "P2": s2_37, "P9": s1_37, "P10": s2_37,
    "P3": a_37, "P4": a_37, "P11": a_37, "P12": a_37,
    "P5": t_37, "P6": t_37, "P13": t_37, "P14": t_37,
    "P7": b_37, "P8": b_37, "P15": b_37, "P16": b_37,
}
add_measure(parts, 37, "37", v_map_37, time_sig=(4, 4))

# =========================================================================
# m38 (3/4 = 11520) - Choirs 1 & 2 unis.
# =========================================================================
s_top_38, s_bot_38 = demix_measure_notes(get_raw_notes("P1", 38))
a_top_38, a_bot_38 = demix_measure_notes(get_raw_notes("P2", 38))
t_38 = [clean_standard_note(n) for n in get_raw_notes("P3", 38)]
b_38 = [clean_standard_note(n) for n in get_raw_notes("P4", 38)]

v_map_38 = {
    "P1": s_top_38, "P2": s_bot_38, "P9": s_top_38, "P10": s_bot_38,
    "P3": a_top_38, "P4": a_bot_38, "P11": a_top_38, "P12": a_bot_38,
    "P5": t_38, "P6": t_38, "P13": t_38, "P14": t_38,
    "P7": b_38, "P8": b_38, "P15": b_38, "P16": b_38,
}
add_measure(parts, 38, "38", v_map_38, time_sig=(3, 4))

# =========================================================================
# m39 (4/4 = 15360) - Choirs 1 & 2 unis.
# =========================================================================
s_39 = [clean_standard_note(n) for n in get_raw_notes("P1", 39)]

# Raw P2 m.39 has A1 (notes 0..3: 1920+3840+3840+5760=15360) and A2 (notes 4..7: 3840x4=15360)
p2_39_notes = [clean_standard_note(n) for n in get_raw_notes("P2", 39)]
a1_39 = p2_39_notes[0:4]
a2_39 = p2_39_notes[4:8]

t_39 = [clean_standard_note(n) for n in get_raw_notes("P3", 39)]
b_39 = [clean_standard_note(n) for n in get_raw_notes("P4", 39)[:1]] # single whole note D3 (15360)

v_map_39 = {
    "P1": s_39, "P2": s_39, "P9": s_39, "P10": s_39,
    "P3": a1_39, "P4": a2_39, "P11": a1_39, "P12": a2_39,
    "P5": t_39, "P6": t_39, "P13": t_39, "P14": t_39,
    "P7": b_39, "P8": b_39, "P15": b_39, "P16": b_39,
}
add_measure(parts, 39, "39", v_map_39, time_sig=(4, 4))

# =========================================================================
# m40 (4/4 = 15360) - Choirs 1 & 2 unis.
# =========================================================================
# P1 m.40: First 9 notes sum to 15360
s_40 = [clean_standard_note(n) for n in get_raw_notes("P1", 40)[:9]]

a_top_40, a_bot_40 = demix_measure_notes(get_raw_notes("P2", 40))
t_40 = [clean_standard_note(n) for n in get_raw_notes("P3", 40)]

# Bass has B1 (D3:11520 + G3:3840 = 15360) and B2 (D2:15360)
b1_40 = [
    make_pitch_note("D", 3, 11520, "half", is_dotted=True),
    make_pitch_note("G", 3, 3840, "quarter", lyric_text="di,", lyric_syl="end"),
]
b2_40 = [
    make_pitch_note("D", 2, 15360, "whole", lyric_text="di,", lyric_syl="end"),
]

v_map_40 = {
    "P1": s_40, "P2": s_40, "P9": s_40, "P10": s_40,
    "P3": a_top_40, "P4": a_bot_40, "P11": a_top_40, "P12": a_bot_40,
    "P5": t_40, "P6": t_40, "P13": t_40, "P14": t_40,
    "P7": b1_40, "P8": b2_40, "P15": b1_40, "P16": b2_40,
}
add_measure(parts, 40, "40", v_map_40, time_sig=None)

# =========================================================================
# m41 (3/4 = 11520) - Choirs 1 & 2 unis.
# =========================================================================
s_41 = [clean_standard_note(n) for n in get_raw_notes("P1", 41)]
a_41 = [clean_standard_note(n) for n in get_raw_notes("P2", 41)]
t_41 = [clean_standard_note(n) for n in get_raw_notes("P3", 41)]

# Bass B1: G3(1920), F3(1920), Eb3(7680) = 11520
# Bass B2: D2(5760), Eb2(1920), G2(1920), A2(1920) = 11520
b_raw_41 = [clean_standard_note(n) for n in get_raw_notes("P4", 41)]
b1_41 = b_raw_41[:3]
b2_41 = b_raw_41[3:]

v_map_41 = {
    "P1": s_41, "P2": s_41, "P9": s_41, "P10": s_41,
    "P3": a_41, "P4": a_41, "P11": a_41, "P12": a_41,
    "P5": t_41, "P6": t_41, "P13": t_41, "P14": t_41,
    "P7": b1_41, "P8": b2_41, "P15": b1_41, "P16": b2_41,
}
add_measure(parts, 41, "41", v_map_41, time_sig=(3, 4))

# =========================================================================
# m42 (3/4 = 11520) - Choirs 1 & 2 unis.
# =========================================================================
s_42 = [clean_standard_note(n) for n in get_raw_notes("P1", 42)]
a_42 = [clean_standard_note(n) for n in get_raw_notes("P2", 42)]
t_42 = [clean_standard_note(n) for n in get_raw_notes("P3", 42)]
b_top_42, b_bot_42 = demix_measure_notes(get_raw_notes("P4", 42))

v_map_42 = {
    "P1": s_42, "P2": s_42, "P9": s_42, "P10": s_42,
    "P3": a_42, "P4": a_42, "P11": a_42, "P12": a_42,
    "P5": t_42, "P6": t_42, "P13": t_42, "P14": t_42,
    "P7": b_top_42, "P8": b_bot_42, "P15": b_top_42, "P16": b_bot_42,
}
add_measure(parts, 42, "42", v_map_42, time_sig=None)

# =========================================================================
# m43 (4/4 = 15360) - Choir 1 TB alone, all others rest
# =========================================================================
r43 = [make_rest_note(15360, is_measure_rest=True)]
t_top_43, t_bot_43 = demix_measure_notes(get_raw_notes("P3", 43))
b_top_43, b_bot_43 = demix_measure_notes(get_raw_notes("P4", 43))

v_map_43 = {
    "P1": r43, "P2": r43, "P3": r43, "P4": r43,
    "P5": t_top_43, "P6": t_bot_43, "P7": b_top_43, "P8": b_bot_43,
    "P9": r43, "P10": r43, "P11": r43, "P12": r43,
    "P13": r43, "P14": r43, "P15": r43, "P16": r43,
}
add_measure(parts, 43, "43", v_map_43, time_sig=(4, 4))

# =========================================================================
# m44 (3/4 = 11520) - Choir 1 TB alone, all others rest
# =========================================================================
r44 = [make_rest_note(11520, is_measure_rest=True)]
t_top_44, t_bot_44 = demix_measure_notes(get_raw_notes("P3", 44))
b_top_44, b_bot_44 = demix_measure_notes(get_raw_notes("P4", 44))

v_map_44 = {
    "P1": r44, "P2": r44, "P3": r44, "P4": r44,
    "P5": t_top_44, "P6": t_bot_44, "P7": b_top_44, "P8": b_bot_44,
    "P9": r44, "P10": r44, "P11": r44, "P12": r44,
    "P13": r44, "P14": r44, "P15": r44, "P16": r44,
}
add_measure(parts, 44, "44", v_map_44, time_sig=(3, 4))

# =========================================================================
# m45 (3/4 = 11520) - Choir 1 TB alone, all others rest
# =========================================================================
r45 = [make_rest_note(11520, is_measure_rest=True)]
t_top_45, t_bot_45 = demix_measure_notes(get_raw_notes("P3", 45))
b_top_45, b_bot_45 = demix_measure_notes(get_raw_notes("P4", 45))

v_map_45 = {
    "P1": r45, "P2": r45, "P3": r45, "P4": r45,
    "P5": t_top_45, "P6": t_bot_45, "P7": b_top_45, "P8": b_bot_45,
    "P9": r45, "P10": r45, "P11": r45, "P12": r45,
    "P13": r45, "P14": r45, "P15": r45, "P16": r45,
}
add_measure(parts, 45, "45", v_map_45, time_sig=None)

print("Section 4 complete.")

out_path = Path("output/test_clamavi_mm0_45.xml")
ET.indent(root, space="  ")
tree_out = ET.ElementTree(root)
tree_out.write(out_path, encoding="utf-8", xml_declaration=True)
print(f"Written test score to {out_path}")
