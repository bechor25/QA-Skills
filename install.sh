#!/usr/bin/env bash
# Install qa-skills into Claude Code via symlinks.
# Edit skills in this repo → changes are live immediately, no reinstall needed.
#
# Note: if you installed via `claude plugin install qa-skills`, you don't need this script.
# Use this only for local development from the repo.

set -e

SKILLS_DIR="$HOME/.claude/skills"
REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILLS_SRC="$REPO_DIR/skills"

install_skill() {
  local name="$1"
  local src="$SKILLS_SRC/$name"
  local dest="$SKILLS_DIR/$name"

  if [ -L "$dest" ]; then
    echo "  ✓ $name (already linked, skipping)"
  elif [ -d "$dest" ]; then
    echo "  ! $name exists as real directory — remove it first: rm -rf $dest"
  else
    ln -s "$src" "$dest"
    echo "  → $name"
  fi
}

echo "Installing qa-skills into $SKILLS_DIR"
echo ""

install_skill "test-orchestrator"
install_skill "unit-test"
install_skill "api-test"
install_skill "security-test"
install_skill "ui-playwright"
install_skill "code-analyzer"
install_skill "coverage-reporter"
install_skill "html-reporter"

echo ""
echo "Done. Restart Claude Code (or open a new session) for skills to appear."
