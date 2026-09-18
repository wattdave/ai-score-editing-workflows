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
import scripts.test_section7_build as s7

parts = s7.parts
root = s7.root
tree_raw = ET.parse('/Users/wattd/Downloads/Clamavi de tribulatione mea 12pp - 2021-06-23 b.xml')
root_raw = tree_raw.getroot()
parts_raw = {p.attrib.get("id"): p for p in root_raw.findall("part")}

def get_raw_notes_voice(pid, m_idx, v="1"):
    m = parts_raw[pid].findall("measure")[m_idx]
    return [n for n in m.findall("note") if n.findtext("voice", "1") == str(v)]

def get_raw_notes(pid, m_idx):
    m = parts_raw[pid].findall("measure")[m_idx]
    return m.findall("note")

print("Assembling Section 8 (mm. 81-91)...")

r15360 = [make_rest_note(15360, is_measure_rest=True)]
r11520 = [make_rest_note(11520, is_measure_rest=True)]
r7680  = [make_rest_note(7680, is_measure_rest=True)]

# =========================================================================
# m81 (4/4 = 15360) - printed 80
# Choir 1 SSAA: v1 S1/S2 tied G#5, v2 A1/A2 chord "at"
# Choir 1 TB: chord "at" then rest
# Choir 2 SSAA + TB: chord "at", then "ad te o-ra-ti-o me-a,"
# =========================================================================
# Fix Choir 1 S pitch from F5 to G#5
c1_s_81 = []
for n in get_raw_notes_voice("P1", 146, "1"):
    cn = clean_standard_note(n)
    p = cn.find("pitch")
    if p is not None:
        p.find("step").text = "G"
        alter = p.find("alter")
        if alter is None:
            alter = ET.SubElement(p, "alter")
        alter.text = "1"
        p.find("octave").text = "5"
    c1_s_81.append(cn)

c1_a1_81, c1_a2_81 = demix_measure_notes(get_raw_notes_voice("P1", 146, "2"))
c1_t_81, c1_b_81   = demix_measure_notes(get_raw_notes_voice("P2", 146, "1"))
c2_s_81, c2_a_81   = demix_measure_notes(get_raw_notes_voice("P7", 146, "1"))
c2_t_81, c2_b_81   = demix_measure_notes(get_raw_notes_voice("P8", 146, "1"))

v_map_81 = {
    "P1": c1_s_81, "P2": c1_s_81, "P3": c1_a1_81, "P4": c1_a2_81,
    "P5": c1_t_81, "P6": c1_t_81, "P7": c1_b_81, "P8": c1_b_81,
    "P9": c2_s_81, "P10": c2_s_81, "P11": c2_a_81, "P12": c2_a_81,
    "P13": c2_t_81, "P14": c2_t_81, "P15": c2_b_81, "P16": c2_b_81,
}
add_measure(parts, 81, "81", v_map_81, time_sig=None)

# =========================================================================
# m82 (4/4 = 15360) - printed 81
# Choir 1 SSAA: S melody "ad te o-ra-ti-o" (G#5 notes)
# Choir 1 TB rests
# Choir 2 SSAA + TB: "a, ... ad te o-ra-ti-o"
# =========================================================================
c1_s_82 = []
for n in get_raw_notes_voice("P1", 147, "1"):
    cn = clean_standard_note(n)
    p = cn.find("pitch")
    if p is not None:
        p.find("step").text = "G"
        alter = p.find("alter")
        if alter is None:
            alter = ET.SubElement(p, "alter")
        alter.text = "1"
        p.find("octave").text = "5"
    c1_s_82.append(cn)

c2_s_82, c2_a_82 = demix_measure_notes(get_raw_notes_voice("P7", 147, "1"))
c2_t_82, c2_b_82 = demix_measure_notes(get_raw_notes_voice("P8", 147, "1"))

