# CLAUDE.md

This repository contains a Python CLI for driving Sibelius through Sibelius
Connect and the bundled `sibwscli` ManuScript bridge plug-in.

## Commands

The project requires Python 3.13 or newer and is managed with `uv`.

```bash
uv sync
uv run sibelius-websocket-cli
uv run pytest
python3 scripts/sync_skills.py
python3 scripts/sync_skills.py --check
```

## Agent skills

`.claude/skills/` is the source of truth. Each skill directory, including its
on-demand references, is symlinked into `.agents/skills/`; the sync script also
generates the corresponding `.cursor/rules/*.mdc` entrypoint. `AGENTS.md` is a
symlink to this file.

## Script execution

Use quoted heredocs for multi-line Python or AppleScript. Do not pass multi-line
programs through `python3 -c`, `osascript -e`, or nested shell strings. Quoting
the heredoc delimiter prevents the shell from altering embedded quotes.
