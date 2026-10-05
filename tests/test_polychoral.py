"""Unit tests for polychoral and 16-voice demixing engine."""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from ai_score_editing.polychoral import (
    build_16voice_part_list,
    clean_note,
    demix_16voices,
    demix_reduction_staff,
    demix_single_staff,
    get_chord_clusters,
    get_midi,
    heal_ties,
    make_rest,
    pad_or_trim_duration,
    validate_16voices,
)


def _make_note(
    step: str,
    octave: int,
    dur: int = 256,
    alter: float = 0,
    voice: str = "1",
    chord: bool = False,
    lyric: str | None = None,
    tie_start: bool = False,
    tie_stop: bool = False,
) -> ET.Element:
    n = ET.Element("note")
    if chord:
        ET.SubElement(n, "chord")
    p = ET.SubElement(n, "pitch")
    ET.SubElement(p, "step").text = step
    ET.SubElement(p, "octave").text = str(octave)
    if alter != 0:
        ET.SubElement(p, "alter").text = str(alter)
    d = ET.SubElement(n, "duration")
    d.text = str(dur)
    v = ET.SubElement(n, "voice")
    v.text = voice
    if lyric is not None:
        lyr = ET.SubElement(n, "lyric")
        ET.SubElement(lyr, "text").text = lyric
    if tie_start:
        ET.SubElement(n, "tie", type="start")
        notations = ET.SubElement(n, "notations")
        ET.SubElement(notations, "tied", type="start")
    if tie_stop:
        ET.SubElement(n, "tie", type="stop")
        notations = n.find("notations")
        if notations is None:
            notations = ET.SubElement(n, "notations")
        ET.SubElement(notations, "tied", type="stop")
    return n


def _make_rest(dur: int, voice: str = "1") -> ET.Element:
    n = ET.Element("note")
    ET.SubElement(n, "rest")
    d = ET.SubElement(n, "duration")
    d.text = str(dur)
    v = ET.SubElement(n, "voice")
    v.text = voice
    return n


def test_get_midi() -> None:
    c4 = _make_note("C", 4)
    assert get_midi(c4) == 60

    a4 = _make_note("A", 4)
    assert get_midi(a4) == 69

    eb5 = _make_note("E", 5, alter=-1)
    assert get_midi(eb5) == 75

    fs3 = _make_note("F", 3, alter=1)
    assert get_midi(fs3) == 54

    rest = _make_rest(256)
    assert get_midi(rest) == -1


def test_midi_accepts_decimal_alter() -> None:
    """Some exports write <alter>-1.0</alter>; alter is a decimal in MusicXML."""
    from ai_score_editing.musicxml_split.routing import midi

    for note, expected in ((_make_note("B", 4, alter=-1.0), 70), (_make_note("C", 4, alter=2.0), 62)):
        assert note.findtext("pitch/alter") in {"-1.0", "2.0"}
        assert get_midi(note) == expected
        assert midi(note) == expected
    # A quarter-tone alter rounds to the nearest semitone.
    assert get_midi(_make_note("D", 4, alter=0.5)) in {62, 63}


def test_clean_note() -> None:
    n = _make_note("D", 4, dur=128, voice="2", chord=True)
    ET.SubElement(n, "staff").text = "2"
    ET.SubElement(n, "stem").text = "up"

    cleaned = clean_note(n, base_dur="256", voice="1")
    assert cleaned.find("chord") is None
    assert cleaned.find("staff") is None
    assert cleaned.find("stem") is None
    assert cleaned.find("voice").text == "1"
    assert cleaned.find("duration").text == "256"


def test_clean_note_grace() -> None:
    n = _make_note("F", 3, dur=128)
    cleaned = clean_note(n, is_grace=True)
    assert cleaned.find("grace") is not None
    assert cleaned.find("duration") is None


def test_make_rest() -> None:
    r = make_rest(1024, voice="1")
    assert r.find("rest") is not None
    assert r.find("rest").attrib.get("measure") == "yes"
    assert r.find("duration").text == "1024"
    assert r.find("voice").text == "1"


def test_get_chord_clusters_and_lyrics() -> None:
    base = _make_note("A", 4, dur=256, lyric="test")
    top = _make_note("D", 5, dur=256, chord=True)
    notes = [base, top]

    clusters = get_chord_clusters(notes)
    assert len(clusters) == 1
    assert len(clusters[0]) == 2
    # Check that lyric was copied to top note
    assert top.find("lyric") is not None
    assert top.find("lyric").find("text").text == "test"


