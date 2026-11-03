"""Persistence for Sibelius Connect session tokens.

Approval in Sibelius is per-token (docs/sibelius-protocol.md 1.1), so the token must be
persisted to avoid an approval dialog on every invocation. Tokens are
stored in a single JSON file keyed by "host:port".

A token is bound to the plug-in list declared in the tokenless connect that
produced it (the list cannot be changed on a token reconnect), so the list
is stored alongside the token: {"token": "...", "plugins": [...]}.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ai_score_editing.paths import config_dir


@dataclass
class TokenEntry:
    token: str
    plugins: list[str] = field(default_factory=list)

    def covers(self, plugins: list[str]) -> bool:
        """True if this token's session declared all the given plug-ins."""
        return set(plugins) <= set(self.plugins)


def default_path() -> Path:
    return config_dir() / "token.json"


class TokenStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_path()

    def _key(self, host: str, port: int) -> str:
        return f"{host}:{port}"

    def _read_all(self) -> dict[str, Any]:
        try:
            data = json.loads(self.path.read_text())
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def load(self, host: str, port: int) -> TokenEntry | None:
        entry = self._read_all().get(self._key(host, port))
        if isinstance(entry, str):  # pre-plugins format
            return TokenEntry(token=entry)
        if isinstance(entry, dict) and isinstance(entry.get("token"), str):
            plugins = entry.get("plugins")
            return TokenEntry(
                token=entry["token"],
                plugins=plugins if isinstance(plugins, list) else [],
            )
        return None

    def save(self, host: str, port: int, token: str, plugins: list[str] | None = None) -> None:
        tokens = self._read_all()
        tokens[self._key(host, port)] = {"token": token, "plugins": plugins or []}
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
