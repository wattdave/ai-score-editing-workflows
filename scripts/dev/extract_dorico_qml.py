#!/usr/bin/env python3
"""Extract the QML sources compiled into Dorico's main binary.

Dorico's UI is largely QtQuick. Its .qml files are compiled into the binary
as Qt resources (rcc): each file is a 4-byte big-endian length followed by
the text, or by a zlib stream when rcc compressed it. This finds every
`import Qt…` and recovers the file around it, deduplicates by content, and
writes the files (named by content hash; rcc's name table is not parsed)
plus an INDEX.txt of each file's root type, visible titles and controller
calls. See docs/dorico.md.

    python3 scripts/dev/extract_dorico_qml.py OUTPUT_DIR [--binary PATH]
"""

from __future__ import annotations

import argparse
import hashlib
import re
import struct
import sys
import zlib
from pathlib import Path

DEFAULT_BINARY = Path("/Applications/Dorico 6.app/Contents/MacOS/Dorico 6")
MAX_PREFIX = 4096          # how far before `import Qt` a file may start
MAX_FILE = 2_000_000
ZLIB_HEADERS = re.compile(rb"\x78[\x9c\xda\x01\x5e]")


def carve_plain(data: bytes) -> dict[int, str]:
    """Uncompressed QML files: a length prefix whose span is text ending in `}`."""
    found: dict[int, str] = {}
    for match in re.finditer(rb"import Qt", data):
        hit = match.start()
        for back in range(MAX_PREFIX):
            start = hit - back
            if start < 4:
                break
            size = struct.unpack(">I", data[start - 4:start])[0]
            if size < back or size > MAX_FILE:
                continue
            try:
                text = data[start:start + size].decode("utf-8")
            except UnicodeDecodeError:
                continue
            if text.rstrip().endswith("}"):
                found.setdefault(start, text)
            break
    return found


def carve_zlib(data: bytes) -> dict[int, str]:
    """rcc-compressed QML files: zlib streams that inflate to QML."""
    found: dict[int, str] = {}
    for match in ZLIB_HEADERS.finditer(data):
        start = match.start()
        try:
            out = zlib.decompressobj().decompress(data[start:start + 400_000], 3_000_000)
        except zlib.error:
            continue
        if b"import Qt" in out[:4000] and out.rstrip().endswith(b"}"):
            found.setdefault(start, out.decode("utf-8", "replace"))
    return found


def index_line(name: str, text: str) -> str:
    body = re.sub(r"^\s*(import|pragma)[^\n]*\n", "", text, flags=re.M)
    root = re.search(r"^\s*([A-Z]\w*)\s*\{", body, re.M)
    titles = re.findall(r'qsTr\w*\(\s*"([^"]{3,50})"', text)[:4]
    calls = sorted({f"{o}.{m}" for o, m in re.findall(r"\b(controller|dialog|model|backend)\.(\w+)\s*\(", text)})
    return f"{root.group(1) if root else '?':<40} {name} {len(text):>6}  titles={titles}  calls={calls[:8]}"


def extract(binary: Path, out: Path) -> int:
    data = binary.read_bytes()
    unique: dict[str, str] = {}
    for text in [*carve_plain(data).values(), *carve_zlib(data).values()]:
        unique.setdefault(hashlib.sha1(text.encode()).hexdigest()[:10], text)
    out.mkdir(parents=True, exist_ok=True)
    lines = []
    for name, text in sorted(unique.items()):
        (out / f"{name}.qml").write_text(text)
        lines.append(index_line(f"{name}.qml", text))
    (out / "INDEX.txt").write_text("\n".join(sorted(lines)) + "\n")
    return len(unique)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("output", type=Path)
    parser.add_argument("--binary", type=Path, default=DEFAULT_BINARY)
    args = parser.parse_args(argv)
    if not args.binary.exists():
        print(f"error: {args.binary} not found", file=sys.stderr)
        return 1
    count = extract(args.binary, args.output)
    print(f"wrote {count} QML files and INDEX.txt to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
