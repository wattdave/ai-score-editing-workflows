"""Queries and batches for Dorico in the Sibelius back end's terms.

Objects are addressed as staff/bar/index, positions are 1/256 of a quarter
note within the bar, pitches are MIDI numbers: the same shapes query_score
and apply_batch use for Sibelius. Underneath, every Dorico event has a
stable id (undo restores it), so an address is resolved to an id from a
fresh read before a batch runs, and bridge.lua checks the id, type,
position and pitch again before it changes anything.
"""

from __future__ import annotations

import re
from typing import Any

from sibelius_websocket_cli.intervals import compute_transposition, parse_note

from .bridge import BarMap

LETTERS = "CDEFGAB"
NATURAL = [0, 2, 4, 5, 7, 9, 11]
REFERENCE_SEMITONES = [0, 2, 4, 5, 7, 9, 11]
#: Spelling for a pitch class when none is given.
DEFAULT_SPELLING = {0: "C", 1: "C#", 2: "D", 3: "Eb", 4: "E", 5: "F", 6: "F#", 7: "G", 8: "Ab", 9: "A", 10: "Bb", 11: "B"}

TYPE_ALIASES: dict[str, set[str]] = {
    "NoteRest": {"NoteEvent", "GraceNoteEvent", "RestEvent", "BarRestEvent"},
    "Note": {"NoteEvent", "GraceNoteEvent"},
    "Rest": {"RestEvent", "BarRestEvent"},
    "Text": {"TextEvent"},
    "Clef": {"ClefEvent"},
    "TimeSignature": {"BarDivisionEvent"},
    "KeySignature": {"TonalityDivisionEvent"},
    "Tuplet": {"TupletEvent"},
    "Dynamic": {"DynamicGroupEvent"},
    "Octave": {"OttavaLineEvent"},
    "Break": {"BreakEvent"},
}
WHERE_FIELDS = {
    "Pitch": "pitch", "Position": "position", "FlowPosition": "flowPosition", "Duration": "duration",
    "Voice": "voice", "Type": "type", "Text": "text", "Name": "name", "Id": "id", "Bar": "bar", "Staff": "staff",
}
_WHERE = re.compile(r"^\s*(\w+)\s*(>=|<=|!=|=|>|<)\s*(.+?)\s*$")
ADDRESSED = {"set-pitch", "delete"}
ADDING = {"add-note", "add-rest", "add-text", "add-clef"}
#: Clef library entities in a new Dorico project (score.libraries.clefs).
CLEFS = {"treble", "bass", "percussion", "tab", "tab.4"}
#: Ops that run as Dorico commands, one undo step each, so they cannot share
#: a batch with the Lua ops (one batch, one undo step).
COMMAND_OPS = {"set-break", "add-lyrics", "set-time", "set-key", "set-barline"}
#: Popover definitions Dorico's create commands take (logged from the popovers).
BARLINE_DEFINITIONS = {"double": "||", "final": "|]", "start_repeat": "|:", "end_repeat": ":|"}
MAJOR_KEYS = {"C", "G", "D", "A", "E", "B", "F#", "C#", "F", "Bb", "Eb", "Ab", "Db", "Gb", "Cb"}
MINOR_KEYS = {"A", "E", "B", "F#", "C#", "G#", "D#", "A#", "D", "G", "C", "F", "Bb", "Eb", "Ab"}
#: Characters a command parameter cannot carry (untested or line-based).
UNSAFE_PARAMETER = set("\\\n\r")


def command_value(text: str) -> str:
    """A value for a Dorico command parameter.

    Dorico splits parameters on "&" and also on ",", and does not URL-decode,
    but a backslash escapes either: "well\\," arrives as "well,", "rock\\&roll"
    as "rock&roll" (checked 2026-09-27). Backslashes and line breaks are refused.
    """
    if UNSAFE_PARAMETER & set(text):
        raise DoricoBatchError(f"{text!r} cannot contain a backslash or a line break")
    return text.replace(",", "\\,").replace("&", "\\&")
