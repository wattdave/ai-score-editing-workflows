"""Attach LilyPond \\lyricmode syllables to the notes of a MusicXML part.

python-ly drops lyrics, so they are added after rebar.py. Syllables go on
sounding notes in order, skipping tie continuations, rests, and notes inside
a slur after its first note (LilyPond's own melisma rule). In the lyrics,
"_" leaves a note without a syllable, "--" joins syllables into a word, and
"__" draws an extender.

usage: add_lyrics.py SOURCE.ly IN.xml OUT.xml PART=NOTES_VAR:LYRICS_VAR ...

SOURCE.ly is the LilyPond file the notes came from (used to find slurs), e.g.
P1=NotesS:LyricsS. The script refuses to write if a part's note count or
syllable count does not match, rather than guessing an alignment.
"""

from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

NOTE = re.compile(r"(?<![a-z])([a-gr])(?:is|es|s|f)*[',]*\d*\.*\s*(~)?\s*(\()?\s*(\))?")


def block(src: str, name: str) -> str:
    match = re.search(rf"(?m)^\s*{re.escape(name)}\s*=", src)
    if not match:
        raise SystemExit(f"variable {name} not found")
    start = src.index("{", match.end())
    depth = 0
    for end in range(start, len(src)):
        depth += {"{": 1, "}": -1}.get(src[end], 0)
        if depth == 0:
            return src[start + 1:end]
    raise SystemExit(f"unbalanced braces in {name}")


def slurred_notes(body: str) -> list[bool]:
    """For each sounding note in LilyPond source: True if it continues a slur."""
    body = re.sub(r"%.*", "", body)
    body = re.sub(r"\\incipitStart\b.*?\\incipitEnd\b", " ", body, flags=re.DOTALL)
    body = re.sub(r"\\set\s+[\w.]+\s*=\s*#?(\"[^\"]*\"|##?[tf])", " ", body)
    # Commands whose arguments look like note names must go with their arguments.
    body = re.sub(r"\\clef\s+(\"[^\"]*\"|\S+)", " ", body)
    body = re.sub(r"\\key\s+[a-g]\w*\s+\\\w+", " ", body)
    body = re.sub(r"\\(relative|transpose)\s+[a-g][a-z]*[',]*(\s+[a-g][a-z]*[',]*)?", " ", body)
    body = re.sub(r"\\time\s+\S+", " ", body)
    body = re.sub(r"\"[^\"]*\"", " ", body)
    body = re.sub(r"\\[a-zA-Z]+", " ", body)
    out: list[bool] = []
    in_slur = False
    for match in NOTE.finditer(body):
        if match.group(1) == "r":
            continue
        out.append(in_slur)
        if match.group(3):
            in_slur = True
        if match.group(4):
            in_slur = False
    return out


def syllables(lyrics: str) -> list[dict]:
    tokens = [t for t in re.split(r"\s+", re.sub(r"%.*", "", lyrics)) if t and not t.startswith("\\")]
    out: list[dict] = []
    for token in tokens:
        if token == "--" and out:
            out[-1]["hyphen"] = True
        elif token == "__" and out:
            out[-1]["extend"] = True
        else:
            out.append({"text": token, "hyphen": False, "extend": False})
    return out


def attach(part: ET.Element, slur: list[bool], syls: list[dict]) -> int:
    onsets = [n for n in part.iter("note")
              if n.find("pitch") is not None and not any(t.get("type") == "stop" for t in n.findall("tie"))]
    if len(onsets) != len(slur):
        raise SystemExit(f"{part.get('id')}: {len(onsets)} notes in the XML but {len(slur)} in the source")
    slots = [n for n, continues in zip(onsets, slur) if not continues]
    if len(slots) != len(syls):
        raise SystemExit(f"{part.get('id')}: {len(slots)} lyric slots but {len(syls)} syllables")
    placed = 0
    joined = False
    for note, syl in zip(slots, syls):
        if syl["text"] == "_":
            continue
        kind = ("middle" if syl["hyphen"] else "end") if joined else ("begin" if syl["hyphen"] else "single")
        lyric = ET.SubElement(note, "lyric", number="1")
        ET.SubElement(lyric, "syllabic").text = kind
        ET.SubElement(lyric, "text").text = syl["text"].replace("~", " ")
        if syl["extend"]:
            ET.SubElement(lyric, "extend")
        joined = syl["hyphen"]
        placed += 1
    return placed


def main() -> None:
    if len(sys.argv) < 5:
        raise SystemExit(__doc__)
    src = Path(sys.argv[1]).read_text(encoding="utf-8-sig")
    tree = ET.parse(sys.argv[2])
    parts = {p.get("id"): p for p in tree.getroot().iter("part")}
    for spec in sys.argv[4:]:
        pid, pair = spec.split("=", 1)
        notes_var, lyrics_var = pair.split(":", 1)
        placed = attach(parts[pid], slurred_notes(block(src, notes_var)), syllables(block(src, lyrics_var)))
        print(f"{pid}: placed {placed} syllables")
    tree.write(sys.argv[3], encoding="UTF-8", xml_declaration=True)


if __name__ == "__main__":
    main()
