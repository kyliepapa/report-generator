"""
HTML report routes.

Relocated from app.py: '/' (home), '/start_job', '/report',
'/reports/<filename>'.
"""

import gc
import threading
import time
import uuid
import re
import hashlib
from collections import OrderedDict
from datetime import datetime

from core.timezone import from_timestamp, now_formatted

from flask import Blueprint, render_template, request, send_from_directory, jsonify

import core.config as config
import core.paths as paths
import core.job_manager as job_manager
import core.analytics as analytics
from core.photo_fetch import fetch_photos, fetch_tags
from core.dataset_router import run_sort
from core.measure_classification import (
    MeasureConfig,
    DuplicateMeasureKeywordError,
    SubcontractedConfigError,
    ManualArrangeConfigError,
    MultiProjectConfigError,
    run_measure_classification,
)
from reporting.html import generators
from datasets.plumbing.config import PLUMBING
from datasets.lighting.config import LIGHTING, level1_tags, parse_location_levels

# Type-specific config keys, per measure, that double as pass-2 fallback
# classification tags (used when a photo carries no measure_keyword).
# These are the vocab a person actually typed in for that measure --
# location/fixture/room names etc -- so a tag unique to one measure's
# vocab is a reasonable signal even without an explicit keyword match.
# water_meter isn't listed since it's not a supported sort target yet.
_CLASSIFICATION_TAG_FIELDS = {
    "aquamizer": ["special_rooms"],
    "lighting": ["installers", "locations", "fixture_types", "phases"],
    "heat_pump": ["fixtures"],
}

report_bp = Blueprint("report_routes", __name__)

# Strip tags
def _clean_tag_list(value):
    if value is None:
        return []

    if isinstance(value, str):
        value = [value]

    return [str(x).strip() for x in value if str(x).strip()]


def _append_usage_log(project_id, project_name):
    ts    = now_formatted('%Y-%m-%d %H:%M:%S')
    entry = f"{ts} | Project ID: {project_id} | Project Name: {project_name}\n"
    paths.append_file(paths.USAGE_LOGS_FILE, entry)


def _append_package_usage_log(package_id, package_name, complete_projects):
    ts = now_formatted('%Y-%m-%d %H:%M:%S')
    proj_str = ", ".join(
        f"{p['id']} ({p['nickname']})" for p in complete_projects
    )
    entry = f"{ts} | Package: {package_name} | package_id={package_id} | Projects: {proj_str}\n"
    paths.append_file(paths.USAGE_LOGS_FILE, entry)


def _slugify(value):
    slug = re.sub(r'[^a-z0-9]+', '_', str(value or '').strip().lower())
    return slug.strip('_') or 'package'


def derive_package_id(package_name, project_ids):
    """Synthetic cache key for multi-project runs."""
    sorted_ids = sorted(str(pid).strip() for pid in project_ids if str(pid).strip())
    digest = hashlib.md5('|'.join(sorted_ids).encode()).hexdigest()[:8]
    return f"pkg_{_slugify(package_name)}_{digest}"


def _filter_complete_projects(projects):
    complete = []
    for p in projects or []:
        pid = str(p.get('id') or '').strip()
        nick = str(p.get('nickname') or '').strip()
        if pid and nick:
            complete.append({'id': pid, 'nickname': nick})
    return complete


def _tag_photos(photos, job_id):
    total = len(photos)
    job_manager.log(job_id, f"🏷 Tagging {total} photos...")
    for i, photo in enumerate(photos):
        try:
            photo["tag_names"] = fetch_tags(photo["id"])
        except Exception:
            photo["tag_names"] = []
            job_manager.log(job_id, f"⚠️ Could not fetch tags for photo {photo['id']}")

        if (i + 1) % 10 == 0 or (i + 1) == total:
            job_manager.log(job_id, f"🏷 Tagging: {i+1}/{total}")

        time.sleep(0.05)


