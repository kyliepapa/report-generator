#This is newreport.py

import re
import os
import requests
import time
from datetime import datetime
import webbrowser
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pdf_generator import generate_pdf_report
import threading
import sys

# ============================
# INPUTS (CLI OR FLASK SAFE)
# ============================
PROJECT_ID = None
PROJECT_NAME = None
multi_bath_bool = False
label_format = "123"
bathrooms_input = []
special_rooms_input = []

def set_inputs(project_id, multi_bath, label_fmt, baths, project_name=None, special_rooms=None):
    global PROJECT_ID, PROJECT_NAME, multi_bath_bool, label_format, bathrooms_input, special_rooms_input

    PROJECT_ID = project_id
    PROJECT_NAME = project_name if project_name else project_id
    multi_bath_bool = multi_bath.lower() == "yes"
    label_format = label_fmt
    bathrooms_input = [b for b in baths if b.strip()]
    special_rooms_input = [r.strip() for r in (special_rooms or []) if r.strip()]


ACCESS_TOKEN = "3kfMeyhnKVfoPhXfMJeMfNH4V71I8uS0ZDgvYVJ2ZG0".strip()


def make_bathroom_order(bath_list):
    return [b.strip() for b in bath_list if b.strip()]


PHASE_ORDER = ["UNTAGGED", "BEFORE", "AFTER"]
SPECIAL_ROOMS_NORMALIZED = []


def configure_sorting():
    global SORT_METHOD_KEY

    if label_format == "123":
        if multi_bath_bool:
            SORT_METHOD_KEY = "unit_bath_phase"
        else:
            SORT_METHOD_KEY = "unit_phase"
    else:
        if multi_bath_bool:
            SORT_METHOD_KEY = "full"
        else:
            SORT_METHOD_KEY = "bldg_unit_phase"


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
os.makedirs(STATIC_DIR, exist_ok=True)
OUTPUT_FILE = os.path.join(STATIC_DIR, "report.html")


def configure_bathrooms():
    global BATHROOM_ORDER, MASTER_INDEX

    BATHROOM_ORDER = make_bathroom_order(bathrooms_input)
    MASTER_INDEX = BATHROOM_ORDER.index("MASTER") if "MASTER" in BATHROOM_ORDER else 0


def configure_special_rooms():
    global SPECIAL_ROOMS_NORMALIZED
    SPECIAL_ROOMS_NORMALIZED = [r.upper() for r in special_rooms_input]


# ============================
# BUILDING / UNIT EXTRACTION & PARSING
# ============================
def parse_bldg_unit(tags_clean):
    global label_format

    bldg = None
    unit = None

    for t in tags_clean:
        b_match = re.search(r'\b(?:BLDG|BUILDING)\s*([A-Z0-9]{1,4})\b', t, re.IGNORECASE)
        if b_match:
            val = b_match.group(1).upper()
            bldg = val.zfill(2) if val.isdigit() else val

    for t in tags_clean:
        u_match = re.search(r'\bUNIT\s*([A-Z0-9]{1,4})\b', t, re.IGNORECASE)
        if u_match:
            val = u_match.group(1).upper()
            unit = val.zfill(3) if val.isdigit() else val

    if bldg and unit:
        return bldg, unit

    letters = [t for t in tags_clean if re.fullmatch(r'[A-Z]', t)]
    numbers = [t for t in tags_clean if re.fullmatch(r'\d{1,4}', t)]
    numbers = [n.zfill(3) for n in numbers]

    if label_format == "123":
        if unit:
            return None, unit
        if letters:
            return None, letters[0]
        if numbers:
            return None, numbers[0]
        return None, "UNASSIGNED"

    elif label_format == "123 A":
        if not unit and letters:
            unit = letters[0]
        if not bldg and numbers:
            bldg = max(numbers)

    elif label_format == "A 123":
        if not bldg and letters:
            bldg = letters[0]
        if not unit and numbers:
            unit = min(numbers)

    if (label_format in ["123 A", "A 123"]) and not letters and len(numbers) >= 2:
        sorted_nums = sorted(numbers)
        unit = sorted_nums[0]
        bldg = sorted_nums[-1]

    if not unit:
        unit = "UNASSIGNED"
    if not bldg:
        bldg = "00"

    return bldg, unit


def build_unit_bathroom_map(photos):
    unit_bathrooms = defaultdict(set)

    for p in photos:
        tags_clean = [t.strip().upper() for t in p.get("tag_names", [])]
        bldg, unit = parse_bldg_unit(tags_clean)
        bath_idx = next(
            (i for i, b in enumerate(BATHROOM_ORDER)
             if any(b.upper() in tag for tag in tags_clean)),
            -1
        )
        if unit != "UNASSIGNED" and bath_idx != -1:
            unit_bathrooms[unit].add(bath_idx)

    unit_to_single_bath = {}
    for unit, baths in unit_bathrooms.items():
        if len(baths) == 1:
            unit_to_single_bath[unit] = list(baths)[0]

    return unit_to_single_bath


def is_unassigned_photo(bath_idx, phase_idx):
    return bath_idx == -1 and phase_idx == -1


def get_special_room_match(tags_clean):
    for tag in tags_clean:
        tag_up = tag.upper()
        for i, room in enumerate(SPECIAL_ROOMS_NORMALIZED):
            if room == tag_up or room in tag_up:
                return special_rooms_input[i].title()
    return None


# ============================
# SORT FUNCTIONS
# ============================
def get_sort_key_unit_phase(photo, unit_bath_map=None):
    tags_clean = [t.strip().upper() for t in photo.get("tag_names", [])]
    bldg, unit = parse_bldg_unit(tags_clean)
    phase_idx = next((i for i, n in enumerate(PHASE_ORDER) if n in tags_clean), -1)
    phase_lbl = next((n for n in PHASE_ORDER if n in tags_clean), -1)
    return (unit, phase_idx, phase_lbl)


def get_sort_key_bldg_unit_phase(photo, unit_bath_map=None):
    tags_clean = [t.strip().upper() for t in photo.get("tag_names", [])]
    bldg, unit_val = parse_bldg_unit(tags_clean)
    phase_idx = next((i for i, n in enumerate(PHASE_ORDER) if n in tags_clean), -1)
    return (bldg, unit_val, phase_idx)


def get_sort_key_unit_bath_phase(photo, unit_bath_map=None):
    tags_clean = [t.strip().upper() for t in photo.get("tag_names", [])]
    bldg, unit_val = parse_bldg_unit(tags_clean)
    bath_idx = next(
        (i for i, b in enumerate(BATHROOM_ORDER)
         if any(b.upper() in tag for tag in tags_clean)),
        -1
    )
    phase_idx = next((i for i, n in enumerate(PHASE_ORDER) if n in tags_clean), -1)
    unassigned = is_unassigned_photo(bath_idx, phase_idx)
    if unassigned and unit_val != "UNASSIGNED" and unit_bath_map:
        if unit_val in unit_bath_map:
            bath_idx = unit_bath_map[unit_val]
    unassigned_priority = 0 if is_unassigned_photo(bath_idx, phase_idx) else 1
    return (unit_val, unassigned_priority, bath_idx, phase_idx)


