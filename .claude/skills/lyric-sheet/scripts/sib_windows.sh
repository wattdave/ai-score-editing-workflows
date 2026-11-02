#!/bin/zsh
# Answer Sibelius dialogs and close score windows, using accessibility clicks
# only (never keystrokes), so a score can be read and put away safely.
#
#   sib_windows.sh update-ok     click OK on an "Update Score: <file>" dialog
#                                (old-format file; the update is in memory only)
#   sib_windows.sh no-save       answer "Do you want to save the changes" with
#                                No (or "Don't Save" on a sheet)
#   sib_windows.sh close FILE    close the window of FILE (.sib path or name)
#   sib_windows.sh list          print the names of Sibelius's windows
#
# Needs Accessibility permission for the terminal. Never saves anything.
cmd="$1"; shift
case "$cmd" in
update-ok)
osascript <<'OSA'
tell application "System Events"
  if not (exists process "Sibelius") then return "none"
  tell process "Sibelius"
    repeat with w in windows
      if (name of w) starts with "Update Score" then
        click button "OK" of w
        return "ok-clicked"
      end if
    end repeat
  end tell
end tell
return "none"
OSA
;;
no-save)
osascript <<'OSA'
tell application "System Events"
  if not (exists process "Sibelius") then return "none"
  tell process "Sibelius"
    repeat with w in windows
      try
        if (exists button "No" of w) and (exists button "Yes" of w) then
          click button "No" of w
          return "no-clicked"
        end if
      end try
      try
        if (exists sheet 1 of w) and (exists button "Don't Save" of sheet 1 of w) then
          click button "Don't Save" of sheet 1 of w
          return "dontsave-clicked"
        end if
      end try
    end repeat
  end tell
end tell
return "none"
OSA
;;
close)
name="${1:t:r}"
script_dir="${0:A:h}"
osascript - "$name" "$script_dir/sib_windows.sh" <<'OSA'
on run argv
  set nm to item 1 of argv
  set me_ to item 2 of argv
  set found to ""
  tell application "System Events"
    if not (exists process "Sibelius") then return "no-sibelius"
    tell process "Sibelius"
      repeat with w in windows
        set wn to name of w
        if wn contains nm then
          set found to wn
          click (first button of w whose subrole is "AXCloseButton")
          exit repeat
        end if
      end repeat
    end tell
  end tell
  if found is "" then return "no-window-for " & nm
  delay 1
  do shell script quoted form of me_ & " no-save"
  return "closed " & found
end run
OSA
;;
list)
osascript -e 'tell application "System Events" to get name of every window of process "Sibelius"'
;;
*) echo "usage: sib_windows.sh update-ok|no-save|close FILE|list" >&2; exit 2;;
esac
