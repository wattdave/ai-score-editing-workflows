"""Utilities for assembling, formatting, and linting score lyrics."""

from __future__ import annotations

import re
from typing import Any

VOWELS_PATTERN = re.compile(r"[aeiouyáéíóúäëïöüàèìòùâêîôûãõñāēīōūăěǐǒǔ]", re.IGNORECASE)


def get_syllable_line(syl: dict[str, Any], default: int = 1) -> int:
    """Return the 1-based verse/line number for a syllable if known."""
    if "line" in syl and syl["line"] is not None:
        try:
            val = int(syl["line"])
            if val > 0:
                return val
        except (ValueError, TypeError):
            pass
    style_id = syl.get("styleId") or syl.get("style", "")
    if isinstance(style_id, str):
        match = re.search(r"line(\d+)", style_id, re.IGNORECASE)
        if match:
            return int(match.group(1))
    return default


def infer_syllable_lines(lyrics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Annotate syllables with a 1-based 'line' (verse) attribute if missing.

    If syllables already have an explicit 'line' or recognizable 'styleId', they are preserved.
    Otherwise, if a staff consistently contains multiple syllables per position across notes,
    the vertical stack at each position is mapped to lines 1, 2, ...
    """
    if not lyrics:
        return []

    by_staff: dict[int, list[dict[str, Any]]] = {}
    for s in lyrics:
        by_staff.setdefault(s.get("staff", 1), []).append(s)

    result: list[dict[str, Any]] = []

    for staff, staff_syls in by_staff.items():
        explicit = any(
            ("line" in s and s["line"] is not None)
            or bool(re.search(r"line(\d+)", str(s.get("styleId", "")), re.I))
            for s in staff_syls
        )

        by_bar_pos: dict[tuple[int, int], list[dict[str, Any]]] = {}
        for s in staff_syls:
            key = (s.get("bar", 1), s.get("position", 0))
            by_bar_pos.setdefault(key, []).append(s)

        depth_counts = [len(s_list) for s_list in by_bar_pos.values()]
        multi_positions = sum(1 for d in depth_counts if d > 1)
        is_multi_verse = multi_positions >= 2

        for (bar, pos), s_list in by_bar_pos.items():
            for i, s in enumerate(s_list):
                s_copy = dict(s)
                if explicit:
                    s_copy["line"] = get_syllable_line(s_copy, default=i + 1)
                elif is_multi_verse:
                    s_copy["line"] = i + 1
                else:
                    s_copy["line"] = 1
                result.append(s_copy)

    # Re-sort to preserve original staff, bar, position, and index
    result.sort(key=lambda s: (s.get("staff", 1), s.get("bar", 1), s.get("position", 0), s.get("index", 0)))
    return result


def filter_lyrics(
    lyrics: list[dict[str, Any]],
    from_bar: int | None = None,
    to_bar: int | None = None,
    verse: int | None = None,
) -> list[dict[str, Any]]:
    """Filter lyrics by bar range and optional verse line."""
    annotated = infer_syllable_lines(lyrics)
    filtered: list[dict[str, Any]] = []
    for s in annotated:
        bar = s.get("bar", 1)
        if from_bar is not None and bar < from_bar:
            continue
        if to_bar is not None and bar > to_bar:
            continue
        if verse is not None and s.get("line") != verse:
            continue
        filtered.append(s)
    return filtered


def assemble_bar_words(syllables: list[dict[str, Any]]) -> str:
    """Join syllables within a bar into hyphenated words."""
    if not syllables:
        return ""

    words: list[str] = []
    current_word_parts: list[str] = []

    for syl in syllables:
        text = syl.get("text", "")
        syllable_type = syl.get("syllableType", "end")

        if not text.strip():
            continue

        clean_text = text.rstrip("-")
        current_word_parts.append(clean_text)

        if syllable_type == "end":
            words.append("-".join(current_word_parts))
            current_word_parts = []

    if current_word_parts:
        words.append("-".join(current_word_parts))

    return " ".join(words)


def format_lyrics(
    lyrics: list[dict[str, Any]],
    staff_names: dict[int, str] | None = None,
    by_bar: bool = False,
    verse: int | None = None,
) -> str:
    """Format a list of syllables into readable text grouped by staff and verse/bar."""
    if not lyrics:
        return "(no lyrics found)"

    annotated = infer_syllable_lines(lyrics)
    if verse is not None:
        annotated = [s for s in annotated if s.get("line") == verse]
        if not annotated:
            return f"(no lyrics found for verse {verse})"

    names = staff_names or {}
    staves: dict[int, list[dict[str, Any]]] = {}
    for s in annotated:
        staves.setdefault(s.get("staff", 1), []).append(s)

    lines: list[str] = []
    for staff in sorted(staves.keys()):
        name = names.get(staff, f"Staff {staff}")
        lines.append(f"=== Staff {staff} ({name}) ===")
        staff_syls = staves[staff]

        verses: dict[int, dict[int, list[dict[str, Any]]]] = {}
        for s in staff_syls:
            l_num = s.get("line", 1)
            bar = s.get("bar", 1)
            verses.setdefault(l_num, {}).setdefault(bar, []).append(s)

        is_multi = len(verses) > 1 and not by_bar

        if is_multi:
            for l_num in sorted(verses.keys()):
                lines.append(f"[Verse {l_num}]")
                bars = verses[l_num]
                for bar in sorted(bars.keys()):
                    text = assemble_bar_words(bars[bar])
                    lines.append(f"  Bar {bar:2d}: {text}")
        else:
            by_b: dict[int, list[dict[str, Any]]] = {}
            for s in staff_syls:
                by_b.setdefault(s.get("bar", 1), []).append(s)
            for bar in sorted(by_b.keys()):
                text = assemble_bar_words(by_b[bar])
                lines.append(f"  Bar {bar:2d}: {text}")

    return "\n".join(lines)


def format_lyrics_by_bar(
    lyrics: list[dict[str, Any]],
    staff_names: dict[int, str] | None = None,
) -> str:
    """Format a list of syllables into readable text grouped by staff and bar."""
    return format_lyrics(lyrics, staff_names, by_bar=True)


def _edit_distance(s1: str, s2: str) -> int:
    """Simple Levenshtein distance."""
    if len(s1) < len(s2):
        return _edit_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)

    previous_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]


def lint_lyrics(
    lyrics: list[dict[str, Any]],
    staff_names: dict[int, str] | None = None,
    staff_bars: dict[int, list[dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    """Inspect lyrics for collisions, cross-voice typos, malformed syllables, and missing lyrics."""
    issues: list[dict[str, Any]] = []
    names = staff_names or {}

    annotated_lyrics = infer_syllable_lines(lyrics)

    # Group syllables by (staff, bar) and bar
    by_staff_bar: dict[tuple[int, int], list[dict[str, Any]]] = {}
    by_bar: dict[int, dict[int, list[dict[str, Any]]]] = {}

    for syl in annotated_lyrics:
        staff = syl.get("staff", 1)
        bar = syl.get("bar", 1)
        by_staff_bar.setdefault((staff, bar), []).append(syl)
        by_bar.setdefault(bar, {}).setdefault(staff, []).append(syl)

    # 1. Check for duplicates / collisions at same position and empty syllables
    for (staff, bar), syls in by_staff_bar.items():
        s_name = names.get(staff, f"Staff {staff}")
        positions: dict[int, list[dict[str, Any]]] = {}
        for s in syls:
            pos = s.get("position", 0)
            text = s.get("text", "")
            if not text.strip():
                issues.append({
                    "type": "empty_syllable",
                    "severity": "warning",
                    "bar": bar,
                    "staff": staff,
                    "message": f"Staff {staff} ({s_name}): Empty syllable at position {pos}",
                })
            positions.setdefault(pos, []).append(s)

        for pos, pos_syls in positions.items():
            by_line: dict[int, list[dict[str, Any]]] = {}
            for s in pos_syls:
                l_num = s.get("line", 1)
                by_line.setdefault(l_num, []).append(s)

            for l_num, line_syls in by_line.items():
                if len(line_syls) > 1:
                    texts = [repr(s.get("text", "")) for s in line_syls]
                    line_str = f", Line {l_num}" if l_num > 1 or len(by_line) > 1 else ""
                    issues.append({
                        "type": "position_collision",
                        "severity": "error",
                        "bar": bar,
                        "staff": staff,
                        "line": l_num,
                        "message": (
                            f"Staff {staff} ({s_name}){line_str}: {len(line_syls)} overlapping syllables "
                            f"at position {pos}: {', '.join(texts)}"
                        ),
                    })

    # 2. Check for malformed syllables (no vowels)
    for s in annotated_lyrics:
        text = s.get("text", "").strip()
        letters_only = "".join(c for c in text if c.isalpha())
        if len(letters_only) >= 2 and not VOWELS_PATTERN.search(letters_only):
            staff = s.get("staff", 1)
            bar = s.get("bar", 1)
            s_name = names.get(staff, f"Staff {staff}")
            issues.append({
                "type": "malformed_syllable",
                "severity": "error",
                "bar": bar,
                "staff": staff,
                "message": f"Staff {staff} ({s_name}): Syllable {text!r} has no vowels (possible missing vowel)",
            })

    # 3. Cross-voice divergence in the same bar (compared verse by verse)
    for bar in sorted(by_bar.keys()):
        staves_in_bar = by_bar[bar]
        if len(staves_in_bar) < 2:
            continue

        lines_in_bar = sorted({s.get("line", 1) for s_list in staves_in_bar.values() for s in s_list})

        for l_num in lines_in_bar:
            bar_words: dict[int, str] = {}
            for st, s_syls in staves_in_bar.items():
                line_syls = [s for s in s_syls if s.get("line", 1) == l_num]
                if line_syls:
                    bar_words[st] = assemble_bar_words(line_syls)

            staff_list = sorted(bar_words.keys())
            for i in range(len(staff_list)):
                for j in range(i + 1, len(staff_list)):
                    s1, s2 = staff_list[i], staff_list[j]
                    w1, w2 = bar_words[s1], bar_words[s2]
                    name1 = names.get(s1, f"Staff {s1}")
                    name2 = names.get(s2, f"Staff {s2}")
                    l_str = f" (Line {l_num})" if len(lines_in_bar) > 1 else ""

                    # Check trailing punctuation divergence
                    p1 = w1[-1] if w1 and w1[-1] in ".,;:?!" else ""
                    p2 = w2[-1] if w2 and w2[-1] in ".,;:?!" else ""
                    if p1 and p2 and p1 != p2:
                        issues.append({
                            "type": "punctuation_mismatch",
                            "severity": "warning",
                            "bar": bar,
                            "staves": [s1, s2],
                            "message": (
                                f"Punctuation mismatch: Staff {s1} ({name1}){l_str} ends with {p1!r}, "
                                f"but Staff {s2} ({name2}){l_str} ends with {p2!r}"
                            ),
                        })

                    # Check word similarity / typo differences
                    tokens1 = re.findall(r"\b[\w-]+\b", w1)
                    tokens2 = re.findall(r"\b[\w-]+\b", w2)
                    if len(tokens1) == len(tokens2) and tokens1 != tokens2:
                        for t1, t2 in zip(tokens1, tokens2):
                            if t1 != t2:
                                dist = _edit_distance(t1.lower(), t2.lower())
                                if 1 <= dist <= 2:
                                    issues.append({
                                        "type": "text_divergence",
                                        "severity": "error",
                                        "bar": bar,
                                        "staves": [s1, s2],
                                        "message": (
                                            f"Potential typo/divergence: Staff {s1} ({name1}){l_str} has {t1!r}, "
                                            f"but Staff {s2} ({name2}){l_str} has {t2!r}"
                                        ),
                                    })

    # 4. Check for untexted passages on vocal staves that have notes
    if staff_bars:
        vocal_staves = {s.get("staff", 1) for s in lyrics}
        for staff in vocal_staves:
            bars_data = staff_bars.get(staff, [])
            untexted_streak: list[int] = []
            s_name = names.get(staff, f"Staff {staff}")

            for b_info in bars_data:
                bar_num = b_info.get("barNumber", 0)
                has_notes = any(
                    obj.get("type") == "NoteRest" and obj.get("notes")
                    for obj in b_info.get("objects", [])
                )
                has_lyrics = (staff, bar_num) in by_staff_bar

                if has_notes and not has_lyrics:
                    untexted_streak.append(bar_num)
                else:
                    if len(untexted_streak) >= 2:
                        issues.append({
                            "type": "untexted_passage",
                            "severity": "warning",
                            "bar": untexted_streak[0],
                            "staff": staff,
                            "message": (
                                f"Staff {staff} ({s_name}): Notes present without lyrics "
                                f"across bars {untexted_streak[0]}–{untexted_streak[-1]}"
                            ),
                        })
                    untexted_streak = []

            if len(untexted_streak) >= 2:
                issues.append({
                    "type": "untexted_passage",
                    "severity": "warning",
                    "bar": untexted_streak[0],
                    "staff": staff,
                    "message": (
                        f"Staff {staff} ({s_name}): Notes present without lyrics "
                        f"across bars {untexted_streak[0]}–{untexted_streak[-1]}"
                    ),
                })

    # 5. Check for vertical note/lyric collisions on vocal staves
    if staff_bars:
        for staff, bars_data in staff_bars.items():
            s_name = names.get(staff, f"Staff {staff}")
            all_pitches: list[int] = []
            for b_info in bars_data:
                for obj in b_info.get("objects", []):
                    if obj.get("type") == "NoteRest" and obj.get("notes"):
                        for n in obj["notes"]:
                            p = n.get("pitch")
                            if isinstance(p, int):
                                all_pitches.append(p)

            if not all_pitches:
                continue

            median_pitch = sorted(all_pitches)[len(all_pitches) // 2]
            s_name_lower = s_name.lower().strip()
            is_tenor = s_name_lower in {"t.", "t", "tenor", "tenore"} or (
                "tenor" in s_name_lower and "alto" not in s_name_lower and "a." not in s_name_lower
            )
            is_bass = (
                "bass" in s_name_lower
                or s_name_lower in {"b.", "b", "basso", "bassoon"}
                or median_pitch <= 50
            )

            # In Treble clef, notes <= 60 (C4 and below) sit below the staff.
            # Tenors in choral notation use octave treble clef (sounding pitch is 12 semitones lower than written).
            # When a bar has a large pitch plunge (span >= 8 semitones down to sub-staff notes <= 60),
            # or extreme low notes (<= 55 on treble / <= 38 on bass), the lyric baseline anchored
            # by higher notes fails to clear the low noteheads and ledger lines.
            low_cutoff = 40 if is_bass else 60
            extreme_cutoff = 38 if is_bass else 55
            high_cutoff = 45 if is_bass else 64

            for b_info in bars_data:
                bar_num = b_info.get("barNumber", 0)
                bar_syls = by_staff_bar.get((staff, bar_num), [])
                if not bar_syls:
                    continue

                syls_by_pos = {s.get("position", 0): s.get("text", "") for s in bar_syls}

                bar_notes = [
                    (obj.get("position", 0), obj["notes"])
                    for obj in b_info.get("objects", [])
                    if obj.get("type") == "NoteRest" and obj.get("notes")
                ]
                if not bar_notes:
                    continue

                all_written_pitches = [
                    (n.get("pitch", 100) + 12 if is_tenor else n.get("pitch", 100))
                    for _, notes in bar_notes
                    for n in notes
                ]
                min_bar_p = min(all_written_pitches)
                max_bar_p = max(all_written_pitches)
                span = max_bar_p - min_bar_p

                is_plunge = min_bar_p <= low_cutoff and max_bar_p >= high_cutoff and span >= 8
                is_extreme = min_bar_p <= extreme_cutoff

                if not (is_plunge or is_extreme):
                    continue

                colliding_notes: list[tuple[str, int, str]] = []
                for pos, notes in bar_notes:
                    lowest = min(notes, key=lambda n: n.get("pitch", 100))
                    raw_p = lowest.get("pitch", 100)
                    w_p = raw_p + 12 if is_tenor else raw_p
                    threshold = low_cutoff if is_plunge else extreme_cutoff
                    if w_p <= threshold and pos in syls_by_pos:
                        n_name = lowest.get("name", "")
                        octave = w_p // 12 - 1
                        note_label = f"{n_name}{octave}" if n_name else f"pitch {w_p}"
                        syl_text = syls_by_pos[pos]
                        colliding_notes.append((note_label, w_p, syl_text))

                if colliding_notes:
                    note_names_str = ", ".join(cn[0] for cn in colliding_notes)
                    syl_texts_str = ", ".join(repr(cn[2]) for cn in colliding_notes)
                    issues.append({
                        "type": "note_lyric_collision",
                        "severity": "warning",
                        "bar": bar_num,
                        "staff": staff,
                        "message": (
                            f"Staff {staff} ({s_name}): {len(colliding_notes)} low note(s) "
                            f"({note_names_str}) descend to ledger lines below staff "
                            f"carrying lyrics ({syl_texts_str}) — potential vertical collision"
                        ),
                    })

    # Deduplicate issues by message
    unique_issues: list[dict[str, Any]] = []
    seen: set[str] = set()
    for issue in issues:
        key = f"{issue['type']}:{issue['bar']}:{issue['message']}"
        if key not in seen:
            seen.add(key)
            unique_issues.append(issue)

    return sorted(unique_issues, key=lambda x: (x.get("bar", 0), x.get("type", "")))


def format_lint_report(issues: list[dict[str, Any]]) -> str:
    """Render lint issues as human-readable text."""
    if not issues:
        return "No lyric issues found. Score lyrics look clean!"

    lines: list[str] = [f"Found {len(issues)} lyric issue(s):\n"]
    for issue in issues:
        tag = issue.get("type", "issue").upper().replace("_", " ")
        bar = issue.get("bar", "?")
        msg = issue.get("message", "")
        lines.append(f"  [{tag}] Bar {bar}: {msg}")

    return "\n".join(lines)
