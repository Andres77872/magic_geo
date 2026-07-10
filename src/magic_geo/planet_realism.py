from __future__ import annotations

import math
from typing import Any


PLANET_PARAMETER_KEYS = (
    "radius_km",
    "gravity_g",
    "day_length_hours",
    "axial_tilt_deg",
    "orbital_eccentricity",
    "stellar_luminosity",
    "atmosphere_pressure_bar",
    "greenhouse_factor",
    "ocean_fraction_target",
    "ocean_water_inventory_km3",
    "internal_heat",
    "geological_age_ga",
)


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _planet_value(planet: Any | None, key: str, default: float) -> float:
    if planet is None:
        return default
    if isinstance(planet, dict):
        raw = planet.get(key, default)
    else:
        raw = getattr(planet, key, default)
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _score_range(value: float, target_min: float, target_max: float) -> float:
    if target_min <= value <= target_max:
        return 1.0
    if value < target_min:
        return _clamp(value / target_min) if target_min > 0.0 else 0.0
    remaining = 1.0 - target_max
    return _clamp((1.0 - value) / remaining) if remaining > 0.0 else 0.0


def _check_record(
    checks: list[dict[str, Any]],
    *,
    name: str,
    question: str,
    metric: str,
    value: float,
    target_min: float,
    target_max: float,
    evidence: dict[str, Any],
) -> None:
    rounded_value = round(_clamp(value), 6)
    checks.append(
        {
            "id": len(checks),
            "domain": "planet",
            "name": name,
            "question": question,
            "metric": metric,
            "value": rounded_value,
            "target_min": round(_clamp(target_min), 6),
            "target_max": round(_clamp(target_max), 6),
            "score": round(_score_range(rounded_value, target_min, target_max), 6),
            "passed": target_min <= rounded_value <= target_max,
            "evidence": evidence,
        }
    )


def _range_score(value: float, lower: float, upper: float, outer_lower: float, outer_upper: float) -> float:
    if lower <= value <= upper:
        return 1.0
    if value < lower:
        return _clamp((value - outer_lower) / max(1.0e-9, lower - outer_lower))
    return _clamp((outer_upper - value) / max(1.0e-9, outer_upper - upper))


