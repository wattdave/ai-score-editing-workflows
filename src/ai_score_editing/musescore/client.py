"""WebSocket client for the ScoreBridge plug-in running in MuseScore.

One request is in flight at a time: the plug-in runs on MuseScore's UI
thread and answers each message before reading the next. The client only
connects to 127.0.0.1, so the token never crosses the network.
"""

from __future__ import annotations

import asyncio
import itertools
import json
from typing import Any

import websockets

from . import install

DEFAULT_HOST = "127.0.0.1"
RECV_TIMEOUT = 30.0
RUN_HINT = f"In MuseScore, choose Plugins > {install.PLUGIN_TITLE}"


class MuseScoreError(Exception):
    """The bridge could not be reached, refused a request, or reported an error."""


class MuseScoreConnectionError(MuseScoreError):
    """The bridge could not be reached (the CLI exits 2)."""


class MuseScoreClient:
    def __init__(self, port: int = install.DEFAULT_PORT, token: str | None = None,
                 timeout: float = RECV_TIMEOUT) -> None:
        self.port = port
        self.token = token
        self.timeout = timeout
        self._ws: Any = None
        self._ids = itertools.count(1)
        self._lock = asyncio.Lock()
        #: Envelope fields of the last reply: bridge, mscoreVersion, score.
        self.last: dict[str, Any] = {}

    async def connect(self) -> None:
        if self.token is None:
            self.token = install.read_token()
        if not self.token:
            raise MuseScoreConnectionError("no bridge token: run 'musescore-cli install-plugin', restart MuseScore, "
                                 f"then {RUN_HINT}")
        try:
            self._ws = await websockets.connect(f"ws://{DEFAULT_HOST}:{self.port}", max_size=None)
        except OSError as exc:
            raise MuseScoreConnectionError(f"the MuseScore bridge is not running on port {self.port} ({exc}). "
                                 f"{RUN_HINT}") from exc

    async def close(self) -> None:
        if self._ws is not None:
            await self._ws.close()
            self._ws = None

    async def __aenter__(self) -> MuseScoreClient:
        await self.connect()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    async def call(self, method: str, args: dict[str, Any] | None = None,
                   timeout: float | None = None) -> Any:
        if self._ws is None:
            await self.connect()
        async with self._lock:
            request_id = next(self._ids)
            await self._ws.send(json.dumps({"id": request_id, "token": self.token, "method": method,
                                            "args": args or {}}))
            try:
                reply = json.loads(await asyncio.wait_for(self._ws.recv(), timeout or self.timeout))
            except TimeoutError:
                raise MuseScoreError("MuseScore did not answer: a dialog may be open there; "
                                     "dismiss it and try again") from None
        if reply.get("id") != request_id:
            raise MuseScoreError(f"reply for request {reply.get('id')} arrived for request {request_id}")
        self.last = {k: reply.get(k) for k in ("bridge", "mscoreVersion", "score")}
        if not reply.get("ok"):
            error = reply.get("error", "unknown error")
            if error == "unauthorised":
                raise MuseScoreError("the bridge refused the token: run 'musescore-cli install-plugin' "
                                     "and restart MuseScore")
            raise MuseScoreError(error)
        return reply.get("result")
