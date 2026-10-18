# Command Reference

Use `uv run sibelius-cli <command> --help` for the complete current
argument list. Run commands from the repository root.

Batch commands are listed first in each section. Reach for single-object
commands only when exactly one change is needed or no batch form exists.

## Reads

Batch reads (one session, compact output):

- `inspect`: compact score identity, staff names, and current selection. The
  default initial safety check; replaces `score-info` + `staves` + `selection`.
- `score-snapshot [--bars A-B] [--staff N] [--lyrics] [--no-barlines]`:
  identity, staves, selection, key/time signatures, and special barlines in
  one call; lyrics are opt-in. Use instead of several structural reads.
- `proofread [--bars A-B] [--staff N] [--lyrics] [--no-barlines]`: read-only
  structural and lyric lint report with compact issue records. Use as the
  first pass for any review instead of `check-lyrics` plus per-staff reads.
- `query [--staff N|NAME]... [--bars A-B] [--type T,...] [--voice V]
  [--where 'Prop OP value']... [--field P,...] [--limit N]`: find bar objects
  anywhere in the score in one call, filtered inside Sibelius. Each result
  carries its `staff`/`bar`/`index` edit address. Types include `NoteRest`,
  `LyricItem`, `Text`, `Clef`, `Tuplet`, `Line` (any line kind) or a specific
  line type such as `Slur`. `--where` filters combine with AND; `Pitch`
  and `Bracketed` match if any note of a chord matches (each note in the
  results also lists its `bracketed` state), and `StemFlipped=true` finds
  flipped stems. Properties are allow-listed per
  object type (an unknown name is rejected with the full list); objects lacking a
  filtered property never match. Use instead of reading bar ranges to hunt
  for objects, e.g. `query --staff Tenor --where 'Pitch>=67'` or
  `query --type Text --field Dx,Dy`. Output is capped at 500 objects; a
  `truncated: true` result means narrow the query. `--staff 0` (or
  `--staff system`) reads the system staff: tempo, metronome and other system
  text, and system lines such as rit./rall. (bridge v48). It is only read
  when asked for.
- `verify-render [--format png|pdf] [--out PATH]`: export once and verify that
  rendered files exist, are non-empty, and optionally match page/hash checks.

Targeted reads (always scope with `--staff` and `--bars`):

- `read [--staff N] [--bars A-B] [--abc]`: addressed notes, pitches, ties, and
  lyrics. `--abc` (or `read-abc`) is far smaller than JSON; prefer it unless
  you need addresses.
- `read-lyrics [--staff N] [--bars A-B] [--words|--compact] [--verse N]`:
  `--words` for review, `--compact` when you need edit addresses. Verse `0`
  means all verses.
- `check-lyrics [--staff N] [--bars A-B] [--verse N]`: lyric collision,
  missing-vowel, divergence, and untexted checks; `proofread --lyrics` usually
  covers this.
- `score-info`, `staves`, `selection`: individual pieces of `inspect`.

## Writes

Write commands create a backup before mutation. Batch writes back up, apply,
and verify once for the whole set.

