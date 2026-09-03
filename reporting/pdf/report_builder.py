"""
PDF report builder — dividers + main orchestrator.

Relocated from pdf_generator.py with these changes:
  - base_dir / reports_dir -> core.paths.PROJECT_ROOT / core.paths.REPORTS_DIR
    (was independently computed via os.path.dirname(__file__), which
    pointed at project root only because pdf_generator.py used to live
    there; this file now lives one directory deeper)
  - bath_divider's hardcoded "Bathroom" text -> the active dataset's
    sub_unit_label_singular, same generalization as
    core/organizer.py's build_used_tag_string() in step 2

Still branches on the same 4 sort_mode literal strings as
core/organizer.py, core/sort_engine.py, and the HTML generators — see
datasets/base.py for why that's a structural contract, not something
this file can generalize away alone.
"""

import gc
import os
import re

from pypdf import PdfReader, PdfWriter

from reportlab.platypus import SimpleDocTemplate, Paragraph, HRFlowable, KeepTogether, Spacer, PageBreak
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.pagesizes import letter
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.units import inch

from reporting.pdf.elements import (
    MARGIN, HEADER_BG, DIVIDER_COLOR, style_bldg, style_unit, style_bath,
    style_no_photo, make_header_footer, fetch_image_to_temp, PAGE_H,
)
from reporting.pdf.sections import (
    build_photo_section, build_photo_section_linear,
    build_id_section, build_id_section_linear, collect_id_photos,
    build_flat_linear_section, build_subcontracted_grid_section,
)
from reporting.html.generators import _lighting_photo_dict, _subcontract_photo_dict, _heat_pump_photo_dict
from reporting.pdf.cover_page import build_cover_page
from reporting.pdf.heading_catalog import (
    resolve_heading_label,
    lighting_path_key,
    lighting_path_default,
    sub_unit_label as catalog_sub_unit_label,
)
from core.organizer import _other_bath_is_active
import core.config as config
import core.paths as paths
import core.job_manager as job_manager

from core.timezone import now_formatted

# Matches the sort_mode_map contract in datasets/base.py -- Lighting's
# one structural shape, same literal used by generators.determine_html_method.
LIGHTING_SORT_KEY = "location_sublocation_type_fixture_phase"
SUBCONTRACTED_SORT_KEY = "subcontracted_sequence"
HEAT_PUMP_SORT_KEY = "heat_pump_phase_serial_buckets"
MANUAL_ARRANGE_SORT_KEY = "manual_arrange_sequence"

# The following helper function is part of an experimental refactor
def _get_dataset_label_singular() -> str:
    ds = config.ACTIVE_DATASET
    if ds is not None:
        return ds.sub_unit_label_singular
    return "Sub-Unit"

# ============================
# PDF CONTEXT BUILDER
# ============================
# Relocated from newreport.py. Was read/written entirely off module
# globals (PROJECT_ID, PROJECT_NAME, SORT_METHOD_KEY); now reads them
# off core.config. "total_bathrooms" keeps its original key name --
# same compatibility reasoning as the SORT_METHOD_KEY literals: it's
# read by cover_page.py's field_map by that exact key, untouched in
# this pass.
def build_pdf_context(structure, photos, special_rooms_structure=None):
    total_photos = len(photos)
    total_buildings = 0
    total_units = 0
    total_bathrooms = 0

    sort_mode = config.SORT_METHOD_KEY

    if sort_mode == "full":
        total_buildings = len(structure)
        total_units = sum(len(units) for units in structure.values())
        total_bathrooms = sum(
            1 for units in structure.values()
            for baths in units.values()
            for bath, phases in baths.items()
            if bath != "OTHER" or _other_bath_is_active(phases)
        )
    elif sort_mode == "bldg_unit_phase":
        total_buildings = len(structure)
        total_units = sum(len(units) for units in structure.values())
    elif sort_mode == "unit_bath_phase":
        total_units = len(structure)
        total_bathrooms = sum(
            1 for baths in structure.values()
            for bath, phases in baths.items()
            if bath != "OTHER" or _other_bath_is_active(phases)
        )
    elif sort_mode == LIGHTING_SORT_KEY:
        # No buildings/bathrooms concept for Lighting -- reuse the
        # existing cover-page fields (which no-op on falsy values) with
        # the closest equivalents so cover_page.py needs no changes:
        #   total_units      -> Locations
        #   total_bathrooms  -> Fixtures ("Installations")
        locations = structure.get("locations", [])
        total_units = len(locations)

        def _count_fixtures(node):
            n = sum(len(t.get("fixtures", [])) for t in node.get("types", []))
            for s in node.get("sublocations", []):
                n += _count_fixtures(s)
            return n

        total_bathrooms = sum(_count_fixtures(loc) for loc in locations)
    elif sort_mode == SUBCONTRACTED_SORT_KEY:
        items = structure.get("items", []) if isinstance(structure, dict) else []
        total_photos = sum(1 for it in items if it.get("type") == "photo")
    elif sort_mode == MANUAL_ARRANGE_SORT_KEY:
        staging = structure.get("staging_items", []) if isinstance(structure, dict) else []
        buckets = structure.get("buckets", []) if isinstance(structure, dict) else []
        total_photos = sum(1 for it in staging if it.get("type") == "photo")
        total_photos += sum(len(b.get("photos", [])) for b in buckets)
    else:
        total_units = len(structure)

    context = {
        "project_id": config.PROJECT_ID,
        "project_name": config.PROJECT_NAME or config.PROJECT_ID,
        "project_name_upper": (config.PROJECT_NAME or config.PROJECT_ID).upper(),
        "address": job_manager.get_project_address(config.PROJECT_ID),
        "date_generated": now_formatted("%B %d, %Y"),
        "total_photos": total_photos,
        "total_buildings": total_buildings,
        "total_units": total_units,
        "total_bathrooms": total_bathrooms,
        "sort_mode": sort_mode,
        "structured": structure,
        "special_rooms_structured": special_rooms_structure or {},
    }

    print("\n========= REPORT METRICS =========")
    print(f"Mode: {sort_mode}")
    print(f"Buildings: {total_buildings}")
    print(f"Units: {total_units}")
    print(f"Bathrooms: {total_bathrooms}")
    print(f"Photos: {total_photos}")
    if special_rooms_structure:
        print(f"Special rooms: {list(special_rooms_structure.keys())}")
    print("==================================\n")

    return context


