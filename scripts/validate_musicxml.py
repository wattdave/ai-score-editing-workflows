#!/usr/bin/env python3
"""Validate MusicXML files against the MusicXML 4.0 schema, independently of our code.

Checks XML syntax and the schema (element order, allowed values, required
fields) with ``xmllint``. It does not check musical sense (bar lengths, chords).
``.mxl`` files are unpacked first. The schema is the W3C MusicXML 4.0 XSD
bundled in ``scripts/musicxml-schema/`` (override with ``--xsd`` or
``$MUSICXML_XSD``), so no score editor needs to be installed.

    python3 scripts/validate_musicxml.py score.musicxml other.mxl

Exit status: 0 all valid, 1 some invalid, 2 no schema or no xmllint.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

BUNDLED_XSD = Path(__file__).resolve().parent / "musicxml-schema" / "musicxml.xsd"


class ValidatorUnavailable(RuntimeError):
    """No xmllint or no schema could be found."""


def find_schema(explicit: str | Path | None = None) -> Path:
    candidates = [explicit, os.environ.get("MUSICXML_XSD"), BUNDLED_XSD]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    raise ValidatorUnavailable(
        f"MusicXML schema not found at {BUNDLED_XSD}; set MUSICXML_XSD or pass --xsd"
    )


def _score_xml(path: Path, workdir: Path) -> Path:
    """Return the score XML for ``path``, unpacking a ``.mxl`` container."""
    if path.suffix.lower() != ".mxl":
        return path
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        target = None
        if "META-INF/container.xml" in names:
            match = re.search(r'full-path="([^"]+)"', archive.read("META-INF/container.xml").decode("utf-8", "replace"))
            target = match.group(1) if match else None
        if target is None:
            target = next((n for n in names if n.lower().endswith((".xml", ".musicxml")) and not n.startswith("META-INF/")), None)
        if target is None or target not in names:
            raise ValueError(f"{path.name}: no score file inside the .mxl")
        out = workdir / "score.xml"
        out.write_bytes(archive.read(target))
        return out


def validate(path: str | Path, xsd: str | Path | None = None) -> list[str]:
    """Return schema and syntax errors for one file; empty means valid."""
    xmllint = shutil.which("xmllint")
    if xmllint is None:
        raise ValidatorUnavailable("xmllint not found (it ships with macOS; on Linux install libxml2-utils)")
    schema = find_schema(xsd)
    path = Path(path)
    with tempfile.TemporaryDirectory() as tmp:
        try:
            source = _score_xml(path, Path(tmp))
        except (ValueError, zipfile.BadZipFile) as error:
            return [str(error)]
        proc = subprocess.run(
            [xmllint, "--noout", "--nonet", "--schema", str(schema), str(source)],
            capture_output=True, text=True,
        )
    if proc.returncode == 0:
        return []
    lines = [line for line in proc.stderr.splitlines() if line.strip()]
    return [line for line in lines if not line.endswith(" validates")] or lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--xsd", help="path to musicxml.xsd")
    parser.add_argument("--max-errors", type=int, default=10, help="errors to print per file (default 10)")
    args = parser.parse_args(argv)
    bad = 0
    try:
        for file in args.files:
            errors = validate(file, args.xsd)
            if not errors:
                print(f"OK       {file}")
                continue
            bad += 1
            print(f"INVALID  {file} ({len(errors)} problem lines)")
            for line in errors[: args.max_errors]:
                print(f"  {line}")
    except ValidatorUnavailable as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
