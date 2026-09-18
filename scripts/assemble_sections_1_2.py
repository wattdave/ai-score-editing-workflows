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

tree = ET.parse('/Users/wattd/Downloads/Clamavi de tribulatione mea 12pp - 2021-06-23 b.xml')
root_raw = tree.getroot()
parts_raw = {p.attrib.get("id"): p for p in root_raw.findall("part")}

def get_raw_notes(pid, m_idx):
    m = parts_raw[pid].findall("measure")[m_idx]
    return m.findall("note")

root, parts = create_base_score()

print("Assembling Section 1 (mm. 0-17)...")
# m0 (pickup, 1/8 = 1920)
s0 = [make_pitch_note("D", 4, 1920, "eighth", lyric_text="Cla", lyric_syl="begin", accent=True)]
r0 = [make_rest_note(1920, "eighth")]
add_tutti_unison_measure(parts, 0, "0", (1, 8), s0, r0, r0, r0, is_pickup=True)

# m1 (3/4 = 11520)
s1 = [make_pitch_note("E", 5, 11520, "half", alter=-1, is_dotted=True, lyric_text="ma", lyric_syl="middle")]
r1 = [make_rest_note(11520, is_measure_rest=True)]
add_tutti_unison_measure(parts, 1, "1", (3, 4), s1, r1, r1, r1)

# m2 (3/4 = 11520)
s2 = [make_pitch_note("B", 4, 11520, "half", alter=-1, is_dotted=True, tie="start", lyric_text="vi", lyric_syl="end")]
a2 = [
    make_rest_note(3840, "quarter"),
    make_rest_note(3840, "quarter"),
    make_rest_note(1920, "eighth"),
    make_pitch_note("D", 4, 1920, "eighth", lyric_text="de", lyric_syl="single"),
]
r2 = [make_rest_note(11520, is_measure_rest=True)]
add_tutti_unison_measure(parts, 2, "2", None, s2, a2, r2, r2)

# m3 (11/8 = 21120)
s3 = [
    make_pitch_note("B", 4, 15360, "whole", alter=-1, tie="stop"),
    make_rest_note(5760, note_type="quarter", is_measure_rest=False, is_dotted=True),
]
a3 = [
    make_pitch_note("D", 4, 1920, "eighth", lyric_text="tri", lyric_syl="begin"),
    make_pitch_note("D", 4, 1920, "eighth", lyric_text="bu", lyric_syl="middle"),
    make_pitch_note("D", 4, 1920, "eighth", lyric_text="la", lyric_syl="middle"),
    make_pitch_note("D", 4, 1920, "eighth", lyric_text="ti", lyric_syl="middle"),
    make_pitch_note("D", 4, 1920, "eighth", lyric_text="o", lyric_syl="middle"),
    make_pitch_note("F", 4, 1920, "eighth", lyric_text="ne", lyric_syl="end"),
    make_pitch_note("G", 4, 1920, "eighth", lyric_text="me", lyric_syl="begin"),
    make_pitch_note("A", 4, 1920, "eighth", alter=-1, lyric_text="-", lyric_syl="middle"),
    make_pitch_note("B", 4, 1920, "eighth", alter=-1, lyric_text="a", lyric_syl="end"),
    make_pitch_note("A", 4, 1920, "eighth", alter=-1, lyric_text="-", lyric_syl="middle"),
    make_pitch_note("G", 4, 1920, "eighth", lyric_text="ad", lyric_syl="single"),
]
r3 = [make_rest_note(21120, is_measure_rest=True)]
add_tutti_unison_measure(parts, 3, "3", (11, 8), s3, a3, r3, r3)

# m4 (9/8 = 17280)
s4 = [make_rest_note(17280, is_measure_rest=True)]
a4 = [
    make_pitch_note("G", 4, 1920, "eighth", lyric_text="Do", lyric_syl="begin"),
    make_pitch_note("D", 4, 1920, "eighth", lyric_text="mi", lyric_syl="middle"),
    make_pitch_note("D", 4, 7680, "half", tie="start", lyric_text="num", lyric_syl="end"),
    make_pitch_note("D", 4, 5760, "quarter", is_dotted=True, tie="stop"),
]
t4 = [
    make_rest_note(3840, "quarter"),
    make_rest_note(1920, "eighth"),
    make_pitch_note("D", 3, 1920, "eighth", lyric_text="et", lyric_syl="single"),
    make_pitch_note("F", 3, 1920, "eighth", lyric_text="ex", lyric_syl="begin"),
    make_pitch_note("G", 3, 1920, "eighth", lyric_text="au", lyric_syl="middle"),
    make_pitch_note("A", 3, 1920, "eighth", alter=-1, lyric_text="di", lyric_syl="middle"),
    make_pitch_note("B", 3, 1920, "eighth", alter=-1, lyric_text="-", lyric_syl="middle"),
    make_pitch_note("C", 4, 1920, "eighth", lyric_text="vit", lyric_syl="end"),
]
b4 = [make_rest_note(17280, is_measure_rest=True)]
add_tutti_unison_measure(parts, 4, "4", (9, 8), s4, a4, t4, b4)

