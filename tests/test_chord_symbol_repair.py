"""Tests for the chord-symbol-repair skill script."""

from __future__ import annotations

import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
from helpers import ROOT, load_script

fx = load_script(ROOT / ".claude/skills/chord-symbol-repair/scripts/fix_chords.py", "fix_chords")
audit = load_script(ROOT / ".claude/skills/score-engraving-audit/scripts/audit_musicxml.py", "audit_musicxml_for_chords")

HEADER = '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 3.1 Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">\n'


def direction(text: str, extra: str = "", placement: str = "") -> str:
    p = f' placement="{placement}"' if placement else ""
    return f"<direction{p}><direction-type><words>{text}</words></direction-type>{extra}</direction>"


NOTE = "<note><pitch><step>G</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>"


def score(*texts: str, raw: str = "") -> str:
    body = "".join(direction(t) for t in texts) + raw
    return (
        HEADER
        + '<score-partwise version="3.1"><work><work-title>T</work-title></work>'
        '<part-list><score-part id="P1"><part-name>V</part-name></score-part></part-list>'
        f'<part id="P1"><measure number="1">{NOTE}{body}{NOTE}</measure></part></score-partwise>\n'
    )


def run(tmp_path: Path, xml: str, *args: str) -> tuple[str, ET.Element]:
    src, out = tmp_path / "in.xml", tmp_path / "out.xml"
    src.write_text(xml, encoding="utf-8")
    assert fx.main([str(src), str(out), *args]) == 0
    text = out.read_text(encoding="utf-8")
    return text, ET.fromstring(text.encode())


STRONG = ("Gm", "Dm", "C7")  # enough unambiguous chords to allow bare letters


@pytest.mark.parametrize(
    ("text", "root", "alter", "kind", "bass"),
    [
        ("C", "C", None, "major", None),
        ("c", "C", None, "major", None),
        ("c7", "C", None, "dominant", None),
        ("dm", "D", None, "minor", None),
        ("Dm", "D", None, "minor", None),
        ("f#m", "F", "1", "minor", None),
        ("bbmaj7", "B", "-1", "major-seventh", None),
        ("Bb", "B", "-1", "major", None),
        ("c/e", "C", None, "major", ("E", None)),
        ("G7/b", "G", None, "dominant", ("B", None)),
        ("Am7", "A", None, "minor-seventh", None),
        ("Cmaj7", "C", None, "major-seventh", None),
        ("CM7", "C", None, "major-seventh", None),
        ("Cdim", "C", None, "diminished", None),
        ("C0", "C", None, "diminished", None),
        ("C07", "C", None, "diminished-seventh", None),
        ("Caug", "C", None, "augmented", None),
        ("C+", "C", None, "augmented", None),
        ("Csus4", "C", None, "suspended-fourth", None),
        ("Dsus2", "D", None, "suspended-second", None),
        ("G6", "G", None, "major-sixth", None),
        ("Gm6", "G", None, "minor-sixth", None),
        ("D9", "D", None, "dominant-ninth", None),
        ("Gl3", "G", None, "dominant-13th", None),
        ("Gll", "G", None, "dominant-11th", None),
        ("Eb/Bb", "E", "-1", "major", ("B", "-1")),
    ],
)
def test_parse_table_and_harmony(tmp_path: Path, text: str, root: str, alter: str | None, kind: str, bass) -> None:
    _, tree = run(tmp_path, score(text, *STRONG))
    h = tree.find(".//harmony")
    assert h.findtext("root/root-step") == root
    assert h.findtext("root/root-alter") == alter
    assert h.findtext("kind") == kind
    if bass:
        assert (h.findtext("bass/bass-step"), h.findtext("bass/bass-alter")) == bass
    else:
        assert h.find("bass") is None


def test_kind_text_is_displayed_suffix(tmp_path: Path) -> None:
    _, tree = run(tmp_path, score("Cmaj7", *STRONG))
    assert tree.find(".//harmony/kind").get("text") == "maj7"


def test_add9_becomes_degree(tmp_path: Path) -> None:
    _, tree = run(tmp_path, score("Cadd9", *STRONG))
    h = tree.find(".//harmony")
    assert h.findtext("kind") == "major"
    assert h.findtext("degree/degree-value") == "9" and h.findtext("degree/degree-type") == "add"


@pytest.mark.parametrize("text", ["With spirit", "mf", "dim.", "Dm.", "rit.", "a tempo", "Coda", "Cb9x", "c vb", "7", "Dm hold", "tempo"])
def test_non_chords_untouched(tmp_path: Path, text: str) -> None:
    _, tree = run(tmp_path, score(text, *STRONG))
    assert [w.text for w in tree.iter("words")] == [text]
    assert len(tree.findall(".//harmony")) == 3


