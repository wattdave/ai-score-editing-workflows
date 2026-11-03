"""play-order and play-on-pass: parsing, CLI wiring and the bridge plug-in source."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from fakes import bridge_call

from ai_score_editing.sibelius import bridge, repeats
from ai_score_editing.sibelius.cli import build_parser
from ai_score_editing.sibelius.commands import layout
from ai_score_editing.sibelius.commands._common import EXIT_COMMAND_FAILED, EXIT_OK

PLUGIN = Path(bridge.__file__).parent / "manuscript" / "ScoreBridge.plg"


def test_parse_bar_order_expands_ranges_in_playback_order() -> None:
    assert repeats.parse_bar_order("1-3, 1-3, 5") == [1, 2, 3, 1, 2, 3, 5]
    assert repeats.parse_bar_order("1–2,1–2") == [1, 2, 1, 2]  # en dashes, as the dialog prints
    assert repeats.parse_bar_order("4") == [4]


@pytest.mark.parametrize("text", ["", "a-b", "3-1", "0-2", "1-", "1,,x"])
def test_parse_bar_order_rejects_bad_text(text: str) -> None:
    with pytest.raises(ValueError):
        repeats.parse_bar_order(text)


def test_parse_bar_order_checks_the_score_length() -> None:
    with pytest.raises(ValueError, match="bar 9 is outside"):
        repeats.parse_bar_order("1-9", bar_count=8)


def test_parse_passes() -> None:
    assert repeats.parse_passes("1-3") == [1, 2, 3]
    assert repeats.parse_passes("3, 1") == [1, 3]
    assert repeats.parse_passes("none") == []
    for bad in ("0", "9", "1-9", "x"):
        with pytest.raises(ValueError):
            repeats.parse_passes(bad)


def test_plugin_defines_the_bridge_methods_and_matches_the_cli_version() -> None:
    source = PLUGIN.read_text()
    for method in ("GetPlayOrder", "SetPlayOrder", "SetPlayOrderText", "GetPlayOnPass", "SetPlayOnPass"):
        assert re.search(rf"^\t{method} \"\(", source, re.M), method
    version = re.search(r"GetBridgeVersion .*?'version', (\d+)", source, re.S)
    assert version and int(version.group(1)) == bridge.CURRENT_BRIDGE_VERSION >= bridge.REPEATS_BRIDGE_VERSION
    assert "BarPlaybackOrder" in source and "SetPlayedOnNthPass" in source


pytestmark = pytest.mark.usefixtures("cli_session")  # patches runner.client and the guards


async def _run(runner: Any, argv: list[str], bridge: AsyncMock) -> tuple[int, AsyncMock]:
    backup = AsyncMock(return_value={"copy": "/tmp/x.backup.sib"})
    with (
        patch("ai_score_editing.sibelius.runner.backup", new=backup),
        bridge_call(new=bridge),
    ):
        code = await runner(build_parser().parse_args(argv))
    return code, backup


async def test_play_order_sets_the_roadmap_after_a_backup() -> None:
    calls: list[tuple[str, Any]] = []

    async def bridge(client: Any, method: str, call_args: Any = None) -> Any:
        calls.append((method, call_args))
        return {"manual": True, "order": "1-2, 1-2", "barCount": 8}

    code, backup = await _run(layout._run_play_order, ["play-order", "1-2, 1-2"], AsyncMock(side_effect=bridge))
    assert code == EXIT_OK
    backup.assert_awaited_once()
    assert calls[-1] == ("SetPlayOrder", [[1, 2, 1, 2]])


def test_format_bar_order_round_trips() -> None:
    assert repeats.format_bar_order([1, 2, 3, 1, 2, 3, 5]) == "1-3, 1-3, 5"
    assert repeats.parse_bar_order(repeats.format_bar_order([4, 3, 2, 2])) == [4, 3, 2, 2]


async def test_play_order_falls_back_to_the_text_form_when_the_array_does_not_take() -> None:
    calls: list[str] = []

    async def bridge(client: Any, method: str, call_args: Any = None) -> Any:
        calls.append(method)
        if method == "SetPlayOrderText":
            assert call_args == ["1-2, 1-2"]
            return {"manual": True, "order": "1–2, 1–2", "barCount": 8}
        return {"manual": True, "order": "1-8", "barCount": 8}

    code, _ = await _run(layout._run_play_order, ["play-order", "1-2, 1-2"], AsyncMock(side_effect=bridge))
    assert code == EXIT_OK
    assert calls == ["GetPlayOrder", "SetPlayOrder", "SetPlayOrderText"]


async def test_play_order_auto_clears_the_manual_roadmap() -> None:
    calls: list[tuple[str, Any]] = []

    async def bridge(client: Any, method: str, call_args: Any = None) -> Any:
        calls.append((method, call_args))
        return {"manual": False, "order": "1-8", "barCount": 8}

    code, _ = await _run(layout._run_play_order, ["play-order", "auto"], AsyncMock(side_effect=bridge))
    assert code == EXIT_OK
    assert calls[-1] == ("SetPlayOrder", [None])


async def test_play_order_refuses_bars_past_the_end_before_backing_up(capsys: pytest.CaptureFixture[str]) -> None:
    bridge = AsyncMock(return_value={"manual": False, "order": "1-4", "barCount": 4})
    code, backup = await _run(layout._run_play_order, ["play-order", "1-6"], bridge)
    assert code == EXIT_COMMAND_FAILED
    backup.assert_not_awaited()
    assert "bar 5 is outside the score" in capsys.readouterr().err


async def test_play_order_without_an_order_only_reads() -> None:
    bridge = AsyncMock(return_value={"manual": False, "order": "1-4", "barCount": 4})
    code, backup = await _run(layout._run_play_order, ["play-order"], bridge)
    assert code == EXIT_OK
    backup.assert_not_awaited()
    bridge.assert_awaited_once()
    assert bridge.await_args.args[1] == "GetPlayOrder"


async def test_play_on_pass_sets_the_listed_passes() -> None:
    bridge = AsyncMock(return_value={"bar": 12, "barlines": []})
    code, backup = await _run(
        layout._run_play_on_pass, ["play-on-pass", "--bar", "12", "--passes", "1-3"], bridge
    )
    assert code == EXIT_OK
    backup.assert_awaited_once()
    assert bridge.await_args.args[1:] == ("SetPlayOnPass", [12, "end_repeat", [1, 2, 3], None])


async def test_play_on_pass_all_and_type() -> None:
    bridge = AsyncMock(return_value={})
    await _run(
        layout._run_play_on_pass,
        ["play-on-pass", "--bar", "2", "--passes", "all", "--type", "start_repeat", "--position", "0"],
        bridge,
    )
    assert bridge.await_args.args[1:] == ("SetPlayOnPass", [2, "start_repeat", list(range(1, 9)), 0])


async def test_play_on_pass_rejects_a_bad_pass_before_connecting(capsys: pytest.CaptureFixture[str]) -> None:
    bridge = AsyncMock()
    code, backup = await _run(
        layout._run_play_on_pass, ["play-on-pass", "--bar", "2", "--passes", "9"], bridge
    )
    assert code == EXIT_COMMAND_FAILED
    backup.assert_not_awaited()
    bridge.assert_not_awaited()
    assert "passes run from 1 to 8" in capsys.readouterr().err


async def test_play_on_pass_without_passes_reads_the_bar() -> None:
    with patch("ai_score_editing.sibelius.commands.layout._run_bridge_call", new=AsyncMock(return_value=0)) as call:
        args = build_parser().parse_args(["play-on-pass", "--bar", "12"])
        assert await layout._run_play_on_pass(args) == 0
    call.assert_awaited_once_with(args, "GetPlayOnPass", [12])
