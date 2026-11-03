"""Unit tests for the lyrics processing and linting module."""

from ai_score_editing.core.lyrics import (
    analyze_lyric_typography,
    assemble_bar_words,
    extract_font_and_size,
    filter_lyrics,
    find_typographical_inconsistencies,
    find_verse_style_jumps,
    format_lint_report,
    format_lyrics,
    format_lyrics_by_bar,
    lint_lyrics,
)


def test_assemble_bar_words_empty():
    assert assemble_bar_words([]) == ""


def test_assemble_bar_words_single_and_hyphenated():
    syllables = [
        {"text": "Ne", "syllableType": "end"},
        {"text": "se-", "syllableType": "middle"},
        {"text": "di", "syllableType": "end"},
        {"text": "Dje-", "syllableType": "middle"},
        {"text": "mo,", "syllableType": "end"},
    ]
    result = assemble_bar_words(syllables)
    assert result == "Ne se-di Dje-mo,"


def test_assemble_bar_words_skips_empty():
    syllables = [
        {"text": "", "syllableType": "middle"},
        {"text": "  ", "syllableType": "end"},
        {"text": "test", "syllableType": "end"},
    ]
    assert assemble_bar_words(syllables) == "test"


def test_format_lyrics_by_bar():
    lyrics = [
        {"staff": 1, "bar": 2, "position": 0, "text": "foo", "syllableType": "end"},
        {"staff": 2, "bar": 1, "position": 0, "text": "bar", "syllableType": "end"},
        {"staff": 1, "bar": 1, "position": 0, "text": "baz", "syllableType": "end"},
    ]
    names = {1: "Soprano", 2: "Tenor"}
    formatted = format_lyrics_by_bar(lyrics, names)

    expected = (
        "=== Staff 1 (Soprano) ===\n"
        "  Bar  1: baz\n"
        "  Bar  2: foo\n"
        "=== Staff 2 (Tenor) ===\n"
        "  Bar  1: bar"
    )
    assert formatted == expected


def test_format_lyrics_by_bar_empty():
    assert format_lyrics_by_bar([]) == "(no lyrics found)"


def test_lint_empty_and_clean():
    issues = lint_lyrics([])
    assert issues == []
    report = format_lint_report(issues)
    assert "clean" in report.lower()


def test_lint_position_collision_and_empty():
    lyrics = [
        {"staff": 1, "bar": 3, "position": 512, "text": "", "syllableType": "end"},
        {"staff": 1, "bar": 3, "position": 256, "text": "word1", "syllableType": "end"},
        {"staff": 1, "bar": 3, "position": 256, "text": "word2", "syllableType": "end"},
    ]
    issues = lint_lyrics(lyrics)
    types = {i["type"] for i in issues}
    assert "empty_syllable" in types
    assert "position_collision" in types


def test_lint_malformed_syllable_no_vowels():
    lyrics = [
        {"staff": 1, "bar": 5, "position": 0, "text": "gn-", "syllableType": "middle"},
        {"staff": 1, "bar": 5, "position": 256, "text": "de", "syllableType": "end"},
    ]
    issues = lint_lyrics(lyrics)
    assert any(i["type"] == "malformed_syllable" and "gn" in i["message"] for i in issues)


def test_lint_text_divergence_and_punctuation():
    lyrics = [
        # Staff 1 has "Djemo."
        {"staff": 1, "bar": 1, "position": 0, "text": "Dje-", "syllableType": "middle"},
        {"staff": 1, "bar": 1, "position": 256, "text": "mo.", "syllableType": "end"},
        # Staff 2 has "Demo," (divergent spelling + divergent punctuation)
        {"staff": 2, "bar": 1, "position": 0, "text": "De-", "syllableType": "middle"},
        {"staff": 2, "bar": 1, "position": 256, "text": "mo,", "syllableType": "end"},
    ]
    issues = lint_lyrics(lyrics, staff_names={1: "Soprano", 2: "Alto"})
    types = {i["type"] for i in issues}
    assert "text_divergence" in types
    assert "punctuation_mismatch" in types


