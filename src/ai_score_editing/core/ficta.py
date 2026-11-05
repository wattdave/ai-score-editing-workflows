"""Find the ficta marks in a MusicXML file and turn them into ``ficta`` batch operations.

A ficta is ``<accidental-mark placement="above">`` on a note (what
``lilypond-pdf-score`` writes). Imported notes have no object ids, so each mark is
reported as part, staff, bar, position in the bar (1/256 of a quarter), the Nth note or
rest in that bar and the sounding pitch. The editors' own ``query`` numbers objects
differently (lyrics, dynamics and so on take indices too), so ``resolve`` looks the real
address up from a ``query`` result by staff, bar, position and pitch. Pure: no I/O.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any

from .batch_schema import FICTA_ACCIDENTALS
from .errors import BatchError
from .units import UNITS_PER_QUARTER

_STEPS = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def _pitch(note: ET.Element) -> int | None:
    pitch = note.find("pitch")
    if pitch is None:
        return None
    alter = float(pitch.findtext("alter", "0"))
    return 12 * (int(pitch.findtext("octave", "4")) + 1) + _STEPS[pitch.findtext("step", "C")] + round(alter)


def list_ficta(xml_text: str) -> list[dict[str, Any]]:
    """Every ficta mark in the score, in score order.

    Each row has ``part``, ``partName``, ``staff`` (counted across the whole score, as the
    editors do), ``bar`` (the 1-based measure count, so a pickup is bar 1), ``barNumber``
    (the printed number), ``position`` (1/256 of a quarter into the bar), ``noteIndex``
    (0-based count of notes and rests in the bar for that staff, a chord counting once),
    ``pitch`` (MIDI, as written in the file) and ``accidental`` (flat, natural or sharp).
    """
    root = ET.fromstring(xml_text)
    names = {sp.get("id"): sp.findtext("part-name", "") for sp in root.iter("score-part")}
    rows: list[dict[str, Any]] = []
    first_staff = 1
    for part in root.findall("part"):
        staves = 1
        divisions = 1
        for bar_number, measure in enumerate(part.findall("measure"), start=1):
            staves = max(staves, int(measure.findtext("attributes/staves", "1")))
            counts: dict[int, int] = {}
            cursor = 0
            last_start = 0
            for child in measure:
                if child.tag == "attributes" and child.findtext("divisions"):
                    divisions = int(child.findtext("divisions", "1"))
                elif child.tag == "backup":
                    cursor -= int(child.findtext("duration", "0"))
                elif child.tag == "forward":
                    cursor += int(child.findtext("duration", "0"))
                elif child.tag == "note":
                    if child.find("grace") is not None:
                        continue
                    chord = child.find("chord") is not None
                    start = last_start if chord else cursor
                    staff = first_staff + int(child.findtext("staff", "1")) - 1
                    if chord:
                        index = counts.get(staff, 1) - 1
                    else:
                        index = counts.get(staff, 0)
                        counts[staff] = index + 1
                        last_start = start
                        cursor += int(child.findtext("duration", "0"))
                    mark = child.find("notations/accidental-mark")
                    if mark is None or mark.get("placement") != "above":
                        continue
                    accidental = (mark.text or "").strip()
                    if accidental not in FICTA_ACCIDENTALS:
                        raise BatchError(f"bar {bar_number}: ficta accidental {accidental!r} is not one of {FICTA_ACCIDENTALS}")
                    rows.append({
                        "part": part.get("id"), "partName": names.get(part.get("id"), ""),
                        "staff": staff, "bar": bar_number, "barNumber": measure.get("number"),
                        "position": start * UNITS_PER_QUARTER // divisions, "noteIndex": index,
                        "pitch": _pitch(child), "accidental": accidental,
                    })
        first_staff += staves
    return rows


def _candidates(objects: list[dict[str, Any]]):
    for obj in objects:
        if obj.get("pitch") is not None:  # Dorico: one event per note
            yield obj, obj["pitch"]
        for note in obj.get("notes") or []:  # Sibelius and MuseScore: a chord with notes
            if isinstance(note, dict) and note.get("pitch") is not None:
                yield obj, note["pitch"]


def resolve(rows: list[dict[str, Any]], objects: list[dict[str, Any]], editor: str) -> list[dict[str, Any]]:
    """``ficta`` operations for ``rows``, addressed from a ``query`` result's ``objects``.

    ``editor`` is ``sibelius``, ``musescore`` or ``dorico`` (Dorico addresses by ``id``).
    Raises ``BatchError`` listing every mark with no, or more than one, matching note.
    """
    if editor not in {"sibelius", "musescore", "dorico"}:
        raise BatchError(f"unknown editor {editor!r}")
    seen = list(_candidates(objects))
    operations: list[dict[str, Any]] = []
    problems: list[str] = []
    for row in rows:
        found = [obj for obj, pitch in seen
                 if obj.get("staff") == row["staff"] and obj.get("bar") == row["bar"]
                 and obj.get("position") == row["position"] and pitch == row["pitch"]]
        if len(found) != 1:
            problems.append(f"staff {row['staff']} bar {row['bar']} position {row['position']} pitch {row['pitch']}: "
                            f"{len(found)} matching notes")
            continue
        obj = found[0]
        if editor == "dorico":
            operations.append({"op": "ficta", "id": obj["id"], "accidental": row["accidental"]})
        else:
            operations.append({"op": "ficta", "staff": row["staff"], "bar": row["bar"], "index": obj["index"],
                               "type": obj.get("type", "NoteRest"), "position": row["position"],
                               "accidental": row["accidental"]})
    if problems:
        raise BatchError("could not place " + "; ".join(problems))
    return operations
