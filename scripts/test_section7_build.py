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
import scripts.test_section6_build as s6

parts = s6.parts
root = s6.root
tree_raw = ET.parse('/Users/wattd/Downloads/Clamavi de tribulatione mea 12pp - 2021-06-23 b.xml')
root_raw = tree_raw.getroot()
parts_raw = {p.attrib.get("id"): p for p in root_raw.findall("part")}

def get_raw_notes_voice(pid, m_idx, v="1"):
    m = parts_raw[pid].findall("measure")[m_idx]
    return [n for n in m.findall("note") if n.findtext("voice", "1") == str(v)]

def get_raw_notes(pid, m_idx):
    m = parts_raw[pid].findall("measure")[m_idx]
    return m.findall("note")

print("Assembling Section 7 (mm. 68-80)...")

# =========================================================================
# m68 (4/4 = 15360) - Choir 1 SSAA "an-gu-sti-a-re-tur in", others rest
# =========================================================================
r15360 = [make_rest_note(15360, is_measure_rest=True)]
c1_s1_68, c1_s2_68 = demix_measure_notes(get_raw_notes_voice("P1", 133, "1"))
c1_a1_68, c1_a2_68 = demix_measure_notes(get_raw_notes_voice("P1", 133, "2"))

v_map_68 = {
    "P1": c1_s1_68, "P2": c1_s2_68, "P3": c1_a1_68, "P4": c1_a2_68,
    "P5": r15360, "P6": r15360, "P7": r15360, "P8": r15360,
    "P9": r15360, "P10": r15360, "P11": r15360, "P12": r15360,
    "P13": r15360, "P14": r15360, "P15": r15360, "P16": r15360,
}
add_measure(parts, 68, "68", v_map_68, time_sig=(4, 4))

# =========================================================================
# m69 (4/4 = 15360) - Choir 1 SSAA "me", others rest
# =========================================================================
c1_s1_69, c1_s2_69 = demix_measure_notes(get_raw_notes_voice("P1", 134, "1"))
c1_a1_69, c1_a2_69 = demix_measure_notes(get_raw_notes_voice("P1", 134, "2"))

v_map_69 = {
    "P1": c1_s1_69, "P2": c1_s2_69, "P3": c1_a1_69, "P4": c1_a2_69,
    "P5": r15360, "P6": r15360, "P7": r15360, "P8": r15360,
    "P9": r15360, "P10": r15360, "P11": r15360, "P12": r15360,
    "P13": r15360, "P14": r15360, "P15": r15360, "P16": r15360,
}
add_measure(parts, 69, "69", v_map_69, time_sig=None)

# =========================================================================
# m70 (3/4 = 11520) - Choir 1 SSAA "a - ni - ma", others rest
# =========================================================================
r11520 = [make_rest_note(11520, is_measure_rest=True)]
c1_s1_70, c1_s2_70 = demix_measure_notes(get_raw_notes_voice("P1", 135, "1"))
c1_a1_70, c1_a2_70 = demix_measure_notes(get_raw_notes_voice("P1", 135, "2"))

v_map_70 = {
    "P1": c1_s1_70, "P2": c1_s2_70, "P3": c1_a1_70, "P4": c1_a2_70,
    "P5": r11520, "P6": r11520, "P7": r11520, "P8": r11520,
    "P9": r11520, "P10": r11520, "P11": r11520, "P12": r11520,
    "P13": r11520, "P14": r11520, "P15": r11520, "P16": r11520,
}
add_measure(parts, 70, "70", v_map_70, time_sig=(3, 4))

# =========================================================================
# m71 (4/4 = 15360) - Choir 1 resolves "me a,"; Choir 2 enters "cum an-gu-sti-a"
# =========================================================================
c1_s1_71, c1_s2_71 = demix_measure_notes(get_raw_notes_voice("P1", 136, "1"))
c1_a1_71, c1_a2_71 = demix_measure_notes(get_raw_notes_voice("P1", 136, "2"))
c2_s_71, c2_a_71 = demix_measure_notes(get_raw_notes_voice("P7", 136, "1"))
c2_t_71, c2_b_71 = demix_measure_notes(get_raw_notes_voice("P8", 136, "1"))

v_map_71 = {
    "P1": c1_s1_71, "P2": c1_s2_71, "P3": c1_a1_71, "P4": c1_a2_71,
    "P5": r15360, "P6": r15360, "P7": r15360, "P8": r15360,
    "P9": c2_s_71, "P10": c2_s_71, "P11": c2_a_71, "P12": c2_a_71,
    "P13": c2_t_71, "P14": c2_t_71, "P15": c2_b_71, "P16": c2_b_71,
}
add_measure(parts, 71, "71", v_map_71, time_sig=(4, 4))