def _build_unknown_by_project(unknown_photos):
    """Group unknown photos by source project nickname, preserving order."""
    groups = OrderedDict()
    for photo in unknown_photos:
        nick = str(photo.get('source_project_nickname') or photo.get('source_project_id') or 'Unknown')
        groups.setdefault(nick, []).append(photo)
    return [{'nickname': nick, 'photos': photos} for nick, photos in groups.items()]


def _to_list(val):
    if isinstance(val, list):
        return [str(x).strip() for x in val if str(x).strip()]
    if isinstance(val, str):
        return [x.strip() for x in val.split(",") if x.strip()]
    return []


def _derive_classification_tags(measure_type, measure_payload):
    """
    Auto-derive pass-2 fallback tags for a measure from its own
    type-specific config fields (see _CLASSIFICATION_TAG_FIELDS),
    rather than requiring a separate frontend field. A tag only helps
    classification if it's unique to one measure -- that uniqueness
    check happens later, in find_unique_classification_tags -- so
    it's safe to just pool everything configured here.
    """
    tags = []
    for field_name in _CLASSIFICATION_TAG_FIELDS.get(measure_type, []):
        if measure_type == "lighting" and field_name == "locations":
            tags.extend(level1_tags(measure_payload))
        else:
            tags.extend(_to_list(measure_payload.get(field_name)))
    return tags


def _build_measure_configs(measures_payload):
    return [
        MeasureConfig(
            id=m.get("id"),
            type=str(m.get("type") or "").lower(),
            name=m.get("name") or str(m.get("type") or "").lower(),
            measure_keywords=_to_list(m.get("measure_keywords")),
            classification_tags=_derive_classification_tags(
                str(m.get("type") or "").lower(), m
            ),
            hash=str(m.get("hash") or "").strip(),
            measure_mark=str(m.get("measure_mark") or "").strip(),
            key_source=str(m.get("key_source") or "tags").lower(),
            applicable_projects=_to_list(m.get("applicable_projects")),
        )
        for m in measures_payload
    ]


