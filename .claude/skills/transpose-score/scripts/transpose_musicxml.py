#!/usr/bin/env python3
"""Transpose a MusicXML file by an interval, with correct spelling and key signature.

Standard library only. Pitches, key signatures, chord symbols and ficta marks
change; durations, lyrics, beams, ties, breaks and layout are copied unchanged.

Usage:
    transpose_musicxml.py IN OUT --by "up M2" [--fifths N] [--keep-key]
                          [--octave PART=N ...] [--report]

--by       direction and interval: "up M2", "down m3", "up P4", "down P5", "up P8".
           Intervals: m2 M2 m3 M3 P4 A4 d5 P5 m6 M6 m7 M7 P8 (A4 and d5 are the tritone).
--fifths   key signature to write in every key element (negative flats, positive
           sharps). Default: the old key shifted by the interval.
--keep-key leave key signatures alone (spell with accidentals instead).
--octave   move one part by whole octaves after transposing, e.g. P4=+1 or
           "Bassus=+1" (part id or part name). Repeatable.
--report   print each part's lowest and highest note before and after.

Ficta: an `accidental-mark` (editorial accidental above the note) is rewritten
to name the new accidental of that note (flat, natural or sharp), so a ficta
natural on B in B-flat major becomes a ficta sharp on C when moved up a major
second to no signature. Explicit `<accidental>` elements are removed; editors
work them out from the pitch and the key signature.

Reads .xml/.musicxml/.mxl; writes plain MusicXML (the XML declaration and
DOCTYPE are kept).
"""

from __future__ import annotations

import argparse
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

STEPS = "CDEFGAB"
NATURAL = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
INTERVALS = {
    "m2": (1, 1), "M2": (1, 2), "m3": (2, 3), "M3": (2, 4), "P4": (3, 5),
    "A4": (3, 6), "d5": (4, 6), "P5": (4, 7), "m6": (5, 8), "M6": (5, 9),
    "m7": (6, 10), "M7": (6, 11), "P8": (7, 12),
}
ACC_NAME = {-2: "double-flat", -1: "flat", 0: "natural", 1: "sharp", 2: "double-sharp"}


def read_text(path: Path) -> str:
    if path.suffix.lower() == ".mxl":
        with zipfile.ZipFile(path) as z:
            name = next(n for n in z.namelist() if n.endswith((".xml", ".musicxml")) and not n.startswith("META-INF"))
            return z.read(name).decode("utf-8")
    return path.read_text(encoding="utf-8")


def parse_by(text: str) -> tuple[int, int, int]:
    """Return (direction, diatonic steps, semitones)."""
    m = re.fullmatch(r"\s*(up|down)\s+([mMPAd]\d)\s*", text)
    if not m or m.group(2) not in INTERVALS:
        raise ValueError(f'cannot read interval "{text}"; use e.g. "up M2" or "down m3"')
    steps, semis = INTERVALS[m.group(2)]
    return (1 if m.group(1) == "up" else -1), steps, semis


def shift_pitch(step: str, alter: int, octave: int, direction: int, steps: int, semis: int) -> tuple[str, int, int]:
    index = STEPS.index(step) + direction * steps
    new_octave = octave + index // 7
    new_step = STEPS[index % 7]
    midi = 12 * (octave + 1) + NATURAL[step] + alter + direction * semis
    return new_step, midi - (12 * (new_octave + 1) + NATURAL[new_step]), new_octave


def fifths_delta(direction: int, steps: int, semis: int) -> int:
    return direction * (7 * semis - 12 * steps)


def pitch_midi(p: ET.Element) -> int:
    return 12 * (int(p.findtext("octave")) + 1) + NATURAL[p.findtext("step")] + int(float(p.findtext("alter") or 0))


def set_pitch(p: ET.Element, step: str, alter: int, octave: int) -> None:
    p.find("step").text = step
    old = p.find("alter")
    if old is not None:
        p.remove(old)
    if alter:
        a = ET.Element("alter")
        a.text = str(alter)
        p.insert(1, a)
    p.find("octave").text = str(octave)


