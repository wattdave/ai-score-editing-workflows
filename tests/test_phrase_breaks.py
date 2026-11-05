"""Tests for the phrase-breaks skill script."""

from __future__ import annotations

from xml.etree import ElementTree as ET

from helpers import ROOT, load_script

pb = load_script(ROOT / ".claude/skills/phrase-breaks/scripts/propose_breaks.py", "propose_breaks")

HEADER = '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 3.0 Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">\n'


def note(dur: int = 4, lyric: str | None = None, rest: bool = False, extra: str = "") -> str:
    body = "<rest/>" if rest else "<pitch><step>C</step><octave>4</octave></pitch>"
    ly = f"<lyric><syllabic>single</syllabic><text>{lyric}</text></lyric>" if lyric else ""
    return f"<note>{body}<duration>{dur}</duration><type>quarter</type>{extra}{ly}</note>"


def measure(n: int, content: str, attrs: str = "", extra: str = "") -> str:
    return f'<measure number="{n}">{attrs}{extra}{content}</measure>'


ATTRS = "<attributes><divisions>4</divisions><time><beats>4</beats><beat-type>4</beat-type></time></attributes>"


def plain(n: int) -> str:
    return note(4) * 4


def score(measures: list[str], parts: int = 1) -> str:
    body = "".join(f'<part id="P{k}">{"".join(measures)}</part>' for k in range(1, parts + 1))
    plist = "".join(f'<score-part id="P{k}"><part-name>P{k}</part-name></score-part>' for k in range(1, parts + 1))
    return f'{HEADER}<score-partwise version="3.0"><part-list>{plist}</part-list>{body}</score-partwise>\n'


def bars_of(xml: str):
    bars, _ = pb.analyse(ET.fromstring(xml))
    return bars


def build(n: int, special: dict[int, str] | None = None, first_attrs: str = ATTRS) -> list[str]:
    special = special or {}
    return [measure(i, special.get(i, plain(i)), first_attrs if i == 1 else "") for i in range(1, n + 1)]


def canon(el: ET.Element) -> list:
    """Tag, attributes and stripped text of an element tree, ignoring indentation."""
    return [(e.tag, sorted(e.attrib.items()), (e.text or "").strip()) for e in el.iter()]


def sig(xml: str, i: int) -> dict:
    return bars_of(xml)[i - 1].signals


# ---- phrase-end signals ----------------------------------------------------

def test_lyric_punctuation_signals() -> None:
    m = {1: note(4, "a") * 3 + note(4, "night."), 2: note(4, "a") * 3 + note(4, "bright;"),
         3: note(4, "a") * 3 + note(4, "night,"), 4: note(4, "a") * 4}
    xml = score(build(5, m))
    assert "lyric-sentence" in sig(xml, 1)
    assert "lyric-semicolon" in sig(xml, 2)
    assert "lyric-comma" in sig(xml, 3)
    assert not {"lyric-sentence", "lyric-semicolon", "lyric-comma"} & set(sig(xml, 4))


def test_long_final_note_and_rest() -> None:
    m = {1: note(4) * 2 + note(8), 2: note(4) * 3 + note(4, rest=True), 3: note(4) * 4}
    xml = score(build(4, m))
    assert "long-note" in sig(xml, 1)
    assert "rest" in sig(xml, 2)
    assert not {"long-note", "rest"} & set(sig(xml, 3))


def test_fermata_and_barlines() -> None:
    fer = note(4, extra="<notations><fermata/></notations>")
    m = {1: note(4) * 3 + fer}
    right = '<barline location="right"><bar-style>light-light</bar-style></barline>'
    rep = '<barline location="right"><bar-style>light-heavy</bar-style><repeat direction="backward"/></barline>'
    fwd = '<barline location="left"><bar-style>heavy-light</bar-style><repeat direction="forward"/></barline>'
    ms = build(6, m)
    ms[1] = measure(2, plain(2) + right)
    ms[2] = measure(3, plain(3) + rep)
    ms[4] = measure(5, plain(5), extra=fwd)
    xml = score(ms)
    assert "fermata" in sig(xml, 1)
    assert "barline" in sig(xml, 2)
    assert "barline" in sig(xml, 3)
    assert "forward-repeat" in sig(xml, 4)


