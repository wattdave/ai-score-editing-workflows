"""Page reader: staff lines, notation glyphs (by glyph NAME), rects and filled polygons."""
import io, os, sys
import pymupdf
from fontTools.cffLib import CFFFontSet

NAMES = "CDEFGAB"


def font_orders(doc):
    """font name (no subset tag) -> glyph-name list, read from the embedded CFF fonts."""
    out = {}
    for pn in range(len(doc)):
        for f in doc[pn].get_fonts():
            base = f[3].split("+")[-1]
            if ("Emmentaler" in base or "feta" in base) and f[0] not in out:
                try:
                    _, ext, _, buf = doc.extract_font(f[0])
                    cs = CFFFontSet()
                    cs.decompile(io.BytesIO(buf), None)
                    names = list(cs[cs.fontNames[0]].CharStrings.keys())
                except Exception:
                    continue
                out[f[0]] = (base, names)
    best = {}
    for base, names in out.values():     # several subsets can share a name: keep the longest list
        if base not in best or len(names) > len(best[base]):
            best[base] = names
    return best


def calibrate_offset(doc, orders):
    """glyph id -> list index is gid + off. 0 for files written by LilyPond itself;
    1 for files re-saved by another program (Preview) that dropped .notdef from the numbering.
    Decided by which offset turns the most glyphs into noteheads."""
    from collections import Counter
    score = {0: 0, 1: 0}
    for pn in range(min(len(doc), 2)):
        cnt = Counter()
        for tr in doc[pn].get_texttrace():
            fn = tr["font"].split("+")[-1]
            if "Emmentaler" in fn and fn in orders:
                for ch in tr["chars"]:
                    cnt[(fn, ch[1])] += 1
        for (fn, gid), n in cnt.items():
            for off in (0, 1):
                i = gid + off
                nm = orders[fn][i] if i < len(orders[fn]) else ""
                if nm.startswith("noteheads."):
                    score[off] += n
    return 0 if score[0] >= score[1] else 1


class Doc:
    def __init__(self, pdf):
        self.doc = pymupdf.open(pdf)
        self.orders = font_orders(self.doc)
        self.off = calibrate_offset(self.doc, self.orders)
        self.pages = [Page(self, pn) for pn in range(len(self.doc))]

    def name(self, font, gid):
        o = self.orders.get(font.split("+")[-1])
        i = gid + self.off
        return o[i] if o and 0 <= i < len(o) else None


