from __future__ import annotations

import os
import threading
from pathlib import Path

import pytest

from ai_score_editing import paths


@pytest.fixture
def xdg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    return tmp_path


def test_xdg_is_respected(xdg: Path) -> None:
    assert paths.config_dir() == xdg / "config" / "ai-score-editing"
    assert paths.cache_dir() == xdg / "cache" / "ai-score-editing"
    assert paths.cache_dir("dorico", "musicxml") == xdg / "cache" / "ai-score-editing" / "dorico" / "musicxml"


def test_defaults_to_home_dot_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert paths.config_dir() == tmp_path / ".config" / "ai-score-editing"
    assert paths.cache_dir() == tmp_path / ".cache" / "ai-score-editing"


def test_fresh_install_creates_nothing(xdg: Path) -> None:
    paths.config_dir()
    assert not (xdg / "config").exists()


def test_migration_moves_and_leaves_a_symlink(xdg: Path) -> None:
    old = xdg / "config" / "sibelius-websocket-cli"
    old.mkdir(parents=True)
    token = old / "token.json"
    token.write_text("{}")
    token.chmod(0o600)
    new = paths.config_dir()
    assert (new / "token.json").read_text() == "{}"
    assert (new / "token.json").stat().st_mode & 0o777 == 0o600
    assert old.is_symlink() and old.resolve() == new.resolve()
    assert (old / "token.json").exists()  # an older checkout still finds it


def test_cache_migrates_too(xdg: Path) -> None:
    old = xdg / "cache" / "sibelius-websocket-cli" / "dorico"
    old.mkdir(parents=True)
    (old / "x").write_text("1")
    assert (paths.cache_dir("dorico") / "x").read_text() == "1"
    assert (xdg / "cache" / "sibelius-websocket-cli").is_symlink()


def test_second_run_does_nothing(xdg: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    old = xdg / "config" / "sibelius-websocket-cli"
    old.mkdir(parents=True)
    paths.config_dir()
    calls: list[object] = []
    monkeypatch.setattr(os, "replace", lambda *a: calls.append(a))
    paths.config_dir()
    assert calls == []


def test_existing_new_folder_is_left_alone(xdg: Path) -> None:
    old = xdg / "config" / "sibelius-websocket-cli"
    new = xdg / "config" / "ai-score-editing"
    old.mkdir(parents=True)
    new.mkdir()
    (old / "a").write_text("old")
    paths.config_dir()
    assert not old.is_symlink() and (old / "a").exists() and not (new / "a").exists()


@pytest.mark.parametrize("error", [FileNotFoundError, FileExistsError])
def test_race_lost_to_another_process_is_not_an_error(
    xdg: Path, monkeypatch: pytest.MonkeyPatch, error: type[OSError]
) -> None:
    old = xdg / "config" / "sibelius-websocket-cli"
    old.mkdir(parents=True)

    def lose(src: Path, dst: Path) -> None:
        raise error()

    monkeypatch.setattr(os, "replace", lose)
    assert paths.config_dir() == xdg / "config" / "ai-score-editing"


def test_concurrent_first_use(xdg: Path) -> None:
    old = xdg / "config" / "sibelius-websocket-cli"
    old.mkdir(parents=True)
    (old / "token.json").write_text("{}")
    errors: list[BaseException] = []
    barrier = threading.Barrier(8)

    def run() -> None:
        try:
            barrier.wait()
            paths.config_dir()
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=run) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert (xdg / "config" / "ai-score-editing" / "token.json").read_text() == "{}"
    assert old.is_symlink()


def test_wire_client_name_is_editor_neutral() -> None:
    assert paths.WIRE_CLIENT_NAME == "ai-score-editing"
    assert paths.LEGACY_WIRE_CLIENT_NAME == "sibelius-websocket-cli"
