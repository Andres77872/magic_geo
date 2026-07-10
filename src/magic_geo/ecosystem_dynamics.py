from __future__ import annotations

from collections import Counter
from typing import Any


FOREST_BIOMES = {"tropical_rainforest", "tropical_seasonal_forest", "temperate_forest", "boreal_forest"}
GRASSLAND_BIOMES = {"savanna", "temperate_grassland", "mediterranean_scrub"}
BARREN_BIOMES = {"ice_cap", "tundra", "alpine", "hot_desert", "cold_desert"}
FISHERY_WATER_TYPES = {"ocean", "continental_shelf", "fresh_lake", "inland_sea"}


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _temperature_suitability(temperature_c: float) -> float:
    return _clamp(1.0 - abs(temperature_c - 18.0) / 34.0)


def _primary_productivity(cell: dict[str, Any]) -> float:
    water_body = str(cell.get("water_body_type", "land"))
    temperature = float(cell.get("temperature_c", 0.0))
    precipitation = float(cell.get("precipitation_mm_y", 0.0))
    pet = max(1.0, float(cell.get("potential_evapotranspiration_mm_y", 0.0)))
    moisture = _clamp(float(cell.get("soil_moisture_index", 0.0)))
    fertility = _clamp(float(cell.get("fertility", 0.0)))
    growing = _clamp(float(cell.get("growing_season_months", 0.0)) / 12.0)
    water_balance = _clamp(precipitation / pet)
    temp_suitability = _temperature_suitability(temperature)
    if bool(cell.get("is_water", False)):
        shelf_bonus = 0.20 if water_body == "continental_shelf" else (0.12 if water_body in {"fresh_lake", "inland_sea"} else 0.04)
        nutrient = _clamp(float(cell.get("runoff_mm_y", 0.0)) / 900.0)
        current = _clamp(abs(float(cell.get("ocean_current_temperature_c", 0.0))) / 4.5)
        return _clamp(0.12 + shelf_bonus + temp_suitability * 0.24 + nutrient * 0.22 + current * 0.12)
    ice = _clamp(float(cell.get("ice_thickness_m", 0.0)) / 1200.0)
    aridity = _clamp(float(cell.get("seasonal_aridity_index", 0.0)))
    return _clamp(temp_suitability * 0.26 + water_balance * 0.22 + moisture * 0.18 + fertility * 0.18 + growing * 0.18 - aridity * 0.14 - ice * 0.18)


def _vegetation_biomass(cell: dict[str, Any], primary_productivity: float) -> float:
    if bool(cell.get("is_water", False)):
        return 0.0
    biome = str(cell.get("biome", "unknown"))
    organic = _clamp(float(cell.get("soil_organic_matter_fraction", 0.0)))
    moisture = _clamp(float(cell.get("soil_moisture_index", 0.0)))
    ice = _clamp(float(cell.get("ice_thickness_m", 0.0)) / 1200.0)
    biome_bonus = 0.28 if biome in FOREST_BIOMES else (0.13 if biome in GRASSLAND_BIOMES else (-0.16 if biome in BARREN_BIOMES else 0.02))
    return _clamp(primary_productivity * 0.52 + organic * 0.18 + moisture * 0.14 + biome_bonus - ice * 0.22)


def _disturbance_pressure(cell: dict[str, Any], biomass: float) -> tuple[float, float]:
    fire = _clamp(float(cell.get("fire_frequency_index", 0.0)))
    aridity = _clamp(float(cell.get("seasonal_aridity_index", 0.0)))
    ecotone = _clamp(float(cell.get("ecotone_index", 0.0)))
    erosion = _clamp(abs(float(cell.get("erosion_rate", 0.0))) / 0.08)
    settlement = _clamp(float(cell.get("settlement_score", 0.0)))
    wind = _clamp((float(cell.get("wind_east", 0.0)) ** 2 + float(cell.get("wind_north", 0.0)) ** 2) ** 0.5)
    wildfire_spread = 0.0 if bool(cell.get("is_water", False)) else _clamp(fire * 0.38 + biomass * 0.22 + aridity * 0.22 + wind * 0.10)
    disturbance = _clamp(wildfire_spread * 0.42 + ecotone * 0.16 + erosion * 0.14 + settlement * 0.16 + aridity * 0.12)
    return wildfire_spread, disturbance


