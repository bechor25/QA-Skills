#!/usr/bin/env bash
# qa-skills-bootstrap — first-run dependency setup for the qa-skills plugin.
#
# Creates an isolated virtualenv under the plugin root and installs the
# `qa-agent` Python package into it. Idempotent: subsequent invocations
# detect an existing venv and return the binary path without reinstalling.
#
# Exits with the absolute path to the `qa-agent` binary on stdout so a
# wrapper script can exec it directly:
#
#     QA_AGENT_BIN="$(qa-skills-bootstrap.sh)"
#     exec "$QA_AGENT_BIN" "$@"
#
# Honors CLAUDE_PLUGIN_ROOT when set (Claude Code injects it). Falls back
# to the script's own parent directory so the script also works when run
# from a `git clone` outside the plugin runtime.

set -euo pipefail

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
VENV="$PLUGIN_ROOT/.venv"
QA_AGENT_BIN="$VENV/bin/qa-agent"

# Already bootstrapped — fast path.
if [ -x "$QA_AGENT_BIN" ]; then
  echo "$QA_AGENT_BIN"
  exit 0
fi

# Locate a Python 3.11+ interpreter.
PYTHON=""
for cand in python3.13 python3.12 python3.11 python3; do
  if command -v "$cand" >/dev/null 2>&1; then
    ver=$("$cand" -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
    major=${ver%%.*}
    minor=${ver##*.}
    if [ "$major" -ge 4 ] || { [ "$major" = "3" ] && [ "$minor" -ge 11 ]; }; then
      PYTHON="$cand"
      break
    fi
  fi
done

if [ -z "$PYTHON" ]; then
  echo "qa-skills: Python 3.11+ is required but was not found in PATH" >&2
  echo "qa-skills: install Python 3.11+ and re-run the plugin" >&2
  exit 1
fi

echo "qa-skills: bootstrapping venv at $VENV using $PYTHON" >&2
"$PYTHON" -m venv "$VENV"
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -e "$PLUGIN_ROOT" 1>&2

if [ ! -x "$QA_AGENT_BIN" ]; then
  echo "qa-skills: bootstrap completed but qa-agent binary is missing at $QA_AGENT_BIN" >&2
  exit 1
fi

echo "qa-skills: bootstrap complete" >&2
echo "$QA_AGENT_BIN"
