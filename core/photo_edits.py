"""
Drag-and-drop edit applicator.

Relocated verbatim from app.py (it was living in the Flask file despite
being pure structure-manipulation logic with no route/request
dependency). No changes -- sort_mode is passed in as a parameter, not
read off a global, so this needed zero rewiring to move.

Still branches on the same 4 SORT_METHOD_KEY literal strings as
core/organizer.py and core/sort_engine.py -- see datasets/base.py for
why. zone_id parsing here is also coupled to script.js's zone-ID
construction (parts split on "__"); that coupling isn't addressed in
this pass.
"""


import logging
from urllib.parse import unquote

logger = logging.getLogger(__name__)

LIGHTING_SORT_KEY = "location_sublocation_type_fixture_phase"


def _normalize_photo_url(url):
    """Align browser img.src with backend uri lookup (trim, decode, no trailing slash)."""
    if not url or not isinstance(url, str):
        return ""
    return unquote(url.strip()).rstrip("/")


def _register_photo_url(url, photo, mapping):
    if not url:
        return
    mapping[url] = photo
    norm = _normalize_photo_url(url)
    if norm and norm != url:
        mapping[norm] = photo


def _resolve_photo_url(url, mapping):
    if not url:
        return None
    photo = mapping.get(url)
    if photo is not None:
        return photo
    return mapping.get(_normalize_photo_url(url))


def _resolve_ordered_photos(ordered_urls, url_to_photo, zone_id=""):
    ordered_photos = []
    seen_ids = set()
    for u in ordered_urls or []:
        if not u or (isinstance(u, str) and u.startswith("heading:")):
            continue
        photo = _resolve_photo_url(u, url_to_photo)
        if photo is None:
            logger.warning(
                "Lighting edit: URL not in sorted structure for zone %r: %r",
                zone_id,
                u,
            )
            continue
        pid = id(photo)
        if pid not in seen_ids:
            seen_ids.add(pid)
            ordered_photos.append(photo)
    return ordered_photos


def _all_photo_urls(p):
    """Every known URI for a photo so browser img.src can match any variant."""
    urls = []
    if isinstance(p, dict):
        if p.get("url"):
            urls.append(p["url"])
        uris = p.get("uris", [])
    elif hasattr(p, "data") and isinstance(p.data, dict):
        if p.data.get("url"):
            urls.append(p.data["url"])
        uris = p.data.get("uris", [])
    else:
        uris = []

    if isinstance(uris, list):
        for u in uris:
            if isinstance(u, dict) and u.get("url"):
                urls.append(u["url"])

    primary = _lighting_photo_url(p)
    if primary:
        urls.append(primary)
    return urls


def _edited_url_keys(photo_edits):
    """All normalized URLs appearing anywhere in the edit payload."""
    keys = set()
    for ordered_urls in photo_edits.values():
        for u in ordered_urls or []:
            if not u or (isinstance(u, str) and u.startswith("heading:")):
                continue
            keys.add(u)
            norm = _normalize_photo_url(u)
            if norm:
                keys.add(norm)
    return keys


def _lighting_photo_url(p):
    """
    Must resolve to the SAME url that _lighting_photo_dict() (in
    reporting/html/generators.py) put on the rendered photo card --
    that's the url the browser actually displays, drags, and sends back
    in photo_edits. Previously this picked whichever uri happened to
    come first in CompanyCam's uris list, regardless of type; whenever
    that wasn't the "web" entry, url_to_photo ended up keyed by a url
    the frontend never sends, and the photo silently vanished from
    every edit that touched its zone. Must stay in sync with
    _lighting_photo_dict's preference order: "web" first, "original" as
    fallback.
    """
    if not p:
        return ""
    if isinstance(p, dict):
        url = p.get("url")
        if url:
            return url
        uris = p.get("uris", [])
    elif hasattr(p, "data") and isinstance(p.data, dict):
        uris = p.data.get("uris", [])
    else:
        return ""

    if not isinstance(uris, list):
        return ""

    for u in uris:
        if isinstance(u, dict) and u.get("type") == "web" and u.get("url"):
            return u["url"]
    for u in uris:
        if isinstance(u, dict) and u.get("type") == "original" and u.get("url"):
            return u["url"]

    if isinstance(p, dict):
        return ""
    return p.data.get("url", "")


