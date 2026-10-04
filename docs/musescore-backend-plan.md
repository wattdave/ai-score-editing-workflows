# MuseScore back end: plan

Goal: a `musescore-mcp` and `musescore-cli` that drive the score open in
MuseScore 4 the way `sibelius-mcp` and `dorico-mcp` drive theirs: the same
seven tools, staff/bar/index addresses with type and position guards,
1/256-quarter units, MIDI pitches, checked batches that are one undo step,
and a dry run. It replaces the third-party `mcp-musescore` server
([musescore.md](musescore.md)) once it covers what that server is used for.

The Dorico back end is the model. It got to parity by probing first
(every behaviour in [dorico.md](dorico.md) is dated and measured), keeping
all planning in pure Python that tests can reach, and landing in small PRs.
This plan follows the same route.

## What is already known

Established on this machine (MuseScore Studio 4.7.5, macOS), 2026-10-03:

- A QML plug-in can run a WebSocket server:
  `api.websocketserver.listen(port, onConnect)`, `onMessage(id, fn)`,
  `send(id, text)`. The upstream plug-in answered `ping` and `getScore`
  through it. MuseScore's bundled `dev_test_websocket` plug-in also shows a
  client side, `api.websocket.open(port, fn)`.
- A plug-in appears in the Plugins menu under its `title` property, or its
  file name when it has none. `menuPath` is ignored, which is why the
  upstream plug-in shows as "musescore-mcp-websocket".
- Enabling a plug-in in the Plugin Manager doesn't start it. The user has
  to run it from the Plugins menu in every MuseScore session. Nothing
  listens on the port until they do.
- The 4.7.5 binary contains the symbols `startCmd`, `endCmd`, `writeScore`,
  `newElement`, `selectRange` and `websocketserver`. That they're present
  doesn't show how they behave; that is phase 0's job.
- Positions in the plug-in API are ticks at 480 per quarter. Measures and
  staves are 0-based.
- Generated elements have to be skipped. In the test score, bars 9, 19
  and 29 reported 20 elements where the other bars had 8, and bar 32 had 12.
  The likely explanation is that the upstream walk counted the clefs, key
  and time signatures MuseScore draws at the start of each system, and the
  final barline. These aren't objects a user placed.

## Architecture

```text
musescore-mcp / musescore-cli
  └─ musescore/client.py    WebSocket client, ws://127.0.0.1:8766, token
       └─ msbridge.qml      this repository's plug-in, inside MuseScore
            └─ MuseScore plug-in API: curScore, Cursor, newElement,
               startCmd/endCmd, cmd(), writeScore
```

New package `src/sibelius_websocket_cli/musescore/`, shaped like `dorico/`:

| Module | Role |
|---|---|
| `msbridge.qml` | The plug-in: one handler per method, no planning logic |
| `client.py` | Connect, authenticate, send one request at a time, timeouts, "plug-in not running" errors |
| `bridge.py` | Typed calls (`read`, `apply`, `write_copy`, `undo`), bridge version check, tick/unit conversion |
| `score.py` | Pure Python: locate objects, assign indices, filter queries, check guards, turn a validated batch into bridge primitives |
| `mscx_read.py` | Parse a `.mscx` copy for structure, layout and anything the plug-in can't see |
| `service.py` | Snapshot, overview, structure, query, apply, undo, save, export |
| `install.py` | Install the plug-in with its token and version |
| `mcp_server.py`, `cli.py` | Same tools and subcommands as Dorico |

`pyproject.toml` gets `musescore-cli` and `musescore-mcp` entry points.
Shared code is reused, not copied: `batch_ops.validate_batch` and its
constants, `query.build_selector` / `parse_where`, `cli.parse_bar_range`,
`intervals.compute_transposition`, and the Session pattern from both MCP
servers. Code that the Dorico back end keeps in `dorico/score.py` but isn't
Dorico-specific (spelling, `transpose_spelled`, `interval_of`, lyric
parsing) moves to a shared module first, in its own PR.

