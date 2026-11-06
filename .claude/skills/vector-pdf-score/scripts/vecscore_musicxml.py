"""Build MusicXML from a Sibelius-exported vector PDF using vecscore.py.

  uv run --with pymupdf python -I vecscore_musicxml.py SCORE.pdf OUT.musicxml \\
      --parts Soprano,Alto,Tenor,Bass --clefs G,G,G8,F --key 2 --time 4/4 --tempo 60 \\
      [--title T] [--composer C] [--override bars.json] [--copy-lyrics 1:2]

Ties come from curve drawings that start on a note and end on the next note of the same pitch.
Lyrics are matched to notes by position (greedy, nearest first). A bar whose events do not add up
(for example two voices on one staff) is reported as BAR SUM and must be given with --override.
Tenor staves written with a treble-8vb clef (G8) are written one octave lower: MusicXML pitch is sounding pitch.
Accidentals (#, b, natural) are read and held for the rest of the bar. Not handled: tuplets, grace notes,
repeats, dynamics and text."""
import argparse, html, json, re, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pymupdf
import vecscore as v

ap = argparse.ArgumentParser()
ap.add_argument('pdf'); ap.add_argument('out')
ap.add_argument('--parts', default='Soprano,Alto,Tenor,Bass')
ap.add_argument('--clefs', default='G,G,G8,F')
ap.add_argument('--key', type=int, default=0, help='key signature as fifths (2 = D major, -3 = E flat major)')
ap.add_argument('--time', default='4/4')
ap.add_argument('--time-changes', default='', help='measure:meter list where the time signature changes, e.g. "8:3/2,11:4/4" (measure numbers as in the output)')
ap.add_argument('--tempo', type=int, default=0, help='quarter-note tempo, 0 = none')
ap.add_argument('--title', default=''); ap.add_argument('--composer', default='')
ap.add_argument('--override', help='JSON file: [{"page":P,"sys":S,"part":K,"bar":B,"voices":[[{"p":["F3"],"dur":4,"x":418.8}, ...], ...]}]')
ap.add_argument('--copy-lyrics', action='append', default=[], help='FROM:TO part indexes: copy lyrics onto a staff that has none in a system')
ap.add_argument('--skip-words', default='p,mp,mf,pp,ppp,f,ff,fff,rit.,rall.,accel.,cresc.,dim.,poco,retenuto,legato,staccato,Broad,Allegro,Andante,Moderato,Adagio', help='lyric rows to ignore (comma list); words of one letter are kept unless listed')
a = ap.parse_args()
PARTS = a.parts.split(','); CLEFS = a.clefs.split(','); NP = len(PARTS)
STEPN = 'CDEFGAB'
SHARPS, FLATS = 'FCGDAEB', 'BEADGCF'
altered = {s_: 1 for s_ in SHARPS[:a.key]} if a.key > 0 else {s_: -1 for s_ in FLATS[:-a.key]}
beats, beat_type = map(int, a.time.split('/')); BAR = 16 * beats // beat_type
TC = {int(m_): tuple(map(int, t_.split('/'))) for m_, t_ in (x_.split(':') for x_ in a.time_changes.split(',') if x_)}
def meter_at(num):
    cur = (beats, beat_type)
    for m_ in sorted(TC):
        if m_ <= num: cur = TC[m_]
    return cur
def bar_at(num): return 16 * meter_at(num)[0] // meter_at(num)[1]

sts = v.parse(a.pdf, NP, tuple(CLEFS))

