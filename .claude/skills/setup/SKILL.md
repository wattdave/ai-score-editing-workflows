---
name: setup
description: >
  Guide a new user through installing everything this repository needs on a
  Mac: Homebrew, git, uv, Python 3.13, ffmpeg, the project's Python
  packages, and the score editors it drives (Sibelius Ultimate 2026.6+ with
  Sibelius Connect, Dorico, MuseScore 4) with their ScoreBridge plug-ins. Use on /setup or $setup, when the user asks to set up,
  install or get started, when a command fails because a tool is missing, or when a user
  seems new to the project.
---

# Setup

Many users of this repository have never used an AI assistant or a
terminal before. Write in plain language, one short step at a time, explain
jargon the first time it appears, and never assume they know what a
command does. Tell them what you are about to do before you do it.

## 1. Check what is already there

```bash
${CLAUDE_SKILL_DIR}/scripts/setup_check.sh
```

It changes nothing. Each line is `ok`, `missing`, `warn` or `optional` plus
a detail. Only offer to install what is `missing`. Mention `optional` items
only if the user wants that workflow (LilyPond sources). If everything is
`ok`, go straight to step 4.

If `macos` is missing, stop: this project only runs on a Mac.

## 2. Explain and ask

Show the user a short table of the missing items, what each is for, and
roughly how long it takes:

| Item | What it is for |
| --- | --- |
| Homebrew | The standard Mac installer for developer tools; installs the rest. Also installs Apple's Command Line Tools (a few minutes, one-time). |
| git | Downloads updates to this project. |
| uv | Runs this project's Python code and installs its packages. |
| Python 3.13 | The language the tool is written in; uv installs a private copy. |
| ffmpeg | Builds the MP3 rehearsal mixes. |
| Project packages | This project's own Python libraries (`uv sync`). |
| Bridge plug-in | A small Sibelius plug-in that lets the tool read the score. |
| poppler (optional) | `pdfinfo` and `pdftoppm`: page counts and page images for PDF scores in the OMR and melody-search workflows. |
| LilyPond (optional) | Converts LilyPond score sources from CPDL/IMSLP; only needed for that workflow. |

Then ask whether to install **everything missing at once** (recommended)
or **one at a time**, confirming each. Use a multiple-choice question tool
if your assistant has one (AskUserQuestion in Claude Code); otherwise ask in
chat and wait for the answer. Respect the
answer; if they choose one at a time, ask before each item and let them
skip any.

## 3. Install, in this order

Run each step, then re-run `${CLAUDE_SKILL_DIR}/scripts/setup_check.sh` to confirm it took
before moving on. If a step fails, show the error in plain words and do not
continue past something the later steps depend on.

1. **Homebrew.** Its installer asks for the Mac login password, which you
   cannot type for them, and must not be run from your own shell tool. Ask the user to open the **Terminal** app
   (Cmd+Space, type Terminal, Return), paste this, press Return, enter
   their Mac password when asked (nothing appears as they type; that is
   normal), and press Return again when prompted:

   ```bash
   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
   ```

   Wait for them to say it finished. Then add Homebrew to their shell so
   new Terminal windows find it (only if `homebrew-path` is `warn`):

   ```bash
   brew_bin=$(ls /opt/homebrew/bin/brew /usr/local/bin/brew 2>/dev/null | head -1)
   echo "eval \"\$($brew_bin shellenv)\"" >> ~/.zprofile
   ```

   Your own shell may not see `brew` until that line runs; prefix later
   commands with `eval "$($brew_bin shellenv)" &&` if `brew` is not found.
2. **git, uv, ffmpeg:** `brew install git uv ffmpeg` (only the missing ones).
   ffmpeg takes a few minutes.
   If the user will work from PDF scores (OMR, melody search), also
   `brew install poppler` for `pdfinfo` and `pdftoppm`.
   If the user will convert LilyPond sources, also `brew install lilypond`;
   python-ly needs no install (it runs through `uvx`).
3. **Python 3.13:** `uv python install 3.13`.
4. **Project packages:** `uv sync` in this folder.

## 4. Sibelius

These steps happen in Sibelius, so the user does them; guide and wait.

1. **Sibelius Ultimate 2026.6 or later** must be installed from Avid. If
   `sibelius` is missing or too old, tell them; the free Sibelius First and
   the mid-tier Sibelius (Artist) do not include Sibelius Connect, which
   this project needs. Do not try to download it for them.
2. If `sibelius-launched` is missing, ask them to open Sibelius once, then
   quit it.
3. **Bridge plug-in:** `uv run --project "${CLAUDE_SKILL_DIR}" sibelius-cli install-plugin`. This also
   removes the old `sibwscli.plg` bridge if the user has it; for MuseScore,
   `musescore-cli install-plugin` removes the old `sibwscli-bridge` folder.
   After upgrading, the user approves the new plug-in once.
4. **Enable Sibelius Connect:** open Sibelius → Sibelius menu →
   Preferences → Input Devices, turn on Sibelius Connect, keep the port at
   1898, and restart Sibelius so the plug-in loads.
5. **First connection:** with Sibelius open, run
   `${CLAUDE_SKILL_DIR}/scripts/setup_check.sh --connect`. Warn them first that Sibelius will
   show a dialog asking to allow "sibelius-cli" and that they
   must click OK. `connection` should report a bridge version. If it says
   Sibelius is busy, a dialog is open in Sibelius and they must close it.

## 4b. MuseScore (optional)

Only if the user wants to work in MuseScore 4.6 or newer (free from
musescore.org). Claude Code starts the MuseScore MCP server from
`.mcp.json`; the plug-in it talks to is installed with:

```bash
uv run --project "${CLAUDE_SKILL_DIR}" musescore-cli install-plugin
```

Then the user:

1. Quits and reopens MuseScore (a new or changed plug-in only loads at
   startup) and opens a score.
2. Goes to Plugins → Manage plugins, enables "ScoreBridge" and clicks
   OK (once only).
3. Chooses Plugins → ScoreBridge in the score's window in every
   MuseScore session before asking Claude to work on the score. Enabling it
   does not start it.

Check with `uv run --project "${CLAUDE_SKILL_DIR}" musescore-cli overview`: it should name the score. The
bridge only answers requests with the token that `install-plugin` stored,
so it is safe on shared networks. If the user has the older
"musescore-mcp-websocket" plug-in installed, suggest deleting it from
`~/Documents/MuseScore4/Plugins`: it accepts edits from anyone on the
network.

## 4c. Dorico (optional)

Only if the user works in Dorico 6.2 or newer. Claude Code starts the
`dorico` MCP server from `.mcp.json`; read the Dorico section of
[docs/dorico.md](../../../docs/dorico.md) for how the connection is made
and approved, and walk the user through it. Check with
`uv run --project "${CLAUDE_SKILL_DIR}" dorico-cli overview`.

## 5. Finish

Run `${CLAUDE_SKILL_DIR}/scripts/setup_check.sh --connect` one last time and show the result.
Then tell them in two or three sentences what they can do now, with
example requests they can type, for example:

- "Make rehearsal mixes of the open score."
- "Check the lyrics in the open score for typos."
- "Transpose the score up a whole step."

Mention that they can ask for setup again any time to re-check (`/setup`
in Claude Code, `$setup` in Codex, or just "check my setup").
