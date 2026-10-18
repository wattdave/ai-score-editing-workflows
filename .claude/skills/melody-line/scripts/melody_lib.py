"""Turn a MIDI melody track (or a hand-typed note list) into a one-staff MusicXML melody with lyrics.

Typical use (see melody_template.py beside this file):

    notes = read_notes("song.mid", track=2, channel=None)          # [(start_beats, end_beats, pitch)]
    events = quantize(notes, grid=0.5, unswing=True)               # [(onset, dur, pitch|None)] in beats
    events = window(events, first=24.0, last=120.0)                # keep one stretch, onsets re-based to 0
    write_xml(events, "out.xml", title="...", fifths=0, beats=4, beat_type=4, pickup=1.0, tempo=120,
              lyrics="Jin-gle bell _ jin-gle bell")
    print(dump(events, beats=4, pickup=1.0, lyrics=...))

Beats are quarter notes. Divisions are 12 per quarter (a 16th is 3, a triplet eighth is 4).
Lyrics: words separated by spaces, syllables by '-', '_' leaves a note without a syllable,
'/' is ignored (phrase marks for the human), a trailing '=' on a syllable continues it as the
next syllable's begin (not needed normally).
"""
from __future__ import annotations

import re
from fractions import Fraction

import mido

DIV = 12
NAMES = {48: ("whole", 0), 36: ("half", 1), 24: ("half", 0), 18: ("quarter", 1), 12: ("quarter", 0),
         9: ("eighth", 1), 6: ("eighth", 0), 3: ("16th", 0), 4: ("eighth", 0)}  # 4 = triplet eighth
ALLOWED = [48, 36, 24, 18, 12, 9, 6, 3]
BEAT = 12  # divisions per beat; layout() sets 18 for 12/8
SHARPS = {0: ("C", 0), 1: ("C", 1), 2: ("D", 0), 3: ("D", 1), 4: ("E", 0), 5: ("F", 0), 6: ("F", 1),
          7: ("G", 0), 8: ("G", 1), 9: ("A", 0), 10: ("A", 1), 11: ("B", 0)}
FLATS = {0: ("C", 0), 1: ("D", -1), 2: ("D", 0), 3: ("E", -1), 4: ("E", 0), 5: ("F", 0), 6: ("G", -1),
         7: ("G", 0), 8: ("A", -1), 9: ("A", 0), 10: ("B", -1), 11: ("B", 0)}


def read_notes(path, track=None, channel=None):
    """[(start, end, pitch)] in quarter-note beats, merged across the file, for one track/channel."""
    mid = mido.MidiFile(path)
    tpq = mid.ticks_per_beat
    out = []
    tracks = [mid.tracks[track]] if track is not None else mid.tracks
    for tr in tracks:
        t = 0
        on = {}
        for msg in tr:
            t += msg.time
            if msg.type == "note_on" and msg.velocity > 0 and (channel is None or msg.channel == channel):
                on.setdefault(msg.note, []).append(t)
            elif msg.type in ("note_off", "note_on") and (channel is None or getattr(msg, "channel", None) == channel):
                if msg.type == "note_off" or msg.velocity == 0:
                    if on.get(msg.note):
                        s = on[msg.note].pop(0)
                        out.append((s / tpq, t / tpq, msg.note))
    return sorted(out)


def first_tempo(path):
    mid = mido.MidiFile(path)
    for tr in mid.tracks:
        for msg in tr:
            if msg.type == "set_tempo":
                return round(mido.tempo2bpm(msg.tempo))
    return 120


def tempo_map(path):
    """[(beat, bpm)] for every tempo change."""
    mid = mido.MidiFile(path)
    tpq = mid.ticks_per_beat
    out = []
    for tr in mid.tracks:
        t = 0
        for msg in tr:
            t += msg.time
            if msg.type == "set_tempo":
                out.append((t / tpq, mido.tempo2bpm(msg.tempo)))
    return sorted(out)


def lyric_events(path, track=None):
    """[(beat, text)] of MIDI lyric/text meta events (karaoke files)."""
    mid = mido.MidiFile(path)
    tpq = mid.ticks_per_beat
    out = []
    tracks = [mid.tracks[track]] if track is not None else mid.tracks
    for tr in tracks:
        t = 0
        for msg in tr:
            t += msg.time
            if msg.type == "lyrics":
                out.append((t / tpq, msg.text))
    return sorted(out)


def _snap(x, grid):
    return round(x / grid) * grid


