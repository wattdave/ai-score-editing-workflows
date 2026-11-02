"""Golden-file regression tests for the MusicXML splitting entry points.

Covers every ``split_satb.py`` subcommand and ``polychoral.demix_16voices`` on
small fixtures.  Regenerate with ``UPDATE_GOLDEN=1 uv run pytest tests/test_split_golden.py``
and review the diff before committing.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
GOLDEN = FIXTURES / "golden"
SCRIPT = ROOT / ".claude" / "skills" / "satb-part-splitting" / "scripts" / "split_satb.py"
SATB_FIXTURE = FIXTURES / "satb_two_staff.musicxml"
POLY_FIXTURE = FIXTURES / "polychoral_raw_12.musicxml"


def _check(name: str, actual: bytes) -> None:
    path = GOLDEN / name
    if os.environ.get("UPDATE_GOLDEN"):
        path.write_bytes(actual)
    assert path.read_bytes() == actual, f"{name} differs from golden file"


def _run(tmp_path: Path, *args: str) -> tuple[int, bytes]:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), *args], capture_output=True, text=True, cwd=ROOT
    )
    text = f"rc={proc.returncode}\n--stdout--\n{proc.stdout}--stderr--\n{proc.stderr}"
    return proc.returncode, text.replace(str(tmp_path), "<TMP>").replace(str(FIXTURES), "<FIX>").encode()


def test_split_default(tmp_path: Path) -> None:
    out = tmp_path / "satb.musicxml"
    rc, log = _run(tmp_path, "split", str(SATB_FIXTURE), "-o", str(out), "--copy-lyrics-to-tb")
    assert rc == 0
    _check("satb_split.musicxml", out.read_bytes())
    _check("satb_split.log", log)


def test_split_solos_no_reconnect(tmp_path: Path) -> None:
    out = tmp_path / "satb.musicxml"
    rc, log = _run(
        tmp_path, "split", str(SATB_FIXTURE), "-o", str(out),
        "--soprano-solo", "3", "--tenor-solo", "2", "--bass-solo", "4", "--no-reconnect-lyrics",
    )
    assert rc == 0
    _check("satb_split_solos.musicxml", out.read_bytes())
    _check("satb_split_solos.log", log)


def test_audit_validate_reconnect(tmp_path: Path) -> None:
    _, log = _run(tmp_path, "audit", str(SATB_FIXTURE))
    _check("satb_audit.log", log)

    out = tmp_path / "satb.musicxml"
    _run(tmp_path, "split", str(SATB_FIXTURE), "-o", str(out))
    _, log = _run(tmp_path, "validate", str(out))
    _check("satb_validate.log", log)

    rec = tmp_path / "reconnected.musicxml"
    _, log = _run(tmp_path, "reconnect-lyrics", str(SATB_FIXTURE), "-o", str(rec))
    _check("satb_reconnect.musicxml", rec.read_bytes())
    _check("satb_reconnect.log", log)


def test_demix_16voices(tmp_path: Path) -> None:
    from ai_score_editing.polychoral import demix_16voices, validate_16voices

    out = tmp_path / "poly16.musicxml"
    result = demix_16voices(POLY_FIXTURE, out)
    summary = json.dumps(result, indent=2, sort_keys=True, default=str)
    summary = summary.replace(str(tmp_path), "<TMP>").replace(str(FIXTURES), "<FIX>")
    _check("poly16.musicxml", out.read_bytes())
    _check("poly16.json", summary.encode())
    _check("poly16_validate.json", json.dumps(validate_16voices(out), indent=2).encode())
