"""Independent land-use v2 availability and complete zone replay.

The unchanged v1 equations/graph replay below retain the independent human-geography
validator implementation, never producer imports. This module is self-contained
to permit later public human-geography dispatch without an import cycle. Agriculture has its own annual-air proxy domain;
mining surface applicability makes no biological or economic-support claim.
"""
from __future__ import annotations

from collections import Counter, defaultdict, deque
import math
from typing import Any

LAND_USE_ZONE_MODEL = "causal_soil_climate_resource_connected_land_use_zones_v1"

AGRICULTURAL_THRESHOLD = 0.58

MINING_THRESHOLD = 0.52

MINING_RESOURCES = {
    "volcanic_arc_metals",
    "craton_iron_gold",
    "sedimentary_fuels",
    "evaporites",
    "placer_metals",
    "geothermal",
}

AGRICULTURAL_LANDFORMS = {"floodplain", "delta", "river_valley", "coastal_plain", "lacustrine_basin"}

AGRICULTURAL_BIOMES = {
    "temperate_forest",
    "temperate_grassland",
    "tropical_seasonal_forest",
    "savanna",
    "wetland",
}

def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))

def _primary(counter: Counter[str], fallback: str) -> str:
    if not counter:
        return fallback
    return sorted(counter.items(), key=lambda item: (-item[1], item[0]))[0][0]

def _components(candidate_ids: set[int], cells_by_id: dict[int, dict[str, Any]]) -> list[list[int]]:
    components: list[list[int]] = []
    remaining = set(candidate_ids)
    while remaining:
        start = min(remaining)
        remaining.remove(start)
        queue: deque[int] = deque([start])
        component = [start]
        while queue:
            current_id = queue.popleft()
            neighbors = cells_by_id[current_id].get("neighbors", [])
            if not isinstance(neighbors, list):
                continue
            for neighbor_raw in neighbors:
                neighbor_id = int(neighbor_raw)
                if neighbor_id not in remaining:
                    continue
                remaining.remove(neighbor_id)
                queue.append(neighbor_id)
                component.append(neighbor_id)
        components.append(sorted(component))
    return components

def _land_use_model() -> dict[str, Any]:
    return {
        "model_type": LAND_USE_ZONE_MODEL,
        "deterministic": True,
        "agricultural_threshold": AGRICULTURAL_THRESHOLD,
        "mining_threshold": MINING_THRESHOLD,
        "threshold_semantics": "raw_pre_serialization_greater_than_or_equal_v1",
        "cell_index_serialization_decimals": 6,
        "agricultural_potential_model": "bounded_soil_climate_water_alluvial_hazard_weighted_index_v1",
        "agricultural_parameters": {
            "fertility_weight": 0.27,
            "soil_depth_scale_m": 3.2,
            "soil_depth_weight": 0.14,
            "soil_moisture_weight": 0.15,
            "climate_optimum_c": 17.0,
            "climate_tolerance_c": 26.0,
            "climate_weight": 0.14,
            "growing_season_scale_months": 10.0,
            "growing_season_weight": 0.12,
            "runoff_scale_mm_y": 650.0,
            "river_water_bonus": 0.20,
            "fresh_lake_water_bonus": 0.16,
            "groundwater_recharge_scale_mm_y": 300.0,
            "groundwater_water_weight": 0.18,
            "water_weight": 0.12,
            "alluvial_landform_bonus": 0.18,
            "agricultural_biome_bonus": 0.10,
            "salinity_penalty_weight": 0.18,
            "erosion_rate_scale": 140.0,
            "erosion_penalty_weight": 0.10,
            "ice_thickness_scale_m": 400.0,
            "ice_penalty_weight": 0.22,
            "aridity_penalty_weight": 0.12,
        },
        "agricultural_landforms": sorted(AGRICULTURAL_LANDFORMS),
        "agricultural_biomes": sorted(AGRICULTURAL_BIOMES),
        "mining_potential_model": "eligible_resource_deposit_geology_access_hazard_weighted_index_v1",
        "mining_parameters": {
            "reserve_weight": 0.28,
            "viability_weight": 0.24,
            "confidence_weight": 0.18,
            "accessibility_weight": 0.12,
            "geology_weight": 0.10,
            "settlement_access_weight": 0.08,
            "hazard_penalty_weight": 0.12,
            "convergent_geology_weight": 0.26,
            "divergent_geology_weight": 0.20,
            "volcanic_geology_weight": 0.18,
            "sediment_scale_m": 3.0,
            "sediment_geology_weight": 0.18,
            "crust_age_scale_ma": 2500.0,
            "crust_age_geology_weight": 0.18,
        },
        "mining_resources": sorted(MINING_RESOURCES),
        "component_model": "candidate_induced_mesh_components_min_cell_breadth_first_v1",
        "record_order": "agricultural_then_mining_components_by_minimum_cell_id_v1",
        "dominant_field_model": "count_then_lexicographic_order_v1",
        "record_link_model": "member_cell_settlement_route_and_primary_resource_deposit_links_v1",
        "model_limitation": "diagnostic_static_potential_and_connected_zones_without_land_market_crop_mine_capacity_or_development_feedback",
    }

