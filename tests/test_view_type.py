"""ScoreBridge reports the Page or Panorama view in GetScoreInfo."""

import re
from pathlib import Path

from ai_score_editing.sibelius import bridge

PLUGIN = Path(__file__).resolve().parents[1] / "src/ai_score_editing/sibelius/manuscript/ScoreBridge.plg"


def test_get_score_info_returns_view_type() -> None:
    source = PLUGIN.read_text(encoding="utf-8")
    block = re.search(r'\tGetScoreInfo "\(\) \{(.*?)\n\t\}"', source, re.S)
    assert block is not None
    body = block.group(1)
    assert "'viewType', Sibelius.GetCurrentScoreViewType()" in body
    assert body.index("RequireScore()") < body.index("GetCurrentScoreViewType")


def test_view_type_bridge_version_is_released() -> None:
    assert bridge.VIEW_TYPE_BRIDGE_VERSION <= bridge.CURRENT_BRIDGE_VERSION