def apply_lighting_photo_edits(structured, photo_edits, measure_id=None):
    if not photo_edits or not isinstance(structured, dict):
        return

    url_to_photo = {}

    def _collect_p(p):
        seen = set()
        for url in _all_photo_urls(p):
            if url and url not in seen:
                seen.add(url)
                _register_photo_url(url, p, url_to_photo)

    def _collect_group(group):
        if not isinstance(group, dict):
            return
        for t in group.get("types", []):
            for f in t.get("fixtures", []):
                for p in f.get("photos", []):
                    _collect_p(p)
            for p in t.get("untagged", []):
                _collect_p(p)
        for sub in group.get("sublocations", []):
            _collect_group(sub)
        for p in group.get("untagged", []):
            _collect_p(p)

    for loc in structured.get("locations", []):
        _collect_group(loc)
    for p in structured.get("untagged", []):
        _collect_p(p)

    def _match_name(node_list, name):
        name_clean = name.replace("_", " ").lower()
        for node in node_list:
            if isinstance(node, dict) and node.get("name", "").replace("_", " ").lower() == name_clean:
                return node
        return None

    # Fixture phase zones are accumulated first, then reassembled once per
    # fixture so cross-zone drags are honored by DOM position, not tags.
    fixture_edits = {}
    all_edited_urls = _edited_url_keys(photo_edits)

    for zone_id, ordered_urls in photo_edits.items():
        ordered_photos = _resolve_ordered_photos(ordered_urls, url_to_photo, zone_id)
        # Must match _zone_id's join delimiter in shared_components.py exactly.
        # See that function's docstring for why this can't be "__".
        parts = zone_id.split("\x1f")

        if measure_id is not None:
            if parts[0].lower() == str(measure_id).lower():
                parts = parts[1:]
            elif parts[0].lower() not in ("top", "loc"):
                continue
        elif parts[0] not in ("top", "loc") and len(parts) > 1 and parts[1] in ("top", "loc"):
            parts = parts[1:]

        if not parts:
            continue

        if parts[0] == "top" and len(parts) > 1 and parts[1] == "untagged":
            structured["untagged"] = ordered_photos
            continue

        if parts[0] == "loc" and len(parts) >= 3:
            loc = _match_name(structured.get("locations", []), parts[1])
            if not loc:
                logger.warning(
                    "Lighting edit: location not found for zone %r (name=%r)",
                    zone_id,
                    parts[1],
                )
                continue

            idx = 2
            curr_group = loc

            while idx < len(parts) and parts[idx] == "sub" and idx + 1 < len(parts):
                sub = _match_name(curr_group.get("sublocations", []), parts[idx + 1])
                if not sub:
                    logger.warning(
                        "Lighting edit: sublocation not found for zone %r (name=%r)",
                        zone_id,
                        parts[idx + 1],
                    )
                    curr_group = None
                    break
                curr_group = sub
                idx += 2

            if curr_group is None:
                continue

            if idx >= len(parts):
                continue

            if parts[idx] == "untagged":
                curr_group["untagged"] = ordered_photos
            elif parts[idx] == "type" and idx + 1 < len(parts):
                type_group = _match_name(curr_group.get("types", []), parts[idx + 1])
                if not type_group:
                    logger.warning(
                        "Lighting edit: type not found for zone %r (name=%r)",
                        zone_id,
                        parts[idx + 1],
                    )
                    continue
                idx += 2
                if idx >= len(parts):
                    continue

                if parts[idx] == "untagged":
                    type_group["untagged"] = ordered_photos
                elif parts[idx] == "serial":
                    fixture = next(
                        (f for f in type_group.get("fixtures", []) if f.get("name") == "Serial-Tagged Fixture"),
                        None,
                    )
                    if fixture is None and ordered_photos:
                        fixture = {"name": "Serial-Tagged Fixture", "photos": []}
                        type_group.setdefault("fixtures", []).insert(0, fixture)
                    if fixture:
                        fixture["photos"] = ordered_photos
                    elif ordered_photos:
                        logger.warning(
                            "Lighting edit: serial fixture missing for zone %r",
                            zone_id,
                        )
                elif parts[idx] == "fixture" and idx + 1 < len(parts):
                    fixture = _match_name(type_group.get("fixtures", []), parts[idx + 1])
                    if fixture:
                        phase = parts[idx + 2] if idx + 2 < len(parts) else None
                        if phase:
                            fid = id(fixture)
                            if fid not in fixture_edits:
                                fixture_edits[fid] = {
                                    "fixture": fixture,
                                    "order": [],
                                    "phases": {},
                                    "original_photos": list(fixture.get("photos") or []),
                                }
                            bucket = fixture_edits[fid]
                            if phase not in bucket["phases"]:
                                bucket["order"].append(phase)
                            bucket["phases"][phase] = ordered_photos
                        else:
                            fixture["photos"] = ordered_photos
                    else:
                        logger.warning(
                            "Lighting edit: fixture not found for zone %r (name=%r)",
                            zone_id,
                            parts[idx + 1],
                        )

    for bucket in fixture_edits.values():
        fixture = bucket["fixture"]
        reassembled = [
            p for phase in bucket["order"] for p in bucket["phases"][phase]
        ]
        placed = {
            _normalize_photo_url(_lighting_photo_url(p)) for p in reassembled
        }
        placed.discard("")
        for p in bucket.get("original_photos") or []:
            key = _normalize_photo_url(_lighting_photo_url(p))
            if key and key not in placed and key not in all_edited_urls:
                reassembled.append(p)
                placed.add(key)
        fixture["photos"] = reassembled


