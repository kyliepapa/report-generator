"""
Sort-key engine.

Four sort-key functions (one per structural hierarchy shape) plus a
dispatcher. Relocated from newreport.py with one deliberate change:
PHASE_ORDER was a bare module-level constant in the original; it now
reads from the active dataset via core.config.get_phase_order(), so a
future dataset with different phases than BEFORE/AFTER doesn't have to
fork this file.

BATHROOM_ORDER -> core.config.SUB_UNIT_ORDER. Everything else --
including the four sort_method_key literal strings this dispatches
on -- is unchanged. See datasets/base.py's sort_mode_map docstring for
why those 4 strings are a structural contract, not free-form labels.
"""

import core.config as config
from core.tag_parser import parse_bldg_unit, is_unassigned_photo


def get_sort_key_unit_phase(photo, unit_bath_map=None):
    tags_clean = [t.strip().upper() for t in photo.get("tag_names", [])]
    bldg, unit = parse_bldg_unit(tags_clean)
    phase_order = config.get_phase_order()
    phase_idx = next((i for i, n in enumerate(phase_order) if n in tags_clean), -1)
    phase_lbl = next((n for n in phase_order if n in tags_clean), -1)
    return (unit, phase_idx, phase_lbl)


def get_sort_key_bldg_unit_phase(photo, unit_bath_map=None):
    tags_clean = [t.strip().upper() for t in photo.get("tag_names", [])]
    bldg, unit_val = parse_bldg_unit(tags_clean)
    phase_order = config.get_phase_order()
    phase_idx = next((i for i, n in enumerate(phase_order) if n in tags_clean), -1)
    return (bldg, unit_val, phase_idx)


def get_sort_key_unit_bath_phase(photo, unit_bath_map=None):
    tags_clean = [t.strip().upper() for t in photo.get("tag_names", [])]
    bldg, unit_val = parse_bldg_unit(tags_clean)
    bath_idx = next(
        (i for i, b in enumerate(config.SUB_UNIT_ORDER)
         if any(b.upper() in tag for tag in tags_clean)),
        -1
    )
    phase_order = config.get_phase_order()
    phase_idx = next((i for i, n in enumerate(phase_order) if n in tags_clean), -1)
    unassigned = is_unassigned_photo(bath_idx, phase_idx)
    if unassigned and unit_val != "UNASSIGNED" and unit_bath_map:
        if unit_val in unit_bath_map:
            bath_idx = unit_bath_map[unit_val]
    unassigned_priority = 0 if is_unassigned_photo(bath_idx, phase_idx) else 1
    return (unit_val, unassigned_priority, bath_idx, phase_idx)


def get_sort_key_full(photo, unit_bath_map=None):
    tags_clean = [t.strip().upper() for t in photo.get("tag_names", [])]
    bldg, unit_val = parse_bldg_unit(tags_clean)
    bath_idx = next(
        (i for i, b in enumerate(config.SUB_UNIT_ORDER)
         if any(b.upper() in tag for tag in tags_clean)),
        -1
    )
    phase_order = config.get_phase_order()
    phase_idx = next((i for i, n in enumerate(phase_order) if n in tags_clean), -1)
    unassigned = is_unassigned_photo(bath_idx, phase_idx)
    if unassigned and unit_val != "UNASSIGNED" and unit_bath_map:
        if unit_val in unit_bath_map:
            bath_idx = unit_bath_map[unit_val]
    unassigned_priority = 0 if is_unassigned_photo(bath_idx, phase_idx) else 1
    return (bldg, unit_val, unassigned_priority, bath_idx, phase_idx)


def determine_sort_method(key):
    if key == "unit_phase":
        return get_sort_key_unit_phase
    elif key == "bldg_unit_phase":
        return get_sort_key_bldg_unit_phase
    elif key == "unit_bath_phase":
        return get_sort_key_unit_bath_phase
    else:
        return get_sort_key_full


def get_sort_key(photo, unit_bath_map=None):
    sort_func = determine_sort_method(config.SORT_METHOD_KEY)
    return sort_func(photo, unit_bath_map)