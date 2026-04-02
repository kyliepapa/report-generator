#This is pdf_generator.py

from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Image, PageBreak,
    Table, TableStyle, HRFlowable, KeepTogether
)
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from datetime import datetime
import os
import requests
from io import BytesIO

from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

session = requests.Session()
retries = Retry(total=3, backoff_factor=0.5)
session.mount('http://', HTTPAdapter(max_retries=retries))
session.mount('https://', HTTPAdapter(max_retries=retries))

# ============================
# PAGE GEOMETRY — GRID MODE
# ============================
PAGE_W, PAGE_H = letter
MARGIN    = 0.6 * inch
CONTENT_W = PAGE_W - 2 * MARGIN

# Two photo columns separated by a small gutter
GUTTER  = 0.12 * inch
IMG_W   = (CONTENT_W - GUTTER) / 2   # full column width per photo side

# Each column is split: image portion + caption strip on the outside
CAPTION_W = 1.05 * inch
PHOTO_W   = IMG_W - CAPTION_W        # actual rendered image width

# Photo height — sized so 2 rows fit comfortably on a page
IMG_H = 3.05 * inch

# ============================
# PAGE GEOMETRY — LINEAR MODE
# ============================
# Photo takes left ~60% of content width; caption takes right ~40%
LINEAR_PHOTO_W   = CONTENT_W * 0.58
LINEAR_CAPTION_W = CONTENT_W * 0.42
# Target 3-4 photos per page → each row ~2.1" tall
LINEAR_IMG_H     = 2.1 * inch
LINEAR_IMG_W     = LINEAR_PHOTO_W   # image fills the photo column

# ============================
# STYLES
# ============================
_base = getSampleStyleSheet()

style_title    = ParagraphStyle("CoverTitle",  fontSize=26, leading=32, alignment=TA_CENTER, spaceAfter=6,  textColor=colors.HexColor("#1a2535"), fontName="Helvetica-Bold")
style_subtitle = ParagraphStyle("CoverSub",    fontSize=13, leading=17, alignment=TA_CENTER, spaceAfter=4,  textColor=colors.HexColor("#2e86de"))
style_meta     = ParagraphStyle("CoverMeta",   fontSize=10, leading=14, alignment=TA_CENTER, spaceAfter=2,  textColor=colors.HexColor("#636e72"))
style_bldg     = ParagraphStyle("BldgHdr",     fontSize=14, leading=18, spaceAfter=2, spaceBefore=5, textColor=colors.HexColor("#1a2535"), fontName="Helvetica-Bold")
style_unit     = ParagraphStyle("UnitHdr",     fontSize=12, leading=16, spaceAfter=2, spaceBefore=3, textColor=colors.HexColor("#2e86de"), fontName="Helvetica-Bold")
style_bath     = ParagraphStyle("BathHdr",     fontSize=10, leading=13, spaceAfter=1, spaceBefore=2, textColor=colors.HexColor("#636e72"), fontName="Helvetica-Bold")
style_phase    = ParagraphStyle("PhaseLabel",  fontSize=7.5, leading=10, alignment=TA_CENTER, textColor=colors.white, fontName="Helvetica-Bold")
style_untag_hdr= ParagraphStyle("UntagHdr",    fontSize=9,  leading=12, spaceAfter=2, spaceBefore=4, textColor=colors.HexColor("#7f8c8d"), fontName="Helvetica-Bold")

# Caption text styles — grid mode (outer captions face the image)
style_cap_L    = ParagraphStyle("CapL",  fontSize=6.5, leading=9,   alignment=TA_RIGHT, textColor=colors.HexColor("#444444"), spaceAfter=2)
style_cap_L2   = ParagraphStyle("CapL2", fontSize=6,   leading=8.5, alignment=TA_RIGHT, textColor=colors.HexColor("#888888"), spaceAfter=1)
style_cap_R    = ParagraphStyle("CapR",  fontSize=6.5, leading=9,   alignment=TA_LEFT,  textColor=colors.HexColor("#444444"), spaceAfter=2)
style_cap_R2   = ParagraphStyle("CapR2", fontSize=6,   leading=8.5, alignment=TA_LEFT,  textColor=colors.HexColor("#888888"), spaceAfter=1)