def test_pad_or_trim_duration() -> None:
    # 1. Exact duration
    n1 = _make_note("C", 4, dur=512)
    n2 = _make_note("D", 4, dur=512)
    res = pad_or_trim_duration([n1, n2], 1024)
    assert len(res) == 2

    # 2. Deficit duration: padded with rest
    res_pad = pad_or_trim_duration([n1], 1024)
    assert len(res_pad) == 2
    assert res_pad[1].find("rest") is not None
    assert res_pad[1].find("duration").text == "512"

    # 3. Slight overflow trimmed
    n_long = _make_note("E", 4, dur=1100)
    res_trim = pad_or_trim_duration([n_long], 1024)
    assert len(res_trim) == 1
    assert res_trim[0].find("duration").text == "1024"


def test_demix_single_staff_polyphonic() -> None:
    v1 = _make_note("G", 4, dur=512, voice="1")
    v2 = _make_note("C", 4, dur=512, voice="2")
    notes = [v1, v2]

    p1, p2 = demix_single_staff(notes, 512)
    assert len(p1) == 1
    assert len(p2) == 1
    assert get_midi(p1[0]) == 67  # G4
    assert get_midi(p2[0]) == 60  # C4


def test_demix_single_staff_homophonic_chord() -> None:
    base = _make_note("C", 4, dur=512)
    top = _make_note("E", 4, dur=512, chord=True)
    notes = [base, top]

    p1, p2 = demix_single_staff(notes, 512)
    assert len(p1) == 1
    assert len(p2) == 1
    assert get_midi(p1[0]) == 64  # E4 (top)
    assert get_midi(p2[0]) == 60  # C4 (bottom)


def test_demix_single_staff_unison() -> None:
    n = _make_note("A", 4, dur=512)
    p1, p2 = demix_single_staff([n], 512)
    assert len(p1) == 1
    assert len(p2) == 1
    assert get_midi(p1[0]) == 69
    assert get_midi(p2[0]) == 69


def test_demix_reduction_staff_4part_cluster() -> None:
    c = _make_note("A", 4, dur=512)
    c1 = _make_note("C", 5, dur=512, chord=True)
    c2 = _make_note("E", 5, dur=512, chord=True)
    c3 = _make_note("A", 5, dur=512, chord=True)
    notes = [c, c1, c2, c3]

    s1, s2, a1, a2 = demix_reduction_staff(notes, 512)
    assert get_midi(s1[0]) == 81  # A5 (highest)
    assert get_midi(s2[0]) == 76  # E5
    assert get_midi(a1[0]) == 72  # C5
    assert get_midi(a2[0]) == 69  # A4 (lowest)


def test_heal_ties() -> None:
    root = ET.Element("score-partwise")
    p = ET.SubElement(root, "part", id="P1")
    m1 = ET.SubElement(p, "measure", number="1")
    n1 = _make_note("G", 4, dur=512, tie_start=True)
    m1.append(n1)

    m2 = ET.SubElement(p, "measure", number="2")
    n2 = _make_note("G", 4, dur=512)  # missing stop
    n3 = _make_note("A", 4, dur=256, tie_start=True)  # followed by mismatched pitch
    n4 = _make_note("B", 4, dur=256)
    m2.append(n2)
    m2.append(n3)
    m2.append(n4)

    stops_added, dangling_removed = heal_ties(root)
    assert stops_added == 1
    assert dangling_removed == 1

    # Verify n2 now has stop tie
    assert any(t.attrib.get("type") == "stop" for t in n2.findall("tie"))
    # Verify n3 no longer has start tie
    assert not any(t.attrib.get("type") == "start" for t in n3.findall("tie"))


def test_build_16voice_part_list() -> None:
    plist = build_16voice_part_list()
    parts = plist.findall("score-part")
    assert len(parts) == 16

    # Verify Choir 1 Tenor 1 has octave treble clef meta
    c1_t1 = plist.find(".//score-part[@id='C1_T1']")
    assert c1_t1 is not None
    assert c1_t1.find("part-name").text == "Choir 1 Tenor 1"

    # Verify MIDI channels are 1 through 16
    channels = [sp.find(".//midi-channel").text for sp in parts]
    assert channels == [str(i) for i in range(1, 17)]


