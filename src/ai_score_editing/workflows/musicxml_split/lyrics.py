"""Lyric repair helpers shared by the SATB splitter and its CLI wrappers."""

from __future__ import annotations

import copy
import re
import xml.etree.ElementTree as ET
from pathlib import Path


def load_english_lexicon() -> set[str]:
    """Load standard words from macOS dictionary plus common choral terms."""
    words = set()
    dict_path = Path("/usr/share/dict/words")
    if dict_path.exists():
        with open(dict_path, "r", errors="ignore") as f:
            for line in f:
                w = line.strip().lower()
                if len(w) > 1:
                    words.add(w)
    words.update([
        "stories", "scenes", "dreams", "weaving", "perfect", "precious",
        "lonely", "pretty", "shining", "children", "forever", "together",
        "loneliness", "inside", "plenty", "delight", "treasure", "concerned",
        "spending", "pleasing", "collected", "guitar", "fairy", "after", "ago"
    ])
    return words


def reconnect_lyrics_in_root(root: ET.Element) -> int:
    """Reconnect shattered OMR syllables across all parts into begin/middle/end words."""
    dict_words = load_english_lexicon()
    stopwords = {"to", "be", "in", "on", "at", "as", "is", "it", "so", "no", "we", "he", "me", "my", "of", "and", "the", "a", "all", "one", "for", "her", "was", "long"}
    total_reconnected = 0

    for part in root.findall("part"):
        tokens = []
        for m in part.findall("measure"):
            for n in m.findall(".//note"):
                lyrs = n.findall("lyric")
                if lyrs:
                    lyr = lyrs[0]
                    t_elem = lyr.find("text")
                    txt = t_elem.text if (t_elem is not None and t_elem.text) else ""
                    clean = re.sub(r"[^a-zA-Z]", "", txt).lower()
                    tokens.append((lyr, txt, clean))

        i = 0
        while i < len(tokens):
            # Try 3-syllables (e.g. won-der-ful, lone-li-ness, for-e-ver)
            if i + 2 < len(tokens):
                t1, t2, t3 = tokens[i][2], tokens[i+1][2], tokens[i+2][2]
                c3 = t1 + t2 + t3
                if t1.isalpha() and t2.isalpha() and t3.isalpha():
                    if len(c3) > 3 and c3 in dict_words and t1 not in stopwords:
                        s1 = tokens[i][0].find("syllabic")
                        if s1 is None:
                            s1 = ET.SubElement(tokens[i][0], "syllabic")
                        s1.text = "begin"

                        s2 = tokens[i+1][0].find("syllabic")
                        if s2 is None:
                            s2 = ET.SubElement(tokens[i+1][0], "syllabic")
                        s2.text = "middle"

                        s3 = tokens[i+2][0].find("syllabic")
                        if s3 is None:
                            s3 = ET.SubElement(tokens[i+2][0], "syllabic")
                        s3.text = "end"

                        total_reconnected += 1
                        i += 3
                        continue

            # Try 2-syllables (e.g. wea-ving, sto-ries, per-fect, con-cerned)
            if i + 1 < len(tokens):
                t1, t2 = tokens[i][2], tokens[i+1][2]
                c2 = t1 + t2
                if t1.isalpha() and t2.isalpha():
                    is_w1 = t1 in dict_words and len(t1) > 2 and t1 not in stopwords
                    is_w2 = t2 in dict_words and len(t2) > 2 and t2 not in stopwords
                    if c2 in dict_words and not (t1 in stopwords or t2 in stopwords):
                        if not (is_w1 and is_w2) or c2 in ("forever", "together", "cannot", "maybe", "into", "without", "inside", "ago", "alone"):
                            s1 = tokens[i][0].find("syllabic")
                            if s1 is None:
                                s1 = ET.SubElement(tokens[i][0], "syllabic")
                            s1.text = "begin"

                            s2 = tokens[i+1][0].find("syllabic")
                            if s2 is None:
                                s2 = ET.SubElement(tokens[i+1][0], "syllabic")
                            s2.text = "end"

                            total_reconnected += 1
                            i += 2
                            continue
            i += 1

    return total_reconnected


def copy_soprano_lyrics_to_tb(root: ET.Element) -> None:
    """Copy only missing lyrics when source and target note streams align."""
    parts = {part.attrib.get("id"): part for part in root.findall("part")}
    soprano, tenor, bass = parts.get("P1"), parts.get("P3"), parts.get("P4")
    if soprano is None or tenor is None or bass is None:
        return
    for s_measure, t_measure, b_measure in zip(
        soprano.findall("measure"), tenor.findall("measure"), bass.findall("measure"), strict=True
    ):
        source = [copy.deepcopy(note.findall("lyric")[0]) if note.findall("lyric") else None for note in s_measure.findall("note")]
        for measure in (t_measure, b_measure):
            notes = measure.findall("note")
            if len(notes) == len(source):
                for note, lyric in zip(notes, source, strict=True):
                    if lyric is not None and not note.findall("lyric"):
                        note.append(lyric)
