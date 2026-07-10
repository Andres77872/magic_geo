from __future__ import annotations

from collections import Counter
from typing import Any


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _monthly_values(cell: dict[str, Any], key: str, fallback_key: str) -> list[float]:
    values = cell.get(key, [])
    if isinstance(values, list) and len(values) == 12:
        return [float(value) for value in values]
    fallback = float(cell.get(fallback_key, 0.0))
    return [fallback / 12.0 if fallback_key.endswith("_mm_y") else fallback for _ in range(12)]


def _monthly_pet_mm(temperature_c: float, lat_deg: float) -> float:
    latitude_factor = 0.66 + 0.34 * (1.0 - min(1.0, abs(lat_deg) / 90.0))
    return max(0.0, temperature_c + 5.0) * 3.1 * latitude_factor


def _expected_biome(
    cell: dict[str, Any],
    annual_pet: float,
    annual_deficit: float,
    growing_months: int,
    frost_months: int,
) -> str:
    water_body = str(cell.get("water_body_type", "land"))
    temperature = float(cell.get("temperature_c", 0.0))
    precipitation = float(cell.get("precipitation_mm_y", 0.0))
    elevation = float(cell.get("elevation_m", 0.0))
    aridity = _clamp(annual_deficit / max(1.0, annual_pet))
    if bool(cell.get("is_water", False)):
        if water_body == "continental_shelf":
            return "continental_shelf"
        if water_body in {"fresh_lake", "saline_basin", "inland_sea"}:
            return "lake"
        return "ocean"
    if float(cell.get("ice_thickness_m", 0.0)) > 120.0 or str(cell.get("biome", "")) == "ice_cap":
        return "ice_cap"
    if elevation > 2800.0 and temperature < 7.0:
        return "alpine"
    if temperature < -3.0 or frost_months >= 8:
        return "tundra"
    if aridity >= 0.72 or precipitation <= 180.0:
        return "cold_desert" if temperature < 11.0 else "hot_desert"
    if temperature > 23.0 and precipitation > 1900.0 and growing_months >= 10:
        return "tropical_rainforest"
    if temperature > 20.0 and precipitation > 850.0:
        return "tropical_seasonal_forest" if aridity < 0.45 else "savanna"
    if temperature > 17.0 and aridity >= 0.45:
        return "savanna"
    if temperature > 8.0 and precipitation > 700.0:
        return "temperate_forest"
    if temperature > 5.0 and aridity < 0.62:
        return "temperate_grassland"
    if temperature > -1.0 and precipitation > 420.0:
        return "boreal_forest"
    return "cold_desert" if aridity >= 0.45 else "tundra"


def _limiting_factor(
    cell: dict[str, Any],
    annual_deficit: float,
    annual_pet: float,
    growing_months: int,
    frost_months: int,
) -> str:
    if bool(cell.get("is_water", False)):
        return "water_body"
    if float(cell.get("ice_thickness_m", 0.0)) > 120.0:
        return "persistent_ice"
    if frost_months >= 8 or float(cell.get("temperature_c", 0.0)) < -3.0:
        return "cold"
    if annual_deficit / max(1.0, annual_pet) >= 0.65:
        return "water_deficit"
    if growing_months <= 3:
        return "short_growing_season"
    if float(cell.get("soil_moisture_index", 0.0)) >= 0.78:
        return "waterlogging"
    if float(cell.get("elevation_m", 0.0)) > 2800.0:
        return "elevation"
    return "balanced"


