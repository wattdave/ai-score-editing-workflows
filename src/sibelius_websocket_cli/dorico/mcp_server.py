"""MCP server exposing Dorico to AI clients through bridge.lua.

Run with `uv run dorico-mcp` (stdio). It mirrors the Sibelius server's tools
(score_overview, score_structure, query_score, apply_batch, undo, save_score,
export_score) over Dorico's Remote Control API, keeping one connection and
serializing calls.
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

from sibelius_websocket_cli.cli import parse_bar_range

from . import lyrics_dialog, service
from . import project_info as project_info_mod
from .bridge import DoricoBridge
from .client import DEFAULT_PORT, DoricoClient, DoricoError
from .score import DoricoBatchError

T = TypeVar("T")

INSTRUCTIONS = """\
Controls the score open in Dorico (the active project, one flow at a time).

Workflow: score_overview to orient, query_score to find objects, then
apply_batch with dry_run=true, then apply_batch. A batch is one undo step;
undo reverts it.

Addresses: staff/bar/index as query_score reports them, or an event's id
(ids are stable in Dorico, even across undo). Pass the type and position
from the query result as guards. set-pitch replaces the note, so the note
gets a new id (reported in the result).

Units: positions and durations are 1/256 of a quarter note (quarter = 256,
a 4/4 bar is 1024 long); position is within the bar, flowPosition from the
start of the flow. Pitches are MIDI numbers (60 = middle C).

