#!/usr/bin/env python3
"""Assemble finished lyric pieces into one Markdown file in running order.

    assemble_lyrics.py --order order.txt --out "Show - Lyrics.md" piece1.md piece2.md ...

Each piece file holds one or more sections that start with `## Title`.
order.txt lists the book: a line `# Act 1` starts a group, every other
non-blank line is a piece title, in order. A title with no section is
reported and gets a "[LYRICS TO BE INSERTED]" slot, so nothing is dropped
quietly. The book starts with a numbered contents list.
"""
import argparse
import re
import sys
from pathlib import Path


def sections(paths):
    secs = {}
    for p in paths:
        txt = Path(p).read_text(encoding="utf-8")
        for m in re.finditer(r"^## (.+?)\n(.*?)(?=^## |\Z)", txt, re.S | re.M):
            title = m.group(1).strip()
            if title in secs:
                sys.exit(f"duplicate section: {title}")
            secs[title] = m.group(2).strip("\n")
    return secs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--order", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--title", default="Lyrics")
    ap.add_argument("pieces", nargs="+")
    a = ap.parse_args()

    secs = sections(a.pieces)
    groups, cur = [], None
    for line in Path(a.order).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("# "):
            cur = (line[2:], [])
            groups.append(cur)
        else:
            if cur is None:
                cur = ("", [])
                groups.append(cur)
            cur[1].append(line)

    out = [f"# {a.title}\n", "## Contents\n"]
    n = 0
    for name, titles in groups:
        if name:
            out.append(f"**{name}**\n")
        for t in titles:
            n += 1
            out.append(f"{n}. {t}")
        out.append("")
    used, missing = set(), []
    for name, titles in groups:
        out.append("\n---\n")
        if name:
            out.append(f"# {name}\n")
        for t in titles:
            if t in secs:
                used.add(t)
                out.append(f"## {t}\n\n{secs[t]}\n")
            else:
                missing.append(t)
                out.append(f"## {t}\n\n**[LYRICS TO BE INSERTED]**\n")
    Path(a.out).write_text("\n".join(out), encoding="utf-8")
    print(f"{n} pieces written to {a.out}")
    if missing:
        print("no section for:", "; ".join(missing))
    extra = set(secs) - used
    if extra:
        print("sections not in the order file:", "; ".join(sorted(extra)))


main()