OPERATIONS = ADDRESSED | ADDING | COMMAND_OPS | {"transpose"}
BREAK_TYPES = {"system", "none"}


class DoricoBatchError(ValueError):
    """A query or batch cannot be run against this score."""


# ------------------------------------------------------------------ spelling

def spelling_letter(pitch: int, spelling: str | None = None) -> str:
    """The letter name to spell `pitch` with, checking an explicit spelling fits."""
    name = spelling or DEFAULT_SPELLING[pitch % 12]
    try:
        step, semitones = parse_note(name)
    except ValueError as exc:
        raise DoricoBatchError(str(exc)) from exc
    if semitones != pitch % 12:
        raise DoricoBatchError(f"spelling {name} does not match MIDI pitch {pitch}")
    return LETTERS[step]


def _alteration(pitch: int, letter: str) -> int:
    return (pitch % 12 - NATURAL[LETTERS.index(letter)] + 6) % 12 - 6


def transpose_spelled(name: str | None, pitch: int, steps: int, semitones: int) -> tuple[int, str]:
    """(new pitch, new letter) for a note moved by diatonic steps and semitones."""
    new_pitch = pitch + semitones
    if not 0 <= new_pitch <= 127:
        raise DoricoBatchError(f"transposing {pitch} by {semitones} leaves the MIDI range")
    if not name:
        return new_pitch, spelling_letter(new_pitch)
    letter = LETTERS[(LETTERS.index(name[0]) + steps) % 7]
    if abs(_alteration(new_pitch, letter)) > 2:
        raise DoricoBatchError(f"{name} transposed would need more than a double accidental")
    return new_pitch, letter


def interval_of(operation: dict[str, Any], label: str) -> tuple[int, int]:
    """(signed diatonic steps, signed semitones) for a transpose operation."""
    if "semitones" in operation:
        semitones = _int(operation, "semitones", label, -36, 36)
        steps = operation.get("steps")
        if steps is None:
            steps = round(semitones * 7 / 12)
        elif not isinstance(steps, int) or isinstance(steps, bool):
            raise DoricoBatchError(f"{label}.steps must be an integer")
        return steps, semitones
    direction = operation.get("direction")
    if direction not in {"up", "down"}:
        raise DoricoBatchError(f"{label}.direction must be 'up' or 'down'")
    octaves = _int({"octaves": 0, **operation}, "octaves", label, 0, 2)
    try:
        degree, interval_type = compute_transposition(
            _str(operation, "fromNote", label), _str(operation, "toNote", label), direction == "up"
        )
    except (KeyError, ValueError) as exc:
        raise DoricoBatchError(f"{label}: {exc}") from exc
    sign = 1 if direction == "up" else -1
    semitones = REFERENCE_SEMITONES[abs(degree)] + interval_type - 5
    return degree + 7 * octaves * sign, sign * (semitones + 12 * octaves)


# ------------------------------------------------------------------ reading

def locate_events(events: list[dict[str, Any]], bars: BarMap) -> list[dict[str, Any]]:
    """Add bar, in-bar position and index (per staff and bar) to read events."""
    located = []
    for event in events:
        item = dict(event)
        item["flowPosition"] = event["position"]
        item["bar"], item["position"] = bars.locate(event["position"])
        located.append(item)
    located.sort(key=lambda e: (e["staff"], e["bar"], e["position"], e.get("voice") or 0, e.get("pitch") or 0, e["id"]))
    counters: dict[tuple[int, int], int] = {}
    for item in located:
        key = (item["staff"], item["bar"])
        item["index"] = counters.get(key, 0)
        counters[key] = item["index"] + 1
    return located


