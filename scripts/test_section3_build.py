import xml.etree.ElementTree as ET
from pathlib import Path
from scripts.assemble_clamavi import (
    add_measure,
    clean_standard_note,
    demix_measure_notes,
    make_rest_note,
    make_pitch_note,
)
import scripts.assemble_sections_1_2 as s12

tree = ET.parse('/Users/wattd/Downloads/Clamavi de tribulatione mea 12pp - 2021-06-23 b.xml')
root_raw = tree.getroot()
parts_raw = {p.attrib.get("id"): p for p in root_raw.findall("part")}

def get_raw_notes(pid, m_idx):
    m = parts_raw[pid].findall("measure")[m_idx]
    return m.findall("note")

parts = s12.parts
root = s12.root

print("Assembling Section 3 (mm. 29-36)...")

# m29 (3/4 = 11520) - Choir 1 sings, Choir 2 rests
c1_s_top, c1_s_bot = demix_measure_notes(get_raw_notes("P1", 29))
c1_t_top, c1_t_bot = demix_measure_notes(get_raw_notes("P2", 29))
r29 = [make_rest_note(11520, is_measure_rest=True)]
v_map_29 = {
    "P1": c1_s_top, "P2": c1_s_top, "P3": c1_s_bot, "P4": c1_s_bot,
    "P5": c1_t_top, "P6": c1_t_top, "P7": c1_t_bot, "P8": c1_t_bot,
    "P9": r29, "P10": r29, "P11": r29, "P12": r29,
    "P13": r29, "P14": r29, "P15": r29, "P16": r29,
}
add_measure(parts, 29, "29", v_map_29, time_sig=(3, 4))

# m30 (3/4 = 11520) - Choir 1 rests, Choir 2 sings (from P5, P6)
r30 = [make_rest_note(11520, is_measure_rest=True)]
c2_s_top, c2_s_bot = demix_measure_notes(get_raw_notes("P5", 30))
c2_t_top, c2_t_bot = demix_measure_notes(get_raw_notes("P6", 30))
v_map_30 = {
    "P1": r30, "P2": r30, "P3": r30, "P4": r30,
    "P5": r30, "P6": r30, "P7": r30, "P8": r30,
    "P9": c2_s_top, "P10": c2_s_top, "P11": c2_s_bot, "P12": c2_s_bot,
    "P13": c2_t_top, "P14": c2_t_top, "P15": c2_t_bot, "P16": c2_t_bot,
}
add_measure(parts, 30, "30", v_map_30, time_sig=None)

# m31 (3/4 = 11520) - Choir 1 enters "Cla-ma-vi", Choir 2 continues
c1_s_top, c1_s_bot = demix_measure_notes(get_raw_notes("P1", 31))
c1_t_top, c1_t_bot = demix_measure_notes(get_raw_notes("P2", 31))
c2_s_notes = get_raw_notes("P5", 31)
# Fix trailing rest in P5 from 1920 to 1280 (triplet eighth rest)
for n in c2_s_notes:
    if n.find("rest") is not None:
        dur = n.find("duration")
        if dur is not None and dur.text == "1920":
            dur.text = "1280"
c2_s_top, c2_s_bot = demix_measure_notes(c2_s_notes)
c2_t_top, c2_t_bot = demix_measure_notes(get_raw_notes("P6", 31))
v_map_31 = {
    "P1": c1_s_top, "P2": c1_s_top, "P3": c1_s_bot, "P4": c1_s_bot,
    "P5": c1_t_top, "P6": c1_t_top, "P7": c1_t_bot, "P8": c1_t_bot,
    "P9": c2_s_top, "P10": c2_s_top, "P11": c2_s_bot, "P12": c2_s_bot,
    "P13": c2_t_top, "P14": c2_t_top, "P15": c2_t_bot, "P16": c2_t_bot,
}
add_measure(parts, 31, "31", v_map_31, time_sig=None)

# m32 (3/4 = 11520)
c1_s_top, c1_s_bot = demix_measure_notes(get_raw_notes("P1", 32))
c1_t_top, c1_t_bot = demix_measure_notes(get_raw_notes("P2", 32))
c2_s_top, c2_s_bot = demix_measure_notes(get_raw_notes("P5", 32))
c2_t_top, c2_t_bot = demix_measure_notes(get_raw_notes("P6", 32))
v_map_32 = {
    "P1": c1_s_top, "P2": c1_s_top, "P3": c1_s_bot, "P4": c1_s_bot,
    "P5": c1_t_top, "P6": c1_t_top, "P7": c1_t_bot, "P8": c1_t_bot,
    "P9": c2_s_top, "P10": c2_s_top, "P11": c2_s_bot, "P12": c2_s_bot,
    "P13": c2_t_top, "P14": c2_t_top, "P15": c2_t_bot, "P16": c2_t_bot,
}
add_measure(parts, 32, "32", v_map_32, time_sig=None)

