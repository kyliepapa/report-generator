"""
datasets/lighting/sort.py

Your lighting draft, relocated unchanged. Uses its own Photo
dataclass (.tags, .timestamp) rather than the raw tag_names dicts
plumbing/water meter use -- normalizing that is the adapter's job
(adapter.py), not this file's.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from core.tag_parser import parse_serial_tags


# ============================================================
# DATA TYPES
# ============================================================

@dataclass
class Photo:
    """
    Represents an installation photo.

    photo_id should be unique within the photo set.
    """
    photo_id: str
    tags: list[str]
    timestamp: datetime
    data: Any = None


@dataclass
class Issue:
    """
    A diagnostic generated while sorting a photo.

    severity:
        "info", "warning", or "error"

    resolved:
        True if the algorithm encountered an issue but was
        ultimately able to place the photo deterministically.
    """
    photo_id: str
    level: str
    issue_type: str
    message: str
    tags: list[str] = field(default_factory=list)
    severity: str = "warning"
    resolved: bool = False
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class SortResult:
    """
    Returned by sort_lighting_photos().
    """
    structure: dict[str, Any]
    issues: list[Issue]


# ============================================================
# CONSTANTS / HELPERS
# ============================================================

UNTAGGED = "Untagged"


def _normalize_tag(value: Any) -> str:
    return str(value).strip().upper()


def _normalize_tag_list(values: list[str]) -> list[str]:
    return [_normalize_tag(v) for v in values if str(v).strip()]


def _normalize_photos(photos: list[Photo]) -> list[Photo]:
    return [
        Photo(
            photo_id=photo.photo_id,
            tags=_normalize_tag_list(photo.tags),
            timestamp=photo.timestamp,
            data=photo.data,
        )
        for photo in photos
    ]


def _normalize_location_levels(location_levels: list[dict]) -> list[dict]:
    return [
        {
            "tags": _normalize_tag_list(level.get("tags") or []),
            "numeric": bool(level.get("numeric")),
        }
        for level in location_levels
    ]


def _normalize_serial_tag(serial_tag: str) -> str:
    tags = [_normalize_tag(t) for t in parse_serial_tags(serial_tag)]
    return ",".join(tags)


def is_numeric_tag(tag: str) -> bool:
    """
    Returns True if the tag can be interpreted as a number.

    Supports integer and decimal representations.
    """
    try:
        float(tag)
        return True
    except (ValueError, TypeError):
        return False


def numeric_value(tag: str) -> float:
    return float(tag)


def numeric_sort_key(value: str):
    """
    Sort numeric bucket names numerically.
    """
    try:
        return float(value)
    except (ValueError, TypeError):
        return float("inf")


def matching_explicit_values(
    photo: Photo,
    allowed_values: list[str],
) -> list[str]:
    """
    Return all configured values appearing in the photo's tags.
    """
    allowed = set(allowed_values)
    return [tag for tag in photo.tags if tag in allowed]


def matching_numeric_tags(photo: Photo) -> list[str]:
    """
    Return all numeric tags on a photo.
    """
    return [tag for tag in photo.tags if is_numeric_tag(tag)]


def record_issue(
    issues: list[Issue],
    photo: Photo,
    level: str,
    issue_type: str,
    message: str,
    *,
    severity: str = "warning",
    resolved: bool = False,
    context: Optional[dict[str, Any]] = None,
):
    issues.append(
        Issue(
            photo_id=photo.photo_id,
            level=level,
            issue_type=issue_type,
            message=message,
            tags=list(photo.tags),
            severity=severity,
            resolved=resolved,
            context=context or {},
        )
    )


# ============================================================
# TAG CLASSIFICATION
# ============================================================

def classify_explicit_tag(
    photo: Photo,
    allowed_values: list[str],
) -> tuple[Optional[str], bool]:
    """
    Returns:

        (matched_value, ambiguous)

    Explicit tags have no ambiguity if exactly one configured
    value is present.

    If multiple configured values appear, the classification
    is ambiguous and returns (None, True).
    """
    matches = matching_explicit_values(photo, allowed_values)

    # Remove duplicates while preserving order.
    unique_matches = list(dict.fromkeys(matches))

    if len(unique_matches) == 1:
        return unique_matches[0], False

    if len(unique_matches) > 1:
        return None, True

    return None, False


# ============================================================
# LOCATION LEVEL CLASSIFICATION (1–5 levels)
# ============================================================

def _level_label(level_index: int) -> str:
    return f"Location Level {level_index + 1}"


def map_numeric_tags_to_levels(
    photo: Photo,
    location_levels: list[dict],
    loc_bigger_num: bool,
    issues: list[Issue],
) -> Optional[dict[int, str]]:
    """
    Assign numeric tags to numeric location levels for one photo.
    Returns None when too many numeric tags are present.
    """
    numeric_indices = [
        i for i, level in enumerate(location_levels) if level.get("numeric")
    ]
    if not numeric_indices:
        return {}

    tags = list(dict.fromkeys(matching_numeric_tags(photo)))
    needed = len(numeric_indices)

    if len(tags) > needed:
        record_issue(
            issues,
            photo,
            "Location",
            "ambiguous_tag",
            f"Photo contains {len(tags)} numeric tags but only "
            f"{needed} numeric location level(s) are configured.",
            context={"numeric_tags": tags},
        )
        return None

    if len(tags) < needed:
        return {}

    sorted_tags = sorted(tags, key=numeric_value)
    if loc_bigger_num:
        sorted_tags = list(reversed(sorted_tags))

    return {
        numeric_indices[i]: sorted_tags[i]
        for i in range(needed)
    }


def determine_level_name(
    photo: Photo,
    level_index: int,
    location_levels: list[dict],
    loc_bigger_num: bool,
    issues: list[Issue],
    numeric_map: Optional[dict[int, str]] = None,
) -> Optional[str]:
    """
    Resolve the bucket name for one photo at a given location level.
    """
    if level_index >= len(location_levels):
        return None

    level_cfg = location_levels[level_index]
    allowed_tags = level_cfg.get("tags") or []
    level_numeric = bool(level_cfg.get("numeric"))
    label = _level_label(level_index)

    explicit, ambiguous = classify_explicit_tag(photo, allowed_tags)

    if ambiguous:
        record_issue(
            issues,
            photo,
            label,
            "ambiguous_tag",
            f"Photo contains multiple competing {label} tags.",
        )
        return None

    if explicit is not None:
        return explicit

    if not level_numeric:
        return None

    if numeric_map is None:
        numeric_map = map_numeric_tags_to_levels(
            photo, location_levels, loc_bigger_num, issues
        )

    if numeric_map is None:
        return None

    if level_index in numeric_map:
        return numeric_map[level_index]

    numeric_indices = [
        i for i, level in enumerate(location_levels) if level.get("numeric")
    ]
    if level_index in numeric_indices:
        record_issue(
            issues,
            photo,
            label,
            "missing_tag",
            f"Photo does not contain enough numeric tags for {label}.",
        )

    return None


def classify_top_level(
    photos: list[Photo],
    location_levels: list[dict],
    loc_bigger_num: bool,
    issues: list[Issue],
) -> tuple[dict[str, list[Photo]], list[Photo]]:
    """Classify photos into level-1 location buckets."""
    if not location_levels:
        return {}, list(photos)

    groups: dict[str, list[Photo]] = {}
    untagged: list[Photo] = []

    for photo in photos:
        numeric_map = map_numeric_tags_to_levels(
            photo, location_levels, loc_bigger_num, issues
        )
        if numeric_map is None:
            untagged.append(photo)
            continue

        name = determine_level_name(
            photo,
            0,
            location_levels,
            loc_bigger_num,
            issues,
            numeric_map=numeric_map,
        )

        if name is None:
            record_issue(
                issues,
                photo,
                _level_label(0),
                "missing_tag",
                "Photo could not be assigned to Location Level 1 "
                "and was placed in the top-level Untagged bucket.",
            )
            untagged.append(photo)
            continue

        groups.setdefault(name, []).append(photo)

    return groups, untagged


def process_child_levels(
    parent_group: dict[str, Any],
    level_index: int,
    location_levels: list[dict],
    fixture_types: list[str],
    installers: list[str],
    phases: list[str],
    serial_tag: str,
    loc_bigger_num: bool,
    issues: list[Issue],
):
    """
    Process optional location levels 2–5 under a parent bucket.
    Unmatched photos remain at the parent and continue down the tree.
    """
    photos = parent_group.pop("_photos")

    if level_index >= len(location_levels):
        parent_group["_photos"] = photos
        process_type_level(
            parent_group,
            fixture_types,
            installers,
            phases,
            serial_tag,
            issues,
        )
        return

    level_cfg = location_levels[level_index]
    if not (level_cfg.get("tags") or level_cfg.get("numeric")):
        parent_group["_photos"] = photos
        process_child_levels(
            parent_group,
            level_index + 1,
            location_levels,
            fixture_types,
            installers,
            phases,
            serial_tag,
            loc_bigger_num,
            issues,
        )
        return

    child_groups: dict[str, list[Photo]] = {}
    unmatched: list[Photo] = []

    for photo in photos:
        numeric_map = map_numeric_tags_to_levels(
            photo, location_levels, loc_bigger_num, issues
        )
        if numeric_map is None:
            unmatched.append(photo)
            continue

        name = determine_level_name(
            photo,
            level_index,
            location_levels,
            loc_bigger_num,
            issues,
            numeric_map=numeric_map,
        )
        if name is None:
            unmatched.append(photo)
        else:
            child_groups.setdefault(name, []).append(photo)

    if not child_groups:
        parent_group["_photos"] = photos
        if level_index + 1 >= len(location_levels):
            process_type_level(
                parent_group,
                fixture_types,
                installers,
                phases,
                serial_tag,
                issues,
            )
        else:
            process_child_levels(
                parent_group,
                level_index + 1,
                location_levels,
                fixture_types,
                installers,
                phases,
                serial_tag,
                loc_bigger_num,
                issues,
            )
        return

    parent_group.setdefault("sublocations", [])

    for child_name, child_photos in child_groups.items():
        child_group = {
            "name": child_name,
            "_photos": child_photos,
        }
        if level_index + 1 >= len(location_levels):
            process_type_level(
                child_group,
                fixture_types,
                installers,
                phases,
                serial_tag,
                issues,
            )
        else:
            process_child_levels(
                child_group,
                level_index + 1,
                location_levels,
                fixture_types,
                installers,
                phases,
                serial_tag,
                loc_bigger_num,
                issues,
            )
        parent_group["sublocations"].append(child_group)

    if unmatched:
        parent_group["_photos"] = unmatched
        if level_index + 1 >= len(location_levels):
            process_type_level(
                parent_group,
                fixture_types,
                installers,
                phases,
                serial_tag,
                issues,
            )
        else:
            process_child_levels(
                parent_group,
                level_index + 1,
                location_levels,
                fixture_types,
                installers,
                phases,
                serial_tag,
                loc_bigger_num,
                issues,
            )


# ============================================================
# TYPE CLASSIFICATION
# ============================================================

def classify_types(
    photos: list[Photo],
    fixture_types: list[str],
    issues: list[Issue],
) -> tuple[dict[str, list[Photo]], list[Photo]]:
    """
    Returns:

        type_groups
        untagged_photos
    """

    type_groups: dict[str, list[Photo]] = {}
    untagged: list[Photo] = []

    for photo in photos:

        fixture_type, ambiguous = classify_explicit_tag(
            photo,
            fixture_types,
        )

        if ambiguous:
            record_issue(
                issues,
                photo,
                "Type",
                "ambiguous_tag",
                "Photo contains multiple competing Type tags.",
            )
            untagged.append(photo)
            continue

        if fixture_type is None:
            record_issue(
                issues,
                photo,
                "Type",
                "missing_tag",
                "Photo has no valid Type tag.",
            )
            untagged.append(photo)
            continue

        type_groups.setdefault(fixture_type, []).append(photo)

    return type_groups, untagged


# ============================================================
# INSTALLER CLASSIFICATION
# ============================================================

def classify_installers(
    photos: list[Photo],
    installers: list[str],
    issues: list[Issue],
) -> tuple[dict[str, list[Photo]], list[Photo]]:
    """
    Returns:

        installer_groups
        unresolved_installer_photos
    """

    groups: dict[str, list[Photo]] = {}
    unassigned: list[Photo] = []

    for photo in photos:

        installer, ambiguous = classify_explicit_tag(
            photo,
            installers,
        )

        if ambiguous:
            record_issue(
                issues,
                photo,
                "Installer",
                "ambiguous_tag",
                "Photo contains multiple competing Installer tags.",
            )
            unassigned.append(photo)
            continue

        if installer is None:
            record_issue(
                issues,
                photo,
                "Installer",
                "missing_tag",
                "Photo has no valid Installer tag.",
            )
            unassigned.append(photo)
            continue

        groups.setdefault(installer, []).append(photo)

    return groups, unassigned


# ============================================================
# PHASE CLASSIFICATION
# ============================================================

def classify_phases(
    photos: list[Photo],
    phases: list[str],
    issues: list[Issue],
) -> tuple[dict[str, list[Photo]], list[Photo]]:
    """
    Classify photos into unambiguous Phase groups.

    A photo with:
        0 matching phases -> unresolved
        1 matching phase  -> valid
        >1 matching phases -> ambiguous/unresolved
    """

    phase_groups: dict[str, list[Photo]] = {
        phase: [] for phase in phases
    }

    unresolved: list[Photo] = []

    for photo in photos:

        matches = matching_explicit_values(photo, phases)
        matches = list(dict.fromkeys(matches))

        if len(matches) == 1:

            phase_groups[matches[0]].append(photo)

        elif len(matches) == 0:

            record_issue(
                issues,
                photo,
                "Phase",
                "missing_tag",
                "Photo has no valid Phase tag.",
            )

            unresolved.append(photo)

        else:

            record_issue(
                issues,
                photo,
                "Phase",
                "ambiguous_tag",
                "Photo contains multiple competing Phase tags.",
                context={"matching_phases": matches},
            )

            unresolved.append(photo)

    return phase_groups, unresolved


# ============================================================
# FIXTURE RECONSTRUCTION
# ============================================================

def build_fixtures_from_phases(
    phase_groups: dict[str, list[Photo]],
    phases: list[str],
) -> list[dict[str, Any]]:
    """
    Build Fixture buckets from all photos with valid Phase tags.

    Number of Fixtures = maximum number of photos in any Phase.
    """

    max_repetition = max(
        (len(phase_groups[phase]) for phase in phases),
        default=0,
    )

    if max_repetition == 0:
        return []

    fixtures = []

    for i in range(max_repetition):
        fixtures.append(
            {
                "name": f"Fixture {i + 1}",
                "photos": [],
                "phase_photos": {},
            }
        )

    # --------------------------------------------------------
    # Assign phase-by-phase, oldest to newest.
    # --------------------------------------------------------

    for phase in phases:

        photos = sorted(
            phase_groups[phase],
            key=lambda p: p.timestamp,
        )

        for index, photo in enumerate(photos):

            fixture = fixtures[index]

            fixture["phase_photos"][phase] = photo
            fixture["photos"].append(photo)

    # --------------------------------------------------------
    # Order each Fixture according to phases.
    # --------------------------------------------------------

    for fixture in fixtures:

        ordered = []

        for phase in phases:
            photo = fixture["phase_photos"].get(phase)

            if photo is not None:
                ordered.append(photo)

        fixture["photos"] = ordered

    return fixtures


def find_open_phase_slots(
    fixtures: list[dict[str, Any]],
    phases: list[str],
) -> list[tuple[int, str]]:
    """
    Return every missing Fixture/Phase slot.

    Each result is:
        (fixture_index, phase)
    """

    open_slots = []

    for fixture_index, fixture in enumerate(fixtures):

        for phase in phases:

            if phase not in fixture["phase_photos"]:
                open_slots.append(
                    (fixture_index, phase)
                )

    return open_slots


def recover_unresolved_photos(
    fixtures: list[dict[str, Any]],
    unresolved_photos: list[Photo],
    phases: list[str],
    type_untagged: list[Photo],
    issues: list[Issue],
):
    """
    Apply the agreed unresolved-photo recovery rules.

    1. If exactly one open Fixture/Phase slot exists,
       fill it.

    2. Otherwise, if only one Fixture exists, append the
       unresolved photo to that Fixture.

    3. Otherwise, put it in Type/Untagged.
    """

    for photo in unresolved_photos:

        open_slots = find_open_phase_slots(
            fixtures,
            phases,
        )

        # ----------------------------------------------------
        # Exactly one open slot
        # ----------------------------------------------------

        if len(open_slots) == 1:

            fixture_index, phase = open_slots[0]
            fixture = fixtures[fixture_index]

            fixture["phase_photos"][phase] = photo

            # Rebuild the Fixture's final photo ordering.
            fixture["photos"] = [
                fixture["phase_photos"][p]
                for p in phases
                if p in fixture["phase_photos"]
            ]

            record_issue(
                issues,
                photo,
                "Phase",
                "recovered_missing_phase",
                (
                    f"Photo was assigned to the only open "
                    f"Fixture/Phase slot: Fixture "
                    f"{fixture_index + 1} / {phase}."
                ),
                severity="info",
                resolved=True,
                context={
                    "fixture": fixture_index + 1,
                    "phase": phase,
                },
            )

            continue

        # ----------------------------------------------------
        # Exactly one Fixture
        # ----------------------------------------------------

        if len(fixtures) == 1:

            fixture = fixtures[0]

            fixture["photos"].append(photo)
            fixture.setdefault("unphased", []).append(photo)

            record_issue(
                issues,
                photo,
                "Phase",
                "unresolved_phase_recovered",
                (
                    "Photo could not be assigned to a Phase, "
                    "but the Installer group produced only one "
                    "Fixture, so it was appended to that Fixture."
                ),
                severity="info",
                resolved=True,
                context={
                    "fixture": 1,
                },
            )

            continue

        # ----------------------------------------------------
        # Multiple Fixtures + no unique slot
        # ----------------------------------------------------

        type_untagged.append(photo)

        record_issue(
            issues,
            photo,
            "Fixture",
            "unresolved_fixture",
            (
                "Photo could not be uniquely assigned to a "
                "Fixture because multiple Fixtures exist and "
                "there is not exactly one open Fixture/Phase slot."
            ),
            context={
                "fixture_count": len(fixtures),
                "open_slots": [
                    {
                        "fixture": i + 1,
                        "phase": phase,
                    }
                    for i, phase in open_slots
                ],
            },
        )


# ============================================================
# INSTALLER → FIXTURE PROCESSING
# ============================================================

def process_installer_group(
    installer_name: str,
    photos: list[Photo],
    phases: list[str],
    type_group: dict[str, Any],
    issues: list[Issue],
):
    """
    Convert one temporary Installer bucket into permanent
    Fixture buckets.
    """

    phase_groups, unresolved_photos = classify_phases(
        photos,
        phases,
        issues,
    )

    fixtures = build_fixtures_from_phases(
        phase_groups,
        phases,
    )

    # --------------------------------------------------------
    # No usable phase information
    # --------------------------------------------------------

    if not fixtures:

        if len(photos) == 1:

            photo = photos[0]

            fixture = {
                "name": "Fixture 1",
                "photos": [photo],
                "unphased": [photo],
            }

            type_group["fixtures"].append(fixture)

            record_issue(
                issues,
                photo,
                "Fixture",
                "unresolved_phase_recovered",
                (
                    "No valid Phase information was available, "
                    "but the Installer group contains only one "
                    "photo, so it was placed into a single Fixture."
                ),
                severity="info",
                resolved=True,
            )

            return

        for photo in unresolved_photos:

            type_group["untagged"].append(photo)

            record_issue(
                issues,
                photo,
                "Fixture",
                "unresolved_fixture",
                (
                    "No valid Phase information was available "
                    "and the Installer group could not be reduced "
                    "to a single determinable Fixture."
                ),
            )

        return

    # --------------------------------------------------------
    # Recover unresolved photos
    # --------------------------------------------------------

    recover_unresolved_photos(
        fixtures,
        unresolved_photos,
        phases,
        type_group["untagged"],
        issues,
    )

    # --------------------------------------------------------
    # Convert temporary Fixtures into final Fixtures
    # --------------------------------------------------------

    for fixture in fixtures:

        type_group["fixtures"].append(
            {
                "name": fixture["name"],
                "photos": fixture["photos"],
                "phase_photos": fixture["phase_photos"],
                "unphased": fixture.get("unphased", []),
            }
        )


# ============================================================
# TYPE → FIXTURE PROCESSING
# ============================================================

def process_type_group(
    type_name: str,
    photos: list[Photo],
    installers: list[str],
    phases: list[str],
    serial_tag: str,
    issues: list[Issue],
) -> dict[str, Any]:
    """
    Process all photos belonging to one Type.
    """

    type_group = {
        "name": type_name,
        "fixtures": [],
        "untagged": [],
    }

    serial_photos: list[Photo] = []
    non_serial_photos: list[Photo] = []

    # --------------------------------------------------------
    # Serial-tagged photos
    # --------------------------------------------------------

    serial_tags = parse_serial_tags(serial_tag)

    for photo in photos:

        if serial_tags and any(t in photo.tags for t in serial_tags):
            serial_photos.append(photo)
        else:
            non_serial_photos.append(photo)

    if serial_photos:

        type_group["fixtures"].append(
            {
                "name": "Serial-Tagged Fixture",
                "photos": serial_photos,
            }
        )

    # --------------------------------------------------------
    # Installer grouping
    # --------------------------------------------------------

    installer_groups, unresolved_installers = classify_installers(
        non_serial_photos,
        installers,
        issues,
    )

    # Photos without a usable Installer cannot participate
    # in Installer/Phase reconstruction.
    for photo in unresolved_installers:

        type_group["untagged"].append(photo)

        record_issue(
            issues,
            photo,
            "Fixture",
            "unresolved_fixture",
            (
                "Photo has no unambiguous Installer tag and "
                "therefore cannot participate in Fixture reconstruction."
            ),
        )

    # --------------------------------------------------------
    # Process every Installer independently
    # --------------------------------------------------------

    for installer_name, installer_photos in installer_groups.items():

        process_installer_group(
            installer_name,
            installer_photos,
            phases,
            type_group,
            issues,
        )

    return type_group


# ============================================================
# TYPE LEVEL
# ============================================================

def process_type_level(
    parent_group: dict[str, Any],
    fixture_types: list[str],
    installers: list[str],
    phases: list[str],
    serial_tag: str,
    issues: list[Issue],
):
    """
    Classify photos within a Location or Sublocation into Types.
    """

    photos = parent_group.pop("_photos")

    type_groups, untagged = classify_types(
        photos,
        fixture_types,
        issues,
    )

    parent_group["types"] = []

    # --------------------------------------------------------
    # Type groups
    # --------------------------------------------------------

    for type_name, type_photos in type_groups.items():

        type_group = process_type_group(
            type_name,
            type_photos,
            installers,
            phases,
            serial_tag,
            issues,
        )

        parent_group["types"].append(type_group)

    # --------------------------------------------------------
    # Type-level Untagged
    # --------------------------------------------------------

    parent_group["untagged"] = untagged


# ============================================================
# NUMERIC BUCKET SORTING
# ============================================================

def sort_numeric_buckets(
    buckets: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Sort a mixture of ordinary and numeric buckets.

    Numeric buckets are ordered numerically among themselves.
    Non-numeric buckets retain their existing relative order.
    """

    numeric = [
        bucket
        for bucket in buckets
        if is_numeric_tag(str(bucket["name"]))
    ]

    non_numeric = [
        bucket
        for bucket in buckets
        if not is_numeric_tag(str(bucket["name"]))
    ]

    numeric.sort(
        key=lambda bucket: numeric_sort_key(
            str(bucket["name"])
        )
    )

    return numeric + non_numeric


