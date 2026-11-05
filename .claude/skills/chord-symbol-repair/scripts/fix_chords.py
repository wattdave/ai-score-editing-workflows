#!/usr/bin/env python3
"""Repair chord symbols that OMR stored as plain direction text in MusicXML.

Standard library only, so the skill runs without the rest of this repository.

Usage:
    fix_chords.py IN OUT [--mode harmony|capitalize] [--report]

IN may be .xml, .musicxml or .mxl; OUT is always plain MusicXML.

Modes:
    harmony      (default) replace each recognised chord word by a real
                 <harmony> element at the same place in the measure.
    capitalize   only upper-case roots and slash basses in the words text
                 (c7 -> C7, bbmaj7 -> Bbmaj7, c/e -> C/E); keep it as text.

A words element counts as a chord only when its whole trimmed text parses as
a chord and it is the only content of a <direction> (one direction-type, no
<sound>).  A bare letter (a, F, e) or the English word "am" is ambiguous, so
it is converted only when the score also holds at least MIN_STRONG
unambiguous chords (Gm, c7, F#, C/E, ...) or <harmony> elements.
"""

from __future__ import annotations

import argparse
import re
import sys
import zipfile
from copy import deepcopy
from pathlib import Path
from xml.etree import ElementTree as ET

MIN_STRONG = 3

# suffix as written (after OCR digit repair) -> (kind, degrees); degrees are (value, alter, type)
KINDS: dict[str, tuple[str, tuple[tuple[int, int, str], ...]]] = {
    "": ("major", ()), "M": ("major", ()), "maj": ("major", ()),
    "m": ("minor", ()), "min": ("minor", ()), "-": ("minor", ()),
    "7": ("dominant", ()),
    "maj7": ("major-seventh", ()), "M7": ("major-seventh", ()), "ma7": ("major-seventh", ()),
    "Δ": ("major-seventh", ()), "Δ7": ("major-seventh", ()),
    "m7": ("minor-seventh", ()), "min7": ("minor-seventh", ()), "-7": ("minor-seventh", ()),
    "dim": ("diminished", ()), "o": ("diminished", ()), "°": ("diminished", ()),
    "dim7": ("diminished-seventh", ()), "o7": ("diminished-seventh", ()), "°7": ("diminished-seventh", ()),
    "ø": ("half-diminished", ()), "ø7": ("half-diminished", ()), "m7b5": ("half-diminished", ()),
    "aug": ("augmented", ()), "+": ("augmented", ()),
    "aug7": ("augmented-seventh", ()), "+7": ("augmented-seventh", ()),
    "sus": ("suspended-fourth", ()), "sus4": ("suspended-fourth", ()), "sus2": ("suspended-second", ()),
    "6": ("major-sixth", ()), "maj6": ("major-sixth", ()),
    "m6": ("minor-sixth", ()), "min6": ("minor-sixth", ()),
    "9": ("dominant-ninth", ()), "maj9": ("major-ninth", ()), "m9": ("minor-ninth", ()),
    "11": ("dominant-11th", ()), "13": ("dominant-13th", ()),
    "5": ("power", ()),
    "add9": ("major", ((9, 0, "add"),)), "madd9": ("minor", ((9, 0, "add"),)),
}

ROOT_RE = re.compile(r"^([A-Ga-g])([#b♯♭]?)(.*?)(?:/([A-Ga-g])([#b♯♭]?))?$")
# Looks like an attempted chord (used only to list what could not be parsed).
LOOSE_RE = re.compile(r"^[A-Ga-g][#b♯♭]?(\d|/|\(|°|ø|Δ|\+|-|[mM](?![A-Za-z])|(maj|min|dim|aug|sus|add)[A-Za-z]*\d*)\S*$")
ENGLISH = {"am"}


class Chord:
    def __init__(self, root: str, root_acc: str, suffix: str, bass: str, bass_acc: str, kind: str, degrees: tuple) -> None:
        self.root, self.root_acc, self.suffix = root, root_acc, suffix
        self.bass, self.bass_acc, self.kind, self.degrees = bass, bass_acc, kind, degrees

    @property
    def weak(self) -> bool:
        """Ambiguous: a bare letter, or an English word that parses as a chord."""
        text = self.root + self.root_acc + self.suffix
        return (not self.root_acc and not self.suffix and not self.bass) or text in ENGLISH

    def name(self) -> str:
        out = self.root.upper() + self.root_acc + self.suffix
        return out + (f"/{self.bass.upper()}{self.bass_acc}" if self.bass else "")


def _alter(acc: str) -> int:
    return {"#": 1, "♯": 1, "b": -1, "♭": -1}.get(acc, 0)


def _repair_suffix(suffix: str) -> str:
    """Fix common OMR misreads inside a chord suffix: l/I/| for 1, 0/O for o."""
    if re.fullmatch(r"[lI|]+", suffix):
        suffix = "1" * len(suffix)
    suffix = re.sub(r"(?<=\d)[lI|]|[lI|](?=\d)", "1", suffix)
    if suffix[:1] in ("0", "O"):
        suffix = "o" + suffix[1:]
    return suffix


def parse_chord(text: str) -> Chord | None:
    """Parse the whole of `text` as a chord, or return None."""
    text = text.strip()
    if not text or " " in text:
        return None
    m = ROOT_RE.match(text)
    if not m:
        return None
    root, acc, suffix, bass, bass_acc = m.group(1), m.group(2), m.group(3), m.group(4) or "", m.group(5) or ""
    suffix = _repair_suffix(suffix)
    entry = KINDS.get(suffix) or (KINDS.get(suffix.lower()) if len(suffix) > 1 else None)
    if entry is None:
        return None
    return Chord(root, acc, suffix, bass, bass_acc, entry[0], entry[1])