def resolve_staves(requested: list[str], staves: list[dict[str, Any]]) -> set[int]:
    numbers: set[int] = set()
    for name in requested:
        text = str(name).strip()
        if text.isdigit():
            number = int(text)
            if number != 0 and not any(s["staff"] == number for s in staves):
                raise DoricoBatchError(f"no staff {number}; staves are 1-{len(staves)}")
            numbers.add(number)
        elif text.lower() == "system":
            numbers.add(0)
        else:
            matches = {s["staff"] for s in staves if (s.get("name") or "").lower() == text.lower()}
            if not matches:
                names = sorted({s.get("name") or "?" for s in staves})
                raise DoricoBatchError(f"no staff named {text!r}; names: {', '.join(names)}")
            numbers |= matches
    return numbers


def _types(requested: list[str]) -> set[str]:
    out: set[str] = set()
    for name in requested:
        out |= TYPE_ALIASES.get(name, {name})
    return out


def _condition(text: str) -> tuple[str, str, Any]:
    match = _WHERE.match(text)
    if not match or match.group(1) not in WHERE_FIELDS:
        raise DoricoBatchError(f"bad condition {text!r}; use Field op value with fields {', '.join(WHERE_FIELDS)}")
    field, op, raw = match.groups()
    value: Any = raw.strip("'\"")
    if re.fullmatch(r"-?\d+", value):
        value = int(value)
    return WHERE_FIELDS[field], op, value


def _holds(item: dict[str, Any], key: str, op: str, value: Any) -> bool:
    actual = item.get(key)
    if key == "type" and isinstance(value, str):
        actual_set = actual in _types([value])
        return actual_set if op == "=" else not actual_set if op == "!=" else False
    if actual is None:
        return op == "!="
    try:
        return {
            "=": actual == value, "!=": actual != value, ">": actual > value,
            "<": actual < value, ">=": actual >= value, "<=": actual <= value,
        }[op]
    except TypeError:
        return False


def query(
    located: list[dict[str, Any]],
    *,
    staves: set[int] | None = None,
    from_bar: int | None = None,
    to_bar: int | None = None,
    types: list[str] | None = None,
    voice: int | None = None,
    where: list[str] | None = None,
    limit: int = 200,
) -> dict[str, Any]:
    wanted_types = _types(types) if types else None
    conditions = [_condition(w) for w in where or []]
    objects = []
    for item in located:
        if staves is not None and item["staff"] not in staves:
            continue
        if staves is None and item["staff"] == 0:
            continue
        if from_bar is not None and item["bar"] < from_bar:
            continue
        if to_bar is not None and item["bar"] > to_bar:
            continue
        if wanted_types is not None and item["type"] not in wanted_types:
            continue
        if voice is not None and item.get("voice") != voice:
            continue
        if not all(_holds(item, *c) for c in conditions):
            continue
        objects.append({k: v for k, v in item.items() if v is not None})
    return {"objects": objects[:limit], "count": len(objects), "truncated": len(objects) > limit}


# ------------------------------------------------------------------ batches

def prepare_batch(
    operations: Any,
    located: list[dict[str, Any]],
    staves: list[dict[str, Any]],
    bars: BarMap,
) -> list[dict[str, Any]]:
    """Validate a batch and resolve it into bridge.lua operations."""
    if not isinstance(operations, list) or not operations:
        raise DoricoBatchError("a batch must be a non-empty JSON array")
    by_id = {e["id"]: e for e in located if "id" in e}
    by_address = {(e["staff"], e["bar"], e["index"]): e for e in located}
    out: list[dict[str, Any]] = []
    targeted: dict[int, int] = {}
    for i, operation in enumerate(operations):
        label = f"op {i}"
        if not isinstance(operation, dict):
            raise DoricoBatchError(f"{label} must be an object")
        op = operation.get("op")
        if op not in OPERATIONS:
            raise DoricoBatchError(f"{label}.op must be one of: {', '.join(sorted(OPERATIONS))}")
        if op == "transpose":
            resolved = _transpose(operation, label, located)
        elif op == "set-break":
            resolved = [_set_break(operation, label, located, bars)]
        elif op == "add-lyrics":
            resolved = [_add_lyrics(operation, label, by_id, by_address)]
        elif op in {"set-time", "set-key", "set-barline"}:
            resolved = [_signature(operation, op, label, located, bars)]
        elif op in ADDRESSED:
            resolved = [_addressed(operation, op, label, by_id, by_address)]
        else:
            resolved = [_adding(operation, op, label, staves, bars)]
        for item in resolved:
            if "id" in item:
                if item["id"] in targeted:
                    raise DoricoBatchError(
                        f"{label} targets event {item['id']}, which op {targeted[item['id']]} already changes"
                    )
                targeted[item["id"]] = i
            out.append(item)
    if not out:
        raise DoricoBatchError("the batch changes nothing (a transpose range may hold no notes)")
    kinds = {o["op"] in COMMAND_OPS for o in operations}
    if len(kinds) > 1:
        raise DoricoBatchError(
            "set-break, set-time, set-key, set-barline and add-lyrics run as Dorico commands "
            "(several undo steps), so they cannot "
            "share a batch with other operations; send them as their own batch"
        )
    return out