def get_sort_key_full(photo, unit_bath_map=None):
    tags_clean = [t.strip().upper() for t in photo.get("tag_names", [])]
    bldg, unit_val = parse_bldg_unit(tags_clean)
    bath_idx = next(
        (i for i, b in enumerate(BATHROOM_ORDER)
         if any(b.upper() in tag for tag in tags_clean)),
        -1
    )
    phase_idx = next((i for i, n in enumerate(PHASE_ORDER) if n in tags_clean), -1)
    unassigned = is_unassigned_photo(bath_idx, phase_idx)
    if unassigned and unit_val != "UNASSIGNED" and unit_bath_map:
        if unit_val in unit_bath_map:
            bath_idx = unit_bath_map[unit_val]
    unassigned_priority = 0 if is_unassigned_photo(bath_idx, phase_idx) else 1
    return (bldg, unit_val, unassigned_priority, bath_idx, phase_idx)


def determine_sort_method(key):
    if key == "unit_phase":
        return get_sort_key_unit_phase
    elif key == "bldg_unit_phase":
        return get_sort_key_bldg_unit_phase
    elif key == "unit_bath_phase":
        return get_sort_key_unit_bath_phase
    else:
        return get_sort_key_full


def get_sort_key(photo, unit_bath_map=None):
    sort_func = determine_sort_method(SORT_METHOD_KEY)
    return sort_func(photo, unit_bath_map)


# ============================
# FETCH FUNCTIONS
# ============================
def fetch_photos():
    all_photos = []
    page = 1
    url_base = f"https://api.companycam.com/v2/projects/{PROJECT_ID}/photos"
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
    per_page = 100

    while True:
        url = f"{url_base}?page={page}&per_page={per_page}"
        r = requests.get(url, headers=headers, timeout=15)

        if r.status_code != 200:
            print("[ERROR] API Error:", r.text)
            exit()

        data = r.json()
        photos = data if isinstance(data, list) else data.get("photos", [])

        if not photos:
            break

        all_photos.extend(photos)
        print(f"[*] Fetched {len(photos)} photos on page {page}, total: {len(all_photos)}")

        if len(photos) < per_page:
            break

        page += 1

    return all_photos


def fetch_tags(photo_id, retries=3):
    url = f"https://api.companycam.com/v2/photos/{photo_id}/tags"
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}

    for attempt in range(retries):
        try:
            r = requests.get(url, headers=headers, timeout=15)

            if r.status_code == 200:
                return [t["display_value"] for t in r.json()]
            else:
                print(f"[WARN] Bad response for {photo_id}: {r.status_code}")

        except Exception as e:
            print(f"[ERROR] Attempt {attempt+1} failed for {photo_id}: {e}")

        time.sleep(1)

    print(f"[FAIL] Could not fetch tags for {photo_id}")
    return []


# ============================
# ORGANIZE PHOTOS
# ============================
def organize_photos(photos, unit_bath_map=None):
    def make_structure():
        if SORT_METHOD_KEY == "full":
            return defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(list))))
        elif SORT_METHOD_KEY == "bldg_unit_phase":
            return defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
        elif SORT_METHOD_KEY == "unit_bath_phase":
            return defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
        else:
            return defaultdict(lambda: defaultdict(list))

    structure = make_structure()
    special_rooms_structure = defaultdict(lambda: defaultdict(list))
    skipped_no_url = 0
    skipped_no_uris = 0

    def get_phase_label(idx):
        return PHASE_ORDER[idx] if isinstance(idx, int) and 0 <= idx < len(PHASE_ORDER) else "UNTAGGED"

    def get_bath_label(idx):
        return BATHROOM_ORDER[idx] if isinstance(idx, int) and 0 <= idx < len(BATHROOM_ORDER) else "OTHER"

    def normalize_unit(unit):
        if unit == "UNASSIGNED":
            return unit
        if isinstance(unit, str) and unit.isdigit():
            return unit.zfill(3)
        return unit

    def normalize_bldg(bldg):
        return bldg if bldg != "00" else "NO_BLDG"

    def get_best_image_url(photo):
        uris = photo.get("uris", [])
        for u in uris:
            if u.get("type") == "web":
                return u.get("url")
        for u in uris:
            if u.get("type") == "original":
                return u.get("url")
        for u in uris:
            if u.get("url"):
                return u.get("url")
        return None

    for p in photos:
        tags_clean = [t.strip().upper() for t in p.get("tag_names", [])]

        if SPECIAL_ROOMS_NORMALIZED:
            room_name = get_special_room_match(tags_clean)
            if room_name:
                phase_idx = next((i for i, n in enumerate(PHASE_ORDER) if n in tags_clean), -1)
                phase_key = PHASE_ORDER[phase_idx] if 0 <= phase_idx < len(PHASE_ORDER) else "UNTAGGED"
                photo_url = get_best_image_url(p)
                coordinates = p.get("coordinates", {})
                all_tags = p.get("tag_names", [])
                photo_data = {
                    "url": photo_url or "https://via.placeholder.com/200x180/cccccc/666666?text=No+Image",
                    "captured_at": p.get("captured_at"),
                    "latitude": coordinates.get("lat"),
                    "longitude": coordinates.get("lon"),
                    "has_image": photo_url is not None,
                    "all_tags": all_tags,
                    "tag_string": room_name,
                    "extra_tags": "",
                }
                special_rooms_structure[room_name][phase_key].append(photo_data)
                if not p.get("uris"):
                    skipped_no_uris += 1
                elif not photo_url:
                    skipped_no_url += 1
                continue

        sort_result = get_sort_key(p, unit_bath_map)

        if SORT_METHOD_KEY == "full":
            bldg, unit, unassigned_priority, bath_idx, phase_idx = sort_result
            bldg_key = normalize_bldg(bldg)
            unit_key = normalize_unit(unit)
            bath_key = get_bath_label(bath_idx)
            phase_key = get_phase_label(phase_idx)
        elif SORT_METHOD_KEY == "bldg_unit_phase":
            bldg, unit, phase_idx = sort_result
            bldg_key = normalize_bldg(bldg)
            unit_key = normalize_unit(unit)
            phase_key = get_phase_label(phase_idx)
        elif SORT_METHOD_KEY == "unit_bath_phase":
            unit, unassigned_priority, bath_idx, phase_idx = sort_result
            unit_key = normalize_unit(unit)
            bath_key = get_bath_label(bath_idx)
            phase_key = get_phase_label(phase_idx)
        else:
            unit, phase_idx, _ = sort_result
            unit_key = normalize_unit(unit)
            phase_key = get_phase_label(phase_idx)

        photo_url = get_best_image_url(p)
        coordinates = p.get("coordinates", {})
        all_tags = p.get("tag_names", [])

        photo_data = {
            "url": photo_url or "https://via.placeholder.com/200x180/cccccc/666666?text=No+Image",
            "captured_at": p.get("captured_at"),
            "latitude": coordinates.get("lat"),
            "longitude": coordinates.get("lon"),
            "has_image": photo_url is not None,
            "all_tags": all_tags,
            "tag_string": "",
            "extra_tags": ""
        }

        if SORT_METHOD_KEY == "full":
            photo_data["tag_string"] = build_used_tag_string(bldg_key, unit_key, bath_key, phase_key)
            photo_data["extra_tags"] = separate_extra_tags(all_tags, [bldg_key, unit_key, bath_key, phase_key])
            structure[bldg_key][unit_key][bath_key][phase_key].append(photo_data)
        elif SORT_METHOD_KEY == "bldg_unit_phase":
            photo_data["tag_string"] = build_used_tag_string(bldg_key, unit_key, None, phase_key)
            photo_data["extra_tags"] = separate_extra_tags(all_tags, [bldg_key, unit_key, phase_key])
            structure[bldg_key][unit_key][phase_key].append(photo_data)
        elif SORT_METHOD_KEY == "unit_bath_phase":
            photo_data["tag_string"] = build_used_tag_string(None, unit_key, bath_key, phase_key)
            photo_data["extra_tags"] = separate_extra_tags(all_tags, [unit_key, bath_key, phase_key])
            structure[unit_key][bath_key][phase_key].append(photo_data)
        else:
            photo_data["tag_string"] = build_used_tag_string(None, unit_key, None, phase_key)
            photo_data["extra_tags"] = separate_extra_tags(all_tags, [unit_key, phase_key])
            structure[unit_key][phase_key].append(photo_data)

        if not p.get("uris"):
            skipped_no_uris += 1
        elif not photo_url:
            skipped_no_url += 1

    print(f"[*] Photos processed: {len(photos)}")
    print(f"[*] Skipped (no URIs): {skipped_no_uris}")
    print(f"[*] Skipped (no valid URL): {skipped_no_url}")

    return structure, special_rooms_structure


