"""Dorico bridge: bar measurement, probing, snapshots and undo-driven deletion."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import pytest

from ai_score_editing.dorico import bridge as bridge_mod
from ai_score_editing.dorico import service
from ai_score_editing.dorico.bridge import DoricoBridge, fingerprint
from ai_score_editing.dorico.client import DoricoError
from ai_score_editing.dorico.score import DoricoBatchError, prepare_batch

from dorico_common import EVENTS, dorico, note  # noqa: F401,F811


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
    with pytest.raises(DoricoError, match="one of: Alto I"):
        await _part_layout(Bridge(), "Bass")  # type: ignore[arg-type]


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
