"""MCP server exposing Sibelius to AI clients through the bridge plug-in.

Run with `uv run sibelius-mcp` (stdio). The server keeps one Sibelius Connect
session open and serializes calls, since Sibelius handles one message at a
time. Tools are deliberately coarse: find objects with query_score, change
them with apply_batch, and undo a batch as a single step.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

import websockets
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from sibelius_websocket_cli import batch_ops, protocol
from sibelius_websocket_cli.cli import (
    BATCH_BRIDGE_VERSION,
    BRIDGE_PLUGIN,
    EXPORT_FORMATS,
    QUERY_BRIDGE_VERSION,
    BridgeError,
    _apply_batch,
    _backup,
    _export_path,
    _require_bridge,
    parse_bar_range,
)
from sibelius_websocket_cli.client import ConnectionFailed, SibeliusClient
from sibelius_websocket_cli.query import QueryError, build_selector, resolve_staves

T = TypeVar("T")

INSTRUCTIONS = """\
Controls the score open in Sibelius.

Workflow: score_overview to orient, query_score to find objects, then
apply_batch with dry_run=true, then apply_batch. A batch is one undo step;
undo reverts it. Prefer one batch over many small ones.

Addresses: every object is staff/bar/index as query_score reports it. Pass
the object's type and position from the query result with each addressed
operation; the batch refuses to run if the object there is not the one
expected. Addresses are read before the batch and stay correct while it runs.

Units: positions and durations are 1/256 of a quarter note (quarter = 256,
half = 512, whole = 1024; a 4/4 bar is 1024 long). Pitches are MIDI numbers
(60 = middle C). Dx/Dy are 1/32 of a staff space.

