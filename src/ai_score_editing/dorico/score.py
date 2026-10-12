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

from ai_score_editing import intervals, lyrics
from ai_score_editing.batch_ops import LAYOUT_NUMBERS, ORIENTATIONS, PAGE_SIZES

from .bridge import BarMap

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
#: Ops that select a note and run one Dorico command on it.
NOTE_COMMAND_OPS = {"add-dynamic", "set-articulation", "add-slur", "add-tempo", "add-rehearsal-mark"}
COMMAND_OPS = {
    "set-break", "add-lyrics", "set-time", "set-key", "set-barline", "copy-passage", "add-line", "add-bars",
    "set-layout", "delete-bars",
} | NOTE_COMMAND_OPS
#: Resolved forms of set-pitch/delete/transpose on notes read from dump().
ROUTED_COMMAND_OPS = {"repitch", "delete-by-id"}
#: set-articulation names and NoteInput.SetArticulation values (checked 2026-09-27).
ARTICULATIONS = {
    "accent": "kAccent", "marcato": "kMarcato", "staccato": "kStaccato",
    "staccatissimo": "kStaccatissimo", "tenuto": "kTenuto", "staccato-tenuto": "kStaccatoTenuto",
    "stress": "kStress", "unstress": "kUnstress",
}
DYNAMICS = {"pppp", "ppp", "pp", "p", "mp", "mf", "f", "ff", "fff", "ffff", "sfz", "sf", "fp", "sfp", "rfz", "fz"}
#: Popover definitions Dorico's create commands take (logged from the popovers).
BARLINE_DEFINITIONS = {"double": "||", "final": "|]", "start_repeat": "|:", "end_repeat": ":|"}
MAJOR_KEYS = {"C", "G", "D", "A", "E", "B", "F#", "C#", "F", "Bb", "Eb", "Ab", "Db", "Gb", "Cb"}
MINOR_KEYS = {"A", "E", "B", "F#", "C#", "G#", "D#", "A#", "D", "G", "C", "F", "Bb", "Eb", "Ab"}
#: add-line kinds: the command that makes one at the selected item, the event
#: it makes, and whether that item must be a note (logged or checked live
#: 2026-09-27; each line starts at the item and lasts as long as it).
LINES: dict[str, tuple[str, str, bool]] = {
    "crescendo": ("NoteInput.CreateDynamic?Definition=<", "DynamicGroupEvent", False),
    "diminuendo": ("NoteInput.CreateDynamic?Definition=>", "DynamicGroupEvent", False),
    "8va": ("NoteInput.OttavaLineStart?Octave=1", "OttavaLineEvent", False),
    "8vb": ("NoteInput.OttavaLineStart?Octave=-1", "OttavaLineEvent", False),
    "trill": ("NoteInput.CreateOrnament?Definition=tr", "TrillEvent", True),
    "pedal": ("NoteInput.CreatePlayingTechnique?Definition=ped", "PedalLineEvent", False),
    "glissando": ("NoteInput.CreateGlissando", "GlissandoLineEvent", True),
}
#: Lines whose length Lua cannot read (a hairpin's is in its dynamic group element).
UNREADABLE_LENGTH = {"DynamicGroupEvent"}
#: The note values EventEdit.DurationLengthenByValue / ShortenByValue take,
#: checked one by one on a line (2026-09-27). Other names, such as kBreve,
#: are not refused but move the end somewhere else, so only these are sent.
RESIZE_VALUES = [(1024, "kSemibreve"), (512, "kMinim"), (256, "kCrotchet"),
                 (128, "kQuaver"), (64, "kSemiquaver"), (32, "kDemisemiquaver")]


def resize_steps(current: int, target: int) -> list[str]:
    """The lengthen/shorten commands that take a selected line from current to target length."""
    change = target - current
    command = "EventEdit.DurationLengthenByValue" if change > 0 else "EventEdit.DurationShortenByValue"
    left = abs(change)
    commands = []
    for units, value in RESIZE_VALUES:
        while left >= units:
            commands.append(f"{command}?RhythmicGridResolutionValue={value}")
            left -= units
    if left:
        raise DoricoBatchError(f"a line cannot be resized by {abs(change)}: lengths go in steps of 32 (a demisemiquaver)")
    return commands


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
OPERATIONS = ADDRESSED | ADDING | COMMAND_OPS | {"transpose", "delete-voice"}
#: A quarter note in the back end's units.
UNIT_QUARTER = 256
#: Sibelius ops with no Dorico route yet, and why (docs/dorico.md).
NOT_ON_DORICO = {
    "set-bar-number": "a bar number change goes through a dialog scripting cannot drive yet",
    "hide-empty-staves": (
        "Dorico hides empty staves per layout, not over a range of bars; use set-layout's "
        "hideEmptyStaves (\"never\", \"after-first-system\" or \"all-systems\") for the whole layout"
    ),
}
#: add-bars refuses more than this, as the Sibelius back end does.
MAX_ADD_BARS = 1000
BREAK_TYPES = {"system", "none"}


class DoricoBatchError(ValueError):
    """A query or batch cannot be run against this score."""


# ------------------------------------------------------------------ spelling
# The shared helpers raise ValueError; batches report DoricoBatchError.

def spelling_letter(pitch: int, spelling: str | None = None) -> str:
    """The letter name to spell `pitch` with, checking an explicit spelling fits."""
    try:
        return intervals.spelling_letter(pitch, spelling)
    except ValueError as exc:
        raise DoricoBatchError(str(exc)) from exc


def transpose_spelled(name: str | None, pitch: int, steps: int, semitones: int) -> tuple[int, str]:
    """(new pitch, new letter) for a note moved by diatonic steps and semitones."""
    try:
        return intervals.transpose_spelled(name, pitch, steps, semitones)
    except ValueError as exc:
        raise DoricoBatchError(str(exc)) from exc


