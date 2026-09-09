"""Unit tests for the lyrics processing and linting module."""

from sibelius_websocket_cli.lyrics import (
    assemble_bar_words,
    filter_lyrics,
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