def test_lint_untexted_passage():
    lyrics = [
        {"staff": 1, "bar": 1, "position": 0, "text": "la", "syllableType": "end"},
        {"staff": 1, "bar": 4, "position": 0, "text": "la", "syllableType": "end"},
    ]
    staff_bars = {
        1: [
            {"barNumber": 1, "objects": [{"type": "NoteRest", "notes": [{"pitch": 60}]}]},
            {"barNumber": 2, "objects": [{"type": "NoteRest", "notes": [{"pitch": 62}]}]},
            {"barNumber": 3, "objects": [{"type": "NoteRest", "notes": [{"pitch": 64}]}]},
            {"barNumber": 4, "objects": [{"type": "NoteRest", "notes": [{"pitch": 65}]}]},
        ]
    }
    issues = lint_lyrics(lyrics, staff_names={1: "Vocal"}, staff_bars=staff_bars)
    untexted = [i for i in issues if i["type"] == "untexted_passage"]
    assert len(untexted) == 1
    assert "bars 2–3" in untexted[0]["message"]


def test_lint_note_lyric_collision():
    lyrics = [
        {"staff": 1, "bar": 12, "position": 0, "text": "ra", "syllableType": "middle"},
        {"staff": 1, "bar": 12, "position": 256, "text": "zna", "syllableType": "middle"},
        {"staff": 1, "bar": 12, "position": 512, "text": "ze", "syllableType": "end"},
    ]
    staff_bars = {
        1: [
            {
                "barNumber": 12,
                "objects": [
                    {"type": "NoteRest", "position": 0, "notes": [{"name": "G", "pitch": 67}]},
                    {"type": "NoteRest", "position": 256, "notes": [{"name": "C", "pitch": 60}]},
                    {"type": "NoteRest", "position": 512, "notes": [{"name": "G", "pitch": 55}]},
                ],
            }
        ]
    }
    issues = lint_lyrics(lyrics, staff_names={1: "Soprano"}, staff_bars=staff_bars)
    collisions = [i for i in issues if i["type"] == "note_lyric_collision"]
    assert len(collisions) == 1
    assert collisions[0]["bar"] == 12
    assert "C4" in collisions[0]["message"]
    assert "G3" in collisions[0]["message"]


def test_filter_lyrics_bar_range_and_verse():
    lyrics = [
        {"staff": 1, "bar": 1, "position": 0, "text": "1.Cuan", "line": 1},
        {"staff": 1, "bar": 1, "position": 0, "text": "2.Ve", "line": 2},
        {"staff": 1, "bar": 2, "position": 0, "text": "te", "line": 1},
        {"staff": 1, "bar": 2, "position": 0, "text": "to,", "line": 2},
        {"staff": 1, "bar": 3, "position": 0, "text": "ra,", "line": 1},
    ]
    b12 = filter_lyrics(lyrics, from_bar=1, to_bar=2)
    assert len(b12) == 4
    assert {s["bar"] for s in b12} == {1, 2}

    v2 = filter_lyrics(lyrics, verse=2)
    assert len(v2) == 2
    assert all(s["line"] == 2 for s in v2)


def test_format_lyrics_multi_verse():
    lyrics = [
        {"staff": 1, "bar": 1, "position": 0, "text": "1.Cuan", "syllableType": "middle", "line": 1},
        {"staff": 1, "bar": 1, "position": 256, "text": "do", "syllableType": "end", "line": 1},
        {"staff": 1, "bar": 1, "position": 0, "text": "2.Ve", "syllableType": "middle", "line": 2},
        {"staff": 1, "bar": 1, "position": 256, "text": "ni", "syllableType": "end", "line": 2},
    ]
    formatted = format_lyrics(lyrics, {1: "Solo"})
    assert "[Verse 1]" in formatted
    assert "[Verse 2]" in formatted
    assert "1.Cuan-do" in formatted
    assert "2.Ve-ni" in formatted

    v1_only = format_lyrics(lyrics, {1: "Solo"}, verse=1)
    assert "[Verse 2]" not in v1_only
    assert "1.Cuan-do" in v1_only


def test_lint_multi_verse_no_false_positive():
    lyrics = [
        {"staff": 1, "bar": 1, "position": 0, "text": "v1a", "syllableType": "end", "line": 1},
        {"staff": 1, "bar": 1, "position": 0, "text": "v2a", "syllableType": "end", "line": 2},
        {"staff": 1, "bar": 1, "position": 256, "text": "v1b", "syllableType": "end", "line": 1},
        {"staff": 1, "bar": 1, "position": 256, "text": "v2b", "syllableType": "end", "line": 2},
    ]
    issues = lint_lyrics(lyrics)
    assert not any(i["type"] == "position_collision" for i in issues)


