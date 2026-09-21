"""CLI tests for split-parts / demix subcommand."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sibelius_websocket_cli.cli import (
    EXIT_COMMAND_FAILED,
    EXIT_OK,
    _run_split_parts,
    build_parser,
    main,
)
from sibelius_websocket_cli.polychoral import make_rest, save_musicxml
import xml.etree.ElementTree as ET


def _create_minimal_valid_score(xml_path: Path) -> None:
    """Create a minimal 8-part open-score MusicXML file for testing."""
    root = ET.Element("score-partwise", version="3.1")
    pl = ET.SubElement(root, "part-list")
    for i in range(1, 9):
        sp = ET.SubElement(pl, "score-part", id=f"P{i}")
        ET.SubElement(sp, "part-name").text = f"Staff {i}"

    for i in range(1, 9):
        p = ET.SubElement(root, "part", id=f"P{i}")
        m = ET.SubElement(p, "measure", number="1")
        if i == 1:
            attrs = ET.SubElement(m, "attributes")
            divs = ET.SubElement(attrs, "divisions")
            divs.text = "256"
            time_el = ET.SubElement(attrs, "time")
            ET.SubElement(time_el, "beats").text = "4"
            ET.SubElement(time_el, "beat-type").text = "4"
        m.append(make_rest(1024))

    save_musicxml(root, xml_path)


def test_split_parts_parser_defaults() -> None:
    parser = build_parser()
    args = parser.parse_args(["split-parts"])
    assert args.subcommand == "split-parts"
    assert args.score_file is None
    assert args.file_opt is None
    assert args.preset == "16voices"
    assert args.validate is True
    assert args.open is False


def test_demix_alias_and_custom_options() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "demix",
            "my_score.mxl",
            "-o",
            "custom_out.mxl",
            "--no-validate",
            "--open",
        ]
    )
    assert args.subcommand == "demix"
    assert args.score_file == "my_score.mxl"
    assert args.out == "custom_out.mxl"
    assert args.validate is False
    assert args.open is True


def test_split_parts_missing_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    parser = build_parser()
    args = parser.parse_args(["split-parts", str(tmp_path / "non_existent.mxl")])
    exit_code = pytest.run_sync(_run_split_parts(args)) if hasattr(pytest, "run_sync") else None


@pytest.mark.asyncio
async def test_split_parts_missing_file_async(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    parser = build_parser()
    args = parser.parse_args(["split-parts", str(tmp_path / "non_existent.mxl")])
    ret = await _run_split_parts(args)
    assert ret == EXIT_COMMAND_FAILED
    captured = capsys.readouterr()
    assert "does not exist" in captured.err


@pytest.mark.asyncio
async def test_split_parts_offline_musicxml(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    in_file = tmp_path / "input.musicxml"
    out_file = tmp_path / "output.mxl"
    _create_minimal_valid_score(in_file)

    parser = build_parser()
    args = parser.parse_args(["split-parts", str(in_file), "-o", str(out_file)])
    ret = await _run_split_parts(args)
    assert ret == EXIT_OK
    assert out_file.exists()

    captured = capsys.readouterr()
    assert "Demixed 1 measures across 16 parts (16voices)" in captured.out
    assert "Validation passed: 0 discrepancies found." in captured.out


@pytest.mark.asyncio
async def test_split_parts_offline_json_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    in_file = tmp_path / "input.musicxml"
    out_file = tmp_path / "output.mxl"
    _create_minimal_valid_score(in_file)

    parser = build_parser()
    args = parser.parse_args(["--json", "split-parts", str(in_file), "-o", str(out_file)])
    ret = await _run_split_parts(args)
    assert ret == EXIT_OK

    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["totalMeasures"] == 1
    assert data["partsCount"] == 16
    assert data["valid"] is True


@pytest.mark.asyncio
async def test_split_parts_with_open_flag(tmp_path: Path) -> None:
    in_file = tmp_path / "input.musicxml"
    out_file = tmp_path / "output.mxl"
    _create_minimal_valid_score(in_file)

    parser = build_parser()
    args = parser.parse_args(["split-parts", str(in_file), "-o", str(out_file), "--open"])
    with patch("sibelius_websocket_cli.launcher.open_score_file") as mock_open:
        ret = await _run_split_parts(args)
        assert ret == EXIT_OK
        mock_open.assert_called_once_with(out_file, app_path=None)


@pytest.mark.asyncio
async def test_split_parts_satb_and_audit_mode(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    in_file = tmp_path / "input.musicxml"
    output = tmp_path / "satb.mxl"
    _create_minimal_valid_score(in_file)
    parser = build_parser()
    args = parser.parse_args(["--json", "split-parts", str(in_file), "--preset", "satb", "-o", str(output)])
    assert await _run_split_parts(args) == EXIT_OK
    assert output.exists()
    assert json.loads(capsys.readouterr().out)["partsCount"] == 4

    audit = parser.parse_args(["--json", "split-parts", str(in_file), "--preset", "satb", "--audit"])
    assert await _run_split_parts(audit) == EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["outputFile"] is None
    assert payload["audit"]


@pytest.mark.asyncio
async def test_split_parts_active_score_roundtrip(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    export_target = tmp_path / "fake_exported.musicxml"
    _create_minimal_valid_score(export_target)
    out_file = tmp_path / "split_from_active.mxl"

    mock_client = AsyncMock()
    mock_context = MagicMock()
    mock_context.__aenter__.return_value = mock_client

    async def fake_bridge(client: object, method: str, args_list: list[object] | None = None) -> dict[str, object]:
        if method == "GetScoreInfo":
            return {"fileName": str(tmp_path / "ActiveSong.sib")}
        elif method == "ExportScore":
            # copy our valid minimal score to the target export path
            assert args_list is not None
            dest = Path(args_list[0])  # type: ignore
            dest.write_bytes(export_target.read_bytes())
            return {"success": True}
        return {}

    parser = build_parser()
    args = parser.parse_args(["split-parts", "-o", str(out_file)])

    with patch("sibelius_websocket_cli.cli._client", return_value=mock_context), \
         patch("sibelius_websocket_cli.cli._check_bridge_version", new_callable=AsyncMock), \
         patch("sibelius_websocket_cli.cli._bridge", side_effect=fake_bridge):
        ret = await _run_split_parts(args)
        assert ret == EXIT_OK
        assert out_file.exists()
