#!/usr/bin/env python3
"""Rebuild readable lyric text from `sibelius-cli read-lyrics` JSON.

    lyrics_text.py raw/SLUG.json [raw/OTHER.json ...] [--staves raw/SLUG.staves.txt]

Words are rebuilt from syllableType (begin/middle join to the next syllable,
end/single stand alone), so a word split across a barline joins correctly;
the --words and --compact views of read-lyrics lose that and should not be used.
Prints, per piece, the distinct texts per verse, grouped by the staves that
agree. Where parts differ (repeats, echoes, solo vs chorus) the groups show it.
"""
import json
import sys
from collections import defaultdict
from pathlib import Path


def load(path):
    raw = Path(path).read_text(encoding="utf-8")
    return json.loads(raw[raw.index("["):])


def build(items):
    """-> {staff: {verse: [words]}} in score order. Hidden lyrics are skipped."""
    by = defaultdict(lambda: defaultdict(list))
    for it in items:
        if not it.get("hidden"):
            by[it["staff"]][it.get("line", 1)].append(it)
    out = {}
    for staff, verses in by.items():
        out[staff] = {}
        for verse, its in sorted(verses.items()):
            its.sort(key=lambda i: (i["bar"], i["position"], i["index"]))
            words, cur = [], ""
            for it in its:
                cur += it["text"].replace(" ", " ")
                if it.get("syllableType") in ("begin", "middle"):
                    continue
                words.append(cur.strip())
                cur = ""
            if cur:
                words.append(cur.strip())
            out[staff][verse] = [w for w in words if w]
    return out


def staff_names(path):
    try:
        return {s["staffNum"]: s["instrumentName"] for s in json.loads(Path(path).read_text())}
    except Exception:
        return {}


def main(argv):
    names = {}
    if "--staves" in argv:
        i = argv.index("--staves")
        names = staff_names(argv[i + 1])
        argv = argv[:i] + argv[i + 2:]
    for path in argv:
        data = build(load(path))
        if len(argv) > 1:
            print(f"\n######## {Path(path).stem}")
        groups = defaultdict(list)
        for staff, verses in sorted(data.items()):
            for v, words in verses.items():
                groups[(v, " ".join(words))].append(names.get(staff, staff))
        for (v, text), staves in sorted(groups.items(), key=lambda x: (x[0][0], x[0][1])):
            print(f"[verse {v}] staves: {', '.join(map(str, staves))}\n{text}\n")


if __name__ == "__main__":
    main(sys.argv[1:])
