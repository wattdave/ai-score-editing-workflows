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

import re
from fractions import Fraction
from typing import Any

from ai_score_editing.core import batch_schema, intervals
from ai_score_editing.core.errors import BatchError
from ai_score_editing.core.units import UNITS_PER_QUARTER  # noqa: F401

from ai_score_editing.core import query as core_query
from ai_score_editing.core.query import Vocabulary

SYSTEM_STAFF = 0

#: Properties `set` may write, with the JSON type each takes (see _set below).
WRITABLE: dict[str, type] = {
    "Dx": int, "Dy": int, "Hidden": bool, "CueSize": bool,
    "Beam": int, "RestPosition": int, "Text": str, "Duration": int, "NumNotes": int,
}

# Order of objects at one tick (docs/musescore-backend-plan.md, Addresses):
# clefs, key and time signatures, annotations, tuplets before the chords
# they hold, chords and rests by voice, lyrics by verse, then lines.
KIND_ORDER = {
    "Clef": 0, "KeySignature": 1, "TimeSignature": 2, "Text": 3,
    "Tuplet": 4, "GraceNote": 5, "NoteRest": 6, "LyricItem": 7, "Line": 8,
}
#: MuseScore NoteType for grace notes (engraving/types/types.h).
GRACE_TYPES = {
    1: "acciaccatura", 2: "appoggiatura", 4: "grace4", 8: "grace16", 16: "grace32",
    32: "grace8-after", 64: "grace16-after", 128: "grace32-after",
}
#: MuseScore spanner names as line types, where Sibelius's name differs.
LINE_TYPES = {"HairPin": "Hairpin"}

#: MuseScore BeamMode: AUTO 0, NONE 1, BEGIN 2, BEGIN16 3, BEGIN32 4, MID 5, END 6.
BEAM_BEGIN, BEAM_MID, MAX_BEAM_MODE = 2, 5, 6
#: Direction: AUTO 0, UP 1, DOWN 2.
STEM_AUTO = 0
#: hasParentheses: 0 none, 3 both sides (1 and 2 hit an assertion on notes).
PARENTHESES = 3

#: Ops that name an existing object (staff/bar/index); they run first.
OBJECT_OPS = {"set", "set-pitch", "tie", "bracket", "flip-stem", "nudge", "delete", "beam"}
#: Dorico's note ops, which the Sibelius batch format does not have. The
#: ones in NOTE_OPS are addressed at a note or rest, as on Dorico.
NOTE_OPS = {"add-dynamic", "set-articulation", "add-slur", "add-tempo", "add-rehearsal-mark"}
DORICO_OPS = {"add-rest", "add-tuplet", "add-clef"} | NOTE_OPS
#: Ops that add objects; they come after every OBJECT_OPS op in a batch.
ADDING_OPS = batch_schema.ADDING | DORICO_OPS
#: Valid batch operations the MuseScore back end does not do yet, with the
#: milestone of docs/musescore-backend-plan.md that adds them.
NOT_YET: dict[str, int] = {}
#: Ops that change bars or the whole score; batch_ops puts them last.
STRUCTURAL_OPS = batch_schema.STRUCTURAL
#: Structural ops that move or re-bar what follows; ops that name objects by
#: ref (transpose, delete-voice) cannot come after them in a batch.
REBARRING = {"set-time", "add-bars", "delete-bars"}

#: set-barline names as MuseScore BarLineType values (types.h, 4.7.5);
#: start_repeat and end_repeat are the bar's repeat flags instead.
BARLINE_TYPES = {"normal": 1, "none": 1, "double": 2, "dashed": 0x10, "final": 0x20, "dotted": 0x80,
                 "thick": 0x200, "invisible": 1, "start_repeat": None, "end_repeat": None}
#: set-barline types MuseScore has no barline for.
BARLINES_REFUSED = {"between_staves", "tick", "short", "triple"}
#: set-time symbols as TimeSigType: FOUR_FOUR 1, ALLA_BREVE 2.
TIME_SYMBOL_TYPES = {(4, 4): 1, (2, 2): 2}
#: KeyMode: MAJOR 1, MINOR 2.
KEY_MODES = {True: 1, False: 2}
#: set-layout page sizes in millimetres (portrait); the other Sibelius sizes
#: have no agreed dimensions here and are refused.
PAGE_SIZES_MM = {
    "letter": (215.9, 279.4), "legal": (215.9, 355.6), "tabloid": (279.4, 431.8),
    "executive": (184.15, 266.7), "statement": (139.7, 215.9), "a3": (297, 420), "a4": (210, 297),
    "a5": (148, 210), "b4": (250, 353), "b5": (176, 250), "concert": (228.6, 304.8),
    "9.5x12.5": (241.3, 317.5), "10x13": (254, 330.2),
}
MM_PER_INCH = 25.4

#: add-text styles as MuseScore element types; other text.staff.* styles
#: make staff text, every text.system.* style system text (add-tempo makes
#: tempo marks, which change playback).
TEXT_ELEMENTS = {"text.staff.expression": "EXPRESSION"}
#: add-line kinds: Sibelius style ids, and Dorico's line names.
LINE_STYLES = {
    "line.staff.slur.up": "slur", "line.staff.slur.down": "slur", "line.staff.slur": "slur",
    "line.staff.octava.plus8": "8va", "line.staff.octava.minus8": "8vb",
    "line.staff.hairpin.crescendo": "hairpin",
}
#: Lines refused, and why (docs/musescore.md).
LINES_REFUSED = {
    "line.staff.hairpin": "only crescendo hairpins are tested (line.staff.hairpin.crescendo); "
                          "add a diminuendo by hand",
}
#: set-articulation names and the MuseScore actions that add them to a
#: selected note [seen]. The actions toggle; the bridge checks the result.
ARTICULATION_ACTIONS = {"staccato": "add-staccato", "tenuto": "add-tenuto", "marcato": "add-marcato",
                        "accent": "add-sforzato"}
#: Dorico's dynamics as MuseScore DynamicType values (types.h, 4.7.5).
DYNAMIC_TYPES = {
    "pppp": 3, "ppp": 4, "pp": 5, "p": 6, "mp": 7, "mf": 8, "f": 9, "ff": 10, "fff": 11, "ffff": 12,
    "fp": 15, "sf": 17, "sfz": 18, "sfp": 23, "rfz": 25, "fz": 27,
}
_DYNAMIC_SYMBOLS = {"p": "dynamicPiano", "m": "dynamicMezzo", "f": "dynamicForte", "s": "dynamicSforzando",
                    "z": "dynamicZ", "r": "dynamicRinforzando"}
