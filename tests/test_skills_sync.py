"""Tests verifying that skill definitions across harnesses (Claude, Antigravity, Cursor) remain in sync."""

from __future__ import annotations

import sys
from pathlib import Path

# Add scripts directory to sys.path to import sync_skills
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "scripts"))

from sync_skills import check_sync, sync_all  # noqa: E402


def test_repo_skills_are_in_sync() -> None:
    """Verify that all skills in this repository are currently synchronized.

    If someone edits a skill in .claude/skills/ or .cursor/rules/ without running
    scripts/sync_skills.py, this test will fail.
    """
    in_sync, issues = check_sync(ROOT_DIR)
    assert in_sync, (
        "Repository agent skills are out of sync across harnesses!\n"
        "Run 'python scripts/sync_skills.py' to synchronize.\n"
        "Issues detected:\n" + "\n".join(f"  - {i}" for i in issues)
    )


def test_check_detects_cursor_drift(tmp_path: Path) -> None:
    """Verify that check_sync fails if a skill body or frontmatter changes without syncing."""
    claude_skills = tmp_path / ".claude" / "skills" / "my-skill"
    claude_skills.mkdir(parents=True)
    skill_file = claude_skills / "SKILL.md"
    skill_file.write_text(
        "---\nname: my-skill\ndescription: Original description\n---\n\n# Original instructions\n",
        encoding="utf-8",
    )
    (tmp_path / "CLAUDE.md").write_text("# Project instructions\n", encoding="utf-8")

    # Initial sync
    sync_all(tmp_path)
    in_sync, issues = check_sync(tmp_path)
    assert in_sync is True
    assert issues == []

    # Modify the Claude skill without updating Cursor rule
    skill_file.write_text(
        "---\nname: my-skill\ndescription: Updated description\n---\n\n# Updated instructions\n",
        encoding="utf-8",
    )
    in_sync, issues = check_sync(tmp_path)
    assert in_sync is False
    assert any("does not match" in i for i in issues)

    # Re-sync fixes the drift
    sync_all(tmp_path)
    in_sync, issues = check_sync(tmp_path)
    assert in_sync is True
    assert issues == []


def test_check_detects_missing_cursor_rule(tmp_path: Path) -> None:
    """Verify that check_sync fails if a new Claude skill lacks a Cursor rule."""
    claude_skills = tmp_path / ".claude" / "skills" / "new-skill"
    claude_skills.mkdir(parents=True)
    (claude_skills / "SKILL.md").write_text(
        "---\nname: new-skill\ndescription: New skill\n---\n\n# New\n",
        encoding="utf-8",
    )
    (tmp_path / "CLAUDE.md").write_text("# Instructions\n", encoding="utf-8")

    in_sync, issues = check_sync(tmp_path)
    assert in_sync is False
    assert any("missing" in i for i in issues)


def test_check_detects_antigravity_link_drift(tmp_path: Path) -> None:
    """Verify that check_sync fails if Antigravity symlink is missing or pointing incorrectly."""
    claude_skills = tmp_path / ".claude" / "skills" / "linked-skill"
    claude_skills.mkdir(parents=True)
    (claude_skills / "SKILL.md").write_text(
        "---\nname: linked-skill\ndescription: Linked\n---\n\n# Linked\n",
        encoding="utf-8",
    )
    (tmp_path / "CLAUDE.md").write_text("# Instructions\n", encoding="utf-8")

    sync_all(tmp_path)
    assert check_sync(tmp_path)[0] is True

    # Break Antigravity symlink
    ag_link = tmp_path / ".agents" / "skills" / "linked-skill"
    ag_link.unlink()
    ag_link.symlink_to("../../wrong/path")

    in_sync, issues = check_sync(tmp_path)
    assert in_sync is False
    assert any("expected" in i for i in issues)


