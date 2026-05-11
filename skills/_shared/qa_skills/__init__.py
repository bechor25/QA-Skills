"""qa_skills — deterministic core for the QA-Skills plugin.

stdlib-only. Imported by orchestrator + sub-agents through `python -m qa_skills.<module>`
or `python skills/_shared/scripts/<name>.py`. No third-party deps so the plugin works
out of the box on a fresh `claude plugin install qa-skills`.

v1 supports typescript/javascript/python only.
"""

__version__ = "1.0.0"
