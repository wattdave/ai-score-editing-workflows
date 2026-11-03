"""Proof-listening checks for a folder of rehearsal mixes.

The checks need only ffmpeg and numpy, and read the finished MP3s (or the
per-staff stems too, when they are at hand). They find structural faults that
a quick listen can miss:

- ``shared``: the same audio in different voices' files. Separate renders of
  different voices never match sample for sample, so a window where several
  files correlate far above their usual level is one render copied into all
  (a stale Cantai render cache gave every staff the same first four bars).
  Where the voices' own stems are silent for the whole stretch, the files carry
  only the accompaniment and are identical as they should be: a ``note``.
- ``repeat``: a stretch of one file that repeats an earlier or later stretch
  sample for sample. Even a repeated phrase is re-rendered with new samples.
- ``level``: a stretch much louder than the rest of its file.
- ``arithmetic`` (with stems): a mix that is not the stems at consistent
  gains, such as one built from the wrong stems.
- ``length``, ``loudness`` and ``silence``: files that disagree with the rest.
"""

from __future__ import annotations

import itertools
import re
import statistics
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

SAMPLE_RATE = 8000
WINDOW = SAMPLE_RATE  # one second
SILENT_DB = -60.0

# shared: correlation this high, and this far above the pair's usual level
SHARED_CORR = 0.9
SHARED_RISE = 0.4
SHARED_MIN_SECONDS = 2
# shared audio quieter than this is a rest or a tail: a warning, not an error
SHARED_AUDIBLE_DB = -40.0
# a voice stem quieter than this is resting
VOICE_REST_DB = -50.0
# repeat: sample-for-sample repeats
REPEAT_CORR = 0.97
REPEAT_MIN_LAG_SECONDS = 2.0
REPEAT_MIN_SECONDS = 2
# level: a run of this many seconds this far above the file's median level
LEVEL_WARN_DB = 6.0
LEVEL_ERROR_DB = 12.0
LEVEL_MIN_SECONDS = 3
LEVEL_SMOOTH_SECONDS = 3
# arithmetic: residual after fitting the stems, relative to the mix
ARITHMETIC_RESIDUAL_DB = -20.0
ARITHMETIC_GAIN_DB = 3.0
ARITHMETIC_STEM_FLOOR_DB = -50.0
ARITHMETIC_CONDITION = 0.02
# files that disagree with the batch
LENGTH_TOLERANCE_SECONDS = 0.25
LOUDNESS_TOLERANCE_LU = 1.5
SILENCE_MIN_SECONDS = 3
SILENCE_EDGE_SECONDS = 5

MIX_KIND = re.compile(r" - (?P<label>.+?)\.(?:mp3|wav|aiff|m4a)$")


@dataclass(frozen=True)
class Finding:
    severity: str  # "error", "warning" or "note" (information, never fails a batch)
    check: str
    message: str
    files: tuple[str, ...] = ()
    start: float | None = None  # seconds
    end: float | None = None

    def line(self) -> str:
        span = f" [{self.start:.1f}-{self.end:.1f} s]" if self.start is not None else ""
        return f"{self.severity.upper():7s} {self.check:10s}{span} {self.message}"


@dataclass
class ProofReport:
    files: list[str] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(f.severity == "error" for f in self.findings)

    def to_json(self) -> dict:
        return {
            "ok": self.ok,
            "files": self.files,
            "findings": [
                {"severity": f.severity, "check": f.check, "message": f.message,
                 "files": list(f.files), "start": f.start, "end": f.end}
                for f in self.findings
            ],
        }

    def format(self) -> str:
        head = f"{len(self.files)} files checked: " + (
            "no problems found" if not self.findings else
            f"{sum(f.severity == 'error' for f in self.findings)} errors, "
            f"{sum(f.severity == 'warning' for f in self.findings)} warnings"
        )
        return "\n".join([head, *(f.line() for f in self.findings)])


