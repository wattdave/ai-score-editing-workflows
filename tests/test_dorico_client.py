"""Dorico client: connection, token, osascript, project-info dialog and PDF export."""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any
import pytest

from ai_score_editing.dorico import bridge as bridge_mod
from ai_score_editing.dorico.bridge import DoricoBridge
from ai_score_editing.dorico.client import DoricoClient, DoricoError

from dorico_common import dorico  # noqa: F401,F811


async def test_client_first_connect_stores_the_approved_token(dorico: Any) -> None:
    fake, port, store = dorico
    async with DoricoClient(port=port, client_name="t", store=store) as client:
        status = await client.status()
        assert status["canUndo"] is True and status["hasSelection"] is True  # merged
    assert store.load("127.0.0.1#t", port).token == "tok-1"
    assert [m["message"] for m in fake.received[:2]] == ["connect", "acceptsessiontoken"]


async def test_client_reuses_token_and_refuses_prompt_when_asked(dorico: Any) -> None:
    fake, port, store = dorico
    with pytest.raises(DoricoError, match="no approved Dorico session"):
        await DoricoClient(port=port, client_name="t", store=store, allow_approval=False).connect()
    store.save("127.0.0.1#t", port, "tok-1")
    async with DoricoClient(port=port, client_name="t", store=store, allow_approval=False):
        pass
    assert fake.received[-1]["sessionToken"] == "tok-1"


async def test_bridge_call_round_trips_through_a_response_file(dorico: Any, tmp_path: Path) -> None:
    fake, port, store = dorico
    store.save("127.0.0.1#t", port, "tok-1")

    def run_script(command: str) -> None:
        request = Path(command.split("ScriptPath=", 1)[1]).read_text()
        response = re.search(r'BRIDGE_RESPONSE = "([^"]+)"', request).group(1)
        assert 'BRIDGE_REQUEST = {["action"] = "overview", ["flow"] = 1}' in request
        Path(response).write_text(json.dumps({"ok": True, "result": {"title": "T"}}))

    fake.on_command = run_script
    async with DoricoClient(port=port, client_name="t", store=store) as client:
        result = await DoricoBridge(client, workdir=tmp_path / "work").overview()
    assert result == {"title": "T"}
    assert list((tmp_path / "work").iterdir()) == []  # request and response cleaned up


async def test_export_pdf_answers_overwrite_and_reads_path_from_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from ai_score_editing.dorico import export

    log = tmp_path / "application.log"
    log.write_text("old line\n")
    pdf = tmp_path / "01 - Full score - Song.pdf"
    clicked: list[tuple[str, ...]] = []

    async def fake_osascript(script: str, *args: str) -> str:
        if script is export._DIALOGS:
            return "" if clicked else "2\tOne or more output files already exist. Do you want to overwrite them?"
        clicked.append(args)
        pdf.write_bytes(b"%PDF")
        with log.open("a") as handle:
            handle.write(f"[info] Exporting PDF to {pdf}\n[info] notifyPostCommandExecute: Print.ExportCurrentLayoutAsPDF (4 ms)\n")
        return "clicked"

    class Client:
        commands: list[str] = []

        async def command(self, command: str) -> None:
            self.commands.append(command)

    monkeypatch.setattr(export, "osascript", fake_osascript)
    client = Client()
    assert await export.export_pdf(client, log) == pdf  # type: ignore[arg-type]
    assert client.commands == ["Print.ExportCurrentLayoutAsPDF"]
    assert clicked == [("2", "Overwrite")]


class _FakeOsascript:
    """Stands in for an osascript child process; never runs a real one."""

    def __init__(self, stdout: bytes = b"", stderr: bytes = b"", returncode: int = 0, hang: bool = False) -> None:
        self.stdout, self.stderr, self.hang = stdout, stderr, hang
        self.result = returncode
        self.returncode: int | None = None
        self.input: bytes | None = None
        self.killed = False
        self.waited = False

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


def _spawn(monkeypatch: pytest.MonkeyPatch, process: _FakeOsascript) -> list[tuple[Any, ...]]:
    from ai_score_editing import macos

    calls: list[tuple[Any, ...]] = []

    async def fake_exec(*args: Any, **kwargs: Any) -> _FakeOsascript:
        calls.append(args)
        assert kwargs["stdin"] == kwargs["stdout"] == kwargs["stderr"] == asyncio.subprocess.PIPE
        return process

    monkeypatch.setattr(macos.asyncio, "create_subprocess_exec", fake_exec)
    return calls


async def test_osascript_runs_without_blocking_and_decodes_like_text_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    from ai_score_editing.dorico import export

    process = _FakeOsascript(stdout="Titre\tSérénade\rsecond line\r\n".encode())
    calls = _spawn(monkeypatch, process)
    out = await export.osascript('tell process "%(process)s" to item 1 of argv', "a b", "c")
    assert calls == [("osascript", "-", "a b", "c")]
    assert process.input == 'tell process "Dorico 6" to item 1 of argv'.encode()
    assert out == "Titre\tSérénade\nsecond line"