# =========================================================================
# m72 (3/4 = 11520) - Choir 1 rests; Choir 2 "-re-tur in me"
# =========================================================================
c2_s_72, c2_a_72 = demix_measure_notes(get_raw_notes_voice("P7", 137, "1"))
c2_t_72, c2_b_72 = demix_measure_notes(get_raw_notes_voice("P8", 137, "1"))

v_map_72 = {
    "P1": r11520, "P2": r11520, "P3": r11520, "P4": r11520,
    "P5": r11520, "P6": r11520, "P7": r11520, "P8": r11520,
    "P9": c2_s_72, "P10": c2_s_72, "P11": c2_a_72, "P12": c2_a_72,
    "P13": c2_t_72, "P14": c2_t_72, "P15": c2_b_72, "P16": c2_b_72,
}
add_measure(parts, 72, "72", v_map_72, time_sig=(3, 4))

# =========================================================================
# m73 (4/4 = 15360) - Choir 2 "a-ni-ma me-a", Choir 1 TB enters "cum"
# =========================================================================
c1_t_73, c1_b_73 = demix_measure_notes(get_raw_notes_voice("P2", 138, "1"))
c2_s_73, c2_a_73 = demix_measure_notes(get_raw_notes_voice("P7", 138, "1"))
c2_t_73, c2_b_73 = demix_measure_notes(get_raw_notes_voice("P8", 138, "1"))

v_map_73 = {
    "P1": r15360, "P2": r15360, "P3": r15360, "P4": r15360,
    "P5": c1_t_73, "P6": c1_t_73, "P7": c1_b_73, "P8": c1_b_73,
    "P9": c2_s_73, "P10": c2_s_73, "P11": c2_a_73, "P12": c2_a_73,
    "P13": c2_t_73, "P14": c2_t_73, "P15": c2_b_73, "P16": c2_b_73,
}
add_measure(parts, 73, "73", v_map_73, time_sig=(4, 4))

# =========================================================================
# m74 (4/4 = 15360) - Choir 1 TB "an-gu-sti-a-re-tur in", others rest
# =========================================================================
c1_t_74, c1_b_74 = demix_measure_notes(get_raw_notes_voice("P2", 139, "1"))

v_map_74 = {
    "P1": r15360, "P2": r15360, "P3": r15360, "P4": r15360,
    "P5": c1_t_74, "P6": c1_t_74, "P7": c1_b_74, "P8": c1_b_74,
    "P9": r15360, "P10": r15360, "P11": r15360, "P12": r15360,
    "P13": r15360, "P14": r15360, "P15": r15360, "P16": r15360,
}
add_measure(parts, 74, "74", v_map_74, time_sig=None)

# =========================================================================
# m75 (4/4 = 15360) - Choir 1 TB "me a-ni-ma me", others rest
# =========================================================================
c1_t_75, c1_b_75 = demix_measure_notes(get_raw_notes_voice("P2", 140, "1"))

v_map_75 = {
    "P1": r15360, "P2": r15360, "P3": r15360, "P4": r15360,
    "P5": c1_t_75, "P6": c1_t_75, "P7": c1_b_75, "P8": c1_b_75,
    "P9": r15360, "P10": r15360, "P11": r15360, "P12": r15360,
    "P13": r15360, "P14": r15360, "P15": r15360, "P16": r15360,
}
add_measure(parts, 75, "75", v_map_75, time_sig=None)

# =========================================================================
# m76 (3/4 = 11520) - Choir 1 TB resolves "-a"; Choir 2 enters
# =========================================================================
c1_t_76, c1_b_76 = demix_measure_notes(get_raw_notes_voice("P2", 141, "1"))
c2_s_76 = [clean_standard_note(n) for n in get_raw_notes_voice("P7", 141, "1")]
c2_t_76, c2_b_76 = demix_measure_notes(get_raw_notes_voice("P8", 141, "1"))

v_map_76 = {
    "P1": r11520, "P2": r11520, "P3": r11520, "P4": r11520,
    "P5": c1_t_76, "P6": c1_t_76, "P7": c1_b_76, "P8": c1_b_76,
    "P9": c2_s_76, "P10": c2_s_76, "P11": r11520, "P12": r11520,
    "P13": c2_t_76, "P14": c2_t_76, "P15": c2_b_76, "P16": c2_b_76,
}
add_measure(parts, 76, "76", v_map_76, time_sig=(3, 4))

