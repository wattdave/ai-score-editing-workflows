#!/usr/bin/env python3
"""Join separate lyric syllables into hyphenated words in a MusicXML file.

Lyrics typed or imported one syllable at a time come out as unconnected text
("win ter", "mak ing"). This sets <syllabic> begin/middle/end so the editor
draws the hyphens. Words are found by concatenating neighbouring syllables
and checking /usr/share/dict/words (plus inflections and a few extras).

    hyphenate_lyrics.py score.xml -o fixed.xml          # write
    hyphenate_lyrics.py score.xml --dry-run             # list joins only
    hyphenate_lyrics.py score.xml -o fixed.xml --not-word fireside --word mistletoe
"""

from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

EXTRA_WORDS = {"december", "caroling", "mistletoe", "together", "christmas", "holiday",
               "winter", "auspicious", "ausspicious", "tonight", "really", "everybody", "gonna", "dreamin"}
#: Real words that are usually two sung words or scat syllables, never joined by default.
NOT_WORDS = {"fireside", "baba", "carling", "daydreaming", "outshine", "domba"}
#: Syllables that are words on their own; a join needs at least one non-common fragment.
COMMON = {"a", "i", "the", "and", "of", "to", "be", "in", "on", "at", "as", "is", "it", "so", "no", "we",
          "he", "me", "my", "all", "one", "for", "her", "was", "with", "you", "this", "love", "come", "true",
          "will", "by", "do", "they", "how", "much", "fun", "get", "know", "trim", "tree", "kiss", "dream",
          "hang", "day", "night", "bright", "side", "care", "thru", "real", "special", "wish", "ooh", "oh",
          "going", "from", "that", "are", "can", "our", "your", "there", "now", "then"}
#: A word that starts with one of these is never joined (except the listed exceptions).
STOP = {"to", "be", "in", "on", "at", "as", "is", "it", "so", "no", "we", "he", "me", "my", "of", "and",
        "the", "a", "all", "one", "for", "her", "was", "with", "you", "this", "love", "come", "true",
        "will", "do", "they", "how", "by"}
STOP_EXCEPTIONS = {"together", "tonight"}
#: Joined whenever the fragments concatenate to one of these (informal sung forms).
FORCE_JOIN = {"together", "tonight", "gonna", "dreamin"}
SUFFIXES = ("ing", "es", "ed", "er", "ly", "s")


def load_words(extra: set[str] = frozenset(), not_words: set[str] = frozenset()) -> set[str]:
    words: set[str] = set()
    path = Path("/usr/share/dict/words")
    if path.exists():
        words = {w.strip().lower() for w in path.read_text(errors="ignore").splitlines() if len(w.strip()) > 1}
    return (words | EXTRA_WORDS | set(extra)) - NOT_WORDS - set(not_words)


def is_word(cat: str, words: set[str]) -> bool:
    if cat in words:
        return True
    for suffix in SUFFIXES:
        if cat.endswith(suffix) and len(cat) - len(suffix) >= 3:
            stem = cat[: -len(suffix)]
            if stem in words or stem + "e" in words:
                return True
    return False


def clean(text: str) -> str:
    return re.sub(r"[^a-zA-Z]", "", text).lower()


def word_groups(tokens: list[str], words: set[str]) -> list[tuple[int, int]]:
    """(start, length) of runs of 2-4 syllables that make one word."""
    out, i = [], 0
    while i < len(tokens):
        for n in (4, 3, 2):
            if i + n > len(tokens):
                continue
            frags = [clean(t) for t in tokens[i:i + n]]
            if not all(frags):
                continue
            if any(t[:1].isupper() for t in tokens[i + 1:i + n]):
                continue  # a capital starts a new word ("day Dream-ing")
            cat = "".join(frags)
            if len(cat) < 4 or not is_word(cat, words):
                continue
            if cat not in FORCE_JOIN:
                if any(f in STOP for f in frags) and cat not in STOP_EXCEPTIONS:
                    continue
                if all(f in COMMON or (f in words and len(f) > 3) for f in frags):
                    continue
            out.append((i, n))
            i += n
            break
        else:
            i += 1
    return out


def set_syllabic(lyric: ET.Element, value: str) -> None:
    node = lyric.find("syllabic")
    if node is None:
        node = ET.Element("syllabic")
        lyric.insert(0, node)
    node.text = value


def hyphenate_lyric_run(lyrics: list[ET.Element], words: set[str]) -> list[str]:
    """Set syllabic on a time-ordered run of lyric elements; return the joined words."""
    texts = [(lyric.findtext("text") or "") for lyric in lyrics]
    joined = []
    for start, n in word_groups(texts, words):
        for k in range(n):
            set_syllabic(lyrics[start + k], "begin" if k == 0 else ("end" if k == n - 1 else "middle"))
        joined.append("-".join(texts[start:start + n]))
    return joined


def hyphenate_tree(root: ET.Element, words: set[str]) -> Counter:
    """One run per part, staff, voice and verse number, in document order."""
    runs: dict[tuple, list[ET.Element]] = {}
    for part in root.findall("part"):
        for note in part.iter("note"):
            for lyric in note.findall("lyric"):
                key = (part.get("id"), note.findtext("staff"), note.findtext("voice"), lyric.get("number"))
                runs.setdefault(key, []).append(lyric)
    found: Counter = Counter()
    for lyrics in runs.values():
        found.update(hyphenate_lyric_run(lyrics, words))
    return found


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input")
    ap.add_argument("-o", "--output")
    ap.add_argument("--dry-run", action="store_true", help="list the words that would be joined")
    ap.add_argument("--word", action="append", default=[], help="extra word to recognise (lowercase, no hyphens)")
    ap.add_argument("--not-word", action="append", default=[], help="word never to join")
    args = ap.parse_args()
    tree = ET.parse(args.input)
    found = hyphenate_tree(tree.getroot(), load_words(set(args.word), set(args.not_word)))
    for word, count in sorted(found.items()):
        print(f"{count:3d}  {word}")
    print(f"{sum(found.values())} words joined, {len(found)} distinct")
    if not args.dry_run:
        if not args.output:
            ap.error("-o/--output is required unless --dry-run")
        tree.write(args.output, encoding="UTF-8", xml_declaration=True)
        print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
