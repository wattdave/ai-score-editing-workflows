"""Reader for PDFs exported by Dorico (the music is SMuFL text in the Bravura font), choral layouts.

A system holds any mix of: separate voice staves labelled S. A. T. B. (the tenor staff is a treble staff with a
small 8 below), and a condensed pair of staves labelled Ch. / Choir SATB (treble: soprano + alto, bass: tenor + bass).

    read(pdf)            -> Score: systems, staves with roles, notes (onset, pitch, duration, ties), lyrics, bar meta
    parts(score)         -> four lists of notes: soprano, alto, tenor, bass
    directions(score)    -> text, rehearsal marks, segno / coda / D.S., fermatas per bar

Onsets and durations are in 1/256 of a quarter note. All measurements scale with the staff space, so the same code
reads the 20 pt "Choir SATB" and the 13.5 pt "Choral score" exports. Verified on Carol of the Bells only."""
import pymupdf, sys
from collections import defaultdict

HEAD_BLACK, HEAD_OPEN = 0xf4be, 0xf4bd
REST = {0xe4e3: 16, 0xe4e4: 8, 0xe4e5: 4, 0xe4e6: 2, 0xe4e7: 1}
ACC = {0xe260: -1, 0xe261: 0, 0xe262: 1}
DOT = 0xe1e7
G_CLEF, G_CLEF_8VB, F_CLEF = 0xe050, 0xe052, 0xe062
STEPS = [0, 2, 4, 5, 7, 9, 11]
FLAT_ORDER = [6, 2, 5, 1, 4, 0, 3]
SHARP_ORDER = [3, 0, 4, 1, 5, 2, 6]
REF_SP = 4.96            # staff space of the 20 pt export the constants below were measured on
LABELS = {'(alto only)': 'lower', '(soprano only)': 'upper', '(tenor only)': 'upper', '(bass only)': 'lower',
          '(S+A)': 'both', '(T+B)': 'both', '(SATB)': 'both'}
ROLE_LABELS = {'S.': 'S', 'A.': 'A', 'T.': 'T', 'B.': 'B', 'Ch.': 'CH', 'Choir SATB': 'CH', 'Choir': 'CH'}


