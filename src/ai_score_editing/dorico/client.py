"""Async client for Dorico's Remote Control API (a local WebSocket).

Connect flow, as observed on Dorico 6.2 (docs/dorico.md): the client sends
{"message": "connect", ...}. With a session token Dorico already approved,
it answers {"code": "kConnected"} straight away. Without one it shows an
approval prompt; once the user accepts, it sends {"message": "sessiontoken"},
the client echoes the token back with "acceptsessiontoken", and Dorico
answers kConnected. Tokens are stored per client name, since approval is.

Dorico also pushes unsolicited "status" and "selectionchanged" messages,
so every request reads until it sees the reply it is waiting for.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

import websockets

from ai_score_editing.token_store import TokenStore, default_path

logger = logging.getLogger(__name__)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 4560
DEFAULT_CLIENT_NAME = "sibelius-websocket-cli"
HANDSHAKE_VERSION = "1.0"
RECV_TIMEOUT = 30.0
APPROVAL_TIMEOUT = 120.0
INITIAL_STATUS_TIMEOUT = 2.0


class DoricoError(Exception):
    """Dorico refused a request or could not be reached."""


def token_store() -> TokenStore:
    return TokenStore(default_path().with_name("dorico-token.json"))


class DoricoClient:
    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        client_name: str | None = None,
        store: TokenStore | None = None,
        allow_approval: bool = True,
        approval_timeout: float = APPROVAL_TIMEOUT,
    ) -> None:
        self.host = host
        self.port = port
        self.client_name = client_name or os.environ.get("DORICO_CLIENT_NAME", DEFAULT_CLIENT_NAME)
        self.store = store or token_store()
        self.allow_approval = allow_approval
        self.approval_timeout = approval_timeout
        self._ws: Any = None
        # Dorico sends a full status after connecting and then only the fields
        # that changed, so status is the merge of every status message seen.
        self._state: dict[str, Any] = {}

    @property
    def uri(self) -> str:
        return f"ws://{self.host}:{self.port}"

    # Tokens are keyed by client name as well as address: Dorico approves a
    # named client, so a token issued to one name is not reused for another.
    @property
    def _store_host(self) -> str:
        return f"{self.host}#{self.client_name}"

    async def __aenter__(self) -> "DoricoClient":
        await self.connect()
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.close()

    async def connect(self) -> None:
        try:
            self._ws = await websockets.connect(self.uri, max_size=None, open_timeout=5, ping_interval=None)
        except (OSError, asyncio.TimeoutError) as exc:
            raise DoricoError(f"cannot reach Dorico at {self.uri}: is Dorico running? ({exc})") from exc
        entry = self.store.load(self._store_host, self.port)
        hello: dict[str, Any] = {
            "message": "connect",
            "clientName": self.client_name,
            "handshakeVersion": HANDSHAKE_VERSION,
        }
        if entry:
            hello["sessionToken"] = entry.token
        elif not self.allow_approval:
            await self.close()
            raise DoricoError(
                f"no approved Dorico session for client {self.client_name!r}; connect once "
                "interactively and accept the prompt in Dorico"
            )
        await self._send(hello)
        timeout = RECV_TIMEOUT if entry else self.approval_timeout
        while True:
            reply = await self._recv(timeout)
            if reply.get("code") == "kConnected":
                await self._initial_status()
                return
            if reply.get("message") == "sessiontoken":
                token = reply["sessionToken"]
                self.store.save(self._store_host, self.port, token)
                await self._send({"message": "acceptsessiontoken", "sessionToken": token})
                continue
            if reply.get("code") == "kError" or reply.get("message") == "disconnect":
                if entry:
                    self.store.forget(self._store_host, self.port)
                raise DoricoError(f"Dorico refused the connection: {reply}")

    async def _initial_status(self) -> None:
        """Take the full status Dorico pushes after connecting, so a later
        getstatus reply is not mistaken for it."""
        try:
            while (await self._recv(INITIAL_STATUS_TIMEOUT)).get("message") != "status":
                pass
        except DoricoError:
            logger.debug("no initial status from Dorico")

    async def close(self) -> None:
        if self._ws is not None:
            try:
                await self._ws.close()
            finally:
                self._ws = None

    async def _send(self, message: dict[str, Any]) -> None:
        if self._ws is None:
            raise DoricoError("not connected to Dorico")
        logger.debug("-> %s", message)
        await self._ws.send(json.dumps(message))

    async def _recv(self, timeout: float = RECV_TIMEOUT) -> dict[str, Any]:
        if self._ws is None:
            raise DoricoError("not connected to Dorico")
        try:
            raw = await asyncio.wait_for(self._ws.recv(), timeout)
        except asyncio.TimeoutError as exc:
            raise DoricoError(
                "Dorico did not answer; a dialog may be open in Dorico. Ask the user to dismiss it."
            ) from exc
        message = json.loads(raw)
        logger.debug("<- %s", str(message)[:300])
        if not isinstance(message, dict):
            return {"message": "unknown", "data": message}
        if message.get("message") == "status":
            self._state.update({k: v for k, v in message.items() if k != "message"})
        return message

    async def request(self, message: dict[str, Any], reply: str, timeout: float = RECV_TIMEOUT) -> dict[str, Any]:
        """Send message and return the first reply named `reply` (or an error)."""
        await self._send(message)
        while True:
            answer = await self._recv(timeout)
            if answer.get("message") == reply:
                return answer
            if answer.get("message") == "response" and answer.get("code") == "kError":
                raise DoricoError(f"Dorico rejected {message.get('message')}: {answer.get('detail')}")

    async def command(self, command: str, timeout: float = RECV_TIMEOUT) -> None:
        """Run a Dorico command, e.g. "Edit.Undo", and wait until it is done."""
        answer = await self.request({"message": "command", "command": command}, "response", timeout)
        if answer.get("code") != "kOK":
            raise DoricoError(f"Dorico rejected command {command}: {answer.get('detail') or answer.get('code')}")

    async def status(self) -> dict[str, Any]:
        """Dorico's full status: every field it has reported, latest values."""
        await self.request({"message": "getstatus"}, "status")
        return dict(self._state)

    async def app_info(self) -> dict[str, Any]:
        return await self.request({"message": "getappinfo", "info": "version"}, "version")

    async def flows(self) -> list[dict[str, Any]]:
        return (await self.request({"message": "getflows"}, "flowslist")).get("flows", [])

    async def layouts(self) -> list[dict[str, Any]]:
        return (await self.request({"message": "getlayouts"}, "layoutslist")).get("layouts", [])

    async def layout_options(self, layout_id: int) -> dict[str, str]:
        """A layout's Layout Options, as {path: current value} (values are text)."""
        answer = await self.request(
            {"message": "getoptions", "optionsType": "kLayout", "layoutID": layout_id}, "optionslist"
        )
        return {o["path"]: o.get("currentValue", "") for o in answer.get("options", [])}
