"""Tests for the Dorico back end, with a fake Dorico instead of the real one."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
import websockets

from sibelius_websocket_cli.dorico import bridge as bridge_mod
from sibelius_websocket_cli.dorico import service
from sibelius_websocket_cli.dorico.bridge import BarMap, DoricoBridge, fingerprint, lua_literal
from sibelius_websocket_cli.dorico.client import DoricoClient, DoricoError
from sibelius_websocket_cli.dorico.score import (
    DoricoBatchError,
    interval_of,
    locate_events,
    prepare_batch,
    query,
    resolve_staves,
    spelling_letter,
    transpose_spelled,
)
from sibelius_websocket_cli.token_store import TokenStore

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

    def __init__(self, reads: list[list[dict[str, Any]]]) -> None:
        self.client = self  # type: ignore[assignment]
        self.workdir = Path("/nonexistent")
        self._bars = {}
        self.reads = reads
        self.commands: list[str] = []

    async def status(self) -> dict[str, Any]:
        return {"notReadOnly": True, "canUndo": True}

    async def command(self, command: str) -> None:
        self.commands.append(command)

    async def call(self, action: str, **params: Any) -> Any:
        if action == "read":
            return {"events": self.reads.pop(0)}
        assert action == "bars"
        return {"divisions": [{"position": 0, "length": 768}], "created": 1}


async def test_bar_measurement_is_undone_and_cached() -> None:
    bridge = ScriptedBridge([EVENTS])
    first = await bridge.bars(1, EVENTS)
    assert first.divisions == [(0, 768)]
    assert bridge.commands == ["Edit.Undo"]
    assert await bridge.bars(1, EVENTS) is first
    assert bridge.commands == ["Edit.Undo"]


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
    from sibelius_websocket_cli.dorico import musicxml_read

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
    from sibelius_websocket_cli.dorico import export

    log = tmp_path / "application.log"
    log.write_text("old line\n")
    pdf = tmp_path / "01 - Full score - Song.pdf"
    clicked: list[tuple[str, ...]] = []

    def fake_osascript(script: str, *args: str) -> str:
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

    monkeypatch.setattr(export, "_osascript", fake_osascript)
    client = Client()
    assert await export.export_pdf(client, log) == pdf  # type: ignore[arg-type]
    assert client.commands == ["Print.ExportCurrentLayoutAsPDF"]
    assert clicked == [("2", "Overwrite")]


# ------------------------------------------------------------------ voice layout

def test_layout_one_voice_per_stave_and_single_stave_instruments() -> None:
    from sibelius_websocket_cli.dorico import layout

    piano = {"staves": [{"stream": 1}, {"stream": 3}],
             "instruments": [{"id": 0, "name": "Piano", "voiceStreams": [4, 2]}]}
    assert [s["voiceStreams"] for s in layout.resolve(piano, [])] == [[2], [4]]
    choir = {"staves": [{"stream": 1}, {"stream": 3}],
             "instruments": [{"id": 0, "name": "S", "voiceStreams": [9, 5]}, {"id": 1, "name": "A", "voiceStreams": [7]}]}
    assert [(s["name"], s["voiceStreams"]) for s in layout.resolve(choir, [])] == [("S", [5, 9]), ("A", [7])]


def test_layout_extra_voice_needs_musicxml_and_is_placed_by_its_notes() -> None:
    from sibelius_websocket_cli.dorico import layout

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


# ------------------------------------------------------------------ add-lyrics

def test_parse_lyrics_words_hyphens_and_melismas() -> None:
    from sibelius_websocket_cli.dorico.score import parse_lyrics

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

    monkeypatch.setattr(service, "bring_to_front", lambda: None)
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
    from sibelius_websocket_cli.dorico.lyrics_dialog import syllable_count

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
    from sibelius_websocket_cli.dorico import lyrics_dialog

    client = _MenuClient(list(history))

    class Bridge:
        pass

    bridge = Bridge()
    bridge.client = client  # type: ignore[attr-defined]
    monkeypatch.setattr(lyrics_dialog, "_osascript", lambda script, *args: client.title())
    monkeypatch.setattr(lyrics_dialog, "MENU_POLL", 0)
    result = await lyrics_dialog._undo_read_steps(bridge, ["Undo Filter Lyrics", "Undo Select All"])  # type: ignore[arg-type]
    assert result is kept and client.commands.count("Edit.Undo") == undone
    assert client.history == history[: len(history) - undone]


async def test_part_layout_is_found_by_player_name() -> None:
    from sibelius_websocket_cli.dorico.lyrics_dialog import _part_layout

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
    from sibelius_websocket_cli.dorico import project_info

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
    from sibelius_websocket_cli.dorico.score import command_value

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
    assert op["select"] == {"id": 3, "stream": 2} and op["extendBars"] == 0
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


# ------------------------------------------------------------------ probe placement

def test_layout_from_probed_placements() -> None:
    from sibelius_websocket_cli.dorico import layout

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
