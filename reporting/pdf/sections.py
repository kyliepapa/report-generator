"""
PDF sections.

Composes elements.py's building blocks (photo columns, phase strips)
into rows and full sections. Relocated from pdf_generator.py with no
logic changes -- including the dead branch flagged below, kept exactly
as-is pending your decision.
"""

from reportlab.platypus import Table, TableStyle, Paragraph, Spacer, HRFlowable, KeepTogether
from reportlab.lib import colors
from reportlab.lib.units import inch

from reporting.pdf.elements import (
    build_photo_col, build_linear_row, style_no_photo,
    DIVIDER_COLOR, IMG_W, IMG_H, BEFORE_COLOR, AFTER_COLOR, UNTAGGED_COLOR,
)


# ============================
# COMPARISON ROW — grid mode
# ============================
def build_comparison_row(before_photo, after_photo, pdf_options=None):
    left  = build_photo_col(before_photo, BEFORE_COLOR, "BEFORE", "left", pdf_options)
    right = build_photo_col(after_photo,  AFTER_COLOR,  "AFTER",  "right", pdf_options)
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
# SINGLE-PHOTO ROW — grid mode
# ============================
def build_single_row(photo, side="left", phase_label=None, pdf_options=None):
    # Renders one photo occupying one half of the two-column grid row,
    # leaving the other half blank.

    # phase_label – if supplied, overrides the default badge text so that an
    #             AFTER photo shifted into the left column still reads "AFTER".
    default_label = "BEFORE" if side == "left" else "AFTER"
    label = phase_label if phase_label else default_label
    color = BEFORE_COLOR if label == "BEFORE" else AFTER_COLOR
    col   = build_photo_col(photo, color, label, side, pdf_options)
    blank = [Spacer(1, IMG_H)]
    data  = [col, blank] if side == "left" else [blank, col]
    tbl   = Table([data], colWidths=[IMG_W, IMG_W])
    tbl.setStyle(TableStyle([
        ("VALIGN",       (0,0),(-1,-1), "TOP"),
        ("LEFTPADDING",  (0,0),(-1,-1), 0),
        ("RIGHTPADDING", (0,0),(-1,-1), 0),
        ("TOPPADDING",   (0,0),(-1,-1), 0),
        ("BOTTOMPADDING",(0,0),(-1,-1), 0),
    ]))
    return tbl


# ============================
# UNTAGGED ROW — grid mode, paired side by side
# No section divider — photos are told apart by their "ID" phase badge only.
# ============================
def build_untagged_pair(photo_left, photo_right=None, pdf_options=None):
    left  = build_photo_col(photo_left,  UNTAGGED_COLOR, "ID", "left", pdf_options)
    right = build_photo_col(photo_right, UNTAGGED_COLOR, "ID", "right", pdf_options) \
            if photo_right else [Spacer(1, 0.1*inch)]
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


def collect_id_photos(phases_dict, hidden_urls):
    # Returns all photos that should be rendered with the IDENTIFICATION badge:
    # the UNTAGGED bucket of any phases_dict (OTHER or real bathroom).
    # Respects the hidden_urls exclusion set.
    return [
        p for p in phases_dict.get("UNTAGGED", [])
        if p.get("url") not in hidden_urls
    ]


def build_id_section(id_photos, header_elements=None, pdf_options=None):
    """
    Renders identification photos two-per-row using the same build_untagged_pair
    layout.  Attaches header_elements to the first group only.
    header_elements is typically [] (no extra heading; ID photos just continue
    after the last real bathroom of the unit).
    """
    if not id_photos:
        return []
    pdf_options = pdf_options or {}
    elements    = []
    header_elements = list(header_elements or [])

    rows = []
    for i in range(0, len(id_photos), 2):
        rows.append(build_untagged_pair(
            id_photos[i],
            id_photos[i + 1] if i + 1 < len(id_photos) else None,
            pdf_options,
        ))

    for gi, start in enumerate(range(0, len(rows), ROWS_PER_GROUP)):
        group  = rows[start : start + ROWS_PER_GROUP]
        spaced = []
        for row in group:
            spaced.append(row)
            spaced.append(Spacer(1, 5))
        block = (header_elements + spaced) if gi == 0 else spaced
        elements.append(KeepTogether(block))

    return elements


