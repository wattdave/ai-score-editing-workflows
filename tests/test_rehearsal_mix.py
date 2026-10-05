"""Tests for rehearsal mix planning (no Sibelius or ffmpeg needed)."""

import math
from pathlib import Path

import pytest

from ai_score_editing.rehearsal_mix import (
    FEATURE_GAIN,
    Stem,
    common_loudness,
    plan_mixes,
    staff_name,
    voice_gains,
)


def _stems() -> list[Stem]:
    return [
        Stem(1, "Soprano", Path("1.aiff"), vocal=True),
        Stem(2, "Alto", Path("2.aiff"), vocal=True),
        Stem(3, "Piano", Path("3.aiff"), vocal=False),
    ]


def test_voice_gains_equalize_and_keep_total_energy() -> None:
    loudness = {1: -20.0, 2: -30.0}
    gains = voice_gains(loudness)
    after = {s: loudness[s] + 20 * math.log10(g) for s, g in gains.items()}
    assert after[1] == pytest.approx(after[2])
    energy = lambda d: sum(10 ** (v / 10) for v in d.values())  # noqa: E731
    assert energy(after) == pytest.approx(energy(loudness))


def test_silent_voice_keeps_unity_gain() -> None:
    gains = voice_gains({1: -20.0, 2: -70.0})
    assert gains[2] == 1.0
    assert gains[1] == pytest.approx(1.0)


def test_plan_has_full_only_and_louder_mixes() -> None:
    gains = {1: 0.5, 2: 2.0}
    mixes = {m.label: m.gains for m in plan_mixes(_stems(), gains)}
    assert list(mixes) == ["All voices", "Soprano only", "Alto only", "Soprano louder", "Alto louder"]
    assert mixes["All voices"] == {1: 0.5, 2: 2.0, 3: 1.0}
    # Alone: no other voice at all, accompaniment untouched.
    assert mixes["Soprano only"] == {1: 0.5, 3: 1.0}
    # Louder: 3x amplitude over the equalized baseline.
    assert mixes["Alto louder"] == {1: 0.5, 2: 2.0 * FEATURE_GAIN, 3: 1.0}


def test_nine_files_for_four_voices_without_accompaniment() -> None:
    stems = [Stem(n, f"V{n}", Path(f"{n}.aiff"), vocal=True) for n in range(1, 5)]
    assert len(plan_mixes(stems, {n: 1.0 for n in range(1, 5)})) == 9


def test_common_loudness_is_the_target_unless_a_file_would_clip() -> None:
    quiet = {"loudness": -30.0, "peak": -20.0}   # reaches -16 with room to spare
    peaky = {"loudness": -20.0, "peak": 2.0}     # at -16 it would peak at +6
    assert common_loudness([quiet], -16.0) == -16.0
    # peaky can only rise to -23 (-20 + -1 - 2), so every file goes to -23.
    assert common_loudness([quiet, peaky], -16.0) == pytest.approx(-23.0)


def test_staff_names_fall_back_and_stay_unique() -> None:
    taken: set[str] = set()
    assert staff_name({"staffNum": 1, "fullInstrumentName": " ",
                       "instrumentName": "[Unnamed (treble staff)]"}, taken) == "Staff 1"
    assert staff_name({"staffNum": 2, "fullInstrumentName": "Alto"}, taken) == "Alto"
    assert staff_name({"staffNum": 3, "fullInstrumentName": "Alto"}, taken) == "Alto 2"
    assert staff_name({"staffNum": 4, "fullInstrumentName": "S/A"}, taken) == "S-A"


def test_parse_peak_reads_levels_above_full_scale() -> None:
    from ai_score_editing.rehearsal_mix import parse_peak

    assert parse_peak("[Parsed_astats_0 @ 0x1] Peak level dB: 9.807554\n") == pytest.approx(9.807554)
    assert parse_peak("Peak level dB: -inf") == -math.inf


def test_sound_problems_flag_non_matching_voices_only() -> None:
    from ai_score_editing.rehearsal_mix import sound_problems

    staves = [
        {"staffNum": 1, "complete": True, "sounds": [{"bar": 1, "soundSet": "Cantai", "patch": "Soprano"}]},
        {"staffNum": 2, "complete": True, "sounds": [
            {"bar": 1, "soundSet": "Cantai", "patch": "Alto"},
            {"bar": 12, "soundSet": "Sibelius 7 Sounds", "patch": "Female Choir aah"},
        ]},
        {"staffNum": 3, "complete": True, "sounds": [{"bar": 1, "soundSet": "Sibelius 7 Sounds", "patch": "Piano"}]},
        {"staffNum": 4, "complete": False, "sounds": [{"bar": 1, "soundSet": "Cantai", "patch": "Bass"}]},
    ]
    problems = sound_problems(staves, {1, 2, 4}, "cantai")
    assert problems == [
        "staff 2 from bar 12: Sibelius 7 Sounds / Female Choir aah",
        "staff 4: sound changes not fully read",
    ]
