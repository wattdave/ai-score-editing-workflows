"""Audio commands: rehearsal-mixes, proof-mixes, playback-sounds, verify-render."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ai_score_editing import mix_proof, rehearsal_mix
from ai_score_editing.cli_common import canonical_format
from ai_score_editing.sibelius.bridge import (
    AUDIO_EXPORT_BRIDGE_VERSION,
    BRIDGE_PLUGIN,
    EXPORT_FORMATS,
    PLAYBACK_SOUNDS_BRIDGE_VERSION,
    BridgeError,
)
from ai_score_editing.sibelius.commands._common import EXIT_COMMAND_FAILED, EXIT_OK
from ai_score_editing.sibelius.commands._common import client as _client


# Collaborators that tests and skill scripts patch on ``sibelius.cli``. They are
# looked up there at call time (like ``_common.client``), so patches still work.
def _cli() -> Any:
    from ai_score_editing.sibelius import cli

    return cli


async def _bridge(client: Any, *rest: Any) -> Any:
    return await _cli()._bridge(client, *rest)


async def _require_bridge(client: Any, *rest: Any) -> Any:
    return await _cli()._require_bridge(client, *rest)


async def _check_bridge_version(client: Any) -> Any:
    return await _cli()._check_bridge_version(client)


async def _assert_expected_score(client: Any, *rest: Any) -> Any:
    return await _cli()._assert_expected_score(client, *rest)


def _export_path(*a: Any) -> Path:
    return _cli()._export_path(*a)


def register(sub: Any) -> dict[str, Callable[..., Any]]:
    mixes = sub.add_parser(
        "rehearsal-mixes",
        help="export rehearsal MP3s: all voices, each voice alone, each voice louder",
        description=(
            "Export one audio stem per staff, equalize the voices (staves with lyrics), "
            "and mix: all voices; each voice alone with accompaniment; each voice at 3x "
            "over the others. Accompaniment keeps its Sibelius level. Needs ffmpeg."
        ),
    )
    mixes.add_argument("--out", required=True, help="directory for the MP3s")
    mixes.add_argument("--file", dest="sib_file", help=".sib file to open first (default: active score)")
    mixes.add_argument("--bitrate", default=rehearsal_mix.DEFAULT_BITRATE, help="MP3 bit rate (default: %(default)s)")
    mixes.add_argument(
        "--name", action="append", default=[], metavar="STAFF=NAME",
        help="name a staff in the file names, e.g. --name 1=Soprano (repeatable)",
    )
    mixes.add_argument("--keep-stems", action="store_true", help="keep the per-staff AIFF stems in --out/stems")
    mixes.add_argument(
        "--loudness", type=float, default=rehearsal_mix.TARGET_LUFS, metavar="LUFS",
        help="integrated loudness for every file (default: %(default)s); lowered if a file would clip",
    )
    mixes.add_argument(
        "--all-parts", action="store_true",
        help="treat every staff as a part to mix, not only staves with lyrics (for instrumental scores)",
    )
    mixes.add_argument(
        "--require-sound", metavar="SOUND_SET",
        help="refuse to export unless every voice plays a sound set containing this, e.g. Cantai",
    )
    mixes.add_argument("--no-proof", action="store_true", help="skip the proof-listening checks after mixing")
    proof = sub.add_parser(
        "proof-mixes",
        help="check a folder of rehearsal mixes for shared audio, repeats, level jumps and mismatched files",
        description=(
            "Proof-listen to rehearsal mixes (needs ffmpeg). Finds the same audio in different voices' "
            "files, stretches that repeat sample for sample, runs far louder than the rest of a file, "
            "and files that differ in length or loudness. With --stems, also checks that each mix is "
            "the stems at fixed gains. Exits non-zero on errors."
        ),
    )
    proof.add_argument("folder", help="folder of MP3s named '<score> - <voice> only.mp3' and so on")
    proof.add_argument("--stems", help="folder of the per-staff stems (rehearsal-mixes --keep-stems)")
    proof.add_argument("--json", action="store_true", help="print the report as JSON")
    sounds = sub.add_parser(
        "playback-sounds",
        help="list each staff's playback sound set, patch and sound ID, and any Mixer override",
    )
    sounds.add_argument("--require", metavar="SOUND_SET",
                        help="exit non-zero unless every staff's sound set contains this")
    verify_render = sub.add_parser(
        "verify-render",
        help="export a score and verify that the rendered files are present and non-empty",
    )
    verify_render.add_argument("--format", type=canonical_format, choices=sorted(EXPORT_FORMATS), default="png")
    verify_render.add_argument("--out", help="output path (default: next to the source file)")
    verify_render.add_argument("--file", dest="sib_file", help=".sib file to open first (default: active score)")
    verify_render.add_argument("--expect-pages", type=int, help="require exactly this many rendered files")
    verify_render.add_argument("--min-bytes", type=int, default=1, help="minimum size for each rendered file")
    verify_render.add_argument("--sha256", action="store_true", help="include SHA-256 hashes in the report")
    return {
        "rehearsal-mixes": _run_rehearsal_mixes,
        "proof-mixes": _run_proof_mixes,
        "playback-sounds": _run_playback_sounds,
        "verify-render": _run_verify_render,
    }


def _print_playback_sounds(staves: list[dict]) -> None:
    for staff in staves:
        override = f"  [Mixer override {staff['override']}]" if staff.get("override") else ""
        for i, change in enumerate(staff.get("sounds", [])):
            where = f"staff {staff['staffNum']}" if i == 0 else f"  from bar {change['bar']}"
            print(f"{where}: {change['soundSet']} / {change['patch']} ({change['actualSoundId']})"
                  f"{override if i == 0 else ''}", file=sys.stderr)


async def _run_playback_sounds(args: argparse.Namespace) -> int:
    async with _client(args, plugins=[BRIDGE_PLUGIN]) as client:
        await _require_bridge(client, PLAYBACK_SOUNDS_BRIDGE_VERSION, "playback-sounds")
        staves = await _bridge(client, "GetPlaybackSounds")
    _print_playback_sounds(staves)
    print(json.dumps(staves, indent=2))
    if args.require:
        problems = rehearsal_mix.sound_problems(staves, {s["staffNum"] for s in staves}, args.require)
        if problems:
            print(f"error: not every staff plays {args.require}:", file=sys.stderr)
            for problem in problems:
                print(f"  {problem}", file=sys.stderr)
            return EXIT_COMMAND_FAILED
    return EXIT_OK


def _parse_staff_names(pairs: list[str]) -> dict[int, str]:
    names: dict[int, str] = {}
    for pair in pairs:
        staff, sep, name = pair.partition("=")
        if not sep or not staff.strip().isdigit() or not name.strip():
            raise ValueError(f"--name must look like 1=Soprano, got {pair!r}")
        names[int(staff)] = name.strip()
    return names


async def _run_rehearsal_mixes(args: argparse.Namespace) -> int:
    import shutil

    if not shutil.which("ffmpeg"):
        print("error: rehearsal-mixes needs ffmpeg on PATH (brew install ffmpeg)", file=sys.stderr)
        return EXIT_COMMAND_FAILED
    try:
        overrides = _parse_staff_names(args.name)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_COMMAND_FAILED
    out_dir = Path(args.out).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="rehearsal-mixes-"))
    stem_dir = out_dir / "stems" if args.keep_stems else work
    stem_dir.mkdir(exist_ok=True)
    try:
        async with _client(args, plugins=[BRIDGE_PLUGIN]) as client:
            await _require_bridge(client, AUDIO_EXPORT_BRIDGE_VERSION, "rehearsal-mixes")
            if args.sib_file:
                await _bridge(client, "OpenScore", [str(Path(args.sib_file).expanduser().resolve())])
            await _assert_expected_score(client, args)
            info = await _bridge(client, "GetScoreInfo")
            staves = await _bridge(client, "GetStaves")
            if unknown := sorted(set(overrides) - {s["staffNum"] for s in staves}):
                print(f"error: --name for staves not in the score: {unknown}", file=sys.stderr)
                return EXIT_COMMAND_FAILED
            vocal = set()
            for staff in staves:
                if args.all_parts or await _bridge(client, "ReadLyrics", [staff["staffNum"], 1, info["barCount"]]):
                    vocal.add(staff["staffNum"])
            await _require_bridge(client, PLAYBACK_SOUNDS_BRIDGE_VERSION, "rehearsal-mixes sound check")
            playback = await _bridge(client, "GetPlaybackSounds")
            _print_playback_sounds(playback)
            if args.require_sound:
                problems = rehearsal_mix.sound_problems(playback, vocal, args.require_sound)
                if problems:
                    print(f"error: voices not playing {args.require_sound}; nothing exported:", file=sys.stderr)
                    for problem in problems:
                        print(f"  {problem}", file=sys.stderr)
                    return EXIT_COMMAND_FAILED
            taken: set[str] = set()
            stems: list[rehearsal_mix.Stem] = []
            for staff in staves:
                num = staff["staffNum"]
                name = rehearsal_mix.staff_name(
                    {**staff, "fullInstrumentName": overrides.get(num, staff.get("fullInstrumentName"))}, taken
                )
                path = stem_dir / f"{num:02d} {name}.aiff"
                print(f"exporting staff {num} ({name})...", file=sys.stderr)
                # The first seconds of an export still sound the previous
                # export's voice (Cantai switches voices late), so a throwaway
                # export of the same staff comes first; the second is clean.
                await _bridge(client, "ExportAudio", [str(work / "warm-up.aiff"), num])
                await _bridge(client, "ExportAudio", [str(path), num])
                if not path.exists():
                    raise BridgeError(f"Sibelius reported exporting {path}, but it does not exist")
                stems.append(rehearsal_mix.Stem(num, name, path, vocal=num in vocal))
        voices = [s for s in stems if s.vocal]
        if not voices:
            print("error: no staff has lyrics, so there are no voices to mix (use --all-parts "
                  "for an instrumental score)", file=sys.stderr)
            return EXIT_COMMAND_FAILED
        loudness = {s.staff: rehearsal_mix.integrated_loudness(s.path) for s in voices}
        gains = rehearsal_mix.voice_gains(loudness)
        title = Path(info["fileName"]).stem if info.get("fileName") else "Score"
        by_staff = {s.staff: s for s in stems}
        measured = []
        for i, mix in enumerate(rehearsal_mix.plan_mixes(stems, gains)):
            print(f"mixing {mix.label}...", file=sys.stderr)
            result = rehearsal_mix.mix_to_wav(mix, by_staff, work / f"mix{i}.wav")
            measured.append({**result, "file": out_dir / f"{title} - {mix.label}.mp3"})
        level = rehearsal_mix.common_loudness(measured, args.loudness)
        results = []
        for m in measured:
            gain_db = level - m["loudness"]
            rehearsal_mix.encode(m["wav"], gain_db, m["file"], args.bitrate)
            results.append({
                "file": str(m["file"]), "gains": m["gains"],
                "gainDb": round(gain_db, 2), "peakDb": round(m["peak"] + gain_db, 2),
            })
        proof_report = None
        if not args.no_proof:
            print("proof-listening to the mixes...", file=sys.stderr)
            proof_report = mix_proof.proof_folder(
                out_dir, stems=[s.path for s in stems], loudness_of=rehearsal_mix.integrated_loudness,
                only=[m["file"] for m in measured],
            )
            print(proof_report.format(), file=sys.stderr)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print(json.dumps({
        "voices": {s.name: {"staff": s.staff, "loudnessLufs": round(loudness[s.staff], 1),
                            "gainDb": round(20 * math.log10(gains[s.staff]), 2)} for s in voices},
        "accompaniment": [s.name for s in stems if not s.vocal],
        "loudnessLufs": round(level, 1),
        "mixes": results,
        "stems": str(stem_dir) if args.keep_stems else None,
        "proof": proof_report.to_json() if proof_report else None,
    }, indent=2))
    if proof_report and not proof_report.ok:
        print("error: the proof-listening checks found errors; do not upload these mixes until they are "
              "fixed (see the rehearsal-mixes skill)", file=sys.stderr)
        return EXIT_COMMAND_FAILED
    return EXIT_OK


async def _run_proof_mixes(args: argparse.Namespace) -> int:
    import shutil

    if not shutil.which("ffmpeg"):
        print("error: proof-mixes needs ffmpeg on PATH (brew install ffmpeg)", file=sys.stderr)
        return EXIT_COMMAND_FAILED
    folder = Path(args.folder).expanduser().resolve()
    stems = Path(args.stems).expanduser().resolve() if args.stems else None
    for path in (folder, stems):
        if path is not None and not path.is_dir():
            print(f"error: {path} is not a folder", file=sys.stderr)
            return EXIT_COMMAND_FAILED
    report = mix_proof.proof_folder(folder, stems=stems, loudness_of=rehearsal_mix.integrated_loudness)
    print(json.dumps(report.to_json(), indent=2) if args.json else report.format())
    return EXIT_OK if report.ok else EXIT_COMMAND_FAILED


async def _run_verify_render(args: argparse.Namespace) -> int:
    if args.min_bytes < 1:
        print("error: --min-bytes must be positive", file=sys.stderr)
        return EXIT_COMMAND_FAILED
    saveas_type, extension = EXPORT_FORMATS[args.format]
    async with _client(args, plugins=[BRIDGE_PLUGIN]) as client:
        await _check_bridge_version(client)
        if args.sib_file:
            source = Path(args.sib_file).expanduser().resolve()
            if not source.exists():
                print(f"error: {source} does not exist", file=sys.stderr)
                return EXIT_COMMAND_FAILED
            await _bridge(client, "OpenScore", [str(source)])
        info = await _bridge(client, "GetScoreInfo")
        await _assert_expected_score(client, args, info)
        if not info.get("fileName") and not args.out:
            print("error: active score has never been saved; pass --out", file=sys.stderr)
            return EXIT_COMMAND_FAILED
        out = _export_path(args.out, info["fileName"], extension)
        await _bridge(client, "ExportScore", [str(out), saveas_type])

    produced = [out] if out.exists() else sorted(out.parent.glob(f"{out.stem}_*{out.suffix}"))
    files: list[dict[str, Any]] = []
    for path in produced:
        try:
            size = path.stat().st_size
        except OSError:
            continue
        entry: dict[str, Any] = {"path": str(path), "bytes": size}
        if args.sha256:
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            entry["sha256"] = digest.hexdigest()
        files.append(entry)

    reasons: list[str] = []
    if not files:
        reasons.append(f"no rendered files found at {out}")
    if any(item["bytes"] < args.min_bytes for item in files):
        reasons.append(f"a rendered file is smaller than {args.min_bytes} bytes")
    if args.expect_pages is not None and len(files) != args.expect_pages:
        reasons.append(f"expected {args.expect_pages} rendered files, found {len(files)}")
    report = {
        "verified": not reasons,
        "format": args.format,
        "source": info.get("fileName", ""),
        "files": files,
        "pages": len(files),
        "bytes": sum(item["bytes"] for item in files),
    }
    if reasons:
        report["errors"] = reasons
    print(json.dumps(report, ensure_ascii=False, separators=(",", ":")))
    return EXIT_OK if report["verified"] else EXIT_COMMAND_FAILED
