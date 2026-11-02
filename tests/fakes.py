"""Test doubles shared by the Sibelius tests."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

BUSY = {"message": "busyError"}


class FakeSibeliusClient:
    """A SibeliusClient whose ScoreBridge answers come from a table.

    ``replies`` maps a bridge method to its return value, or to a callable
    taking the call's args. A reply of ``{"message": "busyError"}`` is sent as
    Sibelius's busy answer. ``calls`` records every call as ``(method, args)``;
    ``invoke_commands`` calls appear as ``("invokeCommands", commands)`` and
    are answered from ``replies["invokeCommands"]`` (only busy matters).
    """

    def __init__(self, replies: dict[str, Any] | None = None) -> None:
        self.replies = replies or {}
        self.calls: list[tuple[str, Any]] = []
        self.connect = AsyncMock()
        self.close = AsyncMock()

    async def invoke_plugin(self, name: str, method: str, args: Any = None) -> dict[str, Any]:
        self.calls.append((method, args))
        reply = self.replies.get(method, {})
        if callable(reply):
            reply = reply(args)
        if isinstance(reply, dict) and reply.get("message") == "busyError":
            return reply
        return {"message": "invokePluginResponse", "result": True, "returnValue": reply}

    async def invoke_commands(self, commands: list[str]) -> dict[str, Any]:
        self.calls.append(("invokeCommands", commands))
        reply = self.replies.get("invokeCommands", {})
        if isinstance(reply, dict) and reply.get("message") == "busyError":
            return reply
        return {"message": "invokeCommandsResponse", "result": True}

    def methods(self) -> list[str]:
        return [method for method, _ in self.calls]
