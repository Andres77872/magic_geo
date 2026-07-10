from __future__ import annotations

from typing import Any


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _score_range(value: float, target_min: float, target_max: float) -> float:
    if target_min <= value <= target_max:
        return 1.0
    width = max(1.0e-9, target_max - target_min)
    distance = target_min - value if value < target_min else value - target_max
    return _clamp(1.0 - distance / width)


def _temperature_range_c(cell: dict[str, Any]) -> float:
    values = cell.get("temperature_monthly_c", [])
    if isinstance(values, list) and values:
        temperatures = [float(value) for value in values]
        return max(temperatures) - min(temperatures)
    return 0.0


def _is_coastal_land(cell: dict[str, Any], cells_by_id: dict[int, dict[str, Any]]) -> bool:
    if bool(cell.get("is_water", False)):
        return False
    return any(
        bool(cells_by_id[int(neighbor_id)].get("is_water", False))
        for neighbor_id in cell.get("neighbors", [])
        if int(neighbor_id) in cells_by_id
    )


def _humidity_index(cell: dict[str, Any]) -> float:
    precipitation = _clamp(float(cell.get("precipitation_mm_y", 0.0)) / 900.0)
    transport = _clamp(float(cell.get("humidity_transport_index", 0.0)))
    advected = _clamp(float(cell.get("advected_moisture_factor", 0.0)))
    return _clamp(precipitation * 0.55 + transport * 0.25 + advected * 0.20)


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
    value = _clamp(value)
    score = _score_range(value, target_min, target_max)
    checks.append(
        {
            "id": len(checks),
            "domain": "climate",
            "name": name,
            "question": question,
            "metric": metric,
            "value": round(value, 6),
            "target_min": round(target_min, 6),
            "target_max": round(target_max, 6),
            "score": round(score, 6),
            "passed": target_min <= value <= target_max,
            "evidence": evidence,
        }
    )


