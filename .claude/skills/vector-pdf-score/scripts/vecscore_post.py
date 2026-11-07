"""Pure helpers for vecscore_musicxml.py: lyric-row selection, footer/copyright lines, skip words, and
MusicXML string edits for what the print has but the reader cannot see (metronome, breaks, final barline,
part abbreviations and a --patch JSON of fermatas, barlines, rehearsal marks, words, slurs).
Every edit works on the writer's own output (divisions 4, one <note> element per chord member)."""
import html, json, re

UNITS = {'whole': 16, 'half': 8, 'quarter': 4, 'eighth': 2, '16th': 1}
FOOTER = re.compile(r'(copyright|©|\(c\)|all rights reserved|score revision|revision \d)', re.I)


def parse_metronome(spec):
    """'dotted-quarter=60', 'half=86', 'quarter.=60' -> (unit, dots, per_minute, quarters_per_minute)."""
    m = re.fullmatch(r'\s*(dotted-)?(whole|half|quarter|eighth|16th)(\.?)\s*=\s*(\d+(?:\.\d+)?)\s*', spec)
    if not m: raise ValueError(f'--metronome {spec!r}: use e.g. quarter=90, half=86, dotted-quarter=60')
    dots = 1 if (m.group(1) or m.group(3)) else 0
    unit, pm = m.group(2), float(m.group(4))
    q = pm * UNITS[unit] / 4 * (1.5 if dots else 1)
    fmt = lambda x: str(int(x)) if x == int(x) else str(round(x, 2))
    return unit, dots, fmt(pm), fmt(q)


def metronome_xml(spec, words=''):
    d = '<direction placement="above">'
    if words: d += f'<direction-type><words font-weight="bold">{html.escape(words)}</words></direction-type>'
    if spec:
        unit, dots, pm, q = parse_metronome(spec)
        d += f'<direction-type><metronome><beat-unit>{unit}</beat-unit>' + '<beat-unit-dot/>' * dots + f'<per-minute>{pm}</per-minute></metronome></direction-type><sound tempo="{q}"/>'
    return d + '</direction>'


def load_skip_words(spec, extra=()):
    """--skip-words: comma list, or a .json file holding a list (so words with commas can be listed); plus --skip-word items."""
    if spec.endswith('.json'):
        with open(spec) as f: words = list(json.load(f))
    else: words = spec.split(',') if spec else []
    return set(words) | set(extra)


def footer_lines(words):
    """(block, line) keys of page-text lines that are a footer or copyright notice (pymupdf 'words' tuples)."""
    lines = {}
    for w in words: lines.setdefault((w[5], w[6]), []).append(w)
    return {k for k, ws in lines.items() if FOOTER.search(' '.join(x[4] for x in sorted(ws, key=lambda x: x[0])))}


def copyright_text(words):
    """The printed copyright line (words joined in order), or '' when the page has none."""
    lines = {}
    for w in words: lines.setdefault((w[5], w[6]), []).append(w)
    for k in sorted(lines, key=lambda k: -lines[k][0][1]):
        t = ' '.join(x[4] for x in sorted(lines[k], key=lambda x: x[0]))
        if re.search(r'copyright|©|\(c\)', t, re.I): return t
    return ''


def keep_rows(row_ys, bot, limit, first_reach=48, sp=4.0):
    """Choose the lyric rows below a staff. row_ys: sorted row tops (pt). The first row must start within
    first_reach of the staff bottom; later rows are kept while each follows the previous one by no more than
    1.6 x the first row spacing (or 4 spaces), and the row stays above `limit` (the next staff's top).
    Returns the kept row tops; a row past a large gap (a footer, a title) is dropped."""
    out = []
    for y in row_ys:
        if y >= limit: break
        if not out:
            if y - bot > first_reach: break
            out.append(y); continue
        gap = y - out[-1]
        allowed = max(1.6 * (out[1] - out[0]), 4 * sp) if len(out) > 1 else 6 * sp
        if gap > allowed: break
        out.append(y)
    return out


# ---------------------------------------------------------------- string edits on the writer's output

def _parts(xml): return re.split(r'(?=<part id=)', xml)


def _measure(chunk, num):
    m = re.search(rf'<measure number="{num}"[^>]*>.*?</measure>', chunk, re.S)
    if not m: raise ValueError(f'no measure {num}')
    return m


def add_barline(xml, num, loc, inner, part=None):
    """<barline location=loc> with inner XML in measure num of every part (or 1-based part)."""
    ps = _parts(xml)
    for i in range(1, len(ps)):
        if part and i != part: continue
        m = _measure(ps[i], num); mx = m.group(0)
        if loc == 'left':
            head = re.match(r'<measure[^>]*>(?:<print [^>]*/>)?', mx).group(0)
            new = head + f'<barline location="left">{inner}</barline>' + mx[len(head):]
        else: new = mx[:-len('</measure>')] + f'<barline location="right">{inner}</barline></measure>'
        ps[i] = ps[i][:m.start()] + new + ps[i][m.end():]
    return ''.join(ps)


def final_barline(xml):
    n = re.findall(r'<measure number="(\d+)"', xml)[-1]
    return add_barline(xml, n, 'right', '<bar-style>light-heavy</bar-style>')


def breaks(xml, starts, pages=()):
    for n in sorted(set(starts) | set(pages)):
        attr = 'new-page="yes"' if n in pages else 'new-system="yes"'
        xml = re.sub(rf'(<measure number="{n}"[^>]*>)', rf'\1<print {attr}/>', xml)
    return xml


