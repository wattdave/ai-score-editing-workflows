"""Tests for the score-metadata-repair skill script."""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from helpers import ROOT, load_script

fix = load_script(ROOT / ".claude/skills/score-metadata-repair/scripts/fix_metadata.py", "fix_metadata")
audit = load_script(ROOT / ".claude/skills/score-engraving-audit/scripts/audit_musicxml.py", "audit_musicxml_for_fix")

HEADER = """<?xml version='1.0' encoding='utf-8'?>
<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 3.0 Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">
"""

BODY = """<score-partwise version="3.0">
  <work>
    <work-title> 1. SILENT NIGHT</work-title>
  </work>
  <identification>
    <encoding>
      <software>Halbestunde</software>
    </encoding>
  </identification>
  <part-list>
    <score-part id="P1">
      <part-name print-object="no">Voice0</part-name>
      <score-instrument id="P1-I1">
        <instrument-name>Voice0</instrument-name>
      </score-instrument>
      <midi-instrument id="P1-I1">
        <midi-channel>1</midi-channel>
      </midi-instrument>
    </score-part>
    <score-part id="P2">
      <part-name>Voice1</part-name>
    </score-part>
  </part-list>
  <part id="P1">
    <measure number="1">
      <attributes><divisions>1</divisions></attributes>
      <note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration><type>whole</type><lyric><syllabic>single</syllabic><text>Si</text></lyric></note>
    </measure>
  </part>
  <part id="P2">
    <measure number="1">
      <note><pitch><step>E</step><octave>4</octave></pitch><duration>4</duration><type>whole</type></note>
    </measure>
  </part>
</score-partwise>
"""


def run(tmp_path: Path, *args: str, header: str = HEADER, body: str = BODY, name: str = "in.xml") -> tuple[int, str, ET.Element]:
    src, dst = tmp_path / name, tmp_path / "out.xml"
    src.write_text(header + body, encoding="utf-8")
    rc = fix.main([str(src), str(dst), *args])
    text = dst.read_text(encoding="utf-8") if dst.exists() else ""
    return rc, text, (ET.fromstring(text[text.index("<score-partwise"):]) if text else None)


def parts_of(root: ET.Element) -> list[ET.Element]:
    return root.findall("part")


def notes_xml(root: ET.Element) -> str:
    return "".join(ET.tostring(p, encoding="unicode") for p in parts_of(root))


def test_rights_templates(tmp_path) -> None:
    rc, _, root = run(tmp_path, "--rights-template", "public-domain", "--source", "the 1818 Gruber edition")
    assert rc == 0 and root.findtext("identification/rights") == "Public domain. Transcribed from the 1818 Gruber edition for rehearsal use."
    rc, _, root = run(tmp_path, "--rights-template", "in-copyright", "--notice", "Copyright 1954 Carl Fischer, Inc.")
    assert root.findtext("identification/rights") == "Copyright 1954 Carl Fischer, Inc. Transcribed for rehearsal use only. Not for distribution."
    assert "©" not in root.findtext("identification/rights")
    rc, _, root = run(tmp_path, "--rights-template", "own-arrangement", "--year", "2026", "--name", "Walter")
    assert root.findtext("identification/rights") == "Arrangement © 2026 Walter."


@pytest.mark.parametrize(
    "args",
    [
        ("--rights-template", "public-domain"),
        ("--rights-template", "in-copyright"),
        ("--rights-template", "own-arrangement", "--year", "2026"),
        ("--rights-template", "own-arrangement", "--name", "Walter"),
    ],
)
def test_template_missing_inputs_is_an_error(tmp_path, args) -> None:
    rc, text, _ = run(tmp_path, *args)
    assert rc == 2 and text == ""


def test_never_invents_metadata(tmp_path) -> None:
    rc, _, root = run(tmp_path)
    assert rc == 0
    assert root.find("identification/rights") is None
    assert root.find("identification/creator") is None
    assert root.find("credit") is None
    assert root.findtext("work/work-title") == " 1. SILENT NIGHT"  # untouched without --normalize-title


