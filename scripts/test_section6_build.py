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
import scripts.test_section5_build as s5

parts = s5.parts
root = s5.root

print("Assembling Section 6 (mm. 55-67)...")

# =========================================================================
# m55 (4/4 = 15360) - Choir 1 completes "ae-ter - num:___", Choir 2 rests
# =========================================================================
c1_s1_55 = [
    make_pitch_note("G", 4, 1920, "eighth", alter=0, lyric_text="ae-", lyric_syl="begin"),
    make_pitch_note("E", 4, 5760, "quarter", is_dotted=True, alter=0, lyric_text="ter-", lyric_syl="middle", tie="start"),
    make_pitch_note("E", 4, 5760, "quarter", is_dotted=True, alter=0, tie="stop"),
    make_pitch_note("B", 3, 1920, "eighth", alter=0, lyric_text="num:___", lyric_syl="end", tie="start"),
]
c1_s2_55 = [
    make_pitch_note("E", 4, 3840, "quarter", alter=0),
    make_pitch_note("D", 4, 3840, "quarter", alter=1),
    make_pitch_note("B", 3, 3840, "quarter", alter=0, lyric_text="num,", lyric_syl="end"),
    make_rest_note(3840, "quarter"),
]
c1_a_55 = [
    make_pitch_note("E", 4, 3840, "quarter", alter=0, lyric_text="num,", lyric_syl="end"),
    make_rest_note(1920, "eighth"),
    make_pitch_note("E", 4, 1920, "eighth", alter=0, lyric_text="ae-", lyric_syl="begin"),
    make_pitch_note("D", 4, 3840, "quarter", alter=1, lyric_text="ter-", lyric_syl="middle"),
    make_pitch_note("C", 4, 3840, "quarter", alter=1, lyric_text="num:___", lyric_syl="end", tie="start"),
]
c1_t_55 = [
    make_pitch_note("C", 4, 3840, "quarter", alter=0, lyric_text="ae-", lyric_syl="begin"),
    make_pitch_note("A", 3, 3840, "quarter", alter=1, lyric_text="ter-", lyric_syl="middle"),
    make_pitch_note("G", 3, 3840, "quarter", alter=0),
    make_pitch_note("F", 3, 3840, "quarter", alter=1, tie="start"),
]
c1_b1_55 = [
    make_pitch_note("G", 3, 3840, "quarter", alter=0, lyric_text="ae-", lyric_syl="begin"),
    make_pitch_note("D", 3, 3840, "quarter", alter=1, lyric_text="ter-", lyric_syl="middle"),
    make_pitch_note("E", 3, 3840, "quarter", alter=0),
    make_pitch_note("D", 3, 3840, "quarter", alter=1, tie="start"),
]
c1_b2_55 = [
    make_pitch_note("G", 3, 3840, "quarter", alter=0, lyric_text="ae-", lyric_syl="begin"),
    make_pitch_note("D", 3, 3840, "quarter", alter=1, lyric_text="ter-", lyric_syl="middle"),
    make_pitch_note("B", 2, 3840, "quarter", alter=0),
    make_pitch_note("A", 2, 3840, "quarter", alter=1, tie="start"),
]
r15360 = [make_rest_note(15360, is_measure_rest=True)]

v_map_55 = {
    "P1": c1_s1_55, "P2": c1_s2_55, "P3": c1_a_55, "P4": c1_a_55,
    "P5": c1_t_55, "P6": c1_t_55, "P7": c1_b1_55, "P8": c1_b2_55,
    "P9": r15360, "P10": r15360, "P11": r15360, "P12": r15360,
    "P13": r15360, "P14": r15360, "P15": r15360, "P16": r15360,
}
add_measure(parts, 55, "55", v_map_55, time_sig=(4, 4))