def _agricultural_potential(cell: dict[str, Any]) -> float:
    if bool(cell.get("is_water", False)):
        return 0.0
    fertility = _clamp(float(cell.get("fertility", 0.0)))
    soil_depth = _clamp(float(cell.get("soil_depth_m", 0.0)) / 3.2)
    soil_moisture = _clamp(float(cell.get("soil_moisture_index", 0.0)))
    salinity_penalty = _clamp(float(cell.get("soil_salinity_index", 0.0)))
    erosion_penalty = _clamp(
        float(cell.get("soil_erodibility_index", 0.0)) * 0.5
        + float(cell.get("erosion_rate", 0.0)) / 140.0
    )
    climate = _clamp(1.0 - abs(float(cell.get("temperature_c", 0.0)) - 17.0) / 26.0)
    growing = _clamp(float(cell.get("growing_season_months", 0.0)) / 10.0)
    water = _clamp(
        float(cell.get("runoff_mm_y", 0.0)) / 650.0
        + (0.20 if bool(cell.get("is_river", False)) else 0.0)
        + (0.16 if str(cell.get("water_body_type", "")) == "fresh_lake" else 0.0)
        + _clamp(float(cell.get("groundwater_recharge_mm_y", 0.0)) / 300.0) * 0.18
    )
    alluvial = 0.18 if str(cell.get("landform", "")) in AGRICULTURAL_LANDFORMS else 0.0
    biome_bonus = 0.10 if str(cell.get("biome", "")) in AGRICULTURAL_BIOMES else 0.0
    ice_penalty = _clamp(float(cell.get("ice_thickness_m", 0.0)) / 400.0)
    aridity_penalty = _clamp(float(cell.get("seasonal_aridity_index", 0.0))) * 0.12
    return _clamp(
        fertility * 0.27
        + soil_depth * 0.14
        + soil_moisture * 0.15
        + climate * 0.14
        + growing * 0.12
        + water * 0.12
        + alluvial
        + biome_bonus
        - salinity_penalty * 0.18
        - erosion_penalty * 0.10
        - ice_penalty * 0.22
        - aridity_penalty
    )

def _mining_potential(cell: dict[str, Any], deposit_by_cell: dict[int, dict[str, Any]]) -> float:
    if bool(cell.get("is_water", False)):
        return 0.0
    if str(cell.get("resource", "none")) not in MINING_RESOURCES:
        return 0.0
    deposit = deposit_by_cell.get(int(cell.get("id", -1)), {})
    reserve = _clamp(float(deposit.get("reserve_potential_index", 0.0)))
    viability = _clamp(float(deposit.get("economic_viability_index", 0.0)))
    confidence = _clamp(float(deposit.get("geologic_confidence_index", 0.0)))
    accessibility = _clamp(float(deposit.get("accessibility_index", 0.0)))
    hazard = _clamp(float(deposit.get("extraction_hazard_index", 0.0)))
    geology = _clamp(
        float(cell.get("boundary_convergent", 0.0)) * 0.26
        + float(cell.get("boundary_divergent", 0.0)) * 0.20
        + float(cell.get("volcanic_potential_index", 0.0)) * 0.18
        + _clamp(float(cell.get("sediment_thickness_m", 0.0)) / 3.0) * 0.18
        + _clamp(float(cell.get("crust_age_ma", 0.0)) / 2500.0) * 0.18
    )
    return _clamp(
        reserve * 0.28
        + viability * 0.24
        + confidence * 0.18
        + accessibility * 0.12
        + geology * 0.10
        + _clamp(float(cell.get("settlement_score", 0.0))) * 0.08
        - hazard * 0.12
    )