@pytest.mark.parametrize(
    "raw, expected",
    [
        (" Silent Night", "Silent Night"),
        ("1. Caroling, Caroling", "Caroling, Caroling"),
        ("12) the first noel", "The First Noel"),
        ("DECK THE HALLS", "Deck the Halls"),
        ("deck the halls", "Deck the Halls"),
        ("IT'S THE MOST WONDERFUL TIME OF THE YEAR", "It's the Most Wonderful Time of the Year"),
        ("o come, o come, emmanuel", "O Come, O Come, Emmanuel"),
        ("Joy to the World", "Joy to the World"),
        ("the holly and the ivy", "The Holly and the Ivy"),
        ("what child is this?", "What Child Is This?"),
        ("Do You Hear What I Hear", "Do You Hear What I Hear"),
    ],
)
def test_title_normalization(raw: str, expected: str) -> None:
    assert fix.normalize_title(raw) == expected


def test_normalize_title_option_sets_work_and_movement_titles_and_credit(tmp_path) -> None:
    body = BODY.replace("<work>", "<movement-title> 1. SILENT NIGHT</movement-title>\n  <work>", 1)
    body = body.replace("<identification>", "<credit page=\"1\"><credit-words> 1. SILENT NIGHT</credit-words></credit>\n  <identification>", 1)
    # schema order does not matter for this check
    rc, _, root = run(tmp_path, "--normalize-title", body=body)
    assert rc == 0
    assert root.findtext("work/work-title") == "Silent Night"
    assert root.findtext("movement-title") == "Silent Night"
    assert root.find("credit/credit-words").text == "Silent Night"


def test_explicit_title_wins_and_creates_work_title(tmp_path) -> None:
    body = BODY.replace("<work>\n    <work-title> 1. SILENT NIGHT</work-title>\n  </work>\n  ", "")
    rc, _, root = run(tmp_path, "--title", "Stille Nacht", body=body)
    assert rc == 0 and root.findtext("work/work-title") == "Stille Nacht"
    assert list(root)[0].tag == "work"


def test_creators_and_credits_in_schema_order(tmp_path) -> None:
    rc, text, root = run(tmp_path, "--normalize-title", "--composer", "Franz Gruber", "--arranger", "W. Dunn", "--lyricist", "Joseph Mohr",
                         "--rights-template", "public-domain", "--source", "a scan")
    ident = root.find("identification")
    assert [c.tag for c in ident] == ["creator", "creator", "creator", "rights", "encoding"]
    assert {c.get("type"): c.text for c in ident.findall("creator")} == {"composer": "Franz Gruber", "arranger": "W. Dunn", "lyricist": "Joseph Mohr"}
    tags = [c.tag for c in root]
    assert tags == ["work", "identification", "credit", "credit", "credit", "credit", "part-list", "part", "part"]
    kinds = [c.findtext("credit-type") for c in root.findall("credit")]
    assert kinds == ["title", "lyricist", "composer", "arranger"]
    assert root.find("credit/credit-words").text == "Silent Night"
    assert "\n  <credit" in text and "\n    <credit-type>" in text  # tidy indentation


def test_credits_follow_defaults_and_are_not_duplicated(tmp_path) -> None:
    body = BODY.replace("<part-list>", "<defaults><page-layout><page-height>1000</page-height><page-width>800</page-width></page-layout></defaults>\n  <part-list>", 1)
    rc, _, root = run(tmp_path, "--composer", "A. Composer", "--normalize-title", body=body)
    tags = [c.tag for c in root]
    assert tags.index("defaults") < tags.index("credit") < tags.index("part-list")
    assert root.find("credit/credit-words").get("default-x") == "400"
    # a second run adds nothing more
    out = tmp_path / "out.xml"
    out2 = tmp_path / "out2.xml"
    fix.main([str(out), str(out2), "--composer", "A. Composer", "--normalize-title"])
    assert len(ET.parse(out2).getroot().findall("credit")) == len(root.findall("credit"))


