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
from typing import Any

from . import layout, musicxml_read, score
from .bridge import BarMap, DoricoBridge, fingerprint
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


async def snapshot(bridge: DoricoBridge, flow: int = 1, lyrics: bool = False, probe: bool = True) -> Snapshot:
    """Read a flow, exporting MusicXML only when Lua's view is not enough.

    Streams Lua cannot take events from (lyrics, tempo marks) are read from
    Dorico's dump() and keep their ids (source "dump"). When the voice layout
    cannot be settled from Lua, voices are placed by probing (probe_placements);
    MusicXML is exported only if that fails, a stream cannot even be dumped,
    bars cannot be measured, or `lyrics` asks for lyric text.
    """
    raw = (await bridge.overview(flow))["layout"]
    events, unreadable = await bridge.read_partial(flow)
    staves = None
    bars = None
    if not unreadable and not lyrics:
        # Bars first: if they cannot be measured the export is needed anyway,
        # and no probe edits should be spent.
        try:
            bars = await bridge.bars(flow, events)
        except DoricoError:
            bars = None
    if bars is not None:
        try:
            staves = layout.resolve(raw, events)
        except layout.NeedsMusicXML:
            staves = None
        if staves is None and probe:
            try:
                placements = await probe_placements(bridge, raw, events, flow)
                staves = layout.resolve(raw, events, placements=placements)
            except (layout.NeedsMusicXML, DoricoError):
                staves = None
    if staves is not None and bars is not None:
        placed = layout.assign(events, staves)
        placed_streams = {v for s in staves for v in s["voiceStreams"]}
        all_voices = {v for i in raw["instruments"] for v in i.get("voiceStreams") or []}
        return Snapshot(staves, score.locate_events(placed, bars), bars,
                        unplaced_voices=sorted(all_voices - placed_streams), raw=raw)

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
    if lyrics:
        _attach_lyrics(lua_located, xml["events"])
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


async def probe_placements(
    bridge: DoricoBridge, raw: dict[str, Any], events: list[dict[str, Any]], flow: int
) -> dict[int, int]:
    """The staff each voice's notes are on, found by probing.

    Lua has no link from a voice to its staff, but a dynamic created at a
    note goes into that staff's stave stream. So for each voice with a note:
    select the note, NoteInput.CreateDynamic, see which staff's stream got
    the new dynamic, and undo it and the selection. Like bar measurement,
    this edits the score briefly and clears the redo history, but leaves the
    undo history as it was, so reads do not shift the undo count of a batch.
    """
    client = bridge.client
    blocks = raw.get("blocks") or {}
    flows = await client.flows()
    flow_id = flows[flow - 1]["flowID"]
    voices = [v for instrument in raw["instruments"] for v in instrument.get("voiceStreams") or []]
    placements: dict[int, int] = {}
    for voice in voices:
        note = next((e for e in events if e.get("stream") == voice and e["type"] == "NoteEvent" and "id" in e), None)
        block = blocks.get(str(voice))
        if note is None or block is None:
            continue
        before = {e["id"] for e in events if e["type"] == "DynamicGroupEvent"}
        await client.command(f"EventEdit.Select?FlowID={flow_id}&EventID={note['id']}&EventBlockID={block}")
        await client.command("NoteInput.CreateDynamic?Definition=p")
        after, _ = await bridge.read_partial(flow)
        made = [e for e in after if e["type"] == "DynamicGroupEvent" and e["id"] not in before]
        if not made:
            raise DoricoError(f"the probe dynamic for voice {voice} was not created")
        await client.command("Edit.Undo")
        check, _ = await bridge.read_partial(flow)
        if any(e.get("id") == made[0]["id"] for e in check):
            raise DoricoError("the probe dynamic could not be undone; check the score")
        # Every EventEdit.Select is an undo step, even of a note already
        # selected, so undo it too; if that reverted anything else, redo it.
        await client.command("Edit.Undo")
        check, _ = await bridge.read_partial(flow)
        if fingerprint(check) != fingerprint(events):
            await client.command("Edit.Redo")
            raise DoricoError("undoing the probe selection changed the score; the undo was redone. Check the score.")
        placements[voice] = made[0]["staff"]
    return placements