def test_check_detects_agents_md_drift(tmp_path: Path) -> None:
    """Verify that check_sync fails if AGENTS.md does not point to CLAUDE.md."""
    claude_skills = tmp_path / ".claude" / "skills" / "demo"
    claude_skills.mkdir(parents=True)
    (claude_skills / "SKILL.md").write_text(
        "---\nname: demo\ndescription: Demo\n---\n\n# Demo\n",
        encoding="utf-8",
    )
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text("# Instructions\n", encoding="utf-8")

    sync_all(tmp_path)
    assert check_sync(tmp_path)[0] is True

    # Break AGENTS.md
    agents_md = tmp_path / "AGENTS.md"
    agents_md.unlink()
    agents_md.write_text("plain text, not a symlink", encoding="utf-8")

    in_sync, issues = check_sync(tmp_path)
    assert in_sync is False
    assert any("not a symlink" in i for i in issues)


def test_cursor_rule_rewrites_reference_links_without_eager_includes(
    tmp_path: Path,
) -> None:
    """Cursor rules point to canonical references without using eager @file includes."""
    skill_dir = tmp_path / ".claude" / "skills" / "linked-skill"
    references = skill_dir / "references"
    references.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: linked-skill\ndescription: Linked\n---\n\n"
        "Read [details](references/details.md) when needed.\n",
        encoding="utf-8",
    )
    (references / "details.md").write_text("# Details\n", encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text("# Instructions\n", encoding="utf-8")

    sync_all(tmp_path)

    cursor_rule = (tmp_path / ".cursor" / "rules" / "linked-skill.mdc").read_text(
        encoding="utf-8"
    )
    assert (
        "[details](../../.claude/skills/linked-skill/references/details.md)"
        in cursor_rule
    )
    assert "@.claude" not in cursor_rule
    assert check_sync(tmp_path) == (True, [])


def test_check_detects_missing_skill_reference(tmp_path: Path) -> None:
    """A reference linked by the canonical skill entrypoint must exist."""
    skill_dir = tmp_path / ".claude" / "skills" / "linked-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: linked-skill\ndescription: Linked\n---\n\n"
        "Read [details](references/missing.md) when needed.\n",
        encoding="utf-8",
    )
    (tmp_path / "CLAUDE.md").write_text("# Instructions\n", encoding="utf-8")

    in_sync, issues = check_sync(tmp_path)

    assert in_sync is False
    assert any(
        "references/missing.md" in issue and "is missing" in issue for issue in issues
    )


def test_antigravity_skill_symlink_exposes_references(tmp_path: Path) -> None:
    """The directory symlink exposes canonical supporting files without copies."""
    skill_dir = tmp_path / ".claude" / "skills" / "linked-skill"
    references = skill_dir / "references"
    references.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: linked-skill\ndescription: Linked\n---\n\n"
        "Read [details](references/details.md) when needed.\n",
        encoding="utf-8",
    )
    (references / "details.md").write_text("# Canonical details\n", encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text("# Instructions\n", encoding="utf-8")

    sync_all(tmp_path)

    linked_reference = (
        tmp_path / ".agents" / "skills" / "linked-skill" / "references" / "details.md"
    )
    assert linked_reference.read_text(encoding="utf-8") == "# Canonical details\n"


def test_repo_skill_entrypoint_stays_within_token_budget() -> None:
    """Keep the always-loaded skill router within its planned static budget."""
    skill_text = (ROOT_DIR / ".claude" / "skills" / "sibelius" / "SKILL.md").read_text(
        encoding="utf-8"
    )

    assert len(skill_text.encode("utf-8")) <= 5_120
    assert len(skill_text.split()) <= 700


def _plugin_tree(tmp_path: Path) -> None:
    """A minimal repo with one owned skill, one repo-only skill and two plugins."""
    import json

    for name in ("owned", "local"):
        skill_dir = tmp_path / ".claude" / "skills" / name
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: {name}\n---\n\n# {name}\n",
            encoding="utf-8",
        )
    (tmp_path / "CLAUDE.md").write_text("# Instructions\n", encoding="utf-8")
    (tmp_path / "scripts").mkdir()
    import sync_skills

    for script in sync_skills.USER_SCRIPTS:
        (tmp_path / "scripts" / script).write_text("", encoding="utf-8")
    plugins = tmp_path / "plugins"
    (plugins / "score-editing-core").mkdir(parents=True)
    (plugins / "other").mkdir()
    (plugins / "skills.json").write_text(
        json.dumps({"owned": "other", "local": None}), encoding="utf-8"
    )
    (tmp_path / ".claude-plugin").mkdir()
    (tmp_path / ".claude-plugin" / "marketplace.json").write_text(
        json.dumps(
            {
                "plugins": [
                    {"name": "score-editing-core", "source": "./plugins/score-editing-core"},
                    {"name": "other", "source": "./plugins/other"},
                ]
            }
        ),
        encoding="utf-8",
    )


