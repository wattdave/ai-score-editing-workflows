"""Validation for batches run by the bridge's ApplyBatch handler.

A batch is a JSON array of operations. Addressed operations name an existing
bar object by staff, bar and index (as `query` and `read` report it, before
the batch runs) and may guard it with the expected `type` and `position`.
The bridge resolves every address before the first edit and applies the
whole batch as one undo step. Operations run in file order.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Properties 'set' may write, per object kind, with the JSON type each takes.
# Mirrors BatchWritableTable in sibwscli.plg (a test keeps them in sync). The
# plug-in cannot check value types, and a wrongly typed write raises a modal
# dialog in Sibelius, so the types are enforced here.
COMMON_WRITABLE: dict[str, type] = {"Dx": int, "Dy": int, "Hidden": bool, "CueSize": bool}
WRITABLE_PROPS: dict[str, dict[str, type]] = {
    "NoteRest": {"Beam": int, "RestPosition": int},
    "LyricItem": {"Text": str, "Duration": int},
    "Text": {"Text": str},
    "Line": {"Duration": int, "RhDx": int},
}

ADDRESSED = {"set", "set-pitch", "tie", "bracket", "flip-stem", "delete", "nudge"}
ADDING = {"add-note", "add-text", "add-lyric"}
OPERATIONS = ADDRESSED | ADDING
DEFAULT_TEXT_STYLE = "text.staff.expression"


class BatchError(ValueError):
    """A batch file is malformed or contains an unsupported operation."""


def load_batch(path: str) -> list[dict[str, Any]]:
    source = Path(path).expanduser()
    try:
        payload = json.loads(source.read_text())
    except OSError as exc:
        raise BatchError(f"cannot read batch file {source}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise BatchError(f"invalid JSON in batch file {source}: {exc}") from exc
    return validate_batch(payload)


def validate_batch(payload: Any) -> list[dict[str, Any]]:
    """Validate a batch and return it normalized for the bridge."""
    if not isinstance(payload, list) or not payload:
        raise BatchError("a batch must be a non-empty JSON array")
    normalized = [_validate(operation, i) for i, operation in enumerate(payload)]
    _reject_use_after_delete(normalized)
    return normalized


def _validate(operation: Any, i: int) -> dict[str, Any]:
    label = f"op {i}"
    if not isinstance(operation, dict):
        raise BatchError(f"{label} must be an object")
    op = operation.get("op")
    if op not in OPERATIONS:
        raise BatchError(f"{label}.op must be one of: {', '.join(sorted(OPERATIONS))}")
    out: dict[str, Any] = {"op": op}
    out["staff"] = _int(operation, "staff", label, minimum=1)
    out["bar"] = _int(operation, "bar", label, minimum=1)

    if op in ADDRESSED:
        out["index"] = _int(operation, "index", label, minimum=0)
        if "type" in operation:
            out["type"] = _str(operation, "type", label)
        if "position" in operation:
            out["position"] = _int(operation, "position", label, minimum=0)
    else:
        out["position"] = _int(operation, "position", label, minimum=0)
        if "voice" in operation:
            out["voice"] = _int(operation, "voice", label, minimum=1, maximum=4)

    if op == "set":
        prop = _str(operation, "prop", label)
        expected = _writable_type(prop)
        if expected is None:
            raise BatchError(f"{label}: {prop!r} is not writable; writable: {', '.join(sorted(_all_writable()))}")
        value = operation.get("value")
        if not _is_type(value, expected):
            raise BatchError(f"{label}.value for {prop} must be {expected.__name__}")
        out.update(prop=prop, value=value)
    elif op == "set-pitch":
        old = _int(operation, "oldPitch", label, minimum=0, maximum=127)
        new = _int(operation, "newPitch", label, minimum=0, maximum=127)
        if old == new:
            raise BatchError(f"{label} set-pitch must change the pitch")
        out.update(oldPitch=old, newPitch=new)
    elif op in {"tie", "bracket"}:
        remove = operation.get("remove", False)
        if not isinstance(remove, bool):
            raise BatchError(f"{label}.remove must be boolean")
        out["tied" if op == "tie" else "bracketed"] = not remove
    elif op == "nudge":
        for field in ("dx", "dy"):
            value = operation.get(field, 0)
            if not _is_type(value, int):
                raise BatchError(f"{label}.{field} must be an integer")
            out[field] = value
    elif op == "add-note":
        pitches = operation.get("pitches")
        if not isinstance(pitches, list) or not pitches or not all(
            _is_type(p, int) and 0 <= p <= 127 for p in pitches
        ):
            raise BatchError(f"{label}.pitches must be a non-empty array of MIDI pitches")
        out["pitches"] = pitches
        out["duration"] = _int(operation, "duration", label, minimum=1)
        tied = operation.get("tied", False)
        if not isinstance(tied, bool):
            raise BatchError(f"{label}.tied must be boolean")
        out["tied"] = tied
    elif op == "add-text":
        out["text"] = _str(operation, "text", label)
        style = operation.get("styleId", DEFAULT_TEXT_STYLE)
        if not isinstance(style, str) or not style.startswith("text.staff."):
            raise BatchError(f"{label}.styleId must be a staff text style id, e.g. {DEFAULT_TEXT_STYLE}")
        out["styleId"] = style
    elif op == "add-lyric":
        out["text"] = _str(operation, "text", label)
        out["duration"] = _int(operation, "duration", label, minimum=1)
        syllable = operation.get("syllableType", "end")
        if syllable not in {"end", "middle"}:
            raise BatchError(f"{label}.syllableType must be 'end' or 'middle'")
        out["syllableType"] = syllable
    return out


def _reject_use_after_delete(operations: list[dict[str, Any]]) -> None:
    deleted: set[tuple[int, int, int]] = set()
    for i, operation in enumerate(operations):
        if operation["op"] not in ADDRESSED:
            continue
        address = (operation["staff"], operation["bar"], operation["index"])
        if address in deleted:
            raise BatchError(
                f"op {i} targets staff {address[0]} bar {address[1]} index {address[2]}, "
                "which an earlier op deletes"
            )
        if operation["op"] == "delete":
            deleted.add(address)


def _all_writable() -> set[str]:
    names = set(COMMON_WRITABLE)
    for props in WRITABLE_PROPS.values():
        names |= set(props)
    return names


def _writable_type(prop: str) -> type | None:
    if prop in COMMON_WRITABLE:
        return COMMON_WRITABLE[prop]
    for props in WRITABLE_PROPS.values():
        if prop in props:
            return props[prop]
    return None


def _is_type(value: Any, expected: type) -> bool:
    if expected is int:
        return isinstance(value, int) and not isinstance(value, bool)
    return isinstance(value, expected)


def _int(
    operation: dict[str, Any], field: str, label: str, *, minimum: int, maximum: int | None = None
) -> int:
    value = operation.get(field)
    if not isinstance(value, int) or isinstance(value, bool):
        raise BatchError(f"{label}.{field} must be an integer")
    if value < minimum or (maximum is not None and value > maximum):
        bound = f"{minimum}-{maximum}" if maximum is not None else f">= {minimum}"
        raise BatchError(f"{label}.{field} must be {bound}")
    return value


def _str(operation: dict[str, Any], field: str, label: str) -> str:
    value = operation.get(field)
    if not isinstance(value, str) or not value:
        raise BatchError(f"{label}.{field} must be a non-empty string")
    return value
