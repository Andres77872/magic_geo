from __future__ import annotations

import math
from collections import Counter, deque
from copy import deepcopy
from typing import Any

from .marine_distance_validation import require_marine_distance

from .ecosystem_dynamics import _is_aquatic_cell
from .aquatic_climate_validation import (
    _EXPECTED_MODELS as _ECOSYSTEM_MODELS,
    validate_aquatic_climate_support,
)


FOREST_BIOMES = {"tropical_rainforest", "tropical_seasonal_forest", "temperate_forest", "boreal_forest"}
GRASSLAND_BIOMES = {"savanna", "temperate_grassland", "mediterranean_scrub"}
DESERT_BIOMES = {"hot_desert", "cold_desert"}
ALPINE_BIOMES = {"tundra", "alpine", "ice_cap"}
FRESHWATER_TYPES = {"fresh_lake"}
MARINE_TYPES = {"ocean", "continental_shelf", "inland_sea"}
TERRESTRIAL_GUILDS = {"canopy_tree", "grassland_grazer", "desert_specialist", "alpine_tundra_specialist", "large_predator"}
SPECIES_RANGE_THRESHOLD = 0.46

GUILD_METADATA = {
    "canopy_tree": ("terrestrial", "primary_producer"),
    "grassland_grazer": ("terrestrial", "herbivore"),
    "desert_specialist": ("arid", "specialist_consumer"),
    "alpine_tundra_specialist": ("alpine", "specialist_consumer"),
    "wetland_amphibian": ("wetland", "secondary_consumer"),
    "large_predator": ("terrestrial", "apex_predator"),
    "freshwater_fish": ("freshwater", "aquatic_consumer"),
    "marine_fish": ("marine", "aquatic_consumer"),
    "reef_builder": ("reef", "foundation_species"),
    "mangrove_coastal_bird": ("wetland", "mobile_consumer"),
}


_SPECIES_V2_MODEL = {
    "model": "heuristic_species_habitat_support_v2",
    "aquatic_selector": "is_water_or_is_lake_or_fishery_water_body_type",
    "terrestrial_guilds": sorted(TERRESTRIAL_GUILDS),
    "marine_water_body_types": sorted(MARINE_TYPES),
    "freshwater_water_body_types": sorted(FRESHWATER_TYPES),
    "freshwater_river_policy": "is_river_on_non_aquatic_non_saline_land",
    "standing_water_fish_input_policy": "requires_current_climate_support_true_primary_and_derived_fishery_flags_and_finite_indices",
    "fish_temperature_proxy": "annual_air_temperature_c",
    "fish_temperature_support_c": {
        "freshwater_fish": {"lower_exclusive": -10.0, "upper_exclusive": 38.0},
        "marine_fish": {"lower_exclusive": -11.0, "upper_exclusive": 37.0},
    },
    "fish_temperature_support_policy": "positive_support_of_existing_guild_temperature_windows_not_species_survival_limits",
    "river_fishery_input_policy": "omit_fishery_term_regardless_upstream_numeric_diagnostic",
    "fishery_habitat_evidence": "upstream_numeric_diagnostic_not_consumed_river_resource",
    "unsupported_fish_score_policy": "numeric_zero_with_false_score_support_flag",
    "temperature_input_policy": "finite_numeric_annual_temperature_required_before_mutation",
    "productivity_input_policy": "absent_is_unavailable_present_requires_finite_numeric_before_mutation",
    "habitat_scope": "empirical_resident_habitat_not_species_survival_or_migration",
    "unmigrated_guild_policy": "reef_builder_wetland_amphibian_mangrove_coastal_bird_legacy_scores",
}

