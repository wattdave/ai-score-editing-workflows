---
name: sibelius
description: Apply user-described changes to the score open in Sibelius, including transposition, lyric work, note inspection, and engraving, through this repository's CLI. Use for score inspection or modification requests and /sibelius.
---

# Driving Sibelius

Run all commands from the repository root with:

```bash
uv run sibelius-websocket-cli <command>
```

The CLI talks to the frontmost score in Sibelius through Sibelius Connect and
the bundled `sibwscli` ManuScript bridge.

## Desktop access and opening scores

Bridge commands communicate with the running macOS Sibelius application. Run
every such command (`inspect`, reads, writes, exports, and plug-in calls) with
desktop access outside the filesystem sandbox. A sandboxed invocation can fail
to see an already-running Sibelius process and mistakenly try to relaunch it.

If a requested score is not frontmost, open it directly rather than asking the
user to do so:

```bash
open -a /Applications/Sibelius.app /absolute/path/to/score.sib
```

Then run `inspect` and confirm `fileName` before reading or changing the score.

## Required workflow

1. Run `inspect` and confirm that `fileName` is the score the user intends.
   If it is not, ask the user to bring the correct score to the front.
2. Read the smallest relevant region before changing it. Prefer `read --abc`
   for notes and `read-lyrics --words` for lyric review; use addressed reads
   before targeted edits.
3. Apply the requested write with global `--expect-file <path>` before the
   subcommand. Write commands create a timestamped `.sib`
   backup beside the source and attempt an in-file version first. Do not bypass
   the backup path.
4. Verify the result and report the backup path printed on stderr. Use a
   command's verified summary when it provides one; otherwise read the changed
   region again. Ask the user to confirm on screen when the bridge cannot
   expose the result, including initial key signatures and clefs.

Addresses are valid only for the read that produced them. Re-read after a
write before using an address again.

## Load only the relevant guidance

- For available commands and argument shapes, read
  [the command reference](references/commands.md).
- For proofreading or changing lyric text, read
  [the lyric workflow](references/lyrics.md).
- For collisions, typography, stems, spacing, or rendered-page review, read
  [the engraving workflow](references/engraving.md); also read the lyric
  workflow when changing lyric text.
- For transposition, key changes, note edits, or passage copying, read
  [the music-edit workflow](references/music-edits.md).
- For bridge plug-in development or a bridge-version failure, read
  [the bridge-development notes](references/bridge-development.md).

Do not load unrelated references.

## Connection recovery

- A new Sibelius process or changed declared plug-in list can show an approval
  dialog. If a command reports that it is waiting, ask the user to click OK in
  Sibelius; the connection timeout is 120 seconds.
- Exit 2 means Sibelius is unavailable or Sibelius Connect is disabled under
  Preferences → Input Devices.
- Exit 1 with a bridge-unreachable or version-mismatch message requires
  `install-plugin`, followed by a Sibelius restart.

## Local authority

For new bridge work, use `docs/manuscript-object-tree.md`,
`docs/manuscript-constants.md`, `docs/commands.md`, and `SPEC.md`; live-probe
changes on a scratch score before applying them to real music.
