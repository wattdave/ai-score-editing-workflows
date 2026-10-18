#!/usr/bin/env python3
"""Merge a treble part and a bass part into one two-staff part (a grand staff).

split_satb.py expects the choral reduction as ONE part with two staves. Sibelius
exports the same music as two single-staff parts, so only the first would be
split and the tenor and bass would come out as empty rests. Run this first.

Usage: merge_grand_staff.py in.xml out.xml
"""

from __future__ import annotations

import copy
import sys

from lxml import etree

NOTE_STAFF_BEFORE = ("beam", "notations", "lyric", "play", "footnote")


def add_staff(el: etree._Element, staff: int, voice_offset: int) -> None:
    voice = el.find("voice")
    if voice is not None:
        voice.text = str(int(voice.text) + voice_offset)
    if el.find("staff") is not None:
        el.find("staff").text = str(staff)
        return
    new = etree.Element("staff")
    new.text = str(staff)
    if el.tag == "note":
        for child in el:
            if child.tag in NOTE_STAFF_BEFORE:
                child.addprevious(new)
                return
        el.append(new)
    else:  # direction: staff follows voice, before sound
        anchor = el.find("sound")
        if anchor is not None:
            anchor.addprevious(new)
        else:
            el.append(new)


def fill_voices(measure: etree._Element) -> None:
    """Chord members without a <voice> belong to the voice of the note before."""
    current = "1"
    for note in measure.findall("note"):
        voice = note.find("voice")
        if voice is None:
            voice = etree.Element("voice")
            voice.text = current
            # schema order: duration, tie, instrument, footnote, level, voice
            before = [c for c in note if c.tag in ("duration", "tie", "cue", "instrument", "footnote", "level")]
            (before[-1] if before else note[-1]).addnext(voice)
        current = voice.text


def main(src: str, dst: str) -> None:
    tree = etree.parse(src)
    root = tree.getroot()
    parts = root.findall("part")
    if len(parts) != 2:
        raise SystemExit(f"expected 2 parts (treble, bass), found {len(parts)}")
    upper, lower = parts
    for m_up, m_lo in zip(upper.findall("measure"), lower.findall("measure")):
        fill_voices(m_up)
        fill_voices(m_lo)
        attrs = m_up.find("attributes")
        if attrs is not None:
            clef = attrs.find("clef")
            if clef is not None:
                clef.set("number", "1")
            lower_attrs = m_lo.find("attributes")
            lower_clef = lower_attrs.find("clef") if lower_attrs is not None else None
            if attrs.find("divisions") is not None:
                anchor = attrs.find("time")
                if anchor is None:
                    anchor = attrs.find("key")
                if anchor is None:
                    anchor = attrs.find("divisions")
                staves = etree.Element("staves")
                staves.text = "2"
                anchor.addnext(staves)
            if lower_clef is not None and clef is not None:
                lower_clef.set("number", "2")
                clef.addnext(lower_clef)
        barline = m_up.find("barline")
        if barline is not None:
            m_up.remove(barline)
        for el in m_up:
            if el.tag in ("note", "direction"):
                add_staff(el, 1, 0)
        cursor = 0  # where the upper staff ended, so the lower staff can start at the bar line
        for el in m_up:
            if el.tag == "note" and el.find("chord") is None and el.find("grace") is None:
                cursor += int(el.findtext("duration"))
            elif el.tag == "backup":
                cursor -= int(el.findtext("duration"))
            elif el.tag == "forward":
                cursor += int(el.findtext("duration"))
        if cursor:
            backup = etree.SubElement(m_up, "backup")
            etree.SubElement(backup, "duration").text = str(cursor)
        lower_barline = None
        for el in list(m_lo):
            if el.tag == "attributes":
                continue
            if el.tag == "barline":
                lower_barline = el
                continue
            moved = copy.deepcopy(el)
            if moved.tag in ("note", "direction"):
                add_staff(moved, 2, 4)
            m_up.append(moved)
        last = barline if barline is not None else lower_barline
        if last is not None:
            m_up.append(copy.deepcopy(last))
    root.remove(lower)
    plist = root.find("part-list")
    for sp in plist.findall("score-part"):
        if sp.get("id") == lower.get("id"):
            plist.remove(sp)
    tree.write(dst, xml_declaration=True, encoding="UTF-8")
    print(f"merged into one two-staff part: {dst}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    main(sys.argv[1], sys.argv[2])
