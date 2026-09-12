"""Political region, border, and trade-flow replay checks."""

from __future__ import annotations

import math
from collections import Counter
from typing import Any
from .settlement_climate import replay_settlement_climate

from .._constants import (
    POLITICAL_BIOME_ORDER,
    POLITICAL_BORDER_MODEL,
    POLITICAL_REGION_MODEL,
    POLITICAL_RESOURCE_ORDER,
    ROUTE_NETWORK_MODEL,
    SETTLEMENT_DESERT_BIOMES,
    SETTLEMENT_MINING_RESOURCES,
    SETTLEMENT_SELECTION_MODEL,
    TRADE_FLOW_MODEL,
    TRADE_RESOURCE_PRIORITY,
)


def _political_clamp(
    value: float, lower: float = 0.0, upper: float = 1.0
) -> float:
    return max(lower, min(upper, value))


def _political_neighbors(
    cell: dict[str, Any], cells_by_id: dict[int, dict[str, Any]]
) -> list[dict[str, Any]]:
    raw_neighbor_ids = cell.get("neighbors", [])
    if not isinstance(raw_neighbor_ids, list):
        raise ValueError("neighbors must be a list")
    neighbors = []
    for raw_neighbor_id in raw_neighbor_ids:
        neighbor = cells_by_id.get(int(raw_neighbor_id))
        if neighbor is None:
            raise ValueError("neighbor does not exist")
        neighbors.append(neighbor)
    return neighbors


def _political_has_water_neighbor(
    cell: dict[str, Any], cells_by_id: dict[int, dict[str, Any]]
) -> bool:
    return any(
        bool(neighbor.get("is_water", False))
        for neighbor in _political_neighbors(cell, cells_by_id)
    )


def _political_angular_distance(
    first: dict[str, Any], second: dict[str, Any]
) -> float:
    first_position = first.get("position_3d", [])
    second_position = second.get("position_3d", [])
    if (
        not isinstance(first_position, list)
        or not isinstance(second_position, list)
        or len(first_position) != 3
        or len(second_position) != 3
    ):
        raise ValueError("position_3d invalid")
    dot = sum(
        float(first_value) * float(second_value)
        for first_value, second_value in zip(first_position, second_position)
    )
    return math.acos(_political_clamp(dot, -1.0, 1.0))


def _political_endpoint_barrier(
    first: dict[str, Any], second: dict[str, Any]
) -> float:
    mountain = _political_clamp(
        (
            max(
                float(first.get("elevation_m", 0.0)),
                float(second.get("elevation_m", 0.0)),
            )
            - 1200.0
        )
        / 2600.0
    )
    tectonic_hazard = 0.50 * (
        float(first.get("boundary_convergent", 0.0))
        + float(second.get("boundary_convergent", 0.0))
    ) + 0.25 * (
        float(first.get("boundary_transform", 0.0))
        + float(second.get("boundary_transform", 0.0))
    )
    desert = (
        0.18
        if str(first.get("biome", "")) in SETTLEMENT_DESERT_BIOMES
        or str(second.get("biome", "")) in SETTLEMENT_DESERT_BIOMES
        else 0.0
    )
    return (
        1.0
        + 0.95 * mountain
        + 0.45 * _political_clamp(tectonic_hazard)
        + desert
    )


def _political_local_relief(
    cell: dict[str, Any], cells_by_id: dict[int, dict[str, Any]]
) -> float:
    neighbors = _political_neighbors(cell, cells_by_id)
    if not neighbors:
        return 0.0
    mean_neighbor_elevation = sum(
        float(neighbor.get("elevation_m", 0.0)) for neighbor in neighbors
    ) / len(neighbors)
    return max(
        0.0,
        float(cell.get("elevation_m", 0.0)) - mean_neighbor_elevation,
    )


