"""Typed calls to the sibwscli bridge, with version checks.

MuseScore reports its version as major * 10000 + minor * 100 + patch
(4.7.5 is 40705). The back end needs 4.6: the undo-stack lock that makes
cmd() actions join a batch, actualKey/concertKey, hasParentheses and
doLayout all arrived then (docs/musescore.md).
"""

from __future__ import annotations

from typing import Any

from . import install
from .client import MuseScoreClient, MuseScoreError

MIN_MSCORE = 40600
#: Newest MuseScore minor version the back end was checked against.
TESTED_MSCORE = (4, 7)
MAX_UNDO_STEPS = 20


def version_text(version: int) -> str:
    return f"{version // 10000}.{version // 100 % 100}.{version % 100}"


class MuseScoreBridge:
    def __init__(self, client: MuseScoreClient) -> None:
        self.client = client
        self._checked = False

    async def check(self) -> dict[str, Any]:
        """Check the bridge and MuseScore versions once per connection."""
        result = await self.client.call("GetBridgeVersion")
        bridge = result.get("version")
        if bridge != install.BRIDGE_VERSION:
            raise MuseScoreError(
                f"the bridge plug-in in MuseScore is version {bridge}, this back end needs "
                f"{install.BRIDGE_VERSION}: run 'musescore-cli install-plugin', restart MuseScore, "
                f"then choose Plugins > {install.PLUGIN_TITLE}"
            )
        mscore = self.client.last.get("mscoreVersion") or 0
        if mscore < MIN_MSCORE:
            raise MuseScoreError(f"MuseScore {version_text(mscore)} is too old: 4.6 or newer is needed")
        self._checked = True
        warnings = []
        if (mscore // 10000, mscore // 100 % 100) > TESTED_MSCORE:
            warnings.append(f"MuseScore {version_text(mscore)} is newer than the versions checked "
                            f"({TESTED_MSCORE[0]}.{TESTED_MSCORE[1]})")
        return {"bridge": bridge, "mscore": version_text(mscore), "warnings": warnings}

    async def call(self, method: str, args: dict[str, Any] | None = None,
                   timeout: float | None = None) -> Any:
        if not self._checked:
            await self.check()
        return await self.client.call(method, args, timeout)

    async def overview(self) -> dict[str, Any]:
        versions = await self.check()
        return {
            **versions,
            "score": await self.call("GetScoreInfo"),
            "staves": await self.call("GetStaves"),
        }

    async def undo(self, steps: int = 1) -> dict[str, Any]:
        if not 1 <= steps <= MAX_UNDO_STEPS:
            raise MuseScoreError(f"steps must be 1-{MAX_UNDO_STEPS}")
        return await self.call("Undo", {"steps": steps})

    async def read(self, from_bar: int | None = None, to_bar: int | None = None,
                   staves: list[int] | None = None) -> dict[str, Any]:
        args: dict[str, Any] = {"staves": staves or []}
        if from_bar is not None:
            args["fromBar"] = from_bar
        if to_bar is not None:
            args["toBar"] = to_bar
        return await self.call("Read", args)

    async def apply(self, primitives: list[dict[str, Any]], expect: dict[str, Any], digests: dict[str, str],
                    dry_run: bool = False, copy: dict[str, Any] | None = None) -> dict[str, Any]:
        args = {"primitives": primitives, "expect": expect, "digests": digests, "dryRun": dry_run}
        if copy:
            args["copy"] = copy
        return await self.call("ApplyBatch", args)

    async def structure(self, from_bar: int | None = None, to_bar: int | None = None) -> dict[str, Any]:
        args: dict[str, Any] = {}
        if from_bar is not None:
            args["fromBar"] = from_bar
        if to_bar is not None:
            args["toBar"] = to_bar
        return await self.call("GetStructure", args)

    async def write_copy(self, path: str, format: str = "musicxml", timeout: float | None = None) -> dict[str, Any]:
        return await self.call("WriteCopy", {"path": path, "format": format}, timeout)

    async def save(self) -> dict[str, Any]:
        return await self.call("Save")

    async def meta_tags(self) -> dict[str, str]:
        return await self.call("GetMetaTags")

    async def set_meta_tags(self, tags: dict[str, str]) -> dict[str, Any]:
        return await self.call("SetMetaTags", {"tags": tags})