def test_end_to_end_synthetic_score(tmp_path: Path) -> None:
    """Create a mini 12-staff score (2 measures) and demix to 16 voices."""
    root = ET.Element("score-partwise")
    plist = ET.SubElement(root, "part-list")

    part_ids = [f"P{i}" for i in range(1, 9)] + ["P9", "P11"]
    for pid in part_ids:
        sp = ET.SubElement(plist, "score-part", id=pid)
        ET.SubElement(sp, "part-name").text = pid

    parts_dict = {}
    for pid in part_ids:
        p = ET.SubElement(root, "part", id=pid)
        parts_dict[pid] = p

    # Measure 1: Open score layout (P1-P8 have notes, P9 & P11 rest)
    for pid in ["P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8"]:
        m = ET.SubElement(parts_dict[pid], "measure", number="1")
        attrs = ET.SubElement(m, "attributes")
        ET.SubElement(attrs, "divisions").text = "256"
        time = ET.SubElement(attrs, "time")
        ET.SubElement(time, "beats").text = "4"
        ET.SubElement(time, "beat-type").text = "4"
        # 2-note chord
        base = _make_note("C", 4, dur=1024, lyric="Gloria")
        top = _make_note("E", 4, dur=1024, chord=True)
        m.append(base)
        m.append(top)

    for pid in ["P9", "P11"]:
        m = ET.SubElement(parts_dict[pid], "measure", number="1")
        attrs = ET.SubElement(m, "attributes")
        ET.SubElement(attrs, "divisions").text = "256"
        m.append(_make_rest(1024))

    # Measure 2: Short score layout (P9 and P11 have notes, P1-P8 rest)
    for pid in ["P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8"]:
        m = ET.SubElement(parts_dict[pid], "measure", number="2")
        m.append(_make_rest(1024))

    for pid in ["P9", "P11"]:
        m = ET.SubElement(parts_dict[pid], "measure", number="2")
        # staff 1: 4-note chord
        c = _make_note("A", 4, dur=1024)
        ET.SubElement(c, "staff").text = "1"
        c1 = _make_note("C", 5, dur=1024, chord=True)
        ET.SubElement(c1, "staff").text = "1"
        c2 = _make_note("E", 5, dur=1024, chord=True)
        ET.SubElement(c2, "staff").text = "1"
        c3 = _make_note("A", 5, dur=1024, chord=True)
        ET.SubElement(c3, "staff").text = "1"
        m.append(c)
        m.append(c1)
        m.append(c2)
        m.append(c3)
        # staff 2: 4-note chord
        b = _make_note("A", 2, dur=1024)
        ET.SubElement(b, "staff").text = "2"
        b1 = _make_note("C", 3, dur=1024, chord=True)
        ET.SubElement(b1, "staff").text = "2"
        b2 = _make_note("E", 3, dur=1024, chord=True)
        ET.SubElement(b2, "staff").text = "2"
        b3 = _make_note("A", 3, dur=1024, chord=True)
        ET.SubElement(b3, "staff").text = "2"
        m.append(b)
        m.append(b1)
        m.append(b2)
        m.append(b3)

    in_file = tmp_path / "synthetic_input.musicxml"
    out_file = tmp_path / "synthetic_16voices.mxl"

    tree = ET.ElementTree(root)
    tree.write(in_file, encoding="utf-8", xml_declaration=True)

    res = demix_16voices(in_file, out_file)
    assert res["partsCount"] == 16
    assert res["totalMeasures"] == 2

    issues = validate_16voices(out_file)
    assert issues == []


def test_real_12pp_export_if_available(tmp_path: Path) -> None:
    """Demix a real export kept outside the repo (the score is copyrighted).

    Set SIBWS_12PP_EXPORT to its path to run this; the synthetic tests above
    cover the same code paths everywhere else.
    """
    source = os.environ.get("SIBWS_12PP_EXPORT")
    if not source:
        pytest.skip("set SIBWS_12PP_EXPORT to a real 12pp MusicXML export to run")
    p = Path(source).expanduser()
    if not p.exists():
        pytest.fail(f"SIBWS_12PP_EXPORT points at a missing file: {p}")

    out_p = tmp_path / "real_16voices.mxl"
    res = demix_16voices(p, out_p)
    source_part = ET.parse(p).getroot().find("part")
    assert source_part is not None
    assert res["totalMeasures"] == len(source_part.findall("measure"))
    assert res["partsCount"] == 16

    from ai_score_editing.musicxml_split.validation import validate_file

    issues = validate_file(out_p, expected_parts=16)
    # Real exports have overflowed source measures. The engine keeps their
    # durations and reports the condition for a caller to resolve.
    assert any(issue.code in {"measure-overflow", "target-overflow"} for issue in issues)


