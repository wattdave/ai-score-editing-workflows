"""reset-staff-space (bridge v66): schema, gate, plug-in text and back-end refusals."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from ai_score_editing.core.errors import BatchError
from ai_score_editing.sibelius import batch_ops, bridge, service
from ai_score_editing.sibelius.bridge import BridgeError
from fakes import FakeSibeliusClient

PLUGIN = Path(__file__).resolve().parents[1] / "src/ai_score_editing/sibelius/manuscript/ScoreBridge.plg"


def _function(source: str, name: str) -> str:
    start = source.index(f'\t{name} "(')
    return source[start:source.index('}"\n', start)]


def test_defaults_to_both_sides_and_every_staff() -> None:
    batch = batch_ops.validate_batch([{"op": "reset-staff-space", "fromBar": 1, "toBar": 43}])
    assert batch == [{"op": "reset-staff-space", "fromBar": 1, "toBar": 43, "above": True, "below": True}]
    assert bridge.batch_bridge_version(batch) == bridge.RESET_STAFF_SPACE_BRIDGE_VERSION


def test_staff_range_and_one_side_pass_through() -> None:
    [op] = batch_ops.validate_batch([
        {"op": "reset-staff-space", "fromBar": 5, "toBar": 8, "topStaff": 2, "bottomStaff": 3, "above": False}
    ])
    assert op == {"op": "reset-staff-space", "fromBar": 5, "toBar": 8, "topStaff": 2, "bottomStaff": 3,
                  "above": False, "below": True}


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"fromBar": 4, "toBar": 2}, "toBar"),
        ({"fromBar": 1, "toBar": 2, "topStaff": 2}, "both topStaff and bottomStaff"),
        ({"fromBar": 1, "toBar": 2, "topStaff": 0, "bottomStaff": 1}, "topStaff"),
        ({"fromBar": 1, "toBar": 2, "topStaff": 3, "bottomStaff": 2}, "bottomStaff"),
        ({"fromBar": 1, "toBar": 2, "above": False, "below": False}, "above or below"),
        ({"fromBar": 1, "toBar": 2, "above": "yes"}, "boolean"),
        ({"fromBar": 1, "toBar": 2, "staff": 1}, "unknown"),
    ],
)
def test_refusals(fields: dict[str, Any], message: str) -> None:
    with pytest.raises(BatchError, match=message):
        batch_ops.validate_batch([{"op": "reset-staff-space", **fields}])


def test_is_structural_and_checked_against_rebarring() -> None:
    reset = {"op": "reset-staff-space", "fromBar": 1, "toBar": 8}
    nudge = {"op": "nudge", "staff": 1, "bar": 1, "index": 0, "dx": 4}
    with pytest.raises(BatchError, match="structural ops must come last"):
        batch_ops.validate_batch([reset, nudge])
    with pytest.raises(BatchError, match="moves"):
        batch_ops.validate_batch([{"op": "set-time", "bar": 3, "numerator": 3, "denominator": 4}, reset])


def test_is_the_newest_gate() -> None:
    assert f"CreateDictionary('version', {bridge.CURRENT_BRIDGE_VERSION})" in PLUGIN.read_text()
    assert bridge.STAFF_NAME_BRIDGE_VERSION < bridge.RESET_STAFF_SPACE_BRIDGE_VERSION <= bridge.CURRENT_BRIDGE_VERSION
    mixed = [{"op": "ficta"}, {"op": "set-layout", "settings": ["autoRespace"]}, {"op": "reset-staff-space"}]
    assert bridge.batch_bridge_version(mixed) == bridge.RESET_STAFF_SPACE_BRIDGE_VERSION


def test_plugin_runs_the_reset_per_staff_before_the_bar_lookup() -> None:
    body = _function(PLUGIN.read_text(), "BatchRunStructural")
    assert "ResetSpaceAroundStaff(above, below, op['fromBar'], op['toBar'])" in body
    assert "if (op['above'] = True)" in body and "if (op['below'] = True)" in body
    assert "bottom = score.StaffCount;" in body and "to bottom + 1" in body
    assert body.index("ResetSpaceAroundStaff") < body.index("bar = systemStaff.NthBar(op['bar'])")


def test_plugin_checks_a_side_and_lists_the_op_as_structural() -> None:
    source = PLUGIN.read_text()
    assert "'reset-staff-space needs above or below'" in _function(source, "BatchCheckStructural")
    assert "opName = 'reset-staff-space'" in _function(source, "BatchStructural")


async def test_apply_on_an_older_bridge_fails_before_the_backup() -> None:
    client = FakeSibeliusClient({"GetBridgeVersion": {"version": bridge.RESET_STAFF_SPACE_BRIDGE_VERSION - 1}})
    b = bridge.SibeliusBridge(client)  # type: ignore[arg-type]
    with pytest.raises(BridgeError, match=f"v{bridge.RESET_STAFF_SPACE_BRIDGE_VERSION}"):
        await service.apply(b, [{"op": "reset-staff-space", "fromBar": 1, "toBar": 4}])
    assert not {"AddVersion", "ApplyBatch", "Save"} & set(client.methods())


async def test_apply_sends_the_normalized_op() -> None:
    client = FakeSibeliusClient({
        "GetBridgeVersion": {"version": bridge.RESET_STAFF_SPACE_BRIDGE_VERSION},
        "ApplyBatch": {"applied": 0, "dryRun": True},
    })
    b = bridge.SibeliusBridge(client)  # type: ignore[arg-type]
    await service.apply(b, [{"op": "reset-staff-space", "fromBar": 1, "toBar": 4}], dry_run=True)
    [(operations, dry_run)] = [args for method, args in client.calls if method == "ApplyBatch"]
    assert dry_run is True
    assert operations == [{"op": "reset-staff-space", "fromBar": 1, "toBar": 4, "above": True, "below": True}]

