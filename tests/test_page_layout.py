"""Pure page-layout planning behind sibelius-cli auto-layout."""

from __future__ import annotations

import pytest

from ai_score_editing.core import page_layout as pl
from ai_score_editing.core.errors import BatchError
from ai_score_editing.sibelius import batch_ops


def test_parse_systems_splits_pages_and_bars() -> None:
    assert pl.parse_systems("1,5,9 / 13 17,21|25") == [[1, 5, 9], [13, 17, 21], [25]]


@pytest.mark.parametrize("spec", ["1,5,5", "9,5", "1,x", "1,5//9", "-1,4"])
def test_parse_systems_refuses_bad_specs(spec: str) -> None:
    with pytest.raises(BatchError):
        pl.parse_systems(spec)


def test_breaks_go_on_the_bar_before_each_system_and_never_bar_0() -> None:
    plan = pl.plan([[5, 9], [13, 17]], verses=2, staves=2)
    assert plan.pages == [[1, 5, 9], [13, 17]]
    assert plan.batch[:4] == [
        {"op": "set-break", "bar": 4, "type": "system"},
        {"op": "set-break", "bar": 8, "type": "system"},
        {"op": "set-break", "bar": 12, "type": "page"},
        {"op": "set-break", "bar": 16, "type": "system"},
    ]
    assert all(op["bar"] >= 1 for op in plan.batch if op["op"] == "set-break")


def test_pickup_offset_shifts_printed_bars() -> None:
    plan = pl.plan([[0, 5, 10]], verses=4, staves=2, offset=1, hide=[(0, 4)])
    assert plan.pages == [[1, 6, 11]]
    assert [op["bar"] for op in plan.batch if op["op"] == "set-break"] == [5, 10]
    assert {"op": "hide-empty-staves", "fromBar": 1, "toBar": 5} in plan.batch


def test_set_layout_is_last_and_the_batch_validates() -> None:
    plan = pl.plan([[1, 5]], verses=4, staves=2, hide=[(4, 15)])
    assert [op["op"] for op in plan.batch] == ["set-break", "hide-empty-staves", "set-layout"]
    batch_ops.validate_batch(plan.batch)


@pytest.mark.parametrize(
    ("staves", "verses", "systems", "expected"),
    [
        (2, 2, 4, (6, 12, 9)),
        (2, 4, 4, (6.5, 17, 9)),
        (2, 5, 4, (6, 22, 8)),
        (2, 6, 4, (5.5, 24, 6)),
        (2, 3, 8, (4.6, 13, 4)),
        (3, 4, 3, (5, 12, 10)),
        (4, 3, 3, (5.5, 8, 4)),
        (1, 1, 14, (5, 6, 7)),
    ],
)
def test_layout_table(staves: int, verses: int, systems: int, expected: tuple[float, float, float]) -> None:
    settings = pl.choose_preset(staves, verses, systems).settings
    assert (settings["staffSize"], settings["spacesBetweenStaves"], settings["spacesBetweenSystems"]) == expected


def test_unmeasured_rows_are_flagged() -> None:
    assert pl.choose_preset(2, 4, 4).measured
    assert not pl.choose_preset(2, 3, 4).measured
    plan = pl.plan([[1, 5]], verses=3, staves=2)
    assert any("not measured" in note for note in plan.notes)


def test_hidden_staves_cap_staff_size_and_overrides_win() -> None:
    plan = pl.plan([[1, 5]], verses=4, staves=2, hide=[(1, 4)])
    assert plan.batch[-1]["staffSize"] == pl.HIDDEN_STAFF_MAX_SIZE
    plan = pl.plan([[1, 5]], verses=4, staves=2, hide=[(1, 4)],
                   overrides=pl.parse_overrides(["staffSize=6", "pageSize=a4"]))
    assert plan.batch[-1]["staffSize"] == 6
    assert plan.batch[-1]["pageSize"] == "a4"


@pytest.mark.parametrize("item", ["staffSize", "nope=3", "staffSize=big", "pageSize=huge"])
def test_parse_overrides_refuses_bad_items(item: str) -> None:
    with pytest.raises(BatchError):
        pl.parse_overrides([item])


