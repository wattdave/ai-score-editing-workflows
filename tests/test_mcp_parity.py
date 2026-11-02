"""The three MCP servers share one set of tool shapes (README, Phase 4)."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from ai_score_editing import cli_common
from ai_score_editing.dorico import mcp_server as dorico
from ai_score_editing.dorico import service as dorico_service
from ai_score_editing.musescore import mcp_server as musescore
from ai_score_editing.musescore import service as musescore_service
from ai_score_editing.sibelius import mcp_server as sibelius
from ai_score_editing.sibelius.bridge import EXPORT_FORMATS as SIBELIUS_FORMATS

SERVERS = {"sibelius": sibelius.server, "dorico": dorico.server, "musescore": musescore.server}
CORE = ["score_overview", "score_structure", "query_score", "apply_batch", "undo", "save_score", "export_score"]

#: Parameters a back end has that the others lack, by tool: real differences
#: of the editor, and deprecated aliases.
ALLOWED_EXTRA: dict[str, dict[str, set[str]]] = {
    "score_overview": {"dorico": {"flow"}},
    "score_structure": {"dorico": {"flow"}},
    "query_score": {"dorico": {"flow", "lyrics"}},
    # backup is Dorico's opt-out of its default-on pre-apply backup (Phase 10);
    # Sibelius and MuseScore always back up before a real apply.
    "apply_batch": {"dorico": {"flow", "backup"}},
    # player is the deprecated alias of staff in Dorico's lyric tools.
    "read_lyrics": {"dorico": {"player"}},
    "edit_lyrics": {"dorico": {"player"}},
}
#: Parameters a back end lacks although the others have them.
ALLOWED_MISSING: dict[str, dict[str, set[str]]] = {
    "score_structure": {"dorico": {"bars"}},
    "query_score": {"dorico": {"fields"}},
}


def _tools(server: Any) -> dict[str, dict[str, Any]]:
    return {t.name: t.input_schema for t in asyncio.run(server.list_tools())}


TOOLS = {name: _tools(server) for name, server in SERVERS.items()}


@pytest.mark.parametrize("server", SERVERS)
def test_core_tools_exist_everywhere(server: str) -> None:
    assert not set(CORE) - set(TOOLS[server])


def test_shared_tools_have_equal_parameter_names() -> None:
    names = {tool for tools in TOOLS.values() for tool in tools}
    for tool in sorted(names):
        having = {s: set(TOOLS[s][tool].get("properties", {})) for s in TOOLS if tool in TOOLS[s]}
        if len(having) < 2:
            continue
        extras = ALLOWED_EXTRA.get(tool, {})
        missing = ALLOWED_MISSING.get(tool, {})
        for s, found in having.items():
            assert extras.get(s, set()) <= found, f"{tool}: {s} lacks allowed extra"
        core = {s: found - extras.get(s, set()) for s, found in having.items()}
        expected = set.union(*core.values())
        for s, found in core.items():
            assert found == expected - missing.get(s, set()), f"{tool}: {s} has {found}, others {expected}"


def test_canonical_shapes() -> None:
    for server, tools in TOOLS.items():
        assert "path" in tools["save_score"]["properties"], server
        assert tools["save_score"].get("required", []) == []
        props = tools["export_score"]["properties"]
        assert list(props) == ["format", "path"], server
        assert props["format"]["default"] == "pdf"
        assert tools["export_score"].get("required", []) == []
        assert tools["query_score"]["properties"]["limit"]["default"] == cli_common.DEFAULT_LIMIT, server
    for server in ("dorico", "musescore"):
        for tool in ("read_lyrics", "edit_lyrics"):
            assert "staff" in TOOLS[server][tool]["properties"]
            assert TOOLS[server][tool]["properties"]["verse"]["default"] == 1


def test_export_format_names() -> None:
    sibelius_formats = set(SIBELIUS_FORMATS)
    musescore_formats = set(musescore_service.EXPORT_FORMATS)
    dorico_formats = set(dorico_service.EXPORT_FORMATS)
    assert "midi" in sibelius_formats and "midi" in musescore_formats
    assert "mid" not in sibelius_formats | musescore_formats  # an alias, not a format name
    assert cli_common.canonical_format("MID") == "midi"
    assert {"pdf", "musicxml"} <= sibelius_formats & musescore_formats & dorico_formats
    assert {"mxl", "png"} <= sibelius_formats & musescore_formats
