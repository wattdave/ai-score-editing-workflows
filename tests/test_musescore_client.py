"""MuseScore client: plug-in install, version checks, token and error handling."""

import json
import stat
import pytest

from ai_score_editing.musescore import install
from ai_score_editing.musescore.bridge import MuseScoreBridge, version_text
from ai_score_editing.musescore.client import MuseScoreClient, MuseScoreError

from musescore_common import ScoreBridge, TOKEN, config, fake  # noqa: F401,F811


def test_install_writes_plugin_with_token_and_keeps_it(config) -> None:
    path = install.install()
    text = path.read_text()
    token = install.read_token()
    assert token and f'"{token}"' in text
    assert not any(f"@{k}@" in text for k in ("TOKEN", "PORT", "VERSION"))
    assert f"port: {install.DEFAULT_PORT}" in text and f"bridgeVersion: {install.BRIDGE_VERSION}" in text
    assert stat.S_IMODE(install.token_path().stat().st_mode) == 0o600
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    install.install()
    assert install.read_token() == token  # reinstalling keeps the running plug-in's token


def test_plugin_properties_come_before_any_block(config) -> None:
    # MuseScore reads title: etc. as text and stops at the first line ending in "{".
    lines = [line.strip() for line in install.render("t").splitlines()]
    start = lines.index("MuseScore {")
    first_block = next(i for i in range(start + 1, len(lines)) if lines[i].endswith("{"))
    assert f'title: "{install.PLUGIN_TITLE}"' in lines[start:first_block]
    # A function named run clashes with the plug-in's run signal and breaks the file.
    assert "function run(" not in install.render("t")


def test_plugin_undo_uses_the_action_name() -> None:
    text = install.TEMPLATE.read_text()
    assert 'cmd("action://notation/undo")' in text and 'cmd("undo")' not in text


async def test_overview_checks_versions(fake) -> None:
    async with MuseScoreClient(port=fake.port, token=TOKEN) as client:
        result = await MuseScoreBridge(client).overview()
    assert result["bridge"] == install.BRIDGE_VERSION and result["mscore"] == "4.7.5"
    assert result["score"]["name"] == "Scratch" and result["staves"][0]["partName"] == "Clarinet in B♭"
    assert result["warnings"] == []
    assert client.last["score"]["staves"] == 3


async def test_old_bridge_and_old_musescore_are_refused(fake) -> None:
    fake.bridge = install.BRIDGE_VERSION - 1
    async with MuseScoreClient(port=fake.port, token=TOKEN) as client:
        with pytest.raises(MuseScoreError, match="install-plugin"):
            await MuseScoreBridge(client).overview()
    fake.bridge, fake.mscore = install.BRIDGE_VERSION, 40502
    async with MuseScoreClient(port=fake.port, token=TOKEN) as client:
        with pytest.raises(MuseScoreError, match="4.5.2 is too old"):
            await MuseScoreBridge(client).overview()


async def test_newer_musescore_warns(fake) -> None:
    fake.mscore = 40800
    async with MuseScoreClient(port=fake.port, token=TOKEN) as client:
        result = await MuseScoreBridge(client).check()
    assert "4.8.0" in result["warnings"][0]


async def test_wrong_token_and_errors(fake) -> None:
    async with MuseScoreClient(port=fake.port, token="wrong") as client:
        with pytest.raises(MuseScoreError, match="refused the token"):
            await client.call("GetBridgeVersion")
    async with MuseScoreClient(port=fake.port, token=TOKEN) as client:
        with pytest.raises(MuseScoreError, match="NoSuchMethod"):
            await client.call("NoSuchMethod")


async def test_undo_sends_steps_and_checks_range(fake) -> None:
    async with MuseScoreClient(port=fake.port, token=TOKEN) as client:
        bridge = MuseScoreBridge(client)
        assert await bridge.undo(3) == {"undone": 3}
        with pytest.raises(MuseScoreError, match="1-20"):
            await bridge.undo(0)
    assert fake.requests[-1]["args"] == {"steps": 3}


async def test_bridge_not_running_says_how_to_start_it(config) -> None:
    client = MuseScoreClient(port=1, token=TOKEN)
    with pytest.raises(MuseScoreError, match="Plugins > ScoreBridge"):
        await client.connect()


async def test_missing_token_says_to_install(config) -> None:
    with pytest.raises(MuseScoreError, match="install-plugin"):
        await MuseScoreClient(port=1).connect()


async def test_real_port_is_guarded() -> None:
    with pytest.raises(RuntimeError, match="fake bridge"):
        await MuseScoreClient(token=TOKEN).connect()


def test_version_text() -> None:
    assert version_text(40705) == "4.7.5"


def test_unauthorised_reply_carries_no_versions() -> None:
    text = install.TEMPLATE.read_text()
    start = text.index('request.token !== root.token')
    branch = text[start:text.index("} else {", start)]
    assert "unauthorised" in branch and "bridgeVersion" not in branch and "mscoreVersion" not in branch


async def test_late_reply_from_a_timed_out_call_is_dropped(fake) -> None:
    import asyncio
    release = asyncio.Event()
    state = {"slow": True}

    async def serve(ws):
        async for message in ws:
            request = json.loads(message)
            if state["slow"]:
                state["slow"] = False
                await release.wait()  # answer the first call only after its timeout
                await ws.send(json.dumps({"id": request["id"], "ok": True, "result": "late"}))
            else:
                await ws.send(json.dumps({"id": request["id"], "ok": True, "result": "fresh"}))

    import websockets
    async with websockets.serve(serve, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        async with MuseScoreClient(port=port, token=TOKEN, timeout=0.2) as client:
            with pytest.raises(MuseScoreError, match="did not answer"):
                await client.call("Slow")
            release.set()
            await asyncio.sleep(0.1)  # the late reply is now waiting on the socket
            assert await client.call("Next") == "fresh"