def chord_direction(d: ET.Element) -> tuple[ET.Element, Chord] | None:
    """(words element, parsed chord) when direction `d` holds only a chord word."""
    types = d.findall("direction-type")
    if len(types) != 1 or d.find("sound") is not None:
        return None
    kids = list(types[0])
    if len(kids) != 1 or kids[0].tag != "words":
        return None
    chord = parse_chord(kids[0].text or "")
    return (kids[0], chord) if chord else None


def _directions(root: ET.Element):
    for parent in root.iter():
        for child in list(parent):
            if child.tag == "direction":
                yield parent, child


def build_harmony(d: ET.Element, words: ET.Element, chord: Chord) -> ET.Element:
    h = ET.Element("harmony")
    if d.get("placement"):
        h.set("placement", d.get("placement"))
    for attr in ("default-x", "default-y", "relative-x", "relative-y"):
        if words.get(attr) is not None:
            h.set(attr, words.get(attr))
    root = ET.SubElement(h, "root")
    ET.SubElement(root, "root-step").text = chord.root.upper()
    if chord.root_acc:
        ET.SubElement(root, "root-alter").text = str(_alter(chord.root_acc))
    ET.SubElement(h, "kind", {"text": chord.suffix}).text = chord.kind
    if chord.bass:
        bass = ET.SubElement(h, "bass")
        ET.SubElement(bass, "bass-step").text = chord.bass.upper()
        if chord.bass_acc:
            ET.SubElement(bass, "bass-alter").text = str(_alter(chord.bass_acc))
    for value, alter, typ in chord.degrees:
        deg = ET.SubElement(h, "degree")
        ET.SubElement(deg, "degree-value").text = str(value)
        ET.SubElement(deg, "degree-alter").text = str(alter)
        ET.SubElement(deg, "degree-type").text = typ
    for tag in ("offset", "staff"):
        el = d.find(tag)
        if el is not None:
            h.append(deepcopy(el))
    return h


def _indent_level(parent: ET.Element, index: int) -> int:
    ws = (parent.text if index == 0 else list(parent)[index - 1].tail) or ""
    return len(ws.rsplit("\n", 1)[-1]) // 2 if "\n" in ws else 0


def repair(root: ET.Element, mode: str = "harmony") -> dict:
    """Edit `root` in place; return a report of what changed and what did not."""
    found = [(p, d, *cd) for p, d in _directions(root) if (cd := chord_direction(d))]
    strong = sum(1 for *_, c in found if not c.weak) + len(root.findall(".//harmony"))
    allow_weak = strong >= MIN_STRONG
    rep = {"converted": [], "ambiguous": [], "unrecognised": [], "allow_weak": allow_weak, "strong": strong}
    for parent, d, words, chord in found:
        if chord.weak and not allow_weak:
            rep["ambiguous"].append((words.text or "").strip())
            continue
        old = (words.text or "").strip()
        if mode == "capitalize":
            if old != chord.name():
                words.text = (words.text or "").replace(old, chord.name())
                rep["converted"].append(f"{old} -> {chord.name()}")
            continue
        index = list(parent).index(d)
        h = build_harmony(d, words, chord)
        ET.indent(h, space="  ", level=_indent_level(parent, index))
        h.tail = d.tail
        parent[index] = h
        rep["converted"].append(f"{old} -> {chord.name()}")
    done = {id(w) for _, _, w, _ in found}
    for _, d in _directions(root):
        for w in d.iter("words"):
            t = (w.text or "").strip()
            if t and LOOSE_RE.match(t) and parse_chord(t) is None and id(w) not in done:
                rep["unrecognised"].append(t)
    return rep


def read_input(path: Path) -> tuple[ET.Element, str]:
    """Return (root, header text before the root element)."""
    data = path.read_bytes()
    if path.suffix.lower() == ".mxl":
        with zipfile.ZipFile(path) as z:
            name = next(n for n in z.namelist() if n.endswith((".xml", ".musicxml")) and not n.startswith("META-INF"))
            data = z.read(name)
    text = data.decode("utf-8", errors="replace")
    m = re.search(r"<score-(partwise|timewise)\b", text)
    header = text[: m.start()] if m else ""
    header = re.sub(r"(encoding\s*=\s*)(['\"])(?!utf-8\2)[^'\"]*\2", r"\1\2utf-8\2", header, count=1, flags=re.I)
    parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True, insert_pis=True))
    return ET.fromstring(data, parser=parser), header


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("input")
    ap.add_argument("output")
    ap.add_argument("--mode", choices=("harmony", "capitalize"), default="harmony")
    ap.add_argument("--report", action="store_true", help="list every change and every word left alone")
    args = ap.parse_args(argv)
    try:
        root, header = read_input(Path(args.input).expanduser())
    except (OSError, ET.ParseError, zipfile.BadZipFile, StopIteration) as exc:
        print(f"cannot read {args.input}: {exc}", file=sys.stderr)
        return 2
    rep = repair(root, args.mode)
    body = ET.tostring(root, encoding="unicode")
    Path(args.output).expanduser().write_text(header + body + "\n", encoding="utf-8")
    print(f"{args.mode}: {len(rep['converted'])} changed, {len(rep['ambiguous'])} ambiguous left, {len(rep['unrecognised'])} unrecognised left -> {args.output}")
    if args.report:
        for line in rep["converted"]:
            print(f"  changed      {line}")
        for t in rep["ambiguous"]:
            print(f"  ambiguous    {t!r} (bare letter; only {rep['strong']} unambiguous chords in score, need {MIN_STRONG})")
        for t in rep["unrecognised"]:
            print(f"  unrecognised {t!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
