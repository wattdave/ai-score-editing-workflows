#!/usr/bin/env python3
"""Helper tool for auditing and cleaning redundant clef objects in Sibelius scores.

OMR sheet music scanners (e.g. PhotoScore, SmartScore) frequently insert redundant
Clef objects at system breaks across all staves. This script audits and purges
such redundant clefs during score proofreading passes.

A clef is reported as redundant when either:
  * its ``styleId`` matches the staff's default clef, or
  * it sits at or past the end of its bar (a courtesy clef before a system break).

Both checks are deliberately conservative: when the staff default cannot be
established, or a bar's length is unknown, the corresponding check is skipped
rather than guessed, because a wrong guess turns a genuine clef change into a
deletion candidate.
"""

from __future__ import annotations

import argparse
import asyncio
from collections import defaultdict
import sys
from typing import Any, Mapping

try:
    from sibelius_websocket_cli.client import SibeliusClient
    from sibelius_websocket_cli.cli import _bridge, BRIDGE_PLUGIN, _backup
    HAVE_CLIENT = True
except ImportError:
    HAVE_CLIENT = False


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
        bars = await _bridge(client, "ReadBars", [staff_num, 1, 1])
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
    score_info = await _bridge(client, "GetScoreInfo")
    staff_count = int(score_info.get("staffCount", 0))
    bar_count = int(score_info.get("barCount", 0))
    meter_map = build_meter_map(score_info.get("timeSignatures"), bar_count)
    target_staves = [staff] if staff and staff > 0 else list(range(1, staff_count + 1))

    staves_info = await _bridge(client, "GetStaves")
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
            bars = await _bridge(client, "ReadBars", [target, start_bar, end_bar])
            findings.extend(
                audit_score_clefs(bars, staff_num=target, default_clef=default_clef, bar_ticks=meter_map)
            )
    return findings


async def delete_redundant_clefs(client: Any, findings: list[dict[str, Any]]) -> int:
    """Delete findings in reverse index order and return the deletion count."""
    grouped: dict[int, dict[int, list[int]]] = defaultdict(lambda: defaultdict(list))
    for finding in findings:
        grouped[finding["staff"]][finding["bar"]].append(finding["index"])

    deleted_count = 0
    for staff in sorted(grouped):
        for bar in sorted(grouped[staff]):
            for index in sorted(grouped[staff][bar], reverse=True):
                result = await _bridge(client, "DeleteObject", [staff, bar, index])
                if "deleted" in result:
                    deleted_count += 1
    return deleted_count


