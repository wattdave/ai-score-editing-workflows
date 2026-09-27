---
name: dorico
description: Inspect and change the project open in Dorico (notes, pitches, chords, text, rests, transposition) through this repository's Dorico back end, the dorico MCP tools or dorico-cli. Use for Dorico score requests and /dorico.
---

# Driving Dorico

The `dorico` MCP server (`score_overview`, `score_structure`, `query_score`,
`apply_batch`, `undo`, `save_score`, `export_score`) and `uv run dorico-cli`
drive the project open in Dorico 6.2+. Read
[docs/dorico.md](../../../docs/dorico.md) before anything unusual: it lists
what Dorico's scripting cannot do.

## Workflow

1. `score_overview` (or `dorico-cli overview`) to see flows, staves and voices.
2. `query_score` to find events. Each has staff, bar, index, type and
   position (its address), plus a stable `id`.
3. `apply_batch` with `dry_run: true`, then for real. One batch is one undo
   step; `undo` reverts it.
4. Read back with `query_score` and report exact results.

Units are the Sibelius tools': 1/256 of a quarter note, position within the
bar (`flowPosition` from the flow start), MIDI pitches. `set-pitch` and
`transpose` replace notes, so their ids change; take new ids from the
result. Give `spelling`/`spellings` when the default (C# Eb F# Ab Bb) is
wrong for the key.

## Staves with lyrics

Dorico's scripting cannot read staves with lyrics, so reads of such a score
export MusicXML behind the scenes (Dorico's export window opens and closes;
the terminal needs Accessibility permission). Those staves' objects have
`"source": "musicxml"`, lyrics, and no `id`: you can add to them, but not
delete, re-pitch or transpose their existing notes. Say so rather than
trying.

## Rules

- Never call `undo` unless the last change was yours and a read-back shows
  it happened: Dorico's undo reverts the user's own edits too.
- Reading bars makes and undoes a temporary edit, which clears Dorico's redo
  history. Say so if the user may want to redo.
- Refuse or explain requests the back end cannot do (lyrics, slurs and
  other lines, dynamics, layout, key or time signature changes, full PDF or
  MusicXML export) instead of approximating them.
- If a call says Dorico did not answer, a dialog is open in Dorico: ask the
  user to dismiss it; do not retry.
- The first connection needs the user to accept Dorico's approval prompt.
