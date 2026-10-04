#!/bin/bash
# Start the MuseScore MCP server (github.com/ghchen99/mcp-musescore) over stdio.
#
# .mcp.json runs this when Claude Code starts in this folder. On first run it
# downloads the server at the pinned commit into .vendor/mcp-musescore and
# copies its plug-in into MuseScore's plug-ins folder; later runs reuse both.
# uv supplies Python and the server's two packages, outside the project's venv.
#
# stdout carries the MCP protocol, so everything else goes to stderr.

set -euo pipefail

repo=https://github.com/ghchen99/mcp-musescore.git
commit=66416a11305102558e34b57a0066c05cead9fed1
plugin=musescore-mcp-websocket.qml
plugin_dir="${MUSESCORE_PLUGIN_DIR:-$HOME/Documents/MuseScore4/Plugins}"

cd "$(dirname "$0")/.."
dest=.vendor/mcp-musescore

if [ "$(git -C "$dest" rev-parse HEAD 2>/dev/null)" != "$commit" ]; then
    echo "musescore-mcp: fetching $repo at ${commit:0:7}" >&2
    if [ ! -d "$dest/.git" ]; then
        rm -rf "$dest"
        git init -q "$dest"
        git -C "$dest" remote add origin "$repo"
    fi
    git -C "$dest" fetch -q --depth 1 origin "$commit" >&2
    git -C "$dest" checkout -q --detach FETCH_HEAD >&2
fi

if ! cmp -s "$dest/$plugin" "$plugin_dir/$plugin"; then
    mkdir -p "$plugin_dir"
    cp "$dest/$plugin" "$plugin_dir/$plugin"
    echo "musescore-mcp: installed $plugin in $plugin_dir" >&2
fi

cd "$dest"
exec uv run --quiet --no-project --python 3.13 \
    --with 'mcp[cli]<2' --with websockets \
    python server.py