# =========================================================================
# m77 (3/4 = 11520) - Choir 1 rests; Choir 2 S + TB "me a-ni-ma me"
# =========================================================================
c2_s_77 = [clean_standard_note(n) for n in get_raw_notes_voice("P7", 142, "1")]
c2_t_77, c2_b_77 = demix_measure_notes(get_raw_notes_voice("P8", 142, "1"))

v_map_77 = {
    "P1": r11520, "P2": r11520, "P3": r11520, "P4": r11520,
    "P5": r11520, "P6": r11520, "P7": r11520, "P8": r11520,
    "P9": c2_s_77, "P10": c2_s_77, "P11": r11520, "P12": r11520,
    "P13": c2_t_77, "P14": c2_t_77, "P15": c2_b_77, "P16": c2_b_77,
}
add_measure(parts, 77, "77", v_map_77, time_sig=None)

# =========================================================================
# m78 (4/4 = 15360) - Choir 1 enters "Do-mi-ni re-cor-da-tus"; Choir 2 resolves "-a"
# =========================================================================
c1_s_78, c1_a_78 = demix_measure_notes(get_raw_notes_voice("P1", 143, "1"))
c1_t_78, c1_b_78 = demix_measure_notes(get_raw_notes_voice("P2", 143, "1"))
c2_s_78 = [clean_standard_note(n) for n in get_raw_notes_voice("P7", 143, "1")]
c2_t_78, c2_b_78 = demix_measure_notes(get_raw_notes_voice("P8", 143, "1"))

v_map_78 = {
    "P1": c1_s_78, "P2": c1_s_78, "P3": c1_a_78, "P4": c1_a_78,
    "P5": c1_t_78, "P6": c1_t_78, "P7": c1_b_78, "P8": c1_b_78,
    "P9": c2_s_78, "P10": c2_s_78, "P11": r15360, "P12": r15360,
    "P13": c2_t_78, "P14": c2_t_78, "P15": c2_b_78, "P16": c2_b_78,
}
add_measure(parts, 78, "78", v_map_78, time_sig=(4, 4))

# =========================================================================
# m79 (4/4 = 15360) - Choir 1 resolves "sum:"; Choir 2 enters "Do-mi-ni re-cor-da-tus"
# =========================================================================
c1_s_79, c1_a_79 = demix_measure_notes(get_raw_notes_voice("P1", 144, "1"))
c1_t_79, c1_b_79 = demix_measure_notes(get_raw_notes_voice("P2", 144, "1"))
c2_s_79, c2_a_79 = demix_measure_notes(get_raw_notes_voice("P7", 144, "1"))
c2_t_79, c2_b_79 = demix_measure_notes(get_raw_notes_voice("P8", 144, "1"))

v_map_79 = {
    "P1": c1_s_79, "P2": c1_s_79, "P3": c1_a_79, "P4": c1_a_79,
    "P5": c1_t_79, "P6": c1_t_79, "P7": c1_b_79, "P8": c1_b_79,
    "P9": c2_s_79, "P10": c2_s_79, "P11": c2_a_79, "P12": c2_a_79,
    "P13": c2_t_79, "P14": c2_t_79, "P15": c2_b_79, "P16": c2_b_79,
}
add_measure(parts, 79, "79", v_map_79, time_sig=None)

# =========================================================================
# m80 (4/4 = 15360) - Both choirs sing "ut ve-ni-"
# =========================================================================
c1_s_80, c1_a_80 = demix_measure_notes(get_raw_notes_voice("P1", 145, "1"))
c1_t_80, c1_b_80 = demix_measure_notes(get_raw_notes_voice("P2", 145, "1"))
c2_s_80, c2_a_80 = demix_measure_notes(get_raw_notes_voice("P7", 145, "1"))
c2_t_80, c2_b_80 = demix_measure_notes(get_raw_notes_voice("P8", 145, "1"))

v_map_80 = {
    "P1": c1_s_80, "P2": c1_s_80, "P3": c1_a_80, "P4": c1_a_80,
    "P5": c1_t_80, "P6": c1_t_80, "P7": c1_b_80, "P8": c1_b_80,
    "P9": c2_s_80, "P10": c2_s_80, "P11": c2_a_80, "P12": c2_a_80,
    "P13": c2_t_80, "P14": c2_t_80, "P15": c2_b_80, "P16": c2_b_80,
}
add_measure(parts, 80, "80", v_map_80, time_sig=None)

print("Section 7 complete.")

out_path = Path("output/test_clamavi_mm0_80.xml")
ET.indent(root, space="  ")
tree_out = ET.ElementTree(root)
tree_out.write(out_path, encoding="utf-8", xml_declaration=True)
print(f"Written test score to {out_path}")
