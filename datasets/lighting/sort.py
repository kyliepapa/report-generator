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
# LOCATION CLASSIFICATION
# ============================================================

def determine_location(
    photo: Photo,
    locations: list[str],
    loc_numeric: bool,
    subloc_numeric: bool,
    loc_bigger_num: bool,
    issues: list[Issue],
) -> tuple[Optional[str], Optional[str]]:
    """
    Determine Location for a photo.

    Returns:
        (location, numeric_sublocation_candidate)

    Explicit Location tags always take precedence over numeric
    tags.

    If both Location and Sublocation are numeric, two numeric
    tags may be interpreted according to loc_bigger_num.

    The second returned value is a candidate Sublocation value
    that can later be used during Sublocation processing.
    """

    # --------------------------------------------------------
    # Explicit Location
    # --------------------------------------------------------

    explicit_location, ambiguous = classify_explicit_tag(
        photo,
        locations,
    )

    if ambiguous:
        record_issue(
            issues,
            photo,
            "Location",
            "ambiguous_tag",
            "Photo contains multiple competing Location tags.",
        )
        return None, None

    if explicit_location is not None:
        return explicit_location, None

    # --------------------------------------------------------
    # No numeric Location support
    # --------------------------------------------------------

    if not loc_numeric:
        return None, None

    numeric_tags = matching_numeric_tags(photo)

    if not numeric_tags:
        return None, None

    unique_numeric = list(dict.fromkeys(numeric_tags))

    # --------------------------------------------------------
    # Only Location is numeric
    # --------------------------------------------------------

    if not subloc_numeric:

        if len(unique_numeric) == 1:
            return unique_numeric[0], None

        # Multiple numeric tags and no way to distinguish them.
        record_issue(
            issues,
            photo,
            "Location",
            "ambiguous_tag",
            "Photo contains multiple numeric tags and no "
            "numeric Sublocation classification is enabled.",
            context={"numeric_tags": unique_numeric},
        )
        return None, None

    # --------------------------------------------------------
    # Both Location and Sublocation are numeric
    # --------------------------------------------------------

    if len(unique_numeric) < 2:
        # There is only one numeric value. It cannot be reliably
        # distinguished between Location and Sublocation.
        record_issue(
            issues,
            photo,
            "Location",
            "missing_tag",
            "Both Location and Sublocation are numeric, but "
            "the photo does not contain two numeric tags.",
            context={"numeric_tags": unique_numeric},
        )
        return None, None

    if len(unique_numeric) > 2:
        record_issue(
            issues,
            photo,
            "Location",
            "ambiguous_tag",
            "Photo contains more than two numeric tags, so "
            "Location/Sublocation cannot be determined uniquely.",
            context={"numeric_tags": unique_numeric},
        )
        return None, None

    first, second = unique_numeric
    first_value = numeric_value(first)
    second_value = numeric_value(second)

    if first_value == second_value:
        record_issue(
            issues,
            photo,
            "Location",
            "ambiguous_tag",
            "Location and Sublocation numeric candidates are "
            "identical and cannot be distinguished.",
            context={"numeric_tags": unique_numeric},
        )
        return None, None

    if loc_bigger_num:
        location = first if first_value > second_value else second
        sublocation = second if first_value > second_value else first
    else:
        location = first if first_value < second_value else second
        sublocation = second if first_value < second_value else first

    return location, sublocation


# ============================================================
# SUBLOCATION CLASSIFICATION
# ============================================================

