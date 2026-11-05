"""Tests for the set-lyric-verse batch op: validation, bridge version and plug-in wiring."""

import re
from pathlib import Path

import pytest

from ai_score_editing.core.batch_schema import verse_dy
from ai_score_editing.sibelius.batch_ops import BatchError, validate_batch
from ai_score_editing.sibelius.bridge import (
    CURRENT_BRIDGE_VERSION,
    SET_LYRIC_VERSE_BRIDGE_VERSION,
    batch_bridge_version as _batch_bridge_version,
)

PLUGIN = Path(__file__).parent.parent / "src/ai_score_editing/sibelius/manuscript/ScoreBridge.plg"


def test_verse_spacing_convention() -> None:
    assert [verse_dy(v) for v in range(1, 6)] == [-192, -272, -352, -432, -512]


def test_defaults_dy_to_the_verse_spacing_and_needs_bridge_59() -> None:
    batch = validate_batch([
        {"op": "set-lyric-verse", "staff": 3, "fromBar": 1, "toBar": 40, "verse": 1},
        {"op": "set-lyric-verse", "staff": 3, "fromBar": 5, "toBar": 5, "verse": 3, "fromVerse": 1,
         "voice": 2, "position": 0, "dy": -400},
    ])
    assert batch[0] == {"op": "set-lyric-verse", "staff": 3, "fromBar": 1, "toBar": 40, "verse": 1,
                        "hasPosition": False, "dy": -192}
    assert batch[1]["dy"] == -400 and batch[1]["position"] == 0 and batch[1]["hasPosition"] is True
    assert _batch_bridge_version(batch) == SET_LYRIC_VERSE_BRIDGE_VERSION == 59


@pytest.mark.parametrize("verse", range(1, 6))
def test_each_verse_gets_its_own_dy(verse: int) -> None:
    op = validate_batch([{"op": "set-lyric-verse", "staff": 1, "fromBar": 1, "toBar": 2, "verse": verse}])[0]
    assert op["dy"] == verse_dy(verse)


@pytest.mark.parametrize(
    ("operation", "message"),
    [
        ({"op": "set-lyric-verse", "staff": 0, "fromBar": 1, "toBar": 2, "verse": 1}, "system staff"),
        ({"op": "set-lyric-verse", "staff": 1, "fromBar": 3, "toBar": 2, "verse": 1}, "toBar must be"),
        ({"op": "set-lyric-verse", "staff": 1, "fromBar": 1, "toBar": 2, "verse": 6}, "verse must be"),
        ({"op": "set-lyric-verse", "staff": 1, "fromBar": 1, "toBar": 2, "verse": 0}, "verse must be"),
        ({"op": "set-lyric-verse", "staff": 1, "fromBar": 1, "toBar": 2}, "verse must be"),
        ({"op": "set-lyric-verse", "staff": 1, "fromBar": 1, "toBar": 2, "verse": 1, "fromVerse": 1},
         "must differ"),
        ({"op": "set-lyric-verse", "staff": 1, "fromBar": 1, "toBar": 2, "verse": 1, "fromVerse": 9},
         "fromVerse must be"),
        ({"op": "set-lyric-verse", "staff": 1, "fromBar": 1, "toBar": 2, "verse": 1, "voice": 5},
         "voice must be"),
        ({"op": "set-lyric-verse", "staff": 1, "fromBar": 1, "toBar": 2, "verse": 1, "dy": 0},
         "must not be 0"),
        ({"op": "set-lyric-verse", "staff": 1, "fromBar": 1, "toBar": 2, "verse": 1, "dy": "low"},
         "dy must be"),
        ({"op": "set-lyric-verse", "staff": 1, "fromBar": 1, "toBar": 2, "verse": 1, "bar": 1},
         "unknown"),
        ({"op": "set-lyric-verse", "staff": 1, "fromBar": 1, "toBar": 2, "verse": 1, "position": -1},
         "position must be"),
    ],
)
def test_rejects(operation: dict, message: str) -> None:
    with pytest.raises(BatchError, match=message):
        validate_batch([operation])


def test_is_an_object_op_that_must_precede_structural_ops() -> None:
    move = {"op": "set-lyric-verse", "staff": 2, "fromBar": 1, "toBar": 4, "verse": 1}
    delete_bars = {"op": "delete-bars", "fromBar": 9, "toBar": 10}
    validate_batch([move, delete_bars])
    with pytest.raises(BatchError, match="structural ops must come last"):
        validate_batch([delete_bars, move])


def _function(source: str, name: str) -> str:
    start = source.index(f'\t{name} "(')
    return source[start:source.index('}"\n', start)]


def test_plugin_wires_the_op_into_check_and_run() -> None:
    source = PLUGIN.read_text()
    assert "CreateDictionary('version', 63)" in source
    assert "return BatchCheckLyricVerse(score, op);" in _function(source, "BatchCheck")
    assert "return BatchRunLyricVerse(score, op);" in _function(source, "BatchRun")
    # not structural: it keeps the addresses of earlier ops valid
    assert "set-lyric-verse" not in _function(source, "BatchStructural")


def test_plugin_refuses_duplicates_and_sets_style_before_dy() -> None:
    source = PLUGIN.read_text()
    check = _function(source, "BatchCheckLyricVerse")
    assert "would land there" in check and "taken[key] = True" in check
    run = _function(source, "BatchRunLyricVerse")
    assert run.index("lyric.StyleId = styleId") < run.index("lyric.Dy = op['dy']")
    moves = _function(source, "LyricVerseMoves")
    assert re.search(r"op\['hasPosition'\] = True", moves)  # position 0 reads as null in ManuScript


def test_verse_name_is_built_before_comparing():
    # `styleId = 'text...verse' & v` matched nothing in Sibelius (v59 smoke test:
    # moved 0 of 319 lyrics); the name must be built first, then compared.
    source = PLUGIN.read_text()
    block = source[source.index("LyricVerseOf"):source.index("LyricVerseMoves")]
    assert "target = 'text.staff.space.hypen.lyrics.verse' & v;" in block
    assert "if (styleId = target)" in block
