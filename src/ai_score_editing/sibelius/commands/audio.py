"""Audio commands: rehearsal-mixes, export-stem, proof-mixes, playback-sounds, verify-render."""

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

from ai_score_editing.workflows import mix_proof, rehearsal_mix
from ai_score_editing.cli_common import canonical_format
from ai_score_editing.sibelius.bridge import (
    AUDIO_EXPORT_BRIDGE_VERSION,
    BRIDGE_PLUGIN,
    EXPORT_FORMATS,
    PLAYBACK_SOUNDS_BRIDGE_VERSION,
    QUERY_CONTAINERS_BRIDGE_VERSION,
    BridgeError,
)
from ai_score_editing.sibelius import bridge, runner
from ai_score_editing.sibelius.commands._common import EXIT_COMMAND_FAILED, EXIT_OK


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
        "--voice-staff", type=int, action="append", default=[], metavar="N",
        help="name the voice staves explicitly instead of detecting them by lyrics "
             "(repeatable; when instruments carry lyrics too)",
    )
    mixes.add_argument(
        "--skip-staff", type=int, action="append", default=[], metavar="N",
        help="leave this staff out entirely: not exported, not a voice, not in any mix "
             "(repeatable; for a melody staff that doubles the parts)",
    )
    mixes.add_argument(
        "--require-sound", metavar="SOUND_SET",
        help="refuse to export unless every voice plays a sound set containing this, e.g. Cantai",
    )
    mixes.add_argument("--no-proof", action="store_true", help="skip the proof-listening checks after mixing")
    stem = sub.add_parser(
        "export-stem",
        help="export the audio of single staves (lossless AIFF) and report each one's length, loudness and silences",
        description=(
            "Export one audio stem per requested staff, without mixing, so one staff can be checked or "
            "re-exported on its own (for example a voice that rehearsal-mixes found silent). Prints each "
            "stem's length, loudness, peak and silent stretches. Needs ffmpeg for the report."
        ),
    )
    stem.add_argument("--out", required=True, help="directory for the AIFF stems")
    stem.add_argument(
        "--staff", type=int, action="append", default=[], metavar="N",
        help="staff number to export (repeatable; default: every staff)",
    )
    stem.add_argument("--file", dest="sib_file", help=".sib file to open first (default: active score)")
    stem.add_argument(
        "--name", action="append", default=[], metavar="STAFF=NAME",
        help="name a staff in the file names, e.g. --name 2=Soprano-div (repeatable)",
    )
    stem.add_argument(
        "--no-warm-up", action="store_true",
        help="skip the throwaway first export (an export's opening can carry the previous staff's voice)",
    )
    stem.add_argument("--min-silence", type=int, default=2, metavar="SECONDS",
                      help="report silent stretches at least this long (default: %(default)s)")
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
        help="list each staff's playback sound set, patch and sound ID, any Mixer override, "
             "and its Mixer mute, solo, volume and pan",
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
        "export-stem": _run_export_stem,
        "proof-mixes": _run_proof_mixes,
        "playback-sounds": _run_playback_sounds,
        "verify-render": _run_verify_render,
    }


MIXER_FIELDS = ["MuteMode", "Solo", "Volume", "Pan"]


async def _read_mixer(client: Any) -> dict[int, dict]:
    """Each staff's Mixer mute, solo, volume and pan (Staff.MuteMode, Solo,
    Volume, Pan), read with a Staff query (bridge v62). Empty, with a note,
    on an older bridge: the check is advisory and must not block an export."""
    from ai_score_editing.sibelius.query_props import build_selector

    try:
        await bridge.require_bridge(client, QUERY_CONTAINERS_BRIDGE_VERSION, "Mixer check")
    except BridgeError as exc:
        print(f"note: Mixer state not read: {exc}", file=sys.stderr)
        return {}
    selector = build_selector(
        staves=[], from_bar=None, to_bar=None, types=["Staff"], voice=None, where=[],
        fields=MIXER_FIELDS, limit=1000,
    )
    result = await bridge.call(client, "Query", [selector])
    rows = result.get("objects", []) if isinstance(result, dict) else []
    return {row["staff"]: row.get("fields", {}) for row in rows if row.get("type") == "Staff"}