def determine_sublocation(
    photo: Photo,
    sublocations: list[str],
    subloc_numeric: bool,
    loc_bigger_num: bool,
    *,
    location: Optional[str] = None,
    location_numeric: bool = False,
    issues: list[Issue],
) -> Optional[str]:
    """
    Determine Sublocation for a photo.

    Explicit Sublocation always takes precedence over numeric
    Sublocation.

    When both Location and Sublocation are numeric, the numeric
    relationship is re-evaluated at this level.
    """

    if not sublocations:
        return None

    # --------------------------------------------------------
    # Explicit Sublocation
    # --------------------------------------------------------

    explicit_sublocation, ambiguous = classify_explicit_tag(
        photo,
        sublocations,
    )

    if ambiguous:
        record_issue(
            issues,
            photo,
            "Sublocation",
            "ambiguous_tag",
            "Photo contains multiple competing Sublocation tags.",
        )
        return None

    if explicit_sublocation is not None:
        return explicit_sublocation

    # --------------------------------------------------------
    # Numeric Sublocation
    # --------------------------------------------------------

    if not subloc_numeric:
        return None

    numeric_tags = list(dict.fromkeys(matching_numeric_tags(photo)))

    if not numeric_tags:
        return None

    # If Location was explicitly classified, its numeric
    # relationship does not need to be inferred here.
    #
    # We only use the two-number relationship when both levels
    # are being represented numerically.
    if location_numeric and len(numeric_tags) == 2:

        first, second = numeric_tags
        first_value = numeric_value(first)
        second_value = numeric_value(second)

        if first_value == second_value:
            record_issue(
                issues,
                photo,
                "Sublocation",
                "ambiguous_tag",
                "Numeric Location and Sublocation candidates "
                "are identical.",
            )
            return None

        if loc_bigger_num:
            sublocation = (
                second
                if first_value > second_value
                else first
            )
        else:
            sublocation = (
                second
                if first_value < second_value
                else first
            )

        return sublocation

    # If exactly one numeric tag remains available, it can serve
    # as the Sublocation.
    if len(numeric_tags) == 1:
        return numeric_tags[0]

    # More than one candidate with no deterministic way to
    # distinguish them.
    record_issue(
        issues,
        photo,
        "Sublocation",
        "ambiguous_tag",
        "Multiple numeric Sublocation candidates exist.",
        context={"numeric_tags": numeric_tags},
    )

    return None


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

    for photo in photos:

        if serial_tag in photo.tags:
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
# SUBLOCATION LEVEL
# ============================================================

def process_sublocations(
    location_group: dict[str, Any],
    sublocations: list[str],
    fixture_types: list[str],
    installers: list[str],
    phases: list[str],
    serial_tag: str,
    subloc_numeric: bool,
    loc_bigger_num: bool,
    issues: list[Issue],
):
    """
    Process the optional Sublocation layer.

    Photos that do not match a Sublocation proceed directly
    into Type processing at the Location level.
    """

    photos = location_group.pop("_photos")

    # --------------------------------------------------------
    # Sublocations disabled
    # --------------------------------------------------------

    if not sublocations:

        location_group["_photos"] = photos

        process_type_level(
            location_group,
            fixture_types,
            installers,
            phases,
            serial_tag,
            issues,
        )

        return

    # --------------------------------------------------------
    # Classify Sublocations
    # --------------------------------------------------------

    sublocation_groups: dict[str, list[Photo]] = {}
    unmatched: list[Photo] = []

    for photo in photos:

        sublocation = determine_sublocation(
            photo,
            sublocations,
            subloc_numeric,
            loc_bigger_num,
            issues=issues,
        )

        if sublocation is None:
            unmatched.append(photo)
        else:
            sublocation_groups.setdefault(
                sublocation,
                [],
            ).append(photo)

    # --------------------------------------------------------
    # No Sublocation matches
    #
    # Behaves exactly like an empty sublocations list.
    # --------------------------------------------------------

    if not sublocation_groups:

        location_group["_photos"] = photos

        process_type_level(
            location_group,
            fixture_types,
            installers,
            phases,
            serial_tag,
            issues,
        )

        return

    # --------------------------------------------------------
    # Process matched Sublocations
    # --------------------------------------------------------

    location_group["sublocations"] = []

    for sublocation_name, sublocation_photos in sublocation_groups.items():

        sublocation_group = {
            "name": sublocation_name,
            "_photos": sublocation_photos,
        }

        process_type_level(
            sublocation_group,
            fixture_types,
            installers,
            phases,
            serial_tag,
            issues,
        )

        location_group["sublocations"].append(
            sublocation_group
        )

    # --------------------------------------------------------
    # Process photos that had no Sublocation.
    #
    # They remain directly under the Location.
    # --------------------------------------------------------

    if unmatched:

        location_group["_photos"] = unmatched

        process_type_level(
            location_group,
            fixture_types,
            installers,
            phases,
            serial_tag,
            issues,
        )


