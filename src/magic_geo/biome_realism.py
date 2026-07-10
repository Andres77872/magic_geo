from __future__ import annotations

from typing import Any


FOREST_BIOMES = {
    "boreal_forest",
    "temperate_forest",
    "tropical_rainforest",
    "tropical_seasonal_forest",
}
DESERT_BIOMES = {"cold_desert", "hot_desert"}
TUNDRA_BIOMES = {"tundra", "alpine"}


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


def _aridity_ratio(cell: dict[str, Any]) -> float:
    pet = max(1.0, float(cell.get("potential_evapotranspiration_mm_y", 0.0)))
    return float(cell.get("precipitation_mm_y", 0.0)) / pet


def _deficit_index(cell: dict[str, Any]) -> float:
    pet = max(1.0, float(cell.get("potential_evapotranspiration_mm_y", 0.0)))
    return _clamp(float(cell.get("climatic_water_deficit_mm_y", 0.0)) / pet)


def _is_coastal_land(cell: dict[str, Any], cells_by_id: dict[int, dict[str, Any]]) -> bool:
    if bool(cell.get("is_water", False)):
        return False
    return any(
        bool(cells_by_id[int(neighbor_id)].get("is_water", False))
        for neighbor_id in cell.get("neighbors", [])
        if int(neighbor_id) in cells_by_id
    )


def _has_water_availability(cell: dict[str, Any]) -> bool:
    return (
        float(cell.get("precipitation_mm_y", 0.0)) >= 600.0
        or float(cell.get("climatic_water_surplus_mm_y", 0.0)) > 0.0
        or float(cell.get("soil_moisture_index", 0.0)) >= 0.35
    ) and _deficit_index(cell) <= 0.55


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
            "domain": "biomes",
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


