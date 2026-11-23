"""Sibelius-only batch rules: the properties `set` may write, and Sibelius-only ops.

The rest of batch validation is editor-neutral and lives in
``ai_score_editing.core.batch_schema``; this module adds the writable-property
table that mirrors BatchWritableTable in ScoreBridge.plg, and the
``set-staff-mixer`` operation (bridge v68; its sound setting v69) through the ``ExtraOps`` hook.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ai_score_editing.core import batch_schema
from ai_score_editing.core.batch_schema import ExtraOps
from ai_score_editing.core.errors import BatchError

# Properties 'set' may write, per object kind, with the JSON type each takes.
# Mirrors BatchWritableTable in ScoreBridge.plg (a test keeps them in sync). The
# plug-in cannot check value types, and a wrongly typed write raises a modal
# dialog in Sibelius, so the types are enforced here.
COMMON_WRITABLE: dict[str, type] = {"Dx": int, "Dy": int, "Hidden": bool, "CueSize": bool}
WRITABLE_PROPS: dict[str, dict[str, type]] = {
    "NoteRest": {"Beam": int, "RestPosition": int},
    "LyricItem": {"Text": str, "Duration": int, "NumNotes": int},
    "Text": {"Text": str},
    "Line": {"Duration": int, "RhDx": int},
}

#: Characters of Opus Text Std that Sibelius's own Add Ficta plug-in writes above a note.
FICTA_SYMBOLS = {"flat": "b", "sharp": "#", "natural": "\u00a7"}

#: Every writable property with its JSON type, as validate_batch takes it.
WRITABLE: dict[str, type] = {
    **COMMON_WRITABLE,
    **{prop: kind for props in WRITABLE_PROPS.values() for prop, kind in props.items()},
}


#: set-staff-mixer's mute names and the Staff.MuteMode constants they stand for
#: (ManuScript Language Guide, "MuteMode Constants"). rehearsal_mix.MUTE_MODES
#: is the reverse, for display.
MIXER_MUTE_MODES = {"muted": 0, "half-muted": 1, "not-muted": 2}
#: set-staff-mixer's integer settings with their ranges.
MIXER_RANGES = {"volume": (0, 127), "pan": (-100, 100), "distance": (0, 100)}
MIXER_SETTINGS = ("sound", "mute", "solo", "volume", "pan", "distance")
#: A playback sound ID (Staff.SetSoundId, bridge v69): dot-separated lower-case words.
SOUND_ID_PATTERN = re.compile(r"[a-z0-9_]+(\.[a-z0-9_+-]+)*")


def _validate_staff_mixer(operation: dict[str, Any], label: str) -> dict[str, Any]:
    """Validate a set-staff-mixer op: one staff's Mixer sound, mute, solo, volume, pan and distance."""
    known = {"op", "staff", *MIXER_SETTINGS}
    if unknown := sorted(operation.keys() - known):
        raise BatchError(
            f"{label}: unknown set-staff-mixer fields {unknown}; allowed: {', '.join(sorted(known - {'op'}))}"
        )
    staff = operation.get("staff")
    if staff is None:
        raise BatchError(f"{label}.staff is required")
    if not isinstance(staff, int) or isinstance(staff, bool):
        raise BatchError(f"{label}.staff must be an integer staff number")
    if staff == batch_schema.SYSTEM_STAFF:
        raise BatchError(f"{label}.staff: the system staff has no Mixer strip")
    if staff < 1:
        raise BatchError(f"{label}.staff must be at least 1")
    out: dict[str, Any] = {"op": "set-staff-mixer", "staff": staff}
    settings: list[str] = []
    if "mute" in operation:
        mute = operation["mute"]
        if not isinstance(mute, str) or mute not in MIXER_MUTE_MODES:
            raise BatchError(f"{label}.mute must be one of: {', '.join(MIXER_MUTE_MODES)}")
        out["muteMode"] = MIXER_MUTE_MODES[mute]
        settings.append("muteMode")
    if "solo" in operation:
        if not isinstance(operation["solo"], bool):
            raise BatchError(f"{label}.solo must be true or false")
        out["solo"] = operation["solo"]
        settings.append("solo")
    for key, (low, high) in MIXER_RANGES.items():
        if key not in operation:
            continue
        value = operation[key]
        # A float or bool written to a Staff property raises a modal dialog in Sibelius.
        if not isinstance(value, int) or isinstance(value, bool) or not low <= value <= high:
            raise BatchError(f"{label}.{key} must be an integer from {low} to {high}")
        out[key] = value
        settings.append(key)
    if "sound" in operation:
        sound = operation["sound"]
        if not isinstance(sound, str) or not SOUND_ID_PATTERN.fullmatch(sound):
            raise BatchError(
                f"{label}.sound must be a sound ID such as voice.female.soprano.ah "
                "(lower-case words joined by dots)"
            )
        out["soundId"] = sound
        settings.insert(0, "soundId")
    if not settings:
        raise BatchError(f"{label}: set-staff-mixer needs at least one of {', '.join(MIXER_SETTINGS)}")
    # ManuScript reads a 0 or false as null, so the plug-in writes only the settings named here.
    out["settings"] = settings
    return out