class Page:
    def __init__(self, D, pn):
        self.pn = pn
        p = D.doc[pn]
        self.p = p
        lines = []
        for d in p.get_drawings():
            for it in d["items"]:
                if it[0] == "l":
                    a, b = it[1], it[2]
                    if abs(a.y - b.y) < 0.01 and abs(a.x - b.x) > 100:
                        lines.append((round(a.y, 2), min(a.x, b.x), max(a.x, b.x)))
        ys = sorted({l[0] for l in lines})
        self.staves = []
        # five equally spaced long lines make a staff; other long horizontal lines (cresc. and dim. spanners,
        # lyric extenders) are skipped over
        i = 0
        while i + 4 < len(ys):
            g = ys[i:i + 5]
            d = [g[j + 1] - g[j] for j in range(4)]
            if max(d) - min(d) < 0.06 and 2.0 < d[0] < 7.0:
                xs = [l for l in lines if l[0] in g]
                self.staves.append(dict(top=g[0], bot=g[4], sp=(g[4] - g[0]) / 4,
                                        x0=min(l[1] for l in xs), x1=max(l[2] for l in xs)))
                i += 5
            else:
                i += 1
        self.glyphs = []
        for sp in p.get_texttrace():
            fn = sp["font"].split("+")[-1]
            if "Emmentaler" in fn or "feta" in fn:
                for ch in sp["chars"]:
                    self.glyphs.append(dict(name=D.name(fn, ch[1]), gid=ch[1], x=ch[2][0], y=ch[2][1],
                                            size=round(sp["size"], 1), bb=ch[3], font=fn))
        self.eights = [(c[2][0], c[2][1]) for sp in p.get_texttrace() if sp["size"] < 8 and "Ital" in sp["font"]
                       for c in sp["chars"] if c[0] == 56]      # the small 8 of a treble-8 clef is text
        sizes = [g["size"] for g in self.glyphs if (g["name"] or "").startswith("noteheads.")]
        self.main = max(set(sizes), key=sizes.count) if sizes else 17.9
        self.k = self.main / 15.9      # scale of every metric hard-wired from the first test piece
        self.words = [(w[0], w[1], w[2], w[3], w[4]) for w in p.get_text("words")]
        # short stroked vertical ticks (2.4 to 3.3 pt): the hooks of a tuplet bracket
        self.hooks = [((d["rect"].x0 + d["rect"].x1) / 2, (d["rect"].y0 + d["rect"].y1) / 2) for d in p.get_drawings()
                      if d["type"] == "s" and d["rect"].width < 0.5 and 2.4 < d["rect"].height < 3.3]
        self.hlines = [(d["rect"].x0, d["rect"].x1, (d["rect"].y0 + d["rect"].y1) / 2) for d in p.get_drawings()
                       if d["type"] == "s" and d["rect"].width > 10 and d["rect"].height < 0.3 and [it[0] for it in d["items"]] == ["l"]]
        self.rects = []
        self.ledgers = []
        self.polys = []
        self.curves = []
        for d in p.get_drawings():
            rr = d["rect"]
            if d["type"] == "s" and 4 < rr.width < 14 and rr.height < 0.3 and [it[0] for it in d["items"]] == ["l"]:
                self.ledgers.append(((rr.x0 + rr.x1) / 2, (rr.y0 + rr.y1) / 2))      # a stroked ledger line
            for it in d["items"]:
                if it[0] == "re":
                    r = it[1]
                    self.rects.append((r.x0, r.y0, r.width, r.height))
                    if 4 < r.width < 14 and r.height < 1.6:
                        self.ledgers.append(((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2))
            if d.get("fill") is not None and d["items"] and all(it[0] == "c" for it in d["items"]):
                r = d["rect"]
                self.curves.append((r.x0, r.y0, r.x1, r.y1))     # a filled tie or slur
            if d.get("fill") is not None and d["items"] and all(it[0] == "l" for it in d["items"]):
                r = d["rect"]
                self.polys.append((r.x0, r.y0, r.x1, r.y1))

    def staff_of(self, y):
        best = None
        bd = 1e9
        for i, s in enumerate(self.staves):
            c = (s["top"] + s["bot"]) / 2
            dd = abs(y - c)
            if dd < bd:
                bd = dd
                best = i
        return best

    def staff_of_head(self, x, y):
        """the staff a notehead at (x, y) belongs to. Far from the staff lines the nearest staff can be the
        wrong one (a low note under one staff is as near to the next staff's top): the ledger lines drawn
        between the head and its staff decide."""
        order = sorted(range(len(self.staves)), key=lambda i: abs(y - (self.staves[i]["top"] + self.staves[i]["bot"]) / 2))
        a = order[0]
        if len(order) < 2:
            return a
        b = order[1]
        da = abs(y - (self.staves[a]["top"] + self.staves[a]["bot"]) / 2)
        db = abs(y - (self.staves[b]["top"] + self.staves[b]["bot"]) / 2)
        if abs(da - db) > 3 * self.staves[a]["sp"]:
            return a
        near = [ly for lx, ly in self.ledgers if abs(lx - (x + 2.8)) < 5]

        def votes(i):
            s = self.staves[i]
            sp = s["sp"]
            n = 0
            for ly in near:
                if y < s["top"] and s["top"] - 7 * sp < ly < s["top"] and abs((s["top"] - ly) / sp - round((s["top"] - ly) / sp)) < 0.15 and ly >= y - 1:
                    n += 1
                elif y > s["bot"] and s["bot"] < ly < s["bot"] + 7 * sp and abs((ly - s["bot"]) / sp - round((ly - s["bot"]) / sp)) < 0.15 and ly <= y + 1:
                    n += 1
            return n
        va, vb = votes(a), votes(b)
        return b if vb > va else a

    def label(self, si):
        """the instrument name printed to the left of staff si (full name, abbreviation or empty)"""
        s = self.staves[si]
        ws = [w for w in self.words if w[2] < s["x0"] - 1 and s["top"] - 4 < (w[1] + w[3]) / 2 < s["bot"] + 4]
        return " ".join(w[4] for w in sorted(ws, key=lambda w: w[0])).strip().lower()

    def hs(self, si, y):
        s = self.staves[si]
        return round((s["bot"] - y) / (s["sp"] / 2))