def midi(idx, alt): return 12 * (idx // 7 + 1) + STEPS[idx % 7] + alt


def key_alter(fifths):
    d = {}
    if fifths > 0:
        for s in SHARP_ORDER[:fifths]: d[s] = 1
    else:
        for s in FLAT_ORDER[:-fifths]: d[s] = -1
    return d


def page_items(pg):
    glyphs = []
    for b in pg.get_text('rawdict')['blocks']:
        for l in b.get('lines', []):
            for s in l['spans']:
                if s['font'].startswith('Bravura'):
                    for c in s['chars']:
                        if c['c'] != ' ': glyphs.append((c['origin'][0], c['origin'][1], ord(c['c']), s['size']))
    vlines, hlines, fills = [], [], []
    for dr in pg.get_drawings():
        r = dr['rect']; kinds = [i[0] for i in dr['items']]
        if dr['type'] == 's' and kinds == ['l']:
            w = dr.get('width') or 0
            if r.width < 0.01: vlines.append((r.x0, r.y0, r.y1, w))
            elif r.height < 0.01: hlines.append((r.y0, r.x0, r.x1, w))
        elif dr['type'] == 'f': fills.append((dr['rect'], kinds))
    return glyphs, vlines, hlines, fills


def find_staves(hlines):
    """five equally spaced long horizontal lines with one x extent -> staff dicts (top, bottom, sp, x0, x1)"""
    groups = defaultdict(list)
    for y, x0, x1, w in hlines:
        if x1 - x0 > 100: groups[(round(x0), round(x1))].append((y, x0, x1))
    staves = []
    for lines in groups.values():
        lines.sort(); i = 0
        while i + 4 < len(lines):
            ys = [lines[i + k][0] for k in range(5)]
            sp = (ys[4] - ys[0]) / 4
            if 2 < sp < 8 and all(abs((ys[k + 1] - ys[k]) - sp) < 0.1 * sp / 4 for k in range(4)):
                staves.append(dict(top=ys[0], bottom=ys[4], sp=sp, u=sp / REF_SP, x0=lines[i][1], x1=lines[i][2])); i += 5
            else: i += 1
    return sorted(staves, key=lambda s: (s['top'], s['x0']))


def staff_marks(pg_glyphs, vlines, s):
    """clef, barlines, thick lines and repeat dots of one staff"""
    top, bot, sp, u = s['top'], s['bottom'], s['sp'], s['u']
    clef = [g for g in pg_glyphs if g[2] in (G_CLEF, G_CLEF_8VB, F_CLEF) and top - 1 <= g[1] <= bot + 1 and g[0] < s['x0'] + 40 * u]
    s['clef'] = {G_CLEF: 'G', G_CLEF_8VB: 'G8', F_CLEF: 'F'}[min(clef, key=lambda g: g[0])[2]] if clef else 'F'
    def wide(w, ratio, tol): return abs(w / sp - ratio) < tol
    s['thick'] = sorted(x for x, y0, y1, w in vlines if wide(w, 0.5, 0.1) and y0 <= top + 1 and y1 >= bot - 1)
    s['dots'] = sorted(x for x, y, c, sz in pg_glyphs if c == 0xe044 and top <= y <= bot)
    s['bars'] = sorted({round(x, 1) for x, y0, y1, w in vlines if wide(w, 0.2, 0.05) and y0 <= top + 1 and y1 >= bot - 1 and s['x0'] < x <= s['x1'] + 0.5})


def staff_edges(s):
    """bar edges of one staff; thin line right of a thick one = start repeat, thin line left of thick + dots = end repeat"""
    u = s['u']
    xs = [s['x0']]; s['rep_start_x'] = []; s['rep_end_x'] = []
    for x in s['bars']:
        tk = [t for t in s['thick'] if 0 < x - t < 8 * u]
        if tk:
            s['rep_start_x'].append(x)
            if tk[0] - xs[-1] > 6 * u: xs.append(tk[0])
            continue
        if any(0 < tx - x < 8 * u for tx in s['thick']) and any(0 < x - dx < 14 * u for dx in s['dots']): s['rep_end_x'].append(x)
        if x - xs[-1] < 6 * u: xs[-1] = x if len(xs) > 1 else xs[-1]
        else: xs.append(x)
    s['edges'] = xs


def staff_items(s, glyphs, vlines, fills, others):
    """noteheads grouped by stem, rests and multi-bar rests of one staff; items are sorted by x"""
    top, bot, sp, u = s['top'], s['bottom'], s['sp'], s['u']
    base = (4 * 7 + 2) if s['clef'] == 'G' else (3 * 7 + 2) if s['clef'] == 'G8' else (2 * 7 + 4)
    s['base'] = base
    def mine(y):
        if not (top - 5.2 * sp <= y <= bot + 5.2 * sp): return False
        return all(abs(y - (top + bot) / 2) <= abs(y - (o['top'] + o['bottom']) / 2) for o in others)
    heads = [(x, y, c) for x, y, c, sz in glyphs if c in (HEAD_BLACK, HEAD_OPEN) and mine(y)]
    stems = [(x, y0, y1) for x, y0, y1, w in vlines if abs(w / sp - 0.121) < 0.03 and y1 > top - 6 * sp and y0 < bot + 6 * sp]
    rests = [(x, y, c) for x, y, c, sz in glyphs if c in REST and mine(y) and x > s['x0'] + 20 * u]
    dots = [(x, y) for x, y, c, sz in glyphs if c == DOT and mine(y)]
    flags = [(x, y, c) for x, y, c, sz in glyphs if c in (0xe240, 0xe241, 0xe242, 0xe243) and mine(y)]
    beams = [r for r, kinds in fills if kinds in (['l', 'l', 'l', 'l'], ['re']) and r.width > 1.0 * sp and r.height < 3.2 * sp and top - 8 * sp < r.y0 < bot + 8 * sp]
    hw = 1.258 * sp
    evs = {}
    for x, y, c in heads:
        p = base + round((bot - y) / (sp / 2))
        found = None
        for sx, y0, y1 in stems:
            if y0 - 0.3 * sp <= y <= y1 + 0.3 * sp and (abs(sx - (x + hw)) < 0.16 * sp or abs(sx - x) < 0.16 * sp): found = (round(sx, 1), y0, y1)
        key = found[0] if found else ('nostem', round(x, 1))
        e = evs.setdefault(key, dict(x=x, heads=[], head=c, stem=found))
        e['heads'].append((p, y, x)); e['x'] = min(e['x'], x)
    items = []
    for key, e in evs.items():
        e['dir'] = None; lv = 0
        if e['stem']:
            sx, y0, y1 = e['stem']; hy = [h[1] for h in e['heads']]
            e['dir'] = 'up' if (min(hy) - y0) > (y1 - max(hy)) else 'down'
            end = y0 if e['dir'] == 'up' else y1
            lv = sum(1 for r in beams if r.x0 - 0.12 * sp <= sx <= r.x1 + 0.12 * sp and (r.y0 - 0.8 * sp <= end <= r.y1 + 0.8 * sp))
            if lv == 0:
                for fx, fy, fc in flags:
                    if abs(fx - sx) < 0.7 * sp and abs(fy - end) < 2.4 * sp: lv = 1 if fc in (0xe240, 0xe241) else 2
        dur = 8 if e['head'] == HEAD_OPEN else 4
        if e['head'] == HEAD_BLACK and lv: dur = {1: 2, 2: 1}.get(lv, 1)
        xr = max(h[2] for h in e['heads'])
        if any(0 < dx - xr < 2.8 * sp and any(-0.7 * sp < h[1] - dy < 0.9 * sp for h in e['heads']) for dx, dy in dots): dur = dur * 3 // 2
        items.append(dict(kind='note', x=e['x'], pitches=sorted(h[0] for h in e['heads']), heads=sorted(e['heads']), dur=dur, dir=e['dir']))
    for x, y, c in rests:
        rdot = any(0 < dx - x < 2 * sp and abs(dy - y) < sp for dx, dy in dots)
        items.append(dict(kind='rest', x=x, y=y, dur=REST[c] * 3 // 2 if rdot else REST[c], dir=None))
    numerals = []
    for dx, dy, dgt in sorted((x, y, c - 0xe080) for x, y, c, sz in glyphs if 0xe080 <= c <= 0xe089 and not (top - 1 <= y <= bot + 1)):
        if numerals and abs(numerals[-1]['y'] - dy) < 1 and dx - numerals[-1]['x1'] < 1.8 * sp: numerals[-1]['d'].append(dgt); numerals[-1]['x1'] = dx
        else: numerals.append(dict(y=dy, x0=dx, x1=dx, d=[dgt]))
    for r, kinds in fills:
        if kinds == ['re'] and r.width > 3 * sp and 0.88 * sp < r.height < 1.13 * sp and abs((r.y0 + r.y1) / 2 - (top + bot) / 2) < sp:
            cx = (r.x0 + r.x1) / 2
            cand = [nm for nm in numerals if abs((nm['x0'] + nm['x1']) / 2 + 0.7 * sp - cx) < 2.8 * sp and abs(nm['y'] - (top + bot) / 2) < 14 * sp]
            n = int(''.join(map(str, min(cand, key=lambda nm: abs((nm['x0'] + nm['x1']) / 2 + 0.7 * sp - cx))['d']))) if cand else 1
            items.append(dict(kind='mrest', x=cx, n=n, dur=0, dir=None))
    s['items'] = sorted(items, key=lambda i: i['x'])


def staff_labels(pg, staves):
    """role of each staff from the instrument name printed at the left of its system: S. A. T. B. Ch. (Choir SATB)"""
    spans = []
    for b in pg.get_text('dict')['blocks']:
        for l in b.get('lines', []):
            for sp_ in l['spans']:
                t = sp_['text'].strip()
                if t in ROLE_LABELS and sp_['bbox'][2] <= min(s['x0'] for s in staves) + 6: spans.append(((sp_['bbox'][1] + sp_['bbox'][3]) / 2, ROLE_LABELS[t]))
    for s in staves:
        cy = (s['top'] + s['bottom']) / 2
        near = [(abs(y - cy), r) for y, r in spans if abs(y - cy) < 12 * s['sp']]
        s['role'] = min(near)[1] if near else None


def read(pdf):
    """-> dict(systems=[...], notes=[...], meta=...) ; see module docstring. Systems keep their staves in reading order."""
    d = pymupdf.open(pdf)
    systems = []
    for pi in range(len(d)):
        glyphs, vlines, hlines, fills = page_items(d[pi])
        staves = find_staves(hlines)
        for s in staves:
            staff_marks(glyphs, vlines, s); staff_edges(s)
        staff_labels(d[pi], staves)
        for s in staves:
            staff_items(s, glyphs, vlines, fills, [o for o in staves if o is not s and abs(o['x0'] - s['x0']) < 1])
        # a system = staves of one x extent whose bar edges agree and that touch (no staff with another extent between)
        staves.sort(key=lambda s: (round(s['x0']), s['top']))
        cur = []
        for s in staves:
            if cur and abs(cur[-1]['x0'] - s['x0']) < 1 and abs(cur[-1]['x1'] - s['x1']) < 1 and s['top'] - cur[-1]['bottom'] < 10 * s['sp'] + 90 and _same_edges(cur[0], s):
                cur.append(s)
            else:
                if cur: systems.append((pi, cur))
                cur = [s]
        if cur: systems.append((pi, cur))
    systems.sort(key=lambda ps: (ps[0], round(ps[1][0]['top'] / 40), ps[1][0]['x0']))
    return d, systems


def _same_edges(a, b):
    ea, eb = a['edges'], b['edges']
    return len(ea) == len(eb) and all(abs(x - y) < 1.5 for x, y in zip(ea[1:], eb[1:]))


# ---------------------------------------------------------------- bars, notes, key, time, repeats
def _prune_edges(staves):
    """drop empty intervals (clef and key only, or the gap before a start repeat) using every staff of the system"""
    ed = staves[0]['edges']; keep = [ed[0]]
    for i in range(len(ed) - 1):
        if any(ed[i] < it['x'] < ed[i + 1] for s in staves for it in s['items']): keep.append(ed[i + 1])
    if len(keep) == 1: keep.append(ed[-1])
    for s in staves: s['edges'] = list(keep)


def _timesigs(glyphs, s):
    top, bot, sp = s['top'], s['bottom'], s['sp']
    digits = sorted((g for g in glyphs if 0xe080 <= g[2] <= 0xe089 and top - 1 <= g[1] <= bot + 1), key=lambda g: g[0])
    cl = []
    for g in digits:
        if cl and abs(cl[-1][-1][0] - g[0]) < 2.4 * sp: cl[-1].append(g)
        else: cl.append([g])
    out = []
    for c in cl:
        up = [g for g in c if g[1] < top + 2.0 * sp]; lo = [g for g in c if g[1] >= top + 2.0 * sp]
        num = int(''.join(str(g[2] - 0xe080) for g in sorted(up))) if up else None
        den = int(''.join(str(g[2] - 0xe080) for g in sorted(lo))) if lo else None
        if num and den: out.append((min(g[0] for g in c), num, den))
    return out


def assemble(pdf):
    d, systems = read(pdf)
    score = dict(doc=d, systems=systems, lyric_size=text_sizes(d)[0], label_size=text_sizes(d)[1], notes=[], key={}, time={}, rep_start=set(), rep_end=set(), intervals=[], pdf=pdf)
    barno = 0; fifths = 0; ts = (3, 4)
    pagecache = {}
    for pi, staves in systems:
        if pi not in pagecache: pagecache[pi] = page_items(d[pi])
        glyphs, _v, _h, fills = pagecache[pi]
        crescents = [r for r, kinds in fills if kinds == ['c', 'l', 'c', 'l']]
        _prune_edges(staves)
        lead = staves[0]
        nb = len(lead['edges']) - 1
        for s in staves:
            s['ts'] = _timesigs(glyphs, s)
            u = s['u']; accs = sorted((g for g in glyphs if g[2] in ACC and s['top'] - 3 * s['sp'] <= g[1] <= s['bottom'] + 3 * s['sp'] and all(abs(g[1] - (s['top'] + s['bottom']) / 2) <= abs(g[1] - (o['top'] + o['bottom']) / 2) for o in staves if o is not s)), key=lambda g: g[0])
            s['accs'] = accs
            first = min([it['x'] for it in s['items']] + [s['edges'][1]])
            lead_digits = min([t[0] for t in s['ts'] if t[0] < s['edges'][1]] + [first])
            lead_acc = [g for g in accs if g[0] < min(first, lead_digits) - 1.6 * s['sp'] and g[2] != 0xe261]
            s['key0'] = (-len(lead_acc) if lead_acc[0][2] == 0xe260 else len(lead_acc)) if lead_acc else 0
        score.setdefault('sysstart', []).append((pi, round(lead['top']), barno + 1))
        for bi in range(nb):
            barno += 1; extra = 0
            for si, s in enumerate(staves):
                e0, e1 = s['edges'][bi], s['edges'][bi + 1]
                sp = s['sp']
                if si == 0:
                    for x, n, dd in s['ts']:
                        if e0 - 1 <= x < e1: ts = (n, dd)
                    if bi == 0: fifths = s['key0']
                barlen = 16 * ts[0] // ts[1]
                its = [it for it in s['items'] if e0 < it['x'] < e1]
                mr = [i for i in its if i['kind'] == 'mrest']
                if mr: extra = max(extra, mr[0]['n'] - 1)
                its = [i for i in its if i['kind'] != 'mrest']
                if any(i['kind'] == 'note' for i in its): its = [i for i in its if not (i['kind'] == 'rest' and i['dur'] >= barlen)]
                bar_accs = [g for g in s['accs'] if e0 < g[0] < e1]
                heads_x = [it['x'] for it in its if it['kind'] == 'note']
                if si == 0:
                    cluster = [g for g in bar_accs if g[0] < e0 + 9 * sp and (not heads_x or g[0] < min(heads_x) - 2.8 * sp)]
                    if cluster and bi > 0:
                        if all(g[2] == 0xe261 for g in cluster): fifths = 0
                        else: fifths = -len([g for g in cluster if g[2] == 0xe260]) if cluster[0][2] == 0xe260 else len([g for g in cluster if g[2] == 0xe262])
                    score['key'][barno] = fifths; score['time'][barno] = ts
                    for ex in range(1, extra + 1): score['key'][barno + ex] = fifths; score['time'][barno + ex] = ts
                kd = key_alter(fifths); held = {}
                # one line when the columns add up to the bar, else split by stem direction
                cols = []
                for it in sorted(its, key=lambda i: i['x']):
                    if cols and abs(cols[-1][0]['x'] - it['x']) < 0.5 * sp: cols[-1].append(it)
                    else: cols.append([it])
                tot, ok = 0, True
                for c in cols:
                    if len({i['dur'] for i in c}) > 1: ok = False; break
                    tot += c[0]['dur']
                voices = {}
                if ok and tot == barlen: voices['a'] = sorted(its, key=lambda i: i['x'])
                else:
                    mid = (s['top'] + s['bottom']) / 2
                    vu = [it for it in its if it['kind'] == 'note' and it['dir'] == 'up']; vd = [it for it in its if it['kind'] == 'note' and it['dir'] != 'up']
                    ru = [it for it in its if it['kind'] == 'rest' and it['y'] < mid]; rd = [it for it in its if it['kind'] == 'rest' and it['y'] >= mid]
                    voices['u'] = sorted(vu + ru, key=lambda i: i['x']); voices['d'] = sorted(vd + rd, key=lambda i: i['x'])
                for vname, vits in voices.items():
                    t = 0
                    for it in vits:
                        if it['kind'] == 'rest':
                            t += barlen if it['dur'] == 16 else it['dur']; continue
                        for p in it['pitches']:
                            alt = held.get(p, kd.get(p % 7, 0))
                            acc_here = [g for g in s['accs'] if 0 < it['x'] - g[0] < 2.8 * sp and abs(g[1] - (s['bottom'] - (p - s['base']) * sp / 2)) < 0.6 * sp and g[0] > e0]
                            if acc_here: alt = ACC[acc_here[-1][2]]; held[p] = alt
                            hy = [h for h in it['heads'] if h[0] == p][0]
                            tie = any(hy[2] + 0.5 * sp <= c.x0 <= hy[2] + 2.6 * sp and abs((c.y0 + c.y1) / 2 - hy[1]) < 1.7 * sp for c in crescents)
                            score['notes'].append(dict(bar=barno, onset=t * 64, midi=midi(p, alt), dur=it['dur'] * 64, x=hy[2], y=hy[1], tie=tie, tie_stop=False, dir=it['dir'],
                                                       vname=vname, page=pi, staff=s, sys=len(score['sysstart']) - 1, si=si))
                        t += it['dur']
            s0 = lead; el, er = s0['edges'][bi], s0['edges'][bi + 1]
            score['intervals'].append((pi, round(s0['top']), round(s0['x0']), barno, extra, el, er, len(score['sysstart']) - 1))
            if any(el - 1 <= x < er for x in s0['rep_start_x']): score['rep_start'].add(barno)
            if any(abs(er - x) < 1.5 for x in s0['rep_end_x']): score['rep_end'].add(barno + extra)
            barno += extra
    # ties: the next note of the same pitch on the same staff after a tied note is its end
    by_staff = defaultdict(list)
    for n in score['notes']: by_staff[n['staff']['role'] if n['staff']['role'] in ('S', 'A', 'T', 'B') else 'CH' + n['staff']['clef']].append(n)
    for seq in by_staff.values():
        seq.sort(key=lambda n: (n['bar'], n['onset']))
        for i, n in enumerate(seq):
            if n['tie']:
                for m in seq[i + 1:]:
                    if m['midi'] == n['midi'] and (m['bar'], m['onset']) > (n['bar'], n['onset']): m['tie_stop'] = True; break
    score['nbars'] = max(score['key'])
    return score


# ---------------------------------------------------------------- lyrics
def text_sizes(d):
    """(lyric size, direction size): the commonest text size, and the size of the (alto only) style cue labels"""
    from collections import Counter
    chars = Counter(); lab = Counter()
    for pg in d:
        for b in pg.get_text('dict')['blocks']:
            for l in b.get('lines', []):
                for sp_ in l['spans']:
                    t = sp_['text'].strip()
                    if 'Finale' not in sp_['font'] or not t: continue
                    chars[round(sp_['size'], 1)] += len(t)
                    if t in LABELS: lab[round(sp_['size'], 1)] += 1
    lyric = chars.most_common(1)[0][0] if chars else 11.0
    return lyric, (lab.most_common(1)[0][0] if lab else lyric + 1)


def _lyric_spans(pg, size):
    out = []
    for b in pg.get_text('dict')['blocks']:
        for l in b.get('lines', []):
            for sp_ in l['spans']:
                if 'Finale' in sp_['font'] and abs(sp_['size'] - size) < 0.2 and sp_['text'].strip():
                    bb = sp_['bbox']; out.append((bb[0], bb[1], bb[2], bb[3], sp_['text'].strip()))
    return out


def attach_lyrics(score):
    """score['lyrics'][(id(staff), bar, onset)] = (text, syllabic): one syllable per note column of a staff"""
    d = score['doc']; lyr = {}
    cols_by_staff = defaultdict(dict)
    for n in score['notes']:
        if not n['tie_stop']: cols_by_staff[id(n['staff'])].setdefault((n['bar'], n['onset']), []).append(n)
    words_cache = {}
    for pi, staves in score['systems']:
        for s in staves:
            u = s['u']
            if pi not in words_cache: words_cache[pi] = _lyric_spans(d[pi], score['lyric_size'])
            band = [w for w in words_cache[pi] if s['bottom'] + 3 * u < w[1] < s['bottom'] + 30 * u and s['x0'] < (w[0] + w[2]) / 2 < s['x1']]
            # a lyric row belongs to the staff above it: drop words nearer to the staff below
            below = [o for o in staves if o['top'] > s['bottom']]
            if below: band = [w for w in band if w[1] < below[0]['top'] - 2 * u]
            if not band: continue
            ymin = min(w[1] for w in band)
            band = [w for w in band if abs(w[1] - ymin) < 6 * u]
            ws = sorted(((w[0] + w[2]) / 2, w[4], w[0], w[2]) for w in band)
            toks = []
            for i, (cx, t, wl, wr) in enumerate(ws):
                if t.strip('-') == '': continue
                nh = i + 1 < len(ws) and ws[i + 1][1].strip('-') == ''; ph = i > 0 and ws[i - 1][1].strip('-') == ''
                toks.append((cx, t.rstrip('-'), 'middle' if ph and nh else 'begin' if nh else 'end' if ph else 'single', wl, wr))
            cols = {k: [n for n in v if n['page'] == pi and n['sys'] == score['systems'].index((pi, staves))] for k, v in cols_by_staff[id(s)].items()}
            cols = {k: v for k, v in cols.items() if v}
            colkeys = sorted(cols, key=lambda c: min(n['x'] for n in cols[c]))
            colx = [min(n['x'] for n in cols[c]) for c in colkeys]
            def gap(tok, c):
                hc = c + 0.64 * s['sp']
                return max(0.0, tok[3] - hc, hc - tok[4])
            pairs = sorted((gap(tok, c), abs(tok[0] - (c + 0.64 * s['sp'])), ti, ci) for ti, tok in enumerate(toks) for ci, c in enumerate(colx) if gap(tok, c) < 2.0 * s['sp'] and abs(tok[0] - (c + 0.64 * s['sp'])) < 8 * s['sp'])
            ut, uc = set(), set()
            for g_, dist, ti, ci in pairs:
                if ti in ut or ci in uc: continue
                ut.add(ti); uc.add(ci); lyr[(id(s), colkeys[ci][0], colkeys[ci][1])] = (toks[ti][1], toks[ti][2])
    score['lyrics'] = lyr
    return lyr


# ---------------------------------------------------------------- voice parts
def cue_labels(score):
    """cue labels like (alto only) -> {id(staff): [(x, state)]} for the staff just below each label"""
    d = score['doc']; out = defaultdict(list)
    for pi, staves in score['systems']:
        for b in d[pi].get_text('dict')['blocks']:
            for l in b.get('lines', []):
                for sp_ in l['spans']:
                    t = sp_['text'].strip()
                    if t in LABELS:
                        x, y1 = sp_['bbox'][0], sp_['bbox'][3]
                        cand = [s for s in staves if 0 < s['top'] - y1 < 14 * s['sp'] and s['x0'] - 1 <= x <= s['x1']]
                        if cand: out[id(min(cand, key=lambda s: s['top'] - y1))].append((x, LABELS[t]))
    for v in out.values(): v.sort()
    return out


def split_parts(score):
    """-> [soprano, alto, tenor, bass] note lists. Separate staves keep their notes; a condensed (Ch.) pair splits by chord,
    stem direction and cue label."""
    labels = cue_labels(score)
    parts = [[], [], [], []]
    state = {'G': 'both', 'F': 'both'}
    role_part = {'S': 0, 'A': 1, 'T': 2, 'B': 3}
    notes_by_staff = defaultdict(list)
    for n in score['notes']: notes_by_staff[id(n['staff'])].append(n)
    for pi, staves in score['systems']:
        for s in staves:
            ns = notes_by_staff[id(s)]
            if s['role'] in role_part:
                for n in ns: parts[role_part[s['role']]].append(n)
                continue
            up, lo = (0, 1) if s['clef'] == 'G' else (2, 3)
            k = 'G' if s['clef'] == 'G' else 'F'
            lab = labels.get(id(s), [])
            groups = defaultdict(list)
            for n in ns: groups[(n['bar'], n['onset'], n['vname'])].append(n)
            for key_ in sorted(groups, key=lambda g: (min(n['x'] for n in groups[g]), g[2])):
                g = sorted(groups[key_], key=lambda n: -n['midi'])
                x = min(n['x'] for n in g)
                for lx, st_ in lab:
                    if lx - 6 * s['u'] <= x: state[k] = st_
                vname = key_[2]
                if vname == 'u': tgt = [(up, g)]
                elif vname == 'd': tgt = [(lo, g)]
                elif len(g) >= 2: tgt = [(up, [g[0]]), (lo, [g[-1]])]
                else: tgt = [(up, g)] if state[k] == 'upper' else [(lo, g)] if state[k] == 'lower' else [(up, g), (lo, g)]
                for pt, nl in tgt:
                    for n in nl: parts[pt].append(n)
    return parts


# ---------------------------------------------------------------- directions
def _bar_at(score, pi, y, x, above):
    """(bar, extra bars, system index) of the system on page pi that lies just below y (or contains y) and whose bar holds x"""
    best = None
    for si, (p, staves) in enumerate(score['systems']):
        if p != pi: continue
        top, bot = staves[0]['top'], staves[-1]['bottom']
        if not (staves[0]['x0'] - 6 <= x <= staves[0]['x1'] + 6): continue
        dist = (top - y) if y < top else 0 if y <= bot else None
        if dist is None or dist > above * staves[0]['u']: continue
        if best is None or dist < best[0]: best = (dist, si)
    if best is None: return None
    si = best[1]
    ivs = [iv for iv in score['intervals'] if iv[7] == si]
    inside = [iv for iv in ivs if iv[5] <= x <= iv[6]]
    iv = inside[0] if inside else min(ivs, key=lambda iv: min(abs(iv[5] - x), abs(iv[6] - x)))
    return iv[3], iv[4], si


def directions(score):
    """per bar: ('words', text) | ('rehearsal', text) | ('segno',) | ('coda',) | ('tocoda',) | ('dsalcoda',);
    score['fermatas'] = [(id(staff), bar, x)]"""
    d = score['doc']; out = defaultdict(list); ferm = []
    for pi in range(len(d)):
        glyphs = page_items(d[pi])[0]
        sysu = [staves[0]['u'] for p, staves in score['systems'] if p == pi]
        if not sysu: continue
        u = sysu[0]
        spans = []
        for b in d[pi].get_text('dict')['blocks']:
            for l in b.get('lines', []):
                for sp_ in l['spans']:
                    t = sp_['text'].strip()
                    if t: spans.append((sp_['bbox'], sp_['font'], sp_['size'], t))
        hel = sorted([s for s in spans if s[1] == 'Helvetica'], key=lambda s: (round(s[0][1]), s[0][0]))
        lines = []
        for bb, f, sz, t in hel:
            if lines and abs(lines[-1][0][1] - bb[1]) < 3 and bb[0] - lines[-1][0][2] < 1.6 * u * 5: lines[-1][0] = (lines[-1][0][0], lines[-1][0][1], bb[2], bb[3]); lines[-1][1] += ' ' + t
            else: lines.append([bb, t])
        for bb, t in lines:
            hit = _bar_at(score, pi, bb[3], (bb[0] + bb[2]) / 2, 100)
            if not hit: print('direction without a bar', pi, t); continue
            b, ex, _si = hit
            if t.startswith('D.S.'): out[b + ex].append(('dsalcoda',))
            elif t.startswith('To Coda'): out[b + ex].append(('tocoda',))
            elif t == 'Coda': out[b].append(('coda',))
        for bb, f, sz, t in spans:
            if 'Finale' not in f or t in LABELS or t in ROLE_LABELS: continue
            if abs(sz - score['lyric_size']) < 0.2 or sz > 16: continue
            if sz > score['label_size'] + 0.5 and t.isalpha() and t.isupper() and len(t) == 1:
                hit = _bar_at(score, pi, bb[3], bb[2] + 2 * u, 100)
                if hit: out[hit[0]].append(('rehearsal', t))
            elif abs(sz - score['label_size']) < 0.2:
                hit = _bar_at(score, pi, bb[3], bb[0] + 8 * u, 100)
                if hit: out[hit[0]].append(('words', t))
        for b in d[pi].get_text('rawdict')['blocks']:
            for l in b.get('lines', []):
                for sp_ in l['spans']:
                    if sp_['font'] == 'BravuraText':
                        for c in sp_['chars']:
                            if ord(c['c']) == 0xe047:
                                hit = _bar_at(score, pi, sp_['bbox'][1], sp_['bbox'][2] + 2 * u, 100)
                                if hit: out[hit[0]].append(('segno',))
        for x, y, c, sz in glyphs:
            if c == 0xe4c0:
                hit = _bar_at(score, pi, y, x, 40)
                if hit:
                    staves = score['systems'][hit[2]][1]
                    s = min(staves, key=lambda s: abs((s['top'] + s['bottom']) / 2 - y))
                    ferm.append((id(s), hit[0], x))
                    out[hit[0]].append(('fermata', x))
    score['fermatas'] = ferm
    return out


# ---------------------------------------------------------------- title block
def metadata(score):
    """(title, composer, arranger) from the first page: the biggest text, the top-right text, the 'arranged by' footer"""
    d = score['doc']; pg = d[0]; title = composer = arranger = ''
    spans = []
    for b in pg.get_text('dict')['blocks']:
        for l in b.get('lines', []):
            for sp_ in l['spans']:
                t = sp_['text'].strip()
                if t: spans.append((sp_['size'], sp_['bbox'], t))
    big = [s for s in spans if s[2] not in LABELS and s[2] not in ROLE_LABELS and s[2] != 'Choral score']
    if big: title = max(big, key=lambda s: s[0])[2]
    right = [s for s in spans if s[1][0] > pg.rect.width * 0.55 and s[1][1] < 160 and s[2] != title and s[2] not in LABELS and not s[2].startswith('(')]
    cands = [s for s in right if s[0] > score['label_size'] and s[2][:1].isupper() and ' ' in s[2]]
    if cands: composer = min(cands, key=lambda s: s[1][1])[2]
    for s in spans:
        if s[2].lower().startswith('arranged by'):
            arranger = s[2][len('arranged by'):].split(' - ')[0].strip()
    return title, composer, arranger
