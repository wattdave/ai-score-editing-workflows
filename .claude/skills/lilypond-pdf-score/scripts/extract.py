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


def head_kind(name):
    # exact names only: incipits are set in mensural heads (noteheads.sM1mensural...) and are not sung
    return HEAD.get(name)


def group_systems(pg, nvoices):
    n = len(pg.staves)
    if n % nvoices:
        raise SystemExit(f"page {pg.pn+1}: {n} staves is not a multiple of {nvoices} voices; "
                         "this reader needs one voice per staff (see SKILL.md)")
    return [list(range(i, i + nvoices)) for i in range(0, n, nvoices)]


def extract(D, nvoices=4, pages=None):
    out = []
    for pg in D.pages:
        if pages is not None and pg.pn not in pages:
            continue
        k = pg.k
        stems = sorted({(round(x, 1), round(y, 1), round(y + h, 1)) for (x, y, w, h) in pg.rects
                        if w < 0.35 * k and 5 * k < h < 20 * k})
        beams = [q for q in pg.polys if q[2] - q[0] > 3.0 * k and q[3] - q[1] < 8 * k]
        beams += [(x, y, x + w, y + h) for (x, y, w, h) in pg.rects if w > 3 * k and 1.2 * k < h < 3 * k]   # level beams are plain rects
        beams = sorted({tuple(round(v, 1) for v in b) for b in beams})   # a filled+stroked rect is listed twice
        bar_rects = [(x, y, h) for (x, y, w, h) in pg.rects if 0.6 < w < 1.2 and h > 15 * k]
        systems = []
        events = defaultdict(list)
        main = [g for g in pg.glyphs if g["name"] and abs(g["size"] - pg.main) < 0.2]
        by_staff = defaultdict(list)
        for g in main:
            by_staff[pg.staff_of(g["y"])].append(g)
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
            if nn:
                a0 = nn[0]
                ya = pg.staves[si]["bot"] - a0["hs"] * sp / 2
                if any(abs(cx1 - a0["x"]) < 6 * k and cx0 < a0["x"] - 4 * k and abs((cy0 + cy1) / 2 - ya) < 3.2 * sp
                       and cx0 >= pg.staves[si]["x0"] for (cx0, cy0, cx1, cy1) in pg.curves):
                    a0["tie_in"] = True
        for sts in group_systems(pg, nvoices):
            ytop = pg.staves[sts[0]]["top"] - 15
            ybot = pg.staves[sts[-1]]["bot"] + 5
            bl = sorted({round(x, 1) for (x, y, h) in bar_rects if ytop <= y <= ybot})
            systems.append(dict(staves=sts, bars=bl, x0=pg.staves[sts[0]]["x0"], x1=pg.staves[sts[0]]["x1"]))
        out.append(dict(pn=pg.pn, events={si: events[si] for si in events}, systems=systems, staves=pg.staves))
    return out


def dur(e):
    if e["t"] == "R":
        base = e["dur"]
    else:
        base = {"B": 8.0, "w": 4.0, "h": 2.0, "b": 1.0}[e["kind"]]
        if e["kind"] == "b":
            base = base / (2 ** max(e["flags"], e["beams"]))
    d = base
    add = base / 2
    for _ in range(e["dots"]):
        d += add
        add /= 2
    return d


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
