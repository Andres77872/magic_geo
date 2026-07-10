from __future__ import annotations

from collections import Counter, defaultdict, deque
from typing import Any


NATURAL_FRONTIER_THRESHOLD = 0.45
NATURAL_FRONTIER_MODEL = "causal_border_terrain_connected_natural_frontiers_v1"
MOUNTAIN_LANDFORMS = {"mountain", "mountain_range", "volcanic_arc", "highland", "ridge"}
DESERT_BIOMES = {"hot_desert", "cold_desert", "desert", "semi_arid_desert"}
DENSE_FOREST_BIOMES = {"tropical_rainforest", "tropical_seasonal_forest", "temperate_rainforest"}
RIVER_LANDFORMS = {"delta", "floodplain", "river_valley", "alluvial_fan"}
SPECIFIC_FRONTIER_TYPES = ("mountain", "river", "desert", "coastal", "ice", "dense_forest", "wetland")


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _primary_key(counter: Counter[str], fallback: str) -> str:
    if not counter:
        return fallback
    return sorted(counter.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _cell_barrier_type(cell: dict[str, Any]) -> str:
    landform = str(cell.get("landform", ""))
    biome = str(cell.get("biome", ""))
    water_body = str(cell.get("water_body_type", "land"))
    if float(cell.get("ice_thickness_m", 0.0)) > 40.0 or str(cell.get("permafrost_class", "")) in {
        "continuous",
        "ice_sheet",
    }:
        return "ice"
    if bool(cell.get("is_river", False)) or landform in RIVER_LANDFORMS:
        return "river"
    if water_body in {"ocean", "continental_shelf", "inland_sea"}:
        return "coastal"
    if landform in MOUNTAIN_LANDFORMS or abs(float(cell.get("elevation_m", 0.0))) >= 1600.0:
        return "mountain"
    if biome in DESERT_BIOMES or float(cell.get("seasonal_aridity_index", 0.0)) >= 0.72:
        return "desert"
    if biome in DENSE_FOREST_BIOMES:
        return "dense_forest"
    if biome == "wetland" or landform == "wetland":
        return "wetland"
    return "open_lowland"


def _cell_barrier_score(cell: dict[str, Any]) -> float:
    landform = str(cell.get("landform", ""))
    biome = str(cell.get("biome", ""))
    water_body = str(cell.get("water_body_type", "land"))
    mountain = _clamp((abs(float(cell.get("elevation_m", 0.0))) - 700.0) / 2400.0)
    if landform in MOUNTAIN_LANDFORMS:
        mountain = max(mountain, 0.76)
    ice = _clamp(float(cell.get("ice_thickness_m", 0.0)) / 420.0)
    if str(cell.get("permafrost_class", "")) in {"continuous", "ice_sheet"}:
        ice = max(ice, 0.58)
    river = 0.62 if bool(cell.get("is_river", False)) or landform in RIVER_LANDFORMS else 0.0
    coast = 0.54 if water_body in {"ocean", "continental_shelf", "inland_sea"} else 0.0
    desert = _clamp(float(cell.get("seasonal_aridity_index", 0.0)))
    if biome in DESERT_BIOMES:
        desert = max(desert, 0.66)
    forest = 0.58 if biome in DENSE_FOREST_BIOMES else 0.0
    wetland = 0.52 if biome == "wetland" or landform == "wetland" else 0.0
    return _clamp(max(mountain, ice, river, coast, desert, forest, wetland))


def _border_pair_key(region_a: int, region_b: int) -> tuple[int, int]:
    return (min(region_a, region_b), max(region_a, region_b))


def _is_natural_border(border: dict[str, Any]) -> bool:
    return str(border.get("type", "open_lowland")) != "open_lowland" or float(border.get("barrier_score", 0.0)) >= NATURAL_FRONTIER_THRESHOLD


def _frontier_type(border: dict[str, Any], cell_a: dict[str, Any], cell_b: dict[str, Any]) -> str:
    border_type = str(border.get("type", "open_lowland"))
    if border_type != "open_lowland":
        return border_type
    type_counts = Counter([_cell_barrier_type(cell_a), _cell_barrier_type(cell_b)])
    type_counts.pop("open_lowland", None)
    return _primary_key(type_counts, "terrain_barrier")


def _frontier_index(border: dict[str, Any], cell_a: dict[str, Any], cell_b: dict[str, Any]) -> float:
    border_score = _clamp(float(border.get("barrier_score", 0.0)))
    local_score = (_cell_barrier_score(cell_a) + _cell_barrier_score(cell_b)) / 2.0
    natural_floor = NATURAL_FRONTIER_THRESHOLD if str(border.get("type", "open_lowland")) != "open_lowland" else 0.0
    return _clamp(max(border_score * 0.72 + local_score * 0.28, border_score, natural_floor))


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
            neighbors = current.get("neighbors", [])
            if not isinstance(neighbors, list):
                continue
            for neighbor_id_raw in neighbors:
                neighbor_id = int(neighbor_id_raw)
                if neighbor_id not in remaining:
                    continue
                remaining.remove(neighbor_id)
                queue.append(neighbor_id)
                component_ids.append(neighbor_id)
        components.append([cells_by_id[cell_id] for cell_id in sorted(component_ids)])
    return components


def _settlements_by_cell(world: dict[str, Any]) -> dict[int, list[int]]:
    by_cell: dict[int, list[int]] = {}
    settlements = world.get("settlements", [])
    if not isinstance(settlements, list):
        return by_cell
    for settlement in settlements:
        settlement_id = int(settlement.get("id", -1))
        cell_id = int(settlement.get("cell_id", -1))
        if settlement_id >= 0 and cell_id >= 0:
            by_cell.setdefault(cell_id, []).append(settlement_id)
    return by_cell


def _route_ids_by_region_pair(world: dict[str, Any]) -> dict[tuple[int, int], set[int]]:
    settlements = world.get("settlements", [])
    routes = world.get("routes", [])
    if not isinstance(settlements, list) or not isinstance(routes, list):
        return {}
    settlement_by_id = {int(settlement.get("id", -1)): settlement for settlement in settlements if isinstance(settlement, dict)}
    by_pair: dict[tuple[int, int], set[int]] = defaultdict(set)
    for route in routes:
        route_id = int(route.get("id", -1))
        source = settlement_by_id.get(int(route.get("from", -1)))
        target = settlement_by_id.get(int(route.get("to", -1)))
        if route_id < 0 or source is None or target is None:
            continue
        region_a = int(source.get("region_id", -1))
        region_b = int(target.get("region_id", -1))
        if region_a >= 0 and region_b >= 0 and region_a != region_b:
            by_pair[_border_pair_key(region_a, region_b)].add(route_id)
    return by_pair


def _waterway_ids_by_cell(world: dict[str, Any]) -> dict[int, int]:
    by_cell: dict[int, int] = {}
    waterways = world.get("navigable_waterways", [])
    if not isinstance(waterways, list):
        return by_cell
    for waterway in waterways:
        waterway_id = int(waterway.get("id", -1))
        if waterway_id < 0:
            continue
        for cell_id_raw in waterway.get("cell_ids", []):
            by_cell[int(cell_id_raw)] = waterway_id
    return by_cell


def enrich_world_with_natural_frontiers(world: dict[str, Any]) -> dict[str, Any]:
    cells = world.get("cells", [])
    if not isinstance(cells, list) or not cells:
        return world
    cells_by_id = {int(cell.get("id", -1)): cell for cell in cells if isinstance(cell, dict)}
    borders = world.get("borders", [])
    if not isinstance(borders, list):
        borders = []

    for cell in cells:
        cell["natural_frontier_index"] = 0.0
        cell["natural_frontier_type"] = "none"
        cell["natural_frontier_id"] = -1

    border_infos: list[dict[str, Any]] = []
    candidate_ids: set[int] = set()
    for border in borders:
        if not isinstance(border, dict) or not _is_natural_border(border):
            continue
        cell_a = cells_by_id.get(int(border.get("cell_a", -1)))
        cell_b = cells_by_id.get(int(border.get("cell_b", -1)))
        if cell_a is None or cell_b is None:
            continue
        frontier_type = _frontier_type(border, cell_a, cell_b)
        frontier_index = _frontier_index(border, cell_a, cell_b)
        info = {
            "id": int(border.get("id", -1)),
            "cell_a": int(border.get("cell_a", -1)),
            "cell_b": int(border.get("cell_b", -1)),
            "region_a": int(border.get("region_a", -1)),
            "region_b": int(border.get("region_b", -1)),
            "type": frontier_type,
            "barrier_score": _clamp(float(border.get("barrier_score", 0.0))),
            "frontier_index": frontier_index,
            "length_km": max(0.0, float(border.get("length_km", 0.0))),
        }
        border_infos.append(info)
        for cell in (cell_a, cell_b):
            cell_id = int(cell.get("id", -1))
            candidate_ids.add(cell_id)
            if frontier_index > float(cell.get("natural_frontier_index", 0.0)):
                cell["natural_frontier_index"] = round(frontier_index, 6)
                cell["natural_frontier_type"] = frontier_type

    settlements_by_cell = _settlements_by_cell(world)
    route_ids_by_pair = _route_ids_by_region_pair(world)
    waterway_ids_by_cell = _waterway_ids_by_cell(world)
    records: list[dict[str, Any]] = []
    for component in _connected_components(candidate_ids, cells_by_id):
        frontier_id = len(records)
        for cell in component:
            cell["natural_frontier_id"] = frontier_id
        member_ids = {int(cell.get("id", -1)) for cell in component}
        component_infos = [
            info for info in border_infos if int(info["cell_a"]) in member_ids or int(info["cell_b"]) in member_ids
        ]
        cell_ids = sorted(member_ids)
        border_ids = sorted(int(info["id"]) for info in component_infos if int(info["id"]) >= 0)
        region_ids = sorted(
            {
                int(info[key])
                for info in component_infos
                for key in ("region_a", "region_b")
                if int(info[key]) >= 0
            }
        )
        route_ids = sorted(
            {
                route_id
                for info in component_infos
                for route_id in route_ids_by_pair.get(_border_pair_key(int(info["region_a"]), int(info["region_b"])), set())
            }
        )
        settlement_ids = sorted({sid for cell_id in cell_ids for sid in settlements_by_cell.get(cell_id, []) if sid >= 0})
        waterway_ids = sorted({waterway_ids_by_cell[cell_id] for cell_id in cell_ids if cell_id in waterway_ids_by_cell})
        area_sum = sum(max(0.0, float(cell.get("area_km2", 0.0))) for cell in component)
        length_sum = sum(float(info["length_km"]) for info in component_infos)
        barrier_sum = sum(float(info["barrier_score"]) for info in component_infos)
        frontier_sum = sum(float(cell.get("natural_frontier_index", 0.0)) for cell in component)
        type_counter = Counter(str(info["type"]) for info in component_infos)
        landform_counter = Counter(str(cell.get("landform", "unknown")) for cell in component)
        biome_counter = Counter(str(cell.get("biome", "unknown")) for cell in component)
        border_count = len(component_infos)
        cell_count = len(component)
        records.append(
            {
                "id": frontier_id,
                "frontier_type": _primary_key(type_counter, "terrain_barrier"),
                "cell_count": cell_count,
                "cell_ids": cell_ids,
                "border_segment_count": border_count,
                "border_ids": border_ids,
                "region_ids": region_ids,
                "area_km2": round(area_sum, 6),
                "total_border_length_km": round(length_sum, 6),
                "mean_barrier_score": round(barrier_sum / border_count, 6) if border_count else 0.0,
                "mean_frontier_index": round(frontier_sum / cell_count, 6) if cell_count else 0.0,
                "dominant_landform": _primary_key(landform_counter, "unknown"),
                "dominant_biome": _primary_key(biome_counter, "unknown"),
                "settlement_ids": settlement_ids,
                "route_ids": route_ids,
                "route_crossing_count": len(route_ids),
                "navigable_waterway_ids": waterway_ids,
            }
        )

    type_counts = Counter(str(record.get("frontier_type", "terrain_barrier")) for record in records)
    total_area = sum(float(record.get("area_km2", 0.0)) for record in records)
    total_length = sum(float(record.get("total_border_length_km", 0.0)) for record in records)
    total_border_segments = sum(int(record.get("border_segment_count", 0)) for record in records)
    natural_frontier_sum = sum(float(cell.get("natural_frontier_index", 0.0)) for cell in cells)
    mean_barrier = sum(float(info["barrier_score"]) for info in border_infos) / len(border_infos) if border_infos else 0.0

    summary = world.setdefault("summary", {})
    summary["natural_frontier_count"] = len(records)
    summary["natural_frontier_cell_count"] = len(candidate_ids)
    summary["natural_frontier_border_segment_count"] = total_border_segments
    summary["natural_frontier_total_area_km2"] = round(total_area, 6)
    summary["natural_frontier_total_length_km"] = round(total_length, 6)
    summary["mean_natural_frontier_index"] = round(natural_frontier_sum / len(cells), 6)
    summary["mean_natural_frontier_barrier_score"] = round(mean_barrier, 6)
    summary["natural_frontier_type_counts"] = dict(sorted(type_counts.items()))
    for frontier_type in SPECIFIC_FRONTIER_TYPES:
        summary[f"{frontier_type}_frontier_count"] = int(type_counts.get(frontier_type, 0))
    world["natural_frontier_model"] = {
        "model_type": NATURAL_FRONTIER_MODEL,
        "deterministic": True,
        "natural_border_threshold": NATURAL_FRONTIER_THRESHOLD,
        "candidate_model": "non_open_border_or_threshold_barrier_score_endpoints_v1",
        "cell_barrier_type_model": "ice_river_coastal_mountain_desert_dense_forest_wetland_open_lowland_priority_v1",
        "cell_barrier_score_model": "maximum_mountain_ice_river_coastal_desert_forest_wetland_signal_v1",
        "cell_barrier_parameters": {
            "mountain_base_elevation_m": 700.0,
            "mountain_elevation_scale_m": 2400.0,
            "mountain_landform_floor": 0.76,
            "mountain_type_elevation_m": 1600.0,
            "ice_thickness_scale_m": 420.0,
            "ice_type_thickness_m": 40.0,
            "permafrost_ice_floor": 0.58,
            "river_score": 0.62,
            "coastal_score": 0.54,
            "desert_biome_floor": 0.66,
            "desert_type_aridity_threshold": 0.72,
            "dense_forest_score": 0.58,
            "wetland_score": 0.52,
        },
        "frontier_index_model": "max_weighted_border_local_border_and_hard_type_floor_v1",
        "frontier_index_parameters": {
            "border_weight": 0.72,
            "local_weight": 0.28,
            "hard_type_floor": NATURAL_FRONTIER_THRESHOLD,
        },
        "cell_assignment_model": "maximum_frontier_index_strict_improvement_in_border_order_v1",
        "component_model": "candidate_induced_mesh_components_min_cell_breadth_first_v1",
        "record_order": "components_by_minimum_cell_id_v1",
        "dominant_field_model": "count_then_lexicographic_order_v1",
        "record_link_model": "touching_border_region_pair_route_member_settlement_and_waterway_links_v1",
        "model_limitation": "diagnostic_border_endpoint_components_without_exact_native_edge_polygons_boundary_negotiation_or_historical_change",
    }
    summary["natural_frontier_model"] = NATURAL_FRONTIER_MODEL
    world["natural_frontiers"] = records
    return world
