---
name: sibelius
description: Apply user-described changes to the score open in Sibelius (transpose, edit lyrics, read notes, etc.) via this repo's CLI. Use when the user asks to inspect or modify a score, e.g. "transpose it into D major", "check the lyrics for spelling errors", "what notes are in bar 3", or "/sibelius".
---

# Driving Sibelius

All interaction goes through `uv run sibelius-websocket-cli ...` (run from the
repo root). It talks to Sibelius Connect on localhost:1898 and, for score
reads/writes, to the bundled `sibwscli` ManuScript bridge plug-in.

## The choreography (always, in this order)

1. **Confirm the target score.** Run `score-info` and check `fileName` against
   what the user means. The bridge acts on the *frontmost* score window;
   with several files open, the wrong one silently gets the edit. If
   `fileName` doesn't match, ask the user to bring the right score to front.
2. **Read before writing.** Fetch the region you're about to change
   (`read`, `read-lyrics`, `score-info`) — both to plan the change and to have
   a before-image for verification.
3. **Write.** Write subcommands (`set-lyric`, `transpose`, `set-key`, …)
   automatically back up first: timestamped `.sib` copy next to the original
   (authoritative) plus a best-effort in-file version. Never bypass this.
4. **Verify by reading back** and tell the user what changed, including the
   backup file path printed on stderr. What the bridge can't verify
   (key signatures, clefs — initial ones don't appear in bar iteration),
   ask the user to confirm on screen.

## Connection and approval realities

- One approval dialog per Sibelius launch (session tokens die with the
  process); another if the declared plug-in list changes. When a command
  hangs on "Waiting for connection approval", tell the user to click OK in
  Sibelius — don't kill it early (timeout is 120 s).
- Exit 2 = can't connect: Sibelius not running or Sibelius Connect disabled
  (Preferences → Input Devices).
- Exit 1 with "bridge plug-in not reachable" or a version-mismatch error:
  run `install-plugin`, then the user must restart Sibelius. Any edit to
  `src/sibelius_websocket_cli/manuscript/sibwscli.plg` needs the same restart
  — batch plug-in changes and bump `GetBridgeVersion` when editing it.

## Command cheat sheet

Reads: `score-info` (title/file/key/time sigs), `staves`, `selection`,
`read --staff N --from A --to B` (notes with MIDI pitch/name/tie, lyrics with
text, addressed by staff/bar/index), `read-lyrics [--staff N]` (0 = all).

Writes (auto-backup): `set-lyric --staff --bar --index --text`,
`transpose --from-note C --to-note D --up|--down [--from-bar --to-bar
--top-staff --bottom-staff]` (whole score by default; downward transposition
has never been exercised live — verify extra carefully),
`set-key --bar --key [--minor]`, `backup [--name]`.

Escape hatches: `do undo`, raw command IDs via `invoke` (fire-and-forget:
success responses are meaningless — see docs/commands.md for all 627), any
bridge method via `plugin sibwscli <Method> --args '<json>'`.

## Task patterns

**Lyric spell-check:** `read-lyrics` → assemble syllables into words
(`syllableType: middle` = word continues, `end` = word ends) → report
suspected errors to the user with bar numbers → on approval, `set-lyric`
per fix using the addresses from the read → `read-lyrics` again to verify.
Addresses are only valid against the read they came from; re-read after
every write.

**Transpose to a key:** current key from `score-info` `keySignatures`
(empty = C major / no signature) → confirm direction with the user if
ambiguous → `transpose --from-note <cur> --to-note <target> --up|--down` →
read back a bar to check pitches → ask the user to confirm the key signature
on screen.

## Trust the local docs, not the Avid guide

The ManuScript Language Guide has proven wrong in specifics (documented
`utils.CalculateDegree` doesn't exist; `return_value` vs `returnValue`).
Ground any new bridge work in `docs/manuscript-object-tree.md`,
`docs/manuscript-constants.md`, `docs/commands.md`, and `SPEC.md`, and
live-probe on a scratch copy of the score before touching real music.