def _measure(part: ET.Element, number: str, *children: ET.Element, first: bool = False) -> ET.Element:
    m = ET.SubElement(part, "measure", number=number)
    if first:
        attrs = ET.SubElement(m, "attributes")
        ET.SubElement(attrs, "divisions").text = "256"
        time = ET.SubElement(attrs, "time")
        ET.SubElement(time, "beats").text = "4"
        ET.SubElement(time, "beat-type").text = "4"
    m.extend(children)
    return m


def _el(tag: str, text: str | None = None, **attrib: str) -> ET.Element:
    e = ET.Element(tag, attrib)
    e.text = text
    return e


def _on_staff(note: ET.Element, staff: str) -> ET.Element:
    ET.SubElement(note, "staff").text = staff
    return note


def _backup(dur: int) -> ET.Element:
    b = ET.Element("backup")
    ET.SubElement(b, "duration").text = str(dur)
    return b


def _raw_export_features(path: Path) -> None:
    """A 2-measure, 10-part score with the features a raw OMR export has.

    Each feature mirrors code only the real 12pp export used to reach: XML
    voices sharing a staff (open and short score), <backup>, a part that
    stops mid-measure, an overflowing measure, staff-bound directions and
    barlines, extra top-level elements, and ties with a missing end.
    """
    root = ET.Element("score-partwise")
    work = ET.SubElement(root, "work")
    ET.SubElement(work, "work-title").text = "Synthetic raw export"
    plist = ET.SubElement(root, "part-list")
    ids = [f"P{i}" for i in range(1, 9)] + ["P9", "P11"]
    parts = {}
    for pid in ids:
        ET.SubElement(ET.SubElement(plist, "score-part", id=pid), "part-name").text = pid
        parts[pid] = ET.SubElement(root, "part", id=pid)

    # Measure 1, open score.
    direction = ET.Element("direction", placement="above")
    words = ET.SubElement(ET.SubElement(direction, "direction-type"), "words")
    words.text = "Lento"
    ET.SubElement(direction, "staff").text = "1"
    barline = ET.Element("barline", location="right")
    ET.SubElement(barline, "bar-style").text = "light-light"
    # P1: two XML voices on one staff, joined with <backup>.
    _measure(parts["P1"], "1", direction,
             _make_note("C", 5, dur=1024, voice="1"), _backup(1024),
             _make_note("A", 4, dur=1024, voice="2"), barline, first=True)
    # P2: stops after a half note; the rest of the bar must be filled.
    _measure(parts["P2"], "1", _make_note("G", 4, dur=512), first=True)
    # P3: five quarters in 4/4, which must be reported, not shortened.
    _measure(parts["P3"], "1", *[_make_note("E", 4, dur=256) for _ in range(5)], first=True)
    # P4: a tie that never stops.
    _measure(parts["P4"], "1", _make_note("D", 4, dur=1024, tie_start=True), first=True)
    for pid in ("P5", "P6", "P7", "P8"):
        _measure(parts[pid], "1", _make_note("C", 4, dur=1024), first=True)
    for pid in ("P9", "P11"):
        _measure(parts[pid], "1", _make_rest(1024), first=True)

    # Measure 2, short score on P9; P5 has a tie stop with no start.
    for pid in ("P1", "P2", "P3", "P4", "P6", "P7", "P8", "P11"):
        _measure(parts[pid], "2", _make_rest(1024))
    _measure(parts["P5"], "2", _make_rest(1024))
    _measure(parts["P9"], "2",
             _on_staff(_make_note("E", 5, dur=1024, voice="1"), "1"), _backup(1024),
             _on_staff(_make_note("C", 5, dur=1024, voice="2"), "1"), _backup(1024),
             _on_staff(_make_note("C", 3, dur=1024, voice="3", tie_stop=True), "2"),
             _on_staff(_make_note("G", 3, dur=1024, voice="3", chord=True), "2"))

    # Measure 3, open score with choir 2 silent.
    forward = ET.Element("forward")
    ET.SubElement(forward, "duration").text = "512"
    # P1: voice 1 has a rest; voice 2 enters late.
    _measure(parts["P1"], "3",
             _make_note("D", 5, dur=512, voice="1"), _make_rest(512, voice="1"), _backup(1024),
             forward, _make_note("B", 4, dur=512, voice="2"))
    # P2: three pitches for two voices must be reported, not dropped silently.
    _measure(parts["P2"], "3", _make_note("C", 4, dur=1024), _make_note("E", 4, dur=1024, chord=True),
             _make_note("G", 4, dur=1024, chord=True))
    # P3: three XML voices cannot be split into two parts.
    _measure(parts["P3"], "3", *[
        child for i, step in enumerate("CEG", 1)
        for child in (_make_note(step, 3, dur=1024, voice=str(i)), _backup(1024))
    ][:-1])
    # P4: one voice overlapping itself.
    _measure(parts["P4"], "3", _make_note("F", 3, dur=1024), _backup(1024), _make_note("A", 3, dur=512))
    for pid in ("P5", "P6", "P7", "P8", "P9", "P11"):
        _measure(parts[pid], "3", _make_rest(1024))
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def test_raw_export_features(tmp_path: Path) -> None:
    from ai_score_editing.musicxml_split.profiles.polychoral_16 import split_16voices
    from ai_score_editing.musicxml_split.validation import validate_file

    source = tmp_path / "raw.musicxml"
    out = tmp_path / "raw16.musicxml"
    _raw_export_features(source)
    result = split_16voices(source, out)
    assert result.measure_count == 3 and len(result.parts) == 16

    root = ET.parse(out).getroot()
    assert root.findtext("work/work-title") == "Synthetic raw export"
    part = {p.get("id"): p for p in root.findall("part")}

    def pitches(pid: str, measure: int) -> list[str]:
        m = part[pid].findall("measure")[measure]
        return [f"{n.findtext('pitch/step')}{n.findtext('pitch/octave')}" if n.find("pitch") is not None else "rest"
                for n in m.findall("note")]

    # Open score: P1's two XML voices become C1 S1 and S2.
    assert pitches("C1_S1", 0) == ["C5"] and pitches("C1_S2", 0) == ["A4"]
    # A direction goes to each choir's top staff without its <staff>; barlines go everywhere.
    c1_s1 = part["C1_S1"].findall("measure")[0]
    assert c1_s1.findtext("direction/direction-type/words") == "Lento"
    assert c1_s1.find("direction/staff") is None
    assert all(p.findall("measure")[0].find("barline") is not None for p in part.values())
    # P2's half note is followed by a filling rest.
    assert pitches("C1_A1", 0) == ["G4", "rest"]
    # Short score: P9 staff 1 voices 1 and 2 fill the upper slots, staff 2 the lower.
    assert pitches("C1_S1", 1) == ["E5"] and pitches("C1_A1", 1) == ["C5"]
    assert {pitches("C1_T1", 1)[0], pitches("C1_B1", 1)[0]} <= {"G3", "C3"}

    codes = {issue.code for issue in result.issues} | {issue.code for issue in validate_file(out, expected_parts=16)}
    assert {"target-overflow", "measure-overflow"} & codes
    assert {"dangling-tie", "unmatched-tie-stop"} <= codes
    assert {"unsupported-pitch-count", "ambiguous-xml-voices", "target-overlap"} <= codes

    # Measure 3: voice 1's rest is kept, and voice 2's late entry gets a rest first.
    assert pitches("C1_S1", 2) == ["D5", "rest"] and pitches("C1_S2", 2) == ["rest", "B4"]
    # Choir 2 has nothing of its own; bar 3 is in the default unison range, so it copies choir 1.
    assert pitches("C2_S1", 2) == pitches("C1_S1", 2)


def test_silent_choir_2_outside_unison_range_stays_silent(tmp_path: Path) -> None:
    from ai_score_editing.musicxml_split.profiles.polychoral_16 import Polychoral16Options, split_16voices

    source = tmp_path / "raw.musicxml"
    out = tmp_path / "raw16.musicxml"
    _raw_export_features(source)
    split_16voices(source, out, Polychoral16Options(choir_unison_indices=frozenset()))
    c2_s1 = next(p for p in ET.parse(out).getroot().findall("part") if p.get("id") == "C2_S1")
    notes = c2_s1.findall("measure")[2].findall("note")
    assert len(notes) == 1 and notes[0].find("rest") is not None
