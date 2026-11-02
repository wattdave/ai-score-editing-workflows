"""The shared ``commands._common.cli`` proxy sees patches on ``sibelius.cli``."""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from ai_score_editing.sibelius import cli
from ai_score_editing.sibelius.commands import _common, audio, layout, lyrics


@pytest.fixture
def seen(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    @asynccontextmanager
    async def fake_client(args: Any, plugins: Any = None) -> Any:
        yield object()

    bridge = AsyncMock(return_value=[])
    monkeypatch.setattr(cli, "_client", lambda args, plugins=None: fake_client(args, plugins))
    monkeypatch.setattr(cli, "_bridge", bridge)
    monkeypatch.setattr(cli, "_require_bridge", AsyncMock())
    return bridge


def test_proxy_resolves_attributes_at_call_time(monkeypatch: pytest.MonkeyPatch) -> None:
    sentinel = object()
    monkeypatch.setattr(cli, "_bridge", sentinel)
    assert _common.cli._bridge is sentinel


async def test_lyrics_handler_sees_cli_bridge_patch(seen: AsyncMock) -> None:
    args = SimpleNamespace(staff=0, from_bar=None, to_bar=None, bar=None, bars=None, verse=None,
                           words=False, compact=False, by_bar=False, json=True)
    assert await lyrics._run_read_lyrics(args) == 0
    assert seen.await_args.args[1] == "ReadLyrics"


async def test_audio_handler_sees_cli_bridge_patch(seen: AsyncMock) -> None:
    args = SimpleNamespace(require=None)
    assert await audio._run_playback_sounds(args) == 0
    assert seen.await_args.args[1] == "GetPlaybackSounds"


async def test_layout_handler_sees_cli_bridge_patch(seen: AsyncMock) -> None:
    args = SimpleNamespace(order=None)
    assert await layout._run_play_order(args) == 0
    assert seen.await_args.args[1] == "GetPlayOrder"
