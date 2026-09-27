"""The Dorico back end's operations, shared by its MCP server and CLI.

Each function takes a connected DoricoBridge and mirrors a Sibelius MCP
tool: overview, structure, query, apply (one undo step), undo, save and
export. See docs/dorico.md for what Dorico's scripting does not expose.
"""

from __future__ import annotations

import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from . import score
from .bridge import BarMap, DoricoBridge
from .client import DoricoError

EXPORT_FORMATS = {"preview-pdf": "preview.pdf", "preview-png": "preview.png"}


async def _located(bridge: DoricoBridge, flow: int) -> tuple[list[dict[str, Any]], BarMap]:
    events = await bridge.read(flow)
    bars = await bridge.bars(flow, events)
    return score.locate_events(events, bars), bars


def _last_bar(located: list[dict[str, Any]], bars: BarMap) -> int:
    ends = [e["flowPosition"] + (e.get("duration") or 0) for e in located if e["staff"] != 0]
    if not ends:
        return 1
    bar, offset = bars.locate(max(ends))
    return bar if offset or bar == 1 else bar - 1


async def overview(bridge: DoricoBridge, flow: int = 1) -> dict[str, Any]:
    info = await bridge.overview(flow)
    located, bars = await _located(bridge, flow)
    status = await bridge.client.status()
    app = await bridge.client.app_info()
    return {
        "dorico": app.get("number"),
        "score": {
            "title": info.get("title"),
            "flow": flow,
            "flowCount": info.get("flowCount"),
            "flows": await bridge.client.flows(),
            "lastBarWithMusic": _last_bar(located, bars),
            "players": info.get("players"),
        },
        "staves": info.get("staves"),
        "layouts": await bridge.client.layouts(),
        "selection": {"hasSelection": status.get("hasSelection"), "type": status.get("selectedEventType")},
        "bridge": info.get("bridge"),
    }


async def structure(bridge: DoricoBridge, flow: int = 1) -> dict[str, Any]:
    located, bars = await _located(bridge, flow)
    time_signatures = [
        {"bar": first, "position": 0, "barLength": length, "flowPosition": start}
        for first, start, length in bars.segments()
    ]
    keys = [
        {"bar": e["bar"], "position": e["position"], "flowPosition": e["flowPosition"], "id": e["id"]}
        for e in located if e["type"] == "TonalityDivisionEvent"
    ]
    return {
        "timeSignatures": time_signatures,
        "keySignatures": keys,
        "note": (
            "Dorico's scripting cannot read a time signature's numerator and denominator or a key "
            "signature's key; barLength (1/256 quarters) is measured, and key signatures report only "
            "where they are."
        ),
        "lastBarWithMusic": _last_bar(located, bars),
    }


async def query(
    bridge: DoricoBridge,
    *,
    flow: int = 1,
    staves: list[str] | None = None,
    from_bar: int | None = None,
    to_bar: int | None = None,
    types: list[str] | None = None,
    voice: int | None = None,
    where: list[str] | None = None,
    limit: int = 200,
) -> dict[str, Any]:
    located, _ = await _located(bridge, flow)
    wanted = None
    if staves:
        wanted = score.resolve_staves(staves, (await bridge.overview(flow))["staves"])
    return score.query(
        located, staves=wanted, from_bar=from_bar, to_bar=to_bar,
        types=types, voice=voice, where=where, limit=limit,
    )


async def apply(
    bridge: DoricoBridge, operations: list[dict[str, Any]], *, flow: int = 1, dry_run: bool = False
) -> dict[str, Any]:
    """Apply a batch as one undo step; nothing changes unless every op checks out."""
    located, bars = await _located(bridge, flow)
    staves = (await bridge.overview(flow))["staves"]
    prepared = score.prepare_batch(operations, located, staves, bars)
    status = await bridge.client.status()
    if not dry_run and status.get("notReadOnly") is False:
        raise DoricoError("the score is read-only")
    checked = await bridge.apply(prepared, flow, dry_run=True)
    if "error" in checked:
        raise DoricoError(f"{checked['error']}; nothing was changed")
    if dry_run:
        return {"dryRun": True, "operations": prepared, "checked": checked.get("results")}
    result = await bridge.apply(prepared, flow)
    if "error" in result:
        applied = result.get("applied", 0)
        raise DoricoError(
            f"{result['error']}; {applied} operation(s) were applied as one undo step. "
            "Call undo once to revert them."
        )
    return {"applied": result.get("applied"), "results": result.get("results")}


async def undo(bridge: DoricoBridge, steps: int = 1) -> dict[str, Any]:
    """Undo up to `steps` changes, stopping when Dorico has nothing to undo."""
    if not 1 <= steps <= 20:
        raise DoricoError("steps must be 1-20")
    done = 0
    for _ in range(steps):
        if not (await bridge.client.status()).get("canUndo"):
            break
        await bridge.client.command("Edit.Undo")
        done += 1
    return {"undone": done, "requested": steps}


async def save(bridge: DoricoBridge, path: str) -> dict[str, Any]:
    target = Path(path).expanduser().resolve()
    if target.suffix != ".dorico":
        raise DoricoError("path must end in .dorico")
    target.parent.mkdir(parents=True, exist_ok=True)
    return await bridge.save(target)


async def export(bridge: DoricoBridge, format: str, path: str) -> dict[str, Any]:
    """Export the preview Dorico embeds in a saved project (the first page).

    Full PDF and MusicXML export go through Dorico's export dialogs, which a
    script cannot drive (docs/dorico.md).
    """
    if format not in EXPORT_FORMATS:
        raise DoricoError(f"format must be one of: {', '.join(EXPORT_FORMATS)}")
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "export.dorico"
        await bridge.save(copy)
        with zipfile.ZipFile(copy) as archive:
            member = f"supplementary_data/preview/{EXPORT_FORMATS[format]}"
            with archive.open(member) as source, target.open("wb") as sink:
                shutil.copyfileobj(source, sink)
    return {"files": [str(target)], "note": "first page of the full score only"}
