"""The autouse fixture in conftest.py keeps tests out of the real home folder."""

import os
from pathlib import Path


def test_home_and_xdg_point_inside_tmp_path(tmp_path: Path) -> None:
    for name in ("HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME"):
        assert Path(os.environ[name]).is_relative_to(tmp_path), name
    assert Path.home().is_relative_to(tmp_path)
