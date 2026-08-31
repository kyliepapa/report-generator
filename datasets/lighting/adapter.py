"""
datasets/lighting/adapter.py

Wraps the lighting draft (sort.py, unmodified) behind the common
SortOutput envelope so core.dataset_router can call it the same way
it calls plumbing and water meter.

Input note: the draft expects a list of datasets.lighting.sort.Photo
(dataclass with .tags/.timestamp), not raw tag_names dicts. Build
that list from your CompanyCam pull before calling run() -- kept as
the caller's job rather than guessing a conversion here.
"""

from dataclasses import asdict

from core.sort_result import SortOutput
from datasets.lighting.sort import sort_lighting_photos


def run(photos, installers, location_levels, fixture_types,
        phases, serial_tag, loc_bigger_num):
    result = sort_lighting_photos(
        photos, installers, location_levels, fixture_types,
        phases, serial_tag, loc_bigger_num,
    )

    return SortOutput(
        dataset_key="lighting",
        shape="location_sublocation_type_fixture_phase",
        structure=result.structure,  # {"locations": [...], "untagged": [...]}
        untagged=result.structure.get("untagged", []),
        issues=[asdict(i) for i in result.issues],
    )