async def _run_audit_or_strip(staff: int | None, dry_run: bool, is_audit_only: bool) -> int:
    if not HAVE_CLIENT:
        print("error: sibelius_websocket_cli required; run with 'uv run python scripts/clean_clefs.py'", file=sys.stderr)
        return 1

    async with SibeliusClient(plugins=[BRIDGE_PLUGIN]) as client:
        score_info = await _bridge(client, "GetScoreInfo")
        staff_count = score_info.get("staffCount", 16)
        bar_count = score_info.get("barCount", 127)
        meter_map = build_meter_map(score_info.get("timeSignatures"), bar_count)

        target_staves = [staff] if staff and staff > 0 else list(range(1, staff_count + 1))

        # Per-staff instrument names and bar counts.
        staves_info = await _bridge(client, "GetStaves")
        instrument_names: dict[int, str] = {}
        staff_bar_counts: dict[int, int] = {}
        for sinfo in staves_info if isinstance(staves_info, list) else []:
            if not isinstance(sinfo, dict):
                continue
            snum = sinfo.get("staffNum", 0)
            instrument_names[snum] = sinfo.get("fullInstrumentName") or sinfo.get("instrumentName") or ""
            if sinfo.get("barCount"):
                staff_bar_counts[snum] = int(sinfo["barCount"])

        # Collect redundant clefs across the score in batch chunks.
        redundant_clefs = []
        default_clefs: dict[int, tuple[str | None, str]] = {}
        for s in target_staves:
            default_clef, source = await _staff_default_clef(client, s, instrument_names.get(s, ""))
            default_clefs[s] = (default_clef, source)
            last_bar = min(bar_count, staff_bar_counts.get(s, bar_count))
            for start_b in range(1, last_bar + 1, 30):
                end_b = min(start_b + 29, last_bar)
                bars = await _bridge(client, "ReadBars", [s, start_b, end_b])
                clefs = audit_score_clefs(
                    bars, staff_num=s, default_clef=default_clef, bar_ticks=meter_map
                )
                redundant_clefs.extend(clefs)

        if not redundant_clefs:
            print(f"Clean score: no redundant clefs found across {len(target_staves)} target staff/staves.")
            return 0

        print(f"Found {len(redundant_clefs)} redundant clef(s) across {len(target_staves)} staff/staves.")
        staff_counts: dict[int, int] = defaultdict(int)
        for c in redundant_clefs:
            staff_counts[c["staff"]] += 1
        for s in sorted(staff_counts.keys()):
            clef, source = default_clefs.get(s, (None, "unknown"))
            print(f"  • Staff {s}: {staff_counts[s]} redundant clefs (default: {clef or 'unknown'} — {source})")

        if is_audit_only or dry_run:
            print("\nPreview of redundant clefs (first 20):")
            for c in redundant_clefs[:20]:
                print(f"  • Staff {c['staff']} Bar {c['bar']} idx {c['index']}: {c['styleId']} at pos {c['position']} ({c['reason']})")
            if len(redundant_clefs) > 20:
                print(f"  ... and {len(redundant_clefs) - 20} more.")
            if is_audit_only:
                print("\nTo purge these clefs, run: uv run python scripts/clean_clefs.py strip")
            return 0

        # Backup before making changes
        backup = await _backup(client, "before clean_clefs")
        print(f"\nBacked up score to: {backup.get('copy')}")

        # Delete in reverse index order per staff and bar to preserve indices
        grouped: dict[int, dict[int, list[int]]] = defaultdict(lambda: defaultdict(list))
        for c in redundant_clefs:
            grouped[c["staff"]][c["bar"]].append(c["index"])

        deleted_count = 0
        for s in sorted(grouped.keys()):
            for b in sorted(grouped[s].keys()):
                indices = sorted(grouped[s][b], reverse=True)
                for idx in indices:
                    res = await _bridge(client, "DeleteObject", [s, b, idx])
                    if "deleted" in res:
                        deleted_count += 1
                    else:
                        print(f"Warning: could not delete Staff {s} Bar {b} idx {idx}: {res}")

        # Save the score
        saved = await _bridge(client, "Save")
        print(f"Saved score to: {saved.get('fileName')}")
        print(f"Successfully purged {deleted_count} redundant clef(s).")
        return 0


def cmd_audit(args: argparse.Namespace) -> int:
    """Audit redundant clefs across the score."""
    target_staff = int(args.staff) if args.staff and str(args.staff).isdigit() and int(args.staff) > 0 else None
    return asyncio.run(_run_audit_or_strip(staff=target_staff, dry_run=True, is_audit_only=True))


def cmd_strip(args: argparse.Namespace) -> int:
    """Purge redundant clefs across the score."""
    target_staff = int(args.staff) if args.staff and str(args.staff).isdigit() and int(args.staff) > 0 else None
    return asyncio.run(_run_audit_or_strip(staff=target_staff, dry_run=args.dry_run, is_audit_only=False))


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit and clean redundant clef objects in Sibelius scores.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # audit
    p_audit = subparsers.add_parser("audit", help="Report redundant clefs across score without modifying")
    p_audit.add_argument("--staff", default=None, help="Target specific staff number (default: all staves)")
    p_audit.set_defaults(func=cmd_audit)

    # strip
    p_strip = subparsers.add_parser("strip", help="Purge redundant clefs across score with automatic backup and save")
    p_strip.add_argument("--staff", default=None, help="Target specific staff number (default: all staves)")
    p_strip.add_argument("--dry-run", action="store_true", help="Preview deletions without modifying score")
    p_strip.set_defaults(func=cmd_strip)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
