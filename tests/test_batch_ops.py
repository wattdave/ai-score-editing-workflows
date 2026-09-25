"""Tests for ApplyBatch operation validation and the writable allow-list."""

import re
from pathlib import Path

import pytest

from sibelius_websocket_cli.batch_ops import (
    COMMON_WRITABLE,
    DEFAULT_TEXT_STYLE,
    STRUCTURAL,
    WRITABLE_PROPS,
    name_structure,
    BatchError,
    validate_batch,
)
from sibelius_websocket_cli.note_patches import batch_operations, execution_order

PLUGIN = Path(__file__).parent.parent / "src/sibelius_websocket_cli/manuscript/sibwscli.plg"


def test_python_writable_table_matches_plugin() -> None:
    source = PLUGIN.read_text()
    start = source.index('BatchWritableTable "() {')
    body = source[start:source.index('}"', start)]
    common_part, types_part = body.split("types = CreateDictionary(", 1)
    assert set(re.findall(r"'(\w+)', True", common_part)) == set(COMMON_WRITABLE)
    types = {
        kind: set(re.findall(r"'(\w+)', True", props))
        for kind, props in re.findall(r"'(\w+)', CreateDictionary\(([^)]*)\)", types_part)
    }
    assert types == {kind: set(props) for kind, props in WRITABLE_PROPS.items()}


def test_python_structural_ops_match_plugin() -> None:
    source = PLUGIN.read_text()
    start = source.index('BatchStructural "(opName) {')
    body = source[start:source.index('}"', start)]
    assert set(re.findall(r"opName = '([\w-]+)'", body)) == STRUCTURAL


def test_validate_normalizes_each_operation() -> None:
    batch = validate_batch([
        {"op": "set", "staff": 1, "bar": 2, "index": 0, "prop": "Dx", "value": -16,
         "type": "NoteRest", "position": 256},
        {"op": "tie", "staff": 1, "bar": 2, "index": 1},
        {"op": "bracket", "staff": 1, "bar": 2, "index": 1, "remove": True},
        {"op": "add-note", "staff": 2, "bar": 3, "position": 0, "duration": 256, "pitches": [60, 64]},
        {"op": "add-text", "staff": 1, "bar": 1, "position": 0, "text": "dolce"},
        {"op": "add-lyric", "staff": 1, "bar": 1, "position": 0, "duration": 256, "text": "la",
         "syllableType": "middle", "voice": 2},
    ])
    assert batch[0] == {"op": "set", "staff": 1, "bar": 2, "index": 0, "type": "NoteRest",
                        "position": 256, "prop": "Dx", "value": -16}
    assert batch[1]["tied"] is True and "remove" not in batch[1]
    assert batch[2]["bracketed"] is False
    assert batch[3]["tied"] is False
    assert batch[4]["styleId"] == DEFAULT_TEXT_STYLE
    assert batch[5]["voice"] == 2 and batch[5]["syllableType"] == "middle"


@pytest.mark.parametrize(
    ("operation", "message"),
    [
        ({"op": "move", "staff": 1, "bar": 1, "index": 0}, "op must be one of"),
        ({"op": "set", "staff": 1, "bar": 1, "index": 0, "prop": "Pitch", "value": 60}, "not writable"),
        ({"op": "set", "staff": 1, "bar": 1, "index": 0, "prop": "Dx", "value": "8"}, "must be int"),
        ({"op": "set", "staff": 1, "bar": 1, "index": 0, "prop": "Dx", "value": True}, "must be int"),
        ({"op": "set", "staff": 1, "bar": 1, "index": 0, "prop": "Hidden", "value": 1}, "must be bool"),
        ({"op": "set-pitch", "staff": 1, "bar": 1, "index": 0, "oldPitch": 60, "newPitch": 60}, "must change"),
        ({"op": "delete", "staff": -1, "bar": 1, "index": 0}, "staff must be"),
        ({"op": "tie", "staff": 0, "bar": 1, "index": 0}, "cannot target the system staff"),
        ({"op": "add-lyric", "staff": 0, "bar": 1, "position": 0, "duration": 256, "text": "x"},
         "cannot target the system staff"),
        ({"op": "add-text", "staff": 0, "bar": 1, "position": 0, "text": "x", "voice": 1}, "no voices"),
        ({"op": "add-text", "staff": 0, "bar": 1, "position": 0, "text": "x",
          "styleId": "text.staff.expression"}, "text.system"),
        ({"op": "add-text", "staff": 1, "bar": 1, "position": 0, "text": "x",
          "styleId": "text.system.tempo"}, "text.staff"),
        ({"op": "add-line", "staff": 0, "bar": 1, "position": 0, "duration": 256}, "styleId"),
        ({"op": "add-line", "staff": 0, "bar": 1, "position": 0, "duration": 256,
          "styleId": "line.staff.slur.up"}, "line.system"),
        ({"op": "add-line", "staff": 1, "bar": 1, "position": 0, "duration": 256,
          "styleId": "line.system.tempo.rall"}, "line.staff"),
        ({"op": "add-line", "staff": 1, "bar": 1, "position": 0,
          "styleId": "line.staff.hairpin.crescendo"}, "duration"),
        ({"op": "add-note", "staff": 1, "bar": 1, "position": 0, "duration": 256, "pitches": [128]}, "MIDI"),
        ({"op": "add-text", "staff": 1, "bar": 1, "position": 0, "text": "x", "styleId": "bogus"}, "styleId"),
        ({"op": "add-lyric", "staff": 1, "bar": 1, "position": 0, "duration": 256, "text": "x",
          "voice": 5}, "voice must be"),
    ],
)
def test_validate_rejects(operation, message) -> None:
    with pytest.raises(BatchError, match=message):
        validate_batch([operation])


