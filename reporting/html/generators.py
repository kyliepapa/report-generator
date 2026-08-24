"""
HTML report generators.

Four functions, one per SORT_METHOD_KEY structural shape (see
datasets/base.py for why those 4 shapes are a shared contract with
core/organizer.py and core/sort_engine.py). Relocated from
newreport.py's "HTML GENERATORS (ALL MODES)" section verbatim --
per the decision to keep these as 4 separate functions for now rather
than collapse them into one generic hierarchy-walker. That collapse is
still a good idea later; this pass is a pure relocation.

Changes from the original, all mechanical:
  - PROJECT_NAME / PROJECT_ID   -> core.config.PROJECT_NAME / .PROJECT_ID
  - PHASE_ORDER                  -> core.config.get_phase_order()
  - OUTPUT_FILE                  -> core.paths.OUTPUT_FILE
  - PDF_BUTTON_HTML               -> assets.get_pdf_button_html()
  - _make_head/_make_tail/_phase_section/_zone_id -> imported from
    reporting.html.shared_components

Multi-measure tabbed report (generate_html_report):
  Each of the four shape generators, plus lighting, has been split
  into a "_render_*" function (body only -- summary/content/special
  rooms, no <head>/report-header/<tail>, no file write) and a thin
  "generate_html_*" wrapper that keeps the original single-measure
  signature/behavior (head + render + tail + write-to-OUTPUT_FILE)
  unchanged. generate_html_report() is the new multi-measure
  entrypoint: one shared head/report-header/tail, one tab per measure
  (rendered via its own shape's _render_* function so per-shape layout
  logic is untouched), plus an auto "Unknown Measure" tab for photos
  that matched no measure during classification (flat bucket, no
  further sectioning -- same treatment as an Untagged zone).

  zone_prefix: every _zone_id(...) call inside the _render_* functions
  (and the lighting render chain, which already threaded a zone_prefix
  tuple) now takes/passes a zone_prefix so two measures of the same
  shape/type in one report don't collide on the same data-zone id
  (which would confuse drag_drop.js's injectEmptyZones(), which scans
  data-zone document-wide). Single-measure callers (generate_html_*)
  pass no zone_prefix, defaulting to "" -- _zone_id() already filters
  falsy parts, so existing single-report zone IDs are byte-for-byte
  unchanged. generate_html_report() passes each measure's id as its
  zone_prefix (the same id already used as the dict key in
  sorted_data["measures"] and job_manager.save_sorted_structure).
"""

import re
from datetime import datetime

import core.config as config
import core.paths as paths
from reporting.html import assets
from reporting.html.shared_components import _make_head, _make_tail, _phase_section, _zone_id, make_photo_card_html, _photo_grid


# ============================================================
# UNIT_PHASE
# ============================================================
def _render_unit_phase(structure, special_rooms_structure=None, zone_prefix=""):
    total_units = len(structure)
    total_photos = sum(len(ph) for u in structure.values() for ph in u.values())
    phase_order = config.get_phase_order()

    html = f"""<div class="summary">
        <div class="summary-item"><span class="number">{total_units}</span><div class="label">Units</div></div>
        <div class="summary-item"><span class="number">{total_photos}</span><div class="label">Photos</div></div>
    </div>
    <div class="content">"""

    for unit in sorted(structure, key=lambda u: (u == "UNASSIGNED", u)):
        html += f'<div class="unit-section"><div class="unit-header">🏠 Unit {unit}</div>'
        html += '<div class="unit-phases" style="padding:20px;">'
        for phase in phase_order:
            photos = structure[unit].get(phase, [])
            if phase == "UNTAGGED" and not photos:
                continue
            zid = _zone_id(zone_prefix, "unit", unit, phase)
            html += _phase_section(photos, phase, zid)
        html += '</div></div>'

    html += generate_special_rooms_html(special_rooms_structure or {}, zone_prefix=zone_prefix)
    html += '</div>'
    return html


def generate_html_unit_phase(structure, special_rooms_structure=None):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    title = config.PROJECT_NAME or config.PROJECT_ID

    html = _make_head(title)
    html += f"""<div class="container">
        <div class="report-header">
            <h1>{title}</h1>
            <div class="meta">Generated {now}</div>
            {assets.get_pdf_button_html()}
        </div>
        {_render_unit_phase(structure, special_rooms_structure)}
    </div>{_make_tail()}"""
    with open(paths.OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)


