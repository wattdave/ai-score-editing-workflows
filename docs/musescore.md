# MuseScore

`musescore-mcp` drives the score open in MuseScore 4.6+ with the same model
as `sibelius-mcp` and `dorico-mcp`: staff/bar/index addresses with type and
position guards, 1/256-quarter units, MIDI pitches, checked batches that
are one undo step, and a dry run (a real one: the batch runs and is rolled
back). It talks to this repository's plug-in, "ScoreBridge", over a
WebSocket on port 8766 with a token. `.mcp.json` registers it as
`musescore`; the [musescore skill](../.claude/skills/musescore/SKILL.md)
covers using it.

```text
Claude Code ─stdio─> musescore-mcp (Python: planning, guards, units)
                        │ JSON {"id", "token", "method", "args"} over ws://127.0.0.1:8766
                        ▼
              msbridge.qml ("ScoreBridge", MuseScore 4 plug-in)
                        │ MuseScore plug-in API: curScore, Cursor, startCmd/endCmd, cmd()
                        ▼
                  the open score
```

## Setup

```bash
uv run musescore-cli install-plugin   # writes the plug-in with a fresh token
```

Restart MuseScore, enable "ScoreBridge" once in Plugins → Manage
plugins, then choose Plugins → ScoreBridge in the window of the score to
work on, every session (each MuseScore window is its own process, and the
bridge serves its own window). A tool that cannot connect says so.
`save_score` reads the score's file from its window, which needs
Accessibility permission for the terminal.

## Parity with the Sibelius back end

