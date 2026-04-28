#!/usr/bin/env bash
# Install qa-skills into Claude Code via symlinks.
# Edit skills in this repo → changes are live immediately, no reinstall needed.

set -e

SKILLS_DIR="$HOME/.claude/skills"
REPO_DIR="$(cd "$(dirname "$0")" && pwd)"

install_skill() {
  local name="$1"
  local src="$2"
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

install_skill "test-orchestrator" "$REPO_DIR/test-orchestrator"
install_skill "unit-test"         "$REPO_DIR/unit-test"
install_skill "api-test"          "$REPO_DIR/api-test"
install_skill "security-test"     "$REPO_DIR/security-test"
install_skill "ui-playwright"     "$REPO_DIR/ui-playwright"
install_skill "code-analyzer"     "$REPO_DIR/shared/code-analyzer"
install_skill "coverage-reporter" "$REPO_DIR/shared/coverage-reporter"
install_skill "html-reporter"     "$REPO_DIR/shared/html-reporter"

echo ""
echo "Done. Restart Claude Code (or open a new session) for skills to appear."
