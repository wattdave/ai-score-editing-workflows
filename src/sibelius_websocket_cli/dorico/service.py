"""The Dorico back end's operations, shared by its MCP server and CLI.

Each function takes a connected DoricoBridge and mirrors a Sibelius MCP
tool: overview, structure, query, apply (one undo step), undo, save and
export. See docs/dorico.md for what Dorico's scripting does not expose.
"""

from __future__ import annotations

import asyncio
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote
from typing import Any

from . import layout, musicxml_read, score
from .bridge import BarMap, DoricoBridge
from .client import DoricoError
from .export import bring_to_front, export_musicxml, export_pdf

#: Formats export_score takes: pdf through Print mode, previews from a saved copy.
PREVIEWS = {"preview-pdf": "preview.pdf", "preview-png": "preview.png"}
EXPORT_FORMATS = ["pdf", "musicxml", *PREVIEWS]


@dataclass
class Snapshot:
    """A flow as the back end sees it: staves, located events, the bar map.

    Events Dorico's Lua can read carry their Dorico id. A MusicXML export is
    made when the voice layout needs it (layout.py) or a staff has lyrics
    (which Lua cannot read); lyric staves then come from the export without
    ids, and bars, time and key signatures come from the export too.
    """

    staves: list[dict[str, Any]]
    located: list[dict[str, Any]]
    bars: BarMap
    musicxml: dict[str, Any] | None = None
    export: Path | None = None
    unreadable_staves: list[int] = field(default_factory=list)
    unplaced_voices: list[int] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


async def snapshot(bridge: DoricoBridge, flow: int = 1) -> Snapshot:
    raw = (await bridge.overview(flow))["layout"]
    events, unreadable = await bridge.read_partial(flow)
    staves = None
    if not unreadable:
        try:
            staves = layout.resolve(raw, events)
        except layout.NeedsMusicXML:
            staves = None
    if staves is not None:
        placed = layout.assign(events, staves)
        bars = await bridge.bars(flow, events)
        return Snapshot(staves, score.locate_events(placed, bars), bars, raw=raw)

    path = await export_musicxml(bridge.client, flow)
    xml = musicxml_read.read(path)
    staves = layout.resolve(raw, events, xml)
    if len(xml["staves"]) != len(staves):
        raise DoricoError(
            f"the MusicXML export has {len(xml['staves'])} staves but the flow has {len(staves)}; "
            "cannot combine them"
        )
    placed = layout.assign(events, staves)
    unreadable_streams = {u["stream"] for u in unreadable}
    bad = sorted(
        s["staff"] for s in staves
        if s["stream"] in unreadable_streams or unreadable_streams & set(s["voiceStreams"])
    )
    placed_streams = {v for s in staves for v in s["voiceStreams"]}
    all_voices = {v for i in raw["instruments"] for v in i.get("voiceStreams") or []}
    lua_located = [e for e in score.locate_events(placed, xml["bars"]) if e["staff"] not in bad]
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
    return Snapshot(staves, located, xml["bars"], xml, path, bad, sorted(all_voices - placed_streams), raw)


def _last_bar(located: list[dict[str, Any]], bars: BarMap) -> int:
    ends = [e["flowPosition"] + (e.get("duration") or 0) for e in located if e["staff"] != 0]
    if not ends:
        return 1
    bar, offset = bars.locate(max(ends))
    return bar if offset or bar == 1 else bar - 1


async def overview(bridge: DoricoBridge, flow: int = 1) -> dict[str, Any]:
    info = await bridge.overview(flow)
    snap = await snapshot(bridge, flow)
    info["staves"] = snap.staves
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
    if snap.export is not None:
        result["readFromMusicXML"] = {"staves": snap.unreadable_staves, "file": str(snap.export)}
    if snap.unplaced_voices:
        result["unplacedVoiceStreams"] = snap.unplaced_voices
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
    snap = await snapshot(bridge, flow)
    located = snap.located
    wanted = None
    if staves:
        wanted = score.resolve_staves(staves, snap.staves)
    return score.query(
        located, staves=wanted, from_bar=from_bar, to_bar=to_bar,
        types=types, voice=voice, where=where, limit=limit,
    )


async def apply(
    bridge: DoricoBridge, operations: list[dict[str, Any]], *, flow: int = 1, dry_run: bool = False
) -> dict[str, Any]:
    """Apply a batch as one undo step; nothing changes unless every op checks out."""
    snap = await snapshot(bridge, flow)
    prepared = score.prepare_batch(operations, snap.located, snap.staves, snap.bars)
    status = await bridge.client.status()
    if not dry_run and status.get("notReadOnly") is False:
        raise DoricoError("the score is read-only")
    if any(op["op"] in score.COMMAND_OPS for op in operations if isinstance(op, dict)):
        return await _apply_commands(bridge, prepared, snap, flow, dry_run)
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


