# Dorico back end

`dorico-mcp` and `dorico-cli` drive the project open in Dorico the way
`sibelius-mcp` and `sibelius-websocket-cli` drive Sibelius: the same tool
names, staff/bar/index addresses, 1/256-quarter units and MIDI pitches, and
one undo step per batch. Everything here was established by probing Dorico
6.2.30 Pro on macOS; Steinberg documents none of it.

## How it works

```
dorico-mcp / dorico-cli
  └─ dorico/client.py   Dorico Remote Control API (WebSocket, 127.0.0.1:4560)
       └─ command "Script.RunScript?ScriptPath=<request.lua>"
            └─ request.lua sets BRIDGE_REQUEST and BRIDGE_RESPONSE, runs
               dorico/bridge.lua inside Dorico, which writes a JSON answer
```

Dorico has two automation surfaces:

| | Remote Control API (WebSocket) | Lua scripting (`Script.RunScript`) |
|---|---|---|
| Reads score content | No: selection-based status only | Yes: flows, streams, events, pitches, text |
| Edits | ~1,090 commands on the selection | Create, delete and change events by id |
| Undo | `Edit.Undo`, `Edit.Redo` | Every edit in one script run is **one** undo step |
| Documentation | None official (community: Dorico.Net) | None |

The bridge uses the WebSocket to run Lua, and for undo, redo and status.

### Staves with lyrics: the MusicXML fallback

Dorico's Lua cannot read a voice stream that holds lyrics. When a read hits
one (`read` with `skipUnreadable` lists them), `service.snapshot` exports
the flow as MusicXML (`dorico/export.py`, UI scripting, below) and reads it
with `dorico/musicxml_read.py`:

- staves Lua can read keep their Dorico events and ids;
- staves it cannot read come from the export (`"source": "musicxml"`, no
  id, with `lyrics`);
- bars, time signatures (numerator/denominator) and keys come from the
  export, so no bar measurement edit is made.

Adding to a lyric staff works; `delete`, `set-pitch` and `transpose` refuse
its existing notes, which have no id to address. Each such read triggers an
export, so it takes several seconds and needs Accessibility permission.

### Connecting

The client sends `connect` with a client name. Dorico shows an approval
prompt the first time; the token it then sends is stored in
`~/.config/sibelius-websocket-cli/dorico-token.json` (keyed by client name,
since that is what Dorico approves). With a stored token Dorico answers
`kConnected` at once, then pushes a full `status`; later status messages
carry only changed fields, so the client merges them.
`DORICO_CLIENT_NAME` overrides the client name; `--no-approval` (CLI) fails
instead of prompting.

## Dorico's Lua model

Lua 5.2 with luabind bindings. `io` and `os` are available. Entry point:
`DoCore.ScriptHost().currentScore`.

- Score, flow, player, stream and event members are luabind **properties**
  (field access, `score.flows`), not methods. `class_info(obj)` lists only
  methods and returns userdata, not a table. The full member lists live in
  the Lua registry (`debug.getregistry()`).
- Calling a function with wrong arguments makes luabind list its real
  signatures ("No matching overload found, candidates: ..."): the way to
  learn an API without changing anything.
- `tostring` throws on some objects ("No such operator defined").
- Events read from a stream are the base `Event` class: `class_info` says
  `Event` and subclass members (`text`, `pitchWithSpelling`) are nil. The
  string form carries the type, spelled pitch and text:
  `kNoteEvent (id:3) at 0, duration 1  C5 (ends 1)`,
  `kTextEvent (id:33) at 12 : espr.\n (paragraph.defaulttext)`.
- Positions and durations are rational quarter notes (`RhythmicLength(n, d)`,
  printed `15/2 (7.5)`).

A flow holds:

| Stream | Holds |
|---|---|
| global timebase (type 0) | `BarDivisionEvent` (time signatures), `TonalityDivisionEvent` (key signatures) |
| instrument stave streams (type 1), one per staff | clefs and other staff items |
| voice streams (type 2) | notes, rests, text, tuplets |
| player streams (type 3) | player-level items |

**Dorico's Lua has no link from a voice to its stave.** `flow.instruments`
has one entry per *voice* (not per stave), each listing all of that
instrument's voice streams; voice streams expose nothing stave-related.
Checked 2026-09-27 on a piano with an extra voice made with Edit > Voices >
Change Voice > New Down-stem Voice on the treble staff: its stream (7) had
a higher id than both stave streams, so ordering by id would have put it on
the bass staff. `dorico/layout.py` therefore assigns voices in Python:

