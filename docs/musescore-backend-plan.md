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

## Sources

Every API name and behaviour below is marked with where it comes from:

- **[live]** Seen on this machine with MuseScore Studio 4.7.5 on macOS,
  2026-10-03, using the upstream plug-in.
- **[src]** Read in MuseScore's source at tag `v4.7.5`:
  - the plug-in API in `src/engraving/api/v1/` (`qmlpluginapi.h/.cpp`,
    `score.h/.cpp`, `elements.h`, `cursor.h/.cpp`, `selection.h`,
    `style.cpp`, `instrument.h`);
  - plug-in loading in `src/framework/extensions/`;
  - the WebSocket API in `src/framework/network/api/websocketserverapi.cpp`;
  - style names in `src/engraving/style/styledef.h`.

  Reading the source shows that a name exists and what it does, not that a
  plug-in gets the result it expects. Each such item still has a probe.
- **[probe]** Not known yet. Phase 0 answers it.
- **[seen]** Answered by a phase 0 probe; the result, with its date, is in
  [musescore.md](musescore.md#probe-results-musescore-studio-475-macos).

Phase 0 ran on 2026-10-03, and the sections below are revised to match
it. The probe results page has the evidence.

The MuseScore team's API reference is generated from the `APIDOC` comments
in those same headers, so it's covered here too.

## What is already known

- **WebSocket server** [live][src]: `api.websocketserver.listen(port, fn)`,
  `onMessage(id, fn)` and `send(id, text)` work. The upstream plug-in
  answered `ping` and `getScore` through them. There is also a client
  side, `api.websocket.open(port, fn)`, used by MuseScore's bundled
  `dev_test_websocket` plug-in.
- **It listens on every network interface** [src][live]. `listen` calls
  `QHostAddress::Any`, and `lsof` showed MuseScore listening on `*:8765`
  while the upstream plug-in ran. Any device that can reach this Mac over
  the network can drive the open score, with no authentication. A plug-in
  can't choose the address, so the bridge has to authenticate every
  request (see Wire protocol).
- **Plug-in name** [src][live]: MuseScore finds the name by scanning the
  QML for a line starting with `title:`, and uses the file name if there is
  none. `menuPath` is never read. The `title:` therefore has to sit on a
  line of its own.
- **Starting the plug-in** [live][src]: enabling a plug-in in the Plugin
  Manager doesn't run it. The framework has "exec points" that set when a
  plug-in runs (`disabled`, `manually`, and any a module registers), but
  no registration for an automatic start showed up. Treat "run it from
  the Plugins menu every session" as the rule.
- **A changed plug-in file needs a MuseScore restart** [seen]: running it
  again used the old file. A function named `run` breaks the whole file,
  because it clashes with the `run` signal [seen].
- **One window, one process** [seen]: each score window is its own
  MuseScore process. The plug-in serves the score of the window it was
  started in, and only one window can hold the port.
- **Undo grouping** [src][seen]: `startCmd()` opens an undo command and
  locks the undo stack, so API edits and `cmd()` actions (tested with
  `tie`) commit as one undo step. `endCmd(true)` rolls everything back at
  once and leaves no undo step. The lock arrived in 4.6.0.
- **Undo is `cmd("action://notation/undo")`** [seen]. `cmd("undo")` does
  nothing in 4.7, because `cmd()` only translates a few old names. Undo is
  only dispatched when something can be undone [src].
- **`writeScore` can't write `.mscz` or `.mscx`** [seen][src]. The request
  fails inside MuseScore's export path, which shows a Retry/Abort dialog;
  after Abort, MuseScore crashed. PDF, PNG, SVG, MusicXML, MXL, MIDI, MEI,
  MNX and the audio formats can be written. A MusicXML export of the whole
  score took 4 ms.
- **Ticks** [live][src]: positions are ticks, and `division` gives the
  ticks per quarter (480). Measure and staff indices are 0-based.
- **No file path or dirty flag** [src]: `Score` exposes `scoreName` (the
  file name without folder or extension) but no path. The plug-in API's
  `filePath` property is commented out, and there's nothing for unsaved
  changes either.
- **Generated elements** [live][src]: in the test score, bars 9, 19 and 29
  reported 20 elements where the other bars had 8, and bar 32 had 12.
  The likely explanation is that the upstream walk counted the clefs, key
  and time signatures drawn at the start of each system, and the final
  barline. Every element has a read-only `generated` property that tells
  these apart from objects a user placed.

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
| `musicxml_read.py` | Read a MusicXML export for anything the plug-in API can't see, converting written pitch back to concert; shared with, or modelled on, `dorico/musicxml_read.py` |
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
`bridge` (version), `mscoreVersion`, and `score` (`scoreName`, measure and
staff counts), so Python notices if the plug-in now serves a different
score (it was started in another window, or the score was reopened).

- **Port 8766**, overridable with `MUSESCORE_PORT`, so that it doesn't clash
  with the upstream plug-in on 8765 while both exist.
- **Token, required** because the server is reachable from the network.
  `musescore-cli install-plugin` generates a long random token, stores it in
  `~/.config/sibelius-websocket-cli/musescore-token` (mode 600), and writes
  it into the installed QML. The plug-in compares it on every request
  and closes the connection on the first wrong one, without saying why.
  The token isn't encrypted in transit; that's acceptable because the
  client only connects to 127.0.0.1.
- **Disconnects.** Replying to a client that has gone hits an assertion,
  and MuseScore crashed right after one [seen]. The plug-in records closed
  connections and never sends to them.
- **Methods:** `GetBridgeVersion`, `GetScoreInfo`, `GetStaves`, `Read`
  (bars, staves), `ApplyBatch` (primitives, dryRun), `WriteCopy` (path,
  format), `Undo` (steps), `Save`.
- **Plug-in name.** `title: "sibwscli bridge"` on its own line, which is the
  name people will see in the menu. Docs, the setup skill and error
  messages use that name.

## Model

### Addresses

- **staff:** 1-based (MuseScore staff index + 1). Staff 0 is the system
  staff (tempo, system text, rehearsal marks), as on Sibelius.
- **bar:** 1-based measure order. Every measure counts, pick-ups and split
  bars included, as on the other back ends, and frames (title VBox, HBox)
  don't. Reads also report MuseScore's displayed number (`no` plus
  `noOffset` [src]), which differs after a pick-up, an excluded measure or
  a number offset.
- **index:** The object's position in a fixed walk of the staff's bar:
  segments in tick order. Within a segment come clefs, then key and time
  signatures, then annotations (text, dynamics, tempo) in track order, then
  chords and rests in voice order, then lyrics by verse. Spanners (slurs,
  hairpins, lines) come at their start segment after the chord they start
  on. Generated elements are skipped. One function in `score.py` defines
  this order, and a test pins it down.
- **Guards:** `type` and `position` as on Sibelius, plus `pitch` for notes.
  MuseScore elements have no ids that survive between calls, so these
  guards are the only check that the object is still the one that was read.
  The bridge resolves every address to an element before the first edit
  (the Sibelius lesson in SPEC.md 1.3.1) and checks each guard against it.
- **Score guard.** There's no file path to check (see above), so a batch
  carries a fingerprint from its snapshot: `scoreName`, measure and staff
  counts, and a hash of the bar contents it touches. It's refused if the
  user switched tabs or edited those bars in between.

### Units

`units = ticks * 256 / division` (`* 8 / 15` at 480). Whole, half, quarter,
eighth, sixteenth and thirty-second positions convert exactly. Tuplet
positions don't: a triplet eighth is 160 ticks, or 85⅓ units. Every object
therefore also carries its exact `ticks`. Addresses and guards accept
either value, with units rounded to the nearest integer. Adding at a tuplet
position takes `ticks`. Sibelius has the same rounding at 256 per quarter,
so the tools look the same either way.

`Dx`/`Dy` are `offsetX`/`offsetY` × 32. The offsets are in staff spaces
(spatium) [src], and the Sibelius unit is 1/32 of a space.

### Types

| MuseScore element | Reported as | Notes |
|---|---|---|
| Chord, Rest | `NoteRest` | notes with `pitch`, `tpc1`/`tpc2`, `tieForward`/`tieBack`, `hasParentheses` [src] |
| Lyrics | `LyricItem` | `text`, `verse`, `syllabic`, `lyricTicks` (melisma) [src] |
| StaffText, Expression, Dynamic, InstrumentChange | `Text` | `styleId` mapped to Sibelius names where one fits |
| SystemText, TempoText, RehearsalMark | `Text` on staff 0 | |
| Clef, KeySig, TimeSig | `Clef`, `KeySignature`, `TimeSignature` | KeySig `key`, `concertKey` [src, since 4.6] |
| Tuplet | `Tuplet` | ratio, span |
| Slur, Hairpin, Ottava, Pedal, Trill, TextLine, Volta | `Line` + `lineType` | from `curScore.spanners`, with `spannerTick`, `spannerTicks`, `startElement`, `endElement` [src] |
| Articulation, Fermata | properties of the NoteRest | `articulations`, as on Dorico |

Allow-listed fields: `Dx`/`Dy` (`offsetX`/`offsetY`), `Hidden`
(`!visible`), `CueSize` (`small`), `StemFlipped` (`stemDirection`), `Beam`
(`beamMode`), `Bracketed` (`hasParentheses`), plus `Pitch`, `Text`, `Voice`.
All of these properties exist and are writable [src].

## Reads

- **`score_overview`:** `scoreName` and metadata tags (`metaTag`
  [src]: workTitle, composer, lyricist and so on), measure count, parts
  with instrument names and staves, and the current selection. There's no
  file path or dirty flag (see above). If one is needed, the user has to
  supply it.
- **`query_score`:** The bridge returns the raw objects for the requested
  bars and staves. `score.query` assigns indices, applies `types`, `voice`,
  `where` and `fields` with the shared selector code, and truncates at
  `limit`, as the Dorico back end does. Lines come from `curScore.spanners`
  [src], so no file copy is needed for them.
- **`score_structure`:** Read live as far as possible:
  - key and time signatures from their segments;
  - barlines (`barlineType` [src]) and repeats (`repeatStart`/`repeatEnd`
    [src]);
  - irregular measures and bar-number offsets (`timesigActual`,
    `irregular`, `noOffset` [src]);
  - page and staff layout from `curScore.style.value` (`pageWidth`,
    `pageHeight`, `spatium`, `staffDistance`, `minSystemDistance`, the
    margin keys, `hideEmptyStaves`; inches, 1/1200 inch and staff spaces [seen]).

  Layout breaks are `LayoutBreak` items in `measure.elements` [seen].
  Anything else the API doesn't show comes from a MusicXML export that
  `WriteCopy` writes to `~/.cache/sibelius-websocket-cli/musescore/` with
  `writeScore`; it left the score's name unchanged [seen]. MusicXML holds
  written pitch for transposing instruments [seen], so `musicxml_read.py`
  converts back with each part's `<transpose>`. (`.mscx` can't be
  written; see above.)
