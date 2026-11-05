#!/usr/bin/env python3
"""Repair beams in a MusicXML file (typically OMR output) before import.

Standard library only. Only <beam> elements change: pitches, durations, stems,
ties and lyrics are never touched.

Usage:
    fix_beams.py IN.xml OUT.xml [--scope mixed|all] [--style meter|syllabic] [--strip]

--scope mixed   (default) re-beam only beat groups that are partly beamed
--scope all     re-beam every beat group
--style meter   (default) beam each beat group as one run, rests break it
--style syllabic  break the beam wherever the next note starts a new syllable
                  (notes without their own lyric are a melisma and stay joined);
                  voices without lyrics fall back to meter
--strip         remove every beam instead; Sibelius, Dorico and MuseScore then
                beam by meter on import

Beat groups: a quarter note in simple time, three eighths in 6/8, 9/8, 12/8.
Reads .xml/.musicxml/.mxl; writes plain MusicXML.
"""

from __future__ import annotations

import argparse
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

LEVEL = {"eighth": 1, "16th": 2, "32nd": 3, "64th": 4, "128th": 5}
AFTER_BEAM = ("notations", "lyric", "play", "listen", "footnote", "level")


class Note:
    """One beamable note, with the chord notes that sound with it."""

    def __init__(self, el: ET.Element, onset: int, dur: int):
        self.el, self.chord, self.onset, self.dur = el, [], onset, dur
        self.level = LEVEL[el.findtext("type")]
        self.dotted = el.find("dot") is not None
        lyric = el.find("lyric")
        self.has_lyric = lyric is not None
        self.old = {b.get("number", "1"): b.text for b in el.findall("beam")}


def read_text(path: Path) -> str:
    if path.suffix.lower() == ".mxl":
        with zipfile.ZipFile(path) as z:
            name = next(n for n in z.namelist() if n.endswith((".xml", ".musicxml")) and not n.startswith("META-INF"))
            return z.read(name).decode("utf-8")
    return path.read_text(encoding="utf-8")


