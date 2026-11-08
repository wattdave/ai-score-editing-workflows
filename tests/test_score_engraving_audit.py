"""Tests for the score-engraving-audit skill script."""

from __future__ import annotations

from xml.etree import ElementTree as ET

from helpers import ROOT, load_script

audit = load_script(ROOT / ".claude/skills/score-engraving-audit/scripts/audit_musicxml.py", "audit_musicxml")


def _note(step: str, typ: str, dur: int, beam: str | None = None, lyric: str | None = None) -> str:
    b = f'<beam number="1">{beam}</beam>' if beam else ""
    ly = f"<lyric><syllabic>single</syllabic><text>{lyric}</text></lyric>" if lyric else ""
    return f"<note><pitch><step>{step}</step><octave>4</octave></pitch><duration>{dur}</duration><type>{typ}</type>{b}{ly}</note>"


def _score(notes: str, title: str = "Silent Night", part: str = "Soprano", time: tuple[int, int] = (6, 8), words: str = "") -> ET.Element:
    return ET.fromstring(
        f"""<score-partwise><work><work-title>{title}</work-title></work>
        <part-list><score-part id="P1"><part-name>{part}</part-name></score-part></part-list>
        <part id="P1"><measure number="1"><attributes><divisions>4</divisions>
        <time><beats>{time[0]}</beats><beat-type>{time[1]}</beat-type></time></attributes>{words}{notes}</measure></part>
        </score-partwise>"""
    )


def codes(root: ET.Element) -> set[str]:
    return {f["code"] for f in audit.audit(root)}


def test_partly_beamed_compound_beat_is_flagged() -> None:
    # 6/8, divisions 4: dotted-eighth+sixteenth joined, third eighth loose (beat = 3 eighths).
    notes = _note("G", "eighth", 3, "begin") + _note("A", "16th", 1, "end") + _note("G", "eighth", 2)
    assert "beams-mixed" in codes(_score(notes))


def test_fully_beamed_group_is_clean() -> None:
    notes = _note("G", "eighth", 2, "begin") + _note("A", "eighth", 2, "continue") + _note("G", "eighth", 2, "end")
    assert not {"beams-mixed", "beams-some-unbeamed"} & codes(_score(notes))


def test_beamless_file_is_info_only() -> None:
    notes = _note("G", "eighth", 2) + _note("A", "eighth", 2) + _note("G", "eighth", 2)
    found = {f["code"]: f["severity"] for f in audit.audit(_score(notes))}
    assert found["beams-none"] == "info"


def test_generic_part_name_and_title_problems() -> None:
    found = codes(_score(_note("C", "quarter", 2), title=" deck the halls", part="Voice0"))
    assert {"part-name-generic", "title-whitespace", "title-case"} <= found


def test_lowercase_chord_text_is_flagged() -> None:
    words = "".join(f"<direction><direction-type><words>{w}</words></direction-type></direction>" for w in ("F", "c", "c7"))
    assert {"chords-as-text", "chords-lowercase"} <= codes(_score(_note("C", "quarter", 2), words=words))


def test_cli_exit_codes(tmp_path) -> None:
    good = tmp_path / "a.xml"
    good.write_text(ET.tostring(_score(_note("C", "quarter", 2))).decode())
    assert audit.main([str(good)]) == 0
    assert audit.main([str(tmp_path / "missing.xml")]) == 2


def test_hidden_time_signatures_are_reported() -> None:
    root = ET.fromstring(
        """<score-partwise><part-list><score-part id="P1"><part-name>S</part-name></score-part></part-list>
        <part id="P1"><measure number="1"><attributes><divisions>1</divisions>
        <time print-object="no"><beats>3</beats><beat-type>2</beat-type></time></attributes></measure>
        <measure number="2"><attributes><time print-object="no"><beats>2</beats><beat-type>2</beat-type></time></attributes></measure>
        </part></score-partwise>"""
    )
    found = [f for f in audit.audit(root) if f["code"] == "time-hidden"]
    assert found and found[0]["message"].startswith("2 bar(s)") and "hide-time-signatures" in found[0]["message"]


# Bar-sum checks. Excerpts are cut down from the Nelson Carol Book raw scans
# (Halbestunde and MuseScore Convert, 2026-11): divisions 2, voices 1 and 2.


def _n(pitch: str | None, dur: int, voice: int = 1, lyric: str | None = None) -> str:
    body = f"<pitch><step>{pitch[0]}</step><octave>{pitch[1]}</octave></pitch>" if pitch else "<rest/>"
    ly = f"<lyric number='1'><syllabic>single</syllabic><text>{lyric}</text></lyric>" if lyric else ""
    return f"<note>{body}<duration>{dur}</duration><voice>{voice}</voice>{ly}</note>"