### Wire protocol

Request: `{"id": n, "token": t, "method": "Query", "args": {...}}`.
Reply: `{"id": n, "ok": true, "result": ...}` or
`{"id": n, "ok": false, "error": "..."}`. Every reply also carries
`bridge` (version) and `score` (title, file path, measure count), so Python
notices when the active tab changed between calls.

- **Port 8766**, overridable with `MUSESCORE_PORT`, so that it doesn't clash
  with the upstream plug-in on 8765 while both exist.
- **Token.** `musescore-cli install-plugin` generates a token, stores it in
  `~/.config/sibelius-websocket-cli/musescore-token`, and writes it into the
  installed QML. The plug-in refuses any request without it. Today any
  local process can drive the upstream plug-in.
- **Methods:** `GetBridgeVersion`, `GetScoreInfo`, `GetStaves`, `Read`
  (bars, staves), `ApplyBatch` (primitives, dryRun), `WriteCopy` (path,
  format), `Undo` (steps), `Save`.
- **Plug-in name.** The `title` is "sibwscli bridge", which is the name
  people will see in the menu. Docs, the setup skill and error messages use
  that name.

## Model

### Addresses

- **staff:** 1-based (MuseScore staff index + 1). Staff 0 is the system
  staff (tempo, system text, rehearsal marks), as on Sibelius.
- **bar:** 1-based measure order. Every measure counts, pick-ups and split
  bars included, as on the other back ends, and frames (title VBox, HBox)
  don't. Reads also report MuseScore's displayed number (`displayNumber`),
  which differs after a pick-up, an excluded measure or a number offset.
- **index:** The object's position in a fixed walk of the staff's bar:
  segments in tick order. Within a segment come clefs, then key and time
  signatures, then annotations (text, dynamics, tempo) in track order, then
  chords and rests in voice order, then lyrics by verse. Spanners (slurs,
  hairpins, lines) come at their start segment after the chord they start on.
  One function in `score.py` defines this order, and a test pins it down.
- **Guards:** `type` and `position` as on Sibelius, plus `pitch` for notes.
  MuseScore elements have no ids that survive between calls, so these
  guards are the only check that the object is still the one that was read.
  The bridge resolves every address to an element before the first edit
  (the Sibelius lesson in SPEC.md 1.3.1) and checks each guard against it.
- **Score guard.** A batch carries the score fingerprint from its snapshot:
  path, measure count, and a hash of the bar contents it touches. It's
  refused if the user switched tabs or edited those bars in between.

### Units

`units = ticks * 256 / 480` (`* 8 / 15`). Whole, half, quarter, eighth,
sixteenth and thirty-second positions convert exactly. Tuplet positions
don't: a triplet eighth is 160 ticks, or 85⅓ units. Every object therefore
also carries its exact `ticks`. Addresses and guards accept either value,
with units rounded to the nearest integer. Adding at a tuplet position
takes `ticks`. Sibelius has the same rounding at 256 per quarter, so the
tools look the same either way.

### Types

| MuseScore element | Reported as | Notes |
|---|---|---|
| Chord, Rest | `NoteRest` | notes with pitch, spelling (tpc), tie, parentheses; rest flag |
| Lyrics | `LyricItem` | text, verse, syllabic, melisma end |
| StaffText, Expression, Dynamic, InstrumentChange | `Text` | `styleId` mapped to Sibelius names where one fits |
| SystemText, TempoText, RehearsalMark | `Text` on staff 0 | |
| Clef, KeySig, TimeSig | `Clef`, `KeySignature`, `TimeSignature` | no generated ones |
| Tuplet | `Tuplet` | ratio, span |
| Slur, Hairpin, Ottava, Pedal, Trill, TextLine, Volta | `Line` + `lineType` | `Slur` etc. as a specific type, as on Sibelius |
| Articulation, Fermata | properties of the NoteRest | `articulations`, as on Dorico |

