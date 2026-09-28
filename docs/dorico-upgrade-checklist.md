# Dorico upgrade checklist

Everything in the Dorico back end rests on undocumented behaviour: Lua
bindings, command names and parameters logged in `application.log`, the
text of `EventStream:dump()`, and the accessibility of a few Qt dialogs
(`docs/dorico.md`). Any Dorico update can change any of it. Run this after
installing a new Dorico, before relying on the back end again.

Work through the parts in order; each ends with the undo that restores the
score. Record failures, then fix, re-baseline and update `docs/dorico.md`
(part 7).

## 0. Before upgrading (optional but useful)

- Note the old version: `dorico-cli overview` → `dorico`.
- Keep the old baselines (`docs/dorico-baseline/*-<old>.txt`); the check
  diffs against them.

## 1. Automatic read-only check

Open any project in Dorico, then:

```bash
uv run python scripts/dorico_upgrade_check.py --baseline 6.2.30
```

It changes nothing. It reports the Dorico, Qt and Lua versions and checks:
the Remote Control connection and saved token; the Lua bridge
(`Script.RunScript`, `DoApp.currentLayoutID`, raw layout, reads, the `dump()`
fallback when the project has lyrics); every command the back end sends is
still listed (`getcommands`); the Lua classes the bridge constructs exist;
`application.log` still records commands; System Events can see Dorico.
Removed or added commands and classes are listed against the baseline.

- **FAIL** lines must be fixed before going further. A renamed command
  means finding its new name the usual way (use the feature in the UI, read
  `application.log`).
- **WARN** lines are differences to read: a removed command that the back
  end does not use is harmless; an added one may be a new capability.

If the approval prompt appears, the token was invalidated: accept it once.

## 2. Open the fixture

Open `tests/fixtures/dorico-upgrade-fixture.musicxml` in Dorico
(File › Open, or `open -a "Dorico 6" <path>`; it imports without a dialog)
and keep it as the active project. Give Dorico a few seconds after the
import before the first read.
It is a two-staff piano, 4/4, C major, four bars:

| Staff | Bar 1 | Bar 2 | Bar 3 | Bar 4 |
|---|---|---|---|---|
| 1 (treble), lyrics | C5 D5 E5 F5 "one two three four" | G5 A5 "five six" | C5 "sev" + voice 2 E4 D4 | rest |
| 2 (bass), no lyrics | C3 | G2 B2 | C3 | rest |

Staff 1 has lyrics, so it is read from `dump()`; staff 2 is read by Lua;
bar 3's second voice forces voice placement by probe. Each bar-1 clef is
index 0 of its bar, so the batches below address staff 2's bar-1 C3 as
index 1 and staff 1's C5 as index 2.

## 3. Reads

Run each and compare with the expected result.

| Command | Expected |
|---|---|
| `dorico-cli overview` | 2 staves named Piano; staff 1 voices = voice 1 and the bar-3 voice, staff 2 one voice; **no** `readFromMusicXML`; no `unplacedVoiceStreams` |
| `dorico-cli structure` | bar length 1024 from bar 1; lastBarWithMusic 3 |
| `dorico-cli query --staff 1 --bars 1` | 4 NoteEvents C5 D5 E5 F5 with ids and `"source": "dump"`, plus LyricEvents |
| `dorico-cli query --staff 1 --bars 1-2 --lyrics` | the same notes carry "one" … "six" |
| `dorico-cli query --staff 2` | C3, G2, B2, C3 with ids, no `source` |
| `dorico-cli lyrics Piano` | "one two three four five six sev" |
| `dorico-cli info` | Title "Dorico Upgrade Fixture" (or as imported) |

If `overview` reports `readFromMusicXML`, probing or bar measurement failed.
Run it once more: the first read straight after the import fell back once
and then read normally. If it persists, `dorico-cli structure` shows whether
bars still measure; if they do, the voice probe is failing (call
`service.probe_placements` directly to see its error) — see `docs/dorico.md`
(voice placement, bar measurement).

