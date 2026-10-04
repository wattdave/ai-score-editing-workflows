"""MuseScore back end: plug-in install, client protocol and version checks.

A fake bridge stands in for the plug-in on a free port; conftest.py fails any
connection to the real bridge's port.
"""

import json
import stat

import pytest
import websockets

from sibelius_websocket_cli.musescore import cli, install
from sibelius_websocket_cli.musescore.bridge import MuseScoreBridge, version_text
from sibelius_websocket_cli.musescore.client import MuseScoreClient, MuseScoreError

TOKEN = "test-token"


@pytest.fixture
def config(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("MUSESCORE_PLUGIN_DIR", str(tmp_path / "plugins"))
    return tmp_path


class FakeBridge:
    """Answers like msbridge.qml: same envelope, a handful of methods."""

    def __init__(self, mscore=40705, bridge=install.BRIDGE_VERSION, handler=None):
        self.mscore, self.bridge, self.handler = mscore, bridge, handler
        self.requests = []

    async def serve(self, ws):
        async for message in ws:
            request = json.loads(message)
            self.requests.append(request)
            reply = {"id": request["id"], "bridge": self.bridge, "mscoreVersion": self.mscore}
            if request.get("token") != TOKEN:
                reply.update(ok=False, error="unauthorised")
            else:
                try:
                    reply.update(ok=True, result=self.answer(request["method"], request["args"]))
                except KeyError as exc:
                    reply.update(ok=False, error=str(exc))
                reply["score"] = {"name": "Scratch", "measures": 8, "staves": 3, "parts": 2}
            await ws.send(json.dumps(reply))

    def answer(self, method, args):
        if self.handler:
            return self.handler(method, args)
        return {
            "GetBridgeVersion": {"version": self.bridge},
            "GetScoreInfo": {"name": "Scratch", "measures": 8, "staves": 3},
            "GetStaves": [{"staff": 1, "partName": "Clarinet in B♭"}],
            "Undo": {"undone": args.get("steps", 1)},
        }[method]


@pytest.fixture
async def fake():
    bridge = FakeBridge()
    async with websockets.serve(bridge.serve, "127.0.0.1", 0) as server:
        bridge.port = server.sockets[0].getsockname()[1]
        yield bridge


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
    with pytest.raises(MuseScoreError, match="Plugins > sibwscli bridge"):
        await client.connect()


async def test_missing_token_says_to_install(config) -> None:
    with pytest.raises(MuseScoreError, match="install-plugin"):
        await MuseScoreClient(port=1).connect()


async def test_real_port_is_guarded() -> None:
    with pytest.raises(RuntimeError, match="fake bridge"):
        await MuseScoreClient(token=TOKEN).connect()


def test_version_text() -> None:
    assert version_text(40705) == "4.7.5"


def test_cli_install_plugin(config, capsys) -> None:
    assert cli.main(["install-plugin"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["installed"].endswith("sibwscli-bridge/msbridge.qml")
