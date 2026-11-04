"""Global voices: onsets in beats, pitch steps, accidentals, lyrics. Also clef, key and time detection."""
import os, sys, statistics
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from collections import Counter
from onset2 import *
from lyr import page_lyrics

DIGITS = {n: i for i, n in enumerate("zero one two three four five six seven eight nine".split())}

# written pitch of the bottom staff line, as diatonic steps from C0 (E4 = 30), by clef glyph and its y
REF = {"clefs.G": 32, "clefs.F": 24, "clefs.C": 28}
CLEFS = set(REF)       # the plain modern clefs; clefs.petrucci.* belong to incipits   # pitch the clef's reference line stands for


def staff_clef(D, res, i):
    """the clef glyph just left of the first sung note of voice i in the first system
    (an incipit before it has its own clef, which is not the one in force)"""
    pg = res[0]
    pgo = D.pages[pg["pn"]]
    st = pg["systems"][0]["staves"][i]
    notes = [e["x"] for e in pg["events"].get(st, []) if e["t"] == "N"]
    x1 = min(notes) if notes else 1e9
    cl = [g for g in pgo.glyphs if g["name"] in CLEFS and pgo.staff_of(g["y"]) == st
          and g["x"] < x1 and g["size"] >= pgo.main * 0.85]
    return (max(cl, key=lambda g: g["x"]) if cl else None), st, pgo


def detect_clefs(D, res):
    """clef spec per voice of the first system, e.g. ['G','G8','F']"""
    specs = []
    for i in range(len(res[0]["systems"][0]["staves"])):
        g, st, pgo = staff_clef(D, res, i)
        if g is None:
            specs.append("G")
            continue
        s = pgo.staves[st]
        eight = [h for h in pgo.eights if abs(h[0] - g["x"]) < 12 * pgo.k and pgo.staff_of(h[1]) == st
                 and h[1] > s["bot"] - 6]
        specs.append(g["name"][-1] + ("8" if eight else ""))
    return specs


def clef_hs0(D, res, spec, i):
    """diatonic step of the bottom staff line for a clef spec, as SOUNDING pitch (8 = an octave lower)"""
    g, st, pgo = staff_clef(D, res, i)
    letter = spec[0]
    if g is not None and g["name"] == "clefs." + letter:
        hs = pgo.hs(st, g["y"])
    else:
        hs = {"G": 2, "F": 6, "C": 4}[letter]
    n = REF["clefs." + letter] - hs
    if spec.endswith("8"):
        n -= 7
    return n


def detect_key(D, res):
    """key signature = the run of flats or sharps just left of the first note of the first system
    (an incipit before it carries its own signature, which is not counted)"""
    pgo = D.pages[res[0]["pn"]]
    st = res[0]["systems"][0]["staves"][0]
    notes = [e["x"] for e in res[0]["events"][st] if e["t"] == "N"]
    x1 = min(notes) if notes else 1e9
    accs = sorted((g["x"] for g in pgo.glyphs if g["name"] in FLAT | SHARP and pgo.staff_of(g["y"]) == st
                   and g["x"] < x1 - 2 * pgo.k and g["size"] >= pgo.main * 0.85), reverse=True)
    sign = [g["name"] in FLAT for g in pgo.glyphs if g["name"] in FLAT | SHARP and pgo.staff_of(g["y"]) == st
            and g["x"] < x1 - 2 * pgo.k and g["size"] >= pgo.main * 0.85]
    run = []
    for x in accs:
        if run and run[-1] - x > 9 * pgo.k:
            break
        run.append(x)
    if not run:
        return 0
    flats = any(g["name"] in FLAT and abs(g["x"] - run[0]) < 0.5 and pgo.staff_of(g["y"]) == st for g in pgo.glyphs)
    return -len(run) if flats else len(run)


def detect_time(D, res):
    """(beats, beat-type, symbol or None) from the first system's top staff"""
    pgo = D.pages[res[0]["pn"]]
    st = res[0]["systems"][0]["staves"][0]
    s = pgo.staves[st]
    for g in pgo.glyphs:
        if g["name"] and g["name"].startswith("timesig.") and pgo.staff_of(g["y"]) == st:
            if g["name"] in ("timesig.C22", "timesig.C44"):
                return {"timesig.C22": (2, 2, "cut"), "timesig.C44": (4, 4, "common")}[g["name"]]
            # mensural time signatures (timesig.mensural22) belong to incipits: look for the digits
    dg = [g for g in pgo.glyphs if g["name"] in DIGITS and pgo.staff_of(g["y"]) == st and g["x"] < s["x0"] + 80]
    if len(dg) >= 2:
        dg.sort(key=lambda g: g["y"])
        return DIGITS[dg[0]["name"]], DIGITS[dg[-1]["name"]], None
    return 4, 4, None


