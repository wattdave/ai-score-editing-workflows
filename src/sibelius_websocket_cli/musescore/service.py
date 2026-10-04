"""The MuseScore back end's operations, shared by its MCP server and CLI.

Each function takes a MuseScoreBridge and mirrors a Sibelius MCP tool:
overview, structure, query, apply (one undo step), undo, save, export,
project info and lyrics. See docs/musescore.md.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sibelius_websocket_cli.query import build_selector

from . import score
from .bridge import MuseScoreBridge
from . import window
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
    needs_style = isinstance(operations, list) and any(
        isinstance(o, dict) and o.get("op") == "set-layout" for o in operations
    )
    primitives, digests, copy = score.prepare_batch(
        operations, snap.objects, snap.staves, snap.read["division"], snap.digests, snap.read["bars"],
        await bridge.structure(1, 1) if needs_style else None,
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
    applied = await bridge.apply(primitives, snap.expect, digests, dry_run=dry_run, copy=copy)
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
    place = primitive.get("ref") or primitive.get("at")
    out = {"op": primitive["label"], "primitive": primitive["op"]}
    if "ref" in primitive:
        out.update(before=view(raw.get("before"), place), after=view(raw.get("after"), place))
    elif place:
        out["added"] = view(raw.get("added"), place)
    else:  # structural: bars or the whole score
        out.update({k: primitive[k] for k in ("bar", "count", "type", "number", "values") if k in primitive})
    if raw.get("note"):
        out["note"] = raw["note"]
    return out


async def structure(bridge: MuseScoreBridge, from_bar: int | None = None,
                    to_bar: int | None = None) -> dict[str, Any]:
    raw = await bridge.structure(from_bar, to_bar)
    staves = await bridge.call("GetStaves")
    return score.structure_report(raw, staves)


async def undo(bridge: MuseScoreBridge, steps: int = 1) -> dict[str, Any]:
    return await bridge.undo(steps)


# ------------------------------------------------------------------ files

#: export_score formats: writeScore's extension and the suffixes a path may have.
EXPORT_FORMATS: dict[str, tuple[str, ...]] = {
    "pdf": (".pdf",), "png": (".png",), "svg": (".svg",), "musicxml": (".musicxml", ".xml"),
    "mxl": (".mxl",), "mid": (".mid",), "mp3": (".mp3",), "wav": (".wav",),
    "flac": (".flac",), "ogg": (".ogg",),
}
AUDIO_FORMATS = {"mp3", "wav", "flac", "ogg"}
SAVE_WAIT = 30.0


async def save(bridge: MuseScoreBridge, path: str | None = None) -> dict[str, Any]:
    """Save the score to its own file (File > Save); with path, also copy the saved file there.

    The plug-in API cannot save elsewhere or write .mscz, so a copy is the
    saved file copied. A score that has never been saved is refused: MuseScore
    would ask where to save it.
    """
    info = await bridge.call("GetScoreInfo")
    source = window.score_file(info["name"])
    if source is None:
        raise MuseScoreError(
            f"cannot find the file of '{info['name']}': it has never been saved (save it once in MuseScore "
            "with File > Save), or Terminal lacks Accessibility permission to read MuseScore's window"
        )
    if source.suffix not in {".mscz", ".mscx"} or not source.exists():
        raise MuseScoreError(f"{source} is not a local MuseScore file; save it in MuseScore instead")
    target = Path(path).expanduser().resolve() if path else None
    if target is not None and target.suffix != source.suffix:
        raise MuseScoreError(f"path must end in {source.suffix}, like the score's own file")
    before = source.stat().st_mtime_ns
    await bridge.save()
    deadline = time.monotonic() + SAVE_WAIT
    while source.stat().st_mtime_ns == before:
        if time.monotonic() > deadline:
            raise MuseScoreError(f"MuseScore did not write {source}: a dialog may be open there")
        await asyncio.sleep(0.2)
    result: dict[str, Any] = {"saved": str(source)}
    if target is not None and target != source:
        target.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.sleep(0.5)  # let MuseScore finish writing the file
        shutil.copyfile(source, target)
        result["copy"] = str(target)
    return result


async def export(bridge: MuseScoreBridge, format: str, path: str) -> dict[str, Any]:
    """Export the whole score to path; PNG and SVG write one file per page (name-1.png, ...)."""
    if format not in EXPORT_FORMATS:
        raise MuseScoreError(f"format must be one of: {', '.join(EXPORT_FORMATS)}")
    target = Path(path).expanduser().resolve()
    if target.suffix.lower() not in EXPORT_FORMATS[format]:
        raise MuseScoreError(f"a {format} path must end in {' or '.join(EXPORT_FORMATS[format])}")
    target.parent.mkdir(parents=True, exist_ok=True)
    started = time.time() - 1
    # writeScore appends its extension unless the path already ends in it, so .xml is sent as "xml".
    ext = target.suffix.lower()[1:]
    written = await bridge.write_copy(str(target), ext, timeout=600 if format in AUDIO_FORMATS else 120)
    files = [target] if target.exists() and target.stat().st_mtime >= started else sorted(
        (f for f in target.parent.glob(f"{target.stem}-*{target.suffix}")
         if f.stem[len(target.stem) + 1:].isdigit() and f.stat().st_mtime >= started),
        key=lambda f: int(f.stem[len(target.stem) + 1:]),
    )
    if not written.get("written") or not files:
        raise MuseScoreError(f"MuseScore did not export {target}")
    result: dict[str, Any] = {"files": [str(f) for f in files]}
    if format in {"png", "svg"} and len(files) > 1:
        result["note"] = "one file per page"
    return result


# ------------------------------------------------------------------ metadata

#: Friendly names for MuseScore's metadata tags (File > Project properties).
TAG_ALIASES = {"title": "workTitle", "worktitle": "workTitle", "movement": "movementTitle"}


def _tag_name(name: str, known: list[str]) -> str:
    key = name.replace(" ", "").replace("_", "").lower()
    if key in TAG_ALIASES:
        return TAG_ALIASES[key]
    for tag in known:
        if tag.lower() == key:
            return tag
    raise MuseScoreError(f"unknown metadata field {name!r}; fields: {', '.join(known)}")


async def project_info(bridge: MuseScoreBridge) -> dict[str, Any]:
    return {"fields": await bridge.meta_tags()}


async def set_project_info(bridge: MuseScoreBridge, fields: dict[str, str]) -> dict[str, Any]:
    """Set metadata tags; MuseScore does not record these for undo, so the old values are returned."""
    if not fields:
        raise MuseScoreError("no fields given")
    known = list(await bridge.meta_tags())
    tags = {_tag_name(name, known): str(value) for name, value in fields.items()}
    changed = await bridge.set_meta_tags(tags)
    return {
        "before": changed["before"],
        "after": {tag: changed["after"][tag] for tag in tags},
        "note": "metadata changes are not undoable in MuseScore; set the 'before' values to revert. "
                "The title frame on the first page is separate text and does not change.",
    }


# ------------------------------------------------------------------ lyrics

def _one_staff(requested: str, staves: list[dict[str, Any]]) -> int:
    found = [s for s in resolve_staves([requested], staves) if s != score.SYSTEM_STAFF]
    if not found:
        raise score.MuseScoreBatchError("the system staff has no lyrics")
    return found[0]


async def read_lyrics(bridge: MuseScoreBridge, staff: str, verse: int = 1) -> dict[str, Any]:
    """A staff's verse as one line of hyphenated text, with the bars it spans."""
    staff_no = _one_staff(staff, await bridge.call("GetStaves"))
    read = await bridge.read(staves=[staff_no])
    line = score.lyric_line(score.locate(read), staff_no, verse)
    result: dict[str, Any] = {"staff": staff_no, "verse": verse, "text": score.lyric_text(line),
                              "syllables": len(line)}
    if line:
        result["bars"] = f"{line[0]['bar']}-{line[-1]['bar']}"
    return result


async def edit_lyrics(bridge: MuseScoreBridge, staff: str, text: str, verse: int = 1) -> dict[str, Any]:
    """Replace a staff's verse with text of the same syllable count, as one undo step."""
    if not text.strip():
        raise MuseScoreError("text is empty")
    snap = await snapshot(bridge)
    staff_no = _one_staff(staff, snap.staves)
    line = score.lyric_line(snap.objects, staff_no, verse)
    primitives, digests = score.lyric_edits(line, text, snap.digests, staff_no, verse)
    before = score.lyric_text(line)
    if not primitives:
        return {"staff": staff_no, "verse": verse, "before": before, "after": before, "changed": 0,
                "undoSteps": 0}
    await bridge.apply(primitives, snap.expect, digests)
    after = await read_lyrics(bridge, str(staff_no), verse)
    expected = score.lyric_text([{**s, "text": w, "syllabic": y}
                                 for s, (w, y) in zip(line, score.split_lyrics(text))])
    result = {"staff": staff_no, "verse": verse, "before": before, "after": after["text"],
              "changed": len({id(p["ref"]) for p in primitives}), "undoSteps": 1}
    if after["text"] != expected:
        result["warning"] = f"the verse reads back differently from the text sent: {expected}"
    return result
