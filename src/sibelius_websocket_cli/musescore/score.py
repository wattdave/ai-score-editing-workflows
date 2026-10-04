"""Queries and batches for MuseScore in the Sibelius back end's terms.

Objects are addressed as staff/bar/index, positions are 1/256 of a quarter
note within the bar, pitches are MIDI numbers: the same shapes query_score
and apply_batch use for Sibelius. Underneath, msbridge.qml walks each bar of
a staff in a fixed order and reports every object's place in that walk (its
raw ordinal). This module orders the walk into indices, and turns a batch
into primitives that name objects by staff, bar, raw ordinal, type and tick;
the bridge walks the bar again and checks all of these before any edit.

MuseScore elements have no ids that last between calls, so the type,
position and pitch guards, plus a digest of each bar a batch touches, are
what make sure the object changed is the one that was read.
"""

from __future__ import annotations

from typing import Any

from sibelius_websocket_cli import batch_ops, intervals

UNITS_PER_QUARTER = 256
SYSTEM_STAFF = 0

# Order of objects at one tick (docs/musescore-backend-plan.md, Addresses):
# clefs, key and time signatures, annotations, tuplets before the chords
# they hold, chords and rests by voice, lyrics by verse, then lines.
KIND_ORDER = {
    "Clef": 0, "KeySignature": 1, "TimeSignature": 2, "Text": 3,
    "Tuplet": 4, "NoteRest": 5, "LyricItem": 6, "Line": 7,
}
#: MuseScore spanner names as line types, where Sibelius's name differs.
LINE_TYPES = {"HairPin": "Hairpin"}

#: MuseScore BeamMode: AUTO 0, NONE 1, BEGIN 2, BEGIN16 3, BEGIN32 4, MID 5, END 6.
BEAM_BEGIN, BEAM_MID, MAX_BEAM_MODE = 2, 5, 6
#: Direction: AUTO 0, UP 1, DOWN 2.
STEM_AUTO = 0
#: hasParentheses: 0 none, 3 both sides (1 and 2 hit an assertion on notes).
PARENTHESES = 3

SUPPORTED = {"set", "set-pitch", "tie", "bracket", "flip-stem", "nudge", "delete", "beam"}
#: Valid batch operations the MuseScore back end does not do yet, with the
#: milestone of docs/musescore-backend-plan.md that adds them.
NOT_YET = {
    **{op: 3 for op in batch_ops.ADDING},
    **{op: 4 for op in batch_ops.STRUCTURAL},
}


class MuseScoreBatchError(ValueError):
    """A batch or query cannot be run against the score as read."""


# ------------------------------------------------------------------ units

def to_units(ticks: int, division: int) -> int:
    """MuseScore ticks as 1/256 quarters, rounded (tuplets are not exact)."""
    return round(ticks * UNITS_PER_QUARTER / division)


def to_ticks(units: int, division: int, label: str) -> int:
    ticks = units * division / UNITS_PER_QUARTER
    if ticks != int(ticks):
        raise MuseScoreBatchError(f"{label}: {units} units is not a whole number of MuseScore ticks")
    return int(ticks)


def dx_units(offset: float) -> int:
    """MuseScore offsetX (staff spaces) as Sibelius Dx (1/32 space)."""
    return round(offset * 32)


def dy_units(offset: float) -> int:
    """MuseScore offsetY (staff spaces, down) as Sibelius Dy (1/32 space, up)."""
    return round(-offset * 32) or 0


# ------------------------------------------------------------------ spelling

_FIFTHS = {"F": -1, "C": 0, "G": 1, "D": 2, "A": 3, "E": 4, "B": 5}


def tpc(letter: str, alter: int) -> int:
    """MuseScore's tonal pitch class: C is 14, each fifth up adds one."""
    return 14 + _FIFTHS[letter] + 7 * alter


