"""Profile-independent routing and score assembly primitives."""

from __future__ import annotations

import copy
from xml.etree.ElementTree import Element

from .model import NoteEvent, SplitIssue, TargetPart

SEMITONES = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
NOTE_TAG_ORDER = ["grace", "cue", "chord", "pitch", "rest", "unpitched", "duration", "tie", "instrument", "footnote", "level", "voice", "type", "dot", "accidental", "time-modification", "stem", "notehead", "notehead-text", "staff", "beam", "notations", "lyric", "play", "listen"]


def midi(note: Element) -> int:
    pitch = note.find("pitch")
    if pitch is None or not pitch.findtext("step") or not pitch.findtext("octave"):
        return -1
    # MusicXML alter is a decimal ("-1.0" in some exports, "0.5" for a quarter tone).
    alter = round(float(pitch.findtext("alter") or "0"))
    return 12 * (int(pitch.findtext("octave") or "0") + 1) + SEMITONES[pitch.findtext("step") or "C"] + alter


def clean_note(note: Element, voice: str = "1") -> Element:
    clone = copy.deepcopy(note)
    for tag in ("staff", "chord", "stem", "instrument"):
        child = clone.find(tag)
        if child is not None:
            clone.remove(child)
    v = clone.find("voice")
    if v is None:
        v = Element("voice")
        voice_rank = NOTE_TAG_ORDER.index("voice")
        position = next(
            (
                index
                for index, child in enumerate(clone)
                if child.tag in NOTE_TAG_ORDER and NOTE_TAG_ORDER.index(child.tag) > voice_rank
            ),
            len(clone),
        )
        clone.insert(position, v)
    v.text = voice
    return clone


def make_rest(duration: int, whole_measure: bool = False) -> Element:
    note = Element("note")
    rest = Element("rest")
    if whole_measure:
        rest.set("measure", "yes")
    note.append(rest)
    duration_el = Element("duration")
    duration_el.text = str(duration)
    note.append(duration_el)
    voice = Element("voice")
    voice.text = "1"
    note.append(voice)
    return note


def _lyrics(notes: tuple[Element, ...], chosen: Element) -> Element:
    clone = clean_note(chosen)
    if not clone.findall("lyric"):
        for note in notes:
            lyrics = note.findall("lyric")
            if lyrics:
                clone.extend(copy.deepcopy(lyrics))
                break
    return clone


def select_pitch_slot(event: NoteEvent, slot_from_top: int, slots: int, duplicate_slots: dict[int, int] | None, issues: list[SplitIssue], measure: str) -> Element | None:
    if event.notes[0].find("rest") is not None:
        return clean_note(event.notes[0])
    pitches = sorted((note for note in event.notes if midi(note) >= 0), key=midi, reverse=True)
    if len(pitches) > slots:
        issues.append(SplitIssue("error", "unsupported-pitch-count", f"{len(pitches)} simultaneous pitches exceed {slots} supported slots; source was not silently reduced", measure, f"{event.part_id}/staff {event.staff}/voice {event.voice}/onset {event.onset}"))
        return None
    source_slot = slot_from_top
    if source_slot >= len(pitches):
        source_slot = (duplicate_slots or {}).get(slot_from_top, -1)
    if source_slot < 0 or source_slot >= len(pitches):
        issues.append(SplitIssue("error", "missing-pitch-slot", f"Pitch slot {slot_from_top + 1} is unavailable", measure, f"{event.part_id}/staff {event.staff}/voice {event.voice}/onset {event.onset}"))
        return None
    return _lyrics(event.notes, pitches[source_slot])


def route_pitch_slots(events: list[NoteEvent], targets: list[str], duplicate_slots: dict[int, int] | None, issues: list[SplitIssue], measure: str) -> dict[str, list[tuple[int, int, Element]]]:
    routed = {target: [] for target in targets}
    for event in events:
        for slot, target in enumerate(targets):
            selected = select_pitch_slot(event, slot, len(targets), duplicate_slots, issues, measure)
            if selected is not None:
                routed[target].append((event.onset, event.duration, selected))
    return routed


