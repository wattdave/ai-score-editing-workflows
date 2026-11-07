"""sibelius-cli auto-layout and the set-layout-last rule in apply, through the fake bridge."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from fakes import CliSession, FakeSibeliusClient, bridge_apply_batch
from ai_score_editing.sibelius import bridge, service
from ai_score_editing.sibelius.cli import build_parser
from ai_score_editing.sibelius.commands._common import EXIT_COMMAND_FAILED, EXIT_OK
from ai_score_editing.sibelius.commands.auto_layout import UNLOCK_FORMAT, _run_auto_layout
from ai_score_editing.sibelius.commands.score import _run_apply

BACKUP = "ai_score_editing.sibelius.runner.backup"


def _args(*argv: str) -> Any:
    return build_parser().parse_args(["auto-layout", *argv])


def _bar_rows(where: list[tuple[int, int]]) -> dict[str, Any]:
    return {"objects": [
        {"index": 0, "type": "Bar", "staff": 0, "bar": i + 1, "fields": {"OnNthPage": p, "OnNthSystem": s}}
        for i, (p, s) in enumerate(where)
    ]}


async def test_out_writes_an_apply_batch_without_connecting(
    cli_session: CliSession, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "layout.json"
    args = _args("--systems", "1,5/9", "--verses", "4", "--staves", "2", "--hide-empty", "5-8", "--out", str(out))
    assert await _run_auto_layout(args) == EXIT_OK
    cli_session.context.__aenter__.assert_not_awaited()
    batch = json.loads(out.read_text())
    assert batch == [
        {"op": "set-break", "bar": 4, "type": "system"},
        {"op": "set-break", "bar": 8, "type": "page"},
        {"op": "hide-empty-staves", "fromBar": 5, "toBar": 8},
        {"op": "set-layout", "staffSize": 5.5, "spacesBetweenStaves": 17, "spacesBetweenSystems": 9,
         "aboveTopStaveGap": 24},
    ]
    report = json.loads(capsys.readouterr().out)
    assert report["next"][0] == "sibelius-cli invoke " + " ".join(UNLOCK_FORMAT)


async def test_out_needs_staves(cli_session: CliSession, capsys: pytest.CaptureFixture[str]) -> None:
    assert await _run_auto_layout(_args("--systems", "1,5", "--verses", "2", "--out", "-")) == EXIT_COMMAND_FAILED
    assert "--staves" in capsys.readouterr().err


async def test_dry_run_checks_and_neither_unlocks_nor_backs_up(
    cli_session: CliSession, capsys: pytest.CaptureFixture[str]
) -> None:
    cli_session.client.replies["GetStaves"] = [{"staffNum": 1}, {"staffNum": 2}, {"staffNum": 3}, {"staffNum": 4}]
    with (
        patch(BACKUP, new=AsyncMock()) as backup,
        bridge_apply_batch(new=AsyncMock(return_value={"applied": 0, "dryRun": True})) as apply_batch,
    ):
        assert await _run_auto_layout(_args("--systems", "1,5", "--verses", "3", "--dry-run")) == EXIT_OK
    backup.assert_not_awaited()
    assert [call.args[2] for call in apply_batch.await_args_list] == [True]
    assert "invokeCommands" not in cli_session.client.methods()
    report = json.loads(capsys.readouterr().out)
    assert report["dryRun"] is True and report["preset"] == "4+ staves"


async def test_real_run_backs_up_unlocks_applies_and_verifies(
    cli_session: CliSession, capsys: pytest.CaptureFixture[str]
) -> None:
    client = cli_session.client
    client.replies["Query"] = _bar_rows([(1, 1), (1, 1), (1, 2), (1, 2), (2, 3), (2, 3)])
    order: list[str] = []
    real_invoke = client.invoke_commands

    async def invoke(commands: list[str]) -> dict[str, Any]:
        order.append("unlock")
        return await real_invoke(commands)

    client.invoke_commands = invoke  # type: ignore[method-assign]

    async def apply(_client: Any, ops: list[dict[str, Any]], dry_run: bool) -> dict[str, Any]:
        order.append("check" if dry_run else "apply")
        return {"applied": 0 if dry_run else len(ops), "results": []}

    async def backup(_client: Any, _name: str) -> dict[str, Any]:
        order.append("backup")
        return {"copy": "/b/a.sib"}

    args = _args("--systems", "1,3/5", "--verses", "2", "--staves", "2", "--verify")
    with patch(BACKUP, new=backup), bridge_apply_batch(new=AsyncMock(side_effect=apply)):
        assert await _run_auto_layout(args) == EXIT_OK
    assert order == ["check", "backup", "unlock", "apply"]
    assert ("invokeCommands", UNLOCK_FORMAT) in client.calls
    report = json.loads(capsys.readouterr().out)
    assert report["verify"] == {"verified": True, "systemStarts": [[1, 3], [5]]}
    assert report["backup"] == "/b/a.sib"


async def test_verify_mismatch_fails(cli_session: CliSession, capsys: pytest.CaptureFixture[str]) -> None:
    cli_session.client.replies["Query"] = _bar_rows([(1, 1), (1, 1), (1, 1), (1, 1), (2, 2), (2, 2)])
    args = _args("--systems", "1,3/5", "--verses", "2", "--staves", "2", "--verify", "--no-unlock-format")
    with (
        patch(BACKUP, new=AsyncMock(return_value={"copy": "/b.sib"})),
        bridge_apply_batch(new=AsyncMock(return_value={"applied": 3, "results": []})),
    ):
        assert await _run_auto_layout(args) == EXIT_COMMAND_FAILED
    assert "invokeCommands" not in cli_session.client.methods()
    report = json.loads(capsys.readouterr().out)
    assert report["verify"]["errors"] == ["page 1: systems start at bars [1], expected [1, 3]"]


async def test_refused_batch_changes_nothing(cli_session: CliSession, capsys: pytest.CaptureFixture[str]) -> None:
    refused = {"error": "op 0: bar 99 is outside the score", "applied": 0}
    with (
        patch(BACKUP, new=AsyncMock()) as backup,
        bridge_apply_batch(new=AsyncMock(return_value=refused)),
    ):
        assert await _run_auto_layout(_args("--systems", "1,100", "--verses", "2", "--staves", "2")) == EXIT_COMMAND_FAILED
    backup.assert_not_awaited()
    assert "invokeCommands" not in cli_session.client.methods()
    assert "nothing was changed" in capsys.readouterr().err


async def test_ready_json_with_pickup(cli_session: CliSession, tmp_path: Path) -> None:
    ready = tmp_path / "ready.json"
    ready.write_text(json.dumps({
        "bars": "pickup + 19 bars", "breaks": {"system_starts_at_measures": [5, 10]}, "page_breaks": [],
    }))
    out = tmp_path / "b.json"
    args = _args("--ready", str(ready), "--verses", "4", "--staves", "2", "--out", str(out))
    assert await _run_auto_layout(args) == EXIT_OK
    assert [op["bar"] for op in json.loads(out.read_text()) if op["op"] == "set-break"] == [5, 10]
    args = _args("--ready", str(ready), "--verses", "4", "--staves", "2", "--no-pickup", "--out", str(out))
    assert await _run_auto_layout(args) == EXIT_OK
    assert [op["bar"] for op in json.loads(out.read_text()) if op["op"] == "set-break"] == [4, 9]


async def test_apply_moves_set_layout_last_and_warns(
    cli_session: CliSession, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    batch_file = tmp_path / "ops.json"
    batch_file.write_text(json.dumps([
        {"op": "set-layout", "staffSize": 6},
        {"op": "set-break", "bar": 4, "type": "system"},
    ]))
    args = build_parser().parse_args(["apply", "--file", str(batch_file), "--dry-run"])
    with bridge_apply_batch(new=AsyncMock(return_value={"applied": 0, "dryRun": True})) as apply_batch:
        assert await _run_apply(args) == EXIT_OK
    assert [op["op"] for op in apply_batch.await_args.args[1]] == ["set-break", "set-layout"]
    assert "set-layout (op 0) was not last" in capsys.readouterr().err


async def test_service_apply_reports_the_move_under_warnings() -> None:
    client = FakeSibeliusClient({"GetBridgeVersion": {"version": 63}, "ApplyBatch": {"applied": 0, "dryRun": True}})
    result = await service.apply(
        bridge.SibeliusBridge(client),  # type: ignore[arg-type]
        [{"op": "set-layout", "staffSize": 6}, {"op": "set-break", "bar": 4, "type": "system"}],
        dry_run=True,
    )
    sent = next(args for method, args in client.calls if method == "ApplyBatch")[0]
    assert [op["op"] for op in sent] == ["set-break", "set-layout"]
    assert "not last" in result["warnings"][0]