def _fix(sts):
    by_sys = {}
    for s_ in sts: by_sys.setdefault((s_['page'], s_['sys']), []).append(s_)
    for (pg_, sy_), group in by_sys.items():
        for s_ in group:      # (b) empty first bar made by a repeat-start barline just after the clef and key
            if s_['bars'] and not s_['bars'][0]:
                s_['bars'].pop(0); s_['edges'].pop(0); s_['marks'] = {k - 1: m for k, m in s_['marks'].items() if k >= 1}; s_['repeat_start'] = True
        for s_ in group:      # (a) a barline other staves of the system do not have (a bracket): merge its two bars
            others = [o for o in group if o is not s_]
            i = 1
            while i < len(s_['edges']) - 1 and i < len(s_['bars']):
                x = s_['edges'][i]
                if others and all(not any(abs(x - e) < 3 for e in o['edges']) for o in others):
                    s_['bars'][i - 1] = s_['bars'][i - 1] + s_['bars'].pop(i); s_['edges'].pop(i)
                    s_['marks'] = {(k if k < i else k - 1): m for k, m in s_['marks'].items()}
                else: i += 1
        for s_ in group:      # (c) notes a second apart sit side by side: same duration, close x -> one chord
            for b in s_['bars']:
                if sum(e['dur'] for e in b) == BAR: continue
                b.sort(key=lambda e: e['x']); k_ = 0
                while k_ + 1 < len(b):
                    e1, e2 = b[k_], b[k_ + 1]
                    if not e1['rest'] and not e2['rest'] and e1['dur'] == e2['dur'] and abs(e1['x'] - e2['x']) < 8:
                        e1['p'] = sorted(set(e1['p']) | set(e2['p'])); b.pop(k_ + 1)
                    else: k_ += 1
    return sts
sts = _fix(sts)
def nidx(name): return STEPN.index(name[0]) + 7 * int(name[1:])
overrides = {}
if a.override:
    for o in json.load(open(a.override)):
        overrides[(o['page'], o['sys'], o['part'], o['bar'])] = [[dict(x=e.get('x', 0), p=[nidx(n_) for n_ in e['p']], dur=e['dur'], rest=not e['p']) for e in voice] for voice in o['voices']]
systems = sorted({(s['page'], s['sys']) for s in sts})
order = {}; g = 0
first_bar = [s for s in sts if (s['page'], s['sys'], s['part']) == (systems[0][0], systems[0][1], 0)][0]['bars'][0]
pickup = sum(e['dur'] for e in first_bar) < BAR
n = 0 if pickup else 1
for pi, si in systems:
    nb = len([s for s in sts if (s['page'], s['sys'], s['part']) == (pi, si, 0)][0]['bars'])
    for bi in range(nb): order[(pi, si, bi)] = n; n += 1
first = 0 if pickup else 1
NB = n - first
def gi(num): return num - first
stream = {k: [None] * NB for k in range(NP)}; src = {k: [None] * NB for k in range(NP)}
for s in sts:
    for bi, b in enumerate(s['bars']):
        num = order[(s['page'], s['sys'], bi)]
        stream[s['part']][gi(num)] = overrides.get((s['page'], s['sys'], s['part'], bi), [b]); src[s['part']][gi(num)] = s
for k in range(NP):      # a whole-bar rest glyph is read as 16 sixteenths; make it the bar length (6/8, 3/4, ...)
    for g_ in range(NB):
        for voice in stream[k][g_]:
            if len(voice) == 1 and voice[0]['rest'] and voice[0]['dur'] == 16 and bar_at(g_ + first) != 16: voice[0] = dict(voice[0], dur=bar_at(g_ + first))
flat = {k: [(g_, e) for g_ in range(NB) for voice in stream[k][g_] for e in voice] for k in range(NP)}

# ties
def curve_boxes(s): return [(c['rect'].x0, c['rect'].x1, c['rect'].y0, c['rect'].y1) for c in s['curves'] if c['rect'].height < 12 and c['rect'].width > 6]
for k in range(NP):
    seq = flat[k]
    for i, (g_, e) in enumerate(seq):
        e['tie'] = False
        if i + 1 >= len(seq) or e['rest'] or len(stream[k][g_]) > 1: continue
        g2, f = seq[i + 1]
        if f['rest'] or sorted(f['p']) != sorted(e['p']): continue
        s = src[k][g_]; sp = s['staff']['sp']; top = s['staff']['top']; bot = s['staff']['bottom']
        same = src[k][g2] is s
        for x0, x1, y0, y1 in curve_boxes(s):
            if not (top - 4 * sp < y0 and y1 < bot + 4 * sp): continue
            if e['x'] - 3 < x0 < e['x'] + sp * 2.2:
                if same and f['x'] - 6 < x1 < f['x'] + sp * 2.2: e['tie'] = True
                if not same and x1 > s['staff']['x1'] - 40: e['tie'] = True
tie_end = {id(flat[k][i + 1][1]) for k in range(NP) for i in range(len(flat[k]) - 1) if flat[k][i][1]['tie']}

