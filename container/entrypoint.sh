#!/usr/bin/env bash
#
# Container entrypoint for ai-score-editing-workflows autonomous agy runs.
#
# Responsibilities:
#   1. Forward localhost WebSocket ports (1898 Sibelius, 4560 Dorico, 8766 MuseScore)
#      to the macOS host (host.docker.internal) via socat, so existing tokens
#      keyed on localhost/127.0.0.1 and hardcoded localhost clients work unchanged.
#   2. Configure git identity and GitHub CLI (gh) credential helper for HTTPS
#      pushes and PR creation when GH_TOKEN is provided.
#   3. Ensure ~/.gemini/config/mcp_config.json registers the project's MCP servers
#      (sibelius, dorico, musescore, semble).
#   4. Clone or update the isolated workspace repository inside /home/agent/workspace
#      and run `uv sync`.
#   5. Launch `agy --dangerously-skip-permissions` (or execute custom command).

set -euo pipefail

HOST_GATEWAY="${SCORE_HOST_GATEWAY:-host.docker.internal}"
WORKSPACE_DIR="${WORKSPACE_DIR:-$HOME/workspace/ai-score-editing-workflows}"
REPO_URL="${REPO_URL:-https://github.com/wattdave/ai-score-editing-workflows.git}"
REPO_BRANCH="${REPO_BRANCH:-main}"

# Ensure mounted Docker volumes are owned by the current unprivileged user
for dir in "$HOME/.gemini" "$HOME/.config/ai-score-editing" "$(dirname "${WORKSPACE_DIR}")"; do
    if [ -d "$dir" ] && [ ! -w "$dir" ]; then
        sudo chown -R "$(id -u):$(id -g)" "$dir"
    fi
done

# ── 1. Forward score editor WebSocket ports to macOS host ────────────────────
start_port_forwarder() {
    local port="$1"
    local name="$2"
    if ! pgrep -f "socat TCP-LISTEN:${port}," >/dev/null 2>&1; then
        socat "TCP-LISTEN:${port},bind=127.0.0.1,reuseaddr,fork" \
              "TCP:${HOST_GATEWAY}:${port}" >/dev/null 2>&1 &
    fi
}

if [ "${FORWARD_EDITOR_PORTS:-1}" = "1" ]; then
    start_port_forwarder "${SIBELIUS_PORT:-1898}" "Sibelius Connect"
    start_port_forwarder "${DORICO_PORT:-4560}" "Dorico Remote Control"
    start_port_forwarder "${MUSESCORE_PORT:-8766}" "MuseScore ScoreBridge"
fi

# ── 2. Configure Git & GitHub CLI (gh) authentication ────────────────────────
if [ -n "${GIT_AUTHOR_NAME:-}" ]; then
    git config --global user.name "${GIT_AUTHOR_NAME}"
fi
if [ -n "${GIT_AUTHOR_EMAIL:-}" ]; then
    git config --global user.email "${GIT_AUTHOR_EMAIL}"
fi
git config --global init.defaultBranch main

if [ -n "${GH_TOKEN:-}" ]; then
    gh auth setup-git >/dev/null 2>&1 || true
fi

# ── 3. Prepare Isolated Repository Workspace ─────────────────────────────────
mkdir -p "$(dirname "${WORKSPACE_DIR}")"

if [ "${WORKSPACE_MODE:-clone}" = "mount" ]; then
    echo "✓ Using mounted workspace at ${WORKSPACE_DIR}"
else
    if [ ! -d "${WORKSPACE_DIR}/.git" ]; then
        echo "⠋ Cloning ${REPO_URL} (branch: ${REPO_BRANCH}) into ${WORKSPACE_DIR}..."
        if [ -d "/host-repo/.git" ]; then
            # Fast local clone from read-only host repo mount, then point origin to GitHub
            git clone --branch "${REPO_BRANCH}" /host-repo "${WORKSPACE_DIR}"
            git -C "${WORKSPACE_DIR}" remote set-url origin "${REPO_URL}"
            git -C "${WORKSPACE_DIR}" fetch origin --prune || true
        else
            git clone --branch "${REPO_BRANCH}" "${REPO_URL}" "${WORKSPACE_DIR}"
        fi
    else
        echo "✓ Existing container workspace found at ${WORKSPACE_DIR}"
        if [ "${REFRESH_WORKSPACE:-0}" = "1" ]; then
            echo "⠋ Fetching latest changes from origin..."
            git -C "${WORKSPACE_DIR}" fetch origin --prune || true
        fi
    fi
fi

cd "${WORKSPACE_DIR}"

echo "⠋ Syncing Python environment with uv..."
uv sync --locked

# ── 4. Configure Antigravity MCP servers (semble + score editors) ────────────
mkdir -p "$HOME/.gemini/config"
MCP_CONFIG="$HOME/.gemini/config/mcp_config.json"
if [ ! -f "${MCP_CONFIG}" ]; then
    cat > "${MCP_CONFIG}" <<EOF
{
  "mcpServers": {
    "semble": {
      "command": "semble",
      "args": ["mcp"]
    },
    "sibelius": {
      "command": "uv",
      "args": ["run", "--directory", "${WORKSPACE_DIR}", "sibelius-mcp"]
    },
    "dorico": {
      "command": "uv",
      "args": ["run", "--directory", "${WORKSPACE_DIR}", "dorico-mcp"]
    },
    "musescore": {
      "command": "uv",
      "args": ["run", "--directory", "${WORKSPACE_DIR}", "musescore-mcp"]
    }
  }
}
EOF
fi

# ── 5. Run Command or Launch Autonomous Antigravity CLI ──────────────────────
if [ "$#" -gt 0 ]; then
    case "$1" in
        bash|sh|zsh|pytest|uv|git|gh|python|python3)
            exec "$@"
            ;;
        agy)
            shift
            exec agy --dangerously-skip-permissions "$@"
            ;;
        *)
            exec agy --dangerously-skip-permissions "$@"
            ;;
    esac
else
    echo ""
    echo "========================================================================"
    echo "  Antigravity Autonomous Container (ai-score-editing-workflows)"
    echo "  Workspace: ${WORKSPACE_DIR}"
    echo "  Mode:      --dangerously-skip-permissions (Full container autonomy)"
    echo "  Bridges:   127.0.0.1:1898,4560,8766 -> ${HOST_GATEWAY}"
    echo "========================================================================"
    echo ""
    exec agy --dangerously-skip-permissions
fi
