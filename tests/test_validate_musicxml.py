"""Independent schema validation of the MusicXML our tools write."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import validate_musicxml as vm  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"
GOLDEN = FIXTURES / "golden"
SPLIT_SCRIPT = ROOT / ".claude" / "skills" / "satb-part-splitting" / "scripts" / "split_satb.py"

pytestmark = pytest.mark.skipif(shutil.which("xmllint") is None, reason="needs xmllint (libxml2-utils)")


def test_bundled_schema_is_used_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MUSICXML_XSD", raising=False)
    schema = vm.find_schema()
    assert schema == vm.BUNDLED_XSD
    assert "Version 4.0" in schema.read_text()[:1500]
    locations = re.findall(r'schemaLocation="([^"]*)"', schema.read_text())
    assert locations == ["xml.xsd", "xlink.xsd"]  # local, so --nonet validation works


@pytest.mark.parametrize(
    "path",
    [
        FIXTURES / "satb_two_staff.musicxml",
        FIXTURES / "dorico-upgrade-fixture.musicxml",
        GOLDEN / "satb_split.musicxml",
        GOLDEN / "satb_split_solos.musicxml",
        GOLDEN / "satb_reconnect.musicxml",
    ],
    ids=lambda p: p.name,
)
def test_repo_musicxml_is_schema_valid(path: Path) -> None:
    assert vm.validate(path) == []


def test_fresh_split_output_is_schema_valid(tmp_path: Path) -> None:
    out = tmp_path / "split.musicxml"
    subprocess.run(
        [sys.executable, str(SPLIT_SCRIPT), "split", str(FIXTURES / "satb_two_staff.musicxml"), "-o", str(out)],
        check=True, capture_output=True,
    )
    assert vm.validate(out) == []


def test_invalid_file_is_reported(tmp_path: Path) -> None:
    text = (FIXTURES / "satb_two_staff.musicxml").read_text()
    broken = tmp_path / "bad.musicxml"
    broken.write_text(text.replace("<duration>2</duration>", "<duration>x</duration>", 1).replace("</part-list>", "<bogus/></part-list>", 1))
    errors = vm.validate(broken)
    assert any("positive-divisions" in e for e in errors)
    assert any("bogus" in e for e in errors)


def test_malformed_xml_is_reported(tmp_path: Path) -> None:
    broken = tmp_path / "broken.musicxml"
    broken.write_text("<score-partwise><part></score-partwise>")
    assert vm.validate(broken)


def test_mxl_is_unpacked_and_checked(tmp_path: Path) -> None:
    source = (FIXTURES / "satb_two_staff.musicxml").read_bytes()
    good = tmp_path / "good.mxl"
    with zipfile.ZipFile(good, "w") as z:
        z.writestr("META-INF/container.xml", '<container><rootfiles><rootfile full-path="s.xml"/></rootfiles></container>')
        z.writestr("s.xml", source)
    assert vm.validate(good) == []
    bad = tmp_path / "bad.mxl"
    with zipfile.ZipFile(bad, "w") as z:
        z.writestr("s.xml", source.replace(b"<duration>2</duration>", b"<duration>x</duration>", 1))
    assert vm.validate(bad)


def test_cli_exit_codes(tmp_path: Path) -> None:
    ok = FIXTURES / "satb_two_staff.musicxml"
    bad = tmp_path / "bad.musicxml"
    bad.write_text("<score-partwise/>")
    assert vm.main([str(ok)]) == 0
    assert vm.main([str(ok), str(bad)]) == 1
