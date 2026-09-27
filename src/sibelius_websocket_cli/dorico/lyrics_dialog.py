"""Read and replace a player's line of lyrics through Dorico's Edit Lyrics dialog.

Lua cannot read a staff with lyrics (docs/dorico.md), but Dorico's
"Edit Line of Lyrics…" dialog shows a whole verse as hyphenated text and
takes an edited one back. The dialog works on the first staff of the
selection, so the window is switched to the player's part layout first:

  Window.SwitchToLayout (the part) -> Edit.SelectAll -> Filter.LyricsLine<n>
  -> Edit.LineOfLyrics -> read or set the text area (System Events) -> OK
  or Cancel -> switch back to the layout and mode the window had.

Only edits with the same number of syllables are applied by Dorico, so any
other edit is refused here; every edit is read back to confirm it.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from .bridge import DoricoBridge
from .client import DoricoError
from .export import _osascript, bring_to_front

DIALOG = "Edit Lyrics"
DIALOG_TIMEOUT = 8.0
LAYOUT_SWITCH_DELAY = 1.0

_DIALOG_OPEN = """
tell application "System Events"
  tell process "%(process)s"
    if exists window "Edit Lyrics" then return "yes"
    return "no"
  end tell
end tell
"""

# argv: new text ("" to only read), button ("OK", "Cancel" or "" to leave open).
_DIALOG_ACT = """
on run argv
  set newText to item 1 of argv
  set buttonName to item 2 of argv
  tell application "System Events"
    tell process "%(process)s"
      set items_ to entire contents of window "Edit Lyrics"
      set t to ""
      repeat with i from 1 to count of items_
        set e to item i of items_
        if (get role of e) is "AXTextArea" then
          if newText is not "" then
            set value of e to newText
            delay 0.3
          end if
          set t to (get value of e) as text
        end if
      end repeat
      if buttonName is not "" then
        repeat with i from 1 to count of items_
          set e to item i of items_
          if (get role of e) is "AXButton" then
            try
              if ((get name of e) as text) is buttonName then
                click e
                return t
              end if
            end try
          end if
        end repeat
      end if
      return t
    end tell
  end tell
end run
"""


def syllable_count(text: str) -> int:
    """Syllables as the dialog writes them: words split by spaces, then hyphens."""
    return sum(len([p for p in word.split("-") if p]) for word in text.split())


def _normal(text: str) -> str:
    return " ".join(text.split())


def _dialog_open() -> bool:
    return _osascript(_DIALOG_OPEN) == "yes"


async def _wait(condition: Any, timeout: float, what: str) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            raise DoricoError(f"timed out waiting for {what}")
        await asyncio.sleep(0.2)


async def _part_layout(bridge: DoricoBridge, player: str) -> dict[str, Any]:
    layouts = await bridge.client.layouts()
    parts = [l for l in layouts if l.get("layoutType") == "kPartLayout"]
    match = [l for l in parts if l["layoutName"].strip().lower() == player.strip().lower()]
    if not match:
        names = ", ".join(l["layoutName"] for l in parts)
        raise DoricoError(f"no part layout named {player!r}; parts: {names}")
    return match[0]


async def _in_dialog(bridge: DoricoBridge, player: str, verse: int, new_text: str | None) -> str:
    """Open the dialog on the player's verse, read it, optionally replace it."""
    if not 1 <= verse <= 5:
        raise DoricoError("verse must be 1-5")
    if _dialog_open():
        raise DoricoError("Dorico's Edit Lyrics dialog is already open; close it first")
    client = bridge.client
    part = await _part_layout(bridge, player)
    status = await client.status()
    score_id, view_id = status.get("activeOpenScoreID"), status.get("activeViewContainerID")
    mode = status.get("windowMode")
    original_layout = (await bridge.call("window"))["layoutID"]
    bring_to_front()
    try:
        if mode != "kWriteMode":
            await client.command("Window.SwitchMode?WindowMode=kWriteMode")
        await client.command(
            f"Window.SwitchToLayout?OpenScoreID={score_id}&ScoreLayoutViewContainerID={view_id}&LayoutID={part['layoutID']}"
        )
        await asyncio.sleep(LAYOUT_SWITCH_DELAY)
        await client.command("Edit.SelectAll")
        await client.command(f"Filter.LyricsLine{verse}")
        if (await client.status()).get("selectedEventType") != "kLyricEvent":
            raise DoricoError(f"{player} has no lyrics in verse {verse}")
        await client.command("Edit.LineOfLyrics")
        await _wait(_dialog_open, DIALOG_TIMEOUT, "the Edit Lyrics dialog")
        current = _osascript(_DIALOG_ACT, "", "")
        if new_text is None:
            return current
        if syllable_count(new_text) != syllable_count(current):
            raise DoricoError(
                f"the new text has {syllable_count(new_text)} syllables but {player}'s verse {verse} has "
                f"{syllable_count(current)}; Dorico only applies edits that keep the count"
            )
        _osascript(_DIALOG_ACT, new_text, "OK")
        await _wait(lambda: not _dialog_open(), DIALOG_TIMEOUT, "Dorico to accept the edit")
        return current
    finally:
        if _dialog_open():
            _osascript(_DIALOG_ACT, "", "Cancel")
        await client.command(
            f"Window.SwitchToLayout?OpenScoreID={score_id}&ScoreLayoutViewContainerID={view_id}&LayoutID={original_layout}"
        )
        if mode and mode != "kWriteMode":
            await client.command(f"Window.SwitchMode?WindowMode={mode}")


async def read_lyrics(bridge: DoricoBridge, player: str, verse: int = 1) -> dict[str, Any]:
    text = await _in_dialog(bridge, player, verse, None)
    return {"player": player, "verse": verse, "text": _normal(text), "syllables": syllable_count(text)}


async def edit_lyrics(bridge: DoricoBridge, player: str, text: str, verse: int = 1) -> dict[str, Any]:
    """Replace a player's verse (same syllable count) and read it back."""
    if not text.strip():
        raise DoricoError("text is empty")
    before = await _in_dialog(bridge, player, verse, text)
    after = await _in_dialog(bridge, player, verse, None)
    if _normal(after) != _normal(text):
        raise DoricoError(f"Dorico did not apply the edit; {player}'s verse {verse} still reads: {_normal(after)[:80]}…")
    return {"player": player, "verse": verse, "before": _normal(before), "after": _normal(after)}
