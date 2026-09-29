"""Export MusicXML from Dorico by scripting its export window.

Dorico's command File.Export?FilterID=MusicXMLExportFilter takes no path: it
opens Dorico's own "Export MusicXML" window, which shows the last "Export
to:" folder. Clicking OK writes "<folder>/Flows from <title>/<title> - Full
score - <n> <flow>.musicxml" (and one file per part if that is ticked).
There is no scripting route around the window, so this drives it through
System Events, which needs Accessibility permission for the terminal.

The window exports to the folder it last used for that project, which may be
the user's score folder, where existing files raise one "Do you want to
overwrite the file ...?" dialog each. So the export always goes to a private
folder (EXPORT_DIR): if the window shows another, its folder button opens a
macOS Open panel, and Go to Folder (shift-command-G) takes the path. Dorico
remembers that folder for the project, and a Cancel keeps the old one, so
it cannot be set back without exporting there (checked 2026-09-28). The
private folder is emptied before each export, so no overwrite prompts come;
any that do are answered only for .musicxml files inside it, and anything
unexpected is cancelled rather than guessed at.
"""

from __future__ import annotations

import asyncio
import re
import shutil
import subprocess
import time
from pathlib import Path

from .bridge import default_workdir
from .client import DoricoClient, DoricoError

PROCESS = "Dorico 6"
WINDOW = "Export MusicXML"
DIALOG_TIMEOUT = 15.0
EXPORT_TIMEOUT = 120.0
#: Polls (0.8 s apart) without an overwrite prompt before the export counts as done.
QUIET_POLLS = 4
#: Where the back end's MusicXML exports go; nothing else is kept there.
EXPORT_DIR = default_workdir() / "musicxml"
#: Reads of the export window before its folder counts as unreadable (it
#: was once read before Dorico had filled it in).
WINDOW_READS = 6

# Returns lines "role\tname\tvalue" for every element of the export window.
_READ_WINDOW = """
on run argv
  set windowName to item 1 of argv
  tell application "System Events"
    tell process "%(process)s"
      if not (exists window windowName) then return "MISSING"
      set out to ""
      set items_ to entire contents of window windowName
      repeat with i from 1 to count of items_
        set e to item i of items_
        set r to get role of e
        set nm to ""
        try
          set nm to (get name of e) as text
        end try
        set v to ""
        try
          set v to (get value of e) as text
        end try
        set out to out & r & tab & nm & tab & v & linefeed
      end repeat
      return out
    end tell
  end tell
end run
"""

_CLICK = """
on run argv
  set windowName to item 1 of argv
  set buttonName to item 2 of argv
  tell application "System Events"
    tell process "%(process)s"
      set items_ to entire contents of window windowName
      repeat with i from 1 to count of items_
        set e to item i of items_
        if (get role of e) is "AXButton" then
          try
            if ((get name of e) as text) is buttonName then
              click e
              return "clicked"
            end if
          end try
        end if
      end repeat
      return "missing"
    end tell
  end tell
end run
"""

# Each open AXDialog as "index\ttext" lines, texts joined, for prompt handling.
_DIALOGS = """
tell application "System Events"
  tell process "%(process)s"
    set out to ""
    repeat with i from 1 to count of windows
      set w to window i
      if (get subrole of w) is "AXDialog" then
        set texts to ""
        set items_ to entire contents of w
        repeat with j from 1 to count of items_
          set e to item j of items_
          if (get role of e) is "AXStaticText" then
            try
              set texts to texts & ((get value of e) as text) & " "
            end try
          end if
        end repeat
        set out to out & i & tab & texts & linefeed
      end if
    end repeat
    return out
  end tell
end tell
"""

_CLICK_IN_DIALOG = """
on run argv
  set windowIndex to (item 1 of argv) as integer
  set buttonName to item 2 of argv
  tell application "System Events"
    tell process "%(process)s"
      set items_ to entire contents of window windowIndex
      repeat with j from 1 to count of items_
        set e to item j of items_
        if (get role of e) is "AXButton" then
          try
            if ((get name of e) as text) is buttonName then
              click e
              return "clicked"
            end if
          end try
        end if
      end repeat
      return "missing"
    end tell
  end tell
end run
"""


