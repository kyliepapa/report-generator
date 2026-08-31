"""Tests for multi-level lighting location nesting."""

from datetime import datetime, timezone

from datasets.lighting.config import parse_location_levels
from datasets.lighting.sort import Photo, count_structure_photos, sort_lighting_photos


def _photo(photo_id, tags):
    return Photo(
        photo_id=photo_id,
        tags=tags,
        timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )


def _base_sort_kwargs():
    return {
        "installers": ["Tech"],
        "fixture_types": ["Wallpack"],
        "phases": ["BEFORE"],
        "serial_tag": "SERIAL",
    }


def test_parse_location_levels_legacy_payload():
    payload = {
        "locations": "Exterior,Hallway",
        "sublocations": "North Wing",
        "loc_numeric": "No",
        "subloc_numeric": "Yes",
        "loc_bigger_num": "Yes",
    }
    levels = parse_location_levels(payload)
    assert len(levels) == 2
    assert levels[0] == {"tags": ["Exterior", "Hallway"], "numeric": False}
    assert levels[1] == {"tags": ["North Wing"], "numeric": True}


def test_parse_location_levels_new_payload():
    payload = {
        "location_levels": [
            {"tags": "A", "numeric": "No"},
            {"tags": "B,C", "numeric": "Yes"},
        ],
    }
    levels = parse_location_levels(payload)
    assert levels[0]["tags"] == ["A"]
    assert levels[1] == {"tags": ["B", "C"], "numeric": True}


def test_three_level_explicit_classification():
    location_levels = [
        {"tags": ["Building A"], "numeric": False},
        {"tags": ["Floor 2"], "numeric": False},
        {"tags": ["Room 101"], "numeric": False},
    ]
    photos = [
        _photo("p1", ["Building A", "Floor 2", "Room 101", "Wallpack", "BEFORE", "Tech"]),
    ]
    result = sort_lighting_photos(
        photos,
        location_levels=location_levels,
        loc_bigger_num=False,
        **_base_sort_kwargs(),
    )
    loc = result.structure["locations"][0]
    assert loc["name"] == "BUILDING A"
    assert loc["sublocations"][0]["name"] == "FLOOR 2"
    assert loc["sublocations"][0]["sublocations"][0]["name"] == "ROOM 101"
    assert loc["sublocations"][0]["sublocations"][0]["types"]


def test_unmatched_photos_stay_at_parent_level():
    location_levels = [
        {"tags": ["Building A"], "numeric": False},
        {"tags": ["Floor 2"], "numeric": False},
    ]
    photos = [
        _photo("p1", ["Building A", "Wallpack", "BEFORE", "Tech"]),
    ]
    result = sort_lighting_photos(
        photos,
        location_levels=location_levels,
        loc_bigger_num=False,
        **_base_sort_kwargs(),
    )
    loc = result.structure["locations"][0]
    assert loc["name"] == "BUILDING A"
    assert not loc.get("sublocations")
    assert loc["types"]


def test_three_level_numeric_loc_bigger_num_true():
    location_levels = [
        {"tags": [], "numeric": True},
        {"tags": [], "numeric": True},
        {"tags": [], "numeric": True},
    ]
    photos = [
        _photo("p1", ["1", "2", "3", "Wallpack", "BEFORE", "Tech"]),
    ]
    result = sort_lighting_photos(
        photos,
        location_levels=location_levels,
        loc_bigger_num=True,
        **_base_sort_kwargs(),
    )
    loc = result.structure["locations"][0]
    assert loc["name"] == "3"
    assert loc["sublocations"][0]["name"] == "2"
    assert loc["sublocations"][0]["sublocations"][0]["name"] == "1"


def test_three_level_numeric_loc_bigger_num_false():
    location_levels = [
        {"tags": [], "numeric": True},
        {"tags": [], "numeric": True},
        {"tags": [], "numeric": True},
    ]
    photos = [
        _photo("p1", ["1", "2", "3", "Wallpack", "BEFORE", "Tech"]),
    ]
    result = sort_lighting_photos(
        photos,
        location_levels=location_levels,
        loc_bigger_num=False,
        **_base_sort_kwargs(),
    )
    loc = result.structure["locations"][0]
    assert loc["name"] == "1"
    assert loc["sublocations"][0]["name"] == "2"
    assert loc["sublocations"][0]["sublocations"][0]["name"] == "3"


