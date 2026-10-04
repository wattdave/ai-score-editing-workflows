---
name: musescore
description: Inspect, compose and edit the score open in MuseScore 4 (notes, rests, chords, tuplets, lyrics, adding or deleting bars, time signatures, tempo, adding instruments) through the third-party musescore MCP server (ghchen99/mcp-musescore) and its WebSocket plug-in. Use for MuseScore score requests and /musescore.
---

# Driving MuseScore

The `musescore` MCP server is [ghchen99/mcp-musescore](https://github.com/ghchen99/mcp-musescore)
(MIT, see [LICENSE](LICENSE)). It is not part of this repository's own back
ends and works differently from the Sibelius and Dorico tools: it moves a
cursor and types at it, with no addresses, guards, dry runs or one-step
batches. [docs/musescore.md](../../../docs/musescore.md) compares it with the
Sibelius tools.

- Read [references/tools.md](references/tools.md) before choosing a tool or
  writing a `processSequence`. It lists the 26 tools, their parameters and
  the ones that do not do what their names say.
- Read [references/architecture.md](references/architecture.md) when
  diagnosing connection, plug-in, port or response problems.

## Setup

`.mcp.json` starts the server through `scripts/musescore_mcp.sh`, which
downloads the pinned commit into `.vendor/mcp-musescore` and copies
`musescore-mcp-websocket.qml` into `~/Documents/MuseScore4/Plugins`. In
MuseScore the user must:

1. Open a score.
2. Enable "MuseScore API Server" once in Plugins → Plugin Manager.
3. Run Plugins → MuseScore API Server in every MuseScore session. The plug-in
   listens on `ws://localhost:8765`; the Python server only connects to it.

To check the bridge without MCP:

```bash
uv run --no-project --with websockets python .claude/skills/musescore/scripts/probe-musescore-bridge.py
```

## Workflow

1. `ping_musescore`. If it reports `Not connected to MuseScore`, ask the user
   to run the plug-in; do not retry edits until a ping returns `pong`.
2. `get_score` before editing. It returns the raw envelope; the score is in
   `result.analysis`. Ticks are 480 per quarter note, not this repository's
   256. Measures and staves are zero-based in the tools, one-based in
   MuseScore's display.
3. Place the cursor (`go_to_measure`, `select_custom_range`, `next_staff`)
   and check the returned selection before writing.
4. Make one or two edits directly, or a known sequence with `processSequence`.
5. `get_score` again and report only what it shows.

## Guardrails

- Every tool call, and every step in a `processSequence`, is a separate undo
  step. `undo` reverts one; count the steps before undoing a sequence.
- `processSequence` keeps going after a failing step and still reports
  success. Verify with `get_score`.
- `set_staff_mute` hides the staff instead of muting it. `set_instrument_sound`
  only opens MuseScore's Instruments panel. Do not use either for playback.
- `delete_selection` deletes whatever is selected. Check the selection first.
- There is no save or export tool. Ask the user to save in MuseScore
  (Cmd+S) and to export from File → Export.
- `undo` reverts whatever was done last, the user's own edits included.
