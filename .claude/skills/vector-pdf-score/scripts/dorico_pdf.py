"""Reader for PDFs exported by Dorico (the music is SMuFL text in the Bravura font), as a 2-staff choral
layout: a treble staff (upper two voices) over a bass staff (lower two voices).

    assemble(pdf)        notes per staff and bar (onset, pitch, duration, ties), key, time signature, repeats
    attach_lyrics(...)   lyric syllables matched to the note columns
    assign_parts(...)    notes of the two staves -> Soprano / Alto / Tenor / Bass using the (alto only) cue labels
    directions(...)      text, rehearsal marks, segno / coda / D.S., fermatas per bar

Onsets and durations are in 1/256 of a quarter note. Run `dorico_pdf_musicxml.py` to write MusicXML.
Verified on one score only (Carol of the Bells, 7 pages): see SKILL.md for what is and is not covered."""
import pymupdf, re, sys, os
from collections import defaultdict
HEAD_BLACK, HEAD_OPEN = 0xf4be, 0xf4bd
REST = {0xe4e3: 16, 0xe4e4: 8, 0xe4e5: 4, 0xe4e6: 2, 0xe4e7: 1}
ACC = {0xe260: -1, 0xe261: 0, 0xe262: 1}
DOT = 0xe1e7
STEPS = [0, 2, 4, 5, 7, 9, 11]
def midi(idx, alt): return 12 * (idx // 7 + 1) + STEPS[idx % 7] + alt
FLAT_ORDER = [6, 2, 5, 1, 4, 0, 3]    # B E A D G C F as diatonic letters C=0
SHARP_ORDER = [3, 0, 4, 1, 5, 2, 6]
def key_alter(fifths):
    d = {}
    if fifths > 0:
        for s in SHARP_ORDER[:fifths]: d[s] = 1
    else:
        for s in FLAT_ORDER[:-fifths]: d[s] = -1
    return d

def page_items(pg):
    glyphs = []; words = []
    for b in pg.get_text('rawdict')['blocks']:
        for l in b.get('lines', []):
            for s in l['spans']:
                if s['font'].startswith('Bravura'):
                    for c in s['chars']:
                        if c['c'] != ' ': glyphs.append((c['origin'][0], c['origin'][1], ord(c['c']), s['size']))
    words = pg.get_text('words')
    vlines = []; hlines = []; fills = []
    for dr in pg.get_drawings():
        r = dr['rect']; kinds = [i[0] for i in dr['items']]
        if dr['type'] == 's' and kinds == ['l']:
            w = round(dr.get('width') or 0, 2)
            if r.width < 0.01: vlines.append((r.x0, r.y0, r.y1, w))
            elif r.height < 0.01: hlines.append((r.y0, r.x0, r.x1, w))
        elif dr['type'] == 'f': fills.append((dr['rect'], kinds))
    return glyphs, words, vlines, hlines, fills

def find_staves(hlines):
    allines = [(y, x0, x1) for y, x0, x1, w in hlines if abs(w - 0.62) < 0.02 and x1 - x0 > 100]
    staves = []
    groups = defaultdict(list)
    for y, x0, x1 in allines: groups[(round(x0), round(x1))].append((y, x0, x1))
    for key, lines in groups.items():
        lines.sort(); i = 0
        while i + 4 < len(lines):
            ys = [lines[i + k][0] for k in range(5)]
            sp = (ys[4] - ys[0]) / 4
            if all(abs((ys[k + 1] - ys[k]) - sp) < 0.1 for k in range(4)):
                staves.append(dict(top=ys[0], bottom=ys[4], sp=sp, x0=lines[i][1], x1=lines[i][2])); i += 5
            else: i += 1
    # reading order: by system row (top of first staff of a pair), then x
    staves.sort(key=lambda s: (round(s['top'] / 60), s['x0'], s['top']))
    return staves

def parse_page(pg):
    glyphs, words, vlines, hlines, fills = page_items(pg)
    staves = find_staves(hlines)
    for st in staves:
        top, bot, sp = st['top'], st['bottom'], st['sp']
        clef = [g for g in glyphs if g[2] in (0xe050, 0xe062) and top - 1 <= g[1] <= bot + 1 and g[0] < st['x0'] + 40]
        st['clef'] = 'G' if (clef and clef[0][2] == 0xe050) else 'F'
        st['thick'] = sorted(x for x, y0, y1, w in vlines if abs(w - 2.48) < 0.1 and y0 <= top + 1 and y1 >= bot - 1)
        st['dots'] = sorted(x for x, y, c, sz in glyphs if c == 0xe044 and top <= y <= bot)
        st['bars'] = sorted({round(x, 1) for x, y0, y1, w in vlines if abs(w - 0.99) < 0.02 and y0 <= top + 1 and y1 >= bot - 1 and st['x0'] < x <= st['x1'] + 0.5})
    return dict(glyphs=glyphs, words=words, vlines=vlines, hlines=hlines, fills=fills, staves=staves)

# ---------------------------------------------------------------- notes
def build(pdf, pages=None):
    d = pymupdf.open(pdf); out = []   # list of (page index, [treble staff, bass staff]); each staff dict carries edges and items
    for pi in range(len(d)):
        if pages is not None and pi not in pages: continue
        P = parse_page(d[pi]); glyphs = P['glyphs']; vlines = P['vlines']; fills = P['fills']
        st = sorted(P['staves'], key=lambda s: (s['top'], s['x0']))
        pairs = []; used = set()
        for i, g in enumerate(st):
            if i in used or g['clef'] != 'G': continue
            for j in range(i + 1, len(st)):
                if j not in used and st[j]['clef'] == 'F' and abs(st[j]['x0'] - g['x0']) < 1 and abs(st[j]['x1'] - g['x1']) < 1:
                    used |= {i, j}; pairs.append([g, st[j]]); break
        pairs.sort(key=lambda p: (round(p[0]['top'] / 40), p[0]['x0']))
        for pair in pairs:
            for k, s in enumerate(pair): s['sysrow'] = k
            for s in pair:
                xs = [s['x0']]; s['rep_start_x'] = []; s['rep_end_x'] = []
                for x in s['bars']:
                    tk = [t for t in s['thick'] if 0 < x - t < 8]
                    if tk:      # thin line right of a thick one: start repeat; the thick line closes the bar before it
                        s['rep_start_x'].append(x)
                        if tk[0] - xs[-1] > 6: xs.append(tk[0])
                        continue
                    if any(0 < tx - x < 8 for tx in s['thick']) and any(0 < x - dx < 14 for dx in s['dots']): s['rep_end_x'].append(x)
                    if x - xs[-1] < 6: xs[-1] = x if len(xs) > 1 else xs[-1]
                    else: xs.append(x)
                s['edges'] = xs
            for s in pair:
                top, bot, sp = s['top'], s['bottom'], s['sp']
                base = (4 * 7 + 2) if s['clef'] == 'G' else (2 * 7 + 4)
                def region(y): return top - 5.2 * sp <= y <= bot + 5.2 * sp
                # exclusive region: closer to this staff than the other staff of the pair
                other = [o for o in pair if o is not s]
                def mine(y):
                    if not region(y): return False
                    if other:
                        o = other[0]
                        return abs(y - (top + bot) / 2) <= abs(y - (o['top'] + o['bottom']) / 2)
                    return True
                heads = [(x, y, c) for x, y, c, sz in glyphs if c in (HEAD_BLACK, HEAD_OPEN) and mine(y)]
                stems = [(x, y0, y1) for x, y0, y1, w in vlines if abs(w - 0.6) < 0.02 and y1 > top - 6 * sp and y0 < bot + 6 * sp]
                rests = [(x, y, c) for x, y, c, sz in glyphs if c in REST and mine(y) and x > s['x0'] + 20]
                dots = [(x, y) for x, y, c, sz in glyphs if c == DOT and mine(y)]
                flags = [(x, y, c) for x, y, c, sz in glyphs if c in (0xe240, 0xe241, 0xe242, 0xe243) and mine(y)]
                beams = [r for r, kinds in fills if kinds in (['l', 'l', 'l', 'l'], ['re']) and r.width > 5 and r.height < 16 and top - 8 * sp < r.y0 < bot + 8 * sp]
                evs = {}   # stem x -> event
                for x, y, c in heads:
                    n = round((bot - y) / (sp / 2)); p = base + n
                    found = None
                    for sx, y0, y1 in stems:
                        if y0 - 1.5 <= y <= y1 + 1.5 and (abs(sx - (x + 6.24)) < 0.8 or abs(sx - x) < 0.8): found = (round(sx, 1), y0, y1)
                    key = found[0] if found else ('nostem', round(x, 1))
                    e = evs.setdefault(key, dict(x=x, heads=[], head=c, stem=found))
                    e['heads'].append((p, y, x)); e['x'] = min(e['x'], x)
                for key, e in evs.items():
                    if e['stem']:
                        sx, y0, y1 = e['stem']; hy = [h[1] for h in e['heads']]
                        e['dir'] = 'up' if (min(hy) - y0) > (y1 - max(hy)) else 'down'
                        e['stem'] = (sx, e['dir'], y0, y1)
                    else: e['dir'] = None
                items = []
                for key, e in evs.items():
                    lv = 0
                    if e['stem']:
                        sx, kind, y0, y1 = e['stem']
                        end = y0 if kind == 'up' else y1
                        lv = sum(1 for r in beams if r.x0 - 0.6 <= sx <= r.x1 + 0.6 and (r.y0 - 4 <= end <= r.y1 + 4))
                        if lv == 0:
                            lv = 0
                            for fx, fy, fc in flags:
                                if abs(fx - sx) < 3.5 and abs(fy - end) < 12: lv = 1 if fc in (0xe240, 0xe241) else 2
                    base_d = 8 if e['head'] == HEAD_OPEN else 4
                    dur = 4 if (e['head'] == HEAD_BLACK and lv == 0) else base_d
                    if e['head'] == HEAD_BLACK and lv: dur = {1: 2, 2: 1, 3: 0}[lv] if lv < 3 else 1
                    dotted = any(0 < dx - max(h[2] for h in e['heads']) < 14 and any(abs(dy - h[1]) < sp * 0.8 for h in e['heads']) for dx, dy in dots)
                    # a dot sits right of the notehead and (in a space) at the head's y or one half-space above
                    dotted = any(0 < dx - (max(h[2] for h in e['heads'])) < 14 and any(-0.7 * sp < h[1] - dy < 0.9 * sp for h in e['heads']) for dx, dy in dots)
                    if dotted: dur = dur * 3 // 2
                    items.append(dict(kind='note', x=e['x'], pitches=sorted(h[0] for h in e['heads']), heads=sorted(e['heads']), dur=dur, dir=e['dir'], lv=lv, dotted=dotted))
                for x, y, c in rests:
                    dur = REST[c]
                    rdot = any(0 < dx - x < 10 and abs(dy - y) < sp for dx, dy in dots)
                    items.append(dict(kind='rest', x=x, y=y, dur=dur * 3 // 2 if rdot else dur, dir=None))
                digs = sorted((x, c - 0xe080) for x, y, c, sz in glyphs if 0xe080 <= c <= 0xe089 and not (top - 1 <= y <= bot + 1))
                for r, kinds in fills:
                    if kinds == ['re'] and r.width > 15 and 4.4 < r.height < 5.6 and abs((r.y0 + r.y1) / 2 - (top + bot) / 2) < sp:
                        cx = (r.x0 + r.x1) / 2
                        numerals = []
                        for dx, dy, dgt in sorted((x, y, c - 0xe080) for x, y, c, sz in glyphs if 0xe080 <= c <= 0xe089 and not (top - 1 <= y <= bot + 1)):
                            if numerals and abs(numerals[-1]['y'] - dy) < 1 and dx - numerals[-1]['x1'] < 9: numerals[-1]['d'].append(dgt); numerals[-1]['x1'] = dx
                            else: numerals.append(dict(y=dy, x0=dx, x1=dx, d=[dgt]))
                        cand = [nm for nm in numerals if abs((nm['x0'] + nm['x1']) / 2 + 3.5 - cx) < 14 and abs(nm['y'] - (top + bot) / 2) < 70]
                        n = int(''.join(map(str, min(cand, key=lambda nm: abs((nm['x0'] + nm['x1']) / 2 + 3.5 - cx))['d']))) if cand else 1
                        items.append(dict(kind='mrest', x=cx, n=n, dur=0, dir=None))
                s['items'] = sorted(items, key=lambda i: i['x'])
            for s in pair:
                ed = s['edges']; keep = [ed[0]]
                for i in range(len(ed) - 1):
                    has = any(ed[i] < it['x'] < ed[i + 1] for it in s['items'])
                    if has: keep.append(ed[i + 1])
                    else:
                        # empty interval (clef/key only, or a double barline gap): merge it into the next one
                        if i + 1 < len(ed) - 1: keep[-1] = keep[-1] if len(keep) == 1 else keep[-1]
                if len(keep) == 1: keep.append(ed[-1])
                # the first interval must start at the staff start
                s['edges'] = keep
            out.append((pi, pair))
    return out

# ---------------------------------------------------------------- bars
def staff_context(P_glyphs, s, pair):
    """key signature (fifths) at system start and time-signature / key-change clusters per bar of one staff."""
    top, bot, sp = s['top'], s['bottom'], s['sp']
    other = [o for o in pair if o is not s]
    def mine(y):
        if not (top - 3 * sp <= y <= bot + 3 * sp): return False
        return all(abs(y - (top + bot) / 2) <= abs(y - (o['top'] + o['bottom']) / 2) for o in other)
    accs = sorted((g for g in P_glyphs if g[2] in ACC and mine(g[1])), key=lambda g: g[0])
    digits = sorted((g for g in P_glyphs if 0xe080 <= g[2] <= 0xe089 and mine(g[1])), key=lambda g: g[0])
    return accs, digits

def timesigs(digits, sp, top):
    """cluster digit glyphs by x: pair (upper numeral, lower numeral); multi-digit numerals are merged by x order."""
    cl = []
    for g in digits:
        if cl and abs(cl[-1][-1][0] - g[0]) < 12 and True: cl[-1].append(g)
        else: cl.append([g])
    out = []
    for c in cl:
        up = [g for g in c if g[1] < top + 2.0 * sp]; lo = [g for g in c if g[1] >= top + 2.0 * sp]
        num = int(''.join(str(g[2] - 0xe080) for g in sorted(up))) if up else None
        den = int(''.join(str(g[2] - 0xe080) for g in sorted(lo))) if lo else None
        if num and den: out.append((min(g[0] for g in c), num, den))
    return out

def assemble(pdf, pages=None):
    d = pymupdf.open(pdf)
    res = build(pdf, pages)
    notes_out = {0: [], 1: []}
    bars = {0: {}, 1: {}}    # staff row -> bar number -> list of (onset, midi, dur)
    meta = dict(time={}, key={})
    barno = 0; fifths = 0; ts = (3, 4)
    for pi, pair in res:
        glyphs, _w, _v, _h, _f = page_items(d[pi])
        crescents = [r for r, kinds in _f if kinds == ['c', 'l', 'c', 'l']]
        nb = len(pair[0]['edges']) - 1
        meta.setdefault('sysstart', []).append((pi, round(pair[0]['top']), barno + 1))
        for k, s in enumerate(pair):
            accs, digits = staff_context(glyphs, s, pair)
            edges = s['edges']
            tsx = timesigs(digits, s['sp'], s['top'])
            # key signature at system start = accidentals left of the first note/rest/digit and right of the clef
            first = min([it['x'] for it in s['items']] + [edges[1]])
            lead_digits = min([t[0] for t in tsx if t[0] < edges[1]] + [first])
            lead = [g for g in accs if g[0] < min(first, lead_digits) - 8 and g[2] != 0xe261]
            if lead:
                # accidentals before the first notehead that are not attached to a note
                fifths_sys = -len(lead) if lead[0][2] == 0xe260 else len(lead)
            else: fifths_sys = 0
            s['key0'] = fifths_sys; s['ts'] = tsx
        for bi in range(nb):
            barno += 1
            extra = 0
            xs0, xs1 = pair[0]['edges'][bi], pair[0]['edges'][bi + 1]
            for k, s in enumerate(pair):
                xs0, xs1 = s['edges'][bi], s['edges'][bi + 1]
                accs, digits = staff_context(glyphs, s, pair)
                # time signature printed at the start of this bar
                for x, n, dd in s['ts']:
                    if xs0 - 1 <= x < xs1 and not (bi == 0 and k >= 0 and False): ts = (n, dd)
                if bi == 0 and s['ts']: pass
                barlen = 16 * ts[0] // ts[1]
                base = (4 * 7 + 2) if s['clef'] == 'G' else (2 * 7 + 4)
                its = [it for it in s['items'] if xs0 < it['x'] < xs1]
                mr = [i for i in its if i['kind'] == 'mrest']
                if mr: extra = max(extra, mr[0]['n'] - 1)
                its = [i for i in its if i['kind'] != 'mrest']
                if any(i['kind'] == 'note' for i in its): its = [i for i in its if not (i['kind'] == 'rest' and i['dur'] >= barlen)]
                if bi == 0: fifths = s['key0']
                # key change at the start of a bar (cluster of accidentals not attached to a head)
                bar_accs = [g for g in accs if xs0 < g[0] < xs1]
                heads_x = [it['x'] for it in its if it['kind'] == 'note']
                cluster = [g for g in bar_accs if g[0] < xs0 + 45 and (not heads_x or g[0] < min(heads_x) - 14)]
                if cluster and bi > 0:
                    if all(g[2] == 0xe261 for g in cluster): fifths = 0
                    else: fifths = -len([g for g in cluster if g[2] == 0xe260]) if cluster[0][2] == 0xe260 else len([g for g in cluster if g[2] == 0xe262])
                kd = key_alter(fifths); held = {}
                meta['key'][barno] = fifths; meta.setdefault('time', {})[barno] = ts
                for ex in range(1, extra + 1):
                    meta['key'][barno + ex] = fifths; meta['time'][barno + ex] = ts
                voices = {}
                # first try one line: columns of items at the same x, each column with one duration
                cols = []
                for it in sorted(its, key=lambda i: i['x']):
                    if cols and abs(cols[-1][0]['x'] - it['x']) < 2.5: cols[-1].append(it)
                    else: cols.append([it])
                tot = 0; ok = True
                for c in cols:
                    ds = {i['dur'] for i in c}
                    if len(ds) > 1: ok = False; break
                    tot += c[0]['dur']
                if ok and tot == barlen: voices['a'] = sorted(its, key=lambda i: i['x'])
                else:
                    mid = (s['top'] + s['bottom']) / 2
                    vu = [it for it in its if it['kind'] == 'note' and it['dir'] == 'up']; vd = [it for it in its if it['kind'] == 'note' and it['dir'] != 'up']
                    ru = [it for it in its if it['kind'] == 'rest' and it['y'] < mid]; rd = [it for it in its if it['kind'] == 'rest' and it['y'] >= mid]
                    voices['u'] = sorted(vu + ru, key=lambda i: i['x']); voices['d'] = sorted(vd + rd, key=lambda i: i['x'])
                bl = []
                for vname, vits in voices.items():
                    t = 0
                    for it in vits:
                        if it['kind'] == 'rest':
                            if it['dur'] == 16: t += barlen
                            else: t += it['dur']
                            continue
                        for p in it['pitches']:
                            alt = held.get(p, kd.get(p % 7, 0))
                            # accidental printed left of the head
                            acc_here = [g for g in accs if 0 < it['x'] - g[0] < 14 and abs(g[1] - (s['bottom'] - (p - base) * s['sp'] / 2)) < 0.6 * s['sp'] and g[0] > xs0]
                            if acc_here: alt = ACC[acc_here[-1][2]]; held[p] = alt
                            hy = [h for h in it['heads'] if h[0] == p][0]
                            tie = any(hy[2] + 2.5 <= c.x0 <= hy[2] + 13 and abs((c.y0 + c.y1) / 2 - hy[1]) < 1.7 * s['sp'] for c in crescents)
                            notes_out[k].append(dict(bar=barno, onset=t * 64, midi=midi(p, alt), dur=it['dur'] * 64, x=hy[2], y=hy[1], tie=tie, dir=it['dir'], vname=vname, page=pi, sysrow=k, item=it, systop=round(pair[0]['top'], 1), sysx0=round(pair[0]['x0'], 1)))
                            bl.append((t * 64, midi(p, alt), it['dur'] * 64))
                        t += it['dur']
                bars[k][barno] = sorted(bl)
            s0 = pair[0]; el, er = s0['edges'][bi], s0['edges'][bi + 1]
            meta.setdefault('intervals', []).append((pi, round(s0['top']), round(s0['x0']), barno, extra, el, er))
            if any(el - 1 <= x < er for x in s0['rep_start_x']): meta.setdefault('rep_start', set()).add(barno)
            if any(abs(er - x) < 1.5 for x in s0['rep_end_x']): meta.setdefault('rep_end', set()).add(barno + extra)
            barno += extra
    for k in (0, 1):
        seq = notes_out[k]
        for i, n in enumerate(seq):
            n['tie_stop'] = False
        for i, n in enumerate(seq):
            if n['tie']:
                for m in seq[i + 1:]:
                    if m['midi'] == n['midi'] and (m['bar'], m['onset']) > (n['bar'], n['onset']):
                        m['tie_stop'] = True; break
    meta['notes'] = notes_out
    return bars, meta

# ---------------------------------------------------------------- lyrics
def attach_lyrics(pdf, bars, meta, res=None):
    """lyric text under each staff -> meta['lyrics'][(k, bar, onset)] = (text, syllabic); one syllable per note column."""
    d = pymupdf.open(pdf)
    res = res or build(pdf)
    lyr = {}
    notes = meta['notes']
    # notes grouped per page / staff row / system order
    for pi, pair in res:
        words = []
        for b in d[pi].get_text('dict')['blocks']:
            for l in b.get('lines', []):
                for sp_ in l['spans']:
                    if 'Finale' in sp_['font'] and abs(sp_['size'] - 11.0) < 0.3 and sp_['text'].strip():
                        bb = sp_['bbox']; words.append((bb[0], bb[1], bb[2], bb[3], sp_['text'].strip()))
        for k, s in enumerate(pair):
            band = [w for w in words if s['bottom'] + 3 < w[1] < s['bottom'] + 30 and s['x0'] < (w[0] + w[2]) / 2 < s['x1']]
            if not band: continue
            # rows: words sorted by x on one baseline (take the nearest row below the staff only)
            ymin = min(w[1] for w in band)
            band = [w for w in band if abs(w[1] - ymin) < 6]
            ws = sorted(((w[0] + w[2]) / 2, w[4]) for w in band)
            toks = []
            for i, (cx, t) in enumerate(ws):
                if t.strip('-') == '': continue
                nh = i + 1 < len(ws) and ws[i + 1][1].strip('-') == ''; ph = i > 0 and ws[i - 1][1].strip('-') == ''
                toks.append((cx, t.rstrip('-'), 'middle' if ph and nh else 'begin' if nh else 'end' if ph else 'single'))
            x0, x1 = s['edges'][0], s['edges'][-1]
            cols = {}
            for n in notes[k]:
                if n['page'] == pi and n['systop'] == round(pair[0]['top'], 1) and n['sysx0'] == round(s['x0'], 1) and not n.get('tie_stop'):
                    cols.setdefault((n['bar'], n['onset']), []).append(n)
            colkeys = sorted(cols, key=lambda c: min(n['x'] for n in cols[c]))
            colx = [min(n['x'] for n in cols[c]) for c in colkeys]
            pairs = sorted((abs(cx - (c + 3.2)), ti, ci) for ti, (cx, t, sy) in enumerate(toks) for ci, c in enumerate(colx) if abs(cx - (c + 3.2)) < 16)
            ut, uc = set(), set()
            for dist, ti, ci in pairs:
                if ti in ut or ci in uc: continue
                ut.add(ti); uc.add(ci)
                lyr[(k, colkeys[ci][0], colkeys[ci][1])] = (toks[ti][1], toks[ti][2])
            for ti, (cx, t, sy) in enumerate(toks):
                if ti not in ut: print('UNMATCHED lyric', pi, k, repr(t), round(cx))
    meta['lyrics'] = lyr
    return lyr

# ---------------------------------------------------------------- voice parts
LABELS = {'(alto only)': ('lower',), '(soprano only)': ('upper',), '(tenor only)': ('upper',), '(bass only)': ('lower',), '(S+A)': ('both',), '(T+B)': ('both',), '(SATB)': ('both',)}
def staff_labels(pdf, res):
    """(page, row-of-staff identity) -> list of (x, state) from the '(alto only)' style cue labels"""
    d = pymupdf.open(pdf); out = {}
    for pi, pair in res:
        spans = []
        for b in d[pi].get_text('dict')['blocks']:
            for l in b.get('lines', []):
                for sp_ in l['spans']:
                    t = sp_['text'].strip()
                    if t in LABELS: spans.append((sp_['bbox'][0], sp_['bbox'][3], t))
        for x, y1, t in spans:
            cand = [s for s in pair if 0 < s['top'] - y1 < 70 and s['x0'] - 1 <= x <= s['x1']]
            if cand:
                s = min(cand, key=lambda s: s['top'] - y1)
                out.setdefault((pi, round(s['top']), round(s['x0'])), []).append((x, LABELS[t][0]))
    for v in out.values(): v.sort()
    return out

def assign_parts(pdf, meta, res=None):
    """each note -> list of voice parts: 0 S, 1 A, 2 T, 3 B (a list because a unison note belongs to two parts)."""
    res = res or build(pdf)
    labels = staff_labels(pdf, res)
    state = {0: 'both', 1: 'both'}
    parts = {i: [] for i in range(4)}
    keys = []
    for pi, pair in res:
        for k, s in enumerate(pair):
            keys.append((pi, round(s['top']), round(s['x0']), k, s))
    # notes per (page, staff, k) in x order
    for pi, top, x0, k, s in keys:
        lab = labels.get((pi, top, x0), [])
        ns = [n for n in meta['notes'][k] if n['page'] == pi and n['systop'] == round(pairtop(res, pi, s), 1) and n['sysx0'] == round(s['x0'], 1)]
        ns.sort(key=lambda n: (n['x'], n['y']))
        # events: group by (bar, onset, voice name)
        groups = {}
        for n in ns: groups.setdefault((n['bar'], n['onset'], n['vname']), []).append(n)
        for key_ in sorted(groups, key=lambda g: (min(n['x'] for n in groups[g]), g[2])):
            g = sorted(groups[key_], key=lambda n: -n['midi'])
            x = min(n['x'] for n in g)
            for lx, st_ in lab:
                if lx - 6 <= x: state[k] = st_
            up, lo = (0, 1) if k == 0 else (2, 3)
            vname = key_[2]
            if vname == 'u': tgt = [(up, g)]
            elif vname == 'd': tgt = [(lo, g)]
            elif len(g) >= 2: tgt = [(up, [g[0]]), (lo, [g[-1]])]
            else:
                st_ = state[k]
                tgt = [(up, g)] if st_ == 'upper' else [(lo, g)] if st_ == 'lower' else [(up, g), (lo, g)]
            for pt, nl in tgt:
                for n in nl: parts[pt].append(n)
    return parts

def pairtop(res, pi, s):
    for p, pair in res:
        if p == pi and s in pair: return pair[0]['top']

# ---------------------------------------------------------------- directions
def bar_at(meta, pi, y, x, above=90):
    """(bar, extra bars) of the system whose top staff lies just below y (page pi) and whose interval holds x"""
    cands = [iv for iv in meta['intervals'] if iv[0] == pi and 0 <= iv[1] - y <= above]
    if not cands: return None
    # nearest system row first, then the interval that contains x (else the nearest one)
    row = min(iv[1] - y for iv in cands)
    cands = [iv for iv in cands if iv[1] - y <= row + 3]
    inside = [iv for iv in cands if iv[5] <= x <= iv[6]]
    best = inside[0] if inside else min(cands, key=lambda iv: min(abs(iv[5] - x), abs(iv[6] - x)))
    return best[3], best[4]

def directions(pdf, meta, res):
    """per bar: list of ('words', text) | ('rehearsal', text) | ('segno',) | ('coda',) | ('tocoda',) | ('dsalcoda',) | ('fermata', x)"""
    d = pymupdf.open(pdf); out = {}
    def add(b, item): out.setdefault(b, []).append(item)
    for pi in range(len(d)):
        spans = []
        for b in d[pi].get_text('dict')['blocks']:
            for l in b.get('lines', []):
                for sp_ in l['spans']:
                    t = sp_['text'].strip()
                    if t: spans.append((sp_['bbox'], sp_['font'], sp_['size'], t))
        # join Helvetica words on one baseline ("D.S." "al" "Coda", "To" "Coda")
        hel = sorted([s for s in spans if s[1] == 'Helvetica'], key=lambda s: (round(s[0][1]), s[0][0]))
        lines = []
        for bb, f, sz, t in hel:
            if lines and abs(lines[-1][0][1] - bb[1]) < 3 and bb[0] - lines[-1][0][2] < 8: lines[-1][0] = (lines[-1][0][0], lines[-1][0][1], bb[2], bb[3]); lines[-1][1] += ' ' + t
            else: lines.append([bb, t])
        for bb, t in lines:
            hit = bar_at(meta, pi, bb[3], (bb[0] + bb[2]) / 2, 100)
            if not hit: print('direction without a bar', pi, t); continue
            b, ex = hit
            if t.startswith('D.S.'): add(b + ex, ('dsalcoda',))
            elif t.startswith('To Coda'): add(b + ex, ('tocoda',))
            elif t == 'Coda': add(b, ('coda',))
        for bb, f, sz, t in spans:
            if 'Finale' not in f: continue
            if abs(sz - 11) < 0.3 or t in LABELS: continue
            if sz >= 13 and sz < 15 and len(t) <= 2:
                hit = bar_at(meta, pi, bb[3], bb[2] + 2, 100)
                if hit: add(hit[0], ('rehearsal', t))
            elif abs(sz - 12) < 0.3:
                hit = bar_at(meta, pi, bb[3], bb[0] + 8, 100)
                if hit: add(hit[0], ('words', t))
        for b in d[pi].get_text('rawdict')['blocks']:
            for l in b.get('lines', []):
                for sp_ in l['spans']:
                    if sp_['font'] == 'BravuraText':
                        for c in sp_['chars']:
                            if ord(c['c']) == 0xe047:
                                hit = bar_at(meta, pi, sp_['bbox'][1], sp_['bbox'][2] + 2, 100)
                                if hit: add(hit[0], ('segno',))
        for x, y, c, sz in page_items(d[pi])[0]:
            if c == 0xe4c0:
                hit = bar_at(meta, pi, y - 4, x, 40)
                if hit: add(hit[0], ('fermata', x))
    return out


if __name__ == '__main__':
    ap_pdf = sys.argv[1]
    bars_, meta_ = assemble(ap_pdf)
    for k_ in (0, 1):
        print('staff', k_ + 1, 'bars', len(bars_[k_]), 'notes', len(meta_['notes'][k_]))
    print('time signatures', sorted({(b, t) for b, t in meta_['time'].items() if b == 1 or meta_['time'].get(b - 1) != t}))
    print('key changes', sorted({(b, f) for b, f in meta_['key'].items() if b == 1 or meta_['key'].get(b - 1) != f}))
    print('repeats start', sorted(meta_.get('rep_start', ())), 'end', sorted(meta_.get('rep_end', ())))
