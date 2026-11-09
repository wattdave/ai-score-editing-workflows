---
name: omr-musescore-convert
description: >
  MuseScore 4.7.6+. Turn a sheet-music PDF into a score with MuseScore's online "Convert file to
  score" service (File > Convert file, same as Scores > Convert): upload from the GUI, wait for the
  cloud score, open it, export MusicXML through the bridge and check it against the PDF. Use when
  asked to convert a PDF with MuseScore, or for a scan or non-Sibelius PDF when Halbestunde is not
  wanted. Clean Sibelius-exported PDFs go to vector-pdf-score instead. Formerly musescore-pdf-convert.
---

# MuseScore PDF to score

(Formerly `musescore-pdf-convert`.) **Which OMR runtime?** Use this skill for MuseScore 4.7.6+
Convert (a cloud score that you open and export as MusicXML through the bridge). Use
`omr-halbestunde` instead for the Halbestunde Mac app, which uploads the PDF to an online service
and is driven through its GUI. Either output is a first draft: send it to `omr-score-repair` next.

**Clean PDF exported from Sibelius?** Use `vector-pdf-score` first: exact, local, nothing
uploaded. This service is the fallback for scans and other programs' PDFs (see also
`omr-halbestunde`).

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
   My online scores. **Do not click the card or Open score before the toast** (or the log line
   "status changed: Processing -> AwaitingReview" in
   `~/Library/Application Support/MuseScore/MuseScore4/logs/MuseScore_*.log`): a card that looks
   ready at +1 min is still Processing, and clicking it starts a second blank `mscore` process
   that never loads. Server errors (too complex, notes not recognised, rate limited) show there.

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

**Headless alternative (no bridge, no window juggling).** Open score downloads the cloud file to
`~/Library/Application Support/MuseScore/MuseScore4/cloud_scores/ID.mscz`. Export it directly
(under 10 s; the process then lingers, kill it):

```bash
"/Applications/MuseScore 4.app/Contents/MacOS/mscore" -o out.xml "$HOME/Library/Application Support/MuseScore/MuseScore4/cloud_scores/ID.mscz"
```

**Opening a cloud score later (after the toast is gone):** only the toast's **Open score** downloads
the `.mscz`. Clicking a card under Home > My online scores while a project is open just tries to
open `cloud_scores/ID.mscz` (not yet downloaded) and starts a second blank `mscore` process that
never loads: kill it. With **no score open** the same card click downloads and opens it. So:
quit and relaunch MuseScore (or close every score tab), Home > My online scores, click one
card, export headless, close the score tab (its X sits right of the title), next card. Toasts
time out and shift when others are dismissed: do not click them blind.

Otherwise use the bridge as follows.

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

Check first, against the print: a **time signature inserted mid-piece** (a bogus 6/8 at bar 37 in
every part of Carol of the Bells), a **lost 8vb** on the tenor staff, lyric junk ("1.=String,"),
garbled title and credits, S/A or T/B pairs merged into one part, bar offsets that shift
mid-piece, and single wrong pitches. Repair the XML with a script and verify every bar against
200-800 dpi crops. The server can also reject a file ("better quality file": Riu Riu Chiu,
O Holy Night): then use another route (`hand-transcribe-poor-scan`).

Driving the app: when screenshots fail ("CU display unavailable"), use `screencapture` + Quartz
clicks + System Events, re-activate MuseScore before every step, and see `sibelius-shared-gui`
for the shared-display rules. In "Your score is being processed" do **not** use "Convert more"
and do not leave a half-open dialog: a wrong file was uploaded that way (check the log's file
size = PDF size + ~440 bytes and the card's name). `zsh` does not word-split `C="uv run ..."`
(use a script).

Calibration on two one-page prints (Deck the Hall, We Wish You a Merry Christmas): MuseScore kept
the pickup bar, rests and part names and read the title block (with garbled subtitle/composer),
but misread about 25 lyric syllables on one page and 2 notes; verse numbers stay in the lyric text
and apostrophes are lost. About 2 min server time plus 6-8 min of GUI steps per piece. Halbestunde
is the default scanner; this is the second opinion.

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

## Ficta (editorial accidentals above the notes)

Renaissance and early-music editions print **ficta** as a small accidental *above* the staff, over
the note it changes and for that note only. It is not a printed-in-the-staff accidental, and it must
not be rendered as one. Sibelius and Dorico both ignore `<accidental-mark placement="above">` on
import and draw the accidental in the staff (checked on Brumel, *Du tout plongiet*, 2026-11-04;
MuseScore imported the pitches correctly but its engraving was not looked at). So after import:

- Keep the sounding pitch right (the `<alter>` carries it); do not add `<accidental>` for a ficta.
- Write `<notations><accidental-mark placement="above">flat|sharp|natural</accidental-mark></notations>`
  on the note so the information survives in the MusicXML (`lilypond-pdf-score` does).
- **Sibelius:** save the import as `.sib`, then for each ficta note run
  `sibelius-cli ficta --staff S --bar B --index I --accidental flat|natural|sharp` (and `--remove` to
  undo). It puts the sign above the note and hides the staff accidental, as Sibelius's own Add Ficta
  plug-in does. List the marks with `uv run python .claude/skills/lilypond-pdf-score/scripts/list_ficta.py file.musicxml` (staff, bar, position, pitch); give it `--query q.json --editor sibelius|musescore|dorico` (the editor's `query` output for the whole score) to get the ready-to-run `ficta` batch. It matches by staff, bar, position and pitch, so no hand-counted indices.
- **Dorico:** `dorico-cli apply` with `{"op":"ficta","id":N,"accidental":"flat"|"natural"|"sharp"}` (address the
  note by `id`). It hides the staff accidental and attaches a playing technique above the note; the project
  needs three custom techniques first (see the dorico skill, "Ficta").
- **MuseScore:** `musescore-cli apply` with `{"op":"ficta","staff":S,"bar":B,"index":I,"type":"NoteRest","position":P,"accidental":"flat"|"natural"|"sharp"}` (bridge v11). It hides the staff accidental and adds the sign as staff text above the note; `"remove":true` undoes it. The added text takes an index in the bar, so query again between batches.