#: add-clef names as MuseScore ClefType values (types.h, 4.7.5).
CLEF_TYPES = {"treble": 0, "treble-8vb": 2, "treble-8va": 3, "alto": 10, "tenor": 11, "bass": 20,
              "bass-8vb": 22, "percussion": 29}
#: Lyric syllabic values: SINGLE 0, BEGIN 1, END 2, MIDDLE 3 [src].
MAX_TUPLET = 32


class MuseScoreBatchError(BatchError):
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
    elif kind == "GraceNote":
        item["duration"] = to_units(obj["duration"], division)
        item["graceType"] = GRACE_TYPES.get(obj.get("noteType"), obj.get("noteType"))
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


#: The properties props() reports, which where clauses and `fields` may name, with their value types.
VOCABULARY = Vocabulary(
    properties={
        "Type": str, "Position": int, "Hidden": bool, "Dx": int, "Dy": int, "VoiceNumber": int,
        "Duration": int, "Text": str, "CueSize": bool, "Beam": int, "NoteCount": int, "StemFlipped": bool,
        "Numerator": int, "Denominator": int, "Pitch": int, "Bracketed": bool,
    },
    fields=frozenset({
        "Type", "Position", "Hidden", "Dx", "Dy", "VoiceNumber", "Duration", "Text", "CueSize", "Beam",
        "NoteCount", "StemFlipped", "Numerator", "Denominator",
    }),
)


def build_selector(**kwargs: Any) -> dict[str, Any]:
    """core.query.build_selector with MuseScore's vocabulary (same keyword arguments)."""
    return core_query.build_selector(vocabulary=VOCABULARY, **kwargs)


def resolve_staves(requested: list[str], staves: list[dict[str, Any]]) -> list[int]:
    """Staff numbers or part names (case-insensitive) as staff numbers; 0 or "system" is the system staff."""
    return core_query.resolve_staves(
        requested, staves, number_key="staff", name_keys=("partName", "shortName"), error=MuseScoreBatchError,
    )


def _matches_type(item: dict[str, Any], wanted: str) -> bool:
    if wanted in {item["type"], item["msType"], item.get("lineType")}:
        return True
    if item["type"] == "NoteRest" and wanted in {"Note", "Chord", "Rest"}:
        return item["rest"] == (wanted == "Rest")
    return False


def _holds(item: dict[str, Any], values: dict[str, Any], condition: dict[str, Any]) -> bool:
    # Pitch and Bracketed match if any note of the chord does.
    notes = item.get("notes", [])
    multi = {"Pitch": [n["pitch"] for n in notes], "Bracketed": [n["bracketed"] for n in notes]}
    return core_query.holds(values, condition, multi)


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
    bars: list[dict[str, Any]] | None = None,
    structure: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, str], dict[str, Any] | None]:
    """Validate a batch against a fresh read; return (primitives, digests of touched bars, copy).

    Object ops name what was read and run first; adding ops place new
    objects by staff, bar, position and voice and run after them, in batch
    order; ties asked for by add-note run once every note exists, before
    any structural op; structural ops come last. copy says what a
    copy-passage copies before the batch opens (None without one).
    """
    try:
        normalized = batch_schema.validate_batch(operations, EXTRA_OPS, WRITABLE)
    except BatchError as exc:
        raise MuseScoreBatchError(str(exc)) from exc
    first_adding = rebarred = numbered = None
    for i, operation in enumerate(normalized):
        op = operation["op"]
        if op in NOT_YET:
            raise MuseScoreBatchError(
                f"op {i}: {op} is not available on MuseScore yet "
                f"(milestone {NOT_YET[op]} of docs/musescore-backend-plan.md)"
            )
        if op in ADDING_OPS and first_adding is None:
            first_adding = i
        elif op in OBJECT_OPS and first_adding is not None:
            raise MuseScoreBatchError(
                f"op {i} ({op}) comes after op {first_adding} ({normalized[first_adding]['op']}); "
                "ops that change objects by index must come before ops that add objects"
            )
        if op in {"transpose", "delete-voice"} and (first_adding is not None or rebarred is not None):
            earlier = first_adding if rebarred is None else rebarred
            raise MuseScoreBatchError(
                f"op {i} ({op}) changes notes as read, and op {earlier} ({normalized[earlier]['op']}) "
                "adds notes or moves bars first; send it as its own batch, or before them"
            )
        if op == "set-time" and numbered is not None:
            raise MuseScoreBatchError(
                f"op {i} (set-time) comes after op {numbered} (set-bar-number); re-barring replaces the "
                "bars after it, so set-time must come first"
            )
        if op == "set-bar-number" and numbered is None:
            numbered = i
        if op in REBARRING and rebarred is None:
            rebarred = i
    if sum(o["op"] == "delete-bars" for o in normalized) > 1:
        raise MuseScoreBatchError("one delete-bars per batch: it selects its range before the batch opens")
    if sum(o["op"] == "copy-passage" for o in normalized) > 1:
        raise MuseScoreBatchError("one copy-passage per batch: it goes through the clipboard")
    by_address = {(o["staff"], o["bar"], o["index"]): o for o in objects}
    by_staff = {s["staff"]: s for s in staves}
    bar_info = {b["bar"]: b for b in bars or []}
    primitives: list[dict[str, Any]] = []
    ties: list[dict[str, Any]] = []
    touched: set[tuple[int, int]] = set()
    copy: dict[str, Any] | None = None
    for i, (original, operation) in enumerate(zip(operations, normalized)):
        label = f"op {i}"
        op = operation["op"]
        if op in STRUCTURAL_OPS and ties:
            primitives += ties  # ties join notes added before the bars move
            ties = []
        if op == "beam":
            made = _beam(operation, label, by_address, objects)
        elif op == "ficta":
            made = _ficta(operation, label, _target(original, operation, label, by_address))
        elif op in NOTE_OPS:
            target = _target(original, operation, label, by_address)
            made = [_note_op(original, operation, label, target, objects, bar_info, division)]
        elif op in ADDING_OPS:
            made = _adding(original, operation, label, by_staff, bar_info, division, objects)
        elif op == "copy-passage":
            copy, made = _copy_passage(operation, label, by_staff, bar_info, division)
        elif op in STRUCTURAL_OPS:
            made = _structural(original, operation, label, objects, staves, bar_info, division, structure)
        else:
            target = _target(original, operation, label, by_address)
            if "spelling" in original:  # set-pitch's optional spelling, which validate_batch drops
                operation = {**operation, "spelling": original["spelling"]}
            made = [_addressed(operation, label, target, by_staff, division)]
        for primitive in made:
            primitive["label"] = label
            where = primitive.get("ref") or primitive.get("at")
            if where:
                touched.add((where["staff"], where["bar"]))
            (ties if primitive["op"] == "tie-at" else primitives).append(primitive)
    primitives += ties
    if not primitives:
        raise MuseScoreBatchError("the batch changes nothing (a transpose or delete-voice range may be empty)")
    digests_out = {f"{staff}:{bar}": digests[(staff, bar)] for staff, bar in sorted(touched)
                   if (staff, bar) in digests}
    return primitives, digests_out, copy


