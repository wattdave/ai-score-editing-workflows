"""Tests for compact, agent-oriented output formats."""

import json

from ai_score_editing.agent_output import (
    project_inspect,
    project_score_snapshot,
    render_compact_inspect,
    render_compact_lyrics,
    render_compact_snapshot,
)


def test_project_inspect_selects_useful_fields_and_orders_staves() -> None:
    score = {
        "fileName": "/scores/canción.sib",
        "title": "Canción",
        "composer": "Composer omitted from compact output",
        "staffCount": 2,
        "barCount": 48,
        "keySignatures": [{"bar": 1, "name": "Eb"}],
    }
    staves = [
        {"staffNum": 2, "instrumentName": "A.", "fullInstrumentName": "Alto", "barCount": 48},
        {"staffNum": 1, "instrumentName": "Soprano", "barCount": 48},
    ]
    selection = {
        "isPassage": True,
        "topStaff": 1,
        "bottomStaff": 2,
        "firstBar": 3,
        "lastBar": 5,
        "ignored": "not emitted",
    }

    assert project_inspect(score, staves, selection) == {
        "fileName": "/scores/canción.sib",
        "title": "Canción",
        "staffCount": 2,
        "barCount": 48,
        "selection": {
            "isPassage": True,
            "topStaff": 1,
            "bottomStaff": 2,
            "firstBar": 3,
            "lastBar": 5,
        },
        "staves": [
            {"staffNum": 1, "instrumentName": "Soprano"},
            {"staffNum": 2, "instrumentName": "Alto"},
        ],
    }


def test_render_compact_inspect_is_one_line_unicode_json_with_fallbacks() -> None:
    rendered = render_compact_inspect(
        {"fileName": "été.sib"},
        [{"staffNumber": 4}],
        {"isPassage": False},
    )

    assert "\n" not in rendered
    assert "été.sib" in rendered
    assert json.loads(rendered) == {
        "fileName": "été.sib",
        "title": "",
        "staffCount": 1,
        "barCount": 0,
        "selection": {"isPassage": False},
        "staves": [{"staffNum": 4, "instrumentName": "Staff 4"}],
    }


def test_score_snapshot_projects_structural_fields_and_optional_data() -> None:
    snapshot = project_score_snapshot(
        {
            "fileName": "/scores/a.sib",
            "title": "A",
            "staffCount": 1,
            "barCount": 8,
            "keySignatures": [{"bar": 1, "name": "Bb", "sharps": -2, "major": True, "ignored": 1}],
            "timeSignatures": [{"bar": 1, "numerator": 6, "denominator": 4, "ignored": 1}],
        },
        [{"staffNum": 1, "fullInstrumentName": "Soprano", "ignored": 1}],
        {"isPassage": False, "ignored": 1},
        barlines=[{"bar": 5, "position": 768, "type": "EndRepeat", "ignored": 1}],
        lyrics=[{"staff": 1, "bar": 2, "index": 3, "position": 256, "text": "la", "ignored": 1}],
    )

    assert snapshot["keySignatures"] == [{"bar": 1, "name": "Bb", "sharps": -2, "major": True}]
    assert snapshot["timeSignatures"] == [{"bar": 1, "numerator": 6, "denominator": 4}]
    assert snapshot["barlines"] == [{"bar": 5, "position": 768, "type": "EndRepeat"}]
    assert snapshot["lyrics"] == [{"staff": 1, "bar": 2, "index": 3, "position": 256, "text": "la"}]
    assert "\n" not in render_compact_snapshot(snapshot)


def test_render_compact_lyrics_preserves_addresses_text_and_order() -> None:
    syllables = [
        {
            "staff": 2,
            "bar": 12,
            "index": 6,
            "position": 512,
            "voice": 1,
            "line": 2,
            "text": 'jah! "Amen"',
        },
        {
            "staff": 1,
            "bar": 2,
            "index": 0,
            "position": 0,
            "voice": 1,
            "text": "Señor",
        },
    ]

    assert render_compact_lyrics(syllables) == (
        'S1 B2 I0 P0 V1 "Señor"\n'
        'S2 B12 I6 P512 V1 L2 "jah! \\"Amen\\""'
    )


def test_render_compact_lyrics_empty_and_missing_optional_fields() -> None:
    assert render_compact_lyrics([]) == ""
    assert render_compact_lyrics([{"staff": 1, "bar": 1, "index": 0, "text": "la"}]) == (
        'S1 B1 I0 P0 V1 "la"'
    )


def test_compact_formats_stay_within_representative_character_budgets() -> None:
    score = {
        "fileName": "/scores/large-score.sib",
        "title": "Large Score",
        "composer": "A Composer",
        "lyricist": "A Lyricist",
        "copyright": "Copyright text",
        "staffCount": 2,
        "barCount": 96,
        "keySignatures": [{"bar": 1, "name": "C", "sharps": 0, "major": True}],
        "timeSignatures": [{"bar": 1, "numerator": 4, "denominator": 4}],
        "mainTextFontName": "Plantin",
        "mainMusicFontName": "Opus",
        "musicTextFontName": "Opus Text",
    }
    staves = [
        {"staffNum": 1, "instrumentName": "S.", "fullInstrumentName": "Soprano", "barCount": 96},
        {"staffNum": 2, "instrumentName": "A.", "fullInstrumentName": "Alto", "barCount": 96},
    ]
    selection = {"isPassage": True, "topStaff": 1, "bottomStaff": 2, "firstBar": 8, "lastBar": 12}
    verbose_inspect = "\n".join(json.dumps(value, indent=2) for value in (score, staves, selection))
    assert len(render_compact_inspect(score, staves, selection)) <= len(verbose_inspect) * 0.55

    syllables = [
        {
            "staff": 1,
            "bar": bar,
            "index": index,
            "position": index * 256,
            "voice": 1,
            "text": text,
            "syllableType": "middle" if text.endswith("-") else "end",
            "styleId": "text.staff.space.hypen.lyrics.verse1",
            "styleAsText": "Lyrics line 1",
        }
        for bar, index, text in ((1, 0, "Hal-"), (1, 2, "le-"), (1, 4, "lu-"), (2, 0, "jah!"))
    ]
    verbose_lyrics = json.dumps(syllables, indent=2, ensure_ascii=False)
    assert len(render_compact_lyrics(syllables)) <= len(verbose_lyrics) * 0.25
