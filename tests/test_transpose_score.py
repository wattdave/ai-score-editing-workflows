"""Tests for the transpose-score skill script."""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
from helpers import ROOT, load_script

tx = load_script(ROOT / ".claude/skills/transpose-score/scripts/transpose_musicxml.py", "transpose_musicxml")

HEADER = '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 3.1 Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">\n'


def note(step: str, octave: int, alter: int = 0, extra: str = "") -> str:
    a = f"<alter>{alter}</alter>" if alter else ""
    return f"<note><pitch><step>{step}</step>{a}<octave>{octave}</octave></pitch><duration>4</duration><type>quarter</type>{extra}</note>"


def score(*notes: str, fifths: int = -2, harmony: str = "") -> str:
    return (
        HEADER
        + '<score-partwise version="3.1"><part-list><score-part id="P1"><part-name>Cantus</part-name></score-part>'
        + '<score-part id="P2"><part-name>Bassus</part-name></score-part></part-list>'
        + f'<part id="P1"><measure number="1"><attributes><divisions>4</divisions><key><fifths>{fifths}</fifths></key></attributes>'
        + harmony
        + "".join(notes)
        + '</measure></part><part id="P2"><measure number="1">'
        + note("C", 2)
        + "</measure></part></score-partwise>"
    )


def run(tmp_path: Path, text: str, *args: str) -> ET.Element:
    src, out = tmp_path / "in.xml", tmp_path / "out.xml"
    src.write_text(text, encoding="utf-8")
    assert tx.main([str(src), str(out), *args]) == 0
    return ET.fromstring(out.read_text(encoding="utf-8"))


def spelled(root: ET.Element, part: str = "P1") -> list[str]:
    out = []
    for n in root.find(f"./part[@id='{part}']").iter("note"):
        p = n.find("pitch")
        alter = {"-1": "b", "1": "#", "": ""}[p.findtext("alter") or ""]
        out.append(p.findtext("step") + alter + p.findtext("octave"))
    return out


def test_up_major_second_respells_and_shifts_the_key(tmp_path):
    root = run(tmp_path, score(note("D", 4), note("E", 4, -1), note("B", 3, -1)), "--by", "up M2")
    assert spelled(root) == ["E4", "F4", "C4"]
    assert root.find(".//fifths").text == "0"


def test_down_minor_third_across_an_octave_boundary(tmp_path):
    root = run(tmp_path, score(note("D", 4), note("C", 4)), "--by", "down m3")
    assert spelled(root) == ["B3", "A3"]
    assert root.find(".//fifths").text == "1"  # B-flat major (-2) down a minor third is G major (+1)


def test_fifths_override_and_keep_key(tmp_path):
    root = run(tmp_path, score(note("D", 4)), "--by", "up M2", "--fifths", "-3")
    assert root.find(".//fifths").text == "-3"
    root = run(tmp_path, score(note("D", 4)), "--by", "up M2", "--keep-key")
    assert root.find(".//fifths").text == "-2"


def test_ficta_mark_names_the_new_accidental(tmp_path):
    ficta_nat = '<notations><accidental-mark placement="above">natural</accidental-mark></notations>'
    ficta_flat = '<notations><accidental-mark placement="above">flat</accidental-mark></notations>'
    root = run(tmp_path, score(note("B", 4, 0, ficta_nat), note("A", 3, -1, ficta_flat)), "--by", "up M2")
    assert spelled(root) == ["C#5", "Bb3"]
    marks = [m.text for m in root.iter("accidental-mark")]
    assert marks == ["sharp", "flat"]


def test_explicit_accidentals_are_removed_so_editors_recompute_them(tmp_path):
    root = run(tmp_path, score(note("B", 3, 0, "<accidental>natural</accidental>")), "--by", "up M2")
    assert root.find(".//accidental") is None


def test_chord_symbols_follow(tmp_path):
    harmony = "<harmony><root><root-step>B</root-step><root-alter>-1</root-alter></root><kind>major</kind><bass><bass-step>F</bass-step></bass></harmony>"
    root = run(tmp_path, score(note("D", 4), harmony=harmony), "--by", "up M2")
    assert root.find(".//root-step").text == "C"
    assert root.find(".//root-alter") is None
    assert root.find(".//bass-step").text == "G"


def test_octave_shift_by_part_name(tmp_path):
    root = run(tmp_path, score(note("D", 4)), "--by", "up M2", "--octave", "Bassus=1")
    assert spelled(root, "P2") == ["D3"]
    assert spelled(root, "P1") == ["E4"]


def test_report_lists_ranges(tmp_path, capsys):
    run(tmp_path, score(note("D", 4), note("G", 4)), "--by", "up M2", "--report")
    assert "P1 Cantus: D4-G4 -> E4-A4" in capsys.readouterr().out


def test_header_is_kept_and_bad_interval_is_refused(tmp_path):
    src, out = tmp_path / "in.xml", tmp_path / "out.xml"
    src.write_text(score(note("D", 4)), encoding="utf-8")
    assert tx.main([str(src), str(out), "--by", "up M2"]) == 0
    assert out.read_text().startswith(HEADER)
    assert tx.main([str(src), str(out), "--by", "sideways"]) == 2


@pytest.mark.parametrize("by,expected", [("up P5", ["A4"]), ("up m2", ["Eb4"]), ("down P4", ["A3"]), ("up P8", ["D5"])])
def test_interval_table(tmp_path, by, expected):
    assert spelled(run(tmp_path, score(note("D", 4)), "--by", by)) == expected
