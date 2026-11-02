"""Keep the test suite away from a real Sibelius, Dorico or MuseScore.

A test that forgets to mock a bridge call would otherwise connect to the
Sibelius on this machine (launching it if needed, since that happens inside
connect) and edit, back up and save whatever score is open.
"""

import pytest

from ai_score_editing.sibelius import protocol
from ai_score_editing.sibelius.client import SibeliusClient
from ai_score_editing.dorico import client as dorico_client
from ai_score_editing.musescore import client as musescore_client
from ai_score_editing.musescore import install as musescore_install

_real_connect = SibeliusClient.connect


async def _guarded_connect(self: SibeliusClient) -> None:
    if self.port == protocol.DEFAULT_PORT:
        raise RuntimeError(
            f"a test tried to connect to Sibelius Connect on port {self.port}; mock the bridge call instead"
        )
    await _real_connect(self)


_real_dorico_connect = dorico_client.DoricoClient.connect


async def _guarded_dorico_connect(self: dorico_client.DoricoClient) -> None:
    if self.port == dorico_client.DEFAULT_PORT:
        raise RuntimeError(
            f"a test tried to connect to Dorico on port {self.port}; mock the bridge call instead"
        )
    await _real_dorico_connect(self)


_real_musescore_connect = musescore_client.MuseScoreClient.connect


async def _guarded_musescore_connect(self: musescore_client.MuseScoreClient) -> None:
    if self.port == musescore_install.DEFAULT_PORT:
        raise RuntimeError(
            f"a test tried to connect to the MuseScore bridge on port {self.port}; use a fake bridge instead"
        )
    await _real_musescore_connect(self)


@pytest.fixture(autouse=True)
def _no_real_sibelius(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(SibeliusClient, "connect", _guarded_connect)
    monkeypatch.setattr(dorico_client.DoricoClient, "connect", _guarded_dorico_connect)
    monkeypatch.setattr(musescore_client.MuseScoreClient, "connect", _guarded_musescore_connect)


@pytest.fixture(autouse=True)
def _isolated_home(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """Point HOME and the XDG folders at tmp_path so no test touches the real
    config, token or cache folders. Tests that need other locations set their
    own values with monkeypatch afterwards."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg-config"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg-cache"))
