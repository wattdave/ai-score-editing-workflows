# MuseScore (third party)

The `musescore` MCP server is [ghchen99/mcp-musescore](https://github.com/ghchen99/mcp-musescore),
pinned in `scripts/musescore_mcp.sh`. It has two parts:

```text
Claude Code ─stdio─> server.py (FastMCP, 26 tools)
                        │ JSON {"action", "params"} over ws://localhost:8765
                        ▼
              musescore-mcp-websocket.qml (MuseScore 4 plug-in, WebSocket server)
                        │ MuseScore plug-in API: curScore, Cursor, cmd()
                        ▼
                  the open score
```

This page compares it with `sibelius-mcp`, based on reading the code at
commit `66416a1`. It has not yet been tested against a running MuseScore.
The [musescore skill](../.claude/skills/musescore/SKILL.md) covers how to use it.

## How it differs

| | `sibelius-mcp` | `mcp-musescore` |
|---|---|---|
| Model | Address objects (staff, bar, index) and send batches | Move a cursor and type at it |
| Edits | `apply_batch`: every operation checked first, one undo step, backup before a real run | One undo step per call; `processSequence` runs steps one by one with no checks or rollback |
| Dry run and guards | `dry_run`, plus type/position guards on each address | None |
| Errors | Batch refused, nothing changed | `processSequence` ignores failing steps and reports success |
| Reads | Filtered queries, structure, overview | `get_score`: the whole score every time, notes, rests and lyrics only |
| Units | 1/256 quarter, 1-based bars and staves | 480 ticks per quarter, 0-based measures and staves |
| Connection | Sibelius Connect, approval dialog | Unauthenticated WebSocket on port 8765 of every network interface (MuseScore listens on `QHostAddress::Any`), so any device on the network can use it |

## Parity with the Sibelius back end

✅ equivalent, ⚠️ partial, ❌ missing.

| Sibelius tool / op | MuseScore | Notes |
|---|---|---|
| `score_overview` | ⚠️ | `get_score` gives title, measure count and staves as `staff0`... with short names; no instrument names, file or selection (`get_cursor_info` has the selection) |
| `score_structure` | ❌ | no key or time signatures, barlines, breaks or layout |
| `query_score` | ⚠️ | no filters: dumps every Chord and Rest with pitch, spelling, tie, tuplet flag and lyrics; no text, clefs, key/time signatures, lines, articulations or dynamics; no addresses for later edits |
| `apply_batch` + `dry_run` | ❌ | `processSequence` has none of the checks, atomicity or error reporting |
| `set` (Dx, Dy, Hidden, CueSize, Beam, ...) | ❌ | |
| `set-pitch` | ❌ | |
| `tie`, `bracket`, `flip-stem`, `nudge`, `beam` | ❌ | |
| `delete` | ⚠️ | `delete_selection`: the current selection or a whole measure |
| `add-note` | ⚠️ | `add_note` at the cursor, chords with `add_to_chord`; voice 1 only; overwrites what is there |
| (MuseScore only) `add_rest`, `add_tuplet` | ✅ | at the cursor |
| `add-text` | ❌ | only tempo text, through `processSequence`'s `setTempo` |
| `add-line` | ❌ | no slurs, hairpins or other lines |
| `add-lyric` | ⚠️ | `add_lyrics`: syllables onto consecutive notes from the cursor, verse number; no syllable type, melisma or editing existing lyrics |
| `transpose` | ❌ | |
| `copy-passage` | ❌ | |
| `set-key` | ❌ | |
| `set-time` | ⚠️ | `set_time_signature` at the cursor; no common/cut symbol |
| `set-break`, `set-barline`, `set-bar-number` | ❌ | |
| `add-bars` | ⚠️ | `append_measure`, `insert_measure` at the cursor; no irregular bars |
| `set-layout`, `hide-empty-staves` | ❌ | |
| `delete-voice` | ❌ | |
| (MuseScore only) `add_instrument` | ✅ | by MuseScore instrument id |
| (MuseScore only) `set_staff_mute`, `set_instrument_sound` | ❌ | the first hides the staff instead of muting it; the second only opens the Instruments panel |
| `undo` | ⚠️ | one step per call, no count; it is wrapped in its own `startCmd`/`endCmd` |
| `save_score` | ❌ | |
| `export_score` | ❌ | |

## What parity needs

[musescore-backend-plan.md](musescore-backend-plan.md) turns this outline
into a phased plan with probes and milestones.

Patching the upstream tools one by one would not get there. The gap is the
model: Sibelius parity needs addresses, guards, checked batches and filtered
reads. Most of the missing operations are things MuseScore's plug-in API can
already do. The upstream plug-in just doesn't expose them.

The most direct route is a MuseScore back end in this repository, built the
way `dorico/` was: a `musescore-mcp` with the same seven tools, reusing
`batch_ops` validation, `query` selectors and the result shapes. It would talk
to a QML bridge plug-in that this repository owns and installs, using the
upstream plug-in's WebSocket setup as the starting point. Parts the MuseScore
API seems to support, to confirm on MuseScore 4.7:

1. **Bridge.** A QML plug-in with one entry point per call, shaped like
   `sibwscli`: `GetScoreInfo`, `GetStaves`, `Query`, `ApplyBatch`, `Save`,
   `Export`. Add a token or origin check so other local processes cannot
   drive it.
2. **Reads.** Walk `curScore` segments and tracks for chords, rests, notes,
   lyrics, clefs, key and time signatures, and segment annotations
   (staff/system text, dynamics, tempo). Give each object staff, bar, index,
   type and position in 1/256 quarters (`ticks * 256 / 480`). For
   `score_structure` and anything the API hides, such as some spanners, read
   a MusicXML copy written with `writeScore`, as the Dorico back end does
   with its MusicXML export.
3. **Batches.** Run every operation of a batch between one
   `curScore.startCmd()` and `endCmd()`, so a batch is one undo step. For
   `dry_run`, apply the batch and call `endCmd(true)` to roll it back.
   MuseScore can roll back where Sibelius and Dorico can't, so a dry run would
   test the real edits rather than only checking them first.
4. **Edit operations,** grouped by how they would be done:
   - element properties: `set` (offset, `visible`, `small`), `set-pitch`
     (`pitch`, `tpc1`/`tpc2`), lyric `text`/`syllabic`, beam mode;
   - selection plus `cmd()`: `tie`, `flip-stem`, `bracket`, `copy-passage`
     (copy/paste), `transpose`, `delete`, slurs and hairpins;
   - `newElement` plus `Cursor.add`: `add-note` in any voice, `add-text`,
     `add-lyric`, `set-key`, `set-time`, `set-break` (layout breaks);
   - measure and style properties: `set-barline`, `set-bar-number`
     (number offset, exclude from count), irregular bars for `add-bars`,
     `set-layout` and `hide-empty-staves` (`curScore.style`).
5. **Save and export.** `writeScore(curScore, path, ext)` for `.mscz`,
   MusicXML, MXL, PDF, MIDI and PNG.
6. **Tests and live check.** Unit tests for the Python side as for Dorico,
   then a recorded live check like `docs/dorico.md`'s.

The upstream server can stay registered until the back end covers what
people use it for. Then `.mcp.json` would point `musescore` at the new
`musescore-mcp`.
