"""set-layout's Auto-Respace / Auto-Optimize switches (bridge v65): plug-in, schema, gate, CLI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from ai_score_editing.core import batch_schema
from ai_score_editing.core.errors import BatchError
from ai_score_editing.sibelius import batch_ops, bridge, service
from ai_score_editing.sibelius.bridge import BridgeError
from ai_score_editing.sibelius.cli import build_parser
from ai_score_editing.sibelius.commands._common import EXIT_OK
from ai_score_editing.sibelius.commands.auto_layout import _run_auto_layout
from fakes import CliSession, FakeSibeliusClient, bridge_apply_batch

PLUGIN = Path(__file__).resolve().parents[1] / "src/ai_score_editing/sibelius/manuscript/ScoreBridge.plg"
BACKUP = "ai_score_editing.sibelius.runner.backup"


def _function(source: str, name: str) -> str:
    start = source.index(f'\t{name} "(')
    return source[start:source.index('}"\n', start)]


def test_layout_read_reports_both_switches() -> None:
    body = _function(PLUGIN.read_text(), "LayoutRead")
    # Exact spelling: an unknown property name raises a modal "Cannot get field" dialog.
    assert "'autoRespace', score.AutoRespaceEnabled" in body
    assert "'autoOptimize', score.AutoOptimizeEnabled" in body


def test_set_layout_writes_switches_by_name_and_first() -> None:
    body = _function(PLUGIN.read_text(), "BatchSetLayout")
    for field, prop in batch_schema.LAYOUT_SWITCHES.items():
        assert f"BatchHasSetting(op, '{field}')" in body
        assert f"score.{prop} = True;" in body
        assert f"score.{prop} = False;" in body
        assert body.index(f"BatchHasSetting(op, '{field}')") < body.index("BatchHasSetting(op, 'pageSize')")


def test_switch_properties_appear_only_in_layout_functions() -> None:
    source = PLUGIN.read_text()
    outside = source.replace(_function(source, "LayoutRead"), "").replace(_function(source, "BatchSetLayout"), "")
    for prop in batch_schema.LAYOUT_SWITCHES.values():
        assert prop not in outside


def test_plugin_version_is_current_and_gates_switches() -> None:
    assert f"CreateDictionary('version', {bridge.CURRENT_BRIDGE_VERSION})" in PLUGIN.read_text()
    assert bridge.LAYOUT_SWITCHES_BRIDGE_VERSION == 65 <= bridge.CURRENT_BRIDGE_VERSION


def test_switches_validate_into_settings() -> None:
    [op] = batch_ops.validate_batch([{"op": "set-layout", "autoRespace": False, "autoOptimize": True, "staffSize": 6}])
    assert op["autoRespace"] is False and op["autoOptimize"] is True
    assert set(op["settings"]) == {"staffSize", "autoRespace", "autoOptimize"}
    assert op["settings"] == [k for k in op if k not in ("op", "settings")]


def test_a_false_switch_alone_is_a_setting() -> None:
    [op] = batch_ops.validate_batch([{"op": "set-layout", "autoOptimize": False}])
    assert op["settings"] == ["autoOptimize"]


@pytest.mark.parametrize("field", list(batch_schema.LAYOUT_SWITCHES))
@pytest.mark.parametrize("value", [1, 0, "off", None])
def test_switches_must_be_booleans(field: str, value: Any) -> None:
    with pytest.raises(BatchError, match=f"{field} must be true or false"):
        batch_ops.validate_batch([{"op": "set-layout", field: value}])


def test_bridge_gate() -> None:
    switch = batch_ops.validate_batch([{"op": "set-layout", "autoRespace": True}])
    plain = batch_ops.validate_batch([{"op": "set-layout", "staffSize": 6}])
    assert bridge.batch_bridge_version(switch) == bridge.LAYOUT_SWITCHES_BRIDGE_VERSION
    assert bridge.batch_bridge_version(plain) == bridge.LAYOUT_BATCH_BRIDGE_VERSION
    mixed = batch_ops.validate_batch([
        {"op": "hide-empty-staves", "fromBar": 1, "toBar": 2},
        {"op": "set-layout", "autoOptimize": False},
    ])
    assert bridge.batch_bridge_version(mixed) == bridge.LAYOUT_SWITCHES_BRIDGE_VERSION


def test_name_structure_turns_switches_into_booleans() -> None:
    named = batch_schema.name_structure({"layout": {"pageSize": 4, "orientation": 0, "autoRespace": 1, "autoOptimize": 0}})
    assert named["layout"]["autoRespace"] is True and named["layout"]["autoOptimize"] is False
    older = batch_schema.name_structure({"layout": {"pageSize": 4, "orientation": 0}})
    assert "autoRespace" not in older["layout"] and "autoOptimize" not in older["layout"]


async def test_apply_with_a_switch_on_an_older_bridge_fails_before_the_backup() -> None:
    client = FakeSibeliusClient({"GetBridgeVersion": {"version": bridge.LAYOUT_SWITCHES_BRIDGE_VERSION - 1}})
    b = bridge.SibeliusBridge(client)  # type: ignore[arg-type]
    with pytest.raises(BridgeError, match=f"v{bridge.LAYOUT_SWITCHES_BRIDGE_VERSION}"):
        await service.apply(b, [{"op": "set-layout", "autoOptimize": False}])
    assert "AddVersion" not in client.methods() and "ApplyBatch" not in client.methods()


def _args(*argv: str) -> Any:
    return build_parser().parse_args(["auto-layout", *argv])


async def test_auto_layout_override_sends_the_switch_and_needs_v65(cli_session: CliSession) -> None:
    cli_session.client.replies["GetStaves"] = [{"staffNum": 1}, {"staffNum": 2}]
    with bridge_apply_batch(new=AsyncMock(return_value={"applied": 0, "dryRun": True})) as apply_batch:
        args = _args("--systems", "1,5", "--verses", "2", "--layout", "autoOptimize=off", "--dry-run")
        assert await _run_auto_layout(args) == EXIT_OK
    [layout] = [op for op in apply_batch.await_args_list[0].args[1] if op["op"] == "set-layout"]
    assert layout["autoOptimize"] is False and "autoOptimize" in layout["settings"]
    versions = [call.args[1] for call in bridge.require_bridge.await_args_list]  # type: ignore[attr-defined]
    assert bridge.LAYOUT_SWITCHES_BRIDGE_VERSION in versions


@pytest.mark.parametrize(
    ("last", "expected"),
    [
        # the shape ApplyBatch returns per operation (seen live, bridge v65)
        ({"i": 2, "op": "set-layout", "before": None,
          "after": {"layout": {"autoRespace": True, "autoOptimize": 0}, "engraving": {}}},
         {"autoRespace": True, "autoOptimize": False}),
        ({"i": 2, "op": "set-layout", "before": None, "after": {"layout": {"staffSize": 6}}}, {}),
    ],
)
async def test_auto_layout_reports_the_switches_read_back(
    cli_session: CliSession, capsys: pytest.CaptureFixture[str], last: dict[str, Any], expected: dict[str, bool]
) -> None:
    async def apply(_client: Any, ops: list[dict[str, Any]], dry_run: bool) -> dict[str, Any]:
        return {"applied": 0 if dry_run else len(ops), "results": [] if dry_run else [None] * (len(ops) - 1) + [last]}

    args = _args("--systems", "1,3", "--verses", "2", "--staves", "2", "--no-unlock-format")
    with patch(BACKUP, new=AsyncMock(return_value={"copy": "/b.sib"})), bridge_apply_batch(new=AsyncMock(side_effect=apply)):
        assert await _run_auto_layout(args) == EXIT_OK
    report = json.loads(capsys.readouterr().out)
    assert {k: report[k] for k in ("autoRespace", "autoOptimize") if k in report} == expected
