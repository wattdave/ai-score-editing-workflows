import xml.etree.ElementTree as ET
from xml.dom import minidom
from pathlib import Path

source_path = Path('/Users/wattd/Downloads/267132177-Posada-Mexicana-Tradicional.xml.orig')
if not source_path.exists():
    source_path = Path('/Users/wattd/Downloads/267132177-Posada-Mexicana-Tradicional.xml')

tree = ET.parse(source_path)
root = tree.getroot()

# 1. Root & Header Metadata
# Remove any existing work or identification to ensure valid schema ordering
for child in list(root):
    if child.tag in ('work', 'identification', 'part-list'):
        root.remove(child)

# <work>
work = ET.Element('work')
work_title = ET.SubElement(work, 'work-title')
work_title.text = "Posada Mexicana"
root.insert(0, work)

# <identification> MUST have <creator> before <encoding> per MusicXML schema:
# ( creator*, rights*, encoding?, source?, relation*, miscellaneous? )
ident = ET.Element('identification')
creator = ET.SubElement(ident, 'creator', type='composer')
creator.text = "Tradicional"

encoding = ET.SubElement(ident, 'encoding')
software = ET.SubElement(encoding, 'software')
software.text = "Halbestunde (repaired)"
enc_date = ET.SubElement(encoding, 'encoding-date')
enc_date.text = "2026-09-15"

root.insert(1, ident)

# 2. Rebuild part-list with SATB names, bracket group, and explicit vocal sound IDs
plist = ET.Element('part-list')
pg_start = ET.SubElement(plist, 'part-group', number='1', type='start')
ET.SubElement(pg_start, 'group-symbol').text = 'bracket'
ET.SubElement(pg_start, 'group-barline').text = 'yes'

# For P4, use "Bass Voice" to prevent Sibelius from assigning Double Bass / Bass Guitar
parts_meta = [
    ('P1', 'Soprano', 'Soprano', 'S', 'voice.soprano', '1'),
    ('P2', 'Alto', 'Alto', 'A', 'voice.alto', '2'),
    ('P3', 'Tenor', 'Tenor', 'T', 'voice.tenor', '3'),
    ('P4', 'Bass Voice', 'Bass', 'B', 'voice.bass', '4'),
]

for pid, pname, disp_name, abbr, sound_id, chan in parts_meta:
    sp = ET.SubElement(plist, 'score-part', id=pid)
    ET.SubElement(sp, 'part-name').text = pname
    if disp_name != pname:
        pnd = ET.SubElement(sp, 'part-name-display')
        ET.SubElement(pnd, 'display-text').text = disp_name
    ET.SubElement(sp, 'part-abbreviation').text = abbr
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

# 3. Clean and fix each part
parts = {p.attrib['id']: p for p in root.findall('part')}

# Leave layout breaks unset so Sibelius can choose system and page flow from
# the document setup, lyric spacing, and engraving rules. Add only deliberate
# phrase-level breaks here after visual review.
breaks = {}

implicit_measures = {18, 28, 29, 34, 38}

