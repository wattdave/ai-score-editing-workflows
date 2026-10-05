"""Tests for validated batched layout operations."""

import json

import pytest

from ai_score_editing.layout import LayoutPatchError, load_layout_patches


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


def test_set_time_accepts_symbol_matching_meter(tmp_path) -> None:
    path = tmp_path / "layout.json"
    path.write_text(json.dumps([
        {"op": "set-time", "bar": 1, "top": 2, "bottom": 2, "symbol": "cut"},
        {"op": "set-time", "bar": 5, "top": 3, "bottom": 4},
    ]))

    assert len(load_layout_patches(str(path))) == 2


@pytest.mark.parametrize(
    "operation, message",
    [
        ({"op": "set-time", "bar": 1, "top": 3, "bottom": 4, "symbol": "cut"}, "requires 2/2"),
        ({"op": "set-time", "bar": 1, "top": 4, "bottom": 4, "symbol": "breve"}, "symbol must be one of"),
        ({"op": "set-time", "bar": 1, "top": 3, "bottom": 5}, "power of two"),
    ],
)
def test_set_time_rejects_invalid_signatures(tmp_path, operation, message) -> None:
    path = tmp_path / "layout.json"
    path.write_text(json.dumps([operation]))

    with pytest.raises(LayoutPatchError, match=message):
        load_layout_patches(str(path))
