"""CLI argument parsing and the run_* handlers (set-lyric fonts, barlines)."""

from __future__ import annotations

from fakes import CliSession, bridge_call


def test_parse_bar_range():
    from ai_score_editing.core.barrange import parse_bar_range

    assert parse_bar_range(bars="1-4") == (1, 4)
    assert parse_bar_range(bars="3..6") == (3, 6)
    assert parse_bar_range(bars="5") == (5, 5)
    assert parse_bar_range(bar=3) == (3, 3)
    assert parse_bar_range(from_bar=2, to_bar=8) == (2, 8)
    assert parse_bar_range() == (None, None)


def test_parser_new_subcommands_and_flags():
    from ai_score_editing.sibelius.cli import build_parser

    parser = build_parser()

    # save
    args = parser.parse_args(["save"])
    assert args.subcommand == "save"

    # reset-design
    args = parser.parse_args(["reset-design", "--lyrics", "--save"])
    assert args.subcommand == "reset-design"
    assert args.lyrics is True
    assert args.save is True

    # read-lyrics with --bars and --verse
    args = parser.parse_args(["read-lyrics", "--bars", "1-3", "--verse", "2", "--words", "--by-bar"])
    assert args.subcommand == "read-lyrics"
    assert args.bars == "1-3"
    assert args.verse == 2
    assert args.words is True
    assert args.by_bar is True

    # check-lyrics with --bars
    args = parser.parse_args(["check-lyrics", "--bars", "4-5"])
    assert args.subcommand == "check-lyrics"
    assert args.bars == "4-5"

    # set-lyric with --save
    args = parser.parse_args(["set-lyric", "--staff", "1", "--bar", "1", "--index", "0", "--text", "la", "--save"])
    assert args.save is True

    # flip-stem with --save
    args = parser.parse_args(["flip-stem", "--staff", "1", "--bar", "1", "--index", "0", "--save"])
    assert args.save is True

    # beam
    args = parser.parse_args(
        ["beam", "--staff", "1", "--bar", "2", "--from-index", "3", "--to-index", "5", "--save"]
    )
    assert args.from_index == 3
    assert args.to_index == 5
    assert args.save is True

    # nudge with --save
    args = parser.parse_args(["nudge", "--staff", "1", "--bar", "1", "--index", "0", "--dx", "1", "--save"])
    assert args.save is True

    # add-staff
    args = parser.parse_args(["add-staff", "--instrument", "soprano", "--position", "bottom", "--save"])
    assert args.subcommand == "add-staff"
    assert args.instrument == "soprano"
    assert args.position == "bottom"
    assert args.save is True

    # create-staff (alias)
    args = parser.parse_args(["create-staff", "--instrument", "piano", "--position", "auto"])
    assert args.subcommand == "create-staff"
    assert args.instrument == "piano"
    assert args.position == "auto"

    # add-bars
    args = parser.parse_args(["add-bars", "--count", "4", "--save"])
    assert args.subcommand == "add-bars"
    assert args.count == 4
    assert args.save is True

    # add-notes / add-note
    args = parser.parse_args(["add-notes", "--staff", "1", "--bar", "2", "--pos", "256", "--pitch", "C4,E4,G4", "--dur", "half", "--save"])
    assert args.subcommand == "add-notes"
    assert args.staff == 1
    assert args.bar == 2
    assert args.pos == 256
    assert args.pitches == "C4,E4,G4"
    assert args.duration == "half"
    assert args.save is True

    args = parser.parse_args(["add-note", "--staff", "2", "--bar", "1", "--notes", "C4:quarter D4:quarter"])
    assert args.subcommand == "add-note"
    assert args.notes == "C4:quarter D4:quarter"

    # add-abc
    args = parser.parse_args(["add-abc", "--staff", "1", "--bar", "1", "C D E F | G4", "--save"])
    assert args.subcommand == "add-abc"
    assert args.staff == 1
    assert args.bar == 1
    assert args.abc == "C D E F | G4"
    assert args.save is True

    # read with --abc
    args = parser.parse_args(["read", "--staff", "1", "--from", "1", "--to", "4", "--abc"])
    assert args.subcommand == "read"
    assert args.abc is True

    # read-abc
    args = parser.parse_args(["read-abc", "--staff", "1", "--bars", "1-4"])
    assert args.subcommand == "read-abc"
    assert args.bars == "1-4"

    # set-staff-name
    args = parser.parse_args(["set-staff-name", "--staff", "1", "--full", "Soprano", "--short", "S.", "--save"])
    assert args.subcommand == "set-staff-name"
    assert args.staff == 1
    assert args.full == "Soprano"
    assert args.short == "S."
    assert args.save is True

    # set-initial-instrument
    args = parser.parse_args(["set-initial-instrument", "--staff", "4", "--instrument", "bass", "--save"])
    assert args.subcommand == "set-initial-instrument"
    assert args.staff == 4
    assert args.instrument == "bass"
    assert args.save is True

    # duplicate-octave-down-to-voice2
    args = parser.parse_args(["duplicate-octave-down-to-voice2", "--staff", "4", "--from-bar", "1", "--to-bar", "12", "--save"])
    assert args.subcommand == "duplicate-octave-down-to-voice2"
    assert args.staff == 4
    assert args.from_bar == 1
    assert args.to_bar == 12
    assert args.save is True

    # set-score-info
    args = parser.parse_args(["set-score-info", "--title", "Hallelujah", "--composer", "William Walker", "--save"])
    assert args.subcommand == "set-score-info"
    assert args.title == "Hallelujah"
    assert args.composer == "William Walker"
    assert args.save is True

    # set-break
    args = parser.parse_args(["set-break", "--bar", "5", "--type", "system", "--save"])
    assert args.subcommand == "set-break"
    assert args.bar == 5
    assert args.type == "system"
    assert args.save is True

    # set-barline
    args = parser.parse_args(["set-barline", "--bar", "71", "--type", "double", "--save"])
    assert args.subcommand == "set-barline"
    assert args.bar == 71
    assert args.type == "double"
    assert args.save is True

    # read-barlines
    args = parser.parse_args(["read-barlines", "--bars", "70-75"])
    assert args.subcommand == "read-barlines"
    assert args.bars == "70-75"

    # set-lyric font options
    args = parser.parse_args([
        "set-lyric", "--staff", "1", "--bar", "12", "--index", "6", "--text", "When",
        "--font", "Big Caslon", "--font-size", "88", "--save",
    ])
    assert args.subcommand == "set-lyric"
    assert args.font == "Big Caslon"
    assert args.font_size == 88
    assert args.save is True

    # set-lyric-style
    args = parser.parse_args([
        "set-lyric-style", "--staff", "2", "--bar", "20", "--index", "0", "--style", "verse1", "--save",
    ])
    assert args.subcommand == "set-lyric-style"
    assert args.staff == 2
    assert args.bar == 20
    assert args.index == 0
    assert args.style == "verse1"
    assert args.save is True


