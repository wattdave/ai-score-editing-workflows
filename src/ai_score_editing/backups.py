"""One backup policy for the three back ends.

Every real (non-dry-run) ``apply`` takes a backup first. Where it goes:

1. the explicit argument, else
2. ``$SIBELIUS_BACKUP_DIR`` / ``$DORICO_BACKUP_DIR`` / ``$MUSESCORE_BACKUP_DIR``, else
3. ``$SCORE_BACKUP_DIR``, else
4. the editor's default: beside the score for Sibelius (``None``), the cache
   folder (``~/.cache/ai-score-editing/<editor>/backups``) for Dorico and MuseScore.

Files are named ``{stem}.backup-{YYYYmmdd-HHMMSS}{suffix}``. Old copies are
never deleted unless ``prune`` is called.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from . import paths

EDITORS = ("sibelius", "dorico", "musescore")
COMMON_ENV = "SCORE_BACKUP_DIR"


def env_name(editor: str) -> str:
    return f"{editor.upper()}_BACKUP_DIR"


def folder(editor: str, explicit: str | Path | None = None) -> Path | None:
    """The backup folder for an editor; None means beside the score (Sibelius only)."""
    chosen = explicit or os.environ.get(env_name(editor)) or os.environ.get(COMMON_ENV)
    if chosen:
        return Path(chosen).expanduser()
    if editor == "sibelius":
        return None
    return paths.cache_dir(editor, "backups")


def stamp(now: datetime | None = None) -> str:
    return (now or datetime.now()).strftime("%Y%m%d-%H%M%S")


def name(stem: str, suffix: str, stamp: str | None = None) -> str:
    """``{stem}.backup-{stamp}{suffix}``; the stamp defaults to now."""
    return f"{stem}.backup-{stamp or globals()['stamp']()}{suffix}"


def prune(target: Path, keep: int) -> list[Path]:
    """Delete all but the newest ``keep`` backups in target; returns what was removed."""
    if keep < 0:
        raise ValueError("keep must be 0 or more")
    found = sorted((p for p in target.glob("*.backup-*") if p.exists()), key=lambda p: p.stat().st_mtime, reverse=True)
    removed = found[keep:]
    for path in removed:
        if path.is_file():
            path.unlink()
        else:
            import shutil
            shutil.rmtree(path)
    return removed
