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
import scripts.test_section9_build as s9

parts = s9.parts
root = s9.root
tree_raw = ET.parse('/Users/wattd/Downloads/Clamavi de tribulatione mea 12pp - 2021-06-23 b.xml')
root_raw = tree_raw.getroot()
parts_raw = {p.attrib.get("id"): p for p in root_raw.findall("part")}

def get_raw_notes_voice(pid, m_idx, v="1"):
    m = parts_raw[pid].findall("measure")[m_idx]
    return [n for n in m.findall("note") if n.findtext("voice", "1") == str(v)]

def get_raw_notes(pid, m_idx):
    m = parts_raw[pid].findall("measure")[m_idx]
    return m.findall("note")

print("Assembling Section 10 (mm. 103-110)...")

r15360 = [make_rest_note(15360, is_measure_rest=True)]
r11520 = [make_rest_note(11520, is_measure_rest=True)]
r7680  = [make_rest_note(7680, is_measure_rest=True)]

# =========================================================================
# m103 (4/4 = 15360) - printed 102
# Choir 1 rests
# Choir 2 SSAA + TB: "te o-ra-ti-o,"
# =========================================================================
c2_s_103, c2_a_103 = demix_measure_notes(get_raw_notes_voice("P7", 168, "1"))
c2_t_103, c2_b_103 = demix_measure_notes(get_raw_notes_voice("P7", 168, "5"))

v_map_103 = {
    "P1": r15360, "P2": r15360, "P3": r15360, "P4": r15360,
    "P5": r15360, "P6": r15360, "P7": r15360, "P8": r15360,
    "P9": c2_s_103, "P10": c2_s_103, "P11": c2_a_103, "P12": c2_a_103,
    "P13": c2_t_103, "P14": c2_t_103, "P15": c2_b_103, "P16": c2_b_103,
}
add_measure(parts, 103, "103", v_map_103, time_sig=(4, 4))

# =========================================================================
# m104 (4/4 = 15360) - printed 103
# Choir 1 SSAA + TB: "o-ra-ti-o me - a"
# Choir 2 enters on beat 4.2 "ut ve -"
# =========================================================================
c1_s_104, c1_a_104 = demix_measure_notes(get_raw_notes_voice("P1", 169, "1"))
c1_t_104, c1_b_104 = demix_measure_notes(get_raw_notes_voice("P2", 169, "1"))
c2_s_104 = [clean_standard_note(n) for n in get_raw_notes_voice("P7", 169, "2")]
# Choir 2 TB also rests + enters on beat 4.2 with F#3
c2_tb_104 = [
    make_rest_note(7680),
    make_rest_note(3840),
    make_rest_note(1920),
    make_pitch_note("F", 3, 1920, "eighth", alter=1, lyric_text="ut"),
]

v_map_104 = {
    "P1": c1_s_104, "P2": c1_s_104, "P3": c1_a_104, "P4": c1_a_104,
    "P5": c1_t_104, "P6": c1_t_104, "P7": c1_b_104, "P8": c1_b_104,
    "P9": c2_s_104, "P10": c2_s_104, "P11": r15360, "P12": r15360,
    "P13": c2_tb_104, "P14": c2_tb_104, "P15": c2_tb_104, "P16": c2_tb_104,
}
add_measure(parts, 104, "104", v_map_104, time_sig=None)

# =========================================================================
# m105 (4/4 = 15360) - printed 104
# Choir 1 rests
# Choir 2 SSAA + TB: runs "- ve - - - - ni-at"
# =========================================================================
c2_s_105, c2_a_105 = demix_measure_notes(get_raw_notes_voice("P7", 170, "1"))
c2_t_105, c2_b_105 = demix_measure_notes(get_raw_notes_voice("P7", 170, "5"))

v_map_105 = {
    "P1": r15360, "P2": r15360, "P3": r15360, "P4": r15360,
    "P5": r15360, "P6": r15360, "P7": r15360, "P8": r15360,
    "P9": c2_s_105, "P10": c2_s_105, "P11": c2_a_105, "P12": c2_a_105,
    "P13": c2_t_105, "P14": c2_t_105, "P15": c2_b_105, "P16": c2_b_105,
}
add_measure(parts, 105, "105", v_map_105, time_sig=None)

# =========================================================================
# m106 (4/4 = 15360) - printed 105
# Choir 1 SSAA + TB: rests, enters on beat 4.2 "ad _"
# Choir 2 SSAA + TB: continues run, resolves "-ni-at" on beat 4
# =========================================================================
c1_s_106 = [clean_standard_note(n) for n in get_raw_notes_voice("P1", 171, "1")]
c1_tb_106 = [clean_standard_note(n) for n in get_raw_notes_voice("P2", 171, "1")]
c2_s_106, c2_a_106 = demix_measure_notes(get_raw_notes_voice("P7", 171, "1"))
c2_t_106, c2_b_106 = demix_measure_notes(get_raw_notes_voice("P7", 171, "5"))

v_map_106 = {
    "P1": c1_s_106, "P2": c1_s_106, "P3": r15360, "P4": r15360,
    "P5": c1_tb_106, "P6": c1_tb_106, "P7": c1_tb_106, "P8": c1_tb_106,
    "P9": c2_s_106, "P10": c2_s_106, "P11": c2_a_106, "P12": c2_a_106,
    "P13": c2_t_106, "P14": c2_t_106, "P15": c2_b_106, "P16": c2_b_106,
}
add_measure(parts, 106, "106", v_map_106, time_sig=None)

