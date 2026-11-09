---
name: sibelius-shared-gui
description: >
  Sibelius and macOS GUI automation when several agents (or an agent and the user) share one
  screen: take a blocking GUI lock, handle stale locks, answer Missing Fonts / Update Score / save
  dialogs, close windows from scripts, real Quartz clicks with a frontmost guard, black display,
  "display unavailable", the zsh word-splitting pitfall. Use before any scripted open, import,
  save, close, click or keystroke in Sibelius (or MuseScore, Halbestunde) when other agents may
  also be using the machine, in overnight batches, or when a bridge call says "plug-in not
  reachable" or "busy".
---

# Sharing one Sibelius GUI

Distilled from the Nelson Carol Book overnight run (six agents, one display). Sibelius has
one window stack and one bridge port, so every open, import, save, close, click and keystroke
belongs to whoever holds the lock. Reads through `sibelius-cli` act on the frontmost score, so
they also need the lock.

## 1. The lock

```bash
S=${CLAUDE_SKILL_DIR}/scripts/gui_lock.sh
export GUI_LOCK_DIR="/shared/project/locks/gui"      # one folder for all agents
$S acquire me "Fum Fum Fum import" 3600 || exit 1    # blocks; exit 0 only when we hold it
# ... GUI work for ONE score ...
$S release me
$S status                                            # owner, age in minutes
```

- `acquire` prints `GOT` and exits 0 only when it holds the lock. The one-liner
  `mkdir "$L" && echo GOT` is the trap: when it prints nothing the next command still ran and one
  agent opened a score under another's session. Always chain with `|| exit 1`.
- Foreground `sleep` is blocked in some harnesses: run `acquire` in the background and wait with
  Monitor, or use the timeout argument.
- Think, repair XML, render and compare images **outside** the lock. Hold it for one score,
  at most about 25 minutes, then close the window and release. A scan or long upload does not
  need it for the whole wait, only for its clicks.
- With many agents the lock was free only minutes per hour (waits of 4 h occurred). Give a
  long-running scanner a reserved turn instead of polling every 15 s, and put a whole task in
  one script so a turn is used fully.
- Match owners exactly: `grep -q w2-slice2 owner` also matches `w2-slice2b`. `gui_lock.sh release`
  compares the whole name. `python3` of the system has no Quartz: use
  `uv run --with pyobjc-framework-Quartz`.
- Never remove a lock you do not own (`release` refuses). Do not `rm -rf` the lock in a
  cleanup trap after you have already released it.
- **Stale lock:** if `status` shows an owner more than 45 minutes old, look at the screen. If
  its window is unchanged and no dialog waits, message the owner once, wait 10 minutes, then
  take over only by: dismissing any dialog, saving and closing its window with Save, removing the
  lock. Write the takeover down.

## 2. Frontmost guard and real clicks

- Check the frontmost process before every keystroke or click, and re-activate the app before each
  step (the user's Terminal steals focus when they type). Never type into Terminal.
- Mouse: only real Quartz events work for Halbestunde, MuseScore and some Sibelius dialogs;
  System Events `click at` does nothing there. Use a click helper that exits unless the target
  app is frontmost (the recipe is in `musescore-pdf-convert`, section 1).
- **Screen scale differs per display.** Read it first: `CGDisplayBounds(CGMainDisplayID())`.
  On a 1920x1080 display screenshot pixels equal points; on another one the divisor was 1.371.
  Do not hard-code it.
- A "Please select a note or chord" dialog (from stray Return presses) is not in Accessibility;
  only a real click on its OK works, and until then the bridge is blocked.
- `zsh` does not word-split a variable: `C="uv run sibelius-cli"; $C inspect` fails. Use a
  function, an array, or a script file.
- Multi-line scripts: quoted heredocs, never `-c`/`-e` strings (repo rule).

## 3. Dialogs: answer every one yourself

A dialog left open blocks every agent, and the bridge then reports "plug-in not reachable" or
"busy". After **each** open check the window list for a dialog and answer it:

| Dialog | Answer |
|---|---|
| Missing Fonts (old-format file, e.g. Opus Text) | Return with Sibelius frontmost. It counts as a change, so closing the score later raises the save sheet. |
| Update Score: FILE | click OK (the update is in memory only) |
| Open MusicXML File | Return (OK). A schema warning before it is harmless. |
| "X is already being edited. Open the previous version and lose your changes?" (opening a score that is already open; Yes is the default) | **No**, with a real click. Then close the stale window, then edit. Until answered, scripts time out with "not frontmost" / "bridge plug-in not reachable". Check the window list before opening a score. |
| Do you want to save the changes | after edits: Save/Yes. After a read-only open: No. |

`lyric-sheet/scripts/sib_windows.sh` has `update-ok`, `no-save`, `close FILE` and `list`
(Accessibility clicks only). Then verify with `sibelius-cli inspect`: `fileName` must be the
score you meant before you act on it. A batch loop must dismiss per score and must not release
the lock while a dialog is open.

## 4. Closing windows

- A window that is not frontmost ignores a click on its AXCloseButton: `AXRaise` it first, then
  **Cmd+W** with System Events (this also closed a saved score that the button click left open).
- The save sheet's buttons are nested: `click button "No" of window 1` fails. Walk
  `entire contents of window` and click the button named "No", or use `sib_windows.sh no-save`.
- Closing a score you only read still asks to save (even unedited). Answer No; never No on a
  score you edited.
- A close loop that does `activate` then Cmd+W skips the close when Terminal steals focus: four
  stale windows then made later opens abort. Close by name (AXRaise that window, then Cmd+W) and
  list the windows (`get name of every window`) after each score.
- Leave windows you did not open alone. After saving and verifying a score, close it.

## 5. Display problems

- Black screenshot (`screencapture -x` all black): `caffeinate -u -t 3`, wait 3 s, retry. A long
  `caffeinate` for the whole run prevents it.
- Computer-use screenshots can fail with "CU display unavailable" while the display is shared.
  The Bash route still works: `screencapture -x f.png` and Read it, Quartz clicks, `osascript`
  System Events for menus and keys. Without screenshots you cannot answer unexpected dialogs:
  check the window list through System Events after each step.

## 6. Import and save from scripts

- `sibelius-cli save --path COPY` is refused (it would switch the open score). To save a
  never-saved MusicXML import: `plugin ScoreBridge ExportScore --args '["/abs/x.sib","SIBL"]'`,
  then `OpenScore` the `.sib`, then edit and `auto-layout --expect-file`. Details:
  `sibelius/references/commands.md` and `import-and-layout-recipes.md`.
- `--backup-dir` is a global option: it goes before the subcommand.

## What is not here

A fair lock queue (first come, first served) is not implemented; the lock is first to poll wins.
