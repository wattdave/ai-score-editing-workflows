#!/usr/bin/env python3
"""Write a MusicXML score with one musical figure per region, for the Dorico
selection research (docs/dorico-selection-research-plan.md).

    python3 scripts/dev/make_selection_fixtures.py OUTPUT.musicxml

A two-staff piano in 4/4 (divisions 12 per quarter, a bar is 48). Plain bars
hold one whole note per staff, with pitches that change every bar so that
no two notes could be taken for a tie. Each figure is alone on its staff in
its bars, separated from the next by control bars. Import the file in Dorico
and run scripts/dev/dorico_selection_probe.py on it. FIGURES lists what is where.
"""

from __future__ import annotations

import sys
from xml.sax.saxutils import escape

DIV = 12
BAR = 48
HALF = BAR // 2

# bar -> (staff 1 figure, staff 2 figure); anything not listed is plain.
FIGURES: dict[int, tuple[str, str]] = {
    4: ("rest", "rest"), 5: ("rest", "rest"), 6: ("rest", "rest"),  # three empty bars on both staves
    8: ("tie-out", "plain"), 9: ("tie-in", "plain"),  # half note tied over the barline 8|9
    11: ("long-start", "plain"), 12: ("long-mid", "plain"), 13: ("long-end", "plain"),  # whole note held over 3 bars
    15: ("grace", "plain"), 16: ("grace", "plain"),  # a grace note before the downbeat
    18: ("triplet", "plain"), 19: ("triplet", "plain"),  # eighth-note triplets
    21: ("melisma", "plain"), 22: ("melisma-end", "plain"),  # lyric extender over the barline 21|22
    24: ("plain", "tie-out"), 25: ("plain", "tie-in"),  # the tie, on staff 2 only
    27: ("plain", "long-start"), 28: ("plain", "long-mid"), 29: ("plain", "long-end"),  # the long note, on staff 2 only
    31: ("rest", "plain"), 32: ("rest", "plain"),  # staff 1 empty, staff 2 playing
    34: ("late", "plain"), 35: ("late", "plain"), 36: ("late", "plain"),  # a half rest, then notes: the first note starts late in the bar
    38: ("late-long", "plain"), 39: ("late-long", "plain"),  # a quarter rest, then a dotted half to the barline
    44: ("voices", "plain"), 45: ("voices", "plain"),  # a second voice of half notes under a whole note
    40: ("wedge-start", "plain"), 41: ("plain-half", "plain"), 42: ("wedge-end", "plain"),  # a crescendo hairpin from bar 40 beat 3 to bar 42 beat 3
    51: ("slur-start", "plain"), 52: ("plain-half", "plain"), 53: ("slur-end", "plain"),  # a slur from bar 51 to bar 53
    58: ("h-s", "plain"), 59: ("he-", "plain"),  # slur from beat 3 of bar 58 to the first note of bar 59
    61: ("hs-", "plain"), 62: ("h--", "plain"), 63: ("he-", "plain"),  # slur from bar 61 beat 1 to the first note of bar 63
    65: ("hs-", "plain"), 66: ("we", "plain"),  # slur from bar 65 beat 1 to a whole note starting bar 66
    68: ("ws", "plain"), 69: ("he-", "plain"),  # slur from a whole note in bar 68 to the first note of bar 69
    47: ("voices-tie", "plain"), 48: ("voices-tie-in", "plain"),  # voice 2 tied over the barline 47|48 under quarter notes
}
LAST_BAR = 71

STEPS = ["C", "D", "E", "F", "G", "A", "B"]


