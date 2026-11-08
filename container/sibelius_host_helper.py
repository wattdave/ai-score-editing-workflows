#!/usr/bin/env python3
"""Host-side HTTP helper for the autonomous Antigravity Docker container.

Exposes a tightly-scoped HTTP endpoint on 127.0.0.1:1899 (forwarded into the
container via socat) so the unprivileged Linux container can:
1. Open a MusicXML or .sib file in macOS Sibelius (`POST /open`) and press
   Return (OK) on the Sibelius MusicXML Import dialog.
2. Approve the Sibelius Connect dialog (`POST /approve-connect`) by pressing
   Return when Sibelius is frontmost.

Security boundary:
- Only binds to 127.0.0.1 on the macOS host.
- Only opens `.musicxml`, `.xml`, or `.sib` files located inside the allowed
  scores directory (`--scores-dir`).
- Never executes arbitrary shell commands or keystrokes in any app other than
  Sibelius (verified via System Events `frontmost is true`).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path


def osa(script: str) -> str:
    res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    return res.stdout.strip()


def frontmost() -> str:
    return osa('tell application "System Events" to return name of first process whose frontmost is true')


def press_return_in_sibelius(wait_before: float = 2.0, presses: int = 1) -> bool:
    time.sleep(wait_before)
    osa('tell application "Sibelius" to activate')
    for _ in range(10):
        if frontmost() == "Sibelius":
            break
        time.sleep(0.2)
    if frontmost() != "Sibelius":
        return False
    for i in range(presses):
        if frontmost() == "Sibelius":
            osa('tell application "System Events" to key code 36')
            if i + 1 < presses:
                time.sleep(0.8)
    return True


class HelperHandler(BaseHTTPRequestHandler):
    scores_dir: Path | None = None

    def log_message(self, fmt: str, *args) -> None:
        pass

    def _send(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send(200, {"ok": True, "scores_dir": str(self.scores_dir) if self.scores_dir else None})
        else:
            self._send(404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length > 0 else b"{}"
        try:
            data = json.loads(raw.decode("utf-8") or "{}")
        except Exception as exc:
            self._send(400, {"ok": False, "error": f"invalid json: {exc}"})
            return

        if self.path == "/approve-connect":
            ok = press_return_in_sibelius(wait_before=0.5, presses=1)
            self._send(200, {"ok": ok, "action": "approve-connect"})
            return

        if self.path in ("/open", "/open-musicxml"):
            req_path = str(data.get("path") or "").strip()
            if not req_path:
                self._send(400, {"ok": False, "error": "missing 'path'"})
                return

            # Translate container /scores/... path to host scores_dir
            if self.scores_dir and (req_path == "/scores" or req_path.startswith("/scores/")):
                rel = req_path[len("/scores"):].lstrip("/")
                host_path = (self.scores_dir / rel).resolve()
            else:
                host_path = Path(req_path).expanduser().resolve()

            if self.scores_dir:
                try:
                    host_path.relative_to(self.scores_dir.resolve())
                except ValueError:
                    self._send(403, {"ok": False, "error": f"path outside allowed scores_dir: {host_path}"})
                    return

            if host_path.suffix.lower() not in (".musicxml", ".xml", ".sib"):
                self._send(400, {"ok": False, "error": f"unsupported extension: {host_path.suffix}"})
                return

            if not host_path.is_file():
                self._send(404, {"ok": False, "error": f"file not found: {host_path}"})
                return

            subprocess.run(["open", "-a", "Sibelius", str(host_path)], check=True)
            is_xml = host_path.suffix.lower() in (".musicxml", ".xml")
            pressed = False
            if is_xml:
                pressed = press_return_in_sibelius(wait_before=float(data.get("wait", 2.2)), presses=1)
                time.sleep(2.5)
            else:
                time.sleep(2.0)

            self._send(200, {
                "ok": True,
                "host_path": str(host_path),
                "dialog_confirmed": pressed,
            })
            return

        self._send(404, {"ok": False, "error": f"unknown endpoint {self.path}"})


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=1899)
    ap.add_argument("--scores-dir", type=Path, default=None)
    args = ap.parse_args()

    HelperHandler.scores_dir = args.scores_dir.expanduser().resolve() if args.scores_dir else None
    server = HTTPServer((args.host, args.port), HelperHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
