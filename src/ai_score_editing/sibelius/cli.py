"""Command-line interface (docs/sibelius-protocol.md 2.2)."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from collections.abc import Awaitable, Callable
from inspect import isawaitable
from pathlib import Path
from typing import Any

from ai_score_editing import (
    batch_ops,
    lyrics,  # noqa: F401  (tests patch cli.lyrics.*)
)
from ai_score_editing.barrange import parse_bar_range  # noqa: F401  (re-exported)
from ai_score_editing.cli_common import (  # noqa: F401  (re-exported)
    DEFAULT_LIMIT,
    EXIT_COMMAND_FAILED,
    EXIT_CONNECTION_FAILED,
    EXIT_OK,
    canonical_format,
)
from ai_score_editing.sibelius import bridge, protocol, service
from ai_score_editing.sibelius.bridge import (  # noqa: F401  (re-exported for skill scripts and tests)
    BRIDGE_PLUGIN,
    EXPORT_FORMATS,
    BridgeBusy,
    BridgeError,
    batch_bridge_version,
    MIN_BRIDGE_VERSION,
    CURRENT_BRIDGE_VERSION,
    QUERY_BRIDGE_VERSION,
    BATCH_BRIDGE_VERSION,
    NUDGE_BRIDGE_VERSION,
    STRUCTURAL_BRIDGE_VERSION,
    STRUCTURE_READ_BRIDGE_VERSION,
    BEAM_RESULT_BRIDGE_VERSION,
    SYSTEM_STAFF_BRIDGE_VERSION,
    LAYOUT_BATCH_BRIDGE_VERSION,
    HIDE_EMPTY_STAVES_BRIDGE_VERSION,
    AUDIO_EXPORT_BRIDGE_VERSION,
    PLAYBACK_SOUNDS_BRIDGE_VERSION,
    DELETE_BARS_BRIDGE_VERSION,
    REPEATS_BRIDGE_VERSION,
    LYRIC_VERSE_BRIDGE_VERSION,
    SET_LYRIC_VERSE_BRIDGE_VERSION,
    TUPLET_NOTES_BRIDGE_VERSION,
    TEXT_FONTS_BRIDGE_VERSION,
    QUERY_CONTAINERS_BRIDGE_VERSION,
)
from ai_score_editing.sibelius import commands
from ai_score_editing.sibelius.commands import _common
from ai_score_editing.sibelius.commands.connection import (  # noqa: F401  (re-exported for tests)
    _run_command,
    _run_forget_token,
    _run_install_plugin,
    _run_invoke,
    _run_ping,
    _run_plugin,
    _run_raw,
    _run_repl,
)
from ai_score_editing.sibelius.commands.inspect import (  # noqa: F401  (re-exported for tests)
    _run_bridge_call,
    _run_bridge_version,
    _run_inspect,
    _run_proofread,
    _run_query,
    _run_read,
    _run_score_info,
    _run_score_snapshot,
    _run_selection,
    _run_staves,
    _run_text_styles,
)
from ai_score_editing.sibelius.commands.notes import (  # noqa: F401  (re-exported for tests)
    _run_add_abc,
    _run_add_notes,
    _run_beam,
    _run_bracket,
    _run_clear_bars,
    _run_copy_passage,
    _run_delete_object,
    _run_delete_voice,
    _run_flip_stem,
    _run_nudge,
    _run_patch_notes,
    _run_set_note,
    _run_tie,
    _run_transpose,
)
from ai_score_editing.sibelius.commands.layout import (  # noqa: F401  (re-exported for tests)
    _run_patch_layout,
    _run_play_on_pass,
    _run_play_order,
    _run_read_barlines,
    _run_reset_design,
    _run_set_barline,
    _run_set_break,
    _run_set_key,
    _run_set_time,
)
from ai_score_editing.sibelius.commands.audio import (  # noqa: F401  (re-exported for tests)
    _parse_staff_names,
    _print_playback_sounds,
    _run_playback_sounds,
    _run_proof_mixes,
    _run_rehearsal_mixes,
    _run_verify_render,
)
from ai_score_editing.sibelius.commands.musicxml import (  # noqa: F401  (re-exported for tests)
    _run_export,
    _run_read_abc,
    _run_round,
    _run_split_parts,
)
from ai_score_editing.sibelius.commands.score import (  # noqa: F401  (re-exported for tests)
    NAMED_OPERATIONS,
    _run_add_bars,
    _run_add_staff,
    _run_apply,
    _run_backup,
    _run_do,
    _run_duplicate_octave_down_to_voice2,
    _run_save,
    _run_set_score_info,
    _run_set_initial_instrument,
    _run_set_staff_name,
)
from ai_score_editing.sibelius.commands.lyrics import (  # noqa: F401  (re-exported for tests)
    _run_check_lyrics,
    _run_patch_lyrics,
    _run_read_lyrics,
    _run_set_lyric,
    _run_set_lyric_style,
)
from ai_score_editing.sibelius.client import ConnectionFailed, SibeliusClient, run_sync
from ai_score_editing.token_store import TokenStore

# Handlers of the areas already moved into ``sibelius/commands/``; filled by build_parser().
_MIGRATED: dict[str, Callable[..., Any]] = {}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sibelius-cli",
        description="Drive Sibelius via its Sibelius Connect WebSocket interface.",
    )
    parser.add_argument("--host", default=protocol.DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=protocol.DEFAULT_PORT)
    parser.add_argument("--client-name", default=protocol.DEFAULT_CLIENT_NAME)
    parser.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        help="seconds to wait for connection approval in Sibelius",
    )
    parser.add_argument(
        "--launch",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="start Sibelius if not already running (default: True)",
    )
    parser.add_argument(
        "--launch-timeout",
        type=float,
        default=30.0,
        help="seconds to wait for Sibelius to start and open port (default: 30)",
    )
    parser.add_argument(
        "--sibelius-path",
        help="custom path to Sibelius application or executable",
    )
    parser.add_argument("--json", action="store_true", help="print raw JSON responses")
    parser.add_argument(
        "--expect-file",
        help="refuse writes unless the active score resolves to this path",
    )
    parser.add_argument(
        "--backup-dir",
        help="put the timestamped .sib backups of write commands in this folder instead of "
        "beside the score (default: the SIBELIUS_BACKUP_DIR environment variable, else beside the score)",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="log the wire traffic")

    sub = parser.add_subparsers(dest="subcommand", required=True)
    _MIGRATED.clear()
    _MIGRATED.update(commands.register_all(sub))
    return parser


_emit = _common.emit


async def _assert_expected_score(
    client: SibeliusClient,
    args: argparse.Namespace,
    info: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Fail before mutation when --expect-file does not name the active score."""
    expected_arg = getattr(args, "expect_file", None)
    if not expected_arg:
        return info
    if info is None:
        info = await _bridge(client, "GetScoreInfo")
    actual_arg = info.get("fileName") if isinstance(info, dict) else None
    if not actual_arg:
        raise BridgeError("active score has no file path; --expect-file cannot be verified")
    expected = Path(expected_arg).expanduser().resolve()
    actual = Path(actual_arg).expanduser().resolve()
    if actual != expected:
        raise BridgeError(f"active score mismatch: expected {expected}, got {actual}")
    return info