#: Operations only Sibelius runs, merged into every Sibelius batch validation.
SIBELIUS_EXTRA_OPS: ExtraOps = {"set-staff-mixer": _validate_staff_mixer}


def load_batch(path: str) -> list[dict[str, Any]]:
    source = Path(path).expanduser()
    try:
        payload = json.loads(source.read_text())
    except OSError as exc:
        raise BatchError(f"cannot read batch file {source}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise BatchError(f"invalid JSON in batch file {source}: {exc}") from exc
    return validate_batch(payload)


def validate_batch(payload: Any, extra: ExtraOps | None = None) -> list[dict[str, Any]]:
    """Validate a batch for Sibelius: the shared schema plus the writable table."""
    batch = batch_schema.validate_batch(payload, {**SIBELIUS_EXTRA_OPS, **(extra or {})}, WRITABLE)
    mixer_staves: set[int] = set()
    for i, operation in enumerate(batch):
        if operation["op"] == "set-staff-mixer":
            if operation["staff"] in mixer_staves:
                raise BatchError(
                    f"op {i}: a second set-staff-mixer for staff {operation['staff']}; merge them into one"
                )
            mixer_staves.add(operation["staff"])
    for operation in batch:
        if operation["op"] == "ficta" and not operation["remove"]:
            operation["symbol"] = FICTA_SYMBOLS[operation["accidental"]]
    return batch


def layout_last(batch: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], str | None]:
    """Move set-layout operations to the end of a validated batch.

    Sibelius ignored a set-layout that later breaks or hide-empty-staves
    re-laid out (Nelson Carol Book run), so it must run last. set-layout names
    no bars, so moving it past other structural operations is safe. Returns
    the batch and a warning when anything moved.
    """
    layouts = [op for op in batch if op["op"] == "set-layout"]
    others = [op for op in batch if op["op"] != "set-layout"]
    reordered = others + layouts
    if reordered == batch:
        return batch, None
    moved = [i for i, op in enumerate(batch) if op["op"] == "set-layout"]
    return reordered, (
        f"set-layout (op {', '.join(map(str, moved))}) was not last in the batch; moved to the end "
        "because Sibelius ignores a set-layout that later breaks or hidden staves re-lay out. "
        "Result indices follow the new order"
    )


def mixer_warnings(batch: list[dict[str, Any]]) -> list[str]:
    """Notes about a validated batch's set-staff-mixer ops (from the live probes, bridge v68).

    Mixer writes are undoable (one undo reverts the batch), so there is no undo
    note. A whole-score audio export honours Mute and Solo, but a single-staff
    export (export-stem, rehearsal-mixes) ignores them.
    """
    if any(
        op["op"] == "set-staff-mixer" and {"muteMode", "solo"} & set(op["settings"]) for op in batch
    ):
        return [
            "Mixer mute and solo change Sibelius playback and a whole-score audio export, but not "
            "single-staff stems (export-stem, rehearsal-mixes); volume changes both"
        ]
    return []


def sound_warnings(batch: list[dict[str, Any]], results: list[dict[str, Any]]) -> list[str]:
    """Notes about set-staff-mixer sound writes, from the plug-in's after values (bridge v69).

    Sibelius picks the playback device per sound ID. Cantai's solo voices
    (voice.female.soprano.ah and the like) are also in Sibelius 7 Sounds, which
    wins unless the playback configuration's Preferred Sounds name Cantai for
    that ID, so a voice.* write that lands outside Cantai is reported. With the
    preference, Sibelius may still report Cantai's first patch (Soprano) for
    such staves; the audio follows the ID (probed 2026-11-22).
    """
    notes: list[str] = []
    for operation, result in zip(batch, results):
        if operation.get("op") != "set-staff-mixer" or "soundId" not in operation.get("settings", ()):
            continue
        after = ((result or {}).get("after") or {}).get("after") or {}
        sound_set = str(after.get("soundSet", ""))
        if operation["soundId"].startswith("voice.") and sound_set and "Cantai" not in sound_set:
            notes.append(
                f"staff {operation['staff']}: {operation['soundId']} plays on {sound_set}, not Cantai; "
                "add a Preferred Sounds entry for it (Play > Playback Devices > Preferred Sounds, "
                "device Cantai) or pick the device in the Mixer"
            )
    return notes