# =========================================================================
# m56 (4/4 = 15360) - Choir 1 resolves and rests; Choir 2 TB enters
# =========================================================================
c1_s1_56 = [
    make_pitch_note("B", 3, 7680, "half", alter=0, tie="stop"),
    make_rest_note(7680, "half"),
]
c1_a_56 = [
    make_pitch_note("C", 4, 3840, "quarter", alter=1, tie="stop"),
    make_rest_note(3840, "quarter"),
    make_rest_note(7680, "half"),
]
c1_t_56 = [
    make_pitch_note("F", 3, 3840, "quarter", alter=1, tie="stop"),
    make_pitch_note("E", 3, 3840, "quarter", alter=0, lyric_text="num:", lyric_syl="end"),
    make_rest_note(7680, "half"),
]
c1_b1_56 = [
    make_pitch_note("D", 3, 3840, "quarter", alter=1, tie="stop"),
    make_pitch_note("B", 2, 3840, "quarter", alter=0, lyric_text="num:", lyric_syl="end"),
    make_rest_note(7680, "half"),
]
c1_b2_56 = [
    make_pitch_note("A", 2, 3840, "quarter", alter=1, tie="stop"),
    make_pitch_note("G", 2, 3840, "quarter", alter=0, lyric_text="num:", lyric_syl="end"),
    make_rest_note(7680, "half"),
]

c2_t_56 = [
    make_rest_note(3840, "quarter"),
    make_rest_note(1920, "eighth"),
    make_pitch_note("B", 3, 1920, "eighth", alter=0, lyric_text="ae-", lyric_syl="begin"),
    make_pitch_note("E", 4, 7680, "half", alter=0, lyric_text="-ter-", lyric_syl="middle", tie="start"),
]
c2_b1_56 = [
    make_pitch_note("B", 2, 3840, "quarter", alter=0, lyric_text="in", lyric_syl="single"),
    make_pitch_note("D", 3, 3840, "quarter", alter=1, lyric_text="ae-", lyric_syl="begin", tie="start"),
    make_pitch_note("D", 3, 7680, "half", alter=1, lyric_text="-ter-", lyric_syl="middle", tie="both"),
]
c2_b2_56 = [
    make_pitch_note("B", 2, 3840, "quarter", alter=0, lyric_text="in", lyric_syl="single"),
    make_pitch_note("A", 2, 3840, "quarter", alter=1, lyric_text="ae-", lyric_syl="begin", tie="start"),
    make_pitch_note("A", 2, 7680, "half", alter=1, lyric_text="-ter-", lyric_syl="middle", tie="both"),
]

v_map_56 = {
    "P1": c1_s1_56, "P2": r15360, "P3": c1_a_56, "P4": c1_a_56,
    "P5": c1_t_56, "P6": c1_t_56, "P7": c1_b1_56, "P8": c1_b2_56,
    "P9": r15360, "P10": r15360, "P11": r15360, "P12": r15360,
    "P13": c2_t_56, "P14": c2_t_56, "P15": c2_b1_56, "P16": c2_b2_56,
}
add_measure(parts, 56, "56", v_map_56, time_sig=None)

# =========================================================================
# m57 (4/4 = 15360) - Choir 1 rests; Choir 2 TB resolves
# =========================================================================
c2_t_57 = [
    make_pitch_note("E", 4, 1920, "eighth", alter=0, tie="stop"),
    make_pitch_note("D", 4, 5760, "quarter", is_dotted=True, alter=1),
    make_pitch_note("B", 3, 7680, "half", alter=0, lyric_text="num:___", lyric_syl="end"),
]
c2_b1_57 = [
    make_pitch_note("D", 3, 7680, "half", alter=1, tie="stop"),
    make_pitch_note("E", 3, 3840, "quarter", alter=0),
    make_pitch_note("B", 2, 3840, "quarter", alter=0, lyric_text="num:", lyric_syl="end"),
]
c2_b2_57 = [
    make_pitch_note("A", 2, 7680, "half", alter=1, tie="stop"),
    make_pitch_note("B", 2, 3840, "quarter", alter=0),
    make_pitch_note("B", 2, 3840, "quarter", alter=0, lyric_text="num:", lyric_syl="end"),
]

