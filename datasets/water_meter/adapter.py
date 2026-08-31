"""
datasets/water_meter/adapter.py

Wraps the water-meter draft (sort.py) behind the common SortOutput
envelope so core.dataset_router can call it the same way it calls
plumbing and lighting. Photos use the program-wide "tag_names"
contract now, same as the other two datasets.

Note: sort_photos() mutates each photo dict in place (adds
"apt"/"designation" keys) -- unchanged from the original draft.
"""

from core.sort_result import SortOutput
from datasets.water_meter.sort import sort_photos


def run(photos, techs, types, phases, serial_tag):
    raw = sort_photos(techs, types, phases, serial_tag, photos)

    issues = []
    for photo in raw["errors"]["missing_unit_tag"]:
        issues.append({
            "photo_id": photo.get("id"),
            "type": "missing_unit_tag",
            "severity": "error",
        })
    for photo in raw["errors"]["missing_specifier_tags"]:
        issues.append({
            "photo_id": photo.get("id"),
            "unit": photo.get("apt"),
            "type": "missing_specifier_tags",
            "severity": "warning",
        })
    for unit in raw["errors"]["units_with_missing_or_duplicated_photos"]:
        issues.append({
            "unit": unit,
            "type": "incomplete_or_duplicate_designations",
            "severity": "warning",
        })

    return SortOutput(
        dataset_key="water_meter",
        shape="unit_designation_list",  # unit -> ordered list of photos (designation 1-6)
        structure=raw["units"],
        untagged=raw["untagged"],
        issues=issues,
    )