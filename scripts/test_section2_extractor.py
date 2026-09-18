import xml.etree.ElementTree as ET
from scripts.assemble_clamavi import (
    create_base_score,
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

# Test extracting raw m.19 (score m.18, 9/8)
m18_s = [clean_standard_note(n) for n in get_raw_notes("P1", 18)]
m18_a = [clean_standard_note(n) for n in get_raw_notes("P2", 18)]
m18_t = [clean_standard_note(n) for n in get_raw_notes("P3", 18)]
m18_b = [clean_standard_note(n) for n in get_raw_notes("P4", 18)]

for name, notes in [("S", m18_s), ("A", m18_a), ("T", m18_t), ("B", m18_b)]:
    dur = sum(int(n.findtext("duration", 0)) for n in notes if n.find("chord") is None)
    print(f"m.18 {name}: dur={dur} (expected 1728)")

# Test extracting raw m.20 (score m.19, 3/4) with Alto divisi
m19_s = [clean_standard_note(n) for n in get_raw_notes("P1", 19)]
m19_a_raw = get_raw_notes("P2", 19)
m19_a_top, m19_a_bot = demix_measure_notes(m19_a_raw)
m19_a_top = [clean_standard_note(n) for n in m19_a_top]
m19_a_bot = [clean_standard_note(n) for n in m19_a_bot]
m19_t = [clean_standard_note(n) for n in get_raw_notes("P3", 19)]
m19_b = [clean_standard_note(n) for n in get_raw_notes("P4", 19)]

for name, notes in [("S", m19_s), ("A_top", m19_a_top), ("A_bot", m19_a_bot), ("T", m19_t), ("B", m19_b)]:
    dur = sum(int(n.findtext("duration", 0)) for n in notes if n.find("chord") is None)
    print(f"m.19 {name}: dur={dur} (expected 1152)")