Allow-listed fields: `Dx`/`Dy` (offset in spatium × 32, the Sibelius
unit), `Hidden` (`!visible`), `CueSize` (`small`), `StemFlipped`
(`stemDirection`), `Beam` (`beamMode`), `Bracketed` (note parentheses),
plus `Pitch`, `Text`, `Voice`.

## Reads

- **`score_overview`:** title and metadata tags, file path, dirty flag,
  measure count, parts with instrument names and staves, and the current
  selection.
- **`query_score`:** The bridge returns the raw objects for the requested
  bars and staves. `score.query` assigns indices, applies `types`, `voice`,
  `where` and `fields` with the shared selector code, and truncates at
  `limit`, as the Dorico back end does.
- **`score_structure`:** Key and time signatures, barlines, repeats and
  voltas, layout breaks, irregular measures and bar-number offsets, page
  and staff layout. Most of it can be read live (measure properties,
  `curScore.style`). Anything the plug-in API can't reach comes from a
  `.mscx` copy that `WriteCopy` writes to
  `~/.cache/sibelius-websocket-cli/musescore/`. That copy holds the full
  current score, saved or not, and `mscx_read.py` parses it. Unlike
  Dorico's MusicXML export, it needs no UI scripting and loses nothing.
  Phase 0 checks that writing a copy leaves the score's own path and dirty
  flag alone.
- **Lyrics:** `read_lyrics` and `edit_lyrics` (Dorico has these, Sibelius
  doesn't) are easy here, since the plug-in can read and write lyric text
  and syllabic directly, with no dialog.

## Batches

1. `batch_ops.validate_batch`, then `score.prepare_batch` against a fresh
   snapshot. This resolves addresses, checks guards and bar order, refuses
   what MuseScore can't do (a `NOT_ON_MUSESCORE` table like Dorico's), and
   emits primitives that name elements by (staff index, track, tick, kind,
   ordinal at that tick).
2. **Bridge `ApplyBatch`:** resolve every primitive's element, then
   `curScore.startCmd()`, run the primitives in order, `curScore.endCmd()`.
   If any primitive throws, `endCmd(true)` rolls the whole batch back.
   Partial batches can't happen, unlike on Sibelius.
3. **`dry_run`:** Run the batch for real, describe each object before and
   after, then `endCmd(true)`. Sibelius and Dorico can only check a batch
   before running it. If rollback is exact, a MuseScore dry run proves the
   batch works.
4. **Backup:** Before a real run, write a `.mscz` copy of the current state
   (unsaved edits included) to the backups folder that Sibelius uses, and
   report its path.
5. **Undo:** Undo the batch's steps with `cmd("undo")`. The result reports
   `undoSteps` when a batch had to use `cmd()` steps that count separately
   (see risk 1).

## Operations

What each operation should map to. The **Probe** column refers to the
phase 0 list below, and **M** is the milestone that delivers it.