def fifths_of(diatonic: int, chromatic: int) -> int:
    """The interval (diatonic steps, semitones) as a number of fifths."""
    for fifths in sorted(range(-30, 31), key=abs):
        if (7 * fifths - chromatic) % 12 == 0 and (4 * fifths - diatonic) % 7 == 0:
            return fifths
    raise MuseScoreBatchError(f"cannot spell a transposition of {diatonic} steps, {chromatic} semitones")


def written_tpc(concert: int, staff: dict[str, Any]) -> int:
    """tpc2 for a concert tpc1 on a staff with Staff.transpose (concert = written + interval)."""
    return concert - fifths_of(staff.get("transposeDiatonic", 0), staff.get("transposeChromatic", 0))


# ------------------------------------------------------------------ reading

def locate(read: dict[str, Any]) -> list[dict[str, Any]]:
    """Turn a bridge Read into addressed objects, in index order per staff and bar."""
    division = read["division"]
    bars = {b["bar"]: b for b in read["bars"]}
    out: list[dict[str, Any]] = []
    for block in read["content"]:
        staff, bar = block["staff"], block["bar"]
        bar_tick = bars[bar]["tick"]
        raw = list(enumerate(block["objects"]))
        raw.sort(key=lambda item: (
            item[1]["tick"], KIND_ORDER[item[1]["kind"]], item[1]["track"], item[1].get("verse", 0), item[0],
        ))
        for index, (ordinal, obj) in enumerate(raw):
            item = present(obj, staff, bar, bar_tick, division)
            item["index"] = index
            item["_ref"] = {"staff": staff, "bar": bar, "raw": ordinal, "type": obj["type"], "tick": obj["tick"]}
            out.append(item)
    return out


def present(obj: dict[str, Any], staff: int, bar: int, bar_tick: int, division: int) -> dict[str, Any]:
    """One object as query_score reports it (before and after views use it too)."""
    ticks = obj["tick"] - bar_tick
    kind = obj["kind"]
    item: dict[str, Any] = {
        "staff": staff, "bar": bar, "type": kind, "position": to_units(ticks, division), "ticks": ticks,
        "msType": obj["type"],
    }
    if staff != SYSTEM_STAFF:
        item["voice"] = obj["track"] % 4 + 1
    item["hidden"] = not obj.get("visible", True)
    if obj.get("offsetX"):
        item["dx"] = dx_units(obj["offsetX"])
    if obj.get("offsetY"):
        item["dy"] = dy_units(obj["offsetY"])
    if kind == "NoteRest":
        item["duration"] = to_units(obj["duration"], division)
        item["durationTicks"] = obj["duration"]
        item["rest"] = obj["type"] != "Chord"
        item["cueSize"] = bool(obj.get("small"))
        item["beam"] = obj.get("beamMode", 0)
        if obj.get("inTuplet"):
            item["inTuplet"] = True
        if not item["rest"]:
            item["stemDirection"] = obj.get("stemDirection", STEM_AUTO)
            item["notes"] = [
                {"pitch": n["pitch"], "tpc1": n["tpc1"], "tpc2": n["tpc2"], "tied": n["tieForward"],
                 "tiedBack": n["tieBack"], "bracketed": n["parentheses"] != 0}
                for n in obj.get("notes", [])
            ]
    elif kind == "LyricItem":
        item.update(text=obj.get("text"), verse=obj.get("verse", 0) + 1, syllabic=obj.get("syllabic"))
        if obj.get("lyricTicks"):
            item["duration"] = to_units(obj["lyricTicks"], division)
    elif kind == "Text":
        item["text"] = obj.get("text")
    elif kind == "Tuplet":
        item.update(actualNotes=obj.get("actualNotes"), normalNotes=obj.get("normalNotes"),
                    duration=to_units(obj["duration"], division))
    elif kind == "Line":
        item["lineType"] = LINE_TYPES.get(obj["type"], obj["type"])
        item["duration"] = to_units(obj.get("duration") or 0, division)
    elif kind == "KeySignature":
        item.update(concertKey=obj.get("concertKey"), writtenKey=obj.get("actualKey"))
    elif kind == "TimeSignature":
        item.update(numerator=obj.get("numerator"), denominator=obj.get("denominator"))
    elif kind == "Clef":
        item["clefType"] = obj.get("clefType")
    return item