def route_two_voices(events: list[NoteEvent], targets: tuple[str, str], issues: list[SplitIssue], measure: str, allow_unison: bool = True) -> dict[str, list[tuple[int, int, Element]]]:
    pitched = [event for event in events if event.notes[0].find("rest") is None]
    voices = sorted({event.voice for event in pitched})
    if len(voices) > 2:
        issues.append(SplitIssue("error", "ambiguous-xml-voices", f"{len(voices)} XML voices cannot be combined into two monophonic targets", measure, ", ".join(voices)))
        return {target: [] for target in targets}
    if len(voices) == 2:
        routed = {target: [] for target in targets}
        for event in events:
            target = targets[0] if event.voice == voices[0] else targets[1]
            selected = select_pitch_slot(event, 0 if target == targets[0] else len(event.notes) - 1, max(1, len(event.notes)), None, issues, measure)
            if selected is not None:
                routed[target].append((event.onset, event.duration, selected))
        return routed
    return route_pitch_slots(events, list(targets), {1: 0} if allow_unison else None, issues, measure)


def render_monophonic(events: list[tuple[int, int, Element]], duration: int, target: str, issues: list[SplitIssue], measure: str) -> list[Element]:
    """Fill explicit time gaps with rests without trimming or altering note durations."""
    result: list[Element] = []
    cursor = 0
    for onset, event_duration, note in sorted(events, key=lambda item: (item[0], item[1] == 0)):
        if event_duration == 0:
            result.append(note)
            continue
        if onset < cursor:
            issues.append(SplitIssue("error", "target-overlap", f"Target {target} has overlapping events at onset {onset}", measure, target))
            continue
        if onset > cursor:
            result.append(make_rest(onset - cursor))
        result.append(note)
        cursor = onset + event_duration
    if cursor == 0:
        return [make_rest(duration, whole_measure=True)]
    if cursor < duration:
        result.append(make_rest(duration - cursor))
    elif cursor > duration:
        issues.append(SplitIssue("error", "target-overflow", f"Target {target} reaches {cursor}, expected {duration}; no duration was shortened", measure, target))
    return result


def part_list(targets: list[TargetPart], groups: list[tuple[str, range]] | None = None) -> Element:
    root = Element("part-list")
    starts = {members.start: (str(index + 1), name) for index, (name, members) in enumerate(groups or [])}
    ends = {members.stop: str(index + 1) for index, (_, members) in enumerate(groups or [])}
    for index, target in enumerate(targets):
        if index in starts:
            number, name = starts[index]
            group = Element("part-group", number=number, type="start")
            name_el = Element("group-name"); name_el.text = name; group.append(name_el)
            symbol = Element("group-symbol"); symbol.text = "bracket"; group.append(symbol)
            barline = Element("group-barline"); barline.text = "yes"; group.append(barline)
            root.append(group)
        score_part = Element("score-part", id=target.id)
        for tag, value in (("part-name", target.name), ("part-abbreviation", target.abbreviation)):
            child = Element(tag); child.text = value; score_part.append(child)
        instrument = Element("score-instrument", id=f"{target.id}-I1")
        name_el = Element("instrument-name"); name_el.text = target.name; instrument.append(name_el)
        sound = Element("instrument-sound"); sound.text = target.sound; instrument.append(sound)
        score_part.append(instrument)
        midi_el = Element("midi-instrument", id=f"{target.id}-I1")
        channel = Element("midi-channel"); channel.text = target.midi_channel; midi_el.append(channel)
        program = Element("midi-program"); program.text = "53"; midi_el.append(program)
        score_part.append(midi_el)
        root.append(score_part)
        if index + 1 in ends:
            root.append(Element("part-group", number=ends[index + 1], type="stop"))
    return root


def attributes_with_clef(original: Element | None, target: TargetPart) -> Element:
    attrs = Element("attributes")
    if original is not None:
        for child in original:
            if child.tag not in {"clef", "staves"}:
                attrs.append(copy.deepcopy(child))
    clef = Element("clef")
    sign = Element("sign"); sign.text = target.clef_sign; clef.append(sign)
    line = Element("line"); line.text = target.clef_line; clef.append(line)
    if target.clef_octave is not None:
        octave = Element("clef-octave-change"); octave.text = target.clef_octave; clef.append(octave)
    attrs.append(clef)
    return attrs
