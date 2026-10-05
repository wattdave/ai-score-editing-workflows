"""Unit tests for the launcher module."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ai_score_editing import launcher


def test_is_local_host() -> None:
    assert launcher.is_local_host("localhost") is True
    assert launcher.is_local_host("LOCALHOST") is True
    assert launcher.is_local_host("127.0.0.1") is True
    assert launcher.is_local_host("127.0.0.2") is True
    assert launcher.is_local_host("::1") is True
    assert launcher.is_local_host("0.0.0.0") is True

    assert launcher.is_local_host("example.com") is False
    assert launcher.is_local_host("192.168.1.50") is False
    assert launcher.is_local_host("10.0.0.1") is False


def test_is_sibelius_running_macos_pgrep_found() -> None:
    mock_run = MagicMock(return_value=MagicMock(returncode=0))
    with patch("sys.platform", "darwin"), patch("subprocess.run", mock_run):
        assert launcher.is_sibelius_running() is True
    mock_run.assert_called_once_with(
        ["pgrep", "-i", "-x", "Sibelius"],
        capture_output=True,
        check=False,
    )


def test_is_sibelius_running_macos_pgrep_missing_osascript_found() -> None:
    def fake_run(cmd: list[str], **kwargs: object) -> MagicMock:
        if cmd[0] == "pgrep":
            return MagicMock(returncode=1)
        elif cmd[0] == "osascript":
            return MagicMock(returncode=0, stdout="true\n")
        return MagicMock(returncode=1)

    with patch("sys.platform", "darwin"), patch("subprocess.run", side_effect=fake_run):
        assert launcher.is_sibelius_running() is True


def test_is_sibelius_running_macos_not_running() -> None:
    mock_run = MagicMock(return_value=MagicMock(returncode=1, stdout="false\n"))
    with patch("sys.platform", "darwin"), patch("subprocess.run", mock_run):
        assert launcher.is_sibelius_running() is False


def test_is_sibelius_running_windows() -> None:
    mock_run = MagicMock(
        return_value=MagicMock(returncode=0, stdout="Sibelius.exe                 1234 Console")
    )
    with patch("sys.platform", "win32"), patch("subprocess.run", mock_run):
        assert launcher.is_sibelius_running() is True

    mock_run_not_found = MagicMock(return_value=MagicMock(returncode=0, stdout="INFO: No tasks"))
    with patch("sys.platform", "win32"), patch("subprocess.run", mock_run_not_found):
        assert launcher.is_sibelius_running() is False


def test_find_sibelius_app_custom_path(tmp_path: Path) -> None:
    fake_app = tmp_path / "FakeSibelius.app"
    fake_app.mkdir()
    assert launcher.find_sibelius_app(fake_app) == fake_app.resolve()

    missing_app = tmp_path / "Missing.app"
    with pytest.raises(FileNotFoundError):
        launcher.find_sibelius_app(missing_app)


def test_launch_sibelius_macos() -> None:
    mock_popen = MagicMock()
    with patch("sys.platform", "darwin"), patch("subprocess.Popen", mock_popen):
        with patch.object(Path, "exists", return_value=True):
            launcher.launch_sibelius("/Applications/Sibelius.app")
    mock_popen.assert_called_once_with(["open", "-a", "/Applications/Sibelius.app"])


def test_launch_sibelius_windows() -> None:
    mock_popen = MagicMock()
    with patch("sys.platform", "win32"), patch("subprocess.Popen", mock_popen):
        launcher.launch_sibelius()
    mock_popen.assert_called_once_with(["cmd", "/c", "start", "", "Sibelius"])


def test_open_score_file_macos(tmp_path: Path) -> None:
    score = tmp_path / "test.mxl"
    score.touch()
    mock_popen = MagicMock()
    with patch("sys.platform", "darwin"), patch("subprocess.Popen", mock_popen):
        with patch.object(Path, "exists", return_value=True):
            launcher.open_score_file(score, app_path="/Applications/Sibelius.app")
    mock_popen.assert_called_once_with(["open", "-a", "/Applications/Sibelius.app", str(score.resolve())])


def test_open_score_file_windows(tmp_path: Path) -> None:
    score = tmp_path / "test.mxl"
    score.touch()
    with patch("sys.platform", "win32"), patch("os.startfile", create=True) as mock_startfile:
        launcher.open_score_file(score)
        mock_startfile.assert_called_once_with(str(score.resolve()))