v_map_57 = {
    "P1": r15360, "P2": r15360, "P3": r15360, "P4": r15360,
    "P5": r15360, "P6": r15360, "P7": r15360, "P8": r15360,
    "P9": r15360, "P10": r15360, "P11": r15360, "P12": r15360,
    "P13": c2_t_57, "P14": c2_t_57, "P15": c2_b1_57, "P16": c2_b2_57,
}
add_measure(parts, 57, "57", v_map_57, time_sig=None)

# =========================================================================
# m58 (3/2 = 23040) - Choir 1 & 2 TB "ter-rae vec-tes con-clu -"
# =========================================================================
r23040 = [make_rest_note(23040, is_measure_rest=True)]

t_58 = [
    make_rest_note(3840, "quarter"),
    make_pitch_note("G", 3, 1920, "eighth", alter=1, lyric_text="ter-", lyric_syl="begin"),
    make_pitch_note("A", 3, 1920, "eighth", alter=0, lyric_text="-rae", lyric_syl="end"),
    make_pitch_note("B", 3, 3840, "quarter", alter=0, lyric_text="vec-", lyric_syl="begin"),
    make_pitch_note("B", 3, 3840, "quarter", alter=0, lyric_text="-tes", lyric_syl="end"),
    make_rest_note(3840, "quarter"),
    make_pitch_note("C", 4, 1920, "eighth", alter=1, lyric_text="con-", lyric_syl="begin"),
    make_pitch_note("D", 4, 1920, "eighth", alter=0, lyric_text="-clu-", lyric_syl="middle"),
]
b1_58 = [
    make_rest_note(3840, "quarter"),
    make_pitch_note("B", 3, 1920, "eighth", alter=0, lyric_text="ter-", lyric_syl="begin"),
    make_pitch_note("A", 3, 1920, "eighth", alter=0, lyric_text="-rae", lyric_syl="end"),
    make_pitch_note("G", 3, 3840, "quarter", alter=1, lyric_text="vec-", lyric_syl="begin"),
    make_pitch_note("F", 3, 3840, "quarter", alter=1, lyric_text="-tes", lyric_syl="end"),
    make_rest_note(3840, "quarter"),
    make_pitch_note("E", 3, 1920, "eighth", alter=0, lyric_text="con-", lyric_syl="begin"),
    make_pitch_note("F", 3, 1920, "eighth", alter=1, lyric_text="-clu-", lyric_syl="middle"),
]
b2_58 = [
    make_rest_note(3840, "quarter"),
    make_pitch_note("E", 3, 1920, "eighth", alter=0, lyric_text="ter-", lyric_syl="begin"),
    make_pitch_note("D", 3, 1920, "eighth", alter=0, lyric_text="-rae", lyric_syl="end"),
    make_pitch_note("C", 3, 3840, "quarter", alter=1, lyric_text="vec-", lyric_syl="begin"),
    make_pitch_note("B", 2, 3840, "quarter", alter=0, lyric_text="-tes", lyric_syl="end"),
    make_rest_note(3840, "quarter"),
    make_pitch_note("A", 2, 1920, "eighth", alter=0, lyric_text="con-", lyric_syl="begin"),
    make_pitch_note("B", 2, 1920, "eighth", alter=0, lyric_text="-clu-", lyric_syl="middle"),
]

v_map_58 = {
    "P1": r23040, "P2": r23040, "P3": r23040, "P4": r23040,
    "P5": t_58, "P6": t_58, "P7": b1_58, "P8": b2_58,
    "P9": r23040, "P10": r23040, "P11": r23040, "P12": r23040,
    "P13": t_58, "P14": t_58, "P15": b1_58, "P16": b2_58,
}
add_measure(parts, 58, "58", v_map_58, time_sig=(3, 2))

