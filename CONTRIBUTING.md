# Contributing

Thanks for helping. Bug reports, score problems the tools could not fix,
new skills and code changes are all welcome.

## Getting set up

Follow [Getting started](README.md#getting-started-with-claude-code) in the
README, or run `scripts/setup_check.sh` and install what it reports missing.
You need a Mac and Sibelius Ultimate 2026.6 or later to use the tools; the
test suite runs without Sibelius.

## Reporting a problem

Open an issue using a template. For score problems, include the Sibelius
version, what you asked for, what happened, and (if you can share it) a
small score that shows the problem. Do not attach scores you do not have the
right to share.

## Making a change

1. Branch from `main` and keep each pull request to one change.
2. Run the checks:

   ```bash
   uv run pytest
   python3 scripts/sync_skills.py --check
   ```

3. If you change the bridge plug-in (`src/sibelius_websocket_cli/manuscript/sibwscli.plg`),
   bump its version, reinstall it with
   `uv run sibelius-websocket-cli install-plugin`, restart Sibelius, and try
   the change on a real score. Say in the pull request what you tested.
4. Skills live in `.claude/skills/`. After adding or editing one, run
   `python3 scripts/sync_skills.py` to update the Codex, Antigravity and
   Cursor copies.
5. `uv.lock` must resolve from public PyPI; `tests/test_lockfile.py` checks
   this.

Using an AI assistant to write your change is fine. You are responsible for
reviewing and testing what it produces.

## License

By contributing you agree that your contributions are licensed under the
[Apache License 2.0](LICENSE).
