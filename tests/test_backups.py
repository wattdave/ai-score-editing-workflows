"""One backup policy: folder rule, naming, and every service's real apply."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import pytest

from ai_score_editing import backups
from ai_score_editing.dorico import service as dorico_service
from ai_score_editing.musescore import service as musescore_service
from ai_score_editing.sibelius import bridge, service as sibelius_service
from fakes import FakeSibeliusClient

NAME = re.compile(r"^(?P<stem>.+)\.backup-\d{8}-\d{6}(?P<suffix>\.\w+)$")


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for editor in backups.EDITORS:
        monkeypatch.delenv(backups.env_name(editor), raising=False)
    monkeypatch.delenv(backups.COMMON_ENV, raising=False)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))


def test_folder_order_argument_editor_env_common_env_default(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cache = tmp_path / "cache" / "ai-score-editing"
    assert backups.folder("sibelius") is None
    assert backups.folder("dorico") == cache / "dorico" / "backups"
    assert backups.folder("musescore") == cache / "musescore" / "backups"
    monkeypatch.setenv("SCORE_BACKUP_DIR", str(tmp_path / "common"))
    assert backups.folder("sibelius") == tmp_path / "common"
    monkeypatch.setenv("DORICO_BACKUP_DIR", str(tmp_path / "d"))
    assert backups.folder("dorico") == tmp_path / "d"
    assert backups.folder("musescore") == tmp_path / "common"
    assert backups.folder("dorico", tmp_path / "arg") == tmp_path / "arg"


def test_name_and_prune(tmp_path: Path) -> None:
    assert backups.name("Song", ".sib", "20260102-030405") == "Song.backup-20260102-030405.sib"
    assert NAME.match(backups.name("Song", ".dorico"))
    for day in ("01", "02", "03"):
        (tmp_path / backups.name("S", ".sib", f"202601{day}-000000")).write_text(day)
    (tmp_path / "other.sib").write_text("x")
    for i, p in enumerate(sorted(tmp_path.glob("*.backup-*"))):
        os.utime(p, (1000 + i, 1000 + i))
    removed = backups.prune(tmp_path, keep=2)
    assert [p.name for p in removed] == ["S.backup-20260101-000000.sib"]
    assert (tmp_path / "other.sib").exists() and len(list(tmp_path.glob("*.backup-*"))) == 2


# ------------------------------------------------------------------ Sibelius

OPS = [{"op": "set", "staff": 1, "bar": 1, "index": 0, "prop": "Dx", "value": 8}]


def _sibelius(tmp_path: Path) -> tuple[bridge.SibeliusBridge, FakeSibeliusClient, Path]:
    score = tmp_path / "song.sib"
    score.write_bytes(b"sib")
    client = FakeSibeliusClient({
        "GetBridgeVersion": {"version": 62}, "Save": {"fileName": str(score)},
        "ApplyBatch": {"applied": 1, "results": []},
    })
    return bridge.SibeliusBridge(client), client, score  # type: ignore[arg-type]


async def test_sibelius_default_is_beside_the_score_and_before_the_write(tmp_path: Path) -> None:
    b, client, score = _sibelius(tmp_path)
    result = await sibelius_service.apply(b, OPS)
    copy = Path(result["backup"])
    assert copy.parent == tmp_path and NAME.match(copy.name) and copy.name.startswith("song.backup-")
    methods = client.methods()
    assert methods.index("Save") < max(i for i, m in enumerate(methods) if m == "ApplyBatch")


async def test_sibelius_env_and_common_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    b, _, _ = _sibelius(tmp_path)
    monkeypatch.setenv("SCORE_BACKUP_DIR", str(tmp_path / "common"))
    assert Path((await sibelius_service.apply(b, OPS))["backup"]).parent == tmp_path / "common"
    monkeypatch.setenv("SIBELIUS_BACKUP_DIR", str(tmp_path / "env"))
    assert Path((await sibelius_service.apply(b, OPS))["backup"]).parent == tmp_path / "env"
    result = await sibelius_service.apply(b, OPS, backup_dir=tmp_path / "arg")
    assert Path(result["backup"]).parent == tmp_path / "arg"


async def test_sibelius_dry_run_takes_no_backup(tmp_path: Path) -> None:
    b, client, _ = _sibelius(tmp_path)
    result = await sibelius_service.apply(b, OPS, dry_run=True)
    assert "backup" not in result and "Save" not in client.methods()
    assert not list(tmp_path.glob("*.backup-*"))


# ------------------------------------------------------------------ MuseScore

class MuseScoreStub:
    """Just enough of MuseScoreBridge for apply; logs the order of calls."""

    def __init__(self) -> None:
        self.log: list[str] = []

    async def write_copy(self, path: str) -> dict[str, Any]:
        self.log.append("write_copy")
        Path(path).write_text("<xml/>")
        return {"written": True}

    async def apply(self, primitives: Any, expect: Any, digests: Any, *, dry_run: bool, copy: Any) -> dict[str, Any]:
        self.log.append("apply-dry" if dry_run else "apply")
        return {"applied": 0, "results": []}


@pytest.fixture
def musescore(monkeypatch: pytest.MonkeyPatch) -> MuseScoreStub:
    snap = musescore_service.Snapshot(
        {"name": "Scratch", "staves": 1}, [], {"barCount": 1, "bars": [], "division": 480, "content": []}, {}  # type: ignore[arg-type]
    )

    async def snapshot(_: Any) -> Any:
        return snap

    monkeypatch.setattr(musescore_service, "snapshot", snapshot)
    monkeypatch.setattr(musescore_service.score, "prepare_batch", lambda *a: ([], {}, None))
    return MuseScoreStub()


async def test_musescore_backup_default_env_and_order(
    musescore: MuseScoreStub, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    result = await musescore_service.apply(musescore, [])  # type: ignore[arg-type]
    path = Path(result["backup"])
    assert path.parent == tmp_path / "cache" / "ai-score-editing" / "musescore" / "backups"
    assert NAME.match(path.name) and path.name.startswith("Scratch.backup-") and path.suffix == ".musicxml"
    assert musescore.log == ["write_copy", "apply"]
    monkeypatch.setenv("MUSESCORE_BACKUP_DIR", str(tmp_path / "env"))
    result = await musescore_service.apply(musescore, [])  # type: ignore[arg-type]
    assert Path(result["backup"]).parent == tmp_path / "env"


async def test_musescore_dry_run_takes_no_backup(musescore: MuseScoreStub, tmp_path: Path) -> None:
    result = await musescore_service.apply(musescore, [], dry_run=True)  # type: ignore[arg-type]
    assert "backup" not in result and musescore.log == ["apply-dry"]
    assert not (tmp_path / "cache").exists()


# ------------------------------------------------------------------ Dorico

class DoricoStub:
    def __init__(self) -> None:
        self.log: list[str] = []
        self.client = self

    async def status(self) -> dict[str, Any]:
        return {"notReadOnly": True}

    async def overview(self, flow: int = 1) -> dict[str, Any]:
        return {"title": "My: Song/1"}

    async def save(self, path: Path) -> dict[str, Any]:
        self.log.append("save")
        path.write_text("dorico")
        return {}

    async def apply(self, ops: Any, flow: int, dry_run: bool = False) -> dict[str, Any]:
        self.log.append("apply-dry" if dry_run else "apply")
        return {"applied": 1, "results": []}


@pytest.fixture
def dorico(monkeypatch: pytest.MonkeyPatch) -> DoricoStub:
    async def snapshot(*_: Any, **__: Any) -> Any:
        return dorico_service.Snapshot([], [], None)  # type: ignore[arg-type]

    monkeypatch.setattr(dorico_service, "snapshot", snapshot)
    monkeypatch.setattr(dorico_service.score, "prepare_batch", lambda *a: [{"op": "set"}])
    return DoricoStub()


async def test_dorico_backup_default_env_argument_and_order(
    dorico: DoricoStub, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    result = await dorico_service.apply(dorico, [])  # type: ignore[arg-type]
    path = Path(result["backup"])
    assert path.parent == tmp_path / "cache" / "ai-score-editing" / "dorico" / "backups"
    assert NAME.match(path.name) and path.name.startswith("My_ Song_1.backup-") and path.suffix == ".dorico"
    assert dorico.log == ["apply-dry", "save", "apply"]  # checked, backed up, then written
    monkeypatch.setenv("DORICO_BACKUP_DIR", str(tmp_path / "env"))
    assert Path((await dorico_service.apply(dorico, []))["backup"]).parent == tmp_path / "env"  # type: ignore[arg-type]
    result = await dorico_service.apply(dorico, [], backup_dir=tmp_path / "arg")  # type: ignore[arg-type]
    assert Path(result["backup"]).parent == tmp_path / "arg"


async def test_dorico_dry_run_and_opt_out_take_no_backup(dorico: DoricoStub) -> None:
    result = await dorico_service.apply(dorico, [], dry_run=True)  # type: ignore[arg-type]
    assert "backup" not in result and "save" not in dorico.log
    result = await dorico_service.apply(dorico, [], backup_copy=False)  # type: ignore[arg-type]
    assert "backup" not in result and "save" not in dorico.log and result["applied"] == 1


async def test_dorico_command_batch_backs_up_after_checks_before_writing(
    dorico: DoricoStub, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(dorico_service.score, "prepare_batch", lambda *a: [{"op": "set-break"}])

    async def commands(bridge: Any, prepared: Any, snap: Any, flow: int, dry_run: bool, take: Any = None) -> Any:
        if dry_run:
            return {"dryRun": True}
        bridge.log.append("commands-start")
        copy = await take()
        bridge.log.append("written")
        return {"applied": 1, "backup": copy}

    monkeypatch.setattr(dorico_service, "_apply_commands", commands)
    monkeypatch.setattr(dorico_service.score, "COMMAND_OPS", {"set-break"})
    result = await dorico_service.apply(dorico, [])  # type: ignore[arg-type]
    assert result["backup"].endswith(".dorico") and dorico.log == ["commands-start", "save", "written"]