def build_id_section_linear(id_photos, header_elements=None, pdf_options=None):
    """
    Linear-mode equivalent of build_id_section.
    """
    if not id_photos:
        return []
    pdf_options = pdf_options or {}
    elements    = []
    header_elements = list(header_elements or [])

    rows = [build_linear_row(p, pdf_options) for p in id_photos]

    for gi, start in enumerate(range(0, len(rows), LINEAR_ROWS_PER_GROUP)):
        group  = rows[start : start + LINEAR_ROWS_PER_GROUP]
        spaced = []
        for row in group:
            spaced.append(row)
            spaced.append(HRFlowable(width="100%", thickness=0.3,
                                    color=colors.HexColor("#eeeeee"), spaceAfter=2))
        block = (header_elements + spaced) if gi == 0 else spaced
        elements.append(KeepTogether(block))

    return elements


# ============================
# SECTION BUILDER — grid mode
# ============================
ROWS_PER_GROUP = 2

def build_photo_section(phases_dict, header_elements, pdf_options=None):
    """
    Untagged photos flow directly after Before/After rows with NO divider header.
    They are distinguished from each other only by the phase badge on each photo.
    """
    pdf_options = pdf_options or {}
    hide_empty  = pdf_options.get("hide_empty_fields", False)
    hidden_urls = pdf_options.get("hidden_photos", set())
    elements    = []

    before_list   = [p for p in phases_dict.get("BEFORE",   []) if p.get("url") not in hidden_urls]
    after_list    = [p for p in phases_dict.get("AFTER",    []) if p.get("url") not in hidden_urls]
    untagged_list = [p for p in phases_dict.get("UNTAGGED", []) if p.get("url") not in hidden_urls]

    if hide_empty:
        spare_untagged = list(untagged_list)
        rows = max(len(before_list), len(after_list))
        if rows == 0:
            # Even with hide_empty, still render any UNTAGGED/ID photos
            if not untagged_list:
                return elements
            # Fall through — comp_rows will be empty, remaining_untagged will render
            comp_rows = []
        for i in range(rows):
            b = before_list[i] if i < len(before_list) else None
            a = after_list[i]  if i < len(after_list)  else None
            if b is None and a is not None:
                # Only an AFTER photo — shift it left but keep the AFTER badge
                comp_rows.append(build_single_row(a, side="left", phase_label="AFTER", pdf_options=pdf_options))
            elif b is not None and a is None:
                filler = spare_untagged.pop(0) if spare_untagged else None
                comp_rows.append(build_comparison_row(b, filler, pdf_options) if filler
                                else build_single_row(b, side="left", phase_label="BEFORE", pdf_options=pdf_options))
            else:
                comp_rows.append(build_comparison_row(b, a, pdf_options))
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
            comp_rows.append(build_comparison_row(b, a, pdf_options))
        remaining_untagged = untagged_list

    # Emit comparison rows — headers go with the first group
    for gi, start in enumerate(range(0, len(comp_rows), ROWS_PER_GROUP)):
        group  = comp_rows[start : start + ROWS_PER_GROUP]
        spaced = []
        for row in group:
            spaced.append(row)
            spaced.append(Spacer(1, 5))
        block = (list(header_elements) + spaced) if gi == 0 else spaced
        elements.append(KeepTogether(block))

    # Untagged rows — NO divider header inserted before them.
    # If there were no comp_rows, the section headers haven't been emitted yet;
    # attach them to the first untagged group so they're never orphaned.
    if remaining_untagged:
        untag_rows = []
        for i in range(0, len(remaining_untagged), 2):
            untag_rows.append(build_untagged_pair(
                remaining_untagged[i],
                remaining_untagged[i+1] if i+1 < len(remaining_untagged) else None,
                pdf_options,
            ))
        headers_pending = list(header_elements) if not comp_rows else []
        for gi, start in enumerate(range(0, len(untag_rows), ROWS_PER_GROUP)):
            group  = untag_rows[start : start + ROWS_PER_GROUP]
            spaced = []
            for row in group:
                spaced.append(row)
                spaced.append(Spacer(1, 5))
            block = (headers_pending + spaced) if gi == 0 else spaced
            elements.append(KeepTogether(block))

    return elements


