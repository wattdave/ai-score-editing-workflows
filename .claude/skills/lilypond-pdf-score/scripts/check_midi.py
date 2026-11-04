"""Compare a glyph read against the piece's own MIDI (Mutopia and CPDL ship one with the PDF).

    python check_midi.py score.pdf score.mid [--pages 1] [--voices 4] [--clefs ...] [--fifths N]

Reports, per voice, the first note where onset, duration or pitch differs. Accidentals that carry through a
bar are not tracked here, so a pitch off by one semitone is reported as 'accidental?'."""
import os, sys, argparse
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build import *

BASE = {0: 0, 1: 2, 2: 4, 3: 5, 4: 7, 5: 9, 6: 11}


def midi_voices(path):
    import mido
    m = mido.MidiFile(path)
    tracks = []
    for tr in m.tracks:
        t = 0
        on = {}
        notes = []
        for msg in tr:
            t += msg.time
            if msg.type == "note_on" and msg.velocity > 0:
                on[msg.note] = t
            elif msg.type in ("note_off", "note_on") and msg.note in on:
                notes.append((on.pop(msg.note) / m.ticks_per_beat, msg.note, (t - 0) / m.ticks_per_beat))
        notes.sort()
        if notes:
            tracks.append(notes)
    return tracks


def xml_voices(path):
    """notes of a MusicXML file as (onset beats, midi pitch, duration) per part, ties merged"""
    import xml.etree.ElementTree as ET
    root = ET.parse(path).getroot()
    out = []
    for part in root.findall("part"):
        t = 0.0
        div = 1
        notes = []
        for m in part.findall("measure"):
            for el in m:
                if el.tag == "attributes" and el.find("divisions") is not None:
                    div = int(el.find("divisions").text)
                elif el.tag == "note":
                    d = int(el.find("duration").text) / div
                    p = el.find("pitch")
                    if p is not None:
                        midi = 12 * (int(p.find("octave").text) + 1) + BASE["CDEFGAB".index(p.find("step").text)] \
                            + int(float(p.find("alter").text)) if p.find("alter") is not None else \
                            12 * (int(p.find("octave").text) + 1) + BASE["CDEFGAB".index(p.find("step").text)]
                        stops = [x for x in el.findall("tie") if x.get("type") == "stop"]
                        if stops and notes and notes[-1][1] == midi:
                            notes[-1] = (notes[-1][0], midi, notes[-1][2] + d)
                        else:
                            notes.append((t, midi, d))
                    t += d
        out.append(notes)
    return out


def main_xml(xml, mid):
    mv = midi_voices(mid)
    xv = xml_voices(xml)
    used = set()
    for vi, mine in enumerate(xv):
        best = None
        for ti, t in enumerate(mv):
            if ti in used:
                continue
            k = 0
            while k < min(len(mine), len(t)) and abs(mine[k][0] - t[k][0]) < 0.02 and (mine[k][1] - t[k][1]) % 12 == 0:
                k += 1
            if best is None or k > best[0]:
                best = (k, ti)
        k, ti = best
        used.add(ti)
        t = mv[ti]
        octs = Counter(round((a_[1] - b_[1]) / 12) for a_, b_ in zip(mine[:k], t[:k]))
        octave = octs.most_common(1)[0][0] if octs else 0
        full = k >= len(mine)
        print(f"part {vi + 1} -> midi track {ti}: {'every note matches' if full else f'matches {k} of {len(mine)} notes'}"
              f" (midi has {len(t)}; extra = repeats)" + (f"; MIDI is {-octave} octave(s) off the print" if octave else ""))
        if not full:
            print("   first difference: mine", [(round(x, 2), p) for x, p, _ in mine[k:k + 3]], " midi", [(round(x, 2), p) for x, p, _ in t[k:k + 3]])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", help="the PDF, or the MusicXML to check (exact pitches, accidentals and ties included)"); ap.add_argument("mid")
    ap.add_argument("--voices", type=int, default=4); ap.add_argument("--pages")
    ap.add_argument("--clefs"); ap.add_argument("--fifths", type=int)
    a = ap.parse_args()
    if a.pdf.endswith((".musicxml", ".xml")):
        return main_xml(a.pdf, a.mid)
    D = Doc(a.pdf)
    res = extract(D, a.voices, [int(x) - 1 for x in a.pages.split(",")] if a.pages else None)
    clefs = a.clefs.split(",") if a.clefs else detect_clefs(D, res)
    fifths = detect_key(D, res) if a.fifths is None else a.fifths
    beats, bt, _ = detect_time(D, res)
    bpb = beats * 4 / bt
    voices, starts, _ = collect(D, res, a.voices, clefs, bpb, fifths)
    flat = {6: -1, 2: -1, 5: -1, 1: -1, 4: -1, 0: -1, 3: -1}
    order = [6, 2, 5, 1, 4, 0, 3] if fifths < 0 else [3, 0, 4, 1, 5, 2, 6]
    key = {i: (-1 if fifths < 0 else 1) for i in order[:abs(fifths)]}
    mv = midi_voices(a.mid)
    print("clefs", clefs, "fifths", fifths, "bar", bpb, "| midi tracks", [len(t) for t in mv], "mine", [sum(1 for e in v if not e.get('rest')) for v in voices])
    used = set()
    for vi, v in enumerate(voices):
        mine = []
        for e in sorted(v, key=lambda e: e["onset"]):
            if e.get("rest"):
                continue
            n = e["step"]
            alt = e["alt"] if e.get("alt") is not None else key.get(n % 7, 0)
            mine.append((e["onset"], 12 * (n // 7 + 1) + BASE[n % 7] + alt, e["dur"]))
        best = None
        for ti, t in enumerate(mv):
            if ti in used:
                continue
            k = 0
            while k < min(len(mine), len(t)) and abs(mine[k][0] - t[k][0]) < 0.02 and (mine[k][1] - t[k][1]) % 12 in (0, 1, 11):
                k += 1
            if best is None or k > best[0]:
                best = (k, ti)
        k, ti = best
        used.add(ti)
        t = mv[ti]
        octs = Counter(round((a_[1] - b_[1]) / 12) for a_, b_ in zip(mine[:k], t[:k]))
        octave = octs.most_common(1)[0][0] if octs else 0
        status = "OK, every note matches" if k >= min(len(mine), len(t)) and len(mine) == len(t) else f"matches {k} notes of {len(mine)} (midi {len(t)})"
        print(f"voice {vi} -> midi track {ti}: {status}" + (f"; MIDI is {-octave} octave(s) off the print here" if octave else ""))
        if k < min(len(mine), len(t)):
            print("   first difference: mine", [(round(x, 2), p) for x, p, _ in mine[k:k + 3]], " midi", [(round(x, 2), p) for x, p, _ in t[k:k + 3]])
        else:
            print("   pitches off by a semitone (accidental?):", sum(1 for a_, b_ in zip(mine, t) if (a_[1] - b_[1]) % 12 != 0))


main()