# ============================
# DIVIDER HELPERS
# ============================
def bldg_divider(label):
    return [
        HRFlowable(width="100%", thickness=2.5, color=HEADER_BG, spaceAfter=3),
        Paragraph(label, style_bldg),
    ]

def unit_divider(label):
    return [
        HRFlowable(width="100%", thickness=1.2, color=colors.HexColor("#2e86de"), spaceAfter=2),
        Paragraph(label, style_unit),
    ]

def bath_divider(label):
    return [
        HRFlowable(width="100%", thickness=0.5, color=DIVIDER_COLOR, spaceAfter=1),
        Paragraph(label, style_bath),
    ]

def special_room_divider(label):
    style_special = ParagraphStyle(
        "SpecialRoomHdr",
        fontSize=14, leading=18, spaceAfter=2, spaceBefore=5,
        textColor=colors.HexColor("#6c3483"), fontName="Helvetica-Bold"
    )
    return [
        HRFlowable(width="100%", thickness=2.5, color=colors.HexColor("#6c3483"), spaceAfter=3),
        Paragraph(f"Special Area — {label}", style_special),
    ]


def measure_divider(label):
    """Top-level divider that separates measures in a multi-measure PDF."""
    return build_measure_heading(label, "normal")


def build_measure_heading(label, size="normal"):
    """Build multi-measure heading block; size: none|normal|large|full_page."""
    size = (size or "normal").lower()
    if size == "none":
        return []

    style_measure = ParagraphStyle(
        "MeasureHdr",
        fontSize=18, leading=22, spaceAfter=4, spaceBefore=10,
        textColor=colors.HexColor("#1a5276"), fontName="Helvetica-Bold",
        alignment=TA_CENTER,
    )

    if size == "full_page":
        banner_h = PAGE_H - 2.2 * inch
        return [
            PageBreak(),
            Spacer(1, banner_h * 0.28),
            HRFlowable(width="72%", thickness=3.5, color=colors.HexColor("#1a5276"), spaceAfter=12),
            Paragraph(label.upper(), style_measure),
            HRFlowable(width="72%", thickness=1.0, color=colors.HexColor("#2e86de"), spaceAfter=8),
            Spacer(1, banner_h * 0.38),
            PageBreak(),
        ]

    if size == "large":
        return [
            Spacer(1, 0.55 * inch),
            HRFlowable(width="100%", thickness=3.5, color=colors.HexColor("#1a5276"), spaceAfter=8),
            Paragraph(label.upper(), style_measure),
            HRFlowable(width="100%", thickness=1.0, color=colors.HexColor("#2e86de"), spaceAfter=6),
            Spacer(1, 0.45 * inch),
        ]

    return [
        HRFlowable(width="100%", thickness=3.5, color=colors.HexColor("#1a5276"), spaceAfter=5),
        Paragraph(label.upper(), style_measure),
        HRFlowable(width="100%", thickness=1.0, color=colors.HexColor("#2e86de"), spaceAfter=4),
    ]


def _measure_show_tags(measure_id, pdf_options):
    measure_opts = pdf_options.get("measure_options", {})
    entry = measure_opts.get(measure_id, {})
    if isinstance(entry, dict) and "show_tags" in entry:
        return bool(entry.get("show_tags", True))
    return pdf_options.get("show_photo_tags", True)


def _measure_heading_size(measure_id, pdf_options):
    measure_opts = pdf_options.get("measure_options", {})
    entry = measure_opts.get(measure_id, {})
    if isinstance(entry, dict) and entry.get("heading_size"):
        return str(entry.get("heading_size")).lower()
    return "normal"


def _standalone_measure_heading_block(measure_hdr_pending, omit_leading_break=False):
    """Return top-level flowables for full-page measure headings."""
    if not measure_hdr_pending:
        return []
    block = list(measure_hdr_pending)
    if omit_leading_break and block and isinstance(block[0], PageBreak):
        block = block[1:]
    return block


def _active_measure_id(pdf_options):
    mid = pdf_options.get("_current_measure_id")
    if mid:
        return mid
    opts = pdf_options.get("measure_options") or {}
    if len(opts) == 1:
        return next(iter(opts))
    return ""


def _heading_visible(key, pdf_options, default=True):
    measure_id = _active_measure_id(pdf_options)
    if not measure_id:
        return default
    entry = (pdf_options.get("measure_options") or {}).get(measure_id, {})
    if not isinstance(entry, dict):
        return default
    vis = entry.get("heading_visibility") or {}
    return vis.get(key, default)


def _maybe_bldg_divider(label, pdf_options, key="building"):
    return bldg_divider(label) if _heading_visible(key, pdf_options) else []


def _maybe_unit_divider(label, pdf_options):
    return unit_divider(label) if _heading_visible("unit", pdf_options) else []


def _maybe_bath_divider(label, pdf_options, key="bathroom"):
    return bath_divider(label) if _heading_visible(key, pdf_options) else []


def _maybe_loc_level_divider(label, pdf_options, depth):
    key = f"location_level_{depth + 1}"
    return bldg_divider(label) if _heading_visible(key, pdf_options) else []


