"""Rehearsal MP3s built from per-staff audio stems.

Sibelius exports one lossless stem per staff (``ExportAudio``). Voices are the
staves that carry lyrics; every other staff is accompaniment. The voices are
first equalized: each is gained to the same integrated loudness, chosen so
the voices together carry the same energy as before. Accompaniment keeps its
Sibelius level. From that baseline the mixes are:

- all voices: every stem at its baseline gain
- "<voice> only": that voice plus accompaniment, no other voice
- "<voice> louder": that voice at 3x amplitude (+9.5 dB) over the others

Every file is then brought to one integrated loudness (-16 LUFS by default),
or less if some file would otherwise peak above -1 dBFS, so switching between
files keeps the same overall level. Each file is gained as a whole, which
keeps every ratio inside it exact. ffmpeg does the measuring, mixing and
encoding.

Each stem is exported twice and the first copy discarded: an export's first
few seconds still sound the voice of the export before it (verified with
Cantai, 2026-09-24), while a second export of the same staff is clean from
the start.

Stems of one score sum to its full export in power (second by second, within
a fraction of a dB), though not sample for sample: each render draws slightly
different samples, so exports never cancel exactly.
"""

from __future__ import annotations

import math
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

FEATURE_GAIN = 3.0
PEAK_CEILING_DB = -1.0
TARGET_LUFS = -16.0
DEFAULT_BITRATE = "192k"
# Integrated loudness of a stem with nothing audible in it.
SILENT_LUFS = -70.0


@dataclass(frozen=True)
class Stem:
    staff: int
    name: str
    path: Path
    vocal: bool


@dataclass(frozen=True)
class Mix:
    """One output file: a linear gain for each staff that sounds in it."""

    label: str
    gains: dict[int, float]


def db_to_gain(db: float) -> float:
    return 10 ** (db / 20)


def voice_gains(loudness: dict[int, float]) -> dict[int, float]:
    """Linear gains that bring every voice to one loudness.

    The target is the power mean of the voices' loudness, so the equalized
    voices together carry as much energy as the originals. A silent voice
    keeps unity gain rather than being boosted without limit.
    """
    audible = {staff: lufs for staff, lufs in loudness.items() if lufs > SILENT_LUFS}
    if not audible:
        return {staff: 1.0 for staff in loudness}
    mean_power = sum(10 ** (lufs / 10) for lufs in audible.values()) / len(audible)
    target = 10 * math.log10(mean_power)
    return {
        staff: db_to_gain(target - loudness[staff]) if staff in audible else 1.0
        for staff in loudness
    }


def plan_mixes(stems: list[Stem], gains: dict[int, float]) -> list[Mix]:
    """The full mix, then an "only" and a "louder" mix for each voice."""
    voices = [s for s in stems if s.vocal]
    accompaniment = {s.staff: 1.0 for s in stems if not s.vocal}
    mixes = [Mix("All voices", {**{v.staff: gains[v.staff] for v in voices}, **accompaniment})]
    for voice in voices:
        mixes.append(Mix(f"{voice.name} only", {voice.staff: gains[voice.staff], **accompaniment}))
    for voice in voices:
        louder = {v.staff: gains[v.staff] * (FEATURE_GAIN if v is voice else 1.0) for v in voices}
        mixes.append(Mix(f"{voice.name} louder", {**louder, **accompaniment}))
    return mixes


def staff_name(staff: dict, taken: set[str]) -> str:
    """A file-safe staff name, unique among those already taken."""
    name = (staff.get("fullInstrumentName") or "").strip()
    if not name or name.startswith("["):
        name = (staff.get("instrumentName") or "").strip()
    if not name or name.startswith("["):
        name = f"Staff {staff['staffNum']}"
    name = re.sub(r'[\\/:*?"<>|]+', "-", name)
    unique, n = name, 2
    while unique in taken:
        unique, n = f"{name} {n}", n + 1
    taken.add(unique)
    return unique


def sound_problems(sounds: list[dict], voices: set[int], required: str) -> list[str]:
    """Voice staves whose playback sound set does not contain `required`
    (case-insensitive), at the start or at any later sound change."""
    problems = []
    want = required.casefold()
    for staff in sounds:
        if staff["staffNum"] not in voices:
            continue
        for change in staff.get("sounds", []):
            if want not in (change.get("soundSet") or "").casefold():
                problems.append(
                    f"staff {staff['staffNum']} from bar {change['bar']}: "
                    f"{change.get('soundSet') or '?'} / {change.get('patch') or '?'}"
                )
        if not staff.get("complete", True):
            problems.append(f"staff {staff['staffNum']}: sound changes not fully read")
    return problems


def _ffmpeg(args: list[str]) -> str:
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostdin", *args], capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr.strip()[-500:]}")
    return result.stderr


def integrated_loudness(path: Path) -> float:
    """EBU R128 integrated loudness of a file, in LUFS."""
    output = _ffmpeg(["-i", str(path), "-af", "ebur128", "-f", "null", "-"])
    match = re.findall(r"I:\s+(-?[\d.]+|-inf)\s+LUFS", output)
    if not match:
        raise RuntimeError(f"no loudness reading for {path}")
    return SILENT_LUFS if match[-1] == "-inf" else max(float(match[-1]), SILENT_LUFS)


def peak_db(path: Path) -> float:
    """Sample peak in dBFS. Float mixes can exceed 0 dBFS; volumedetect caps
    its reading at 0.0 there, so astats is used instead."""
    output = _ffmpeg([
        "-i", str(path), "-af", "astats=measure_perchannel=none:measure_overall=Peak_level",
        "-f", "null", "-",
    ])
    return parse_peak(output)


def parse_peak(astats_output: str) -> float:
    match = re.search(r"Peak level dB:\s+(-?[\d.]+|-inf)", astats_output)
    if not match:
        raise RuntimeError("no peak reading from ffmpeg astats")
    return -math.inf if match.group(1) == "-inf" else float(match.group(1))


def mix_to_wav(mix: Mix, stems: dict[int, Stem], wav: Path) -> dict:
    """Mix the stems at the mix's gains to float WAV; measure loudness and peak."""
    staves = sorted(mix.gains)
    inputs: list[str] = []
    for staff in staves:
        inputs += ["-i", str(stems[staff].path)]
    chains = [f"[{i}]volume={mix.gains[staff]:.6f}[s{i}]" for i, staff in enumerate(staves)]
    labels = "".join(f"[s{i}]" for i in range(len(staves)))
    graph = ";".join(chains) + f";{labels}amix=inputs={len(staves)}:normalize=0:duration=longest"
    _ffmpeg([*inputs, "-filter_complex", graph, "-c:a", "pcm_f32le", "-y", str(wav)])
    return {
        "wav": wav,
        "gains": {str(s): round(mix.gains[s], 4) for s in staves},
        "loudness": integrated_loudness(wav),
        "peak": peak_db(wav),
    }


def common_loudness(measured: list[dict], target: float, ceiling_db: float = PEAK_CEILING_DB) -> float:
    """The loudness every file can reach without its peak passing the ceiling:
    the target, or less if some file would clip at the target."""
    reachable = [m["loudness"] + ceiling_db - m["peak"] for m in measured if m["peak"] > -math.inf]
    return min([target, *reachable])


def encode(wav: Path, gain_db: float, out: Path, bitrate: str) -> None:
    _ffmpeg([
        "-i", str(wav), "-af", f"volume={gain_db:.4f}dB",
        "-c:a", "libmp3lame", "-b:a", bitrate, "-y", str(out),
    ])