def beat_length(divisions: int, beats: int, beat_type: int) -> int:
    if beat_type == 8 and beats % 3 == 0 and beats >= 6:
        return divisions * 3 // 2
    return max(1, divisions * 4 // beat_type)


def collect(measure: ET.Element, divisions: int, beats: int, beat_type: int):
    """Return ({(staff, voice): [Note]}, divisions, beats, beat_type) for one measure."""
    cursor, last = 0, 0
    voices: dict[tuple[str, str], list] = {}
    last_note: Note | None = None
    for el in measure:
        if el.tag == "attributes":
            if el.findtext("divisions"):
                divisions = int(el.findtext("divisions"))
            t = el.find("time")
            if t is not None and (t.findtext("beats") or "").isdigit():
                beats, beat_type = int(t.findtext("beats")), int(t.findtext("beat-type"))
        elif el.tag == "backup":
            cursor -= int(el.findtext("duration") or 0)
        elif el.tag == "forward":
            cursor += int(el.findtext("duration") or 0)
        elif el.tag == "note":
            chord = el.find("chord") is not None
            onset = last if chord else cursor
            dur = int(el.findtext("duration") or 0)
            key = (el.findtext("staff") or "1", el.findtext("voice") or "1")
            if not chord:
                last = onset
                if el.find("grace") is None:
                    cursor += dur
            seq = voices.setdefault(key, [])
            if chord:
                if last_note is not None and last_note.el is not None and seq and seq[-1] is last_note:
                    last_note.chord.append(el)
                continue
            if el.find("rest") is not None or el.find("grace") is not None or el.findtext("type") not in LEVEL:
                seq.append(None)  # a rest or unbeamable note breaks runs
                last_note = None
                continue
            last_note = Note(el, onset, dur)
            seq.append(last_note)
    return voices, divisions, beats, beat_type


def runs_in_voice(seq: list, bl: int):
    """Yield beat-group runs: consecutive Notes (no rests between) sharing one beat."""
    run: list[Note] = []
    for item in seq + [None]:
        if item is not None and run and item.onset // bl == run[0].onset // bl:
            run.append(item)
            continue
        if run:
            yield run
        run = [item] if item is not None else []


def split_syllabic(run: list[Note], voice_has_lyrics: bool) -> list[list[Note]]:
    if not voice_has_lyrics:
        return [run]
    out, cur = [], [run[0]]
    for n in run[1:]:
        if n.has_lyric:  # new syllable starts here
            out.append(cur)
            cur = [n]
        else:
            cur.append(n)
    out.append(cur)
    return out


def beam_values(run: list[Note]) -> list[dict[str, str]]:
    """Beam number -> value for each note of one beamed run (len >= 2)."""
    result: list[dict[str, str]] = [{} for _ in run]
    top = max(n.level for n in run)
    for lvl in range(1, top + 1):
        for i, n in enumerate(run):
            if n.level < lvl:
                continue
            prev = i > 0 and run[i - 1].level >= lvl
            nxt = i < len(run) - 1 and run[i + 1].level >= lvl
            if prev and nxt:
                v = "continue"
            elif nxt:
                v = "begin"
            elif prev:
                v = "end"
            else:  # a lone short note: hook toward its beat-mate
                back = i == len(run) - 1 or (i > 0 and run[i - 1].dotted)
                v = "backward hook" if back else "forward hook"
            result[i][str(lvl)] = v
    return result


def set_beams(el: ET.Element, values: dict[str, str]) -> None:
    for b in el.findall("beam"):
        el.remove(b)
    pos = len(el)
    for i, child in enumerate(el):
        if child.tag in AFTER_BEAM:
            pos = i
            break
    for k in sorted(values, key=int):
        b = ET.Element("beam", number=k)
        b.text = values[k]
        el.insert(pos, b)
        pos += 1


def joined(run: list[Note]) -> list[bool]:
    return [a.old.get("1") in ("begin", "continue") and b.old.get("1") in ("continue", "end") for a, b in zip(run, run[1:])]


def process(root: ET.Element, scope: str, style: str, strip: bool) -> dict:
    stats = {"groups_fixed": 0, "beams_removed": 0, "notes_touched": 0}
    for part in root.findall("part"):
        divisions, beats, beat_type = 1, 4, 4
        for m in part.findall("measure"):
            voices, divisions, beats, beat_type = collect(m, divisions, beats, beat_type)
            bl = beat_length(divisions, beats, beat_type)
            for seq in voices.values():
                has_lyrics = any(n is not None and n.has_lyric for n in seq)
                if strip:
                    for n in (x for x in seq if x is not None):
                        for el in [n.el, *n.chord]:
                            for b in el.findall("beam"):
                                el.remove(b)
                                stats["beams_removed"] += 1
                    continue
                for run in runs_in_voice(seq, bl):
                    if len(run) < 2:
                        continue
                    j = joined(run)
                    if scope == "mixed" and (all(j) or not any(j)):
                        # complete or entirely unbeamed groups are left alone
                        if not (style == "syllabic" and all(j)):
                            continue
                    pieces = split_syllabic(run, has_lyrics) if style == "syllabic" else [run]
                    for piece in pieces:
                        if len(piece) < 2:
                            for n in piece:
                                for el in [n.el, *n.chord]:
                                    set_beams(el, {})
                            continue
                        for n, vals in zip(piece, beam_values(piece)):
                            for el in [n.el, *n.chord]:
                                set_beams(el, vals)
                            stats["notes_touched"] += 1
                    stats["groups_fixed"] += 1
    return stats


def header_of(text: str) -> str:
    """Everything before the root element (XML declaration and DOCTYPE), so it survives."""
    m = re.search(r"<score-(partwise|timewise)\b", text)
    return text[: m.start()] if m else ""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input")
    ap.add_argument("output")
    ap.add_argument("--scope", choices=("mixed", "all"), default="mixed")
    ap.add_argument("--style", choices=("meter", "syllabic"), default="meter")
    ap.add_argument("--strip", action="store_true")
    args = ap.parse_args(argv)
    try:
        text = read_text(Path(args.input))
        root = ET.fromstring(text)
    except Exception as exc:
        print(f"error: cannot read {args.input}: {exc}", file=sys.stderr)
        return 2
    if root.tag != "score-partwise":
        print("error: only score-partwise MusicXML is supported", file=sys.stderr)
        return 2
    stats = process(root, args.scope, args.style, args.strip)
    ET.indent(root, space="  ")
    body = ET.tostring(root, encoding="unicode")
    header = header_of(text) or '<?xml version="1.0" encoding="UTF-8"?>\n'
    Path(args.output).write_text(header + body + "\n", encoding="utf-8")
    print(f"wrote {args.output}: {stats}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
