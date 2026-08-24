from datasets.base import DatasetConfig


def _subcontracted_sort_mode_map(label_format: str, multi_sub_unit: bool) -> str:
    return "subcontracted_sequence"


SUBCONTRACTED = DatasetConfig(
    key="subcontracted",
    display_name="Subcontracted",
    sub_unit_field_name="item",
    sub_unit_label_singular="Item",
    sub_unit_label_plural="Items",
    primary_sub_unit_marker=None,
    phase_order=[],
    sort_shape="subcontracted",
    render_mode="subcontracted",
    sort_mode_map=_subcontracted_sort_mode_map,
    supports_special_rooms=False,
)