def quantize(notes, grid=0.5, unswing=False, rest_gap=0.75, legato=True, swing_from=0.5):
    """[(onset, dur, pitch|None)] in beats. Onsets snap to `grid`. With unswing, onsets whose
    fractional beat is near 2/3 (swung off-beat) snap to 1/2 first. A rest is written only when
    the silence between a note's end and the next onset is at least `rest_gap` beats."""
    ons = []
    for s, e, p in notes:
        if unswing:
            frac = s - int(s // 1)
            if abs(frac - 2 / 3) < 0.12:
                s = int(s // 1) + 0.5
            elif abs(frac - 1 / 3) < 0.12:
                s = int(s // 1) + 0.5 if False else s  # leave: triplet-ish pickups are handled by grid
        ons.append((_snap(s, grid), e, p))
    ons.sort()
    # collapse simultaneous onsets (keep the top note)
    dedup = []
    for s, e, p in ons:
        if dedup and abs(dedup[-1][0] - s) < 1e-6:
            if p > dedup[-1][2]:
                dedup[-1] = (s, e, p)
        else:
            dedup.append((s, e, p))
    ev = []
    for i, (s, e, p) in enumerate(dedup):
        nxt = dedup[i + 1][0] if i + 1 < len(dedup) else None
        if nxt is None:
            end = max(_snap(e, grid), s + grid)
        else:
            end_raw = e
            gap = nxt - end_raw
            end = nxt if (legato and gap < rest_gap and (gap < 0.75 or e - s < 1.0)) else max(_snap(end_raw, grid), s + grid)
            if end > nxt:
                end = nxt
        ev.append([s, end - s, p])
        if nxt is not None and nxt - end > 1e-6:
            ev.append([end, nxt - end, None])
    return [tuple(x) for x in ev]


def window(events, first, last):
    """Keep events whose onset is in [first, last); re-base onsets to 0 at `first`."""
    return [(s - first, d, p) for s, d, p in events if first - 1e-6 <= s < last - 1e-6]


def transpose(events, semitones):
    return [(s, d, None if p is None else p + semitones) for s, d, p in events]


def spell(pitch, fifths, prefer_flats=None):
    flats = (fifths < 0) if prefer_flats is None else prefer_flats
    step, alter = (FLATS if flats else SHARPS)[pitch % 12]
    return step, alter, pitch // 12 - 1


def parse_lyrics(text):
    """-> list of (syllable|None, syllabic). None = note without a syllable ('_')."""
    out = []
    for word in text.split():
        if word == "/":
            continue
        if word == "_":
            out.append((None, None))
            continue
        parts = word.split("-")
        parts = [p for p in parts]
        for i, p in enumerate(parts):
            if p == "":
                continue
            n = len(parts)
            syl = "single" if n == 1 else "begin" if i == 0 else "end" if i == n - 1 else "middle"
            out.append((p.replace("_", " "), syl))
    return out


def _chunks(pos, dur, bar_len):
    """Split a duration (divisions) starting at bar-relative `pos` into allowed note values that do
    not cross the bar and stay beat-aligned where possible."""
    out = []
    while dur > 0:
        room = bar_len - pos
        for L in ALLOWED:
            if BEAT == 18:  # 12/8: beats are dotted quarters
                ok = L == dur or (L in (36, 18) and pos % 18 == 0) or (L == 12 and pos % 18 in (0, 6)) or L in (24, 6, 3)
            else:
                ok = pos % (12 if L == 9 else min(L, 12)) == 0 and (L < 24 or pos % 12 == 0)
            if L <= dur and L <= room and ok:
                out.append(L)
                pos += L
                dur -= L
                break
        else:
            L = 3 if dur >= 3 else dur
            out.append(L)
            pos += L
            dur -= L
    return out


def layout(events, beats, beat_type, pickup=0.0):
    """-> list of bars; each bar a list of (kind, pitch, dur_div, tie_in, tie_out, note_index|None)."""
    global BEAT
    BEAT = 18 if (beats, beat_type) in ((12, 8), (9, 8)) else 12
    bar_len = int(beats * DIV * 4 / beat_type)
    pk = int(round(pickup * DIV))
    lens = []
    total = int(round(sum(d for _, d, _ in events) * DIV))
    if pk:
        lens.append(pk)
        total -= pk
    while total > 0:
        lens.append(min(bar_len, total))
        total -= bar_len
    bars = [[] for _ in lens]
    bi, pos = 0, 0
    nidx = 0
    for s, d, p in events:
        dur = int(round(d * DIV))
        first = True
        pieces = []
        while dur > 0:
            room = lens[bi] - pos if bi < len(lens) else dur
            take = min(dur, room)
            for c in _chunks(pos, take, lens[bi]):
                pieces.append((bi, c))
                pos += c
            dur -= take
            if pos >= lens[bi]:
                bi += 1
                pos = 0
        for k, (b, c) in enumerate(pieces):
            kind = "rest" if p is None else "note"
            bars[b].append([kind, p, c, k > 0 and kind == "note", k < len(pieces) - 1 and kind == "note",
                            (nidx if k == 0 and kind == "note" else None)])
        if p is not None:
            nidx += 1
    return bars


def note_name(p, fifths):
    step, alter, octave = spell(p, fifths)
    return f"{step}{'#' if alter == 1 else 'b' if alter == -1 else ''}{octave}"


def dump(events, beats, beat_type, pickup=0.0, fifths=0, lyrics=""):
    syl = parse_lyrics(lyrics)
    bars = layout(events, beats, beat_type, pickup)
    out, si = [], 0
    first_bar = 0 if pickup else 1
    for i, bar in enumerate(bars):
        parts = []
        for kind, p, c, tin, tout, idx in bar:
            if kind == "rest":
                parts.append(f"r{c}")
                continue
            txt = ""
            if idx is not None:
                if si < len(syl):
                    t = syl[si][0]
                    txt = f'"{t}"' if t else "_"
                si += 1
            parts.append(f"{note_name(p, fifths)}:{c}{'~' if tout else ''}{txt}")
        out.append(f"{i + first_bar:3d}: " + " ".join(parts))
    n_notes = sum(1 for b in bars for x in b if x[5] is not None)
    out.append(f"-- {n_notes} notes, {len(syl)} syllables ({'MATCH' if n_notes == len(syl) else 'MISMATCH'})")
    return "\n".join(out)


def write_xml(events, path, title, fifths, beats, beat_type, pickup=0.0, tempo=120, lyrics="",
              part_name="Melody", prefer_flats=None, tempo_changes=None, clef=("G", 2), metronome=None):
    """tempo_changes: {bar_index (0-based in the written bars): bpm}. metronome: (beat_unit, dots, bpm) for the
    printed mark when it differs from `tempo` (quarter-note bpm), e.g. ("quarter", 1, 147) in 12/8."""
    syl = parse_lyrics(lyrics)
    bars = layout(events, beats, beat_type, pickup)
    L = []
    w = L.append
    w('<?xml version="1.0" encoding="UTF-8"?>')
    w('<score-partwise version="3.1"><work><work-title>%s</work-title></work>' % title)
    w('<part-list><score-part id="P1"><part-name>%s</part-name></score-part></part-list><part id="P1">' % part_name)
    si = 0
    for i, bar in enumerate(bars):
        num = i if pickup else i + 1
        attrs = ' implicit="yes"' if (pickup and i == 0) else ""
        w(f'<measure number="{num}"{attrs}>')
        if i == 0:
            w(f"<attributes><divisions>{DIV}</divisions><key><fifths>{fifths}</fifths></key>"
              f"<time><beats>{beats}</beats><beat-type>{beat_type}</beat-type></time>"
              f"<clef><sign>{clef[0]}</sign><line>{clef[1]}</line></clef></attributes>")
            if metronome:
                unit, dots, bpm = metronome
                w('<direction placement="above"><direction-type><metronome><beat-unit>%s</beat-unit>%s'
                  '<per-minute>%s</per-minute></metronome></direction-type><sound tempo="%s"/></direction>'
                  % (unit, "<beat-unit-dot/>" * dots, bpm, tempo))
            else:
                w(f'<direction placement="above"><direction-type><words> </words></direction-type><sound tempo="{tempo}"/></direction>')
        elif tempo_changes and i in tempo_changes:
            w(f'<direction placement="above"><direction-type><words> </words></direction-type><sound tempo="{tempo_changes[i]}"/></direction>')
        for kind, p, c, tin, tout, idx in bar:
            if kind == "rest":
                w(f"<note><rest/><duration>{c}</duration><voice>1</voice><type>{NAMES[c][0]}</type>"
                  + "<dot/>" * NAMES[c][1] + "</note>")
                continue
            step, alter, octv = spell(p, fifths, prefer_flats)
            x = f"<note><pitch><step>{step}</step>"
            if alter:
                x += f"<alter>{alter}</alter>"
            x += f"<octave>{octv}</octave></pitch><duration>{c}</duration>"
            if tin:
                x += '<tie type="stop"/>'
            if tout:
                x += '<tie type="start"/>'
            x += f"<voice>1</voice><type>{NAMES[c][0]}</type>" + "<dot/>" * NAMES[c][1]
            nt = ""
            if tin:
                nt += '<tied type="stop"/>'
            if tout:
                nt += '<tied type="start"/>'
            if nt:
                x += f"<notations>{nt}</notations>"
            if idx is not None:
                if si < len(syl):
                    t, sy = syl[si]
                    if t:
                        x += f'<lyric number="1"><syllabic>{sy}</syllabic><text>{t}</text></lyric>'
                si += 1
            w(x + "</note>")
        if i == len(bars) - 1:
            w('<barline location="right"><bar-style>light-heavy</bar-style></barline>')
        w("</measure>")
    w("</part></score-partwise>")
    open(path, "w").write("\n".join(L))
    n_notes = sum(1 for b in bars for x in b if x[5] is not None)
    return n_notes, len(syl)


def parse_notes(text, bar_marks=True):
    """Hand-typed melody -> events in beats. Tokens: 'G4:2' (pitch+octave, ':' duration in beats),
    'F#4:.5', 'Bb3:1.5', 'r:1' for a rest. '|' is ignored (barline marks for the human)."""
    pcs = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
    ev, t = [], 0.0
    for tok in text.split():
        if tok == "|":
            continue
        name, dur = tok.split(":")
        d = float(Fraction(dur)) if "/" in dur else float(dur)
        if name == "r":
            ev.append((t, d, None))
        else:
            m = re.match(r"([A-G])([#b]?)(-?\d)", name)
            p = pcs[m.group(1)] + {"#": 1, "b": -1, "": 0}[m.group(2)] + 12 * (int(m.group(3)) + 1)
            ev.append((t, d, p))
        t += d
    return ev


def swing(events, phase=0.0):
    """Re-time straight eighths as a 2:1 swing in 12/8: each beat becomes 1.5 quarter-lengths, an off-beat eighth
    starts 1.0 after its beat. `phase` = beat position (0-1) of the first event (a pickup starts mid-beat).
    Write the result with beats=12, beat_type=8 and 1.5x the quarter tempo; pickup = its straight length."""
    def sw(t):
        n, f = int(t // 1), t - int(t // 1)
        if abs(f) > 1e-6 and abs(f - 0.5) > 1e-6:
            raise ValueError(f"off-grid time {t}")
        return n * 1.5 + (1.0 if f > 0.25 else 0.0)
    base = sw(phase)
    return [(sw(s + phase) - base, sw(s + d + phase) - sw(s + phase), p) for s, d, p in events]


def swing_playback(events, phase=0.0, bar_q=6.0, pickup_q=0.0):
    """swing() plus the playback fixes. Tied notes drone in Sibelius's Cantai playback, so no note is tied inside a
    bar: a duration that is not one note value (e.g. 30 or 42 divisions) is played as the largest single value and
    the remainder is rested (a small breath). A note crossing a barline keeps the one tie it needs when both halves
    are single values. The final note becomes one dotted half with the rest of the bar rested out."""
    SING = (48, 36, 24, 18, 12, 6, 3)
    sev = swing(events, phase)
    out = []
    for s_, d_, p_ in sev:
        if p_ is None:
            out.append((s_, d_, p_))
            continue
        D = int(round(d_ * 12))
        start = s_ - pickup_q
        edge = None
        if start >= 0:
            nb = (int(start // bar_q + 1e-9) + 1) * bar_q + pickup_q
            if s_ + d_ > nb + 1e-6:
                edge = nb
        elif s_ + d_ > pickup_q + 1e-6:
            edge = pickup_q
        if edge is None:
            ok = D in SING
        else:
            a, b = int(round((edge - s_) * 12)), int(round((s_ + d_ - edge) * 12))
            ok = a in SING and b in SING
        if ok:
            out.append((s_, d_, p_))
            continue
        if edge is None:
            single = max(v for v in SING if v <= D)
        else:
            a = int(round((edge - s_) * 12))
            single = a + max(v for v in SING if v <= D - a) if a in SING and D - a >= 3 else max(v for v in SING if v <= min(D, a))
        out += [(s_, single / 12, p_), (s_ + single / 12, d_ - single / 12, None)]
    s_, d_, p_ = out[-1]
    if p_ is not None and d_ > 3:
        out[-1:] = [(s_, 3.0, p_), (s_ + 3.0, d_ - 3.0, None)]
    return out


def write_swing_xml(events, path, title, fifths, beats, beat_type, pickup=0.0, tempo=120, lyrics="", **kw):
    """Write the swing playback copy of a straight-eighth line: 4/4 -> 12/8, 3/4 -> 9/8, the beat becomes a dotted
    quarter (printed mark: dotted quarter = `tempo`), quarter-note playback tempo is 1.5x."""
    assert beat_type == 4
    phase = (1.0 - pickup) % 1.0  # a pickup ends on a beat
    pk = swing([(0.0, pickup, 60)], phase)[0][1] if pickup else 0.0
    return write_xml(swing_playback(events, phase, beats * 1.5, pk), path, title, fifths, beats * 3, 8, pickup=pk,
                     tempo=int(tempo * 1.5), lyrics=lyrics, metronome=("quarter", 1, tempo), **kw)
