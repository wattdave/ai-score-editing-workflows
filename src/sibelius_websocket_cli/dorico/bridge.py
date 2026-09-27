"""Run bridge.lua inside Dorico and read its answers.

Each call writes a small Lua request file that sets BRIDGE_REQUEST and
BRIDGE_RESPONSE and then runs bridge.lua, asks Dorico to run it with
Script.RunScript, and reads the JSON response file the bridge writes.

Positions and durations are in 1/256 of a quarter note, as in the Sibelius
back end. Dorico counts positions from the start of the flow; bar numbers
are worked out here from the bar lengths `measure_bars` finds.
"""

from __future__ import annotations

import json
import math
import os
import re
import time
import uuid
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

from .client import DoricoClient, DoricoError

UNITS = 256
RESPONSE_TIMEOUT = 30.0
_SAFE_PATH = re.compile(r"^[A-Za-z0-9_./ ~+-]+$")


def lua_literal(value: Any) -> str:
    """A Lua expression for a JSON-like value (dicts, lists, str, numbers, bools)."""
    if value is None:
        return "nil"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            raise ValueError("cannot send NaN or infinity to Lua")
        return repr(value)
    if isinstance(value, str):
        out = []
        for ch in value:
            code = ord(ch)
            if ch in '"\\':
                out.append("\\" + ch)
            elif ch == "\n":
                out.append("\\n")
            elif code < 32 or code == 127:
                out.append(f"\\{code:03d}")
            else:
                out.append(ch)
        return '"' + "".join(out) + '"'
    if isinstance(value, (list, tuple)):
        if any(item is None for item in value):
            raise ValueError("Lua arrays cannot hold nil")
        return "{" + ", ".join(lua_literal(item) for item in value) + "}"
    if isinstance(value, dict):
        items = []
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("Lua table keys must be strings")
            if item is not None:
                items.append(f"[{lua_literal(key)}] = {lua_literal(item)}")
        return "{" + ", ".join(items) + "}"
    raise ValueError(f"cannot send a {type(value).__name__} to Lua")


def default_workdir() -> Path:
    cache = os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache"))
    return Path(cache) / "sibelius-websocket-cli" / "dorico"


def bridge_script() -> Path:
    return Path(str(resources.files("sibelius_websocket_cli.dorico").joinpath("bridge.lua")))


@dataclass
class BarMap:
    """Bar numbers from bar divisions: (flow position, bar length) pairs."""

    divisions: list[tuple[int, int]]

    def segments(self) -> list[tuple[int, int, int]]:
        """(first bar, start position, bar length) for each division."""
        out: list[tuple[int, int, int]] = []
        bar = 1
        for i, (start, length) in enumerate(self.divisions):
            out.append((bar, start, length))
            if i + 1 < len(self.divisions):
                bar += max(1, math.ceil((self.divisions[i + 1][0] - start) / length))
        return out

    def locate(self, position: int) -> tuple[int, int]:
        """(bar, position within the bar) for a flow position."""
        found = (1, 0, self.divisions[0][1]) if self.divisions else (1, 0, 4 * UNITS)
        for segment in self.segments():
            if segment[1] <= position:
                found = segment
        bar, start, length = found
        offset = position - start
        return bar + offset // length, offset % length

    def position(self, bar: int, offset: int = 0) -> int:
        """The flow position of a bar and a position within it."""
        found = None
        for segment in self.segments():
            if segment[0] <= bar:
                found = segment
        if found is None:
            raise DoricoError(f"bar {bar} is before the first bar")
        first, start, length = found
        if not 0 <= offset < length:
            raise DoricoError(f"position {offset} is outside bar {bar}, which is {length} long")
        return start + (bar - first) * length + offset

    def bar_length(self, bar: int) -> int:
        return next(length for first, _, length in reversed(self.segments()) if first <= bar)


def fingerprint(events: list[dict[str, Any]]) -> list[tuple[Any, ...]]:
    return sorted(
        (e.get("stream"), e.get("id"), e.get("type"), e.get("position"), e.get("duration"), e.get("pitch"), e.get("text"))
        for e in events
    )