def _attach_lyrics(located: list[dict[str, Any]], xml_events: list[dict[str, Any]]) -> None:
    """Give Lua-read notes the lyrics the MusicXML export has on the same note."""
    by_note = {
        (e["staff"], e["flowPosition"], e.get("pitch")): e["lyrics"]
        for e in xml_events if e.get("lyrics")
    }
    for event in located:
        if event.get("type") in score.TYPE_ALIASES["Note"]:
            found = by_note.get((event["staff"], event["flowPosition"], event.get("pitch")))
            if found:
                event["lyrics"] = found


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
    lyrics: bool = False,
) -> dict[str, Any]:
    snap = await snapshot(bridge, flow, lyrics=lyrics)
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
    # Decide on the resolved ops: set-pitch/delete/transpose on notes read
    # from dump() become command ops (repitch, delete-by-id).
    if any(op["op"] in score.COMMAND_OPS | score.ROUTED_COMMAND_OPS for op in prepared):
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
    add-lyrics is one step for the selection, one per verse below its own
    and one per syllable. The result reports how many steps to undo. Lyrics
    are checked afterwards against a MusicXML export, since Lua cannot read
    a staff with lyrics.
    """
    removals = [op for op in prepared if op["op"] == "delete"]
    commands = [op for op in prepared if op["op"] != "delete"]
    blocks = snap.raw.get("blocks") or {}
    for op in commands:
        for key in ("select", "anchor"):
            if key in op:
                block = blocks.get(str(op[key]["stream"]))
                if block is None:
                    raise DoricoError(f"cannot find the event block of stream {op[key]['stream']}; nothing was changed")
                op[key]["block"] = block
    if removals:
        checked = await bridge.apply(removals, flow, dry_run=True)
        if "error" in checked:
            raise DoricoError(f"{checked['error']}; nothing was changed")
    planned = (1 if removals else 0) + sum(
        1 + (op["verse"] - 1) + len(op["syllables"]) if op["op"] == "add-lyrics"
        else COPY_STEPS + op["extendBars"] + ("tempRest" in op) if op["op"] == "copy-passage"
        else 2
        for op in commands
    )  # every other command op is its selection plus one command (repitch may add respells)
    await _plan_lyrics(bridge, [op for op in commands if op["op"] == "add-lyrics"], flow)
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
            if op["op"] == "copy-passage":
                done, result = await _copy_passage(bridge, op, flow, flow_id, blocks)
                steps += done
                results.append(result)
                continue
            if op["op"] == "delete-by-id":
                await bridge.client.command(
                    f"EventEdit.Delete?FlowID={flow_id}&EventID={target['id']}&EventBlockID={target['block']}"
                )
                steps += 2  # EventEdit.Delete is two undo steps (measured 2026-09-27)
                events, _ = await bridge.read_partial(flow)
                if any(e.get("id") == target["id"] for e in events):
                    raise DoricoError(f"Dorico did not delete event {target['id']}")
                results.append({"op": "delete", "id": target["id"], "via": "command"})
                continue
            await bridge.client.command(
                f"EventEdit.Select?FlowID={flow_id}&EventID={target['id']}&EventBlockID={target['block']}"
            )
            steps += 1  # the selection is an undo step of its own
            if op["op"] == "repitch":
                done, result = await _repitch(bridge, op, flow)
                steps += done
                results.append(result)
            elif op["op"] == "set-break":
                await bridge.client.command("Edit.CreateSystemBreak")
                events, _ = await bridge.read_partial(flow)
                made = [e for e in events if e["type"] == "BreakEvent" and e["position"] == op["position"]]
                if not made:
                    raise DoricoError(f"Dorico made no break at bar {op['bar']}")
                steps += 1
                results.append({"op": "set-break", "type": "system", "bar": op["bar"], "id": made[0]["id"]})
            elif op["op"] in {"set-time", "set-key", "set-barline"}:
                before = {e["id"] for e in (await bridge.read_partial(flow))[0]}
                await bridge.client.command(f"{op['command']}?Definition={op['definition']}")
                events, _ = await bridge.read_partial(flow)
                made = [e for e in events if e["id"] not in before and e["type"] == op["expect"]
                        and e["position"] == op["position"]]
                if not made:
                    raise DoricoError(f"Dorico made no {op['op'][4:]} change at bar {op['bar']} ({op['definition']})")
                steps += 1
                results.append({"op": op["op"], "bar": op["bar"], "definition": op["definition"], "id": made[0]["id"]})
            elif op["op"] in score.NOTE_COMMAND_OPS:
                results.append(await _run_note_command(bridge, op, flow))
                steps += 1
            else:
                steps += await _type_lyrics(bridge, op["syllables"], op["keep"])
                lyrics.append(op)
                results.append({"op": "add-lyrics", "staff": op["staff"], "verse": op["verse"],
                                "syllables": len(op["syllables"])})
        except DoricoError as exc:
            raise DoricoError(f"{exc}; {steps} undo step(s) were applied (undo that many to revert)") from exc
    outcome: dict[str, Any] = {"applied": len(results), "undoSteps": steps, "results": results}
    if lyrics:
        outcome["lyricsCheck"] = await _check_lyrics(bridge, lyrics, flow)
    return outcome


LETTERS = "CDEFGAB"
#: Undo steps of one copy-passage staff before extension and temporary rest:
#: select, SelectMore, select anchor, paste (measured 2026-09-27).
COPY_STEPS = 4


async def _copy_passage(
    bridge: DoricoBridge, op: dict[str, Any], flow: int, flow_id: Any, blocks: dict[str, Any]
) -> tuple[int, dict[str, Any]]:
    """Copy one staff's bars by selection, Edit.Copy and Edit.Paste; check the notes."""
    client = bridge.client
    steps = 0
    anchor = op.get("anchor")
    if anchor is None:
        rest = op["tempRest"]
        made = await bridge.apply([{"op": "add-rest", **rest}], flow)
        if "error" in made:
            raise DoricoError(f"could not place the paste anchor: {made['error']}")
        steps += 1
        anchor = {"id": made["results"][0]["after"]["id"], "stream": rest["stream"],
                  "block": blocks.get(str(rest["stream"]))}
    source = op["select"]
    await client.command(f"EventEdit.Select?FlowID={flow_id}&EventID={source['id']}&EventBlockID={source['block']}")
    await client.command("Edit.SelectMore")
    for _ in range(op["extendBars"]):
        await client.command("EventEdit.NavigateRightExtendBar")
    await client.command("Edit.Copy")
    mode = (await client.status()).get("noteInputMode")
    await client.command(f"EventEdit.Select?FlowID={flow_id}&EventID={anchor['id']}&EventBlockID={anchor['block']}")
    if mode != "kOverwrite":
        await client.command("NoteInput.Mode?NoteInputMode=kOverwrite")
    try:
        await client.command("Edit.Paste")
    finally:
        if mode and mode != "kOverwrite":
            await client.command(f"NoteInput.Mode?NoteInputMode={mode}")
    steps += COPY_STEPS + op["extendBars"]
    events, _ = await bridge.read_partial(flow)
    start = op["anchorPosition"]
    span = max(p for p, _ in op["expect"]) + 1
    pasted = sorted(
        (e["position"] - start, e.get("pitch")) for e in events
        if e.get("stream") == anchor["stream"] and e["type"] in ("NoteEvent", "GraceNoteEvent") and start <= e["position"] < start + span
    )
    ok = pasted == sorted(op["expect"])
    return steps, {"op": "copy-passage", "staff": op["staff"], "destStaff": op["destStaff"],
                   "notes": len(op["expect"]), "verified": ok, **({} if ok else {"found": pasted})}


