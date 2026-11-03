"""Inspection commands: score-info, staves, selection, inspect, score-snapshot, proofread,
text-styles, bridge-version, read, query."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from typing import Any

from ai_score_editing.sibelius import agent_output
from ai_score_editing.workflows import abc_notation
from ai_score_editing.core import lyrics
from ai_score_editing.core.barrange import parse_bar_range
from ai_score_editing.cli_common import DEFAULT_LIMIT
from ai_score_editing.sibelius import protocol, service
from ai_score_editing.sibelius.bridge import BRIDGE_PLUGIN, TEXT_FONTS_BRIDGE_VERSION, BridgeError
from ai_score_editing.sibelius.commands._common import EXIT_COMMAND_FAILED, EXIT_OK
from ai_score_editing.sibelius.commands._common import client as _client


class _Cli:
    """Late lookup of ``sibelius.cli`` attributes.

    Tests and skill scripts patch ``cli._bridge``, ``cli._require_bridge``,
    ``cli._check_bridge_version`` and friends, so handlers resolve them at call time.
    """

    def __getattr__(self, name: str) -> Any:
        from ai_score_editing.sibelius import cli

        return getattr(cli, name)


_cli = _Cli()


def register(sub: Any) -> dict[str, Callable[..., Any]]:
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
    query.add_argument(
        "--limit", type=int, default=DEFAULT_LIMIT, help=f"maximum objects to return (default: {DEFAULT_LIMIT})"
    )
    sub.add_parser("bridge-version", help="report the installed bridge plug-in version")
    return {
        "score-info": _run_score_info,
        "text-styles": _run_text_styles,
        "staves": _run_staves,
        "selection": _run_selection,
        "inspect": _run_inspect,
        "score-snapshot": _run_score_snapshot,
        "proofread": _run_proofread,
        "read": _run_read,
        "query": _run_query,
        "bridge-version": _run_bridge_version,
    }


async def _run_score_info(args: argparse.Namespace) -> int:
    return await _cli._run_bridge_call(args, "GetScoreInfo")


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
    from ai_score_editing.sibelius import text_styles

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
            await _cli._require_bridge(client, TEXT_FONTS_BRIDGE_VERSION, "text-styles")
            info = await _cli._bridge(client, "GetScoreInfo")
            found = []
            for system, staves in ((True, [0]), (False, [])):
                selector["staves"] = staves
                result = await _cli._bridge(client, "Query", [selector])
                found += [(obj.get("styleId", ""), system) for obj in result["objects"]]
            probed = await _cli._bridge(client, "GetTextStyleFonts", [text_styles.style_requests(found)])
    except BridgeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_COMMAND_FAILED
    print(json.dumps(text_styles.build_report(info, probed["styles"]), indent=None if args.json else 2))
    return EXIT_OK


async def _run_staves(args: argparse.Namespace) -> int:
    return await _cli._run_bridge_call(args, "GetStaves")


async def _run_selection(args: argparse.Namespace) -> int:
    return await _cli._run_bridge_call(args, "GetSelectionInfo")


async def _run_inspect(args: argparse.Namespace) -> int:
    async with _client(args, plugins=[BRIDGE_PLUGIN]) as client:
        await _cli._check_bridge_version(client)
        info = await _cli._bridge(client, "GetScoreInfo")
        staves = await _cli._bridge(client, "GetStaves")
        selection = await _cli._bridge(client, "GetSelectionInfo")
    projected = agent_output.project_inspect(info, staves, selection)
    if args.json:
        print(json.dumps(projected, ensure_ascii=False, separators=(",", ":")))
    else:
        print(agent_output.render_compact_inspect(info, staves, selection))
    return EXIT_OK


async def _run_score_snapshot(args: argparse.Namespace) -> int:
    from_b, to_b = parse_bar_range(bars=getattr(args, "bars", None))
    async with _client(args, plugins=[BRIDGE_PLUGIN]) as client:
        await _cli._check_bridge_version(client)
        info = await _cli._bridge(client, "GetScoreInfo")
        staves = await _cli._bridge(client, "GetStaves")
        selection = await _cli._bridge(client, "GetSelectionInfo")

        barlines: list[dict[str, Any]] = []
        if args.barlines:
            bar_start = from_b or 1
            bar_end = to_b or int(info.get("barCount", bar_start))
            barlines = await _cli._bridge(client, "GetSpecialBarlines", [bar_start, bar_end])

        lyric_data: list[dict[str, Any]] | None = None
        if args.lyrics:
            lyric_data = await _cli._bridge(
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
        await _cli._check_bridge_version(client)
        info = await _cli._bridge(client, "GetScoreInfo")
        staves_info = await _cli._bridge(client, "GetStaves")
        selection = await _cli._bridge(client, "GetSelectionInfo")
        names = {
            s.get("staffNum", s.get("staffNumber", i + 1)): (
                s.get("fullInstrumentName")
                or s.get("instrumentName")
                or s.get("name")
                or f"Staff {s.get('staffNum', i + 1)}"
            )
            for i, s in enumerate(staves_info)
        }
        raw_lyrics = await _cli._bridge(client, "ReadLyrics", [args.staff, from_b or 0, to_b or 0])
        filtered_lyrics = lyrics.filter_lyrics(raw_lyrics, from_bar=from_b, to_bar=to_b, verse=verse)

        bar_count = int(info.get("barCount", 0))
        start_b = from_b or 1
        end_b = to_b or bar_count
        target_staves = [args.staff] if args.staff > 0 else sorted({s.get("staff", 1) for s in filtered_lyrics})
        staff_bars: dict[int, list[dict[str, Any]]] = {}
        for staff_num in target_staves:
            if end_b >= start_b:
                staff_bars[staff_num] = await _cli._bridge(client, "ReadBars", [staff_num, start_b, end_b])

        barlines: list[dict[str, Any]] = []
        if args.barlines:
            barlines = await _cli._bridge(client, "GetSpecialBarlines", [start_b, end_b])

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
            result = await service.query(_cli._CliBridge(client), staves=args.staff, **params)
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
            await _cli._check_bridge_version(client)
            info = await _cli._bridge(client, "GetScoreInfo")
            staves_info = await _cli._bridge(client, "GetStaves")
            # An unaddressed ABC export is expected to represent the whole
            # staff.  Ordinary `read` retains its one-bar default.
            if from_b is None and to_b is None:
                end_bar = info.get("barCount", end_bar)
            bars = await _cli._bridge(client, "ReadBars", [args.staff, start_bar, end_bar])
            raw_lyrics = await _cli._bridge(
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

    return await _cli._run_bridge_call(args, "ReadBars", [args.staff, start_bar, end_bar])


async def _run_bridge_version(args: argparse.Namespace) -> int:
    return await _cli._run_bridge_call(args, "GetBridgeVersion")
