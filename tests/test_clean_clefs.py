"""Tests for redundant clef auditing in sibelius_websocket_cli.clefs.

Clef cleanup is engraving proofreading, not playback repair -- see the
"Engraving vs. Playback" note in the hanging-playback-note-repair skill.
"""

from __future__ import annotations

from sibelius_websocket_cli import clefs as clean_clefs


def _clef_bar(bar_number: int, *clefs: tuple[int, int, str]) -> dict:
    """Build a bar dict from (index, position, styleId) triples."""
    return {
        "barNumber": bar_number,
        "objects": [
            {"type": "Clef", "index": idx, "position": pos, "styleId": style}
            for idx, pos, style in clefs
        ],
    }


# --- Clef inference from instrument names ----------------------------------


def test_infer_expected_clef_vocal_parts() -> None:
    assert clean_clefs.infer_expected_clef("Soprano") == "clef.treble"
    assert clean_clefs.infer_expected_clef("Mezzo-Soprano") == "clef.treble"
    assert clean_clefs.infer_expected_clef("Tenor") == "clef.treble.down.8"
    assert clean_clefs.infer_expected_clef("Baritone") == "clef.bass"
    assert clean_clefs.infer_expected_clef("Bass") == "clef.bass"


def test_infer_expected_clef_choral_altos_read_treble() -> None:
    """Choral altos read treble; alto clef is viola territory."""
    assert clean_clefs.infer_expected_clef("Alto") == "clef.treble"
    assert clean_clefs.infer_expected_clef("Contralto") == "clef.treble"
    assert clean_clefs.infer_expected_clef("Alto 2") == "clef.treble"
    assert clean_clefs.infer_expected_clef("Viola") == "clef.alto"


def test_infer_expected_clef_instrument_name_beats_vocal_range() -> None:
    """A vocal range in an instrument's name describes pitch, not clef."""
    assert clean_clefs.infer_expected_clef("Alto Saxophone") == "clef.treble"
    assert clean_clefs.infer_expected_clef("Tenor Saxophone") == "clef.treble"
    assert clean_clefs.infer_expected_clef("Baritone Saxophone") == "clef.treble"
    assert clean_clefs.infer_expected_clef("Alto Flute") == "clef.treble"
    assert clean_clefs.infer_expected_clef("Bass Clarinet") == "clef.treble"
    assert clean_clefs.infer_expected_clef("Tenor Trombone") == "clef.bass"
    assert clean_clefs.infer_expected_clef("Bassoon") == "clef.bass"
    assert clean_clefs.infer_expected_clef("Violoncello") == "clef.bass"
    assert clean_clefs.infer_expected_clef("Violin") == "clef.treble"
    assert clean_clefs.infer_expected_clef("Alto Trombone") == "clef.alto"


def test_infer_expected_clef_returns_none_when_unsure() -> None:
    """No confident answer must not silently become treble."""
    assert clean_clefs.infer_expected_clef("Piano") is None
    assert clean_clefs.infer_expected_clef("Organ") is None
    assert clean_clefs.infer_expected_clef("") is None
    assert clean_clefs.infer_expected_clef("   ") is None


# --- Meter map -------------------------------------------------------------


def test_bar_length_ticks() -> None:
    assert clean_clefs.bar_length_ticks(4, 4) == 1024
    assert clean_clefs.bar_length_ticks(3, 4) == 768
    assert clean_clefs.bar_length_ticks(2, 4) == 512
    assert clean_clefs.bar_length_ticks(6, 8) == 768
    assert clean_clefs.bar_length_ticks(7, 8) == 896
    assert clean_clefs.bar_length_ticks(0, 4) == 0


def test_build_meter_map_carries_signatures_forward() -> None:
    signatures = [
        {"bar": 1, "numerator": 4, "denominator": 4},
        {"bar": 3, "numerator": 3, "denominator": 4},
    ]
    meter_map = clean_clefs.build_meter_map(signatures, bar_count=5)
    assert meter_map == {1: 1024, 2: 1024, 3: 768, 4: 768, 5: 768}