# lyrics
pdf = pymupdf.open(a.pdf)
skip = set(a.skip_words.split(','))
words = {}
for pi, pg in enumerate(pdf):
    stf = sorted({(s['staff']['top'], s['staff']['bottom'], s['sys'], s['part']) for s in sts if s['page'] == pi})
    if not stf: continue
    for w in pg.get_text('words'):
        t = w[4]
        if t in skip or re.fullmatch(r'[0-9]+\.?', t) or t.startswith('(') or w[2] < 60 or any(c in t for c in 'œ™˙&?#°¢‹Ó‰Œ∑') or v.has_music_code(t): continue
        cand = [x for x in stf if x[1] <= w[1] + 3]
        if not cand or w[1] < stf[0][0] - 40: continue
        top, bot, sysi, part = max(cand, key=lambda x: x[1])
        if w[3] - bot > 48: continue
        words.setdefault((pi, sysi, part), []).append(((w[0] + w[2]) / 2, t, w[1]))
words_rows = {}
for key_, lst_ in words.items():
    ys_ = sorted({round(w_[2]) for w_ in lst_}); rows_ = []
    for y_ in ys_:
        if rows_ and y_ - rows_[-1][-1] <= 5: rows_[-1].append(y_)
        else: rows_.append([y_])
    for r_, grp in enumerate(rows_):
        words_rows.setdefault(r_, {})[key_] = [(cx_, t_) for cx_, t_, y_ in lst_ if round(y_) in grp]
lyr_v = []
for vrow in sorted(words_rows):
    words = words_rows[vrow]; lyr = {}
    for (pi, sysi, part), ws in words.items():
        ws.sort(); toks = []
        for i, (cx, t) in enumerate(ws):
            if t.strip('-') == '': continue
            nh = i + 1 < len(ws) and ws[i + 1][1].strip('-') == ''; ph = i > 0 and ws[i - 1][1].strip('-') == ''
            toks.append((cx, t.rstrip('-'), 'middle' if ph and nh else 'begin' if nh else 'end' if ph else 'single'))
        cands = [(g_, vi, ei, e) for g_ in range(NB) if src[part][g_] and (src[part][g_]['page'], src[part][g_]['sys']) == (pi, sysi)
                 for vi, voice in enumerate(stream[part][g_]) for ei, e in enumerate(voice) if not e['rest'] and id(e) not in tie_end]
        pairs = sorted((abs(c[3]['x'] + 4.5 - cx), ti, ci) for ti, (cx, t, sy) in enumerate(toks) for ci, c in enumerate(cands) if abs(c[3]['x'] + 4.5 - cx) < 24)
        ut, uc = set(), set()
        for d_, ti, ci in pairs:
            if ti in ut or ci in uc: continue
            ut.add(ti); uc.add(ci); c = cands[ci]; lyr[(part, c[0], c[1], c[2])] = (toks[ti][1], toks[ti][2])
        for ti, (cx, t, sy) in enumerate(toks):
            if ti not in ut: print('UNMATCHED lyric', PARTS[part], 'page', pi, 'system', sysi, repr(t), round(cx))
    lyr_v.append(lyr)
lyr = lyr_v[0] if lyr_v else {}
for spec in a.copy_lyrics:
    fr, to = map(int, spec.split(':'))
    for g_ in range(NB):
        if any(k[0] == to and k[1] == g_ for k in lyr): continue
        for vi, voice in enumerate(stream[to][g_]):
            for ei, e in enumerate(voice):
                if e['rest']: continue
                for vj, vo in enumerate(stream[fr][g_]):
                    for ej, ea in enumerate(vo):
                        if not ea['rest'] and abs(ea['x'] - e['x']) < 3 and (fr, g_, vj, ej) in lyr: lyr[(to, g_, vi, ei)] = lyr[(fr, g_, vj, ej)]

