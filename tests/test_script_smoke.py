"""Every skill and repo script must import, and its --help must work.

A broken import path in a script that no other test covers would otherwise
only show up when someone runs the skill.
"""

from __future__ import annotations

import asyncio
import inspect
import sys
from pathlib import Path

import pytest

from helpers import ROOT, load_script

SCRIPTS = sorted(
    [*ROOT.glob(".claude/skills/*/scripts/*.py"), *ROOT.glob("scripts/*.py")]
)


# Third-party modules the skill scripts use that are not project dependencies.
_OPTIONAL = {"Quartz", "pymupdf", "mido", "pyphen", "lxml", "fitz"}


def _id(path: Path) -> str:
    return str(path.relative_to(ROOT))


@pytest.mark.parametrize("path", SCRIPTS, ids=_id)
def test_script_imports_and_help_works(path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    assert SCRIPTS, "no scripts found"
    # Scripts import their siblings (from rebar import ...) as they would when run directly.
    monkeypatch.syspath_prepend(str(path.parent))
    name = f"smoke_{path.parent.parent.name}_{path.stem}".replace("-", "_")
    try:
        module = load_script(path, name)
    except ModuleNotFoundError as exc:
        local = {p.stem for p in path.parent.glob("*.py")}
        if exc.name and exc.name.split(".")[0] not in local | {"ai_score_editing"} and exc.name in _OPTIONAL:
            pytest.skip(f"optional dependency {exc.name} is not installed")
        raise
    try:
        main = getattr(module, "main", None)
        if main is None or "argparse" not in path.read_text():
            return
        params = list(inspect.signature(main).parameters.values())
        if any(p.default is p.empty for p in params):
            return  # main takes plain arguments; there is no --help to call
        monkeypatch.setattr(sys, "argv", ["prog", "--help"])
        with pytest.raises(SystemExit) as exc_info:
            result = main()
            if inspect.isawaitable(result):
                asyncio.run(result)
        assert exc_info.value.code == 0
        assert capsys.readouterr().out.strip()
    finally:
        sys.modules.pop(name, None)


def test_scripts_were_found() -> None:
    assert len(SCRIPTS) >= 20