# m5 (4/4 = 15360)
s5 = [
    make_rest_note(3840, "quarter"),
    make_rest_note(1920, "eighth"),
    make_pitch_note("F", 4, 1920, "eighth", lyric_text="cla", lyric_syl="begin"),
    make_pitch_note("E", 5, 5760, "quarter", alter=-1, is_dotted=True, lyric_text="ma", lyric_syl="middle"),
    make_pitch_note("F", 5, 1920, "eighth", lyric_text="-", lyric_syl="middle"),
]
t5 = [make_pitch_note("D", 4, 15360, "whole", tie="start", lyric_text="me;", lyric_syl="single")]
r5 = [make_rest_note(15360, is_measure_rest=True)]
add_tutti_unison_measure(parts, 5, "5", (4, 4), s5, r5, t5, r5)

# m6 (3/4 = 11520)
s6 = [
    make_pitch_note("B", 4, 7680, "half", alter=-1, lyric_text="vi", lyric_syl="end"),
    make_rest_note(3840, "quarter"),
]
a6 = [
    make_rest_note(7680, "half"),
    make_rest_note(1920, "eighth"),
    make_pitch_note("F", 4, 1920, "eighth", lyric_text="de", lyric_syl="single"),
]
t6 = [
    make_pitch_note("D", 4, 7680, "half", tie="stop"),
    make_rest_note(3840, "quarter"),
]
b6 = [
    make_rest_note(7680, "half"),
    make_rest_note(1920, "eighth"),
    make_pitch_note("D", 3, 1920, "eighth", lyric_text="de", lyric_syl="single"),
]
add_tutti_unison_measure(parts, 6, "6", (3, 4), s6, a6, t6, b6)

# m7 (3/4 = 11520)
r7 = [make_rest_note(11520, is_measure_rest=True)]
a7 = [
    make_pitch_note("F", 4, 1920, "eighth", lyric_text="ven", lyric_syl="begin"),
    make_pitch_note("F", 4, 1920, "eighth", lyric_text="tre", lyric_syl="end"),
    make_pitch_note("F", 4, 1920, "eighth", lyric_text="in", lyric_syl="begin"),
    make_pitch_note("G", 4, 1920, "eighth", lyric_text="fe", lyric_syl="middle"),
    make_pitch_note("A", 4, 1920, "eighth", alter=-1, lyric_text="ri", lyric_syl="end"),
    make_pitch_note("B", 4, 1920, "eighth", alter=-1, lyric_text="cla", lyric_syl="begin"),
]
b7 = [
    make_pitch_note("D", 3, 1920, "eighth", lyric_text="ven", lyric_syl="begin"),
    make_pitch_note("D", 3, 1920, "eighth", lyric_text="tre", lyric_syl="end"),
    make_pitch_note("D", 3, 1920, "eighth", lyric_text="in", lyric_syl="begin"),
    make_pitch_note("E", 3, 1920, "eighth", alter=-1, lyric_text="fe", lyric_syl="middle"),
    make_pitch_note("F", 3, 1920, "eighth", lyric_text="ri", lyric_syl="end"),
    make_pitch_note("G", 3, 1920, "eighth", lyric_text="cla", lyric_syl="begin"),
]
add_tutti_unison_measure(parts, 7, "7", None, r7, a7, r7, b7)

# m8 (3/4 = 11520)
r8 = [make_rest_note(11520, is_measure_rest=True)]
a8 = [
    make_pitch_note("B", 4, 2880, "eighth", alter=-1, is_dotted=True, lyric_text="ma", lyric_syl="middle"),
    make_pitch_note("D", 4, 960, "16th", lyric_text="vi,", lyric_syl="end"),
    make_rest_note(1920, "eighth"),
    make_pitch_note("F", 4, 1920, "eighth", lyric_text="et", lyric_syl="single"),
    make_pitch_note("F", 4, 1920, "eighth", lyric_text="ex", lyric_syl="begin"),
    make_pitch_note("F", 4, 1920, "eighth", lyric_text="au", lyric_syl="middle"),
]
b8 = [
    make_pitch_note("G", 3, 2880, "eighth", is_dotted=True, lyric_text="ma", lyric_syl="middle"),
    make_pitch_note("G", 3, 960, "16th", lyric_text="vi,", lyric_syl="end"),
    make_rest_note(1920, "eighth"),
    make_pitch_note("D", 3, 1920, "eighth", lyric_text="et", lyric_syl="single"),
    make_pitch_note("D", 3, 1920, "eighth", lyric_text="ex", lyric_syl="begin"),
    make_pitch_note("D", 3, 1920, "eighth", lyric_text="au", lyric_syl="middle"),
]
add_tutti_unison_measure(parts, 8, "8", None, r8, a8, r8, b8)

