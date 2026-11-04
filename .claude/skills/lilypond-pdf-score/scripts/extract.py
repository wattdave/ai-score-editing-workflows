"""Per page: notes, rests, dots, flags, beams, accidentals per staff, and the systems (groups of staves)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from collections import defaultdict
from reader import *

HEAD = {"noteheads.sM1": "B", "noteheads.s0": "w", "noteheads.s1": "h", "noteheads.s2": "b"}
REST = {"rests.M1": 8.0, "rests.0": 4.0, "rests.1": 2.0, "rests.2": 1.0, "rests.3": 0.5, "rests.4": 0.25}
FLAT = {"accidentals.flat", "accidentals.M1", "accidentals.M2"}
SHARP = {"accidentals.sharp", "accidentals.1"}
NAT = {"accidentals.natural", "accidentals.0"}


# Some editions draw their breves with the neomensural shape; incipits use it too (see extract)
NEO = {"noteheads.sM1neomensural": "B", "noteheads.srM1neomensural": "B",
       "noteheads.uM2neomensural": "L", "noteheads.dM2neomensural": "L",
       "noteheads.urM2neomensural": "L", "noteheads.drM2neomensural": "L",
       "noteheads.uM2": "L", "noteheads.dM2": "L"}   # B = breve (8 beats), L = longa (16)


FINAL_BREVE = False   # --final-breve: a longa that ends its staff in a system sounds as a breve (Hawthorne editions: f\\longa*1/2)


def head_kind(name):
    # incipits are set in mensural heads (noteheads.sM1mensural...) and are not sung
    return HEAD.get(name) or NEO.get(name)


def group_systems(pg, nvoices, names=None):
    """[(staff indexes, voice index of each)] per system.
    Usually every system has all the voices in order. LilyPond can hide a resting staff (RemoveEmptyStaves), so a
    system may have fewer staves: then systems are found from the vertical gaps and each staff is matched to a
    voice by the name or abbreviation printed in the left margin (the first three letters)."""
    n = len(pg.staves)
    if n == 0:
        return []
    gaps = [pg.staves[i + 1]["top"] - pg.staves[i]["bot"] for i in range(n - 1)]
    positional = [(list(range(i, i + nvoices)), list(range(nvoices))) for i in range(0, n, nvoices)] if n % nvoices == 0 else None
    med = sorted(gaps)[len(gaps) // 2] if gaps else 0
    systems, cur = [], [0]
    for i, g in enumerate(gaps):
        if g > 1.3 * med:
            systems.append(cur)
            cur = []
        cur.append(i + 1)
    systems.append(cur)
    if all(len(sts) == nvoices for sts in systems):
        return [(sts, list(range(nvoices))) for sts in systems]
    if positional and names and all(pg.label(st)[:3] == names[v][:3] for sts, vids in positional for st, v in zip(sts, vids)):
        return positional      # the margin names run through the voices in order in every system
    if positional and not all(pg.label(st) for sts in systems for st in sts):
        return positional      # no names printed to tell the staves apart: assume full systems, in order
    out = []
    for sts in systems:
        if len(sts) == nvoices:
            out.append((sts, list(range(nvoices))))
            continue
        vids = []
        for st in sts:
            lab = pg.label(st)
            hit = [v for v, nm in enumerate(names or []) if lab[:3] and nm[:3] == lab[:3]]
            if len(hit) != 1:
                if positional:
                    return positional      # labels cannot decide: assume full systems, in order
                raise SystemExit(f"page {pg.pn+1}: a system has {len(sts)} staves, not {nvoices}, and staff {st} "
                                 f"(label {lab!r}) cannot be matched to a voice (see SKILL.md)")
            vids.append(hit[0])
        out.append((sts, vids))
    return out


def first_system_names(D, nvoices):
    pg = D.pages[0]
    if len(pg.staves) < nvoices:
        return None
    names = [pg.label(i) for i in range(nvoices)]
    return names if all(names) else None


def extract(D, nvoices=4, pages=None):
    out = []
    names = first_system_names(D, nvoices)
    for pg in D.pages:
        if pages is not None and pg.pn not in pages:
            continue
        k = pg.k
        stems = sorted({(round(x, 1), round(y, 1), round(y + h, 1)) for (x, y, w, h) in pg.rects
                        if w < 0.35 * k and 5 * k < h < 20 * k})
        beams = [q for q in pg.polys if q[2] - q[0] > 3.0 * k and q[3] - q[1] < 8 * k]
        beams += [(x, y, x + w, y + h) for (x, y, w, h) in pg.rects if w > 3 * k and 1.2 * k < h < 3 * k]   # level beams are plain rects
        beams = sorted({tuple(round(v, 1) for v in b) for b in beams})   # a filled+stroked rect is listed twice
        sp0 = pg.staves[0]["sp"] if pg.staves else 4.5
        # a barline is a tall thin rect: 0.6-1.2 wide in older files, thinner in newer ones, then
        # recognised by running through at least two staves (taller than 8 staff spaces)
        bar_rects = [(x, y, h) for (x, y, w, h) in pg.rects if (0.6 < w < 1.2 and h > 15 * k) or (w < 1.2 and h > 8 * sp0)]
        systems = []
        events = defaultdict(list)
        main = [g for g in pg.glyphs if g["name"] and abs(g["size"] - pg.main) < 0.2]
        by_staff = defaultdict(list)
        for g in main:
            by_staff[pg.staff_of_head(g["x"], g["y"]) if (g["name"] or "").startswith("noteheads.") else pg.staff_of(g["y"])].append(g)
        for si, gs in by_staff.items():
            s = pg.staves[si]
            gs.sort(key=lambda g: g["x"])
            for g in gs:
                nm = g["name"]
                h = pg.hs(si, g["y"])
                kind = head_kind(nm) if nm.startswith("noteheads.") else None
                if kind:
                    events[si].append(dict(t="N", kind=kind, x=g["x"], hs=h, dots=0, flags=0, beams=0, name=nm))
                elif nm in REST:
                    events[si].append(dict(t="R", dur=REST[nm], x=g["x"], hs=h, dots=0, name=nm))
            if si < nvoices and pg.pn == D.pages[0].pn:
                # first system only: an incipit (original clef, mensural time sign, a note or two) sits left of the
                # first modern clef; none of it is sung
                clefx = [g["x"] for g in gs if g["name"] in ("clefs.G", "clefs.F", "clefs.C") and g["size"] >= pg.main * 0.85]
                if clefx:
                    cut = min(clefx)
                    events[si] = [e for e in events[si] if not (e["t"] == "N" and e["x"] < cut - 1)]
            notes = [e for e in events[si] if e["t"] == "N"]
            rests = [e for e in events[si] if e["t"] == "R"]
            for g in gs:
                nm = g["name"]
                if nm == "dots.dot":
                    cand = [e for e in notes + rests if 3 * k <= g["x"] - e["x"] <= 14 * k]
                    if cand:
                        min(cand, key=lambda e: g["x"] - e["x"])["dots"] += 1
                elif nm.startswith(("flags.u", "flags.d")):
                    nfl = max(1, int(nm[-1]) - 2)
                    exp = (5.3 if nm.startswith("flags.u") else 0.6) * k
                    cand = [e for e in notes if e["kind"] == "b" and abs(g["x"] - e["x"] - exp) <= 1.5 * k]
                    cand = [e for e in cand if 8 * k < abs(g["y"] - (s["bot"] - e["hs"] * s["sp"] / 2)) < 18 * k]
                    if cand:
                        e = min(cand, key=lambda e: abs(g["x"] - e["x"] - exp))
                        e["flags"] = max(e["flags"], nfl)
                elif nm in FLAT | SHARP | NAT and g["x"] > 0:
                    alt = -1 if nm in FLAT else 1 if nm in SHARP else 0
                    cand = [e for e in notes if 2 * k <= e["x"] - g["x"] <= 14 * k and pg.hs(si, g["y"]) == e["hs"]]
                    if cand:
                        e = min(cand, key=lambda e: e["x"] - g["x"])
                        e["acc"] = alt
                        e["acc_x"] = g["x"]
            for e in notes:
                if e["kind"] != "b":
                    continue
                y = s["bot"] - e["hs"] * s["sp"] / 2
                st = None
                for (x0, ya, yb) in stems:
                    if -0.7 * k <= x0 - e["x"] <= 5.8 * k and (abs(ya - y) < 1.2 or abs(yb - y) < 1.2):
                        st = (x0, ya, yb)
                        break
                if not st:
                    continue
                tip = st[2] if abs(st[1] - y) < 1.2 else st[1]
                e["beams"] = sum(1 for (bx0, by0, bx1, by1) in beams
                                 if bx0 - 0.8 <= st[0] <= bx1 + 0.8 and by0 - 3 <= tip <= by1 + 3)
        for si in events:
            events[si].sort(key=lambda e: e["x"])
            if FINAL_BREVE:
                nn_ = [e for e in events[si] if e["t"] == "N"]
                if nn_ and nn_[-1]["kind"] == "L":
                    nn_[-1]["kind"] = "B"
            # a curve from one head to the next head of the same pitch is a tie (a slur between equal notes is too)
            sp = pg.staves[si]["sp"]
            nn = [e for e in events[si] if e["t"] == "N"]
            for a, b in zip(nn, nn[1:]):
                if a["hs"] != b["hs"]:
                    continue
                ya = pg.staves[si]["bot"] - a["hs"] * sp / 2
                if any(cx0 >= a["x"] + 2 * k and cx1 <= b["x"] + 4 * k and cx1 - cx0 > 3 * k and abs((cy0 + cy1) / 2 - ya) < 3.2 * sp
                       for (cx0, cy0, cx1, cy1) in pg.curves):
                    b["tie"] = True
            # a tie that runs over a system break shows as a stub ending at the first note of the next system
            # a small "3" over or under a bracket: the three events nearest its centre are a triplet (2/3 length)
            ev = events[si]
            s_ = pg.staves[si]
            for w in pg.words:
                if w[4] != "3":
                    continue
                wy, wx = (w[1] + w[3]) / 2, (w[0] + w[2]) / 2
                dist = max(s_["top"] - wy, wy - s_["bot"], 0)
                if not any(abs(hx - wx) < 30 and abs(hy - wy) < 8 for hx, hy in pg.hooks):
                    continue      # no bracket hooks near it: a bar number, not a tuplet
                if dist < sp or dist > 3 * sp or not (s_["x0"] <= wx <= s_["x1"]) or len(ev) < 3:
                    continue
                i = min(range(len(ev)), key=lambda j: abs(ev[j]["x"] + 2 * k - wx))
                i = min(max(i, 1), len(ev) - 2)
                # the digit belongs to the nearest staff only
                if any(max(o["top"] - wy, wy - o["bot"], 0) < dist for o in pg.staves if o is not s_ and o["x0"] <= wx <= o["x1"]):
                    continue
                for x_ in ev[i - 1:i + 2]:
                    x_["tup"] = True
            if nn:
                a0 = nn[0]
                ya = pg.staves[si]["bot"] - a0["hs"] * sp / 2
                if any(abs(cx1 - a0["x"]) < 6 * k and cx0 < a0["x"] - 4 * k and abs((cy0 + cy1) / 2 - ya) < 3.2 * sp
                       and cx0 >= pg.staves[si]["x0"] for (cx0, cy0, cx1, cy1) in pg.curves):
                    a0["tie_in"] = True
        for sts, vids in group_systems(pg, nvoices, names):
            ytop = pg.staves[sts[0]]["top"] - 15
            ybot = pg.staves[sts[-1]]["bot"] + 5
            bl = sorted({round(x, 1) for (x, y, h) in bar_rects if ytop <= y <= ybot})
            # a whole rest centred between two barlines is a rest for the whole bar, which can be longer than a whole
            # note (a bar of a breve and a half); take the bar length from the other staves' bars
            if len(bl) >= 2:
                full = []
                for si in sts:
                    for e in events[si]:
                        if e["t"] == "R" and e["name"] == "rests.0":
                            lo = [b for b in bl if b < e["x"]]
                            hi = [b for b in bl if b > e["x"] + 2 * k]
                            if lo and hi and abs(e["x"] + 2 * k - (lo[-1] + hi[0]) / 2) < 5 * k:
                                full.append(e)
                if full:
                    sums = {}
                    for si in sts:
                        for e in events[si]:
                            if e not in full and e["x"] > bl[0]:
                                b = sum(1 for x in bl if x < e["x"] + 3)
                                sums[(si, b)] = sums.get((si, b), 0) + dur(e)
                    from collections import Counter
                    c = Counter(round(v, 2) for v in sums.values() if v >= 4)
                    if c:
                        for e in full:
                            e["dur"] = c.most_common(1)[0][0]
                            e["full"] = True        # centred in its bar: its x is not where the bar starts
            systems.append(dict(staves=sts, voices=vids, bars=bl, x0=pg.staves[sts[0]]["x0"], x1=pg.staves[sts[0]]["x1"]))
        out.append(dict(pn=pg.pn, events={si: events[si] for si in events}, systems=systems, staves=pg.staves))
    return out


def dur(e):
    if e["t"] == "R":
        base = e["dur"]
    else:
        base = {"L": 16.0, "B": 8.0, "w": 4.0, "h": 2.0, "b": 1.0}[e["kind"]]
        if e["kind"] == "b":
            base = base / (2 ** max(e["flags"], e["beams"]))
    d = base
    add = base / 2
    for _ in range(e["dots"]):
        d += add
        add /= 2
    return d * 2 / 3 if e.get("tup") else d


if __name__ == "__main__":
    D = Doc(sys.argv[1])
    print("glyph offset", D.off, "main size", [p.main for p in D.pages])
    pages = [int(x) - 1 for x in sys.argv[3].split(",")] if len(sys.argv) > 3 else None
    res = extract(D, int(sys.argv[2]) if len(sys.argv) > 2 else 4, pages)
    for pg in res:
        for s in pg["systems"]:
            print("page", pg["pn"] + 1, "system staves", s["staves"], "barlines", len(s["bars"]))
            for si in s["staves"]:
                ev = pg["events"].get(si, [])
                bars = defaultdict(float)
                for e in ev:
                    bars[sum(1 for b in s["bars"] if b < e["x"] + 3)] += dur(e)
                print("  staff", si, "bar sums", [round(bars[k], 2) for k in sorted(bars)])