def load_mono(path: Path, seconds: float | None = None) -> np.ndarray:
    """Decode any audio file to mono float32 at SAMPLE_RATE."""
    cmd = ["ffmpeg", "-v", "error", "-nostdin", "-i", str(path), "-ac", "1", "-ar", str(SAMPLE_RATE)]
    if seconds:
        cmd += ["-t", str(seconds)]
    result = subprocess.run([*cmd, "-f", "f32le", "-"], capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg could not read {path}: {result.stderr.decode(errors='replace')[-300:]}")
    return np.frombuffer(result.stdout, dtype=np.float32)


def _windows(x: np.ndarray) -> np.ndarray:
    n = len(x) // WINDOW
    return x[: n * WINDOW].reshape(n, WINDOW)


def window_db(x: np.ndarray) -> np.ndarray:
    """RMS level of each one-second window, in dB."""
    w = _windows(x).astype(np.float64)
    return 20 * np.log10(np.sqrt((w ** 2).mean(axis=1)) + 1e-9)


def _runs(flags: np.ndarray, minimum: int) -> list[tuple[int, int]]:
    """Half-open index ranges of at least `minimum` consecutive True values."""
    runs, start = [], None
    for i, flag in enumerate(list(flags) + [False]):
        if flag and start is None:
            start = i
        elif not flag and start is not None:
            if i - start >= minimum:
                runs.append((start, i))
            start = None
    return runs


def check_level(name: str, x: np.ndarray) -> list[Finding]:
    """A run of seconds far louder than the file's median."""
    db = window_db(x)
    if len(db) < LEVEL_MIN_SECONDS * 2:
        return []
    audible = db > SILENT_DB
    kernel = np.ones(LEVEL_SMOOTH_SECONDS) / LEVEL_SMOOTH_SECONDS
    smooth = np.convolve(db, kernel, mode="same")
    median = float(np.median(smooth[audible])) if audible.any() else 0.0
    findings = []
    for threshold, severity in ((LEVEL_ERROR_DB, "error"), (LEVEL_WARN_DB, "warning")):
        for start, end in _runs((smooth - median > threshold) & audible, LEVEL_MIN_SECONDS):
            if severity == "warning" and any(f.start is not None and f.start < end and start < f.end for f in findings):
                continue
            peak = float((smooth[start:end] - median).max())
            findings.append(Finding(
                severity, "level", f"{peak:.0f} dB louder than the file's median level",
                (name,), float(start), float(end),
            ))
    return findings


def _normalized_correlation(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Pearson correlation of each pair of rows."""
    a = a - a.mean(axis=1, keepdims=True)
    b = b - b.mean(axis=1, keepdims=True)
    denom = np.sqrt((a ** 2).sum(axis=1) * (b ** 2).sum(axis=1))
    return (a * b).sum(axis=1) / np.maximum(denom, 1e-12)


def check_shared(signals: dict[str, np.ndarray]) -> list[Finding]:
    """Windows where different files carry the same audio.

    Compare files pairwise in one-second windows. A pair's usual correlation
    (its median) sets the baseline, since voices over a shared accompaniment
    correlate somewhat all the time; a run of windows far above the baseline
    and nearly 1 is one render appearing in both files. Overlapping pairs are
    merged into one finding naming every file that shares the stretch.
    """
    hits: list[tuple[int, int, str, str, float]] = []
    names = list(signals)
    for a, b in itertools.combinations(names, 2):
        n = min(len(signals[a]), len(signals[b])) // WINDOW
        if n < SHARED_MIN_SECONDS:
            continue
        wa, wb = _windows(signals[a])[:n].astype(np.float64), _windows(signals[b])[:n].astype(np.float64)
        corr = _normalized_correlation(wa, wb)
        loud = (window_db(signals[a])[:n] > SILENT_DB) & (window_db(signals[b])[:n] > SILENT_DB)
        baseline = float(np.median(corr[loud])) if loud.any() else 0.0
        flags = (corr > SHARED_CORR) & (corr - baseline > SHARED_RISE) & loud
        level = window_db(signals[a])[:n]
        for start, end in _runs(flags, SHARED_MIN_SECONDS):
            hits.append((start, end, a, b, float(level[start:end].mean())))
    merged: list[dict] = []
    for start, end, a, b, level in sorted(hits):
        for group in merged:
            if start < group["end"] and group["start"] < end:
                group["start"], group["end"] = min(group["start"], start), max(group["end"], end)
                group["files"].update((a, b))
                group["level"] = max(group["level"], level)
                break
        else:
            merged.append({"start": start, "end": end, "files": {a, b}, "level": level})
    return [
        Finding(
            "error" if g["level"] > SHARED_AUDIBLE_DB else "warning", "shared",
            f"{len(g['files'])} files carry the same audio: " + ", ".join(sorted(g["files"])),
            tuple(sorted(g["files"])), float(g["start"]), float(g["end"]),
        )
        for g in merged
    ]


def check_repeats(name: str, x: np.ndarray) -> list[Finding]:
    """Stretches that repeat another stretch of the same file sample for sample."""
    n = len(x) // WINDOW
    if n < REPEAT_MIN_SECONDS * 2 + 2:
        return []
    x = x[: n * WINDOW].astype(np.float64)
    size = 1 << (len(x) * 2 - 1).bit_length()
    spectrum = np.fft.rfft(x, size)
    energy = np.concatenate(([0.0], np.cumsum(x ** 2)))
    db = window_db(x)
    min_lag = int(REPEAT_MIN_LAG_SECONDS * SAMPLE_RATE)
    flags = np.zeros(n, dtype=bool)
    partner = [0] * n
    for i in range(n):
        if db[i] < SILENT_DB:
            continue
        w = x[i * WINDOW:(i + 1) * WINDOW]
        w_energy = float((w ** 2).sum())
        # cross-correlation of the window against the whole file, by FFT
        cc = np.fft.irfft(spectrum * np.conj(np.fft.rfft(w, size)), size)[: len(x) - WINDOW + 1]
        local = energy[WINDOW:WINDOW + len(cc)] - energy[: len(cc)]
        ncc = cc / np.sqrt(np.maximum(local * w_energy, 1e-12))
        lo, hi = max(0, i * WINDOW - min_lag + 1), min(len(ncc), i * WINDOW + min_lag)
        ncc[lo:hi] = 0
        best = int(np.argmax(ncc))
        if ncc[best] > REPEAT_CORR:
            flags[i] = True
            partner[i] = best
    runs = _runs(flags, REPEAT_MIN_SECONDS)
    if not runs:
        return []
    shown = ", ".join(f"{a}-{b} s (again at {partner[a] / SAMPLE_RATE:.0f} s)" for a, b in runs[:4])
    more = f" and {len(runs) - 4} more" if len(runs) > 4 else ""
    return [Finding(
        "warning", "repeat",
        f"{sum(b - a for a, b in runs)} s repeat other stretches sample for sample: {shown}{more}. "
        "Normal for a repeated verse in sampled sounds; Cantai should re-sing each time.",
        (name,), float(runs[0][0]), float(runs[-1][1]),
    )]


def check_arithmetic(name: str, mix: np.ndarray, stems: dict[str, np.ndarray]) -> list[Finding]:
    """Fit a mix to the stems in each second; flag poor fits and gain jumps."""
    names = list(stems)
    n = min([len(mix) // WINDOW, *(len(s) // WINDOW for s in stems.values())])
    if n < 2 or not names:
        return []
    m = _windows(mix)[:n].astype(np.float64)
    basis = np.stack([_windows(stems[k])[:n].astype(np.float64) for k in names], axis=2)
    gains = np.zeros((n, len(names)))
    residual = np.zeros(n)
    audible = np.stack([window_db(stems[k])[:n] > ARITHMETIC_STEM_FLOOR_DB for k in names], axis=1)
    conditioned = np.zeros(n, dtype=bool)
    for i in range(n):
        g, *_ = np.linalg.lstsq(basis[i], m[i], rcond=None)
        gains[i] = g
        # gains are only meaningful when the stems are distinct enough to tell apart
        sv = np.linalg.svd(basis[i][:, audible[i]], compute_uv=False) if audible[i].any() else np.zeros(1)
        conditioned[i] = bool(sv[0] > 0 and sv[-1] / sv[0] > ARITHMETIC_CONDITION)
        mix_power = float((m[i] ** 2).mean())
        residual[i] = 10 * np.log10(float(((m[i] - basis[i] @ g) ** 2).mean()) / max(mix_power, 1e-12) + 1e-12)
    loud = window_db(mix)[:n] > SILENT_DB
    findings = [
        Finding("error", "arithmetic",
                f"mix is not the stems at fixed gains (residual {residual[start:end].max():.0f} dB)",
                (name,), float(start), float(end))
        for start, end in _runs((residual > ARITHMETIC_RESIDUAL_DB) & loud, 2)
    ]
    for j, stem in enumerate(names):
        usable = loud & conditioned & audible[:, j]
        if not usable.any():
            continue
        median = float(np.median(gains[usable, j]))
        if abs(median) < 1e-3:
            continue
        off = np.abs(20 * np.log10(np.maximum(np.abs(gains[:, j]), 1e-9) / abs(median))) > ARITHMETIC_GAIN_DB
        for start, end in _runs(off & usable, 2):
            findings.append(Finding(
                "error", "arithmetic", f"stem '{stem}' is mixed at a different gain here than elsewhere",
                (name,), float(start), float(end),
            ))
    return findings


def check_silence(name: str, x: np.ndarray) -> list[Finding]:
    """Long silences away from the start and end."""
    db = window_db(x)
    inside = np.zeros(len(db), dtype=bool)
    inside[SILENCE_EDGE_SECONDS:max(len(db) - SILENCE_EDGE_SECONDS, 0)] = True
    return [
        Finding("warning", "silence", f"{end - start} s of silence inside the file", (name,), float(start), float(end))
        for start, end in _runs((db < SILENT_DB) & inside, SILENCE_MIN_SECONDS)
    ]


def check_batch(durations: dict[str, float], loudness: dict[str, float]) -> list[Finding]:
    """Files whose length or loudness differs from the rest."""
    findings = []
    if durations:
        median = statistics.median(durations.values())
        for name, d in durations.items():
            if abs(d - median) > LENGTH_TOLERANCE_SECONDS:
                findings.append(Finding(
                    "error", "length", f"{d:.1f} s long; the batch's median is {median:.1f} s", (name,)))
    if loudness:
        median = statistics.median(loudness.values())
        for name, lufs in loudness.items():
            if abs(lufs - median) > LOUDNESS_TOLERANCE_LU:
                findings.append(Finding(
                    "warning", "loudness", f"{lufs:.1f} LUFS; the batch's median is {median:.1f} LUFS", (name,)))
    return findings


def kind_of(path: Path) -> str:
    """'only', 'louder', 'all' or 'other', from the name `<score> - <label>.mp3`."""
    match = MIX_KIND.search(path.name)
    label = match.group("label").lower() if match else ""
    if label.endswith(" only"):
        return "only"
    if label.endswith(" louder"):
        return "louder"
    if label == "all voices":
        return "all"
    return "other"


def _stem_key(name: str) -> str:
    """'04 Soprano.aiff' -> 'soprano', the name a mix label uses."""
    return re.sub(r"^\d+\s+", "", Path(name).stem).lower()


def _voice_key(name: str) -> str:
    """'Song - Soprano only.mp3' -> 'soprano'."""
    match = MIX_KIND.search(name)
    label = match.group("label") if match else Path(name).stem
    return re.sub(r" (?:only|louder)$", "", label, flags=re.IGNORECASE).lower()


def note_accompaniment_only(findings: list[Finding], stems: dict[str, np.ndarray]) -> list[Finding]:
    """Turn `shared` findings over stretches where the voices rest into notes.

    When every voice named by a finding has a stem of its own and each is
    silent for the stretch (leaving out its first and last second when the
    stretch is longer than two, where a voice can still be dying away or coming
    in), the files hold nothing but the accompaniment and are identical for
    that reason. A voice with no matching stem keeps the finding as it was, and
    the stems' own `shared` check still catches a copied render.
    """
    by_voice = {_stem_key(n): x for n, x in stems.items()}
    out = []
    for f in findings:
        voices = [by_voice.get(_voice_key(n)) for n in f.files]
        if f.check != "shared" or f.start is None or any(v is None for v in voices):
            out.append(f)
            continue
        start, end = int(f.start), int(f.end)
        if end - start > 2:  # the edges can hold a voice's last notes or first entry
            start, end = start + 1, end - 1
        if all(window_db(v)[start:end].max() < VOICE_REST_DB for v in voices):
            out.append(Finding(
                "note", "shared",
                "only the accompaniment plays here (these voices rest), so the files are identical: "
                + ", ".join(f.files),
                f.files, f.start, f.end,
            ))
        else:
            out.append(f)
    return out


def proof_folder(
    folder: Path, stems: Path | list[Path] | None = None, loudness_of=None, only: list[Path] | None = None
) -> ProofReport:
    """Run every check over the audio files in `folder`.

    `shared` compares the "only" files with each other and the "louder" files
    with each other, never across kinds, since a voice's "only" and "louder"
    files are made from the same stem. Pass the stems (a folder or a list of files) to add the
    arithmetic check and to run the others on the stems as well.
    """
    audio = sorted(
        (p for p in folder.iterdir() if p.suffix.lower() in {".mp3", ".wav", ".aiff", ".m4a"}),
    )
    if only is not None:
        names = {p.name for p in only}
        audio = [p for p in audio if p.name in names]
    if any(kind_of(p) != "other" for p in audio):
        audio = [p for p in audio if kind_of(p) != "other"]  # skip loose recordings in the folder
    report = ProofReport(files=[p.name for p in audio])
    signals = {p.name: load_mono(p) for p in audio}
    for name, x in signals.items():
        report.findings += check_level(name, x) + check_repeats(name, x) + check_silence(name, x)
    shared = []
    for kind in ("only", "louder"):
        group = {p.name: signals[p.name] for p in audio if kind_of(p) == kind}
        shared += check_shared(group)
    report.findings += shared
    report.findings += check_batch(
        {n: len(x) / SAMPLE_RATE for n, x in signals.items()},
        {p.name: loudness_of(p) for p in audio} if loudness_of else {},
    )
    if stems is not None:
        stem_files = sorted(
            stems if isinstance(stems, list) else (p for p in stems.iterdir() if p.suffix.lower() in {".aiff", ".wav"})
        )
        stem_signals = {p.name: load_mono(p) for p in stem_files}
        report.findings = [f for f in report.findings if f not in shared] + note_accompaniment_only(
            shared, stem_signals
        )
        report.files += [f"stems/{n}" for n in stem_signals]
        for name, x in stem_signals.items():
            report.findings += [
                Finding(f.severity, f.check, f.message, tuple(f"stems/{n}" for n in f.files), f.start, f.end)
                for f in check_level(name, x) + check_repeats(name, x)
            ]
        report.findings += [
            Finding(f.severity, f.check, f.message, tuple(f"stems/{n}" for n in f.files), f.start, f.end)
            for f in check_shared(stem_signals)
        ]
        for p in audio:
            report.findings += check_arithmetic(p.name, signals[p.name], stem_signals)
    return report
