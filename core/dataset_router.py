"""
core/dataset_router.py

One call site for "run whichever dataset's sort algorithm applies,
get back a SortOutput". Existing plumbing code (core/config.py,
core/organizer.py, core/sort_engine.py) is untouched -- run_plumbing()
just calls it in the same sequence app.py already does and wraps the
result. Water meter and lighting go through their own adapters.

This is deliberately separate from DatasetConfig (datasets/base.py):
that class's sort_mode_map/sub_unit_* fields describe plumbing's
bldg/unit/sub-unit/phase shape specifically. Water meter (unit ->
ordered designation list) and lighting (location -> sublocation ->
type -> fixture -> phase) don't share that shape, so forcing them
into DatasetConfig would mean fields that don't apply to them. A
plain dispatch table is more honest about that until/unless a shared
shape emerges -- at which point this table is the one place that'd
need to change.

Usage (from app.py, once photos + form inputs are collected):

    from core.dataset_router import run_sort

    result = run_sort("water_meter", photos,
                       techs=[...], types=[...], phases=[...],
                       serial_tag="SN")

    result.structure  # dataset-specific shape, see result.shape
    result.issues      # list of normalized issue dicts
"""

from core.sort_result import SortOutput


def run_plumbing(photos, **kwargs):
    """
    Assumes core.config is already configured for this job (set_dataset,
    set_inputs, configure_sub_units, configure_sorting, configure_special_rooms
    -- same sequence app.py already runs). Unchanged pipeline, just wrapped.
    """
    import core.config as config
    from core.organizer import organize_photos, analyze_missing_photos, build_unit_bathroom_map
    from core.sort_engine import get_sort_key

    unit_bath_map = build_unit_bathroom_map(photos)
    photos.sort(key=lambda p: get_sort_key(p, unit_bath_map))
    structure, special = organize_photos(photos, unit_bath_map)
    missing = analyze_missing_photos(structure)

    issues = [{"label": lbl, "phase": "BEFORE", "type": "missing_photo"} for lbl in missing["BEFORE"]]
    issues += [{"label": lbl, "phase": "AFTER", "type": "missing_photo"} for lbl in missing["AFTER"]]

    return SortOutput(
        dataset_key=config.ACTIVE_DATASET.key if config.ACTIVE_DATASET else "plumbing",
        shape=config.SORT_METHOD_KEY,
        structure=structure,
        special=special,
        issues=issues,
    )


def run_water_meter(photos, **kwargs):
    from datasets.water_meter.adapter import run
    return run(
        photos,
        techs=kwargs["techs"],
        types=kwargs["types"],
        phases=kwargs["phases"],
        serial_tag=kwargs["serial_tag"],
    )


def run_lighting(photos, **kwargs):
    from datasets.lighting.adapter import run
    return run(
        photos,
        installers=kwargs["installers"],
        location_levels=kwargs["location_levels"],
        fixture_types=kwargs["fixture_types"],
        phases=kwargs["phases"],
        serial_tag=kwargs["serial_tag"],
        loc_bigger_num=kwargs["loc_bigger_num"],
    )


def run_subcontracted(photos, **kwargs):
    from datasets.subcontracted.adapter import run
    return run(
        photos,
        hash_char=kwargs["hash"],
        measure_mark=kwargs.get("measure_mark") or "",
        key_source=kwargs.get("key_source") or "tags",
    )


def run_heat_pump(photos, **kwargs):
    from datasets.heat_pump.adapter import run
    return run(
        photos,
        fixtures=kwargs["fixtures"],
        serial_tag=kwargs["serial_tag"],
        allow_competing_fixture_tags=kwargs.get("allow_competing_fixture_tags", False),
        auto_assign_lone_serial_to_before=kwargs.get(
            "auto_assign_lone_serial_to_before", False
        ),
        intuitive_fixture_sort=kwargs.get("intuitive_fixture_sort", True),
        multi_unit=kwargs.get("multi_unit", False),
        lone_number_mode=kwargs.get("lone_number_mode", "none"),
        locations=kwargs.get("locations"),
    )


def run_manual_arrange(photos, **kwargs):
    from datasets.manual_arrange.adapter import run
    return run(
        photos,
        pre_sort_buckets=kwargs.get("pre_sort_buckets"),
        allow_conflicting_tags=kwargs.get("allow_conflicting_tags", True),
    )


ROUTES = {
    "plumbing": run_plumbing,
    "water_meter": run_water_meter,
    "lighting": run_lighting,
    "subcontracted": run_subcontracted,
    "heat_pump": run_heat_pump,
    "manual_arrange": run_manual_arrange,
}


def run_sort(dataset_key, photos, **kwargs):
    if dataset_key not in ROUTES:
        raise ValueError(f"Unknown dataset key: {dataset_key!r}. Known: {list(ROUTES)}")
    return ROUTES[dataset_key](photos, **kwargs)