"""Build MusicXML from a Sibelius-exported vector PDF using vecscore.py.

  uv run --with pymupdf python -I vecscore_musicxml.py SCORE.pdf OUT.musicxml \\
      --parts Soprano,Alto,Tenor,Bass --clefs G,G,G8,F --key 2 --time 4/4 --tempo 60 \\
      [--title T] [--composer C] [--override bars.json] [--copy-lyrics 1:2]

Ties come from curve drawings that start on a note and end on the next note of the same pitch.
Lyrics are matched to notes by position (greedy, nearest first). A bar whose events do not add up
is reported as BAR SUM and must be given with --override (two voices on one staff are split, see --split-voices).
Tenor staves written with a treble-8vb clef (G8) are written one octave lower: MusicXML pitch is sounding pitch.
Accidentals (#, b, natural) are read and held for the rest of the bar. Not handled: tuplets, grace notes,
repeats, dynamics and text."""
import argparse, html, json, re, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pymupdf
import vecscore as v
import vecscore_post as post

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
ap.add_argument('--split-voices', default='auto', choices=('auto', 'off'), help='auto: a staff with two voices in a bar (stems up and down together) is written as voice 1 and 2, with hidden rests where a voice has none printed')
ap.add_argument('--skip-word', action='append', default=[], help='one more word to skip (may contain a comma, e.g. "Revels,"); repeatable')
ap.add_argument('--lyric-reach', default='auto', help='auto: rows below a staff are kept while they follow each other (the first within 48 pt), up to the next staff; or a number of pt below the staff bottom')
ap.add_argument('--metronome', default='', help='printed metronome mark, e.g. "dotted-quarter=60", "half=86" (sound tempo is written in quarters)')
ap.add_argument('--tempo-text', default='', help='printed tempo words, e.g. "Langsam" (bold, above the first bar)')
ap.add_argument('--cut-time', action='store_true', help='write the time signature with symbol="cut" (2/2)')
ap.add_argument('--breaks', default='', help='measure numbers that start a system, e.g. "5,9" (<print new-system>); "p12" starts a page')
ap.add_argument('--final-barline', action='store_true', help='light-heavy barline after the last measure')
ap.add_argument('--abbrevs', default='', help='part abbreviations in part order, e.g. "S/A,T/B"')
ap.add_argument('--rights', default='', help='"auto": the copyright line printed on the page, verbatim (nothing if none is printed); or the text')
ap.add_argument('--patch', help='JSON list of fermatas, slurs, barlines, voltas, rehearsal marks, words, dynamics (see vecscore_post.apply_patch)')
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

sts = v.parse(a.pdf, NP, tuple(CLEFS), a.split_voices)

def _merge_voices(vs, i):
    a_, b_ = vs[i - 1], vs.pop(i)
    if a_ or b_: vs[i - 1] = [(a_[k] if a_ else []) + (b_[k] if b_ else []) for k in range(2)] if a_ and b_ else None

def pad_voices(vv, barlen, sp):
    """Fill each voice of a two-voice bar to barlen with hidden rests: a gap goes before a note when the other voice
    (the one that adds up) has a note at the same x starting later."""
    sums = [sum(e['dur'] for e in x) for x in vv]
    ref = next((x for x, t in zip(vv, sums) if t == barlen), None)
    on = []; t = 0
    for e in ref or []: on.append((e['x'], t)); t += e['dur']
    out = []
    for x, tot in zip(vv, sums):
        if x is ref or tot >= barlen: out.append(x); continue
        nv = []; t = 0
        for e in x:
            want = next((o for rx, o in on if abs(rx - e['x']) < sp * 1.3), None)
            if want is not None and want > t: nv += _hidden(want - t, e['x'] - 1); t = want
            nv.append(e); t += e['dur']
        if t < barlen: nv += _hidden(barlen - t, (x[-1]['x'] + 1) if x else 0)
        out.append(nv)
    return out