def props(item: dict[str, Any]) -> dict[str, Any]:
    """An object's values under query.py's (Sibelius) property names."""
    out: dict[str, Any] = {
        "Type": item["type"], "Position": item["position"], "Hidden": item["hidden"],
        "Dx": item.get("dx", 0), "Dy": item.get("dy", 0),
    }
    if "voice" in item:
        out["VoiceNumber"] = item["voice"]
    if "duration" in item:
        out["Duration"] = item["duration"]
    if "text" in item:
        out["Text"] = item["text"]
    if item["type"] == "NoteRest":
        out.update(CueSize=item["cueSize"], Beam=item["beam"], NoteCount=len(item.get("notes", [])))
        if not item["rest"]:
            out["StemFlipped"] = item["stemDirection"] != STEM_AUTO
    if item["type"] == "TimeSignature":
        out.update(Numerator=item["numerator"], Denominator=item["denominator"])
    return out


def _matches_type(item: dict[str, Any], wanted: str) -> bool:
    if wanted in {item["type"], item["msType"], item.get("lineType")}:
        return True
    if item["type"] == "NoteRest" and wanted in {"Note", "Chord", "Rest"}:
        return item["rest"] == (wanted == "Rest")
    return False


def _holds(item: dict[str, Any], values: dict[str, Any], condition: dict[str, Any]) -> bool:
    prop, op, value = condition["prop"], condition["op"], condition["value"]
    if prop in {"Pitch", "Bracketed"}:
        key = "pitch" if prop == "Pitch" else "bracketed"
        return any(_compare(n[key], op, value) for n in item.get("notes", []))
    if prop not in values:
        return op == "!="
    return _compare(values[prop], op, value)


def _compare(actual: Any, op: str, value: Any) -> bool:
    try:
        return {
            "=": actual == value, "!=": actual != value, ">": actual > value,
            "<": actual < value, ">=": actual >= value, "<=": actual <= value,
        }[op]
    except TypeError:
        return False


def query(objects: list[dict[str, Any]], selector: dict[str, Any]) -> dict[str, Any]:
    """Filter located objects with a query.build_selector selector.

    The system staff (0) is only included when asked for by staff.
    """
    staves = set(selector.get("staves") or [])
    types = selector.get("types") or []
    voice = selector.get("voice") or 0
    first, last = selector.get("fromBar"), selector.get("toBar")
    found = []
    for item in objects:
        if staves and item["staff"] not in staves:
            continue
        if not staves and item["staff"] == SYSTEM_STAFF:
            continue
        if first is not None and item["bar"] < first or last is not None and item["bar"] > last:
            continue
        if types and not any(_matches_type(item, t) for t in types):
            continue
        if voice and item.get("voice") != voice:
            continue
        values = props(item)
        if not all(_holds(item, values, c) for c in selector.get("where", [])):
            continue
        out = public(item)
        for field in selector.get("fields", []):
            if field in values:
                out[field] = values[field]
        found.append(out)
    limit = selector.get("limit", len(found))
    return {"objects": found[:limit], "count": len(found), "truncated": len(found) > limit}


def public(item: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in item.items() if not k.startswith("_")}


# ------------------------------------------------------------------ batches