class DoricoBridge:
    def __init__(self, client: DoricoClient, workdir: Path | None = None) -> None:
        self.client = client
        self.workdir = workdir or default_workdir()
        self._bars: dict[tuple[Any, ...], BarMap] = {}

    async def call(self, action: str, **params: Any) -> Any:
        """Run one bridge action and return its result."""
        self.workdir.mkdir(parents=True, exist_ok=True)
        script = bridge_script()
        name = uuid.uuid4().hex
        request_path = self.workdir / f"request-{name}.lua"
        response_path = self.workdir / f"response-{name}.json"
        for path in (script, request_path):
            if not _SAFE_PATH.match(str(path)) or " " in str(path):
                raise DoricoError(f"Dorico cannot run a script from {path}; its path must not contain spaces or ?&=")
        request_path.write_text(
            f"BRIDGE_REQUEST = {lua_literal({'action': action, **params})}\n"
            f"BRIDGE_RESPONSE = {lua_literal(str(response_path))}\n"
            f"dofile({lua_literal(str(script))})\n"
        )
        try:
            await self.client.command(f"Script.RunScript?ScriptPath={request_path}")
            payload = self._wait_for(response_path)
        finally:
            request_path.unlink(missing_ok=True)
            response_path.unlink(missing_ok=True)
        if not payload.get("ok"):
            raise DoricoError(f"bridge {action} failed: {payload.get('error')}")
        return payload.get("result")

    @staticmethod
    def _wait_for(path: Path) -> dict[str, Any]:
        deadline = time.monotonic() + RESPONSE_TIMEOUT
        while not path.exists():
            if time.monotonic() > deadline:
                raise DoricoError(
                    "the Dorico bridge did not answer; check Dorico's Script console "
                    "(Script > Show Console) or application.log"
                )
            time.sleep(0.02)
        return json.loads(path.read_text())

    async def overview(self, flow: int = 1) -> dict[str, Any]:
        return await self.call("overview", flow=flow)

    async def read(self, flow: int = 1) -> list[dict[str, Any]]:
        return (await self.call("read", flow=flow))["events"]

    async def read_partial(self, flow: int = 1) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """(events, unreadable streams): what Lua can read, and what it cannot."""
        result = await self.call("read", flow=flow, skipUnreadable=True)
        return result["events"], result.get("unreadable") or []

    async def bars(self, flow: int = 1, events: list[dict[str, Any]] | None = None) -> BarMap:
        """The flow's bar map, measured once per set of bar divisions.

        Measuring edits the score (see bridge.lua's bars action), so the edit
        is undone at once and the score compared with a read taken before.
        If the undo reverted anything else, it is redone and an error raised.
        """
        events = events if events is not None else await self.read(flow)
        key = (flow, tuple((e["id"], e["position"]) for e in events if e["type"] == "BarDivisionEvent"))
        if key in self._bars:
            return self._bars[key]
        status = await self.client.status()
        if status.get("notReadOnly") is False:
            raise DoricoError("the score is read-only, so its bars cannot be measured")
        result = await self.call("bars", flow=flow)
        if result.get("created"):
            await self.client.command("Edit.Undo")
            after = await self.read(flow)
            if fingerprint(after) != fingerprint(events):
                await self.client.command("Edit.Redo")
                raise DoricoError(
                    "measuring bars left the score changed after undo; the undo was redone. "
                    "Check the score in Dorico."
                )
        if result.get("error"):
            raise DoricoError(f"could not measure bars: {result['error']}")
        bar_map = BarMap([(d["position"], d["length"]) for d in result["divisions"]])
        self._bars[key] = bar_map
        return bar_map

    async def apply(self, operations: list[dict[str, Any]], flow: int = 1, dry_run: bool = False) -> dict[str, Any]:
        return await self.call("apply", flow=flow, operations=operations, dryRun=dry_run)

    async def save(self, path: Path) -> dict[str, Any]:
        return await self.call("save", path=str(path))