# =========================================================================
# m59 (4/4 = 15360) - Choir 1 & 2 TB "-se - runt"
# =========================================================================
t_59 = [
    make_pitch_note("G", 3, 11520, "half", is_dotted=True, alter=1, lyric_text="-se-", lyric_syl="middle"),
    make_pitch_note("A", 3, 3840, "quarter", alter=0, lyric_text="-runt", lyric_syl="end"),
]
b1_59 = [
    make_pitch_note("D", 3, 11520, "half", is_dotted=True, alter=1, lyric_text="-se-", lyric_syl="middle"),
    make_pitch_note("E", 3, 3840, "quarter", alter=0, lyric_text="-runt", lyric_syl="end"),
]
b2_59 = [
    make_pitch_note("G", 2, 11520, "half", is_dotted=True, alter=1, lyric_text="-se-", lyric_syl="middle"),
    make_pitch_note("A", 2, 3840, "quarter", alter=0, lyric_text="-runt", lyric_syl="end"),
]

v_map_59 = {
    "P1": r15360, "P2": r15360, "P3": r15360, "P4": r15360,
    "P5": t_59, "P6": t_59, "P7": b1_59, "P8": b2_59,
    "P9": r15360, "P10": r15360, "P11": r15360, "P12": r15360,
    "P13": t_59, "P14": t_59, "P15": b1_59, "P16": b2_59,
}
add_measure(parts, 59, "59", v_map_59, time_sig=(4, 4))

# =========================================================================
# m60 (4/4 = 15360) - Choir 1 & 2 TB "me."
# =========================================================================
t_60 = [make_pitch_note("G", 3, 15360, "whole", alter=0, lyric_text="me.", lyric_syl="single")]
b1_60 = [make_pitch_note("E", 3, 15360, "whole", alter=0, lyric_text="me.", lyric_syl="single")]
b2_60 = [make_pitch_note("E", 2, 15360, "whole", alter=0, lyric_text="me.", lyric_syl="single")]

v_map_60 = {
    "P1": r15360, "P2": r15360, "P3": r15360, "P4": r15360,
    "P5": t_60, "P6": t_60, "P7": b1_60, "P8": b2_60,
    "P9": r15360, "P10": r15360, "P11": r15360, "P12": r15360,
    "P13": t_60, "P14": t_60, "P15": b1_60, "P16": b2_60,
}
add_measure(parts, 60, "60", v_map_60, time_sig=None)

# =========================================================================
# m61 (3/4 = 11520) - "Serene and pure" Sopranos "Et", others rest
# =========================================================================
r11520 = [make_rest_note(11520, is_measure_rest=True)]
s_61 = [
    make_rest_note(3840, "quarter"),
    make_pitch_note("B", 4, 7680, "half", alter=0, lyric_text="Et", lyric_syl="single"),
]

v_map_61 = {
    "P1": s_61, "P2": s_61, "P3": r11520, "P4": r11520,
    "P5": r11520, "P6": r11520, "P7": r11520, "P8": r11520,
    "P9": s_61, "P10": s_61, "P11": r11520, "P12": r11520,
    "P13": r11520, "P14": r11520, "P15": r11520, "P16": r11520,
}
add_measure(parts, 61, "61", v_map_61, time_sig=(3, 4))

