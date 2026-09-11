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
        match = re.search(r"(?:line|verse)(\d+)", style_id, re.IGNORECASE)
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
            or bool(re.search(r"(?:line|verse)(\d+)", str(s.get("styleId", "")), re.I))
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


def extract_font_and_size(syl: dict[str, Any]) -> tuple[str | None, int | None]:
    """Extract font name and its raw size value without conflating Sibelius units.

    Styled-string ``\\sN\\`` values are tenths of a point. Historical or
    synthetic ``initialFontSize`` metadata may use Sibelius' native space
    units, so callers must not treat the two representations as convertible.
    """
    font = syl.get("initialFontName")
    size = syl.get("initialFontSize")
    text = syl.get("textWithFormatting") or syl.get("text", "")
    if isinstance(text, str):
        f_match = re.search(r"\\f([^\\]+)\\", text)
        if f_match:
            font = f_match.group(1).strip()
        s_match = re.search(r"\\s(\d+)\\", text)
        if s_match:
            size = int(s_match.group(1))
    f_clean = str(font).strip() if font and str(font).strip() and str(font).strip() != "null" else None
    s_val = int(size) if isinstance(size, int) and size > 0 else None
    return (f_clean, s_val)


def analyze_lyric_typography(
    lyrics: list[dict[str, Any]],
    score_default_font: str | None = None,
    staff_names: dict[int, str] | None = None,
) -> dict[str, Any]:
    """Analyze font families and sizes across lyrics, detecting predominant fonts and divergences from score defaults."""
    names = staff_names or {}
    font_records: list[tuple[dict[str, Any], str | None, int | None]] = []
    font_counts: dict[str, int] = {}
    size_counts: dict[int, int] = {}

    for s in lyrics:
        font, size = extract_font_and_size(s)
        font_records.append((s, font, size))
        if font:
            font_counts[font] = font_counts.get(font, 0) + 1
        if size:
            size_counts[size] = size_counts.get(size, 0) + 1

    total_syllables = len(lyrics)

    predominant_font = max(font_counts.items(), key=lambda x: x[1])[0] if font_counts else None
    predominant_font_count = font_counts.get(predominant_font, 0) if predominant_font else 0
    predominant_font_pct = (predominant_font_count / total_syllables * 100.0) if total_syllables > 0 else 0.0

    predominant_size = max(size_counts.items(), key=lambda x: x[1])[0] if size_counts else None
    predominant_size_count = size_counts.get(predominant_size, 0) if predominant_size else 0
    predominant_size_pct = (predominant_size_count / total_syllables * 100.0) if total_syllables > 0 else 0.0

    clean_default = (
        str(score_default_font).strip()
        if score_default_font and str(score_default_font).strip() and str(score_default_font).strip() != "null"
        else None
    )

    if not predominant_font and clean_default:
        predominant_font = clean_default
        predominant_font_count = total_syllables
        predominant_font_pct = 100.0 if total_syllables > 0 else 0.0


    has_divergence = False
    divergence_msg = None
    if clean_default and predominant_font and clean_default.lower() != predominant_font.lower():
        has_divergence = True
        divergence_msg = (
            f"Score embedded default font is '{clean_default}', but existing lyrics predominantly "
            f"use font '{predominant_font}' ({predominant_font_count}/{total_syllables} syllables, {predominant_font_pct:.0f}%). "
            f"Adopt '{predominant_font}' for lyric corrections to minimize visual clash."
        )

    inconsistent_syllables: list[dict[str, Any]] = []
    for s, font, size in font_records:
        staff = s.get("staff", 1)
        bar = s.get("bar", 1)
        text = s.get("text", "")
        s_name = names.get(staff, f"Staff {staff}")

        if predominant_font and font and font != predominant_font:
            inconsistent_syllables.append({
                "type": "font_inconsistency",
                "severity": "warning",
                "bar": bar,
                "staff": staff,
                "text": text,
                "font": font,
                "expected_font": predominant_font,
                "message": (
                    f"Staff {staff} ({s_name}): Syllable {text!r} uses font '{font}', "
                    f"differing from predominant font '{predominant_font}'"
                ),
            })
        if predominant_size and size and size != predominant_size:
            inconsistent_syllables.append({
                "type": "font_size_inconsistency",
                "severity": "warning",
                "bar": bar,
                "staff": staff,
                "text": text,
                "size": size,
                "expected_size": predominant_size,
                "message": (
                    f"Staff {staff} ({s_name}): Syllable {text!r} uses font size value {size}, "
                    f"differing from predominant value {predominant_size}"
                ),
            })

    return {
        "total_syllables": total_syllables,
        "score_default_font": clean_default,
        "predominant_font": predominant_font,
        "predominant_font_count": predominant_font_count,
        "predominant_font_pct": predominant_font_pct,
        "predominant_size": predominant_size,
        "predominant_size_count": predominant_size_count,
        "predominant_size_pct": predominant_size_pct,
        "font_counts": font_counts,
        "size_counts": size_counts,
        "has_divergence_from_score_default": has_divergence,
        "divergence_message": divergence_msg,
        "inconsistent_syllables": inconsistent_syllables,
    }