def test_system_staff_takes_system_text_and_lines() -> None:
    batch = validate_batch([
        {"op": "delete", "staff": 0, "bar": 40, "index": 0, "type": "Text"},
        {"op": "set", "staff": 0, "bar": 41, "index": 0, "prop": "Hidden", "value": False},
        {"op": "add-text", "staff": 0, "bar": 1, "position": 0, "text": "Allegro"},
        {"op": "add-line", "staff": 0, "bar": 40, "position": 512, "duration": 3584,
         "styleId": "line.system.tempo.rall"},
        {"op": "add-line", "staff": 2, "bar": 3, "position": 0, "duration": 512,
         "styleId": "line.staff.hairpin.crescendo", "voice": 2},
    ])
    assert batch[2]["styleId"] == "text.system.tempo"
    assert batch[3] == {"op": "add-line", "staff": 0, "bar": 40, "position": 512,
                        "styleId": "line.system.tempo.rall", "duration": 3584}
    assert batch[4]["voice"] == 2


def test_system_staff_ops_need_bridge_48() -> None:
    from sibelius_websocket_cli.cli import SYSTEM_STAFF_BRIDGE_VERSION, _batch_bridge_version

    system_text = validate_batch([{"op": "delete", "staff": 0, "bar": 1, "index": 0}])
    staff_line = validate_batch([{"op": "add-line", "staff": 1, "bar": 1, "position": 0,
                                  "duration": 0, "styleId": "line.staff.hairpin.crescendo"}])
    staff_text = validate_batch([{"op": "delete", "staff": 1, "bar": 1, "index": 0}])
    assert _batch_bridge_version(system_text) == SYSTEM_STAFF_BRIDGE_VERSION
    assert _batch_bridge_version(staff_line) == SYSTEM_STAFF_BRIDGE_VERSION
    assert _batch_bridge_version(staff_text) < SYSTEM_STAFF_BRIDGE_VERSION


def test_rejects_empty_batch_and_use_after_delete() -> None:
    with pytest.raises(BatchError, match="non-empty"):
        validate_batch([])
    with pytest.raises(BatchError, match="earlier op deletes"):
        validate_batch([
            {"op": "delete", "staff": 1, "bar": 1, "index": 2},
            {"op": "flip-stem", "staff": 1, "bar": 1, "index": 2},
        ])


def test_note_patches_translate_to_batch_operations() -> None:
    batch = batch_operations([
        {"op": "set-pitch", "staff": 1, "bar": 2, "index": 0, "oldPitch": 60, "newPitch": 62},
        {"op": "tie", "staff": 1, "bar": 2, "index": 1, "remove": True},
        {"op": "delete-voice", "staff": 2, "fromBar": 1, "toBar": 3, "voice": 2},
        {"op": "flip-stem", "staff": 1, "bar": 3, "index": 0},
    ])
    assert [op["op"] for op in batch] == ["set-pitch", "tie", "delete-voice", "flip-stem"]
    with pytest.raises(BatchError, match="structural ops must come last"):
        validate_batch(batch)
    ordered = validate_batch(batch_operations(execution_order(batch)))
    assert ordered[1]["tied"] is False and ordered[-1]["op"] == "delete-voice"


def test_nudge_is_relative_and_defaults_to_zero() -> None:
    batch = validate_batch([{"op": "nudge", "staff": 1, "bar": 2, "index": 0, "dx": -16}])
    assert batch == [{"op": "nudge", "staff": 1, "bar": 2, "index": 0, "dx": -16, "dy": 0}]
    with pytest.raises(BatchError, match="dy must be an integer"):
        validate_batch([{"op": "nudge", "staff": 1, "bar": 2, "index": 0, "dy": 1.5}])


