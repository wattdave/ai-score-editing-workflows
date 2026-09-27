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

`flow.instruments` has one entry per stave, in stave order, with the
instrument id (names come from `score.players[*].instruments`) and the
instrument's voice streams. A two-stave instrument lists the same voices on
both entries; when it has one voice per stave they are given out in order.
Confirmed on a two-stave piano and an imported eight-staff SATB score. (The
first rule used, voice-follows-preceding-stave by id, failed on the import.)

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
| `score_structure` | ⚠️ | bar lengths and key signature positions only (see gaps) |
| `query_score` | ✅ | staves, bars, types (Sibelius names or Dorico's), voice, `where` |
| `apply_batch` + `dry_run` | ✅ | every op checked first; one undo step |
| `set-pitch` | ✅ | replaces the note, spelled as asked; new id reported |
| `delete` | ✅ | |
| `add-note` (chords), `add-rest`, `add-text` | ✅ | into voices that already exist |
| (Dorico only) `add-clef` | ✅ | treble, bass, percussion, tab, tab.4 from the score's clef library |
| `transpose` | ✅ | per-note, respelled diatonically |
| `set` (Dx, Dy, Hidden, ...), `tie`, `bracket`, `flip-stem`, `nudge`, `beam` | ❌ | not in the Lua model |
| `add-line`, `add-lyric` | ❌ | no line or lyric classes exposed |
| `copy-passage` | ❌ | `copyRange(from, to, stream, dest, 0)` runs but copies nothing |
| `set-key`, `set-time` | 🔜/❌ | create calls exist but need elements Lua cannot construct |
| `set-break` | 🔜 | `createSystemBreak(0, pos)` makes a `BreakEvent`, but the render broke at a different bar; meaning of the int unknown |
| `set-barline`, `set-bar-number`, `add-bars`, `set-layout`, `hide-empty-staves`, `delete-voice` | ❌ | not exposed |
| `undo` | ✅ | stops when Dorico has nothing to undo |
| `save_score` | ⚠️ | saves a copy to a given `.dorico` path; the project keeps its own file |
| `export_score` | ⚠️ | first-page preview PDF/PNG only |

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
