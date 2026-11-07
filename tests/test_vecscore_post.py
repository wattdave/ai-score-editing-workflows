"""Tests for the vector-pdf-score writer helpers (metronome, lyric rows, footers, MusicXML patches)."""

import json

import pytest
from helpers import ROOT, load_script

post = load_script(ROOT / ".claude/skills/vector-pdf-score/scripts/vecscore_post.py", "vecscore_post")

XML = ('<?xml version="1.0"?><score-partwise version="3.0"><part-list>'
       '<score-part id="P1"><part-name>S</part-name></score-part><score-part id="P2"><part-name>B</part-name></score-part></part-list>'
       + ''.join(f'<part id="P{p}">' + ''.join(
           f'<measure number="{m}"><note><pitch><step>C</step><octave>4</octave></pitch><duration>8</duration><voice>1</voice><type>half</type></note>'
           f'<note><pitch><step>D</step><octave>4</octave></pitch><duration>8</duration><voice>1</voice><type>half</type>'
           f'<lyric number="1"><syllabic>single</syllabic><text>la</text></lyric></note></measure>' for m in (1, 2)) + '</part>' for p in (1, 2))
       + '</score-partwise>')


def test_metronome_units_and_quarter_tempo() -> None:
    assert post.parse_metronome("dotted-quarter=60") == ("quarter", 1, "60", "90")
    assert post.parse_metronome("half=86") == ("half", 0, "86", "172")
    assert post.parse_metronome("quarter.=52")[3] == "78"
    with pytest.raises(ValueError):
        post.parse_metronome("q=60")
    x = post.metronome_xml("dotted-quarter=60", "Langsam")
    assert "<beat-unit-dot/>" in x and 'tempo="90"' in x and "Langsam" in x


def test_skip_words_json_allows_commas(tmp_path) -> None:
    f = tmp_path / "skip.json"
    f.write_text(json.dumps(["Revels,", "Inc."]))
    assert post.load_skip_words(str(f), ["TENOR"]) == {"Revels,", "Inc.", "TENOR"}
    assert post.load_skip_words("p,mf") == {"p", "mf"}


def test_footer_and_copyright_lines() -> None:
    w = [(0, 700, 10, 710, "Copyright", 5, 0, 0), (12, 700, 20, 710, "©", 5, 0, 1), (22, 700, 40, 710, "2006", 5, 0, 2),
         (0, 720, 10, 730, "score", 6, 0, 0), (12, 720, 30, 730, "revision", 6, 0, 1),
         (0, 200, 10, 210, "Si-", 1, 0, 0)]
    assert post.footer_lines(w) == {(5, 0), (6, 0)}
    assert post.copyright_text(w) == "Copyright © 2006"
    assert post.copyright_text(w[-1:]) == ""


def test_keep_rows_follows_rows_and_stops_at_a_gap() -> None:
    # staff bottom 100: rows at 112, 124, 136 (three verses) then a footer at 200
    assert post.keep_rows([112, 124, 136, 200], 100, 1e9) == [112, 124, 136]
    assert post.keep_rows([112, 124, 136], 100, 130) == [112, 124]   # next staff top
    assert post.keep_rows([160], 100, 1e9) == []                      # first row too far


def test_breaks_barline_abbreviations() -> None:
    x = post.breaks(XML, [2])
    assert x.count('<measure number="2"><print new-system="yes"/>') == 2
    x = post.final_barline(x)
    assert x.count('light-heavy') == 2
    x = post.abbreviations(x, ["S.", ""])
    assert "<part-name>S</part-name><part-abbreviation>S.</part-abbreviation>" in x and x.count("part-abbreviation>") == 2


def test_patch_fermata_slur_rehearsal_volta() -> None:
    x = post.apply_patch(XML, [
        {"type": "fermata", "measure": 2, "part": 2, "beat": 3},
        {"type": "slur", "measure": 1, "from": 1, "to": 3},
        {"type": "rehearsal", "measure": 2, "text": "A"},
        {"type": "barline", "measure": 1, "style": "repeat-start"},
        {"type": "volta", "number": 1, "measure": 2},
    ])
    p1, p2 = x.split('<part id="P2">')
    assert '<slur type="start" number="1"/>' in p1 and '<slur type="stop" number="1"/></notations><lyric' in p1
    assert p2.count("<fermata") == 1 and "<rehearsal" not in p2 and "<rehearsal" in p1
    assert x.count('<repeat direction="forward"/>') == 2 and x.count('<ending number="1" type="stop"/>') == 2
    with pytest.raises(ValueError):
        post.apply_patch(XML, [{"type": "fermata", "measure": 1, "beat": 2}])
