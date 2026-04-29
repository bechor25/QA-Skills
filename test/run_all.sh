#!/usr/bin/env bash
# Run all QA-Skills self-validators
# Usage: bash test/run_all.sh
# Exit 0 if all pass, 1 if any fail.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VALIDATORS="$SCRIPT_DIR/validators"
PASSED=0
FAILED=0
ERRORS=()

echo "=== QA-Skills self-test suite ==="
echo ""

for f in "$VALIDATORS"/test_*.py; do
  name=$(basename "$f")
  printf "  %-50s" "$name"
  if python3 "$f" > /tmp/qa_skills_test_out.txt 2>&1; then
    echo "✅ PASS"
    ((PASSED++)) || true
  else
    echo "❌ FAIL"
    ((FAILED++)) || true
    ERRORS+=("$name")
    cat /tmp/qa_skills_test_out.txt | sed 's/^/    /'
  fi
done

echo ""
echo "=== Results: $PASSED passed, $FAILED failed ==="

if [ ${#ERRORS[@]} -gt 0 ]; then
  echo ""
  echo "Failed validators:"
  for e in "${ERRORS[@]}"; do
    echo "  - $e"
  done
  exit 1
fi

echo "All tests passed ✅"
