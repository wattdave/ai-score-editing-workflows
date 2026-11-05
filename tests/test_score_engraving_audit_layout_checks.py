"""Tests for the lyrics-crowded, stems-wrong-direction and beam-style checks."""

from __future__ import annotations

from xml.etree import ElementTree as ET

from helpers import ROOT, load_script

audit = load_script(ROOT / ".claude/skills/score-engraving-audit/scripts/audit_musicxml.py", "audit_musicxml_layout")


def _n(step="B", octave=4, typ="quarter", dur=4, stem=None, beam=None, lyrics=(), voice=1, chord=False) -> str:
    ly = "".join(f'<lyric number="{i + 1}"><syllabic>{syl}</syllabic><text>{t}</text></lyric>' for i, (t, syl) in enumerate(lyrics))
    stem_xml = f"<stem>{stem}</stem>" if stem else ""
    beam_xml = f'<beam number="1">{beam}</beam>' if beam else ""
    return (
        f"<note>{'<chord/>' if chord else ''}<pitch><step>{step}</step><octave>{octave}</octave></pitch>"
        f"<duration>{dur}</duration><voice>{voice}</voice><type>{typ}</type>{stem_xml}{beam_xml}{ly}</note>"
    )


TREBLE = "<sign>G</sign><line>2</line>"
BASS = "<sign>F</sign><line>4</line>"


def _score(*bars: str, clef: str = TREBLE) -> ET.Element:
    ms = ""
    for i, b in enumerate(bars, 1):
        attrs = f"<attributes><divisions>4</divisions><time><beats>4</beats><beat-type>4</beat-type></time><clef>{clef}</clef></attributes>" if i == 1 else ""
        ms += f'<measure number="{i}">{attrs}{b}</measure>'
    return ET.fromstring(
        '<score-partwise><work><work-title>T</work-title></work><part-list><score-part id="P1"><part-name>S</part-name></score-part></part-list>'
        f'<part id="P1">{ms}</part></score-partwise>'
    )


def found(root: ET.Element, code: str) -> list[dict]:
    return [f for f in audit.audit(root) if f["code"] == code]


def test_lyrics_crowded_long_syllables_on_short_notes() -> None:
    bar = "".join(_n(typ="16th", dur=1, lyrics=[("ring", "single")]) for _ in range(4)) + _n(dur=12)
    f = found(_score(bar), "lyrics-crowded")
    assert f and f[0]["severity"] == "warn" and "P1 bar 1" in f[0]["where"]


def test_lyrics_not_crowded_for_ordinary_text() -> None:
    bar = "".join(_n(lyrics=[("night", "single")]) for _ in range(4))
    assert not found(_score(bar), "lyrics-crowded")


def test_lyrics_crowded_reports_worst_five_bars_and_stacked_verses() -> None:
    crowded = "".join(_n(typ="eighth", dur=2, lyrics=[("glo-", "begin"), ("ria", "single"), ("x", "single")]) for _ in range(8))
    f = found(_score(*[crowded] * 7), "lyrics-crowded")
    assert f and len(f[0]["where"].split(", ")) == 5 and "3 verses are stacked" in f[0]["message"]


def test_stems_single_voice_rule() -> None:
    good = _n("D", 5, stem="down") + _n("G", 4, stem="up") + _n("B", 4, stem="down") + _n("C", 4, stem="up")
    assert found(_score(good), "stems-wrong-direction")[0]["severity"] == "info"
    bad = "".join(_n("D", 5, stem="up") for _ in range(4))
    f = found(_score(bad), "stems-wrong-direction")[0]
    assert f["severity"] == "warn" and "P1 bar 1" in f["where"]


def test_stems_bass_clef_and_chord_farthest_note() -> None:
    # Bass clef: middle line is D3, so F2 is below it and stems up.
    bad = "".join(_n("F", 2, stem="down") for _ in range(4))
    assert found(_score(bad, clef=BASS), "stems-wrong-direction")[0]["severity"] == "warn"
    # Chord A3 + C3: A3 is farthest from D3, so the chord stems down.
    chord = "".join(_n("A", 3, stem="down") + _n("C", 3, stem="down", chord=True) for _ in range(4))
    assert found(_score(chord, clef=BASS), "stems-wrong-direction")[0]["severity"] == "info"


def test_stems_two_voices_and_beamed_group() -> None:
    two = _n("C", 5, stem="down", voice=1) + "<backup><duration>4</duration></backup>" + _n("C", 4, stem="down", voice=2)
    assert found(_score(*[two] * 4), "stems-wrong-direction")[0]["severity"] == "warn"
    # Beamed G4 (below) and D5 (above): D5 is farthest, so the group stems down.
    beamed = _n("G", 4, typ="eighth", dur=2, stem="down", beam="begin") + _n("D", 5, typ="eighth", dur=2, stem="down", beam="end") + _n("C", 5, dur=4, stem="down")
    assert found(_score(*[beamed] * 4), "stems-wrong-direction")[0]["severity"] == "info"


def test_stems_absent_is_info_not_checked() -> None:
    f = found(_score(_n() * 4), "stems-wrong-direction")
    assert f[0]["severity"] == "info" and "not checked" in f[0]["message"]


def _pair(syllables: tuple[str, str] | None, joined: bool) -> str:
    def ly(i: int) -> list:
        return [(syllables[i], "single")] if syllables else []

    b1, b2 = ("begin", "end") if joined else (None, None)
    return _n(typ="eighth", dur=2, beam=b1, lyrics=ly(0)) + _n(typ="eighth", dur=2, beam=b2, lyrics=ly(1)) + _n(dur=4) + _n(dur=4)


def test_beam_style_undetermined_with_few_beams() -> None:
    f = found(_score(_pair(("a", "b"), True)), "beam-style")
    assert f[0]["severity"] == "info" and "undetermined" in f[0]["message"]


def test_beam_style_modern_and_syllabic() -> None:
    modern = found(_score(*[_pair(("a", "b"), True)] * 8), "beam-style")[0]["message"]
    assert "modern" in modern and "--style meter" in modern
    # Joined pairs share a syllable (no lyric on the second note); broken pairs start a new one.
    melisma = _n(typ="eighth", dur=2, beam="begin", lyrics=[("a", "single")]) + _n(typ="eighth", dur=2, beam="end") + _n(dur=4) + _n(dur=4)
    syl = found(_score(*([melisma] * 6 +[_pair(("a", "b"), False)] * 4)), "beam-style")[0]["message"]
    assert "syllabic" in syl and "--style syllabic" in syl
