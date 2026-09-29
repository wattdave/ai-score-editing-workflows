---
name: dorico
description: Inspect and change the project open in Dorico (notes, pitches, chords, text, rests, transposition, dynamics, articulations, slurs, tempo, key/time signatures, barlines, lyrics, copying bars, adding bars, deleting voices, page layout, project info) through this repository's Dorico back end, the dorico MCP tools or dorico-cli. Use for Dorico score requests and /dorico.
---

# Driving Dorico

The `dorico` MCP server (`score_overview`, `score_structure`, `query_score`,
`apply_batch`, `undo`, `save_score`, `export_score`, `read_lyrics`,
`edit_lyrics`, `project_info`, `set_project_info`) and `uv run dorico-cli`
drive the project open in Dorico 6.2+. Read
[docs/dorico.md](../../../docs/dorico.md) before anything unusual: it lists
what Dorico's scripting can and cannot do, and why.

## Workflow

1. `score_overview` (or `dorico-cli overview`) to see flows, staves and voices.
2. `query_score` to find events. Each has staff, bar, index, type and
   position (its address), plus a stable `id`.
3. `apply_batch` with `dry_run: true`, then for real.
4. Read back with `query_score` and report exact results.

Units are the Sibelius tools': 1/256 of a quarter note, position within the
bar (`flowPosition` from the flow start), MIDI pitches. Give
`spelling`/`spellings` when the default (C# Eb F# Ab Bb) is wrong for the key.

## Two kinds of batch

- **Lua ops** (add-note, add-rest, add-text, add-clef, delete-voice, and
  set-pitch, delete, transpose on ordinary staves) run as one script: one
  undo step.
  set-pitch/transpose there replace the note, so its id changes.
- **Command ops** (set-time, set-key, set-barline, set-break, add-dynamic,
  set-articulation, add-slur, add-tempo, add-rehearsal-mark, add-line,
  add-bars, set-layout, copy-passage, add-lyrics, and edits to notes on staves with lyrics) drive Dorico's own
  commands. Each takes several undo steps; the result's `undoSteps` says how
  many. They cannot share a batch with Lua ops.

## Staves with lyrics

Lua cannot hand over the events of staves with lyrics (or a timebase with
tempo marks), so they are read from Dorico's `dump()`: objects have ids and
`"source": "dump"`. Command ops work on them; set-pitch, delete and
transpose are done by commands (the note keeps its id and lyric).
`query_score(lyrics=true)` adds lyric text from a MusicXML export.
`add-lyrics` adds lyrics in any verse (`"verse": 2`), keeping the others,
and refuses to type over existing lyrics in that verse; `read_lyrics` /
`edit_lyrics` read and correct a player's verse (same syllable count).

## Limits

- Signatures and barlines work at any bar (bar 1 replaces the opening
  signature; an empty bar gets a temporary rest, 4 undo steps), except
  where every voice holds a note over the barline. Breaks: the same, from
  bar 2 on. `add-slur` joins a note to the next only. `add-line` makes
  hairpins, 8va/8vb, trills, pedal lines and glissandos, but octave lines
  rewrite the notes (Dorico keeps the sounding pitch) and hairpin lengths
  cannot be read back.
  copy-passage pastes at the start of a bar only. add-bars inserts before
  an existing bar or appends; it cannot make irregular bars (`length`).
  set-layout changes one layout (the full score unless `layout` names a
  part); it has no extra gap below vocal staves, and hides empty staves only
  for a whole layout (`hideEmptyStaves`), not over a range of bars.
- Not reachable: bar numbers (set-bar-number), Sibelius line styles beyond
  the seven add-line kinds. Say so rather than approximating.

## Rules

- Never call `undo` unless the last change was yours and a read-back shows
  it happened: Dorico's undo reverts the user's own edits too. Undo exactly
  the reported `undoSteps`.
- Reads may briefly edit the score (bar measurement, voice probes) and undo
  it: this clears Dorico's redo history. Say so if the user may want to redo.
- Some ops bring Dorico to the front or open and close its dialogs (MusicXML
  export, lyrics, Project Info); the terminal needs Accessibility permission.
- If a call says Dorico did not answer, a dialog is open in Dorico: ask the
  user to dismiss it; do not retry.
- The first connection needs the user to accept Dorico's approval prompt.
