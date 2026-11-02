"""Find the file behind a MuseScore window, through macOS Accessibility.

The plug-in API has no score path (docs/musescore.md), but each MuseScore
window reports its document as AXDocument. Every window is its own
"mscore" process, so all of them are searched for the score's name.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

from ai_score_editing import macos

SCRIPT = """
set out to ""
tell application "System Events"
  repeat with p in (every process whose name is "mscore")
    repeat with w in (windows of p)
      try
        set out to out & (name of w) & tab & (value of attribute "AXDocument" of w) & linefeed
      end try
    end repeat
  end repeat
end tell
return out
"""


def windows() -> list[tuple[str, str]]:
    """(window title, document URL) for every MuseScore window; [] when it cannot be read."""
    if sys.platform != "darwin":
        return []
    try:
        stdout = macos.osascript_sync(SCRIPT)
    except (OSError, subprocess.TimeoutExpired, macos.OsascriptError):
        return []
    out = []
    for line in stdout.splitlines():
        title, _, document = line.partition("\t")
        if document and document != "missing value":
            out.append((title, document))
    return out


def score_file(score_name: str, found: list[tuple[str, str]] | None = None) -> Path | None:
    """The local file of the window showing score_name, or None (never saved, or not found)."""
    for title, document in windows() if found is None else found:
        if title.lstrip("*").strip() != score_name:
            continue
        url = urlparse(document)
        if url.scheme == "file":
            return Path(unquote(url.path))
    return None
