#!/usr/bin/env python3
"""Make a playback copy of a MusicXML score with exactly one sounding note per staff.

Some playback setups (solo vocal samples, one MIDI channel per singer) sound only
one note per staff, so chords and divisi are lost. This script rewrites the score
so every chord note sits on its own staff, using these rules:

1. ``--unison-until N``: bars 1..N of every other part copy the melody part.
2. Resting voices double the melody (disable with ``--no-double-rests``): a rest
   in another part is replaced by the melody's notes when the melody's note
   boundaries line up with the rest exactly.
3. Melody chords are shared among the voices singing melody material at that
   moment: top note to the melody part, bottom note to the lowest such part,
   middle notes to the parts in between. With fewer notes than voices, the
   leftover voices sing the top (melody) note.
4. Chords in any other part: the part keeps the note nearest its previous note.
   Each extra note is dropped if another part already sounds that pitch;
   otherwise it replaces the note of the adjacent part nearest in pitch that
   starts at the same moment with the same duration, preferring non-melody
   parts. The melody part is a last resort, and qualifies only when the note it
   would lose sounds (in any octave) in another part. If no part qualifies, the
   extra note is dropped.

Every judgement from rules 3 and 4 is printed as a decision log so the user can
review it. Unhandled cases are reported, never guessed silently.
"""

from __future__ import annotations

import argparse
import copy
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

# The skill remains runnable with plain ``python3`` from a source checkout.
SOURCE_ROOT = Path(__file__).resolve().parents[4] / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from ai_score_editing.workflows.musicxml_split.routing import midi  # noqa: E402


@dataclass
class Event:
    onset: int
    duration: int
    notes: list[ET.Element]
    from_melody: bool = False
    rest: bool = field(init=False)

    def __post_init__(self) -> None:
        self.rest = self.notes[0].find("rest") is not None


def name(note: ET.Element) -> str:
    pitch = note.find("pitch")
    alter = round(float(pitch.findtext("alter") or 0))
    return pitch.findtext("step") + {1: "#", -1: "b", 0: ""}.get(alter, "?") + pitch.findtext("octave")


def events(measure: ET.Element) -> list[Event]:
    out: list[Event] = []
    onset = 0
    for element in measure:
        if element.tag == "backup" or element.tag == "forward":
            raise SystemExit(f"bar {measure.get('number')}: multiple voices per staff are not supported")
        if element.tag != "note":
            continue
        if element.find("chord") is not None:
            out[-1].notes.append(element)
            continue
        duration = int(element.findtext("duration") or 0)
        out.append(Event(onset, duration, [element]))
        onset += duration
    return out


def set_pitch(target: ET.Element, source: ET.Element) -> None:
    new = copy.deepcopy(source.find("pitch"))
    old = target.find("pitch")
    target.insert(list(target).index(old), new)
    target.remove(old)


def write_events(measure: ET.Element, evs: list[Event]) -> None:
    """Replace the measure's notes with one note per event, preserving other children."""
    notes = [e for e in measure if e.tag == "note"]
    first = list(measure).index(notes[0]) if notes else len(measure)
    for note in notes:
        measure.remove(note)
    for i, ev in enumerate(evs):
        measure.insert(first + i, ev.notes[0])


def fill_rests(part_evs: list[Event], melody_evs: list[Event]) -> list[Event]:
    """Replace rests whose span the melody's note boundaries tile exactly."""
    merged: list[Event] = []
    for ev in part_evs:
        if ev.rest and merged and merged[-1].rest:
            merged[-1].duration += ev.duration
        else:
            merged.append(Event(ev.onset, ev.duration, ev.notes, ev.from_melody))
    out: list[Event] = []
    for ev in merged:
        if not ev.rest:
            out.append(ev)
            continue
        end = ev.onset + ev.duration
        span = [m for m in melody_evs if ev.onset <= m.onset < end]
        tiles = (span and span[0].onset == ev.onset
                 and span[-1].onset + span[-1].duration == end
                 and all(a.onset + a.duration == b.onset for a, b in zip(span, span[1:])))
        if not tiles or all(m.rest for m in span):
            out.append(ev)
            continue
        for m in span:
            copies = [copy.deepcopy(n) for n in m.notes]
            for n in copies:
                if n.find("rest") is not None:
                    n.find("rest").attrib.pop("measure", None)
            out.append(Event(m.onset, m.duration, copies, from_melody=True))
    return out


