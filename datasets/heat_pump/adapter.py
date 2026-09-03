"""
datasets/heat_pump/adapter.py

Wraps sort_heat_pump_photos behind the common SortOutput envelope.
"""

from core.sort_result import SortOutput
from datasets.heat_pump.sort import sort_heat_pump_photos

HEAT_PUMP_SHAPE = "heat_pump_phase_serial_buckets"


def run(
    photos,
    fixtures,
    serial_tag,
    allow_competing_fixture_tags=False,
    auto_assign_lone_serial_to_before=False,
    intuitive_fixture_sort=True,
    multi_unit=False,
    lone_number_mode="none",
    locations=None,
):
    result = sort_heat_pump_photos(
        photos,
        fixtures=fixtures,
        serial_tag=serial_tag,
        allow_competing_fixture_tags=allow_competing_fixture_tags,
        auto_assign_lone_serial_to_before=auto_assign_lone_serial_to_before,
        intuitive_fixture_sort=intuitive_fixture_sort,
        multi_unit=multi_unit,
        lone_number_mode=lone_number_mode,
        locations=locations,
    )

    return SortOutput(
        dataset_key="heat_pump",
        shape=HEAT_PUMP_SHAPE,
        structure=result.structure,
        untagged=result.structure.get("untagged", []),
        issues=result.issues,
    )
