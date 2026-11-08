# Running Antigravity (`agy`) in an Autonomous Container

To run long or overnight tasks without approving individual tool permissions—and without granting unrestricted access to your entire Mac—you can run `agy` inside an isolated Linux container powered by [OrbStack](https://orbstack.dev/) (or Docker).

Inside the container, `agy` runs with `--dangerously-skip-permissions`, giving it full autonomy over its isolated workspace while keeping your macOS host filesystem protected.

---

## What is Inside the Container

The container image ([`Dockerfile`](../Dockerfile)) includes everything this repository and its agent skills need:

- **Google Antigravity CLI (`agy`)** pre-installed at `~/.local/bin/agy`
- **Python 3.13 & `uv`** (`ghcr.io/astral-sh/uv:python3.13-bookworm-slim`) with the project's virtual environment pre-warmed
- **Git & GitHub CLI (`gh`)** configured automatically with your host Git identity and `gh auth token` so the agent can create branches, push commits, open PRs, and watch CI checks (`gh pr checks --watch`)
- **Code Search & Score Tools**:
  - `semble` MCP server (`mcp__semble__search` and `mcp__semble__find_related`)
  - `ffmpeg` (rehearsal mixes and audio verification)
  - `poppler-utils` (`pdfinfo`, `pdftoppm` for PDF score inspection)
  - `pandoc` (Markdown to Word lyric sheets)
  - `lilypond` and `python-ly` (LilyPond score conversion)
- **Live Score Editor Bridge Forwarding (`socat`)**:
  - Forwards `127.0.0.1:1898` (Sibelius Connect), `127.0.0.1:4560` (Dorico Remote Control), and `127.0.0.1:8766` (MuseScore ScoreBridge) inside the container to `host.docker.internal` on your Mac
  - Shares `~/.config/ai-score-editing` so session tokens approved on your Mac work inside the container without re-prompting

---

## Quick Start

### 1. First-Time Sign-In to `agy`

Launch the container interactively:

```bash
./container/run.sh
```

On the very first run:
1. OrbStack builds the `ai-score-editing-agy:latest` image (takes ~1–2 minutes once).
2. The container clones an isolated copy of this repository into `/home/agent/workspace/ai-score-editing-workflows`.
3. `agy` prompts you with an OAuth URL to sign in with your Google account. Open the link in your Mac browser to complete authentication.

Your `agy` login state is saved in a dedicated Docker volume (`ai-score-editing-agy-gemini`), so subsequent container runs stay signed in automatically.

### 2. Running an Overnight Project (`/goal`)

You can start `agy` interactively and type `/goal` in the TUI:

```bash
./container/run.sh
```

Or pass an initial prompt directly from your Mac terminal:

```bash
./container/run.sh --goal "/goal Implement <task description>, run pytest and sync_skills.py --check, push a branch, and open a PR"
```

Or run a non-interactive one-shot prompt (`-p` / `--prompt`):

```bash
./container/run.sh --prompt "Run the full test suite and skill sync check, and summarize the status."
```

---

## Launcher Options (`./container/run.sh`)

| Option | Description |
| --- | --- |
| *(no arguments)* | Start interactive `agy --dangerously-skip-permissions` inside the isolated container workspace |
| `-i`, `--goal "<prompt>"` | Start interactive `agy` and immediately run `<prompt>` |
| `-p`, `--prompt "<prompt>"` | Run `<prompt>` non-interactively and print the result |
| `--fresh` | Wipe the container's cloned workspace volume and re-clone a clean copy from `main` |
| `--build` | Force a rebuild of the Docker image (`ai-score-editing-agy:latest`) |
| `--mount-host-repo` | Bind-mount your Mac working tree directly instead of using an isolated container clone |
| `--scores-dir <path>` | Mount a folder of score files from your Mac at `/scores` inside the container |
| `--shell` | Open a `bash` shell inside the container (for manual inspection or debugging) |

---

## How Workspace Isolation & PR Submission Work

By default (`WORKSPACE_MODE=clone`), the container does **not** touch your Mac's working copy:

1. **Isolated Clone**: The container maintains its own Git clone in the `ai-score-editing-agy-workspace` Docker volume (seeded quickly from `/host-repo:ro` and pointed at `https://github.com/wattdave/ai-score-editing-workflows.git`).
2. **GitHub Authentication**: `container/run.sh` reads `gh auth token` from your Mac's logged-in `gh` CLI and passes it as `GH_TOKEN` into the container. Inside the container, `gh auth setup-git` configures HTTPS Git pushes automatically—your SSH private keys never enter the container.
3. **Opening PRs**: The agent can create a feature branch, run `uv run pytest` and `python3 scripts/sync_skills.py --check`, push the branch to `origin`, and run `gh pr create` + `gh pr checks --watch`.

To start a brand-new task from a clean `main` branch, pass `--fresh`:

```bash
./container/run.sh --fresh
```

---

## Connecting to Live Score Editors on Your Mac

Pure WebSocket commands (`score_overview`, `score_structure`, `query_score`, `apply_batch`, `undo`) work from inside the container for **Sibelius** (`1898`) and **MuseScore** (`8766`) because the container forwards `127.0.0.1` ports to `host.docker.internal` and mounts `~/.config/ai-score-editing/`.

### Opening MusicXML / `.sib` Files & Dismissing Dialogs in Host Sibelius (`sibelius-host-open`)

When you launch `./container/run.sh --scores-dir "/path/to/scores"`, `run.sh` starts a lightweight, tightly-scoped host listener (`container/sibelius_host_helper.py`) on `127.0.0.1:1899` (forwarded into the container via `socat`). Inside the container, the `sibelius-host-open` command can:
- Open a `.musicxml`, `.xml`, or `.sib` file inside `/scores` in macOS Sibelius and automatically press `Return` (OK) on the MusicXML Import dialog:
  ```bash
  sibelius-host-open /scores/musicxml/AdesteFideles.musicxml
  ```
- Press `Return` on the Sibelius Connect remote-control approval dialog if Sibelius was just launched:
  ```bash
  sibelius-host-open --approve-connect
  ```
The host helper only accepts paths inside `--scores-dir` and verifies that `Sibelius` is the frontmost application before sending `Return`.

### Limitations When Driving Host GUI Editors from Linux

Because the container runs Linux while the score editors run on macOS:
- **File Paths (`save_score` / `export_score` / backups)**: When Sibelius writes a `.sib` file, backup, or PDF export, Sibelius expects a **macOS host path** (e.g., `/Users/wattd/Documents/Scores/...`), whereas tools inside the container read/write `/scores/...`. Pass the macOS path to `sibelius-cli save` / `export` / `--backup-dir`, and read the resulting file at `/scores/...` inside the container.
- **Dorico Lua & UI Scripting**: `dorico-cli` exchanges temporary Lua request/response files on disk with Dorico and uses macOS `osascript` (System Events) for MusicXML/PDF export and Project Info dialogs. Full Dorico automation and macOS GUI skills (`halbestunde-omr`, `musescore-pdf-convert`) require running on macOS directly rather than inside the Linux container.
