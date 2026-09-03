"""
datasets/heat_pump/sort.py

Sort Water Heaters / Heat Pumps photos into four buckets:
  BEFORE + serial, BEFORE, AFTER + serial, AFTER.

Optional multi-unit mode adds outer location buckets first.

Uses raw CompanyCam photo dicts (tag_names). Phase tags are fixed BEFORE/AFTER.
Serial tag is an exact tag match (same as Lighting).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from core.timezone import from_timestamp
from typing import Any, Dict, List, Optional, Set, Tuple

from core.constants import TECH_NAMES
from core.tag_parser import parse_serial_tags
from datasets.heat_pump.config import (
    ANCILLARY_FIXTURE_TAGS,
    PRIMARY_FIXTURE_TAGS,
    parse_heat_pump_location_config,
)
from datasets.lighting.sort import is_numeric_tag, numeric_sort_key

PHASE_BEFORE = "BEFORE"
PHASE_AFTER = "AFTER"
EXCLUDE_WATER_HEATER = "WATER HEATER"

BUCKET_DEFS = [
    ("before_serial", "BEFORE — SERIAL NUMBERS"),
    ("before", "BEFORE"),
    ("after_serial", "AFTER — SERIAL NUMBERS"),
    ("after", "AFTER"),
]


def _normalize_tag_static(value: Any) -> str:
    return str(value).strip().upper()


INTUITIVE_EXCLUDE_TAGS: Set[str] = {
    PHASE_BEFORE,
    PHASE_AFTER,
    EXCLUDE_WATER_HEATER,
    *[_normalize_tag_static(t) for t in TECH_NAMES],
}


@dataclass
class HeatPumpSortResult:
    structure: Dict[str, Any]
    issues: List[Dict[str, Any]] = field(default_factory=list)


def _normalize_tag(value: Any) -> str:
    return str(value).strip().upper()


def _get_tags(photo: Any) -> List[str]:
    if hasattr(photo, "tags"):
        return list(photo.tags)
    if isinstance(photo, dict):
        return photo.get("tag_names", photo.get("tags", []))
    return []


def _get_photo_id(photo: Any):
    if hasattr(photo, "photo_id"):
        return photo.photo_id
    if isinstance(photo, dict):
        return photo.get("photo_id") or photo.get("id")
    return None


def _photo_timestamp(photo: Any) -> datetime:
    raw = None
    if isinstance(photo, dict):
        raw = photo.get("created_at") or photo.get("captured_at")
    if isinstance(raw, (int, float)):
        return from_timestamp(raw)
    if isinstance(raw, str):
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except Exception:
            pass
    if isinstance(raw, datetime):
        return raw
    return datetime.min


def _record_issue(
    issues: List[Dict[str, Any]],
    photo: Any,
    level: str,
    issue_type: str,
    message: str,
    *,
    severity: str = "warning",
    resolved: bool = False,
    context: Optional[Dict[str, Any]] = None,
):
    issues.append({
        "photo_id": _get_photo_id(photo),
        "level": level,
        "issue_type": issue_type,
        "message": message,
        "tags": [_normalize_tag(t) for t in _get_tags(photo)],
        "severity": severity,
        "resolved": resolved,
        "context": context or {},
    })


def _classify_phase(
    tags: List[str],
    issues: List[Dict],
    photo: Any,
    *,
    serial_norms: Optional[List[str]] = None,
    auto_assign_lone_serial_to_before: bool = False,
) -> Optional[str]:
    serial_norms = serial_norms or []
    has_before = PHASE_BEFORE in tags
    has_after = PHASE_AFTER in tags
    if has_before and has_after:
        _record_issue(
            issues, photo, "Phase", "ambiguous_tag",
            "Photo contains both BEFORE and AFTER tags.",
        )
        return None
    if has_before:
        return PHASE_BEFORE
    if has_after:
        return PHASE_AFTER
    if auto_assign_lone_serial_to_before and serial_norms and any(s in tags for s in serial_norms):
        return PHASE_BEFORE
    _record_issue(
        issues, photo, "Phase", "missing_tag",
        "Photo has no BEFORE or AFTER tag.",
    )
    return None


def _classify_fixture(
    tags: List[str],
    fixtures: List[str],
    issues: List[Dict],
    photo: Any,
    *,
    allow_competing: bool = False,
) -> Optional[str]:
    fixture_set = set(fixtures)
    matches = [t for t in tags if t in fixture_set]
    unique = list(dict.fromkeys(matches))
    if len(unique) == 1:
        return unique[0]
    if len(unique) > 1:
        if allow_competing:
            for fixture in fixtures:
                if fixture in unique:
                    return fixture
        _record_issue(
            issues, photo, "Fixture", "ambiguous_tag",
            "Photo contains multiple competing fixture tags.",
            context={"matching_fixtures": unique},
        )
        return None
    return ""


def _bucket_key(phase: str, has_serial: bool) -> str:
    if phase == PHASE_BEFORE:
        return "before_serial" if has_serial else "before"
    return "after_serial" if has_serial else "after"


def _build_fixture_order(
    configured: List[str],
    assigned: List[Tuple[Any, str]],
) -> List[str]:
    """UI list order first; extras appended by first-seen timestamp."""
    order = list(configured)
    seen = set(order)
    extras: List[Tuple[datetime, str]] = []
    for photo, fixture in assigned:
        if fixture not in seen:
            extras.append((_photo_timestamp(photo), fixture))
            seen.add(fixture)
    extras.sort(key=lambda x: x[0])
    for _, name in extras:
        if name not in order:
            order.append(name)
    return order


def _photo_tags_norm(photo: Any) -> List[str]:
    return [_normalize_tag(t) for t in _get_tags(photo)]


def _intuitive_exclude_set(serial_norms: List[str]) -> Set[str]:
    return INTUITIVE_EXCLUDE_TAGS | set(serial_norms)


def _is_primary_tag(tag: str, primary_tags: List[str]) -> bool:
    return tag in primary_tags


def _is_ancillary_tag(tag: str, ancillary_set: Set[str]) -> bool:
    return tag in ancillary_set


def _eligible_remaining_tag(
    tag: str,
    exclude: Set[str],
    primary_set: Set[str],
    ancillary_set: Set[str],
) -> bool:
    return (
        tag not in exclude
        and tag not in primary_set
        and tag not in ancillary_set
    )


def _build_first_seen_order(
    photos: List[Any],
    tag_predicate,
) -> List[str]:
    """Append tags in timestamp order the first time each appears."""
    order: List[str] = []
    seen: Set[str] = set()
    sorted_photos = sorted(photos, key=_photo_timestamp)
    for photo in sorted_photos:
        tags = _photo_tags_norm(photo)
        for tag in tags:
            if tag_predicate(tag) and tag not in seen:
                order.append(tag)
                seen.add(tag)
    return order


def _build_ancillary_order(
    photos: List[Any],
    ancillary_set: Set[str],
) -> List[str]:
    return _build_first_seen_order(
        photos,
        lambda tag: _is_ancillary_tag(tag, ancillary_set),
    )


def _collect_eligible_tags(
    photos: List[Any],
    exclude: Set[str],
    primary_set: Set[str],
    ancillary_set: Set[str],
) -> Set[str]:
    tags: Set[str] = set()
    for photo in photos:
        for tag in _photo_tags_norm(photo):
            if _eligible_remaining_tag(tag, exclude, primary_set, ancillary_set):
                tags.add(tag)
    return tags


def _build_matched_order(
    before_photos: List[Any],
    after_photos: List[Any],
    exclude: Set[str],
    primary_set: Set[str],
    ancillary_set: Set[str],
) -> List[str]:
    before_tags = _collect_eligible_tags(
        before_photos, exclude, primary_set, ancillary_set,
    )
    after_tags = _collect_eligible_tags(
        after_photos, exclude, primary_set, ancillary_set,
    )
    matched_set = before_tags & after_tags
    if not matched_set:
        return []

    combined = before_photos + after_photos
    return _build_first_seen_order(
        combined,
        lambda tag: tag in matched_set,
    )


def _find_primary_match(tags: List[str], primary_tags: List[str]) -> Optional[Tuple[str, int]]:
    for index, primary in enumerate(primary_tags):
        if primary in tags:
            return primary, index
    return None


def _find_ordered_match(tags: List[str], order: List[str]) -> Optional[Tuple[str, int]]:
    for index, name in enumerate(order):
        if name in tags:
            return name, index
    return None


def _intuitive_sort_key(
    photo: Any,
    primary_tags: List[str],
    ancillary_order: List[str],
    matched_order: List[str],
) -> Tuple[int, int, datetime]:
    tags = _photo_tags_norm(photo)
    ts = _photo_timestamp(photo)

    primary_match = _find_primary_match(tags, primary_tags)
    if primary_match:
        _, index = primary_match
        return (0, index, ts)

    ancillary_match = _find_ordered_match(tags, ancillary_order)
    if ancillary_match:
        _, index = ancillary_match
        return (1, index, ts)

    matched_match = _find_ordered_match(tags, matched_order)
    if matched_match:
        _, index = matched_match
        return (2, index, ts)

    return (3, 0, ts)


def _fixture_for_intuitive_sort(
    photo: Any,
    primary_tags: List[str],
    ancillary_order: List[str],
    matched_order: List[str],
) -> str:
    tags = _photo_tags_norm(photo)
    primary_match = _find_primary_match(tags, primary_tags)
    if primary_match:
        return primary_match[0]
    ancillary_match = _find_ordered_match(tags, ancillary_order)
    if ancillary_match:
        return ancillary_match[0]
    matched_match = _find_ordered_match(tags, matched_order)
    if matched_match:
        return matched_match[0]
    return ""


def _sort_buckets_intuitive(
    buckets: Dict[str, List[Any]],
    serial_norms: List[str],
) -> List[str]:
    primary_tags = [_normalize_tag(t) for t in PRIMARY_FIXTURE_TAGS]
    ancillary_set = {_normalize_tag(t) for t in ANCILLARY_FIXTURE_TAGS}
    primary_set = set(primary_tags)
    exclude = _intuitive_exclude_set(serial_norms)

    before_photos = buckets.get("before", [])
    after_photos = buckets.get("after", [])
    combined = before_photos + after_photos

    ancillary_order = _build_ancillary_order(combined, ancillary_set)
    matched_order = _build_matched_order(
        before_photos,
        after_photos,
        exclude,
        primary_set,
        ancillary_set,
    )

    for key in ("before", "after"):
        photos = buckets.get(key, [])
        photos.sort(
            key=lambda p: _intuitive_sort_key(
                p, primary_tags, ancillary_order, matched_order,
            )
        )
        for photo in photos:
            photo["_fixture"] = _fixture_for_intuitive_sort(
                photo, primary_tags, ancillary_order, matched_order,
            )

    for key in ("before_serial", "after_serial"):
        buckets[key].sort(key=_photo_timestamp)

    return primary_tags + ancillary_order + matched_order


def _matching_numeric_tags_norm(tags: List[str]) -> List[str]:
    return [t for t in tags if is_numeric_tag(t)]


def _matching_explicit_locations(tags: List[str], explicit_locations: List[str]) -> List[str]:
    allowed = {_normalize_tag(v) for v in explicit_locations}
    matches = [t for t in tags if t in allowed]
    return list(dict.fromkeys(matches))


def _classify_location(
    photo: Any,
    lone_number_mode: str,
    explicit_locations: List[str],
    issues: List[Dict[str, Any]],
) -> Optional[str]:
    tags = [_normalize_tag(t) for t in _get_tags(photo)]
    explicit_matches = _matching_explicit_locations(tags, explicit_locations)
    numeric_matches = _matching_numeric_tags_norm(tags)

    if lone_number_mode == "all":
        if len(numeric_matches) == 1:
            return numeric_matches[0]
        if len(numeric_matches) > 1:
            _record_issue(
                issues, photo, "Location", "ambiguous_tag",
                "Photo contains multiple numeric location tags.",
                context={"numeric_tags": numeric_matches},
            )
        return None

    if lone_number_mode == "none":
        if len(explicit_matches) == 1:
            return explicit_matches[0]
        if len(explicit_matches) > 1:
            _record_issue(
                issues, photo, "Location", "ambiguous_tag",
                "Photo contains multiple competing location tags.",
                context={"matching_locations": explicit_matches},
            )
        return None

    # some: explicit takes precedence over numeric
    if len(explicit_matches) > 1:
        _record_issue(
            issues, photo, "Location", "ambiguous_tag",
            "Photo contains multiple competing location tags.",
            context={"matching_locations": explicit_matches},
        )
        return None
    if len(explicit_matches) == 1:
        return explicit_matches[0]

    if len(numeric_matches) == 1:
        return numeric_matches[0]
    if len(numeric_matches) > 1:
        _record_issue(
            issues, photo, "Location", "ambiguous_tag",
            "Photo contains multiple numeric location tags.",
            context={"numeric_tags": numeric_matches},
        )
    return None


def _discover_location_names(
    photos: List[Any],
    lone_number_mode: str,
    explicit_locations: List[str],
) -> List[str]:
    numeric_names: Set[str] = set()
    if lone_number_mode in ("some", "all"):
        for photo in photos:
            tags = [_normalize_tag(t) for t in _get_tags(photo)]
            for tag in _matching_numeric_tags_norm(tags):
                numeric_names.add(tag)

    explicit_names = [_normalize_tag(v) for v in explicit_locations]

    numeric_ordered = sorted(
        numeric_names,
        key=lambda name: numeric_sort_key(name),
    )
    text_ordered = [n for n in explicit_names if n not in numeric_names]
    return numeric_ordered + text_ordered


def _structure_from_buckets(
    buckets: Dict[str, List[Any]],
    untagged: List[Any],
    fixture_order: List[str],
) -> Dict[str, Any]:
    return {
        "buckets": [
            {"key": key, "label": label, "photos": buckets[key]}
            for key, label in BUCKET_DEFS
        ],
        "untagged": untagged,
        "fixture_order": fixture_order,
    }


def _sort_heat_pump_subset(
    photos: List[Any],
    fixtures_norm: List[str],
    serial_norms: List[str],
    issues: List[Dict[str, Any]],
    *,
    allow_competing_fixture_tags: bool = False,
    auto_assign_lone_serial_to_before: bool = False,
    intuitive_fixture_sort: bool = True,
) -> Dict[str, Any]:
    buckets: Dict[str, List[Any]] = {key: [] for key, _ in BUCKET_DEFS}
    untagged: List[Any] = []
    assigned: List[Tuple[Any, str]] = []

    use_intuitive = intuitive_fixture_sort
    classify_fixtures = not use_intuitive and fixtures_norm

    for photo in photos:
        tags = [_normalize_tag(t) for t in _get_tags(photo)]
        phase = _classify_phase(
            tags,
            issues,
            photo,
            serial_norms=serial_norms,
            auto_assign_lone_serial_to_before=auto_assign_lone_serial_to_before,
        )
        if phase is None:
            untagged.append(photo)
            continue

        if classify_fixtures:
            fixture = _classify_fixture(
                tags,
                fixtures_norm,
                issues,
                photo,
                allow_competing=allow_competing_fixture_tags,
            )
            if fixture is None:
                untagged.append(photo)
                continue
        else:
            fixture = ""

        has_serial = bool(serial_norms) and any(s in tags for s in serial_norms)
        key = _bucket_key(phase, has_serial)
        photo["_fixture"] = fixture
        buckets[key].append(photo)
        if fixture:
            assigned.append((photo, fixture))

    if use_intuitive:
        fixture_order = _sort_buckets_intuitive(buckets, serial_norms)
    else:
        fixture_order = _build_fixture_order(fixtures_norm, assigned)
        index_of = {name: i for i, name in enumerate(fixture_order)}
        for key in buckets:
            buckets[key].sort(
                key=lambda p: (
                    index_of.get(p.get("_fixture", ""), len(fixture_order)),
                    _photo_timestamp(p),
                )
            )

    return _structure_from_buckets(buckets, untagged, fixture_order)


def _build_location_buckets(
    photos: List[Any],
    location_config: dict,
    sort_kwargs: dict,
) -> Dict[str, Any]:
    issues: List[Dict[str, Any]] = sort_kwargs["issues"]
    lone_number_mode = location_config["lone_number_mode"]
    explicit_locations = location_config["locations"]

    location_names = _discover_location_names(
        photos, lone_number_mode, explicit_locations,
    )
    partitions: Dict[str, List[Any]] = {name: [] for name in location_names}
    top_untagged: List[Any] = []

    for photo in photos:
        loc = _classify_location(
            photo, lone_number_mode, explicit_locations, issues,
        )
        if loc is None or loc not in partitions:
            top_untagged.append(photo)
        else:
            partitions[loc].append(photo)

    locations = []
    for name in location_names:
        subset = partitions.get(name, [])
        if subset:
            subset_kwargs = dict(sort_kwargs)
            loc_structure = _sort_heat_pump_subset(subset, **subset_kwargs)
        else:
            loc_structure = _structure_from_buckets(
                {key: [] for key, _ in BUCKET_DEFS}, [], [],
            )
        locations.append({"name": name, **loc_structure})

    return {"locations": locations, "untagged": top_untagged}


def sort_heat_pump_photos(
    photos: List[Any],
    fixtures: List[str],
    serial_tag: str,
    *,
    allow_competing_fixture_tags: bool = False,
    auto_assign_lone_serial_to_before: bool = False,
    intuitive_fixture_sort: bool = True,
    multi_unit: bool = False,
    lone_number_mode: str = "none",
    locations=None,
) -> HeatPumpSortResult:
    issues: List[Dict[str, Any]] = []

    fixtures_norm = [_normalize_tag(f) for f in fixtures if str(f).strip()]
    serial_norms = [_normalize_tag(t) for t in parse_serial_tags(serial_tag)]
    location_config = parse_heat_pump_location_config(
        multi_unit, lone_number_mode, locations,
    )

    sort_kwargs = {
        "fixtures_norm": fixtures_norm,
        "serial_norms": serial_norms,
        "issues": issues,
        "allow_competing_fixture_tags": allow_competing_fixture_tags,
        "auto_assign_lone_serial_to_before": auto_assign_lone_serial_to_before,
        "intuitive_fixture_sort": intuitive_fixture_sort,
    }

    if location_config["multi_unit"]:
        structure = _build_location_buckets(photos, location_config, sort_kwargs)
        return HeatPumpSortResult(structure=structure, issues=issues)

    structure = _sort_heat_pump_subset(photos, **sort_kwargs)
    return HeatPumpSortResult(structure=structure, issues=issues)
