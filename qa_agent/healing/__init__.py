"""Self-healing engine for failing tests.

- `engine`/`classifiers`/`policies`: deterministic pre-execution fixes.
- `cluster`: root-cause grouping for the post-run heal loop.
- `loop`: the heal loop stop predicate.
- `patcher`: snapshot / apply / revert with edit-scope gating.
"""

from . import cluster, loop, patcher

__all__ = ["cluster", "loop", "patcher"]