def find_verse_style_jumps(
    lyrics: list[dict[str, Any]],
    staff_names: dict[int, str] | None = None,
) -> list[dict[str, Any]]:
    """Detect unprompted mid-phrase jumps between lyric lines/verses on a single vocal voice."""
    issues: list[dict[str, Any]] = []
    names = staff_names or {}

    annotated = infer_syllable_lines(lyrics)
    by_staff_voice: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for s in annotated:
        key = (s.get("staff", 1), s.get("voice", 1))
        by_staff_voice.setdefault(key, []).append(s)

    for (staff, voice), syls in by_staff_voice.items():
        s_name = names.get(staff, f"Staff {staff}")
        sorted_syls = sorted(
            syls,
            key=lambda s: (s.get("bar", 1), s.get("position", 0), s.get("index", 0)),
        )
        if len(sorted_syls) < 2:
            continue

        pos_counts: dict[tuple[int, int], set[int]] = {}
        for s in sorted_syls:
            pos_counts.setdefault((s.get("bar", 1), s.get("position", 0)), set()).add(s.get("line", 1))

        for i in range(len(sorted_syls) - 1):
            cur = sorted_syls[i]
            nxt = sorted_syls[i + 1]

            cur_pos_key = (cur.get("bar", 1), cur.get("position", 0))
            nxt_pos_key = (nxt.get("bar", 1), nxt.get("position", 0))

            if len(pos_counts.get(cur_pos_key, set())) > 1 or len(pos_counts.get(nxt_pos_key, set())) > 1:
                continue

            cur_line = cur.get("line", 1)
            nxt_line = nxt.get("line", 1)

            if cur_line != nxt_line:
                bar_diff = nxt.get("bar", 1) - cur.get("bar", 1)
                if 0 <= bar_diff <= 1:
                    cur_text = cur.get("text", "")
                    nxt_text = nxt.get("text", "")
                    nxt_bar = nxt.get("bar", 1)
                    issues.append({
                        "type": "verse_style_jump",
                        "severity": "warning",
                        "bar": nxt_bar,
                        "staff": staff,
                        "voice": voice,
                        "message": (
                            f"Staff {staff} ({s_name}): Lyric baseline step between Bar {cur.get('bar', 1)} "
                            f"and Bar {nxt_bar}: syllable {nxt_text!r} is on Line {nxt_line}, but preceding "
                            f"syllable {cur_text!r} is on Line {cur_line}"
                        ),
                    })

    return issues