SUBCONTRACTED_SORT_KEY = "subcontracted_sequence"
HEAT_PUMP_SORT_KEY = "heat_pump_phase_serial_buckets"
MANUAL_ARRANGE_SORT_KEY = "manual_arrange_sequence"


def apply_heat_pump_photo_edits(structured, photo_edits, measure_id=None):
    if not photo_edits or not isinstance(structured, dict):
        return

    url_to_photo = {}

    def _collect_p(p):
        url = _lighting_photo_url(p)
        if url:
            url_to_photo[url] = p

    def _collect_location(loc):
        for bucket in loc.get("buckets", []):
            for p in bucket.get("photos", []):
                _collect_p(p)
        for p in loc.get("untagged", []):
            _collect_p(p)

    for loc in structured.get("locations", []):
        _collect_location(loc)
    for bucket in structured.get("buckets", []):
        for p in bucket.get("photos", []):
            _collect_p(p)
    for p in structured.get("untagged", []):
        _collect_p(p)

    def _match_name(node_list, name):
        name_clean = name.replace("_", " ").lower()
        for node in node_list:
            if isinstance(node, dict) and node.get("name", "").replace("_", " ").lower() == name_clean:
                return node
        return None

    bucket_by_key = {b.get("key"): b for b in structured.get("buckets", [])}

    for zone_id, ordered_urls in photo_edits.items():
        ordered_photos = [url_to_photo[u] for u in ordered_urls if u in url_to_photo]
        parts = zone_id.split("\x1f")

        if measure_id is not None:
            if parts[0].lower() == str(measure_id).lower():
                parts = parts[1:]
            elif parts[0] not in ("bucket", "untagged", "loc"):
                continue
        elif parts and parts[0] not in ("bucket", "untagged", "loc"):
            continue

        if not parts:
            continue

        if parts[0] == "untagged":
            structured["untagged"] = ordered_photos
            continue

        if parts[0] == "loc" and len(parts) > 1:
            loc = _match_name(structured.get("locations", []), parts[1])
            if loc is None:
                continue
            sub_parts = parts[2:]
            if not sub_parts:
                continue
            if sub_parts[0] == "untagged":
                loc["untagged"] = ordered_photos
                continue
            if sub_parts[0] == "bucket" and len(sub_parts) > 1:
                loc_buckets = {b.get("key"): b for b in loc.get("buckets", [])}
                bucket = loc_buckets.get(sub_parts[1])
                if bucket is not None:
                    bucket["photos"] = ordered_photos
            continue

        if parts[0] == "bucket" and len(parts) > 1:
            bucket = bucket_by_key.get(parts[1])
            if bucket is not None:
                bucket["photos"] = ordered_photos