# ============================
# MISSING PHOTO ANALYSIS
# ============================
def _other_bath_is_active(phases_dict):
    return bool(phases_dict.get("BEFORE") or phases_dict.get("AFTER"))


def analyze_missing_photos(structure):
    missing = {"BEFORE": [], "AFTER": []}

    def check(label, phases_dict, is_other=False):
        if is_other and not _other_bath_is_active(phases_dict):
            return
        for phase in ["BEFORE", "AFTER"]:
            if not phases_dict.get(phase):
                missing[phase].append(label)

    if SORT_METHOD_KEY == "full":
        for bldg in sorted(structure):
            for unit in sorted(structure[bldg]):
                for bath in sorted(structure[bldg][unit]):
                    lbl = f"Bldg {bldg} / Unit {unit} / {bath}"
                    check(lbl, structure[bldg][unit][bath], is_other=(bath == "OTHER"))
    elif SORT_METHOD_KEY == "bldg_unit_phase":
        for bldg in sorted(structure):
            for unit in sorted(structure[bldg]):
                lbl = f"Bldg {bldg} / Unit {unit}"
                check(lbl, structure[bldg][unit])
    elif SORT_METHOD_KEY == "unit_bath_phase":
        for unit in sorted(structure):
            for bath in sorted(structure[unit]):
                lbl = f"Unit {unit} / {bath}"
                check(lbl, structure[unit][bath], is_other=(bath == "OTHER"))
    else:
        for unit in sorted(structure):
            lbl = f"Unit {unit}"
            check(lbl, structure[unit])

    return missing


# ============================
# SHARED HTML COMPONENTS
# ============================
LIGHTBOX_CSS = """
    /* LIGHTBOX */
    .lightbox-overlay {
        display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.94);
        z-index: 9999; align-items: center; justify-content: center; gap: 24px;
        padding: 24px;
    }
    .lightbox-overlay.active { display: flex; }
    .lightbox-img-wrap { position: relative; flex-shrink: 0; }
    .lightbox-overlay img {
        max-width: 72vw; max-height: 88vh; object-fit: contain;
        border-radius: 8px; display: block;
        box-shadow: 0 8px 48px rgba(0,0,0,0.6);
    }
    .lightbox-close {
        position: absolute; top: -40px; right: 0; color: white; font-size: 30px;
        cursor: pointer; background: none; border: none; line-height: 1; opacity: 0.8;
    }
    .lightbox-close:hover { opacity: 1; }
    .lightbox-info {
        width: 240px; flex-shrink: 0; color: #cdd6e0;
        display: flex; flex-direction: column; gap: 14px;
    }
    .lightbox-info-row { display: flex; flex-direction: column; gap: 4px; }
    .lightbox-info-label {
        font-size: 10px; font-weight: 700; text-transform: uppercase;
        letter-spacing: 0.8px; color: #6b8099;
    }
    .lightbox-info-value { font-size: 13px; color: #e0eaf4; line-height: 1.5; }
    .lightbox-tags { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 2px; }
    .lightbox-tag {
        background: rgba(46,134,222,0.2); border: 1px solid rgba(46,134,222,0.4);
        color: #7ec8f7; font-size: 11px; padding: 2px 8px; border-radius: 12px;
    }
    .lightbox-geo-link { color: #7ec8f7; text-decoration: none; font-size: 13px; }
    .lightbox-geo-link:hover { text-decoration: underline; }
    .lightbox-actions { margin-top: 6px; }
    .lightbox-download {
        background: #2e86de; color: white; border: none; padding: 10px 20px;
        border-radius: 8px; cursor: pointer; font-size: 13px; text-decoration: none;
        display: inline-flex; align-items: center; gap: 7px; width: 100%;
        justify-content: center; font-weight: 600;
    }
    .lightbox-download:hover { background: #2170c2; }
    .photo-card img { cursor: zoom-in; }
"""

LIGHTBOX_HTML = """
<div class="lightbox-overlay" id="lightbox" onclick="closeLightbox(event)">
    <div class="lightbox-img-wrap">
        <button class="lightbox-close" onclick="document.getElementById('lightbox').classList.remove('active')">&#x2715;</button>
        <img id="lightbox-img" src="" alt="Photo">
    </div>
    <div class="lightbox-info">
        <div class="lightbox-info-row">
            <span class="lightbox-info-label">Timestamp</span>
            <span class="lightbox-info-value" id="lightbox-ts">—</span>
        </div>
        <div class="lightbox-info-row">
            <span class="lightbox-info-label">Location</span>
            <span class="lightbox-info-value" id="lightbox-geo">—</span>
        </div>
        <div class="lightbox-info-row">
            <span class="lightbox-info-label">Tags</span>
            <div class="lightbox-tags" id="lightbox-tags"></div>
        </div>
        <div class="lightbox-actions">
            <a id="lightbox-dl" class="lightbox-download" href="" download target="_blank">&#11015; Download Image</a>
        </div>
    </div>
</div>
"""

LIGHTBOX_JS = """
<script>
function openLightbox(url, tags, timestamp, geoLabel, geoUrl) {
    // Don't open lightbox while dragging
    if (window._dragActive) return;

    document.getElementById('lightbox-img').src = url;
    document.getElementById('lightbox-dl').href = url;
    document.getElementById('lightbox-ts').textContent = timestamp || '—';

    const geoEl = document.getElementById('lightbox-geo');
    if (geoLabel && geoUrl) {
        geoEl.innerHTML = '<a class="lightbox-geo-link" href="' + geoUrl + '" target="_blank">📍 ' + geoLabel + '</a>';
    } else {
        geoEl.textContent = 'No location data';
    }

    const tagsEl = document.getElementById('lightbox-tags');
    tagsEl.innerHTML = '';
    if (tags && tags.length) {
        tags.forEach(function(t) {
            const span = document.createElement('span');
            span.className = 'lightbox-tag';
            span.textContent = t;
            tagsEl.appendChild(span);
        });
    } else {
        tagsEl.textContent = 'None';
    }

    document.getElementById('lightbox').classList.add('active');
}
function closeLightbox(e) {
    if (e.target === document.getElementById('lightbox')) {
        document.getElementById('lightbox').classList.remove('active');
    }
}
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') document.getElementById('lightbox').classList.remove('active');
});
</script>
"""

