"""MuseScore CLI argument parsing and plug-in installation."""

import json

from ai_score_editing.musescore import cli

from musescore_common import ScoreBridge, config  # noqa: F401,F811


def test_cli_install_plugin(config, capsys) -> None:
    assert cli.main(["install-plugin"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["installed"].endswith("ScoreBridge/msbridge.qml")


def test_cli_query_parses(monkeypatch) -> None:
    args = cli.build_parser().parse_args(["query", "--staff", "1", "--bars", "2-3", "--where", "Pitch>60"])
    assert args.staves == ["1"] and args.bars == "2-3"


def test_cli_files_commands_parse() -> None:
    parser = cli.build_parser()
    assert parser.parse_args(["export", "--format", "png", "--path", "x.png"]).format == "png"
    assert parser.parse_args(["set-info", "--field", "composer=Anon."]).field == ["composer=Anon."]
    assert parser.parse_args(["edit-lyrics", "--staff", "1", "--text", "a b"]).verse == 1