# =========================================================================
# m62 (3/4 = 11520) - Sopranos "sub-le-va-bis de cor-", others rest
# =========================================================================
s1_62 = [
    make_pitch_note("E", 5, 1920, "eighth", alter=0, lyric_text="sub-", lyric_syl="begin"),
    make_pitch_note("D", 5, 1920, "eighth", alter=1, lyric_text="-le-", lyric_syl="middle"),
    make_pitch_note("C", 5, 1920, "eighth", alter=1, lyric_text="-va-", lyric_syl="middle"),
    make_pitch_note("B", 4, 1920, "eighth", alter=0, lyric_text="-bis", lyric_syl="end"),
    make_pitch_note("C", 5, 1920, "eighth", alter=1, lyric_text="de", lyric_syl="single"),
    make_pitch_note("D", 5, 1920, "eighth", alter=1, lyric_text="cor-", lyric_syl="begin"),
]
s2_62 = [
    make_pitch_note("A", 4, 1920, "eighth", alter=1, lyric_text="sub-", lyric_syl="begin"),
    make_pitch_note("A", 4, 1920, "eighth", alter=1, lyric_text="-le-", lyric_syl="middle"),
    make_pitch_note("A", 4, 1920, "eighth", alter=1, lyric_text="-va-", lyric_syl="middle"),
    make_pitch_note("A", 4, 1920, "eighth", alter=1, lyric_text="-bis", lyric_syl="end"),
    make_pitch_note("A", 4, 1920, "eighth", alter=1, lyric_text="de", lyric_syl="single"),
    make_pitch_note("A", 4, 1920, "eighth", alter=1, lyric_text="cor-", lyric_syl="begin"),
]

v_map_62 = {
    "P1": s1_62, "P2": s2_62, "P3": r11520, "P4": r11520,
    "P5": r11520, "P6": r11520, "P7": r11520, "P8": r11520,
    "P9": s1_62, "P10": s2_62, "P11": r11520, "P12": r11520,
    "P13": r11520, "P14": r11520, "P15": r11520, "P16": r11520,
}
add_measure(parts, 62, "62", v_map_62, time_sig=None)

# =========================================================================
# m63 (7/8 = 13440) - Sopranos "-rup-ti-o-ne", others rest
# =========================================================================
r13440 = [make_rest_note(13440, is_measure_rest=True)]
s1_63 = [
    make_pitch_note("D", 5, 3840, "quarter", alter=1, lyric_text="-rup-", lyric_syl="middle"),
    make_pitch_note("D", 5, 1920, "eighth", alter=1, lyric_text="-ti-", lyric_syl="middle"),
    make_pitch_note("D", 5, 3840, "quarter", alter=1, lyric_text="-o-", lyric_syl="middle"),
    make_pitch_note("D", 5, 3840, "quarter", alter=1, lyric_text="-ne", lyric_syl="end"),
]
s2_63 = [
    make_pitch_note("G", 4, 3840, "quarter", alter=1, lyric_text="-rup-", lyric_syl="middle"),
    make_pitch_note("G", 4, 1920, "eighth", alter=1, lyric_text="-ti-", lyric_syl="middle"),
    make_pitch_note("G", 4, 3840, "quarter", alter=1, lyric_text="-o-", lyric_syl="middle"),
    make_pitch_note("G", 4, 3840, "quarter", alter=1, lyric_text="-ne", lyric_syl="end"),
]

v_map_63 = {
    "P1": s1_63, "P2": s2_63, "P3": r13440, "P4": r13440,
    "P5": r13440, "P6": r13440, "P7": r13440, "P8": r13440,
    "P9": s1_63, "P10": s2_63, "P11": r13440, "P12": r13440,
    "P13": r13440, "P14": r13440, "P15": r13440, "P16": r13440,
}
add_measure(parts, 63, "63", v_map_63, time_sig=(7, 8))

# =========================================================================
# m64 (4/4 = 15360) - Sopranos "vi - tam me-am", others rest
# =========================================================================
s1_64 = [
    make_pitch_note("D", 5, 1920, "eighth", alter=0, lyric_text="vi-", lyric_syl="begin"),
    make_pitch_note("D", 5, 1920, "eighth", alter=1),
    make_pitch_note("D", 5, 3840, "quarter", alter=1, lyric_text="-tam", lyric_syl="end"),
    make_pitch_note("E", 5, 3840, "quarter", alter=0, lyric_text="me-", lyric_syl="begin"),
    make_pitch_note("D", 5, 3840, "quarter", alter=1, lyric_text="-am", lyric_syl="end"),
]
s2_64 = [
    make_pitch_note("B", 4, 1920, "eighth", alter=0, lyric_text="vi-", lyric_syl="begin"),
    make_pitch_note("G", 4, 1920, "eighth", alter=1),
    make_pitch_note("G", 4, 3840, "quarter", alter=1, lyric_text="-tam", lyric_syl="end"),
    make_pitch_note("G", 4, 3840, "quarter", alter=0, lyric_text="me-", lyric_syl="begin"),
    make_pitch_note("G", 4, 3840, "quarter", alter=1, lyric_text="-am", lyric_syl="end"),
]

