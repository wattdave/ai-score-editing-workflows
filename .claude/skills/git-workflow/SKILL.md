---
name: git-workflow
description: >
  Guidelines and procedures for git operations in this repository, including
  squash-merge conflict recovery, branch synchronization, safe push policies,
  and pre-push verification.
---

# Git Workflow & Safety

This skill documents repository Git workflows, conflict resolution strategies (especially squash-merge divergence), pre-push validation, and safety policies.

---

## Core Safety Principles

- **Never force-push to `main`**: All shared history on `main` is protected.
- **Always use `--force-with-lease`**: When updating rebased feature branches on the remote, use `git push --force-with-lease <remote> <branch>` rather than unconstrained `--force`.
- **Create backup branches before complex rebases**: Run `git branch backup-<branch-name>` before performing history rewrites or rebases.
- **Never destroy uncommitted work**: Avoid `git reset --hard` or `git clean -fd` unless untracked/scratch files have been inspected or backed up.

---

## Squash-Merge Recovery

When a feature branch (e.g. `feat/foo`) is squash-merged into `main` via GitHub PR, GitHub creates a single new commit with a new SHA on `main`. Any downstream branch that branched off `feat/foo` will appear to conflict with `main` because git's three-way merge base remains the commit *prior* to `feat/foo`.

### Diagnosis
1. Fetch latest upstream:
   ```bash
   git fetch origin
   ```
2. Verify if the squash commit on `main` matches the tree of the original feature branch commit:
   ```bash
   git rev-parse origin/main^{tree} <old-base-commit>^{tree}
   ```
   If the tree hashes match, the diff is 100% identical.

### Resolution
1. Create a local backup tag or branch:
   ```bash
   git branch backup-<branch>
   ```
2. Rebase the downstream commits onto `origin/main` using `--onto`:
   ```bash
   git rebase --onto origin/main <old-base-commit> <feature-branch>
   ```
3. Verify that the rebased tree matches the expected diff:
   ```bash
   git diff backup-<branch>..<feature-branch>
   ```
   (Should be empty if cleanly transplanted).
4. Run test and sync checks (see Pre-Push Checklist below).
5. Push with lease:
   ```bash
   git push --force-with-lease origin <feature-branch>
   ```
6. Clean up temporary backup:
   ```bash
   git branch -D backup-<branch>
   ```

---

## Pre-Push Checklist

Before pushing commits to GitHub, always verify:

1. **Test suite passes**:
   ```bash
   uv run pytest
   ```
2. **Agent skills are synchronized across harnesses**:
   ```bash
   python3 scripts/sync_skills.py --check
   ```
   If out of sync, run `python3 scripts/sync_skills.py` and commit the updated links/rules.
3. **Manuscript plugin lint passes** (if `.plg` files modified):
   ```bash
   uv run sibwscli lint-plugin
   ```
4. **Git status is clean**: Ensure no scratch or temporary test output is accidentally staged.

---

## Harness Skill Management

- The canonical source of truth for skills is `.claude/skills/`.
- Never edit `.cursor/rules/*.mdc` directly; generate them via `python3 scripts/sync_skills.py`.
- Ensure symlinks into `.agents/skills/` point to `../../.claude/skills/<name>`.
