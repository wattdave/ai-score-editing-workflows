"""Client-to-bridge layer for Sibelius: calling the ScoreBridge plug-in.

The functions here take a connected ``SibeliusClient``; ``SibeliusBridge``
wraps one client and remembers the bridge version it reported, so the version
is read once per connection however many ``require`` calls follow.
"""

from __future__ import annotations

import json
import weakref
from pathlib import Path
from typing import Any

from ai_score_editing.core import batch_schema
from ai_score_editing.sibelius import protocol
from ai_score_editing.sibelius.client import SibeliusClient

BRIDGE_PLUGIN = "ScoreBridge"

# CLI format name -> (ManuScript SaveAs type, file extension)
EXPORT_FORMATS = {
    "musicxml": ("MUSICXML", ".musicxml"),
    "mxl": ("MXL", ".mxl"),
    "pdf": ("PDF", ".pdf"),
    "midi": ("Midi", ".mid"),
    "png": ("PNG", ".png"),
}


class BridgeError(Exception):
    def __init__(self, payload: Any) -> None:
        super().__init__(json.dumps(payload))
        self.payload = payload


class BridgeBusy(BridgeError):
    """Sibelius answered "busyError": a dialog is open and a person must dismiss it."""


BUSY_MESSAGE = (
    "Sibelius is busy: a dialog is probably open in Sibelius. Ask the user to "
    "dismiss it, then try again."
)


def raise_if_busy(response: dict[str, Any]) -> None:
    if response.get("message") == "busyError":
        raise BridgeBusy(BUSY_MESSAGE)


MIN_BRIDGE_VERSION = 7
CURRENT_BRIDGE_VERSION = 63
QUERY_BRIDGE_VERSION = 38
BATCH_BRIDGE_VERSION = 39
NUDGE_BRIDGE_VERSION = 41
STRUCTURAL_BRIDGE_VERSION = 44
STRUCTURE_READ_BRIDGE_VERSION = 45
BEAM_RESULT_BRIDGE_VERSION = 46
SYSTEM_STAFF_BRIDGE_VERSION = 48
LAYOUT_BATCH_BRIDGE_VERSION = 50
HIDE_EMPTY_STAVES_BRIDGE_VERSION = 52
AUDIO_EXPORT_BRIDGE_VERSION = 54
PLAYBACK_SOUNDS_BRIDGE_VERSION = 55
DELETE_BARS_BRIDGE_VERSION = 56
REPEATS_BRIDGE_VERSION = 57
LYRIC_VERSE_BRIDGE_VERSION = 58
SET_LYRIC_VERSE_BRIDGE_VERSION = 59
TUPLET_NOTES_BRIDGE_VERSION = 60
TEXT_FONTS_BRIDGE_VERSION = 61
QUERY_CONTAINERS_BRIDGE_VERSION = 62
FICTA_BRIDGE_VERSION = 63


def batch_bridge_version(operations: list[dict[str, Any]]) -> int:
    """The oldest bridge that runs every operation in a validated batch."""
    names = {operation["op"] for operation in operations}
    if "ficta" in names:
        return FICTA_BRIDGE_VERSION
    if names & {"add-tuplet-notes", "clear-bars"}:
        return TUPLET_NOTES_BRIDGE_VERSION
    if "set-lyric-verse" in names:
        return SET_LYRIC_VERSE_BRIDGE_VERSION
    if any(
        operation["op"] == "add-lyric" and ("verse" in operation or "dy" in operation)
        for operation in operations
    ):
        return LYRIC_VERSE_BRIDGE_VERSION
    if "delete-bars" in names:
        return DELETE_BARS_BRIDGE_VERSION
    if "hide-empty-staves" in names:
        return HIDE_EMPTY_STAVES_BRIDGE_VERSION
    if names & {"set-bar-number", "set-layout"} or any(
        operation.get("prop") == "NumNotes"
        or (operation["op"] == "add-bars" and ("bar" in operation or "length" in operation))
        for operation in operations
    ):
        return LAYOUT_BATCH_BRIDGE_VERSION
    if "add-line" in names or any(operation.get("staff") == batch_schema.SYSTEM_STAFF for operation in operations):
        return SYSTEM_STAFF_BRIDGE_VERSION
    if names & (batch_schema.STRUCTURAL | {"beam"}):
        return STRUCTURAL_BRIDGE_VERSION
    if "nudge" in names:
        return NUDGE_BRIDGE_VERSION
    return BATCH_BRIDGE_VERSION