def bar_modes(res):
    """most common bar length in each system, read from the sums between barlines"""
    out = []
    for pg in res:
        for s in pg["systems"]:
            sums = []
            for st in s["staves"]:
                bars = defaultdict(float)
                for e in pg["events"].get(st, []):
                    bars[sum(1 for b in s["bars"] if b < e["x"] + 3)] += dur(e)
                sums += [round(v, 2) for v in bars.values()]
            if sums and len(s["bars"]) >= 3:
                out.append(Counter(sums).most_common(1)[0][0])
    return out


def time_changes(D, res, systems, starts):
    """[(global beat, beats, beat-type, symbol)] every time signature printed on the top staff, in order;
    one whose notes follow it in the same system is dated by the next note, a courtesy one at the end of a
    system by the end of that system"""
    out = []
    for (pg, s), S in zip(systems, starts):
        pgo = D.pages[pg["pn"]]
        st = s["staves"][0]
        gl = [g for g in pgo.glyphs if pgo.staff_of(g["y"]) == st and g["name"]
              and (g["name"] in ("timesig.C22", "timesig.C44") or g["name"] in DIGITS) and g["size"] >= pgo.main * 0.85 * 0.5]
        L, tot = timeline(pg, s)[st]
        clusters = []
        for g in sorted(gl, key=lambda g: g["x"]):
            if clusters and g["x"] - clusters[-1][0]["x"] < 4 * pgo.k:
                clusters[-1].append(g)
            else:
                clusters.append([g])
        for c in clusters:
            x = c[0]["x"]
            if c[0]["name"].startswith("timesig."):
                sig = {"timesig.C22": (2, 2, "cut"), "timesig.C44": (4, 4, "common")}.get(c[0]["name"])
            else:
                dg = sorted(c, key=lambda g: g["y"])
                sig = (DIGITS[dg[0]["name"]], DIGITS[dg[-1]["name"]], None) if len(dg) >= 2 else None
            if not sig:
                continue
            nxt = [tt for e, tt in L if e["x"] > x]
            out.append((S + (nxt[0] if nxt else tot), *sig))
    ded = []
    for t, b, d, sym in sorted(out):
        if not ded or (b, d) != (ded[-1][1], ded[-1][2]):
            ded.append((t, b, d, sym))
    return ded


def system_starts(res, beats_per_bar):
    # a time-signature change (4/2 then 2/2) makes the bar length vary: snap on the shortest usual bar
    beats_per_bar = min([beats_per_bar] + bar_modes(res))
    systems = [(pg, s) for pg in res for s in pg["systems"]]
    starts = []
    grid = 0.0
    for n, (pg, s) in enumerate(systems):
        ons = timeline(pg, s)
        cands = []
        for b in s["bars"][1:-1] if n > 0 else s["bars"][1:-1]:
            for st, (L, t) in ons.items():
                prev = [(e, tt) for e, tt in L if e["x"] < b]
                nxt = [(e, tt) for e, tt in L if e["x"] > b]
                if prev and nxt:
                    pe, pt = prev[-1]
                    ne, nt = nxt[0]
                    if abs(pt + dur(pe) - nt) < 1e-6:
                        cands.append(round(nt % beats_per_bar, 2))
        mode = Counter(cands).most_common(1)[0][0] if cands else 0.0
        if n == 0:
            S0 = 0.0
            grid = mode            # barlines fall at this beat residue (nonzero when the piece has a pickup)
        else:
            ppg, ps = systems[n - 1]
            pons = timeline(ppg, ps)
            tot = statistics.median([t for _, t in pons.values()])
            base = starts[-1] + tot
            if not cands:      # no barlines to read a residue from (unbarred edition): trust the sums
                starts.append(base)
                continue
            want = (grid - mode) % beats_per_bar
            k = round((base - want) / beats_per_bar)
            S0 = want + beats_per_bar * k
        starts.append(S0)
    return systems, starts


