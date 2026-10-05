---
name: sibelius
description: Apply user-described changes to the score open in Sibelius, including transposition, lyric work, note inspection, and engraving, through this repository's CLI. Use for score inspection or modification requests and /sibelius.
---

# Driving Sibelius

Run all commands from the repository root with:

```bash
uv run sibelius-cli <command>
```

The CLI talks to the frontmost score in Sibelius through Sibelius Connect and
the bundled `ScoreBridge` ManuScript bridge.

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

Writes refuse a never-saved MusicXML import; import and save it through the
bridge, not dialogs ([commands](references/commands.md#importing-musicxml)).

## Batch first: minimize calls and output

Each CLI call opens a session and its output enters context. Batch commands
use one session, one backup, one verification, and a compact summary:

| Instead of | Use |
| --- | --- |
| `score-info` + `staves` + `selection` | `inspect` or `score-snapshot` |
| `check-lyrics` + per-staff `read-lyrics` | `proofread [--lyrics]` |
| repeated `set-lyric` | `patch-lyrics --file` |
| repeated `set-note` / `tie` / `flip-stem` / `delete-object` | `patch-notes --file` |
| repeated nudges, breaks, barlines, clef deletes | `patch-layout --file` |
| `export --format png` | `verify-render` |
| several `invoke` calls | one `invoke ID1 ID2 ...` |

- Scope reads with `--bars` and `--staff`; prefer `read --abc` and
  `read-lyrics --compact|--words`; avoid `--json`.
- Collect all edits, then write once with `--save` instead of a later `save`.
- Trust a batch summary; re-read only on reported problems or for fresh
  addresses. Validate patch files with `--dry-run`.

## Required workflow

1. Run `inspect` (or `score-snapshot` when you also need structure) and
   confirm that `fileName` is the score the user intends. If it is not, ask
   the user to bring the correct score to the front.
2. Read the smallest relevant region before changing it. For review, start
   with one `proofread`; for notes use `read --abc`; use compact addressed
   reads before targeted edits.
3. Apply the requested writes as one batch where a batch command exists, with
   global `--expect-file <path>` before the subcommand. Write commands create
   a timestamped `.sib` backup beside the source and attempt an in-file
   version first. Do not bypass the backup path.
4. Verify the result and report the backup path printed on stderr. Use the
   batch command's verified summary; otherwise read only the changed region
   again. Ask the user to confirm on screen when the bridge cannot expose the
   result, including initial key signatures and clefs.

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
- A fresh Sibelius may reject the first connection
  (`kClientRejected_UserRefusedRequest`) without a prompt; retry once.
- Exit 2 means Sibelius is unavailable or Sibelius Connect is disabled under
  Preferences → Input Devices.
- Exit 1 with a bridge-unreachable or version-mismatch message requires
  `install-plugin`, followed by a Sibelius restart.

## Local authority

For new bridge work, use `docs/avid-reference.md` and `docs/sibelius-protocol.md`; live-probe
changes on a scratch score before applying them to real music.
