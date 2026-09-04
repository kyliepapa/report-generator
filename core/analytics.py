"""
Usage analytics: per-run records and derived user profiles.

Each report or PDF job is stored as a self-contained JSON document under
data/analytics/runs/{run_id}.json. An append-only runs.jsonl mirror is
written for audit/history. users.json holds rolling aggregates for the
dashboard overview and future presets.
"""

from __future__ import annotations

import json
import os
import re
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional

import core.paths as paths
from core.timezone import now_iso
from datasets.lighting.config import parse_location_levels

_lock = threading.Lock()

_RUN_TYPES = frozenset({"report", "pdf"})


def _now_iso() -> str:
    return now_iso()


def slugify_user_id(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", str(name or "").strip().lower())
    return slug.strip("_") or "anonymous"


def _runs_dir() -> str:
    d = paths.ANALYTICS_RUNS_DIR
    os.makedirs(d, exist_ok=True)
    return d


def _run_path(run_id: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_-]", "", str(run_id or ""))
    return os.path.join(_runs_dir(), f"{safe}.json")


def _read_json(path: str, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _write_json(path: str, data) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def _append_jsonl(path: str, record: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _to_list(val) -> List[str]:
    if isinstance(val, list):
        return [str(x).strip() for x in val if str(x).strip()]
    if isinstance(val, str):
        return [x.strip() for x in val.split(",") if x.strip()]
    return []


def _measure_config_snapshot(measure_type: str, payload: dict) -> dict:
    mtype = str(measure_type or "").lower()
    if mtype == "aquamizer":
        return {
            "multi_bath": payload.get("multi_bath"),
            "label_format": payload.get("label_format"),
            "bath_names": _to_list(payload.get("bath_names")),
            "special_rooms": _to_list(payload.get("special_rooms")),
        }
    if mtype == "lighting":
        return {
            "installers": _to_list(payload.get("installers")),
            "location_levels": parse_location_levels(payload),
            "fixture_types": _to_list(payload.get("fixture_types")),
            "phases": _to_list(payload.get("phases")),
            "serial_tag": _to_list(payload.get("serial_tag")),
            "loc_bigger_num": payload.get("loc_bigger_num"),
        }
    if mtype == "heat_pump":
        return {
            "fixtures": _to_list(payload.get("fixtures")),
            "serial_tag": _to_list(payload.get("serial_tag")),
            "allow_competing_fixture_tags": bool(
                payload.get("allow_competing_fixture_tags")
            ),
            "auto_assign_lone_serial_to_before": bool(
                payload.get("auto_assign_lone_serial_to_before")
            ),
            "intuitive_fixture_sort": bool(payload.get("intuitive_fixture_sort", True)),
            "multi_unit": bool(payload.get("multi_unit")),
            "lone_number_mode": str(payload.get("lone_number_mode") or "none"),
            "locations": _to_list(payload.get("locations")),
        }
    if mtype == "subcontracted":
        return {
            "hash": str(payload.get("hash") or ""),
            "measure_mark": str(payload.get("measure_mark") or ""),
            "key_source": str(payload.get("key_source") or "tags"),
        }
    if mtype == "manual_arrange":
        return {
            "pre_sort_buckets": _to_list(payload.get("pre_sort_buckets")),
            "allow_conflicting_tags": bool(payload.get("allow_conflicting_tags", True)),
        }
    if mtype == "outliers":
        sets = []
        for raw_set in payload.get("outlier_sets") or []:
            sets.append({
                "section_name": str(raw_set.get("section_name") or ""),
                "project_id": str(raw_set.get("project_id") or ""),
                "tags": _to_list(raw_set.get("tags")),
                "tag_match_mode": str(raw_set.get("tag_match_mode") or "any"),
            })
        return {"outlier_sets": sets}
    return {}


def build_measures_snapshot(
    measures_payload: List[dict],
    measure_outcomes: Optional[Dict[str, dict]] = None,
) -> List[dict]:
    measure_outcomes = measure_outcomes or {}
    measures_out = []
    for m in measures_payload or []:
        mid = m.get("id")
        mtype = str(m.get("type") or "").lower()
        outcome = measure_outcomes.get(mid) or {}
        measures_out.append({
            "id": mid,
            "type": mtype,
            "name": m.get("name") or mtype,
            "measure_keywords": _to_list(m.get("measure_keywords")),
            "config": _measure_config_snapshot(mtype, m),
            "applicable_projects": _to_list(m.get("applicable_projects")),
            "outcome": outcome,
        })
    return measures_out


def empty_edits() -> dict:
    return {
        "edit_mode_entered": False,
        "photo_moves_count": 0,
        "photo_reorders_count": 0,
        "undo_count": 0,
        "reset_clicked": False,
        "heading_edits_count": 0,
        "heading_injections_count": 0,
        "heading_label_edits_count": 0,
        "photo_tag_edits_count": 0,
        "photo_transforms_count": 0,
        "zones_touched": [],
        "cover_project_name_edited": False,
        "edit_intensity": 0.0,
    }


def compute_edit_intensity(edits: dict, photo_count: int) -> float:
    if not photo_count:
        return 0.0
    total = (
        int(edits.get("photo_moves_count") or 0)
        + int(edits.get("photo_reorders_count") or 0)
        + int(edits.get("heading_edits_count") or 0)
        + int(edits.get("heading_injections_count") or 0)
        + int(edits.get("heading_label_edits_count") or 0)
        + int(edits.get("photo_tag_edits_count") or 0)
        + int(edits.get("photo_transforms_count") or 0)
    )
    return round(total / photo_count, 4)


def new_report_run(
    run_id: str,
    user_id: str,
    display_name: str,
    session_id: str,
    project_block: dict,
    measures_payload: List[dict],
    ux: Optional[dict] = None,
    user_agent: str = "",
) -> dict:
    return {
        "run_id": run_id,
        "parent_run_id": None,
        "run_type": "report",
        "ts_start": _now_iso(),
        "ts_end": None,
        "duration_ms": None,
        "user_id": user_id,
        "display_name": display_name,
        "session_id": session_id,
        "status": "running",
        "error_type": None,
        "error_message": None,
        "project": project_block,
        "measures": build_measures_snapshot(measures_payload),
        "pipeline": None,
        "edits": empty_edits(),
        "pdf": None,
        "ux": ux or {},
        "meta": {"user_agent": user_agent},
    }


def finalize_report_run(
    record: dict,
    status: str,
    measures_payload: List[dict],
    measure_outcomes: Dict[str, dict],
    photos_fetched_total: int,
    photos_per_project: Optional[dict],
    ts_start: float,
    unknown_count: int = 0,
    html_generated: bool = False,
    timing_ms: Optional[dict] = None,
    error_type: Optional[str] = None,
    error_message: Optional[str] = None,
) -> dict:
    ts_end = _now_iso()
    duration_ms = int((datetime.now().timestamp() - ts_start) * 1000)
    unknown_rate = round(unknown_count / photos_fetched_total, 4) if photos_fetched_total else 0.0
    measures = build_measures_snapshot(measures_payload, measure_outcomes)

    record["ts_end"] = ts_end
    record["duration_ms"] = duration_ms
    record["status"] = status
    record["error_type"] = error_type
    record["error_message"] = error_message
    record["measures"] = measures
    record["pipeline"] = {
        "photos_fetched_total": photos_fetched_total,
        "photos_per_project": photos_per_project or {},
        "unknown_photo_count": unknown_count,
        "unknown_rate": unknown_rate,
        "html_generated": html_generated,
        "measure_count": len(measures_payload or []),
        "project_count": len((record.get("project") or {}).get("projects") or []) or 1,
        "timing_ms": timing_ms or {"total": duration_ms},
    }
    photo_count = photos_fetched_total or 1
    record["edits"]["edit_intensity"] = compute_edit_intensity(record.get("edits") or {}, photo_count)
    return record


def new_pdf_run(
    run_id: str,
    parent_run_id: str,
    user_id: str,
    display_name: str,
    session_id: str,
    project_block: dict,
    pdf_block: dict,
    edits: dict,
    ux: Optional[dict] = None,
    user_agent: str = "",
) -> dict:
    return {
        "run_id": run_id,
        "parent_run_id": parent_run_id,
        "run_type": "pdf",
        "ts_start": _now_iso(),
        "ts_end": None,
        "duration_ms": None,
        "user_id": user_id,
        "display_name": display_name,
        "session_id": session_id,
        "status": "running",
        "error_type": None,
        "error_message": None,
        "project": project_block,
        "measures": [],
        "pipeline": None,
        "edits": edits,
        "pdf": pdf_block,
        "ux": ux or {},
        "meta": {"user_agent": user_agent},
    }


def finalize_pdf_run(
    record: dict,
    status: str,
    ts_start: float,
    timing_ms: Optional[dict] = None,
    error_type: Optional[str] = None,
    error_message: Optional[str] = None,
) -> dict:
    duration_ms = int((datetime.now().timestamp() - ts_start) * 1000)
    record["ts_end"] = _now_iso()
    record["duration_ms"] = duration_ms
    record["status"] = status
    record["error_type"] = error_type
    record["error_message"] = error_message
    if record.get("pdf") is not None:
        record["pdf"]["generated"] = status == "complete"
        record["pdf"]["duration_ms"] = duration_ms
        if timing_ms:
            record["pdf"]["timing_ms"] = timing_ms
    return record


def save_run(record: dict) -> None:
    run_id = record.get("run_id")
    if not run_id:
        return
    with _lock:
        _write_json(_run_path(run_id), record)
        _append_jsonl(paths.ANALYTICS_RUNS_LOG, record)
        _update_user_profile(record)


def load_run(run_id: str) -> Optional[dict]:
    path = _run_path(run_id)
    if not os.path.isfile(path):
        return None
    return _read_json(path, None)


def patch_report_edits(run_id: str, edits: dict) -> bool:
    record = load_run(run_id)
    if not record or record.get("run_type") != "report":
        return False
    merged = empty_edits()
    merged.update(record.get("edits") or {})
    merged.update(edits or {})
    photos = (record.get("pipeline") or {}).get("photos_fetched_total") or 0
    merged["edit_intensity"] = compute_edit_intensity(merged, photos)
    record["edits"] = merged
    save_run(record)
    return True


def list_runs(
    user_id: Optional[str] = None,
    run_type: Optional[str] = None,
    limit: Optional[int] = None,
) -> List[dict]:
    runs = []
    runs_dir = _runs_dir()
    for name in os.listdir(runs_dir):
        if not name.endswith(".json"):
            continue
        rec = _read_json(os.path.join(runs_dir, name), None)
        if not rec:
            continue
        if user_id and rec.get("user_id") != user_id:
            continue
        if run_type and rec.get("run_type") != run_type:
            continue
        runs.append(rec)
    runs.sort(key=lambda r: r.get("ts_start") or "", reverse=True)
    if limit:
        runs = runs[:limit]
    return runs


def list_user_ids() -> List[dict]:
    users = _read_json(paths.ANALYTICS_USERS_FILE, {})
    out = []
    for uid, data in users.items():
        out.append({
            "user_id": uid,
            "display_name": data.get("display_name") or uid,
            "last_seen": data.get("last_seen"),
            "run_count": data.get("run_count", 0),
        })
    out.sort(key=lambda u: u.get("last_seen") or "", reverse=True)
    return out


def _inc_pref(prefs: dict, key: str, value) -> None:
    if value is None or value == "":
        return
    bucket = prefs.setdefault(key, {})
    sval = str(value)
    bucket[sval] = bucket.get(sval, 0) + 1


def _update_user_profile(record: dict) -> None:
    uid = record.get("user_id")
    if not uid:
        return
    users = _read_json(paths.ANALYTICS_USERS_FILE, {})
    entry = users.setdefault(uid, {
        "display_name": record.get("display_name") or uid,
        "first_seen": record.get("ts_start"),
        "last_seen": record.get("ts_start"),
        "run_count": 0,
        "totals": {
            "reports": 0,
            "pdfs": 0,
            "photos_processed": 0,
            "unknown_photos": 0,
            "edits_total": 0,
        },
        "preferences": {},
    })
    entry["display_name"] = record.get("display_name") or entry.get("display_name") or uid
    ts = record.get("ts_end") or record.get("ts_start")
    if ts and (not entry.get("first_seen") or ts < entry["first_seen"]):
        entry["first_seen"] = ts
    if ts and (not entry.get("last_seen") or ts > entry["last_seen"]):
        entry["last_seen"] = ts
    entry["run_count"] = entry.get("run_count", 0) + 1

    totals = entry.setdefault("totals", {})
    prefs = entry.setdefault("preferences", {})
    rtype = record.get("run_type")
    if rtype == "report" and record.get("status") == "complete":
        totals["reports"] = totals.get("reports", 0) + 1
        pipe = record.get("pipeline") or {}
        totals["photos_processed"] = totals.get("photos_processed", 0) + int(
            pipe.get("photos_fetched_total") or 0
        )
        totals["unknown_photos"] = totals.get("unknown_photos", 0) + int(
            pipe.get("unknown_photo_count") or 0
        )
        edits = record.get("edits") or {}
        edit_total = (
            int(edits.get("photo_moves_count") or 0)
            + int(edits.get("photo_reorders_count") or 0)
            + int(edits.get("heading_edits_count") or 0)
            + int(edits.get("heading_injections_count") or 0)
            + int(edits.get("heading_label_edits_count") or 0)
        )
        totals["edits_total"] = totals.get("edits_total", 0) + edit_total
        for m in record.get("measures") or []:
            cfg = m.get("config") or {}
            mtype = m.get("type") or "unknown"
            for key, val in cfg.items():
                if isinstance(val, list):
                    for item in val:
                        _inc_pref(prefs, f"{mtype}.{key}", item)
                else:
                    _inc_pref(prefs, f"{mtype}.{key}", val)
    elif rtype == "pdf" and record.get("status") == "complete":
        totals["pdfs"] = totals.get("pdfs", 0) + 1
        pdf = record.get("pdf") or {}
        _inc_pref(prefs, "pdf.layout", pdf.get("layout"))
        _inc_pref(prefs, "pdf.metadata_position", pdf.get("metadata_position"))
        _inc_pref(prefs, "pdf.hide_empty_fields", pdf.get("hide_empty_fields"))

    _write_json(paths.ANALYTICS_USERS_FILE, users)


def compute_overview(user_id: Optional[str] = None) -> dict:
    runs = list_runs(user_id=user_id)
    reports = [r for r in runs if r.get("run_type") == "report"]
    pdfs = [r for r in runs if r.get("run_type") == "pdf"]
    completed_reports = [r for r in reports if r.get("status") == "complete"]
    completed_pdfs = [r for r in pdfs if r.get("status") == "complete"]

    total_photos = sum(
        int((r.get("pipeline") or {}).get("photos_fetched_total") or 0)
        for r in completed_reports
    )
    total_unknown = sum(
        int((r.get("pipeline") or {}).get("unknown_photo_count") or 0)
        for r in completed_reports
    )
    unknown_rates = [
        float((r.get("pipeline") or {}).get("unknown_rate") or 0)
        for r in completed_reports
    ]
    edit_intensities = [
        float((r.get("edits") or {}).get("edit_intensity") or 0)
        for r in completed_reports
    ]
    success_reports = len(completed_reports)
    failed_reports = len([r for r in reports if r.get("status") == "error"])

    measure_type_counts: Dict[str, int] = {}
    for r in completed_reports:
        for m in r.get("measures") or []:
            t = m.get("type") or "unknown"
            measure_type_counts[t] = measure_type_counts.get(t, 0) + 1

    user_ids = sorted({r.get("user_id") for r in runs if r.get("user_id")})

    def _avg(vals):
        return round(sum(vals) / len(vals), 4) if vals else 0.0

    return {
        "user_filter": user_id,
        "total_runs": len(runs),
        "report_runs": len(reports),
        "pdf_runs": len(pdfs),
        "reports_completed": success_reports,
        "reports_failed": failed_reports,
        "pdfs_completed": len(completed_pdfs),
        "total_photos_processed": total_photos,
        "total_unknown_photos": total_unknown,
        "avg_unknown_rate": _avg(unknown_rates),
        "avg_edit_intensity": _avg(edit_intensities),
        "pdf_conversion_rate": round(len(completed_pdfs) / success_reports, 4) if success_reports else 0.0,
        "measure_type_counts": measure_type_counts,
        "user_ids": user_ids,
    }
