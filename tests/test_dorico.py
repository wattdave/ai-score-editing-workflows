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
