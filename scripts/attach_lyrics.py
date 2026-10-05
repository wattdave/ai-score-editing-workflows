#!/usr/bin/env python3
"""Attach a verified lyric-item plan to the open Sibelius score.

The plan is a JSON list of ``{staff, bar, position, duration, text,
syllableType}`` entries.  Positions and durations are Sibelius ticks (a
quarter note is 256).  The plan runs as one ``ApplyBatch`` of ``add-lyric``
operations, so it is a single undo step; it never adds, moves, or changes notes.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from ai_score_editing import batch_ops, protocol
from ai_score_editing.client import SibeliusClient


BRIDGE = "sibwscli"


async def call(client: SibeliusClient, method: str, args: list[Any]) -> Any:
    response = await client.invoke_plugin(BRIDGE, method, args)
    if not protocol.is_success(response):
        raise RuntimeError(f"{method} transport failure: {response}")
    value = protocol.plugin_return_value(response)
    if isinstance(value, dict) and "error" in value:
        raise RuntimeError(f"{method}: {value['error']}")
    return value


def parse_plan(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text())
    if not isinstance(payload, list) or not payload:
        raise ValueError("plan must be a non-empty JSON array")
    required = {"staff", "bar", "position", "duration", "text", "syllableType"}
    seen: set[tuple[int, int, int, int]] = set()
    for item in payload:
        if not isinstance(item, dict) or required - item.keys():
            raise ValueError(f"invalid lyric item: {item!r}")
        if item["syllableType"] not in {"end", "middle"}:
            raise ValueError(f"invalid syllableType: {item!r}")
        if unsupported := item.keys() & {"hidden", "styleId", "dy"}:
            raise ValueError(f"unsupported keys {sorted(unsupported)}: {item!r}")
        if "voice" in item and item["voice"] not in {1, 2, 3, 4}:
            raise ValueError(f"invalid voice: {item!r}")
        key = (item["staff"], item["bar"], item["position"], item.get("voice", 1))
        if key in seen:
            raise ValueError(f"duplicate lyric location: {key}")
        seen.add(key)
    return payload


def plan_to_batch(plan: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return batch_ops.validate_batch([{"op": "add-lyric", **item} for item in plan])


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--expect-file", type=Path, required=True)
    parser.add_argument("--save", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    plan = parse_plan(args.plan)
    operations = plan_to_batch(plan)
    expected = args.expect_file.expanduser().resolve()

    async with SibeliusClient(plugins=[BRIDGE], launch_if_needed=False) as client:
        info = await call(client, "GetScoreInfo", [])
        actual = Path(info["fileName"]).resolve()
        if actual != expected:
            raise RuntimeError(f"frontmost score mismatch: expected {expected}, got {actual}")
        if args.dry_run:
            print(json.dumps({"file": str(actual), "items": len(plan)}, indent=2))
            return
        result = await call(client, "ApplyBatch", [operations, False])
        if args.save:
            await call(client, "Save", [])
        print(json.dumps({"file": str(actual), "added": result.get("applied", 0)}, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
