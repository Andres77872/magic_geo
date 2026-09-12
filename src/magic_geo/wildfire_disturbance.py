from __future__ import annotations

import math
from collections import Counter
from typing import Any

from .ecosystem_dynamics import _is_aquatic_cell
from .climate_model_dispatch import ecology_uses_native_seasonal_climate


IGNITION_THRESHOLD = 0.28
SPREAD_THRESHOLD = 0.30
HIGH_FUEL_THRESHOLD = 0.35
HIGH_FIREBREAK_THRESHOLD = 0.55
MAX_EVENT_COUNT = 96
MAX_SPREAD_STEPS = 6
MAX_EVENT_CELLS = 96

LEGACY_WILDFIRE_MODEL = {
    "model": "heuristic_wildfire_aquatic_exclusion_v2",
    "aquatic_selector": "is_water_or_is_lake_or_fishery_water_body_type",
    "aquatic_fire_policy": "zero_fuel_ignition_and_spread_non_burnable_no_history",
    "neighbor_fuel_policy": "terrestrial_biomass_neighbors",
    "ignition_model": "legacy_energy_aridity_fuel_wind_settlement_proxy_v1",
}
NATIVE_WILDFIRE_MODEL = {
    **LEGACY_WILDFIRE_MODEL,
    "model": "heuristic_wildfire_native_seasonal_v3",
    "ignition_model": "aridity_fuel_wind_settlement_susceptibility_without_energy_stress_v1",
    "lightning_model": "not_modelled",
    "energy_stress_input_policy": "omitted_without_substitute",
    "remaining_ignition_weights": "unchanged_without_renormalization",
    "history_interpretation": "heuristic_disturbance_scenario_not_observed_fire_or_lightning",
    "climate_input_policy": "requires_known_native_identity_and_upstream_energy_enrichment",
}

_AVAILABILITY_POLICY = {
    "ecosystem_parent_model": "heuristic_ecosystem_climate_support_v4",
    "fuel_input_policy": "own_supported_primary_biomass_ecosystem_risk_and_every_terrestrial_neighbor_biomass",
    "neighbor_availability_policy": "one_hop_biomass_not_recursive_neighbor_fuel",
    "neighbor_denominator_policy": "all_declared_neighbors_aquatic_known_excluded_zero_no_renormalization",
    "firebreak_input_policy": "requires_available_fuel_no_unknown_as_sparse_fuel",
    "ignition_input_policy": "requires_available_fuel_firebreak_and_own_ecosystem_risk_disturbance",
    "aquatic_availability_policy": "known_excluded_fuel_zero_ignition_zero_firebreak_one_all_three_supported",
    "unsupported_estimate_policy": "numeric_zero_with_false_support_flag_not_physical_absence_or_barrier",
    "unsupported_regime": "fuel_proxy_unavailable_before_ice_or_sparse_fuel_classification_aquatic_rule_independent",
    "spread_input_policy": "no_seed_or_source_target_spread_comparison_without_available_inputs",
    "front_coverage_policy": "all_burned_active_front_adjacency_with_explicit_directed_unmodelled_edges",
    "containment_scope": "coefficient_index_on_modelled_cells_not_physical_containment",
    "summary_availability_policy": "all_cell_means_include_unavailable_zero_sentinels_with_supported_counts",
    "counter_policy": "supported_estimates_only_existing_six_decimal_thresholds",
    "fire_support_scope": "existing_parent_dependent_proxy_no_new_fire_temperature_or_dead_fuel_model",
}
PARENT_WILDFIRE_MODEL = {
    **LEGACY_WILDFIRE_MODEL, **_AVAILABILITY_POLICY,
    "model": "heuristic_wildfire_parent_availability_v4",
}
NATIVE_PARENT_WILDFIRE_MODEL = {
    **NATIVE_WILDFIRE_MODEL, **_AVAILABILITY_POLICY,
    "model": "heuristic_wildfire_native_seasonal_parent_availability_v5",
}

_NATURAL_ACTIVITY_POLICY = {
    "ecosystem_parent_model": "heuristic_ecosystem_climate_support_v5",
    "activity_forcing_policy": "prescribed_natural_scenario_without_anthropogenic_activity_input",
    "settlement_score_input_policy": "not_read_omitted_without_substitute_or_renormalization",
    "activity_scope": "scenario_boundary_not_inferred_absence_of_people_or_observed_fire",
    "physical_input_policy": "explicit_finite_consumed_descriptors_typed_habitat_and_reciprocal_complete_graph_no_missing_value_substitution",
}
NATURAL_PARENT_WILDFIRE_MODEL = {
    **PARENT_WILDFIRE_MODEL, **_NATURAL_ACTIVITY_POLICY,
    "model": "heuristic_wildfire_prescribed_natural_parent_availability_v6",
    "ignition_model": "legacy_energy_aridity_fuel_wind_prescribed_natural_proxy_without_settlement_v1",
}
NATIVE_NATURAL_PARENT_WILDFIRE_MODEL = {
    **NATIVE_PARENT_WILDFIRE_MODEL, **_NATURAL_ACTIVITY_POLICY,
    "model": "heuristic_wildfire_native_seasonal_prescribed_natural_parent_availability_v7",
    "ignition_model": "aridity_fuel_wind_prescribed_natural_susceptibility_without_settlement_v1",
}


