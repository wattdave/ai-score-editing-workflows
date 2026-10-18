"""Parsing for the playback-roadmap and Play-on-pass commands."""

from __future__ import annotations

import re

MAX_PASS = 8  # Inspector > Playback > Play on pass has checkboxes 1 to 8

_DASHES = "–—−"  # the Repeats dialog prints en dashes
_RANGE = re.compile(r"(\d+)\s*(?:-\s*(\d+))?")


def _normalize(text: str) -> str:
    for dash in _DASHES:
        text = text.replace(dash, "-")
    return text


def parse_bar_order(text: str, bar_count: int | None = None) -> list[int]:
    """'1-12, 1-12, 14' -> bar numbers in playback order (ranges ascend)."""
    order: list[int] = []
    for part in _normalize(text).replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        match = _RANGE.fullmatch(part)
        if not match:
            raise ValueError(f"cannot read {part!r}: use bar numbers and ranges such as '1-12, 1-12, 14'")
        first = int(match.group(1))
        last = int(match.group(2)) if match.group(2) else first
        if first < 1 or last < first:
            raise ValueError(f"bad range {part!r}: bars start at 1 and ranges must ascend")
        order.extend(range(first, last + 1))
    if not order:
        raise ValueError("the playback order is empty")
    if bar_count is not None and (bad := [n for n in order if n > bar_count]):
        raise ValueError(f"bar {bad[0]} is outside the score ({bar_count} bars)")
    return order


def format_bar_order(order: list[int]) -> str:
    """[1, 2, 3, 1, 2, 3, 5] -> '1-3, 1-3, 5' (the Repeats dialog's format, with a hyphen)."""
    runs: list[list[int]] = []
    for n in order:
        if runs and n == runs[-1][1] + 1:
            runs[-1][1] = n
        else:
            runs.append([n, n])
    return ", ".join(str(a) if a == b else f"{a}-{b}" for a, b in runs)


def parse_passes(text: str) -> list[int]:
    """'1-3' or '1,3' -> the passes (1 to 8) that stay ticked; 'none' ticks nothing."""
    if text.strip().lower() == "none":
        return []
    passes: set[int] = set()
    for part in _normalize(text).split(","):
        match = _RANGE.fullmatch(part.strip())
        if not match:
            raise ValueError(f"cannot read {part.strip()!r}: use passes such as '1-3' or '1,3'")
        first = int(match.group(1))
        last = int(match.group(2)) if match.group(2) else first
        if first < 1 or last > MAX_PASS or last < first:
            raise ValueError(f"passes run from 1 to {MAX_PASS}, got {part.strip()!r}")
        passes.update(range(first, last + 1))
    return sorted(passes)
