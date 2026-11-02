"""Tests for the Dorico back end, with a fake Dorico instead of the real one."""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any

import pytest
from types import SimpleNamespace
import websockets

from ai_score_editing.dorico import bridge as bridge_mod
from ai_score_editing.dorico import score, service
from ai_score_editing.dorico.bridge import BarMap, DoricoBridge, fingerprint, lua_literal
from ai_score_editing.dorico.client import DoricoClient, DoricoError
from ai_score_editing.dorico.score import (
    DoricoBatchError,
    interval_of,
    locate_events,
    prepare_batch,
    query,
    resolve_staves,
    spelling_letter,
    transpose_spelled,
)
from ai_score_editing.token_store import TokenStore

STAVES = [
    {"staff": 1, "name": "Piano", "stream": 1, "voiceStreams": [2]},
    {"staff": 2, "name": "Piano", "stream": 3, "voiceStreams": [4]},
]


def note(id: int, position: int, pitch: int, name: str, duration: int = 256, stream: int = 2, staff: int = 1) -> dict[str, Any]:
    return {"id": id, "type": "NoteEvent", "stream": stream, "staff": staff, "voice": 1,
            "position": position, "duration": duration, "pitch": pitch, "name": name}


EVENTS = [
    {"id": 0, "type": "TonalityDivisionEvent", "stream": 0, "staff": 0, "position": 0, "duration": 0},
    {"id": 1, "type": "BarDivisionEvent", "stream": 0, "staff": 0, "position": 0, "duration": 0},
    note(3, 0, 72, "C5"), note(4, 256, 71, "B4"), note(5, 512, 69, "A4"), note(6, 768, 67, "G4"),
    note(7, 1024, 65, "F4"), note(8, 1280, 64, "E4"),
]
BARS = BarMap([(0, 1024)])


# ------------------------------------------------------------------ Lua literals

def test_lua_literal_escapes_and_nests() -> None:
    text = lua_literal({"a": 'say "hi"\\\n', "b": [1, 2.5, True], "c": None, "d": {"e": False}})
    assert text == '{["a"] = "say \\"hi\\"\\\\\\n", ["b"] = {1, 2.5, true}, ["d"] = {["e"] = false}}'


def test_lua_literal_rejects_nil_in_arrays_and_control_codes_escaped() -> None:
    with pytest.raises(ValueError):
        lua_literal([1, None])
    assert lua_literal("a\x01b") == '"a\\001b"'


# ------------------------------------------------------------------ bars

def test_bar_map_with_a_time_change() -> None:
    bars = BarMap([(0, 1024), (2048, 768)])  # two 4/4 bars, then 3/4
    assert bars.segments() == [(1, 0, 1024), (3, 2048, 768)]
    assert bars.locate(1500) == (2, 476)
    assert bars.locate(2048 + 768 + 10) == (4, 10)
    assert bars.position(4, 10) == 2048 + 768 + 10
    assert bars.bar_length(3) == 768
    with pytest.raises(DoricoError):
        bars.position(3, 800)


def test_locate_events_indexes_per_staff_and_bar() -> None:
    located = locate_events(EVENTS, BARS)
    bar2 = [e for e in located if e["staff"] == 1 and e["bar"] == 2]
    assert [(e["id"], e["index"], e["position"], e["flowPosition"]) for e in bar2] == [(7, 0, 0, 1024), (8, 1, 256, 1280)]


# ------------------------------------------------------------------ spelling

def test_spelling_letters() -> None:
    assert spelling_letter(70) == "B"          # Bb by default
    assert spelling_letter(70, "A#") == "A"
    with pytest.raises(DoricoBatchError):
        spelling_letter(70, "B")


def test_transpose_spelled_keeps_letters_moving_diatonically() -> None:
    steps, semis = interval_of({"fromNote": "C", "toNote": "D", "direction": "up"}, "op")
    assert (steps, semis) == (1, 2)
    assert transpose_spelled("B4", 71, steps, semis) == (73, "C")   # C#5
    assert transpose_spelled("Eb4", 63, steps, semis) == (65, "F")
    steps, semis = interval_of({"fromNote": "C", "toNote": "A", "direction": "down", "octaves": 1}, "op")
    assert (steps, semis) == (-9, -15)
    with pytest.raises(DoricoBatchError):
        transpose_spelled("Bx4", 73, 0, 2)  # would need a triple sharp


# ------------------------------------------------------------------ query

def test_query_filters_and_type_aliases() -> None:
    located = locate_events(EVENTS, BARS)
    result = query(located, types=["NoteRest"], from_bar=1, to_bar=1, where=["Pitch>=69"])
    assert [o["id"] for o in result["objects"]] == [3, 4, 5]
    assert query(located, staves={0}, types=["TimeSignature"])["count"] == 1
    assert query(located)["count"] == 6  # the timebase is only included when asked for
    assert query(located, where=["Name='E4'"])["objects"][0]["id"] == 8


def test_resolve_staves_by_number_and_name() -> None:
    assert resolve_staves(["piano"], STAVES) == {1, 2}
    assert resolve_staves(["2", "system"], STAVES) == {0, 2}
    with pytest.raises(DoricoBatchError):
        resolve_staves(["Flute"], STAVES)


# ------------------------------------------------------------------ batches

def test_prepare_batch_resolves_addresses_and_spells() -> None:
    located = locate_events(EVENTS, BARS)
    ops = prepare_batch(
        [
            {"op": "set-pitch", "staff": 1, "bar": 2, "index": 1, "type": "NoteRest", "position": 256,
             "oldPitch": 64, "newPitch": 66, "spelling": "Gb"},
            {"op": "add-note", "staff": 2, "bar": 2, "position": 512, "duration": 256, "pitches": [48, 51]},
            {"op": "delete", "id": 3},
            {"op": "add-clef", "staff": 2, "bar": 2, "position": 0, "clef": "treble"},
        ],
        located, STAVES, BARS,
    )
    assert ops[0] == {"op": "set-pitch", "stream": 2, "id": 8, "type": "NoteEvent", "position": 1280,
                      "oldPitch": 64, "newPitch": 66, "letter": "G"}
    assert ops[1] == {"op": "add-note", "stream": 4, "position": 1536, "duration": 256,
                      "pitches": [48, 51], "letters": ["C", "E"]}
    assert ops[2]["id"] == 3 and ops[2]["position"] == 0
    assert ops[3] == {"op": "add-clef", "stream": 3, "position": 1024, "clef": "clef.treble"}


def test_a_lyric_melisma_across_the_barline_drags_in_the_next_bar() -> None:
    bars = BarMap([(0, 1024)])
    events = [
        {"id": 0, "type": "BarDivisionEvent", "stream": 0, "staff": 0, "position": 0, "duration": 0},
        note(3, 0, 72, "C5", duration=1024), note(4, 1024, 71, "B4", duration=1024), note(5, 2048, 69, "A4", duration=1024),
        {"id": 9, "type": "LyricEvent", "stream": 2, "staff": 1, "voice": 1, "position": 1024, "duration": 1536},
    ]
    located = locate_events(events, bars)
    # One step from bar 1 reaches bar 2's end, but the melisma runs on into bar 3.
    assert score._extension_plan(located, bars, 1, 2) is None
    assert score._extension_plan([e for e in located if e["type"] != "LyricEvent"], bars, 1, 2)["extend"] == 1  # without the lyric it is exact
    assert score._extension_plan(located, bars, 1, 3)["extend"] == 1


@pytest.mark.parametrize(
    ("operation", "message"),
    [
        ({"op": "set-pitch", "staff": 1, "bar": 1, "index": 0, "oldPitch": 60, "newPitch": 61}, "has pitch 72"),
        ({"op": "delete", "staff": 1, "bar": 1, "index": 0, "position": 256}, "at position 0"),
        ({"op": "delete", "staff": 1, "bar": 9, "index": 0}, "nothing at staff 1 bar 9"),
        ({"op": "add-note", "staff": 1, "voice": 2, "bar": 1, "position": 0, "duration": 256, "pitches": [60]}, "1 voice"),
        ({"op": "add-rest", "staff": 1, "bar": 1, "position": 1024, "duration": 256}, "outside bar 1"),
        ({"op": "frobnicate"}, "must be one of"),
        ({"op": "add-clef", "staff": 1, "bar": 1, "position": 0, "clef": "alto"}, "clef must be one of"),
    ],
)
def test_prepare_batch_refuses(operation: dict[str, Any], message: str) -> None:
    with pytest.raises(DoricoBatchError, match=message):
        prepare_batch([operation], locate_events(EVENTS, BARS), STAVES, BARS)


def test_prepare_batch_refuses_two_changes_to_one_event() -> None:
    with pytest.raises(DoricoBatchError, match="already changes"):
        prepare_batch(
            [
                {"op": "delete", "id": 5},
                {"op": "transpose", "fromBar": 1, "toBar": 1, "topStaff": 1, "bottomStaff": 1,
                 "semitones": 2},
            ],
            locate_events(EVENTS, BARS), STAVES, BARS,
        )


def test_transpose_expands_to_spelled_set_pitch() -> None:
    ops = prepare_batch(
        [{"op": "transpose", "fromBar": 2, "toBar": 2, "topStaff": 1, "bottomStaff": 1,
          "fromNote": "C", "toNote": "Eb", "direction": "up"}],
        locate_events(EVENTS, BARS), STAVES, BARS,
    )
    assert [(o["id"], o["newPitch"], o["letter"]) for o in ops] == [(7, 68, "A"), (8, 67, "G")]


# ------------------------------------------------------------------ client

class FakeDorico:
    """A local WebSocket server that answers like Dorico's Remote Control API."""

    def __init__(self, token: str = "tok-1") -> None:
        self.token = token
        self.received: list[dict[str, Any]] = []
        self.on_command = lambda command: None

    async def handler(self, ws: Any) -> None:
        async for raw in ws:
            message = json.loads(raw)
            self.received.append(message)
            kind = message["message"]
            if kind == "connect":
                if message.get("sessionToken") == self.token:
                    await ws.send(json.dumps({"message": "response", "code": "kConnected"}))
                    await ws.send(json.dumps({"message": "status", "canUndo": True, "notReadOnly": True}))
                else:
                    await ws.send(json.dumps({"message": "sessiontoken", "sessionToken": self.token}))
            elif kind == "acceptsessiontoken":
                await ws.send(json.dumps({"message": "response", "code": "kConnected"}))
                await ws.send(json.dumps({"message": "status", "canUndo": True, "notReadOnly": True}))
            elif kind == "getstatus":
                # Like Dorico: only fields that changed since the last status.
                await ws.send(json.dumps({"message": "selectionchanged"}))
                await ws.send(json.dumps({"message": "status", "hasSelection": True}))
            elif kind == "command":
                self.on_command(message["command"])
                await ws.send(json.dumps({"message": "response", "code": "kOK"}))


