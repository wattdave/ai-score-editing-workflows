"""set-staff-mixer (bridge v68): schema, gate, plug-in text, the mixer CLI and MCP set_staff_playback."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from ai_score_editing.core.errors import BatchError
from ai_score_editing.sibelius import batch_ops, bridge, mcp_server, service
from ai_score_editing.sibelius.bridge import BridgeError
from ai_score_editing.sibelius.cli import build_parser
from ai_score_editing.sibelius.commands import audio
from ai_score_editing.sibelius.mcp_server import Session
from fakes import CliSession, FakeSibeliusClient

PLUGIN = Path(__file__).resolve().parents[1] / "src/ai_score_editing/sibelius/manuscript/ScoreBridge.plg"
STAVES = [
    {"staffNum": 1, "instrumentName": "Soprano", "fullInstrumentName": "Soprano"},
    {"staffNum": 2, "instrumentName": "Alto", "fullInstrumentName": "Alto"},
    {"staffNum": 3, "instrumentName": "Piano", "fullInstrumentName": "Piano"},
]


def _function(source: str, name: str) -> str:
    start = source.index(f'\t{name} "(')
    return source[start:source.index('}"\n', start)]


def _mixer(op: dict[str, Any]) -> dict[str, Any]:
    return {"op": "set-staff-mixer", "staff": 2, **op}


# ------------------------------------------------------------------ schema

def test_full_op_normalizes_and_lists_its_settings() -> None:
    [op] = batch_ops.validate_batch([_mixer({"mute": "half-muted", "solo": True, "volume": 90, "pan": 30,
                                             "distance": 60})])
    assert op == {"op": "set-staff-mixer", "staff": 2, "muteMode": 1, "solo": True, "volume": 90, "pan": 30,
                  "distance": 60, "settings": ["muteMode", "solo", "volume", "pan", "distance"]}


def test_zero_and_false_values_are_settings() -> None:
    [op] = batch_ops.validate_batch([_mixer({"mute": "muted", "solo": False, "volume": 0, "pan": 0})])
    assert op["muteMode"] == 0 and op["solo"] is False and op["volume"] == 0 and op["pan"] == 0
    assert op["settings"] == ["muteMode", "solo", "volume", "pan"]
    [only] = batch_ops.validate_batch([_mixer({"mute": "not-muted"})])
    assert only["settings"] == ["muteMode"] and only["muteMode"] == 2


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"volume": -1}, "volume"), ({"volume": 128}, "volume"),
        ({"pan": -101}, "pan"), ({"pan": 101}, "pan"),
        ({"distance": -1}, "distance"), ({"distance": 101}, "distance"),
        ({"volume": True}, "volume"), ({"volume": 1.5}, "volume"),
        ({"solo": "on"}, "solo"), ({"mute": "loud"}, "mute"),
        ({"gain": 3}, "unknown"), ({}, "at least one of"),
    ],
)
def test_refusals(fields: dict[str, Any], message: str) -> None:
    with pytest.raises(BatchError, match=message):
        batch_ops.validate_batch([_mixer(fields)])


@pytest.mark.parametrize(("staff", "message"), [(0, "system staff"), ("2", "integer"), (None, "required"),
                                                (-1, "at least 1")])
def test_staff_refusals(staff: Any, message: str) -> None:
    op = {"op": "set-staff-mixer", "mute": "muted"}
    if staff is not None:
        op["staff"] = staff
    with pytest.raises(BatchError, match=message):
        batch_ops.validate_batch([op])


def test_two_ops_on_one_staff_are_refused() -> None:
    with pytest.raises(BatchError, match="merge"):
        batch_ops.validate_batch([_mixer({"mute": "muted"}), _mixer({"volume": 10})])
    assert len(batch_ops.validate_batch([_mixer({"mute": "muted"}), {**_mixer({"volume": 10}), "staff": 3}])) == 2


def test_must_come_before_structural_ops() -> None:
    brk = {"op": "set-break", "bar": 4, "type": "system"}
    assert len(batch_ops.validate_batch([_mixer({"mute": "muted"}), brk])) == 2
    with pytest.raises(BatchError, match="structural"):
        batch_ops.validate_batch([brk, _mixer({"mute": "muted"})])


def test_is_the_newest_gate() -> None:
    assert f"CreateDictionary('version', {bridge.CURRENT_BRIDGE_VERSION})" in PLUGIN.read_text()
    assert bridge.STAFF_NAME_BRIDGE_VERSION < bridge.MIXER_BRIDGE_VERSION <= bridge.CURRENT_BRIDGE_VERSION
    assert bridge.RESET_STAFF_SPACE_BRIDGE_VERSION < bridge.MIXER_BRIDGE_VERSION
    batch = batch_ops.validate_batch([
        _mixer({"mute": "muted"}),
        {"op": "ficta", "staff": 1, "bar": 1, "index": 0, "accidental": "flat"},
        {"op": "set-layout", "autoRespace": True},
        {"op": "reset-staff-space", "fromBar": 1, "toBar": 2},
    ])
    assert bridge.batch_bridge_version(batch) == bridge.MIXER_BRIDGE_VERSION


def test_warnings_name_stems_only_for_mute_or_solo() -> None:
    assert batch_ops.mixer_warnings(batch_ops.validate_batch([_mixer({"volume": 10})])) == []
    [note] = batch_ops.mixer_warnings(batch_ops.validate_batch([_mixer({"solo": False})]))
    assert "single-staff stems" in note


# ------------------------------------------------------------------ plug-in text

def test_plugin_writes_only_named_settings() -> None:
    body = _function(PLUGIN.read_text(), "BatchRunMixer")
    for setting in ("muteMode", "solo", "volume", "pan", "distance"):
        assert f"BatchHasSetting(op, '{setting}')" in body
    for text in ("staff.MuteMode = op['muteMode'];", "staff.Solo = True;", "staff.Solo = False;",
                 "staff.Volume = op['volume'];", "staff.Pan = op['pan'];", "staff.Distance = op['distance'];",
                 "MixerRead(staff)"):
        assert text in body
    assert "BatchRunMixer(score, op)" in _function(PLUGIN.read_text(), "BatchRun")


def test_plugin_checks_the_staff_and_reads_before_values() -> None:
    source = PLUGIN.read_text()
    check = _function(source, "BatchCheck")
    assert "opName = 'set-staff-mixer'" in check and "op['staff'] > score.StaffCount" in check
    assert "before = MixerRead(mixerStaff);" in _function(source, "ApplyBatch")
    for name in ("BatchStructural", "BatchAddressed"):
        assert "set-staff-mixer" not in _function(source, name)
    mixer_read = _function(source, "MixerRead")
    for key in ("muteMode", "solo", "volume", "pan", "distance"):
        assert f"'{key}'" in mixer_read


# ------------------------------------------------------------------ CLI

def _query(rows: dict[int, dict[str, Any]]) -> dict[str, Any]:
    return {"objects": [{"index": 0, "type": "Staff", "staff": n, "bar": 0, "fields": f} for n, f in rows.items()]}


DEFAULT = {"MuteMode": 2, "Solo": False, "Volume": 100, "Pan": 0, "Distance": 50}


async def test_read_only_mixer_makes_no_write(cli_session: CliSession, capsys: pytest.CaptureFixture[str]) -> None:
    cli_session.client.replies["Query"] = _query({1: DEFAULT, 2: {**DEFAULT, "MuteMode": 0}})
    args = build_parser().parse_args(["mixer"])
    with patch("ai_score_editing.sibelius.runner.backup", new=AsyncMock()) as backup:
        assert await audio._run_mixer(args) == 0
    backup.assert_not_awaited()
    assert cli_session.client.methods() == ["Query"]
    out = capsys.readouterr()
    assert json.loads(out.out)["mixer"]["2"]["MuteMode"] == 0
    assert "staff 2: muted, volume 100, pan 0, distance 50" in out.err


async def test_write_needs_bridge_v68_before_the_backup(cli_session: CliSession) -> None:
    cli_session.client.replies["GetStaves"] = STAVES
    args = build_parser().parse_args(["mixer", "--staff", "2", "--mute", "muted", "--volume", "0"])
    bridge.require_bridge.side_effect = BridgeError("mixer needs bridge v68+")
    with patch("ai_score_editing.sibelius.runner.backup", new=AsyncMock()) as backup:
        assert await audio._run_mixer(args) == 1
    bridge.require_bridge.assert_awaited_once_with(cli_session.client, bridge.MIXER_BRIDGE_VERSION, "mixer")
    backup.assert_not_awaited()
    assert "ApplyBatch" not in cli_session.client.methods()


async def test_write_checks_backs_up_applies_and_rereads(
    cli_session: CliSession, capsys: pytest.CaptureFixture[str]
) -> None:
    cli_session.client.replies.update(GetStaves=STAVES, Query=_query({2: DEFAULT}),
                                      ApplyBatch={"applied": 1, "results": []})
    args = build_parser().parse_args(["mixer", "--staff", "Alto", "--mute", "muted", "--volume", "0"])
    with patch("ai_score_editing.sibelius.runner.backup", new=AsyncMock(return_value={"copy": "/b.sib"})) as backup:
        assert await audio._run_mixer(args) == 0
    backup.assert_awaited_once()
    applies = [a for m, a in cli_session.client.calls if m == "ApplyBatch"]
    assert [dry for _, dry in applies] == [True, False]
    assert applies[1][0] == [{"op": "set-staff-mixer", "staff": 2, "muteMode": 0, "volume": 0,
                              "settings": ["muteMode", "volume"]}]
    assert cli_session.client.methods()[-1] == "Query"
    out = capsys.readouterr()
    assert json.loads(out.out)["backup"] == "/b.sib"
    assert "single-staff stems" in out.err


async def test_write_notes_a_sibling_staff_that_changed_too(
    cli_session: CliSession, capsys: pytest.CaptureFixture[str]
) -> None:
    reads = iter([_query({2: DEFAULT, 3: DEFAULT}), _query({2: {**DEFAULT, "Volume": 10}, 3: {**DEFAULT, "Volume": 10}})])
    cli_session.client.replies.update(GetStaves=STAVES, Query=lambda _args: next(reads),
                                      ApplyBatch={"applied": 1, "results": []})
    args = build_parser().parse_args(["mixer", "--staff", "2", "--volume", "10"])
    with patch("ai_score_editing.sibelius.runner.backup", new=AsyncMock(return_value={"copy": "/b.sib"})):
        assert await audio._run_mixer(args) == 0
    assert json.loads(capsys.readouterr().out)["notes"] == [
        "staff 3 changed too (it was not named; probably the same instrument)"
    ]


async def test_dry_run_makes_no_backup(cli_session: CliSession, capsys: pytest.CaptureFixture[str]) -> None:
    before = {"muteMode": 2, "solo": False, "volume": 100, "pan": 0, "distance": 50}
    cli_session.client.replies.update(
        GetStaves=STAVES,
        ApplyBatch={"applied": 0, "dryRun": True, "results": [{"i": 0, "op": "set-staff-mixer", "before": before}]},
    )
    args = build_parser().parse_args(["mixer", "--staff", "2", "--mute", "muted", "--dry-run"])
    with patch("ai_score_editing.sibelius.runner.backup", new=AsyncMock()) as backup:
        assert await audio._run_mixer(args) == 0
    backup.assert_not_awaited()
    assert [a[1] for m, a in cli_session.client.calls if m == "ApplyBatch"] == [True]
    assert json.loads(capsys.readouterr().out)["results"][0]["before"] == before


async def test_reset_covers_every_staff(cli_session: CliSession) -> None:
    cli_session.client.replies.update(GetStaves=STAVES, ApplyBatch={"applied": 0, "dryRun": True, "results": []})
    args = build_parser().parse_args(["mixer", "--reset", "--dry-run"])
    assert await audio._run_mixer(args) == 0
    [(ops, _)] = [a for m, a in cli_session.client.calls if m == "ApplyBatch"]
    assert [(op["staff"], op["muteMode"], op["solo"]) for op in ops] == [(1, 2, False), (2, 2, False), (3, 2, False)]


@pytest.mark.parametrize("argv", [["--volume", "200"], ["--pan", "-101"], ["--reset", "--mute", "muted"]])
async def test_bad_values_exit_before_connecting(cli_session: CliSession, argv: list[str]) -> None:
    args = build_parser().parse_args(["mixer", "--staff", "1", *argv])
    assert await audio._run_mixer(args) == 1
    cli_session.context.__aenter__.assert_not_awaited()


def test_bad_mute_name_is_an_argument_error() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["mixer", "--mute", "loud"])


# ------------------------------------------------------------------ MCP

def _use(client: FakeSibeliusClient) -> Any:
    return patch.object(mcp_server, "session", Session(lambda: client))


def _mcp_client(version: int = bridge.MIXER_BRIDGE_VERSION) -> FakeSibeliusClient:
    return FakeSibeliusClient({
        "GetBridgeVersion": {"version": version}, "GetStaves": STAVES,
        "ApplyBatch": {"applied": 1, "results": []},
    })


@pytest.mark.parametrize(("play", "mode"), [(False, 0), (True, 2)])
async def test_set_staff_playback_backs_up_then_mutes(play: bool, mode: int) -> None:
    client = _mcp_client()
    with _use(client), patch.object(mcp_server, "_backup", new=AsyncMock(return_value={"copy": "/b.sib"})) as backup:
        result = await mcp_server.set_staff_playback(["2", "Piano"], play)
    backup.assert_awaited_once()
    assert result["backup"] == "/b.sib"
    applies = [a for m, a in client.calls if m == "ApplyBatch"]
    assert [dry for _, dry in applies] == [True, False]
    assert [(op["staff"], op["muteMode"]) for op in applies[1][0]] == [(2, mode), (3, mode)]


@pytest.mark.parametrize(("staves", "voices"), [(["2"], [1]), (["0"], None), (["system"], None), ([], None)])
async def test_set_staff_playback_refusals(staves: list[str], voices: list[int] | None) -> None:
    client = _mcp_client()
    with _use(client), pytest.raises(ToolError):
        await mcp_server.set_staff_playback(staves, False, voices)
    assert "ApplyBatch" not in client.methods()


async def test_set_staff_playback_accepts_all_four_voices() -> None:
    client = _mcp_client()
    with _use(client), patch.object(mcp_server, "_backup", new=AsyncMock(return_value={"copy": "/b.sib"})):
        await mcp_server.set_staff_playback(["1"], False, [1, 2, 3, 4])
    assert "ApplyBatch" in client.methods()


async def test_set_staff_playback_on_an_old_bridge() -> None:
    client = _mcp_client(bridge.MIXER_BRIDGE_VERSION - 1)
    with _use(client), patch.object(mcp_server, "_backup", new=AsyncMock()) as backup:
        with pytest.raises(ToolError, match=f"v{bridge.MIXER_BRIDGE_VERSION}"):
            await mcp_server.set_staff_playback(["1"], False)
    backup.assert_not_awaited()


async def test_apply_batch_passes_set_staff_mixer_through_once_validated() -> None:
    client = _mcp_client()
    with _use(client), patch.object(mcp_server, "_backup", new=AsyncMock(return_value={"copy": "/b.sib"})):
        result = await mcp_server.apply_batch([_mixer({"solo": True})])
    assert result["warnings"] and "single-staff stems" in result["warnings"][0]
    with _use(_mcp_client()), patch.object(mcp_server, "_backup", new=AsyncMock(return_value={"copy": "/b.sib"})):
        await mcp_server.apply_batch([{"op": "set-layout", "pageSize": "letter"}])


async def test_service_apply_on_an_old_bridge_fails_before_the_backup() -> None:
    client = _mcp_client(bridge.MIXER_BRIDGE_VERSION - 1)
    b = bridge.SibeliusBridge(client)  # type: ignore[arg-type]
    with pytest.raises(BridgeError, match=f"v{bridge.MIXER_BRIDGE_VERSION}"):
        await service.apply(b, [_mixer({"mute": "muted"})])
    assert not {"AddVersion", "ApplyBatch", "Save"} & set(client.methods())
