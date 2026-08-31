"""
datasets/manual_arrange/sort.py

Sort manual-arrange photos into an optional pre-sort staging layout:
  - staging_items: flat list (photos + optional headings later via edits)
  - buckets: labeled boxes for photos matching pre-sort bucket tags
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ManualArrangeSortResult:
    structure: Dict[str, Any]
    issues: List[Dict[str, Any]] = field(default_factory=list)


def _normalize_tag(value: Any) -> str:
    return str(value).strip().upper()


def _get_tags(photo: Any) -> list:
    if hasattr(photo, "tags"):
        return photo.tags
    if isinstance(photo, dict):
        return photo.get("tag_names", photo.get("tags", []))
    return []


def _get_photo_id(photo: Any):
    if hasattr(photo, "photo_id"):
        return photo.photo_id
    if isinstance(photo, dict):
        return photo.get("photo_id") or photo.get("id")
    return None


def _bucket_key(label: str) -> str:
    return _normalize_tag(label).replace(" ", "_")


def _classify_bucket(
    tags: List[str],
    bucket_labels: List[str],
    *,
    allow_conflicting: bool = True,
) -> Optional[str]:
    """Return bucket label or None for staging."""
    label_set = {_normalize_tag(b) for b in bucket_labels}
    matches = [t for t in tags if t in label_set]
    unique = list(dict.fromkeys(matches))

    if len(unique) == 0:
        return None
    if len(unique) == 1:
        for label in bucket_labels:
            if _normalize_tag(label) == unique[0]:
                return label
        return None
    if allow_conflicting:
        for label in bucket_labels:
            if _normalize_tag(label) in unique:
                return label
    return None


def sort_manual_arrange_photos(
    photos: List[Any],
    pre_sort_buckets: Optional[List[str]] = None,
    *,
    allow_conflicting_tags: bool = True,
) -> ManualArrangeSortResult:
    bucket_labels = [
        str(b).strip() for b in (pre_sort_buckets or []) if str(b).strip()
    ]

    staging_items: List[Dict[str, Any]] = []
    bucket_photos: Dict[str, List[Any]] = {label: [] for label in bucket_labels}
    issues: List[Dict[str, Any]] = []

    if not bucket_labels:
        for photo in photos:
            staging_items.append({"type": "photo", "photo": photo})
        return ManualArrangeSortResult(
            structure={"staging_items": staging_items},
            issues=issues,
        )

    for photo in photos:
        tags = [_normalize_tag(t) for t in _get_tags(photo)]
        assigned = _classify_bucket(
            tags,
            bucket_labels,
            allow_conflicting=allow_conflicting_tags,
        )
        if assigned is None:
            staging_items.append({"type": "photo", "photo": photo})
            if len([t for t in tags if t in {_normalize_tag(b) for b in bucket_labels}]) > 1:
                if not allow_conflicting_tags:
                    issues.append({
                        "type": "ambiguous_bucket_tag",
                        "photo_id": _get_photo_id(photo),
                        "tags": tags,
                    })
        else:
            bucket_photos[assigned].append(photo)

    buckets = [
        {
            "key": _bucket_key(label),
            "label": label,
            "photos": bucket_photos[label],
        }
        for label in bucket_labels
    ]

    return ManualArrangeSortResult(
        structure={
            "staging_items": staging_items,
            "buckets": buckets,
        },
        issues=issues,
    )
