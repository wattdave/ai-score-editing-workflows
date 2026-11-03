# CLAUDE.md

This repository contains Python CLIs, MCP servers and agent skills for driving
score editors: Sibelius (through Sibelius Connect and the bundled `ScoreBridge`
ManuScript plug-in), Dorico and MuseScore. Code lives in `src/ai_score_editing/`,
with one subpackage per editor (`sibelius/`, `dorico/`, `musescore/`), editor-neutral
pipelines in `workflows/` (MusicXML splitting and rounding, ABC, rehearsal mixes),
pure helpers in `core/`, and shared modules at the top level.

## New users

Many people using this repository are new to Claude Code and to the
terminal. At the start of a session, if the user seems new, asks how to get
started, or a command fails because a tool is missing, use the `setup` skill
(also `/setup`). It checks and installs Homebrew, git, uv, Python 3.13,
ffmpeg, the project packages, and the Sibelius bridge plug-in. Optional:
poppler (PDF page images), pandoc (Markdown to Word) and LibreOffice
(`soffice --headless --convert-to pdf` to render and check Word files).

## Commands

The project requires Python 3.13 or newer and is managed with `uv`.

```bash
uv sync
uv run sibelius-cli
uv run pytest
uv run dorico-cli overview      # Dorico back end, see docs/dorico.md
python3 scripts/sync_skills.py
python3 scripts/sync_skills.py --check
```

## Architecture

Layering, the package map, where to add a CLI command, MCP tool or editor
operation, testing seams and backward-compat notes are in
[docs/architecture.md](docs/architecture.md). Shared pure helpers live in
`core/`, editor-neutral pipelines in `workflows/`, and each editor's CLI is a
thin layer over its `service.py`.

## Agent skills

`.claude/skills/` is the source of truth. Each skill directory, including its
on-demand references, is symlinked into `.agents/skills/`; the sync script also
generates the corresponding `.cursor/rules/*.mdc` entrypoint. `AGENTS.md` is a
symlink to this file.

## Script execution

Use quoted heredocs for multi-line Python or AppleScript. Do not pass multi-line
programs through `python3 -c`, `osascript -e`, or nested shell strings. Quoting
the heredoc delimiter prevents the shell from altering embedded quotes.
