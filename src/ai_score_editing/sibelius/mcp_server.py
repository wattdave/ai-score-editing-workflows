"""MCP server exposing Sibelius to AI clients through the bridge plug-in.

Run with `uv run sibelius-mcp` (stdio). The server keeps one Sibelius Connect
session open and serializes calls, since Sibelius handles one message at a
time. Tools are deliberately coarse: find objects with query_score, change
them with apply_batch, and undo a batch as a single step.
"""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from ai_score_editing.sibelius import batch_ops
from ai_score_editing.cli_common import DEFAULT_LIMIT, canonical_format
from ai_score_editing.mcp_common import EXPORT, READ_ONLY, WRITE, env_port, parse_bars
from ai_score_editing.mcp_common import Session as CommonSession
from ai_score_editing.core.errors import QueryError
from ai_score_editing.sibelius import bridge, protocol, service
from ai_score_editing.sibelius.bridge import BRIDGE_PLUGIN, BUSY_MESSAGE, EXPORT_FORMATS, BridgeBusy, BridgeError
from ai_score_editing.core.barrange import parse_bar_range
from ai_score_editing.sibelius.client import ConnectionFailed, SibeliusClient

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


class Session(CommonSession[bridge.SibeliusBridge]):
    """One lazily opened Sibelius Connect session, used by one call at a time."""

    def __init__(self, factory: Callable[[], SibeliusClient]) -> None:
        super().__init__(
            "Sibelius", factory, bridge.for_client, ConnectionFailed,
            (BridgeError, QueryError, batch_ops.BatchError), _message_for,
        )


def _message_for(exc: Exception) -> str | None:
    if isinstance(exc, BridgeBusy):
        return BUSY_MESSAGE
    if isinstance(exc, BridgeError) and isinstance(exc.payload, str):
        return exc.payload
    return None


def _default_client() -> SibeliusClient:
    return SibeliusClient(
        host=os.environ.get("SIBELIUS_HOST", protocol.DEFAULT_HOST),
        port=env_port("SIBELIUS_PORT", protocol.DEFAULT_PORT),
        plugins=[BRIDGE_PLUGIN],
    )


session = Session(_default_client)


async def _backup(client: SibeliusClient, name: str) -> dict[str, Any]:
    """Back up the open score, into $SIBELIUS_BACKUP_DIR if set, else beside it."""
    return await service.backup(bridge.for_client(client), name, service.backup_folder())


async def _run(action: Callable[[bridge.SibeliusBridge], Awaitable[T]], *, retry: bool) -> T:
    """Run action on the session's bridge, turning service errors into tool errors."""
    return await session.run(action, retry=retry)


@server.tool(annotations=READ_ONLY)
async def score_overview() -> dict[str, Any]:
    """Describe the open score: title, file, bar count, staves (number and
    instrument names) and the current selection. Call this first; call
    score_structure for key and time signatures, barlines and breaks."""

    return await _run(service.overview, retry=True)


@server.tool(annotations=READ_ONLY)
async def score_structure(bars: str | None = None) -> dict[str, Any]:
    """Read the score's structure: key and time signatures, special barlines
    and system/page breaks, for bars such as "1-40" (default all), plus the
    score's page layout and staff spacing.

    Key and time signatures report the bar they take effect in (a change is
    stored at the end of the bar before; storedBar says which). Barline and
    break types use the names apply_batch's set-barline and set-break take;
    a barline or break at bar B sits at the end of bar B. layout (page size,
    orientation, staff size, margins and stave gaps in mm, page count) and
    engraving (spaces between staves and systems) use the names set-layout
    takes.
    """
    from_bar, to_bar = parse_bars(bars)
    return await _run(lambda b: service.structure(b, from_bar, to_bar), retry=True)