TYPES = {1: ('16th', 0), 2: ('eighth', 0), 3: ('eighth', 1), 4: ('quarter', 0), 6: ('quarter', 1), 8: ('half', 0), 12: ('half', 1), 16: ('whole', 0), 24: ('whole', 1)}
def part_xml(k):
    o = [f'<part id="P{k + 1}">']
    for g_ in range(NB):
        num = g_ + first
        o.append(f'<measure number="{num}"' + (' implicit="yes"' if pickup and g_ == 0 else '') + '>')
        if g_ == 0:
            clef = {'G': '<sign>G</sign><line>2</line>', 'G8': '<sign>G</sign><line>2</line><clef-octave-change>-1</clef-octave-change>', 'F': '<sign>F</sign><line>4</line>'}[CLEFS[k]]
            o.append(f'<attributes><divisions>4</divisions><key><fifths>{a.key}</fifths></key><time><beats>{beats}</beats><beat-type>{beat_type}</beat-type></time><clef>{clef}</clef></attributes>')
            if k == 0 and a.tempo: o.append(f'<direction placement="above"><direction-type><metronome><beat-unit>quarter</beat-unit><per-minute>{a.tempo}</per-minute></metronome></direction-type><sound tempo="{a.tempo}"/></direction>')
        if g_ and num in TC: o.append(f'<attributes><time><beats>{TC[num][0]}</beats><beat-type>{TC[num][1]}</beat-type></time></attributes>')
        for vi, voice in enumerate(stream[k][g_]):
            if vi: o.append(f'<backup><duration>{sum(e["dur"] for e in stream[k][g_][0])}</duration></backup>')
            for ei, e in enumerate(voice):
                tstart = e.get('tie', False); tstop = id(e) in tie_end
                for pi_ in range(max(1, len(e['p']))):
                    s = '<note>' + ('<chord/>' if pi_ else '')
                    if e['rest']: s += '<rest measure="yes"/>' if e['dur'] == bar_at(num) else '<rest/>'
                    else:
                        idx = e['p'][pi_]; st = STEPN[idx % 7]; oc = idx // 7 - (1 if CLEFS[k] == 'G8' else 0); al = e.get('alt', {}).get(idx, altered.get(st, 0))
                        s += f'<pitch><step>{st}</step>' + (f'<alter>{al}</alter>' if al else '') + f'<octave>{oc}</octave></pitch>'
                    ty, dot = TYPES[e['dur']]
                    s += f'<duration>{e["dur"]}</duration>'
                    if tstop and not e['rest']: s += '<tie type="stop"/>'
                    if tstart and not e['rest']: s += '<tie type="start"/>'
                    s += f'<voice>{vi + 1}</voice><type>{ty}</type>' + ('<dot/>' if dot else '')
                    nt = ('<tied type="stop"/>' if tstop and not e['rest'] else '') + ('<tied type="start"/>' if tstart and not e['rest'] else '')
                    if nt: s += f'<notations>{nt}</notations>'
                    if pi_ == 0:
                        for vn_, lv_ in enumerate(lyr_v):
                            if (k, g_, vi, ei) in lv_:
                                t, sy = lv_[(k, g_, vi, ei)]; s += f'<lyric number="{vn_ + 1}"><syllabic>{sy}</syllabic><text>{html.escape(t)}</text></lyric>'
                    o.append(s + '</note>')
        o.append('</measure>')
    o.append('</part>'); return '\n'.join(o)
ident = (f'<identification><creator type="composer">{html.escape(a.composer)}</creator></identification>' if a.composer else '')
head = ('<?xml version="1.0" encoding="UTF-8"?><score-partwise version="3.0">' + (f'<work><work-title>{html.escape(a.title)}</work-title></work>' if a.title else '') + ident + '<part-list>'
        + ''.join(f'<score-part id="P{i + 1}"><part-name>{html.escape(n_)}</part-name></score-part>' for i, n_ in enumerate(PARTS)) + '</part-list>')
open(a.out, 'w').write(head + '\n'.join(part_xml(k) for k in range(NP)) + '</score-partwise>')
bad = 0
for g_ in range(NB):
    for k in range(NP):
        tot = [sum(e['dur'] for e in voice) for voice in stream[k][g_]]
        want = bar_at(g_ + first) if (g_ or not pickup) else None
        if any(t != want for t in tot) and want: print('BAR SUM', PARTS[k], 'bar', g_ + first, tot); bad += 1
print(f'{NB} bars{" (pickup + " + str(NB - 1) + ")" if pickup else ""}, {NP} parts, ties {sum(1 for k in range(NP) for _, e in flat[k] if e["tie"])}, lyrics {len(lyr)}, bars to fix: {bad}')