# Private names kept for skill scripts and tests; code below calls them through
# this module's globals so patches on ``cli._bridge`` etc. still take effect.
_bridge = bridge.call
_apply_batch = bridge.apply_batch
_require_bridge = bridge.require_bridge
_check_bridge_version = bridge.check_bridge_version
_batch_bridge_version = batch_bridge_version
_export_path = bridge.export_path


class _CliBridge(bridge.SibeliusBridge):
    """A SibeliusBridge whose calls go through this module's ``_bridge`` & co.

    The service functions use it, so patches of ``cli._bridge``,
    ``cli._require_bridge`` and ``cli._apply_batch`` still take effect.
    """

    async def call(self, method: str, args: list[Any] | None = None) -> Any:
        if args is None:
            return await _bridge(self.client, method)
        return await _bridge(self.client, method, args)

    async def apply_batch(self, operations: list[dict[str, Any]], dry_run: bool) -> dict[str, Any]:
        return await _apply_batch(self.client, operations, dry_run)

    async def require(self, version: int, feature: str) -> None:
        await _require_bridge(self.client, version, feature)


async def _backup(client: SibeliusClient, name: str) -> dict[str, Any]:
    """In-file version + save + timestamped copy, into $SIBELIUS_BACKUP_DIR if set.

    Kept for skill scripts; main() exports --backup-dir to the environment.
    """
    return await service.backup(_CliBridge(client), name, service.backup_folder())