- **Lyrics:** `read_lyrics` and `edit_lyrics` (Dorico has these, Sibelius
  doesn't) are easy here, since the plug-in can read and write lyric text
  and syllabic directly, with no dialog [src].

## Batches

1. `batch_ops.validate_batch`, then `score.prepare_batch` against a fresh
   snapshot. This resolves addresses, checks guards and bar order, refuses
   what MuseScore can't do (a `NOT_ON_MUSESCORE` table like Dorico's), and
   emits primitives that name elements by (staff index, track, tick, kind,
   ordinal at that tick).
2. **Bridge `ApplyBatch`:** resolve every primitive's element, then
   `curScore.startCmd("AI batch")`, run the primitives in order, then
   `curScore.endCmd()`. If any primitive throws, `endCmd(true)` rolls the
   whole batch back [src]. Partial batches can't happen, unlike on
   Sibelius. The name passed to `startCmd` is what Edit → Undo shows.
3. **`dry_run`:** Run the batch for real, call
   `curScore.doLayout(fraction(0, 1), fraction(-1, 1))` so derived values
   such as bar numbers are current [seen], describe each object before
   and after, then `endCmd(true)`. Rollback was exact in every probe that
   didn't crash, so a MuseScore dry run proves the batch works; Sibelius
   and Dorico can only check a batch before running it.
