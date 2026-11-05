"""The SATB split must carry <beam> elements through to the four staves.

Several committed *- SATB.xml files from an earlier run had no beams at all; this
pins the current engine so beams scanned by OMR are not lost again.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from ai_score_editing.workflows.musicxml_split.profiles.satb import split_satb

XML = """<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="3.0">
  <part-list><score-part id="P1"><part-name>Piano</part-name></score-part></part-list>
  <part id="P1"><measure number="1">
    <attributes><divisions>2</divisions><time><beats>4</beats><beat-type>4</beat-type></time><staves>2</staves>
      <clef number="1"><sign>G</sign><line>2</line></clef><clef number="2"><sign>F</sign><line>4</line></clef></attributes>
    {s1v1}<backup><duration>8</duration></backup>
    {s1v2}<backup><duration>8</duration></backup>
    {s2v1}<backup><duration>8</duration></backup>
    {s2v2}
  </measure></part>
</score-partwise>
"""


def _bar(step: str, octave: int, staff: int, voice: int) -> str:
    def n(typ: str, dur: int, beam: str | None = None) -> str:
        b = f'<beam number="1">{beam}</beam>' if beam else ""
        return (f"<note><pitch><step>{step}</step><octave>{octave}</octave></pitch><duration>{dur}</duration>"
                f"<voice>{voice}</voice><type>{typ}</type><staff>{staff}</staff>{b}</note>")
    return n("eighth", 1, "begin") + n("eighth", 1, "end") + n("quarter", 2) + n("half", 4)


def test_split_keeps_every_beam(tmp_path: Path) -> None:
    src, dst = tmp_path / "in.xml", tmp_path / "out.xml"
    src.write_text(XML.format(s1v1=_bar("E", 5, 1, 1), s1v2=_bar("C", 5, 1, 2), s2v1=_bar("G", 3, 2, 1), s2v2=_bar("C", 3, 2, 2)))
    split_satb(src, dst)
    root = ET.parse(dst).getroot()
    parts = root.findall("part")
    assert len(parts) == 4
    for part in parts:
        values = [b.text for b in part.iter("beam")]
        assert values == ["begin", "end"], f"{part.get('id')} lost or changed its beam: {values}"
