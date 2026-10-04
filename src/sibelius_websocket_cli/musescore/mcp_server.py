"""MCP server exposing MuseScore to AI clients through msbridge.qml.

Run with `uv run musescore-mcp` (stdio). It mirrors the Sibelius server's
tools as the MuseScore back end gains them (docs/musescore-backend-plan.md):
so far score_overview, score_structure, query_score, apply_batch and undo. One connection is
kept and calls are serialized.
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

from sibelius_websocket_cli.batch_ops import BatchError
from sibelius_websocket_cli.cli import parse_bar_range
from sibelius_websocket_cli.query import QueryError

from . import install, service
from .bridge import MuseScoreBridge
from .client import MuseScoreClient, MuseScoreError
from .score import MuseScoreBatchError

T = TypeVar("T")

INSTRUCTIONS = f"""\
Controls the score open in MuseScore 4, in the window where the
"{install.PLUGIN_TITLE}" plug-in was started (Plugins > {install.PLUGIN_TITLE}).

Workflow: score_overview to orient, query_score to find objects, then
apply_batch with dry_run=true, then apply_batch. A batch is one undo step;
undo reverts it. A dry run really makes the edits, then rolls them back.

Addresses: staff/bar/index as query_score reports them. Pass the type and
position (or ticks) from the query result as guards; MuseScore objects have
no lasting ids. Staff 0 is the system staff (system text, tempo, rehearsal
marks, voltas).

Units: positions and durations are 1/256 of a quarter note (quarter = 256);
ticks are MuseScore's own (480 per quarter), exact for tuplets. Pitches are
MIDI numbers (60 = middle C). Dx/Dy are 1/32 of a staff space, Dy up.

