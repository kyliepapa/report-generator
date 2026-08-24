"""
Dataset configuration interface.

Every dataset module (plumbing, hvac, lighting, ...) exposes one
DatasetConfig instance. core/ only ever talks to this interface --
it never imports a specific dataset module directly. Whatever picks
the active dataset for a job (a route, a form field, etc.) is
responsible for calling core.config.set_dataset(...) with the right
one before the job runs.

Adding a new dataset means creating datasets/<name>/config.py with one
DatasetConfig, NOT touching core/.
"""

from dataclasses import dataclass, field
from typing import Callable, List, Optional


@dataclass
class DatasetConfig:
    # ── Identity ──────────────────────────────────────────────
    key: str
    display_name: str

    # ── Sub-unit vocabulary ───────────────────────────────────
    sub_unit_field_name: str = "sub_unit"
    sub_unit_label_singular: str = "Sub-Unit"
    sub_unit_label_plural: str = "Sub-Units"

    primary_sub_unit_marker: Optional[str] = None

    # ── Phases ────────────────────────────────────────────────
    phase_order: List[str] = field(
        default_factory=lambda: ["UNTAGGED", "BEFORE", "AFTER"]
    )

    # ── Dataset-level shape metadata ──────────────────────────
    # This is the important generalization: sort mode is not limited
    # to plumbing-only strings.
    sort_shape: str = "generic"
    render_mode: str = "standard"

    # Optional; some datasets (like Plumbing) still use it, others
    # may not need it.
    sort_mode_map: Optional[Callable[[str, bool], str]] = None

    supports_special_rooms: bool = True

    def __post_init__(self):
        if self.sort_mode_map is not None and not callable(self.sort_mode_map):
            raise ValueError(
                f"DatasetConfig '{self.key}' sort_mode_map must be callable or None."
            )




# Below is my original code, above is an experimental refactor
# from dataclasses import dataclass, field
# from typing import Callable, List, Optional


# @dataclass
# class DatasetConfig:
#     # ── Identity ──────────────────────────────────────────────
#     key: str                       # e.g. "plumbing", "hvac", "lighting"
#     display_name: str              # e.g. "Plumbing"

#     # ── Sub-unit vocabulary ───────────────────────────────────
#     # "Sub-unit" generalizes what used to be hardcoded everywhere as
#     # "bathroom". The user still types the actual list at request time
#     # (e.g. bath names in the dashboard) -- this config just supplies
#     # the *labels* and *rules* around that list for this dataset.
#     #   plumbing: sub-unit = bathroom            (MASTER, HALL, ...)
#     #   hvac:     sub-unit = equipment type       (SPLIT, PACKAGE, ...)
#     #   lighting: sub-unit = area                 (INTERIOR, EXTERIOR)
#     sub_unit_field_name: str = "sub_unit"       # internal key, e.g. "bath"
#     sub_unit_label_singular: str = "Sub-Unit"   # UI label, e.g. "Bathroom"
#     sub_unit_label_plural: str = "Sub-Units"

#     primary_sub_unit_marker: Optional[str] = None
#     # e.g. "MASTER" -- if a sub-unit with this exact name is present in
#     # the user's typed list, it becomes the default/primary index.
#     # None means "no special default, first entry wins" (same as the
#     # original behavior when "MASTER" wasn't present).

#     # ── Phases ────────────────────────────────────────────────
#     phase_order: List[str] = field(
#         default_factory=lambda: ["UNTAGGED", "BEFORE", "AFTER"]
#     )

#     # ── Sort-mode mapping ─────────────────────────────────────
#     # (label_format, multi_sub_unit_bool) -> sort_method_key string.
#     #
#     # REQUIRED, no default. This is NOT free-form -- despite living on
#     # a per-dataset config, the returned string is a structural switch
#     # consumed verbatim by core/organizer.py (organize_photos,
#     # analyze_missing_photos) and core/sort_engine.py
#     # (determine_sort_method), and -- not yet migrated -- by
#     # generate_html_* and the apply_photo_edits/script.js zone-ID
#     # parsing. Those functions only know 4 shapes today:
#     #   "unit_phase"        -> unit -> phase                (2 levels)
#     #   "bldg_unit_phase"    -> bldg -> unit -> phase         (3 levels)
#     #   "unit_bath_phase"    -> unit -> sub_unit -> phase     (3 levels)
#     #   "full"               -> bldg -> unit -> sub_unit -> phase (4 levels)
#     # A dataset MUST map onto one of these 4 strings until core is
#     # extended to support a genuinely new hierarchy shape -- adding a
#     # 5th shape means updating organize_photos/analyze_missing_photos/
#     # determine_sort_method (and eventually generate_html_*), not just
#     # this config. There used to be a permissive default here that
#     # silently returned an unrecognized string for one branch; removed
#     # in favor of failing at dataset-definition time instead.
#     sort_mode_map: Callable[[str, bool], str] = None

#     # ── Special rooms ─────────────────────────────────────────
#     # Whether this dataset supports the free-form "special rooms" tag
#     # builder (laundry room, garage, etc). True for every dataset today;
#     # exists as a flag in case a future one doesn't use it.
#     supports_special_rooms: bool = True

#     def __post_init__(self):
#         if self.sort_mode_map is None:
#             raise ValueError(
#                 f"DatasetConfig '{self.key}' must supply a sort_mode_map. "
#                 f"It has to return one of: 'unit_phase', 'bldg_unit_phase', "
#                 f"'unit_bath_phase', 'full' -- see the sort_mode_map "
#                 f"docstring above for why there's no safe generic default."
#             )