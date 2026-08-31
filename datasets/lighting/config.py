from datasets.base import DatasetConfig


def _to_list(val):
    if isinstance(val, list):
        return [str(x).strip() for x in val if str(x).strip()]
    if isinstance(val, str):
        return [x.strip() for x in val.split(",") if x.strip()]
    return []


def _yes_no(val) -> bool:
    return str(val or "").strip().lower() == "yes"


def parse_location_levels(payload: dict) -> list[dict]:
    """
    Normalize lighting location levels from a measure payload.
    Each level: {"tags": list[str], "numeric": bool}. Max 5 levels.
    """
    raw = payload.get("location_levels")
    if raw and isinstance(raw, list):
        levels = []
        for item in raw[:5]:
            if not isinstance(item, dict):
                continue
            levels.append({
                "tags": _to_list(item.get("tags")),
                "numeric": _yes_no(item.get("numeric")),
            })
        if levels:
            return levels

    levels = [{
        "tags": _to_list(payload.get("locations")),
        "numeric": _yes_no(payload.get("loc_numeric")),
    }]
    sub_tags = _to_list(payload.get("sublocations"))
    if sub_tags or _yes_no(payload.get("subloc_numeric")):
        levels.append({
            "tags": sub_tags,
            "numeric": _yes_no(payload.get("subloc_numeric")),
        })
    return levels


def level1_tags(payload: dict) -> list[str]:
    levels = parse_location_levels(payload)
    return levels[0]["tags"] if levels else []


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