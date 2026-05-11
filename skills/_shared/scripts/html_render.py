#!/usr/bin/env python3
"""CLI wrapper around qa_skills.html_render.write_html_report.

Usage:
    python skills/_shared/scripts/html_render.py \
      --report-data report-data.json \
      --out report-x.html
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from qa_skills.html_render import write_html_report  # noqa: E402

if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog="html_render")
    parser.add_argument("--report-data", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    data = json.loads(Path(args.report_data).read_text(encoding="utf-8"))
    out = write_html_report(data, args.out)
    print(json.dumps({"status": "completed", "html_report_path": str(out)}))
