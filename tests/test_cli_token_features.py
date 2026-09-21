"""CLI coverage for compact output and mechanically enforced write safety."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sibelius_websocket_cli.cli import (
    EXIT_COMMAND_FAILED,
    EXIT_OK,
    BridgeError,
    _assert_expected_score,
    _run_inspect,
    _run_patch_lyrics,
    _run_read_lyrics,
    _run_reset_design,
    _run_set_lyric,
    _run_tie,
    _run_write,
    build_parser,
)


def _client_context() -> tuple[MagicMock, AsyncMock]:
    context = MagicMock()
    client = AsyncMock()
    context.__aenter__.return_value = client
    return context, client


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


async def test_inspect_combines_three_reads_in_one_context(capsys: pytest.CaptureFixture[str]) -> None:
    args = build_parser().parse_args(["inspect"])
    context, client = _client_context()

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
        patch("sibelius_websocket_cli.cli._client", return_value=context),
        patch("sibelius_websocket_cli.cli._check_bridge_version", new=AsyncMock()),
        patch("sibelius_websocket_cli.cli._bridge", side_effect=bridge_side_effect) as bridge,
    ):
        assert await _run_inspect(args) == EXIT_OK

    assert context.__aenter__.call_count == 1
    assert [call.args[1] for call in bridge.call_args_list] == [
        "GetScoreInfo",
        "GetStaves",
        "GetSelectionInfo",
    ]
    assert capsys.readouterr().out.strip().startswith('{"fileName":"/scores/a.sib"')


async def test_compact_read_lyrics_keeps_edit_address(capsys: pytest.CaptureFixture[str]) -> None:
    args = build_parser().parse_args(["read-lyrics", "--compact", "--staff", "1"])
    context, _client = _client_context()
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
        patch("sibelius_websocket_cli.cli._client", return_value=context),
        patch("sibelius_websocket_cli.cli._bridge", new=AsyncMock(return_value=payload)),
    ):
        assert await _run_read_lyrics(args) == EXIT_OK

    assert capsys.readouterr().out.strip() == 'S1 B2 I3 P256 V1 L1 "Hal-"'


async def test_expected_score_mismatch_fails() -> None:
    args = Namespace(expect_file="/scores/expected.sib")
    with pytest.raises(BridgeError, match="active score mismatch"):
        await _assert_expected_score(
            AsyncMock(), args, {"fileName": "/scores/other.sib"}
        )


async def test_expected_score_failure_prevents_backup_and_write() -> None:
    args = build_parser().parse_args(
        ["--expect-file", "/scores/a.sib", "set-key", "--key", "D"]
    )
    context, _client = _client_context()
    with (
        patch("sibelius_websocket_cli.cli._client", return_value=context),
        patch("sibelius_websocket_cli.cli._check_bridge_version", new=AsyncMock()),
        patch(
            "sibelius_websocket_cli.cli._assert_expected_score",
            new=AsyncMock(side_effect=BridgeError("active score mismatch")),
        ),
        patch("sibelius_websocket_cli.cli._backup", new=AsyncMock()) as backup,
        patch("sibelius_websocket_cli.cli._bridge", new=AsyncMock()) as bridge,
    ):
        with pytest.raises(BridgeError, match="active score mismatch"):
            await _run_write(args, "SetKeySignature", [1, "D", True])

    backup.assert_not_awaited()
    bridge.assert_not_awaited()


async def test_raw_lyric_requires_style_reset_acknowledgement(
    capsys: pytest.CaptureFixture[str],
) -> None:
    args = build_parser().parse_args(
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
        ]
    )
    with patch("sibelius_websocket_cli.cli._run_write", new=AsyncMock()) as write:
        assert await _run_set_lyric(args) == EXIT_COMMAND_FAILED
    write.assert_not_awaited()
    assert "--allow-style-reset" in capsys.readouterr().err


async def test_reset_design_backs_up_before_mutation() -> None:
    args = build_parser().parse_args(["reset-design", "--lyrics"])
    context, client = _client_context()
    events: list[str] = []

    async def backup_side_effect(*unused: Any) -> dict[str, Any]:
        events.append("backup")
        return {"copy": "/scores/a.backup.sib"}

    async def invoke_side_effect(commands: list[str]) -> dict[str, Any]:
        del commands
        events.append("mutate")
        return {"result": True}

    client.invoke_commands.side_effect = invoke_side_effect
    with (
        patch("sibelius_websocket_cli.cli._client", return_value=context),
        patch("sibelius_websocket_cli.cli._check_bridge_version", new=AsyncMock()),
        patch("sibelius_websocket_cli.cli._assert_expected_score", new=AsyncMock()),
        patch("sibelius_websocket_cli.cli._backup", side_effect=backup_side_effect),
    ):
        assert await _run_reset_design(args) == EXIT_OK

    assert events == ["backup", "mutate"]


async def test_patch_lyrics_uses_one_connection_backup_and_verification(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    patch_file = tmp_path / "patches.json"
    patch_file.write_text(
        '[{"staff":1,"bar":2,"index":0,"text":"glo-"},'
        '{"staff":1,"bar":2,"index":2,"text":"ry"}]'
    )
    args = build_parser().parse_args(
        [
            "patch-lyrics",
            "--file",
            str(patch_file),
            "--font",
            "Plantin",
            "--font-size",
            "95",
            "--save",
        ]
    )
    context, _client = _client_context()
    reads = 0

    async def bridge_side_effect(
        unused_client: Any, method: str, call_args: list[Any] | None = None
    ) -> Any:
        nonlocal reads
        del unused_client
        if method == "ReadLyrics":
            reads += 1
            texts = ("old-a", "old-b") if reads == 1 else ("glo-", "ry")
            return [
                {"staff": 1, "bar": 2, "index": 0, "text": texts[0]},
                {"staff": 1, "bar": 2, "index": 2, "text": texts[1]},
            ]
        if method == "SetLyricText":
            assert call_args is not None
            return {"oldText": "old", "newText": call_args[-1]}
        if method == "Save":
            return {"fileName": "/scores/a.sib"}
        raise AssertionError(method)

    with (
        patch("sibelius_websocket_cli.cli._client", return_value=context),
        patch("sibelius_websocket_cli.cli._check_bridge_version", new=AsyncMock()),
        patch("sibelius_websocket_cli.cli._assert_expected_score", new=AsyncMock()),
        patch(
            "sibelius_websocket_cli.cli._backup",
            new=AsyncMock(return_value={"copy": "/scores/a.backup.sib"}),
        ) as backup,
        patch("sibelius_websocket_cli.cli._bridge", side_effect=bridge_side_effect) as bridge,
    ):
        assert await _run_patch_lyrics(args) == EXIT_OK

    assert context.__aenter__.call_count == 1
    backup.assert_awaited_once()
    write_calls = [call for call in bridge.call_args_list if call.args[1] == "SetLyricText"]
    assert [call.args[2] for call in write_calls] == [
        [1, 2, 0, "\\fPlantin\\\\s95\\glo-"],
        [1, 2, 2, "\\fPlantin\\\\s95\\ry"],
    ]
    assert reads == 2
    output = capsys.readouterr().out
    assert "patched 2; verified 2/2" in output
    assert "saved /scores/a.sib" in output


async def test_tie_passes_string_booleans_to_bridge() -> None:
    parser = build_parser()

    # Test tie add passes "true"
    tie_args = parser.parse_args(["tie", "--staff", "1", "--bar", "2", "--index", "3"])
    with patch("sibelius_websocket_cli.cli._run_write", new=AsyncMock(return_value=EXIT_OK)) as run_write:
        assert await _run_tie(tie_args) == EXIT_OK
        run_write.assert_awaited_once_with(
            tie_args, "SetTie", [1, 2, 3, "true"]
        )

    # Test tie remove passes "false"
    untie_args = parser.parse_args(["tie", "--staff", "1", "--bar", "2", "--index", "3", "--remove"])
    with patch("sibelius_websocket_cli.cli._run_write", new=AsyncMock(return_value=EXIT_OK)) as run_write:
        assert await _run_tie(untie_args) == EXIT_OK
        run_write.assert_awaited_once_with(
            untie_args, "SetTie", [1, 2, 3, "false"]
        )