# m9 (9/8 = 17280)
s9 = [
    make_rest_note(5760, note_type="quarter", is_measure_rest=False, is_dotted=True),
    make_rest_note(3840, "quarter"),
    make_rest_note(3840, "quarter"),
    make_rest_note(1920, "eighth"),
    make_pitch_note("C", 5, 1920, "eighth", lyric_text="et", lyric_syl="single"),
]
t9 = [
    make_rest_note(5760, note_type="quarter", is_measure_rest=False, is_dotted=True),
    make_rest_note(3840, "quarter"),
    make_rest_note(3840, "quarter"),
    make_rest_note(1920, "eighth"),
    make_pitch_note("G", 3, 1920, "eighth", lyric_text="et", lyric_syl="single"),
]
a9 = [
    make_pitch_note("F", 4, 1920, "eighth", lyric_text="di", lyric_syl="middle"),
    make_pitch_note("G", 4, 1920, "eighth", lyric_text="-", lyric_syl="middle"),
    make_pitch_note("B", 4, 1920, "eighth", alter=-1, lyric_text="sti", lyric_syl="end"),
    make_pitch_note("C", 5, 1920, "eighth", lyric_text="vo", lyric_syl="begin"),
    make_pitch_note("B", 4, 1920, "eighth", alter=-1, lyric_text="-", lyric_syl="middle"),
    make_pitch_note("G", 4, 3840, "quarter", lyric_text="cem,", lyric_syl="end"),
    make_rest_note(1920, "eighth"),
    make_pitch_note("G", 4, 1920, "eighth", lyric_text="et", lyric_syl="single"),
]
b9 = [
    make_pitch_note("D", 3, 1920, "eighth", lyric_text="di", lyric_syl="middle"),
    make_pitch_note("F", 3, 1920, "eighth", lyric_text="-", lyric_syl="middle"),
    make_pitch_note("G", 3, 1920, "eighth", lyric_text="sti", lyric_syl="end"),
    make_pitch_note("A", 3, 1920, "eighth", lyric_text="vo", lyric_syl="begin"),
    make_pitch_note("G", 3, 1920, "eighth", lyric_text="-", lyric_syl="middle"),
    make_pitch_note("D", 3, 3840, "quarter", lyric_text="cem,", lyric_syl="end"),
    make_rest_note(1920, "eighth"),
    make_pitch_note("G", 3, 1920, "eighth", lyric_text="et", lyric_syl="single"),
]
add_tutti_unison_measure(parts, 9, "9", (9, 8), s9, a9, t9, b9)

# m10 (3/4 = 11520)
s10 = [make_pitch_note("C", 5, 1920, "eighth", lyric_text=txt, lyric_syl=syl) for txt, syl in [("ex","begin"),("au","middle"),("di","middle"),("sti","end"),("vo","begin"),("cem","end")]]
a10 = [make_pitch_note("G", 4, 1920, "eighth", lyric_text=txt, lyric_syl=syl) for txt, syl in [("ex","begin"),("au","middle"),("di","middle"),("sti","end"),("vo","begin"),("cem","end")]]
t10 = [make_pitch_note("G", 3, 1920, "eighth", lyric_text=txt, lyric_syl=syl) for txt, syl in [("ex","begin"),("au","middle"),("di","middle"),("sti","end"),("vo","begin"),("cem","end")]]
b10 = [make_pitch_note("E", 3, 1920, "eighth", lyric_text=txt, lyric_syl=syl) for txt, syl in [("ex","begin"),("au","middle"),("di","middle"),("sti","end"),("vo","begin"),("cem","end")]]
add_tutti_unison_measure(parts, 10, "10", (3, 4), s10, a10, t10, b10)

