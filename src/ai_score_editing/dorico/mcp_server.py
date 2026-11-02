"""MCP server exposing Dorico to AI clients through bridge.lua.

Run with `uv run dorico-mcp` (stdio). It mirrors the Sibelius server's tools
(score_overview, score_structure, query_score, apply_batch, undo, save_score,
export_score) over Dorico's Remote Control API, keeping one connection and
serializing calls.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from ai_score_editing.cli_common import DEFAULT_LIMIT
from ai_score_editing.mcp_common import EXPORT, READ_ONLY, WRITE, env_port, parse_bars
from ai_score_editing.mcp_common import Session as CommonSession

from . import lyrics_dialog, service
from . import project_info as project_info_mod
from .bridge import DoricoBridge
from .client import DEFAULT_PORT, DoricoClient, DoricoError
from .score import DoricoBatchError

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


class Session(CommonSession[DoricoBridge]):
    """One lazily opened Dorico connection, used by one call at a time."""

    def __init__(self, factory: Callable[[], DoricoClient]) -> None:
        super().__init__("Dorico", factory, DoricoBridge, DoricoError, (DoricoError, DoricoBatchError))


def _default_client() -> DoricoClient:
    return DoricoClient(port=env_port("DORICO_PORT", DEFAULT_PORT))


session = Session(_default_client)


@server.tool(annotations=READ_ONLY)
async def score_overview(flow: int = 1) -> dict[str, Any]:
    """Describe the open Dorico project: title, flows, players, staves (with
    their voice streams), layouts, the last bar with music, and whether
    anything is selected. Call this first."""
    return await session.run(lambda b: service.overview(b, flow), retry=True)


@server.tool(annotations=READ_ONLY)
async def score_structure(flow: int = 1) -> dict[str, Any]:
    """Time signatures (as measured bar lengths), key signature positions,
    and the full score layout's page setup ("layout", in set-layout's terms).

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
    limit: int = DEFAULT_LIMIT,
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
    first, last = parse_bars(bars)
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
    - {"op":"delete-voice","staff":S,"voice":V,"fromBar":A,"toBar":B}:
      deletes everything in that voice that starts in bars A-B, lyrics
      included (a note held into the range is kept); runs after the batch's
      other operations, in its one undo step. Works on staves with lyrics.

    - {"op":"set-break","bar":B,"type":"system"|"none"}: add or remove a
      system break at the start of bar B. Must be the only kind of op in
      its batch: each added break selects a note in bar B and runs a Dorico
      command, two undo steps (the result's undoSteps says how many to undo;
      the user's selection in Dorico changes). A bar with no note or rest
      of its own gets a temporary rest to select, made and deleted around
      the command (four undo steps); refused only where every voice holds a
      note over the barline. The project must be Dorico's active one.

    - {"op":"set-time","bar":B,"numerator":N,"denominator":D[,"pickup":P]},
      {"op":"set-key","bar":B,"key":"Bb"[,"minor":true]},
      {"op":"set-barline","bar":B,"type":"double"|"final"|"start_repeat"|"end_repeat"[,"position":P]}:
      at the start of bar B (bar 1 replaces the opening signature or
      barline). pickup (1/256 quarters) makes the bar a pick-up of that
      length, then the meter. position puts a barline part-way through bar
      B (a repeat mid-bar, with no visible time signature); set a pick-up
      before placing such barlines. Later operations in the batch may not
      name bars after B. Remove a time signature with {"op":"delete","id":N}
      (ids from query_score types ["TimeSignature"]). Dorico places it at a selected item, so a note or rest on
      B's first beat is selected, or, where the bar starts with implicit
      rests only, a temporary rest made and deleted around it. Two undo
      steps each (selection + command), four with a temporary rest; refused
      where every voice holds a note over the barline.
    - {"op":"add-dynamic",...,"dynamic":"p"|"mf"|...}, {"op":"set-articulation",
      ...,"articulation":"accent"|"marcato"|"staccato"|"staccatissimo"|
      "tenuto"|"staccato-tenuto"|"stress"|"unstress"}, {"op":"add-slur",...}
      (to the next note), {"op":"add-tempo",...,"text":"Allegro"|"q=120"},
      {"op":"add-rehearsal-mark",...}: at a note addressed like set-pitch
      (works on staves with lyrics too). Two undo steps each; slurs cannot be
      checked afterwards (verified: false).
    - {"op":"add-line","line":"crescendo"|"diminuendo"|"8va"|"8vb"|"trill"|
      "pedal"|"glissando","staff":S,"bar":B,"position":P,"duration":D}: a line
      from the note or rest on staff S at that position (a temporary rest
      where there is none; trills and glissandos need a note), resized to D
      (a multiple of 32). A glissando runs to the next note and takes no
      duration. Hairpins cannot be read back (verified: false); the others
      are. Octave lines keep the sounding pitch, so Dorico rewrites the notes
      under them (unlike Sibelius). Undo steps: selection + command, plus the
      line's selection and one per resize step, plus two for a temporary rest.
    - {"op":"set-layout", ...}: any of pageSize ("letter", "a4", "a3", "a5",
      "tabloid", "legal", "executive", "statement", "concert", "octavo",
      "9.5x12.5", "10x13"), orientation ("portrait"/"landscape"), or
      pageWidth + pageHeight (mm), staffSize, topMargin, bottomMargin,
      leftMargin, rightMargin, aboveTopStaveGap, belowBottomStaveGap (mm),
      spacesBetweenStaves, spacesBetweenSystems (staff spaces), and
      hideEmptyStaves ("never"|"after-first-system"|"all-systems", for the
      whole layout). Changes the full score layout unless "layout" names
      another (name or layoutID). One undo step; every option is read back.
      score_structure reports the current settings as "layout".
    - {"op":"delete-bars","fromBar":A,"toBar":B}: removes the bars from every
      staff and moves the rest up; not the whole flow
    - {"op":"add-bars","count":N[,"bar":B]}: N bars of the meter in force
      inserted before bar B (selecting an item on B's first beat, or a
      temporary rest: 2 undo steps, 4 with the rest; refused past the end of
      the flow), or appended at the end without "bar" (one undo step per
      bar; not read back, verified: false). No "length": irregular bars are
      not supported. Later operations in the batch may not name bar B or
      after, which the insert moves.
    - {"op":"copy-passage","fromBar":A,"toBar":B,"topStaff":T,"bottomStaff":U,
      "destStaff":S,"destBar":D}: copies each staff's notes by Dorico's copy
      and paste (overwriting at the destination), anchored so the notes keep
      their places in the bar; checked afterwards. Needs a note in bar A on
      each staff with notes; refuses a destination under a sustained note.
    - {"op":"move-passage", ...same fields as copy-passage}: cuts instead of
      copies, so the source bars keep their place and hold rests, and the
      notes keep their ids at the destination. Checked afterwards: the source
      notes must be gone and no other note of either staff lost; otherwise
      the score is put back and the batch fails. One more undo step than
      copy-passage.
    - {"op":"add-lyrics","staff":S,"bar":B,"index":I (or "id"),"text":"ma-king lyr-ics _ now","verse":V}:
      lyrics typed into Dorico's lyric popover from that note on (spaces
      separate words, hyphens syllables, "_" continues a melisma), in verse
      V (1-10, default 1). Other verses are kept; the batch is refused if a
      syllable would land on a note that already has a lyric in verse V
      (use edit_lyrics to change existing words). One undo step for the
      selection, one per verse below V, and one per syllable; Dorico is
      brought to the front while it types, and the result's lyricsCheck
      compares a MusicXML export with the text.
      Command ops (set-break, set-time, set-key, set-barline, add-bars, delete-bars,
      set-layout, add-lyrics, the notation ops above) cannot share a batch
      with the others. set-bar-number and a ranged hide-empty-staves are
      not available on Dorico.

    No operation may target an event another operation already changes.
    Returns each operation's before/after events and the number applied.
    """
    return await session.run(lambda b: service.apply(b, operations, flow=flow, dry_run=dry_run), retry=False)


@server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False))
async def read_lyrics(staff: str | None = None, verse: int = 1, player: str | None = None) -> dict[str, Any]:
    """A player's line of lyrics as text, read from Dorico's Edit Lyrics dialog.

    staff is a staff number (as score_overview lists them) or the player's
    part layout name; player is the old, deprecated name for the same (pass
    one of the two). verse 1-5. The text is hyphenated as Dorico shows it ("ma-king"). For a
    two-staff player it is the first staff's line. The window briefly shows
    the part layout and Dorico comes to the front; it is switched back.
    The selections it makes are undone again, so the undo history is left as
    it was (a "note" in the result says when that could not be done).
    Syllables are not tied to notes here: use query_score for that.
    """

    async def action(b: DoricoBridge) -> dict[str, Any]:
        return await lyrics_dialog.read_lyrics(b, await service.resolve_player(b, staff, player), verse)

    return await session.run(action, retry=True)


@server.tool(annotations=WRITE)
async def edit_lyrics(
    staff: str | None = None, text: str = "", verse: int = 1, player: str | None = None
) -> dict[str, Any]:
    """Replace a player's line of lyrics with text (read it first with read_lyrics).

    staff is a staff number or the player's name; player is the old,
    deprecated name for the same (pass one of the two).

    The new text must have the same number of syllables (words split by
    spaces and hyphens): Dorico ignores edits that change the count, so they
    are refused. The result is read back and compared, and its undoSteps
    (3: two selections and the edit) is what undo needs to revert it. Use
    this to correct words or hyphenation; add-lyrics (apply_batch) adds new
    lyrics, including a further verse.
    """

    async def action(b: DoricoBridge) -> dict[str, Any]:
        return await lyrics_dialog.edit_lyrics(b, await service.resolve_player(b, staff, player), text, verse)

    return await session.run(action, retry=False)


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
async def save_score(path: str | None = None) -> dict[str, Any]:
    """Save the open project to its own file (Dorico's Save command; refused
    when the project has no file yet). With path, save a copy to that .dorico
    file instead: the open project keeps its own file, so this does not
    change where Cmd-S saves."""
    return await session.run(lambda b: service.save(b, path), retry=False)


@server.tool(annotations=EXPORT)
async def export_score(format: str = "pdf", path: str | None = None) -> dict[str, Any]:
    """Export the open project to path as pdf, musicxml, preview-pdf or preview-png.
    path is required: Dorico does not report the project's file name.

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
