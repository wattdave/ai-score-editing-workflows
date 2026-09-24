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
    _run_score_snapshot,
    _run_patch_lyrics,
    _run_patch_layout,
    _run_apply,
    _run_patch_notes,
    _run_proofread,
    _run_verify_render,
    _run_read_lyrics,
    _run_reset_design,
    _run_set_lyric,
    _backup,
    _run_bracket,
    _run_set_time,
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


async def test_score_snapshot_combines_structural_reads_in_one_context(
    capsys: pytest.CaptureFixture[str],
) -> None:
    args = build_parser().parse_args(["score-snapshot", "--lyrics", "--bars", "2-3"])
    context, client = _client_context()

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
        patch("sibelius_websocket_cli.cli._client", return_value=context),
        patch("sibelius_websocket_cli.cli._check_bridge_version", new=AsyncMock()),
        patch("sibelius_websocket_cli.cli._bridge", side_effect=bridge_side_effect) as bridge,
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


async def test_patch_layout_uses_one_context_and_one_backup(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    patch_file = tmp_path / "layout.json"
    patch_file.write_text(
        '[{"op":"nudge","staff":1,"bar":4,"index":2,"dx":8},'
        '{"op":"set-barline","bar":20,"type":"end_repeat"}]'
    )
    args = build_parser().parse_args(["patch-layout", "--file", str(patch_file), "--save"])
    context, client = _client_context()

    async def bridge_side_effect(
        unused_client: Any, method: str, call_args: list[Any] | None = None
    ) -> Any:
        del unused_client, call_args
        if method == "Save":
            return {"fileName": "/scores/a.sib"}
        return {"changed": True}

    with (
        patch("sibelius_websocket_cli.cli._client", return_value=context),
        patch("sibelius_websocket_cli.cli._check_bridge_version", new=AsyncMock()),
        patch("sibelius_websocket_cli.cli._assert_expected_score", new=AsyncMock()),
        patch("sibelius_websocket_cli.cli._backup", new=AsyncMock(return_value={"copy": "/scores/a.backup.sib"})) as backup,
        patch("sibelius_websocket_cli.cli._bridge", side_effect=bridge_side_effect) as bridge,
    ):
        assert await _run_patch_layout(args) == EXIT_OK

    assert context.__aenter__.call_count == 1
    backup.assert_awaited_once()
    assert [call.args[1] for call in bridge.call_args_list] == [
        "NudgeObject", "SetSpecialBarline", "Save"
    ]
    output = capsys.readouterr().out.strip()
    assert '"operations":2' in output
    assert '"verified":2' in output


async def test_patch_layout_removes_redundant_clefs_from_installed_package(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    patch_file = tmp_path / "layout.json"
    patch_file.write_text('[{"op":"remove-redundant-clefs","staff":1}]')
    args = build_parser().parse_args(["patch-layout", "--file", str(patch_file)])
    context, _client = _client_context()
    deleted: list[list[Any]] = []

    async def bridge_side_effect(
        unused_client: Any, method: str, call_args: list[Any] | None = None
    ) -> Any:
        del unused_client
        if method == "GetScoreInfo":
            return {"staffCount": 1, "barCount": 1,
                    "timeSignatures": [{"bar": 1, "numerator": 2, "denominator": 4}]}
        if method == "GetStaves":
            return [{"staffNum": 1, "instrumentName": "Bass", "barCount": 1}]
        if method == "ReadBars":
            # Initial clefs are not bar objects, so only the courtesy clef shows.
            objects = [] if deleted else [
                {"type": "Clef", "index": 3, "position": 512, "styleId": "clef.treble"}
            ]
            return [{"barNumber": 1, "objects": objects}]
        if method == "DeleteObject":
            deleted.append(call_args or [])
            return {"deleted": True}
        raise AssertionError(f"unexpected bridge call {method}")

    with (
        patch("sibelius_websocket_cli.cli._client", return_value=context),
        patch("sibelius_websocket_cli.cli._check_bridge_version", new=AsyncMock()),
        patch("sibelius_websocket_cli.cli._assert_expected_score", new=AsyncMock()),
        patch("sibelius_websocket_cli.cli._backup", new=AsyncMock(return_value={"copy": "/scores/a.backup.sib"})),
        patch("sibelius_websocket_cli.cli._bridge", side_effect=bridge_side_effect),
    ):
        assert await _run_patch_layout(args) == EXIT_OK

    # The courtesy clef sits at the end of the 2/4 bar (tick 512).
    assert deleted == [[1, 1, 3]]
    assert '"verified":1' in capsys.readouterr().out


async def test_patch_notes_sends_one_batch_then_voice_deletes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    patch_file = tmp_path / "notes.json"
    patch_file.write_text(
        '[{"op":"delete","staff":1,"bar":4,"index":1},'
        '{"op":"delete-voice","staff":2,"fromBar":1,"toBar":2,"voice":2},'
        '{"op":"delete","staff":1,"bar":4,"index":3},'
        '{"op":"tie","staff":2,"bar":5,"index":0,"remove":true}]'
    )
    args = build_parser().parse_args(["patch-notes", "--file", str(patch_file), "--save"])
    context, _client = _client_context()

    async def bridge_side_effect(
        unused_client: Any, method: str, call_args: list[Any] | None = None
    ) -> Any:
        del unused_client, call_args
        if method == "Save":
            return {"fileName": "/scores/a.sib"}
        return {"changed": True}

    batch_result = {"applied": 3, "results": [{"i": 0}, {"i": 1}, {"i": 2}]}
    with (
        patch("sibelius_websocket_cli.cli._client", return_value=context),
        patch("sibelius_websocket_cli.cli._require_bridge", new=AsyncMock()),
        patch("sibelius_websocket_cli.cli._assert_expected_score", new=AsyncMock()),
        patch("sibelius_websocket_cli.cli._backup", new=AsyncMock(return_value={"copy": "/scores/a.backup.sib"})) as backup,
        patch("sibelius_websocket_cli.cli._apply_batch", new=AsyncMock(return_value=batch_result)) as apply_batch,
        patch("sibelius_websocket_cli.cli._bridge", side_effect=bridge_side_effect) as bridge,
    ):
        assert await _run_patch_notes(args) == EXIT_OK

    assert context.__aenter__.call_count == 1
    backup.assert_awaited_once()
    apply_batch.assert_awaited_once()
    batch, dry_run = apply_batch.await_args.args[1:]
    assert dry_run is False
    assert batch == [
        {"op": "tie", "staff": 2, "bar": 5, "index": 0, "tied": False},
        {"op": "delete", "staff": 1, "bar": 4, "index": 3},
        {"op": "delete", "staff": 1, "bar": 4, "index": 1},
    ]
    assert [(call.args[1], call.args[2] if len(call.args) > 2 else None) for call in bridge.call_args_list] == [
        ("DeleteVoiceInPassage", [1, 2, 2, 2]),
        ("Save", None),
    ]
    assert '"applied":4' in capsys.readouterr().out.strip()


async def test_apply_dry_run_skips_backup_and_save(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    batch_file = tmp_path / "ops.json"
    batch_file.write_text('[{"op":"set","staff":1,"bar":1,"index":0,"prop":"Dx","value":8}]')
    args = build_parser().parse_args(["apply", "--file", str(batch_file), "--dry-run", "--save"])
    context, _client = _client_context()
    result = {"applied": 0, "dryRun": True, "results": [{"i": 0, "op": "set"}]}
    with (
        patch("sibelius_websocket_cli.cli._client", return_value=context),
        patch("sibelius_websocket_cli.cli._require_bridge", new=AsyncMock()),
        patch("sibelius_websocket_cli.cli._assert_expected_score", new=AsyncMock()),
        patch("sibelius_websocket_cli.cli._backup", new=AsyncMock()) as backup,
        patch("sibelius_websocket_cli.cli._apply_batch", new=AsyncMock(return_value=result)) as apply_batch,
        patch("sibelius_websocket_cli.cli._bridge", new=AsyncMock()) as bridge,
    ):
        assert await _run_apply(args) == EXIT_OK

    backup.assert_not_awaited()
    bridge.assert_not_awaited()
    assert apply_batch.await_args.args[2] is True
    assert '"dryRun":true' in capsys.readouterr().out


async def test_apply_reports_partial_failure_with_undo_hint(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    batch_file = tmp_path / "ops.json"
    batch_file.write_text(
        '[{"op":"add-note","staff":1,"bar":1,"position":0,"duration":256,"pitches":[60]},'
        '{"op":"add-note","staff":1,"bar":1,"position":256,"duration":256,"pitches":[62]}]'
    )
    args = build_parser().parse_args(["apply", "--file", str(batch_file), "--save"])
    context, _client = _client_context()
    result = {"error": "op 1: Sibelius refused add-note", "applied": 1, "failedOp": 1}
    with (
        patch("sibelius_websocket_cli.cli._client", return_value=context),
        patch("sibelius_websocket_cli.cli._require_bridge", new=AsyncMock()),
        patch("sibelius_websocket_cli.cli._assert_expected_score", new=AsyncMock()),
        patch("sibelius_websocket_cli.cli._backup", new=AsyncMock(return_value={"copy": "/b.sib"})),
        patch(
            "sibelius_websocket_cli.cli._apply_batch",
            new=AsyncMock(side_effect=[{"applied": 0, "dryRun": True}, result]),
        ),
        patch("sibelius_websocket_cli.cli._bridge", new=AsyncMock()) as bridge,
    ):
        assert await _run_apply(args) == EXIT_COMMAND_FAILED

    bridge.assert_not_awaited()  # no save after a failed batch
    assert "invoke undo" in capsys.readouterr().err


async def test_apply_refused_batch_skips_backup(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    batch_file = tmp_path / "ops.json"
    batch_file.write_text('[{"op":"delete","staff":1,"bar":1,"index":99}]')
    args = build_parser().parse_args(["apply", "--file", str(batch_file)])
    context, _client = _client_context()
    refused = {"error": "op 0: no object at staff 1 bar 1 index 99", "applied": 0, "failedOp": 0}
    with (
        patch("sibelius_websocket_cli.cli._client", return_value=context),
        patch("sibelius_websocket_cli.cli._require_bridge", new=AsyncMock()),
        patch("sibelius_websocket_cli.cli._assert_expected_score", new=AsyncMock()),
        patch("sibelius_websocket_cli.cli._backup", new=AsyncMock()) as backup,
        patch("sibelius_websocket_cli.cli._apply_batch", new=AsyncMock(return_value=refused)) as apply_batch,
    ):
        assert await _run_apply(args) == EXIT_COMMAND_FAILED

    backup.assert_not_awaited()
    assert [call.args[2] for call in apply_batch.await_args_list] == [True]
    assert "nothing was changed" in capsys.readouterr().err


async def test_proofread_combines_reads_and_returns_compact_report(
    capsys: pytest.CaptureFixture[str],
) -> None:
    args = build_parser().parse_args(["proofread", "--bars", "2-3", "--lyrics"])
    context, _client = _client_context()

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
        patch("sibelius_websocket_cli.cli._client", return_value=context),
        patch("sibelius_websocket_cli.cli._check_bridge_version", new=AsyncMock()),
        patch("sibelius_websocket_cli.cli._bridge", side_effect=bridge_side_effect),
        patch("sibelius_websocket_cli.cli.lyrics.lint_lyrics", return_value=[]),
    ):
        assert await _run_proofread(args) == EXIT_OK

    output = capsys.readouterr().out.strip()
    assert '"errors":0' in output
    assert '"warnings":0' in output
    assert '"lyrics":[{"staff":1,"bar":2,"index":0,"position":0,"line":1,"text":"la"}]' in output


async def test_verify_render_exports_and_verifies_files(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output_path = tmp_path / "proof.png"
    args = build_parser().parse_args(
        ["verify-render", "--format", "png", "--out", str(output_path), "--expect-pages", "1", "--sha256"]
    )
    context, _client = _client_context()

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
        patch("sibelius_websocket_cli.cli._client", return_value=context),
        patch("sibelius_websocket_cli.cli._check_bridge_version", new=AsyncMock()),
        patch("sibelius_websocket_cli.cli._bridge", side_effect=bridge_side_effect) as bridge,
        patch("sibelius_websocket_cli.cli._assert_expected_score", new=AsyncMock()),
    ):
        assert await _run_verify_render(args) == EXIT_OK

    assert context.__aenter__.call_count == 1
    assert [call.args[1] for call in bridge.call_args_list] == ["GetScoreInfo", "ExportScore"]
    output = capsys.readouterr().out.strip()
    assert '"verified":true' in output
    assert '"pages":1' in output
    assert '"sha256"' in output


@pytest.mark.parametrize("pages", [1, 2])
async def test_verify_render_finds_files_when_out_has_no_extension(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], pages: int
) -> None:
    args = build_parser().parse_args(
        ["verify-render", "--format", "png", "--out", str(tmp_path / "proof"), "--expect-pages", str(pages)]
    )
    context, _client = _client_context()

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
        patch("sibelius_websocket_cli.cli._client", return_value=context),
        patch("sibelius_websocket_cli.cli._check_bridge_version", new=AsyncMock()),
        patch("sibelius_websocket_cli.cli._bridge", side_effect=bridge_side_effect),
        patch("sibelius_websocket_cli.cli._assert_expected_score", new=AsyncMock()),
    ):
        assert await _run_verify_render(args) == EXIT_OK

    output = capsys.readouterr().out
    assert '"verified":true' in output
    assert f'"pages":{pages}' in output


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


async def test_bracket_and_set_time_pass_string_booleans_to_bridge() -> None:
    parser = build_parser()

    bracket_args = parser.parse_args(["bracket", "--staff", "1", "--bar", "8", "--index", "1"])
    with patch("sibelius_websocket_cli.cli._run_write", new=AsyncMock(return_value=EXIT_OK)) as run_write:
        assert await _run_bracket(bracket_args) == EXIT_OK
        run_write.assert_awaited_once_with(bracket_args, "SetBracketed", [1, 8, 1, "true"])

    cut_args = parser.parse_args(["set-time", "--top", "2", "--bottom", "2", "--symbol", "cut"])
    with patch("sibelius_websocket_cli.cli._run_write", new=AsyncMock(return_value=EXIT_OK)) as run_write:
        assert await _run_set_time(cut_args) == EXIT_OK
        run_write.assert_awaited_once_with(cut_args, "SetTimeSignature", [1, 2, 2, "true"])


async def test_set_time_rejects_symbol_contradicting_meter() -> None:
    args = build_parser().parse_args(["set-time", "--top", "3", "--bottom", "4", "--symbol", "cut"])
    with patch("sibelius_websocket_cli.cli._run_write", new=AsyncMock()) as run_write:
        assert await _run_set_time(args) == EXIT_COMMAND_FAILED
        run_write.assert_not_awaited()


async def test_backup_refuses_imported_score_without_a_path() -> None:
    responses = {"AddVersion": {"ok": True}, "Save": {"fileName": "peace round"}}
    with patch(
        "sibelius_websocket_cli.cli._bridge",
        new=AsyncMock(side_effect=lambda _client, method, *_: responses[method]),
    ):
        with pytest.raises(BridgeError, match="never been saved as a .sib"):
            await _backup(MagicMock(), "before set-time")
