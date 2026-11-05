"""Sibelius-only batch rules: the properties `set` may write.

The rest of batch validation is editor-neutral and lives in
``ai_score_editing.core.batch_schema``; this module adds the writable-property
table that mirrors BatchWritableTable in ScoreBridge.plg.
"""

from __future__ import annotations

import json
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
    batch = batch_schema.validate_batch(payload, extra, WRITABLE)
    for operation in batch:
        if operation["op"] == "ficta" and not operation["remove"]:
            operation["symbol"] = FICTA_SYMBOLS[operation["accidental"]]
    return batch
