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

Selecting is an undo step in Dorico, so a read undoes its Select All and
Filter afterwards, each only when the Edit menu names it as the step on top
(Undo Filter Lyrics, Undo Select All); anything else is left alone.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from .bridge import DoricoBridge
from .client import DoricoError
from .export import osascript, bring_to_front

DIALOG = "Edit Lyrics"
DIALOG_TIMEOUT = 8.0
LAYOUT_SWITCH_DELAY = 1.0
#: Edit menu titles of the undo steps a read leaves, top first (Dorico 6.2.30,
#: English UI). Another language will not match, and nothing is undone.
READ_UNDO_TITLES = ("Undo Filter Lyrics", "Undo Select All")
#: The Edit menu's titles lag behind commands by up to about a second.
MENU_SETTLE_TIMEOUT = 4.0
MENU_POLL = 0.3

_UNDO_TITLE = """
tell application "System Events"
  tell process "%(process)s"
    return name of menu item 1 of menu 1 of menu bar item "Edit" of menu bar 1
  end tell
end tell
"""

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


async def _dialog_open() -> bool:
    return await osascript(_DIALOG_OPEN) == "yes"


async def _dialog_closed() -> bool:
    return not await _dialog_open()


async def _wait(condition: Any, timeout: float, what: str) -> None:
    deadline = time.monotonic() + timeout
    while not await condition():
        if time.monotonic() > deadline:
            raise DoricoError(f"timed out waiting for {what}")
        await asyncio.sleep(0.2)


async def _undo_title(changed_from: str | None = None) -> str:
    """The Edit menu's undo title once it has settled (read twice alike, and
    different from changed_from when given)."""
    deadline = time.monotonic() + MENU_SETTLE_TIMEOUT
    last = None
    while True:
        title = await osascript(_UNDO_TITLE)
        if title == last and title != changed_from:
            return title
        if time.monotonic() > deadline:
            return title
        last = title
        await asyncio.sleep(MENU_POLL)


async def _undo_read_steps(bridge: DoricoBridge, titles: list[str]) -> bool:
    """Undo the selection steps a read made, top first, each only while the
    Edit menu names it on top. False if anything else was there."""
    previous = None
    for expected in titles:
        title = await _undo_title(previous)
        if title != expected:
            return False
        await bridge.client.command("Edit.Undo")
        previous = title
    return True


async def _part_layout(bridge: DoricoBridge, player: str) -> dict[str, Any]:
    layouts = await bridge.client.layouts()
    parts = [l for l in layouts if l.get("layoutType") == "kPartLayout"]
    match = [l for l in parts if l["layoutName"].strip().lower() == player.strip().lower()]
    if not match:
        names = ", ".join(l["layoutName"] for l in parts)
        raise DoricoError(f"no part layout named {player!r}; Dorico keeps lyrics per part layout, one of: {names}")
    return match[0]


async def _in_dialog(bridge: DoricoBridge, player: str, verse: int, new_text: str | None) -> tuple[str, bool]:
    """Open the dialog on the player's verse, read it, optionally replace it.

    Returns the verse's text before any edit, and whether a read left the
    undo history as it found it (an edit leaves its selections under it).
    """
    if not 1 <= verse <= 5:
        raise DoricoError("verse must be 1-5")
    if await _dialog_open():
        raise DoricoError("Dorico's Edit Lyrics dialog is already open; close it first")
    client = bridge.client
    part = await _part_layout(bridge, player)
    status = await client.status()
    score_id, view_id = status.get("activeOpenScoreID"), status.get("activeViewContainerID")
    mode = status.get("windowMode")
    original_layout = (await bridge.call("window"))["layoutID"]
    selections: list[str] = []  # undo titles of the selection steps made, in order
    kept = False
    await bring_to_front()
    try:
        if mode != "kWriteMode":
            await client.command("Window.SwitchMode?WindowMode=kWriteMode")
        await client.command(
            f"Window.SwitchToLayout?OpenScoreID={score_id}&ScoreLayoutViewContainerID={view_id}&LayoutID={part['layoutID']}"
        )
        await asyncio.sleep(LAYOUT_SWITCH_DELAY)
        await client.command("Edit.SelectAll")
        selections.append(READ_UNDO_TITLES[1])
        await client.command(f"Filter.LyricsLine{verse}")
        selections.append(READ_UNDO_TITLES[0])
        if (await client.status()).get("selectedEventType") != "kLyricEvent":
            raise DoricoError(f"{player} has no lyrics in verse {verse}")
        await client.command("Edit.LineOfLyrics")
        await _wait(_dialog_open, DIALOG_TIMEOUT, "the Edit Lyrics dialog")
        current = await osascript(_DIALOG_ACT, "", "")
        if new_text is not None:
            await _replace(current, new_text, player, verse)
            await _wait(_dialog_closed, DIALOG_TIMEOUT, "Dorico to accept the edit")
            selections.clear()  # now under the edit: undoing them would undo it
    finally:
        if await _dialog_open():
            await osascript(_DIALOG_ACT, "", "Cancel")
        await client.command(
            f"Window.SwitchToLayout?OpenScoreID={score_id}&ScoreLayoutViewContainerID={view_id}&LayoutID={original_layout}"
        )
        if mode and mode != "kWriteMode":
            await client.command(f"Window.SwitchMode?WindowMode={mode}")
        if selections:
            kept = await _undo_read_steps(bridge, selections[::-1])
    return current, kept


async def _replace(current: str, new_text: str, player: str, verse: int) -> None:
    """Set the open dialog's text and press OK, if the syllable count is kept."""
    if syllable_count(new_text) != syllable_count(current):
        raise DoricoError(
            f"the new text has {syllable_count(new_text)} syllables but {player}'s verse {verse} has "
            f"{syllable_count(current)}; Dorico only applies edits that keep the count"
        )
    await osascript(_DIALOG_ACT, new_text, "OK")


async def read_lyrics(bridge: DoricoBridge, player: str, verse: int = 1) -> dict[str, Any]:
    text, kept = await _in_dialog(bridge, player, verse, None)
    result = {"player": player, "verse": verse, "text": _normal(text), "syllables": syllable_count(text)}
    if not kept:
        result["note"] = ("the read's selections could not be identified in Dorico's Edit menu, so they "
                          "were left in the undo history (2 steps)")
    return result


async def edit_lyrics(bridge: DoricoBridge, player: str, text: str, verse: int = 1) -> dict[str, Any]:
    """Replace a player's verse (same syllable count) and read it back."""
    if not text.strip():
        raise DoricoError("text is empty")
    before, _ = await _in_dialog(bridge, player, verse, text)
    after, kept = await _in_dialog(bridge, player, verse, None)
    if _normal(after) != _normal(text):
        raise DoricoError(f"Dorico did not apply the edit; {player}'s verse {verse} still reads: {_normal(after)[:80]}…")
    # Select All, Filter and the edit; the read-back undoes its own selections.
    return {"player": player, "verse": verse, "before": _normal(before), "after": _normal(after),
            "undoSteps": 3 if kept else 5}
