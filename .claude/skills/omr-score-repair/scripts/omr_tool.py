#!/usr/bin/env python3
"""CLI utility for auditing, unstacking, and repairing OMR artifacts in MusicXML files."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from xml.dom import minidom


def parse_xml(file_path: str | Path) -> tuple[ET.ElementTree, ET.Element]:
    path = Path(file_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    tree = ET.parse(path)
    root = tree.getroot()
    if not root.tag.endswith("score-partwise"):
        raise ValueError(f"Expected root <score-partwise>, got <{root.tag}>")
    return tree, root


def audit_score(file_path: str | Path) -> dict:
    _, root = parse_xml(file_path)
    part_list = root.find("part-list")
    parts_info = []

    for p in root.findall("part"):
        pid = p.attrib.get("id", "")
        pname = ""
        if part_list is not None:
            sp = part_list.find(f"score-part[@id='{pid}']")
            if sp is not None:
                pname = sp.findtext("part-name", "")

        measures = p.findall("measure")
        measure_details = []
        dummy_rests = []

        for m in measures:
            mnum = m.attrib.get("number", "")
            notes = m.findall("note")
            is_all_rest = bool(notes) and all(n.find("rest") is not None for n in notes)
            lyrics = [
                n.findtext(".//lyric/text", "")
                for n in notes
                if n.find(".//lyric/text") is not None
            ]
            if is_all_rest:
                dummy_rests.append(mnum)
            measure_details.append({
                "number": mnum,
                "note_count": len(notes),
                "is_all_rest": is_all_rest,
                "lyrics": [l for l in lyrics if l],
            })

        parts_info.append({
            "id": pid,
            "name": pname,
            "measure_count": len(measures),
            "dummy_rest_measures": dummy_rests,
            "measures": measure_details,
        })

    is_stacked_suspect = (
        len(parts_info) > 1
        and len({p["measure_count"] for p in parts_info}) <= 2
    )

    return {
        "file": str(Path(file_path).resolve()),
        "part_count": len(parts_info),
        "is_stacked_suspect": is_stacked_suspect,
        "parts": parts_info,
    }


def validate_score(file_path: str | Path) -> list[str]:
    _, root = parse_xml(file_path)
    issues = []

    for p in root.findall("part"):
        pid = p.attrib.get("id", "")
        current_divisions = None
        current_beats = None
        current_beat_type = None

        for m in p.findall("measure"):
            mnum = m.attrib.get("number", "")
            attrs = m.find("attributes")
            if attrs is not None:
                divs = attrs.findtext("divisions")
                if divs:
                    current_divisions = int(divs)
                time = attrs.find("time")
                if time is not None:
                    beats = time.findtext("beats")
                    btype = time.findtext("beat-type")
                    if beats and btype:
                        current_beats = int(beats)
                        current_beat_type = int(btype)

            if current_divisions and current_beats and current_beat_type:
                expected_dur = int(current_beats * (current_divisions * 4 / current_beat_type))
                actual_dur = 0
                for n in m.findall("note"):
                    if n.find("chord") is not None:
                        continue
                    dur = n.findtext("duration")
                    if dur:
                        actual_dur += int(dur)

                if actual_dur != expected_dur:
                    issues.append(
                        f"Part {pid} Measure {mnum}: duration sum {actual_dur} != expected {expected_dur}"
                    )

    return issues


def unstack_parts(
    file_path: str | Path,
    output_path: str | Path | None = None,
    prune_measures: list[str] | None = None,
    part_name: str = "Voice",
    insert_system_breaks: bool = True,
) -> Path:
    tree, root = parse_xml(file_path)
    source_path = Path(file_path).resolve()
    target_path = Path(output_path).resolve() if output_path else source_path

    # Parse prune specs: e.g. "P1:6", "1:6", or simply "P1:m6"
    prune_set = set()
    if prune_measures:
        for pm in prune_measures:
            if ":" in pm:
                p_id, m_num = pm.split(":", 1)
                prune_set.add((p_id.strip(), m_num.strip()))
            else:
                prune_set.add(("", pm.strip()))

    parts = root.findall("part")
    if not parts:
        raise ValueError("No <part> elements found in score")

    # Create new score structure
    new_root = ET.Element("score-partwise", version=root.attrib.get("version", "3.1"))

    # Copy work, movement, identification elements if present
    for tag in ["work", "movement-number", "movement-title", "identification", "defaults"]:
        elem = root.find(tag)
        if elem is not None:
            new_root.append(elem)

    # Rebuild part-list with single part
    part_list = ET.SubElement(new_root, "part-list")
    score_part = ET.SubElement(part_list, "score-part", id="P1")
    ET.SubElement(score_part, "part-name").text = part_name
    score_instr = ET.SubElement(score_part, "score-instrument", id="P1-I1")
    ET.SubElement(score_instr, "instrument-name").text = part_name
    midi_instr = ET.SubElement(score_part, "midi-instrument", id="P1-I1")
    ET.SubElement(midi_instr, "midi-channel").text = "1"
    ET.SubElement(midi_instr, "midi-program").text = "53"

    new_part = ET.SubElement(new_root, "part", id="P1")

    global_m_num = 1
    for p_idx, p in enumerate(parts):
        pid = p.attrib.get("id", f"P{p_idx+1}")
        measures = p.findall("measure")
        is_first_part = (p_idx == 0)

        for m_idx, m in enumerate(measures):
            mnum = m.attrib.get("number", str(m_idx + 1))
            if (pid, mnum) in prune_set or ("", mnum) in prune_set:
                continue

            # Clone measure
            m_copy = ET.Element("measure", number=str(global_m_num))

            # If start of subsequent part and system breaks requested, insert <print new-system="yes"/>
            if not is_first_part and m_idx == 0 and insert_system_breaks:
                existing_print = m.find("print")
                if existing_print is not None:
                    existing_print.set("new-system", "yes")
                else:
                    print_elem = ET.Element("print", {"new-system": "yes"})
                    m_copy.append(print_elem)

            for child in m:
                # Remove redundant clef/key/time in non-initial measures unless they changed
                if child.tag == "attributes" and not is_first_part:
                    clean_attrs = ET.Element("attributes")
                    for sub in child:
                        if sub.tag in {"divisions", "staff-details"}:
                            clean_attrs.append(sub)
                    if len(clean_attrs):
                        m_copy.append(clean_attrs)
                else:
                    m_copy.append(child)

            new_part.append(m_copy)
            global_m_num += 1

    # Ensure last bar has final barline if not present
    last_measure = new_part.findall("measure")[-1]
    if last_measure.find("barline") is None:
        bl = ET.SubElement(last_measure, "barline", location="right")
        ET.SubElement(bl, "bar-style").text = "light-heavy"

    # Backup source if writing in-place
    if target_path == source_path:
        backup_path = source_path.with_suffix(source_path.suffix + ".orig")
        if not backup_path.exists():
            shutil.copyfile(source_path, backup_path)

    # Format pretty XML
    xml_str = ET.tostring(new_root, encoding="utf-8")
    dom = minidom.parseString(xml_str)
    pretty_xml = dom.toprettyxml(indent="  ", encoding="utf-8").decode("utf-8")
    lines = [l for l in pretty_xml.splitlines() if l.strip()]
    header = """<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 3.1 Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">"""
    final_output = header + "\n" + "\n".join(lines[1:]) + "\n"

    target_path.write_text(final_output, encoding="utf-8")
    return target_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit, validate, and unstack OMR artifacts in MusicXML scores."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # audit
    p_audit = subparsers.add_parser("audit", help="Audit a MusicXML score for OMR artifacts")
    p_audit.add_argument("file", help="Path to MusicXML file")
    p_audit.add_argument("--json", action="store_true", help="Output JSON format")

    # validate
    p_val = subparsers.add_parser("validate", help="Validate measure durations in MusicXML")
    p_val.add_argument("file", help="Path to MusicXML file")

    # unstack
    p_unstack = subparsers.add_parser("unstack", help="Unstack multi-part systems into sequential lines")
    p_unstack.add_argument("file", help="Path to input MusicXML file")
    p_unstack.add_argument("-o", "--output", help="Path to output MusicXML file (default: overwrite with .orig backup)")
    p_unstack.add_argument("--prune", nargs="*", help="Measures to prune (e.g. 'P1:6' or '6')")
    p_unstack.add_argument("--part-name", default="Voice", help="Name for merged part (default: 'Voice')")
    p_unstack.add_argument("--no-system-breaks", action="store_true", help="Do not insert <print new-system='yes'/> at line starts")

    args = parser.parse_args(argv)

    if args.command == "audit":
        res = audit_score(args.file)
        if args.json:
            import json
            print(json.dumps(res, indent=2))
        else:
            print(f"File: {res['file']}")
            print(f"Parts count: {res['part_count']}")
            print(f"Stacked system suspected: {res['is_stacked_suspect']}")
            for p in res["parts"]:
                print(f"  Part {p['id']} ('{p['name']}'): {p['measure_count']} measures")
                if p["dummy_rest_measures"]:
                    print(f"    Suspected dummy rest measures: {p['dummy_rest_measures']}")
        return 0

    elif args.command == "validate":
        issues = validate_score(args.file)
        if issues:
            print("Validation issues found:", file=sys.stderr)
            for issue in issues:
                print(f"  - {issue}", file=sys.stderr)
            return 1
        print("Score validated: all measure durations match time signature.")
        return 0

    elif args.command == "unstack":
        out = unstack_parts(
            args.file,
            output_path=args.output,
            prune_measures=args.prune,
            part_name=args.part_name,
            insert_system_breaks=not args.no_system_breaks,
        )
        print(f"Unstacked score written to: {out}")
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
