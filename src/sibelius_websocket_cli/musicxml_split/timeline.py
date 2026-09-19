"""Cursor-accurate conversion of MusicXML measures into onset events."""

from __future__ import annotations

from collections import defaultdict
from xml.etree.ElementTree import Element

from .model import MeasureTimeline, NoteEvent, SplitIssue


def _duration(element: Element) -> int:
    text = element.findtext("duration")
    try:
        return int(text) if text else 0
    except ValueError:
        return 0


def timeline_for_measure(
    measure: Element,
    part_id: str,
    expected_duration: int,
    issues: list[SplitIssue],
) -> MeasureTimeline:
    """Parse notes, ``backup`` and ``forward`` using the MusicXML time cursor.

    A chord note is deliberately joined only to the immediately preceding event
    with the same staff, XML voice, onset, and duration.  This preserves separate
    XML voices even when they happen to sound at the same time.
    """
    cursor = high_water = 0
    events: list[NoteEvent] = []
    last_event: dict[tuple[str, str], int] = {}
    number = measure.attrib.get("number", "?")
    for order, child in enumerate(measure):
        if child.tag == "backup":
            cursor -= _duration(child)
            if cursor < 0:
                issues.append(SplitIssue("error", "cursor-underflow", "<backup> moves before the measure start", number, part_id))
                cursor = 0
            continue
        if child.tag == "forward":
            cursor += _duration(child)
            high_water = max(high_water, cursor)
            continue
        if child.tag != "note":
            continue
        staff = child.findtext("staff") or "1"
        voice = child.findtext("voice") or "1"
        duration = 0 if child.find("grace") is not None else _duration(child)
        key = (staff, voice)
        if child.find("chord") is not None:
            event_index = last_event.get(key)
            if event_index is None:
                issues.append(SplitIssue("error", "orphan-chord", "A <chord> has no preceding base note in its staff and XML voice", number, f"{part_id}/staff {staff}/voice {voice}"))
                onset = cursor
            else:
                previous = events[event_index]
                onset = previous.onset
                if previous.duration != duration:
                    issues.append(SplitIssue("error", "chord-duration-mismatch", "Chord members have different MusicXML durations", number, part_id))
                events[event_index] = NoteEvent(previous.onset, previous.duration, part_id, staff, voice, previous.notes + (child,), previous.source_order)
                continue
        else:
            onset = cursor
        event = NoteEvent(onset, duration, part_id, staff, voice, (child,), order)
        events.append(event)
        last_event[key] = len(events) - 1
        if child.find("chord") is None and duration:
            cursor += duration
            high_water = max(high_water, cursor)
    actual = max(high_water, max((event.onset + event.duration for event in events), default=0))
    if expected_duration and actual > expected_duration:
        issues.append(SplitIssue("error", "measure-overflow", f"MusicXML cursor reaches {actual}, expected {expected_duration}; no duration was shortened", number, part_id))
    return MeasureTimeline(number, max(expected_duration, actual), sorted(events, key=lambda event: (event.onset, event.source_order)), part_id, measure)


def measure_duration_state(parts: list[Element]) -> list[int]:
    """Return declared durations, carrying divisions and meter across measures."""
    if not parts:
        return []
    count = max(len(part.findall("measure")) for part in parts)
    divisions, beats, beat_type = 1, 4, 4
    result: list[int] = []
    for index in range(count):
        for part in parts:
            measures = part.findall("measure")
            if index >= len(measures):
                continue
            attrs = measures[index].find("attributes")
            if attrs is None:
                continue
            if attrs.findtext("divisions"):
                divisions = int(attrs.findtext("divisions") or "1")
            time = attrs.find("time")
            if time is not None and time.findtext("beats") and time.findtext("beat-type"):
                beats, beat_type = int(time.findtext("beats") or "4"), int(time.findtext("beat-type") or "4")
            break
        result.append(beats * 4 * divisions // beat_type)
    return result


def timelines_by_part(root: Element, issues: list[SplitIssue]) -> dict[str, list[MeasureTimeline]]:
    parts = root.findall("part")
    durations = measure_duration_state(parts)
    return {
        part.attrib.get("id", "?"): [timeline_for_measure(measure, part.attrib.get("id", "?"), durations[index], issues) for index, measure in enumerate(part.findall("measure"))]
        for part in parts
    }