4. **Never inside a batch.** These either escape undo and rollback or are
   unsafe, so `prepare_batch` never sends them inside a batch:
   - `setMetaTag`: rollback kept the new value [seen];
   - a layout break through `Cursor.add` (`MeasureBase::addInternal`)
     [src]; breaks go through `cmd("system-break")` instead;
   - a spanner through `Cursor.add`: it is added to a segment, which can't
     hold one ("Segment::add() unknown HairPin") [seen];
   - a range selection made inside the batch: `selectRange` only records
     ticks until the command ends [src], and a copy of such a selection
     crashed MuseScore [seen]. Ranges are selected, and copied, before
     `startCmd`;
   - an action that opens a dialog or starts an interactive edit, such as
     `add-hairpin` dragging the new hairpin's end [src].
5. **Backup:** `.mscz` copies are impossible [seen], so a real run first
   writes a MusicXML export of the current state to the backups folder and
   reports it as a record rather than a full backup: it loses detail only
   MuseScore keeps. The real safety net is the batch's single undo step
   and the dry run.
6. **Undo:** `cmd("action://notation/undo")` once per step [seen]. A batch
   is one step [seen].

## Operations

What each operation should map to. The **Probe** column refers to the
phase 0 list below, and **M** is the milestone that delivers it.

| Op | MuseScore route | Probe | M |
|---|---|---|---|
| `set` Dx/Dy, Hidden, CueSize | `offsetX`/`offsetY`, `visible`, `small` [src] | P5 | 2 |
| `set` Beam, RestPosition | `beamMode` (AUTO 0, NONE 1, BEGIN 2, ...) [seen]; rest `offsetY` | P5 | 2 |
| `set` lyric Text, NumNotes | `text`, `lyricTicks` [src] | P9 | 2 |
| `set` Text, line Duration | `text`; `spannerTicks` [src] | P7 | 2 |
| `set-pitch` | `pitch`, `tpc1` (concert) and `tpc2` (written, from `Staff.transpose(tick)`) together, since `pitch` alone keeps the old spelling [seen]. The note keeps its ties, lyrics and articulations (Dorico replaces it) | P6 | 2 |
| `tie` | select the note + `cmd("tie")`: joins the batch, and undoes and rolls back with it [seen] | P3 | 2 |
| `bracket` | `hasParentheses` 3 or 0 (1 and 2 hit an assertion) [seen] | P5 | 2 |
| `flip-stem` | `stemDirection` [src] | P5 | 2 |
| `nudge` | offset += | P5 | 2 |
| `delete` | `removeElement` (`deleteItem` [src]); a chord becomes a rest | P4 | 2 |
| `beam` | `beamMode` begin/mid on the range | P5 | 2 |
| `add-note` | Cursor at (track, tick), `setDuration`, `addNote(pitch, addToChord)`; replaces what is at that position [seen]. Voices 2-4: rewind on voice 1, then set `track` [seen], so only at ticks where voice 1 has a chord or rest. Spelling set afterwards | P4 | 3 |
| `add-rest`, `add-tuplet` (MuseScore and Dorico) | `Cursor.addRest`, `addTuplet(ratio, duration)` [src] | P4 | 3 |
| `add-text` | `newElement` STAFF_TEXT / SYSTEM_TEXT / EXPRESSION / TEMPO_TEXT / REHEARSAL_MARK + `Cursor.add` (undoable [src]); styleId mapped | P4 | 3 |
| `add-lyric` | `newElement(LYRICS)` + `Cursor.add` onto the chord; `verse` (0-based), `syllabic` (0 single, 1 begin, 2 end, 3 middle), `lyricTicks` [seen] | P9 | 3 |
| `add-line` | **Open.** Slurs: select a note + `cmd("add-slur")`, to the next chord [seen]. Never `Cursor.add` [seen]. Octave lines: `cmd("add-8va")` is a plain edit on the selection [src]. Hairpins: `cmd("add-hairpin")` then end its interactive edit (`action://notation/cancel`) before the batch ends [src]. Ranges selected before the batch. To be tried in milestone 3, one isolated step at a time | P7 | 3 |
| `add-dynamic`, `set-articulation`, `add-tempo`, `add-rehearsal-mark`, `add-slur`, `add-clef` (Dorico ops) | `newElement` + `Cursor.add` for DYNAMIC, TEMPO_TEXT (`tempo` in beats per second) and REHEARSAL_MARK [seen]; ARTICULATION with a numeric `symbol` id (623 = staccato in 4.7.5), or select a note + `cmd("add-staccato")` / `"add-tenuto"` / `"add-marcato"` / `"add-sforzato"` [seen]; CLEF (`Cursor.add` handles placement [src]) | P4 | 3 |
| `transpose` | per note: `pitch` + `tpc` with the shared `transpose_spelled`; there is no transpose call in the plug-in API [src]. Key signatures in range too | P6, P10 | 4 |
| `copy-passage` | `selectRange` + `cmd("copy")` **before** `startCmd` (inside a batch the copy crashed MuseScore [seen]); then, in the batch, select the destination + `cmd("paste")`. Untested: milestone 4, isolated | P11 | 4 |
| `set-key` | `newElement(KEYSIG)` with `concertKey` **and** `actualKey` (the written key, from the staff's transposition; MuseScore doesn't derive it), `Cursor.add` on each staff's first track [seen] | P10 | 4 |
| `set-time` | `newElement(TIMESIG)`, `timesig = fraction(n, d)`, `Cursor.add`: re-bars what follows [seen]; `timesigType` for common/cut | P4 | 4 |
| `set-break` | select a note or rest in the bar + `cmd("system-break")` / `"page-break"`; they toggle, so check `measure.elements` first [seen] | P12 | 4 |
| `set-barline` | `barlineType` on the end barline, which spans the system [seen]; repeats as measure `repeatStart`/`repeatEnd` [seen] | P12 | 4 |
| `add-bars` | `appendMeasures(n)` at the end; before bar B, select a note or rest there + `cmd("insert-measure")` once per bar (`insert-measures` takes its count from a dialog) [seen]; irregular `length` by `timesigActual` [seen] | P13 | 4 |
| `set-bar-number` | measure `noOffset` and `irregular` (exclude from count) [seen]; Dorico can't do this at all | P13 | 4 |
| `set-layout` | `curScore.style.setValue`, undoable [seen]: `pageWidth`/`pageHeight` and margins in inches, `spatium` in 1/1200 inch, `staffDistance` and system distances in staff spaces | P14 | 4 |
| `hide-empty-staves` | style `hideEmptyStaves` (score-wide), or per system with `System.setHideStaffIfEmpty(staffIdx, hide)` [src], which might allow a bar range | P14 | 4 |
| `delete-voice` | `removeElement` on every chord and rest in that track over the range | P4 | 4 |
| `undo` | `cmd("action://notation/undo")` × steps [seen]; nothing happens when nothing is left to undo [src] | P15 | 1 |
| `save_score` | `cmd("file-save")` for a score already saved (the API has no save call [src]); whether it opens a dialog is still to probe. No "save a copy", since `writeScore` can't write `.mscz` [seen] | P16 | 5 |
| `export_score` | `writeScore(score, path, ext)` for pdf, png, svg, musicxml, mxl, mid, mei, mnx, wav, mp3, ogg, flac or aac [src]; musicxml checked [seen]. Never `.mscz`/`.mscx`, which open a dialog [seen] | P16 | 5 |
| `project_info`, `set_project_info` | `metaTag` / `setMetaTag`; not undone or rolled back [seen], so it runs outside batches and says so | P17 | 5 |
| `add_instrument` (upstream) | `appendPart(id)` [seen]; also `insertPart`, `replacePart`, `removeParts` [src] | P18 | 6 |
| staff mute (upstream does this wrong) | `Channel.mute` does nothing in MuseScore 4 [src]. The nearest is turning off a staff's `playbackVoice1`-`4`, which is writable [seen]; whether that silences playback is still to be heard | P18 | 6 |