async def _apply_commands(
    bridge: DoricoBridge, prepared: list[dict[str, Any]], snap: Snapshot, flow: int, dry_run: bool
) -> dict[str, Any]:
    """Run a batch of command ops (set-break, add-lyrics) in order.

    Break removals go first, as one Lua step. Each added break is two undo
    steps (selecting its note, which Dorico records, and the break); each
    add-lyrics is one step for the selection plus one per syllable. The
    result reports how many steps to undo. Lyrics are checked afterwards
    against a MusicXML export, since Lua cannot read a staff with lyrics.
    """
    removals = [op for op in prepared if op["op"] == "delete"]
    commands = [op for op in prepared if op["op"] != "delete"]
    blocks = snap.raw.get("blocks") or {}
    for op in commands:
        block = blocks.get(str(op["select"]["stream"]))
        if block is None:
            raise DoricoError(f"cannot find the event block of stream {op['select']['stream']}; nothing was changed")
        op["select"]["block"] = block
    if removals:
        checked = await bridge.apply(removals, flow, dry_run=True)
        if "error" in checked:
            raise DoricoError(f"{checked['error']}; nothing was changed")
    planned = (1 if removals else 0) + sum(
        2 if op["op"] == "set-break" else 1 + len(op["syllables"]) for op in commands
    )
    if dry_run:
        return {"dryRun": True, "operations": prepared, "undoSteps": planned}
    steps = 0
    results: list[dict[str, Any]] = []
    if removals:
        result = await bridge.apply(removals, flow)
        if "error" in result:
            raise DoricoError(f"{result['error']}; call undo once to revert the removals")
        steps += 1
        results += [{"op": "set-break", "type": "none", "position": op["position"]} for op in removals]
    flows = await bridge.client.flows()
    if commands and not 1 <= flow <= len(flows):
        raise DoricoError(f"Dorico lists {len(flows)} flow(s), not flow {flow}")
    flow_id = flows[flow - 1]["flowID"] if commands else None
    lyrics = []
    for op in commands:
        target = op["select"]
        try:
            await bridge.client.command(
                f"EventEdit.Select?FlowID={flow_id}&EventID={target['id']}&EventBlockID={target['block']}"
            )
            steps += 1  # the selection is an undo step of its own
            if op["op"] == "set-break":
                await bridge.client.command("Edit.CreateSystemBreak")
                events, _ = await bridge.read_partial(flow)
                made = [e for e in events if e["type"] == "BreakEvent" and e["position"] == op["position"]]
                if not made:
                    raise DoricoError(f"Dorico made no break at bar {op['bar']}")
                steps += 1
                results.append({"op": "set-break", "type": "system", "bar": op["bar"], "id": made[0]["id"]})
            else:
                steps += await _type_lyrics(bridge, op["syllables"])
                lyrics.append(op)
                results.append({"op": "add-lyrics", "staff": op["staff"], "syllables": len(op["syllables"])})
        except DoricoError as exc:
            raise DoricoError(f"{exc}; {steps} undo step(s) were applied (undo that many to revert)") from exc
    outcome: dict[str, Any] = {"applied": len(results), "undoSteps": steps, "results": results}
    if lyrics:
        outcome["lyricsCheck"] = await _check_lyrics(bridge, lyrics, flow)
    return outcome


# Dorico's lyric popover is part of its UI: it needs Dorico frontmost and a
# moment to open, and each accepted syllable about 120 ms. Sent faster, the
# accepts run without effect (checked 2026-09-27).
POPOVER_OPEN_DELAY = 0.8
SYLLABLE_DELAY = 0.3


async def _type_lyrics(bridge: DoricoBridge, syllables: list[list[str]]) -> int:
    """Type syllables into the lyric popover at the selected note; return undo steps."""
    bring_to_front()
    await bridge.client.command("NoteInput.StartLyricInput")
    await asyncio.sleep(POPOVER_OPEN_DELAY)
    for text, kind in syllables:
        await bridge.client.command(
            f"NoteInput.AcceptCurrentLyricInput?LyricText={quote(text)}&LyricsEntryAdvanceType={kind}"
        )
        await asyncio.sleep(SYLLABLE_DELAY)
        if kind != score.END_INPUT:
            await bridge.client.command("NoteInput.AdvanceLyricInput")
            await asyncio.sleep(SYLLABLE_DELAY)
    return len(syllables)


async def _check_lyrics(bridge: DoricoBridge, ops: list[dict[str, Any]], flow: int) -> dict[str, Any]:
    """Compare the typed syllables with a MusicXML export of the staff."""
    xml = musicxml_read.read(await export_musicxml(bridge.client, flow))
    checks = []
    for op in ops:
        wanted = [text for text, _ in op["syllables"] if text]
        found = [
            lyric["text"]
            for e in sorted(xml["events"], key=lambda e: e["flowPosition"])
            if e["staff"] == op["staff"] and e["flowPosition"] >= op["position"]
            for lyric in e.get("lyrics", []) if lyric["verse"] == 1 and lyric["text"]
        ][: len(wanted)]
        checks.append({"staff": op["staff"], "ok": found == wanted, "expected": wanted, "found": found})
    return {"ok": all(c["ok"] for c in checks), "staves": checks}


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
