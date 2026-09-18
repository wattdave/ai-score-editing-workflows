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
import scripts.test_section8_build as s8

parts = s8.parts
root = s8.root
tree_raw = ET.parse('/Users/wattd/Downloads/Clamavi de tribulatione mea 12pp - 2021-06-23 b.xml')
root_raw = tree_raw.getroot()
parts_raw = {p.attrib.get("id"): p for p in root_raw.findall("part")}

def get_raw_notes_voice(pid, m_idx, v="1"):
    m = parts_raw[pid].findall("measure")[m_idx]
    return [n for n in m.findall("note") if n.findtext("voice", "1") == str(v)]

def get_raw_notes(pid, m_idx):
    m = parts_raw[pid].findall("measure")[m_idx]
    return m.findall("note")

print("Assembling Section 9 (mm. 92-102)...")

r15360 = [make_rest_note(15360, is_measure_rest=True)]
r11520 = [make_rest_note(11520, is_measure_rest=True)]

# =========================================================================
# m92 (3/4 = 11520) - printed 91
# Choir 1 SSAA + TB: triplets "ve-ni-at ad te o-ra-ti-o"
# Choir 2 rests
# =========================================================================
c1_s_92, c1_a_92 = demix_measure_notes(get_raw_notes_voice("P1", 157, "1"))
c1_t_92, c1_b_92 = demix_measure_notes(get_raw_notes_voice("P2", 157, "1"))

v_map_92 = {
    "P1": c1_s_92, "P2": c1_s_92, "P3": c1_a_92, "P4": c1_a_92,
    "P5": c1_t_92, "P6": c1_t_92, "P7": c1_b_92, "P8": c1_b_92,
    "P9": r11520, "P10": r11520, "P11": r11520, "P12": r11520,
    "P13": r11520, "P14": r11520, "P15": r11520, "P16": r11520,
}
add_measure(parts, 92, "92", v_map_92, time_sig=(3, 4))

# =========================================================================
# m93 (3/4 = 11520) - printed 92
# Choir 1 SSAA + TB: triplets "me - - - - a"
# Choir 2 rests
# =========================================================================
c1_s_93, c1_a_93 = demix_measure_notes(get_raw_notes_voice("P1", 158, "1"))
c1_t_93, c1_b_93 = demix_measure_notes(get_raw_notes_voice("P2", 158, "1"))

v_map_93 = {
    "P1": c1_s_93, "P2": c1_s_93, "P3": c1_a_93, "P4": c1_a_93,
    "P5": c1_t_93, "P6": c1_t_93, "P7": c1_b_93, "P8": c1_b_93,
    "P9": r11520, "P10": r11520, "P11": r11520, "P12": r11520,
    "P13": r11520, "P14": r11520, "P15": r11520, "P16": r11520,
}
add_measure(parts, 93, "93", v_map_93, time_sig=None)

# =========================================================================
# m94 (4/4 = 15360) - printed 93
# Choir 1 SSAA + TB: resolves "a" on beat 1 then rests
# Choir 2 SSAA + TB: enters "ad tem-plum san-ctum"
# =========================================================================
c1_s_94, c1_a_94 = demix_measure_notes(get_raw_notes_voice("P1", 159, "1"))
c1_t_94, c1_b_94 = demix_measure_notes(get_raw_notes_voice("P2", 159, "1"))
c2_s_94, c2_a_94 = demix_measure_notes(get_raw_notes_voice("P5", 159, "1"))
c2_t_94, c2_b_94 = demix_measure_notes(get_raw_notes_voice("P5", 159, "5"))

v_map_94 = {
    "P1": c1_s_94, "P2": c1_s_94, "P3": c1_a_94, "P4": c1_a_94,
    "P5": c1_t_94, "P6": c1_t_94, "P7": c1_b_94, "P8": c1_b_94,
    "P9": c2_s_94, "P10": c2_s_94, "P11": c2_a_94, "P12": c2_a_94,
    "P13": c2_t_94, "P14": c2_t_94, "P15": c2_b_94, "P16": c2_b_94,
}
add_measure(parts, 94, "94", v_map_94, time_sig=(4, 4))

# =========================================================================
# m95 (4/4 = 15360) - printed 94
# Both Choirs sing: "ad tem-plum / tu-um, ad tem-plum"
# =========================================================================
c1_s_95, c1_a_95 = demix_measure_notes(get_raw_notes_voice("P1", 160, "1"))
c1_t_95, c1_b_95 = demix_measure_notes(get_raw_notes_voice("P2", 160, "1"))
c2_s_95, c2_a_95 = demix_measure_notes(get_raw_notes_voice("P5", 160, "1"))
c2_t_95, c2_b_95 = demix_measure_notes(get_raw_notes_voice("P5", 160, "5"))

