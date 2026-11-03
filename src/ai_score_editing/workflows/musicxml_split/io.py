"""MusicXML input/output shared by all splitter profiles."""

from __future__ import annotations

import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path


def parse_musicxml(path: Path) -> tuple[ET.ElementTree, ET.Element]:
    if path.suffix.lower() != ".mxl":
        tree = ET.parse(path)
        return tree, tree.getroot()
    with zipfile.ZipFile(path) as archive:
        root_name = None
        if "META-INF/container.xml" in archive.namelist():
            container = ET.parse(archive.open("META-INF/container.xml"))
            rootfile = container.find(".//{*}rootfile")
            if rootfile is None:
                rootfile = container.find(".//rootfile")
            root_name = rootfile.attrib.get("full-path") if rootfile is not None else None
        if not root_name:
            root_name = next(
                (name for name in archive.namelist() if name.endswith(".xml") and not name.startswith("META-INF/")),
                None,
            )
        if not root_name:
            raise ValueError(f"No score XML file found in archive {path}")
        tree = ET.parse(archive.open(root_name))
        return tree, tree.getroot()


def save_musicxml(root: ET.Element, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    if path.suffix.lower() != ".mxl":
        path.write_bytes(data)
        return
    container = '''<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="score.xml" media-type="application/vnd.recordare.musicxml+xml"/></rootfiles></container>'''
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("META-INF/container.xml", container)
        archive.writestr("score.xml", data)