def _flat_fixture_names(structure):
    """Collect fixture names from the first type in a flat location tree."""
    loc = structure["locations"][0]
    types = loc.get("types") or []
    if not types:
        return []
    fixtures = types[0].get("fixtures") or []
    return [f["name"] for f in fixtures]


def test_multi_serial_tag_matches_any_variant():
    location_levels = [{"tags": ["Building A"], "numeric": False}]
    photos = [
        _photo("serial", ["Building A", "Wallpack", "PART NUMBER", "Tech"]),
        _photo("normal", ["Building A", "Wallpack", "BEFORE", "Tech"]),
    ]
    result = sort_lighting_photos(
        photos,
        location_levels=location_levels,
        loc_bigger_num=False,
        installers=["Tech"],
        fixture_types=["Wallpack"],
        phases=["BEFORE"],
        serial_tag="SERIAL,PART NUMBER",
    )
    fixture_names = _flat_fixture_names(result.structure)
    assert "Serial-Tagged Fixture" in fixture_names


def test_empty_serial_tag_skips_serial_bucket():
    location_levels = [{"tags": ["Building A"], "numeric": False}]
    photos = [
        _photo("p1", ["Building A", "Wallpack", "SERIAL", "BEFORE", "Tech"]),
    ]
    result = sort_lighting_photos(
        photos,
        location_levels=location_levels,
        loc_bigger_num=False,
        installers=["Tech"],
        fixture_types=["Wallpack"],
        phases=["BEFORE"],
        serial_tag="",
    )
    fixture_names = _flat_fixture_names(result.structure)
    assert "Serial-Tagged Fixture" not in fixture_names


def test_case_insensitive_location_and_fixture_tags():
    location_levels = [
        {"tags": ["HALLWAYS"], "numeric": False},
    ]
    photos = [
        _photo(
            "p1",
            ["Hallways", "light switch", "Before", "Jesus Fierros"],
        ),
    ]
    result = sort_lighting_photos(
        photos,
        location_levels=location_levels,
        loc_bigger_num=False,
        installers=["Jesus Fierros"],
        fixture_types=["Light Switch"],
        phases=["Before"],
        serial_tag="",
    )
    assert result.structure["untagged"] == []
    loc = result.structure["locations"][0]
    assert loc["name"] == "HALLWAYS"
    assert loc["types"][0]["name"] == "LIGHT SWITCH"


def test_sublocations_preserved_when_siblings_unmatched():
    location_levels = [
        {"tags": ["BUILDING 1"], "numeric": False},
        {"tags": ["STAIRWAY 1", "HALLWAY"], "numeric": False},
        {"tags": ["1ST FLOOR"], "numeric": False},
    ]
    photos = [
        _photo(
            "matched",
            ["BUILDING 1", "STAIRWAY 1", "1ST FLOOR", "Wallpack", "BEFORE", "Tech"],
        ),
        _photo(
            "unmatched",
            ["BUILDING 1", "1ST FLOOR", "Wallpack", "BEFORE", "Tech"],
        ),
    ]
    result = sort_lighting_photos(
        photos,
        location_levels=location_levels,
        loc_bigger_num=False,
        **_base_sort_kwargs(),
    )

    assert count_structure_photos(result.structure) == 2
    loc = result.structure["locations"][0]
    assert loc["name"] == "BUILDING 1"
    stairway_names = [sub["name"] for sub in loc.get("sublocations", [])]
    assert "STAIRWAY 1" in stairway_names


def test_case_insensitive_sublocation_tags():
    location_levels = [
        {"tags": ["BUILDING 1"], "numeric": False},
        {"tags": ["STAIRWAY 1"], "numeric": False},
        {"tags": ["1ST FLOOR"], "numeric": False},
    ]
    photos = [
        _photo(
            "p1",
            ["building 1", "stairway 1", "1st floor", "wallpack", "before", "tech"],
        ),
    ]
    result = sort_lighting_photos(
        photos,
        location_levels=location_levels,
        loc_bigger_num=False,
        installers=["Tech"],
        fixture_types=["Wallpack"],
        phases=["Before"],
        serial_tag="",
    )
    loc = result.structure["locations"][0]
    assert loc["name"] == "BUILDING 1"
    assert loc["sublocations"][0]["name"] == "STAIRWAY 1"
    assert loc["sublocations"][0]["sublocations"][0]["name"] == "1ST FLOOR"
