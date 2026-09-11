"""Compact, deterministic output formats intended for automated clients."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any


_SELECTION_FIELDS = ("isPassage", "topStaff", "bottomStaff", "firstBar", "lastBar")


def project_inspect(
    score_info: Mapping[str, Any],
    staves: Sequence[Mapping[str, Any]],
    selection: Mapping[str, Any],
) -> dict[str, Any]:
    """Project score, staff, and selection data into an agent-sized summary."""
    projected_staves = []
    for fallback_number, staff in enumerate(staves, start=1):
        staff_number = staff.get("staffNum", staff.get("staffNumber", fallback_number))
        name = (
            staff.get("fullInstrumentName")
            or staff.get("instrumentName")
            or staff.get("name")
            or f"Staff {staff_number}"
        )
        projected_staves.append({"staffNum": staff_number, "instrumentName": name})

    projected_staves.sort(key=lambda item: (item["staffNum"], item["instrumentName"]))
    projected_selection = {
        field: selection[field] for field in _SELECTION_FIELDS if field in selection
    }

    return {
        "fileName": score_info.get("fileName", ""),
        "title": score_info.get("title", ""),
        "staffCount": score_info.get("staffCount", len(projected_staves)),
        "barCount": score_info.get("barCount", 0),
        "selection": projected_selection,
        "staves": projected_staves,
    }


def render_compact_inspect(
    score_info: Mapping[str, Any],
    staves: Sequence[Mapping[str, Any]],
    selection: Mapping[str, Any],
) -> str:
    """Render :func:`project_inspect` as whitespace-free, Unicode JSON."""
    return json.dumps(
        project_inspect(score_info, staves, selection),
        ensure_ascii=False,
        separators=(",", ":"),
    )


def render_compact_lyrics(syllables: Sequence[Mapping[str, Any]]) -> str:
    """Render lyric edit addresses as one deterministic, safely quoted line each."""
    ordered = sorted(
        syllables,
        key=lambda item: (
            _integer(item.get("staff")),
            _integer(item.get("bar")),
            _integer(item.get("index")),
            _integer(item.get("position")),
            _integer(item.get("voice")),
        ),
    )
    lines = []
    for syllable in ordered:
        address = (
            f"S{_integer(syllable.get('staff'))} "
            f"B{_integer(syllable.get('bar'))} "
            f"I{_integer(syllable.get('index'))} "
            f"P{_integer(syllable.get('position'))} "
            f"V{_integer(syllable.get('voice'), default=1)}"
        )
        if "line" in syllable:
            address += f" L{_integer(syllable.get('line'), default=1)}"
        text = json.dumps(str(syllable.get("text", "")), ensure_ascii=False)
        lines.append(f"{address} {text}")
    return "\n".join(lines)


def _integer(value: Any, *, default: int = 0) -> int:
    """Return deterministic numeric addresses when bridge payload fields are absent."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