def enrich_world_with_climate_realism(world: dict[str, Any]) -> dict[str, Any]:
    cells = world.get("cells", [])
    if not isinstance(cells, list) or not cells:
        return world

    cells_by_id = {int(cell.get("id", -1)): cell for cell in cells}
    land_cells = [cell for cell in cells if not bool(cell.get("is_water", False))]
    subtropical_land = [cell for cell in land_cells if 20.0 <= abs(float(cell.get("lat_deg", 0.0))) <= 35.0]
    equatorial_land = [cell for cell in land_cells if abs(float(cell.get("lat_deg", 0.0))) <= 12.0]
    midlatitude_land = [cell for cell in land_cells if 40.0 <= abs(float(cell.get("lat_deg", 0.0))) <= 60.0]
    reference_precipitation = max(
        1.0,
        _mean([float(cell.get("precipitation_mm_y", 0.0)) for cell in equatorial_land + midlatitude_land]),
    )
    subtropical_precipitation = _mean(
        [float(cell.get("precipitation_mm_y", 0.0)) for cell in subtropical_land]
    )
    subtropical_dry_belt = (
        _clamp(1.0 - subtropical_precipitation / reference_precipitation)
        if subtropical_land and (equatorial_land or midlatitude_land)
        else 1.0
    )

    equatorial_ocean_influenced = [
        cell
        for cell in cells
        if abs(float(cell.get("lat_deg", 0.0))) <= 12.0
        and (
            bool(cell.get("is_water", False))
            or float(cell.get("upwind_ocean_fetch_km", 0.0)) > 500.0
            or any(
                bool(cells_by_id[int(neighbor_id)].get("is_water", False))
                for neighbor_id in cell.get("neighbors", [])
                if int(neighbor_id) in cells_by_id
            )
        )
    ]
    equatorial_humidity = (
        _mean([_humidity_index(cell) for cell in equatorial_ocean_influenced])
        if equatorial_ocean_influenced
        else 1.0
    )

    land_precipitation_mean = _mean([float(cell.get("precipitation_mm_y", 0.0)) for cell in land_cells])
    rain_shadow_cells = [
        cell
        for cell in land_cells
        if float(cell.get("rain_shadow_factor", 1.0)) <= 0.90
    ]
    rain_shadow_dry_fraction = (
        sum(
            1
            for cell in rain_shadow_cells
            if float(cell.get("precipitation_mm_y", 0.0)) <= land_precipitation_mean
            or float(cell.get("seasonal_aridity_index", 0.0)) >= 0.35
        )
        / len(rain_shadow_cells)
        if rain_shadow_cells
        else 1.0
    )

    coastal_land = [cell for cell in land_cells if _is_coastal_land(cell, cells_by_id)]
    interior_land = [cell for cell in land_cells if not _is_coastal_land(cell, cells_by_id)]
    interior_temperature_range = _mean([_temperature_range_c(cell) for cell in interior_land])
    coastal_temperature_range = _mean([_temperature_range_c(cell) for cell in coastal_land])
    continentality_temperature_range = (
        _clamp(0.5 + (interior_temperature_range - coastal_temperature_range) / 20.0)
        if interior_land and coastal_land
        else 1.0
    )

    cold_current_coasts = [
        cell
        for cell in coastal_land
        if float(cell.get("ocean_current_temperature_c", 0.0)) <= -0.25
    ]
    warm_current_coasts = [
        cell
        for cell in coastal_land
        if float(cell.get("ocean_current_temperature_c", 0.0)) >= 0.25
    ]
    cold_current_moisture = _mean([float(cell.get("ocean_current_moisture_factor", 1.0)) for cell in cold_current_coasts])
    warm_current_moisture = _mean([float(cell.get("ocean_current_moisture_factor", 1.0)) for cell in warm_current_coasts])
    current_moisture_advantage = warm_current_moisture - cold_current_moisture
    cold_current_drying = (
        _clamp(current_moisture_advantage / 0.12)
        if cold_current_coasts and warm_current_coasts
        else 1.0
    )
    cold_current_temperature_range = _mean([_temperature_range_c(cell) for cell in cold_current_coasts])
    warm_current_temperature_range = _mean([_temperature_range_c(cell) for cell in warm_current_coasts])
    warm_current_range_reduction = cold_current_temperature_range - warm_current_temperature_range
    warm_current_moderation = (
        _clamp(_clamp(current_moisture_advantage / 0.12) * 0.5 + _clamp(warm_current_range_reduction / 6.0) * 0.5)
        if cold_current_coasts and warm_current_coasts
        else 1.0
    )

    checks: list[dict[str, Any]] = []
    _check_record(
        checks,
        name="subtropical_dry_belt",
        question="Are there relatively dry belts near 30 degrees latitude?",
        metric="subtropical_precipitation_deficit_index",
        value=subtropical_dry_belt,
        target_min=0.15,
        target_max=1.0,
        evidence={
            "subtropical_land_cell_count": len(subtropical_land),
            "reference_land_cell_count": len(equatorial_land) + len(midlatitude_land),
            "mean_subtropical_precipitation_mm_y": round(subtropical_precipitation, 6),
            "reference_precipitation_mm_y": round(reference_precipitation, 6),
        },
    )
    _check_record(
        checks,
        name="equatorial_ocean_humidity",
        question="Are ocean-influenced equatorial cells humid when oceans exist?",
        metric="equatorial_ocean_humidity_index",
        value=equatorial_humidity,
        target_min=0.55,
        target_max=1.0,
        evidence={
            "equatorial_ocean_influenced_cell_count": len(equatorial_ocean_influenced),
            "mean_equatorial_precipitation_mm_y": round(
                _mean([float(cell.get("precipitation_mm_y", 0.0)) for cell in equatorial_ocean_influenced]),
                6,
            ),
        },
    )
    _check_record(
        checks,
        name="orographic_rain_shadow",
        question="Do rain-shadow cells tend to be dry relative to generated land climate?",
        metric="fraction_rain_shadow_cells_drier_than_land_mean",
        value=rain_shadow_dry_fraction,
        target_min=0.45,
        target_max=1.0,
        evidence={
            "rain_shadow_candidate_cell_count": len(rain_shadow_cells),
            "mean_land_precipitation_mm_y": round(land_precipitation_mean, 6),
        },
    )
    _check_record(
        checks,
        name="continental_interior_extremes",
        question="Are continental interiors more seasonally extreme than maritime margins?",
        metric="continentality_temperature_range_index",
        value=continentality_temperature_range,
        target_min=0.40,
        target_max=1.0,
        evidence={
            "interior_land_cell_count": len(interior_land),
            "coastal_land_cell_count": len(coastal_land),
            "mean_interior_temperature_range_c": round(interior_temperature_range, 6),
            "mean_coastal_temperature_range_c": round(coastal_temperature_range, 6),
        },
    )
    _check_record(
        checks,
        name="cold_current_coastal_drying",
        question="Do cold currents reduce coastal moisture availability?",
        metric="cold_current_moisture_deficit_index",
        value=cold_current_drying,
        target_min=0.20,
        target_max=1.0,
        evidence={
            "cold_current_coastal_cell_count": len(cold_current_coasts),
            "warm_current_coastal_cell_count": len(warm_current_coasts),
            "mean_cold_current_moisture_factor": round(cold_current_moisture, 6),
            "mean_warm_current_moisture_factor": round(warm_current_moisture, 6),
        },
    )
    _check_record(
        checks,
        name="warm_current_climate_moderation",
        question="Do warm currents soften coastal climates and raise moisture availability?",
        metric="warm_current_moderation_index",
        value=warm_current_moderation,
        target_min=0.20,
        target_max=1.0,
        evidence={
            "cold_current_coastal_cell_count": len(cold_current_coasts),
            "warm_current_coastal_cell_count": len(warm_current_coasts),
            "temperature_range_reduction_c": round(warm_current_range_reduction, 6),
            "moisture_factor_advantage": round(current_moisture_advantage, 6),
        },
    )

    summary = world.setdefault("summary", {})
    pass_count = sum(1 for check in checks if bool(check["passed"]))
    score_sum = sum(float(check["score"]) for check in checks)
    world["climate_realism_checks"] = checks
    summary["subtropical_dry_belt_index"] = round(subtropical_dry_belt, 6)
    summary["equatorial_ocean_humidity_index"] = round(equatorial_humidity, 6)
    summary["orographic_rain_shadow_index"] = round(rain_shadow_dry_fraction, 6)
    summary["continentality_temperature_range_index"] = round(continentality_temperature_range, 6)
    summary["cold_current_coastal_drying_index"] = round(cold_current_drying, 6)
    summary["warm_current_moderation_index"] = round(warm_current_moderation, 6)
    summary["climate_realism_check_count"] = len(checks)
    summary["climate_realism_pass_count"] = pass_count
    summary["climate_realism_pass_fraction"] = round(pass_count / len(checks), 6) if checks else 0.0
    summary["mean_climate_realism_score"] = round(score_sum / len(checks), 6) if checks else 0.0
    return world
