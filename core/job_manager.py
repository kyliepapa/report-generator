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
"""

import threading

# { job_id: { status, log, pdf_filename, progress_done, progress_total } }
jobs = {}
# Cached sorted structures from HTML generation, one entry per measure:
# key: (str(project_id).lower(), str(measure_id).lower())
sorted_structures = {}

jobs_lock = threading.Lock()
work_lock = threading.Lock()


def save_sorted_structure(project_id, measure_id, structure, photos,
                          special_rooms_structure=None, sort_mode=None, name=None):
    if not project_id or not measure_id:
        return
    key = (str(project_id).strip().lower(), str(measure_id).strip().lower())
    with jobs_lock:
        sorted_structures[key] = {
            "project_id": project_id,
            "measure_id": str(measure_id).strip().lower(),
            "name": name or str(measure_id),
            "sort_mode": sort_mode,
            "structure": structure,
            "photos": photos,
            "special_rooms_structure": special_rooms_structure or {},
        }


def get_sorted_structure(project_id, measure_id):
    if not project_id or not measure_id:
        return None
    key = (str(project_id).strip().lower(), str(measure_id).strip().lower())
    with jobs_lock:
        return sorted_structures.get(key)


def get_all_sorted_structures(project_id):
    """Returns all cached sorted structures for a given project_id."""
    if not project_id:
        return []
    pid = str(project_id).strip().lower()
    with jobs_lock:
        return [v for k, v in sorted_structures.items() if k[0] == pid]


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