Reading bars measures them with a temporary edit that is undone at once, so
Dorico's redo history is cleared. If a tool reports that Dorico did not
answer, a dialog is probably open in Dorico and a person must dismiss it.
"""

server = MCPServer("dorico", instructions=INSTRUCTIONS)


class Session:
    """One lazily opened Dorico connection, used by one call at a time."""

    def __init__(self, factory: Callable[[], DoricoClient]) -> None:
        self._factory = factory
        self._bridge: DoricoBridge | None = None
        self._lock = asyncio.Lock()

    async def run(self, action: Callable[[DoricoBridge], Awaitable[T]], *, retry: bool) -> T:
        async with self._lock:
            try:
                return await self._guard(action(await self._connected()))
            except (websockets.exceptions.ConnectionClosed, OSError):
                await self._reset()
                if not retry:
                    raise ToolError(
                        "the connection to Dorico dropped during a change; it may or may not "
                        "have been applied. Check with query_score before trying again."
                    ) from None
                return await self._guard(action(await self._connected()))

    @staticmethod
    async def _guard(awaitable: Awaitable[T]) -> T:
        try:
            return await awaitable
        except (DoricoError, DoricoBatchError) as exc:
            raise ToolError(str(exc)) from exc

    async def _connected(self) -> DoricoBridge:
        if self._bridge is None:
            client = self._factory()
            try:
                await client.connect()
            except DoricoError as exc:
                raise ToolError(f"cannot connect to Dorico: {exc}") from exc
            self._bridge = DoricoBridge(client)
        return self._bridge

    async def _reset(self) -> None:
        if self._bridge is not None:
            try:
                await self._bridge.client.close()
            except Exception:
                pass
            self._bridge = None


def _default_client() -> DoricoClient:
    return DoricoClient(port=int(os.environ.get("DORICO_PORT", DEFAULT_PORT)))


session = Session(_default_client)

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False)


def _bars(bars: str | None) -> tuple[int | None, int | None]:
    try:
        return parse_bar_range(bars=bars) if bars else (None, None)
    except ValueError as exc:
        raise ToolError(str(exc)) from exc


@server.tool(annotations=READ_ONLY)
async def score_overview(flow: int = 1) -> dict[str, Any]:
    """Describe the open Dorico project: title, flows, players, staves (with
    their voice streams), layouts, the last bar with music, and whether
    anything is selected. Call this first."""
    return await session.run(lambda b: service.overview(b, flow), retry=True)


@server.tool(annotations=READ_ONLY)
async def score_structure(flow: int = 1) -> dict[str, Any]:
    """Time signatures (as measured bar lengths) and key signature positions.

    Dorico's scripting cannot read a time signature's numbers or a key
    signature's key, only where they are and how long the bars are.
    """
    return await session.run(lambda b: service.structure(b, flow), retry=True)


@server.tool(annotations=READ_ONLY)
async def query_score(
    staves: list[str] | None = None,
    bars: str | None = None,
    types: list[str] | None = None,
    voice: int | None = None,
    where: list[str] | None = None,
    flow: int = 1,
    limit: int = 200,
    lyrics: bool = False,
) -> dict[str, Any]:
    """Find events in a flow of the open Dorico project.

    staves: staff numbers or player names (default all); 0 or "system" is the
    global timebase (time and key signature events). bars: "12-20" or "5".
    types: NoteRest, Note, Rest, Text, Clef, TimeSignature, KeySignature,
    Tuplet, Dynamic, or Dorico names such as NoteEvent. voice: 1-8. where:
    conditions that must all hold, e.g. "Pitch>=72", "Name='Bb4'",
    "Duration<256". Each note of a chord is its own object.

    lyrics=true adds each note's lyrics (text, verse, syllable), read from a
    MusicXML export (slower; Dorico's export window opens and closes).
    Objects on staves with lyrics or tempo marks have "source": "dump":
    they can be selected and used by command ops but not changed by Lua ops.

    Returns {objects, count, truncated}. Each object has staff, bar, index,
    type and position (its address for apply_batch), plus id, flowPosition,
    duration, voice, and pitch and spelled name for notes.
    """
    first, last = _bars(bars)
    return await session.run(
        lambda b: service.query(
            b, flow=flow, staves=staves, from_bar=first, to_bar=last,
            types=types, voice=voice, where=where, limit=limit, lyrics=lyrics,
        ),
        retry=True,
    )


@server.tool(annotations=WRITE)
async def apply_batch(operations: list[dict[str, Any]], dry_run: bool = False, flow: int = 1) -> dict[str, Any]:
    """Apply a list of edits to a flow as one undo step.

    Every operation is checked against the score before anything changes.
    Addressed operations take staff, bar, index from query_score (or "id"),
    plus optional type and position guards:

    - {"op":"set-pitch",...,"oldPitch":P,"newPitch":Q[,"spelling":"Bb"]}:
      replaces the note, spelled as given (default C# Eb F# Ab Bb)
    - {"op":"delete",...}
    On staves with lyrics (objects with "source": "dump"), set-pitch, delete
    and transpose run as Dorico commands on the note's id: the note keeps its
    id and lyric, and the batch counts as a command batch (undoSteps).

    Adding operations take staff, bar and position (or flowPosition), and
    an optional voice (default 1; only voices that already exist):

    - {"op":"add-note",...,"duration":D,"pitches":[..][,"spellings":[..]]}
    - {"op":"add-rest",...,"duration":D}
    - {"op":"add-text",...,"text":T}
    - {"op":"add-clef",...,"clef":"treble"|"bass"|"percussion"|"tab"|"tab.4"}
      (no voice; goes on the staff)

    - {"op":"transpose","fromBar":A,"toBar":B,"topStaff":T,"bottomStaff":U,
      "fromNote":"C","toNote":"D","direction":"up"|"down"[,"octaves":N]}
      (or "semitones":N[,"steps":D]): respells every note in range.

    - {"op":"set-break","bar":B,"type":"system"|"none"}: add or remove a
      system break at the start of bar B. Must be the only kind of op in
      its batch: each added break selects a note in bar B and runs a Dorico
      command, two undo steps (the result's undoSteps says how many to undo;
      the user's selection in Dorico changes). Adding needs a note or rest
      that starts in bar B, and the project must be Dorico's active one.

    - {"op":"set-time","bar":B,"numerator":N,"denominator":D},
      {"op":"set-key","bar":B,"key":"Bb"[,"minor":true]},
      {"op":"set-barline","bar":B,"type":"double"|"final"|"start_repeat"|"end_repeat"}:
      at the start of bar B (not bar 1); needs a note or rest with an id on
      B's first beat. Two undo steps each (selection + command).
    - {"op":"add-dynamic",...,"dynamic":"p"|"mf"|...}, {"op":"set-articulation",
      ...,"articulation":"accent"|"marcato"|"staccato"|"staccatissimo"|
      "tenuto"|"staccato-tenuto"|"stress"|"unstress"}, {"op":"add-slur",...}
      (to the next note), {"op":"add-tempo",...,"text":"Allegro"|"q=120"},
      {"op":"add-rehearsal-mark",...}: at a note addressed like set-pitch
      (works on staves with lyrics too). Two undo steps each; slurs cannot be
      checked afterwards (verified: false).
    - {"op":"copy-passage","fromBar":A,"toBar":B,"topStaff":T,"bottomStaff":U,
      "destStaff":S,"destBar":D}: copies each staff's notes by Dorico's copy
      and paste (overwriting at the destination), anchored so the notes keep
      their places in the bar; checked afterwards. Needs a note in bar A on
      each staff with notes; refuses a destination under a sustained note.
    - {"op":"add-lyrics","staff":S,"bar":B,"index":I (or "id"),"text":"ma-king lyr-ics _ now","verse":V}:
      lyrics typed into Dorico's lyric popover from that note on (spaces
      separate words, hyphens syllables, "_" continues a melisma), in verse
      V (1-10, default 1). Other verses are kept; the batch is refused if a
      syllable would land on a note that already has a lyric in verse V
      (use edit_lyrics to change existing words). One undo step for the
      selection, one per verse below V, and one per syllable; Dorico is
      brought to the front while it types, and the result's lyricsCheck
      compares a MusicXML export with the text.
      Command ops (set-break, set-time, set-key, set-barline, add-lyrics,
      the notation ops above) cannot share a batch with the others.

    No operation may target an event another operation already changes.
    Returns each operation's before/after events and the number applied.
    """
    return await session.run(lambda b: service.apply(b, operations, flow=flow, dry_run=dry_run), retry=False)


@server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False))
async def read_lyrics(player: str, verse: int = 1) -> dict[str, Any]:
    """A player's line of lyrics as text, read from Dorico's Edit Lyrics dialog.

    player is a part layout name (as score_overview's players list them);
    verse 1-5. The text is hyphenated as Dorico shows it ("ma-king"). For a
    two-staff player it is the first staff's line. The window briefly shows
    the part layout and Dorico comes to the front; it is switched back.
    Syllables are not tied to notes here: use query_score for that.
    """
    return await session.run(lambda b: lyrics_dialog.read_lyrics(b, player, verse), retry=True)


@server.tool(annotations=WRITE)
async def edit_lyrics(player: str, text: str, verse: int = 1) -> dict[str, Any]:
    """Replace a player's line of lyrics with text (read it first with read_lyrics).

    The new text must have the same number of syllables (words split by
    spaces and hyphens): Dorico ignores edits that change the count, so they
    are refused. The result is read back and compared. Use this to correct
    words or hyphenation; add-lyrics (apply_batch) adds new lyrics, including
    a further verse.
    """
    return await session.run(lambda b: lyrics_dialog.edit_lyrics(b, player, text, verse), retry=False)


@server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False))
async def project_info() -> dict[str, Any]:
    """The project's Project Info fields (Title, Subtitle, Composer, Lyricist,
    Arranger, Copyright, ...), read from Dorico's Project Info dialog. These
    are what title pages and headers show through Dorico's text tokens."""
    return await session.run(lambda b: project_info_mod.read_project_info(b), retry=True)


@server.tool(annotations=WRITE)
async def set_project_info(fields: dict[str, str]) -> dict[str, Any]:
    """Set Project Info fields by name, e.g. {"Composer": "Traditional",
    "Arranger": "D. Watt"}; "" clears a field. Typed into Dorico's Project
    Info dialog (Dorico comes to the front), applied, and read back.
    Project-level fields only, not per-flow ones."""
    return await session.run(lambda b: project_info_mod.set_project_info(b, fields), retry=False)


@server.tool(annotations=WRITE)
async def undo(steps: int = 1) -> dict[str, Any]:
    """Undo the last change(s) in Dorico. One apply_batch is one step.

    Undo reverts whatever was done last, including the user's own edits, so
    only call it right after the change you mean to revert. Stops early if
    Dorico has nothing left to undo.
    """
    return await session.run(lambda b: service.undo(b, steps), retry=False)


@server.tool(annotations=WRITE)
async def save_score(path: str) -> dict[str, Any]:
    """Save a copy of the open project to a .dorico file at path. The open
    project keeps its own file, so this does not change where Cmd-S saves."""
    return await session.run(lambda b: service.save(b, path), retry=False)


@server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False))
async def export_score(path: str, format: str = "pdf") -> dict[str, Any]:
    """Export the open project to path as pdf, musicxml, preview-pdf or preview-png.

    pdf: the layout in Dorico's active window, every page, with Print mode's
    settings; Dorico also keeps its own copy next to the project and
    overwrites an earlier one. musicxml: the full score of flow 1, through
    Dorico's export window (opens and closes by itself; needs Accessibility
    permission). preview-*: the first page only.
    """
    return await session.run(lambda b: service.export(b, format, path), retry=True)


def main() -> None:
    server.run("stdio")


if __name__ == "__main__":
    main()
