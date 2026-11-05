"""Tests for the beaming-repair skill script."""

from __future__ import annotations

from xml.etree import ElementTree as ET

from helpers import ROOT, load_script

fix = load_script(ROOT / ".claude/skills/beaming-repair/scripts/fix_beams.py", "fix_beams")
audit = load_script(ROOT / ".claude/skills/score-engraving-audit/scripts/audit_musicxml.py", "audit_musicxml_for_beams")


def note(typ: str, dur: int, beam: str | None = None, lyric: str | None = None, dot: bool = False, chord: bool = False, rest: bool = False) -> str:
    b = f'<beam number="1">{beam}</beam>' if beam else ""
    ly = f"<lyric><syllabic>single</syllabic><text>{lyric}</text></lyric>" if lyric else ""
    body = "<rest/>" if rest else "<pitch><step>C</step><octave>4</octave></pitch>"
    return f"<note>{'<chord/>' if chord else ''}{body}<duration>{dur}</duration><voice>1</voice><type>{typ}</type>{'<dot/>' if dot else ''}{b}{ly}</note>"


def score(notes: str, time: tuple[int, int] = (6, 8)) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n<score-partwise version="3.0"><part-list>'
        '<score-part id="P1"><part-name>S</part-name></score-part></part-list><part id="P1"><measure number="1">'
        f"<attributes><divisions>4</divisions><time><beats>{time[0]}</beats><beat-type>{time[1]}</beat-type></time></attributes>"
        f"{notes}</measure></part></score-partwise>"
    )


def run(tmp_path, xml: str, *args: str) -> ET.Element:
    src, dst = tmp_path / "in.xml", tmp_path / "out.xml"
    src.write_text(xml)
    assert fix.main([str(src), str(dst), *args]) == 0
    return ET.parse(dst).getroot()


def beams(root: ET.Element) -> list[list[tuple[str, str]]]:
    return [[(b.get("number"), b.text) for b in n.findall("beam")] for n in root.iter("note")]


def test_partial_compound_group_is_completed(tmp_path) -> None:
    xml = score(note("eighth", 3, "begin", dot=True) + note("16th", 1, "end") + note("eighth", 2))
    out = beams(run(tmp_path, xml))
    assert out[0] == [("1", "begin")]
    assert out[1] == [("1", "continue"), ("2", "backward hook")]
    assert out[2] == [("1", "end")]


def test_complete_and_unbeamed_groups_untouched_in_mixed_scope(tmp_path) -> None:
    done = note("eighth", 2, "begin") + note("eighth", 2, "continue") + note("eighth", 2, "end")
    loose = note("eighth", 2) + note("eighth", 2) + note("eighth", 2)
    assert beams(run(tmp_path, score(done + loose))) == [[("1", "begin")], [("1", "continue")], [("1", "end")], [], [], []]


def test_scope_all_beams_unbeamed_groups(tmp_path) -> None:
    out = beams(run(tmp_path, score(note("eighth", 2) * 3), "--scope", "all"))
    assert [b[0][1] for b in out] == ["begin", "continue", "end"]


def test_rest_breaks_the_beam(tmp_path) -> None:
    # 4/4, divisions 4: beat 1 = two eighths, beat 2 = rest + eighth (nothing to join).
    xml = score(note("eighth", 2) + note("eighth", 2) + note("eighth", 2, rest=True) + note("eighth", 2), (4, 4))
    out = beams(run(tmp_path, xml, "--scope", "all"))
    assert out == [[("1", "begin")], [("1", "end")], [], []]


def test_syllabic_breaks_at_new_syllable_and_keeps_melisma(tmp_path) -> None:
    xml = score(note("eighth", 2, lyric="Sil") + note("eighth", 2) + note("eighth", 2, lyric="lent"), (6, 8))
    out = beams(run(tmp_path, xml, "--scope", "all", "--style", "syllabic"))
    assert out[0] == [("1", "begin")] and out[1] == [("1", "end")] and out[2] == []


def test_strip_removes_all_beams(tmp_path) -> None:
    xml = score(note("eighth", 2, "begin") + note("eighth", 2, "end"))
    assert beams(run(tmp_path, xml, "--strip")) == [[], []]


def test_chord_notes_get_same_beams_and_nothing_else_changes(tmp_path) -> None:
    xml = score(note("eighth", 3, "begin", dot=True) + note("eighth", 3, dot=True, chord=True) + note("16th", 1, "end") + note("16th", 1, chord=True) + note("eighth", 2))
    root = run(tmp_path, xml)
    b = beams(root)
    assert b[0][0] == b[1][0] == ("1", "begin") and b[2][0] == b[3][0]
    before = [tuple((c.tag, (c.text or "").strip()) for c in n if c.tag != "beam") for n in ET.fromstring(xml).iter("note")]
    after = [tuple((c.tag, (c.text or "").strip()) for c in n if c.tag != "beam") for n in root.iter("note")]
    assert before == after


def test_idempotent_and_clears_audit_finding(tmp_path) -> None:
    xml = score(note("eighth", 3, "begin", dot=True) + note("16th", 1, "end") + note("eighth", 2))
    assert "beams-mixed" in {f["code"] for f in audit.audit(ET.fromstring(xml))}
    first = run(tmp_path, xml)
    assert "beams-mixed" not in {f["code"] for f in audit.audit(first)}
    again = run(tmp_path, ET.tostring(first, encoding="unicode"))
    assert beams(again) == beams(first)


def test_header_preserved(tmp_path) -> None:
    xml = '<?xml version="1.0"?>\n<!DOCTYPE score-partwise PUBLIC "x" "y">\n' + score(note("eighth", 2) * 3).split("\n", 1)[1]
    src, dst = tmp_path / "a.xml", tmp_path / "b.xml"
    src.write_text(xml)
    fix.main([str(src), str(dst)])
    assert "<!DOCTYPE score-partwise" in dst.read_text()
