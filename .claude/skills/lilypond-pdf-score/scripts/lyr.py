"""Lyric tokens from the text font, plus hyphens from drawn rects.

A file written straight by LilyPond keeps a usable text layer, so the character codes are read as they are.
A file re-saved by another program (the Brumel PDF went through macOS Preview) can have a scrambled text
layer: then letters come from glyph shapes via a gid -> letter table. SH below is that table for the Brumel
PDF only; glyph ids differ per PDF, so rebuild it for another file (see SKILL.md)."""
import os, sys
import pymupdf

SH = "A y n c M B o d C p e D q f P E r g Q F s h t i u j T v J l a m b ] 8 - 9 . é 0 1 2 ’ 3 ( 4 ) 5 [ 6 _ 7 ,".split(" ")
GM = {i + 2: (" " if ch == "_" else "'" if ch == "’" else ch) for i, ch in enumerate(SH)}
SCRAMBLED = False


def lyric_size(doc):
    from collections import Counter
    c = Counter()
    for pn in range(len(doc)):
        for tr in doc[pn].get_texttrace():
            if "Roma" in tr["font"] and 7 < tr["size"] < 13:
                c[round(tr["size"], 1)] += len(tr["chars"])
    return c.most_common(1)[0][0] if c else 9.7


def page_lyrics(doc, pn, scrambled=None):
    scrambled = SCRAMBLED if scrambled is None else scrambled
    size = lyric_size(doc)
    chars = []
    for sid, tr in enumerate(doc[pn].get_texttrace()):
        if "Roma" not in tr["font"] or abs(tr["size"] - size) > 0.4:
            continue
        for ch in tr["chars"]:
            x0, y0, x1, y1 = ch[3]
            u = GM.get(ch[1], "?") if scrambled else chr(ch[0])
            chars.append(dict(u=u, x0=x0, x1=x1, y=round(ch[2][1], 1), ox=ch[2][0], sp=sid))
    rows = {}
    for c in chars:
        rows.setdefault(c["y"], []).append(c)
    toks = []
    for y, cs in rows.items():
        cs.sort(key=lambda c: c["ox"])
        cur = None
        for c in cs:
            if c["u"] == " ":
                if cur:
                    toks.append(cur)
                cur = None
            elif cur and c["x0"] - cur["x1"] < 1.6 and c["u"] != "-" and (scrambled or c["sp"] == cur["sp"]):   # LilyPond writes each word as its own text span
                cur["text"] += c["u"]
                cur["x1"] = c["x1"]
            else:
                if cur:
                    toks.append(cur)
                cur = dict(text=c["u"], x0=c["x0"], x1=c["x1"], y=y, sp=c["sp"])
                if c["u"] == "-":
                    toks.append(cur)
                    cur = None
        if cur:
            toks.append(cur)
    seen = set()
    for dd in doc[pn].get_drawings():
        r = dd["rect"]
        if dd["type"] in ("f", "fs") and 1.8 < r.width < 4.6 and r.height < 1.2:
            k = (round(r.x0, 1), round(r.y0, 1))
            if k in seen:
                continue
            seen.add(k)
            toks.append(dict(text="-", x0=r.x0, x1=r.x1, y=round(r.y0 + 2.0, 1)))
    return toks


if __name__ == "__main__":
    d = pymupdf.open(sys.argv[1])
    pn = int(sys.argv[2])
    for t in sorted(page_lyrics(d, pn), key=lambda t: (t["y"], t["x0"])):
        print(t["y"], round(t["x0"], 1), round(t["x1"], 1), repr(t["text"]))