_SCORE_PARENTS = {
    "canopy_tree": ("primary", "biomass", "forest", "disturbance"),
    "grassland_grazer": ("primary", "richness", "biomass", "disturbance"),
    "desert_specialist": ("richness",),
    "alpine_tundra_specialist": ("richness",),
    "large_predator": ("richness", "biomass", "primary", "disturbance"),
    "wetland_amphibian": ("richness",),
    "freshwater_fish": ("primary", "standing_fishery_if_applicable"),
    "marine_fish": ("primary", "fishery"),
    "reef_builder": ("reef_growth", "fishery"),
    "mangrove_coastal_bird": ("richness", "disturbance"),
}
_OWN_TEMPERATURE_BOUNDS = {
    "canopy_tree": (-6.0, 42.0), "grassland_grazer": (-6.0, 42.0),
    "alpine_tundra_specialist": (None, 8.0),
    "wetland_amphibian": (11.0, 39.0), "freshwater_fish": (-10.0, 38.0),
    "marine_fish": (-11.0, 37.0), "reef_builder": (11.0, 39.0),
    "mangrove_coastal_bird": (11.0, 39.0),
}
SPECIES_PARENT_MODEL = {
    "model": "heuristic_species_parent_support_v3",
    "parent_model": "heuristic_ecosystem_climate_support_v4",
    "aquatic_selector": "is_water_or_is_lake_or_fishery_water_body_type",
    "terrestrial_guilds": sorted(TERRESTRIAL_GUILDS),
    "marine_water_body_types": sorted(MARINE_TYPES),
    "freshwater_water_body_types": sorted(FRESHWATER_TYPES),
    "freshwater_river_policy": "is_river_on_non_aquatic_non_saline_land",
    "other_habitat_policy": "reef_builder_wetland_amphibian_mangrove_coastal_bird_existing_unconditional_applicability",
    "temperature_source": "annual_surface_air_climate_proxy",
    "own_temperature_support_c": {guild: {"lower_exclusive": bounds[0], "upper_exclusive": bounds[1]} for guild, bounds in _OWN_TEMPERATURE_BOUNDS.items()},
    "guilds_without_own_temperature_window": ["desert_specialist", "large_predator"],
    "own_temperature_policy": "positive_support_of_existing_guild_terms_not_survival_limits_or_habitat_absence",
    "score_parent_inputs": {guild: list(parents) for guild, parents in _SCORE_PARENTS.items()},
    "parent_input_policy": "exact_true_availability_and_finite_numeric_unit_interval_supported_zero_valid",
    "aquatic_biomass_policy": "known_structural_zero_for_common_descriptors_not_terrestrial_score_habitat",
    "river_fishery_input_policy": "omit_standing_fishery_term_regardless_numeric_value_require_supported_primary",
    "reef_growth_input_policy": "finite_numeric_unit_interval_upstream_reef_descriptor_no_new_habitat_claim",
    "confidence_inputs": ["primary", "richness", "disturbance", "biome_confidence", "wetland", "reef_growth"],
    "endemism_inputs": ["disturbance", "wetland", "reef_growth"],
    "common_record_policy": "requires_supported_primary_richness_disturbance_confidence_endemism_and_finite_common_descriptors",
    "record_evidence_policy": "fishery_mean_only_when_all_members_consume_supported_fishery_forest_mean_only_for_canopy_tree",
    "unsupported_estimate_policy": "numeric_zero_with_false_support_flag_not_species_absence",
    "composition_denominator": "existing_habitat_applicability_only_own_temperature_reduces_support",
    "composition_status_policy": "not_applicable_if_no_habitats_unavailable_if_no_supported_scores_complete_if_all_habitat_scores_supported_otherwise_partial",
    "dominance_policy": "maximum_supported_score_only_none_below_0.25_or_unavailable",
    "range_policy": "supported_score_at_least_0.46_and_supported_common_record_descriptors_connected_mesh_components",
    "summary_policy": "all_cell_means_include_unavailable_zero_sentinels_with_support_and_composition_counts",
    "source_input_policy": "finite_numeric_annual_and_present_numeric_descriptors_required_before_mutation_absent_biological_inputs_unavailable",
    "scope": "empirical_resident_habitat_scores_not_population_survival_migration_or_global_habitability",
}


NATURAL_SPECIES_PARENT_MODEL = {
    **SPECIES_PARENT_MODEL,
    "model": "heuristic_species_parent_support_v4",
    "parent_model": "heuristic_ecosystem_climate_support_v5",
    "source_input_policy": "explicit_finite_numeric_annual_and_consumed_descriptors_typed_habitat_categories_and_reciprocal_complete_graph_before_publication",
    "source_link_policy": "explicit_unique_natural_source_records_reciprocal_cell_membership_basin_ids_are_native_outlet_cells",
}