v_map_82 = {
    "P1": c1_s_82, "P2": c1_s_82, "P3": r15360, "P4": r15360,
    "P5": r15360, "P6": r15360, "P7": r15360, "P8": r15360,
    "P9": c2_s_82, "P10": c2_s_82, "P11": c2_a_82, "P12": c2_a_82,
    "P13": c2_t_82, "P14": c2_t_82, "P15": c2_b_82, "P16": c2_b_82,
}
add_measure(parts, 82, "82", v_map_82, time_sig=None)

# =========================================================================
# m83 (4/4 = 15360) - printed 82
# Choir 1 SSAA: v1 S1/S2 "me ...", v2 A1/A2 "ad te o-ra-ti-"
# Choir 1 TB: "ad te o-ra-ti-o"
# Choir 2 SSAA + TB: "me - - a"
# =========================================================================
# Fix Choir 1 S1 pitch in m83: note 1 is G#5, note 2 is E5
c1_s_83_raw = get_raw_notes_voice("P1", 148, "1")
c1_s_83 = []
for idx_n, n in enumerate(c1_s_83_raw):
    cn = clean_standard_note(n)
    p = cn.find("pitch")
    if p is not None:
        if idx_n == 0:
            p.find("step").text = "G"
            alter = p.find("alter")
            if alter is None:
                alter = ET.SubElement(p, "alter")
            alter.text = "1"
            p.find("octave").text = "5"
        else:
            p.find("step").text = "E"
            alter = p.find("alter")
            if alter is not None:
                p.remove(alter)
            p.find("octave").text = "5"
    c1_s_83.append(cn)

c1_a1_83, c1_a2_83 = demix_measure_notes(get_raw_notes_voice("P1", 148, "2"))
c1_t_83, c1_b_83   = demix_measure_notes(get_raw_notes_voice("P2", 148, "2"))
c2_s_83, c2_a_83   = demix_measure_notes(get_raw_notes_voice("P7", 148, "1"))
c2_t_83, c2_b_83   = demix_measure_notes(get_raw_notes_voice("P8", 148, "1"))

v_map_83 = {
    "P1": c1_s_83, "P2": c1_s_83, "P3": c1_a1_83, "P4": c1_a2_83,
    "P5": c1_t_83, "P6": c1_t_83, "P7": c1_b_83, "P8": c1_b_83,
    "P9": c2_s_83, "P10": c2_s_83, "P11": c2_a_83, "P12": c2_a_83,
    "P13": c2_t_83, "P14": c2_t_83, "P15": c2_b_83, "P16": c2_b_83,
}
add_measure(parts, 83, "83", v_map_83, time_sig=None)

# =========================================================================
# m84 (4/4 = 15360) - printed 83
# Choir 1 SSAA + TB resolve "- o me - a"
# Choir 2 rests
# =========================================================================
c1_s_84 = [clean_standard_note(n) for n in get_raw_notes_voice("P1", 149, "1")]
c1_a_84 = [clean_standard_note(n) for n in get_raw_notes_voice("P1", 149, "2")]
c1_t_84 = [clean_standard_note(n) for n in get_raw_notes_voice("P2", 149, "1")]
c1_b_84 = [clean_standard_note(n) for n in get_raw_notes_voice("P2", 149, "2")]

v_map_84 = {
    "P1": c1_s_84, "P2": c1_s_84, "P3": c1_a_84, "P4": c1_a_84,
    "P5": c1_t_84, "P6": c1_t_84, "P7": c1_b_84, "P8": c1_b_84,
    "P9": r15360, "P10": r15360, "P11": r15360, "P12": r15360,
    "P13": r15360, "P14": r15360, "P15": r15360, "P16": r15360,
}
add_measure(parts, 84, "84", v_map_84, time_sig=None)

