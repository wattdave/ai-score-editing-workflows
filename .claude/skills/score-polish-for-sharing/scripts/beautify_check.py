"""Beautifier checks for the Sibelius score that is open: render it to PDF and report what still looks unfinished.

  python3 beautify_check.py --expect-file /abs/score.sib [--json] [--pdf out.pdf]
  python3 beautify_check.py --pdf render.pdf --title "Title" --composer "Name"      # PDF only, no Sibelius

Read-only: it never edits the score. Checks (code: meaning):
  title-missing       the Score Info title is not printed on page 1
  composer-missing    the Score Info composer / lyricist is not printed on page 1
  footer-missing      no rights or source line ("Public domain", "Copyright", "(c)") anywhere
  footer-tight        the lowest staff ink sits closer than --footer-gap points above the footer line
  word-overlap        two words overprint each other (crowded or colliding lyrics and text)
  margin-overflow     a word runs outside the page margins (left/right 20 pt, bottom 6 pt)
  title-too-high      the title line is closer than 28 pt to the top edge of the paper
  lyric-numeral       a lyric word still starts with "1." (verse numbers belong in staff text: skill verse-numbers)
  sparse-last-page    several pages and the last one is less than a third full (a re-spacing may save a page)
  one-system-page     a page with a single system on a multi-page score
  generic-staff-name  a staff is still called "Voice0", "Staff 1" ...
  lyric-issues        sibelius-cli check-lyrics reports typos or cross-voice differences (collision notes are info)
Needs poppler (pdftotext, pdftoppm, pdfinfo). Exit status 0 when there are no errors or warnings."""
import argparse
import html
import json
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]  # .claude/skills/score-polish-for-sharing/scripts/ -> repository root
CLI = ["uv", "run", "--project", str(REPO), "sibelius-cli"]
WORD = re.compile(r'xMin="(-?[\d.]+)" yMin="(-?[\d.]+)" xMax="(-?[\d.]+)" yMax="(-?[\d.]+)">([^<]*)<')
FOOTER_WORDS = ("public", "copyright", "©", "(c)", "transcribed", "arrangement")


def norm(text):
    plain = unicodedata.normalize("NFKD", html.unescape(text)).encode("ascii", "ignore").decode()  # ä -> a
    return re.sub(r"[^\w]", "", plain.lower())


def cli(*args, expect=None):
    cmd = CLI + (["--expect-file", expect] if expect else []) + list(args)
    out = subprocess.run(cmd, capture_output=True, text=True)
    return out.stdout if out.returncode == 0 else ""


def pages_of(pdf):
    bbox = subprocess.run(["pdftotext", "-bbox", pdf, "-"], capture_output=True, text=True).stdout
    pages = []
    for chunk in bbox.split("<page ")[1:]:
        w = float(re.search(r'width="([\d.]+)"', chunk).group(1))
        h = float(re.search(r'height="([\d.]+)"', chunk).group(1))
        words = [(float(a), float(b), float(c), float(d), html.unescape(t)) for a, b, c, d, t in WORD.findall(chunk)]
        pages.append((w, h, words))
    return pages


def ink_rows(pdf, page, dpi=72):
    """Rows (in points from the top) that hold dark pixels on a page, via a grayscale raster."""
    ppm = subprocess.run(["pdftoppm", "-r", str(dpi), "-f", str(page), "-l", str(page), "-gray", pdf],
                         capture_output=True).stdout
    m = re.match(rb"P5\s+(\d+)\s+(\d+)\s+(\d+)\s", ppm)
    if not m:
        return [], 0
    w, h = int(m.group(1)), int(m.group(2))
    data = ppm[m.end():]
    s = 72 / dpi
    return [(r * s, min(data[r * w:(r + 1) * w]) < 128) for r in range(h)], w


