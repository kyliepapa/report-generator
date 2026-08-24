from datasets.base import DatasetConfig


def _lighting_sort_mode_map(label_format: str, multi_sub_unit: bool) -> str:
    # Lighting does not follow plumbing's bathroom/unit hierarchy.
    return "location_sublocation_type_fixture_phase"


LIGHTING = DatasetConfig(
    key="lighting",
    display_name="Lighting",
    sub_unit_field_name="area",
    sub_unit_label_singular="Area",
    sub_unit_label_plural="Areas",
    primary_sub_unit_marker=None,
    phase_order=["UNTAGGED", "BEFORE", "AFTER"],
    sort_shape="lighting",
    render_mode="lighting",
    sort_mode_map=_lighting_sort_mode_map,
    supports_special_rooms=False,
)

# This file is new as part of an experimental refactor