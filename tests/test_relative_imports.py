"""Every relative import resolves, including lazy ones inside functions.

The Sibelius ``query`` command imported ``.query`` after that module moved to
the top-level package; nothing failed until the command ran.
"""

import ast
import importlib.util
from pathlib import Path

import pytest

import ai_score_editing

PACKAGE_DIR = Path(ai_score_editing.__file__).parent
SOURCES = sorted(PACKAGE_DIR.rglob("*.py"))


def _package_of(path: Path) -> str:
    parts = path.relative_to(PACKAGE_DIR.parent).with_suffix("").parts
    return ".".join(parts[:-1])


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: str(p.relative_to(PACKAGE_DIR)))
def test_relative_imports_resolve(path):
    package = _package_of(path)
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or node.level == 0:
            continue
        name = "." * node.level + (node.module or "")
        if node.module is None:
            continue
        assert importlib.util.find_spec(name, package) is not None, (
            f"{path.name}:{node.lineno} imports missing module {name!r}"
        )
