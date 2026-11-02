"""The three command lines share subcommand and option names (Phase 4)."""

from __future__ import annotations

import argparse

import pytest

from ai_score_editing import cli_common
from ai_score_editing.dorico.cli import build_parser as dorico_parser
from ai_score_editing.musescore.cli import build_parser as musescore_parser
from ai_score_editing.sibelius.cli import build_parser as sibelius_parser


def _subcommands(parser: argparse.ArgumentParser) -> dict[str, argparse.ArgumentParser]:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return dict(action.choices)
    raise AssertionError("no subcommands")


def _options(parser: argparse.ArgumentParser) -> set[str]:
    return {o for a in parser._actions for o in a.option_strings if o not in ("-h", "--help")}


COMMANDS = {
    "sibelius": _subcommands(sibelius_parser()),
    "dorico": _subcommands(dorico_parser()),
    "musescore": _subcommands(musescore_parser()),
}

#: Options only some back ends have, by subcommand: aliases, deprecated
#: spellings and real differences of the editor.
ALLOWED_EXTRA: dict[str, dict[str, set[str]]] = {
    "query": {"dorico": {"--lyrics"}},
    "export": {"sibelius": {"--out", "--file"}},
    # --no-backup / --backup-dir: Dorico's opt-out of its default-on pre-apply
    # backup (Phase 10); Sibelius and MuseScore always back up.
    "apply": {"sibelius": {"--save"}, "dorico": {"--no-backup", "--backup-dir"}},
    "install-plugin": {"sibelius": {"--plugin-dir"}},
}
#: Options a back end lacks although another has them.
ALLOWED_MISSING: dict[str, dict[str, set[str]]] = {
    "query": {"dorico": {"--field"}},
    "apply": {"sibelius": {"--json"}},
    "structure": {"dorico": {"--bars"}},
}


def test_shared_subcommands_have_equal_options() -> None:
    names = {c for cmds in COMMANDS.values() for c in cmds}
    for command in sorted(names):
        having = {s: _options(cmds[command]) for s, cmds in COMMANDS.items() if command in cmds}
        if len(having) < 2:
            continue
        extras = ALLOWED_EXTRA.get(command, {})
        missing = ALLOWED_MISSING.get(command, {})
        core = {s: o - extras.get(s, set()) for s, o in having.items()}
        expected = set.union(*core.values())
        for s, found in core.items():
            assert found == expected - missing.get(s, set()), f"{command}: {s} has {found}, expected {expected}"


@pytest.mark.parametrize("back_end", COMMANDS)
def test_canonical_flags(back_end: str) -> None:
    commands = COMMANDS[back_end]
    assert "--path" in _options(commands["save"])
    assert {"--format", "--path"} <= _options(commands["export"])
    assert "--limit" in _options(commands["query"])
    if "lyrics" in commands:
        assert "--staff" in _options(commands["lyrics"])
        assert {"--staff", "--text"} <= _options(commands["edit-lyrics"])


def test_one_query_limit() -> None:
    for back_end, commands in COMMANDS.items():
        limit = next(a for a in commands["query"]._actions if "--limit" in a.option_strings)
        assert limit.default == cli_common.DEFAULT_LIMIT, back_end


def test_dorico_set_info_takes_field_or_positionals() -> None:
    args = dorico_parser().parse_args(["set-info", "--field", "Composer=X", "Title=Y"])
    assert args.field == ["Composer=X"] and args.fields == ["Title=Y"]


def test_sibelius_out_is_an_alias_of_path() -> None:
    parser = sibelius_parser()
    assert parser.parse_args(["export", "--out", "a.pdf"]).out == "a.pdf"
    assert parser.parse_args(["export", "--path", "a.pdf"]).out == "a.pdf"
    assert parser.parse_args(["export", "--format", "mid"]).format == "midi"


def test_musescore_mid_is_an_alias_of_midi() -> None:
    assert musescore_parser().parse_args(["export", "--format", "mid"]).format == "midi"


def test_dorico_export_path_positional_or_option() -> None:
    parser = dorico_parser()
    assert cli_common.resolve_path(parser.parse_args(["export", "out.pdf"])) == "out.pdf"
    assert cli_common.resolve_path(parser.parse_args(["export", "--path", "out.pdf"])) == "out.pdf"
    assert cli_common.resolve_path(parser.parse_args(["export"])) is None
    with pytest.raises(SystemExit):
        parser.parse_args(["export", "a.pdf", "--path", "b.pdf"])


def test_dorico_lyrics_player_positional_still_parses() -> None:
    args = dorico_parser().parse_args(["lyrics", "Soprano", "--verse", "2"])
    assert args.player == "Soprano" and args.staff is None
    assert dorico_parser().parse_args(["lyrics", "--staff", "1"]).staff == "1"
