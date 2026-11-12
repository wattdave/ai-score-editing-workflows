"""CLI write commands: patch, apply, batch operations and range commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from fakes import CliSession, bridge_apply_batch, bridge_call
from ai_score_editing.sibelius.cli import build_parser
from ai_score_editing.sibelius.commands._common import EXIT_COMMAND_FAILED, EXIT_OK
from ai_score_editing.sibelius.commands.layout import _run_patch_layout, _run_set_time
from ai_score_editing.sibelius.commands.lyrics import _run_patch_lyrics
from ai_score_editing.sibelius.commands.notes import _run_add_notes, _run_beam, _run_bracket, _run_copy_passage, _run_delete_voice, _run_patch_notes, _run_tie, _run_transpose
from ai_score_editing.sibelius.commands.score import _run_add_bars, _run_apply


def _client_context() -> tuple[MagicMock, AsyncMock]:
    context = MagicMock()
    client = AsyncMock()
    context.__aenter__.return_value = client
    return context, client


async def test_patch_layout_uses_one_context_and_one_backup(cli_session: CliSession, 
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    patch_file = tmp_path / "layout.json"
    patch_file.write_text(
        '[{"op":"nudge","staff":1,"bar":4,"index":2,"dx":8},'
        '{"op":"set-barline","bar":20,"type":"end_repeat"}]'
    )
    args = build_parser().parse_args(["patch-layout", "--file", str(patch_file), "--save"])
    context, client = cli_session.context, cli_session.client

    async def bridge_side_effect(
        unused_client: Any, method: str, call_args: list[Any] | None = None
    ) -> Any:
        del unused_client, call_args
        if method == "Save":
            return {"fileName": "/scores/a.sib"}
        return {"changed": True}

    with (
        patch("ai_score_editing.sibelius.runner.backup", new=AsyncMock(return_value={"copy": "/scores/a.backup.sib"})) as backup,
        bridge_apply_batch(new=AsyncMock(return_value={"applied": 2, "results": [
                {"i": 0, "after": {"newDx": 8}},
                {"i": 1, "after": {"bar": 20, "removed": 0, "barlineType": "1"}},
            ]}),
        ) as apply_batch,
        bridge_call(side_effect=bridge_side_effect) as bridge,
    ):
        assert await _run_patch_layout(args) == EXIT_OK

    assert context.__aenter__.call_count == 1
    backup.assert_awaited_once()
    apply_batch.assert_awaited_once()
    assert [op["op"] for op in apply_batch.await_args.args[1]] == ["nudge", "set-barline"]
    assert [call.args[1] for call in bridge.call_args_list] == ["Save"]
    output = capsys.readouterr().out.strip()
    assert '"operations":2' in output
    assert '"verified":2' in output


async def test_patch_layout_removes_redundant_clefs_from_installed_package(cli_session: CliSession, 
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    patch_file = tmp_path / "layout.json"
    patch_file.write_text('[{"op":"remove-redundant-clefs","staff":1}]')
    args = build_parser().parse_args(["patch-layout", "--file", str(patch_file)])
    context, _client = cli_session.context, cli_session.client
    deleted: list[list[Any]] = []

    async def bridge_side_effect(
        unused_client: Any, method: str, call_args: list[Any] | None = None
    ) -> Any:
        del unused_client
        if method == "GetScoreInfo":
            return {"staffCount": 1, "barCount": 1,
                    "timeSignatures": [{"bar": 1, "numerator": 2, "denominator": 4}]}
        if method == "GetStaves":
            return [{"staffNum": 1, "instrumentName": "Bass", "barCount": 1}]
        if method == "ReadBars":
            # Initial clefs are not bar objects, so only the courtesy clef shows.
            objects = [] if deleted else [
                {"type": "Clef", "index": 3, "position": 512, "styleId": "clef.treble"}
            ]
            return [{"barNumber": 1, "objects": objects}]
        raise AssertionError(f"unexpected bridge call {method}")

    async def apply_batch(unused_client: Any, batch: list[dict[str, Any]], dry_run: bool) -> dict[str, Any]:
        del unused_client
        assert dry_run is False
        deleted.extend(batch)
        return {"applied": len(batch), "results": []}

    with (
        patch("ai_score_editing.sibelius.runner.backup", new=AsyncMock(return_value={"copy": "/scores/a.backup.sib"})),
        patch("ai_score_editing.sibelius.bridge.call", side_effect=bridge_side_effect),
        patch("ai_score_editing.sibelius.bridge.apply_batch", side_effect=apply_batch),
    ):
        assert await _run_patch_layout(args) == EXIT_OK

    # The courtesy clef sits at the end of the 2/4 bar (tick 512), guarded to a Clef.
    assert deleted == [{"op": "delete", "staff": 1, "bar": 1, "index": 3, "type": "Clef"}]
    assert '"verified":1' in capsys.readouterr().out


async def test_patch_notes_sends_one_batch_with_voice_deletes_last(cli_session: CliSession, 
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    patch_file = tmp_path / "notes.json"
    patch_file.write_text(
        '[{"op":"delete","staff":1,"bar":4,"index":1},'
        '{"op":"delete-voice","staff":2,"fromBar":1,"toBar":2,"voice":2},'
        '{"op":"delete","staff":1,"bar":4,"index":3},'
        '{"op":"tie","staff":2,"bar":5,"index":0,"remove":true}]'
    )
    args = build_parser().parse_args(["patch-notes", "--file", str(patch_file), "--save"])
    context, _client = cli_session.context, cli_session.client

    async def bridge_side_effect(
        unused_client: Any, method: str, call_args: list[Any] | None = None
    ) -> Any:
        del unused_client, call_args
        if method == "Save":
            return {"fileName": "/scores/a.sib"}
        return {"changed": True}

    batch_result = {"applied": 4, "results": [{"i": 0}, {"i": 1}, {"i": 2}, {"i": 3}]}
    with (
        patch("ai_score_editing.sibelius.runner.backup", new=AsyncMock(return_value={"copy": "/scores/a.backup.sib"})) as backup,
        bridge_apply_batch(new=AsyncMock(return_value=batch_result)) as apply_batch,
        bridge_call(side_effect=bridge_side_effect) as bridge,
    ):
        assert await _run_patch_notes(args) == EXIT_OK

    assert context.__aenter__.call_count == 1
    backup.assert_awaited_once()
    apply_batch.assert_awaited_once()
    batch, dry_run = apply_batch.await_args.args[1:]
    assert dry_run is False
    assert batch == [
        {"op": "tie", "staff": 2, "bar": 5, "index": 0, "tied": False},
        {"op": "delete", "staff": 1, "bar": 4, "index": 3},
        {"op": "delete", "staff": 1, "bar": 4, "index": 1},
        {"op": "delete-voice", "fromBar": 1, "toBar": 2, "staff": 2, "voice": 2},
    ]
    assert [call.args[1] for call in bridge.call_args_list] == ["Save"]
    assert '"applied":4' in capsys.readouterr().out.strip()


async def test_apply_dry_run_skips_backup_and_save(cli_session: CliSession, 
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    batch_file = tmp_path / "ops.json"
    batch_file.write_text('[{"op":"set","staff":1,"bar":1,"index":0,"prop":"Dx","value":8}]')
    args = build_parser().parse_args(["apply", "--file", str(batch_file), "--dry-run", "--save"])
    context, _client = cli_session.context, cli_session.client
    result = {"applied": 0, "dryRun": True, "results": [{"i": 0, "op": "set"}]}
    with (
        patch("ai_score_editing.sibelius.runner.backup", new=AsyncMock()) as backup,
        bridge_apply_batch(new=AsyncMock(return_value=result)) as apply_batch,
        bridge_call(new=AsyncMock()) as bridge,
    ):
        assert await _run_apply(args) == EXIT_OK

    backup.assert_not_awaited()
    bridge.assert_not_awaited()
    assert apply_batch.await_args.args[2] is True
    assert '"dryRun":true' in capsys.readouterr().out


async def test_apply_reports_partial_failure_with_undo_hint(cli_session: CliSession, 
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    batch_file = tmp_path / "ops.json"
    batch_file.write_text(
        '[{"op":"add-note","staff":1,"bar":1,"position":0,"duration":256,"pitches":[60]},'
        '{"op":"add-note","staff":1,"bar":1,"position":256,"duration":256,"pitches":[62]}]'
    )
    args = build_parser().parse_args(["apply", "--file", str(batch_file), "--save"])
    context, _client = cli_session.context, cli_session.client
    result = {"error": "op 1: Sibelius refused add-note", "applied": 1, "failedOp": 1}
    with (
        patch("ai_score_editing.sibelius.runner.backup", new=AsyncMock(return_value={"copy": "/b.sib"})),
        bridge_apply_batch(new=AsyncMock(side_effect=[{"applied": 0, "dryRun": True}, result]),
        ),
        bridge_call(new=AsyncMock()) as bridge,
    ):
        assert await _run_apply(args) == EXIT_COMMAND_FAILED

    bridge.assert_not_awaited()  # no save after a failed batch
    assert "invoke undo" in capsys.readouterr().err


async def test_apply_refused_batch_skips_backup(cli_session: CliSession, 
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    batch_file = tmp_path / "ops.json"
    batch_file.write_text('[{"op":"delete","staff":1,"bar":1,"index":99}]')
    args = build_parser().parse_args(["apply", "--file", str(batch_file)])
    context, _client = cli_session.context, cli_session.client
    refused = {"error": "op 0: no object at staff 1 bar 1 index 99", "applied": 0, "failedOp": 0}
    with (
        patch("ai_score_editing.sibelius.runner.backup", new=AsyncMock()) as backup,
        bridge_apply_batch(new=AsyncMock(return_value=refused)) as apply_batch,
    ):
        assert await _run_apply(args) == EXIT_COMMAND_FAILED

    backup.assert_not_awaited()
    assert [call.args[2] for call in apply_batch.await_args_list] == [True]
    assert "nothing was changed" in capsys.readouterr().err


async def test_patch_lyrics_uses_one_connection_backup_and_verification(cli_session: CliSession, 
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    patch_file = tmp_path / "patches.json"
    patch_file.write_text(
        '[{"staff":1,"bar":2,"index":0,"text":"glo-"},'
        '{"staff":1,"bar":2,"index":2,"text":"ry"}]'
    )
    args = build_parser().parse_args(
        [
            "patch-lyrics",
            "--file",
            str(patch_file),
            "--font",
            "Plantin",
            "--font-size",
            "95",
            "--save",
        ]
    )
    context, _client = cli_session.context, cli_session.client
    reads = 0
    old = [{"i": 0, "before": {"text": "old-a"}}, {"i": 1, "before": {"text": "old-b"}}]
    batch_replies = [{"applied": 0, "dryRun": True, "results": old}, {"applied": 2, "results": old}]

    async def bridge_side_effect(
        unused_client: Any, method: str, call_args: list[Any] | None = None
    ) -> Any:
        nonlocal reads
        del unused_client
        if method == "ReadLyrics":
            reads += 1
            texts = ("old-a", "old-b") if reads == 1 else ("glo-", "ry")
            return [
                {"staff": 1, "bar": 2, "index": 0, "text": texts[0]},
                {"staff": 1, "bar": 2, "index": 2, "text": texts[1]},
            ]
        if method == "Save":
            return {"fileName": "/scores/a.sib"}
        raise AssertionError(method)

    with (
        patch(
            "ai_score_editing.sibelius.runner.backup",
            new=AsyncMock(return_value={"copy": "/scores/a.backup.sib"}),
        ) as backup,
        bridge_apply_batch(new=AsyncMock(side_effect=batch_replies)) as apply_batch,
        bridge_call(side_effect=bridge_side_effect),
    ):
        assert await _run_patch_lyrics(args) == EXIT_OK

    assert context.__aenter__.call_count == 1
    backup.assert_awaited_once()
    # Checked first, then applied as one batch.
    assert [call.args[2] for call in apply_batch.await_args_list] == [True, False]
    assert [(op["index"], op["type"], op["value"]) for op in apply_batch.await_args.args[1]] == [
        (0, "LyricItem", "\\fPlantin\\\\s95\\glo-"),
        (2, "LyricItem", "\\fPlantin\\\\s95\\ry"),
    ]
    assert reads == 2
    output = capsys.readouterr().out
    assert "patched 2; verified 2/2" in output
    assert "saved /scores/a.sib" in output


async def test_tie_sends_one_batch_operation() -> None:
    parser = build_parser()
    for argv, remove in ((["tie"], False), (["tie", "--remove"], True)):
        args = parser.parse_args([*argv, "--staff", "1", "--bar", "2", "--index", "3"])
        with patch("ai_score_editing.sibelius.runner.run_op", new=AsyncMock(return_value=EXIT_OK)) as run_op:
            assert await _run_tie(args) == EXIT_OK
        assert run_op.await_args.args[1] == {"op": "tie", "staff": 1, "bar": 2, "index": 3, "remove": remove}


async def test_bracket_and_set_time_run_as_batch_ops() -> None:
    parser = build_parser()

    bracket_args = parser.parse_args(["bracket", "--staff", "1", "--bar", "8", "--index", "1"])
    with patch("ai_score_editing.sibelius.runner.run_op", new=AsyncMock(return_value=EXIT_OK)) as run_op:
        assert await _run_bracket(bracket_args) == EXIT_OK
    assert run_op.await_args.args[1] == {"op": "bracket", "staff": 1, "bar": 8, "index": 1, "remove": False}

    cut_args = parser.parse_args(["set-time", "--top", "2", "--bottom", "2", "--symbol", "cut"])
    with patch("ai_score_editing.sibelius.runner.run_op", new=AsyncMock(return_value=EXIT_OK)) as run_op:
        assert await _run_set_time(cut_args) == EXIT_OK
    assert run_op.await_args.args[1] == {
        "op": "set-time", "bar": 1, "numerator": 2, "denominator": 2, "symbol": "cut",
    }
    legacy = run_op.await_args.args[2]
    after = {"bar": 1, "numerator": 2, "denominator": 2, "barCount": 8}
    assert legacy({"after": after}) == {"bar": 1, "numerator": 2, "denominator": 2, "style": "cut"}


async def test_set_time_rejects_symbol_contradicting_meter() -> None:
    args = build_parser().parse_args(["set-time", "--top", "3", "--bottom", "4", "--symbol", "cut"])
    with patch("ai_score_editing.sibelius.runner.run_write", new=AsyncMock()) as run_write:
        assert await _run_set_time(args) == EXIT_COMMAND_FAILED
        run_write.assert_not_awaited()


async def test_add_note_pitches_reports_only_added_notes(capsys: pytest.CaptureFixture[str]) -> None:
    args = build_parser().parse_args(
        ["add-note", "--staff", "2", "--bar", "2", "--pitches", "G3", "--duration", "whole"]
    )
    after = {"notes": [{"pitch": 50, "name": "D", "tied": False}, {"pitch": 55, "name": "G", "tied": False}]}
    with patch(
        "ai_score_editing.sibelius.runner.run_op",
        new=AsyncMock(side_effect=lambda a, op, legacy: print(json.dumps(legacy({"after": after}))) or EXIT_OK),
    ) as run_op:
        assert await _run_add_notes(args) == EXIT_OK
    op = run_op.await_args.args[1]
    assert op["op"] == "add-note" and op["pitches"] == [55] and op["duration"] == 1024
    assert json.loads(capsys.readouterr().out)["notes"] == [{"pitch": 55, "name": "G", "tied": False}]


async def test_patch_layout_batches_runs_split_by_ordering_rules(cli_session: CliSession, tmp_path: Path) -> None:
    patch_file = tmp_path / "layout.json"
    patch_file.write_text(json.dumps([
        {"op": "nudge", "staff": 1, "bar": 1, "index": 0, "dx": 8},
        {"op": "nudge", "staff": 1, "bar": 1, "index": 1, "dy": -8},
        {"op": "set-barline", "bar": 2, "type": "double"},
        {"op": "nudge", "staff": 2, "bar": 3, "index": 0, "dx": 4},
    ]))
    args = build_parser().parse_args(["patch-layout", "--file", str(patch_file)])
    context, _client = cli_session.context, cli_session.client
    calls: list[str] = []

    async def apply_batch(unused_client: Any, batch: list[dict[str, Any]], dry_run: bool) -> dict[str, Any]:
        del unused_client, dry_run
        calls.append("+".join(op["op"] for op in batch))
        barline = {"bar": 2, "removed": 0, "barlineType": "3"}
        return {"applied": len(batch), "results": [
            {"i": i, "after": barline if op["op"] == "set-barline" else {}} for i, op in enumerate(batch)
        ]}

    async def bridge(unused_client: Any, method: str, call_args: list[Any] | None = None) -> Any:
        del unused_client, call_args
        calls.append(method)
        return {"ok": True}

    with (
        patch("ai_score_editing.sibelius.runner.backup", new=AsyncMock(return_value={"copy": "/b.sib"})),
        bridge_apply_batch(side_effect=apply_batch),
        bridge_call(side_effect=bridge),
    ):
        assert await _run_patch_layout(args) == EXIT_OK

    # A nudge cannot follow a structural op in the same batch, so it starts a new one.
    assert calls == ["nudge+nudge+set-barline", "nudge"]


async def _captured_op(runner: Any, argv: list[str]) -> tuple[Any, Any]:
    """Run a command with _run_op mocked; return its operation and legacy mapper."""
    args = build_parser().parse_args(argv)
    with patch("ai_score_editing.sibelius.runner.run_op", new=AsyncMock(return_value=EXIT_OK)) as run_op:
        assert await runner(args) == EXIT_OK
    return run_op.await_args.args[1], run_op.await_args.args[2]


async def test_transpose_defaults_to_whole_score_and_keeps_output() -> None:
    build, legacy = await _captured_op(
        _run_transpose, ["transpose", "--from-note", "C", "--to-note", "D", "--up", "--octaves", "1"]
    )
    with bridge_call(new=AsyncMock(return_value={"barCount": 12, "staffCount": 4})):
        operation = await build(AsyncMock())
    assert operation == {"op": "transpose", "fromBar": 1, "toBar": 12, "topStaff": 1, "bottomStaff": 4,
                         "degree": 8, "intervalType": 5}
    # The batch reports bars and interval only; the staves come from the built operation.
    after = {"fromBar": 1, "toBar": 12, "degree": 8, "intervalType": 5}
    assert legacy({"after": after}) == {**after, "topStaff": 1, "bottomStaff": 4}


async def test_range_commands_keep_their_output() -> None:
    operation, legacy = await _captured_op(
        _run_delete_voice, ["delete-voice", "--from-bar", "2", "--to-bar", "5", "--staff", "3", "--voice", "2"]
    )
    assert operation == {"op": "delete-voice", "fromBar": 2, "toBar": 5, "staff": 3, "voice": 2}
    assert legacy({"after": {"staff": 3, "voice": 2, "objects": 7}}) == {
        "fromBar": 2, "toBar": 5, "staff": 3, "deletedVoice": 2, "objects": 7,
    }

    operation, legacy = await _captured_op(_run_add_bars, ["add-bars", "--count", "3"])
    assert operation == {"op": "add-bars", "count": 3}
    assert legacy({"after": {"addedBars": 3, "barCount": 15}}) == {"addedBars": 3, "totalBars": 15}

    operation, legacy = await _captured_op(
        _run_copy_passage,
        ["copy-passage", "--from-bar", "1", "--to-bar", "2", "--top-staff", "1",
         "--dest-staff", "2", "--dest-bar", "5"],
    )
    assert operation["bottomStaff"] == 1 and operation["destPosition"] == 0
    assert legacy({"after": {}}) == {k: v for k, v in operation.items() if k != "op"}

    operation, legacy = await _captured_op(
        _run_beam, ["beam", "--staff", "1", "--bar", "3", "--from-index", "0", "--to-index", "3"]
    )
    assert operation == {"op": "beam", "staff": 1, "bar": 3, "firstIndex": 0, "lastIndex": 3}


async def test_patch_layout_rejects_an_unbatchable_value_before_backup(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    patch_file = tmp_path / "layout.json"
    patch_file.write_text('[{"op":"set-time","bar":1,"top":65,"bottom":4}]')
    args = build_parser().parse_args(["patch-layout", "--file", str(patch_file)])
    with patch("ai_score_editing.sibelius.runner.client") as client:
        assert await _run_patch_layout(args) == EXIT_COMMAND_FAILED
    client.assert_not_called()
    assert "numerator must be" in capsys.readouterr().err


async def test_run_write_save_without_path_argument(cli_session: CliSession) -> None:
    """set-staff-name has --save but no path; saving must not need args.path."""
    from ai_score_editing.sibelius.commands.score import _run_set_staff_name

    args = build_parser().parse_args(["set-staff-name", "--staff", "1", "--full", "Voice", "--save"])

    async def bridge_side_effect(unused_client: Any, method: str, call_args: list[Any] | None = None) -> Any:
        del unused_client, call_args
        if method == "Save":
            return {"fileName": "/scores/a.sib"}
        return {"staffNum": 1}

    with (
        patch("ai_score_editing.sibelius.runner.backup", new=AsyncMock(return_value={"copy": "/scores/a.backup.sib"})),
        patch("ai_score_editing.sibelius.bridge.check_bridge_version", new=AsyncMock()),
        patch("ai_score_editing.sibelius.bridge.require_bridge", new=AsyncMock()),
        bridge_call(side_effect=bridge_side_effect) as bridge,
    ):
        assert await _run_set_staff_name(args) == EXIT_OK

    assert [call.args[1] for call in bridge.call_args_list] == ["SetStaffName", "Save"]