# Caption text styles — linear mode (caption always to the right of image)
style_lin_cap  = ParagraphStyle("LinCap",  fontSize=7.5, leading=11, alignment=TA_LEFT, textColor=colors.HexColor("#333333"), spaceAfter=3)
style_lin_cap2 = ParagraphStyle("LinCap2", fontSize=6.5, leading=9.5, alignment=TA_LEFT, textColor=colors.HexColor("#777777"), spaceAfter=2)

style_no_photo = ParagraphStyle("NoPhoto", fontSize=8, leading=11, alignment=TA_CENTER, textColor=colors.HexColor("#bbbbbb"), fontName="Helvetica-Oblique")

BEFORE_COLOR   = colors.HexColor("#7f8c8d")
AFTER_COLOR    = colors.HexColor("#7f8c8d")
UNTAGGED_COLOR = colors.HexColor("#7f8c8d")
DIVIDER_COLOR  = colors.HexColor("#dde3ed")
HEADER_BG      = colors.HexColor("#1a2535")


# ============================
# IMAGE FETCHER
# ============================
from PIL import Image as PILImage

def fetch_image(url, max_w=PHOTO_W, max_h=IMG_H):
    try:
        r = session.get(url, timeout=8)
        if r.status_code == 200:
            pil_img = PILImage.open(BytesIO(r.content))

            if pil_img.mode in ("RGBA", "P"):
                pil_img = pil_img.convert("RGB")

            TARGET_PX = 1200
            pil_img.thumbnail((TARGET_PX, TARGET_PX))

            buffer = BytesIO()
            pil_img.save(buffer, format="JPEG", quality=80, optimize=True)
            buffer.seek(0)

            img = Image(buffer)

            iw, ih = img.imageWidth, img.imageHeight
            if iw and ih:
                ratio = min(max_w / iw, max_h / ih)
                img.drawWidth  = iw * ratio
                img.drawHeight = ih * ratio
            else:
                img.drawWidth, img.drawHeight = max_w, max_h

            return img

    except Exception as e:
        print(f"[IMG FETCH ERROR] {e}")

    return None


# ============================
# HEADER / FOOTER
# ============================
def make_header_footer(project_name):
    def _draw(canvas, doc):
        canvas.saveState()
        w, h = letter

        # Header bar
        canvas.setFillColor(HEADER_BG)
        canvas.rect(0, h - 26, w, 26, fill=1, stroke=0)
        canvas.setFont("Helvetica-Bold", 8.5)
        canvas.setFillColor(colors.white)
        canvas.drawString(MARGIN, h - 17, "Aquamizer Report Generator")
        canvas.drawRightString(w - MARGIN, h - 17, project_name)

        # Footer
        canvas.setStrokeColor(DIVIDER_COLOR)
        canvas.setLineWidth(0.5)
        canvas.line(MARGIN, 28, w - MARGIN, 28)
        canvas.setFillColor(colors.HexColor("#999999"))
        canvas.setFont("Helvetica", 7.5)
        canvas.drawString(MARGIN, 14, "Bottom Line Utility Solutions, Inc.")
        canvas.drawCentredString(w / 2, 14, f"Page {doc.page}")
        canvas.drawRightString(w - MARGIN, 14, project_name)

        canvas.restoreState()
    return _draw


# ============================
# PHASE STRIP  (grid mode only)
# ============================
def phase_strip(label, color, width):
    tbl = Table([[Paragraph(label, style_phase)]], colWidths=[width], rowHeights=[13])
    tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), color),
        ("ALIGN",         (0,0),(-1,-1), "CENTER"),
        ("TOPPADDING",    (0,0),(-1,-1), 1),
        ("BOTTOMPADDING", (0,0),(-1,-1), 1),
        ("LEFTPADDING",   (0,0),(-1,-1), 0),
        ("RIGHTPADDING",  (0,0),(-1,-1), 0),
    ]))
    return tbl


