"""`qa-agent report` — render the latest HTML report."""

from __future__ import annotations

import argparse
import json
import webbrowser

from ...report.builder import build_report_data
from ...report.renderer import render_html
from ...runtime.workspace import latest_run, new_workspace
from ...shared.logging import get_logger
from ...shared.paths import run_dir

log = get_logger("qa_agent.report")


def run(args: argparse.Namespace) -> int:
    ws = latest_run(args.project)
    if ws is None:
        # No prior run — create a fresh workspace so the report still
        # has a place to live.
        ws = new_workspace(args.project)
    data = build_report_data(args.project)
    data_path = ws.root / "report-data.json"
    data_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    html_path = render_html(data, args.project, ws.run_id)

    log.info("report: data=%s", data_path)
    log.info("report: html=%s", html_path)
    if args.open_browser:
        webbrowser.open(html_path.as_uri())
    print(str(html_path))
    return 0
