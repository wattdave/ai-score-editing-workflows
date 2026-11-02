from __future__ import annotations

import json

import pytest

from ai_score_editing.sibelius.batch_lyrics import (
    BatchLyricsError,
    AffectedRange,
    LyricPatch,
    affected_lyric_ranges,
    build_batch_summary,
    format_compact_summary,
    load_lyric_patches,
    parse_lyric_patches,
    plain_lyric_text,
    resolve_lyric_text,
    validate_patch_targets,
    verify_lyric_patches,
)


def test_load_and_normalize_patch_file(tmp_path) -> None:
    source = tmp_path / "patches.json"
    source.write_text(json.dumps([
        {"staff": 2, "bar": 7, "index": 0, "text": "glo-"},
        {
            "staff": 2,
            "bar": 7,
            "index": 2,
            "text": "ry",
            "font": " Plantin ",
            "fontSize": 95,
        },
    ]))

    patches = load_lyric_patches(source)

    assert patches == [
        LyricPatch(2, 7, 0, "glo-"),
        LyricPatch(2, 7, 2, "ry", "Plantin", 95),
    ]


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ([], "non-empty JSON array"),
        ({}, "non-empty JSON array"),
        ([{"staff": 1}], "missing field"),
        ([{"staff": True, "bar": 1, "index": 0, "text": "la"}], "staff"),
        ([{"staff": 1, "bar": 0, "index": 0, "text": "la"}], "bar"),
        ([{"staff": 1, "bar": 1, "index": -1, "text": "la"}], "index"),
        ([{"staff": 1, "bar": 1, "index": 0, "text": 7}], "text"),
        ([{"staff": 1, "bar": 1, "index": 0, "text": "la", "raw": True}], "unknown"),
    ],
)
def test_parse_rejects_invalid_patch_files(payload, message) -> None:
    with pytest.raises(BatchLyricsError, match=message):
        parse_lyric_patches(payload)


def test_parse_rejects_duplicate_addresses() -> None:
    payload = [
        {"staff": 1, "bar": 3, "index": 2, "text": "one"},
        {"staff": 1, "bar": 3, "index": 2, "text": "two"},
    ]
    with pytest.raises(BatchLyricsError, match="duplicates lyric address S1 B3 I2"):
        parse_lyric_patches(payload)


def test_affected_ranges_are_minimal_and_sorted() -> None:
    patches = [
        LyricPatch(3, 9, 0, "a"),
        LyricPatch(1, 12, 1, "b"),
        LyricPatch(3, 4, 2, "c"),
    ]
    assert affected_lyric_ranges(patches) == [
        # Sorted by staff, with one inclusive range per staff.
        AffectedRange(1, 12, 12),
        AffectedRange(3, 4, 9),
    ]


def test_validate_targets_returns_addressed_lyrics() -> None:
    patches = [LyricPatch(1, 2, 0, "new")]
    current = [{"staff": 1, "bar": 2, "index": 0, "text": "old"}]
    assert validate_patch_targets(patches, current)[(1, 2, 0)]["text"] == "old"


def test_validate_targets_reports_all_missing_addresses() -> None:
    patches = [LyricPatch(1, 2, 0, "a"), LyricPatch(2, 3, 4, "b")]
    with pytest.raises(BatchLyricsError, match="S1 B2 I0, S2 B3 I4"):
        validate_patch_targets(patches, [])


def test_resolve_text_uses_patch_then_command_defaults() -> None:
    per_patch = LyricPatch(1, 2, 0, "la", "Plantin", 95)
    assert resolve_lyric_text(
        per_patch, default_font="Garamond", default_font_size=100
    ) == "\\fPlantin\\\\s95\\la"

    defaults = LyricPatch(1, 2, 0, "la")
    assert resolve_lyric_text(
        defaults, default_font="Garamond", default_font_size=100
    ) == "\\fGaramond\\\\s100\\la"


def test_resolve_text_matches_existing_set_lyric_inference() -> None:
    patch = LyricPatch(1, 2, 0, "hermosa")
    staff_lyrics = [
        {"staff": 1, "bar": 1, "index": 0, "text": "\\fQuicksand\\s88\\One"},
        {"staff": 1, "bar": 1, "index": 1, "text": "\\fQuicksand\\s88\\Two"},
        {"staff": 1, "bar": 2, "index": 0, "text": "ermosa"},
    ]
    assert resolve_lyric_text(
        patch, staff_lyrics=staff_lyrics, score_default_font="Times New Roman"
    ) == "\\fQuicksand\\\\s88\\hermosa"


def test_resolve_text_uses_size_only_and_preserves_pretagged_text() -> None:
    assert resolve_lyric_text(
        LyricPatch(1, 1, 0, "la", font_size=90)
    ) == "\\s90\\la"
    tagged = "\\fPlantin\\s95\\la"
    assert resolve_lyric_text(LyricPatch(1, 1, 0, tagged)) == tagged


def test_verify_compares_plain_text_and_reports_missing() -> None:
    patches = [
        LyricPatch(1, 2, 0, "\\fPlantin\\s95\\glo-"),
        LyricPatch(1, 2, 2, "ry"),
    ]
    checked = verify_lyric_patches(
        patches,
        [{"staff": 1, "bar": 2, "index": 0, "text": "glo-"}],
    )
    assert checked[0].verified is True
    assert checked[0].expected == "glo-"
    assert checked[1].verified is False
    assert checked[1].actual is None
    assert plain_lyric_text("\\fPlantin\\s95\\glo-") == "glo-"


def test_summary_is_json_ready_and_compact() -> None:
    patches = [LyricPatch(1, 2, 0, "new"), LyricPatch(2, 3, 1, "lost")]
    checked = verify_lyric_patches(
        patches,
        [{"staff": 1, "bar": 2, "index": 0, "text": "new"}],
    )
    summary = build_batch_summary(
        patches,
        [{"oldText": "old", "newText": "new"}, {"oldText": "found", "newText": "lost"}],
        checked,
        backup={"copy": "/scores/song.backup.sib"},
        saved={"fileName": "/scores/song.sib"},
    )

    assert json.loads(json.dumps(summary)) == summary
    assert summary["patched"] == 2
    assert summary["verified"] == 1
    assert format_compact_summary(summary) == (
        "patched 2; verified 1/2; backup /scores/song.backup.sib; "
        "saved /scores/song.sib; verification failed: S2 B3 I1"
    )