## Phase 0: probes

**Status, 2026-10-03:** answered, apart from the items below; the results
are in [musescore.md](musescore.md#probe-results-musescore-studio-475-macos).
Still open, and moved to the milestones that need them: copy-passage with
the selection made before the batch (P11), hairpins and other lines (P7),
`cmd("file-save")` (P16), whether `playbackVoice` silences playback (P18),
and closing the last score of the only window (P1). Three probes crashed
MuseScore (an `.mscx` export, a hairpin, a copy inside a batch), so risky
steps run one per request, after reading the source.

Write a scratch probe plug-in (not shipped) with a "run this JS snippet"
method, then record each answer in `docs/musescore.md` with the date and
version, as `dorico.md` does. Each probe that lands an edit also checks
the undo count with a marker edit.

- **P1 Plug-in lifecycle.** Does the server survive closing and opening
  scores, and switching tabs? What happens when the plug-in runs a second
  time (the port is already taken)? After the QML file changes, is
  re-running enough or is a restart needed? Does the Plugin Manager offer
  any exec point besides "manually"? (It's already known that the server
  listens on every interface [src][live].)
- **P2 Rollback.** Are several edits between `startCmd`/`endCmd` one undo
  step? Does `endCmd(true)` restore everything and leave no redo entry? Does
  the window show the score as unsaved afterwards?
- **P3 `cmd()` inside `startCmd`.** The source says `cmd()` changes join the
  open command. Check this for `tie`, `copy`, `paste`, `delete` and the
  break and measure actions, including under `endCmd(true)`. `cmd()`
  dispatches through the UI's action system [src], which might not finish
  before it returns.
- **P4 Cursor and newElement.** Adding into voices 2-4 and empty
  measures; overwrite versus merge at a position; adding at tuplet ticks.
- **P5 Properties.** Read and write `offsetX`, `visible`, `small`,
  `stemDirection`, `beamMode` and `hasParentheses`, and confirm each is one
  undo step.
- **P6 Pitch and spelling.** Setting `pitch` and `tpc1`/`tpc2` on
  transposing instruments. Do ties survive a pitch change?
- **P7 Spanners.** Read `curScore.spanners` [src] on a score with slurs and
  hairpins. Create one with `newElement` + `Cursor.add` and set its length.
- **P8 Generated elements.** Check that `generated` [src] separates the
  bar 9/19/29 extras from placed objects.
- **P9 Lyrics.** Writing `syllabic`, `verse` and `lyricTicks`.
- **P10 Key signatures.** Set `key` and `concertKey` [src] on transposing
  staves, and check that every staff gets the change.
- **P11 Clipboard.** Does copy/paste through `cmd()` work with no score
  view focus, and does it overwrite the user's clipboard?
- **P12 Breaks and barlines.** Which action names make and remove system
  and page breaks, and are they undoable? Is `barlineType` writable? Are
  the repeat flags writable?
- **P13 Measures.** `appendMeasures`, and the action that inserts before a
  bar; changing `timesigActual`; `noOffset` and `irregular`.
- **P14 Style.** Units of `pageWidth`, margins and distances;
  `System.setHideStaffIfEmpty` over a bar range.
- **P15 Undo safety.** Does `cmd("undo")` with an empty history open a
  dialog? There's no way to ask whether undo is available [src], so the
  bridge has to count its own steps.
- **P16 Save and export.** Does `writeScore` change the score's file name or
  saved state? Which formats does it take? Does `cmd("file-save")` open a
  dialog for a score that has never been saved? The `mscore -o`
  command-line export is the fallback for saved files.
- **P17 Metadata.** Check that `setMetaTag` survives a save and isn't undone.
- **P18 Parts and playback.** `appendPart`; whether turning off
  `playbackVoice1`-`4` actually silences a staff.
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
2. **Reads and addressed edits** (done 2026-10-03; see
   [musescore.md](musescore.md#our-back-end-in-progress)): `Read`, `score.py` locating and indexing,
   `query_score`, `score_overview`; `ApplyBatch` with resolve, guards,
   rollback, dry run and backup; set, set-pitch, tie, bracket, flip-stem,
   nudge, delete, beam.
3. **Adding:** add-note, add-rest, add-tuplet, add-text, add-lyric,
   add-line, and the Dorico note ops.
4. **Structure:** `musicxml_read.py` and `score_structure`; transpose,
   copy-passage, set-key, set-time, set-break, set-barline, add-bars,
   set-bar-number, set-layout, hide-empty-staves, delete-voice.
5. **Files and metadata:** save_score, export_score, project_info,
   read_lyrics, edit_lyrics.
6. **Switch-over:** add_instrument and staff playback; a recorded live
   check; the `musescore` skill rewritten for the new tools (the upstream
   notes kept as history); README, setup skill, `docs/musescore.md` parity
   table; `.mcp.json` points `musescore` at `musescore-mcp`.

## Testing

- **Unit tests** (`tests/test_musescore.py`), like `test_dorico.py`:
  index order, unit conversion and tuplet rounding, guard failures, query
  filters, `prepare_batch` for every op and refusal, batch ordering rules,
  and the MusicXML reader against MuseScore exports under `tests/fixtures/`.
- **Client tests** against a fake WebSocket server on a free port: token
  refusal, timeouts, a score change between calls, an old bridge version.
- **QML checks:** a syntax check of `msbridge.qml` in CI (upstream ships
  `syntax_check.js`), a test that `title:` sits on its own line, and a test
  that the `cmd()` allow-list and the methods match what Python calls, like
  the test that keeps `BatchWritableTable` in step with `batch_ops`.
- **Live check:** `scripts/musescore_live_check.py` runs a fixed scenario on a scratch
  score (read, a batch of every op, dry run, rollback, undo by the reported
  steps, a marker edit left untouched) and prints a report. Its results go
  into `docs/musescore.md` the way `dorico.md`'s live verification section
  records Dorico's.

## Expected parity

Assuming the probes go as expected:

- **✅** `score_overview` (without a file path), `query_score`,
  `apply_batch` with `dry_run` (better than Sibelius: a real rollback),
  `undo`, every addressed op, add-note, add-rest, add-tuplet, add-text,
  add-lyric, the Dorico note ops, set-time, set-bar-number, set-layout,
  delete-voice, project info, lyrics read and edit.
- **✅ or ⚠️, depending on probes:** `score_structure` (P12, P14), add-line
  (P7), transpose and set-key (P10), copy-passage (P3, P11), set-break
  (P12), set-barline (P12), add-bars before a bar (P13), hide-empty-staves
  over a bar range (P14), save_score and export_score (P16).
- **❌ likely:** staff mute as such. MuseScore 4's mixer isn't reachable from
  plug-ins [src].
- **Still manual:** starting the plug-in each session, unless P1 finds an
  exec point that runs it at startup. The first tool call that can't
  connect has to say exactly which menu item to run.

## Risks and decisions

1. **Network exposure.** Covered by the token. The docs and the setup skill
   also say that the upstream plug-in has no such protection: while it
   runs, anyone on the same network can edit the open score. Recommended:
   stop using it once milestone 2 lands.
2. **`cmd()` actions (P3).** `tie`, `add-slur`, the breaks,
   `insert-measure`, the articulation actions and undo all finished before
   `cmd()` returned, and joined the batch [seen]. But `cmd()` runs
   MuseScore's own UI actions, and all three crashes came from that side:
   export, a hairpin's interactive edit, copy. The bridge keeps an
   allow-list of actions, each with its known preconditions (a note
   selected; no range selected inside a batch), and refuses any other.
3. **Things never sent inside a batch** (Batches, step 4). Keep the list in
   `score.py` and add to it whenever a probe finds another.
4. **UI-thread blocking (P19).** Not a problem at the sizes tried: a full
   read of 300 bars with 7,200 notes took 38 ms [seen]. One request in
   flight at a time.
5. **MuseScore versions.** Development targets 4.7.x. Several properties
   used here are only available since 4.6 [src] (`actualKey`, `concertKey`,
   `hasParentheses`, `doLayout`, `isHeader`, `showElementInScore`), and the
   undo-stack lock that makes `cmd()` join a batch arrived in 4.6.0 [src].
   The bridge reports `mscoreVersion`, refuses anything older than 4.6, and
   warns on an untested minor version. MuseScore 3.x is out of scope: it
   has no WebSocket API, no rollback and an older plug-in system. An upgrade checklist like
   `dorico-upgrade-checklist.md` follows the first upgrade.
6. **Which way the WebSocket runs.** Recommended: the plug-in stays the
   server, as upstream has it. The other way (Python listens, the plug-in
   connects with `api.websocket.open`) would avoid the open port, but would
   mean starting the MCP server before the plug-in, every session. Decided
   after P1.
7. **The upstream server.** It stays registered as `musescore` until
   milestone 6. Then it either moves to `musescore-upstream` or is removed;
   recommended: removed, with its plug-in left for the user to delete.
8. **Licensing.** The bridge is new code. Taking the upstream plug-in's
   WebSocket setup is fine under its MIT license, which stays credited.
   MuseScore's own sources (GPL-3.0) are only read for reference, not
   copied.