# ============================
# CAPTION BUILDER — grid mode
# ============================
def build_captions(photo, side):
    cs  = style_cap_L  if side == "left" else style_cap_R
    cs2 = style_cap_L2 if side == "left" else style_cap_R2
    items = []
    if not photo:
        return [Paragraph("—", cs)]

    ts = "Unknown"
    try:
        ts = datetime.fromtimestamp(int(photo.get("captured_at"))).strftime("%Y-%m-%d %H:%M")
    except:
        pass
    items.append(Paragraph(f"📷 {ts}", cs))

    tag_str = (photo.get("tag_string") or "").strip()
    for part in tag_str.split(" — "):
        if part.strip():
            items.append(Paragraph(part.strip(), cs))

    extras = (photo.get("extra_tags") or "").strip()
    if extras:
        filtered = ", ".join(
            t for t in extras.split(", ")
            if t.strip() and not t.strip().isdigit()
        )
        if filtered:
            items.append(Paragraph(f"Tags: {filtered}", cs2))

    lat, lon = photo.get("latitude"), photo.get("longitude")
    if lat and lon:
        geo_url = f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"
        items.append(Paragraph(
            f'<link href="{geo_url}"><u>📍 {lat:.4f}, {lon:.4f}</u></link>', cs2
        ))

    return items


# ============================
# CAPTION BUILDER — linear mode
# ============================
def build_captions_linear(photo):
    """Returns caption paragraphs for the right-side column in linear layout."""
    items = []
    if not photo:
        return [Paragraph("—", style_lin_cap)]

    ts = "Unknown"
    try:
        ts = datetime.fromtimestamp(int(photo.get("captured_at"))).strftime("%Y-%m-%d %H:%M")
    except:
        pass
    items.append(Paragraph(f"📷  {ts}", style_lin_cap))

    tag_str = (photo.get("tag_string") or "").strip()
    for part in tag_str.split(" — "):
        if part.strip():
            items.append(Paragraph(part.strip(), style_lin_cap))

    extras = (photo.get("extra_tags") or "").strip()
    if extras:
        filtered = ", ".join(
            t for t in extras.split(", ")
            if t.strip() and not t.strip().isdigit()
        )
        if filtered:
            items.append(Paragraph(f"Tags: {filtered}", style_lin_cap2))

    lat, lon = photo.get("latitude"), photo.get("longitude")
    if lat and lon:
        geo_url = f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"
        items.append(Paragraph(
            f'<link href="{geo_url}"><u>📍 {lat:.4f}, {lon:.4f}</u></link>',
            style_lin_cap2
        ))

    return items


# ============================
# PHOTO COLUMN BUILDER — grid mode
# ============================
def build_photo_col(photo, phase_color, phase_label, side):
    strip    = phase_strip(phase_label, phase_color, IMG_W)
    captions = build_captions(photo, side)

    if photo and photo.get("url"):
        img = fetch_image(photo["url"])
        img_cell = [img] if img else [Paragraph("[ unavailable ]", style_no_photo)]
    else:
        img_cell = [Spacer(1, 0.15*inch), Paragraph("No photo available", style_no_photo)]

    if side == "left":
        inner_data   = [captions, img_cell]
        inner_widths = [CAPTION_W, PHOTO_W]
    else:
        inner_data   = [img_cell, captions]
        inner_widths = [PHOTO_W, CAPTION_W]

    inner = Table([inner_data], colWidths=inner_widths)
    inner.setStyle(TableStyle([
        ("VALIGN",       (0,0),(-1,-1), "MIDDLE"),
        ("LEFTPADDING",  (0,0),(-1,-1), 3),
        ("RIGHTPADDING", (0,0),(-1,-1), 3),
        ("TOPPADDING",   (0,0),(-1,-1), 5),
        ("BOTTOMPADDING",(0,0),(-1,-1), 5),
    ]))

    return [strip, inner]


# ============================
# COMPARISON ROW — grid mode  (Before | After)
# ============================
def build_comparison_row(before_photo, after_photo):
    left  = build_photo_col(before_photo, BEFORE_COLOR, "BEFORE", "left")
    right = build_photo_col(after_photo,  AFTER_COLOR,  "AFTER",  "right")

    tbl = Table([[left, right]], colWidths=[IMG_W, IMG_W])
    tbl.setStyle(TableStyle([
        ("VALIGN",       (0,0),(-1,-1), "TOP"),
        ("LEFTPADDING",  (0,0),(-1,-1), 0),
        ("RIGHTPADDING", (0,0),(-1,-1), 0),
        ("TOPPADDING",   (0,0),(-1,-1), 0),
        ("BOTTOMPADDING",(0,0),(-1,-1), 0),
        ("BOX",          (0,0),(-1,-1), 0.75, DIVIDER_COLOR),
        ("LINEAFTER",    (0,0),(0,-1),  0.75, DIVIDER_COLOR),
    ]))
    return tbl