def _expected_land_use_zones(
    *,
    zone_type: str,
    components: list[list[int]],
    potential_by_cell: dict[int, float],
    cells_by_id: dict[int, dict[str, Any]],
    settlements_by_cell: dict[int, list[int]],
    routes_by_settlement: dict[int, set[int]],
    deposit_by_cell: dict[int, dict[str, Any]],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for cell_ids in components:
        settlement_ids = sorted(
            {settlement_id for cell_id in cell_ids for settlement_id in settlements_by_cell.get(cell_id, []) if settlement_id >= 0}
        )
        route_ids = sorted(
            {route_id for settlement_id in settlement_ids for route_id in routes_by_settlement.get(settlement_id, set()) if route_id >= 0}
        )
        deposit_ids = sorted(
            {
                int(deposit_by_cell[cell_id].get("id", -1))
                for cell_id in cell_ids
                if cell_id in deposit_by_cell and int(deposit_by_cell[cell_id].get("id", -1)) >= 0
            }
        )
        cells = [cells_by_id[cell_id] for cell_id in cell_ids]
        count = len(cells)
        records.append(
            {
                "id": len(records),
                "zone_type": zone_type,
                "cell_count": count,
                "cell_ids": cell_ids,
                "area_km2": round(sum(max(0.0, float(cell.get("area_km2", 0.0))) for cell in cells), 6),
                "mean_potential_index": round(sum(potential_by_cell[cell_id] for cell_id in cell_ids) / count, 6),
                "mean_fertility_index": round(
                    sum(_clamp(float(cell.get("fertility", 0.0))) for cell in cells) / count,
                    6,
                ),
                "dominant_resource": _primary(Counter(str(cell.get("resource", "none")) for cell in cells), "none"),
                "dominant_landform": _primary(Counter(str(cell.get("landform", "unknown")) for cell in cells), "unknown"),
                "dominant_biome": _primary(Counter(str(cell.get("biome", "unknown")) for cell in cells), "unknown"),
                "settlement_ids": settlement_ids,
                "route_ids": route_ids,
                "resource_deposit_ids": deposit_ids,
            }
        )
    return records

def _land_use_replay_valid(payload: dict[str, Any]) -> bool:
    cells = payload.get("cells", [])
    summary = payload.get("summary", {})
    if not isinstance(cells, list) or not cells or not isinstance(summary, dict):
        return False
    if payload.get("land_use_zone_model") != _land_use_model() or summary.get("land_use_zone_model") != LAND_USE_ZONE_MODEL:
        return False
    cells_by_id = {int(cell.get("id", -1)): cell for cell in cells if isinstance(cell, dict)}
    if len(cells_by_id) != len(cells):
        return False
    deposits = payload.get("resource_deposits", [])
    if not isinstance(deposits, list):
        return False
    deposit_by_cell = {
        int(deposit.get("cell_id", -1)): deposit
        for deposit in deposits
        if isinstance(deposit, dict) and int(deposit.get("cell_id", -1)) >= 0
    }
    raw_agricultural: dict[int, float] = {}
    raw_mining: dict[int, float] = {}
    agricultural: dict[int, float] = {}
    mining: dict[int, float] = {}
    agricultural_ids: set[int] = set()
    mining_ids: set[int] = set()
    for cell_id, cell in cells_by_id.items():
        raw_agricultural[cell_id] = _agricultural_potential(cell)
        raw_mining[cell_id] = _mining_potential(cell, deposit_by_cell)
        agricultural[cell_id] = round(raw_agricultural[cell_id], 6)
        mining[cell_id] = round(raw_mining[cell_id], 6)
        if raw_agricultural[cell_id] >= AGRICULTURAL_THRESHOLD:
            agricultural_ids.add(cell_id)
        if raw_mining[cell_id] >= MINING_THRESHOLD:
            mining_ids.add(cell_id)

    agricultural_components = _components(agricultural_ids, cells_by_id)
    mining_components = _components(mining_ids, cells_by_id)
    expected_agricultural_zone_id = {
        cell_id: zone_id for zone_id, component in enumerate(agricultural_components) for cell_id in component
    }
    expected_mining_zone_id = {
        cell_id: zone_id for zone_id, component in enumerate(mining_components) for cell_id in component
    }
    for cell_id, cell in cells_by_id.items():
        if (
            float(cell.get("agricultural_potential_index", -1.0)) != agricultural[cell_id]
            or float(cell.get("mining_potential_index", -1.0)) != mining[cell_id]
            or int(cell.get("agricultural_zone_id", -2)) != expected_agricultural_zone_id.get(cell_id, -1)
            or int(cell.get("mining_zone_id", -2)) != expected_mining_zone_id.get(cell_id, -1)
        ):
            return False

    settlements = payload.get("settlements", [])
    routes = payload.get("routes", [])
    if not isinstance(settlements, list) or not isinstance(routes, list):
        return False
    settlements_by_cell: dict[int, list[int]] = {}
    for settlement in settlements:
        settlements_by_cell.setdefault(int(settlement.get("cell_id", -1)), []).append(int(settlement.get("id", -1)))
    routes_by_settlement: dict[int, set[int]] = {}
    for route in routes:
        route_id = int(route.get("id", -1))
        for key in ("from", "to"):
            routes_by_settlement.setdefault(int(route.get(key, -1)), set()).add(route_id)

    expected_agricultural = _expected_land_use_zones(
        zone_type="agricultural",
        components=agricultural_components,
        potential_by_cell=agricultural,
        cells_by_id=cells_by_id,
        settlements_by_cell=settlements_by_cell,
        routes_by_settlement=routes_by_settlement,
        deposit_by_cell=deposit_by_cell,
    )
    expected_mining = _expected_land_use_zones(
        zone_type="mining",
        components=mining_components,
        potential_by_cell=mining,
        cells_by_id=cells_by_id,
        settlements_by_cell=settlements_by_cell,
        routes_by_settlement=routes_by_settlement,
        deposit_by_cell=deposit_by_cell,
    )
    if payload.get("agricultural_zones") != expected_agricultural or payload.get("mining_zones") != expected_mining:
        return False
    expected_summary = {
        "land_use_zone_model": LAND_USE_ZONE_MODEL,
        "agricultural_zone_count": len(expected_agricultural),
        "agricultural_zone_cell_count": len(agricultural_ids),
        "agricultural_zone_total_area_km2": round(sum(zone["area_km2"] for zone in expected_agricultural), 6),
        "mean_agricultural_potential_index": round(sum(raw_agricultural.values()) / len(cells), 6),
        "mining_zone_count": len(expected_mining),
        "mining_zone_cell_count": len(mining_ids),
        "mining_zone_total_area_km2": round(sum(zone["area_km2"] for zone in expected_mining), 6),
        "mean_mining_potential_index": round(sum(raw_mining.values()) / len(cells), 6),
    }
    return all(summary.get(key) == value for key, value in expected_summary.items())

# Independently declared below; no producer metadata or eligibility imports.
_POLICY: dict[str, Any] = {'model_type': 'causal_soil_climate_resource_connected_land_use_zones_v2',
 'agricultural_temperature_source': 'annual_surface_air_climate_proxy',
 'agricultural_minimum_temperature_c': -9.0,
 'agricultural_maximum_temperature_c': 43.0,
 'agricultural_temperature_bounds': 'exclusive',
 'agricultural_habitat_selector': 'complement_of_is_water_or_is_lake_or_fishery_water_body_type',
 'agricultural_parent_policy': 'own_soil_climate_water_descriptors_without_ecosystem_primary_dependency',
 'agricultural_support_scope': 'existing_annual_potential_proxy_not_crop_survival_or_yield',
 'unsupported_agricultural_policy': 'numeric_zero_false_support_no_zone_not_observed_absence',
 'fresh_lake_water_bonus_policy': 'inapplicable_on_aquatic_cells_not_transferred_to_neighbors',
 'summary_availability_policy': 'all_cell_means_include_unavailable_zero_sentinels_with_supported_cell_counts',
 'agricultural_descriptor_policy': 'present_finite_numeric_nonboolean_and_typed_categorical_inputs_required',
 'agricultural_numeric_inputs': ['erosion_rate',
                                 'fertility',
                                 'groundwater_recharge_mm_y',
                                 'growing_season_months',
                                 'ice_thickness_m',
                                 'runoff_mm_y',
                                 'seasonal_aridity_index',
                                 'soil_depth_m',
                                 'soil_erodibility_index',
                                 'soil_moisture_index',
                                 'soil_salinity_index'],
 'agricultural_categorical_inputs': ['biome', 'landform'],
 'agricultural_boolean_inputs': ['is_river'],
 'habitat_input_policy': 'explicit_boolean_water_lake_and_nonempty_string_water_body_required',
 'mining_surface_policy': 'exposed_land_only_without_underwater_extraction_model',
 'mining_surface_applicability_scope': 'exposed_land_not_complete_mining_input_or_economic_access_availability'}
_MINING_POLICY = {
    'model_type': 'causal_soil_climate_resource_connected_land_use_zones_v3',
    'source_resource_deposit_model': 'causal_geologic_resource_deposit_diagnostics_v5',
    'source_settlement_model': 'causal_native_score_local_max_separated_settlement_selection_v3',
    'mining_input_policy': 'audited_matching_material_deposit_and_settlement_v3_complete_economic_inputs',
    'unsupported_mining_policy': 'null_potential_false_support_preserve_structural_zero',
    'mining_zone_policy': 'withhold_complete_component_family_if_any_eligible_candidate_input_unavailable',
    'mining_summary_policy': 'emitted_zone_counts_with_explicit_completeness_and_complete_all_cell_mean_or_null',
    'summary_availability_policy': 'agricultural_v2_sentinel_means_mining_complete_all_cell_mean_or_null',
    'agricultural_policy': 'unchanged_v2_equations_flags_zero_sentinels_and_components',
}
MINING_FLAGS = ('mining_potential_supported', 'mining_zone_membership_supported')
MINING_SUMMARY = ('mining_potential_supported_cell_count','unsupported_mining_potential_cell_count',
                  'mining_input_applicable_cell_count','mining_input_supported_cell_count',
                  'mining_zone_selection_complete','mean_mining_potential_supported')

_FLAGS = ("agricultural_habitat_applicable", "agricultural_climate_supported",
          "agricultural_potential_supported", "mining_surface_applicable")
_SUMMARY = tuple(k + "_cell_count" for k in _FLAGS) + (
    "agricultural_potential_supported_area_km2", "unsupported_terrestrial_agricultural_cell_count")
_WATER = {"ocean", "continental_shelf", "inland_sea", "fresh_lake"}
_NUMERIC = ("fertility", "soil_depth_m", "soil_moisture_index", "soil_salinity_index",
            "soil_erodibility_index", "erosion_rate", "growing_season_months", "runoff_mm_y",
            "groundwater_recharge_mm_y", "ice_thickness_m", "seasonal_aridity_index")


class LandUseAvailabilityError(ValueError):
    """Malformed declared land-use input or an independent replay mismatch."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise LandUseAvailabilityError("land use availability: " + message)


def _finite(value: Any) -> bool:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _same(actual: Any, expected: Any) -> bool:
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, dict):
        return actual.keys() == expected.keys() and all(_same(actual[k], v) for k, v in expected.items())
    if isinstance(expected, list):
        return len(actual) == len(expected) and all(_same(a, b) for a, b in zip(actual, expected))
    return actual == expected


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value)


def land_use_model_version(world: dict[str, Any]) -> int:
    """Exact own-model dispatch; absent declaration selects new v2, v1 stays v1."""
    _require(isinstance(world, dict), "world must be an object")
    summary = world.get("summary", {})
    _require(isinstance(summary, dict), "summary must be an object")
    model = world.get("land_use_zone_model")
    parent = world.get("resource_deposit_model")
    new_parent = isinstance(parent, dict) and parent.get("model_type") == _MINING_POLICY["source_resource_deposit_model"]
    settlement = world.get("settlement_selection_model")
    new_selection = isinstance(settlement, dict) and settlement.get("model_type") == _MINING_POLICY["source_settlement_model"]
    version = 3 if new_parent or new_selection else 2
    if "land_use_zone_model" in world:
        if _same(model, _land_use_model()):
            version = 1
        elif _same(model, {**_land_use_model(), **_POLICY}):
            version = 2
        else:
            _require(_same(model, {**_land_use_model(), **_POLICY, **_MINING_POLICY}), "unknown or malformed land_use_zone_model")
            version = 3
        _require(summary.get("land_use_zone_model") == model["model_type"], "missing or mismatched summary model identity")
    else:
        _require("land_use_zone_model" not in summary, "summary model identity lacks its declaration")
    cells = world.get("cells", [])
    has_mirrors = any(k in summary for k in _SUMMARY) or (isinstance(cells, list) and any(
        isinstance(c, dict) and any(k in c for k in _FLAGS) for c in cells))
    _require(not has_mirrors or (version in (2,3) and "land_use_zone_model" in world), "undeclared or historical availability mirrors")
    if version == 3:
        _require(new_parent and new_selection and world.get("generation_scope") != "geo_only", "land-use-v3 requires full settlement-v3 and resource-v5")
        if "land_use_zone_model" not in world:
            owned_summary = (*_SUMMARY, *MINING_SUMMARY, "agricultural_zone_count", "agricultural_zone_cell_count", "agricultural_zone_total_area_km2", "mean_agricultural_potential_index", "mining_zone_count", "mining_zone_cell_count", "mining_zone_total_area_km2", "mean_mining_potential_index")
            present = any(k in world for k in ("agricultural_zones", "mining_zones")) or any(k in summary for k in owned_summary) or any(any(k in c for k in (*_FLAGS,*MINING_FLAGS,"agricultural_potential_index","mining_potential_index","agricultural_zone_id","mining_zone_id")) for c in cells)
            _require(not present, "undeclared land-use-v3 mirrors require explicit audited clearing")
    else:
        _require(not new_parent and not new_selection, "historical land-use requires old economic parents; explicit upgrade required")
        _require(not any(k in summary for k in MINING_SUMMARY) and not any(any(k in c for k in MINING_FLAGS) for c in cells), "new mining mirrors require land-use-v3")
    return version


def mining_inputs(world: dict[str, Any]) -> dict[int, tuple[bool, bool]]:
    from .biological_resource_validation import audit_biological_resource_deposits
    from .settlement_input_availability import require_settlement_v3_inputs
    audit_biological_resource_deposits(world)
    sites = require_settlement_v3_inputs(world)
    deposits = {d["cell_id"]: d for d in world["resource_deposits"]}
    result = {}
    for cell in world["cells"]:
        cid = cell["id"]
        applicable = _support(cell)[3] and cell["resource"] in MINING_RESOURCES
        if applicable:
            _require(cid in deposits and deposits[cid]["resource"] == cell["resource"], "mining requires matching material deposit")
            for key in ("boundary_convergent","boundary_divergent","volcanic_potential_index","sediment_thickness_m","crust_age_ma","fertility"):
                _require(_finite(cell.get(key)), "missing finite mining descriptor " + key)
        available = not applicable or (sites[cid].available and deposits[cid]["accessibility_supported"] and deposits[cid]["economic_viability_supported"])
        result[cid] = (applicable, available)
    return result


def validate_land_use_inputs(world: dict[str, Any]) -> None:
    """Check structural inputs without inventing availability or coercing values."""
    _require(isinstance(world, dict), "world must be an object")
    _require(isinstance(world.get("cells"), list), "cells must be a list")
    new_mining = land_use_model_version(world) == 3
    ids = set()
    for cell in world["cells"]:
        _require(isinstance(cell, dict), "every cell must be an object")
        cid = cell.get("id")
        _require(type(cid) is int and cid >= 0 and cid not in ids, "cell IDs must be unique nonnegative integers")
        ids.add(cid)
        _require(_finite(cell.get("area_km2")) and cell["area_km2"] >= 0, f"cell {cid}: area_km2 must be finite and nonnegative")
        _require(type(cell.get("is_water")) is bool and type(cell.get("is_lake")) is bool and _text(cell.get("water_body_type")),
                 f"cell {cid}: explicit water/lake booleans and water-body type are required")
        neighbors = cell.get("neighbors")
        _require(isinstance(neighbors, list) and all(type(n) is int and n >= 0 for n in neighbors), f"cell {cid}: neighbors must be nonnegative integer IDs")
        _require(_text(cell.get("resource")), f"cell {cid}: explicit primary resource categorical string required")
        if cell.get("resource") in MINING_RESOURCES and not (cell["is_water"] or cell["is_lake"] or cell["water_body_type"] in _WATER):
            for key in ("boundary_convergent", "boundary_divergent", "volcanic_potential_index", "sediment_thickness_m", "crust_age_ma", "settlement_score", "fertility"):
                _require(key not in cell or _finite(cell[key]), f"cell {cid}: malformed consumed mining descriptor " + key)
    adjacency = {cell["id"]: set(cell["neighbors"]) for cell in world["cells"]}
    for cell in world["cells"]:
        cid = cell["id"]
        neighbors = cell.get("neighbors", [])
        _require(len(neighbors) == len(set(neighbors)), f"cell {cid}: neighbors must be unique")
        _require(cid not in neighbors, f"cell {cid}: neighbors must not reference the cell itself")
        _require(all(n in ids for n in neighbors), f"cell {cid}: neighbor references an unknown cell")
        _require(all(cid in adjacency[n] for n in neighbors), f"cell {cid}: neighbors must be reciprocal")
    settlement_ids: set[int] = set()
    for family, links in (("resource_deposits", ("cell_id",)), ("settlements", ("cell_id",)), ("routes", ("from", "to"))):
        records = world.get(family)
        _require(isinstance(records, list), family + " must be a list")
        seen = set()
        sources = set()
        for record in records:
            _require(isinstance(record, dict), family + " records must be objects")
            rid = record.get("id")
            _require(type(rid) is int and rid >= 0 and rid not in seen, family + " IDs must be unique nonnegative integers")
            seen.add(rid)
            for key in links:
                _require(type(record.get(key)) is int and record[key] >= 0, family + ": invalid " + key)
                targets = settlement_ids if family == "routes" else ids
                target_type = "settlement" if family == "routes" else "cell"
                _require(record[key] in targets, family + f" {rid}: {key} references an unknown " + target_type)
            if family == "settlements":
                settlement_ids.add(rid)
            if family == "resource_deposits":
                _require(record["cell_id"] not in sources, "duplicate primary resource deposit for one cell")
                sources.add(record["cell_id"])
                for key in ("reserve_potential_index", "economic_viability_index", "geologic_confidence_index", "accessibility_index", "extraction_hazard_index"):
                    if new_mining and key in ("economic_viability_index", "accessibility_index"):
                        flag = "economic_viability_supported" if key == "economic_viability_index" else "accessibility_supported"
                        _require(type(record.get(flag)) is bool and key in record and (_finite(record[key]) if record[flag] else record[key] is None), family + ": malformed nullable numeric " + key)
                    else:
                        _require(key not in record or _finite(record[key]), family + ": malformed numeric " + key)


def _support(cell: dict[str, Any]) -> tuple[bool, bool, bool, bool]:
    land = not (cell["is_water"] or cell["is_lake"] or cell["water_body_type"] in _WATER)
    t = cell.get("temperature_c")
    climate = _finite(t) and -9.0 < t < 43.0
    descriptors = all(_finite(cell.get(k)) for k in _NUMERIC)
    descriptors = descriptors and _text(cell.get("biome")) and _text(cell.get("landform")) and type(cell.get("is_river")) is bool
    return land, climate, bool(land and climate and descriptors), land


def validate_land_use_availability(world: dict[str, Any]) -> list[str]:
    """At most one error; v2 replays every score, raw threshold, component and link.

Exact declared v1 uses its existing independent legacy replay. This validates
land-use outputs, not the physical calibration of upstream soils or phenology.
"""
    try:
        version = land_use_model_version(world)
        _require("land_use_zone_model" in world, "outputs require a complete model declaration")
        if version == 1:
            for key in ("cells", "resource_deposits", "settlements", "routes"):
                records = world.get(key, [])
                _require(isinstance(records, list) and all(isinstance(r, dict) for r in records), "legacy " + key + " must contain objects")
            _require(_land_use_replay_valid(world), "legacy v1 replay mismatch")
            return []
        validate_land_use_inputs(world)
        cells = world["cells"]
        by_id = {c["id"]: c for c in cells}
        support = {cid: _support(c) for cid, c in by_id.items()}
        deposits = {d["cell_id"]: d for d in world.get("resource_deposits", [])}
        raw_ag = {cid: _agricultural_potential(c) if support[cid][2] else 0.0 for cid, c in by_id.items()}
        mining_support = mining_inputs(world) if version == 3 else None
        complete_mining = mining_support is None or all(v[1] for v in mining_support.values())
        raw_mine = {cid: (_mining_potential(c, deposits) if support[cid][3] else 0.0) if mining_support is None or mining_support[cid][1] else None for cid, c in by_id.items()}
        _require(all(v is None and version == 3 or _finite(v) for v in (*raw_ag.values(), *raw_mine.values())), "nonfinite reconstructed potential")
        settlements = defaultdict(list)
        routes = defaultdict(set)
        for s in world.get("settlements", []):
            settlements[s["cell_id"]].append(s["id"])
        for r in world.get("routes", []):
            for end in (r["from"], r["to"]):
                routes[end].add(r["id"])
        expected_summary = {"land_use_zone_model": (_MINING_POLICY if version == 3 else _POLICY)["model_type"]}
        for kind, raw, threshold in (("agricultural", raw_ag, .58), ("mining", raw_mine, .52)):
            candidates = {cid for cid, value in raw.items() if value is not None and value >= threshold} if kind != "mining" or complete_mining else set()
            components = _components(candidates, by_id)
            assignments = {cid: index for index, group in enumerate(components) for cid in group}
            rounded = {cid: round(value, 6) if value is not None else None for cid, value in raw.items()}
            for cid, c in by_id.items():
                _require(_same(c.get(kind + "_potential_index"), rounded[cid]), f"cell {cid}: {kind} potential mismatch")
                _require(_same(c.get(kind + "_zone_id"), None if kind == "mining" and not complete_mining and mining_support[cid][0] else assignments.get(cid, -1)), f"cell {cid}: {kind} zone membership mismatch")
            zones = _expected_land_use_zones(zone_type=kind, components=components, potential_by_cell=rounded,
                cells_by_id=by_id, settlements_by_cell=settlements, routes_by_settlement=routes, deposit_by_cell=deposits)
            _require(_same(world.get(kind + "_zones"), zones), kind + " zone records or links mismatch")
            expected_summary.update({kind + "_zone_count": len(zones), kind + "_zone_cell_count": len(candidates),
                kind + "_zone_total_area_km2": round(sum(z["area_km2"] for z in zones), 6),
                "mean_" + kind + "_potential_index": (round(sum(raw.values()) / len(cells), 6) if cells else 0.0) if kind != "mining" or complete_mining else None})
        if version == 3:
            for cid, cell in by_id.items():
                _require(cell.get("mining_potential_supported") is mining_support[cid][1], f"cell {cid}: mining potential support mismatch")
                _require(cell.get("mining_zone_membership_supported") is (complete_mining or not mining_support[cid][0]), f"cell {cid}: mining membership support mismatch")
            expected_summary.update({"mining_potential_supported_cell_count": sum(v[1] for v in mining_support.values()),
                "unsupported_mining_potential_cell_count": sum(not v[1] for v in mining_support.values()),
                "mining_input_applicable_cell_count": sum(v[0] for v in mining_support.values()),
                "mining_input_supported_cell_count": sum(v[0] and v[1] for v in mining_support.values()),
                "mining_zone_selection_complete": complete_mining, "mean_mining_potential_supported": complete_mining})
        for index, flag in enumerate(_FLAGS):
            for cid, cell in by_id.items():
                _require(cell.get(flag) is support[cid][index], f"cell {cid}: {flag} mismatch")
            expected_summary[flag + "_cell_count"] = sum(s[index] for s in support.values())
        expected_summary["agricultural_potential_supported_area_km2"] = round(sum(float(c["area_km2"]) for c in cells if support[c["id"]][2]), 6)
        expected_summary["unsupported_terrestrial_agricultural_cell_count"] = sum(s[0] and not s[2] for s in support.values())
        for key, value in expected_summary.items():
            _require(not isinstance(value, float) or math.isfinite(value), key + " is not representable")
            _require(_same(world["summary"].get(key), value), "summary " + key + " mismatch")
        return []
    except LandUseAvailabilityError as exc:
        return [str(exc)]
    except (TypeError, ValueError, KeyError, OverflowError, ArithmeticError) as exc:
        return ["land use availability: malformed consumed input or output (" + type(exc).__name__ + ")"]
