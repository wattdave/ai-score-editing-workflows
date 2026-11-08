#!/usr/bin/env bash
#
# Build and run the isolated Antigravity (agy) container for overnight
# autonomous coding, score workflows, and PR submission.
#
# Usage:
#   ./container/run.sh                      # Launch interactive agy TUI with full container autonomy
#   ./container/run.sh --goal "..."         # Run a prompt / overnight goal non-interactively or interactively
#   ./container/run.sh --shell              # Open a bash shell inside the container
#   ./container/run.sh --fresh              # Wipe the cloned container workspace and re-clone from main
#   ./container/run.sh --build              # Force rebuild of the Docker image
#   ./container/run.sh --mount-host-repo    # Bind-mount the host working tree instead of an isolated clone

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

IMAGE_NAME="ai-score-editing-agy:latest"
STATE_VOLUME="ai-score-editing-agy-gemini"
WORKSPACE_VOLUME="ai-score-editing-agy-workspace"

FORCE_BUILD=0
FRESH_WORKSPACE=0
WORKSPACE_MODE="clone"
SHELL_ONLY=0
SCORES_DIR="${SCORES_DIR:-}"
AGY_ARGS=()

show_help() {
    cat <<EOF
Usage: ./container/run.sh [options] [-- agy-args...]

Options:
  --build               Force rebuild the container image (${IMAGE_NAME})
  --fresh               Reset the isolated container workspace volume before starting
  --mount-host-repo     Bind-mount the host repository instead of cloning an isolated copy
  --scores-dir <path>   Mount a host folder of score files at /scores inside the container
  --shell               Start an interactive bash shell instead of agy
  -p, --prompt <text>   Run a prompt non-interactively (passes -p to agy)
  -i, --interactive <t> Start agy interactively with an initial prompt (passes -i to agy)
  -h, --help            Show this help message

Examples:
  ./container/run.sh
  ./container/run.sh -i "/goal Implement issue #42, run pytest, and open a PR"
  ./container/run.sh --fresh -p "Run pytest and report any issues"
EOF
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --build)
            FORCE_BUILD=1
            shift
            ;;
        --fresh)
            FRESH_WORKSPACE=1
            shift
            ;;
        --mount-host-repo)
            WORKSPACE_MODE="mount"
            shift
            ;;
        --scores-dir)
            SCORES_DIR="$2"
            shift 2
            ;;
        --shell)
            SHELL_ONLY=1
            shift
            ;;
        -p|--prompt)
            AGY_ARGS+=("-p" "$2")
            shift 2
            ;;
        -i|--interactive|--goal)
            AGY_ARGS+=("-i" "$2")
            shift 2
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        --)
            shift
            AGY_ARGS+=("$@")
            break
            ;;
        *)
            AGY_ARGS+=("$1")
            shift
            ;;
    esac
done

if ! command -v docker >/dev/null 2>&1; then
    echo "error: 'docker' CLI not found. Please start OrbStack (open -a OrbStack)." >&2
    exit 1
fi

if ! docker info >/dev/null 2>&1; then
    echo "⠋ Starting OrbStack daemon..."
    open -a OrbStack
    for _ in {1..15}; do
        if docker info >/dev/null 2>&1; then
            break
        fi
        sleep 1
    done
fi

# 1. Build image if missing or requested
if [ "${FORCE_BUILD}" = "1" ] || ! docker image inspect "${IMAGE_NAME}" >/dev/null 2>&1; then
    echo "⠋ Building container image ${IMAGE_NAME}..."
    docker build -t "${IMAGE_NAME}" "${REPO_ROOT}"
fi

# 2. Reset workspace volume if --fresh requested
if [ "${FRESH_WORKSPACE}" = "1" ] && [ "${WORKSPACE_MODE}" = "clone" ]; then
    echo "⠋ Resetting isolated workspace volume ${WORKSPACE_VOLUME}..."
    docker volume rm -f "${WORKSPACE_VOLUME}" >/dev/null 2>&1 || true
fi

# 3. Gather Git identity and GitHub token from host (without exposing raw files)
GIT_AUTHOR_NAME="$(git -C "${REPO_ROOT}" config user.name || echo "David Watt")"
GIT_AUTHOR_EMAIL="$(git -C "${REPO_ROOT}" config user.email || echo "ai-score-editing-workflows@dave.wattlink.net")"
GIT_COMMITTER_NAME="${GIT_AUTHOR_NAME}"
GIT_COMMITTER_EMAIL="${GIT_AUTHOR_EMAIL}"

