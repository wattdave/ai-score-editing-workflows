"""Validation and compact reporting for batched Sibelius layout patches."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class LayoutPatchError(ValueError):
    """A layout patch file is malformed or contains an unsupported operation."""


_BARLINE_TYPES = {
    "double", "start_repeat", "end_repeat", "final", "dashed", "invisible",
    "between_staves", "normal", "tick", "short", "dotted", "triple", "thick", "none",
}
_BREAK_TYPES = {"system", "page", "none"}
_OPERATIONS = {"nudge", "set-break", "set-barline", "reset-design", "remove-redundant-clefs"}


def load_layout_patches(path: str) -> list[dict[str, Any]]:
    """Load and validate a non-empty JSON array of layout operations."""
    source = Path(path).expanduser()
    try:
        payload = json.loads(source.read_text())
    except OSError as exc:
        raise LayoutPatchError(f"cannot read layout patch file {source}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise LayoutPatchError(f"invalid JSON in layout patch file {source}: {exc}") from exc
    if not isinstance(payload, list) or not payload:
        raise LayoutPatchError("layout patch file must contain a non-empty JSON array")
    for index, operation in enumerate(payload):
        _validate_operation(operation, index)
    return payload


def _validate_operation(operation: Any, index: int) -> None:
    label = f"operation {index + 1}"
    if not isinstance(operation, dict):
        raise LayoutPatchError(f"{label} must be an object")
    op = operation.get("op")
    if op not in _OPERATIONS:
        raise LayoutPatchError(f"{label}.op must be one of: {', '.join(sorted(_OPERATIONS))}")

    if op == "nudge":
        _positive_int(operation, "staff", label)
        _positive_int(operation, "bar", label)
        _nonnegative_int(operation, "index", label)
        _integer(operation, "dx", label, default=0)
        _integer(operation, "dy", label, default=0)
        if operation.get("dx", 0) == 0 and operation.get("dy", 0) == 0:
            raise LayoutPatchError(f"{label} nudge must change dx or dy")
    elif op == "set-break":
        _positive_int(operation, "bar", label)
        if operation.get("type", "system") not in _BREAK_TYPES:
            raise LayoutPatchError(f"{label}.type must be one of: {', '.join(sorted(_BREAK_TYPES))}")
    elif op == "set-barline":
        _positive_int(operation, "bar", label)
        if operation.get("type", "double") not in _BARLINE_TYPES:
            raise LayoutPatchError(f"{label}.type must be one of: {', '.join(sorted(_BARLINE_TYPES))}")
    elif op == "reset-design":
        if not isinstance(operation.get("lyrics", False), bool):
            raise LayoutPatchError(f"{label}.lyrics must be boolean")
    elif op == "remove-redundant-clefs":
        staff = operation.get("staff")
        if staff is not None:
            _positive_int(operation, "staff", label)


def _integer(operation: dict[str, Any], field: str, label: str, *, default: int | None = None) -> int:
    value = operation.get(field, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise LayoutPatchError(f"{label}.{field} must be an integer")
    return value


def _positive_int(operation: dict[str, Any], field: str, label: str) -> int:
    value = _integer(operation, field, label)
    if value < 1:
        raise LayoutPatchError(f"{label}.{field} must be positive")
    return value


def _nonnegative_int(operation: dict[str, Any], field: str, label: str) -> int:
    value = _integer(operation, field, label)
    if value < 0:
        raise LayoutPatchError(f"{label}.{field} must be non-negative")
    return value


def compact_summary(summary: dict[str, Any]) -> str:
    """Render a one-line summary suitable for agent consumption."""
    return json.dumps(summary, ensure_ascii=False, separators=(",", ":"))
