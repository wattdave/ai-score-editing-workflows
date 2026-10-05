"""Audit and delete redundant clef objects in the open Sibelius score.

OMR sheet music scanners (e.g. PhotoScore, SmartScore) frequently insert redundant
Clef objects at system breaks across all staves.

A clef is reported as redundant when either:
  * its ``styleId`` matches the staff's default clef, or
  * it sits at or past the end of its bar (a courtesy clef before a system break).

Both checks are deliberately conservative: when the staff default cannot be
established, or a bar's length is unknown, the corresponding check is skipped
rather than guessed, because a wrong guess turns a genuine clef change into a
deletion candidate.
"""

from __future__ import annotations

from typing import Any, Mapping

from ai_score_editing import batch_ops
from ai_score_editing.sibelius import cli


# Sibelius expresses object positions in ticks, where a quarter note is 256.
TICKS_PER_WHOLE = 1024
DEFAULT_METER = (4, 4)

# Instrument-name keywords, matched *before* the vocal-part names below: a name
# like "Tenor Trombone" or "Alto Saxophone" describes the instrument's range,
# not the clef it reads.
INSTRUMENT_CLEF_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    # Alto clef is viola territory (plus the alto trombone).
    (("viola", "alto trombone"), "clef.alto"),
    (("trombone", "tuba", "euphonium", "cello", "bassoon", "contrabass",
      "double bass", "timpani"), "clef.bass"),
    # Winds and strings named for a vocal range still read treble.
    (("saxophone", "sax", "flute", "clarinet", "oboe", "recorder", "trumpet",
      "cornet", "horn", "violin"), "clef.treble"),
)

# Choral / vocal part names.
VOICE_CLEF_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("soprano", "mezzo", "descant", "treble"), "clef.treble"),
    # Choral altos read treble clef -- alto clef is handled above.
    (("alto", "contralto"), "clef.treble"),
    (("tenor",), "clef.treble.down.8"),
    (("baritone", "bass"), "clef.bass"),
)


def bar_length_ticks(numerator: int, denominator: int) -> int:
    """Length of one bar in ticks for the given meter (4/4 is 1024)."""
    if numerator <= 0 or denominator <= 0:
        return 0
    return int(numerator * TICKS_PER_WHOLE / denominator)


def build_meter_map(
    time_signatures: list[dict[str, Any]] | None,
    bar_count: int,
) -> dict[int, int]:
    """Map every bar number to its length in ticks.

    ``GetScoreInfo`` reports time signatures only where they change, so each one
    is carried forward until the next. This replaces an earlier meter-agnostic
    set of "terminal" tick positions, which mistook mid-bar positions in longer
    meters (beat 3 of 4/4 is tick 512) for end-of-bar courtesy clefs.
    """
    changes: dict[int, int] = {}
    for ts in time_signatures or []:
        bar = ts.get("bar")
        numerator = ts.get("numerator")
        denominator = ts.get("denominator")
        if isinstance(bar, int) and numerator and denominator:
            length = bar_length_ticks(int(numerator), int(denominator))
            if length:
                changes[bar] = length

    meter_map: dict[int, int] = {}
    current = changes.get(1, bar_length_ticks(*DEFAULT_METER))
    for bar in range(1, max(int(bar_count), 0) + 1):
        current = changes.get(bar, current)
        meter_map[bar] = current
    return meter_map


def infer_expected_clef(instrument_name: str) -> str | None:
    """Infer a staff's default clef from its instrument name.

    Returns ``None`` when the name supports no confident answer (e.g. "Piano",
    "Organ", or an empty name). Callers must then skip the default-clef
    comparison instead of assuming treble.
    """
    name = (instrument_name or "").strip().lower()
    if not name:
        return None
    for keywords, clef in INSTRUMENT_CLEF_RULES + VOICE_CLEF_RULES:
        if any(keyword in name for keyword in keywords):
            return clef
    return None


