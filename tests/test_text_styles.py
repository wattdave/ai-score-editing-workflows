"""Text style font report and the Text font query fields."""

from pathlib import Path

import pytest

from ai_score_editing.query import QueryError, build_selector
from ai_score_editing.sibelius import cli
from ai_score_editing.text_styles import (
    LYRIC_STYLE_IDS,
    build_report,
    is_music_font,
    style_requests,
)

PLUGIN = Path(cli.__file__).parent / "manuscript" / "ScoreBridge.plg"


@pytest.mark.parametrize("name", ["Opus Text Std", "Opus Std", "Reprise", "reprise text", "Helsinki Std"])
def test_music_fonts(name) -> None:
    assert is_music_font(name)


@pytest.mark.parametrize("name", ["Garamond", "Times New Roman", "", None])
def test_text_fonts(name) -> None:
    assert not is_music_font(name)


def test_style_requests_keep_lyrics_and_system_flag() -> None:
    requests = style_requests(
        [("text.staff.expression", False), ("text.system.tempo", True), ("", False),
         ("text.staff.space.hypen.lyrics.verse1", False)]
    )
    ids = [r["styleId"] for r in requests]
    assert set(LYRIC_STYLE_IDS) <= set(ids)
    assert len(ids) == len(set(ids))
    assert {"styleId": "text.system.tempo", "system": True} in requests
    assert {"styleId": "text.staff.expression", "system": False} in requests


def test_report_flags_music_font_on_lyric_style() -> None:
    info = {"mainTextFontName": "Garamond", "mainMusicFontName": "Opus", "musicTextFontName": "Opus Text"}
    rows = [
        {"styleId": "text.staff.space.hypen.lyrics.verse1", "fontName": "Opus Text Std", "fontSize": 160},
        {"styleId": "text.staff.expression", "fontName": "Opus Text Std", "fontSize": 160},
        {"styleId": "text.staff.technique", "skipped": "AddText refused the style"},
    ]
    report = build_report(info, rows)
    assert [s["musicFont"] for s in report["styles"]] == [True, True, False]
    assert [s["lyric"] for s in report["styles"]] == [True, False, False]
    assert len(report["warnings"]) == 1
    assert "verse1" in report["warnings"][0]


def test_report_flags_music_main_text_font() -> None:
    report = build_report({"mainTextFontName": "Opus Text Std"}, [])
    assert "main text font" in report["warnings"][0]


def test_font_fields_accepted_for_text_only() -> None:
    selector = build_selector(
        staves=[], from_bar=None, to_bar=None, types=["Text"], voice=None,
        where=[], fields=["InitialFontName,InitialFontSize"],
    )
    assert selector["fields"] == ["InitialFontName", "InitialFontSize"]
    with pytest.raises(QueryError, match="unknown field"):
        build_selector(staves=[], from_bar=None, to_bar=None, types=["LyricItem"],
                       voice=None, where=[], fields=["FontName"])


def test_plugin_probe_and_version() -> None:
    source = PLUGIN.read_text()
    assert cli.TEXT_FONTS_BRIDGE_VERSION == cli.CURRENT_BRIDGE_VERSION == 61
    start = source.index('GetTextStyleFonts "(')
    body = source[start:source.index('}"\n', start)]
    # LyricItem has no font properties; the probe reads a Text object only
    assert "text.Type = 'Text'" in body
    assert "text.Delete();" in body