def test_parse_range() -> None:
    assert pl.parse_range("11-18") == (11, 18)
    assert pl.parse_range("7") == (7, 7)
    with pytest.raises(BatchError):
        pl.parse_range("18-11")


def test_ready_with_starts_and_page_starts() -> None:
    data = {
        "bars": 34,
        "breaks": [5, 9, 13, 17, 22, 26, 31],
        "page_breaks": [9, 17, 26],
        "pages_in_print": 4,
        "post_import": ["system breaks before bars 5,9,13; page breaks before 9, 17, 26 (4 pages)"],
    }
    pages, offset, notes = pl.pages_from_ready(data)
    assert pages == [[5], [9, 13], [17, 22], [26, 31]]
    assert offset == 0 and notes == []


def test_ready_page_start_missing_from_system_starts_and_first_page_without_bar_1() -> None:
    pages, _, _ = pl.pages_from_ready({"breaks": [10, 16, 22, 32, 36], "page_breaks": [4, 27], "pages_in_print": 3})
    assert pages == [[], [4, 10, 16, 22], [27, 32, 36]]
    assert pl.to_score_bars(pages, 0) == [[1], [4, 10, 16, 22], [27, 32, 36]]


def test_ready_ends_after_also_shifts_page_breaks() -> None:
    data = {"bars": 48, "breaks": {"system_ends_after_bars": [5, 10, 14, 19, 48]}, "page_breaks": [14]}
    pages, _, _ = pl.pages_from_ready(data)
    assert pages == [[6, 11], [15, 20]]


def test_ready_bare_list_said_after_is_read_as_ends() -> None:
    data = {"bars": 10, "breaks": [5], "page_breaks": [], "post_import": ["system break after bar 5"]}
    pages, _, notes = pl.pages_from_ready(data)
    assert pages == [[6]]
    assert "after" in notes[0]


def test_ready_pickup_and_page_count_notes() -> None:
    data = {
        "bars": "20 measures: pickup quarter (number 0, implicit)",
        "breaks": {"system_starts_at_measures": [5, 10, 15], "system_ends_after_measures": [4, 9, 14, 19]},
        "page_breaks": [],
        "pages_in_print": 2,
    }
    pages, offset, notes = pl.pages_from_ready(data)
    assert pages == [[5, 10, 15]] and offset == 1
    assert any("pickup" in n for n in notes) and any("2 page(s)" in n for n in notes)


def test_actual_pages_from_bar_rows() -> None:
    where = [(1, 1), (1, 1), (1, 2), (1, 2), (2, 3), (2, 3), (2, 4)]
    rows = [{"bar": i + 1, "fields": {"OnNthPage": p, "OnNthSystem": s}} for i, (p, s) in enumerate(where)]
    assert pl.actual_pages(rows) == [[1, 3], [5, 7]]
    assert pl.compare_pages([[1, 3], [5, 7]], pl.actual_pages(rows)) == []
    problems = pl.compare_pages([[1, 4], [5, 7], [8]], pl.actual_pages(rows))
    assert problems == ["2 page(s), expected 3", "page 1: systems start at bars [1, 3], expected [1, 4]"]


def test_count_pdf_pages() -> None:
    tree = b"1 0 obj << /Type /Pages /Kids [3 0 R 4 0 R] /Count 2 >> endobj 3 0 obj << /Type /Page >>"
    assert pl.count_pdf_pages(tree) == 2
    assert pl.count_pdf_pages(b"<< /Type /Page >> << /Type/Page >> << /Type /Pages >>") == 2
    assert pl.count_pdf_pages(b"%PDF-1.7 compressed") is None


def test_layout_last_moves_set_layout_and_warns() -> None:
    batch = batch_ops.validate_batch([
        {"op": "set-layout", "staffSize": 6},
        {"op": "set-break", "bar": 4, "type": "system"},
    ])
    reordered, warning = batch_ops.layout_last(batch)
    assert [op["op"] for op in reordered] == ["set-break", "set-layout"]
    assert warning and "op 0" in warning
    same, none = batch_ops.layout_last(reordered)
    assert same is reordered and none is None
