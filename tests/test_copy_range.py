from __future__ import annotations

from typing import Any

import pytest

from ai_score_editing.sibelius import batch_ops
from ai_score_editing.sibelius import copy_range
from ai_score_editing.sibelius.cli import build_parser


def note(index: int, position: int, duration: int, *pitches: int, tied: bool = False, voice: int = 1) -> dict[str, Any]:
    names = {60: "C", 62: "D", 67: "G", 71: "B"}
    return {
        "type": "NoteRest", "index": index, "position": position, "duration": duration, "voice": voice,
        "notes": [{"pitch": p, "name": names[p], "tied": tied} for p in pitches],
    }


def rest(index: int, position: int, duration: int) -> dict[str, Any]:
    return {"type": "NoteRest", "index": index, "position": position, "duration": duration, "voice": 1, "notes": []}


def lyric(index: int, position: int, text: str, *, verse: int = 1, syllable: str = "end", dy: int = -192) -> dict[str, Any]:
    return {
        "type": "LyricItem", "index": index, "position": position, "text": text, "syllableType": syllable, "dy": dy,
        "voice": 1, "styleId": f"text.staff.space.hypen.lyrics.verse{verse}",
    }


# bar 32: G half, G, G with "Si me"; bar 50: the same bar with its last two beats gone
SOURCE = [note(0, 0, 512, 67), note(1, 512, 256, 67), lyric(2, 512, "Si"), note(3, 768, 256, 67), lyric(4, 768, "me")]
EMPTY_TAIL = [note(0, 0, 512, 67), rest(1, 512, 512)]


def test_parse_beats() -> None:
    assert copy_range.parse_beats("3-4") == (3, 4)
    assert copy_range.parse_beats("2") == (2, 2)
    for bad in ("0-1", "4-3", "a", ""):
        with pytest.raises(copy_range.CopyRangeError):
            copy_range.parse_beats(bad)


def test_beats_read_as_quarters_or_as_the_time_signature() -> None:
    assert copy_range.beats_to_positions(3, 4, 2, 2, "quarter") == (512, 1024)
    assert copy_range.beats_to_positions(2, 2, 2, 2, "signature") == (512, 1024)
    assert copy_range.beats_to_positions(1, 1, 3, 4, "signature") == (0, 256)
    with pytest.raises(copy_range.CopyRangeError, match="past the end"):
        copy_range.beats_to_positions(3, 5, 2, 2, "quarter")
    assert "quarter-note" in copy_range.beat_note(2, 2, "quarter", 3, 4, 512, 1024)


def test_copying_the_last_two_beats_replaces_only_that_range() -> None:
    plan = copy_range.plan_staff(1, 1, 32, 50, SOURCE, EMPTY_TAIL, 512, 1024, 512)
    assert plan.before == "z:2"
    assert plan.source == "G:1 G:1 | v1 Si me"
    kinds = [op["op"] for op in plan.ops]
    assert kinds == ["add-note", "add-note", "add-lyric", "add-lyric"]  # nothing to delete: only a rest was there
    assert [op["position"] for op in plan.ops] == [512, 768, 512, 768]
    assert all(op["bar"] == 50 and op["staff"] == 1 for op in plan.ops)
    batch_ops.validate_batch(plan.ops)


def test_existing_notes_and_lyrics_in_the_range_are_deleted_first_and_counted() -> None:
    dest = [note(0, 0, 512, 62), note(1, 512, 256, 60), lyric(2, 512, "no"), note(3, 768, 256, 60)]
    plan = copy_range.plan_staff(2, 2, 32, 35, SOURCE, dest, 512, 1024, 512)
    assert plan.replaced == {"notes": 2, "lyrics": 1}
    deletes = [op for op in plan.ops if op["op"] == "delete"]
    assert [(op["index"], op["type"]) for op in deletes] == [(1, "NoteRest"), (2, "LyricItem"), (3, "NoteRest")]
    assert plan.ops.index(deletes[-1]) < next(i for i, op in enumerate(plan.ops) if op["op"] == "add-note")
    assert not any(op["position"] < 512 for op in plan.ops)  # the first half is untouched


def test_dest_position_moves_the_range() -> None:
    plan = copy_range.plan_staff(1, 3, 32, 7, SOURCE, [rest(0, 0, 1024)], 512, 1024, 0)
    assert [op["position"] for op in plan.ops if op["op"] == "add-note"] == [0, 256]
    assert plan.ops[0]["staff"] == 3 and plan.ops[0]["bar"] == 7


def test_a_note_across_the_range_edge_is_refused_on_either_side() -> None:
    with pytest.raises(copy_range.CopyRangeError, match="crosses the edge"):
        copy_range.plan_staff(1, 1, 32, 50, SOURCE, EMPTY_TAIL, 256, 768, 256)
    dest = [note(0, 256, 512, 67), rest(1, 768, 256)]
    with pytest.raises(copy_range.CopyRangeError, match="would cut it"):
        copy_range.plan_staff(1, 1, 32, 50, SOURCE, dest, 512, 1024, 512)


def test_ties_voices_and_other_objects_are_carried_or_reported() -> None:
    source = [note(0, 0, 256, 67, tied=True, voice=2), {"type": "Text", "index": 1, "position": 0}]
    plan = copy_range.plan_staff(1, 1, 5, 6, source, [rest(0, 0, 1024)], 0, 256, 0)
    add = plan.ops[0]
    assert add["tied"] is True and add["voice"] == 2
    assert any("not copied" in w for w in plan.warnings)


def test_a_tie_into_the_range_with_a_different_pitch_is_flagged() -> None:
    prior = [note(0, 0, 512, 62, tied=True)]
    plan = copy_range.plan_staff(1, 1, 32, 50, SOURCE, EMPTY_TAIL, 512, 1024, 512, prior)
    assert any("different pitch" in w for w in plan.warnings)


def test_verify_compares_notes_and_words_after_the_shift() -> None:
    after = [note(0, 0, 512, 67), note(1, 512, 256, 67), lyric(2, 512, "Si"), note(3, 768, 256, 67), lyric(4, 768, "me")]
    assert copy_range.verify(SOURCE, after, 512, 1024, 512)
    after[1] = note(1, 512, 256, 62)
    assert not copy_range.verify(SOURCE, after, 512, 1024, 512)


def test_cli_accepts_the_new_options() -> None:
    args = build_parser().parse_args([
        "copy-passage", "--from-bar", "32", "--to-bar", "32", "--top-staff", "1", "--bottom-staff", "3",
        "--dest-staff", "1", "--dest-bar", "50", "--beats", "3-4", "--dry-run",
    ])
    assert args.beats == "3-4" and args.beat_unit == "quarter" and args.dry_run and args.dest_pos is None
