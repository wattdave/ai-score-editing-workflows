"""Tests for validated, safely ordered batched note operations."""

import json

import pytest

from sibelius_websocket_cli.note_patches import (
    NotePatchError,
    bridge_call,
    execution_order,
    load_note_patches,
)


def _write(tmp_path, payload):
    path = tmp_path / "notes.json"
    path.write_text(json.dumps(payload))
    return str(path)


def test_execution_order_runs_edits_then_descending_deletes_then_voices(tmp_path) -> None:
    ops = load_note_patches(_write(tmp_path, [
        {"op": "delete", "staff": 1, "bar": 4, "index": 1},
        {"op": "delete-voice", "staff": 2, "fromBar": 1, "toBar": 3, "voice": 2},
        {"op": "tie", "staff": 1, "bar": 4, "index": 3, "remove": True},
        {"op": "delete", "staff": 1, "bar": 4, "index": 5},
        {"op": "set-pitch", "staff": 1, "bar": 2, "index": 0, "oldPitch": 60, "newPitch": 62},
    ]))

    ordered = execution_order(ops)

    assert [(op["op"], op.get("index")) for op in ordered] == [
        ("tie", 3), ("set-pitch", 0), ("delete", 5), ("delete", 1), ("delete-voice", None),
    ]
    assert bridge_call(ordered[0]) == ("SetTie", [1, 4, 3, "false"])
    assert bridge_call(ordered[-1]) == ("DeleteVoiceInPassage", [1, 3, 2, 2])


@pytest.mark.parametrize(
    "payload, message",
    [
        ([], "non-empty"),
        ([{"op": "unknown", "staff": 1}], "must be one of"),
        ([{"op": "set-pitch", "staff": 1, "bar": 1, "index": 0, "oldPitch": 60, "newPitch": 60}], "change the pitch"),
        ([{"op": "set-pitch", "staff": 1, "bar": 1, "index": 0, "oldPitch": 60, "newPitch": 200}], "MIDI pitch"),
        ([{"op": "tie", "staff": 1, "bar": 1, "index": 0, "remove": "yes"}], "boolean"),
        ([{"op": "delete-voice", "staff": 1, "fromBar": 5, "toBar": 2, "voice": 1}], "precede"),
        ([{"op": "delete", "staff": 1, "bar": 1, "index": 2}] * 2, "duplicate delete"),
    ],
)
def test_load_note_patches_rejects_invalid_operations(tmp_path, payload, message) -> None:
    with pytest.raises(NotePatchError, match=message):
        load_note_patches(_write(tmp_path, payload))


def test_bracket_maps_to_set_bracketed(tmp_path) -> None:
    ops = load_note_patches(_write(tmp_path, [
        {"op": "bracket", "staff": 1, "bar": 8, "index": 1},
        {"op": "bracket", "staff": 1, "bar": 8, "index": 2, "remove": True},
    ]))

    assert bridge_call(ops[0]) == ("SetBracketed", [1, 8, 1, "true"])
    assert bridge_call(ops[1]) == ("SetBracketed", [1, 8, 2, "false"])


def test_bracket_rejects_non_boolean_remove(tmp_path) -> None:
    with pytest.raises(NotePatchError, match="remove must be boolean"):
        load_note_patches(_write(tmp_path, [
            {"op": "bracket", "staff": 1, "bar": 8, "index": 1, "remove": "yes"},
        ]))
