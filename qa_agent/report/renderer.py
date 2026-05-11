"""HTML renderer — single-file output via Jinja2."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from ..shared.errors import ReportError
from ..shared.paths import reports_template_dir, run_dir


def render_html(
    data: dict[str, Any],
    project: str | None,
    run_id: str,
    template_name: str = "enterprise.html.j2",
) -> Path:
    """Render the report HTML to `<project>/.qa-agent/runs/<run_id>/report.html`.
    Returns the path.
    """
    tpl_dir = reports_template_dir()
    if not (tpl_dir / template_name).exists():
        raise ReportError(f"report template missing: {tpl_dir / template_name}")
    env = Environment(
        loader=FileSystemLoader(str(tpl_dir)),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template(template_name)
    html = template.render(data=data)
    out = run_dir(project, run_id) / "report.html"
    out.write_text(html, encoding="utf-8")
    return out