async def _repitch(bridge: DoricoBridge, op: dict[str, Any], flow: int) -> tuple[int, dict[str, Any]]:
    """Move the selected note chromatically to newPitch, then respell to the
    asked letter; the note keeps its id and anything attached (lyrics).

    Returns the undo steps taken (not counting the selection) and the result.
    """
    shift = op["newPitch"] - op["oldPitch"]
    direction = "Up" if shift > 0 else "Down"
    await bridge.client.command(f"NoteEdit.Pitch{direction}Chromatic?count={abs(shift)}")
    steps = 1

    async def current() -> dict[str, Any]:
        events, _ = await bridge.read_partial(flow)
        note = next((e for e in events if e.get("id") == op["id"]), None)
        if note is None:
            raise DoricoError(f"note {op['id']} disappeared while changing its pitch")
        return note

    note = await current()
    for _ in range(2):
        name = note.get("name") or ""
        if not name or name[0] == op["letter"]:
            break
        up = (LETTERS.index(op["letter"]) - LETTERS.index(name[0])) % 7 == 1
        await bridge.client.command(f"NoteEdit.RespellUsingNoteName{'Above' if up else 'Below'}")
        steps += 1
        note = await current()
    if note.get("pitch") != op["newPitch"] or not (note.get("name") or "").startswith(op["letter"]):
        raise DoricoError(f"note {op['id']} reads {note.get('name')} ({note.get('pitch')}), not {op['letter']} ({op['newPitch']})")
    return steps, {"op": "set-pitch", "id": op["id"], "via": "command", "before": op.get("name"), "after": note.get("name")}


