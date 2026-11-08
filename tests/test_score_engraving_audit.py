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