def _measure_forces_linear(m_sort_mode):
    return m_sort_mode in (LIGHTING_SORT_KEY, HEAT_PUMP_SORT_KEY)


def _render_lighting_location(location, pdf_options, elements, initial_headers=None):
    """
    Render one Location and any nested sublocation levels.

    When sublocations exist, content directly on a group is headed with
    that group's name; each child sublocation uses a compound heading
    (e.g. "Building A: Floor 2: Room 101").
    """
    init_hdr = list(initial_headers or [])
    first_emission = [True]

    def maybe_prepend(headers):
        if first_emission[0] and init_hdr:
            first_emission[0] = False
            return init_hdr + list(headers)
        return list(headers)

    def _render_subtree(group, path_parts, depth=0):
        loc_default = lighting_path_default(path_parts)
        loc_key = lighting_path_key(path_parts)
        resolved_loc = resolve_heading_label(loc_key, loc_default, pdf_options)
        loc_hdr = _maybe_loc_level_divider(resolved_loc, pdf_options, depth)
        if group.get("sublocations"):
            direct_header = maybe_prepend(loc_hdr)
            _render_lighting_types_and_untagged(
                group, path_parts, direct_header, pdf_options, elements,
            )
            for sub in group["sublocations"]:
                child_parts = path_parts + [sub["name"]]
                _render_subtree(sub, child_parts, depth + 1)
        else:
            loc_header = maybe_prepend(loc_hdr)
            _render_lighting_types_and_untagged(
                group, path_parts, loc_header, pdf_options, elements,
            )

    _render_subtree(location, [location["name"]], 0)


def _render_lighting_types_and_untagged(group, path_parts, pending_headers, pdf_options, elements):
    """
    Renders one Location's or Sublocation's Types (each Type gets its
    own heading; its Fixtures' photos are flattened together with no
    Fixture-level heading) plus that group's own leftover Untagged
    photos. `pending_headers` is attached to whichever piece of
    content comes first so it's never orphaned on its own page.
    """
    emitted = False

    for type_group in group.get("types", []):
        type_default = type_group["name"]
        type_key = f"type:{lighting_path_key(path_parts)}:{type_default}"
        resolved_type = resolve_heading_label(type_key, type_default, pdf_options)
        type_hdr = (
            _maybe_bath_divider(resolved_type, pdf_options, key="fixture_type")
            if _heading_visible("fixture_type", pdf_options) else []
        )
        photos = []
        for fixture in type_group.get("fixtures", []):
            photos.extend(fixture["photos"])
        photos.extend(type_group.get("untagged", []))
        photo_dicts = [_lighting_photo_dict(p) for p in photos]

        header = (pending_headers + type_hdr) if not emitted else type_hdr
        elements.extend(build_flat_linear_section(photo_dicts, header, pdf_options))
        emitted = True

    leftover = [_lighting_photo_dict(p) for p in group.get("untagged", [])]
    if leftover:
        header = pending_headers if not emitted else []
        elements.extend(build_flat_linear_section(leftover, header, pdf_options))
        emitted = True

    # Nothing at all under this heading -- still show it (unless
    # hide_empty is on) so it isn't silently dropped.
    if not emitted and pending_headers and not pdf_options.get("hide_empty_fields", False):
        elements.append(KeepTogether(list(pending_headers) + [
            Paragraph("No photos in this section.", style_no_photo),
            Spacer(1, 6),
        ]))


def _subcontract_heading_divider(text, weight):
    w = (weight or "medium").lower()
    if w == "light":
        return bath_divider(text)
    if w == "heavy":
        return measure_divider(text)
    return bldg_divider(text)


def _render_subcontracted_items(items, pdf_options, elements, is_linear, section_fn, initial_headers=None):
    hidden_urls = set(pdf_options.get("hidden_photos", []))
    photo_buf = []
    pending_headers = list(initial_headers or [])

    def flush_photos():
        nonlocal photo_buf, pending_headers
        visible = [p for p in photo_buf if p.get("url") not in hidden_urls]
        photo_buf = []
        if not visible:
            return
        if is_linear:
            elements.extend(build_flat_linear_section(visible, pending_headers, pdf_options))
        else:
            elements.extend(build_subcontracted_grid_section(visible, pending_headers, pdf_options))
        pending_headers = []

    def flush_lonely_headers():
        nonlocal pending_headers
        if pending_headers and not pdf_options.get("hide_empty_fields", False):
            elements.append(KeepTogether(list(pending_headers) + [
                Paragraph("No photos in this section.", style_no_photo),
                Spacer(1, 6),
            ]))
        pending_headers = []

    for item in items or []:
        if item.get("type") == "heading":
            flush_photos()
            if _heading_visible("section", pdf_options):
                pending_headers.extend(
                    _subcontract_heading_divider(item.get("text", ""), item.get("weight", "medium"))
                )
        elif item.get("type") == "photo":
            pd = _subcontract_photo_dict(item.get("photo"))
            if pd.get("url") not in hidden_urls:
                photo_buf.append(pd)
    flush_photos()
    flush_lonely_headers()


