"""Note commands: set-note, tie, delete-object, delete-voice, clear-bars, flip-stem, bracket,
beam, nudge, add-notes (add-note), add-abc, copy-passage, patch-notes, transpose."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from typing import Any

from ai_score_editing import abc_notation, batch_ops, layout, music, note_patches
from ai_score_editing.intervals import compute_transposition
from ai_score_editing.sibelius import copy_range
from ai_score_editing.sibelius.bridge import (
    BEAM_RESULT_BRIDGE_VERSION,
    BRIDGE_PLUGIN,
    LYRIC_VERSE_BRIDGE_VERSION,
    NUDGE_BRIDGE_VERSION,
    BridgeError,
)
from ai_score_editing.sibelius.client import SibeliusClient
from ai_score_editing.sibelius.commands._common import EXIT_COMMAND_FAILED, EXIT_OK
from ai_score_editing.sibelius.commands._common import client as _client


class _Cli:
    """Late lookup of ``sibelius.cli`` attributes.

    Tests and skill scripts patch ``cli._bridge``, ``cli._backup``,
    ``cli._apply_batch`` and friends, so handlers resolve them at call time.
    """

    def __getattr__(self, name: str) -> Any:
        from ai_score_editing.sibelius import cli

        return getattr(cli, name)


_cli = _Cli()


def register(sub: Any) -> dict[str, Callable[..., Any]]:
    patch_notes = sub.add_parser(
        "patch-notes",
        help="apply a validated JSON batch of pitch, tie, stem, and delete edits",
    )
    patch_notes.add_argument("--file", required=True, help="JSON note operation array")
    patch_notes.add_argument("--save", action="store_true", help="save after all operations complete")
    patch_notes.add_argument("--dry-run", action="store_true", help="validate and report without connecting or mutating")
    transpose = sub.add_parser("transpose", help="transpose a passage or the whole score (backs up first)")
    transpose.add_argument("--from-note", required=True, help="current tonic, e.g. C or Eb")
    transpose.add_argument("--to-note", required=True, help="target tonic, e.g. D or F#")
    direction = transpose.add_mutually_exclusive_group(required=True)
    direction.add_argument("--up", action="store_true")
    direction.add_argument("--down", action="store_true")
    transpose.add_argument("--octaves", type=int, default=0, help="extra octaves in the same direction")
    transpose.add_argument("--from-bar", type=int, help="default: 1")
    transpose.add_argument("--to-bar", type=int, help="default: last bar")
    transpose.add_argument("--top-staff", type=int, help="default: 1")
    transpose.add_argument("--bottom-staff", type=int, help="default: last staff")
    transpose.add_argument("--save", action="store_true", help="save active score in Sibelius after change")
    copyp = sub.add_parser("copy-passage", help="copy a passage to another staff/bar (backs up first)")
    copyp.add_argument("--from-bar", type=int, required=True)
    copyp.add_argument("--to-bar", type=int, required=True)
    copyp.add_argument("--top-staff", type=int, required=True)
    copyp.add_argument("--bottom-staff", type=int, help="default: same as --top-staff")
    copyp.add_argument("--dest-staff", type=int, required=True)
    copyp.add_argument("--dest-bar", type=int, required=True)
    copyp.add_argument("--dest-pos", type=int, help="1/256th-quarter offset in dest bar (default 0; with a range, the range's own start)")
    copyp.add_argument("--from-pos", type=int, help="copy only from this 1/256th-quarter position of the (single) source bar")
    copyp.add_argument("--to-pos", type=int, help="copy only up to (not including) this position of the source bar")
    copyp.add_argument("--beats", help="copy only these beats of the source bar, e.g. 3-4 (counted from 1)")
    copyp.add_argument("--beat-unit", choices=["quarter", "signature"], default="quarter",
                       help="what --beats counts: quarter notes (default) or the time signature's own beat (half notes in 2/2)")
    copyp.add_argument("--dry-run", action="store_true",
                       help="check the copy and show what the destination holds now against what it would hold; change nothing")
    copyp.add_argument("--save", action="store_true", help="save active score in Sibelius after change")
    set_note = sub.add_parser("set-note", help="repitch one note in a chord/NoteRest (backs up first)")
    set_note.add_argument("--staff", type=int, required=True)
    set_note.add_argument("--bar", type=int, required=True)
    set_note.add_argument("--index", type=int, required=True)
    set_note.add_argument("--old-pitch", type=int, required=True, help="MIDI pitch to replace")
    set_note.add_argument("--new-pitch", type=int, required=True, help="replacement MIDI pitch")
    set_note.add_argument("--save", action="store_true", help="save active score in Sibelius after change")
    tie = sub.add_parser("tie", help="tie a NoteRest to its following matching note (backs up first)")
    tie.add_argument("--staff", type=int, required=True)
    tie.add_argument("--bar", type=int, required=True)
    tie.add_argument("--index", type=int, required=True)
    tie.add_argument("--remove", action="store_true", help="remove the tie instead")
    tie.add_argument("--save", action="store_true", help="save active score in Sibelius after change")
    del_obj = sub.add_parser("delete-object", help="delete the object at an address (backs up first)")
    del_obj.add_argument("--staff", type=int, required=True)
    del_obj.add_argument("--bar", type=int, required=True)
    del_obj.add_argument("--index", type=int, required=True)
    del_obj.add_argument("--save", action="store_true", help="save active score in Sibelius after change")
    del_voice = sub.add_parser(
        "delete-voice",
        help="remove one voice's contents (incl. rests) from a staff passage (backs up first)",
    )
    del_voice.add_argument("--staff", type=int, required=True)
    del_voice.add_argument("--from-bar", type=int, required=True)
    del_voice.add_argument("--to-bar", type=int, required=True)
    del_voice.add_argument("--voice", type=int, required=True, choices=[1, 2, 3, 4])
    del_voice.add_argument("--save", action="store_true", help="save active score in Sibelius after change")
    clear_bars = sub.add_parser(
        "clear-bars",
        help="replace bars of one staff with a bar rest, tuplets and slurs included (backs up first)",
    )
    clear_bars.add_argument("--staff", type=int, required=True)
    clear_bars.add_argument("--from-bar", type=int, required=True)
    clear_bars.add_argument("--to-bar", type=int, required=True)
    clear_bars.add_argument("--voice", type=int, choices=[1, 2, 3, 4], help="only this voice (default: all)")
    clear_bars.add_argument("--save", action="store_true", help="save active score in Sibelius after change")
    flip = sub.add_parser("flip-stem", help="flip the stem of a NoteRest (backs up first)")
    flip.add_argument("--staff", type=int, required=True)
    flip.add_argument("--bar", type=int, required=True)
    flip.add_argument("--index", type=int, required=True)
    flip.add_argument("--save", action="store_true", help="save active score in Sibelius after change")
    bracket = sub.add_parser("bracket", help="put a note or chord in parentheses (backs up first)")
    bracket.add_argument("--staff", type=int, required=True)
    bracket.add_argument("--bar", type=int, required=True)
    bracket.add_argument("--index", type=int, required=True)
    bracket.add_argument("--remove", action="store_true", help="remove the parentheses instead")
    bracket.add_argument("--save", action="store_true", help="save active score in Sibelius after change")
    beam = sub.add_parser("beam", help="beam a contiguous group of NoteRest objects (backs up first)")
    beam.add_argument("--staff", type=int, required=True)
    beam.add_argument("--bar", type=int, required=True)
    beam.add_argument("--from-index", type=int, required=True, help="first NoteRest object index")
    beam.add_argument("--to-index", type=int, required=True, help="last NoteRest object index")
    beam.add_argument("--save", action="store_true", help="save active score in Sibelius after change")
    nudge = sub.add_parser("nudge", help="shift an object graphically (1/32 spaces; backs up first)")
    nudge.add_argument("--staff", type=int, required=True)
    nudge.add_argument("--bar", type=int, required=True)
    nudge.add_argument("--index", type=int, required=True)
    nudge.add_argument("--dx", type=int, default=0, help="right positive")
    nudge.add_argument("--dy", type=int, default=0, help="up positive")
    nudge.add_argument("--save", action="store_true", help="save active score in Sibelius after change")
    add_notes = sub.add_parser(
        "add-notes",
        aliases=["add-note"],
        help="insert notes, chords, or sequences into a staff/bar (backs up first)",
    )
    add_notes.add_argument("--staff", type=int, required=True, help="staff number (from 1)")
    add_notes.add_argument("--bar", type=int, required=True, help="bar number (from 1)")
    add_notes.add_argument("--pos", "--position", dest="pos", type=int, default=0, help="position in bar (ticks, default: 0)")
    add_notes.add_argument("--pitch", "--pitches", dest="pitches", help="pitch name(s) or MIDI number(s), e.g. 'C4' or '60' or 'C4,E4,G4'")
    add_notes.add_argument("--duration", "--dur", dest="duration", default="quarter", help="duration name or ticks, e.g. 'quarter', 'half.', '256'")
    add_notes.add_argument("--notes", "--sequence", dest="notes", help="shorthand sequence, e.g. 'C4:quarter D4:quarter E4:half'")
    add_notes.add_argument("--voice", type=int, default=1, choices=[1, 2, 3, 4], help="voice number (1-4, default: 1)")
    add_notes.add_argument("--tied", action="store_true", help="tie note to next")
    add_notes.add_argument("--save", action="store_true", help="save active score in Sibelius after change")
    add_abc = sub.add_parser(
        "add-abc",
        help="insert music and lyrics from an ABC notation snippet (backs up first)",
    )
    add_abc.add_argument("--staff", type=int, required=True, help="staff number (from 1)")
    add_abc.add_argument("--bar", type=int, default=1, help="starting bar number (default: 1)")
    add_abc.add_argument("--pos", "--position", dest="pos", type=int, default=0, help="starting position in bar (ticks, default: 0)")
    add_abc.add_argument("abc", nargs="?", help="ABC notation string with notes and optional w: lyrics")
    add_abc.add_argument("--abc", dest="abc_opt", help="ABC notation string (alternative to positional argument)")
    add_abc.add_argument("--voice", type=int, default=1, choices=[1, 2, 3, 4], help="voice number (1-4, default: 1)")
    add_abc.add_argument("--save", action="store_true", help="save active score in Sibelius after change")
    return {
        "patch-notes": _run_patch_notes,
        "transpose": _run_transpose,
        "copy-passage": _run_copy_passage,
        "set-note": _run_set_note,
        "tie": _run_tie,
        "delete-object": _run_delete_object,
        "delete-voice": _run_delete_voice,
        "clear-bars": _run_clear_bars,
        "flip-stem": _run_flip_stem,
        "bracket": _run_bracket,
        "beam": _run_beam,
        "nudge": _run_nudge,
        "add-notes": _run_add_notes,
        "add-note": _run_add_notes,
        "add-abc": _run_add_abc,
    }


async def _run_patch_notes(args: argparse.Namespace) -> int:
    try:
        operations = note_patches.load_note_patches(args.file)
    except note_patches.NotePatchError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_COMMAND_FAILED

    ordered = note_patches.execution_order(operations)
    if args.dry_run:
        print(layout.compact_summary({
            "operations": len(operations),
            "validated": True,
            "dryRun": True,
            "order": [op["op"] for op in ordered],
        }))
        return EXIT_OK

    results: list[dict[str, Any]] = []
    batch = batch_ops.validate_batch(note_patches.batch_operations(ordered))
    async with _client(args, plugins=[BRIDGE_PLUGIN]) as client:
        await _cli._require_bridge(client, _cli._batch_bridge_version(batch), "patch-notes")
        await _cli._assert_expected_score(client, args)
        backup = await _cli._backup(client, "before patch-notes")
        # One round trip and one undo step for the whole file.
        outcome = await _cli._apply_batch(client, batch, False)
        if "error" in outcome:
            raise BridgeError(
                f"patch-notes batch stopped: {outcome['error']} after "
                f"{outcome.get('applied', 0)} applied as one undo step; "
                f"restore from {backup.get('copy')}"
            )
        for operation, result in zip(batch, outcome.get("results", [])):
            results.append({"op": operation["op"], "result": result})

        saved = None
        if args.save:
            saved = await _cli._bridge(client, "Save")

    summary = {
        "operations": len(operations),
        "applied": len(results),
        "backup": backup.get("copy"),
        "results": results,
    }
    if saved is not None:
        summary["saved"] = saved.get("fileName", "")
    print(layout.compact_summary(summary))
    return EXIT_OK


async def _run_transpose(args: argparse.Namespace) -> int:
    degree, interval_type = compute_transposition(args.from_note, args.to_note, bool(args.up))
    degree += 7 * args.octaves * (1 if args.up else -1)

    built: dict[str, Any] = {}

    async def build(client: SibeliusClient) -> dict[str, Any]:
        info = await _cli._bridge(client, "GetScoreInfo")
        built.update(
            op="transpose",
            fromBar=args.from_bar or 1, toBar=args.to_bar or info["barCount"],
            topStaff=args.top_staff or 1, bottomStaff=args.bottom_staff or info["staffCount"],
            degree=degree, intervalType=interval_type,
        )
        return dict(built)

    def legacy(result: dict[str, Any]) -> dict[str, Any]:
        return {key: built[key] for key in (
            "degree", "intervalType", "fromBar", "toBar", "topStaff", "bottomStaff",
        )}

    return await _cli._run_op(args, build, legacy)


async def _run_copy_passage(args: argparse.Namespace) -> int:
    if args.beats or args.from_pos is not None or args.to_pos is not None:
        return await _run_copy_range(args)
    dest_pos = args.dest_pos or 0
    operation = {
        "op": "copy-passage", "fromBar": args.from_bar, "toBar": args.to_bar,
        "topStaff": args.top_staff, "bottomStaff": args.bottom_staff or args.top_staff,
        "destStaff": args.dest_staff, "destBar": args.dest_bar, "destPosition": dest_pos,
    }

    async def replacing(client: SibeliusClient, batch: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """What each destination bar holds now, against what the source bar brings."""
        rows = []
        for offset in range(operation["bottomStaff"] - operation["topStaff"] + 1):
            for bar_offset in range(operation["toBar"] - operation["fromBar"] + 1):
                source = await _cli._read_rows(client, operation["topStaff"] + offset, operation["fromBar"] + bar_offset,
                                          operation["fromBar"] + bar_offset)
                dest = await _cli._read_rows(client, operation["destStaff"] + offset, operation["destBar"] + bar_offset,
                                        operation["destBar"] + bar_offset)
                start = dest_pos if bar_offset == 0 else 0
                rows.append({
                    "staff": operation["destStaff"] + offset, "bar": operation["destBar"] + bar_offset,
                    "destinationBefore": copy_range.describe(dest, start, 10**9),
                    "copied": copy_range.describe(source, 0, 10**9),
                })
        return rows

    return await _cli._run_op(
        args, operation, lambda result: {k: v for k, v in operation.items() if k != "op"}, before_write=replacing,
    )


async def _run_copy_range(args: argparse.Namespace) -> int:
    """Copy part of one bar (a position or beat range) by composing ordinary batch ops."""
    if args.from_bar != args.to_bar:
        print("error: a position or beat range copies within one source bar; use whole bars for --from-bar/--to-bar spans",
              file=sys.stderr)
        return EXIT_COMMAND_FAILED
    top = args.top_staff
    bottom = args.bottom_staff or top
    try:
        async with _client(args, plugins=[BRIDGE_PLUGIN]) as client:
            await _cli._require_bridge(client, LYRIC_VERSE_BRIDGE_VERSION, "copy-passage with a range")
            await _cli._assert_expected_score(client, args)
            info = await _cli._bridge(client, "GetScoreInfo")
            numerator, denominator = _cli._time_signature_at(info, args.from_bar)
            note = None
            if args.beats:
                first, last = copy_range.parse_beats(args.beats)
                start, end = copy_range.beats_to_positions(first, last, numerator, denominator, args.beat_unit)
                note = copy_range.beat_note(numerator, denominator, args.beat_unit, first, last, start, end)
            else:
                start = args.from_pos or 0
                end = args.to_pos if args.to_pos is not None else numerator * copy_range.WHOLE // denominator
                if not 0 <= start < end:
                    raise copy_range.CopyRangeError(f"the range {start}-{end} is empty or backwards")
            dest_start = args.dest_pos if args.dest_pos is not None else start
            if note:
                print(note, file=sys.stderr)
            if (args.dest_staff, args.dest_bar) == (top, args.from_bar) and dest_start < end and start < dest_start + (end - start):
                raise copy_range.CopyRangeError("the destination range overlaps the source range on the same staff and bar")

            plans, sources = [], []
            for offset in range(bottom - top + 1):
                source = await _cli._read_rows(client, top + offset, args.from_bar, args.from_bar)
                dest_bars = await _cli._read_rows(client, args.dest_staff + offset, max(1, args.dest_bar - 1), args.dest_bar)
                dest = [r for r in dest_bars if r["bar"] == args.dest_bar]
                prior = [r for r in dest_bars if r["bar"] < args.dest_bar or (r["bar"] == args.dest_bar and r["position"] < dest_start)]
                sources.append(source)
                plans.append(copy_range.plan_staff(
                    top + offset, args.dest_staff + offset, args.from_bar, args.dest_bar,
                    source, dest, start, end, dest_start, prior,
                ))
            batch = batch_ops.validate_batch([op for plan in plans for op in plan.ops])
            await _cli._require_bridge(client, _cli._batch_bridge_version(batch), "copy-passage with a range")
            checked = await _cli._apply_batch(client, batch, True)
            if "error" in checked:
                raise BridgeError(checked["error"])
            report: dict[str, Any] = {
                "sourceBar": args.from_bar, "range": [start, end], "destBar": args.dest_bar, "destPosition": dest_start,
                "staves": [plan.summary() for plan in plans],
            }
            if note:
                report["beats"] = note
            if args.dry_run:
                print(json.dumps({"dryRun": True, "checked": len(batch), **report}, indent=2))
                return EXIT_OK
            backup = await _cli._backup(client, f"before {args.subcommand}")
            print(f"backed up: {backup['copy']}", file=sys.stderr)
            result = await _cli._apply_batch(client, batch, False)
            if "error" in result:
                raise BridgeError(f"{result['error']}; restore from {backup.get('copy')}")
            verified = True
            for offset, source in enumerate(sources):
                after = [r for r in await _cli._read_rows(client, args.dest_staff + offset, args.dest_bar, args.dest_bar)]
                verified = verified and copy_range.verify(source, after, start, end, dest_start)
            report["verified"] = verified
            if getattr(args, "save", False):
                saved = await _cli._bridge(client, "Save")
                print(f"saved: {saved.get('fileName', '')}", file=sys.stderr)
    except (copy_range.CopyRangeError, batch_ops.BatchError, BridgeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_COMMAND_FAILED
    for plan in plans:
        for warning in plan.warnings:
            print(f"warning: staff {plan.dest_staff}: {warning}", file=sys.stderr)
    print(json.dumps(report, indent=2))
    return EXIT_OK


async def _run_set_note(args: argparse.Namespace) -> int:
    def legacy(result: dict[str, Any]) -> dict[str, Any]:
        missing = {"name": "", "tied": False, "pitch": args.new_pitch}
        old = next((n for n in _cli._notes(result["before"]) if n["pitch"] == args.old_pitch), missing)
        new = next((n for n in _cli._notes(result["after"]) if n["pitch"] == args.new_pitch), missing)
        return {
            "oldPitch": args.old_pitch, "oldName": old["name"],
            "newPitch": new["pitch"], "newName": new["name"], "tied": old["tied"],
        }

    return await _cli._run_op(
        args,
        {"op": "set-pitch", **_cli._address(args), "oldPitch": args.old_pitch, "newPitch": args.new_pitch},
        legacy,
    )


async def _run_tie(args: argparse.Namespace) -> int:
    return await _cli._run_op(
        args,
        {"op": "tie", **_cli._address(args), "remove": args.remove},
        lambda result: {
            **_cli._address(args), "tied": not args.remove, "notes": len(_cli._notes(result["after"])),
        },
    )


async def _run_delete_object(args: argparse.Namespace) -> int:
    return await _cli._run_op(
        args, {"op": "delete", **_cli._address(args)}, lambda result: {"deleted": result["before"]}
    )


async def _run_delete_voice(args: argparse.Namespace) -> int:
    return await _cli._run_op(
        args,
        {"op": "delete-voice", "fromBar": args.from_bar, "toBar": args.to_bar,
         "staff": args.staff, "voice": args.voice},
        lambda result: {
            "fromBar": args.from_bar, "toBar": args.to_bar, "staff": args.staff,
            "deletedVoice": args.voice, "objects": result["after"]["objects"],
        },
    )


async def _run_clear_bars(args: argparse.Namespace) -> int:
    op: dict[str, Any] = {
        "op": "clear-bars", "fromBar": args.from_bar, "toBar": args.to_bar, "staff": args.staff,
    }
    if args.voice is not None:
        op["voice"] = args.voice
    return await _cli._run_op(args, op, lambda result: result["after"])


async def _run_flip_stem(args: argparse.Namespace) -> int:
    return await _cli._run_op(
        args,
        {"op": "flip-stem", **_cli._address(args)},
        lambda result: {"flipped": True, **_cli._address(args)},
    )


async def _run_bracket(args: argparse.Namespace) -> int:
    return await _cli._run_op(
        args,
        {"op": "bracket", **_cli._address(args), "remove": args.remove},
        lambda result: {
            **_cli._address(args), "bracketed": not args.remove, "notes": len(_cli._notes(result["after"])),
        },
    )


async def _run_beam(args: argparse.Namespace) -> int:
    return await _cli._run_op(
        args,
        {"op": "beam", "staff": args.staff, "bar": args.bar,
         "firstIndex": args.from_index, "lastIndex": args.to_index},
        lambda result: result["after"],
        BEAM_RESULT_BRIDGE_VERSION,
    )


async def _run_nudge(args: argparse.Namespace) -> int:
    return await _cli._run_op(
        args,
        {"op": "nudge", **_cli._address(args), "dx": args.dx, "dy": args.dy},
        lambda result: result["after"],
        NUDGE_BRIDGE_VERSION,
    )


async def _run_add_notes(args: argparse.Namespace) -> int:
    if getattr(args, "notes", None):
        seq = music.parse_note_sequence(args.notes)
        return await _cli._run_write(
            args,
            "AddNoteSequence",
            [args.staff, args.bar, getattr(args, "pos", 0), seq, args.voice],
        )
    if not getattr(args, "pitches", None):
        print("error: either --pitch/--pitches or --notes is required", file=sys.stderr)
        return EXIT_COMMAND_FAILED
    pitches = [music.parse_pitch(p.strip()) for p in args.pitches.split(",") if p.strip()]
    duration = music.parse_duration(args.duration)
    position = getattr(args, "pos", 0)
    voice = args.voice or 1
    return await _cli._run_op(
        args,
        {
            "op": "add-note", "staff": args.staff, "bar": args.bar, "position": position,
            "duration": duration, "pitches": pitches, "voice": voice,
            "tied": bool(getattr(args, "tied", False)),
        },
        lambda result: {
            "staff": args.staff, "bar": args.bar, "position": position,
            "duration": duration, "voice": voice,
            "notes": [
                {"pitch": n["pitch"], "name": n["name"], "tied": n["tied"]}
                for n in _cli._notes(result["after"])
                if n["pitch"] in pitches
            ],
        },
    )


async def _run_add_abc(args: argparse.Namespace) -> int:
    abc_text = args.abc or getattr(args, "abc_opt", None)
    if not abc_text:
        print("error: ABC notation string is required (positional or --abc)", file=sys.stderr)
        return EXIT_COMMAND_FAILED

    async with _client(args, plugins=[BRIDGE_PLUGIN]) as client:
        await _cli._check_bridge_version(client)
        info = await _cli._bridge(client, "GetScoreInfo")
        await _cli._assert_expected_score(client, args, info)
        default_key = "C"
        for ks in info.get("keySignatures", []):
            if ks.get("bar", 1) <= args.bar:
                default_key = ks.get("name", "C")

        parsed = abc_notation.parse_abc_snippet(abc_text, default_key=default_key)

        sequence = []
        for n in parsed["notes"]:
            actual_bar = args.bar + (n["bar"] - 1)
            actual_pos = n["position"]
            if n["bar"] == 1:
                actual_pos += getattr(args, "pos", 0)
            sequence.append({
                "bar": actual_bar,
                "position": actual_pos,
                "duration": n["duration"],
                "pitches": n["pitches"],
                "tied": n["tied"],
            })

        backup = await _cli._backup(client, f"before {args.subcommand}")
        print(f"backed up: {backup['copy']}", file=sys.stderr)

        note_result = await _cli._bridge(
            client,
            "AddNoteSequence",
            [args.staff, args.bar, getattr(args, "pos", 0), sequence, args.voice],
        )

        added_lyrics = []
        for lyr in parsed["lyrics"]:
            actual_bar = args.bar + (lyr["bar"] - 1)
            actual_pos = lyr["position"]
            if lyr["bar"] == 1:
                actual_pos += getattr(args, "pos", 0)
            lyr_res = await _cli._bridge(
                client,
                "AddLyric",
                [args.staff, actual_bar, actual_pos, lyr["duration"], lyr["text"], lyr["syllableType"]],
            )
            added_lyrics.append(lyr_res)

        if getattr(args, "save", False):
            saved = await _cli._bridge(client, "Save")
            print(f"saved: {saved.get('fileName', '')}", file=sys.stderr)

    result = {
        "notes": note_result,
        "lyricsCount": len(added_lyrics),
    }
    print(json.dumps(result, indent=2))
    return EXIT_OK
