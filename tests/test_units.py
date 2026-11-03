from ai_score_editing.core import units
from ai_score_editing.dorico import bridge, score as dorico_score
from ai_score_editing.musescore import score as musescore_score
from ai_score_editing.sibelius import clefs


def test_shared_values():
    assert units.UNITS_PER_QUARTER == 256
    assert units.UNITS_PER_WHOLE == 4 * units.UNITS_PER_QUARTER == 1024


def test_aliases_match_shared_values():
    assert bridge.UNITS == units.UNITS_PER_QUARTER
    assert dorico_score.UNIT_QUARTER == units.UNITS_PER_QUARTER
    assert musescore_score.UNITS_PER_QUARTER == units.UNITS_PER_QUARTER
    assert clefs.TICKS_PER_WHOLE == units.UNITS_PER_WHOLE