def _configure_and_sort_measure(measure_type, measure_payload, measure_photos, job_id, project_id, project_name):
    """
    Runs the existing single-dataset configure+sort pipeline against
    just this measure's classified photo subset, and returns the
    resulting SortOutput. Mirrors the per-dataset branches that used
    to run once per job; now runs once per measure. water_meter isn't
    handled here since dataset_router.run_water_meter's kwargs aren't
    wired to a frontend payload shape yet -- same "not supported yet"
    state as before, just enforced per-measure now instead of globally.
    """
    if measure_type == "aquamizer":
        multi_bath = measure_payload.get("multi_bath")
        label_format = measure_payload.get("label_format")
        bath_names = _to_list(measure_payload.get("bath_names"))
        special_rooms = _to_list(measure_payload.get("special_rooms"))

        config.set_dataset(PLUMBING)
        config.set_inputs(project_id, multi_bath, label_format, bath_names, project_name, special_rooms)
        config.configure_sorting()
        config.configure_sub_units()
        config.configure_special_rooms()

        sort_output = run_sort("plumbing", measure_photos)

        missing_before = [i["label"] for i in sort_output.issues if i.get("phase") == "BEFORE"]
        missing_after = [i["label"] for i in sort_output.issues if i.get("phase") == "AFTER"]
        job_manager.log(job_id, "📊 MISSING PHOTO SUMMARY")
        job_manager.log(job_id, f"🟠 Missing BEFORE photos: {len(missing_before)}")
        for loc in missing_before:
            job_manager.log(job_id, f"   • {loc}")
        job_manager.log(job_id, f"🟡 Missing AFTER photos: {len(missing_after)}")
        for loc in missing_after:
            job_manager.log(job_id, f"   • {loc}")

        return sort_output

    elif measure_type == "lighting":
        lighting_photos = _convert_photos_for_lighting(measure_photos)
        config.set_dataset(LIGHTING)
        config.PROJECT_ID = project_id
        config.PROJECT_NAME = project_name
        config.SORT_METHOD_KEY = "location_sublocation_type_fixture_phase"

        dataset_kwargs = {
            "installers": _to_list(measure_payload.get("installers")),
            "location_levels": parse_location_levels(measure_payload),
            "fixture_types": _to_list(measure_payload.get("fixture_types")),
            "phases": _to_list(measure_payload.get("phases")),
            "serial_tag": str(measure_payload.get("serial_tag", "")),
            "loc_bigger_num": str(measure_payload.get("loc_bigger_num", "")).strip().lower() == "yes",
        }
        sort_output = run_sort("lighting", lighting_photos, **dataset_kwargs)

        # # Scary Terminal Logs
        # job_manager.log(job_id, "📄 Lighting sort output:")
        # job_manager.log(job_id, repr(sort_output.structure))
        # job_manager.log(job_id, "📄 Lighting issues:")
        # job_manager.log(job_id, repr(sort_output.issues))

        return sort_output

    elif measure_type == "subcontracted":
        sort_output = run_sort(
            "subcontracted",
            measure_photos,
            hash=measure_payload.get("hash"),
            measure_mark=measure_payload.get("measure_mark") or "",
            key_source=measure_payload.get("key_source") or "tags",
        )

        missing_keys = [i for i in sort_output.issues if i.get("type") == "missing_order_key"]
        if missing_keys:
            job_manager.log(job_id, f"⚠️ {len(missing_keys)} photo(s) missing order key:")
            for issue in missing_keys:
                job_manager.log(job_id, f"   • photo {issue.get('photo_id')} (tag: {issue.get('tag')})")

        # # Scary Terminal Logs
        # job_manager.log(job_id, "📄 Subcontracted sort output:")
        # job_manager.log(job_id, repr(sort_output.structure))
        # job_manager.log(job_id, "📄 Subcontracted Measure issues:")
        # job_manager.log(job_id, repr(sort_output.issues))

        return sort_output

    elif measure_type == "heat_pump":
        intuitive_fixture_sort = bool(measure_payload.get("intuitive_fixture_sort", True))
        fixtures = [] if intuitive_fixture_sort else _to_list(measure_payload.get("fixtures"))
        allow_competing = False if intuitive_fixture_sort else bool(
            measure_payload.get("allow_competing_fixture_tags")
        )
        sort_output = run_sort(
            "heat_pump",
            measure_photos,
            fixtures=fixtures,
            serial_tag=str(measure_payload.get("serial_tag", "")),
            allow_competing_fixture_tags=allow_competing,
            auto_assign_lone_serial_to_before=bool(
                measure_payload.get("auto_assign_lone_serial_to_before")
            ),
            intuitive_fixture_sort=intuitive_fixture_sort,
            multi_unit=bool(measure_payload.get("multi_unit")),
            lone_number_mode=str(measure_payload.get("lone_number_mode", "none")),
            locations=_to_list(measure_payload.get("locations")),
        )

        # # Scary Terminal Logs
        # job_manager.log(job_id, "📄 Heat pump sort output:")
        # job_manager.log(job_id, repr(sort_output.structure))
        # job_manager.log(job_id, "📄 Heat pump issues:")
        # job_manager.log(job_id, repr(sort_output.issues))

        return sort_output

    elif measure_type == "manual_arrange":
        sort_output = run_sort(
            "manual_arrange",
            measure_photos,
            pre_sort_buckets=_to_list(measure_payload.get("pre_sort_buckets")),
            allow_conflicting_tags=bool(
                measure_payload.get("allow_conflicting_tags", True)
            ),
        )

        # # Scary Terminal Logs
        # job_manager.log(job_id, "📄 Manual arrange sort output:")
        # job_manager.log(job_id, repr(sort_output.structure))
        # job_manager.log(job_id, "📄 Manual arrange issues:")
        # job_manager.log(job_id, repr(sort_output.issues))

        return sort_output

    else:
        raise ValueError(f"'{measure_type}' is not supported yet — pick a different measure type.")


