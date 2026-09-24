"""Tests for ApplyBatch operation validation and the writable allow-list."""

import re
from pathlib import Path

import pytest

from sibelius_websocket_cli.batch_ops import (
    COMMON_WRITABLE,
    DEFAULT_TEXT_STYLE,
    WRITABLE_PROPS,
    BatchError,
    validate_batch,
)
from sibelius_websocket_cli.note_patches import batch_operations

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
        ({"op": "delete", "staff": 0, "bar": 1, "index": 0}, "staff must be"),
        ({"op": "add-note", "staff": 1, "bar": 1, "position": 0, "duration": 256, "pitches": [128]}, "MIDI"),
        ({"op": "add-text", "staff": 1, "bar": 1, "position": 0, "text": "x", "styleId": "bogus"}, "styleId"),
        ({"op": "add-lyric", "staff": 1, "bar": 1, "position": 0, "duration": 256, "text": "x",
          "voice": 5}, "voice must be"),
    ],
)
def test_validate_rejects(operation, message) -> None:
    with pytest.raises(BatchError, match=message):
        validate_batch([operation])


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
    assert [op["op"] for op in batch] == ["set-pitch", "tie", "flip-stem"]
    assert validate_batch(batch)[1]["tied"] is False


def test_nudge_is_relative_and_defaults_to_zero() -> None:
    batch = validate_batch([{"op": "nudge", "staff": 1, "bar": 2, "index": 0, "dx": -16}])
    assert batch == [{"op": "nudge", "staff": 1, "bar": 2, "index": 0, "dx": -16, "dy": 0}]
    with pytest.raises(BatchError, match="dy must be an integer"):
        validate_batch([{"op": "nudge", "staff": 1, "bar": 2, "index": 0, "dy": 1.5}])