# m11 (3/4 = 11520)
s11 = [make_pitch_note("F", 5, 7680, "half", tie="start", lyric_text="me", lyric_syl="begin"), make_pitch_note("E", 5, 3840, "quarter", lyric_text="-", lyric_syl="middle")]
a11 = [make_pitch_note("C", 5, 11520, "half", is_dotted=True, lyric_text="me", lyric_syl="begin")]
t11 = [make_pitch_note("G", 3, 7680, "half", lyric_text="me", lyric_syl="begin"), make_pitch_note("A", 3, 3840, "quarter", lyric_text="-", lyric_syl="middle")]
b11 = [make_pitch_note("C", 3, 7680, "half", lyric_text="me", lyric_syl="begin"), make_pitch_note("F", 3, 3840, "quarter", lyric_text="-", lyric_syl="middle")]
add_tutti_unison_measure(parts, 11, "11", None, s11, a11, t11, b11)

# m12 (3/4 = 11520)
s12 = [make_pitch_note("F", 5, 7680, "half", tie="stop", lyric_text="am,", lyric_syl="end"), make_pitch_note("F", 5, 1920, "eighth"), make_rest_note(1920, "eighth")]
a12 = [make_pitch_note("C", 5, 7680, "half", lyric_text="am,", lyric_syl="end"), make_pitch_note("C", 5, 1920, "eighth"), make_rest_note(1920, "eighth")]
t12 = [make_pitch_note("A", 3, 7680, "half", lyric_text="am,", lyric_syl="end"), make_pitch_note("A", 3, 1920, "eighth"), make_rest_note(1920, "eighth")]
b12 = [make_pitch_note("F", 3, 7680, "half", lyric_text="am,", lyric_syl="end"), make_pitch_note("F", 3, 1920, "eighth"), make_rest_note(1920, "eighth")]
add_tutti_unison_measure(parts, 12, "12", None, s12, a12, t12, b12)

# mm 13-17: Extracted from raw XML with Bass shift fixed (Bass = raw P4 idx-1)
for mnum in range(13, 18):
    raw_idx = mnum  # raw P1..P3 index
    bass_idx = mnum - 1 # raw P4 index (shifted 1 earlier)
    s_n = [clean_standard_note(n) for n in get_raw_notes("P1", raw_idx)]
    a_n = [clean_standard_note(n) for n in get_raw_notes("P2", raw_idx)]
    t_n = [clean_standard_note(n) for n in get_raw_notes("P3", raw_idx)]
    b_n = [clean_standard_note(n) for n in get_raw_notes("P4", bass_idx)]
    add_tutti_unison_measure(parts, mnum, str(mnum), None, s_n, a_n, t_n, b_n)

print("Section 1 complete.")

print("Assembling Section 2 (mm. 18-28)...")
# m18 (9/8 = 17280)
s18 = [clean_standard_note(n) for n in get_raw_notes("P1", 18)]
a18 = [clean_standard_note(n) for n in get_raw_notes("P2", 18)]
t18 = [clean_standard_note(n) for n in get_raw_notes("P3", 18)]
b18 = [clean_standard_note(n) for n in get_raw_notes("P4", 18)]
add_tutti_unison_measure(parts, 18, "18", (9, 8), s18, a18, t18, b18)

# m19 (3/4 = 11520) - Alto divisi
s19 = [clean_standard_note(n) for n in get_raw_notes("P1", 19)]
a19_top, a19_bot = demix_measure_notes(get_raw_notes("P2", 19))
t19 = [clean_standard_note(n) for n in get_raw_notes("P3", 19)]
b19 = [clean_standard_note(n) for n in get_raw_notes("P4", 19)]
v_map_19 = {
    "P1": s19, "P2": s19, "P9": s19, "P10": s19,
    "P3": a19_top, "P4": a19_bot, "P11": a19_top, "P12": a19_bot,
    "P5": t19, "P6": t19, "P13": t19, "P14": t19,
    "P7": b19, "P8": b19, "P15": b19, "P16": b19,
}
add_measure(parts, 19, "19", v_map_19, time_sig=(3, 4))

# m20 (4/4 = 15360) - Alto divisi
s20 = [clean_standard_note(n) for n in get_raw_notes("P1", 20)]
a20_top, a20_bot = demix_measure_notes(get_raw_notes("P2", 20))
t20 = [clean_standard_note(n) for n in get_raw_notes("P3", 20)]
b20 = [clean_standard_note(n) for n in get_raw_notes("P4", 20)]
v_map_20 = {
    "P1": s20, "P2": s20, "P9": s20, "P10": s20,
    "P3": a20_top, "P4": a20_bot, "P11": a20_top, "P12": a20_bot,
    "P5": t20, "P6": t20, "P13": t20, "P14": t20,
    "P7": b20, "P8": b20, "P15": b20, "P16": b20,
}
add_measure(parts, 20, "20", v_map_20, time_sig=(4, 4))