@pytest.mark.parametrize(
    ("stderr", "message"),
    [
        (b"execution error: osascript is not allowed assistive access. (-1719)\n", "Accessibility permission"),
        (b"syntax error: oops (-2741)\n", r"UI scripting failed: syntax error: oops \(-2741\)$"),
    ],
)
async def test_osascript_failure_messages(monkeypatch: pytest.MonkeyPatch, stderr: bytes, message: str) -> None:
    from ai_score_editing.dorico import export

    _spawn(monkeypatch, _FakeOsascript(stderr=stderr, returncode=1))
    with pytest.raises(DoricoError, match=message):
        await export.osascript("script")


async def test_osascript_timeout_kills_the_child(monkeypatch: pytest.MonkeyPatch) -> None:
    import subprocess

    from ai_score_editing.dorico import export

    process = _FakeOsascript(hang=True)
    _spawn(monkeypatch, process)
    monkeypatch.setattr(export, "OSASCRIPT_TIMEOUT", 0.01)
    with pytest.raises(subprocess.TimeoutExpired):  # as subprocess.run raised, not an OSError
        await export.osascript("script", "x")
    assert process.killed and process.waited


async def test_osascript_cancellation_kills_the_child(monkeypatch: pytest.MonkeyPatch) -> None:
    from ai_score_editing.dorico import export

    process = _FakeOsascript(hang=True)
    _spawn(monkeypatch, process)
    task = asyncio.create_task(export.osascript("script"))
    await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert process.killed and process.waited


async def test_bridge_wait_for_polls_without_blocking(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    response = tmp_path / "response.json"

    async def answer_later() -> None:
        await asyncio.sleep(0.05)  # runs only if the poll yields to the event loop
        response.write_text(json.dumps({"ok": True}))

    writer = asyncio.create_task(answer_later())
    assert await DoricoBridge._wait_for(response) == {"ok": True}
    await writer
    monkeypatch.setattr(bridge_mod, "RESPONSE_TIMEOUT", 0.05)
    with pytest.raises(DoricoError, match="did not answer"):
        await DoricoBridge._wait_for(tmp_path / "never.json")


async def test_read_project_info_drives_the_dialog(monkeypatch: pytest.MonkeyPatch) -> None:
    from ai_score_editing.dorico import project_info

    state = {"open": False}
    scripts: list[tuple[str, ...]] = []

    async def fake_osascript(script: str, *args: str) -> str:
        scripts.append(args)
        if script is project_info._OPEN:
            return "yes" if state["open"] else "no"
        if script is project_info._READ:
            return "Title\tSong\nComposer\tMe\nNot a field\tx"
        if script is project_info._PRESS:
            state["open"] = False
            return "clicked"
        raise AssertionError(script)

    async def front() -> None:
        scripts.append(("front",))

    class Client:
        async def command(self, command: str) -> None:
            assert command == "File.ScoreInfo"
            state["open"] = True

    class Bridge:
        client = Client()

    monkeypatch.setattr(project_info, "osascript", fake_osascript)
    monkeypatch.setattr(project_info, "bring_to_front", front)
    assert await project_info.read_project_info(Bridge()) == {"Title": "Song", "Composer": "Me"}  # type: ignore[arg-type]
    assert ("front",) in scripts and ("Close",) in scripts and not state["open"]


# ------------------------------------------------------------------ project info

@pytest.mark.parametrize(
    ("fields", "message"),
    [({"Composr": "x"}, "unknown Project Info fields"), ({}, "no fields"), ({"Title": "a\nb"}, "single-line")],
)
async def test_set_project_info_validates_before_opening_the_dialog(fields: dict[str, str], message: str) -> None:
    from ai_score_editing.dorico import project_info

    with pytest.raises(DoricoError, match=message):
        await project_info.set_project_info(None, fields)  # type: ignore[arg-type]


def test_private_export_folder_is_emptied_and_guarded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from ai_score_editing.dorico import export

    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    work = tmp_path / "cache" / "ai-score-editing" / "dorico"
    monkeypatch.setattr(export, "EXPORT_DIR", work / "musicxml")
    old = work / "musicxml" / "Flows from Old"
    old.mkdir(parents=True)
    (old / "Old - Full score - 01 Old.musicxml").write_text("<x/>")
    assert export._clear_export_dir() == (work / "musicxml").resolve()
    assert list((work / "musicxml").iterdir()) == []
    monkeypatch.setattr(export, "EXPORT_DIR", tmp_path / "Scores")
    with pytest.raises(DoricoError, match="refusing to clear"):
        export._clear_export_dir()
