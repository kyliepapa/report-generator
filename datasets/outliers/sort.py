"""Build empty bucket scaffolding for an Outliers measure."""

from typing import Any, Dict, List

from core.outlier_extraction import build_outlier_buckets


def sort_outliers(outlier_sets: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "staging_items": [],
        "buckets": build_outlier_buckets(outlier_sets),
    }