- `apply --file PATH [--dry-run] [--save]`: the general batch. A JSON array
  of operations runs in one call as **one undo step**; `invoke undo` reverts
  the whole batch. Every operation is checked against the open score first,
  and if any check fails nothing changes and no backup is made. Addresses
  are `staff`/`bar`/`index` exactly as `query` or `read` reported them before
  the batch; they stay correct even when earlier operations shift indices.
  Add `"type"` and/or `"position"` from the query result to any addressed
  operation as a guard against editing the wrong object. `--dry-run` checks
  and reports each target without changing anything.
  - `{"op":"set","staff":S,"bar":B,"index":I,"prop":P,"value":V}`: writable
    `Dx`, `Dy` (int), `Hidden`, `CueSize` (bool) on anything; `Beam`,
    `RestPosition` on NoteRest; `Text`, `Duration`, `NumNotes` (melisma span,
    bridge v50) on LyricItem; `Text` on
    Text; `Duration`, `RhDx` on lines.
  - `{"op":"nudge","staff":S,"bar":B,"index":I,"dx":X,"dy":Y}`: move by
    relative offsets (1/32 space); unlike `set` `Dx`, adds to the current value.
  - `set-pitch`, `tie`, `bracket`, `flip-stem`, `delete`: as in `patch-notes`
    below. Deleting a NoteRest leaves a rest.
  - `{"op":"add-note","staff":S,"bar":B,"position":P,"duration":D,"pitches":[..][,"voice":V,"tied":true]}`
    (adds to an existing chord at that position)
  - `{"op":"add-text","staff":S,"bar":B,"position":P,"text":T[,"styleId":"text.staff.expression","voice":V]}`
  - `{"op":"add-line","staff":S,"bar":B,"position":P,"duration":D,"styleId":"line.staff.hairpin.crescendo"[,"voice":V]}`
    (bridge v48)
  - `{"op":"add-lyric","staff":S,"bar":B,"position":P,"duration":D,"text":T[,"syllableType":"middle","voice":V]}`
  - Staff 0 is the system staff (bridge v48). It takes `set`, `delete`,
    `nudge`, `add-text` and `add-line`, with system styles only and no voice:
    `add-text` defaults to `text.system.tempo` there (or e.g.
    `text.system.metronome`), and `add-line` takes `line.system.*` styles such
    as `line.system.tempo.rall`. Every other staff takes only staff styles.
  - `{"op":"beam","staff":S,"bar":B,"firstIndex":I,"lastIndex":J}`: beam the
    NoteRests from I to J together (bridge v44)

  Structural operations (bridge v44) work on bar ranges or the whole score.
  They must come **after every operation above**, since they can replace or
  renumber the objects an address points at. Bars and staves refer to the
  score before the batch. A `set-time` re-bars what follows it, so no later
  operation may name a bar after its bar; likewise an `add-bars` with a `bar`
  moves that bar and every later one. Every `set-time` must come
  before any `set-key`, `set-break` or `set-barline` (re-barring erased a
  barline just before it).
  - `{"op":"transpose","fromBar":A,"toBar":B,"topStaff":T,"bottomStaff":U,"fromNote":"C","toNote":"D","direction":"up"[,"octaves":N]}`,
    or `"degree"` (±21) and `"intervalType"` (0-10) instead of the notes
  - `{"op":"copy-passage","fromBar":A,"toBar":B,"topStaff":T,"bottomStaff":U,"destStaff":S,"destBar":D[,"destPosition":P]}`:
    overwrites the destination; pasting past the last bar adds bars
  - `{"op":"set-key","bar":B,"key":"Bb"[,"minor":true]}`: one of the 15
    standard keys per mode; adds a double barline, as Sibelius does
  - `{"op":"set-time","bar":B,"numerator":N,"denominator":D[,"symbol":"common"|"cut"]}`
  - `{"op":"set-break","bar":B,"type":"system"|"page"|"none"}`
  - `{"op":"set-barline","bar":B,"type":T}`: types as in `set-barline`;
    replaces any special barline already there
  - `{"op":"add-bars","count":N[,"bar":B,"length":L]}`: appends N bars at the
    end, or inserts them before bar B; `length` (1/256 quarters) makes them
    irregular bars (`bar`/`length` bridge v50)
  - `{"op":"delete-bars","fromBar":A,"toBar":B}`: removes the bars from every
    staff and moves the rest up, as Delete Bars does on a system passage
    (bridge v56). Bar numbers after it shift, so no later operation may name a
    bar after A. Time signatures, repeats and barlines in the range go with it.
  - `{"op":"set-bar-number","bar":B,"number":N[,"skip":true]}`: restart bar
    numbering at bar B; `skip` leaves bar B itself unnumbered (bridge v50)
  - `{"op":"set-layout", ...}`: any of `pageSize` (`a4`, `letter`, `a3`,
    `tabloid`, `concert`, ...), `orientation` (`portrait`/`landscape`),
    `staffSize`, `topMargin`, `bottomMargin`, `leftMargin`, `rightMargin`,
    `aboveTopStaveGap`, `belowBottomStaveGap` (mm), `spacesBetweenStaves`,
    `extraSpacesBelowVocalStaves`, `spacesBetweenSystems` (staff spaces).
    Only the given settings change; `score_structure` reports the current
    values as `layout` and `engraving` (bridge v50).
  - `{"op":"delete-voice","fromBar":A,"toBar":B,"staff":S,"voice":V}`
  - `{"op":"hide-empty-staves","fromBar":A,"toBar":B}`: hides every staff
    with nothing in bars A-B, then optimizes staff spacing there (bridge v52)

  Typical flow: `query` to find targets, write the operations with the
  returned addresses plus `type`/`position` guards, `apply --dry-run`, then
  `apply`.
