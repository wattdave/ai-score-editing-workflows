"""Dorico PDF (choral layouts, see dorico_pdf.py) -> four-part SATB MusicXML.

  uv run --with pymupdf python -I dorico_pdf_musicxml.py SCORE.pdf OUT.musicxml --tempo 144 --tempo-map 35:126,117:112 \\
      [--title T] [--composer C] [--arranger A]

The PDF carries no metronome mark, so the tempo comes from --tempo / --tempo-map (bar:bpm, quarter notes).
Repeats, the segno, To Coda, D.S. al Coda and the coda are written as MusicXML jumps; Sibelius plays them in order.
Title, composer and arranger are read from the first page unless given."""
import argparse, html, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dorico_pdf as dp

TYPES = {1: ('16th', 0), 2: ('eighth', 0), 3: ('eighth', 1), 4: ('quarter', 0), 6: ('quarter', 1), 8: ('half', 0), 12: ('half', 1), 16: ('whole', 0)}
PARTNAMES = ['Soprano', 'Alto', 'Tenor', 'Bass']
CLEFS = {0: '<clef><sign>G</sign><line>2</line></clef>', 1: '<clef><sign>G</sign><line>2</line></clef>',
         2: '<clef><sign>G</sign><line>2</line><clef-octave-change>-1</clef-octave-change></clef>', 3: '<clef><sign>F</sign><line>4</line></clef>'}


def pitch_xml(m, fifths):
    names = ['C', 'Db', 'D', 'Eb', 'E', 'F', 'Gb', 'G', 'Ab', 'A', 'Bb', 'B'] if fifths < 0 else ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
    n = names[m % 12]
    alter = -1 if len(n) > 1 and n[1] == 'b' else 1 if len(n) > 1 else 0
    return f'<pitch><step>{n[0]}</step>' + (f'<alter>{alter}</alter>' if alter else '') + f'<octave>{m // 12 - 1}</octave></pitch>'


def rest_xml(dur16, measure=False):
    if measure: return f'<note><rest measure="yes"/><duration>{dur16}</duration><voice>1</voice></note>'
    out, rem = '', dur16
    for d_ in (16, 12, 8, 6, 4, 3, 2, 1):
        while rem >= d_:
            ty, dot = TYPES[d_]
            out += f'<note><rest/><duration>{d_}</duration><voice>1</voice><type>{ty}</type>' + ('<dot/>' if dot else '') + '</note>'
            rem -= d_
    return out