# ============================================================
# BLDG_UNIT_PHASE
# ============================================================
def _render_bldg_unit_phase(structure, special_rooms_structure=None, zone_prefix=""):
    total_buildings = len(structure)
    total_units = sum(len(units) for units in structure.values())
    total_photos = sum(len(photos) for units in structure.values()
                       for phases in units.values() for photos in phases.values())
    phase_order = config.get_phase_order()

    html = f"""<div class="summary">
        <div class="summary-item"><span class="number">{total_buildings}</span><div class="label">Buildings</div></div>
        <div class="summary-item"><span class="number">{total_units}</span><div class="label">Units</div></div>
        <div class="summary-item"><span class="number">{total_photos}</span><div class="label">Photos</div></div>
    </div>
    <div class="content">"""

    for bldg in sorted(structure):
        html += f'<div class="building-section"><h2 class="building-title">🏢 Building {bldg}</h2>'
        for unit in sorted(structure[bldg], key=lambda u: (u == "UNASSIGNED", u)):
            html += f'<div class="unit-section"><div class="unit-header">🏠 Unit {unit}</div>'
            html += '<div class="unit-phases" style="padding:20px;">'
            for phase in phase_order:
                photos = structure[bldg][unit].get(phase, [])
                if phase == "UNTAGGED" and not photos:
                    continue
                zid = _zone_id(zone_prefix, "bldg", bldg, "unit", unit, phase)
                html += _phase_section(photos, phase, zid)
            html += '</div></div>'
        html += '</div>'

    html += generate_special_rooms_html(special_rooms_structure or {}, zone_prefix=zone_prefix)
    html += '</div>'
    return html


def generate_html_bldg_unit_phase(structure, special_rooms_structure=None):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    title = config.PROJECT_NAME or config.PROJECT_ID

    html = _make_head(title)
    html += f"""<div class="container">
        <div class="report-header">
            <h1>{title}</h1>
            <div class="meta">Generated {now}</div>
            {assets.get_pdf_button_html()}
        </div>
        {_render_bldg_unit_phase(structure, special_rooms_structure)}
    </div>{_make_tail()}"""
    with open(paths.OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)


# ============================================================
# UNIT_BATH_PHASE
# ============================================================
def _render_unit_bath_phase(structure, special_rooms_structure=None, zone_prefix=""):
    total_units = len(structure)
    total_photos = sum(len(photos) for units in structure.values()
                       for baths in units.values() for photos in baths.values())
    phase_order = config.get_phase_order()

    html = f"""<div class="summary">
        <div class="summary-item"><span class="number">{total_units}</span><div class="label">Units</div></div>
        <div class="summary-item"><span class="number">{total_photos}</span><div class="label">Photos</div></div>
    </div>
    <div class="content">"""

    for unit in sorted(structure, key=lambda u: (u == "UNASSIGNED", u)):
        html += f'<div class="unit-section"><div class="unit-header">🏠 Unit {unit}</div>'
        for bath in sorted(structure[unit]):
            html += f'<div class="bathroom-group"><div class="bathroom-header">🛁 {bath}</div>'
            html += '<div class="unit-phases">'
            for phase in phase_order:
                photos = structure[unit][bath].get(phase, [])
                if phase == "UNTAGGED" and not photos:
                    continue
                zid = _zone_id(zone_prefix, "unit", unit, "bath", bath, phase)
                html += _phase_section(photos, phase, zid)
            html += '</div></div>'
        html += '</div>'

    html += generate_special_rooms_html(special_rooms_structure or {}, zone_prefix=zone_prefix)
    html += '</div>'
    return html


def generate_html_unit_bath_phase(structure, special_rooms_structure=None):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    title = config.PROJECT_NAME or config.PROJECT_ID

    html = _make_head(title)
    html += f"""<div class="container">
        <div class="report-header">
            <h1>{title}</h1>
            <div class="meta">Generated {now}</div>
            {assets.get_pdf_button_html()}
        </div>
        {_render_unit_bath_phase(structure, special_rooms_structure)}
    </div>{_make_tail()}"""
    with open(paths.OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)