def _render_heat_pump_buckets(m_data, pdf_options, elements, is_linear, section_fn, initial_headers=None, location_name=None):
    hidden_urls = set(pdf_options.get("hidden_photos", []))
    pending_init = list(initial_headers or [])
    for bucket in m_data.get("buckets", []):
        photos = [_heat_pump_photo_dict(p) for p in bucket.get("photos", [])]
        visible = [p for p in photos if p.get("url") not in hidden_urls]
        if not visible:
            continue
        bucket_label = bucket.get("label", "")
        if location_name:
            bucket_key = f"loc:{location_name}:bucket:{bucket_label}"
        else:
            bucket_key = f"bucket:{bucket_label}"
        resolved_bucket = resolve_heading_label(bucket_key, bucket_label, pdf_options)
        bucket_hdr = _maybe_bldg_divider(resolved_bucket, pdf_options, key="bucket")
        hdr = pending_init + bucket_hdr
        pending_init = []
        if is_linear:
            elements.extend(build_flat_linear_section(visible, hdr, pdf_options))
        else:
            elements.extend(section_fn({"UNTAGGED": visible}, hdr, pdf_options))

    untagged = [_heat_pump_photo_dict(p) for p in m_data.get("untagged", [])]
    visible_untagged = [p for p in untagged if p.get("url") not in hidden_urls]
    if visible_untagged:
        hdr = pending_init + bldg_divider("Untagged")
        pending_init = []
        if is_linear:
            elements.extend(build_flat_linear_section(visible_untagged, hdr, pdf_options))
        else:
            elements.extend(section_fn({"UNTAGGED": visible_untagged}, hdr, pdf_options))
    elif pending_init and not pdf_options.get("hide_empty_fields", False):
        elements.append(KeepTogether(list(pending_init) + [
            Paragraph("No photos in this section.", style_no_photo),
            Spacer(1, 6),
        ]))


def _render_heat_pump_locations(m_data, pdf_options, elements, is_linear, section_fn, initial_headers=None):
    pending_init = list(initial_headers or [])
    for location in m_data.get("locations", []):
        loc_name = location.get("name", "")
        loc_default = loc_name
        loc_key = f"loc:{loc_name}"
        resolved_loc = resolve_heading_label(loc_key, loc_default, pdf_options)
        loc_hdr = _maybe_bldg_divider(resolved_loc, pdf_options, key="location")
        hdr = pending_init + loc_hdr
        pending_init = []
        _render_heat_pump_buckets(
            location, pdf_options, elements, is_linear, section_fn,
            initial_headers=hdr, location_name=loc_name,
        )
    top_untagged = [_heat_pump_photo_dict(p) for p in m_data.get("untagged", [])]
    hidden_urls = set(pdf_options.get("hidden_photos", []))
    visible_untagged = [p for p in top_untagged if p.get("url") not in hidden_urls]
    if visible_untagged:
        hdr = pending_init + bldg_divider("Untagged")
        if is_linear:
            elements.extend(build_flat_linear_section(visible_untagged, hdr, pdf_options))
        else:
            elements.extend(section_fn({"UNTAGGED": visible_untagged}, hdr, pdf_options))
    elif pending_init and not pdf_options.get("hide_empty_fields", False):
        elements.append(KeepTogether(list(pending_init) + [
            Paragraph("No photos in this section.", style_no_photo),
            Spacer(1, 6),
        ]))


def _render_manual_arrange_measure(m_data, pdf_options, elements, is_linear, section_fn, initial_headers=None):
    """Render staging sequence first, then any remaining bucket photos."""
    _render_subcontracted_items(
        m_data.get("staging_items", []), pdf_options, elements, is_linear, section_fn,
        initial_headers=initial_headers,
    )
    hidden_urls = set(pdf_options.get("hidden_photos", []))
    for bucket in m_data.get("buckets", []):
        photos = [_subcontract_photo_dict(p) for p in bucket.get("photos", [])]
        visible = [p for p in photos if p.get("url") not in hidden_urls]
        if not visible:
            continue
        bucket_label = bucket.get("label", "")
        bucket_key = f"bucket:{bucket_label}"
        resolved_bucket = resolve_heading_label(bucket_key, bucket_label, pdf_options)
        bucket_hdr = _maybe_bldg_divider(resolved_bucket, pdf_options, key="bucket")
        if is_linear:
            elements.extend(build_flat_linear_section(visible, bucket_hdr, pdf_options))
        else:
            elements.extend(section_fn({"UNTAGGED": visible}, bucket_hdr, pdf_options))


# This helper is part of an experimental refactor
def _sub_unit_label():
    return catalog_sub_unit_label()

# ============================
# VISIBLE PHOTO COLLECTION
# ============================
def _collect_visible_photos(data, sort_mode, special_data, hidden_urls):
    """Return photo dicts that will be rendered, respecting hidden_urls."""
    result = []

    def _collect_photos(phases_dict):
        for phase_list in phases_dict.values():
            for p in phase_list:
                if p.get("url") not in hidden_urls:
                    result.append(p)

    if sort_mode == "full":
        for bldg in data:
            for unit in data[bldg]:
                for bath in data[bldg][unit]:
                    _collect_photos(data[bldg][unit][bath])
    elif sort_mode == "bldg_unit_phase":
        for bldg in data:
            for unit in data[bldg]:
                _collect_photos(data[bldg][unit])
    elif sort_mode == "unit_bath_phase":
        for unit in data:
            for bath in data[unit]:
                _collect_photos(data[unit][bath])
    elif sort_mode == LIGHTING_SORT_KEY:
        def _collect_lighting(node):
            for t in node.get("types", []):
                for f in t.get("fixtures", []):
                    for p in f["photos"]:
                        d = _lighting_photo_dict(p)
                        if d.get("url") not in hidden_urls:
                            result.append(d)
                for p in t.get("untagged", []):
                    d = _lighting_photo_dict(p)
                    if d.get("url") not in hidden_urls:
                        result.append(d)
            for s in node.get("sublocations", []):
                _collect_lighting(s)
            for p in node.get("untagged", []):
                d = _lighting_photo_dict(p)
                if d.get("url") not in hidden_urls:
                    result.append(d)
        for loc in data.get("locations", []):
            _collect_lighting(loc)
        for p in data.get("untagged", []):
            d = _lighting_photo_dict(p)
            if d.get("url") not in hidden_urls:
                result.append(d)
    elif sort_mode == SUBCONTRACTED_SORT_KEY:
        for item in data.get("items", []):
            if item.get("type") == "photo":
                d = _subcontract_photo_dict(item.get("photo"))
                if d.get("url") not in hidden_urls:
                    result.append(d)
    elif sort_mode == MANUAL_ARRANGE_SORT_KEY:
        for item in data.get("staging_items", []):
            if item.get("type") == "photo":
                d = _subcontract_photo_dict(item.get("photo"))
                if d.get("url") not in hidden_urls:
                    result.append(d)
        for bucket in data.get("buckets", []):
            for p in bucket.get("photos", []):
                d = _subcontract_photo_dict(p)
                if d.get("url") not in hidden_urls:
                    result.append(d)
    elif sort_mode == HEAT_PUMP_SORT_KEY:
        for bucket in data.get("buckets", []):
            for p in bucket.get("photos", []):
                d = _heat_pump_photo_dict(p)
                if d.get("url") not in hidden_urls:
                    result.append(d)
        for p in data.get("untagged", []):
            d = _heat_pump_photo_dict(p)
            if d.get("url") not in hidden_urls:
                result.append(d)
    else:
        for unit in data:
            _collect_photos(data[unit])

    for room in special_data or {}:
        _collect_photos(special_data[room])

    return result