class SibeliusBridge:
    """The ScoreBridge plug-in as seen through one connected client."""

    def __init__(self, client: SibeliusClient) -> None:
        self.client = client
        self._version: Any = None
        self._have_version = False

    async def call(self, method: str, args: list[Any] | None = None) -> Any:
        """Call a bridge method; raise BridgeError on transport or bridge failure."""
        response = await self.client.invoke_plugin(BRIDGE_PLUGIN, method, args)
        if not protocol.is_success(response):
            raise_if_busy(response)
            raise BridgeError(
                "bridge plug-in not reachable — run 'sibelius-cli "
                f"install-plugin' and restart Sibelius. Response: {json.dumps(response)}"
            )
        value = protocol.plugin_return_value(response)
        if isinstance(value, dict) and "error" in value:
            raise BridgeError(value["error"])
        return value

    async def apply_batch(self, operations: list[dict[str, Any]], dry_run: bool) -> dict[str, Any]:
        """Run ApplyBatch; return its result, including any partial results on failure."""
        response = await self.client.invoke_plugin(BRIDGE_PLUGIN, "ApplyBatch", [operations, dry_run])
        if not protocol.is_success(response):
            raise_if_busy(response)
            raise BridgeError(f"bridge plug-in not reachable. Response: {json.dumps(response)}")
        value = protocol.plugin_return_value(response)
        if not isinstance(value, dict):
            raise BridgeError(f"unexpected ApplyBatch result: {value!r}")
        return value

    async def version(self) -> Any:
        """The GetBridgeVersion result, read once and cached on this instance."""
        if not self._have_version:
            self._version = await self.call("GetBridgeVersion")
            self._have_version = True
        return self._version

    async def require(self, version: int, feature: str) -> None:
        info = await self.version()
        if not (isinstance(info, dict) and info.get("version", 0) >= version):
            raise BridgeError(
                f"{feature} needs bridge v{version}+, got {info!r} — run install-plugin and restart Sibelius"
            )


_bridges: weakref.WeakKeyDictionary[Any, SibeliusBridge] = weakref.WeakKeyDictionary()


def for_client(client: SibeliusClient) -> SibeliusBridge:
    """The one SibeliusBridge for this client (a fresh, uncached one if it cannot be weakly referenced)."""
    try:
        found = _bridges.get(client)
        if found is None:
            found = _bridges[client] = SibeliusBridge(client)
        return found
    except TypeError:
        return SibeliusBridge(client)


async def call(client: SibeliusClient, method: str, args: list[Any] | None = None) -> Any:
    return await for_client(client).call(method, args)


async def apply_batch(client: SibeliusClient, operations: list[dict[str, Any]], dry_run: bool) -> dict[str, Any]:
    return await for_client(client).apply_batch(operations, dry_run)


async def require_bridge(client: SibeliusClient, version: int, feature: str) -> None:
    await for_client(client).require(version, feature)


async def check_bridge_version(client: SibeliusClient) -> None:
    info = await for_client(client).version()
    if not (isinstance(info, dict) and info.get("version", 0) >= MIN_BRIDGE_VERSION):
        raise BridgeError(
            f"bridge v{MIN_BRIDGE_VERSION}+ required, got {info!r} — run install-plugin and restart Sibelius"
        )


def export_path(requested: str | None, score_file: str, extension: str) -> Path:
    """Resolve an export target that always carries the format's extension.

    Sibelius appends the extension itself when it is missing (``--out proof``
    is written as ``proof.png``), so the path is normalized up front to name
    the file Sibelius actually writes.
    """
    out = Path(requested).expanduser().resolve() if requested else Path(score_file).with_suffix(extension)
    if out.suffix.lower() != extension:
        out = out.with_name(out.name + extension)
    return out