# m21 (4/4 = 15360) - S has Bb4, A has Gb4, T/B tied
s21 = [clean_standard_note(n) for n in get_raw_notes("P1", 21)]
a21 = [clean_standard_note(n) for n in get_raw_notes("P2", 21)]
t21 = [clean_standard_note(n) for n in get_raw_notes("P3", 21)]
b21 = [clean_standard_note(n) for n in get_raw_notes("P4", 21)]
add_tutti_unison_measure(parts, 21, "21", None, s21, a21, t21, b21)

# m22 (4/4 = 15360) - Bass enters alone (with quintuplet fix)
r22 = [make_rest_note(15360, is_measure_rest=True)]
b22_raw = get_raw_notes("P4", 22)
b22 = []
for n in b22_raw:
    n_clean = clean_standard_note(n)
    # Fix quintuplet 16th duration from 640 to 768
    if n_clean.findtext("type") == "16th":
        d = n_clean.find("duration")
        if d is not None:
            d.text = "768"
    b22.append(n_clean)
add_tutti_unison_measure(parts, 22, "22", None, r22, r22, r22, b22)

# m23 (4/4 = 15360) - S and A enter, Bass continues
s23 = [clean_standard_note(n) for n in get_raw_notes("P1", 23)]
a23 = [clean_standard_note(n) for n in get_raw_notes("P2", 23)]
r23 = [make_rest_note(15360, is_measure_rest=True)]
b23 = [clean_standard_note(n) for n in get_raw_notes("P4", 23)]
add_tutti_unison_measure(parts, 23, "23", None, s23, a23, r23, b23)

# m24 (4/4 = 15360) - T and B sing
r24 = [make_rest_note(15360, is_measure_rest=True)]
t24 = [clean_standard_note(n) for n in get_raw_notes("P3", 24)]
b24 = [clean_standard_note(n) for n in get_raw_notes("P4", 24)]
add_tutti_unison_measure(parts, 24, "24", None, r24, r24, t24, b24)

# m25 (4/4 = 15360) - S, A, T, B
s25 = [clean_standard_note(n) for n in get_raw_notes("P1", 25)]
a25 = [clean_standard_note(n) for n in get_raw_notes("P2", 25)]
t25 = [clean_standard_note(n) for n in get_raw_notes("P3", 25)]
b25 = [clean_standard_note(n) for n in get_raw_notes("P4", 25)]
add_tutti_unison_measure(parts, 25, "25", None, s25, a25, t25, b25)

# m26 (2/4 = 7680)
s26 = [clean_standard_note(n) for n in get_raw_notes("P1", 26)]
a26 = [clean_standard_note(n) for n in get_raw_notes("P2", 26)]
t26 = [clean_standard_note(n) for n in get_raw_notes("P3", 26)]
b26 = [clean_standard_note(n) for n in get_raw_notes("P4", 26)]
add_tutti_unison_measure(parts, 26, "26", (2, 4), s26, a26, t26, b26)

# m27 (3/4 = 11520) - S and A rest, T and B sing
r27 = [make_rest_note(11520, is_measure_rest=True)]
t27 = [clean_standard_note(n) for n in get_raw_notes("P3", 27)]
b27 = [clean_standard_note(n) for n in get_raw_notes("P4", 27)]
add_tutti_unison_measure(parts, 27, "27", (3, 4), r27, r27, t27, b27)

# m28 (3/4 = 11520) - Choir 1 alone, Choir 2 rests!
s28 = [clean_standard_note(n) for n in get_raw_notes("P1", 28)]
a28 = [clean_standard_note(n) for n in get_raw_notes("P2", 28)]
t28 = [clean_standard_note(n) for n in get_raw_notes("P3", 28)]
b28 = [clean_standard_note(n) for n in get_raw_notes("P4", 28)]
r28 = [make_rest_note(11520, is_measure_rest=True)]

v_map_28 = {
    # Choir 1 sings
    "P1": s28, "P2": s28, "P3": a28, "P4": a28,
    "P5": t28, "P6": t28, "P7": b28, "P8": b28,
    # Choir 2 rests
    "P9": r28, "P10": r28, "P11": r28, "P12": r28,
    "P13": r28, "P14": r28, "P15": r28, "P16": r28,
}
add_measure(parts, 28, "28", v_map_28, time_sig=None)

print("Section 2 complete.")

out_path = Path("output/test_clamavi_mm0_28.xml")
ET.indent(root, space="  ")
tree_out = ET.ElementTree(root)
tree_out.write(out_path, encoding="utf-8", xml_declaration=True)
print(f"Written test score to {out_path}")