def recursively_sort_numeric_buckets(
    structure: dict[str, Any],
):
    """
    Sort numeric Location and Sublocation buckets at every
    applicable level.
    """

    if "locations" in structure:

        structure["locations"] = sort_numeric_buckets(
            structure["locations"]
        )

        for location in structure["locations"]:
            recursively_sort_numeric_buckets(location)

    if "sublocations" in structure:

        structure["sublocations"] = sort_numeric_buckets(
            structure["sublocations"]
        )

        for sublocation in structure["sublocations"]:
            recursively_sort_numeric_buckets(
                sublocation
            )


# ============================================================
# CLEAN INTERNAL STRUCTURE
# ============================================================

def clean_internal_fields(node: Any):
    """
    Remove temporary internal fields such as _photos.

    Any photos still sitting in _photos are merged into untagged
    rather than discarded.
    """

    if isinstance(node, dict):

        stranded = node.pop("_photos", None)
        if stranded:
            node.setdefault("untagged", []).extend(stranded)

        for value in node.values():
            clean_internal_fields(value)

    elif isinstance(node, list):

        for item in node:
            clean_internal_fields(item)


def count_structure_photos(structure: dict[str, Any]) -> int:
    """
    Count every photo placed in the final lighting structure.
    """

    def _count_node(node: dict[str, Any]) -> int:
        total = len(node.get("untagged", []))
        for type_group in node.get("types", []):
            total += len(type_group.get("untagged", []))
            for fixture in type_group.get("fixtures", []):
                total += len(fixture.get("photos", []))
        for sublocation in node.get("sublocations", []):
            total += _count_node(sublocation)
        return total

    total = sum(_count_node(location) for location in structure.get("locations", []))
    total += len(structure.get("untagged", []))
    return total