def _addressed(
    operation: dict[str, Any], op: str, label: str,
    by_id: dict[int, dict[str, Any]], by_address: dict[tuple[int, int, int], dict[str, Any]],
) -> dict[str, Any]:
    if "id" in operation:
        event = by_id.get(_int(operation, "id", label, 0))
        if event is None:
            raise DoricoBatchError(f"{label}: no event with id {operation['id']}")
    else:
        address = (
            _int(operation, "staff", label, 0), _int(operation, "bar", label, 1), _int(operation, "index", label, 0)
        )
        event = by_address.get(address)
        if event is None:
            raise DoricoBatchError(f"{label}: nothing at staff {address[0]} bar {address[1]} index {address[2]}")
    if "id" not in event:
        raise DoricoBatchError(
            f"{label}: staff {event['staff']} was read from a MusicXML export (Dorico's scripting cannot "
            "read staves with lyrics), so its existing notes cannot be changed or deleted; adding works"
        )
    if event.get("source") == "dump" and op != "lookup":
        raise DoricoBatchError(
            f"{label}: event {event['id']} is on a staff Dorico's scripting can only list (lyrics or "
            "tempo marks), so it cannot be changed or deleted from a script; adding works"
        )
    if "type" in operation and event["type"] not in _types([_str(operation, "type", label)]):
        raise DoricoBatchError(f"{label}: the object there is a {event['type']}, not a {operation['type']}")
    if "position" in operation and event["position"] != operation["position"]:
        raise DoricoBatchError(f"{label}: the object there is at position {event['position']}, not {operation['position']}")
    out: dict[str, Any] = {
        "op": op, "stream": event["stream"], "id": event["id"],
        "type": event["type"], "position": event["flowPosition"],
    }
    if op == "set-pitch":
        if event["type"] not in TYPE_ALIASES["Note"]:
            raise DoricoBatchError(f"{label}: set-pitch needs a note, not a {event['type']}")
        old = _int(operation, "oldPitch", label, 0, 127)
        new = _int(operation, "newPitch", label, 0, 127)
        if old == new:
            raise DoricoBatchError(f"{label} set-pitch must change the pitch")
        if event.get("pitch") != old:
            raise DoricoBatchError(f"{label}: the note there has pitch {event.get('pitch')}, not {old}")
        spelling = operation.get("spelling")
        out.update(oldPitch=old, newPitch=new, letter=spelling_letter(new, spelling if spelling else None))
    return out