| Op | MuseScore route | Probe | M |
|---|---|---|---|
| `set` Dx/Dy, Hidden, CueSize | `offsetX`/`offsetY`, `visible`, `small` | P5 | 2 |
| `set` Beam, RestPosition | `beamMode`; rest `offsetY` | P5 | 2 |
| `set` lyric Text, NumNotes | `text`, `lyricTicks` (melisma) | P9 | 2 |
| `set` Text, line Duration | `text`; spanner `spannerTicks` | P7 | 2 |
| `set-pitch` | `pitch` + `tpc1`/`tpc2`; the note keeps its ties, lyrics and articulations (Dorico replaces it) | P6 | 2 |
| `tie` | `Tie` element on the note, or select + `cmd("tie")` | P3, P6 | 2 |
| `bracket` | note parentheses | P5 | 2 |
| `flip-stem` | `stemDirection` | P5 | 2 |
| `nudge` | offset += | P5 | 2 |
| `delete` | `removeElement`; a chord becomes a rest | P4 | 2 |
| `beam` | `beamMode` begin/mid on the range | P5 | 2 |
| `add-note` | Cursor at (track, tick), `setDuration`, `addNote(pitch, addToChord)`; any voice; `tied`; spelling from tpc | P4 | 3 |
| `add-rest`, `add-tuplet` (MuseScore and Dorico) | `Cursor.addRest`, `addTuplet` | P4 | 3 |
| `add-text` | `newElement` STAFF_TEXT / SYSTEM_TEXT / EXPRESSION / TEMPO_TEXT / REHEARSAL_MARK + `Cursor.add`; styleId mapped | P4 | 3 |
| `add-lyric` | `newElement(LYRICS)`, `verse`, `syllabic`, `lyricTicks` | P9 | 3 |
| `add-line` | spanner via `newElement` + `Cursor.add` with an end tick, or selectRange + `cmd("add-hairpin")` / `"add-slur"` / `"add-8va"` | P7, P3 | 3 |
| `add-dynamic`, `set-articulation`, `add-tempo`, `add-rehearsal-mark`, `add-slur`, `add-clef` (Dorico ops) | `newElement` DYNAMIC / ARTICULATION / TEMPO_TEXT (with `tempo`) / REHEARSAL_MARK / CLEF | P4 | 3 |
| `transpose` | per note: `pitch` + `tpc` with the shared `transpose_spelled`, plus key signatures in range | P6, P10 | 4 |
| `copy-passage` | `selectRange` + `cmd("copy")`, select destination + `cmd("paste")` | P3, P11 | 4 |
| `set-key` | `newElement(KEYSIG)` with key/mode at the bar's first segment | P10 | 4 |
| `set-time` | `newElement(TIMESIG)`, `timesig = fraction(n, d)`, common/cut by subtype | P4 | 4 |
| `set-break` | `newElement(LAYOUT_BREAK)`, `layoutBreakType` line/page, added to the measure; `none` removes it | P12 | 4 |
| `set-barline` | end barline `barLineType`; repeats as measure `repeatStart`/`repeatEnd` | P12 | 4 |
| `add-bars` | `appendMeasures(n)` / insert; irregular `length` by measure actual duration | P13 | 4 |
| `set-bar-number` | measure `noOffset` and `irregular` (exclude from count); Dorico can't do this at all | P13 | 4 |
| `set-layout` | `curScore.style.setValue`: page size (inches), spatium, margins, staff and system distances | P14 | 4 |
| `hide-empty-staves` | style `hideEmptyStaves` (score-wide); a bar range likely isn't possible, as on Dorico | P14 | 4 |
| `delete-voice` | `removeElement` on every chord and rest in that track over the range | P4 | 4 |
| `undo` | `cmd("undo")` × steps, refusing when nothing is left to undo | P15 | 1 |
| `save_score` | `cmd("file-save")` for a saved score; `writeScore(.mscz)` for "save a copy" | P16 | 5 |
| `export_score` | `writeScore` to pdf, png, svg, mid, musicxml, mxl; mp3 if supported | P16 | 5 |
| `project_info`, `set_project_info` | `metaTag` / `setMetaTag` (workTitle, composer, lyricist, arranger, copyright) | P17 | 5 |
| `add_instrument` (upstream) | `appendPart(id)` | P18 | 6 |
| staff mute (upstream does this wrong) | the part's instrument channel `mute` | P18 | 6 |

## Phase 0: probes

Write a scratch probe plug-in (not shipped) with a "run this JS snippet"
method, then record each answer in `docs/musescore.md` with the date and
version, as `dorico.md` does. Each probe that lands an edit also checks
the undo count with a marker edit.

- **P1 Plug-in lifecycle.** Does the server survive closing and opening
  scores, and switching tabs? What happens when the plug-in runs a second
  time (the port is already taken)? After the QML file changes, is
  re-running enough or is a restart needed? Does `listen` bind to
  127.0.0.1 or to every interface?
