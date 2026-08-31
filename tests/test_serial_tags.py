"""Tests for multi serial-tag parsing and heat pump matching."""

from core.tag_parser import parse_serial_tags
from datasets.heat_pump.sort import sort_heat_pump_photos


def test_parse_serial_tags_from_string():
    assert parse_serial_tags("SERIAL, PART NUMBER") == ["SERIAL", "PART NUMBER"]


def test_parse_serial_tags_from_list():
    assert parse_serial_tags(["SERIAL", "PART NUMBER"]) == ["SERIAL", "PART NUMBER"]


def test_parse_serial_tags_empty():
    assert parse_serial_tags("") == []
    assert parse_serial_tags([]) == []


def test_heat_pump_multi_serial_tag():
    photos = [{"photo_id": "p1", "tag_names": ["BEFORE", "PART NUMBER"]}]
    result = sort_heat_pump_photos(
        photos,
        fixtures=[],
        serial_tag="SERIAL,PART NUMBER",
    )
    before_serial = result.structure["buckets"][0]["photos"]
    assert len(before_serial) == 1


def test_heat_pump_empty_serial_tag():
    photos = [{"photo_id": "p1", "tag_names": ["BEFORE", "SERIAL"]}]
    result = sort_heat_pump_photos(
        photos,
        fixtures=[],
        serial_tag="",
    )
    before = result.structure["buckets"][1]["photos"]
    assert len(before) == 1
    assert not result.structure["buckets"][0]["photos"]
