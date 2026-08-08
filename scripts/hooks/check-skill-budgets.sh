#!/usr/bin/env bash
# Verify the plugin's Markdown surface stays inside its context budgets.
#
# Frontmatter loads in EVERY session, so oversized metadata taxes every conversation;
# an oversized body defeats progressive disclosure. Budgets:
#   frontmatter <= 100 tokens, body <= 5000 tokens, body <= 300 lines,
#   inline tables <= 20 data rows.
#
# Exit 0 = within budget, exit 1 = at least one violation.
# Also usable as a Claude Code PostToolUse hook (reads the tool payload from stdin and
# exits 0 quietly when the edited file is not a skill/agent Markdown file).
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# Hook mode: stdin carries the tool payload. Bail out quietly unless a skill/agent .md
# was touched, so the hook stays free on unrelated edits.
if [ ! -t 0 ]; then
  PAYLOAD="$(cat || true)"
  if [ -n "$PAYLOAD" ]; then
    case "$PAYLOAD" in
      *SKILL.md*|*/agents/*.md*) ;;
      *) exit 0 ;;
    esac
  fi
fi

cd "$REPO_ROOT"
python3 - <<'PY'
import pathlib
import re
import sys

REPO = pathlib.Path.cwd()
MAX_META, MAX_BODY, MAX_LINES, MAX_ROWS = 100, 5000, 300, 20

def tokens(text: str) -> int:
    # Cheap proxy: ~4 characters per token. Good enough for a budget guard.
    return round(len(text) / 4)

def split(path: pathlib.Path):
    raw = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", raw, re.S)
    return (m.group(1), m.group(2)) if m else ("", raw)

def max_table_rows(body: str) -> int:
    best = run = 0
    for line in body.splitlines():
        s = line.strip()
        if s.startswith("|") and s.endswith("|"):
            if re.fullmatch(r"\|[\s:|-]+\|", s):
                continue
            run += 1
            best = max(best, run)
        else:
            run = 0
    return max(best - 1, 0)  # discount the header row

targets = sorted(REPO.glob("skills/*/SKILL.md")) + sorted(REPO.glob("agents/*.md"))
if not targets:
    print("no skill or agent Markdown files found")
    sys.exit(0)

violations = []
rows = []
for path in targets:
    rel = path.relative_to(REPO)
    meta, body = split(path)
    mt, bt = tokens(meta), tokens(body)
    lines = body.count("\n") + 1
    trows = max_table_rows(body)
    rows.append((str(rel), mt, bt, lines, trows))

    if mt > MAX_META:
        violations.append(f"{rel}: frontmatter ~{mt} tokens > {MAX_META} — trim the description")
    if bt > MAX_BODY:
        violations.append(f"{rel}: body ~{bt} tokens > {MAX_BODY} — move detail to references/")
    if lines > MAX_LINES and not (path.parent / "references").is_dir():
        violations.append(f"{rel}: body {lines} lines > {MAX_LINES} with no sibling references/ — split it")
    if trows > MAX_ROWS:
        violations.append(f"{rel}: inline table has {trows} data rows > {MAX_ROWS} — move it to references/")

width = max(len(r[0]) for r in rows)
print(f"{'file'.ljust(width)}  meta  body  lines  rows")
for name, mt, bt, lines, trows in rows:
    print(f"{name.ljust(width)}  {mt:>4}  {bt:>4}  {lines:>5}  {trows:>4}")

if violations:
    print("\nbudget violations:")
    for v in violations:
        print(f"  - {v}")
    sys.exit(1)

print("\nall skills and agents within budget")
PY