# ============================================================
# FULL HIERARCHY (bldg -> unit -> bath -> phase)
# ============================================================
def _render_full_hierarchy(structure, special_rooms_structure=None, zone_prefix=""):
    total_buildings = len(structure)
    total_units = sum(len(units) for units in structure.values())
    total_photos = sum(len(photos) for units in structure.values()
                       for units_val in units.values()
                       for baths in units_val.values()
                       for photos in baths.values())
    phase_order = config.get_phase_order()

    html = f"""<div class="summary">
        <div class="summary-item"><span class="number">{total_buildings}</span><div class="label">Buildings</div></div>
        <div class="summary-item"><span class="number">{total_units}</span><div class="label">Units</div></div>
        <div class="summary-item"><span class="number">{total_photos}</span><div class="label">Photos</div></div>
    </div>
    <div class="content">"""

    for bldg in sorted(structure):
        html += f'<div class="building-section"><h2 class="building-title">🏢 Building {bldg}</h2>'
        for unit in sorted(structure[bldg], key=lambda u: (u == "UNASSIGNED", u)):
            html += f'<div class="unit-section"><div class="unit-header">🏠 Unit {unit}</div>'
            for bath in sorted(structure[bldg][unit]):
                html += f'<div class="bathroom-group"><div class="bathroom-header">🛁 {bath}</div>'
                html += '<div class="unit-phases">'
                for phase in phase_order:
                    photos = structure[bldg][unit][bath].get(phase, [])
                    if phase == "UNTAGGED" and not photos:
                        continue
                    zid = _zone_id(zone_prefix, "bldg", bldg, "unit", unit, "bath", bath, phase)
                    html += _phase_section(photos, phase, zid)
                html += '</div></div>'
            html += '</div>'
        html += '</div>'

    html += generate_special_rooms_html(special_rooms_structure or {}, zone_prefix=zone_prefix)
    html += '</div>'
    return html


def generate_html_full_hierarchy(structure, special_rooms_structure=None):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    title = config.PROJECT_NAME or config.PROJECT_ID

    html = _make_head(title)
    html += f"""<div class="container">
        <div class="report-header">
            <h1>{title}</h1>
            <div class="meta">Installation Photos | Generated {now}</div>
            {assets.get_pdf_button_html()}
        </div>
        {_render_full_hierarchy(structure, special_rooms_structure)}
    </div>{_make_tail()}"""
    with open(paths.OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)


SUBCONTRACTED_SHAPE = "subcontracted_sequence"
HEAT_PUMP_SHAPE = "heat_pump_phase_serial_buckets"


def determine_html_method(key):
    if key == "unit_phase":
        return generate_html_unit_phase
    elif key == "bldg_unit_phase":
        return generate_html_bldg_unit_phase
    elif key == "unit_bath_phase":
        return generate_html_unit_bath_phase
    elif key == "location_sublocation_type_fixture_phase":
        return generate_html_lighting
    elif key == HEAT_PUMP_SHAPE:
        return generate_html_heat_pump
    elif key == SUBCONTRACTED_SHAPE:
        return generate_html_subcontracted
    else:
        return generate_html_full_hierarchy


def determine_render_method(key):
    """
    Body-only counterpart to determine_html_method (no head/tail/file
    write), used by generate_html_report() so each measure's tab can
    render just its own content without a duplicate page shell per
    measure.
    """
    if key == "unit_phase":
        return _render_unit_phase
    elif key == "bldg_unit_phase":
        return _render_bldg_unit_phase
    elif key == "unit_bath_phase":
        return _render_unit_bath_phase
    elif key == "location_sublocation_type_fixture_phase":
        return _render_lighting
    elif key == HEAT_PUMP_SHAPE:
        return _render_heat_pump
    elif key == SUBCONTRACTED_SHAPE:
        return _render_subcontracted
    else:
        return _render_full_hierarchy


# ============================================================
# LIGHTING (location -> sublocation? -> type -> fixture -> phase)
# ============================================================
# Added per Lighting_HTML_Report_Adjustments. Reuses existing CSS
# classes wherever the shape matches the original layout:
#   Location      -> .building-section / .building-title (relabeled)
#   Sublocation    -> .bathroom-header  (relabeled, optional nesting)
#   Type box       -> .unit-section (new .type-heading inside instead
#                      of the usual .unit-header bar, per spec)
#   Fixture        -> .bathroom-group / .bathroom-header (relabeled)
#   Before/After/Settings -> .phase-section (Settings = phases[2],
#                      renders like the old optional "Identification"
#                      wrapper but relabeled and only shown if present)
# Only 2 new CSS rules are added (_LIGHTING_EXTRA_CSS below) for the
# type-box heading row + its divider; everything else is verbatim
# reuse so plumbing's styling/behavior is untouched.

