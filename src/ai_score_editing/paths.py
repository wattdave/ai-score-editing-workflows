"""Where this project keeps its config and cache, and the name it gives editors.

Files live under ``$XDG_CONFIG_HOME/ai-score-editing`` and
``$XDG_CACHE_HOME/ai-score-editing`` (``~/.config`` and ``~/.cache`` by
default). The folders were once called ``sibelius-websocket-cli``; the first
use of the new folder moves the old one and leaves a symlink behind, so older
checkouts keep working.
"""

from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "ai-score-editing"
LEGACY_APP_NAME = "sibelius-websocket-cli"

#: The client name sent to Sibelius Connect and Dorico, which show it in their
#: approval prompts. Editor-neutral because the same name serves every editor.
WIRE_CLIENT_NAME = "ai-score-editing"
#: The name sent before WIRE_CLIENT_NAME; stored approvals under it are reused.
LEGACY_WIRE_CLIENT_NAME = LEGACY_APP_NAME


def _migrate(old: Path, new: Path) -> None:
    """Move old to new once and leave old as a symlink to new.

    Does nothing if new exists or old does not. A concurrent process doing the
    same move is not an error. os.replace keeps file modes (tokens are 600).
    """
    if new.exists() or new.is_symlink() or old.is_symlink() or not old.exists():
        return
    try:
        new.parent.mkdir(parents=True, exist_ok=True)
        os.replace(old, new)
    except (FileNotFoundError, FileExistsError):
        # Another process moved it first, or new appeared: already done.
        return
    except OSError:
        # e.g. ENOTEMPTY when a racing process created new in between.
        if new.exists():
            return
        raise
    try:
        old.symlink_to(new, target_is_directory=True)
    except (FileExistsError, FileNotFoundError):
        pass


def _base(variable: str, fallback: str) -> Path:
    return Path(os.environ.get(variable) or Path.home() / fallback)


def config_dir() -> Path:
    """The config folder (not created); the old one is migrated on first use."""
    base = _base("XDG_CONFIG_HOME", ".config")
    new = base / APP_NAME
    _migrate(base / LEGACY_APP_NAME, new)
    return new


def cache_dir(*parts: str) -> Path:
    """The cache folder, or a path below it (not created); migrated on first use."""
    base = _base("XDG_CACHE_HOME", ".cache")
    new = base / APP_NAME
    _migrate(base / LEGACY_APP_NAME, new)
    return new.joinpath(*parts)
