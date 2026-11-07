"""Hide time signatures the print does not show: pure helpers.

Behind ``sibelius-cli hide-time-signatures``. Sibelius ignores
``print-object="no"`` on a MusicXML ``<time>`` and draws the signature (Lullay
My Liking: 53 bars; Mirie It Is), so the hidden ones are hidden after import
with ``set Hidden true`` on the system staff's TimeSignature objects.

Bars are Sibelius bars: the n-th measure of the file is bar n (a pickup is
bar 1), which is how an imported score numbers them.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any

from ai_score_editing.core.errors import BatchError

SYSTEM_STAFF = 0


def parse_bars(spec: str) -> list[int]:
    """Parse "2-54,60,62-63" (commas or spaces between items) into sorted bars."""
    bars: set[int] = set()
    items = [item for item in spec.replace(",", " ").split() if item]
    if not items:
        raise BatchError("--bars is empty")
    for item in items:
        parts = item.replace("..", "-").split("-")
        try:
            if len(parts) == 1:
                first = last = int(parts[0])
            elif len(parts) == 2:
                first, last = int(parts[0]), int(parts[1])
            else:
                raise ValueError(item)
        except ValueError as exc:
            raise BatchError(f"bars must look like 2-54,60, not {item!r}") from exc
        if first < 1 or last < first:
            raise BatchError(f"bar range {item!r} must run forwards from bar 1 or later")
        bars.update(range(first, last + 1))
    return sorted(bars)


def hidden_time_bars(root: ET.Element) -> tuple[list[int], list[int]]:
    """Bars whose time signature the file hides (``<time print-object="no">``).

    Returns (hidden, mixed). A bar is hidden when any part hides a time
    signature in it. ``mixed`` lists the hidden bars where some part also has a
    printed ``<time>``: Sibelius has one time signature for all staves, so
    those are hidden too, but worth a look against the print.
    """
    hidden: set[int] = set()
    shown: set[int] = set()
    for part in root.iter("part"):
        for n, measure in enumerate(part.findall("measure"), start=1):
            for time in measure.iter("time"):
                (hidden if time.get("print-object") == "no" else shown).add(n)
    return sorted(hidden), sorted(hidden & shown)


@dataclass
class HidePlan:
    """The set ops to send and what was found for each wanted bar."""

    batch: list[dict[str, Any]]
    hide: list[int] = field(default_factory=list)
    already_hidden: list[int] = field(default_factory=list)
    missing: list[int] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        out: dict[str, Any] = {"hide": len(self.hide), "bars": compact_bars(self.hide)}
        if self.already_hidden:
            out["alreadyHidden"] = compact_bars(self.already_hidden)
        if self.missing:
            out["noTimeSignature"] = compact_bars(self.missing)
        return out


def plan_hide(rows: list[dict[str, Any]], bars: list[int]) -> HidePlan:
    """Build ``set Hidden true`` ops for the TimeSignature objects in ``bars``.

    ``rows`` are query results for TimeSignature on the system staff, with the
    ``Hidden`` field. Each op carries the object's type and position as
    guards. Bars with no time signature object are reported, not an error:
    Sibelius may drop one that repeats the previous signature.
    """
    wanted = set(bars)
    found: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        if row.get("type") != "TimeSignature" or row.get("bar") not in wanted:
            continue
        found.setdefault(int(row["bar"]), []).append(row)
    plan = HidePlan(batch=[])
    for bar in sorted(wanted):
        objects = found.get(bar)
        if not objects:
            plan.missing.append(bar)
            continue
        todo = [o for o in objects if not (o.get("fields") or {}).get("Hidden")]
        if not todo:
            plan.already_hidden.append(bar)
            continue
        plan.hide.append(bar)
        for obj in todo:
            op: dict[str, Any] = {
                "op": "set", "staff": SYSTEM_STAFF, "bar": bar, "index": int(obj["index"]),
                "type": "TimeSignature", "prop": "Hidden", "value": True,
            }
            if obj.get("position") is not None:
                op["position"] = int(obj["position"])
            plan.batch.append(op)
    return plan


def compact_bars(bars: list[int]) -> str:
    """[1, 2, 3, 5, 7, 8] -> "1-3,5,7-8"."""
    out: list[str] = []
    run: list[int] = []
    for bar in sorted(set(bars)):
        if run and bar != run[-1] + 1:
            out.append(_run_text(run))
            run = []
        run.append(bar)
    if run:
        out.append(_run_text(run))
    return ",".join(out)


def _run_text(run: list[int]) -> str:
    return str(run[0]) if len(run) == 1 else f"{run[0]}-{run[-1]}"
