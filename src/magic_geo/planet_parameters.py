from __future__ import annotations

import math
from typing import Any


EARTH_RADIUS_KM = 6371.0
EARTH_STANDARD_GRAVITY_M_S2 = 9.80665
# Preserve the ice-flow model's historical Earth baseline while still scaling
# it by configured relative gravity.
LEGACY_ICE_FLOW_EARTH_GRAVITY_M_S2 = 9.81

PLANET_PARAMETER_DEFAULTS: dict[str, float] = {
    "radius_km": EARTH_RADIUS_KM,
    "gravity_g": 1.0,
    "day_length_hours": 24.0,
    "axial_tilt_deg": 23.5,
    "orbital_eccentricity": 0.016,
    "stellar_luminosity": 1.0,
    "atmosphere_pressure_bar": 1.0,
    "greenhouse_factor": 1.0,
    "ocean_fraction_target": 0.70,
    "ocean_water_inventory_km3": 1_338_000_000.0,
    "internal_heat": 1.0,
    "geological_age_ga": 4.5,
}


def _value(source: Any | None, key: str, default: float) -> float:
    if source is None:
        return default
    if isinstance(source, dict):
        raw = source.get(key, default)
    else:
        raw = getattr(source, key, default)
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return default
    return value if math.isfinite(value) else default


def planet_parameter_snapshot(planet: Any | None = None) -> dict[str, float]:
    """Return the stable top-level planet snapshot used by Python enrichers."""

    return {
        key: round(_value(planet, key, default), 6)
        for key, default in PLANET_PARAMETER_DEFAULTS.items()
    }


def planet_radius_km(world: dict[str, Any]) -> float:
    """Read configured radius, retaining Earth scale for legacy payloads."""

    parameters = world.get("planet_parameters", {})
    radius = _value(parameters if isinstance(parameters, dict) else None, "radius_km", EARTH_RADIUS_KM)
    return radius if radius > 0.0 else EARTH_RADIUS_KM


def planet_gravity_g(world: dict[str, Any]) -> float:
    """Read configured relative surface gravity with a legacy Earth default."""

    parameters = world.get("planet_parameters", {})
    gravity = _value(parameters if isinstance(parameters, dict) else None, "gravity_g", 1.0)
    return gravity if gravity > 0.0 else 1.0


def surface_gravity_m_s2(
    world: dict[str, Any],
    *,
    earth_reference_m_s2: float = EARTH_STANDARD_GRAVITY_M_S2,
) -> float:
    return planet_gravity_g(world) * earth_reference_m_s2