v_map_64 = {
    "P1": s1_64, "P2": s2_64, "P3": r15360, "P4": r15360,
    "P5": r15360, "P6": r15360, "P7": r15360, "P8": r15360,
    "P9": s1_64, "P10": s2_64, "P11": r15360, "P12": r15360,
    "P13": r15360, "P14": r15360, "P15": r15360, "P16": r15360,
}
add_measure(parts, 64, "64", v_map_64, time_sig=(4, 4))

# =========================================================================
# m65 (4/4 = 15360) - "a 3, SMA" Sopranos & Altos "Do-mi-ne De-us", TB rest
# =========================================================================
s1_65 = [
    make_pitch_note("D", 5, 5760, "quarter", is_dotted=True, alter=0, lyric_text="Do-", lyric_syl="begin"),
    make_pitch_note("D", 5, 1920, "eighth", alter=0, lyric_text="-mi-", lyric_syl="middle"),
    make_pitch_note("D", 5, 3840, "quarter", alter=0, lyric_text="-ne", lyric_syl="end"),
    make_pitch_note("D", 5, 1920, "eighth", alter=0, lyric_text="De-", lyric_syl="begin"),
    make_pitch_note("D", 5, 1920, "eighth", alter=0, lyric_text="-us", lyric_syl="end"),
]
s2_65 = [
    make_pitch_note("B", 4, 5760, "quarter", is_dotted=True, alter=0, lyric_text="Do-", lyric_syl="begin"),
    make_pitch_note("B", 4, 1920, "eighth", alter=0, lyric_text="-mi-", lyric_syl="middle"),
    make_pitch_note("B", 4, 3840, "quarter", alter=0, lyric_text="-ne", lyric_syl="end"),
    make_pitch_note("B", 4, 1920, "eighth", alter=0, lyric_text="De-", lyric_syl="begin"),
    make_pitch_note("B", 4, 1920, "eighth", alter=0, lyric_text="-us", lyric_syl="end"),
]
a_65 = [
    make_pitch_note("G", 4, 5760, "quarter", is_dotted=True, alter=0, lyric_text="Do-", lyric_syl="begin"),
    make_pitch_note("G", 4, 1920, "eighth", alter=0, lyric_text="-mi-", lyric_syl="middle"),
    make_pitch_note("G", 4, 3840, "quarter", alter=0, lyric_text="-ne", lyric_syl="end"),
    make_pitch_note("G", 4, 1920, "eighth", alter=0, lyric_text="De-", lyric_syl="begin"),
    make_pitch_note("G", 4, 1920, "eighth", alter=0, lyric_text="-us", lyric_syl="end"),
]

v_map_65 = {
    "P1": s1_65, "P2": s2_65, "P3": a_65, "P4": a_65,
    "P5": r15360, "P6": r15360, "P7": r15360, "P8": r15360,
    "P9": s1_65, "P10": s2_65, "P11": a_65, "P12": a_65,
    "P13": r15360, "P14": r15360, "P15": r15360, "P16": r15360,
}
add_measure(parts, 65, "65", v_map_65, time_sig=None)

