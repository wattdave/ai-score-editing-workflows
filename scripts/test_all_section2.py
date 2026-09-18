import xml.etree.ElementTree as ET
from scripts.assemble_clamavi import (
    clean_standard_note,
    demix_measure_notes,
    make_rest_note,
    DIVISIONS,
)

tree = ET.parse('/Users/wattd/Downloads/Clamavi de tribulatione mea 12pp - 2021-06-23 b.xml')
root_raw = tree.getroot()
parts_raw = {p.attrib.get("id"): p for p in root_raw.findall("part")}

def get_raw_notes(pid, m_idx):
    m = parts_raw[pid].findall("measure")[m_idx]
    return m.findall("note")

# Check raw measures 18 to 28 (score mm. 18 to 28)
expected_time_sigs = {
    18: (9, 8, 1728),
    19: (3, 4, 1152),
    20: (4, 4, 1536),
    21: (4, 4, 1536),
    22: (4, 4, 1536),
    23: (4, 4, 1536),
    24: (4, 4, 1536),
    25: (4, 4, 1536),
    26: (2, 4, 768),
    27: (3, 4, 1152),
    28: (3, 4, 1152),
}

for score_m, (beats, beat_type, exp_dur) in expected_time_sigs.items():
    raw_idx = score_m  # because score m.18 is raw idx 18 (raw m.19)
    # Check parts P1, P2, P3, P4
    p1_notes = get_raw_notes("P1", raw_idx)
    p2_notes = get_raw_notes("P2", raw_idx)
    p3_notes = get_raw_notes("P3", raw_idx)
    p4_notes = get_raw_notes("P4", raw_idx)

    # In m.28: Choir 1 alone
    # Let's inspect durations
    d1 = sum(int(float(n.findtext("duration", 0))) // 10 for n in p1_notes if n.find("chord") is None)
    d2 = sum(int(float(n.findtext("duration", 0))) // 10 for n in p2_notes if n.find("chord") is None)
    d3 = sum(int(float(n.findtext("duration", 0))) // 10 for n in p3_notes if n.find("chord") is None)
    d4 = sum(int(float(n.findtext("duration", 0))) // 10 for n in p4_notes if n.find("chord") is None)
    print(f"score m.{score_m} (raw idx {raw_idx}) exp={exp_dur}: P1={d1}, P2={d2}, P3={d3}, P4={d4}")
