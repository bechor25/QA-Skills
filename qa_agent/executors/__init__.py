"""Per-framework test executors.

Each executor consumes a list of test files + the project root and runs
them via the runtime/process_manager. Results are returned as
`ExecutionRecord` ready to append to execution_history.json.
"""

from .base import Executor, ExecutionResult  # noqa: F401
