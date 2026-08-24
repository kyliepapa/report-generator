"""
Core, dataset-agnostic configuration state.

Holds the workflow-wide inputs (project ID, label format, sub-unit
list, etc.) that used to live as bare module-level globals scattered
through the old newreport.py. Still global/mutable state -- same
threading model as before (one job runs at a time, guarded by
work_lock in the Flask routes) -- just centralized and stripped of
plumbing-specific naming.

Dataset-specific defaults (sub-unit vocabulary, phase order, sort-mode
mapping) come from whichever DatasetConfig is passed to set_dataset().
"""

import os
from typing import List, Optional

from datasets.base import DatasetConfig

# ─────────────────────────────────────────
# ACCESS TOKEN
# ─────────────────────────────────────────
# Was hardcoded directly in newreport.py. Now reads from an environment
# variable; falls back to the old value ONLY so nothing breaks before
# your env is set up. Set REPORT_ACCESS_TOKEN and remove the fallback
# once you've rotated this token (it was sitting in plaintext before).
ACCESS_TOKEN = os.environ.get(
    "REPORT_ACCESS_TOKEN",
    "3kfMeyhnKVfoPhXfMJeMfNH4V71I8uS0ZDgvYVJ2ZG0",
)

# ─────────────────────────────────────────
# RUN-SCOPED INPUT STATE
# (was: PROJECT_ID, PROJECT_NAME, multi_bath_bool, label_format,
#  bathrooms_input, special_rooms_input)
# ─────────────────────────────────────────
PROJECT_ID: Optional[str] = None
PROJECT_NAME: Optional[str] = None
LABEL_FORMAT: str = "123"
MULTI_SUB_UNIT: bool = False
SUB_UNITS_INPUT: List[str] = []
SPECIAL_ROOMS_INPUT: List[str] = []

# Populated by configure_sorting() / configure_sub_units() / configure_special_rooms()
SORT_METHOD_KEY: Optional[str] = None
SUB_UNIT_ORDER: List[str] = []
PRIMARY_SUB_UNIT_INDEX: int = 0
SPECIAL_ROOMS_NORMALIZED: List[str] = []

# Currently-active dataset (plumbing / hvac / lighting / ...).
# Must be set via set_dataset() before configure_sorting() or
# configure_sub_units() are called -- there's no silent default,
# so a missing call fails loudly instead of quietly using the
# wrong dataset's rules.
ACTIVE_DATASET: Optional[DatasetConfig] = None


def set_dataset(dataset: DatasetConfig) -> None:
    """Select which dataset's rules apply to the current job."""
    global ACTIVE_DATASET
    ACTIVE_DATASET = dataset


def set_inputs(project_id, multi_sub_unit, label_fmt, sub_units,
                project_name=None, special_rooms=None) -> None:
    """
    Equivalent to the original set_inputs(), generalized:
      multi_bath_bool -> multi_sub_unit   (still 'yes'/'no'-style string in)
      bathrooms_input  -> sub_units_input
    """
    global PROJECT_ID, PROJECT_NAME, MULTI_SUB_UNIT, LABEL_FORMAT
    global SUB_UNITS_INPUT, SPECIAL_ROOMS_INPUT

    PROJECT_ID = project_id
    PROJECT_NAME = project_name if project_name else project_id
    MULTI_SUB_UNIT = str(multi_sub_unit).lower() == "yes"
    LABEL_FORMAT = label_fmt
    SUB_UNITS_INPUT = [s for s in sub_units if s.strip()]
    SPECIAL_ROOMS_INPUT = [r.strip() for r in (special_rooms or []) if r.strip()]


def _require_dataset() -> DatasetConfig:
    if ACTIVE_DATASET is None:
        raise RuntimeError(
            "No dataset selected. Call set_dataset(...) before "
            "configure_sorting()/configure_sub_units()."
        )
    return ACTIVE_DATASET


def configure_sub_units() -> None:
    """
    Was configure_bathrooms(). Builds the ordered sub-unit list and
    picks the 'primary' index (was MASTER_INDEX, hardcoded to the
    literal string "MASTER"). The marker now comes from the active
    dataset's primary_sub_unit_marker, so a non-plumbing dataset can
    use a different default -- or none -- without touching this
    function.
    """
    global SUB_UNIT_ORDER, PRIMARY_SUB_UNIT_INDEX

    dataset = _require_dataset()
    SUB_UNIT_ORDER = [s.strip() for s in SUB_UNITS_INPUT if s.strip()]

    marker = dataset.primary_sub_unit_marker
    if marker and marker in SUB_UNIT_ORDER:
        PRIMARY_SUB_UNIT_INDEX = SUB_UNIT_ORDER.index(marker)
    else:
        PRIMARY_SUB_UNIT_INDEX = 0


def configure_sorting() -> None:
    """
    Was configure_sorting(). Delegates the
    (label_format, multi_sub_unit) -> sort_method_key decision to the
    active dataset's sort_mode_map, so a dataset can override the
    mapping if it needs different hierarchy levels/names.
    """
    global SORT_METHOD_KEY
    dataset = _require_dataset()
    SORT_METHOD_KEY = dataset.sort_mode_map(LABEL_FORMAT, MULTI_SUB_UNIT)


def get_phase_order() -> List[str]:
    """
    NEW accessor, added while wiring up core/sort_engine.py and
    core/organizer.py in step 2. Both used to reference a bare
    module-level PHASE_ORDER = ["UNTAGGED", "BEFORE", "AFTER"] constant
    in newreport.py. Since DatasetConfig already carries a phase_order
    field (a future dataset might have more/different phases than
    BEFORE/AFTER), this reads from the active dataset instead of
    hardcoding the plumbing-specific list a second time.
    """
    return _require_dataset().phase_order


def configure_special_rooms() -> None:
    """
    Unchanged behavior from the original -- special rooms are
    dataset-agnostic (any dataset can have free-form extra areas
    like a laundry room or garage).
    """
    global SPECIAL_ROOMS_NORMALIZED
    SPECIAL_ROOMS_NORMALIZED = [r.upper() for r in SPECIAL_ROOMS_INPUT]