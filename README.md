# sibelius-websocket-cli

A command-line tool for driving Sibelius via **Sibelius Connect** — the
WebSocket server built into Sibelius 2024.3+ (Ultimate tier). It can fire any
of Sibelius's ~627 command IDs, and — via a bundled ManuScript bridge plug-in —
read score structure and note content back out.

## Requirements

- Sibelius Ultimate 2024.3 or later, running on the same machine
- Python 3.13+ and [uv](https://docs.astral.sh/uv/)

## Setup

1. **Enable Sibelius Connect** in Sibelius: Preferences → Input Devices
   (default port 1898).

2. **Install the CLI**:

   ```bash
   uv sync
   ```

3. **Install the bridge plug-in** (needed only for the read commands —
   `score-info`, `staves`, `selection`, `read`):

   ```bash
   uv run sibelius-websocket-cli install-plugin
   ```

   Then restart Sibelius so it loads the plug-in.

4. **First connection**: any command will make Sibelius show an approval
   dialog naming the client — click OK. The session token is cached at
   `~/.config/sibelius-websocket-cli/token.json`, so subsequent invocations
   connect silently. Tokens die with the Sibelius process, so expect one
   dialog per Sibelius launch.

## Usage

Reading the open score (requires the bridge plug-in):

```bash
uv run sibelius-websocket-cli score-info          # title, file, staves, bars
uv run sibelius-websocket-cli inspect             # compact identity, staves, selection
uv run sibelius-websocket-cli score-snapshot      # compact structural snapshot
uv run sibelius-websocket-cli staves              # instrument names per staff
uv run sibelius-websocket-cli selection           # current passage selection
uv run sibelius-websocket-cli read --staff 1 --from 1 --to 4
                                                  # bar contents: notes (MIDI
                                                  # pitch, name, tie), rests,
                                                  # durations, positions
```

Writing (each write backs up first: in-file version + save + timestamped
`.sib` copy next to the original):

```bash
uv run sibelius-websocket-cli check-lyrics                # lint lyrics for typos, collisions, untexted bars
uv run sibelius-websocket-cli read-lyrics --words         # lyrics grouped by staff and bar into words
uv run sibelius-websocket-cli read-lyrics                 # all raw lyrics with addresses
uv run sibelius-websocket-cli read-lyrics --compact       # compact edit addresses
uv run sibelius-websocket-cli set-lyric --staff 1 --bar 3 --index 2 --text "ry-"
uv run sibelius-websocket-cli patch-lyrics --file patches.json --font Plantin --font-size 95
uv run sibelius-websocket-cli patch-layout --file layout-fixes.json --save
uv run sibelius-websocket-cli transpose --from-note C --to-note D --up
uv run sibelius-websocket-cli set-key --key D             # key signature only
uv run sibelius-websocket-cli backup                      # backup on demand
uv run sibelius-websocket-cli bridge-version              # check installed bridge
```

Driving Sibelius with command IDs (fire-and-forget — Sibelius acknowledges
receipt but never reports whether a command did anything):

```bash
uv run sibelius-websocket-cli do undo             # curated friendly names:
                                                  # undo, redo, save, select-all,
                                                  # select-none, delete, add-bar,
                                                  # play, play-stop, transpose-dialog
uv run sibelius-websocket-cli invoke select_all delete
                                                  # raw command IDs, batched;
                                                  # see docs/commands.md for all 627
```

Splitting MusicXML is performed locally and deterministically (no score is
edited in Sibelius except optional `.sib` export/opening):

```bash
uv run sibelius-websocket-cli split-parts score.mxl --preset satb --out score_satb.mxl
uv run sibelius-websocket-cli split-parts score.mxl --preset 16voices --audit --json
```

The SATB profile accepts `--soprano-solo`, `--tenor-solo`, and
`--bass-solo` bar ranges. Audit mode writes nothing and returns stable issue
codes for malformed rhythm, ambiguous XML voices, unsupported pitch counts,
and ties.

Calling ManuScript plug-ins and exploring the protocol:

```bash
uv run sibelius-websocket-cli plugin sibwscli Echo --args '[1, {"a": true}]'
uv run sibelius-websocket-cli raw '{"message": "invokeCommands", "commands": []}'
uv run sibelius-websocket-cli repl                # interactive session
uv run sibelius-websocket-cli ping                # is Sibelius responding?
uv run sibelius-websocket-cli forget-token        # drop the cached token
```

Global options: `--host`, `--port`, `--client-name`, `--timeout` (seconds to
wait for the approval dialog), `--launch` / `--no-launch` (automatically start Sibelius
if not running, default: true), `--launch-timeout` (seconds to wait for Sibelius to start, default: 30),
`--sibelius-path` (custom application executable path), `--json` (raw JSON responses),
`--expect-file` (reject writes to a different frontmost score),
`-v` (wire traffic logging).

Exit codes: `0` success, `1` the call failed (plug-in not found, bridge error),
`2` could not connect to Sibelius.

## Multi-Agent Skills (Claude, Antigravity, Cursor)

The canonical Sibelius skill lives in `.claude/skills/sibelius/`. Its concise
entrypoint links to focused references that agents read only for the active
workflow. The complete directory is exposed to Antigravity by symlink; the
generated Cursor rule links back to the same canonical references without
automatically loading them. Keep the harness files in sync:

```bash
python scripts/sync_skills.py          # sync .claude/skills, .agents/skills, and .cursor/rules
python scripts/sync_skills.py --check  # check for drift without modifying files
```

## Documentation

- [`SPEC.md`](SPEC.md) — the empirically verified Sibelius Connect wire
  protocol (one-step handshake, silent token reconnect, `invokePlugin`
  semantics and gotchas) and the CLI design
- [`docs/sibelius-connect.md`](docs/sibelius-connect.md) — the official
  protocol chapter from the ManuScript Language Guide
- [`docs/commands.md`](docs/commands.md) — all 627 command IDs
- [`docs/manuscript-object-tree.md`](docs/manuscript-object-tree.md) — the
  full ManuScript object reference, for extending the bridge plug-in
  (`src/sibelius_websocket_cli/manuscript/sibwscli.plg`)

## Development

```bash
uv run pytest        # tests run against a fake Sibelius Connect server
```

Sources: `src/sibelius_websocket_cli/` — `protocol.py` (message builders),
`client.py` (async client with token/approval handling), `launcher.py` (Sibelius
process detection and launch), `token_store.py`, `cli.py`, and the bundled bridge plug-in
under `manuscript/`.
