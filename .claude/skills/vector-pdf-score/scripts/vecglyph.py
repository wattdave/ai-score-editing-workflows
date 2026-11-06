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