def _validate_political_regions(
    payload: dict[str, Any],
    summary: dict[str, Any],
    cells_by_id: dict[int, dict[str, Any]],
) -> list[str]:
    """Replay capital selection, settlement/cell partitions, and region records."""

    failure = ["political region model or causal replay invalid"]
    model = payload.get("political_region_model", {})
    settlements = payload.get("settlements", [])
    routes = payload.get("routes", [])
    regions = payload.get("political_regions", [])
    planet = payload.get("planet_parameters", {})
    try:
        selection_model, _ = replay_settlement_climate(payload)
        metadata_invalid = (
            not isinstance(model, dict)
            or not isinstance(settlements, list)
            or not isinstance(routes, list)
            or not isinstance(regions, list)
            or not isinstance(planet, dict)
            or model.get("model_type") != POLITICAL_REGION_MODEL
            or model.get("source_settlement_model")
            != selection_model
            or model.get("source_route_network_model") != ROUTE_NETWORK_MODEL
            or model.get("target_model")
            != "clamp_floor_settlement_count_div_5_plus_1_1_min_10_count_v1"
            or model.get("capital_selection_model")
            != "settlement_order_greedy_angular_separation_v1"
            or abs(
                float(
                    model.get("capital_minimum_angular_separation_rad", -1.0)
                )
                - 0.18
            )
            > 1.0e-12
            or model.get("region_type_model")
            != "port_river_mining_mountain_agrarian_frontier_priority_v1"
            or model.get("settlement_assignment_model")
            != "minimum_endpoint_barrier_cost_with_basin_coast_direct_route_discounts_v1"
            or model.get("cell_assignment_model")
            != "minimum_capital_endpoint_barrier_cost_with_basin_coast_discounts_v1"
            or model.get("settlement_assignment_discounts")
            != {
                "shared_basin_river": 0.76,
                "shared_coast": 0.72,
                "direct_coastal_route": 0.45,
                "direct_other_route": 0.58,
            }
            or model.get("cell_assignment_discounts")
            != {"shared_basin_river": 0.80, "shared_coast": 0.76}
            or model.get("dominant_field_model")
            != "count_then_native_enum_order_with_nonzero_resource_v1"
            or model.get("record_order")
            != "capital_selection_order_with_sequential_region_ids"
            or model.get("deterministic") is not True
            or model.get("model_limitation")
            != "static_nearest_capital_partition_without_contiguity_constraint_population_feedback_or_state_dynamics"
            or summary.get("political_region_model") != POLITICAL_REGION_MODEL
        )
    except (TypeError, ValueError):
        return failure
    if metadata_invalid or any(
        not isinstance(record, dict)
        for record in [*settlements, *routes, *regions]
    ):
        return failure

    settlements_by_id = {
        int(settlement.get("id", -1)): settlement for settlement in settlements
    }
    if sorted(settlements_by_id) != list(range(len(settlements))):
        return failure
    try:
        radius = float(planet.get("radius_km", -1.0))
        if radius <= 0.0:
            return failure

        def settlement_cell(settlement_id: int) -> dict[str, Any]:
            cell = cells_by_id.get(
                int(settlements_by_id[settlement_id].get("cell_id", -1))
            )
            if cell is None:
                raise ValueError("settlement cell does not exist")
            return cell

        target_count = (
            max(1, min(min(10, len(settlements)), len(settlements) // 5 + 1))
            if settlements
            else 0
        )
        capital_ids: list[int] = []
        for settlement_id in range(len(settlements)):
            cell = settlement_cell(settlement_id)
            if any(
                _political_angular_distance(
                    cell, settlement_cell(capital_id)
                )
                < 0.18
                for capital_id in capital_ids
            ):
                continue
            capital_ids.append(settlement_id)
            if len(capital_ids) >= target_count:
                break
        if settlements and not capital_ids:
            capital_ids.append(0)

        def region_type(capital_id: int) -> str:
            capital = settlements_by_id[capital_id]
            cell = settlement_cell(capital_id)
            settlement_type = str(capital.get("type", ""))
            resource = str(cell.get("resource", ""))
            landform = str(cell.get("landform", ""))
            if settlement_type == "port":
                return "maritime_league"
            if settlement_type == "river_city" or bool(
                cell.get("is_river", False)
            ):
                return "river_realm"
            if (
                settlement_type == "mining_town"
                or resource in SETTLEMENT_MINING_RESOURCES
            ):
                return "mining_domain"
            if (
                float(cell.get("elevation_m", 0.0)) > 1200.0
                or landform in {"mountain_belt", "glacial_valley"}
            ):
                return "mountain_march"
            if (
                settlement_type == "agricultural_town"
                or float(cell.get("fertility", 0.0)) > 0.68
                or resource == "fertile_alluvium"
            ):
                return "agrarian_state"
            return "frontier_territory"

        direct_route_by_pair: dict[tuple[int, int], dict[str, Any]] = {}
        for route in routes:
            first_id = int(route.get("from", -1))
            second_id = int(route.get("to", -1))
            if first_id < 0 or second_id < 0:
                return failure
            direct_route_by_pair.setdefault(
                (min(first_id, second_id), max(first_id, second_id)), route
            )

        def settlement_region_cost(
            settlement_id: int, capital_id: int
        ) -> float:
            first = settlement_cell(settlement_id)
            capital = settlement_cell(capital_id)
            cost = (
                _political_angular_distance(first, capital)
                * radius
                * _political_endpoint_barrier(first, capital)
            )
            if int(first.get("basin_id", -1)) == int(
                capital.get("basin_id", -2)
            ) and (
                bool(first.get("is_river", False))
                or bool(capital.get("is_river", False))
            ):
                cost *= 0.76
            if _political_has_water_neighbor(
                first, cells_by_id
            ) and _political_has_water_neighbor(capital, cells_by_id):
                cost *= 0.72
            route = direct_route_by_pair.get(
                (min(settlement_id, capital_id), max(settlement_id, capital_id))
            )
            if route is not None:
                cost *= 0.45 if str(route.get("type", "")) == "coastal_sea" else 0.58
            return cost

        expected_settlement_regions = {
            capital_id: region_id
            for region_id, capital_id in enumerate(capital_ids)
        }
        for settlement_id in range(len(settlements)):
            if settlement_id in expected_settlement_regions:
                continue
            best_cost = math.inf
            best_region = 0
            for region_id, capital_id in enumerate(capital_ids):
                cost = settlement_region_cost(settlement_id, capital_id)
                if cost < best_cost:
                    best_cost = cost
                    best_region = region_id
            expected_settlement_regions[settlement_id] = best_region

        expected_cell_regions: dict[int, int] = {}
        for cell_id, cell in cells_by_id.items():
            if bool(cell.get("is_water", False)):
                expected_cell_regions[cell_id] = -1
                continue
            best_cost = math.inf
            best_region = -1
            for region_id, capital_id in enumerate(capital_ids):
                capital = settlement_cell(capital_id)
                cost = (
                    _political_angular_distance(cell, capital)
                    * radius
                    * _political_endpoint_barrier(cell, capital)
                )
                if int(cell.get("basin_id", -1)) == int(
                    capital.get("basin_id", -2)
                ) and (
                    bool(cell.get("is_river", False))
                    or bool(capital.get("is_river", False))
                ):
                    cost *= 0.80
                if _political_has_water_neighbor(
                    cell, cells_by_id
                ) and _political_has_water_neighbor(capital, cells_by_id):
                    cost *= 0.76
                if cost < best_cost:
                    best_cost = cost
                    best_region = region_id
            expected_cell_regions[cell_id] = best_region
    except (KeyError, TypeError, ValueError):
        return failure

    try:
        if any(
            int(settlement.get("region_id", -2))
            != expected_settlement_regions[settlement_id]
            for settlement_id, settlement in settlements_by_id.items()
        ) or any(
            int(cells_by_id[cell_id].get("political_region_id", -2))
            != expected_region
            for cell_id, expected_region in expected_cell_regions.items()
        ):
            return failure
    except (TypeError, ValueError):
        return failure

    expected_regions: list[dict[str, Any]] = []
    for region_id, capital_id in enumerate(capital_ids):
        settlement_ids = [
            settlement_id
            for settlement_id in range(len(settlements))
            if expected_settlement_regions[settlement_id] == region_id
        ]
        region_cells = [
            cells_by_id[cell_id]
            for cell_id, assigned_region in expected_cell_regions.items()
            if assigned_region == region_id
        ]
        area = sum(float(cell.get("area_km2", 0.0)) for cell in region_cells)
        mean_elevation = (
            sum(
                float(cell.get("elevation_m", 0.0))
                * float(cell.get("area_km2", 0.0))
                for cell in region_cells
            )
            / area
            if area > 0.0
            else 0.0
        )
        barrier_pressure = (
            sum(
                _political_clamp(
                    _political_local_relief(cell, cells_by_id) / 1800.0
                )
                * float(cell.get("area_km2", 0.0))
                for cell in region_cells
            )
            / area
            if area > 0.0
            else 0.0
        )
        biome_counts = Counter(str(cell.get("biome", "")) for cell in region_cells)
        resource_counts = Counter(
            str(cell.get("resource", "")) for cell in region_cells
        )
        dominant_biome = next(
            (
                biome
                for biome in POLITICAL_BIOME_ORDER
                if biome_counts.get(biome, 0)
                == max(biome_counts.values(), default=0)
            ),
            "ocean",
        )
        nonzero_resource_max = max(
            (
                resource_counts.get(resource, 0)
                for resource in POLITICAL_RESOURCE_ORDER[1:]
            ),
            default=0,
        )
        dominant_resource = next(
            (
                resource
                for resource in POLITICAL_RESOURCE_ORDER[1:]
                if resource_counts.get(resource, 0) == nonzero_resource_max
                and nonzero_resource_max > 0
            ),
            "none",
        )
        route_count = sum(
            expected_settlement_regions.get(int(route.get("from", -1)))
            == region_id
            and expected_settlement_regions.get(int(route.get("to", -1)))
            == region_id
            for route in routes
        )
        expected_regions.append(
            {
                "id": region_id,
                "capital_settlement_id": capital_id,
                "type": region_type(capital_id),
                "dominant_biome": dominant_biome,
                "dominant_resource": dominant_resource,
                "settlement_count": len(settlement_ids),
                "route_count": route_count,
                "settlement_ids": settlement_ids,
                "area_km2": area,
                "mean_settlement_score": (
                    sum(
                        float(settlements_by_id[settlement_id].get("score", 0.0))
                        for settlement_id in settlement_ids
                    )
                    / len(settlement_ids)
                    if settlement_ids
                    else 0.0
                ),
                "mean_elevation_m": mean_elevation,
                "barrier_pressure": barrier_pressure,
            }
        )

    if (
        len(regions) != len(expected_regions)
        or int(model.get("target_count", -1)) != target_count
        or int(model.get("capital_count", -1)) != len(capital_ids)
        or int(model.get("region_count", -1)) != len(expected_regions)
        or int(summary.get("political_region_count", -1))
        != len(expected_regions)
    ):
        return failure
    precision = int(summary.get("output_float_precision", -1))
    unit = 10.0 ** (-precision)
    try:
        for actual, expected in zip(regions, expected_regions):
            area = float(expected["area_km2"])
            if (
                any(
                    actual.get(key) != expected[key]
                    for key in (
                        "id",
                        "capital_settlement_id",
                        "type",
                        "dominant_biome",
                        "dominant_resource",
                        "settlement_count",
                        "route_count",
                        "settlement_ids",
                    )
                )
                or abs(float(actual.get("area_km2", math.inf)) - area)
                > max(0.01, area * 1.0e-8)
                or abs(
                    float(actual.get("mean_settlement_score", math.inf))
                    - float(expected["mean_settlement_score"])
                )
                > unit * 2.0
                or abs(
                    float(actual.get("mean_elevation_m", math.inf))
                    - float(expected["mean_elevation_m"])
                )
                > max(0.001, unit * 2.0)
                or abs(
                    float(actual.get("barrier_pressure", math.inf))
                    - float(expected["barrier_pressure"])
                )
                > unit * 2.0
            ):
                return failure
    except (TypeError, ValueError):
        return failure
    return []


def _validate_political_borders(
    payload: dict[str, Any],
    summary: dict[str, Any],
    cells_by_id: dict[int, dict[str, Any]],
) -> list[str]:
    """Replay every cross-region adjacency edge, type, length, and score."""

    failure = ["political border model or causal replay invalid"]
    model = payload.get("political_border_model", {})
    borders = payload.get("borders", [])
    planet = payload.get("planet_parameters", {})
    try:
        selection_model, _ = replay_settlement_climate(payload)
        metadata_invalid = (
            not isinstance(model, dict)
            or not isinstance(borders, list)
            or not isinstance(planet, dict)
            or model.get("model_type") != POLITICAL_BORDER_MODEL
            or model.get("source_political_region_model")
            != POLITICAL_REGION_MODEL
            or model.get("candidate_model")
            != "undirected_nonwater_adjacent_different_region_edges_v1"
            or model.get("record_order")
            != "ascending_cell_id_then_exported_neighbor_order_v1"
            or model.get("type_model")
            != "river_mountain_desert_ice_coastal_open_lowland_priority_v1"
            or model.get("length_model")
            != "great_circle_cell_center_distance_v1"
            or model.get("barrier_model")
            != "base_relief_tectonic_hazard_and_hard_type_bonus_v1"
            or float(model.get("mountain_elevation_threshold_m", -1.0))
            != 1400.0
            or model.get("barrier_parameters")
            != {
                "base": 0.18,
                "relief_scale_m": 2500.0,
                "convergent_pair_weight": 0.50,
                "transform_pair_weight": 0.25,
                "tectonic_weight": 0.45,
                "hard_type_bonus": 0.34,
            }
            or model.get("deterministic") is not True
            or model.get("model_limitation")
            != "cell_center_adjacency_segments_without_exact_native_edge_polygons_or_negotiated_boundaries"
            or summary.get("political_border_model") != POLITICAL_BORDER_MODEL
        )
    except (TypeError, ValueError):
        return failure
    if metadata_invalid or any(not isinstance(border, dict) for border in borders):
        return failure

    def border_type(first: dict[str, Any], second: dict[str, Any]) -> str:
        if bool(first.get("is_river", False)) or bool(
            second.get("is_river", False)
        ):
            return "river"
        if (
            str(first.get("landform", ""))
            in {"mountain_belt", "glacial_valley"}
            or str(second.get("landform", ""))
            in {"mountain_belt", "glacial_valley"}
            or float(first.get("elevation_m", 0.0)) > 1400.0
            or float(second.get("elevation_m", 0.0)) > 1400.0
        ):
            return "mountain"
        if (
            str(first.get("biome", "")) in SETTLEMENT_DESERT_BIOMES
            or str(second.get("biome", "")) in SETTLEMENT_DESERT_BIOMES
        ):
            return "desert"
        if (
            str(first.get("landform", "")) == "ice_field"
            or str(second.get("landform", "")) == "ice_field"
            or str(first.get("biome", "")) == "ice_cap"
            or str(second.get("biome", "")) == "ice_cap"
        ):
            return "ice"
        if (
            str(first.get("landform", "")) == "coastal_plain"
            or str(second.get("landform", "")) == "coastal_plain"
        ):
            return "coastal"
        return "open_lowland"

    try:
        radius = float(planet.get("radius_km", -1.0))
        if radius <= 0.0:
            return failure
        expected_borders: list[dict[str, Any]] = []
        for cell_id in sorted(cells_by_id):
            cell = cells_by_id[cell_id]
            region_id = int(cell.get("political_region_id", -1))
            if bool(cell.get("is_water", False)) or region_id < 0:
                continue
            raw_neighbor_ids = cell.get("neighbors", [])
            if not isinstance(raw_neighbor_ids, list):
                return failure
            for raw_neighbor_id in raw_neighbor_ids:
                neighbor_id = int(raw_neighbor_id)
                if neighbor_id <= cell_id:
                    continue
                neighbor = cells_by_id.get(neighbor_id)
                if neighbor is None:
                    return failure
                neighbor_region = int(neighbor.get("political_region_id", -1))
                if (
                    bool(neighbor.get("is_water", False))
                    or neighbor_region < 0
                    or neighbor_region == region_id
                ):
                    continue
                selected_type = border_type(cell, neighbor)
                relief = abs(
                    float(cell.get("elevation_m", 0.0))
                    - float(neighbor.get("elevation_m", 0.0))
                )
                hazard = 0.50 * (
                    float(cell.get("boundary_convergent", 0.0))
                    + float(neighbor.get("boundary_convergent", 0.0))
                ) + 0.25 * (
                    float(cell.get("boundary_transform", 0.0))
                    + float(neighbor.get("boundary_transform", 0.0))
                )
                barrier_score = _political_clamp(
                    0.18
                    + relief / 2500.0
                    + hazard * 0.45
                    + (
                        0.34
                        if selected_type in {"mountain", "desert", "ice"}
                        else 0.0
                    )
                )
                expected_borders.append(
                    {
                        "id": len(expected_borders),
                        "region_a": min(region_id, neighbor_region),
                        "region_b": max(region_id, neighbor_region),
                        "cell_a": cell_id,
                        "cell_b": neighbor_id,
                        "type": selected_type,
                        "length_km": max(
                            0.001,
                            _political_angular_distance(cell, neighbor) * radius,
                        ),
                        "barrier_score": barrier_score,
                    }
                )
    except (TypeError, ValueError):
        return failure

    type_counts = Counter(border["type"] for border in expected_borders)
    if (
        len(borders) != len(expected_borders)
        or int(model.get("border_count", -1)) != len(expected_borders)
        or model.get("border_type_counts") != dict(sorted(type_counts.items()))
        or int(summary.get("border_segment_count", -1))
        != len(expected_borders)
    ):
        return failure
    precision = int(summary.get("output_float_precision", -1))
    unit = 10.0 ** (-precision)
    try:
        for actual, expected in zip(borders, expected_borders):
            if (
                any(
                    actual.get(key) != expected[key]
                    for key in (
                        "id",
                        "region_a",
                        "region_b",
                        "cell_a",
                        "cell_b",
                        "type",
                    )
                )
                or abs(
                    float(actual.get("length_km", math.inf))
                    - float(expected["length_km"])
                )
                > max(0.001, unit * 2.0)
                or abs(
                    float(actual.get("barrier_score", math.inf))
                    - float(expected["barrier_score"])
                )
                > unit * 2.0
            ):
                return failure
    except (TypeError, ValueError):
        return failure
    return []


def _validate_trade_flows(
    payload: dict[str, Any],
    summary: dict[str, Any],
    cells_by_id: dict[int, dict[str, Any]],
) -> list[str]:
    """Replay one endpoint-driven trade flow for every valid native route."""

    failure = ["trade flow model or causal replay invalid"]
    model = payload.get("trade_flow_model", {})
    flows = payload.get("trade_flows", [])
    routes = payload.get("routes", [])
    settlements = payload.get("settlements", [])
    try:
        metadata_invalid = (
            not isinstance(model, dict)
            or not isinstance(flows, list)
            or not isinstance(routes, list)
            or not isinstance(settlements, list)
            or model.get("model_type") != TRADE_FLOW_MODEL
            or model.get("source_route_network_model") != ROUTE_NETWORK_MODEL
            or model.get("source_political_region_model")
            != POLITICAL_REGION_MODEL
            or model.get("record_model")
            != "one_flow_per_valid_route_in_route_order_v1"
            or model.get("primary_good_model")
            != "endpoint_resource_priority_then_coastal_then_fertility_fallback_v1"
            or model.get("friction_model")
            != "route_cost_div_max_one_distance_v1"
            or model.get("volume_model")
            != "endpoint_strength_resource_fertility_climate_region_route_bonus_over_friction_v1"
            or model.get("resource_priority") != TRADE_RESOURCE_PRIORITY
            or model.get("volume_parameters")
            != {
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
            }
            or model.get("deterministic") is not True
            or model.get("model_limitation")
            != "diagnostic_static_flow_without_supply_demand_inventory_price_capacity_or_equilibrium_feedback"
            or summary.get("trade_flow_model") != TRADE_FLOW_MODEL
        )
    except (TypeError, ValueError):
        return failure
    if metadata_invalid or any(
        not isinstance(record, dict) for record in [*flows, *routes, *settlements]
    ):
        return failure
    settlements_by_id = {
        int(settlement.get("id", -1)): settlement for settlement in settlements
    }
    if sorted(settlements_by_id) != list(range(len(settlements))):
        return failure

    def endpoint_cell(settlement_id: int) -> dict[str, Any]:
        settlement = settlements_by_id.get(settlement_id)
        if settlement is None:
            raise ValueError("settlement does not exist")
        cell = cells_by_id.get(int(settlement.get("cell_id", -1)))
        if cell is None:
            raise ValueError("settlement cell does not exist")
        return cell

    def primary_good(
        first_settlement: dict[str, Any],
        second_settlement: dict[str, Any],
        first_cell: dict[str, Any],
        second_cell: dict[str, Any],
    ) -> str:
        selected = "none"
        best_priority = 0
        for cell in (first_cell, second_cell):
            resource = str(cell.get("resource", "none"))
            priority = TRADE_RESOURCE_PRIORITY.get(resource, 0)
            if resource != "none" and priority > best_priority:
                selected = resource
                best_priority = priority
        if selected != "none":
            return selected
        if (
            str(first_settlement.get("type", "")) == "port"
            or str(second_settlement.get("type", "")) == "port"
            or _political_has_water_neighbor(first_cell, cells_by_id)
            or _political_has_water_neighbor(second_cell, cells_by_id)
        ):
            return "coastal_fisheries"
        if (
            float(first_cell.get("fertility", 0.0)) > 0.62
            or float(second_cell.get("fertility", 0.0)) > 0.62
        ):
            return "fertile_alluvium"
        return "none"

    expected_flows: list[dict[str, Any]] = []
    try:
        for route in routes:
            first_id = int(route.get("from", -1))
            second_id = int(route.get("to", -1))
            if first_id not in settlements_by_id or second_id not in settlements_by_id:
                continue
            first_settlement = settlements_by_id[first_id]
            second_settlement = settlements_by_id[second_id]
            first_cell = endpoint_cell(first_id)
            second_cell = endpoint_cell(second_id)
            distance = float(route.get("distance_km", 0.0))
            friction = float(route.get("cost", 0.0)) / max(1.0, distance)
            selected_good = primary_good(
                first_settlement,
                second_settlement,
                first_cell,
                second_cell,
            )
            resource_bonus = (
                0.0
                if selected_good == "none"
                else 0.16
                if selected_good in {"fertile_alluvium", "coastal_fisheries"}
                else 0.30
            )
            fertility_complement = abs(
                float(first_cell.get("fertility", 0.0))
                - float(second_cell.get("fertility", 0.0))
            )
            climate_complement = _political_clamp(
                abs(
                    float(first_cell.get("temperature_c", 0.0))
                    - float(second_cell.get("temperature_c", 0.0))
                )
                / 45.0,
                0.0,
                0.55,
            )
            first_region = int(first_settlement.get("region_id", -1))
            second_region = int(second_settlement.get("region_id", -1))
            interregional = (
                first_region >= 0
                and second_region >= 0
                and first_region != second_region
            )
            route_type = str(route.get("type", ""))
            route_bonus = (
                0.25
                if route_type == "coastal_sea"
                else 0.18
                if route_type == "river_corridor"
                else -0.10
                if route_type == "mountain_pass"
                else 0.0
            )
            endpoint_strength = 0.50 * (
                float(first_settlement.get("score", 0.0))
                + float(second_settlement.get("score", 0.0))
            )
            volume = (
                80.0
                * endpoint_strength
                * (
                    1.0
                    + resource_bonus
                    + 0.35 * fertility_complement
                    + 0.25 * climate_complement
                    + (0.22 if interregional else 0.0)
                    + route_bonus
                )
                / (0.55 + friction)
            )
            expected_flows.append(
                {
                    "id": len(expected_flows),
                    "route_id": int(route.get("id", -1)),
                    "from": first_id,
                    "to": second_id,
                    "region_from": first_region,
                    "region_to": second_region,
                    "primary_good": selected_good,
                    "interregional": interregional,
                    "distance_km": distance,
                    "friction": friction,
                    "volume_index": _political_clamp(volume, 0.0, 100.0),
                }
            )
    except (TypeError, ValueError):
        return failure

    precision = int(summary.get("output_float_precision", -1))
    unit = 10.0 ** (-precision)
    good_counts = Counter(flow["primary_good"] for flow in expected_flows)
    interregional_count = sum(flow["interregional"] for flow in expected_flows)
    serialized_volume_total = round(
        sum(round(float(flow["volume_index"]), precision) for flow in expected_flows),
        6,
    )
    if (
        len(flows) != len(expected_flows)
        or int(model.get("route_count", -1)) != len(routes)
        or int(model.get("flow_count", -1)) != len(expected_flows)
        or int(model.get("interregional_flow_count", -1))
        != interregional_count
        or model.get("primary_good_counts") != dict(sorted(good_counts.items()))
        or abs(
            float(model.get("total_volume_index", math.inf))
            - serialized_volume_total
        )
        > max(1.0e-6, len(expected_flows) * 0.02)
        or int(summary.get("trade_flow_count", -1)) != len(expected_flows)
    ):
        return failure
    try:
        for actual, expected in zip(flows, expected_flows):
            if (
                any(
                    actual.get(key) != expected[key]
                    for key in (
                        "id",
                        "route_id",
                        "from",
                        "to",
                        "region_from",
                        "region_to",
                        "primary_good",
                        "interregional",
                    )
                )
                or float(actual.get("distance_km", math.inf))
                != float(expected["distance_km"])
                or abs(
                    float(actual.get("friction", math.inf))
                    - float(expected["friction"])
                )
                > max(0.001, unit * 4.0)
                or abs(
                    float(actual.get("volume_index", math.inf))
                    - float(expected["volume_index"])
                )
                > max(0.02, unit * 4.0)
            ):
                return failure
    except (TypeError, ValueError):
        return failure
    return []
