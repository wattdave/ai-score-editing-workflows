import xml.etree.ElementTree as ET

tree = ET.parse('/Users/wattd/Downloads/Clamavi de tribulatione mea 12pp - 2021-06-23 b.xml')
root_raw = tree.getroot()
parts_raw = {p.attrib.get("id"): p for p in root_raw.findall("part")}

print("Mapping remaining raw measures (from idx 133 onward):")
for m_idx in range(133, 180):
    lyr_summary = []
    for pid in ["P1", "P2", "P3", "P4", "P5", "P7", "P8"]:
        if pid in parts_raw:
            m = parts_raw[pid].findall("measure")[m_idx]
            lyrs = [l.findtext("text") for l in m.findall(".//lyric") if l.findtext("text")]
            if lyrs:
                lyr_summary.append(f"{pid}:{' '.join(lyrs[:3])}")
    ts = parts_raw["P1"].findall("measure")[m_idx].find(".//time")
    ts_str = f" [{ts.findtext('beats')}/{ts.findtext('beat-type')}]" if ts is not None else ""
    if lyr_summary:
        print(f"raw idx {m_idx:3d} (m={m_idx+1:3d}){ts_str}: {', '.join(lyr_summary)}")
