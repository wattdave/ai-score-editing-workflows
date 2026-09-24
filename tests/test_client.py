"""Client tests against a fake Sibelius Connect server."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
import websockets

from sibelius_websocket_cli.client import ConnectionFailed, SibeliusClient
from sibelius_websocket_cli.token_store import TokenStore

FAKE_TOKEN = "{fake-token-1234}"


class FakeSibelius:
    """Mimics Sibelius Connect: one-step handshake, silent token reconnect."""

    def __init__(self) -> None:
        self.approved_tokens: set[str] = set()
        self.token_plugins: dict[str, list[str]] = {}
        self.installed_plugins: set[str] = {"sibwscli"}
        self.connect_dialogs_shown = 0
        self.port: int = 0
        self._server: websockets.asyncio.server.Server | None = None

    async def __aenter__(self) -> "FakeSibelius":
        self._server = await websockets.serve(self._handle, "localhost", 0)
        self.port = self._server.sockets[0].getsockname()[1]
        return self

    async def __aexit__(self, *exc: object) -> None:
        assert self._server is not None
        self._server.close()
        await self._server.wait_closed()

    async def _handle(self, ws: websockets.asyncio.server.ServerConnection) -> None:
        connected = False
        session_plugins: list[str] = []
        async for raw in ws:
            msg = json.loads(raw)
            kind = msg.get("message")
            if kind == "connect":
                token = msg.get("sessionToken")
                if token in self.approved_tokens:
                    connected = True  # silent: no reply at all
                    session_plugins = self.token_plugins.get(token, [])
                else:
                    self.connect_dialogs_shown += 1
                    new_token = FAKE_TOKEN
                    self.approved_tokens.add(new_token)
                    session_plugins = msg.get("plugins", [])
                    self.token_plugins[new_token] = session_plugins
                    connected = True
                    await ws.send(json.dumps({
                        "message": "connectResponse",
                        "result": True,
                        "sessionToken": new_token,
                    }))
            elif not connected:
                await ws.close()
            elif kind == "command":
                ok = msg.get("commandName") != "Bogus.Command"
                await ws.send(json.dumps({"message": "commandResponse", "result": ok}))
            elif kind == "invokeCommands":
                await ws.send(json.dumps({"message": "invokeCommandsResponse", "result": True}))
            elif kind == "invokePlugin":
                ok = msg.get("name") in session_plugins and msg.get("name") in self.installed_plugins
                method = msg.get("method")
                ret = {"echo": msg.get("args")}
                if method == "GetBridgeVersion":
                    ret = {"version": 13}
                await ws.send(json.dumps({
                    "message": "invokePluginResponse",
                    "result": ok,
                    "return_value": ret if ok else "",
                }))
            else:
                await ws.send(json.dumps({
                    "message": "messageProcessingError",
                    "errorDetails": "unrecognized message",
                }))


@pytest.fixture
def store(tmp_path: Path) -> TokenStore:
    return TokenStore(tmp_path / "token.json")


def make_client(fake: FakeSibelius, store: TokenStore) -> SibeliusClient:
    return SibeliusClient(host="localhost", port=fake.port, token_store=store, approval_timeout=5)


async def test_fresh_connect_stores_token_and_commands_work(store: TokenStore) -> None:
    async with FakeSibelius() as fake:
        async with make_client(fake, store) as client:
            assert await client.ping() is True
            response = await client.send_command("Edit.Undo")
            assert response["result"] is True
        assert fake.connect_dialogs_shown == 1
        entry = store.load("localhost", fake.port)
        assert entry is not None and entry.token == FAKE_TOKEN


async def test_token_reconnect_skips_approval_dialog(store: TokenStore) -> None:
    async with FakeSibelius() as fake:
        async with make_client(fake, store):
            pass
        async with make_client(fake, store) as client:
            assert await client.ping() is True
        assert fake.connect_dialogs_shown == 1


async def test_stale_token_falls_back_to_approval(store: TokenStore) -> None:
    async with FakeSibelius() as fake:
        store.save("localhost", fake.port, "{stale-token}")
        async with make_client(fake, store) as client:
            assert await client.ping() is True
        assert fake.connect_dialogs_shown == 1
        entry = store.load("localhost", fake.port)
        assert entry is not None and entry.token == FAKE_TOKEN


async def test_failed_command_reports_result_false(store: TokenStore) -> None:
    async with FakeSibelius() as fake:
        async with make_client(fake, store) as client:
            response = await client.send_command("Bogus.Command")
            assert response["result"] is False


async def test_connect_refused_when_no_server(store: TokenStore) -> None:
    client = SibeliusClient(host="localhost", port=1, token_store=store)
    with pytest.raises(ConnectionFailed):
        await client.connect()


def test_token_store_roundtrip(tmp_path: Path) -> None:
    store = TokenStore(tmp_path / "token.json")
    assert store.load("localhost", 1898) is None
    store.save("localhost", 1898, "{t1}")
    store.save("otherhost", 9999, "{t2}")
    e1, e2 = store.load("localhost", 1898), store.load("otherhost", 9999)
    assert e1 is not None and e1.token == "{t1}"
    assert e2 is not None and e2.token == "{t2}"
    assert (tmp_path / "token.json").stat().st_mode & 0o777 == 0o600
    assert store.forget("localhost", 1898) is True
    assert store.load("localhost", 1898) is None
    assert store.forget("localhost", 1898) is False


async def test_send_raw_unrecognized_message(store: TokenStore) -> None:
    async with FakeSibelius() as fake:
        async with make_client(fake, store) as client:
            response = await client.send_raw({"message": "getstatus"})
            assert response["message"] == "messageProcessingError"


async def test_invoke_commands_batch(store: TokenStore) -> None:
    async with FakeSibelius() as fake:
        async with make_client(fake, store) as client:
            response = await client.invoke_commands(["a", "b"])
            assert response["result"] is True


async def test_invoke_plugin_with_declared_plugin(store: TokenStore) -> None:
    async with FakeSibelius() as fake:
        client = SibeliusClient(
            host="localhost", port=fake.port, token_store=store,
            approval_timeout=5, plugins=["sibwscli"],
        )
        async with client:
            response = await client.invoke_plugin("sibwscli", "Echo", [42])
            assert response["result"] is True
            assert response["return_value"] == {"echo": [42]}
        entry = store.load("localhost", fake.port)
        assert entry is not None and entry.plugins == ["sibwscli"]


async def test_token_without_plugin_coverage_forces_fresh_connect(store: TokenStore) -> None:
    async with FakeSibelius() as fake:
        plain = SibeliusClient(host="localhost", port=fake.port, token_store=store, approval_timeout=5)
        async with plain:
            pass
        assert fake.connect_dialogs_shown == 1
        with_plugin = SibeliusClient(
            host="localhost", port=fake.port, token_store=store,
            approval_timeout=5, plugins=["sibwscli"],
        )
        async with with_plugin:
            response = await with_plugin.invoke_plugin("sibwscli", "Echo", [])
            assert response["result"] is True
        # the cached token did not cover the plug-in, so a second dialog is expected
        assert fake.connect_dialogs_shown == 2


async def test_invoke_plugin_not_installed_reports_result_false(store: TokenStore) -> None:
    async with FakeSibelius() as fake:
        client = SibeliusClient(
            host="localhost", port=fake.port, token_store=store,
            approval_timeout=5, plugins=["missing_plugin"],
        )
        async with client:
            response = await client.invoke_plugin("missing_plugin")
            assert response["result"] is False


def test_token_store_migrates_plain_string_entries(tmp_path: Path) -> None:
    path = tmp_path / "token.json"
    path.write_text(json.dumps({"localhost:1898": "{old-style}"}))
    store = TokenStore(path)
    entry = store.load("localhost", 1898)
    assert entry is not None
    assert entry.token == "{old-style}"
    assert entry.plugins == []
    assert entry.covers([]) is True
    assert entry.covers(["sibwscli"]) is False


def test_interval_math() -> None:
    from sibelius_websocket_cli.intervals import compute_transposition

    assert compute_transposition("C", "D", up=True) == (1, 5)      # major 2nd up
    assert compute_transposition("C", "G", up=True) == (4, 5)      # perfect 5th up
    assert compute_transposition("E", "F", up=True) == (1, 4)      # minor 2nd up
    assert compute_transposition("C", "F#", up=True) == (3, 6)     # aug 4th up
    assert compute_transposition("A", "C", up=True) == (2, 4)      # minor 3rd up
    assert compute_transposition("C", "D", up=False) == (-6, 4)    # minor 7th down
    assert compute_transposition("Eb", "D", up=False) == (-1, 4)   # minor 2nd down
    assert compute_transposition("C", "C", up=True) == (0, 5)      # unison


async def test_client_launch_bypassed_if_already_running(store: TokenStore) -> None:
    from unittest.mock import patch

    async with FakeSibelius() as fake:
        with patch("sibelius_websocket_cli.launcher.is_sibelius_running", return_value=True), \
             patch("sibelius_websocket_cli.launcher.launch_sibelius") as mock_launch:
            client = SibeliusClient(
                host="localhost",
                port=fake.port,
                token_store=store,
                approval_timeout=5,
                launch_if_needed=True,
            )
            async with client:
                assert await client.ping() is True
            mock_launch.assert_not_called()


async def test_client_launches_if_not_running(store: TokenStore) -> None:
    from unittest.mock import patch

    async with FakeSibelius() as fake:
        with patch("sibelius_websocket_cli.launcher.is_sibelius_running", return_value=False), \
             patch("sibelius_websocket_cli.launcher.launch_sibelius") as mock_launch:
            client = SibeliusClient(
                host="localhost",
                port=fake.port,
                token_store=store,
                approval_timeout=5,
                launch_if_needed=True,
                launch_timeout=2.0,
            )
            async with client:
                assert await client.ping() is True
            mock_launch.assert_called_once_with(None)


async def test_client_launch_timeout_raises_connection_failed(store: TokenStore) -> None:
    from unittest.mock import patch

    with patch("sibelius_websocket_cli.launcher.is_sibelius_running", return_value=False), \
         patch("sibelius_websocket_cli.launcher.launch_sibelius"):
        client = SibeliusClient(
            host="localhost",
            port=1,
            token_store=store,
            approval_timeout=5,
            launch_if_needed=True,
            launch_timeout=0.2,
        )
        with pytest.raises(ConnectionFailed, match="Sibelius was started, but could not connect"):
            await client.connect()


async def test_client_launch_bypassed_for_remote_host(store: TokenStore) -> None:
    from unittest.mock import patch

    with patch("sibelius_websocket_cli.launcher.is_sibelius_running", return_value=False), \
         patch("sibelius_websocket_cli.launcher.launch_sibelius") as mock_launch:
        client = SibeliusClient(
            host="192.168.1.100",
            port=1,
            token_store=store,
            approval_timeout=5,
            launch_if_needed=True,
            launch_timeout=0.2,
        )
        with pytest.raises(ConnectionFailed):
            await client.connect()
        mock_launch.assert_not_called()


def test_parse_bar_range():
    from sibelius_websocket_cli.cli import parse_bar_range

    assert parse_bar_range(bars="1-4") == (1, 4)
    assert parse_bar_range(bars="3..6") == (3, 6)
    assert parse_bar_range(bars="5") == (5, 5)
    assert parse_bar_range(bar=3) == (3, 3)
    assert parse_bar_range(from_bar=2, to_bar=8) == (2, 8)
    assert parse_bar_range() == (None, None)


def test_parser_new_subcommands_and_flags():
    from sibelius_websocket_cli.cli import build_parser

    parser = build_parser()

    # save
    args = parser.parse_args(["save"])
    assert args.subcommand == "save"

    # reset-design
    args = parser.parse_args(["reset-design", "--lyrics", "--save"])
    assert args.subcommand == "reset-design"
    assert args.lyrics is True
    assert args.save is True

    # read-lyrics with --bars and --verse
    args = parser.parse_args(["read-lyrics", "--bars", "1-3", "--verse", "2", "--words", "--by-bar"])
    assert args.subcommand == "read-lyrics"
    assert args.bars == "1-3"
    assert args.verse == 2
    assert args.words is True
    assert args.by_bar is True

    # check-lyrics with --bars
    args = parser.parse_args(["check-lyrics", "--bars", "4-5"])
    assert args.subcommand == "check-lyrics"
    assert args.bars == "4-5"

    # set-lyric with --save
    args = parser.parse_args(["set-lyric", "--staff", "1", "--bar", "1", "--index", "0", "--text", "la", "--save"])
    assert args.save is True

    # flip-stem with --save
    args = parser.parse_args(["flip-stem", "--staff", "1", "--bar", "1", "--index", "0", "--save"])
    assert args.save is True

    # beam
    args = parser.parse_args(
        ["beam", "--staff", "1", "--bar", "2", "--from-index", "3", "--to-index", "5", "--save"]
    )
    assert args.from_index == 3
    assert args.to_index == 5
    assert args.save is True

    # nudge with --save
    args = parser.parse_args(["nudge", "--staff", "1", "--bar", "1", "--index", "0", "--dx", "1", "--save"])
    assert args.save is True

    # add-staff
    args = parser.parse_args(["add-staff", "--instrument", "soprano", "--position", "bottom", "--save"])
    assert args.subcommand == "add-staff"
    assert args.instrument == "soprano"
    assert args.position == "bottom"
    assert args.save is True

    # create-staff (alias)
    args = parser.parse_args(["create-staff", "--instrument", "piano", "--position", "auto"])
    assert args.subcommand == "create-staff"
    assert args.instrument == "piano"
    assert args.position == "auto"

    # add-bars
    args = parser.parse_args(["add-bars", "--count", "4", "--save"])
    assert args.subcommand == "add-bars"
    assert args.count == 4
    assert args.save is True

    # add-notes / add-note
    args = parser.parse_args(["add-notes", "--staff", "1", "--bar", "2", "--pos", "256", "--pitch", "C4,E4,G4", "--dur", "half", "--save"])
    assert args.subcommand == "add-notes"
    assert args.staff == 1
    assert args.bar == 2
    assert args.pos == 256
    assert args.pitches == "C4,E4,G4"
    assert args.duration == "half"
    assert args.save is True

    args = parser.parse_args(["add-note", "--staff", "2", "--bar", "1", "--notes", "C4:quarter D4:quarter"])
    assert args.subcommand == "add-note"
    assert args.notes == "C4:quarter D4:quarter"

    # add-abc
    args = parser.parse_args(["add-abc", "--staff", "1", "--bar", "1", "C D E F | G4", "--save"])
    assert args.subcommand == "add-abc"
    assert args.staff == 1
    assert args.bar == 1
    assert args.abc == "C D E F | G4"
    assert args.save is True

    # read with --abc
    args = parser.parse_args(["read", "--staff", "1", "--from", "1", "--to", "4", "--abc"])
    assert args.subcommand == "read"
    assert args.abc is True

    # read-abc
    args = parser.parse_args(["read-abc", "--staff", "1", "--bars", "1-4"])
    assert args.subcommand == "read-abc"
    assert args.bars == "1-4"

    # set-staff-name
    args = parser.parse_args(["set-staff-name", "--staff", "1", "--full", "Soprano", "--short", "S.", "--save"])
    assert args.subcommand == "set-staff-name"
    assert args.staff == 1
    assert args.full == "Soprano"
    assert args.short == "S."
    assert args.save is True

    # set-initial-instrument
    args = parser.parse_args(["set-initial-instrument", "--staff", "4", "--instrument", "bass", "--save"])
    assert args.subcommand == "set-initial-instrument"
    assert args.staff == 4
    assert args.instrument == "bass"
    assert args.save is True

    # duplicate-octave-down-to-voice2
    args = parser.parse_args(["duplicate-octave-down-to-voice2", "--staff", "4", "--from-bar", "1", "--to-bar", "12", "--save"])
    assert args.subcommand == "duplicate-octave-down-to-voice2"
    assert args.staff == 4
    assert args.from_bar == 1
    assert args.to_bar == 12
    assert args.save is True

    # set-score-info
    args = parser.parse_args(["set-score-info", "--title", "Hallelujah", "--composer", "William Walker", "--save"])
    assert args.subcommand == "set-score-info"
    assert args.title == "Hallelujah"
    assert args.composer == "William Walker"
    assert args.save is True

    # set-break
    args = parser.parse_args(["set-break", "--bar", "5", "--type", "system", "--save"])
    assert args.subcommand == "set-break"
    assert args.bar == 5
    assert args.type == "system"
    assert args.save is True

    # set-barline
    args = parser.parse_args(["set-barline", "--bar", "71", "--type", "double", "--save"])
    assert args.subcommand == "set-barline"
    assert args.bar == 71
    assert args.type == "double"
    assert args.save is True

    # read-barlines
    args = parser.parse_args(["read-barlines", "--bars", "70-75"])
    assert args.subcommand == "read-barlines"
    assert args.bars == "70-75"

    # set-lyric font options
    args = parser.parse_args([
        "set-lyric", "--staff", "1", "--bar", "12", "--index", "6", "--text", "When",
        "--font", "Big Caslon", "--font-size", "88", "--save",
    ])
    assert args.subcommand == "set-lyric"
    assert args.font == "Big Caslon"
    assert args.font_size == 88
    assert args.save is True

    # set-lyric-style
    args = parser.parse_args([
        "set-lyric-style", "--staff", "2", "--bar", "20", "--index", "0", "--style", "verse1", "--save",
    ])
    assert args.subcommand == "set-lyric-style"
    assert args.staff == 2
    assert args.bar == 20
    assert args.index == 0
    assert args.style == "verse1"
    assert args.save is True


async def test_run_set_lyric_adopts_predominant_font() -> None:
    from unittest.mock import AsyncMock, MagicMock, patch
    from sibelius_websocket_cli.cli import _run_set_lyric, build_parser

    parser = build_parser()
    args = parser.parse_args(["set-lyric", "--staff", "1", "--bar", "2", "--index", "0", "--text", "hermosa"])

    staff_lyrics = [
        {"staff": 1, "bar": 1, "index": 0, "text": "\\fQuicksand\\s88\\One"},
        {"staff": 1, "bar": 1, "index": 1, "text": "\\fQuicksand\\s88\\Two"},
        {"staff": 1, "bar": 2, "index": 0, "text": "ermosa"},
    ]

    mock_client_ctx = MagicMock()
    mock_client = AsyncMock()
    mock_client_ctx.__aenter__.return_value = mock_client

    with patch("sibelius_websocket_cli.cli._client", return_value=mock_client_ctx), \
         patch("sibelius_websocket_cli.cli._check_bridge_version", new=AsyncMock()), \
         patch("sibelius_websocket_cli.cli._bridge", new=AsyncMock(return_value=staff_lyrics)), \
         patch("sibelius_websocket_cli.cli._run_op", new=AsyncMock(return_value=0)) as mock_write:

        res = await _run_set_lyric(args)
        assert res == 0
        mock_write.assert_awaited_once()
        assert mock_write.await_args.args[1] == {
            "op": "set", "staff": 1, "bar": 2, "index": 0,
            "type": "LyricItem", "prop": "Text", "value": "\\fQuicksand\\\\s88\\hermosa",
        }


async def test_run_set_lyric_adopts_predominant_font_when_existing_is_outlier() -> None:
    from unittest.mock import AsyncMock, MagicMock, patch
    from sibelius_websocket_cli.cli import _run_set_lyric, build_parser

    parser = build_parser()
    args = parser.parse_args(["set-lyric", "--staff", "1", "--bar", "2", "--index", "0", "--text", "hermosa"])

    staff_lyrics = [
        {"staff": 1, "bar": 1, "index": 0, "text": "\\fQuicksand\\s88\\One"},
        {"staff": 1, "bar": 1, "index": 1, "text": "\\fQuicksand\\s88\\Two"},
        {"staff": 1, "bar": 1, "index": 2, "text": "\\fQuicksand\\s88\\Three"},
        {"staff": 1, "bar": 2, "index": 0, "text": "\\fPlantin\\s88\\ermosa"},
    ]

    mock_client_ctx = MagicMock()
    mock_client = AsyncMock()
    mock_client_ctx.__aenter__.return_value = mock_client

    with patch("sibelius_websocket_cli.cli._client", return_value=mock_client_ctx), \
         patch("sibelius_websocket_cli.cli._check_bridge_version", new=AsyncMock()), \
         patch("sibelius_websocket_cli.cli._bridge", new=AsyncMock(return_value=staff_lyrics)), \
         patch("sibelius_websocket_cli.cli._run_op", new=AsyncMock(return_value=0)) as mock_write:

        res = await _run_set_lyric(args)
        assert res == 0
        mock_write.assert_awaited_once()
        assert mock_write.await_args.args[1] == {
            "op": "set", "staff": 1, "bar": 2, "index": 0,
            "type": "LyricItem", "prop": "Text", "value": "\\fQuicksand\\\\s88\\hermosa",
        }


async def test_run_set_lyric_explicit_font_overrides_predominant() -> None:
    from unittest.mock import AsyncMock, patch
    from sibelius_websocket_cli.cli import _run_set_lyric, build_parser

    parser = build_parser()
    args = parser.parse_args([
        "set-lyric", "--staff", "1", "--bar", "2", "--index", "0", "--text", "hermosa",
        "--font", "Garamond", "--font-size", "96",
    ])

    with patch("sibelius_websocket_cli.cli._run_op", new=AsyncMock(return_value=0)) as mock_write:
        res = await _run_set_lyric(args)
        assert res == 0
        mock_write.assert_awaited_once()
        assert mock_write.await_args.args[1] == {
            "op": "set", "staff": 1, "bar": 2, "index": 0,
            "type": "LyricItem", "prop": "Text", "value": "\\fGaramond\\\\s96\\hermosa",
        }


async def test_run_set_lyric_adopts_score_default_font_and_size_when_unstyled() -> None:
    from unittest.mock import AsyncMock, MagicMock, patch
    from sibelius_websocket_cli.cli import _run_set_lyric, build_parser

    parser = build_parser()
    args = parser.parse_args(["set-lyric", "--staff", "1", "--bar", "2", "--index", "0", "--text", "hermosa"])

    score_info = {"mainTextFontName": "Times New Roman"}
    staff_lyrics = [
        {"staff": 1, "bar": 1, "index": 0, "text": "One"},
        {"staff": 1, "bar": 1, "index": 1, "text": "Two"},
        {"staff": 1, "bar": 2, "index": 0, "text": "ermosa"},
    ]

    mock_client_ctx = MagicMock()
    mock_client = AsyncMock()
    mock_client_ctx.__aenter__.return_value = mock_client

    async def bridge_side_effect(client: Any, method: str, args: list[Any] | None = None) -> Any:
        if method == "GetScoreInfo":
            return score_info
        if method == "ReadLyrics":
            return staff_lyrics
        return None

    with patch("sibelius_websocket_cli.cli._client", return_value=mock_client_ctx), \
         patch("sibelius_websocket_cli.cli._check_bridge_version", new=AsyncMock()), \
         patch("sibelius_websocket_cli.cli._bridge", side_effect=bridge_side_effect), \
         patch("sibelius_websocket_cli.cli._run_op", new=AsyncMock(return_value=0)) as mock_write:

        res = await _run_set_lyric(args)
        assert res == 0
        # When unstyled, adopts score default font (Times New Roman) and standard 11pt size (110 tenths of a pt)
        mock_write.assert_awaited_once()
        assert mock_write.await_args.args[1] == {
            "op": "set", "staff": 1, "bar": 2, "index": 0,
            "type": "LyricItem", "prop": "Text", "value": "\\fTimes New Roman\\\\s110\\hermosa",
        }


async def test_run_set_barline() -> None:
    from unittest.mock import AsyncMock, patch
    from sibelius_websocket_cli.cli import _run_set_barline, build_parser

    parser = build_parser()
    args = parser.parse_args(["set-barline", "--bar", "71", "--type", "double"])

    with patch("sibelius_websocket_cli.cli._run_op", new=AsyncMock(return_value=0)) as run_op:
        res = await _run_set_barline(args)
        assert res == 0
    assert run_op.await_args.args[1] == {"op": "set-barline", "bar": 71, "type": "double"}
    legacy = run_op.await_args.args[2]
    assert legacy({"after": {"bar": 71, "removed": 1, "barlineType": "-1"}}) == {
        "bar": 71, "deleted": 1, "barlineType": "7",
    }


async def test_run_read_barlines() -> None:
    from unittest.mock import AsyncMock, patch
    from sibelius_websocket_cli.cli import _run_read_barlines, build_parser

    parser = build_parser()
    args = parser.parse_args(["read-barlines", "--bars", "70-75"])

    with patch("sibelius_websocket_cli.cli._run_bridge_call", new=AsyncMock(return_value=0)) as mock_call:
        res = await _run_read_barlines(args)
        assert res == 0
        mock_call.assert_called_once_with(args, "GetSpecialBarlines", [70, 75])

