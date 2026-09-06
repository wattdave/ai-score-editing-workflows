# sibelius-websocket-cli — Specification

A command-line tool for driving Sibelius via **Sibelius Connect**, the WebSocket
server built into Sibelius 2024.3+ (Ultimate tier).

Protocol details below were empirically verified against a live Sibelius
instance on 2026-09-05. Sibelius Connect shares only its port-and-connect
*shape* with Dorico's Remote Control API — the message vocabulary is different
(Dorico-style `getstatus`/`getappinfo`/`getcommands` all return
`messageProcessingError: unrecognized message`).

## 1. Protocol (verified)

Transport: plain WebSocket, `ws://localhost:1898` by default (port configurable
in Sibelius). Messages are JSON objects with a `message` discriminator field.

### 1.1 Handshake

Client sends:

```json
{"message": "connect", "clientName": "<name>", "handshakeVersion": "1.0"}
```

Two cases:

- **No `sessionToken` supplied** — Sibelius shows a user-approval dialog
  (naming `clientName`). On approval it replies:
  ```json
  {"message": "connectResponse", "result": true, "sessionToken": "{uuid}"}
  ```
  If the user is slow to approve, the reply is simply delayed — use a generous
  timeout (≥ 60 s) and tell the user to look at Sibelius.
- **`sessionToken` supplied** (from a previous connect) — Sibelius accepts
  silently and sends **no reply at all**. The connection is immediately usable.
  A client MUST NOT block waiting for `connectResponse` in this case.

This is a one-step handshake. There is no Dorico-style
`acceptsessiontoken`/`kConnected` exchange (this mismatch is why mcp-score
v0.1.0's `connect_to_sibelius` fails against a healthy Sibelius).

Approval is **per-token, not per-`clientName`** (verified: reconnecting with
the same client name but no token re-prompts the user). Persisting the token is
therefore the only way to avoid a dialog on every invocation. Token lifetime
across Sibelius restarts is unverified. Handle rejection/expiry by falling back
to a tokenless connect (one dialog).

### 1.2 Commands

Two verified request shapes:

```json
{"message": "command", "commandName": "Edit.Undo"}
→ {"message": "commandResponse", "result": true}

{"message": "invokeCommands", "commands": ["<id>", "..."]}
→ {"message": "invokeCommandsResponse", "result": true}
```

`invokeCommands` batches multiple command IDs in one round trip (an empty list
is accepted and returns `result: true` — useful as a keepalive/ping).
Sibelius Connect reportedly exposes 900+ ManuScript command IDs; discovering
the full list is an open task (no `getcommands`-style message exists).

### 1.3 Errors

Unknown message types return:

```json
{"message": "messageProcessingError", "errorDetails": "unrecognized message"}
```

Command failures are expected to surface as `result: false` in the
`commandResponse`/`invokeCommandsResponse` (unverified — confirm with a bogus
command name).

## 2. CLI design

### 2.1 Package layout

```
src/sibelius_websocket_cli/
  __init__.py      # main() entry point (console script)
  cli.py           # argparse/typer command definitions
  client.py        # SibeliusClient: connect/handshake/send, sync wrapper over asyncio
  protocol.py      # message constants, request builders, response parsing
  token_store.py   # session-token persistence
```

Dependencies: `websockets` (runtime); `pytest` (dev). Prefer stdlib `argparse`
unless subcommand ergonomics justify `typer`.

### 2.2 Commands

```
sibelius-websocket-cli ping                      # connect + empty invokeCommands
sibelius-websocket-cli command <CommandName>     # send one command, print JSON response
sibelius-websocket-cli invoke <id> [<id> ...]    # batch via invokeCommands
sibelius-websocket-cli repl                      # interactive: read message names/JSON, print replies
sibelius-websocket-cli raw '<json>'              # send arbitrary JSON (protocol exploration)
sibelius-websocket-cli forget-token              # delete cached session token
```

Global options: `--host` (default `localhost`), `--port` (default `1898`),
`--client-name` (default `sibelius-websocket-cli`), `--timeout`, `--json`
(machine-readable output).

### 2.3 Session-token handling

- Persist the token at `~/.config/sibelius-websocket-cli/token.json`, keyed by
  `host:port` (mode 0600).
- Connect flow: token present → send connect with token, do **not** await a
  reply, verify liveness with an empty `invokeCommands`. No token / liveness
  check fails → tokenless connect, print "approve the connection in Sibelius",
  await `connectResponse` with a long timeout, store the new token.

### 2.4 Behavior

- Exit codes: 0 success; 1 command returned `result: false`; 2 connection or
  handshake failure.
- Default output: human-readable one-liner; `--json` prints the raw response.
- One connection per invocation (except `repl`); always close cleanly.

## 3. Milestones

1. **M1 — client core**: `protocol.py`, `client.py`, `token_store.py`; `ping`
   and `command` subcommands; tests with a fake WebSocket server.
2. **M2 — exploration tools**: `raw`, `invoke`, `repl`; discover and document
   useful ManuScript command IDs in `docs/commands.md`.
3. **M3 — ergonomics**: named high-level operations (undo, barlines, etc.)
   built on discovered commands; verify error/`result:false` semantics.

## 4. Open questions

- Session-token lifetime across Sibelius restarts.
- How to enumerate the available command IDs (no discovery message found).
- Shape of a failed command response (`result: false`? extra detail fields?).
- Whether any message can *read* score state (Sibelius Connect appears
  write/trigger-only; reading may require a ManuScript plugin bridge).