- **P2 Undo grouping.** Are several edits between `startCmd`/`endCmd` one
  step? Does `endCmd(true)` restore everything, leave no redo entry, and
  leave the dirty flag alone?
- **P3 `cmd()` inside `startCmd`.** Does `cmd("tie")`, `"copy"`, `"paste"`
  or `"delete"` join the open command, start its own undo step, or fail?
  This is the biggest unknown (risk 1).
- **P4 Cursor and newElement.** Adding into voices 2-4 and empty
  measures; overwrite versus merge at a position; adding at tuplet ticks.
- **P5 Properties.** Which of `offsetX`, `visible`, `small`,
  `stemDirection`, `beamMode` and parentheses are readable and writable
  from QML, and in what units.
- **P6 Pitch and spelling.** Setting `pitch` and `tpc1`/`tpc2` on
  transposing instruments. Do ties survive a pitch change?
- **P7 Spanners.** Can the plug-in list slurs, hairpins and lines and
  their start and end ticks? Can it create them with a chosen length?
  If not, which `cmd()` actions make them from a range selection?
- **P8 Generated elements.** Which property separates system-start and
  courtesy signatures from placed ones (the bar 9/19/29 counts above)?
- **P9 Lyrics.** Writing `syllabic`, verse and melisma (`lyricTicks`).
- **P10 Key signatures.** Can a KeySig's key be set from QML, by concert
  or written key? Older plug-in APIs couldn't.
- **P11 Clipboard.** Does copy/paste through `cmd()` work with no score
  view focus, and does it overwrite the user's clipboard?
- **P12 Breaks and barlines.** Can LAYOUT_BREAK be added and removed? Is
  `barLineType` writable? Are the repeat flags writable?
- **P13 Measures.** `appendMeasures` and insertion before a bar; changing a
  measure's actual length; `noOffset`/`irregular`.
- **P14 Style.** `style.value`/`setValue` names and units for page size,
  spatium, margins, staff and system distances, hide-empty staves. Are
  they undoable inside `startCmd`?
- **P15 Undo safety.** Does `cmd("undo")` with an empty history open a
  dialog? Can the plug-in tell whether undo is available?
- **P16 Save and export.** Does `writeScore` change the score's path or
  dirty flag? Which formats does it take? Does `cmd("file-save")` open a
  dialog for a score that has never been saved? The `mscore -o`
  command-line export is the fallback for saved files.
- **P17 Metadata.** Are `setMetaTag` edits undoable?
- **P18 Parts.** `appendPart`, and mute through the part's instruments and
  channels.
- **P19 Size.** How long `Read` takes on a large choral score (the
  SATB scores used for Dorico). The plug-in runs on MuseScore's UI thread,
  so a long read freezes the window. Chunk by bars if needed.
- **P20 Modal dialogs.** Which `cmd()` actions open a dialog (the upstream
  `set_instrument_sound` opens a panel). The bridge keeps an allow-list of
  `cmd()` names and refuses any other.

## Milestones (one PR each)

0. **Probes:** The probe plug-in, the P1-P20 answers in `docs/musescore.md`,
   and this plan revised where the answers change it. Move the shared
   spelling and lyric code out of `dorico/score.py`.
1. **Bridge and connection:** `msbridge.qml` with the token, version,
   `GetScoreInfo`, `GetStaves` and `Undo`; `client.py`, `bridge.py`,
   `install.py`; `musescore-cli install-plugin | overview | undo`; a
   conftest guard that fails any test connecting to port 8766.
2. **Reads and addressed edits:** `Read`, `score.py` locating and indexing,
   `query_score`, `score_overview`; `ApplyBatch` with resolve, guards,
   rollback, dry run and backup; set, set-pitch, tie, bracket, flip-stem,
   nudge, delete, beam.
3. **Adding:** add-note, add-rest, add-tuplet, add-text, add-lyric,
   add-line, and the Dorico note ops.
4. **Structure:** `mscx_read.py` and `score_structure`; transpose,
   copy-passage, set-key, set-time, set-break, set-barline, add-bars,
   set-bar-number, set-layout, hide-empty-staves, delete-voice.
