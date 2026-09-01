"""
PDF job routes.

Relocated from app.py: '/start_pdf_job', '/job_status/<job_id>'.
job_status polls the same job_manager store report_routes.py's
start_job writes to -- one shared store, two producers.

Same dataset-selection TODO as report_routes.py.
"""

import copy
import gc
import threading
import time
import uuid

from flask import Blueprint, request, jsonify

import core.config as config
import core.job_manager as job_manager
import core.analytics as analytics
from reporting.pdf.heading_catalog import count_heading_label_overrides
from core.photo_fetch import fetch_photos, fetch_tags
from core.organizer import build_unit_bathroom_map, organize_photos
from core.sort_engine import get_sort_key
from core.photo_edits import apply_photo_edits, apply_photo_tag_edits
from core.dataset_router import run_sort
from reporting.pdf.report_builder import build_pdf_context, generate_pdf_report, _collect_visible_photos
from datasets.plumbing.config import PLUMBING
from .report_routes import _convert_photos_for_lighting, _to_list

from datasets.lighting.config import LIGHTING, parse_location_levels

# Same literal used by reporting.pdf.report_builder.LIGHTING_SORT_KEY and
# reporting.html.generators.determine_html_method -- see datasets/base.py
# for why this is a structural contract string, not a free-form label.
LIGHTING_SORT_KEY = "location_sublocation_type_fixture_phase"

pdf_bp = Blueprint("pdf_routes", __name__)


def _resolve_pdf_project_name(raw_name, cover_fields):
    """Match cover_page.py: visible project_name cover field overrides PDF display name."""
    for f in cover_fields or []:
        if not isinstance(f, dict):
            continue
        if f.get("key") == "project_name" and f.get("visible", True):
            v = (f.get("value") or "").strip()
            if v:
                return v
    return raw_name or ""


def _project_names_differ(original, resolved):
    return (original or "").strip().casefold() != (resolved or "").strip().casefold()