def _hidden(d, x):
    o = []
    for u in (24, 16, 12, 8, 6, 4, 3, 2, 1):
        while d >= u: o.append(dict(x=x, p=[], dur=u, rest=True, hidden=True)); d -= u
    return o

def _fix(sts):
    by_sys = {}
    for s_ in sts: by_sys.setdefault((s_['page'], s_['sys']), []).append(s_)
    for (pg_, sy_), group in by_sys.items():
        for s_ in group:
            if s_.get('voices') and s_['bars'] and not s_['bars'][0]: s_['voices'].pop(0)
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
                    if s_.get('voices'): _merge_voices(s_['voices'], i)
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
s0_ = [s for s in sts if (s['page'], s['sys'], s['part']) == (systems[0][0], systems[0][1], 0)][0]
first_bar = (s0_.get('voices') or [None])[0][0] if (s0_.get('voices') or [None])[0] else s0_['bars'][0]
pickup = sum(e['dur'] for e in first_bar) < BAR
n = 0 if pickup else 1
for pi, si in systems:
    nb = len([s for s in sts if (s['page'], s['sys'], s['part']) == (pi, si, 0)][0]['bars'])
    for bi in range(nb): order[(pi, si, bi)] = n; n += 1
first = 0 if pickup else 1
NB = n - first
def gi(num): return num - first
split_bars = set()
stream = {k: [None] * NB for k in range(NP)}; src = {k: [None] * NB for k in range(NP)}
for s in sts:
    for bi, b in enumerate(s['bars']):
        num = order[(s['page'], s['sys'], bi)]
        vv = (s.get('voices') or [None] * len(s['bars']))[bi] if bi < len(s.get('voices') or []) else None
        if vv and (g_n := gi(num)) >= 0: vv = pad_voices(vv, bar_at(num) if (g_n or not pickup) else max(sum(e['dur'] for e in x) for x in vv), s['staff']['sp'])
        stream[s['part']][gi(num)] = overrides.get((s['page'], s['sys'], s['part'], bi), vv or [b]); src[s['part']][gi(num)] = s
        if vv and (s['page'], s['sys'], s['part'], bi) not in overrides: split_bars.add((s['part'], gi(num)))
for k in range(NP):      # a whole-bar rest glyph is read as 16 sixteenths; make it the bar length (6/8, 3/4, ...)
    for g_ in range(NB):
        for voice in stream[k][g_]:
            if len(voice) == 1 and voice[0]['rest'] and voice[0]['dur'] == 16 and bar_at(g_ + first) != 16: voice[0] = dict(voice[0], dur=bar_at(g_ + first))
