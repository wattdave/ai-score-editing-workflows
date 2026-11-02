#!/usr/bin/env python3
"""Install and talk to the MuseScore probe plug-in (scripts/dev/musescore_probe/).

    uv run python scripts/dev/musescore_probe.py install
    uv run python scripts/dev/musescore_probe.py eval 'return curScore.nmeasures;'
    uv run python scripts/dev/musescore_probe.py run probe.js

`install` generates a token (or reuses the stored one), stores it in
~/.config/sibelius-websocket-cli/musescore-probe-token (mode 600) and writes
the plug-in, with the token, to ~/Documents/MuseScore4/Plugins/ScoreBridge-probe/.
In MuseScore, enable "ScoreBridge probe" in Plugins > Plugin Manager once, then
run it from the Plugins menu in each session. Snippets are JavaScript
function bodies; see msprobe.qml.in for the names they can use.
"""

from __future__ import annotations

import argparse
import asyncio
import itertools
import json
import os
import secrets
import sys
from pathlib import Path

import websockets

PORT = int(os.environ.get("MUSESCORE_PROBE_PORT", "8767"))
TEMPLATE = Path(__file__).with_name("musescore_probe") / "msprobe.qml.in"
TOKEN_FILE = Path.home() / ".config" / "sibelius-websocket-cli" / "musescore-probe-token"
PLUGIN_DIR = Path(os.environ.get("MUSESCORE_PLUGIN_DIR", Path.home() / "Documents" / "MuseScore4" / "Plugins"))

_ids = itertools.count(1)


def install() -> Path:
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    token = TOKEN_FILE.read_text().strip() if TOKEN_FILE.exists() else ""
    if not token:
        token = secrets.token_urlsafe(32)
        TOKEN_FILE.write_text(token)
    TOKEN_FILE.chmod(0o600)
    target = PLUGIN_DIR / "ScoreBridge-probe" / "msprobe.qml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(TEMPLATE.read_text().replace("@TOKEN@", token).replace("@PORT@", str(PORT)))
    target.chmod(0o600)
    return target


async def evaluate(code: str, timeout: float) -> dict:
    token = TOKEN_FILE.read_text().strip()
    request_id = next(_ids)
    async with websockets.connect(f"ws://127.0.0.1:{PORT}", max_size=None) as ws:
        await ws.send(json.dumps({"id": request_id, "token": token, "code": code}))
        return json.loads(await asyncio.wait_for(ws.recv(), timeout))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("install")
    ev = sub.add_parser("eval")
    ev.add_argument("code")
    run = sub.add_parser("run")
    run.add_argument("file")
    for p in (ev, run):
        p.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args(argv)

    if args.command == "install":
        print(f"installed {install()}")
        return 0
    code = args.code if args.command == "eval" else Path(args.file).read_text()
    try:
        reply = asyncio.run(evaluate(code, args.timeout))
    except (OSError, websockets.exceptions.WebSocketException) as exc:
        print(f"cannot reach the probe on port {PORT}: {exc}. Is Plugins > ScoreBridge probe running?", file=sys.stderr)
        return 2
    except TimeoutError:
        print("no reply: a dialog may be open in MuseScore", file=sys.stderr)
        return 2
    print(json.dumps(reply.get("result") if reply.get("ok") else reply, indent=1))
    return 0 if reply.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
