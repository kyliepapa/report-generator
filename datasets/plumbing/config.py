"""
Plumbing dataset configuration.

Reproduces the ORIGINAL (implicit) behavior of newreport.py exactly:
  - sub-units are bathrooms, still typed in by the user via the dashboard
  - "MASTER" is the primary/default bathroom if present, else index 0
  - sort-mode key strings match the original literals exactly
    (unit_phase / unit_bath_phase / bldg_unit_phase / full) so nothing
    downstream -- determine_html_method, apply_photo_edits,
    generate_html_*, or script.js's zone-ID parsing -- needs to change
    in this pass. Those all still key off these exact strings.

When HVAC/lighting datasets are added later, they can supply their own
sort_mode_map with whatever key names make sense for their hierarchy --
plumbing intentionally does NOT do that yet, to keep this step a pure
relocation with no behavior change.
"""

from datasets.base import DatasetConfig


def _plumbing_sort_mode_map(label_format: str, multi_sub_unit: bool) -> str:
    """Identical to the original configure_sorting() body in newreport.py."""
    if label_format == "123":
        return "unit_bath_phase" if multi_sub_unit else "unit_phase"
    else:
        return "full" if multi_sub_unit else "bldg_unit_phase"


PLUMBING = DatasetConfig(
    key="plumbing",
    display_name="Plumbing",
    sub_unit_field_name="bath",
    sub_unit_label_singular="Bathroom",
    sub_unit_label_plural="Bathrooms",
    primary_sub_unit_marker="MASTER",
    phase_order=["UNTAGGED", "BEFORE", "AFTER"],
    sort_mode_map=_plumbing_sort_mode_map,
    supports_special_rooms=True,
)