def check_pdf(pdf, title=None, composer=None, lyricist=None, footer_gap=10.0, title_clear=28.0):
    found = []

    def add(sev, code, msg):
        found.append({"sev": sev, "code": code, "msg": msg})

    pages = pages_of(pdf)
    if not pages:
        add("error", "no-pages", "the PDF has no pages")
        return found
    text_words = [[w for w in ws if w[3] - w[1] < 20 and w[4].strip()] for _, _, ws in pages]  # drop music-font glyphs
    # the title is set larger than lyrics (about 23 pt); music-font glyph words are about 34 pt
    head_words = [w for w in pages[0][2] if w[4].strip() and (w[3] - w[1] < 30 or re.fullmatch(r"[A-Za-z\u00c0-\u00ff']{3,}", w[4]))]
    page1 = " ".join(norm(w[4]) for w in head_words)
    if title and norm(title) not in page1.replace(" ", ""):
        first = [norm(w[4]) for w in head_words if w[1] < pages[0][1] * 0.3]
        if not all(norm(t) in first for t in title.split() if norm(t)):
            add("error", "title-missing", f"title {title!r} is not printed on page 1")
    for what, name in (("composer", composer), ("lyricist", lyricist)):
        if name:
            last = norm(name.split()[-1].rstrip(".,"))
            if last and last not in page1.replace(" ", ""):
                add("warn", "composer-missing", f"{what} {name!r} is not printed on page 1")
    flat = " ".join(w[4].lower() for ws in text_words for w in ws)
    if not any(k in flat for k in FOOTER_WORDS):
        add("info", "footer-missing", "no rights or source line found (Public domain / Copyright / (c))")

    # footer: lowest staff ink above the footer line, on the page that carries it
    for pi, (w, h, ws) in enumerate(pages, 1):
        foot = [x for x in text_words[pi - 1] if x[4].lower().rstrip(".,") in ("public", "copyright", "©")]
        if not foot or foot[0][1] < h * 0.8:
            continue
        top = foot[0][1]
        rows, _ = ink_rows(pdf, pi)
        above = [y for y, dark in rows if dark and y < top - 1]
        if above and top - max(above) < footer_gap:
            add("warn", "footer-tight", f"page {pi}: lowest ink is {top - max(above):.0f} pt above the footer (< {footer_gap:.0f})")

    for pi, (w, h, ws) in enumerate(pages, 1):
        tw = text_words[pi - 1]
        over = []
        for i, a in enumerate(tw):
            for b in tw[i + 1:]:
                ix = min(a[2], b[2]) - max(a[0], b[0])
                iy = min(a[3], b[3]) - max(a[1], b[1])
                if ix > 1 and iy > 2:
                    smaller = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))
                    if smaller and ix * iy / smaller > 0.35:
                        over.append(f"{a[4]!r}/{b[4]!r}")
        if over:
            add("warn", "word-overlap", f"page {pi}: {len(over)} overprinting word pair(s), e.g. {', '.join(over[:4])}")
        out = [x[4] for x in tw if re.fullmatch(r"[A-Za-z\u00a9\u00c0-\u00ff']{2,}", x[4]) and (x[2] > w - 20 or x[0] < 20 or x[3] > h - 6)]
        if pi == 1:  # the title block must clear the paper edge (printers clip about 0.2 in): baseline of the top big line
            big = [x for x in pages[0][2] if x[3] - x[1] >= 15 and re.fullmatch(r"[A-Za-z\u00c0-\u00ff']{3,}", x[4])]
            if big:
                base = min(x[3] for x in big)
                if base < title_clear:
                    add("warn", "title-too-high", f"the title line's bottom is only {base:.0f} pt below the top edge (< {title_clear:.0f}): "
                        "it sits in the printer's clipping zone")
        if out:
            add("warn", "margin-overflow", f"page {pi}: words outside the margins: {out[:5]}")
        num = [x[4] for x in tw if re.match(r"^\d+\.\S", x[4])]
        if num:
            add("error", "lyric-numeral", f"page {pi}: lyric words that start with a verse number: {num[:5]}")

    if len(pages) > 1:
        rows, _ = ink_rows(pdf, len(pages))
        ink = [y for y, dark in rows if dark]
        h = pages[-1][1]
        low = max((y for y in ink if y < h * 0.9), default=0)
        if low < h / 3:
            add("info", "sparse-last-page", f"the last page ({len(pages)}) is filled to {low / h:.0%}")
    return found


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--expect-file", help="absolute .sib path of the open score (renders it)")
    ap.add_argument("--pdf", help="check this PDF instead of rendering (or where to write the render)")
    ap.add_argument("--title")
    ap.add_argument("--composer")
    ap.add_argument("--lyricist")
    ap.add_argument("--footer-gap", type=float, default=10.0)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    title, composer, lyricist = a.title, a.composer, a.lyricist
    extra = []
    pdf = a.pdf
    if a.expect_file:
        pdf = pdf or "/tmp/beautify_check.pdf"
        cli("verify-render", "--format", "pdf", "--out", pdf, expect=a.expect_file)
        info = json.loads(cli("score-info", expect=a.expect_file) or "{}")
        title = title or info.get("title")
        composer = composer or info.get("composer")
        lyricist = lyricist or info.get("lyricist")
        for s in json.loads(cli("staves", expect=a.expect_file) or "[]"):
            if re.match(r"^(voice|staff|part)\s*\d*$", (s.get("instrumentName") or "").strip(), re.I):
                extra.append({"sev": "warn", "code": "generic-staff-name", "msg": f"staff {s['staffNum']} is called {s['instrumentName']!r}"})
        lyr = cli("check-lyrics", expect=a.expect_file)
        issues = re.findall(r"\[([A-Z -]+)\] (.*)", lyr)
        real = [i for i in issues if "COLLISION" not in i[0]]
        if real:
            extra.append({"sev": "warn", "code": "lyric-issues", "msg": f"{len(real)} check-lyrics issue(s), e.g. {real[0][0]}: {real[0][1][:90]}"})
        if len(issues) > len(real):
            extra.append({"sev": "info", "code": "lyric-issues", "msg": f"{len(issues) - len(real)} note/lyric collision note(s) from check-lyrics"})
    if not pdf:
        ap.error("give --expect-file or --pdf")
    found = check_pdf(pdf, title, composer, lyricist, a.footer_gap) + extra
    if a.json:
        print(json.dumps({"pdf": pdf, "title": title, "findings": found}, indent=1))
    else:
        for f in found:
            print(f"{f['sev']:5} {f['code']:18} {f['msg']}")
        if not found:
            print("clean")
    sys.exit(1 if any(f["sev"] in ("error", "warn") for f in found) else 0)


if __name__ == "__main__":
    main()
