"""Tests for the MCP server's session handling and tool behaviour."""

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
import websockets
from mcp.server.mcpserver.exceptions import ToolError

from sibelius_websocket_cli import mcp_server
from sibelius_websocket_cli.mcp_server import Session


class FakeClient:
    def __init__(self, replies: dict[str, Any] | None = None) -> None:
        self.replies = replies or {}
        self.calls: list[tuple[str, Any]] = []
        self.connect = AsyncMock()
        self.close = AsyncMock()

    async def invoke_plugin(self, name: str, method: str, args: Any = None) -> dict[str, Any]:
        self.calls.append((method, args))
        reply = self.replies.get(method, {})
        if isinstance(reply, dict) and reply.get("message") == "busyError":
            return reply
        return {"message": "invokePluginResponse", "result": True, "returnValue": reply}

    async def invoke_commands(self, commands: list[str]) -> dict[str, Any]:
        self.calls.append(("invokeCommands", commands))
        return {"message": "invokeCommandsResponse", "result": True}


def _use(client: FakeClient) -> Any:
    return patch.object(mcp_server, "session", Session(lambda: client))


async def test_session_connects_once_and_reuses_connection() -> None:
    clients = [FakeClient()]
    session = Session(lambda: clients[0])
    action = AsyncMock(return_value="ok")
    assert await session.run(action, retry=True) == "ok"
    assert await session.run(action, retry=True) == "ok"
    clients[0].connect.assert_awaited_once()


async def test_session_retries_reads_after_dropped_connection() -> None:
    made: list[FakeClient] = []

    def factory() -> FakeClient:
        made.append(FakeClient())
        return made[-1]

    session = Session(factory)
    action = AsyncMock(side_effect=[websockets.exceptions.ConnectionClosed(None, None), "ok"])
    assert await session.run(action, retry=True) == "ok"
    assert len(made) == 2
    made[0].close.assert_awaited_once()


async def test_session_never_retries_writes() -> None:
    session = Session(FakeClient)
    action = AsyncMock(side_effect=websockets.exceptions.ConnectionClosed(None, None))
    with pytest.raises(ToolError, match="may or may not"):
        await session.run(action, retry=False)
    assert action.await_count == 1


async def test_busy_reply_names_the_dialog() -> None:
    client = FakeClient({"GetBridgeVersion": {"message": "busyError"}})
    with _use(client), pytest.raises(ToolError, match="dialog"):
        await mcp_server.score_overview()


async def test_query_rejects_unknown_property_before_connecting() -> None:
    client = FakeClient()
    with _use(client), pytest.raises(ToolError, match="NoSuchProp"):
        await mcp_server.query_score(where=["NoSuchProp=1"])
    client.connect.assert_not_awaited()


async def test_query_resolves_staff_names() -> None:
    client = FakeClient({
        "GetBridgeVersion": {"version": 39},
        "GetStaves": [{"staffNum": 1, "instrumentName": "S.", "fullInstrumentName": "Soprano"},
                      {"staffNum": 2, "instrumentName": "T.", "fullInstrumentName": "Tenor"}],
        "Query": {"objects": [], "count": 0, "truncated": False},
    })
    with _use(client):
        assert (await mcp_server.query_score(staves=["Tenor"], bars="3-4"))["count"] == 0
    method, args = client.calls[-1]
    assert method == "Query"
    assert args[0]["staves"] == [2] and args[0]["fromBar"] == 3 and args[0]["toBar"] == 4


async def test_apply_refused_batch_changes_nothing_and_skips_backup() -> None:
    client = FakeClient({
        "GetBridgeVersion": {"version": 39},
        "ApplyBatch": {"error": "op 0: no object at staff 1 bar 1 index 9", "applied": 0},
    })
    ops = [{"op": "delete", "staff": 1, "bar": 1, "index": 9}]
    with _use(client), patch.object(mcp_server, "_backup", new=AsyncMock()) as backup:
        with pytest.raises(ToolError, match="nothing was changed"):
            await mcp_server.apply_batch(ops)
    backup.assert_not_awaited()
    assert [c for c in client.calls if c[0] == "ApplyBatch"] == [("ApplyBatch", [ops, True])]


async def test_apply_checks_backs_up_then_applies() -> None:
    client = FakeClient({"GetBridgeVersion": {"version": 39}, "ApplyBatch": {"applied": 1, "results": []}})
    ops = [{"op": "set", "staff": 1, "bar": 1, "index": 0, "prop": "Dx", "value": 8}]
    with _use(client), patch.object(mcp_server, "_backup", new=AsyncMock(return_value={"copy": "/b.sib"})):
        result = await mcp_server.apply_batch(ops)
    assert result["backup"] == "/b.sib"
    assert [c[1][1] for c in client.calls if c[0] == "ApplyBatch"] == [True, False]


async def test_undo_bounds_and_command() -> None:
    client = FakeClient()
    with _use(client):
        with pytest.raises(ToolError):
            await mcp_server.undo(0)
        assert await mcp_server.undo(2) == {"undone": 2}
    assert client.calls == [("invokeCommands", ["undo", "undo"])]


async def test_structure_names_barlines_and_breaks_and_defaults_to_all_bars() -> None:
    client = FakeClient({
        "GetBridgeVersion": {"version": 45},
        "GetScoreInfo": {"barCount": 12},
        "GetScoreStructure": {
            "barCount": 12, "keySignatures": [{"bar": 2, "storedBar": 1, "name": "D"}],
            "timeSignatures": [], "barlines": [{"bar": 4, "internalType": "3", "position": 1024}],
            "breaks": [{"bar": 8, "breakType": 6}, {"bar": 9, "breakType": 4}],
        },
    })
    with _use(client):
        result = await mcp_server.score_structure()
        assert ("GetScoreStructure", [1, 12]) in client.calls
        assert result["barlines"] == [{"bar": 4, "type": "double", "position": 1024}]
        assert result["breaks"] == [{"bar": 8, "type": "system"}, {"bar": 9, "type": "page"}]
        assert result["keySignatures"][0]["bar"] == 2
        await mcp_server.score_structure("5-")
        assert ("GetScoreStructure", [5, 12]) in client.calls
        await mcp_server.score_structure("7")
        assert ("GetScoreStructure", [7, 7]) in client.calls


async def test_structure_needs_bridge_45() -> None:
    client = FakeClient({"GetBridgeVersion": {"version": 44}})
    with _use(client), pytest.raises(ToolError, match="v45"):
        await mcp_server.score_structure()
