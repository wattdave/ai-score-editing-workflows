"""Old spellings keep working: Dorico player=, format="mid", exit codes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from ai_score_editing import cli_common
from ai_score_editing.dorico import cli as dorico_cli
from ai_score_editing.dorico import lyrics_dialog
from ai_score_editing.dorico import mcp_server as dorico_mcp
from ai_score_editing.dorico import service as dorico_service
from ai_score_editing.dorico.client import DoricoConnectionError, DoricoError
from ai_score_editing.musescore import cli as musescore_cli
from ai_score_editing.musescore import service as musescore_service
from ai_score_editing.musescore.client import MuseScoreConnectionError, MuseScoreError
from ai_score_editing.sibelius import bridge as sibelius_bridge
from ai_score_editing.sibelius import service as sibelius_service


class FakeSession:
    async def run(self, action: Any, *, retry: bool) -> Any:
        return await action(object())


async def test_dorico_player_alias_and_staff_name(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[str, int]] = []

    async def read(b: Any, player: str, verse: int = 1) -> dict[str, Any]:
        seen.append((player, verse))
        return {}

    monkeypatch.setattr(lyrics_dialog, "read_lyrics", read)
    monkeypatch.setattr(dorico_mcp, "session", FakeSession())
    await dorico_mcp.read_lyrics(player="Soprano")
    await dorico_mcp.read_lyrics(staff="Alto", verse=2)
    assert seen == [("Soprano", 1), ("Alto", 2)]
    for kwargs in ({}, {"staff": "1", "player": "Soprano"}):
        with pytest.raises(DoricoError, match="exactly one"):
            await dorico_mcp.read_lyrics(**kwargs)


async def test_dorico_staff_number_maps_to_its_player(monkeypatch: pytest.MonkeyPatch) -> None:
    class Snap:
        staves = [{"staff": 1, "name": "Soprano"}, {"staff": 2, "name": "Piano"}, {"staff": 3, "name": "Piano"}]

    async def snapshot(bridge: Any, flow: int = 1) -> Snap:
        return Snap()

    class Client:
        async def layouts(self) -> list[dict[str, Any]]:
            return [{"layoutName": "Piano", "layoutType": "kPartLayout"}, {"layoutName": "Full score", "layoutType": "kFullScoreLayout"}]

    class Bridge:
        client = Client()

    monkeypatch.setattr(dorico_service, "snapshot", snapshot)
    assert await dorico_service.resolve_player(Bridge(), "2") == "Piano"  # type: ignore[arg-type]
    with pytest.raises(DoricoError, match="no staff 9"):
        await dorico_service.resolve_player(Bridge(), "9")  # type: ignore[arg-type]
    # Soprano is a staff but not a part layout: say so and name what works.
    with pytest.raises(DoricoError, match=r"not a part layout.*Piano \(staves 2, 3\)"):
        await dorico_service.resolve_player(Bridge(), "1")  # type: ignore[arg-type]


async def test_mid_is_accepted_as_midi(tmp_path: Path) -> None:
    assert cli_common.canonical_format("mid") == "midi"
    assert sibelius_bridge.EXPORT_FORMATS["midi"][1] == ".mid"
    assert "midi" in musescore_service.EXPORT_FORMATS

    class Bridge:
        async def write_copy(self, path: str, ext: str, timeout: int = 0) -> dict[str, Any]:
            Path(path).write_bytes(b"x")
            return {"written": True}

    result = await musescore_service.export(Bridge(), "mid", str(tmp_path / "a.mid"))  # type: ignore[arg-type]
    assert result["files"] == [str(tmp_path / "a.mid")]
    with pytest.raises(DoricoError, match="format must be"):
        await dorico_service.export(object(), "mid", str(tmp_path / "a.mid"))  # type: ignore[arg-type]


async def test_dorico_export_without_path_asks_for_one() -> None:
    with pytest.raises(DoricoError, match="pass path"):
        await dorico_service.export(object(), "pdf")  # type: ignore[arg-type]


async def test_sibelius_save_with_path_is_refused() -> None:
    with pytest.raises(sibelius_bridge.BridgeError, match="cannot save a copy"):
        await sibelius_service.save(object(), "/tmp/x.sib")  # type: ignore[arg-type]


def test_connection_errors_exit_2(monkeypatch: pytest.MonkeyPatch) -> None:
    async def dorico_run(args: Any) -> Any:
        raise DoricoConnectionError("no dorico")

    async def musescore_run(args: Any) -> Any:
        raise MuseScoreConnectionError("no musescore")

    monkeypatch.setattr(dorico_cli, "run", dorico_run)
    monkeypatch.setattr(musescore_cli, "run", musescore_run)
    assert dorico_cli.main(["overview"]) == cli_common.EXIT_CONNECTION_FAILED == 2
    assert musescore_cli.main(["overview"]) == 2

    async def failing(args: Any) -> Any:
        raise MuseScoreError("bad")

    monkeypatch.setattr(musescore_cli, "run", failing)
    assert musescore_cli.main(["overview"]) == cli_common.EXIT_COMMAND_FAILED
    assert issubclass(DoricoConnectionError, DoricoError)
