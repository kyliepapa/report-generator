"""
Static asset loader for the HTML report.

The original newreport.py had ~1,300 lines of CSS/JS/HTML sitting in
Python triple-quoted string constants (LIGHTBOX_CSS, DRAG_DROP_JS,
PDF_PROGRESS_JS, etc). Those are now real files under styles/, scripts/,
and partials/ -- readable by a CSS/JS linter, diffable sensibly, and
editable without touching Python at all.

This module's job is narrow: read those files and hand back strings in
exactly the shape the old inline constants were, so shared_components.py
can assemble the page exactly like the original _make_head()/_make_tail()
did. The three .js files had their <script> wrapper stripped when they
were extracted (so they read as real JS, not JS-wrapped-in-HTML-wrapped-
in-a-Python-string) -- get_*_js() below re-adds it here, once, in one
place, rather than in every generator function.

Content is cached after first read (report generation runs many times
per job across 4 possible generator functions -- no reason to hit disk
repeatedly for content that never changes mid-process).

tabs.css / tabs.js added for the multi-measure tabbed report layout
(generate_html_report in generators.py) -- same read/cache/wrap
pattern as everything else here.
"""

import os
from functools import lru_cache

_HTML_DIR = os.path.dirname(os.path.abspath(__file__))
_STYLES_DIR = os.path.join(_HTML_DIR, "styles")
_SCRIPTS_DIR = os.path.join(_HTML_DIR, "scripts")
_PARTIALS_DIR = os.path.join(_HTML_DIR, "partials")


@lru_cache(maxsize=None)
def _read(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


# ─────────────────────────────────────────
# CSS (each wrapped for direct <style> interpolation)
# ─────────────────────────────────────────
def get_shared_css() -> str:
    return _read(os.path.join(_STYLES_DIR, "shared.css"))


def get_lightbox_css() -> str:
    return _read(os.path.join(_STYLES_DIR, "lightbox.css"))


def get_pdf_dashboard_css() -> str:
    return _read(os.path.join(_STYLES_DIR, "pdf_dashboard.css"))


def get_drag_drop_css() -> str:
    return _read(os.path.join(_STYLES_DIR, "drag_drop.css"))


def get_tabs_css() -> str:
    return _read(os.path.join(_STYLES_DIR, "tabs.css"))


# ─────────────────────────────────────────
# JS (re-wrapped in <script> tags on the way out, matching the
# original LIGHTBOX_JS / DRAG_DROP_JS / PDF_PROGRESS_JS constants)
# ─────────────────────────────────────────
def get_photo_session_js() -> str:
    return f"<script>\n{_read(os.path.join(_SCRIPTS_DIR, 'photo_session.js'))}</script>\n"


def get_lightbox_js() -> str:
    return f"<script>\n{_read(os.path.join(_SCRIPTS_DIR, 'lightbox.js'))}</script>\n"


def get_sortable_js() -> str:
    return (
        '<script src="https://cdn.jsdelivr.net/npm/sortablejs@1.15.6/Sortable.min.js"></script>\n'
    )


def get_drag_drop_js() -> str:
    return f"<script>\n{_read(os.path.join(_SCRIPTS_DIR, 'drag_drop.js'))}</script>\n"


def get_pdf_progress_js() -> str:
    return f"<script>\n{_read(os.path.join(_SCRIPTS_DIR, 'pdf_progress.js'))}</script>\n"


def get_analytics_edits_js() -> str:
    return f"<script>\n{_read(os.path.join(_SCRIPTS_DIR, 'analytics_edits.js'))}</script>\n"


def get_analytics_context_js() -> str:
    return (
        "<script>\n"
        "(function(){var p=new URLSearchParams(location.search);"
        "window.AutoRecReportContext={"
        "run_id:p.get('run_id'),"
        "user_id:p.get('user_id'),"
        "display_name:p.get('display_name'),"
        "session_id:p.get('session_id')};})();\n"
        "</script>\n"
    )


def get_tabs_js() -> str:
    return f"<script>\n{_read(os.path.join(_SCRIPTS_DIR, 'tabs.js'))}</script>\n"


# ─────────────────────────────────────────
# HTML partials
# ─────────────────────────────────────────
def get_lightbox_html() -> str:
    return _read(os.path.join(_PARTIALS_DIR, "lightbox.html"))


def get_pdf_button_html() -> str:
    return _read(os.path.join(_PARTIALS_DIR, "pdf_button.html"))


def get_dnd_toolbar_html() -> str:
    return _read(os.path.join(_PARTIALS_DIR, "dnd_toolbar.html"))