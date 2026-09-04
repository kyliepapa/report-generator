"""
Extract outlier photos from sorted measure structures and unknown list.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set

from core.measure_classification import _get_source_project_id, normalize_tag, normalize_tags

MANUAL_ARRANGE_SHAPE = "manual_arrange_sequence"
SUBCONTRACTED_SHAPE = "subcontracted_sequence"
HEAT_PUMP_SHAPE = "heat_pump_phase_serial_buckets"
LIGHTING_SHAPE = "location_sublocation_type_fixture_phase"


def _get_tags(photo: Any) -> List[str]:
    if hasattr(photo, "tags"):
        return list(photo.tags)
    if isinstance(photo, dict):
        return photo.get("tag_names", photo.get("tags", []))
    return []


def _get_photo_id(photo: Any) -> Optional[str]:
    if hasattr(photo, "photo_id"):
        return str(photo.photo_id) if photo.photo_id is not None else None
    if isinstance(photo, dict):
        raw = photo.get("photo_id") or photo.get("id")
        return str(raw) if raw is not None else None
    return None


def _bucket_key(label: str) -> str:
    return normalize_tag(label).replace(" ", "_")


def photo_matches_set(
    photo: Any,
    project_id: str,
    tags: List[str],
    tag_match_mode: str,
    *,
    single_project: bool = False,
) -> bool:
    if not single_project:
        if _get_source_project_id(photo) != str(project_id or "").strip():
            return False

    identifier_tags = normalize_tags(tags)
    if not identifier_tags:
        return False

    photo_tags = set(normalize_tags(_get_tags(photo)))
    if tag_match_mode == "all":
        return all(t in photo_tags for t in identifier_tags)
    return any(t in photo_tags for t in identifier_tags)


def _remove_from_photo_list(
    photos: List[Any],
    remove_ids: Set[str],
    removed: List[Any],
) -> List[Any]:
    kept: List[Any] = []
    for photo in photos:
        pid = _get_photo_id(photo)
        if pid and pid in remove_ids:
            removed.append(photo)
        else:
            kept.append(photo)
    return kept


def _remove_photos_recursive(node: Any, remove_ids: Set[str], removed: List[Any]) -> None:
    if node is None:
        return

    if isinstance(node, list):
        i = 0
        while i < len(node):
            item = node[i]
            if isinstance(item, dict) and item.get("type") == "photo" and "photo" in item:
                pid = _get_photo_id(item.get("photo"))
                if pid and pid in remove_ids:
                    removed.append(item["photo"])
                    node.pop(i)
                    continue
            if isinstance(item, (dict, list)):
                _remove_photos_recursive(item, remove_ids, removed)
            elif hasattr(item, "photo_id"):
                pid = _get_photo_id(item)
                if pid and pid in remove_ids:
                    removed.append(item)
                    node.pop(i)
                    continue
            elif isinstance(item, dict) and (_get_photo_id(item) or item.get("url")):
                pid = _get_photo_id(item)
                if pid and pid in remove_ids:
                    removed.append(item)
                    node.pop(i)
                    continue
            i += 1
        return

    if not isinstance(node, dict):
        return

    if "photos" in node and isinstance(node["photos"], list):
        node["photos"] = _remove_from_photo_list(node["photos"], remove_ids, removed)

    if "untagged" in node and isinstance(node["untagged"], list):
        node["untagged"] = _remove_from_photo_list(node["untagged"], remove_ids, removed)

    if "items" in node and isinstance(node["items"], list):
        new_items = []
        for item in node["items"]:
            if isinstance(item, dict) and item.get("type") == "photo" and "photo" in item:
                pid = _get_photo_id(item.get("photo"))
                if pid and pid in remove_ids:
                    removed.append(item["photo"])
                    continue
            new_items.append(item)
        node["items"] = new_items

    if "staging_items" in node and isinstance(node["staging_items"], list):
        new_staging = []
        for item in node["staging_items"]:
            if isinstance(item, dict) and item.get("type") == "photo" and "photo" in item:
                pid = _get_photo_id(item.get("photo"))
                if pid and pid in remove_ids:
                    removed.append(item["photo"])
                    continue
            new_staging.append(item)
        node["staging_items"] = new_staging

    if "buckets" in node and isinstance(node["buckets"], list):
        for bucket in node["buckets"]:
            if isinstance(bucket, dict) and isinstance(bucket.get("photos"), list):
                bucket["photos"] = _remove_from_photo_list(
                    bucket["photos"], remove_ids, removed
                )

    skip_keys = {"photos", "untagged", "items", "staging_items", "buckets"}
    for key, value in node.items():
        if key in skip_keys:
            continue
        if isinstance(value, dict):
            _remove_photos_recursive(value, remove_ids, removed)
        elif isinstance(value, list):
            if all(isinstance(x, dict) and not x.get("type") for x in value):
                for child in value:
                    _remove_photos_recursive(child, remove_ids, removed)
            elif key not in skip_keys:
                _remove_photos_recursive(value, remove_ids, removed)


def remove_photos_from_structure(
    structure: Any,
    shape: str,
    photo_ids: Set[str],
) -> List[Any]:
    removed: List[Any] = []
    if not structure or not photo_ids:
        return removed
    _remove_photos_recursive(structure, set(photo_ids), removed)
    return removed


def _iter_photos_in_structure(structure: Any):
    if structure is None:
        return
    if isinstance(structure, list):
        for item in structure:
            yield from _iter_photos_in_structure(item)
        return
    if isinstance(structure, dict):
        if structure.get("type") == "photo" and "photo" in structure:
            yield structure["photo"]
            return
        for key in ("photos", "untagged"):
            if key in structure and isinstance(structure[key], list):
                for photo in structure[key]:
                    yield photo
        if "items" in structure and isinstance(structure["items"], list):
            for item in structure["items"]:
                if isinstance(item, dict) and item.get("type") == "photo":
                    yield item.get("photo")
        if "staging_items" in structure and isinstance(structure["staging_items"], list):
            for item in structure["staging_items"]:
                if isinstance(item, dict) and item.get("type") == "photo":
                    yield item.get("photo")
        if "buckets" in structure and isinstance(structure["buckets"], list):
            for bucket in structure["buckets"]:
                if isinstance(bucket, dict):
                    yield from _iter_photos_in_structure(bucket)
        for key, value in structure.items():
            if key in ("photos", "untagged", "items", "staging_items", "buckets"):
                continue
            if isinstance(value, (dict, list)):
                yield from _iter_photos_in_structure(value)
        return
    if hasattr(structure, "photo_id"):
        yield structure


def _find_matching_in_structure(
    structure: Any,
    predicate: Callable[[Any], bool],
    already_claimed: Set[str],
) -> List[Any]:
    matches: List[Any] = []
    seen: Set[str] = set()
    for photo in _iter_photos_in_structure(structure):
        pid = _get_photo_id(photo)
        if not pid or pid in already_claimed or pid in seen:
            continue
        if predicate(photo):
            matches.append(photo)
            seen.add(pid)
    return matches


@dataclass
class ExtractionResult:
    structure: Dict[str, Any]
    issues: List[Dict[str, Any]] = field(default_factory=list)
    updated_unknown: List[Any] = field(default_factory=list)
    mutated_measure_ids: Set[str] = field(default_factory=set)


def build_outlier_buckets(outlier_sets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {
            "key": _bucket_key(str(raw_set.get("section_name") or "").strip()),
            "label": str(raw_set.get("section_name") or "").strip(),
            "photos": [],
        }
        for raw_set in outlier_sets
    ]


def extract_outliers(
    outlier_sets: List[Dict[str, Any]],
    sorted_measures: Dict[str, Dict[str, Any]],
    unknown_photos: List[Any],
    *,
    single_project: bool = False,
    outlier_measure_id: Optional[str] = None,
) -> ExtractionResult:
    issues: List[Dict[str, Any]] = []
    already_claimed: Set[str] = set()
    mutated_measure_ids: Set[str] = set()
    buckets = build_outlier_buckets(outlier_sets)
    unknown = list(unknown_photos)

    for set_idx, raw_set in enumerate(outlier_sets):
        if set_idx >= len(buckets):
            break

        project_id = str(raw_set.get("project_id") or "").strip()
        tags = raw_set.get("tags") or []
        tag_match_mode = str(raw_set.get("tag_match_mode") or "any").strip().lower()
        section_name = str(raw_set.get("section_name") or "").strip()

        def _predicate(photo: Any) -> bool:
            return photo_matches_set(
                photo,
                project_id,
                tags,
                tag_match_mode,
                single_project=single_project,
            )

        for measure_id, mdata in sorted_measures.items():
            if measure_id == outlier_measure_id:
                continue
            if mdata.get("type") == "outliers":
                continue

            structure = mdata.get("sorted_structure") or mdata.get("structure")
            shape = mdata.get("shape") or ""
            matches = _find_matching_in_structure(structure, _predicate, already_claimed)

            for photo in matches:
                pid = _get_photo_id(photo)
                if not pid:
                    continue
                if pid in already_claimed:
                    issues.append({
                        "type": "already_claimed",
                        "photo_id": pid,
                        "section_name": section_name,
                    })
                    continue

                remove_photos_from_structure(structure, shape, {pid})
                buckets[set_idx]["photos"].append(photo)
                already_claimed.add(pid)
                mutated_measure_ids.add(measure_id)

        new_unknown: List[Any] = []
        for photo in unknown:
            pid = _get_photo_id(photo)
            if not pid:
                new_unknown.append(photo)
                continue
            if pid in already_claimed:
                new_unknown.append(photo)
                continue
            if _predicate(photo):
                buckets[set_idx]["photos"].append(photo)
                already_claimed.add(pid)
            else:
                new_unknown.append(photo)
        unknown = new_unknown

    return ExtractionResult(
        structure={"staging_items": [], "buckets": buckets},
        issues=issues,
        updated_unknown=unknown,
        mutated_measure_ids=mutated_measure_ids,
    )