def test_sync_creates_plugin_skill_and_script_links(tmp_path: Path) -> None:
    import os

    _plugin_tree(tmp_path)
    sync_all(tmp_path)

    link = tmp_path / "plugins" / "other" / "skills" / "owned"
    assert os.readlink(link) == "../../../.claude/skills/owned"
    assert not (tmp_path / "plugins" / "other" / "skills" / "local").exists()
    scripts = tmp_path / "plugins" / "score-editing-core" / "scripts"
    assert scripts.is_dir() and not scripts.is_symlink()
    assert (scripts / "attach_lyrics.py").is_symlink()
    assert check_sync(tmp_path) == (True, [])


def test_check_reports_manifest_and_plugin_link_drift(tmp_path: Path) -> None:
    import json

    _plugin_tree(tmp_path)
    sync_all(tmp_path)

    manifest = tmp_path / "plugins" / "skills.json"
    manifest.write_text(json.dumps({"owned": "other"}), encoding="utf-8")
    assert any(
        "local is missing from plugins/skills.json" in i for i in check_sync(tmp_path)[1]
    )
    manifest.write_text(json.dumps({"owned": "other", "local": None}), encoding="utf-8")

    skills = tmp_path / "plugins" / "other" / "skills"
    link = skills / "owned"
    link.unlink()
    link.symlink_to("../../../wrong")
    (skills / "stray").symlink_to("../../../.claude/skills/local")
    issues = check_sync(tmp_path)[1]
    assert any("points to" in i and "owned" in i for i in issues)
    assert any("Extra plugin skill link" in i and "stray" in i for i in issues)
    link.unlink()
    assert any("owned" in i and "is missing" in i for i in check_sync(tmp_path)[1])

    sync_all(tmp_path)
    assert check_sync(tmp_path) == (True, [])


def test_check_reports_marketplace_and_script_drift(tmp_path: Path) -> None:
    import json

    _plugin_tree(tmp_path)
    sync_all(tmp_path)

    (tmp_path / "plugins" / "third").mkdir()
    assert any("plugins/third is not listed" in i for i in check_sync(tmp_path)[1])
    (tmp_path / "plugins" / "third").rmdir()

    market = tmp_path / ".claude-plugin" / "marketplace.json"
    market.write_text(
        json.dumps({"plugins": [{"source": "./plugins/other"}]}), encoding="utf-8"
    )
    assert any("score-editing-core is not listed" in i for i in check_sync(tmp_path)[1])

    scripts = tmp_path / "plugins" / "score-editing-core" / "scripts"
    (scripts / "dev_probe.py").symlink_to("../../../scripts/attach_lyrics.py")
    assert any("Extra plugin script" in i for i in check_sync(tmp_path)[1])
    (scripts / "attach_lyrics.py").unlink()
    assert any("attach_lyrics.py is missing" in i for i in check_sync(tmp_path)[1])


def test_repo_dev_probes_are_not_exposed_to_plugin() -> None:
    scripts = ROOT_DIR / "plugins" / "score-editing-core" / "scripts"
    assert scripts.is_dir() and not scripts.is_symlink()
    assert not (scripts / "musescore_probe.py").exists()
    assert (ROOT_DIR / "scripts" / "dev" / "musescore_probe.py").is_file()