nferm = 0      # printed fermatas: on the nearest event of the staff (any voice), within one staff space
for k in range(NP):
    for s_ in {id(x_): x_ for x_ in src[k] if x_}.values():
        sp_ = s_['staff']['sp']
        evs = [(vi, e) for g_ in range(NB) if src[k][g_] is s_ for vi, voice in enumerate(stream[k][g_]) for e in voice if not e.get('hidden')]
        for fx, ft in s_.get('fermatas', []):
            near = [(vi, e) for vi, e in evs if abs(e['x'] - fx) < sp_ * 1.2]
            if len({vi for vi, e in near}) > 1: near = [(vi, e) for vi, e in near if vi == (0 if ft == 'upright' else max(v_ for v_, _ in near))]
            if any(e.get('fermata') for vi, e in near): continue   # one fermata per note (two-voice chords print one above, one below)
            for vi, e in near: e['fermata'] = ft
            nferm += bool(near)
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
skip = post.load_skip_words(a.skip_words, a.skip_word)
reach = None if a.lyric_reach == 'auto' else float(a.lyric_reach)
rights_lines = []
words = {}
for pi, pg in enumerate(pdf):
    stf = sorted({(s['staff']['top'], s['staff']['bottom'], s['sys'], s['part']) for s in sts if s['page'] == pi})
    if not stf: continue
    pw = pg.get_text('words'); foot = post.footer_lines(pw)
    if (c_ := post.copyright_text(pw)): rights_lines.append(c_)
    for w in pw:
        t = w[4]
        if (w[5], w[6]) in foot or ('=' in t and len(t) > 1): continue
        if t in skip or re.fullmatch(r'[0-9]+\.?', t) or t.startswith('(') or w[2] < 60 or any(c in t for c in 'œ™˙&#°¢‹Ó‰Œ∑') or ('?' in t and not re.search(r'[^\W\d_]{2}', t)) or v.has_music_code(t): continue
        cand = [x for x in stf if x[1] <= w[1] + 3]
        if not cand or w[1] < stf[0][0] - 40: continue
        top, bot, sysi, part = max(cand, key=lambda x: x[1])
        if w[3] - bot > (reach if reach is not None else 48 * 8): continue
        words.setdefault((pi, sysi, part), []).append(((w[0] + w[2]) / 2, t, w[1], w[3]))
    if reach is None:     # keep the rows that follow each other under the staff, up to the next staff
        for (top, bot, sysi, part) in stf:
            ws = words.get((pi, sysi, part))
            if not ws: continue
            nxt = min((t_ for t_, b_, _, _ in stf if t_ > bot), default=1e9)
            rows = {}
            for w_ in ws: rows.setdefault(round(w_[2]), []).append(w_)
            tops = sorted(rows); grp = []
            for y_ in tops:
                if grp and y_ - grp[-1][-1] <= 5: grp[-1].append(y_)
                else: grp.append([y_])
            bots = [max(w_[3] for y_ in g for w_ in rows[y_]) for g in grp]
            kept = set(post.keep_rows(bots, bot, nxt, 48, sp=[s for s in sts if s['page'] == pi and s['sys'] == sysi and s['part'] == part][0]['staff']['sp']))
            drop = [w_ for g, b_ in zip(grp, bots) if b_ not in kept for y_ in g for w_ in rows[y_]]
            if drop: print('lyric rows skipped under', PARTS[part], 'page', pi, 'system', sysi, ':', ' '.join(w_[1] for w_ in sorted(drop, key=lambda w_: (w_[2], w_[0])))[:80])
            words[(pi, sysi, part)] = [w_ for w_ in ws if w_ not in drop]
words_rows = {}
for key_, lst_ in words.items():
    ys_ = sorted({round(w_[2]) for w_ in lst_}); rows_ = []
    for y_ in ys_:
        if rows_ and y_ - rows_[-1][-1] <= 5: rows_[-1].append(y_)
        else: rows_.append([y_])
    for r_, grp in enumerate(rows_):
        words_rows.setdefault(r_, {})[key_] = [(cx_, t_) for cx_, t_, y_, _ in lst_ if round(y_) in grp]
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
                 for vi, voice in enumerate(stream[part][g_]) for ei, e in enumerate(voice) if not e['rest'] and id(e) not in tie_end
                 and not (vi and (part, g_) in split_bars and any(abs(e1['x'] - e['x']) < 6 for e1 in stream[part][g_][0] if not e1.get('hidden')))]
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
            o.append(f'<attributes><divisions>4</divisions><key><fifths>{a.key}</fifths></key><time' + (' symbol="cut"' if a.cut_time else '') + f'><beats>{beats}</beats><beat-type>{beat_type}</beat-type></time><clef>{clef}</clef></attributes>')
            if k == 0 and (a.metronome or a.tempo_text): o.append(post.metronome_xml(a.metronome, a.tempo_text))
            if k == 0 and a.tempo and not a.metronome: o.append(f'<direction placement="above"><direction-type><metronome><beat-unit>quarter</beat-unit><per-minute>{a.tempo}</per-minute></metronome></direction-type><sound tempo="{a.tempo}"/></direction>')
        if g_ and num in TC: o.append(f'<attributes><time><beats>{TC[num][0]}</beats><beat-type>{TC[num][1]}</beat-type></time></attributes>')
        for vi, voice in enumerate(stream[k][g_]):
            if vi: o.append(f'<backup><duration>{sum(e["dur"] for e in stream[k][g_][0])}</duration></backup>')
            for ei, e in enumerate(voice):
                tstart = e.get('tie', False); tstop = id(e) in tie_end
                for pi_ in range(max(1, len(e['p']))):
                    s = ('<note print-object="no">' if e.get('hidden') else '<note>') + ('<chord/>' if pi_ else '')
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
                    if e.get('fermata') and pi_ == 0: nt += f'<fermata type="{e["fermata"]}"/>'
                    if nt: s += f'<notations>{nt}</notations>'
                    if pi_ == 0:
                        for vn_, lv_ in enumerate(lyr_v):
                            if (k, g_, vi, ei) in lv_:
                                t, sy = lv_[(k, g_, vi, ei)]; s += f'<lyric number="{vn_ + 1}"><syllabic>{sy}</syllabic><text>{html.escape(t)}</text></lyric>'
                    o.append(s + '</note>')
        o.append('</measure>')
    o.append('</part>'); return '\n'.join(o)
