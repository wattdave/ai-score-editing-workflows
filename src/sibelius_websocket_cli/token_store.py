"""Persistence for Sibelius Connect session tokens.

Approval in Sibelius is per-token (SPEC.md 1.1), so the token must be
persisted to avoid an approval dialog on every invocation. Tokens are
stored in a single JSON file keyed by "host:port".
"""

from __future__ import annotations

import json
import os
from pathlib import Path


def default_path() -> Path:
    config_home = os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
    return Path(config_home) / "sibelius-websocket-cli" / "token.json"


class TokenStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_path()

    def _key(self, host: str, port: int) -> str:
        return f"{host}:{port}"

    def _read_all(self) -> dict[str, str]:
        try:
            data = json.loads(self.path.read_text())
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def load(self, host: str, port: int) -> str | None:
        return self._read_all().get(self._key(host, port))

    def save(self, host: str, port: int, token: str) -> None:
        tokens = self._read_all()
        tokens[self._key(host, port)] = token
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(tokens, indent=2) + "\n")
        self.path.chmod(0o600)

    def forget(self, host: str, port: int) -> bool:
        """Remove the token for host:port. Returns True if one existed."""
        tokens = self._read_all()
        removed = tokens.pop(self._key(host, port), None) is not None
        if removed:
            self.path.write_text(json.dumps(tokens, indent=2) + "\n")
        return removed