1. staves go to instruments in order (one each, all to a single
   instrument, or by the MusicXML export's parts);
2. a one-stave instrument gets all its voices;
3. one voice per stave: given out in id order (piano, imported SATB);
4. otherwise each voice goes to the stave whose MusicXML notes match its
   own (flow position and pitch); a voice with no notes is left out and
   reported as `unplacedVoiceStreams`.

Rules 1 and 4 need a MusicXML export, so reading such a score exports it.
Verified live: the extra treble voice read as staff 1 voice 2, the empty
voice as unplaced.

Notes carry six properties: `kNotePitch` (MIDI), `kNoteSpelling`,
`kEventPosition`, `kEventDuration`, `kEventSecondaryPosition`,
`kEventSecondaryEndPositionOffset`. Chord notes are separate events at the
same position.

### Useful signatures

```
EventStream:createNote(RhythmicLength pos, RhythmicLength dur, MIDIPitchWithSpelling)
EventStream:createRest(pos, dur)             EventStream:createBarRest(pos)
EventStream:createText(pos, dur, string)     EventStream:createGraceNote(pos, dur, dur, pitch)
EventStream:createClef(pos, dur, bool, ClefCollectionEntity)
EventStream:createTuplet(pos, TupletDefinition)
EventStream:createBarDivision(pos, BarDivisionElement)
EventStream:createTonalityDivision(pos, TonalityDivisionElement)
EventStream:createSystemBreak(int, pos)
EventStream:delete(Event)                    EventStream:deleteEventsInRange(pos, pos)
EventStream:moveRange(pos, pos, EventStream, pos, int)
EventStream:copyRange(pos, pos, EventStream, pos, int)
EventPropertyTable:get(name, PropertyContext)   :set(name, Variant, PropertyContext)
DoCore.MIDIPitchWithSpelling(DoCore.MIDIPitch(midi), DoCore.NoteName.fromString("B"))
DoCore.WesternPitchTransposer.transpose(MIDIPitchWithSpelling, Interval, bool)
DoApp.DoApp():save(Score, path)              DoApp.DoApp():doCommand(string)
ScriptHost:convertFolderOfScores(in, out, fmt)  -- throws "Not implemented"
```

## Parity with the Sibelius back end

| Sibelius tool / op | Dorico | Notes |
|---|---|---|
| `score_overview` | ✅ | title, flows, players, staves with voice streams, layouts, selection |
| `score_structure` | ⚠️ | from a MusicXML export when any staff has lyrics (full time/key info); otherwise bar lengths and key positions only |
| `query_score` | ✅ | staves, bars, types (Sibelius names or Dorico's), voice, `where`; lyric staves via MusicXML (no ids) |
| `apply_batch` + `dry_run` | ✅ | every op checked first; one undo step |
| `set-pitch` | ✅ | replaces the note, spelled as asked; new id reported |
| `delete` | ✅ | |
| `add-note` (chords), `add-rest`, `add-text` | ✅ | into voices that already exist |
| (Dorico only) `add-clef` | ✅ | treble, bass, percussion, tab, tab.4 from the score's clef library |
| `transpose` | ✅ | per-note, respelled diatonically |
| `set` (Dx, Dy, Hidden, ...), `tie`, `bracket`, `flip-stem`, `nudge`, `beam` | ❌ | not in the Lua model |
| `add-line` | ❌ | no line classes exposed |
| `add-lyric` → `add-lyrics` | ⚠️ | verse 1, typed through the lyric popover by command (see gaps); staff must have no lyrics yet |
| `copy-passage` | ❌ | `copyRange(from, to, stream, dest, 0)` runs but copies nothing |
| `set-key`, `set-time` | 🔜/❌ | create calls exist but need elements Lua cannot construct |
| `set-break` | ⚠️ | system breaks via `Edit.CreateSystemBreak` on a selected note (2 undo steps each); bars without a note or rest of their own are refused |
| `set-barline`, `set-bar-number`, `add-bars`, `set-layout`, `hide-empty-staves`, `delete-voice` | ❌ | not exposed |
| `undo` | ✅ | stops when Dorico has nothing to undo |
| `save_score` | ⚠️ | saves a copy to a given `.dorico` path; the project keeps its own file |
| `export_score` | ✅ | `pdf` (all pages, via Print mode), `musicxml` (full score, via the export window), first-page previews |

## Gaps and workarounds

- **Lyrics block reading.** Reading `events` (or `block.events`) of a voice
  stream that holds lyrics throws `Not implemented - this may leave the
  score in an unpredictable state`. Confirmed on an imported SATB score
  (2026-09-27): every staff with lyrics failed; after deleting Soprano II's
  lyrics, that staff read normally (81 notes). Saving and reopening as
  `.dorico` does not help. The bridge reports these streams as unreadable
  rather than empty, but it cannot query them or run addressed ops
  (`delete`, `set-pitch`, `transpose`), which look events up first.
  **Adding works**: `createNote` into Alto I (with lyrics) added a G5 as a
  chord with the existing note, lyrics intact, one undo step (2026-09-27).
  **`deleteEventsInRange` works too, but takes the lyric with it**: deleting
  flow range ½-2 quarters on Alto I removed the D4 *and* its lyric "fare"
  (rests filled the gap; neighbouring notes and lyrics untouched; one
  undo restored both). Lyrics are events at the note's position in the same
  voice stream, and a range takes every event in it (a whole chord, not one
  note). So a pitch change there would lose the lyric (Lua cannot create
  lyrics), and a delete could only mean "clear this position, lyric and all".

- **Bar numbers.** A time signature's content (`kBarDivisionTimeSignatures`)
  is a Variant Lua cannot convert, so bar lengths are measured: a bar rest
  created at each bar division takes that bar's length. That is an edit, so
  `DoricoBridge.bars` undoes it at once, re-reads the score and compares it
  with the read taken before; if they differ (the undo hit something else)
  it redoes and fails. The map is cached per connection until the bar
  divisions change. Side effect: Dorico's redo history is cleared by each
  measurement.
- **Key signatures.** `TonalityDivisionElement` is an unregistered class:
  positions are known, keys are not.
- **Spelling.** `kNoteSpelling` accepts writes that change nothing, so a
  respelled pitch is a delete plus a create with an explicit
  `MIDIPitchWithSpelling`. Setting `kNotePitch` alone lets Dorico pick the
  spelling (A4 + 2 became A𝄪4).
- **Durations.** `kEventDuration` accepts `Variant.createString("1/2")` and
  the render changes, but the event's `duration` still reads the old value
  afterwards, so there is no set-duration op until reads agree.
- **Voices.** Lua cannot create a voice stream; `add-*` into voice N needs
  that voice to exist on the staff.
- **Save.** `DoApp:save(score, path)` writes a copy to a `.dorico` path;
  `ScriptHost:save` returns false. The open project keeps its own file
  (checked 2026-09-27: after several saves to scratch paths, Save As still
  offered the project's usual folder), so Cmd-S is unaffected.
- **PDF export (works, 2026-09-27).** `Print.ExportCurrentLayoutAsPDF`
  writes the active window's layout, every page, with Print mode's current
  settings, to `<project folder>/<nn> - <layout> - <title>.pdf`: no dialog
  the first time. If that file exists Dorico asks "One or more output files
  already exist" (Overwrite / Create New); `export_pdf` answers Overwrite.
  The path appears only in the log ("Exporting PDF to ..."), so it is read
  from `application.log`. Checked: 11-page SATB score, every page exported.
- **Export.** Every save embeds `supplementary_data/preview/preview.pdf`
  and `preview.png` (first page of the full score); `export_score` extracts
  them. Full PDF and MusicXML export go through dialogs
  (`File.Export`, `Print.ExportCurrentLayoutAsPDF` untested).
  `convertFolderOfScores` is a stub.
- **MusicXML export by UI scripting (works, 2026-09-27).** The menu logs
  only `File.Export?FilterID=MusicXMLExportFilter`, with no path.
  Sent over the WebSocket it returns kOK at once and opens Dorico's own
  "Export MusicXML" window (not a macOS Save panel). Through System Events
  (Accessibility permission needed): the window lists format, flow and
  layout check boxes and the last "Export to:" folder as static text;
  clicking **OK** writes `<folder>/Flows from <title>/<title> - Full score
  - 01 <flow>.musicxml` plus one file per part. Existing files raise one
  "Do you want to overwrite the file ...?" dialog each (Overwrite / Cancel
  / Skip this file); moving the old folder aside first avoids them.
  AppleScript must use `get role of e` / `get name of e` explicitly on
  Dorico's Qt elements, or comparisons silently fail.

- **System breaks (2026-09-27).** A break made with the menu is
  `EventEdit.Select?FlowID=0&EventID=<a note at the bar>&EventBlockID=<block>`
  then `Edit.CreateSystemBreak`: a `BreakEvent` in the global timebase at
  the bar's start (`kBreakType` 1, a `kBreakLayoutID` Lua cannot read), and
  the full score starts a system there. `createSystemBreak(n, pos)` from Lua
  makes a `BreakEvent` with the same readable properties, but with n = 0 or
  1 the full score ignores it. So set-break would go through the command,
  which needs a note or rest (with an id) starting in that bar, and the
  project to be Dorico's active score. Deleting the `BreakEvent` removes a
  break. `set-break` does exactly this; bars with no event of their own
  (empty bars, or only a note tied in from the bar before) are refused.
  Dorico's implied rests are not events, and `Edit.GoToLocation` /
  `GoToRhythmicPosition` do not select anything. A temporary rest to select
  worked but was dropped as too fragile to undo.
- **Selections are undo steps.** `EventEdit.Select` adds an entry to
  Dorico's undo history, so select-then-command costs two undo steps; an
  undo count that ignores this reverts the wrong thing (seen twice on
  2026-09-27). Every Lua script, even a read, also clears the redo stack.
- **Active score.** `ScriptHost().currentScore` and every command follow
  Dorico's active project, which changes only when a window really gets
  focus. Raising a window by script works with System Events: set the
  process `frontmost`, then `perform action "AXRaise"` on the window
  ("Flow 1 in sample"); clicking the Window menu item alone did not.

- **Adding lyrics (2026-09-27).** Logged from the lyric popover and
  replayed over the WebSocket: `EventEdit.Select` the first note,
  `NoteInput.StartLyricInput` (which posts its own `AdvanceLyricInput`),
  then per syllable `NoteInput.AcceptCurrentLyricInput?LyricText=<url-encoded>&LyricsEntryAdvanceType=`
  `kHyphenateCurrentWord` (mid-word) / `kEndOrExtendCurrentWord` (end of
  word; with empty text, a melisma) / `kEndInput` (last), each followed by
  `NoteInput.AdvanceLyricInput` except the last. The popover needs Dorico
  frontmost and time: about 0.8 s after opening and 0.3 s between
  commands; sent faster, the accepts run in ~15 ms and do nothing. One undo
  step per syllable, plus the selection. Editing an existing lyric logs
  `NoteInput.EnterAtPoint?X=..&Y=..` (a double-click by page position) and
  an accept with `kEndInput`, so it can only be reached by pixel position.
  A selected lyric's `getproperties` gives its syllable type, verse, and
  placement values, but never its text.
- **Qt.** Dorico 6.2.30 is built on Qt 6.10.1 (universal, Apple LLVM 15),
  with QtLabs QML modules; dialogs are reachable through macOS
  accessibility, the score canvas is not.

## Safety rules

- Never follow a Lua write with `Edit.Undo` unless the script is known to
  have changed something: an undo after a failed script reverts the user's
  own last edit. (`Edit.Redo` puts it back.)
- A script that creates and deletes (net zero) still adds an undo step.
- Commands that open dialogs block Dorico until a person dismisses them;
  the client then times out with "a dialog may be open".
- Tests must not reach Dorico: `tests/conftest.py` fails any connection to
  port 4560.

## Live verification (2026-09-27, Dorico 6.2.30)

On a scratch piano score, each step read back and then undone to the
original notes and ids:

- read: 9 notes with ids, positions, durations, MIDI pitch and spelling
- bar measurement: 4/4 → 1024, undone, score unchanged, cache hit
- one batch (4 ops): B♭4 respelling, C–E–G chord, text, rest; rendered
  preview checked; one undo restored everything
- CLI batch: transpose bar 1 up a major second (D5 C♯5 B4 A4), set-pitch by
  staff/bar/index spelled F♯4, D♭–F–A♭ chord, text; dry run then apply; one
  undo restored
- `add-clef`: treble clef on the bass staff at bar 2, rendered, read back
  as `clef.treble`, undone
- MCP tools: dry run refused on a pitch guard; delete + add-rest + add-text;
  text read back with its paragraph style; preview PNG export; `undo`
  restored
