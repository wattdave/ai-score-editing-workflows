#!/bin/zsh
# Prepare this Mac for an unattended overnight run of Claude Code driving
# MuseScore (or Sibelius/Dorico) from this terminal.
#
#   scripts/overnight_prep.sh [hours]     # default 10
#
# What it does:
#   1. Accessibility (System Events UI scripting): checks it; if missing,
#      opens the Settings pane. Needed to start the bridge from the Plugins
#      menu, read MuseScore's windows and dismiss dialogs.
#   2. Automation of System Events: the first check triggers the prompt.
#   3. Screen Recording: checks it with a test screenshot; if missing, opens
#      the Settings pane. Needed to see dialogs that Accessibility can't read.
#      macOS makes you quit and reopen the terminal after granting it, which
#      ends a running Claude Code session: grant it before starting one.
#   4. Starts caffeinate (display, idle, disk and system sleep) for [hours],
#      unless one started by this script is still running.
#   5. Reports whether the screen locks when idle; a locked screen stops UI
#      scripting and screenshots. It doesn't change that setting (that needs
#      your password): set Lock Screen to "Never" for the night.
#
# macOS doesn't let scripts grant privacy permissions, so steps 1 and 3 can
# only check and open the right pane. Run the script again after granting.

set -u
hours=${1:-10}
ok=1
pass() { print -P "%F{green}OK%f    $1"; }
fail() { print -P "%F{red}TODO%f  $1"; ok=0; }

app=${TERM_PROGRAM:-Terminal}
[[ $app == Apple_Terminal ]] && app=Terminal
print "Checking permissions for: $app\n"

# 1-2. Accessibility and Automation: list processes and read a window.
if out=$(osascript -e 'tell application "System Events" to get name of first process whose frontmost is true' 2>&1); then
    if osascript -e 'tell application "System Events" to get count of windows of (first process whose frontmost is true)' >/dev/null 2>&1; then
        pass "Accessibility and Automation (System Events)"
    else
        fail "Accessibility: turn on $app in the pane that just opened"
        open "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
    fi
else
    if [[ $out == *"-1743"* || $out == *"not allowed"* ]]; then
        fail "Automation: allow $app to control System Events (Privacy & Security > Automation)"
        open "x-apple.systempreferences:com.apple.preference.security?Privacy_Automation"
    else
        fail "Accessibility: turn on $app in the pane that just opened ($out)"
        open "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
    fi
fi

# 3. Screen Recording: a screenshot fails ("could not create image") without it.
shot=$(mktemp -t overnight).png
if screencapture -x "$shot" 2>/dev/null && [[ -s $shot ]]; then
    pass "Screen Recording"
else
    fail "Screen Recording: turn on $app, then quit and reopen $app (before starting Claude Code)"
    open "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"
fi
rm -f "$shot"

# 4. caffeinate.
pidfile=${TMPDIR:-/tmp}/overnight-caffeinate.pid
if [[ -f $pidfile ]] && kill -0 "$(<$pidfile)" 2>/dev/null; then
    pass "caffeinate already running (pid $(<$pidfile)); kill it to restart"
else
    nohup caffeinate -dimsu -t $((hours * 3600)) >/dev/null 2>&1 &
    print $! > "$pidfile"
    pass "caffeinate started for $hours h (pid $!): no sleep until it ends"
fi

# 5. Screen lock.
delay=$(sysadminctl -screenLock status 2>&1 | grep -oE 'delay is [0-9]+|immediate|off' | head -1)
if [[ $delay == off ]]; then
    pass "Screen lock is off"
else
    fail "Screen lock is on (${delay:-unknown}): set System Settings > Lock Screen to Never for tonight"
fi

print
if (( ok )); then
    print "Ready for an unattended run."
else
    print "Fix the TODO items above, then run this again."
    exit 1
fi
