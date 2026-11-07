"""Score commands: save, apply, backup, do, add-staff (create-staff), add-bars, set-staff-name,
set-initial-instrument, duplicate-octave-down-to-voice2, set-score-info."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from typing import Any

from ai_score_editing.sibelius import layout
from ai_score_editing.sibelius import batch_ops
from ai_score_editing.core import music
from ai_score_editing.sibelius import service
from ai_score_editing.sibelius.bridge import BRIDGE_PLUGIN, BridgeError
from ai_score_editing.sibelius import bridge, runner
from ai_score_editing.sibelius.commands._common import EXIT_COMMAND_FAILED, EXIT_OK
from ai_score_editing.sibelius.commands._common import emit as _emit

# Curated friendly names -> ManuScript command IDs (see docs/avid-reference.md).
# Note these are fire-and-forget: Sibelius acknowledges receipt but never
# reports whether the command did anything (docs/sibelius-protocol.md 1.2).
NAMED_OPERATIONS = {
    "undo": "undo",
    "redo": "redo",
    "save": "save",
    "select-all": "select_all",
    "select-none": "select_none",
    "delete": "delete",
    "add-bar": "add_bar_at_end",
    "play": "play_from_selection",
    "play-stop": "play/stop",
    "transpose-dialog": "transpose",
}


def register(sub: Any) -> dict[str, Callable[..., Any]]:
    save = sub.add_parser("save", help="save the active score in Sibelius")
    save.add_argument("--path", help="save a copy here (not supported in Sibelius: refused)")
    apply = sub.add_parser(
        "apply",
        help="apply a JSON batch of edits as one undo step (requires bridge plug-in)",
    )
    apply.add_argument("--file", required=True, help="JSON operation array; see the sibelius skill's command reference")
    apply.add_argument("--save", action="store_true", help="save after the batch succeeds")
    apply.add_argument("--dry-run", action="store_true", help="check every operation against the open score without changing it")
    add_staff = sub.add_parser(
        "add-staff",
        aliases=["create-staff"],
        help="add an instrument staff to the score (backs up first)",
    )
    add_staff.add_argument(
        "--instrument",
        "--style",
        dest="instrument",
        help="instrument alias or style ID, e.g. 'soprano', 'piano', 'violin'",
    )
    add_staff.add_argument(
        "--position",
        choices=["bottom", "top", "auto"],
        default="bottom",
        help="where to place the new staff (default: bottom)",
    )
    add_staff.add_argument("--full-name", help="custom full instrument name")
    add_staff.add_argument("--short-name", help="custom short instrument name")
    add_staff.add_argument("--above-staff", type=int, help="add an extra staff above this staff")
    add_staff.add_argument("--below-staff", type=int, help="add an extra staff below this staff")
    add_staff.add_argument("--ossia", action="store_true", help="make the added staff an ossia staff")
    add_staff.add_argument("--save", action="store_true", help="save active score in Sibelius after change")
    add_bars = sub.add_parser(
        "add-bars",
        help="add empty bars to the end of the score (backs up first)",
    )
    add_bars.add_argument("--count", type=int, default=1, help="number of bars to add (default: 1)")
    add_bars.add_argument("--save", action="store_true", help="save active score in Sibelius after change")
    set_staff_name = sub.add_parser(
        "set-staff-name",
        help="set full and short instrument names for a staff (backs up first)",
    )
    set_staff_name.add_argument("--staff", type=int, required=True, help="staff number (from 1)")
    set_staff_name.add_argument("--full", help="full instrument name (e.g. 'Soprano')")
    set_staff_name.add_argument("--short", help="short instrument name (e.g. 'S.')")
    set_staff_name.add_argument("--save", action="store_true", help="save active score in Sibelius after change")
    set_initial_instrument = sub.add_parser(
        "set-initial-instrument",
        help="set a staff's instrument at score start (backs up first)",
    )
    set_initial_instrument.add_argument("--staff", type=int, required=True, help="staff number (from 1)")
    set_initial_instrument.add_argument(
        "--instrument",
        required=True,
        help="instrument alias or style ID, e.g. 'bass' or 'instrument.singers.bass'",
    )
    set_initial_instrument.add_argument("--save", action="store_true", help="save active score in Sibelius after change")
    duplicate_octave_down = sub.add_parser(
        "duplicate-octave-down-to-voice2",
        help="add hidden voice-2 copies of octave-down chord tones (backs up first)",
    )
    duplicate_octave_down.add_argument("--staff", type=int, required=True, help="staff number (from 1)")
    duplicate_octave_down.add_argument("--from-bar", type=int, required=True, help="first bar (from 1)")
    duplicate_octave_down.add_argument("--to-bar", type=int, required=True, help="last bar")
    duplicate_octave_down.add_argument("--save", action="store_true", help="save active score after change")
    set_score_info = sub.add_parser(
        "set-score-info",
        help="set title, composer, and lyricist in Score Info (backs up first)",
    )
    set_score_info.add_argument("--title", help="score title")
    set_score_info.add_argument("--composer", help="composer name")
    set_score_info.add_argument("--lyricist", help="lyricist name")
    set_score_info.add_argument("--save", action="store_true", help="save active score in Sibelius after change")
    backup = sub.add_parser("backup", help="in-file version + save + timestamped file copy")
    backup.add_argument("--name", default="ai-score-editing backup")
    do = sub.add_parser("do", help="run a named operation (curated command IDs)")
    do.add_argument(
        "operation",
        choices=sorted(NAMED_OPERATIONS),
        metavar="operation",
        help=f"one of: {', '.join(sorted(NAMED_OPERATIONS))}",
    )
    return {
        "save": _run_save,
        "apply": _run_apply,
        "backup": _run_backup,
        "do": _run_do,
        "add-staff": _run_add_staff,
        "create-staff": _run_add_staff,
        "add-bars": _run_add_bars,
        "set-staff-name": _run_set_staff_name,
        "set-initial-instrument": _run_set_initial_instrument,
        "duplicate-octave-down-to-voice2": _run_duplicate_octave_down_to_voice2,
        "set-score-info": _run_set_score_info,
    }


async def _run_save(args: argparse.Namespace) -> int:
    async with runner.client(args, plugins=[BRIDGE_PLUGIN]) as client:
        await bridge.check_bridge_version(client)
        await runner.assert_expected_score(client, args)
        saved = await service.save(bridge.for_client(client), getattr(args, "path", None))
    print(json.dumps(saved) if args.json else f"saved: {saved.get('fileName', '')}")
    return EXIT_OK


async def _run_apply(args: argparse.Namespace) -> int:
    try:
        operations = batch_ops.load_batch(args.file)
    except batch_ops.BatchError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_COMMAND_FAILED
    operations, warning = batch_ops.layout_last(operations)
    if warning:
        print(f"warning: {warning}", file=sys.stderr)

    backup = None
    saved = None
    failure: service.BatchFailed | None = None
    try:
        async with runner.client(args, plugins=[BRIDGE_PLUGIN]) as client:
            sb = bridge.for_client(client)
            await bridge.require_bridge(client, bridge.batch_bridge_version(operations), "apply")
            await runner.assert_expected_score(client, args)
            try:
                # Check first so a refused batch neither saves nor backs up.
                result = await service.check(sb, operations)
                if not args.dry_run:
                    result = await service.commit(
                        sb, operations, backup_name="before apply",
                        backup_fn=lambda b, name: runner.backup(b.client, name),
                    )
                    backup = result.get("backup")
            except service.BatchFailed as exc:
                failure, result, backup = exc, exc.result, exc.backup
            if args.save and not args.dry_run and failure is None:
                saved = await service.save(sb)
    except BridgeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_COMMAND_FAILED

    summary: dict[str, Any] = {"operations": len(operations), **result}
    if backup is not None:
        summary["backup"] = backup
    if saved is not None:
        summary["saved"] = saved.get("fileName", "")
    print(layout.compact_summary(summary))
    if failure is not None:
        applied = failure.applied
        hint = (
            "nothing was changed" if not applied
            else f"{applied} op(s) were applied as one undo step; run 'invoke undo' to revert them"
        )
        print(f"error: {result['error']} — {hint}", file=sys.stderr)
        return EXIT_COMMAND_FAILED
    return EXIT_OK




async def _run_do(args: argparse.Namespace) -> int:
    command_id = NAMED_OPERATIONS[args.operation]
    async with runner.client(args) as client:
        response = await client.invoke_commands([command_id])
    return _emit(args, response, f"sent {args.operation} ({command_id})")


async def _run_set_staff_name(args: argparse.Namespace) -> int:
    return await runner.run_write(
        args, "SetStaffName", [args.staff, args.full or "", args.short or ""]
    )


async def _run_set_initial_instrument(args: argparse.Namespace) -> int:
    style_id = music.resolve_instrument_style(args.instrument)
    return await runner.run_write(args, "SetInitialInstrument", [args.staff, style_id])


async def _run_duplicate_octave_down_to_voice2(args: argparse.Namespace) -> int:
    return await runner.run_write(
        args,
        "DuplicateOctaveDownToVoice2",
        [args.staff, args.from_bar, args.to_bar],
    )


async def _run_set_score_info(args: argparse.Namespace) -> int:
    return await runner.run_write(
        args,
        "SetScoreInfo",
        [args.title or "", args.composer or "", args.lyricist or ""],
    )


async def _run_add_staff(args: argparse.Namespace) -> int:
    if getattr(args, "above_staff", None):
        return await runner.run_write(
            args,
            "AddStaffToInstrument",
            [args.above_staff, True, bool(getattr(args, "ossia", False))],
        )
    if getattr(args, "below_staff", None):
        return await runner.run_write(
            args,
            "AddStaffToInstrument",
            [args.below_staff, False, bool(getattr(args, "ossia", False))],
        )
    if not getattr(args, "instrument", None):
        print(
            "error: --instrument is required (unless --above-staff or --below-staff is given)",
            file=sys.stderr,
        )
        return EXIT_COMMAND_FAILED
    style_id = music.resolve_instrument_style(args.instrument)
    return await runner.run_write(
        args,
        "CreateStaff",
        [style_id, args.position, args.full_name or "", args.short_name or ""],
    )


async def _run_add_bars(args: argparse.Namespace) -> int:
    count = getattr(args, "count", 1)
    return await runner.run_op(
        args,
        {"op": "add-bars", "count": count},
        lambda result: {"addedBars": result["after"]["addedBars"], "totalBars": result["after"]["barCount"]},
    )


async def _run_backup(args: argparse.Namespace) -> int:
    async with runner.client(args, plugins=[BRIDGE_PLUGIN]) as client:
        await bridge.check_bridge_version(client)
        await runner.assert_expected_score(client, args)
        result = await runner.backup(client, args.name)
    print(json.dumps(result, indent=2))
    return EXIT_OK