def _print_mixer_problems(mixer: dict[int, dict], staves: set[int]) -> None:
    problems = rehearsal_mix.mixer_problems(mixer, staves)
    if problems:
        print("warning: Mixer settings that can silence or quieten exported audio:", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)


def _print_playback_sounds(staves: list[dict], mixer: dict[int, dict] | None = None) -> None:
    for staff in staves:
        override = f"  [Mixer override {staff['override']}]" if staff.get("override") else ""
        fields = (mixer or {}).get(staff["staffNum"])
        state = ""
        if fields:
            mute = rehearsal_mix.MUTE_MODES.get(fields.get("MuteMode"), "mute ?")
            solo = ", solo" if fields.get("Solo") in (True, 1) else ""
            state = f"  [{mute}{solo}, volume {fields.get('Volume', '?')}, pan {fields.get('Pan', '?')}]"
        for i, change in enumerate(staff.get("sounds", [])):
            where = f"staff {staff['staffNum']}" if i == 0 else f"  from bar {change['bar']}"
            print(f"{where}: {change['soundSet']} / {change['patch']} ({change['actualSoundId']})"
                  f"{override + state if i == 0 else ''}", file=sys.stderr)


async def _run_playback_sounds(args: argparse.Namespace) -> int:
    async with runner.client(args, plugins=[BRIDGE_PLUGIN]) as client:
        await bridge.require_bridge(client, PLAYBACK_SOUNDS_BRIDGE_VERSION, "playback-sounds")
        mixer = await _read_mixer(client)
        staves = await bridge.call(client, "GetPlaybackSounds")
    for staff in staves:
        if staff.get("staffNum") in mixer:
            staff["mixer"] = mixer[staff["staffNum"]]
    _print_playback_sounds(staves, mixer)
    _print_mixer_problems(mixer, {s["staffNum"] for s in staves})
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


async def _export_staff(client: Any, path: Path, staff: int, work: Path, warm_up: bool = True) -> None:
    """Export one staff's audio to `path`. The first seconds of an export still
    sound the previous export's voice (Cantai switches voices late), so a
    throwaway export of the same staff comes first; the second is clean."""
    if warm_up:
        await bridge.call(client, "ExportAudio", [str(work / "warm-up.aiff"), staff])
    await bridge.call(client, "ExportAudio", [str(path), staff])
    if not path.exists():
        raise BridgeError(f"Sibelius reported exporting {path}, but it does not exist")


