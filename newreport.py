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

def set_inputs(project_id, multi_bath, label_fmt, baths, project_name=None):
    global PROJECT_ID, PROJECT_NAME, multi_bath_bool, label_format, bathrooms_input

    PROJECT_ID = project_id
    PROJECT_NAME = project_name if project_name else project_id
    multi_bath_bool = multi_bath.lower() == "yes"
    label_format = label_fmt
    bathrooms_input = [b for b in baths if b.strip()]


ACCESS_TOKEN = "3kfMeyhnKVfoPhXfMJeMfNH4V71I8uS0ZDgvYVJ2ZG0".strip()


def make_bathroom_order(bath_list):
    return [b.strip() for b in bath_list if b.strip()]


PHASE_ORDER = ["UNTAGGED", "BEFORE", "AFTER"]


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


# ============================
# UNIT EXTRACTION
# ============================
def extract_unit(tags_clean):
    for t in tags_clean:
        match = re.search(r'\bUNIT\s*([A-Z0-9]{1,4})\b', t)
        if match:
            val = match.group(1)
            return val.zfill(3) if val.isdigit() else val

    for t in tags_clean:
        if re.fullmatch(r'\d{1,4}', t):
            return t.zfill(3)

    return "UNASSIGNED"


def build_unit_bathroom_map(photos):
    unit_bathrooms = defaultdict(set)

    for p in photos:
        tags_clean = [t.strip().upper() for t in p.get("tag_names", [])]
        unit = extract_unit(tags_clean)
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


# ============================
# SORT FUNCTIONS
# ============================
def get_sort_key_unit_phase(photo, unit_bath_map=None):
    tags_clean = [t.strip().upper() for t in photo.get("tag_names", [])]
    unit = extract_unit(tags_clean)
    phase_idx = next((i for i, n in enumerate(PHASE_ORDER) if n in tags_clean), -1)
    phase_lbl = next((n for n in PHASE_ORDER if n in tags_clean), -1)
    return (unit, phase_idx, phase_lbl)


def get_sort_key_bldg_unit_phase(photo, unit_bath_map=None):
    tags_clean = [t.strip().upper() for t in photo.get("tag_names", [])]
    bldg = "00"
    unit_val = extract_unit(tags_clean)
    for t in tags_clean:
        b_match = re.search(r'\b(?:BLDG|BUILDING)\s*(\d+)\b', t)
        if b_match:
            bldg = b_match.group(1).zfill(2)
            break
    phase_idx = next((i for i, n in enumerate(PHASE_ORDER) if n in tags_clean), -1)
    return (bldg, unit_val, phase_idx)


def get_sort_key_unit_bath_phase(photo, unit_bath_map=None):
    tags_clean = [t.strip().upper() for t in photo.get("tag_names", [])]
    unit_val = extract_unit(tags_clean)
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
    unit_val = extract_unit(tags_clean)
    bldg = "00"
    for t in tags_clean:
        b_match = re.search(r'\b(?:BLDG|BUILDING)\s*(\d+)\b', t)
        if b_match:
            bldg = b_match.group(1).zfill(2)
            break
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

# Pre-timeout & retries version
# def fetch_tags(photo_id):
#     url = f"https://api.companycam.com/v2/photos/{photo_id}/tags"
#     headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
#     r = requests.get(url, headers=headers)

#     if r.status_code == 200:
#         return [t["display_value"] for t in r.json()]
#     return []

# Post timeout & retries version
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

        # wait before retrying
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

    return structure


# ============================
# MISSING PHOTO ANALYSIS
# ============================
def _other_bath_is_active(phases_dict):
    """OTHER bathroom only counts if it has at least one BEFORE or AFTER photo."""
    return bool(phases_dict.get("BEFORE") or phases_dict.get("AFTER"))


def analyze_missing_photos(structure):
    """Returns summary counts and a detailed list of missing before/after photos."""
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

# PDF_PROGRESS_JS = """
# <script>
# function generatePDF() {
#     const params = new URLSearchParams(window.location.search);
#     const btn = document.getElementById('pdfBtn');
#     const bar = document.getElementById('pdfProgressBar');
#     const barWrap = document.getElementById('pdfProgressWrap');
#     const status = document.getElementById('pdfStatus');