def _signature(
    operation: dict[str, Any], op: str, label: str, located: list[dict[str, Any]], bars: BarMap
) -> dict[str, Any]:
    """A time signature, key signature or barline at the start of a bar.

    Selects an item that starts exactly at the bar (Dorico puts a signature
    at the selected item's position, mid-bar if it is not at the start) and
    runs NoteInput.CreateTimeSignature / CreateKeySignature / CreateBarLine
    with the popover's text as Definition, sent unencoded (Dorico does not
    URL-decode parameters). Bar 1 cannot be changed this way: the edit-in-
    place commands do nothing (docs/dorico.md).
    """
    bar = _int(operation, "bar", label, 2)
    if op == "set-time":
        top = _int(operation, "numerator", label, 1, 64)
        bottom = _int(operation, "denominator", label, 1, 64)
        if bottom & (bottom - 1):
            raise DoricoBatchError(f"{label}.denominator must be a power of two up to 64")
        definition, command, expect = f"{top}/{bottom}", "NoteInput.CreateTimeSignature", "BarDivisionEvent"
    elif op == "set-key":
        key = _str(operation, "key", label)
        minor = operation.get("minor", False)
        if not isinstance(minor, bool):
            raise DoricoBatchError(f"{label}.minor must be boolean")
        keys = MINOR_KEYS if minor else MAJOR_KEYS
        if key not in keys:
            raise DoricoBatchError(f"{label}.key must be a {'minor' if minor else 'major'} key: {', '.join(sorted(keys))}")
        # The key popover takes a capital letter for major, lower case for minor.
        definition = key[0].lower() + key[1:] if minor else key
        command, expect = "NoteInput.CreateKeySignature", "TonalityDivisionEvent"
    else:
        kind = operation.get("type")
        if kind not in BARLINE_DEFINITIONS:
            raise DoricoBatchError(f"{label}.type must be one of: {', '.join(sorted(BARLINE_DEFINITIONS))}")
        definition, command, expect = BARLINE_DEFINITIONS[kind], "NoteInput.CreateBarLine", "BarDivisionEvent"
    try:
        position = bars.position(bar, 0)
    except Exception as exc:
        raise DoricoBatchError(f"{label}: {exc}") from exc
    candidates = [
        e for e in located
        if e["bar"] == bar and e["position"] == 0 and e["staff"] >= 1 and "id" in e
        and e["type"] in TYPE_ALIASES["NoteRest"] and e.get("voice")
    ]
    if not candidates:
        raise DoricoBatchError(
            f"{label}: bar {bar} has no note or rest the bridge can select at its first beat "
            "(Dorico places the change at the selected item)"
        )
    target = min(candidates, key=lambda e: (e["staff"], e["id"]))
    return {"op": op, "bar": bar, "position": position, "command": command, "definition": definition,
            "expect": expect, "select": {"id": target["id"], "stream": target["stream"]}}


def _set_break(
    operation: dict[str, Any], label: str, located: list[dict[str, Any]], bars: BarMap
) -> dict[str, Any]:
    """A system break at the start of a bar ("system"), or its removal ("none").

    Adding selects the bar's first note or rest (by id) and runs
    Edit.CreateSystemBreak: Lua-made breaks are ignored by the layout
    (docs/dorico.md). Removing deletes the BreakEvent through Lua.
    """
    bar = _int(operation, "bar", label, 2)
    kind = operation.get("type")
    if kind not in BREAK_TYPES:
        raise DoricoBatchError(f"{label}.type must be one of: {', '.join(sorted(BREAK_TYPES))}")
    try:
        position = bars.position(bar, 0)
    except Exception as exc:
        raise DoricoBatchError(f"{label}: {exc}") from exc
    existing = [e for e in located if e["type"] == "BreakEvent" and e["flowPosition"] == position]
    if kind == "none":
        if not existing:
            raise DoricoBatchError(f"{label}: there is no break at bar {bar}")
        e = existing[0]
        return {"op": "delete", "stream": e["stream"], "id": e["id"], "type": "BreakEvent", "position": position}
    if existing:
        raise DoricoBatchError(f"{label}: bar {bar} already has a break")
    candidates = [
        e for e in located
        if e["bar"] == bar and e["staff"] >= 1 and "id" in e
        and e["type"] in TYPE_ALIASES["NoteRest"] and e.get("voice")
    ]
    if not candidates:
        raise DoricoBatchError(
            f"{label}: bar {bar} has no note or rest the bridge can select (staves with lyrics "
            "have no ids), so Dorico cannot be told where to break"
        )
    target = min(candidates, key=lambda e: (e["position"], e["staff"], e["id"]))
    return {"op": "set-break", "type": "system", "bar": bar, "position": position,
            "select": {"id": target["id"], "stream": target["stream"]}}


