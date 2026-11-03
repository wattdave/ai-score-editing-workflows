"""The selection probe's model and argument parsing (no Dorico needed)."""

from pathlib import Path
from types import SimpleNamespace

from helpers import load_script

from ai_score_editing.dorico.bridge import BarMap

ROOT = Path(__file__).parent.parent
probe = load_script(ROOT / "scripts" / "dev" / "dorico_selection_probe.py")

BAR = 1024


def note(id_: int, start: int, duration: int) -> dict:
    return {"id": id_, "type": "NoteEvent", "staff": 1, "voice": 1, "stream": 4, "duration": duration,
            "flowPosition": start, "bar": start // BAR + 1}


def lab(events: list[dict], slurs: list[tuple[int, int, int, int, int]] | None = None) -> SimpleNamespace:
    bars = BarMap([(0, BAR)])
    return SimpleNamespace(located=events, bars=bars, bar_of=lambda p: bars.locate(p)[0], slurs=slurs or [], tie_offset=0,
                           staves=[{"staff": 1, "name": "Piano"}])


def test_parse_ranges() -> None:
    assert probe.parse_ranges("5-8,7") == [(5, 8), (7, 7)]


def test_a_selection_ending_on_a_barline_moves_a_whole_bar() -> None:
    events = [note(i, i * BAR, BAR) for i in range(4)]
    assert probe.predict_bars(lab(events), 1, events[0], 1) == (1, 2)
    assert probe.predict_bars(lab(events), 1, events[0], 3) == (1, 4)


def test_a_short_note_reaches_the_end_of_its_own_bar() -> None:
    events = [note(1, 0, 256), note(2, 256, 768), note(3, BAR, BAR)]
    assert probe.predict_bars(lab(events), 1, events[0], 1) == (1, 1)


def test_a_tie_over_the_barline_drags_the_next_bar_in() -> None:
    events = [note(1, 0, BAR + 256), note(2, BAR + 256, 768), note(3, 2 * BAR, BAR)]
    assert probe.predict_bars(lab(events), 1, events[0], 1) == (1, 2)


def test_a_slur_starting_inside_the_selection_drags_in_the_bars_it_spans() -> None:
    # whole notes in bars 1, 2, 4, 6; half notes in bars 3 and 5; a slur from bar 3 to the second half of bar 5
    events = [note(1, 0, BAR), note(2, BAR, BAR), note(3, 2 * BAR, 512), note(4, 2 * BAR + 512, 512),
              note(5, 3 * BAR, BAR), note(6, 4 * BAR, 512), note(7, 4 * BAR + 512, 512), note(8, 5 * BAR, BAR)]
    slurs = [(1, 3, 0, 5, 512)]
    assert probe.predict_bars(lab(events), 1, events[0], 2) == (1, 3)
    assert probe.predict_bars(lab(events, slurs), 1, events[0], 2, slurs=True) == (1, 5)
    # a slur that starts before the anchor is not pulled in
    assert probe.predict_bars(lab(events, slurs), 1, events[3], 1, slurs=True) == (3, 4)


def test_a_slur_ending_on_a_barline_does_not_touch_the_next_bar() -> None:
    # bars 1-3 of half notes; a slur from the second half of bar 1 to the first note of bar 2
    events = [note(1, 0, 512), note(2, 512, 512), note(3, BAR, 512), note(4, BAR + 512, 512), note(5, 2 * BAR, BAR)]
    slurs = [(1, 1, 512, 2, 0)]
    assert probe.predict_bars(lab(events, slurs), 1, events[0], 1, slurs=True) == (1, 1)
    # ending inside the next bar it does reach it
    inside = [(1, 1, 512, 2, 512)]
    assert probe.predict_bars(lab(events, inside), 1, events[0], 1, slurs=True) == (1, 2)