def test_unrecognised_reported(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    run(tmp_path, score("Dm.", "C13b9", *STRONG), "--report")
    out = capsys.readouterr().out
    assert "unrecognised 'Dm.'" in out and "unrecognised 'C13b9'" in out


def test_lone_a_is_reported_not_converted(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    _, tree = run(tmp_path, score("a", "Gm"), "--report")
    assert [w.text for w in tree.iter("words")] == ["a"]
    assert len(tree.findall(".//harmony")) == 1  # Gm converted
    assert "ambiguous    'a'" in capsys.readouterr().out


def test_bare_letters_converted_with_enough_evidence(tmp_path: Path) -> None:
    _, tree = run(tmp_path, score("a", "F", "am", *STRONG))
    assert [h.findtext("root/root-step") for h in tree.findall(".//harmony")] == ["A", "F", "A", "G", "D", "C"]
    assert not list(tree.iter("words"))


def test_existing_harmony_counts_as_evidence(tmp_path: Path) -> None:
    existing = "<harmony><root><root-step>C</root-step></root><kind>major</kind></harmony>" * 3
    _, tree = run(tmp_path, score("e", raw=existing))
    assert len(tree.findall(".//harmony")) == 4


def test_direction_with_other_content_is_skipped(tmp_path: Path) -> None:
    xml = score(*STRONG, raw="<direction><direction-type><words>c</words></direction-type><direction-type><dynamics><f/></dynamics></direction-type></direction>")
    xml = xml.replace("</measure>", "<direction><direction-type><words>Dm</words></direction-type><sound tempo='90'/></direction></measure>")
    _, tree = run(tmp_path, xml)
    assert sorted(w.text for w in tree.iter("words")) == ["Dm", "c"]


def test_offset_staff_placement_preserved_and_position(tmp_path: Path) -> None:
    d = '<direction placement="above"><direction-type><words default-x="5" default-y="30">c7</words></direction-type><offset>2</offset><staff>2</staff></direction>'
    _, tree = run(tmp_path, score(*STRONG, raw=d))
    h = tree.findall(".//harmony")[-1]
    assert h.get("placement") == "above" and h.get("default-y") == "30" and h.get("default-x") == "5"
    assert h.findtext("offset") == "2" and h.findtext("staff") == "2"
    tags = [c.tag for c in h]
    assert tags == ["root", "kind", "offset", "staff"]
    measure = tree.find(".//measure")
    assert [c.tag for c in measure] == ["note", "harmony", "harmony", "harmony", "harmony", "note"]


def test_capitalize_mode(tmp_path: Path) -> None:
    texts = ["dm", "c7", "bbmaj7", "f#m", "c/e", "C", "Gm"]
    text, tree = run(tmp_path, score(*texts), "--mode", "capitalize")
    assert [w.text for w in tree.iter("words")] == ["Dm", "C7", "Bbmaj7", "F#m", "C/E", "C", "Gm"]
    assert "<harmony" not in text


def test_capitalize_leaves_bare_a_alone(tmp_path: Path) -> None:
    _, tree = run(tmp_path, score("a", "dm"), "--mode", "capitalize")
    assert [w.text for w in tree.iter("words")] == ["a", "Dm"]


def test_header_preserved(tmp_path: Path) -> None:
    text, _ = run(tmp_path, score("c", *STRONG))
    assert text.startswith(HEADER)


def test_idempotent(tmp_path: Path) -> None:
    first, _ = run(tmp_path, score("c", "dm", *STRONG))
    (tmp_path / "again.xml").write_text(first, encoding="utf-8")
    assert fx.main([str(tmp_path / "again.xml"), str(tmp_path / "again-out.xml")]) == 0
    assert (tmp_path / "again-out.xml").read_text(encoding="utf-8") == first
    cap, _ = run(tmp_path, score("c", "dm"), "--mode", "capitalize")
    (tmp_path / "cap.xml").write_text(cap, encoding="utf-8")
    assert fx.main([str(tmp_path / "cap.xml"), str(tmp_path / "cap2.xml"), "--mode", "capitalize"]) == 0
    assert (tmp_path / "cap2.xml").read_text(encoding="utf-8") == cap


def test_notes_unchanged(tmp_path: Path) -> None:
    _, tree = run(tmp_path, score("c", "dm", *STRONG))
    notes = tree.findall(".//note")
    assert len(notes) == 2
    assert all(ET.tostring(n) == ET.tostring(ET.fromstring(NOTE)) for n in notes)


def test_comments_survive(tmp_path: Path) -> None:
    text, _ = run(tmp_path, score("c", *STRONG, raw="<!-- keep me -->"))
    assert "<!-- keep me -->" in text


def test_mxl_input(tmp_path: Path) -> None:
    mxl = tmp_path / "in.mxl"
    with zipfile.ZipFile(mxl, "w") as z:
        z.writestr("score.xml", score("c", *STRONG))
    out = tmp_path / "out.xml"
    assert fx.main([str(mxl), str(out)]) == 0
    assert out.read_text(encoding="utf-8").startswith(HEADER)
    assert "<harmony" in out.read_text(encoding="utf-8")


def test_unreadable_input_exit_2(tmp_path: Path) -> None:
    assert fx.main([str(tmp_path / "missing.xml"), str(tmp_path / "o.xml")]) == 2


def test_audit_clean_after_harmony(tmp_path: Path) -> None:
    src = tmp_path / "in.xml"
    src.write_text(score("c", "dm", "c7", "F", "G7"), encoding="utf-8")
    before = {f["code"] for f in audit.audit(audit.load(src))}
    assert {"chords-as-text", "chords-lowercase"} <= before
    _, tree = run(tmp_path, score("c", "dm", "c7", "F", "G7"))
    after = {f["code"] for f in audit.audit(tree)}
    assert not {"chords-as-text", "chords-lowercase"} & after
