"""qa_skills — deterministic core for the QA-Skills plugin.

stdlib-only. Invoked by orchestrator + sub-agents through wrapper scripts at
`skills/_shared/scripts/*.py` — each wrapper does `sys.path.insert` and imports
the matching module here. `python -m qa_skills.<module>` does NOT work in the
target project without PYTHONPATH; always use the wrapper scripts. No
third-party deps so the plugin works out of the box on a fresh
`claude plugin install qa-skills`.

v1 supports typescript/javascript/python only.
"""

__version__ = "1.0.0"
