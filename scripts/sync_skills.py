#!/usr/bin/env python3
"""Sync skill definitions across coding agent harnesses (Claude Code, Antigravity, Cursor).

- Claude Code:  .claude/skills/<name>/SKILL.md
- Antigravity:  .agents/skills/<name>/SKILL.md (or symlink)
- Cursor:       .cursor/rules/<name>.mdc
- Cross-agent:  AGENTS.md -> CLAUDE.md
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
CLAUDE_SKILLS_DIR = ROOT_DIR / ".claude" / "skills"
AGENTS_SKILLS_DIR = ROOT_DIR / ".agents" / "skills"
CURSOR_RULES_DIR = ROOT_DIR / ".cursor" / "rules"
CLAUDE_MD = ROOT_DIR / "CLAUDE.md"
AGENTS_MD = ROOT_DIR / "AGENTS.md"

FRONTMATTER_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    match = FRONTMATTER_PATTERN.match(text)
    if not match:
        return {}, text
    fm_raw, body = match.group(1), match.group(2)
    metadata: dict[str, str] = {}
    current_key: str | None = None
    current_val: list[str] = []

    for line in fm_raw.splitlines():
        if ":" in line and not line.startswith(" ") and not line.startswith("\t"):
            if current_key is not None:
                metadata[current_key] = "\n".join(current_val).strip()
            k, v = line.split(":", 1)
            current_key = k.strip()
            v_strip = v.strip()
            current_val = [v_strip] if v_strip and v_strip not in {">", ">-", "|"} else []
        elif current_key is not None:
            current_val.append(line.strip())

    if current_key is not None:
        metadata[current_key] = " ".join(current_val).strip()

    return metadata, body


def generate_cursor_mdc(metadata: dict[str, str], body: str) -> str:
    description = metadata.get("description", "").replace("\n", " ").strip()
    return f"""---
description: {description}
globs: *
alwaysApply: false
---

{body.strip()}
"""


def sync_agents_md(check_only: bool) -> bool:
    """Ensure AGENTS.md symlink exists pointing to CLAUDE.md."""
    if not CLAUDE_MD.exists():
        return True
    if AGENTS_MD.is_symlink():
        target = os.readlink(AGENTS_MD)
        if target in {"CLAUDE.md", str(CLAUDE_MD)}:
            return True

    if check_only:
        print("Out of sync: AGENTS.md -> CLAUDE.md missing or not a symlink")
        return False

    if AGENTS_MD.exists() or AGENTS_MD.is_symlink():
        AGENTS_MD.unlink()
    AGENTS_MD.symlink_to("CLAUDE.md")
    print("Linked: AGENTS.md -> CLAUDE.md")
    return True


def sync_antigravity_skills(skill_name: str, check_only: bool) -> bool:
    """Ensure .agents/skills/<name> is symlinked to .claude/skills/<name>."""
    AGENTS_SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    target_link = AGENTS_SKILLS_DIR / skill_name
    expected_rel_target = f"../../.claude/skills/{skill_name}"

    if target_link.is_symlink():
        target = os.readlink(target_link)
        if target == expected_rel_target:
            return True

    if check_only:
        print(f"Out of sync: {target_link} does not point to {expected_rel_target}")
        return False

    if target_link.exists() or target_link.is_symlink():
        target_link.unlink()
    target_link.symlink_to(expected_rel_target)
    print(f"Linked Antigravity skill: {target_link.relative_to(ROOT_DIR)} -> {expected_rel_target}")
    return True


def sync_cursor_rule(skill_name: str, skill_file: Path, check_only: bool) -> bool:
    """Ensure .cursor/rules/<name>.mdc matches SKILL.md content."""
    CURSOR_RULES_DIR.mkdir(parents=True, exist_ok=True)
    target_file = CURSOR_RULES_DIR / f"{skill_name}.mdc"

    content = skill_file.read_text(encoding="utf-8")
    metadata, body = parse_frontmatter(content)
    mdc_content = generate_cursor_mdc(metadata, body)

    if target_file.exists():
        existing = target_file.read_text(encoding="utf-8")
        if existing == mdc_content:
            return True

    if check_only:
        print(f"Out of sync: {target_file.relative_to(ROOT_DIR)} differs from {skill_file.relative_to(ROOT_DIR)}")
        return False

    target_file.write_text(mdc_content, encoding="utf-8")
    print(f"Updated Cursor rule: {target_file.relative_to(ROOT_DIR)}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync skills between Claude, Antigravity, and Cursor.")
    parser.add_argument("--check", action="store_true", help="check if harnesses are in sync without modifying files")
    args = parser.parse_args()

    if not CLAUDE_SKILLS_DIR.exists():
        print(f"Error: {CLAUDE_SKILLS_DIR} not found", file=sys.stderr)
        return 1

    all_in_sync = True

    # 1. Sync AGENTS.md
    if not sync_agents_md(args.check):
        all_in_sync = False

    # 2. Sync each skill in .claude/skills
    for skill_dir in sorted(CLAUDE_SKILLS_DIR.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.exists():
            continue

        skill_name = skill_dir.name

        # Antigravity sync
        if not sync_antigravity_skills(skill_name, args.check):
            all_in_sync = False

        # Cursor sync
        if not sync_cursor_rule(skill_name, skill_file, args.check):
            all_in_sync = False

    if args.check:
        if all_in_sync:
            print("All harness skill files and links are in sync.")
            return 0
        else:
            print("Some harness skill files or links are out of sync. Run without --check to fix.", file=sys.stderr)
            return 1

    print("Sync complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