_LIGHTING_EXTRA_CSS = """
.type-header-row { display:flex; align-items:center; gap:18px; padding:18px 20px;
    border-bottom:1px solid var(--border); flex-wrap:wrap; }
.type-heading { font-size:1.3em; font-weight:700; color:var(--primary); margin:0; white-space:nowrap; }
.type-header-row .phase-section { flex:1; min-width:220px; margin:0; }
"""


def _lighting_photo_dict(photo):
    """
    Convert Lighting's Photo dataclass / CompanyCam payload into the
    normalized dictionary expected by make_photo_card_html().
    """
    data = getattr(photo, "data", None)

    if isinstance(data, dict):
        d = dict(data)
    else:
        d = {}

    # CompanyCam stores image URLs inside the "uris" list.
    url = ""
    uris = d.get("uris", [])

    if isinstance(uris, list):
        # Prefer the web-sized image for the report.
        for uri_data in uris:
            if (
                isinstance(uri_data, dict)
                and uri_data.get("type") == "web"
                and uri_data.get("url")
            ):
                url = uri_data["url"]
                break

        # Fall back to the original image if no web image exists.
        if not url:
            for uri_data in uris:
                if (
                    isinstance(uri_data, dict)
                    and uri_data.get("type") == "original"
                    and uri_data.get("url")
                ):
                    url = uri_data["url"]
                    break

    # CompanyCam stores coordinates under "coordinates".
    coordinates = d.get("coordinates") or {}

    latitude = coordinates.get("lat") if isinstance(coordinates, dict) else None
    longitude = coordinates.get("lon") if isinstance(coordinates, dict) else None

    # Preserve the existing normalized fields expected by the renderer.
    d["url"] = url
    d["captured_at"] = d.get(
        "captured_at",
        int(photo.timestamp.timestamp()) if getattr(photo, "timestamp", None) else None
    )
    d["latitude"] = latitude
    d["longitude"] = longitude
    d["all_tags"] = getattr(photo, "tags", d.get("tag_names", []))
    d["has_image"] = bool(url)

    # Tag list for the caption block, same position/style as plumbing's
    # (see elements.build_captions / build_captions_linear, which read
    # "extra_tags"). Unlike Aquamizer, this is NOT filtered down to
    # unused-in-classification tags -- every tag is shown, just
    # normalized out of ALL-CAPS into Title Case.
    raw_tags = d["all_tags"] or []
    normalized = [_normalize_lighting_tag(t) for t in raw_tags]
    d["extra_tags"] = ", ".join(t for t in normalized if t)

    return d


def _normalize_lighting_tag(tag):
    """ALL-CAPS (or slug-style) tag -> Title Case display text."""
    text = str(tag).replace("_", " ").replace("-", " ").strip()
    return text.title() if text else ""


def _lighting_phase_section(photos, phase_label, phase_index, zone_id):
    """
    Same visual/markup contract as _phase_section, but phase_index 2
    is relabeled "Settings" (renamed from the old "Identification"
    wrapper) instead of keying off a literal "UNTAGGED" string, since
    lighting's phase names are caller-configured, not fixed.
    """
    badge = "before" if phase_index == 0 else ("after" if phase_index == 1 else "untagged")
    label = "Settings" if phase_index == 2 else phase_label
    cards = ''.join(make_photo_card_html(_lighting_photo_dict(p)) for p in photos)
    html = '<div class="phase-section">'
    html += f'<div class="phase-header"><h3 class="phase-title"><span class="phase-badge {badge}">{label}</span></h3>'
    html += f'<span class="phase-count">{len(photos)} photos</span></div>'
    if photos:
        html += f'<div class="photo-grid" data-zone="{zone_id}">{cards}</div>'
    else:
        html += f'<div class="photo-grid" data-zone="{zone_id}"></div><div class="no-photos">No photos</div>'
    html += '</div>'
    return html


def _lighting_untagged_section(photos, zone_id, label="Untagged"):
    if not photos:
        return ""
    cards = ''.join(make_photo_card_html(_lighting_photo_dict(p)) for p in photos)
    html = '<div class="phase-section">'
    html += f'<div class="phase-header"><h3 class="phase-title"><span class="phase-badge untagged">{label}</span></h3>'
    html += f'<span class="phase-count">{len(photos)} photos</span></div>'
    html += f'<div class="photo-grid" data-zone="{zone_id}">{cards}</div></div>'
    return html