def collect(D, res, nvoices, clefs, beats_per_bar, fifths, pickup_shift=None):
    systems, starts = system_starts(res, beats_per_bar)
    detected = detect_clefs(D, res)
    # an explicit --clefs with an 8 where the print shows none (Brumel's Cantus) shifts that whole voice
    extra8 = [1 if c.endswith("8") and not d.endswith("8") else 0 for c, d in zip(clefs, detected)]
    voices = [[] for _ in range(nvoices)]
    ptoks = {pn: page_lyrics(D.doc, pn) for pn in {pg["pn"] for pg, _ in systems}}
    for n, ((pg, s), S) in enumerate(zip(systems, starts)):
        pgo = D.pages[pg["pn"]]
        ons = timeline(pg, s)
        small = [g for g in pgo.glyphs if g["name"] in (FLAT | SHARP | NAT) and g["size"] < pgo.main * 0.85]
        if D.off == 1:
            # a PDF re-saved by Preview loses the name of the last glyph of each font subset;
            # in the Brumel PDF that glyph is the small ficta flat
            for g in pgo.glyphs:
                if g["name"] is None and g["size"] < pgo.main * 0.85 and "Emmentaler" in g["font"]:
                    g["name"] = "accidentals.flat"
                    small.append(g)
        for vi, st in zip(s["voices"], s["staves"]):
            L, _ = ons[st]
            # the first |fifths| accidentals after the clef are the key signature, not accidentals on a note
            first_x = min((e["x"] for e, _ in L if e["t"] == "N"), default=1e9)
            clefs_x = [g["x"] for g in pgo.glyphs if g["name"] and g["name"].startswith("clefs.")
                       and pgo.staff_of(g["y"]) == st and g["x"] < first_x]
            cx = max(clefs_x) if clefs_x else -1e9
            keyx = sorted(g["x"] for g in pgo.glyphs if g["name"] in FLAT | SHARP and pgo.staff_of(g["y"]) == st
                          and cx < g["x"] < first_x and g["size"] >= pgo.main * 0.85)[:abs(fifths)]
            clef_marks = sorted((g["x"], g, any(abs(h[0] - g["x"]) < 12 * pgo.k and pgo.staff_of(h[1]) == st
                                                  and h[1] > pgo.staves[st]["bot"] - 6 for h in pgo.eights))
                                for g in pgo.glyphs if g["name"] in CLEFS and pgo.staff_of(g["y"]) == st
                                and g["size"] >= pgo.main * 0.6)
            clef_marks = [(x, g, e8) for x, g, e8 in clef_marks]

            def hs0_at(x):
                """bottom-line step for the clef in force at x (a clef can change mid-piece)"""
                cur = [m for m in clef_marks if m[0] < x]
                if not cur:
                    return clef_hs0(D, res, clefs[vi], vi)
                _, g, e8 = cur[-1]
                n = REF[g["name"]] - pgo.hs(st, g["y"]) - (7 if e8 else 0)
                return n - 7 * extra8[vi]
            for e, t in L:
                if e.get("acc_x") is not None and any(abs(e["acc_x"] - kx) < 0.3 for kx in keyx):
                    e.pop("acc", None)
                ev = dict(onset=S + t, dur=dur(e), x=e["x"], page=pg["pn"], sys=n, voice=vi)
                if e.get("tup"):
                    ev["tup"] = True
                if e["t"] == "R":
                    ev["rest"] = True
                else:
                    ev["step"] = hs0_at(e["x"]) + e["hs"]
                    alt = None
                    for g in small:
                        if pgo.staff_of(g["y"]) == st and 0 <= g["x"] - e["x"] <= 3.2 * pgo.k:
                            alt = -1 if g["name"] in FLAT else 1 if g["name"] in SHARP else 0
                            ev["ficta"] = True
                    if alt is None and "acc" in e:
                        alt = e["acc"]
                        ev["acc"] = True
                    ev["alt"] = alt
                if (e.get("tie") or e.get("tie_in")) and not e["t"] == "R":
                    prev = [p for p in voices[vi] if not p.get("rest")]
                    if prev and (prev[-1]["sys"] == n or e.get("tie_in")) and prev[-1].get("step") == ev["step"] \
                            and abs(prev[-1]["onset"] + prev[-1]["dur"] - ev["onset"]) < 1e-6:
                        prev[-1]["dur"] += ev["dur"]      # tied note: one longer note
                        continue
                voices[vi].append(ev)
            sb = pgo.staves[st]["bot"]
            nxt = pgo.staves[st + 1]["top"] if st + 1 < len(pgo.staves) else sb + 60
            row = [t for t in ptoks[pg["pn"]] if sb < t["y"] - 5 < nxt and t["x0"] >= pgo.staves[st]["x0"]]
            row.sort(key=lambda t: t["x0"])
            notes = [ev for ev in voices[vi] if ev["sys"] == n and not ev.get("rest")]
            sy = [t for t in row if t["text"] != "-"]
            last = -1
            for ti, t in enumerate(sy):
                xc = (t["x0"] + t["x1"]) / 2
                best = None
                for k, ev in enumerate(notes):
                    if k <= last:
                        continue
                    dxx = abs(xc - (ev["x"] + 2.6 * pgo.k))
                    if best is None or dxx < best[0]:
                        best = (dxx, k)
                if best is None or best[0] > 14:
                    continue
                last = best[1]
                prev_x1 = sy[ti - 1]["x1"] if ti > 0 else -1e9
                next_x0 = sy[ti + 1]["x0"] if ti + 1 < len(sy) else 1e9
                after = [h for h in row if h["text"] == "-" and t["x1"] - 1 <= h["x0"] <= next_x0]
                before = [h for h in row if h["text"] == "-" and prev_x1 - 1 <= h["x0"] <= t["x0"] + 1]
                syl = "middle" if (after and before) else "begin" if after else "end" if before else "single"
                notes[best[1]]["lyric"] = (t["text"], syl)
    return voices, starts, systems
