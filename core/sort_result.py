"""
core/sort_result.py

Normalized envelope every dataset's sort entry point returns, via
core.dataset_router.run_sort(). Plumbing's structure is still the old
nested dict (shape = one of the 4 SORT_METHOD_KEY strings); water
meter and lighting have their own shapes since they don't share
plumbing's bldg/unit/sub-unit/phase decomposition. `shape` exists so
a future report-writer knows which shape it's looking at without
depending on dataset_key naming.

This does NOT replace DatasetConfig (datasets/base.py) -- that's
still how plumbing's own bldg/unit/sub-unit/phase pipeline configures
itself. This is one level up: a common wrapper around "whatever a
dataset's algorithm returns" so callers (app.py routes, eventually
report generators) have one shape to import instead of three.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class SortOutput:
    dataset_key: str
    shape: str
    structure: Any
    untagged: List[Any] = field(default_factory=list)
    special: Dict[str, Any] = field(default_factory=dict)
    issues: List[Dict[str, Any]] = field(default_factory=list)