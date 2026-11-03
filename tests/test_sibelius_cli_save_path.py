"""``sibelius-cli save --path`` must refuse, not silently save in place."""

from __future__ import annotations

import pytest
from fakes import CliSession

from ai_score_editing.sibelius.cli import main
from ai_score_editing.sibelius.commands._common import EXIT_COMMAND_FAILED, EXIT_OK


def test_save_with_a_path_is_refused_and_saves_nothing(
    cli_session: CliSession, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["save", "--path", "/tmp/copy.sib"]) == EXIT_COMMAND_FAILED
    assert "cannot save a copy" in capsys.readouterr().err
    assert "Save" not in cli_session.client.methods()


def test_save_without_a_path_still_saves(cli_session: CliSession, capsys: pytest.CaptureFixture[str]) -> None:
    cli_session.client.replies["Save"] = {"fileName": "/tmp/score.sib"}
    assert main(["save"]) == EXIT_OK
    assert "saved: /tmp/score.sib" in capsys.readouterr().out
    assert "Save" in cli_session.client.methods()
