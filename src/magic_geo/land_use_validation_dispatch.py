"""Public full-world boundary for independently versioned land-use outputs."""

from __future__ import annotations

from typing import Any

from .land_use_availability_validation import (
    land_use_model_version,
    validate_land_use_availability,
)


def validate_public_land_use(world: dict[str, Any]) -> tuple[bool, list[str]]:
    """Require a published model before eager full-world numeric consumers.

    Exact v1 keeps the existing public numerical/record checks. Exact v2 is
    independently replayed, including availability and raw candidate thresholds.
    Geography-only validation does not require this human stage. Absence here is
    not the producer's first-call policy: a full output must declare its model.
    """
    try:
        version = land_use_model_version(world)
        if "land_use_zone_model" not in world:
            return False, ["land use availability: published land_use_zone_model required"]
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        return False, [str(exc)[:600] or "land use availability: malformed model declaration"]
    if version == 1:
        return False, []
    return True, validate_land_use_availability(world)
