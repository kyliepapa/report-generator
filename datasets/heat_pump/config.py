from datasets.base import DatasetConfig

# Intuitive Fixture Sort — primary fixture tags (fixed order).
PRIMARY_FIXTURE_TAGS = [
    "COMMON AREA ELECTRIC METER NUMBER",
    "COMMON AREA ELECTRIC METER #",
    "THERMOSTATIC MIXING VALVE",
    "GAS METER",
    "METER NUMBER",
    "ELECTRIC METER",
    "METER NUMBER",
    "METER #",
    "WATER HEATER JA-13",
    "ENABLEMENT/TOU",
    "TOU SCREENSHOT",
    "ENABLEMENT SCREENSHOT",
]

# Intuitive Fixture Sort — ancillary tags (runtime order built dynamically).
ANCILLARY_FIXTURE_TAGS = [
    "EXPANSION TANK",
    "STRAPS",
    "DRAINPAINS",
    "CHECK VALVE",
    "BALL VALVE",
    "TMV",
    "TMVS",
    "INSULATION",
    "DUCTING",
    "CONDENSATION PITS/LINES",
    "CONDENSATION PIT",
    "CONDENSATION LINE",
    "CONDENSER",
    "DESCALER",
    "ISOLATION VALVE",
]


def _heat_pump_sort_mode_map(label_format: str, multi_sub_unit: bool) -> str:
    return "heat_pump_phase_serial_buckets"


def parse_heat_pump_location_config(
    multi_unit: bool,
    lone_number_mode: str,
    locations,
) -> dict:
    """Normalize multi-unit location settings from API/frontend payload."""
    mode = str(lone_number_mode or "none").strip().lower()
    if mode not in ("none", "some", "all"):
        mode = "none"
    locs = []
    if isinstance(locations, str):
        locs = [t.strip() for t in locations.split(",") if t.strip()]
    elif locations:
        locs = [str(t).strip() for t in locations if str(t).strip()]
    return {
        "multi_unit": bool(multi_unit),
        "lone_number_mode": mode,
        "locations": locs,
    }


HEAT_PUMP = DatasetConfig(
    key="heat_pump",
    display_name="Water Heaters / Heat Pumps",
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
