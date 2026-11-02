"""Lyrics commands: read-lyrics, check-lyrics, set-lyric, patch-lyrics, set-lyric-style."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from typing import Any

from ai_score_editing import agent_output, batch_lyrics, batch_ops, lyrics
from ai_score_editing.barrange import parse_bar_range
from ai_score_editing.sibelius.bridge import BATCH_BRIDGE_VERSION, BRIDGE_PLUGIN
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
    read_lyrics = sub.add_parser("read-lyrics", help="list all lyrics with addresses")
    read_lyrics.add_argument("--staff", type=int, default=0, help="staff number (0 = all)")
    read_lyrics.add_argument("--from", dest="from_bar", type=int, help="first bar (from 1)")
    read_lyrics.add_argument("--to", dest="to_bar", type=int, help="last bar")
    read_lyrics.add_argument("--bar", type=int, help="specific bar number")
    read_lyrics.add_argument("--bars", type=str, help="bar range, e.g. '1-3' or '5'")
    read_lyrics.add_argument(
        "--verse",
        type=int,
        help="filter to a specific verse/line number (1-based; 0 = all)",
    )
    read_lyrics.add_argument(
        "--words",
        action="store_true",
        help="format syllables into words grouped by staff and verse/bar",
    )
    read_lyrics.add_argument(
        "--by-bar",
        action="store_true",
        help="when used with --words, format strictly bar-by-bar rather than grouped by verse",
    )
    read_lyrics.add_argument(
        "--compact",
        action="store_true",
        help="print one address-preserving line per lyric",
    )
    check_lyrics = sub.add_parser(
        "check-lyrics",
        help="lint score lyrics for typos, cross-voice divergence, collisions, and missing text",
    )
    check_lyrics.add_argument("--staff", type=int, default=0, help="staff number (0 = all)")
    check_lyrics.add_argument("--from", dest="from_bar", type=int, help="first bar (from 1)")
    check_lyrics.add_argument("--to", dest="to_bar", type=int, help="last bar")
    check_lyrics.add_argument("--bar", type=int, help="specific bar number")
    check_lyrics.add_argument("--bars", type=str, help="bar range, e.g. '1-3' or '5'")
    check_lyrics.add_argument(
        "--verse",
        type=int,
        help="filter to a specific verse/line number (1-based; 0 = all)",
    )
    set_lyric = sub.add_parser("set-lyric", help="rewrite one lyric syllable (backs up first)")
    set_lyric.add_argument("--staff", type=int, required=True)
    set_lyric.add_argument("--bar", type=int, required=True)
    set_lyric.add_argument("--index", type=int, required=True)
    set_lyric.add_argument("--text", required=True)
    set_lyric.add_argument("--font", help="override font family, e.g. 'Big Caslon'")
    set_lyric.add_argument(
        "--font-size",
        type=int,
        help="styled-string font size in tenths of a point (e.g. 110 = 11 pt)",
    )
    set_lyric.add_argument("--raw", action="store_true", help="do not preserve existing font/size tags")
    set_lyric.add_argument(
        "--allow-style-reset",
        action="store_true",
        help="acknowledge that --raw may reset the lyric to its text style",
    )
    set_lyric.add_argument("--save", action="store_true", help="save active score in Sibelius after change")
    patch_lyrics = sub.add_parser(
        "patch-lyrics",
        help="apply and verify a validated JSON batch of lyric corrections",
    )
    patch_lyrics.add_argument("--file", required=True, help="JSON patch array")
    patch_lyrics.add_argument("--font", help="default font family for patched lyrics")
    patch_lyrics.add_argument(
        "--font-size",
        type=int,
        help="default styled-string font size in tenths of a point",
    )
    patch_lyrics.add_argument(
        "--save", action="store_true", help="save active score after all patches verify"
    )
    set_lyric_style = sub.add_parser(
        "set-lyric-style", help="change a lyric item's verse/style line (backs up first)"
    )
    set_lyric_style.add_argument("--staff", type=int, required=True)
    set_lyric_style.add_argument("--bar", type=int, required=True)
    set_lyric_style.add_argument("--index", type=int, required=True)
    set_lyric_style.add_argument(
        "--style",
        required=True,
        help="style identifier or alias: verse1, verse2, verse3, chorus, above, etc.",
    )
    set_lyric_style.add_argument(
        "--save", action="store_true", help="save active score in Sibelius after change"
    )
    return {
        "read-lyrics": _run_read_lyrics,
        "check-lyrics": _run_check_lyrics,
        "set-lyric": _run_set_lyric,
        "patch-lyrics": _run_patch_lyrics,
        "set-lyric-style": _run_set_lyric_style,
    }


async def _run_read_lyrics(args: argparse.Namespace) -> int:
    from_b, to_b = parse_bar_range(
        bar=getattr(args, "bar", None),
        bars=getattr(args, "bars", None),
        from_bar=getattr(args, "from_bar", None),
        to_bar=getattr(args, "to_bar", None),
    )
    verse = getattr(args, "verse", None)
    if verse == 0:
        verse = None
    by_bar = getattr(args, "by_bar", False)

    if getattr(args, "compact", False) and getattr(args, "words", False):
        print("error: --compact and --words cannot be combined", file=sys.stderr)
        return EXIT_COMMAND_FAILED

    async with _client(args, plugins=[BRIDGE_PLUGIN]) as client:
        raw_lyrics = await _cli._bridge(
            client, "ReadLyrics", [args.staff, from_b or 0, to_b or 0]
        )
        filtered = lyrics.filter_lyrics(raw_lyrics, from_bar=from_b, to_bar=to_b, verse=verse)

        if getattr(args, "compact", False):
            annotated = lyrics.infer_syllable_lines(filtered)
            print(agent_output.render_compact_lyrics(annotated))
            return EXIT_OK

        if args.words:
            if args.json:
                print(json.dumps(filtered))
                return EXIT_OK
            staves_info = await _cli._bridge(client, "GetStaves")
            names = {
                s.get("staffNum", s.get("staffNumber", i + 1)): (
                    s.get("fullInstrumentName")
                    or s.get("instrumentName")
                    or s.get("name")
                    or f"Staff {s.get('staffNum', i + 1)}"
                )
                for i, s in enumerate(staves_info)
            }
            print(lyrics.format_lyrics(filtered, names, by_bar=by_bar, verse=verse))
            return EXIT_OK

    print(json.dumps(filtered) if args.json else json.dumps(filtered, indent=2))
    return EXIT_OK


async def _run_check_lyrics(args: argparse.Namespace) -> int:
    from_b, to_b = parse_bar_range(
        bar=getattr(args, "bar", None),
        bars=getattr(args, "bars", None),
        from_bar=getattr(args, "from_bar", None),
        to_bar=getattr(args, "to_bar", None),
    )
    verse = getattr(args, "verse", None)
    if verse == 0:
        verse = None

    async with _client(args, plugins=[BRIDGE_PLUGIN]) as client:
        info = await _cli._bridge(client, "GetScoreInfo")
        staves_info = await _cli._bridge(client, "GetStaves")
        names = {
            s.get("staffNum", s.get("staffNumber", i + 1)): (
                s.get("fullInstrumentName")
                or s.get("instrumentName")
                or s.get("name")
                or f"Staff {s.get('staffNum', i + 1)}"
            )
            for i, s in enumerate(staves_info)
        }
        raw_lyrics = await _cli._bridge(
            client, "ReadLyrics", [args.staff, from_b or 0, to_b or 0]
        )
        filtered_lyrics = lyrics.filter_lyrics(
            raw_lyrics, from_bar=from_b, to_bar=to_b, verse=verse
        )

        bar_count = info.get("barCount", 0)
        start_b = from_b or 1
        end_b = to_b or bar_count

        staff_bars: dict[int, list[dict[str, Any]]] = {}
        target_staves = (
            [args.staff]
            if args.staff > 0
            else sorted({s.get("staff", 1) for s in filtered_lyrics})
        )
        for s_num in target_staves:
            if bar_count > 0 and end_b >= start_b:
                bars = await _cli._bridge(client, "ReadBars", [s_num, start_b, end_b])
                staff_bars[s_num] = bars

        score_default_font = info.get("mainTextFontName")
        typography = lyrics.analyze_lyric_typography(
            filtered_lyrics, score_default_font=score_default_font, staff_names=names
        )
        issues = lyrics.lint_lyrics(
            filtered_lyrics, names, staff_bars, score_default_font=score_default_font
        )

    if args.json:
        print(json.dumps(issues, indent=2))
    else:
        print(lyrics.format_lint_report(issues, typography=typography))

    has_errors = any(issue.get("severity") == "error" for issue in issues)
    return EXIT_COMMAND_FAILED if has_errors else EXIT_OK


async def _run_set_lyric(args: argparse.Namespace) -> int:
    if getattr(args, "raw", False) and not getattr(args, "allow_style_reset", False):
        print(
            "error: --raw can reset lyric typography; pass --allow-style-reset to acknowledge",
            file=sys.stderr,
        )
        return EXIT_COMMAND_FAILED
    text = args.text
    if getattr(args, "font", None):
        size = getattr(args, "font_size", None) or 110
        text = f"\\f{args.font}\\\\s{size}\\{text}"
    elif getattr(args, "font_size", None):
        text = f"\\s{args.font_size}\\{text}"
    elif not getattr(args, "raw", False) and not text.startswith("\\f"):
        try:
            async with _client(args, plugins=[BRIDGE_PLUGIN]) as client:
                await _cli._check_bridge_version(client)
                score_info = await _cli._bridge(client, "GetScoreInfo")
                score_default_font = score_info.get("mainTextFontName") if isinstance(score_info, dict) else None

                # Read lyrics on this staff to find the predominant font across the part
                staff_lyrics = await _cli._bridge(client, "ReadLyrics", [args.staff, 0, 0])
                typography = lyrics.analyze_lyric_typography(
                    staff_lyrics, score_default_font=score_default_font
                )
                pred_font = typography.get("predominant_font") or score_default_font or "Times New Roman"
                pred_size = typography.get("predominant_size") or 110

                existing = next(
                    (s for s in staff_lyrics if s.get("bar") == args.bar and s.get("index") == args.index),
                    None,
                )
                chosen_font = None
                chosen_size = None

                if existing:
                    existing_font, existing_size = lyrics.extract_font_and_size(existing)
                    if existing_font and (not pred_font or existing_font == pred_font):
                        chosen_font = existing_font
                        chosen_size = existing_size
                    elif pred_font:
                        chosen_font = pred_font
                        chosen_size = pred_size or existing_size
                elif pred_font:
                    chosen_font = pred_font
                    chosen_size = pred_size

                effective_font = chosen_font or pred_font
                if effective_font == "BigCaslon-Medium":
                    effective_font = "Big Caslon"
                effective_size = chosen_size or pred_size or 110

                text = f"\\f{effective_font}\\\\s{effective_size}\\{text}"
        except Exception:
            pass

    return await _cli._run_op(
        args,
        {"op": "set", **_cli._address(args), "type": "LyricItem", "prop": "Text", "value": text},
        lambda result: {"oldText": result["before"]["text"], "newText": result["after"]["text"]},
    )


async def _run_patch_lyrics(args: argparse.Namespace) -> int:
    try:
        patches = batch_lyrics.load_lyric_patches(args.file)
        if getattr(args, "font", None) is not None and not args.font.strip():
            raise batch_lyrics.BatchLyricsError("--font must be a non-empty string")
        if getattr(args, "font_size", None) is not None and args.font_size < 1:
            raise batch_lyrics.BatchLyricsError("--font-size must be a positive integer")
    except batch_lyrics.BatchLyricsError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_COMMAND_FAILED

    ranges = batch_lyrics.affected_lyric_ranges(patches)
    needs_inference = any(
        patch.font is None
        and getattr(args, "font", None) is None
        and patch.font_size is None
        and getattr(args, "font_size", None) is None
        and not patch.text.startswith("\\f")
        for patch in patches
    )

    async with _client(args, plugins=[BRIDGE_PLUGIN]) as client:
        await _cli._check_bridge_version(client)
        info: dict[str, Any] | None = None
        if getattr(args, "expect_file", None) or needs_inference:
            info = await _cli._bridge(client, "GetScoreInfo")
        await _cli._assert_expected_score(client, args, info)

        before: list[dict[str, Any]] = []
        for affected in ranges:
            before.extend(
                await _cli._bridge(
                    client,
                    "ReadLyrics",
                    [affected.staff, affected.from_bar, affected.to_bar],
                )
            )
        try:
            batch_lyrics.validate_patch_targets(patches, before)
        except batch_lyrics.BatchLyricsError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return EXIT_COMMAND_FAILED

        staff_lyrics: dict[int, list[dict[str, Any]]] = {}
        if needs_inference:
            for staff in sorted({patch.staff for patch in patches}):
                staff_lyrics[staff] = await _cli._bridge(client, "ReadLyrics", [staff, 0, 0])

        score_default_font = info.get("mainTextFontName") if info else None
        try:
            rendered = [
                batch_lyrics.resolve_lyric_text(
                    patch,
                    default_font=getattr(args, "font", None),
                    default_font_size=getattr(args, "font_size", None),
                    staff_lyrics=staff_lyrics.get(patch.staff, before),
                    score_default_font=score_default_font,
                )
                for patch in patches
            ]
        except batch_lyrics.BatchLyricsError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return EXIT_COMMAND_FAILED

        # One checked batch: nothing changes unless every target is still a
        # lyric, and the whole patch set is one undo step.
        batch = batch_ops.validate_batch([
            {"op": "set", "staff": patch.staff, "bar": patch.bar, "index": patch.index,
             "type": "LyricItem", "prop": "Text", "value": text}
            for patch, text in zip(patches, rendered)
        ])
        await _cli._require_bridge(client, BATCH_BRIDGE_VERSION, args.subcommand)
        checked = await _cli._apply_batch(client, batch, True)
        if "error" in checked:
            print(f"error: {checked['error']}; nothing was changed", file=sys.stderr)
            return EXIT_COMMAND_FAILED
        backup = await _cli._backup(client, f"before {args.subcommand}")
        outcome = await _cli._apply_batch(client, batch, False)
        if "error" in outcome:
            print(
                f"error: lyric batch stopped after {outcome.get('applied', 0)}/{len(patches)} writes "
                f"(one undo step); backup: {backup.get('copy', '')}; {outcome['error']}",
                file=sys.stderr,
            )
            return EXIT_COMMAND_FAILED
        write_results = [{"oldText": result["before"]["text"]} for result in outcome["results"]]

        after: list[dict[str, Any]] = []
        for affected in ranges:
            after.extend(
                await _cli._bridge(
                    client,
                    "ReadLyrics",
                    [affected.staff, affected.from_bar, affected.to_bar],
                )
            )
        verification = batch_lyrics.verify_lyric_patches(patches, after)

        saved = None
        if all(item.verified for item in verification) and getattr(args, "save", False):
            saved = await _cli._bridge(client, "Save")

    summary = batch_lyrics.build_batch_summary(
        patches, write_results, verification, backup=backup, saved=saved
    )
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, separators=(",", ":")))
    else:
        print(batch_lyrics.format_compact_summary(summary))
    return (
        EXIT_OK
        if summary["verified"] == summary["patched"]
        else EXIT_COMMAND_FAILED
    )


async def _run_set_lyric_style(args: argparse.Namespace) -> int:
    return await _cli._run_write(
        args, "SetLyricStyle", [args.staff, args.bar, args.index, args.style]
    )