rights = (rights_lines[0] if rights_lines else '') if a.rights == 'auto' else a.rights
if a.rights == 'auto': print('rights:', repr(rights) if rights else 'no copyright line printed, none written')
ident = ('<identification>' + (f'<creator type="composer">{html.escape(a.composer)}</creator>' if a.composer else '')
         + (f'<rights>{html.escape(rights)}</rights>' if rights else '') + '</identification>') if a.composer or rights else ''
head = ('<?xml version="1.0" encoding="UTF-8"?><score-partwise version="3.0">' + (f'<work><work-title>{html.escape(a.title)}</work-title></work>' if a.title else '') + ident + '<part-list>'
        + ''.join(f'<score-part id="P{i + 1}"><part-name>{html.escape(n_)}</part-name></score-part>' for i, n_ in enumerate(PARTS)) + '</part-list>')
xml = head + '\n'.join(part_xml(k) for k in range(NP)) + '</score-partwise>'
if a.abbrevs: xml = post.abbreviations(xml, a.abbrevs.split(','))
if a.breaks:
    bk = [x_.strip() for x_ in a.breaks.split(',') if x_.strip()]
    xml = post.breaks(xml, [int(x_) for x_ in bk if not x_.startswith('p')], [int(x_[1:]) for x_ in bk if x_.startswith('p')])
if a.patch: xml = post.apply_patch(xml, json.load(open(a.patch)))
if a.final_barline and '<barline location="right"><bar-style>' not in xml.rsplit('<measure ', 1)[-1]: xml = post.final_barline(xml)
open(a.out, 'w').write(xml)
bad = 0
for g_ in range(NB):
    for k in range(NP):
        tot = [sum(e['dur'] for e in voice) for voice in stream[k][g_]]
        want = bar_at(g_ + first) if (g_ or not pickup) else None
        if any(t != want for t in tot) and want: print('BAR SUM', PARTS[k], 'bar', g_ + first, tot); bad += 1
nhid = sum(1 for k in range(NP) for g_ in range(NB) if any(e.get('hidden') for voice in stream[k][g_] for e in voice))
if nhid: print(f'two voices on a staff in {len(split_bars)} bars; hidden rests added in {nhid} (check them against the print)')
if nferm: print(f'fermatas {nferm}')
print(f'{NB} bars{" (pickup + " + str(NB - 1) + ")" if pickup else ""}, {NP} parts, ties {sum(1 for k in range(NP) for _, e in flat[k] if e["tie"])}, lyrics {len(lyr)}, bars to fix: {bad}')