def _lighting_render_type_box(type_group, phases, zone_prefix):
    """One Type box: heading + serial-tagged photos row, divider, then
    each Fixture (like a Bathroom) with its Before/After/Settings
    wrappers, divider between each, plus a type-level Untagged tail.

    zone_prefix is a tuple of parts (measure id prepended by the
    caller chain, see _render_lighting), splatted into every
    _zone_id(...) call below via *zone_prefix.
    """
    fixtures = list(type_group.get("fixtures", []))
    serial = next((f for f in fixtures if f["name"] == "Serial-Tagged Fixture"), None)
    other_fixtures = [f for f in fixtures if f is not serial]

    html = '<div class="unit-section">'
    html += '<div class="type-header-row">'
    html += f'<h3 class="type-heading">💡 {type_group["name"]}</h3>'
    if serial:
        zid = _zone_id(*zone_prefix, "type", type_group["name"], "serial")
        html += _lighting_untagged_section(serial["photos"], zid, label="Serial Photos")
    html += '</div>'

    for fixture in other_fixtures:
        html += '<div class="bathroom-group"><div class="bathroom-header">' + fixture["name"] + '</div>'
        html += '<div class="unit-phases">'
        for i, phase in enumerate(phases):
            # Fixture photos were already ordered by phase in sort.py; we
            # only have the flat list here, so split by phase membership.
            phase_photos = [p for p in fixture["photos"] if phase in p.tags]
            zid = _zone_id(*zone_prefix, "type", type_group["name"], "fixture", fixture["name"], phase)
            if i == 2 and not phase_photos:
                continue
            html += _lighting_phase_section(phase_photos, phase, i, zid)
        html += '</div></div>'

    zid = _zone_id(*zone_prefix, "type", type_group["name"], "untagged")
    html += _lighting_untagged_section(type_group.get("untagged", []), zid)
    html += '</div>'
    return html


def _lighting_render_group(group, fixture_types_ignored, phases, zone_prefix, heading_html):
    """Renders one Location or Sublocation: its Types (if any), its
    nested Sublocations (if any), and its own leftover Untagged."""
    html = heading_html
    for type_group in group.get("types", []):
        html += _lighting_render_type_box(type_group, phases, zone_prefix)
    for sub in group.get("sublocations", []):
        sub_zone = zone_prefix + ("sub", sub["name"])
        sub_heading = f'<div class="bathroom-header" style="padding:0 4px;"> {sub["name"]}</div>'
        html += _lighting_render_group(sub, fixture_types_ignored, phases, sub_zone, sub_heading)
    zid = _zone_id(*zone_prefix, "untagged")
    html += _lighting_untagged_section(group.get("untagged", []), zid)
    return html


def _render_lighting(structure, special_rooms_structure=None, phases=None, zone_prefix=""):
    """
    key = "location_sublocation_type_fixture_phase"
    phases: ordered 3-item list [BEFORE_tag, AFTER_tag, SETTINGS_tag]
    used both to split each fixture's photos and to label wrappers.
    Falls back to config.get_phase_order() if not passed explicitly
    (kept as a param since lighting's phase tags are dataset-specific,
    not the plumbing BEFORE/AFTER/UNTAGGED constants).

    zone_prefix is a single value (measure id, or "" for single-measure
    reports) -- wrapped into a 1-tuple below and threaded through the
    whole lighting render chain, which already splats a zone_prefix
    tuple into every _zone_id(...) call.
    """
    phases = phases or config.get_phase_order()
    prefix_tuple = (zone_prefix,) if zone_prefix else ()

    locations = structure.get("locations", [])
    total_locations = len(locations)

    def _count(node):
        n = len(node.get("untagged", []))
        for t in node.get("types", []):
            n += len(t.get("untagged", []))
            for f in t.get("fixtures", []):
                n += len(f["photos"])
        for s in node.get("sublocations", []):
            n += _count(s)
        return n

    total_photos = sum(_count(loc) for loc in locations) + len(structure.get("untagged", []))

    html = f"""<div class="summary">
        <div class="summary-item"><span class="number">{total_locations}</span><div class="label">Locations</div></div>
        <div class="summary-item"><span class="number">{total_photos}</span><div class="label">Photos</div></div>
    </div>
    <div class="content">"""

    for location in locations:
        html += '<div class="building-section"><h2 class="building-title">' + location["name"] + '</h2>'
        html += _lighting_render_group(location, None, phases, prefix_tuple + ("loc", location["name"]), "")
        html += '</div>'

    html += generate_special_rooms_html(special_rooms_structure or {}, zone_prefix=zone_prefix)

    zid = _zone_id(*prefix_tuple, "top", "untagged")
    html += _lighting_untagged_section(structure.get("untagged", []), zid)

    html += '</div>'
    return html


