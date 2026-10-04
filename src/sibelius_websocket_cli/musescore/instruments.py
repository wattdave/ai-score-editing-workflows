"""MuseScore instrument ids, for add_instrument.

instruments.tsv lists the ids of MuseScore 4.7.5's instruments.xml with
their track names and MusicXML sound ids. appendPart quietly adds a default
instrument for an id it doesn't know, so ids are checked here first (and
again in the bridge).
"""

from __future__ import annotations

import difflib
from functools import cache
from pathlib import Path

from .client import MuseScoreError

TABLE = Path(__file__).with_name("instruments.tsv")


@cache
def table() -> list[tuple[str, str, str]]:
    rows = []
    for line in TABLE.read_text().splitlines():
        if line and not line.startswith("#"):
            instrument_id, name, musicxml = (line.split("\t") + ["", ""])[:3]
            rows.append((instrument_id, name, musicxml))
    return rows


def resolve(instrument: str) -> dict[str, str]:
    """An instrument id, MusicXML sound id (e.g. strings.violin) or unique track name, as bridge args."""
    text = instrument.strip()
    rows = table()
    for instrument_id, _, _ in rows:
        if instrument_id == text:
            return {"instrumentId": instrument_id}
    for instrument_id, _, musicxml in rows:
        if musicxml and musicxml == text:
            return {"instrumentId": instrument_id}
    named = [r for r in rows if r[1].lower() == text.lower()]
    if len(named) == 1:
        return {"instrumentId": named[0][0]}
    if named:
        choices = ", ".join(f"{r[0]}" for r in named[:12])
        raise MuseScoreError(f"several instruments are called {text!r}; give an id: {choices}")
    keys = [r[0] for r in rows] + [r[1].lower() for r in rows]
    close = difflib.get_close_matches(text.lower(), keys, n=6, cutoff=0.6)
    ids = []
    for key in close:
        for instrument_id, name, _ in rows:
            if key in {instrument_id, name.lower()} and instrument_id not in ids:
                ids.append(instrument_id)
    hint = f"; close: {', '.join(ids)}" if ids else ""
    raise MuseScoreError(f"MuseScore has no instrument {text!r} (ids are like violin, flute, soprano, "
                         f"bb-clarinet){hint}")