def note(step: str, octave: int, dur: int, typ: str, staff: int, *, extra: str = "", lyric: str = "", dot: bool = False,
         tie: str = "", grace: bool = False, tuplet: str = "", voice: int = 0) -> str:
    parts = ["<note>"]
    if grace:
        parts.append("<grace/>")
    parts.append(f"<pitch><step>{step}</step><octave>{octave}</octave></pitch>")
    if not grace:
        parts.append(f"<duration>{dur}</duration>")
    if tie in ("start", "both"):
        parts.append('<tie type="start"/>')
    if tie in ("stop", "both"):
        parts.append('<tie type="stop"/>')
    parts.append(f"<voice>{voice or (1 if staff == 1 else 5)}</voice>")
    parts.append(f"<type>{typ}</type>")
    if dot:
        parts.append("<dot/>")
    if tuplet:
        parts.append("<time-modification><actual-notes>3</actual-notes><normal-notes>2</normal-notes></time-modification>")
    parts.append(f"<staff>{staff}</staff>")
    notations = ""
    if tie in ("start", "both"):
        notations += '<tied type="start"/>'
    if tie in ("stop", "both"):
        notations += '<tied type="stop"/>'
    notations += extra
    if tuplet == "start":
        notations += '<tuplet type="start"/>'
    elif tuplet == "stop":
        notations += '<tuplet type="stop"/>'
    if notations:
        parts.append(f"<notations>{notations}</notations>")
    if lyric:
        text = escape(lyric.split("+")[0])
        ext = "<extend/>" if lyric.endswith("+") else ""
        parts.append(f'<lyric number="1"><syllabic>single</syllabic><text>{text}</text>{ext}</lyric>')
    parts.append("</note>")
    return "".join(parts)


def rest(staff: int) -> str:
    voice = 1 if staff == 1 else 5
    return (f'<note><rest measure="yes"/><duration>{BAR}</duration><voice>{voice}</voice><staff>{staff}</staff></note>')


def whole(bar: int, staff: int, *, tie: str = "", pitch_shift: int = 0) -> str:
    base = 5 if staff == 1 else 3
    step = STEPS[(bar * 2 + staff + pitch_shift) % 7]
    return note(step, base, BAR, "whole", staff, tie=tie)


