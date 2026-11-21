# MuseScore on Linux: plan for a trial

Status: **not started** (written 2026-11-20). Nothing here has been run on Linux.

MuseScore 4 is the one editor we drive that has a Linux build. Dorico and
Sibelius are macOS and Windows only (as far as we could find, 2026-11-20), so
MuseScore is the cheapest way to learn whether any of this repository can run
off the Mac. It is also the route to running on Windows through WSL2, where
WSLg shows a Linux MuseScore window on the Windows desktop. WSLg cannot host
Sibelius or Dorico, which are Windows programs.

Related: [musescore.md](musescore.md), [musescore-backend-plan.md](musescore-backend-plan.md).

## Goal

Decide, with evidence, whether `musescore-cli` and `musescore-mcp` work
against MuseScore Studio on Linux, and list exactly what is Mac-only. A
useful result can be "works with these three changes" or "does not work
because X". Writing the Linux port is not the goal of the trial.

## What should already work (from reading the code, unverified on Linux)

- The client is a WebSocket to `127.0.0.1` with a token
  (`musescore/client.py`), so the CLI and the plug-in only need to share a
  machine. Inside one Linux install or one WSL2 distro that holds.
- The ScoreBridge plug-in is QML against MuseScore's own plug-in API
  (`musescore/msbridge.qml.in`), so it is not tied to macOS.
- Config and token live under `$XDG_CONFIG_HOME` or `~/.config`
  (`src/ai_score_editing/paths.py`), which is the Linux convention.
- `install-plugin` writes the plug-in folder named by `MUSESCORE_PLUGIN_DIR`,
  default `~/Documents/MuseScore4/Plugins` (`musescore/install.py`).
- The bridge refuses MuseScore older than 4.6 and warns on versions newer than
  tested (`musescore/bridge.py`), so a too-old distro package is caught.

## What is Mac-only today

- `musescore/window.py` maps a window to its file with AppleScript and returns
  `[]` when `sys.platform != "darwin"`. It fails soft, so the effect is that
  "which file does this window show" does not work.
- Everything that clicks: starting the plug-in from Plugins > ScoreBridge,
  answering save prompts, closing windows, and the online PDF convert flow
  (`omr-musescore-convert`). These use System Events and Quartz clicks.
- Setup (`setup` skill, README) is Homebrew and Mac only.
- The skills' shell scripts are zsh and assume macOS tools.

## Unknowns to settle first

1. Where Linux MuseScore 4.7 looks for plug-ins. The Mac default will not be
   right. Check the Linux plug-in folder in the MuseScore handbook or Preferences, and
   whether the AppImage, Flatpak and Snap builds differ (a sandbox may hide
   `~/.config/ai-score-editing/` or block port 8766).
2. Whether the plug-in must still be enabled once in Plugins > Manage plugins
   and started from the Plugins menu each session, as on the Mac. That is a
   click the trial cannot skip.
3. Whether the Linux build has the same menus and cloud features. The PDF
   convert is a MuseScore.com cloud feature and may not exist or may need a
   login.
4. Whether MuseScore's command-line conversion mode (`mscore -o out.pdf in.mscz`)
   can replace GUI export steps. Unverified; it would avoid some clicking.

## Phases

Each phase ends with a pass or fail and a short note appended to this file.

### Phase 0: get a running MuseScore on Linux

- Pick the target: native Linux (a spare machine, VM or container with a
  display) or WSL2 with WSLg on Windows 11. Run `wsl --update` first for WSLg.
- Install MuseScore Studio 4.6 or newer, preferably the AppImage so the build
  matches upstream. Record the exact version (`mscore --version`).
- Pass: the window opens and a score loads. Note any missing fonts, audio or
  GPU errors; none of them should matter for the bridge.

### Phase 1: install the bridge and connect

- Install this repo: `uv sync`, Python 3.13.
- `MUSESCORE_PLUGIN_DIR=<linux plug-in folder> uv run musescore-cli install-plugin`
- Restart MuseScore, enable ScoreBridge once, start it from the Plugins menu
  in a scratch score's window.
- `uv run musescore-cli overview`
- Pass: overview returns the score and the bridge version. Fail modes to
  record: plug-in not listed, port refused, token file unreadable (sandbox).

### Phase 2: the existing live check

- Open a score whose name contains "Scratch" with at least 8 bars and 2 staves.
- `uv run python scripts/dev/musescore_live_check.py`
- Pass: every step PASS. It covers reads, a dry run, a real batch with one
  undo step, lyrics, every export format, metadata, adding an instrument, and
  staff playback, and leaves the score as it found it. Record each FAIL with
  the step name; differences from macOS are the main finding of the trial.

### Phase 3: tests and CI

- Run `uv run pytest` on the Linux target. Most tests are offline and CI
  already runs them on Ubuntu, so new failures here would point at paths or
  locale, not the editor.
- If phase 2 passes, decide whether a CI job can run the live check headless
  (`xvfb-run`) against an installed AppImage. Likely too heavy; the decision
  and reason go in this file.

### Phase 4: the Mac-only gaps

Only if phases 1 and 2 pass.

- `window.py`: a Linux implementation (for example `xdotool` or
  `wmctrl` window titles on X11; WSLg also exposes X11/Wayland windows) or a
  documented "not available" with the CLI taking the file path explicitly.
- GUI steps: list each click the skills need and whether the CLI route can
  avoid it (command-line export, passing the file path). Anything left needs a
  Linux equivalent of the macOS automation, or stays manual.
- Setup: a Linux section in `setup` and the README (package manager,
  AppImage, plug-in folder, `libxml2-utils`).

### Phase 5: WSL2 specifics

Only if the target is Windows.

- Run everything inside one WSL2 distro, so `127.0.0.1` is shared and no
  cross-boundary networking is involved.
- Check that clicks into a WSLg window work from the tools we would use, and
  that the WSLg window shows in screenshots.
- Do not mix with a Windows MuseScore: a Windows-side MuseScore reached from
  WSL2 needs mirrored networking or the host IP, and the plug-in folder is a
  Windows path. That is a separate experiment.

## Success criteria

- **Full pass:** phases 1 and 2 pass; the only changes needed are documented
  paths and setup.
- **Partial:** the bridge works but some live-check steps fail or need GUI
  clicks. List the steps; decide per step whether to fix or document.
- **Fail:** the bridge cannot connect or the plug-in cannot load. Record the
  cause (sandbox, plug-in API difference, missing feature) and stop.

## Out of scope

- Sibelius and Dorico on Linux (not available).
- Sibelius on Windows, which needs Windows GUI automation in place of the
  AppleScript and Quartz code. That is a bigger piece of work than this trial.
- Replacing the zsh skills with portable scripts, until the trial shows it is
  worth doing.

## Log

(Append dated results per phase here.)