# m33 (4/4 = 15360)
c1_s_top, c1_s_bot = demix_measure_notes(get_raw_notes("P1", 33))
c1_t_top, c1_t_bot = demix_measure_notes(get_raw_notes("P2", 33))
c2_s_top, c2_s_bot = demix_measure_notes(get_raw_notes("P5", 33))
c2_t_top, c2_t_bot = demix_measure_notes(get_raw_notes("P6", 33))
v_map_33 = {
    "P1": c1_s_top, "P2": c1_s_top, "P3": c1_s_bot, "P4": c1_s_bot,
    "P5": c1_t_top, "P6": c1_t_top, "P7": c1_t_bot, "P8": c1_t_bot,
    "P9": c2_s_top, "P10": c2_s_top, "P11": c2_s_bot, "P12": c2_s_bot,
    "P13": c2_t_top, "P14": c2_t_top, "P15": c2_t_bot, "P16": c2_t_bot,
}
add_measure(parts, 33, "33", v_map_33, time_sig=(4, 4))

# m34 (4/4 = 15360)
c1_s_top, c1_s_bot = demix_measure_notes(get_raw_notes("P1", 34))
c1_t_top, c1_t_bot = demix_measure_notes(get_raw_notes("P2", 34))
c2_s_top, c2_s_bot = demix_measure_notes(get_raw_notes("P5", 34))
c2_t_top, c2_t_bot = demix_measure_notes(get_raw_notes("P6", 34))
v_map_34 = {
    "P1": c1_s_top, "P2": c1_s_top, "P3": c1_s_bot, "P4": c1_s_bot,
    "P5": c1_t_top, "P6": c1_t_top, "P7": c1_t_bot, "P8": c1_t_bot,
    "P9": c2_s_top, "P10": c2_s_top, "P11": c2_s_bot, "P12": c2_s_bot,
    "P13": c2_t_top, "P14": c2_t_top, "P15": c2_t_bot, "P16": c2_t_bot,
}
add_measure(parts, 34, "34", v_map_34, time_sig=None)

# m35 (4/4 = 15360) - Choir 1 sings, Choir 2 rests
c1_s_top, c1_s_bot = demix_measure_notes(get_raw_notes("P1", 35))
c1_t_top, c1_t_bot = demix_measure_notes(get_raw_notes("P2", 35))
r35 = [make_rest_note(15360, is_measure_rest=True)]
v_map_35 = {
    "P1": c1_s_top, "P2": c1_s_top, "P3": c1_s_bot, "P4": c1_s_bot,
    "P5": c1_t_top, "P6": c1_t_top, "P7": c1_t_bot, "P8": c1_t_bot,
    "P9": r35, "P10": r35, "P11": r35, "P12": r35,
    "P13": r35, "P14": r35, "P15": r35, "P16": r35,
}
add_measure(parts, 35, "35", v_map_35, time_sig=None)

# m36 (4/4 = 15360) - Choir 1 held chords, Choir 2 Bass enters
# In raw XML, P1 m.36 has Soprano (notes 0,1: 3840+11520=15360) and Alto (notes 2,3,4: 7680+3840+3840=15360)
p1_notes = [clean_standard_note(n) for n in get_raw_notes("P1", 36)]
c1_s36 = p1_notes[0:2]
c1_a36 = p1_notes[2:5]

# Similarly, raw P2 m.36 has Tenor (notes 0,1) and Bass (notes 2,3,4)
p2_notes = [clean_standard_note(n) for n in get_raw_notes("P2", 36)]
c1_t36 = p2_notes[0:2]
c1_b36 = p2_notes[2:5]

r36 = [make_rest_note(15360, is_measure_rest=True)]

# Choir 2 Bass enters with octave divisi on "ma" and "vi"
c2_b1_36 = [
    make_rest_note(1920, "eighth"),
    make_pitch_note("C", 3, 1920, "eighth", alter=1, lyric_text="cla", lyric_syl="begin"),
    make_pitch_note("D", 4, 7680, "half", lyric_text="ma", lyric_syl="middle"),
    make_pitch_note("E", 4, 3840, "quarter", lyric_text="vi,", lyric_syl="end"),
]
c2_b2_36 = [
    make_rest_note(1920, "eighth"),
    make_pitch_note("C", 3, 1920, "eighth", alter=1, lyric_text="cla", lyric_syl="begin"),
    make_pitch_note("D", 3, 7680, "half", lyric_text="ma", lyric_syl="middle"),
    make_pitch_note("E", 3, 3840, "quarter", lyric_text="vi,", lyric_syl="end"),
]

v_map_36 = {
    "P1": c1_s36, "P2": c1_s36, "P3": c1_a36, "P4": c1_a36,
    "P5": c1_t36, "P6": c1_t36, "P7": c1_b36, "P8": c1_b36,
    "P9": r36, "P10": r36, "P11": r36, "P12": r36,
    "P13": r36, "P14": r36, "P15": c2_b1_36, "P16": c2_b2_36,
}
add_measure(parts, 36, "36", v_map_36, time_sig=None)

print("Section 3 complete.")

out_path = Path("output/test_clamavi_mm0_36.xml")
ET.indent(root, space="  ")
tree_out = ET.ElementTree(root)
tree_out.write(out_path, encoding="utf-8", xml_declaration=True)
print(f"Written test score to {out_path}")
