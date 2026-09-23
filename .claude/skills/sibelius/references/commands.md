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
  - `{"op":"set-break","bar":B,"type":"system|page|none"}`
  - `{"op":"set-barline","bar":B,"type":"double|final|..."}`
  - `{"op":"set-time","bar":B,"top":N,"bottom":D[,"symbol":"cut|common"]}`
  - `{"op":"reset-design","lyrics":false}`
  - `{"op":"remove-redundant-clefs"[,"staff":S]}`
- `invoke ID1 ID2 ...`: several built-in command IDs in one request.

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
