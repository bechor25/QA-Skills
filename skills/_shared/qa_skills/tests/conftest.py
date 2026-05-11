"""Make `qa_skills` importable when pytest runs from any cwd."""

from __future__ import annotations

import sys
from pathlib import Path

_SHARED = Path(__file__).resolve().parent.parent.parent  # skills/_shared/
if str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))
