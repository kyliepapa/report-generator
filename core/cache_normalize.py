"""
Normalize sorted structures to slim photo dicts before disk cache.

Strips raw CompanyCam payloads and Photo dataclasses while retaining
fields required for PDF links, captions, and transforms.
"""

from reporting.html.generators import (
    _lighting_photo_dict,
    _subcontract_photo_dict,
    _heat_pump_photo_dict,
)

LIGHTING_SORT_KEY = "location_sublocation_type_fixture_phase"
SUBCONTRACTED_SORT_KEY = "subcontracted_sequence"
HEAT_PUMP_SORT_KEY = "heat_pump_phase_serial_buckets"
MANUAL_ARRANGE_SORT_KEY = "manual_arrange_sequence"

_SLIM_PHOTO_KEYS = (
    "url", "original_url", "has_image", "captured_at", "latitude", "longitude",
    "tag_string", "extra_tags", "all_tags", "session_tags",
)


def _slim_photo_dict(photo_dict):
    if not isinstance(photo_dict, dict):
        return photo_dict
    return {k: photo_dict[k] for k in _SLIM_PHOTO_KEYS if k in photo_dict}


def _normalize_photo(photo, normalizer):
    if photo is None:
        return None
    if isinstance(photo, dict) and all(k in photo for k in ("url", "has_image")):
        return _slim_photo_dict(photo)
    return _slim_photo_dict(normalizer(photo))


def _normalize_plumbing_phases(phases_dict):
    if not isinstance(phases_dict, dict):
        return phases_dict
    return {
        phase: [_slim_photo_dict(p) for p in photos]
        for phase, photos in phases_dict.items()
    }


def _normalize_plumbing_structure(structure, sort_mode):
    if not isinstance(structure, dict):
        return structure or {}

    if sort_mode == "full":
        return {
            bldg: {
                unit: {
                    bath: _normalize_plumbing_phases(phases)
                    for bath, phases in units.items()
                }
                for unit, units in bldg_data.items()
            }
            for bldg, bldg_data in structure.items()
        }
    if sort_mode == "bldg_unit_phase":
        return {
            bldg: {
                unit: _normalize_plumbing_phases(phases)
                for unit, phases in units.items()
            }
            for bldg, units in structure.items()
        }
    if sort_mode == "unit_bath_phase":
        return {
            unit: {
                bath: _normalize_plumbing_phases(phases)
                for bath, phases in baths.items()
            }
            for unit, baths in structure.items()
        }
    return {
        unit: _normalize_plumbing_phases(phases)
        for unit, phases in structure.items()
    }


def _normalize_lighting_photos(photos):
    return [_normalize_photo(p, _lighting_photo_dict) for p in photos]


def _normalize_lighting_group(group):
    if not isinstance(group, dict):
        return group
    out = dict(group)
    if "types" in group:
        out["types"] = [_normalize_lighting_type(t) for t in group.get("types", [])]
    if "fixtures" in group:
        out["fixtures"] = [_normalize_lighting_fixture(f) for f in group.get("fixtures", [])]
    if "sublocations" in group:
        out["sublocations"] = [_normalize_lighting_group(s) for s in group.get("sublocations", [])]
    if "untagged" in group:
        out["untagged"] = _normalize_lighting_photos(group.get("untagged", []))
    return out


def _normalize_lighting_type(type_group):
    if not isinstance(type_group, dict):
        return type_group
    out = dict(type_group)
    out["fixtures"] = [_normalize_lighting_fixture(f) for f in type_group.get("fixtures", [])]
    out["untagged"] = _normalize_lighting_photos(type_group.get("untagged", []))
    return out


def _normalize_lighting_fixture(fixture):
    if not isinstance(fixture, dict):
        return fixture
    out = dict(fixture)
    out["photos"] = _normalize_lighting_photos(fixture.get("photos", []))
    return out


def _normalize_lighting_structure(structure):
    if not isinstance(structure, dict):
        return structure or {}
    return {
        "locations": [_normalize_lighting_group(loc) for loc in structure.get("locations", [])],
        "untagged": _normalize_lighting_photos(structure.get("untagged", [])),
    }


def _normalize_subcontracted_structure(structure):
    if not isinstance(structure, dict):
        return structure or {}
    items = []
    for item in structure.get("items", []):
        if item.get("type") == "photo":
            items.append({
                **item,
                "photo": _normalize_photo(item.get("photo"), _subcontract_photo_dict),
            })
        else:
            items.append(item)
    return {"items": items}


def _normalize_heat_pump_location(loc):
    buckets = []
    for bucket in loc.get("buckets", []):
        buckets.append({
            **{k: v for k, v in bucket.items() if k != "photos"},
            "photos": [
                _normalize_photo(p, _heat_pump_photo_dict)
                for p in bucket.get("photos", [])
            ],
        })
    return {
        "name": loc.get("name", ""),
        "buckets": buckets,
        "untagged": [
            _normalize_photo(p, _heat_pump_photo_dict)
            for p in loc.get("untagged", [])
        ],
        "fixture_order": loc.get("fixture_order", []),
    }


def _normalize_heat_pump_structure(structure):
    if not isinstance(structure, dict):
        return structure or {}
    if structure.get("locations"):
        return {
            "locations": [
                _normalize_heat_pump_location(loc)
                for loc in structure.get("locations", [])
            ],
            "untagged": [
                _normalize_photo(p, _heat_pump_photo_dict)
                for p in structure.get("untagged", [])
            ],
        }
    buckets = []
    for bucket in structure.get("buckets", []):
        buckets.append({
            **{k: v for k, v in bucket.items() if k != "photos"},
            "photos": [
                _normalize_photo(p, _heat_pump_photo_dict)
                for p in bucket.get("photos", [])
            ],
        })
    return {
        "buckets": buckets,
        "untagged": [
            _normalize_photo(p, _heat_pump_photo_dict)
            for p in structure.get("untagged", [])
        ],
    }


def _normalize_manual_arrange_structure(structure):
    if not isinstance(structure, dict):
        return structure or {}
    staging_items = []
    for item in structure.get("staging_items", []):
        if item.get("type") == "photo":
            staging_items.append({
                **item,
                "photo": _normalize_photo(item.get("photo"), _subcontract_photo_dict),
            })
        else:
            staging_items.append(item)
    buckets = []
    for bucket in structure.get("buckets", []):
        buckets.append({
            **{k: v for k, v in bucket.items() if k != "photos"},
            "photos": [
                _normalize_photo(p, _subcontract_photo_dict)
                for p in bucket.get("photos", [])
            ],
        })
    out = {"staging_items": staging_items}
    if buckets:
        out["buckets"] = buckets
    return out


def normalize_special_rooms_for_cache(special_rooms_structure):
    if not special_rooms_structure:
        return {}
    return {
        room: _normalize_plumbing_phases(phases)
        for room, phases in special_rooms_structure.items()
    }


def normalize_structure_for_cache(structure, sort_mode=None):
    if not structure:
        return structure or {}

    if sort_mode == LIGHTING_SORT_KEY:
        return _normalize_lighting_structure(structure)
    if sort_mode == SUBCONTRACTED_SORT_KEY:
        return _normalize_subcontracted_structure(structure)
    if sort_mode == HEAT_PUMP_SORT_KEY:
        return _normalize_heat_pump_structure(structure)
    if sort_mode == MANUAL_ARRANGE_SORT_KEY:
        return _normalize_manual_arrange_structure(structure)
    return _normalize_plumbing_structure(structure, sort_mode)