def _parameter_snapshot(planet: Any | None) -> dict[str, float]:
    defaults = {
        "radius_km": 6371.0,
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
    return {
        key: round(_planet_value(planet, key, default), 6)
        for key, default in defaults.items()
    }


def enrich_world_with_planet_realism(world: dict[str, Any], planet: Any | None = None) -> dict[str, Any]:
    cells = world.get("cells", [])
    if not isinstance(cells, list) or not cells:
        return world

    parameters = _parameter_snapshot(planet)
    world["planet_parameters"] = parameters
    summary = world.setdefault("summary", {})

    temperatures = [float(cell.get("temperature_c", 0.0)) for cell in cells]
    mean_temperature = _mean(temperatures)
    liquid_temperature_fraction = (
        sum(1 for temperature in temperatures if -5.0 <= temperature <= 40.0) / len(temperatures)
    )
    surface_water_fraction = (
        sum(1 for cell in cells if bool(cell.get("is_water", False)) or bool(cell.get("is_lake", False))) / len(cells)
    )
    mean_temperature_score = _range_score(mean_temperature, -5.0, 30.0, -55.0, 70.0)
    liquid_water_temperature_index = _clamp(
        mean_temperature_score * 0.46 + liquid_temperature_fraction * 0.38 + surface_water_fraction * 0.16
    )

    gravity = max(0.0, parameters["gravity_g"])
    pressure = max(0.0, parameters["atmosphere_pressure_bar"])
    gravity_score = _range_score(gravity, 0.45, 2.2, 0.08, 4.5)
    pressure_score = _range_score(math.log10(max(pressure, 1.0e-6)), math.log10(0.1), math.log10(5.0), -4.0, 1.3)
    atmosphere_gravity_index = _clamp(gravity_score * 0.55 + pressure_score * 0.45)

    day_length = max(0.0, parameters["day_length_hours"])
    day_length_score = _range_score(day_length, 8.0, 48.0, 1.0, 120.0)
    atmospheric_cell_counts = summary.get("atmospheric_cell_counts", {})
    if not isinstance(atmospheric_cell_counts, dict):
        atmospheric_cell_counts = {}
    atmospheric_band_count = sum(1 for count in atmospheric_cell_counts.values() if int(count) > 0)
    atmospheric_band_score = _clamp(atmospheric_band_count / 4.0)
    rotation_circulation_index = _clamp(day_length_score * 0.55 + atmospheric_band_score * 0.45)

    target_ocean_fraction = _clamp(float(summary.get("target_ocean_fraction", parameters["ocean_fraction_target"])))
    ocean_fraction = _clamp(float(summary.get("ocean_fraction", 0.0)))
    target_ocean_volume = max(0.0, parameters["ocean_water_inventory_km3"])
    actual_ocean_volume = max(0.0, float(summary.get("ocean_volume_km3", 0.0)))
    water_body_counts = summary.get("water_body_counts", {})
    if not isinstance(water_body_counts, dict):
        water_body_counts = {}
    water_body_diversity = sum(1 for name, count in water_body_counts.items() if name != "land" and int(count) > 0)
    ocean_match_score = _clamp(1.0 - abs(ocean_fraction - target_ocean_fraction) / 0.25)
    if target_ocean_fraction < 0.05:
        ocean_match_score = max(ocean_match_score, _clamp(1.0 - ocean_fraction / 0.1))
    if target_ocean_volume > 0.0:
        ocean_volume_match_score = _clamp(
            1.0 - abs(actual_ocean_volume - target_ocean_volume) / target_ocean_volume
        )
    else:
        ocean_volume_match_score = _clamp(1.0 - actual_ocean_volume / 1_000_000.0)
    water_diversity_score = _clamp(water_body_diversity / 3.0)
    surface_water_inventory_index = _clamp(
        ocean_volume_match_score * 0.62 + ocean_match_score * 0.20 + water_diversity_score * 0.18
    )

    checks: list[dict[str, Any]] = []
    _check_record(
        checks,
        name="liquid_water_temperature_window",
        question="Does the global temperature regime allow liquid water?",
        metric="temperature_and_surface_water_liquid_water_index",
        value=liquid_water_temperature_index,
        target_min=0.55,
        target_max=1.0,
        evidence={
            "global_mean_temperature_c": round(mean_temperature, 6),
            "liquid_temperature_cell_fraction": round(liquid_temperature_fraction, 6),
            "surface_water_cell_fraction": round(surface_water_fraction, 6),
            "mean_temperature_window_score": round(mean_temperature_score, 6),
        },
    )
    _check_record(
        checks,
        name="atmosphere_gravity_stability",
        question="Does gravity allow a stable atmosphere for the configured pressure?",
        metric="gravity_pressure_stability_index",
        value=atmosphere_gravity_index,
        target_min=0.6,
        target_max=1.0,
        evidence={
            "gravity_g": round(gravity, 6),
            "atmosphere_pressure_bar": round(pressure, 6),
            "gravity_window_score": round(gravity_score, 6),
            "pressure_window_score": round(pressure_score, 6),
        },
    )
    _check_record(
        checks,
        name="rotation_circulation_plausibility",
        question="Does rotation allow plausible atmospheric circulation cells?",
        metric="day_length_and_atmospheric_band_plausibility_index",
        value=rotation_circulation_index,
        target_min=0.65,
        target_max=1.0,
        evidence={
            "day_length_hours": round(day_length, 6),
            "day_length_window_score": round(day_length_score, 6),
            "atmospheric_band_count": atmospheric_band_count,
            "atmospheric_cell_counts": dict(sorted((str(k), int(v)) for k, v in atmospheric_cell_counts.items())),
        },
    )
    _check_record(
        checks,
        name="surface_water_inventory",
        question="Does the water inventory allow oceans, seas, lakes, or a coherent arid world?",
        metric="surface_water_inventory_match_index",
        value=surface_water_inventory_index,
        target_min=0.7,
        target_max=1.0,
        evidence={
            "target_ocean_fraction": round(target_ocean_fraction, 6),
            "actual_ocean_fraction": round(ocean_fraction, 6),
            "target_ocean_water_inventory_km3": round(target_ocean_volume, 6),
            "actual_ocean_volume_km3": round(actual_ocean_volume, 6),
            "ocean_volume_match_score": round(ocean_volume_match_score, 6),
            "surface_water_cell_fraction": round(surface_water_fraction, 6),
            "water_body_diversity": water_body_diversity,
            "water_body_counts": dict(sorted((str(k), int(v)) for k, v in water_body_counts.items())),
        },
    )

    pass_count = sum(1 for check in checks if check["passed"])
    score_sum = sum(float(check["score"]) for check in checks)
    world["planet_realism_checks"] = checks
    summary["global_liquid_water_temperature_index"] = round(liquid_water_temperature_index, 6)
    summary["atmosphere_gravity_stability_index"] = round(atmosphere_gravity_index, 6)
    summary["rotation_circulation_plausibility_index"] = round(rotation_circulation_index, 6)
    summary["surface_water_inventory_index"] = round(surface_water_inventory_index, 6)
    summary["planet_realism_check_count"] = len(checks)
    summary["planet_realism_pass_count"] = pass_count
    summary["planet_realism_pass_fraction"] = round(pass_count / len(checks), 6) if checks else 0.0
    summary["mean_planet_realism_score"] = round(score_sum / len(checks), 6) if checks else 0.0
    return world
