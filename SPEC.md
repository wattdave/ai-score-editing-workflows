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
therefore the only way to avoid a dialog on every invocation. Per the official
docs (`docs/sibelius-connect.md`), a token **is valid only as long as Sibelius
runs** — expect one approval dialog per Sibelius launch. Handle rejection or
expiry by falling back to a tokenless connect.

The connect message also takes an optional `"plugins"` array — the file names
(without extension) of every ManuScript plug-in the client intends to call via
`invokePlugin`. The plug-in list is fixed for the session and **cannot be
changed when reconnecting with a token**; changing it requires a tokenless
connect. Connections are only accepted from the same host.

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

The valid command IDs are the snake_case ManuScript command IDs (e.g. `undo`,
`add_bar_at_end`) documented in the ManuScript Language Guide chapter 5 — all
627 are extracted verbatim to `docs/commands.md`. The same IDs are what
ManuScript's `Sibelius.Execute()` takes.

**`result: true` only acknowledges receipt, not execution** (verified with a
bogus command ID, and confirmed by the official docs: "the `invokeCommands`
message always returns success"). Exit code 1 (`result: false`) may never
occur in practice for command messages.

### 1.3 Plug-in invocation (verified)

```json
{"message": "invokePlugin", "name": "pluginX", "method": "Method", "args": [42, {"k": "v"}]}
→ {"message": "invokePluginResponse", "result": true, "return_value": "..."}
```

`name` (plug-in file name without extension, which must have been declared in
the connect message's `plugins` array) is mandatory; `method` defaults to
`Run`; `args` supports strings, booleans, numbers, nested arrays, and
dictionaries. `result` reports whether the plug-in/method was found and
called; the return value carries the method's return (empty string if none,
JSON `null` if untranslatable). The field is **`returnValue`** (verified live —
the guide's example wrongly shows `return_value`; the client accepts both).
Nested arrays and dictionaries round-trip intact in both directions.

Gotcha: some ManuScript property values are not directly JSON-translatable and
arrive as `null` (observed with `Score.FileName` on a saved score). Coerce
such values to strings in the plug-in (`value & ''`) before returning them.

This is the path to *reading* score state: a ManuScript plug-in (see
`docs/manuscript-object-tree.md` for the object API) can return data, unlike
fire-and-forget command IDs.

### 1.4 Errors

Unknown message types return:

```json
{"message": "messageProcessingError", "errorDetails": "unrecognized message"}
```

Command messages never report failure (see 1.2). `invokePluginResponse.result`
is the only documented per-call failure signal.

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
sibelius-websocket-cli plugin <name> [method] [--args JSON]   # invokePlugin
sibelius-websocket-cli score-info | staves | selection        # bridge reads
sibelius-websocket-cli read --staff N --from A --to B         # read bar contents
sibelius-websocket-cli do <operation>           # curated named command IDs
sibelius-websocket-cli install-plugin           # install bundled sibwscli.plg
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
3. **M3 — plug-in bridge** (done): `invokePlugin` support (client method,
   `plugins` list in connect, tokens bound to their declared plug-in list,
   `plugin`/`score-info`/`install-plugin` subcommands); bundled `sibwscli.plg`
   bridge returning score state.
4. **M4 — ergonomics** (done): bridge methods GetStaves, GetSelectionInfo,
   ReadBars (notes with pitch/name/tie, durations, positions, per bar);
   `staves`/`selection`/`read` subcommands; `do <operation>` named operations
   mapped to curated command IDs.

## 4. Open questions

- Whether any response ever carries `result: false` (bogus command IDs are
  silently acknowledged with `result: true`).
- Whether any message can *read* score state directly — per the official docs,
  reading requires an `invokePlugin` round trip to a ManuScript plug-in that
  returns the data (M3).