# ============================================================
# MAIN FUNCTION
# ============================================================

def sort_lighting_photos(
    photos: list[Photo],
    installers: list[str],
    location_levels: list[dict],
    fixture_types: list[str],
    phases: list[str],
    serial_tag: str,
    loc_bigger_num: bool,
) -> SortResult:
    """
    Main Lighting Closeout Photo Sorting Algorithm.

    location_levels: list of {"tags": list[str], "numeric": bool}, max 5.
    """

    photos = _normalize_photos(photos)
    installers = _normalize_tag_list(installers)
    fixture_types = _normalize_tag_list(fixture_types)
    phases = _normalize_tag_list(phases)
    location_levels = _normalize_location_levels(location_levels)
    serial_tag = _normalize_serial_tag(serial_tag)

    issues: list[Issue] = []

    structure: dict[str, Any] = {
        "locations": [],
        "untagged": [],
    }

    location_groups, location_untagged = classify_top_level(
        photos,
        location_levels,
        loc_bigger_num,
        issues,
    )

    structure["untagged"].extend(location_untagged)

    for location_name, location_photos in location_groups.items():
        location_group = {
            "name": location_name,
            "_photos": location_photos,
        }

        if len(location_levels) > 1:
            process_child_levels(
                location_group,
                1,
                location_levels,
                fixture_types,
                installers,
                phases,
                serial_tag,
                loc_bigger_num,
                issues,
            )
        else:
            process_type_level(
                location_group,
                fixture_types,
                installers,
                phases,
                serial_tag,
                issues,
            )

        structure["locations"].append(location_group)

    recursively_sort_numeric_buckets(structure)
    clean_internal_fields(structure)

    input_count = len(photos)
    output_count = count_structure_photos(structure)
    if input_count != output_count:
        raise ValueError(
            "Lighting sort photo count mismatch: "
            f"{input_count} in, {output_count} out"
        )

    return SortResult(
        structure=structure,
        issues=issues,
    )