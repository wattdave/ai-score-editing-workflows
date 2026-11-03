"""Tests for the Sibelius service layer shared by the CLI and the MCP server."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from ai_score_editing.core.errors import BatchError
from ai_score_editing.query import QueryError
from ai_score_editing.sibelius import bridge, mcp_server, service
from ai_score_editing.sibelius.bridge import BUSY_MESSAGE, BridgeBusy, BridgeError
from ai_score_editing.sibelius.mcp_server import Session
from fakes import BUSY, FakeSibeliusClient

OPS = [{"op": "set", "staff": 1, "bar": 1, "index": 0, "prop": "Dx", "value": 8}]


def _bridge(replies: dict[str, Any]) -> tuple[bridge.SibeliusBridge, FakeSibeliusClient]:
    client = FakeSibeliusClient(replies)
    return bridge.SibeliusBridge(client), client  # type: ignore[arg-type]


def _score(tmp_path: Path) -> Path:
    score = tmp_path / "song.sib"
    score.write_bytes(b"sib")
    return score


def test_backup_folder_prefers_argument_then_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("SIBELIUS_BACKUP_DIR", raising=False)
    assert service.backup_folder() is None
    monkeypatch.setenv("SIBELIUS_BACKUP_DIR", str(tmp_path / "env"))
    assert service.backup_folder() == tmp_path / "env"
    assert service.backup_folder(str(tmp_path / "arg")) == tmp_path / "arg"


async def test_overview_reads_four_bridge_calls() -> None:
    b, client = _bridge({"GetBridgeVersion": {"version": 62}, "GetScoreInfo": {"title": "A"}})
    result = await service.overview(b)
    assert set(result) == {"bridge", "score", "staves", "selection"}
    assert client.methods() == ["GetBridgeVersion", "GetScoreInfo", "GetStaves", "GetSelectionInfo"]


async def test_busy_raises_bridge_busy_with_the_dialog_text() -> None:
    b, _ = _bridge({"GetBridgeVersion": BUSY})
    with pytest.raises(BridgeBusy) as caught:
        await service.overview(b)
    assert caught.value.payload == BUSY_MESSAGE
    assert "dialog" in BUSY_MESSAGE


async def test_structure_needs_bridge_45_and_defaults_to_all_bars() -> None:
    b, _ = _bridge({"GetBridgeVersion": {"version": 44}})
    with pytest.raises(BridgeError, match="v45"):
        await service.structure(b, None, None)
    b, client = _bridge({
        "GetBridgeVersion": {"version": 45}, "GetScoreInfo": {"barCount": 9},
        "GetScoreStructure": {"barCount": 9, "keySignatures": [], "timeSignatures": [], "barlines": [], "breaks": []},
    })
    await service.structure(b, None, None)
    assert ("GetScoreStructure", [1, 9]) in client.calls


async def test_query_rejects_bad_property_before_calling_sibelius() -> None:
    b, client = _bridge({})
    with pytest.raises(QueryError, match="NoSuchProp"):
        await service.query(b, where=["NoSuchProp=1"])
    assert client.calls == []


async def test_query_resolves_staff_names_and_gates_versions() -> None:
    staves = [{"staffNum": 1, "instrumentName": "S.", "fullInstrumentName": "Soprano"},
              {"staffNum": 2, "instrumentName": "T.", "fullInstrumentName": "Tenor"}]
    b, client = _bridge({"GetBridgeVersion": {"version": 62}, "GetStaves": staves, "Query": {"count": 0}})
    await service.query(b, staves=["Tenor"], from_bar=3, to_bar=4)
    method, args = client.calls[-1]
    assert method == "Query" and args[0]["staves"] == [2] and args[0]["fromBar"] == 3

    old, _ = _bridge({"GetBridgeVersion": {"version": 40}})
    with pytest.raises(BridgeError, match="v62"):
        await service.query(old, types=["Bar"])
    with pytest.raises(BridgeError, match="v61"):
        await service.query(old, fields=["InitialFontName"], types=["Text"])


async def test_apply_dry_run_checks_only() -> None:
    b, client = _bridge({"GetBridgeVersion": {"version": 62}, "ApplyBatch": {"applied": 0, "dryRun": True}})
    result = await service.apply(b, OPS, dry_run=True)
    assert result["dryRun"] is True
    assert [c[1][1] for c in client.calls if c[0] == "ApplyBatch"] == [True]
    assert "AddVersion" not in client.methods()


async def test_apply_refused_says_nothing_was_changed_and_skips_backup() -> None:
    b, client = _bridge({
        "GetBridgeVersion": {"version": 62},
        "ApplyBatch": {"error": "op 0: no object at staff 1 bar 1 index 9", "applied": 0},
    })
    with pytest.raises(service.BatchFailed, match="nothing was changed"):
        await service.apply(b, OPS)
    assert not {"AddVersion", "Save"} & set(client.methods())
    assert [c[1][1] for c in client.calls if c[0] == "ApplyBatch"] == [True]


async def test_apply_rejects_an_invalid_batch() -> None:
    b, client = _bridge({})
    with pytest.raises(BatchError):
        await service.apply(b, [{"op": "no-such-op"}])
    assert client.calls == []


async def test_apply_saves_backs_up_then_applies(tmp_path: Path) -> None:
    score = _score(tmp_path)
    folder = tmp_path / "backups"
    b, client = _bridge({
        "GetBridgeVersion": {"version": 62}, "Save": {"fileName": str(score)},
        "ApplyBatch": {"applied": 1, "results": []},
    })
    result = await service.apply(b, OPS, backup_dir=folder)
    assert Path(result["backup"]).parent == folder
    assert Path(result["backup"]).read_bytes() == b"sib"
    methods = client.methods()
    assert methods.index("Save") < len(methods) - 1  # saved before the real batch
    assert [c[1][1] for c in client.calls if c[0] == "ApplyBatch"] == [True, False]


async def test_apply_partial_failure_says_to_undo_once(tmp_path: Path) -> None:
    score = _score(tmp_path)
    answers = iter([{"applied": 0, "dryRun": True}, {"error": "op 1: refused", "applied": 1, "failedOp": 1}])
    b, _ = _bridge({
        "GetBridgeVersion": {"version": 62}, "Save": {"fileName": str(score)},
        "ApplyBatch": lambda args: next(answers),
    })
    with pytest.raises(service.BatchFailed) as caught:
        await service.apply(b, OPS, backup_dir=tmp_path / "bk")
    assert "1 operation(s) were applied as one undo step. Call undo once to revert them." in str(caught.value)
    assert caught.value.applied == 1 and caught.value.backup


async def test_undo_bounds_command_and_busy() -> None:
    b, client = _bridge({})
    with pytest.raises(BatchError):
        await service.undo(b, 0)
    assert await service.undo(b, 2) == {"undone": 2}
    assert client.calls == [("invokeCommands", ["undo", "undo"])]
    busy, _ = _bridge({"invokeCommands": BUSY})
    with pytest.raises(BridgeBusy):
        await service.undo(busy, 1)


async def test_save_returns_the_bridge_result() -> None:
    b, _ = _bridge({"Save": {"fileName": "/s.sib"}})
    assert await service.save(b) == {"fileName": "/s.sib"}


async def test_export_names_the_produced_files(tmp_path: Path) -> None:
    out = tmp_path / "song.pdf"

    def export_score(args: Any) -> dict[str, Any]:
        Path(args[0]).write_bytes(b"pdf")
        return {"ok": True}

    b, client = _bridge({"GetScoreInfo": {"fileName": str(tmp_path / "song.sib")}, "ExportScore": export_score})
    result = await service.export(b, "pdf")
    assert result["files"] == [str(out)] and result["size"] == 3
    assert ("ExportScore", [str(out), "PDF"]) in client.calls
    with pytest.raises(BatchError, match="format must be"):
        await service.export(b, "docx")
    unsaved, _ = _bridge({"GetScoreInfo": {"fileName": ""}})
    with pytest.raises(BridgeError, match="never been saved"):
        await service.export(unsaved, "pdf")


async def test_backup_refuses_a_score_without_a_path() -> None:
    b, _ = _bridge({"Save": {"fileName": "peace round"}})
    with pytest.raises(BridgeError, match="never been saved as a .sib"):
        await service.backup(b, "before x", None)


async def test_backup_goes_beside_the_score_by_default(tmp_path: Path) -> None:
    score = _score(tmp_path)
    b, _ = _bridge({"Save": {"fileName": str(score)}})
    result = await service.backup(b, "before x", None)
    assert Path(result["copy"]).parent == tmp_path


async def test_mcp_apply_batch_backs_up_into_the_environment_folder(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    score = _score(tmp_path)
    folder = tmp_path / "env-backups"
    monkeypatch.setenv("SIBELIUS_BACKUP_DIR", str(folder))
    client = FakeSibeliusClient({
        "GetBridgeVersion": {"version": 62}, "Save": {"fileName": str(score)},
        "ApplyBatch": {"applied": 1, "results": []},
    })
    with patch.object(mcp_server, "session", Session(lambda: client)):
        result = await mcp_server.apply_batch(OPS)
    assert Path(result["backup"]).parent == folder
    assert not list(tmp_path.glob("*.backup-*"))


async def test_mcp_texts_for_busy_and_partial_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    score = _score(tmp_path)
    monkeypatch.setenv("SIBELIUS_BACKUP_DIR", str(tmp_path / "bk"))
    answers = iter([{"applied": 0}, {"error": "op 0: refused", "applied": 2}])
    client = FakeSibeliusClient({
        "GetBridgeVersion": {"version": 62}, "Save": {"fileName": str(score)},
        "ApplyBatch": lambda args: next(answers),
    })
    with patch.object(mcp_server, "session", Session(lambda: client)):
        with pytest.raises(ToolError, match="Call undo once to revert them"):
            await mcp_server.apply_batch(OPS)
    busy = FakeSibeliusClient({"GetBridgeVersion": BUSY})
    with patch.object(mcp_server, "session", Session(lambda: busy)):
        with pytest.raises(ToolError) as caught:
            await mcp_server.score_overview()
    assert str(caught.value) == BUSY_MESSAGE
