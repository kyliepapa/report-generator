# This is app.py

from flask import Flask, render_template, request, send_from_directory, Response, jsonify
import os
import time
import threading
import uuid

from newreport import (
    fetch_photos,
    fetch_tags,
    build_unit_bathroom_map,
    organize_photos,
    build_pdf_context,
    get_sort_key,
    set_inputs,
    configure_sorting,
    configure_bathrooms,
    configure_special_rooms,
    analyze_missing_photos,
    determine_html_method,
)
from pdf_generator import generate_pdf_report

app = Flask(__name__)

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR  = os.path.join(BASE_DIR, 'static')
REPORTS_DIR = os.path.join(STATIC_DIR, 'reports')
os.makedirs(REPORTS_DIR, exist_ok=True)

# ─────────────────────────────────────────
# In-memory job store
# { job_id: { status, log, pdf_filename } }
# ─────────────────────────────────────────
jobs = {}
jobs_lock = threading.Lock()
work_lock = threading.Lock()


def _new_job():
    return {"status": "running", "log": [], "pdf_filename": None}


def _log(job_id, msg):
    with jobs_lock:
        jobs[job_id]["log"].append(msg)


def _finish(job_id, status, pdf_filename=None):
    with jobs_lock:
        jobs[job_id]["status"] = status
        if pdf_filename:
            jobs[job_id]["pdf_filename"] = pdf_filename


# ─────────────────────────────────────────
# DRAG-AND-DROP EDIT APPLICATOR
#
# photo_edits is a dict: { zone_id: [ordered_photo_urls] }
# We walk the structured data and reorder (and optionally re-assign)
# photo_data entries to match the order the user arranged in the browser.
#
# Strategy:
#   1. Build a flat map: url → photo_data  (from the original structure)
#   2. For each zone that has edits, replace its photo list with the
#      url-ordered version from photo_edits.
#   3. Photos whose url appears in a *different* zone than originally
#      are effectively moved there — the original zone loses them.
# ─────────────────────────────────────────
def apply_photo_edits(structured, special_rooms_structured, photo_edits, sort_mode):
    """
    Mutates `structured` and `special_rooms_structured` in-place to reflect
    the drag-and-drop order supplied in `photo_edits`.

    photo_edits: { "zone__id__string": ["url1", "url2", ...], ... }
    """
    if not photo_edits:
        return

    # ── 1. Collect all photo_data objects keyed by URL ────────────────────────
    url_to_photo = {}

    def _collect(phases_dict):
        for phase_list in phases_dict.values():
            for pd in phase_list:
                url_to_photo[pd["url"]] = pd

    if sort_mode == "full":
        for bldg in structured:
            for unit in structured[bldg]:
                for bath in structured[bldg][unit]:
                    _collect(structured[bldg][unit][bath])
    elif sort_mode == "bldg_unit_phase":
        for bldg in structured:
            for unit in structured[bldg]:
                _collect(structured[bldg][unit])
    elif sort_mode == "unit_bath_phase":
        for unit in structured:
            for bath in structured[unit]:
                _collect(structured[unit][bath])
    else:
        for unit in structured:
            _collect(structured[unit])

    for room in special_rooms_structured:
        _collect(special_rooms_structured[room])

    # ── 2. Parse zone IDs and apply the new order ─────────────────────────────
    # Zone IDs are built by _zone_id() in newreport.py:
    #   unit_phase:       "unit__<unit>__<PHASE>"
    #   bldg_unit_phase:  "bldg__<bldg>__unit__<unit>__<PHASE>"
    #   unit_bath_phase:  "unit__<unit>__bath__<bath>__<PHASE>"
    #   full:             "bldg__<bldg>__unit__<unit>__bath__<bath>__<PHASE>"
    #   special:          "special__<room>__<PHASE>"

    for zone_id, ordered_urls in photo_edits.items():
        parts = zone_id.split("__")

        # Resolve the phases_dict for this zone
        phases_dict = None

        if parts[0] == "special":
            # "special__<room>__<PHASE>"
            room = parts[1].replace("_", " ").title()
            # fuzzy match room name (case-insensitive)
            matched_room = next(
                (r for r in special_rooms_structured if r.lower() == room.lower()),
                None
            )
            if matched_room:
                phases_dict = special_rooms_structured[matched_room]
                phase = parts[2]
        elif sort_mode == "unit_phase":
            # "unit__<unit>__<PHASE>"
            unit  = parts[1]
            phase = parts[2]
            phases_dict = structured.get(unit)
        elif sort_mode == "bldg_unit_phase":
            # "bldg__<bldg>__unit__<unit>__<PHASE>"
            bldg  = parts[1]
            unit  = parts[3]
            phase = parts[4]
            phases_dict = structured.get(bldg, {}).get(unit)
        elif sort_mode == "unit_bath_phase":
            # "unit__<unit>__bath__<bath>__<PHASE>"
            unit  = parts[1]
            bath  = parts[3]
            phase = parts[4]
            phases_dict = structured.get(unit, {}).get(bath)
        elif sort_mode == "full":
            # "bldg__<bldg>__unit__<unit>__bath__<bath>__<PHASE>"
            bldg  = parts[1]
            unit  = parts[3]
            bath  = parts[5]
            phase = parts[6]
            phases_dict = structured.get(bldg, {}).get(unit, {}).get(bath)

        if phases_dict is None:
            continue

        # Replace this phase's list with the user-ordered photo_data objects
        new_list = []
        for url in ordered_urls:
            pd = url_to_photo.get(url)
            if pd:
                new_list.append(pd)

        phases_dict[phase] = new_list


