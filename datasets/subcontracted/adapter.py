"""
datasets/subcontracted/adapter.py

Wraps sort_subcontracted_photos behind the common SortOutput envelope.
"""

from core.sort_result import SortOutput
from datasets.subcontracted.sort import sort_subcontracted_photos

SUBCONTRACTED_SHAPE = "subcontracted_sequence"


def run(photos, hash_char, measure_mark="", key_source="tags"):
    result = sort_subcontracted_photos(
        photos,
        hash_char=hash_char,
        measure_mark=measure_mark or "",
        key_source=key_source or "tags",
    )

    return SortOutput(
        dataset_key="subcontracted",
        shape=SUBCONTRACTED_SHAPE,
        structure=result.structure,
        issues=result.issues,
    )
