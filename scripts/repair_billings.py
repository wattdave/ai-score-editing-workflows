import xml.etree.ElementTree as ET
from xml.dom import minidom
from pathlib import Path
import shutil

xml_path = Path.home() / 'Downloads/Billings--Lamention Over Boston.xml'
orig_path = Path.home() / 'Downloads/Billings--Lamention Over Boston.xml.orig'

# 0. Backup original if not already backed up
if not orig_path.exists():
    shutil.copy2(xml_path, orig_path)
    print(f"Created backup: {orig_path}")
else:
    print(f"Backup already exists: {orig_path}")

tree = ET.parse(orig_path)
root = tree.getroot()

# 1. Root & Header Metadata
for child in list(root):
    if child.tag in ('work', 'identification', 'part-list'):
        root.remove(child)

work = ET.Element('work')
work_title = ET.SubElement(work, 'work-title')
work_title.text = "Lamentation Over Boston"
root.insert(0, work)

ident = ET.Element('identification')
creator = ET.SubElement(ident, 'creator', type='composer')
creator.text = "William Billings (1746-1800)"

rights = ET.SubElement(ident, 'rights')
rights.text = "Copyright © 2026 by Wendy Powers after Barry Johnston, ed., & AMS Billings Works"

encoding = ET.SubElement(ident, 'encoding')
software = ET.SubElement(encoding, 'software')
software.text = "Halbestunde (repaired)"
enc_date = ET.SubElement(encoding, 'encoding-date')
enc_date.text = "2026-09-15"

root.insert(1, ident)

# 2. Rebuild part-list with 4 vocal parts in a bracketed group
# Using "Bass Voice" to ensure Sibelius assigns choral bass rather than double bass
plist = ET.Element('part-list')
pg_start = ET.SubElement(plist, 'part-group', number='1', type='start')
ET.SubElement(pg_start, 'group-symbol').text = 'bracket'
ET.SubElement(pg_start, 'group-barline').text = 'yes'

parts_meta = [
    ('P1', 'Treble', 'Treble', 'Tr.', 'voice.soprano', '1'),
    ('P2', 'Counter', 'Counter', 'Ct.', 'voice.alto', '2'),
    ('P3', 'Tenor', 'Tenor', 'T.', 'voice.tenor', '3'),
    ('P4', 'Bass Voice', 'Bass Voice', 'B.', 'voice.bass', '4'),
]

for pid, pname, disp_name, abbr, sound_id, chan in parts_meta:
    sp = ET.SubElement(plist, 'score-part', id=pid)
    ET.SubElement(sp, 'part-name').text = pname
    if disp_name != pname:
        pnd = ET.SubElement(sp, 'part-name-display')
        ET.SubElement(pnd, 'display-text').text = disp_name
    ET.SubElement(sp, 'part-abbreviation').text = abbr
    if abbr != disp_name:
        pad = ET.SubElement(sp, 'part-abbreviation-display')
        ET.SubElement(pad, 'display-text').text = abbr

    instr = ET.SubElement(sp, 'score-instrument', id=f"{pid}-I1")
    ET.SubElement(instr, 'instrument-name').text = pname
    ET.SubElement(instr, 'instrument-sound').text = sound_id

    midi = ET.SubElement(sp, 'midi-instrument', id=f"{pid}-I1")
    ET.SubElement(midi, 'midi-channel').text = chan
    ET.SubElement(midi, 'midi-program').text = '53'

ET.SubElement(plist, 'part-group', number='1', type='stop')
root.insert(2, plist)

# 3. Restructure Parts:
# Move measures 83-133 from P5->P2, P6->P3, P7->P4, then delete P5, P6, P7
parts_dict = {p.attrib['id']: p for p in root.findall('part')}

# P2 (Counter): replace mm 83-133 with P5 mm 83-133
p2 = parts_dict['P2']
p5 = parts_dict['P5']
# Remove existing measures >= 83 from P2
for m in list(p2.findall('measure')):
    if int(m.attrib['number']) >= 83:
        p2.remove(m)
# Append measures >= 83 from P5 to P2
for m in p5.findall('measure'):
    if int(m.attrib['number']) >= 83:
        p2.append(m)

# P3 (Tenor): replace mm 83-133 with P6 mm 83-133
p3 = parts_dict['P3']
p6 = parts_dict['P6']
for m in list(p3.findall('measure')):
    if int(m.attrib['number']) >= 83:
        p3.remove(m)
for m in p6.findall('measure'):
    if int(m.attrib['number']) >= 83:
        p3.append(m)

