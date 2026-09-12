"""Public validation of the complete declared natural water diagnostic chain."""

from __future__ import annotations

from typing import Any

from .groundwater_validation_dispatch import (
    groundwater_validation_mode,
    validate_groundwater_source_summary,
)
from .natural_channel_validation import (
    natural_downstream_model_version,
    validate_natural_river_hydraulics,
)
from .natural_karst_validation import validate_natural_karst_diagnostics


def validate_public_natural_water_chain(world: dict[str, Any]) -> tuple[bool, list[str]]:
    """Audit actual matching parents before public consumers parse numeric fields.

    The hydraulic audit includes channel, groundwater and aquifer replay. Karst
    has its own aquifer dependency. Historical outputs retain the existing
    public numerical checks after exact declaration selection.
    """
    natural, errors = groundwater_validation_mode(world)
    if errors:
        return natural, errors
    try:
        expected_version = 2 if natural else 1
        for stage in ("channel", "hydraulics", "karst"):
            if natural_downstream_model_version(world, stage) != expected_version:
                return natural, [f"natural water: {stage} and groundwater versions must match"]
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        return natural, [str(exc)[:600] or "natural water: malformed model declaration"]
    if not natural:
        return False, []
    for validate in (
        validate_natural_river_hydraulics,
        validate_natural_karst_diagnostics,
        validate_groundwater_source_summary,
    ):
        errors = validate(world)
        if errors:
            return True, errors
    return True, []