def test_structural_ops_normalize() -> None:
    batch = validate_batch([
        {"op": "beam", "staff": 1, "bar": 2, "firstIndex": 0, "lastIndex": 3},
        {"op": "transpose", "fromBar": 1, "toBar": 4, "topStaff": 1, "bottomStaff": 2,
         "fromNote": "C", "toNote": "D", "direction": "up", "octaves": 1},
        {"op": "transpose", "fromBar": 1, "toBar": 1, "topStaff": 1, "bottomStaff": 1,
         "degree": -2, "intervalType": 4},
        {"op": "copy-passage", "fromBar": 1, "toBar": 2, "topStaff": 1, "bottomStaff": 1,
         "destStaff": 2, "destBar": 3},
        {"op": "set-time", "bar": 4, "numerator": 2, "denominator": 2, "symbol": "cut"},
        {"op": "set-key", "bar": 1, "key": "F#", "minor": True},
        {"op": "set-break", "bar": 2, "type": "page"},
        {"op": "set-barline", "bar": 4, "type": "final"},
        {"op": "delete-voice", "fromBar": 1, "toBar": 4, "staff": 1, "voice": 2},
        {"op": "add-bars", "count": 2},
    ])
    assert batch[1]["degree"] == 8 and batch[1]["intervalType"] == 5
    assert batch[2] == {"op": "transpose", "fromBar": 1, "toBar": 1, "topStaff": 1, "bottomStaff": 1,
                        "degree": -2, "intervalType": 4}
    assert batch[3]["destPosition"] == 0
    assert batch[4]["symbol"] is True
    assert batch[5]["major"] is False


BAR_RANGE = {"fromBar": 1, "toBar": 2, "topStaff": 1, "bottomStaff": 1}


@pytest.mark.parametrize(
    ("operation", "message"),
    [
        ({"op": "set-time", "bar": 1, "numerator": 0, "denominator": 4}, "numerator must be"),
        ({"op": "set-time", "bar": 1, "numerator": 4, "denominator": 3}, "power of two"),
        ({"op": "set-time", "bar": 1, "numerator": 3, "denominator": 4, "symbol": "common"}, "requires 4/4"),
        ({"op": "set-key", "bar": 1, "key": "H#"}, "major key"),
        ({"op": "set-key", "bar": 1, "key": "Db", "minor": True}, "minor key"),
        ({"op": "transpose", **BAR_RANGE, "degree": 70, "intervalType": 5}, "degree must be"),
        ({"op": "transpose", **BAR_RANGE, "degree": 1, "intervalType": 11}, "intervalType must be"),
        ({"op": "transpose", **BAR_RANGE, "fromNote": "C", "toNote": "D"}, "direction"),
        ({"op": "transpose", **BAR_RANGE, "fromNote": "C", "toNote": "D", "direction": "up",
          "octaves": 3}, "octaves must be"),
        ({"op": "copy-passage", **BAR_RANGE, "toBar": 0, "destStaff": 1, "destBar": 1}, "toBar must be"),
        ({"op": "add-bars", "count": 0}, "count must be"),
        ({"op": "set-break", "bar": 1, "type": "column"}, "type must be one of"),
        ({"op": "set-barline", "bar": 1}, "type must be one of"),
        ({"op": "beam", "staff": 1, "bar": 1, "firstIndex": 2, "lastIndex": 2}, "after firstIndex"),
    ],
)
def test_structural_rejects(operation, message) -> None:
    with pytest.raises(BatchError, match=message):
        validate_batch([operation])


def test_structural_ops_must_come_last() -> None:
    with pytest.raises(BatchError, match="structural ops must come last"):
        validate_batch([
            {"op": "set-break", "bar": 2, "type": "system"},
            {"op": "flip-stem", "staff": 1, "bar": 1, "index": 0},
        ])
    with pytest.raises(BatchError, match="structural ops must come last"):
        validate_batch([
            {"op": "add-bars", "count": 1},
            {"op": "beam", "staff": 1, "bar": 1, "firstIndex": 0, "lastIndex": 1},
        ])


def test_no_bar_after_a_set_time_bar() -> None:
    validate_batch([
        {"op": "set-time", "bar": 3, "numerator": 3, "denominator": 4},
        {"op": "set-barline", "bar": 3, "type": "double"},
        {"op": "set-break", "bar": 2, "type": "system"},
    ])
    with pytest.raises(BatchError, match="earlier set-time or add-bars moves"):
        validate_batch([
            {"op": "set-time", "bar": 3, "numerator": 3, "denominator": 4},
            {"op": "delete-voice", "fromBar": 1, "toBar": 4, "staff": 1, "voice": 2},
        ])


