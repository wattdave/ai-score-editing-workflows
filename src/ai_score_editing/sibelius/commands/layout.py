"""Layout commands: patch-layout, set-break, set-barline, set-time, set-key, reset-design,
play-order, play-on-pass, read-barlines."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from typing import Any

from ai_score_editing import batch_ops, layout
from ai_score_editing.barrange import parse_bar_range
from ai_score_editing.sibelius import protocol, repeats
from ai_score_editing.sibelius.bridge import (
    BATCH_BRIDGE_VERSION,
    BRIDGE_PLUGIN,
    REPEATS_BRIDGE_VERSION,
    BridgeError,
)
from ai_score_editing.sibelius.clefs import delete_redundant_clefs, find_redundant_clefs
from ai_score_editing.sibelius.commands._common import EXIT_COMMAND_FAILED, EXIT_OK
from ai_score_editing.sibelius.commands._common import client as _client
from ai_score_editing.sibelius.commands._common import cli as _cli
from ai_score_editing.sibelius.commands._common import emit as _emit



def register(sub: Any) -> dict[str, Callable[..., Any]]:
    patch_layout = sub.add_parser(
        "patch-layout",
        help="apply and verify a validated JSON batch of layout corrections",
    )
    patch_layout.add_argument("--file", required=True, help="JSON layout operation array")
    patch_layout.add_argument("--save", action="store_true", help="save after all operations complete")
    patch_layout.add_argument("--dry-run", action="store_true", help="validate and report without connecting or mutating")
    set_key = sub.add_parser("set-key", help="add a key signature (backs up first)")
    set_key.add_argument("--bar", type=int, default=1)
    set_key.add_argument("--key", required=True, help='key name, e.g. D or Bb')
    set_key.add_argument("--minor", action="store_true")
    set_key.add_argument("--save", action="store_true", help="save active score in Sibelius after change")
    set_time = sub.add_parser("set-time", help="add a time signature (backs up first)")
    set_time.add_argument("--bar", type=int, default=1)
    set_time.add_argument("--top", type=int, required=True)
    set_time.add_argument("--bottom", type=int, required=True)
    set_time.add_argument("--symbol", choices=["common", "cut"], help="draw 4/4 as common time or 2/2 as cut time")
    set_time.add_argument("--save", action="store_true", help="save active score in Sibelius after change")
    reset_d = sub.add_parser(
        "reset-design",
        help="reset design/formatting overrides (e.g. font styles) on score objects",
    )
    reset_d.add_argument("--lyrics", action="store_true", help="filter to lyrics only")
    reset_d.add_argument("--save", action="store_true", help="save active score in Sibelius after resetting design")
    set_break = sub.add_parser(
        "set-break",
        help="set system or page break at a bar (backs up first)",
    )
    set_break.add_argument("--bar", type=int, required=True, help="bar number (from 1)")
    set_break.add_argument(
        "--type",
        choices=["system", "page", "none"],
        default="system",
        help="break type: system, page, or none to clear an existing break (default: system)",
    )
    set_break.add_argument("--save", action="store_true", help="save active score in Sibelius after change")
    set_barline = sub.add_parser(
        "set-barline",
        help="set or change special barline at a bar (backs up first)",
    )
    set_barline.add_argument("--bar", type=int, required=True, help="bar number (from 1)")
    set_barline.add_argument(
        "--type",
        choices=[
            "double", "start_repeat", "end_repeat", "final", "dashed",
            "invisible", "between_staves", "normal", "tick", "short",
            "dotted", "triple", "thick", "none",
        ],
        default="double",
        help="barline type (default: double)",
    )
    set_barline.add_argument("--save", action="store_true", help="save active score in Sibelius after change")
    play_order = sub.add_parser(
        "play-order",
        help="read or set the playback roadmap (Play > Interpretation > Repeats, manual repeats playback)",
    )
    play_order.add_argument(
        "order", nargs="?",
        help="bars in the order they play, e.g. '1-12, 1-12, 1-12'; 'auto' returns to automatic repeats playback; "
        "omit to read the current order",
    )
    play_order.add_argument("--save", action="store_true", help="save active score in Sibelius after change")
    play_on_pass = sub.add_parser(
        "play-on-pass",
        help="read or set Inspector > Playback > Play on pass (1-8) on a barline",
    )
    play_on_pass.add_argument("--bar", type=int, required=True, help="bar number (from 1) holding the barline")
    play_on_pass.add_argument(
        "--passes",
        help="passes that play, e.g. '1-3' or '1,3' ('none' for no pass, 'all' for 1-8); the rest are cleared. "
        "Omit to read the barline's checkboxes",
    )
    play_on_pass.add_argument(
        "--type", default="end_repeat",
        choices=["start_repeat", "end_repeat", "double", "final", "dashed", "invisible", "between_staves",
                 "tick", "short", "dotted", "triple", "thick"],
        help="which barline in the bar to change (default: %(default)s)",
    )
    play_on_pass.add_argument("--position", type=int, help="barline position in the bar (1/256 quarters), if several match")
    play_on_pass.add_argument("--save", action="store_true", help="save active score in Sibelius after change")
    read_barlines = sub.add_parser(
        "read-barlines",
        help="read special barlines in a bar or range",
    )
    read_barlines.add_argument("--bar", type=int, help="specific bar number")
    read_barlines.add_argument("--bars", help="bar range, e.g. '1-10'")
    read_barlines.add_argument("--from", dest="from_bar", type=int, help="first bar")
    read_barlines.add_argument("--to", dest="to_bar", type=int, help="last bar")
    return {
        "patch-layout": _run_patch_layout,
        "set-break": _run_set_break,
        "set-barline": _run_set_barline,
        "set-time": _run_set_time,
        "set-key": _run_set_key,
        "reset-design": _run_reset_design,
        "play-order": _run_play_order,
        "play-on-pass": _run_play_on_pass,
        "read-barlines": _run_read_barlines,
    }


async def _run_reset_design(args: argparse.Namespace) -> int:
    commands = ["select_all"]
    if getattr(args, "lyrics", False):
        commands.append("filter_lyrics")
    commands.append("reset_design")
    commands.append("select_none")

    async with _client(args, plugins=[BRIDGE_PLUGIN]) as client:
        await _cli._check_bridge_version(client)
        await _cli._assert_expected_score(client, args)
        backup = await _cli._backup(client, f"before {args.subcommand}")
        print(f"backed up: {backup['copy']}", file=sys.stderr)
        response = await client.invoke_commands(commands)
        if not protocol.is_success(response):
            print(f"error resetting design: {json.dumps(response)}", file=sys.stderr)
            return EXIT_COMMAND_FAILED
        if getattr(args, "save", False):
            saved = await _cli._bridge(client, "Save")
            print(f"saved: {saved.get('fileName', '')}", file=sys.stderr)
    return _emit(
        args,
        response,
        f"reset design ({'lyrics' if getattr(args, 'lyrics', False) else 'all'})",
    )


_LAYOUT_BATCHED = {"nudge", "set-break", "set-barline", "set-time"}


def _layout_batch_op(operation: dict[str, Any]) -> dict[str, Any]:
    """Translate a patch-layout operation into an ApplyBatch operation."""
    op = operation["op"]
    if op == "nudge":
        return {"op": op, "staff": operation["staff"], "bar": operation["bar"],
                "index": operation["index"], "dx": operation.get("dx", 0), "dy": operation.get("dy", 0)}
    if op == "set-break":
        return {"op": op, "bar": operation["bar"], "type": operation.get("type", "system")}
    if op == "set-barline":
        return {"op": op, "bar": operation["bar"], "type": operation.get("type", "double")}
    out = {"op": op, "bar": operation["bar"], "numerator": operation["top"], "denominator": operation["bottom"]}
    if operation.get("symbol"):
        out["symbol"] = operation["symbol"]
    return out


def _legacy_layout(operation: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """Map a batch result to what the retired single-purpose handlers returned."""
    if operation["op"] == "set-barline":
        barline = after["barlineType"]
        # SetSpecialBarline reported 'none' and 'normal' as SpecialBarlineNormal.
        return {"bar": after["bar"], "deleted": after["removed"], "barlineType": "7" if barline == "-1" else barline}
    if operation["op"] == "set-time":
        meter = (after["numerator"], after["denominator"])
        style = "numeric"
        if operation.get("symbol"):
            style = {(4, 4): "common", (2, 2): "cut"}.get(meter, "numeric")
        return {"bar": after["bar"], "numerator": after["numerator"],
                "denominator": after["denominator"], "style": style}
    return after


async def _run_patch_layout(args: argparse.Namespace) -> int:
    try:
        operations = layout.load_layout_patches(args.file)
    except layout.LayoutPatchError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_COMMAND_FAILED

    if args.dry_run:
        print(layout.compact_summary({"operations": len(operations), "validated": True, "dryRun": True}))
        return EXIT_OK

    results: list[dict[str, Any]] = []
    batchable = [_layout_batch_op(o) for o in operations if o["op"] in _LAYOUT_BATCHED]
    try:
        for operation in batchable:
            batch_ops.validate_batch([operation])
    except batch_ops.BatchError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_COMMAND_FAILED
    async with _client(args, plugins=[BRIDGE_PLUGIN]) as client:
        await _cli._check_bridge_version(client)
        if batchable:
            await _cli._require_bridge(client, _cli._batch_bridge_version(batchable), "patch-layout")
        elif any(operation["op"] == "remove-redundant-clefs" for operation in operations):
            await _cli._require_bridge(client, BATCH_BRIDGE_VERSION, "patch-layout remove-redundant-clefs")
        await _cli._assert_expected_score(client, args)
        backup = await _cli._backup(client, "before patch-layout")
        pending: list[dict[str, Any]] = []

        async def flush() -> None:
            # A run of batchable operations is one checked batch and one undo
            # step; a new batch starts where the ordering rules require it.
            if not pending:
                return
            batch = batch_ops.validate_batch(pending)
            outcome = await _cli._apply_batch(client, batch, False)
            if "error" in outcome:
                raise BridgeError(
                    f"patch-layout batch failed: {outcome['error']}; restore from {backup.get('copy')}"
                )
            for operation, result in zip(batch, outcome["results"]):
                results.append({
                    "op": operation["op"], "result": _legacy_layout(operation, result["after"]),
                    "verified": True,
                })
            pending.clear()

        for operation in operations:
            op = operation["op"]
            operation_verified = True
            if op in _LAYOUT_BATCHED:
                candidate = _layout_batch_op(operation)
                try:
                    batch_ops.validate_batch([*pending, candidate])
                except batch_ops.BatchError:
                    await flush()
                pending.append(candidate)
                continue
            await flush()
            if op == "remove-redundant-clefs":

                target_staff = operation.get("staff")
                findings = await find_redundant_clefs(client, target_staff)
                deleted = await delete_redundant_clefs(client, findings)
                remaining = await find_redundant_clefs(client, target_staff)
                operation_verified = not remaining
                result = {
                    "found": len(findings),
                    "deleted": deleted,
                    "remaining": len(remaining),
                    "staff": target_staff,
                }
                if not operation_verified:
                    raise BridgeError(f"remove-redundant-clefs left {len(remaining)} finding(s)")
            else:  # reset-design
                commands = ["select_all"]
                if operation.get("lyrics", False):
                    commands.append("filter_lyrics")
                commands.extend(["reset_design", "select_none"])
                response = await client.invoke_commands(commands)
                if not protocol.is_success(response):
                    raise BridgeError(f"reset-design failed: {json.dumps(response)}")
                result = {"commands": commands, "ok": True}
            results.append({"op": op, "result": result, "verified": operation_verified})
        await flush()

        saved = None
        if args.save:
            saved = await _cli._bridge(client, "Save")

    summary = {
        "operations": len(operations),
        "verified": len(results),
        "backup": backup.get("copy"),
        "results": results,
    }
    if saved is not None:
        summary["saved"] = saved.get("fileName", "")
    print(layout.compact_summary(summary))
    return EXIT_OK


async def _run_set_key(args: argparse.Namespace) -> int:
    key = args.key[:1].upper() + args.key[1:]
    return await _cli._run_op(
        args,
        {"op": "set-key", "bar": args.bar, "key": key, "minor": args.minor},
        lambda result: result["after"],
    )


async def _run_set_time(args: argparse.Namespace) -> int:
    operation = {"op": "set-time", "bar": args.bar, "numerator": args.top, "denominator": args.bottom}
    if args.symbol:
        operation["symbol"] = args.symbol
    return await _cli._run_op(
        args, operation, lambda result: _legacy_layout({"op": "set-time", "symbol": args.symbol}, result["after"])
    )


async def _run_set_break(args: argparse.Namespace) -> int:
    return await _cli._run_op(
        args, {"op": "set-break", "bar": args.bar, "type": args.type}, lambda result: result["after"]
    )


async def _run_set_barline(args: argparse.Namespace) -> int:
    return await _cli._run_op(
        args,
        {"op": "set-barline", "bar": args.bar, "type": args.type},
        lambda result: _legacy_layout({"op": "set-barline"}, result["after"]),
    )


async def _run_read_barlines(args: argparse.Namespace) -> int:
    from_b, to_b = parse_bar_range(
        bar=getattr(args, "bar", None),
        bars=getattr(args, "bars", None),
        from_bar=getattr(args, "from_bar", None),
        to_bar=getattr(args, "to_bar", None),
    )
    if from_b is None:
        from_b = 1
    if to_b is None:
        to_b = from_b
    return await _cli._run_bridge_call(args, "GetSpecialBarlines", [from_b, to_b])


def _read_order(result: dict[str, Any]) -> list[int] | None:
    try:
        return repeats.parse_bar_order(str(result.get("order", "")))
    except ValueError:
        return None


async def _run_play_order(args: argparse.Namespace) -> int:
    if args.order is None:
        async with _client(args, plugins=[BRIDGE_PLUGIN]) as client:
            await _cli._require_bridge(client, REPEATS_BRIDGE_VERSION, "play-order")
            result = await _cli._bridge(client, "GetPlayOrder")
        print(json.dumps(result, indent=2))
        return EXIT_OK
    try:
        bars = None if args.order.strip().lower() == "auto" else repeats.parse_bar_order(args.order)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_COMMAND_FAILED
    async with _client(args, plugins=[BRIDGE_PLUGIN]) as client:
        await _cli._require_bridge(client, REPEATS_BRIDGE_VERSION, "play-order")
        await _cli._assert_expected_score(client, args)
        before = await _cli._bridge(client, "GetPlayOrder")
        if bars is not None and (bad := [n for n in bars if n > before["barCount"]]):
            print(f"error: bar {bad[0]} is outside the score ({before['barCount']} bars)", file=sys.stderr)
            return EXIT_COMMAND_FAILED
        backup = await _cli._backup(client, f"before {args.subcommand}")
        print(f"backed up: {backup['copy']}", file=sys.stderr)
        result = await _cli._bridge(client, "SetPlayOrder", [bars])
        if bars is not None and _read_order(result) != bars:
            # Assigning the array did not take; try the dialog's own text form.
            result = await _cli._bridge(client, "SetPlayOrderText", [repeats.format_bar_order(bars)])
            if _read_order(result) != bars:
                print(f"error: Sibelius reports the order {result.get('order')!r}, not the requested one",
                      file=sys.stderr)
                return EXIT_COMMAND_FAILED
        if getattr(args, "save", False):
            saved = await _cli._bridge(client, "Save")
            print(f"saved: {saved.get('fileName', '')}", file=sys.stderr)
    print(json.dumps({"before": before, "after": result}, indent=2))
    return EXIT_OK


async def _run_play_on_pass(args: argparse.Namespace) -> int:
    if args.passes is None:
        return await _cli._run_bridge_call(args, "GetPlayOnPass", [args.bar])
    try:
        if args.passes.strip().lower() == "all":
            passes = list(range(1, repeats.MAX_PASS + 1))
        else:
            passes = repeats.parse_passes(args.passes)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_COMMAND_FAILED
    async with _client(args, plugins=[BRIDGE_PLUGIN]) as client:
        await _cli._require_bridge(client, REPEATS_BRIDGE_VERSION, "play-on-pass")
        await _cli._assert_expected_score(client, args)
        backup = await _cli._backup(client, f"before {args.subcommand}")
        print(f"backed up: {backup['copy']}", file=sys.stderr)
        result = await _cli._bridge(client, "SetPlayOnPass", [args.bar, args.type, passes, args.position])
        if getattr(args, "save", False):
            saved = await _cli._bridge(client, "Save")
            print(f"saved: {saved.get('fileName', '')}", file=sys.stderr)
    print(json.dumps(result, indent=2))
    return EXIT_OK
