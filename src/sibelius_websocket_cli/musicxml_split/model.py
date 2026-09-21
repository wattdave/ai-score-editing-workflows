"""Typed data exchanged by the deterministic MusicXML splitting engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal
from xml.etree.ElementTree import Element


@dataclass(frozen=True)
class TargetPart:
    id: str
    name: str
    abbreviation: str
    clef_sign: str
    clef_line: str
    clef_octave: str | None
    sound: str
    midi_channel: str


@dataclass(frozen=True)
class NoteEvent:
    onset: int
    duration: int
    part_id: str
    staff: str
    voice: str
    notes: tuple[Element, ...]
    source_order: int

    @property
    def is_grace(self) -> bool:
        return self.duration == 0 or any(note.find("grace") is not None for note in self.notes)


@dataclass
class MeasureTimeline:
    number: str
    duration: int
    events: list[NoteEvent]
    source_part: str
    source_measure: Element


@dataclass(frozen=True)
class SplitIssue:
    severity: Literal["warning", "error"]
    code: str
    message: str
    measure: str | None = None
    source: str | None = None

    def as_dict(self) -> dict[str, str | None]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "measure": self.measure,
            "source": self.source,
        }


@dataclass
class SplitResult:
    output_file: Path | None
    parts: list[str]
    measure_count: int
    issues: list[SplitIssue] = field(default_factory=list)
    audit: list[dict[str, object]] = field(default_factory=list)

    def as_dict(self, input_file: Path | None = None) -> dict[str, object]:
        return {
            **({"inputFile": str(input_file)} if input_file else {}),
            "outputFile": str(self.output_file) if self.output_file else None,
            "totalMeasures": self.measure_count,
            "partsCount": len(self.parts),
            "parts": self.parts,
            "issues": [issue.as_dict() for issue in self.issues],
            "audit": self.audit,
        }