def _succession_stage(cell: dict[str, Any], biomass: float, productivity: float, disturbance: float, forest_growth: float) -> str:
    if bool(cell.get("is_water", False)):
        return "aquatic_primary_productivity"
    if str(cell.get("biome", "")) == "ice_cap" or float(cell.get("ice_thickness_m", 0.0)) > 120.0:
        return "barren_ice"
    if biomass < 0.08 or productivity < 0.12:
        return "pioneer_sparse_cover"
    if disturbance >= 0.58:
        return "disturbance_mosaic"
    if forest_growth >= 0.62 and biomass >= 0.62:
        return "mature_closed_canopy"
    if biomass >= 0.44:
        return "mid_successional_cover"
    return "early_successional_cover"


def _fishery_productivity(cell: dict[str, Any], primary_productivity: float) -> float:
    water_body = str(cell.get("water_body_type", "land"))
    if water_body not in FISHERY_WATER_TYPES:
        return 0.0
    shelf = 0.30 if water_body == "continental_shelf" else (0.18 if water_body in {"fresh_lake", "inland_sea"} else 0.08)
    runoff_nutrient = _clamp(float(cell.get("runoff_mm_y", 0.0)) / 900.0)
    current_mixing = _clamp(abs(float(cell.get("ocean_current_temperature_c", 0.0))) / 4.5 + abs(float(cell.get("ocean_current_east", 0.0))) * 0.4)
    temperature = _clamp(1.0 - abs(float(cell.get("temperature_c", 0.0)) - 12.0) / 32.0)
    return _clamp(shelf + primary_productivity * 0.34 + runoff_nutrient * 0.20 + current_mixing * 0.14 + temperature * 0.12)


def _forest_growth(cell: dict[str, Any], primary_productivity: float, biomass: float, disturbance: float) -> float:
    biome = str(cell.get("biome", "unknown"))
    if biome not in FOREST_BIOMES and "forest" not in biome:
        return _clamp(primary_productivity * 0.20 + biomass * 0.12) if biome in GRASSLAND_BIOMES else 0.0
    moisture = _clamp(float(cell.get("soil_moisture_index", 0.0)))
    fertility = _clamp(float(cell.get("fertility", 0.0)))
    return _clamp(primary_productivity * 0.44 + biomass * 0.28 + moisture * 0.14 + fertility * 0.12 - disturbance * 0.16)


def _history_steps(
    cell: dict[str, Any],
    primary_productivity: float,
    biomass: float,
    wildfire: float,
    disturbance: float,
    forest_growth: float,
) -> list[dict[str, Any]]:
    phases = [("establishment", 0), ("canopy_building", 25), ("mature_state", 60), ("disturbance_recovery", 90)]
    start_biomass = _clamp(biomass * (0.38 + (1.0 - disturbance) * 0.26))
    steps: list[dict[str, Any]] = []
    for index, (phase, years) in enumerate(phases):
        progress = index / max(1, len(phases) - 1)
        step_biomass = _clamp(start_biomass + (biomass - start_biomass) * progress + primary_productivity * 0.04 * index - disturbance * 0.025 * index)
        step_disturbance = _clamp(disturbance * (1.0 - progress * 0.18) + wildfire * (0.08 if phase == "disturbance_recovery" else 0.0))
        canopy = _clamp(step_biomass * (0.50 + forest_growth * 0.42))
        recovery = _clamp(progress * (1.0 - step_disturbance * 0.38))
        steps.append(
            {
                "phase": phase,
                "years_since_start": years,
                "succession_stage": _succession_stage(cell, step_biomass, primary_productivity, step_disturbance, forest_growth),
                "biomass_index": round(step_biomass, 6),
                "canopy_closure_index": round(canopy, 6),
                "primary_productivity_index": round(primary_productivity, 6),
                "disturbance_pressure_index": round(step_disturbance, 6),
                "wildfire_spread_risk_index": round(wildfire, 6),
                "recovery_fraction": round(recovery, 6),
            }
        )
    return steps


