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
import tempfile
from datetime import datetime
from io import BytesIO

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from urllib.parse import unquote

from PIL import Image as PILImage
from reportlab.platypus import Flowable, Image, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.utils import ImageReader
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
# PAGE GEOMETRY — SUBCONTRACTED 2×2 GRID
# ============================
GRID2_CELL_W     = CONTENT_W / 2
GRID2_CAPTION_W  = 0.72 * inch
GRID2_PHOTO_W    = GRID2_CELL_W - GRID2_CAPTION_W - 0.08 * inch
GRID2_IMG_H      = 2.45 * inch
GRID2_ROWS_PER_GROUP = 2   # 2 rows × 2 cols = 4 photos per KeepTogether block

# ============================
# PAGE GEOMETRY — LINEAR MODE
# ============================
LINEAR_PHOTO_W   = CONTENT_W * 0.58
LINEAR_CAPTION_W = CONTENT_W * 0.42
LINEAR_IMG_H     = 1.55 * inch
LINEAR_IMG_W     = LINEAR_PHOTO_W
LINEAR_TOP_MARGIN    = 0.85 * inch
LINEAR_BOTTOM_MARGIN = 0.5 * inch
LINEAR_HEADER_FOOTER_RESERVE = 0.55 * inch
LINEAR_ROW_OVERHEAD  = 0.18 * inch
MIN_LINEAR_IMG_H     = 1.0 * inch
MAX_LINEAR_IMG_H     = 2.75 * inch

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

style_grid2_cap_L  = ParagraphStyle("Grid2CapL",  fontSize=6,   leading=8.5, alignment=TA_RIGHT, textColor=colors.HexColor("#444444"), spaceAfter=1)
style_grid2_cap_L2 = ParagraphStyle("Grid2CapL2", fontSize=5.5, leading=8,   alignment=TA_RIGHT, textColor=colors.HexColor("#888888"), spaceAfter=1)
style_grid2_cap_R  = ParagraphStyle("Grid2CapR",  fontSize=6,   leading=8.5, alignment=TA_LEFT,  textColor=colors.HexColor("#444444"), spaceAfter=1)
style_grid2_cap_R2 = ParagraphStyle("Grid2CapR2", fontSize=5.5, leading=8,   alignment=TA_LEFT,  textColor=colors.HexColor("#888888"), spaceAfter=1)

BEFORE_COLOR   = colors.HexColor("#7f8c8d")
AFTER_COLOR    = colors.HexColor("#7f8c8d")
UNTAGGED_COLOR = colors.HexColor("#7f8c8d")
DIVIDER_COLOR  = colors.HexColor("#dde3ed")
HEADER_BG      = colors.HexColor("#1a2535")


class HyperlinkedImage(Image):
    """ReportLab Image with an optional URL annotation over the image bounds."""

    def __init__(self, filename, hyperlink=None, **kwargs):
        super().__init__(filename, **kwargs)
        self.hyperlink = hyperlink

    def drawOn(self, canvas, x, y, _sW=0):
        if self.hyperlink:
            x1 = self._hAlignAdjust(x, _sW)
            y1 = y
            x2 = x1 + self.drawWidth
            y2 = y1 + self.drawHeight
            canvas.linkURL(self.hyperlink, (x1, y1, x2, y2), thickness=0, relative=1)
        super().drawOn(canvas, x, y, _sW)


def photo_link_url(photo):
    """Return the CompanyCam original URL for PDF photo links, or None."""
    if not photo or not photo.get("has_image"):
        return None
    url = photo.get("original_url") or photo.get("url")
    if not url or "via.placeholder.com" in url:
        return None
    return url


def _geo_caption_paragraph(lat, lon, style):
    """Build a clickable geo caption, or None when coordinates are absent."""
    if lat is None or lon is None:
        return None
    try:
        lat_f, lon_f = float(lat), float(lon)
    except (TypeError, ValueError):
        return None
    geo_url = f"https://www.google.com/maps/search/?api=1&query={lat_f},{lon_f}"
    return Paragraph(
        f'<link href="{geo_url}"><u>📍 {lat_f:.4f}, {lon_f:.4f}</u></link>',
        style,
    )


def _normalize_photo_url(url):
    if not url or not isinstance(url, str):
        return ""
    return unquote(url.strip()).rstrip("/")


