"""
datasets/manual_arrange/adapter.py

Wraps sort_manual_arrange_photos behind the common SortOutput envelope.
"""

from core.sort_result import SortOutput
from datasets.manual_arrange.sort import sort_manual_arrange_photos

MANUAL_ARRANGE_SHAPE = "manual_arrange_sequence"


def run(
    photos,
    pre_sort_buckets=None,
    allow_conflicting_tags=True,
):
    result = sort_manual_arrange_photos(
        photos,
        pre_sort_buckets=pre_sort_buckets,
        allow_conflicting_tags=allow_conflicting_tags,
    )

    return SortOutput(
        dataset_key="manual_arrange",
        shape=MANUAL_ARRANGE_SHAPE,
        structure=result.structure,
        issues=result.issues,
    )
