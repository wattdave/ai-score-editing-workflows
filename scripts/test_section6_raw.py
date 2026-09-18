import xml.etree.ElementTree as ET

tree = ET.parse('/Users/wattd/Downloads/Clamavi de tribulatione mea 12pp - 2021-06-23 b.xml')
root_raw = tree.getroot()
parts_raw = {p.attrib.get("id"): p for p in root_raw.findall("part")}

for m_idx in range(54, 62):
    active = {}
    for pid, p in parts_raw.items():
        m = p.findall("measure")[m_idx]
        notes = [n for n in m.findall("note") if n.find("pitch") is not None]
        if notes:
            lyrs = [l.findtext("text") for l in m.findall(".//lyric") if l.findtext("text")]
            active[pid] = f"{len(notes)}n ({' '.join(lyrs[:2])})"
    ts = parts_raw["P1"].findall("measure")[m_idx].find(".//time")
    ts_str = f" [{ts.findtext('beats')}/{ts.findtext('beat-type')}]" if ts is not None else ""
    print(f"raw idx {m_idx} (raw m={m_idx+1}){ts_str}: {active}")
