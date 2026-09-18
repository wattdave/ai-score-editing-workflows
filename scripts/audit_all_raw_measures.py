import xml.etree.ElementTree as ET

tree = ET.parse('/Users/wattd/Downloads/Clamavi de tribulatione mea 12pp - 2021-06-23 b.xml')
root_raw = tree.getroot()
parts = {p.attrib.get("id"): p for p in root_raw.findall("part")}

print("Checking measure counts across all parts:")
for pid, p in parts.items():
    print(f"  {pid}: {len(p.findall('measure'))} measures")