async def _run_note_command(bridge: DoricoBridge, op: dict[str, Any], flow: int) -> dict[str, Any]:
    """Run a note command on the selected note and check what can be checked."""
    before = {e["id"] for e in (await bridge.read_partial(flow))[0]}
    query = "&".join(f"{k}={v}" for k, v in op["parameters"].items())
    await bridge.client.command(op["command"] + (f"?{query}" if query else ""))
    events, _ = await bridge.read_partial(flow)
    result: dict[str, Any] = {"op": op["op"], "note": op["select"]["id"]}
    if "expect" in op:
        made = [e for e in events if e["id"] not in before and e["type"] == op["expect"] and e["position"] == op["position"]]
        if not made:
            raise DoricoError(f"Dorico made no {op['expect']} at the note ({op['op']})")
        result["id"] = made[0]["id"]
    elif op["op"] == "set-articulation" and op.get("checkable"):
        note = next((e for e in events if e.get("id") == op["select"]["id"]), {})
        if op["articulation"] not in (note.get("articulations") or []):
            raise DoricoError(f"the note does not show {op['articulation']} after SetArticulation")
        result["articulations"] = note.get("articulations")
    else:
        result["verified"] = False  # slurs, and articulations on dump-read notes, are not visible to Lua
    return result


# Dorico's lyric popover is part of its UI: it needs Dorico frontmost and a
# moment to open, and each accepted syllable about 120 ms. Sent faster, the
# accepts run without effect (checked 2026-09-27).
POPOVER_OPEN_DELAY = 0.8
SYLLABLE_DELAY = 0.3


