"""Command-line interface (docs/sibelius-protocol.md 2.2)."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import tempfile
from collections.abc import Awaitable, Callable
from inspect import isawaitable
from pathlib import Path
from typing import Any

from ai_score_editing import (
    abc_notation,
    agent_output,
    batch_ops,
    layout,
    lyrics,
    music,
)
from ai_score_editing.barrange import parse_bar_range
from ai_score_editing.sibelius import bridge, launcher, protocol, service
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
from ai_score_editing.sibelius.commands.lyrics import (  # noqa: F401  (re-exported for tests)
    _run_check_lyrics,
    _run_patch_lyrics,
    _run_read_lyrics,
    _run_set_lyric,
    _run_set_lyric_style,
)
from ai_score_editing.sibelius.client import ConnectionFailed, SibeliusClient, run_sync
from ai_score_editing.token_store import TokenStore

EXIT_OK = _common.EXIT_OK
EXIT_COMMAND_FAILED = _common.EXIT_COMMAND_FAILED
EXIT_CONNECTION_FAILED = _common.EXIT_CONNECTION_FAILED

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
    sub.add_parser("save", help="save the active score in Sibelius")
    sub.add_parser(
        "score-info",
        help="read info about the open score (requires the bundled ScoreBridge plug-in)",
    )
    sub.add_parser(
        "text-styles",
        help="list the font and size of each text and lyric style in use; flags music fonts on lyric styles",
    )
    sub.add_parser("staves", help="list staves of the open score (requires bridge plug-in)")
    sub.add_parser("selection", help="describe the current selection (requires bridge plug-in)")
    sub.add_parser(
        "inspect",
        help="compact score identity, staff, and selection summary",
    )
    snapshot = sub.add_parser(
        "score-snapshot",
        help="compact structural snapshot from one bridge session",
    )
    snapshot.add_argument("--bars", help="bar range for optional lyrics and barlines, e.g. '1-30'")
    snapshot.add_argument("--staff", type=int, default=0, help="staff for optional lyrics (0 = all)")
    snapshot.add_argument("--lyrics", action="store_true", help="include compact lyric data")
    snapshot.add_argument(
        "--no-barlines",
        dest="barlines",
        action="store_false",
        help="omit special barlines from the snapshot",
    )
    snapshot.set_defaults(barlines=True)
    proofread = sub.add_parser(
        "proofread",
        help="read-only structural and lyric proofreading report",
    )
    proofread.add_argument("--bars", help="bar range to inspect, e.g. '1-30'")
    proofread.add_argument("--staff", type=int, default=0, help="staff to inspect (0 = all lyric-bearing staves)")
    proofread.add_argument("--lyrics", action="store_true", help="include compact lyric data in the report")
    proofread.add_argument("--no-barlines", dest="barlines", action="store_false", help="omit special barlines")
    proofread.set_defaults(barlines=True)
    apply = sub.add_parser(
        "apply",
        help="apply a JSON batch of edits as one undo step (requires bridge plug-in)",
    )
    apply.add_argument("--file", required=True, help="JSON operation array; see the sibelius skill's command reference")
    apply.add_argument("--save", action="store_true", help="save after the batch succeeds")
    apply.add_argument("--dry-run", action="store_true", help="check every operation against the open score without changing it")
    read = sub.add_parser("read", help="read bar contents (requires bridge plug-in)")
    read.add_argument("--staff", type=int, default=1, help="staff number, from 1")
    read.add_argument("--from", dest="from_bar", type=int, help="first bar, from 1")
    read.add_argument("--to", dest="to_bar", type=int, help="last bar (default: same as --from)")
    read.add_argument("--bar", type=int, help="specific bar number")
    read.add_argument("--bars", type=str, help="bar range, e.g. '1-3' or '5'")
    read.add_argument("--abc", action="store_true", help="format output as ABC notation with aligned lyrics")
    query = sub.add_parser(
        "query",
        help="find bar objects by staff, bars, type, voice and property filters (requires bridge plug-in)",
    )
    query.add_argument("--staff", action="append", default=[], help="staff number or instrument name; repeatable (default: all)")
    query.add_argument("--bars", type=str, help="bar range, e.g. '12-20' or '5' (default: all)")
    query.add_argument("--type", action="append", default=[], help="object type, e.g. NoteRest, LyricItem, Text, Line, Slur; repeatable or comma-separated")
    query.add_argument("--voice", type=int, help="voice 1-4")
    query.add_argument("--where", action="append", default=[], help="property filter, e.g. 'Pitch>=72' or 'Hidden=true'; repeatable, all must match")
    query.add_argument("--field", action="append", default=[], help="extra properties to return, e.g. Dx,Dy; repeatable or comma-separated")
    query.add_argument("--limit", type=int, default=500, help="maximum objects to return (default: 500)")
    read_abc = sub.add_parser("read-abc", help="format bar contents as standard ABC notation")
    read_abc.add_argument("--staff", type=int, default=1, help="staff number, from 1")
    read_abc.add_argument("--from", dest="from_bar", type=int, help="first bar, from 1")
    read_abc.add_argument("--to", dest="to_bar", type=int, help="last bar (default: same as --from)")
    read_abc.add_argument("--bar", type=int, help="specific bar number")
    read_abc.add_argument("--bars", type=str, help="bar range, e.g. '1-3' or '5'")
    sub.add_parser("bridge-version", help="report the installed bridge plug-in version")
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
    export = sub.add_parser("export", help="export the active (or a given) score to another format")
    export.add_argument("--format", choices=sorted(EXPORT_FORMATS), default="musicxml")
    export.add_argument("--out", help="output path (default: next to the source file)")
    export.add_argument("--file", dest="sib_file", help=".sib file to open first (default: active score)")
    backup = sub.add_parser("backup", help="in-file version + save + timestamped file copy")
    backup.add_argument("--name", default="ai-score-editing backup")
    do = sub.add_parser("do", help="run a named operation (curated command IDs)")
    do.add_argument(
        "operation",
        choices=sorted(NAMED_OPERATIONS),
        metavar="operation",
        help=f"one of: {', '.join(sorted(NAMED_OPERATIONS))}",
    )
    split_parts = sub.add_parser(
        "split-parts",
        aliases=["demix"],
        help="demix multi-voice / choral scores into discrete vocal staves",
    )
    split_parts.add_argument(
        "score_file",
        nargs="?",
        help="input score file (.sib, .xml, .mxl); defaults to active score in Sibelius",
    )
    split_parts.add_argument(
        "--file",
        "-f",
        dest="file_opt",
        help="alternative to positional score file",
    )
    split_parts.add_argument(
        "--preset",
        choices=["16voices", "satb"],
        default="16voices",
        help="demixing preset (default: 16voices)",
    )
    split_parts.add_argument(
        "--out",
        "-o",
        help="output path (default: <input_stem>_<preset>.mxl)",
    )
    split_parts.add_argument(
        "--validate",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="validate measure durations across generated parts (default: True)",
    )
    split_parts.add_argument(
        "--audit",
        action="store_true",
        help="report layout and routing diagnostics without writing an output score",
    )
    split_parts.add_argument("--soprano-solo", help="SATB solo bars, e.g. 8-15,20")
    split_parts.add_argument("--tenor-solo", help="SATB solo bars, e.g. 8-15,20")
    split_parts.add_argument("--bass-solo", help="SATB solo bars, e.g. 8-15,20")
    split_parts.add_argument(
        "--open",
        action="store_true",
        help="open the resulting score in Sibelius upon completion",
    )
    round_cmd = sub.add_parser(
        "round",
        help="arrange a single-part round as staggered voices for playback (MusicXML in and out)",
    )
    round_cmd.add_argument("score_file", help="single-part round (.xml, .musicxml, .mxl)")
    round_cmd.add_argument("--out", "-o", help="output path (default: <input_stem>_round.musicxml)")
    round_cmd.add_argument("--voices", type=int, help='number of voices (default: highest "N." entry mark)')
    round_cmd.add_argument("--gap", type=int, help='bars between entries (default: from "1." and "2." marks)')
    round_cmd.add_argument("--passes", type=int, default=2, help="times each voice sings the song (default: 2)")
    round_cmd.add_argument(
        "--program", type=int, default=53, help="General MIDI program, 1-based (default: 53, Choir Aahs)"
    )
    round_cmd.add_argument(
        "--no-hold-final",
        dest="hold_final",
        action="store_false",
        help="keep each voice's last bar as written instead of holding its first note",
    )
    round_cmd.add_argument("--open", action="store_true", help="open the result in Sibelius")
    return parser


_emit = _common.emit


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


async def _run_score_info(args: argparse.Namespace) -> int:
    return await _run_bridge_call(args, "GetScoreInfo")


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
            saved = await service.save(_CliBridge(client))
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


async def _run_save(args: argparse.Namespace) -> int:
    async with _client(args, plugins=[BRIDGE_PLUGIN]) as client:
        await _check_bridge_version(client)
        await _assert_expected_score(client, args)
        saved = await service.save(_CliBridge(client))
    print(json.dumps(saved) if args.json else f"saved: {saved.get('fileName', '')}")
    return EXIT_OK


async def _run_bridge_call(
    args: argparse.Namespace, method: str, call_args: list[Any] | None = None
) -> int:
    async with _client(args, plugins=[BRIDGE_PLUGIN]) as client:
        response = await client.invoke_plugin(BRIDGE_PLUGIN, method, call_args)
    if not protocol.is_success(response):
        print(
            "error: bridge plug-in not reachable — run "
            "'sibelius-cli install-plugin' and restart Sibelius. "
            f"Response: {json.dumps(response)}",
            file=sys.stderr,
        )
        return EXIT_COMMAND_FAILED
    value = protocol.plugin_return_value(response)
    print(json.dumps(response) if args.json else json.dumps(value, indent=2))
    if isinstance(value, dict) and "error" in value:
        return EXIT_COMMAND_FAILED
    return EXIT_OK


async def _run_text_styles(args: argparse.Namespace) -> int:
    from ai_score_editing import text_styles

    selector = {
        "staves": [],
        "types": ["Text", "LyricItem"],
        "where": [],
        "fields": [],
        "voice": 0,
        "limit": 100000,
    }
    try:
        async with _client(args, plugins=[BRIDGE_PLUGIN]) as client:
            await _require_bridge(client, TEXT_FONTS_BRIDGE_VERSION, "text-styles")
            info = await _bridge(client, "GetScoreInfo")
            found = []
            for system, staves in ((True, [0]), (False, [])):
                selector["staves"] = staves
                result = await _bridge(client, "Query", [selector])
                found += [(obj.get("styleId", ""), system) for obj in result["objects"]]
            probed = await _bridge(client, "GetTextStyleFonts", [text_styles.style_requests(found)])
    except BridgeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_COMMAND_FAILED
    print(json.dumps(text_styles.build_report(info, probed["styles"]), indent=None if args.json else 2))
    return EXIT_OK


async def _run_staves(args: argparse.Namespace) -> int:
    return await _run_bridge_call(args, "GetStaves")


async def _run_selection(args: argparse.Namespace) -> int:
    return await _run_bridge_call(args, "GetSelectionInfo")


async def _run_inspect(args: argparse.Namespace) -> int:
    async with _client(args, plugins=[BRIDGE_PLUGIN]) as client:
        await _check_bridge_version(client)
        info = await _bridge(client, "GetScoreInfo")
        staves = await _bridge(client, "GetStaves")
        selection = await _bridge(client, "GetSelectionInfo")
    projected = agent_output.project_inspect(info, staves, selection)
    if args.json:
        print(json.dumps(projected, ensure_ascii=False, separators=(",", ":")))
    else:
        print(agent_output.render_compact_inspect(info, staves, selection))
    return EXIT_OK


async def _run_score_snapshot(args: argparse.Namespace) -> int:
    from_b, to_b = parse_bar_range(bars=getattr(args, "bars", None))
    async with _client(args, plugins=[BRIDGE_PLUGIN]) as client:
        await _check_bridge_version(client)
        info = await _bridge(client, "GetScoreInfo")
        staves = await _bridge(client, "GetStaves")
        selection = await _bridge(client, "GetSelectionInfo")

        barlines: list[dict[str, Any]] = []
        if args.barlines:
            bar_start = from_b or 1
            bar_end = to_b or int(info.get("barCount", bar_start))
            barlines = await _bridge(client, "GetSpecialBarlines", [bar_start, bar_end])

        lyric_data: list[dict[str, Any]] | None = None
        if args.lyrics:
            lyric_data = await _bridge(
                client,
                "ReadLyrics",
                [args.staff, from_b or 0, to_b or 0],
            )

    snapshot = agent_output.project_score_snapshot(
        info,
        staves,
        selection,
        barlines=barlines,
        lyrics=lyric_data,
    )
    print(agent_output.render_compact_snapshot(snapshot))
    return EXIT_OK


async def _run_proofread(args: argparse.Namespace) -> int:
    from_b, to_b = parse_bar_range(bars=getattr(args, "bars", None))
    verse = None
    async with _client(args, plugins=[BRIDGE_PLUGIN]) as client:
        await _check_bridge_version(client)
        info = await _bridge(client, "GetScoreInfo")
        staves_info = await _bridge(client, "GetStaves")
        selection = await _bridge(client, "GetSelectionInfo")
        names = {
            s.get("staffNum", s.get("staffNumber", i + 1)): (
                s.get("fullInstrumentName")
                or s.get("instrumentName")
                or s.get("name")
                or f"Staff {s.get('staffNum', i + 1)}"
            )
            for i, s in enumerate(staves_info)
        }
        raw_lyrics = await _bridge(client, "ReadLyrics", [args.staff, from_b or 0, to_b or 0])
        filtered_lyrics = lyrics.filter_lyrics(raw_lyrics, from_bar=from_b, to_bar=to_b, verse=verse)

        bar_count = int(info.get("barCount", 0))
        start_b = from_b or 1
        end_b = to_b or bar_count
        target_staves = [args.staff] if args.staff > 0 else sorted({s.get("staff", 1) for s in filtered_lyrics})
        staff_bars: dict[int, list[dict[str, Any]]] = {}
        for staff_num in target_staves:
            if end_b >= start_b:
                staff_bars[staff_num] = await _bridge(client, "ReadBars", [staff_num, start_b, end_b])

        barlines: list[dict[str, Any]] = []
        if args.barlines:
            barlines = await _bridge(client, "GetSpecialBarlines", [start_b, end_b])

    score_default_font = info.get("mainTextFontName")
    typography = lyrics.analyze_lyric_typography(
        filtered_lyrics, score_default_font=score_default_font, staff_names=names
    )
    issues = lyrics.lint_lyrics(
        filtered_lyrics, names, staff_bars, score_default_font=score_default_font
    )
    snapshot = agent_output.project_score_snapshot(
        info,
        staves_info,
        selection,
        barlines=barlines,
        lyrics=filtered_lyrics if args.lyrics else None,
    )
    compact_issues = [
        {
            field: issue[field]
            for field in ("type", "severity", "bar", "staff", "staves", "line", "message")
            if field in issue
        }
        for issue in issues
    ]
    report = {
        "snapshot": snapshot,
        "issues": compact_issues,
        "errors": sum(issue.get("severity") == "error" for issue in issues),
        "warnings": sum(issue.get("severity") == "warning" for issue in issues),
        "typography": {
            field: typography[field]
            for field in ("predominant_font", "predominant_size", "has_divergence_from_score_default")
            if field in typography
        },
    }
    print(json.dumps(report, ensure_ascii=False, separators=(",", ":")))
    return EXIT_COMMAND_FAILED if report["errors"] else EXIT_OK


async def _run_apply(args: argparse.Namespace) -> int:
    try:
        operations = batch_ops.load_batch(args.file)
    except batch_ops.BatchError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_COMMAND_FAILED

    backup = None
    saved = None
    failure: service.BatchFailed | None = None
    try:
        async with _client(args, plugins=[BRIDGE_PLUGIN]) as client:
            sb = _CliBridge(client)
            await _require_bridge(client, _batch_bridge_version(operations), "apply")
            await _assert_expected_score(client, args)
            try:
                # Check first so a refused batch neither saves nor backs up.
                result = await service.check(sb, operations)
                if not args.dry_run:
                    result = await service.commit(
                        sb, operations, backup_name="before apply",
                        backup_fn=lambda b, name: _backup(b.client, name),
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


async def _run_query(args: argparse.Namespace) -> int:
    from ai_score_editing.query import QueryError

    from_b, to_b = (None, None)
    if args.bars:
        from_b, to_b = parse_bar_range(bars=args.bars)
    params: dict[str, Any] = {
        "from_bar": from_b, "to_bar": to_b, "types": args.type, "voice": args.voice,
        "where": args.where, "fields": args.field, "limit": args.limit,
    }
    try:
        service.query_selector(**params)  # validate everything but staff names before connecting
        async with _client(args, plugins=[BRIDGE_PLUGIN]) as client:
            result = await service.query(_CliBridge(client), staves=args.staff, **params)
    except (QueryError, BridgeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_COMMAND_FAILED
    print(json.dumps(result, indent=None if args.json else 2))
    if result.get("truncated"):
        print(f"warning: truncated at {args.limit} objects; narrow the query or raise --limit", file=sys.stderr)
    return EXIT_OK


async def _run_read(args: argparse.Namespace) -> int:
    from_b, to_b = parse_bar_range(
        bar=getattr(args, "bar", None),
        bars=getattr(args, "bars", None),
        from_bar=getattr(args, "from_bar", None),
        to_bar=getattr(args, "to_bar", None),
    )
    start_bar = from_b if from_b is not None else 1
    end_bar = to_b if to_b is not None else start_bar

    if getattr(args, "abc", False) or getattr(args, "subcommand", "") == "read-abc":
        async with _client(args, plugins=[BRIDGE_PLUGIN]) as client:
            await _check_bridge_version(client)
            info = await _bridge(client, "GetScoreInfo")
            staves_info = await _bridge(client, "GetStaves")
            # An unaddressed ABC export is expected to represent the whole
            # staff.  Ordinary `read` retains its one-bar default.
            if from_b is None and to_b is None:
                end_bar = info.get("barCount", end_bar)
            bars = await _bridge(client, "ReadBars", [args.staff, start_bar, end_bar])
            raw_lyrics = await _bridge(
                client, "ReadLyrics", [args.staff, start_bar, end_bar]
            )
            filtered_lyrics = lyrics.filter_lyrics(raw_lyrics, from_bar=start_bar, to_bar=end_bar)

            key_name = "C"
            for ks in info.get("keySignatures", []):
                if ks.get("bar", 1) <= start_bar:
                    key_name = ks.get("name", "C")

            time_sig = None
            for ts in info.get("timeSignatures", []):
                if ts.get("bar", 1) <= start_bar:
                    time_sig = (ts.get("numerator", 4), ts.get("denominator", 4))

            instr_name = None
            for s in staves_info:
                if s.get("staffNum") == args.staff:
                    instr_name = s.get("fullInstrumentName") or s.get("instrumentName")

            abc_str = abc_notation.score_to_abc(
                bars,
                lyrics=filtered_lyrics,
                time_sig=time_sig,
                key=key_name,
                staff_num=args.staff,
                instrument_name=instr_name,
            )
            print(abc_str)
            return EXIT_OK

    return await _run_bridge_call(args, "ReadBars", [args.staff, start_bar, end_bar])


async def _run_read_abc(args: argparse.Namespace) -> int:
    setattr(args, "abc", True)
    return await _run_read(args)


async def _run_do(args: argparse.Namespace) -> int:
    command_id = NAMED_OPERATIONS[args.operation]
    async with _client(args) as client:
        response = await client.invoke_commands([command_id])
    return _emit(args, response, f"sent {args.operation} ({command_id})")


async def _run_bridge_version(args: argparse.Namespace) -> int:
    return await _run_bridge_call(args, "GetBridgeVersion")




async def _run_set_staff_name(args: argparse.Namespace) -> int:
    return await _run_write(
        args, "SetStaffName", [args.staff, args.full or "", args.short or ""]
    )


async def _run_set_initial_instrument(args: argparse.Namespace) -> int:
    style_id = music.resolve_instrument_style(args.instrument)
    return await _run_write(args, "SetInitialInstrument", [args.staff, style_id])


async def _run_duplicate_octave_down_to_voice2(args: argparse.Namespace) -> int:
    return await _run_write(
        args,
        "DuplicateOctaveDownToVoice2",
        [args.staff, args.from_bar, args.to_bar],
    )


async def _run_set_score_info(args: argparse.Namespace) -> int:
    return await _run_write(
        args,
        "SetScoreInfo",
        [args.title or "", args.composer or "", args.lyricist or ""],
    )


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


async def _run_add_staff(args: argparse.Namespace) -> int:
    if getattr(args, "above_staff", None):
        return await _run_write(
            args,
            "AddStaffToInstrument",
            [args.above_staff, True, bool(getattr(args, "ossia", False))],
        )
    if getattr(args, "below_staff", None):
        return await _run_write(
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
    return await _run_write(
        args,
        "CreateStaff",
        [style_id, args.position, args.full_name or "", args.short_name or ""],
    )


async def _run_add_bars(args: argparse.Namespace) -> int:
    count = getattr(args, "count", 1)
    return await _run_op(
        args,
        {"op": "add-bars", "count": count},
        lambda result: {"addedBars": result["after"]["addedBars"], "totalBars": result["after"]["barCount"]},
    )


async def _run_export(args: argparse.Namespace) -> int:
    async with _client(args, plugins=[BRIDGE_PLUGIN]) as client:
        await _check_bridge_version(client)
        if args.sib_file:
            source = Path(args.sib_file).expanduser().resolve()
            if not source.exists():
                print(f"error: {source} does not exist", file=sys.stderr)
                return EXIT_COMMAND_FAILED
            opened = await _bridge(client, "OpenScore", [str(source)])
            print(f"opened: {opened['fileName']}", file=sys.stderr)
        try:
            result = await service.export(_CliBridge(client), args.format, args.out)
        except BridgeError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return EXIT_COMMAND_FAILED
    print(json.dumps(result, indent=2))
    return EXIT_OK


async def _run_backup(args: argparse.Namespace) -> int:
    async with _client(args, plugins=[BRIDGE_PLUGIN]) as client:
        await _check_bridge_version(client)
        await _assert_expected_score(client, args)
        result = await _backup(client, args.name)
    print(json.dumps(result, indent=2))
    return EXIT_OK


async def _run_split_parts(args: argparse.Namespace) -> int:
    input_str = args.file_opt or args.score_file
    temp_dir: tempfile.TemporaryDirectory[str] | None = None
    source_path: Path | None = None

    if input_str:
        source_path = Path(input_str).expanduser().resolve()
        if not source_path.exists():
            print(f"error: {source_path} does not exist", file=sys.stderr)
            return EXIT_COMMAND_FAILED

    # If input is .sib or omitted, connect to Sibelius to export to MusicXML
    if source_path is None or source_path.suffix.lower() == ".sib":
        temp_dir = tempfile.TemporaryDirectory(prefix="sib_split_parts_")
        exported_xml = Path(temp_dir.name) / "source_export.musicxml"
        async with _client(args, plugins=[BRIDGE_PLUGIN]) as client:
            await _check_bridge_version(client)
            if source_path is not None:
                opened = await _bridge(client, "OpenScore", [str(source_path)])
                print(f"opened: {opened.get('fileName', str(source_path))}", file=sys.stderr)
            info = await _bridge(client, "GetScoreInfo")
            saveas_type, _ = EXPORT_FORMATS["musicxml"]
            await _bridge(client, "ExportScore", [str(exported_xml), saveas_type])

        xml_input_path = exported_xml
        file_name = info.get("fileName")
        default_stem = source_path.stem if source_path else (Path(file_name).stem if file_name else "score")
        default_parent = source_path.parent if source_path else (Path(file_name).parent if file_name else Path.cwd())
    else:
        xml_input_path = source_path
        default_stem = source_path.stem
        default_parent = source_path.parent

    # Determine destination output path
    if args.out:
        out_path = Path(args.out).expanduser().resolve()
    else:
        out_path = default_parent / f"{default_stem}_{args.preset}.mxl"

    try:
        from ai_score_editing.musicxml_split.profiles.polychoral_16 import split_16voices
        from ai_score_editing.musicxml_split.profiles.satb import SATBOptions, split_satb
        from ai_score_editing.musicxml_split.validation import validate_file

        def parse_ranges(value: str | None) -> frozenset[int]:
            bars: set[int] = set()
            for item in (value or "").split(","):
                item = item.strip()
                if not item:
                    continue
                start, separator, end = item.partition("-")
                bars.update(range(int(start), int(end) + 1) if separator else [int(start)])
            return frozenset(bars)

        if args.preset == "16voices":
            result = split_16voices(xml_input_path, None if args.audit else out_path, audit_only=args.audit)
        elif args.preset == "satb":
            result = split_satb(
                xml_input_path,
                None if args.audit else out_path,
                SATBOptions(
                    soprano_solo_bars=parse_ranges(args.soprano_solo),
                    tenor_solo_bars=parse_ranges(args.tenor_solo),
                    bass_solo_bars=parse_ranges(args.bass_solo),
                ),
                audit_only=args.audit,
            )
        else:
            print(f"error: unknown preset {args.preset}", file=sys.stderr)
            return EXIT_COMMAND_FAILED

        res = result.as_dict(xml_input_path)
        val_issues = validate_file(out_path, expected_parts=len(result.parts)) if args.validate and not args.audit else []
        all_issues = result.issues + val_issues
        res["valid"] = not any(issue.severity == "error" for issue in all_issues)
        res["issues"] = [issue.as_dict() for issue in all_issues]
        if val_issues:
            res["validationIssues"] = [issue.as_dict() for issue in val_issues]

        if args.open and not args.audit:
            launcher.open_score_file(out_path, app_path=args.sibelius_path)
            res["opened"] = True

        if args.json:
            print(json.dumps(res, indent=2))
        else:
            action = "Audited" if args.audit else "Demixed"
            print(f"{action} {res['totalMeasures']} measures across {res['partsCount']} parts ({args.preset}).")
            if not args.audit:
                print(f"Saved to: {res['outputFile']}")
            if args.validate:
                if all_issues:
                    print(
                        f"Validation warning: {len(all_issues)} issue(s) detected:",
                        file=sys.stderr,
                    )
                    for issue in all_issues[:10]:
                        print(f"  - {issue.code}: {issue.message}", file=sys.stderr)
                else:
                    print("Validation passed: 0 discrepancies found.")
        return EXIT_OK
    finally:
        if temp_dir is not None:
            temp_dir.cleanup()


async def _run_round(args: argparse.Namespace) -> int:
    import xml.etree.ElementTree as ET

    from ai_score_editing.musicxml_round import RoundOptions, build_round
    from ai_score_editing.musicxml_split.io import parse_musicxml, save_musicxml

    source = Path(args.score_file).expanduser().resolve()
    if source.suffix.lower() not in {".xml", ".musicxml", ".mxl"}:
        print("error: round needs MusicXML input; export .sib scores first", file=sys.stderr)
        return EXIT_COMMAND_FAILED
    out = Path(args.out).expanduser().resolve() if args.out else source.with_name(f"{source.stem}_round.musicxml")
    try:
        _, root = parse_musicxml(source)
        result = build_round(root, RoundOptions(
            voices=args.voices, gap=args.gap, passes=args.passes,
            program=args.program, hold_final=args.hold_final,
        ))
    except (OSError, ValueError, ET.ParseError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_COMMAND_FAILED
    save_musicxml(result.root, out)
    summary = {**result.as_dict(), "outputFile": str(out)}
    if args.open:
        launcher.open_score_file(out, app_path=args.sibelius_path)
        summary["opened"] = True
    print(layout.compact_summary(summary))
    return EXIT_OK


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

    legacy = {
        "score-info": _run_score_info,
        "text-styles": _run_text_styles,
        "staves": _run_staves,
        "selection": _run_selection,
        "inspect": _run_inspect,
        "score-snapshot": _run_score_snapshot,
        "proofread": _run_proofread,
        "read": _run_read,
        "do": _run_do,
        "query": _run_query,
        "apply": _run_apply,
        "bridge-version": _run_bridge_version,
        "backup": _run_backup,
        "export": _run_export,
        "save": _run_save,
        "read-abc": _run_read_abc,
        "add-staff": _run_add_staff,
        "create-staff": _run_add_staff,
        "add-bars": _run_add_bars,
        "set-staff-name": _run_set_staff_name,
        "set-initial-instrument": _run_set_initial_instrument,
        "duplicate-octave-down-to-voice2": _run_duplicate_octave_down_to_voice2,
        "set-score-info": _run_set_score_info,
        "split-parts": _run_split_parts,
        "demix": _run_split_parts,
        "round": _run_round,
    }
    runner = _MIGRATED.get(args.subcommand)
    if runner is not None:
        # A re-exported ``cli._run_*`` name wins, so tests can patch handlers on ``cli``.
        runner = globals().get(runner.__name__, runner)
    else:
        runner = legacy[args.subcommand]
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
