"""
Filesystem paths.

The original app.py and newreport.py each computed their own BASE_DIR
from __file__ -- which happened to agree, since both files lived at
the project root. That coincidence breaks once report generation moves
into reporting/html/generators.py (two directories deeper), so this
module is the one place PROJECT_ROOT/STATIC_DIR/OUTPUT_FILE get
computed, and everything else imports from here.

web/routes/ will be updated to use this too when it's relocated in a
later step; until then, app.py's own independent BASE_DIR/STATIC_DIR
still happens to resolve to the same real path (it hasn't moved yet).
"""

import os

# core/paths.py -> core/ -> project root
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(PROJECT_ROOT, "static")
REPORTS_DIR = os.path.join(STATIC_DIR, "reports")
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
OUTPUT_FILE = os.path.join(STATIC_DIR, "report.html")

# Was CHANGELOG_FILE/REPNREQ_FILE/USAGE_LOGS_FILE, defined directly in
# app.py alongside its route handlers. Centralized here with the rest
# of the path config.
CHANGELOG_FILE  = os.path.join(DATA_DIR, "changelog.txt")
REPNREQ_FILE    = os.path.join(DATA_DIR, "repnreq.txt")
USAGE_LOGS_FILE = os.path.join(DATA_DIR, "usage_logs.txt")

os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(REPORTS_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)


# ─────────────────────────────────────────
# Small file I/O helpers
# (were module-level in app.py: _read_file/_write_file/_append_file)
# ─────────────────────────────────────────
def read_file(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""


def write_file(path, content):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def append_file(path, content):
    with open(path, "a", encoding="utf-8") as f:
        f.write(content)