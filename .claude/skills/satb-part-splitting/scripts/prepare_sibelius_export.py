#!/usr/bin/env python3
"""Fix two quirks of a MusicXML file exported from Sibelius before splitting it.

1. Chord members come out with different <duration> values (for example
   E4:192 with G4:128 in one chord). Sibelius itself holds one length per chord,
   the longest, so every member is set to the longest.
2. Lyric verses are numbered "part1verse1".."part1verseN", which Sibelius folds
   onto a single lyric line when the file is imported again. They become 1..N.

Usage: prepare_sibelius_export.py in.xml out.xml
"""

from __future__ import annotations

import re
import sys

from lxml import etree


def normalize_chords(root: etree._Element) -> int:
    fixed = 0
    for measure in root.iter("measure"):
        group: list[etree._Element] = []
        for el in list(measure) + [None]:
            starts_new = el is None or el.tag != "note" or el.find("chord") is None
            if starts_new:
                durations = [int(n.findtext("duration")) for n in group if n.findtext("duration")]
                if len(set(durations)) > 1:
                    for n in group:
                        n.find("duration").text = str(max(durations))
                    fixed += 1
                group = []
            if el is not None and el.tag == "note":
                group.append(el)
    return fixed


def renumber_verses(root: etree._Element) -> int:
    count = 0
    for lyric in root.iter("lyric"):
        match = re.fullmatch(r"part\d+verse(\d+)", lyric.get("number", ""))
        if match:
            lyric.set("number", match.group(1))
            count += 1
    return count


def main(src: str, dst: str) -> None:
    tree = etree.parse(src)
    chords = normalize_chords(tree.getroot())
    lyrics = renumber_verses(tree.getroot())
    tree.write(dst, xml_declaration=True, encoding="UTF-8")
    print(f"normalized {chords} chords, renumbered {lyrics} lyrics: {dst}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    main(sys.argv[1], sys.argv[2])