# P4 (Bass): replace mm 83-133 with P7 mm 83-133
p4 = parts_dict['P4']
p7 = parts_dict['P7']
for m in list(p4.findall('measure')):
    if int(m.attrib['number']) >= 83:
        p4.remove(m)
for m in p7.findall('measure'):
    if int(m.attrib['number']) >= 83:
        p4.append(m)

# Remove parts P5, P6, P7 from root
for pid in ['P5', 'P6', 'P7']:
    root.remove(parts_dict[pid])

active_parts = {pid: parts_dict[pid] for pid in ['P1', 'P2', 'P3', 'P4']}

# 4. Measure-by-measure corrections across all 4 parts
for pid, part in active_parts.items():
    for m in part.findall('measure'):
        mnum = int(m.attrib['number'])

        # Fix float alter values '1.0' -> '1'
        for alt in m.findall('.//alter'):
            if alt.text == '1.0':
                alt.text = '1'

        # Remove spurious backward repeat at m48 (which was an OCR error for 3/2 time signature)
        if mnum == 48:
            for bl in list(m.findall('barline')):
                rep = bl.find('repeat')
                if rep is not None and rep.attrib.get('direction') == 'backward':
                    m.remove(bl)

        # Insert 3/2 time signature in measure 49
        if mnum == 49:
            attrs = m.find('attributes')
            if attrs is None:
                attrs = ET.Element('attributes')
                m.insert(0, attrs)
            time_elem = attrs.find('time')
            if time_elem is None:
                time_elem = ET.SubElement(attrs, 'time')
                beats = ET.SubElement(time_elem, 'beats')
                beats.text = '3'
                btype = ET.SubElement(time_elem, 'beat-type')
                btype.text = '2'

        # Ensure measure 50 has 2/2 time signature
        if mnum == 50:
            attrs = m.find('attributes')
            if attrs is None:
                attrs = ET.Element('attributes')
                m.insert(0, attrs)
            time_elem = attrs.find('time')
            if time_elem is None:
                time_elem = ET.SubElement(attrs, 'time')
                beats = ET.SubElement(time_elem, 'beats')
                beats.text = '2'
                btype = ET.SubElement(time_elem, 'beat-type')
                btype.text = '2'

        # Clean redundant key signatures on non-initial measures
        if mnum in [24, 54, 83, 109]:
            attrs = m.find('attributes')
            if attrs is not None:
                key_elem = attrs.find('key')
                if key_elem is not None:
                    attrs.remove(key_elem)
                # If attributes is now empty, remove it
                if len(attrs) == 0:
                    m.remove(attrs)

        # Remove redundant 4/4 time signature at m109 (piece continues in cut time 2/2)
        if mnum == 109:
            attrs = m.find('attributes')
            if attrs is not None:
                time_elem = attrs.find('time')
                if time_elem is not None:
                    attrs.remove(time_elem)
                if len(attrs) == 0:
                    m.remove(attrs)

        # Clean redundant clef at m83 if it matches initial clef
        if mnum == 83:
            attrs = m.find('attributes')
            if attrs is not None:
                clef = attrs.find('clef')
                if clef is not None:
                    attrs.remove(clef)
                if len(attrs) == 0:
                    m.remove(attrs)

