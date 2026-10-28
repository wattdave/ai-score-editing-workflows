"""Compare two MusicXML files (.musicxml, .xml or .mxl) part by part.

Prints bar, note and lyric counts per part, then the first pitch/duration
differences and a lyric diff (words dropped, added or changed).

    python -I compare_musicxml.py original.musicxml converted.musicxml
"""
import difflib
import sys
import zipfile
import xml.etree.ElementTree as ET


def load(path):
    if path.endswith(".mxl"):
        z = zipfile.ZipFile(path)
        name = next(n for n in z.namelist() if n.endswith(".xml") and not n.startswith("META"))
        root = ET.fromstring(z.read(name))
    else:
        root = ET.parse(path).getroot()
    divisions = int(root.find("part/measure/attributes/divisions").text)
    parts = []
    for p in root.findall("part"):
        notes, lyrics, bars = [], [], 0
        for m in p.findall("measure"):
            bars += 1
            for n in m.findall("note"):
                dur = int(n.findtext("duration") or 0) / divisions
                pitch = n.find("pitch")
                if pitch is None:
                    notes.append(("R", dur))
                else:
                    step = pitch.findtext("step") + (pitch.findtext("alter") or "")
                    notes.append((step + pitch.findtext("octave"), dur))
                lyrics += [l.findtext("text") or "" for l in n.findall("lyric")]
        parts.append((bars, notes, lyrics))
    return parts


def main(a_path, b_path):
    a, b = load(a_path), load(b_path)
    print(f"parts: {len(a)} vs {len(b)}")
    for i, ((ba, na, la), (bb, nb, lb)) in enumerate(zip(a, b), 1):
        diffs = [(k, x, y) for k, (x, y) in enumerate(zip(na, nb)) if x != y]
        print(f"part {i}: bars {ba} vs {bb}; notes {len(na)} vs {len(nb)}; "
              f"note diffs {len(diffs)} {diffs[:4]}; lyrics {len(la)} vs {len(lb)}")
        for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, la, lb).get_opcodes():
            if op != "equal":
                print(f"   lyric {op}: {la[i1:i2]} -> {lb[j1:j2]} after {la[max(0, i1 - 3):i1]}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
