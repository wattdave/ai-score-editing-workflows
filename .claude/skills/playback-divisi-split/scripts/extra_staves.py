#!/usr/bin/env python3
"""Playback copy with an extra "div" staff per part, so that every note is audible.

``playback_split.py`` keeps one staff per part and must drop or move chord notes.
This script instead adds a second staff after each part:

* where the part sings one note, the div staff duplicates it (never rests);
* where the part has a chord (divisi), the highest note stays on the main staff and
  the lowest goes to the div staff; lyrics are copied to both.

Nothing is dropped. The script checks that every source note shows up on the main
or the div staff and exits non-zero if one is missing. Parts must hold one voice
per staff, with at most two notes in a chord (three-note chords are refused).

Usage: extra_staves.py IN.xml OUT.xml [--suffix " div"] [--abbr-suffix " d."]
"""

from __future__ import annotations

import argparse
import copy
import sys
import xml.etree.ElementTree as ET

STEP = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def midi(note: ET.Element) -> int:
    pitch = note.find("pitch")
    return (12 * (int(pitch.findtext("octave")) + 1) + STEP[pitch.findtext("step")]
            + round(float(pitch.findtext("alter") or 0)))


def groups(measure: ET.Element) -> list[list[ET.Element]]:
    out: list[list[ET.Element]] = []
    for note in measure.findall("note"):
        if note.find("chord") is not None:
            out[-1].append(note)
        else:
            out.append([note])
    return out


def single(note: ET.Element) -> ET.Element:
    note = copy.deepcopy(note)
    for chord in note.findall("chord"):
        note.remove(chord)
    return note


def split_group(group: list[ET.Element]) -> tuple[ET.Element, ET.Element]:
    ordered = sorted(group, key=midi, reverse=True)
    if len(ordered) > 2:
        raise SystemExit(f"{len(ordered)}-note chord: add more div staves or choose notes by hand")
    lyrics = [copy.deepcopy(lyric) for note in group for lyric in note.findall("lyric")]
    upper, lower = single(ordered[0]), single(ordered[-1])
    for note in (upper, lower):
        for lyric in note.findall("lyric"):
            note.remove(lyric)
        for lyric in lyrics:  # lyrics come last in a note, so appending stays schema-valid
            note.append(copy.deepcopy(lyric))
    return upper, lower


def replace_notes(measure: ET.Element, notes: list[ET.Element]) -> None:
    children = list(measure)
    first = next((i for i, c in enumerate(children) if c.tag == "note"), len(children))
    for child in children:
        if child.tag == "note":
            measure.remove(child)
    for offset, note in enumerate(notes):
        measure.insert(first + offset, note)


def build(root: ET.Element, suffix: str, abbr_suffix: str) -> int:
    """Add a div part after every part. Returns the number of divided chords."""
    part_list = root.find("part-list")
    divided = 0
    for part in list(root.findall("part")):
        pid = part.get("id")
        div = copy.deepcopy(part)
        div.set("id", pid + "d")
        for main, other in zip(part.findall("measure"), div.findall("measure")):
            upper: list[ET.Element] = []
            lower: list[ET.Element] = []
            for group in groups(main):
                if len(group) == 1:
                    upper.append(single(group[0]))
                    lower.append(single(group[0]))
                else:
                    hi, lo = split_group(group)
                    upper.append(hi)
                    lower.append(lo)
                    divided += 1
            replace_notes(main, upper)
            replace_notes(other, lower)
        score_part = next(s for s in part_list.findall("score-part") if s.get("id") == pid)
        copy_part = copy.deepcopy(score_part)
        copy_part.set("id", pid + "d")
        name = copy_part.find("part-name")
        if name is not None:
            name.text = (name.text or pid) + suffix
        abbreviation = copy_part.find("part-abbreviation")
        if abbreviation is not None:
            abbreviation.text = (abbreviation.text or "") + abbr_suffix
        part_list.insert(list(part_list).index(score_part) + 1, copy_part)
        root.insert(list(root).index(part) + 1, div)
    return divided


def check(source: ET.Element, result: ET.Element) -> list[str]:
    """Every source note must sound on the main or the div staff."""
    problems: list[str] = []
    for part in source.findall("part"):
        pid = part.get("id")
        main = result.find(f"part[@id='{pid}']")
        div = result.find(f"part[@id='{pid}d']")
        for src, a, b in zip(part.findall("measure"), main.findall("measure"), div.findall("measure")):
            for index, group in enumerate(groups(src)):
                want = sorted(midi(n) for n in group if n.find("pitch") is not None)
                have = sorted({midi(g[index][0]) for g in (groups(a), groups(b))
                               if index < len(g) and g[index][0].find("pitch") is not None})
                if sorted(set(want)) != have:
                    problems.append(f"{pid} bar {src.get('number')} note {index + 1}: "
                                    f"source {want}, staves {have}")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("input")
    parser.add_argument("output")
    parser.add_argument("--suffix", default=" div", help="added to each part name (default ' div')")
    parser.add_argument("--abbr-suffix", default=" d.", help="added to each abbreviation (default ' d.')")
    args = parser.parse_args()
    tree = ET.parse(args.input)
    source = copy.deepcopy(tree.getroot())
    divided = build(tree.getroot(), args.suffix, args.abbr_suffix)
    problems = check(source, tree.getroot())
    title = tree.getroot().find("work/work-title")
    if title is not None and not (title.text or "").endswith("(playback)"):
        title.text = (title.text or "") + " (playback)"
    ET.indent(tree)
    tree.write(args.output, encoding="utf-8", xml_declaration=True)
    print(f"{divided} chords split; {len(problems)} notes missing", file=sys.stderr)
    for line in problems[:20]:
        print("MISSING", line)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