# ============================
# SINGLE-PHOTO ROW — grid mode (for hide-empty fill or lone left-column photo)
# ============================
def build_single_row(photo, side="left"):
    """Renders one photo in the grid layout; the other half is whitespace."""
    col = build_photo_col(photo, BEFORE_COLOR if side == "left" else AFTER_COLOR,
                          "BEFORE" if side == "left" else "AFTER", side)
    blank = [Spacer(1, IMG_H)]   # tasteful empty column

    if side == "left":
        data = [col, blank]
    else:
        data = [blank, col]

    tbl = Table([data], colWidths=[IMG_W, IMG_W])
    tbl.setStyle(TableStyle([
        ("VALIGN",       (0,0),(-1,-1), "TOP"),
        ("LEFTPADDING",  (0,0),(-1,-1), 0),
        ("RIGHTPADDING", (0,0),(-1,-1), 0),
        ("TOPPADDING",   (0,0),(-1,-1), 0),
        ("BOTTOMPADDING",(0,0),(-1,-1), 0),
    ]))
    return tbl


# ============================
# UNTAGGED ROWS — grid mode, paired side by side
# ============================
def build_untagged_pair(photo_left, photo_right=None):
    left  = build_photo_col(photo_left,  UNTAGGED_COLOR, "ID", "left")
    right = build_photo_col(photo_right, UNTAGGED_COLOR, "ID", "right") if photo_right else [Spacer(1, 0.1*inch)]

    tbl = Table([[left, right]], colWidths=[IMG_W, IMG_W])
    tbl.setStyle(TableStyle([
        ("VALIGN",       (0,0),(-1,-1), "TOP"),
        ("LEFTPADDING",  (0,0),(-1,-1), 0),
        ("RIGHTPADDING", (0,0),(-1,-1), 0),
        ("TOPPADDING",   (0,0),(-1,-1), 0),
        ("BOTTOMPADDING",(0,0),(-1,-1), 0),
        ("BOX",          (0,0),(-1,-1), 0.75, DIVIDER_COLOR),
        ("LINEAFTER",    (0,0),(0,-1),  0.75, DIVIDER_COLOR),
    ]))
    return tbl


# ============================
# LINEAR-MODE ROW BUILDER
# One photo (left) + metadata column (right), no phase badge, no borders.
# ============================
def build_linear_row(photo):
    """Single photo + caption row for linear layout."""
    if photo and photo.get("url"):
        img = fetch_image(photo["url"], max_w=LINEAR_IMG_W, max_h=LINEAR_IMG_H)
        img_cell = [img] if img else [Paragraph("[ unavailable ]", style_no_photo)]
    else:
        img_cell = [Spacer(1, LINEAR_IMG_H * 0.5), Paragraph("No photo available", style_no_photo)]

    captions = build_captions_linear(photo)

    tbl = Table([[img_cell, captions]],
                colWidths=[LINEAR_PHOTO_W, LINEAR_CAPTION_W])
    tbl.setStyle(TableStyle([
        ("VALIGN",       (0,0),(-1,-1), "MIDDLE"),
        ("LEFTPADDING",  (0,0),(0,-1),  0),
        ("RIGHTPADDING", (0,0),(0,-1),  8),
        ("LEFTPADDING",  (1,0),(1,-1),  10),
        ("RIGHTPADDING", (1,0),(1,-1),  0),
        ("TOPPADDING",   (0,0),(-1,-1), 6),
        ("BOTTOMPADDING",(0,0),(-1,-1), 6),
    ]))
    return tbl


# ============================
# SECTION BUILDER — grid mode
# ============================
ROWS_PER_GROUP = 2