# ── Drag-and-Drop CSS ──────────────────────────────────────────────────────────
DRAG_DROP_CSS = """
    /* ── EDIT MODE TOOLBAR ── */
    #dnd-toolbar {
        position: sticky; top: 0; z-index: 900;
        background: #1a2535;
        display: flex; align-items: center; gap: 12px;
        padding: 10px 20px;
        box-shadow: 0 2px 12px rgba(0,0,0,0.18);
        flex-wrap: wrap;
    }
    #dnd-toolbar .toolbar-label {
        font-size: 12px; font-weight: 700; text-transform: uppercase;
        letter-spacing: 0.8px; color: #8899aa; flex-shrink: 0;
    }
    #edit-mode-btn {
        padding: 7px 18px; border-radius: 20px; border: 2px solid #2e86de;
        background: transparent; color: #2e86de; font-size: 13px; font-weight: 700;
        cursor: pointer; transition: all 0.2s; white-space: nowrap;
    }
    #edit-mode-btn.active {
        background: #2e86de; color: white;
        box-shadow: 0 0 16px rgba(46,134,222,0.35);
    }
    #edit-mode-btn:hover { opacity: 0.85; }
    #undo-btn, #reset-btn {
        padding: 7px 14px; border-radius: 20px; border: 1px solid rgba(255,255,255,0.12);
        background: rgba(255,255,255,0.06); color: #cdd6e0; font-size: 12px;
        font-weight: 600; cursor: pointer; transition: all 0.18s; white-space: nowrap;
    }
    #undo-btn:hover, #reset-btn:hover {
        background: rgba(255,255,255,0.12); border-color: rgba(255,255,255,0.25);
    }
    #undo-btn:disabled, #reset-btn:disabled {
        opacity: 0.3; cursor: not-allowed;
    }
    #edit-count-badge {
        background: #e67e22; color: white; font-size: 11px; font-weight: 700;
        padding: 3px 9px; border-radius: 20px; display: none;
        animation: pop 0.2s ease;
    }
    @keyframes pop { 0%{transform:scale(0.7)} 60%{transform:scale(1.15)} 100%{transform:scale(1)} }
    #edit-mode-hint {
        font-size: 11.5px; color: #8899aa; font-style: italic; margin-left: auto;
    }

    /* ── DRAG-AND-DROP STATES ── */

    /* Card becomes draggable in edit mode */
    body.edit-mode .photo-card {
        cursor: grab;
        position: relative;
    }
    body.edit-mode .photo-card::before {
        content: '⠿';
        position: absolute; top: 5px; left: 5px; z-index: 10;
        color: white; font-size: 16px; line-height: 1;
        background: rgba(0,0,0,0.45);
        border-radius: 4px; padding: 2px 4px;
        pointer-events: none;
        opacity: 0; transition: opacity 0.15s;
    }
    body.edit-mode .photo-card:hover::before { opacity: 1; }
    body.edit-mode .photo-card img { cursor: grab; }
    body.edit-mode .photo-card.dragging {
        opacity: 0.35; transform: scale(0.97);
        box-shadow: none; cursor: grabbing;
    }

    /* Drop zone highlight */
    body.edit-mode .photo-grid {
        min-height: 60px;
        border-radius: 8px;
        transition: background 0.15s, box-shadow 0.15s;
    }
    body.edit-mode .photo-grid.drag-over {
        background: rgba(46,134,222,0.08);
        box-shadow: inset 0 0 0 2px #2e86de;
    }

    /* Drop insert line (shows between cards) */
    .drop-indicator {
        width: 3px; height: 170px;
        background: #2e86de;
        border-radius: 3px;
        flex-shrink: 0;
        box-shadow: 0 0 8px rgba(46,134,222,0.7);
        animation: blink-indicator 0.8s ease infinite alternate;
    }
    @keyframes blink-indicator {
        from { opacity: 0.6; } to { opacity: 1; }
    }

    /* "Moved" flash on a card that just landed */
    .photo-card.just-dropped {
        animation: drop-flash 0.55s ease forwards;
    }
    @keyframes drop-flash {
        0%  { box-shadow: 0 0 0 3px #2e86de; background: #e8f4ff; }
        100%{ box-shadow: 0 2px 8px rgba(0,0,0,0.08); background: white; }
    }

    /* Edit-mode: disable lightbox cursor hint */
    body.edit-mode .photo-card img { cursor: grab; }

    /* Empty-zone placeholder (shown when all cards are dragged out) */
    .drop-empty-hint {
        display: none; width: 100%; padding: 18px;
        text-align: center; font-size: 12px; color: #aab8c8; font-style: italic;
        border: 2px dashed rgba(46,134,222,0.3); border-radius: 8px;
        pointer-events: none;
    }
    body.edit-mode .photo-grid:empty + .drop-empty-hint,
    body.edit-mode .drop-empty-hint.visible { display: block; }
"""