for pid, part in parts.items():
    for m in part.findall('measure'):
        mnum = int(m.attrib['number'])
        
        # Incomplete / pickup measures
        if mnum in implicit_measures:
            m.attrib['implicit'] = 'yes'
        elif 'implicit' in m.attrib:
            del m.attrib['implicit']
            
        # Breaks
        if mnum in breaks:
            btype = breaks[mnum]
            pr = m.find('print')
            if pr is None:
                pr = ET.Element('print')
                m.insert(0, pr)
            if btype == 'system':
                pr.attrib['new-system'] = 'yes'
            elif btype == 'page':
                pr.attrib['new-page'] = 'yes'
                
        # Fix alter tags: replace '1.0' with integer '1'
        for alt in m.findall('.//alter'):
            if alt.text == '1.0':
                alt.text = '1'

        # Fix barlines: remove old barlines to recreate cleanly
        for bl in list(m.findall('barline')):
            m.remove(bl)

        if mnum == 17:
            # End of Section 1
            bl = ET.SubElement(m, 'barline', location='right')
            ET.SubElement(bl, 'bar-style').text = 'light-light'
        elif mnum == 28:
            # End of Section 2
            bl = ET.SubElement(m, 'barline', location='right')
            ET.SubElement(bl, 'bar-style').text = 'light-light'
        elif mnum == 30:
            # Start of Verse repeat ("Juana no te dilates")
            bl = ET.SubElement(m, 'barline', location='left')
            ET.SubElement(bl, 'bar-style').text = 'heavy-light'
            ET.SubElement(bl, 'repeat', direction='forward')
        elif mnum == 33:
            # End of Verse repeat
            bl = ET.SubElement(m, 'barline', location='right')
            ET.SubElement(bl, 'bar-style').text = 'light-heavy'
            ET.SubElement(bl, 'repeat', direction='backward')
        elif mnum == 38:
            # End of Chorus
            bl = ET.SubElement(m, 'barline', location='right')
            ET.SubElement(bl, 'bar-style').text = 'light-light'
        elif mnum == 39:
            # Start of Section 4 (Dale, dale, dale)
            bl = ET.SubElement(m, 'barline', location='left')
            ET.SubElement(bl, 'bar-style').text = 'heavy-light'
            ET.SubElement(bl, 'repeat', direction='forward')
        elif mnum == 46:
            # First ending of Section 4
            bl = ET.SubElement(m, 'barline', location='right')
            ET.SubElement(bl, 'bar-style').text = 'light-heavy'
            ET.SubElement(bl, 'repeat', direction='backward')
        elif mnum == 47:
            # Second phrase of Section 4
            bl = ET.SubElement(m, 'barline', location='left')
            ET.SubElement(bl, 'bar-style').text = 'heavy-light'
            ET.SubElement(bl, 'repeat', direction='forward')
        elif mnum == 50:
            # Final barline of piece
            bl = ET.SubElement(m, 'barline', location='right')
            ET.SubElement(bl, 'bar-style').text = 'light-heavy'
            ET.SubElement(bl, 'repeat', direction='backward')

        # Remove existing directions from measures (we will add clean tempo/dynamics)
        for d in list(m.findall('direction')):
            m.remove(d)

        # Fix Measure 48: Half note -> Quarter note + Quarter rest
        if mnum == 48:
            notes = m.findall('note')
            if len(notes) == 1 and notes[0].find('rest') is None:
                n0 = notes[0]
                n0.find('duration').text = '2'
                n0.find('type').text = 'quarter'
                for l in list(n0.findall('lyric')):
                    n0.remove(l)
                rest_note = ET.Element('note')
                ET.SubElement(rest_note, 'rest')
                ET.SubElement(rest_note, 'duration').text = '2'
                ET.SubElement(rest_note, 'voice').text = '1'
                ET.SubElement(rest_note, 'type').text = 'quarter'
                m.append(rest_note)

        # Fix Measure 17 Bass: F#3 -> D3
        if pid == 'P4' and mnum == 17:
            n = m.find('note')
            p = n.find('pitch')
            p.find('step').text = 'D'
            p.find('octave').text = '3'
            alt = p.find('alter')
            if alt is not None:
                p.remove(alt)
            acc = n.find('accidental')
            if acc is not None:
                n.remove(acc)

        # Clear existing lyrics from all notes (we will inject clean ones)
        for n in m.findall('note'):
            for l in list(n.findall('lyric')):
                n.remove(l)

# 4. Add Direction / Tempo / Dynamics
p1 = parts['P1']

def add_words_dir(m, words_text, tempo_val=None, default_y="30", italic=True):
    d = ET.Element('direction', placement='above')
    dt = ET.SubElement(d, 'direction-type')
    w = ET.SubElement(dt, 'words', **{'default-y': default_y, 'font-weight': 'bold'})
    if italic:
        w.attrib['font-style'] = 'italic'
    w.text = words_text
    if tempo_val:
        ET.SubElement(d, 'sound', tempo=str(tempo_val))
    m.insert(0, d)