#: How AcceptCurrentLyricInput leaves each syllable (logged from the popover).
HYPHENATE = "kHyphenateCurrentWord"
END_WORD = "kEndOrExtendCurrentWord"
END_INPUT = "kEndInput"


def parse_lyrics(text: str) -> list[tuple[str, str]]:
    """Syllables and how each ends: "ma-king lyr-ics _ now" ->
    [("ma", hyphen), ("king", end), ("lyr", hyphen), ("ics", end), ("", end), ("now", end input)].

    Spaces separate words, a hyphen splits a word into syllables, and "_"
    continues the previous syllable over the next note (a melisma).
    """
    syllables: list[tuple[str, str]] = []
    for word in text.split():
        if word == "_":
            syllables.append(("", END_WORD))
            continue
        parts = [p for p in word.split("-") if p]
        if not parts:
            raise DoricoBatchError(f"lyric word {word!r} has no syllables")
        syllables += [(p, HYPHENATE) for p in parts[:-1]] + [(parts[-1], END_WORD)]
    if not syllables:
        raise DoricoBatchError("lyrics text is empty")
    last_text, _ = syllables[-1]
    syllables[-1] = (last_text, END_INPUT)
    return syllables


def _add_lyrics(
    operation: dict[str, Any], label: str,
    by_id: dict[int, dict[str, Any]], by_address: dict[tuple[int, int, int], dict[str, Any]],
) -> dict[str, Any]:
    """Lyrics typed into Dorico's lyric popover from a first note onwards.

    Runs NoteInput.StartLyricInput and one AcceptCurrentLyricInput per
    syllable, as the popover does (docs/dorico.md). Dorico moves to the next
    note itself, so only the first note needs an id: the staff must not
    have lyrics yet (Lua cannot read a staff that has them).
    """
    target = _addressed({**operation, "op": "delete"}, "lookup", label, by_id, by_address)
    if target["type"] not in TYPE_ALIASES["Note"]:
        raise DoricoBatchError(f"{label}: lyrics start on a note, not a {target['type']}")
    if by_id[target["id"]].get("source") == "dump":
        raise DoricoBatchError(f"{label}: staff {by_id[target['id']]['staff']} already has lyrics (or items "
                               "Dorico's scripting cannot read); add-lyrics needs a staff without lyrics")
    verse = operation.get("verse", 1)
    if verse != 1:
        raise DoricoBatchError(f"{label}: only verse 1 is supported so far")
    text = operation.get("text")
    if isinstance(text, str) and UNSAFE_PARAMETER & set(text):
        raise DoricoBatchError(f"{label}.text cannot contain a backslash or a line break")
    if not isinstance(text, str):
        raise DoricoBatchError(f"{label}.text must be a string of words, e.g. \"ma-king lyr-ics\"")
    event = by_id[target["id"]]
    return {
        "op": "add-lyrics", "staff": event["staff"], "position": event["flowPosition"],
        "select": {"id": target["id"], "stream": target["stream"]},
        "syllables": [list(s) for s in parse_lyrics(text)],
    }


def _stream_for(staff: int, voice: int, staves: list[dict[str, Any]], label: str) -> int:
    for s in staves:
        if s["staff"] == staff:
            voices = s.get("voiceStreams") or []
            if not 1 <= voice <= len(voices):
                raise DoricoBatchError(
                    f"{label}: staff {staff} has {len(voices)} voice(s) the bridge can see; "
                    "add a voice in Dorico first"
                )
            return voices[voice - 1]
    raise DoricoBatchError(f"{label}: no staff {staff}")