def lookup_transform(url, pdf_options):
    """Resolve session transform for a photo URL from pdf_options."""
    transforms = (pdf_options or {}).get("photo_transforms") or {}
    if not url or not transforms:
        return None
    norm = _normalize_photo_url(url)
    for key, val in transforms.items():
        if _normalize_photo_url(key) == norm:
            return val
    return transforms.get(url)


def _apply_pil_transform(pil_img, transform):
    if not transform:
        return pil_img
    rot = int(transform.get("rotation") or 0) % 360
    if rot:
        # CSS rotate() is clockwise; PIL rotates counter-clockwise.
        pil_img = pil_img.rotate(-rot, expand=True)
    crop = transform.get("crop")
    if crop and isinstance(crop, dict):
        w, h = pil_img.size
        x = max(0, min(w, int(float(crop.get("x", 0)) * w)))
        y = max(0, min(h, int(float(crop.get("y", 0)) * h)))
        cw = max(1, min(w - x, int(float(crop.get("w", 1)) * w)))
        ch = max(1, min(h - y, int(float(crop.get("h", 1)) * h)))
        pil_img = pil_img.crop((x, y, x + cw, y + ch))
    return pil_img


# ============================
# IMAGE FETCHER
# ============================
def fetch_image_to_temp(url, max_w, max_h, transform=None):
    """Stream-download a photo to a temp JPEG path; caller must unlink."""
    download_path = None
    try:
        r = session.get(url, timeout=8, stream=True)
        if r.status_code != 200:
            return None
        with tempfile.NamedTemporaryFile(delete=False, suffix=".img") as download_tmp:
            download_path = download_tmp.name
            for chunk in r.iter_content(chunk_size=65536):
                if chunk:
                    download_tmp.write(chunk)
        pil_img = PILImage.open(download_path)
        if pil_img.mode in ("RGBA", "P"):
            pil_img = pil_img.convert("RGB")
        pil_img = _apply_pil_transform(pil_img, transform)
        pil_img.thumbnail((800, 800))
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as jpeg_tmp:
            jpeg_path = jpeg_tmp.name
        pil_img.save(jpeg_path, format="JPEG", quality=70, optimize=True)
        return jpeg_path
    except Exception as e:
        print(f"[IMG FETCH ERROR] {e}")
        return None
    finally:
        if download_path:
            try:
                os.unlink(download_path)
            except OSError:
                pass


class LazyRemoteImage(Flowable):
    """Flowable that fetches a remote image at draw time (not wrap time)."""

    def __init__(self, url, draw_w, draw_h, link_url=None, transform=None, fetch_fn=None, halign="center"):
        super().__init__()
        self.url = url
        self.draw_w = draw_w
        self.draw_h = draw_h
        self.link_url = link_url
        self.transform = transform
        self.fetch_fn = fetch_fn or fetch_image_to_temp
        self.halign = halign

    def wrap(self, availWidth, availHeight):
        return self.draw_w, self.draw_h

    def drawOn(self, canvas, x, y, _sW=0):
        path = self.fetch_fn(self.url, self.draw_w, self.draw_h, self.transform)
        if not path:
            canvas.saveState()
            canvas.setFont("Helvetica-Oblique", 8)
            canvas.setFillColor(colors.HexColor("#bbbbbb"))
            canvas.drawCentredString(
                x + self.draw_w / 2, y + self.draw_h / 2, "[ unavailable ]",
            )
            canvas.restoreState()
            return
        try:
            iw, ih = ImageReader(path).getSize()
            if iw and ih:
                ratio = min(self.draw_w / iw, self.draw_h / ih)
                w, h = iw * ratio, ih * ratio
            else:
                w, h = self.draw_w, self.draw_h
            if self.halign == "left":
                img_x = x
            else:
                img_x = x + (self.draw_w - w) / 2
            img_y = y + (self.draw_h - h) / 2
            if self.link_url:
                canvas.linkURL(
                    self.link_url, (img_x, img_y, img_x + w, img_y + h), thickness=0, relative=1,
                )
            canvas.drawImage(path, img_x, img_y, width=w, height=h)
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass


def fetch_image(url, max_w=PHOTO_W, max_h=IMG_H, link_url=None, transform=None):
    try:
        r = session.get(url, timeout=8)
        if r.status_code == 200:
            pil_img = PILImage.open(BytesIO(r.content))
            if pil_img.mode in ("RGBA", "P"):
                pil_img = pil_img.convert("RGB")
            pil_img = _apply_pil_transform(pil_img, transform)
            TARGET_PX = 1200
            pil_img.thumbnail((TARGET_PX, TARGET_PX))
            buffer = BytesIO()
            pil_img.save(buffer, format="JPEG", quality=80, optimize=True)
            buffer.seek(0)
            if link_url:
                img = HyperlinkedImage(buffer, hyperlink=link_url)
            else:
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
def make_header_footer(project_name, page_offset=0):
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
        canvas.drawCentredString(w / 2, 14, f"Page {doc.page + page_offset}")
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
# METADATA POSITION + LINEAR GEOMETRY HELPERS
# ============================
def resolve_caption_side(metadata_position, column_index):
    """Map dashboard metadata_position + column (0=left, 1=right) to caption side."""
    pos = (metadata_position or "outside").lower()
    if pos == "left":
        return "left"
    if pos == "right":
        return "right"
    if pos == "inside":
        return "right" if column_index == 0 else "left"
    return "left" if column_index == 0 else "right"


def linear_row_geometry(pdf_options=None):
    """Return (img_h, img_w, photo_w, caption_w) scaled for photos-per-page."""
    pdf_options = pdf_options or {}
    per_page = int(pdf_options.get("linear_photos_per_page") or 4)
    if per_page not in (2, 3, 4):
        per_page = 4

    content_h = PAGE_H - LINEAR_TOP_MARGIN - LINEAR_BOTTOM_MARGIN - LINEAR_HEADER_FOOTER_RESERVE
    row_overhead = LINEAR_ROW_OVERHEAD
    per_row_h = (content_h - (per_page - 1) * row_overhead) / per_page
    img_h = max(MIN_LINEAR_IMG_H, min(MAX_LINEAR_IMG_H, per_row_h - 0.12 * inch))

    return img_h, LINEAR_IMG_W, LINEAR_PHOTO_W, LINEAR_CAPTION_W


def _grid_caption_styles(side, compact=False):
    if compact:
        return (style_grid2_cap_L, style_grid2_cap_L2) if side == "left" else (style_grid2_cap_R, style_grid2_cap_R2)
    return (style_cap_L, style_cap_L2) if side == "left" else (style_cap_R, style_cap_R2)


# ============================
# CAPTION BUILDER — grid mode
# ============================
def build_captions(photo, side, show_tags=True, compact=False):
    cs, cs2 = _grid_caption_styles(side, compact=compact)
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
        session_tags = photo.get("session_tags")
        if session_tags:
            tag_line = ", ".join(t for t in session_tags if str(t).strip())
            if tag_line:
                items.append(Paragraph(f"Tags: {tag_line}", cs2))
        else:
            tag_str = (photo.get("tag_string") or "").strip()
            for part in tag_str.split(" — "):
                if part.strip():
                    items.append(Paragraph(part.strip(), cs))
            extras = (photo.get("extra_tags") or "").strip()
            if extras:
                filtered = ", ".join(t for t in extras.split(", ") if t.strip() and not t.strip().isdigit())
                if filtered:
                    items.append(Paragraph(f"Tags: {filtered}", cs2))
    geo = _geo_caption_paragraph(photo.get("latitude"), photo.get("longitude"), cs2)
    if geo:
        items.append(geo)
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
        session_tags = photo.get("session_tags")
        if session_tags:
            tag_line = ", ".join(t for t in session_tags if str(t).strip())
            if tag_line:
                items.append(Paragraph(f"Tags: {tag_line}", style_lin_cap2))
        else:
            tag_str = (photo.get("tag_string") or "").strip()
            for part in tag_str.split(" — "):
                if part.strip():
                    items.append(Paragraph(part.strip(), style_lin_cap))
            extras = (photo.get("extra_tags") or "").strip()
            if extras:
                filtered = ", ".join(t for t in extras.split(", ") if t.strip() and not t.strip().isdigit())
                if filtered:
                    items.append(Paragraph(f"Tags: {filtered}", style_lin_cap2))
    geo = _geo_caption_paragraph(photo.get("latitude"), photo.get("longitude"), style_lin_cap2)
    if geo:
        items.append(geo)
    return items