def add_dynamic(m, dyn_type, default_y="-70"):
    d = ET.Element('direction', placement='below')
    dt = ET.SubElement(d, 'direction-type')
    dyn = ET.SubElement(dt, 'dynamics', **{'default-y': default_y})
    ET.SubElement(dyn, dyn_type)
    m.insert(0, d)

# m.1: "Andante Molto", initial volume mf across ALL 4 parts (Soprano, Alto, Tenor, Bass)
add_words_dir(p1.find("measure[@number='1']"), "Andante Molto", tempo_val=90)
for pid in ['P1', 'P2', 'P3', 'P4']:
    add_dynamic(parts[pid].find("measure[@number='1']"), 'mf')

# m.18: "Moderato", f across all parts
add_words_dir(p1.find("measure[@number='18']"), "Moderato", tempo_val=100)
for pid in ['P1', 'P2', 'P3', 'P4']:
    add_dynamic(parts[pid].find("measure[@number='18']"), 'f')

# m.29: "Allegro"
add_words_dir(p1.find("measure[@number='29']"), "Allegro", tempo_val=120)

# m.34: "Coro"
add_words_dir(p1.find("measure[@number='34']"), "Coro", italic=False)

# m.39: "Molto Allegro"
add_words_dir(p1.find("measure[@number='39']"), "Molto Allegro", tempo_val=140)

# 5. Inject Clean Spanish Lyrics for P1 (Soprano), P2 (Alto), P3 (Tenor)
def set_lyric(note, syllabic, text, number="1", extend=False):
    lyr = ET.SubElement(note, 'lyric', number=str(number))
    ET.SubElement(lyr, 'syllabic').text = syllabic
    ET.SubElement(lyr, 'text').text = text
    if extend:
        ET.SubElement(lyr, 'extend')