def enrich_world_with_biome_diagnostics(world: dict[str, Any]) -> dict[str, Any]:
    cells = world.get("cells", [])
    if not isinstance(cells, list) or not cells:
        return world

    cells_by_id = {int(cell.get("id", -1)): cell for cell in cells}
    diagnostics: list[dict[str, Any]] = []
    limiting_counts: Counter[str] = Counter()
    pet_sum = 0.0
    deficit_sum = 0.0
    growing_sum = 0.0
    fire_sum = 0.0
    confidence_sum = 0.0
    ecotone_sum = 0.0
    match_count = 0
    transition_count = 0
    high_fire_count = 0
    water_stress_count = 0

    for cell in cells:
        cell_id = int(cell.get("id", len(diagnostics)))
        lat = float(cell.get("lat_deg", 0.0))
        monthly_temperature = _monthly_values(cell, "temperature_monthly_c", "temperature_c")
        monthly_precipitation = _monthly_values(cell, "precipitation_monthly_mm", "precipitation_mm_y")
        monthly_pet = [_monthly_pet_mm(temperature, lat) for temperature in monthly_temperature]
        annual_pet = sum(monthly_pet)
        annual_precipitation = sum(max(0.0, value) for value in monthly_precipitation)
        annual_deficit = max(0.0, annual_pet - annual_precipitation)
        annual_surplus = max(0.0, annual_precipitation - annual_pet)
        growing_months = sum(
            1
            for temperature, precipitation, pet in zip(monthly_temperature, monthly_precipitation, monthly_pet, strict=True)
            if temperature >= 5.0 and precipitation >= pet * 0.25
        )
        frost_months = sum(1 for temperature in monthly_temperature if temperature < 0.0)
        dry_months = sum(1 for precipitation, pet in zip(monthly_precipitation, monthly_pet, strict=True) if precipitation < pet * 0.35)
        wet_months = sum(1 for precipitation, pet in zip(monthly_precipitation, monthly_pet, strict=True) if precipitation >= pet * 0.75)
        moisture = _clamp(float(cell.get("soil_moisture_index", 0.0)))
        seasonal_aridity = _clamp(float(cell.get("seasonal_aridity_index", 0.0)))
        deficit_index = _clamp(annual_deficit / max(1.0, annual_pet))
        warmth_index = _clamp((float(cell.get("temperature_c", 0.0)) + 5.0) / 30.0)
        fuel_index = _clamp(
            0.18
            + (0.28 if str(cell.get("biome", "")) in {"savanna", "temperate_grassland", "mediterranean_scrub"} else 0.0)
            + (0.16 if "forest" in str(cell.get("biome", "")) else 0.0)
            + float(cell.get("soil_organic_matter_fraction", 0.0)) * 0.70
        )
        fire_frequency = 0.0 if bool(cell.get("is_water", False)) or str(cell.get("biome", "")) in {"ice_cap", "tundra", "alpine"} else _clamp(
            warmth_index * 0.28 + deficit_index * 0.34 + seasonal_aridity * 0.20 + fuel_index * 0.18 - moisture * 0.18
        )
        neighbor_biomes = {
            str(cells_by_id[int(neighbor_id)].get("biome", ""))
            for neighbor_id in cell.get("neighbors", [])
            if int(neighbor_id) in cells_by_id
        }
        neighbor_diversity = _clamp((len(neighbor_biomes) - 1) / 4.0) if neighbor_biomes else 0.0
        climate_margin = _clamp(1.0 - abs(deficit_index - 0.50) * 2.0)
        ecotone = _clamp(neighbor_diversity * 0.62 + climate_margin * 0.26 + seasonal_aridity * 0.12)
        expected = _expected_biome(cell, annual_pet, annual_deficit, growing_months, frost_months)
        biome = str(cell.get("biome", "unknown"))
        matches = expected == biome or (expected == "lake" and biome in {"lake", "wetland"})
        confidence = _clamp((0.58 if matches else 0.30) + (1.0 - ecotone) * 0.22 + (1.0 - deficit_index) * 0.08 + moisture * 0.12)
        transition = ecotone >= 0.55 or not matches
        limiting_factor = _limiting_factor(cell, annual_deficit, annual_pet, growing_months, frost_months)

        cell["potential_evapotranspiration_mm_y"] = round(annual_pet, 6)
        cell["climatic_water_deficit_mm_y"] = round(annual_deficit, 6)
        cell["climatic_water_surplus_mm_y"] = round(annual_surplus, 6)
        cell["growing_season_months"] = growing_months
        cell["frost_months"] = frost_months
        cell["dry_season_months"] = dry_months
        cell["wet_season_months"] = wet_months
        cell["fire_frequency_index"] = round(fire_frequency, 6)
        cell["biome_confidence_index"] = round(confidence, 6)
        cell["ecotone_index"] = round(ecotone, 6)
        cell["biome_transition_zone"] = transition

        limiting_counts[limiting_factor] += 1
        pet_sum += annual_pet
        deficit_sum += annual_deficit
        growing_sum += growing_months
        fire_sum += fire_frequency
        confidence_sum += confidence
        ecotone_sum += ecotone
        match_count += 1 if matches else 0
        transition_count += 1 if transition else 0
        high_fire_count += 1 if fire_frequency >= 0.65 else 0
        water_stress_count += 1 if deficit_index >= 0.55 else 0
        diagnostics.append(
            {
                "id": len(diagnostics),
                "cell_id": cell_id,
                "biome": biome,
                "expected_biome": expected,
                "limiting_factor": limiting_factor,
                "potential_evapotranspiration_mm_y": round(annual_pet, 6),
                "climatic_water_deficit_mm_y": round(annual_deficit, 6),
                "climatic_water_surplus_mm_y": round(annual_surplus, 6),
                "soil_moisture_index": round(moisture, 6),
                "seasonal_aridity_index": round(seasonal_aridity, 6),
                "growing_season_months": growing_months,
                "frost_months": frost_months,
                "dry_season_months": dry_months,
                "wet_season_months": wet_months,
                "fire_frequency_index": round(fire_frequency, 6),
                "ecotone_index": round(ecotone, 6),
                "biome_confidence_index": round(confidence, 6),
                "biome_transition_zone": transition,
            }
        )

    cell_count = len(cells)
    world["biome_diagnostics"] = diagnostics
    summary = world.setdefault("summary", {})
    summary["biome_diagnostic_count"] = len(diagnostics)
    summary["biome_transition_zone_count"] = transition_count
    summary["high_fire_frequency_biome_count"] = high_fire_count
    summary["water_stressed_biome_cell_fraction"] = round(water_stress_count / cell_count, 6)
    summary["biome_expected_match_fraction"] = round(match_count / cell_count, 6)
    summary["mean_potential_evapotranspiration_mm_y"] = round(pet_sum / cell_count, 6)
    summary["mean_climatic_water_deficit_mm_y"] = round(deficit_sum / cell_count, 6)
    summary["mean_growing_season_months"] = round(growing_sum / cell_count, 6)
    summary["mean_fire_frequency_index"] = round(fire_sum / cell_count, 6)
    summary["mean_biome_confidence_index"] = round(confidence_sum / cell_count, 6)
    summary["mean_ecotone_index"] = round(ecotone_sum / cell_count, 6)
    summary["biome_limiting_factor_counts"] = dict(sorted(limiting_counts.items()))
    return world
