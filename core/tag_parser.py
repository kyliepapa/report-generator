"""
Tag parsing.

Pure "given a photo's cleaned tag list, extract meaning" functions.
Genuinely dataset-agnostic -- the letter/number/combo token
classification in parse_bldg_unit() doesn't know or care what domain
it's running in. Only reads core.config for LABEL_FORMAT and the
special-rooms state.

Relocated from newreport.py with NO logic changes. One piece of dead
code was dropped: a commented-out older version of parse_bldg_unit()
(dated "commented out on April 1, 2026" in the original file) was not
carried forward -- it was inert and superseded by the live function
below.
"""

import re

import core.config as config


def parse_bldg_unit(tags_clean):
    """
    Extract (bldg, unit) from a photo's cleaned (uppercased, stripped)
    tag list. Behavior is unchanged from the original -- see the
    label_format branches below for the "123" / "123 A" / "A 123"
    conventions.
    """
    bldg = None
    unit = None
    used_values = set()

    # --- Explicit building ---
    for t in tags_clean:
        b_match = re.search(r'\b(?:BLDG|BUILDING)\s*([A-Z0-9]{1,4})\b', t, re.IGNORECASE)
        if b_match:
            val = b_match.group(1).upper()
            bldg = val.zfill(2) if val.isdigit() else val
            used_values.add(val)

    # --- Explicit unit ---
    for t in tags_clean:
        u_match = re.search(r'\bUNIT\s*([A-Z0-9]{1,4})\b', t, re.IGNORECASE)
        if u_match:
            val = u_match.group(1).upper()
            unit = val.zfill(3) if val.isdigit() else val
            used_values.add(val)

    if bldg and unit:
        return bldg, unit

    # --- Token classification ---
    letters = []
    numbers = []
    combos = []

    for t in tags_clean:
        t = t.upper()
        if t in used_values:
            continue

        if re.fullmatch(r'[A-Z]', t):
            letters.append(t)

        elif re.fullmatch(r'\d{1,4}', t):
            numbers.append(t.zfill(3))

        elif re.fullmatch(r'[A-Z]\d{1,4}', t) or re.fullmatch(r'\d{1,4}[A-Z]', t):
            combos.append(t)

    # --- Helper: remove used number ---
    def remaining_numbers(exclude=None):
        return [n for n in numbers if n != exclude]

    # --- Format logic ---
    label_format = config.LABEL_FORMAT

    if label_format == "123":
        if unit:
            return None, unit
        if combos:
            return None, combos[0]
        if letters:
            return None, letters[0]
        if numbers:
            return None, numbers[0]
        return None, "UNASSIGNED"

    elif label_format == "123 A":
        # Building prefers largest number
        if not bldg and numbers:
            bldg = max(numbers)

        # Unit priority: combo > letter > remaining number
        if not unit:
            if combos:
                unit = combos[0]
            elif letters:
                unit = letters[0]
            else:
                rem = remaining_numbers(bldg)
                if rem:
                    unit = min(rem)

    elif label_format == "A 123":
        # Building prefers letter
        if not bldg and letters:
            bldg = letters[0]

        # Unit priority: combo > number > remaining letter
        if not unit:
            if combos:
                unit = combos[0]
            elif numbers:
                unit = min(numbers)
            else:
                rem_letters = [l for l in letters if l != bldg]
                if rem_letters:
                    unit = rem_letters[0]

    # --- All-number fallback ---
    if (label_format in ["123 A", "A 123"]) and not letters and not combos and len(numbers) >= 2:
        sorted_nums = sorted(numbers)
        unit = sorted_nums[0]
        bldg = sorted_nums[-1]

    # --- Defaults ---
    if not unit:
        unit = "UNASSIGNED"
    if not bldg:
        bldg = "00"

    return bldg, unit


def parse_serial_tags(serial_tag) -> list:
    """Parse serial_tag from a comma-separated string or list."""
    if isinstance(serial_tag, list):
        return [str(x).strip() for x in serial_tag if str(x).strip()]
    if isinstance(serial_tag, str):
        return [x.strip() for x in serial_tag.split(",") if x.strip()]
    return []


def is_unassigned_photo(bath_idx, phase_idx):
    """
    Unchanged. Name kept as "bath_idx" for the parameter since it's
    called positionally from sort_engine.py/organizer.py with a
    sub-unit index -- renaming the parameter alone (with no behavior
    change) wasn't worth touching every call site in this pass.
    """
    return bath_idx == -1 and phase_idx == -1


def get_special_room_match(tags_clean):
    """
    Was hardcoded to read the module globals SPECIAL_ROOMS_NORMALIZED
    and special_rooms_input directly. Now reads them off core.config,
    same values, same matching logic.
    """
    for tag in tags_clean:
        tag_up = tag.upper()
        for i, room in enumerate(config.SPECIAL_ROOMS_NORMALIZED):
            if room == tag_up or room in tag_up:
                return config.SPECIAL_ROOMS_INPUT[i].title()
    return None