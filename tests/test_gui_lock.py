"""gui_lock.sh: acquire blocks until the lock is ours; release only by the owner."""

from __future__ import annotations

import subprocess

from helpers import ROOT

SCRIPT = ROOT / ".claude/skills/sibelius-shared-gui/scripts/gui_lock.sh"


def run(lock, *args):
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        capture_output=True,
        text=True,
        env={"GUI_LOCK_DIR": str(lock), "PATH": "/usr/bin:/bin"},
    )


def test_acquire_release_cycle(tmp_path):
    lock = tmp_path / "gui"
    assert run(lock, "status").returncode == 1
    got = run(lock, "acquire", "a", "task")
    assert got.returncode == 0 and got.stdout.strip() == "GOT"
    assert "a task" in run(lock, "status").stdout
    assert run(lock, "release", "b").returncode == 1
    assert lock.is_dir()
    assert run(lock, "release", "a").returncode == 0
    assert not lock.exists()


def test_second_acquire_times_out_and_does_not_report_got(tmp_path):
    lock = tmp_path / "gui"
    assert run(lock, "acquire", "a", "t").returncode == 0
    second = run(lock, "acquire", "b", "t", "1")
    assert second.returncode == 1
    assert "GOT" not in second.stdout
    assert "TIMEOUT" in second.stderr