# ============================
# PHOTO COLUMN BUILDER — grid mode
# ============================
def build_photo_col(photo, phase_color, phase_label, side, pdf_options=None,
                    cell_w=None, caption_w=None, photo_w=None, img_h=None, strip_w=None):
    pdf_options = pdf_options or {}
    show_tags = pdf_options.get("show_photo_tags", True)
    _cell_w   = cell_w or IMG_W
    _cap_w    = caption_w or CAPTION_W
    _photo_w  = photo_w or PHOTO_W
    _img_h    = img_h or IMG_H
    _strip_w  = strip_w or _cell_w
    strip    = phase_strip(phase_label, phase_color, _strip_w)
    captions = build_captions(photo, side, show_tags=show_tags)
    if photo and photo.get("url"):
        img_cell = [LazyRemoteImage(
            photo["url"], _photo_w, _img_h,
            link_url=photo_link_url(photo),
            transform=lookup_transform(photo["url"], pdf_options),
            fetch_fn=pdf_options.get("_fetch_fn"),
        )]
    else:
        img_cell = [Spacer(1, 0.15*inch), Paragraph("No photo available", style_no_photo)]
    if side == "left":
        inner_data, inner_widths = [captions, img_cell], [_cap_w, _photo_w]
    else:
        inner_data, inner_widths = [img_cell, captions], [_photo_w, _cap_w]
    inner = Table([inner_data], colWidths=inner_widths)
    inner.setStyle(TableStyle([
        ("VALIGN",       (0,0),(-1,-1), "MIDDLE"),
        ("LEFTPADDING",  (0,0),(-1,-1), 3),
        ("RIGHTPADDING", (0,0),(-1,-1), 3),
        ("TOPPADDING",   (0,0),(-1,-1), 5),
        ("BOTTOMPADDING",(0,0),(-1,-1), 5),
    ]))
    return [strip, inner]


def build_grid2_cell(photo, col_index, pdf_options=None):
    """Compact photo cell for subcontracted 2×2 grid."""
    pdf_options = pdf_options or {}
    show_tags = pdf_options.get("show_photo_tags", True)
    side = resolve_caption_side(pdf_options.get("metadata_position", "outside"), col_index)
    captions = build_captions(photo, side, show_tags=show_tags, compact=True)
    if photo and photo.get("url"):
        img_cell = [LazyRemoteImage(
            photo["url"], GRID2_PHOTO_W, GRID2_IMG_H,
            link_url=photo_link_url(photo),
            transform=lookup_transform(photo["url"], pdf_options),
            fetch_fn=pdf_options.get("_fetch_fn"),
        )]
    else:
        img_cell = [Spacer(1, 0.1*inch)]
    cap_w, photo_w = GRID2_CAPTION_W, GRID2_PHOTO_W
    if side == "left":
        inner_data, inner_widths = [captions, img_cell], [cap_w, photo_w]
    else:
        inner_data, inner_widths = [img_cell, captions], [photo_w, cap_w]
    inner = Table([inner_data], colWidths=inner_widths)
    inner.setStyle(TableStyle([
        ("VALIGN",       (0,0),(-1,-1), "MIDDLE"),
        ("LEFTPADDING",  (0,0),(-1,-1), 2),
        ("RIGHTPADDING", (0,0),(-1,-1), 2),
        ("TOPPADDING",   (0,0),(-1,-1), 3),
        ("BOTTOMPADDING",(0,0),(-1,-1), 3),
    ]))
    return inner


# ============================
# LINEAR-MODE ROW BUILDER
# ============================
def build_linear_row(photo, pdf_options=None):
    pdf_options = pdf_options or {}
    show_tags = pdf_options.get("show_photo_tags", True)
    img_h, img_w, photo_w, caption_w = linear_row_geometry(pdf_options)
    if photo and photo.get("url"):
        img_cell = [LazyRemoteImage(
            photo["url"], img_w, img_h,
            link_url=photo_link_url(photo),
            transform=lookup_transform(photo["url"], pdf_options),
            fetch_fn=pdf_options.get("_fetch_fn"),
            halign="left",
        )]
    else:
        img_cell = [Spacer(1, img_h * 0.5), Paragraph("No photo available", style_no_photo)]
    captions = build_captions_linear(photo, show_tags=show_tags)
    tbl = Table([[img_cell, captions]], colWidths=[photo_w, caption_w])
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