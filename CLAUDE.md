# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

A CLI tool for driving Sibelius (the music notation app) via Sibelius Connect, its built-in WebSocket server (Sibelius 2024.3+, port 1898). Currently a bare uv-managed Python scaffold — the entry point is a hello-world stub.

**Read `SPEC.md` before implementing** — it documents the empirically verified wire protocol (one-step handshake, silent token reconnect, `command`/`invokeCommands` messages), the planned module layout, CLI surface, and open questions. Notably, Sibelius Connect is *not* the Dorico Remote Control protocol despite sharing the connect shape.

## Commands

Managed with [uv](https://docs.astral.sh/uv/); requires Python >= 3.13 (pinned in `.python-version`).

```bash
uv sync                          # install/update the environment
uv run sibelius-websocket-cli    # run the CLI
```

No test suite or linter is configured yet. If adding tests, use `uv run pytest` after adding pytest as a dev dependency (`uv add --dev pytest`).

## Structure

- Package: `src/sibelius_websocket_cli/` (src layout, built with `uv_build`)
- Console script `sibelius-websocket-cli` maps to `sibelius_websocket_cli:main` in `src/sibelius_websocket_cli/__init__.py`