async def _plan_lyrics(bridge: DoricoBridge, ops: list[dict[str, Any]], flow: int) -> None:
    """Give each add-lyrics op the text to keep at its first note in each lower verse.

    Moving the popover down a verse accepts its current text, and an empty
    accept deletes the lyric there, so the text of verses 1..verse-1 at the
    first note is sent back unchanged. A staff without lyrics has none to
    keep. On a staff with lyrics they are read from a MusicXML export, and
    the batch is refused if a syllable would land on a note that already
    has a lyric in that verse (typing would replace it).
    """
    for op in ops:
        op["keep"] = [""] * (op["verse"] - 1)
    with_lyrics = [op for op in ops if op["hasLyrics"]]
    if not with_lyrics:
        return
    snap = await snapshot(bridge, flow, lyrics=True)
    for op in with_lyrics:
        by_position: dict[int, list[dict[str, Any]]] = {}
        for e in snap.located:
            if e.get("stream") == op["select"]["stream"] and e["type"] in score.TYPE_ALIASES["Note"] \
                    and e["flowPosition"] >= op["position"]:
                by_position.setdefault(e["flowPosition"], []).extend(e.get("lyrics", []))
        positions = sorted(by_position)[: len(op["syllables"])]
        first = {lyric["verse"]: lyric["text"] for lyric in by_position.get(op["position"], [])}
        op["keep"] = [first.get(verse, "") for verse in range(1, op["verse"])]
        for text in op["keep"]:
            score.command_value(text)  # refuses text a command cannot carry
        taken = [p for p in positions if any(lyric["verse"] == op["verse"] for lyric in by_position[p])]
        if taken:
            bar, offset = snap.bars.locate(taken[0])
            raise DoricoError(
                f"staff {op['staff']} already has a verse {op['verse']} lyric at bar {bar} "
                f"(position {offset}) where these lyrics would go; nothing was changed"
            )


async def _type_lyrics(bridge: DoricoBridge, syllables: list[list[str]], keep: list[str]) -> int:
    """Type syllables into the lyric popover at the selected note; return undo steps.

    keep holds the text already at that note in each verse below the target;
    each is accepted again with kIncrementVerseNumber to move down a line.
    """
    bring_to_front()
    await bridge.client.command("NoteInput.StartLyricInput")
    await asyncio.sleep(POPOVER_OPEN_DELAY)
    for text in keep:
        lyric = f"LyricText={score.command_value(text)}&" if text else ""
        await bridge.client.command(f"NoteInput.AcceptCurrentLyricInput?{lyric}LyricsEntryAdvanceType={score.NEXT_VERSE}")
        await asyncio.sleep(SYLLABLE_DELAY)
        await bridge.client.command("NoteInput.AdvanceLyricInput")
        await asyncio.sleep(SYLLABLE_DELAY)
    for text, kind in syllables:
        await bridge.client.command(
            f"NoteInput.AcceptCurrentLyricInput?LyricText={score.command_value(text)}&LyricsEntryAdvanceType={kind}"
        )
        await asyncio.sleep(SYLLABLE_DELAY)
        if kind != score.END_INPUT:
            await bridge.client.command("NoteInput.AdvanceLyricInput")
            await asyncio.sleep(SYLLABLE_DELAY)
    return len(keep) + len(syllables)


async def _check_lyrics(bridge: DoricoBridge, ops: list[dict[str, Any]], flow: int) -> dict[str, Any]:
    """Compare the typed syllables, and the lower verses kept at the first note, with a MusicXML export."""
    xml = musicxml_read.read(await export_musicxml(bridge.client, flow))
    checks = []
    for op in ops:
        wanted = [text for text, _ in op["syllables"] if text]
        staff_events = sorted((e for e in xml["events"] if e["staff"] == op["staff"]), key=lambda e: e["flowPosition"])
        found = [
            lyric["text"]
            for e in staff_events if e["flowPosition"] >= op["position"]
            for lyric in e.get("lyrics", []) if lyric["verse"] == op["verse"] and lyric["text"]
        ][: len(wanted)]
        at_first = {lyric["verse"]: lyric["text"] for e in staff_events if e["flowPosition"] == op["position"]
                    for lyric in e.get("lyrics", [])}
        kept = [at_first.get(verse, "") for verse in range(1, op["verse"])]
        check = {"staff": op["staff"], "verse": op["verse"], "ok": found == wanted and kept == op["keep"],
                 "expected": wanted, "found": found}
        if op["keep"]:
            check.update(keptExpected=op["keep"], keptFound=kept)
        checks.append(check)
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
