---
name: musescore
description: Inspect, compose and edit the score open in MuseScore 4 (notes, pitches, chords, rests, tuplets, text, lyrics, dynamics, articulations, slurs, octave lines, clefs, tempo, transposition, key/time signatures, barlines, breaks, bar numbers, adding bars, copying bars, deleting voices, page layout, metadata, saving, exporting PDF/MusicXML/MIDI/audio, adding instruments, silencing staves) through this repository's MuseScore back end, the musescore MCP tools or musescore-cli. Use for MuseScore score requests and /musescore.
---

# Driving MuseScore

The `musescore` MCP server (`score_overview`, `score_structure`,
`query_score`, `apply_batch`, `undo`, `save_score`, `export_score`,
`project_info`, `set_project_info`, `read_lyrics`, `edit_lyrics`,
`add_instrument`, `set_staff_playback`) and `uv run musescore-cli` drive the
score open in MuseScore 4.6+, through this repository's plug-in
"ScoreBridge". Read [docs/musescore.md](../../../docs/musescore.md)
before anything unusual: it has the parity table and what MuseScore's
plug-in API can and cannot do.

## Setup

1. `uv run musescore-cli install-plugin`, then restart MuseScore (a changed
   plug-in only loads at startup).
2. Plugins → Manage plugins: enable "ScoreBridge" (once).
3. Plugins → ScoreBridge, in the window of the score to work on, every
   session. Each MuseScore window is its own process; the bridge serves the
   window it was started in.

If a tool says the bridge is not running, ask the user to do step 3. If it
says the bridge is an older version, steps 1-3. The bridge needs a token
(written by `install-plugin`), so other devices on the network cannot use
it.

## Workflow

1. `score_overview` (or `musescore-cli overview`): score, metadata, staves
   with transposition, bar count.
2. `query_score` to find objects. Each has staff, bar, index, type and
   position (its address), plus `ticks` (480 per quarter, exact for
   tuplets). Staff 0 is the system staff (tempo, system text, rehearsal
   marks); it is only listed when asked for.
3. `apply_batch` with `dry_run: true`, then for real. A dry run really makes
   the edits and rolls them back, so it catches what would fail. A real
   batch is one undo step and writes a MusicXML backup first.
4. Read back with `query_score` / `score_structure` and report exact results.

Units are the Sibelius tools': 1/256 of a quarter note, position within the
bar, MIDI pitches (concert). Bars count every measure from 1.

## Batch order

Object ops (set, set-pitch, tie, bracket, flip-stem, nudge, delete, beam)
come first, then adding ops (add-note, add-rest, add-tuplet, add-text,
add-lyric, add-line, add-clef, add-dynamic, set-articulation, add-slur,
add-tempo, add-rehearsal-mark), then structural ops. transpose and
delete-voice cannot follow adding ops or set-time/add-bars/delete-bars;
set-time comes before set-bar-number; one copy-passage and one delete-bars
per batch. delete-bars removes whole bars from every staff. The `apply_batch`
description lists every op's fields.

## Limits

- **No hairpins.** add-line refuses them: adding one crashed MuseScore
  twice. Slurs and octave lines work. Ask the user to add hairpins by hand.
- An empty voice 2-4 can only start where voice 1 has a note or rest
  starting. Durations are single note values (up to three dots) in the bar.
- `set` Beam takes MuseScore beam modes (0 auto, 1 none, 2 begin,
  5 middle); a lyric melisma is `Duration`, not `NumNotes`.
- hide-empty-staves is whole-score only. set-layout has no octavo, hymn,
  quarto, folio or us-band page sizes.
- `save_score` saves in place (as Cmd-S) and can copy the saved `.mscz` to a
  path. A score never saved is refused: ask the user to save it once.
- `export_score`: pdf, png, svg (one file per page when there are several),
  musicxml (`.musicxml`/`.xml`), mxl, mid, mp3, wav, flac, ogg.
- `set_project_info` is **not undoable**: the result has the old values.
  The title frame on the page is separate text and does not change.
- `edit_lyrics` needs the same syllable count; add or delete syllables with
  add-lyric / delete in a batch.
- `set_staff_playback` silences the notes there now (MuseScore's mixer is
  out of reach): notes added later still play until it is run again.

## Rules

- Never call `undo` unless the last change was yours and a read-back shows
  it happened: undo reverts the user's own edits too. Undo exactly the
  reported `undoSteps`.
- copy-passage overwrites the clipboard, even in a dry run.
- If a call says MuseScore did not answer, a dialog is open in MuseScore:
  ask the user to dismiss it; do not retry.
- `scripts/musescore_live_check.py` checks the whole back end on a scratch
  score; never run it on the user's own score.

The third-party server this replaced, ghchen99/mcp-musescore, is described
in [references/upstream-tools.md](references/upstream-tools.md) and
[references/upstream-architecture.md](references/upstream-architecture.md)
for history only. Its plug-in has no authentication; if the user still runs
"musescore-mcp-websocket", suggest removing it from
`~/Documents/MuseScore4/Plugins`.
