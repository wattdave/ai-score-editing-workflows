"""Sibelius operations shared by the CLI and the MCP server.

Every function takes a connected ``SibeliusBridge`` and raises ``BridgeError``
(``BridgeBusy`` when a dialog is open in Sibelius), ``QueryError`` or
``BatchError``. Nothing here prints results, exits or raises a tool error: the
CLI and the MCP server each translate these exceptions for their own audience.
"""

from __future__ import annotations

import shutil
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from ai_score_editing import backups, batch_ops
from ai_score_editing.batch_ops import BatchError
from ai_score_editing.query import (
    CONTAINER_KINDS,
    FONT_FIELDS,
    QueryError,
    build_selector,
    resolve_staves,
)
from ai_score_editing.sibelius.bridge import (
    EXPORT_FORMATS,
    QUERY_BRIDGE_VERSION,
    QUERY_CONTAINERS_BRIDGE_VERSION,
    STRUCTURE_READ_BRIDGE_VERSION,
    SYSTEM_STAFF_BRIDGE_VERSION,
    TEXT_FONTS_BRIDGE_VERSION,
    BridgeBusy,
    BridgeError,
    SibeliusBridge,
    batch_bridge_version,
    export_path,
    raise_if_busy,
)

__all__ = [
    "BatchError", "BatchFailed", "BridgeBusy", "BridgeError", "QueryError", "apply", "backup",
    "backup_folder", "check", "commit", "export", "overview", "query", "query_selector", "save",
    "structure", "undo",
]

BACKUP_DIR_ENV = "SIBELIUS_BACKUP_DIR"

BackupFn = Callable[[SibeliusBridge, str], Awaitable[dict[str, Any]]]


class BatchFailed(BatchError):
    """Sibelius refused or only partly applied a batch.

    ``result`` is the bridge's ApplyBatch result (with its ``error``),
    ``applied`` how many operations were applied (as one undo step) and
    ``backup`` the backup copy made before the write, if any.
    """

    def __init__(self, message: str, result: dict[str, Any], backup: str | None = None) -> None:
        super().__init__(message)
        self.result = result
        self.applied = int(result.get("applied", 0) or 0)
        self.backup = backup


def backup_folder(arg: str | Path | None = None) -> Path | None:
    """Where backups go (backups.folder): argument, env, else None (beside the score)."""
    return backups.folder("sibelius", arg)


async def overview(b: SibeliusBridge) -> dict[str, Any]:
    return {
        "bridge": await b.call("GetBridgeVersion"),
        "score": await b.call("GetScoreInfo"),
        "staves": await b.call("GetStaves"),
        "selection": await b.call("GetSelectionInfo"),
    }


async def structure(b: SibeliusBridge, from_bar: int | None = None, to_bar: int | None = None) -> dict[str, Any]:
    await b.require(STRUCTURE_READ_BRIDGE_VERSION, "score_structure")
    last = to_bar
    if last is None:
        last = (await b.call("GetScoreInfo"))["barCount"]
    return batch_ops.name_structure(await b.call("GetScoreStructure", [from_bar or 1, last]))


def query_selector(
    *,
    from_bar: int | None = None,
    to_bar: int | None = None,
    types: list[str] | None = None,
    voice: int | None = None,
    where: list[str] | None = None,
    fields: list[str] | None = None,
    limit: int = 200,
) -> dict[str, Any]:
    """Validate a query without connecting (staff names are resolved later); raises QueryError."""
    return build_selector(
        staves=[], from_bar=from_bar, to_bar=to_bar, types=types or [], voice=voice,
        where=where or [], fields=fields or [], limit=limit,
    )


async def query(
    b: SibeliusBridge,
    *,
    staves: list[str] | None = None,
    from_bar: int | None = None,
    to_bar: int | None = None,
    types: list[str] | None = None,
    voice: int | None = None,
    where: list[str] | None = None,
    fields: list[str] | None = None,
    limit: int = 200,
) -> dict[str, Any]:
    """Find bar objects; staves are numbers or instrument names. Gates on the bridge version."""
    selector = query_selector(
        from_bar=from_bar, to_bar=to_bar, types=types, voice=voice, where=where, fields=fields, limit=limit
    )
    await b.require(QUERY_BRIDGE_VERSION, "query")
    if staves:
        selector["staves"] = resolve_staves([str(s) for s in staves], await b.call("GetStaves"))
        if 0 in selector["staves"]:
            await b.require(SYSTEM_STAFF_BRIDGE_VERSION, "query of the system staff")
    if CONTAINER_KINDS & set(selector["types"]):
        await b.require(QUERY_CONTAINERS_BRIDGE_VERSION, "query of Bar or Staff")
    if FONT_FIELDS & set(selector["fields"]):
        await b.require(TEXT_FONTS_BRIDGE_VERSION, "query of text fonts")
    return await b.call("Query", [selector])