# =========================================================================
# m66 (3/8 = 5760) - Sopranos & Altos "me -", TB rest
# =========================================================================
r5760 = [make_rest_note(5760, is_measure_rest=True)]
s1_66 = [
    make_pitch_note("D", 5, 3840, "quarter", alter=0, lyric_text="me-", lyric_syl="begin"),
    make_pitch_note("E", 5, 1920, "eighth", alter=-1),
]
s2_66 = [
    make_pitch_note("B", 4, 3840, "quarter", alter=0, lyric_text="me-", lyric_syl="begin"),
    make_pitch_note("A", 4, 1920, "eighth", alter=-1),
]
a_66 = [
    make_pitch_note("G", 4, 3840, "quarter", alter=0, lyric_text="me-", lyric_syl="begin"),
    make_pitch_note("E", 4, 1920, "eighth", alter=-1),
]

v_map_66 = {
    "P1": s1_66, "P2": s2_66, "P3": a_66, "P4": a_66,
    "P5": r5760, "P6": r5760, "P7": r5760, "P8": r5760,
    "P9": s1_66, "P10": s2_66, "P11": a_66, "P12": a_66,
    "P13": r5760, "P14": r5760, "P15": r5760, "P16": r5760,
}
add_measure(parts, 66, "66", v_map_66, time_sig=(3, 8))

# =========================================================================
# m67 (3/4 = 11520) - "-us", Choir 1 enters with "cum", Choir 2 rests
# =========================================================================
c1_s1_67 = [
    make_pitch_note("E", 5, 5760, "quarter", is_dotted=True, alter=-1, lyric_text="-us", lyric_syl="end"),
    make_rest_note(1920, "eighth"),
    make_pitch_note("A", 4, 3840, "quarter", alter=-1, lyric_text="cum", lyric_syl="single"),
]
c1_s2_67 = [
    make_pitch_note("A", 4, 5760, "quarter", is_dotted=True, alter=-1, lyric_text="-us", lyric_syl="end"),
    make_rest_note(1920, "eighth"),
    make_pitch_note("E", 4, 3840, "quarter", alter=-1, lyric_text="cum", lyric_syl="single"),
]
c1_a_67 = [
    make_pitch_note("E", 4, 5760, "quarter", is_dotted=True, alter=-1, lyric_text="-us", lyric_syl="end"),
    make_rest_note(1920, "eighth"),
    make_pitch_note("A", 3, 3840, "quarter", alter=-1, lyric_text="cum", lyric_syl="single"),
]

c2_s1_67 = [
    make_pitch_note("E", 5, 5760, "quarter", is_dotted=True, alter=-1, lyric_text="-us", lyric_syl="end"),
    make_rest_note(1920, "eighth"),
    make_rest_note(3840, "quarter"),
]
c2_s2_67 = [
    make_pitch_note("A", 4, 5760, "quarter", is_dotted=True, alter=-1, lyric_text="-us", lyric_syl="end"),
    make_rest_note(1920, "eighth"),
    make_rest_note(3840, "quarter"),
]
c2_a_67 = [
    make_pitch_note("E", 4, 5760, "quarter", is_dotted=True, alter=-1, lyric_text="-us", lyric_syl="end"),
    make_rest_note(1920, "eighth"),
    make_rest_note(3840, "quarter"),
]

v_map_67 = {
    "P1": c1_s1_67, "P2": c1_s2_67, "P3": c1_a_67, "P4": c1_a_67,
    "P5": r11520, "P6": r11520, "P7": r11520, "P8": r11520,
    "P9": c2_s1_67, "P10": c2_s2_67, "P11": c2_a_67, "P12": c2_a_67,
    "P13": r11520, "P14": r11520, "P15": r11520, "P16": r11520,
}
add_measure(parts, 67, "67", v_map_67, time_sig=(3, 4))

print("Section 6 complete.")

out_path = Path("output/test_clamavi_mm0_67.xml")
ET.indent(root, space="  ")
tree_out = ET.ElementTree(root)
tree_out.write(out_path, encoding="utf-8", xml_declaration=True)
print(f"Written test score to {out_path}")
