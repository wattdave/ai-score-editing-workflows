"""Tests for the vector-pdf-score skill: the MusicXML comparator and the Dorico PDF reader's staff finder."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / ".claude" / "skills" / "vector-pdf-score" / "scripts"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


compare_musicxml = _load("compare_musicxml")


def _score(notes: str, extra: str = "") -> str:
    return (
        '<score-partwise version="3.0"><part-list><score-part id="P1"><part-name>S</part-name></score-part></part-list>'
        '<part id="P1"><measure number="1"><attributes><divisions>4</divisions><key><fifths>-2</fifths></key>'
        '<time><beats>3</beats><beat-type>4</beat-type></time></attributes>' + extra + notes + '</measure></part></score-partwise>'
    )


def _note(step: str, octave: int, dur: int, lyric: str = "", tie: str = "", chord: bool = False) -> str:
    return (
        "<note>" + ("<chord/>" if chord else "") + f"<pitch><step>{step}</step><octave>{octave}</octave></pitch><duration>{dur}</duration>"
        + (f'<tie type="{tie}"/>' if tie else "") + (f"<lyric><text>{lyric}</text></lyric>" if lyric else "") + "</note>"
    )


def _write(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.write_text(body)
    return path


def test_load_reads_slots_with_onsets_in_quarter_256(tmp_path: Path) -> None:
    path = _write(tmp_path, "a.xml", _score(_note("B", 3, 4, "Hark") + _note("A", 3, 2) + _note("B", 3, 2)))
    parts, meta = compare_musicxml.load(path)
    assert parts["P1"] == {
        (1, 0, 59): (256, False, False, "Hark"),
        (1, 256, 57): (128, False, False, ""),
        (1, 384, 59): (128, False, False, ""),
    }
    assert meta["time"] == [(1, 3, 4)] and meta["key"] == [(1, -2)]


def test_chord_notes_share_the_onset(tmp_path: Path) -> None:
    path = _write(tmp_path, "a.xml", _score(_note("C", 4, 4) + _note("E", 4, 4, chord=True)))
    parts, _ = compare_musicxml.load(path)
    assert {k[:2] for k in parts["P1"]} == {(1, 0)}


def test_compare_reports_shared_missing_and_differing_slots(tmp_path: Path) -> None:
    ref = _write(tmp_path, "ref.xml", _score(_note("B", 3, 4, "Hark") + _note("A", 3, 4, "how") + _note("G", 3, 4)))
    cand = _write(tmp_path, "cand.xml", _score(_note("B", 3, 4, "Hark") + _note("A", 3, 2, "hou", tie="start") + _note("C", 4, 4)))
    lines: list[str] = []
    totals = compare_musicxml.compare(compare_musicxml.load(ref), compare_musicxml.load(cand), out=lines.append)
    assert totals == {"shared": 2, "ref_only": 1, "cand_only": 1, "duration": 1, "tie": 1, "lyric": 1}
    assert any("only in reference 1" in line for line in lines)
    assert "time signatures: same" in lines and "key signatures: same" in lines


def test_compare_flags_a_changed_time_signature(tmp_path: Path) -> None:
    ref = _write(tmp_path, "ref.xml", _score(_note("B", 3, 4)))
    cand = _write(tmp_path, "cand.xml", _score(_note("B", 3, 4)).replace("<beats>3</beats>", "<beats>2</beats>"))
    lines: list[str] = []
    compare_musicxml.compare(compare_musicxml.load(ref), compare_musicxml.load(cand), out=lines.append)
    assert any(line.startswith("time signatures: reference") for line in lines)


# ---- Dorico PDF reader: staff lines, barlines and repeat markers are drawings, so a synthetic page can test them

def _staff(page, top: float, x0: float = 72.0, x1: float = 570.0, sp: float = 5.0) -> None:
    for i in range(5):
        y = top + i * sp
        page.draw_line((x0, y), (x1, y), width=0.125 * sp)


def test_find_staves_reads_five_lines_and_groups_by_extent() -> None:
    pymupdf = pytest.importorskip("pymupdf")
    dorico_pdf = _load("dorico_pdf")
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    _staff(page, 100); _staff(page, 160); _staff(page, 300, x0=42, x1=398); _staff(page, 300, x0=428, x1=570)
    _, _, hlines, _ = dorico_pdf.page_items(page)
    staves = dorico_pdf.find_staves(hlines)
    assert len(staves) == 4
    assert {round(s["sp"], 2) for s in staves} == {5.0}
    assert sorted((round(s["top"]), round(s["x0"])) for s in staves) == [(100, 72), (160, 72), (300, 42), (300, 428)]


def test_staff_measurements_scale_with_the_staff_space() -> None:
    """the 20 pt and 13.5 pt exports have staff spaces of 4.96 and 3.375; stems and barlines scale with them"""
    pymupdf = pytest.importorskip("pymupdf")
    dorico_pdf = _load("dorico_pdf")
    for sp in (4.96, 3.375):
        doc = pymupdf.open()
        page = doc.new_page(width=612, height=792)
        _staff(page, 100, sp=sp)
        for x in (200.0, 330.0, 570.0): page.draw_line((x, 100), (x, 100 + 4 * sp), width=0.2 * sp)
        page.draw_line((325.0, 100), (325.0, 100 + 4 * sp), width=0.5 * sp)
        glyphs, vlines, hlines, _ = dorico_pdf.page_items(page)
        staff = dorico_pdf.find_staves(hlines)[0]
        dorico_pdf.staff_marks(glyphs, vlines, staff)
        assert staff["bars"] == [200.0, 330.0, 570.0]
        assert [round(x) for x in staff["thick"]] == [325]
        assert staff["clef"] == "F"          # no Bravura clef glyph on the synthetic page
        assert staff["u"] == pytest.approx(sp / 4.96, rel=1e-3)


def test_staff_edges_treat_a_thin_line_after_a_thick_one_as_a_start_repeat() -> None:
    dorico_pdf = _load("dorico_pdf")
    staff = dict(x0=42.0, x1=570.0, u=1.0, bars=[180.0, 280.0, 473.0, 564.5], thick=[468.5, 568.8], dots=[559.6])
    dorico_pdf.staff_edges(staff)
    assert staff["edges"] == [42.0, 180.0, 280.0, 468.5, 564.5]
    assert staff["rep_start_x"] == [473.0] and staff["rep_end_x"] == [564.5]


def test_key_alter_spells_flats_and_sharps_in_order() -> None:
    dorico_pdf = _load("dorico_pdf")
    assert dorico_pdf.key_alter(-2) == {6: -1, 2: -1}      # B and E flat
    assert dorico_pdf.key_alter(3) == {3: 1, 0: 1, 4: 1}   # F, C and G sharp
    assert dorico_pdf.key_alter(0) == {}
    assert dorico_pdf.midi(30, 0) == 64 and dorico_pdf.midi(27, -1) == 58   # E4 and B flat 3


def test_rest_and_pitch_spelling_in_the_musicxml_writer() -> None:
    pytest.importorskip("pymupdf")
    writer = _load("dorico_pdf_musicxml")
    assert writer.pitch_xml(58, -2) == "<pitch><step>B</step><alter>-1</alter><octave>3</octave></pitch>"
    assert writer.pitch_xml(66, 0) == "<pitch><step>F</step><alter>1</alter><octave>4</octave></pitch>"
    assert writer.rest_xml(12, measure=True).startswith('<note><rest measure="yes"/><duration>12</duration>')
    assert writer.rest_xml(6).count("<rest/>") == 1 and "<dot/>" in writer.rest_xml(6)