def interval_of(operation: dict[str, Any], label: str) -> tuple[int, int]:
    """(signed diatonic steps, signed semitones) for a transpose operation."""
    try:
        return intervals.interval_of(operation, label)
    except ValueError as exc:
        raise DoricoBatchError(str(exc)) from exc


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
        # Global items (time and key signatures, breaks) are on staff 0: left
        # out unless asked for by staff or by type.
        if staves is None and item["staff"] == 0 and not (wanted_types and item["type"] in wanted_types):
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
        if op in NOT_ON_DORICO:
            raise DoricoBatchError(f"{label}: {op} is not available on Dorico: {NOT_ON_DORICO[op]}")
        if op not in OPERATIONS:
            raise DoricoBatchError(f"{label}.op must be one of: {', '.join(sorted(OPERATIONS))}")
        if op == "transpose":
            resolved = _transpose(operation, label, located)
        elif op == "set-break":
            resolved = [_set_break(operation, label, located, bars, staves)]
        elif op == "add-lyrics":
            resolved = [_add_lyrics(operation, label, by_id, by_address)]
        elif op in {"set-time", "set-key", "set-barline"}:
            resolved = [_signature(operation, op, label, located, bars, staves)]
        elif op in NOTE_COMMAND_OPS:
            resolved = [_note_command(operation, op, label, by_id, by_address)]
        elif op == "add-line":
            resolved = [_add_line(operation, label, located, staves, bars)]
        elif op == "copy-passage":
            resolved = _copy_passage(operation, label, located, staves, bars)
        elif op == "delete-voice":
            resolved = [_delete_voice(operation, label, staves, bars)]
        elif op == "add-bars":
            resolved = [_add_bars(operation, label, located, staves, bars)]
        elif op == "delete-bars":
            resolved = [_delete_bars(operation, label, located, staves, bars)]
        elif op == "set-layout":
            resolved = [_set_layout(operation, label)]
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
    _check_inserted_bars(operations)
    # As on Sibelius, voice deletions run after everything else in the batch.
    out.sort(key=lambda o: o["op"] == "delete-voice")
    kinds = {o["op"] in COMMAND_OPS | ROUTED_COMMAND_OPS or o["op"] == "delete" and o.get("type") == "BreakEvent"
             for o in out}
    if len(kinds) > 1:
        raise DoricoBatchError(
            "command ops (set-break, set-time, set-key, set-barline, add-bars, set-layout, add-lyrics, notation ops, and "
            "edits to notes on staves with lyrics) take several undo steps, so they cannot "
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
    dumped = event.get("source") == "dump"
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
    if dumped and op in ("set-pitch", "delete"):
        # No Lua object for this note (its staff has lyrics or tempo marks):
        # use Dorico's commands on its id instead (docs/dorico.md).
        out["op"] = "repitch" if op == "set-pitch" else "delete-by-id"
        out["select"] = {"id": event["id"], "stream": event["stream"]}
        out["name"] = event.get("name")
    return out


def _note_command(
    operation: dict[str, Any], op: str, label: str,
    by_id: dict[int, dict[str, Any]], by_address: dict[tuple[int, int, int], dict[str, Any]],
) -> dict[str, Any]:
    """A notation added at a note by selecting it and running one command.

    Works on notes read from dump() too (only the id is needed). What each
    op creates, and how it is checked afterwards, is in docs/dorico.md.
    """
    target = _addressed({**operation, "op": "lookup"}, "lookup", label, by_id, by_address)
    event = by_id[target["id"]]
    if event["type"] not in TYPE_ALIASES["NoteRest"]:
        raise DoricoBatchError(f"{label}: {op} needs a note or rest, not a {event['type']}")
    out: dict[str, Any] = {"op": op, "staff": event["staff"], "position": event["flowPosition"],
                           "select": {"id": target["id"], "stream": target["stream"]}}
    if op == "add-dynamic":
        dynamic = _str(operation, "dynamic", label)
        if dynamic not in DYNAMICS:
            raise DoricoBatchError(f"{label}.dynamic must be one of: {', '.join(sorted(DYNAMICS))}")
        out.update(command="NoteInput.CreateDynamic", parameters={"Definition": dynamic}, expect="DynamicGroupEvent")
    elif op == "set-articulation":
        name = _str(operation, "articulation", label)
        if name not in ARTICULATIONS:
            raise DoricoBatchError(f"{label}.articulation must be one of: {', '.join(sorted(ARTICULATIONS))}")
        if event["type"] not in TYPE_ALIASES["Note"]:
            raise DoricoBatchError(f"{label}: articulations go on notes, not a {event['type']}")
        out.update(command="NoteInput.SetArticulation", parameters={"Value": ARTICULATIONS[name]},
                   articulation=name, checkable=event.get("source") != "dump")
    elif op == "add-slur":
        if event["type"] not in TYPE_ALIASES["Note"]:
            raise DoricoBatchError(f"{label}: slurs start on a note, not a {event['type']}")
        out.update(command="NoteInput.SlurStart", parameters={})
    elif op == "add-tempo":
        out.update(command="NoteInput.CreateTempo", parameters={"Definition": command_value(_str(operation, "text", label))},
                   expect="ImmediateTempoChangeEvent")
    else:
        out.update(command="NoteInput.CreateRehearsalMark", parameters={}, expect="RehearsalMarkEvent")
    return out


def _copy_passage(
    operation: dict[str, Any], label: str, located: list[dict[str, Any]],
    staves: list[dict[str, Any]], bars: BarMap,
) -> list[dict[str, Any]]:
    """Copy bars fromBar-toBar of staves top-bottom to destBar of destStaff on.

    Dorico copies what the selection holds: an exact selection from
    _extension_plan where there is one, else Edit.SelectMore (from a note)
    and NavigateRightExtendBar, which can reach a bar too far or too short.
    The selection starts at the range's first *note*, not the barline, and
    is pasted at the selected item. So the paste anchor is the destination
    bar start plus that note's offset: an existing item there, or a
    temporary rest (overwritten by the paste). One resolved op per staff.
    """
    first = _int(operation, "fromBar", label, 1)
    last = _int(operation, "toBar", label, first)
    top = _int(operation, "topStaff", label, 1)
    bottom = _int(operation, "bottomStaff", label, top)
    dest_staff = _int(operation, "destStaff", label, 1)
    dest_bar = _int(operation, "destBar", label, 1)
    if operation.get("destPosition", 0) != 0:
        raise DoricoBatchError(f"{label}: copy-passage pastes at the start of destBar only (destPosition 0)")
    if dest_staff + (bottom - top) > len(staves):
        raise DoricoBatchError(f"{label}: the destination runs past the last staff")
    try:
        source_start = bars.position(first, 0)
        source_end = bars.position(last, 0) + bars.bar_length(last)
        dest_start = bars.position(dest_bar, 0)
    except Exception as exc:
        raise DoricoBatchError(f"{label}: {exc}") from exc
    if dest_bar <= last and dest_bar + (last - first) >= first and dest_staff <= bottom and dest_staff + (bottom - top) >= top:
        raise DoricoBatchError(f"{label}: the destination overlaps the source")
    out = []
    for offset_staff in range(bottom - top + 1):
        staff, target_staff = top + offset_staff, dest_staff + offset_staff
        notes = sorted(
            (e for e in located if e["staff"] == staff and e["type"] in TYPE_ALIASES["Note"] and "id" in e
             and source_start <= e["flowPosition"] < source_end),
            key=lambda e: (e["flowPosition"], e.get("voice") or 0),
        )
        if not notes:
            continue  # nothing to copy on this staff
        in_first_bar = [e for e in notes if e["bar"] == first]
        if not in_first_bar:
            raise DoricoBatchError(f"{label}: staff {staff} has no note in bar {first} to start the selection from")
        offset = notes[0]["flowPosition"] - source_start
        anchor_position = dest_start + offset
        voices = next(s for s in staves if s["staff"] == target_staff).get("voiceStreams") or []
        if not voices:
            raise DoricoBatchError(f"{label}: staff {target_staff} has no voice to paste into")
        dest_events = [e for e in located if e["staff"] == target_staff and "id" in e and e["type"] in TYPE_ALIASES["NoteRest"]]
        covering = [e for e in dest_events if e["flowPosition"] < anchor_position < e["flowPosition"] + (e.get("duration") or 0)]
        if covering:
            raise DoricoBatchError(f"{label}: a note on staff {target_staff} covers the paste point; clear it first")
        at_anchor = [e for e in dest_events if e["flowPosition"] == anchor_position]
        resolved: dict[str, Any] = {
            "op": "copy-passage", "staff": staff, "destStaff": target_staff,
            "select": {"id": in_first_bar[0]["id"], "stream": in_first_bar[0]["stream"]},
            "extendBars": last - first,
            "expect": [(e["flowPosition"] - notes[0]["flowPosition"], e.get("pitch")) for e in notes],
            "anchorPosition": anchor_position, "destStreams": list(voices),
        }
        # An exact selection (no Edit.SelectMore): see _extension_plan.
        plan = _extension_plan(located, bars, first, last, staff=staff, anchor=in_first_bar[0], cover=True)
        if plan is not None:
            resolved.update(extendBars=plan["extend"], exact=True)
        if at_anchor:
            resolved["anchor"] = {"id": at_anchor[0]["id"], "stream": at_anchor[0]["stream"]}
        else:
            later = [e["flowPosition"] for e in dest_events if e["stream"] == voices[0] and e["flowPosition"] > anchor_position]
            room = min(later + [anchor_position + 256]) - anchor_position
            resolved["tempRest"] = {"stream": voices[0], "position": anchor_position, "duration": min(room, 256)}
        out.append(resolved)
    if not out:
        raise DoricoBatchError(f"{label}: there are no notes to copy in bars {first}-{last}")
    return out


def _signature(
    operation: dict[str, Any], op: str, label: str, located: list[dict[str, Any]], bars: BarMap,
    staves: list[dict[str, Any]],
) -> dict[str, Any]:
    """A time signature, key signature or barline at the start of a bar.

    Selects an item that starts exactly at the bar (Dorico puts a signature
    at the selected item's position, mid-bar if it is not at the start), or
    a temporary rest when the bar starts with implicit rests only, and
    runs NoteInput.CreateTimeSignature / CreateKeySignature / CreateBarLine
    with the popover's text as Definition, sent unencoded (Dorico does not
    URL-decode parameters). At bar 1 the new signature or barline replaces
    the one already there (docs/dorico.md).
    """
    bar = _int(operation, "bar", label, 1)
    offset = 0
    if op == "set-time":
        top = _int(operation, "numerator", label, 1, 64)
        bottom = _int(operation, "denominator", label, 1, 64)
        if bottom & (bottom - 1):
            raise DoricoBatchError(f"{label}.denominator must be a power of two up to 64")
        definition, command, expect = f"{top}/{bottom}", "NoteInput.CreateTimeSignature", "BarDivisionEvent"
        if "pickup" in operation:
            definition += "\\," + _pickup_beats(operation, label, top, bottom)
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
        # Part-way through a bar (a repeat on beat 4 of 6/4): Dorico splits
        # the bar there with a hidden restatement of the meter, and shows no
        # time signature (checked 2026-09-28).
        offset = _int({"position": 0, **operation}, "position", label, 0)
    try:
        position = bars.position(bar, offset)
    except Exception as exc:
        raise DoricoBatchError(f"{label}: {exc}") from exc
    candidates = [
        e for e in located
        if e["bar"] == bar and e["position"] == offset and e["staff"] >= 1 and "id" in e
        and e["type"] in TYPE_ALIASES["NoteRest"] and e.get("voice")
    ]
    resolved = {"op": op, "bar": bar, "position": position, "command": command, "definition": definition,
                "expect": expect}
    if offset:
        resolved["offset"] = offset
    if candidates:
        target = min(candidates, key=lambda e: (e["staff"], e["id"]))
        resolved["select"] = {"id": target["id"], "stream": target["stream"]}
        return resolved
    rest = _temporary_rest(position, located, staves)
    if rest is None:
        raise DoricoBatchError(
            f"{label}: nothing starts at position {offset} of bar {bar} and every voice holds a note over "
            "it, so there is nothing to select and no room for a temporary rest (Dorico places the change "
            "at the selected item)"
        )
    resolved["tempRest"] = rest
    return resolved


def _pickup_beats(operation: dict[str, Any], label: str, top: int, bottom: int) -> str:
    """set-time's pickup (1/256 quarters) in beats of the denominator, as the
    time signature popover takes it: 6/4,3 is 6/4 with a three-quarter
    pick-up, 6/8,3 three eighths, 4/4,1.5 a quarter and a half (all
    checked by measuring the bar, 2026-09-28)."""
    from fractions import Fraction

    bar_length = 4 * UNIT_QUARTER * top // bottom
    pickup = _int(operation, "pickup", label, 1, bar_length - 1)
    beats = Fraction(pickup * bottom, 4 * UNIT_QUARTER)
    if 1000 % beats.denominator:
        raise DoricoBatchError(f"{label}.pickup {pickup} is not a whole number of 1/1000 beats of 1/{bottom}")
    text = f"{float(beats):.3f}".rstrip("0").rstrip(".")
    return text


def _temporary_rest(
    position: int, located: list[dict[str, Any]], staves: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """A quarter rest (shorter if a note follows sooner) to select at position,
    in the first voice, top staff first, with nothing held over that point.

    For a bar whose first beat (for a break, whole bar) holds only Dorico's
    implicit rests, which are not events and so cannot be selected. Created
    and deleted around the command (two more undo steps).
    """
    for staff in sorted(staves, key=lambda s: s["staff"]):
        for stream in staff.get("voiceStreams") or []:
            events = [e for e in located if e.get("stream") == stream and e["type"] in TYPE_ALIASES["NoteRest"]]
            if any(e["flowPosition"] < position < e["flowPosition"] + (e.get("duration") or 0) for e in events):
                continue
            later = [e["flowPosition"] for e in events if e["flowPosition"] > position]
            return {"stream": stream, "position": position, "duration": min(later + [position + 256]) - position}
    return None


def _set_break(
    operation: dict[str, Any], label: str, located: list[dict[str, Any]], bars: BarMap,
    staves: list[dict[str, Any]],
) -> dict[str, Any]:
    """A system break at the start of a bar ("system"), or its removal ("none").

    Adding selects the bar's first note or rest (by id), or a temporary rest
    in a bar with nothing of its own, and runs Edit.CreateSystemBreak:
    Lua-made breaks are ignored by the layout (docs/dorico.md). Removing
    deletes the BreakEvent through Lua.
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
    resolved: dict[str, Any] = {"op": "set-break", "type": "system", "bar": bar, "position": position}
    if candidates:
        target = min(candidates, key=lambda e: (e["position"], e["staff"], e["id"]))
        resolved["select"] = {"id": target["id"], "stream": target["stream"]}
        return resolved
    rest = _temporary_rest(position, located, staves)
    if rest is None:
        raise DoricoBatchError(
            f"{label}: nothing starts in bar {bar} and every voice holds a note over its barline, so "
            "there is nothing to select and no room for a temporary rest (Dorico breaks at the selected item)"
        )
    resolved["tempRest"] = rest
    return resolved


#: How AcceptCurrentLyricInput leaves each syllable (logged from the popover).
HYPHENATE = "kHyphenateCurrentWord"
NEXT_VERSE = "kIncrementVerseNumber"  # the popover's Down Arrow
#: Lyric lines past this are refused as likely mistakes.
MAX_VERSE = 10
END_WORD = "kEndOrExtendCurrentWord"
END_INPUT = "kEndInput"


#: The popover advance each syllable kind ends with.
ADVANCE = {lyrics.BEGIN: HYPHENATE, lyrics.MIDDLE: HYPHENATE, lyrics.END: END_WORD,
           lyrics.SINGLE: END_WORD, lyrics.MELISMA: END_WORD}


def parse_lyrics(text: str) -> list[tuple[str, str]]:
    """Syllables and how each ends: "ma-king lyr-ics _ now" ->
    [("ma", hyphen), ("king", end), ("lyr", hyphen), ("ics", end), ("", end), ("now", end input)].

    Spaces separate words, a hyphen splits a word into syllables, and "_"
    continues the previous syllable over the next note (a melisma).
    """
    try:
        syllables = [(text, ADVANCE[kind]) for text, kind in lyrics.split_syllables(text)]
    except ValueError as exc:
        raise DoricoBatchError(str(exc)) from exc
    last_text, _ = syllables[-1]
    syllables[-1] = (last_text, END_INPUT)
    return syllables


def _add_lyrics(
    operation: dict[str, Any], label: str,
    by_id: dict[int, dict[str, Any]], by_address: dict[tuple[int, int, int], dict[str, Any]],
) -> dict[str, Any]:
    """Lyrics typed into Dorico's lyric popover from a first note onwards, in any verse.

    Runs NoteInput.StartLyricInput, one kIncrementVerseNumber accept per
    verse below the target (as the popover's Down Arrow does), then one
    AcceptCurrentLyricInput per syllable (docs/dorico.md). Dorico moves to
    the next note itself, so only the first note needs an id. On a staff
    that already has lyrics, the lower verses' text at that note and any
    lyrics the new syllables would overwrite are checked before typing
    (service._plan_lyrics).
    """
    target = _addressed({**operation, "op": "delete"}, "lookup", label, by_id, by_address)
    if target["type"] not in TYPE_ALIASES["Note"]:
        raise DoricoBatchError(f"{label}: lyrics start on a note, not a {target['type']}")
    verse = operation.get("verse", 1)
    if isinstance(verse, bool) or not isinstance(verse, int) or not 1 <= verse <= MAX_VERSE:
        raise DoricoBatchError(f"{label}.verse must be a whole number from 1 to {MAX_VERSE}")
    text = operation.get("text")
    if isinstance(text, str) and UNSAFE_PARAMETER & set(text):
        raise DoricoBatchError(f"{label}.text cannot contain a backslash or a line break")
    if not isinstance(text, str):
        raise DoricoBatchError(f"{label}.text must be a string of words, e.g. \"ma-king lyr-ics\"")
    event = by_id[target["id"]]
    return {
        "op": "add-lyrics", "staff": event["staff"], "position": event["flowPosition"], "verse": verse,
        "select": {"id": target["id"], "stream": target["stream"]},
        "hasLyrics": event.get("source") == "dump",
        "syllables": [list(s) for s in parse_lyrics(text)],
    }


def _add_line(
    operation: dict[str, Any], label: str, located: list[dict[str, Any]],
    staves: list[dict[str, Any]], bars: BarMap,
) -> dict[str, Any]:
    """A hairpin, octave line, trill, pedal line or glissando on a staff.

    Dorico makes each at the selected item, lasting as long as it (LINES):
    the op selects a note or rest on the staff starting at the position (a
    temporary rest where there is none, for lines that need no note), runs
    the command, then selects the new line and lengthens or shortens it to
    duration (resize_steps). A glissando runs to the next note and takes no
    duration. Compare Sibelius's add-line (a styleId and duration); octave
    lines differ in meaning: Dorico keeps the sounding pitch and rewrites
    the notes, Sibelius keeps the notes.
    """
    kind = operation.get("line")
    if kind not in LINES:
        raise DoricoBatchError(f"{label}.line must be one of: {', '.join(LINES)}")
    command, expect, needs_note = LINES[kind]
    staff = _int(operation, "staff", label, 1)
    stave = next((s for s in staves if s["staff"] == staff), None)
    if stave is None:
        raise DoricoBatchError(f"{label}: no staff {staff}")
    bar = _int(operation, "bar", label, 1)
    offset = _int({"position": 0, **operation}, "position", label, 0)
    try:
        position = bars.position(bar, offset)
    except Exception as exc:
        raise DoricoBatchError(f"{label}: {exc}") from exc
    if kind == "glissando":
        if "duration" in operation:
            raise DoricoBatchError(f"{label}: a glissando runs to the next note and takes no duration")
        duration = None
    else:
        duration = _int(operation, "duration", label, 32)
        if duration % 32:
            raise DoricoBatchError(f"{label}.duration must be a multiple of 32 (a demisemiquaver)")
    types = TYPE_ALIASES["Note"] if needs_note else TYPE_ALIASES["NoteRest"]
    at = [e for e in located if e["staff"] == staff and e["flowPosition"] == position and "id" in e
          and e["type"] in types and e.get("voice")]
    resolved: dict[str, Any] = {"op": "add-line", "line": kind, "staff": staff, "bar": bar, "position": position,
                                "command": command, "expect": expect, "duration": duration}
    if at:
        item = min(at, key=lambda e: (e.get("voice") or 0, e["id"]))
        resolved["select"] = {"id": item["id"], "stream": item["stream"]}
        resolved["itemDuration"] = item.get("duration") or 0
    elif needs_note:
        raise DoricoBatchError(f"{label}: a {kind} starts on a note, and staff {staff} has none at bar {bar} position {offset}")
    else:
        rest = _temporary_rest(position, located, [stave])
        if rest is None:
            raise DoricoBatchError(
                f"{label}: nothing starts on staff {staff} at bar {bar} position {offset} and every voice holds "
                "a note over it, so there is nothing to select and no room for a temporary rest"
            )
        resolved["tempRest"] = rest
        resolved["itemDuration"] = rest["duration"]
    if duration is not None:
        resolved["resize"] = resize_steps(resolved["itemDuration"], duration)
    return resolved


def _check_inserted_bars(operations: list[dict[str, Any]]) -> None:
    """Refuse ops that name a bar an earlier op in the batch moves.

    Addresses are read before the batch, so after add-bars before bar B
    (bar B on), a set-time at bar B (the bars after B are re-barred) or a
    barline part-way through bar B (the bars after it are renumbered, since
    each part of a split bar is a bar), those bars would mean something else.
    """
    moved_after: int | None = None
    for i, operation in enumerate(operations):
        named = [operation[f] for f in ("bar", "fromBar", "toBar", "destBar") if isinstance(operation.get(f), int)]
        if moved_after is not None and any(b > moved_after for b in named):
            raise DoricoBatchError(
                f"op {i} names a bar after bar {moved_after}, which an earlier op in this batch moves "
                "(add-bars, delete-bars, set-time, or a barline part-way through a bar); put it earlier or send it "
                "in a later batch"
            )
        op = operation.get("op")
        if op == "delete-bars" and isinstance(operation.get("fromBar"), int):
            after = operation["fromBar"] - 1
            moved_after = after if moved_after is None else min(moved_after, after)
            continue
        bar = operation.get("bar")
        if not isinstance(bar, int):
            continue
        if op == "add-bars":
            after = bar - 1
        elif op == "set-time" or (op == "set-barline" and operation.get("position")):
            after = bar
        else:
            continue
        moved_after = after if moved_after is None else min(moved_after, after)


def _delete_voice(
    operation: dict[str, Any], label: str, staves: list[dict[str, Any]], bars: BarMap
) -> dict[str, Any]:
    """Everything in one voice of a staff that starts in bars fromBar-toBar.

    bridge.lua deletes it with EventStream:deleteEventsInRange, which takes
    the events starting in the range (lyrics included, since they are events
    in the same stream) and leaves a note held into the range from before it
    alone; the gap shows Dorico's implicit rests. Works on staves with
    lyrics too, where Lua can only dump the stream (checked 2026-09-28).
    """
    first = _int(operation, "fromBar", label, 1)
    last = _int(operation, "toBar", label, first)
    staff = _int(operation, "staff", label, 1)
    voice = _int(operation, "voice", label, 1, 8)
    stream = _stream_for(staff, voice, staves, label)
    try:
        start = bars.position(first, 0)
        end = bars.position(last, 0) + bars.bar_length(last)
    except Exception as exc:
        raise DoricoBatchError(f"{label}: {exc}") from exc
    return {"op": "delete-voice", "stream": stream, "staff": staff, "voice": voice,
            "fromBar": first, "toBar": last, "start": start, "end": end}


def _extension_plan(
    located: list[dict[str, Any]], bars: BarMap, first: int, last: int, *,
    staff: int | None = None, anchor: dict[str, Any] | None = None, cover: bool = False,
) -> dict[str, Any] | None:
    """A selection that covers exactly bars first-last: an item in bar `first`
    and how many EventEdit.NavigateRightExtendBar steps to run.

    Measured 2026-10-11 (docs/dorico.md, "Selecting bars"): the selection
    always holds whole items of one staff, an extend step moves its end to
    the next barline after it, and every item of the staff that starts
    before that barline is pulled in whole, so a note tied across the
    barline drags the following bar in. Edit.DeleteBars removes every bar the
    selection touches. This replays the steps on the events read, and
    returns the first anchor and step count that touch bars first-last and
    no others, or None. `staff` and `anchor` (an event) restrict the search;
    `cover` instead asks for every item that starts in the bars, as a copy
    needs (a single note touches its bar but copies only itself).
    """
    last_bar = max((e["bar"] for e in located), default=0)
    staves = [staff] if staff is not None else sorted({e["staff"] for e in located if e["staff"] >= 1})
    try:
        cover_end = bars.position(last, 0) + bars.bar_length(last)
    except Exception:
        return None
    for staff in staves:
        items = [
            e for e in located
            if e["staff"] == staff and e["type"] in TYPE_ALIASES["NoteRest"] and "id" in e and e.get("voice")
        ]
        # A lyric is an item of the stream: a melisma runs on past the barline and drags
        # the next bar in like a tied note (measured on Smith, 2026-10-11).
        lyrics = [e for e in located if e["staff"] == staff and e["type"] == "LyricEvent" and e.get("voice")]
        spans = [(e["flowPosition"], e["flowPosition"] + (e.get("duration") or 0)) for e in items + lyrics]
        anchors = sorted((e for e in items if e["bar"] == first),
                         key=lambda e: (e["type"] not in TYPE_ALIASES["Note"], e["flowPosition"], e.get("voice") or 0, e["id"]))
        if anchor is not None:
            anchors = [e for e in anchors if e["id"] == anchor["id"]]
        for chosen in anchors[:3]:
            end = chosen["flowPosition"] + (chosen.get("duration") or 0)
            for steps in range(0, last - first + 4):
                target = None
                if steps:
                    try:
                        bar, _ = bars.locate(end)
                        target = bars.position(bar + 1, 0)
                    except Exception:
                        break
                    # Only items that start in the selection's range are pulled in: a lyric
                    # extender that began before the anchor is not (measured on a synthetic score).
                    end = max([target] + [e for s_, e in spans if chosen["flowPosition"] <= s_ < target])
                if cover:
                    if not steps:
                        start = bars.position(first, 0)
                        alone = [e for e in items if start <= e["flowPosition"] < cover_end]
                        if len(alone) == 1 and alone[0]["id"] == chosen["id"]:
                            return {"select": {"id": chosen["id"], "stream": chosen["stream"]}, "extend": 0,
                                    "staff": staff}  # the one item that starts in the bars
                        continue
                    # A copy needs every item that starts in the bars: the step that targets the
                    # end of bar `last` pulls them all in, whatever a tie then adds past it.
                    if target == cover_end:
                        return {"select": {"id": chosen["id"], "stream": chosen["stream"]}, "extend": steps,
                                "staff": staff}
                    if target is not None and target > cover_end:
                        break
                    continue
                try:
                    touched_last = bars.locate(end - 1)[0]
                except Exception:
                    break
                if touched_last == last:
                    return {"select": {"id": chosen["id"], "stream": chosen["stream"]}, "extend": steps,
                            "staff": staff}
                if touched_last > last:
                    break  # overshot: a tied note dragged in a bar; try another anchor or staff
    return None


def _extension_plans(
    located: list[dict[str, Any]], bars: BarMap, first: int, last: int, limit: int = 3,
) -> list[dict[str, Any]]:
    """Up to `limit` exact selections for bars first-last, each on a different staff.

    The first is what _extension_plan would pick (staves in order). The others are the
    next staves whose own selection is exact: Dorico refuses the extend step on some staves
    (condensed players answer kCommandNotAllowed) and a slur or hairpin that Lua cannot read
    can make one staff's selection reach further than modelled, while another staff's is fine.
    """
    plans: list[dict[str, Any]] = []
    for staff in sorted({e["staff"] for e in located if e["staff"] >= 1}):
        plan = _extension_plan(located, bars, first, last, staff=staff)
        if plan is not None:
            plans.append(plan)
            if len(plans) >= limit:
                break
    return plans


def _delete_bars(
    operation: dict[str, Any], label: str, located: list[dict[str, Any]], staves: list[dict[str, Any]],
    bars: BarMap,
) -> dict[str, Any]:
    """Bars fromBar-toBar removed from every staff, the later bars moving up.

    Where _extension_plan finds a selection that covers exactly these bars,
    one select, some extend steps and one Edit.DeleteBars do it. Otherwise
    one bar at a time, last bar first so that the positions and ids read
    before the batch stay right: select an item in the bar (or a temporary
    rest, which goes with the bar), Edit.DeleteBars. Extending one selection
    with NavigateRightExtendBar, or Edit.SelectMore, removed the wrong
    number of bars (checked 2026-10-11), and a slur or hairpin starting in the selection pulls
    its whole span in, which the plan cannot see, and Dorico refuses the extend step on some
    staves; so a planned selection is a trial, checked and undone when it removes the wrong bars
    or is refused. Up to three plans on different staves (`plans`; `plan` is the first) are tried
    in turn, then the per-bar route (`fallback`). Lua cannot count a flow's bars, so the result is
    checked by a note after the range: it must have moved back by the length
    removed (or, with nothing after, the last bar's item must be gone).
    """
    first = _int(operation, "fromBar", label, 1)
    last = _int(operation, "toBar", label, first)
    try:
        start = bars.position(first, 0)
        end = bars.position(last, 0) + bars.bar_length(last)
    except Exception as exc:
        raise DoricoBatchError(f"{label}: {exc}") from exc
    last_bar = max((e["bar"] for e in located), default=0)
    if first == 1 and last >= last_bar:
        raise DoricoBatchError(f"{label}: delete-bars cannot remove every bar of the flow")
    resolved: dict[str, Any] = {"op": "delete-bars", "fromBar": first, "toBar": last, "start": start,
                                "removed": end - start, "bars": []}
    later = [e for e in located if e["flowPosition"] >= end and e["staff"] >= 1 and "id" in e
             and e["type"] in TYPE_ALIASES["Note"]]
    if later:
        marker = min(later, key=lambda e: (e["flowPosition"], e["id"]))
        resolved["marker"] = {"id": marker["id"], "position": marker["flowPosition"]}
    def per_bar() -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for bar in range(last, first - 1, -1):
            candidates = [
                e for e in located
                if e["bar"] == bar and e["staff"] >= 1 and "id" in e and e["type"] in TYPE_ALIASES["NoteRest"]
                and e.get("voice")
            ]
            if candidates:
                # A note, on the top staff's first voice if it has one (checked 2026-10-11).
                target = min(candidates, key=lambda e: (e["type"] not in TYPE_ALIASES["Note"], e["staff"],
                                                        e.get("voice") or 0, e["position"], e["id"]))
                items.append({"bar": bar, "select": {"id": target["id"], "stream": target["stream"]}})
                continue
            try:
                rest = _temporary_rest(bars.position(bar, 0), located, staves)
            except Exception as exc:
                raise DoricoBatchError(f"{label}: {exc}") from exc
            if rest is None:
                raise DoricoBatchError(
                    f"{label}: bar {bar} has nothing to select and no room for a temporary rest"
                )
            items.append({"bar": bar, "tempRest": rest})
        return items

    plans = _extension_plans(located, bars, first, last)
    if plans:
        # The plans model only what Lua can read (not slurs or hairpins, which also pull bars in),
        # and Dorico refuses the extend step on some staves, so each is tried and checked in turn;
        # a plan that removes the wrong number of bars (or is refused) is undone and the next one
        # tried, and after the last the bars are deleted one at a time (service._delete_bars).
        resolved["plan"] = plans[0]
        resolved["plans"] = plans
        try:
            resolved["fallback"] = per_bar()
        except DoricoBatchError:
            pass  # no per-bar route (a bar with nothing to select): the last plan has to work
        resolved["bars"] = [{"bar": b} for b in range(last, first - 1, -1)]  # the fallback's size, for counting
        resolved["lastItem"] = plans[0]["select"]
        return resolved
    resolved["bars"] = per_bar()
    resolved["lastItem"] = resolved["bars"][0].get("select")
    return resolved


def _add_bars(
    operation: dict[str, Any], label: str, located: list[dict[str, Any]], staves: list[dict[str, Any]],
    bars: BarMap,
) -> dict[str, Any]:
    """count bars of the meter in force, before bar `bar` or at the end.

    Inserting selects an item on the bar's first beat (or a temporary rest)
    and runs NoteInput.CreateBarLine?Definition=+N, the bars popover's text,
    which inserts N bars before it. Appending runs
    NoteInput.AddBarAtEndOfFlow once per bar, with nothing selected
    (both checked 2026-09-28).
    """
    count = _int(operation, "count", label, 1, MAX_ADD_BARS)
    if "length" in operation:
        raise DoricoBatchError(
            f"{label}.length is not supported on Dorico: an irregular bar is a barline part-way "
            "through a bar, which this back end cannot make yet"
        )
    if "bar" not in operation:
        return {"op": "add-bars", "count": count}
    bar = _int(operation, "bar", label, 1)
    try:
        position = bars.position(bar, 0)
        shift = count * bars.bar_length(bar)
    except Exception as exc:
        raise DoricoBatchError(f"{label}: {exc}") from exc
    resolved: dict[str, Any] = {"op": "add-bars", "count": count, "bar": bar, "position": position, "shift": shift}
    candidates = [
        e for e in located
        if e["bar"] == bar and e["position"] == 0 and e["staff"] >= 1 and "id" in e
        and e["type"] in TYPE_ALIASES["NoteRest"] and e.get("voice")
    ]
    if candidates:
        target = min(candidates, key=lambda e: (e["staff"], e["id"]))
        resolved["select"] = {"id": target["id"], "stream": target["stream"]}
        return resolved
    rest = _temporary_rest(position, located, staves)
    if rest is None:
        raise DoricoBatchError(
            f"{label}: nothing starts at bar {bar}'s first beat and every voice holds a note over it, "
            "so there is nothing to select and no room for a temporary rest (Dorico inserts bars at "
            "the selected item)"
        )
    resolved["tempRest"] = rest
    return resolved


#: Page sizes by set-layout name, portrait, in points (1/72 inch), for the
#: Sibelius names whose dimensions are unambiguous. The others (b4, b5,
#: us-band, hymn, quarto, folio) need pageWidth/pageHeight in millimetres.
PAGE_POINTS: dict[str, tuple[float, float]] = {
    "letter": (612, 792), "tabloid": (792, 1224), "legal": (612, 1008), "executive": (522, 756),
    "statement": (396, 612), "a3": (841.89, 1190.55), "a4": (595.28, 841.89), "a5": (419.53, 595.28),
    "concert": (648, 864), "octavo": (486, 756), "9.5x12.5": (684, 900), "10x13": (720, 936),
}
#: set-layout's millimetre fields and the Layout Options they set (points).
#: With identical margins, Dorico's outer margin is the left one and its
#: inner margin the right (checked in a render, 2026-09-28).
LAYOUT_MM_KEYS = {
    "topMargin": "pageSizeAndMarginOptions.pageMargins.margins.top",
    "bottomMargin": "pageSizeAndMarginOptions.pageMargins.margins.bottom",
    "leftMargin": "pageSizeAndMarginOptions.pageMargins.margins.outer",
    "rightMargin": "pageSizeAndMarginOptions.pageMargins.margins.inner",
    "aboveTopStaveGap": "pageSizeAndMarginOptions.defaultMusicFrameTopPadding",
    "belowBottomStaveGap": "pageSizeAndMarginOptions.defaultMusicFrameBottomPadding",
}
#: set-layout's staff-space fields and their Layout Options (staff spaces).
LAYOUT_SPACE_KEYS = {
    "spacesBetweenStaves": "verticalStaveGapOptions.staveToStaveGap",
    "spacesBetweenSystems": "verticalStaveGapOptions.interSystemGap",
}
PAGE_WIDTH = "pageSizeAndMarginOptions.pageWidth"
PAGE_HEIGHT = "pageSizeAndMarginOptions.pageHeight"
SPACE_SIZE = "defaultSpaceSize"  # one staff space, in points
MARGIN_TYPE = "pageSizeAndMarginOptions.pageMargins.type"
HIDE_EMPTY = "hideEmptyStavesPolicy"
HIDE_EMPTY_POLICIES = {"never": "kNever", "after-first-system": "kAfterFirstSystem", "all-systems": "kAllSystems"}
POINTS_PER_MM = 72 / 25.4


def _set_layout(operation: dict[str, Any], label: str) -> dict[str, Any]:
    """Validate set-layout. The Layout Options it sets are worked out when it
    runs (layout_dictionary), since an orientation on its own and left or
    right margins depend on the layout's current settings."""
    known = {"op", "pageSize", "orientation", "pageWidth", "pageHeight", "hideEmptyStaves", "layout",
             *LAYOUT_NUMBERS}
    if unknown := sorted(operation.keys() - known):
        raise DoricoBatchError(f"{label}: unknown set-layout fields {unknown}; allowed: {', '.join(sorted(known - {'op'}))}")
    if "extraSpacesBelowVocalStaves" in operation:
        raise DoricoBatchError(f"{label}.extraSpacesBelowVocalStaves has no Layout Option in Dorico")
    settings: dict[str, Any] = {}
    if "pageSize" in operation:
        size = operation["pageSize"]
        if size not in PAGE_SIZES:
            raise DoricoBatchError(f"{label}.pageSize must be one of: {', '.join(PAGE_SIZES)}")
        if size not in PAGE_POINTS:
            raise DoricoBatchError(
                f"{label}.pageSize {size} is not supported on Dorico (its size is ambiguous); "
                "give pageWidth and pageHeight in millimetres"
            )
        settings["pageSize"] = size
    if ("pageWidth" in operation) != ("pageHeight" in operation):
        raise DoricoBatchError(f"{label}: give pageWidth and pageHeight together")
    if "pageWidth" in operation:
        if "pageSize" in operation:
            raise DoricoBatchError(f"{label}: give pageSize or pageWidth/pageHeight, not both")
        for field in ("pageWidth", "pageHeight"):
            settings[field] = _number(operation, field, label, 50, 1000)
    if "orientation" in operation:
        if operation["orientation"] not in ORIENTATIONS:
            raise DoricoBatchError(f"{label}.orientation must be one of: {', '.join(ORIENTATIONS)}")
        settings["orientation"] = operation["orientation"]
    for field, (_, low, high) in LAYOUT_NUMBERS.items():
        if field in operation and field != "extraSpacesBelowVocalStaves":
            settings[field] = _number(operation, field, label, low, high)
    if "hideEmptyStaves" in operation:
        if operation["hideEmptyStaves"] not in HIDE_EMPTY_POLICIES:
            raise DoricoBatchError(f"{label}.hideEmptyStaves must be one of: {', '.join(HIDE_EMPTY_POLICIES)}")
        settings["hideEmptyStaves"] = operation["hideEmptyStaves"]
    if not settings:
        raise DoricoBatchError(f"{label}: set-layout needs at least one setting")
    out: dict[str, Any] = {"op": "set-layout", "settings": settings}
    if "layout" in operation:
        layout = operation["layout"]
        if isinstance(layout, bool) or not isinstance(layout, (str, int)) or layout == "":
            raise DoricoBatchError(f"{label}.layout must be a layout's name or layoutID")
        out["layout"] = layout
    return out


def _number(operation: dict[str, Any], field: str, label: str, low: float, high: float) -> float:
    value = operation.get(field)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not low <= value <= high:
        raise DoricoBatchError(f"{label}.{field} must be a number from {low} to {high}")
    return value


def choose_layout(requested: Any, layouts: list[dict[str, Any]], label: str) -> dict[str, Any]:
    """The layout set-layout changes: the one named (or with that layoutID),
    else the project's only full score layout."""
    if requested is None:
        full = [lay for lay in layouts if lay.get("layoutType") == "kFullScoreLayout"]
        if len(full) == 1:
            return full[0]
        names = ", ".join(str(lay.get("layoutName")) for lay in layouts)
        raise DoricoBatchError(f"{label}: say which layout to change (\"layout\"): {names}")
    for lay in layouts:
        if requested == lay.get("layoutID") or (
            isinstance(requested, str) and requested.casefold() == str(lay.get("layoutName", "")).casefold()
        ):
            return lay
    names = ", ".join(f"{lay.get('layoutName')} ({lay.get('layoutID')})" for lay in layouts)
    raise DoricoBatchError(f"{label}: no layout {requested!r}; layouts: {names}")


def layout_dictionary(settings: dict[str, Any], current: dict[str, str], label: str) -> dict[str, str]:
    """The Layout Options (path -> value text) that apply set-layout's settings
    to a layout whose current options are `current`."""
    out: dict[str, str] = {}
    width = height = None
    if "pageSize" in settings:
        width, height = PAGE_POINTS[settings["pageSize"]]
    elif "pageWidth" in settings:
        width, height = settings["pageWidth"] * POINTS_PER_MM, settings["pageHeight"] * POINTS_PER_MM
    orientation = settings.get("orientation")
    if orientation is not None and width is None:
        width, height = float(current[PAGE_WIDTH]), float(current[PAGE_HEIGHT])
    if width is not None and height is not None:
        if orientation == "landscape":
            width, height = max(width, height), min(width, height)
        elif orientation == "portrait":
            width, height = min(width, height), max(width, height)
        out[PAGE_WIDTH], out[PAGE_HEIGHT] = _points(width), _points(height)
    if "staffSize" in settings:
        # Sibelius's staff size is the staff's height, four spaces.
        out[SPACE_SIZE] = _points(settings["staffSize"] / 4 * POINTS_PER_MM)
    if ("leftMargin" in settings or "rightMargin" in settings) and current.get(MARGIN_TYPE) != "kIdentical":
        raise DoricoBatchError(
            f"{label}: this layout's page margins are {current.get(MARGIN_TYPE)}, so left and right "
            "differ between pages; set Page margins to Same in Layout Options first"
        )
    for field, path in LAYOUT_MM_KEYS.items():
        if field in settings:
            out[path] = _points(settings[field] * POINTS_PER_MM)
    for field, path in LAYOUT_SPACE_KEYS.items():
        if field in settings:
            out[path] = _points(settings[field])
    if "hideEmptyStaves" in settings:
        out[HIDE_EMPTY] = HIDE_EMPTY_POLICIES[settings["hideEmptyStaves"]]
    return out


def _points(value: float) -> str:
    return f"{value:.6f}"


def layout_command(layout_id: int, open_score_id: int, options: dict[str, str]) -> str:
    """Project.Layout.SetOptions as Layout Options' Apply sends it (logged
    2026-09-28): the Dictionary is key and value strings, commas escaped."""
    pairs = []
    for path, value in options.items():
        if any(ch in path + value for ch in ',"\\&\n'):
            raise DoricoBatchError(f"cannot send the layout option {path} = {value!r}")
        pairs.append(f'{{string: "{path}"}}\\, {{string: "{value}"}}')
    return (f"Project.Layout.SetOptions?LayoutIDArray={layout_id}&Dictionary=list: "
            + "\\, ".join(pairs) + f"&OpenScoreID={open_score_id}")


def layout_report(current: dict[str, str]) -> dict[str, Any]:
    """A layout's page setup in set-layout's terms (millimetres, staff spaces)."""
    def mm(path: str) -> float | None:
        try:
            return round(float(current[path]) / POINTS_PER_MM, 2)
        except (KeyError, ValueError):
            return None

    width, height = mm(PAGE_WIDTH), mm(PAGE_HEIGHT)
    report: dict[str, Any] = {"pageWidth": width, "pageHeight": height}
    if width is not None and height is not None:
        report["orientation"] = "landscape" if width > height else "portrait"
        w_pt, h_pt = float(current[PAGE_WIDTH]), float(current[PAGE_HEIGHT])
        report["pageSize"] = next(
            (name for name, (w, h) in PAGE_POINTS.items()
             if abs(min(w_pt, h_pt) - w) < 0.5 and abs(max(w_pt, h_pt) - h) < 0.5),
            "custom",
        )
    try:
        report["staffSize"] = round(float(current[SPACE_SIZE]) * 4 / POINTS_PER_MM, 2)
    except (KeyError, ValueError):
        pass
    for field, path in LAYOUT_MM_KEYS.items():
        report[field] = mm(path)
    for field, path in LAYOUT_SPACE_KEYS.items():
        try:
            report[field] = float(current[path])
        except (KeyError, ValueError):
            report[field] = None
    policy = current.get(HIDE_EMPTY)
    report["hideEmptyStaves"] = next((k for k, v in HIDE_EMPTY_POLICIES.items() if v == policy), policy)
    report["marginType"] = current.get(MARGIN_TYPE)
    return report


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
        if "id" not in event:
            raise DoricoBatchError(
                f"{label}: staff {event['staff']} was read from a MusicXML export, so its notes have no ids "
                "and cannot be transposed"
            )
        try:
            pitch, letter = transpose_spelled(event.get("name"), event["pitch"], steps, semitones)
        except DoricoBatchError as exc:
            raise DoricoBatchError(f"{label}: event {event['id']}: {exc}") from exc
        item = {
            "op": "set-pitch", "stream": event["stream"], "id": event["id"], "type": event["type"],
            "position": event["flowPosition"], "oldPitch": event["pitch"], "newPitch": pitch, "letter": letter,
        }
        if event.get("source") == "dump":
            item.update(op="repitch", select={"id": event["id"], "stream": event["stream"]}, name=event.get("name"))
        out.append(item)
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
