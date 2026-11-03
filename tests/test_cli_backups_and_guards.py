"""CLI safety: backups, expected-score checks and the legacy run_op path."""

from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from fakes import CliSession, bridge_apply_batch, bridge_call
from ai_score_editing.sibelius import runner
from ai_score_editing.sibelius.bridge import BridgeError
from ai_score_editing.sibelius.cli import build_parser
from ai_score_editing.sibelius.commands._common import EXIT_COMMAND_FAILED, EXIT_OK
from ai_score_editing.sibelius.commands.layout import _run_reset_design
from ai_score_editing.sibelius.commands.lyrics import _run_set_lyric
from ai_score_editing.sibelius.commands.notes import _run_flip_stem, _run_set_note


async def test_expected_score_mismatch_fails() -> None:
    args = Namespace(expect_file="/scores/expected.sib")
    with pytest.raises(BridgeError, match="active score mismatch"):
        await runner.assert_expected_score(
            AsyncMock(), args, {"fileName": "/scores/other.sib"}
        )


async def test_expected_score_failure_prevents_backup_and_write(cli_session: CliSession) -> None:
    args = build_parser().parse_args(
        ["--expect-file", "/scores/a.sib", "set-key", "--key", "D"]
    )
    context, _client = cli_session.context, cli_session.client
    with (
        patch(
            "ai_score_editing.sibelius.runner.assert_expected_score",
            new=AsyncMock(side_effect=BridgeError("active score mismatch")),
        ),
        patch("ai_score_editing.sibelius.runner.backup", new=AsyncMock()) as backup,
        bridge_call(new=AsyncMock()) as bridge,
    ):
        with pytest.raises(BridgeError, match="active score mismatch"):
            await runner.run_write(args, "SetStaffName", [1, "Flute", "Fl."])

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
    with patch("ai_score_editing.sibelius.runner.run_write", new=AsyncMock()) as write:
        assert await _run_set_lyric(args) == EXIT_COMMAND_FAILED
    write.assert_not_awaited()
    assert "--allow-style-reset" in capsys.readouterr().err


async def test_reset_design_backs_up_before_mutation(cli_session: CliSession) -> None:
    args = build_parser().parse_args(["reset-design", "--lyrics"])
    context, client = cli_session.context, AsyncMock()  # bespoke: records invoke_commands
    context.__aenter__.return_value = client
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
        patch("ai_score_editing.sibelius.runner.backup", side_effect=backup_side_effect),
    ):
        assert await _run_reset_design(args) == EXIT_OK

    assert events == ["backup", "mutate"]


async def test_backup_refuses_imported_score_without_a_path() -> None:
    responses = {"AddVersion": {"ok": True}, "Save": {"fileName": "peace round"}}
    with bridge_call(new=AsyncMock(side_effect=lambda _client, method, *_: responses[method]),
    ):
        with pytest.raises(BridgeError, match="never been saved as a .sib"):
            await runner.backup(MagicMock(), "before set-time")


async def test_backup_goes_beside_the_score_by_default(tmp_path: Path) -> None:
    score = tmp_path / "song.sib"
    score.write_bytes(b"sib")
    responses = {"AddVersion": {"ok": True}, "Save": {"fileName": str(score)}}
    with bridge_call(new=AsyncMock(side_effect=lambda _client, method, *_: responses[method]),
    ):
        result = await runner.backup(MagicMock(), "before set-time")
    assert Path(result["copy"]).parent == tmp_path
    assert Path(result["copy"]).read_bytes() == b"sib"


async def test_backup_dir_collects_backups_in_one_folder(tmp_path: Path) -> None:
    score = tmp_path / "song.sib"
    score.write_bytes(b"sib")
    folder = tmp_path / "backups" / "nested"
    responses = {"AddVersion": {"ok": True}, "Save": {"fileName": str(score)}}
    with patch.dict("os.environ", {"SIBELIUS_BACKUP_DIR": str(folder)}), bridge_call(new=AsyncMock(side_effect=lambda _client, method, *_: responses[method]),
    ):
        result = await runner.backup(MagicMock(), "before set-time")
    assert Path(result["copy"]).parent == folder
    assert Path(result["copy"]).name.startswith("song.backup-")
    assert not list(tmp_path.glob("*.backup-*"))


def test_backup_dir_option_and_environment_set_the_folder(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from ai_score_editing.sibelius import cli, service
    from ai_score_editing.sibelius.commands import connection

    monkeypatch.setattr(connection, "_run_ping", AsyncMock(return_value=EXIT_OK), raising=True)
    monkeypatch.setenv("SIBELIUS_BACKUP_DIR", str(tmp_path / "env"))
    cli.main(["ping"])
    assert service.backup_folder() == tmp_path / "env"
    cli.main(["--backup-dir", str(tmp_path / "flag"), "ping"])
    assert service.backup_folder() == tmp_path / "flag"
    monkeypatch.delenv("SIBELIUS_BACKUP_DIR")
    assert service.backup_folder() is None


async def test_run_op_checks_before_backup_and_prints_legacy_output(cli_session: CliSession, 
    capsys: pytest.CaptureFixture[str],
) -> None:
    args = build_parser().parse_args(
        ["set-note", "--staff", "1", "--bar", "2", "--index", "0", "--old-pitch", "76", "--new-pitch", "75"]
    )
    before = {"type": "NoteRest", "notes": [{"pitch": 76, "name": "E", "tied": True}]}
    after = {"type": "NoteRest", "notes": [{"pitch": 75, "name": "Eb", "tied": True}]}
    replies = [
        {"applied": 0, "dryRun": True, "results": [{"i": 0, "before": before}]},
        {"applied": 1, "results": [{"i": 0, "op": "set-pitch", "before": before, "after": after}]},
    ]
    context, _client = cli_session.context, cli_session.client
    with (
        patch("ai_score_editing.sibelius.runner.backup", new=AsyncMock(return_value={"copy": "/b.sib"})) as backup,
        bridge_apply_batch(new=AsyncMock(side_effect=replies)) as apply_batch,
    ):
        assert await _run_set_note(args) == EXIT_OK

    backup.assert_awaited_once()
    assert [call.args[2] for call in apply_batch.await_args_list] == [True, False]
    assert json.loads(capsys.readouterr().out) == {
        "oldPitch": 76, "oldName": "E", "newPitch": 75, "newName": "Eb", "tied": True,
    }


async def test_run_op_refused_edit_skips_backup(cli_session: CliSession) -> None:
    args = build_parser().parse_args(["flip-stem", "--staff", "1", "--bar", "1", "--index", "9"])
    context, _client = cli_session.context, cli_session.client
    refused = {"error": "op 0: no object at staff 1 bar 1 index 9", "applied": 0}
    with (
        patch("ai_score_editing.sibelius.runner.backup", new=AsyncMock()) as backup,
        bridge_apply_batch(new=AsyncMock(return_value=refused)),
        pytest.raises(BridgeError, match="index 9"),
    ):
        await _run_flip_stem(args)
    backup.assert_not_awaited()