_PARENT_FIELDS = (
    ("primary_productivity_index", "primary_productivity_supported"),
    ("vegetation_biomass_index", "vegetation_biomass_supported"),
    ("wildfire_spread_risk_index", "ecosystem_wildfire_spread_risk_supported"),
    ("ecosystem_disturbance_pressure_index", "ecosystem_disturbance_pressure_supported"),
)
_SUPPORT_FIELDS = (
    "wildfire_fuel_continuity_supported", "wildfire_firebreak_supported",
    "wildfire_ignition_potential_supported",
)
_PARENT_MARKERS = ("terrestrial_primary_climate_supported", "primary_productivity_supported",
    "vegetation_biomass_supported", "ecosystem_wildfire_spread_risk_supported",
    "ecosystem_disturbance_pressure_supported")


def _finite_input(value: Any, context: str) -> float:
    if type(value) not in (int, float):
        raise ValueError(f"wildfire {context} must be a finite number")
    try:
        result = float(value)
    except OverflowError as error:
        raise ValueError(f"wildfire {context} must be a finite number") from error
    if not math.isfinite(result):
        raise ValueError(f"wildfire {context} must be a finite number")
    return result


def _parent_availability(world: dict[str, Any], *, native_seasonal: bool, prescribed_natural: bool = False) -> dict[int, tuple[bool, bool, bool]] | None:
    """Validate the frozen upstream contract before any fire output mutation."""
    parent = world.get("ecosystem_dynamics_model")
    cells = world.get("cells", [])
    if parent is None and "ecosystem_dynamics_model" not in world:
        if isinstance(cells, list) and any(isinstance(c, dict) and (
            any(k in c for k in _PARENT_MARKERS + _SUPPORT_FIELDS)
        ) for c in cells):
            raise ValueError("wildfire parent availability requires its ecosystem declaration")
        return None
    name = parent.get("model") if isinstance(parent, dict) else None
    if prescribed_natural:
        from .aquatic_climate_validation import _EXPECTED_MODELS
        expected = _EXPECTED_MODELS["heuristic_ecosystem_climate_support_v5"]
    else:
        expected = _PARENT_MODELS.get(name) if isinstance(name, str) else None
    if expected is None or parent != expected:
        raise ValueError("wildfire requires exact known ecosystem parent metadata")
    if name != ("heuristic_ecosystem_climate_support_v5" if prescribed_natural else "heuristic_ecosystem_climate_support_v4"):
        if isinstance(cells, list) and any(isinstance(c, dict) and (
            any(k in c for k in _PARENT_MARKERS + _SUPPORT_FIELDS)
        ) for c in cells):
            raise ValueError("wildfire parent availability fields do not match historical ecosystem metadata")
        return None
    if not isinstance(cells, list) or any(not isinstance(c, dict) for c in cells):
        raise ValueError("wildfire parent availability requires valid cells")
    by_id = {}
    own_available = {}
    biomass_available = {}
    disturbance_available = {}
    for cell in cells:
        cell_id = cell.get("id")
        if type(cell_id) is not int or cell_id < 0 or cell_id in by_id:
            raise ValueError("wildfire requires unique nonnegative integer cell IDs")
        by_id[cell_id] = cell
        aquatic = _is_aquatic_cell(cell)
        temperature = cell.get("temperature_c")
        # This reconstructs the declared upstream annual proxy, not a fire
        # thermal envelope. Invalid annual inputs are explicitly unavailable.
        primary = isinstance(temperature, (int, float)) and not isinstance(temperature, bool) and -16.0 < temperature < 52.0
        biomass = not aquatic and primary
        risk = aquatic or biomass
        expected_flags = (primary, biomass, risk, risk)
        for (field, flag), supported in zip(_PARENT_FIELDS, expected_flags):
            if type(cell.get(flag)) is not bool or cell[flag] != supported:
                raise ValueError(f"wildfire cell {cell_id}: inconsistent parent {flag}")
            value = _finite_input(cell.get(field), f"cell {cell_id} {field}")
            if not 0 <= value <= 1 or (not supported and value != 0):
                raise ValueError(f"wildfire cell {cell_id}: invalid parent {field}")
        if aquatic and cell["vegetation_biomass_index"] != 0:
            raise ValueError(f"wildfire cell {cell_id}: aquatic biomass must be structural zero")
        own_available[cell_id] = all(expected_flags[:3])
        disturbance_available[cell_id] = expected_flags[3]
        biomass_available[cell_id] = biomass
        fields = (
            "seasonal_aridity_index", "wetland_extent_index", "ice_thickness_m",
            "floodplain_connectivity_index", "wind_east", "wind_north",
            "lat_deg", "lon_deg", "elevation_m", "area_km2",
        ) + (() if prescribed_natural else ("settlement_score",)) + (() if native_seasonal else ("climate_energy_stress_index",))
        for field in fields:
            _finite_input(cell.get(field, 0.0), f"cell {cell_id} {field}")
        if not -90 <= cell.get("lat_deg", 0.0) <= 90 or not -180 <= cell.get("lon_deg", 0.0) <= 180:
            raise ValueError(f"wildfire cell {cell_id}: invalid canonical latitude/longitude")
        if "biome" in cell and not isinstance(cell["biome"], str):
            raise ValueError(f"wildfire cell {cell_id}: biome must be a string descriptor")
        if not math.isfinite(math.hypot(cell.get("wind_east", 0.0), cell.get("wind_north", 0.0))):
            raise ValueError(f"wildfire cell {cell_id}: wind magnitude exceeds finite range")
    available = {}
    for cell_id, cell in by_id.items():
        neighbors = cell.get("neighbors", [])
        if not isinstance(neighbors, list) or any(type(n) is not int or n not in by_id or n == cell_id for n in neighbors) or len(neighbors) != len(set(neighbors)):
            raise ValueError(f"wildfire cell {cell_id}: invalid complete neighbor list")
        aquatic = _is_aquatic_cell(cell)
        fuel = aquatic or (own_available[cell_id] and all(
            _is_aquatic_cell(by_id[n]) or biomass_available[n] for n in neighbors
        ))
        available[cell_id] = (fuel, fuel, aquatic or (fuel and disturbance_available[cell_id]))
    return available