def test_parts_names_abbreviations_and_instruments(tmp_path) -> None:
    rc, _, root = run(tmp_path, "--parts", "Soprano,Alto")
    sp1, sp2 = root.findall("part-list/score-part")
    assert sp1.findtext("part-name") == "Soprano" and sp1.findtext("part-abbreviation") == "S."
    assert "print-object" not in sp1.find("part-name").attrib
    assert sp2.findtext("part-name") == "Alto" and sp2.findtext("part-abbreviation") == "A."
    assert [c.tag for c in sp1] == ["part-name", "part-abbreviation", "score-instrument", "midi-instrument"]
    assert sp1.findtext("score-instrument/instrument-name") == "Soprano"


@pytest.mark.parametrize(
    "name, abbrev",
    [("Soprano", "S."), ("Alto", "A."), ("Tenor", "T."), ("Bass", "B."), ("Piano", "Pno."), ("Treble", "Tr."), ("Soprano 1", "S. 1"), ("Baritone", "Bar."), ("Vln", "Vln.")],
)
def test_abbreviations(name: str, abbrev: str) -> None:
    assert fix.abbreviate(name) == abbrev


def test_missing_abbreviation_filled_for_real_names_only(tmp_path) -> None:
    body = BODY.replace("Voice1", "Tenor")
    rc, _, root = run(tmp_path, body=body)
    sp1, sp2 = root.findall("part-list/score-part")
    assert sp1.find("part-abbreviation") is None  # generic name: nothing invented
    assert sp2.findtext("part-abbreviation") == "T."


def test_too_many_part_names_is_an_error(tmp_path) -> None:
    rc, text, _ = run(tmp_path, "--parts", "Soprano,Alto,Tenor")
    assert rc == 2


def test_header_preserved_and_note_content_unchanged(tmp_path) -> None:
    rc, text, root = run(tmp_path, "--normalize-title", "--composer", "X", "--parts", "Soprano,Alto",
                         "--rights-template", "own-arrangement", "--year", "2026", "--name", "Walter")
    assert text.startswith(HEADER)  # declaration and DOCTYPE byte for byte
    before = ET.fromstring(BODY)
    assert notes_xml(root) == notes_xml(before)
    # raw text of the parts is identical too
    assert text[text.index("<part id"):] .strip() == BODY[BODY.index("<part id"):].strip()


def test_missing_header_gets_declaration(tmp_path) -> None:
    rc, text, _ = run(tmp_path, "--normalize-title", header="")
    assert text.startswith('<?xml version="1.0" encoding="UTF-8"?>\n<score-partwise')


def test_idempotent(tmp_path) -> None:
    args = ["--normalize-title", "--composer", "Franz Gruber", "--parts", "Soprano,Alto", "--rights-template", "public-domain", "--source", "a scan"]
    rc, once, _ = run(tmp_path, *args)
    src, dst = tmp_path / "out.xml", tmp_path / "again.xml"
    fix.main([str(src), str(dst), *args])
    assert dst.read_text(encoding="utf-8") == once


def test_reads_mxl(tmp_path) -> None:
    mxl = tmp_path / "in.mxl"
    with zipfile.ZipFile(mxl, "w") as z:
        z.writestr("META-INF/container.xml", "<container/>")
        z.writestr("score.xml", HEADER + BODY)
    out = tmp_path / "out.xml"
    assert fix.main([str(mxl), str(out), "--normalize-title"]) == 0
    assert "<work-title>Silent Night</work-title>" in out.read_text(encoding="utf-8")


def test_unreadable_input_exits_2(tmp_path) -> None:
    assert fix.main([str(tmp_path / "nope.xml"), str(tmp_path / "o.xml")]) == 2


