#!/bin/zsh
# Restart MuseScore on a score and start the "sibwscli bridge" plug-in, with
# no one at the keyboard (for unattended runs; see scripts/overnight_prep.sh).
#
#   scripts/musescore_restart.sh [score.mscz]
#     default: ~/Documents/MuseScore4/Scores/ScratchScore.mscz
#
# It reinstalls the bridge (a changed plug-in only loads at startup), quits
# MuseScore WITHOUT SAVING (unsaved changes are lost; force-quits after 20 s),
# reopens the score, answers No to "The previous session quit unexpectedly.
# Restore?" (its buttons ignore scripted clicks; Escape works), starts the
# bridge from the Plugins menu and prints the start of `musescore-cli
# overview`. Needs Accessibility permission for the terminal. The bridge must
# already be enabled in Plugins > Manage plugins.

set -u
score=${1:-$HOME/Documents/MuseScore4/Scores/ScratchScore.mscz}
name=${${score:t}:r}
cd "${0:A:h}/.."

uv run musescore-cli install-plugin >/dev/null

# Without the timeout, quit waits on the save dialog; the -128 error is harmless.
osascript <<'AS' 2>/dev/null
with timeout of 10 seconds
  tell application "MuseScore 4" to quit saving no
end timeout
AS
for i in {1..20}; do pgrep -x mscore >/dev/null || break; sleep 1; done
pkill -x mscore && sleep 2

open -a "MuseScore 4" "$score"
sleep 15

osascript <<'AS'
tell application "System Events" to tell process "mscore"
  repeat with w in windows
    try
      if (name of buttons of w) contains "No" then
        set frontmost to true
        perform action "AXRaise" of w
        delay 0.5
        key code 53
        delay 1
      end if
    end try
  end repeat
end tell
AS

# After the restore dialog MuseScore shows its Home screen: open the score again.
if ! osascript -e 'tell application "System Events" to tell process "mscore" to return name of windows' | grep -qF "$name"; then
  open -a "MuseScore 4" "$score"
  sleep 8
fi

osascript <<'AS' >/dev/null
tell application "System Events" to tell process "mscore"
  set frontmost to true
  click menu item "sibwscli bridge" of menu "Plugins" of menu bar 1
end tell
AS
sleep 2
uv run musescore-cli overview | head -8