# ── Drag-and-Drop JS ───────────────────────────────────────────────────────────
DRAG_DROP_JS = """
<script>
// ============================================================
// DRAG-AND-DROP ENGINE
// ============================================================

// Global state
window._editMode   = false;
window._dragActive = false;
let _dragging      = null;   // the card element being dragged
let _sourceZone    = null;   // the photo-grid it came from
let _undoStack     = [];     // [{card, fromZone, fromIndex, toZone, toIndex}]
let _editCount     = 0;

// ── Edit-mode toggle ────────────────────────────────────────
const editBtn  = document.getElementById('edit-mode-btn');
const undoBtn  = document.getElementById('undo-btn');
const resetBtn = document.getElementById('reset-btn');
const badge    = document.getElementById('edit-count-badge');

editBtn.addEventListener('click', toggleEditMode);

function toggleEditMode() {
    window._editMode = !window._editMode;
    document.body.classList.toggle('edit-mode', window._editMode);
    editBtn.classList.toggle('active', window._editMode);
    editBtn.textContent = window._editMode ? '✏️ Editing On' : '✏️ Edit Photos';
    document.getElementById('edit-mode-hint').textContent = window._editMode
        ? 'Drag photos between zones · Ctrl+Z to undo'
        : 'Enable to rearrange photos';
    refreshZones();
}

// Keyboard shortcut: Ctrl/Cmd+Z → undo
document.addEventListener('keydown', function(e) {
    if ((e.ctrlKey || e.metaKey) && e.key === 'z' && window._editMode) {
        e.preventDefault();
        undoLast();
    }
});

// ── Undo ────────────────────────────────────────────────────
undoBtn.addEventListener('click', undoLast);

function undoLast() {
    if (!_undoStack.length) return;
    const op = _undoStack.pop();

    // Re-insert the card at its original position
    const children = [...op.fromZone.querySelectorAll('.photo-card')];
    if (op.fromIndex >= children.length) {
        op.fromZone.appendChild(op.card);
    } else {
        op.fromZone.insertBefore(op.card, children[op.fromIndex]);
    }

    op.card.classList.add('just-dropped');
    op.card.addEventListener('animationend', () => op.card.classList.remove('just-dropped'), {once:true});

    _editCount = Math.max(0, _editCount - 1);
    refreshBadge();
    refreshZones();
    syncCounters();
}

// ── Reset all edits ─────────────────────────────────────────
resetBtn.addEventListener('click', function() {
    if (!_undoStack.length) return;
    if (!confirm('Reset all photo edits and restore the original layout?')) return;
    while (_undoStack.length) undoLast();
});

// ── Helpers ─────────────────────────────────────────────────
function refreshBadge() {
    undoBtn.disabled  = _undoStack.length === 0;
    resetBtn.disabled = _undoStack.length === 0;
    if (_editCount > 0) {
        badge.textContent = _editCount + ' edit' + (_editCount !== 1 ? 's' : '');
        badge.style.display = 'inline-block';
    } else {
        badge.style.display = 'none';
    }
}

// Update the "(N photos)" counters in each phase-section header
function syncCounters() {
    document.querySelectorAll('.phase-section').forEach(section => {
        const grid    = section.querySelector('.photo-grid');
        const counter = section.querySelector('.phase-count');
        if (grid && counter) {
            const n = grid.querySelectorAll('.photo-card').length;
            counter.textContent = n + ' photo' + (n !== 1 ? 's' : '');
        }
    });
}

// Ensure every photo-grid has a drop-empty-hint sibling
function refreshZones() {
    document.querySelectorAll('.photo-grid').forEach(grid => {
        let hint = grid.nextElementSibling;
        if (!hint || !hint.classList.contains('drop-empty-hint')) {
            hint = document.createElement('div');
            hint.className = 'drop-empty-hint';
            hint.textContent = 'Drop photos here';
            grid.parentNode.insertBefore(hint, grid.nextSibling);
        }
        // Toggle visibility
        const empty = grid.querySelectorAll('.photo-card').length === 0;
        hint.classList.toggle('visible', empty && window._editMode);
    });
}

// ── Drag event wiring ────────────────────────────────────────
// We use event delegation on document so dynamically-moved cards
// keep working without re-binding.

document.addEventListener('dragstart', function(e) {
    if (!window._editMode) return;
    const card = e.target.closest('.photo-card');
    if (!card) return;

    _dragging       = card;
    _sourceZone     = card.closest('.photo-grid');
    window._dragActive = true;

    // Semi-transparent ghost (browser default is fine, but we fade the source)
    setTimeout(() => card.classList.add('dragging'), 0);
    e.dataTransfer.effectAllowed = 'move';
    // Store card URL as transfer data (used for cross-zone logic)
    const img = card.querySelector('img');
    if (img) e.dataTransfer.setData('text/plain', img.src);
});

document.addEventListener('dragend', function(e) {
    if (_dragging) {
        _dragging.classList.remove('dragging');
        _dragging = null;
    }
    window._dragActive = false;

    // Clean up all drop indicators and highlights
    document.querySelectorAll('.drop-indicator').forEach(el => el.remove());
    document.querySelectorAll('.photo-grid.drag-over').forEach(el => el.classList.remove('drag-over'));
    refreshZones();
    syncCounters();
});

document.addEventListener('dragover', function(e) {
    if (!window._editMode || !_dragging) return;
    const grid = e.target.closest('.photo-grid');
    if (!grid) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';

    grid.classList.add('drag-over');

    // Remove any existing indicator
    grid.querySelectorAll('.drop-indicator').forEach(el => el.remove());

    // Find the card we're hovering over and insert an indicator before it
    const cards = [...grid.querySelectorAll('.photo-card:not(.dragging)')];
    let insertBefore = null;

    for (const c of cards) {
        const rect = c.getBoundingClientRect();
        const midX = rect.left + rect.width / 2;
        if (e.clientX < midX) {
            insertBefore = c;
            break;
        }
    }

    const indicator = document.createElement('div');
    indicator.className = 'drop-indicator';
    if (insertBefore) {
        grid.insertBefore(indicator, insertBefore);
    } else {
        grid.appendChild(indicator);
    }
});

document.addEventListener('dragleave', function(e) {
    const grid = e.target.closest('.photo-grid');
    if (!grid) return;
    // Only clear if we truly left the grid (not entered a child)
    if (!grid.contains(e.relatedTarget)) {
        grid.classList.remove('drag-over');
        grid.querySelectorAll('.drop-indicator').forEach(el => el.remove());
    }
});

document.addEventListener('drop', function(e) {
    if (!window._editMode || !_dragging) return;
    const grid = e.target.closest('.photo-grid');
    if (!grid || grid === _dragging) return;
    e.preventDefault();

    grid.classList.remove('drag-over');

    // Find insert position (before whichever card the cursor is left of)
    const cards = [...grid.querySelectorAll('.photo-card:not(.dragging)')];
    let insertBefore = null;
    for (const c of cards) {
        const rect = c.getBoundingClientRect();
        if (e.clientX < rect.left + rect.width / 2) {
            insertBefore = c;
            break;
        }
    }

    // Record undo state BEFORE the move
    const fromZone  = _sourceZone;
    const fromIndex = [...fromZone.querySelectorAll('.photo-card')].indexOf(_dragging);
    const toZone    = grid;
    const toIndex   = insertBefore
        ? [...toZone.querySelectorAll('.photo-card')].indexOf(insertBefore)
        : toZone.querySelectorAll('.photo-card').length;

    _undoStack.push({ card: _dragging, fromZone, fromIndex, toZone, toIndex });

    // Perform the move
    if (insertBefore) {
        grid.insertBefore(_dragging, insertBefore);
    } else {
        grid.appendChild(_dragging);
    }

    // Visual feedback
    _dragging.classList.add('just-dropped');
    _dragging.addEventListener('animationend', () => _dragging.classList.remove('just-dropped'), {once:true});

    _editCount++;
    refreshBadge();
    refreshZones();
    syncCounters();
});

// ── Make all cards draggable in edit mode ───────────────────
// We set draggable=true on all .photo-card elements at init,
// but only the dragstart handler actually fires when editMode is off.
document.querySelectorAll('.photo-card').forEach(card => {
    card.setAttribute('draggable', 'true');
});

// ── Initial state ────────────────────────────────────────────
refreshBadge();
refreshZones();
</script>
"""

