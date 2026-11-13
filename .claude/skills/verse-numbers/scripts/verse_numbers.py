"""Draw verse numbers ("1." "2." ...) beside the first syllable of each lyric verse in the open Sibelius score,
as plain staff text, NOT as part of the lyric (a "1. The" lyric is sung by vocal playback and read by every
lyric tool). Idempotent: a verse whose numeral text already sits at its first syllable is skipped.

Runs `uv run sibelius-cli` for this repository from any directory:
  python3 .claude/skills/verse-numbers/scripts/verse_numbers.py --expect-file /abs/x.sib [--staff 1] [--dx -120]
        [--strip-lyric-prefix] [--dry-run] [--save]
--strip-lyric-prefix first removes a leading "N. " that an earlier pass put inside the lyric text.
It then calibrates itself: it renders the score to PDF (needs poppler's pdftotext), measures where each numeral and
its verse's first word land, and solves Dy per verse so each numeral shares its word's baseline, and one Dx for all so the numerals form a
column, with the tightest row (the widest first word) kept --gap-pt away from its word. --dx and --dy-adjust are only the starting guess (or the final values with --no-auto)."""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]  # .claude/skills/verse-numbers/scripts/ -> repository root
CLI = ["uv", "run", "--project", str(REPO), "sibelius-cli"]
VERSE = re.compile(r"lyrics\.verse(\d)$")
PREFIX = re.compile(r"^\s*(\d+)\.\s*")


def cli(*args, expect=None, check=True):
    cmd = CLI + (["--expect-file", expect] if expect else []) + list(args)
    out = subprocess.run(cmd, capture_output=True, text=True)
    if check and out.returncode != 0:
        sys.exit(f"sibelius-cli {' '.join(args)} failed:\n{out.stderr or out.stdout}")
    return out.stdout


def query(staff, bars, types):
    text = cli("query", "--staff", str(staff), "--bars", bars, "--type", types)
    return json.loads(text)["objects"]


def first_syllables(staff, last_bar, from_bar=1):
    """Earliest lyric item per verse (a pickup or a late start may put a verse's first syllable after bar 1)."""
    first = {}
    start = from_bar
    while start <= last_bar:
        end = min(start + 7, last_bar)
        for o in query(staff, f"{start}-{end}", "LyricItem"):
            m = VERSE.search(o["styleId"])
            if not m:
                continue
            v = int(m.group(1))
            key = (o["bar"], o["position"])
            if v not in first or key < (first[v]["bar"], first[v]["position"]):
                first[v] = o
        if first and start > from_bar:
            break
        start = end + 1
    return first


