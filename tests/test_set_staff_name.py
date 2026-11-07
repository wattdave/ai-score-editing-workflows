"""set-staff-name sets the instrument name only, so Sibelius draws it once."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from ai_score_editing.sibelius import bridge as sibelius_bridge
from ai_score_editing.sibelius.bridge import BridgeError
from ai_score_editing.sibelius.cli import build_parser
from ai_score_editing.sibelius.commands import score as score_commands
from fakes import CliSession

PLUGIN = Path(__file__).resolve().parents[1] / "src/ai_score_editing/sibelius/manuscript/ScoreBridge.plg"


def _function(source: str, name: str) -> str:
    start = source.index(f'\t{name} "(')
    return source[start:source.index('}"\n', start)]


def test_plugin_sets_instrument_names_and_never_writes_a_staff_name() -> None:
    body = _function(PLUGIN.read_text(), "SetStaffName")
    assert "staff.FullInstrumentName = '' & fullName;" in body
    assert "staff.ShortInstrumentName = '' & shortName;" in body
    # the staff name is only ever cleared, never set to the new name
    assert "staff.FullStaffName = '' & fullName" not in body
    assert "staff.ShortStaffName = '' & shortName" not in body
    assert "staff.FullStaffName = '';" in body
    assert "staff.ShortStaffName = '';" in body
    assert "'fullStaffName', staff.FullStaffName" in body


def test_plugin_version_matches_the_staff_name_gate() -> None:
    source = PLUGIN.read_text()
    assert f"CreateDictionary('version', {sibelius_bridge.CURRENT_BRIDGE_VERSION})" in source
    assert sibelius_bridge.STAFF_NAME_BRIDGE_VERSION == sibelius_bridge.CURRENT_BRIDGE_VERSION == 64


async def test_set_staff_name_needs_bridge_v64_before_the_backup(cli_session: CliSession) -> None:
    args = build_parser().parse_args(["set-staff-name", "--staff", "1", "--full", "I", "--short", "I"])
    sibelius_bridge.require_bridge.side_effect = BridgeError("set-staff-name needs bridge v64+")
    with patch("ai_score_editing.sibelius.runner.backup", new=AsyncMock()) as backup:
        with pytest.raises(BridgeError, match="v64"):
            await score_commands._run_set_staff_name(args)
    sibelius_bridge.require_bridge.assert_awaited_once_with(cli_session.client, 64, "set-staff-name")
    backup.assert_not_awaited()
    assert "SetStaffName" not in cli_session.client.methods()


async def test_set_staff_name_calls_the_bridge(
    cli_session: CliSession, capsys: pytest.CaptureFixture[str]
) -> None:
    args = build_parser().parse_args(["set-staff-name", "--staff", "2", "--full", "Alto"])
    cli_session.client.replies["SetStaffName"] = {
        "staffNum": 2, "fullInstrumentName": "Alto", "shortInstrumentName": "A.",
        "fullStaffName": "", "shortStaffName": "",
    }
    with patch("ai_score_editing.sibelius.runner.backup", new=AsyncMock(return_value={"copy": "/b.sib"})):
        assert await score_commands._run_set_staff_name(args) == 0
    assert ("SetStaffName", [2, "Alto", ""]) in cli_session.client.calls
    assert '"fullStaffName": ""' in capsys.readouterr().out