def test_lint_multi_verse_real_collision():
    lyrics = [
        {"staff": 1, "bar": 1, "position": 0, "text": "v1a", "syllableType": "end", "line": 1},
        {"staff": 1, "bar": 1, "position": 0, "text": "v2a", "syllableType": "end", "line": 2},
        {"staff": 1, "bar": 1, "position": 256, "text": "v1b1", "syllableType": "end", "line": 1},
        {"staff": 1, "bar": 1, "position": 256, "text": "v1b2", "syllableType": "end", "line": 1},
        {"staff": 1, "bar": 1, "position": 256, "text": "v2b", "syllableType": "end", "line": 2},
    ]
    issues = lint_lyrics(lyrics)
    collisions = [i for i in issues if i["type"] == "position_collision"]
    assert len(collisions) == 1
    assert "Line 1" in collisions[0]["message"]


def test_find_verse_style_jumps_detected():
    # Syllables jump from line 2 to line 1 mid-phrase
    lyrics = [
        {"staff": 1, "voice": 1, "bar": 20, "position": 0, "text": "I'll", "styleId": "text.staff.space.hypen.lyrics.verse2"},
        {"staff": 1, "voice": 1, "bar": 20, "position": 512, "text": "sing", "styleId": "text.staff.space.hypen.lyrics.verse2"},
        {"staff": 1, "voice": 1, "bar": 21, "position": 768, "text": "jah!", "styleId": "text.staff.space.hypen.lyrics.verse2"},
        {"staff": 1, "voice": 1, "bar": 21, "position": 1280, "text": "And", "styleId": "text.staff.space.hypen.lyrics.verse1"},
        {"staff": 1, "voice": 1, "bar": 22, "position": 0, "text": "you'll", "styleId": "text.staff.space.hypen.lyrics.verse1"},
    ]
    issues = find_verse_style_jumps(lyrics, {1: "Soprano"})
    assert len(issues) == 1
    assert issues[0]["type"] == "verse_style_jump"
    assert issues[0]["bar"] == 21
    assert "Line 2" in issues[0]["message"]
    assert "Line 1" in issues[0]["message"]


def test_find_verse_style_jumps_no_false_positive_on_stacked_verses():
    # Stacking verse 1 and verse 2 at the same positions should not trigger jumps
    lyrics = [
        {"staff": 1, "voice": 1, "bar": 1, "position": 0, "text": "v1", "styleId": "text.staff.space.hypen.lyrics.verse1"},
        {"staff": 1, "voice": 1, "bar": 1, "position": 0, "text": "v2", "styleId": "text.staff.space.hypen.lyrics.verse2"},
        {"staff": 1, "voice": 1, "bar": 1, "position": 512, "text": "w1", "styleId": "text.staff.space.hypen.lyrics.verse1"},
        {"staff": 1, "voice": 1, "bar": 1, "position": 512, "text": "w2", "styleId": "text.staff.space.hypen.lyrics.verse2"},
    ]
    issues = find_verse_style_jumps(lyrics)
    assert issues == []


def test_find_typographical_inconsistencies():
    # Majority font is Big Caslon size 88, but one syllable is Helvetica size 74
    lyrics = [
        {"staff": 1, "bar": 1, "position": 0, "text": "\\fBig Caslon\\s88\\Word1"},
        {"staff": 1, "bar": 1, "position": 256, "text": "\\fBig Caslon\\s88\\Word2"},
        {"staff": 1, "bar": 1, "position": 512, "text": "\\fBig Caslon\\s88\\Word3"},
        {"staff": 1, "bar": 2, "position": 0, "text": "\\fHelvetica\\s74\\Word4"},
    ]
    issues = find_typographical_inconsistencies(lyrics, {1: "Soprano"})
    types = {i["type"] for i in issues}
    assert "font_inconsistency" in types
    assert "font_size_inconsistency" in types
    font_issue = next(i for i in issues if i["type"] == "font_inconsistency")
    assert "Helvetica" in font_issue["message"]
    assert "Big Caslon" in font_issue["message"]
    size_issue = next(i for i in issues if i["type"] == "font_size_inconsistency")
    assert "74" in size_issue["message"]
    assert "88" in size_issue["message"]