GH_TOKEN_VAL="${GH_TOKEN:-}"
if [ -z "${GH_TOKEN_VAL}" ] && command -v gh >/dev/null 2>&1; then
    GH_TOKEN_VAL="$(gh auth token 2>/dev/null || true)"
fi

# 4. Prepare volume mounts
DOCKER_MOUNTS=(
    # Persist Antigravity CLI login & conversation state across container runs
    "-v" "${STATE_VOLUME}:/home/agent/.gemini"
    # Read-only mount of host repo for fast initial git clone
    "-v" "${REPO_ROOT}:/host-repo:ro"
)

if [ "${WORKSPACE_MODE}" = "mount" ]; then
    DOCKER_MOUNTS+=("-v" "${REPO_ROOT}:/home/agent/workspace/ai-score-editing-workflows")
else
    DOCKER_MOUNTS+=("-v" "${WORKSPACE_VOLUME}:/home/agent/workspace")
fi

# Mount score editor session tokens (Sibelius, Dorico, MuseScore) if present on host
HOST_CONFIG_DIR="${HOME}/.config/ai-score-editing"
mkdir -p "${HOST_CONFIG_DIR}"
DOCKER_MOUNTS+=("-v" "${HOST_CONFIG_DIR}:/home/agent/.config/ai-score-editing")

# Optional scores directory mount
HELPER_PID=""
cleanup_helper() {
    if [ -n "${HELPER_PID}" ] && kill -0 "${HELPER_PID}" >/dev/null 2>&1; then
        kill "${HELPER_PID}" >/dev/null 2>&1 || true
    fi
}
trap cleanup_helper EXIT

if [ -n "${SCORES_DIR}" ]; then
    RESOLVED_SCORES="$(cd "${SCORES_DIR}" && pwd)"
    DOCKER_MOUNTS+=("-v" "${RESOLVED_SCORES}:/scores")
    # Start the host-side Sibelius helper on 127.0.0.1:1899 so the container can
    # open .musicxml/.sib files in Sibelius and press Return on the import dialog.
    if ! pgrep -f "sibelius_host_helper.py" >/dev/null 2>&1; then
        python3 "${SCRIPT_DIR}/sibelius_host_helper.py" --port 1899 --scores-dir "${RESOLVED_SCORES}" >/dev/null 2>&1 &
        HELPER_PID="$!"
    fi
fi

# 5. Run container
TTY_FLAGS=("-i")
if [ -t 0 ] && [ -t 1 ]; then
    TTY_FLAGS+=("-t")
fi

DOCKER_ENV=(
    "-e" "GIT_AUTHOR_NAME=${GIT_AUTHOR_NAME}"
    "-e" "GIT_AUTHOR_EMAIL=${GIT_AUTHOR_EMAIL}"
    "-e" "GIT_COMMITTER_NAME=${GIT_COMMITTER_NAME}"
    "-e" "GIT_COMMITTER_EMAIL=${GIT_COMMITTER_EMAIL}"
    "-e" "WORKSPACE_MODE=${WORKSPACE_MODE}"
    "-e" "SCORE_HOST_GATEWAY=host.docker.internal"
)

if [ -n "${GH_TOKEN_VAL}" ]; then
    DOCKER_ENV+=("-e" "GH_TOKEN=${GH_TOKEN_VAL}")
fi

if [ "${SHELL_ONLY}" = "1" ]; then
    docker run --rm "${TTY_FLAGS[@]}" \
        --add-host=host.docker.internal:host-gateway \
        "${DOCKER_MOUNTS[@]}" \
        "${DOCKER_ENV[@]}" \
        "${IMAGE_NAME}" \
        bash "${AGY_ARGS[@]}"
else
    docker run --rm "${TTY_FLAGS[@]}" \
        --add-host=host.docker.internal:host-gateway \
        "${DOCKER_MOUNTS[@]}" \
        "${DOCKER_ENV[@]}" \
        "${IMAGE_NAME}" \
        "${AGY_ARGS[@]}"
fi
