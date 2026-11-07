"""Glyph code normalisation for Opus/Helsinki PDFs (no PDF library needed, so it can be tested alone).

Sibelius's own PDF export stores the music-font glyphs under their Mac Roman characters (notehead 'œ',
half note '˙', dot '™'). A PDF made through a Windows print driver (PScript5, PDFCreator, PrimoPDF) stores
the same glyphs as symbol-font codes: the same byte plus 0xF000 (U+F0CF for 'œ', U+F0FA for '˙', U+F0AA for
'™'). normalize_glyph maps both to the Mac Roman character the reader's tables use."""


def normalize_glyph(ch: str) -> str:
    code = ord(ch)
    if 0xF000 <= code <= 0xF0FF:
        return bytes([code - 0xF000]).decode("mac_roman")
    return ch


def has_music_code(text: str) -> bool:
    """True if the text holds a symbol-font code (U+F000-U+F0FF): a run of music glyphs that text extraction
    returned as a "word", never a lyric syllable."""
    return any(0xF000 <= ord(ch) <= 0xF0FF for ch in text)


def stem_barline_cut(sp: float, helsinki: bool) -> float:
    """Line width above which a vertical line is a barline and not a stem. Helsinki stems are 0.60 wide and barlines
    0.75 whatever the staff size. Opus widths scale with the staff space sp (stems 0.09-0.10 sp, barlines 0.155 sp:
    0.42/0.66 at sp 4.25 but 0.36/0.60 at sp 3.75, where a fixed 0.6 cut missed every barline)."""
    return 0.68 if helsinki else 0.125 * sp
  
def is_music_font(font: str, text: str) -> bool:
    """True if a text span is set in a music font. Sibelius names the fonts Opus* and Helsinki*; Ghostscript
    renames them (TT1F7t00, TT204t00, TT206t00) and drops the name, so also accept a span whose non-space
    characters are all symbol-font codes (U+F000-U+F0FF, never present in a text font's lyrics or title)."""
    if font.startswith(("Opus", "Helsinki")):
        return True
    chars = [ch for ch in text if not ch.isspace()]
    return bool(chars) and all(0xF000 <= ord(ch) <= 0xF0FF for ch in chars)
