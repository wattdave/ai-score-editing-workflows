"""SATB profile for conventional two-staff choral reductions."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree.ElementTree import Element

from ..io import parse_musicxml, save_musicxml
from ..model import NoteEvent, SplitIssue, SplitResult, TargetPart
from ..routing import attributes_with_clef, clean_note, part_list, route_two_voices, select_pitch_slot, render_monophonic
from ..timeline import timelines_by_part

SATB_PARTS = [
    TargetPart("P1", "Soprano", "S.", "G", "2", None, "voice.soprano", "1"),
    TargetPart("P2", "Alto", "A.", "G", "2", None, "voice.alto", "2"),
    TargetPart("P3", "Tenor", "T.", "G", "2", "-1", "voice.tenor", "3"),
    TargetPart("P4", "Bass", "B.", "F", "4", None, "voice.bass", "4"),
]


@dataclass(frozen=True)
class SATBOptions:
    soprano_solo_bars: frozenset[int] = field(default_factory=frozenset)
    tenor_solo_bars: frozenset[int] = field(default_factory=frozenset)
    bass_solo_bars: frozenset[int] = field(default_factory=frozenset)


def _staff_events(events: list[NoteEvent], staff: str) -> list[NoteEvent]:
    return [event for event in events if event.staff == staff]


def _solo(events: list[NoteEvent], target: str, upper: bool, issues: list[SplitIssue], measure: str) -> dict[str, list[tuple[int, int, Element]]]:
    result: list[tuple[int, int, Element]] = []
    for event in events:
        slot = 0 if upper else max(0, len(event.notes) - 1)
        selected = select_pitch_slot(event, slot, max(1, len(event.notes)), None, issues, measure)
        if selected is not None:
            result.append((event.onset, event.duration, selected))
    return {target: result}


def _shared_elements(measure: Element, targets: dict[str, Element]) -> None:
    for child in measure:
        if child.tag == "direction":
            copied = copy.deepcopy(child)
            staff = copied.find("staff")
            target = "P3" if staff is not None and staff.text == "2" else "P1"
            if staff is not None:
                copied.remove(staff)
            targets[target].append(copied)
        elif child.tag == "harmony":
            copied = copy.deepcopy(child)
            staff = copied.find("staff")
            if staff is not None:
                copied.remove(staff)
            targets["P1"].append(copied)


def split_satb(
    input_file: Path | str,
    output_file: Path | str | None,
    options: SATBOptions | None = None,
    *,
    audit_only: bool = False,
) -> SplitResult:
    """Route a two-staff SATB reduction without changing source durations."""
    options = options or SATBOptions()
    input_path = Path(input_file)
    _, root = parse_musicxml(input_path)
    issues: list[SplitIssue] = []
    all_timelines = timelines_by_part(root, issues)
    if not all_timelines:
        raise ValueError("No parts found in input MusicXML")
    source_id = next(iter(all_timelines))
    source = root.find(f"part[@id='{source_id}']")
    assert source is not None
    timelines = all_timelines[source_id]
    target_parts = {target.id: Element("part", id=target.id) for target in SATB_PARTS}
    audit: list[dict[str, object]] = []

    for index, timeline in enumerate(timelines):
        try:
            bar_number = int(timeline.number)
        except ValueError:
            bar_number = -1
        upper, lower = _staff_events(timeline.events, "1"), _staff_events(timeline.events, "2")
        if bar_number in options.soprano_solo_bars:
            routed = _solo(upper, "P1", True, issues, timeline.number)
            routed["P2"] = []
            layout = "soprano-solo"
        else:
            routed = route_two_voices(upper, ("P1", "P2"), issues, timeline.number)
            layout = "upper-two-part"
        if bar_number in options.tenor_solo_bars:
            routed.update(_solo(lower, "P3", True, issues, timeline.number))
            routed["P4"] = []
            layout += "+tenor-solo"
        elif bar_number in options.bass_solo_bars:
            routed["P3"] = []
            routed.update(_solo(lower, "P4", False, issues, timeline.number))
            layout += "+bass-solo"
        else:
            routed.update(route_two_voices(lower, ("P3", "P4"), issues, timeline.number))
            layout += "+lower-two-part"
        audit.append({"measure": timeline.number, "layout": layout, "sources": {target: source_id for target in ("P1", "P2", "P3", "P4")}})
        if audit_only:
            continue
        source_measure = source.findall("measure")[index]
        measures = {target.id: Element("measure", number=timeline.number) for target in SATB_PARTS}
        if "implicit" in source_measure.attrib:
            for measure in measures.values():
                measure.set("implicit", source_measure.attrib["implicit"])
        original_attributes = source_measure.find("attributes")
        if original_attributes is not None or index == 0:
            for target in SATB_PARTS:
                measures[target.id].append(attributes_with_clef(original_attributes, target))
        _shared_elements(source_measure, measures)
        for target in SATB_PARTS:
            measures[target.id].extend(render_monophonic(routed.get(target.id, []), timeline.duration, target.id, issues, timeline.number))
            for barline in source_measure.findall("barline"):
                measures[target.id].append(copy.deepcopy(barline))
            target_parts[target.id].append(measures[target.id])

    if audit_only:
        return SplitResult(None, [part.id for part in SATB_PARTS], len(timelines), issues, audit)
    result_root = Element(root.tag, root.attrib)
    for child in root:
        if child.tag not in {"part-list", "part"}:
            result_root.append(copy.deepcopy(child))
    result_root.append(part_list(SATB_PARTS, [("Choir", range(0, 4))]))
    for target in SATB_PARTS:
        result_root.append(target_parts[target.id])
    path = Path(output_file) if output_file is not None else None
    if path is not None:
        save_musicxml(result_root, path)
    return SplitResult(path, [part.id for part in SATB_PARTS], len(timelines), issues, audit)
