"""
Cover page builder.

Relocated from pdf_generator.py with one change: base_dir (used to
locate static/logo.png) now comes from core.paths.PROJECT_ROOT instead
of a locally-computed os.path.dirname(__file__), since this file lives
one directory deeper than the original pdf_generator.py did.

cover_fields in pdf_options is a list of dicts:
  { "key": str, "value": str, "visible": bool }

Recognised keys (in render order):
  subtitle         "INSTALLATION PHOTOS"
  project_name     large title
  address          project address
  date             "Date: <generated date>"
  total_buildings  "Buildings: N"
  total_units      "Units: N"
  total_bathrooms  "Installations: N"
  total_photos     "Total Photos: N"
  layout           "Grid Layout" / "Linear Layout"

visible=False → field is skipped entirely.
value override replaces the default text (leave empty to keep default).
"""

import os

from reportlab.platypus import Paragraph, Spacer, Image, PageBreak, HRFlowable
from reportlab.lib import colors
from reportlab.lib.units import inch

from reporting.pdf.elements import style_title, style_subtitle, style_meta
import core.paths as paths


def build_cover_page(context, pdf_options, is_linear, base_dir, elements):
    project_name = context.get("project_name", context.get("project_id", "Report"))

    # Build fast lookup
    field_map = {f["key"]: f for f in pdf_options.get("cover_fields", [])}

    def _render(key, default_text, style, extra_spacer=None):
        """Appends a paragraph if the field is visible. Returns True if rendered."""
        entry = field_map.get(key)
        if entry is not None:
            if not entry.get("visible", True):
                return False
            text = entry.get("value", "").strip() or default_text
        else:
            text = default_text
        if not text:
            return False
        elements.append(Paragraph(text, style))
        if extra_spacer:
            elements.append(Spacer(1, extra_spacer))
        return True

    # ── Logo ──────────────────────────────────────────────────────────────────
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

    # ── Subtitle ──────────────────────────────────────────────────────────────
    _render("subtitle", "INSTALLATION PHOTOS", style_subtitle, extra_spacer=0.12*inch)

    # ── Project name ──────────────────────────────────────────────────────────
    _render("project_name",
            context.get("project_name_upper", project_name.upper()),
            style_title)

    elements.append(Spacer(1, 0.28*inch))
    elements.append(HRFlowable(width="55%", thickness=1.5,
                                color=colors.HexColor("#2e86de"), hAlign="CENTER"))
    elements.append(Spacer(1, 0.22*inch))

    # ── Address ───────────────────────────────────────────────────────────────
    _render("address", context.get("address", ""), style_meta)

    # ── Date ──────────────────────────────────────────────────────────────────
    _render("date", f"Date: {context.get('date_generated', '')}", style_meta)

    elements.append(Spacer(1, 0.12*inch))

    # ── Stats ─────────────────────────────────────────────────────────────────
    for key, label in [("total_buildings", "Buildings"),
                       ("total_units",     "Units"),
                       ("total_bathrooms", "Installations"),
                       ("total_photos",    "Total Photos")]:
        ctx_val = context.get(key)
        if not ctx_val:
            continue
        entry = field_map.get(key)
        if entry is not None and not entry.get("visible", True):
            continue
        if entry is not None:
            raw = entry.get("value", "").strip()
            if raw:
                text = f"{label}: {raw}" if raw.isdigit() else raw
            else:
                text = f"{label}: {ctx_val}"
        else:
            text = f"{label}: {ctx_val}"
        elements.append(Paragraph(text, style_meta))

    # ── Layout badge ──────────────────────────────────────────────────────────
    layout_default = "Linear Layout" if is_linear else "Grid Layout"
    elements.append(Spacer(1, 0.08*inch))
    _render("layout", layout_default, style_meta)

    elements.append(PageBreak())