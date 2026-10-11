"""The selection probe's model and argument parsing (no Dorico needed)."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

from ai_score_editing.dorico.bridge import BarMap

ROOT = Path(__file__).parent.parent
spec = importlib.util.spec_from_file_location("dorico_selection_probe", ROOT / "scripts" / "dorico_selection_probe.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)

BAR = 1024


def note(id_: int, start: int, duration: int) -> dict:
    return {"id": id_, "type": "NoteEvent", "staff": 1, "voice": 1, "stream": 4, "duration": duration,
            "flowPosition": start, "bar": start // BAR + 1}


def lab(events: list[dict]) -> SimpleNamespace:
    bars = BarMap([(0, BAR)])
    return SimpleNamespace(located=events, bars=bars, bar_of=lambda p: bars.locate(p)[0])


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