def test_audit_no_longer_reports_fixed_metadata(tmp_path) -> None:
    src = tmp_path / "in.xml"
    src.write_text(HEADER + BODY, encoding="utf-8")
    before = {f["code"] for f in audit.audit(audit.load(src))}
    assert {"title-case", "title-whitespace", "title-numbered", "rights-missing", "part-name-generic", "composer-missing"} <= before
    out = tmp_path / "out.xml"
    assert fix.main([str(src), str(out), "--normalize-title", "--composer", "Franz Gruber", "--parts", "Soprano,Alto",
                     "--rights-template", "public-domain", "--source", "a scan"]) == 0
    after = {f["code"] for f in audit.audit(audit.load(out))}
    assert not [c for c in after if c.startswith("title-") or c in {"rights-missing", "part-name-generic", "part-abbreviation-missing", "composer-missing"}]


def test_output_is_well_formed_for_all_options(tmp_path) -> None:
    rc, text, root = run(tmp_path, "--title", "Stille Nacht", "--arranger", "A", "--parts", "Soprano")
    assert rc == 0 and re.search(r"<part-name>Soprano</part-name>", text)


def test_voice_letter_names_abbreviate_to_themselves() -> None:
    for name in ("S A", "T B", "S", "A & B", "SATB"):
        assert fix.abbreviate(name) == name
    assert fix.abbreviate("Baritone") == "Bar."
    assert fix.abbreviate("Soprano") == "S."


def test_subtitle_is_written_as_a_credit(tmp_path) -> None:
    src, dst = tmp_path / "in.xml", tmp_path / "out.xml"
    src.write_text('<?xml version="1.0"?>\n<score-partwise version="3.0"><work><work-title>x</work-title></work>'
                   '<part-list><score-part id="P1"><part-name>S</part-name></score-part></part-list>'
                   '<part id="P1"><measure number="1"/></part></score-partwise>\n')
    assert fix.main([str(src), str(dst), "--title", "Silent Night", "--subtitle", "(Stille Nacht)"]) == 0
    root = ET.parse(dst).getroot()
    kinds = {c.findtext("credit-type"): c.findtext("credit-words") for c in root.findall("credit")}
    assert kinds["title"] == "Silent Night" and kinds["subtitle"] == "(Stille Nacht)"


# Credits copied from the Nelson Carol Book reader output (SingWeNoel, Chlausezauerli,
# PartingGlass_2010, EsIstEinRos_Combined, LetUnionBe): one <credit> per printed line.
def _cred(ctype: str | None, text: str, x: float, y: float, just: str, size: int = 12, page: int = 1, valign: str = "top") -> str:
    t = f"<credit-type>{ctype}</credit-type>" if ctype else ""
    return (f'  <credit page="{page}">{t}<credit-words default-x="{x:g}" default-y="{y:g}" justify="{just}" '
            f'valign="{valign}" font-size="{size}">{text}</credit-words></credit>\n')


NELSON_CREDITS = (
    _cred("title", "Sing We Noël", 616.5, 1500, "center", 24)
    + _cred("subtitle", "(Yodeling song for Silvesternacht)", 616.5, 1465, "center", 14)
    + _cred("lyricist", "Susan Cooper for the Christmas Revels", 80, 1450, "left")
    + _cred("composer", "anon. 16th century French", 1153, 1450, "right")
    + _cred("arranger", "arr. Thomas Lindemuth 1998", 1153, 1430, "right")
    + _cred("rights", "Transcription Copyright © 2009 California Revels, Inc.", 616.5, 60, "center", 9, valign="bottom")
    + _cred(None, "2.  Old King Solomon in all his glory,", 230, 1000, "left", 11, page=2)
    + _cred(None, "Told each wife a different story", 230, 974, "left", 11, page=2)
    + _cred(None, "3.  Come on lads and raise your glasses", 230, 870, "left", 11, page=2)
    + _cred(None, "Grab the bottle as it passes;", 230, 844, "left", 11, page=2)
)