def generate_html_lighting(structure, special_rooms_structure=None, phases=None):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    title = config.PROJECT_NAME or config.PROJECT_ID

    html = _make_head(title, extra_css=_LIGHTING_EXTRA_CSS)
    html += f"""<div class="container">
        <div class="report-header">
            <h1>{title}</h1>
            <div class="meta">Generated {now}</div>
            {assets.get_pdf_button_html()}
        </div>
        {_render_lighting(structure, special_rooms_structure, phases=phases)}
    </div>{_make_tail()}"""
    with open(paths.OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)


def generate_special_rooms_html(special_rooms_structure, zone_prefix=""):
    if not special_rooms_structure:
        return ""

    phase_order = config.get_phase_order()

    html = '<div class="building-section special-rooms-section">'
    html += '<h2 class="building-title" style="border-left-color:#9b59b6;">🏛 Special Areas</h2>'

    for room_name in sorted(special_rooms_structure):
        phases_dict = special_rooms_structure[room_name]
        html += f'<div class="unit-section"><div class="unit-header" style="background:#6c3483;">🏛 {room_name}</div>'
        html += '<div class="unit-phases" style="padding:20px;">'
        for phase in phase_order:
            photos = phases_dict.get(phase, [])
            if phase == "UNTAGGED" and not photos:
                continue
            zid = _zone_id(zone_prefix, "special", room_name.replace(" ", "_"), phase)
            html += _phase_section(photos, phase, zid)
        html += '</div></div>'

    html += '</div>'
    return html


# ============================================================
# SUBCONTRACTED (flat numbered sequence + injectable headings)
# ============================================================

def _subcontract_photo_dict(photo):
    """Normalize a raw photo dict for subcontracted report cards."""
    if isinstance(photo, dict) and photo.get("url"):
        uris = photo.get("uris", [])
        url = photo["url"]
    else:
        raw = photo if isinstance(photo, dict) else getattr(photo, "data", {}) or {}
        uris = raw.get("uris", [])
        url = ""
        for u in uris:
            if isinstance(u, dict) and u.get("type") == "web" and u.get("url"):
                url = u["url"]
                break
        if not url:
            for u in uris:
                if isinstance(u, dict) and u.get("type") == "original" and u.get("url"):
                    url = u["url"]
                    break
        photo = raw

    coords = photo.get("coordinates") or {}
    raw_tags = photo.get("tag_names", photo.get("tags", []))
    normalized = [_normalize_lighting_tag(t) for t in (raw_tags or [])]
    return {
        "url": url or "https://via.placeholder.com/200x180/cccccc/666666?text=No+Image",
        "captured_at": photo.get("captured_at"),
        "latitude": coords.get("lat"),
        "longitude": coords.get("lon"),
        "has_image": bool(url),
        "all_tags": raw_tags,
        "extra_tags": ", ".join(t for t in normalized if t),
    }


def _subcontract_heading_html(item):
    weight = item.get("weight", "medium")
    text = item.get("text", "")
    hid = item.get("id", "")
    return (
        f'<div class="subcontract-heading weight-{weight}" '
        f'data-heading-id="{hid}" data-weight="{weight}">'
        f'<span class="heading-text">{text}</span>'
        f'<button type="button" class="heading-delete-btn" title="Remove heading" '
        f'aria-label="Remove heading">×</button>'
        f'</div>'
    )


def _render_subcontracted(structure, special_rooms_structure=None, zone_prefix=""):
    items = structure.get("items", []) if isinstance(structure, dict) else []
    photo_count = sum(1 for it in items if it.get("type") == "photo")

    html = f"""<div class="summary">
        <div class="summary-item"><span class="number">{photo_count}</span><div class="label">Photos</div></div>
    </div>
    <div class="content">"""

    zid = _zone_id(zone_prefix, "sub")
    html += f'<div class="subcontract-grid photo-grid" data-zone="{zid}">'

    photo_idx = 0
    for item in items:
        if item.get("type") == "heading":
            html += _subcontract_heading_html(item)
        elif item.get("type") == "photo":
            photo_idx += 1
            pd = _subcontract_photo_dict(item.get("photo"))
            html += make_photo_card_html(pd, idx=photo_idx)

    html += '</div></div>'
    return html