def find_typographical_inconsistencies(
    lyrics: list[dict[str, Any]],
    staff_names: dict[int, str] | None = None,
    score_default_font: str | None = None,
) -> list[dict[str, Any]]:
    """Detect mismatched font families or sizes across score lyrics and divergence from score defaults."""
    analysis = analyze_lyric_typography(lyrics, score_default_font=score_default_font, staff_names=staff_names)
    issues: list[dict[str, Any]] = []

    if analysis["has_divergence_from_score_default"] and analysis["divergence_message"]:
        issues.append({
            "type": "font_score_divergence",
            "severity": "warning",
            "bar": 1,
            "message": analysis["divergence_message"],
            "score_default_font": analysis["score_default_font"],
            "predominant_font": analysis["predominant_font"],
        })

    for item in analysis["inconsistent_syllables"]:
        issues.append({
            "type": item["type"],
            "severity": item["severity"],
            "bar": item["bar"],
            "staff": item["staff"],
            "message": item["message"],
        })

    return issues


def lint_lyrics(
    lyrics: list[dict[str, Any]],
    staff_names: dict[int, str] | None = None,
    staff_bars: dict[int, list[dict[str, Any]]] | None = None,
    score_default_font: str | None = None,
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

    # 6. Check for unprompted verse/line baseline jumps
    issues.extend(find_verse_style_jumps(annotated_lyrics, names))

    # 7. Check for typographical inconsistencies (font family & point size)
    issues.extend(
        find_typographical_inconsistencies(
            annotated_lyrics, names, score_default_font=score_default_font
        )
    )

    # Deduplicate issues by message
    unique_issues: list[dict[str, Any]] = []
    seen: set[str] = set()
    for issue in issues:
        key = f"{issue['type']}:{issue['bar']}:{issue['message']}"
        if key not in seen:
            seen.add(key)
            unique_issues.append(issue)

    return sorted(unique_issues, key=lambda x: (x.get("bar", 0), x.get("type", "")))


def format_lint_report(
    issues: list[dict[str, Any]],
    typography: dict[str, Any] | None = None,
) -> str:
    """Render lint issues as human-readable text, including an up-front typography summary."""
    lines: list[str] = []

    if typography and (typography.get("predominant_font") or typography.get("score_default_font")):
        lines.append("=== Lyric Typography Analysis ===")
        if typography.get("score_default_font"):
            lines.append(f"  Score Default Font: {typography['score_default_font']}")
        if typography.get("predominant_font"):
            cnt = typography.get("predominant_font_count", 0)
            tot = typography.get("total_syllables", 0)
            pct = typography.get("predominant_font_pct", 0.0)
            lines.append(
                f"  Predominant Font:   {typography['predominant_font']} ({cnt}/{tot} syllables, {pct:.0f}%)"
            )
        pred_size_val = typography.get("predominant_size")
        if pred_size_val:
            lines.append(f"  Predominant Size Value: {pred_size_val}")
        else:
            lines.append("  Predominant Size Value: unavailable from lyric objects")

        if len(typography.get("font_counts", {})) > 1:
            dist = ", ".join(
                f"{f}: {c}"
                for f, c in sorted(typography["font_counts"].items(), key=lambda x: -x[1])
            )
            lines.append(f"  Font Breakdown:     {dist}")

        if typography.get("has_divergence_from_score_default"):
            lines.append(
                f"  Status:             Divergence detected — existing lyrics use '{typography['predominant_font']}' "
                f"while score default is '{typography['score_default_font']}'."
            )
            lines.append(
                f"  Guidance:           Adopt '{typography['predominant_font']}' for lyric patches to minimize visual differences."
            )
        elif typography.get("inconsistent_syllables"):
            lines.append(
                f"  Status:             {len(typography['inconsistent_syllables'])} syllable(s) differ from predominant typography."
            )
        else:
            lines.append("  Status:             Consistent typography across lyrics.")
        lines.append("=================================\n")

    if not issues:
        lines.append("No lyric issues found. Score lyrics look clean!")
        return "\n".join(lines)

    lines.append(f"Found {len(issues)} lyric issue(s):\n")
    for issue in issues:
        tag = issue.get("type", "issue").upper().replace("_", " ")
        bar = issue.get("bar", "?")
        msg = issue.get("message", "")
        lines.append(f"  [{tag}] Bar {bar}: {msg}")

    return "\n".join(lines)
