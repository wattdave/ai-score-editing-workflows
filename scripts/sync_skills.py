#!/usr/bin/env python3
"""Sync skill definitions across coding agent harnesses (Claude Code, Antigravity, Cursor).

- Claude Code:  .claude/skills/<name>/SKILL.md
- Antigravity:  .agents/skills/<name>/SKILL.md (symlink)
- Cursor:       .cursor/rules/<name>.mdc
- Cross-agent:  AGENTS.md -> CLAUDE.md
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

DEFAULT_ROOT_DIR = Path(__file__).resolve().parent.parent

FRONTMATTER_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)
REFERENCE_LINK_PATTERN = re.compile(
    r"(?P<prefix>\[[^\]]+\]\()(?P<target>references/[^)\s]+)(?P<suffix>\))"
)


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
            current_val = (
                [v_strip] if v_strip and v_strip not in {">", ">-", "|"} else []
            )
        elif current_key is not None:
            current_val.append(line.strip())

    if current_key is not None:
        metadata[current_key] = " ".join(current_val).strip()

    return metadata, body


def reference_targets(body: str) -> list[str]:
    """Return relative reference targets linked from a skill entrypoint."""
    return [
        match.group("target").split("#", 1)[0]
        for match in REFERENCE_LINK_PATTERN.finditer(body)
    ]


def generate_cursor_mdc(metadata: dict[str, str], body: str, skill_name: str) -> str:
    """Generate a Cursor rule while keeping supporting references on demand."""
    description = metadata.get("description", "").replace("\n", " ").strip()
    cursor_body = REFERENCE_LINK_PATTERN.sub(
        lambda match: (
            f"{match.group('prefix')}../../.claude/skills/{skill_name}/"
            f"{match.group('target')}{match.group('suffix')}"
        ),
        body,
    )
    return f"""---
description: {description}
globs: *
alwaysApply: false
---

