"""Where this project keeps its config and cache, and the name it gives editors.

Files live under ``$XDG_CONFIG_HOME/ai-score-editing`` and
``$XDG_CACHE_HOME/ai-score-editing`` (``~/.config`` and ``~/.cache`` by
default).
"""

from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "ai-score-editing"

#: The client name sent to Sibelius Connect and Dorico, which show it in their
#: approval prompts. Editor-neutral because the same name serves every editor.
WIRE_CLIENT_NAME = "ai-score-editing"

def _base(variable: str, fallback: str) -> Path:
    return Path(os.environ.get(variable) or Path.home() / fallback)


def config_dir() -> Path:
    """The config folder (not created)."""
    return _base("XDG_CONFIG_HOME", ".config") / APP_NAME


def cache_dir(*parts: str) -> Path:
    """The cache folder, or a path below it (not created)."""
    return _base("XDG_CACHE_HOME", ".cache").joinpath(APP_NAME, *parts)
