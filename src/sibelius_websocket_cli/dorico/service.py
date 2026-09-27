"""The Dorico back end's operations, shared by its MCP server and CLI.

Each function takes a connected DoricoBridge and mirrors a Sibelius MCP
tool: overview, structure, query, apply (one undo step), undo, save and
export. See docs/dorico.md for what Dorico's scripting does not expose.
"""

from __future__ import annotations

import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import musicxml_read, score
from .bridge import BarMap, DoricoBridge
from .client import DoricoError
from .export import export_musicxml, export_pdf

#: Formats export_score takes: pdf through Print mode, previews from a saved copy.
PREVIEWS = {"preview-pdf": "preview.pdf", "preview-png": "preview.png"}
EXPORT_FORMATS = ["pdf", "musicxml", *PREVIEWS]


@dataclass
class Snapshot:
    """A flow as the back end sees it: located events and the bar map.

    Events Dorico's Lua can read carry their Dorico id. Staves it cannot
    read (lyrics) come from a MusicXML export instead, without ids; then
    bars, time and key signatures come from the export too.
    """

    located: list[dict[str, Any]]
    bars: BarMap
    musicxml: dict[str, Any] | None = None
    export: Path | None = None
    unreadable_staves: list[int] = field(default_factory=list)


async def snapshot(bridge: DoricoBridge, flow: int = 1) -> Snapshot:
    events, unreadable = await bridge.read_partial(flow)
    if not unreadable:
        bars = await bridge.bars(flow, events)
        return Snapshot(score.locate_events(events, bars), bars)
    path = await export_musicxml(bridge.client, flow)
    xml = musicxml_read.read(path)
    staves = (await bridge.overview(flow))["staves"]
    if len(xml["staves"]) != len(staves):
        raise DoricoError(
            f"the MusicXML export has {len(xml['staves'])} staves but the flow has {len(staves)}; "
            "cannot combine them"
        )
    bad = sorted({u["staff"] for u in unreadable if u.get("staff")})
    lua_located = [e for e in score.locate_events(events, xml["bars"]) if e["staff"] not in bad]
    from_xml = [dict(e, source="musicxml") for e in xml["events"] if e["staff"] in bad]
    located = sorted(
        lua_located + from_xml,
        key=lambda e: (e["staff"], e["bar"], e["position"], e.get("voice") or 0, e.get("pitch") or 0),
    )
    counters: dict[tuple[int, int], int] = {}
    for item in located:
        key = (item["staff"], item["bar"])
        item["index"] = counters.get(key, 0)
        counters[key] = item["index"] + 1
    return Snapshot(located, xml["bars"], xml, path, bad)


def _last_bar(located: list[dict[str, Any]], bars: BarMap) -> int:
    ends = [e["flowPosition"] + (e.get("duration") or 0) for e in located if e["staff"] != 0]
    if not ends:
        return 1
    bar, offset = bars.locate(max(ends))
    return bar if offset or bar == 1 else bar - 1


async def overview(bridge: DoricoBridge, flow: int = 1) -> dict[str, Any]:
    info = await bridge.overview(flow)
    snap = await snapshot(bridge, flow)
    status = await bridge.client.status()
    app = await bridge.client.app_info()
    result = {
        "dorico": app.get("number"),
        "score": {
            "title": info.get("title"),
            "flow": flow,
            "flowCount": info.get("flowCount"),
            "flows": await bridge.client.flows(),
            "lastBarWithMusic": _last_bar(snap.located, snap.bars),
            "players": info.get("players"),
        },
        "staves": info.get("staves"),
        "layouts": await bridge.client.layouts(),
        "selection": {"hasSelection": status.get("hasSelection"), "type": status.get("selectedEventType")},
        "bridge": info.get("bridge"),
    }
    if snap.unreadable_staves:
        result["readFromMusicXML"] = {"staves": snap.unreadable_staves, "file": str(snap.export)}
    return result


async def structure(bridge: DoricoBridge, flow: int = 1) -> dict[str, Any]:
    snap = await snapshot(bridge, flow)
    if snap.musicxml is not None:
        return {
            "timeSignatures": snap.musicxml["timeSignatures"],
            "keySignatures": snap.musicxml["keySignatures"],
            "bars": [
                {"bar": first, "barLength": length, "flowPosition": start}
                for first, start, length in snap.bars.segments()
            ],
            "barCount": snap.musicxml["barCount"],
            "source": str(snap.export),
        }
    time_signatures = [
        {"bar": first, "position": 0, "barLength": length, "flowPosition": start}
        for first, start, length in snap.bars.segments()
    ]
    keys = [
        {"bar": e["bar"], "position": e["position"], "flowPosition": e["flowPosition"], "id": e["id"]}
        for e in snap.located if e["type"] == "TonalityDivisionEvent"
    ]
    return {
        "timeSignatures": time_signatures,
        "keySignatures": keys,
        "note": (
            "Dorico's scripting cannot read a time signature's numerator and denominator or a key "
            "signature's key; barLength (1/256 quarters) is measured, and key signatures report only "
            "where they are."
        ),
        "lastBarWithMusic": _last_bar(snap.located, snap.bars),
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
    located = (await snapshot(bridge, flow)).located
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
    snap = await snapshot(bridge, flow)
    staves = (await bridge.overview(flow))["staves"]
    prepared = score.prepare_batch(operations, snap.located, staves, snap.bars)
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
    """Export the open project and copy the result to path.

    pdf: the current layout, all pages, with Print mode's settings.
    musicxml: the full score of flow 1 through the Export MusicXML window.
    preview-pdf / preview-png: the first page Dorico embeds in a saved copy.
    """
    if format not in EXPORT_FORMATS:
        raise DoricoError(f"format must be one of: {', '.join(EXPORT_FORMATS)}")
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    if format in ("pdf", "musicxml"):
        produced = await (export_pdf(bridge.client) if format == "pdf" else export_musicxml(bridge.client))
        if produced.resolve() != target:
            shutil.copyfile(produced, target)
        return {"files": [str(target)], "exportedBy": str(produced)}
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "export.dorico"
        await bridge.save(copy)
        with zipfile.ZipFile(copy) as archive:
            member = f"supplementary_data/preview/{PREVIEWS[format]}"
            with archive.open(member) as source, target.open("wb") as sink:
                shutil.copyfileobj(source, sink)
    return {"files": [str(target)], "note": "first page of the full score only"}
