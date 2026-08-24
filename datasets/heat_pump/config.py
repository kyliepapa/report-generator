from datasets.base import DatasetConfig


def _heat_pump_sort_mode_map(label_format: str, multi_sub_unit: bool) -> str:
    return "heat_pump_phase_serial_buckets"


HEAT_PUMP = DatasetConfig(
    key="heat_pump",
    display_name="Single-Unit Heat Pump",
    sub_unit_field_name="fixture",
    sub_unit_label_singular="Fixture",
    sub_unit_label_plural="Fixtures",
    primary_sub_unit_marker=None,
    phase_order=["BEFORE", "AFTER"],
    sort_shape="heat_pump",
    render_mode="heat_pump",
    sort_mode_map=_heat_pump_sort_mode_map,
    supports_special_rooms=False,
)
