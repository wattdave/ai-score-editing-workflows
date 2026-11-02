from __future__ import annotations

import asyncio
import subprocess
from typing import Any

import pytest

from ai_score_editing import macos


class FakeProcess:
    def __init__(self, stdout: bytes = b"", stderr: bytes = b"", returncode: int = 0, hang: bool = False) -> None:
        self.stdout, self.stderr, self.hang, self.result = stdout, stderr, hang, returncode
        self.returncode: int | None = None
        self.input: bytes | None = None
        self.killed = self.waited = False

    async def communicate(self, data: bytes) -> tuple[bytes, bytes]:
        self.input = data
        if self.hang:
            await asyncio.sleep(3600)
        self.returncode = self.result
        return self.stdout, self.stderr

    def kill(self) -> None:
        self.killed = True

    async def wait(self) -> int:
        self.waited = True
        self.returncode = -9
        return -9


def spawn(monkeypatch: pytest.MonkeyPatch, process: FakeProcess) -> list[tuple[Any, ...]]:
    calls: list[tuple[Any, ...]] = []

    async def fake_exec(*args: Any, **kwargs: Any) -> FakeProcess:
        calls.append(args)
        return process

    monkeypatch.setattr(macos.asyncio, "create_subprocess_exec", fake_exec)
    return calls


async def test_osascript_passes_script_on_stdin_and_args(monkeypatch: pytest.MonkeyPatch) -> None:
    process = FakeProcess(stdout=b"a\r\nb\r")
    calls = spawn(monkeypatch, process)
    assert await macos.osascript("return 1", "x y", "z") == "a\nb"
    assert calls == [("osascript", "-", "x y", "z")]
    assert process.input == b"return 1"


async def test_osascript_failure_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    spawn(monkeypatch, FakeProcess(stderr=b"syntax error (-2741)\n", returncode=1))
    with pytest.raises(macos.OsascriptError) as info:
        await macos.osascript("bad")
    assert info.value.message == "syntax error (-2741)" and not info.value.accessibility


async def test_osascript_accessibility_denied(monkeypatch: pytest.MonkeyPatch) -> None:
    spawn(monkeypatch, FakeProcess(stderr=b"osascript is not allowed assistive access", returncode=1))
    with pytest.raises(macos.OsascriptError) as info:
        await macos.osascript("x")
    assert info.value.accessibility


async def test_osascript_timeout_kills_the_process(monkeypatch: pytest.MonkeyPatch) -> None:
    process = FakeProcess(hang=True)
    spawn(monkeypatch, process)
    with pytest.raises(subprocess.TimeoutExpired):
        await macos.osascript("x", timeout=0.01)
    assert process.killed and process.waited


async def test_osascript_cancellation_kills_the_process(monkeypatch: pytest.MonkeyPatch) -> None:
    process = FakeProcess(hang=True)
    spawn(monkeypatch, process)
    task = asyncio.create_task(macos.osascript("x"))
    await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert process.killed and process.waited


def test_osascript_sync(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        seen.update(cmd=cmd, **kwargs)
        return subprocess.CompletedProcess(cmd, 0, stdout="true\n", stderr="")

    monkeypatch.setattr(macos.subprocess, "run", run)
    assert macos.osascript_sync("s", "a") == "true"
    assert seen["cmd"] == ["osascript", "-", "a"] and seen["input"] == "s"


async def test_bring_to_front_passes_the_process_name(monkeypatch: pytest.MonkeyPatch) -> None:
    process = FakeProcess()
    calls = spawn(monkeypatch, process)
    await macos.bring_to_front("Dorico 6")
    assert calls == [("osascript", "-", "Dorico 6")]
    assert process.input is not None and b"frontmost" in process.input


@pytest.mark.parametrize(("out", "expected"), [("true", True), ("false", False)])
def test_is_running(monkeypatch: pytest.MonkeyPatch, out: str, expected: bool) -> None:
    monkeypatch.setattr(macos, "osascript_sync", lambda script, *a, **k: out)
    assert macos.is_running("com.avid.sibelius") is expected


def test_is_running_false_when_osascript_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*a: Any, **k: Any) -> str:
        raise FileNotFoundError

    monkeypatch.setattr(macos, "osascript_sync", fail)
    assert macos.is_running("x") is False
