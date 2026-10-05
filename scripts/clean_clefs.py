#!/usr/bin/env python3
"""Helper tool for auditing and cleaning redundant clef objects in Sibelius scores.

The detection rules live in ``ai_score_editing.clefs``, shared with the
``remove-redundant-clefs`` operation of ``patch-layout``. This script adds the
audit report and a standalone strip-and-save command.
"""

from __future__ import annotations

import argparse
import asyncio
from collections import defaultdict
import sys

try:
    from ai_score_editing.cli import _bridge, BRIDGE_PLUGIN, _backup
    from ai_score_editing.client import SibeliusClient
    from ai_score_editing.clefs import _staff_default_clef, audit_score_clefs, build_meter_map
    HAVE_CLIENT = True
except ImportError:
    HAVE_CLIENT = False


async def _run_audit_or_strip(staff: int | None, dry_run: bool, is_audit_only: bool) -> int:
    if not HAVE_CLIENT:
        print("error: ai_score_editing required; run with 'uv run python scripts/clean_clefs.py'", file=sys.stderr)
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
