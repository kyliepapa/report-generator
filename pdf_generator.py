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
# PAGE GEOMETRY
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
# Usable body height ≈ 11 - 0.85(top) - 0.5(bottom) - 0.26(header) - 0.28(footer) ≈ 9.1"
# 2 rows + inter-row spacing: each row gets ~4.35" total; image gets ~3.1"
IMG_H = 3.05 * inch

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

# Caption text — left-photo captions are right-aligned (faces the image to its right),
# right-photo captions are left-aligned (faces the image to its left).
style_cap_L    = ParagraphStyle("CapL",  fontSize=6.5, leading=9,   alignment=TA_RIGHT, textColor=colors.HexColor("#444444"), spaceAfter=2)
style_cap_L2   = ParagraphStyle("CapL2", fontSize=6,   leading=8.5, alignment=TA_RIGHT, textColor=colors.HexColor("#888888"), spaceAfter=1)
style_cap_R    = ParagraphStyle("CapR",  fontSize=6.5, leading=9,   alignment=TA_LEFT,  textColor=colors.HexColor("#444444"), spaceAfter=2)
style_cap_R2   = ParagraphStyle("CapR2", fontSize=6,   leading=8.5, alignment=TA_LEFT,  textColor=colors.HexColor("#888888"), spaceAfter=1)
style_no_photo = ParagraphStyle("NoPhoto", fontSize=8, leading=11, alignment=TA_CENTER, textColor=colors.HexColor("#bbbbbb"), fontName="Helvetica-Oblique")

BEFORE_COLOR   = colors.HexColor("#c0392b")
AFTER_COLOR    = colors.HexColor("#10ac84")
UNTAGGED_COLOR = colors.HexColor("#7f8c8d")
DIVIDER_COLOR  = colors.HexColor("#dde3ed")
HEADER_BG      = colors.HexColor("#1a2535")


# ============================
# IMAGE FETCHER
# ============================
def fetch_image(url, max_w=PHOTO_W, max_h=IMG_H):
    try:
        r = session.get(url, timeout=8)
        if r.status_code == 200:
            img = Image(BytesIO(r.content))
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
# PHASE STRIP
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
# CAPTION BUILDER
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
# PHOTO COLUMN BUILDER
# Produces a mini 2-column table: [caption | image] for left side,
# [image | caption] for right side.
# ============================
def build_photo_col(photo, phase_color, phase_label, side):
    strip   = phase_strip(phase_label, phase_color, IMG_W)
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
# COMPARISON ROW  (Before | After)
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
# UNTAGGED ROWS — paired side by side
# ============================
def build_untagged_pair(photo_left, photo_right=None):
    """Two untagged photos side by side (outer captions), or one on the left."""
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
# SECTION BUILDER
# Bundles ALL enclosing headers with the first photo row so a page
# never ends with only headings. Rows are also grouped in pairs so
# the layout targets ~2 rows per page.
# ============================
ROWS_PER_GROUP = 2

