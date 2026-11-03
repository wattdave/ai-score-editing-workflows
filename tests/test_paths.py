from __future__ import annotations

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


def test_wire_client_name_is_editor_neutral() -> None:
    assert paths.WIRE_CLIENT_NAME == "ai-score-editing"