def _bars(*bars: str, beats: int = 3, implicit: tuple[int, ...] = ()) -> ET.Element:
    attributes = f"<attributes><divisions>2</divisions><time><beats>{beats}</beats><beat-type>4</beat-type></time></attributes>"
    measures = "".join(
        f"<measure number='{i + 1}' implicit='{'yes' if i in implicit else 'no'}'>{attributes if i == 0 else ''}{body}</measure>"
        for i, body in enumerate(bars)
    )
    return ET.fromstring(
        "<score-partwise><work><work-title>Carol</work-title></work><part-list><score-part id='P1'>"
        f"<part-name>Choir</part-name></score-part></part-list><part id='P1'>{measures}</part></score-partwise>"
    )


def two_voices(v1: str, v2: str, back: int) -> str:
    return v1 + f"<backup><duration>{back}</duration></backup>" + v2


FULL_34 = two_voices(_n("G4", 6), _n("D4", 6, 2), 6)
FULL_44 = two_voices(_n("G4", 8), _n("D4", 8, 2), 8)
LAST_2_BEATS = two_voices(_n("G4", 4), _n("D4", 4, 2), 4)
BAR_CODES = {"score-empty", "bar1-empty", "bar1-pickup-suspect", "bars-short"}


def bar_findings(root: ET.Element) -> dict[str, str]:
    return {f["code"]: f["message"] for f in audit.audit(root) if f["code"] in BAR_CODES}


def test_clean_pickup_and_matching_last_bar_pass() -> None:
    pickup = two_voices(_n("D4", 2, lyric="We"), _n("B3", 2, 2), 2)
    assert bar_findings(_bars(pickup, FULL_34, LAST_2_BEATS)) == {}


def test_empty_score_is_an_error() -> None:  # Adeste Fideles at pad 40: one bar, no notes
    assert set(bar_findings(_bars(""))) == {"score-empty"}


def test_empty_leading_bar() -> None:  # Deck the Hall: bar 1 is one short rest per voice
    rests = two_voices(_n(None, 1), _n(None, 1, 2), 1)
    assert "bar1-empty" in bar_findings(_bars(rests, FULL_44, beats=4))


def test_verse_number_notes_and_uneven_voices_in_pickup() -> None:
    # The First Nowell: "1." read as two extra eighths in voice 1 (4 eighths against a 2-eighth pickup)
    v1 = _n("D4", 1, lyric="1.") + _n("A3", 1) + _n("F4", 1, lyric="The") + _n("E4", 1, lyric="first")
    found = bar_findings(_bars(two_voices(v1, _n("C4", 2, 2), 4), FULL_34, FULL_34))
    assert "verse number" in found["bar1-pickup-suspect"]
    assert "[2, 4]" in found["bar1-pickup-suspect"]


def test_pickup_padded_with_rests() -> None:  # O Come, All Ye Faithful: half rest + the quarter pickup
    bar1 = two_voices(_n(None, 4) + _n("G4", 2), _n(None, 4, 2) + _n("D4", 2, 2), 6)
    found = bar_findings(_bars(bar1, FULL_44, beats=4))
    assert "opens with a rest" in found["bar1-pickup-suspect"]


def test_pickup_read_as_full_bar_and_dropped_rests() -> None:
    # We Wish You a Merry Christmas (Halbestunde): bar 1 full, last bar 2 beats; voice 2 lost its rest
    dropped = two_voices(_n("G4", 4) + _n(None, 2), _n("D4", 4, 2), 6)
    found = bar_findings(_bars(FULL_34, dropped, LAST_2_BEATS))
    assert "pickup of 2" in found["bar1-pickup-suspect"]
    assert "bar 2 (staff/voice 1/2)" in found["bars-short"]


def test_overfull_first_bar() -> None:  # We Three Kings: a bass voice lasts 5 eighths in 3/8 (here 7 in 3/4)
    bar1 = two_voices(_n("G4", 6), _n("B3", 4, 2) + _n("B3", 3, 2), 6)
    assert "lasts 7 of 6" in bar_findings(_bars(bar1, FULL_34))["bar1-pickup-suspect"]


def test_split_bars_are_not_short() -> None:  # Dorico writes a bar split by a barline as two halves, one implicit
    half = two_voices(_n("G4", 2), _n("D4", 2, 2), 2)
    assert "bars-short" not in bar_findings(_bars(FULL_34, half, LAST_2_BEATS, FULL_34, implicit=(2,)))
