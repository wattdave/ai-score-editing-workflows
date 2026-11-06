"""MCP server exposing MuseScore to AI clients through msbridge.qml.

Run with `uv run musescore-mcp` (stdio). It mirrors the Sibelius server's
tools as the MuseScore back end gains them (docs/musescore-backend-plan.md):
score_overview, score_structure, query_score, apply_batch, undo, save_score,
export_score, project_info, set_project_info, read_lyrics, edit_lyrics,
add_instrument and set_staff_playback. One
connection is kept and calls are serialized.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from mcp.server.mcpserver import MCPServer

from ai_score_editing.core.errors import BatchError
from ai_score_editing.cli_common import DEFAULT_LIMIT
from ai_score_editing.mcp_common import EXPORT, READ_ONLY, WRITE, env_port, parse_bars
from ai_score_editing.mcp_common import Session as CommonSession
from ai_score_editing.core.errors import QueryError

from . import install, service
from .bridge import MuseScoreBridge
from .client import MuseScoreClient, MuseScoreError
from .score import MuseScoreBatchError

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


class Session(CommonSession[MuseScoreBridge]):
    """One lazily opened MuseScore connection, used by one call at a time."""

    def __init__(self, factory: Callable[[], MuseScoreClient]) -> None:
        super().__init__(
            "MuseScore", factory, MuseScoreBridge, MuseScoreError,
            (MuseScoreError, MuseScoreBatchError, BatchError, QueryError),
        )


def _default_client() -> MuseScoreClient:
    return MuseScoreClient(port=env_port("MUSESCORE_PORT", install.DEFAULT_PORT))


session = Session(_default_client)


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
    first, last = parse_bars(bars)
    return await session.run(lambda bridge: service.structure(bridge, first, last), retry=True)


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
    """Find objects in the open score.

    staves: staff numbers or part names (default all); 0 or "system" is the
    system staff (only when asked for). bars: "12-20" or "5". types:
    NoteRest (or Chord, Rest), GraceNote (read-only), LyricItem, Text, Clef,
    KeySignature, TimeSignature, Tuplet, Line, a line type such as Slur or Hairpin, or a
    MuseScore type such as Dynamic or StaffText. voice: 1-4. where:
    conditions that must all hold, e.g. "Pitch>=72", "Bracketed=true" (any
    note of a chord), "StemFlipped=true", "Hidden=true", "Text='dolce'".
    fields: extra properties, e.g. ["Dx", "Dy"].

    Returns {objects, count, truncated}. Each object has staff, bar, index,
    type and position (its address for apply_batch), ticks, and msType.
    """
    first, last = parse_bars(bars)
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
    - {"op":"ficta",...,"accidental":"flat"|"natural"|"sharp"|"remove":true}:
      hides the chord's staff accidental and adds the sign as small text
      above the note (editorial ficta); the added text takes an index in
      the bar, so query again before the next batch
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
      .down), line.staff.octava.plus8/.minus8, line.staff.hairpin.crescendo
      (no diminuendo)
    - {"op":"add-clef",...,"clef":"treble"|"treble-8vb"|"treble-8va"|
      "alto"|"tenor"|"bass"|"bass-8vb"|"percussion"}
    - At a note or rest by staff/bar/index (Dorico's ops):
      add-dynamic ("dynamic":"mf"), set-articulation ("articulation":
      staccato|tenuto|marcato|accent), add-slur (to the next note),
      add-tempo ("text":"q = 96" or "text" plus "bpm"), add-rehearsal-mark
      (next letter, or "text")

    Structural ops come last; bars are as read before the batch, and no op
    may name a bar after a set-time, add-bars (before a bar) or delete-bars moves it:

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
    - {"op":"delete-bars","fromBar":A,"toBar":B}: removes the bars from
      every staff and moves the rest up; not the whole score
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


@server.tool(annotations=WRITE)
async def save_score(path: str | None = None) -> dict[str, Any]:
    """Save the score to its own file, as File > Save does; with path (same
    extension, .mscz), also copy the saved file there. A score that has never
    been saved is refused: save it once in MuseScore first."""
    return await session.run(lambda bridge: service.save(bridge, path), retry=False)


@server.tool(annotations=EXPORT)
async def export_score(format: str = "pdf", path: str | None = None) -> dict[str, Any]:
    """Export the whole score to path as pdf, png, svg, musicxml, mxl, midi
    (or mid), mp3, wav, flac or ogg (the path's extension must match; without
    path the score's own file name is used). png and svg
    write one file per page (name-1.png, name-2.png, ...) when there is more
    than one. Audio uses MuseScore's playback sounds and can take a while.
    Returns the files written."""
    return await session.run(lambda bridge: service.export(bridge, format, path), retry=True)


@server.tool(annotations=READ_ONLY)
async def project_info() -> dict[str, Any]:
    """The score's metadata (File > Project properties): workTitle, subtitle,
    composer, lyricist, arranger, translator, copyright, poet, movementTitle,
    movementNumber, workNumber, creationDate, source. Headers and footers
    show these; the title frame on the first page is separate text."""
    return await session.run(service.project_info, retry=True)


@server.tool(annotations=WRITE)
async def set_project_info(fields: dict[str, str]) -> dict[str, Any]:
    """Set metadata fields by name, e.g. {"composer": "Traditional",
    "arranger": "D. Watt"} ("title" means workTitle; "" clears a field).
    MuseScore does not record these for undo: the result has the old values
    to set back. The title frame text on the page does not change."""
    return await session.run(lambda bridge: service.set_project_info(bridge, fields), retry=False)


@server.tool(annotations=READ_ONLY)
async def read_lyrics(staff: str, verse: int = 1) -> dict[str, Any]:
    """A staff's lyrics in one verse as a line of text, hyphenated within
    words ("ma-king"), with the syllable count and the bars it spans. staff
    is a staff number or part name (the first staff of a multi-staff part).
    Syllables are not tied to notes here: use query_score for that."""
    return await session.run(lambda bridge: service.read_lyrics(bridge, staff, verse), retry=True)


@server.tool(annotations=WRITE)
async def edit_lyrics(staff: str, text: str, verse: int = 1) -> dict[str, Any]:
    """Replace a staff's verse with text (read it first with read_lyrics).

    The text must have the same number of syllables (words split by spaces,
    then hyphens): each syllable stays on its note, and its text and
    hyphenation change. One undo step. Use apply_batch's add-lyric and delete
    to add or remove syllables.
    """
    return await session.run(lambda bridge: service.edit_lyrics(bridge, staff, text, verse), retry=False)


@server.tool(annotations=WRITE)
async def add_instrument(instrument: str, dry_run: bool = False) -> dict[str, Any]:
    """Add a part at the bottom of the score: a MuseScore instrument id
    (violin, flute, soprano, alto, tenor, bass, piano, bb-clarinet, ...), a
    MusicXML sound id (strings.violin) or an instrument name. One undo step;
    a dry run adds it and rolls it back. Returns the new part's staves."""
    return await session.run(lambda bridge: service.add_instrument(bridge, instrument, dry_run=dry_run),
                             retry=False)


@server.tool(annotations=WRITE)
async def set_staff_playback(staves: list[str], play: bool, voices: list[int] | None = None) -> dict[str, Any]:
    """Silence (play=false) or restore (play=true) staves in playback and
    audio export, for voices 1-4 (default all). staves are numbers or part
    names. MuseScore's mixer is out of reach of plug-ins, so this turns off
    each note's playback and the staff's voice playback flags: notes added
    later still play until it is run again, and play=true also restores
    notes silenced one by one. One undo step per staff."""
    return await session.run(lambda bridge: service.set_staff_playback(bridge, staves, play, voices), retry=False)


def main() -> None:
    server.run("stdio")


if __name__ == "__main__":
    main()