@pytest.fixture
async def dorico(tmp_path: Path) -> Any:
    fake = FakeDorico()
    async with websockets.serve(fake.handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        yield fake, port, TokenStore(tmp_path / "tokens.json")


async def test_client_first_connect_stores_the_approved_token(dorico: Any) -> None:
    fake, port, store = dorico
    async with DoricoClient(port=port, client_name="t", store=store) as client:
        status = await client.status()
        assert status["canUndo"] is True and status["hasSelection"] is True  # merged
    assert store.load("127.0.0.1#t", port).token == "tok-1"
    assert [m["message"] for m in fake.received[:2]] == ["connect", "acceptsessiontoken"]


async def test_client_reuses_token_and_refuses_prompt_when_asked(dorico: Any) -> None:
    fake, port, store = dorico
    with pytest.raises(DoricoError, match="no approved Dorico session"):
        await DoricoClient(port=port, client_name="t", store=store, allow_approval=False).connect()
    store.save("127.0.0.1#t", port, "tok-1")
    async with DoricoClient(port=port, client_name="t", store=store, allow_approval=False):
        pass
    assert fake.received[-1]["sessionToken"] == "tok-1"


async def test_bridge_call_round_trips_through_a_response_file(dorico: Any, tmp_path: Path) -> None:
    fake, port, store = dorico
    store.save("127.0.0.1#t", port, "tok-1")

    def run_script(command: str) -> None:
        request = Path(command.split("ScriptPath=", 1)[1]).read_text()
        response = re.search(r'BRIDGE_RESPONSE = "([^"]+)"', request).group(1)
        assert 'BRIDGE_REQUEST = {["action"] = "overview", ["flow"] = 1}' in request
        Path(response).write_text(json.dumps({"ok": True, "result": {"title": "T"}}))

    fake.on_command = run_script
    async with DoricoClient(port=port, client_name="t", store=store) as client:
        result = await DoricoBridge(client, workdir=tmp_path / "work").overview()
    assert result == {"title": "T"}
    assert list((tmp_path / "work").iterdir()) == []  # request and response cleaned up


# ------------------------------------------------------------------ bar measurement guard

class ScriptedBridge(DoricoBridge):
    """A bridge whose Dorico calls are scripted, for the measure-and-undo guard."""

    def __init__(self, reads: list[list[dict[str, Any]]], divisions: list[dict[str, Any]] | None = None) -> None:
        self.client = self  # type: ignore[assignment]
        self.workdir = Path("/nonexistent")
        self._bars = {}
        self.reads = reads
        self.divisions = divisions or [{"position": 0, "length": 768}]
        self.commands: list[str] = []

    async def status(self) -> dict[str, Any]:
        return {"notReadOnly": True, "canUndo": True}

    async def command(self, command: str) -> None:
        self.commands.append(command)

    async def call(self, action: str, **params: Any) -> Any:
        if action == "read":
            return {"events": self.reads.pop(0)}
        assert action == "bars"
        return {"divisions": self.divisions, "created": len(self.divisions)}


async def test_bar_measurement_is_undone_and_cached() -> None:
    bridge = ScriptedBridge([EVENTS])
    first = await bridge.bars(1, EVENTS)
    assert first.divisions == [(0, 768)]
    assert bridge.commands == ["Edit.Undo"]
    assert await bridge.bars(1, EVENTS) is first
    assert bridge.commands == ["Edit.Undo"]


async def test_a_division_that_keeps_the_meter_adds_no_run() -> None:
    # A bar number change at bar 3, measured in a free voice: same length.
    bridge = ScriptedBridge([EVENTS], [{"position": 0, "length": 1024, "next": 1024},
                                       {"position": 2048, "length": 1024, "next": 1024}])
    bars = await bridge.bars(1, EVENTS)
    assert bars.divisions == [(0, 1024), (2048, 1024)]
    assert bars.locate(2048 + 1024 + 5) == (4, 5)


async def test_a_pickup_is_a_bar_of_its_own() -> None:
    # 4/4 with a two-beat pick-up (4/4,2): the bar rest there measures 512.
    bridge = ScriptedBridge([EVENTS], [{"position": 0, "length": 512, "next": 1024}])
    bars = await bridge.bars(1, EVENTS)
    assert bars.segments() == [(1, 0, 512), (2, 512, 1024)]
    assert bars.locate(512 + 1024 + 256) == (3, 256)
    assert bars.bar_length(1) == 512


async def test_a_repeat_part_way_through_a_bar_splits_it() -> None:
    # An end repeat on beat 3 of bar 2 (measured live, 2026-09-28): the bar
    # after it measures 512, the one after that the meter again.
    bridge = ScriptedBridge([EVENTS], [{"position": 0, "length": 1024, "next": 1024},
                                       {"position": 1536, "length": 512, "next": 1024}])
    bars = await bridge.bars(1, EVENTS)
    assert bars.segments() == [(1, 0, 1024), (3, 1536, 512), (4, 2048, 1024)]
    assert [bars.bar_length(b) for b in (1, 2, 3, 4)] == [1024, 512, 512, 1024]
    assert bars.locate(1536) == (3, 0) and bars.locate(2560) == (4, 512)
    with pytest.raises(DoricoError, match="512 long"):
        bars.position(2, 512)


async def test_an_unmeasurable_bar_is_refused() -> None:
    bridge = ScriptedBridge([EVENTS], [{"position": 0, "length": 0}])
    with pytest.raises(DoricoError, match="could not measure the bar at 0"):
        await bridge.bars(1, EVENTS)


def test_musicxml_pickup_and_split_bars_keep_their_length() -> None:
    from ai_score_editing.dorico import musicxml_read

    # Dorico's export of 4/4 with a two-beat pick-up, a start repeat on beat 3
    # of bar 1 and an end repeat on beat 3 of bar 2: only the later part of
    # each split bar is marked implicit.
    xml = musicxml_read.read(Path(__file__).parent / "fixtures" / "dorico-pickup-split-bars.musicxml")
    lengths = [xml["bars"].bar_length(b) for b in range(1, xml["barCount"] + 1)]
    assert lengths == [512, 512, 512, 512, 512, 1024, 1024]


async def test_bar_measurement_redoes_if_the_undo_hit_something_else() -> None:
    changed = [dict(e) for e in EVENTS]
    changed[2]["pitch"] = 60
    bridge = ScriptedBridge([changed])
    with pytest.raises(DoricoError, match="undo was redone"):
        await bridge.bars(1, EVENTS)
    assert bridge.commands == ["Edit.Undo", "Edit.Redo"]
    assert fingerprint(EVENTS) != fingerprint(changed)


async def test_undo_stops_when_nothing_is_left() -> None:
    class Client:
        def __init__(self) -> None:
            self.left = 1
            self.commands: list[str] = []

        async def status(self) -> dict[str, Any]:
            return {"canUndo": self.left > 0}

        async def command(self, command: str) -> None:
            self.commands.append(command)
            self.left -= 1

    class Bridge:
        client = Client()

    result = await service.undo(Bridge(), 3)  # type: ignore[arg-type]
    assert result == {"undone": 1, "requested": 3}


def test_bridge_lua_ships_with_the_package() -> None:
    script = bridge_mod.bridge_script()
    assert script.exists() and "BRIDGE_VERSION" in script.read_text()


# ------------------------------------------------------------------ MusicXML fallback

MUSICXML = """<?xml version="1.0"?>
<score-partwise version="4.0">
  <part-list>
    <score-part id="P1"><part-name>Alto</part-name></score-part>
    <score-part id="P2"><part-name>Tenor</part-name></score-part>
  </part-list>
  <part id="P1">
    <measure number="0" implicit="yes">
      <attributes><divisions>2</divisions><key><fifths>1</fifths></key>
        <time><beats>4</beats><beat-type>4</beat-type></time></attributes>
      <note><pitch><step>D</step><octave>4</octave></pitch><duration>1</duration><voice>1</voice>
        <lyric number="1"><syllabic>single</syllabic><text>Oh</text></lyric></note>
    </measure>
    <measure number="1">
      <note><pitch><step>F</step><alter>1</alter><octave>4</octave></pitch><duration>4</duration><voice>1</voice>
        <lyric number="1"><syllabic>begin</syllabic><text>fare</text></lyric></note>
      <note><chord/><pitch><step>A</step><octave>4</octave></pitch><duration>4</duration><voice>1</voice></note>
      <note><rest/><duration>4</duration><voice>1</voice></note>
    </measure>
  </part>
  <part id="P2">
    <measure number="0" implicit="yes">
      <attributes><divisions>2</divisions><staves>2</staves></attributes>
      <note><rest/><duration>1</duration><voice>1</voice><staff>1</staff></note>
      <backup><duration>1</duration></backup>
      <note><rest/><duration>1</duration><voice>5</voice><staff>2</staff></note>
    </measure>
    <measure number="1">
      <note><rest measure="yes"/><duration>8</duration><voice>1</voice><staff>1</staff></note>
      <backup><duration>8</duration></backup>
      <note><pitch><step>B</step><alter>-1</alter><octave>2</octave></pitch><duration>8</duration><voice>5</voice><staff>2</staff></note>
    </measure>
  </part>
</score-partwise>
"""


def test_musicxml_read_staves_bars_lyrics(tmp_path: Path) -> None:
    from ai_score_editing.dorico import musicxml_read

    path = tmp_path / "s.musicxml"
    path.write_text(MUSICXML)
    data = musicxml_read.read(path)
    assert [s["name"] for s in data["staves"]] == ["Alto", "Tenor", "Tenor"]
    assert data["bars"].segments() == [(1, 0, 128), (2, 128, 1024)]
    assert data["keySignatures"] == [{"bar": 1, "fifths": 1, "key": "G", "minor": False}]
    alto = [e for e in data["events"] if e["staff"] == 1]
    assert [(e["bar"], e["index"], e["position"], e.get("name"), e["flowPosition"]) for e in alto] == [
        (1, 0, 0, "D4", 0), (2, 0, 0, "F#4", 128), (2, 1, 0, "A4", 128), (2, 2, 512, None, 640),
    ]
    assert alto[1]["lyrics"] == [{"verse": 1, "text": "fare", "syllabic": "begin"}]
    bass = [e for e in data["events"] if e["staff"] == 3]
    assert [(e["type"], e.get("name"), e["voice"]) for e in bass] == [("RestEvent", None, 1), ("NoteEvent", "Bb2", 1)]


async def test_snapshot_fills_unreadable_staves_from_musicxml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "s.musicxml"
    path.write_text(MUSICXML)

    async def fake_export(client: Any, flow: int = 1) -> Path:
        return path

    monkeypatch.setattr(service, "export_musicxml", fake_export)

    class Bridge:
        client = None

        async def read_partial(self, flow: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
            # Lua gives voice events no staff; the Tenor's one voice on two
            # staves must be placed by matching the MusicXML.
            tenor_note = {**note(40, 128, 46, "Bb2", duration=1024, stream=9), "staff": None, "voice": None}
            return [tenor_note], [{"stream": 5, "staff": None, "voice": None}]

        async def overview(self, flow: int) -> dict[str, Any]:
            return {"layout": {
                "staves": [{"stream": 1}, {"stream": 3}, {"stream": 4}],
                "instruments": [{"id": 0, "name": "Alto", "voiceStreams": [5]},
                                {"id": 1, "name": "Tenor", "voiceStreams": [9]}],
            }}

    snap = await service.snapshot(Bridge(), 1)  # type: ignore[arg-type]
    assert snap.unreadable_staves == [1]
    assert [s["voiceStreams"] for s in snap.staves] == [[5], [], [9]]
    alto = [e for e in snap.located if e["staff"] == 1]
    assert all(e["source"] == "musicxml" and "id" not in e for e in alto)
    tenor = [e for e in snap.located if e["staff"] == 3]
    assert [(e["id"], e["bar"], e["position"]) for e in tenor] == [(40, 2, 0)]  # Lua event, MusicXML bars
    with pytest.raises(DoricoBatchError, match="read from a MusicXML export"):
        prepare_batch([{"op": "delete", "staff": 1, "bar": 2, "index": 0}], snap.located,
                      [{"staff": 1, "voiceStreams": [5]}], snap.bars)
    ops = prepare_batch([{"op": "add-note", "staff": 1, "bar": 2, "position": 256, "duration": 256, "pitches": [62]}],
                        snap.located, [{"staff": 1, "voiceStreams": [5]}], snap.bars)
    assert ops[0]["position"] == 384


async def test_export_pdf_answers_overwrite_and_reads_path_from_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from ai_score_editing.dorico import export

    log = tmp_path / "application.log"
    log.write_text("old line\n")
    pdf = tmp_path / "01 - Full score - Song.pdf"
    clicked: list[tuple[str, ...]] = []

    async def fake_osascript(script: str, *args: str) -> str:
        if script is export._DIALOGS:
            return "" if clicked else "2\tOne or more output files already exist. Do you want to overwrite them?"
        clicked.append(args)
        pdf.write_bytes(b"%PDF")
        with log.open("a") as handle:
            handle.write(f"[info] Exporting PDF to {pdf}\n[info] notifyPostCommandExecute: Print.ExportCurrentLayoutAsPDF (4 ms)\n")
        return "clicked"

    class Client:
        commands: list[str] = []

        async def command(self, command: str) -> None:
            self.commands.append(command)

    monkeypatch.setattr(export, "osascript", fake_osascript)
    client = Client()
    assert await export.export_pdf(client, log) == pdf  # type: ignore[arg-type]
    assert client.commands == ["Print.ExportCurrentLayoutAsPDF"]
    assert clicked == [("2", "Overwrite")]



class _FakeOsascript:
    """Stands in for an osascript child process; never runs a real one."""

    def __init__(self, stdout: bytes = b"", stderr: bytes = b"", returncode: int = 0, hang: bool = False) -> None:
        self.stdout, self.stderr, self.hang = stdout, stderr, hang
        self.result = returncode
        self.returncode: int | None = None
        self.input: bytes | None = None
        self.killed = False
        self.waited = False

    async def communicate(self, data: bytes) -> tuple[bytes, bytes]:
        self.input = data
        if self.hang:
            await asyncio.sleep(3600)
        self.returncode = self.result
        return self.stdout, self.stderr

    def kill(self) -> None:
        self.killed = True

    async def wait(self) -> int:
        self.waited = True
        self.returncode = -9
        return -9


def _spawn(monkeypatch: pytest.MonkeyPatch, process: _FakeOsascript) -> list[tuple[Any, ...]]:
    from ai_score_editing import macos

    calls: list[tuple[Any, ...]] = []

    async def fake_exec(*args: Any, **kwargs: Any) -> _FakeOsascript:
        calls.append(args)
        assert kwargs["stdin"] == kwargs["stdout"] == kwargs["stderr"] == asyncio.subprocess.PIPE
        return process

    monkeypatch.setattr(macos.asyncio, "create_subprocess_exec", fake_exec)
    return calls


async def test_osascript_runs_without_blocking_and_decodes_like_text_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    from ai_score_editing.dorico import export

    process = _FakeOsascript(stdout="Titre\tSérénade\rsecond line\r\n".encode())
    calls = _spawn(monkeypatch, process)
    out = await export.osascript('tell process "%(process)s" to item 1 of argv', "a b", "c")
    assert calls == [("osascript", "-", "a b", "c")]
    assert process.input == 'tell process "Dorico 6" to item 1 of argv'.encode()
    assert out == "Titre\tSérénade\nsecond line"


@pytest.mark.parametrize(
    ("stderr", "message"),
    [
        (b"execution error: osascript is not allowed assistive access. (-1719)\n", "Accessibility permission"),
        (b"syntax error: oops (-2741)\n", r"UI scripting failed: syntax error: oops \(-2741\)$"),
    ],
)
async def test_osascript_failure_messages(monkeypatch: pytest.MonkeyPatch, stderr: bytes, message: str) -> None:
    from ai_score_editing.dorico import export

    _spawn(monkeypatch, _FakeOsascript(stderr=stderr, returncode=1))
    with pytest.raises(DoricoError, match=message):
        await export.osascript("script")


async def test_osascript_timeout_kills_the_child(monkeypatch: pytest.MonkeyPatch) -> None:
    import subprocess

    from ai_score_editing.dorico import export

    process = _FakeOsascript(hang=True)
    _spawn(monkeypatch, process)
    monkeypatch.setattr(export, "OSASCRIPT_TIMEOUT", 0.01)
    with pytest.raises(subprocess.TimeoutExpired):  # as subprocess.run raised, not an OSError
        await export.osascript("script", "x")
    assert process.killed and process.waited


async def test_osascript_cancellation_kills_the_child(monkeypatch: pytest.MonkeyPatch) -> None:
    from ai_score_editing.dorico import export

    process = _FakeOsascript(hang=True)
    _spawn(monkeypatch, process)
    task = asyncio.create_task(export.osascript("script"))
    await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert process.killed and process.waited


async def test_bridge_wait_for_polls_without_blocking(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    response = tmp_path / "response.json"

    async def answer_later() -> None:
        await asyncio.sleep(0.05)  # runs only if the poll yields to the event loop
        response.write_text(json.dumps({"ok": True}))

    writer = asyncio.create_task(answer_later())
    assert await DoricoBridge._wait_for(response) == {"ok": True}
    await writer
    monkeypatch.setattr(bridge_mod, "RESPONSE_TIMEOUT", 0.05)
    with pytest.raises(DoricoError, match="did not answer"):
        await DoricoBridge._wait_for(tmp_path / "never.json")


async def test_read_project_info_drives_the_dialog(monkeypatch: pytest.MonkeyPatch) -> None:
    from ai_score_editing.dorico import project_info

    state = {"open": False}
    scripts: list[tuple[str, ...]] = []

    async def fake_osascript(script: str, *args: str) -> str:
        scripts.append(args)
        if script is project_info._OPEN:
            return "yes" if state["open"] else "no"
        if script is project_info._READ:
            return "Title\tSong\nComposer\tMe\nNot a field\tx"
        if script is project_info._PRESS:
            state["open"] = False
            return "clicked"
        raise AssertionError(script)

    async def front() -> None:
        scripts.append(("front",))

    class Client:
        async def command(self, command: str) -> None:
            assert command == "File.ScoreInfo"
            state["open"] = True

    class Bridge:
        client = Client()

    monkeypatch.setattr(project_info, "osascript", fake_osascript)
    monkeypatch.setattr(project_info, "bring_to_front", front)
    assert await project_info.read_project_info(Bridge()) == {"Title": "Song", "Composer": "Me"}  # type: ignore[arg-type]
    assert ("front",) in scripts and ("Close",) in scripts and not state["open"]


# ------------------------------------------------------------------ voice layout

def test_layout_one_voice_per_stave_and_single_stave_instruments() -> None:
    from ai_score_editing.dorico import layout

    piano = {"staves": [{"stream": 1}, {"stream": 3}],
             "instruments": [{"id": 0, "name": "Piano", "voiceStreams": [4, 2]}]}
    assert [s["voiceStreams"] for s in layout.resolve(piano, [])] == [[2], [4]]
    choir = {"staves": [{"stream": 1}, {"stream": 3}],
             "instruments": [{"id": 0, "name": "S", "voiceStreams": [9, 5]}, {"id": 1, "name": "A", "voiceStreams": [7]}]}
    assert [(s["name"], s["voiceStreams"]) for s in layout.resolve(choir, [])] == [("S", [5, 9]), ("A", [7])]


def test_layout_extra_voice_needs_musicxml_and_is_placed_by_its_notes() -> None:
    from ai_score_editing.dorico import layout

    # A piano whose third voice (stream 7, made later) is on the treble staff:
    # id order alone would put it on the bass staff.
    raw = {"staves": [{"stream": 1}, {"stream": 3}],
           "instruments": [{"id": 0, "name": "Piano", "voiceStreams": [2, 4, 6, 7]}]}
    events = [
        {"stream": 2, "position": 0, "pitch": 72}, {"stream": 4, "position": 0, "pitch": 48},
        {"stream": 7, "position": 1024, "pitch": 72},
    ]
    with pytest.raises(layout.NeedsMusicXML):
        layout.resolve(raw, events)
    xml = {"staves": [{"staff": 1, "name": "Piano", "part": "P1"}, {"staff": 2, "name": "Piano", "part": "P1"}],
           "events": [{"staff": 1, "flowPosition": 0, "pitch": 72}, {"staff": 2, "flowPosition": 0, "pitch": 48},
                      {"staff": 1, "flowPosition": 1024, "pitch": 72}]}
    staves = layout.resolve(raw, events, xml)
    assert [s["voiceStreams"] for s in staves] == [[2, 7], [4]]  # empty voice 6 left out
    placed = layout.assign([{"stream": 7, "staff": None, "voice": None}, {"stream": 6, "staff": None}], staves)
    assert placed == [{"stream": 7, "staff": 1, "voice": 2}]


# ------------------------------------------------------------------ set-break

def test_set_break_selects_a_note_in_the_bar_and_removes_via_lua() -> None:
    located = locate_events(EVENTS + [
        {"id": 50, "type": "BreakEvent", "stream": 0, "staff": 0, "position": 2048, "duration": 0},
    ], BarMap([(0, 1024)]))
    ops = prepare_batch([{"op": "set-break", "bar": 2, "type": "system"},
                         {"op": "set-break", "bar": 3, "type": "none"}], located, STAVES, BARS)
    assert ops[0] == {"op": "set-break", "type": "system", "bar": 2, "position": 1024,
                      "select": {"id": 7, "stream": 2}}
    assert ops[1] == {"op": "delete", "stream": 0, "id": 50, "type": "BreakEvent", "position": 2048}


@pytest.mark.parametrize(
    ("batch", "message"),
    [
        ([{"op": "set-break", "bar": 2, "type": "none"}], "no break at bar 2"),
        ([{"op": "set-break", "bar": 2, "type": "system"}, {"op": "delete", "id": 3}], "cannot share a batch"),
    ],
)
def test_set_break_refusals(batch: list[dict[str, Any]], message: str) -> None:
    with pytest.raises(DoricoBatchError, match=message):
        prepare_batch(batch, locate_events(EVENTS, BARS), STAVES, BARS)


def test_set_break_in_an_empty_bar_uses_a_temporary_rest() -> None:
    break_at_5 = [{"op": "set-break", "bar": 5, "type": "system"}]
    ops = prepare_batch(break_at_5, locate_events(EVENTS, BARS), STAVES, BARS)
    assert "select" not in ops[0] and ops[0]["tempRest"] == {"stream": 2, "position": 4096, "duration": 256}
    held = EVENTS + [note(9, 3584, 60, "C4", duration=1024), note(10, 3840, 48, "C3", duration=512, stream=4, staff=2)]
    with pytest.raises(DoricoBatchError, match="every voice holds a note over its barline"):
        prepare_batch(break_at_5, locate_events(held, BARS), STAVES, BARS)


# ------------------------------------------------------------------ delete-voice, add-bars

def test_delete_voice_covers_whole_bars_and_runs_last() -> None:
    located = locate_events(EVENTS, BARS)
    ops = prepare_batch([{"op": "delete-voice", "staff": 1, "voice": 1, "fromBar": 1, "toBar": 2},
                         {"op": "set-pitch", "id": 3, "oldPitch": 72, "newPitch": 74}], located, STAVES, BARS)
    assert [o["op"] for o in ops] == ["set-pitch", "delete-voice"]
    assert ops[1] == {"op": "delete-voice", "stream": 2, "staff": 1, "voice": 1,
                      "fromBar": 1, "toBar": 2, "start": 0, "end": 2048}
    with pytest.raises(DoricoBatchError, match="has 1 voice"):
        prepare_batch([{"op": "delete-voice", "staff": 1, "voice": 2, "fromBar": 1, "toBar": 1}], located, STAVES, BARS)


def test_add_bars_inserts_at_the_bar_start_or_appends() -> None:
    located = locate_events(EVENTS, BARS)
    ops = prepare_batch([{"op": "add-bars", "count": 2, "bar": 2}], located, STAVES, BARS)
    assert ops == [{"op": "add-bars", "count": 2, "bar": 2, "position": 1024, "shift": 2048,
                    "select": {"id": 7, "stream": 2}}]
    ops = prepare_batch([{"op": "add-bars", "count": 1, "bar": 3}], located, STAVES, BARS)
    assert "select" not in ops[0] and ops[0]["tempRest"] == {"stream": 2, "position": 2048, "duration": 256}
    assert prepare_batch([{"op": "add-bars", "count": 3}], located, STAVES, BARS) == [{"op": "add-bars", "count": 3}]


def test_delete_bars_plans_an_exact_selection() -> None:
    located = locate_events(EVENTS, BARS)
    ops = prepare_batch([{"op": "delete-bars", "fromBar": 1, "toBar": 1}], located, STAVES, BARS)
    assert ops[0]["removed"] == 1024 and ops[0]["marker"]["position"] >= 1024
    assert ops[0]["plan"] == {"select": {"id": 3, "stream": 2}, "extend": 0, "staff": 1}
    ops = prepare_batch([{"op": "delete-bars", "fromBar": 2, "toBar": 2}], located, STAVES, BARS)
    assert ops[0]["plan"]["select"]["id"] == 7 and "marker" not in ops[0]
    with pytest.raises(DoricoBatchError, match="every bar"):
        prepare_batch([{"op": "delete-bars", "fromBar": 1, "toBar": 2}], located, STAVES, BARS)
    with pytest.raises(DoricoBatchError, match="names a bar after bar 0"):
        prepare_batch([{"op": "delete-bars", "fromBar": 1, "toBar": 1},
                       {"op": "set-break", "bar": 2, "type": "system"}], located, STAVES, BARS)


def test_delete_bars_plans_one_selection_per_staff_up_to_three() -> None:
    located = locate_events(EVENTS, BARS)
    plans = score._extension_plans(located, BARS, 1, 1)
    staves = [p["staff"] for p in plans]
    assert staves == sorted(set(staves)) and 1 <= len(plans) <= 3
    assert plans[0] == score._extension_plan(located, BARS, 1, 1)  # the old single choice comes first
    ops = prepare_batch([{"op": "delete-bars", "fromBar": 1, "toBar": 1}], located, STAVES, BARS)
    assert ops[0]["plans"] == plans and ops[0]["plan"] == plans[0]
    assert len(score._extension_plans(located, BARS, 1, 1, limit=1)) == 1


def test_a_tied_note_across_the_last_barline_drags_in_the_next_bar() -> None:
    """The measured rule: items starting before the barline are pulled in whole."""
    bars = BarMap([(0, 1024)])
    events = [
        {"id": 0, "type": "BarDivisionEvent", "stream": 0, "staff": 0, "position": 0, "duration": 0},
        note(3, 0, 72, "C5", duration=1024), note(4, 1024, 71, "B4", duration=1536),  # held into bar 3
        note(5, 2560, 69, "A4", duration=512), note(6, 3072, 67, "G4", duration=1024),
    ]
    located = locate_events(events, bars)
    one = score._extension_plan(located, bars, 1, 1)
    assert one == {"select": {"id": 3, "stream": 2}, "extend": 0, "staff": 1}
    # Bar 2's note runs into bar 3, so no selection on this staff covers bars 2-2 exactly:
    assert score._extension_plan(located, bars, 2, 2) is None
    # A copy needs every item that starts in the bars; the tie into bar 3 adds only a tail.
    assert score._extension_plan(located, bars, 1, 1, staff=1, cover=True)["extend"] == 0  # its only item
    assert score._extension_plan(located, bars, 1, 2, staff=1, cover=True)["extend"] == 1  # the step to bar 2's end
    assert score._extension_plan(located, bars, 2, 2, staff=1, cover=True)["extend"] == 0
    two = score._extension_plan(located, bars, 2, 3)
    assert two is not None and two["select"]["id"] == 4
    longer = score._extension_plan(located, bars, 1, 3)
    assert longer == {"select": {"id": 3, "stream": 2}, "extend": 1, "staff": 1}  # the tie reaches bar 3


@pytest.mark.parametrize(
    ("batch", "message"),
    [
        ([{"op": "add-bars", "count": 1, "bar": 2, "length": 768}], "length is not supported"),
        ([{"op": "add-bars", "count": 1001}], "count must be 1-1000"),
        ([{"op": "add-bars", "count": 1, "bar": 2}, {"op": "set-break", "bar": 3, "type": "system"}],
         "names a bar after bar 1, which an earlier op"),
        ([{"op": "add-bars", "count": 1}, {"op": "delete", "id": 3}], "cannot share a batch"),
        ([{"op": "delete-voice", "staff": 1, "voice": 1, "fromBar": 1, "toBar": 1},
          {"op": "add-bars", "count": 1}], "cannot share a batch"),
    ],
)
def test_add_bars_refusals(batch: list[dict[str, Any]], message: str) -> None:
    with pytest.raises(DoricoBatchError, match=message):
        prepare_batch(batch, locate_events(EVENTS, BARS), STAVES, BARS)


async def test_add_bars_past_the_end_of_the_flow_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    exports: list[int] = []

    async def export(client: Any, flow: int) -> Path:
        exports.append(flow)
        return Path("/nonexistent.musicxml")

    monkeypatch.setattr(service, "export_musicxml", export)
    monkeypatch.setattr(service.musicxml_read, "read", lambda path: {"barCount": 4})
    located = locate_events(EVENTS, BARS)  # music in bars 1-2
    snap = service.Snapshot(STAVES, located, BARS)
    bridge = SimpleNamespace(client=None)
    ops = prepare_batch([{"op": "add-bars", "count": 1, "bar": 4}], located, STAVES, BARS)
    await service._check_bars_exist(bridge, ops, snap, 1)  # type: ignore[arg-type]
    ops = prepare_batch([{"op": "add-bars", "count": 1, "bar": 6}], located, STAVES, BARS)
    with pytest.raises(DoricoError, match="past the end of the flow, which has 4 bars"):
        await service._check_bars_exist(bridge, ops, snap, 1)  # type: ignore[arg-type]
    ops = prepare_batch([{"op": "add-bars", "count": 1, "bar": 2}], located, STAVES, BARS)
    await service._check_bars_exist(bridge, ops, snap, 1)  # type: ignore[arg-type]
    assert exports == [1, 1]  # a bar with music needs no export


def test_ops_before_an_insert_or_at_earlier_bars_are_allowed() -> None:
    located = locate_events(EVENTS, BARS)
    ops = prepare_batch([{"op": "set-break", "bar": 3, "type": "system"},
                         {"op": "add-bars", "count": 1, "bar": 3},
                         {"op": "set-barline", "bar": 2, "type": "double"}], located, STAVES, BARS)
    assert [o["op"] for o in ops] == ["set-break", "add-bars", "set-barline"]


# ------------------------------------------------------------------ pick-ups, mid-bar barlines

def test_query_by_type_includes_global_items() -> None:
    located = locate_events(EVENTS, BARS)
    assert [o["id"] for o in query(located, types=["TimeSignature"])["objects"]] == [1]
    assert all(o["staff"] != 0 for o in query(located)["objects"])


def test_set_time_with_a_pickup_sends_beats_of_the_denominator() -> None:
    located = locate_events(EVENTS, BARS)
    cases = [((6, 4, 768), "6/4\\,3"), ((6, 8, 384), "6/8\\,3"), ((4, 4, 384), "4/4\\,1.5"), ((3, 4, 256), "3/4\\,1")]
    for (top, bottom, pickup), definition in cases:
        op = prepare_batch([{"op": "set-time", "bar": 1, "numerator": top, "denominator": bottom, "pickup": pickup}],
                           located, STAVES, BARS)[0]
        assert op["definition"] == definition
    with pytest.raises(DoricoBatchError, match="pickup must be 1-1023"):
        prepare_batch([{"op": "set-time", "bar": 1, "numerator": 4, "denominator": 4, "pickup": 1024}],
                      located, STAVES, BARS)


def test_set_barline_part_way_through_a_bar() -> None:
    located = locate_events(EVENTS, BARS)
    ops = prepare_batch([{"op": "set-barline", "bar": 1, "type": "end_repeat", "position": 512}], located, STAVES, BARS)
    assert ops[0]["select"] == {"id": 5, "stream": 2}
    assert ops[0]["position"] == 512 and ops[0]["offset"] == 512 and ops[0]["definition"] == ":|"
    ops = prepare_batch([{"op": "set-barline", "bar": 3, "type": "start_repeat", "position": 768}], located, STAVES, BARS)
    assert "select" not in ops[0] and ops[0]["tempRest"]["position"] == 2048 + 768
    with pytest.raises(DoricoBatchError, match="outside bar 1"):
        prepare_batch([{"op": "set-barline", "bar": 1, "type": "double", "position": 1024}], located, STAVES, BARS)


@pytest.mark.parametrize(
    "batch",
    [
        [{"op": "set-time", "bar": 2, "numerator": 2, "denominator": 4}, {"op": "set-barline", "bar": 3, "type": "double"}],
        [{"op": "set-barline", "bar": 1, "type": "end_repeat", "position": 512},
         {"op": "set-break", "bar": 2, "type": "system"}],
    ],
)
def test_ops_after_a_rebarring_op_may_not_name_moved_bars(batch: list[dict[str, Any]]) -> None:
    with pytest.raises(DoricoBatchError, match="which an earlier op in this batch moves"):
        prepare_batch(batch, locate_events(EVENTS, BARS), STAVES, BARS)


def test_ops_at_or_before_a_rebarred_bar_are_allowed() -> None:
    ops = prepare_batch([{"op": "set-time", "bar": 2, "numerator": 2, "denominator": 4},
                         {"op": "set-barline", "bar": 2, "type": "double"},
                         {"op": "set-key", "bar": 1, "key": "G"}], locate_events(EVENTS, BARS), STAVES, BARS)
    assert [o["op"] for o in ops] == ["set-time", "set-barline", "set-key"]


# ------------------------------------------------------------------ set-layout

LETTER_OPTIONS = {
    "pageSizeAndMarginOptions.pageWidth": "612", "pageSizeAndMarginOptions.pageHeight": "792",
    "defaultSpaceSize": "4.96", "pageSizeAndMarginOptions.pageMargins.type": "kIdentical",
    "pageSizeAndMarginOptions.pageMargins.margins.top": "42", "pageSizeAndMarginOptions.pageMargins.margins.bottom": "42",
    "pageSizeAndMarginOptions.pageMargins.margins.outer": "42", "pageSizeAndMarginOptions.pageMargins.margins.inner": "42",
    "pageSizeAndMarginOptions.defaultMusicFrameTopPadding": "40",
    "pageSizeAndMarginOptions.defaultMusicFrameBottomPadding": "30",
    "verticalStaveGapOptions.staveToStaveGap": "6", "verticalStaveGapOptions.interSystemGap": "10",
    "hideEmptyStavesPolicy": "kNever",
}


def _layout_options(batch: dict[str, Any], current: dict[str, str] = LETTER_OPTIONS) -> dict[str, str]:
    from ai_score_editing.dorico.score import layout_dictionary

    op = prepare_batch([{"op": "set-layout", **batch}], locate_events(EVENTS, BARS), STAVES, BARS)[0]
    return layout_dictionary(op["settings"], current, "op 0")


def test_layout_command_matches_what_layout_options_apply_sends() -> None:
    from ai_score_editing.dorico.score import layout_command

    # Logged from Layout Options' Apply after choosing Landscape (2026-09-28).
    logged = ('Project.Layout.SetOptions?LayoutIDArray=0&Dictionary=list: '
              '{string: "pageSizeAndMarginOptions.pageWidth"}\\, {string: "792.000000"}\\, '
              '{string: "pageSizeAndMarginOptions.pageHeight"}\\, {string: "612.000000"}&OpenScoreID=0')
    assert layout_command(0, 0, _layout_options({"orientation": "landscape"})) == logged


def test_set_layout_converts_to_dorico_units() -> None:
    options = _layout_options({"pageSize": "a4", "staffSize": 7, "topMargin": 20, "leftMargin": 15,
                               "rightMargin": 10, "spacesBetweenStaves": 9, "hideEmptyStaves": "all-systems"})
    assert options == {
        "pageSizeAndMarginOptions.pageWidth": "595.280000", "pageSizeAndMarginOptions.pageHeight": "841.890000",
        "defaultSpaceSize": "4.960630",  # a 7 mm staff: 1.75 mm spaces
        "pageSizeAndMarginOptions.pageMargins.margins.top": "56.692913",
        "pageSizeAndMarginOptions.pageMargins.margins.outer": "42.519685",  # left
        "pageSizeAndMarginOptions.pageMargins.margins.inner": "28.346457",  # right
        "verticalStaveGapOptions.staveToStaveGap": "9.000000",
        "hideEmptyStavesPolicy": "kAllSystems",
    }
    assert _layout_options({"pageSize": "a4", "orientation": "landscape"})["pageSizeAndMarginOptions.pageWidth"] == "841.890000"
    assert _layout_options({"pageWidth": 100, "pageHeight": 200}) == {
        "pageSizeAndMarginOptions.pageWidth": "283.464567", "pageSizeAndMarginOptions.pageHeight": "566.929134",
    }


@pytest.mark.parametrize(
    ("batch", "message"),
    [
        ({"pageSize": "b5"}, "ambiguous"),
        ({"pageSize": "huge"}, "pageSize must be one of"),
        ({"extraSpacesBelowVocalStaves": 2}, "no Layout Option in Dorico"),
        ({"staffSize": 40}, "staffSize must be a number from 1 to 30"),
        ({"pageWidth": 200}, "together"),
        ({"hideEmptyStaves": "sometimes"}, "hideEmptyStaves must be one of"),
        ({}, "at least one setting"),
        ({"margin": 3}, "unknown set-layout fields"),
    ],
)
def test_set_layout_refusals(batch: dict[str, Any], message: str) -> None:
    with pytest.raises(DoricoBatchError, match=message):
        prepare_batch([{"op": "set-layout", **batch}], locate_events(EVENTS, BARS), STAVES, BARS)


def test_left_and_right_margins_need_identical_margins() -> None:
    mirrored = {**LETTER_OPTIONS, "pageSizeAndMarginOptions.pageMargins.type": "kMirrored"}
    with pytest.raises(DoricoBatchError, match="kMirrored"):
        _layout_options({"leftMargin": 10}, mirrored)
    assert "pageSizeAndMarginOptions.pageMargins.margins.top" in _layout_options({"topMargin": 10}, mirrored)


def test_choose_layout_defaults_to_the_full_score() -> None:
    from ai_score_editing.dorico.score import choose_layout

    layouts = [{"layoutID": 0, "layoutName": "Full score", "layoutType": "kFullScoreLayout"},
               {"layoutID": 1, "layoutName": "Piano", "layoutType": "kPartLayout"}]
    assert choose_layout(None, layouts, "op 0")["layoutID"] == 0
    assert choose_layout("piano", layouts, "op 0")["layoutID"] == 1
    assert choose_layout(1, layouts, "op 0")["layoutID"] == 1
    with pytest.raises(DoricoBatchError, match="no layout 'Flute'"):
        choose_layout("Flute", layouts, "op 0")
    with pytest.raises(DoricoBatchError, match="say which layout"):
        choose_layout(None, [layouts[1]], "op 0")


def test_layout_report_in_set_layout_terms() -> None:
    from ai_score_editing.dorico.score import layout_report

    report = layout_report({**LETTER_OPTIONS, "pageSizeAndMarginOptions.pageWidth": "792",
                            "pageSizeAndMarginOptions.pageHeight": "612"})
    assert report["pageSize"] == "letter" and report["orientation"] == "landscape"
    assert report["pageWidth"] == 279.4 and report["staffSize"] == 7.0
    assert report["leftMargin"] == 14.82 and report["spacesBetweenStaves"] == 6.0
    assert report["hideEmptyStaves"] == "never"


@pytest.mark.parametrize("op", ["set-bar-number", "hide-empty-staves"])
def test_sibelius_ops_without_a_dorico_route_say_why(op: str) -> None:
    with pytest.raises(DoricoBatchError, match=f"{op} is not available on Dorico"):
        prepare_batch([{"op": op, "bar": 2, "number": 5}], locate_events(EVENTS, BARS), STAVES, BARS)


# ------------------------------------------------------------------ add-line

def test_resize_steps_use_only_checked_note_values() -> None:
    from ai_score_editing.dorico.score import resize_steps

    lengthen = "EventEdit.DurationLengthenByValue?RhythmicGridResolutionValue="
    shorten = "EventEdit.DurationShortenByValue?RhythmicGridResolutionValue="
    assert resize_steps(1024, 1024) == []
    assert resize_steps(1024, 1536) == [lengthen + "kMinim"]
    assert resize_steps(256, 1312) == [lengthen + v for v in ("kSemibreve", "kDemisemiquaver")]
    assert resize_steps(1024, 384) == [shorten + "kMinim", shorten + "kQuaver"]
    with pytest.raises(DoricoBatchError, match="steps of 32"):
        resize_steps(256, 270)


def test_add_line_selects_the_item_at_the_position_or_a_temporary_rest() -> None:
    located = locate_events(EVENTS, BARS)
    ops = prepare_batch([{"op": "add-line", "line": "crescendo", "staff": 1, "bar": 1, "position": 256, "duration": 768}],
                        located, STAVES, BARS)
    assert ops[0]["select"] == {"id": 4, "stream": 2} and ops[0]["position"] == 256 and ops[0]["itemDuration"] == 256
    assert ops[0]["command"] == "NoteInput.CreateDynamic?Definition=<" and ops[0]["expect"] == "DynamicGroupEvent"
    assert ops[0]["resize"] == ["EventEdit.DurationLengthenByValue?RhythmicGridResolutionValue=kMinim"]
    ops = prepare_batch([{"op": "add-line", "line": "pedal", "staff": 2, "bar": 3, "duration": 256}], located, STAVES, BARS)
    assert "select" not in ops[0] and ops[0]["tempRest"] == {"stream": 4, "position": 2048, "duration": 256}
    assert ops[0]["resize"] == []
    ops = prepare_batch([{"op": "add-line", "line": "glissando", "staff": 1, "bar": 1}], located, STAVES, BARS)
    assert ops[0]["duration"] is None and "resize" not in ops[0]


@pytest.mark.parametrize(
    ("operation", "message"),
    [
        ({"line": "hairpin", "duration": 256}, "line must be one of"),
        ({"line": "trill", "bar": 3, "duration": 256}, "starts on a note"),
        ({"line": "glissando", "duration": 256}, "takes no duration"),
        ({"line": "8va", "duration": 100}, "multiple of 32"),
        ({"line": "8va"}, "duration must be an integer"),
        ({"line": "8va", "staff": 3, "duration": 256}, "no staff 3"),
    ],
)
def test_add_line_refusals(operation: dict[str, Any], message: str) -> None:
    batch = [{"op": "add-line", "staff": 1, "bar": 1, **operation}]
    with pytest.raises(DoricoBatchError, match=message):
        prepare_batch(batch, locate_events(EVENTS, BARS), STAVES, BARS)


# ------------------------------------------------------------------ add-lyrics

def test_parse_lyrics_words_hyphens_and_melismas() -> None:
    from ai_score_editing.dorico.score import parse_lyrics

    assert parse_lyrics("ma-king lyr-ics _ now") == [
        ("ma", "kHyphenateCurrentWord"), ("king", "kEndOrExtendCurrentWord"),
        ("lyr", "kHyphenateCurrentWord"), ("ics", "kEndOrExtendCurrentWord"),
        ("", "kEndOrExtendCurrentWord"), ("now", "kEndInput"),
    ]
    with pytest.raises(DoricoBatchError):
        parse_lyrics("   ")


def test_add_lyrics_resolves_first_note_and_refuses_the_rest() -> None:
    located = locate_events(EVENTS, BARS)
    ops = prepare_batch([{"op": "add-lyrics", "staff": 1, "bar": 1, "index": 0, "text": "Oh fare-well"}],
                        located, STAVES, BARS)
    assert ops == [{"op": "add-lyrics", "staff": 1, "position": 0, "verse": 1, "select": {"id": 3, "stream": 2},
                    "hasLyrics": False,
                    "syllables": [["Oh", "kEndOrExtendCurrentWord"], ["fare", "kHyphenateCurrentWord"],
                                  ["well", "kEndInput"]]}]
    ops = prepare_batch([{"op": "add-lyrics", "id": 3, "text": "x", "verse": 3}], located, STAVES, BARS)
    assert ops[0]["verse"] == 3
    for verse in (0, 11, True, "2"):
        with pytest.raises(DoricoBatchError, match="verse must be"):
            prepare_batch([{"op": "add-lyrics", "id": 3, "text": "x", "verse": verse}], located, STAVES, BARS)
    with pytest.raises(DoricoBatchError, match="cannot share a batch"):
        prepare_batch([{"op": "add-lyrics", "id": 3, "text": "x"}, {"op": "delete", "id": 4}], located, STAVES, BARS)


def _lyric_op(position: int, verse: int, syllables: int, has_lyrics: bool = True) -> dict[str, Any]:
    return {"op": "add-lyrics", "staff": 1, "position": position, "verse": verse, "hasLyrics": has_lyrics,
            "select": {"id": 3, "stream": 2}, "syllables": [["la", "kEndOrExtendCurrentWord"]] * syllables}


async def test_plan_lyrics_keeps_lower_verses_and_refuses_to_overwrite(monkeypatch: pytest.MonkeyPatch) -> None:
    def note(position: int, *lyrics: tuple[int, str]) -> dict[str, Any]:
        return {"type": "NoteEvent", "stream": 2, "flowPosition": position,
                "lyrics": [{"verse": v, "text": t} for v, t in lyrics]}

    located = [note(0, (1, "well,")), note(256, (1, "a")), note(512, (1, "day"), (3, "tres")),
               {"type": "NoteEvent", "stream": 9, "flowPosition": 256, "lyrics": [{"verse": 3, "text": "x"}]}]
    reads: list[bool] = []

    async def fake_snapshot(bridge: Any, flow: int, lyrics: bool = False) -> Any:
        reads.append(lyrics)
        return service.Snapshot([], located, BarMap([(0, 1024)]))

    monkeypatch.setattr(service, "snapshot", fake_snapshot)
    fresh = _lyric_op(0, 3, 2, has_lyrics=False)
    await service._plan_lyrics(None, [fresh], 1)  # type: ignore[arg-type]
    assert fresh["keep"] == ["", ""] and reads == []  # a staff without lyrics needs no export
    op = _lyric_op(0, 3, 2)  # lands on 0 and 256; stream 9's verse 3 at 256 is another voice
    await service._plan_lyrics(None, [op], 1)  # type: ignore[arg-type]
    assert op["keep"] == ["well,", ""] and reads == [True]
    with pytest.raises(DoricoError, match="already has a verse 3 lyric at bar 1"):
        await service._plan_lyrics(None, [_lyric_op(0, 3, 3)], 1)  # type: ignore[arg-type]


async def test_type_lyrics_moves_down_a_verse_per_kept_text(monkeypatch: pytest.MonkeyPatch) -> None:
    class Client:
        commands: list[str] = []

        async def command(self, command: str) -> None:
            self.commands.append(command)

    class Bridge:
        client = Client()

    async def front() -> None:
        pass

    monkeypatch.setattr(service, "bring_to_front", front)
    monkeypatch.setattr(service, "POPOVER_OPEN_DELAY", 0)
    monkeypatch.setattr(service, "SYLLABLE_DELAY", 0)
    steps = await service._type_lyrics(Bridge(), [["u", "kHyphenateCurrentWord"], ["no", "kEndInput"]],  # type: ignore[arg-type]
                                       ["well,", ""])
    assert steps == 4
    assert Bridge.client.commands == [
        "NoteInput.StartLyricInput",
        "NoteInput.AcceptCurrentLyricInput?LyricText=well\\,&LyricsEntryAdvanceType=kIncrementVerseNumber",
        "NoteInput.AdvanceLyricInput",
        "NoteInput.AcceptCurrentLyricInput?LyricsEntryAdvanceType=kIncrementVerseNumber",  # no text: nothing to keep
        "NoteInput.AdvanceLyricInput",
        "NoteInput.AcceptCurrentLyricInput?LyricText=u&LyricsEntryAdvanceType=kHyphenateCurrentWord",
        "NoteInput.AdvanceLyricInput",
        "NoteInput.AcceptCurrentLyricInput?LyricText=no&LyricsEntryAdvanceType=kEndInput",
    ]


# ------------------------------------------------------------------ lyrics dialog

def test_syllable_count_matches_the_dialog_text() -> None:
    from ai_score_editing.dorico.lyrics_dialog import syllable_count

    assert syllable_count("This was a lark for ma-king lyr-ics.") == 9
    assert syllable_count("if I go ten thou-sand-miles.") == 7
    assert syllable_count("  ") == 0


class _MenuClient:
    """Dorico's undo history as its Edit menu names it, top last."""

    def __init__(self, history: list[str]) -> None:
        self.history = history
        self.commands: list[str] = []

    async def command(self, command: str) -> None:
        self.commands.append(command)
        if command == "Edit.Undo":
            self.history.pop()

    def title(self) -> str:
        return f"Undo {self.history[-1]}" if self.history else "Undo"


@pytest.mark.parametrize(
    ("history", "undone", "kept"),
    [
        (["Add Text", "Select All", "Filter Lyrics"], 2, True),
        (["Select All", "Add Text"], 0, False),  # the top step is not the read's: leave everything
        (["Add Text", "Tout sélectionner", "Filtrer"], 0, False),  # another UI language
    ],
)
async def test_read_undoes_only_its_own_selections(
    monkeypatch: pytest.MonkeyPatch, history: list[str], undone: int, kept: bool
) -> None:
    from ai_score_editing.dorico import lyrics_dialog

    client = _MenuClient(list(history))

    class Bridge:
        pass

    bridge = Bridge()
    bridge.client = client  # type: ignore[attr-defined]
    async def menu_title(script: str, *args: str) -> str:
        return client.title()

    monkeypatch.setattr(lyrics_dialog, "osascript", menu_title)
    monkeypatch.setattr(lyrics_dialog, "MENU_POLL", 0)
    result = await lyrics_dialog._undo_read_steps(bridge, ["Undo Filter Lyrics", "Undo Select All"])  # type: ignore[arg-type]
    assert result is kept and client.commands.count("Edit.Undo") == undone
    assert client.history == history[: len(history) - undone]


async def test_part_layout_is_found_by_player_name() -> None:
    from ai_score_editing.dorico.lyrics_dialog import _part_layout

    class Client:
        async def layouts(self) -> list[dict[str, Any]]:
            return [{"layoutID": 0, "layoutName": "Full score", "layoutType": "kFullScoreLayout"},
                    {"layoutID": 3, "layoutName": "Alto I", "layoutType": "kPartLayout"}]

    class Bridge:
        client = Client()

    assert (await _part_layout(Bridge(), "alto i"))["layoutID"] == 3  # type: ignore[arg-type]
    with pytest.raises(DoricoError, match="parts: Alto I"):
        await _part_layout(Bridge(), "Bass")  # type: ignore[arg-type]


# ------------------------------------------------------------------ project info

@pytest.mark.parametrize(
    ("fields", "message"),
    [({"Composr": "x"}, "unknown Project Info fields"), ({}, "no fields"), ({"Title": "a\nb"}, "single-line")],
)
async def test_set_project_info_validates_before_opening_the_dialog(fields: dict[str, str], message: str) -> None:
    from ai_score_editing.dorico import project_info

    with pytest.raises(DoricoError, match=message):
        await project_info.set_project_info(None, fields)  # type: ignore[arg-type]


# ------------------------------------------------------------------ set-time / set-key / set-barline

def test_signature_ops_select_a_first_beat_note_and_use_popover_definitions() -> None:
    located = locate_events(EVENTS, BARS)
    ops = prepare_batch([
        {"op": "set-key", "bar": 2, "key": "Bb", "minor": True},
        {"op": "set-time", "bar": 2, "numerator": 6, "denominator": 8},
        {"op": "set-barline", "bar": 2, "type": "final"},
    ], located, STAVES, BARS)
    assert [(o["command"], o["definition"], o["expect"]) for o in ops] == [
        ("NoteInput.CreateKeySignature", "bb", "TonalityDivisionEvent"),
        ("NoteInput.CreateTimeSignature", "6/8", "BarDivisionEvent"),
        ("NoteInput.CreateBarLine", "|]", "BarDivisionEvent"),
    ]
    assert ops[0]["select"] == {"id": 7, "stream": 2} and ops[0]["position"] == 1024
    ops = prepare_batch([{"op": "set-time", "bar": 1, "numerator": 3, "denominator": 4},
                         {"op": "set-key", "bar": 1, "key": "G"},
                         {"op": "set-barline", "bar": 1, "type": "start_repeat"}], located, STAVES, BARS)
    assert [(o["definition"], o["position"], o["select"]["id"]) for o in ops] == [
        ("3/4", 0, 3), ("G", 0, 3), ("|:", 0, 3)]


def test_signature_in_a_bar_of_implicit_rests_uses_a_temporary_rest() -> None:
    time_at_bar_3 = [{"op": "set-time", "bar": 3, "numerator": 3, "denominator": 4}]
    ops = prepare_batch(time_at_bar_3, locate_events(EVENTS, BARS), STAVES, BARS)
    assert "select" not in ops[0] and ops[0]["tempRest"] == {"stream": 2, "position": 2048, "duration": 256}
    # a note soon after the first beat shortens the rest to fit
    ops = prepare_batch(time_at_bar_3, locate_events(EVENTS + [note(9, 2176, 60, "C4")], BARS), STAVES, BARS)
    assert ops[0]["tempRest"] == {"stream": 2, "position": 2048, "duration": 128}
    # held over the barline: the top voice is skipped for the next free one
    held = EVENTS + [note(9, 1536, 60, "C4", duration=1024)]
    ops = prepare_batch(time_at_bar_3, locate_events(held, BARS), STAVES, BARS)
    assert ops[0]["tempRest"]["stream"] == 4
    held.append(note(10, 1792, 48, "C3", duration=512, stream=4, staff=2))
    with pytest.raises(DoricoBatchError, match="every voice holds a note over it"):
        prepare_batch(time_at_bar_3, locate_events(held, BARS), STAVES, BARS)


@pytest.mark.parametrize(
    ("operation", "message"),
    [
        ({"op": "set-key", "bar": 0, "key": "D"}, "bar must be"),
        ({"op": "set-key", "bar": 2, "key": "H"}, "major key"),
        ({"op": "set-time", "bar": 2, "numerator": 3, "denominator": 3}, "power of two"),
        ({"op": "set-barline", "bar": 2, "type": "dashed"}, "type must be one of"),
        ({"op": "add-lyrics", "id": 3, "text": "back\\slash"}, "cannot contain"),
    ],
)
def test_signature_and_lyric_refusals(operation: dict[str, Any], message: str) -> None:
    with pytest.raises(DoricoBatchError, match=message):
        prepare_batch([operation], locate_events(EVENTS, BARS), STAVES, BARS)


def test_command_values_escape_commas_and_ampersands() -> None:
    from ai_score_editing.dorico.score import command_value

    assert command_value("well, you'll & more") == "well\\, you'll \\& more"
    with pytest.raises(DoricoBatchError):
        command_value("a\\b")


# ------------------------------------------------------------------ dump()-read streams

DUMPED = EVENTS + [
    {"id": 60, "type": "NoteEvent", "stream": 2, "staff": 1, "voice": 1, "position": 2048, "duration": 256,
     "pitch": 60, "name": "C4", "source": "dump"},
]


def test_edits_to_notes_read_from_dump_become_commands() -> None:
    located = locate_events(DUMPED, BARS)
    ops = prepare_batch([{"op": "delete", "id": 60}], located, STAVES, BARS)
    assert ops[0]["op"] == "delete-by-id" and ops[0]["select"] == {"id": 60, "stream": 2}
    ops = prepare_batch([{"op": "set-pitch", "id": 60, "oldPitch": 60, "newPitch": 62}], located, STAVES, BARS)
    assert (ops[0]["op"], ops[0]["newPitch"], ops[0]["letter"]) == ("repitch", 62, "D")
    ops = prepare_batch([{"op": "transpose", "fromBar": 3, "toBar": 3, "topStaff": 1, "bottomStaff": 1,
                          "fromNote": "C", "toNote": "E", "direction": "up"}], located, STAVES, BARS)
    assert [(o["op"], o["newPitch"], o["letter"]) for o in ops] == [("repitch", 64, "E")]
    with pytest.raises(DoricoBatchError, match="cannot share a batch"):
        prepare_batch([{"op": "delete", "id": 60}, {"op": "delete", "id": 3}], located, STAVES, BARS)
    ops = prepare_batch([{"op": "add-lyrics", "id": 60, "text": "la", "verse": 2}], located, STAVES, BARS)
    assert ops[0]["hasLyrics"] and ops[0]["select"] == {"id": 60, "stream": 2}


def test_command_ops_can_select_notes_read_from_dump() -> None:
    ops = prepare_batch([{"op": "set-key", "bar": 3, "key": "G"}], locate_events(DUMPED, BARS), STAVES, BARS)
    assert ops[0]["select"] == {"id": 60, "stream": 2}


def test_attach_lyrics_matches_notes_by_staff_position_and_pitch() -> None:
    located = [{"type": "NoteEvent", "staff": 1, "flowPosition": 0, "pitch": 62},
               {"type": "NoteEvent", "staff": 1, "flowPosition": 256, "pitch": 64}]
    service._attach_lyrics(located, [{"staff": 1, "flowPosition": 0, "pitch": 62,
                                      "lyrics": [{"verse": 1, "text": "Oh", "syllabic": "single"}]}])
    assert located[0]["lyrics"][0]["text"] == "Oh" and "lyrics" not in located[1]


# ------------------------------------------------------------------ notation command ops

def test_note_command_ops_resolve_to_commands() -> None:
    ops = prepare_batch([
        {"op": "add-dynamic", "id": 4, "dynamic": "mf"},
        {"op": "set-articulation", "id": 4, "articulation": "tenuto"},
        {"op": "add-slur", "id": 3},
        {"op": "add-tempo", "id": 5, "text": "Allegro, ma non troppo"},
        {"op": "add-rehearsal-mark", "id": 6},
    ], locate_events(EVENTS, BARS), STAVES, BARS)
    assert [(o["command"], o["parameters"], o.get("expect")) for o in ops] == [
        ("NoteInput.CreateDynamic", {"Definition": "mf"}, "DynamicGroupEvent"),
        ("NoteInput.SetArticulation", {"Value": "kTenuto"}, None),
        ("NoteInput.SlurStart", {}, None),
        ("NoteInput.CreateTempo", {"Definition": "Allegro\\, ma non troppo"}, "ImmediateTempoChangeEvent"),
        ("NoteInput.CreateRehearsalMark", {}, "RehearsalMarkEvent"),
    ]
    assert ops[1]["checkable"] is True


@pytest.mark.parametrize(
    ("operation", "message"),
    [({"op": "add-dynamic", "id": 4, "dynamic": "loud"}, "dynamic must be"),
     ({"op": "set-articulation", "id": 4, "articulation": "spiccato"}, "articulation must be")],
)
def test_note_command_refusals(operation: dict[str, Any], message: str) -> None:
    with pytest.raises(DoricoBatchError, match=message):
        prepare_batch([operation], locate_events(EVENTS, BARS), STAVES, BARS)


# ------------------------------------------------------------------ copy-passage

def test_copy_passage_anchors_at_the_first_note_offset() -> None:
    events = [note(3, 128, 60, "C4"), note(4, 512, 62, "D4")]  # bar 1: first note half a beat in
    located = locate_events(events, BARS)
    ops = prepare_batch([{"op": "copy-passage", "fromBar": 1, "toBar": 1, "topStaff": 1, "bottomStaff": 1,
                          "destStaff": 1, "destBar": 3}], located, STAVES, BARS)
    op = ops[0]
    assert op["select"] == {"id": 3, "stream": 2} and op["extendBars"] == 1 and op["exact"]
    assert op["destStreams"] == [2]
    assert op["anchorPosition"] == 2048 + 128
    assert op["tempRest"] == {"stream": 2, "position": 2176, "duration": 256}
    assert op["expect"] == [(0, 60), (384, 62)]


@pytest.mark.parametrize(
    ("operation", "message"),
    [
        ({"fromBar": 1, "toBar": 2, "destBar": 2}, "overlaps"),
        ({"fromBar": 3, "toBar": 3, "destBar": 5}, "no notes to copy"),
        ({"fromBar": 1, "toBar": 1, "destBar": 3, "destPosition": 256}, "destPosition"),
    ],
)
def test_copy_passage_refusals(operation: dict[str, Any], message: str) -> None:
    base = {"op": "copy-passage", "topStaff": 1, "bottomStaff": 1, "destStaff": 1}
    with pytest.raises(DoricoBatchError, match=message):
        prepare_batch([{**base, **operation}], locate_events(EVENTS, BARS), STAVES, BARS)


def test_copy_passage_refuses_a_note_over_the_paste_point() -> None:
    events = [note(3, 128, 60, "C4"), note(9, 2048, 55, "G3", duration=512)]  # a half note from bar 3's start
    with pytest.raises(DoricoBatchError, match="covers the paste point"):
        prepare_batch([{"op": "copy-passage", "fromBar": 1, "toBar": 1, "topStaff": 1, "bottomStaff": 1,
                        "destStaff": 1, "destBar": 3}], locate_events(events, BARS), STAVES, BARS)


def test_move_passage_resolves_like_copy_with_the_ids_that_must_go_and_stay() -> None:
    events = [note(3, 128, 60, "C4"), note(4, 512, 62, "D4"), note(5, 1024, 64, "E4")]  # bars 1 and 2
    located = locate_events(events, BARS)
    ops = prepare_batch([{"op": "move-passage", "fromBar": 1, "toBar": 1, "topStaff": 1, "bottomStaff": 1,
                          "destStaff": 1, "destBar": 3}], located, STAVES, BARS)
    op = ops[0]
    assert op["op"] == "copy-passage" and op["move"] is True
    assert op["cutIds"] == [3, 4] and op["keepIds"] == [5]  # bar 2's note stays
    assert op["expect"] == [(0, 60), (384, 62)]


def test_move_passage_cuts_and_checks_what_vanished() -> None:
    import asyncio
    from types import SimpleNamespace

    from ai_score_editing.dorico import service

    def n(id_: int, pos: int, pitch: int) -> dict:
        return {"id": id_, "type": "NoteEvent", "position": pos, "stream": 2, "pitch": pitch}

    def run(overreach: bool) -> tuple[list[str], list[int], Exception | None]:
        client = SimpleNamespace(commands=[])
        state = {"events": [n(3, 0, 60), n(4, 512, 62), n(5, 1024, 64)], "history": []}

        async def command(c: str) -> None:
            client.commands.append(c)
            if c == "Edit.Cut":
                state["history"].append(state["events"])
                gone = {3, 4, 5} if overreach else {3, 4}  # overreach: a slur drags bar 2's note in
                state["events"] = [e for e in state["events"] if e["id"] not in gone]
            elif c == "Edit.Paste":
                state["history"].append(state["events"])
                state["events"] = state["events"] + [n(3, 2048, 60), n(4, 2432, 62)]  # a paste keeps the ids
            elif c == "Edit.Undo":
                state["events"] = state["history"].pop()

        async def status() -> dict:
            return {"noteInputMode": "kOverwrite"}

        client.command, client.status = command, status
        bridge = SimpleNamespace(client=client)

        async def read_partial(flow: int):
            return state["events"], []

        bridge.read_partial = read_partial
        op = {"op": "copy-passage", "move": True, "staff": 1, "destStaff": 1, "select": {"id": 3, "stream": 2, "block": 7},
              "extendBars": 1, "exact": True, "expect": [(0, 60), (384, 62)], "anchorPosition": 2048, "destStreams": [2],
              "anchor": {"id": 9, "stream": 2, "block": 7}, "cutIds": [3, 4], "keepIds": [5]}
        error = None
        try:
            steps, result = asyncio.run(service._copy_passage(bridge, op, 1, 0, {"2": 7}))
        except Exception as exc:  # noqa: BLE001
            error = exc
            result = {}
        return client.commands, [(e["id"], e["position"]) for e in state["events"]], error if error else result

    commands, ids, result = run(overreach=False)
    assert "Edit.Cut" in commands and "Edit.Copy" not in commands
    assert result["op"] == "move-passage" and result["verified"] and sorted(ids) == [(3, 2048), (4, 2432), (5, 1024)]

    commands, ids, error = run(overreach=True)
    assert isinstance(error, service.DoricoError) and "cut more" in str(error)
    assert ids == [(3, 0), (4, 512), (5, 1024)]  # put back, positions and all
    assert commands.count("Edit.Undo") == 2  # the paste and the cut


# ------------------------------------------------------------------ probe placement

def test_layout_from_probed_placements() -> None:
    from ai_score_editing.dorico import layout

    piano = {"staves": [{"stream": 1}, {"stream": 3}],
             "instruments": [{"id": 0, "name": "Piano", "voiceStreams": [2, 4, 6, 7]}]}
    staves = layout.resolve(piano, [], placements={2: 1, 4: 2, 7: 1})
    assert [s["voiceStreams"] for s in staves] == [[2, 7], [4]]  # 6 has no notes: unplaced
    choir = {"staves": [{"stream": 1}, {"stream": 3}, {"stream": 5}],
             "instruments": [{"id": 0, "name": "S", "voiceStreams": [10]},
                             {"id": 1, "name": "T", "voiceStreams": [11, 12]}]}
    staves = layout.resolve(choir, [], placements={10: 1, 11: 2, 12: 3})
    assert [(s["name"], s["voiceStreams"]) for s in staves] == [("S", [10]), ("T", [11]), ("T", [12])]
    with pytest.raises(layout.NeedsMusicXML):
        layout.resolve(choir, [], placements={11: 2, 12: 3})  # S has nothing probed


def test_loose_placements_name_staves_whatever_order_instruments_are_listed() -> None:
    from ai_score_editing.dorico import layout

    # Instruments listed out of staff order, one with no notes: strict reading gives up, loose does not.
    raw = {"staves": [{"stream": 1}, {"stream": 3}, {"stream": 5}],
           "instruments": [{"id": 0, "name": "Bells", "voiceStreams": [10]},
                           {"id": 1, "name": "Kit", "voiceStreams": [11]},
                           {"id": 2, "name": "Flute", "voiceStreams": [12]}]}
    with pytest.raises(layout.NeedsMusicXML):
        layout.resolve(raw, [], placements={10: 3, 12: 1})
    staves = layout.resolve(raw, [], placements={10: 3, 12: 1}, loose=True)
    assert [(s["staff"], s["name"], s["voiceStreams"]) for s in staves] == [
        (1, "Flute", [12]), (2, None, []), (3, "Bells", [10])]


class _ProbeClient:
    """Dorico's undo stack as the probe sees it: selections and dynamics are steps."""

    def __init__(self, notes: list[dict[str, Any]], history: list[Any], select_is_a_step: bool = True) -> None:
        self.commands: list[str] = []
        self.notes = notes
        self.history = history  # the user's own steps come first
        self.select_is_a_step = select_is_a_step
        self.selected = ""
        self.undone: Any = None

    async def flows(self) -> list[dict[str, Any]]:
        return [{"flowID": 0}]

    async def command(self, command: str) -> None:
        self.commands.append(command)
        if command.startswith("EventEdit.Select"):
            self.selected = command
            if self.select_is_a_step:
                self.history.append("select")
        elif command.startswith("NoteInput.CreateDynamic"):
            staff = 1 if "EventID=3&" in self.selected else 2
            self.history.append({"id": 90 + len(self.commands), "type": "DynamicGroupEvent", "staff": staff})
        elif command == "Edit.Undo":
            self.undone = self.history.pop()
        elif command == "Edit.Redo":
            self.history.append(self.undone)

    def events(self) -> list[dict[str, Any]]:
        return self.notes + [step for step in self.history if isinstance(step, dict)]


class _ProbeBridge:
    def __init__(self, client: _ProbeClient) -> None:
        self.client = client

    async def read_partial(self, flow: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        return self.client.events(), []


_PROBE_RAW = {"blocks": {"2": 2, "4": 4, "6": 6}, "instruments": [{"id": 0, "voiceStreams": [2, 4, 6]}]}
_PROBE_NOTES = [{"id": 3, "stream": 2, "type": "NoteEvent"}, {"id": 13, "stream": 4, "type": "NoteEvent"}]
_USER_EDIT = {"id": 50, "type": "TextEvent", "stream": 2, "text": "the user's own edit"}


async def test_probe_placements_selects_probes_and_undoes() -> None:
    client = _ProbeClient(list(_PROBE_NOTES), [_USER_EDIT])
    placements = await service.probe_placements(_ProbeBridge(client), _PROBE_RAW, client.events(), 1)  # type: ignore[arg-type]
    assert placements == {2: 1, 4: 2}
    # the dynamic and the selection are undone for each probe, so the undo
    # history is as it was: the user's edit is still the next step to undo
    assert client.commands.count("Edit.Undo") == 4 and client.history == [_USER_EDIT]


async def test_probe_placements_redoes_an_undo_that_changed_the_score() -> None:
    client = _ProbeClient(list(_PROBE_NOTES), [_USER_EDIT], select_is_a_step=False)
    with pytest.raises(DoricoError, match="redone"):
        await service.probe_placements(_ProbeBridge(client), _PROBE_RAW, client.events(), 1)  # type: ignore[arg-type]
    assert client.commands[-1] == "Edit.Redo" and client.history == [_USER_EDIT]


def test_deleting_by_command_counts_measured_undo_steps() -> None:
    # EventEdit.Delete by id: two steps for a note, one for a rest or a time
    # signature (each measured with a marker edit).
    assert service._delete_steps({"op": "delete-by-id", "type": "NoteEvent"}) == 2
    assert service._delete_steps({"op": "delete-by-id", "type": "RestEvent"}) == 1
    assert service._delete_steps({"op": "delete-by-id", "type": "BarDivisionEvent"}) == 1


def test_private_export_folder_is_emptied_and_guarded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from ai_score_editing.dorico import export

    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    work = tmp_path / "cache" / "ai-score-editing" / "dorico"
    monkeypatch.setattr(export, "EXPORT_DIR", work / "musicxml")
    old = work / "musicxml" / "Flows from Old"
    old.mkdir(parents=True)
    (old / "Old - Full score - 01 Old.musicxml").write_text("<x/>")
    assert export._clear_export_dir() == (work / "musicxml").resolve()
    assert list((work / "musicxml").iterdir()) == []
    monkeypatch.setattr(export, "EXPORT_DIR", tmp_path / "Scores")
    with pytest.raises(DoricoError, match="refusing to clear"):
        export._clear_export_dir()


def test_delete_bars_undoes_a_planned_selection_that_removes_the_wrong_bars_and_goes_bar_by_bar() -> None:
    import asyncio
    from types import SimpleNamespace

    from ai_score_editing.dorico import service

    def note(id_: int, position: int) -> dict:
        return {"id": id_, "type": "NoteEvent", "position": position, "stream": 1}

    class Client:
        def __init__(self) -> None:
            self.events = [note(1, 0), note(2, 1024), note(3, 2048), note(4, 3072)]
            self.history: list[list[dict]] = []
            self.deletes = 0
            self.commands: list[str] = []

        async def command(self, command: str) -> None:
            self.commands.append(command)
            if command == "Edit.Undo":
                self.events = self.history.pop()
            elif command == "Edit.DeleteBars":
                self.deletes += 1
                self.history.append(self.events)
                bars = 2 if self.deletes == 1 else 1  # the first, planned, selection overshoots by a bar (a slur)
                self.events = [{**e, "position": e["position"] - 1024 * bars} for e in self.events if e["position"] >= 1024 * bars]

    client = Client()
    bridge = SimpleNamespace(client=client)

    async def read_partial(flow: int):
        return client.events, []

    async def overview(flow: int):
        return {"layout": {"blocks": {"1": 5}}}

    bridge.read_partial, bridge.overview = read_partial, overview
    op = {"op": "delete-bars", "fromBar": 1, "toBar": 1, "removed": 1024, "marker": {"id": 4, "position": 3072},
          "plan": {"select": {"id": 1, "stream": 1}, "extend": 0},
          "fallback": [{"bar": 1, "select": {"id": 1, "stream": 1}}], "bars": [{"bar": 1}]}
    steps, result = asyncio.run(service._delete_bars(bridge, op, 1, 0, {"1": 5}))
    assert result["via"].startswith("per-bar") and result["verified"] and "retried" in result
    assert client.deletes == 2 and client.commands.count("Edit.Undo") == 1
    assert [e["position"] for e in client.events] == [0, 1024, 2048]
    assert steps == 2


class _FakeDorico:
    """A client and bridge for service._delete_bars: four bars of whole notes (ids 1-4), a note
    after the range (id 4). Selecting a note in `refuse` makes EventEdit.NavigateRightExtendBar
    answer kCommandNotAllowed; in `overshoot` makes Edit.DeleteBars remove two bars, not one."""

    def __init__(self, refuse: set[int] = frozenset(), overshoot: set[int] = frozenset()) -> None:
        from types import SimpleNamespace

        self.events = [{"id": i + 1, "type": "NoteEvent", "position": 1024 * i, "stream": 1} for i in range(4)]
        self.history: list[list[dict]] = []
        self.refuse, self.overshoot = refuse, overshoot
        self.selected = 0
        self.commands: list[str] = []
        self.client = self
        self.bridge = SimpleNamespace(client=self, read_partial=self.read_partial, overview=self.overview)

    async def command(self, command: str) -> None:
        from ai_score_editing.dorico.client import DoricoError

        self.commands.append(command)
        if command.startswith("EventEdit.Select"):
            self.selected = int(command.split("EventID=")[1].split("&")[0])
        elif command == "EventEdit.NavigateRightExtendBar":
            if self.selected in self.refuse:
                raise DoricoError("Dorico rejected command EventEdit.NavigateRightExtendBar: kCommandNotAllowed")
        elif command == "Edit.Undo":
            self.events = self.history.pop()
        elif command == "Edit.DeleteBars":
            self.history.append(self.events)
            bars = 2 if self.selected in self.overshoot else 1
            self.events = [{**e, "position": e["position"] - 1024 * bars} for e in self.events if e["position"] >= 1024 * bars]

    async def read_partial(self, flow: int):
        return self.events, []

    async def overview(self, flow: int):
        return {"layout": {"blocks": {"1": 5}}}

    def op(self, plans: list[tuple[int, int]], fallback: bool = True) -> dict:
        built = [{"select": {"id": i, "stream": 1}, "extend": extend, "staff": i} for i, extend in plans]
        return {"op": "delete-bars", "fromBar": 1, "toBar": 1, "removed": 1024, "marker": {"id": 4, "position": 3072},
                "plan": built[0], "plans": built, "bars": [{"bar": 1}],
                **({"fallback": [{"bar": 1, "select": {"id": 3, "stream": 1}}]} if fallback else {})}

    def run(self, op: dict) -> tuple[int, dict]:
        import asyncio

        from ai_score_editing.dorico import service

        return asyncio.run(service._delete_bars(self.bridge, op, 1, 0, {"1": 5}))


def test_delete_bars_tries_the_next_plan_when_one_is_refused_or_overshoots() -> None:
    # plan 1 overshoots a bar (one Undo), plan 2 is refused on the extend step (nothing to undo), plan 3 works
    fake = _FakeDorico(refuse={2}, overshoot={1})
    steps, result = fake.run(fake.op([(1, 1), (2, 1), (3, 1)]))
    assert result["via"] == "extend" and result["verified"] and result["attempts"] == 3 and "kCommandNotAllowed" in result["retried"]
    assert fake.commands.count("Edit.Undo") == 1 and fake.commands.count("Edit.DeleteBars") == 2
    assert [e["position"] for e in fake.events] == [0, 1024, 2048] and steps == 3


def test_delete_bars_goes_bar_by_bar_when_every_plan_fails() -> None:
    fake = _FakeDorico(refuse={2}, overshoot={1})
    steps, result = fake.run(fake.op([(1, 0), (2, 1)]))
    assert result["via"].startswith("per-bar") and result["verified"] and result["attempts"] == 2
    assert fake.commands.count("Edit.Undo") == 1 and steps == 2
    assert [e["position"] for e in fake.events] == [0, 1024, 2048]


def test_delete_bars_without_a_fallback_still_raises_when_the_last_plan_fails() -> None:
    import pytest

    from ai_score_editing.dorico.client import DoricoError

    refused = _FakeDorico(refuse={1, 2})
    with pytest.raises(DoricoError, match="kCommandNotAllowed"):
        refused.run(refused.op([(1, 1), (2, 1)], fallback=False))
    assert refused.commands.count("Edit.Undo") == 0 and refused.commands.count("Edit.DeleteBars") == 0

    wrong = _FakeDorico(overshoot={1})
    with pytest.raises(DoricoError, match="did not delete bars"):
        wrong.run(wrong.op([(1, 0)], fallback=False))


def test_delete_bars_cost_is_the_dearest_route() -> None:
    from ai_score_editing.dorico import service

    fake = _FakeDorico()
    op = fake.op([(1, 0), (2, 3)])
    assert service._delete_bars_cost(op) == 5  # 2 + 3 extend steps, against 2 for the per-bar route
    assert service._delete_bars_cost({**op, "fallback": [{"bar": b, "tempRest": {}} for b in (3, 2, 1)]}) == 9
    assert service._delete_bars_cost({"plan": op["plan"]}) == 2
