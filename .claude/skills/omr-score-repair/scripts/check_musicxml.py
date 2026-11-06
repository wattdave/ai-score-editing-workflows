#!/usr/bin/env python3
"""Check a MusicXML file for the structure mistakes that raise Sibelius import warnings.

Run it after any script edits an OMR file and before OpenScore. Checks:

* ``<attributes>`` children are in schema order (``clef`` before ``transpose``);
* ``<note>`` children are in schema order (chord, pitch|rest, duration, tie, voice,
  type, dot, accidental, stem, staff, beam, notations, lyric);
* a note holds at most one ``<rest/>`` and never both a rest and a pitch;
* every part has the same number of bars, and every bar adds up to the bar length
  (``--no-durations`` skips this, for scores with pickups or anacruses by design).

Exits 1 and prints each problem when something is wrong.
"""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET

ATTRIBUTES = ["footnote", "level", "divisions", "key", "time", "staves", "part-symbol", "instruments",
              "clef", "staff-details", "transpose", "for-part", "directive", "measure-style"]
NOTE = ["grace", "cue", "chord", "pitch", "unpitched", "rest", "duration", "tie", "instrument",
        "footnote", "level", "voice", "type", "dot", "accidental", "time-modification", "stem",
        "notehead", "notehead-text", "staff", "beam", "notations", "lyric", "play"]


def order_problem(element: ET.Element, order: list[str]) -> str | None:
    last = -1
    for child in element:
        if child.tag not in order:
            continue
        index = order.index(child.tag)
        if index < last:
            return f"<{child.tag}> comes after <{order[last]}>"
        last = max(last, index)
    return None


def check(root: ET.Element, durations: bool) -> list[str]:
    problems: list[str] = []
    counts: dict[str, int] = {}
    for part in root.findall("part"):
        pid = part.get("id")
        measures = part.findall("measure")
        counts[pid] = len(measures)
        divisions, beats, beat_type = 1, 4, 4
        for measure in measures:
            number = measure.get("number")
            for attributes in measure.findall("attributes"):
                if (value := attributes.findtext("divisions")):
                    divisions = int(value)
                time = attributes.find("time")
                if time is not None and time.findtext("beats") and "+" not in time.findtext("beats"):
                    beats, beat_type = int(time.findtext("beats")), int(time.findtext("beat-type"))
                if (message := order_problem(attributes, ATTRIBUTES)):
                    problems.append(f"{pid} bar {number}: attributes: {message}")
            position = 0
            for note in measure.findall("note"):
                if (message := order_problem(note, NOTE)):
                    problems.append(f"{pid} bar {number}: note: {message}")
                rests = len(note.findall("rest"))
                if rests > 1 or (rests and note.find("pitch") is not None):
                    problems.append(f"{pid} bar {number}: note has {rests} rest(s) and "
                                    f"{'a pitch' if note.find('pitch') is not None else 'no pitch'}")
                if note.find("chord") is None and note.find("grace") is None:
                    position += int(note.findtext("duration") or 0)
            for element in measure:
                if element.tag in ("backup", "forward"):
                    position = None
                    break
            if durations and position is not None and number not in ("0", "1"):
                if position != divisions * 4 * beats // beat_type:
                    problems.append(f"{pid} bar {number}: lasts {position}, bar is "
                                    f"{divisions * 4 * beats // beat_type}")
    if len(set(counts.values())) > 1:
        problems.append(f"parts differ in bar count: {counts}")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("input", help="MusicXML file (uncompressed)")
    parser.add_argument("--no-durations", dest="durations", action="store_false",
                        help="skip the bar-length check")
    args = parser.parse_args()
    problems = check(ET.parse(args.input).getroot(), args.durations)
    for line in problems[:50]:
        print(line)
    print(f"{len(problems)} problem(s)", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
