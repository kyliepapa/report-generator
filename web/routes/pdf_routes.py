"""
PDF job routes.

Relocated from app.py: '/start_pdf_job', '/job_status/<job_id>'.
job_status polls the same job_manager store report_routes.py's
start_job writes to -- one shared store, two producers.

Same dataset-selection TODO as report_routes.py.
"""

import copy
import threading
import time
import uuid

from flask import Blueprint, request, jsonify

import core.config as config
import core.job_manager as job_manager
from core.photo_fetch import fetch_photos, fetch_tags
from core.organizer import build_unit_bathroom_map, organize_photos
from core.sort_engine import get_sort_key
from core.photo_edits import apply_photo_edits
from core.dataset_router import run_sort
from reporting.pdf.report_builder import build_pdf_context, generate_pdf_report
from datasets.plumbing.config import PLUMBING
from .report_routes import _convert_photos_for_lighting, _to_list
from reporting.html.generators import _lighting_photo_dict

from datasets.lighting.config import LIGHTING

# Same literal used by reporting.pdf.report_builder.LIGHTING_SORT_KEY and
# reporting.html.generators.determine_html_method -- see datasets/base.py
# for why this is a structural contract string, not a free-form label.
LIGHTING_SORT_KEY = "location_sublocation_type_fixture_phase"

pdf_bp = Blueprint("pdf_routes", __name__)


