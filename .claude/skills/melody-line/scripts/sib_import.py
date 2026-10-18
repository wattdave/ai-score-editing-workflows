"""Import a MusicXML file into the running Sibelius, click through any import dialog, save it as .sib
and reopen the .sib. Usage: sib_import.py IN.xml OUT.sib   (run with: uv run --with pyobjc-framework-Quartz --with pillow --with numpy)
Only clicks when Sibelius is the frontmost app, on a blue push button of dialog size."""
import subprocess, sys, time, tempfile
from pathlib import Path
import numpy as np
from PIL import Image
import Quartz as Q

xml, sib = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
CLI = ["uv", "run", "sibelius-cli"]
REPO = str(Path(__file__).resolve().parents[4])  # the repository root (this file lives in .claude/skills/melody-line/scripts)


def front():
    return subprocess.run(["osascript", "-e", 'tell application "System Events" to return name of first process whose frontmost is true'],
                          capture_output=True, text=True).stdout.strip()


def click(x, y):
    pt = (x, y)
    Q.CGEventPost(Q.kCGHIDEventTap, Q.CGEventCreateMouseEvent(None, Q.kCGEventMouseMoved, pt, 0)); time.sleep(0.3)
    for k in (Q.kCGEventLeftMouseDown, Q.kCGEventLeftMouseUp):
        Q.CGEventPost(Q.kCGHIDEventTap, Q.CGEventCreateMouseEvent(None, k, pt, Q.kCGMouseButtonLeft)); time.sleep(0.1)


def find_ok():
    """centre (screen points) of a blue ~55x20 px (at 1600 wide) button, or None"""
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "s.png"
        subprocess.run(["screencapture", "-x", str(p)], check=True)
        im = Image.open(p).convert("RGB")
    W = Q.CGDisplayBounds(Q.CGMainDisplayID()).size.width
    scale = W / im.width
    a = np.asarray(im).astype(int)
    mask = (abs(a[:, :, 0] - 10) < 40) & (abs(a[:, :, 1] - 120) < 40) & (a[:, :, 2] > 220)
    ys, xs = np.nonzero(mask)
    if len(xs) < 300:
        return None
    # largest connected-ish cluster: use bounding box of the densest 150x60 px window
    best = None
    for cx, cy in zip(xs[::50], ys[::50]):
        sel = (abs(xs - cx) < 90 * (im.width / 1600) * 2) & (abs(ys - cy) < 40 * (im.width / 1600) * 2)
        if best is None or sel.sum() > best[0]:
            best = (sel.sum(), xs[sel].mean(), ys[sel].mean())
    if best[0] < 300:
        return None
    return best[1] * scale, best[2] * scale


proc = subprocess.Popen(CLI + ["--timeout", "120", "plugin", "ScoreBridge", "OpenScore", "--args", f'["{xml}"]'],
                        cwd=REPO, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
clicks = 0
deadline = time.time() + 150
while proc.poll() is None and time.time() < deadline:
    time.sleep(3)
    if proc.poll() is not None:
        break
    pos = find_ok()
    if pos and clicks < 4:
        # Sibelius's dialogs take focus; refuse to click if another app is in front
        if front() != "Sibelius":
            print("front app is", front(), "- not clicking; bringing Sibelius forward", flush=True)
            subprocess.run(["osascript", "-e", 'tell application "Sibelius" to activate'])
            continue
        click(*pos)
        clicks += 1
        print("clicked OK at", pos, flush=True)
        time.sleep(3)
out = proc.communicate()[0]
print("open:", out.strip().replace("\n", " ")[:120])
for args in (["ExportScore", f'["{sib}", "SIBL"]'], ["OpenScore", f'["{sib}"]']):
    r = subprocess.run(CLI + ["plugin", "ScoreBridge", args[0], "--args", args[1]], cwd=REPO, capture_output=True, text=True)
    print(args[0], "->", (r.stdout + r.stderr).strip().replace("\n", " ")[-100:])
r = subprocess.run(CLI + ["--json", "score-snapshot"], cwd=REPO, capture_output=True, text=True)
print(r.stdout[:260])
if f'"fileName":"{sib}"' not in r.stdout:
    sys.exit(f"WRONG SCORE ACTIVE: expected {sib}; do not export from this window")