# =========================================================================
# m85 (4/4 = 15360) - printed 84
# Choir 1 SSAA + T rests; Bass sings "a" (d=1920) then rests
# Choir 2 SSAA + TB: "ad tem-plum san-ctum"
# =========================================================================
c1_b_85 = [clean_standard_note(n) for n in get_raw_notes_voice("P2", 150, "2")]
c2_s_85, c2_a_85 = demix_measure_notes(get_raw_notes_voice("P7", 150, "1"))
c2_t_85, c2_b_85 = demix_measure_notes(get_raw_notes_voice("P8", 150, "1"))

v_map_85 = {
    "P1": r15360, "P2": r15360, "P3": r15360, "P4": r15360,
    "P5": r15360, "P6": r15360, "P7": c1_b_85, "P8": c1_b_85,
    "P9": c2_s_85, "P10": c2_s_85, "P11": c2_a_85, "P12": c2_a_85,
    "P13": c2_t_85, "P14": c2_t_85, "P15": c2_b_85, "P16": c2_b_85,
}
add_measure(parts, 85, "85", v_map_85, time_sig=None)

# =========================================================================
# m86 (4/4 = 15360) - printed 85
# Choir 1 SSAA rests; Choir 1 TB enters "ut ve-ni-at ad te o-ra-ti-"
# Choir 2 SSAA + TB resolves "tu - um"
# =========================================================================
c1_t1_86, c1_t2_86 = demix_measure_notes(get_raw_notes_voice("P2", 151, "1"))
c1_b1_86, c1_b2_86 = demix_measure_notes(get_raw_notes_voice("P2", 151, "2"))
c2_s_86, c2_a_86   = demix_measure_notes(get_raw_notes_voice("P7", 151, "1"))
c2_t_86, c2_b_86   = demix_measure_notes(get_raw_notes_voice("P8", 151, "1"))

v_map_86 = {
    "P1": r15360, "P2": r15360, "P3": r15360, "P4": r15360,
    "P5": c1_t1_86, "P6": c1_t2_86, "P7": c1_b1_86, "P8": c1_b2_86,
    "P9": c2_s_86, "P10": c2_s_86, "P11": c2_a_86, "P12": c2_a_86,
    "P13": c2_t_86, "P14": c2_t_86, "P15": c2_b_86, "P16": c2_b_86,
}
add_measure(parts, 86, "86", v_map_86, time_sig=None)

# =========================================================================
# m87 (4/4 = 15360) - printed 86
# Choir 1 SSAA rests; Choir 1 TB resolves "-o me - a,"
# Choir 2 SSAA + TB: "ad tem-plum san-ctum tu-"
# =========================================================================
c1_t_87 = [clean_standard_note(n) for n in get_raw_notes_voice("P2", 152, "1")]
c1_b_87 = [clean_standard_note(n) for n in get_raw_notes_voice("P2", 152, "2")]
# Add missing beat 4 rest (dur=3840) to c1_b_87
c1_b_87.append(make_rest_note(3840))

c2_s_87, c2_a_87 = demix_measure_notes(get_raw_notes_voice("P7", 152, "1"))
c2_t_87, c2_b_87 = demix_measure_notes(get_raw_notes_voice("P8", 152, "1"))

v_map_87 = {
    "P1": r15360, "P2": r15360, "P3": r15360, "P4": r15360,
    "P5": c1_t_87, "P6": c1_t_87, "P7": c1_b_87, "P8": c1_b_87,
    "P9": c2_s_87, "P10": c2_s_87, "P11": c2_a_87, "P12": c2_a_87,
    "P13": c2_t_87, "P14": c2_t_87, "P15": c2_b_87, "P16": c2_b_87,
}
add_measure(parts, 87, "87", v_map_87, time_sig=None)

