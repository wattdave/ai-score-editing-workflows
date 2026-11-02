"""MusicXML commands: export, split-parts (demix), round, read-abc."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ai_score_editing import layout
from ai_score_editing.cli_common import canonical_format
from ai_score_editing.sibelius import launcher, service
from ai_score_editing.sibelius.bridge import BRIDGE_PLUGIN, EXPORT_FORMATS, BridgeError
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
    read_abc = sub.add_parser("read-abc", help="format bar contents as standard ABC notation")
    read_abc.add_argument("--staff", type=int, default=1, help="staff number, from 1")
    read_abc.add_argument("--from", dest="from_bar", type=int, help="first bar, from 1")
    read_abc.add_argument("--to", dest="to_bar", type=int, help="last bar (default: same as --from)")
    read_abc.add_argument("--bar", type=int, help="specific bar number")
    read_abc.add_argument("--bars", type=str, help="bar range, e.g. '1-3' or '5'")
    export = sub.add_parser("export", help="export the active (or a given) score to another format")
    export.add_argument("--format", type=canonical_format, choices=sorted(EXPORT_FORMATS), default="musicxml")
    export.add_argument(
        "--path", "--out", dest="out", help="output path (default: next to the source file); --out is the old name"
    )
    export.add_argument("--file", dest="sib_file", help=".sib file to open first (default: active score)")
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
    return {
        "export": _run_export,
        "read-abc": _run_read_abc,
        "split-parts": _run_split_parts,
        "demix": _run_split_parts,
        "round": _run_round,
    }


async def _run_read_abc(args: argparse.Namespace) -> int:
    setattr(args, "abc", True)
    return await _cli._run_read(args)

async def _run_export(args: argparse.Namespace) -> int:
    async with _client(args, plugins=[BRIDGE_PLUGIN]) as client:
        await _cli._check_bridge_version(client)
        if args.sib_file:
            source = Path(args.sib_file).expanduser().resolve()
            if not source.exists():
                print(f"error: {source} does not exist", file=sys.stderr)
                return EXIT_COMMAND_FAILED
            opened = await _cli._bridge(client, "OpenScore", [str(source)])
            print(f"opened: {opened['fileName']}", file=sys.stderr)
        try:
            result = await service.export(_cli._CliBridge(client), args.format, args.out)
        except BridgeError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return EXIT_COMMAND_FAILED
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
            await _cli._check_bridge_version(client)
            if source_path is not None:
                opened = await _cli._bridge(client, "OpenScore", [str(source_path)])
                print(f"opened: {opened.get('fileName', str(source_path))}", file=sys.stderr)
            info = await _cli._bridge(client, "GetScoreInfo")
            saveas_type, _ = EXPORT_FORMATS["musicxml"]
            await _cli._bridge(client, "ExportScore", [str(exported_xml), saveas_type])

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
