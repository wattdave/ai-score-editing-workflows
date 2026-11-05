"""Dorico service layer: batch planning, spelling, layout, lyrics and passage operations."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import pytest
from types import SimpleNamespace

from ai_score_editing.dorico import score, service
from ai_score_editing.core.errors import BatchError
from ai_score_editing.dorico.bridge import BarMap, lua_literal
from ai_score_editing.dorico.client import DoricoError
from ai_score_editing.dorico.score import DoricoBatchError, interval_of, locate_events, prepare_batch, query, resolve_staves, spelling_letter, transpose_spelled

from dorico_common import EVENTS, note  # noqa: F401,F811


STAVES = [
    {"staff": 1, "name": "Piano", "stream": 1, "voiceStreams": [2]},
    {"staff": 2, "name": "Piano", "stream": 3, "voiceStreams": [4]},
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
    with pytest.raises(BatchError):
        spelling_letter(70, "B")


def test_transpose_spelled_keeps_letters_moving_diatonically() -> None:
    steps, semis = interval_of({"fromNote": "C", "toNote": "D", "direction": "up"}, "op")
    assert (steps, semis) == (1, 2)
    assert transpose_spelled("B4", 71, steps, semis) == (73, "C")   # C#5
    assert transpose_spelled("Eb4", 63, steps, semis) == (65, "F")
    steps, semis = interval_of({"fromNote": "C", "toNote": "A", "direction": "down", "octaves": 1}, "op")
    assert (steps, semis) == (-9, -15)
    with pytest.raises(BatchError):
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


def test_ficta_hides_the_accidental_and_names_the_technique() -> None:
    ops = prepare_batch([
        {"op": "ficta", "id": 4, "accidental": "flat"},
        {"op": "ficta", "id": 4, "remove": True},
    ], locate_events(EVENTS, BARS), STAVES, BARS)
    assert [(o["command"], o["ficta"], o.get("technique")) for o in ops] == [
        ("Edit.HideAccidental", "flat", "fictaflat"),
        ("Edit.ShowAccidental", None, None),
    ]


@pytest.mark.parametrize(
    ("operation", "message"),
    [({"op": "ficta", "id": 4}, "accidental must be"),
     ({"op": "ficta", "id": 4, "accidental": "double-sharp"}, "accidental must be"),
     ({"op": "ficta", "id": 4, "remove": True, "accidental": "flat"}, "not used with remove"),
     ({"op": "ficta", "id": 4, "remove": "yes"}, "remove must be boolean")],
)
def test_ficta_refusals(operation: dict[str, Any], message: str) -> None:
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
