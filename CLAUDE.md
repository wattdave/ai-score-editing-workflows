# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code), Antigravity, and other coding agents when working with code in this repository.

## Project

A CLI tool for driving Sibelius (the music notation app) via Sibelius Connect, its built-in WebSocket server (Sibelius 2024.3+, port 1898), paired with a companion ManuScript bridge plug-in (`sibwscli.plg`).

Key capabilities:
- **Transport & Lifecycle**: WebSocket handshake with silent token reuse, auto-launching Sibelius if not running.
- **Score Inspection**: Reads score metadata, staves, passages, notes with pitches/ties, lyrics, and selections.
- **Lyric Proofreading & Editing**: Automated lyric linting (`check-lyrics`) for horizontal collisions, vertical note-lyric collisions (with clef & ledger line awareness), missing vowels, cross-voice divergence, and untexted passages with multi-verse awareness and bar range filtering (`--bars`); stanza formatting (`read-lyrics --words [--verse N]`); and targeted writing (`set-lyric`).
- **Engraving & Modification**: In-file versioning + auto-backup, layout nudging (`nudge`), stem flipping (`flip-stem`), passage copying, transposition, direct score saving (`save`, `--save`), design/format reset (`reset-design`), and format export (MusicXML, MIDI, PDF, PNG).
- **Agent Skill Harmonization**: Single source of truth for agent skills in `.claude/skills/` synchronized to Antigravity and Cursor via `scripts/sync_skills.py`.

## Commands

Managed with [uv](https://docs.astral.sh/uv/); requires Python >= 3.13 (pinned in `.python-version`).

```bash
uv sync                          # install/update the environment
uv run sibelius-websocket-cli    # run the CLI
uv run pytest                    # run the test suite
python3 scripts/sync_skills.py   # sync skills across agent harnesses
python3 scripts/sync_skills.py --check # verify all harnesses are in sync
```

## Structure

- Package: `src/sibelius_websocket_cli/`
  - `client.py`: WebSocket client and connection management
  - `launcher.py`: Sibelius process detection and launching
  - `lyrics.py`: lyric parsing, word aggregation, and proofreading lint rules
  - `cli.py`: command-line parser and bridge dispatching
  - `manuscript/sibwscli.plg`: ManuScript bridge plug-in installed into Sibelius
- Tests: `tests/` (`test_client.py`, `test_launcher.py`, `test_lyrics.py`, `test_skills_sync.py`)
- Skills: `.claude/skills/sibelius/SKILL.md` (synced to `.agents/skills/` and `.cursor/rules/`)

## Script Execution Rules

- **Always use quoted heredocs (`<< 'EOF'`):** Never execute inline scripts via `-c '...'` or nested command-line string arguments (such as `python3 -c '...'` or `osascript -e '...'`).
- Multi-line scripts must ALWAYS use quoted heredocs (`python3 << 'EOF'`, `osascript << 'EOF'`) or be written to a temporary scratch file. Quoting the delimiter (`'EOF'`) ensures single and double quotes inside the script are never mangled by the shell.