# Presses the folder button after the "Export to:" path, then types the
# target into the Open panel's Go to Folder field and chooses it.
_CHOOSE_FOLDER = """
on run argv
  set target to item 1 of argv
  tell application "System Events"
    tell process "%(process)s"
      set frontmost to true
      set w to window "Export MusicXML"
      set items_ to entire contents of w
      set found to false
      set pressed to false
      repeat with i from 1 to count of items_
        set e to item i of items_
        if found is false and (get role of e) is "AXStaticText" then
          try
            if ((get value of e) as text) starts with "/" then set found to true
          end try
        else if found is true and (get role of e) is "AXButton" then
          click e
          set pressed to true
          exit repeat
        end if
      end repeat
      if not pressed then return "no folder button"
      repeat 20 times
        if exists window "Open" then exit repeat
        delay 0.25
      end repeat
      if not (exists window "Open") then return "no Open panel"
      perform action "AXRaise" of window "Open"
      delay 0.3
      keystroke "g" using {command down, shift down}
      delay 0.8
      keystroke target
      delay 0.5
      key code 36
      delay 1.0
      key code 36
      delay 1.0
      if exists window "Open" then
        key code 53
        return "Open panel still open"
      end if
      return "chosen"
    end tell
  end tell
end run
"""


def _osascript(script: str, *args: str) -> str:
    result = subprocess.run(
        ["osascript", "-", *args], input=script % {"process": PROCESS},
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        message = result.stderr.strip()
        if "assistive access" in message or "not allowed" in message:
            raise DoricoError(
                "macOS denied UI scripting; give the terminal Accessibility permission "
                "(System Settings > Privacy & Security > Accessibility)"
            )
        raise DoricoError(f"UI scripting failed: {message}")
    return result.stdout.strip()


def read_export_window() -> dict[str, object]:
    """The export window's folder and check boxes, or {} if it is not open."""
    text = _osascript(_READ_WINDOW, WINDOW)
    if text == "MISSING":
        return {}
    rows = [line.split("\t") + ["", ""] for line in text.splitlines()]
    boxes = {r[1]: r[2] == "1" for r in rows if r[0] == "AXCheckBox"}
    texts = [r[1] for r in rows if r[0] == "AXStaticText"]
    folder = None
    if "Export to:" in texts:
        after = texts[texts.index("Export to:") + 1:]
        folder = next((t for t in after if t.startswith("/")), None)
    return {"folder": folder, "boxes": boxes}


def _handle_prompts(folder: Path) -> list[str]:
    """Answer overwrite prompts for .musicxml files under folder; refuse others."""
    answered = []
    for line in _osascript(_DIALOGS).splitlines():
        index, _, text = line.partition("\t")
        if "overwrite the file" not in text:
            continue
        target = text.split("'")[1] if text.count("'") >= 2 else ""
        if target.endswith(".musicxml") and Path(target).resolve().is_relative_to(folder.resolve()):
            _osascript(_CLICK_IN_DIALOG, index, "Overwrite")
            answered.append(target)
        else:
            _osascript(_CLICK_IN_DIALOG, index, "Cancel")
            raise DoricoError(f"Dorico asked to overwrite {target or text.strip()!r}; cancelled")
    return answered


async def _read_filled_window() -> dict[str, object]:
    """The export window once Dorico has filled in its folder ({} if closed)."""
    window = read_export_window()
    for _ in range(WINDOW_READS):
        if not window or window.get("folder"):
            break
        await asyncio.sleep(0.3)
        window = read_export_window()
    return window


def _clear_export_dir() -> Path:
    """Empty the private export folder (only ever the back end's exports)."""
    root = EXPORT_DIR.resolve()
    if not root.is_relative_to(default_workdir().resolve()):
        raise DoricoError(f"refusing to clear {root}: not under the back end's work folder")
    root.mkdir(parents=True, exist_ok=True)
    for item in root.iterdir():
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()
    return root


async def export_musicxml(client: DoricoClient, flow: int = 1) -> Path:
    """Export the full score of the active project as MusicXML; return the file."""
    if read_export_window():
        raise DoricoError("Dorico's Export MusicXML window is already open; close it first")
    root = _clear_export_dir()
    await client.command("File.Export?FilterID=MusicXMLExportFilter")
    deadline = time.monotonic() + DIALOG_TIMEOUT
    window = read_export_window()
    while not window:
        if time.monotonic() > deadline:
            raise DoricoError("Dorico did not open its Export MusicXML window")
        await asyncio.sleep(0.3)
        window = read_export_window()
    window = await _read_filled_window()
    if window.get("folder") and Path(str(window["folder"])).resolve() != root:
        outcome = _osascript(_CHOOSE_FOLDER, str(root))
        window = await _read_filled_window()
        if outcome != "chosen" or not window.get("folder") or Path(str(window["folder"])).resolve() != root:
            if window:
                _osascript(_CLICK, WINDOW, "Cancel")
            raise DoricoError(
                f"could not point Dorico's Export MusicXML window at {root} ({outcome}); export cancelled"
            )
    boxes = window["boxes"]
    folder = window["folder"]
    problem = None
    if not folder:
        problem = "could not read the Export to: folder"
    elif not boxes.get("Export uncompressed XML (.musicxml)"):  # type: ignore[union-attr]
        problem = "tick 'Export uncompressed XML (.musicxml)' in Dorico's Export MusicXML window"
    elif not boxes.get("Full score", True):  # type: ignore[union-attr]
        problem = "tick the Full score layout in Dorico's Export MusicXML window"
    if problem:
        _osascript(_CLICK, WINDOW, "Cancel")
        raise DoricoError(f"{problem}; export cancelled")
    started = time.time()
    if _osascript(_CLICK, WINDOW, "OK") != "clicked":
        raise DoricoError("could not press OK in Dorico's Export MusicXML window")
    deadline = time.monotonic() + EXPORT_TIMEOUT
    while True:
        _handle_prompts(root)
        found = sorted(
            (p for p in root.rglob("*Full score*.musicxml") if p.stat().st_mtime >= started - 1),
            key=lambda p: p.stat().st_mtime,
        )
        flows = [p for p in found if f" - {flow:02d} " in p.name] or found
        if flows and not read_export_window():
            # Part files follow the full score, each possibly with its own
            # overwrite prompt; a prompt left open blocks every later
            # command, so wait until prompts stop coming.
            quiet = 0
            while quiet < QUIET_POLLS:
                await asyncio.sleep(0.8)
                quiet = 0 if _handle_prompts(root) else quiet + 1
                if time.monotonic() > deadline:
                    raise DoricoError("Dorico kept asking to overwrite exported files")
            return flows[-1]
        if time.monotonic() > deadline:
            raise DoricoError(f"no new full-score MusicXML appeared under {root}")
        await asyncio.sleep(0.5)


APPLICATION_LOG = Path.home() / "Library/Application Support/Steinberg/Dorico 6/application.log"
_EXPORTING_PDF = re.compile(r"Exporting PDF to (.+\.pdf)\s*$", re.MULTILINE)


def _answer_pdf_prompts() -> bool:
    """Choose Overwrite in Dorico's "output files already exist" prompt."""
    answered = False
    for line in _osascript(_DIALOGS).splitlines():
        index, _, text = line.partition("\t")
        if "output files already exist" in text:
            _osascript(_CLICK_IN_DIALOG, index, "Overwrite")
            answered = True
    return answered


async def export_pdf(client: DoricoClient, log: Path = APPLICATION_LOG) -> Path:
    """Export the current layout as a PDF with Print mode's settings.

    Print.ExportCurrentLayoutAsPDF writes "<project folder>/<nn> - <layout> -
    <title>.pdf" with no dialog, unless the file exists; then Dorico asks
    Overwrite / Create New, and Overwrite is chosen. The path is only in
    Dorico's log ("Exporting PDF to ..."), so it is read from there.
    """
    offset = log.stat().st_size if log.exists() else 0
    await client.command("Print.ExportCurrentLayoutAsPDF")
    deadline = time.monotonic() + EXPORT_TIMEOUT
    while True:
        _answer_pdf_prompts()
        with log.open("rb") as handle:
            handle.seek(offset)
            recent = handle.read().decode("utf-8", "replace")
        found = _EXPORTING_PDF.findall(recent)
        if found and "notifyPostCommandExecute: Print.ExportCurrentLayoutAsPDF" in recent:
            path = Path(found[-1])
            if path.exists():
                return path
        if time.monotonic() > deadline:
            raise DoricoError("Dorico did not report exporting a PDF")
        await asyncio.sleep(0.3)


def bring_to_front() -> None:
    """Make Dorico the frontmost app; its lyric popover needs it."""
    _osascript('tell application "System Events" to tell process "%(process)s" to set frontmost to true')
