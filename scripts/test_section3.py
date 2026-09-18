import xml.etree.ElementTree as ET
from scripts.assemble_clamavi import (
    demix_measure_notes,
    clean_standard_note,
)

tree = ET.parse('/Users/wattd/Downloads/Clamavi de tribulatione mea 12pp - 2021-06-23 b.xml')
root_raw = tree.getroot()
parts_raw = {p.attrib.get("id"): p for p in root_raw.findall("part")}

def get_raw_notes(pid, m_idx):
    m = parts_raw[pid].findall("measure")[m_idx]
    return m.findall("note")

print("Checking Section 3 (score mm. 29 to 36):")
# m.29 (raw idx 29, 3/4 = 11520)
p1_notes = get_raw_notes("P1", 29)
p2_notes = get_raw_notes("P2", 29)
s_top, s_bot = demix_measure_notes(p1_notes)
t_top, t_bot = demix_measure_notes(p2_notes)

d_s_top = sum(int(n.findtext("duration", 0)) for n in s_top if n.find("chord") is None)
d_t_top = sum(int(n.findtext("duration", 0)) for n in t_top if n.find("chord") is None)
print(f"score m.29 C1 S: dur={d_s_top}, T: dur={d_t_top} (expected 11520)")

# m.30 (raw idx 30, 3/4 = 11520) - Choir 2 in P5/P6
p5_notes = get_raw_notes("P5", 30)
p6_notes = get_raw_notes("P6", 30)
c2_s_top, c2_s_bot = demix_measure_notes(p5_notes)
c2_t_top, c2_t_bot = demix_measure_notes(p6_notes)
d_c2_s = sum(int(n.findtext("duration", 0)) for n in c2_s_top if n.find("chord") is None)
d_c2_t = sum(int(n.findtext("duration", 0)) for n in c2_t_top if n.find("chord") is None)
print(f"score m.30 C2 S: dur={d_c2_s}, T: dur={d_c2_t} (expected 11520)")
