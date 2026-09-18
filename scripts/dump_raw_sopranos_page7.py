import xml.etree.ElementTree as ET

tree = ET.parse('/Users/wattd/Downloads/Clamavi de tribulatione mea 12pp - 2021-06-23 b.xml')
root_raw = tree.getroot()
parts_raw = {p.attrib.get("id"): p for p in root_raw.findall("part")}

p1 = parts_raw["P1"]
for m_idx in range(61, 68):
    m = p1.findall("measure")[m_idx]
    notes = m.findall("note")
    ts = m.find(".//time")
    ts_str = f" [{ts.findtext('beats')}/{ts.findtext('beat-type')}]" if ts is not None else ""
    print(f"raw idx {m_idx} (m={m_idx+1}){ts_str}:")
    for n in notes:
        chord = n.find("chord") is not None
        rest = n.find("rest") is not None
        dur = n.findtext("duration")
        p = n.find("pitch")
        p_str = f"{p.findtext('step')}{p.findtext('alter','')}{p.findtext('octave')}" if p is not None else "REST"
        lyrs = [l.findtext("text") for l in n.findall(".//lyric")]
        print(f"  {'CHORD ' if chord else ''}{p_str} dur={dur} lyr={lyrs}")