def enrich_world_with_ecosystem_dynamics(world: dict[str, Any]) -> dict[str, Any]:
    cells = world.get("cells", [])
    if not isinstance(cells, list) or not cells:
        return world

    histories: list[dict[str, Any]] = []
    renewable_records: list[dict[str, Any]] = []
    stage_counts: Counter[str] = Counter()
    renewable_counts: Counter[str] = Counter()
    primary_sum = 0.0
    biomass_sum = 0.0
    richness_sum = 0.0
    wildfire_sum = 0.0
    disturbance_sum = 0.0
    forest_growth_sum = 0.0
    fishery_sum = 0.0
    high_wildfire_count = 0
    mature_count = 0
    forest_record_count = 0
    fishery_record_count = 0

    for cell in cells:
        primary = _primary_productivity(cell)
        biomass = _vegetation_biomass(cell, primary)
        wildfire, disturbance = _disturbance_pressure(cell, biomass)
        species_richness = _clamp(primary * 0.34 + biomass * 0.22 + _clamp(float(cell.get("ecotone_index", 0.0))) * 0.18 + _temperature_suitability(float(cell.get("temperature_c", 0.0))) * 0.16 + _clamp(float(cell.get("soil_moisture_index", 0.0))) * 0.10)
        forest_growth = _forest_growth(cell, primary, biomass, disturbance)
        fishery = _fishery_productivity(cell, primary)
        recovery_years = int(round(4 + (1.0 - primary) * 46 + disturbance * 34 + (1.0 - biomass) * 18))
        stage = _succession_stage(cell, biomass, primary, disturbance, forest_growth)

        cell["primary_productivity_index"] = round(primary, 6)
        cell["vegetation_biomass_index"] = round(biomass, 6)
        cell["species_richness_index"] = round(species_richness, 6)
        cell["wildfire_spread_risk_index"] = round(wildfire, 6)
        cell["ecosystem_disturbance_pressure_index"] = round(disturbance, 6)
        cell["vegetation_succession_stage"] = stage
        cell["vegetation_recovery_years"] = recovery_years
        cell["forest_growth_index"] = round(forest_growth, 6)
        cell["fishery_productivity_index"] = round(fishery, 6)

        stage_counts[stage] += 1
        primary_sum += primary
        biomass_sum += biomass
        richness_sum += species_richness
        wildfire_sum += wildfire
        disturbance_sum += disturbance
        forest_growth_sum += forest_growth
        fishery_sum += fishery
        high_wildfire_count += 1 if wildfire >= 0.65 else 0
        mature_count += 1 if stage == "mature_closed_canopy" else 0

        if not bool(cell.get("is_water", False)) and stage not in {"barren_ice", "pioneer_sparse_cover"} and biomass > 0.06:
            steps = _history_steps(cell, primary, biomass, wildfire, disturbance, forest_growth)
            histories.append(
                {
                    "id": len(histories),
                    "cell_id": int(cell.get("id", -1)),
                    "biome": str(cell.get("biome", "unknown")),
                    "initial_succession_stage": str(steps[0]["succession_stage"]),
                    "final_succession_stage": str(steps[-1]["succession_stage"]),
                    "step_count": len(steps),
                    "recovery_years": recovery_years,
                    "mean_biomass_index": round(sum(float(step["biomass_index"]) for step in steps) / len(steps), 6),
                    "mean_canopy_closure_index": round(sum(float(step["canopy_closure_index"]) for step in steps) / len(steps), 6),
                    "mean_disturbance_pressure_index": round(sum(float(step["disturbance_pressure_index"]) for step in steps) / len(steps), 6),
                    "max_wildfire_spread_risk_index": round(max(float(step["wildfire_spread_risk_index"]) for step in steps), 6),
                    "steps": steps,
                }
            )

        resource_type = ""
        productivity = 0.0
        if forest_growth >= 0.25:
            resource_type = "forest_growth"
            productivity = forest_growth
            forest_record_count += 1
        if fishery >= 0.35 and fishery >= productivity:
            resource_type = "fishery_productivity"
            productivity = fishery
            fishery_record_count += 1
            if forest_growth >= 0.25:
                forest_record_count -= 1
        if resource_type:
            sustainability = _clamp(productivity * 0.56 + primary * 0.20 + biomass * 0.14 - disturbance * 0.18)
            renewable_counts[resource_type] += 1
            renewable_records.append(
                {
                    "id": len(renewable_records),
                    "cell_id": int(cell.get("id", -1)),
                    "resource_type": resource_type,
                    "biome": str(cell.get("biome", "unknown")),
                    "water_body_type": str(cell.get("water_body_type", "land")),
                    "productivity_index": round(productivity, 6),
                    "sustainable_yield_index": round(sustainability, 6),
                    "regeneration_years": max(1, int(round(recovery_years * (0.35 if resource_type == "fishery_productivity" else 1.0)))),
                    "climate_dependency_index": round(_clamp(1.0 - _temperature_suitability(float(cell.get("temperature_c", 0.0))) + _clamp(float(cell.get("seasonal_aridity_index", 0.0))) * 0.35), 6),
                    "water_dependency_index": round(_clamp(float(cell.get("soil_moisture_index", 0.0)) * 0.45 + float(cell.get("groundwater_recharge_mm_y", 0.0)) / 450.0 * 0.35 + (0.30 if bool(cell.get("is_water", False)) else 0.0)), 6),
                    "disturbance_risk_index": round(disturbance, 6),
                    "formation_evidence": {
                        "primary_productivity_index": round(primary, 6),
                        "vegetation_biomass_index": round(biomass, 6),
                        "forest_growth_index": round(forest_growth, 6),
                        "fishery_productivity_index": round(fishery, 6),
                        "runoff_mm_y": round(max(0.0, float(cell.get("runoff_mm_y", 0.0))), 6),
                        "soil_moisture_index": round(_clamp(float(cell.get("soil_moisture_index", 0.0))), 6),
                    },
                }
            )

    cell_count = len(cells)
    world["vegetation_succession_histories"] = histories
    world["renewable_resource_records"] = renewable_records
    summary = world.setdefault("summary", {})
    summary["vegetation_succession_history_count"] = len(histories)
    summary["vegetation_succession_step_count"] = sum(int(history.get("step_count", 0)) for history in histories)
    summary["mean_primary_productivity_index"] = round(primary_sum / cell_count, 6)
    summary["mean_vegetation_biomass_index"] = round(biomass_sum / cell_count, 6)
    summary["mean_species_richness_index"] = round(richness_sum / cell_count, 6)
    summary["mean_wildfire_spread_risk_index"] = round(wildfire_sum / cell_count, 6)
    summary["mean_ecosystem_disturbance_pressure_index"] = round(disturbance_sum / cell_count, 6)
    summary["high_wildfire_spread_risk_cell_count"] = high_wildfire_count
    summary["mature_vegetation_cell_fraction"] = round(mature_count / cell_count, 6)
    summary["mean_forest_growth_index"] = round(forest_growth_sum / cell_count, 6)
    summary["mean_fishery_productivity_index"] = round(fishery_sum / cell_count, 6)
    summary["renewable_resource_record_count"] = len(renewable_records)
    summary["forest_growth_resource_count"] = forest_record_count
    summary["fishery_productivity_resource_count"] = fishery_record_count
    summary["vegetation_succession_stage_counts"] = dict(sorted(stage_counts.items()))
    summary["renewable_resource_type_counts"] = dict(sorted(renewable_counts.items()))
    return world