v_map_95 = {
    "P1": c1_s_95, "P2": c1_s_95, "P3": c1_a_95, "P4": c1_a_95,
    "P5": c1_t_95, "P6": c1_t_95, "P7": c1_b_95, "P8": c1_b_95,
    "P9": c2_s_95, "P10": c2_s_95, "P11": c2_a_95, "P12": c2_a_95,
    "P13": c2_t_95, "P14": c2_t_95, "P15": c2_b_95, "P16": c2_b_95,
}
add_measure(parts, 95, "95", v_map_95, time_sig=None)

# =========================================================================
# m96 (4/4 = 15360) - printed 95
# Both Choirs sing: "san-ctum tu-um,"
# =========================================================================
c1_s_96, c1_a_96 = demix_measure_notes(get_raw_notes_voice("P1", 161, "1"))
c1_t_96, c1_b_96 = demix_measure_notes(get_raw_notes_voice("P2", 161, "1"))
c2_s_96, c2_a_96 = demix_measure_notes(get_raw_notes_voice("P5", 161, "1"))
c2_t_96, c2_b_96 = demix_measure_notes(get_raw_notes_voice("P5", 161, "5"))

v_map_96 = {
    "P1": c1_s_96, "P2": c1_s_96, "P3": c1_a_96, "P4": c1_a_96,
    "P5": c1_t_96, "P6": c1_t_96, "P7": c1_b_96, "P8": c1_b_96,
    "P9": c2_s_96, "P10": c2_s_96, "P11": c2_a_96, "P12": c2_a_96,
    "P13": c2_t_96, "P14": c2_t_96, "P15": c2_b_96, "P16": c2_b_96,
}
add_measure(parts, 96, "96", v_map_96, time_sig=None)

# =========================================================================
# m97 (3/4 = 11520) - printed 96
# Choir 1 SSAA enters "ut ve-ni"
# Choir 1 TB rests
# Choir 2 SSAA rests
# Choir 2 TB: "ve-ni-at"
# =========================================================================
c1_s_97, c1_a_97 = demix_measure_notes(get_raw_notes_voice("P1", 162, "1"))
c2_t_97, c2_b_97 = demix_measure_notes(get_raw_notes_voice("P5", 162, "5"))

v_map_97 = {
    "P1": c1_s_97, "P2": c1_s_97, "P3": c1_a_97, "P4": c1_a_97,
    "P5": r11520, "P6": r11520, "P7": r11520, "P8": r11520,
    "P9": r11520, "P10": r11520, "P11": r11520, "P12": r11520,
    "P13": c2_t_97, "P14": c2_t_97, "P15": c2_b_97, "P16": c2_b_97,
}
add_measure(parts, 97, "97", v_map_97, time_sig=(3, 4))

# =========================================================================
# m98 (4/4 = 15360) - printed 97
# Choir 1 SSAA + TB: "at ... ad tem-plum"
# Choir 2 SSAA + TB: "ad tem-plum"
# =========================================================================
c1_s_98, c1_a_98 = demix_measure_notes(get_raw_notes_voice("P1", 163, "1"))
c1_t_98, c1_b_98 = demix_measure_notes(get_raw_notes_voice("P2", 163, "1"))
c2_s_98, c2_a_98 = demix_measure_notes(get_raw_notes_voice("P5", 163, "1"))
c2_t_98, c2_b_98 = demix_measure_notes(get_raw_notes_voice("P5", 163, "5"))

v_map_98 = {
    "P1": c1_s_98, "P2": c1_s_98, "P3": c1_a_98, "P4": c1_a_98,
    "P5": c1_t_98, "P6": c1_t_98, "P7": c1_b_98, "P8": c1_b_98,
    "P9": c2_s_98, "P10": c2_s_98, "P11": c2_a_98, "P12": c2_a_98,
    "P13": c2_t_98, "P14": c2_t_98, "P15": c2_b_98, "P16": c2_b_98,
}
add_measure(parts, 98, "98", v_map_98, time_sig=(4, 4))

# =========================================================================
# m99 (4/4 = 15360) - printed 98
# Choir 1 SSAA + TB: "sanc-tum tu-um / ut ve-ni-"
# Choir 2 SSAA + TB: "sanc-tum tu-um"
# =========================================================================
c1_s_99, c1_a_99 = demix_measure_notes(get_raw_notes_voice("P1", 164, "1"))
c1_t_99, c1_b_99 = demix_measure_notes(get_raw_notes_voice("P2", 164, "1"))
c2_s_99, c2_a_99 = demix_measure_notes(get_raw_notes_voice("P5", 164, "1"))
c2_t_99, c2_b_99 = demix_measure_notes(get_raw_notes_voice("P5", 164, "5"))

