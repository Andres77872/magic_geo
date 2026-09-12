from __future__ import annotations

from typing import Any

from .settlement_climate_support import (
    SEASONAL_SETTLEMENT_SELECTION_MODEL, SETTLEMENT_CLIMATE_SUPPORT_MODEL, seasonal_settlement_inputs,
)


SETTLEMENT_SELECTION_MODEL = (
    "causal_native_score_local_max_separated_settlement_selection_v2"
)
ROUTE_NETWORK_MODEL = "causal_endpoint_barrier_ranked_route_network_v1"
SETTLEMENT_SCORE_THRESHOLD = 0.48
SETTLEMENT_TARGET_CELL_DIVISOR = 180
SETTLEMENT_TARGET_MINIMUM = 8
SETTLEMENT_TARGET_MAXIMUM = 64
SETTLEMENT_MINIMUM_SEPARATION_FACTOR = 2.4
ROUTE_LINKS_PER_SETTLEMENT = 2


def _candidate_count(cells: list[dict[str, Any]], temperatures: dict[int, float] | None = None) -> int:
    cells_by_id = {
        int(cell.get("id", -1)): cell
        for cell in cells
        if isinstance(cell, dict) and int(cell.get("id", -1)) >= 0
    }
    count = 0
    for cell in cells:
        if not isinstance(cell, dict):
            continue
        score = float(cell.get("settlement_score", 0.0))
        if (
            bool(cell.get("is_water", False))
            or bool(cell.get("is_lake", False))
            or (temperatures is not None and not -14.0 < temperatures[cell['id']] < 48.0)
            or score < SETTLEMENT_SCORE_THRESHOLD
        ):
            continue
        if all(
            bool(neighbor.get("is_water", False))
            or bool(neighbor.get("is_lake", False))
            or (temperatures is not None and not -14.0 < temperatures[neighbor["id"]] < 48.0)
            or float(neighbor.get("settlement_score", 0.0)) <= score
            for raw_neighbor_id in cell.get("neighbors", [])
            if (neighbor := cells_by_id.get(int(raw_neighbor_id))) is not None
        ):
            count += 1
    return count


def enrich_world_with_settlement_route_models(
    world: dict[str, Any],
) -> dict[str, Any]:
    temperatures = seasonal_settlement_inputs(world)
    seasonal = temperatures is not None
    selection_model = SEASONAL_SETTLEMENT_SELECTION_MODEL if seasonal else SETTLEMENT_SELECTION_MODEL
    cells = world.get("cells", [])
    if not isinstance(cells, list) or not cells:
        return world
    settlements = world.get("settlements", [])
    routes = world.get("routes", [])
    if not isinstance(settlements, list):
        settlements = []
    if not isinstance(routes, list):
        routes = []

    target_count = max(
        SETTLEMENT_TARGET_MINIMUM,
        min(
            SETTLEMENT_TARGET_MAXIMUM,
            len(cells) // SETTLEMENT_TARGET_CELL_DIVISOR,
        ),
    )
    output_precision = int(world.get("summary", {}).get("output_float_precision", 4))
    world["settlement_selection_model"] = {
        "model_type": selection_model,
        "score_model": ("native_soil_biome_resource_water_climate_hazard_landform_score_with_annual_proxy_support_v3" if seasonal else "native_soil_biome_resource_water_climate_hazard_landform_score_v2"),
        "candidate_model": ("nonmarine_nonlake_annual_proxy_supported_raw_score_threshold_neighbor_local_max_v3" if seasonal else "nonmarine_nonlake_raw_score_threshold_neighbor_local_max_v2"),
        "rank_model": "descending_raw_score_then_cell_id_v1",
        "selection_model": "greedy_spherical_minimum_separation_until_target_v1",
        "target_model": "clamp_floor_cell_count_divisor_minimum_maximum_v1",
        "type_model": "adjacent_water_river_mining_agriculture_oasis_frontier_priority_v1",
        "score_threshold": SETTLEMENT_SCORE_THRESHOLD,
        "target_cell_divisor": SETTLEMENT_TARGET_CELL_DIVISOR,
        "target_minimum": SETTLEMENT_TARGET_MINIMUM,
        "target_maximum": SETTLEMENT_TARGET_MAXIMUM,
        "minimum_separation_factor": SETTLEMENT_MINIMUM_SEPARATION_FACTOR,
        "score_weights": {
            "water_access": 0.38,
            "fertility": 0.30,
            "climate": 0.18,
            "resource_bonus": 0.18,
        },
        "hazard_weights": {
            "convergent": 0.28,
            "transform": 0.18,
            "relief": 0.24,
            "ice": 0.22,
            "maximum": 0.65,
        },
        "cold_biome_multiplier": 0.18,
        "landform_score_adjustments": {
            "delta_or_floodplain_add": 0.08,
            "alluvial_fan_add": 0.03,
            "salt_flat_multiplier": 0.55,
            "glacial_valley_or_moraine_multiplier": 0.42,
            "glacial_lake_multiplier": 0.72,
            "coastal_plain_add": 0.04,
        },
        "threshold_and_rank_semantics": "unrounded_native_scores",
        "selection_score_precision": max(8, output_precision),
        "formula_replay_tolerance_model": "max_16_selection_units_one_output_unit",
        "record_order": "selection_order_with_sequential_ids",
        "deterministic": True,
        "candidate_cell_count": _candidate_count(cells, temperatures),
        "target_count": target_count,
        "settlement_count": len(settlements),
        "model_limitation": "static_suitability_selection_without_population_growth_land_market_or_infrastructure_feedback",
    }
    if seasonal:
        world["settlement_selection_model"]["annual_climate_applicability"] = dict(SETTLEMENT_CLIMATE_SUPPORT_MODEL)
    world["route_network_model"] = {
        "model_type": ROUTE_NETWORK_MODEL,
        "source_settlement_model": selection_model,
        "ranking_model": "endpoint_great_circle_distance_times_barrier_with_port_or_river_discount_v1",
        "barrier_model": "endpoint_mountain_tectonic_hazard_and_desert_multiplier_v1",
        "selection_model": "two_lowest_ranked_neighbors_per_settlement_then_unique_unordered_pair_v1",
        "route_type_model": "port_pair_river_basin_mountain_hazard_overland_priority_v1",
        "record_order": "source_settlement_order_then_rank_with_first_unique_pair_v1",
        "links_per_settlement": ROUTE_LINKS_PER_SETTLEMENT,
        "planet_radius_source": "planet_parameters.radius_km",
        "barrier_parameters": {
            "mountain_start_m": 1200.0,
            "mountain_scale_m": 2600.0,
            "mountain_weight": 0.95,
            "convergent_pair_weight": 0.50,
            "transform_pair_weight": 0.25,
            "tectonic_weight": 0.45,
            "desert_addition": 0.18,
        },
        "ranking_discounts": {"port_pair": 0.68, "shared_basin_river": 0.78},
        "mountain_route_elevation_threshold_m": 1300.0,
        "mountain_route_convergence_threshold": 0.24,
        "deterministic": True,
        "settlement_count": len(settlements),
        "route_count": len(routes),
        "model_limitation": "endpoint_only_network_selection_before_downstream_cell_path_routing_capacity_congestion_and_equilibrium",
    }
    summary = world.setdefault("summary", {})
    summary["settlement_selection_model"] = selection_model
    summary["route_network_model"] = ROUTE_NETWORK_MODEL
    return world