def _same_model_metadata(observed: Any, expected: Any) -> bool:
    if type(observed) is not type(expected):
        return False
    if isinstance(expected, dict):
        return observed.keys() == expected.keys() and all(
            _same_model_metadata(observed[key], value) for key, value in expected.items()
        )
    if isinstance(expected, list):
        return len(observed) == len(expected) and all(
            _same_model_metadata(left, right) for left, right in zip(observed, expected)
        )
    return observed == expected


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _primary_key(counter: Counter[str], fallback: str) -> str:
    if not counter:
        return fallback
    return sorted(counter.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _temperature_window(temperature_c: float, center: float, half_width: float) -> float:
    return _clamp(1.0 - abs(temperature_c - center) / max(1.0, half_width))


def _connected_components(candidate_ids: set[int], cells_by_id: dict[int, dict[str, Any]]) -> list[list[dict[str, Any]]]:
    components: list[list[dict[str, Any]]] = []
    remaining = set(candidate_ids)
    while remaining:
        start = min(remaining)
        remaining.remove(start)
        queue: deque[int] = deque([start])
        component_ids = [start]
        while queue:
            current_id = queue.popleft()
            current = cells_by_id[current_id]
            for neighbor_id_raw in current.get("neighbors", []):
                neighbor_id = int(neighbor_id_raw)
                if neighbor_id not in remaining:
                    continue
                remaining.remove(neighbor_id)
                queue.append(neighbor_id)
                component_ids.append(neighbor_id)
        components.append([cells_by_id[cell_id] for cell_id in sorted(component_ids)])
    return components


def _centroid(component: list[dict[str, Any]]) -> tuple[float, float]:
    if not component:
        return 0.0, 0.0
    weight_sum = 0.0
    x_sum = 0.0
    y_sum = 0.0
    z_sum = 0.0
    for cell in component:
        weight = max(0.0, float(cell.get("area_km2", 0.0))) or 1.0
        lat = math.radians(float(cell.get("lat_deg", 0.0)))
        lon = math.radians(float(cell.get("lon_deg", 0.0)))
        cos_lat = math.cos(lat)
        x_sum += math.cos(lon) * cos_lat * weight
        y_sum += math.sin(lon) * cos_lat * weight
        z_sum += math.sin(lat) * weight
        weight_sum += weight
    if weight_sum <= 0.0:
        return 0.0, 0.0
    lon = math.degrees(math.atan2(y_sum / weight_sum, x_sum / weight_sum))
    hyp = math.hypot(x_sum / weight_sum, y_sum / weight_sum)
    lat = math.degrees(math.atan2(z_sum / weight_sum, hyp))
    return round(lat, 6), round(lon, 6)


def _range_fragmentation(component: list[dict[str, Any]]) -> float:
    member_ids = {int(cell.get("id", -1)) for cell in component}
    total_edges = 0
    external_edges = 0
    for cell in component:
        for neighbor_id_raw in cell.get("neighbors", []):
            total_edges += 1
            if int(neighbor_id_raw) not in member_ids:
                external_edges += 1
    edge_fraction = external_edges / total_edges if total_edges else 1.0
    small_range_pressure = 1.0 / max(1.0, float(len(component)))
    return _clamp(edge_fraction * 0.72 + small_range_pressure * 0.28)


def _finite_number(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _supported_index(value: Any) -> bool:
    return _finite_number(value) and 0.0 <= value <= 1.0


def _legacy_habitat_support(cell: dict[str, Any]) -> dict[str, bool | str]:
    """Declare resident habitat and availability of the two fish scores.

    An unavailable standing-water productivity sentinel is not a physical
    zero. Rivers have a separate channel proxy that does not consume the
    standing-water resource-fishery estimate. Neither rule is a universal
    survival or migration constraint.
    """
    water_body = str(cell.get("water_body_type", "land"))
    terrestrial = not _is_aquatic_cell(cell)
    river = bool(cell.get("is_river", False)) and terrestrial and water_body != "saline_basin"
    freshwater = water_body in FRESHWATER_TYPES or river
    marine = water_body in MARINE_TYPES
    temperature = cell.get("temperature_c")
    # These are the positive supports of the existing guild temperature
    # windows, applied to annual air climate. They are proxy applicability
    # bounds, not measured water temperatures or universal survival limits.
    freshwater_thermal = _finite_number(temperature) and -10.0 < temperature < 38.0
    marine_thermal = _finite_number(temperature) and -11.0 < temperature < 37.0
    standing_inputs = (
        _finite_number(temperature) and -16.0 < temperature < 44.0
        and cell.get("aquatic_primary_climate_supported") is True
        and cell.get("fishery_productivity_supported") is True
        and _supported_index(cell.get("primary_productivity_index"))
        and _supported_index(cell.get("fishery_productivity_index"))
    )
    freshwater_supported = freshwater and freshwater_thermal and (
        _supported_index(cell.get("primary_productivity_index")) if river else standing_inputs
    )
    return {
        "species_terrestrial_habitat_eligible": terrestrial,
        "species_freshwater_habitat_eligible": freshwater,
        "species_marine_habitat_eligible": marine,
        "species_freshwater_fish_score_supported": freshwater_supported,
        "species_marine_fish_score_supported": marine and marine_thermal and standing_inputs,
        "species_freshwater_fishery_input_mode": (
            "river_inapplicable_omitted" if river else
            "standing_water_required" if freshwater else "not_applicable"
        ),
    }


def _habitat_applicability(cell: dict[str, Any]) -> dict[str, bool]:
    old = _legacy_habitat_support(cell)
    return {
        **{guild: old["species_terrestrial_habitat_eligible"] for guild in TERRESTRIAL_GUILDS},
        "freshwater_fish": old["species_freshwater_habitat_eligible"],
        "marine_fish": old["species_marine_habitat_eligible"],
        "reef_builder": True, "wetland_amphibian": True, "mangrove_coastal_bird": True,
    }


def _parent_inputs(cell: dict[str, Any]) -> dict[str, bool]:
    fields = {
        "primary": ("primary_productivity_supported", "primary_productivity_index"),
        "biomass": ("vegetation_biomass_supported", "vegetation_biomass_index"),
        "forest": ("forest_growth_supported", "forest_growth_index"),
        "richness": ("species_richness_supported", "species_richness_index"),
        "disturbance": ("ecosystem_disturbance_pressure_supported", "ecosystem_disturbance_pressure_index"),
        "fishery": ("fishery_productivity_supported", "fishery_productivity_index"),
    }
    known = {key: cell.get(flag) is True and _supported_index(cell.get(field)) for key, (flag, field) in fields.items()}
    known["biomass"] = known["biomass"] or (_is_aquatic_cell(cell) and _supported_index(cell.get("vegetation_biomass_index")) and cell["vegetation_biomass_index"] == 0)
    known["reef_growth"] = _supported_index(cell.get("reef_growth_index"))
    known["wetland"] = _supported_index(cell.get("wetland_extent_index"))
    known["biome_confidence"] = _supported_index(cell.get("biome_confidence_index"))
    river = _legacy_habitat_support(cell)["species_freshwater_fishery_input_mode"] == "river_inapplicable_omitted"
    known["standing_fishery_if_applicable"] = river or known["fishery"]
    return known


def _habitat_support(cell: dict[str, Any]) -> dict[str, Any]:
    fields = _legacy_habitat_support(cell)
    habitat, parents = _habitat_applicability(cell), _parent_inputs(cell)
    temperature = cell.get("temperature_c")
    for guild, dependencies in _SCORE_PARENTS.items():
        lower, upper = _OWN_TEMPERATURE_BOUNDS.get(guild, (None, None))
        thermal = _finite_number(temperature) and (lower is None or temperature > lower) and (upper is None or temperature < upper)
        fields[f"species_{guild}_score_supported"] = habitat[guild] and thermal and all(parents[key] for key in dependencies)
    fields["species_composition_confidence_supported"] = all(parents[key] for key in SPECIES_PARENT_MODEL["confidence_inputs"])
    fields["species_endemism_supported"] = all(parents[key] for key in SPECIES_PARENT_MODEL["endemism_inputs"])
    fields["species_record_descriptors_supported"] = fields["species_composition_confidence_supported"] and fields["species_endemism_supported"] and all(parents[key] for key in ("primary", "richness", "disturbance"))
    applicable = sum(habitat.values())
    supported = sum(fields[f"species_{guild}_score_supported"] for guild in GUILD_METADATA)
    fields["species_applicable_guild_count"] = applicable
    fields["species_supported_guild_count"] = supported
    fields["species_composition_status"] = "not_applicable" if applicable == 0 else "unavailable" if supported == 0 else "complete" if supported == applicable else "partial"
    return fields


def _guild_scores(cell: dict[str, Any]) -> dict[str, float]:
    biome = str(cell.get("biome", "unknown"))
    ecotone = str(cell.get("biome_ecotone_type", "none"))
    water_body = str(cell.get("water_body_type", "land"))
    support = _habitat_support(cell)
    temperature = float(cell.get("temperature_c", 0.0))
    precipitation = max(0.0, float(cell.get("precipitation_mm_y", 0.0)))
    aridity = _clamp(float(cell.get("seasonal_aridity_index", 0.0)))
    moisture = _clamp(float(cell.get("soil_moisture_index", 0.0)))
    primary = _clamp(float(cell.get("primary_productivity_index", 0.0)))
    biomass = _clamp(float(cell.get("vegetation_biomass_index", 0.0)))
    richness = _clamp(float(cell.get("species_richness_index", 0.0)))
    disturbance = _clamp(float(cell.get("ecosystem_disturbance_pressure_index", 0.0)))
    forest_growth = _clamp(float(cell.get("forest_growth_index", 0.0)))
    fishery = _clamp(float(cell.get("fishery_productivity_index", 0.0)))
    wetland = _clamp(float(cell.get("wetland_extent_index", 0.0)))
    reef = _clamp(float(cell.get("reef_growth_index", 0.0)))
    river_channel = _clamp(float(cell.get("river_channel_width_m", 0.0)) / 180.0)
    river_depth = _clamp(float(cell.get("river_channel_depth_m", 0.0)) / 9.0)
    elevation = float(cell.get("elevation_m", 0.0))
    ice = _clamp(float(cell.get("ice_thickness_m", 0.0)) / 800.0)
    permafrost = _clamp(float(cell.get("permafrost_extent_index", 0.0)))
    coastal = 0.0 if cell.get("marine_distance_status") == "no_marine_source" else _clamp(1.0 - float(cell.get("distance_to_marine_water_km", 9999.0)) / 80.0)
    temp_temperate = _temperature_window(temperature, 18.0, 24.0)
    temp_warm = _temperature_window(temperature, 25.0, 14.0)
    temp_cold = _clamp((8.0 - temperature) / 22.0)

    forest_bonus = 0.24 if biome in FOREST_BIOMES or "forest" in biome else 0.0
    grass_bonus = 0.24 if biome in GRASSLAND_BIOMES else 0.0
    desert_bonus = 0.30 if biome in DESERT_BIOMES else 0.0
    alpine_bonus = 0.28 if biome in ALPINE_BIOMES else 0.0
    river_fish = support["species_freshwater_fishery_input_mode"] == "river_inapplicable_omitted"
    freshwater_bonus = 0.30 if water_body in FRESHWATER_TYPES else (0.22 if river_fish else 0.0)
    # Wetland amphibian habitat has not migrated in this bounded correction.
    # Retain its original bonus independently of resident fish classification.
    legacy_amphibian_freshwater_bonus = 0.30 if water_body in {"fresh_lake", "inland_sea"} else (0.22 if bool(cell.get("is_river", False)) else 0.0)
    marine_bonus = 0.30 if water_body in MARINE_TYPES else 0.0
    reef_bonus = 0.34 if str(cell.get("reef_type", "none")) != "none" else 0.0
    mangrove_bonus = 0.34 if ecotone == "mangrove" or str(cell.get("wetland_system_type", "")) == "mangrove" else 0.0

    non_water_gate = 1.0 if support["species_terrestrial_habitat_eligible"] else 0.0
    scores = {
        "canopy_tree": non_water_gate
        * _clamp(
            forest_bonus
            + primary * 0.24
            + biomass * 0.28
            + forest_growth * 0.20
            + moisture * 0.12
            + temp_temperate * 0.10
            - disturbance * 0.14
            - aridity * 0.08
            - ice * 0.26
        ),
        "grassland_grazer": non_water_gate
        * _clamp(
            grass_bonus
            + primary * 0.24
            + richness * 0.16
            + _clamp(1.0 - abs(aridity - 0.45) / 0.45) * 0.18
            + temp_temperate * 0.12
            + _clamp(1.0 - biomass) * 0.08
            - disturbance * 0.10
            - ice * 0.22
        ),
        "desert_specialist": non_water_gate
        * _clamp(
            desert_bonus
            + aridity * 0.28
            + _clamp(1.0 - moisture) * 0.16
            + _clamp(1.0 - precipitation / 420.0) * 0.14
            + richness * 0.10
            - ice * 0.22
            - wetland * 0.24
        ),
        "alpine_tundra_specialist": non_water_gate
        * _clamp(
            alpine_bonus
            + temp_cold * 0.22
            + _clamp((elevation - 1200.0) / 2600.0) * 0.18
            + permafrost * 0.18
            + richness * 0.12
            - ice * 0.18
        ),
        "wetland_amphibian": _clamp(
            wetland * 0.34
            + _clamp(float(cell.get("wetland_hydrology_index", 0.0))) * 0.18
            + moisture * 0.12
            + richness * 0.14
            + temp_warm * 0.10
            + legacy_amphibian_freshwater_bonus * 0.18
            - aridity * 0.10
        ),
        "large_predator": non_water_gate
        * _clamp(
            richness * 0.28
            + biomass * 0.24
            + primary * 0.18
            + _clamp(1.0 - disturbance) * 0.18
            + forest_bonus * 0.10
            + grass_bonus * 0.10
            - ice * 0.26
        ),
        "freshwater_fish": _clamp(
            freshwater_bonus
            + (0.0 if river_fish else fishery * 0.30)
            + primary * 0.12
            + river_channel * 0.14
            + river_depth * 0.12
            + _temperature_window(temperature, 14.0, 24.0) * 0.10
            - ice * 0.22
        ) if support["species_freshwater_fish_score_supported"] else 0.0,
        "marine_fish": _clamp(
            marine_bonus
            + fishery * 0.42
            + primary * 0.14
            + _temperature_window(temperature, 13.0, 24.0) * 0.10
            + (0.08 if water_body == "continental_shelf" else 0.0)
            - ice * 0.18
        ) if support["species_marine_fish_score_supported"] else 0.0,
        "reef_builder": _clamp(reef_bonus + reef * 0.54 + fishery * 0.10 + temp_warm * 0.08 - ice * 0.22),
        "mangrove_coastal_bird": _clamp(
            mangrove_bonus
            + wetland * 0.22
            + coastal * 0.14
            + richness * 0.12
            + temp_warm * 0.12
            + _clamp(precipitation / 1600.0) * 0.10
            - disturbance * 0.08
        ),
    }
    return {guild: round(score, 6) if support[f"species_{guild}_score_supported"] else 0.0 for guild, score in scores.items()}


def _cell_endemism(cell: dict[str, Any], cells_by_id: dict[int, dict[str, Any]]) -> float:
    biome = str(cell.get("biome", "unknown"))
    neighbors = [
        cells_by_id[int(neighbor_id)]
        for neighbor_id in cell.get("neighbors", [])
        if int(neighbor_id) in cells_by_id
    ]
    same_biome_fraction = (
        sum(1 for neighbor in neighbors if str(neighbor.get("biome", "unknown")) == biome) / len(neighbors)
        if neighbors
        else 0.0
    )
    island_class = str(cell.get("island_class", "mainland"))
    island_score = {
        "islet": 0.42,
        "island": 0.34,
        "large_island": 0.24,
        "continental_island": 0.16,
    }.get(island_class, 0.0)
    ecotone = 0.22 if str(cell.get("biome_ecotone_type", "none")) != "none" else 0.0
    reef = _clamp(float(cell.get("reef_growth_index", 0.0))) * 0.16
    wetland = _clamp(float(cell.get("wetland_extent_index", 0.0))) * 0.12
    elevation = _clamp((float(cell.get("elevation_m", 0.0)) - 1500.0) / 3000.0) * 0.14
    isolation = _clamp(1.0 - same_biome_fraction) * 0.24
    disturbance_penalty = _clamp(float(cell.get("ecosystem_disturbance_pressure_index", 0.0))) * 0.10
    return _clamp(island_score + ecotone + reef + wetland + elevation + isolation - disturbance_penalty)


def _cell_confidence(cell: dict[str, Any]) -> float:
    biome_confidence = _clamp(float(cell.get("biome_confidence_index", 0.0)))
    richness = _clamp(float(cell.get("species_richness_index", 0.0)))
    productivity = _clamp(float(cell.get("primary_productivity_index", 0.0)))
    wetland_or_reef = max(_clamp(float(cell.get("wetland_extent_index", 0.0))), _clamp(float(cell.get("reef_growth_index", 0.0))))
    disturbance = _clamp(float(cell.get("ecosystem_disturbance_pressure_index", 0.0)))
    return _clamp(biome_confidence * 0.30 + richness * 0.22 + productivity * 0.20 + wetland_or_reef * 0.12 + (1.0 - disturbance) * 0.16)


def _mean(component: list[dict[str, Any]], key: str) -> float:
    if not component:
        return 0.0
    return sum(float(cell.get(key, 0.0)) for cell in component) / len(component)


def _linked_ids(component: list[dict[str, Any]], key: str) -> list[int]:
    return sorted({int(cell.get(key, -1)) for cell in component if int(cell.get(key, -1)) >= 0})


def _habitat_evidence(component: list[dict[str, Any]], guild: str) -> dict[str, float]:
    cell_count = len(component) or 1
    evidence = {
        "mean_wetland_extent_index": round(_mean(component, "wetland_extent_index"), 6),
        "mean_reef_growth_index": round(_mean(component, "reef_growth_index"), 6),
        "river_cell_fraction": round(sum(1 for cell in component if bool(cell.get("is_river", False))) / cell_count, 6),
        "water_cell_fraction": round(sum(1 for cell in component if _is_aquatic_cell(cell)) / cell_count, 6),
        "coastal_cell_fraction": round(
            sum(1 for cell in component if cell.get("marine_distance_status") != "no_marine_source" and float(cell.get("distance_to_marine_water_km", 9999.0)) <= 80.0) / cell_count,
            6,
        ),
    }

    if guild in {"marine_fish", "reef_builder"} or (guild == "freshwater_fish" and all(cell["species_freshwater_fishery_input_mode"] == "standing_water_required" for cell in component)):
        evidence["mean_fishery_productivity_index"] = round(_mean(component, "fishery_productivity_index"), 6)
    if guild == "canopy_tree":
        evidence["mean_forest_growth_index"] = round(_mean(component, "forest_growth_index"), 6)
    return evidence


def _build_species_ranges(world: dict[str, Any], *, prescribed_natural: bool = False) -> dict[str, Any]:
    if not isinstance(world, dict):
        raise ValueError("species ranges require a world object before enrichment")
    if "species_ranges_model" in world and not any(
        _same_model_metadata(world["species_ranges_model"], known)
        for known in (_SPECIES_V2_MODEL, SPECIES_PARENT_MODEL, NATURAL_SPECIES_PARENT_MODEL)
    ):
        raise ValueError("species ranges require exact known model metadata before enrichment")
    if "ecosystem_dynamics_model" in world and not any(
        _same_model_metadata(world["ecosystem_dynamics_model"], known)
        for known in _ECOSYSTEM_MODELS.values()
    ):
        raise ValueError("species ranges require exact known ecosystem model metadata before enrichment")
    cells = world.get("cells", [])
    if not isinstance(cells, list):
        raise ValueError("species ranges require a cell list before enrichment")
    if "summary" in world and not isinstance(world["summary"], dict):
        raise ValueError("species ranges require a summary object before enrichment")
    if not cells and not prescribed_natural:
        return world
    parent_model = world.get("ecosystem_dynamics_model")
    expected_parent = "heuristic_ecosystem_climate_support_v5" if prescribed_natural else "heuristic_ecosystem_climate_support_v4"
    if not isinstance(parent_model, dict) or parent_model.get("model") != expected_parent:
        raise ValueError("species parent support requires declared " + expected_parent + " before enrichment" if prescribed_natural else "species parent support requires declared ecosystem parent model v4 before enrichment")
    parent_errors = validate_aquatic_climate_support(world)
    if parent_errors:
        raise ValueError("species parent support requires valid ecosystem parents: " + parent_errors[0])
    marine_contract = require_marine_distance(world)
    cell_ids = {cell["id"] for cell in cells}
    # Every range exports an annual climate envelope. Fail before publishing
    # metadata, cell fields or partial records if that source is unavailable.
    for cell in cells:
        if not isinstance(cell, dict) or not _finite_number(cell.get("temperature_c")):
            raise ValueError("species ranges require finite numeric annual temperature_c before enrichment")
        for key in (
            "primary_productivity_index", "fishery_productivity_index", "vegetation_biomass_index",
            "species_richness_index", "ecosystem_disturbance_pressure_index", "forest_growth_index",
            "reef_growth_index", "wetland_extent_index", "biome_confidence_index",
            "precipitation_mm_y", "seasonal_aridity_index", "soil_moisture_index",
            "wetland_hydrology_index", "river_channel_width_m", "river_channel_depth_m",
            "elevation_m", "ice_thickness_m", "permafrost_extent_index",
            "distance_to_marine_water_km", "area_km2", "lat_deg", "lon_deg",
        ):
            if key == "distance_to_marine_water_km" and marine_contract:
                continue
            if key in cell and not _finite_number(cell[key]):
                raise ValueError(f"species ranges require finite numeric {key} when present before enrichment")
        for key in ("wetland_system_id", "reef_system_id", "aquifer_system_id", "basin_id"):
            if key in cell and (type(cell[key]) is not int or cell[key] < -1):
                raise ValueError(f"species ranges require integer {key} >= -1 when present before enrichment")
        neighbors = cell.get("neighbors", [])
        if not isinstance(neighbors, list) or any(type(i) is not int or i not in cell_ids for i in neighbors):
            raise ValueError("species ranges require valid integer neighbor IDs before enrichment")
    world["species_ranges_model"] = deepcopy(NATURAL_SPECIES_PARENT_MODEL if prescribed_natural else SPECIES_PARENT_MODEL)

    cells_by_id = {int(cell.get("id", -1)): cell for cell in cells if isinstance(cell, dict)}
    candidate_ids_by_guild: dict[str, set[int]] = {guild: set() for guild in GUILD_METADATA}
    scores_by_cell: dict[int, dict[str, float]] = {}
    dominant_counts: Counter[str] = Counter()
    suitability_sum = 0.0
    endemism_sum = 0.0
    confidence_sum = 0.0

    for cell in cells:
        cell_id = int(cell.get("id", -1))
        cell.update(_habitat_support(cell))
        scores = _guild_scores(cell)
        scores_by_cell[cell_id] = scores
        available_scores = [(guild, score) for guild, score in scores.items() if cell[f"species_{guild}_score_supported"]]
        dominant_guild, dominant_score = sorted(available_scores, key=lambda item: (-item[1], item[0]))[0] if available_scores else ("none", 0.0)
        if dominant_score < 0.25:
            dominant_guild = "none"
        endemism = _cell_endemism(cell, cells_by_id) if cell["species_endemism_supported"] else 0.0
        confidence = _cell_confidence(cell) if cell["species_composition_confidence_supported"] else 0.0
        guild_richness = sum(1 for _guild, score in available_scores if score >= SPECIES_RANGE_THRESHOLD)
        cell["species_guild_scores"] = dict(scores)

        cell["dominant_species_guild"] = dominant_guild
        cell["species_habitat_suitability_index"] = round(dominant_score, 6)
        cell["species_endemism_index"] = round(endemism, 6)
        cell["species_range_fragmentation_index"] = 0.0
        cell["species_composition_confidence_index"] = round(confidence, 6)
        cell["species_guild_richness_count"] = guild_richness
        cell["species_range_record_ids"] = []

        dominant_counts[dominant_guild] += 1
        suitability_sum += dominant_score
        endemism_sum += endemism
        confidence_sum += confidence

        for guild, score in scores.items():
            if cell[f"species_{guild}_score_supported"] and cell["species_record_descriptors_supported"] and score >= SPECIES_RANGE_THRESHOLD and cell_id >= 0:
                candidate_ids_by_guild[guild].add(cell_id)

    records: list[dict[str, Any]] = []
    guild_counts: Counter[str] = Counter()
    habitat_counts: Counter[str] = Counter()
    high_endemism_count = 0
    high_stress_count = 0

    for guild in sorted(GUILD_METADATA):
        habitat_class, trophic_role = GUILD_METADATA[guild]
        for component in _connected_components(candidate_ids_by_guild[guild], cells_by_id):
            record_id = len(records)
            cell_ids = [int(cell.get("id", -1)) for cell in component]
            for cell in component:
                cell["species_range_record_ids"].append(record_id)
            area = sum(max(0.0, float(cell.get("area_km2", 0.0))) for cell in component)
            fragmentation = _range_fragmentation(component)
            mean_endemism = _mean(component, "species_endemism_index")
            mean_confidence = _mean(component, "species_composition_confidence_index")
            mean_disturbance = _mean(component, "ecosystem_disturbance_pressure_index")
            small_range_bonus = _clamp((800000.0 - area) / 800000.0) * 0.18
            record_endemism = _clamp(mean_endemism * 0.72 + fragmentation * 0.18 + small_range_bonus)
            stress = _clamp(mean_disturbance * 0.38 + fragmentation * 0.22 + (1.0 - mean_confidence) * 0.22 + record_endemism * 0.18)
            temperatures = [float(cell.get("temperature_c", 0.0)) for cell in component]
            precipitations = [max(0.0, float(cell.get("precipitation_mm_y", 0.0))) for cell in component]
            centroid_lat, centroid_lon = _centroid(component)
            biome_counts = Counter(str(cell.get("biome", "unknown")) for cell in component)
            ecotone_counts = Counter(str(cell.get("biome_ecotone_type", "none")) for cell in component)
            water_body_counts = Counter(str(cell.get("water_body_type", "land")) for cell in component)

            record = {
                "id": record_id,
                "guild_type": guild,
                "habitat_class": habitat_class,
                "trophic_role": trophic_role,
                "cell_count": len(component),
                "cell_ids": cell_ids,
                "area_km2": round(area, 6),
                "centroid_lat_deg": centroid_lat,
                "centroid_lon_deg": centroid_lon,
                "dominant_biome": _primary_key(biome_counts, "unknown"),
                "dominant_ecotone_type": _primary_key(ecotone_counts, "none"),
                "dominant_water_body_type": _primary_key(water_body_counts, "land"),
                "mean_habitat_suitability_index": round(
                    sum(scores_by_cell[int(cell.get("id", -1))][guild] for cell in component) / len(component),
                    6,
                ),
                "max_habitat_suitability_index": round(
                    max(scores_by_cell[int(cell.get("id", -1))][guild] for cell in component),
                    6,
                ),
                "mean_species_richness_index": round(_mean(component, "species_richness_index"), 6),
                "mean_primary_productivity_index": round(_mean(component, "primary_productivity_index"), 6),
                "mean_disturbance_pressure_index": round(mean_disturbance, 6),
                "mean_composition_confidence_index": round(mean_confidence, 6),
                "mean_temperature_c": round(sum(temperatures) / len(temperatures), 6),
                "mean_precipitation_mm_y": round(sum(precipitations) / len(precipitations), 6),
                "range_fragmentation_index": round(fragmentation, 6),
                "endemism_index": round(record_endemism, 6),
                "conservation_stress_index": round(stress, 6),
                "climate_envelope": {
                    "min_temperature_c": round(min(temperatures), 6),
                    "mean_temperature_c": round(sum(temperatures) / len(temperatures), 6),
                    "max_temperature_c": round(max(temperatures), 6),
                    "min_precipitation_mm_y": round(min(precipitations), 6),
                    "mean_precipitation_mm_y": round(sum(precipitations) / len(precipitations), 6),
                    "max_precipitation_mm_y": round(max(precipitations), 6),
                },
                "habitat_evidence": _habitat_evidence(component, guild),
                "wetland_system_ids": _linked_ids(component, "wetland_system_id"),
                "reef_system_ids": _linked_ids(component, "reef_system_id"),
                "aquifer_system_ids": _linked_ids(component, "aquifer_system_id"),
                "river_basin_ids": _linked_ids(component, "basin_id"),
            }
            records.append(record)
            guild_counts[guild] += 1
            habitat_counts[habitat_class] += 1
            high_endemism_count += 1 if record_endemism >= 0.60 else 0
            high_stress_count += 1 if stress >= 0.60 else 0

    for record in records:
        fragmentation = float(record.get("range_fragmentation_index", 0.0))
        for cell_id in record.get("cell_ids", []):
            cell = cells_by_id.get(int(cell_id))
            if cell is None:
                continue
            cell["species_range_fragmentation_index"] = round(
                max(float(cell.get("species_range_fragmentation_index", 0.0)), fragmentation),
                6,
            )

    range_cell_ids = {
        int(cell.get("id", -1))
        for cell in cells
        if isinstance(cell.get("species_range_record_ids", []), list) and cell.get("species_range_record_ids", [])
    }
    summary = world.setdefault("summary", {})
    cell_count = len(cells) or 1
    summary["species_range_record_count"] = len(records)
    summary["species_range_cell_count"] = len(range_cell_ids)
    summary["terrestrial_species_range_count"] = sum(
        1 for record in records if str(record.get("habitat_class", "")) in {"terrestrial", "arid", "alpine"}
    )
    summary["aquatic_species_range_count"] = sum(
        1 for record in records if str(record.get("habitat_class", "")) in {"freshwater", "marine", "reef"}
    )
    summary["wetland_species_range_count"] = habitat_counts.get("wetland", 0)
    summary["high_endemism_species_range_count"] = high_endemism_count
    summary["high_conservation_stress_species_range_count"] = high_stress_count
    summary["species_range_total_area_km2"] = round(sum(float(record.get("area_km2", 0.0)) for record in records), 6)
    summary["mean_species_habitat_suitability_index"] = round(suitability_sum / cell_count, 6)
    summary["mean_species_endemism_index"] = round(endemism_sum / cell_count, 6)
    summary["mean_species_composition_confidence_index"] = round(confidence_sum / cell_count, 6)
    summary["species_guild_type_counts"] = dict(sorted(guild_counts.items()))
    summary["species_habitat_class_counts"] = dict(sorted(habitat_counts.items()))
    summary["dominant_species_guild_counts"] = dict(sorted(dominant_counts.items()))
    summary["species_score_supported_cell_counts"] = {guild: sum(cell[f"species_{guild}_score_supported"] for cell in cells) for guild in sorted(GUILD_METADATA)}
    for flag in ("species_composition_confidence_supported", "species_endemism_supported", "species_record_descriptors_supported"):
        summary[flag + "_cell_count"] = sum(cell[flag] for cell in cells)
    summary["species_composition_status_counts"] = dict(sorted(Counter(cell["species_composition_status"] for cell in cells).items()))
    world["species_range_records"] = records
    return world



def enrich_world_with_species_ranges(world: dict[str, Any]) -> dict[str, Any]:
    """Preserve historical dispatch; stage/audit/commit only the matched E5 child."""
    from .species_habitat_validation import (
        PRESCRIBED_SPECIES_CELL_FIELDS as cell_fields,
        PRESCRIBED_SPECIES_SUMMARY_FIELDS as summary_fields,
        validate_prescribed_species_inputs, validate_species_habitat_support,
    )
    if not isinstance(world, dict):
        raise ValueError("species ranges require a world object before enrichment")
    own = world.get("species_ranges_model")
    parent = world.get("ecosystem_dynamics_model")
    natural_parent = isinstance(parent, dict) and parent.get("model") == "heuristic_ecosystem_climate_support_v5"
    natural_own = isinstance(own, dict) and own.get("model") == "heuristic_species_parent_support_v4"
    if not (natural_parent or natural_own):
        return _build_species_ranges(world)
    if "species_ranges_model" in world:
        if not _same_model_metadata(own, NATURAL_SPECIES_PARENT_MODEL):
            raise ValueError("prescribed natural species requires exact matching own v4; clear audited historical outputs before migration")
    else:
        cells, summary = world.get("cells"), world.get("summary", {})
        partial = "species_range_records" in world or (isinstance(summary, dict) and any(k in summary for k in summary_fields))
        partial = partial or (isinstance(cells, list) and any(isinstance(c, dict) and any(k in c for k in cell_fields) for c in cells))
        if partial:
            raise ValueError("prescribed natural species: undeclared owned outputs; audit and clear before migration")
    validate_prescribed_species_inputs(world)
    staged = {**world, "cells": [dict(c) for c in world["cells"]], "summary": dict(world.get("summary", {}))}
    try:
        _build_species_ranges(staged, prescribed_natural=True)
        errors = validate_species_habitat_support(staged)
        if errors:
            raise ValueError(errors[0])
    except (TypeError, ValueError, KeyError, ArithmeticError, AttributeError) as error:
        raise ValueError(("prescribed natural species: " + str(error))[:600]) from error
    for cell, result in zip(world["cells"], staged["cells"]):
        cell.update({key: result[key] for key in cell_fields})
    world["species_ranges_model"] = staged["species_ranges_model"]
    world["species_range_records"] = staged["species_range_records"]
    world.setdefault("summary", {}).update({key: staged["summary"][key] for key in summary_fields})
    return world