## 4. Writes, one batch at a time

For each batch: `dorico-cli apply --json '<batch>' --dry-run`, then apply,
check the result, look at the render when noted (`dorico-cli export
/tmp/x.png --format preview-png`), then `dorico-cli undo --steps <undoSteps>`
(Lua batches: `--steps 1`) and confirm with a query that the fixture is
back. **Never undo more than the result reports.**

Reads (`query`, `overview`, `structure`) must leave the undo history as it
was, so the reported count stays right however many reads come between the
batch and the undo. This is itself under test: if an undo of the reported
steps leaves the batch in place, stop, undo one step at a time checking
each with a read until the fixture is back, and treat it as a failure
(before #60, each read on this fixture added one selection per voice).

### 4a. Lua ops (staff 2)

```json
[{"op":"set-pitch","staff":2,"bar":1,"index":1,"oldPitch":48,"newPitch":50},
 {"op":"add-note","staff":2,"bar":4,"position":0,"duration":512,"pitches":[43,47]},
 {"op":"add-text","staff":2,"bar":4,"position":0,"text":"dolce"},
 {"op":"add-clef","staff":2,"bar":4,"position":0,"clef":"treble"},
 {"op":"delete","staff":2,"bar":3,"index":0}]
```

Expect 5 applied; query shows D3 in bar 1, the chord and text in bar 4, a
clef event, no C3 in bar 3. Undo 1 step.

```json
[{"op":"transpose","fromBar":2,"toBar":2,"topStaff":2,"bottomStaff":2,"fromNote":"C","toNote":"D","direction":"up"}]
```

Expect G2→A2, B2→C#3. Undo 1.

### 4b. Signatures, barlines, breaks (command ops)

```json
[{"op":"set-key","bar":3,"key":"G"},{"op":"set-time","bar":3,"numerator":3,"denominator":4},
 {"op":"set-barline","bar":3,"type":"double"}]
```

Expect three results with ids, `undoSteps` 6; render shows ||, G major and
3/4 at bar 3. Undo the reported steps. Then `[{"op":"set-break","bar":3,"type":"system"}]`
(render: a system starts at bar 3), undo.

Empty bar: `[{"op":"set-time","bar":4,"numerator":3,"denominator":4}]` (bar 4
holds implicit rests only). Expect `undoSteps` 4, a render with 3/4 at bar 4
and only bar rests after it, and `query --bars 4` on both staves showing no
leftover rest. Undo the reported steps. Then `[{"op":"set-break","bar":4,"type":"system"}]`:
`undoSteps` 4, a system starting at bar 4, no leftover rest; undo.

Bar 1: `[{"op":"set-time","bar":1,"numerator":3,"denominator":4},{"op":"set-key","bar":1,"key":"G"}]`.
Expect `undoSteps` 4, `structure` measuring bar 1 as 768, and a render
opening in 3/4, G major with the music re-barred. Run `dorico-cli lyrics
Piano` before undoing the reported steps: reads, `lyrics` included, must
leave the undo history alone, so the undo still reverts the batch exactly.

### 4c. Notation ops (command ops)

```json
[{"op":"add-dynamic","staff":2,"bar":2,"index":0,"dynamic":"p"},
 {"op":"set-articulation","staff":2,"bar":2,"index":0,"articulation":"staccato"},
 {"op":"add-slur","staff":2,"bar":2,"index":0},
 {"op":"add-tempo","staff":2,"bar":2,"index":1,"text":"Allegro, ma non troppo"},
 {"op":"add-rehearsal-mark","staff":2,"bar":2,"index":0}]
```

Expect `undoSteps` 10 and ids for dynamic, tempo and rehearsal mark;
articulations `["staccato"]`; slur `verified: false`. Render: p, staccato,
slur G2→B2, the tempo text with its comma, a boxed A. Undo the reported
steps; the timebase must be readable again (`query --staff system`).

### 4d. Edits on the lyric staff (command ops)

```json
[{"op":"set-pitch","staff":1,"bar":1,"index":2,"oldPitch":72,"newPitch":73,"spelling":"Db"},
 {"op":"delete","staff":1,"bar":1,"index":8}]
```

(`index` counts the clef and lyric events too: clef 0, then a lyric and
its note for each beat, so C5 is 2 and F5 is 8; check with `query --staff 1
--bars 1`.) Expect the note to keep its id and read Db5, the F5 gone, and
`dorico-cli lyrics Piano` unchanged. Undo the reported steps.

### 4e. copy-passage and add-lyrics

```json
[{"op":"copy-passage","fromBar":2,"toBar":2,"topStaff":2,"bottomStaff":2,"destStaff":2,"destBar":4}]
```

Expect `verified: true` and bar 4 = G2 B2. Undo the reported steps.

```json
[{"op":"add-lyrics","staff":2,"bar":1,"index":1,"text":"la, la-la"}]
```

Expect `lyricsCheck.ok` (the comma survives). Undo the reported steps; staff
2 must read without `source: "dump"` again.

```json
[{"op":"add-lyrics","staff":1,"bar":1,"index":2,"verse":2,"text":"u-no dos"}]
```

Expect `undoSteps` 5, `lyricsCheck.ok` with `keptFound` `["one"]`, and
`query --staff 1 --bars 1 --lyrics` showing verse 1 "one two three four"
unchanged and verse 2 "u-no dos" on C5 D5 E5. Undo the reported steps and
check the lyrics again: the Lua read cannot tell a verse-2 lyric from a
verse-1 one. The same batch again with `"verse":1` must be refused
("already has a verse 1 lyric").

## 5. Dialog and export automation

These depend on dialog titles, control names and log lines.

| Step | Expected |
|---|---|
| `dorico-cli export /tmp/f.pdf --format pdf` | every page; no dialog left open. Run twice: the second answers the "output files already exist" prompt |
| `dorico-cli export /tmp/f.musicxml --format musicxml` | the Export MusicXML window opens and closes by itself; the file parses |
| `dorico-cli export /tmp/f.png --format preview-png` | a PNG of page 1 |
| `dorico-cli edit-lyrics Piano "<same text with one word changed>"` | `after` shows the change and `undoSteps` 3; `undo --steps 3` restores the text (check with `lyrics`, whose result must carry no `note` about undo steps) |
| `dorico-cli set-info Composer=Test` then `set-info Composer=` | read back each time; title page shows the composer |

After each, check no Dorico dialog is left open.

The PDF export also leaves Dorico's own copy next to the file the project
came from, which for the imported fixture is
`tests/fixtures/01 - Full score - Dorico Upgrade Fixture.pdf`: delete it
(`git status` should be clean afterwards).

## 6. Re-test the known limits

An update may lift a limit. Try each once and update `docs/dorico.md` if it
now works:

- Lua `events` on a stream with lyrics or tempo marks (currently "Not
  implemented": the `dump()` fallback would become unnecessary).
- `kBarDivisionTimeSignatures` / tonality elements readable from Lua.
- `EventEdit.EditExistingTimeSignature` / `…KeySignature` (bar 1 changes).
- Lua `createSystemBreak` honoured by the layout.
- `kNoteSpelling` writes; `kEventDuration` read-back after a write.
- `ScriptHost:convertFolderOfScores` (currently "Not implemented").
- Slurs visible to Lua; `copyRange` copying anything.
- The jump bar logging a command; the Project Info flow list accessible.

## 7. Afterwards

- Save new baselines: `uv run python scripts/dorico_upgrade_check.py
  --write-baseline` writes `docs/dorico-baseline/commands-<version>.txt` and
  `lua-classes-<version>.txt`; use `--baseline <version>` from then on.
- Record the Dorico version, what changed and what was fixed in
  `docs/dorico.md`.
- Run `uv run pytest`.
