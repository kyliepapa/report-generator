"""
In-memory job store.

Was living directly in app.py, mixed in with route handlers. Genuinely
dataset-agnostic infra (both the HTML-report job and the PDF job share
this same store), so it belongs in core/ rather than web/routes/ --
multiple route modules import from here rather than each other.

Cache key changed from (project_id, dataset_key) to (project_id,
measure_id) as part of multi-measure support: a run can now produce
several sorted structures for the same project (one per measure), and
two measures can share the same dataset_key/type (e.g. two separate
Lighting measures), so dataset_key is no longer unique enough on its
own. measure_id is the per-measure id the frontend already generates
for each tab, so it's unique within a run and stable for a given
measure across the job. Locking behavior and the job dict shape are
otherwise unchanged.

Sorted structures are pickled to disk (slim photo dicts only); RAM
holds metadata index entries keyed by (project_id, measure_id).
"""

import os
import pickle
import re
import threading
import time

import core.paths as paths
from core.cache_normalize import (
    normalize_structure_for_cache,
    normalize_special_rooms_for_cache,
)

# { job_id: { status, log, pdf_filename, progress_done, progress_total } }
jobs = {}
# Metadata index for on-disk sorted-structure caches:
# key: (str(project_id).lower(), str(measure_id).lower())
# value: {project_id, measure_id, name, sort_mode, cache_path, saved_at}
sorted_structures = {}
# Per-project metadata (address, etc.) keyed by str(project_id).lower()
project_metadata = {}

jobs_lock = threading.Lock()
work_lock = threading.Lock()


def _safe_cache_component(value):
    text = str(value).strip().lower()
    return re.sub(r"[^\w\-.]+", "_", text) or "unknown"


def _cache_key(project_id, measure_id):
    return (
        str(project_id).strip().lower(),
        str(measure_id).strip().lower(),
    )


def _cache_path(project_id, measure_id):
    pid = _safe_cache_component(project_id)
    mid = _safe_cache_component(measure_id)
    return os.path.join(paths.CACHE_DIR, f"{pid}_{mid}.pkl")


def _list_disk_cache_entries(project_id):
    pid = _safe_cache_component(project_id)
    prefix = f"{pid}_"
    if not os.path.isdir(paths.CACHE_DIR):
        return []
    entries = []
    for name in os.listdir(paths.CACHE_DIR):
        if not name.startswith(prefix) or not name.endswith(".pkl"):
            continue
        measure_id = name[len(prefix):-4]
        entries.append((measure_id, os.path.join(paths.CACHE_DIR, name)))
    return entries


def _hydrate_cache_entry(meta):
    path = meta.get("cache_path")
    if not path or not os.path.isfile(path):
        return None
    with open(path, "rb") as f:
        payload = pickle.load(f)
    return {
        "project_id": meta.get("project_id"),
        "measure_id": meta.get("measure_id"),
        "name": meta.get("name") or payload.get("name"),
        "sort_mode": meta.get("sort_mode") or payload.get("sort_mode"),
        "cache_path": path,
        "saved_at": meta.get("saved_at"),
        "structure": payload["structure"],
        "special_rooms_structure": payload.get("special_rooms_structure", {}),
    }


def save_project_metadata(project_id, **fields):
    if not project_id:
        return
    key = str(project_id).strip().lower()
    with jobs_lock:
        entry = project_metadata.setdefault(key, {})
        entry.update({k: v for k, v in fields.items() if v is not None})


def get_project_metadata(project_id):
    if not project_id:
        return {}
    key = str(project_id).strip().lower()
    with jobs_lock:
        return dict(project_metadata.get(key, {}))


def get_project_address(project_id):
    return str(get_project_metadata(project_id).get("address") or "").strip()


def save_sorted_structure(project_id, measure_id, structure, photos=None,
                          special_rooms_structure=None, sort_mode=None, name=None):
    if not project_id or not measure_id:
        return
    key = _cache_key(project_id, measure_id)
    slim_structure = normalize_structure_for_cache(structure, sort_mode)
    slim_special = normalize_special_rooms_for_cache(special_rooms_structure)
    cache_path = _cache_path(project_id, measure_id)
    payload = {
        "structure": slim_structure,
        "special_rooms_structure": slim_special,
        "sort_mode": sort_mode,
        "name": name or str(measure_id),
    }
    with open(cache_path, "wb") as f:
        pickle.dump(payload, f, protocol=pickle.HIGHEST_PROTOCOL)
    with jobs_lock:
        sorted_structures[key] = {
            "project_id": project_id,
            "measure_id": str(measure_id).strip().lower(),
            "name": name or str(measure_id),
            "sort_mode": sort_mode,
            "cache_path": cache_path,
            "saved_at": time.time(),
        }


def load_sorted_structure(project_id, measure_id):
    if not project_id or not measure_id:
        return None
    key = _cache_key(project_id, measure_id)
    with jobs_lock:
        meta = sorted_structures.get(key)
    if meta is None:
        path = _cache_path(project_id, measure_id)
        if not os.path.isfile(path):
            return None
        meta = {
            "project_id": project_id,
            "measure_id": str(measure_id).strip().lower(),
            "cache_path": path,
            "saved_at": os.path.getmtime(path),
        }
    return _hydrate_cache_entry(meta)


def get_sorted_structure(project_id, measure_id):
    return load_sorted_structure(project_id, measure_id)


def get_all_sorted_structures(project_id):
    """Returns all cached sorted structures for a given project_id."""
    if not project_id:
        return []
    pid = str(project_id).strip().lower()
    with jobs_lock:
        metas = [dict(v) for k, v in sorted_structures.items() if k[0] == pid]
    indexed_paths = {m.get("cache_path") for m in metas}
    for measure_id, path in _list_disk_cache_entries(project_id):
        if path in indexed_paths:
            continue
        metas.append({
            "project_id": project_id,
            "measure_id": measure_id,
            "cache_path": path,
            "saved_at": os.path.getmtime(path),
        })
    results = []
    for meta in metas:
        entry = _hydrate_cache_entry(meta)
        if entry:
            results.append(entry)
    return results


def evict_project(project_id):
    """Clear in-memory cache index for a project; disk pickle files are kept.

    PDF jobs call this after each export so RAM does not grow across runs.
    Re-export without re-running HTML still works via load from CACHE_DIR.
    """
    if not project_id:
        return
    pid = str(project_id).strip().lower()
    with jobs_lock:
        for key in [k for k in sorted_structures if k[0] == pid]:
            del sorted_structures[key]


def new_job():
    return {
        "status":         "running",
        "log":            [],
        "pdf_filename":   None,
        "progress_done":  0,
        "progress_total": 0,
        # Multi-measure result envelope: {"measures": {measure_id: {...}}, "unknown": [...]}.
        # Set once via set_sorted_data(); None until the classification/sort step completes.
        "sorted_data":    None,
    }


def set_sorted_data(job_id, sorted_data):
    with jobs_lock:
        if job_id in jobs:
            jobs[job_id]["sorted_data"] = sorted_data


def log(job_id, msg):
    with jobs_lock:
        jobs[job_id]["log"].append(msg)


def set_progress(job_id, done, total):
    with jobs_lock:
        jobs[job_id]["progress_done"]  = done
        jobs[job_id]["progress_total"] = total


def finish(job_id, status, pdf_filename=None):
    with jobs_lock:
        jobs[job_id]["status"] = status
        if pdf_filename:
            jobs[job_id]["pdf_filename"] = pdf_filename


def get_job(job_id):
    with jobs_lock:
        return jobs.get(job_id)
