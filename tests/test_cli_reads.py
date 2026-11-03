"""CLI parser options and the combined read commands (inspect, snapshot, proofread, verify-render)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch
import pytest

from fakes import CliSession, bridge_call
from ai_score_editing.sibelius.cli import build_parser
from ai_score_editing.sibelius.commands._common import EXIT_OK
from ai_score_editing.sibelius.commands.audio import _run_verify_render
from ai_score_editing.sibelius.commands.inspect import _run_inspect, _run_proofread, _run_score_snapshot
from ai_score_editing.sibelius.commands.lyrics import _run_read_lyrics


def test_parser_accepts_agent_and_safety_options(tmp_path: Path) -> None:
    parser = build_parser()

    inspect_args = parser.parse_args(["--expect-file", "/scores/a.sib", "inspect"])
    assert inspect_args.subcommand == "inspect"
    assert inspect_args.expect_file == "/scores/a.sib"

    compact_args = parser.parse_args(["read-lyrics", "--compact", "--bars", "2-3"])
    assert compact_args.compact is True

    raw_args = parser.parse_args(
        [
            "set-lyric",
            "--staff",
            "1",
            "--bar",
            "2",
            "--index",
            "0",
            "--text",
            "la",
            "--raw",
            "--allow-style-reset",
        ]
    )
    assert raw_args.raw is True
    assert raw_args.allow_style_reset is True

    patch_file = tmp_path / "patches.json"
    batch_args = parser.parse_args(["patch-lyrics", "--file", str(patch_file)])
    assert batch_args.subcommand == "patch-lyrics"
    assert batch_args.file == str(patch_file)

    layout_args = parser.parse_args(["patch-layout", "--file", str(patch_file), "--dry-run"])
    assert layout_args.subcommand == "patch-layout"
    assert layout_args.dry_run is True

    snapshot_args = parser.parse_args(["score-snapshot", "--lyrics", "--bars", "2-3"])
    assert snapshot_args.subcommand == "score-snapshot"
    assert snapshot_args.lyrics is True
    assert snapshot_args.barlines is True

    proofread_args = parser.parse_args(["proofread", "--bars", "2-3", "--lyrics"])
    assert proofread_args.subcommand == "proofread"
    assert proofread_args.lyrics is True

    render_args = parser.parse_args(["verify-render", "--format", "png", "--expect-pages", "3"])
    assert render_args.subcommand == "verify-render"
    assert render_args.expect_pages == 3


async def test_inspect_combines_three_reads_in_one_context(cli_session: CliSession, capsys: pytest.CaptureFixture[str]) -> None:
    args = build_parser().parse_args(["inspect"])
    context, client = cli_session.context, cli_session.client

    async def bridge_side_effect(
        unused_client: Any, method: str, call_args: list[Any] | None = None
    ) -> Any:
        del unused_client, call_args
        return {
            "GetScoreInfo": {"fileName": "/scores/a.sib", "title": "A", "staffCount": 1, "barCount": 8},
            "GetStaves": [{"staffNum": 1, "fullInstrumentName": "Soprano"}],
            "GetSelectionInfo": {"isPassage": False},
        }[method]

    with (
        bridge_call(side_effect=bridge_side_effect) as bridge,
    ):
        assert await _run_inspect(args) == EXIT_OK

    assert context.__aenter__.call_count == 1
    assert [call.args[1] for call in bridge.call_args_list] == [
        "GetScoreInfo",
        "GetStaves",
        "GetSelectionInfo",
    ]
    assert capsys.readouterr().out.strip().startswith('{"fileName":"/scores/a.sib"')


async def test_score_snapshot_combines_structural_reads_in_one_context(cli_session: CliSession, 
    capsys: pytest.CaptureFixture[str],
) -> None:
    args = build_parser().parse_args(["score-snapshot", "--lyrics", "--bars", "2-3"])
    context, client = cli_session.context, cli_session.client

    async def bridge_side_effect(
        unused_client: Any, method: str, call_args: list[Any] | None = None
    ) -> Any:
        del unused_client
        if method == "GetScoreInfo":
            return {
                "fileName": "/scores/a.sib",
                "title": "A",
                "staffCount": 1,
                "barCount": 8,
                "keySignatures": [],
                "timeSignatures": [{"bar": 1, "numerator": 4, "denominator": 4}],
            }
        if method == "GetStaves":
            return [{"staffNum": 1, "fullInstrumentName": "Soprano"}]
        if method == "GetSelectionInfo":
            return {"isPassage": False}
        if method == "GetSpecialBarlines":
            assert call_args == [2, 3]
            return [{"bar": 2, "position": 1024, "type": "EndRepeat"}]
        if method == "ReadLyrics":
            assert call_args == [0, 2, 3]
            return [{"staff": 1, "bar": 2, "index": 0, "position": 0, "text": "la"}]
        raise AssertionError(method)

    with (
        bridge_call(side_effect=bridge_side_effect) as bridge,
    ):
        assert await _run_score_snapshot(args) == EXIT_OK

    assert context.__aenter__.call_count == 1
    assert [call.args[1] for call in bridge.call_args_list] == [
        "GetScoreInfo",
        "GetStaves",
        "GetSelectionInfo",
        "GetSpecialBarlines",
        "ReadLyrics",
    ]
    output = capsys.readouterr().out.strip()
    assert output.startswith('{"fileName":"/scores/a.sib"')
    assert '"barlines":[{"bar":2,"position":1024,"type":"EndRepeat"}]' in output
    assert '"lyrics":[{"staff":1,"bar":2,"index":0,"position":0,"text":"la"}]' in output


async def test_proofread_combines_reads_and_returns_compact_report(cli_session: CliSession, 
    capsys: pytest.CaptureFixture[str],
) -> None:
    args = build_parser().parse_args(["proofread", "--bars", "2-3", "--lyrics"])
    context, _client = cli_session.context, cli_session.client

    async def bridge_side_effect(
        unused_client: Any, method: str, call_args: list[Any] | None = None
    ) -> Any:
        del unused_client
        if method == "GetScoreInfo":
            return {
                "fileName": "/scores/a.sib",
                "title": "A",
                "staffCount": 1,
                "barCount": 8,
                "keySignatures": [],
                "timeSignatures": [{"bar": 1, "numerator": 4, "denominator": 4}],
                "mainTextFontName": "Plantin",
            }
        if method == "GetStaves":
            return [{"staffNum": 1, "fullInstrumentName": "Soprano"}]
        if method == "GetSelectionInfo":
            return {"isPassage": False}
        if method == "ReadLyrics":
            assert call_args == [0, 2, 3]
            return [{"staff": 1, "bar": 2, "index": 0, "position": 0, "text": "la"}]
        if method == "ReadBars":
            assert call_args == [1, 2, 3]
            return [{"barNumber": 2, "objects": []}]
        if method == "GetSpecialBarlines":
            assert call_args == [2, 3]
            return [{"bar": 2, "position": 1024, "type": "EndRepeat"}]
        raise AssertionError(method)

    with (
        bridge_call(side_effect=bridge_side_effect),
        patch("ai_score_editing.core.lyrics.lint_lyrics", return_value=[]),
    ):
        assert await _run_proofread(args) == EXIT_OK

    output = capsys.readouterr().out.strip()
    assert '"errors":0' in output
    assert '"warnings":0' in output
    assert '"lyrics":[{"staff":1,"bar":2,"index":0,"position":0,"line":1,"text":"la"}]' in output


async def test_verify_render_exports_and_verifies_files(cli_session: CliSession, 
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output_path = tmp_path / "proof.png"
    args = build_parser().parse_args(
        ["verify-render", "--format", "png", "--out", str(output_path), "--expect-pages", "1", "--sha256"]
    )
    context, _client = cli_session.context, cli_session.client

    async def bridge_side_effect(
        unused_client: Any, method: str, call_args: list[Any] | None = None
    ) -> Any:
        del unused_client, call_args
        if method == "GetScoreInfo":
            return {"fileName": "/scores/a.sib"}
        if method == "ExportScore":
            output_path.write_bytes(b"rendered")
            return {"exportedTo": str(output_path)}
        raise AssertionError(method)

    with (
        bridge_call(side_effect=bridge_side_effect) as bridge,
    ):
        assert await _run_verify_render(args) == EXIT_OK

    assert context.__aenter__.call_count == 1
    assert [call.args[1] for call in bridge.call_args_list] == ["GetScoreInfo", "ExportScore"]
    output = capsys.readouterr().out.strip()
    assert '"verified":true' in output
    assert '"pages":1' in output
    assert '"sha256"' in output


@pytest.mark.parametrize("pages", [1, 2])
async def test_verify_render_finds_files_when_out_has_no_extension(cli_session: CliSession, 
    tmp_path: Path, capsys: pytest.CaptureFixture[str], pages: int
) -> None:
    args = build_parser().parse_args(
        ["verify-render", "--format", "png", "--out", str(tmp_path / "proof"), "--expect-pages", str(pages)]
    )
    context, _client = cli_session.context, cli_session.client

    async def bridge_side_effect(
        unused_client: Any, method: str, call_args: list[Any] | None = None
    ) -> Any:
        del unused_client
        if method == "GetScoreInfo":
            return {"fileName": "/scores/a.sib"}
        if method == "ExportScore":
            # Mimic Sibelius: add the extension, and page suffixes for multi-page images.
            target = Path((call_args or [""])[0])
            stem = target.name.removesuffix(".png")
            names = [f"{stem}.png"] if pages == 1 else [f"{stem}_{i:04d}.png" for i in range(1, pages + 1)]
            for name in names:
                (target.parent / name).write_bytes(b"rendered")
            return {"exportedTo": str(target)}
        raise AssertionError(method)

    with (
        bridge_call(side_effect=bridge_side_effect),
    ):
        assert await _run_verify_render(args) == EXIT_OK

    output = capsys.readouterr().out
    assert '"verified":true' in output
    assert f'"pages":{pages}' in output


async def test_compact_read_lyrics_keeps_edit_address(cli_session: CliSession, capsys: pytest.CaptureFixture[str]) -> None:
    args = build_parser().parse_args(["read-lyrics", "--compact", "--staff", "1"])
    context, _client = cli_session.context, cli_session.client
    payload = [
        {
            "staff": 1,
            "bar": 2,
            "index": 3,
            "position": 256,
            "voice": 1,
            "text": "Hal-",
            "syllableType": "middle",
            "styleAsText": "Lyrics line 1",
        }
    ]
    with (
        bridge_call(new=AsyncMock(return_value=payload)),
    ):
        assert await _run_read_lyrics(args) == EXIT_OK

    assert capsys.readouterr().out.strip() == 'S1 B2 I3 P256 V1 L1 "Hal-"'