5. **Files and metadata:** save_score, export_score, project_info,
   read_lyrics, edit_lyrics.
6. **Switch-over:** add_instrument and mute; a recorded live check; the
   `musescore` skill rewritten for the new tools (the upstream notes kept
   as history); README, setup skill, `docs/musescore.md` parity table;
   `.mcp.json` points `musescore` at `musescore-mcp`.

## Testing

- **Unit tests** (`tests/test_musescore.py`), like `test_dorico.py`:
  index order, unit conversion and tuplet rounding, guard failures, query
  filters, `prepare_batch` for every op and refusal, batch ordering rules,
  and the mscx parser against fixtures under `tests/fixtures/`.
- **Client tests** against a fake WebSocket server on a free port: token
  refusal, timeouts, a score change between calls, an old bridge version.
- **QML checks:** a syntax check of `msbridge.qml` in CI (upstream ships
  `syntax_check.js`), plus a test that the `cmd()` allow-list and the
  methods match what Python calls, like the test that keeps
  `BatchWritableTable` in step with `batch_ops`.
- **Live check:** `scripts/musescore_live_check.py` runs a fixed scenario on a scratch
  score (read, a batch of every op, dry run, rollback, undo by the reported
  steps, a marker edit left untouched) and prints a report. Its results go
  into `docs/musescore.md` the way `dorico.md`'s live verification section
  records Dorico's.

## Expected parity

Assuming the probes go as expected:

- **✅** `score_overview`, `query_score`, `apply_batch` with `dry_run` (better
  than Sibelius: a real rollback), `undo`, every addressed op, add-note,
  add-rest, add-tuplet, add-text, add-lyric, the Dorico note ops,
  set-time, set-break, set-bar-number, delete-voice, project info, lyrics
  read and edit.
- **✅ or ⚠️, depending on probes:** `score_structure` (P12-P14), add-line
  (P7), transpose and set-key (P10), copy-passage (P3, P11), set-barline
  (P12), add-bars with `length` (P13), set-layout (P14), save_score and
  export_score (P16).
- **⚠️ likely:** hide-empty-staves over a bar range.
- **Still manual:** starting the plug-in each session. MuseScore 4 has no
  auto-start for plug-ins, so the first tool call that can't connect has to
  say exactly which menu item to run.

## Risks and decisions

1. **`cmd()` and undo (P3).** If `cmd()` actions take their own undo
   steps, the operations that depend on them (copy-passage and possibly
   tie and line creation) can't join the batch's single step or its
   rollback. In that case: prefer direct element edits; run any remaining
   `cmd()` ops after the `endCmd` of the API edits; report `undoSteps`;
   and make dry runs of those ops check only, as on Sibelius.
2. **Spanner reads (P7).** If the plug-in API can't list spanners, reads
   take them from the `.mscx` copy. That costs one file write per read, but
   unlike Dorico's export it needs no UI scripting.
3. **UI-thread blocking (P19).** Reads are chunked by bars, with one
   request in flight at a time.
4. **MuseScore versions.** Development targets 4.7.x. The bridge reports
   `mscoreVersion` and the client warns on an untested major or minor
   version. An upgrade checklist like `dorico-upgrade-checklist.md` follows
   the first upgrade.
5. **Which way the WebSocket runs.** Recommended: the plug-in stays the
   server, as upstream has it. The other way (Python listens, the plug-in
   connects with `api.websocket.open`) would mean starting the MCP server
   before the plug-in, every session. Decided after P1.
6. **The upstream server.** It stays registered as `musescore` until
   milestone 6. Then it either moves to `musescore-upstream` or is removed;
   recommended: removed, with its plug-in left for the user to delete.
7. **Licensing.** The bridge is new code. Taking the upstream plug-in's
   WebSocket setup is fine under its MIT license, which stays credited.
   MuseScore's own sources are only read for reference.
