"""Helpers shared by the tests."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parent.parent


def load_script(path: str | Path, name: str | None = None) -> ModuleType:
    """Import a script by file path under a fresh sys.modules entry.

    The module is registered in sys.modules while it runs (dataclasses look it
    up there) and any earlier entry of the same name is replaced.  A failed
    import leaves nothing behind.
    """
    path = Path(path)
    if not path.is_absolute():
        path = ROOT / path
    name = name or path.stem.replace("-", "_")
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader, f"cannot load {path}"
    module = importlib.util.module_from_spec(spec)
    sys.modules.pop(name, None)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return module
