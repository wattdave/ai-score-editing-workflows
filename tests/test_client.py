"""Client tests against a fake Sibelius Connect server."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
import websockets

from sibelius_websocket_cli.client import ConnectionFailed, SibeliusClient
from sibelius_websocket_cli.token_store import TokenStore

FAKE_TOKEN = "{fake-token-1234}"


class FakeSibelius:
    """Mimics Sibelius Connect: one-step handshake, silent token reconnect."""

    def __init__(self) -> None:
        self.approved_tokens: set[str] = set()
        self.connect_dialogs_shown = 0
        self.port: int = 0
        self._server: websockets.asyncio.server.Server | None = None

    async def __aenter__(self) -> "FakeSibelius":
        self._server = await websockets.serve(self._handle, "localhost", 0)
        self.port = self._server.sockets[0].getsockname()[1]
        return self

    async def __aexit__(self, *exc: object) -> None:
        assert self._server is not None
        self._server.close()
        await self._server.wait_closed()

    async def _handle(self, ws: websockets.asyncio.server.ServerConnection) -> None:
        connected = False
        async for raw in ws:
            msg = json.loads(raw)
            kind = msg.get("message")
            if kind == "connect":
                token = msg.get("sessionToken")
                if token in self.approved_tokens:
                    connected = True  # silent: no reply at all
                else:
                    self.connect_dialogs_shown += 1
                    new_token = FAKE_TOKEN
                    self.approved_tokens.add(new_token)
                    connected = True
                    await ws.send(json.dumps({
                        "message": "connectResponse",
                        "result": True,
                        "sessionToken": new_token,
                    }))
            elif not connected:
                await ws.close()
            elif kind == "command":
                ok = msg.get("commandName") != "Bogus.Command"
                await ws.send(json.dumps({"message": "commandResponse", "result": ok}))
            elif kind == "invokeCommands":
                await ws.send(json.dumps({"message": "invokeCommandsResponse", "result": True}))
            else:
                await ws.send(json.dumps({
                    "message": "messageProcessingError",
                    "errorDetails": "unrecognized message",
                }))


@pytest.fixture
def store(tmp_path: Path) -> TokenStore:
    return TokenStore(tmp_path / "token.json")


def make_client(fake: FakeSibelius, store: TokenStore) -> SibeliusClient:
    return SibeliusClient(host="localhost", port=fake.port, token_store=store, approval_timeout=5)


async def test_fresh_connect_stores_token_and_commands_work(store: TokenStore) -> None:
    async with FakeSibelius() as fake:
        async with make_client(fake, store) as client:
            assert await client.ping() is True
            response = await client.send_command("Edit.Undo")
            assert response["result"] is True
        assert fake.connect_dialogs_shown == 1
        assert store.load("localhost", fake.port) == FAKE_TOKEN


async def test_token_reconnect_skips_approval_dialog(store: TokenStore) -> None:
    async with FakeSibelius() as fake:
        async with make_client(fake, store):
            pass
        async with make_client(fake, store) as client:
            assert await client.ping() is True
        assert fake.connect_dialogs_shown == 1


async def test_stale_token_falls_back_to_approval(store: TokenStore) -> None:
    async with FakeSibelius() as fake:
        store.save("localhost", fake.port, "{stale-token}")
        async with make_client(fake, store) as client:
            assert await client.ping() is True
        assert fake.connect_dialogs_shown == 1
        assert store.load("localhost", fake.port) == FAKE_TOKEN


async def test_failed_command_reports_result_false(store: TokenStore) -> None:
    async with FakeSibelius() as fake:
        async with make_client(fake, store) as client:
            response = await client.send_command("Bogus.Command")
            assert response["result"] is False


async def test_connect_refused_when_no_server(store: TokenStore) -> None:
    client = SibeliusClient(host="localhost", port=1, token_store=store)
    with pytest.raises(ConnectionFailed):
        await client.connect()


def test_token_store_roundtrip(tmp_path: Path) -> None:
    store = TokenStore(tmp_path / "token.json")
    assert store.load("localhost", 1898) is None
    store.save("localhost", 1898, "{t1}")
    store.save("otherhost", 9999, "{t2}")
    assert store.load("localhost", 1898) == "{t1}"
    assert store.load("otherhost", 9999) == "{t2}"
    assert (tmp_path / "token.json").stat().st_mode & 0o777 == 0o600
    assert store.forget("localhost", 1898) is True
    assert store.load("localhost", 1898) is None
    assert store.forget("localhost", 1898) is False


async def test_send_raw_unrecognized_message(store: TokenStore) -> None:
    async with FakeSibelius() as fake:
        async with make_client(fake, store) as client:
            response = await client.send_raw({"message": "getstatus"})
            assert response["message"] == "messageProcessingError"


async def test_invoke_commands_batch(store: TokenStore) -> None:
    async with FakeSibelius() as fake:
        async with make_client(fake, store) as client:
            response = await client.invoke_commands(["a", "b"])
            assert response["result"] is True