def test_build_meter_map_defaults_to_common_time() -> None:
    assert clean_clefs.build_meter_map(None, bar_count=2) == {1: 1024, 2: 1024}
    assert clean_clefs.build_meter_map([], bar_count=0) == {}


# --- Redundant clef detection ---------------------------------------------


def test_audit_score_clefs_clean() -> None:
    bars = [
        {
            "barNumber": 1,
            "objects": [
                {
                    "type": "NoteRest",
                    "index": 0,
                    "position": 0,
                    "duration": 512,
                    "voice": 1,
                    "notes": [{"pitch": 60, "name": "C4", "tied": False}],
                },
            ],
        }
    ]
    found = clean_clefs.audit_score_clefs(
        bars, staff_num=1, default_clef="clef.treble", bar_ticks={1: 1024}
    )
    assert found == []


def test_audit_score_clefs_flags_default_match_and_terminal_barline() -> None:
    bars = [
        _clef_bar(
            1,
            # Mid-bar clef repeating the staff default: OMR system-break clutter.
            (0, 256, "clef.bass"),
            # Courtesy clef parked on the terminal barline, even though it changes clef.
            (1, 1024, "clef.treble"),
        )
    ]
    redundant = clean_clefs.audit_score_clefs(
        bars, staff_num=16, default_clef="clef.bass", bar_ticks={1: 1024}
    )
    assert len(redundant) == 2

    by_index = {c["index"]: c for c in redundant}
    assert "Matches staff default" in by_index[0]["reason"]
    assert "Terminal barline artifact" in by_index[1]["reason"]
    assert by_index[1]["position"] == 1024
    assert all(c["staff"] == 16 and c["bar"] == 1 for c in redundant)


def test_audit_score_clefs_keeps_mid_bar_clef_change_in_long_meter() -> None:
    """Tick 512 is beat 3 of a 4/4 bar, not a barline: must not be flagged."""
    bars = [_clef_bar(7, (0, 512, "clef.treble"))]
    assert clean_clefs.audit_score_clefs(
        bars, staff_num=16, default_clef="clef.bass", bar_ticks={7: 1024}
    ) == []


def test_audit_score_clefs_flags_same_tick_when_it_ends_a_short_bar() -> None:
    """The same tick 512 *is* the barline in 2/4, so there it is an artifact."""
    bars = [_clef_bar(7, (0, 512, "clef.treble"))]
    redundant = clean_clefs.audit_score_clefs(
        bars, staff_num=16, default_clef="clef.bass", bar_ticks={7: 512}
    )
    assert len(redundant) == 1
    assert "Terminal barline artifact" in redundant[0]["reason"]


def test_audit_score_clefs_skips_terminal_check_without_meter() -> None:
    """An unknown bar length must not be guessed at."""
    bars = [_clef_bar(7, (0, 1024, "clef.treble"))]
    assert clean_clefs.audit_score_clefs(
        bars, staff_num=16, default_clef="clef.bass", bar_ticks=None
    ) == []
    assert clean_clefs.audit_score_clefs(
        bars, staff_num=16, default_clef="clef.bass", bar_ticks={1: 1024}
    ) == []


def test_audit_score_clefs_skips_default_check_when_default_unknown() -> None:
    """With no known staff default, only barline artifacts are reported."""
    bars = [_clef_bar(1, (0, 256, "clef.bass"), (1, 1024, "clef.bass"))]
    redundant = clean_clefs.audit_score_clefs(
        bars, staff_num=5, default_clef=None, bar_ticks={1: 1024}
    )
    assert len(redundant) == 1
    assert redundant[0]["position"] == 1024


# --- Reading the staff default out of the score ----------------------------


def test_first_clef_style_prefers_earliest_position() -> None:
    bars = [_clef_bar(1, (3, 512, "clef.treble"), (0, 0, "clef.bass"))]
    assert clean_clefs.first_clef_style(bars) == "clef.bass"


def test_first_clef_style_none_when_no_clef_present() -> None:
    assert clean_clefs.first_clef_style([{"barNumber": 1, "objects": []}]) is None
    assert clean_clefs.first_clef_style([]) is None