def apply_subcontracted_photo_edits(structured, photo_edits, heading_edits=None, measure_id=None):
    if not photo_edits or not isinstance(structured, dict):
        return

    existing_headings = {}
    url_to_item = {}
    for item in structured.get("items", []):
        if item.get("type") == "heading":
            existing_headings[item.get("id")] = item
        elif item.get("type") == "photo":
            url = _lighting_photo_url(item.get("photo"))
            if url:
                url_to_item[url] = item

    heading_edits = heading_edits or {}

    for zone_id, ordered_tokens in photo_edits.items():
        parts = zone_id.split("\x1f")

        if measure_id is not None:
            if parts[0].lower() == str(measure_id).lower():
                parts = parts[1:]
            elif parts[0].lower() != "sub":
                continue
        elif parts and parts[0] != "sub":
            continue

        if not parts or parts[0] != "sub":
            continue

        new_items = []
        for token in ordered_tokens:
            if isinstance(token, str) and token.startswith("heading:"):
                hid = token[8:]
                he = heading_edits.get(hid, {})
                prev = existing_headings.get(hid, {})
                new_items.append({
                    "type": "heading",
                    "id": hid,
                    "text": he.get("text", prev.get("text", "")),
                    "weight": he.get("weight", prev.get("weight", "medium")),
                })
            elif token in url_to_item:
                new_items.append(url_to_item[token])

        structured["items"] = new_items


def apply_manual_arrange_photo_edits(structured, photo_edits, heading_edits=None, measure_id=None):
    if not photo_edits or not isinstance(structured, dict):
        return

    existing_headings = {}
    url_to_item = {}
    for item in structured.get("staging_items", []):
        if item.get("type") == "heading":
            existing_headings[item.get("id")] = item
        elif item.get("type") == "photo":
            url = _lighting_photo_url(item.get("photo"))
            if url:
                url_to_item[url] = item

    url_to_photo = {}
    bucket_by_key = {b.get("key"): b for b in structured.get("buckets", [])}
    for item in structured.get("staging_items", []):
        if item.get("type") == "photo":
            p = item.get("photo")
            url = _lighting_photo_url(p)
            if url:
                url_to_photo[url] = p
    for bucket in structured.get("buckets", []):
        for p in bucket.get("photos", []):
            url = _lighting_photo_url(p)
            if url:
                url_to_photo[url] = p

    heading_edits = heading_edits or {}

    for zone_id, ordered_tokens in photo_edits.items():
        parts = zone_id.split("\x1f")

        if measure_id is not None:
            if parts[0].lower() == str(measure_id).lower():
                parts = parts[1:]
            elif parts[0].lower() not in ("staging", "bucket"):
                continue
        elif parts and parts[0] not in ("staging", "bucket"):
            continue

        if not parts:
            continue

        if parts[0] == "staging":
            new_items = []
            for token in ordered_tokens:
                if isinstance(token, str) and token.startswith("heading:"):
                    hid = token[8:]
                    he = heading_edits.get(hid, {})
                    prev = existing_headings.get(hid, {})
                    new_items.append({
                        "type": "heading",
                        "id": hid,
                        "text": he.get("text", prev.get("text", "")),
                        "weight": he.get("weight", prev.get("weight", "medium")),
                    })
                elif token in url_to_item:
                    new_items.append(url_to_item[token])
                elif token in url_to_photo:
                    new_items.append({"type": "photo", "photo": url_to_photo[token]})
            structured["staging_items"] = new_items
            continue

        if parts[0] == "bucket" and len(parts) > 1:
            bucket = bucket_by_key.get(parts[1])
            if bucket is not None:
                ordered_photos = [
                    url_to_photo[u] for u in ordered_tokens
                    if isinstance(u, str) and u in url_to_photo
                ]
                bucket["photos"] = ordered_photos


