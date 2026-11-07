"""auto-layout: lay out an imported score like its print in one command.

Replaces the hand recipe of the Nelson Carol Book run (references/
import-and-layout-recipes.md): Unlock Format on the whole score, a system or
page break before each printed system, hide-empty-staves ranges, then
set-layout last with values from the staves x verses table in
``core.page_layout``.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ai_score_editing.core import page_layout
from ai_score_editing.core.errors import BatchError
from ai_score_editing.sibelius import batch_ops, bridge, protocol, runner, service
from ai_score_editing.sibelius.bridge import BRIDGE_PLUGIN, BridgeError
from ai_score_editing.sibelius.commands._common import EXIT_COMMAND_FAILED, EXIT_OK

#: Select All, Layout > Format > Unlock Format, then clear the selection.
UNLOCK_FORMAT = ["select_all", "unlock_format", "select_none"]

DESCRIPTION = """\
Lay out the open score like its print: system and page breaks where the print's
systems start, hide-empty-staves ranges, and set-layout values chosen from the
number of staves and lyric verses (the Nelson Carol Book table). The edits run as
one checked apply batch with set-layout last.

By default the whole score is first unlocked with Select All + Layout > Format >
Unlock Format (--unlock-format). That CLEARS MANUAL FORMATTING: every imported
or hand-made system and page break and every locked bar layout goes, so only the
breaks given here remain. It is a separate undo step from the batch. Pass
--no-unlock-format to keep the existing formatting.