@server.tool(annotations=READ_ONLY)
async def query_score(
    staves: list[str] | None = None,
    bars: str | None = None,
    types: list[str] | None = None,
    voice: int | None = None,
    where: list[str] | None = None,
    fields: list[str] | None = None,
    limit: int = DEFAULT_LIMIT,
) -> dict[str, Any]:
    """Find bar objects in the open score.

    staves: staff numbers or instrument names (default all instruments); 0 or
    "system" is the system staff, with tempo and other system text and system
    lines such as rall. (only when asked for). bars: range such
    as "12-20" or "5" (default all). types: NoteRest, LyricItem, Text, Clef,
    KeySignature, TimeSignature, Tuplet, Line (any line), or a specific line
    type such as Slur. voice: 1-4. where: conditions that must all hold, e.g.
    "Pitch>=72" or "Bracketed=true" (any note of a chord), "StemFlipped=true",
    "Hidden=true", "Text='dolce'". fields:
    extra properties to return, e.g. ["Dx", "Dy"]; readable kinds are
    NoteRest, LyricItem, Text, Line, Clef, KeySignature, TimeSignature, Tuplet,
    Bar and Staff (one row per bar or staff: Length, InstrumentName, ...; Staff
    rows have bar 0, ignore bars, and need a non-system staff), BarRest, Comment, SymbolItem, SystemSymbolItem, InstrumentChange,
    RehearsalMark and GuitarFrame (chord symbols), with their documented
    simple properties plus Color, DrawOrder, Time and Voices on all; Text objects also give
    "InitialFontName" and "InitialFontSize" (1/32 spaces); LyricItem has no
    font properties, so read the font of lyric styles with sibelius-cli
    text-styles. Only allow-listed
    properties exist; an unknown one is rejected with the list.

    Returns {objects, count, truncated}. Each object has staff, bar, index,
    type and position: its address for apply_batch.
    """
    try:
        from_bar, to_bar = parse_bar_range(bars=bars) if bars else (None, None)
        service.query_selector(  # reject a bad query before connecting
            from_bar=from_bar, to_bar=to_bar, types=types, voice=voice, where=where, fields=fields, limit=limit
        )
    except (QueryError, ValueError) as exc:
        raise ToolError(str(exc)) from exc

    return await _run(
        lambda b: service.query(
            b, staves=staves, from_bar=from_bar, to_bar=to_bar, types=types, voice=voice,
            where=where, fields=fields, limit=limit,
        ),
        retry=True,
    )


@server.tool(annotations=WRITE)
async def apply_batch(operations: list[dict[str, Any]], dry_run: bool = False) -> dict[str, Any]:
    """Apply a list of edits to the open score as one undo step.

    Every operation is checked against the score before anything changes; if
    any check fails, nothing changes. A real run first saves the score in Sibelius
    to its file (so unsaved edits are kept), then copies that file as a backup
    (into $SIBELIUS_BACKUP_DIR if set, else beside the score). Addressed operations take staff, bar, index from
    query_score, plus optional type and position guards (recommended):

    - {"op":"set","staff":S,"bar":B,"index":I,"prop":P,"value":V}: Dx, Dy
      (int), Hidden, CueSize (bool) on anything; Beam, RestPosition on
      NoteRest; Text, Duration, NumNotes (melisma span) on LyricItem; Text on Text; Duration, RhDx on
      lines.
    - {"op":"set-pitch",...,"oldPitch":P,"newPitch":Q}
    - {"op":"tie"|"bracket",...[,"remove":true]}
    - {"op":"ficta",...,"accidental":"flat"|"natural"|"sharp"} or {"op":"ficta",...,"remove":true}: an
      editorial ficta, the small sign above a note, with the staff accidental hidden (bridge v63)
    - {"op":"flip-stem",...}
    - {"op":"nudge",...,"dx":X,"dy":Y}: move by relative offsets (1/32 space)
    - {"op":"delete",...} (a deleted NoteRest becomes a rest)

    Adding operations take staff, bar and position instead of index:

    - {"op":"add-note",...,"duration":D,"pitches":[..][,"voice":V,"tied":true]}
    - {"op":"add-tuplet-notes",...,"left":3,"right":2,"unit":128,"notes":[{"pitches":[..],
      "duration":D[,"tied":true]},...][,"voice":V]}: a tuplet bracket and its notes. Durations
      are written values from the start of the bracket and may total at most left * unit; empty
      pitches is a rest. To change a tuplet, delete it and add it again. Bridge v60
    - {"op":"add-text",...,"text":T[,"styleId":"text.staff.expression","voice":V]}
    - {"op":"add-line",...,"duration":D,"styleId":"line.staff.hairpin.crescendo"[,"voice":V]}
    - {"op":"add-lyric",...,"duration":D,"text":T[,"syllableType":"middle","voice":V,"verse":1-5,"dy":N]}
    - {"op":"set-lyric-verse","staff":S,"fromBar":A,"toBar":B,"verse":1-5[,"fromVerse":1-5,
      "voice":V,"position":P,"dy":N]}: move the staff's lyrics in bars A-B
      onto that verse line and set Dy (default -192 - 80*(verse-1)). Lyrics
      already on the line, and chorus/above lyrics, are left alone. Refused
      if a moved lyric would share a position and voice with another lyric
      on the target line. Bridge v59

    Staff 0 is the system staff. It takes set, delete, nudge, add-text and
    add-line, with system styles only and no voice: e.g. add-text with
    "styleId":"text.system.tempo" (the default there) or
    "text.system.metronome", add-line with "line.system.tempo.rall".

    Structural operations work on bar ranges or the whole score and must come
    after every operation above. Bars and staves refer to the score before the
    batch; no operation may name a bar after an earlier set-time's bar or
    at or after an earlier add-bars' insertion bar, and every set-time must come before any set-key, set-break or set-barline.

    - {"op":"beam","staff":S,"bar":B,"firstIndex":I,"lastIndex":J}: beam the
      NoteRests from I to J together (may sit among the operations above)
    - {"op":"transpose","fromBar":A,"toBar":B,"topStaff":T,"bottomStaff":U,
      "fromNote":"C","toNote":"D","direction":"up"|"down"[,"octaves":N]}
      (or "degree" and "intervalType" 0-10 instead of the notes)
    - {"op":"copy-passage","fromBar":A,"toBar":B,"topStaff":T,"bottomStaff":U,
      "destStaff":S,"destBar":D[,"destPosition":P]}: overwrites the
      destination; pasting past the last bar adds bars
    - {"op":"set-key","bar":B,"key":"Bb"[,"minor":true]}
    - {"op":"set-time","bar":B,"numerator":N,"denominator":D[,"symbol":"common"|"cut"]}:
      re-bars the music after it
    - {"op":"set-break","bar":B,"type":"system"|"page"|"none"}
    - {"op":"set-barline","bar":B,"type":"double"|"final"|"start_repeat"|
      "end_repeat"|"dashed"|"dotted"|"thick"|...|"none"}
    - {"op":"add-bars","count":N[,"bar":B,"length":L]}: appends bars at the
      end, or inserts them before bar B; length makes them irregular bars of
      L (1/256 quarters)
    - {"op":"delete-bars","fromBar":A,"toBar":B}: removes the bars from every
      staff (and the system staff) and moves the rest up; not the whole score
    - {"op":"set-bar-number","bar":B,"number":N[,"skip":true]}: renumber
      from bar B; skip leaves bar B itself unnumbered
    - {"op":"set-layout", any of "pageSize":"a4"|"letter"|..., "orientation":
      "portrait"|"landscape", "staffSize", "topMargin", "bottomMargin",
      "leftMargin", "rightMargin", "aboveTopStaveGap", "belowBottomStaveGap"
      (mm), "spacesBetweenStaves", "extraSpacesBelowVocalStaves",
      "spacesBetweenSystems" (staff spaces)}: only the given settings change
    - {"op":"delete-voice","fromBar":A,"toBar":B,"staff":S,"voice":V}
    - {"op":"clear-bars","fromBar":A,"toBar":B,"staff":S[,"voice":V]}: replace the bars with a bar
      rest, tuplets and slurs included, in every voice unless one is given. Bridge v60
    - {"op":"hide-empty-staves","fromBar":A,"toBar":B}: hide staves with
      nothing in bars A-B, then optimize staff spacing there

    Returns each operation's before/after description and the number applied.
    """
    try:
        batch = batch_ops.validate_batch(operations)  # reject a bad batch before connecting
    except batch_ops.BatchError as exc:
        raise ToolError(str(exc)) from exc

    return await _run(
        lambda b: service.apply(
            b, batch, dry_run=dry_run, backup_name="before apply_batch",
            backup_fn=lambda bb, name: _backup(bb.client, name),
        ),
        retry=False,
    )


