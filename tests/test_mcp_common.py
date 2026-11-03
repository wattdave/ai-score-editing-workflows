"""Session and helper behaviour shared by the Sibelius, Dorico and MuseScore MCP servers."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
import websockets
from mcp.server.mcpserver.exceptions import ToolError

from ai_score_editing import mcp_common
from ai_score_editing.sibelius import batch_ops
from ai_score_editing.dorico import mcp_server as dorico_server
from ai_score_editing.dorico.client import DoricoError
from ai_score_editing.dorico.score import DoricoBatchError
from ai_score_editing.musescore import mcp_server as musescore_server
from ai_score_editing.musescore.client import MuseScoreError
from ai_score_editing.musescore.score import MuseScoreBatchError
from ai_score_editing.query import QueryError
from ai_score_editing.sibelius import mcp_server as sibelius_server
from ai_score_editing.sibelius.bridge import BridgeBusy, BridgeError
from ai_score_editing.sibelius.client import ConnectionFailed


class FakeClient:
    def __init__(self, connect_error: Exception | None = None) -> None:
        self.connect = AsyncMock(side_effect=connect_error)
        self.close = AsyncMock()


# (module, app name, connect error, errors converted to ToolError with their messages)
BACKENDS = [
    pytest.param(
        sibelius_server, "Sibelius", ConnectionFailed("no socket"),
        [(BridgeError("bad"), "bad"), (BridgeError({"a": 1}), '{"a": 1}'), (QueryError("q"), "q"),
         (batch_ops.BatchError("b"), "b"), (BridgeBusy("busyError"), None)],
        id="sibelius",
    ),
    pytest.param(
        dorico_server, "Dorico", DoricoError("no socket"),
        [(DoricoError("e"), "e"), (DoricoBatchError("b"), "b")],
        id="dorico",
    ),
    pytest.param(
        musescore_server, "MuseScore", MuseScoreError("no socket"),
        [(MuseScoreError("e"), "e"), (MuseScoreBatchError("b"), "b"), (batch_ops.BatchError("c"), "c"),
         (QueryError("q"), "q")],
        id="musescore",
    ),
]


def _dropped() -> Exception:
    return websockets.exceptions.ConnectionClosed(None, None)


@pytest.mark.parametrize(("module", "app", "connect_error", "errors"), BACKENDS)
async def test_reconnects_after_dropped_read(module: Any, app: str, connect_error: Exception, errors: list) -> None:
    made: list[FakeClient] = []

    def factory() -> FakeClient:
        made.append(FakeClient())
        return made[-1]

    session = module.Session(factory)
    action = AsyncMock(side_effect=[_dropped(), "ok"])
    assert await session.run(action, retry=True) == "ok"
    assert len(made) == 2
    made[0].close.assert_awaited_once()


@pytest.mark.parametrize(("module", "app", "connect_error", "errors"), BACKENDS)
async def test_oserror_on_read_also_retries(module: Any, app: str, connect_error: Exception, errors: list) -> None:
    session = module.Session(FakeClient)
    action = AsyncMock(side_effect=[OSError("reset"), "ok"])
    assert await session.run(action, retry=True) == "ok"


@pytest.mark.parametrize(("module", "app", "connect_error", "errors"), BACKENDS)
async def test_dropped_write_is_not_retried(module: Any, app: str, connect_error: Exception, errors: list) -> None:
    made: list[FakeClient] = []

    def factory() -> FakeClient:
        made.append(FakeClient())
        return made[-1]

    session = module.Session(factory)
    action = AsyncMock(side_effect=_dropped())
    with pytest.raises(ToolError) as info:
        await session.run(action, retry=False)
    assert str(info.value) == (
        f"the connection to {app} dropped during a change; it may or may not "
        "have been applied. Check with query_score before trying again."
    )
    assert action.await_count == 1
    made[0].close.assert_awaited_once()


@pytest.mark.parametrize(("module", "app", "connect_error", "errors"), BACKENDS)
async def test_connect_failure_names_the_app(module: Any, app: str, connect_error: Exception, errors: list) -> None:
    session = module.Session(lambda: FakeClient(connect_error))
    action = AsyncMock()
    with pytest.raises(ToolError) as info:
        await session.run(action, retry=True)
    assert str(info.value) == f"cannot connect to {app}: {connect_error}"
    action.assert_not_awaited()


@pytest.mark.parametrize(("module", "app", "connect_error", "errors"), BACKENDS)
async def test_error_types_become_tool_errors(module: Any, app: str, connect_error: Exception, errors: list) -> None:
    for exc, expected in errors:
        session = module.Session(FakeClient)
        with pytest.raises(ToolError) as info:
            await session.run(AsyncMock(side_effect=exc), retry=True)
        if expected is None:
            assert "busy" in str(info.value)
        else:
            assert str(info.value) == expected


@pytest.mark.parametrize(("module", "app", "connect_error", "errors"), BACKENDS)
async def test_connects_once_and_reuses(module: Any, app: str, connect_error: Exception, errors: list) -> None:
    client = FakeClient()
    session = module.Session(lambda: client)
    action = AsyncMock(return_value="ok")
    await session.run(action, retry=True)
    await session.run(action, retry=True)
    client.connect.assert_awaited_once()


def test_parse_bars() -> None:
    assert mcp_common.parse_bars(None) == (None, None)
    assert mcp_common.parse_bars("3-5") == (3, 5)
    with pytest.raises(ToolError):
        mcp_common.parse_bars("x-y")


def test_env_port(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SOME_PORT", raising=False)
    assert mcp_common.env_port("SOME_PORT", 1234) == 1234
    monkeypatch.setenv("SOME_PORT", "99")
    assert mcp_common.env_port("SOME_PORT", 1234) == 99