# ============================================================
# LOCATION LEVEL
# ============================================================

def classify_locations(
    photos: list[Photo],
    locations: list[str],
    loc_numeric: bool,
    subloc_numeric: bool,
    loc_bigger_num: bool,
    issues: list[Issue],
) -> tuple[dict[str, list[Photo]], list[Photo], dict[str, str]]:
    """
    Classify photos into Locations.

    Returns:

        location_groups
        untagged_photos
        numeric_location_names

    numeric_location_names maps the output bucket name to the
    numeric value used to create it.
    """

    location_groups: dict[str, list[Photo]] = {}
    untagged: list[Photo] = []
    numeric_locations: dict[str, str] = {}

    for photo in photos:

        location, _numeric_sublocation_candidate = determine_location(
            photo,
            locations,
            loc_numeric,
            subloc_numeric,
            loc_bigger_num,
            issues,
        )

        if location is None:

            record_issue(
                issues,
                photo,
                "Location",
                "missing_tag",
                (
                    "Photo could not be assigned to a Location "
                    "and was placed in the top-level Untagged bucket."
                ),
            )

            untagged.append(photo)
            continue

        location_groups.setdefault(
            location,
            [],
        ).append(photo)

        if is_numeric_tag(location):
            numeric_locations[location] = location

    return location_groups, untagged, numeric_locations


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
    """

    if isinstance(node, dict):

        node.pop("_photos", None)

        for value in node.values():
            clean_internal_fields(value)

    elif isinstance(node, list):

        for item in node:
            clean_internal_fields(item)


# ============================================================
# MAIN FUNCTION
# ============================================================

def sort_lighting_photos(
    photos: list[Photo],
    installers: list[str],
    locations: list[str],
    sublocations: list[str],
    fixture_types: list[str],
    phases: list[str],
    serial_tag: str,
    loc_numeric: bool,
    subloc_numeric: bool,
    loc_bigger_num: bool,
) -> SortResult:
    """
    Main Lighting Closeout Photo Sorting Algorithm.

    Returns:
        SortResult(
            structure=...,
            issues=...
        )
    """

    issues: list[Issue] = []

    structure: dict[str, Any] = {
        "locations": [],
        "untagged": [],
    }

    # ========================================================
    # LOCATION CLASSIFICATION
    # ========================================================

    location_groups, location_untagged, numeric_locations = (
        classify_locations(
            photos,
            locations,
            loc_numeric,
            subloc_numeric,
            loc_bigger_num,
            issues,
        )
    )

    # --------------------------------------------------------
    # Top-level Untagged
    # --------------------------------------------------------

    structure["untagged"].extend(
        location_untagged
    )

    # ========================================================
    # PROCESS EACH LOCATION
    # ========================================================

    for location_name, location_photos in location_groups.items():

        location_group = {
            "name": location_name,
            "_photos": location_photos,
        }

        process_sublocations(
            location_group,
            sublocations,
            fixture_types,
            installers,
            phases,
            serial_tag,
            subloc_numeric,
            loc_bigger_num,
            issues,
        )

        structure["locations"].append(
            location_group
        )

    # ========================================================
    # FINAL SORTING
    # ========================================================

    recursively_sort_numeric_buckets(
        structure
    )

    # ========================================================
    # REMOVE TEMPORARY INTERNAL DATA
    # ========================================================

    clean_internal_fields(
        structure
    )

    return SortResult(
        structure=structure,
        issues=issues,
    )