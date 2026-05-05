#!/usr/bin/env bash
# Install qa-skills into Claude Code via symlinks.
# Installs three things:
#   1. skills/    → ~/.claude/skills/         (thin trigger entry points)
#   2. agents/    → ~/.claude/agents/         (heavy QA logic, isolated subagents)
#   3. reference/ → ~/.claude/qa-skills-reference/  (code patterns loaded on demand)
#
# Edit files in this repo → changes are live immediately, no reinstall needed.
#
# If you installed via `claude plugin install qa-skills`, this script is not needed.

set -e

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILLS_SRC="$REPO_DIR/skills"
AGENTS_SRC="$REPO_DIR/agents"
REFERENCE_SRC="$REPO_DIR/reference"

SKILLS_DIR="$HOME/.claude/skills"
AGENTS_DIR="$HOME/.claude/agents"
REFERENCE_DIR="$HOME/.claude/qa-skills-reference"

mkdir -p "$SKILLS_DIR" "$AGENTS_DIR"

install_skill() {
  local name="$1"
  local src="$SKILLS_SRC/$name"
  local dest="$SKILLS_DIR/$name"

  if [ -L "$dest" ]; then
    echo "  ✓ skill $name (linked, skipping)"
  elif [ -d "$dest" ]; then
    echo "  ! skill $name exists as real dir — remove first: rm -rf $dest"
  else
    ln -s "$src" "$dest"
    echo "  → skill $name"
  fi
}

install_agent() {
  local name="$1"  # e.g. qa-ui-test
  local src="$AGENTS_SRC/$name.md"
  local dest="$AGENTS_DIR/$name.md"

  if [ ! -f "$src" ]; then
    echo "  ! agent file missing: $src"
    return
  fi

  if [ -L "$dest" ]; then
    echo "  ✓ agent $name (linked, skipping)"
  elif [ -f "$dest" ]; then
    echo "  ! agent $name exists as real file — remove first: rm $dest"
  else
    ln -s "$src" "$dest"
    echo "  → agent $name"
  fi
}

install_reference() {
  if [ -L "$REFERENCE_DIR" ]; then
    echo "  ✓ reference (linked, skipping)"
  elif [ -d "$REFERENCE_DIR" ]; then
    echo "  ! reference exists as real dir — remove first: rm -rf $REFERENCE_DIR"
  else
    ln -s "$REFERENCE_SRC" "$REFERENCE_DIR"
    echo "  → reference → $REFERENCE_DIR"
  fi
}

echo "Installing qa-skills:"
echo ""
echo "  Skills (triggers) → $SKILLS_DIR"
install_skill "test-orchestrator"
install_skill "unit-test"
install_skill "api-test"
install_skill "security-test"
install_skill "ui-playwright"
install_skill "accessibility-test"
install_skill "contract-test"
install_skill "flaky-detector"
install_skill "env-validator"
install_skill "git-diff-analyzer"
install_skill "code-analyzer"
install_skill "coverage-reporter"
install_skill "html-reporter"

echo ""
echo "  Agents (isolated workers) → $AGENTS_DIR"
install_agent "qa-orchestrator"
install_agent "qa-code-analyzer"
install_agent "qa-env-validator"
install_agent "qa-git-diff-analyzer"
install_agent "qa-unit-test"
install_agent "qa-api-test"
install_agent "qa-ui-test"
install_agent "qa-security-test"
install_agent "qa-a11y-test"
install_agent "qa-contract-test"
install_agent "qa-flaky-detector"
install_agent "qa-coverage-reporter"
install_agent "qa-html-reporter"

echo ""
echo "  Reference patterns → $REFERENCE_DIR"
install_reference

echo ""
echo "Done. Restart Claude Code (or open a new session) for skills + agents to appear."