def name_of(midi: int) -> str:
    names = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
    return f"{names[midi % 12]}{midi // 12 - 1}"


def part_labels(root: ET.Element) -> dict[str, list[str]]:
    out = {}
    for sp in root.iter("score-part"):
        out[sp.get("id")] = [sp.get("id"), (sp.findtext("part-name") or "").strip()]
    return out


def transpose(root: ET.Element, direction: int, steps: int, semis: int, fifths: int | None, keep_key: bool, octaves: dict[str, int]) -> dict:
    stats = {"notes": 0, "ficta": 0, "harmony": 0, "keys": 0, "ranges": {}}
    delta = fifths_delta(direction, steps, semis)
    labels = part_labels(root)
    for part in root.findall("part"):
        pid = part.get("id")
        shift = 0
        for key in labels.get(pid, [pid]):
            shift = octaves.get(key, shift)
        low = [999, 999]
        high = [-1, -1]
        for note in part.iter("note"):
            p = note.find("pitch")
            if p is None:
                continue
            before = pitch_midi(p)
            step, alter, octave = shift_pitch(p.findtext("step"), int(float(p.findtext("alter") or 0)), int(p.findtext("octave")), direction, steps, semis)
            set_pitch(p, step, alter, octave + shift)
            after = pitch_midi(p)
            low = [min(low[0], before), min(low[1], after)]
            high = [max(high[0], before), max(high[1], after)]
            for acc in note.findall("accidental"):
                note.remove(acc)
            for mark in note.iter("accidental-mark"):
                mark.text = ACC_NAME.get(alter, "natural")
                stats["ficta"] += 1
            stats["notes"] += 1
        stats["ranges"][pid] = (low, high, labels.get(pid, ["", ""])[1])
        for h in part.iter("harmony"):
            for tag, atag in (("root", "root"), ("bass", "bass")):
                el = h.find(tag)
                if el is None:
                    continue
                s = el.find(f"{tag}-step")
                a = el.find(f"{tag}-alter")
                step, alter, _ = shift_pitch(s.text, int(float(a.text)) if a is not None and a.text else 0, 4, direction, steps, semis)
                s.text = step
                if a is not None:
                    el.remove(a)
                if alter:
                    new = ET.Element(f"{tag}-alter")
                    new.text = str(alter)
                    el.insert(1, new)
            stats["harmony"] += 1
        if not keep_key:
            for k in part.iter("key"):
                f = k.find("fifths")
                if f is not None and f.text is not None:
                    f.text = str(fifths if fifths is not None else int(f.text) + delta)
                    stats["keys"] += 1
    return stats


def header_of(text: str) -> str:
    m = re.search(r"<score-(partwise|timewise)\b", text)
    return text[: m.start()] if m else ""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input")
    ap.add_argument("output")
    ap.add_argument("--by", required=True)
    ap.add_argument("--fifths", type=int)
    ap.add_argument("--keep-key", action="store_true")
    ap.add_argument("--octave", action="append", default=[], metavar="PART=N")
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args(argv)
    try:
        direction, steps, semis = parse_by(args.by)
        octaves = {}
        for item in args.octave:
            name, _, n = item.partition("=")
            octaves[name.strip()] = int(n)
        text = read_text(Path(args.input))
        root = ET.fromstring(text)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if root.tag != "score-partwise":
        print("error: only score-partwise MusicXML is supported", file=sys.stderr)
        return 2
    stats = transpose(root, direction, steps, semis, args.fifths, args.keep_key, octaves)
    ET.indent(root, space="  ")
    header = header_of(text) or '<?xml version="1.0" encoding="UTF-8"?>\n'
    Path(args.output).write_text(header + ET.tostring(root, encoding="unicode") + "\n", encoding="utf-8")
    print(f"wrote {args.output}: {stats['notes']} notes, {stats['ficta']} ficta marks, {stats['harmony']} chord symbols, {stats['keys']} key signatures")
    if args.report:
        for pid, (low, high, name) in stats["ranges"].items():
            if low[0] < 999:
                print(f"{pid} {name}: {name_of(low[0])}-{name_of(high[0])} -> {name_of(low[1])}-{name_of(high[1])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
