"""Tests for two-voice splitting in the vector-pdf-score reader (split_bar_voices)."""

import pytest

from helpers import ROOT, load_script

pytest.importorskip("pymupdf")
vecscore = load_script(ROOT / ".claude/skills/vector-pdf-score/scripts/vecscore.py", "vecscore")

STAFF = dict(top=100.0, bottom=128.0, sp=7.0)
W = 7.0 * 1.18  # notehead width: an up stem sits this far right of the head's x


def head(x, y, p, c="œ"):
    return dict(x=x, y=y, c=c, p=p, dot=False)


def test_half_against_two_quarters_splits_into_two_voices() -> None:
    # voice 1: two quarters (stems up); voice 2: one half note (stem down) under the first quarter
    heads = [head(10, 107, 33), head(40, 110.5, 32), head(10, 121, 29, "˙")]
    stems = [(10 + W, 85, 107), (40 + W, 88, 110.5), (10, 121, 142)]
    merged = [dict(x=10, p=[29, 33], dur=4, rest=False), dict(x=40, p=[32], dur=4, rest=False)]
    v = vecscore.split_bar_voices(heads, [], merged, stems, [], [], [], STAFF)
    assert [[(e["p"], e["dur"]) for e in voice] for voice in v] == [[([33], 4), ([32], 4)], [([29], 8)]]


def test_same_rhythm_chords_stay_one_voice() -> None:
    heads = [head(10, 107, 33), head(10, 121, 29)]
    stems = [(10 + W, 85, 107), (10, 121, 142)]
    merged = [dict(x=10, p=[29, 33], dur=4, rest=False)]
    assert vecscore.split_bar_voices(heads, [], merged, stems, [], [], [], STAFF) is None


def test_one_voice_bar_is_left_alone() -> None:
    heads = [head(10, 107, 33), head(40, 121, 29)]
    stems = [(10 + W, 85, 107), (40, 121, 142)]
    merged = [dict(x=10, p=[33], dur=4, rest=False), dict(x=40, p=[29], dur=4, rest=False)]
    assert vecscore.split_bar_voices(heads, [], merged, stems, [], [], [], STAFF) is None