# ── Updated PDF_PROGRESS_JS: sends current DOM order to the server ─────────────
PDF_PROGRESS_JS = """
<script>
function collectPhotoEdits() {
    // Walk every photo-grid in DOM order and record [zoneId → [orderedPhotoUrls]]
    // The zone id is the data-zone attribute set on each .photo-grid
    const edits = {};
    document.querySelectorAll('.photo-grid[data-zone]').forEach(grid => {
        const zoneId = grid.dataset.zone;
        const urls = [...grid.querySelectorAll('.photo-card img')].map(img => img.src);
        edits[zoneId] = urls;
    });
    return edits;
}

function generatePDF() {
    const params = new URLSearchParams(window.location.search);
    const btn    = document.getElementById('pdfBtn');
    const status = document.getElementById('pdfStatus');
    const bar    = document.getElementById('pdfProgressBar');
    const barWrap= document.getElementById('pdfProgressWrap');

    btn.disabled = true;
    btn.textContent = "Generating...";
    barWrap.style.display = "block";
    bar.style.width = "0%";
    status.textContent = "Starting...";

    const photoEdits = _editCount > 0 ? collectPhotoEdits() : null;

    fetch('/start_pdf_job', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            project_id:   params.get("project_id"),
            project_name: params.get("project_name"),
            multi_bath:   params.get("multi_bath"),
            label_format: params.get("label_format"),
            bath_names:   params.get("bath_names"),
            special_rooms:params.get("special_rooms"),
            photo_edits:  photoEdits,   // ← drag-and-drop order, or null
        }),
    })
    .then(res => res.json())
    .then(({ job_id }) => {
        const interval = setInterval(() => {
            fetch(`/job_status/${job_id}`)
                .then(res => res.json())
                .then(data => {
                    if (data.status === "complete") {
                        clearInterval(interval);
                        bar.style.width = "100%";
                        status.textContent = _editCount > 0
                            ? "✅ PDF ready! (" + _editCount + " edit" + (_editCount!==1?'s':'') + " applied)"
                            : "✅ PDF ready!";
                        btn.textContent = "Open PDF";
                        btn.disabled = false;
                        btn.onclick = () => window.open(`/reports/${data.pdf_filename}`, "_blank");
                    }
                    if (data.status === "error") {
                        clearInterval(interval);
                        status.textContent = "❌ Error generating PDF";
                        btn.textContent = "Try Again";
                        btn.disabled = false;
                        btn.onclick = generatePDF;
                    }
                });
        }, 2000);
    });
}
</script>
"""

PDF_BUTTON_HTML = """
<button id="pdfBtn" onclick="generatePDF()" style="
    margin-top:16px; padding:11px 26px; font-size:15px;
    background:#3498db; color:white; border:none; border-radius:8px; cursor:pointer;
    font-weight:600; transition:background 0.2s;">
    ⬇ Download PDF
</button>
<div id="pdfProgressWrap" style="display:none; margin-top:14px; width:320px;">
    <div style="background:#e0e0e0; border-radius:6px; height:10px; overflow:hidden;">
        <div id="pdfProgressBar" style="background:#3498db; height:100%; width:0%; transition:width 0.4s ease; border-radius:6px;"></div>
    </div>
    <div id="pdfStatus" style="margin-top:8px; font-size:13px; color:#555;"></div>
</div>
"""

# ── Edit-mode toolbar HTML (injected once at top of <body>) ───────────────────
DND_TOOLBAR_HTML = """
<div id="dnd-toolbar">
    <span class="toolbar-label">Layout</span>
    <button id="edit-mode-btn">✏️ Edit Photos</button>
    <button id="undo-btn" disabled>↩ Undo</button>
    <button id="reset-btn" disabled>⟳ Reset</button>
    <span id="edit-count-badge"></span>
    <span id="edit-mode-hint">Enable to rearrange photos</span>
</div>
"""


