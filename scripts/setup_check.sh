#!/bin/bash
# Report which setup requirements are met. Changes nothing.
#
# Usage: scripts/setup_check.sh [--connect]
#   --connect  also ask the running Sibelius for the bridge plug-in version
#              (the first connection per Sibelius launch shows an approval
#              dialog in Sibelius)
#
# Prints one line per requirement: "ok|missing|warn|optional <name> <detail>".
# Exits 0 when everything required is ok, 1 otherwise.

cd "$(dirname "$0")/.." || exit 2

# Homebrew is not on PATH in a fresh shell until ~/.zprofile is updated.
for prefix in /opt/homebrew /usr/local; do
    [ -x "$prefix/bin/brew" ] && eval "$("$prefix/bin/brew" shellenv)" && break
done
export PATH="$HOME/.local/bin:$PATH"

failed=0
report() {
    printf '%-8s %-18s %s\n' "$1" "$2" "$3"
    [ "$1" = missing ] && failed=1
}

if [ "$(uname -s)" = Darwin ]; then
    report ok macos "$(sw_vers -productVersion) ($(uname -m))"
else
    report missing macos "this project needs a Mac; found $(uname -s)"
fi

if xcode-select -p >/dev/null 2>&1; then
    report ok xcode-tools "$(xcode-select -p)"
else
    report missing xcode-tools "Apple Command Line Tools (Homebrew installs them)"
fi

if command -v brew >/dev/null 2>&1; then
    report ok homebrew "$(brew --version | head -1)"
    if ! grep -qs 'brew shellenv' "$HOME/.zprofile"; then
        report warn homebrew-path "brew is not added to ~/.zprofile; new Terminal windows will not find it"
    fi
else
    report missing homebrew "https://brew.sh"
fi

if command -v git >/dev/null 2>&1 && git --version >/dev/null 2>&1; then
    report ok git "$(git --version)"
else
    report missing git "brew install git"
fi

if command -v uv >/dev/null 2>&1; then
    report ok uv "$(uv --version)"
    if py=$(uv python find 3.13 2>/dev/null); then
        report ok python-3.13 "$py"
    else
        report missing python-3.13 "uv python install 3.13"
    fi
else
    report missing uv "brew install uv"
    report missing python-3.13 "installed by uv once uv is present"
fi

if command -v ffmpeg >/dev/null 2>&1; then
    report ok ffmpeg "$(ffmpeg -version 2>/dev/null | head -1 | cut -d' ' -f1-3)"
else
    report missing ffmpeg "brew install ffmpeg (needed for rehearsal mixes)"
fi

# Optional: only needed to convert LilyPond sources (lilypond-to-score skill).
if command -v lilypond >/dev/null 2>&1; then
    report ok lilypond "$(lilypond --version 2>/dev/null | head -1)"
else
    report optional lilypond "brew install lilypond (only for LilyPond sources)"
fi
if command -v uv >/dev/null 2>&1; then
    report ok python-ly "runs on demand with: uvx --from python-ly ly musicxml"
else
    report optional python-ly "installed by uv once uv is present"
fi

if [ -x .venv/bin/sibelius-cli ]; then
    report ok project-deps ".venv is set up"
else
    report missing project-deps "uv sync"
fi

sib=""
for app in /Applications/Sibelius.app "$HOME/Applications/Sibelius.app"; do
    [ -d "$app" ] && sib="$app" && break
done
if [ -n "$sib" ]; then
    version=$(defaults read "$sib/Contents/Info.plist" CFBundleShortVersionString 2>/dev/null)
    major=${version%%.*}
    rest=${version#*.}
    minor=${rest%%.*}
    # Bundle versions are year-based: 26.6 is Sibelius 2026.6.
    if [ -n "$major" ] && { [ "$major" -gt 26 ] || { [ "$major" -eq 26 ] && [ "$minor" -ge 6 ]; }; }; then
        report ok sibelius "$sib version $version"
    else
        report missing sibelius "$sib version $version is older than 2026.6"
    fi
else
    report missing sibelius "Sibelius Ultimate 2026.6+ not found in Applications"
fi

support=$(ls -d "$HOME/Library/Application Support/Avid/Sibelius"* 2>/dev/null | sort | tail -1)
if [ -z "$support" ]; then
    report missing sibelius-launched "open Sibelius once so it creates its support folder"
elif [ -f "$support/Plugins/ScoreBridge/ScoreBridge.plg" ]; then
    report ok bridge-plugin "$support/Plugins/ScoreBridge/ScoreBridge.plg"
else
    report missing bridge-plugin "uv run sibelius-cli install-plugin"
fi

if [ "$1" = --connect ]; then
    if [ -z "$sib" ] || ! pgrep -xq Sibelius; then
        report missing connection "Sibelius is not running"
    elif out=$(uv run sibelius-cli --no-launch --timeout 30 bridge-version 2>&1); then
        report ok connection "$(echo "$out" | tr '\n' ' ')"
    else
        report missing connection "$(echo "$out" | tail -1)"
    fi
fi

exit $failed