# ─────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────

@app.route('/')
def home():
    return render_template('index.html')


@app.route('/report')
def open_report():
    return send_from_directory(STATIC_DIR, 'report.html')


@app.route('/reports/<filename>')
def download_report(filename):
    return send_from_directory(REPORTS_DIR, filename)


# ── Start a report job ───────────────────
@app.route('/start_job', methods=['POST'])
def start_job():
    if not work_lock.acquire(blocking=False):
        return jsonify({"error": "busy"}), 429

    data         = request.json
    job_id       = str(uuid.uuid4())
    project_id   = data.get('project_id')
    project_name = data.get('project_name') or project_id
    multi_bath   = data.get('multi_bath')
    label_format = data.get('label_format')
    bath_names   = data.get('bath_names', '').split(',')
    special_rooms = [r.strip() for r in data.get('special_rooms', '').split(',') if r.strip()]

    with jobs_lock:
        jobs[job_id] = _new_job()

    def run():
        try:
            _log(job_id, "⚙️ Configuring inputs...")
            set_inputs(project_id, multi_bath, label_format, bath_names, project_name, special_rooms)
            configure_sorting()
            configure_bathrooms()
            configure_special_rooms()

            _log(job_id, "📥 Fetching photos...")
            photos = fetch_photos()
            _log(job_id, f"✅ {len(photos)} photos fetched")

            total = len(photos)
            _log(job_id, f"🏷 Tagging {total} photos...")
            for i, photo in enumerate(photos):
                try:
                    photo["tag_names"] = fetch_tags(photo["id"])
                except Exception:
                    photo["tag_names"] = []
                    _log(job_id, f"⚠️ Could not fetch tags for photo {photo['id']}")

                if (i + 1) % 10 == 0 or (i + 1) == total:
                    _log(job_id, f"🏷 Tagging: {i+1}/{total}")

                time.sleep(0.05)

            _log(job_id, "📦 Building unit map...")
            unit_bath_map = build_unit_bathroom_map(photos)

            _log(job_id, "🔄 Sorting photos...")
            photos.sort(key=lambda p: get_sort_key(p, unit_bath_map))

            _log(job_id, "🧩 Structuring data...")
            structured, special_rooms_structured = organize_photos(photos, unit_bath_map)

            _log(job_id, "🔍 Analyzing missing photos...")
            missing = analyze_missing_photos(structured)
            missing_before = missing.get("BEFORE", [])
            missing_after  = missing.get("AFTER",  [])
            # _log(job_id, f"📊 Missing BEFORE: {len(missing_before)}")
            # _log(job_id, f"📊 Missing AFTER: {len(missing_after)}")
            # for loc in missing_before:
            #     _log(job_id, f"🔴 {loc}")
            # for loc in missing_after:
            #     _log(job_id, f"🟡 {loc}")
            _log(job_id, "📊 MISSING PHOTO SUMMARY")

            # ── BEFORE section ───────────────────────
            _log(job_id, f"🟠 Missing BEFORE photos: {len(missing_before)}")
            if missing_before:
                _log(job_id, "   ─────────────────────")
                for loc in missing_before:
                    _log(job_id, f"   • {loc}")
            else:
                _log(job_id, "   ✓ None")
            _log(job_id, "")  # blank line

            # ── AFTER section ────────────────────────
            _log(job_id, f"🟡 Missing AFTER photos: {len(missing_after)}")
            if missing_after:
                _log(job_id, "   ─────────────────────")
                for loc in missing_after:
                    _log(job_id, f"   • {loc}")
            else:
                _log(job_id, "   ✓ None")

            _log(job_id, "")  # blank line    
            if special_rooms_structured:
                _log(job_id, f"🏛 Special areas: {', '.join(special_rooms_structured.keys())}")

            _log(job_id, "🏗 Generating HTML report...")
            from newreport import SORT_METHOD_KEY as SMK
            html_func = determine_html_method(SMK)
            html_func(structured, special_rooms_structured)

            _log(job_id, "✅ HTML report ready!")
            _finish(job_id, "complete")

        except Exception as e:
            import traceback
            _log(job_id, f"❌ ERROR: {e}")
            _log(job_id, traceback.format_exc())
            _finish(job_id, "error")

        finally:
            work_lock.release()

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"job_id": job_id})


