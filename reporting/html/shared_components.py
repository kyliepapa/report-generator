"""
Shared HTML components.

Relocated from newreport.py's "SHARED HTML COMPONENTS" section
(originally ~1,300 lines, mostly CSS/JS string constants -- those now
live as real files under styles/, scripts/, partials/, loaded via
assets.py). The functions below are unchanged logic-wise; only their
CSS/JS/HTML sourcing changed, from Python string literals to
assets.get_*() calls.

make_shared_css() kept its original name/signature (it's called from
_make_head() the same way it always was) even though it's now a thin
wrapper over assets.get_shared_css() -- a rename wasn't worth touching
every call site before the generator functions get relocated next.
"""

import html as html_module
import json

from core.timezone import format_timestamp
from reporting.html import assets


def make_photo_card_html(photo_data, idx=None, zone_id=None):
    """
    Renders one photo card.
    zone_id is unused here but kept for signature compatibility.
    The data-zone attribute is placed on the .photo-grid wrapper, not individual cards.
    idx: optional 1-based position label for subcontracted measures.
    """
    url = photo_data["url"]
    captured_at = photo_data.get("captured_at")
    latitude = photo_data.get("latitude")
    longitude = photo_data.get("longitude")
    has_image = photo_data.get("has_image", True)
    all_tags = photo_data.get("all_tags", [])

    timestamp_str = "Unknown"
    if captured_at:
        try:
            timestamp_str = format_timestamp(int(captured_at))
        except:
            timestamp_str = "Unknown"

    img_style = "" if has_image else "filter: grayscale(100%); opacity: 0.6;"

    tags_json = json.dumps(all_tags)
    original_url = photo_data.get("original_url") or url
    has_geo = latitude is not None and longitude is not None
    try:
        geo_label = f"{float(latitude):.4f}, {float(longitude):.4f}" if has_geo else ""
        geo_url = (
            f"https://www.google.com/maps/search/?api=1&query={float(latitude)},{float(longitude)}"
            if has_geo else ""
        )
    except (TypeError, ValueError):
        has_geo = False
        geo_label = ""
        geo_url = ""

    esc_url = html_module.escape(url, quote=True)
    esc_orig = html_module.escape(original_url, quote=True)
    esc_ts = html_module.escape(timestamp_str, quote=True)
    esc_geo_label = html_module.escape(geo_label, quote=True)
    esc_geo_url = html_module.escape(geo_url, quote=True)
    esc_tags = html_module.escape(tags_json, quote=True)

    html  = (
        f'<div class="photo-card" draggable="true" data-photo-url="{esc_url}"'
        f' data-original-url="{esc_orig}" data-timestamp="{esc_ts}"'
        f' data-geo-label="{esc_geo_label}" data-geo-url="{esc_geo_url}"'
        f' data-tags="{esc_tags}" data-tags-default="{esc_tags}">'
    )
    if idx is not None:
        html += f'<span class="photo-index">{idx}</span>'
    html += (
        f'<div class="photo-img-wrap">'
        f'<img src="{url}" loading="lazy" style="{img_style}"'
        f' onclick="openLightboxFromCard(event, this.closest(\'.photo-card\'))">'
        f'</div>'
    )
    html += '<div class="photo-metadata">'
    html += f'<div class="timestamp">📷 {timestamp_str}</div>'
    if not has_image:
        html += '<div class="geotag" style="color:#e74c3c;">⚠️ No image available</div>'
    if has_geo:
        html += f'<div class="geotag">📍 <a class="geotag-link" href="{geo_url}" target="_blank">{geo_label}</a></div>'
    else:
        html += '<div class="geotag">📍 No location data</div>'
    html += '</div></div>'
    return html


def _photo_grid(photos, zone_id):
    """Renders a .photo-grid div with a data-zone attribute for drag-and-drop tracking."""
    cards = ''.join(make_photo_card_html(p) for p in photos)
    return f'<div class="photo-grid" data-zone="{zone_id}">{cards}</div>'


def make_shared_css():
    """Was an inline triple-quoted string; now reads styles/shared.css."""
    return assets.get_shared_css()


# ── Zone-ID generator ─────────────────────────────────────────────────────────
def _zone_id(*parts):
    """
    Creates a stable zone identifier from structural keys.

    IMPORTANT: callers on the Lighting path (apply_lighting_photo_edits in
    core/photo_edits.py) parse this string back apart by FIXED POSITION
    (parts[0], parts[1], idx += 2, etc.), not by token content.

    The delimiter below (\x1f, ASCII "unit separator") is deliberately NOT
    "_" or any character that .replace(" ", "_") can produce. The previous
    version joined with "__" while also replacing spaces with "_" -- so a
    real-world name containing a double space (or a literal double
    underscore) silently produced an extra "__" boundary, split()-ing into
    an extra part and shifting every later positional index in the parser.
    \x1f cannot appear in a name typed through any normal UI, so join/split
    round-trips unambiguously regardless of what the name contains.

    Only None is dropped from parts; an empty string in a structural slot
    still occupies its position (dropping it would cause the same kind of
    index shift this fix is meant to eliminate).
    """
    return "\x1f".join(
        str(p).replace(" ", "_") for p in parts if p is not None
    )


# ── Head snippet (combines all CSS) ──────────────────────────────────────────
def _make_head(title, extra_css=""):
    style = (
        f"{make_shared_css()}"
        f"{assets.get_lightbox_css()}"
        f"{assets.get_drag_drop_css()}"
        f"{assets.get_pdf_dashboard_css()}"
        f"{extra_css}"
    )
    return f"""<!DOCTYPE html><html><head>
    <title>{title} — Report</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>{style}</style>
    </head><body>
    {assets.get_dnd_toolbar_html()}
    {assets.get_lightbox_html()}"""


def _make_tail():
    return (
        f"{assets.get_analytics_context_js()}"
        f"{assets.get_analytics_edits_js()}"
        f"{assets.get_photo_session_js()}"
        f"{assets.get_lightbox_js()}"
        f"{assets.get_pdf_progress_js()}"
        f"{assets.get_sortable_js()}"
        f"{assets.get_drag_drop_js()}"
        f"</body></html>"
    )


# ── Phase-section builder (shared by all 4 generators) ───────────────────────
def _phase_section(photos, phase, zone_id):
    badge = "before" if phase == "BEFORE" else ("after" if phase == "AFTER" else "untagged")
    label = phase if phase != "UNTAGGED" else "Identification"
    html  = f'<div class="phase-section">'
    html += f'<div class="phase-header"><h3 class="phase-title"><span class="phase-badge {badge}">{label}</span></h3>'
    html += f'<span class="phase-count">{len(photos)} photos</span></div>'
    if photos:
        html += _photo_grid(photos, zone_id)
    else:
        html += f'<div class="photo-grid" data-zone="{zone_id}"></div>'
        html += '<div class="no-photos">No photos</div>'
    html += '</div>'
    return html