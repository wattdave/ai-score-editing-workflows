# Command Reference

Use `uv run sibelius-websocket-cli <command> --help` for the complete current
argument list. Run commands from the repository root.

## Reads

- `inspect`: compact score identity, staff names, and current selection. Prefer
  this initial safety check over three separate read commands.
- `score-snapshot [--bars A-B] [--lyrics] [--no-barlines]`: one-session,
  compact structural snapshot with identity, staves, selection, key/time
  signatures, and special barlines; lyrics are opt-in.
- `proofread [--bars A-B] [--staff N] [--lyrics]`: one-session read-only
  structural and lyric lint report with compact issue records.
- `verify-render [--format png|pdf] [--out PATH]`: export once and verify that
  rendered files exist, are non-empty, and optionally match page/hash checks.
- `score-info`: title, file, key signatures, and time signatures.
- `staves`: staff numbers and names.
- `selection`: current Sibelius selection.
- `read [--staff N] [--from A] [--to B] [--bars A-B] [--abc]`: addressed
  notes, pitches, ties, and lyrics. `--abc` or `read-abc` produces compact ABC
  notation with aligned lyrics.
- `read-lyrics [--staff N] [--bars A-B] [--words|--compact] [--verse N]`: addressed
  lyric items. Verse `0` means all verses; `--words` groups syllables into
  words by staff, verse, and bar; `--compact` retains edit addresses in a short
  line format.
- `check-lyrics [--staff N] [--bars A-B] [--verse N]`: lyric collision,
  missing-vowel, cross-voice divergence, and untexted-passage checks.

## Writes

Write commands create a backup before mutation.

- Structure: `add-staff`, `add-bars`, `set-staff-name`, `set-score-info`, and
  `set-break`.
- Entry: `add-notes` and `add-abc`.
- Editing: `set-note`, `set-lyric`, `patch-lyrics`, `set-lyric-style`, `transpose`, `set-key`,
  `copy-passage`, `flip-stem`, `nudge`, and `reset-design`.
- Batched layout: `patch-layout --file PATH [--save]`, with validated `nudge`,
  `set-break`, `set-barline`, `reset-design`, and conservative
  `remove-redundant-clefs` operations.
- Persistence: `save` and `backup`.
- Export: `export --format musicxml|mxl|pdf|midi|png [--out PATH] [--file SCORE]`;
  `verify-render` adds file/page verification for rendered output.

Most mutating commands accept `--save`. Read their `--help` before composing a
new invocation rather than inferring omitted arguments.

Use global `--expect-file PATH` before a mutating subcommand to make the CLI
reject a frontmost-score mismatch before backup or mutation.

## Escape hatches

- `do undo` invokes the named built-in command.
- `invoke` accepts raw command IDs. Successful responses are fire-and-forget;
  see `docs/commands.md` for the available IDs.
- `plugin sibwscli <Method> --args '<json>'` calls a bridge method directly.

Use escape hatches only when a purpose-built command does not cover the task,
and retain the required read/write/verify workflow from the main skill.
