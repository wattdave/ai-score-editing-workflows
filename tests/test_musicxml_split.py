"""Regression coverage for the shared onset-based splitting core."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from sibelius_websocket_cli.musicxml_split.io import parse_musicxml
from sibelius_websocket_cli.musicxml_split.profiles.satb import split_satb
from sibelius_websocket_cli.musicxml_split.timeline import timeline_for_measure


def _note(step: str, duration: int, *, chord: bool = False, staff: str = "1", voice: str = "1", grace: bool = False) -> ET.Element:
    note = ET.Element("note")
    if grace:
        ET.SubElement(note, "grace")
    if chord:
        ET.SubElement(note, "chord")
    pitch = ET.SubElement(note, "pitch")
    ET.SubElement(pitch, "step").text = step
    ET.SubElement(pitch, "octave").text = "4"
    if not grace:
        ET.SubElement(note, "duration").text = str(duration)
    ET.SubElement(note, "voice").text = voice
    ET.SubElement(note, "staff").text = staff
    return note


def test_timeline_honors_chords_backup_forward_and_grace() -> None:
    measure = ET.Element("measure", number="7")
    measure.append(_note("C", 4))
    measure.append(_note("E", 4, chord=True))
    backup = ET.SubElement(measure, "backup"); ET.SubElement(backup, "duration").text = "4"
    measure.append(_note("G", 2, staff="2", voice="2"))
    forward = ET.SubElement(measure, "forward"); ET.SubElement(forward, "duration").text = "2"
    measure.append(_note("A", 0, grace=True, staff="2", voice="2"))
    issues = []
    timeline = timeline_for_measure(measure, "P1", 4, issues)
    assert [(event.onset, event.duration, len(event.notes)) for event in timeline.events] == [(0, 4, 2), (0, 2, 1), (4, 0, 1)]
    assert issues == []


def test_satb_profile_routes_chord_lyrics_and_preserves_measure_duration(tmp_path: Path) -> None:
    root = ET.Element("score-partwise")
    ET.SubElement(root, "part-list")
    part = ET.SubElement(root, "part", id="P1")
    measure = ET.SubElement(part, "measure", number="1")
    attrs = ET.SubElement(measure, "attributes")
    ET.SubElement(attrs, "divisions").text = "1"
    time = ET.SubElement(attrs, "time")
    ET.SubElement(time, "beats").text = "4"; ET.SubElement(time, "beat-type").text = "4"
    alto = _note("C", 4)
    lyric = ET.SubElement(alto, "lyric"); ET.SubElement(lyric, "text").text = "Kyrie"
    measure.append(alto)
    measure.append(_note("G", 4, chord=True))
    backup = ET.SubElement(measure, "backup"); ET.SubElement(backup, "duration").text = "4"
    measure.append(_note("D", 4, staff="2"))
    measure.append(_note("A", 4, chord=True, staff="2"))
    source = tmp_path / "source.xml"; output = tmp_path / "satb.mxl"
    ET.ElementTree(root).write(source, encoding="utf-8", xml_declaration=True)
    result = split_satb(source, output)
    assert result.parts == ["P1", "P2", "P3", "P4"]
    _, split = parse_musicxml(output)
    assert split.find("part[@id='P1']/measure/note/lyric/text").text == "Kyrie"
    assert all(sum(int(note.findtext("duration") or "0") for note in part.find("measure").findall("note")) == 4 for part in split.findall("part"))