def build_musicxml(pdf, tempo=144, tempo_map=None, title=None, composer=None, arranger=None, log=print):
    score = dp.assemble(pdf)
    lyr = dp.attach_lyrics(score)
    parts = dp.split_parts(score)
    dirs = dp.directions(score)
    t0, c0, a0 = dp.metadata(score)
    title, composer, arranger = title or t0, composer or c0, arranger or a0
    nbars = score['nbars']
    tempos = {1: tempo, **(tempo_map or {})}
    ferm = score['fermatas']

    def part_xml(pi_):
        byb = {}
        for n in parts[pi_]: byb.setdefault(n['bar'], []).append(n)
        o = [f'<part id="P{pi_ + 1}">']
        prevkey = prevtime = None
        for b in range(1, nbars + 1):
            fifths = score['key'][b]; ts = score['time'][b]; barlen = 16 * ts[0] // ts[1]
            ns = sorted(byb.get(b, []), key=lambda n: (n['onset'], -n['midi']))
            o.append(f'<measure number="{b}">')
            if b in score['rep_start']: o.append('<barline location="left"><bar-style>heavy-light</bar-style><repeat direction="forward"/></barline>')
            if b == 1 or prevkey != fifths or prevtime != ts:
                att = '<divisions>4</divisions>'
                if prevkey != fifths: att += f'<key><fifths>{fifths}</fifths></key>'
                if prevtime != ts: att += f'<time><beats>{ts[0]}</beats><beat-type>{ts[1]}</beat-type></time>'
                if b == 1: att += CLEFS[pi_]
                o.append(f'<attributes>{att}</attributes>')
            prevkey, prevtime = fifths, ts
            for item in dirs.get(b, []):
                if item[0] == 'words' and pi_ == 0: o.append(f'<direction placement="above"><direction-type><words>{html.escape(item[1])}</words></direction-type></direction>')
                elif item[0] == 'rehearsal' and pi_ == 0: o.append(f'<direction placement="above"><direction-type><rehearsal>{html.escape(item[1])}</rehearsal></direction-type></direction>')
                elif item[0] == 'segno': o.append('<direction placement="above"><direction-type><segno/></direction-type><sound segno="segno"/></direction>')
                elif item[0] == 'coda': o.append('<direction placement="above"><direction-type><coda/></direction-type><sound coda="coda"/></direction>')
            if b in tempos and pi_ == 0:
                o.append(f'<direction placement="above"><direction-type><metronome><beat-unit>quarter</beat-unit><per-minute>{tempos[b]}</per-minute></metronome></direction-type><sound tempo="{tempos[b]}"/></direction>')
            t = 0; last_on = None
            for n in ns:
                on = n['onset'] // 64
                chord = last_on == on
                if not chord:
                    if on > t: o.append(rest_xml(on - t)); t = on
                    if on < t: continue
                d16 = n['dur'] // 64
                if d16 not in TYPES: log(f'odd duration {d16} in bar {b}'); continue
                ty, dot = TYPES[d16]
                s = '<note>' + ('<chord/>' if chord else '') + pitch_xml(n['midi'], fifths) + f'<duration>{d16}</duration>'
                if n['tie_stop']: s += '<tie type="stop"/>'
                if n['tie']: s += '<tie type="start"/>'
                s += f'<voice>1</voice><type>{ty}</type>' + ('<dot/>' if dot else '')
                nt = ('<tied type="stop"/>' if n['tie_stop'] else '') + ('<tied type="start"/>' if n['tie'] else '')
                sp = n['staff']['sp']
                if any(f[0] == id(n['staff']) and f[1] == b and abs(f[2] - n['x']) < 2.4 * sp for f in ferm) and not chord: nt += '<fermata/>'
                if nt: s += f'<notations>{nt}</notations>'
                L = lyr.get((id(n['staff']), n['bar'], n['onset']))
                if L and not chord: s += f'<lyric number="1"><syllabic>{L[1]}</syllabic><text>{html.escape(L[0])}</text></lyric>'
                o.append(s + '</note>')
                if not chord: t += d16; last_on = on
            if t < barlen: o.append(rest_xml(barlen - t, measure=(t == 0)))
            elif t > barlen: log(f'bar {b} of {PARTNAMES[pi_]} is overfull: {t} of {barlen}')
            if any(it[0] == 'tocoda' for it in dirs.get(b, [])):
                o.append('<direction placement="above"><direction-type><words>To Coda</words></direction-type><sound tocoda="coda"/></direction>')
            if any(it[0] == 'dsalcoda' for it in dirs.get(b, [])):
                o.append('<direction placement="above"><direction-type><words>D.S. al Coda</words></direction-type><sound dalsegno="segno"/></direction>')
            if b in score['rep_end']: o.append('<barline location="right"><bar-style>light-heavy</bar-style><repeat direction="backward"/></barline>')
            o.append('</measure>')
        o.append('</part>')
        return '\n'.join(o)

    head = ('<?xml version="1.0" encoding="UTF-8"?><score-partwise version="3.0"><work><work-title>' + html.escape(title) + '</work-title></work>'
            '<identification><creator type="composer">' + html.escape(composer) + '</creator><creator type="arranger">' + html.escape(arranger) + '</creator></identification><part-list>'
            + ''.join(f'<score-part id="P{i + 1}"><part-name>{n}</part-name></score-part>' for i, n in enumerate(PARTNAMES)) + '</part-list>')
    return head + '\n'.join(part_xml(i) for i in range(4)) + '</score-partwise>', nbars


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('pdf'); ap.add_argument('out')
    ap.add_argument('--tempo', type=int, default=144, help='quarter-note tempo at bar 1')
    ap.add_argument('--tempo-map', default='', help='bar:bpm,bar:bpm tempo changes')
    ap.add_argument('--title'); ap.add_argument('--composer'); ap.add_argument('--arranger')
    a = ap.parse_args(argv)
    tm = {int(k): int(v) for k, v in (kv.split(':') for kv in a.tempo_map.split(',') if kv)}
    xml, nbars = build_musicxml(a.pdf, a.tempo, tm, a.title, a.composer, a.arranger)
    open(a.out, 'w').write(xml)
    print('wrote', a.out, nbars, 'bars')


if __name__ == '__main__':
    main()