def staff_bar(bar: int, staff: int) -> str:
    kind = FIGURES.get(bar, ("plain", "plain"))[staff - 1]
    base = 5 if staff == 1 else 3
    if kind == "rest":
        return rest(staff)
    if kind == "tie-out":
        return note("C", base, HALF, "half", staff) + note("D", base, HALF, "half", staff, tie="start")
    if kind == "tie-in":
        return note("D", base, HALF, "half", staff, tie="stop") + note("E", base, HALF, "half", staff)
    if kind == "long-start":
        return note("F", base, BAR, "whole", staff, tie="start")
    if kind == "long-mid":
        return note("F", base, BAR, "whole", staff, tie="both")
    if kind == "long-end":
        return note("F", base, BAR, "whole", staff, tie="stop")
    if kind == "late":
        out = f'<note><rest/><duration>{HALF}</duration><voice>{1 if staff == 1 else 5}</voice><type>half</type><staff>{staff}</staff></note>'
        for step in ("C", "D", "E", "F"):
            out += note(step, base, HALF // 4 * 1, "eighth" if False else "eighth", staff)
        return out
    if kind == "late-long":
        voice = 1 if staff == 1 else 5
        out = f'<note><rest/><duration>{DIV}</duration><voice>{voice}</voice><type>quarter</type><staff>{staff}</staff></note>'
        return out + note("C", base, BAR - DIV, "half", staff, dot=True)  # a quarter rest, then a dotted half to the barline
    if kind in ("voices", "voices-tie", "voices-tie-in"):
        back = f"<backup><duration>{BAR}</duration></backup>"
        if kind == "voices":
            return (note("C", base + 1, BAR, "whole", staff) + back
                    + note("E", base, HALF, "half", staff, voice=2) + note("F", base, HALF, "half", staff, voice=2))
        if kind == "voices-tie":
            top = "".join(note(step, base + 1, DIV, "quarter", staff) for step in ("C", "D", "E", "F"))
            return top + back + note("A", base, HALF, "half", staff, voice=2) + note("G", base, HALF, "half", staff, voice=2, tie="start")
        top = "".join(note(step, base + 1, DIV, "quarter", staff) for step in ("G", "A", "B", "C"))
        return top + back + note("G", base, HALF, "half", staff, voice=2, tie="stop") + note("F", base, HALF, "half", staff, voice=2)
    if kind in ("wedge-start", "plain-half", "wedge-end"):
        def wedge(kind_: str) -> str:
            return f'<direction placement="below"><direction-type><wedge type="{kind_}"/></direction-type><staff>{staff}</staff></direction>'
        def dyn(mark: str) -> str:
            return f'<direction placement="below"><direction-type><dynamics><{mark}/></dynamics></direction-type><staff>{staff}</staff></direction>'
        first = note("C", base, HALF, "half", staff)
        second = note("D", base, HALF, "half", staff)
        if kind == "wedge-start":
            return dyn("p") + wedge("crescendo") + first + second
        if kind == "wedge-end":
            return first + wedge("stop") + dyn("f") + second
        return first + second
    if len(kind) == 3 and kind[0] == "h" or kind in ("we", "ws"):
        # "h" + one letter per half note, "w" + one letter for a whole note: s starts a slur on that note, e ends it
        def mark(c: str) -> str:
            return {"s": '<slur type="start" number="1"/>', "e": '<slur type="stop" number="1"/>'}.get(c, "")
        if kind[0] == "w":
            return note("C", base, BAR, "whole", staff, extra=mark(kind[1]))
        return note("C", base, HALF, "half", staff, extra=mark(kind[1])) + note("D", base, HALF, "half", staff, extra=mark(kind[2]))
    if kind in ("slur-start", "slur-end"):
        slur = lambda t: f'<slur type="{t}" number="1"/>'
        if kind == "slur-start":
            return note("C", base, HALF, "half", staff, extra=slur("start")) + note("D", base, HALF, "half", staff)
        return note("C", base, HALF, "half", staff) + note("D", base, HALF, "half", staff, extra=slur("stop"))
    if kind == "grace":
        return note("B", base, 0, "eighth", staff, grace=True) + note("C", base, BAR, "whole", staff)
    if kind == "triplet":
        out = note("C", base, HALF, "half", staff)
        for i, step in enumerate(("D", "E", "F")):
            out += note(step, base, DIV // 3, "eighth", staff, tuplet=("start" if i == 0 else "stop" if i == 2 else "mid"))
        out += note("G", base, DIV, "quarter", staff)  # half + triplet quarter + quarter fill the bar
        return out
    if kind == "melisma":
        return note("C", base, HALF, "half", staff) + note("D", base, HALF, "half", staff, lyric="la+")
    if kind == "melisma-end":
        return note("E", base, HALF, "half", staff) + note("F", base, HALF, "half", staff)
    return whole(bar, staff)


def build() -> str:
    measures = []
    for bar in range(1, LAST_BAR + 1):
        attrs = ""
        if bar == 1:
            attrs = (f"<attributes><divisions>{DIV}</divisions><key><fifths>0</fifths></key>"
                     "<time><beats>4</beats><beat-type>4</beat-type></time><staves>2</staves>"
                     '<clef number="1"><sign>G</sign><line>2</line></clef>'
                     '<clef number="2"><sign>F</sign><line>4</line></clef></attributes>')
        body = staff_bar(bar, 1)
        back = f"<backup><duration>{BAR}</duration></backup>"
        measures.append(f'<measure number="{bar}">{attrs}{body}{back}{staff_bar(bar, 2)}</measure>')
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">\n'
        '<score-partwise version="4.0"><work><work-title>Selection figures</work-title></work>'
        '<part-list><score-part id="P1"><part-name>Piano</part-name></score-part></part-list>'
        f'<part id="P1">{"".join(measures)}</part></score-partwise>\n'
    )


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    with open(sys.argv[1], "w", encoding="utf-8") as handle:
        handle.write(build())


if __name__ == "__main__":
    main()