@pdf_bp.route('/start_pdf_job', methods=['POST'])
def start_pdf_job():
    if not job_manager.work_lock.acquire(blocking=False):
        return jsonify({"error": "busy"}), 429

    data          = request.json
    job_id        = str(uuid.uuid4())
    project_id    = data.get('project_id')
    package_id    = data.get('package_id')
    cache_key     = package_id or project_id
    original_project_name = data.get('project_name') or cache_key
    project_address = (
        str(data.get('project_address') or '').strip()
        or job_manager.get_project_address(cache_key)
    )
    if data.get('project_address'):
        job_manager.save_project_metadata(cache_key, address=project_address)
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
    photo_transforms = data.get('photo_transforms') or {}
    photo_tag_edits  = data.get('photo_tag_edits') or {}

    # Multi-measure selection from the PDF dashboard tabs.
    # measures_included: list of measure IDs to include (None = single-measure/legacy path).
    measures_included  = data.get('measures_included')   # list[str] | None

    # ── New PDF customization options from the dashboard ──────────────────────
    _linear_per_page = int(data.get("linear_photos_per_page") or 4)
    if _linear_per_page not in (2, 3, 4):
        _linear_per_page = 4

    _meta_pos = str(data.get("metadata_position") or "outside").lower()
    if _meta_pos not in ("left", "outside", "inside", "right"):
        _meta_pos = "outside"

    pdf_options = {
        "layout":                 data.get("pdf_layout", "grid"),          # "grid" | "linear"
        "hide_empty_fields":      data.get("hide_empty_fields", False),    # bool
        "hidden_photos":          data.get("hidden_photos", []),           # list of URLs
        "cover_fields":           data.get("cover_fields", []),            # list of {key, label, value, visible} from the dashboard
        "measure_options":        data.get("measure_options", {}),        # { measure_id: { show_tags, heading_size } }
        "show_photo_tags":        data.get("show_photo_tags", True),      # single-measure fallback
        "metadata_position":      _meta_pos,
        "linear_photos_per_page": _linear_per_page,
        "photo_transforms":       photo_transforms,
        "photo_tag_edits":          photo_tag_edits,
    }

    resolved_project_name = _resolve_pdf_project_name(
        original_project_name, pdf_options.get("cover_fields")
    )
    project_name_edited = _project_names_differ(original_project_name, resolved_project_name)
    project_name = resolved_project_name

    analytics_payload = data.get("analytics") or {}
    parent_run_id = analytics_payload.get("parent_run_id") or data.get("parent_run_id")
    display_name = str(analytics_payload.get("display_name") or "").strip() or "Anonymous"
    user_id = analytics_payload.get("user_id") or analytics.slugify_user_id(display_name)
    session_id = str(analytics_payload.get("session_id") or uuid.uuid4())
    ux = analytics_payload.get("ux") or {}
    user_agent = request.headers.get("User-Agent", "")

    edits_block = analytics_payload.get("edits") or {}
    if not edits_block:
        photo_transforms_count = len(photo_transforms) if photo_transforms else 0
        photo_tag_count = len(photo_tag_edits) if photo_tag_edits else 0
        heading_count = len(heading_edits) if heading_edits else 0
        zone_edit_count = len(photo_edits) if photo_edits else 0
        edits_block = analytics.empty_edits()
        edits_block.update({
            "photo_moves_count": zone_edit_count,
            "heading_edits_count": heading_count,
            "photo_tag_edits_count": photo_tag_count,
            "photo_transforms_count": photo_transforms_count,
        })
    else:
        merged_edits = analytics.empty_edits()
        merged_edits.update(edits_block)
        edits_block = merged_edits

    if not int(edits_block.get("heading_label_edits_count") or 0):
        edits_block["heading_label_edits_count"] = count_heading_label_overrides(
            pdf_options.get("measure_options")
        )
    edits_block["cover_project_name_edited"] = project_name_edited

    pdf_run_id = str(uuid.uuid4())
    project_block = {
        "is_multi_project": bool(package_id),
        "project_id": project_id,
        "package_id": package_id,
        "project_name": original_project_name if not package_id else None,
        "project_address": project_address,
        "package_name": original_project_name if package_id else None,
        "projects": [],
    }
    pdf_block = {
        "opened": True,
        "generated": False,
        "layout": pdf_options.get("layout"),
        "hide_empty_fields": pdf_options.get("hide_empty_fields"),
        "metadata_position": pdf_options.get("metadata_position"),
        "linear_photos_per_page": pdf_options.get("linear_photos_per_page"),
        "hidden_photo_count": len(pdf_options.get("hidden_photos") or []),
        "measures_included": measures_included,
        "measure_inclusions": data.get("measure_inclusions") or {},
        "measure_options": pdf_options.get("measure_options") or {},
        "cover_fields": pdf_options.get("cover_fields") or [],
        "project_name": resolved_project_name,
        "project_name_edited": project_name_edited,
        "duration_ms": None,
        "timing_ms": {},
    }
    pdf_analytics_record = analytics.new_pdf_run(
        run_id=pdf_run_id,
        parent_run_id=parent_run_id or "",
        user_id=user_id,
        display_name=display_name,
        session_id=session_id,
        project_block=project_block,
        pdf_block=pdf_block,
        edits=edits_block,
        ux=ux,
        user_agent=user_agent,
    )

    with job_manager.jobs_lock:
        job_manager.jobs[job_id] = job_manager.new_job()
        job_manager.jobs[job_id]["analytics_run_id"] = pdf_run_id

    def run():
        ts_start = time.time()
        status = "error"
        error_type = None
        error_message = None

        def _save_pdf_analytics():
            analytics.finalize_pdf_run(
                pdf_analytics_record,
                status=status,
                ts_start=ts_start,
                timing_ms={"total": int((time.time() - ts_start) * 1000)},
                error_type=error_type,
                error_message=error_message,
            )
            analytics.save_run(pdf_analytics_record)
            if parent_run_id:
                try:
                    analytics.patch_report_edits(parent_run_id, edits_block)
                except Exception:
                    pass

        try:
            job_manager.log(job_id, "📄 Starting PDF generation...")

            # ── MULTI-MEASURE PATH ─────────────────────────────────────────────
            # When the dashboard sent a measures_included list, iterate each
            # requested measure using the correct (project_id, measure_id) cache
            # key -- NOT the bare dataset_key string.
            if measures_included is not None:
                from core.timezone import now_formatted
                config.PROJECT_ID = cache_key
                config.PROJECT_NAME = project_name
                cached_entries = job_manager.get_all_sorted_structures(cache_key)
                cache_by_id = {e["measure_id"]: e for e in cached_entries}

                measures_for_pdf = []

                for measure_id in measures_included:
                    mid_norm = str(measure_id).strip().lower()
                    cached = cache_by_id.get(mid_norm)
                    if not cached:
                        job_manager.log(job_id, f"⚠️ No cached structure for measure '{measure_id}' — skipping.")
                        continue

                    job_manager.log(job_id, f"⚡ Using cached structure for measure '{measure_id}'...")
                    has_edits = bool(photo_edits) or bool(photo_tag_edits) or bool(heading_edits)
                    if has_edits:
                        # Deep-copy before mutating so disk cache stays pristine for reset/re-export.
                        structured = copy.deepcopy(cached["structure"])
                        special_structured = copy.deepcopy(cached.get("special_rooms_structure", {}))
                    else:
                        structured = cached["structure"]
                        special_structured = cached.get("special_rooms_structure", {})
                    # Derive sort_mode from cache entry if available, else fall back heuristic
                    sort_mode = cached.get("sort_mode") or LIGHTING_SORT_KEY

                    if photo_edits:
                        job_manager.log(job_id, f"✏️ Applying edits for measure '{measure_id}'...")
                        apply_photo_edits(
                            structured, special_structured, photo_edits,
                            sort_mode, measure_id=mid_norm,
                            heading_edits=heading_edits,
                        )
                    if photo_tag_edits:
                        apply_photo_tag_edits(structured, special_structured, photo_tag_edits)

                    measures_for_pdf.append({
                        "measure_id":              mid_norm,
                        "measure_name":            cached.get("name") or measure_id,
                        "structure":               structured,
                        "special_rooms_structure": special_structured,
                        "sort_mode":               sort_mode,
                    })

                if not measures_for_pdf:
                    job_manager.log(job_id, "❌ No measures could be loaded. PDF generation aborted.")
                    error_type = "NoMeasuresLoaded"
                    error_message = "No measures could be loaded from cache."
                    job_manager.finish(job_id, "error")
                    return

                job_manager.log(job_id, f"📊 Building multi-measure PDF ({len(measures_for_pdf)} measure(s))...")

                hidden_set = set(pdf_options.get("hidden_photos", []))
                visible_count = sum(
                    len(_collect_visible_photos(
                        m["structure"],
                        m["sort_mode"],
                        m["special_rooms_structure"],
                        hidden_set,
                    ))
                    for m in measures_for_pdf
                )
                job_manager.set_progress(job_id, 0, visible_count)
                job_manager.log(job_id, f"🖼 Rendering {visible_count} photos into PDF...")

                context = {
                    "project_id":               cache_key,
                    "project_name":             project_name,
                    "project_name_upper":        (project_name or cache_key or "").upper(),
                    "address":                  project_address,
                    "date_generated":           now_formatted("%B %d, %Y"),
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
                status = "complete"
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
                    has_edits = bool(photo_edits) or bool(photo_tag_edits) or bool(heading_edits)
                    if has_edits:
                        structured = copy.deepcopy(cached["structure"])
                        special_rooms_structured = copy.deepcopy(cached.get("special_rooms_structure", {}))
                    else:
                        structured = cached["structure"]
                        special_rooms_structured = cached.get("special_rooms_structure", {})
                    sort_mode_cached = cached.get("sort_mode") or LIGHTING_SORT_KEY

                    if photo_edits:
                        job_manager.log(job_id, f"✏️ Applying {len(photo_edits)} zone edit(s) from report...")
                        apply_photo_edits(structured, special_rooms_structured, photo_edits, config.SORT_METHOD_KEY, heading_edits=heading_edits)
                    if photo_tag_edits:
                        apply_photo_tag_edits(structured, special_rooms_structured, photo_tag_edits)

                    photos = _collect_visible_photos(
                        structured, sort_mode_cached, special_rooms_structured, set(),
                    )
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
                        "location_levels": parse_location_levels(data),
                        "fixture_types": _to_list(data.get("fixture_types")),
                        "phases": _to_list(data.get("phases")),
                        "serial_tag": str(data.get("serial_tag", "")),
                        "loc_bigger_num": bool(data.get("loc_bigger_num", False)),
                    }
                    sort_output = run_sort("lighting", lighting_photos, **dataset_kwargs)
                    structured = sort_output.structure
                    special_rooms_structured = {}  # Lighting has no special-rooms support yet

                    if photo_edits:
                        job_manager.log(job_id, f"✏️ Applying {len(photo_edits)} zone edit(s) from report...")
                        apply_photo_edits(structured, special_rooms_structured, photo_edits, config.SORT_METHOD_KEY, heading_edits=heading_edits)
                    if photo_tag_edits:
                        apply_photo_tag_edits(structured, special_rooms_structured, photo_tag_edits)

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
                if photo_tag_edits:
                    apply_photo_tag_edits(structured, special_rooms_structured, photo_tag_edits)

            # Count visible (non-hidden) photos so we can initialize the progress bar
            hidden_set = set(pdf_options.get("hidden_photos", []))
            visible_count = len(_collect_visible_photos(
                structured, config.SORT_METHOD_KEY, special_rooms_structured, hidden_set,
            ))
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
            status = "complete"
            job_manager.finish(job_id, "complete", pdf_filename=filename)

        except Exception as e:
            import traceback
            job_manager.log(job_id, f"❌ ERROR: {e}")
            job_manager.log(job_id, traceback.format_exc())
            error_type = type(e).__name__
            error_message = str(e)
            job_manager.finish(job_id, "error")

        finally:
            try:
                _save_pdf_analytics()
            except Exception:
                pass
            job_manager.evict_project(cache_key)
            gc.collect()
            job_manager.work_lock.release()

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"job_id": job_id, "run_id": pdf_run_id})


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