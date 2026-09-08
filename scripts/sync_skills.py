#!/usr/bin/env python3
"""Sync skill definitions across coding agent harnesses (Claude Code, Antigravity, Cursor).

- Claude Code:  .claude/skills/<name>/SKILL.md
- Antigravity:  .agents/skills/<name>/SKILL.md (symlink)
- Cursor:       .cursor/rules/<name>.mdc
- Cross-agent:  AGENTS.md -> CLAUDE.md
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

DEFAULT_ROOT_DIR = Path(__file__).resolve().parent.parent

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


def check_sync(root_dir: Path | None = None) -> tuple[bool, list[str]]:
    """Check whether skill files and links are synchronized across harnesses.

    Returns (is_in_sync, issues).
    """
    root = (root_dir or DEFAULT_ROOT_DIR).resolve()
    claude_skills = root / ".claude" / "skills"
    agents_skills = root / ".agents" / "skills"
    cursor_rules = root / ".cursor" / "rules"
    claude_md = root / "CLAUDE.md"
    agents_md = root / "AGENTS.md"

    issues: list[str] = []

    # 1. Check AGENTS.md symlink
    if claude_md.exists():
        if not agents_md.exists() and not agents_md.is_symlink():
            issues.append("AGENTS.md missing (should be a symlink to CLAUDE.md)")
        elif not agents_md.is_symlink():
            issues.append("AGENTS.md exists but is not a symlink to CLAUDE.md")
        else:
            target = os.readlink(agents_md)
            if target not in {"CLAUDE.md", str(claude_md)}:
                issues.append(f"AGENTS.md points to {target!r}, expected 'CLAUDE.md'")

    if not claude_skills.exists():
        issues.append(f"Missing Claude skills directory: {claude_skills}")
        return False, issues

    skill_names: set[str] = set()

    # 2. Check each skill defined in .claude/skills
    for skill_dir in sorted(claude_skills.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.exists():
            continue

        skill_name = skill_dir.name
        skill_names.add(skill_name)

        # Check Antigravity link
        ag_link = agents_skills / skill_name
        expected_target = f"../../.claude/skills/{skill_name}"
        if not ag_link.is_symlink():
            issues.append(f"Antigravity skill {ag_link} is missing or not a symlink")
        else:
            target = os.readlink(ag_link)
            if target != expected_target:
                issues.append(
                    f"Antigravity skill {ag_link} points to {target!r}, expected {expected_target!r}"
                )

        # Check Cursor rule
        mdc_file = cursor_rules / f"{skill_name}.mdc"
        if not mdc_file.exists():
            issues.append(f"Cursor rule {mdc_file.relative_to(root)} is missing")
        else:
            content = skill_file.read_text(encoding="utf-8")
            meta, body = parse_frontmatter(content)
            expected_mdc = generate_cursor_mdc(meta, body)
            actual_mdc = mdc_file.read_text(encoding="utf-8")
            if actual_mdc != expected_mdc:
                issues.append(
                    f"Cursor rule {mdc_file.relative_to(root)} does not match {skill_file.relative_to(root)}"
                )

    # 3. Check for orphan cursor rules
    if cursor_rules.exists():
        for mdc in cursor_rules.glob("*.mdc"):
            if mdc.stem not in skill_names:
                issues.append(f"Orphan Cursor rule without Claude skill: {mdc.relative_to(root)}")

    # 4. Check for orphan antigravity skills
    if agents_skills.exists():
        for item in agents_skills.iterdir():
            if item.name not in skill_names:
                issues.append(
                    f"Orphan Antigravity skill without Claude skill: {item.relative_to(root)}"
                )

    return len(issues) == 0, issues


def sync_all(root_dir: Path | None = None) -> None:
    """Synchronize skill files across Claude, Antigravity, and Cursor."""
    root = (root_dir or DEFAULT_ROOT_DIR).resolve()
    claude_skills = root / ".claude" / "skills"
    agents_skills = root / ".agents" / "skills"
    cursor_rules = root / ".cursor" / "rules"
    claude_md = root / "CLAUDE.md"
    agents_md = root / "AGENTS.md"

    if not claude_skills.exists():
        raise FileNotFoundError(f"{claude_skills} does not exist")

    # 1. Sync AGENTS.md
    if claude_md.exists():
        if agents_md.exists() or agents_md.is_symlink():
            agents_md.unlink()
        agents_md.symlink_to("CLAUDE.md")
        print("Linked: AGENTS.md -> CLAUDE.md")

    agents_skills.mkdir(parents=True, exist_ok=True)
    cursor_rules.mkdir(parents=True, exist_ok=True)

    # 2. Sync each skill
    for skill_dir in sorted(claude_skills.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.exists():
            continue

        skill_name = skill_dir.name

        # Antigravity symlink
        ag_link = agents_skills / skill_name
        rel_target = f"../../.claude/skills/{skill_name}"
        if ag_link.exists() or ag_link.is_symlink():
            ag_link.unlink()
        ag_link.symlink_to(rel_target)
        print(f"Linked Antigravity skill: {ag_link.relative_to(root)} -> {rel_target}")

        # Cursor rule
        mdc_file = cursor_rules / f"{skill_name}.mdc"
        content = skill_file.read_text(encoding="utf-8")
        meta, body = parse_frontmatter(content)
        mdc_content = generate_cursor_mdc(meta, body)
        mdc_file.write_text(mdc_content, encoding="utf-8")
        print(f"Updated Cursor rule: {mdc_file.relative_to(root)}")

    print("Sync complete.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sync skills between Claude, Antigravity, and Cursor.")
    parser.add_argument("--check", action="store_true", help="check if harnesses are in sync without modifying files")
    args = parser.parse_args(argv)

    if args.check:
        in_sync, issues = check_sync()
        if in_sync:
            print("All harness skill files and links are in sync.")
            return 0
        else:
            print("Harness skill files are out of sync:", file=sys.stderr)
            for issue in issues:
                print(f"  - {issue}", file=sys.stderr)
            print("Run 'python scripts/sync_skills.py' to synchronize.", file=sys.stderr)
            return 1

    sync_all()
    return 0


if __name__ == "__main__":
    sys.exit(main())
