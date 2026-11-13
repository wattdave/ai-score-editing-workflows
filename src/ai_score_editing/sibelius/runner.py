"""Helpers that run Sibelius commands: client factory, guards, backup and write wrappers.

Command modules call these through the module (``runner.run_op(...)``), so
tests patch ``ai_score_editing.sibelius.runner.<name>`` as the one seam.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from ai_score_editing.cli_common import EXIT_COMMAND_FAILED, EXIT_OK
from ai_score_editing.sibelius import batch_ops, bridge, service
from ai_score_editing.sibelius.bridge import BATCH_BRIDGE_VERSION, BRIDGE_PLUGIN, BridgeError
from ai_score_editing.sibelius.client import SibeliusClient


def client(args: argparse.Namespace, plugins: list[str] | None = None) -> SibeliusClient:
    return SibeliusClient(
        host=args.host,
        port=args.port,
        client_name=args.client_name,
        approval_timeout=args.timeout,
        plugins=plugins,
        launch_if_needed=args.launch,
        launch_timeout=args.launch_timeout,
        app_path=args.sibelius_path,
    )


async def assert_expected_score(
    client: SibeliusClient,
    args: argparse.Namespace,
    info: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Fail before mutation when --expect-file does not name the active score."""
    expected_arg = getattr(args, "expect_file", None)
    if not expected_arg:
        return info
    if info is None:
        info = await bridge.call(client, "GetScoreInfo")
    actual_arg = info.get("fileName") if isinstance(info, dict) else None
    if not actual_arg:
        raise BridgeError("active score has no file path; --expect-file cannot be verified")
    expected = Path(expected_arg).expanduser().resolve()
    actual = Path(actual_arg).expanduser().resolve()
    if actual != expected:
        raise BridgeError(f"active score mismatch: expected {expected}, got {actual}")
    return info


async def backup(client: SibeliusClient, name: str) -> dict[str, Any]:
    """In-file version + save + timestamped copy, into $SIBELIUS_BACKUP_DIR if set.

    Also used by skill scripts; ``main`` exports --backup-dir to the environment.
    """
    return await service.backup(bridge.for_client(client), name, service.backup_folder())


async def backup_and_report(b: bridge.SibeliusBridge, name: str) -> dict[str, Any]:
    made = await backup(b.client, name)
    print(f"backed up: {made['copy']}", file=sys.stderr)
    return made


async def run_write(
    args: argparse.Namespace,
    method: str,
    call_args: list[Any],
    min_bridge: int | None = None,
) -> int:
    """Backup, then run a bridge write method and print its result.

    min_bridge, when given, refuses to run on an older bridge (checked before
    the backup).
    """
    async with client(args, plugins=[BRIDGE_PLUGIN]) as c:
        await bridge.check_bridge_version(c)
        if min_bridge is not None:
            await bridge.require_bridge(c, min_bridge, args.subcommand)
        await assert_expected_score(c, args)
        made = await backup(c, f"before {args.subcommand}")
        print(f"backed up: {made['copy']}", file=sys.stderr)
        result = await bridge.call(c, method, call_args)
        if getattr(args, "save", False):
            # Most write commands have --save but no path argument.
            saved = await service.save(bridge.for_client(c), getattr(args, "path", None))
            print(f"saved: {saved.get('fileName', '')}", file=sys.stderr)
    print(json.dumps(result, indent=2))
    return EXIT_OK


async def run_op(
    args: argparse.Namespace,
    operation: dict[str, Any] | Callable[[SibeliusClient], Awaitable[dict[str, Any]]],
    legacy: Callable[[dict[str, Any]], Any],
    min_bridge: int = BATCH_BRIDGE_VERSION,
    before_write: Callable[[SibeliusClient, list[dict[str, Any]]], Awaitable[Any]] | None = None,
) -> int:
    """Run one edit as a one-operation ApplyBatch.

    The operation is checked against the score before the backup, so a bad
    address fails without saving anything. legacy() maps the batch result to
    the command's historical output shape. An operation that depends on the
    score (such as defaults of "the whole score") is passed as an async
    builder, called once connected. before_write(client, batch) runs after the
    check and returns a report: with --dry-run it is printed and nothing is
    written, otherwise it goes to stderr before the write.
    """
    batch: list[dict[str, Any]] = []
    if isinstance(operation, dict):
        try:
            batch = batch_ops.validate_batch([operation])
        except batch_ops.BatchError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return EXIT_COMMAND_FAILED
    async with client(args, plugins=[BRIDGE_PLUGIN]) as c:
        if not batch:
            try:
                batch = batch_ops.validate_batch([await operation(c)])
            except batch_ops.BatchError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return EXIT_COMMAND_FAILED
        await bridge.require_bridge(c, max(min_bridge, bridge.batch_bridge_version(batch)), args.subcommand)
        await assert_expected_score(c, args)
        sb = bridge.for_client(c)
        try:
            await service.check(sb, batch)
        except service.BatchFailed as exc:
            raise BridgeError(exc.result["error"]) from exc
        report = await before_write(c, batch) if before_write else None
        if getattr(args, "dry_run", False):
            print(json.dumps({"dryRun": True, "checked": len(batch), "preview": report}, indent=2))
            return EXIT_OK
        if report is not None:
            print(json.dumps({"replacing": report}, indent=2), file=sys.stderr)
        try:
            result = await service.commit(
                sb, batch, backup_name=f"before {args.subcommand}", backup_fn=backup_and_report
            )
        except service.BatchFailed as exc:
            raise BridgeError(f"{exc.result['error']}; restore from {exc.backup}") from exc
        if getattr(args, "save", False):
            saved = await service.save(sb)
            print(f"saved: {saved.get('fileName', '')}", file=sys.stderr)
    print(json.dumps(legacy(result["results"][0]), indent=2))
    return EXIT_OK


def address(args: argparse.Namespace) -> dict[str, Any]:
    return {"staff": args.staff, "bar": args.bar, "index": args.index}


def notes(description: dict[str, Any] | None) -> list[dict[str, Any]]:
    return list((description or {}).get("notes", []))


async def read_rows(client: SibeliusClient, staff: int, from_bar: int, to_bar: int) -> list[dict[str, Any]]:
    """Every object of one staff in the bars, as Query reports it."""
    from ai_score_editing.sibelius.query_props import build_selector

    selector = build_selector(
        staves=[staff], from_bar=from_bar, to_bar=to_bar, types=[], voice=None, where=[], fields=[], limit=5000,
    )
    return list((await bridge.call(client, "Query", [selector])).get("objects", []))


def time_signature_at(info: dict[str, Any], bar: int) -> tuple[int, int]:
    found = (4, 4)
    for signature in info.get("timeSignatures", []):
        if signature.get("bar", 1) <= bar:
            found = (signature.get("numerator", 4), signature.get("denominator", 4))
    return found