def audit_score_clefs(
    bars_data: list[dict[str, Any]],
    staff_num: int = 1,
    default_clef: str | None = None,
    bar_ticks: Mapping[int, int] | None = None,
) -> list[dict[str, Any]]:
    """Audit score bars for redundant clef objects.

    ``default_clef`` is the staff's default clef, or ``None`` when it could not
    be established. ``bar_ticks`` maps bar number to bar length in ticks; bars
    absent from it are not checked for end-of-bar courtesy clefs.

    Returns a list of dicts describing redundant clefs.
    """
    redundant = []
    for bar in bars_data:
        bar_num = bar.get("barNumber", 0)
        bar_end = bar_ticks.get(bar_num) if bar_ticks else None
        for obj in bar.get("objects", []):
            if obj.get("type") != "Clef":
                continue
            style = obj.get("styleId", "")
            pos = obj.get("position", 0)
            idx = obj.get("index", 0)

            reason = ""
            if default_clef and style == default_clef:
                reason = f"Matches staff default ({default_clef})"
            elif bar_end and pos >= bar_end:
                reason = f"Terminal barline artifact at tick {pos} (bar ends at {bar_end})"

            if reason:
                redundant.append({
                    "staff": staff_num,
                    "bar": bar_num,
                    "index": idx,
                    "position": pos,
                    "styleId": style,
                    "reason": reason,
                })
    return redundant


def first_clef_style(bars_data: list[dict[str, Any]]) -> str | None:
    """The styleId of the earliest Clef object in the given bars, if any."""
    clefs = [
        obj
        for bar in bars_data
        for obj in bar.get("objects", [])
        if obj.get("type") == "Clef"
    ]
    if not clefs:
        return None
    earliest = min(clefs, key=lambda obj: obj.get("position", 0))
    style = earliest.get("styleId")
    return str(style) if style else None


async def _staff_default_clef(
    client: Any,
    staff_num: int,
    instrument_name: str,
) -> tuple[str | None, str]:
    """Resolve a staff's default clef, preferring the score over name inference.

    The clef Sibelius draws at the start of bar 1 *is* the staff default, so read
    it rather than guessing. Returns (clef, source-description).
    """
    try:
        bars = await cli._bridge(client, "ReadBars", [staff_num, 1, 1])
    except Exception:  # noqa: BLE001 - fall back to inference on any read failure
        bars = None

    if isinstance(bars, list):
        style = first_clef_style(bars)
        if style:
            return style, "read from bar 1"

    inferred = infer_expected_clef(instrument_name)
    if inferred:
        return inferred, f"inferred from '{instrument_name}'"
    return None, "unknown - default-clef check skipped"


async def find_redundant_clefs(client: Any, staff: int | None = None) -> list[dict[str, Any]]:
    """Return conservative redundant-clef findings for one or all staves."""
    score_info = await cli._bridge(client, "GetScoreInfo")
    staff_count = int(score_info.get("staffCount", 0))
    bar_count = int(score_info.get("barCount", 0))
    meter_map = build_meter_map(score_info.get("timeSignatures"), bar_count)
    target_staves = [staff] if staff and staff > 0 else list(range(1, staff_count + 1))

    staves_info = await cli._bridge(client, "GetStaves")
    instrument_names: dict[int, str] = {}
    staff_bar_counts: dict[int, int] = {}
    for sinfo in staves_info if isinstance(staves_info, list) else []:
        if not isinstance(sinfo, dict):
            continue
        snum = sinfo.get("staffNum", 0)
        instrument_names[snum] = sinfo.get("fullInstrumentName") or sinfo.get("instrumentName") or ""
        if sinfo.get("barCount"):
            staff_bar_counts[snum] = int(sinfo["barCount"])

    findings: list[dict[str, Any]] = []
    for target in target_staves:
        default_clef, _ = await _staff_default_clef(client, target, instrument_names.get(target, ""))
        last_bar = min(bar_count, staff_bar_counts.get(target, bar_count))
        for start_bar in range(1, last_bar + 1, 30):
            end_bar = min(start_bar + 29, last_bar)
            bars = await cli._bridge(client, "ReadBars", [target, start_bar, end_bar])
            findings.extend(
                audit_score_clefs(bars, staff_num=target, default_clef=default_clef, bar_ticks=meter_map)
            )
    return findings


async def delete_redundant_clefs(client: Any, findings: list[dict[str, Any]]) -> int:
    """Delete findings as one checked batch and return the deletion count.

    Each delete is guarded to a Clef, so a stale finding fails the whole batch
    before anything changes. Addresses are resolved before the first delete,
    so their order does not matter.
    """
    addresses = sorted({(f["staff"], f["bar"], f["index"]) for f in findings})
    if not addresses:
        return 0
    batch = batch_ops.validate_batch([
        {"op": "delete", "staff": staff, "bar": bar, "index": index, "type": "Clef"}
        for staff, bar, index in addresses
    ])
    outcome = await cli._apply_batch(client, batch, False)
    if "error" in outcome:
        raise cli.BridgeError(f"clef deletion refused: {outcome['error']}")
    return int(outcome.get("applied", 0))
