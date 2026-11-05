#!/usr/bin/env python3
"""Propose system and page breaks for a MusicXML file by musical phrase.

OMR output has no system or page breaks, and copying the source print's
breaks is not the goal: breaks should fall where the music breathes, with
lines of similar length. This script detects phrase ends, then chooses
breaks by dynamic programming for several candidate layouts (wide, medium,
narrow) so a person can compare them and say which reads best.

Standard library only, so the skill runs without the rest of this repository.

Usage:
    propose_breaks.py IN [--candidates wide,medium,narrow] [--json] [--page-bars N]
    propose_breaks.py IN --apply NAME --out OUT.xml [--page-bars N]

IN may be .xml, .musicxml or .mxl; output is plain MusicXML. --apply writes
<print new-system="yes"/> into the first measure of every system in EVERY
part (and new-page="yes" at page starts with --page-bars). Notes are never
touched, and the XML declaration and DOCTYPE are preserved.

A candidate is a name from CANDIDATES (wide, medium, narrow) or a number,
taken as the target bars per system without density scaling.

Cost model (all weights in W, below)
------------------------------------
A layout is a list of systems. Its cost is the sum, over systems, of:

  size      W["size"] * (length - target)**2       far from the target size
  uneven    W["uneven"] * (length - previous)**2   neighbouring systems differ
  break     W["off_phrase"] * (1 - min(score, PHRASE_CAP) / PHRASE_CAP)
            a break after a bar costs more the weaker that bar's phrase-end
            score is (score 0 = mid-phrase, PHRASE_CAP or more = free)
  tie       W["tie"]            a break splits a tied note
  orphan    W["orphan1"] / W["orphan2"]   last system of one or two bars
  short     W["short_final"] * (0.5 * target - length)**2   last system under
            half the target
  last_note W["last_note"]      break right before a final bar that holds
            only its last note (a dangling closing chord or note)

Forbidden: a break between a pickup bar and the bar after it; systems longer
than max_len bars. Length counts a pickup bar as its fraction of a full bar.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

# ---- tunables -------------------------------------------------------------

W = {
    "size": 1.0,
    "uneven": 1.0,
    "off_phrase": 6.0,
    "tie": 2.0,
    "orphan1": 30.0,
    "orphan2": 8.0,
    "short_final": 2.0,
    "last_note": 10.0,
}

# Phrase-end signals and their scores. A bar's score is the sum of its signals.
SIGNALS = {
    "lyric-sentence": 3.0,     # last lyric ends with . ! ?
    "lyric-semicolon": 2.0,    # last lyric ends with ; or :
    "lyric-comma": 1.0,        # last lyric ends with ,
    "fermata": 3.0,
    "barline": 3.0,            # double bar, final-style bar or backward repeat
    "forward-repeat": 2.0,     # next bar opens a repeat
    "rest": 2.0,               # bar ends with a rest of a beat or more
    "rest-bar": 2.0,           # every part rests in the whole bar (added to rest)
    "long-note": 1.5,          # melody ends on a note of half a bar or more
    "key-time-change": 2.0,    # next bar changes key or time signature
    "tempo-change": 2.0,       # next bar carries a tempo mark
    "rehearsal": 2.0,          # next bar carries a rehearsal mark
    "volta": 2.0,              # next bar starts a first/second ending
    "periodicity": 1.0,        # full bar number is a multiple of 4
    "periodicity-8": 0.5,      # ... and of 8
}
PHRASE_MIN = 2.0   # score at or above which a break counts as "phrase end"
PHRASE_CAP = 4.0   # score at which the break cost reaches zero

# Candidate layouts: base target bars per system (scaled by density).
CANDIDATES = {"wide": 5.5, "medium": 4.0, "narrow": 3.0}
REF_LOAD = 8.0     # notes per bar (busiest part) that counts as normal density
SCALE_MIN, SCALE_MAX = 0.75, 1.2
# Stacked verses need room under the notes: the longest system allowed, by number of verses.
# Lesson 2026-11-05 (Deck the Halls, 3 verses): 8 bars per system crushed and collided the lyrics.
VERSE_CAPS = {2: 6, 3: 4}   # 3 or more verses -> at most 4 bars per system
MAX_LEN_FACTOR = 1.75  # longest allowed system = target * factor + 1

BARLINE_STYLES = {"light-light", "light-heavy", "heavy-light", "heavy-heavy"}


# ---- reading --------------------------------------------------------------

def read_text(path: Path) -> str:
    if path.suffix.lower() == ".mxl":
        with zipfile.ZipFile(path) as z:
            name = next(n for n in z.namelist() if n.endswith((".xml", ".musicxml")) and not n.startswith("META-INF"))
            return z.read(name).decode("utf-8")
    return path.read_text(encoding="utf-8")


def header_of(text: str) -> str:
    """Everything before the root element (XML declaration and DOCTYPE), so it survives."""
    m = re.search(r"<score-(partwise|timewise)\b", text)
    return text[: m.start()] if m else ""


def _int(el: ET.Element | None, default: int) -> int:
    try:
        return int(float(el.text)) if el is not None and el.text else default
    except ValueError:
        return default


class Bar:
    """What the proposer needs to know about one measure index (all parts merged)."""

    def __init__(self, index: int, label: str):
        self.index = index
        self.label = label
        self.beats, self.beat_type = 4, 4
        self.quarters = 4.0          # nominal length in quarter notes
        self.length = 0.0            # actual length in quarters (longest part)
        self.notes = 0               # most notes in one part (chords counted once)
        self.signals: dict[str, float] = {}
        self.final_only = False      # bar holds a single sounding note or chord
        self.tie_out = False         # a note is tied into the next bar
        self.lyric_chars: list[int] = []
        self.verses = 0              # most lyric lines under one note
        self.pickup = False

    @property
    def score(self) -> float:
        return sum(self.signals.values())

    @property
    def weight(self) -> float:
        return max(0.25, min(1.0, self.length / self.quarters)) if self.pickup else 1.0


def _read_part(part: ET.Element, n: int) -> tuple[list[dict], int]:
    """Per-measure facts for one part, and how many lyric syllables it has."""
    divisions, beats, beat_type, key = 1, 4, 4, None
    rows: list[dict] = []
    lyrics = 0
    for i, m in enumerate(part.findall("measure")[:n]):
        info: dict = {"events": [], "fermata": False, "last_lyric": None, "barline": False, "fwd": False,
                      "tempo": False, "reh": False, "volta": False, "keychg": False, "timechg": False,
                      "lyric_chars": [], "verses": 0}
        for a in m.findall("attributes"):
            if a.find("divisions") is not None:
                divisions = _int(a.find("divisions"), divisions)
            t = a.find("time")
            if t is not None:
                nb, nt = _int(t.find("beats"), beats), _int(t.find("beat-type"), beat_type)
                if (nb, nt) != (beats, beat_type) and i > 0:
                    info["timechg"] = True
                beats, beat_type = nb, nt
            k = a.find("key")
            if k is not None:
                new = (_int(k.find("fifths"), 0), k.findtext("mode") or "")
                if key is not None and new != key and i > 0:
                    info["keychg"] = True
                key = new
        info["beats"], info["beat_type"], info["divisions"] = beats, beat_type, divisions
        cursor = longest = 0
        for el in m:
            if el.tag == "note":
                chord = el.find("chord") is not None
                grace = el.find("grace") is not None
                dur = 0 if grace else _int(el.find("duration"), 0)
                if chord and info["events"]:
                    onset = info["events"][-1]["onset"]
                else:
                    onset = cursor
                    cursor += dur
                    longest = max(longest, cursor)
                ev = {"onset": onset, "dur": dur, "rest": el.find("rest") is not None, "chord": chord,
                      "tie": any(t.get("type") == "start" for t in el.findall("tie"))}
                texts = [(ly.findtext("text") or "") for ly in el.findall("lyric")]
                if any(texts):
                    lyrics += 1
                    info["last_lyric"] = (onset, " ".join(t for t in texts if t))
                    info["lyric_chars"].extend(len(t) for t in texts if t)
                    info["verses"] = max(info["verses"], sum(1 for t in texts if t))
                if not grace:
                    info["events"].append(ev)
                if el.find(".//fermata") is not None:
                    info["fermata"] = True
            elif el.tag == "backup":
                cursor -= _int(el.find("duration"), 0)
            elif el.tag == "forward":
                cursor += _int(el.find("duration"), 0)
                longest = max(longest, cursor)
            elif el.tag == "direction":
                if el.find(".//rehearsal") is not None:
                    info["reh"] = True
                if el.find(".//metronome") is not None or el.find("sound[@tempo]") is not None:
                    info["tempo"] = True
            elif el.tag == "sound" and el.get("tempo"):
                info["tempo"] = True
            elif el.tag == "barline":
                rep = el.find("repeat")
                ending = el.find("ending")
                if el.get("location", "right") == "left":
                    if rep is not None and rep.get("direction") == "forward":
                        info["fwd"] = True
                    if ending is not None and ending.get("type") == "start":
                        info["volta"] = True
                elif (rep is not None and rep.get("direction") == "backward") or el.findtext("bar-style") in BARLINE_STYLES:
                    info["barline"] = True
        info["length"] = longest / divisions
        rows.append(info)
    return rows, lyrics


def analyse(root: ET.Element) -> tuple[list[Bar], list[str]]:
    """Return (bars, warnings). Bars are indexed by measure position across parts."""
    warnings: list[str] = []
    parts = root.findall("part")
    if not parts:
        return [], ["no parts"]
    counts = [len(p.findall("measure")) for p in parts]
    n = min(counts)
    if len(set(counts)) > 1:
        warnings.append(f"parts have different measure counts {counts}; aligned by position, first {n} used")
    bars = [Bar(i, m.get("number", str(i + 1))) for i, m in enumerate(parts[0].findall("measure")[:n])]
    per_part, lyric_count = [], []
    for part in parts:
        rows, lyrics = _read_part(part, n)
        per_part.append(rows)
        lyric_count.append(lyrics)
    melody = max(range(len(parts)), key=lambda k: (lyric_count[k], -k))
    for i, bar in enumerate(bars):
        rows = [pp[i] for pp in per_part]
        mel = rows[melody]
        bar.beats, bar.beat_type = mel["beats"], mel["beat_type"]
        bar.quarters = bar.beats * 4.0 / bar.beat_type
        bar.length = max(r["length"] for r in rows)
        bar.pickup = i == 0 and n > 1 and 0 < bar.length < bar.quarters * 0.999
        bar.notes = max(sum(1 for e in r["events"] if not e["rest"] and not e["chord"]) for r in rows)
        bar.lyric_chars = [c for r in rows for c in r["lyric_chars"]]
        bar.verses = max(r["verses"] for r in rows)
        bar.final_only = sum(1 for e in mel["events"] if not e["rest"] and not e["chord"]) <= 1
        bar.tie_out = any(e["tie"] for r in rows for e in r["events"])
    for i, bar in enumerate(bars):
        _signals(bars, i, [pp[i] for pp in per_part], per_part[melody][i], [pp[i + 1] for pp in per_part] if i + 1 < n else [])
    return bars, warnings


def _signals(bars: list[Bar], i: int, rows: list[dict], mel: dict, nxt: list[dict]) -> None:
    """Fill bars[i].signals: how strongly the music ends a phrase after bar i."""
    bar = bars[i]
    sig = bar.signals
    latest = [r["last_lyric"] for r in rows if r["last_lyric"]]
    if latest:
        onset = max(x[0] for x in latest)
        text = " ".join(x[1] for x in latest if x[0] == onset).strip().rstrip("\"')]”’»")
        if text.endswith((".", "!", "?")):
            sig["lyric-sentence"] = SIGNALS["lyric-sentence"]
        elif text.endswith((";", ":")):
            sig["lyric-semicolon"] = SIGNALS["lyric-semicolon"]
        elif text.endswith(","):
            sig["lyric-comma"] = SIGNALS["lyric-comma"]
    if any(r["fermata"] for r in rows):
        sig["fermata"] = SIGNALS["fermata"]
    if any(r["barline"] for r in rows):
        sig["barline"] = SIGNALS["barline"]
    evs = [e for e in mel["events"] if not e["chord"]]
    div = mel["divisions"]
    if evs:
        last = evs[-1]
        if last["rest"]:
            if last["dur"] / div >= 1.0:
                sig["rest"] = SIGNALS["rest"]
        elif not last["tie"]:
            durs = sorted(e["dur"] for e in evs if not e["rest"])
            median = durs[len(durs) // 2]
            if last["dur"] / div >= bar.quarters * 0.5 and last["dur"] >= 2 * median:
                sig["long-note"] = SIGNALS["long-note"]
    if all(r["events"] and all(e["rest"] for e in r["events"]) for r in rows):
        sig["rest-bar"] = SIGNALS["rest-bar"]
    if any(r["keychg"] or r["timechg"] for r in nxt):
        sig["key-time-change"] = SIGNALS["key-time-change"]
    if any(r["tempo"] for r in nxt):
        sig["tempo-change"] = SIGNALS["tempo-change"]
    if any(r["reh"] for r in nxt):
        sig["rehearsal"] = SIGNALS["rehearsal"]
    if any(r["volta"] for r in nxt):
        sig["volta"] = SIGNALS["volta"]
    if any(r["fwd"] for r in nxt):
        sig["forward-repeat"] = SIGNALS["forward-repeat"]
    full = i + 1 - (1 if bars[0].pickup else 0)
    if full > 0 and full % 4 == 0 and i + 1 < len(bars):
        sig["periodicity"] = SIGNALS["periodicity"]
        if full % 8 == 0:
            sig["periodicity-8"] = SIGNALS["periodicity-8"]


# ---- layout ---------------------------------------------------------------

def density_scale(bars: list[Bar]) -> tuple[float, dict]:
    """Return (scale, facts). Dense bars, long syllables and long bars take fewer per system."""
    notes = [b.notes for b in bars if not b.pickup] or [b.notes for b in bars]
    per_bar = sum(notes) / max(1, len(notes))
    chars = [c for b in bars for c in b.lyric_chars]
    syl = sum(chars) / len(chars) if chars else 3.0
    quarters = sum(b.quarters for b in bars) / max(1, len(bars))
    load = per_bar * (1 + 0.05 * max(0.0, syl - 3.0)) * math.sqrt(max(quarters, 1.0) / 4.0)
    scale = 1.0 if load <= 0 else max(SCALE_MIN, min(SCALE_MAX, math.sqrt(REF_LOAD / load)))
    return scale, {"notes_per_bar": round(per_bar, 1), "syllable_chars": round(syl, 1),
                   "bar_quarters": round(quarters, 1), "load": round(load, 1), "scale": round(scale, 2)}


def verse_cap(bars: list[Bar]) -> int | None:
    """Longest system (in bars) that the stacked verses allow, or None when unconstrained."""
    verses = max((b.verses for b in bars), default=0)
    for v in sorted(VERSE_CAPS, reverse=True):
        if verses >= v:
            return VERSE_CAPS[v]
    return None


def solve(bars: list[Bar], target: float, max_bars: int | None = None) -> tuple[list[int], float]:
    """Return (system start indices, cost), minimising the cost model by DP over (start, end)."""
    n = len(bars)
    if n == 0:
        return [], 0.0
    pre = [0.0]
    for b in bars:
        pre.append(pre[-1] + b.weight)
    max_len = max(2, int(target * MAX_LEN_FACTOR) + 1)
    if max_bars is not None:
        max_len = max(2, min(max_len, max_bars))
    pickup = bars[0].pickup
    last_only = n >= 2 and bars[-1].final_only

    def length(s: int, e: int) -> float:
        return pre[e] - pre[s]

    def own(s: int, e: int) -> float:
        L = length(s, e)
        c = W["size"] * (L - target) ** 2
        if e < n:
            c += W["off_phrase"] * (1 - min(bars[e - 1].score, PHRASE_CAP) / PHRASE_CAP)
            if bars[e - 1].tie_out:
                c += W["tie"]
            if last_only and e == n - 1:
                c += W["last_note"]
        else:
            if e - s <= 1:
                c += W["orphan1"]
            elif e - s <= 2:
                c += W["orphan2"]
            c += W["short_final"] * max(0.0, 0.5 * target - L) ** 2
        return c

    inf = float("inf")
    best: dict[tuple[int, int], tuple[float, tuple[int, int] | None]] = {}
    for e in range(1, min(n, max_len) + 1):
        if pickup and e == 1 and n > 1:
            continue  # no break between a pickup and its first bar
        best[(0, e)] = (own(0, e), None)
    for s in range(1, n):
        for e in range(s + 1, min(n, s + max_len) + 1):
            c_best, back = inf, None
            for p in range(max(0, s - max_len), s):
                prev = best.get((p, s))
                if prev is None:
                    continue
                c = prev[0] + W["uneven"] * (length(p, s) - length(s, e)) ** 2
                if c < c_best:
                    c_best, back = c, (p, s)
            if back is not None:
                best[(s, e)] = (c_best + own(s, e), back)
    finals = [(v[0], k) for k, v in best.items() if k[1] == n]
    if not finals:
        return [0], own(0, n)
    cost, key = min(finals)
    starts = []
    while key is not None:
        starts.append(key[0])
        key = best[key][1]
    return sorted(starts), cost


def reason(bars: list[Bar], idx: int) -> str:
    """Explain a break placed after bar index idx."""
    b = bars[idx]
    names = ", ".join(sorted(b.signals, key=lambda k: -b.signals[k]))
    if b.score >= PHRASE_MIN:
        return f"phrase end after bar {b.label} because of: {names}"
    if b.score > 0:
        return f"weak phrase end after bar {b.label} ({names} only)"
    if not any(x.score >= PHRASE_MIN for x in bars[:-1]):
        return f"compromise: broke after bar {b.label} by size; the piece has no phrase signals"
    nxt = next((j for j in range(idx + 1, len(bars) - 1) if bars[j].score >= PHRASE_MIN), None)
    if nxt is None:
        return f"compromise: broke mid-phrase after bar {b.label}; no later phrase end"
    gap = nxt - idx
    return (f"compromise: broke mid-phrase after bar {b.label}; next phrase end is after bar "
            f"{bars[nxt].label}, {gap} bar{'s' if gap != 1 else ''} away")


def resolve_candidates(spec: str, scale: float) -> list[tuple[str, float]]:
    out = []
    for name in (x.strip() for x in spec.split(",") if x.strip()):
        if name in CANDIDATES:
            out.append((name, max(2.0, min(8.0, round(CANDIDATES[name] * scale * 2) / 2))))
        else:
            try:
                out.append((name, float(name)))
            except ValueError:
                raise SystemExit(f"error: unknown candidate {name!r} (use {', '.join(CANDIDATES)} or a number)")
    return out


def page_starts(bars: list[Bar], starts: list[int], page_bars: int) -> list[int]:
    """Pick system starts (never the first) that begin a new page, about every page_bars bars."""
    if not page_bars or len(starts) < 3:
        return []
    pages: list[int] = []
    pool = starts[1:]
    last = 0
    while len(bars) - last > page_bars * 1.35:
        ideal = last + page_bars
        window = [s for s in pool if s > last and abs(s - ideal) <= max(2, page_bars // 3)]
        if not window:
            window = [s for s in pool if s > last]
            if not window:
                break
        # nearer the ideal and after a stronger phrase end or rest is better
        pick = max(window, key=lambda s: bars[s - 1].score - abs(s - ideal) * 0.75)
        if len(bars) - pick < page_bars * 0.35:
            break
        pages.append(pick)
        last = pick
    return pages


def layouts(bars: list[Bar], spec: str, page_bars: int = 0) -> tuple[list[dict], dict]:
    scale, facts = density_scale(bars)
    cap = verse_cap(bars)
    facts["verses"] = max((b.verses for b in bars), default=0)
    if cap is not None:
        facts["max_bars_per_system"] = cap
    result = []
    for name, target in resolve_candidates(spec, scale):
        capped = cap is not None and target > cap
        if capped:
            target = float(cap)
        starts, cost = solve(bars, target, cap)
        pages = page_starts(bars, starts, page_bars)
        systems = []
        for k, s in enumerate(starts):
            e = starts[k + 1] if k + 1 < len(starts) else len(bars)
            systems.append({
                "system": k + 1, "first_bar": bars[s].label, "last_bar": bars[e - 1].label, "bars": e - s,
                "new_page": s in pages,
                "break_after": None if e == len(bars) else reason(bars, e - 1),
                "break_score": None if e == len(bars) else round(bars[e - 1].score, 1),
            })
        result.append({"name": name, "target": target, "capped_by_verses": capped, "cost": round(cost, 1), "starts": starts, "pages": pages,
                       "sizes": [s["bars"] for s in systems], "systems": systems})
    return result, facts


def format_text(title: str, bars: list[Bar], cands: list[dict], facts: dict, warnings: list[str]) -> str:
    lines = [f"{title}: {len(bars)} bars, {bars[0].beats}/{bars[0].beat_type}" + (", pickup bar" if bars[0].pickup else "")]
    lines.append("density: " + ", ".join(f"{k}={v}" for k, v in facts.items()))
    ends = [f"{b.label}({b.score:g})" for b in bars[:-1] if b.score >= PHRASE_MIN]
    lines.append("phrase ends after bars (score): " + (", ".join(ends) or "none found"))
    lines += [f"warning: {w}" for w in warnings]
    for c in cands:
        lines += ["", f"== {c['name']}: target {c['target']:g} bars/system, {len(c['systems'])} systems, "
                      f"sizes {'-'.join(map(str, c['sizes']))}, cost {c['cost']}"
                  + (f" (capped: {facts['verses']} stacked verses leave room for {facts['max_bars_per_system']} bars at most)"
                     if c.get("capped_by_verses") else ""),
                  f"{'sys':>3}  {'bars':<9} {'n':>2}  break"]
        for s in c["systems"]:
            rng = s["first_bar"] if s["first_bar"] == s["last_bar"] else f"{s['first_bar']}-{s['last_bar']}"
            page = " [new page]" if s["new_page"] else ""
            lines.append(f"{s['system']:>3}  {rng:<9} {s['bars']:>2}  {s['break_after'] or '(end of piece)'}{page}")
    return "\n".join(lines)


# ---- applying -------------------------------------------------------------

def apply_breaks(root: ET.Element, starts: list[int], pages: set[int]) -> int:
    """Write system/page breaks into the first measure of each system in every part."""
    count = 0
    for part in root.findall("part"):
        measures = part.findall("measure")
        for s in starts[1:]:
            if s >= len(measures):
                continue
            pr = measures[s].find("print")
            if pr is None:
                pr = ET.Element("print")
                measures[s].insert(0, pr)
            pr.set("new-system", "yes")
            if s in pages:
                pr.set("new-page", "yes")
            count += 1
    return count


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input")
    ap.add_argument("--candidates", default="wide,medium,narrow")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--apply", metavar="NAME", help="write the named candidate's breaks (requires --out)")
    ap.add_argument("--out", help="output MusicXML path for --apply")
    ap.add_argument("--page-bars", type=int, default=0, help="add new-page about every N bars")
    args = ap.parse_args(argv)
    path = Path(args.input)
    try:
        text = read_text(path)
        root = ET.fromstring(text)
    except Exception as exc:
        print(f"error: cannot read {args.input}: {exc}", file=sys.stderr)
        return 2
    if root.tag != "score-partwise":
        print("error: only score-partwise MusicXML is supported", file=sys.stderr)
        return 2
    bars, warnings = analyse(root)
    if not bars:
        print("error: no measures found", file=sys.stderr)
        return 2
    existing = sum(1 for pr in root.iter("print") if pr.get("new-system") == "yes" or pr.get("new-page") == "yes")
    if existing:
        warnings.append(f"input already has {existing} system/page break markers; they are left as they are")
    cands, facts = layouts(bars, args.apply or args.candidates, args.page_bars)
    if args.apply:
        if not args.out:
            print("error: --apply needs --out", file=sys.stderr)
            return 2
        c = cands[0]
        n = apply_breaks(root, c["starts"], set(c["pages"]))
        ET.indent(root, space="  ")
        header = header_of(text) or '<?xml version="1.0" encoding="UTF-8"?>\n'
        Path(args.out).write_text(header + ET.tostring(root, encoding="unicode") + "\n", encoding="utf-8")
        print(f"wrote {args.out}: {c['name']} layout, {len(c['starts']) - 1} system breaks"
              f" ({len(c['pages'])} page breaks) in {n} measures; sizes {'-'.join(map(str, c['sizes']))}")
        return 0
    title = (root.findtext("work/work-title") or path.stem).strip()
    if args.json:
        print(json.dumps({"title": title, "bars": len(bars), "density": facts, "warnings": warnings,
                          "phrase_ends": [{"bar": b.label, "score": b.score, "signals": b.signals}
                                          for b in bars[:-1] if b.score > 0],
                          "candidates": cands}, indent=2))
    else:
        print(format_text(title, bars, cands, facts, warnings))
    return 0


if __name__ == "__main__":
    sys.exit(main())
