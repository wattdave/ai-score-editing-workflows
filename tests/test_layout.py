"""Tests for validated batched layout operations."""

import json

import pytest

from sibelius_websocket_cli.layout import LayoutPatchError, load_layout_patches


def test_load_layout_patches_accepts_supported_operations(tmp_path) -> None:
    path = tmp_path / "layout.json"
    path.write_text(
        json.dumps([
            {"op": "nudge", "staff": 1, "bar": 4, "index": 2, "dx": 8},
            {"op": "set-break", "bar": 12, "type": "system"},
            {"op": "set-barline", "bar": 20, "type": "end_repeat"},
            {"op": "reset-design", "lyrics": True},
            {"op": "remove-redundant-clefs", "staff": 3},
        ])
    )

    assert len(load_layout_patches(str(path))) == 5


@pytest.mark.parametrize(
    "payload, message",
    [
        ([], "non-empty"),
        ([{"op": "nudge", "staff": 1, "bar": 1, "index": 0}], "dx or dy"),
        ([{"op": "set-break", "bar": 0}], "positive"),
        ([{"op": "unknown"}], "must be one of"),
    ],
)
def test_load_layout_patches_rejects_invalid_operations(tmp_path, payload, message) -> None:
    path = tmp_path / "layout.json"
    path.write_text(json.dumps(payload))

    with pytest.raises(LayoutPatchError, match=message):
        load_layout_patches(str(path))
