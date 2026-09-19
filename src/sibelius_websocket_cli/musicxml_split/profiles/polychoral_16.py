"""16-voice polychoral profile; score-specific layout detection lives here."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree.ElementTree import Element

from ..io import parse_musicxml, save_musicxml
from ..model import NoteEvent, SplitIssue, SplitResult, TargetPart
from ..routing import attributes_with_clef, part_list, route_pitch_slots, route_two_voices, render_monophonic
from ..timeline import timelines_by_part

PARTS_16 = [
    TargetPart("C1_S1", "Choir 1 Soprano 1", "C1 S1", "G", "2", None, "voice.soprano", "1"),
    TargetPart("C1_S2", "Choir 1 Soprano 2", "C1 S2", "G", "2", None, "voice.soprano", "2"),
    TargetPart("C1_A1", "Choir 1 Alto 1", "C1 A1", "G", "2", None, "voice.alto", "3"),
    TargetPart("C1_A2", "Choir 1 Alto 2", "C1 A2", "G", "2", None, "voice.alto", "4"),
    TargetPart("C1_T1", "Choir 1 Tenor 1", "C1 T1", "G", "2", "-1", "voice.tenor", "5"),
    TargetPart("C1_T2", "Choir 1 Tenor 2", "C1 T2", "G", "2", "-1", "voice.tenor", "6"),
    TargetPart("C1_B1", "Choir 1 Bass 1", "C1 B1", "F", "4", None, "voice.bass", "7"),
    TargetPart("C1_B2", "Choir 1 Bass 2", "C1 B2", "F", "4", None, "voice.bass", "8"),
    TargetPart("C2_S1", "Choir 2 Soprano 1", "C2 S1", "G", "2", None, "voice.soprano", "9"),
    TargetPart("C2_S2", "Choir 2 Soprano 2", "C2 S2", "G", "2", None, "voice.soprano", "10"),
    TargetPart("C2_A1", "Choir 2 Alto 1", "C2 A1", "G", "2", None, "voice.alto", "11"),
    TargetPart("C2_A2", "Choir 2 Alto 2", "C2 A2", "G", "2", None, "voice.alto", "12"),
    TargetPart("C2_T1", "Choir 2 Tenor 1", "C2 T1", "G", "2", "-1", "voice.tenor", "13"),
    TargetPart("C2_T2", "Choir 2 Tenor 2", "C2 T2", "G", "2", "-1", "voice.tenor", "14"),
    TargetPart("C2_B1", "Choir 2 Bass 1", "C2 B1", "F", "4", None, "voice.bass", "15"),
    TargetPart("C2_B2", "Choir 2 Bass 2", "C2 B2", "F", "4", None, "voice.bass", "16"),
]
VOICE_KEYS = ("S1", "S2", "A1", "A2", "T1", "T2", "B1", "B2")


@dataclass(frozen=True)
class Polychoral16Options:
    choir_unison_indices: frozenset[int] = field(default_factory=lambda: frozenset(set(range(27)) | set(range(36, 40))))


def _staff(events: list[NoteEvent], number: str, duration: int = 0) -> list[NoteEvent]:
    selected = [event for event in events if event.staff == number]
    # Some exporters serialize the second staff after the first without a
    # MusicXML ``backup``.  That is malformed as a combined stream but has a
    # clear staff-local interpretation; rebase only when it begins at or past
    # the whole declared measure, never for an ordinary delayed entrance.
    first = min((event.onset for event in selected if event.duration), default=0)
    if duration and first >= duration:
        return [
            NoteEvent(event.onset - first, event.duration, event.part_id, event.staff, event.voice, event.notes, event.source_order)
            for event in selected
        ]
    return selected


def _has_pitch(events: list[NoteEvent]) -> bool:
    return any(event.notes[0].find("rest") is None for event in events)


def _four(events: list[NoteEvent], ids: tuple[str, str, str, str], issues: list[SplitIssue], measure: str) -> dict[str, list[tuple[int, int, Element]]]:
    voices = sorted({event.voice for event in events if event.notes[0].find("rest") is None})
    if len(voices) > 2:
        issues.append(SplitIssue("error", "ambiguous-xml-voices", f"{len(voices)} XML voices cannot be routed to a four-slot reduction", measure, ", ".join(voices)))
        return {identifier: [] for identifier in ids}
    if len(voices) == 2:
        first = [event for event in events if event.voice == voices[0]]
        second = [event for event in events if event.voice == voices[1]]
        result = route_two_voices(first, ids[:2], issues, measure)
        result.update(route_two_voices(second, ids[2:], issues, measure))
        return result
    # The explicit reduction policy is high-to-low.  Missing slots duplicate
    # the nearest declared outer voice, matching the historic profile behavior.
    return route_pitch_slots(events, list(ids), {1: 0, 2: 1, 3: 2}, issues, measure)


def split_16voices(input_file: Path | str, output_file: Path | str | None, options: Polychoral16Options | None = None, *, audit_only: bool = False) -> SplitResult:
    options = options or Polychoral16Options()
    input_path = Path(input_file)
    _, root = parse_musicxml(input_path)
    issues: list[SplitIssue] = []
    timelines = timelines_by_part(root, issues)
    if not timelines:
        raise ValueError("No parts found in input MusicXML")
    reference_id = "P1" if "P1" in timelines else next(iter(timelines))
    reference_part = root.find(f"part[@id='{reference_id}']")
    assert reference_part is not None
    count = len(timelines[reference_id])
    target_parts = {target.id: Element("part", id=target.id) for target in PARTS_16}
    audit: list[dict[str, object]] = []
    for index in range(count):
        reference = timelines[reference_id][index]
        p9 = timelines.get("P9", [])
        p11 = timelines.get("P11", [])
        short = index < len(p9) and (_has_pitch(p9[index].events) or (index < len(p11) and _has_pitch(p11[index].events)))
        routed: dict[str, list[tuple[int, int, Element]]] = {}
        source_labels: dict[str, str] = {}
        if short:
            layout = "short-score"
            for choir, source_id in (("C1", "P9"), ("C2", "P11")):
                source_timeline = timelines.get(source_id, [])[index] if index < len(timelines.get(source_id, [])) else None
                if choir == "C2" and index in options.choir_unison_indices:
                    for key in VOICE_KEYS:
                        routed[f"C2_{key}"] = copy.deepcopy(routed.get(f"C1_{key}", [])); source_labels[f"C2_{key}"] = "C1 (intentional unison)"
                    continue
                if source_timeline is None:
                    continue
                routed.update(_four(_staff(source_timeline.events, "1", reference.duration), tuple(f"{choir}_{key}" for key in VOICE_KEYS[:4]), issues, reference.number))
                routed.update(_four(_staff(source_timeline.events, "2", reference.duration), tuple(f"{choir}_{key}" for key in VOICE_KEYS[4:]), issues, reference.number))
                source_labels.update({f"{choir}_{key}": source_id for key in VOICE_KEYS})
        else:
            layout = "open-score"
            for choir, offset in (("C1", 1), ("C2", 5)):
                source_ids = [f"P{offset + n}" for n in range(4)]
                independent = any(index < len(timelines.get(source_id, [])) and _has_pitch(timelines[source_id][index].events) for source_id in source_ids)
                if choir == "C2" and not independent and index in options.choir_unison_indices:
                    for key in VOICE_KEYS:
                        routed[f"C2_{key}"] = copy.deepcopy(routed.get(f"C1_{key}", [])); source_labels[f"C2_{key}"] = "C1 (intentional unison)"
                    continue
                if not independent:
                    continue
                for pair, source_id in zip((VOICE_KEYS[0:2], VOICE_KEYS[2:4], VOICE_KEYS[4:6], VOICE_KEYS[6:8]), source_ids, strict=True):
                    events = timelines[source_id][index].events if index < len(timelines.get(source_id, [])) else []
                    routed.update(route_two_voices(events, (f"{choir}_{pair[0]}", f"{choir}_{pair[1]}"), issues, reference.number))
                    source_labels.update({f"{choir}_{key}": source_id for key in pair})
        audit.append({"measure": reference.number, "layout": layout, "sources": source_labels})
        if audit_only:
            continue
        source_measure = reference_part.findall("measure")[index]
        measures = {target.id: Element("measure", number=reference.number) for target in PARTS_16}
        if "implicit" in source_measure.attrib:
            for measure in measures.values():
                measure.set("implicit", source_measure.attrib["implicit"])
        original_attributes = source_measure.find("attributes")
        if original_attributes is not None or index == 0:
            for target in PARTS_16:
                measures[target.id].append(attributes_with_clef(original_attributes, target))
        for target in PARTS_16:
            # System directions are placed on each choir's top staff; barlines on all staves.
            if target.id in {"C1_S1", "C2_S1"}:
                for direction in source_measure.findall("direction"):
                    copied = copy.deepcopy(direction); staff = copied.find("staff")
                    if staff is not None: copied.remove(staff)
                    measures[target.id].append(copied)
            if target.id == "C1_S1":
                for harmony in source_measure.findall("harmony"):
                    copied = copy.deepcopy(harmony); staff = copied.find("staff")
                    if staff is not None: copied.remove(staff)
                    measures[target.id].append(copied)
            measures[target.id].extend(render_monophonic(routed.get(target.id, []), reference.duration, target.id, issues, reference.number))
            for barline in source_measure.findall("barline"):
                measures[target.id].append(copy.deepcopy(barline))
            target_parts[target.id].append(measures[target.id])
    if audit_only:
        return SplitResult(None, [part.id for part in PARTS_16], count, issues, audit)
    result_root = Element(root.tag, root.attrib)
    for child in root:
        if child.tag not in {"part-list", "part"}:
            result_root.append(copy.deepcopy(child))
    result_root.append(part_list(PARTS_16, [("Choir 1", range(0, 8)), ("Choir 2", range(8, 16))]))
    for target in PARTS_16:
        result_root.append(target_parts[target.id])
    path = Path(output_file) if output_file is not None else None
    if path is not None:
        save_musicxml(result_root, path)
    return SplitResult(path, [part.id for part in PARTS_16], count, issues, audit)
