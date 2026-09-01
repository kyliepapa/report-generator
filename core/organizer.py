"""
Photo organization.

organize_photos() builds the nested dict structure the HTML/PDF
generators walk over. analyze_missing_photos() flags hierarchy nodes
missing BEFORE/AFTER coverage. build_unit_bathroom_map() precomputes a
unit -> single-sub-unit lookup used to backfill unassigned photos.

Relocated from newreport.py with these generalizations:
  - BATHROOM_ORDER          -> core.config.SUB_UNIT_ORDER
  - PHASE_ORDER              -> core.config.get_phase_order()
  - SPECIAL_ROOMS_NORMALIZED -> core.config.SPECIAL_ROOMS_NORMALIZED
  - the hardcoded "Bathroom" text in build_used_tag_string() ->
    the active dataset's sub_unit_label_singular

All branching on SORT_METHOD_KEY's 4 literal strings is unchanged --
see datasets/base.py for why those are a structural contract shared
with core/sort_engine.py, not something this file can generalize away
on its own.
"""

from collections import defaultdict

import core.config as config
from core.photo_urls import resolve_image_urls
from core.sort_engine import get_sort_key
from core.tag_parser import get_special_room_match, title_case_tag_text


# ─────────────────────────────────────────
# UNIT -> SINGLE SUB-UNIT MAP
# (was build_unit_bathroom_map)
# ─────────────────────────────────────────
def build_unit_bathroom_map(photos):
    """
    Kept its original name (used throughout app.py / web routes as
    build_unit_bathroom_map) even though it now operates on the
    generic SUB_UNIT_ORDER, to avoid a rename that would ripple into
    every call site before those are refactored too.
    """
    from core.tag_parser import parse_bldg_unit

    unit_bathrooms = defaultdict(set)

    for p in photos:
        tags_clean = [t.strip().upper() for t in p.get("tag_names", [])]
        bldg, unit = parse_bldg_unit(tags_clean)
        bath_idx = next(
            (i for i, b in enumerate(config.SUB_UNIT_ORDER)
             if any(b.upper() in tag for tag in tags_clean)),
            -1
        )
        if unit != "UNASSIGNED" and bath_idx != -1:
            unit_bathrooms[unit].add(bath_idx)

    unit_to_single_bath = {}
    for unit, baths in unit_bathrooms.items():
        if len(baths) == 1:
            unit_to_single_bath[unit] = list(baths)[0]

    return unit_to_single_bath


# ─────────────────────────────────────────
# TAG STRING HELPERS
# (was in the "PDF HELPER FUNCTIONS" section, but organize_photos()
#  depends on them directly, so they live next to their caller now
#  instead of ~1700 lines away in the same file)
# ─────────────────────────────────────────
def title_case_tag(tag):
    return title_case_tag_text(tag)


def build_used_tag_string(bldg, unit, bath, phase):
    dataset = config._require_dataset()
    sub_unit_label = dataset.sub_unit_label_singular

    parts = []
    if bldg and bldg not in ("NO_BLDG", "00"):
        parts.append(f"Building {bldg}")
    if unit and unit != "UNASSIGNED":
        parts.append(f"Unit {unit}")
    if bath and bath != "OTHER":
        parts.append(f"{title_case_tag_text(bath)} {sub_unit_label}")
    if phase and phase != "UNTAGGED":
        parts.append(title_case_tag_text(phase))
    return " — ".join(parts)


def separate_extra_tags(all_tags, used_parts):
    used_words = set(" ".join(str(p) for p in used_parts if p).upper().split())
    extras = []
    for t in all_tags:
        words = t.upper().split()
        if not any(w in used_words for w in words):
            extras.append(title_case_tag(t))
    return ", ".join(sorted(extras))


