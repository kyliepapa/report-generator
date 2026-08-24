"""
datasets/subcontracted/sort.py

Sort subcontracted-measure photos by parsing a subcon key per photo:
  hash (1 char) + optional measure mark (1 letter) + order key (trailing digits).

The key may come from a photo tag or the photo description (per measure config).
Photos missing an order key are appended at the bottom and reported as issues.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class SubcontractSortResult:
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


def _get_description(photo: Any) -> str:
    if isinstance(photo, dict):
        raw = photo["description"]["plain_text_content"]
        return str(raw).strip()
    else:
        return str(getattr(photo, "description", "") or "").strip()


def _build_prefix(hash_char: str, measure_mark: str) -> str:
    prefix = hash_char.upper()
    if measure_mark:
        prefix += measure_mark.upper()
    return prefix


def _parse_tag(tag: str, hash_char: str, measure_mark: str) -> Tuple[Optional[int], bool]:
    """
    Returns (order_key, valid).
    valid=False when the tag matches the prefix but has extra chars between
    mark and order key (e.g. !AB5 when mark=A).
    """
    norm = _normalize_tag(tag)
    prefix = _build_prefix(hash_char, measure_mark)
    if not norm.startswith(prefix):
        return None, True

    remainder = norm[len(prefix):]
    if not remainder:
        return None, True

    match = re.search(r"\d+$", remainder)
    if not match:
        return None, True

    middle = remainder[: match.start()]
    if middle:
        return None, False

    return int(match.group()), True


def _subcon_key_matches(key: str, hash_char: str, measure_mark: str) -> bool:
    norm = _normalize_tag(key)
    if not norm or norm[0] != hash_char.upper():
        return False
    if measure_mark:
        return norm.startswith(_build_prefix(hash_char, measure_mark))
    return bool(re.match(r"^" + re.escape(hash_char.upper()) + r"\d+$", norm))


def _tag_matches_subcontract(tag: str, hash_char: str, measure_mark: str) -> bool:
    return _subcon_key_matches(tag, hash_char, measure_mark)


def _find_matching_tag(photo: Any, hash_char: str, measure_mark: str) -> Optional[str]:
    for raw in _get_tags(photo):
        if _subcon_key_matches(raw, hash_char, measure_mark):
            return _normalize_tag(raw)
    return None


def _find_subcon_key(
    photo: Any,
    hash_char: str,
    measure_mark: str,
    key_source: str = "tags",
) -> Optional[str]:
    if (key_source or "tags").lower() == "description":
        key = _normalize_tag(_get_description(photo))
        if key and _subcon_key_matches(key, hash_char, measure_mark):
            return key
        return None
    return _find_matching_tag(photo, hash_char, measure_mark)


def sort_subcontracted_photos(
    photos: List[Any],
    hash_char: str,
    measure_mark: str = "",
    key_source: str = "tags",
) -> SubcontractSortResult:
    hash_char = (hash_char or "").strip()
    measure_mark = (measure_mark or "").strip()
    key_source = (key_source or "tags").strip().lower()

    if len(hash_char) != 1:
        raise ValueError("Subcontracted measure requires a single-character hash.")

    with_key: List[Tuple[int, Any, str]] = []
    without_key: List[Tuple[Any, str]] = []
    issues: List[Dict[str, Any]] = []

    for photo in photos:
        matched_key = _find_subcon_key(photo, hash_char, measure_mark, key_source)
        photo_id = _get_photo_id(photo)

        if not matched_key:
            without_key.append((photo, ""))
            issues.append({
                "type": "no_matching_key",
                "photo_id": photo_id,
                "tag": "",
                "key_source": key_source,
            })
            continue

        order_key, valid = _parse_tag(matched_key, hash_char, measure_mark)
        if not valid:
            without_key.append((photo, matched_key))
            issues.append({
                "type": "invalid_tag_format",
                "photo_id": photo_id,
                "tag": matched_key,
            })
            continue

        if order_key is None:
            without_key.append((photo, matched_key))
            issues.append({
                "type": "missing_order_key",
                "photo_id": photo_id,
                "tag": matched_key,
            })
            continue

        with_key.append((order_key, photo, matched_key))

    with_key.sort(key=lambda t: t[0])

    items: List[Dict[str, Any]] = []
    for order_key, photo, source_tag in with_key:
        items.append({
            "type": "photo",
            "photo": photo,
            "order_key": order_key,
            "source_tag": source_tag,
        })
    for photo, source_tag in without_key:
        items.append({
            "type": "photo",
            "photo": photo,
            "order_key": None,
            "source_tag": source_tag,
        })

    return SubcontractSortResult(
        structure={"items": items},
        issues=issues,
    )
