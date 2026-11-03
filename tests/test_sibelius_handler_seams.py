"""Handlers reach the bridge through the real modules, so patches there take effect."""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from fakes import bridge_call

from ai_score_editing.sibelius import bridge, runner
from ai_score_editing.sibelius.commands import audio, layout, lyrics


@pytest.fixture
def seen(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    @asynccontextmanager
    async def fake_client(args: Any, plugins: Any = None) -> Any:
        yield object()

    monkeypatch.setattr(runner, "client", lambda args, plugins=None: fake_client(args, plugins))
    monkeypatch.setattr(bridge, "require_bridge", AsyncMock())
    with bridge_call(return_value=[]) as mock:
        yield mock


async def test_lyrics_handler_sees_bridge_patch(seen: AsyncMock) -> None:
    args = SimpleNamespace(staff=0, from_bar=None, to_bar=None, bar=None, bars=None, verse=None,
                           words=False, compact=False, by_bar=False, json=True)
    assert await lyrics._run_read_lyrics(args) == 0
    assert seen.await_args.args[1] == "ReadLyrics"


async def test_audio_handler_sees_bridge_patch(seen: AsyncMock) -> None:
    args = SimpleNamespace(require=None)
    assert await audio._run_playback_sounds(args) == 0
    assert seen.await_args.args[1] == "GetPlaybackSounds"


async def test_layout_handler_sees_bridge_patch(seen: AsyncMock) -> None:
    args = SimpleNamespace(order=None)
    assert await layout._run_play_order(args) == 0
    assert seen.await_args.args[1] == "GetPlayOrder"
