from __future__ import annotations

import math
from collections import Counter
from typing import Any


FOREST_BIOMES = {"tropical_rainforest", "tropical_seasonal_forest", "temperate_forest", "boreal_forest"}
GRASSLAND_BIOMES = {"savanna", "temperate_grassland", "mediterranean_scrub"}
BARREN_BIOMES = {"ice_cap", "tundra", "alpine", "hot_desert", "cold_desert"}
FISHERY_WATER_TYPES = {"ocean", "continental_shelf", "fresh_lake", "inland_sea"}
AQUATIC_PRIMARY_TEMPERATURE_MINIMUM_C = -16.0
AQUATIC_PRIMARY_TEMPERATURE_MAXIMUM_C = 52.0
FISHERY_TEMPERATURE_MINIMUM_C = -20.0
FISHERY_TEMPERATURE_MAXIMUM_C = 44.0
TERRESTRIAL_PRIMARY_TEMPERATURE_MINIMUM_C = -16.0
TERRESTRIAL_PRIMARY_TEMPERATURE_MAXIMUM_C = 52.0


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _finite_temperature(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        temperature = float(value)
    except OverflowError:
        return None
    return temperature if math.isfinite(temperature) else None


def _temperature_suitability(temperature_c: Any) -> float:
    temperature = _finite_temperature(temperature_c)
    return _clamp(1.0 - abs(temperature - 18.0) / 34.0) if temperature is not None else 0.0


def _is_aquatic_cell(cell: dict[str, Any]) -> bool:
    # The native marine mask excludes lakes. A saline_basin label alone can
    # also describe a dry depression, so standing saline water needs is_lake.
    return (
        bool(cell.get("is_water", False))
        or bool(cell.get("is_lake", False))
        or str(cell.get("water_body_type", "land")) in FISHERY_WATER_TYPES
    )


def _aquatic_climate_support(cell: dict[str, Any]) -> tuple[bool, bool, bool, bool]:
    """Limit the existing annual air-climate proxies to their own support.

    These are empirical model limits, not water temperatures at habitat depth
    or universal biological survival limits. In particular, cold air and sea
    ice do not imply absence of aquatic production. See the observations and
    model-scope discussion in docs/seasonal_climate_ecology_migration.md.
    """
    water_body = str(cell.get("water_body_type", "land"))
    aquatic = _is_aquatic_cell(cell)
    temperature = _finite_temperature(cell.get("temperature_c"))
    primary_supported = aquatic and temperature is not None and (
        AQUATIC_PRIMARY_TEMPERATURE_MINIMUM_C < temperature < AQUATIC_PRIMARY_TEMPERATURE_MAXIMUM_C
    )
    fishery_supported = water_body in FISHERY_WATER_TYPES and temperature is not None and (
        FISHERY_TEMPERATURE_MINIMUM_C < temperature < FISHERY_TEMPERATURE_MAXIMUM_C
    )
    # A sentinel zero for unsupported primary productivity is not a known
    # physical zero that the downstream fishery calculation may consume.
    fishery_productivity_supported = fishery_supported and primary_supported
    return aquatic, primary_supported, fishery_supported, fishery_productivity_supported


def _terrestrial_primary_climate_support(cell: dict[str, Any]) -> bool:
    """Applicability of the existing annual primary proxy, not plant survival.

    This domain does not define biome, phenology, crop, human or fuel support.
    Use the input interval directly: evaluating the triangular temperature
    factor can round to zero for represented inputs just inside an endpoint.
    """
    temperature = _finite_temperature(cell.get("temperature_c"))
    return not _is_aquatic_cell(cell) and temperature is not None and (
        TERRESTRIAL_PRIMARY_TEMPERATURE_MINIMUM_C < temperature
        < TERRESTRIAL_PRIMARY_TEMPERATURE_MAXIMUM_C
    )


def _primary_productivity(cell: dict[str, Any]) -> float:
    aquatic, primary_supported, _, _ = _aquatic_climate_support(cell)
    if aquatic and not primary_supported:
        return 0.0
    if not aquatic and not _terrestrial_primary_climate_support(cell):
        return 0.0
    water_body = str(cell.get("water_body_type", "land"))
    temperature = cell.get("temperature_c", 0.0)
    precipitation = float(cell.get("precipitation_mm_y", 0.0))
    pet = max(1.0, float(cell.get("potential_evapotranspiration_mm_y", 0.0)))
    moisture = _clamp(float(cell.get("soil_moisture_index", 0.0)))
    fertility = _clamp(float(cell.get("fertility", 0.0)))
    growing = _clamp(float(cell.get("growing_season_months", 0.0)) / 12.0)
    water_balance = _clamp(precipitation / pet)
    temp_suitability = _temperature_suitability(temperature)
    if aquatic:
        shelf_bonus = 0.20 if water_body == "continental_shelf" else (0.12 if water_body in {"fresh_lake", "inland_sea"} else 0.04)
        nutrient = _clamp(float(cell.get("runoff_mm_y", 0.0)) / 900.0)
        current = _clamp(abs(float(cell.get("ocean_current_temperature_c", 0.0))) / 4.5)
        return _clamp(0.12 + shelf_bonus + temp_suitability * 0.24 + nutrient * 0.22 + current * 0.12)
    ice = _clamp(float(cell.get("ice_thickness_m", 0.0)) / 1200.0)
    aridity = _clamp(float(cell.get("seasonal_aridity_index", 0.0)))
    return _clamp(temp_suitability * 0.26 + water_balance * 0.22 + moisture * 0.18 + fertility * 0.18 + growing * 0.18 - aridity * 0.14 - ice * 0.18)


def _vegetation_biomass(cell: dict[str, Any], primary_productivity: float) -> float:
    if not _terrestrial_primary_climate_support(cell):
        return 0.0
    biome = str(cell.get("biome", "unknown"))
    organic = _clamp(float(cell.get("soil_organic_matter_fraction", 0.0)))
    moisture = _clamp(float(cell.get("soil_moisture_index", 0.0)))
    ice = _clamp(float(cell.get("ice_thickness_m", 0.0)) / 1200.0)
    biome_bonus = 0.28 if biome in FOREST_BIOMES else (0.13 if biome in GRASSLAND_BIOMES else (-0.16 if biome in BARREN_BIOMES else 0.02))
    return _clamp(primary_productivity * 0.52 + organic * 0.18 + moisture * 0.14 + biome_bonus - ice * 0.22)


def _disturbance_pressure(cell: dict[str, Any], biomass: float, *, prescribed_natural: bool = False) -> tuple[float, float]:
    # Unknown terrestrial biomass is not a measured zero-fuel contribution.
    # Aquatic risk, in contrast, is a structural zero in this terrestrial proxy;
    # its remaining disturbance descriptors do not consume primary production.
    if not _is_aquatic_cell(cell) and not _terrestrial_primary_climate_support(cell):
        return 0.0, 0.0
    fire = _clamp(float(cell.get("fire_frequency_index", 0.0)))
    aridity = _clamp(float(cell.get("seasonal_aridity_index", 0.0)))
    ecotone = _clamp(float(cell.get("ecotone_index", 0.0)))
    erosion = _clamp(abs(float(cell.get("erosion_rate", 0.0))) / 0.08)
    settlement = 0.0 if prescribed_natural else _clamp(float(cell.get("settlement_score", 0.0)))
    wind = _clamp((float(cell.get("wind_east", 0.0)) ** 2 + float(cell.get("wind_north", 0.0)) ** 2) ** 0.5)
    wildfire_spread = 0.0 if _is_aquatic_cell(cell) else _clamp(fire * 0.38 + biomass * 0.22 + aridity * 0.22 + wind * 0.10)
    disturbance = _clamp(wildfire_spread * 0.42 + ecotone * 0.16 + erosion * 0.14 + settlement * 0.16 + aridity * 0.12)
    return wildfire_spread, disturbance


def _succession_stage(cell: dict[str, Any], biomass: float, productivity: float, disturbance: float, forest_growth: float) -> str:
    if _is_aquatic_cell(cell):
        return "aquatic_primary_productivity"
    if not _terrestrial_primary_climate_support(cell):
        return "terrestrial_primary_proxy_unavailable"
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
    _, _, _, fishery_productivity_supported = _aquatic_climate_support(cell)
    if not fishery_productivity_supported:
        return 0.0
    water_body = str(cell.get("water_body_type", "land"))
    shelf = 0.30 if water_body == "continental_shelf" else (0.18 if water_body in {"fresh_lake", "inland_sea"} else 0.08)
    runoff_nutrient = _clamp(float(cell.get("runoff_mm_y", 0.0)) / 900.0)
    current_mixing = _clamp(abs(float(cell.get("ocean_current_temperature_c", 0.0))) / 4.5 + abs(float(cell.get("ocean_current_east", 0.0))) * 0.4)
    temperature = _clamp(1.0 - abs(float(cell.get("temperature_c", 0.0)) - 12.0) / 32.0)
    return _clamp(shelf + primary_productivity * 0.34 + runoff_nutrient * 0.20 + current_mixing * 0.14 + temperature * 0.12)


def _forest_growth(cell: dict[str, Any], primary_productivity: float, biomass: float, disturbance: float) -> float:
    if not _terrestrial_primary_climate_support(cell):
        return 0.0
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


def _model_metadata(prescribed_natural: bool = False) -> dict[str, Any]:
    model = {
        "model": "heuristic_ecosystem_climate_support_v4",
        "aquatic_temperature_source": "annual_surface_air_climate_proxy",
        "aquatic_selector": "is_water_or_is_lake_or_fishery_water_body_type",
        "aquatic_ecology_policy": "shared_aquatic_selector_for_primary_and_terrestrial_exclusion",
        "fishery_water_body_types": sorted(FISHERY_WATER_TYPES),
        "aquatic_primary_minimum_temperature_c": AQUATIC_PRIMARY_TEMPERATURE_MINIMUM_C,
        "aquatic_primary_maximum_temperature_c": AQUATIC_PRIMARY_TEMPERATURE_MAXIMUM_C,
        "fishery_minimum_temperature_c": FISHERY_TEMPERATURE_MINIMUM_C,
        "fishery_maximum_temperature_c": FISHERY_TEMPERATURE_MAXIMUM_C,
        "temperature_bounds": "exclusive",
        "support_relationship": "fishery_estimate_requires_own_climate_and_supported_primary_input",
        "monthly_temperature_policy": "not_used",
        "invalid_annual_temperature_policy": "unsupported_without_numeric_coercion",
        "unsupported_productivity_policy": "numeric_zero_with_false_support_flag",
        "unsupported_fishery_record_policy": "no_record_without_supported_fishery_productivity",
        "support_scope": "empirical_climate_proxy_not_aquatic_survival_limits",
        "terrestrial_temperature_source": "annual_surface_air_climate_proxy",
        "terrestrial_selector": "complement_of_shared_aquatic_selector",
        "terrestrial_primary_minimum_temperature_c": TERRESTRIAL_PRIMARY_TEMPERATURE_MINIMUM_C,
        "terrestrial_primary_maximum_temperature_c": TERRESTRIAL_PRIMARY_TEMPERATURE_MAXIMUM_C,
        "terrestrial_support_scope": "existing_annual_primary_proxy_not_plant_survival_biome_phenology_crop_or_fuel_limits",
        "primary_availability_policy": "supported_aquatic_or_terrestrial_climate_input",
        "terrestrial_dependency_policy": "biomass_requires_supported_terrestrial_primary_forest_and_succession_require_supported_primary_biomass_and_disturbance",
        "unsupported_terrestrial_estimate_policy": "numeric_zero_with_false_support_flag_not_observed_physical_zero",
        "unsupported_terrestrial_succession_policy": "terrestrial_primary_proxy_unavailable_zero_recovery_years_no_history",
        "unsupported_forest_record_policy": "no_record_without_supported_forest_growth",
        "summary_availability_policy": "all_cell_means_include_unavailable_zero_sentinels_with_supported_cell_counts",
        "species_richness_availability_policy": "requires_supported_primary_and_terrestrial_biomass_or_aquatic_structural_zero",
        "ecosystem_wildfire_availability_policy": "requires_supported_terrestrial_biomass_aquatic_risk_is_known_zero",
        "ecosystem_disturbance_availability_policy": "requires_supported_ecosystem_wildfire_risk_aquatic_descriptors_remain_applicable",
        "vegetation_recovery_availability_policy": "requires_supported_primary_and_disturbance_and_terrestrial_biomass_or_aquatic_structural_zero",
        "renewable_record_availability_policy": "requires_supported_resource_productivity_primary_disturbance_recovery_and_terrestrial_biomass_or_aquatic_structural_zero",
        "unsupported_parent_estimate_policy": "numeric_zero_with_false_support_flag_not_absence_damage_or_physical_nonburnability",
        "ecosystem_disturbance_input_scope": "static_empirical_fire_frequency_aridity_ecotone_erosion_settlement_wind_descriptors_not_observed_fire_or_final_wildfire_feedback",
        "aquatic_biomass_input_policy": "structural_zero_for_aquatic_richness_recovery_and_renewable_inputs_not_terrestrial_biomass_estimate",
    }
    if prescribed_natural:
        model.update({
            "model": "heuristic_ecosystem_climate_support_v5",
            "ecosystem_disturbance_input_scope": "static_empirical_fire_frequency_aridity_ecotone_erosion_wind_descriptors_not_observed_fire_or_final_wildfire_feedback",
            "activity_forcing_policy": "prescribed_natural_scenario_without_anthropogenic_activity_input",
            "settlement_score_input_policy": "not_read_omitted_without_substitute_or_renormalization",
            "activity_scope": "scenario_boundary_not_inferred_absence_of_people_or_observed_fire",
            "physical_input_policy": "explicit_finite_nonboolean_descriptors_and_typed_habitat_biome_sources_no_missing_value_substitution",
        })
    return model


def _build_ecosystem_dynamics(world: dict[str, Any], *, prescribed_natural: bool = False) -> dict[str, Any]:
    cells = world.get("cells", [])
    if not prescribed_natural and (not isinstance(cells, list) or not cells):
        return world
    world["ecosystem_dynamics_model"] = _model_metadata(prescribed_natural)

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
        aquatic, primary_supported, fishery_supported, fishery_productivity_supported = _aquatic_climate_support(cell)
        cell["aquatic_climate_proxy_applicable"] = aquatic
        cell["aquatic_primary_climate_supported"] = primary_supported
        cell["fishery_climate_supported"] = fishery_supported
        cell["fishery_productivity_supported"] = fishery_productivity_supported
        terrestrial_supported = _terrestrial_primary_climate_support(cell)
        primary_available = primary_supported or terrestrial_supported
        biomass_available = terrestrial_supported
        # Aquatic biomass is deliberately excluded from this terrestrial
        # estimate. Its known zero can still enter aquatic richness, recovery
        # and renewable equations without claiming terrestrial biomass support.
        biomass_input_available = aquatic or biomass_available
        richness_available = primary_available and biomass_input_available
        wildfire_available = aquatic or biomass_available
        disturbance_available = wildfire_available
        forest_available = terrestrial_supported and biomass_available and disturbance_available
        succession_available = forest_available
        recovery_available = primary_available and biomass_input_available and disturbance_available
        cell["terrestrial_primary_climate_supported"] = terrestrial_supported
        cell["primary_productivity_supported"] = primary_available
        cell["vegetation_biomass_supported"] = biomass_available
        cell["species_richness_supported"] = richness_available
        cell["ecosystem_wildfire_spread_risk_supported"] = wildfire_available
        cell["ecosystem_disturbance_pressure_supported"] = disturbance_available
        cell["forest_growth_supported"] = forest_available
        cell["vegetation_succession_supported"] = succession_available
        cell["vegetation_recovery_supported"] = recovery_available
        primary = _primary_productivity(cell)
        biomass = _vegetation_biomass(cell, primary)
        wildfire, disturbance = _disturbance_pressure(cell, biomass, prescribed_natural=prescribed_natural) if disturbance_available else (0.0, 0.0)
        species_richness = _clamp(primary * 0.34 + biomass * 0.22 + _clamp(float(cell.get("ecotone_index", 0.0))) * 0.18 + _temperature_suitability(cell.get("temperature_c", 0.0)) * 0.16 + _clamp(float(cell.get("soil_moisture_index", 0.0))) * 0.10) if richness_available else 0.0
        forest_growth = _forest_growth(cell, primary, biomass, disturbance) if forest_available else 0.0
        fishery = _fishery_productivity(cell, primary)
        recovery_years = int(round(4 + (1.0 - primary) * 46 + disturbance * 34 + (1.0 - biomass) * 18)) if recovery_available else 0
        # Zero recovery years with false support is unavailable, not immediate
        # recovery. Aquatic succession remains inapplicable at any temperature.
        stage = _succession_stage(cell, biomass, primary, disturbance, forest_growth) if aquatic or succession_available else "terrestrial_primary_proxy_unavailable"

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
        high_wildfire_count += 1 if wildfire_available and wildfire >= 0.65 else 0
        mature_count += 1 if stage == "mature_closed_canopy" else 0

        if succession_available and recovery_available and wildfire_available and stage not in {"barren_ice", "pioneer_sparse_cover"} and biomass > 0.06:
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
        renewable_inputs_available = primary_available and biomass_input_available and disturbance_available and recovery_available
        forest_resource_eligible = forest_available and renewable_inputs_available and forest_growth >= 0.25
        if forest_resource_eligible:
            resource_type = "forest_growth"
            productivity = forest_growth
            forest_record_count += 1
        if fishery_productivity_supported and renewable_inputs_available and fishery >= 0.35 and fishery >= productivity:
            resource_type = "fishery_productivity"
            productivity = fishery
            fishery_record_count += 1
            if forest_resource_eligible:
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
                    "climate_dependency_index": round(_clamp(1.0 - _temperature_suitability(cell.get("temperature_c", 0.0)) + _clamp(float(cell.get("seasonal_aridity_index", 0.0))) * 0.35), 6),
                    "water_dependency_index": round(_clamp(float(cell.get("soil_moisture_index", 0.0)) * 0.45 + float(cell.get("groundwater_recharge_mm_y", 0.0)) / 450.0 * 0.35 + (0.30 if aquatic else 0.0)), 6),
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
    divisor = cell_count or 1
    world["vegetation_succession_histories"] = histories
    world["renewable_resource_records"] = renewable_records
    summary = world.setdefault("summary", {})
    summary["vegetation_succession_history_count"] = len(histories)
    summary["vegetation_succession_step_count"] = sum(int(history.get("step_count", 0)) for history in histories)
    summary["mean_primary_productivity_index"] = round(primary_sum / divisor, 6)
    summary["mean_vegetation_biomass_index"] = round(biomass_sum / divisor, 6)
    summary["mean_species_richness_index"] = round(richness_sum / divisor, 6)
    summary["mean_wildfire_spread_risk_index"] = round(wildfire_sum / divisor, 6)
    summary["mean_ecosystem_disturbance_pressure_index"] = round(disturbance_sum / divisor, 6)
    summary["high_wildfire_spread_risk_cell_count"] = high_wildfire_count
    summary["mature_vegetation_cell_fraction"] = round(mature_count / divisor, 6)
    summary["mean_forest_growth_index"] = round(forest_growth_sum / divisor, 6)
    summary["mean_fishery_productivity_index"] = round(fishery_sum / divisor, 6)
    summary["renewable_resource_record_count"] = len(renewable_records)
    summary["forest_growth_resource_count"] = forest_record_count
    summary["fishery_productivity_resource_count"] = fishery_record_count
    summary["vegetation_succession_stage_counts"] = dict(sorted(stage_counts.items()))
    summary["renewable_resource_type_counts"] = dict(sorted(renewable_counts.items()))
    for field in (
        "terrestrial_primary_climate_supported", "primary_productivity_supported",
        "vegetation_biomass_supported", "forest_growth_supported", "vegetation_succession_supported",
        "species_richness_supported", "ecosystem_wildfire_spread_risk_supported",
        "ecosystem_disturbance_pressure_supported", "vegetation_recovery_supported",
    ):
        summary[field + "_cell_count"] = sum(cell[field] is True for cell in cells)
    return world


def _same_model(actual: Any, expected: Any) -> bool:
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, dict):
        return actual.keys() == expected.keys() and all(_same_model(actual[k], v) for k, v in expected.items())
    if isinstance(expected, list):
        return len(actual) == len(expected) and all(_same_model(a, b) for a, b in zip(actual, expected))
    return actual == expected


