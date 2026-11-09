"""Tests for the Halbestunde driver's window lookup (the GUI itself cannot run in tests)."""

from __future__ import annotations

import sys
import types

import pytest

from helpers import ROOT, load_script

PATH = ROOT / ".claude/skills/omr-halbestunde/scripts/halbestunde_convert.py"
MAIN = ((100, 50), (1020, 720))
TOAST = ((900, 40), (300, 80))


@pytest.fixture
def hb(monkeypatch):
    # Quartz (pyobjc) is not a project dependency; window_origin does not use it.
    monkeypatch.setitem(sys.modules, "Quartz", types.ModuleType("Quartz"))
    module = load_script(PATH, "halbestunde_convert_test")
    yield module
    sys.modules.pop("halbestunde_convert_test", None)


def fake_lookup(*answers):
    calls = {"lookup": 0, "reopen": 0}
    queue = list(answers)

    def lookup():
        calls["lookup"] += 1
        return queue.pop(0) if len(queue) > 1 else queue[0]

    def reopen():
        calls["reopen"] += 1

    return lookup, reopen, calls


def test_parse_windows_handles_no_windows(hb) -> None:
    # osascript prints an empty line when every window is closed (the old ValueError).
    assert hb.parse_windows("") == []
    assert hb.parse_windows("900, 40, 100, 50, 300, 80, 1020, 720") == [TOAST, MAIN]


def test_window_found_first_time_does_not_reopen(hb) -> None:
    lookup, reopen, calls = fake_lookup([TOAST, MAIN])
    assert hb.window_origin(lookup, reopen, sleep=lambda s: None) == (100, 50)
    assert calls == {"lookup": 1, "reopen": 0}


def test_no_window_reopens_until_it_appears(hb) -> None:
    lookup, reopen, calls = fake_lookup([], [], [MAIN])
    assert hb.window_origin(lookup, reopen, sleep=lambda s: None) == (100, 50)
    assert calls == {"lookup": 3, "reopen": 2}


def test_no_window_gives_up_with_clear_error(hb) -> None:
    lookup, reopen, calls = fake_lookup([])
    with pytest.raises(SystemExit, match="no window after 4 tries"):
        hb.window_origin(lookup, reopen, sleep=lambda s: None, attempts=4)
    assert calls == {"lookup": 4, "reopen": 3}


def test_wrong_size_window_names_the_sizes(hb) -> None:
    lookup, reopen, _ = fake_lookup([TOAST])
    with pytest.raises(SystemExit, match=r"found \[\(300, 80\)\]"):
        hb.window_origin(lookup, reopen, sleep=lambda s: None, attempts=2)