async def _run_export_stem(args: argparse.Namespace) -> int:
    import shutil

    if not shutil.which("ffmpeg"):
        print("error: export-stem needs ffmpeg on PATH (brew install ffmpeg)", file=sys.stderr)
        return EXIT_COMMAND_FAILED
    try:
        overrides = _parse_staff_names(args.name)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_COMMAND_FAILED
    out_dir = Path(args.out).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="export-stem-"))
    reports: list[dict[str, Any]] = []
    try:
        async with runner.client(args, plugins=[BRIDGE_PLUGIN]) as client:
            await bridge.require_bridge(client, AUDIO_EXPORT_BRIDGE_VERSION, "export-stem")
            if args.sib_file:
                await bridge.call(client, "OpenScore", [str(Path(args.sib_file).expanduser().resolve())])
            await runner.assert_expected_score(client, args)
            staves = await bridge.call(client, "GetStaves")
            known = {s["staffNum"] for s in staves}
            wanted = args.staff or sorted(known)
            if unknown := sorted((set(wanted) | set(overrides)) - known):
                print(f"error: staves not in the score: {unknown}", file=sys.stderr)
                return EXIT_COMMAND_FAILED
            _print_mixer_problems(await _read_mixer(client), set(wanted))
            taken: set[str] = set()
            for staff in staves:
                num = staff["staffNum"]
                name = rehearsal_mix.staff_name(
                    {**staff, "fullInstrumentName": overrides.get(num, staff.get("fullInstrumentName"))}, taken
                )
                if num not in wanted:
                    continue
                path = out_dir / f"{num:02d} {name}.aiff"
                print(f"exporting staff {num} ({name})...", file=sys.stderr)
                await _export_staff(client, path, num, work, warm_up=not args.no_warm_up)
                report = {"staff": num, "name": name, **rehearsal_mix.stem_report(path, args.min_silence)}
                reports.append(report)
                silent = ", ".join(f"{a}-{b} s" for a, b in report["silentSeconds"]) or "none"
                print(f"  {report['seconds']} s, {report['loudnessLufs']} LUFS, peak {report['peakDb']} dB, "
                      f"silent: {silent}", file=sys.stderr)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print(json.dumps({"stems": reports}, indent=2))
    return EXIT_OK


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
        async with runner.client(args, plugins=[BRIDGE_PLUGIN]) as client:
            await bridge.require_bridge(client, AUDIO_EXPORT_BRIDGE_VERSION, "rehearsal-mixes")
            if args.sib_file:
                await bridge.call(client, "OpenScore", [str(Path(args.sib_file).expanduser().resolve())])
            await runner.assert_expected_score(client, args)
            info = await bridge.call(client, "GetScoreInfo")
            staves = await bridge.call(client, "GetStaves")
            if unknown := sorted(set(overrides) - {s["staffNum"] for s in staves}):
                print(f"error: --name for staves not in the score: {unknown}", file=sys.stderr)
                return EXIT_COMMAND_FAILED
            vocal = set()
            skip = set(args.skip_staff)
            if unknown := sorted(skip - {s["staffNum"] for s in staves}):
                print(f"error: --skip-staff for staves not in the score: {unknown}", file=sys.stderr)
                return EXIT_COMMAND_FAILED
            for staff in staves:
                if staff["staffNum"] in skip:
                    continue
                if args.voice_staff:
                    if staff["staffNum"] in args.voice_staff:
                        vocal.add(staff["staffNum"])
                    continue
                if args.all_parts or await bridge.call(client, "ReadLyrics", [staff["staffNum"], 1, info["barCount"]]):
                    vocal.add(staff["staffNum"])
            await bridge.require_bridge(client, PLAYBACK_SOUNDS_BRIDGE_VERSION, "rehearsal-mixes sound check")
            mixer = await _read_mixer(client)
            playback = await bridge.call(client, "GetPlaybackSounds")
            _print_playback_sounds(playback, mixer)
            _print_mixer_problems(mixer, {s["staffNum"] for s in staves} - skip)
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
                if num in skip:
                    continue
                name = rehearsal_mix.staff_name(
                    {**staff, "fullInstrumentName": overrides.get(num, staff.get("fullInstrumentName"))}, taken
                )
                path = stem_dir / f"{num:02d} {name}.aiff"
                print(f"exporting staff {num} ({name})...", file=sys.stderr)
                await _export_staff(client, path, num, work)
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
    async with runner.client(args, plugins=[BRIDGE_PLUGIN]) as client:
        await bridge.check_bridge_version(client)
        if args.sib_file:
            source = Path(args.sib_file).expanduser().resolve()
            if not source.exists():
                print(f"error: {source} does not exist", file=sys.stderr)
                return EXIT_COMMAND_FAILED
            await bridge.call(client, "OpenScore", [str(source)])
        info = await bridge.call(client, "GetScoreInfo")
        await runner.assert_expected_score(client, args, info)
        if not info.get("fileName") and not args.out:
            print("error: active score has never been saved; pass --out", file=sys.stderr)
            return EXIT_COMMAND_FAILED
        out = bridge.export_path(args.out, info["fileName"], extension)
        await bridge.call(client, "ExportScore", [str(out), saveas_type])

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
