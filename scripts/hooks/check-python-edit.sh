#!/usr/bin/env bash
# PostToolUse hook: syntax-check an edited engine file immediately.
#
# A syntax error inside qa_agent/ breaks every pipeline phase downstream, so catching it at
# edit time is far cheaper than at pytest time. Reads the Claude Code tool payload on stdin,
# extracts the edited path, and exits 0 quietly for anything that is not a qa_agent .py file.
set -uo pipefail

PAYLOAD="$(cat 2>/dev/null || true)"
[ -z "$PAYLOAD" ] && exit 0

FILE_PATH="$(printf '%s' "$PAYLOAD" | python3 -c '
import json, sys
try:
    payload = json.load(sys.stdin)
except Exception:
    sys.exit(0)
data = payload.get("tool_input") or payload.get("toolInput") or {}
print(data.get("file_path") or data.get("path") or "")
' 2>/dev/null)"

case "$FILE_PATH" in
  *qa_agent/*.py) ;;
  *) exit 0 ;;
esac

[ -f "$FILE_PATH" ] || exit 0

if ! OUT="$(python3 -m py_compile "$FILE_PATH" 2>&1)"; then
  echo "syntax error in $FILE_PATH:" >&2
  echo "$OUT" >&2
  echo "fix it before running pytest — every downstream phase imports this package." >&2
  exit 2   # exit 2 feeds the message back to Claude as actionable feedback
fi

exit 0