def abbreviations(xml, names):
    for i, ab in enumerate(names):
        if ab: xml = re.sub(rf'(<score-part id="P{i + 1}"><part-name>.*?</part-name>)',
                            lambda m: m.group(1) + f'<part-abbreviation>{html.escape(ab)}</part-abbreviation>', xml, count=1)
    return xml


def _note_at(chunk, num, voice, beat=None, note=None):
    """Span of the first <note> (not a chord member, not hidden) of voice in measure num starting at beat
    (1-based quarter beats, e.g. 2.5) or the note-th such note (0-based)."""
    m = _measure(chunk, num); ms = m.group(0); pos = 0; k = 0
    for t in re.finditer(r'<note[ >].*?</note>|<backup>.*?</backup>', ms, re.S):
        s = t.group(0); d = int(re.search(r'<duration>(\d+)', s).group(1))
        if s.startswith('<backup'): pos -= d; continue
        if '<chord/>' in s: continue
        if f'<voice>{voice}</voice>' in s and 'print-object="no"' not in s:
            if (beat is not None and abs(pos - (beat - 1) * 4) < 0.01) or (beat is None and k == note):
                return m.start() + t.start(), m.start() + t.end()
            k += 1
        pos += d
    raise ValueError(f'measure {num} voice {voice}: no note at beat {beat} / index {note}')


def _notate(chunk, span, tag):
    a, b = span; t = chunk[a:b]
    if '</notations>' in t: new = t.replace('</notations>', tag + '</notations>', 1)
    elif '<lyric' in t: new = t.replace('<lyric', f'<notations>{tag}</notations><lyric', 1)
    else: new = t[:-len('</note>')] + f'<notations>{tag}</notations></note>'
    return chunk[:a] + new + chunk[b:]


def _direction(chunk, num, inner, placement='above'):
    m = re.search(rf'<measure number="{num}"[^>]*>(?:<print [^>]*/>)?(?:<barline location="left">.*?</barline>)?(?:<attributes>.*?</attributes>)?', chunk, re.S)
    if not m: raise ValueError(f'no measure {num}')
    return chunk[:m.end()] + f'<direction placement="{placement}"><direction-type>{inner}</direction-type></direction>' + chunk[m.end():]


BARS = {'double': '<bar-style>light-light</bar-style>', 'final': '<bar-style>light-heavy</bar-style>',
        'repeat-start': '<bar-style>heavy-light</bar-style><repeat direction="forward"/>',
        'repeat-end': '<bar-style>light-heavy</bar-style><repeat direction="backward"/>'}


def apply_patch(xml, items):
    """items: list of dicts with "type" and "measure" (as numbered in the output), plus
    fermata: part, voice (1), beat or note, [placement "below"]   slur: part, voice, from/to (beats) or from_note/to_note
    barline: style double|final|repeat-start|repeat-end, [part]    volta: number, from, to (measures), [part]
    rehearsal / words / dynamics: text, [part] (default part 1)    Parts are 1-based."""
    for it in items:
        ty, num = it['type'], it['measure']; part = it.get('part'); v = it.get('voice', 1)
        if ty == 'barline':
            st = it['style']; loc = 'left' if st == 'repeat-start' else 'right'
            xml = add_barline(xml, num, loc, BARS[st], part); continue
        if ty == 'volta':
            n = it['number']; fr, to = it.get('from', num), it.get('to', num)
            xml = add_barline(xml, fr, 'left', f'<ending number="{n}" type="start"/>', part)
            end = it.get('end', 'stop' if str(n) == '1' else 'discontinue')
            xml = add_barline(xml, to, 'right', f'<ending number="{n}" type="{end}"/>', part); continue
        ps = _parts(xml); i = part or 1
        if ty in ('fermata', 'slur', 'accent', 'staccato', 'tenuto'):
            if ty == 'fermata':
                tag = '<fermata type="inverted"/>' if it.get('placement') == 'below' else '<fermata type="upright"/>'
                ps[i] = _notate(ps[i], _note_at(ps[i], num, v, it.get('beat'), it.get('note', 0 if 'beat' not in it else None)), tag)
            elif ty == 'slur':
                n_ = it.get('number', 1)
                end_num = it.get('to_measure', num)
                b = _note_at(ps[i], end_num, v, it.get('to'), it.get('to_note'))
                ps[i] = _notate(ps[i], b, f'<slur type="stop" number="{n_}"/>')
                a = _note_at(ps[i], num, v, it.get('from'), it.get('from_note'))
                ps[i] = _notate(ps[i], a, f'<slur type="start" number="{n_}"/>')
            else:
                ps[i] = _notate(ps[i], _note_at(ps[i], num, v, it.get('beat'), it.get('note', 0 if 'beat' not in it else None)), f'<articulations><{ty}/></articulations>')
        elif ty == 'rehearsal': ps[i] = _direction(ps[i], num, f'<rehearsal enclosure="square">{html.escape(it["text"])}</rehearsal>')
        elif ty == 'words': ps[i] = _direction(ps[i], num, f'<words>{html.escape(it["text"])}</words>', it.get('placement', 'above'))
        elif ty == 'dynamics': ps[i] = _direction(ps[i], num, f'<dynamics><{it["text"]}/></dynamics>', 'below')
        else: raise ValueError(f'--patch: unknown type {ty!r}')
        xml = ''.join(ps)
    return xml