# ─────────────────────────────────────────
# ORGANIZE PHOTOS
# ─────────────────────────────────────────
def organize_photos(photos, unit_bath_map=None):
    def make_structure():
        if config.SORT_METHOD_KEY == "full":
            return defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(list))))
        elif config.SORT_METHOD_KEY == "bldg_unit_phase":
            return defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
        elif config.SORT_METHOD_KEY == "unit_bath_phase":
            return defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
        else:
            return defaultdict(lambda: defaultdict(list))

    structure = make_structure()
    special_rooms_structure = defaultdict(lambda: defaultdict(list))
    skipped_no_url = 0
    skipped_no_uris = 0

    phase_order = config.get_phase_order()

    def get_phase_label(idx):
        return phase_order[idx] if isinstance(idx, int) and 0 <= idx < len(phase_order) else "UNTAGGED"

    def get_bath_label(idx):
        return config.SUB_UNIT_ORDER[idx] if isinstance(idx, int) and 0 <= idx < len(config.SUB_UNIT_ORDER) else "OTHER"

    def normalize_unit(unit):
        if unit == "UNASSIGNED":
            return unit
        if isinstance(unit, str) and unit.isdigit():
            return unit.zfill(3)
        return unit

    def normalize_bldg(bldg):
        return bldg if bldg != "00" else "NO_BLDG"

    for p in photos:
        tags_clean = [t.strip().upper() for t in p.get("tag_names", [])]

        if config.SPECIAL_ROOMS_NORMALIZED:
            room_name = get_special_room_match(tags_clean)
            if room_name:
                phase_idx = next((i for i, n in enumerate(phase_order) if n in tags_clean), -1)
                phase_key = phase_order[phase_idx] if 0 <= phase_idx < len(phase_order) else "UNTAGGED"
                photo_url, original_url = resolve_image_urls(p)
                coordinates = p.get("coordinates", {})
                all_tags = p.get("tag_names", [])
                photo_data = {
                    "url": photo_url or "https://via.placeholder.com/200x180/cccccc/666666?text=No+Image",
                    "original_url": original_url,
                    "captured_at": p.get("captured_at"),
                    "latitude": coordinates.get("lat"),
                    "longitude": coordinates.get("lon"),
                    "has_image": photo_url is not None,
                    "all_tags": all_tags,
                    "tag_string": room_name,
                    "extra_tags": "",
                }
                special_rooms_structure[room_name][phase_key].append(photo_data)
                if not p.get("uris"):
                    skipped_no_uris += 1
                elif not photo_url:
                    skipped_no_url += 1
                continue

        sort_result = get_sort_key(p, unit_bath_map)

        if config.SORT_METHOD_KEY == "full":
            bldg, unit, unassigned_priority, bath_idx, phase_idx = sort_result
            bldg_key = normalize_bldg(bldg)
            unit_key = normalize_unit(unit)
            bath_key = get_bath_label(bath_idx)
            phase_key = get_phase_label(phase_idx)
        elif config.SORT_METHOD_KEY == "bldg_unit_phase":
            bldg, unit, phase_idx = sort_result
            bldg_key = normalize_bldg(bldg)
            unit_key = normalize_unit(unit)
            phase_key = get_phase_label(phase_idx)
        elif config.SORT_METHOD_KEY == "unit_bath_phase":
            unit, unassigned_priority, bath_idx, phase_idx = sort_result
            unit_key = normalize_unit(unit)
            bath_key = get_bath_label(bath_idx)
            phase_key = get_phase_label(phase_idx)
        else:
            unit, phase_idx, _ = sort_result
            unit_key = normalize_unit(unit)
            phase_key = get_phase_label(phase_idx)

        photo_url, original_url = resolve_image_urls(p)
        coordinates = p.get("coordinates", {})
        all_tags = p.get("tag_names", [])

        photo_data = {
            "url": photo_url or "https://via.placeholder.com/200x180/cccccc/666666?text=No+Image",
            "original_url": original_url,
            "captured_at": p.get("captured_at"),
            "latitude": coordinates.get("lat"),
            "longitude": coordinates.get("lon"),
            "has_image": photo_url is not None,
            "all_tags": all_tags,
            "tag_string": "",
            "extra_tags": ""
        }

        if config.SORT_METHOD_KEY == "full":
            photo_data["tag_string"] = build_used_tag_string(bldg_key, unit_key, bath_key, phase_key)
            photo_data["extra_tags"] = separate_extra_tags(all_tags, [bldg_key, unit_key, bath_key, phase_key])
            structure[bldg_key][unit_key][bath_key][phase_key].append(photo_data)
        elif config.SORT_METHOD_KEY == "bldg_unit_phase":
            photo_data["tag_string"] = build_used_tag_string(bldg_key, unit_key, None, phase_key)
            photo_data["extra_tags"] = separate_extra_tags(all_tags, [bldg_key, unit_key, phase_key])
            structure[bldg_key][unit_key][phase_key].append(photo_data)
        elif config.SORT_METHOD_KEY == "unit_bath_phase":
            photo_data["tag_string"] = build_used_tag_string(None, unit_key, bath_key, phase_key)
            photo_data["extra_tags"] = separate_extra_tags(all_tags, [unit_key, bath_key, phase_key])
            structure[unit_key][bath_key][phase_key].append(photo_data)
        else:
            photo_data["tag_string"] = build_used_tag_string(None, unit_key, None, phase_key)
            photo_data["extra_tags"] = separate_extra_tags(all_tags, [unit_key, phase_key])
            structure[unit_key][phase_key].append(photo_data)

        if not p.get("uris"):
            skipped_no_uris += 1
        elif not photo_url:
            skipped_no_url += 1

    print(f"[*] Photos processed: {len(photos)}")
    print(f"[*] Skipped (no URIs): {skipped_no_uris}")
    print(f"[*] Skipped (no valid URL): {skipped_no_url}")

    return structure, special_rooms_structure


# ─────────────────────────────────────────
# MISSING PHOTO ANALYSIS
# ─────────────────────────────────────────
def _other_bath_is_active(phases_dict):
    return bool(phases_dict.get("BEFORE") or phases_dict.get("AFTER"))


def analyze_missing_photos(structure):
    missing = {"BEFORE": [], "AFTER": []}

    def check(label, phases_dict, is_other=False):
        # Skip UNASSIGNED / UNTAGGED sections entirely
        if "UNASSIGNED" in label or "UNTAGGED" in label:
            return

        if is_other and not _other_bath_is_active(phases_dict):
            return

        for phase in ["BEFORE", "AFTER"]:
            if not phases_dict.get(phase):
                missing[phase].append(label)

    if config.SORT_METHOD_KEY == "full":
        for bldg in sorted(structure):
            for unit in sorted(structure[bldg]):
                for bath in sorted(structure[bldg][unit]):
                    lbl = f"Bldg {bldg} / Unit {unit} / {bath}"
                    check(lbl, structure[bldg][unit][bath], is_other=(bath == "OTHER"))

    elif config.SORT_METHOD_KEY == "bldg_unit_phase":
        for bldg in sorted(structure):
            for unit in sorted(structure[bldg]):
                lbl = f"Bldg {bldg} / Unit {unit}"
                check(lbl, structure[bldg][unit])

    elif config.SORT_METHOD_KEY == "unit_bath_phase":
        for unit in sorted(structure):
            for bath in sorted(structure[unit]):
                lbl = f"Unit {unit} / {bath}"
                check(lbl, structure[unit][bath], is_other=(bath == "OTHER"))

    else:
        for unit in sorted(structure):
            lbl = f"Unit {unit}"
            check(lbl, structure[unit])

    return missing