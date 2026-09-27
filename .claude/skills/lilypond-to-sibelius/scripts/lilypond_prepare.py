"""Flatten a LilyPond score into a notes-only file that python-ly can convert.

python-ly's MusicXML export copes with plain staves of notes, but not with
most real-world engraving code. This keeps each part's notes and drops the
rest: incipits, bar checks, overrides, markup, editorial brackets, and any
macros you name. Bar checks are dropped because python-ly treats them as
barlines; rebar.py rebuilds the bars afterwards.

usage:
  lilypond_prepare.py SOURCE.ly OUT.ly --part VAR[:CLEF] [--part ...]
      [--language english] [--drop MACRO ...] [--replace MACRO=LILYPOND ...]

VAR is the variable holding a part's notes (e.g. cantoI or NotesS). CLEF, if
given, is written before the part (treble, bass, "treble_8", ...); leave it
out when the variable sets its own clef.

Run convert-ly on old files first. Check the result against LilyPond's own
MIDI with midi_info.py before trusting it.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path


def find_block(src: str, name: str) -> tuple[str, str]:
    """Return (prefix, braced body) for `name = [\\relative X] { ... }`."""
    match = re.search(rf"(?m)^\s*{re.escape(name)}\s*=", src)
    if not match:
        raise SystemExit(f"variable {name} not found")
    start = src.index("{", match.end())
    prefix = src[match.end():start].strip()
    depth = 0
    for end in range(start, len(src)):
        depth += {"{": 1, "}": -1}.get(src[end], 0)
        if depth == 0:
            return prefix, src[start:end + 1]
    raise SystemExit(f"unbalanced braces in {name}")


def clean(body: str, drop: list[str], replace: dict[str, str]) -> str:
    """Strip engraving-only code from a part's notes."""
    body = re.sub(r"%.*", "", body)
    body = re.sub(r"\\incipitStart\b.*?\\incipitEnd\b", " ", body, flags=re.DOTALL)
    for macro, value in replace.items():
        body = re.sub(rf"\\{re.escape(macro)}\b", lambda _m, v=value: f" {v} ", body)
    body = re.sub(r"\\set\s+[\w.]+\s*=\s*#?(\"[^\"]*\"|##?[tf])", " ", body)
    body = re.sub(r"\\unset\s+[\w.]+", " ", body)
    body = re.sub(r"(\\once\s*)?\\override\s+[^\n]*", " ", body)
    body = re.sub(r"\\revert\s+[\w.]+(\s+#'[\w-]+|\.[\w-]+)?", " ", body)
    body = re.sub(r"s1\*0\s*[_^-]?\\markup\s*(\"[^\"]*\"|\{[^}]*\})", " ", body)
    body = re.sub(r"[_^-]?\\markup\s*(\"[^\"]*\"|\{[^}]*\})", " ", body)
    body = re.sub(r"\\bar\s*\"[^\"]*\"", " ", body)
    body = body.replace("\\[", " ").replace("\\]", " ")
    body = re.sub(r"\\longa\*1/2", r"\\breve", body)
    body = re.sub(r"(?<![A-Za-z\\])R(?![A-Za-z])", "r", body)
    body = re.sub(r"(?<!\|)\|(?!\|)", " ", body)
    for macro in drop:
        body = re.sub(rf"\\{re.escape(macro)}\b", " ", body)
    return re.sub(r"[ \t]+", " ", body)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source")
    parser.add_argument("out")
    parser.add_argument("--part", action="append", required=True, metavar="VAR[:CLEF]")
    parser.add_argument("--language", help='note-name language, e.g. "english" for bf/fs names')
    parser.add_argument("--drop", nargs="*", default=[], metavar="MACRO", help="macros to delete (no arguments)")
    parser.add_argument("--replace", nargs="*", default=[], metavar="MACRO=LILYPOND",
                        help=r"macros to substitute, e.g. 'fourTwoCutTime=\time 4/2'")
    args = parser.parse_args()

    src = Path(args.source).read_text(encoding="utf-8-sig")
    replace = dict(item.split("=", 1) for item in args.replace)
    lines = ['\\version "2.26.0"']
    if args.language:
        lines.append(f'\\language "{args.language}"')
    lines.append("<<")
    for spec in args.part:
        name, _, clef = spec.partition(":")
        prefix, body = find_block(src, name)
        clef_cmd = f"\\clef {clef} " if clef else ""
        lines.append(f"\\new Staff = \"{name}\" {{ {clef_cmd}{prefix} {clean(body, args.drop, replace)} }}")
    lines.append(">>")
    Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {args.out} with {len(args.part)} part(s)")


if __name__ == "__main__":
    main()