def build_photo_section(phases_dict, header_elements, pdf_options=None):
    """
    Builds grid-layout photo rows for a section.

    pdf_options keys used here:
      hide_empty_fields (bool) — skip Before/After slot if no photo; fill with untagged if available
      hidden_photos (set)      — URLs to omit entirely
    """
    pdf_options    = pdf_options or {}
    hide_empty     = pdf_options.get("hide_empty_fields", False)
    hidden_urls    = pdf_options.get("hidden_photos", set())

    elements = []

    before_list   = [p for p in phases_dict.get("BEFORE",   []) if p.get("url") not in hidden_urls]
    after_list    = [p for p in phases_dict.get("AFTER",    []) if p.get("url") not in hidden_urls]
    untagged_list = [p for p in phases_dict.get("UNTAGGED", []) if p.get("url") not in hidden_urls]

    # ── Hide-empty-fields mode ────────────────────────────────────────────────
    if hide_empty:
        # Pool of spare untagged photos to fill lone slots
        spare_untagged = list(untagged_list)

        # We need to decide which photos to actually show.
        # Strategy: pair them up as before/after. Where one side is missing,
        # try to fill with a spare untagged. Where neither exists, skip the row.
        rows = max(len(before_list), len(after_list))

        if rows == 0:
            # No before/after at all — nothing to show for this section
            return elements   # skip headers too if truly empty

        comp_rows = []
        for i in range(rows):
            b = before_list[i] if i < len(before_list) else None
            a = after_list[i]  if i < len(after_list)  else None

            if b is None and a is not None:
                # Lone After — shift to left column
                comp_rows.append(build_single_row(a, side="left"))
            elif b is not None and a is None:
                # Lone Before — try to fill After slot with untagged
                filler = spare_untagged.pop(0) if spare_untagged else None
                if filler:
                    comp_rows.append(build_comparison_row(b, filler))
                else:
                    comp_rows.append(build_single_row(b, side="left"))
            else:
                comp_rows.append(build_comparison_row(b, a))

        # Untagged photos that weren't used as fillers — show in own rows
        remaining_untagged = spare_untagged

    else:
        rows = max(len(before_list), len(after_list))

        if rows == 0 and not untagged_list:
            block = list(header_elements) + [
                Paragraph("No photos in this section.", style_no_photo),
                Spacer(1, 6),
            ]
            elements.append(KeepTogether(block))
            return elements

        comp_rows = []
        for i in range(rows):
            b = before_list[i] if i < len(before_list) else None
            a = after_list[i]  if i < len(after_list)  else None
            comp_rows.append(build_comparison_row(b, a))

        remaining_untagged = untagged_list

    # Group comparison rows; first group carries headers
    for gi, start in enumerate(range(0, len(comp_rows), ROWS_PER_GROUP)):
        group = comp_rows[start : start + ROWS_PER_GROUP]
        spaced = []
        for row in group:
            spaced.append(row)
            spaced.append(Spacer(1, 5))
        block = (list(header_elements) + spaced) if gi == 0 else spaced
        elements.append(KeepTogether(block))

    # Remaining untagged rows
    if remaining_untagged:
        untag_rows = []
        for i in range(0, len(remaining_untagged), 2):
            untag_rows.append(build_untagged_pair(
                remaining_untagged[i],
                remaining_untagged[i+1] if i+1 < len(remaining_untagged) else None
            ))
        untag_hdr = [
            HRFlowable(width="100%", thickness=0.5, color=DIVIDER_COLOR, spaceAfter=2),
            Paragraph("Identification", style_untag_hdr),
        ]
        for gi, start in enumerate(range(0, len(untag_rows), ROWS_PER_GROUP)):
            group = untag_rows[start : start + ROWS_PER_GROUP]
            spaced = []
            for row in group:
                spaced.append(row)
                spaced.append(Spacer(1, 5))
            block = (untag_hdr + spaced) if gi == 0 else spaced
            elements.append(KeepTogether(block))

    return elements


# ============================
# SECTION BUILDER — linear mode
# ============================
LINEAR_ROWS_PER_GROUP = 3   # keep 3 photos together to avoid orphans