# 5. Systematic Lyric and Prosody Corrections
# Define corrections for OCR misreads:
# (measure_number, part_id, old_text, new_text, new_syllabic)
lyric_corrections = [
    # m2: Kiv -> Riv
    (2, 'P1', 'Kiv', 'Riv', 'begin'),
    (2, 'P2', 'Kiv', 'Riv', 'begin'),
    (2, 'P3', 'Kiv', 'Riv', 'begin'),
    (2, 'P4', 'Kiv', 'Riv', 'begin'),
    # m13: berd -> ber'd
    (13, 'P1', 'berd', "ber'd", 'end'),
    (13, 'P2', 'berd', "ber'd", 'end'),
    (13, 'P3', 'berd', "ber'd", 'end'),
    (13, 'P4', 'berd', "ber'd", 'end'),
    # m14: Treble the -> thee
    (14, 'P1', 'the', 'thee', 'single'),
    # m17: berd -> ber'd
    (17, 'P1', 'berd', "ber'd", 'end'),
    (17, 'P2', 'berd', "ber'd", 'end'),
    (17, 'P3', 'berd', "ber'd", 'end'),
    (17, 'P4', 'berd', "ber'd", 'end'),
    # m20-21: riends -> Friends
    (21, 'P2', 'riends', 'Friends', 'single'),
    (21, 'P4', 'riends,', 'Friends,', 'single'),
    # m24: serve -> syllabic end
    (24, 'P1', 'serve', 'serve', 'end'),
    (24, 'P2', 'serve', 'serve', 'end'),
    (24, 'P3', 'serve', 'serve', 'end'),
    (24, 'P4', 'serve', 'serve', 'end'),
    # m39-40: Bass re-quired
    (39, 'P4', 're', 're', 'begin'),
    (40, 'P4', 'quired', 'quired', 'end'),
    # m45: Bass breth rer. -> breth ren.
    (45, 'P4', 'breth', 'breth', 'begin'),
    (45, 'P4', 'rer.', 'ren.', 'end'),
    # m59: Treble mer ic can -> mer i can
    (59, 'P1', 'ic', 'i', 'middle'),
    # m63: Ros bu ry -> Rox bu ry
    (63, 'P1', 'Ros', 'Rox', 'begin'),
    (63, 'P2', 'Ros', 'Rox', 'begin'),
    (63, 'P3', 'Ros', 'Rox', 'begin'),
    (63, 'P4', 'Ros', 'Rox', 'begin'),
    # m64: ech od -> ech o'd
    (64, 'P1', 'ech', 'ech', 'begin'),
    (64, 'P1', 'od', "o'd", 'end'),
    (64, 'P2', 'ech', 'ech', 'begin'),
    (64, 'P2', 'od', "o'd", 'end'),
    (64, 'P3', 'ech', 'ech', 'begin'),
    (64, 'P3', 'od', "o'd", 'end'),
    (64, 'P4', 'ech', 'ech', 'begin'),
    (64, 'P4', 'od', "o'd", 'end'),
    # m65: Tenor nemt. -> nent.
    (65, 'P3', 'nemt.', 'nent.', 'end'),
    # m76: Tenor dan -> Dan
    (76, 'P3', 'dan', 'Dan', 'begin'),
    # m83: dearTown, -> dear Town,
    (83, 'P1', 'dearTown,', 'dear', 'single'),
    (83, 'P4', 'dearTown,', 'dear', 'single'),
    # m84: add Town, if split
    (84, 'P1', 'Town,', 'Town,', 'single'),
    (84, 'P4', 'Town,', 'Town,', 'single'),
    # m2: Treble vers -> ers
    (2, 'P1', 'vers', 'ers', 'end'),
    # m91: Treble still -> still.
    (91, 'P1', 'still', 'still.', 'single'),
    # m95: Bass be -> ber
    (95, 'P4', 'be', 'ber', 'end'),
    # m105: Counter cerase -> cease
    (105, 'P2', 'cerase', 'cease', 'single'),
    # m116: Counter the, -> the
    (116, 'P2', 'the,', 'the', 'single'),
    (116, 'P2', 'Air', 'Air,', 'single'),
    # m126: Counter hance, -> hence,
    (126, 'P2', 'hance,', 'hence,', 'single'),
]

# Apply lyric corrections
for mnum, pid, old_txt, new_txt, new_syl in lyric_corrections:
    part = active_parts[pid]
    m = part.find(f"measure[@number='{mnum}']")
    if m is not None:
        for n in m.findall('note'):
            lyr = n.find('lyric')
            if lyr is not None:
                txt = lyr.find('text')
                if txt is not None and txt.text == old_txt:
                    txt.text = new_txt
                    syl = lyr.find('syllabic')
                    if syl is not None and new_syl:
                        syl.text = new_syl

# Special check for m83/m84 in P1 and P4:
# In P1 m83: let's inspect exactly what lyrics are on m83 and m84 notes
for pid in ['P1', 'P4']:
    part = active_parts[pid]
    m83 = part.find("measure[@number='83']")
    m84 = part.find("measure[@number='84']")
    notes83 = [n for n in m83.findall('note') if n.find('lyric') is not None]
    for n in notes83:
        txt = n.find('lyric/text')
        if txt is not None and 'dearTown' in txt.text:
            txt.text = 'dear'
    notes84 = [n for n in m84.findall('note') if n.find('lyric') is not None]
    if notes84:
        txt0 = notes84[0].find('lyric/text')
        if txt0 is not None and txt0.text != 'Town,':
            # ensure m84 has Town,
            txt0.text = 'Town,'

# 6. Pretty-print XML and write output
xml_str = ET.tostring(root, encoding='utf-8')
dom = minidom.parseString(xml_str)
pretty_xml = dom.toprettyxml(indent='  ', encoding='utf-8').decode('utf-8')
lines = [l for l in pretty_xml.splitlines() if l.strip()]
header = """<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 3.1 Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">"""
final_output = header + "\n" + "\n".join(lines[1:]) + "\n"

xml_path.write_text(final_output, encoding='utf-8')
print("Successfully wrote repaired MusicXML to:", xml_path)
