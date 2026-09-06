# Bridge v2 design

Goal: let an LLM-driven client describe score changes in natural language and
apply them safely — e.g. "fix lyric spelling errors" or "transpose into
D major" — over Sibelius Connect. All ManuScript API references below are
verified against `docs/manuscript-object-tree.md`.

Because every plug-in change requires a Sibelius restart to load, v2 is
designed as one complete API and shipped once.

## Principles

1. **Read → write → verify.** Every mutation is bracketed: the client reads
   the affected region first, writes via a bridge method (never a bare
   command ID, which gives no feedback), then reads back to confirm.
2. **Backup before mutate.** The CLI refuses to run a write method unless a
   backup exists from the last N minutes (configurable), and can create one
   automatically: an in-file version (`VersionHistory.AddVersion`) plus a
   filesystem copy made by the CLI (`cp` of `FileName` — the CLI, not the
   plug-in, owns filesystem copies to avoid SaveAs re-association risk).
3. **Structured results.** Every method returns a dictionary; failures return
   `{'error': <message>}` and the CLI exits 1. Writes return what changed so
   the transcript is self-documenting.
4. **Stable addressing.** Objects are addressed as
   `(staffNum, barNumber, index)` where `index` is the object's position in
   `ReadBars` output for that bar. Reads emit these coordinates; writes accept
   them. Indexes are only valid against the read they came from — the CLI
   verify step re-reads to detect drift.

## API

### Meta

- `GetBridgeVersion()` → `{version: 2}` — CLI checks compatibility and tells
  the user to reinstall + restart when stale (removes a whole class of
  confusing failures seen during v1 development).

### Reads

- `GetScoreInfo()` — v1 fields plus `keySignatures` (per-bar changes via
  `KeySignature.Sharps`/`AsText`), `timeSignatures`, `transposingScore`.
- `GetStaves()` — as v1.
- `GetSelectionInfo()` — as v1.
- `ReadBars(staffNum, fromBar, toBar)` — v1 plus, per object: `index` (its
  address), `voice`, and for LyricItem: `text`, `syllableType`
  (`LyricItem.Text`, `.SyllableType`), for Clef/KeySignature/TimeSignature:
  their textual value.
- `ReadLyrics(staffNum)` — flat ordered list:
  `[{staff, bar, index, position, text, syllableType}]` across the staff
  (0 = all staves). This is the spell-check input: the client joins syllables
  (MiddleOfWord vs EndOfWord) into words, checks them, and maps corrections
  back to addresses.

### Writes

- `SetLyricText(staffNum, barNumber, index, newText)` — asserts the object at
  that address is a LyricItem, sets `Text`, returns old and new text.
- `TransposePassage(fromBar, toBar, topStaff, bottomStaff, fromPitch, toPitch, upward)`
  — `Selection.SelectPassage(...)` then
  `Selection.Transpose(0-based degree, interval, True, True)` with the
  interval computed by `Utils.CalculateInterval(fromPitch, toPitch, upward)`;
  `transpose keys = True` moves key signatures too. Whole-score transposition
  is this with full bounds. Returns the interval applied.
- `SetKeySignature(barNumber, keyName, major)` —
  `Bar.AddKeySignatureFromText(0, keyName, major)` on the system staff, for
  cases where a key change is wanted without transposing.
- `SetTimeSignature(barNumber, top, bottom)` — `Bar.AddTimeSignature(...)`,
  which returns an error string — surfaced verbatim.
- `AddNotes(staffNum, barNumber, position, duration, pitches, voice)` —
  `Bar.AddNote` for the first pitch, `NoteRest.AddNote` for the rest (chord).
- `AddLyric(staffNum, barNumber, position, duration, text, syllableType)` —
  `Bar.AddLyric(...)`.
- `DeleteObject(staffNum, barNumber, index)` — deletes the object at an
  address (`BarObject.Delete()`); returns what was deleted.

### Safety

- `AddVersion(name, comment)` — `score.GetVersions().AddVersion(...)`;
  in-file snapshot, survives with the .sib.
- `Save()` — `score.Save(score.FileName)` for an already-saved score; errors
  if the score has never been saved (no dialogs from the bridge, ever).

## CLI layer

- `backup` subcommand: `AddVersion` + `Save` + filesystem copy of `FileName`
  to `<name>.backup-<timestamp>.sib` next to the original.
- Write subcommands (`set-lyric`, `transpose`, `set-key`, …) run the
  backup-freshness check first (`--no-backup` to override), call the bridge,
  then re-read the affected bars and print a before/after summary.
- `transpose --to <key>` computes `fromPitch`/`toPitch` from
  `GetScoreInfo().keySignatures` tonic → target tonic, choosing the smaller
  direction unless `--up`/`--down` is given.

## Example flows

**"Fix lyric spelling errors":** `ReadLyrics(0)` → client assembles words and
finds errors → `backup` → `SetLyricText` per fix → `ReadLyrics` verify.

**"Transpose into D major":** `GetScoreInfo` (current key, bounds) → `backup`
→ `TransposePassage(1, barCount, 1, staffCount, <tonic>, 62, <direction>)` →
`GetScoreInfo` + spot `ReadBars` verify.

## Risks / open items

- `Selection.Transpose` degree is 0-based and paired with the interval type
  from `CalculateInterval`; needs one live calibration test (e.g. C→D on a
  scratch score) before trusting on real scores.
- LyricItem word assembly across barlines relies on `SyllableType` being set
  correctly in the score.
- Multi-voice addressing: `index` covers it, but verify `for each` object
  ordering is stable across reads (it is documented as chronological).
- `Save()` on a score with unsaved dialog state (e.g. never saved) must fail
  cleanly, not hang — bridge checks `FileName` first.
