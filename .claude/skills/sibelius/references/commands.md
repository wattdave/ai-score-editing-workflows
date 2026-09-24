# Command Reference

Use `uv run sibelius-websocket-cli <command> --help` for the complete current
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
  matches if any note of a chord matches. Properties are allow-listed per
  object type (an unknown name is rejected with the full list); objects lacking a
  filtered property never match. Use instead of reading bar ranges to hunt
  for objects, e.g. `query --staff Tenor --where 'Pitch>=67'` or
  `query --type Text --field Dx,Dy`. Output is capped at 500 objects; a
  `truncated: true` result means narrow the query.
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

- `patch-lyrics --file PATH [--font F --font-size N] [--save]`: JSON array of
  `{staff, bar, index, text[, font, fontSize]}`. Use for two or more lyric
  changes.
- `patch-notes --file PATH [--save] [--dry-run]`: JSON array of note edits.
  All addresses refer to the score as read before the batch; the CLI runs
  edits first, then deletes in descending index order per bar, then voice
  deletions, so addresses never shift under it:
  - `{"op":"set-pitch","staff":S,"bar":B,"index":I,"oldPitch":P,"newPitch":Q}`
  - `{"op":"tie","staff":S,"bar":B,"index":I[,"remove":true]}`
  - `{"op":"bracket","staff":S,"bar":B,"index":I[,"remove":true]}` (parenthesize a note/chord)
  - `{"op":"flip-stem","staff":S,"bar":B,"index":I}`
  - `{"op":"delete","staff":S,"bar":B,"index":I}`
  - `{"op":"delete-voice","staff":S,"fromBar":A,"toBar":B,"voice":V}`
- `patch-layout --file PATH [--save] [--dry-run]`: JSON array of operations:
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
  call instead of per-bar calls.
- Persistence: `save` and `backup`. Prefer `--save` on the final write over a
  separate `save`.
- Export: `export --format musicxml|mxl|pdf|midi|png [--out PATH] [--file SCORE]`.

Read a command's `--help` before composing a new invocation rather than
inferring omitted arguments.

Use global `--expect-file PATH` before a mutating subcommand to make the CLI
reject a frontmost-score mismatch before backup or mutation.

## Importing MusicXML

Writes refuse an imported, never-saved MusicXML score. Import and save it
through the bridge instead of asking the user to click through the import
dialog and Save As:

```bash
uv run sibelius-websocket-cli plugin sibwscli OpenScore --args '["/abs/score.xml"]'
uv run sibelius-websocket-cli plugin sibwscli ExportScore --args '["/abs/score.sib", "SIBL"]'
uv run sibelius-websocket-cli plugin sibwscli OpenScore --args '["/abs/score.sib"]'
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
  see `docs/commands.md` for the available IDs.
- `plugin sibwscli <Method> --args '<json>'` calls a bridge method directly.

Use escape hatches only when a purpose-built command does not cover the task,
and retain the required read/write/verify workflow from the main skill. When a
task needs many bridge calls with no batch command, write one Python script
that opens a single `SibeliusClient` session (see `scripts/clean_clefs.py`)
rather than looping CLI invocations.
