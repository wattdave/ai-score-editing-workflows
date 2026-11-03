"""Helpers for old import paths that now alias a module or package at a new home.

The alias is the very same module object (``sys.modules`` holds one entry for
both names), so ``monkeypatch.setattr`` on either path, module-level state and
``isinstance`` checks all agree.
"""

from __future__ import annotations

import importlib
import importlib.abc
import importlib.util
import sys
from types import ModuleType


def alias_module(old: str, new: str) -> ModuleType:
    """Make ``import <old>`` return the module ``<new>`` itself."""
    module = importlib.import_module(new)
    sys.modules[old] = module
    return module


class _AliasLoader(importlib.abc.Loader):
    def __init__(self, target: str) -> None:
        self.target = target

    def create_module(self, spec):
        return importlib.import_module(self.target)

    def exec_module(self, module) -> None:  # already executed under its real name
        return None


class _AliasFinder(importlib.abc.MetaPathFinder):
    """Resolve ``<old>.<sub>`` to the already-real module ``<new>.<sub>``."""

    def __init__(self, old: str, new: str) -> None:
        self.old = old
        self.new = new

    def find_spec(self, fullname, path=None, target=None):
        if not fullname.startswith(self.old + "."):
            return None
        real = self.new + fullname[len(self.old):]
        real_spec = importlib.util.find_spec(real)
        if real_spec is None:
            return None
        return importlib.util.spec_from_loader(
            fullname,
            _AliasLoader(real),
            is_package=real_spec.submodule_search_locations is not None,
        )


def alias_package(old: str, new: str) -> ModuleType:
    """Make ``<old>`` and every ``<old>.<sub>...`` resolve to the ``<new>`` objects."""
    package = importlib.import_module(new)
    sys.modules[old] = package
    if not any(isinstance(f, _AliasFinder) and f.old == old for f in sys.meta_path):
        sys.meta_path.insert(0, _AliasFinder(old, new))
    return package
