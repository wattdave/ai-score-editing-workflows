"""Copy part of a bar (a range of beats) between staves or bars.

The bridge's copy-passage copies whole bars only. A partial range is built from
ordinary batch operations instead: delete the destination's notes and lyrics in
the range, then add the source's notes and lyrics there. Everything runs as one
apply batch, so it is one undo step and needs no newer bridge.

Positions are 1/256 of a quarter note, as everywhere else. Rows are the objects
returned by the bridge's Query (NoteRest and LyricItem).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ai_score_editing.units import UNITS_PER_QUARTER

QUARTER = UNITS_PER_QUARTER
WHOLE = 4 * QUARTER


class CopyRangeError(ValueError):
    """The requested range cannot be copied as asked."""


def parse_beats(text: str) -> tuple[int, int]:
    """'3-4' -> (3, 4); '3' -> (3, 3)."""
    try:
        first, _, last = text.partition("-")
        low, high = int(first), int(last or first)
    except ValueError:
        raise CopyRangeError(f"--beats must look like 3-4 or 3, not {text!r}") from None
    if low < 1 or high < low:
        raise CopyRangeError(f"--beats {text!r}: beats count from 1 and must not run backwards")
    return low, high


def beat_length(denominator: int, beat_unit: str) -> int:
    """Length of one beat. 'quarter' counts quarter notes whatever the meter;
    'signature' counts the time signature's own beat (a half note in 2/2)."""
    if beat_unit == "quarter":
        return QUARTER
    return WHOLE // denominator


def beats_to_positions(first: int, last: int, numerator: int, denominator: int, beat_unit: str) -> tuple[int, int]:
    """Beats first..last (1-based, inclusive) as a half-open position range."""
    unit = beat_length(denominator, beat_unit)
    start, end = (first - 1) * unit, last * unit
    bar = numerator * WHOLE // denominator
    if end > bar:
        raise CopyRangeError(
            f"beats {first}-{last} run past the end of a {numerator}/{denominator} bar "
            f"({bar // unit if bar % unit == 0 else bar / unit:g} beats of this size)"
        )
    return start, end


def beat_note(numerator: int, denominator: int, beat_unit: str, first: int, last: int, start: int, end: int) -> str:
    """One line saying how the beats were read, so a wrong guess shows."""
    what = "quarter-note" if beat_unit == "quarter" else f"time-signature ({'half' if denominator == 2 else '1/%d' % denominator}-note)"
    return (
        f"beats {first}-{last} of a {numerator}/{denominator} bar = positions {start}-{end} "
        f"({what} beats; --beat-unit {'signature' if beat_unit == 'quarter' else 'quarter'} reads them the other way)"
    )


def _voice(row: dict[str, Any]) -> int:
    return row.get("voice", 1)


def _notes(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in rows if r.get("type") == "NoteRest" and r.get("notes")]


def _lyrics(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in rows if r.get("type") == "LyricItem"]


def _crosses(row: dict[str, Any], start: int, end: int) -> bool:
    first, last = row["position"], row["position"] + row.get("duration", 0)
    return first < end and last > start and (first < start or last > end)


def verse_of(row: dict[str, Any]) -> int:
    """Lyric line from the style id (text.staff.space.hypen.lyrics.verse2 -> 2)."""
    style = row.get("styleId", "")
    tail = style.rsplit("verse", 1)[-1]
    return int(tail) if tail.isdigit() else 1


def describe(rows: list[dict[str, Any]], start: int, end: int) -> str:
    """Compact text for the range: 'G:2 G:1 | v1 Si me' (durations in quarters)."""
    parts = []
    for row in sorted((r for r in rows if r.get("type") == "NoteRest"), key=lambda r: (_voice(r), r["position"])):
        if not start <= row["position"] < end:
            continue
        names = [n["name"] for n in row.get("notes", [])]
        pitch = "z" if not names else names[0] if len(names) == 1 else "[" + " ".join(names) + "]"
        tie = "~" if any(n.get("tied") for n in row.get("notes", [])) else ""
        parts.append(f"{pitch}:{row['duration'] / QUARTER:g}{tie}")
    words: dict[int, list[str]] = {}
    for row in sorted(_lyrics(rows), key=lambda r: r["position"]):
        if start <= row["position"] < end:
            words.setdefault(verse_of(row), []).append(row["text"] + ("-" if row.get("syllableType") == "middle" else ""))
    text = " ".join(parts) or "(empty)"
    for verse in sorted(words):
        text += f" | v{verse} " + " ".join(words[verse])
    return text


@dataclass
class StaffPlan:
    staff: int
    dest_staff: int
    ops: list[dict[str, Any]] = field(default_factory=list)
    before: str = ""
    source: str = ""
    replaced: dict[str, int] = field(default_factory=lambda: {"notes": 0, "lyrics": 0})
    warnings: list[str] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "staff": self.staff, "destStaff": self.dest_staff,
            "destinationBefore": self.before, "copied": self.source,
            "replaced": dict(self.replaced),
        }
        if self.warnings:
            out["warnings"] = self.warnings
        return out


