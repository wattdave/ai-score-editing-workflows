---
name: musescore-pdf-convert
description: >
  MuseScore 4.7.6+. Turn a sheet-music PDF into a score with MuseScore's online "Convert file to
  score" service (File > Convert file, same as Scores > Convert): upload from the GUI, wait for the
  cloud score, open it, export MusicXML through the bridge and check it against the PDF. Use when
  asked to convert a PDF with MuseScore, or for a scan or non-Sibelius PDF when Halbestunde is not
  wanted. Clean Sibelius-exported PDFs go to vector-pdf-score instead.
---

# MuseScore PDF to score

**Clean PDF exported from Sibelius?** Use `vector-pdf-score` first: exact, local, nothing
uploaded. This service is the fallback for scans and other programs' PDFs (see also
`halbestunde-omr`).

MuseScore 4.7.6 added an online converter. The app uploads the PDF (or images, or audio in a
beta) to musescore.com, which recognises it and puts a cloud score in the user's account. It is
GUI-only: the plug-in API and `musescore-cli` have no hook for it. Source:
`src/project/qml/MuseScore/Project/ConvertFileToScoreDialog.qml`, server
`desktop.musescore.com/editor/v1/score/convert/*`. The result is a MuseScore score, not `.musx`
or MusicXML, so export it afterwards.

**Uploading sends the PDF to an external service and leaves a score in the user's musescore.com
account.** Only do it for files the user has named. The user must already be signed in (the
dialog shows their avatar); you cannot sign in for them. File size, page and file-count limits
come from the server (the dialog's "File requirements" link shows them).

## 1. Upload

Drive MuseScore with real mouse events (QML buttons ignore AX clicks); menus work through System
Events. Before every click or keystroke, check `mscore` is frontmost (see `gui-automation-safety`
in memory: keystrokes have landed in the user's terminal before).

1. `tell application "MuseScore 4" to activate`, then check the frontmost process is `mscore`.
2. File > **Convert file…** (System Events menu click). The "Convert file to score" dialog opens.
3. Click **Select** (real click). In the macOS file dialog press Cmd+Shift+G, type the full PDF
   path, Return; the file is highlighted, then click **Open**. Screenshot to confirm the right file.
4. The dialog shows the file and a **Save as** name (default: the PDF's name; this is the cloud
   score's name). Click **Convert**. A "Your score is being processed" dialog appears: **OK**.
5. Wait. A 4-page, 62 KB choir score took about 2.5 minutes. Poll with screenshots every 20 s; the
   toast "Your score is ready!" has **Open score**. Progress also shows under Home > Scores >
   My online scores. Server errors (too complex, notes not recognised, rate limited) show there.

A click helper (needs `uv`; screen points equal screenshot pixels on the 1920x1080 display):

```python
# click.py x y  — Quartz click, refuses unless mscore is frontmost
import sys, time, subprocess, Quartz
front = subprocess.run(["osascript", "-e", 'tell application "System Events" to name of first process whose frontmost is true'], capture_output=True, text=True).stdout.strip()
if front != "mscore": sys.exit(f"frontmost is {front}, not mscore")
for t in (Quartz.kCGEventLeftMouseDown, Quartz.kCGEventLeftMouseUp):
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, Quartz.CGEventCreateMouseEvent(None, t, (float(sys.argv[1]), float(sys.argv[2])), Quartz.kCGMouseButtonLeft))
    time.sleep(0.08)
```

Run it as `uv run --no-project --with pyobjc-framework-Quartz python click.py X Y` from the
scratchpad, and read coordinates off a fresh screenshot each time.

## 2. Export to MusicXML

**Open score** opens the cloud score in a new window. Export through the bridge, not the File >
Export dialog: that dialog and the bridge both attach to the *first* score window, so with
another score open they export the wrong one (a file with the wrong piece was exported this way).

1. Close any other score windows (the bridge holds one WebSocket port, 8766, and the older window wins).
2. With the converted score's window frontmost: Plugins > **ScoreBridge**.
3. `uv run musescore-cli overview` and check the name, bar count and staves are the converted
   score's, then:

```bash
uv run musescore-cli export --format musicxml --path "<folder>/<name>.musicxml"
```

## 3. Check the result

```bash
uv run python -I ${CLAUDE_SKILL_DIR}/scripts/compare_musicxml.py original.musicxml converted.musicxml
```

With no original, compare the opened score against the PDF page by page. Joy to the World in C
(4-page Sibelius PDF, SATB, 60 bars) came back with every pitch and duration right in all four
parts (the comparison does not cover dynamics, ties or slurs). Lyrics were the weak spot: full
stops became commas, and the tenor line lost two words ("Lord", "truth"). So always diff the
lyrics, expect dropped words and punctuation slips, and fix them in the target editor
(`musescore`, `lyric-hyphenation`, `omr-score-repair`). Parts come back named by voice (Soprano,
Alto...), unlike Halbestunde's `Voice0`.

The cloud score stays in the user's musescore.com account; mention it. There is a quality-review
rating step for converted scores (good/bad plus a comment); leave it to the user.