v_map_99 = {
    "P1": c1_s_99, "P2": c1_s_99, "P3": c1_a_99, "P4": c1_a_99,
    "P5": c1_t_99, "P6": c1_t_99, "P7": c1_b_99, "P8": c1_b_99,
    "P9": c2_s_99, "P10": c2_s_99, "P11": c2_a_99, "P12": c2_a_99,
    "P13": c2_t_99, "P14": c2_t_99, "P15": c2_b_99, "P16": c2_b_99,
}
add_measure(parts, 99, "99", v_map_99, time_sig=None)

# =========================================================================
# m100 (3/4 = 11520) - printed 99
# Choir 1 SSAA: S "o-ra-", A "at ad te o-ra"
# Choir 1 TB: "at ad te o-ra"
# Choir 2 rests
# =========================================================================
c1_s_100 = [clean_standard_note(n) for n in get_raw_notes_voice("P1", 165, "1")]
c1_a1_100, c1_a2_100 = demix_measure_notes(get_raw_notes_voice("P1", 165, "2"))
c1_t_100, c1_b_100   = demix_measure_notes(get_raw_notes_voice("P2", 165, "1"))

v_map_100 = {
    "P1": c1_s_100, "P2": c1_s_100, "P3": c1_a1_100, "P4": c1_a2_100,
    "P5": c1_t_100, "P6": c1_t_100, "P7": c1_b_100, "P8": c1_b_100,
    "P9": r11520, "P10": r11520, "P11": r11520, "P12": r11520,
    "P13": r11520, "P14": r11520, "P15": r11520, "P16": r11520,
}
add_measure(parts, 100, "100", v_map_100, time_sig=(3, 4))

# =========================================================================
# m101 (4/4 = 15360) - printed 100
# Choir 1 SSAA + TB: "ti - o me - a"
# Choir 2 rests
# =========================================================================
c1_s_101 = [clean_standard_note(n) for n in get_raw_notes_voice("P1", 166, "1")]
c1_a1_101, c1_a2_101 = demix_measure_notes(get_raw_notes_voice("P1", 166, "2"))
c1_t_101, c1_b_101   = demix_measure_notes(get_raw_notes_voice("P2", 166, "1"))

v_map_101 = {
    "P1": c1_s_101, "P2": c1_s_101, "P3": c1_a1_101, "P4": c1_a2_101,
    "P5": c1_t_101, "P6": c1_t_101, "P7": c1_b_101, "P8": c1_b_101,
    "P9": r15360, "P10": r15360, "P11": r15360, "P12": r15360,
    "P13": r15360, "P14": r15360, "P15": r15360, "P16": r15360,
}
add_measure(parts, 101, "101", v_map_101, time_sig=(4, 4))

# =========================================================================
# m102 (4/4 = 15360) - printed 101
# Choir 1 SSAA + TB: resolves "- a" on beat 1 then rests
# Choir 2 SSAA + TB: enters "ut ve-ni-at ad"
# =========================================================================
c1_s_102, c1_a_102 = demix_measure_notes(get_raw_notes_voice("P1", 167, "2"))
c1_t_102, c1_b_102 = demix_measure_notes(get_raw_notes_voice("P2", 167, "1"))
c2_s_102 = [clean_standard_note(n) for n in get_raw_notes_voice("P5", 167, "1")]
c2_a_102 = [clean_standard_note(n) for n in get_raw_notes_voice("P5", 167, "2")]
c2_t_102, c2_b_102 = demix_measure_notes(get_raw_notes_voice("P5", 167, "5"))

v_map_102 = {
    "P1": c1_s_102, "P2": c1_s_102, "P3": c1_a_102, "P4": c1_a_102,
    "P5": c1_t_102, "P6": c1_t_102, "P7": c1_b_102, "P8": c1_b_102,
    "P9": c2_s_102, "P10": c2_s_102, "P11": c2_a_102, "P12": c2_a_102,
    "P13": c2_t_102, "P14": c2_t_102, "P15": c2_b_102, "P16": c2_b_102,
}
add_measure(parts, 102, "102", v_map_102, time_sig=None)

print("Section 9 complete.")

out_path = Path("output/test_clamavi_mm0_102.xml")
ET.indent(root, space="  ")
tree_out = ET.ElementTree(root)
tree_out.write(out_path, encoding="utf-8", xml_declaration=True)
print(f"Written test score to {out_path}")
