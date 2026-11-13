"""Fix what beautify_check.py reports in the open Sibelius score, for the two defects a script can repair safely:
  title-too-high  raise aboveTopStaveGap until the title baseline is --title-base pt below the top edge (the title follows
                  the first system; this moves the music down by the same amount and may add a page: checked)
  footer-tight    bottomMargin 12 mm and belowBottomStaveGap 35 mm (the Nelson Carol Book footer setting)
Everything else is reported and left alone. Run beautify_check.py first; this script reruns it after each fix and
refuses to save a result that has more findings than before.

  python3 beautify_fix.py --expect-file /abs/score.sib [--save] [--title-base 38]
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import beautify_check as bc  # noqa: E402



def title_base(pdf):
    w, h, ws = bc.pages_of(pdf)[0]
    big = [x for x in ws if x[3] - x[1] >= 15 and re.fullmatch(r"[A-Za-zÀ-ÿ']{3,}", x[4])]
    return min(x[3] for x in big) if big else None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--expect-file", required=True)
    ap.add_argument("--title-base", type=float, default=38.0)
    ap.add_argument("--save", action="store_true")
    a = ap.parse_args()
    f = a.expect_file
    pdf = "/tmp/beautify_fix.pdf"

    def run(*args):
        r = subprocess.run(bc.CLI + ["--expect-file", f, *args], capture_output=True, text=True)
        if r.returncode:
            sys.exit(f"sibelius-cli {args[0]} failed: {r.stderr or r.stdout}")
        return r.stdout

    def apply_ops(ops):
        json.dump(ops, open("/tmp/beautify_fix.json", "w"))
        return run("apply", "--file", "/tmp/beautify_fix.json")

    def findings_of(path):
        info = json.loads(run("score-info"))
        return bc.check_pdf(path, info.get("title"), info.get("composer"), info.get("lyricist"))

    def findings():
        run("verify-render", "--format", "pdf", "--out", pdf)
        info = json.loads(run("score-info"))
        return bc.check_pdf(pdf, info.get("title"), info.get("composer"), info.get("lyricist"))

    before = findings()
    codes = {x["code"] for x in before}
    pages_before = len(bc.pages_of(pdf))
    if codes & {"title-too-high", "title-missing"}:  # a title pushed off the page counts as too high
        # The page-aligned title follows the first system: Dy on it is ignored, and the title baseline is a fixed
        # distance above the top staff (topMargin + aboveTopStaveGap). Raise aboveTopStaveGap. Layout values cannot
        # be read back, so measure: two gaps give pt per mm, then solve for --title-base.
        # A title added with add-text starts at Dy 496 (above the page) and Dy cannot be changed: it only shows
        # once the first system is low enough (about 50 mm), so try a second probe pair before giving up.
        for g1, g2 in ((20.0, 25.0), (60.0, 65.0)):
            apply_ops([{"op": "set-layout", "aboveTopStaveGap": g1}])
            run("verify-render", "--format", "pdf", "--out", pdf)
            b1 = title_base(pdf)
            apply_ops([{"op": "set-layout", "aboveTopStaveGap": g2}])
            run("verify-render", "--format", "pdf", "--out", pdf)
            b2 = title_base(pdf)
            if b1 is not None and b2 is not None:
                break
        else:
            sys.exit("the title is not drawn at any probe gap: look at the score")
        slope = (b2 - b1) / (g2 - g1)
        if slope <= 0.5:
            sys.exit(f"the title does not follow aboveTopStaveGap (moved {b2 - b1:.1f} pt for 5 mm): fix it by hand")
        gap = round(max(0.0, g1 + (a.title_base - b1) / slope), 1)
        apply_ops([{"op": "set-layout", "aboveTopStaveGap": gap}])
        run("verify-render", "--format", "pdf", "--out", pdf)
        print(f"title: aboveTopStaveGap {gap} mm ({slope:.2f} pt per mm), baseline now {title_base(pdf):.0f} pt")
    if "footer-tight" in codes:
        for gap in (35, 45):  # systems are justified down to the bottom gap: a bigger gap lifts the last staff
            apply_ops([{"op": "set-layout", "bottomMargin": 12, "belowBottomStaveGap": gap}])
            run("verify-render", "--format", "pdf", "--out", pdf)
            if not any(x["code"] == "footer-tight" for x in findings_of(pdf)):
                break
        print(f"footer: bottomMargin 12, belowBottomStaveGap {gap}")
    after = findings()
    pages_after = len(bc.pages_of(pdf))
    bad = [x for x in after if x["sev"] in ("error", "warn")]
    for x in after:
        print(f"{x['sev']:5} {x['code']:18} {x['msg'][:110]}")
    if pages_after != pages_before:
        sys.exit(f"page count changed {pages_before} -> {pages_after}: not saved, undo in Sibelius (Cmd+Z) and look")
    if a.save:
        run("save")
        print("saved")


if __name__ == "__main__":
    main()
