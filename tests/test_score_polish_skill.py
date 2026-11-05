"""The score-polish-for-sharing orchestrator must only name skills and scripts that exist."""

from __future__ import annotations

import re

from helpers import ROOT

SKILL = ROOT / ".claude/skills/score-polish-for-sharing/SKILL.md"
SKILLS = ROOT / ".claude/skills"


def test_frontmatter_names_the_skill() -> None:
    text = SKILL.read_text()
    assert text.startswith("---\nname: score-polish-for-sharing\n")


def test_required_skills_exist() -> None:
    table = SKILL.read_text().split("## Requires", 1)[1].split("## Before you start", 1)[0]
    names = set(re.findall(r"`([a-z][a-z-]+)`", table))
    assert {"score-engraving-audit", "score-metadata-repair", "chord-symbol-repair", "beaming-repair", "phrase-breaks"} <= names
    missing = sorted(n for n in names if not (SKILLS / n).is_dir())
    assert not missing, f"skills named but not present: {missing}"


def test_referenced_scripts_exist() -> None:
    for rel in set(re.findall(r"\$\{CLAUDE_SKILL_DIR\}/\.\./([\w-]+/scripts/[\w.]+)", SKILL.read_text())):
        assert (SKILLS / rel).is_file(), rel


def test_router_lists_the_skill() -> None:
    assert "score-polish-for-sharing" in (SKILLS / "score-editing/SKILL.md").read_text()