Bar numbers are as printed. With --pickup (or a ready.json that mentions one)
the print numbers the pickup 0, so printed bar N is score bar N+1.
"""


def register(sub: Any) -> dict[str, Callable[..., Any]]:
    parser = sub.add_parser(
        "auto-layout",
        help="lay out the score like its print: unlock format, breaks, hidden staves, set-layout last",
        description=DESCRIPTION,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--systems",
        help='bars where the print\'s systems start, pages separated by "/", e.g. "1,5,9/13,17,21" '
        "(bar 1 may be left out)",
    )
    source.add_argument("--ready", help="ready.json whose breaks and page_breaks describe the print's systems")
    parser.add_argument("--verses", type=int, required=True, help="number of lyric verse rows (0 if none)")
    parser.add_argument("--staves", type=int, help="number of staves (default: read from the open score)")
    parser.add_argument(
        "--hide-empty", action="append", default=[], metavar="A-B",
        help="hide-empty-staves over printed bars A-B (repeatable)",
    )
    parser.add_argument(
        "--pickup", action=argparse.BooleanOptionalAction, default=None,
        help="the print numbers a pickup bar 0 (default: off, or from --ready)",
    )
    parser.add_argument(
        "--layout", action="append", default=[], metavar="NAME=VALUE",
        help="override a set-layout value, e.g. staffSize=5.5 (repeatable)",
    )
    parser.add_argument(
        "--unlock-format", action=argparse.BooleanOptionalAction, default=True,
        help="first run Select All + Unlock Format, which clears manual formatting: all existing "
        "system/page breaks and locked layout (default: on)",
    )
    parser.add_argument(
        "--out",
        help="write the apply batch JSON here ('-' for stdout) and stop without connecting; needs --staves. "
        "Run 'invoke select_all unlock_format select_none' and 'apply --file' yourself",
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="check the batch against the open score; unlock nothing, change nothing")
    parser.add_argument("--verify", action="store_true",
                        help="after the layout, read each bar's page and system and compare with the print")
    parser.add_argument("--pdf", help="after the layout, export a PDF here and report its page count")
    parser.add_argument("--save", action="store_true", help="save after the layout succeeds")
    return {"auto-layout": _run_auto_layout}


def _inputs(args: argparse.Namespace) -> tuple[list[list[int]], int, list[str]]:
    notes: list[str] = []
    offset = 0
    if args.ready:
        path = Path(args.ready).expanduser()
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise BatchError(f"cannot read {path}: {exc}") from exc
        if not isinstance(data, dict):
            raise BatchError(f"{path} must hold a JSON object")
        pages, offset, notes = page_layout.pages_from_ready(data)
    else:
        pages = page_layout.parse_systems(args.systems)
    if args.pickup is not None:
        offset = 1 if args.pickup else 0
        notes = [n for n in notes if "pickup" not in n]
    return pages, offset, notes


def _plan(args: argparse.Namespace, staves: int, pages: list[list[int]], offset: int,
          notes: list[str]) -> page_layout.Plan:
    plan = page_layout.plan(
        pages,
        verses=args.verses,
        staves=staves,
        hide=[page_layout.parse_range(r) for r in args.hide_empty],
        overrides=page_layout.parse_overrides(args.layout),
        offset=offset,
    )
    plan.notes[:0] = notes
    # Same validation apply uses, so the file is accepted by 'apply --file'.
    batch_ops.validate_batch(plan.batch)
    return plan


def _write_batch(args: argparse.Namespace, plan: page_layout.Plan) -> int:
    text = json.dumps(plan.batch, indent=1)
    summary = {**plan.summary(), "unlockFormat": args.unlock_format}
    steps = []
    if args.unlock_format:
        steps.append(f"sibelius-cli invoke {' '.join(UNLOCK_FORMAT)}")
    steps.append(f"sibelius-cli apply --file {args.out if args.out != '-' else 'BATCH.json'}")
    summary["next"] = steps
    if args.out == "-":
        print(text)
        print(json.dumps(summary, separators=(",", ":")), file=sys.stderr)
        return EXIT_OK
    Path(args.out).expanduser().write_text(text + "\n")
    print(json.dumps({"written": args.out, **summary}, separators=(",", ":")))
    return EXIT_OK


async def _run_auto_layout(args: argparse.Namespace) -> int:
    try:
        pages, offset, notes = _inputs(args)
        if args.out:
            if args.staves is None:
                raise BatchError("--out does not read the score, so it needs --staves")
            return _write_batch(args, _plan(args, args.staves, pages, offset, notes))
        if args.staves is not None:
            _plan(args, args.staves, pages, offset, notes)  # fail on bad input before connecting
    except BatchError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_COMMAND_FAILED

    try:
        async with runner.client(args, plugins=[BRIDGE_PLUGIN]) as client:
            sb = bridge.for_client(client)
            staves = args.staves
            if staves is None:
                staves = len(await bridge.call(client, "GetStaves"))
            try:
                plan = _plan(args, staves, pages, offset, notes)
            except BatchError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return EXIT_COMMAND_FAILED
            # The same validation apply does: it names the set-layout settings
            # ("settings") and turns page size words into the plug-in's indexes;
            # without it the plug-in fails in BatchHasSetting.
            try:
                batch, _ = batch_ops.layout_last(batch_ops.validate_batch(plan.batch))
            except BatchError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return EXIT_COMMAND_FAILED
            await bridge.require_bridge(client, bridge.batch_bridge_version(batch), "auto-layout")
            await runner.assert_expected_score(client, args)
            summary: dict[str, Any] = {**plan.summary(), "unlockFormat": args.unlock_format}
            try:
                # Check first, so a refused batch neither unlocks nor backs up.
                checked = await service.check(sb, batch)
            except service.BatchFailed as exc:
                print(f"error: {exc.result.get('error')} (nothing was changed)", file=sys.stderr)
                return EXIT_COMMAND_FAILED
            if args.dry_run:
                print(json.dumps({**summary, "dryRun": True, "checked": len(plan.batch),
                                  "batch": plan.batch, "check": checked}, separators=(",", ":")))
                return EXIT_OK
            made = await runner.backup(client, "before auto-layout")
            print(f"backed up: {made['copy']}", file=sys.stderr)
            summary["backup"] = made.get("copy")
            if args.unlock_format:
                response = await client.invoke_commands(UNLOCK_FORMAT)
                if not protocol.is_success(response):
                    print(f"error: unlock_format failed: {json.dumps(response)}; nothing else was changed",
                          file=sys.stderr)
                    return EXIT_COMMAND_FAILED

            async def same_backup(_b: Any, _name: str) -> dict[str, Any]:
                return made

            try:
                result = await service.commit(sb, batch, backup_name="before auto-layout",
                                              backup_fn=same_backup)
            except service.BatchFailed as exc:
                undo = "run 'invoke undo' once for the batch" if exc.applied else "nothing in the batch was applied"
                if args.unlock_format:
                    undo += " and once more for Unlock Format"
                print(f"error: {exc.result.get('error')}; {undo}, or restore {made.get('copy')}", file=sys.stderr)
                return EXIT_COMMAND_FAILED
            summary["applied"] = result.get("applied")
            ok = True
            if args.verify:
                ok = await _verify(sb, plan, summary)
            if args.pdf:
                ok = _pdf(await service.export(sb, "pdf", args.pdf), plan, summary) and ok
            if args.save:
                saved = await service.save(sb)
                summary["saved"] = saved.get("fileName", "")
    except BridgeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_COMMAND_FAILED
    print(json.dumps(summary, separators=(",", ":")))
    return EXIT_OK if ok else EXIT_COMMAND_FAILED


async def _verify(sb: bridge.SibeliusBridge, plan: page_layout.Plan, summary: dict[str, Any]) -> bool:
    """Read each bar's page and system (system staff) and compare with the plan."""
    found = await service.query(sb, staves=["0"], types=["Bar"], fields=["OnNthPage", "OnNthSystem"], limit=5000)
    try:
        actual = page_layout.actual_pages(found.get("objects", []))
    except BatchError as exc:
        summary["verify"] = {"verified": False, "errors": [str(exc)]}
        return False
    problems = page_layout.compare_pages(plan.pages, actual)
    summary["verify"] = {"verified": not problems, "systemStarts": actual}
    if problems:
        summary["verify"]["errors"] = problems
    return not problems


def _pdf(exported: dict[str, Any], plan: page_layout.Plan, summary: dict[str, Any]) -> bool:
    path = Path(exported["files"][0])
    pages = page_layout.count_pdf_pages(path.read_bytes())
    summary["pdf"] = {"path": str(path), "pages": pages}
    if pages is not None and pages != len(plan.pages):
        summary["pdf"]["error"] = f"{pages} page(s), expected {len(plan.pages)}"
        return False
    return True
