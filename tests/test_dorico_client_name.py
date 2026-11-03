from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_score_editing.dorico import client as dc
from ai_score_editing.core.token_store import TokenStore


MISMATCH = "kClientRejected_ConnectClientNameAndTokenMismatch"


def _closed_by_dorico() -> Exception:
    """What websockets raises when Dorico closes the socket with a reason, as it
    does when a token is presented under a client name it was not issued to."""
    from websockets.exceptions import ConnectionClosedOK
    from websockets.frames import Close

    close = Close(1000, MISMATCH)
    return ConnectionClosedOK(close, close, True)


async def test_a_refusal_is_an_error_not_a_loop_or_a_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    connections = 0

    class FakeWs:
        async def send(self, raw: str) -> None:
            pass

        async def recv(self) -> str:
            raise _closed_by_dorico()

        async def close(self) -> None:
            pass

    async def connect(*args: object, **kwargs: object) -> FakeWs:
        nonlocal connections
        connections += 1
        return FakeWs()

    monkeypatch.setattr(dc.websockets, "connect", connect)
    store = TokenStore(tmp_path / "t.json")
    with pytest.raises(dc.DoricoConnectionError, match=MISMATCH):
        async with dc.DoricoClient(port=45601, store=store):
            pass
    assert connections == 1
