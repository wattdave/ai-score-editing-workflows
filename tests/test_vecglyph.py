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


def test_barline_cut_scales_with_staff_size_for_opus() -> None:
    # (stem width, barline width, staff space) measured in Dona Nobis Pacem, Here's a Health and In Dulci Jubilo
    for stem, bar, sp in [(0.42, 0.66, 4.25), (0.36, 0.60, 3.825), (0.36, 0.60, 3.9)]:
        cut = vecglyph.stem_barline_cut(sp, False)
        assert stem <= cut < bar
    assert vecglyph.stem_barline_cut(4.0, True) == 0.68