def build_photo_section(phases_dict, header_elements):
    elements = []

    before_list   = phases_dict.get("BEFORE",   [])
    after_list    = phases_dict.get("AFTER",    [])
    untagged_list = phases_dict.get("UNTAGGED", [])

    rows = max(len(before_list), len(after_list))

    if rows == 0 and not untagged_list:
        block = list(header_elements) + [
            Paragraph("No photos in this section.", style_no_photo),
            Spacer(1, 6),
        ]
        elements.append(KeepTogether(block))
        return elements

    # Build comparison rows
    comp_rows = []
    for i in range(rows):
        b = before_list[i] if i < len(before_list) else None
        a = after_list[i]  if i < len(after_list)  else None
        comp_rows.append(build_comparison_row(b, a))

    # Group into pairs; first group carries all the headers
    for gi, start in enumerate(range(0, len(comp_rows), ROWS_PER_GROUP)):
        group = comp_rows[start : start + ROWS_PER_GROUP]
        # Add a small spacer between rows within the group
        spaced = []
        for row in group:
            spaced.append(row)
            spaced.append(Spacer(1, 5))

        if gi == 0:
            block = list(header_elements) + spaced
        else:
            block = spaced
        elements.append(KeepTogether(block))

    # Untagged photos — own sub-header, grouped the same way
    if untagged_list:
        untag_rows = []
        for i in range(0, len(untagged_list), 2):
            untag_rows.append(build_untagged_pair(
                untagged_list[i],
                untagged_list[i+1] if i+1 < len(untagged_list) else None
            ))
        untag_hdr  = [
            HRFlowable(width="100%", thickness=0.5, color=DIVIDER_COLOR, spaceAfter=2),
            Paragraph("Identification", style_untag_hdr),
        ]
        for gi, start in enumerate(range(0, len(untag_rows), ROWS_PER_GROUP)):
            group = untag_rows[start : start + ROWS_PER_GROUP]
            spaced = []
            for row in group:
                spaced.append(row)
                spaced.append(Spacer(1, 5))
            if gi == 0:
                block = untag_hdr + spaced
            else:
                block = spaced
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
def generate_pdf_report(context):
    project_name = context.get("project_name", context.get("project_id", "Report"))
    filename     = f"{project_name}_Report.pdf".replace(" ", "_")

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

    elements.append(PageBreak())

    # ---- CONTENT ----
    data      = context["structured"]
    sort_mode = context.get("sort_mode", "full")

    if sort_mode == "full":
        for bldg in sorted(data):
            bldg_hdr = bldg_divider(f"Building {bldg if bldg != 'NO_BLDG' else 'Unassigned'}")
            for ui, unit in enumerate(sorted(data[bldg])):
                unit_hdr = unit_divider(f"Unit {unit if unit != 'UNASSIGNED' else 'Unassigned'}")
                for bi, bath in enumerate(sorted(data[bldg][unit])):
                    bath_hdr = bath_divider(f"{bath.title()} Bathroom")
                    combined = bldg_hdr + unit_hdr + bath_hdr
                    elements += build_photo_section(data[bldg][unit][bath], combined)
                    # Only show bldg header on the very first section
                    bldg_hdr = []
                    unit_hdr = []   # only show unit header on first bath of unit

    elif sort_mode == "bldg_unit_phase":
        for bldg in sorted(data):
            bldg_hdr = bldg_divider(f"Building {bldg if bldg != 'NO_BLDG' else 'Unassigned'}")
            for unit in sorted(data[bldg]):
                unit_hdr = unit_divider(f"Unit {unit if unit != 'UNASSIGNED' else 'Unassigned'}")
                combined = bldg_hdr + unit_hdr
                elements += build_photo_section(data[bldg][unit], combined)
                bldg_hdr = []

    elif sort_mode == "unit_bath_phase":
        for unit in sorted(data):
            unit_hdr = unit_divider(f"Unit {unit if unit != 'UNASSIGNED' else 'Unassigned'}")
            for bath in sorted(data[unit]):
                bath_hdr = bath_divider(f"{bath.title()} Bathroom")
                combined = unit_hdr + bath_hdr
                elements += build_photo_section(data[unit][bath], combined)
                unit_hdr = []

    else:  # unit_phase
        for unit in sorted(data):
            unit_hdr = unit_divider(f"Unit {unit if unit != 'UNASSIGNED' else 'Unassigned'}")
            elements += build_photo_section(data[unit], unit_hdr)

    # ---- SPECIAL ROOMS ----
    special_data = context.get("special_rooms_structured", {})
    if special_data:
        for room_name in sorted(special_data):
            room_hdr = special_room_divider(room_name)
            elements += build_photo_section(special_data[room_name], room_hdr)

    doc.build(elements, onFirstPage=hf, onLaterPages=hf)
    print(f"[OK] PDF saved: {save_path}")
    return filename