- `patch-lyrics --file PATH [--font F --font-size N] [--save]`: JSON array of
  `{staff, bar, index, text[, font, fontSize]}`. Use for two or more lyric
  changes.
- `patch-notes --file PATH [--save] [--dry-run]`: JSON array of note edits.
  All addresses refer to the score as read before the batch. The whole file
  runs as one `apply` batch (one undo step), with voice deletions last:
  - `{"op":"set-pitch","staff":S,"bar":B,"index":I,"oldPitch":P,"newPitch":Q}`
  - `{"op":"tie","staff":S,"bar":B,"index":I[,"remove":true]}`
  - `{"op":"bracket","staff":S,"bar":B,"index":I[,"remove":true]}` (parenthesize a note/chord)
  - `{"op":"flip-stem","staff":S,"bar":B,"index":I}`
  - `{"op":"delete","staff":S,"bar":B,"index":I}`
  - `{"op":"delete-voice","staff":S,"fromBar":A,"toBar":B,"voice":V}`
- `patch-layout --file PATH [--save] [--dry-run]`: JSON array of operations.
  Runs of `nudge`, `set-break`, `set-barline` and `set-time` go as `apply`
  batches, one undo step each; a new batch starts where the `apply` ordering
  rules require it (a nudge after a structural op, a `set-time` after a key,
  break or barline). Put `set-time` first: in a later batch it can still
  erase a barline just before it. `reset-design` and `remove-redundant-clefs`
  are separate steps.
  - `{"op":"nudge","staff":S,"bar":B,"index":I,"dx":X,"dy":Y}`
  - `{"op":"set-break","bar":B,"type":"system|page|none"}` (`none` clears a break; it does not forbid one)
  - `{"op":"set-barline","bar":B,"type":"double|final|..."}`
  - `{"op":"set-time","bar":B,"top":N,"bottom":D[,"symbol":"cut|common"]}`
  - `{"op":"reset-design","lyrics":false}`
  - `{"op":"remove-redundant-clefs"[,"staff":S]}`
- `invoke ID1 ID2 ...`: several built-in command IDs in one request.
- `round FILE.musicxml [--voices N --gap BARS --passes P --open]`: local
  MusicXML transform; builds a staggered-entry playback score from a
  single-part round, inferring voices and gap from `1.` `2.` entry marks.

Single-object writes:

- Structure: `add-staff`, `add-bars`, `set-staff-name`, `set-score-info`,
  `set-break`.
- Entry: `add-notes` and `add-abc` (enter a whole passage per call).
- Editing: `set-note`, `set-lyric`, `set-lyric-style`, `tie`, `delete-object`,
  `delete-voice`, `transpose`, `set-key`, `set-time`, `bracket`, `copy-passage`, `flip-stem`, `nudge`,
  `reset-design`. `transpose` and `delete-voice` take ranges; use one ranged
  call instead of per-bar calls. Each structural write (`transpose`,
  `copy-passage`, `set-key`, `set-time`, `set-break`, `set-barline`, `beam`,
  `add-bars`, `delete-voice`) runs as a one-operation `apply` batch, checked
  before the backup; `set-key` takes only the 15 standard keys per mode and
  `transpose --octaves` at most 2.
- Persistence: `save` and `backup`. Prefer `--save` on the final write over a
  separate `save`.