If a tool reports that Sibelius is busy, a dialog is open in Sibelius and a
person must dismiss it; do not retry until they have.
"""

server = MCPServer("sibelius", instructions=INSTRUCTIONS)


class Session:
    """One lazily opened Sibelius Connect session, used by one call at a time."""

    def __init__(self, factory: Callable[[], SibeliusClient]) -> None:
        self._factory = factory
        self._client: SibeliusClient | None = None
        self._lock = asyncio.Lock()

    async def run(self, action: Callable[[SibeliusClient], Awaitable[T]], *, retry: bool) -> T:
        """Run action on the session, reconnecting if the connection dropped.

        Only read-only actions retry: a write whose connection dropped may
        already have been applied, and repeating it could apply it twice.
        """
        async with self._lock:
            try:
                return await action(await self._connected())
            except (websockets.exceptions.ConnectionClosed, OSError):
                await self._reset()
                if not retry:
                    raise ToolError(
                        "the connection to Sibelius dropped during a change; it may or may not "
                        "have been applied. Check with query_score before trying again."
                    ) from None
                return await action(await self._connected())

    async def _connected(self) -> SibeliusClient:
        if self._client is None:
            client = self._factory()
            try:
                await client.connect()
            except ConnectionFailed as exc:
                raise ToolError(f"cannot connect to Sibelius: {exc}") from exc
            self._client = client
        return self._client

    async def _reset(self) -> None:
        if self._client is not None:
            try:
                await self._client.close()
            except Exception:
                pass
            self._client = None


def _default_client() -> SibeliusClient:
    return SibeliusClient(
        host=os.environ.get("SIBELIUS_HOST", protocol.DEFAULT_HOST),
        port=int(os.environ.get("SIBELIUS_PORT", protocol.DEFAULT_PORT)),
        plugins=[BRIDGE_PLUGIN],
    )


session = Session(_default_client)


async def _call(client: SibeliusClient, method: str, args: list[Any] | None = None) -> Any:
    """Call a bridge method, translating failures into tool errors."""
    response = await client.invoke_plugin(BRIDGE_PLUGIN, method, args)
    _raise_if_busy(response)
    if not protocol.is_success(response):
        raise ToolError(
            "the sibwscli bridge plug-in is not loaded; run "
            "'sibelius-websocket-cli install-plugin' and restart Sibelius"
        )
    value = protocol.plugin_return_value(response)
    if isinstance(value, dict) and "error" in value:
        raise ToolError(str(value["error"]))
    return value


def _raise_if_busy(response: dict[str, Any]) -> None:
    if response.get("message") == "busyError":
        raise ToolError(
            "Sibelius is busy: a dialog is probably open in Sibelius. Ask the user to "
            "dismiss it, then try again."
        )


async def _guarded(awaitable: Awaitable[T]) -> T:
    try:
        return await awaitable
    except BridgeError as exc:
        message = str(exc.payload) if isinstance(exc.payload, str) else str(exc)
        if "busyError" in message:
            _raise_if_busy({"message": "busyError"})
        raise ToolError(message) from exc


READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False)


@server.tool(annotations=READ_ONLY)
async def score_overview() -> dict[str, Any]:
    """Describe the open score: title, file, bar count, staves (number and
    instrument names) and the current selection. Call this first."""

    async def action(client: SibeliusClient) -> dict[str, Any]:
        return {
            "bridge": await _call(client, "GetBridgeVersion"),
            "score": await _call(client, "GetScoreInfo"),
            "staves": await _call(client, "GetStaves"),
            "selection": await _call(client, "GetSelectionInfo"),
        }

    return await session.run(action, retry=True)


@server.tool(annotations=READ_ONLY)
async def query_score(
    staves: list[str] | None = None,
    bars: str | None = None,
    types: list[str] | None = None,
    voice: int | None = None,
    where: list[str] | None = None,
    fields: list[str] | None = None,
    limit: int = 200,
) -> dict[str, Any]:
    """Find bar objects in the open score.

    staves: staff numbers or instrument names (default all). bars: range such
    as "12-20" or "5" (default all). types: NoteRest, LyricItem, Text, Clef,
    KeySignature, TimeSignature, Tuplet, Line (any line), or a specific line
    type such as Slur. voice: 1-4. where: conditions that must all hold, e.g.
    "Pitch>=72" or "Bracketed=true" (any note of a chord), "StemFlipped=true",
    "Hidden=true", "Text='dolce'". fields:
    extra properties to return, e.g. ["Dx", "Dy"]. Only allow-listed
    properties exist; an unknown one is rejected with the list.

    Returns {objects, count, truncated}. Each object has staff, bar, index,
    type and position: its address for apply_batch.
    """
    try:
        from_bar, to_bar = parse_bar_range(bars=bars) if bars else (None, None)
        selector = build_selector(
            staves=[], from_bar=from_bar, to_bar=to_bar, types=types or [],
            voice=voice, where=where or [], fields=fields or [], limit=limit,
        )
    except (QueryError, ValueError) as exc:
        raise ToolError(str(exc)) from exc

    async def action(client: SibeliusClient) -> dict[str, Any]:
        await _guarded(_require_bridge(client, QUERY_BRIDGE_VERSION, "query_score"))
        if staves:
            try:
                selector["staves"] = resolve_staves(
                    [str(s) for s in staves], await _call(client, "GetStaves")
                )
            except QueryError as exc:
                raise ToolError(str(exc)) from exc
        return await _call(client, "Query", [selector])

    return await session.run(action, retry=True)


@server.tool(annotations=WRITE)
async def apply_batch(operations: list[dict[str, Any]], dry_run: bool = False) -> dict[str, Any]:
    """Apply a list of edits to the open score as one undo step.

    Every operation is checked against the score before anything changes; if
    any check fails, nothing changes. A real run first saves a backup copy of
    the score file. Addressed operations take staff, bar, index from
    query_score, plus optional type and position guards (recommended):

    - {"op":"set","staff":S,"bar":B,"index":I,"prop":P,"value":V}: Dx, Dy
      (int), Hidden, CueSize (bool) on anything; Beam, RestPosition on
      NoteRest; Text, Duration on LyricItem; Text on Text; Duration, RhDx on
      lines.
    - {"op":"set-pitch",...,"oldPitch":P,"newPitch":Q}
    - {"op":"tie"|"bracket",...[,"remove":true]}
    - {"op":"flip-stem",...}
    - {"op":"delete",...} (a deleted NoteRest becomes a rest)

    Adding operations take staff, bar and position instead of index:

    - {"op":"add-note",...,"duration":D,"pitches":[..][,"voice":V,"tied":true]}
    - {"op":"add-text",...,"text":T[,"styleId":"text.staff.expression","voice":V]}
    - {"op":"add-lyric",...,"duration":D,"text":T[,"syllableType":"middle","voice":V]}

    Returns each operation's before/after description and the number applied.
    """
    try:
        batch = batch_ops.validate_batch(operations)
    except batch_ops.BatchError as exc:
        raise ToolError(str(exc)) from exc

    async def action(client: SibeliusClient) -> dict[str, Any]:
        await _guarded(_require_bridge(client, BATCH_BRIDGE_VERSION, "apply_batch"))
        result = await _guarded(_apply_batch(client, batch, True))
        if dry_run or "error" in result:
            if "error" in result:
                raise ToolError(f"{result['error']}; nothing was changed")
            return result
        backup = await _guarded(_backup(client, "before apply_batch"))
        result = await _guarded(_apply_batch(client, batch, False))
        result["backup"] = backup.get("copy")
        if "error" in result:
            applied = result.get("applied", 0)
            raise ToolError(
                f"{result['error']}; {applied} operation(s) were applied as one undo "
                "step. Call undo once to revert them."
            )
        return result

    return await session.run(action, retry=False)


@server.tool(annotations=WRITE)
async def undo(steps: int = 1) -> dict[str, Any]:
    """Undo the last change(s) in Sibelius. One apply_batch is one step.

    Undo reverts whatever was done last, including the user's own edits, so
    only call it right after the change you mean to revert.
    """
    if not 1 <= steps <= 20:
        raise ToolError("steps must be 1-20")

    async def action(client: SibeliusClient) -> dict[str, Any]:
        response = await client.invoke_commands(["undo"] * steps)
        _raise_if_busy(response)
        return {"undone": steps}

    return await session.run(action, retry=False)


@server.tool(annotations=WRITE)
async def save_score() -> dict[str, Any]:
    """Save the open score to its file. Fails if it has never been saved."""

    async def action(client: SibeliusClient) -> dict[str, Any]:
        return await _call(client, "Save")

    return await session.run(action, retry=False)


@server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False))
async def export_score(format: str, path: str | None = None) -> dict[str, Any]:
    """Export the open score as musicxml, mxl, pdf, midi or png.

    path defaults to the score's own file name with the format's extension.
    Image formats may produce one file per page (name_0001.png, ...).
    """
    if format not in EXPORT_FORMATS:
        raise ToolError(f"format must be one of: {', '.join(EXPORT_FORMATS)}")
    saveas_type, extension = EXPORT_FORMATS[format]

    async def action(client: SibeliusClient) -> dict[str, Any]:
        info = await _call(client, "GetScoreInfo")
        if not info.get("fileName") and not path:
            raise ToolError("the score has never been saved; pass path")
        out = _export_path(path, info["fileName"], extension)
        await _call(client, "ExportScore", [str(out), saveas_type])
        produced = [out] if out.exists() else sorted(out.parent.glob(f"{out.stem}_*{out.suffix}"))
        if not produced:
            raise ToolError(f"Sibelius reported the export but {out} does not exist")
        return {"files": [str(f) for f in produced]}

    return await session.run(action, retry=True)


def main() -> None:
    server.run("stdio")


if __name__ == "__main__":
    main()
