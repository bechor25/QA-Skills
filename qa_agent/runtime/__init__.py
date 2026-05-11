"""Runtime layer.

Process management, workspace isolation, and dependency installation.
Everything subprocess-related lives here so the rest of qa_agent stays
testable without spawning real processes.
"""