✅ equivalent, ⚠️ partial, ❌ missing. Checked live on MuseScore 4.7.5
(see [Live check](#live-check)).

| Sibelius tool / op | MuseScore | Notes |
|---|---|---|
| `score_overview` | ✅ | versions, score, metadata, staves with transposition, bar count |
| `score_structure` | ✅ | keys, times, barlines, repeats, breaks, bar numbers, layout |
| `query_score` | ✅ | plus `ticks` (exact for tuplets) and `msType`; grace notes listed read-only (`GraceNote`, with `graceType`) |
| `apply_batch` + `dry_run` | ✅ | the dry run really runs and rolls back; a MusicXML backup before a real run |
| `set` | ⚠️ | Dx, Dy, Hidden, CueSize, Beam (MuseScore modes), RestPosition, Text, Duration; lyric `NumNotes` is `Duration` |
| `ficta` | ✅ | hides the staff accidental, adds `<sym>accidentalFlat\|Natural\|Sharp</sym>` staff text above; re-query after (text takes an index) |
| `set-pitch`, `tie`, `bracket`, `flip-stem`, `nudge`, `delete`, `beam` | ✅ | set-pitch keeps ties, lyrics and articulations |
| `add-note`, `add-rest`, `add-tuplet`, `add-text`, `add-lyric`, `add-clef` | ✅ | voices 2-4 only where voice 1 has a note or rest starting |
| `add-line` | ⚠️ | slurs and octave lines; **hairpins refused** (they crashed MuseScore twice) |
| Dorico's note ops (`add-dynamic`, `set-articulation`, `add-slur`, `add-tempo`, `add-rehearsal-mark`) | ✅ | |
| `transpose`, `copy-passage`, `set-key`, `set-time` | ✅ | copy-passage goes through the clipboard, one per batch |
| `set-break`, `set-barline`, `set-bar-number`, `add-bars` | ✅ | no between-staves, tick, short or triple barlines in MuseScore |
| `set-layout` | ⚠️ | no octavo/hymn/quarto/folio/us-band sizes, no extra gap below vocal staves |
| `hide-empty-staves` | ⚠️ | whole score only |
| `delete-voice` | ✅ | |
| `undo` | ✅ | by steps |
| `save_score` | ⚠️ | saves in place (File > Save) and copies the file; a never-saved score is refused |
| `export_score` | ✅ | pdf, png, svg, musicxml, mxl, midi (`mid` is an alias), mp3, wav, flac, ogg; without `path` the score's own file name (read from its window) with the format's extension |
| `project_info`, `set_project_info` (Dorico) | ⚠️ | not undoable in MuseScore; the old values are returned |
| `read_lyrics`, `edit_lyrics` (Dorico) | ✅ | edit is one undo step, same syllable count |
| `add_instrument` (MuseScore) | ✅ | by id, MusicXML sound id or name; unknown ids refused |
| `set_staff_playback` (MuseScore) | ⚠️ | silences the notes there now (each note's `play`); the mixer is out of reach |

## Our back end

`musescore-cli` is this repository's own MuseScore back end, built
milestone by milestone from [musescore-backend-plan.md](musescore-backend-plan.md).
`.mcp.json` registers it as `musescore`.
It needs MuseScore 4.6 or newer.

```bash
uv run musescore-cli install-plugin   # then restart MuseScore
uv run musescore-cli overview
uv run musescore-cli query --staff 1 --bars 1-4 --where 'Pitch>=72'
uv run musescore-cli apply --dry-run --file batch.json
uv run musescore-cli apply --file batch.json
uv run musescore-cli undo --steps 1
uv run musescore-cli structure --bars 1-40
uv run musescore-cli save [--path copy.mscz]
uv run musescore-cli export --format pdf [--path score.pdf]   # default: beside the score
uv run musescore-cli info
uv run musescore-cli set-info --field composer=Traditional
uv run musescore-cli lyrics --staff 1 --verse 1
uv run musescore-cli edit-lyrics --staff 1 --text "Ma-king a joy-ful noise"
uv run musescore-mcp                  # the Sibelius tools plus project_info, set_project_info, read_lyrics, edit_lyrics
```

After installing, enable "ScoreBridge" once in Plugins → Manage
plugins, then choose Plugins → ScoreBridge in the window of the score
to work on, every session. It listens on port 8766 and refuses requests
without the token stored in `~/.config/ai-score-editing/musescore-token`.
Checked live on 4.7.5 (2026-10-03): `overview` read the score, its metadata
and staves; `undo` reverted a note added by hand.

Milestone 2 (bridge version 2) adds `query` and `apply` with set, set-pitch,
tie, bracket, flip-stem, nudge, delete and beam. Objects are addressed by
staff/bar/index, with `ticks` (480 per quarter) beside `position` because
tuplet positions don't convert exactly. A dry run makes the edits and rolls
them back, reporting each object before and after. A real run first writes a
MusicXML copy to `~/.cache/ai-score-editing/musescore/backups/`
(`$MUSESCORE_BACKUP_DIR` or `$SCORE_BACKUP_DIR` move it), named
`<score>.backup-YYYYmmdd-HHMMSS.musicxml` like every back end's backups
(`backups.py`).
Differences from Sibelius: `Beam` takes MuseScore's beam modes (0 auto,
1 none, 2 begin, 5 middle); a lyric's melisma is set with `Duration`, not
`NumNotes`; a tie needs a next note of the same pitch. The opening clef is
generated in MuseScore, so it isn't listed. Grace notes are listed as
`GraceNote` just before their main chord, at its position, with `graceType`
(acciaccatura, appoggiatura, grace8-after, ...) and `notes`; they are
read-only, so a batch addressing one is refused.

Checked live on 4.7.5 (2026-10-03, ScratchScore): query read bars 1-2 of all
three staves. A dry run of seven ops (Dy, set-pitch 71→70 spelled B♭ with
written C, bracket, flip-stem, nudge, Hidden on a rest, delete) reported
every change and left the score as it was. A set-pitch followed by a tie to
the new note worked in one batch; a tie with no matching next note was
refused and rolled back. The real run was one undo step, and one `undo`
restored all seven, including the deleted chord.

Milestone 3 (bridge version 3) adds the adding ops: add-note (chords,
voices 1-4, spellings, ties), add-rest, add-tuplet, add-text, add-lyric,
add-line (slurs and octave lines), add-clef, and Dorico's note ops
add-dynamic, set-articulation, add-slur, add-tempo and add-rehearsal-mark.
They come after the object ops in a batch, place by staff, bar, position and
voice, and report what they added. How they behave:

- Where nothing in the voice starts at the position, the rest covering it
  is split; a note covering it is never split, and add-note refuses to
  overlap a note unless it starts and ends with it (then the pitches join
  that chord, as Sibelius's add-note does). add-rest replaces anything.
- An empty voice 2-4 can only start where voice 1 has a note or rest
  starting [seen, milestone 0].
- Durations must be one note value with up to three dots, inside the bar:
  the cursor silently turns any other length into a quarter [src].
- Notes without a spelling are spelled by MuseScore for the key, which is
  usually better than the Sibelius default.
- add-lyric works out begin/middle/end from the previous syllable of that
  verse; a melisma (duration longer than the note) runs to the start of the
  last note it covers, which is how MuseScore measures `lyricTicks`.
- add-tempo needs a metronome value (a "q = 96" text or `bpm`): a MuseScore
  tempo mark always sets the playback tempo. add-text on staff 0 makes
  system text, which does not.
- set-articulation does staccato, tenuto, marcato and accent (the actions
  that add them by name); one already there is left as it was.
- **Hairpins are refused.** `add-hairpin` crashed MuseScore again on
  2026-10-03, with two notes selected and the interactive edit cancelled
  straight after, inside a command. That makes two crashes; hairpins are
  added by hand for now.
- A clef that starts a bar is stored at the end of the bar before; the
  read reports it in the bar it starts, at position 0, as Sibelius does.

Checked live on 4.7.5 (2026-10-03, ScratchScore): a dry run of 19 ops (every
adding op, a chord added to, a G♯ spelled, voice 2 in an empty voice, a rest
split from a bar rest, a triplet with a chord, a hyphenated three-syllable
word, a slur over three notes, an 8va over a bar, a tied pair) reported each
added object; the real run read back as asked and was one undo step, and one
`undo` restored bars 3-5 exactly. Refused in the bridge, with nothing
changed: a note inside another note, a note overlapping a longer one, voice 3
where voice 1 had no position, a pitch already in the chord, a lyric with no
note, a tie with no next note, a slur with no later note.

Milestone 4 (bridge version 4) adds `score_structure` (`musescore-cli
structure`) and the structural ops: transpose, copy-passage, set-key,
set-time, set-break, set-barline, set-bar-number, add-bars, set-layout,
hide-empty-staves and delete-voice. Everything is read live through the
plug-in API, so no MusicXML reader was needed. How they behave:

- **transpose** respells each note from its own spelling (C up a minor
  third is E♭, B is D) and writes concert and written spelling; key
  signatures in the range move by the same interval, keeping their mode.
- **set-key** sets every staff, with the written key worked out for
  transposing instruments (kept within seven sharps or flats). MuseScore
  does not add a double barline, unlike Sibelius.
- **Key signatures are replaced, not edited.** Writing `concertKey` on one
  already in the score changed nothing, and setting `keysig_mode` on a new
  one before adding it **crashed MuseScore**: the setter updates the
  staff's key list, and an element not yet in the score has no staff
  (`KeySig::setProperty`, `staff()->setKey`). So the bridge removes the old
  one, adds a new one, and sets the mode afterwards.
- **set-time** re-bars what follows, as on Sibelius; `symbol` gives common
  or cut time.
- **set-break** and **set-barline** work at the end of bar B, as on
  Sibelius; a start repeat starts bar B and an end repeat ends it.
  MuseScore has no between-staves, tick, short or triple barline.
- **set-bar-number** is absolute, as on Sibelius. MuseScore's offset is
  relative, so bars inserted later in the same batch would move the number;
  the bridge numbers bars at the end of the batch, after layout. `skip`
  leaves bar B out of the count and gives the next bar the number.
- **add-bars** appends, or inserts before bar B (one `insert-measure` per
  bar); `length` makes irregular bars.
- **delete-bars** removes bars A-B from every staff and moves the rest up. The
  bridge selects those bars as a range before the command opens (a range
  selected inside one is not filled in; extending a selection with
  `select(el, true)` made no range either), then runs `time-delete` ("Remove
  selected range"), which deletes whole bars [src: `Score::doTimeDelete`].
  One per batch; not the whole score. Needs bridge 10.
- **set-layout** converts millimetres to MuseScore's inches, staff size to
  spatium, and the right margin to a printable width; both odd and even
  pages change. Sibelius page sizes without agreed dimensions (octavo,
  hymn, quarto, folio, us-band) and the extra gap below vocal staves are
  refused.
- **hide-empty-staves** only for the whole score (the style setting);
  MuseScore does not hide staves over a range of bars.
- **delete-voice** turns voice-1 notes into rests and empties voices 2-4.
- **copy-passage** selects and copies the source before the command opens,
  and pastes inside it. It overwrites the clipboard, even in a dry run.
  One per batch.
- transpose and delete-voice change notes as read, so they cannot follow
  adding ops or a set-time/add-bars/delete-bars in the same batch; set-time must come
  before set-bar-number.

Checked live on 4.7.5 (2026-10-03, ScratchScore): every structural op ran
and rolled back in a dry run. A real batch of ten (transpose bars 1-2 up a
minor third, 3/4 at bar 20, D major at bar 3, a system break, a double
barline, a repeat over bars 5-6, bar 8 numbered 20, A4 page with a 6 mm
staff and 20 mm left margin, two bars appended) read back as asked: key
E♭ at bar 1 with the clarinet in F, 40 bars. One undo restored
`score_structure` exactly. A second batch (delete-voice, E minor, bar 5
skipped and the next numbered 10, empty staves hidden, two 3/4 bars
inserted before bar 3) read back as asked, numbering included, and one undo
restored it. copy-passage of bars 2-3 on two staves to bar 10 matched the
source note for note, and undo restored the destination.

Milestone 5 (bridge version 5) adds the file, metadata and lyric tools:
`save_score`, `export_score`, `project_info`, `set_project_info`,
`read_lyrics` and `edit_lyrics`. How they behave:

- **save_score** runs File > Save (`cmd("file-save")`), which saves a score
  that already has a file without asking [src, seen]. The plug-in API has
  no score path, so Python reads the window's `AXDocument` through System
  Events (Accessibility permission) to find the file, waits until its
  modification time changes, and with `path` copies the saved `.mscz`
  there. A score that has never been saved is refused, since MuseScore
  would ask where to save it.
- **export_score** writes the whole score with `writeScore`: pdf, png, svg,
  musicxml (`.musicxml` or `.xml`), mxl, midi (`mid` too; `.mid`), mp3, wav, flac and ogg. With no
  `path` the file lands beside the score, named like it.
  `writeScore` adds its own extension unless the path already ends in it
  (a `.xml` path sent as `musicxml` became `s.xml.musicxml`), so the
  path's suffix is sent as the format. PNG and SVG write one file per page,
  `name-1.png`, `name-2.png`, ..., and a single page as `name.png`.
- **project_info / set_project_info** read and write the metadata tags
  (`workTitle`, `composer`, `lyricist`, ...). MuseScore does not record
  them for undo (rollback and undo both left the new value), so they run
  outside batches and return the old values. The title frame on the first
  page is separate text and does not change.
- **read_lyrics** builds a staff's verse from the read, in score order
  across voices, hyphenated within words. **edit_lyrics** takes text with
  the same number of syllables and changes each syllable's `text` and
  `syllabic` in place, as one batch (one undo step), then reads it back.

Checked live on 4.7.5 (2026-10-03, ScratchScore, 33 bars): every export
format wrote a file without a dialog; png in 1.9 s, the others in under
0.1 s; audio (69 s of music) in 0.7-1.1 s, with an "Exporting audio..."
progress window that closed by itself. The WAV is 32-bit float, 44.1 kHz
stereo, and had sound (peak -17 dB); MP3 128 kb/s, OGG is Opus. With 153
bars (five pages) png and svg wrote five files each (png in 8.8 s). Save
rewrote the file with no dialog, and the copy is a valid `.mscz`. Metadata
round-tripped, and an unknown tag was refused. Seven syllables added with
add-lyric read back as "Ma-king a joy-ful noise now"; edit_lyrics to
"Mak-ing a-joy ful noise now" changed five syllables, hyphens included, as
shown on the page; one undo restored it, and a two-syllable text was
refused.

Milestone 6 (bridge version 6) adds `add_instrument` and
`set_staff_playback` and makes this back end the `musescore` server:

- **add_instrument** appends a part with `appendPart(id)` inside a command,
  so it is one undo step and a dry run rolls it back. `appendPart` quietly
  adds a default instrument for an id it doesn't know [src]; the bridge
  checks the new part's `instrumentId` and rolls back on a mismatch, and
  Python checks the id first against `instruments.tsv` (the 644 ids of
  4.7.5's `instruments.xml`), accepting a MusicXML sound id
  (`strings.violin`) or an unambiguous name and suggesting close ids.
- **set_staff_playback** silences or restores a staff's voices. The staff's
  `playbackVoice1`-`4` flags are writable, but MuseScore 4's audio ignores
  them: only the old MIDI code reads them [src], and a WAV export with
  voice 1 off was as loud as before (peak -17 dB) [seen]. Audio does honour
  each note's `play` flag (`NoteRenderer` skips notes that don't play
  [src]), so the bridge sets both: the export with the clarinet silenced
  this way peaked at -91 dB, and undo brought it back [seen]. Notes added
  later still play.

## Live check

`scripts/dev/musescore_live_check.py` runs a fixed scenario on the open score
(it refuses scores whose name lacks "Scratch" unless `--force`): a marker
text, then a dry run of a batch with every kind of adding and structural op
(the score must read back identical), the same batch for real (one undo
must restore it), lyrics read/edit/undo, every export format, metadata,
add_instrument (dry and real) and staff playback, each undone, with the
marker surviving every undo; finally the marker is undone and the score
must read back exactly as it started. "Identical" compares every object
`query_score` reports, `score_structure` and the staves.

Run on 2026-10-04, MuseScore 4.7.5, ScratchScore (33 bars, three staves):
28/28 passed. The batch had 14 ops (15 primitives: chords, a tie, a rest, a
triplet with a rest and a chord, a C♭, expression text, a lyric, an 8va,
an alto clef, E♭ major, a system break, a double barline, bar 100). Exports:
png 1.8 s, audio 0.7-1.1 s, the rest under 0.1 s.

Starting two plug-ins that listen (the bridge and the probe) does not give
two servers: MuseScore has one WebSocket server, the second `listen` only
logs "QTcpServer::listen() called when already listening", and the second
plug-in's handler answers on the first one's port. Start only the bridge.

## Probe results (MuseScore Studio 4.7.5, macOS)

Milestone 0 of [musescore-backend-plan.md](musescore-backend-plan.md).
Probes ran through `scripts/dev/musescore_probe.py` and its plug-in on a
throwaway score (Clarinet in B♭ and Piano). The plug-in requires a token,
because MuseScore's WebSocket server listens on every interface (checked:
`*:8767`; requests with a wrong or missing token were refused). Each edit
probe ran in its own `startCmd` and was rolled back unless noted.

### Plug-in loading (P1, partly), 2026-10-03

- A plug-in function named `run` clashes with the plug-in's `run` signal:
  MuseScore logs "Duplicate method name" and then fails the whole file
  with "Cannot assign to non-existent property onRun".
- **A changed plug-in file is not reloaded until MuseScore restarts.**
  After fixing the file, running the plug-in again failed with the old
  file's error and line number. Every bridge update needs a restart.
- MuseScore reads `title:` and the other properties as text and stops at
  the first line ending in `{`, so they must stay above every block.
- **Replying to a client that has disconnected hits an assertion**
  (`WebSocketServerApi::send ... it != m_clients.end()`), and MuseScore
  crashed right after it (crash dump written). The bridge has to keep track
  of disconnects and not send to a closed client.

### Reading (P8), 2026-10-03

- `generated` is true for system-start header clefs and for ordinary
  barlines (begin and end). The opening key and time signatures in bar 1
  are real elements (`generated` false), unlike Sibelius, where they are
  not bar objects.
- Parts report `longName`, `instrumentId`, `startTrack`, `endTrack` and
  their staves; tracks are 4 per staff.

### Undo and rollback (P2, P3, P15), 2026-10-03

- Two edits between `startCmd()` and `endCmd()` are **one** undo step.
- `endCmd(true)` restores the score at once (the same request reads the old
  values), and leaves no undo step behind: the next undo reverted the edit
  before it.
- **`cmd("undo")` does nothing in 4.7.** `cmd()` translates only a few old
  names (`copy`, `paste`, `delete`, ...); the undo action is
  `action://notation/undo` (and `action://notation/redo`). With that name,
  undo takes effect before `cmd()` returns. The upstream plug-in's `undo`
  tool sends `cmd("undo")`, so it never worked.
- Undo is only dispatched when something can be undone (`canUndo`), so an
  empty history cannot open a dialog [src].
- **`cmd()` joins the batch.** In one `startCmd`: a pitch change through
  the API, then selecting the previous note and `cmd("tie")`. The tie
  existed before `cmd()` returned, one undo reverted both, and
  `endCmd(true)` rolled both back. (The undo-stack lock that makes this
  work arrived in 4.6.0: it is absent from `score.cpp` at v4.5.2.)

### Properties and spelling (P5, P6), 2026-10-03

- Writable, and rolled back: `offsetX`/`offsetY` (staff spaces), `visible`,
  `small`, `stemDirection` (0 auto, 1 up, 2 down).
- `hasParentheses` takes 0 or 3 (both sides); `true` (1, left only) logs
  "Notes cannot set left & right parens individually". `cmd("add-parentheses")`
  on a selected note sets 3.
- `beamMode` always read 0 and did not change when set to 2, 3 or "BEGIN",
  nor after `cmd("beam-break-left")`; not yet known whether the write or the
  read fails.
- **Setting `pitch` keeps the old spelling** (pitch 74 with tpc1 still C),
  so set-pitch must write `pitch`, `tpc1` and `tpc2` together. On the
  clarinet `tpc1` was 14 (C, concert) and `tpc2` 16 (D, written); `tpc`
  writes the spelling of the current concert/transposed view only.
  `curScore.staves[0].transpose(fraction(0, 1))` gave chromatic -2,
  diatonic -1.
- `selection.select()` refuses a Chord ("Cannot select element of type
  Chord"); select a note.

### Adding notes (P4), 2026-10-03

- Cursor at track 0, `rewindToTick`, `setDuration(1, 8)`, `addNote` three
  times wrote three eighths and filled the bar with rests.
- `addNote(p, true)` after rewinding adds to the chord.
- **Adding where a note is replaces it** (bar 1 beat 1: 72 became 60).
- `addTuplet(fraction(3, 2), fraction(1, 4))`, then rewinding and adding
  eighths, wrote three 160-tick tuplet notes and carried on after it.
- **Voice 2 needs a position from voice 1.** `rewindToTick` on track 1 in a
  bar with no voice-2 content leaves no position ("cursor location is
  undefined") and `addNote` adds nothing. Rewinding on track 0 and then
  setting `track = 1` without rewinding works; this only reaches ticks
  where voice 1 has a chord or rest.
- In one request, `addNote` failed after earlier rolled-back probes in the
  same request ("cursor location is undefined"), where the same steps
  worked as the first probe. Not yet explained.

### writeScore (P16, partly), 2026-10-03

- **`writeScore` cannot write `.mscz` or `.mscx` in 4.7.5.** It exports
  through the File → Export path, choosing per-page, per-part or
  multi-part output by what the writer supports. The `.msc*` writer only
  supports multi-part, and its multi-part function returns "Not supported"
  (`MscNotationWriter::writeList`). The export then shows a Retry/Abort
  dialog, which blocks the plug-in; every Retry failed again. After Abort,
  MuseScore crashed (see above). An empty file was left at the path.
- So the plan's `.mscx` structure read and `.mscz` backups need another
  route. Any failed export opens that dialog, so the bridge must only
  request formats known to work.

### Exports and lines (P16, P7), 2026-10-03

- `writeScore` picks an export mode from what the format's writer supports
  [src]: per page for PNG and SVG; per part for PDF, MusicXML (`musicxml`,
  `xml`, `mxl`), MIDI, MEI, MNX and the audio formats. With one score each of
  these writes one file (PNG and SVG one per page). Only `.mscz` and `.mscx`
  fail (above).
- `writeScore(curScore, path, "musicxml")` wrote the whole score (both
  parts, 32 bars each) in 4 ms and left `scoreName` unchanged. MusicXML is
  the route for structure the plug-in API does not show.
- **A slur:** select a note, `cmd("add-slur")`: it slurs to the next chord.
  `curScore.spanners` reads it back (type, track, `spannerTick`,
  `spannerTicks`, start and end chords), and rollback removes it.
- **Never add a spanner with `Cursor.add`.** `newElement(Element.HAIRPIN)`
  and `Cursor.add` fall through to adding it to a segment, which does not
  hold spanners: MuseScore logged "Segment::add() unknown HairPin" (and
  "Segment::remove() unknown HairPin" on rollback). The hairpin read back
  with `spannerTick` -1 and no end element. In a later request, the same
  step followed by `cmd("add-hairpin")` on a selected note crashed
  MuseScore (crash dump written), most likely because of the bad hairpin.
- `cmd("add-hairpin")` with a range selection did nothing ("no one can
  handle the action: add-hairpin"): it needs a note or rest selected
  [src], and a range selected inside a batch is not filled in yet (see
  Selections below). With a single note selected, adding one hairpin
  also starts dragging its end handle (`startEditGrip`) [src], an
  interactive edit that a rollback would cut from under; that may be what
  crashed. Hairpins and other lines stay open.

### Selections, copy and paste (P11), 2026-10-03

- **Make range selections outside a batch.** Inside an open command,
  `selection.selectRange` only records the ticks and fills in the selection
  when the command ends (`setRangeTicks`) [src].
- `selectRange(0, 1920, 0, 1)` inside a batch followed by `cmd("copy")`
  crashed MuseScore (crash dump written), most likely because the copy
  serialised that unfilled selection. The clipboard was unchanged
  (fingerprint compared before and after). copy-passage would select and
  copy before `startCmd`, since copying changes nothing, and paste inside
  the batch; not yet tried.

### More editing (P9, P10, P12, P13, P14, P17), 2026-10-03

All rolled back cleanly unless noted.

- **Lyrics:** `newElement(Element.LYRICS)` + `Cursor.add` attaches to the
  chord at the cursor. `text`, `syllabic` (0 single, 1 begin, 2 end,
  3 middle [src]), `verse` (0-based) and `lyricTicks` (melisma length,
  480 = a quarter) read and write.
- **Key signatures:** the property is `actualKey`, not `key`. Adding one
  with `Cursor.add` on each staff's track 0 works, but MuseScore does not
  derive the written key: concert D (`concertKey` 2) on the B♭ clarinet
  came out `actualKey` 2. Setting `concertKey` 2 and `actualKey` 4 before
  adding gave concert D, written E. `Staff.key(tick)` returns the written
  key (2 for the clarinet in concert C).
- **Barlines and repeats:** `repeatStart`/`repeatEnd` are writable;
  `barlineType` 2 (double) set on staff 0's end barline changed all three
  staves (barlines span the system).
- **Bar numbers:** `noOffset` and `irregular` are writable, but `no` (the
  displayed number) of later bars did not change inside the batch: layout
  runs when the command ends. A dry run's "after" view needs
  `curScore.doLayout` for derived values; not yet tried.
- **Layout breaks:** with a note selected, `cmd("system-break")` and
  `cmd("page-break")` add a break, and the same command again removes it
  (they toggle). `measure.elements` lists it as `LayoutBreak` with
  `layoutBreakType` 1 (system) or 0 (page). This is a plain edit, with no
  interactive mode [src].
- **Bars:** `appendMeasures(3)` added three bars; with a note selected,
  `cmd("insert-measure")` inserted an empty bar before it and moved the
  music on; `timesigActual = fraction(3, 4)` made bar 5 1440 ticks long and
  refilled its rests. `insert-measures` (several) takes a count from its
  dialog [src], so it was not tried.
- **Time signatures:** `newElement(Element.TIMESIG)`, `timesig =
  fraction(3, 4)`, `Cursor.add` at bar 3 re-barred everything after it
  (32 bars became 42).
- **Deleting:** `removeElement` on a chord leaves a rest, on one note of a
  chord removes that note, on a chord's only note leaves a rest.
- **Text and marks:** `newElement` + `Cursor.add` works for STAFF_TEXT,
  SYSTEM_TEXT, TEMPO_TEXT (`tempo` in beats per second,
  `tempoFollowText`), DYNAMIC, REHEARSAL_MARK and ARTICULATION (attached
  to the chord; which symbol it shows is not yet known). They read back as
  segment `annotations` with `text`.
- **Style:** `curScore.style.value`/`setValue` work and are undoable and
  rolled back. Page sizes and margins are in inches (Letter: 8.5 × 11);
  `spatium` is in 1/1200 inch (82.68 = 1.75 mm); `staffDistance`,
  `akkoladeDistance` and the system distances are in staff spaces. An
  unknown key returns null and logs a warning, with no dialog.
- **Metadata:** `metaTag` reads workTitle, composer, lyricist and so on.
  `setMetaTag` is **not** undone by rollback (it kept "PROBE"), as the
  source shows, so it was put back by hand.

### Beams, articulations, layout, parts, size (P5, P18, P19), 2026-10-03

- **Beams:** `beamMode` is writable after all: BeamMode is AUTO 0, NONE 1,
  BEGIN 2, BEGIN16 3, BEGIN32 4, ... [src]. Setting 2 on the third of four
  eighths split them into two beamed pairs, checked in a MusicXML export.
  The earlier tries set 3 (BEGIN16), which does nothing to eighths, or
  beamed quarters.
- **Articulations:** `symbol` takes MuseScore's numeric symbol id, not a
  name: 623 is `articStaccatoAbove` in 4.7.5 (ids come from `symid.h` and
  can change between versions). With a note selected, the actions
  `add-staccato`, `add-tenuto`, `add-marcato` and `add-sforzato` (an
  accent) add the same thing; they toggle. With nothing
  selected they start note input instead [src], so always select first.
- **Layout mid-batch:** `curScore.doLayout(fraction(0, 1), fraction(-1, 1))`
  (since 4.6) updated bar 3's displayed number from 2 to 11 after a
  `noOffset` change, inside the batch; rollback restored it.
- **MusicXML exports written pitch** for transposing instruments (the
  clarinet's concert C4 came out as D4), so a MusicXML read converts back
  with the part's `<transpose>`.
- **Parts:** `appendPart("flute")` added a Flute part (4 staves) and was
  rolled back. `Staff.playbackVoice1` (to 4) is writable and rolled back;
  whether it silences playback was not listened to.
- **Size:** inside a rolled-back batch, 300 bars filled with eighths on all
  three staves (7,200 notes) took 41 ms to write; reading every non-generated
  element with pitches and spellings took 38 ms; the request took 0.17 s.
  Reads do not need to be split into chunks. (Layout runs at the end of a
  command, so these times exclude it.)
- `root.scores`, the list of open scores, read as empty with a score open.

### Windows and closing (P1), 2026-10-03

- **Each score window is its own MuseScore process.** With ScratchScore
  open, File → New opened the second score in a new process
  (`mscore --session-type start-with-new`). The plug-in, started in the
  first window, kept seeing ScratchScore (`curScore`, `api.engraving.curScore`
  and a new cursor's score), and `writeScore` exported ScratchScore. Only
  one process can listen on the port, so the bridge serves the score of the
  window it was started in; to switch scores, start it in the other window.
- `curScore` looks up the window's current score on every access, and is
  null with no score [src].
- With a second window open, closing ScratchScore ended its whole process
  normally ("Goodbye!! code: 0"), and the plug-in with it; the client got
  "connection refused". Closing the last score of the only window (start
  screen left open) was not tried.
- `root.scores` is not implemented in 4.7.5 (`NOT_IMPLEMENTED`) [src].

### Starting the plug-in and opening scores by script (P1), 2026-10-03

- **MuseScore's menus are native macOS menus.** With Accessibility
  permission for the terminal, System Events listed the menu bar of the
  `mscore` process (Apple, MuseScore Studio, File, Edit, View, Add, Format,
  Tools, Plugins, Help) and the Plugins menu (Manage plugins…, ScoreBridge
  probe, musescore-mcp-websocket). Each window's process can be targeted
  by its unix id.
- **Clicking Plugins → ScoreBridge probe by AppleScript started the plug-in**
  on the start screen, with no score open: it answered, with `curScore`
  null. So a launcher can start the bridge in a given window without the
  user, once Accessibility is granted.
- **`readScore(path)` from the start screen opened the score in the same
  process**: no new window, the plug-in kept running and saw the score
  (3 staves) from the next request. (The probe passes `curScore` to each
  snippet as it was at the start of the request, so the opening request
  itself still saw null.)
- With a score already open, MuseScore 4 opens another in a new process
  (above), where the plug-in isn't running. `closeScore()` exists, but
  closing a score with unsaved changes asks whether to save, a dialog that
  blocks the plug-in, and the API can't tell whether there are unsaved
  changes. Not tried.

## The upstream server (history)

Until milestone 6 the `musescore` MCP server was [ghchen99/mcp-musescore](https://github.com/ghchen99/mcp-musescore),
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
Its tool notes are kept in the musescore skill's
[references/upstream-tools.md](../.claude/skills/musescore/references/upstream-tools.md).

### How it differs

| | `sibelius-mcp` | `mcp-musescore` |
|---|---|---|
| Model | Address objects (staff, bar, index) and send batches | Move a cursor and type at it |
| Edits | `apply_batch`: every operation checked first, one undo step, backup before a real run | One undo step per call; `processSequence` runs steps one by one with no checks or rollback |
| Dry run and guards | `dry_run`, plus type/position guards on each address | None |
| Errors | Batch refused, nothing changed | `processSequence` ignores failing steps and reports success |
| Reads | Filtered queries, structure, overview | `get_score`: the whole score every time, notes, rests and lyrics only |
| Units | 1/256 quarter, 1-based bars and staves | 480 ticks per quarter, 0-based measures and staves |
| Connection | Sibelius Connect, approval dialog | Unauthenticated WebSocket on port 8765 of every network interface (MuseScore listens on `QHostAddress::Any`), so any device on the network can use it |

### Its parity with the Sibelius back end

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

### What parity needed (the plan's starting point)

[musescore-backend-plan.md](musescore-backend-plan.md) turns this outline
into a phased plan with probes and milestones.

Patching the upstream tools one by one would not get there. The gap is the
model: Sibelius parity needs addresses, guards, checked batches and filtered
reads. Most of the missing operations are things MuseScore's plug-in API can
already do. The upstream plug-in just doesn't expose them.

The most direct route is a MuseScore back end in this repository, built the
way `dorico/` was: a `musescore-mcp` with the same seven tools, reusing
`core.batch_schema` validation, `core.query` selectors and the result shapes. It would talk
to a QML bridge plug-in that this repository owns and installs, using the
upstream plug-in's WebSocket setup as the starting point. Parts the MuseScore
API seems to support, to confirm on MuseScore 4.7:

1. **Bridge.** A QML plug-in with one entry point per call, shaped like
   `ScoreBridge`: `GetScoreInfo`, `GetStaves`, `Query`, `ApplyBatch`, `Save`,
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