def plan_staff(
    staff: int,
    dest_staff: int,
    src_bar: int,
    dest_bar: int,
    src_rows: list[dict[str, Any]],
    dest_rows: list[dict[str, Any]],
    start: int,
    end: int,
    dest_start: int,
    prior_rows: list[dict[str, Any]] | None = None,
) -> StaffPlan:
    """Operations that make dest_bar[dest_start:] hold src_bar[start:end] on one staff pair.

    prior_rows are the destination staff's notes before the range (the end of
    the previous bar when the range starts the bar), used only to check ties.
    """
    plan = StaffPlan(staff, dest_staff)
    dest_end = dest_start + (end - start)
    shift = dest_start - start

    for row in _notes(src_rows):
        if _crosses(row, start, end):
            raise CopyRangeError(
                f"staff {staff} bar {src_bar}: a note at position {row['position']} (length {row['duration']}) "
                f"crosses the edge of the range {start}-{end}; choose a range on note boundaries"
            )
    for row in _notes(dest_rows):
        if _crosses(row, dest_start, dest_end):
            raise CopyRangeError(
                f"staff {dest_staff} bar {dest_bar}: a note at position {row['position']} (length {row['duration']}) "
                f"crosses the edge of the destination range {dest_start}-{dest_end}; copying would cut it"
            )

    plan.before = describe(dest_rows, dest_start, dest_end)
    plan.source = describe(src_rows, start, end)

    for row in dest_rows:
        if not dest_start <= row["position"] < dest_end:
            continue
        if row.get("type") == "NoteRest" and row.get("notes"):
            plan.replaced["notes"] += 1
        elif row.get("type") == "LyricItem":
            plan.replaced["lyrics"] += 1
        else:
            continue
        plan.ops.append({
            "op": "delete", "staff": dest_staff, "bar": dest_bar, "index": row["index"],
            "type": row["type"], "position": row["position"],
        })

    copied = [r for r in _notes(src_rows) if start <= r["position"] < end]
    for row in sorted(copied, key=lambda r: (_voice(r), r["position"])):
        op: dict[str, Any] = {
            "op": "add-note", "staff": dest_staff, "bar": dest_bar, "position": row["position"] + shift,
            "duration": row["duration"], "pitches": [n["pitch"] for n in row["notes"]],
        }
        if _voice(row) != 1:
            op["voice"] = _voice(row)
        if any(n.get("tied") for n in row["notes"]):
            op["tied"] = True
        plan.ops.append(op)
    for row in sorted(_lyrics(src_rows), key=lambda r: r["position"]):
        if not start <= row["position"] < end:
            continue
        op = {
            "op": "add-lyric", "staff": dest_staff, "bar": dest_bar, "position": row["position"] + shift,
            "duration": row.get("duration") or QUARTER, "text": row["text"],
            "syllableType": "middle" if row.get("syllableType") == "middle" else "end",
            "verse": verse_of(row), "dy": row.get("dy", -192),
        }
        if _voice(row) != 1:
            op["voice"] = _voice(row)
        plan.ops.append(op)

    if copied and copied[-1].get("notes") and any(n.get("tied") for n in copied[-1]["notes"]) and end >= _bar_end(src_rows):
        plan.warnings.append("the last copied note is tied onward, so it now ties into whatever follows the destination range")
    others = [r for r in src_rows if start <= r.get("position", -1) < end and r.get("type") not in ("NoteRest", "LyricItem")]
    if others:
        plan.warnings.append(f"{len(others)} other object(s) in the source range (dynamics, text, lines) are not copied")

    prior = [r for r in _notes(prior_rows or []) if _voice(r) == 1]
    if prior and copied and any(n.get("tied") for n in prior[-1]["notes"]):
        first = sorted(copied, key=lambda r: r["position"])[0]
        if {n["pitch"] for n in prior[-1]["notes"]} != {n["pitch"] for n in first["notes"]}:
            plan.warnings.append("the note before the destination range is tied forward, but the first copied note has a different pitch")
    return plan


def _bar_end(rows: list[dict[str, Any]]) -> int:
    notes = _notes(rows) or rows
    return max((r["position"] + r.get("duration", 0) for r in notes), default=0)


def verify(plan_source_rows: list[dict[str, Any]], dest_rows_after: list[dict[str, Any]], start: int, end: int, dest_start: int) -> bool:
    """True when the destination range now holds the same notes and lyric text as the source range."""
    shift = dest_start - start

    def key(rows: list[dict[str, Any]], offset: int, lo: int, hi: int) -> list[Any]:
        out = []
        for row in rows:
            if not lo <= row["position"] < hi:
                continue
            if row.get("type") == "NoteRest" and row.get("notes"):
                out.append(("n", _voice(row), row["position"] + offset, row["duration"], tuple(sorted(n["pitch"] for n in row["notes"]))))
            elif row.get("type") == "LyricItem":
                out.append(("l", verse_of(row), row["position"] + offset, row["text"]))
        return sorted(out)

    return key(plan_source_rows, shift, start, end) == key(dest_rows_after, 0, dest_start, dest_start + (end - start))