# ------------------------------------------------------------------ structure

def _structural(
    original: dict[str, Any], operation: dict[str, Any], label: str, objects: list[dict[str, Any]],
    staves: list[dict[str, Any]], bar_info: dict[int, dict[str, Any]], division: int,
    structure: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    op = operation["op"]
    last_bar = max(bar_info) if bar_info else 0
    for field in ("bar", "fromBar", "toBar"):
        if field in operation and operation[field] > last_bar and not (op == "add-bars" and field == "bar"):
            raise MuseScoreBatchError(f"{label}: no bar {operation[field]}; the score has {last_bar}")
    if op == "transpose":
        return _transpose(operation, label, objects, {s["staff"]: s for s in staves})
    if op == "delete-voice":
        return _delete_voice(operation, label, objects, staves)
    if op == "set-key":
        return [_set_key(operation, label, staves, bar_info)]
    if op == "set-time":
        primitive = {"op": "set-time", "bar": operation["bar"], "tick": bar_info[operation["bar"]]["tick"],
                     "numerator": operation["numerator"], "denominator": operation["denominator"]}
        if operation["symbol"]:
            primitive["timesigType"] = TIME_SYMBOL_TYPES[(operation["numerator"], operation["denominator"])]
        return [primitive]
    if op == "set-break":
        return [{"op": "set-break", "bar": operation["bar"], "type": operation["type"]}]
    if op == "set-barline":
        kind = operation["type"]
        if kind in BARLINES_REFUSED:
            raise MuseScoreBatchError(f"{label}: MuseScore has no {kind} barline; it has: "
                                      f"{', '.join(sorted(BARLINE_TYPES))}")
        return [{"op": "set-barline", "bar": operation["bar"], "type": kind, "code": BARLINE_TYPES[kind]}]
    if op == "set-bar-number":
        if operation["skip"] and operation["bar"] >= last_bar:
            raise MuseScoreBatchError(f"{label}: skip needs a bar after bar {operation['bar']} to carry the number")
        return [{"op": "set-bar-number", "bar": operation["bar"], "number": operation["number"],
                 "skip": operation["skip"]}]
    if op == "add-bars":
        primitive: dict[str, Any] = {"op": "add-bars", "count": operation["count"]}
        if "bar" in operation:
            if operation["bar"] > last_bar:
                raise MuseScoreBatchError(f"{label}: no bar {operation['bar']} to insert before; leave out "
                                          "bar to add bars at the end")
            primitive["bar"] = operation["bar"]
        if "length" in operation:
            length = Fraction(operation["length"], 4 * UNITS_PER_QUARTER)
            primitive.update(z=length.numerator, n=length.denominator)
        return [primitive]
    if op == "delete-bars":
        if operation["fromBar"] == 1 and operation["toBar"] == last_bar:
            raise MuseScoreBatchError(f"{label}: delete-bars cannot remove every bar of the score")
        # The bridge selects the range before the command opens (see copy-passage).
        first, last = operation["fromBar"], operation["toBar"]
        end = bar_info[last]["tick"] + bar_info[last]["ticks"]
        return [{"op": "delete-bars", "fromBar": first, "toBar": last, "startTick": bar_info[first]["tick"],
                 "endTick": end, "staffStart": 0, "staffEnd": len(staves)}]
    if op == "set-layout":
        return [{"op": "set-style", "values": layout_style(operation, label, (structure or {}).get("style") or {})}]
    if op == "hide-empty-staves":
        if operation["fromBar"] != 1 or operation["toBar"] != last_bar:
            raise MuseScoreBatchError(
                f"{label}: MuseScore hides empty staves for the whole score, not a range of bars; "
                f"use fromBar 1 and toBar {last_bar}"
            )
        return [{"op": "set-style", "values": {"hideEmptyStaves": True}}]
    raise MuseScoreBatchError(f"{label}: {op} is not handled")  # pragma: no cover


def key_fifths(key: str, major: bool) -> int:
    """A key name as sharps (+) or flats (-) in its signature."""
    step, semitones = intervals.parse_note(key)
    letter = intervals.LETTERS[step]
    fifths = _FIFTHS[letter] + 7 * intervals.alteration(semitones, letter)
    return fifths if major else fifths - 3


def written_key(concert: int, staff: dict[str, Any]) -> int:
    """The written key of a concert key on a staff, kept within seven sharps or flats."""
    written = concert - fifths_of(staff.get("transposeDiatonic", 0), staff.get("transposeChromatic", 0))
    while written > 7:
        written -= 12
    while written < -7:
        written += 12
    return written


def _set_key(operation: dict[str, Any], label: str, staves: list[dict[str, Any]],
             bar_info: dict[int, dict[str, Any]]) -> dict[str, Any]:
    concert = key_fifths(operation["key"], operation["major"])
    return {"op": "set-key", "bar": operation["bar"], "tick": bar_info[operation["bar"]]["tick"],
            "mode": KEY_MODES[operation["major"]],
            "staves": [{"staffIdx": s["staff"] - 1, "concertKey": concert, "actualKey": written_key(concert, s)}
                       for s in staves]}


def tpc_name(value: int) -> str:
    """A tonal pitch class as a note name: 14 is C, 20 F#, 12 Bb."""
    letter = "FCGDAEB"[(value + 1) % 7]
    alter = (value + 1) // 7 - 2
    return letter + ("#" * alter if alter > 0 else "b" * -alter)


def _transpose(operation: dict[str, Any], label: str, objects: list[dict[str, Any]],
               by_staff: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    degree, kind = operation["degree"], operation["intervalType"]
    sign = -1 if degree < 0 else 1
    steps = abs(degree)
    semitones = sign * (intervals.REFERENCE_SEMITONES[steps % 7] + 12 * (steps // 7) + kind - 5)
    fifths = fifths_of(degree, semitones)
    out = []
    for item in objects:
        if not (operation["topStaff"] <= item["staff"] <= operation["bottomStaff"]
                and operation["fromBar"] <= item["bar"] <= operation["toBar"]):
            continue
        if item["type"] == "NoteRest" and not item["rest"]:
            notes = []
            for n in item["notes"]:
                try:
                    pitch, letter = intervals.transpose_spelled(tpc_name(n["tpc1"]), n["pitch"], degree, semitones)
                except ValueError as exc:
                    raise MuseScoreBatchError(f"{label}: staff {item['staff']} bar {item['bar']}: {exc}") from exc
                concert = tpc(letter, intervals.alteration(pitch, letter))
                notes.append({"oldPitch": n["pitch"], "pitch": pitch, "tpc1": concert,
                              "tpc2": written_tpc(concert, by_staff[item["staff"]])})
            out.append({"op": "repitch", "ref": item["_ref"], "notes": notes})
        elif item["type"] == "KeySignature" and item.get("concertKey") is not None:
            concert = item["concertKey"] + fifths
            while concert > 7:
                concert -= 12
            while concert < -7:
                concert += 12
            # Replaced, keeping its mode (the bridge cannot edit one in place).
            out.append({"op": "set-key", "bar": item["bar"], "tick": item["_ref"]["tick"], "mode": None,
                        "staves": [{"staffIdx": item["staff"] - 1, "concertKey": concert,
                                    "actualKey": written_key(concert, by_staff[item["staff"]])}]})
    return out


def _delete_voice(operation: dict[str, Any], label: str, objects: list[dict[str, Any]],
                  staves: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every chord in the voice over the bars; and, in voices 2-4, every rest.

    Voice 1 always holds something, so its chords become rests.
    """
    if not any(s["staff"] == operation["staff"] for s in staves):
        raise MuseScoreBatchError(f"{label}: no staff {operation['staff']}")
    voice = operation["voice"]
    return [
        {"op": "delete", "ref": o["_ref"]} for o in objects
        if o["staff"] == operation["staff"] and o.get("voice") == voice and o["type"] == "NoteRest"
        and operation["fromBar"] <= o["bar"] <= operation["toBar"] and (voice > 1 or not o["rest"])
        and not o.get("inTuplet")
    ]


def _copy_passage(operation: dict[str, Any], label: str, by_staff: dict[int, dict[str, Any]],
                  bar_info: dict[int, dict[str, Any]], division: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Copy bars fromBar-toBar of staves top-bottom, before the batch, and paste at the destination."""
    top, bottom, dest = operation["topStaff"], operation["bottomStaff"], operation["destStaff"]
    if bottom not in by_staff or dest + bottom - top not in by_staff:
        raise MuseScoreBatchError(f"{label}: the staves run past the last staff ({max(by_staff)})")
    first, last = bar_info[operation["fromBar"]], bar_info[operation["toBar"]]
    start, end = first["tick"], last["tick"] + last["ticks"]
    if operation["destBar"] not in bar_info:
        raise MuseScoreBatchError(f"{label}: no bar {operation['destBar']}")
    at = _at({"bar": operation["destBar"], "position": operation["destPosition"], "voice": 1}, label,
             bar_info, division, staff=dest)
    final = bar_info[max(bar_info)]
    if at["tick"] + end - start > final["tick"] + final["ticks"]:
        raise MuseScoreBatchError(f"{label}: the passage would run past the last bar; add bars first")
    copy = {"startTick": start, "endTick": end, "staffStart": top - 1, "staffEnd": bottom}
    return copy, [{"op": "paste", "at": at}]


def layout_style(operation: dict[str, Any], label: str, current: dict[str, Any]) -> dict[str, Any]:
    """Sibelius set-layout settings (mm, staff spaces) as MuseScore style values.

    MuseScore keeps page sizes and margins in inches, spatium in 1/1200 inch
    and the stave gaps in staff spaces [seen]; it has no right margin, only a
    printable width, and odd and even pages have margins of their own.
    """
    if "extraSpacesBelowVocalStaves" in operation:
        raise MuseScoreBatchError(f"{label}: MuseScore has no extra gap below vocal staves")
    inch = lambda mm: mm / MM_PER_INCH  # noqa: E731
    values: dict[str, Any] = {}
    width, height = current.get("pageWidth"), current.get("pageHeight")
    if "pageSize" in operation:
        name = batch_schema.PAGE_SIZES[operation["pageSize"]]
        if name not in PAGE_SIZES_MM:
            raise MuseScoreBatchError(f"{label}: page size {name} is not available on MuseScore; use one of "
                                      f"{', '.join(PAGE_SIZES_MM)}")
        width, height = (inch(v) for v in PAGE_SIZES_MM[name])
    if width is None or height is None:
        raise MuseScoreBatchError(f"{label}: the current page size could not be read")
    landscape = width > height
    if "orientation" in operation:
        landscape = batch_schema.ORIENTATIONS[operation["orientation"]] == "landscape"
    if landscape != (width > height):
        width, height = height, width
    if "pageSize" in operation or "orientation" in operation:
        values.update(pageWidth=width, pageHeight=height)
    left = inch(operation["leftMargin"]) if "leftMargin" in operation else current.get("pageOddLeftMargin", 0)
    old_right = (current.get("pageWidth", width) - current.get("pageOddLeftMargin", 0)
                 - current.get("pagePrintableWidth", width))
    right = inch(operation["rightMargin"]) if "rightMargin" in operation else old_right
    if {"leftMargin", "rightMargin", "pageSize", "orientation"} & operation.keys():
        if width - left - right <= 0:
            raise MuseScoreBatchError(f"{label}: the margins leave no room on the page")
        values.update(pageOddLeftMargin=left, pageEvenLeftMargin=left, pagePrintableWidth=width - left - right)
    for field, keys in (("topMargin", ("pageOddTopMargin", "pageEvenTopMargin")),
                        ("bottomMargin", ("pageOddBottomMargin", "pageEvenBottomMargin"))):
        if field in operation:
            values.update({k: inch(operation[field]) for k in keys})
    if "staffSize" in operation:
        # A staff is four spaces; spatium is in 1/1200 inch [seen].
        values["spatium"] = inch(operation["staffSize"] / 4) * 1200
    spaces = lambda mm: mm / (operation["staffSize"] / 4 if "staffSize" in operation  # noqa: E731
                              else current.get("spatium", 1) / 1200 * MM_PER_INCH)
    if "aboveTopStaveGap" in operation:
        values["staffUpperBorder"] = spaces(operation["aboveTopStaveGap"])
    if "belowBottomStaveGap" in operation:
        values["staffLowerBorder"] = spaces(operation["belowBottomStaveGap"])
    if "spacesBetweenStaves" in operation:
        values["staffDistance"] = operation["spacesBetweenStaves"]
    if "spacesBetweenSystems" in operation:
        values["minSystemDistance"] = operation["spacesBetweenSystems"]
    return values


def structure_report(raw: dict[str, Any], staves: list[dict[str, Any]]) -> dict[str, Any]:
    """GetStructure in score_structure's terms (set-key, set-barline, ... names; mm)."""
    names = {v: k for k, v in BARLINE_TYPES.items() if v is not None and k not in {"none", "invisible"}}
    barlines = []
    for b in raw["barlines"]:
        if b["repeatStart"]:
            barlines.append({"bar": b["bar"], "type": "start_repeat"})
        if b["repeatEnd"]:
            barlines.append({"bar": b["bar"], "type": "end_repeat"})
        elif not b["visible"]:
            barlines.append({"bar": b["bar"], "type": "invisible"})
        elif b["barlineType"] != 1:
            barlines.append({"bar": b["bar"], "type": names.get(b["barlineType"], str(b["barlineType"]))})
    keys = []
    for k in raw["keySignatures"]:
        if keys and keys[-1]["bar"] == k["bar"]:
            keys[-1].setdefault("writtenKeys", {})[k["staff"]] = k["actualKey"]
            continue
        major = k["mode"] != 2
        keys.append({"bar": k["bar"], "sharps": k["concertKey"], "major": major,
                     "name": key_name(k["concertKey"], major), "writtenKeys": {k["staff"]: k["actualKey"]}})
    for k in keys:  # only worth listing where a staff is written in another key
        if all(v == k["sharps"] for v in k["writtenKeys"].values()):
            del k["writtenKeys"]
    style = raw["style"]
    mm = lambda inches: round(inches * MM_PER_INCH, 2)  # noqa: E731
    space_mm = style["spatium"] / 1200 * MM_PER_INCH
    layout = {
        "pageWidth": mm(style["pageWidth"]), "pageHeight": mm(style["pageHeight"]),
        "orientation": "landscape" if style["pageWidth"] > style["pageHeight"] else "portrait",
        "staffSize": round(space_mm * 4, 2), "topMargin": mm(style["pageOddTopMargin"]),
        "bottomMargin": mm(style["pageOddBottomMargin"]), "leftMargin": mm(style["pageOddLeftMargin"]),
        "rightMargin": mm(style["pageWidth"] - style["pageOddLeftMargin"] - style["pagePrintableWidth"]),
        "aboveTopStaveGap": round(style["staffUpperBorder"] * space_mm, 2),
        "belowBottomStaveGap": round(style["staffLowerBorder"] * space_mm, 2),
    }
    for name, (w, h) in PAGE_SIZES_MM.items():
        if {round(w, 1), round(h, 1)} == {round(layout["pageWidth"], 1), round(layout["pageHeight"], 1)}:
            layout["pageSize"] = name
    return {
        "timeSignatures": [{"bar": t["bar"], "numerator": t["numerator"], "denominator": t["denominator"],
                            **({"symbol": {1: "common", 2: "cut"}[t["timesigType"]]}
                               if t.get("timesigType") in {1, 2} else {})} for t in raw["timeSignatures"]],
        "keySignatures": keys,
        "barlines": barlines,
        "breaks": raw["breaks"],
        "barNumbers": [{"bar": n["bar"], "skip": True} if n["irregular"] else
                       {"bar": n["bar"], "shownAs": next(b["no"] + 1 for b in raw["bars"] if b["bar"] == n["bar"])}
                       for n in raw["barNumbers"]],
        "irregularBars": [{"bar": b["bar"], "length": to_units(b["ticks"], raw.get("division", 480))}
                          for b in raw["bars"] if _irregular(b, raw)],
        "barCount": raw["barCount"],
        "layout": layout,
        "engraving": {"spacesBetweenStaves": style["staffDistance"],
                      "spacesBetweenSystems": style["minSystemDistance"]},
        "hideEmptyStaves": bool(style["hideEmptyStaves"]),
    }


def _irregular(bar: dict[str, Any], raw: dict[str, Any]) -> bool:
    """A bar shorter or longer than its time signature."""
    current = None
    for t in raw["timeSignatures"]:
        if t["bar"] <= bar["bar"]:
            current = t
    if current is None:
        return False
    return bar["ticks"] * current["denominator"] != 4 * raw.get("division", 480) * current["numerator"]


_KEY_NAMES_MAJOR = ["Cb", "Gb", "Db", "Ab", "Eb", "Bb", "F", "C", "G", "D", "A", "E", "B", "F#", "C#"]
_KEY_NAMES_MINOR = ["Ab", "Eb", "Bb", "F", "C", "G", "D", "A", "E", "B", "F#", "C#", "G#", "D#", "A#"]


def key_name(fifths: int, major: bool) -> str:
    return (_KEY_NAMES_MAJOR if major else _KEY_NAMES_MINOR)[fifths + 7]


# ------------------------------------------------------------------ adding

def _req_int(operation: dict[str, Any], field: str, label: str, minimum: int, maximum: int | None = None,
             default: int | None = None) -> int:
    value = operation.get(field, default)
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum \
            or (maximum is not None and value > maximum):
        bound = f"{minimum}-{maximum}" if maximum is not None else f">= {minimum}"
        raise BatchError(f"{label}.{field} must be an integer {bound}")
    return value


def _req_str(operation: dict[str, Any], field: str, label: str) -> str:
    value = operation.get(field)
    if not isinstance(value, str) or not value.strip():
        raise BatchError(f"{label}.{field} must be a non-empty string")
    return value


def _placed(operation: dict[str, Any], label: str) -> dict[str, Any]:
    """staff (1 up), bar, position and voice of an op that adds at a place."""
    return {"op": operation["op"], "staff": _req_int(operation, "staff", label, 1),
            "bar": _req_int(operation, "bar", label, 1), "position": _req_int(operation, "position", label, 0),
            "voice": _req_int(operation, "voice", label, 1, 4, default=1)}


def _addressed_extra(operation: dict[str, Any], label: str) -> dict[str, Any]:
    """staff/bar/index and guards of a Dorico note op."""
    out = {"op": operation["op"], "staff": _req_int(operation, "staff", label, 1),
           "bar": _req_int(operation, "bar", label, 1), "index": _req_int(operation, "index", label, 0)}
    if "type" in operation:
        out["type"] = _req_str(operation, "type", label)
    if "position" in operation:
        out["position"] = _req_int(operation, "position", label, 0)
    return out


def _validate_rest(operation: dict[str, Any], label: str) -> dict[str, Any]:
    return {**_placed(operation, label), "duration": _req_int(operation, "duration", label, 1)}


def _validate_tuplet(operation: dict[str, Any], label: str) -> dict[str, Any]:
    out = {**_placed(operation, label), "duration": _req_int(operation, "duration", label, 1),
           "actual": _req_int(operation, "actual", label, 2, MAX_TUPLET),
           "normal": _req_int(operation, "normal", label, 1, MAX_TUPLET)}
    if out["actual"] == out["normal"]:
        raise BatchError(f"{label}: actual and normal must differ")
    notes = operation.get("notes")
    if not isinstance(notes, list) or not 1 <= len(notes) <= out["actual"] or not all(
        isinstance(n, list) and all(isinstance(p, int) and not isinstance(p, bool) and 0 <= p <= 127 for p in n)
        for n in notes
    ):
        raise BatchError(
            f"{label}.notes must list up to {out['actual']} chords, each a list of MIDI pitches ([] for a rest)"
        )
    out["notes"] = notes
    return out


def _validate_clef(operation: dict[str, Any], label: str) -> dict[str, Any]:
    clef = _req_str(operation, "clef", label).removeprefix("clef.")
    if clef not in CLEF_TYPES:
        raise BatchError(f"{label}.clef must be one of: {', '.join(CLEF_TYPES)}")
    return {**_placed(operation, label), "clef": clef}


def _validate_note_op(operation: dict[str, Any], label: str) -> dict[str, Any]:
    out = _addressed_extra(operation, label)
    op = operation["op"]
    if op == "add-dynamic":
        dynamic = _req_str(operation, "dynamic", label)
        if dynamic not in DYNAMIC_TYPES:
            raise BatchError(f"{label}.dynamic must be one of: {', '.join(DYNAMIC_TYPES)}")
        out["dynamic"] = dynamic
    elif op == "set-articulation":
        name = _req_str(operation, "articulation", label)
        if name not in ARTICULATION_ACTIONS:
            raise BatchError(
                f"{label}.articulation must be one of: {', '.join(ARTICULATION_ACTIONS)} "
                "(MuseScore's plug-ins can only add these by name)"
            )
        out["articulation"] = name
    elif op == "add-tempo":
        out["text"] = _req_str(operation, "text", label)
        if "bpm" in operation:
            out["bpm"] = _req_int(operation, "bpm", label, 1, 1000)
    elif op == "add-rehearsal-mark" and "text" in operation:
        out["text"] = _req_str(operation, "text", label)
    return out


EXTRA_OPS: batch_schema.ExtraOps = {
    "add-rest": _validate_rest, "add-tuplet": _validate_tuplet, "add-clef": _validate_clef,
    **{op: _validate_note_op for op in NOTE_OPS},
}


def note_value(ticks: int, division: int) -> Fraction | None:
    """ticks as a fraction of a whole note, if it is one note value with up to 3 dots."""
    whole = 4 * division
    base = Fraction(2 * whole)  # a breve
    while base >= 1:
        for dots in range(4):
            if base * (2 - Fraction(1, 2 ** dots)) == ticks:
                return Fraction(ticks, whole)
        base /= 2
    return None


def _length(units: int, division: int, label: str, what: str = "duration") -> tuple[int, Fraction]:
    ticks = to_ticks(units, division, f"{label}.{what}")
    value = note_value(ticks, division)
    if value is None:
        raise MuseScoreBatchError(
            f"{label}.{what} {units} is not a single note value (with up to three dots); "
            "split it into several notes"
        )
    return ticks, value


def _at(operation: dict[str, Any], label: str, bar_info: dict[int, dict[str, Any]], division: int,
        staff: int | None = None, length: int = 0) -> dict[str, Any]:
    """Where an op adds: staff, bar, absolute tick and track; checks the bar holds it."""
    staff = operation["staff"] if staff is None else staff
    bar = bar_info.get(operation["bar"])
    if bar is None:
        raise MuseScoreBatchError(f"{label}: no bar {operation['bar']}")
    ticks = to_ticks(operation["position"], division, f"{label}.position")
    if ticks >= bar["ticks"] or ticks + length > bar["ticks"]:
        raise MuseScoreBatchError(
            f"{label}: bar {operation['bar']} is {to_units(bar['ticks'], division)} long; "
            "an added note or rest cannot cross the barline"
        )
    voice = operation.get("voice", 1)
    real = max(staff, 1)
    return {"staff": staff, "bar": operation["bar"], "tick": bar["tick"] + ticks,
            "track": (real - 1) * 4 + voice - 1}


def _spelled(pitch: int, spelling: Any, staff: dict[str, Any], label: str) -> dict[str, int]:
    try:
        letter = intervals.spelling_letter(pitch, spelling if isinstance(spelling, str) and spelling else None)
    except ValueError as exc:
        raise MuseScoreBatchError(f"{label}: {exc}") from exc
    concert = tpc(letter, intervals.alteration(pitch, letter))
    return {"pitch": pitch, "tpc1": concert, "tpc2": written_tpc(concert, staff)}


def _adding(
    original: dict[str, Any], operation: dict[str, Any], label: str, by_staff: dict[int, dict[str, Any]],
    bar_info: dict[int, dict[str, Any]], division: int, objects: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    op = operation["op"]
    staff = by_staff.get(operation["staff"]) if operation["staff"] != SYSTEM_STAFF else {}
    if staff is None:
        raise MuseScoreBatchError(f"{label}: no staff {operation['staff']}")
    if op == "add-note":
        ticks, value = _length(operation["duration"], division, label)
        spellings = original.get("spellings")
        if spellings is not None and (not isinstance(spellings, list) or len(spellings) != len(operation["pitches"])):
            raise MuseScoreBatchError(f"{label}.spellings must list one spelling (or null) per pitch")
        if len(set(operation["pitches"])) != len(operation["pitches"]):
            raise MuseScoreBatchError(f"{label}.pitches has the same pitch twice")
        # Without a spelling MuseScore spells the note for the key.
        notes = [_spelled(p, s, staff, label) if s else {"pitch": p}
                 for p, s in zip(operation["pitches"], spellings or [None] * len(operation["pitches"]))]
        at = _at(operation, label, bar_info, division, length=ticks)
        out = [{"op": "add-note", "at": at, "ticks": ticks, "z": value.numerator, "n": value.denominator,
                "notes": notes}]
        if operation["tied"]:
            out.append({"op": "tie-at", "at": at, "pitches": operation["pitches"]})
        return out
    if op == "add-rest":
        ticks, value = _length(operation["duration"], division, label)
        at = _at(operation, label, bar_info, division, length=ticks)
        return [{"op": "add-rest", "at": at, "ticks": ticks, "z": value.numerator, "n": value.denominator}]
    if op == "add-tuplet":
        ticks = to_ticks(operation["duration"], division, f"{label}.duration")
        base = Fraction(ticks, operation["normal"])
        if base.denominator != 1 or note_value(int(base), division) is None:
            raise MuseScoreBatchError(
                f"{label}: duration / normal ({operation['duration']} / {operation['normal']}) must be one note value"
            )
        total, unit = Fraction(ticks, 4 * division), Fraction(int(base), 4 * division)
        at = _at(operation, label, bar_info, division, length=ticks)
        return [{"op": "add-tuplet", "at": at, "ticks": ticks, "z": total.numerator, "n": total.denominator,
                 "actual": operation["actual"], "normal": operation["normal"],
                 "baseZ": unit.numerator, "baseN": unit.denominator,
                 "notes": [[{"pitch": p} for p in chord] for chord in operation["notes"]]}]
    if op == "add-clef":
        return [{"op": "add-clef", "at": _at(operation, label, bar_info, division),
                 "clefType": CLEF_TYPES[operation["clef"]]}]
    if op == "add-text":
        system = operation["staff"] == SYSTEM_STAFF
        element = "SYSTEM_TEXT" if system else TEXT_ELEMENTS.get(operation["styleId"], "STAFF_TEXT")
        return [{"op": "add-text", "at": _at(operation, label, bar_info, division), "element": element,
                 "text": operation["text"]}]
    if op == "add-lyric":
        verse = original.get("verse", 1)
        if not isinstance(verse, int) or isinstance(verse, bool) or not 1 <= verse <= 99:
            raise MuseScoreBatchError(f"{label}.verse must be an integer 1-99")
        ticks = to_ticks(operation["duration"], division, f"{label}.duration")
        return [{"op": "add-lyric", "at": _at(operation, label, bar_info, division), "text": operation["text"],
                 "verse": verse - 1, "hyphen": operation["syllableType"] == "middle", "ticks": ticks}]
    if op == "add-line":
        kind = LINE_STYLES.get(operation["styleId"])
        for prefix, reason in LINES_REFUSED.items():
            if kind is None and operation["styleId"].startswith(prefix):
                raise MuseScoreBatchError(f"{label}: {reason}")
        if kind is None:
            raise MuseScoreBatchError(
                f"{label}: MuseScore can add these lines: {', '.join(sorted(LINE_STYLES))}; "
                f"not {operation['styleId']}"
            )
        if operation["duration"] < 1:
            raise MuseScoreBatchError(f"{label}: a line's duration must be positive")
        at = _at(operation, label, bar_info, division)
        return [{"op": "add-line", "at": at, "line": kind,
                 "endTick": at["tick"] + to_ticks(operation["duration"], division, f"{label}.duration")}]
    raise MuseScoreBatchError(f"{label}: {op} is not handled")  # pragma: no cover


#: MuseScore has no ficta. The sign is staff text holding one SMuFL accidental, above the note, and the
#: note's own accidental is hidden, so the pitch and playback are unchanged.
FICTA_SYMBOLS = {"flat": "accidentalFlat", "natural": "accidentalNatural", "sharp": "accidentalSharp"}


def _ficta(operation: dict[str, Any], label: str, item: dict[str, Any]) -> list[dict[str, Any]]:
    """Hide (or show again) a chord's staff accidental and add (or remove) the ficta text above it."""
    _chord(item, "ficta", label)
    at = {"staff": item["staff"], "bar": item["bar"], "tick": item["_ref"]["tick"],
          "track": (item["staff"] - 1) * 4 + item["voice"] - 1}
    # Any ficta text already there goes first, so adding twice leaves one.
    primitives: list[dict[str, Any]] = [{"op": "remove-ficta-text", "at": at}]
    if operation["remove"]:
        return [{"op": "ficta-show", "ref": item["_ref"], "on": True}, *primitives]
    text = f"<sym>{FICTA_SYMBOLS[operation['accidental']]}</sym>"
    return [{"op": "ficta-show", "ref": item["_ref"], "on": False}, *primitives,
            {"op": "add-text", "at": at, "element": "STAFF_TEXT", "text": text}]


def _note_op(
    original: dict[str, Any], operation: dict[str, Any], label: str, item: dict[str, Any],
    objects: list[dict[str, Any]], bar_info: dict[int, dict[str, Any]], division: int,
) -> dict[str, Any]:
    """A Dorico note op at the note or rest it names."""
    op = operation["op"]
    if item["type"] != "NoteRest":
        raise MuseScoreBatchError(f"{label}: {op} needs a note or rest, not a {item['msType']}")
    at = {"staff": item["staff"], "bar": item["bar"], "tick": item["_ref"]["tick"],
          "track": (item["staff"] - 1) * 4 + item["voice"] - 1}
    if op in {"set-articulation", "add-slur"}:
        _chord(item, op, label)
    if op == "add-dynamic":
        text = "".join(f"<sym>{_DYNAMIC_SYMBOLS[c]}</sym>" for c in operation["dynamic"])
        return {"op": "add-dynamic", "at": at, "text": text, "dynamicType": DYNAMIC_TYPES[operation["dynamic"]]}
    if op == "set-articulation":
        return {"op": "articulation", "at": at, "action": ARTICULATION_ACTIONS[operation["articulation"]]}
    if op == "add-slur":
        return {"op": "add-line", "at": at, "line": "slur", "endTick": None}
    if op == "add-tempo":
        bpm = operation.get("bpm") or _bpm_in(operation["text"])
        if bpm is None:
            raise MuseScoreBatchError(
                f"{label}: give bpm (quarter notes per minute) or a text with a metronome mark such as "
                "'q = 120': a MuseScore tempo mark always sets the playback tempo"
            )
        return {"op": "add-tempo", "at": {**at, "track": 0}, "text": _tempo_text(operation["text"]),
                "tempo": bpm / 60}
    # add-rehearsal-mark: the next letter after the marks before it, unless given.
    text = operation.get("text")
    if text is None:
        before = [o for o in objects if o.get("msType") == "RehearsalMark"
                  and (o["bar"], o["position"]) < (item["bar"], item["position"])]
        text = _mark_letter(len(before))
    return {"op": "add-rehearsal-mark", "at": {**at, "track": 0}, "text": text}


_METRONOME = re.compile(r"^\s*(?:q|♩|crotchet|quarter)\s*=\s*(\d+)\s*$", re.IGNORECASE)


def _bpm_in(text: str) -> int | None:
    match = re.search(r"=\s*(\d+)", text)
    return int(match.group(1)) if match else None


def _tempo_text(text: str) -> str:
    """Dorico-style "q = 120" as MuseScore's metronome mark; other text as given."""
    match = _METRONOME.match(text)
    return f"<sym>metNoteQuarterUp</sym> = {match.group(1)}" if match else text


def _mark_letter(count: int) -> str:
    letters = ""
    count += 1
    while count:
        count, rest = divmod(count - 1, 26)
        letters = chr(ord("A") + rest) + letters
    return letters


def _target(
    original: dict[str, Any], operation: dict[str, Any], label: str,
    by_address: dict[tuple[int, int, int], dict[str, Any]],
) -> dict[str, Any]:
    address = (operation["staff"], operation["bar"], operation["index"])
    item = by_address.get(address)
    if item is None:
        raise MuseScoreBatchError(f"{label}: nothing at staff {address[0]} bar {address[1]} index {address[2]}")
    if item["type"] == "GraceNote":
        raise MuseScoreBatchError(f"{label}: grace notes are read-only in MuseScore so far")
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


# ------------------------------------------------------------------ lyrics

SYLLABIC_SINGLE, SYLLABIC_BEGIN, SYLLABIC_END, SYLLABIC_MIDDLE = 0, 1, 2, 3


def lyric_line(objects: list[dict[str, Any]], staff: int, verse: int) -> list[dict[str, Any]]:
    """A staff's syllables of one verse (1-based), in score order across voices."""
    line = [o for o in objects if o["type"] == "LyricItem" and o["staff"] == staff and o["verse"] == verse]
    line.sort(key=lambda o: (o["bar"], o["ticks"], o["voice"]))
    return line


def lyric_text(line: list[dict[str, Any]]) -> str:
    """Syllables as one line of text, hyphenated within words ("ma-king")."""
    out = []
    for syllable in line:
        joined = syllable["syllabic"] in {SYLLABIC_BEGIN, SYLLABIC_MIDDLE}
        out.append((syllable["text"] or "") + ("-" if joined else " "))
    return "".join(out).strip().rstrip("-")


def split_lyrics(text: str) -> list[tuple[str, int]]:
    """Words split by spaces, then hyphens, as (syllable, MuseScore syllabic)."""
    out: list[tuple[str, int]] = []
    for word in text.split():
        parts = [p for p in word.split("-") if p]
        if len(parts) == 1:
            out.append((parts[0], SYLLABIC_SINGLE))
        elif parts:
            out.append((parts[0], SYLLABIC_BEGIN))
            out += [(p, SYLLABIC_MIDDLE) for p in parts[1:-1]]
            out.append((parts[-1], SYLLABIC_END))
    return out


def lyric_edits(line: list[dict[str, Any]], text: str, digests: dict[tuple[int, int], str],
                staff: int, verse: int) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Primitives that make a verse read as text: same syllable count, changed syllables only."""
    new = split_lyrics(text)
    if not line:
        raise MuseScoreBatchError(f"staff {staff} has no lyrics in verse {verse}; add them with add-lyric")
    if len(new) != len(line):
        raise MuseScoreBatchError(
            f"the new text has {len(new)} syllables and staff {staff}'s verse {verse} has {len(line)}; "
            "edit_lyrics keeps each syllable on its note, so the counts must match (use add-lyric or "
            "delete in apply_batch to change them)"
        )
    primitives: list[dict[str, Any]] = []
    for k, (syllable, (word, syllabic)) in enumerate(zip(line, new)):
        label = f"syllable {k + 1} (bar {syllable['bar']})"
        if syllable["text"] != word:
            primitives.append({"op": "set", "ref": syllable["_ref"], "prop": "text", "value": word, "label": label})
        if syllable["syllabic"] != syllabic:
            primitives.append({"op": "set", "ref": syllable["_ref"], "prop": "syllabic", "value": syllabic,
                               "label": label})
    touched = sorted({(p["ref"]["staff"], p["ref"]["bar"]) for p in primitives})
    return primitives, {f"{s}:{b}": digests[(s, b)] for s, b in touched if (s, b) in digests}
