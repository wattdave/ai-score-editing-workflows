#!/usr/bin/env python3
"""Drive the Halbestunde Mac app: upload one PDF, convert it, save the MusicXML.

Halbestunde exposes no controls to AppleScript, so this posts real mouse
clicks at positions relative to the window and checks that the app is in
front before every click or keystroke. Do not use the keyboard or mouse
while it runs.

Run with:
  uv run --with pyobjc-framework-Quartz --with pillow --with numpy python -I \
    halbestunde_convert.py "/path/01 Silent Night.pdf"

The XML is saved next to the PDF with the same name and an .xml extension.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import Quartz as Q
from PIL import Image

WINDOW_SIZE = (1020, 720)

# Positions relative to the window's top-left corner.
PLUS = (36, 575)
DROP_AREA = (546, 326)
CONVERT = (546, 518)
GREAT = (546, 440)
GREAT_PROBE = (480, 430)  # button padding; the centre of the button is dark text
DOWNLOAD_NOW = (913, 76)
MIDI_BOX = (547, 300)
XML_BOX = (360, 332)
NAME_FIELD = (535, 404)
SAVE = (386, 509)
MODAL_X = {"confirm": (707, 242), "form": (707, 211)}  # close buttons of the two Save As states


def osa(script: str) -> str:
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if result.returncode:
        raise SystemExit(f"osascript failed: {result.stderr.strip()}")
    return result.stdout.strip()


def frontmost() -> str:
    return osa('tell application "System Events" to return name of first process whose frontmost is true')


def window_origin() -> tuple[int, int]:
    raw = osa('tell application "System Events" to tell process "Halbestunde" '
              'to return (position of window 1) & (size of window 1)')
    x, y, w, h = (int(float(v)) for v in raw.split(","))
    if (w, h) != WINDOW_SIZE:
        raise SystemExit(f"Window is {w}x{h}, expected {WINDOW_SIZE}; resize it or update the offsets.")
    return x, y


def focus() -> tuple[int, int]:
    osa('tell application "Halbestunde" to activate')
    for _ in range(10):
        if frontmost() == "Halbestunde":
            return window_origin()
        time.sleep(0.3)
    raise SystemExit("Halbestunde did not come to the front; keystrokes would go to another app.")


def click(rel: tuple[int, int]) -> None:
    ox, oy = focus()
    pt = (ox + rel[0], oy + rel[1])
    Q.CGEventPost(Q.kCGHIDEventTap, Q.CGEventCreateMouseEvent(None, Q.kCGEventMouseMoved, pt, 0))
    time.sleep(0.2)
    for kind in (Q.kCGEventLeftMouseDown, Q.kCGEventLeftMouseUp):
        Q.CGEventPost(Q.kCGHIDEventTap, Q.CGEventCreateMouseEvent(None, kind, pt, Q.kCGMouseButtonLeft))
        time.sleep(0.1)
    time.sleep(1.5)


def keys(script: str) -> None:
    focus()
    osa(f'tell application "System Events"\n{script}\nend tell')
    time.sleep(1)


def shot() -> Image.Image:
    ox, oy = window_origin()
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "w.png"
        subprocess.run(["screencapture", "-x", "-R", f"{ox},{oy},{WINDOW_SIZE[0]},{WINDOW_SIZE[1]}", str(path)], check=True)
        return Image.open(path).convert("RGB")


def pixel(img: Image.Image, rel: tuple[int, int]) -> tuple[int, int, int]:
    scale = img.width / WINDOW_SIZE[0]
    return img.getpixel((int(rel[0] * scale), int(rel[1] * scale)))


def is_blue(rgb: tuple[int, int, int]) -> bool:
    return rgb[2] - rgb[0] > 80  # checked boxes are blue, unchecked are grey


def is_teal_button(rgb: tuple[int, int, int]) -> bool:
    return rgb[1] > 150 and rgb[2] > 120 and rgb[0] < 120


def wait_for(what: str, test, timeout: float) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if test(shot()):
            return
        time.sleep(3)
    raise SystemExit(f"Timed out after {timeout:.0f}s waiting for {what}.")


def is_modal_grey(rgb: tuple[int, int, int]) -> bool:
    return rgb == (38, 38, 38)  # the app background is (23, 26, 26)


def dismiss_modal() -> None:
    """Close a leftover Save As dialog; Escape does not close it."""
    img = shot()
    if not is_modal_grey(pixel(img, (400, 300))):
        return
    # the form is taller than the confirmation, so its top edge is at y=190
    click(MODAL_X["form" if is_modal_grey(pixel(img, (500, 190))) else "confirm"])


def box_checked(img: Image.Image, rel: tuple[int, int]) -> bool:
    # probe the corner of the box: its centre is the white tick when checked
    return is_blue(pixel(img, (rel[0] - 5, rel[1] - 5)))


def set_box(rel: tuple[int, int], want: bool, name: str) -> None:
    """The dialog remembers the last choice, so read the state before clicking."""
    if box_checked(shot(), rel) != want:
        click(rel)
    if box_checked(shot(), rel) != want:
        raise SystemExit(f"Could not {'check' if want else 'uncheck'} {name}.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--resume", action="store_true",
                    help="skip the upload and carry on from the current screen "
                         "(scan finished, or the Save As form already open)")
    ap.add_argument("--timeout", type=float, default=600, help="seconds to wait for the scan")
    args = ap.parse_args()
    pdf = args.pdf.expanduser().resolve()
    if not pdf.is_file():
        raise SystemExit(f"No such file: {pdf}")
    target = pdf.with_suffix(".xml")
    if target.exists():
        raise SystemExit(f"{target} already exists; move it aside first.")

    if not subprocess.run(["pgrep", "-x", "Halbestunde"], capture_output=True).stdout:
        subprocess.run(["open", "-a", "Halbestunde"], check=True)
        time.sleep(4)

    focus()
    if not args.resume:
        dismiss_modal()
        click(PLUS)
        click(DROP_AREA)
        keys('keystroke "g" using {command down, shift down}')
        keys(f'keystroke "{pdf}"')
        keys("key code 36")  # Return: go to the file
        keys("key code 36")  # Return: Open
        click(CONVERT)
        print("Uploaded; waiting for the scan...", file=sys.stderr)
    img = shot()
    form_open = is_modal_grey(pixel(img, (500, 190)))  # --resume may start inside the Save As form
    if not form_open:
        wait_for('"Great, let\'s go"', lambda im: is_teal_button(pixel(im, GREAT_PROBE)), args.timeout)
        click(GREAT)
        time.sleep(8)  # the converted preview loads
        click(DOWNLOAD_NOW)
    wait_for("the Save As form", lambda im: is_modal_grey(pixel(im, (500, 190))), 20)
    time.sleep(1)  # let the dialog finish appearing before reading the boxes

    # the file types behave like radio buttons: ticking XML unticks the others,
    # and clicking a ticked box does nothing
    set_box(XML_BOX, True, "XML")
    if box_checked(shot(), MIDI_BOX):
        raise SystemExit("MIDI is still ticked after ticking XML.")
    click(NAME_FIELD)
    keys('keystroke "a" using {command down}')
    keys(f'keystroke "{pdf.stem}"')
    click(SAVE)

    for _ in range(20):
        if target.exists():
            size = target.stat().st_size
            time.sleep(1)
            if size and size == target.stat().st_size:
                print(target)
                return 0
        time.sleep(1)
    raise SystemExit(f"{target} did not appear. The save folder in the dialog may differ; check 'Save to'.")


if __name__ == "__main__":
    raise SystemExit(main())
