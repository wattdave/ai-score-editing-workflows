"""Tests for the vector-pdf-score glyph normaliser (Opus PDFs printed through a Windows driver)."""

from helpers import ROOT, load_script

vecglyph = load_script(ROOT / ".claude/skills/vector-pdf-score/scripts/vecglyph.py", "vecglyph")


def test_print_driver_codes_map_to_the_sibelius_glyphs() -> None:
    # Mac Roman byte + 0xF000: notehead, half note, dot, treble and bass clef, flat, quarter and eighth rest.
    pairs = {"": "œ", "": "˙", "": "™", "": "&", "": "?", "": "b",
             "": "J", "": "j", "": "…", "": "‰"[0:0] or "•"}
    for code, glyph in pairs.items():
        assert vecglyph.normalize_glyph(code) == glyph


def test_plain_sibelius_glyphs_are_left_alone() -> None:
    for ch in "œ˙™&?bJjÓŒ‰>":
        assert vecglyph.normalize_glyph(ch) == ch


def test_music_glyph_runs_are_not_lyric_words() -> None:
    # Text extraction returned runs of music glyphs as "words" in print-driver PDFs; they stole notes from lyrics.
    assert vecglyph.has_music_code("") and vecglyph.has_music_code("a")
    assert not vecglyph.has_music_code("Al-le") and not vecglyph.has_music_code("lu")