def test_extract_font_and_size():
    # Syllable with embedded tags
    syl1 = {"text": "\\fTimes New Roman\\s96\\Hello"}
    font, size = extract_font_and_size(syl1)
    assert font == "Times New Roman"
    assert size == 96

    # Syllable with metadata dictionary fields
    syl2 = {"text": "World", "initialFontName": "BigCaslon-Medium", "initialFontSize": 88}
    font, size = extract_font_and_size(syl2)
    assert font == "BigCaslon-Medium"
    assert size == 88

    # Syllable with textWithFormatting overriding plain text
    syl3 = {
        "text": "World",
        "textWithFormatting": "\\fQuicksand\\s88\\World",
    }
    font, size = extract_font_and_size(syl3)
    assert font == "Quicksand"
    assert size == 88


def test_analyze_lyric_typography_uniform():
    lyrics = [
        {"staff": 1, "bar": 1, "position": 0, "text": "\\fQuicksand\\s88\\One"},
        {"staff": 1, "bar": 1, "position": 256, "text": "\\fQuicksand\\s88\\Two"},
    ]
    typo = analyze_lyric_typography(lyrics, score_default_font="Quicksand")
    assert typo["total_syllables"] == 2
    assert typo["predominant_font"] == "Quicksand"
    assert typo["predominant_size"] == 88
    assert typo["predominant_font_count"] == 2
    assert typo["predominant_font_pct"] == 100.0
    assert typo["has_divergence_from_score_default"] is False
    assert typo["inconsistent_syllables"] == []


def test_analyze_lyric_typography_divergence_from_score_default():
    lyrics = [
        {"staff": 1, "bar": 1, "position": 0, "text": "\\fQuicksand\\s88\\One"},
        {"staff": 1, "bar": 1, "position": 256, "text": "\\fQuicksand\\s88\\Two"},
        {"staff": 1, "bar": 1, "position": 512, "text": "\\fQuicksand\\s88\\Three"},
        {"staff": 1, "bar": 2, "position": 0, "text": "\\fPlantin\\s88\\Four"},
    ]
    typo = analyze_lyric_typography(lyrics, score_default_font="Plantin")
    assert typo["predominant_font"] == "Quicksand"
    assert typo["predominant_font_count"] == 3
    assert typo["has_divergence_from_score_default"] is True
    assert "Quicksand" in typo["divergence_message"]
    assert "Plantin" in typo["divergence_message"]
    assert len(typo["inconsistent_syllables"]) == 1
    assert typo["inconsistent_syllables"][0]["font"] == "Plantin"


def test_find_typographical_inconsistencies_with_score_default():
    lyrics = [
        {"staff": 1, "bar": 1, "position": 0, "text": "\\fQuicksand\\s88\\One"},
        {"staff": 1, "bar": 1, "position": 256, "text": "\\fQuicksand\\s88\\Two"},
    ]
    issues = find_typographical_inconsistencies(
        lyrics, staff_names={1: "Soprano"}, score_default_font="Plantin"
    )
    assert len(issues) == 1
    assert issues[0]["type"] == "font_score_divergence"
    assert "Plantin" in issues[0]["message"]
    assert "Quicksand" in issues[0]["message"]


def test_format_lint_report_with_typography():
    typo = {
        "score_default_font": "Plantin",
        "predominant_font": "Quicksand",
        "predominant_font_count": 45,
        "total_syllables": 48,
        "predominant_font_pct": 93.75,
        "predominant_size": 88,
        "font_counts": {"Quicksand": 45, "Plantin": 3},
        "has_divergence_from_score_default": True,
    }
    report = format_lint_report([], typography=typo)
    assert "=== Lyric Typography Analysis ===" in report
    assert "Score Default Font: Plantin" in report
    assert "Predominant Font:   Quicksand (45/48 syllables, 94%)" in report
    assert "Predominant Size Value: 88" in report
    assert "Divergence detected" in report
    assert "Adopt 'Quicksand'" in report
    assert "No lyric issues found" in report



