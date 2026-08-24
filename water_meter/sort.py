"""
datasets/water_meter/sort.py

Your water-meter draft, relocated with one change: reads "tag_names"
(program-wide photo contract, same as plumbing) instead of the
draft's original "tags" key, and normalizes tags the same way
plumbing's tags_clean does (stripped, uppercased) before matching.
techs/types/phases/serial_tag are uppercased on the way in too, so
matching is case-insensitive like the rest of the program.
"""

from collections import defaultdict


def sort_photos(techs, types, phases, serial_tag, photos):
    """
    Sort photos into Units and then order them within each Unit.

    Parameters
    ----------
    techs : list[str]
        Tags identifying technicians/installers.

    types : list[str]
        Two type tags:
            types[0]
            types[1]

    phases : list[str]
        Two phase tags:
            phases[0]
            phases[1]

    serial_tag : str
        Tag identifying a serial-number photo.

    photos : list[dict]
        Each photo should contain a "tag_names" key whose value is a
        list of strings (program-wide photo contract, same as
        plumbing/lighting).

        Example:
            {
                "id": "photo_001",
                "tag_names": ["101", "John", "Fixture", "Phase 1"]
            }

    Returns
    -------
    dict
        {
            "units": {
                apartment_number: [sorted photos]
            },
            "untagged": [photos missing an apartment tag],
            "errors": {
                "missing_unit_tag": [photos],
                "missing_specifier_tags": [photos],
                "units_with_missing_or_duplicated_photos": [unit numbers]
            }
        }
    """

    # --------------------------------------------------
    # INPUT VALIDATION
    # --------------------------------------------------

    if len(types) < 2:
        raise ValueError("types must contain at least two values.")

    if len(phases) < 2:
        raise ValueError("phases must contain at least two values.")

    # --------------------------------------------------
    # NORMALIZE INPUTS
    # (stripped/uppercased, same convention as plumbing's tags_clean)
    # --------------------------------------------------

    techs = [t.strip().upper() for t in techs]
    types = [t.strip().upper() for t in types]
    phases = [p.strip().upper() for p in phases]
    serial_tag = serial_tag.strip().upper()

    # --------------------------------------------------
    # INITIALIZE STORAGE
    # --------------------------------------------------

    units = defaultdict(list)
    untagged = []

    errors = {
        "missing_unit_tag": [],
        "missing_specifier_tags": [],
        "units_with_missing_or_duplicated_photos": []
    }

    # Convert techs to a set for faster lookup.
    tech_tags = set(techs)

    # --------------------------------------------------
    # SORT PHOTOS INTO UNITS
    # --------------------------------------------------

    for photo in photos:

        tags = [t.strip().upper() for t in photo.get("tag_names", [])]

        # Find the numeric tag (apartment/unit number).
        apartment_tag = next(
            (tag for tag in tags if str(tag).isdigit()),
            None
        )

        # No apartment tag.
        if apartment_tag is None:
            untagged.append(photo)
            errors["missing_unit_tag"].append(photo)
            continue

        # Store the apartment/unit number on the photo.
        photo["apt"] = apartment_tag

        # Add the photo to its Unit.
        units[apartment_tag].append(photo)

    # --------------------------------------------------
    # PROCESS EACH UNIT
    # --------------------------------------------------

    for apartment, unit_photos in units.items():

        for photo in unit_photos:

            tags = [t.strip().upper() for t in photo.get("tag_names", [])]

            # ------------------------------------------
            # DETERMINE TAG ARCHITECTURE
            # ------------------------------------------

            has_tech = any(tag in tech_tags for tag in tags)
            has_sn = serial_tag in tags

            has_type_0 = types[0] in tags
            has_type_1 = types[1] in tags

            has_phase_0 = phases[0] in tags
            has_phase_1 = phases[1] in tags

            # ------------------------------------------
            # ASSIGN PHOTO DESIGNATION
            # ------------------------------------------

            if has_type_0 and has_phase_0:
                designation = 2

            elif has_type_1 and has_phase_0:
                designation = 3

            elif has_type_1 and has_phase_1:
                designation = 5

            elif has_type_0 and has_phase_1:
                designation = 6

            elif has_tech and not has_sn:
                designation = 1

            elif has_sn and not has_tech:
                designation = 4

            else:
                designation = None

                errors["missing_specifier_tags"].append(photo)

            # Store designation on photo.
            photo["designation"] = designation

        # ----------------------------------------------
        # CHECK FOR MISSING / DUPLICATED DESIGNATIONS
        # ----------------------------------------------

        designation_counts = {
            designation: 0
            for designation in range(1, 7)
        }

        for photo in unit_photos:

            designation = photo["designation"]

            # Ignore photos with no designation.
            if designation is None:
                continue

            designation_counts[designation] += 1

        unit_has_issue = False

        for designation in range(1, 7):

            count = designation_counts[designation]

            # Missing designation.
            if count == 0:
                unit_has_issue = True

            # Duplicated designation.
            elif count > 1:
                unit_has_issue = True

        if unit_has_issue:
            errors[
                "units_with_missing_or_duplicated_photos"
            ].append(apartment)

        # ----------------------------------------------
        # SORT PHOTOS WITHIN UNIT
        # ----------------------------------------------

        # Designations 1-6 come first.
        # Photos without a designation go at the end.
        unit_photos.sort(
            key=lambda photo: (
                photo["designation"]
                if photo["designation"] is not None
                else float("inf")
            )
        )

    # --------------------------------------------------
    # RETURN RESULTS
    # --------------------------------------------------

    return {
        "units": dict(units),
        "untagged": untagged,
        "errors": errors
    }