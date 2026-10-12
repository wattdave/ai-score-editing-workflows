# Dorico back end

After installing a new Dorico, run the checks in
[dorico-upgrade-checklist.md](dorico-upgrade-checklist.md).

`dorico-mcp` and `dorico-cli` drive the project open in Dorico the way
`sibelius-mcp` and `sibelius-cli` drive Sibelius: the same tool
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
| `query_score` | ✅ | staves, bars, types (Sibelius names or Dorico's), voice, `where`; lyric staves via `dump()` with ids, lyric text with `lyrics=true` |
| `apply_batch` + `dry_run` | ✅ | every op checked first; one undo step |
| `set-pitch` | ✅ | replaces the note, spelled as asked; new id reported |
| `delete` | ✅ | |
| `add-note` (chords), `add-rest`, `add-text` | ✅ | into voices that already exist |
| (Dorico only) `add-clef` | ✅ | treble, bass, percussion, tab, tab.4 from the score's clef library |
| `transpose` | ✅ | per-note, respelled diatonically |
| `set` (Dx, Dy, Hidden, ...), `tie`, `bracket`, `flip-stem`, `nudge`, `beam` | ❌ | not in the Lua model |
| `add-line` | ⚠️ | crescendo/diminuendo hairpins, 8va/8vb, trills, pedal lines and glissandos at any position and length (multiples of 32), by command then resize (see gaps); hairpin lengths cannot be read back; octave lines keep the sounding pitch and rewrite the notes, unlike Sibelius; other Sibelius line styles are not mapped. Slurs: `add-slur`, note to next note |
| (Dorico only) `add-dynamic`, `set-articulation`, `add-slur`, `add-tempo`, `add-rehearsal-mark` | ✅ | by command at a note; slurs cannot be read back |
| (Dorico only) `read_lyrics`, `edit_lyrics` | ⚠️ | a player's verse as text through the Edit Lyrics dialog; edits must keep the syllable count |
| `add-lyric` → `add-lyrics` | ⚠️ | verses 1-10, typed through the lyric popover by command (see gaps); refuses to type over a lyric already in that verse |
| `copy-passage` | ✅ | by selection + `Edit.Copy` / `Edit.Paste` (see gaps); destPosition 0 only |
| `set-key`, `set-time` | ✅ | by command at the start of any bar, bar 1 included: 2 undo steps each, 4 where the bar starts with implicit rests only (a temporary rest is selected); refused only when every voice holds a note over the barline (see gaps). `set-time` takes a `pickup` (Dorico only). A time signature is removed with `delete` by its id (`query_score` type `TimeSignature`) |
| `set-break` | ✅ | system breaks via `Edit.CreateSystemBreak` on a selected note (2 undo steps each), or a temporary rest in a bar with nothing of its own (4); refused only where every voice holds a note over the barline |
| `set-barline` | ⚠️ | double, final, start/end repeat, by command like set-time (a start repeat at bar 1 keeps the opening time signature); `position` puts one part-way through a bar (Dorico only) |
| `delete-voice` | ✅ | Lua `deleteEventsInRange` over the bars: everything starting there, lyrics included; staves with lyrics too; one undo step with the batch |
| `add-bars` | ⚠️ | before a bar by the bars popover (`+N`) or at the end (`AddBarAtEndOfFlow`); no `length` (irregular bars); appended bars are not read back |
| `delete-bars` | ✅ | plans a selection that covers exactly the bars (see "Selecting bars"): one `EventEdit.Select`, some `EventEdit.NavigateRightExtendBar`, one `Edit.DeleteBars`; falls back to one bar at a time when no staff has such a selection. A note after the range must move up by the length removed. `undo` takes at most 20 steps per call |
| `set-layout` | ⚠️ | `Project.Layout.SetOptions`, one undo step, read back; the full score layout unless `layout` names another; no `extraSpacesBelowVocalStaves`; page sizes with ambiguous dimensions need `pageWidth`/`pageHeight` (mm); left/right margins need identical margins. `score_structure` reports the settings as `layout` |
| `hide-empty-staves` | ⚠️ | not over a range of bars: Dorico hides empty staves per layout, set by `set-layout`'s `hideEmptyStaves` (`never`, `after-first-system`, `all-systems`) |
| `set-bar-number` | ❌ | the number only exists inside a dialog: no command carries it and nothing reads it back (see gaps) |
| `undo` | ✅ | stops when Dorico has nothing to undo |
| (Dorico only) `project_info`, `set_project_info` | ✅ | project-level Project Info fields through the Project Info dialog (typed); not per-flow |
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
  **What a bar rest measures (2026-09-28, at every beat of every voice).**
  `createBarRest` at a barline returns the length to the *next barline*,
  but only in a voice with nothing sounding there. Anywhere else, or where
  the voice has a note starting or held over, it returns 0. The staff,
  player and timebase streams refuse bar rests altogether. So:
  - each division is measured in a voice free at that point, and so is the
    bar after it: a pick-up (`4/4\,2` measures 512) or the part of a bar
    after a barline placed part-way through it is shorter than the meter,
    and only the next bar gives the meter;
  - a bar number change or barline on its own at a bar start is a
    `BarDivisionEvent` too, and simply measures the meter;
  - where every voice has a note (common in choral music), the bars cannot
    be measured, and reads use the MusicXML export instead.

  #68 took a 0 to mean "a division without a meter" and carried the previous
  length on. A 0 only means the voice was busy, so a real time signature
  change there (3/4 at bar 3 of the fixture, every voice with a note) read as
  4/4 carrying on, silently; the carry is gone.

  **Bar numbering.** Every barline-to-barline measure is a bar, as in the
  MusicXML export and the Sibelius back end: a pick-up is bar 1, and each
  part of a bar split by a mid-bar barline is a bar of its own. Dorico
  *shows* a pick-up as bar 0 and both parts of a split bar with the same
  number (its bar ruler read 0, 1, 1, 2, 2, 3, 4 for a pick-up and two
  mid-bar repeats), so its displayed numbers can be lower than these.
  Dorico places `:|` and `|:` part-way through a bar (at the selected note)
  with a hidden restatement of the meter (a signpost such as
  "4/4 (q, 1+1+1+1)"), and makes no visible time signature.

  **MusicXML.** A measure is as long as its music. Dorico's export marks
  only the *later* part of a split bar `implicit="yes"` (numbered `X1`,
  `X2`, ...), and Sibelius marks neither a pick-up nor a split, so padding
  unmarked short measures to the meter (as before) put every later bar in
  the wrong place.
- **Key signatures.** `TonalityDivisionElement` is an unregistered class:
  positions are known, keys are not.
- **Spelling.** `kNoteSpelling` accepts writes that change nothing, so a
  respelled pitch is a delete plus a create with an explicit
  `MIDIPitchWithSpelling`. Setting `kNotePitch` alone lets Dorico pick the
  spelling (A4 + 2 became A𝄪4).
- **Respelling (2026-09-27).** With a note selected by id,
  `NoteEdit.RespellUsingNoteNameAbove` / `…Below` respell it one letter
  name up or down (G2 -> A𝄫2 -> G2 -> F𝄪2), and the Lua read shows the new
  spelling. `NoteEdit.ResetSpellingInCurrentLayout` / `…InAllLayouts` did
  not undo that respelling (they seem to clear layout-specific overrides
  only). `NoteEdit.ResetSpellAutomatically` opens the QML "Respell Notes
  Automatically" dialog, not tried. These could let set-pitch keep the
  note (set `kNotePitch`, then respell) instead of replacing it, at the
  cost of extra undo steps; not done, since it is not yet known what the
  replacement loses.
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
  **Where it exports (2026-09-28).** The "Export to:" folder is remembered
  per project (Hallelujah's was its score folder, the fixture's `~/Music`),
  so reads used to write `Flows from <title>` into the user's folders, and
  a second read raised an overwrite prompt per file (the back end answered
  them, so an export of the user's own there would have been replaced).
  Now every export goes to `~/.cache/sibelius-websocket-cli/dorico/musicxml`,
  emptied first, so no prompts come. The button after the folder path opens
  a macOS **Open** panel; shift-command-G, the path, Return, Return chooses
  the folder. Dorico then remembers it for the project; a **Cancel** keeps
  the old folder, and an OK with every flow unticked writes nothing but also
  keeps the old folder, so it cannot be put back without exporting there.
  Side effect: after the back end has read a project, that project's
  Export MusicXML window suggests the private folder. The first export of a
  project takes about 13 s (the panel), later ones about 7 s. Reading the
  window is retried, since it was once read before Dorico filled in the
  folder ("could not read the Export to: folder").

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
  get a temporary rest to select (see the signatures section), and only a
  bar where every voice holds a note over the barline is refused.
  Dorico's implied rests are not events, and `Edit.GoToLocation` /
  `GoToRhythmicPosition` do not select anything. A temporary rest to select
  worked but was dropped as too fragile to undo; the signature ops now use
  one (next section), with the undo steps measured.
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
- **Further verses (2026-09-27).** In the popover, Down Arrow logs
  `NoteInput.AcceptCurrentLyricInput?LyricText=<the lyric already there>&LyricsEntryAdvanceType=kIncrementVerseNumber`
  and `NoteInput.AdvanceLyricInput`: it accepts the current line's text
  and moves down a line at the same note. Sent by command it works the
  same: one increment per line below the target, then the syllables as for
  verse 1, and later syllables stay on that line. The text sent must be
  the lyric already on that line: an increment with no `LyricText` deleted
  the verse-1 lyric under it, while re-sending it kept it, hyphenation
  included (a `begin` syllable stayed `begin`). On a line with no lyric no
  text is sent and none is created (verse 3 over an empty verse 2 left
  verse 2 empty). Undo steps, measured with a marker edit: the selection 1,
  each increment 1, each syllable 1. `add-lyrics` reads the lower lines'
  text at the first note from a MusicXML export when the staff has lyrics,
  and refuses a batch whose syllables would land on a note that already
  has a lyric in the target verse (typing replaces it). Up Arrow (chorus),
  Shift-Up/Down (above/below the staff) and Alt-Down (translation) were not
  tried.
- **Qt.** Dorico 6.2.30 is built on Qt 6.10.1 (universal, Apple LLVM 15),
  with QtLabs QML modules; dialogs are reachable through macOS
  accessibility, the score canvas is not.

- **Reading and editing a line of lyrics (2026-09-27).** In Write mode,
  `Edit.SelectAll` then `Filter.LyricsLine1` (…`Line5`) selects a verse
  without pixels; `Edit.LineOfLyrics` ("Edit Line of Lyrics…") opens an
  "Edit Lyrics" dialog whose text area (readable and settable through
  System Events) holds the verse of the *first staff in the selection*,
  hyphenated ("ma-king lyr-ics"), with a counter "Current number of
  lyrics: N (target: N)". To reach one player, show its part layout first:
  `Window.SwitchToLayout?OpenScoreID=&ScoreLayoutViewContainerID=&LayoutID=`
  (ids from `getstatus` and `getlayouts`), then switch back. Setting the
  text and pressing OK applied a same-length edit ("lark" -> "song", read
  back, restored the same way); an edit with one more syllable was not
  applied, and the counter did not change when the text was set by
  script. Selecting a clef by id cannot be widened (`SelectMore`,
  `SelectToEndOfSystem`, `NavigateRightExtendBar` all refused), so part
  layouts are the only per-player route found. `Edit.SelectAll` is refused
  outside Write mode (`Window.SwitchMode?WindowMode=kWriteMode`).
  **Undo history (2026-09-27):** `Edit.SelectAll` and `Filter.LyricsLine<n>`
  are undo steps (layout and mode switches, opening and cancelling the
  dialog are not), so a read left two. Dorico's Edit menu names the step on
  top ("Undo Select", "Undo Select All", "Undo Filter Lyrics"; "Redo …"
  likewise), readable through System Events, but its titles lag commands by
  up to about a second: read at 0.4 s after an undo it still showed the old
  one, at 1.5 s it was right both passively and with the menu opened. A read
  now undoes its two steps afterwards, each only once the title has settled
  and names that step, and leaves them if anything else is on top (or the
  UI is not English). An edit's selections are under the edit, so
  `edit_lyrics` reports `undoSteps` 3 (Select All, Filter, the edit); its
  read-back cleans up after itself. Measured with a marker edit: a read
  leaves 0 steps, with or without a prior selection; undoing an edit's 3
  steps restored the text and kept the marker.
  `dorico/lyrics_dialog.py` does this (the `read_lyrics` / `edit_lyrics`
  tools), restoring the window's layout (Lua `DoApp().currentLayoutID`)
  and mode afterwards. `Edit.LineOfLyrics` runs for as long as the dialog is
  open and applies the edit itself: no separate command is logged, so there
  is no way around the dialog.
- **QML (2026-09-27).** Dorico's UI is largely QtQuick; 88 `Dorico/…qml`
  sources are compiled into the main binary as readable text. The build has
  no QML debugging enabler and ships no `qmltooling` plugins, so Qt's QML
  inspector/debugger is not available; GammaRay-style injection would
  fight the hardened runtime. `scripts/extract_dorico_qml.py OUT_DIR`
  recovers them (324 unique files in 6.2.30, named by content hash, with an
  INDEX.txt of root type, titles and controller calls). They are layout
  bound to C++ `controller` objects (`controller.onLyricsPopoverButtonClicked()`),
  so they show a screen's structure but offer nothing to call. 48 are
  `DoricoDialog`s (Project Statistics, Respell Notes Automatically,
  Generate Notes From Chord Symbols, Edit Instrument Families, …). The
  dialogs driven here (Edit Lyrics, Export MusicXML) are not among them:
  they are Qt Widgets, which is why macOS accessibility reaches them.

- **Project Info and tokens (2026-09-27).** Text tokens such as
  `{@projectComposer@}` resolve in page frames (title pages, headers), not
  in staff text items: a Lua-created text shows the token literally.
  `score.title` is read-only in Lua. `File.ScoreInfo` opens the Project
  Info dialog (Qt Widgets, named text fields plus Apply/Close), which
  `dorico/project_info.py` drives. Setting a field's value through
  accessibility shows the text but Apply ignores it (Qt sees no edit), so
  values are typed; Cmd-A is Dorico's Select All, so a field is cleared by
  deleting each character. The dialog's Project/flow list does not respond
  to accessibility, so only project-level fields are handled.

- **Time signatures, keys and barlines (2026-09-27).** Entered through
  the popovers (Shift+K `D`, Shift+B `||`) Dorico logs
  `NoteInput.CreateKeySignature?Definition=D&UseLocalOverride=0` and
  `NoteInput.CreateBarLine?Definition=||&UseLocalOverride=0`; with a note
  selected, `NoteInput.CreateTimeSignature?Definition=3/4`,
  `CreateKeySignature?Definition=d` (lower case = minor) and `CreateBarLine`
  with `|]`, `final`, `:|`, `|:`, `||` all work. **Parameters must not be
  URL-encoded**: Dorico does not decode them (`%7C%5D` did nothing), so
  values are sent raw. Dorico also splits parameters on **commas** (a
  lyric "well," arrived as "well"), but a **backslash escapes** both:
  `well\,` -> "well,", `rock\&roll` -> "rock&roll"; apostrophes need
  nothing. `score.command_value` escapes them and refuses backslashes and
  line breaks. Key changes are
  `TonalityDivisionEvent`s and time signatures and barlines
  `BarDivisionEvent`s in the global timebase (a barline at the same bar
  replaces the time signature's event, which then carries both). Dorico
  places the change at the *selected item's position*, so the item must
  start at the bar (a note half a beat in made a short bar first).
  `EventEdit.EditExistingTimeSignature` / `…KeySignature` with an event id
  and `Text` are accepted but change nothing. **Bar 1 works the same way
  as any other bar (2026-09-27):** with a bar-1 note selected,
  `CreateTimeSignature?Definition=3/4` replaced the opening 4/4 (a new
  `BarDivisionEvent` id at position 0; bars measured 768 and the music was
  re-barred), `CreateKeySignature?Definition=G` replaced the opening key
  (new `TonalityDivisionEvent` id), and `CreateBarLine?Definition=|:` put a
  start repeat at bar 1 in a new event that keeps 4/4. Two undo steps each,
  as elsewhere; a time and key batch at bar 1 is 4.
  **Bars with nothing to select (2026-09-27).** Where no staff has a note
  or rest starting on the bar's first beat (Dorico's implicit rests are not
  events), the op creates a temporary rest there by Lua (a quarter, shorter
  if a note follows sooner; the first voice, top staff first, with nothing
  held over the barline), selects it, runs the command, and deletes it with
  `EventEdit.Delete` by id (which works in streams Lua can only dump).
  Measured with a marker edit: creating it 1 step, deleting a *rest* by id 1
  (a note is 2), so these ops are 4 steps; undoing the reported count left
  exactly the marker for time, key, barline and a time + key batch (8).
  On the fixture's empty bar 4, 3/4 rendered with Dorico's own bar rests
  and no leftover rest. Refused only where every voice holds a note over
  the barline (a tie across it is one event), since a rest there would cut
  the note short. `set-break` does the same (2026-09-27): a break at the
  fixture's empty bar 4 rendered with a new system there and no leftover
  rest, 4 undo steps, exact with a marker (a break at bar 3 and bar 4 in
  one batch: 6). The timebase `dump()`
  was no help in reading them back: it lists these events only as
  `element ID = 0`, not their content, so bar lengths (measured) and the
  new event ids are the read-back.
  Keystroke-driven popovers are fragile: a leftover lyric popover took a
  Shift+M. The ops send the commands directly.

- **Dynamics, articulations, slurs, tempo, rehearsal marks, copy/paste
  (2026-09-27).** All tested on a note selected by id, rendered, and undone:
  - `NoteInput.CreateDynamic?Definition=p` makes a `DynamicGroupEvent` in
    the staff's stave stream at the note (readable from Lua).
  - Articulation shortcuts log `NoteInput.SetArticulation?Value=kAccent` /
    `kStaccato`; they become note properties (`kArticulationForce`,
    `kArticulationDuration`), readable from Lua.
  - S logs `NoteInput.SlurStart`; with one note selected it slurs to the
    next note. The slur is in no stream Lua can see. `SlurStop` on a later
    note did not extend it; `SlurStart` on a selection extended with
    `EventEdit.NavigateRightExtend` spans it, but each step stops on every
    note and rest, implied rests included, so the count is not knowable and
    `add-slur` only slurs a note to the next.
  - `SetArticulation` values: kAccent / kMarcato set `kArticulationForce`
    0/1; kStaccatissimo / kStaccato / kStaccatoTenuto / kTenuto set
    `kArticulationDuration` 0-3; kStress / kUnstress set
    `kArticulationStress` 0/1 (kSpiccato, kStrongAccent do nothing). Reads
    report them as a note's `articulations`.
  - `NoteInput.CreateTempo?Definition=Allegro` and `…=q=120` and
    `NoteInput.CreateRehearsalMark` work (a second tempo at the same
    position replaced the first), but they make the **global timebase
    unreadable** to Lua ("Not implemented"), taking time and key signature
    events with it: such scores need the MusicXML read.
  - From a selected note, `EventEdit.NavigateRightExtend` extends the
    selection (it is refused from a clef); `Edit.Copy`, then selecting a
    destination note and `Edit.Paste`, pasted the passage at that note's
    position, overwriting what was there, as one undo step.

- **dump() rescues unreadable streams (2026-09-27).** Window mode makes
  no difference to the "Not implemented" failure (same in Write, Engrave,
  Play, Print and Setup), but `EventStream:dump()`, written by Dorico's C++,
  still lists every event of such a stream: notes with id, position,
  duration and spelled pitch, `kLyricEvent`s (id, position, element id, no
  text), and in the timebase `kImmediateTempoChangeEvent` /
  `kRehearsalMarkEvent` alongside time and key signatures. The bridge
  reads those streams from `dump()` (items marked `source: "dump"`, MIDI
  pitch computed from the spelling), so lyric staves keep their ids:
  command ops (set-break, set-time, set-key, set-barline, selections) work
  on them. Lua ops (set-pitch, delete, transpose, add-lyrics) refuse them,
  since there is no Lua object to change. MusicXML is now exported only for
  voice-layout questions, streams that cannot even be dumped, or
  `query_score(lyrics=true)`, which attaches lyric text to notes.

- **Editing notes on staves with lyrics (2026-09-27).** Notes read from
  `dump()` have ids but no Lua objects, so `set-pitch`, `delete` and
  `transpose` go through commands instead: `EventEdit.Delete?FlowID=&EventID=
  &EventBlockID=` deletes by id with no selection (2 undo steps; the note's
  lyric event stays); a pitch change selects the note, runs
  `NoteEdit.PitchUpChromatic` / `PitchDownChromatic?count=N` (Dorico spells
  it; A4 +1 became A#4) and then `NoteEdit.RespellUsingNoteNameAbove` /
  `…Below` until the letter matches (B♭4). The note keeps its id, lyric and
  anything attached. Undo steps: selection + move + each respell. Checked
  live: the verse text was unchanged throughout.

- **Lines (2026-09-27).** With a note (or rest) selected, each of these
  makes a line starting there and lasting as long as the item:
  `NoteInput.CreateDynamic?Definition=<` / `>` (hairpin; a
  `DynamicGroupEvent` in the staff's stave stream whose length is in its
  dynamic group element, which Lua cannot reach: duration reads 0),
  `NoteInput.OttavaLineStart?Octave=1` / `-1` (8va / 8vb, an
  `OttavaLineEvent` with a readable duration), `NoteInput.CreateOrnament?Definition=tr`
  (`TrillEvent` in the voice stream), `NoteInput.CreatePlayingTechnique?Definition=ped`
  (`PedalLineEvent`; on a piano it lands in the *upper* staff's stream even
  when started on the lower, and is drawn below the lower staff) and
  `NoteInput.CreateGlissando` (to the next note). Trill and pedal events
  make their streams unreadable to Lua, so those are read from `dump()`,
  lengths included. Octave lines keep the sounding pitch: Dorico rewrites
  the notes under them an octave the other way (Sibelius keeps the written
  notes and changes playback). A selected line is resized exactly by
  `EventEdit.DurationLengthenByValue` / `DurationShortenByValue?RhythmicGridResolutionValue=`
  `kSemibreve`, `kMinim`, `kCrotchet`, `kQuaver`, `kSemiquaver` or
  `kDemisemiquaver` (each checked on an octave line: +1024 … +32, id kept);
  `kBreve` and `kHemidemisemiquaver` are accepted but moved the end by 256
  and 160, so they are never sent. Undo steps, measured with a marker for
  each kind: selection 1, command 1, selecting the line 1, each resize 1
  (a glissando: 2). `add-line` does exactly this, with a temporary rest
  where nothing starts at the position; a batch of all six kinds reported
  24 steps and undoing exactly 24 left the marker. Lua's
  `EventStream:createOttavaLine(pos, ?, duration, ?, string)` makes events
  the layout ignores (like Lua-made system breaks) and accepts any string,
  so it is not used.

- **copy-passage (2026-09-27).** `Edit.SelectMore` from a *note* selects
  its whole bar on that staff (from a rest it does not), and
  `EventEdit.NavigateRightExtendBar` then adds exactly one bar per call. What
  `Edit.Copy` takes starts at the range's first note, not the barline, and
  `Edit.Paste` lines that note up with the selected destination item, so the
  op anchors the paste at destination bar start + that note's offset: an
  existing item there, or a temporary rest it creates (overwritten by the
  paste). Paste inserts if Dorico is in Insert mode, so the op forces
  `NoteInput.Mode?NoteInputMode=kOverwrite` and restores the user's mode.
  The jump bar's go-to-bar logs no command (it is internal to the UI), and
  `Edit.GoTo` / `Edit.GoToLocation` only move the view. Measured undo steps
  per staff: temporary rest (if any) + select + SelectMore + one per extra
  bar + select anchor + paste.

- **Placing voices by probe (2026-09-27).** A dynamic created at a note
  goes into the stave stream of the staff the note is on, so
  `service.probe_placements` finds each ambiguous voice's staff by
  selecting one of its notes, `NoteInput.CreateDynamic?Definition=p`,
  reading which staff's stream got it, and undoing it. `layout.resolve`
  then derives each instrument's staves (contiguous, in order) and the
  voice placements without a MusicXML export; voices with no notes stay
  unplaced. Like bar measurement this edits the score briefly and clears
  redo. Each probe also undoes its selection (every `EventEdit.Select` is
  an undo step, even re-selecting the same note), then checks the score
  against the read taken before and redoes if anything else was reverted,
  so reads leave the undo history as they found it; until #60 each read of
  a probed score left one selection per voice there, and `undo` of a
  batch's reported steps reverted those instead. Bars are measured first
  (see Bar numbers above); where no voice is free to measure a bar, the score
  reads from MusicXML. Bar measurement
  now also works when every voice has lyrics (Lua can create in and delete
  from a stream it can only dump).

- **Deleting a voice (2026-09-28).** `EventStream:deleteEventsInRange(start,
  end)` deletes the events that *start* in [start, end): a note held into
  the range from before it keeps its full length, and one starting at the
  end is kept. Nothing is put in their place (Dorico shows implicit rests),
  lyrics go with their notes (they are events in the same stream), and it
  works on streams Lua can only dump. One undo step, like any Lua script.
- **Adding bars (2026-09-28).** With an item selected, the bars popover's
  `NoteInput.CreateBarLine?Definition=+N` inserts N bars of the meter in
  force before it (ids kept; undo title "Create Barline"; bar 1 works, the
  opening signatures stay at the start). `NoteInput.AddBarAtEndOfFlow`
  appends one bar with nothing selected, one undo step. Lua cannot read how
  many bars a flow has (Flow has no length attribute and the timebase
  dump has no end marker), so appended bars are not read back, and a bar
  past the last one holding anything is checked against a MusicXML export
  before inserting: a temporary rest created past the end makes Dorico
  lengthen the flow to hold it (before bar 6 of 4 left 7 bars). `+3q`
  inserts beats into the bar rather than a bar; a `|` barline after them
  makes an irregular bar, which reads correctly since #68 but is not
  offered yet.
- **Bar number changes, layout options, staff visibility (2026-09-28).**
  - `Edit.AddBarNumberChange` opens "Insert Bar Number Change" (Qt
    Widgets: Primary/Subordinate spin boxes, Type Primary / Subordinate /
    Don't Include / Continue Primary, "Hide primary bar numbers") and logs
    no parameters. The change is a `BarDivisionEvent`. Driving the spin box
    failed: AXIncrement steps by 10000, and typed digits registered once
    in three tries, with value reads lagging.
  - Walked through by hand (2026-09-28), to see whether any command
    carries the number:
    - Typing in the dialog works for a person: Primary 10 at bar 3 made
      the bar ruler read 1, 2, 10, 11, with an orange italic 10 above the
      bar. OK still logs only `Edit.AddBarNumberChange`.
    - **A bar number change is a hidden time signature.** Selected, the
      status bar calls it a time signature, and the Properties panel shows
      only Common and Time Signatures ("Hide time signature" on). There is
      no Bar Numbers group, so no property edit that would log the number.
    - Double-clicking it opens the **time signature popover**
      (`NoteInput.EnterAtPoint` then
      `EventEdit.EditExistingTimeSignature?...&Text=4/4`). Closing it left
      two visible 4/4 time signatures and note input steps on the undo
      stack ("Create Time Signature" twice, "Start Note Input", "Stop Note
      Input"). Never double-click one to edit it.
    - Editing an existing change through the dialog (Primary 12) logs only
      `Edit.AddBarNumberChange?OpenScoreID=-1&LayoutID=-1`, and the
      `BarDivisionEvent` gets a new id.
    - **Nothing reads the number back.** Lua shows the event but not its
      element, and the MusicXML export numbers measures 1 to n whatever the
      bar numbers are (`<measure number="3">` with bar 3 showing 12).
    - So set-bar-number could only type into the dialog without being able
      to check the result. It stays refused.
  - `Project.Layout.Options` opens a modeless Layout Options window whose
    controls accessibility lists (page size, orientation, rastral size,
    margins in points, ...), but Qt ignores accessibility presses there
    (Apply stays disabled), and System Events' `click at` is an
    accessibility press too. The dialog is not needed, though (next item).
- **Layout Options by command (2026-09-28).** Changing an option by hand
  and pressing Apply logs
  `Project.Layout.SetOptions?LayoutIDArray=0&Dictionary=list: {string: "pageSizeAndMarginOptions.pageWidth"}\, {string: "792.000000"}\, {string: "pageSizeAndMarginOptions.pageHeight"}\, {string: "612.000000"}&OpenScoreID=0`:
  key and value strings in turn, commas escaped. Sent over the WebSocket
  it applies at once (several keys in one command too), as one undo step
  titled "Set Layout Options", which it adds even when nothing changes.
  Enum values can be sent by name (`{string: "kAllSystems"}`) or by their
  index in the option's `enumValues` (`{int: 0}`, as Apply sends them).
  The Remote Control API's
  `{"message": "getoptions", "optionsType": "kLayout", "layoutID": N}`
  answers `optionslist`: all 241 of the layout's options with `path`,
  `valueType`, `currentValue` (text) and, for enums, `enumValues`. So
  options are read back exactly. Lengths are in points (`kPun`: page
  size, margins, music frame margins, `defaultSpaceSize`, which is one
  staff space) or staff spaces (`kStaveUnit`: `verticalStaveGapOptions.*`).
  Landscape is only width and height swapped. With identical margins
  (`pageMargins.type` `kIdentical`), `margins.outer` is the left margin and
  `margins.inner` the right (checked in renders). `hideEmptyStavesPolicy`
  is `kAllSystems`, `kAfterFirstSystem` or `kNever`. The page size presets
  (`PageDimensionsPresetEntityID`) could not be listed
  (`getlibraryentities` for `kPageDimensionsPresetCollection` is empty), so
  set-layout sends sizes in points. Most option paths are in the binary as
  `xxxOptions.yyy` strings (2157 of them); `getoptions` is the reliable
  list.
  - `Edit.ManualStaffVisibility` opens a dialog whose per-staff rows are
    not exposed; OK runs `Internal.Command?BlobID=`
    (HideEmptyStavesOverridesInternalCommand), which cannot be replayed.
    "Hide All" hid a staff that holds music (and split the system there),
    so it is not hide-empty-staves.

- **Pick-ups, mid-bar repeats, and scores exported with half-bars
  (2026-09-28).** Sibelius can only put a repeat part-way through a bar by
  splitting the bar with (hidden) time signatures; its MusicXML keeps them
  (Hallelujah in 6/4: 3/4 half-bars around each repeat, 6/4 after), and
  Dorico's import shows them. Dorico writes this natively:
  - `set-time` with `pickup` sends the popover's `N/D,beats` (the comma
    escaped): the pick-up in beats of the denominator, decimals allowed.
    `6/8,3` measured 384 (three eighths), `4/4,1.5` measured 384.
  - `set-barline` with `position` puts the barline at the item there, as the
    popover does; Dorico splits the bar with a hidden restatement of the
    meter. Both parts keep one displayed number.
  - A time signature is a `BarDivisionEvent` in the timebase; `delete` by
    its id removes it through Lua (one undo step with the batch), and the
    music re-bars with the meter before it. Removing the half-bars' 2/4 and
    the 4/4 after them was not enough on its own: **the imported repeat
    barline's event carried the 2/4 too** (signpost "2/4 (q, 1+1)"), so the
    music after it stayed in 2/4. Delete the repeat's event as well, and put
    the repeat back part-way through the bar with `set-barline` `position`.
  - **Order matters: set the pick-up first.** A barline placed part-way
    through a bar keeps the rest of that bar as its offset; a pick-up made
    afterwards moves every barline, which left the repeat on a barline and a
    two-beat bar after it. With the pick-up first, then the positions read
    again, then the repeats, the fixture's ruler read 0, 1, 2, 2, 3, 4.
  - The recipe on the fixture, each step checked with a marker edit:
    delete the extra time signatures and the imported repeats (1 undo step),
    `set-time` with `pickup` at bar 1 (2), `set-barline` with `position`
    (2 each). Batches refuse a later op that names a bar an earlier
    add-bars, set-time or mid-bar barline moves, as on Sibelius.
  - Changing meters can lengthen the flow (the fixture gained an empty
    bar), and undo does not shorten it again; check the end of the flow.
  - In a flow with a tempo mark the timebase is read from `dump()`, so
    deleting a time signature goes through `EventEdit.Delete` by id
    rather than Lua. It works the same (the music re-bars) and is **one**
    undo step, like a rest; only a note is two (measured with a marker
    edit, 2026-09-28; until then every command delete was counted as two).
  - `query_score` with `types` now includes global items (time and key
    signatures, breaks, on staff 0) of those types.

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

## Reading the selection (checked 2026-10-11)

The Remote Control API does not report which items or bars are selected.
After a selection command Dorico pushes `selectionchanged` (with only
`openScoreID`) and `status`; the useful status fields are `hasSelection` and
`selectedEventType` (`kNoteEvent` for one note, `kMixed` after
`EventEdit.NavigateRightExtendBar`). `getproperties` lists the properties of
the selection's event types, not its extent. `getselection` is unhandled
(`kUnhandledMessage`) and the Lua classes list has no selection class. So a
selection's extent can only be checked from its effect, as `delete-bars` does.

## Selecting bars (measured 2026-10-11)

Measured on a copy of the Fugue 16 example, by selecting, running
`Edit.DeleteBars`, reading the removed events through Lua (no MusicXML
export) and undoing. `Edit.DeleteBars` removes every bar the selection
touches, so the bars removed show how far a selection reaches.

- **A selection holds whole items of one staff.** One note touches its own
  bar only; a note or rest that runs across a barline touches both bars.
- **`EventEdit.NavigateRightExtendBar` moves the selection's end to the next
  barline after it, then pulls in every item of the staff (all its voices)
  that starts before that barline, whole.** So a note tied over the barline
  drags the following bar in, and the next step starts from the end of that
  note. The steps are not "one bar each" on a staff with such notes; items on
  other staves are ignored. A selection already ending on a barline (a bar
  rest, or a note that ends the bar) moves a full bar on the first step.
- **Slurs and hairpins that start inside the selection are items too**:
  `Edit.DeleteBars` also removes every bar they span (a slur from bar 51 to
  53 makes a one-bar selection from bar 51 remove bars 51-53). They are not
  readable from Lua, so `delete-bars` cannot see them yet; the probe models
  them from a MusicXML export (`dorico_selection_probe.py bars --slurs`).
- **`delete-bars` treats a planned selection as a trial.** The planner finds
  up to three exact selections, each on a different staff (`plans`; `plan`
  is the first). Each is run in turn: select, extend steps, `Edit.DeleteBars`,
  then a note after the range must have moved up by exactly the length
  removed. If not (a slur or hairpin pulled more bars in), or Dorico rejects
  a step (condensed players answer `kCommandNotAllowed` to the extend step),
  the notes and rests are put back by undoing until they match a snapshot
  taken before the trial, and the next plan is tried; after the last, the
  bars are deleted one at a time. The result's `via` is `extend` (with
  `attempts` when it was not the first plan, and `retried` the last reason) or
  `per-bar after the planned selection failed` (with `attempts` and
  `retried`). Checked live on the fixture (a slur from bar 51 to 53; a
  one-bar delete from a slurred staff removed bar 51 only, via the fallback);
  the several-plan loop is covered by unit tests with a fake client. When no
  per-bar route exists (a bar with nothing to select and no room for a
  temporary rest) the last plan's failure is an error, as before. `undoSteps`
  in a dry run is the dearest route: the largest plan or the per-bar route,
  since a failed trial is undone.
- Replaying this on the events read predicted the bars removed in all 24
  trials (two staves, 1 to 8 steps), and `delete-bars` uses it:
  `score._extension_plan` returns an item in the first bar and the number
  of steps, or none when a tie over the last barline makes every selection
  on every staff overshoot.
- **A lyric is an item too (Smith Preces, 2026-10-11).** A melisma's lyric
  event starts on its note and lasts to the end of the extender line; one
  that runs past the barline drags the next bar in, like a tied note
  (Tenor "forth_": one step to the end of bar 2 touched bar 3). With lyrics
  counted, the model predicted 30 of 30 trials, and `_extension_plan`
  counts them.
- A step past the last bar of a flow stops at the last bar.
- **Measure removed bars from notes and rests only.** Slurs, lines and
  other spanning events that cross the edit are re-created with new ids,
  so they look removed from the bar before the range.
- **Liszt (open): the extend step that reaches the end of bar 8 goes on
  into bar 9, and bar 18 on into bar 20**, on both staves, with nothing
  in the events crossing either barline (see
  `docs/dorico-selection-research-plan.md`).
- **`Edit.SelectMore` is not a fixed step.** Once: the item's own bar. Twice:
  the bars either side too (4-6 from bar 5). Three times: nearly the whole
  flow. It also gave wrong counts after `NavigateRightExtendBar`.
- **`EventEdit.NavigateRightExtend`** (by item) from a note covered 1 bar
  after 4 and 8 steps and 2 after 16: it follows items, not bars.
- The method: select, run the command, read through Lua,
  undo until the events match the baseline. It needs no export.
- **Copying a group of bars** needs every item that starts in them, which is
  a different test from "bars touched". The step whose target is the end of
  the last bar pulls those in, whatever a tie then adds past it. The old
  recipe (`Edit.SelectMore`, then one step per further bar) is not a step
  and a half: on bars 6-9 of the example it copied 21 of 26 notes, while
  the planned recipe copied all of them (bars 5-8, 7-10, 8-10, 6-9, 5-12
  all exact; only 6-9 differed). `copy-passage` now uses
  `_extension_plan(..., cover=True)` with the first note of the range as
  anchor, and the old recipe only when no plan exists. Its read-back used to
  look at one destination voice only, so it reported `verified: false` for
  any staff with two voices; it now checks every voice of the destination.