@server.tool(annotations=WRITE)
async def undo(steps: int = 1) -> dict[str, Any]:
    """Undo the last change(s) in Sibelius. One apply_batch is one step.

    Undo reverts whatever was done last, including the user's own edits, so
    only call it right after the change you mean to revert.
    """
    if not 1 <= steps <= 20:
        raise ToolError("steps must be 1-20")
    return await _run(lambda b: service.undo(b, steps), retry=False)


@server.tool(annotations=WRITE)
async def save_score(path: str | None = None) -> dict[str, Any]:
    """Save the open score to its file. Fails if it has never been saved.

    A path (a copy under another name) is refused in Sibelius: saving as .sib
    would switch the open score to the new file."""

    return await _run(lambda b: service.save(b, path), retry=False)


@server.tool(annotations=EXPORT)
async def export_score(format: str = "pdf", path: str | None = None) -> dict[str, Any]:
    """Export the open score as musicxml, mxl, pdf, midi (or mid) or png.

    path defaults to the score's own file name with the format's extension.
    Image formats may produce one file per page (name_0001.png, ...).
    """
    format = canonical_format(format)
    if format not in EXPORT_FORMATS:
        raise ToolError(f"format must be one of: {', '.join(EXPORT_FORMATS)}")

    async def action(b: bridge.SibeliusBridge) -> dict[str, Any]:
        return {"files": (await service.export(b, format, path))["files"]}

    return await _run(action, retry=True)


def main() -> None:
    server.run("stdio")


if __name__ == "__main__":
    main()
