"""Public validation of declared groundwater versions and the final source budget."""

from __future__ import annotations

import math
from typing import Any

from .natural_groundwater_validation import (
    NaturalGroundwaterError,
    natural_groundwater_model_version,
    validate_natural_groundwater_flow,
)


def groundwater_validation_mode(world: dict[str, Any]) -> tuple[bool, list[str]]:
    """Select an exact, compatible declaration without rewriting its payload."""
    try:
        aquifer_version = natural_groundwater_model_version(world, "aquifer")
        flow_version = natural_groundwater_model_version(world, "groundwater")
        if aquifer_version != flow_version:
            return False, ["natural groundwater: aquifer and flow declarations must match"]
        return flow_version == 2, []
    except (NaturalGroundwaterError, TypeError, ValueError, KeyError, OverflowError) as exc:
        return False, [str(exc)]


def validate_groundwater_source_summary(world: dict[str, Any]) -> list[str]:
    """Require the final hydrology summary to mirror the audited recharge source.

    Aquifer generation runs before the hydrology summary is refreshed. This is
    therefore a public-output check, deliberately absent from producer preflight.
    """
    summary = world.get("summary", {})
    if not isinstance(summary, dict):
        return ["natural groundwater: final hydrology summary must be an object"]
    values = [summary.get(key) for key in (
        "total_infiltration_km3_y",
        "total_groundwater_recharge_source_infiltration_km3_y",
    )]
    try:
        finite = all(type(value) in (int, float) and math.isfinite(value) for value in values)
    except OverflowError:
        finite = False
    if not finite:
        return ["natural groundwater: final infiltration source totals must be finite numeric"]
    infiltration, source = values
    allowance = max(1.1e-6, 8 * math.ulp(source))
    if abs(infiltration - source) > allowance:
        return ["natural groundwater: final infiltration summary does not match the recharge source"]
    return []


def validate_public_natural_groundwater(world: dict[str, Any]) -> tuple[bool, list[str]]:
    """Replay natural v2 before eager public consumers; retain the legacy path."""
    natural, errors = groundwater_validation_mode(world)
    if errors or not natural:
        return natural, errors
    errors = validate_natural_groundwater_flow(world)
    if not errors:
        errors = validate_groundwater_source_summary(world)
    return natural, errors
