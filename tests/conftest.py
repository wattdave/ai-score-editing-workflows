"""Keep the test suite away from a real Sibelius or Dorico.

A test that forgets to mock a bridge call would otherwise connect to the
Sibelius on this machine (launching it if needed, since that happens inside
connect) and edit, back up and save whatever score is open.
"""

import pytest

from sibelius_websocket_cli import protocol
from sibelius_websocket_cli.client import SibeliusClient
from sibelius_websocket_cli.dorico import client as dorico_client

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


@pytest.fixture(autouse=True)
def _no_real_sibelius(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(SibeliusClient, "connect", _guarded_connect)
    monkeypatch.setattr(dorico_client.DoricoClient, "connect", _guarded_dorico_connect)