# =========================================================================
# m88 (4/4 = 15360) - printed 87
# Choir 1 SSAA enters "ut ve-ni-at ad te o-ra-ti-"
# Choir 1 TB enters "ut ve-ni-at ad te o-"
# Choir 2 SSAA + TB resolves "-um,"
# =========================================================================
# Construct Choir 1 S:
# beat 1: D#4 (1920) 'ut', E4 (1920)
# beat 2: triplet F#4 (1280), F#4 (1280), G#4 (1280)
# beat 3: triplet A4 (1280), A4 (1280), B4 (1280)
# beat 4: eighth C#5 (1920) 'ra', eighth D#5 (1920) 'ti'
c1_s_88 = [
    make_pitch_note("D", 4, 1920, "eighth", alter=1, lyric_text="ut"),
    make_pitch_note("E", 4, 1920, "eighth", alter=0),
    make_pitch_note("F", 4, 1280, "eighth", alter=1, lyric_text="ve"),
    make_pitch_note("F", 4, 1280, "eighth", alter=1, lyric_text="ni"),
    make_pitch_note("G", 4, 1280, "eighth", alter=1, lyric_text="at"),
    make_pitch_note("A", 4, 1280, "eighth", alter=0, lyric_text="ad"),
    make_pitch_note("A", 4, 1280, "eighth", alter=0, lyric_text="te"),
    make_pitch_note("B", 4, 1280, "eighth", alter=0, lyric_text="o"),
    make_pitch_note("C", 5, 1920, "eighth", alter=1, lyric_text="ra"),
    make_pitch_note("D", 5, 1920, "eighth", alter=1, lyric_text="ti"),
]

# Construct Choir 1 A:
# beat 1: quarter D#4 (3840) 'ut'
# beat 2: triplet C#4 (1280), C#4 (1280), D#4 (1280)
# beat 3: triplet E4 (1280), E4 (1280), F#4 (1280)
# beat 4: triplet G#4 (1280), A#4 (1280), B4 (1280)
c1_a_88 = [
    make_pitch_note("D", 4, 3840, "quarter", alter=1, lyric_text="ut"),
    make_pitch_note("C", 4, 1280, "eighth", alter=1, lyric_text="ve"),
    make_pitch_note("C", 4, 1280, "eighth", alter=1, lyric_text="ni"),
    make_pitch_note("D", 4, 1280, "eighth", alter=1, lyric_text="at"),
    make_pitch_note("E", 4, 1280, "eighth", alter=0, lyric_text="ad"),
    make_pitch_note("E", 4, 1280, "eighth", alter=0, lyric_text="te"),
    make_pitch_note("F", 4, 1280, "eighth", alter=1, lyric_text="o"),
    make_pitch_note("G", 4, 1280, "eighth", alter=1, lyric_text="ra"),
    make_pitch_note("A", 4, 1280, "eighth", alter=1, lyric_text="ti"),
    make_pitch_note("B", 4, 1280, "eighth", alter=0, lyric_text="o"),
]

c1_t_88, c1_b_88 = demix_measure_notes(get_raw_notes_voice("P2", 153, "1"))
c2_s_88, c2_a_88 = demix_measure_notes(get_raw_notes_voice("P7", 153, "1"))
c2_t_88, c2_b_88 = demix_measure_notes(get_raw_notes_voice("P8", 153, "1"))

v_map_88 = {
    "P1": c1_s_88, "P2": c1_s_88, "P3": c1_a_88, "P4": c1_a_88,
    "P5": c1_t_88, "P6": c1_t_88, "P7": c1_b_88, "P8": c1_b_88,
    "P9": c2_s_88, "P10": c2_s_88, "P11": c2_a_88, "P12": c2_a_88,
    "P13": c2_t_88, "P14": c2_t_88, "P15": c2_b_88, "P16": c2_b_88,
}
add_measure(parts, 88, "88", v_map_88, time_sig=None)

# =========================================================================
# m89 (2/4 = 7680) - printed 88
# Choir 1 SSAA: S "-o me -", A "me - - a"
# Choir 1 TB: "ra - ti - o me -"
# Choir 2 rests
# =========================================================================
c1_s_89 = [clean_standard_note(n) for n in get_raw_notes_voice("P1", 154, "1")]
c1_a_89 = [clean_standard_note(n) for n in get_raw_notes_voice("P1", 154, "2")]
c1_t_89, c1_b_89 = demix_measure_notes(get_raw_notes_voice("P2", 154, "1"))