def _adding(
    operation: dict[str, Any], op: str, label: str, staves: list[dict[str, Any]], bars: BarMap
) -> dict[str, Any]:
    staff = _int(operation, "staff", label, 1)
    voice = _int({"voice": 1, **operation}, "voice", label, 1, 8)
    if "flowPosition" in operation:
        position = _int(operation, "flowPosition", label, 0)
    else:
        bar = _int(operation, "bar", label, 1)
        offset = _int(operation, "position", label, 0)
        try:
            position = bars.position(bar, offset)
        except Exception as exc:
            raise DoricoBatchError(f"{label}: {exc}") from exc
    if op == "add-clef":
        clef = _str(operation, "clef", label)
        if clef.removeprefix("clef.") not in CLEFS:
            raise DoricoBatchError(f"{label}.clef must be one of: {', '.join(sorted(CLEFS))}")
        stave = next((s for s in staves if s["staff"] == staff), None)
        if stave is None:
            raise DoricoBatchError(f"{label}: no staff {staff}")
        return {"op": op, "stream": stave["stream"], "position": position, "clef": "clef." + clef.removeprefix("clef.")}
    out: dict[str, Any] = {"op": op, "stream": _stream_for(staff, voice, staves, label), "position": position}
    if op == "add-note":
        pitches = operation.get("pitches")
        if not isinstance(pitches, list) or not pitches or not all(
            isinstance(p, int) and not isinstance(p, bool) and 0 <= p <= 127 for p in pitches
        ):
            raise DoricoBatchError(f"{label}.pitches must be a non-empty array of MIDI pitches")
        spellings = operation.get("spellings") or [None] * len(pitches)
        if not isinstance(spellings, list) or len(spellings) != len(pitches):
            raise DoricoBatchError(f"{label}.spellings must list one spelling per pitch")
        out.update(
            duration=_int(operation, "duration", label, 1),
            pitches=pitches,
            letters=[spelling_letter(p, s) for p, s in zip(pitches, spellings)],
        )
    elif op == "add-rest":
        out["duration"] = _int(operation, "duration", label, 1)
    elif op == "add-text":
        out["text"] = _str(operation, "text", label)
        out["duration"] = 0
    return out


def _transpose(operation: dict[str, Any], label: str, located: list[dict[str, Any]]) -> list[dict[str, Any]]:
    first = _int(operation, "fromBar", label, 1)
    last = _int(operation, "toBar", label, first)
    top = _int(operation, "topStaff", label, 1)
    bottom = _int(operation, "bottomStaff", label, top)
    steps, semitones = interval_of(operation, label)
    if semitones == 0:
        raise DoricoBatchError(f"{label} must transpose by a non-zero interval")
    out = []
    for event in located:
        if event["type"] not in TYPE_ALIASES["Note"] or not first <= event["bar"] <= last or not top <= event["staff"] <= bottom:
            continue
        if "id" not in event or event.get("source") == "dump":
            raise DoricoBatchError(
                f"{label}: staff {event['staff']} has lyrics or tempo marks, which Dorico's scripting cannot "
                "read, so its notes cannot be transposed"
            )
        try:
            pitch, letter = transpose_spelled(event.get("name"), event["pitch"], steps, semitones)
        except DoricoBatchError as exc:
            raise DoricoBatchError(f"{label}: event {event['id']}: {exc}") from exc
        out.append({
            "op": "set-pitch", "stream": event["stream"], "id": event["id"], "type": event["type"],
            "position": event["flowPosition"], "oldPitch": event["pitch"], "newPitch": pitch, "letter": letter,
        })
    return out


def _int(operation: dict[str, Any], field: str, label: str, minimum: int, maximum: int | None = None) -> int:
    value = operation.get(field)
    if not isinstance(value, int) or isinstance(value, bool):
        raise DoricoBatchError(f"{label}.{field} must be an integer")
    if value < minimum or (maximum is not None and value > maximum):
        bound = f"{minimum}-{maximum}" if maximum is not None else f">= {minimum}"
        raise DoricoBatchError(f"{label}.{field} must be {bound}")
    return value


def _str(operation: dict[str, Any], field: str, label: str) -> str:
    value = operation.get(field)
    if not isinstance(value, str) or not value:
        raise DoricoBatchError(f"{label}.{field} must be a non-empty string")
    return value
