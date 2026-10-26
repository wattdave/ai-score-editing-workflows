"""Text style font report: which fonts the score's text and lyric styles use."""

from __future__ import annotations

from typing import Any

# Lyric style identifiers guaranteed to exist in every score.
LYRIC_STYLE_IDS = (
    "text.staff.space.hypen.lyrics.verse1",
    "text.staff.space.hypen.lyrics.verse2",
    "text.staff.space.hypen.lyrics.verse3",
    "text.staff.space.hypen.lyrics.verse4",
    "text.staff.space.hypen.lyrics.verse5",
    "text.staff.space.hypen.lyrics.chorus",
    "text.staff.space.hypen.lyrics.above",
    "text.staff.lyrics.block",
)

# Lower-case font name prefixes of symbol fonts: text set in them shows music
# symbols instead of letters.
MUSIC_FONT_PREFIXES = (
    "opus", "reprise", "helsinki", "inkpen2", "bravura", "petaluma", "leland",
    "maestro", "november", "engraver", "sebastian", "norfolk", "seville",
)


def is_music_font(name: str | None) -> bool:
    return bool(name) and str(name).strip().casefold().startswith(MUSIC_FONT_PREFIXES)


def is_lyric_style(style_id: str) -> bool:
    return ".lyrics." in style_id


def style_requests(found: list[tuple[str, bool]]) -> list[dict[str, Any]]:
    """Styles to probe: the lyric styles plus every (styleId, system) found in the score."""
    seen: dict[str, bool] = {style_id: False for style_id in LYRIC_STYLE_IDS}
    for style_id, system in found:
        if style_id:
            seen.setdefault(style_id, system)
    return [{"styleId": style_id, "system": system} for style_id, system in seen.items()]


def build_report(score_info: dict[str, Any], probed: list[dict[str, Any]]) -> dict[str, Any]:
    """Combine the score font settings with the probed style fonts and flag symbol fonts."""
    styles = []
    warnings = []
    for row in probed:
        style_id = row.get("styleId", "")
        entry = dict(row)
        font = row.get("fontName")
        entry["lyric"] = is_lyric_style(style_id)
        entry["musicFont"] = is_music_font(font)
        if entry["lyric"] and entry["musicFont"]:
            warnings.append(
                f"lyric style {style_id} uses the music font {font!r}: lyrics will show as music symbols"
            )
        styles.append(entry)
    main_text = score_info.get("mainTextFontName")
    if is_music_font(main_text):
        warnings.append(
            f"main text font is the music font {main_text!r}: text styles that follow it show music symbols"
        )
    return {
        "mainTextFontName": main_text,
        "mainMusicFontName": score_info.get("mainMusicFontName"),
        "musicTextFontName": score_info.get("musicTextFontName"),
        "styles": styles,
        "warnings": warnings,
        "note": "fontSize is in 1/32 spaces (SU), not points",
    }
