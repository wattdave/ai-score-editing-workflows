"""Install the sibwscli bridge plug-in into MuseScore 4.

The plug-in is written from msbridge.qml.in with a token, the port and the
bridge version filled in. The token is kept in
~/.config/sibelius-websocket-cli/musescore-token (mode 600) and reused, so
reinstalling does not invalidate a plug-in that is already running.
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path

#: Bump when msbridge.qml.in changes; the client refuses an older bridge.
BRIDGE_VERSION = 3
DEFAULT_PORT = 8766
PLUGIN_TITLE = "sibwscli bridge"
TEMPLATE = Path(__file__).with_name("msbridge.qml.in")


def config_dir() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "sibelius-websocket-cli"


def token_path() -> Path:
    return config_dir() / "musescore-token"


def plugin_dir() -> Path:
    default = Path.home() / "Documents" / "MuseScore4" / "Plugins"
    return Path(os.environ.get("MUSESCORE_PLUGIN_DIR", default)) / "sibwscli-bridge"


def read_token() -> str | None:
    path = token_path()
    if not path.exists():
        return None
    return path.read_text().strip() or None


def ensure_token() -> str:
    token = read_token()
    if not token:
        token = secrets.token_urlsafe(32)
        token_path().parent.mkdir(parents=True, exist_ok=True)
        token_path().write_text(token)
    token_path().chmod(0o600)
    return token


def render(token: str, port: int = DEFAULT_PORT) -> str:
    return (
        TEMPLATE.read_text()
        .replace("@TOKEN@", token)
        .replace("@PORT@", str(port))
        .replace("@VERSION@", str(BRIDGE_VERSION))
    )


def install(port: int = DEFAULT_PORT) -> Path:
    target = plugin_dir() / "msbridge.qml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render(ensure_token(), port))
    target.chmod(0o600)
    return target
