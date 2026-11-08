"""core.hidden_time and sibelius-cli hide-time-signatures, through the fake bridge."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from fakes import CliSession, bridge_apply_batch
from ai_score_editing.core import hidden_time
from ai_score_editing.core.errors import BatchError
from ai_score_editing.sibelius.cli import build_parser
from ai_score_editing.sibelius.commands._common import EXIT_COMMAND_FAILED, EXIT_OK
from ai_score_editing.sibelius.commands.hide_time_signatures import _run_hide_time_signatures

BACKUP = "ai_score_editing.sibelius.runner.backup"


def _time(hidden: bool, beats: int = 3) -> str:
    attr = ' print-object="no"' if hidden else ""
    return f"<attributes><time{attr}><beats>{beats}</beats><beat-type>2</beat-type></time></attributes>"


def _xml(parts: list[list[str]]) -> str:
    body = "".join(
        f'<part id="P{p}">' + "".join(f'<measure number="{i}">{m}</measure>' for i, m in enumerate(bars, 1)) + "</part>"
        for p, bars in enumerate(parts, 1)
    )
    return f"<score-partwise>{body}</score-partwise>"


def _ts(bar: int, index: int = 0, position: int = 0, hidden: bool = False) -> dict[str, Any]:
    return {"index": index, "type": "TimeSignature", "staff": 0, "bar": bar, "position": position,
            "fields": {"Hidden": hidden}}


# ---------------------------------------------------------------- pure helpers ---

def test_parse_bars() -> None:
    assert hidden_time.parse_bars("2-4, 7 9..10") == [2, 3, 4, 7, 9, 10]
    assert hidden_time.parse_bars("5,5,3") == [3, 5]
    for bad in ("", "0-3", "4-2", "a", "1-2-3"):
        with pytest.raises(BatchError):
            hidden_time.parse_bars(bad)


def test_compact_bars() -> None:
    assert hidden_time.compact_bars([1, 2, 3, 5, 7, 8]) == "1-3,5,7-8"
    assert hidden_time.compact_bars([]) == ""


def test_hidden_time_bars_any_part_hides_and_reports_mixed() -> None:
    root = ET.fromstring(_xml([
        [_time(True), "", _time(True), _time(False, 2)],
        [_time(False), "", _time(True), _time(False, 2)],
    ]))
    assert hidden_time.hidden_time_bars(root) == ([1, 3], [1])


def test_plan_hide_guards_skips_hidden_and_reports_missing() -> None:
    rows = [_ts(2, index=1, position=0), _ts(3, hidden=True), _ts(9),
            {"index": 0, "type": "SystemTextItem", "staff": 0, "bar": 4, "position": 0}]
    plan = hidden_time.plan_hide(rows, [2, 3, 4])
    assert plan.batch == [{"op": "set", "staff": 0, "bar": 2, "index": 1, "type": "TimeSignature",
                           "prop": "Hidden", "value": True, "position": 0}]
    assert (plan.hide, plan.already_hidden, plan.missing) == ([2], [3], [4])
    assert plan.summary() == {"hide": 1, "bars": "2", "alreadyHidden": "3", "noTimeSignature": "4"}


# --------------------------------------------------------------------- command ---

def _args(*argv: str) -> Any:
    return build_parser().parse_args(["hide-time-signatures", *argv])


async def test_dry_run_from_musicxml_checks_and_does_not_back_up(
    cli_session: CliSession, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    xml = tmp_path / "in.musicxml"
    xml.write_text(_xml([[_time(True), "", _time(True), _time(False, 2)]]))
    cli_session.client.replies["Query"] = {"objects": [_ts(1), _ts(3, index=2, position=0), _ts(4)]}
    with (
        patch(BACKUP, new=AsyncMock()) as backup,
        bridge_apply_batch(new=AsyncMock(return_value={"applied": 0, "dryRun": True})) as apply_batch,
    ):
        assert await _run_hide_time_signatures(_args("--musicxml", str(xml), "--dry-run")) == EXIT_OK
    backup.assert_not_awaited()
    assert [call.args[2] for call in apply_batch.await_args_list] == [True]
    sent = apply_batch.await_args.args[1]
    assert [(op["bar"], op["index"], op["prop"], op["value"]) for op in sent] == [(1, 0, "Hidden", True),
                                                                                 (3, 2, "Hidden", True)]
    selector = next(args for method, args in cli_session.client.calls if method == "Query")[0]
    assert selector["staves"] == [0] and selector["types"] == ["TimeSignature"]
    report = json.loads(capsys.readouterr().out)
    assert report["dryRun"] is True and report["bars"] == "1,3"


async def test_real_run_checks_backs_up_then_applies(
    cli_session: CliSession, capsys: pytest.CaptureFixture[str]
) -> None:
    cli_session.client.replies["Query"] = {"objects": [_ts(2), _ts(3), _ts(4, hidden=True)]}
    order: list[str] = []

    async def apply(_client: Any, ops: list[dict[str, Any]], dry_run: bool) -> dict[str, Any]:
        order.append("check" if dry_run else "apply")
        return {"applied": 0 if dry_run else len(ops), "results": []}

    async def backup(_client: Any, _name: str) -> dict[str, Any]:
        order.append("backup")
        return {"copy": "/b/a.sib"}

    with patch(BACKUP, new=backup), bridge_apply_batch(new=AsyncMock(side_effect=apply)):
        assert await _run_hide_time_signatures(_args("--bars", "2-5")) == EXIT_OK
    assert order == ["check", "backup", "apply"]
    report = json.loads(capsys.readouterr().out)
    assert report == {"hide": 2, "bars": "2-3", "alreadyHidden": "4", "noTimeSignature": "5",
                      "applied": 2, "backup": "/b/a.sib"}


async def test_nothing_to_hide_sends_no_batch(cli_session: CliSession, capsys: pytest.CaptureFixture[str]) -> None:
    cli_session.client.replies["Query"] = {"objects": [_ts(2, hidden=True)]}
    with bridge_apply_batch(new=AsyncMock()) as apply_batch:
        assert await _run_hide_time_signatures(_args("--bars", "2")) == EXIT_OK
    apply_batch.assert_not_awaited()
    assert json.loads(capsys.readouterr().out)["applied"] == 0


async def test_file_without_hidden_signatures_does_not_connect(
    cli_session: CliSession, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    xml = tmp_path / "in.xml"
    xml.write_text(_xml([[_time(False)]]))
    assert await _run_hide_time_signatures(_args("--musicxml", str(xml))) == EXIT_OK
    cli_session.context.__aenter__.assert_not_awaited()
    assert json.loads(capsys.readouterr().out)["hide"] == 0


async def test_refused_batch_changes_nothing(cli_session: CliSession, capsys: pytest.CaptureFixture[str]) -> None:
    cli_session.client.replies["Query"] = {"objects": [_ts(2)]}
    refused = {"error": "op 0: expected TimeSignature", "applied": 0}
    with patch(BACKUP, new=AsyncMock()) as backup, bridge_apply_batch(new=AsyncMock(return_value=refused)):
        assert await _run_hide_time_signatures(_args("--bars", "2")) == EXIT_COMMAND_FAILED
    backup.assert_not_awaited()
    assert "nothing was changed" in capsys.readouterr().err


async def test_bad_input_fails_before_connecting(
    cli_session: CliSession, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert await _run_hide_time_signatures(_args("--bars", "9-2")) == EXIT_COMMAND_FAILED
    assert await _run_hide_time_signatures(_args("--musicxml", str(tmp_path / "none.xml"))) == EXIT_COMMAND_FAILED
    cli_session.context.__aenter__.assert_not_awaited()
    assert "cannot read" in capsys.readouterr().err
