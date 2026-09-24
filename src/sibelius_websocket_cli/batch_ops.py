"""Validation for batches run by the bridge's ApplyBatch handler.

A batch is a JSON array of operations. Addressed operations name an existing
bar object by staff, bar and index (as `query` and `read` report it, before
the batch runs) and may guard it with the expected `type` and `position`.
The bridge resolves every address before the first edit and applies the
whole batch as one undo step. Operations run in file order.

Structural operations (transpose, copy-passage, key and time signatures,
breaks, barlines, add-bars, delete-voice) work on bar ranges or the whole
score. They can replace or renumber the objects an address points at, so they
must come after every object operation. Their bars are checked against the
score before the batch; a set-time re-bars what follows it, so no later
operation may name a bar after its bar. Re-barring also erased a special
barline just before it (SPEC.md 1.3.1), so every set-time must come before any
set-key, set-break or set-barline.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .intervals import compute_transposition

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
STRUCTURAL = {
    "transpose", "copy-passage", "set-key", "set-time", "set-break",
    "set-barline", "add-bars", "delete-voice",
}
OPERATIONS = ADDRESSED | ADDING | STRUCTURAL | {"beam"}
DEFAULT_TEXT_STYLE = "text.staff.expression"

# AddKeySignatureFromText turns an unknown name into C major without an error
# (SPEC.md 1.3.1), so only the fifteen standard keys of each mode are allowed.
MAJOR_KEYS = {"C", "G", "D", "A", "E", "B", "F#", "C#", "F", "Bb", "Eb", "Ab", "Db", "Gb", "Cb"}
MINOR_KEYS = {"A", "E", "B", "F#", "C#", "G#", "D#", "A#", "D", "G", "C", "F", "Bb", "Eb", "Ab"}
TIME_SYMBOLS = {"common": (4, 4), "cut": (2, 2)}
BREAK_TYPES = {"system", "page", "none"}
BARLINE_TYPES = {
    "double", "start_repeat", "end_repeat", "final", "dashed", "invisible",
    "between_staves", "normal", "tick", "short", "dotted", "triple", "thick", "none",
}
# SpecialBarline internal types 0-12, in order, as set-barline names.
BARLINE_NAMES = [
    "start_repeat", "end_repeat", "dashed", "double", "final", "invisible",
    "between_staves", "normal", "tick", "short", "dotted", "triple", "thick",
]
# Bar.BreakType values other than Default (7), as set-break names where one
# exists; the rest keep their ManuScript constant names.
BREAK_NAMES = {
    6: "system", 4: "page", 1: "MiddleOfSystem", 2: "EndOfSystem",
    3: "MiddleOfPage", 5: "NotEndOfSystem", 8: "SpecialPageBreak",
}

# Selection.Transpose shows a modal dialog for out-of-range arguments
# (SPEC.md 1.3.1). Interval types run 0-10; degrees are held to three octaves.
MAX_TRANSPOSE_DEGREE = 21
MAX_ADD_BARS = 1000


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
    _check_structural_order(normalized)
    return normalized


def _validate(operation: Any, i: int) -> dict[str, Any]:
    label = f"op {i}"
    if not isinstance(operation, dict):
        raise BatchError(f"{label} must be an object")
    op = operation.get("op")
    if op not in OPERATIONS:
        raise BatchError(f"{label}.op must be one of: {', '.join(sorted(OPERATIONS))}")
    if op in STRUCTURAL:
        return _validate_structural(operation, op, label)
    out: dict[str, Any] = {"op": op}
    out["staff"] = _int(operation, "staff", label, minimum=1)
    out["bar"] = _int(operation, "bar", label, minimum=1)

    if op == "beam":
        out["firstIndex"] = _int(operation, "firstIndex", label, minimum=0)
        out["lastIndex"] = _int(operation, "lastIndex", label, minimum=0)
        if out["lastIndex"] <= out["firstIndex"]:
            raise BatchError(f"{label}.lastIndex must be after firstIndex")
        return out

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


def _validate_structural(operation: dict[str, Any], op: str, label: str) -> dict[str, Any]:
    out: dict[str, Any] = {"op": op}
    if op in {"transpose", "copy-passage", "delete-voice"}:
        out["fromBar"] = _int(operation, "fromBar", label, minimum=1)
        out["toBar"] = _int(operation, "toBar", label, minimum=out["fromBar"])
    if op in {"transpose", "copy-passage"}:
        out["topStaff"] = _int(operation, "topStaff", label, minimum=1)
        out["bottomStaff"] = _int(operation, "bottomStaff", label, minimum=out["topStaff"])
    if op in {"set-key", "set-time", "set-break", "set-barline"}:
        out["bar"] = _int(operation, "bar", label, minimum=1)

    if op == "transpose":
        out.update(_transposition(operation, label))
    elif op == "copy-passage":
        out["destStaff"] = _int(operation, "destStaff", label, minimum=1)
        out["destBar"] = _int(operation, "destBar", label, minimum=1)
        out["destPosition"] = _int({"destPosition": 0, **operation}, "destPosition", label, minimum=0)
    elif op == "delete-voice":
        out["staff"] = _int(operation, "staff", label, minimum=1)
        out["voice"] = _int(operation, "voice", label, minimum=1, maximum=4)
    elif op == "set-key":
        key = _str(operation, "key", label)
        minor = operation.get("minor", False)
        if not isinstance(minor, bool):
            raise BatchError(f"{label}.minor must be boolean")
        keys = MINOR_KEYS if minor else MAJOR_KEYS
        if key not in keys:
            mode = "minor" if minor else "major"
            raise BatchError(f"{label}.key must be a {mode} key: {', '.join(sorted(keys))}")
        out.update(key=key, major=not minor)
    elif op == "set-time":
        # AddTimeSignature with a zero numerator crashes Sibelius (SPEC.md 1.3.1).
        top = _int(operation, "numerator", label, minimum=1, maximum=64)
        bottom = _int(operation, "denominator", label, minimum=1, maximum=64)
        if bottom & (bottom - 1):
            raise BatchError(f"{label}.denominator must be a power of two up to 64")
        symbol = operation.get("symbol")
        if symbol is not None:
            if symbol not in TIME_SYMBOLS:
                raise BatchError(f"{label}.symbol must be one of: {', '.join(sorted(TIME_SYMBOLS))}")
            if TIME_SYMBOLS[symbol] != (top, bottom):
                raise BatchError(f"{label}.symbol {symbol} requires {'/'.join(map(str, TIME_SYMBOLS[symbol]))}")
        out.update(numerator=top, denominator=bottom, symbol=symbol is not None)
    elif op == "set-break":
        out["type"] = _choice(operation, "type", label, BREAK_TYPES)
    elif op == "set-barline":
        out["type"] = _choice(operation, "type", label, BARLINE_TYPES)
    elif op == "add-bars":
        out["count"] = _int(operation, "count", label, minimum=1, maximum=MAX_ADD_BARS)
    return out


def _transposition(operation: dict[str, Any], label: str) -> dict[str, int]:
    """Accept degree and intervalType, or fromNote/toNote/direction[/octaves]."""
    if "fromNote" in operation or "toNote" in operation:
        direction = operation.get("direction")
        if direction not in {"up", "down"}:
            raise BatchError(f"{label}.direction must be 'up' or 'down'")
        octaves = _int({"octaves": 0, **operation}, "octaves", label, minimum=0, maximum=2)
        try:
            degree, interval_type = compute_transposition(
                _str(operation, "fromNote", label), _str(operation, "toNote", label), direction == "up"
            )
        except (KeyError, ValueError) as exc:
            raise BatchError(f"{label}: {exc}") from exc
        degree += 7 * octaves * (1 if direction == "up" else -1)
    else:
        degree = _int(operation, "degree", label, minimum=-MAX_TRANSPOSE_DEGREE, maximum=MAX_TRANSPOSE_DEGREE)
        interval_type = _int(operation, "intervalType", label, minimum=0, maximum=10)
    if abs(degree) > MAX_TRANSPOSE_DEGREE:
        raise BatchError(f"{label} transposes more than {MAX_TRANSPOSE_DEGREE // 7} octaves")
    return {"degree": degree, "intervalType": interval_type}


def _bars_named(operation: dict[str, Any]) -> list[int]:
    return [operation[f] for f in ("bar", "fromBar", "toBar", "destBar") if f in operation]


def _check_structural_order(operations: list[dict[str, Any]]) -> None:
    first_structural: int | None = None
    rebarred_after: int | None = None
    marked: int | None = None
    for i, operation in enumerate(operations):
        if operation["op"] not in STRUCTURAL:
            if first_structural is not None:
                raise BatchError(
                    f"op {i} ({operation['op']}) comes after structural op {first_structural} "
                    f"({operations[first_structural]['op']}); structural ops must come last"
                )
            continue
        if first_structural is None:
            first_structural = i
        if rebarred_after is not None and any(b > rebarred_after for b in _bars_named(operation)):
            raise BatchError(
                f"op {i} names a bar after bar {rebarred_after}, which an earlier set-time re-bars"
            )
        if operation["op"] in {"set-key", "set-break", "set-barline"}:
            marked = i
        if operation["op"] == "set-time" and marked is not None:
            raise BatchError(
                f"op {i} (set-time) comes after op {marked} ({operations[marked]['op']}); "
                "re-barring can erase key signatures, breaks and barlines, so set-time must come first"
            )
        if operation["op"] == "set-time":
            bar = operation["bar"]
            rebarred_after = bar if rebarred_after is None else min(rebarred_after, bar)


def _reject_use_after_delete(operations: list[dict[str, Any]]) -> None:
    deleted: set[tuple[int, int, int]] = set()
    for i, operation in enumerate(operations):
        if operation["op"] == "beam":
            indices = range(operation["firstIndex"], operation["lastIndex"] + 1)
        elif operation["op"] in ADDRESSED:
            indices = range(operation["index"], operation["index"] + 1)
        else:
            continue
        for index in indices:
            address = (operation["staff"], operation["bar"], index)
            if address in deleted:
                raise BatchError(
                    f"op {i} targets staff {address[0]} bar {address[1]} index {address[2]}, "
                    "which an earlier op deletes"
                )
        if operation["op"] == "delete":
            deleted.add((operation["staff"], operation["bar"], operation["index"]))


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


def _choice(operation: dict[str, Any], field: str, label: str, choices: set[str]) -> str:
    value = operation.get(field)
    if value not in choices:
        raise BatchError(f"{label}.{field} must be one of: {', '.join(sorted(choices))}")
    return value


def _str(operation: dict[str, Any], field: str, label: str) -> str:
    value = operation.get(field)
    if not isinstance(value, str) or not value:
        raise BatchError(f"{label}.{field} must be a non-empty string")
    return value


def name_structure(structure: dict[str, Any]) -> dict[str, Any]:
    """Give GetScoreStructure's barlines and breaks the names apply_batch takes."""
    named = dict(structure)
    named["barlines"] = [
        {"bar": b["bar"], "type": _barline_name(b["internalType"]), "position": b["position"]}
        for b in structure.get("barlines", [])
    ]
    named["breaks"] = [
        {"bar": b["bar"], "type": BREAK_NAMES.get(int(b["breakType"]), str(b["breakType"]))}
        for b in structure.get("breaks", [])
    ]
    return named


def _barline_name(internal_type: Any) -> str:
    try:
        return BARLINE_NAMES[int(internal_type)]
    except (ValueError, IndexError):
        return str(internal_type)
