#!/usr/bin/env python3
"""Convert an OMR-produced MusicXML or compressed MusicXML file to ABC.

The converter deliberately preserves every MusicXML part and voice as a
separate ABC voice.  It makes no musical corrections: this is important for
PDF reconstruction, where questionable OMR output must remain auditable.
"""

from __future__ import annotations

import argparse
import io
import zipfile
from collections import defaultdict
from pathlib import Path
from xml.etree import ElementTree as ET


FIFTHS_TO_KEY = {
    -7: "Cb", -6: "Gb", -5: "Db", -4: "Ab", -3: "Eb", -2: "Bb",
    -1: "F", 0: "C", 1: "G", 2: "D", 3: "A", 4: "E", 5: "B",
    6: "F#", 7: "C#",
}


def child_text(element: ET.Element, path: str, default: str = "") -> str:
    child = element.find(path)
    return child.text.strip() if child is not None and child.text else default


def read_musicxml(path: Path) -> ET.Element:
    """Read either a plain MusicXML document or the root score from an MXL."""
    if path.suffix.lower() != ".mxl":
        return ET.parse(path).getroot()
    with zipfile.ZipFile(path) as archive:
        container = ET.fromstring(archive.read("META-INF/container.xml"))
        rootfile = container.find(".//rootfile")
        if rootfile is None or not rootfile.get("full-path"):
            raise ValueError(f"No MusicXML root file declared in {path}")
        return ET.parse(io.BytesIO(archive.read(rootfile.get("full-path")))).getroot()


def duration_token(duration: int, divisions: int) -> str:
    """Express a MusicXML duration in ABC's L:1/8 units."""
    numerator = duration * 2
    denominator = divisions
    if numerator == denominator:
        return ""
    if denominator and numerator % denominator == 0:
        return str(numerator // denominator)
    if numerator == 1:
        return f"/{denominator}" if denominator != 2 else "/"
    return f"{numerator}/{denominator}"


def pitch_token(note: ET.Element) -> str:
    """Render a written MusicXML pitch as an ABC token."""
    pitch = note.find("pitch")
    if pitch is None:
        return "z"
    step = child_text(pitch, "step").upper()
    alter = int(child_text(pitch, "alter", "0"))
    octave = int(child_text(pitch, "octave", "4"))
    accidental = {2: "^^", 1: "^", 0: "", -1: "_", -2: "__"}.get(alter)
    if accidental is None:
        raise ValueError(f"Unsupported accidental {alter} in {ET.tostring(note, encoding='unicode')}")
    if octave == 4:
        letter = step
    elif octave == 5:
        letter = step.lower()
    elif octave > 5:
        letter = step.lower() + "'" * (octave - 5)
    else:
        letter = step + "," * (4 - octave)
    return accidental + letter


def lyric_token(note: ET.Element) -> str | None:
    lyric = note.find("lyric")
    if lyric is None:
        return None
    text = child_text(lyric, "text")
    if not text:
        return None
    syllabic = child_text(lyric, "syllabic")
    return text + ("-" if syllabic in {"begin", "middle"} else "")


def measure_tokens(measure: ET.Element, divisions: int) -> dict[str, tuple[list[str], list[str]]]:
    """Return ABC music and lyric tokens per MusicXML voice for one measure."""
    cursor = 0
    events: dict[str, list[dict[str, object]]] = defaultdict(list)
    last_event: dict[str, dict[str, object]] = {}
    for element in measure:
        if element.tag == "backup":
            cursor -= int(child_text(element, "duration", "0"))
            continue
        if element.tag == "forward":
            cursor += int(child_text(element, "duration", "0"))
            continue
        if element.tag != "note":
            continue
        voice = child_text(element, "voice", "1")
        duration = int(child_text(element, "duration", "0"))
        is_chord_tone = element.find("chord") is not None
        if is_chord_tone and voice in last_event:
            event = last_event[voice]
            event["pitches"].append(pitch_token(element))  # type: ignore[index]
            continue
        event = {
            "offset": cursor,
            "duration": duration,
            "pitches": [pitch_token(element)],
            "lyric": lyric_token(element),
        }
        events[voice].append(event)
        last_event[voice] = event
        cursor += duration

    result: dict[str, tuple[list[str], list[str]]] = {}
    for voice, voice_events in events.items():
        music: list[str] = []
        lyrics: list[str] = []
        position = 0
        for event in sorted(voice_events, key=lambda item: int(item["offset"])):
            offset = int(event["offset"])
            if offset > position:
                music.append("z" + duration_token(offset - position, divisions))
                lyrics.append("*")
            pitches = event["pitches"]  # type: ignore[assignment]
            duration = duration_token(int(event["duration"]), divisions)
            if pitches == ["z"]:
                music.append("z" + duration)
                lyrics.append("*")
            elif len(pitches) == 1:
                music.append(pitches[0] + duration)
                lyrics.append(event["lyric"] or "*")
            else:
                music.append("[" + "".join(pitches) + "]" + duration)
                lyrics.append(event["lyric"] or "*")
            position = max(position, offset + int(event["duration"]))
        result[voice] = music, lyrics
    return result


def convert(root: ET.Element) -> str:
    title = child_text(root, "work/work-title") or child_text(root, "movement-title") or "Untitled OMR reconstruction"
    parts = root.findall("part")
    key = "C"
    meter = "4/4"
    voices: dict[str, dict[str, list[str]]] = {}
    voice_names: dict[str, str] = {}
    for part_index, part in enumerate(parts, 1):
        divisions = 1
        for measure in part.findall("measure"):
            attrs = measure.find("attributes")
            if attrs is not None:
                divisions = int(child_text(attrs, "divisions", str(divisions)))
                fifths = child_text(attrs, "key/fifths")
                if fifths:
                    key = FIFTHS_TO_KEY.get(int(fifths), "C")
                beats = child_text(attrs, "time/beats")
                beat_type = child_text(attrs, "time/beat-type")
                if beats and beat_type:
                    meter = f"{beats}/{beat_type}"
            for xml_voice, (music, lyrics) in measure_tokens(measure, divisions).items():
                voice_id = f"P{part_index}_{xml_voice}"
                if voice_id not in voices:
                    voices[voice_id] = {"music": [], "lyrics": []}
                    voice_names[voice_id] = f"Part {part_index}, voice {xml_voice}"
                voices[voice_id]["music"].extend(music + ["|"])
                voices[voice_id]["lyrics"].extend(lyrics + ["*"])

    lines = [
        "% Generated mechanically from MusicXML.  Review OMR output before performance.",
        "X:1",
        f"T:{title}",
        f"M:{meter}",
        "L:1/8",
        f"K:{key}",
    ]
    for voice_id, data in voices.items():
        lines.append(f'V:{voice_id} name="{voice_names[voice_id]}"')
    for voice_id, data in voices.items():
        lines.append(f"[V:{voice_id}] " + " ".join(data["music"]))
        if any(token != "*" for token in data["lyrics"]):
            lines.append("w: " + " ".join(data["lyrics"]))
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="MusicXML (.xml/.musicxml) or compressed MusicXML (.mxl)")
    parser.add_argument("output", type=Path, help="Destination ABC file")
    args = parser.parse_args()
    args.output.write_text(convert(read_musicxml(args.input)), encoding="utf-8")


if __name__ == "__main__":
    main()
