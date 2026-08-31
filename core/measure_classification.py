"""
core/measure_classification.py

Classifies fetched photos into configured measure instances, before
any measure-specific sorting runs. Does not touch measure-specific
sorters, adapters, or report/PDF generation.

Handles two existing photo shapes transparently:
  - the lighting Photo dataclass (.tags / .photo_id)
  - the plumbing/aquamizer raw dict shape ({"tag_names": [...], "photo_id": ...})
"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set


# ---------------- Tag normalization ----------------

def normalize_tag(value: Any) -> str:
    return str(value).strip().upper()


def normalize_tags(values) -> List[str]:
    return [n for n in (normalize_tag(v) for v in values) if n]


# ---------------- Photo shape adapters ----------------
# Small compatibility layer so classification works whether a photo
# is the lighting Photo dataclass or a plumbing-style dict. Nothing
# about the underlying Photo objects is modified or copied.

def _get_tags(photo: Any) -> list:
    if hasattr(photo, "tags"):
        return photo.tags
    if isinstance(photo, dict):
        return photo.get("tag_names", photo.get("tags", []))
    return []


def _get_photo_id(photo: Any):
    if hasattr(photo, "photo_id"):
        return photo.photo_id
    if isinstance(photo, dict):
        return photo.get("photo_id")
    return None

# _HTML_TAG_RE = re.compile(r"<[^>]+>")

# def _strip_html(value: str) -> str:
#     return _HTML_TAG_RE.sub("", value).strip()

# def _get_description(photo: Any) -> str:
#     if isinstance(photo, dict):
#         raw = str(photo.get("description") or "")
#     else:
#         raw = str(getattr(photo, "description", "") or "")
#     return _strip_html(raw)

def _get_description(photo: Any) -> str:
    if isinstance(photo, dict):
        return photo.get("description", "").get("plain_text_content", "")
    return getattr(photo, "description", "").get("plain_text_content", "")


# ---------------- Measure configuration ----------------

@dataclass
class MeasureConfig:
    id: str
    type: str
    name: str
    measure_keywords: List[str] = field(default_factory=list)
    classification_tags: List[str] = field(default_factory=list)
    sorter_config: Any = None
    hash: str = ""
    measure_mark: str = ""
    key_source: str = "tags"
    applicable_projects: List[str] = field(default_factory=list)


# ---------------- Duplicate measure-keyword detection ----------------

def find_duplicate_measure_keywords(
    measures: List[MeasureConfig],
) -> Dict[str, List[str]]:
    """{normalized_keyword: [measure_id, ...]} for keywords owned by 2+ measures."""
    owners: Dict[str, Set[str]] = {}
    for measure in measures:
        seen = set()
        for raw in measure.measure_keywords:
            norm = normalize_tag(raw)
            if not norm or norm in seen:
                continue
            seen.add(norm)
            owners.setdefault(norm, set()).add(measure.id)
    return {k: sorted(ids) for k, ids in owners.items() if len(ids) > 1}


class DuplicateMeasureKeywordError(ValueError):
    """Raised when a run is configured with a keyword shared across measures."""
    def __init__(self, duplicates: Dict[str, List[str]]):
        self.duplicates = duplicates
        details = "; ".join(f"{kw} -> {ids}" for kw, ids in duplicates.items())
        super().__init__(f"Duplicate measure keywords across measures: {details}")


class SubcontractedConfigError(ValueError):
    """Raised when subcontracted measure configuration is invalid."""
    pass


class MultiProjectConfigError(ValueError):
    """Raised when multi-project package configuration is invalid."""
    pass


class ManualArrangeConfigError(ValueError):
    """Raised when manual arrange measure configuration is invalid."""
    pass


def _get_source_project_id(photo: Any) -> str:
    if isinstance(photo, dict):
        return str(photo.get("source_project_id") or "").strip()
    return ""


def validate_multi_project_config(
    measures: List[MeasureConfig],
    complete_projects: List[Dict[str, str]],
) -> None:
    """Validate project-pair coverage and uniqueness for a multi-project run."""
    if not complete_projects:
        raise MultiProjectConfigError("At least one complete project pair is required.")

    ids_seen: Dict[str, str] = {}
    nicks_seen: Dict[str, str] = {}
    for proj in complete_projects:
        pid = str(proj.get("id") or "").strip()
        nick = str(proj.get("nickname") or "").strip()
        if pid in ids_seen:
            raise MultiProjectConfigError(
                f"Duplicate project ID '{pid}' (nicknames '{ids_seen[pid]}' and '{nick}')."
            )
        ids_seen[pid] = nick
        if nick in nicks_seen:
            raise MultiProjectConfigError(
                f"Duplicate project nickname '{nick}' (IDs '{nicks_seen[nick]}' and '{pid}')."
            )
        nicks_seen[nick] = pid

    complete_ids = set(ids_seen.keys())
    claimed: Set[str] = set()

    for measure in measures:
        apps = [str(p).strip() for p in measure.applicable_projects if str(p).strip()]
        if not apps:
            raise MultiProjectConfigError(
                f"Measure '{measure.name or measure.id}' must select at least one project."
            )
        for pid in apps:
            if pid not in complete_ids:
                raise MultiProjectConfigError(
                    f"Measure '{measure.name or measure.id}' references unknown project ID '{pid}'."
                )
            claimed.add(pid)

    unclaimed = complete_ids - claimed
    if unclaimed:
        unclaimed_nicks = [ids_seen[pid] for pid in sorted(unclaimed)]
        raise MultiProjectConfigError(
            f"Project(s) not assigned to any measure: {', '.join(unclaimed_nicks)}."
        )


def _subcon_key_matches(key: str, hash_char: str, measure_mark: str) -> bool:
    norm = normalize_tag(key)
    h = (hash_char or "").strip().upper()
    if not norm or not h or norm[0] != h:
        return False
    mark = (measure_mark or "").strip().upper()
    if mark:
        return norm.startswith(h + mark)
    return bool(re.match(r"^" + re.escape(h) + r"\d+$", norm))


def _tag_matches_subcontract(tag: str, hash_char: str, measure_mark: str) -> bool:
    return _subcon_key_matches(tag, hash_char, measure_mark)


def validate_subcontracted_measures(measures: List[MeasureConfig]) -> None:
    subcontracted = [m for m in measures if m.type == "subcontracted"]
    if not subcontracted:
        return

    marks_seen: Dict[str, str] = {}
    hash_only: Dict[str, str] = {}

    for measure in subcontracted:
        key_source = (measure.key_source or "tags").strip().lower()
        if key_source not in ("tags", "description"):
            raise SubcontractedConfigError(
                f"Subcontracted measure '{measure.id}' key_source must be 'tags' or 'description'."
            )

        h = (measure.hash or "").strip()
        if len(h) != 1:
            raise SubcontractedConfigError(
                f"Subcontracted measure '{measure.id}' requires a single-character hash."
            )

        mark = (measure.measure_mark or "").strip().upper()
        if mark:
            if len(mark) != 1 or not mark.isalpha():
                raise SubcontractedConfigError(
                    f"Subcontracted measure '{measure.id}' measure mark must be a single letter."
                )
            if mark in marks_seen:
                raise SubcontractedConfigError(
                    f"Duplicate subcontracted measure mark '{mark}' "
                    f"(measures {marks_seen[mark]} and {measure.id})."
                )
            marks_seen[mark] = measure.id
        else:
            h_up = h.upper()
            if h_up in hash_only:
                raise SubcontractedConfigError(
                    f"Only one subcontracted measure without a measure mark is allowed "
                    f"per hash '{h}' (measures {hash_only[h_up]} and {measure.id})."
                )
            hash_only[h_up] = measure.id


def validate_manual_arrange_config(
    measures: List[MeasureConfig],
    multi_project: bool = False,
) -> None:
    manual_arrange = [m for m in measures if m.type == "manual_arrange"]
    if not manual_arrange:
        return

    if not multi_project:
        if len(measures) > 1:
            raise ManualArrangeConfigError(
                "Manual Arrange cannot be combined with other measures in a single-project run."
            )
        return

    ma_projects: Dict[str, str] = {}
    other_projects: Dict[str, str] = {}

    for measure in measures:
        for pid in measure.applicable_projects:
            pid = str(pid).strip()
            if not pid:
                continue
            if measure.type == "manual_arrange":
                if pid in other_projects:
                    raise ManualArrangeConfigError(
                        f"Project '{pid}' is assigned to Manual Arrange measure "
                        f"'{measure.id}' and also to measure '{other_projects[pid]}'."
                    )
                ma_projects[pid] = measure.id
            else:
                if pid in ma_projects:
                    raise ManualArrangeConfigError(
                        f"Project '{pid}' is assigned to measure '{measure.id}' "
                        f"and also to Manual Arrange measure '{ma_projects[pid]}'."
                    )
                other_projects[pid] = measure.id

    for measure in manual_arrange:
        apps = [str(p).strip() for p in measure.applicable_projects if str(p).strip()]
        if not apps:
            raise ManualArrangeConfigError(
                f"Manual Arrange measure '{measure.name or measure.id}' must select at least one project."
            )


# ---------------- Unique classification-tag discovery ----------------

def find_unique_classification_tags(
    measures: List[MeasureConfig],
) -> Dict[str, Set[str]]:
    """{measure_id: {tag, ...}} — every measure represented, even with an empty set."""
    owners: Dict[str, Set[str]] = {}
    for measure in measures:
        for raw in measure.classification_tags:
            norm = normalize_tag(raw)
            if norm:
                owners.setdefault(norm, set()).add(measure.id)

    unique_by_measure: Dict[str, Set[str]] = {m.id: set() for m in measures}
    for tag, owning_ids in owners.items():
        if len(owning_ids) == 1:
            (only_id,) = tuple(owning_ids)
            unique_by_measure[only_id].add(tag)
    return unique_by_measure


# ---------------- Classification diagnostics ----------------

UNKNOWN_MEASURE = "UNKNOWN"
REASON_MEASURE_KEYWORD = "measure_keyword"
REASON_UNIQUE_TAG = "unique_measure_tag"
REASON_SUBCONTRACTED = "subcontracted_prefix"
REASON_SOLE_PROJECT = "sole_project_owner"
REASON_MANUAL_ARRANGE = "manual_arrange_project"
REASON_UNKNOWN = "unknown"


@dataclass
class ClassificationDecision:
    photo_id: Any
    measure_id: Optional[str]  # None when Unknown
    reason: str
    matched_tags: List[str] = field(default_factory=list)


@dataclass
class ClassificationResult:
    by_measure: Dict[str, List[Any]]
    unknown: List[Any]
    decisions: List[ClassificationDecision] = field(default_factory=list)


# ---------------- Photo classification ----------------

def _eligible_measures(
    measures: List[MeasureConfig],
    photo: Any,
    multi_project: bool,
) -> List[MeasureConfig]:
    if not multi_project:
        return measures
    source = _get_source_project_id(photo)
    return [m for m in measures if source in m.applicable_projects]


def _build_sole_project_owners(measures: List[MeasureConfig]) -> Dict[str, str]:
    """project_id -> measure_id when only one measure claims that project."""
    owners: Dict[str, Set[str]] = {}
    for measure in measures:
        for pid in measure.applicable_projects:
            pid = str(pid).strip()
            if pid:
                owners.setdefault(pid, set()).add(measure.id)
    return {pid: next(iter(ids)) for pid, ids in owners.items() if len(ids) == 1}


def _build_manual_arrange_by_project(measures: List[MeasureConfig]) -> Dict[str, str]:
    """project_id -> manual_arrange measure_id."""
    owners: Dict[str, str] = {}
    for measure in measures:
        if measure.type != "manual_arrange":
            continue
        for pid in measure.applicable_projects:
            pid = str(pid).strip()
            if pid:
                owners[pid] = measure.id
    return owners


def classify_photos(
    photos: List[Any],
    measures: List[MeasureConfig],
    multi_project: bool = False,
) -> ClassificationResult:
    by_measure: Dict[str, List[Any]] = {m.id: [] for m in measures}
    unknown: List[Any] = []
    decisions: List[ClassificationDecision] = []

    # Single-project shortcut: sole manual_arrange measure gets every photo.
    if not multi_project and len(measures) == 1 and measures[0].type == "manual_arrange":
        for photo in photos:
            by_measure[measures[0].id].append(photo)
            decisions.append(ClassificationDecision(
                _get_photo_id(photo), measures[0].id, REASON_MANUAL_ARRANGE, [],
            ))
        return ClassificationResult(by_measure=by_measure, unknown=unknown, decisions=decisions)

    manual_arrange_by_project = _build_manual_arrange_by_project(measures)
    tag_classifiable = [m for m in measures if m.type != "manual_arrange"]

    keyword_owners: Dict[str, Set[str]] = {}
    for measure in tag_classifiable:
        for raw in measure.measure_keywords:
            norm = normalize_tag(raw)
            if norm:
                keyword_owners.setdefault(norm, set()).add(measure.id)

    unique_tags_by_measure = find_unique_classification_tags(tag_classifiable)
    tag_owner: Dict[str, str] = {}
    for measure_id, tags in unique_tags_by_measure.items():
        for tag in tags:
            tag_owner[tag] = measure_id

    subcontracted_measures = [m for m in tag_classifiable if m.type == "subcontracted"]
    sole_project_owners = _build_sole_project_owners(tag_classifiable) if multi_project else {}

    for photo in photos:
        photo_tags = normalize_tags(_get_tags(photo))
        photo_id = _get_photo_id(photo)
        eligible = _eligible_measures(measures, photo, multi_project)
        eligible_ids = {m.id for m in eligible}

        if multi_project and not eligible_ids:
            unknown.append(photo)
            decisions.append(ClassificationDecision(photo_id, None, REASON_UNKNOWN, []))
            continue

        # Pass 0: Manual Arrange project routing (exclusive, no tag matching)
        if multi_project:
            ma_owner = manual_arrange_by_project.get(_get_source_project_id(photo))
            if ma_owner and ma_owner in eligible_ids:
                by_measure[ma_owner].append(photo)
                decisions.append(ClassificationDecision(photo_id, ma_owner, REASON_MANUAL_ARRANGE, []))
                continue

        # Tag-based passes only consider non-manual-arrange measures
        eligible_tag_ids = {m.id for m in eligible if m.type != "manual_arrange"}

        # Pass 1: Measure Keywords
        matched_ids: Set[str] = set()
        matched_keywords: List[str] = []
        for tag in photo_tags:
            owners = keyword_owners.get(tag)
            if owners:
                matched_ids.update(owners & eligible_tag_ids)
                if owners & eligible_tag_ids:
                    matched_keywords.append(tag)

        if len(matched_ids) == 1:
            (mid,) = tuple(matched_ids)
            by_measure[mid].append(photo)
            decisions.append(ClassificationDecision(photo_id, mid, REASON_MEASURE_KEYWORD, matched_keywords))
            continue
        if len(matched_ids) > 1:
            unknown.append(photo)
            decisions.append(ClassificationDecision(photo_id, None, REASON_MEASURE_KEYWORD, matched_keywords))
            continue

        # Pass 2: Unique Classification Tags (only unresolved photos reach here)
        matched_ids = set()
        matched_unique: List[str] = []
        for tag in photo_tags:
            owner = tag_owner.get(tag)
            if owner and owner in eligible_tag_ids:
                matched_ids.add(owner)
                matched_unique.append(tag)

        if len(matched_ids) == 1:
            (mid,) = tuple(matched_ids)
            by_measure[mid].append(photo)
            decisions.append(ClassificationDecision(photo_id, mid, REASON_UNIQUE_TAG, matched_unique))
            continue
        if len(matched_ids) > 1:
            unknown.append(photo)
            decisions.append(ClassificationDecision(photo_id, None, REASON_UNIQUE_TAG, matched_unique))
            continue

        # Pass 3: Subcontracted prefix matching
        matched_sub_ids: Set[str] = set()
        matched_sub_tags: List[str] = []
        eligible_sub = [m for m in subcontracted_measures if m.id in eligible_tag_ids]
        for measure in eligible_sub:
            if (measure.key_source or "tags").lower() == "description":
                key = normalize_tag(_get_description(photo))
                if key and _subcon_key_matches(key, measure.hash, measure.measure_mark):
                    matched_sub_ids.add(measure.id)
                    matched_sub_tags.append(key)
            else:
                for tag in photo_tags:
                    if _subcon_key_matches(tag, measure.hash, measure.measure_mark):
                        matched_sub_ids.add(measure.id)
                        matched_sub_tags.append(tag)

        if len(matched_sub_ids) == 1:
            (mid,) = tuple(matched_sub_ids)
            by_measure[mid].append(photo)
            decisions.append(ClassificationDecision(photo_id, mid, REASON_SUBCONTRACTED, matched_sub_tags))
            continue
        if len(matched_sub_ids) > 1:
            unknown.append(photo)
            decisions.append(ClassificationDecision(photo_id, None, REASON_SUBCONTRACTED, matched_sub_tags))
            continue

        # Pass 4: Sole project owner (multi-project only)
        if multi_project:
            sole_owner = sole_project_owners.get(_get_source_project_id(photo))
            if sole_owner and sole_owner in eligible_tag_ids:
                by_measure[sole_owner].append(photo)
                decisions.append(ClassificationDecision(photo_id, sole_owner, REASON_SOLE_PROJECT, []))
                continue

        unknown.append(photo)
        decisions.append(ClassificationDecision(photo_id, None, REASON_UNKNOWN, matched_unique))

    return ClassificationResult(by_measure=by_measure, unknown=unknown, decisions=decisions)


# ---------------- Orchestration entry point ----------------

def run_measure_classification(
    photos: List[Any],
    measures: List[MeasureConfig],
    multi_project: bool = False,
    complete_projects: Optional[List[Dict[str, str]]] = None,
) -> ClassificationResult:
    """
    Single call site dropped into the job flow ahead of per-measure
    sorting (see web/routes/report_routes.py start_job()):

        try:
            result = run_measure_classification(all_photos, configured_measures)
        except DuplicateMeasureKeywordError as e:
            # surfaced to the caller / job as a failed run
            raise

        for measure in configured_measures:
            photos_for_measure = result.by_measure[measure.id]
            # handed off to that measure's adapter/sorter via
            # core.dataset_router.run_sort(measure.type, photos_for_measure, ...)

        # result.unknown -> photos that didn't resolve to any measure;
        # surfaced to the user rather than silently dropped.

    Validates the run's configuration (duplicate measure keywords)
    before classifying, since a duplicate keyword makes Pass 1
    unreliable for every photo that carries it.
    """
    duplicates = find_duplicate_measure_keywords(measures)
    if duplicates:
        raise DuplicateMeasureKeywordError(duplicates)

    validate_subcontracted_measures(measures)
    validate_manual_arrange_config(measures, multi_project=multi_project)

    if multi_project:
        validate_multi_project_config(measures, complete_projects or [])

    return classify_photos(photos, measures, multi_project=multi_project)