def _convert_photos_for_lighting(raw_photos):
    from datasets.lighting.sort import Photo as LightingPhoto
    lighting_photos = []
    for p in raw_photos:
        p_id = str(p.get("id") or p.get("photo_id") or "")
        tags = _clean_tag_list(p.get("tag_names", [])) # Added helper call here to clean tags from CC
        raw_ts = p.get("created_at") or p.get("captured_at") or 0
        if isinstance(raw_ts, (int, float)):
            ts = from_timestamp(raw_ts)
        elif isinstance(raw_ts, str):
            try:
                ts = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
            except Exception:
                ts = datetime.min
        elif isinstance(raw_ts, datetime):
            ts = raw_ts
        else:
            ts = datetime.min
        lighting_photos.append(LightingPhoto(photo_id=p_id, tags=tags, timestamp=ts, data=p))
    return lighting_photos


@report_bp.route('/')
def home():
    return render_template('index.html')


@report_bp.route('/report')
def open_report():
    return send_from_directory(paths.STATIC_DIR, 'report.html')


@report_bp.route('/reports/<filename>')
def download_report(filename):
    return send_from_directory(paths.REPORTS_DIR, filename)


@report_bp.route('/start_job', methods=['POST'])
def start_job():
    if not job_manager.work_lock.acquire(blocking=False):
        return jsonify({"error": "busy"}), 429

    data           = request.json or {}
    job_id         = str(uuid.uuid4())
    run_id         = str(uuid.uuid4())
    is_multi       = bool(data.get('is_multi_project'))
    project_id     = data.get('project_id')
    project_name   = data.get('project_name') or project_id
    project_address = str(data.get('project_address') or '').strip()
    package_name   = data.get('package_name') or project_name
    projects_raw   = data.get('projects') or []
    measures_payload = data.get('measures') or []

    analytics_payload = data.get('analytics') or {}
    display_name = str(analytics_payload.get('display_name') or '').strip() or 'Anonymous'
    user_id = analytics_payload.get('user_id') or analytics.slugify_user_id(display_name)
    session_id = str(analytics_payload.get('session_id') or uuid.uuid4())
    ux = analytics_payload.get('ux') or {}
    user_agent = request.headers.get('User-Agent', '')

    complete_projects = _filter_complete_projects(projects_raw) if is_multi else []
    cache_key = None
    if is_multi:
        cache_key = derive_package_id(package_name, [p['id'] for p in complete_projects])

    project_block = {
        "is_multi_project": is_multi,
        "project_id": project_id if not is_multi else None,
        "package_id": cache_key,
        "project_name": project_name if not is_multi else None,
        "project_address": project_address,
        "package_name": package_name if is_multi else None,
        "projects": complete_projects if is_multi else [],
    }

    analytics_record = analytics.new_report_run(
        run_id=run_id,
        user_id=user_id,
        display_name=display_name,
        session_id=session_id,
        project_block=project_block,
        measures_payload=measures_payload,
        ux=ux,
        user_agent=user_agent,
    )

    with job_manager.jobs_lock:
        job_manager.jobs[job_id] = job_manager.new_job()
        job_manager.jobs[job_id]['analytics_run_id'] = run_id
        if cache_key:
            job_manager.jobs[job_id]['package_id'] = cache_key

    def run():
        nonlocal project_id, project_name, cache_key
        ts_start = time.time()
        timing = {}
        photos = []
        photos_per_project = {}
        measure_outcomes = {}
        unknown_count = 0
        html_generated = False
        status = "error"
        error_type = None
        error_message = None

        def _save_analytics():
            analytics.finalize_report_run(
                analytics_record,
                status=status,
                measures_payload=measures_payload,
                measure_outcomes=measure_outcomes,
                photos_fetched_total=len(photos),
                photos_per_project=photos_per_project,
                ts_start=ts_start,
                unknown_count=unknown_count,
                html_generated=html_generated,
                timing_ms=timing,
                error_type=error_type,
                error_message=error_message,
            )
            analytics.save_run(analytics_record)

        try:
            job_manager.log(job_id, f"⚙️ Configuring {len(measures_payload)} measure(s)...")

            measure_configs = _build_measure_configs(measures_payload)
            payload_by_id = {m.get("id"): m for m in measures_payload}

            t0 = time.time()

            if is_multi:
                if not complete_projects:
                    job_manager.log(job_id, "❌ ERROR: No complete project pairs provided.")
                    error_type = "ValidationError"
                    error_message = "No complete project pairs provided."
                    job_manager.finish(job_id, "error")
                    return

                cache_key = derive_package_id(package_name, [p['id'] for p in complete_projects])
                project_id = cache_key
                project_name = package_name
                config.PROJECT_ID = cache_key
                config.PROJECT_NAME = package_name
                job_manager.save_project_metadata(cache_key, address=project_address)

                _append_package_usage_log(cache_key, package_name, complete_projects)
                job_manager.log(job_id, f"📦 Multi-project package: {package_name} ({cache_key})")

                for proj in complete_projects:
                    pid, nick = proj['id'], proj['nickname']
                    job_manager.log(job_id, f"📥 Fetching photos for '{nick}' ({pid})...")
                    project_photos = fetch_photos(pid)
                    photos_per_project[nick] = len(project_photos)
                    for photo in project_photos:
                        photo['source_project_id'] = pid
                        photo['source_project_nickname'] = nick
                    job_manager.log(job_id, f"✅ {len(project_photos)} photos from '{nick}'")
                    photos.extend(project_photos)

                job_manager.log(job_id, f"✅ {len(photos)} total photos across {len(complete_projects)} project(s)")
            else:
                config.PROJECT_ID = project_id
                config.PROJECT_NAME = project_name
                job_manager.save_project_metadata(project_id, address=project_address)
                _append_usage_log(project_id, project_name)
                job_manager.log(job_id, "📥 Fetching photos...")
                job_manager.log(job_id, f"Route project_id={project_id}, config.PROJECT_ID={config.PROJECT_ID}")
                photos = fetch_photos(project_id)
                photos_per_project[project_name or project_id] = len(photos)
                job_manager.log(job_id, f"✅ {len(photos)} photos fetched")

            timing["fetch"] = int((time.time() - t0) * 1000)
            report_title = project_name

            t_tag = time.time()
            _tag_photos(photos, job_id)
            timing["tagging"] = int((time.time() - t_tag) * 1000)

            job_manager.log(job_id, "🔀 Classifying photos by measure...")
            t_class = time.time()
            try:
                classification = run_measure_classification(
                    photos,
                    measure_configs,
                    multi_project=is_multi,
                    complete_projects=complete_projects if is_multi else None,
                )
            except DuplicateMeasureKeywordError as e:
                job_manager.log(job_id, f"❌ ERROR: {e}")
                error_type = "DuplicateMeasureKeywordError"
                error_message = str(e)
                job_manager.finish(job_id, "error")
                return
            except SubcontractedConfigError as e:
                job_manager.log(job_id, f"❌ ERROR: {e}")
                error_type = "SubcontractedConfigError"
                error_message = str(e)
                job_manager.finish(job_id, "error")
                return
            except ManualArrangeConfigError as e:
                job_manager.log(job_id, f"❌ ERROR: {e}")
                error_type = "ManualArrangeConfigError"
                error_message = str(e)
                job_manager.finish(job_id, "error")
                return
            except MultiProjectConfigError as e:
                job_manager.log(job_id, f"❌ ERROR: {e}")
                error_type = "MultiProjectConfigError"
                error_message = str(e)
                job_manager.finish(job_id, "error")
                return
            timing["classification"] = int((time.time() - t_class) * 1000)

            unknown_count = len(classification.unknown)
            if classification.unknown:
                job_manager.log(job_id, f"❓ {unknown_count} photo(s) didn't match any measure")

            sorted_data = {"measures": {}, "unknown": classification.unknown}
            html_measures = []
            cache_key = project_id

            t_sort = time.time()
            for measure in measure_configs:
                measure_photos = classification.by_measure.get(measure.id, [])
                measure_payload = payload_by_id.get(measure.id, {})
                job_manager.log(
                    job_id,
                    f"🔄 Sorting '{measure.name}' ({measure.type}) — {len(measure_photos)} photo(s)...",
                )

                try:
                    sort_output = _configure_and_sort_measure(
                        measure.type, measure_payload, measure_photos, job_id, cache_key, project_name
                    )
                except ValueError as e:
                    job_manager.log(job_id, f"⚠️ Skipping '{measure.name}': {e}")
                    measure_outcomes[measure.id] = {
                        "photos_classified": len(measure_photos),
                        "sort_shape": None,
                        "sort_issues": [{"error": str(e)}],
                        "issues_count": 1,
                        "skipped": True,
                    }
                    continue

                issues = sort_output.issues or []
                measure_outcomes[measure.id] = {
                    "photos_classified": len(measure_photos),
                    "sort_shape": sort_output.shape,
                    "sort_issues": issues,
                    "issues_count": len(issues),
                }

                sorted_data["measures"][measure.id] = {
                    "type": measure.type,
                    "name": measure.name,
                    "sorted_structure": sort_output.structure,
                    "special": sort_output.special,
                    "issues": sort_output.issues,
                    "shape": sort_output.shape,
                }

                job_manager.save_sorted_structure(
                    project_id=cache_key,
                    measure_id=measure.id,
                    structure=sort_output.structure,
                    photos=measure_photos,
                    special_rooms_structure=sort_output.special,
                    sort_mode=sort_output.shape,
                    name=measure.name,
                )

                html_entry = {
                    "id": measure.id,
                    "name": measure.name,
                    "type": measure.type,
                    "shape": sort_output.shape,
                    "structure": sort_output.structure,
                    "special": sort_output.special,
                    "phases": _to_list(measure_payload.get("phases")) if measure.type == "lighting" else None,
                }
                if measure.type == "lighting":
                    html_entry["location_level_count"] = len(
                        parse_location_levels(measure_payload)
                    )
                html_measures.append(html_entry)

            timing["sort_total"] = int((time.time() - t_sort) * 1000)
            job_manager.set_sorted_data(job_id, sorted_data)

            if html_measures:
                job_manager.log(job_id, "🏗 Generating HTML report...")
                t_html = time.time()
                if is_multi and classification.unknown:
                    unknown_by_project = _build_unknown_by_project(classification.unknown)
                    generators.generate_html_report(
                        html_measures,
                        unknown_photos_by_project=unknown_by_project,
                        title=report_title,
                    )
                else:
                    generators.generate_html_report(
                        html_measures,
                        unknown_photos=classification.unknown,
                        title=report_title,
                    )
                timing["html_gen"] = int((time.time() - t_html) * 1000)
                html_generated = True
                job_manager.log(job_id, "✅ HTML report ready!")
            else:
                job_manager.log(job_id, "⚠️ No measure produced a sortable result — no HTML report generated.")

            status = "complete"
            job_manager.finish(job_id, "complete")

        except Exception as e:
            import traceback
            job_manager.log(job_id, f"❌ ERROR: {e}")
            job_manager.log(job_id, traceback.format_exc())
            error_type = type(e).__name__
            error_message = str(e)
            job_manager.finish(job_id, "error")

        finally:
            timing["total"] = int((time.time() - ts_start) * 1000)
            try:
                _save_analytics()
            except Exception:
                pass
            try:
                del photos
                del html_measures
            except NameError:
                pass
            gc.collect()
            job_manager.work_lock.release()

    threading.Thread(target=run, daemon=True).start()
    response = {"job_id": job_id, "run_id": run_id}
    if cache_key:
        response["package_id"] = cache_key
    return jsonify(response)