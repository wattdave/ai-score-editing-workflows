"""Async client for Sibelius Connect, plus a sync convenience wrapper.

Connect flow (SPEC.md 2.3): with a cached token, connect silently (Sibelius
sends no reply) and verify liveness with an empty invokeCommands. Without a
token — or if the silent connect turns out dead — do a tokenless connect,
which pops an approval dialog in Sibelius, and store the new token.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import websockets

from sibelius_websocket_cli import protocol
from sibelius_websocket_cli.token_store import TokenStore

logger = logging.getLogger(__name__)

#: Timeout for ordinary command responses.
RECV_TIMEOUT = 30.0
#: Timeout for the tokenless connect — the user has to click a dialog.
APPROVAL_TIMEOUT = 120.0
#: How long to wait for a liveness reply after a silent token reconnect.
LIVENESS_TIMEOUT = 5.0


class ConnectionFailed(Exception):
    """Could not establish a working connection to Sibelius."""


class SibeliusClient:
    def __init__(
        self,
        host: str = protocol.DEFAULT_HOST,
        port: int = protocol.DEFAULT_PORT,
        client_name: str = protocol.DEFAULT_CLIENT_NAME,
        token_store: TokenStore | None = None,
        approval_timeout: float = APPROVAL_TIMEOUT,
        plugins: list[str] | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.client_name = client_name
        self.token_store = token_store or TokenStore()
        self.approval_timeout = approval_timeout
        self.plugins = plugins or []
        self._connection: websockets.asyncio.client.ClientConnection | None = None

    @property
    def uri(self) -> str:
        return f"ws://{self.host}:{self.port}"

    async def __aenter__(self) -> "SibeliusClient":
        await self.connect()
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.close()

    async def connect(self) -> None:
        """Establish a working, handshaken connection.

        Raises:
            ConnectionFailed: if the socket cannot be opened or the
                handshake does not complete.
        """
        entry = self.token_store.load(self.host, self.port)
        # A token reconnect cannot change the declared plug-in list, so a
        # cached token whose session didn't declare our plug-ins is useless.
        if entry is not None and entry.covers(self.plugins):
            self._connection = await self._open_socket()
            # Include plugins anyway: ignored on a token reconnect, but if
            # Sibelius treats a stale token as a fresh connect, this list
            # is what the new session gets.
            await self._send(
                protocol.connect_message(self.client_name, entry.token, self.plugins)
            )
            # A token connect gets no reply; probe with an empty batch.
            await self._send(protocol.invoke_commands_message([]))
            try:
                reply = await self._recv(timeout=LIVENESS_TIMEOUT)
            except (TimeoutError, websockets.exceptions.ConnectionClosed):
                logger.info("Cached session token rejected; falling back to approval")
                await self.close()
            else:
                if reply.get("message") == protocol.MSG_INVOKE_COMMANDS_RESPONSE:
                    return
                if reply.get("message") == protocol.MSG_CONNECT_RESPONSE:
                    # Sibelius treated the stale token as a fresh connect and
                    # issued a new token; adopt it and drain the pending
                    # invokeCommandsResponse to the liveness probe.
                    try:
                        new_token = protocol.parse_connect_response(reply)
                        await self._recv(timeout=LIVENESS_TIMEOUT)
                    except (TimeoutError, protocol.ProtocolError,
                            websockets.exceptions.ConnectionClosed):
                        await self.close()
                    else:
                        self.token_store.save(self.host, self.port, new_token, self.plugins)
                        return
                else:
                    logger.info("Unexpected liveness reply %s; falling back to approval", reply)
                    await self.close()

        self._connection = await self._open_socket()
        await self._send(protocol.connect_message(self.client_name, plugins=self.plugins))
        logger.warning(
            "Waiting for connection approval in Sibelius (client name: %s)...",
            self.client_name,
        )
        try:
            response = await self._recv(timeout=self.approval_timeout)
            new_token = protocol.parse_connect_response(response)
        except (TimeoutError, websockets.exceptions.ConnectionClosed, protocol.ProtocolError) as exc:
            await self.close()
            raise ConnectionFailed(f"Handshake with Sibelius at {self.uri} failed: {exc}") from exc
        self.token_store.save(self.host, self.port, new_token, self.plugins)

    async def close(self) -> None:
        if self._connection is not None:
            try:
                await self._connection.close()
            except websockets.exceptions.WebSocketException:
                pass
            self._connection = None

    async def send_command(self, command_name: str) -> dict[str, Any]:
        await self._send(protocol.command_message(command_name))
        return await self._recv()

    async def invoke_commands(self, commands: list[str]) -> dict[str, Any]:
        await self._send(protocol.invoke_commands_message(commands))
        return await self._recv()

    async def invoke_plugin(
        self,
        name: str,
        method: str | None = None,
        args: list[Any] | None = None,
    ) -> dict[str, Any]:
        await self._send(protocol.invoke_plugin_message(name, method, args))
        return await self._recv()

    async def send_raw(self, message: dict[str, Any]) -> dict[str, Any]:
        """Send an arbitrary protocol message and return the reply."""
        await self._send(message)
        return await self._recv()

    async def ping(self) -> bool:
        """True if Sibelius answers an empty invokeCommands batch."""
        try:
            reply = await self.invoke_commands([])
        except (TimeoutError, websockets.exceptions.WebSocketException):
            return False
        return reply.get("message") == protocol.MSG_INVOKE_COMMANDS_RESPONSE

    # ── internals ─────────────────────────────────────────────────────

    async def _open_socket(self) -> websockets.asyncio.client.ClientConnection:
        try:
            return await websockets.connect(self.uri)
        except (OSError, websockets.exceptions.WebSocketException) as exc:
            raise ConnectionFailed(
                f"Could not open {self.uri} — is Sibelius running with "
                f"Sibelius Connect enabled? ({exc})"
            ) from exc

    async def _send(self, message: dict[str, Any]) -> None:
        assert self._connection is not None, "not connected"
        payload = json.dumps(message)
        logger.debug("-> %s", payload)
        await self._connection.send(payload)

    async def _recv(self, timeout: float = RECV_TIMEOUT) -> dict[str, Any]:
        assert self._connection is not None, "not connected"
        raw = await asyncio.wait_for(self._connection.recv(), timeout)
        logger.debug("<- %s", raw)
        result: dict[str, Any] = json.loads(raw)
        return result


def run_sync(coro: Any) -> Any:
    """Run an async client interaction from synchronous CLI code."""
    return asyncio.run(coro)
