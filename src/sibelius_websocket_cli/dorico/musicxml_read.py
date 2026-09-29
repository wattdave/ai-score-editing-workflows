"""Read a Dorico MusicXML export into the Lua bridge's event shape.

Dorico's Lua cannot read voice streams that hold lyrics (docs/dorico.md),
so for those staves the back end reads an exported full score instead.
Staves are numbered in part order, then by <staff> within a part: the same
order as Dorico's stave streams. Voices are numbered per staff in the order
MusicXML voice numbers first appear there. Events carry no Dorico id.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from fractions import Fraction
from pathlib import Path
from typing import Any

from .bridge import UNITS, BarMap

STEPS = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
ACCIDENTALS = {-2: "bb", -1: "b", 0: "", 1: "#", 2: "x"}
FIFTHS_MAJOR = ["Cb", "Gb", "Db", "Ab", "Eb", "Bb", "F", "C", "G", "D", "A", "E", "B", "F#", "C#"]


def _units(value: Fraction) -> int:
    return round(value * UNITS)


def read(path: str | Path) -> dict[str, Any]:
    """{"staves", "events", "bars", "timeSignatures", "keySignatures"} from a score."""
    root = ET.parse(path).getroot()
    names = {p.get("id"): (p.findtext("part-name") or "").strip() for p in root.iter("score-part")}
    events: list[dict[str, Any]] = []
    staves: list[dict[str, Any]] = []
    bar_lengths: list[int] = []
    times: list[dict[str, Any]] = []
    keys: list[dict[str, Any]] = []
    first_staff = 1
    for part_index, part in enumerate(root.iter("part")):
        divisions = 1
        staff_count = 1
        voices: dict[int, dict[int, int]] = {}
        flow = Fraction(0)
        beats = (4, 4)
        for bar_index, measure in enumerate(part.findall("measure"), start=1):
            cursor = Fraction(0)
            longest = Fraction(0)
            last_start = Fraction(0)
            for child in measure:
                if child.tag == "attributes":
                    divisions = int(child.findtext("divisions") or divisions)
                    staff_count = int(child.findtext("staves") or staff_count)
                    if (time := child.find("time")) is not None and time.findtext("beats"):
                        beats = (int(time.findtext("beats")), int(time.findtext("beat-type")))
                        if part_index == 0:
                            times.append({"bar": bar_index, "numerator": beats[0], "denominator": beats[1]})
                    if (key := child.find("key")) is not None and key.findtext("fifths") is not None and part_index == 0:
                        fifths = int(key.findtext("fifths"))
                        minor = key.findtext("mode") == "minor"
                        name = FIFTHS_MAJOR[fifths + 7] if -7 <= fifths <= 7 else str(fifths)
                        keys.append({"bar": bar_index, "fifths": fifths, "key": name, "minor": minor})
                elif child.tag == "backup":
                    cursor -= Fraction(int(child.findtext("duration") or 0), divisions)
                elif child.tag == "forward":
                    cursor += Fraction(int(child.findtext("duration") or 0), divisions)
                elif child.tag == "note":
                    duration = Fraction(int(child.findtext("duration") or 0), divisions)
                    chord = child.find("chord") is not None
                    start = last_start if chord else cursor
                    staff_in_part = int(child.findtext("staff") or 1)
                    voice_xml = int(child.findtext("voice") or 1)
                    order = voices.setdefault(staff_in_part, {})
                    voice = order.setdefault(voice_xml, len(order) + 1)
                    event: dict[str, Any] = {
                        "staff": first_staff + staff_in_part - 1,
                        "voice": voice,
                        "bar": bar_index,
                        "position": _units(start),
                        "flowPosition": _units(flow + start),
                        "duration": _units(duration),
                    }
                    if child.find("grace") is not None:
                        event["duration"] = 0
                    if child.find("rest") is not None:
                        event["type"] = "BarRestEvent" if child.find("rest").get("measure") == "yes" else "RestEvent"
                    elif (pitch := child.find("pitch")) is not None:
                        step = pitch.findtext("step")
                        alter = int(round(float(pitch.findtext("alter") or 0)))
                        octave = int(pitch.findtext("octave"))
                        event["type"] = "GraceNoteEvent" if child.find("grace") is not None else "NoteEvent"
                        event["pitch"] = 12 * (octave + 1) + STEPS[step] + alter
                        event["name"] = f"{step}{ACCIDENTALS.get(alter, '?')}{octave}"
                        lyrics = [
                            {"verse": int(l.get("number") or 1), "text": l.findtext("text") or "",
                             "syllabic": l.findtext("syllabic") or "single"}
                            for l in child.findall("lyric")
                        ]
                        if lyrics:
                            event["lyrics"] = lyrics
                        if any(t.get("type") == "start" for t in child.findall("tie")):
                            event["tiedForward"] = True
                    else:
                        continue
                    events.append(event)
                    if not chord:
                        last_start = cursor
                        if child.find("grace") is None:
                            cursor += duration
                    longest = max(longest, cursor)
            # A measure is as long as its music: pick-ups and the parts of a
            # bar split by a barline are short, and exporters do not always
            # mark them implicit (Dorico marks only the later part of a split
            # bar; Sibelius marks neither). An empty measure takes the meter.
            natural = Fraction(4 * beats[0], beats[1])
            length = longest if longest > 0 else natural
            if part_index == 0:
                bar_lengths.append(_units(length))
            flow += length
        for staff_in_part in range(1, staff_count + 1):
            staves.append({"staff": first_staff + staff_in_part - 1, "name": names.get(part.get("id"), ""), "part": part.get("id")})
        first_staff += staff_count
    divisions_map: list[tuple[int, int]] = []
    position = 0
    for length in bar_lengths:
        if not divisions_map or divisions_map[-1][1] != length or _bar_breaks_segment(divisions_map, position, length):
            divisions_map.append((position, length))
        position += length
    events.sort(key=lambda e: (e["staff"], e["bar"], e["position"], e["voice"], e.get("pitch") or 0))
    counters: dict[tuple[int, int], int] = {}
    for event in events:
        key_ = (event["staff"], event["bar"])
        event["index"] = counters.get(key_, 0)
        counters[key_] = event["index"] + 1
    return {
        "staves": staves,
        "events": events,
        "bars": BarMap(divisions_map),
        "barCount": len(bar_lengths),
        "timeSignatures": times,
        "keySignatures": keys,
    }


def _bar_breaks_segment(divisions: list[tuple[int, int]], position: int, length: int) -> bool:
    """True if a bar of `length` at `position` does not continue the last segment evenly."""
    start, seg_length = divisions[-1]
    return (position - start) % seg_length != 0
