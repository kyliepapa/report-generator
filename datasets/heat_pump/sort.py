"""
datasets/heat_pump/sort.py

Sort Single-Unit Heat Pump photos into four buckets:
  BEFORE + serial, BEFORE, AFTER + serial, AFTER.

Uses raw CompanyCam photo dicts (tag_names). Phase tags are fixed BEFORE/AFTER.
Serial tag is an exact tag match (same as Lighting).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from core.tag_parser import parse_serial_tags

PHASE_BEFORE = "BEFORE"
PHASE_AFTER = "AFTER"

BUCKET_DEFS = [
    ("before_serial", "BEFORE — SERIAL NUMBERS"),
    ("before", "BEFORE"),
    ("after_serial", "AFTER — SERIAL NUMBERS"),
    ("after", "AFTER"),
]


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
        return datetime.fromtimestamp(raw)
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


def sort_heat_pump_photos(
    photos: List[Any],
    fixtures: List[str],
    serial_tag: str,
    *,
    allow_competing_fixture_tags: bool = False,
    auto_assign_lone_serial_to_before: bool = False,
) -> HeatPumpSortResult:
    issues: List[Dict[str, Any]] = []

    fixtures_norm = [_normalize_tag(f) for f in fixtures if str(f).strip()]
    serial_norms = [_normalize_tag(t) for t in parse_serial_tags(serial_tag)]

    buckets: Dict[str, List[Any]] = {key: [] for key, _ in BUCKET_DEFS}
    untagged: List[Any] = []
    assigned: List[Tuple[Any, str]] = []

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

        if fixtures_norm:
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

    fixture_order = _build_fixture_order(fixtures_norm, assigned)
    index_of = {name: i for i, name in enumerate(fixture_order)}

    for key in buckets:
        buckets[key].sort(
            key=lambda p: (
                index_of.get(p.get("_fixture", ""), len(fixture_order)),
                _photo_timestamp(p),
            )
        )

    structure = {
        "buckets": [
            {"key": key, "label": label, "photos": buckets[key]}
            for key, label in BUCKET_DEFS
        ],
        "untagged": untagged,
        "fixture_order": fixture_order,
    }

    return HeatPumpSortResult(structure=structure, issues=issues)
