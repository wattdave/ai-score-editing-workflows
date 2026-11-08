#!/usr/bin/env python3
"""Container-side CLI to ask the macOS Host Sibelius Helper to open a file in Sibelius.

Usage inside the container:
  sibelius-host-open /scores/musicxml/AdesteFideles.musicxml
  sibelius-host-open --approve-connect
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("path", nargs="?", help="Path to .musicxml, .xml, or .sib file (under /scores)")
    ap.add_argument("--approve-connect", action="store_true", help="Press Return on the Sibelius Connect dialog")
    ap.add_argument("--wait", type=float, default=2.2, help="Seconds to wait before pressing Return on the MusicXML dialog")
    ap.add_argument("--port", type=int, default=int(os.environ.get("SIBELIUS_HELPER_PORT", "1899")))
    args = ap.parse_args()

    base_url = f"http://127.0.0.1:{args.port}"
    if args.approve_connect:
        endpoint = f"{base_url}/approve-connect"
        payload = {}
    elif args.path:
        endpoint = f"{base_url}/open"
        payload = {"path": args.path, "wait": args.wait}
    else:
        ap.error("provide a file path or --approve-connect")

    req = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            print(json.dumps(body))
            return 0 if body.get("ok") else 1
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="replace")
        print(f"error ({exc.code}): {err_body}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"error connecting to host Sibelius helper at {base_url}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