async def test_run_set_lyric_adopts_predominant_font(cli_session: CliSession) -> None:
    from unittest.mock import AsyncMock, MagicMock, patch
    from ai_score_editing.sibelius.cli import build_parser
    from ai_score_editing.sibelius.commands.lyrics import _run_set_lyric

    parser = build_parser()
    args = parser.parse_args(["set-lyric", "--staff", "1", "--bar", "2", "--index", "0", "--text", "hermosa"])

    staff_lyrics = [
        {"staff": 1, "bar": 1, "index": 0, "text": "\\fQuicksand\\s88\\One"},
        {"staff": 1, "bar": 1, "index": 1, "text": "\\fQuicksand\\s88\\Two"},
        {"staff": 1, "bar": 2, "index": 0, "text": "ermosa"},
    ]

    mock_client_ctx = MagicMock()
    mock_client = AsyncMock()
    mock_client_ctx.__aenter__.return_value = mock_client

    with bridge_call(new=AsyncMock(return_value=staff_lyrics)), \
         patch("ai_score_editing.sibelius.runner.run_op", new=AsyncMock(return_value=0)) as mock_write:

        res = await _run_set_lyric(args)
        assert res == 0
        mock_write.assert_awaited_once()
        assert mock_write.await_args.args[1] == {
            "op": "set", "staff": 1, "bar": 2, "index": 0,
            "type": "LyricItem", "prop": "Text", "value": "\\fQuicksand\\\\s88\\hermosa",
        }


async def test_run_set_lyric_adopts_predominant_font_when_existing_is_outlier(cli_session: CliSession) -> None:
    from unittest.mock import AsyncMock, MagicMock, patch
    from ai_score_editing.sibelius.cli import build_parser
    from ai_score_editing.sibelius.commands.lyrics import _run_set_lyric

    parser = build_parser()
    args = parser.parse_args(["set-lyric", "--staff", "1", "--bar", "2", "--index", "0", "--text", "hermosa"])

    staff_lyrics = [
        {"staff": 1, "bar": 1, "index": 0, "text": "\\fQuicksand\\s88\\One"},
        {"staff": 1, "bar": 1, "index": 1, "text": "\\fQuicksand\\s88\\Two"},
        {"staff": 1, "bar": 1, "index": 2, "text": "\\fQuicksand\\s88\\Three"},
        {"staff": 1, "bar": 2, "index": 0, "text": "\\fPlantin\\s88\\ermosa"},
    ]

    mock_client_ctx = MagicMock()
    mock_client = AsyncMock()
    mock_client_ctx.__aenter__.return_value = mock_client

    with bridge_call(new=AsyncMock(return_value=staff_lyrics)), \
         patch("ai_score_editing.sibelius.runner.run_op", new=AsyncMock(return_value=0)) as mock_write:

        res = await _run_set_lyric(args)
        assert res == 0
        mock_write.assert_awaited_once()
        assert mock_write.await_args.args[1] == {
            "op": "set", "staff": 1, "bar": 2, "index": 0,
            "type": "LyricItem", "prop": "Text", "value": "\\fQuicksand\\\\s88\\hermosa",
        }