def prepare_batch(
    operations: Any,
    objects: list[dict[str, Any]],
    staves: list[dict[str, Any]],
    division: int,
    digests: dict[tuple[int, int], str],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Validate a batch against a fresh read; return (primitives, digests of touched bars)."""
    try:
        normalized = batch_ops.validate_batch(operations)
    except batch_ops.BatchError as exc:
        raise MuseScoreBatchError(str(exc)) from exc
    for i, operation in enumerate(normalized):
        if operation["op"] in NOT_YET:
            raise MuseScoreBatchError(
                f"op {i}: {operation['op']} is not available on MuseScore yet "
                f"(milestone {NOT_YET[operation['op']]} of docs/musescore-backend-plan.md)"
            )
    by_address = {(o["staff"], o["bar"], o["index"]): o for o in objects}
    by_staff = {s["staff"]: s for s in staves}
    primitives: list[dict[str, Any]] = []
    touched: set[tuple[int, int]] = set()
    for i, (original, operation) in enumerate(zip(operations, normalized)):
        label = f"op {i}"
        if operation["op"] == "beam":
            made = _beam(operation, label, by_address, objects)
        else:
            target = _target(original, operation, label, by_address)
            if "spelling" in original:  # set-pitch's optional spelling, which validate_batch drops
                operation = {**operation, "spelling": original["spelling"]}
            made = [_addressed(operation, label, target, by_staff, division)]
        for primitive in made:
            primitive["label"] = label
            touched.add((primitive["ref"]["staff"], primitive["ref"]["bar"]))
            primitives.append(primitive)
    return primitives, {f"{staff}:{bar}": digests[(staff, bar)] for staff, bar in sorted(touched)}


def _target(
    original: dict[str, Any], operation: dict[str, Any], label: str,
    by_address: dict[tuple[int, int, int], dict[str, Any]],
) -> dict[str, Any]:
    address = (operation["staff"], operation["bar"], operation["index"])
    item = by_address.get(address)
    if item is None:
        raise MuseScoreBatchError(f"{label}: nothing at staff {address[0]} bar {address[1]} index {address[2]}")
    if "type" in operation and not _matches_type(item, operation["type"]):
        raise MuseScoreBatchError(f"{label}: the object there is a {item['type']} ({item['msType']}), "
                                  f"not a {operation['type']}")
    if "position" in operation and item["position"] != operation["position"]:
        raise MuseScoreBatchError(f"{label}: the object there is at position {item['position']}, "
                                  f"not {operation['position']}")
    if "ticks" in original and item["ticks"] != original["ticks"]:
        raise MuseScoreBatchError(f"{label}: the object there is at tick {item['ticks']}, not {original['ticks']}")
    if "pitch" in original and not any(n["pitch"] == original["pitch"] for n in item.get("notes", [])):
        raise MuseScoreBatchError(f"{label}: the object there has no note of pitch {original['pitch']}")
    return item


def _chord(item: dict[str, Any], op: str, label: str) -> None:
    if item["type"] != "NoteRest" or item["rest"]:
        raise MuseScoreBatchError(f"{label}: {op} needs a chord, not a {item['msType']}")


def _addressed(
    operation: dict[str, Any], label: str, item: dict[str, Any],
    by_staff: dict[int, dict[str, Any]], division: int,
) -> dict[str, Any]:
    op = operation["op"]
    out: dict[str, Any] = {"op": op, "ref": item["_ref"]}
    if op == "set":
        out.update(_set(operation["prop"], operation["value"], item, label, division))
    elif op == "set-pitch":
        _chord(item, op, label)
        pitches = [n["pitch"] for n in item["notes"]]
        old, new = operation["oldPitch"], operation["newPitch"]
        if old not in pitches:
            raise MuseScoreBatchError(f"{label}: no note with pitch {old}; the chord has {pitches}")
        if new in pitches:
            raise MuseScoreBatchError(f"{label}: the chord already has a note of pitch {new}")
        spelling = operation.get("spelling")
        try:
            letter = intervals.spelling_letter(new, spelling if isinstance(spelling, str) and spelling else None)
        except ValueError as exc:
            raise MuseScoreBatchError(f"{label}: {exc}") from exc
        concert = tpc(letter, intervals.alteration(new, letter))
        out.update(oldPitch=old, pitch=new, tpc1=concert, tpc2=written_tpc(concert, by_staff[item["staff"]]))
    elif op in {"tie", "bracket"}:
        _chord(item, op, label)
        out["on"] = operation["tied" if op == "tie" else "bracketed"]
    elif op == "flip-stem":
        _chord(item, op, label)
    elif op == "nudge":
        out.update(dx=operation["dx"] / 32, dy=-operation["dy"] / 32)
    return out


def _set(prop: str, value: Any, item: dict[str, Any], label: str, division: int) -> dict[str, Any]:
    """A Sibelius-named property write as a MuseScore one."""
    kind = item["type"]
    if prop == "Dx":
        return {"prop": "offsetX", "value": value / 32}
    if prop == "Dy":
        return {"prop": "offsetY", "value": -value / 32}
    if prop == "Hidden":
        return {"prop": "visible", "value": not value}
    if prop == "CueSize":
        return {"prop": "small", "value": value}
    if kind == "NoteRest" and prop == "Beam":
        if not 0 <= value <= MAX_BEAM_MODE:
            raise MuseScoreBatchError(f"{label}: Beam is a MuseScore beam mode, 0-{MAX_BEAM_MODE} "
                                      "(0 auto, 1 none, 2 begin, 5 middle)")
        return {"prop": "beamMode", "value": value}
    if kind == "NoteRest" and prop == "RestPosition":
        if not item["rest"]:
            raise MuseScoreBatchError(f"{label}: RestPosition is for rests")
        # Staff positions (half spaces), up positive; offsetY is in spaces, down positive.
        return {"prop": "offsetY", "value": -value / 2}
    if kind in {"LyricItem", "Text"} and prop == "Text":
        return {"prop": "text", "value": value}
    if kind == "LyricItem" and prop == "Duration":
        return {"prop": "lyricTicks", "ticks": to_ticks(value, division, label)}
    if kind == "Line" and prop == "Duration":
        if value < 1:
            raise MuseScoreBatchError(f"{label}: a line's Duration must be positive")
        return {"prop": "spannerTicks", "ticks": to_ticks(value, division, label)}
    if kind == "LyricItem" and prop == "NumNotes":
        raise MuseScoreBatchError(f"{label}: MuseScore measures a melisma in time: set Duration instead of NumNotes")
    raise MuseScoreBatchError(f"{label}: {prop} is not writable on a {kind} in MuseScore")


def _beam(
    operation: dict[str, Any], label: str,
    by_address: dict[tuple[int, int, int], dict[str, Any]], objects: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Beam NoteRests firstIndex..lastIndex: begin, then middle; break after the last."""
    staff, bar = operation["staff"], operation["bar"]
    span = []
    for index in range(operation["firstIndex"], operation["lastIndex"] + 1):
        item = by_address.get((staff, bar, index))
        if item is None:
            raise MuseScoreBatchError(f"{label}: nothing at staff {staff} bar {bar} index {index}")
        span.append(item)
    if span[0]["type"] != "NoteRest" or span[-1]["type"] != "NoteRest":
        raise MuseScoreBatchError(f"{label}: beam endpoints must be NoteRests")
    voice = span[0]["voice"]
    chords = [o for o in span if o["type"] == "NoteRest" and o["voice"] == voice]
    if len(chords) < 2:
        raise MuseScoreBatchError(f"{label}: a beam needs at least two NoteRests in one voice")
    out = [{"op": "set", "ref": chords[0]["_ref"], "prop": "beamMode", "value": BEAM_BEGIN}]
    out += [{"op": "set", "ref": o["_ref"], "prop": "beamMode", "value": BEAM_MID} for o in chords[1:]]
    following = [
        o for o in objects
        if o["staff"] == staff and o["bar"] == bar and o["type"] == "NoteRest" and o.get("voice") == voice
        and o["position"] > chords[-1]["position"]
    ]
    if following and following[0]["beam"] in {0, BEAM_MID}:
        out.append({"op": "set", "ref": following[0]["_ref"], "prop": "beamMode", "value": BEAM_BEGIN})
    return out