def measure(first_words, expect=None):
    """Render the open score to PDF and return {verse: (baseline_error_pt, gap_pt)}: the verse's first word's
    bottom minus the numeral's bottom (positive = numeral too high), and the space between numeral and word."""
    pdf = "/tmp/verse_numbers_render.pdf"
    cli("verify-render", "--format", "pdf", "--out", pdf, expect=expect)
    bbox = subprocess.run(["pdftotext", "-bbox", pdf, "-"], capture_output=True, text=True).stdout
    verses = list(first_words)
    out = {}
    for page in bbox.split("<page ")[1:]:
        words = [
            (float(x0), float(y0), float(x1), float(y1), t)
            for x0, y0, x1, y1, t in re.findall(
                r'xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">([^<]*)<', page)
        ]
        merged = []  # pdftotext may split "1." into "1" and "." (a narrow digit): join them
        for w in words:
            if merged and w[4] == "." and merged[-1][4].isdigit() and 0 <= w[0] - merged[-1][2] < 3:
                x0, y0, x1, y1, t = merged[-1]
                merged[-1] = (x0, y0, w[2], max(y1, w[3]), t + ".")
            else:
                merged.append(w)
        words = merged
        prev = None  # bottom of the previous verse's word: verse rows run downwards in verse order
        for v in sorted(verses):
            if v in out:
                continue
            for n in [w for w in words if w[4] == f"{v}."]:
                right = [w for w in words if w[0] > n[0] and abs(w[3] - n[3]) < 25
                         and w[4].rstrip("-") and first_words[v].startswith(w[4].rstrip("-"))
                         and (prev is None or w[3] > prev + 3)]
                if right:
                    # several verses may start with the same word ("The"): take the topmost row still free
                    word = min(right, key=lambda w: (w[3], w[0]))
                    out[v] = (word[3] - n[3], word[0] - n[2])
                    prev = word[3]
                    break
    missing = [v for v in verses if v not in out]
    if missing:
        sys.exit(f"could not find the rendered numeral and first word for verses {missing} in {pdf}")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--expect-file", required=True, help="absolute .sib path the open score must be")
    ap.add_argument("--staff", type=int, default=1)
    ap.add_argument("--from-bar", type=int, default=1,
                    help="only look for first syllables from this score bar on: use it when the numbered verse rows "
                         "start in a later system than the first words (Ther is no rose: verse 1 is also sung "
                         "unnumbered in bars 1-6, the numerals start at bar 7)")
    ap.add_argument("--dx", type=int, default=-120, help="Dx of each numeral, 1/32 space (default -120)")
    ap.add_argument("--dy-adjust", type=int, default=0,
                    help="added to each lyric line's Dy for the numeral (1/32 space); the plain-text baseline differs "
                         "per score, so calibrate it on the render (negative = lower)")
    ap.add_argument("--gap-pt", type=float, default=2.5, help="space between numeral and word, points (default 2.5)")
    ap.add_argument("--no-auto", action="store_true",
                    help="do not calibrate from the render: use --dx and --dy-adjust as given (needs poppler's "
                         "pdftotext otherwise)")
    ap.add_argument("--strip-lyric-prefix", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--save", action="store_true")
    a = ap.parse_args()

    info = json.loads(cli("score-info"))
    first = first_syllables(a.staff, info["barCount"], a.from_bar)
    if not first:
        sys.exit("no lyric items found on that staff")

    strips = [
        {"staff": a.staff, "bar": o["bar"], "index": o["index"], "text": PREFIX.sub("", o["text"])}
        for o in first.values()
        if PREFIX.match(o["text"])
    ]
    existing = {
        (t["bar"], t["position"], t["text"])
        for bar in {o["bar"] for o in first.values()}
        for t in query(a.staff, f"{bar}-{bar}", "Text")
    }
    adds = [
        {"op": "add-text", "staff": a.staff, "bar": o["bar"], "position": o["position"], "text": f"{v}.",
         "styleId": "text.staff.plain"}
        for v, o in sorted(first.items())
        if (o["bar"], o["position"], f"{v}.") not in existing
    ]
    print(f"verses {sorted(first)}: strip {len(strips)} lyric prefixes, add {len(adds)} numerals")
    if a.dry_run:
        return

    if strips and a.strip_lyric_prefix:
        path = "/tmp/verse_numbers_strip.json"
        json.dump(strips, open(path, "w"))
        cli("patch-lyrics", "--file", path, "--font", "Times New Roman", "--font-size", "74", expect=a.expect_file)
    elif strips:
        print("warning: some lyrics start with 'N. '; pass --strip-lyric-prefix to remove them", file=sys.stderr)
    if adds:
        path = "/tmp/verse_numbers_add.json"
        json.dump(adds, open(path, "w"))
        cli("apply", "--file", path, expect=a.expect_file)
    objs = {}  # verse -> (bar, index) of its numeral text object
    for v, o in sorted(first.items()):
        for t in query(a.staff, f"{o['bar']}-{o['bar']}", "Text"):
            if t["position"] == o["position"] and t["text"] == f"{v}.":
                objs[v] = (t["bar"], t["index"])
    if len(objs) != len(first):
        sys.exit(f"numerals found for verses {sorted(objs)} but lyrics for {sorted(first)}")

    def place(values):
        """values: verse -> (dx, dy) in 1/32 space."""
        sets = []
        for v, (dx, dy) in values.items():
            bar, idx = objs[v]
            sets += [
                {"op": "set", "staff": a.staff, "bar": bar, "index": idx, "prop": "Dx", "value": int(round(dx))},
                {"op": "set", "staff": a.staff, "bar": bar, "index": idx, "prop": "Dy", "value": int(round(dy))},
            ]
        path = "/tmp/verse_numbers_set.json"
        json.dump(sets, open(path, "w"))
        cli("apply", "--file", path, expect=a.expect_file)

    start = {v: (a.dx, o["dy"] + a.dy_adjust) for v, o in first.items()}
    place(start)
    if not a.no_auto:
        # Solve Dx/Dy per verse from the rendered PDF: baseline of the numeral = baseline of the verse's first
        # word, and a fixed gap (a.gap_pt points) between the numeral and the word.
        words = {v: o["text"] for v, o in first.items()}
        probe = 40  # units moved up to measure how many points one unit is
        m0 = measure(words, expect=a.expect_file)
        up = {v: (dx, dy + probe) for v, (dx, dy) in start.items()}
        place(up)
        m1 = measure(words, expect=a.expect_file)
        solved = {}
        ks = {}
        for v in first:
            err0, err1 = m0[v][0], m1[v][0]  # lyric baseline minus numeral baseline, pt (grows as the numeral rises)
            k = (err1 - err0) / probe        # points per unit
            if k <= 0.01:
                sys.exit(f"verse {v}: moving the numeral did not move it in the PDF ({err0:.2f} -> {err1:.2f} pt)")
            dx1, dy1 = up[v]
            ks[v] = k
            solved[v] = (dx1 - (a.gap_pt - m1[v][1]) / k, dy1 - err1 / k)
            if abs(solved[v][1] - first[v]["dy"]) > 90:
                sys.exit(f"verse {v}: the numeral landed {solved[v][1] - first[v]['dy']:+.0f} units from its lyric line, "
                         "so it probably locked onto a neighbouring row: pass a closer --dy-adjust and rerun")
        # one shared Dx so the numerals form a column (as in the print); the widest first word sets how far left
        col = min(dx for dx, _ in solved.values())
        solved = {v: (col, dy) for v, (_, dy) in solved.items()}
        place(solved)
        final = measure(words, expect=a.expect_file)
        for _ in range(2):  # refine: baselines to 0, the tightest gap to the target
            tight = min(g for _, g in final.values())
            if all(abs(final[v][0]) <= 0.3 for v in first) and abs(tight - a.gap_pt) <= 0.3:
                break
            kmean = sum(ks.values()) / len(ks)
            col -= (a.gap_pt - tight) / kmean
            solved = {v: (col, solved[v][1] - final[v][0] / ks[v]) for v in first}
            place(solved)
            final = measure(words, expect=a.expect_file)
        print(f"column Dx {col:.0f}")
        for v in sorted(first):
            print(f"verse {v}: Dy {solved[v][1]:.0f}; baseline off {final[v][0]:+.2f} pt, gap to the word {final[v][1]:.2f} pt")
        bad = [v for v in first if abs(final[v][0]) > 0.5]
        if bad:
            sys.exit(f"verses {bad} are still off the lyric baseline by more than 0.5 pt: not saved, check the render")
    if a.save:
        cli("save", expect=a.expect_file)
    print("done" + (" and saved" if a.save else " (not saved)"))


if __name__ == "__main__":
    main()
