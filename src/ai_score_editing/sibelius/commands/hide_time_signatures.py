"""hide-time-signatures: hide the time signatures the print does not show.

Sibelius ignores ``print-object="no"`` on a MusicXML ``<time>`` and draws the
signature after import (Nelson Carol Book: Lullay My Liking, 53 bars). The hand
fix was ``set Hidden true`` on the system staff's TimeSignature in each bar;
this command finds those objects and hides them in one checked apply batch.
"""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ai_score_editing.core import hidden_time
from ai_score_editing.core.errors import BatchError, QueryError
from ai_score_editing.sibelius import batch_ops, bridge, runner, service
from ai_score_editing.sibelius.bridge import BRIDGE_PLUGIN, BridgeError
from ai_score_editing.sibelius.commands._common import EXIT_COMMAND_FAILED, EXIT_OK
from ai_score_editing.workflows.musicxml_split.io import parse_musicxml

#: Enough for any score; a truncated query is refused rather than half-applied.
QUERY_LIMIT = 5000

DESCRIPTION = """\
Hide time signatures after a MusicXML import. Sibelius ignores print-object="no"
on <time> and draws every such signature; this sets Hidden on the system staff's
TimeSignature objects in the given bars, as one checked apply batch (one undo step).

Bars are Sibelius bars: with --musicxml, the n-th measure of the file is bar n
(a pickup is bar 1). Bars that have no time signature object in Sibelius are
reported, not an error.
"""


def register(sub: Any) -> dict[str, Callable[..., Any]]:
    parser = sub.add_parser(
        "hide-time-signatures",
        help="hide time signatures the print does not show (print-object=\"no\" is lost on import)",
        description=DESCRIPTION,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--bars", help='bars whose time signature to hide, e.g. "2-54" or "1,3-9,12"')
    source.add_argument("--musicxml", help='the imported MusicXML file: hide the bars whose <time> has print-object="no"')
    parser.add_argument("--dry-run", action="store_true", help="check the batch against the open score; change nothing")
    parser.add_argument("--save", action="store_true", help="save after the batch succeeds")
    return {"hide-time-signatures": _run_hide_time_signatures}


def _wanted_bars(args: argparse.Namespace) -> tuple[list[int], list[str]]:
    if args.bars:
        return hidden_time.parse_bars(args.bars), []
    path = Path(args.musicxml).expanduser()
    try:
        _, root = parse_musicxml(path)
    except (OSError, ValueError, SyntaxError, zipfile.BadZipFile) as exc:  # ET.ParseError is a SyntaxError
        raise BatchError(f"cannot read {path}: {exc}") from exc
    bars, mixed = hidden_time.hidden_time_bars(root)
    notes = []
    if mixed:
        notes.append(f"bars {hidden_time.compact_bars(mixed)}: one part hides the time signature and another "
                     "prints it; hidden (Sibelius has one per bar), check the print")
    return bars, notes


async def _run_hide_time_signatures(args: argparse.Namespace) -> int:
    try:
        bars, notes = _wanted_bars(args)
    except BatchError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_COMMAND_FAILED
    if not bars:
        print(json.dumps({"hide": 0, "notes": ["no time signature in the file has print-object=\"no\""]},
                         separators=(",", ":")))
        return EXIT_OK

    try:
        async with runner.client(args, plugins=[BRIDGE_PLUGIN]) as client:
            sb = bridge.for_client(client)
            try:
                found = await service.query(
                    sb, staves=["0"], from_bar=bars[0], to_bar=bars[-1], types=["TimeSignature"],
                    fields=["Hidden"], limit=QUERY_LIMIT,
                )
            except QueryError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return EXIT_COMMAND_FAILED
            if found.get("truncated"):
                print("error: too many time signatures to read at once; pass a narrower --bars", file=sys.stderr)
                return EXIT_COMMAND_FAILED
            plan = hidden_time.plan_hide(found.get("objects", []), bars)
            summary: dict[str, Any] = plan.summary()
            if notes:
                summary["notes"] = notes
            if not plan.batch:
                print(json.dumps({**summary, "applied": 0}, separators=(",", ":")))
                return EXIT_OK
            try:
                batch = batch_ops.validate_batch(plan.batch)
            except BatchError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return EXIT_COMMAND_FAILED
            await bridge.require_bridge(client, bridge.batch_bridge_version(batch), "hide-time-signatures")
            await runner.assert_expected_score(client, args)
            try:
                checked = await service.check(sb, batch)
            except service.BatchFailed as exc:
                print(f"error: {exc.result.get('error')} (nothing was changed)", file=sys.stderr)
                return EXIT_COMMAND_FAILED
            if args.dry_run:
                print(json.dumps({**summary, "dryRun": True, "checked": len(batch), "batch": plan.batch,
                                  "check": checked}, separators=(",", ":")))
                return EXIT_OK
            try:
                result = await service.commit(
                    sb, batch, backup_name="before hide-time-signatures",
                    backup_fn=lambda b, name: runner.backup(b.client, name),
                )
            except service.BatchFailed as exc:
                undo = "run 'invoke undo' once" if exc.applied else "nothing was applied"
                print(f"error: {exc.result.get('error')}; {undo}, or restore {exc.backup}", file=sys.stderr)
                return EXIT_COMMAND_FAILED
            summary["applied"] = result.get("applied")
            summary["backup"] = result.get("backup")
            if args.save:
                saved = await service.save(sb)
                summary["saved"] = saved.get("fileName", "")
    except BridgeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_COMMAND_FAILED
    print(json.dumps(summary, separators=(",", ":")))
    return EXIT_OK
