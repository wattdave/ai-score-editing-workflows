#!/usr/bin/env python3
"""Audit, split, and validate 2-staff choral/piano scores into 4-staff SATB scores.

Thin argparse wrapper over ``ai_score_editing.musicxml_split`` (the single MusicXML
splitting engine).  Supports both uncompressed .xml and compressed .mxl MusicXML files.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# The skill remains runnable with plain ``python3`` from a source checkout.
REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from ai_score_editing.musicxml_split.io import parse_musicxml, save_musicxml  # noqa: E402
from ai_score_editing.musicxml_split.lyrics import (  # noqa: E402
    copy_soprano_lyrics_to_tb,
    reconnect_lyrics_in_root,
)
from ai_score_editing.musicxml_split.profiles.satb import SATBOptions, split_satb  # noqa: E402


def parse_bar_ranges(range_str: str) -> set[int]:
    """Parse comma-separated bar numbers and ranges, e.g. '8-15,20-27,41'."""
    bars = set()
    if not range_str.strip():
        return bars
    for part in range_str.split(","):
        part = part.strip()
        if "-" in part:
            start, end = part.split("-", 1)
            bars.update(range(int(start), int(end) + 1))
        elif part:
            bars.add(int(part))
    return bars


def cmd_audit(args: argparse.Namespace) -> int:
    """Audit a 2-staff score for voices, chord clusters, and lyrics."""
    path = Path(args.input)
    if not path.exists():
        print(f"error: file not found: {path}", file=sys.stderr)
        return 1

    _, root = parse_musicxml(path)
    parts = root.findall("part")
    print(f"File: {path.name}")
    print(f"Parts found: {len(parts)}")

    for p in parts:
        pid = p.attrib.get("id")
        measures = p.findall("measure")
        print(f"\n--- Part {pid} ({len(measures)} measures) ---")

        s1_voices = set()
        s2_voices = set()
        chords_s1 = 0
        chords_s2 = 0
        lyrics_count = 0

        for m in measures:
            for elem in m:
                if elem.tag == "note":
                    s = elem.find("staff")
                    v = elem.find("voice")
                    s_val = s.text if (s is not None and s.text) else "1"
                    v_val = v.text if (v is not None and v.text) else "1"
                    if s_val == "1":
                        s1_voices.add(v_val)
                        if elem.find("chord") is not None:
                            chords_s1 += 1
                    else:
                        s2_voices.add(v_val)
                        if elem.find("chord") is not None:
                            chords_s2 += 1
                    if elem.findall("lyric"):
                        lyrics_count += len(elem.findall("lyric"))

        print(f"  Staff 1 Voices: {sorted(list(s1_voices))}")
        print(f"  Staff 1 Chord Note Elements: {chords_s1}")
        print(f"  Staff 2 Voices: {sorted(list(s2_voices))}")
        print(f"  Staff 2 Chord Note Elements: {chords_s2}")
        print(f"  Total Lyrics Found: {lyrics_count}")

    return 0


def cmd_split(args: argparse.Namespace) -> int:
    """Split a 2-staff score into 4 discrete SATB parts."""
    in_path = Path(args.input)
    out_path = Path(args.output)
    if not in_path.exists():
        print(f"error: file not found: {in_path}", file=sys.stderr)
        return 1

    # All routing lives in the shared onset-based engine; lyric repair is post-processing.
    options = SATBOptions(
        soprano_solo_bars=frozenset(parse_bar_ranges(args.soprano_solo or "")),
        tenor_solo_bars=frozenset(parse_bar_ranges(args.tenor_solo or "")),
        bass_solo_bars=frozenset(parse_bar_ranges(args.bass_solo or "")),
    )
    result = split_satb(in_path, out_path, options)
    if result.issues:
        for issue in result.issues:
            print(f"[{issue.severity}] {issue.code}: {issue.message}", file=sys.stderr)
    if args.copy_lyrics_to_tb or args.reconnect_lyrics:
        _, output_root = parse_musicxml(out_path)
        if args.copy_lyrics_to_tb:
            copy_soprano_lyrics_to_tb(output_root)
        if args.reconnect_lyrics:
            count = reconnect_lyrics_in_root(output_root)
            print(f"Reconnected {count} multi-syllable words across parts.")
        save_musicxml(output_root, out_path)
    print(f"Successfully split into 4-staff score: {out_path}")
    return 0


def cmd_reconnect_lyrics(args: argparse.Namespace) -> int:
    """Scan and reconnect shattered OMR lyric syllables in an existing MusicXML file."""
    in_path = Path(args.input)
    out_path = Path(args.output) if args.output else in_path
    if not in_path.exists():
        print(f"error: file not found: {in_path}", file=sys.stderr)
        return 1

    tree, root = parse_musicxml(in_path)
    count = reconnect_lyrics_in_root(root)
    save_musicxml(root, out_path)
    print(f"Successfully reconnected {count} words in {out_path}")
    return 0



def cmd_validate(args: argparse.Namespace) -> int:
    """Validate measure durations across all 4 parts of an SATB score."""
    path = Path(args.input)
    if not path.exists():
        print(f"error: file not found: {path}", file=sys.stderr)
        return 1

    _, root = parse_musicxml(path)
    parts = root.findall("part")
    if len(parts) != 4:
        print(f"[!] Warning: Expected 4 parts, found {len(parts)}", file=sys.stderr)

    issues = 0
    current_div = 1
    current_beats = 4
    current_beat_type = 4

    for p in parts:
        pid = p.attrib.get("id", "unknown")
        for m in p.findall("measure"):
            mnum = m.attrib.get("number", "?")
            div_elem = m.find(".//divisions")
            if div_elem is not None and div_elem.text:
                current_div = int(div_elem.text)
            time_elem = m.find(".//time")
            if time_elem is not None:
                beats_e = time_elem.find("beats")
                bt_e = time_elem.find("beat-type")
                if beats_e is not None and bt_e is not None and beats_e.text and bt_e.text:
                    current_beats = int(beats_e.text)
                    current_beat_type = int(bt_e.text)

            expected_dur = int(current_beats * (4.0 / current_beat_type) * current_div)
            actual_dur = 0
            for n in m.findall("note"):
                if n.find("chord") is None:
                    d_elem = n.find("duration")
                    if d_elem is not None and d_elem.text:
                        actual_dur += int(d_elem.text)

            if actual_dur != expected_dur and expected_dur > 0:
                print(f"  [!] Duration mismatch in Part {pid} Bar {mnum}: expected {expected_dur}, got {actual_dur}")
                issues += 1

    if issues == 0:
        print(f"Clean validation: all {len(parts)} parts have consistent measure durations across {path.name}.")
        return 0
    else:
        print(f"Validation finished: {issues} issue(s) found.")
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit, split, and validate 2-staff scores into 4-staff SATB.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # audit
    p_audit = subparsers.add_parser("audit", help="Audit a 2-staff score for voices, chords, and lyrics")
    p_audit.add_argument("input", help="Path to input .xml or .mxl")
    p_audit.set_defaults(func=cmd_audit)

    # split
    p_split = subparsers.add_parser("split", help="Split 2-staff score into 4-staff SATB")
    p_split.add_argument("input", help="Path to input 2-staff .xml or .mxl")
    p_split.add_argument("--output", "-o", required=True, help="Path to output 4-staff .xml or .mxl")
    p_split.add_argument("--tenor-solo", help="Comma-separated bar numbers or ranges for Tenor solo (e.g. '8-15,20-27')")
    p_split.add_argument("--bass-solo", help="Comma-separated bar numbers or ranges for Bass solo")
    p_split.add_argument("--soprano-solo", help="Comma-separated bar numbers or ranges for Soprano solo")
    p_split.add_argument("--copy-lyrics-to-tb", action="store_true", help="Copy choral lyrics to homophonic Tenor/Bass lines")
    p_split.add_argument("--reconnect-lyrics", action="store_true", default=True, help="Automatically reconnect shattered OMR syllables into begin/middle/end words (default: True)")
    p_split.add_argument("--no-reconnect-lyrics", dest="reconnect_lyrics", action="store_false", help="Disable automatic syllable reconnection")
    p_split.set_defaults(func=cmd_split)

    # reconnect-lyrics
    p_rec = subparsers.add_parser("reconnect-lyrics", help="Scan and reconnect shattered OMR syllables in an XML or MXL file")
    p_rec.add_argument("input", help="Path to input .xml or .mxl")
    p_rec.add_argument("--output", "-o", help="Path to output .xml or .mxl (defaults to overwriting input)")
    p_rec.set_defaults(func=cmd_reconnect_lyrics)

    # validate
    p_val = subparsers.add_parser("validate", help="Validate measure durations in an SATB score")
    p_val.add_argument("input", help="Path to 4-staff .xml or .mxl")
    p_val.set_defaults(func=cmd_validate)

    args = parser.parse_args()
    return args.func(args)



if __name__ == "__main__":
    sys.exit(main())