def generate_html_subcontracted(structure, special_rooms_structure=None):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    title = config.PROJECT_NAME or config.PROJECT_ID

    html = _make_head(title)
    html += f"""<div class="container">
        <div class="report-header">
            <h1>{title}</h1>
            <div class="meta">Generated {now}</div>
            {assets.get_pdf_button_html()}
        </div>
        {_render_subcontracted(structure, special_rooms_structure)}
    </div>{_make_tail()}"""
    with open(paths.OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)


# ============================================================
# HEAT PUMP (four phase/serial buckets, flat fixture order)
# ============================================================

def _heat_pump_photo_dict(photo):
    """Normalize a raw photo dict for heat pump report cards."""
    return _subcontract_photo_dict(photo)


def _heat_pump_bucket_section(bucket, zone_prefix):
    """One bucket: heading + photo grid."""
    label = bucket.get("label", "")
    key = bucket.get("key", "")
    photos = bucket.get("photos", [])
    zid = _zone_id(zone_prefix, "bucket", key)
    cards = ''.join(make_photo_card_html(_heat_pump_photo_dict(p)) for p in photos)
    html = '<div class="phase-section">'
    html += f'<div class="phase-header"><h3 class="phase-title"><span class="phase-badge before">{label}</span></h3>'
    html += f'<span class="phase-count">{len(photos)} photos</span></div>'
    if photos:
        html += f'<div class="photo-grid" data-zone="{zid}">{cards}</div>'
    else:
        html += f'<div class="photo-grid" data-zone="{zid}"></div><div class="no-photos">No photos</div>'
    html += '</div>'
    return html


def _render_heat_pump(structure, special_rooms_structure=None, zone_prefix=""):
    buckets = structure.get("buckets", []) if isinstance(structure, dict) else []
    untagged = structure.get("untagged", []) if isinstance(structure, dict) else []
    photo_count = sum(len(b.get("photos", [])) for b in buckets) + len(untagged)

    html = f"""<div class="summary">
        <div class="summary-item"><span class="number">{photo_count}</span><div class="label">Photos</div></div>
    </div>
    <div class="content">"""

    for bucket in buckets:
        html += _heat_pump_bucket_section(bucket, zone_prefix)

    if untagged:
        zid = _zone_id(zone_prefix, "untagged")
        cards = ''.join(make_photo_card_html(_heat_pump_photo_dict(p)) for p in untagged)
        html += '<div class="phase-section">'
        html += '<div class="phase-header"><h3 class="phase-title"><span class="phase-badge untagged">Untagged</span></h3>'
        html += f'<span class="phase-count">{len(untagged)} photos</span></div>'
        html += f'<div class="photo-grid" data-zone="{zid}">{cards}</div></div>'

    html += '</div>'
    return html


def generate_html_heat_pump(structure, special_rooms_structure=None):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    title = config.PROJECT_NAME or config.PROJECT_ID

    html = _make_head(title)
    html += f"""<div class="container">
        <div class="report-header">
            <h1>{title}</h1>
            <div class="meta">Generated {now}</div>
            {assets.get_pdf_button_html()}
        </div>
        {_render_heat_pump(structure, special_rooms_structure)}
    </div>{_make_tail()}"""
    with open(paths.OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)


# ============================================================
# MULTI-MEASURE TABBED REPORT
# ============================================================
def _unknown_photo_dict(photo):
    """
    Normalizes a raw (pre-organize) photo dict -- the shape
    classification.unknown holds -- into what make_photo_card_html
    expects. No sorting/sectioning is attempted, per spec: this is a
    flat, single-bucket tab, same treatment as an Untagged zone.
    """
    uris = photo.get("uris", [])
    url = ""
    for u in uris:
        if isinstance(u, dict) and u.get("type") == "web" and u.get("url"):
            url = u["url"]
            break
    if not url:
        for u in uris:
            if isinstance(u, dict) and u.get("type") == "original" and u.get("url"):
                url = u["url"]
                break
    coords = photo.get("coordinates") or {}
    return {
        "url": url or "https://via.placeholder.com/200x180/cccccc/666666?text=No+Image",
        "captured_at": photo.get("captured_at"),
        "latitude": coords.get("lat"),
        "longitude": coords.get("lon"),
        "has_image": bool(url),
        "all_tags": photo.get("tag_names", []),
    }


def _slugify_nickname(value):
    slug = re.sub(r'[^a-z0-9]+', '_', str(value or '').strip().lower())
    return slug.strip('_') or 'project'