v_map_89 = {
    "P1": c1_s_89, "P2": c1_s_89, "P3": c1_a_89, "P4": c1_a_89,
    "P5": c1_t_89, "P6": c1_t_89, "P7": c1_b_89, "P8": c1_b_89,
    "P9": r7680, "P10": r7680, "P11": r7680, "P12": r7680,
    "P13": r7680, "P14": r7680, "P15": r7680, "P16": r7680,
}
add_measure(parts, 89, "89", v_map_89, time_sig=(2, 4))

# =========================================================================
# m90 (4/4 = 15360) - printed 89
# Choir 1 SSAA + TB resolves "- a" on beat 1 then rests
# Choir 2 SSAA + TB: "ad tem-plum san-ctum tu - um,"
# =========================================================================
c1_s_90 = [
    make_pitch_note("C", 5, 1920, "eighth", alter=1, lyric_text="a"),
    make_rest_note(1920),
    make_rest_note(3840),
    make_rest_note(7680)
]
c1_a_90 = [
    make_pitch_note("E", 4, 1920, "eighth", alter=0, lyric_text="a"),
    make_rest_note(1920),
    make_rest_note(3840),
    make_rest_note(7680)
]
c1_t_90, c1_b_90 = demix_measure_notes(get_raw_notes_voice("P2", 155, "1"))
c2_s_90, c2_a_90 = demix_measure_notes(get_raw_notes_voice("P7", 155, "1"))
c2_t_90, c2_b_90 = demix_measure_notes(get_raw_notes_voice("P8", 155, "1"))

v_map_90 = {
    "P1": c1_s_90, "P2": c1_s_90, "P3": c1_a_90, "P4": c1_a_90,
    "P5": c1_t_90, "P6": c1_t_90, "P7": c1_b_90, "P8": c1_b_90,
    "P9": c2_s_90, "P10": c2_s_90, "P11": c2_a_90, "P12": c2_a_90,
    "P13": c2_t_90, "P14": c2_t_90, "P15": c2_b_90, "P16": c2_b_90,
}
add_measure(parts, 90, "90", v_map_90, time_sig=(4, 4))

# =========================================================================
# m91 (3/4 = 11520) - printed 90
# Choir 1 SSAA: rests, then Alto chord B3+E4 on last triplet eighth "ut"
# Choir 1 TB: rest, then "ut ve-ni-at,"
# Choir 2 SSAA + TB: resolves "-um," on beat 1 then rests
# =========================================================================
c1_s_91, c1_a_91 = demix_measure_notes(get_raw_notes_voice("P1", 156, "1"))
c1_t_91, c1_b_91 = demix_measure_notes(get_raw_notes_voice("P2", 156, "1"))
c2_s_91, c2_a_91 = demix_measure_notes(get_raw_notes_voice("P7", 156, "1"))
c2_t_91, c2_b_91 = demix_measure_notes(get_raw_notes_voice("P8", 156, "1"))

v_map_91 = {
    "P1": c1_s_91, "P2": c1_s_91, "P3": c1_a_91, "P4": c1_a_91,
    "P5": c1_t_91, "P6": c1_t_91, "P7": c1_b_91, "P8": c1_b_91,
    "P9": c2_s_91, "P10": c2_s_91, "P11": c2_a_91, "P12": c2_a_91,
    "P13": c2_t_91, "P14": c2_t_91, "P15": c2_b_91, "P16": c2_b_91,
}
add_measure(parts, 91, "91", v_map_91, time_sig=(3, 4))

print("Section 8 complete.")

out_path = Path("output/test_clamavi_mm0_91.xml")
ET.indent(root, space="  ")
tree_out = ET.ElementTree(root)
tree_out.write(out_path, encoding="utf-8", xml_declaration=True)
print(f"Written test score to {out_path}")
