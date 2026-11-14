#!/bin/bash
# Blocking lock for the one Sibelius/macOS GUI that several agents share.
#
#   gui_lock.sh acquire NAME TASK [TIMEOUT_SECONDS]   wait until the lock is ours; exit 0 only then
#   gui_lock.sh release NAME                          release it (refuses if NAME is not the owner)
#   gui_lock.sh status                                owner line and age in minutes; exit 1 if free
#
# The lock is a directory (mkdir is atomic). GUI_LOCK_DIR sets where (default
# $HOME/.sibelius-gui-lock); use one shared folder when agents run in different
# checkouts. acquire never exits 0 without holding the lock, so
# `gui_lock.sh acquire me task || exit 1` is safe before any GUI step.
set -u
L="${GUI_LOCK_DIR:-$HOME/.sibelius-gui-lock}"
cmd="${1:-}"
case "$cmd" in
acquire)
  name="${2:?name}"; task="${3:?task}"; timeout="${4:-0}"; waited=0
  until mkdir "$L" 2>/dev/null; do
    if [ "$timeout" -gt 0 ] && [ "$waited" -ge "$timeout" ]; then
      echo "TIMEOUT waiting for the GUI lock: $(cat "$L/owner" 2>/dev/null)" >&2
      exit 1
    fi
    sleep 1; waited=$((waited + 1))
  done
  echo "$name $task $(date '+%F %T')" > "$L/owner"
  echo "GOT"
  ;;
release)
  name="${2:?name}"
  owner="$(cat "$L/owner" 2>/dev/null)"
  case "$owner" in
    "$name "*) rm -rf "$L"; echo "RELEASED" ;;
    *) echo "not releasing: owner is '${owner:-nobody}'" >&2; exit 1 ;;
  esac
  ;;
status)
  [ -d "$L" ] || { echo "free"; exit 1; }
  mtime=$(stat -c %Y "$L/owner" 2>/dev/null || stat -f %m "$L/owner" 2>/dev/null || echo 0)
  echo "$(cat "$L/owner" 2>/dev/null) ($(( ( $(date +%s) - mtime ) / 60 )) min old)"
  ;;
*)
  echo "usage: gui_lock.sh acquire NAME TASK [TIMEOUT] | release NAME | status" >&2
  exit 2
  ;;
esac
