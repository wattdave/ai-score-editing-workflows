"""Dorico PDF (2-staff choral layout, see dorico_pdf.py) -> four-part SATB MusicXML.

  uv run --with pymupdf python -I dorico_pdf_musicxml.py SCORE.pdf OUT.musicxml --tempo 144 --tempo-map 35:126,117:112 \
      [--title T] [--composer C] [--arranger A]

The PDF carries no metronome mark, so the tempo comes from --tempo / --tempo-map (bar:bpm, quarter notes).
Repeats, the segno, To Coda, D.S. al Coda and the coda are written as MusicXML jumps; Sibelius plays them in order."""
import sys, os, html, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dorico_pdf as dpdf
ap = argparse.ArgumentParser(); ap.add_argument('pdf'); ap.add_argument('out')
ap.add_argument('--tempo', type=int, default=144); ap.add_argument('--tempo-map', default='')
ap.add_argument('--title', default='Carol of the Bells'); ap.add_argument('--composer', default='Mykola Leontovych'); ap.add_argument('--arranger', default='Walter John Bankovitch')
a = ap.parse_args()
pdf = a.pdf
bars, meta = dpdf.assemble(pdf); res = dpdf.build(pdf)
lyr = dpdf.attach_lyrics(pdf, bars, meta, res)
parts = dpdf.assign_parts(pdf, meta, res)
dirs = dpdf.directions(pdf, meta, res)
NBARS = max(meta['key'])
TYPES = {1: ('16th', 0), 2: ('eighth', 0), 3: ('eighth', 1), 4: ('quarter', 0), 6: ('quarter', 1), 8: ('half', 0), 12: ('half', 1), 16: ('whole', 0)}
STEPN = 'CDEFGAB'
def pitch_xml(m, fifths):
    # spell by key: prefer flats in flat keys, sharps otherwise
    names_f = ['C', 'Db', 'D', 'Eb', 'E', 'F', 'Gb', 'G', 'Ab', 'A', 'Bb', 'B']
    names_s = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
    n = (names_f if fifths < 0 else names_s)[m % 12]
    step = n[0]; alter = -1 if len(n) > 1 and n[1] == 'b' else 1 if len(n) > 1 else 0
    return f'<pitch><step>{step}</step>' + (f'<alter>{alter}</alter>' if alter else '') + f'<octave>{m // 12 - 1}</octave></pitch>'
tempos = {1: a.tempo}
for kv in filter(None, a.tempo_map.split(',')):
    b_, t_ = kv.split(':'); tempos[int(b_)] = int(t_)
PARTNAMES = ['Soprano', 'Alto', 'Tenor', 'Bass']
rows = {0: 0, 1: 0, 2: 1, 3: 1}   # part -> staff row (lyrics)
def rest_xml(dur16, measure=False):
    if measure: return '<note><rest measure="yes"/><duration>%d</duration><voice>1</voice></note>' % dur16
    out = ''
    # split into representable durations
    rem = dur16
    for d_ in (16, 12, 8, 6, 4, 3, 2, 1):
        while rem >= d_:
            ty, dot = TYPES[d_]
            out += f'<note><rest/><duration>{d_}</duration><voice>1</voice><type>{ty}</type>' + ('<dot/>' if dot else '') + '</note>'
            rem -= d_
    return out
