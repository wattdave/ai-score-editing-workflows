# sibelius-websocket-cli

A command-line tool for driving Sibelius via **Sibelius Connect** — the
WebSocket server built into Sibelius 2024.3+ (Ultimate tier). It can fire any
of Sibelius's ~627 command IDs, and — via a bundled ManuScript bridge plug-in —
read score structure and note content back out.

## Getting started with Claude Code

You do not need to install anything by hand. You need a Mac, Sibelius
Ultimate 2026.6 or later, and a paid Claude account: Claude Code needs a
Pro, Max, Team or Enterprise plan, or a Console (API) account. The free
Claude plan does not include Claude Code; see
[Setting up without Claude](#setting-up-without-claude) instead.

1. Install Claude Code: open the **Terminal** app (Cmd+Space, type
   Terminal, press Return) and paste
   `curl -fsSL https://claude.ai/install.sh | bash`.
2. Get this folder: on GitHub, click **Code → Download ZIP** and unzip it
   (or `git clone` it if you already have git).
3. In Terminal, type `cd ` (with a trailing space), drag the folder onto the
   Terminal window, press Return, then type `claude` and press Return. The
   first time, it opens your browser to sign in to your Claude account, then
   asks whether to trust this folder and approve its `sibelius` tool server;
   say yes to both.
4. Type `/setup`. Claude explains what is missing (Homebrew, git, uv,
   Python 3.13, ffmpeg, the Sibelius plug-in), asks whether to install it
   all at once or one item at a time, and does the work.

`scripts/setup_check.sh` shows what is installed at any time.

## Using Codex or Antigravity instead

The skills in this folder also work in OpenAI Codex and Google Antigravity,
which both read the skills in `.agents/skills/` (Codex also reads
`AGENTS.md`). Instead of `/setup`, type `$setup` in Codex, or in either tool just ask "help me set up this project".

- **Codex** (install it following OpenAI's Codex docs) works with a
  ChatGPT account. OpenAI lists Codex on the Free plan for "quick coding
  tasks", but whether the Free plan includes the Codex command-line tool has
  not been tested with this project; paid ChatGPT plans include it.
  When Codex asks whether to trust this folder, say yes: that lets it load
  `.codex/config.toml`, which connects the `sibelius` tool server.
- **Antigravity** has a free Individual plan with weekly usage limits. It
  does not load this folder's `sibelius` tool server automatically, but the
  skills can run the `sibelius-websocket-cli` commands directly instead.

Free tiers have low limits. Setup fits easily; a long editing session may
run out partway.

## Setting up without Claude

The same steps by hand, in Terminal, from this folder:

1. See what is missing (this changes nothing):

   ```bash
   scripts/setup_check.sh
   ```

2. Install [Homebrew](https://brew.sh). It asks for your Mac password;
   nothing appears as you type, which is normal. Follow the "Next steps" it
   prints at the end so new Terminal windows can find `brew`.

   ```bash
   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
   ```

3. Install the tools, Python and this project's packages:

   ```bash
   brew install git uv ffmpeg
   uv python install 3.13
   uv sync
   ```

4. Open Sibelius once and quit it, then install the bridge plug-in:

   ```bash
   uv run sibelius-websocket-cli install-plugin
   ```

5. In Sibelius, turn on Sibelius Connect (Sibelius menu → Preferences →
   Input Devices, port 1898) and restart Sibelius.
6. With Sibelius open, check everything, and click OK when Sibelius asks to
   allow the connection:

   ```bash
   scripts/setup_check.sh --connect
   ```

## Requirements

- Sibelius Ultimate 2026.6 or later, running on the same machine
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
uv run sibelius-websocket-cli proofread            # read-only structural/lyric report
uv run sibelius-websocket-cli verify-render --format png --out /tmp/score-proof.png
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
uv run sibelius-websocket-cli patch-notes --file note-fixes.json --save   # pitches, ties, stems, deletes
uv run sibelius-websocket-cli transpose --from-note C --to-note D --up
uv run sibelius-websocket-cli set-key --key D             # key signature only
uv run sibelius-websocket-cli set-time --top 2 --bottom 2 --symbol cut  # cut time
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
                                                  # see the guide's Command IDs chapter
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

`round` arranges a single-part round as one part per voice for playback, also
locally. Voice count and entry spacing come from the score's `1.` `2.` entry
marks unless given; each voice sings the song `--passes` times (default 2),
holds its final note and drops out, and the last voice ends under a fermata:

```bash
uv run sibelius-websocket-cli round round.musicxml --open
uv run sibelius-websocket-cli round round.mxl --voices 3 --gap 4 --passes 1 -o out.mxl
```

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

## MCP server

`sibelius-mcp` exposes the open score to MCP clients over stdio. It keeps one
Sibelius Connect session open and needs the bridge plug-in (v39+).

| Tool | Does |
|---|---|
| `score_overview` | Score info, staves and selection |
| `score_structure` | Key and time signatures, special barlines and breaks, with the names `apply_batch` takes |
| `query_score` | Find bar objects by staff, bars, type, voice and property filters |
| `apply_batch` | Apply a batch of edits as one undo step, after checking every operation (`dry_run` to check only) |
| `undo` | Undo the last step(s); one batch is one step |
| `save_score` | Save the score to its file |
| `export_score` | Export as MusicXML, MXL, PDF, MIDI or PNG |

This repository's `.mcp.json` registers it for Claude Code. For another
client, run `uv run --directory /path/to/sibelius-websocket-cli sibelius-mcp`.
`SIBELIUS_HOST` and `SIBELIUS_PORT` override the default `localhost:1898`.
The first call shows Sibelius's connection approval dialog, as the CLI does.

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
- [`docs/avid-reference.md`](docs/avid-reference.md) — links to Avid's
  ManuScript Language Guide (Sibelius Connect protocol, all 627 command IDs,
  and the object reference for extending the bridge plug-in in
  `src/sibelius_websocket_cli/manuscript/sibwscli.plg`), plus the places
  where the guide is wrong

## Development

```bash
uv run pytest        # tests run against a fake Sibelius Connect server
```

Tests never reach a running Sibelius: `tests/conftest.py` fails any test that
connects to the Sibelius Connect port. One test demixes a real 12-page choral
export, which is copyrighted and kept out of the repository; it skips unless
`SIBWS_12PP_EXPORT` names the file:

```bash
SIBWS_12PP_EXPORT=~/Downloads/export.xml uv run pytest tests/test_polychoral.py
```

Sources: `src/sibelius_websocket_cli/` — `protocol.py` (message builders),
`client.py` (async client with token/approval handling), `launcher.py` (Sibelius
process detection and launch), `token_store.py`, `cli.py`, and the bundled bridge plug-in
under `manuscript/`.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Bug reports and skill requests are
welcome as GitHub issues.

## License

[Apache License 2.0](LICENSE). Sibelius, Sibelius Connect and ManuScript are
products of Avid Technology; this project is not affiliated with or endorsed
by Avid.
