from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_score_editing.dorico import client as dc
from ai_score_editing.token_store import TokenStore


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