# --- SOPRANO (P1) LYRICS ---
p1_lyrics = [
    # Section 1: mm. 1-17 (3/4, Andante Molto)
    (1, 0, 'single', 'En', 1, True),
    (1, 2, 'begin', 'nom', 1, False),
    (2, 0, 'end', 'bre', 1, True),
    (2, 2, 'single', 'del', 1, False),
    (3, 0, 'begin', 'cie', 1, True),
    (4, 0, 'end', 'lo,', 1, False),
    (5, 0, 'single', 'os', 1, True),
    (5, 2, 'begin', 'pi', 1, False),
    (6, 0, 'end', 'do', 1, True),
    (6, 2, 'begin', 'po', 1, False),
    (7, 0, 'middle', 'sa', 1, True),
    (8, 0, 'end', 'da,', 1, False),
    (9, 0, 'single', 'pues', 1, True),
    (9, 2, 'single', 'no', 1, False),
    (10, 0, 'begin', 'pue', 1, False),
    (10, 1, 'end', 'de an', 1, False),
    (11, 0, 'single', 'dar', 1, True),
    (13, 0, 'single', 'mi', 1, True),
    (13, 2, 'begin', 'es', 1, False),
    (14, 0, 'middle', 'po', 1, True),
    (14, 2, 'end', 'sa a', 1, False),
    (15, 0, 'begin', 'ma', 1, True),
    (17, 0, 'end', 'da.', 1, False),

    # Section 2: mm. 18-28 (4/4, Moderato)
    (18, 0, 'begin', 'En', 1, False),
    (18, 1, 'end', 'tren,', 1, False),
    (19, 0, 'begin', 'san', 1, False),
    (19, 1, 'end', 'tos', 1, False),
    (19, 2, 'begin', 'pe', 1, False),
    (19, 3, 'middle', 're', 1, False),
    (20, 0, 'middle', 'gri', 1, False),
    (20, 1, 'end', 'nos,', 1, False),
    (20, 2, 'begin', 'pe', 1, False),
    (20, 3, 'middle', 're', 1, False),
    (21, 0, 'middle', 'gri', 1, False),
    (21, 1, 'end', 'nos,', 1, False),
    (21, 2, 'begin', 're', 1, False),
    (21, 3, 'middle', 'ci', 1, False),
    (22, 0, 'end', 'ban', 1, False),
    (22, 1, 'begin', 'es', 1, False),
    (22, 2, 'end', 'te', 1, False),
    (22, 3, 'begin', 'rin', 1, False),
    (23, 0, 'end', 'cón,', 1, False),
    (23, 1, 'single', 'no', 1, False),
    (23, 2, 'single', 'de es', 1, False),
    (24, 0, 'single', 'ta', 1, False),
    (24, 1, 'begin', 'po', 1, False),
    (24, 2, 'end', 'bre', 1, False),
    (24, 3, 'begin', 'mo', 1, False),
    (25, 0, 'middle', 'ra', 1, False),
    (25, 1, 'end', 'da,', 1, False),
    (25, 2, 'single', 'mi', 1, False),
    (25, 3, 'begin', 'mo', 1, False),
    (26, 0, 'middle', 'ra', 1, False),
    (26, 1, 'end', 'da,', 1, False),
    (26, 2, 'begin', 'si', 1, False),
    (26, 3, 'end', 'no', 1, False),
    (27, 0, 'single', 'de', 1, False),
    (27, 1, 'single', 'mi', 1, False),
    (27, 2, 'begin', 'co', 1, False),
    (27, 3, 'middle', 'ra', 1, False),
    (28, 0, 'end', 'zón.', 1, False),

    # Section 3: mm. 29-38 (6/8, Allegro)
    # Pickup m.29
    (29, 0, 'begin', 'Án', 1, False),
    (29, 1, 'middle', 'da', 1, False),
    (29, 2, 'end', 'le', 1, False),
    # Verse 1 (number=1)
    (30, 0, 'begin', 'Jua', 1, False),
    (30, 1, 'end', 'na,', 1, False),
    (30, 2, 'single', 'no', 1, False),
    (30, 3, 'single', 'te', 1, False),
    (30, 4, 'begin', 'di', 1, False),
    (31, 0, 'middle', 'la', 1, False),
    (31, 1, 'end', 'tes', 1, False),
    (31, 2, 'single', 'con', 1, False),
    (31, 3, 'single', 'la', 1, False),
    (31, 4, 'begin', 'ca', 1, False),
    (32, 0, 'middle', 'nas', 1, False),
    (32, 1, 'end', 'ta', 1, False),
    (32, 2, 'single', 'de', 1, False),
    (32, 3, 'single', 'los', 1, False),
    (32, 4, 'begin', 'ca', 1, False),
    (32, 5, 'middle', 'ca', 1, False),
    (33, 0, 'middle', 'hua', 1, False),
    (33, 1, 'end', 'tes.', 1, False),
    # Verse 2 (number=2)
    (30, 0, 'begin', 'cru', 2, False),
    (30, 1, 'end', 'da,', 2, False),
    (30, 2, 'begin', 'cas', 2, False),
    (30, 3, 'middle', 'ta', 2, False),
    (30, 4, 'middle', 'ña', 2, False),
    (31, 0, 'end', 'da,', 2, False),
    (31, 1, 'begin', 'den', 2, False),
    (31, 2, 'end', 'le', 2, False),
    (31, 3, 'single', 'de', 2, False),
    (31, 4, 'begin', 'pa', 2, False),
    (32, 0, 'end', 'los', 2, False),
    (32, 1, 'single', 'al', 2, False),
    (32, 2, 'single', 'de', 2, False),
    (32, 3, 'single', 'la', 2, False),
    (32, 4, 'begin', 'po', 2, False),
    (32, 5, 'middle', 'sa', 2, False),
    (33, 0, 'end', 'da.', 2, False),
    (33, 2, 'begin', 'cas', 2, False),
    (33, 3, 'middle', 'ta', 2, False),
    (33, 4, 'end', 'ña', 2, False),
    # Chorus mm. 34-38
    (34, 0, 'single', 'Yo', 1, False),
    (34, 1, 'single', 'no', 1, False),
    (34, 2, 'begin', 'quie', 1, False),
    (35, 0, 'end', 'ro o', 1, False),
    (35, 1, 'end', 'ro,', 1, False),
    (35, 2, 'single', 'ni', 1, False),
    (35, 3, 'begin', 'quie', 1, False),
    (35, 4, 'end', 'ro', 1, False),
    (36, 0, 'begin', 'pla', 1, False),
    (36, 1, 'end', 'ta,', 1, False),
    (36, 2, 'single', 'yo', 1, False),
    (36, 3, 'single', 'lo', 1, False),
    (36, 4, 'single', 'que', 1, False),
    (37, 0, 'begin', 'quie', 1, False),
    (37, 1, 'end', 'ro es', 1, False),
    (37, 2, 'begin', 'que', 1, False),
    (37, 3, 'end', 'brar', 1, False),
    (37, 4, 'single', 'la', 1, False),
    (37, 5, 'begin', 'pi', 1, False),
    (38, 0, 'middle', 'ña', 1, False),
    (38, 1, 'end', 'ta.', 1, False),

    # Section 4: mm. 39-50 (2/4, Molto Allegro)
    (39, 0, 'begin', 'da', 1, False),
    (39, 1, 'end', 'le,', 1, False),
    (39, 2, 'begin', 'da', 1, False),
    (39, 3, 'end', 'le,', 1, False),
    (40, 0, 'begin', 'da', 1, False),
    (40, 1, 'end', 'le,', 1, False),
    (41, 0, 'single', 'no', 1, False),
    (41, 1, 'begin', 'pier', 1, False),
    (41, 2, 'end', 'das', 1, False),
    (41, 3, 'single', 'el', 1, False),
    (42, 0, 'begin', 'ti', 1, False),
    (42, 1, 'end', 'no,', 1, False),
    (43, 0, 'begin', 'mi', 1, False),
    (43, 1, 'end', 'de', 1, False),
    (43, 2, 'single', 'la', 1, False),
    (43, 3, 'begin', 'dis', 1, False),
    (44, 0, 'middle', 'tan', 1, False),
    (44, 1, 'end', 'cia', 1, False),
    (45, 0, 'single', 'que hay', 1, False),
    (45, 1, 'single', 'en', 1, False),
    (45, 2, 'single', 'el', 1, False),
    (45, 3, 'begin', 'ca', 1, False),
    (46, 0, 'middle', 'mi', 1, False),
    (46, 1, 'end', 'no.', 1, False),
    (47, 0, 'single', 'que', 1, False),
    (47, 1, 'single', 'si', 1, False),
    (47, 2, 'single', 'no', 1, False),
    (47, 3, 'single', 'le', 1, False),
    (48, 0, 'single', 'das,', 1, False),
    (49, 0, 'single', 'de un', 1, False),
    (49, 1, 'begin', 'pa', 1, False),
    (49, 2, 'end', 'lo', 1, False),
    (49, 3, 'begin', 'te em', 1, False),
    (50, 0, 'middle', 'pi', 1, False),
    (50, 1, 'end', 'no.', 1, False),
]

