"""The MuseScore back end's operations, shared by its MCP server and CLI.

Each function takes a MuseScoreBridge and mirrors a Sibelius MCP tool:
overview, query, apply (one undo step) and undo. See docs/musescore.md.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sibelius_websocket_cli.query import build_selector

from . import score
from .bridge import MuseScoreBridge
from .client import MuseScoreError


@dataclass
class Snapshot:
    """The whole score as read: staves, addressed objects, bar digests."""

    info: dict[str, Any]
    staves: list[dict[str, Any]]
    read: dict[str, Any]
    objects: list[dict[str, Any]]

    @property
    def digests(self) -> dict[tuple[int, int], str]:
        return {(c["staff"], c["bar"]): c["digest"] for c in self.read["content"]}

    @property
    def expect(self) -> dict[str, Any]:
        """The score guard ApplyBatch checks: the same score, bar and staff counts."""
        return {"name": self.info["name"], "measures": self.read["barCount"], "staves": self.info["staves"]}


async def snapshot(bridge: MuseScoreBridge) -> Snapshot:
    # A full read of 300 bars with 7,200 notes took 38 ms (docs/musescore.md),
    # so the whole score is read every time.
    info = await bridge.call("GetScoreInfo")
    staves = await bridge.call("GetStaves")
    read = await bridge.read()
    return Snapshot(info, staves, read, score.locate(read))


def backup_dir() -> Path:
    base = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache")))
    return base / "sibelius-websocket-cli" / "musescore" / "backups"


async def overview(bridge: MuseScoreBridge) -> dict[str, Any]:
    result = await bridge.overview()
    read = await bridge.read(staves=[0])
    result["bars"] = read["barCount"]
    renumbered = [b for b in read["bars"] if b["no"] + 1 != b["bar"]]
    if renumbered:
        result["barNumbers"] = "displayed numbers differ from bar order from bar " \
            f"{renumbered[0]['bar']} (shown as {renumbered[0]['no'] + 1})"
    return result


def resolve_staves(requested: list[str], staves: list[dict[str, Any]]) -> list[int]:
    """Staff numbers or part names (case-insensitive) as staff numbers; 0 or "system" is the system staff."""
    out: list[int] = []
    for item in requested:
        text = str(item).strip()
        if text == "0" or text.lower() == "system":
            out.append(score.SYSTEM_STAFF)
        elif text.isdigit():
            if not any(s["staff"] == int(text) for s in staves):
                raise score.MuseScoreBatchError(f"no staff {text}; staves are 1-{len(staves)}")
            out.append(int(text))
        else:
            matches = [s["staff"] for s in staves
                       if text.lower() in {str(s.get("partName", "")).lower(), str(s.get("shortName", "")).lower()}]
            if not matches:
                names = sorted({s.get("partName") or "?" for s in staves})
                raise score.MuseScoreBatchError(f"no staff named {text!r}; parts: {', '.join(names)}")
            out.extend(matches)
    return out


async def query(
    bridge: MuseScoreBridge,
    *,
    staves: list[str] | None = None,
    from_bar: int | None = None,
    to_bar: int | None = None,
    types: list[str] | None = None,
    voice: int | None = None,
    where: list[str] | None = None,
    fields: list[str] | None = None,
    limit: int = 200,
) -> dict[str, Any]:
    selector = build_selector(staves=[], from_bar=from_bar, to_bar=to_bar, types=types or [], voice=voice,
                              where=where or [], fields=fields or [], limit=limit)
    if staves:
        selector["staves"] = resolve_staves(staves, await bridge.call("GetStaves"))
    read = await bridge.read(from_bar, to_bar, selector["staves"] or None)
    return score.query(score.locate(read), selector)


async def apply(bridge: MuseScoreBridge, operations: list[dict[str, Any]], *, dry_run: bool = False) -> dict[str, Any]:
    """Apply a batch as one undo step; nothing changes unless every op succeeds.

    A dry run makes the edits and rolls them back, so it shows each object
    after the change. A real run first writes a MusicXML copy of the score
    as a record (MuseScore's plug-ins cannot write .mscz).
    """
    snap = await snapshot(bridge)
    primitives, digests = score.prepare_batch(
        operations, snap.objects, snap.staves, snap.read["division"], snap.digests, snap.read["bars"],
    )
    result: dict[str, Any] = {}
    if not dry_run:
        folder = backup_dir()
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{snap.info['name']}-{time.strftime('%Y%m%d-%H%M%S')}.musicxml"
        written = await bridge.write_copy(str(path))
        if not written.get("written") or not path.exists():
            raise MuseScoreError(f"could not write the backup copy {path}; nothing was changed")
        result["backup"] = str(path)
    applied = await bridge.apply(primitives, snap.expect, digests, dry_run=dry_run)
    bars = {b["bar"]: b["tick"] for b in snap.read["bars"]}
    division = snap.read["division"]

    def view(described: dict[str, Any] | None, ref: dict[str, Any]) -> dict[str, Any] | None:
        if described is None:
            return None
        return score.public(score.present(described, ref["staff"], ref["bar"], bars[ref["bar"]], division))

    result.update(
        dryRun=dry_run,
        applied=applied["applied"],
        results=[_result(p, r, view) for p, r in zip(primitives, applied["results"])],
    )
    if dry_run:
        result["note"] = "The batch ran and was rolled back; nothing changed."
    else:
        result["undoSteps"] = 1
    return result


def _result(primitive: dict[str, Any], raw: dict[str, Any], view: Any) -> dict[str, Any]:
    """One primitive's report: the object before and after, or what it added."""
    place = primitive.get("ref") or primitive["at"]
    out = {"op": primitive["label"], "primitive": primitive["op"]}
    if "ref" in primitive:
        out.update(before=view(raw.get("before"), place), after=view(raw.get("after"), place))
    else:
        out["added"] = view(raw.get("added"), place)
    if raw.get("note"):
        out["note"] = raw["note"]
    return out


async def undo(bridge: MuseScoreBridge, steps: int = 1) -> dict[str, Any]:
    return await bridge.undo(steps)
