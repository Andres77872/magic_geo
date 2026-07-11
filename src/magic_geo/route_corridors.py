from __future__ import annotations

import heapq
import math
from collections import Counter
from typing import Any

from .planet_parameters import planet_radius_km


MARINE_WATER_TYPES = {"ocean", "continental_shelf", "inland_sea"}
ROUTE_CORRIDOR_MODEL = "causal_feature_weighted_dijkstra_route_corridors_v1"
MOUNTAIN_PASS_THRESHOLD = 0.45
RIVER_VALLEY_THRESHOLD = 0.45
COASTAL_ROUTE_THRESHOLD = 0.45
OASIS_ROUTE_THRESHOLD = 0.45
MOUNTAIN_LANDFORMS = {"mountain", "mountain_range", "volcanic_arc", "highland", "ridge", "glacial_valley"}
RIVER_VALLEY_LANDFORMS = {"delta", "floodplain", "river_valley", "alluvial_fan", "wetland"}
DESERT_BIOMES = {"hot_desert", "cold_desert", "desert", "semi_arid_desert"}


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _cell_distance_km(
    first: dict[str, Any],
    second: dict[str, Any],
    radius_km: float,
) -> float:
    first_lat = math.radians(float(first.get("lat_deg", 0.0)))
    first_lon = math.radians(float(first.get("lon_deg", 0.0)))
    second_lat = math.radians(float(second.get("lat_deg", 0.0)))
    second_lon = math.radians(float(second.get("lon_deg", 0.0)))
    delta_lat = second_lat - first_lat
    delta_lon = second_lon - first_lon
    sin_lat = math.sin(delta_lat * 0.5)
    sin_lon = math.sin(delta_lon * 0.5)
    haversine = sin_lat * sin_lat + math.cos(first_lat) * math.cos(second_lat) * sin_lon * sin_lon
    return max(
        0.001,
        radius_km
        * 2.0
        * math.asin(min(1.0, math.sqrt(max(0.0, haversine)))),
    )


