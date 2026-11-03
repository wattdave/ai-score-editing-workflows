from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_score_editing.dorico import client as dc
from ai_score_editing.core.token_store import TokenStore


async def test_reuses_a_token_stored_under_the_old_client_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent: list[dict] = []

    class FakeWs:
        async def send(self, raw: str) -> None:
            sent.append(json.loads(raw))

        done = False

        async def recv(self) -> str:
            first = not self.done
            self.done = True
            return json.dumps({"code": "kConnected"} if first else {"message": "status"})

        async def close(self) -> None:
            pass

    async def connect(*args: object, **kwargs: object) -> FakeWs:
        return FakeWs()

    monkeypatch.setattr(dc.websockets, "connect", connect)
    store = TokenStore(tmp_path / "t.json")
    store.save("127.0.0.1#sibelius-websocket-cli", 45601, "OLD")
    async with dc.DoricoClient(port=45601, store=store):
        pass
    assert sent[0]["clientName"] == "ai-score-editing"
    assert sent[0]["sessionToken"] == "OLD"
    loaded = store.load("127.0.0.1#ai-score-editing", 45601)
    assert loaded is not None and loaded.token == "OLD"


MISMATCH = "kClientRejected_ConnectClientNameAndTokenMismatch"


def _closed_by_dorico() -> Exception:
    """What websockets raises when Dorico closes the socket with a reason, as it
    does when a token is presented under a client name it was not issued to."""
    from websockets.exceptions import ConnectionClosedOK
    from websockets.frames import Close

    close = Close(1000, MISMATCH)
    return ConnectionClosedOK(close, close, True)


async def test_old_token_rejected_by_closing_the_socket_falls_back_to_a_fresh_approval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    hellos: list[dict] = []
    connections = 0

    class FakeWs:
        def __init__(self, refuse: bool) -> None:
            self.refuse = refuse
            self.queue: list[dict] = []

        async def send(self, raw: str) -> None:
            message = json.loads(raw)
            if message["message"] == "connect":
                hellos.append(message)
                if not self.refuse:
                    self.queue = [
                        {"message": "sessiontoken", "sessionToken": "NEW"},
                        {"code": "kConnected"},
                        {"message": "status"},
                    ]

        async def recv(self) -> str:
            if self.refuse:
                raise _closed_by_dorico()
            return json.dumps(self.queue.pop(0))

        async def close(self) -> None:
            pass

    async def connect(*args: object, **kwargs: object) -> FakeWs:
        nonlocal connections
        connections += 1
        return FakeWs(refuse=connections == 1)  # only the old-token attempt is refused

    monkeypatch.setattr(dc.websockets, "connect", connect)
    store = TokenStore(tmp_path / "t.json")
    store.save("127.0.0.1#sibelius-websocket-cli", 45601, "OLD")
    async with dc.DoricoClient(port=45601, store=store):
        pass
    assert [h.get("sessionToken") for h in hellos] == ["OLD", None]
    assert store.load("127.0.0.1#sibelius-websocket-cli", 45601) is None
    new = store.load("127.0.0.1#ai-score-editing", 45601)
    assert new is not None and new.token == "NEW"


async def test_a_refusal_with_no_old_token_is_an_error_not_a_loop_or_a_traceback(
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