# ── Poll job status ──────────────────────
@app.route('/job_status/<job_id>')
def job_status(job_id):
    with jobs_lock:
        job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify({
        "status":       job["status"],
        "log":          job["log"],
        "pdf_filename": job.get("pdf_filename"),
    })


# ── Start a PDF job ──────────────────────
@app.route('/start_pdf_job', methods=['POST'])
def start_pdf_job():
    if not work_lock.acquire(blocking=False):
        return jsonify({"error": "busy"}), 429

    data          = request.json
    job_id        = str(uuid.uuid4())
    project_id    = data.get('project_id')
    project_name  = data.get('project_name') or project_id
    multi_bath    = data.get('multi_bath')
    label_format  = data.get('label_format')
    bath_names    = data.get('bath_names', '').split(',')
    special_rooms = [r.strip() for r in data.get('special_rooms', '').split(',') if r.strip()]
    # ← New: drag-and-drop edit map from the report page
    photo_edits   = data.get('photo_edits') or {}   # { zone_id: [url, ...] }

    with jobs_lock:
        jobs[job_id] = _new_job()

    def run():
        try:
            _log(job_id, "📄 Starting PDF generation...")
            set_inputs(project_id, multi_bath, label_format, bath_names, project_name, special_rooms)
            configure_sorting()
            configure_bathrooms()
            configure_special_rooms()

            _log(job_id, "📥 Fetching photos...")
            photos = fetch_photos()
            total = len(photos)
            _log(job_id, f"✅ {total} photos fetched")

            _log(job_id, f"🏷 Tagging {total} photos...")
            for i, photo in enumerate(photos):
                try:
                    photo["tag_names"] = fetch_tags(photo["id"])
                except Exception:
                    photo["tag_names"] = []
                if (i + 1) % 10 == 0 or (i + 1) == total:
                    _log(job_id, f"🏷 Tagging: {i+1}/{total}")
                time.sleep(0.05)

            _log(job_id, "🧩 Organizing photos...")
            unit_bath_map = build_unit_bathroom_map(photos)
            photos.sort(key=lambda p: get_sort_key(p, unit_bath_map))
            structured, special_rooms_structured = organize_photos(photos, unit_bath_map)

            # ── Apply drag-and-drop edits (if any) ──────────────────────────
            if photo_edits:
                from newreport import SORT_METHOD_KEY as SMK
                n_edits = sum(len(v) for v in photo_edits.values())
                _log(job_id, f"✏️ Applying {len(photo_edits)} zone edit(s) from report...")
                apply_photo_edits(structured, special_rooms_structured, photo_edits, SMK)
            else:
                from newreport import SORT_METHOD_KEY as SMK

            _log(job_id, "🏗 Building PDF...")
            context = build_pdf_context(structured, photos, special_rooms_structured)
            context["structured"] = structured
            context["special_rooms_structured"] = special_rooms_structured
            filename = generate_pdf_report(context)

            _log(job_id, "✅ PDF ready!")
            _finish(job_id, "complete", pdf_filename=filename)

        except Exception as e:
            import traceback
            _log(job_id, f"❌ ERROR: {e}")
            _log(job_id, traceback.format_exc())
            _finish(job_id, "error")

        finally:
            work_lock.release()

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"job_id": job_id})


if __name__ == '__main__':
    app.run(debug=True)