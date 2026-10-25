import shutil
import wave
from pathlib import Path

import numpy as np
import pytest

from ai_score_editing import mix_proof as mp

SR = mp.SAMPLE_RATE


def voice(seed: int, seconds: int = 30, pitch: float = 220.0, level: float = 0.1) -> np.ndarray:
    """A stand-in for one rendered voice: a pitched tone with its own noise,
    like a separate render, so two voices never match sample for sample."""
    rng = np.random.default_rng(seed)
    t = np.arange(seconds * SR) / SR
    tone = sum(np.sin(2 * np.pi * pitch * k * t + rng.uniform(0, 6.28)) / k for k in (1, 2, 3))
    return (level * (tone + 0.3 * rng.standard_normal(len(t)))).astype(np.float32)


def test_clean_voices_have_no_findings():
    voices = {f"v{i} only.mp3": voice(i, pitch=200 + 50 * i) for i in range(4)}
    assert mp.check_shared(voices) == []
    for name, x in voices.items():
        assert mp.check_level(name, x) == []
        assert mp.check_repeats(name, x) == []


def test_shared_opening_across_voices_is_an_error():
    voices = {f"v{i} only.mp3": voice(i, pitch=200 + 50 * i) for i in range(4)}
    leaked = voice(99, seconds=10, pitch=300, level=0.4)
    for x in voices.values():
        x[: len(leaked)] = leaked
    (finding,) = mp.check_shared(voices)
    assert finding.severity == "error" and finding.check == "shared"
    assert len(finding.files) == 4
    assert (finding.start, finding.end) == (0.0, 10.0)


def test_shared_audio_in_a_rest_is_only_a_warning():
    a, b = voice(1), voice(2)
    quiet = voice(3, seconds=5, level=0.003)  # about -45 dB
    a[5 * SR:10 * SR] = quiet
    b[5 * SR:10 * SR] = quiet
    (finding,) = mp.check_shared({"a only.mp3": a, "b only.mp3": b})
    assert finding.severity == "warning"


def test_voices_over_a_shared_accompaniment_are_not_flagged():
    accompaniment = voice(50, pitch=110, level=0.2)
    voices = {f"v{i} only.mp3": voice(i, pitch=200 + 50 * i) + accompaniment for i in range(3)}
    assert mp.check_shared(voices) == []


def test_loud_opening_is_flagged():
    x = voice(1)
    x[: 8 * SR] *= 12  # +21.6 dB
    (finding,) = mp.check_level("a only.mp3", x)
    assert finding.severity == "error" and finding.start == 0.0


def test_moderate_dynamics_are_only_a_warning():
    x = voice(1)
    x[10 * SR:16 * SR] *= 2.5  # +8 dB
    findings = mp.check_level("a only.mp3", x)
    assert findings and all(f.severity == "warning" for f in findings)


def test_sample_for_sample_repeat_is_reported():
    x = voice(1, seconds=40)
    x[25 * SR:33 * SR] = x[5 * SR:13 * SR]
    (finding,) = mp.check_repeats("a only.mp3", x)
    assert finding.severity == "warning"
    assert "again at 5 s" in finding.message


def test_mix_arithmetic_accepts_fixed_gains_and_flags_a_swapped_stem():
    stems = {f"s{i}": voice(i, pitch=200 + 60 * i) for i in range(3)}
    mix = 1.0 * stems["s0"] + 0.5 * stems["s1"] + 2.0 * stems["s2"]
    assert mp.check_arithmetic("m", mix, stems) == []
    bad = mix.copy()
    bad[10 * SR:14 * SR] = (1.0 * stems["s0"] + 4.0 * stems["s1"] + 2.0 * stems["s2"])[10 * SR:14 * SR]
    assert any(f.check == "arithmetic" for f in mp.check_arithmetic("m", bad, stems))


def test_batch_flags_the_odd_length_and_loudness():
    findings = mp.check_batch(
        {"a": 90.0, "b": 90.0, "c": 90.1, "d": 96.0}, {"a": -16.0, "b": -16.2, "c": -16.1, "d": -20.0}
    )
    assert {(f.check, f.files) for f in findings} == {("length", ("d",)), ("loudness", ("d",))}


def test_silence_inside_the_file_is_a_warning():
    x = voice(1, seconds=40)
    x[15 * SR:25 * SR] = 0
    (finding,) = mp.check_silence("a", x)
    assert finding.severity == "warning" and (finding.start, finding.end) == (15.0, 25.0)


@pytest.mark.parametrize("name,kind", [
    ("Song - Alto only.mp3", "only"), ("Song - Tenor II louder.mp3", "louder"),
    ("Song - All voices.mp3", "all"), ("Anne alto.mp3", "other"),
])
def test_kind_of(name, kind):
    assert mp.kind_of(Path(name)) == kind


def write_wav(path: Path, x: np.ndarray):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")
def test_proof_folder_end_to_end(tmp_path):
    leaked = voice(99, seconds=10, pitch=300, level=0.4)
    for i, leak in ((0, False), (1, True)):
        folder = tmp_path / f"batch{i}"
        folder.mkdir()
        for j, part in enumerate(("Alto", "Bass", "Tenor")):
            x = voice(j, pitch=200 + 50 * j)
            if leak:
                x[: len(leaked)] = leaked
            write_wav(folder / f"Song - {part} only.wav", x)
        write_wav(folder / "Loose recording.wav", voice(7, seconds=45))
        report = mp.proof_folder(folder)
        assert "Loose recording.wav" not in report.files
        assert report.ok is (not leak)
        assert any(f.check == "shared" for f in report.findings) is leak
