"""Route-corridor replay checks."""

from __future__ import annotations

import heapq
import math
from collections import Counter
from typing import Any

from ...planet_parameters import planet_radius_km as configured_planet_radius_km
from .._constants import (
    AQUIFER_RESOURCE_MODEL,
    NAVIGABILITY_MARINE_WATER_TYPES,
    NAVIGABILITY_MODEL,
    PORT_SITE_MODEL,
    ROUTE_CORRIDOR_MODEL,
    ROUTE_DESERT_BIOMES,
    ROUTE_FEATURE_THRESHOLD,
    ROUTE_MOUNTAIN_LANDFORMS,
    ROUTE_RIVER_VALLEY_LANDFORMS,
)


def _validate_route_corridors(
    payload: dict[str, Any],
    summary: dict[str, Any],
    cells_by_id: dict[int, dict[str, Any]],
) -> list[str]:
    """Replay feature fields, weighted Dijkstra paths, assignment, and records."""

    failure = ["route corridor model or causal replay invalid"]
    model = payload.get("route_corridor_model", {})
    corridors = payload.get("route_corridors", [])
    routes = payload.get("routes", [])
    settlements = payload.get("settlements", [])
    radius_km = configured_planet_radius_km(payload)
    try:
        metadata_invalid = (
            not isinstance(model, dict)
            or not isinstance(corridors, list)
            or not isinstance(routes, list)
            or not isinstance(settlements, list)
            or model.get("model_type") != ROUTE_CORRIDOR_MODEL
            or model.get("source_navigability_model") != NAVIGABILITY_MODEL
            or model.get("source_port_model") != PORT_SITE_MODEL
            or model.get("source_aquifer_model") != AQUIFER_RESOURCE_MODEL
            or model.get("domain")
            != "all_cells_with_one_path_per_valid_route"
            or model.get("mountain_pass_model")
            != "neighbor_saddle_convergence_landform_relief_elevation_ice_v1"
            or model.get("river_valley_model")
            != "flow_runoff_river_landform_relief_navigability_ice_v1"
            or model.get("coastal_model")
            != "marine_or_coastal_contact_navigability_harbor_port_depth_relief_v1"
            or model.get("oasis_model")
            != "aridity_water_recharge_aquifer_soil_fertility_settlement_ice_v1"
            or model.get("movement_cost_model")
            != "directed_distance_terrain_water_route_type_feature_support_v1"
            or model.get("path_model")
            != "strict_improvement_dijkstra_cost_then_cell_id_heap_v1"
            or model.get("corridor_classification_model")
            != "route_type_preference_then_feature_count_lexical_tie_v1"
            or model.get("cell_assignment_model")
            != "maximum_membership_with_later_route_winning_equal_ties_v1"
            or model.get("record_order")
            != "ascending_route_id_for_valid_endpoints_and_paths"
            or abs(float(model.get("planet_radius_km", -1.0)) - radius_km)
            > 1.0e-9
            or abs(
                float(model.get("feature_threshold", -1.0))
                - ROUTE_FEATURE_THRESHOLD
            )
            > 1.0e-12
            or model.get("threshold_semantics")
            != "serialized_feature_indices"
            or model.get("deterministic") is not True
            or model.get("model_limitation")
            != "diagnostic_static_corridors_without_capacity_congestion_seasonality_construction_cost_network_equilibrium_or_multimodal_scheduling"
            or summary.get("route_corridor_model") != ROUTE_CORRIDOR_MODEL
        )
    except (TypeError, ValueError):
        return failure
    if metadata_invalid:
        return failure

    def clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
        return max(lower, min(upper, value))

    def distance_km(first: dict[str, Any], second: dict[str, Any]) -> float:
        first_lat = math.radians(float(first.get("lat_deg", 0.0)))
        first_lon = math.radians(float(first.get("lon_deg", 0.0)))
        second_lat = math.radians(float(second.get("lat_deg", 0.0)))
        second_lon = math.radians(float(second.get("lon_deg", 0.0)))
        delta_lat = second_lat - first_lat
        delta_lon = second_lon - first_lon
        sin_lat = math.sin(delta_lat * 0.5)
        sin_lon = math.sin(delta_lon * 0.5)
        haversine = (
            sin_lat * sin_lat
            + math.cos(first_lat) * math.cos(second_lat) * sin_lon * sin_lon
        )
        return max(
            0.001,
            radius_km
            * 2.0
            * math.asin(min(1.0, math.sqrt(max(0.0, haversine)))),
        )

    def marine_neighbors(cell: dict[str, Any]) -> list[dict[str, Any]]:
        raw_neighbors = cell.get("neighbors", [])
        if not isinstance(raw_neighbors, list):
            raise ValueError("neighbors must be a list")
        return [
            neighbor
            for raw_neighbor_id in raw_neighbors
            if (neighbor := cells_by_id.get(int(raw_neighbor_id))) is not None
            and str(neighbor.get("water_body_type", "land"))
            in NAVIGABILITY_MARINE_WATER_TYPES
        ]

    def land_neighbors(cell: dict[str, Any]) -> list[dict[str, Any]]:
        raw_neighbors = cell.get("neighbors", [])
        if not isinstance(raw_neighbors, list):
            raise ValueError("neighbors must be a list")
        return [
            neighbor
            for raw_neighbor_id in raw_neighbors
            if (neighbor := cells_by_id.get(int(raw_neighbor_id))) is not None
            and not bool(neighbor.get("is_water", False))
        ]

    def is_coastal(cell: dict[str, Any]) -> bool:
        return (
            str(cell.get("water_body_type", "land"))
            in NAVIGABILITY_MARINE_WATER_TYPES
            or bool(marine_neighbors(cell))
        )

    settlements_by_id = {
        int(settlement.get("id", -1)): settlement
        for settlement in settlements
        if isinstance(settlement, dict)
        and int(settlement.get("id", -1)) >= 0
    }
    if any(not isinstance(settlement, dict) for settlement in settlements):
        return failure
    route_by_id = {
        int(route.get("id", -1)): route
        for route in routes
        if isinstance(route, dict) and int(route.get("id", -1)) >= 0
    }
    if any(not isinstance(route, dict) for route in routes):
        return failure
    oasis_settlement_cell_ids = {
        int(settlement.get("cell_id", -1))
        for settlement in settlements
        if str(settlement.get("type", "")) == "oasis"
        and int(settlement.get("cell_id", -1)) >= 0
    }
    try:
        max_flow = max(
            (
                max(0.0, float(cell.get("flow_accumulation", 0.0)))
                for cell in cells_by_id.values()
            ),
            default=1.0,
        )
    except (TypeError, ValueError):
        return failure

    def mountain_pass(cell: dict[str, Any]) -> float:
        if bool(cell.get("is_water", False)):
            return 0.0
        elevation = float(cell.get("elevation_m", 0.0))
        neighbors = land_neighbors(cell)
        if not neighbors:
            return 0.0
        elevations = [
            float(neighbor.get("elevation_m", 0.0)) for neighbor in neighbors
        ]
        high_neighbors = [value for value in elevations if value >= 900.0]
        landform = str(cell.get("landform", ""))
        context = max(
            clamp((max(elevations, default=elevation) - 700.0) / 2300.0),
            clamp(float(cell.get("boundary_convergent", 0.0)) * 1.9),
            0.68 if landform in ROUTE_MOUNTAIN_LANDFORMS else 0.0,
        )
        if context <= 0.05 and not high_neighbors:
            return 0.0
        high_mean = (
            sum(high_neighbors) / len(high_neighbors)
            if high_neighbors
            else max(elevations)
        )
        saddle_gap = clamp((high_mean - elevation + 260.0) / 1150.0)
        pass_elevation = clamp((elevation - 180.0) / 1700.0)
        relief_window = clamp((max(elevations) - min(elevations)) / 1900.0)
        ice_penalty = clamp(float(cell.get("ice_thickness_m", 0.0)) / 280.0)
        return clamp(
            context * 0.38
            + saddle_gap * 0.32
            + relief_window * 0.18
            + pass_elevation * 0.12
            - ice_penalty * 0.30
        )

    def river_valley(cell: dict[str, Any]) -> float:
        if bool(cell.get("is_water", False)) and str(
            cell.get("water_body_type", "land")
        ) in NAVIGABILITY_MARINE_WATER_TYPES:
            return 0.0
        landform = str(cell.get("landform", ""))
        flow = clamp(
            float(cell.get("flow_accumulation", 0.0)) / max(1.0, max_flow)
        )
        runoff = clamp(float(cell.get("runoff_mm_y", 0.0)) / 850.0)
        river = 0.34 if bool(cell.get("is_river", False)) else 0.0
        valley = 0.28 if landform in ROUTE_RIVER_VALLEY_LANDFORMS else 0.0
        low_relief = clamp(
            1.0 - abs(float(cell.get("elevation_m", 0.0))) / 1900.0
        )
        navigability = clamp(
            float(cell.get("river_navigability_index", 0.0))
        )
        ice_penalty = clamp(float(cell.get("ice_thickness_m", 0.0)) / 260.0)
        return clamp(
            flow * 0.22
            + runoff * 0.14
            + river
            + valley
            + low_relief * 0.12
            + navigability * 0.16
            - ice_penalty * 0.24
        )

    def coastal(cell: dict[str, Any]) -> float:
        water_body = str(cell.get("water_body_type", "land"))
        adjacent_marine = marine_neighbors(cell)
        if water_body in NAVIGABILITY_MARINE_WATER_TYPES:
            land_contact = clamp(len(land_neighbors(cell)) / 4.0)
            shelf = (
                0.25
                if water_body in {"continental_shelf", "inland_sea"}
                else 0.10
            )
            navigability = clamp(
                float(cell.get("coastal_navigability_index", 0.0))
            )
            chokepoint = clamp(
                float(cell.get("transport_chokepoint_index", 0.0))
            )
            depth_access = clamp(
                1.0 - float(cell.get("water_depth_m", 0.0)) / 700.0
            )
            return clamp(
                shelf
                + land_contact * 0.22
                + navigability * 0.30
                + chokepoint * 0.18
                + depth_access * 0.15
            )
        if not adjacent_marine:
            return 0.0
        marine_contact = clamp(len(adjacent_marine) / 3.0)
        low_relief = clamp(
            1.0 - abs(float(cell.get("elevation_m", 0.0))) / 1200.0
        )
        harbor = clamp(float(cell.get("harbor_suitability_index", 0.0)))
        port = clamp(float(cell.get("port_suitability_index", 0.0)))
        navigability = clamp(
            float(cell.get("coastal_navigability_index", 0.0))
        )
        return clamp(
            marine_contact * 0.24
            + low_relief * 0.18
            + harbor * 0.20
            + port * 0.18
            + navigability * 0.20
        )

    def oasis(cell: dict[str, Any]) -> float:
        if bool(cell.get("is_water", False)):
            return 0.0
        biome = str(cell.get("biome", ""))
        aridity = clamp(float(cell.get("seasonal_aridity_index", 0.0)))
        arid_context = max(
            aridity, 0.72 if biome in ROUTE_DESERT_BIOMES else 0.0
        )
        cell_id = int(cell.get("id", -1))
        if arid_context < 0.45 and cell_id not in oasis_settlement_cell_ids:
            return 0.0
        water_access = max(
            0.85 if bool(cell.get("is_river", False)) else 0.0,
            0.70 if bool(cell.get("is_lake", False)) else 0.0,
            clamp(float(cell.get("runoff_mm_y", 0.0)) / 220.0),
            clamp(float(cell.get("groundwater_recharge_mm_y", 0.0)) / 180.0),
            clamp(float(cell.get("aquifer_productivity_index", 0.0))),
            clamp(float(cell.get("soil_moisture_index", 0.0))),
        )
        fertility = clamp(float(cell.get("fertility", 0.0)))
        settlement = 0.25 if cell_id in oasis_settlement_cell_ids else 0.0
        return clamp(
            arid_context * 0.32
            + water_access * 0.43
            + fertility * 0.12
            + settlement
            - clamp(float(cell.get("ice_thickness_m", 0.0)) / 200.0)
        )

    expected_by_id: dict[int, dict[str, Any]] = {}
    for cell_id, cell in cells_by_id.items():
        try:
            expected_by_id[cell_id] = {
                "mountain": round(mountain_pass(cell), 6),
                "river": round(river_valley(cell), 6),
                "coastal": round(coastal(cell), 6),
                "oasis": round(oasis(cell), 6),
                "corridor": 0.0,
                "type": "none",
                "corridor_id": -1,
            }
        except (TypeError, ValueError):
            return failure

    def feature_values(cell_id: int) -> dict[str, float]:
        expected = expected_by_id[cell_id]
        return {
            "mountain_pass_corridor": float(expected["mountain"]),
            "river_valley_corridor": float(expected["river"]),
            "coastal_corridor": float(expected["coastal"]),
            "oasis_corridor": float(expected["oasis"]),
        }

    def movement_cost(
        current_id: int, neighbor_id: int, route_type: str
    ) -> float:
        current = cells_by_id[current_id]
        neighbor = cells_by_id[neighbor_id]
        distance = distance_km(current, neighbor)
        water_body = str(neighbor.get("water_body_type", "land"))
        is_water = bool(neighbor.get("is_water", False))
        elevation_delta = abs(
            float(neighbor.get("elevation_m", 0.0))
            - float(current.get("elevation_m", 0.0))
        )
        slope = clamp(elevation_delta / 2000.0)
        ice = clamp(float(neighbor.get("ice_thickness_m", 0.0)) / 320.0)
        aridity = clamp(float(neighbor.get("seasonal_aridity_index", 0.0)))
        mountain = clamp(
            (float(neighbor.get("elevation_m", 0.0)) - 1000.0) / 2200.0
        )
        features = feature_values(neighbor_id)
        if route_type == "coastal_sea":
            support = max(
                features["coastal_corridor"],
                float(neighbor.get("navigability_index", 0.0)),
            )
            water_penalty = (
                0.08
                if water_body in NAVIGABILITY_MARINE_WATER_TYPES
                else 0.72
                if is_coastal(neighbor)
                else 1.80
            )
        elif route_type == "river_corridor":
            support = max(
                features["river_valley_corridor"],
                float(neighbor.get("river_navigability_index", 0.0)),
            )
            water_penalty = (
                1.45
                if water_body in NAVIGABILITY_MARINE_WATER_TYPES
                else 0.18
                if bool(neighbor.get("is_river", False))
                else 0.42
            )
        elif route_type == "mountain_pass":
            support = max(
                features["mountain_pass_corridor"],
                features["river_valley_corridor"] * 0.45,
            )
            water_penalty = 1.70 if is_water else 0.20
        else:
            support = max(
                features["river_valley_corridor"] * 0.72,
                features["coastal_corridor"] * 0.62,
                features["oasis_corridor"] * 0.72,
                features["mountain_pass_corridor"] * 0.46,
            )
            water_penalty = (
                1.65
                if water_body in NAVIGABILITY_MARINE_WATER_TYPES
                else 0.20
                if bool(neighbor.get("is_river", False))
                else 0.34
            )
        terrain = (
            0.64
            + slope * 0.42
            + ice * 0.55
            + aridity * 0.18
            + mountain * 0.20
            + water_penalty
            - support * 0.50
        )
        return distance * max(0.12, terrain)

    def shortest_path(start: int, end: int, route_type: str) -> list[int]:
        if start == end and start in cells_by_id:
            return [start]
        if start not in cells_by_id or end not in cells_by_id:
            return []
        queue: list[tuple[float, int]] = [(0.0, start)]
        best_cost = {start: 0.0}
        previous: dict[int, int] = {}
        visited: set[int] = set()
        while queue:
            cost, cell_id = heapq.heappop(queue)
            if cell_id in visited:
                continue
            visited.add(cell_id)
            if cell_id == end:
                break
            raw_neighbors = cells_by_id[cell_id].get("neighbors", [])
            if not isinstance(raw_neighbors, list):
                return []
            for raw_neighbor_id in raw_neighbors:
                neighbor_id = int(raw_neighbor_id)
                if neighbor_id not in cells_by_id:
                    continue
                next_cost = cost + movement_cost(
                    cell_id, neighbor_id, route_type
                )
                if next_cost < best_cost.get(neighbor_id, math.inf):
                    best_cost[neighbor_id] = next_cost
                    previous[neighbor_id] = cell_id
                    heapq.heappush(queue, (next_cost, neighbor_id))
        if end not in best_cost:
            return []
        path = [end]
        while path[-1] != start:
            parent = previous.get(path[-1])
            if parent is None:
                return []
            path.append(parent)
        return list(reversed(path))

    def corridor_type(path: list[int], route_type: str) -> str:
        counts = {
            name: sum(
                feature_values(cell_id)[name] >= ROUTE_FEATURE_THRESHOLD
                for cell_id in path
            )
            for name in (
                "mountain_pass_corridor",
                "river_valley_corridor",
                "coastal_corridor",
                "oasis_corridor",
            )
        }
        if route_type == "coastal_sea" and counts["coastal_corridor"] > 0:
            return "coastal_corridor"
        if route_type == "river_corridor" and counts["river_valley_corridor"] > 0:
            return "river_valley_corridor"
        if route_type == "mountain_pass" and counts["mountain_pass_corridor"] > 0:
            return "mountain_pass_corridor"
        best_type, best_count = sorted(
            counts.items(), key=lambda item: (-item[1], item[0])
        )[0]
        return best_type if best_count > 0 else "overland_corridor"

    expected_route_fields: dict[int, dict[str, Any]] = {}
    expected_corridors: list[dict[str, Any]] = []
    for route_id in sorted(route_by_id):
        route = route_by_id[route_id]
        source = settlements_by_id.get(int(route.get("from", -1)))
        target = settlements_by_id.get(int(route.get("to", -1)))
        if source is None or target is None:
            expected_route_fields[route_id] = {
                "route_corridor_id": -1,
                "route_corridor_type": "none",
                "path_cell_ids": [],
            }
            continue
        start = int(source.get("cell_id", -1))
        end = int(target.get("cell_id", -1))
        route_type = str(route.get("type", "overland"))
        path = shortest_path(start, end, route_type)
        if not path:
            expected_route_fields[route_id] = {
                "route_corridor_id": -1,
                "route_corridor_type": "none",
                "path_cell_ids": [],
            }
            continue
        corridor_id = len(expected_corridors)
        selected_type = corridor_type(path, route_type)
        for cell_id in path:
            support = max(feature_values(cell_id).values())
            membership = clamp(0.35 + support * 0.65)
            if membership >= float(expected_by_id[cell_id]["corridor"]):
                expected_by_id[cell_id]["corridor"] = round(membership, 6)
                expected_by_id[cell_id]["type"] = selected_type
                expected_by_id[cell_id]["corridor_id"] = corridor_id
        expected_route_fields[route_id] = {
            "route_corridor_id": corridor_id,
            "route_corridor_type": selected_type,
            "path_cell_ids": path,
        }
        path_length = sum(
            distance_km(cells_by_id[first], cells_by_id[second])
            for first, second in zip(path, path[1:])
        )
        straight_distance = max(0.001, float(route.get("distance_km", 0.0)))
        feature_counts = {
            name: sum(
                feature_values(cell_id)[name] >= ROUTE_FEATURE_THRESHOLD
                for cell_id in path
            )
            for name in (
                "mountain_pass_corridor",
                "river_valley_corridor",
                "coastal_corridor",
                "oasis_corridor",
            )
        }
        named_count = sum(
            any(
                value >= ROUTE_FEATURE_THRESHOLD
                for value in feature_values(cell_id).values()
            )
            for cell_id in path
        )
        corridor_values = [
            float(expected_by_id[cell_id]["corridor"]) for cell_id in path
        ]
        mountain_values = [feature_values(cell_id)["mountain_pass_corridor"] for cell_id in path]
        river_values = [feature_values(cell_id)["river_valley_corridor"] for cell_id in path]
        coastal_values = [feature_values(cell_id)["coastal_corridor"] for cell_id in path]
        oasis_values = [feature_values(cell_id)["oasis_corridor"] for cell_id in path]
        expected_corridors.append(
            {
                "id": corridor_id,
                "route_id": route_id,
                "route_type": route_type,
                "corridor_type": selected_type,
                "from_settlement_id": int(route.get("from", -1)),
                "to_settlement_id": int(route.get("to", -1)),
                "start_cell_id": start,
                "end_cell_id": end,
                "cell_count": len(path),
                "cell_ids": path,
                "path_length_km": round(path_length, 6),
                "straight_distance_km": round(straight_distance, 6),
                "detour_ratio": round(path_length / straight_distance, 6),
                "mean_route_corridor_index": round(
                    sum(corridor_values) / len(corridor_values), 6
                ),
                "max_route_corridor_index": round(max(corridor_values), 6),
                "mean_mountain_pass_route_index": round(
                    sum(mountain_values) / len(mountain_values), 6
                ),
                "mean_river_valley_route_index": round(
                    sum(river_values) / len(river_values), 6
                ),
                "mean_coastal_route_index": round(
                    sum(coastal_values) / len(coastal_values), 6
                ),
                "mean_oasis_route_index": round(
                    sum(oasis_values) / len(oasis_values), 6
                ),
                "mountain_pass_cell_count": feature_counts[
                    "mountain_pass_corridor"
                ],
                "river_valley_cell_count": feature_counts[
                    "river_valley_corridor"
                ],
                "coastal_cell_count": feature_counts["coastal_corridor"],
                "oasis_cell_count": feature_counts["oasis_corridor"],
                "named_feature_cell_count": named_count,
                "settlement_ids": sorted(
                    {int(route.get("from", -1)), int(route.get("to", -1))}
                    - {-1}
                ),
                "region_ids": sorted(
                    {
                        int(source.get("region_id", -1)),
                        int(target.get("region_id", -1)),
                    }
                    - {-1}
                ),
                "route_ids": [route_id],
                "navigable_waterway_ids": sorted(
                    {
                        int(cells_by_id[cell_id].get("navigable_waterway_id", -1))
                        for cell_id in path
                        if int(
                            cells_by_id[cell_id].get(
                                "navigable_waterway_id", -1
                            )
                        )
                        >= 0
                    }
                ),
                "port_site_ids": sorted(
                    {
                        int(cells_by_id[cell_id].get("port_site_id", -1))
                        for cell_id in path
                        if int(cells_by_id[cell_id].get("port_site_id", -1))
                        >= 0
                    }
                ),
            }
        )

    field_map = {
        "mountain_pass_route_index": "mountain",
        "river_valley_route_index": "river",
        "coastal_route_index": "coastal",
        "oasis_route_index": "oasis",
        "route_corridor_index": "corridor",
    }
    for cell_id, expected in expected_by_id.items():
        cell = cells_by_id[cell_id]
        try:
            if (
                any(
                    abs(float(cell.get(field, math.inf)) - float(expected[key]))
                    > 1.0e-9
                    for field, key in field_map.items()
                )
                or str(cell.get("route_corridor_type", "")) != expected["type"]
                or int(cell.get("route_corridor_id", -2))
                != expected["corridor_id"]
            ):
                return failure
        except (TypeError, ValueError):
            return failure
    for route_id, expected in expected_route_fields.items():
        route = route_by_id[route_id]
        if (
            int(route.get("route_corridor_id", -2))
            != expected["route_corridor_id"]
            or str(route.get("route_corridor_type", ""))
            != expected["route_corridor_type"]
            or [int(value) for value in route.get("path_cell_ids", [])]
            != expected["path_cell_ids"]
        ):
            return failure
    if len(corridors) != len(expected_corridors):
        return failure
    for actual, expected in zip(corridors, expected_corridors):
        if not isinstance(actual, dict) or any(
            actual.get(key) != value for key, value in expected.items()
        ):
            return failure
    if (
        int(model.get("route_count", -1)) != len(route_by_id)
        or int(model.get("corridor_count", -1)) != len(expected_corridors)
    ):
        return failure

    type_counts = Counter(
        corridor["corridor_type"] for corridor in expected_corridors
    )
    cell_count = len(cells_by_id)
    if cell_count <= 0:
        return failure
    expected_summary = {
        "route_corridor_model": ROUTE_CORRIDOR_MODEL,
        "route_corridor_count": len(expected_corridors),
        "route_corridor_cell_count": sum(
            int(expected["corridor_id"]) >= 0
            for expected in expected_by_id.values()
        ),
        "route_corridor_total_path_length_km": round(
            sum(corridor["path_length_km"] for corridor in expected_corridors),
            6,
        ),
        "mean_route_corridor_index": round(
            sum(float(expected["corridor"]) for expected in expected_by_id.values())
            / cell_count,
            6,
        ),
        "mean_mountain_pass_route_index": round(
            sum(float(expected["mountain"]) for expected in expected_by_id.values())
            / cell_count,
            6,
        ),
        "mean_river_valley_route_index": round(
            sum(float(expected["river"]) for expected in expected_by_id.values())
            / cell_count,
            6,
        ),
        "mean_coastal_route_index": round(
            sum(float(expected["coastal"]) for expected in expected_by_id.values())
            / cell_count,
            6,
        ),
        "mean_oasis_route_index": round(
            sum(float(expected["oasis"]) for expected in expected_by_id.values())
            / cell_count,
            6,
        ),
        "route_feature_coverage_index": (
            round(
                sum(
                    corridor["named_feature_cell_count"] > 0
                    for corridor in expected_corridors
                )
                / len(expected_corridors),
                6,
            )
            if expected_corridors
            else 1.0
        ),
        "mountain_pass_route_corridor_count": type_counts.get(
            "mountain_pass_corridor", 0
        ),
        "river_valley_route_corridor_count": type_counts.get(
            "river_valley_corridor", 0
        ),
        "coastal_route_corridor_count": type_counts.get(
            "coastal_corridor", 0
        ),
        "oasis_route_corridor_count": type_counts.get("oasis_corridor", 0),
        "route_corridor_type_counts": dict(sorted(type_counts.items())),
    }
    if any(summary.get(key) != value for key, value in expected_summary.items()):
        return failure
    return []