#     btn.disabled = true;
#     btn.textContent = 'Generating...';
#     barWrap.style.display = 'block';
#     status.textContent = 'Starting PDF generation...';

#     let progress = 0;
#     const interval = setInterval(() => {
#         progress = Math.min(progress + Math.random() * 8, 88);
#         bar.style.width = progress + '%';
#     }, 600);

#     fetch(`/generate_pdf?${params}`)
#         .then(res => res.json())
#         .then(data => {
#             clearInterval(interval);
#             bar.style.width = '100%';
#             if (data.status === 'success') {
#                 status.textContent = '✅ PDF ready!';
#                 btn.textContent = 'Open PDF';
#                 btn.disabled = false;
#                 btn.onclick = () => window.open(`/reports/${data.filename}`);
#             } else {
#                 status.textContent = '❌ Error: ' + data.message;
#                 btn.textContent = 'Try Again';
#                 btn.disabled = false;
#                 btn.onclick = generatePDF;
#             }
#         })
#         .catch(err => {
#             clearInterval(interval);
#             status.textContent = '❌ Server error';
#             btn.textContent = 'Try Again';
#             btn.disabled = false;
#             btn.onclick = generatePDF;
#         });
# }
# </script>
# """
PDF_PROGRESS_JS = """
<script>
function generatePDF() {
    const params = new URLSearchParams(window.location.search);
    const btn = document.getElementById('pdfBtn');
    const status = document.getElementById('pdfStatus');
    const bar = document.getElementById('pdfProgressBar');
    const barWrap = document.getElementById('pdfProgressWrap');

    btn.disabled = true;
    btn.textContent = "Generating...";
    barWrap.style.display = "block";
    bar.style.width = "0%";
    status.textContent = "Starting...";

    fetch('/start_pdf_job', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
        project_id: params.get("project_id"),
        project_name: params.get("project_name"),
        multi_bath: params.get("multi_bath"),
        label_format: params.get("label_format"),
        bath_names: params.get("bath_names"),
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
                        status.textContent = "✅ PDF ready!";

                        btn.textContent = "Open PDF";
                        btn.disabled = false;

                        btn.onclick = () => {
                            window.open(`/reports/${data.pdf_filename}`, "_blank");
                        };
                    }

                    if (data.status === "error") {
                        clearInterval(interval);

                        status.textContent = "❌ Error generating PDF";
                        btn.textContent = "Try Again";
                        btn.disabled = false;
                        btn.onclick = generatePDF;
                    }

                });
        }, 2000); // poll every 2 seconds

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

def make_photo_card_html(photo_data, idx=None):
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

    # Build JSON-safe tag list and geo strings for lightbox
    import json
    tags_json = json.dumps(all_tags)
    geo_label = f"{latitude:.4f}, {longitude:.4f}" if (latitude and longitude) else ""
    geo_url   = f"https://www.google.com/maps/search/?api=1&query={latitude},{longitude}" if (latitude and longitude) else ""

    html  = f'<div class="photo-card">'
    #html += f'<img src="{url}" loading="lazy" style="{img_style}" onclick="openLightbox({json.dumps(url)},{tags_json},{json.dumps(timestamp_str)},{json.dumps(geo_label)},{json.dumps(geo_url)})">'
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


# ============================
# HTML GENERATORS (ALL MODES)
# ============================
def generate_html_unit_phase(structure):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    title = PROJECT_NAME or PROJECT_ID
    total_units = len(structure)
    total_photos = sum(len(ph) for u in structure.values() for ph in u.values())

    html = f"""<!DOCTYPE html><html><head>
    <title>{title} — Report</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>{make_shared_css()}{LIGHTBOX_CSS}</style>
    </head><body>
    {LIGHTBOX_HTML}
    <div class="container">
        <div class="report-header">
            <h1>{title}</h1>
            <div class="meta">Generated {now}</div>
            {PDF_BUTTON_HTML}
        </div>
        <div class="summary">
            <div class="summary-item"><span class="number">{total_units}</span><div class="label">Units</div></div>
            <div class="summary-item"><span class="number">{total_photos}</span><div class="label">Photos</div></div>
        </div>
        <div class="content">
    """

    for unit in sorted(structure, key=lambda u: (u == "UNASSIGNED", u)):
        html += f'<div class="unit-section"><div class="unit-header">🏠 Unit {unit}</div><div class="unit-phases" style="padding:20px;">'
        for phase in PHASE_ORDER:
            photos = structure[unit].get(phase, [])
            if phase == "UNTAGGED" and not photos:
                continue
            badge = "before" if phase == "BEFORE" else ("after" if phase == "AFTER" else "untagged")
            label = phase if phase != "UNTAGGED" else "Untagged"
            html += f'<div class="phase-section"><div class="phase-header"><h3 class="phase-title"><span class="phase-badge {badge}">{label}</span></h3><span class="phase-count">{len(photos)} photos</span></div>'
            if photos:
                html += '<div class="photo-grid">' + ''.join(make_photo_card_html(p) for p in photos) + '</div>'
            else:
                html += '<div class="no-photos">No photos</div>'
            html += '</div>'
        html += '</div></div>'

    html += f'</div></div>{LIGHTBOX_JS}{PDF_PROGRESS_JS}</body></html>'
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)


def generate_html_bldg_unit_phase(structure):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    title = PROJECT_NAME or PROJECT_ID
    total_buildings = len(structure)
    total_units = sum(len(units) for units in structure.values())
    total_photos = sum(len(photos) for units in structure.values()
                       for phases in units.values() for photos in phases.values())

    html = f"""<!DOCTYPE html><html><head>
    <title>{title} — Report</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>{make_shared_css()}{LIGHTBOX_CSS}</style>
    </head><body>
    {LIGHTBOX_HTML}
    <div class="container">
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
        <div class="content">
    """

    for bldg in sorted(structure):
        html += f'<div class="building-section"><h2 class="building-title">🏢 Building {bldg}</h2>'
        for unit in sorted(structure[bldg], key=lambda u: (u == "UNASSIGNED", u)):
            html += f'<div class="unit-section"><div class="unit-header">🏠 Unit {unit}</div><div class="unit-phases" style="padding:20px;">'
            for phase in PHASE_ORDER:
                photos = structure[bldg][unit].get(phase, [])
                if phase == "UNTAGGED" and not photos:
                    continue
                badge = "before" if phase == "BEFORE" else ("after" if phase == "AFTER" else "untagged")
                label = phase if phase != "UNTAGGED" else "Untagged"
                html += f'<div class="phase-section"><div class="phase-header"><h3 class="phase-title"><span class="phase-badge {badge}">{label}</span></h3><span class="phase-count">{len(photos)} photos</span></div>'
                if photos:
                    html += '<div class="photo-grid">' + ''.join(make_photo_card_html(p) for p in photos) + '</div>'
                else:
                    html += '<div class="no-photos">No photos</div>'
                html += '</div>'
            html += '</div></div>'
        html += '</div>'

    html += f'</div></div>{LIGHTBOX_JS}{PDF_PROGRESS_JS}</body></html>'
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)


def generate_html_unit_bath_phase(structure):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    title = PROJECT_NAME or PROJECT_ID
    total_units = len(structure)
    total_photos = sum(len(photos) for units in structure.values()
                       for baths in units.values() for photos in baths.values())

    html = f"""<!DOCTYPE html><html><head>
    <title>{title} — Report</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>{make_shared_css()}{LIGHTBOX_CSS}</style>
    </head><body>
    {LIGHTBOX_HTML}
    <div class="container">
        <div class="report-header">
            <h1>{title}</h1>
            <div class="meta">Generated {now}</div>
            {PDF_BUTTON_HTML}
        </div>
        <div class="summary">
            <div class="summary-item"><span class="number">{total_units}</span><div class="label">Units</div></div>
            <div class="summary-item"><span class="number">{total_photos}</span><div class="label">Photos</div></div>
        </div>
        <div class="content">
    """

    for unit in sorted(structure, key=lambda u: (u == "UNASSIGNED", u)):
        html += f'<div class="unit-section"><div class="unit-header">🏠 Unit {unit}</div>'
        for bath in sorted(structure[unit]):
            html += f'<div class="bathroom-group"><div class="bathroom-header">🛁 {bath}</div><div class="unit-phases">'
            for phase in PHASE_ORDER:
                photos = structure[unit][bath].get(phase, [])
                if phase == "UNTAGGED" and not photos:
                    continue
                badge = "before" if phase == "BEFORE" else ("after" if phase == "AFTER" else "untagged")
                label = phase if phase != "UNTAGGED" else "Untagged"
                html += f'<div class="phase-section"><div class="phase-header"><h3 class="phase-title"><span class="phase-badge {badge}">{label}</span></h3><span class="phase-count">{len(photos)} photos</span></div>'
                if photos:
                    html += '<div class="photo-grid">' + ''.join(make_photo_card_html(p) for p in photos) + '</div>'
                else:
                    html += '<div class="no-photos">No photos</div>'
                html += '</div>'
            html += '</div></div>'
        html += '</div>'

    html += f'</div></div>{LIGHTBOX_JS}{PDF_PROGRESS_JS}</body></html>'
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)


def generate_html_full_hierarchy(structure):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    title = PROJECT_NAME or PROJECT_ID
    total_buildings = len(structure)
    total_units = sum(len(units) for units in structure.values())
    total_photos = sum(len(photos) for units in structure.values()
                       for units_val in units.values()
                       for baths in units_val.values()
                       for photos in baths.values())

    html = f"""<!DOCTYPE html><html><head>
    <title>{title} — Report</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>{make_shared_css()}{LIGHTBOX_CSS}</style>
    </head><body>
    {LIGHTBOX_HTML}
    <div class="container">
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
        <div class="content">
    """

    for bldg in sorted(structure):
        html += f'<div class="building-section"><h2 class="building-title">🏢 Building {bldg}</h2>'
        for unit in sorted(structure[bldg], key=lambda u: (u == "UNASSIGNED", u)):
            html += f'<div class="unit-section"><div class="unit-header">🏠 Unit {unit}</div>'
            for bath in sorted(structure[bldg][unit]):
                html += f'<div class="bathroom-group"><div class="bathroom-header">🛁 {bath}</div><div class="unit-phases">'
                for phase in PHASE_ORDER:
                    photos = structure[bldg][unit][bath].get(phase, [])
                    if phase == "UNTAGGED" and not photos:
                        continue
                    badge = "before" if phase == "BEFORE" else ("after" if phase == "AFTER" else "untagged")
                    label = phase if phase != "UNTAGGED" else "Untagged"
                    html += f'<div class="phase-section"><div class="phase-header"><h3 class="phase-title"><span class="phase-badge {badge}">{label}</span></h3><span class="phase-count">{len(photos)} photos</span></div>'
                    if photos:
                        html += '<div class="photo-grid">' + ''.join(make_photo_card_html(p) for p in photos) + '</div>'
                    else:
                        html += '<div class="no-photos">No photos</div>'
                    html += '</div>'
                html += '</div></div>'
            html += '</div>'
        html += '</div>'

    html += f'</div></div>{LIGHTBOX_JS}{PDF_PROGRESS_JS}</body></html>'
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
def build_pdf_context(structure, photos):
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
    }

    print("\n========= REPORT METRICS =========")
    print(f"Mode: {SORT_METHOD_KEY}")
    print(f"Buildings: {total_buildings}")
    print(f"Units: {total_units}")
    print(f"Bathrooms: {total_bathrooms}")
    print(f"Photos: {total_photos}")
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

    structured = organize_photos(photos, unit_bath_map)
    pdf_context = build_pdf_context(structured, photos)

    print("[*] Generating HTML...")
    function_to_generate_html = determine_html_method(SORT_METHOD_KEY)
    function_to_generate_html(structured)

    generate_pdf_report(pdf_context)


if __name__ == "__main__":
    main()