def _safe_partial_name(value, fallback="measure"):
    text = re.sub(r"[^\w\-.]+", "_", str(value or "").strip()) or fallback
    return text[:80]


def _generate_partial_pdf(elements, save_path, project_name, page_offset=0):
    doc = SimpleDocTemplate(
        save_path,
        pagesize=letter,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=0.85 * inch,
        bottomMargin=0.5 * inch,
    )
    doc.project_name = project_name
    hf = make_header_footer(project_name, page_offset=page_offset)
    doc.build(elements, onFirstPage=hf, onLaterPages=hf)


def _merge_partial_pdfs(partial_paths, save_path):
    writer = PdfWriter()
    for path in partial_paths:
        writer.append(path)
    with open(save_path, "wb") as out_f:
        writer.write(out_f)


def _build_measure_elements(m_entry, pdf_options, is_linear, hide_empty, hidden_urls, sub_unit_label, omit_leading_break=False):
    """Build platypus elements for one measure in a multi-measure report."""
    elements = []
    m_id        = m_entry.get("measure_id") or ""
    m_name      = m_entry.get("measure_name") or m_id or "Measure"
    m_data      = m_entry["structure"]
    m_special   = m_entry.get("special_rooms_structure", {})
    m_sort_mode = m_entry.get("sort_mode") or "unit_phase"

    saved_show_tags = pdf_options.get("show_photo_tags", True)
    pdf_options["show_photo_tags"] = _measure_show_tags(m_id, pdf_options)
    pdf_options["_current_measure_id"] = m_id

    m_is_linear = is_linear or _measure_forces_linear(m_sort_mode)
    m_section_fn = build_photo_section_linear if m_is_linear else build_photo_section

    heading_size = _measure_heading_size(m_id, pdf_options)
    measure_hdr_pending = build_measure_heading(m_name, heading_size)
    heading_is_full_page = heading_size == "full_page"
    measure_hdr_used = [False]

    if heading_is_full_page and measure_hdr_pending:
        elements.extend(_standalone_measure_heading_block(measure_hdr_pending, omit_leading_break=omit_leading_break))
        measure_hdr_used[0] = True

    def _with_measure_hdr(headers):
        if heading_is_full_page:
            return list(headers)
        if not measure_hdr_used[0] and measure_hdr_pending:
            measure_hdr_used[0] = True
            return measure_hdr_pending + list(headers)
        return list(headers)

    def _initial_measure_headers():
        if heading_is_full_page or measure_hdr_used[0]:
            return None
        return measure_hdr_pending

    def _section_has_photos(phases_dict):
        return any(
            p.get("url") not in hidden_urls
            for phase_list in phases_dict.values()
            for p in phase_list
        )

    if m_sort_mode == "full":
        for bldg in sorted(m_data):
            bldg_default = f"Building {bldg if bldg != 'NO_BLDG' else 'Unassigned'}"
            bldg_hdr = _maybe_bldg_divider(
                resolve_heading_label(f"building:{bldg}", bldg_default, pdf_options),
                pdf_options,
            )
            for unit in sorted(m_data[bldg]):
                unit_default = f"Unit {unit if unit != 'UNASSIGNED' else 'Unassigned'}"
                unit_hdr = _maybe_unit_divider(
                    resolve_heading_label(f"unit:{bldg}:{unit}", unit_default, pdf_options),
                    pdf_options,
                )
                unit_id_photos = []
                real_baths = [b for b in sorted(m_data[bldg][unit]) if b != "OTHER"]
                for bath in real_baths:
                    phases = m_data[bldg][unit][bath]
                    unit_id_photos.extend(collect_id_photos(phases, hidden_urls))
                    clean_phases = {k: v for k, v in phases.items() if k in ("BEFORE", "AFTER")}
                    if hide_empty and not _section_has_photos(clean_phases):
                        continue
                    bath_default = f"{bath.title()} {sub_unit_label}"
                    bath_hdr = _maybe_bath_divider(
                        resolve_heading_label(
                            f"bathroom:{bldg}:{unit}:{bath}", bath_default, pdf_options,
                        ),
                        pdf_options,
                    )
                    combined = _with_measure_hdr(bldg_hdr + unit_hdr + bath_hdr)
                    elements += m_section_fn(clean_phases, combined, pdf_options)
                    bldg_hdr = []
                    unit_hdr = []
                if "OTHER" in m_data[bldg][unit]:
                    for phase_list in m_data[bldg][unit]["OTHER"].values():
                        unit_id_photos.extend(
                            p for p in phase_list if p.get("url") not in hidden_urls
                        )
                id_fn = build_id_section_linear if m_is_linear else build_id_section
                elements += id_fn(unit_id_photos, _with_measure_hdr([]), pdf_options)

    elif m_sort_mode == "bldg_unit_phase":
        for bldg in sorted(m_data):
            bldg_default = f"Building {bldg if bldg != 'NO_BLDG' else 'Unassigned'}"
            bldg_hdr = _maybe_bldg_divider(
                resolve_heading_label(f"building:{bldg}", bldg_default, pdf_options),
                pdf_options,
            )
            for unit in sorted(m_data[bldg]):
                phases = m_data[bldg][unit]
                if hide_empty and not _section_has_photos(phases):
                    continue
                unit_default = f"Unit {unit if unit != 'UNASSIGNED' else 'Unassigned'}"
                unit_hdr = _maybe_unit_divider(
                    resolve_heading_label(f"unit:{bldg}:{unit}", unit_default, pdf_options),
                    pdf_options,
                )
                combined = _with_measure_hdr(bldg_hdr + unit_hdr)
                elements += m_section_fn(phases, combined, pdf_options)
                bldg_hdr = []

    elif m_sort_mode == "unit_bath_phase":
        for unit in sorted(m_data):
            unit_default = f"Unit {unit if unit != 'UNASSIGNED' else 'Unassigned'}"
            unit_hdr = _maybe_unit_divider(
                resolve_heading_label(f"unit:{unit}", unit_default, pdf_options),
                pdf_options,
            )
            unit_id_photos = []
            real_baths = [b for b in sorted(m_data[unit]) if b != "OTHER"]
            for bath in real_baths:
                phases = m_data[unit][bath]
                unit_id_photos.extend(collect_id_photos(phases, hidden_urls))
                clean_phases = {k: v for k, v in phases.items() if k in ("BEFORE", "AFTER")}
                if hide_empty and not _section_has_photos(clean_phases):
                    continue
                bath_default = f"{bath.title()} {sub_unit_label}"
                bath_hdr = _maybe_bath_divider(
                    resolve_heading_label(
                        f"bathroom:{unit}:{bath}", bath_default, pdf_options,
                    ),
                    pdf_options,
                )
                combined = _with_measure_hdr(unit_hdr + bath_hdr)
                elements += m_section_fn(clean_phases, combined, pdf_options)
                unit_hdr = []
            if "OTHER" in m_data[unit]:
                for phase_list in m_data[unit]["OTHER"].values():
                    unit_id_photos.extend(
                        p for p in phase_list if p.get("url") not in hidden_urls
                    )
            id_fn = build_id_section_linear if m_is_linear else build_id_section
            elements += id_fn(unit_id_photos, _with_measure_hdr([]), pdf_options)

    elif m_sort_mode == LIGHTING_SORT_KEY:
        for location in m_data.get("locations", []):
            _render_lighting_location(
                location, pdf_options, elements,
                initial_headers=_initial_measure_headers(),
            )
            if not measure_hdr_used[0]:
                measure_hdr_used[0] = True
        top_untagged = [_lighting_photo_dict(p) for p in m_data.get("untagged", [])]
        if top_untagged:
            untagged_hdr = _with_measure_hdr(bldg_divider("Untagged"))
            elements += build_flat_linear_section(top_untagged, untagged_hdr, pdf_options)

    elif m_sort_mode == SUBCONTRACTED_SORT_KEY:
        _render_subcontracted_items(
            m_data.get("items", []), pdf_options, elements, m_is_linear, m_section_fn,
            initial_headers=_initial_measure_headers(),
        )
        measure_hdr_used[0] = True

    elif m_sort_mode == HEAT_PUMP_SORT_KEY:
        if m_data.get("locations"):
            _render_heat_pump_locations(
                m_data, pdf_options, elements, m_is_linear, m_section_fn,
                initial_headers=_initial_measure_headers(),
            )
        else:
            _render_heat_pump_buckets(
                m_data, pdf_options, elements, m_is_linear, m_section_fn,
                initial_headers=_initial_measure_headers(),
            )
        measure_hdr_used[0] = True

    elif m_sort_mode == MANUAL_ARRANGE_SORT_KEY:
        _render_manual_arrange_measure(
            m_data, pdf_options, elements, m_is_linear, m_section_fn,
            initial_headers=_initial_measure_headers(),
        )
        measure_hdr_used[0] = True

    else:  # unit_phase (default)
        for unit in sorted(m_data):
            phases = m_data[unit]
            if hide_empty and not _section_has_photos(phases):
                continue
            unit_default = f"Unit {unit if unit != 'UNASSIGNED' else 'Unassigned'}"
            unit_hdr = _maybe_unit_divider(
                resolve_heading_label(f"unit:{unit}", unit_default, pdf_options),
                pdf_options,
            )
            elements += m_section_fn(phases, _with_measure_hdr(unit_hdr), pdf_options)

    if not measure_hdr_used[0] and measure_hdr_pending and not hide_empty and not heading_is_full_page:
        elements.append(KeepTogether(list(measure_hdr_pending) + [
            Paragraph("No photos in this section.", style_no_photo),
            Spacer(1, 6),
        ]))

    if m_special:
        for room_name in sorted(m_special):
            phases = m_special[room_name]
            if hide_empty and not _section_has_photos(phases):
                continue
            resolved_room = resolve_heading_label(
                f"special:{room_name}", room_name, pdf_options,
            )
            room_hdr = special_room_divider(resolved_room)
            elements += m_section_fn(phases, room_hdr, pdf_options)

    pdf_options["show_photo_tags"] = saved_show_tags
    return elements


