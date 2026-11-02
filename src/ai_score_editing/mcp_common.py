"""Pieces shared by the Sibelius, Dorico and MuseScore MCP servers."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable
from typing import Generic, TypeVar

import websockets.exceptions
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from ai_score_editing.barrange import parse_bar_range

T = TypeVar("T")
B = TypeVar("B")

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False)
EXPORT = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False)


def parse_bars(bars: str | None) -> tuple[int | None, int | None]:
    """Parse a bar range such as "1-40" (None means all bars); bad input is a ToolError."""
    try:
        return parse_bar_range(bars=bars) if bars else (None, None)
    except ValueError as exc:
        raise ToolError(str(exc)) from exc


def env_port(name: str, default: int | str) -> int:
    """The port number in environment variable name, or default."""
    return int(os.environ.get(name, default))


class Session(Generic[B]):
    """One lazily opened connection to a score editor, used by one call at a time.

    app names the editor in messages; factory makes an unconnected client;
    wrap turns a connected client into the bridge actions receive (its .client
    is the client); connect_error is raised by client.connect(); errors are
    converted to ToolError while an action runs, using message_for(exc) when
    it returns text, else str(exc).
    """

    def __init__(
        self,
        app: str,
        factory: Callable[[], object],
        wrap: Callable[..., B],
        connect_error: type[Exception],
        errors: tuple[type[Exception], ...],
        message_for: Callable[[Exception], str | None] | None = None,
    ) -> None:
        self._app = app
        self._factory = factory
        self._wrap = wrap
        self._connect_error = connect_error
        self._errors = errors
        self._message_for = message_for
        self._bridge: B | None = None
        self._lock = asyncio.Lock()

    async def run(self, action: Callable[[B], Awaitable[T]], *, retry: bool) -> T:
        """Run action on the session's bridge, reconnecting if the connection dropped.

        Only read-only actions retry: a write whose connection dropped may
        already have been applied, and repeating it could apply it twice.
        """
        async with self._lock:
            try:
                return await self._guard(action(await self._connected()))
            except (websockets.exceptions.ConnectionClosed, OSError):
                await self._reset()
                if not retry:
                    raise ToolError(
                        f"the connection to {self._app} dropped during a change; it may or may not "
                        "have been applied. Check with query_score before trying again."
                    ) from None
                return await self._guard(action(await self._connected()))

    async def _guard(self, awaitable: Awaitable[T]) -> T:
        try:
            return await awaitable
        except self._errors as exc:
            message = self._message_for(exc) if self._message_for else None
            raise ToolError(message if message is not None else str(exc)) from exc

    async def _connected(self) -> B:
        if self._bridge is None:
            client = self._factory()
            try:
                await client.connect()  # type: ignore[attr-defined]
            except self._connect_error as exc:
                raise ToolError(f"cannot connect to {self._app}: {exc}") from exc
            self._bridge = self._wrap(client)
        return self._bridge

    async def _reset(self) -> None:
        if self._bridge is not None:
            try:
                await self._bridge.client.close()  # type: ignore[attr-defined]
            except Exception:
                pass
            self._bridge = None
