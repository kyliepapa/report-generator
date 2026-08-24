"""
PDF elements.

The smallest reusable pieces: page geometry constants, paragraph
styles, image fetching, header/footer drawing, caption builders, and
single-photo-column builders. reporting/pdf/sections.py composes these
into full rows/sections; reporting/pdf/cover_page.py and
report_builder.py use the styles/constants directly.

Relocated from pdf_generator.py with no logic changes, except:
  - BRAND_NAME / HEADER_TITLE pulled out as named constants (were
    string literals buried inside make_header_footer's closure) so
    rebranding the PDF footer is a one-line edit instead of a
    find-in-2400-lines edit.
"""

import os
from datetime import datetime
from io import BytesIO

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from PIL import Image as PILImage
from reportlab.platypus import Image, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

session = requests.Session()
retries = Retry(total=3, backoff_factor=0.5)
session.mount('http://', HTTPAdapter(max_retries=retries))
session.mount('https://', HTTPAdapter(max_retries=retries))

# ─────────────────────────────────────────
# BRANDING
# (was inline string literals inside make_header_footer)
# ─────────────────────────────────────────
HEADER_TITLE = "Installation Photos"
BRAND_NAME = "Bottom Line Utility Solutions, Inc."

# ============================
# PAGE GEOMETRY — GRID MODE
# ============================
PAGE_W, PAGE_H = letter
MARGIN    = 0.6 * inch
CONTENT_W = PAGE_W - 2 * MARGIN

GUTTER  = 0.12 * inch
IMG_W   = (CONTENT_W - GUTTER) / 2

CAPTION_W = 1.05 * inch
PHOTO_W   = IMG_W - CAPTION_W

IMG_H = 3.05 * inch

# ============================
# PAGE GEOMETRY — LINEAR MODE
# ============================
LINEAR_PHOTO_W   = CONTENT_W * 0.58
LINEAR_CAPTION_W = CONTENT_W * 0.42
LINEAR_IMG_H     = 1.55 * inch
LINEAR_IMG_W     = LINEAR_PHOTO_W

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

style_cap_L    = ParagraphStyle("CapL",  fontSize=6.5, leading=9,   alignment=TA_RIGHT, textColor=colors.HexColor("#444444"), spaceAfter=2)
style_cap_L2   = ParagraphStyle("CapL2", fontSize=6,   leading=8.5, alignment=TA_RIGHT, textColor=colors.HexColor("#888888"), spaceAfter=1)
style_cap_R    = ParagraphStyle("CapR",  fontSize=6.5, leading=9,   alignment=TA_LEFT,  textColor=colors.HexColor("#444444"), spaceAfter=2)
style_cap_R2   = ParagraphStyle("CapR2", fontSize=6,   leading=8.5, alignment=TA_LEFT,  textColor=colors.HexColor("#888888"), spaceAfter=1)

style_lin_cap  = ParagraphStyle("LinCap",  fontSize=7.5, leading=11,  alignment=TA_LEFT, textColor=colors.HexColor("#333333"), spaceAfter=3)
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
        canvas.setFillColor(HEADER_BG)
        canvas.rect(0, h - 26, w, 26, fill=1, stroke=0)
        canvas.setFont("Helvetica-Bold", 8.5)
        canvas.setFillColor(colors.white)
        canvas.drawString(MARGIN, h - 17, HEADER_TITLE)
        canvas.drawRightString(w - MARGIN, h - 17, project_name)
        canvas.setStrokeColor(DIVIDER_COLOR)
        canvas.setLineWidth(0.5)
        canvas.line(MARGIN, 28, w - MARGIN, 28)
        canvas.setFillColor(colors.HexColor("#999999"))
        canvas.setFont("Helvetica", 7.5)
        canvas.drawString(MARGIN, 14, BRAND_NAME)
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
# CAPTION BUILDER — grid mode
# ============================
def build_captions(photo, side, show_tags=True):
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
    if show_tags:
        tag_str = (photo.get("tag_string") or "").strip()
        for part in tag_str.split(" — "):
            if part.strip():
                items.append(Paragraph(part.strip(), cs))
        extras = (photo.get("extra_tags") or "").strip()
        if extras:
            filtered = ", ".join(t for t in extras.split(", ") if t.strip() and not t.strip().isdigit())
            if filtered:
                items.append(Paragraph(f"Tags: {filtered}", cs2))
    lat, lon = photo.get("latitude"), photo.get("longitude")
    if lat and lon:
        geo_url = f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"
        items.append(Paragraph(f'<link href="{geo_url}"><u>📍 {lat:.4f}, {lon:.4f}</u></link>', cs2))
    return items


# ============================
# CAPTION BUILDER — linear mode
# ============================
def build_captions_linear(photo, show_tags=True):
    items = []
    if not photo:
        return [Paragraph("—", style_lin_cap)]
    ts = "Unknown"
    try:
        ts = datetime.fromtimestamp(int(photo.get("captured_at"))).strftime("%Y-%m-%d %H:%M")
    except:
        pass
    items.append(Paragraph(f"📷  {ts}", style_lin_cap))
    if show_tags:
        tag_str = (photo.get("tag_string") or "").strip()
        for part in tag_str.split(" — "):
            if part.strip():
                items.append(Paragraph(part.strip(), style_lin_cap))
        extras = (photo.get("extra_tags") or "").strip()
        if extras:
            filtered = ", ".join(t for t in extras.split(", ") if t.strip() and not t.strip().isdigit())
            if filtered:
                items.append(Paragraph(f"Tags: {filtered}", style_lin_cap2))
    lat, lon = photo.get("latitude"), photo.get("longitude")
    if lat and lon:
        geo_url = f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"
        items.append(Paragraph(f'<link href="{geo_url}"><u>📍 {lat:.4f}, {lon:.4f}</u></link>', style_lin_cap2))
    return items


# ============================
# PHOTO COLUMN BUILDER — grid mode
# ============================
def build_photo_col(photo, phase_color, phase_label, side, pdf_options=None):
    pdf_options = pdf_options or {}
    show_tags = pdf_options.get("show_photo_tags", True)
    strip    = phase_strip(phase_label, phase_color, IMG_W)
    captions = build_captions(photo, side, show_tags=show_tags)
    if photo and photo.get("url"):
        img = fetch_image(photo["url"])
        img_cell = [img] if img else [Paragraph("[ unavailable ]", style_no_photo)]
    else:
        img_cell = [Spacer(1, 0.15*inch), Paragraph("No photo available", style_no_photo)]
    if side == "left":
        inner_data, inner_widths = [captions, img_cell], [CAPTION_W, PHOTO_W]
    else:
        inner_data, inner_widths = [img_cell, captions], [PHOTO_W, CAPTION_W]
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
# LINEAR-MODE ROW BUILDER
# ============================
def build_linear_row(photo, pdf_options=None):
    pdf_options = pdf_options or {}
    show_tags = pdf_options.get("show_photo_tags", True)
    if photo and photo.get("url"):
        img = fetch_image(photo["url"], max_w=LINEAR_IMG_W, max_h=LINEAR_IMG_H)
        img_cell = [img] if img else [Paragraph("[ unavailable ]", style_no_photo)]
    else:
        img_cell = [Spacer(1, LINEAR_IMG_H * 0.5), Paragraph("No photo available", style_no_photo)]
    captions = build_captions_linear(photo, show_tags=show_tags)
    tbl = Table([[img_cell, captions]], colWidths=[LINEAR_PHOTO_W, LINEAR_CAPTION_W])
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