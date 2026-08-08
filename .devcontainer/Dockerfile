# Standalone dev/CI image for qa-skills.
# The devcontainer uses the prebuilt Microsoft image plus scripts/setup.sh; this Dockerfile
# exists for plain `docker build` use and for agents that need one reproducible environment
# identical to CI.
FROM python:3.12-slim-bookworm

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# git is needed by the resume/diff logic; build-essential backs tree-sitter source builds
RUN apt-get update \
    && apt-get install -y --no-install-recommends git build-essential curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

# Copy metadata first so dependency layers cache across source edits
COPY pyproject.toml README.md ./
COPY qa_agent ./qa_agent

RUN python -m pip install --upgrade pip \
    && (pip install -e '.[parsing,dev]' || pip install -e '.[dev]')

COPY . .

CMD ["pytest", "qa_agent/tests"]
