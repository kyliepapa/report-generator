"""Tests for geotag preservation and manual-arrange edit fixes."""

from core.photo_edits import apply_manual_arrange_photo_edits
from reporting.html.generators import _subcontract_photo_dict, _unknown_photo_dict


def _slim_photo(url, lat, lon):
    return {
        "url": url,
        "original_url": url,
        "has_image": True,
        "captured_at": 1700000000,
        "latitude": lat,
        "longitude": lon,
    }


def test_subcontract_photo_dict_passthrough_slim_cache():
    slim = _slim_photo("https://example.com/a.jpg", 33.74, -117.99)
    assert _subcontract_photo_dict(slim) is slim


def test_subcontract_photo_dict_reads_top_level_coords():
    raw = {
        "url": "https://example.com/b.jpg",
        "original_url": "https://example.com/b.jpg",
        "latitude": 40.0,
        "longitude": -74.0,
        "captured_at": 1700000000,
    }
    out = _subcontract_photo_dict(raw)
    assert out["latitude"] == 40.0
    assert out["longitude"] == -74.0


def test_subcontract_photo_dict_reads_nested_coordinates():
    raw = {
        "uris": [{"type": "web", "url": "https://example.com/c.jpg"}],
        "coordinates": {"lat": 34.5, "lon": -118.2},
        "captured_at": 1700000001,
    }
    out = _subcontract_photo_dict(raw)
    assert out["latitude"] == 34.5
    assert out["longitude"] == -118.2


def test_unknown_photo_dict_reads_top_level_coords():
    slim = _slim_photo("https://example.com/d.jpg", 0.0, 10.0)
    out = _unknown_photo_dict(slim)
    assert out is slim


def test_manual_arrange_staging_to_bucket_edit():
    staging_photo = _slim_photo("https://example.com/staging.jpg", 1.0, 2.0)
    bucket_photo = _slim_photo("https://example.com/bucket.jpg", 3.0, 4.0)
    structured = {
        "staging_items": [{"type": "photo", "photo": staging_photo}],
        "buckets": [
            {"key": "BEFORE", "label": "BEFORE", "photos": [bucket_photo]},
        ],
    }
    zone_staging = "m1\x1fstaging"
    zone_bucket = "m1\x1fbucket\x1fBEFORE"
    photo_edits = {
        zone_staging: [],
        zone_bucket: [
            "https://example.com/bucket.jpg",
            "https://example.com/staging.jpg",
        ],
    }
    apply_manual_arrange_photo_edits(
        structured, photo_edits, measure_id="m1",
    )
    assert structured["staging_items"] == []
    assert len(structured["buckets"][0]["photos"]) == 2
    assert structured["buckets"][0]["photos"][1]["url"] == staging_photo["url"]
