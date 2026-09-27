"""Read and set the project's Project Info fields (File > Project Info…).

Title, composer, lyricist and the rest are what Dorico's text tokens
({@projectTitle@}, {@projectComposer@}, …) show on title pages and headers,
so setting them updates every layout. Lua cannot write them (score.title is
read-only), so this drives the Project Info dialog through System Events:

- values are read straight from the dialog's fields;
- values are *typed*: setting a field's value through accessibility shows
  the text but Qt does not treat it as an edit, and Apply ignores it. Cmd-A
  is Dorico's Select All, so a field is cleared by deleting each character.

Only the project-level fields are handled; the dialog's list of flows does
not respond to accessibility (docs/dorico.md).
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from .bridge import DoricoBridge
from .client import DoricoError
from .export import _osascript, bring_to_front

FIELDS = [
    "Title", "Subtitle", "Dedication", "Composer", "Composer dates", "Composition year",
    "Work number", "Lyricist", "Arranger", "Artist", "Copyist", "Publisher", "Editor",
    "Copyright", "Other information",
]
DIALOG_TIMEOUT = 8.0

_OPEN = """
tell application "System Events"
  tell process "%(process)s"
    if exists (first window whose name starts with "Project Info") then return "yes"
    return "no"
  end tell
end tell
"""

# Every text field and text area of the dialog as "name<TAB>value" lines.
_READ = """
tell application "System Events"
  tell process "%(process)s"
    set w to (first window whose name starts with "Project Info")
    set out to ""
    set items_ to entire contents of w
    repeat with i from 1 to count of items_
      try
        set e to item i of items_
        set r to get role of e
        if r is "AXTextField" or r is "AXTextArea" then
          set out to out & ((get name of e) as text) & tab & ((get value of e) as text) & linefeed
        end if
      end try
    end repeat
    return out
  end tell
end tell
"""

# argv: field name, new value. Types the value into that field.
_TYPE = """
on run argv
  set fieldName to item 1 of argv
  set newValue to item 2 of argv
  tell application "System Events"
    tell process "%(process)s"
      set frontmost to true
      set w to (first window whose name starts with "Project Info")
      set items_ to entire contents of w
      repeat with i from 1 to count of items_
        try
          set e to item i of items_
          set r to get role of e
          if (r is "AXTextField" or r is "AXTextArea") and ((get name of e) as text) is fieldName then
            set focused of e to true
            delay 0.2
            key code 124 using command down
            set n to count of ((get value of e) as text)
            repeat n times
              key code 51
            end repeat
            if newValue is not "" then keystroke newValue
            if r is "AXTextField" then key code 48
            delay 0.3
            return (get value of e) as text
          end if
        end try
      end repeat
      error "no field " & fieldName
    end tell
  end tell
end run
"""

# argv: button name.
_PRESS = """
on run argv
  set buttonName to item 1 of argv
  tell application "System Events"
    tell process "%(process)s"
      set w to (first window whose name starts with "Project Info")
      set items_ to entire contents of w
      repeat with i from 1 to count of items_
        try
          set e to item i of items_
          if (get role of e) is "AXButton" and ((get name of e) as text) is buttonName then
            click e
            return "clicked"
          end if
        end try
      end repeat
      return "missing"
    end tell
  end tell
end run
"""


def _is_open() -> bool:
    return _osascript(_OPEN) == "yes"


async def _open(bridge: DoricoBridge) -> None:
    if _is_open():
        raise DoricoError("Dorico's Project Info dialog is already open; close it first")
    bring_to_front()
    await bridge.client.command("File.ScoreInfo")
    deadline = time.monotonic() + DIALOG_TIMEOUT
    while not _is_open():
        if time.monotonic() > deadline:
            raise DoricoError("Dorico did not open its Project Info dialog")
        await asyncio.sleep(0.2)
    await asyncio.sleep(0.5)


async def _close() -> None:
    if _is_open():
        _osascript(_PRESS, "Close")
        await asyncio.sleep(0.5)


def _read_fields() -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in _osascript(_READ).splitlines():
        name, _, value = line.partition("\t")
        if name in FIELDS:
            fields[name] = value
    return fields


async def read_project_info(bridge: DoricoBridge) -> dict[str, str]:
    """The project-level Project Info fields, by their dialog names."""
    await _open(bridge)
    try:
        return _read_fields()
    finally:
        await _close()


async def set_project_info(bridge: DoricoBridge, fields: dict[str, str]) -> dict[str, Any]:
    """Set some fields ("" clears one), Apply, and read them back."""
    unknown = sorted(set(fields) - set(FIELDS))
    if unknown:
        raise DoricoError(f"unknown Project Info fields {unknown}; fields: {', '.join(FIELDS)}")
    if not fields:
        raise DoricoError("no fields to set")
    for name, value in fields.items():
        if not isinstance(value, str) or ("\n" in value and name not in ("Copyright", "Other information")):
            raise DoricoError(f"{name} must be a single-line string")
    await _open(bridge)
    try:
        before = _read_fields()
        for name, value in fields.items():
            _osascript(_TYPE, name, value)
        if _osascript(_PRESS, "Apply") != "clicked":
            raise DoricoError("could not press Apply in the Project Info dialog")
        await asyncio.sleep(0.5)
    finally:
        await _close()
    after = await read_project_info(bridge)
    wrong = {k: after.get(k) for k, v in fields.items() if after.get(k) != v}
    if wrong:
        raise DoricoError(f"Dorico did not keep {sorted(wrong)}; they now read {wrong}")
    return {"changed": {k: {"before": before.get(k), "after": after.get(k)} for k in fields}}