If a tool reports that MuseScore did not answer, a dialog is probably open
there and a person must dismiss it.
"""

server = MCPServer("musescore", instructions=INSTRUCTIONS)


class Session:
    """One lazily opened bridge connection, used by one call at a time."""

    def __init__(self, factory: Callable[[], MuseScoreClient]) -> None:
        self._factory = factory
        self._bridge: MuseScoreBridge | None = None
        self._lock = asyncio.Lock()

    async def run(self, action: Callable[[MuseScoreBridge], Awaitable[T]], *, retry: bool) -> T:
        async with self._lock:
            try:
                return await self._guard(action(await self._connected()))
            except (websockets.exceptions.ConnectionClosed, OSError):
                await self._reset()
                if not retry:
                    raise ToolError(
                        "the connection to MuseScore dropped during a change; it may or may not "
                        "have been applied. Check with query_score before trying again."
                    ) from None
                return await self._guard(action(await self._connected()))

    @staticmethod
    async def _guard(awaitable: Awaitable[T]) -> T:
        try:
            return await awaitable
        except (MuseScoreError, MuseScoreBatchError, BatchError, QueryError) as exc:
            raise ToolError(str(exc)) from exc

    async def _connected(self) -> MuseScoreBridge:
        if self._bridge is None:
            client = self._factory()
            try:
                await client.connect()
            except MuseScoreError as exc:
                raise ToolError(f"cannot connect to MuseScore: {exc}") from exc
            self._bridge = MuseScoreBridge(client)
        return self._bridge

    async def _reset(self) -> None:
        if self._bridge is not None:
            try:
                await self._bridge.client.close()
            except Exception:
                pass
            self._bridge = None


def _default_client() -> MuseScoreClient:
    return MuseScoreClient(port=int(os.environ.get("MUSESCORE_PORT", install.DEFAULT_PORT)))


session = Session(_default_client)

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False)


@server.tool(annotations=READ_ONLY)
async def score_overview() -> dict[str, Any]:
    """Versions, score name, metadata, staves (with transposition) and bar count."""
    return await session.run(service.overview, retry=True)


@server.tool(annotations=READ_ONLY)
async def score_structure(bars: str | None = None) -> dict[str, Any]:
    """Key and time signatures, special barlines and repeats, system/page
    breaks, bar number changes and irregular bars, for bars such as "1-40"
    (default all), plus the page layout (mm) and staff spacing (spaces).

    Names are the ones apply_batch's structural ops take. A barline or break
    at bar B is at the end of bar B; a start repeat at bar B starts bar B.
    Keys are concert keys; writtenKeys lists staves written in another key.
    """
    try:
        first, last = parse_bar_range(bars=bars) if bars else (None, None)
    except ValueError as exc:
        raise ToolError(str(exc)) from exc
    return await session.run(lambda bridge: service.structure(bridge, first, last), retry=True)


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
    """Find objects in the open score.

    staves: staff numbers or part names (default all); 0 or "system" is the
    system staff (only when asked for). bars: "12-20" or "5". types:
    NoteRest (or Chord, Rest), LyricItem, Text, Clef, KeySignature,
    TimeSignature, Tuplet, Line, a line type such as Slur or Hairpin, or a
    MuseScore type such as Dynamic or StaffText. voice: 1-4. where:
    conditions that must all hold, e.g. "Pitch>=72", "Bracketed=true" (any
    note of a chord), "StemFlipped=true", "Hidden=true", "Text='dolce'".
    fields: extra properties, e.g. ["Dx", "Dy"].

    Returns {objects, count, truncated}. Each object has staff, bar, index,
    type and position (its address for apply_batch), ticks, and msType.
    """
    try:
        first, last = parse_bar_range(bars=bars) if bars else (None, None)
    except ValueError as exc:
        raise ToolError(str(exc)) from exc
    return await session.run(
        lambda bridge: service.query(bridge, staves=staves, from_bar=first, to_bar=last, types=types,
                                     voice=voice, where=where, fields=fields, limit=limit),
        retry=True,
    )


@server.tool(annotations=WRITE)
async def apply_batch(operations: list[dict[str, Any]], dry_run: bool = False) -> dict[str, Any]:
    """Apply a list of edits to the open score as one undo step.

    Every address is checked before anything changes, and if any edit fails
    the whole batch is rolled back. A dry run makes the edits, reports each
    object before and after, and rolls them back. A real run first writes a
    MusicXML copy of the score as a record. Operations take staff, bar,
    index from query_score, plus type and position (or ticks) guards, and
    pitch to require a note of that pitch:

    - {"op":"set",...,"prop":P,"value":V}: Dx, Dy (int), Hidden, CueSize
      (bool) on anything; Beam (MuseScore beam mode: 0 auto, 1 none,
      2 begin, 5 middle) and RestPosition (rests, staff positions up) on
      NoteRest; Text and Duration (melisma length) on LyricItem; Text on
      Text; Duration on lines
    - {"op":"set-pitch",...,"oldPitch":P,"newPitch":Q[,"spelling":"Eb"]}:
      the note keeps its ties, lyrics and articulations
    - {"op":"tie"|"bracket",...[,"remove":true]}: every note of the chord;
      a tie needs a next note of the same pitch
    - {"op":"flip-stem",...}
    - {"op":"nudge",...,"dx":X,"dy":Y}: relative offsets (1/32 space)
    - {"op":"delete",...}: a deleted chord becomes a rest
    - {"op":"beam","staff":S,"bar":B,"firstIndex":I,"lastIndex":J}

    Adding ops come after the ops above. They place by staff, bar, position
    and voice (1-4); where nothing starts at the position, the rest covering
    it is split (never a note). An empty voice 2-4 can only start where
    voice 1 has a note or rest starting. Durations are single note values
    (up to three dots) within the bar:

    - {"op":"add-note","staff":S,"bar":B,"position":P,"duration":D,
      "pitches":[..][,"voice":V,"tied":true,"spellings":["Db",null]]}:
      joins a chord of the same start and length there; replaces rests;
      refuses to overlap other notes. Unspelled notes follow the key
    - {"op":"add-rest",...,"duration":D}: replaces whatever is there
    - {"op":"add-tuplet",...,"duration":D,"actual":3,"normal":2,
      "notes":[[60],[],[64,67]]}: chords of duration/normal each ([] rest)
    - {"op":"add-text",...,"text":T[,"styleId":"text.staff.expression"]}:
      expression, other staff styles make staff text; staff 0 system text
    - {"op":"add-lyric",...,"duration":D,"text":T[,"syllableType":"middle",
      "verse":N]}: on a note starting there; hyphens follow the verse
    - {"op":"add-line",...,"duration":D,"styleId":S}: line.staff.slur(.up/
      .down), line.staff.octava.plus8/.minus8; no hairpins (they crashed
      MuseScore)
    - {"op":"add-clef",...,"clef":"treble"|"treble-8vb"|"treble-8va"|
      "alto"|"tenor"|"bass"|"bass-8vb"|"percussion"}
    - At a note or rest by staff/bar/index (Dorico's ops):
      add-dynamic ("dynamic":"mf"), set-articulation ("articulation":
      staccato|tenuto|marcato|accent), add-slur (to the next note),
      add-tempo ("text":"q = 96" or "text" plus "bpm"), add-rehearsal-mark
      (next letter, or "text")

    Structural ops come last; bars are as read before the batch, and no op
    may name a bar after a set-time or add-bars (before a bar) moves it:

    - {"op":"transpose","fromBar":A,"toBar":B,"topStaff":T,"bottomStaff":U,
      "fromNote":"C","toNote":"D","direction":"up"[,"octaves":N]} (or degree
      and intervalType): respells notes; key signatures in range move too
    - {"op":"copy-passage","fromBar":A,"toBar":B,"topStaff":T,
      "bottomStaff":U,"destStaff":S,"destBar":D[,"destPosition":P]}:
      overwrites the destination, through the clipboard; one per batch
    - {"op":"set-key","bar":B,"key":"Bb"[,"minor":true]}: every staff,
      written keys worked out for transposing instruments
    - {"op":"set-time","bar":B,"numerator":N,"denominator":D
      [,"symbol":"common"|"cut"]}: re-bars what follows
    - {"op":"set-break","bar":B,"type":"system"|"page"|"none"}
    - {"op":"set-barline","bar":B,"type":T}: double, final, dashed, dotted,
      thick, invisible, normal/none at the end of bar B; start_repeat
      starts bar B, end_repeat ends it
    - {"op":"set-bar-number","bar":B,"number":N[,"skip":true]}: skip leaves
      bar B out of the count and gives the next bar N
    - {"op":"add-bars","count":N[,"bar":B,"length":L]}: append, or insert
      before bar B; length makes irregular bars
    - {"op":"set-layout",...}: pageSize, orientation, staffSize, margins,
      stave gaps (mm), spacesBetweenStaves, spacesBetweenSystems
    - {"op":"hide-empty-staves","fromBar":1,"toBar":LAST}: whole score only
    - {"op":"delete-voice","staff":S,"voice":V,"fromBar":A,"toBar":B}:
      voice 1 notes become rests; voices 2-4 are emptied

    transpose and delete-voice change notes as read, so they cannot follow
    adding ops or a set-time/add-bars in the same batch.
    """
    return await session.run(lambda bridge: service.apply(bridge, operations, dry_run=dry_run), retry=False)


@server.tool(annotations=WRITE)
async def undo(steps: int = 1) -> dict[str, Any]:
    """Undo the last change(s) in MuseScore; a batch is one step."""
    return await session.run(lambda bridge: service.undo(bridge, steps), retry=False)


def main() -> None:
    server.run("stdio")


if __name__ == "__main__":
    main()