def test_next_bar_changes_and_rehearsal() -> None:
    ms = build(6)
    ms[1] = measure(2, plain(2), "<attributes><time><beats>3</beats><beat-type>4</beat-type></time></attributes>")
    ms[2] = measure(3, note(4) * 3)
    ms[3] = measure(4, plain(4), "<attributes><key><fifths>2</fifths></key></attributes>")
    ms[4] = measure(5, plain(5), extra='<direction><direction-type><rehearsal>A</rehearsal></direction-type></direction>')
    ms[5] = measure(6, plain(6), extra='<direction><direction-type><words>Allegro</words></direction-type><sound tempo="120"/></direction>')
    xml = score(ms)
    assert "key-time-change" in sig(xml, 1)
    assert "key-time-change" not in sig(xml, 2)
    assert "rehearsal" in sig(xml, 4)
    assert "tempo-change" in sig(xml, 5)


def test_four_bar_periodicity_counts_from_first_full_bar() -> None:
    plain_xml = score(build(10))
    assert "periodicity" in sig(plain_xml, 4) and "periodicity-8" not in sig(plain_xml, 4)
    assert {"periodicity", "periodicity-8"} <= set(sig(plain_xml, 8))
    pick = [measure(1, note(4), ATTRS)] + [measure(i, plain(i)) for i in range(2, 11)]
    xml = score(pick)
    assert "periodicity" in sig(xml, 5) and "periodicity" not in sig(xml, 4)


# ---- DP behaviour ----------------------------------------------------------

def test_targets_and_phrase_alignment() -> None:
    # phrase ends after bars 4, 8, 12 of 16: every candidate breaks there
    m = {i: note(4, "a") * 3 + note(4, "end.") for i in (4, 8, 12)}
    bars = bars_of(score(build(16, m)))
    starts, _ = pb.solve(bars, 4.0)
    assert starts == [0, 4, 8, 12]
    wide, _ = pb.solve(bars, 8.0)
    assert wide == [0, 8]


def test_sizes_near_target_and_no_orphan_final_system() -> None:
    bars = bars_of(score(build(13)))  # no signals at all except periodicity
    starts, _ = pb.solve(bars, 4.0)
    sizes = [b - a for a, b in zip(starts, starts[1:] + [13])]
    assert sizes[-1] >= 3 and max(sizes) - min(sizes) <= 2
    assert all(2 <= s <= 7 for s in sizes)


def test_pickup_is_never_separated_from_first_bar() -> None:
    # A phrase end after the pickup would invite a break there.
    pick = measure(1, note(4, "up."), ATTRS)
    ms = [pick] + [measure(i, plain(i)) for i in range(2, 10)]
    bars = bars_of(score(ms))
    assert bars[0].pickup
    for target in (1.0, 2.0, 3.0, 4.0):
        starts, _ = pb.solve(bars, target)
        assert 1 not in starts


def test_break_before_single_note_final_bar_is_avoided() -> None:
    ms = build(9)
    ms[8] = measure(9, note(16))  # final bar holds only one note
    bars = bars_of(score(ms))
    assert bars[-1].final_only
    starts, _ = pb.solve(bars, 4.0)
    assert 8 not in starts


def test_candidates_differ() -> None:
    bars = bars_of(score(build(24)))
    cands, _ = pb.layouts(bars, "wide,medium,narrow")
    sizes = {c["name"]: c["sizes"] for c in cands}
    assert len({tuple(s) for s in sizes.values()}) == 3
    assert max(sizes["wide"]) > max(sizes["medium"]) > max(sizes["narrow"])


def test_dense_music_takes_fewer_bars() -> None:
    dense = [measure(i, note(1) * 16, ATTRS if i == 1 else "") for i in range(1, 25)]
    sparse = [measure(i, note(8) * 2, ATTRS if i == 1 else "") for i in range(1, 25)]
    d, _ = pb.layouts(bars_of(score(dense)), "medium")
    s, _ = pb.layouts(bars_of(score(sparse)), "medium")
    assert d[0]["target"] < s[0]["target"]


