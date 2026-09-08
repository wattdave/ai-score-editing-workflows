"""Utilities for assembling, formatting, and linting score lyrics."""

from __future__ import annotations

import re
from typing import Any

VOWELS_PATTERN = re.compile(r"[aeiouyáéíóúäëïöüàèìòùâêîôûãõñāēīōūăěǐǒǔ]", re.IGNORECASE)


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


def format_lyrics_by_bar(
    lyrics: list[dict[str, Any]],
    staff_names: dict[int, str] | None = None,
) -> str:
    """Format a list of syllables into readable text grouped by staff and bar."""
    if not lyrics:
        return "(no lyrics found)"

    names = staff_names or {}
    staves: dict[int, dict[int, list[dict[str, Any]]]] = {}

    for syl in lyrics:
        staff = syl.get("staff", 1)
        bar = syl.get("bar", 1)
        staves.setdefault(staff, {}).setdefault(bar, []).append(syl)

    lines: list[str] = []
    for staff in sorted(staves.keys()):
        name = names.get(staff, f"Staff {staff}")
        lines.append(f"=== Staff {staff} ({name}) ===")
        bars = staves[staff]
        for bar in sorted(bars.keys()):
            text = assemble_bar_words(bars[bar])
            lines.append(f"  Bar {bar:2d}: {text}")

    return "\n".join(lines)


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

    # Group syllables by (staff, bar) and bar
    by_staff_bar: dict[tuple[int, int], list[dict[str, Any]]] = {}
    by_bar: dict[int, dict[int, list[dict[str, Any]]]] = {}

    for syl in lyrics:
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
            if len(pos_syls) > 1:
                texts = [repr(s.get("text", "")) for s in pos_syls]
                issues.append({
                    "type": "position_collision",
                    "severity": "error",
                    "bar": bar,
                    "staff": staff,
                    "message": (
                        f"Staff {staff} ({s_name}): {len(pos_syls)} overlapping syllables "
                        f"at position {pos}: {', '.join(texts)}"
                    ),
                })

    # 2. Check for malformed syllables (no vowels)
    for s in lyrics:
        text = s.get("text", "").strip()
        letters_only = re.sub(r"[^a-zA-Z]", "", text)
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

    # 3. Cross-voice divergence in the same bar
    for bar in sorted(by_bar.keys()):
        staves_in_bar = by_bar[bar]
        if len(staves_in_bar) < 2:
            continue

        bar_words: dict[int, str] = {
            st: assemble_bar_words(s_syls) for st, s_syls in staves_in_bar.items()
        }

        # Compare pairs of staves
        staff_list = sorted(bar_words.keys())
        for i in range(len(staff_list)):
            for j in range(i + 1, len(staff_list)):
                s1, s2 = staff_list[i], staff_list[j]
                w1, w2 = bar_words[s1], bar_words[s2]
                name1 = names.get(s1, f"Staff {s1}")
                name2 = names.get(s2, f"Staff {s2}")

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
                            f"Punctuation mismatch: Staff {s1} ({name1}) ends with {p1!r}, "
                            f"but Staff {s2} ({name2}) ends with {p2!r}"
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
                                        f"Potential typo/divergence: Staff {s1} ({name1}) has {t1!r}, "
                                        f"but Staff {s2} ({name2}) has {t2!r}"
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
