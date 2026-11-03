"""Tie repair helpers for split scores."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from .routing import insert_note_child, midi


def heal_ties(root: ET.Element) -> tuple[int, int]:
    """Ensure every start tie connects to a matching pitch and prune dangling ties."""
    stops_added = 0
    dangling_removed = 0
    for part in root.findall("part"):
        notes = []
        for m in part.findall("measure"):
            for n in m.findall("note"):
                if n.find("grace") is None and n.find("rest") is None:
                    notes.append((m.attrib.get("number"), n))
        for i in range(len(notes) - 1):
            _, n1 = notes[i]
            _, n2 = notes[i + 1]
            p1 = midi(n1)
            p2 = midi(n2)
            has_start = any(
                t.attrib.get("type") == "start"
                for t in n1.findall("tie") + n1.findall(".//tied")
            )
            if has_start:
                if p1 == p2:
                    if not any(t.attrib.get("type") == "stop" for t in n2.findall("tie")):
                        tie_elem = ET.Element("tie", type="stop")
                        insert_note_child(n2, tie_elem)
                        notations = n2.find("notations")
                        if notations is None:
                            notations = ET.Element("notations")
                            insert_note_child(n2, notations)
                        ET.SubElement(notations, "tied", type="stop")
                        stops_added += 1
                else:
                    for t in list(n1.findall("tie")):
                        if t.attrib.get("type") == "start":
                            n1.remove(t)
                            dangling_removed += 1
                    notations = n1.find("notations")
                    if notations is not None:
                        for td in list(notations.findall("tied")):
                            if td.attrib.get("type") == "start":
                                notations.remove(td)
        if notes:
            _, last_n = notes[-1]
            for t in list(last_n.findall("tie")):
                if t.attrib.get("type") == "start":
                    last_n.remove(t)
                    dangling_removed += 1
            notations = last_n.find("notations")
            if notations is not None:
                for td in list(notations.findall("tied")):
                    if td.attrib.get("type") == "start":
                        notations.remove(td)

    return stops_added, dangling_removed