async def check(b: SibeliusBridge, batch: list[dict[str, Any]]) -> dict[str, Any]:
    """Dry-run a validated batch; raise BatchFailed (nothing was changed) if Sibelius refuses it."""
    result = await b.apply_batch(batch, True)
    if "error" in result:
        raise BatchFailed(f"{result['error']}; nothing was changed", result)
    return result


async def commit(
    b: SibeliusBridge,
    batch: list[dict[str, Any]],
    *,
    backup_name: str,
    backup_dir: str | Path | None = None,
    backup_fn: BackupFn | None = None,
) -> dict[str, Any]:
    """Back up the score, then apply an already checked batch for real.

    The result carries the backup copy's path under "backup". If Sibelius
    stops partway, BatchFailed says how many operations were applied as one
    undo step.
    """
    if backup_fn is not None:
        made = await backup_fn(b, backup_name)
    else:
        made = await backup(b, backup_name, backup_folder(backup_dir))
    copy = made.get("copy")
    result = await b.apply_batch(batch, False)
    result["backup"] = copy
    if "error" in result:
        raise BatchFailed(
            f"{result['error']}; {result.get('applied', 0)} operation(s) were applied as one undo "
            "step. Call undo once to revert them.",
            result,
            copy,
        )
    return result


async def apply(
    b: SibeliusBridge,
    ops: list[dict[str, Any]],
    *,
    dry_run: bool = False,
    backup_dir: str | Path | None = None,
    backup_name: str = "before apply_batch",
    feature: str = "apply_batch",
    backup_fn: BackupFn | None = None,
) -> dict[str, Any]:
    """Validate, check and (unless dry_run) back up and apply a batch as one undo step.

    The batch is checked against the score first, so a refused batch neither
    saves nor backs up. A real run saves the user's score to its file before
    copying it as the backup. Raises BatchError for an invalid batch and
    BatchFailed for a refused or partly applied one.
    """
    batch = batch_ops.validate_batch(ops)
    await b.require(batch_bridge_version(batch), feature)
    result = await check(b, batch)
    if dry_run:
        return result
    return await commit(b, batch, backup_name=backup_name, backup_dir=backup_dir, backup_fn=backup_fn)


async def undo(b: SibeliusBridge, steps: int = 1) -> dict[str, Any]:
    if not 1 <= steps <= 20:
        raise BatchError("steps must be 1-20")
    raise_if_busy(await b.client.invoke_commands(["undo"] * steps))
    return {"undone": steps}


async def save(b: SibeliusBridge) -> dict[str, Any]:
    return await b.call("Save")


async def export(b: SibeliusBridge, format: str, path: str | None = None) -> dict[str, Any]:
    """Export the open score; returns the bridge result plus "files" and "size"."""
    if format not in EXPORT_FORMATS:
        raise BatchError(f"format must be one of: {', '.join(EXPORT_FORMATS)}")
    saveas_type, extension = EXPORT_FORMATS[format]
    info = await b.call("GetScoreInfo")
    if not info.get("fileName") and not path:
        raise BridgeError("the score has never been saved; pass path")
    out = export_path(path, info["fileName"], extension)
    result = await b.call("ExportScore", [str(out), saveas_type])
    # Sibelius appends page suffixes for image formats (foo_0001.png).
    produced = [out] if out.exists() else sorted(out.parent.glob(f"{out.stem}_*{out.suffix}"))
    if not produced:
        raise BridgeError(f"Sibelius reported the export but {out} does not exist")
    result = dict(result) if isinstance(result, dict) else {}
    result["files"] = [str(f) for f in produced]
    result["size"] = sum(f.stat().st_size for f in produced)
    return result


async def backup(b: SibeliusBridge, name: str, folder: Path | None) -> dict[str, Any]:
    """In-file version + save + timestamped filesystem copy. Returns details.

    This saves the user's score to its file first, so the copy holds the
    current state. folder is where the copy goes (None: beside the score).
    """
    try:
        version = await b.call("AddVersion", [name, "automatic backup before write"])
    except BridgeError as exc:
        # In-file versioning is best-effort; the filesystem copy below is the
        # real backup. Sibelius sometimes refuses AddVersion (returns null).
        version = {"skipped": str(exc)}
        print(f"warning: in-file version skipped: {exc}", file=sys.stderr)
    saved = await b.call("Save")
    source = Path(saved["fileName"])
    if not source.is_absolute():
        # Bridges before v36 accept an imported score's bare title as a path.
        raise BridgeError(
            f"score {saved['fileName']!r} has never been saved as a .sib; save it in Sibelius first"
        )
    target = folder or source.parent
    target.mkdir(parents=True, exist_ok=True)
    copy = target / backups.name(source.stem, source.suffix)
    shutil.copy2(source, copy)
    return {"version": version, "savedTo": str(source), "copy": str(copy)}