def enrich_world_with_biome_realism(world: dict[str, Any]) -> dict[str, Any]:
    cells = world.get("cells", [])
    if not isinstance(cells, list) or not cells:
        return world

    cells_by_id = {int(cell.get("id", index)): cell for index, cell in enumerate(cells)}
    land_cells = [cell for cell in cells if not bool(cell.get("is_water", False))]
    desert_cells = [cell for cell in land_cells if str(cell.get("biome", "")) in DESERT_BIOMES]
    forest_cells = [cell for cell in land_cells if str(cell.get("biome", "")) in FOREST_BIOMES]
    tundra_cells = [cell for cell in land_cells if str(cell.get("biome", "")) in TUNDRA_BIOMES]
    savanna_cells = [cell for cell in land_cells if str(cell.get("biome", "")) == "savanna"]
    mangrove_cells = [
        cell
        for cell in land_cells
        if (
            str(cell.get("biome", "")) == "mangrove"
            or str(cell.get("landform", "")) == "mangrove"
            or str(cell.get("biome_ecotone_type", "")) == "mangrove"
        )
    ]
    warm_wet_coastal_wetlands = [
        cell
        for cell in land_cells
        if str(cell.get("biome", "")) == "wetland"
        and _is_coastal_land(cell, cells_by_id)
        and float(cell.get("temperature_c", 0.0)) >= 18.0
        and (
            float(cell.get("precipitation_mm_y", 0.0)) >= 900.0
            or float(cell.get("soil_moisture_index", 0.0)) >= 0.65
        )
    ]

    desert_water_limited = [
        cell
        for cell in desert_cells
        if (
            float(cell.get("precipitation_mm_y", 0.0)) <= 320.0
            or _aridity_ratio(cell) <= 0.75
            or _deficit_index(cell) >= 0.35
            or (
                str(cell.get("biome", "")) == "cold_desert"
                and float(cell.get("precipitation_mm_y", 0.0)) <= 450.0
                and float(cell.get("soil_moisture_index", 0.0)) <= 0.32
            )
        )
    ]
    desert_water_deficit = len(desert_water_limited) / len(desert_cells) if desert_cells else 1.0

    water_available_forests = [cell for cell in forest_cells if _has_water_availability(cell)]
    forest_water_availability = len(water_available_forests) / len(forest_cells) if forest_cells else 1.0

    climate_driven_tundra = [
        cell
        for cell in tundra_cells
        if (
            float(cell.get("temperature_c", 0.0)) <= 2.0
            or int(cell.get("frost_months", 0)) >= 6
            or float(cell.get("elevation_m", 0.0)) >= 2200.0
            or float(cell.get("ice_thickness_m", 0.0)) > 20.0
        )
    ]
    tundra_cold_altitude = len(climate_driven_tundra) / len(tundra_cells) if tundra_cells else 1.0

    seasonal_savannas = [
        cell
        for cell in savanna_cells
        if (
            float(cell.get("temperature_c", 0.0)) >= 17.0
            and (
                int(cell.get("dry_season_months", 0)) >= 2
                or float(cell.get("seasonal_aridity_index", 0.0)) >= 0.25
            )
            and int(cell.get("wet_season_months", 0)) >= 3
        )
    ]
    savanna_seasonality = len(seasonal_savannas) / len(savanna_cells) if savanna_cells else 1.0

    valid_mangroves = [
        cell
        for cell in mangrove_cells
        if (
            _is_coastal_land(cell, cells_by_id)
            and float(cell.get("temperature_c", 0.0)) >= 18.0
            and int(cell.get("frost_months", 0)) == 0
            and (
                float(cell.get("precipitation_mm_y", 0.0)) >= 900.0
                or float(cell.get("soil_moisture_index", 0.0)) >= 0.65
            )
        )
    ]
    mangrove_warm_wet_coast = len(valid_mangroves) / len(mangrove_cells) if mangrove_cells else 1.0

    checks: list[dict[str, Any]] = []
    _check_record(
        checks,
        name="desert_water_deficit_alignment",
        question="Do desert biomes coincide with generated water limitation?",
        metric="fraction_desert_cells_water_limited",
        value=desert_water_deficit,
        target_min=0.70,
        target_max=1.0,
        evidence={
            "desert_cell_count": len(desert_cells),
            "water_limited_desert_cell_count": len(desert_water_limited),
            "mean_desert_precipitation_mm_y": round(
                _mean([float(cell.get("precipitation_mm_y", 0.0)) for cell in desert_cells]),
                6,
            ),
            "mean_desert_aridity_ratio": round(_mean([_aridity_ratio(cell) for cell in desert_cells]), 6),
        },
    )
    _check_record(
        checks,
        name="forest_water_availability_alignment",
        question="Do forest biomes coincide with available water?",
        metric="fraction_forest_cells_with_water_available",
        value=forest_water_availability,
        target_min=0.75,
        target_max=1.0,
        evidence={
            "forest_cell_count": len(forest_cells),
            "water_available_forest_cell_count": len(water_available_forests),
            "mean_forest_precipitation_mm_y": round(
                _mean([float(cell.get("precipitation_mm_y", 0.0)) for cell in forest_cells]),
                6,
            ),
            "mean_forest_soil_moisture_index": round(
                _mean([float(cell.get("soil_moisture_index", 0.0)) for cell in forest_cells]),
                6,
            ),
        },
    )
    _check_record(
        checks,
        name="tundra_cold_altitude_alignment",
        question="Does tundra appear because of cold, frost, altitude, or ice?",
        metric="fraction_tundra_cells_cold_high_or_icy",
        value=tundra_cold_altitude,
        target_min=0.85,
        target_max=1.0,
        evidence={
            "tundra_cell_count": len(tundra_cells),
            "climate_driven_tundra_cell_count": len(climate_driven_tundra),
            "mean_tundra_temperature_c": round(
                _mean([float(cell.get("temperature_c", 0.0)) for cell in tundra_cells]),
                6,
            ),
            "mean_tundra_frost_months": round(
                _mean([float(cell.get("frost_months", 0.0)) for cell in tundra_cells]),
                6,
            ),
        },
    )
    _check_record(
        checks,
        name="savanna_seasonality_alignment",
        question="Do savannas appear in warm seasonal climates?",
        metric="fraction_savanna_cells_warm_and_seasonal",
        value=savanna_seasonality,
        target_min=0.65,
        target_max=1.0,
        evidence={
            "savanna_cell_count": len(savanna_cells),
            "seasonal_savanna_cell_count": len(seasonal_savannas),
            "mean_savanna_dry_season_months": round(
                _mean([float(cell.get("dry_season_months", 0.0)) for cell in savanna_cells]),
                6,
            ),
            "mean_savanna_wet_season_months": round(
                _mean([float(cell.get("wet_season_months", 0.0)) for cell in savanna_cells]),
                6,
            ),
        },
    )
    _check_record(
        checks,
        name="mangrove_warm_wet_coast_constraint",
        question="Are mangrove-labeled cells restricted to warm wet coasts?",
        metric="fraction_mangrove_cells_warm_wet_coastal",
        value=mangrove_warm_wet_coast,
        target_min=0.95,
        target_max=1.0,
        evidence={
            "mangrove_cell_count": len(mangrove_cells),
            "valid_mangrove_cell_count": len(valid_mangroves),
            "warm_wet_coastal_wetland_proxy_count": len(warm_wet_coastal_wetlands),
            "explicit_mangrove_biome_available": bool(mangrove_cells),
            "explicit_mangrove_ecotone_count": sum(
                1 for cell in mangrove_cells if str(cell.get("biome_ecotone_type", "")) == "mangrove"
            ),
        },
    )

    summary = world.setdefault("summary", {})
    pass_count = sum(1 for check in checks if bool(check["passed"]))
    score_sum = sum(float(check["score"]) for check in checks)
    world["biome_realism_checks"] = checks
    summary["desert_water_deficit_alignment_index"] = round(desert_water_deficit, 6)
    summary["forest_water_availability_index"] = round(forest_water_availability, 6)
    summary["tundra_cold_altitude_index"] = round(tundra_cold_altitude, 6)
    summary["savanna_seasonality_index"] = round(savanna_seasonality, 6)
    summary["mangrove_warm_wet_coast_index"] = round(mangrove_warm_wet_coast, 6)
    summary["biome_realism_check_count"] = len(checks)
    summary["biome_realism_pass_count"] = pass_count
    summary["biome_realism_pass_fraction"] = round(pass_count / len(checks), 6) if checks else 0.0
    summary["mean_biome_realism_score"] = round(score_sum / len(checks), 6) if checks else 0.0
    return world