def _render_unknown_measure(photos, photos_by_project=None):
    if photos_by_project:
        total = sum(len(g.get('photos') or []) for g in photos_by_project)
        html = f"""<div class="summary">
        <div class="summary-item"><span class="number">{total}</span><div class="label">Photos</div></div>
    </div>
    <div class="content">"""
        for group in photos_by_project:
            nick = group.get('nickname') or 'Unknown'
            raw_photos = group.get('photos') or []
            normalized = [_unknown_photo_dict(p) for p in raw_photos]
            zid = _zone_id("__unknown__", _slugify_nickname(nick))
            html += f'<div class="unit-section"><div class="unit-header">{nick}</div>'
            html += f'<div class="unit-phases" style="padding:20px;">{_photo_grid(normalized, zid)}</div></div>'
        html += '</div>'
        return html

    normalized = [_unknown_photo_dict(p) for p in (photos or [])]
    zid = _zone_id("__unknown__", "untagged")
    html = f"""<div class="summary">
        <div class="summary-item"><span class="number">{len(normalized)}</span><div class="label">Photos</div></div>
    </div>
    <div class="content">"""
    html += '<div class="unit-section"><div class="unit-header">Unmatched Photos</div>'
    html += f'<div class="unit-phases" style="padding:20px;">{_photo_grid(normalized, zid)}</div></div>'
    html += '</div>'
    return html


def generate_html_report(measures, unknown_photos=None, unknown_photos_by_project=None, title=None):
    """
    Multi-measure entrypoint.

    measures: list of dicts, one per measure --
        {
          "id": measure id (str),
          "name": display name (falls back to type if not provided),
          "type": measure type string,
          "shape": sort_output.shape -- one of the SORT_METHOD_KEY
                   literals (unit_phase / bldg_unit_phase /
                   unit_bath_phase / full / location_sublocation_type_
                   fixture_phase),
          "structure": sort_output.structure,
          "special": sort_output.special,
          "phases": lighting-only ordered [BEFORE, AFTER, SETTINGS]
                     tag list, or None for non-lighting measures.
        }
    unknown_photos_by_project: multi-project only -- list of
        {"nickname": str, "photos": list} grouped unknown buckets.
        When set, takes precedence over unknown_photos.

    One shared head/report-header/tail for the whole page; each
    measure gets its own tab, rendered via its own shape's
    determine_render_method() so per-shape layout logic is untouched.
    Each tab's internal zone IDs are scoped by that measure's id (see
    module docstring) so same-shape measures don't collide.
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    title = title or config.PROJECT_NAME or config.PROJECT_ID

    tabs = []
    for m in measures:
        render_fn = determine_render_method(m["shape"])
        if m["shape"] == "location_sublocation_type_fixture_phase":
            inner = render_fn(m["structure"], m.get("special"), phases=m.get("phases"), zone_prefix=m["id"])
        else:
            inner = render_fn(m["structure"], m.get("special"), zone_prefix=m["id"])
        tabs.append({"id": m["id"], "label": m.get("name") or m["type"], "inner": inner})

    if unknown_photos_by_project:
        tabs.append({
            "id": "__unknown__",
            "label": "Unknown Measure",
            "inner": _render_unknown_measure(None, photos_by_project=unknown_photos_by_project),
        })
    elif unknown_photos:
        tabs.append({
            "id": "__unknown__",
            "label": "Unknown Measure",
            "inner": _render_unknown_measure(unknown_photos),
        })

    if not tabs:
        # Caller should already guard against calling this with nothing
        # to render, but stay safe and skip writing an empty shell.
        return

    nav = "".join(
        f'<button class="tab-btn{" active" if i == 0 else ""}" data-tab="{t["id"]}">{t["label"]}</button>'
        for i, t in enumerate(tabs)
    )
    panes = "".join(
        f'<div class="tab-pane{" active" if i == 0 else ""}" id="tab-{t["id"]}">{t["inner"]}</div>'
        for i, t in enumerate(tabs)
    )

    html = _make_head(title, extra_css=assets.get_tabs_css())
    html += f"""<div class="container">
        <div class="report-header">
            <h1>{title}</h1>
            <div class="meta">Generated {now}</div>
            {assets.get_pdf_button_html()}
        </div>
        <div class="tab-nav">{nav}</div>
        {panes}
    </div>{assets.get_tabs_js()}{_make_tail()}"""

    with open(paths.OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)