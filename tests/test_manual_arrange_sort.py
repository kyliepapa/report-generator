"""Tests for manual arrange photo sorting."""

from datasets.manual_arrange.sort import sort_manual_arrange_photos


def _photo(photo_id, tags):
    return {"photo_id": photo_id, "tag_names": tags}


def test_no_buckets_all_staging():
    photos = [_photo("1", ["A"]), _photo("2", [])]
    result = sort_manual_arrange_photos(photos, pre_sort_buckets=[])
    assert len(result.structure["staging_items"]) == 2
    assert "buckets" not in result.structure


def test_single_bucket_match():
    photos = [_photo("1", ["BEFORE"]), _photo("2", ["OTHER"])]
    result = sort_manual_arrange_photos(photos, pre_sort_buckets=["BEFORE"])
    buckets = result.structure["buckets"]
    assert len(buckets[0]["photos"]) == 1
    assert len(result.structure["staging_items"]) == 1


def test_conflicting_tags_on_assigns_first_bucket():
    photos = [_photo("1", ["BEFORE", "AFTER"])]
    result = sort_manual_arrange_photos(
        photos,
        pre_sort_buckets=["BEFORE", "AFTER"],
        allow_conflicting_tags=True,
    )
    assert len(result.structure["buckets"][0]["photos"]) == 1
    assert len(result.structure["staging_items"]) == 0


def test_conflicting_tags_off_goes_to_staging():
    photos = [_photo("1", ["BEFORE", "AFTER"])]
    result = sort_manual_arrange_photos(
        photos,
        pre_sort_buckets=["BEFORE", "AFTER"],
        allow_conflicting_tags=False,
    )
    assert len(result.structure["staging_items"]) == 1
    assert len(result.structure["buckets"][0]["photos"]) == 0
    assert len(result.structure["buckets"][1]["photos"]) == 0