def split(root: ET.Element, melody_id: str, unison_until: int, double_rests: bool) -> list[str]:
    parts = root.findall("part")
    ids = [p.get("id") for p in parts]
    if melody_id not in ids:
        raise SystemExit(f"melody part {melody_id} not found (parts: {', '.join(ids)})")
    order = {pid: i for i, pid in enumerate(ids)}
    measures = {p.get("id"): p.findall("measure") for p in parts}
    counts = {len(m) for m in measures.values()}
    if len(counts) != 1:
        raise SystemExit("parts have different bar counts")
    divisions = {d.text for d in root.iter("divisions")}
    if len(divisions) > 1:
        raise SystemExit(f"parts use different <divisions> ({', '.join(sorted(divisions))})")

    log: list[str] = []
    previous_pitch: dict[str, int | None] = {pid: None for pid in ids}
    for index in range(counts.pop()):
        bar = measures[melody_id][index].get("number")
        melody_evs = events(measures[melody_id][index])
        bar_evs: dict[str, list[Event]] = {}
        for pid in ids:
            if pid == melody_id:
                bar_evs[pid] = melody_evs
                continue
            evs = events(measures[pid][index])
            if index < unison_until:
                evs = [Event(m.onset, m.duration, [copy.deepcopy(n) for n in m.notes], True) for m in melody_evs]
            elif double_rests:
                evs = fill_rests(evs, melody_evs)
            bar_evs[pid] = evs

        # Rule 3: share melody chords among voices singing melody material.
        for m in melody_evs:
            if len(m.notes) < 2 or m.rest:
                continue
            singers = [melody_id] + [pid for pid in ids if pid != melody_id and any(
                e.from_melody and e.onset == m.onset for e in bar_evs[pid])]
            singers.sort(key=order.get)
            pitches = [copy.deepcopy(n) for n in sorted(m.notes, key=midi, reverse=True)]
            assignment: dict[str, ET.Element] = {}
            assignment[singers[0]] = pitches[0]
            if len(singers) > 1:
                assignment[singers[-1]] = pitches[-1] if len(pitches) > 1 else pitches[0]
            middle_pitches = pitches[1:-1]
            for i, pid in enumerate(singers[1:-1]):
                assignment[pid] = middle_pitches[i] if i < len(middle_pitches) else pitches[0]
            dropped = [p for p in pitches if all(p is not a for a in assignment.values())]
            for pid, pitch in assignment.items():
                ev = next(e for e in bar_evs[pid] if e.onset == m.onset)
                set_pitch(ev.notes[0], pitch)
                ev.notes[1:] = []
            log.append(f"bar {bar} @{m.onset}: melody chord {'/'.join(name(p) for p in pitches)} -> "
                       + ", ".join(f"{pid}={name(assignment[pid])}" for pid in singers)
                       + (f"; dropped {', '.join(name(p) for p in dropped)}" if dropped else ""))

        # Rule 4: chords on any other part's own line.
        for pid in ids:
            if pid == melody_id:
                continue
            previous = previous_pitch[pid]
            for ev in bar_evs[pid]:
                if ev.rest:
                    continue
                if len(ev.notes) < 2:
                    previous = midi(ev.notes[0])
                    continue
                pitches = [copy.deepcopy(n) for n in sorted(ev.notes, key=midi, reverse=True)]
                keep = min(pitches, key=lambda n: abs(midi(n) - previous)) if previous is not None else pitches[0]
                keep_pitch = keep
                extras = [n for n in pitches if n is not keep]
                set_pitch(ev.notes[0], keep_pitch)
                ev.notes[1:] = []
                previous = midi(keep_pitch)
                moves = []
                for extra in extras:
                    sounding = {other: next((e for e in bar_evs[other] if e.onset <= ev.onset < e.onset + e.duration
                                             and not e.rest), None) for other in ids if other != pid}
                    if any(e is not None and midi(e.notes[0]) == midi(extra) for e in sounding.values()):
                        moves.append(f"{name(extra)} already sounds, dropped")
                        continue
                    neighbours = [ids[order[pid] + d] for d in (-1, 1) if 0 <= order[pid] + d < len(ids)]
                    def doubled(other: str, e: Event) -> bool:
                        """The melody's note may be replaced only if its pitch class sounds elsewhere."""
                        pc = midi(e.notes[0]) % 12
                        return any(o is not None and midi(o.notes[0]) % 12 == pc
                                   for k, o in sounding.items() if k != other) or midi(keep_pitch) % 12 == pc
                    candidates = [(abs(midi(e.notes[0]) - midi(extra)), other, e) for other in neighbours
                                  if (e := sounding[other]) is not None
                                  and e.onset == ev.onset and e.duration == ev.duration
                                  and (other != melody_id or doubled(other, e))]
                    if not candidates:
                        moves.append(f"{name(extra)} dropped (no neighbour starts with it)")
                        continue
                    _, other, target = min(candidates, key=lambda c: (c[1] == melody_id, c[0]))
                    replaced = name(target.notes[0])
                    set_pitch(target.notes[0], extra)
                    moves.append(f"{name(extra)} -> {other} (replacing {replaced})")
                log.append(f"bar {bar} @{ev.onset}: {pid} chord {'/'.join(name(p) for p in pitches)} -> "
                           f"{pid} keeps {name(keep_pitch)}; " + "; ".join(moves))
            previous_pitch[pid] = previous

        for pid in ids:
            for ev in bar_evs[pid]:
                ev.notes[1:] = []
            write_events(measures[pid][index], bar_evs[pid])
    return log


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("input", help="MusicXML file (.xml/.musicxml, uncompressed)")
    parser.add_argument("-o", "--output", required=True)
    parser.add_argument("--melody", default="P1", help="part id carrying the melody (default: P1)")
    parser.add_argument("--unison-until", type=int, default=0, metavar="N",
                        help="every part copies the melody for bars 1..N (bar indexes, pickup = 1)")
    parser.add_argument("--no-double-rests", dest="double_rests", action="store_false",
                        help="leave rests in other parts as written")
    parser.add_argument("--title-suffix", default=" (playback)")
    args = parser.parse_args()

    tree = ET.parse(args.input)
    root = tree.getroot()
    log = split(root, args.melody, args.unison_until, args.double_rests)
    if root.findall(".//note/chord"):
        raise SystemExit("internal error: chords remain after splitting")
    title = root.find("work/work-title")
    if title is not None and args.title_suffix and not (title.text or "").endswith(args.title_suffix):
        title.text = (title.text or "") + args.title_suffix
    ET.indent(tree)
    tree.write(args.output, encoding="utf-8", xml_declaration=True)
    print("\n".join(log) if log else "no chords found")
    print(f"wrote {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