# ============================
# SECTION BUILDER — linear mode
# ============================
LINEAR_ROWS_PER_GROUP = 4

def build_photo_section_linear(phases_dict, header_elements, pdf_options=None):
    pdf_options = pdf_options or {}
    hidden_urls = pdf_options.get("hidden_photos", set())
    hide_empty  = pdf_options.get("hide_empty_fields", False)
    elements    = []
    all_photos  = []
    for phase in ("BEFORE", "AFTER", "UNTAGGED"):
        for p in phases_dict.get(phase, []):
            if p.get("url") not in hidden_urls:
                all_photos.append(p)

    if not all_photos:
        # ────────────────────────────────────────────────────────────────
        # TODO / FLAG FOR REVIEW — relocated EXACTLY as found, not fixed:
        # The original code here had the comment
        #   "Just me rigging the system real quick, don't mind me:"
        # followed by an unconditional `hide_empty = True`. That makes the
        # "No photos in this section" placeholder block below completely
        # unreachable -- it always returns early regardless of what the
        # user's hide_empty_fields toggle is actually set to. This may have
        # been an intentional permanent decision (never show the
        # placeholder in linear mode) or a leftover debugging hack that
        # was never cleaned up. Preserved as-is because it changes
        # user-visible PDF output either way -- needs a decision, not a
        # silent fix.
        # ────────────────────────────────────────────────────────────────
        hide_empty = True
        if hide_empty:
            return elements
        # hide_empty is off: render the "No photos" placeholder so the
        # section heading still appears and the user knows the slot exists.
        block = list(header_elements) + [
            Paragraph("No photos in this section.", style_no_photo),
            Spacer(1, 6),
        ]
        elements.append(KeepTogether(block))
        return elements

    rows = [build_linear_row(p, pdf_options) for p in all_photos]
    for gi, start in enumerate(range(0, len(rows), LINEAR_ROWS_PER_GROUP)):
        group  = rows[start : start + LINEAR_ROWS_PER_GROUP]
        spaced = []
        for row in group:
            spaced.append(row)
            spaced.append(HRFlowable(width="100%", thickness=0.3,
                                    color=colors.HexColor("#eeeeee"), spaceAfter=2))
        block = (list(header_elements) + spaced) if gi == 0 else spaced
        elements.append(KeepTogether(block))
    return elements


# ============================
# FLAT LINEAR SECTION — Lighting (linear-only dataset)
# ============================
# Same row-building/grouping approach as build_photo_section_linear,
# but takes an already-flat photo list rather than a phases_dict --
# Lighting's fixtures don't map onto the fixed BEFORE/AFTER/UNTAGGED
# phase keys the way plumbing's do (phases are caller-configured tags),
# and per the Lighting PDF adjustments individual fixtures don't get
# their own headings, so photos from a Type's fixtures are flattened
# into one continuous stream under that Type's heading.
#
# Deliberately does NOT carry over build_photo_section_linear's forced
# `hide_empty = True` hack (see the TODO flagged there) -- this
# function respects pdf_options["hide_empty_fields"] as written.
def build_flat_linear_section(photos, header_elements, pdf_options=None):
    pdf_options = pdf_options or {}
    hidden_urls = pdf_options.get("hidden_photos", set())
    hide_empty  = pdf_options.get("hide_empty_fields", False)
    header_elements = list(header_elements or [])

    visible = [p for p in photos if p.get("url") not in hidden_urls]

    if not visible:
        if hide_empty or not header_elements:
            return []
        block = header_elements + [
            Paragraph("No photos in this section.", style_no_photo),
            Spacer(1, 6),
        ]
        return [KeepTogether(block)]

    elements = []
    rows = [build_linear_row(p, pdf_options) for p in visible]
    for gi, start in enumerate(range(0, len(rows), LINEAR_ROWS_PER_GROUP)):
        group  = rows[start : start + LINEAR_ROWS_PER_GROUP]
        spaced = []
        for row in group:
            spaced.append(row)
            spaced.append(HRFlowable(width="100%", thickness=0.3,
                                    color=colors.HexColor("#eeeeee"), spaceAfter=2))
        block = (header_elements + spaced) if gi == 0 else spaced
        elements.append(KeepTogether(block))
    return elements