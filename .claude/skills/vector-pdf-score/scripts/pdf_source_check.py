"""Say what made a score PDF and which skill can read it: scan, Sibelius, Finale, LilyPond, MusiXTeX, MuseScore or other.

Usage: uv run --with pymupdf python -I pdf_source_check.py score.pdf [more.pdf ...]

Looks at the first pages only: page images, vector drawings, horizontal staff lines, and the font names (the creator
and producer fields are often overwritten by PDF converters such as iLovePDF, so the fonts decide). Prints one line
per file with the verdict and the next step."""
import argparse
import re
import sys

# music-font name prefix -> (program, which skill reads it)
MUSIC_FONTS = [
    ("Opus", "Sibelius (Opus)", "vector-pdf-score (reader supported)"),
    ("Helsinki", "Sibelius (Helsinki)", "vector-pdf-score (reader supported)"),
    ("Petrucci", "Finale (legacy Petrucci)", "vector-pdf-score (reader supports it; see its Finale section)"),
    ("Maestro", "Finale (Maestro)", "not supported yet: glyph codes unchecked"),
    ("FinaleMaestro", "Finale (Maestro)", "not supported yet: glyph codes unchecked"),
    ("Toccata", "Finale (Toccata)", "not supported yet: glyph codes unchecked"),
    ("Engraver", "Finale (text font only)", "not supported yet: glyph codes unchecked"),
    ("Emmentaler", "LilyPond", "lilypond-pdf-score"),
    ("TeXMUSIX", "MusiXTeX", "hand-read with PyMuPDF (vector-pdf-score, MusiXTeX section)"),
    ("TeXXSL", "MusiXTeX", "hand-read with PyMuPDF (vector-pdf-score, MusiXTeX section)"),
    ("Leland", "MuseScore 4", "not supported yet: glyph codes unchecked"),
    ("Bravura", "SMuFL font (Dorico, MuseScore or Finale)", "not supported yet: glyph codes unchecked"),
    ("November", "SMuFL font (Dorico or Finale)", "not supported yet: glyph codes unchecked"),
    ("Musejazz", "MuseScore", "not supported yet: glyph codes unchecked"),
    ("Gonville", "LilyPond (Gonville)", "lilypond-pdf-score"),
]
PAGES_LOOKED_AT = 3


def font_name(raw: str) -> str:
    return re.sub(r"^[A-Z]{6}\+", "", raw)     # drop the subset tag


def check(path: str) -> dict:
    import pymupdf
    doc = pymupdf.open(path)
    n = len(doc)
    images = drawings = staff_lines = 0
    fonts: set[str] = set()
    for page in list(doc)[:PAGES_LOOKED_AT]:
        images += len(page.get_images())
        for f in page.get_fonts():
            fonts.add(font_name(f[3]))
        ys = set()
        for dr in page.get_drawings():
            drawings += 1
            for it in dr["items"]:
                if it[0] == "l" and abs(it[1].y - it[2].y) < 0.01 and abs(it[1].x - it[2].x) > 100:
                    ys.add(round(it[1].y, 1))
        staff_lines += len(ys)
    # table order sets priority: a music font beats a text font from the same program (EngraverText)
    found = [(prog, skill, f) for pre, prog, skill in MUSIC_FONTS for f in sorted(fonts) if f.startswith(pre)]
    meta = doc.metadata or {}
    if found:
        prog, skill, font = found[0]
        verdict, step = prog, skill
        kind = "vector"
    elif staff_lines >= 5:
        kind = "vector"
        verdict = "vector staves, no named music font (fonts renamed, outlined or printed through a driver)"
        if any(f.startswith("CIDFont") for f in fonts):
            verdict += "; CIDFont names suggest a print driver"
        step = "try vector-pdf-score; it accepts renamed Sibelius fonts (symbol codes U+F0xx); otherwise dump the glyphs first"
    elif images:
        kind, verdict = "scan", "scanned image"
        step = "omr-halbestunde, omr-musescore-convert or hand-transcribe-poor-scan"
    else:
        kind, verdict, step = "text", "no staves, no images (text only?)", "nothing to read"
    return dict(path=path, pages=n, kind=kind, verdict=verdict, step=step, images=images, drawings=drawings,
                staff_lines=staff_lines, fonts=sorted(fonts), creator=meta.get("creator", ""),
                producer=meta.get("producer", ""))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf", nargs="+")
    ap.add_argument("-v", "--verbose", action="store_true", help="also list every font, creator and producer")
    args = ap.parse_args(argv)
    rc = 0
    for p in args.pdf:
        try:
            r = check(p)
        except Exception as exc:    # unreadable file: report and go on
            print(f"{p}: cannot open ({exc})")
            rc = 1
            continue
        print(f"{p}: {r['kind']} - {r['verdict']} | {r['pages']} pages, images {r['images']}, drawings {r['drawings']}, "
              f"staff lines {r['staff_lines']} (first {PAGES_LOOKED_AT} pages) -> {r['step']}")
        if args.verbose:
            print(f"    fonts: {', '.join(r['fonts']) or '-'}; creator: {r['creator'] or '-'}; producer: {r['producer'] or '-'}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