def build_photo_section_linear(phases_dict, header_elements, pdf_options=None):
    """
    Builds linear-layout photo rows for a section.
    All photos run vertically in a single column; phase badge omitted.
    """
    pdf_options = pdf_options or {}
    hidden_urls = pdf_options.get("hidden_photos", set())

    elements = []

    all_photos = []
    for phase in ("BEFORE", "AFTER", "UNTAGGED"):
        for p in phases_dict.get(phase, []):
            if p.get("url") not in hidden_urls:
                all_photos.append(p)

    if not all_photos:
        block = list(header_elements) + [
            Paragraph("No photos in this section.", style_no_photo),
            Spacer(1, 6),
        ]
        elements.append(KeepTogether(block))
        return elements

    rows = [build_linear_row(p) for p in all_photos]

    for gi, start in enumerate(range(0, len(rows), LINEAR_ROWS_PER_GROUP)):
        group = rows[start : start + LINEAR_ROWS_PER_GROUP]
        spaced = []
        for row in group:
            spaced.append(row)
            spaced.append(HRFlowable(width="100%", thickness=0.3,
                                     color=colors.HexColor("#eeeeee"), spaceAfter=2))
        block = (list(header_elements) + spaced) if gi == 0 else spaced
        elements.append(KeepTogether(block))

    return elements


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