{cursor_body.strip()}
"""


#: User-facing scripts exposed through plugins/score-editing-core/scripts/.
#: Developer probes live in scripts/dev/ and are not shipped.
CORE_PLUGIN = "score-editing-core"
USER_SCRIPTS = (
    "attach_lyrics.py",
    "musescore_mcp.sh",
    "musicxml_to_abc.py",
    "normalize_omr_musicxml.py",
    "sanitize_omr_musicxml.py",
    "split_16voices.py",
)


def load_manifest(root: Path) -> dict[str, str | None]:
    """Read plugins/skills.json (skill name -> owning plugin directory or null)."""
    manifest = root / "plugins" / "skills.json"
    if not manifest.is_file():
        return {}
    return json.loads(manifest.read_text(encoding="utf-8"))


def check_plugins(root: Path, skill_names: set[str]) -> list[str]:
    """Check skill ownership links, script links and the marketplace listing."""
    issues: list[str] = []
    plugins = root / "plugins"
    manifest_path = plugins / "skills.json"
    if not manifest_path.is_file():
        return issues  # no plugin layout in this tree
    manifest = load_manifest(root)

    for name in sorted(skill_names - manifest.keys()):
        issues.append(f"Skill {name} is missing from plugins/skills.json")
    for name in sorted(manifest.keys() - skill_names):
        issues.append(f"plugins/skills.json lists {name}, which is not in .claude/skills")

    expected: dict[str, set[str]] = {}
    for name, owner in manifest.items():
        if owner is None or name not in skill_names:
            continue
        if not (plugins / owner).is_dir():
            issues.append(f"Skill {name} is owned by unknown plugin {owner!r}")
            continue
        expected.setdefault(owner, set()).add(name)
        link = plugins / owner / "skills" / name
        want = f"../../../.claude/skills/{name}"
        if not link.is_symlink():
            issues.append(f"Plugin skill link {link.relative_to(root)} is missing")
        elif os.readlink(link) != want:
            issues.append(
                f"Plugin skill link {link.relative_to(root)} points to "
                f"{os.readlink(link)!r}, expected {want!r}"
            )

    for plugin in sorted(p for p in plugins.iterdir() if p.is_dir()):
        skills_dir = plugin / "skills"
        if not skills_dir.is_dir():
            continue
        for item in sorted(skills_dir.iterdir()):
            if item.name not in expected.get(plugin.name, set()):
                issues.append(f"Extra plugin skill link {item.relative_to(root)}")

    # Core plugin scripts: a real folder of per-file symlinks.
    scripts_dir = plugins / CORE_PLUGIN / "scripts"
    if scripts_dir.is_dir() or scripts_dir.is_symlink():
        if scripts_dir.is_symlink() or not scripts_dir.is_dir():
            issues.append(f"{scripts_dir.relative_to(root)} must be a real folder of symlinks")
        else:
            for name in USER_SCRIPTS:
                link = scripts_dir / name
                want = f"../../../scripts/{name}"
                if not link.is_symlink():
                    issues.append(f"Plugin script link {link.relative_to(root)} is missing")
                elif os.readlink(link) != want:
                    issues.append(
                        f"Plugin script link {link.relative_to(root)} points to "
                        f"{os.readlink(link)!r}, expected {want!r}"
                    )
            for item in sorted(scripts_dir.iterdir()):
                if item.name not in USER_SCRIPTS:
                    issues.append(f"Extra plugin script {item.relative_to(root)}")
    else:
        issues.append(f"{scripts_dir.relative_to(root)} is missing")

    # Marketplace lists every plugin directory.
    marketplace = root / ".claude-plugin" / "marketplace.json"
    plugin_dirs = {p.name for p in plugins.iterdir() if p.is_dir()}
    if not marketplace.is_file():
        issues.append(".claude-plugin/marketplace.json is missing")
    else:
        listed = {
            Path(entry.get("source", "")).name
            for entry in json.loads(marketplace.read_text(encoding="utf-8")).get(
                "plugins", []
            )
        }
        for name in sorted(plugin_dirs - listed):
            issues.append(f"plugins/{name} is not listed in .claude-plugin/marketplace.json")
        for name in sorted(listed - plugin_dirs):
            issues.append(f"marketplace.json lists {name}, which is not in plugins/")
    return issues


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

        content = skill_file.read_text(encoding="utf-8")
        meta, body = parse_frontmatter(content)

        for target in reference_targets(body):
            reference = skill_dir / target
            if not reference.is_file():
                issues.append(
                    f"Skill reference {reference.relative_to(root)} linked from "
                    f"{skill_file.relative_to(root)} is missing"
                )

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
            expected_mdc = generate_cursor_mdc(meta, body, skill_name)
            actual_mdc = mdc_file.read_text(encoding="utf-8")
            if actual_mdc != expected_mdc:
                issues.append(
                    f"Cursor rule {mdc_file.relative_to(root)} does not match {skill_file.relative_to(root)}"
                )

    # 3. Check for orphan cursor rules
    if cursor_rules.exists():
        for mdc in cursor_rules.glob("*.mdc"):
            if mdc.stem not in skill_names:
                issues.append(
                    f"Orphan Cursor rule without Claude skill: {mdc.relative_to(root)}"
                )

    # 4. Check for orphan antigravity skills
    if agents_skills.exists():
        for item in agents_skills.iterdir():
            if item.name not in skill_names:
                issues.append(
                    f"Orphan Antigravity skill without Claude skill: {item.relative_to(root)}"
                )

    issues.extend(check_plugins(root, skill_names))

    return len(issues) == 0, issues


def link_plugin_assets(root: Path, skill_names: set[str]) -> None:
    """Create plugins/<owner>/skills/<name> and core script symlinks."""
    plugins = root / "plugins"
    if not (plugins / "skills.json").is_file():
        return
    manifest = load_manifest(root)
    for name in sorted(skill_names):
        owner = manifest.get(name)
        if owner is None:
            continue
        skills_dir = plugins / owner / "skills"
        skills_dir.mkdir(parents=True, exist_ok=True)
        link = skills_dir / name
        if link.is_symlink() or link.exists():
            link.unlink()
        link.symlink_to(f"../../../.claude/skills/{name}")
        print(f"Linked plugin skill: {link.relative_to(root)}")
    # Remove links no longer in the manifest.
    for plugin in plugins.iterdir():
        skills_dir = plugin / "skills"
        if not skills_dir.is_dir():
            continue
        for item in skills_dir.iterdir():
            if item.is_symlink() and manifest.get(item.name) != plugin.name:
                item.unlink()
                print(f"Removed stale plugin skill link: {item.relative_to(root)}")

    core = plugins / CORE_PLUGIN
    if core.is_dir():
        scripts_dir = core / "scripts"
        if scripts_dir.is_symlink():
            scripts_dir.unlink()
        scripts_dir.mkdir(exist_ok=True)
        for item in scripts_dir.iterdir():
            if item.name not in USER_SCRIPTS:
                item.unlink()
        for name in USER_SCRIPTS:
            link = scripts_dir / name
            if link.is_symlink() or link.exists():
                link.unlink()
            link.symlink_to(f"../../../scripts/{name}")
        print(f"Linked plugin scripts: {scripts_dir.relative_to(root)}")


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
        mdc_content = generate_cursor_mdc(meta, body, skill_name)
        mdc_file.write_text(mdc_content, encoding="utf-8")
        print(f"Updated Cursor rule: {mdc_file.relative_to(root)}")

    link_plugin_assets(
        root,
        {
            d.name
            for d in claude_skills.iterdir()
            if d.is_dir() and (d / "SKILL.md").exists()
        },
    )

    print("Sync complete.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Sync skills between Claude, Antigravity, and Cursor."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="check if harnesses are in sync without modifying files",
    )
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
            print(
                "Run 'python scripts/sync_skills.py' to synchronize.", file=sys.stderr
            )
            return 1

    sync_all()
    return 0


if __name__ == "__main__":
    sys.exit(main())