def enrich_world_with_ecosystem_dynamics(world: dict[str, Any]) -> dict[str, Any]:
    """Exact v4 retention, or atomic prescribed-natural v5 first publication.

    Deliberate archive upgrades must audit their old declaration and clear this
    producer's owned fields/records/summary mirrors before removing its model.
    No occupation inference is made from missing or malformed settlement data.
    """
    from .aquatic_climate_validation import _EXPECTED_MODELS, validate_aquatic_climate_support
    from .prescribed_natural_ecosystem_validation import (
        CELL_FIELDS, RECORD_FIELDS, SUMMARY_FIELDS, PrescribedNaturalEcosystemError,
        validate_prescribed_natural_inputs,
    )
    if not isinstance(world, dict):
        raise PrescribedNaturalEcosystemError("prescribed natural ecosystem: world must be an object")
    model = world.get("ecosystem_dynamics_model")
    declared = "ecosystem_dynamics_model" in world
    if declared:
        if _same_model(model, _model_metadata()):
            return _build_ecosystem_dynamics(world)
        if any(_same_model(model, _EXPECTED_MODELS[key]) for key in (
            "heuristic_ecosystem_climate_support_v2", "heuristic_ecosystem_climate_support_v3"
        )):
            # These exact older producer inputs historically promote to v4.
            return _build_ecosystem_dynamics(world)
        if not _same_model(model, _model_metadata(True)):
            raise PrescribedNaturalEcosystemError("prescribed natural ecosystem: unknown or malformed own model")
    else:
        cells, summary = world.get("cells", []), world.get("summary", {})
        mirrors = any(key in world for key in RECORD_FIELDS) or (isinstance(summary, dict) and any(key in summary for key in SUMMARY_FIELDS))
        mirrors = mirrors or (isinstance(cells, list) and any(isinstance(c, dict) and any(key in c for key in CELL_FIELDS) for c in cells))
        if mirrors:
            raise PrescribedNaturalEcosystemError("prescribed natural ecosystem: undeclared owned outputs; audit and clear before explicit migration")
    validate_prescribed_natural_inputs(world)
    staged = {**world, "cells": [dict(cell) for cell in world["cells"]], "summary": dict(world.get("summary", {}))}
    try:
        _build_ecosystem_dynamics(staged, prescribed_natural=True)
        errors = validate_aquatic_climate_support(staged)
        if errors:
            raise PrescribedNaturalEcosystemError(errors[0])
    except (TypeError, ValueError, KeyError, ArithmeticError, AttributeError) as error:
        if isinstance(error, PrescribedNaturalEcosystemError):
            raise
        raise PrescribedNaturalEcosystemError("prescribed natural ecosystem: malformed or unrepresentable source/output (" + type(error).__name__ + ")") from error
    for cell, patch in zip(world["cells"], staged["cells"]):
        for key in CELL_FIELDS:
            cell[key] = patch[key]
    for key in RECORD_FIELDS + ("ecosystem_dynamics_model",):
        world[key] = staged[key]
    summary = world.setdefault("summary", {})
    summary.update({key: staged["summary"][key] for key in SUMMARY_FIELDS})
    return world
