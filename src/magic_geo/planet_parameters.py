from __future__ import annotations

import math
from typing import Any


EARTH_RADIUS_KM = 6371.0
EARTH_STANDARD_GRAVITY_M_S2 = 9.80665

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
        key: _value(planet, key, default)
        for key, default in PLANET_PARAMETER_DEFAULTS.items()
    }


def _positive_world_parameter(world: dict[str, Any], key: str) -> float:
    if not isinstance(world, dict):
        raise ValueError("world must be an object")
    if "planet_parameters" not in world:
        raise ValueError("world must provide planet_parameters")
    parameters = world["planet_parameters"]
    if not isinstance(parameters, dict):
        raise ValueError("planet_parameters must be an object")
    if key not in parameters:
        raise ValueError(f"planet_parameters.{key} is required")
    raw = parameters[key]
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise ValueError(f"planet_parameters.{key} must be numeric")
    try:
        value = float(raw)
    except OverflowError as exc:
        raise ValueError(
            f"planet_parameters.{key} must be finite and positive"
        ) from exc
    if not math.isfinite(value) or value <= 0.0:
        raise ValueError(f"planet_parameters.{key} must be finite and positive")
    return value


def planet_radius_km(world: dict[str, Any]) -> float:
    """Read the required finite, positive configured planet radius."""

    return _positive_world_parameter(world, "radius_km")


def planet_gravity_g(world: dict[str, Any]) -> float:
    """Read the required finite, positive relative surface gravity."""

    return _positive_world_parameter(world, "gravity_g")


def surface_gravity_m_s2(
    world: dict[str, Any],
    *,
    earth_reference_m_s2: float = EARTH_STANDARD_GRAVITY_M_S2,
) -> float:
    return planet_gravity_g(world) * earth_reference_m_s2