def _marine_neighbors(cell: dict[str, Any], cells_by_id: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    neighbors: list[dict[str, Any]] = []
    for neighbor_id_raw in cell.get("neighbors", []):
        neighbor = cells_by_id.get(int(neighbor_id_raw))
        if neighbor is not None and str(neighbor.get("water_body_type", "land")) in MARINE_WATER_TYPES:
            neighbors.append(neighbor)
    return neighbors


def _land_neighbors(cell: dict[str, Any], cells_by_id: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    neighbors: list[dict[str, Any]] = []
    for neighbor_id_raw in cell.get("neighbors", []):
        neighbor = cells_by_id.get(int(neighbor_id_raw))
        if neighbor is not None and not bool(neighbor.get("is_water", False)):
            neighbors.append(neighbor)
    return neighbors


def _is_coastal(cell: dict[str, Any], cells_by_id: dict[int, dict[str, Any]]) -> bool:
    if str(cell.get("water_body_type", "land")) in MARINE_WATER_TYPES:
        return True
    return bool(_marine_neighbors(cell, cells_by_id))


def _mountain_pass_index(cell: dict[str, Any], cells_by_id: dict[int, dict[str, Any]]) -> float:
    if bool(cell.get("is_water", False)):
        return 0.0
    elevation = float(cell.get("elevation_m", 0.0))
    neighbors = _land_neighbors(cell, cells_by_id)
    if not neighbors:
        return 0.0
    neighbor_elevations = [float(neighbor.get("elevation_m", 0.0)) for neighbor in neighbors]
    high_neighbors = [value for value in neighbor_elevations if value >= 900.0]
    local_landform = str(cell.get("landform", ""))
    mountain_context = max(
        _clamp((max(neighbor_elevations, default=elevation) - 700.0) / 2300.0),
        _clamp(float(cell.get("boundary_convergent", 0.0)) * 1.9),
        0.68 if local_landform in MOUNTAIN_LANDFORMS else 0.0,
    )
    if mountain_context <= 0.05 and not high_neighbors:
        return 0.0
    high_mean = sum(high_neighbors) / len(high_neighbors) if high_neighbors else max(neighbor_elevations)
    saddle_gap = _clamp((high_mean - elevation + 260.0) / 1150.0)
    pass_elevation = _clamp((elevation - 180.0) / 1700.0)
    relief_window = _clamp((max(neighbor_elevations) - min(neighbor_elevations)) / 1900.0)
    ice_penalty = _clamp(float(cell.get("ice_thickness_m", 0.0)) / 280.0)
    return _clamp(
        mountain_context * 0.38
        + saddle_gap * 0.32
        + relief_window * 0.18
        + pass_elevation * 0.12
        - ice_penalty * 0.30
    )


def _river_valley_route_index(cell: dict[str, Any], max_flow_accumulation: float) -> float:
    if bool(cell.get("is_water", False)) and str(cell.get("water_body_type", "land")) in MARINE_WATER_TYPES:
        return 0.0
    landform = str(cell.get("landform", ""))
    flow = _clamp(float(cell.get("flow_accumulation", 0.0)) / max(1.0, max_flow_accumulation))
    runoff = _clamp(float(cell.get("runoff_mm_y", 0.0)) / 850.0)
    river = 0.34 if bool(cell.get("is_river", False)) else 0.0
    valley = 0.28 if landform in RIVER_VALLEY_LANDFORMS else 0.0
    low_relief = _clamp(1.0 - abs(float(cell.get("elevation_m", 0.0))) / 1900.0)
    navigability = _clamp(float(cell.get("river_navigability_index", 0.0)))
    ice_penalty = _clamp(float(cell.get("ice_thickness_m", 0.0)) / 260.0)
    return _clamp(flow * 0.22 + runoff * 0.14 + river + valley + low_relief * 0.12 + navigability * 0.16 - ice_penalty * 0.24)


def _coastal_route_index(cell: dict[str, Any], cells_by_id: dict[int, dict[str, Any]]) -> float:
    water_body = str(cell.get("water_body_type", "land"))
    marine_neighbors = _marine_neighbors(cell, cells_by_id)
    if water_body in MARINE_WATER_TYPES:
        land_contact = _clamp(len(_land_neighbors(cell, cells_by_id)) / 4.0)
        shelf = 0.25 if water_body in {"continental_shelf", "inland_sea"} else 0.10
        navigability = _clamp(float(cell.get("coastal_navigability_index", 0.0)))
        chokepoint = _clamp(float(cell.get("transport_chokepoint_index", 0.0)))
        depth_access = _clamp(1.0 - float(cell.get("water_depth_m", 0.0)) / 700.0)
        return _clamp(shelf + land_contact * 0.22 + navigability * 0.30 + chokepoint * 0.18 + depth_access * 0.15)
    if not marine_neighbors:
        return 0.0
    marine_contact = _clamp(len(marine_neighbors) / 3.0)
    low_relief = _clamp(1.0 - abs(float(cell.get("elevation_m", 0.0))) / 1200.0)
    harbor = _clamp(float(cell.get("harbor_suitability_index", 0.0)))
    port = _clamp(float(cell.get("port_suitability_index", 0.0)))
    navigability = _clamp(float(cell.get("coastal_navigability_index", 0.0)))
    return _clamp(marine_contact * 0.24 + low_relief * 0.18 + harbor * 0.20 + port * 0.18 + navigability * 0.20)


def _oasis_route_index(cell: dict[str, Any], oasis_settlement_cell_ids: set[int]) -> float:
    if bool(cell.get("is_water", False)):
        return 0.0
    biome = str(cell.get("biome", ""))
    aridity = _clamp(float(cell.get("seasonal_aridity_index", 0.0)))
    arid_context = max(aridity, 0.72 if biome in DESERT_BIOMES else 0.0)
    if arid_context < 0.45 and int(cell.get("id", -1)) not in oasis_settlement_cell_ids:
        return 0.0
    water_access = max(
        0.85 if bool(cell.get("is_river", False)) else 0.0,
        0.70 if bool(cell.get("is_lake", False)) else 0.0,
        _clamp(float(cell.get("runoff_mm_y", 0.0)) / 220.0),
        _clamp(float(cell.get("groundwater_recharge_mm_y", 0.0)) / 180.0),
        _clamp(float(cell.get("aquifer_productivity_index", 0.0))),
        _clamp(float(cell.get("soil_moisture_index", 0.0))),
    )
    fertility = _clamp(float(cell.get("fertility", 0.0)))
    settlement = 0.25 if int(cell.get("id", -1)) in oasis_settlement_cell_ids else 0.0
    return _clamp(arid_context * 0.32 + water_access * 0.43 + fertility * 0.12 + settlement - _clamp(float(cell.get("ice_thickness_m", 0.0)) / 200.0))


def _feature_values(cell: dict[str, Any]) -> dict[str, float]:
    return {
        "mountain_pass_corridor": float(cell.get("mountain_pass_route_index", 0.0)),
        "river_valley_corridor": float(cell.get("river_valley_route_index", 0.0)),
        "coastal_corridor": float(cell.get("coastal_route_index", 0.0)),
        "oasis_corridor": float(cell.get("oasis_route_index", 0.0)),
    }


def _movement_cost(
    current: dict[str, Any],
    neighbor: dict[str, Any],
    route_type: str,
    cells_by_id: dict[int, dict[str, Any]],
    radius_km: float,
) -> float:
    distance = _cell_distance_km(current, neighbor, radius_km)
    route_type = str(route_type)
    water_body = str(neighbor.get("water_body_type", "land"))
    is_water = bool(neighbor.get("is_water", False))
    elevation_delta = abs(float(neighbor.get("elevation_m", 0.0)) - float(current.get("elevation_m", 0.0)))
    slope = _clamp(elevation_delta / 2000.0)
    ice = _clamp(float(neighbor.get("ice_thickness_m", 0.0)) / 320.0)
    aridity = _clamp(float(neighbor.get("seasonal_aridity_index", 0.0)))
    mountain = _clamp((float(neighbor.get("elevation_m", 0.0)) - 1000.0) / 2200.0)
    features = _feature_values(neighbor)

    if route_type == "coastal_sea":
        support = max(features["coastal_corridor"], float(neighbor.get("navigability_index", 0.0)))
        water_penalty = 0.08 if water_body in MARINE_WATER_TYPES else 0.72 if _is_coastal(neighbor, cells_by_id) else 1.80
    elif route_type == "river_corridor":
        support = max(features["river_valley_corridor"], float(neighbor.get("river_navigability_index", 0.0)))
        water_penalty = 1.45 if water_body in MARINE_WATER_TYPES else 0.18 if bool(neighbor.get("is_river", False)) else 0.42
    elif route_type == "mountain_pass":
        support = max(features["mountain_pass_corridor"], features["river_valley_corridor"] * 0.45)
        water_penalty = 1.70 if is_water else 0.20
    else:
        support = max(
            features["river_valley_corridor"] * 0.72,
            features["coastal_corridor"] * 0.62,
            features["oasis_corridor"] * 0.72,
            features["mountain_pass_corridor"] * 0.46,
        )
        water_penalty = 1.65 if water_body in MARINE_WATER_TYPES else 0.20 if bool(neighbor.get("is_river", False)) else 0.34

    terrain = 0.64 + slope * 0.42 + ice * 0.55 + aridity * 0.18 + mountain * 0.20 + water_penalty - support * 0.50
    return distance * max(0.12, terrain)


def _shortest_route_path(
    start_cell_id: int,
    end_cell_id: int,
    route_type: str,
    cells_by_id: dict[int, dict[str, Any]],
    radius_km: float,
) -> list[int]:
    if start_cell_id == end_cell_id and start_cell_id in cells_by_id:
        return [start_cell_id]
    if start_cell_id not in cells_by_id or end_cell_id not in cells_by_id:
        return []
    queue: list[tuple[float, int]] = [(0.0, start_cell_id)]
    best_cost: dict[int, float] = {start_cell_id: 0.0}
    previous: dict[int, int] = {}
    visited: set[int] = set()
    while queue:
        cost, cell_id = heapq.heappop(queue)
        if cell_id in visited:
            continue
        visited.add(cell_id)
        if cell_id == end_cell_id:
            break
        cell = cells_by_id.get(cell_id)
        if cell is None:
            continue
        for neighbor_id_raw in cell.get("neighbors", []):
            neighbor_id = int(neighbor_id_raw)
            neighbor = cells_by_id.get(neighbor_id)
            if neighbor is None:
                continue
            next_cost = cost + _movement_cost(
                cell,
                neighbor,
                route_type,
                cells_by_id,
                radius_km,
            )
            if next_cost < best_cost.get(neighbor_id, float("inf")):
                best_cost[neighbor_id] = next_cost
                previous[neighbor_id] = cell_id
                heapq.heappush(queue, (next_cost, neighbor_id))
    if end_cell_id not in best_cost:
        return []
    path = [end_cell_id]
    while path[-1] != start_cell_id:
        parent = previous.get(path[-1])
        if parent is None:
            return []
        path.append(parent)
    path.reverse()
    return path


def _path_length_km(
    path_cell_ids: list[int],
    cells_by_id: dict[int, dict[str, Any]],
    radius_km: float,
) -> float:
    length = 0.0
    for first_id, second_id in zip(path_cell_ids, path_cell_ids[1:]):
        first = cells_by_id.get(first_id)
        second = cells_by_id.get(second_id)
        if first is not None and second is not None:
            length += _cell_distance_km(first, second, radius_km)
    return length


def _primary_corridor_type(path_cells: list[dict[str, Any]], route_type: str) -> str:
    counts = {
        "mountain_pass_corridor": sum(1 for cell in path_cells if float(cell.get("mountain_pass_route_index", 0.0)) >= MOUNTAIN_PASS_THRESHOLD),
        "river_valley_corridor": sum(1 for cell in path_cells if float(cell.get("river_valley_route_index", 0.0)) >= RIVER_VALLEY_THRESHOLD),
        "coastal_corridor": sum(1 for cell in path_cells if float(cell.get("coastal_route_index", 0.0)) >= COASTAL_ROUTE_THRESHOLD),
        "oasis_corridor": sum(1 for cell in path_cells if float(cell.get("oasis_route_index", 0.0)) >= OASIS_ROUTE_THRESHOLD),
    }
    if route_type == "coastal_sea" and counts["coastal_corridor"] > 0:
        return "coastal_corridor"
    if route_type == "river_corridor" and counts["river_valley_corridor"] > 0:
        return "river_valley_corridor"
    if route_type == "mountain_pass" and counts["mountain_pass_corridor"] > 0:
        return "mountain_pass_corridor"
    best_type, best_count = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0]
    return best_type if best_count > 0 else "overland_corridor"


def _route_record(
    corridor_id: int,
    route: dict[str, Any],
    settlements_by_id: dict[int, dict[str, Any]],
    path_cell_ids: list[int],
    cells_by_id: dict[int, dict[str, Any]],
    radius_km: float,
) -> dict[str, Any]:
    path_cells = [cells_by_id[cell_id] for cell_id in path_cell_ids if cell_id in cells_by_id]
    route_type = str(route.get("type", "overland"))
    corridor_type = _primary_corridor_type(path_cells, route_type)
    path_length = _path_length_km(path_cell_ids, cells_by_id, radius_km)
    straight_distance = max(0.001, float(route.get("distance_km", 0.0)))
    mountain_count = sum(1 for cell in path_cells if float(cell.get("mountain_pass_route_index", 0.0)) >= MOUNTAIN_PASS_THRESHOLD)
    river_count = sum(1 for cell in path_cells if float(cell.get("river_valley_route_index", 0.0)) >= RIVER_VALLEY_THRESHOLD)
    coastal_count = sum(1 for cell in path_cells if float(cell.get("coastal_route_index", 0.0)) >= COASTAL_ROUTE_THRESHOLD)
    oasis_count = sum(1 for cell in path_cells if float(cell.get("oasis_route_index", 0.0)) >= OASIS_ROUTE_THRESHOLD)
    named_feature_cell_count = sum(
        1
        for cell in path_cells
        if (
            float(cell.get("mountain_pass_route_index", 0.0)) >= MOUNTAIN_PASS_THRESHOLD
            or float(cell.get("river_valley_route_index", 0.0)) >= RIVER_VALLEY_THRESHOLD
            or float(cell.get("coastal_route_index", 0.0)) >= COASTAL_ROUTE_THRESHOLD
            or float(cell.get("oasis_route_index", 0.0)) >= OASIS_ROUTE_THRESHOLD
        )
    )
    route_ids = [int(route.get("id", -1))]
    source = settlements_by_id.get(int(route.get("from", -1)), {})
    target = settlements_by_id.get(int(route.get("to", -1)), {})
    region_ids = sorted(
        {
            int(source.get("region_id", -1)),
            int(target.get("region_id", -1)),
        }
        - {-1}
    )
    navigable_waterway_ids = sorted(
        {
            int(cell.get("navigable_waterway_id", -1))
            for cell in path_cells
            if int(cell.get("navigable_waterway_id", -1)) >= 0
        }
    )
    port_site_ids = sorted(
        {
            int(cell.get("port_site_id", -1))
            for cell in path_cells
            if int(cell.get("port_site_id", -1)) >= 0
        }
    )
    corridor_values = [float(cell.get("route_corridor_index", 0.0)) for cell in path_cells]
    mountain_values = [float(cell.get("mountain_pass_route_index", 0.0)) for cell in path_cells]
    river_values = [float(cell.get("river_valley_route_index", 0.0)) for cell in path_cells]
    coastal_values = [float(cell.get("coastal_route_index", 0.0)) for cell in path_cells]
    oasis_values = [float(cell.get("oasis_route_index", 0.0)) for cell in path_cells]
    return {
        "id": corridor_id,
        "route_id": int(route.get("id", -1)),
        "route_type": route_type,
        "corridor_type": corridor_type,
        "from_settlement_id": int(route.get("from", -1)),
        "to_settlement_id": int(route.get("to", -1)),
        "start_cell_id": int(source.get("cell_id", -1)),
        "end_cell_id": int(target.get("cell_id", -1)),
        "cell_count": len(path_cell_ids),
        "cell_ids": path_cell_ids,
        "path_length_km": round(path_length, 6),
        "straight_distance_km": round(straight_distance, 6),
        "detour_ratio": round(path_length / straight_distance, 6),
        "mean_route_corridor_index": round(sum(corridor_values) / len(corridor_values), 6) if corridor_values else 0.0,
        "max_route_corridor_index": round(max(corridor_values), 6) if corridor_values else 0.0,
        "mean_mountain_pass_route_index": round(sum(mountain_values) / len(mountain_values), 6) if mountain_values else 0.0,
        "mean_river_valley_route_index": round(sum(river_values) / len(river_values), 6) if river_values else 0.0,
        "mean_coastal_route_index": round(sum(coastal_values) / len(coastal_values), 6) if coastal_values else 0.0,
        "mean_oasis_route_index": round(sum(oasis_values) / len(oasis_values), 6) if oasis_values else 0.0,
        "mountain_pass_cell_count": mountain_count,
        "river_valley_cell_count": river_count,
        "coastal_cell_count": coastal_count,
        "oasis_cell_count": oasis_count,
        "named_feature_cell_count": named_feature_cell_count,
        "settlement_ids": sorted({int(route.get("from", -1)), int(route.get("to", -1))} - {-1}),
        "region_ids": region_ids,
        "route_ids": route_ids,
        "navigable_waterway_ids": navigable_waterway_ids,
        "port_site_ids": port_site_ids,
    }


def enrich_world_with_route_corridors(world: dict[str, Any]) -> dict[str, Any]:
    cells = world.get("cells", [])
    routes = world.get("routes", [])
    settlements = world.get("settlements", [])
    if not isinstance(cells, list) or not cells:
        return world
    if not isinstance(routes, list):
        routes = []
    if not isinstance(settlements, list):
        settlements = []
    radius_km = planet_radius_km(world)
    cells_by_id = {int(cell.get("id", -1)): cell for cell in cells if isinstance(cell, dict)}
    settlements_by_id = {
        int(settlement.get("id", -1)): settlement
        for settlement in settlements
        if isinstance(settlement, dict) and int(settlement.get("id", -1)) >= 0
    }
    max_flow_accumulation = max((max(0.0, float(cell.get("flow_accumulation", 0.0))) for cell in cells), default=1.0)
    oasis_settlement_cell_ids = {
        int(settlement.get("cell_id", -1))
        for settlement in settlements
        if isinstance(settlement, dict)
        and str(settlement.get("type", "")) == "oasis"
        and int(settlement.get("cell_id", -1)) >= 0
    }

    for cell in cells:
        cell["mountain_pass_route_index"] = round(_mountain_pass_index(cell, cells_by_id), 6)
        cell["river_valley_route_index"] = round(_river_valley_route_index(cell, max_flow_accumulation), 6)
        cell["coastal_route_index"] = round(_coastal_route_index(cell, cells_by_id), 6)
        cell["oasis_route_index"] = round(_oasis_route_index(cell, oasis_settlement_cell_ids), 6)
        cell["route_corridor_index"] = 0.0
        cell["route_corridor_type"] = "none"
        cell["route_corridor_id"] = -1

    records: list[dict[str, Any]] = []
    route_by_id = {
        int(route.get("id", -1)): route for route in routes if isinstance(route, dict) and int(route.get("id", -1)) >= 0
    }
    for route_id in sorted(route_by_id):
        route = route_by_id[route_id]
        source = settlements_by_id.get(int(route.get("from", -1)))
        target = settlements_by_id.get(int(route.get("to", -1)))
        if source is None or target is None:
            route["route_corridor_id"] = -1
            route["route_corridor_type"] = "none"
            route["path_cell_ids"] = []
            continue
        start_cell_id = int(source.get("cell_id", -1))
        end_cell_id = int(target.get("cell_id", -1))
        path_cell_ids = _shortest_route_path(
            start_cell_id,
            end_cell_id,
            str(route.get("type", "overland")),
            cells_by_id,
            radius_km,
        )
        if not path_cell_ids:
            route["route_corridor_id"] = -1
            route["route_corridor_type"] = "none"
            route["path_cell_ids"] = []
            continue
        corridor_id = len(records)
        path_cells = [cells_by_id[cell_id] for cell_id in path_cell_ids if cell_id in cells_by_id]
        corridor_type = _primary_corridor_type(path_cells, str(route.get("type", "overland")))
        for cell in path_cells:
            feature_support = max(_feature_values(cell).values())
            membership = _clamp(0.35 + feature_support * 0.65)
            if membership >= float(cell.get("route_corridor_index", 0.0)):
                cell["route_corridor_index"] = round(membership, 6)
                cell["route_corridor_type"] = corridor_type
                cell["route_corridor_id"] = corridor_id
        route["route_corridor_id"] = corridor_id
        route["route_corridor_type"] = corridor_type
        route["path_cell_ids"] = path_cell_ids
        records.append(
            _route_record(
                corridor_id,
                route,
                settlements_by_id,
                path_cell_ids,
                cells_by_id,
                radius_km,
            )
        )

    corridor_cell_ids = {int(cell.get("id", -1)) for cell in cells if int(cell.get("route_corridor_id", -1)) >= 0}
    type_counts = Counter(str(record.get("corridor_type", "overland_corridor")) for record in records)
    summary = world.setdefault("summary", {})
    cell_count = len(cells)
    world["route_corridor_model"] = {
        "model_type": ROUTE_CORRIDOR_MODEL,
        "source_navigability_model": "causal_channel_hydraulic_coastal_navigability_v1",
        "source_port_model": "causal_navigability_coastal_port_site_selection_v1",
        "source_aquifer_model": "finite_recharge_causal_aquifer_resources_v1",
        "domain": "all_cells_with_one_path_per_valid_route",
        "mountain_pass_model": "neighbor_saddle_convergence_landform_relief_elevation_ice_v1",
        "river_valley_model": "flow_runoff_river_landform_relief_navigability_ice_v1",
        "coastal_model": "marine_or_coastal_contact_navigability_harbor_port_depth_relief_v1",
        "oasis_model": "aridity_water_recharge_aquifer_soil_fertility_settlement_ice_v1",
        "movement_cost_model": "directed_distance_terrain_water_route_type_feature_support_v1",
        "path_model": "strict_improvement_dijkstra_cost_then_cell_id_heap_v1",
        "corridor_classification_model": "route_type_preference_then_feature_count_lexical_tie_v1",
        "cell_assignment_model": "maximum_membership_with_later_route_winning_equal_ties_v1",
        "record_order": "ascending_route_id_for_valid_endpoints_and_paths",
        "planet_radius_km": radius_km,
        "feature_threshold": MOUNTAIN_PASS_THRESHOLD,
        "threshold_semantics": "serialized_feature_indices",
        "deterministic": True,
        "route_count": len(route_by_id),
        "corridor_count": len(records),
        "model_limitation": "diagnostic_static_corridors_without_capacity_congestion_seasonality_construction_cost_network_equilibrium_or_multimodal_scheduling",
    }
    summary["route_corridor_model"] = ROUTE_CORRIDOR_MODEL
    summary.update(
        {
            "route_corridor_count": len(records),
            "route_corridor_cell_count": len(corridor_cell_ids),
            "route_corridor_total_path_length_km": round(sum(float(record.get("path_length_km", 0.0)) for record in records), 6),
            "mean_route_corridor_index": round(sum(float(cell.get("route_corridor_index", 0.0)) for cell in cells) / cell_count, 6),
            "mean_mountain_pass_route_index": round(sum(float(cell.get("mountain_pass_route_index", 0.0)) for cell in cells) / cell_count, 6),
            "mean_river_valley_route_index": round(sum(float(cell.get("river_valley_route_index", 0.0)) for cell in cells) / cell_count, 6),
            "mean_coastal_route_index": round(sum(float(cell.get("coastal_route_index", 0.0)) for cell in cells) / cell_count, 6),
            "mean_oasis_route_index": round(sum(float(cell.get("oasis_route_index", 0.0)) for cell in cells) / cell_count, 6),
            "route_feature_coverage_index": round(
                sum(1 for record in records if int(record.get("named_feature_cell_count", 0)) > 0) / len(records),
                6,
            )
            if records
            else 1.0,
            "mountain_pass_route_corridor_count": type_counts.get("mountain_pass_corridor", 0),
            "river_valley_route_corridor_count": type_counts.get("river_valley_corridor", 0),
            "coastal_route_corridor_count": type_counts.get("coastal_corridor", 0),
            "oasis_route_corridor_count": type_counts.get("oasis_corridor", 0),
            "route_corridor_type_counts": dict(sorted(type_counts.items())),
        }
    )
    world["route_corridors"] = records
    return world