async def _backup_and_report(b: bridge.SibeliusBridge, name: str) -> dict[str, Any]:
    made = await _backup(b.client, name)
    print(f"backed up: {made['copy']}", file=sys.stderr)
    return made


async def _run_write(
    args: argparse.Namespace, method: str, call_args: list[Any]
) -> int:
    """Backup, then run a bridge write method and print its result."""
    async with _client(args, plugins=[BRIDGE_PLUGIN]) as client:
        await _check_bridge_version(client)
        await _assert_expected_score(client, args)
        backup = await _backup(client, f"before {args.subcommand}")
        print(f"backed up: {backup['copy']}", file=sys.stderr)
        result = await _bridge(client, method, call_args)
        if getattr(args, "save", False):
            saved = await service.save(_CliBridge(client), args.path)
            print(f"saved: {saved.get('fileName', '')}", file=sys.stderr)
    print(json.dumps(result, indent=2))
    return EXIT_OK


async def _run_op(
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
    async with _client(args, plugins=[BRIDGE_PLUGIN]) as client:
        if not batch:
            try:
                batch = batch_ops.validate_batch([await operation(client)])
            except batch_ops.BatchError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return EXIT_COMMAND_FAILED
        await _require_bridge(client, max(min_bridge, _batch_bridge_version(batch)), args.subcommand)
        await _assert_expected_score(client, args)
        sb = _CliBridge(client)
        try:
            await service.check(sb, batch)
        except service.BatchFailed as exc:
            raise BridgeError(exc.result["error"]) from exc
        report = await before_write(client, batch) if before_write else None
        if getattr(args, "dry_run", False):
            print(json.dumps({"dryRun": True, "checked": len(batch), "preview": report}, indent=2))
            return EXIT_OK
        if report is not None:
            print(json.dumps({"replacing": report}, indent=2), file=sys.stderr)
        try:
            result = await service.commit(
                sb, batch, backup_name=f"before {args.subcommand}", backup_fn=_backup_and_report
            )
        except service.BatchFailed as exc:
            raise BridgeError(f"{exc.result['error']}; restore from {exc.backup}") from exc
        if getattr(args, "save", False):
            saved = await service.save(sb)
            print(f"saved: {saved.get('fileName', '')}", file=sys.stderr)
    print(json.dumps(legacy(result["results"][0]), indent=2))
    return EXIT_OK


def _address(args: argparse.Namespace) -> dict[str, Any]:
    return {"staff": args.staff, "bar": args.bar, "index": args.index}


def _notes(description: dict[str, Any] | None) -> list[dict[str, Any]]:
    return list((description or {}).get("notes", []))


async def _read_rows(client: SibeliusClient, staff: int, from_bar: int, to_bar: int) -> list[dict[str, Any]]:
    """Every object of one staff in the bars, as Query reports it."""
    from ai_score_editing.query import build_selector

    selector = build_selector(
        staves=[staff], from_bar=from_bar, to_bar=to_bar, types=[], voice=None, where=[], fields=[], limit=5000,
    )
    return list((await _bridge(client, "Query", [selector])).get("objects", []))


def _time_signature_at(info: dict[str, Any], bar: int) -> tuple[int, int]:
    found = (4, 4)
    for signature in info.get("timeSignatures", []):
        if signature.get("bar", 1) <= bar:
            found = (signature.get("numerator", 4), signature.get("denominator", 4))
    return found


def _client(args: argparse.Namespace, plugins: list[str] | None = None) -> SibeliusClient:
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


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    # Resolve the backup folder once; every backup (CLI, skill scripts) reads it back
    # through service.backup_folder().
    folder = service.backup_folder(args.backup_dir)
    if folder is not None:
        os.environ[service.BACKUP_DIR_ENV] = str(folder)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(message)s",
    )

    runner = _MIGRATED[args.subcommand]
    # A re-exported ``cli._run_*`` name wins, so tests can patch handlers on ``cli``.
    runner = globals().get(runner.__name__, runner)
    try:
        result = runner(args)
        if isawaitable(result):
            result = run_sync(result)
        return int(result)
    except BridgeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_COMMAND_FAILED
    except ConnectionFailed as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_CONNECTION_FAILED
    except TimeoutError:
        print("error: timed out waiting for a response from Sibelius", file=sys.stderr)
        return EXIT_CONNECTION_FAILED