@pdf_bp.route('/start_pdf_job', methods=['POST'])
def start_pdf_job():
    if not job_manager.work_lock.acquire(blocking=False):
        return jsonify({"error": "busy"}), 429

    data          = request.json
    job_id        = str(uuid.uuid4())
    project_id    = data.get('project_id')
    package_id    = data.get('package_id')
    cache_key     = package_id or project_id
    project_name  = data.get('project_name') or cache_key
    dataset_key   = str(data.get('dataset_key') or data.get('dataset') or 'plumbing').lower()

    # Plumbing-only inputs -- absent (None) on a Lighting job, so these
    # must not be touched (e.g. .split(',')) until we're in the
    # plumbing branch below. Mirrors report_routes.py's start_job.
    multi_bath    = data.get('multi_bath')
    label_format  = data.get('label_format')
    bath_names    = _to_list(data.get('bath_names'))
    special_rooms = _to_list(data.get('special_rooms'))
    photo_edits   = data.get('photo_edits') or {}
    heading_edits = data.get('heading_edits') or {}

    # Multi-measure selection from the PDF dashboard tabs.
    # measures_included: list of measure IDs to include (None = single-measure/legacy path).
    measures_included  = data.get('measures_included')   # list[str] | None

    # ── New PDF customization options from the dashboard ──────────────────────
    pdf_options = {
        "layout":            data.get("pdf_layout", "grid"),          # "grid" | "linear"
        "hide_empty_fields": data.get("hide_empty_fields", False),    # bool
        "hidden_photos":     data.get("hidden_photos", []),           # list of URLs
        "cover_fields":      data.get("cover_fields", []),            # list of {key, label, value, visible} from the dashboard
        "measure_options":   data.get("measure_options", {}),        # { measure_id: { show_tags: bool } }
        "show_photo_tags":   data.get("show_photo_tags", True),      # single-measure fallback
    }

    with job_manager.jobs_lock:
        job_manager.jobs[job_id] = job_manager.new_job()

    def run():
        try:
            job_manager.log(job_id, "📄 Starting PDF generation...")

            # ── MULTI-MEASURE PATH ─────────────────────────────────────────────
            # When the dashboard sent a measures_included list, iterate each
            # requested measure using the correct (project_id, measure_id) cache
            # key -- NOT the bare dataset_key string.
            if measures_included is not None:
                from datetime import datetime as _dt
                config.PROJECT_ID = cache_key
                config.PROJECT_NAME = project_name
                cached_entries = job_manager.get_all_sorted_structures(cache_key)
                cache_by_id = {e["measure_id"]: e for e in cached_entries}

                measures_for_pdf = []
                all_photos_combined = []

                for measure_id in measures_included:
                    mid_norm = str(measure_id).strip().lower()
                    cached = cache_by_id.get(mid_norm)
                    if not cached:
                        job_manager.log(job_id, f"⚠️ No cached structure for measure '{measure_id}' — skipping.")
                        continue

                    job_manager.log(job_id, f"⚡ Using cached structure for measure '{measure_id}'...")
                    # Deep-copy before mutating: cached["structure"] is the SAME
                    # object living in job_manager.sorted_structures. apply_photo_edits
                    # mutates in place, so editing the reference directly would
                    # permanently corrupt the shared cache entry -- every future PDF
                    # request (including a "reset") would then start from already-
                    # damaged data instead of the pristine sorted structure.
                    structured         = copy.deepcopy(cached["structure"])
                    measure_photos     = cached["photos"]
                    special_structured = copy.deepcopy(cached.get("special_rooms_structure", {}))
                    # Derive sort_mode from cache entry if available, else fall back heuristic
                    sort_mode = cached.get("sort_mode") or LIGHTING_SORT_KEY

                    if photo_edits:
                        job_manager.log(job_id, f"✏️ Applying edits for measure '{measure_id}'...")
                        apply_photo_edits(
                            structured, special_structured, photo_edits,
                            sort_mode, measure_id=mid_norm,
                            heading_edits=heading_edits,
                        )

                    all_photos_combined.extend(measure_photos)
                    measures_for_pdf.append({
                        "measure_id":              mid_norm,
                        "measure_name":            cached.get("name") or measure_id,
                        "structure":               structured,
                        "special_rooms_structure": special_structured,
                        "sort_mode":               sort_mode,
                    })

                if not measures_for_pdf:
                    job_manager.log(job_id, "❌ No measures could be loaded. PDF generation aborted.")
                    job_manager.finish(job_id, "error")
                    return

                job_manager.log(job_id, f"📊 Building multi-measure PDF ({len(measures_for_pdf)} measure(s))...")

                hidden_set = set(pdf_options.get("hidden_photos", []))
                def _photo_url_mm(p):
                    if isinstance(p, dict) and p.get("url"):
                        return p["url"]
                    return _lighting_photo_dict(p).get("url", "")
                visible_count = sum(
                    1 for p in all_photos_combined
                    if _photo_url_mm(p) and _photo_url_mm(p) not in hidden_set
                )
                job_manager.set_progress(job_id, 0, visible_count)
                job_manager.log(job_id, f"🖼 Rendering {visible_count} photos into PDF...")

                context = {
                    "project_id":               cache_key,
                    "project_name":             project_name,
                    "project_name_upper":        (project_name or cache_key or "").upper(),
                    "address":                  "Project Address",
                    "date_generated":           _dt.now().strftime("%B %d, %Y"),
                    "total_photos":             visible_count,
                    "total_buildings":          0,
                    "total_units":              0,
                    "total_bathrooms":          0,
                    "sort_mode":                "multi",   # sentinel consumed by generate_pdf_report
                    "structured":               {},
                    "special_rooms_structured": {},
                    "measures":                 measures_for_pdf,
                }

                def on_progress_mm(done, total_p):
                    job_manager.set_progress(job_id, done, total_p)

                filename = generate_pdf_report(context, pdf_options=pdf_options,
                                               progress_callback=on_progress_mm)
                job_manager.log(job_id, "✅ PDF ready!")
                job_manager.finish(job_id, "complete", pdf_filename=filename)
                return

            # ── SINGLE-MEASURE / LEGACY PATH ──────────────────────────────────
            job_manager.log(job_id, f"🧩 Organizing photos ({dataset_key})...")

            if dataset_key == "lighting":
                config.set_dataset(LIGHTING) # This line is part of an experimental refactor
                config.PROJECT_ID = cache_key
                config.PROJECT_NAME = project_name
                config.SORT_METHOD_KEY = LIGHTING_SORT_KEY

                # Fix: cache key is (project_id, measure_id), not dataset_key.
                # For legacy single-measure lighting jobs, scan all cached entries
                # for this project rather than looking up the wrong bare key.
                cached = None
                for entry in job_manager.get_all_sorted_structures(cache_key):
                    cached = entry
                    break
                if cached:
                    job_manager.log(job_id, "⚡ Using pre-sorted photo structure for Lighting (skipping fetch/tag/sort)...")
                    # Deep-copy before mutating -- see multi-measure branch above for why:
                    # cached["structure"] is the same object stored in
                    # job_manager.sorted_structures, and apply_photo_edits mutates in place.
                    structured = copy.deepcopy(cached["structure"])
                    photos = cached["photos"]
                    special_rooms_structured = copy.deepcopy(cached.get("special_rooms_structure", {}))

                    if photo_edits:
                        job_manager.log(job_id, f"✏️ Applying {len(photo_edits)} zone edit(s) from report...")
                        apply_photo_edits(structured, special_rooms_structured, photo_edits, config.SORT_METHOD_KEY, heading_edits=heading_edits)
                else:
                    job_manager.log(job_id, "📥 Pre-sorted structure not in memory; fetching photos...")
                    photos = fetch_photos(project_id)
                    total = len(photos)
                    job_manager.log(job_id, f"✅ {total} photos fetched")

                    job_manager.log(job_id, f"🏷 Tagging {total} photos...")
                    for i, photo in enumerate(photos):
                        try:
                            photo["tag_names"] = fetch_tags(photo["id"])
                        except Exception:
                            photo["tag_names"] = []
                        if (i + 1) % 10 == 0 or (i + 1) == total:
                            job_manager.log(job_id, f"🏷 Tagging: {i+1}/{total}")
                        time.sleep(0.05)

                    lighting_photos = _convert_photos_for_lighting(photos)
                    dataset_kwargs = {
                        "installers": _to_list(data.get("installers")),
                        "locations": _to_list(data.get("locations")),
                        "sublocations": _to_list(data.get("sublocations")),
                        "fixture_types": _to_list(data.get("fixture_types")),
                        "phases": _to_list(data.get("phases")),
                        "serial_tag": str(data.get("serial_tag", "")),
                        "loc_numeric": bool(data.get("loc_numeric", False)),
                        "subloc_numeric": bool(data.get("subloc_numeric", False)),
                        "loc_bigger_num": bool(data.get("loc_bigger_num", False)),
                    }
                    sort_output = run_sort("lighting", lighting_photos, **dataset_kwargs)
                    structured = sort_output.structure
                    special_rooms_structured = {}  # Lighting has no special-rooms support yet

                    if photo_edits:
                        job_manager.log(job_id, f"✏️ Applying {len(photo_edits)} zone edit(s) from report...")
                        apply_photo_edits(structured, special_rooms_structured, photo_edits, config.SORT_METHOD_KEY, heading_edits=heading_edits)

            else:
                config.set_dataset(PLUMBING)
                config.set_inputs(cache_key, multi_bath, label_format, bath_names, project_name, special_rooms)
                config.configure_sorting()
                config.configure_sub_units()
                config.configure_special_rooms()

                job_manager.log(job_id, "📥 Fetching photos...")
                photos = fetch_photos(project_id)
                total = len(photos)
                job_manager.log(job_id, f"✅ {total} photos fetched")

                job_manager.log(job_id, f"🏷 Tagging {total} photos...")
                for i, photo in enumerate(photos):
                    try:
                        photo["tag_names"] = fetch_tags(photo["id"])
                    except Exception:
                        photo["tag_names"] = []
                    if (i + 1) % 10 == 0 or (i + 1) == total:
                        job_manager.log(job_id, f"🏷 Tagging: {i+1}/{total}")
                    time.sleep(0.05)

                unit_bath_map = build_unit_bathroom_map(photos)
                photos.sort(key=lambda p: get_sort_key(p, unit_bath_map))
                structured, special_rooms_structured = organize_photos(photos, unit_bath_map)

                if photo_edits:
                    job_manager.log(job_id, f"✏️ Applying {len(photo_edits)} zone edit(s) from report...")
                    apply_photo_edits(structured, special_rooms_structured, photo_edits, config.SORT_METHOD_KEY, heading_edits=heading_edits)

            # Count visible (non-hidden) photos so we can initialize the progress bar
            hidden_set = set(pdf_options.get("hidden_photos", []))
            def _photo_url(p):
                if isinstance(p, dict) and p.get("url"):
                    return p["url"]
                return _lighting_photo_dict(p).get("url", "")

            visible_count = sum(
                1 for p in photos
                if _photo_url(p) and _photo_url(p) not in hidden_set
            )
            job_manager.set_progress(job_id, 0, visible_count)
            job_manager.log(job_id, f"🖼 Rendering {visible_count} photos into PDF...")

            layout_label = "Linear" if pdf_options.get("layout") == "linear" else "Grid"
            job_manager.log(job_id, f"📐 Layout: {layout_label}")
            if pdf_options.get("hide_empty_fields"):
                job_manager.log(job_id, "🔲 Hide empty fields: ON")
            if hidden_set:
                job_manager.log(job_id, f"🙈 Hiding {len(hidden_set)} photo(s) per your selection")

            cover_fields = pdf_options.get("cover_fields", [])
            if cover_fields:
                hidden_fields = [f["label"] for f in cover_fields if not f.get("visible", True)]
                if hidden_fields:
                    job_manager.log(job_id, f"📋 Cover fields hidden: {', '.join(hidden_fields)}")
                edited_fields = [f["label"] for f in cover_fields
                                 if f.get("visible", True) and f.get("value", "").strip()]
                if edited_fields:
                    job_manager.log(job_id, f"📋 Cover fields edited: {', '.join(edited_fields)}")

            job_manager.log(job_id, "🏗 Building PDF...")
            context = build_pdf_context(structured, photos, special_rooms_structured)
            context["structured"] = structured
            context["special_rooms_structured"] = special_rooms_structured

            # Progress callback updates the job progress fields
            def on_progress(done, total_p):
                job_manager.set_progress(job_id, done, total_p)

            filename = generate_pdf_report(context, pdf_options=pdf_options,
                                           progress_callback=on_progress)

            job_manager.log(job_id, "✅ PDF ready!")
            job_manager.finish(job_id, "complete", pdf_filename=filename)

        except Exception as e:
            import traceback
            job_manager.log(job_id, f"❌ ERROR: {e}")
            job_manager.log(job_id, traceback.format_exc())
            job_manager.finish(job_id, "error")

        finally:
            job_manager.work_lock.release()

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"job_id": job_id})


@pdf_bp.route('/job_status/<job_id>')
def job_status(job_id):
    job = job_manager.get_job(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify({
        "status":         job["status"],
        "log":            job["log"],
        "pdf_filename":   job.get("pdf_filename"),
        "progress_done":  job.get("progress_done",  0),
        "progress_total": job.get("progress_total", 0),
    })