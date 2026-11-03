"""Shared helpers for the test_dorico test modules."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
import pytest
import websockets

from ai_score_editing.core.token_store import TokenStore


def note(id: int, position: int, pitch: int, name: str, duration: int = 256, stream: int = 2, staff: int = 1) -> dict[str, Any]:
    return {"id": id, "type": "NoteEvent", "stream": stream, "staff": staff, "voice": 1,
            "position": position, "duration": duration, "pitch": pitch, "name": name}


EVENTS = [
    {"id": 0, "type": "TonalityDivisionEvent", "stream": 0, "staff": 0, "position": 0, "duration": 0},
    {"id": 1, "type": "BarDivisionEvent", "stream": 0, "staff": 0, "position": 0, "duration": 0},
    note(3, 0, 72, "C5"), note(4, 256, 71, "B4"), note(5, 512, 69, "A4"), note(6, 768, 67, "G4"),
    note(7, 1024, 65, "F4"), note(8, 1280, 64, "E4"),
]


# ------------------------------------------------------------------ client

class FakeDorico:
    """A local WebSocket server that answers like Dorico's Remote Control API."""

    def __init__(self, token: str = "tok-1") -> None:
        self.token = token
        self.received: list[dict[str, Any]] = []
        self.on_command = lambda command: None

    async def handler(self, ws: Any) -> None:
        async for raw in ws:
            message = json.loads(raw)
            self.received.append(message)
            kind = message["message"]
            if kind == "connect":
                if message.get("sessionToken") == self.token:
                    await ws.send(json.dumps({"message": "response", "code": "kConnected"}))
                    await ws.send(json.dumps({"message": "status", "canUndo": True, "notReadOnly": True}))
                else:
                    await ws.send(json.dumps({"message": "sessiontoken", "sessionToken": self.token}))
            elif kind == "acceptsessiontoken":
                await ws.send(json.dumps({"message": "response", "code": "kConnected"}))
                await ws.send(json.dumps({"message": "status", "canUndo": True, "notReadOnly": True}))
            elif kind == "getstatus":
                # Like Dorico: only fields that changed since the last status.
                await ws.send(json.dumps({"message": "selectionchanged"}))
                await ws.send(json.dumps({"message": "status", "hasSelection": True}))
            elif kind == "command":
                self.on_command(message["command"])
                await ws.send(json.dumps({"message": "response", "code": "kOK"}))


@pytest.fixture
async def dorico(tmp_path: Path) -> Any:
    fake = FakeDorico()
    async with websockets.serve(fake.handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        yield fake, port, TokenStore(tmp_path / "tokens.json")