for mnum, nidx, syllabic, txt, vnum, ext in p1_lyrics:
    m = parts['P1'].find(f"measure[@number='{mnum}']")
    notes = [n for n in m.findall('note') if n.find('rest') is None]
    if nidx < len(notes):
        set_lyric(notes[nidx], syllabic, txt, number=vnum, extend=ext)

# --- ALTO (P2) LYRICS ---
p2_lyrics_s1 = [
    (1, 0, 'single', 'En', 1, True),
    (1, 2, 'begin', 'nom', 1, False),
    (2, 0, 'end', 'bre', 1, True),
    (2, 2, 'single', 'del', 1, False),
    (3, 0, 'begin', 'cie', 1, True),
    (4, 0, 'end', 'lo,', 1, False),
    (5, 0, 'single', 'os', 1, True),
    (5, 2, 'begin', 'pi', 1, False),
    (6, 0, 'end', 'do', 1, True),
    (6, 2, 'begin', 'po', 1, False),
    (7, 0, 'middle', 'sa', 1, True),
    (8, 0, 'end', 'da,', 1, False),
    (9, 0, 'single', 'pues', 1, True),
    (9, 2, 'single', 'no', 1, False),
    (10, 0, 'begin', 'pue', 1, False),
    (10, 1, 'end', 'de an', 1, False),
    (11, 0, 'single', 'dar', 1, True),
    (13, 0, 'single', 'mi', 1, False),
    (13, 1, 'begin', 'es', 1, False),
    (14, 0, 'middle', 'po', 1, True),
    (14, 2, 'end', 'sa a', 1, False),
    (15, 0, 'begin', 'ma', 1, True),
    (17, 0, 'end', 'da.', 1, False),
]