def make_photo_card_html(photo_data, idx=None, zone_id=None):
    """
    Renders one photo card.
    zone_id is unused here but kept for signature compatibility.
    The data-zone attribute is placed on the .photo-grid wrapper, not individual cards.
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
            dt = datetime.fromtimestamp(int(captured_at))
            timestamp_str = dt.strftime("%Y-%m-%d %H:%M")
        except:
            timestamp_str = "Unknown"

    img_style = "" if has_image else "filter: grayscale(100%); opacity: 0.6;"

    import json
    tags_json = json.dumps(all_tags)
    geo_label = f"{latitude:.4f}, {longitude:.4f}" if (latitude and longitude) else ""
    geo_url   = f"https://www.google.com/maps/search/?api=1&query={latitude},{longitude}" if (latitude and longitude) else ""

    html  = f'<div class="photo-card" draggable="true">'
    html += f'<img src="{url}" loading="lazy" style="{img_style}" onclick=\'openLightbox({json.dumps(url)},{tags_json},{json.dumps(timestamp_str)},{json.dumps(geo_label)},{json.dumps(geo_url)})\'>'
    html += '<div class="photo-metadata">'
    html += f'<div class="timestamp">📷 {timestamp_str}</div>'
    if not has_image:
        html += '<div class="geotag" style="color:#e74c3c;">⚠️ No image available</div>'
    if latitude and longitude:
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
    return """
        :root {
            --primary: #1a2535;
            --accent: #2e86de;
            --accent2: #10ac84;
            --danger: #e74c3c;
            --bg: #f0f3f8;
            --card: #ffffff;
            --text: #2d3436;
            --muted: #636e72;
            --border: #dde3ed;
            --shadow: 0 4px 16px rgba(0,0,0,0.09);
            --radius: 12px;
        }
        * { box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', system-ui, sans-serif;
            margin: 0; background: var(--bg); color: var(--text);
        }
        .container { max-width: 1440px; margin: 0 auto; padding: 24px; }
        .report-header {
            background: linear-gradient(135deg, var(--primary) 0%, #2c4a7c 100%);
            color: white; padding: 36px 40px; border-radius: var(--radius);
            text-align: center; margin-bottom: 28px; box-shadow: var(--shadow);
        }
        .report-header h1 { margin: 0; font-size: 2.2em; font-weight: 300; letter-spacing: 1px; }
        .report-header .meta { margin-top: 8px; opacity: 0.85; font-size: 1em; }
        .summary {
            display: flex; justify-content: center; flex-wrap: wrap; gap: 16px; margin-bottom: 28px;
        }
        .summary-item {
            background: var(--card); padding: 18px 28px; border-radius: var(--radius);
            box-shadow: var(--shadow); text-align: center; min-width: 130px;
            transition: transform 0.18s;
        }
        .summary-item:hover { transform: translateY(-3px); }
        .summary-item .number { font-size: 2em; font-weight: 700; color: var(--accent); display: block; }
        .summary-item .label { font-size: 0.85em; color: var(--muted); margin-top: 4px; }
        .building-section { margin-bottom: 50px; }
        .building-title {
            font-size: 1.6em; color: var(--primary); border-left: 5px solid var(--accent);
            padding-left: 14px; margin-bottom: 18px; font-weight: 600;
        }
        .unit-section {
            background: var(--card); border-radius: var(--radius); margin-bottom: 24px;
            box-shadow: var(--shadow); overflow: hidden;
        }
        .unit-header {
            background: var(--primary); color: white; padding: 14px 22px;
            font-size: 1.15em; font-weight: 600;
        }
        .bathroom-group { padding: 20px; border-bottom: 1px solid var(--border); }
        .bathroom-header {
            font-size: 1em; font-weight: 600; margin-bottom: 14px;
            color: var(--accent); text-transform: uppercase; letter-spacing: 0.5px;
        }
        .unit-phases { display: flex; gap: 16px; flex-wrap: wrap; }
        .phase-section {
            flex: 1; min-width: 260px; background: #fafbfd;
            border-radius: 8px; padding: 14px; border: 1px solid var(--border);
        }
        .phase-header { margin-bottom: 12px; display: flex; align-items: center; gap: 10px; }
        .phase-title { font-size: 1em; font-weight: 600; margin: 0; }
        .phase-badge {
            padding: 3px 10px; border-radius: 20px; font-size: 0.75em;
            color: white; font-weight: 700; text-transform: uppercase;
        }
        .phase-badge.before { background: var(--danger); }
        .phase-badge.after { background: var(--accent2); }
        .phase-badge.untagged { background: #95a5a6; }
        .phase-count { margin-left: auto; font-size: 0.85em; color: var(--muted); }
        .photo-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); gap: 12px; }
        .photo-card {
            background: white; border-radius: 8px; overflow: hidden;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08); transition: transform 0.18s, box-shadow 0.18s;
        }
        .photo-card:hover { transform: translateY(-3px); box-shadow: 0 6px 18px rgba(0,0,0,0.14); }
        .photo-card img { width: 100%; height: 170px; object-fit: cover; display: block; }
        .photo-metadata { padding: 9px 10px; font-size: 0.8em; color: var(--muted); }
        .timestamp { font-weight: 600; color: var(--text); margin-bottom: 4px; }
        .geotag-link { color: var(--accent); text-decoration: none; }
        .geotag-link:hover { text-decoration: underline; }
        .no-photos {
            text-align: center; padding: 24px; color: var(--muted); font-style: italic;
            border: 2px dashed var(--border); border-radius: 8px; background: white;
        }
        @media (max-width: 900px) { .unit-phases { flex-direction: column; } }
    """


# ── Zone-ID generator ─────────────────────────────────────────────────────────
def _zone_id(*parts):
    """Creates a stable, URL-safe zone identifier from structural keys."""
    return "__".join(str(p).replace(" ", "_") for p in parts if p)


# ── Head snippet (combines all CSS) ──────────────────────────────────────────
def _make_head(title):
    return f"""<!DOCTYPE html><html><head>
    <title>{title} — Report</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>{make_shared_css()}{LIGHTBOX_CSS}{DRAG_DROP_CSS}</style>
    </head><body>
    {DND_TOOLBAR_HTML}
    {LIGHTBOX_HTML}"""


def _make_tail():
    return f'{LIGHTBOX_JS}{PDF_PROGRESS_JS}{DRAG_DROP_JS}</body></html>'


# ── Phase-section builder (shared by all 4 generators) ───────────────────────
def _phase_section(photos, phase, zone_id):
    badge = "before" if phase == "BEFORE" else ("after" if phase == "AFTER" else "untagged")
    label = phase if phase != "UNTAGGED" else "Untagged"
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


# ============================
# HTML GENERATORS (ALL MODES)
# ============================
def generate_html_unit_phase(structure, special_rooms_structure=None):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    title = PROJECT_NAME or PROJECT_ID
    total_units = len(structure)
    total_photos = sum(len(ph) for u in structure.values() for ph in u.values())

    html  = _make_head(title)
    html += f"""<div class="container">
        <div class="report-header">
            <h1>{title}</h1>
            <div class="meta">Generated {now}</div>
            {PDF_BUTTON_HTML}
        </div>
        <div class="summary">
            <div class="summary-item"><span class="number">{total_units}</span><div class="label">Units</div></div>
            <div class="summary-item"><span class="number">{total_photos}</span><div class="label">Photos</div></div>
        </div>
        <div class="content">"""

    for unit in sorted(structure, key=lambda u: (u == "UNASSIGNED", u)):
        html += f'<div class="unit-section"><div class="unit-header">🏠 Unit {unit}</div>'
        html += '<div class="unit-phases" style="padding:20px;">'
        for phase in PHASE_ORDER:
            photos = structure[unit].get(phase, [])
            if phase == "UNTAGGED" and not photos:
                continue
            zid = _zone_id("unit", unit, phase)
            html += _phase_section(photos, phase, zid)
        html += '</div></div>'

    html += generate_special_rooms_html(special_rooms_structure or {})
    html += f'</div></div>{_make_tail()}'
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)


def generate_html_bldg_unit_phase(structure, special_rooms_structure=None):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    title = PROJECT_NAME or PROJECT_ID
    total_buildings = len(structure)
    total_units = sum(len(units) for units in structure.values())
    total_photos = sum(len(photos) for units in structure.values()
                       for phases in units.values() for photos in phases.values())

    html  = _make_head(title)
    html += f"""<div class="container">
        <div class="report-header">
            <h1>{title}</h1>
            <div class="meta">Generated {now}</div>
            {PDF_BUTTON_HTML}
        </div>
        <div class="summary">
            <div class="summary-item"><span class="number">{total_buildings}</span><div class="label">Buildings</div></div>
            <div class="summary-item"><span class="number">{total_units}</span><div class="label">Units</div></div>
            <div class="summary-item"><span class="number">{total_photos}</span><div class="label">Photos</div></div>
        </div>
        <div class="content">"""

    for bldg in sorted(structure):
        html += f'<div class="building-section"><h2 class="building-title">🏢 Building {bldg}</h2>'
        for unit in sorted(structure[bldg], key=lambda u: (u == "UNASSIGNED", u)):
            html += f'<div class="unit-section"><div class="unit-header">🏠 Unit {unit}</div>'
            html += '<div class="unit-phases" style="padding:20px;">'
            for phase in PHASE_ORDER:
                photos = structure[bldg][unit].get(phase, [])
                if phase == "UNTAGGED" and not photos:
                    continue
                zid = _zone_id("bldg", bldg, "unit", unit, phase)
                html += _phase_section(photos, phase, zid)
            html += '</div></div>'
        html += '</div>'

    html += generate_special_rooms_html(special_rooms_structure or {})
    html += f'</div></div>{_make_tail()}'
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)


def generate_html_unit_bath_phase(structure, special_rooms_structure=None):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    title = PROJECT_NAME or PROJECT_ID
    total_units = len(structure)
    total_photos = sum(len(photos) for units in structure.values()
                       for baths in units.values() for photos in baths.values())

    html  = _make_head(title)
    html += f"""<div class="container">
        <div class="report-header">
            <h1>{title}</h1>
            <div class="meta">Generated {now}</div>
            {PDF_BUTTON_HTML}
        </div>
        <div class="summary">
            <div class="summary-item"><span class="number">{total_units}</span><div class="label">Units</div></div>
            <div class="summary-item"><span class="number">{total_photos}</span><div class="label">Photos</div></div>
        </div>
        <div class="content">"""

    for unit in sorted(structure, key=lambda u: (u == "UNASSIGNED", u)):
        html += f'<div class="unit-section"><div class="unit-header">🏠 Unit {unit}</div>'
        for bath in sorted(structure[unit]):
            html += f'<div class="bathroom-group"><div class="bathroom-header">🛁 {bath}</div>'
            html += '<div class="unit-phases">'
            for phase in PHASE_ORDER:
                photos = structure[unit][bath].get(phase, [])
                if phase == "UNTAGGED" and not photos:
                    continue
                zid = _zone_id("unit", unit, "bath", bath, phase)
                html += _phase_section(photos, phase, zid)
            html += '</div></div>'
        html += '</div>'

    html += generate_special_rooms_html(special_rooms_structure or {})
    html += f'</div></div>{_make_tail()}'
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)


def generate_html_full_hierarchy(structure, special_rooms_structure=None):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    title = PROJECT_NAME or PROJECT_ID
    total_buildings = len(structure)
    total_units = sum(len(units) for units in structure.values())
    total_photos = sum(len(photos) for units in structure.values()
                       for units_val in units.values()
                       for baths in units_val.values()
                       for photos in baths.values())

    html  = _make_head(title)
    html += f"""<div class="container">
        <div class="report-header">
            <h1>{title}</h1>
            <div class="meta">Installation Photos | Generated {now}</div>
            {PDF_BUTTON_HTML}
        </div>
        <div class="summary">
            <div class="summary-item"><span class="number">{total_buildings}</span><div class="label">Buildings</div></div>
            <div class="summary-item"><span class="number">{total_units}</span><div class="label">Units</div></div>
            <div class="summary-item"><span class="number">{total_photos}</span><div class="label">Photos</div></div>
        </div>
        <div class="content">"""

    for bldg in sorted(structure):
        html += f'<div class="building-section"><h2 class="building-title">🏢 Building {bldg}</h2>'
        for unit in sorted(structure[bldg], key=lambda u: (u == "UNASSIGNED", u)):
            html += f'<div class="unit-section"><div class="unit-header">🏠 Unit {unit}</div>'
            for bath in sorted(structure[bldg][unit]):
                html += f'<div class="bathroom-group"><div class="bathroom-header">🛁 {bath}</div>'
                html += '<div class="unit-phases">'
                for phase in PHASE_ORDER:
                    photos = structure[bldg][unit][bath].get(phase, [])
                    if phase == "UNTAGGED" and not photos:
                        continue
                    zid = _zone_id("bldg", bldg, "unit", unit, "bath", bath, phase)
                    html += _phase_section(photos, phase, zid)
                html += '</div></div>'
            html += '</div>'
        html += '</div>'

    html += generate_special_rooms_html(special_rooms_structure or {})
    html += f'</div></div>{_make_tail()}'
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)


def determine_html_method(key):
    if key == "unit_phase":
        return generate_html_unit_phase
    elif key == "bldg_unit_phase":
        return generate_html_bldg_unit_phase
    elif key == "unit_bath_phase":
        return generate_html_unit_bath_phase
    else:
        return generate_html_full_hierarchy


def generate_special_rooms_html(special_rooms_structure):
    if not special_rooms_structure:
        return ""

    html = '<div class="building-section special-rooms-section">'
    html += '<h2 class="building-title" style="border-left-color:#9b59b6;">🏛 Special Areas</h2>'

    for room_name in sorted(special_rooms_structure):
        phases_dict = special_rooms_structure[room_name]
        html += f'<div class="unit-section"><div class="unit-header" style="background:#6c3483;">🏛 {room_name}</div>'
        html += '<div class="unit-phases" style="padding:20px;">'
        for phase in PHASE_ORDER:
            photos = phases_dict.get(phase, [])
            if phase == "UNTAGGED" and not photos:
                continue
            zid = _zone_id("special", room_name.replace(" ", "_"), phase)
            html += _phase_section(photos, phase, zid)
        html += '</div></div>'

    html += '</div>'
    return html


# ============================
# PDF HELPER FUNCTIONS
# ============================
def title_case_tag(tag):
    return " ".join(w.capitalize() for w in tag.split())


def build_used_tag_string(bldg, unit, bath, phase):
    parts = []
    if bldg and bldg not in ("NO_BLDG", "00"):
        parts.append(f"Building {bldg}")
    if unit and unit != "UNASSIGNED":
        parts.append(f"Unit {unit}")
    if bath and bath != "OTHER":
        parts.append(f"{bath.title()} Bathroom")
    if phase and phase != "UNTAGGED":
        parts.append(phase.title())
    return " — ".join(parts)


def separate_extra_tags(all_tags, used_parts):
    used_words = set(" ".join(str(p) for p in used_parts if p).upper().split())
    extras = []
    for t in all_tags:
        words = t.upper().split()
        if not any(w in used_words for w in words):
            extras.append(title_case_tag(t))
    return ", ".join(sorted(extras))


# ============================
# PDF DATA ENGINE (ALL MODES)
# ============================
def build_pdf_context(structure, photos, special_rooms_structure=None):
    total_photos = len(photos)
    total_buildings = 0
    total_units = 0
    total_bathrooms = 0

    if SORT_METHOD_KEY == "full":
        total_buildings = len(structure)
        total_units = sum(len(units) for units in structure.values())
        total_bathrooms = sum(
            1 for units in structure.values()
            for baths in units.values()
            for bath, phases in baths.items()
            if bath != "OTHER" or _other_bath_is_active(phases)
        )
    elif SORT_METHOD_KEY == "bldg_unit_phase":
        total_buildings = len(structure)
        total_units = sum(len(units) for units in structure.values())
    elif SORT_METHOD_KEY == "unit_bath_phase":
        total_units = len(structure)
        total_bathrooms = sum(
            1 for baths in structure.values()
            for bath, phases in baths.items()
            if bath != "OTHER" or _other_bath_is_active(phases)
        )
    else:
        total_units = len(structure)

    context = {
        "project_id": PROJECT_ID,
        "project_name": PROJECT_NAME or PROJECT_ID,
        "project_name_upper": (PROJECT_NAME or PROJECT_ID).upper(),
        "address": "Project Address",
        "date_generated": datetime.now().strftime("%B %d, %Y"),
        "total_photos": total_photos,
        "total_buildings": total_buildings,
        "total_units": total_units,
        "total_bathrooms": total_bathrooms,
        "sort_mode": SORT_METHOD_KEY,
        "structured": structure,
        "special_rooms_structured": special_rooms_structure or {},
    }

    print("\n========= REPORT METRICS =========")
    print(f"Mode: {SORT_METHOD_KEY}")
    print(f"Buildings: {total_buildings}")
    print(f"Units: {total_units}")
    print(f"Bathrooms: {total_bathrooms}")
    print(f"Photos: {total_photos}")
    if special_rooms_structure:
        print(f"Special rooms: {list(special_rooms_structure.keys())}")
    print("==================================\n")

    return context


# ============================
# MAIN
# ============================
def main():
    print("[*] Generating professional report...")

    photos = fetch_photos()
    print(f"[*] Total photos to process: {len(photos)}")

    total = len(photos)
    start_time = time.time()
    print(f"[*] Fetching tags for {total} photos...\n")
    for i, photo in enumerate(photos, 1):
        photo["tag_names"] = fetch_tags(photo["id"])
        if i % 10 == 0 or i == total:
            elapsed = time.time() - start_time
            rate = i / elapsed if elapsed > 0 else 0
            remaining = (total - i) / rate if rate > 0 else 0
            print(f"[{i}/{total}] ({rate:.1f} photos/sec) ETA: {remaining:.1f}s")

    print("[*] Tag fetching complete. Sorting photos...")
    unit_bath_map = build_unit_bathroom_map(photos)
    photos.sort(key=lambda p: get_sort_key(p, unit_bath_map))

    structured, special_rooms_structured = organize_photos(photos, unit_bath_map)
    pdf_context = build_pdf_context(structured, photos, special_rooms_structured)

    print("[*] Generating HTML...")
    function_to_generate_html = determine_html_method(SORT_METHOD_KEY)
    function_to_generate_html(structured, special_rooms_structured)

    generate_pdf_report(pdf_context)


if __name__ == "__main__":
    main()