def test_beam_rejects_a_deleted_object() -> None:
    with pytest.raises(BatchError, match="earlier op deletes"):
        validate_batch([
            {"op": "delete", "staff": 1, "bar": 1, "index": 2},
            {"op": "beam", "staff": 1, "bar": 1, "firstIndex": 0, "lastIndex": 3},
        ])


def test_set_time_must_precede_key_break_and_barline() -> None:
    with pytest.raises(BatchError, match="set-time must come first"):
        validate_batch([
            {"op": "set-barline", "bar": 2, "type": "double"},
            {"op": "set-time", "bar": 3, "numerator": 3, "denominator": 4},
        ])


def test_barline_names_match_set_barline_types() -> None:
    from sibelius_websocket_cli.batch_ops import BARLINE_NAMES, BARLINE_TYPES
    assert set(BARLINE_NAMES) | {"none"} == BARLINE_TYPES


def test_layout_batch_ops_validate_and_need_bridge_50() -> None:
    from sibelius_websocket_cli.cli import LAYOUT_BATCH_BRIDGE_VERSION, _batch_bridge_version

    batch = validate_batch([
        {"op": "set", "staff": 1, "bar": 2, "index": 1, "prop": "NumNotes", "value": 3},
        {"op": "set-bar-number", "bar": 5, "number": 1, "skip": True},
        {"op": "set-layout", "pageSize": "letter", "orientation": "landscape",
         "staffSize": 6.5, "spacesBetweenSystems": 10},
        {"op": "add-bars", "count": 1, "bar": 3, "length": 256},
    ])
    assert batch[1] == {"op": "set-bar-number", "bar": 5, "number": 1, "skip": True}
    assert batch[2] == {"op": "set-layout", "pageSize": 0, "orientation": 1,
                        "staffSize": 6.5, "spacesBetweenSystems": 10,
                        "settings": ["pageSize", "orientation", "staffSize", "spacesBetweenSystems"]}
    assert batch[3] == {"op": "add-bars", "count": 1, "bar": 3, "length": 256}
    for ops in ([batch[0]], [batch[1]], [batch[2]], [batch[3]]):
        assert _batch_bridge_version(ops) == LAYOUT_BATCH_BRIDGE_VERSION
    plain = validate_batch([{"op": "add-bars", "count": 2}])
    assert plain == [{"op": "add-bars", "count": 2}]
    assert _batch_bridge_version(plain) < LAYOUT_BATCH_BRIDGE_VERSION


@pytest.mark.parametrize(("op", "match"), [
    ({"op": "set-layout"}, "at least one setting"),
    ({"op": "set-layout", "pageSize": "custom"}, "pageSize must be one of"),
    ({"op": "set-layout", "staffSize": 0}, "staffSize must be a number"),
    ({"op": "set-layout", "topMargin": True}, "topMargin must be a number"),
    ({"op": "set-layout", "margin": 10}, "unknown set-layout fields"),
    ({"op": "set-bar-number", "bar": 1, "number": 0}, "number"),
    ({"op": "set-bar-number", "bar": 1, "number": 2, "skip": 1}, "skip must be boolean"),
    ({"op": "add-bars", "count": 1, "length": 0}, "length"),
])
def test_layout_batch_ops_reject_bad_values(op: dict, match: str) -> None:
    with pytest.raises(BatchError, match=match):
        validate_batch([op])


def test_no_bar_at_or_after_an_insertion() -> None:
    insert = {"op": "add-bars", "count": 1, "bar": 4}
    validate_batch([insert, {"op": "set-break", "bar": 3, "type": "system"}])
    with pytest.raises(BatchError, match="add-bars moves"):
        validate_batch([insert, {"op": "set-break", "bar": 4, "type": "system"}])
    validate_batch([{"op": "add-bars", "count": 1}, {"op": "set-break", "bar": 40, "type": "system"}])


def test_structure_names_layout_constants() -> None:
    named = name_structure({"layout": {"pageSize": 4, "orientation": 0, "staffSize": 7},
                            "engraving": {"spacesBetweenStaves": 4}})
    assert named["layout"] == {"pageSize": "a4", "orientation": "portrait", "staffSize": 7}
    assert name_structure({"layout": {"pageSize": 18, "orientation": 1}})["layout"]["pageSize"] == "custom"


def test_set_layout_names_zero_valued_settings() -> None:
    # ManuScript reads 0 as null, so "letter", "portrait" and zero margins
    # must reach the plug-in by name.
    [op] = validate_batch([{"op": "set-layout", "pageSize": "letter", "orientation": "portrait",
                            "topMargin": 0}])
    assert op["settings"] == ["pageSize", "orientation", "topMargin"]
    assert (op["pageSize"], op["orientation"], op["topMargin"]) == (0, 0, 0)