p2_lyrics = p2_lyrics_s1 + [l for l in p1_lyrics if l[0] >= 18]

for mnum, nidx, syllabic, txt, vnum, ext in p2_lyrics:
    m = parts['P2'].find(f"measure[@number='{mnum}']")
    notes = [n for n in m.findall('note') if n.find('rest') is None]
    if nidx < len(notes):
        set_lyric(notes[nidx], syllabic, txt, number=vnum, extend=ext)

# --- TENOR (P3) LYRICS ---
p3_lyrics_s1 = [
    (1, 0, 'single', 'En', 1, False),
    (1, 1, 'begin', 'nom', 1, False),
    (2, 0, 'end', 'bre', 1, False),
    (2, 1, 'single', 'del', 1, False),
    (3, 0, 'begin', 'cie', 1, True),
    (4, 0, 'end', 'lo,', 1, False),
    (5, 0, 'single', 'os', 1, False),
    (5, 1, 'begin', 'pi', 1, False),
    (6, 0, 'end', 'do', 1, False),
    (6, 1, 'begin', 'po', 1, False),
    (7, 0, 'middle', 'sa', 1, True),
    (8, 0, 'end', 'da,', 1, True),
    (9, 0, 'single', 'pues', 1, False),
    (9, 1, 'single', 'no', 1, False),
    (10, 0, 'begin', 'pue', 1, False),
    (10, 1, 'end', 'de an', 1, False),
    (11, 0, 'single', 'dar', 1, False),
]

p3_lyrics = p3_lyrics_s1 + [l for l in p1_lyrics if l[0] >= 18]

for mnum, nidx, syllabic, txt, vnum, ext in p3_lyrics:
    m = parts['P3'].find(f"measure[@number='{mnum}']")
    notes = [n for n in m.findall('note') if n.find('rest') is None]
    if nidx < len(notes):
        set_lyric(notes[nidx], syllabic, txt, number=vnum, extend=ext)

# 6. Pretty-print XML and write output
target_path = Path('/Users/wattd/Downloads/267132177-Posada-Mexicana-Tradicional.xml')
xml_str = ET.tostring(root, encoding='utf-8')
dom = minidom.parseString(xml_str)
pretty_xml = dom.toprettyxml(indent='  ', encoding='utf-8').decode('utf-8')
lines = [l for l in pretty_xml.splitlines() if l.strip()]
header = """<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 3.1 Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">"""
final_output = header + "\n" + "\n".join(lines[1:]) + "\n"

target_path.write_text(final_output, encoding='utf-8')
print("Successfully wrote updated MusicXML to:", target_path)