# ============================
# MAIN GENERATOR
# ============================
def generate_pdf_report(context, pdf_options=None, progress_callback=None):
    """
    pdf_options (dict, optional):
      layout            : "grid" (default) | "linear"
      hide_empty_fields : True | False
      hidden_photos     : list/set of photo URLs to omit
      cover_fields      : list of {key, value, visible} dicts
    progress_callback(done, total) called after each image fetch.
    """
    pdf_options  = pdf_options or {}
    layout       = pdf_options.get("layout", "grid")
    hidden_urls  = set(pdf_options.get("hidden_photos", []))
    pdf_options["hidden_photos"] = hidden_urls

    # Lighting PDF Report Adjustments: only linear mode is available,
    # regardless of what the dashboard/pdf_options requested.
    if context.get("sort_mode") == LIGHTING_SORT_KEY:
        layout = "linear"
    if context.get("sort_mode") == HEAT_PUMP_SORT_KEY:
        layout = "linear"

    is_linear  = (layout == "linear")
    section_fn = build_photo_section_linear if is_linear else build_photo_section

    project_name = context.get("project_name", context.get("project_id", "Report"))
    suffix       = f"_{layout.capitalize()}" if layout != "grid" else ""
    filename     = f"{project_name}_Report{suffix}.pdf".replace(" ", "_")

    base_dir    = paths.PROJECT_ROOT
    reports_dir = paths.REPORTS_DIR
    os.makedirs(reports_dir, exist_ok=True)
    save_path = os.path.join(reports_dir, filename)

    doc = SimpleDocTemplate(
        save_path,
        pagesize=letter,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=0.85 * inch,
        bottomMargin=0.5 * inch,
    )
    doc.project_name = project_name
    hf       = make_header_footer(project_name)
    elements = []

    # ── Progress tracking ─────────────────────────────────────────────────────
    data         = context.get("structured", {})
    sort_mode    = context.get("sort_mode", "full")
    special_data = context.get("special_rooms_structured", {})

    all_photos_flat = []
    if sort_mode == "multi":
        for m_entry in context.get("measures", []):
            all_photos_flat.extend(_collect_visible_photos(
                m_entry["structure"],
                m_entry.get("sort_mode") or "unit_phase",
                m_entry.get("special_rooms_structure", {}),
                hidden_urls,
            ))
    else:
        all_photos_flat = _collect_visible_photos(
            data, sort_mode, special_data, hidden_urls,
        )

    total_to_fetch = len(all_photos_flat)
    fetched_count  = [0]

    def fetch_with_progress(url, max_w, max_h, transform=None):
        path = fetch_image_to_temp(url, max_w, max_h, transform=transform)
        fetched_count[0] += 1
        if progress_callback:
            progress_callback(fetched_count[0], total_to_fetch)
        return path

    pdf_options["_fetch_fn"]     = fetch_with_progress
    pdf_options["_total_photos"] = total_to_fetch
    context["total_photos"]      = total_to_fetch

    hide_empty = pdf_options.get("hide_empty_fields", False)
    sub_unit_label = _sub_unit_label()

    # ─────────────────────────────────────────────────────────────────────────
    # MULTI-MEASURE RENDERING (chunked partial PDFs + merge)
    # ─────────────────────────────────────────────────────────────────────────
    if sort_mode == "multi":
        partial_paths = []
        page_offset = 0
        try:
            measures = context.get("measures", [])
            for idx, m_entry in enumerate(measures):
                elements = []
                if idx == 0:
                    build_cover_page(context, pdf_options, is_linear, base_dir, elements)
                elements.extend(_build_measure_elements(
                    m_entry, pdf_options, is_linear, hide_empty, hidden_urls, sub_unit_label,
                    omit_leading_break=True,
                ))

                mid = _safe_partial_name(m_entry.get("measure_id"), f"measure_{idx}")
                partial_filename = f"{project_name}_partial_{mid}.pdf".replace(" ", "_")
                partial_path = os.path.join(reports_dir, partial_filename)
                _generate_partial_pdf(elements, partial_path, project_name, page_offset=page_offset)
                partial_paths.append(partial_path)

                page_offset += len(PdfReader(partial_path).pages)
                del elements
                gc.collect()

            _merge_partial_pdfs(partial_paths, save_path)
        finally:
            for partial_path in partial_paths:
                try:
                    os.unlink(partial_path)
                except OSError:
                    pass

        print(f"[OK] PDF saved: {save_path}")
        return filename

    # ---- COVER PAGE (single-measure) ----
    build_cover_page(context, pdf_options, is_linear, base_dir, elements)

    _opts = pdf_options.get("measure_options") or {}
    if len(_opts) == 1:
        pdf_options["_current_measure_id"] = next(iter(_opts))

    # ── Skip-empty helper ─────────────────────────────────────────────────────
    def _section_has_photos(phases_dict):
        return any(
            p.get("url") not in hidden_urls
            for phase_list in phases_dict.values()
            for p in phase_list
        )

    # ---- CONTENT (single-measure) ----
    if sort_mode == "full":
        for bldg in sorted(data):
            bldg_default = f"Building {bldg if bldg != 'NO_BLDG' else 'Unassigned'}"
            bldg_hdr = _maybe_bldg_divider(
                resolve_heading_label(f"building:{bldg}", bldg_default, pdf_options),
                pdf_options,
            )
            for ui, unit in enumerate(sorted(data[bldg])):
                unit_default = f"Unit {unit if unit != 'UNASSIGNED' else 'Unassigned'}"
                unit_hdr = _maybe_unit_divider(
                    resolve_heading_label(f"unit:{bldg}:{unit}", unit_default, pdf_options),
                    pdf_options,
                )
                unit_id_photos = []   # accumulated across all baths in this unit

                real_baths = [b for b in sorted(data[bldg][unit]) if b != "OTHER"]
                for bath in real_baths:
                    phases = data[bldg][unit][bath]
                    # Collect UNTAGGED from every real bathroom too
                    unit_id_photos.extend(collect_id_photos(phases, hidden_urls))
                    # Build a stripped phases dict (BEFORE + AFTER only) for the main section
                    clean_phases = {k: v for k, v in phases.items() if k in ("BEFORE", "AFTER")}
                    if hide_empty and not _section_has_photos(clean_phases):
                        continue
                    bath_default = f"{bath.title()} {sub_unit_label}"
                    bath_hdr = _maybe_bath_divider(
                        resolve_heading_label(
                            f"bathroom:{bldg}:{unit}:{bath}", bath_default, pdf_options,
                        ),
                        pdf_options,
                    )
                    combined = bldg_hdr + unit_hdr + bath_hdr
                    elements += section_fn(clean_phases, combined, pdf_options)
                    bldg_hdr = []
                    unit_hdr = []

                # Collect everything from the OTHER bathroom (if present)
                if "OTHER" in data[bldg][unit]:
                    other_phases = data[bldg][unit]["OTHER"]
                    for phase_list in other_phases.values():
                        unit_id_photos.extend(
                            p for p in phase_list if p.get("url") not in hidden_urls
                        )

            # Emit the ID block (no extra heading) after the last real bathroom
            id_fn = build_id_section_linear if is_linear else build_id_section
            elements += id_fn(unit_id_photos, [], pdf_options)

    elif sort_mode == "bldg_unit_phase":
        for bldg in sorted(data):
            bldg_default = f"Building {bldg if bldg != 'NO_BLDG' else 'Unassigned'}"
            bldg_hdr = _maybe_bldg_divider(
                resolve_heading_label(f"building:{bldg}", bldg_default, pdf_options),
                pdf_options,
            )
            for unit in sorted(data[bldg]):
                phases = data[bldg][unit]
                if hide_empty and not _section_has_photos(phases):
                    continue
                unit_default = f"Unit {unit if unit != 'UNASSIGNED' else 'Unassigned'}"
                unit_hdr = _maybe_unit_divider(
                    resolve_heading_label(f"unit:{bldg}:{unit}", unit_default, pdf_options),
                    pdf_options,
                )
                combined = bldg_hdr + unit_hdr
                elements += section_fn(phases, combined, pdf_options)
                bldg_hdr = []

    elif sort_mode == "unit_bath_phase":
        for unit in sorted(data):
            unit_default = f"Unit {unit if unit != 'UNASSIGNED' else 'Unassigned'}"
            unit_hdr = _maybe_unit_divider(
                resolve_heading_label(f"unit:{unit}", unit_default, pdf_options),
                pdf_options,
            )
            unit_id_photos = []

            real_baths = [b for b in sorted(data[unit]) if b != "OTHER"]
            for bath in real_baths:
                phases = data[unit][bath]
                unit_id_photos.extend(collect_id_photos(phases, hidden_urls))
                clean_phases = {k: v for k, v in phases.items() if k in ("BEFORE", "AFTER")}
                if hide_empty and not _section_has_photos(clean_phases):
                    continue
                bath_default = f"{bath.title()} {sub_unit_label}"
                bath_hdr = _maybe_bath_divider(
                    resolve_heading_label(
                        f"bathroom:{unit}:{bath}", bath_default, pdf_options,
                    ),
                    pdf_options,
                )
                combined = unit_hdr + bath_hdr
                elements += section_fn(clean_phases, combined, pdf_options)
                unit_hdr = []

            if "OTHER" in data[unit]:
                other_phases = data[unit]["OTHER"]
                for phase_list in other_phases.values():
                    unit_id_photos.extend(
                        p for p in phase_list if p.get("url") not in hidden_urls
                    )

            id_fn = build_id_section_linear if is_linear else build_id_section
            elements += id_fn(unit_id_photos, [], pdf_options)

    elif sort_mode == LIGHTING_SORT_KEY:
        for location in data.get("locations", []):
            _render_lighting_location(location, pdf_options, elements)

        top_untagged = [_lighting_photo_dict(p) for p in data.get("untagged", [])]
        if top_untagged:
            untagged_hdr = bldg_divider("Untagged")
            elements += build_flat_linear_section(top_untagged, untagged_hdr, pdf_options)

    elif sort_mode == SUBCONTRACTED_SORT_KEY:
        _render_subcontracted_items(
            data.get("items", []), pdf_options, elements, is_linear, section_fn,
        )

    elif sort_mode == HEAT_PUMP_SORT_KEY:
        if data.get("locations"):
            _render_heat_pump_locations(data, pdf_options, elements, is_linear, section_fn)
        else:
            _render_heat_pump_buckets(data, pdf_options, elements, is_linear, section_fn)

    elif sort_mode == MANUAL_ARRANGE_SORT_KEY:
        _render_manual_arrange_measure(
            data, pdf_options, elements, is_linear, section_fn,
        )

    else:  # unit_phase
        for unit in sorted(data):
            phases = data[unit]
            if hide_empty and not _section_has_photos(phases):
                continue
            unit_default = f"Unit {unit if unit != 'UNASSIGNED' else 'Unassigned'}"
            unit_hdr = _maybe_unit_divider(
                resolve_heading_label(f"unit:{unit}", unit_default, pdf_options),
                pdf_options,
            )
            elements += section_fn(phases, unit_hdr, pdf_options)

    # ---- SPECIAL ROOMS ----
    if special_data:
        for room_name in sorted(special_data):
            phases = special_data[room_name]
            if hide_empty and not _section_has_photos(phases):
                continue
            resolved_room = resolve_heading_label(
                f"special:{room_name}", room_name, pdf_options,
            )
            room_hdr = special_room_divider(resolved_room)
            elements += section_fn(phases, room_hdr, pdf_options)

    doc.build(elements, onFirstPage=hf, onLaterPages=hf)
    print(f"[OK] PDF saved: {save_path}")
    return filename