async def test_run_set_lyric_explicit_font_overrides_predominant() -> None:
    from unittest.mock import AsyncMock, patch
    from ai_score_editing.sibelius.cli import build_parser
    from ai_score_editing.sibelius.commands.lyrics import _run_set_lyric

    parser = build_parser()
    args = parser.parse_args([
        "set-lyric", "--staff", "1", "--bar", "2", "--index", "0", "--text", "hermosa",
        "--font", "Garamond", "--font-size", "96",
    ])

    with patch("ai_score_editing.sibelius.runner.run_op", new=AsyncMock(return_value=0)) as mock_write:
        res = await _run_set_lyric(args)
        assert res == 0
        mock_write.assert_awaited_once()
        assert mock_write.await_args.args[1] == {
            "op": "set", "staff": 1, "bar": 2, "index": 0,
            "type": "LyricItem", "prop": "Text", "value": "\\fGaramond\\\\s96\\hermosa",
        }


async def test_run_set_lyric_adopts_score_default_font_and_size_when_unstyled(cli_session: CliSession) -> None:
    from unittest.mock import AsyncMock, MagicMock, patch
    from ai_score_editing.sibelius.cli import build_parser
    from ai_score_editing.sibelius.commands.lyrics import _run_set_lyric

    parser = build_parser()
    args = parser.parse_args(["set-lyric", "--staff", "1", "--bar", "2", "--index", "0", "--text", "hermosa"])

    score_info = {"mainTextFontName": "Times New Roman"}
    staff_lyrics = [
        {"staff": 1, "bar": 1, "index": 0, "text": "One"},
        {"staff": 1, "bar": 1, "index": 1, "text": "Two"},
        {"staff": 1, "bar": 2, "index": 0, "text": "ermosa"},
    ]

    mock_client_ctx = MagicMock()
    mock_client = AsyncMock()
    mock_client_ctx.__aenter__.return_value = mock_client

    async def bridge_side_effect(client: Any, method: str, args: list[Any] | None = None) -> Any:
        if method == "GetScoreInfo":
            return score_info
        if method == "ReadLyrics":
            return staff_lyrics
        return None

    with bridge_call(side_effect=bridge_side_effect), \
         patch("ai_score_editing.sibelius.runner.run_op", new=AsyncMock(return_value=0)) as mock_write:

        res = await _run_set_lyric(args)
        assert res == 0
        # When unstyled, adopts score default font (Times New Roman) and standard 11pt size (110 tenths of a pt)
        mock_write.assert_awaited_once()
        assert mock_write.await_args.args[1] == {
            "op": "set", "staff": 1, "bar": 2, "index": 0,
            "type": "LyricItem", "prop": "Text", "value": "\\fTimes New Roman\\\\s110\\hermosa",
        }


async def test_run_set_barline() -> None:
    from unittest.mock import AsyncMock, patch
    from ai_score_editing.sibelius.cli import build_parser
    from ai_score_editing.sibelius.commands.layout import _run_set_barline

    parser = build_parser()
    args = parser.parse_args(["set-barline", "--bar", "71", "--type", "double"])

    with patch("ai_score_editing.sibelius.runner.run_op", new=AsyncMock(return_value=0)) as run_op:
        res = await _run_set_barline(args)
        assert res == 0
    assert run_op.await_args.args[1] == {"op": "set-barline", "bar": 71, "type": "double"}
    legacy = run_op.await_args.args[2]
    assert legacy({"after": {"bar": 71, "removed": 1, "barlineType": "-1"}}) == {
        "bar": 71, "deleted": 1, "barlineType": "7",
    }


async def test_run_read_barlines() -> None:
    from unittest.mock import AsyncMock, patch
    from ai_score_editing.sibelius.cli import build_parser
    from ai_score_editing.sibelius.commands.layout import _run_read_barlines

    parser = build_parser()
    args = parser.parse_args(["read-barlines", "--bars", "70-75"])

    with patch("ai_score_editing.sibelius.commands.layout._run_bridge_call", new=AsyncMock(return_value=0)) as mock_call:
        res = await _run_read_barlines(args)
        assert res == 0
        mock_call.assert_called_once_with(args, "GetSpecialBarlines", [70, 75])
