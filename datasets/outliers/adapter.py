"""Wraps outlier bucket scaffolding behind the common SortOutput envelope."""

from core.sort_result import SortOutput
from datasets.manual_arrange.adapter import MANUAL_ARRANGE_SHAPE
from datasets.outliers.sort import sort_outliers


def run(outlier_sets=None, **kwargs):
    sets = outlier_sets or []
    return SortOutput(
        dataset_key="outliers",
        shape=MANUAL_ARRANGE_SHAPE,
        structure=sort_outliers(sets),
        issues=[],
    )
