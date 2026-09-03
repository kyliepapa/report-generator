"""
Automatic (structure-derived) PDF heading catalog and label resolution.

Used by the HTML report (embed catalog for the PDF modal) and report_builder
(apply user overrides at render time). Injected subcontracted/manual-arrange
headings are handled separately via heading_edits.
"""

from __future__ import annotations

import core.config as config

LIGHTING_SORT_KEY = "location_sublocation_type_fixture_phase"
HEAT_PUMP_SORT_KEY = "heat_pump_phase_serial_buckets"
SUBCONTRACTED_SORT_KEY = "subcontracted_sequence"
MANUAL_ARRANGE_SORT_KEY = "manual_arrange_sequence"


def sub_unit_label():
    ds = config.ACTIVE_DATASET
    if ds is None:
        return "Sub-Unit"
    if ds.key == "lighting":
        return "Fixture"
    if ds.key == "plumbing":
        return "Bathroom"
    return ds.sub_unit_label_singular


def lighting_path_key(path_parts):
    if not path_parts:
        return ""
    key = f"loc:{path_parts[0]}"
    for part in path_parts[1:]:
        key += f":sub:{part}"
    return key


def lighting_path_default(path_parts):
    return ": ".join(path_parts)


def _building_default(bldg):
    return f"Building {bldg if bldg != 'NO_BLDG' else 'Unassigned'}"


def _unit_default(unit):
    return f"Unit {unit if unit != 'UNASSIGNED' else 'Unassigned'}"


def _bathroom_default(bath, sub_label):
    return f"{bath.title()} {sub_label}"


def _add_heading(headings, key, heading_type, default_label):
    if not key or not default_label:
        return
    if key not in headings:
        headings[key] = {
            "key": key,
            "type": heading_type,
            "default_label": default_label,
        }


def _collect_special_rooms(special, headings):
    for room_name in sorted(special or {}):
        _add_heading(headings, f"special:{room_name}", "special", room_name)


def _walk_lighting_group(group, path_parts, headings):
    _add_heading(
        headings,
        lighting_path_key(path_parts),
        f"location_level_{len(path_parts)}",
        lighting_path_default(path_parts),
    )
    for type_group in group.get("types", []):
        type_name = type_group.get("name", "")
        _add_heading(
            headings,
            f"type:{lighting_path_key(path_parts)}:{type_name}",
            "fixture_type",
            type_name,
        )
    for sub in group.get("sublocations", []):
        _walk_lighting_group(sub, path_parts + [sub.get("name", "")], headings)


def _collect_lighting(structure, headings):
    for location in structure.get("locations", []):
        _walk_lighting_group(location, [location.get("name", "")], headings)


def _collect_buckets(structure, headings):
    for bucket in structure.get("buckets", []):
        label = bucket.get("label", "")
        _add_heading(headings, f"bucket:{label}", "bucket", label)


def _collect_heat_pump_locations(structure, headings):
    for location in structure.get("locations", []):
        loc_name = location.get("name", "")
        _add_heading(headings, f"loc:{loc_name}", "location", loc_name)
        for bucket in location.get("buckets", []):
            label = bucket.get("label", "")
            _add_heading(
                headings,
                f"loc:{loc_name}:bucket:{label}",
                "bucket",
                label,
            )


def collect_measure_automatic_headings(measure):
    """Return [{ key, type, default_label }, ...] for one measure tab."""
    shape = measure.get("shape") or ""
    structure = measure.get("structure") or {}
    special = measure.get("special") or {}
    sub_label = sub_unit_label()
    headings = {}

    if shape == "full":
        for bldg in sorted(structure):
            _add_heading(headings, f"building:{bldg}", "building", _building_default(bldg))
            for unit in sorted(structure[bldg]):
                _add_heading(
                    headings,
                    f"unit:{bldg}:{unit}",
                    "unit",
                    _unit_default(unit),
                )
                for bath in sorted(structure[bldg][unit]):
                    if bath == "OTHER":
                        continue
                    _add_heading(
                        headings,
                        f"bathroom:{bldg}:{unit}:{bath}",
                        "bathroom",
                        _bathroom_default(bath, sub_label),
                    )

    elif shape == "bldg_unit_phase":
        for bldg in sorted(structure):
            _add_heading(headings, f"building:{bldg}", "building", _building_default(bldg))
            for unit in sorted(structure[bldg]):
                _add_heading(
                    headings,
                    f"unit:{bldg}:{unit}",
                    "unit",
                    _unit_default(unit),
                )

    elif shape == "unit_bath_phase":
        for unit in sorted(structure):
            _add_heading(headings, f"unit:{unit}", "unit", _unit_default(unit))
            for bath in sorted(structure[unit]):
                if bath == "OTHER":
                    continue
                _add_heading(
                    headings,
                    f"bathroom:{unit}:{bath}",
                    "bathroom",
                    _bathroom_default(bath, sub_label),
                )

    elif shape == "unit_phase":
        for unit in sorted(structure):
            _add_heading(headings, f"unit:{unit}", "unit", _unit_default(unit))

    elif shape == LIGHTING_SORT_KEY:
        _collect_lighting(structure, headings)

    elif shape == HEAT_PUMP_SORT_KEY:
        if structure.get("locations"):
            _collect_heat_pump_locations(structure, headings)
        else:
            _collect_buckets(structure, headings)

    elif shape == MANUAL_ARRANGE_SORT_KEY:
        _collect_buckets(structure, headings)

    _collect_special_rooms(special, headings)

    return list(headings.values())


def build_automatic_heading_catalog(measures):
    """Return { measure_id: [{ key, type, default_label }, ...] }."""
    catalog = {}
    for measure in measures or []:
        measure_id = measure.get("id")
        if not measure_id:
            continue
        entries = collect_measure_automatic_headings(measure)
        if entries:
            catalog[measure_id] = entries
    return catalog


def resolve_heading_label(key, default, pdf_options):
    measure_id = pdf_options.get("_current_measure_id") or ""
    if not measure_id:
        return default
    entry = (pdf_options.get("measure_options") or {}).get(measure_id, {})
    if not isinstance(entry, dict):
        return default
    labels = entry.get("heading_labels") or {}
    override = str(labels.get(key, "") or "").strip()
    return override or default


def count_heading_label_overrides(measure_options):
    count = 0
    for opts in (measure_options or {}).values():
        if not isinstance(opts, dict):
            continue
        labels = opts.get("heading_labels") or {}
        count += sum(1 for value in labels.values() if str(value or "").strip())
    return count
