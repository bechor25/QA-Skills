#!/usr/bin/env bash
# Bootstrap the qa-skills development environment.
# Idempotent: safe to re-run. Creates .venv, installs the package editable with the
# parsing + dev extras, and verifies the test suite can collect.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${VENV_DIR:-$REPO_ROOT/.venv}"

echo "==> python: $("$PYTHON_BIN" --version)"
"$PYTHON_BIN" - <<'PY'
import sys
if sys.version_info < (3, 11):
    sys.exit(f"qa-agent requires Python >= 3.11, found {sys.version.split()[0]}")
PY

if [ ! -d "$VENV_DIR" ]; then
  echo "==> creating venv at $VENV_DIR"
  "$PYTHON_BIN" -m venv "$VENV_DIR"
else
  echo "==> reusing venv at $VENV_DIR"
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

echo "==> upgrading pip"
python -m pip install --quiet --upgrade pip

echo "==> installing qa-agent (editable, extras: parsing,dev)"
if ! python -m pip install --quiet -e '.[parsing,dev]'; then
  echo "!! parsing extra failed (tree-sitter wheels are platform-specific)"
  echo "!! falling back to the dev extra only — AST parsing degrades gracefully"
  python -m pip install --quiet -e '.[dev]'
fi

echo "==> verifying test collection"
python -m pytest qa_agent/tests --collect-only -q | tail -n 3

cat <<'EOF'

Setup complete.

  source .venv/bin/activate
  pytest qa_agent/tests            # full verification gate
  scripts/hooks/check-skill-budgets.sh
EOF
