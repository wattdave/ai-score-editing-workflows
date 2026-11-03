"""Tests for scripts/dev/extract_dorico_qml.py on a synthetic rcc-style blob."""

import struct
import zlib
from pathlib import Path

from helpers import load_script

extract_dorico_qml = load_script(Path(__file__).parent.parent / "scripts" / "dev" / "extract_dorico_qml.py")

PLAIN = "// header\nimport QtQuick 2.15\nDoricoDialog {\n    title: qsTr(\"Project Statistics\")\n}\n"
PACKED = "import QtQuick 2.15\nItem {\n    onClicked: controller.doThing()\n}\n"


def test_carves_plain_and_zlib_files_and_writes_an_index(tmp_path: Path) -> None:
    plain = PLAIN.encode()
    packed = zlib.compress(PACKED.encode())
    blob = (b"\x00" * 50 + struct.pack(">I", len(plain)) + plain + b"\x00" * 30
            + struct.pack(">II", len(packed) + 4, len(PACKED)) + packed + b"\x00" * 20)
    binary = tmp_path / "Dorico"
    binary.write_bytes(blob)
    assert list(extract_dorico_qml.carve_plain(blob).values()) == [PLAIN]
    assert list(extract_dorico_qml.carve_zlib(blob).values()) == [PACKED]
    assert extract_dorico_qml.extract(binary, tmp_path / "out") == 2
    index = (tmp_path / "out" / "INDEX.txt").read_text()
    assert "DoricoDialog" in index and "Project Statistics" in index and "controller.doThing" in index