def apply_photo_edits(structured, special_rooms_structured, photo_edits, sort_mode, measure_id=None, heading_edits=None):
    if not photo_edits:
        return

    if sort_mode == LIGHTING_SORT_KEY:
        apply_lighting_photo_edits(structured, photo_edits, measure_id=measure_id)
        return

    if sort_mode == SUBCONTRACTED_SORT_KEY:
        apply_subcontracted_photo_edits(
            structured, photo_edits, heading_edits=heading_edits, measure_id=measure_id,
        )
        return

    if sort_mode == HEAT_PUMP_SORT_KEY:
        apply_heat_pump_photo_edits(structured, photo_edits, measure_id=measure_id)
        return

    if sort_mode == MANUAL_ARRANGE_SORT_KEY:
        apply_manual_arrange_photo_edits(
            structured, photo_edits, heading_edits=heading_edits, measure_id=measure_id,
        )
        return

    url_to_photo = {}

    def _collect(phases_dict):
        for phase_list in phases_dict.values():
            for pd in phase_list:
                url_to_photo[pd["url"]] = pd

    if sort_mode == "full":
        for bldg in structured:
            for unit in structured[bldg]:
                for bath in structured[bldg][unit]:
                    _collect(structured[bldg][unit][bath])
    elif sort_mode == "bldg_unit_phase":
        for bldg in structured:
            for unit in structured[bldg]:
                _collect(structured[bldg][unit])
    elif sort_mode == "unit_bath_phase":
        for unit in structured:
            for bath in structured[unit]:
                _collect(structured[unit][bath])
    else:
        for unit in structured:
            _collect(structured[unit])

    for room in special_rooms_structured:
        _collect(special_rooms_structured[room])

    for zone_id, ordered_urls in photo_edits.items():
        # Must match _zone_id's join delimiter in shared_components.py exactly.
        parts = zone_id.split("\x1f")

        if measure_id is not None:
            if parts[0].lower() == str(measure_id).lower():
                parts = parts[1:]
            elif parts[0].lower() not in ("special", "unit", "bldg"):
                continue
        elif parts[0] not in ("special", "unit", "bldg") and len(parts) > 1 and parts[1] in ("special", "unit", "bldg"):
            parts = parts[1:]

        if not parts:
            continue

        phases_dict = None

        if parts[0] == "special":
            room = parts[1].replace("_", " ").title()
            matched_room = next(
                (r for r in special_rooms_structured if r.lower() == room.lower()),
                None
            )
            if matched_room:
                phases_dict = special_rooms_structured[matched_room]
                phase = parts[2]
        elif sort_mode == "unit_phase":
            unit  = parts[1]
            phase = parts[2]
            phases_dict = structured.get(unit)
        elif sort_mode == "bldg_unit_phase":
            bldg  = parts[1]
            unit  = parts[3]
            phase = parts[4]
            phases_dict = structured.get(bldg, {}).get(unit)
        elif sort_mode == "unit_bath_phase":
            unit  = parts[1]
            bath  = parts[3]
            phase = parts[4]
            phases_dict = structured.get(unit, {}).get(bath)
        elif sort_mode == "full":
            bldg  = parts[1]
            unit  = parts[3]
            bath  = parts[5]
            phase = parts[6]
            phases_dict = structured.get(bldg, {}).get(unit, {}).get(bath)

        if phases_dict is None:
            continue

        new_list = []
        for url in ordered_urls:
            pd = url_to_photo.get(url)
            if pd:
                new_list.append(pd)

        phases_dict[phase] = new_list


def _collect_all_photos(structured, special_rooms_structured=None):
    """Build url -> photo mapping by walking any sorted structure shape."""
    url_to_photo = {}

    def visit(node):
        if node is None:
            return
        if isinstance(node, dict):
            url = node.get("url") or _lighting_photo_url(node)
            if url:
                _register_photo_url(url, node, url_to_photo)
            for v in node.values():
                visit(v)
        elif isinstance(node, list):
            for item in node:
                visit(item)
        elif hasattr(node, "data"):
            for u in _all_photo_urls(node):
                _register_photo_url(u, node, url_to_photo)

    visit(structured)
    if special_rooms_structured:
        visit(special_rooms_structured)
    return url_to_photo


def apply_photo_tag_edits(structured, special_rooms_structured, tag_edits):
    """Apply session tag overrides from the HTML lightbox before PDF render."""
    if not tag_edits or not isinstance(tag_edits, dict):
        return

    url_map = _collect_all_photos(structured, special_rooms_structured)
    for url, tags in tag_edits.items():
        if not tags or not isinstance(tags, list):
            continue
        photo = _resolve_photo_url(url, url_map)
        if photo is None:
            logger.warning("Tag edit: URL not in structure: %r", url)
            continue
        clean = [str(t).strip() for t in tags if str(t).strip()]
        if isinstance(photo, dict):
            photo["session_tags"] = clean
            photo["all_tags"] = clean
            photo["extra_tags"] = ", ".join(clean)
        elif hasattr(photo, "tags"):
            photo.tags = clean
            if hasattr(photo, "data") and isinstance(photo.data, dict):
                photo.data["session_tags"] = clean
                photo.data["all_tags"] = clean
                photo.data["extra_tags"] = ", ".join(clean)