def _credit_score(credits: str) -> str:
    return ('<score-partwise version="3.0">\n  <work><work-title>Sing We Noël</work-title></work>\n'
            + credits + '  <part-list><score-part id="P1"><part-name>Soprano</part-name>'
            '<part-abbreviation>S.</part-abbreviation></score-part></part-list>\n'
            '  <part id="P1"><measure number="1"/></part>\n</score-partwise>\n')


def _credits(root: ET.Element) -> list[tuple[list[str], str, str, str]]:
    return [([t.text for t in c.findall("credit-type")], c.findtext("credit-words"),
             c.find("credit-words").get("default-x"), c.find("credit-words").get("default-y"))
            for c in root.findall("credit")]


def test_merge_credits_joins_stacked_lines_of_one_block(tmp_path) -> None:
    rc, text, root = run(tmp_path, "--merge-credits", body=_credit_score(NELSON_CREDITS))
    assert rc == 0
    got = _credits(root)
    assert (["composer", "arranger"], "anon. 16th century French\narr. Thomas Lindemuth 1998", "1153", "1450") in got
    # Verses on page 2: each stanza becomes one block; the wider stanza gap keeps them apart.
    assert ([], "2.  Old King Solomon in all his glory,\nTold each wife a different story", "230", "1000") in got
    assert ([], "3.  Come on lads and raise your glasses\nGrab the bottle as it passes;", "230", "870") in got
    # Title, subtitle, the left lyricist and the footer are untouched.
    for kind, words in [("title", "Sing We Noël"), ("subtitle", "(Yodeling song for Silvesternacht)"),
                        ("lyricist", "Susan Cooper for the Christmas Revels"),
                        ("rights", "Transcription Copyright © 2009 California Revels, Inc.")]:
        assert any(t == [kind] and w == words for t, w, _, _ in got)
    assert len(got) == 7


def test_merge_credits_reports_and_is_idempotent(tmp_path, capsys) -> None:
    rc, text, _ = run(tmp_path, "--merge-credits", body=_credit_score(NELSON_CREDITS))
    out = capsys.readouterr().out
    assert "credits merged (composer/arranger, page 1, right): anon. 16th century French | arr. Thomas Lindemuth 1998" in out
    assert out.count("credits merged") == 3
    again = tmp_path / "again.xml"
    assert fix.main([str(tmp_path / "out.xml"), str(again), "--merge-credits"]) == 0
    assert "nothing to change" in capsys.readouterr().out
    assert again.read_text(encoding="utf-8") == text


def test_merge_credits_is_conservative(tmp_path) -> None:
    credits = (
        _cred("title", "The Parting", 616.5, 1500, "center", 14)
        + _cred("title", "Glass", 616.5, 1480, "center", 14)  # two title lines: never merged
        + _cred("composer", "Traditional Irish", 80, 1450, "left")
        + _cred("arranger", "Arranged by Jerome Epstein", 1153, 1450, "right")  # other alignment
        + _cred("arranger", "far below", 1153, 1300, "right")  # too far apart
        + _cred("composer", "different font", 1153, 1280, "right", 10)
        + _cred("rights", "score revision 002", 1153, 1262, "right", 10)  # creator vs rights text
    )
    rc, text, root = run(tmp_path, "--merge-credits", body=_credit_score(credits))
    assert rc == 0 and len(root.findall("credit")) == 7
    assert all("\n" not in (w or "") for _, w, _, _ in _credits(root))


def test_merge_credits_off_by_default_and_audit_flags_split(tmp_path) -> None:
    body = _credit_score(NELSON_CREDITS)
    rc, text, root = run(tmp_path, body=body)
    assert len(root.findall("credit")) == 10
    split = [f for f in audit.audit(root) if f["code"] == "credits-split"]
    assert split and split[0]["severity"] == "warn" and "3 credit block(s)" in split[0]["message"]
    rc, text, root = run(tmp_path, "--merge-credits", body=body)
    assert not [f for f in audit.audit(root) if f["code"] == "credits-split"]
