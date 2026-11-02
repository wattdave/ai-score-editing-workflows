"""Tests for the Sibelius client->bridge layer."""

from __future__ import annotations

from typing import Any

import pytest

from ai_score_editing.sibelius import bridge


class FakeClient:
    def __init__(self, version: int = 62, busy: bool = False) -> None:
        self.version = version
        self.busy = busy
        self.calls: list[str] = []

    async def invoke_plugin(self, plugin: str, method: str, args: list[Any] | None = None) -> dict[str, Any]:
        self.calls.append(method)
        if self.busy:
            return {"message": "busyError"}
        if method == "GetBridgeVersion":
            return {"result": True, "returnValue": {"version": self.version}}
        return {"result": True, "returnValue": {"ok": method}}


async def test_version_read_once_per_client_across_requires() -> None:
    client = FakeClient()
    await bridge.require_bridge(client, 10, "a")
    await bridge.require_bridge(client, 20, "b")
    await bridge.check_bridge_version(client)
    assert client.calls.count("GetBridgeVersion") == 1
    other = FakeClient()
    await bridge.require_bridge(other, 10, "a")
    assert other.calls.count("GetBridgeVersion") == 1


async def test_require_refuses_old_bridge() -> None:
    client = FakeClient(version=40)
    with pytest.raises(bridge.BridgeError, match="needs bridge v50"):
        await bridge.require_bridge(client, 50, "feature")


async def test_busy_response_raises_bridge_busy() -> None:
    client = FakeClient(busy=True)
    with pytest.raises(bridge.BridgeBusy) as caught:
        await bridge.call(client, "GetScoreInfo")
    assert isinstance(caught.value, bridge.BridgeError)
    assert caught.value.payload == bridge.BUSY_MESSAGE
    with pytest.raises(bridge.BridgeBusy):
        await bridge.apply_batch(client, [], True)


@pytest.mark.parametrize(
    ("operations", "expected"),
    [
        ([{"op": "set-pitch"}], bridge.BATCH_BRIDGE_VERSION),
        ([{"op": "nudge"}], bridge.NUDGE_BRIDGE_VERSION),
        ([{"op": "delete-bars"}], bridge.DELETE_BARS_BRIDGE_VERSION),
        ([{"op": "hide-empty-staves"}], bridge.HIDE_EMPTY_STAVES_BRIDGE_VERSION),
        ([{"op": "set-layout"}], bridge.LAYOUT_BATCH_BRIDGE_VERSION),
        ([{"op": "set-lyric-verse"}], bridge.SET_LYRIC_VERSE_BRIDGE_VERSION),
        ([{"op": "add-lyric", "verse": 2}], bridge.LYRIC_VERSE_BRIDGE_VERSION),
        ([{"op": "clear-bars"}], bridge.TUPLET_NOTES_BRIDGE_VERSION),
        ([{"op": "nudge"}, {"op": "clear-bars"}], bridge.TUPLET_NOTES_BRIDGE_VERSION),
    ],
)
def test_batch_bridge_version_table(operations: list[dict[str, Any]], expected: int) -> None:
    assert bridge.batch_bridge_version(operations) == expected
