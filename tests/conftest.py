"""Keep the test suite away from a real Sibelius.

A test that forgets to mock a bridge call would otherwise connect to the
Sibelius on this machine (launching it if needed, since that happens inside
connect) and edit, back up and save whatever score is open.
"""

import pytest

from sibelius_websocket_cli import protocol
from sibelius_websocket_cli.client import SibeliusClient

_real_connect = SibeliusClient.connect


async def _guarded_connect(self: SibeliusClient) -> None:
    if self.port == protocol.DEFAULT_PORT:
        raise RuntimeError(
            f"a test tried to connect to Sibelius Connect on port {self.port}; mock the bridge call instead"
        )
    await _real_connect(self)


@pytest.fixture(autouse=True)
def _no_real_sibelius(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(SibeliusClient, "connect", _guarded_connect)