def test_reasons_name_signal_or_compromise() -> None:
    m = {4: note(4, "a") * 3 + note(4, "end.")}
    bars = bars_of(score(build(12, m)))
    assert "lyric-sentence" in pb.reason(bars, 3)
    assert pb.reason(bars, 1).startswith("compromise: broke mid-phrase after bar 2")
    assert "after bar 4, 2 bars away" in pb.reason(bars, 1)
    assert "no later phrase end" in pb.reason(bars, 5)


# ---- --apply ---------------------------------------------------------------

def test_apply_writes_breaks_in_every_part_and_preserves_header_and_notes(tmp_path) -> None:
    ms = build(12)
    ms[4] = measure(5, plain(5), extra='<print new-page="no" page-number="3"/>')
    src = tmp_path / "in.xml"
    src.write_text(score(ms, parts=2), encoding="utf-8")
    out = tmp_path / "out.xml"
    assert pb.main([str(src), "--apply", "narrow", "--out", str(out)]) == 0
    text = out.read_text(encoding="utf-8")
    assert text.startswith(HEADER)
    root = ET.fromstring(text)
    broken = []
    for part in root.findall("part"):
        broken.append([i for i, m in enumerate(part.findall("measure")) if (m.find("print") is not None and m.find("print").get("new-system") == "yes")])
    assert broken[0] == broken[1] and len(broken[0]) >= 2
    assert all(i > 0 for i in broken[0])
    pr = root.findall("part")[0].findall("measure")[4].find("print")
    assert pr.get("page-number") == "3" and pr.get("new-page") == "no"
    before = ET.fromstring(src.read_text(encoding="utf-8"))
    for p0, p1 in zip(before.findall("part"), root.findall("part")):
        assert [canon(n) for n in p0.iter("note")] == [canon(n) for n in p1.iter("note")]


def test_apply_is_idempotent(tmp_path) -> None:
    src = tmp_path / "in.xml"
    src.write_text(score(build(16), parts=2), encoding="utf-8")
    one, two = tmp_path / "one.xml", tmp_path / "two.xml"
    assert pb.main([str(src), "--apply", "medium", "--out", str(one)]) == 0
    assert pb.main([str(one), "--apply", "medium", "--out", str(two)]) == 0
    assert one.read_text() == two.read_text()


def test_page_bars_adds_new_page_at_system_starts(tmp_path) -> None:
    src = tmp_path / "in.xml"
    src.write_text(score(build(48)), encoding="utf-8")
    out = tmp_path / "out.xml"
    assert pb.main([str(src), "--apply", "medium", "--page-bars", "16", "--out", str(out)]) == 0
    root = ET.fromstring(out.read_text())
    pages = [i for i, m in enumerate(root.find("part").findall("measure")) if m.find("print") is not None and m.find("print").get("new-page") == "yes"]
    assert 1 <= len(pages) <= 3
    assert all(m.find("print").get("new-system") == "yes" for m in root.find("part").findall("measure") if m.find("print") is not None)


def test_apply_needs_out_and_bad_input(tmp_path, capsys) -> None:
    src = tmp_path / "in.xml"
    src.write_text(score(build(8)), encoding="utf-8")
    assert pb.main([str(src), "--apply", "medium"]) == 2
    assert pb.main([str(tmp_path / "missing.xml")]) == 2


def test_report_and_json(tmp_path, capsys) -> None:
    src = tmp_path / "in.xml"
    src.write_text(score(build(12)), encoding="utf-8")
    assert pb.main([str(src)]) == 0
    out = capsys.readouterr().out
    assert "== wide" in out and "== medium" in out and "== narrow" in out
    assert pb.main([str(src), "--json", "--candidates", "medium,5"]) == 0
    import json
    data = json.loads(capsys.readouterr().out)
    assert [c["name"] for c in data["candidates"]] == ["medium", "5"]
