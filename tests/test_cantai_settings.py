"""Cantai score language: settings-file edits and the cantai-language command."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from ai_score_editing.sibelius import cantai_settings as cs
from ai_score_editing.sibelius import cli, service

SCORE_ID = "6B004C9D-A80F-4D82-AFB2-626F9422F102"
KEY = "sibLang_" + hashlib.md5(SCORE_ID.encode()).hexdigest()

SETTINGS = (
    '<?xml version="1.0" encoding="UTF-8"?>\r\n\r\n<PROPERTIES>\r\n'
    '  <VALUE name="scoreLanguage" val="es"/>\r\n'
    f'  <VALUE name="{KEY}" val="la"/>\r\n'
    '  <VALUE name="sibVoice_0123" val="5016"/>\r\n'
    "</PROPERTIES>\r\n"
)


def test_score_key_matches_cantai_hash():
    # Key observed in a real Cantai.settings for this score id.
    assert cs.score_key(SCORE_ID) == "sibLang_b7a0c7b0f874ebb16dd120707f09b5db"


@pytest.mark.parametrize(
    ("given", "code"),
    [("la", "la"), ("Latin", "la"), ("EN", "en"), ("en-gb", "en-GB"), ("spanish", "es"), ("pt-br", "pt-BR")],
)
def test_normalize_language(given, code):
    assert cs.normalize_language(given) == code


def test_normalize_language_rejects_unknown():
    with pytest.raises(cs.CantaiSettingsError):
        cs.normalize_language("de")


def test_read_and_set_score_language_keeps_everything_else():
    assert cs.score_language(SETTINGS, SCORE_ID) == "la"
    assert cs.default_language(SETTINGS) == "es"
    new = cs.set_score_language(SETTINGS, SCORE_ID, "en")
    assert cs.score_language(new, SCORE_ID) == "en"
    assert new == SETTINGS.replace(f'"{KEY}" val="la"', f'"{KEY}" val="en"')


def test_set_adds_missing_entry_and_default():
    other = "00000000-1111-2222-3333-444444444444"
    new = cs.set_score_language(SETTINGS, other, "en-GB", also_default=True)
    assert cs.score_language(new, other) == "en-GB"
    assert cs.default_language(new) == "en-GB"
    assert cs.score_language(new, SCORE_ID) == "la"
    assert "\r\n" in new and "\n  <VALUE" not in new.replace("\r\n", "")


def test_bad_score_id():
    with pytest.raises(cs.CantaiSettingsError):
        cs.score_key("not-a-guid")


def test_read_active_score(tmp_path: Path):
    cfg = tmp_path / "cfg.json"
    cfg.write_text(json.dumps({"activeScore": {"scoreId": SCORE_ID, "scoreName": "palestrina"}}))
    assert cs.read_active_score(cfg) == cs.ActiveScore(SCORE_ID, "palestrina")
    cfg.write_text(json.dumps({"activeScore": None, "schemaVersion": 1}))
    assert cs.read_active_score(cfg) is None
    assert cs.read_active_score(tmp_path / "missing.json") is None


def _files(tmp_path: Path, active: bool = True) -> tuple[Path, Path]:
    settings = tmp_path / "Cantai.settings"
    settings.write_bytes(SETTINGS.encode())
    cfg = tmp_path / "cfg.json"
    cfg.write_text(json.dumps({"activeScore": {"scoreId": SCORE_ID, "scoreName": "x"} if active else None}))
    return settings, cfg


def _run(settings: Path, cfg: Path, *extra: str) -> int:
    return cli.main(["--json", "cantai-language", *extra, "--settings", str(settings), "--export-config", str(cfg)])


def test_command_reads_active_score(tmp_path, capsys):
    settings, cfg = _files(tmp_path)
    assert _run(settings, cfg) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["scoreId"] == SCORE_ID and out["language"] == "la" and out["defaultLanguage"] == "es"


def test_command_sets_language_with_sibelius_quit(tmp_path, capsys, monkeypatch):
    settings, cfg = _files(tmp_path, active=False)
    monkeypatch.setattr("ai_score_editing.sibelius.launcher.is_sibelius_running", lambda: False)
    # cli.main exports --backup-dir to the environment; let monkeypatch undo that.
    monkeypatch.setenv(service.BACKUP_DIR_ENV, "")
    monkeypatch.delenv(service.BACKUP_DIR_ENV)
    backups = tmp_path / "bak"
    code = cli.main([
        "--json", "--backup-dir", str(backups), "cantai-language", "Spanish", "--score-id", SCORE_ID,
        "--settings", str(settings), "--export-config", str(cfg),
    ])
    assert code == 0
    out = json.loads(capsys.readouterr().out)
    assert out["newLanguage"] == "es" and out["changed"]
    assert cs.score_language(settings.read_text(newline=""), SCORE_ID) == "es"
    backup_files = list(Path(out["backup"]).parent.glob("Cantai.settings.*.bak"))
    assert len(backup_files) == 1 and backup_files[0].read_bytes() == SETTINGS.encode()


def test_command_refuses_while_sibelius_runs(tmp_path, capsys, monkeypatch):
    settings, cfg = _files(tmp_path)
    monkeypatch.setattr("ai_score_editing.sibelius.launcher.is_sibelius_running", lambda: True)
    assert _run(settings, cfg, "en") != 0
    assert "Quit Sibelius" in capsys.readouterr().err
    assert settings.read_bytes() == SETTINGS.encode()


def test_command_dry_run_and_no_active_score(tmp_path, capsys, monkeypatch):
    settings, cfg = _files(tmp_path, active=False)
    assert _run(settings, cfg) != 0
    assert "no active score" in capsys.readouterr().err
    monkeypatch.setattr("ai_score_editing.sibelius.launcher.is_sibelius_running", lambda: True)
    assert _run(settings, cfg, "en", "--score-id", SCORE_ID, "--dry-run") == 0
    assert settings.read_bytes() == SETTINGS.encode()