# ============================
# MAIN GENERATOR
# ============================
def generate_pdf_report(context, pdf_options=None, progress_callback=None):
    """
    pdf_options (dict, optional):
      layout          : "grid" (default) | "linear"
      hide_empty_fields: True | False   (grid mode only)
      hidden_photos   : set of photo URLs to omit

    progress_callback(done, total):
      Called after each photo is fetched so the caller can track progress.
    """
    pdf_options   = pdf_options or {}
    layout        = pdf_options.get("layout", "grid")
    hidden_urls   = set(pdf_options.get("hidden_photos", []))
    pdf_options["hidden_photos"] = hidden_urls   # normalise to set

    is_linear = (layout == "linear")

    # Choose section builder
    section_fn = build_photo_section_linear if is_linear else build_photo_section

    project_name = context.get("project_name", context.get("project_id", "Report"))
    suffix       = f"_{layout.capitalize()}" if layout != "grid" else ""
    filename     = f"{project_name}_Report{suffix}.pdf".replace(" ", "_")

    base_dir    = os.path.dirname(os.path.abspath(__file__))
    reports_dir = os.path.join(base_dir, "static", "reports")
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
    hf = make_header_footer(project_name)
    elements = []

    # ── Count total photos for progress tracking ──────────────────────────────
    data      = context["structured"]
    sort_mode = context.get("sort_mode", "full")
    special_data = context.get("special_rooms_structured", {})

    all_photos_flat = []
    def _collect_photos(phases_dict):
        for phase_list in phases_dict.values():
            for p in phase_list:
                if p.get("url") not in hidden_urls:
                    all_photos_flat.append(p)

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
    else:
        for unit in data:
            _collect_photos(data[unit])
    for room in special_data:
        _collect_photos(special_data[room])

    total_to_fetch = len(all_photos_flat)
    fetched_count  = [0]   # mutable counter

    # Wrap fetch_image to emit progress
    def fetch_with_progress(url, max_w, max_h):
        img = fetch_image(url, max_w=max_w, max_h=max_h)
        fetched_count[0] += 1
        if progress_callback:
            progress_callback(fetched_count[0], total_to_fetch)
        return img

    # Monkey-patch a local version so section builders use it
    # (We store it in pdf_options and pass through; section builders call it if present)
    pdf_options["_fetch_fn"]      = fetch_with_progress
    pdf_options["_total_photos"]  = total_to_fetch

    # ---- COVER PAGE ----
    logo_path = os.path.join(base_dir, "static", "logo.png")
    if os.path.exists(logo_path):
        _raw = Image(logo_path)
        lw, lh = _raw.imageWidth, _raw.imageHeight
        max_logo_w, max_logo_h = 3.2 * inch, 1.6 * inch
        if lw and lh:
            ratio = min(max_logo_w / lw, max_logo_h / lh)
            logo = Image(logo_path, width=lw*ratio, height=lh*ratio)
        else:
            logo = Image(logo_path, width=max_logo_w, height=max_logo_h)
        logo.hAlign = "CENTER"
        elements.append(Spacer(1, 1.0*inch))
        elements.append(logo)
        elements.append(Spacer(1, 0.45*inch))
    else:
        elements.append(Spacer(1, 2.2*inch))

    elements.append(Paragraph("INSTALLATION PHOTOS", style_subtitle))
    elements.append(Spacer(1, 0.12*inch))
    elements.append(Paragraph(context.get("project_name_upper", project_name.upper()), style_title))
    elements.append(Spacer(1, 0.28*inch))
    elements.append(HRFlowable(width="55%", thickness=1.5, color=colors.HexColor("#2e86de"), hAlign="CENTER"))
    elements.append(Spacer(1, 0.22*inch))
    elements.append(Paragraph(context.get("address", ""), style_meta))
    elements.append(Paragraph(f"Date: {context.get('date_generated', '')}", style_meta))
    elements.append(Spacer(1, 0.12*inch))

    for key, label in [("total_buildings","Buildings"),("total_units","Units"),
                        ("total_bathrooms","Bathrooms"),("total_photos","Total Photos")]:
        if context.get(key):
            elements.append(Paragraph(f"{label}: {context[key]}", style_meta))

    # Layout badge on cover
    layout_label = "Linear Layout" if is_linear else "Grid Layout"
    elements.append(Spacer(1, 0.08*inch))
    elements.append(Paragraph(layout_label, style_meta))

    elements.append(PageBreak())

    # ── Helper to decide whether a section should be skipped in hide-empty mode ──
    def _section_has_photos(phases_dict):
        for phase_list in phases_dict.values():
            for p in phase_list:
                if p.get("url") not in hidden_urls:
                    return True
        return False

    hide_empty = pdf_options.get("hide_empty_fields", False)

    # ---- CONTENT ----
    if sort_mode == "full":
        for bldg in sorted(data):
            bldg_hdr = bldg_divider(f"Building {bldg if bldg != 'NO_BLDG' else 'Unassigned'}")
            for ui, unit in enumerate(sorted(data[bldg])):
                unit_hdr = unit_divider(f"Unit {unit if unit != 'UNASSIGNED' else 'Unassigned'}")
                for bi, bath in enumerate(sorted(data[bldg][unit])):
                    phases = data[bldg][unit][bath]
                    if hide_empty and not _section_has_photos(phases):
                        continue
                    bath_hdr = bath_divider(f"{bath.title()} Bathroom")
                    combined = bldg_hdr + unit_hdr + bath_hdr
                    elements += section_fn(phases, combined, pdf_options)
                    bldg_hdr = []
                    unit_hdr = []

    elif sort_mode == "bldg_unit_phase":
        for bldg in sorted(data):
            bldg_hdr = bldg_divider(f"Building {bldg if bldg != 'NO_BLDG' else 'Unassigned'}")
            for unit in sorted(data[bldg]):
                phases = data[bldg][unit]
                if hide_empty and not _section_has_photos(phases):
                    continue
                unit_hdr = unit_divider(f"Unit {unit if unit != 'UNASSIGNED' else 'Unassigned'}")
                combined = bldg_hdr + unit_hdr
                elements += section_fn(phases, combined, pdf_options)
                bldg_hdr = []

    elif sort_mode == "unit_bath_phase":
        for unit in sorted(data):
            unit_hdr = unit_divider(f"Unit {unit if unit != 'UNASSIGNED' else 'Unassigned'}")
            for bath in sorted(data[unit]):
                phases = data[unit][bath]
                if hide_empty and not _section_has_photos(phases):
                    continue
                bath_hdr = bath_divider(f"{bath.title()} Bathroom")
                combined = unit_hdr + bath_hdr
                elements += section_fn(phases, combined, pdf_options)
                unit_hdr = []

    else:  # unit_phase
        for unit in sorted(data):
            phases = data[unit]
            if hide_empty and not _section_has_photos(phases):
                continue
            unit_hdr = unit_divider(f"Unit {unit if unit != 'UNASSIGNED' else 'Unassigned'}")
            elements += section_fn(phases, unit_hdr, pdf_options)

    # ---- SPECIAL ROOMS ----
    if special_data:
        for room_name in sorted(special_data):
            phases = special_data[room_name]
            if hide_empty and not _section_has_photos(phases):
                continue
            room_hdr = special_room_divider(room_name)
            elements += section_fn(phases, room_hdr, pdf_options)

    doc.build(elements, onFirstPage=hf, onLaterPages=hf)
    print(f"[OK] PDF saved: {save_path}")
    return filename