def _available_fire_cell(cell: dict[str, Any]) -> bool:
    return all(cell.get(field) is True for field in _SUPPORT_FIELDS)


def _front_coverage(active_ids: set[int], cells_by_id: dict[int, dict[str, Any]]) -> dict[str, Any]:
    unknown = set()
    known = set()
    for source_id in active_ids:
        for target in _neighbors(cells_by_id[source_id], cells_by_id):
            pair = (source_id, target["id"])
            (known if _is_aquatic_cell(target) or _available_fire_cell(target) else unknown).add(pair)
    return {
        "front_coverage_status": "partial_unavailable_inputs" if unknown else "complete_for_examined_adjacency",
        "unmodelled_adjacent_cell_ids": sorted({target for _, target in unknown}),
        "unmodelled_front_cell_ids": sorted({source for source, _ in unknown}),
        "unmodelled_front_edges": [{"from_cell_id": a, "to_cell_id": b} for a, b in sorted(unknown)],
        "unmodelled_front_edge_count": len(unknown),
        "supported_front_edge_count": len(known),
    }


# Frozen parent identities: downstream preflight does not run ecosystem again.
_PARENT_MODELS = {'heuristic_ecosystem_climate_support_v2': {'model': 'heuristic_ecosystem_climate_support_v2',
                                            'aquatic_temperature_source': 'annual_surface_air_climate_proxy',
                                            'aquatic_selector': 'is_water_or_is_lake_or_fishery_water_body_type',
                                            'fishery_water_body_types': ['continental_shelf',
                                                                         'fresh_lake',
                                                                         'inland_sea',
                                                                         'ocean'],
                                            'aquatic_primary_minimum_temperature_c': -16.0,
                                            'aquatic_primary_maximum_temperature_c': 52.0,
                                            'fishery_minimum_temperature_c': -20.0,
                                            'fishery_maximum_temperature_c': 44.0,
                                            'temperature_bounds': 'exclusive',
                                            'support_relationship': 'fishery_estimate_requires_own_climate_and_supported_primary_input',
                                            'monthly_temperature_policy': 'not_used',
                                            'invalid_annual_temperature_policy': 'unsupported_without_numeric_coercion',
                                            'unsupported_productivity_policy': 'numeric_zero_with_false_support_flag',
                                            'unsupported_fishery_record_policy': 'no_record_without_supported_fishery_productivity',
                                            'support_scope': 'empirical_climate_proxy_not_aquatic_survival_limits'},
 'heuristic_ecosystem_climate_support_v3': {'model': 'heuristic_ecosystem_climate_support_v3',
                                            'aquatic_temperature_source': 'annual_surface_air_climate_proxy',
                                            'aquatic_selector': 'is_water_or_is_lake_or_fishery_water_body_type',
                                            'fishery_water_body_types': ['continental_shelf',
                                                                         'fresh_lake',
                                                                         'inland_sea',
                                                                         'ocean'],
                                            'aquatic_primary_minimum_temperature_c': -16.0,
                                            'aquatic_primary_maximum_temperature_c': 52.0,
                                            'fishery_minimum_temperature_c': -20.0,
                                            'fishery_maximum_temperature_c': 44.0,
                                            'temperature_bounds': 'exclusive',
                                            'support_relationship': 'fishery_estimate_requires_own_climate_and_supported_primary_input',
                                            'monthly_temperature_policy': 'not_used',
                                            'invalid_annual_temperature_policy': 'unsupported_without_numeric_coercion',
                                            'unsupported_productivity_policy': 'numeric_zero_with_false_support_flag',
                                            'unsupported_fishery_record_policy': 'no_record_without_supported_fishery_productivity',
                                            'support_scope': 'empirical_climate_proxy_not_aquatic_survival_limits',
                                            'aquatic_ecology_policy': 'shared_aquatic_selector_for_primary_and_terrestrial_exclusion'},
 'heuristic_ecosystem_climate_support_v4': {'model': 'heuristic_ecosystem_climate_support_v4',
                                            'aquatic_temperature_source': 'annual_surface_air_climate_proxy',
                                            'aquatic_selector': 'is_water_or_is_lake_or_fishery_water_body_type',
                                            'fishery_water_body_types': ['continental_shelf',
                                                                         'fresh_lake',
                                                                         'inland_sea',
                                                                         'ocean'],
                                            'aquatic_primary_minimum_temperature_c': -16.0,
                                            'aquatic_primary_maximum_temperature_c': 52.0,
                                            'fishery_minimum_temperature_c': -20.0,
                                            'fishery_maximum_temperature_c': 44.0,
                                            'temperature_bounds': 'exclusive',
                                            'support_relationship': 'fishery_estimate_requires_own_climate_and_supported_primary_input',
                                            'monthly_temperature_policy': 'not_used',
                                            'invalid_annual_temperature_policy': 'unsupported_without_numeric_coercion',
                                            'unsupported_productivity_policy': 'numeric_zero_with_false_support_flag',
                                            'unsupported_fishery_record_policy': 'no_record_without_supported_fishery_productivity',
                                            'support_scope': 'empirical_climate_proxy_not_aquatic_survival_limits',
                                            'aquatic_ecology_policy': 'shared_aquatic_selector_for_primary_and_terrestrial_exclusion',
                                            'terrestrial_temperature_source': 'annual_surface_air_climate_proxy',
                                            'terrestrial_selector': 'complement_of_shared_aquatic_selector',
                                            'terrestrial_primary_minimum_temperature_c': -16.0,
                                            'terrestrial_primary_maximum_temperature_c': 52.0,
                                            'terrestrial_support_scope': 'existing_annual_primary_proxy_not_plant_survival_biome_phenology_crop_or_fuel_limits',
                                            'primary_availability_policy': 'supported_aquatic_or_terrestrial_climate_input',
                                            'terrestrial_dependency_policy': 'biomass_requires_supported_terrestrial_primary_forest_and_succession_require_supported_primary_biomass_and_disturbance',
                                            'unsupported_terrestrial_estimate_policy': 'numeric_zero_with_false_support_flag_not_observed_physical_zero',
                                            'unsupported_terrestrial_succession_policy': 'terrestrial_primary_proxy_unavailable_zero_recovery_years_no_history',
                                            'unsupported_forest_record_policy': 'no_record_without_supported_forest_growth',
                                            'summary_availability_policy': 'all_cell_means_include_unavailable_zero_sentinels_with_supported_cell_counts',
                                            'species_richness_availability_policy': 'requires_supported_primary_and_terrestrial_biomass_or_aquatic_structural_zero',
                                            'ecosystem_wildfire_availability_policy': 'requires_supported_terrestrial_biomass_aquatic_risk_is_known_zero',
                                            'ecosystem_disturbance_availability_policy': 'requires_supported_ecosystem_wildfire_risk_aquatic_descriptors_remain_applicable',
                                            'vegetation_recovery_availability_policy': 'requires_supported_primary_and_disturbance_and_terrestrial_biomass_or_aquatic_structural_zero',
                                            'renewable_record_availability_policy': 'requires_supported_resource_productivity_primary_disturbance_recovery_and_terrestrial_biomass_or_aquatic_structural_zero',
                                            'unsupported_parent_estimate_policy': 'numeric_zero_with_false_support_flag_not_absence_damage_or_physical_nonburnability',
                                            'ecosystem_disturbance_input_scope': 'static_empirical_fire_frequency_aridity_ecotone_erosion_settlement_wind_descriptors_not_observed_fire_or_final_wildfire_feedback',
                                            'aquatic_biomass_input_policy': 'structural_zero_for_aquatic_richness_recovery_and_renewable_inputs_not_terrestrial_biomass_estimate'}}


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _primary_key(counter: Counter[str], fallback: str) -> str:
    if not counter:
        return fallback
    return sorted(counter.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _neighbors(cell: dict[str, Any], cells_by_id: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    return [cells_by_id[int(neighbor_id)] for neighbor_id in cell.get("neighbors", []) if int(neighbor_id) in cells_by_id]


def _wind_alignment(cell: dict[str, Any], neighbor: dict[str, Any]) -> float:
    lat_a = math.radians(float(cell.get("lat_deg", 0.0)))
    lat_b = math.radians(float(neighbor.get("lat_deg", 0.0)))
    lon_a = math.radians(float(cell.get("lon_deg", 0.0)))
    lon_b = math.radians(float(neighbor.get("lon_deg", 0.0)))
    dlon = lon_b - lon_a
    while dlon > math.pi:
        dlon -= math.tau
    while dlon < -math.pi:
        dlon += math.tau
    east = dlon * math.cos((lat_a + lat_b) * 0.5)
    north = lat_b - lat_a
    length = math.hypot(east, north)
    if length <= 0.0:
        return 0.0
    east /= length
    north /= length
    wind_east = float(cell.get("wind_east", 0.0))
    wind_north = float(cell.get("wind_north", 0.0))
    wind_speed = _clamp(math.hypot(wind_east, wind_north))
    if wind_speed <= 0.0:
        return 0.0
    dot = (wind_east * east + wind_north * north) / max(0.000001, math.hypot(wind_east, wind_north))
    return _clamp((dot + 1.0) * 0.5) * wind_speed


def _fuel_continuity(cell: dict[str, Any], neighbors: list[dict[str, Any]]) -> float:
    if _is_aquatic_cell(cell):
        return 0.0
    biomass = _clamp(float(cell.get("vegetation_biomass_index", 0.0)))
    primary = _clamp(float(cell.get("primary_productivity_index", 0.0)))
    wildfire = _clamp(float(cell.get("wildfire_spread_risk_index", 0.0)))
    aridity = _clamp(float(cell.get("seasonal_aridity_index", 0.0)))
    wetland = _clamp(float(cell.get("wetland_extent_index", 0.0)))
    ice = _clamp(float(cell.get("ice_thickness_m", 0.0)) / 500.0)
    neighbor_fuel = (
        sum(1 for neighbor in neighbors if not _is_aquatic_cell(neighbor) and float(neighbor.get("vegetation_biomass_index", 0.0)) >= 0.20) / len(neighbors)
        if neighbors
        else 0.0
    )
    forest_bonus = 0.10 if "forest" in str(cell.get("biome", "")) else 0.0
    grass_bonus = 0.08 if str(cell.get("biome", "")) in {"savanna", "temperate_grassland", "mediterranean_scrub"} else 0.0
    return _clamp(
        biomass * 0.32
        + primary * 0.16
        + wildfire * 0.20
        + aridity * 0.14
        + neighbor_fuel * 0.12
        + forest_bonus
        + grass_bonus
        - wetland * 0.18
        - ice * 0.34
    )


def _firebreak(cell: dict[str, Any], neighbors: list[dict[str, Any]], fuel: float) -> float:
    if _is_aquatic_cell(cell):
        return 1.0
    water_neighbor_fraction = sum(1 for neighbor in neighbors if _is_aquatic_cell(neighbor)) / len(neighbors) if neighbors else 0.0
    wetland = _clamp(float(cell.get("wetland_extent_index", 0.0)))
    river = 0.18 if bool(cell.get("is_river", False)) else 0.0
    floodplain = _clamp(float(cell.get("floodplain_connectivity_index", 0.0))) * 0.12
    ice = _clamp(float(cell.get("ice_thickness_m", 0.0)) / 500.0)
    sparse_fuel = _clamp(1.0 - fuel) * 0.18
    return _clamp(water_neighbor_fraction * 0.34 + wetland * 0.24 + river + floodplain + ice * 0.30 + sparse_fuel)


def _ignition_potential(cell: dict[str, Any], fuel: float, firebreak: float, wind_alignment: float, *, native_seasonal: bool = False, prescribed_natural: bool = False) -> float:
    if _is_aquatic_cell(cell):
        return 0.0
    wildfire = _clamp(float(cell.get("wildfire_spread_risk_index", 0.0)))
    aridity = _clamp(float(cell.get("seasonal_aridity_index", 0.0)))
    disturbance = _clamp(float(cell.get("ecosystem_disturbance_pressure_index", 0.0)))
    settlement = 0.0 if prescribed_natural else _clamp(float(cell.get("settlement_score", 0.0)))
    lightning_proxy = 0.0 if native_seasonal else _clamp(float(cell.get("climate_energy_stress_index", 0.0))) * 0.06
    ice = _clamp(float(cell.get("ice_thickness_m", 0.0)) / 500.0)
    return _clamp(
        wildfire * 0.34
        + fuel * 0.28
        + aridity * 0.16
        + disturbance * 0.10
        + wind_alignment * 0.08
        + settlement * 0.08
        + lightning_proxy
        - firebreak * 0.18
        - ice * 0.18
    )


def _regime(cell: dict[str, Any], ignition: float, fuel: float, firebreak: float, wind_alignment: float) -> str:
    if _is_aquatic_cell(cell):
        return "non_burnable_water"
    if str(cell.get("biome", "")) == "ice_cap" or float(cell.get("ice_thickness_m", 0.0)) > 120.0:
        return "ice_or_barren_firebreak"
    if fuel < 0.12:
        return "sparse_fuel"
    if firebreak >= HIGH_FIREBREAK_THRESHOLD:
        return "fragmented_firebreak_mosaic"
    if ignition >= 0.34 and fuel >= HIGH_FUEL_THRESHOLD and wind_alignment >= 0.35:
        return "wind_driven_crown_fire"
    if ignition >= IGNITION_THRESHOLD:
        return "seasonal_surface_fire"
    return "low_fire_activity"


def _spread_probability(source: dict[str, Any], target: dict[str, Any]) -> float | None:
    if _is_aquatic_cell(source) or _is_aquatic_cell(target):
        return 0.0
    if any(field in cell for cell in (source, target) for field in _SUPPORT_FIELDS) and (
        not _available_fire_cell(source) or not _available_fire_cell(target)
    ):
        return None  # An unmodelled edge, not physical zero spread probability.
    if str(target.get("wildfire_disturbance_regime", "")) == "ice_or_barren_firebreak":
        return 0.0
    same_biome = 0.06 if str(source.get("biome", "")) == str(target.get("biome", "")) else 0.0
    downhill_drying = 0.04 if float(target.get("elevation_m", 0.0)) <= float(source.get("elevation_m", 0.0)) else 0.0
    return _clamp(
        float(target.get("wildfire_ignition_potential_index", 0.0)) * 0.26
        + float(target.get("wildfire_fuel_continuity_index", 0.0)) * 0.28
        + _wind_alignment(source, target) * 0.20
        + float(source.get("wildfire_fuel_continuity_index", 0.0)) * 0.08
        + same_biome
        + downhill_drying
        - float(target.get("wildfire_firebreak_index", 0.0)) * 0.22
    )


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


def _mean(cells: list[dict[str, Any]], key: str) -> float:
    return sum(float(cell.get(key, 0.0)) for cell in cells) / len(cells) if cells else 0.0


def _build_history(
    event_id: int,
    ignition_cell: dict[str, Any],
    cells_by_id: dict[int, dict[str, Any]],
    assigned_cell_ids: set[int],
    *, availability_aware: bool = False,
) -> dict[str, Any]:
    if availability_aware and not _available_fire_cell(ignition_cell):
        raise ValueError("wildfire cannot seed an unavailable ignition estimate")
    ignition_id = int(ignition_cell.get("id", -1))
    burned_ids: set[int] = {ignition_id}
    active_ids: set[int] = {ignition_id}
    step_probabilities: dict[int, float] = {ignition_id: float(ignition_cell.get("wildfire_ignition_potential_index", 0.0))}
    steps: list[dict[str, Any]] = []

    for step_index in range(MAX_SPREAD_STEPS):
        if step_index == 0:
            newly_burned = [ignition_id]
            probabilities = [step_probabilities[ignition_id]]
        else:
            candidate_probabilities: dict[int, float] = {}
            for active_id in active_ids:
                active = cells_by_id.get(active_id)
                if active is None:
                    continue
                for neighbor_id_raw in active.get("neighbors", []):
                    neighbor_id = int(neighbor_id_raw)
                    if neighbor_id in burned_ids or neighbor_id in assigned_cell_ids or neighbor_id not in cells_by_id:
                        continue
                    probability = _spread_probability(active, cells_by_id[neighbor_id])
                    if probability is not None and probability >= SPREAD_THRESHOLD:
                        candidate_probabilities[neighbor_id] = max(candidate_probabilities.get(neighbor_id, 0.0), probability)
            remaining_slots = max(0, MAX_EVENT_CELLS - len(burned_ids))
            selected = sorted(candidate_probabilities.items(), key=lambda item: (-item[1], item[0]))[:remaining_slots]
            newly_burned = sorted(cell_id for cell_id, _probability in selected)
            probabilities = [candidate_probabilities[cell_id] for cell_id in newly_burned]
            if not newly_burned:
                break
            for cell_id in newly_burned:
                burned_ids.add(cell_id)
                step_probabilities[cell_id] = candidate_probabilities[cell_id]
            active_ids = set(newly_burned)

        burned_cells = [cells_by_id[cell_id] for cell_id in sorted(burned_ids)]
        burned_area = sum(max(0.0, float(cell.get("area_km2", 0.0))) for cell in burned_cells)
        mean_probability = sum(probabilities) / len(probabilities) if probabilities else 0.0
        mean_firebreak = _mean([cells_by_id[cell_id] for cell_id in newly_burned], "wildfire_firebreak_index")
        steps.append(
            {
                "step_index": step_index,
                "newly_burned_cell_ids": newly_burned,
                "active_front_cell_ids": sorted(active_ids),
                "cumulative_burned_cell_count": len(burned_ids),
                "burned_area_km2": round(burned_area, 6),
                "mean_spread_probability_index": round(mean_probability, 6),
                "containment_index": round(_clamp(mean_firebreak + (1.0 - mean_probability) * 0.28), 6),
            }
        )
        if availability_aware:
            steps[-1].update(_front_coverage(active_ids, cells_by_id))
            steps[-1]["containment_scope"] = "coefficient_index_on_modelled_cells_not_physical_containment"

    cells = [cells_by_id[cell_id] for cell_id in sorted(burned_ids)]
    cell_ids = [int(cell.get("id", -1)) for cell in cells]
    area = sum(max(0.0, float(cell.get("area_km2", 0.0))) for cell in cells)
    centroid_lat, centroid_lon = _centroid(cells)
    biome_counts = Counter(str(cell.get("biome", "unknown")) for cell in cells)
    regime_counts = Counter(str(cell.get("wildfire_disturbance_regime", "unknown")) for cell in cells)
    max_probability = max(step_probabilities.values()) if step_probabilities else 0.0
    containment = _clamp(_mean(cells, "wildfire_firebreak_index") * 0.62 + (1.0 - max_probability) * 0.20)
    history = {
        "id": event_id,
        "ignition_cell_id": ignition_id,
        "cell_count": len(cells),
        "cell_ids": cell_ids,
        "area_km2": round(area, 6),
        "centroid_lat_deg": centroid_lat,
        "centroid_lon_deg": centroid_lon,
        "dominant_biome": _primary_key(biome_counts, "unknown"),
        "dominant_disturbance_regime": _primary_key(regime_counts, "unknown"),
        "mean_wildfire_spread_risk_index": round(_mean(cells, "wildfire_spread_risk_index"), 6),
        "mean_ignition_potential_index": round(_mean(cells, "wildfire_ignition_potential_index"), 6),
        "mean_fuel_continuity_index": round(_mean(cells, "wildfire_fuel_continuity_index"), 6),
        "mean_wind_alignment_index": round(_mean(cells, "wildfire_wind_alignment_index"), 6),
        "mean_firebreak_index": round(_mean(cells, "wildfire_firebreak_index"), 6),
        "mean_ecosystem_disturbance_pressure_index": round(_mean(cells, "ecosystem_disturbance_pressure_index"), 6),
        "max_spread_probability_index": round(max_probability, 6),
        "containment_index": round(containment, 6),
        "spread_step_count": len(steps),
        "steps": steps,
        "disturbance_regime_counts": dict(sorted(regime_counts.items())),
    }
    if availability_aware:
        history.update(_front_coverage(burned_ids, cells_by_id))
        history["containment_scope"] = "coefficient_index_on_modelled_cells_not_physical_containment"
        history["spread_limit_reached"] = len(steps) == MAX_SPREAD_STEPS or len(burned_ids) == MAX_EVENT_CELLS
    return history


def _build_wildfire_disturbance(world: dict[str, Any], *, prescribed_natural: bool = False) -> dict[str, Any]:
    if "summary" in world and not isinstance(world["summary"], dict):
        raise ValueError("wildfire summary must be an object when present before enrichment")
    native_seasonal = ecology_uses_native_seasonal_climate(world)
    availability = _parent_availability(world, native_seasonal=native_seasonal, prescribed_natural=prescribed_natural)
    availability_aware = availability is not None
    model = ((NATIVE_PARENT_WILDFIRE_MODEL if native_seasonal else PARENT_WILDFIRE_MODEL)
        if availability_aware else (NATIVE_WILDFIRE_MODEL if native_seasonal else LEGACY_WILDFIRE_MODEL))
    if prescribed_natural:
        model = NATIVE_NATURAL_PARENT_WILDFIRE_MODEL if native_seasonal else NATURAL_PARENT_WILDFIRE_MODEL
    if "wildfire_disturbance_model" in world and world["wildfire_disturbance_model"] != model:
        old_models = (LEGACY_WILDFIRE_MODEL, NATIVE_WILDFIRE_MODEL) if availability_aware else (LEGACY_WILDFIRE_MODEL,)
        if (not availability_aware and not native_seasonal) or world["wildfire_disturbance_model"] not in old_models:
            raise ValueError("wildfire disturbance requires exact known model metadata")
    cells = world.get("cells", [])
    if (not isinstance(cells, list) or not cells) and not prescribed_natural:
        return world
    world["wildfire_disturbance_model"] = dict(model)
    cells_by_id = {int(cell.get("id", -1)): cell for cell in cells if isinstance(cell, dict)}

    ignition_sum = 0.0
    fuel_sum = 0.0
    wind_sum = 0.0
    firebreak_sum = 0.0
    high_ignition_count = 0
    high_fuel_count = 0
    high_firebreak_count = 0
    regime_counts: Counter[str] = Counter()

    for cell in cells:
        neighbors = _neighbors(cell, cells_by_id)
        supports = availability[cell["id"]] if availability_aware else (True, True, True)
        fuel = _fuel_continuity(cell, neighbors) if supports[0] else 0.0
        firebreak = _firebreak(cell, neighbors, fuel) if supports[1] else 0.0
        wind_alignment = max((_wind_alignment(cell, neighbor) for neighbor in neighbors), default=0.0)
        ignition = _ignition_potential(cell, fuel, firebreak, wind_alignment, native_seasonal=native_seasonal, prescribed_natural=prescribed_natural) if supports[2] else 0.0
        regime = _regime(cell, ignition, fuel, firebreak, wind_alignment) if all(supports) else "fuel_proxy_unavailable"
        if availability_aware:
            for flag, supported in zip(_SUPPORT_FIELDS, supports):
                cell[flag] = supported
        rounded_ignition = round(ignition, 6)
        rounded_fuel = round(fuel, 6)
        rounded_firebreak = round(firebreak, 6)
        cell["wildfire_ignition_potential_index"] = rounded_ignition
        cell["wildfire_fuel_continuity_index"] = rounded_fuel
        cell["wildfire_wind_alignment_index"] = round(wind_alignment, 6)
        cell["wildfire_firebreak_index"] = rounded_firebreak
        cell["wildfire_disturbance_regime"] = regime
        cell["wildfire_spread_history_ids"] = []
        ignition_sum += ignition
        fuel_sum += fuel
        wind_sum += wind_alignment
        firebreak_sum += firebreak
        high_ignition_count += 1 if supports[2] and rounded_ignition >= IGNITION_THRESHOLD else 0
        high_fuel_count += 1 if supports[0] and rounded_fuel >= HIGH_FUEL_THRESHOLD else 0
        high_firebreak_count += 1 if supports[1] and rounded_firebreak >= HIGH_FIREBREAK_THRESHOLD else 0
        regime_counts[regime] += 1

    assigned_cell_ids: set[int] = set()
    candidate_cells = sorted(
        [
            cell
            for cell in cells
            if (not availability_aware or _available_fire_cell(cell))
            and float(cell.get("wildfire_ignition_potential_index", 0.0)) >= IGNITION_THRESHOLD
            and float(cell.get("wildfire_fuel_continuity_index", 0.0)) >= 0.18
            and str(cell.get("wildfire_disturbance_regime", "")) not in {"non_burnable_water", "ice_or_barren_firebreak"}
        ],
        key=lambda cell: (-float(cell.get("wildfire_ignition_potential_index", 0.0)), int(cell.get("id", -1))),
    )
    histories: list[dict[str, Any]] = []
    for ignition_cell in candidate_cells:
        if len(histories) >= MAX_EVENT_COUNT:
            break
        ignition_id = int(ignition_cell.get("id", -1))
        if ignition_id in assigned_cell_ids:
            continue
        history = _build_history(len(histories), ignition_cell, cells_by_id, assigned_cell_ids, availability_aware=availability_aware)
        histories.append(history)
        for cell_id in history.get("cell_ids", []):
            assigned_cell_ids.add(int(cell_id))
            cell = cells_by_id.get(int(cell_id))
            if cell is not None:
                cell["wildfire_spread_history_ids"].append(int(history["id"]))

    wildfire_cell_ids = {
        int(cell.get("id", -1))
        for cell in cells
        if isinstance(cell.get("wildfire_spread_history_ids", []), list) and cell.get("wildfire_spread_history_ids", [])
    }
    summary = world.setdefault("summary", {})
    cell_count = len(cells) or 1
    summary["wildfire_spread_history_count"] = len(histories)
    summary["wildfire_disturbance_cell_count"] = len(wildfire_cell_ids)
    summary["wildfire_spread_step_count"] = sum(int(history.get("spread_step_count", 0)) for history in histories)
    summary["high_wildfire_ignition_potential_cell_count"] = high_ignition_count
    summary["high_wildfire_fuel_continuity_cell_count"] = high_fuel_count
    summary["high_wildfire_firebreak_cell_count"] = high_firebreak_count
    summary["wildfire_total_burned_area_km2"] = round(sum(float(history.get("area_km2", 0.0)) for history in histories), 6)
    summary["mean_wildfire_ignition_potential_index"] = round(ignition_sum / cell_count, 6)
    summary["mean_wildfire_fuel_continuity_index"] = round(fuel_sum / cell_count, 6)
    summary["mean_wildfire_wind_alignment_index"] = round(wind_sum / cell_count, 6)
    summary["mean_wildfire_firebreak_index"] = round(firebreak_sum / cell_count, 6)
    summary["wildfire_disturbance_regime_counts"] = dict(sorted(regime_counts.items()))
    if availability_aware:
        for flag in _SUPPORT_FIELDS:
            summary[flag + "_cell_count"] = sum(cell[flag] for cell in cells)
        summary["wildfire_unavailable_cell_count"] = sum(not all(flags) for flags in availability.values())
        summary["wildfire_partial_front_history_count"] = sum(h["front_coverage_status"] == "partial_unavailable_inputs" for h in histories)
        summary["wildfire_unmodelled_adjacent_cell_count"] = len({i for h in histories for i in h["unmodelled_adjacent_cell_ids"]})
        summary["wildfire_unmodelled_front_edge_count"] = sum(h["unmodelled_front_edge_count"] for h in histories)
        summary["wildfire_supported_front_edge_count"] = sum(h["supported_front_edge_count"] for h in histories)
    world["wildfire_spread_histories"] = histories
    return world



def enrich_world_with_wildfire_disturbance(world: dict[str, Any]) -> dict[str, Any]:
    """Keep historical paths intact; publish exact E5 fire children atomically."""
    from .wildfire_aquatic_validation import (
        PRESCRIBED_FIRE_CELL_FIELDS as cell_fields,
        PRESCRIBED_FIRE_SUMMARY_FIELDS as summary_fields,
        _same_natural_structure, validate_prescribed_fire_inputs,
        validate_wildfire_aquatic_exclusion,
    )
    if not isinstance(world, dict):
        raise ValueError("wildfire requires a world object before enrichment")
    own, parent = world.get("wildfire_disturbance_model"), world.get("ecosystem_dynamics_model")
    names = ("heuristic_wildfire_prescribed_natural_parent_availability_v6", "heuristic_wildfire_native_seasonal_prescribed_natural_parent_availability_v7")
    natural_parent = isinstance(parent, dict) and parent.get("model") == "heuristic_ecosystem_climate_support_v5"
    natural_own = isinstance(own, dict) and own.get("model") in names
    if not (natural_parent or natural_own):
        return _build_wildfire_disturbance(world)
    native = ecology_uses_native_seasonal_climate(world)
    expected = NATIVE_NATURAL_PARENT_WILDFIRE_MODEL if native else NATURAL_PARENT_WILDFIRE_MODEL
    if "wildfire_disturbance_model" in world:
        if not _same_natural_structure(own, expected):
            raise ValueError("prescribed natural wildfire requires exact matching own6/7; clear audited historical outputs before migration")
    else:
        cells, summary = world.get("cells"), world.get("summary", {})
        partial = "wildfire_spread_histories" in world or (isinstance(summary, dict) and any(k in summary for k in summary_fields))
        partial = partial or (isinstance(cells, list) and any(isinstance(c, dict) and any(k in c for k in cell_fields) for c in cells))
        if partial:
            raise ValueError("prescribed natural wildfire: undeclared owned outputs; audit and clear before migration")
    validate_prescribed_fire_inputs(world, native=native)
    staged = {**world, "cells": [dict(c) for c in world["cells"]], "summary": dict(world.get("summary", {}))}
    try:
        _build_wildfire_disturbance(staged, prescribed_natural=True)
        errors = validate_wildfire_aquatic_exclusion(staged)
        if errors:
            raise ValueError(errors[0])
    except (TypeError, ValueError, KeyError, ArithmeticError, AttributeError) as error:
        raise ValueError(("prescribed natural wildfire: " + str(error))[:600]) from error
    for cell, result in zip(world["cells"], staged["cells"]):
        cell.update({key: result[key] for key in cell_fields})
    world["wildfire_disturbance_model"] = staged["wildfire_disturbance_model"]
    world["wildfire_spread_histories"] = staged["wildfire_spread_histories"]
    world.setdefault("summary", {}).update({key: staged["summary"][key] for key in summary_fields})
    return world
