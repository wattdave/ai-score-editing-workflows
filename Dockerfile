# Container image for running Google Antigravity CLI (agy) autonomously with
# full tool permissions on ai-score-editing-workflows.
#
# Build / launch via:
#   ./container/run.sh

FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive

# Install core CLI utilities, GitHub CLI, media/score pipelines, and socat
# (socat forwards localhost:1898/4560/8766 inside the container to the macOS
# host's Sibelius, Dorico, and MuseScore WebSocket bridges).
RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    ca-certificates \
    curl \
    ffmpeg \
    git \
    gnupg \
    jq \
    less \
    lilypond \
    openssh-client \
    pandoc \
    poppler-utils \
    procps \
    ripgrep \
    socat \
    sudo \
    tzdata \
    unzip \
    && mkdir -p -m 755 /etc/apt/keyrings \
    && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
       | dd of=/etc/apt/keyrings/githubcli-archive-keyring.gpg \
    && chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
       > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends gh \
    && rm -rf /var/lib/apt/lists/*

# Create unprivileged agent user matching typical macOS UID (501) or standard Linux UID
ARG USERNAME=agent
RUN useradd -m -s /bin/bash "${USERNAME}" \
    && echo "${USERNAME} ALL=(ALL) NOPASSWD:ALL" > "/etc/sudoers.d/${USERNAME}" \
    && chmod 0440 "/etc/sudoers.d/${USERNAME}"

USER ${USERNAME}
ENV HOME=/home/${USERNAME}
ENV UV_TOOL_BIN_DIR=/home/${USERNAME}/.local/bin
ENV UV_TOOL_DIR=/home/${USERNAME}/.local/share/uv/tools
ENV UV_LINK_MODE=copy
ENV PATH="/home/${USERNAME}/.local/bin:${PATH}"

RUN mkdir -p "${HOME}/.gemini/config" "${HOME}/.config/ai-score-editing" "${HOME}/workspace"

# Install Google Antigravity CLI (agy) and pre-warm uv tools (semble, python-ly)
RUN curl -fsSL https://antigravity.google/cli/install.sh | bash \
    && agy --version \
    && uv tool install "semble[mcp]==0.6.1" \
    && uv tool install python-ly

# Pre-warm the project's Python virtual environment cache so container clones
# sync instantaneously without downloading wheels on every run.
WORKDIR /home/${USERNAME}/workspace
COPY --chown=${USERNAME}:${USERNAME} pyproject.toml uv.lock README.md ./
COPY --chown=${USERNAME}:${USERNAME} src ./src
RUN uv sync --locked && rm -rf /home/${USERNAME}/workspace/*

COPY --chown=${USERNAME}:${USERNAME} container/entrypoint.sh /usr/local/bin/container-entrypoint.sh
COPY --chown=${USERNAME}:${USERNAME} container/sibelius_host_open.py /usr/local/bin/sibelius-host-open
RUN chmod +x /usr/local/bin/container-entrypoint.sh /usr/local/bin/sibelius-host-open \
    && printf '#!/bin/sh\nexec sleep infinity\n' | sudo tee /usr/local/bin/Sibelius >/dev/null \
    && sudo chmod +x /usr/local/bin/Sibelius \
    && sudo ln -sf /usr/local/bin/Sibelius /usr/local/bin/sibelius

WORKDIR /home/${USERNAME}/workspace
ENTRYPOINT ["/usr/local/bin/container-entrypoint.sh"]