# =========================================================================
# m107 (3/4 = 11520) - printed 106
# Time sig 3/4
# Choir 1 SSAA + TB: "te ... o"
# Choir 2 SSAA + TB: "ad te"
# =========================================================================
c1_s_107, c1_a_107 = demix_measure_notes(get_raw_notes_voice("P1", 172, "1"))
c1_t_107, c1_b_107 = demix_measure_notes(get_raw_notes_voice("P2", 172, "1"))
c2_s_107, c2_a_107 = demix_measure_notes(get_raw_notes_voice("P7", 172, "1"))
c2_t_107, c2_b_107 = demix_measure_notes(get_raw_notes_voice("P7", 172, "5"))

v_map_107 = {
    "P1": c1_s_107, "P2": c1_s_107, "P3": c1_a_107, "P4": c1_a_107,
    "P5": c1_t_107, "P6": c1_t_107, "P7": c1_b_107, "P8": c1_b_107,
    "P9": c2_s_107, "P10": c2_s_107, "P11": c2_a_107, "P12": c2_a_107,
    "P13": c2_t_107, "P14": c2_t_107, "P15": c2_b_107, "P16": c2_b_107,
}
add_measure(parts, 107, "107", v_map_107, time_sig=(3, 4))

# =========================================================================
# m108 (2/4 = 7680) - printed 107
# Time sig 2/4
# Choir 1 SSAA + TB: "ra - ti - o"
# Choir 2 SSAA + TB: "o - ra - ti - o"
# =========================================================================
c1_s_108, c1_a_108 = demix_measure_notes(get_raw_notes_voice("P1", 173, "1"))
c1_t_108, c1_b_108 = demix_measure_notes(get_raw_notes_voice("P2", 173, "1"))
c2_s_108, c2_a_108 = demix_measure_notes(get_raw_notes_voice("P7", 173, "1"))
c2_t_108, c2_b_108 = demix_measure_notes(get_raw_notes_voice("P7", 173, "5"))

v_map_108 = {
    "P1": c1_s_108, "P2": c1_s_108, "P3": c1_a_108, "P4": c1_a_108,
    "P5": c1_t_108, "P6": c1_t_108, "P7": c1_b_108, "P8": c1_b_108,
    "P9": c2_s_108, "P10": c2_s_108, "P11": c2_a_108, "P12": c2_a_108,
    "P13": c2_t_108, "P14": c2_t_108, "P15": c2_b_108, "P16": c2_b_108,
}
add_measure(parts, 108, "108", v_map_108, time_sig=(2, 4))

# =========================================================================
# m109 (4/4 = 15360) - printed 108
# Time sig 4/4
# Choir 1 SSAA: S "me - a", A "me - a"
# Choir 1 TB: "me - a"
# Choir 2 SSAA + TB: "me - - a"
# =========================================================================
c1_s_109 = [clean_standard_note(n) for n in get_raw_notes_voice("P1", 174, "1")]
c1_a_109 = [clean_standard_note(n) for n in get_raw_notes_voice("P1", 174, "2")]
c1_t_109, c1_b_109 = demix_measure_notes(get_raw_notes_voice("P2", 174, "1"))
c2_s_109 = [clean_standard_note(n) for n in get_raw_notes_voice("P7", 174, "1")]
c2_a_109 = [clean_standard_note(n) for n in get_raw_notes_voice("P7", 174, "2")]
c2_t_109, c2_b_109 = demix_measure_notes(get_raw_notes_voice("P7", 174, "5"))

v_map_109 = {
    "P1": c1_s_109, "P2": c1_s_109, "P3": c1_a_109, "P4": c1_a_109,
    "P5": c1_t_109, "P6": c1_t_109, "P7": c1_b_109, "P8": c1_b_109,
    "P9": c2_s_109, "P10": c2_s_109, "P11": c2_a_109, "P12": c2_a_109,
    "P13": c2_t_109, "P14": c2_t_109, "P15": c2_b_109, "P16": c2_b_109,
}
add_measure(parts, 109, "109", v_map_109, time_sig=(4, 4))

# =========================================================================
# m110 (4/4 = 15360) - printed 109
# Choir 1 SSAA + TB: "ad tem-plum sanc-tum."
# Choir 2 SSAA + TB: resolves "a", enters "sanc-tum."
# =========================================================================
c1_s_110 = [clean_standard_note(n) for n in get_raw_notes_voice("P1", 175, "1")]
c1_a_110 = [clean_standard_note(n) for n in get_raw_notes_voice("P1", 175, "2")]
c1_t_110, c1_b_110 = demix_measure_notes(get_raw_notes_voice("P2", 175, "1"))
c2_s_110 = [clean_standard_note(n) for n in get_raw_notes_voice("P7", 175, "1")]
c2_tb_110 = [clean_standard_note(n) for n in get_raw_notes_voice("P7", 175, "5")]

v_map_110 = {
    "P1": c1_s_110, "P2": c1_s_110, "P3": c1_a_110, "P4": c1_a_110,
    "P5": c1_t_110, "P6": c1_t_110, "P7": c1_b_110, "P8": c1_b_110,
    "P9": c2_s_110, "P10": c2_s_110, "P11": r15360, "P12": r15360,
    "P13": c2_tb_110, "P14": c2_tb_110, "P15": c2_tb_110, "P16": c2_tb_110,
}
add_measure(parts, 110, "110", v_map_110, time_sig=None)

print("Section 10 complete.")

out_path = Path("output/test_clamavi_mm0_110.xml")
ET.indent(root, space="  ")
tree_out = ET.ElementTree(root)
tree_out.write(out_path, encoding="utf-8", xml_declaration=True)
print(f"Written test score to {out_path}")
