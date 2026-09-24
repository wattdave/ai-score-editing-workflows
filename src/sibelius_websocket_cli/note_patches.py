"""Validation and safe ordering for batched Sibelius note patches."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class NotePatchError(ValueError):
    """A note patch file is malformed or contains an unsupported operation."""


_OPERATIONS = {"set-pitch", "tie", "bracket", "flip-stem", "delete", "delete-voice"}
_ADDRESSED = {"set-pitch", "tie", "bracket", "flip-stem", "delete"}


def load_note_patches(path: str) -> list[dict[str, Any]]:
    """Load and validate a non-empty JSON array of note operations."""
    source = Path(path).expanduser()
    try:
        payload = json.loads(source.read_text())
    except OSError as exc:
        raise NotePatchError(f"cannot read note patch file {source}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise NotePatchError(f"invalid JSON in note patch file {source}: {exc}") from exc
    if not isinstance(payload, list) or not payload:
        raise NotePatchError("note patch file must contain a non-empty JSON array")
    for index, operation in enumerate(payload):
        _validate_operation(operation, index)
    _reject_duplicate_deletes(payload)
    return payload


def execution_order(operations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Order operations so every address stays valid while the batch runs.

    All addresses refer to the score as read before the batch. Non-deleting
    operations run first, in file order; addressed deletes follow in
    descending index order within each bar, so no deletion shifts a later
    target; range-based voice deletions run last.
    """
    edits = [op for op in operations if op["op"] not in {"delete", "delete-voice"}]
    deletes = sorted(
        (op for op in operations if op["op"] == "delete"),
        key=lambda op: (op["staff"], op["bar"], -op["index"]),
    )
    voices = [op for op in operations if op["op"] == "delete-voice"]
    return edits + deletes + voices


def delete_voice_call(operation: dict[str, Any]) -> tuple[str, list[Any]]:
    """Return the bridge method and arguments for a delete-voice operation.

    delete-voice works through a selection rather than an object address, so
    it runs outside the ApplyBatch batch that carries every other operation.
    """
    return "DeleteVoiceInPassage", [
        operation["fromBar"], operation["toBar"], operation["staff"], operation["voice"],
    ]


def _validate_operation(operation: Any, index: int) -> None:
    label = f"operation {index + 1}"
    if not isinstance(operation, dict):
        raise NotePatchError(f"{label} must be an object")
    op = operation.get("op")
    if op not in _OPERATIONS:
        raise NotePatchError(f"{label}.op must be one of: {', '.join(sorted(_OPERATIONS))}")

    _positive_int(operation, "staff", label)
    if op in _ADDRESSED:
        _positive_int(operation, "bar", label)
        _nonnegative_int(operation, "index", label)
    if op == "set-pitch":
        old = _pitch(operation, "oldPitch", label)
        new = _pitch(operation, "newPitch", label)
        if old == new:
            raise NotePatchError(f"{label} set-pitch must change the pitch")
    elif op in {"tie", "bracket"}:
        if not isinstance(operation.get("remove", False), bool):
            raise NotePatchError(f"{label}.remove must be boolean")
    elif op == "delete-voice":
        first = _positive_int(operation, "fromBar", label)
        last = _positive_int(operation, "toBar", label)
        if last < first:
            raise NotePatchError(f"{label}.toBar must not precede fromBar")
        if operation.get("voice") not in {1, 2, 3, 4}:
            raise NotePatchError(f"{label}.voice must be 1, 2, 3, or 4")


def _reject_duplicate_deletes(operations: list[dict[str, Any]]) -> None:
    seen: set[tuple[int, int, int]] = set()
    for operation in operations:
        if operation["op"] != "delete":
            continue
        address = (operation["staff"], operation["bar"], operation["index"])
        if address in seen:
            raise NotePatchError(f"duplicate delete at staff {address[0]} bar {address[1]} index {address[2]}")
        seen.add(address)


def _integer(operation: dict[str, Any], field: str, label: str) -> int:
    value = operation.get(field)
    if isinstance(value, bool) or not isinstance(value, int):
        raise NotePatchError(f"{label}.{field} must be an integer")
    return value


def _positive_int(operation: dict[str, Any], field: str, label: str) -> int:
    value = _integer(operation, field, label)
    if value < 1:
        raise NotePatchError(f"{label}.{field} must be positive")
    return value


def _nonnegative_int(operation: dict[str, Any], field: str, label: str) -> int:
    value = _integer(operation, field, label)
    if value < 0:
        raise NotePatchError(f"{label}.{field} must be non-negative")
    return value


def _pitch(operation: dict[str, Any], field: str, label: str) -> int:
    value = _integer(operation, field, label)
    if not 0 <= value <= 127:
        raise NotePatchError(f"{label}.{field} must be a MIDI pitch from 0 to 127")
    return value


def batch_operations(operations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Translate addressed note operations into ApplyBatch operations.

    delete-voice works through a selection rather than an object address, so
    it is not part of the batch; run it afterwards with delete_voice_call.
    """
    batch: list[dict[str, Any]] = []
    for operation in operations:
        op = operation["op"]
        if op == "delete-voice":
            continue
        out = {"op": op, "staff": operation["staff"], "bar": operation["bar"], "index": operation["index"]}
        if op == "set-pitch":
            out.update(oldPitch=operation["oldPitch"], newPitch=operation["newPitch"])
        elif op in {"tie", "bracket"}:
            out["remove"] = operation.get("remove", False)
        batch.append(out)
    return batch
