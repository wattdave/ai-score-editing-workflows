"""Non-destructive structural validation for generated MusicXML scores."""

from __future__ import annotations

from pathlib import Path

from .io import parse_musicxml
from .model import SplitIssue
from .routing import midi
from .timeline import measure_duration_state, timelines_by_part


def validate_file(path: Path | str, expected_parts: int | None = None) -> list[SplitIssue]:
    score_path = Path(path)
    if not score_path.exists():
        return [SplitIssue("error", "file-not-found", f"File not found: {score_path}")]
    _, root = parse_musicxml(score_path)
    parts = root.findall("part")
    issues: list[SplitIssue] = []
    if expected_parts is not None and len(parts) != expected_parts:
        issues.append(SplitIssue("error", "part-count", f"Expected {expected_parts} parts, found {len(parts)}"))
    timelines = timelines_by_part(root, issues)
    expected = measure_duration_state(parts)
    counts = {part_id: len(values) for part_id, values in timelines.items()}
    if len(set(counts.values())) > 1:
        issues.append(SplitIssue("error", "measure-count", f"Inconsistent measure counts: {counts}"))
    for part_id, values in timelines.items():
        for index, timeline in enumerate(values):
            declared = expected[index] if index < len(expected) else timeline.duration
            sounding = [event for event in timeline.events if event.duration > 0]
            if sounding and max(event.onset + event.duration for event in sounding) < declared:
                issues.append(SplitIssue("error", "measure-underflow", f"Measure ends before declared duration {declared}", timeline.number, part_id))
            # The target streams must be monophonic.  Source voices are still
            # represented in the timeline, so this catches accidental merging.
            by_onset: dict[int, list[object]] = {}
            for event in sounding:
                by_onset.setdefault(event.onset, []).append(event)
            if any(len(events) > 1 for events in by_onset.values()):
                issues.append(SplitIssue("error", "target-overlap", "Multiple rhythmic events share an onset in a monophonic part", timeline.number, part_id))
        active_ties: set[int] = set()
        for timeline in values:
            for event in timeline.events:
                for note in event.notes:
                    if note.find("rest") is not None:
                        continue
                    pitch = midi(note)
                    ties = {tie.attrib.get("type") for tie in note.findall("tie")} | {tie.attrib.get("type") for tie in note.findall(".//tied")}
                    if "stop" in ties and pitch not in active_ties:
                        issues.append(SplitIssue("warning", "unmatched-tie-stop", "Tie stop has no matching previous start", timeline.number, part_id))
                    if "stop" in ties:
                        active_ties.discard(pitch)
                    if "start" in ties:
                        active_ties.add(pitch)
        for pitch in sorted(active_ties):
            issues.append(SplitIssue("error", "dangling-tie", f"Tie start for MIDI pitch {pitch} has no matching stop", source=part_id))
    return issues