def part_xml(pi_):
    notes = parts[pi_]
    byb = {}
    for n in notes: byb.setdefault(n['bar'], []).append(n)
    o = [f'<part id="P{pi_+1}">']
    prevkey = None; prevtime = None
    b = 1
    while b <= NBARS:
        fifths = meta['key'][b]; ts = meta['time'][b]; barlen = 16 * ts[0] // ts[1]
        ns = sorted(byb.get(b, []), key=lambda n: (n['onset'], -n['midi']))
        # multi-measure rests of the print are written out as single bars here
        o.append(f'<measure number="{b}">')
        if b in meta.get('rep_start', ()): o.append('<barline location="left"><bar-style>heavy-light</bar-style><repeat direction="forward"/></barline>')
        att = ''
        if prevkey != fifths or prevtime != ts or b == 1:
            att += '<divisions>4</divisions>'
            if prevkey != fifths: att += f'<key><fifths>{fifths}</fifths></key>'
            if prevtime != ts: att += f'<time><beats>{ts[0]}</beats><beat-type>{ts[1]}</beat-type></time>'
            if b == 1:
                att += {0: '<clef><sign>G</sign><line>2</line></clef>', 1: '<clef><sign>G</sign><line>2</line></clef>', 2: '<clef><sign>G</sign><line>2</line><clef-octave-change>-1</clef-octave-change></clef>', 3: '<clef><sign>F</sign><line>4</line></clef>'}[pi_]
            o.append(f'<attributes>{att}</attributes>')
        prevkey, prevtime = fifths, ts
        # directions
        for item in dirs.get(b, []):
            if item[0] == 'words' and pi_ == 0: o.append(f'<direction placement="above"><direction-type><words>{html.escape(item[1])}</words></direction-type></direction>')
            elif item[0] == 'rehearsal' and pi_ == 0: o.append(f'<direction placement="above"><direction-type><rehearsal>{html.escape(item[1])}</rehearsal></direction-type></direction>')
            elif item[0] == 'segno': o.append(f'<direction placement="above"><direction-type><segno/></direction-type><sound segno="segno"/></direction>')
            elif item[0] == 'coda': o.append(f'<direction placement="above"><direction-type><coda/></direction-type><sound coda="coda"/></direction>')
        if b in tempos and pi_ == 0:
            o.append(f'<direction placement="above"><direction-type><metronome><beat-unit>quarter</beat-unit><per-minute>{tempos[b]}</per-minute></metronome></direction-type><sound tempo="{tempos[b]}"/></direction>')
        t = 0
        for n in ns:
            if n['onset'] // 64 > t: o.append(rest_xml(n['onset'] // 64 - t)); t = n['onset'] // 64
            if n['onset'] // 64 < t: continue   # overlapping duplicate (should not happen)
            d16 = n['dur'] // 64
            if d16 not in TYPES: print('odd duration', b, d16); continue
            ty, dot = TYPES[d16]
            s = '<note>' + pitch_xml(n['midi'], fifths) + f'<duration>{d16}</duration>'
            if n.get('tie_stop'): s += '<tie type="stop"/>'
            if n['tie']: s += '<tie type="start"/>'
            s += f'<voice>1</voice><type>{ty}</type>' + ('<dot/>' if dot else '')
            nt = ('<tied type="stop"/>' if n.get('tie_stop') else '') + ('<tied type="start"/>' if n['tie'] else '')
            fx = [it for it in dirs.get(b, []) if it[0] == 'fermata' and abs(it[1] - n['x']) < 12]
            if fx: nt += '<fermata/>'
            if nt: s += f'<notations>{nt}</notations>'
            L = lyr.get((rows[pi_], n['bar'], n['onset']))
            if L: s += f'<lyric number="1"><syllabic>{L[1]}</syllabic><text>{html.escape(L[0])}</text></lyric>'
            o.append(s + '</note>'); t += d16
        if t < barlen: o.append(rest_xml(barlen - t, measure=(t == 0)))
        elif t > barlen: print('BAR OVERFULL', PARTNAMES[pi_], b, t, barlen)
        if any(it[0] == 'tocoda' for it in dirs.get(b, [])) and pi_ == 0 or any(it[0] == 'tocoda' for it in dirs.get(b, [])):
            o.append('<direction placement="above"><direction-type><words>To Coda</words></direction-type><sound tocoda="coda"/></direction>')
        if any(it[0] == 'dsalcoda' for it in dirs.get(b, [])):
            o.append('<direction placement="above"><direction-type><words>D.S. al Coda</words></direction-type><sound dalsegno="segno"/></direction>')
        if b in meta.get('rep_end', ()): o.append('<barline location="right"><bar-style>light-heavy</bar-style><repeat direction="backward"/></barline>')
        o.append('</measure>'); b += 1
    o.append('</part>'); return '\n'.join(o)
head = ('<?xml version="1.0" encoding="UTF-8"?><score-partwise version="3.0"><work><work-title>' + html.escape(a.title) + '</work-title></work>'
        '<identification><creator type="composer">' + html.escape(a.composer) + '</creator><creator type="arranger">' + html.escape(a.arranger) + '</creator></identification><part-list>'
        + ''.join(f'<score-part id="P{i+1}"><part-name>{n}</part-name></score-part>' for i, n in enumerate(PARTNAMES)) + '</part-list>')
open(a.out, 'w').write(head + '\n'.join(part_xml(i) for i in range(4)) + '</score-partwise>')
print('wrote', a.out, NBARS, 'bars')