- Export: `export --format musicxml|mxl|pdf|midi|png [--out PATH] [--file SCORE]`.
- Rehearsal audio: `rehearsal-mixes --out DIR [--file SCORE] [--name 1=Soprano]
  [--bitrate 192k] [--keep-stems]` (bridge v54, needs ffmpeg). Exports one
  audio stem per staff and writes `<score> - All voices.mp3`, then
  `<voice> only` (that voice plus accompaniment) and `<voice> louder` (that
  voice at 3x amplitude) for each staff with lyrics. Voices are first
  equalized to one loudness; accompaniment keeps its Sibelius level. Every
  file is then gained as a whole to one integrated loudness (`--loudness`,
  default -16 LUFS, lowered if a file would peak above -1 dBFS), so balance
  within a file is exact and all files play at the same level. Name unnamed staves with
  `--name`. The score is not changed. Each staff is exported twice (the first
  copy warms the sound up: an export's opening otherwise carries the previous
  staff's voice), so allow about 10 seconds per staff. It prints each staff's playback sound
  first; `--require-sound Cantai` refuses to export unless every voice plays
  a sound set containing that name. `--all-parts` treats every staff as a
  voice, for instrumental scores without lyrics.
- Playback sounds: `playback-sounds [--require SOUND_SET]` (bridge v55) lists
  each staff's sound set, patch and sound ID at the start and at every later
  sound change, plus any Mixer override. `--require` exits non-zero if any
  staff's sound set does not contain the name.
- Playback roadmap (bridge v57): `play-order ["1-12, 1-12, 1-12"|auto]
  [--save]` reads or sets Play > Interpretation > Repeats. A list of bars sets
  Manual repeats playback (ranges expand to the bar numbers in playback
  order, via `Score.BarPlaybackOrder`); `auto` returns to the automatic order;
  no argument prints `manual`, `order` (the dialog's own string) and
  `barCount`. Backs up first. Don't play repeats has no ManuScript property.
- Play on pass (bridge v57): `play-on-pass --bar B [--passes 1-3|1,3|none|all]
  [--type end_repeat] [--position P] [--save]` sets Inspector > Playback >
  Play on pass (checkboxes 1-8) on the barline of that type in bar B: the
  listed passes are ticked, the others cleared, so `--passes 1-3` makes a
  repeat play three times. Without `--passes` it prints the checkboxes of
  every special barline in the bar. Backs up first.
  Checked live on a scratch score: `play-on-pass` set and read back boxes
  1-3; a fresh end-repeat reads only pass 1 ticked, a start repeat all eight;
  `play-order auto` clears manual mode. Assigning an order list from a JSON
  array was accepted but left the order at `1-48` (manual mode on), so the
  command checks the order Sibelius reports and retries with the dialog's text
  form (`BarPlaybackOrderString`); it fails loudly if neither takes. Check the
  printed `order` against the Repeats dialog.

Read a command's `--help` before composing a new invocation rather than
inferring omitted arguments.

Use global `--expect-file PATH` before a mutating subcommand to make the CLI
reject a frontmost-score mismatch before backup or mutation.

## Importing MusicXML

Writes refuse an imported, never-saved MusicXML score. Import and save it
through the bridge instead of asking the user to click through the import
dialog and Save As:

```bash
uv run sibelius-cli plugin ScoreBridge OpenScore --args '["/abs/score.xml"]'
uv run sibelius-cli plugin ScoreBridge ExportScore --args '["/abs/score.sib", "SIBL"]'
uv run sibelius-cli plugin ScoreBridge OpenScore --args '["/abs/score.sib"]'
```

`OpenScore` imports MusicXML silently. `ExportScore` with `SIBL` writes a
`.sib` but leaves the untitled import as the active window, so reopen the
saved file before editing. Back up any existing `.sib` at that path first.

`OpenScore` does not bring an already-open score to the front. With several
copies of the same score open (for example an old window and a fresh
re-import), reads can hit a stale window. Ask the user to close every copy,
confirm `score-snapshot` reports `no score open`, and then open from disk.

## Escape hatches

- `do undo` invokes the named built-in command.
- `invoke` accepts raw command IDs. Successful responses are fire-and-forget;
  see the Command IDs chapter linked from `docs/avid-reference.md`.
- `plugin ScoreBridge <Method> --args '<json>'` calls a bridge method directly.

Use escape hatches only when a purpose-built command does not cover the task,
and retain the required read/write/verify workflow from the main skill. When a
task needs many bridge calls with no batch command, write one Python script
that opens a single `SibeliusClient` session (see `scripts/clean_clefs.py`)
rather than looping CLI invocations.
