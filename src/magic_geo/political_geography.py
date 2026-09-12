from __future__ import annotations

from collections import Counter
from typing import Any

from .settlement_routes import ROUTE_NETWORK_MODEL, SETTLEMENT_SELECTION_MODEL
from .settlement_climate_support import SEASONAL_SETTLEMENT_SELECTION_MODEL, seasonal_settlement_inputs


POLITICAL_REGION_MODEL = "causal_capital_barrier_partition_political_regions_v1"
POLITICAL_BORDER_MODEL = "causal_adjacent_region_terrain_border_segments_v1"
TRADE_FLOW_MODEL = "causal_route_endpoint_complement_trade_flows_v1"


def enrich_world_with_political_geography_models(
    world: dict[str, Any],
) -> dict[str, Any]:
    selection_model = (SEASONAL_SETTLEMENT_SELECTION_MODEL if seasonal_settlement_inputs(world) is not None else SETTLEMENT_SELECTION_MODEL)
    if selection_model == SEASONAL_SETTLEMENT_SELECTION_MODEL and world.get("settlement_selection_model", {}).get("model_type") != selection_model:
        raise ValueError("political geography requires matching settlement selection metadata")
    cells = world.get("cells", [])
    if not isinstance(cells, list) or not cells:
        return world
    settlements = world.get("settlements", [])
    routes = world.get("routes", [])
    regions = world.get("political_regions", [])
    borders = world.get("borders", [])
    flows = world.get("trade_flows", [])
    settlements = settlements if isinstance(settlements, list) else []
    routes = routes if isinstance(routes, list) else []
    regions = regions if isinstance(regions, list) else []
    borders = borders if isinstance(borders, list) else []
    flows = flows if isinstance(flows, list) else []
    target_count = (
        max(1, min(min(10, len(settlements)), len(settlements) // 5 + 1))
        if settlements
        else 0
    )

    world["political_region_model"] = {
        "model_type": POLITICAL_REGION_MODEL,
        "source_settlement_model": selection_model,
        "source_route_network_model": ROUTE_NETWORK_MODEL,
        "target_model": "clamp_floor_settlement_count_div_5_plus_1_1_min_10_count_v1",
        "capital_selection_model": "settlement_order_greedy_angular_separation_v1",
        "capital_minimum_angular_separation_rad": 0.18,
        "region_type_model": "port_river_mining_mountain_agrarian_frontier_priority_v1",
        "settlement_assignment_model": "minimum_endpoint_barrier_cost_with_basin_coast_direct_route_discounts_v1",
        "cell_assignment_model": "minimum_capital_endpoint_barrier_cost_with_basin_coast_discounts_v1",
        "settlement_assignment_discounts": {
            "shared_basin_river": 0.76,
            "shared_coast": 0.72,
            "direct_coastal_route": 0.45,
            "direct_other_route": 0.58,
        },
        "cell_assignment_discounts": {
            "shared_basin_river": 0.80,
            "shared_coast": 0.76,
        },
        "dominant_field_model": "count_then_native_enum_order_with_nonzero_resource_v1",
        "record_order": "capital_selection_order_with_sequential_region_ids",
        "deterministic": True,
        "target_count": target_count,
        "capital_count": len(regions),
        "region_count": len(regions),
        "model_limitation": "static_nearest_capital_partition_without_contiguity_constraint_population_feedback_or_state_dynamics",
    }
    border_types = Counter(
        str(border.get("type", "unknown"))
        for border in borders
        if isinstance(border, dict)
    )
    world["political_border_model"] = {
        "model_type": POLITICAL_BORDER_MODEL,
        "source_political_region_model": POLITICAL_REGION_MODEL,
        "candidate_model": "undirected_nonwater_adjacent_different_region_edges_v1",
        "record_order": "ascending_cell_id_then_exported_neighbor_order_v1",
        "type_model": "river_mountain_desert_ice_coastal_open_lowland_priority_v1",
        "length_model": "great_circle_cell_center_distance_v1",
        "barrier_model": "base_relief_tectonic_hazard_and_hard_type_bonus_v1",
        "mountain_elevation_threshold_m": 1400.0,
        "barrier_parameters": {
            "base": 0.18,
            "relief_scale_m": 2500.0,
            "convergent_pair_weight": 0.50,
            "transform_pair_weight": 0.25,
            "tectonic_weight": 0.45,
            "hard_type_bonus": 0.34,
        },
        "deterministic": True,
        "border_count": len(borders),
        "border_type_counts": dict(sorted(border_types.items())),
        "model_limitation": "cell_center_adjacency_segments_without_exact_native_edge_polygons_or_negotiated_boundaries",
    }
    flow_types = Counter(
        str(flow.get("primary_good", "none"))
        for flow in flows
        if isinstance(flow, dict)
    )
    world["trade_flow_model"] = {
        "model_type": TRADE_FLOW_MODEL,
        "source_route_network_model": ROUTE_NETWORK_MODEL,
        "source_political_region_model": POLITICAL_REGION_MODEL,
        "record_model": "one_flow_per_valid_route_in_route_order_v1",
        "primary_good_model": "endpoint_resource_priority_then_coastal_then_fertility_fallback_v1",
        "friction_model": "route_cost_div_max_one_distance_v1",
        "volume_model": "endpoint_strength_resource_fertility_climate_region_route_bonus_over_friction_v1",
        "resource_priority": {
            "volcanic_arc_metals": 6,
            "craton_iron_gold": 6,
            "placer_metals": 6,
            "sedimentary_fuels": 5,
            "evaporites": 5,
            "geothermal": 4,
            "fertile_alluvium": 3,
            "coastal_fisheries": 2,
            "none": 0,
        },
        "volume_parameters": {
            "scale": 80.0,
            "friction_offset": 0.55,
            "strategic_resource_bonus": 0.30,
            "fertile_or_fishery_bonus": 0.16,
            "fertility_complement_weight": 0.35,
            "climate_complement_scale_c": 45.0,
            "climate_complement_maximum": 0.55,
            "climate_complement_weight": 0.25,
            "interregional_bonus": 0.22,
            "coastal_route_bonus": 0.25,
            "river_route_bonus": 0.18,
            "mountain_route_bonus": -0.10,
            "maximum_volume_index": 100.0,
        },
        "deterministic": True,
        "route_count": len(routes),
        "flow_count": len(flows),
        "interregional_flow_count": sum(
            bool(flow.get("interregional", False))
            for flow in flows
            if isinstance(flow, dict)
        ),
        "primary_good_counts": dict(sorted(flow_types.items())),
        "total_volume_index": round(
            sum(
                float(flow.get("volume_index", 0.0))
                for flow in flows
                if isinstance(flow, dict)
            ),
            6,
        ),
        "model_limitation": "diagnostic_static_flow_without_supply_demand_inventory_price_capacity_or_equilibrium_feedback",
    }
    summary = world.setdefault("summary", {})
    summary["political_region_model"] = POLITICAL_REGION_MODEL
    summary["political_border_model"] = POLITICAL_BORDER_MODEL
    summary["trade_flow_model"] = TRADE_FLOW_MODEL
    return world
