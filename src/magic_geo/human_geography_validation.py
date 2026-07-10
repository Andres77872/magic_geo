from __future__ import annotations

from collections import Counter, defaultdict, deque
from typing import Any


LAND_USE_ZONE_MODEL = "causal_soil_climate_resource_connected_land_use_zones_v1"
NATURAL_FRONTIER_MODEL = "causal_border_terrain_connected_natural_frontiers_v1"
WORLDBUILDING_REALISM_MODEL = "causal_upstream_evidence_worldbuilding_realism_checks_v1"

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

NATURAL_FRONTIER_THRESHOLD = 0.45
MOUNTAIN_LANDFORMS = {"mountain", "mountain_range", "volcanic_arc", "highland", "ridge"}
DESERT_BIOMES = {"hot_desert", "cold_desert", "desert", "semi_arid_desert"}
DENSE_FOREST_BIOMES = {"tropical_rainforest", "tropical_seasonal_forest", "temperate_rainforest"}
RIVER_LANDFORMS = {"delta", "floodplain", "river_valley", "alluvial_fan"}
SPECIFIC_FRONTIER_TYPES = ("mountain", "river", "desert", "coastal", "ice", "dense_forest", "wetland")

MARINE_WATER_TYPES = {"ocean", "continental_shelf", "inland_sea"}
WATER_ACCESS_TYPES = MARINE_WATER_TYPES | {"fresh_lake", "saline_basin"}


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


def _natural_frontier_model() -> dict[str, Any]:
    return {
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


def _frontier_cell_type(cell: dict[str, Any]) -> str:
    landform = str(cell.get("landform", ""))
    biome = str(cell.get("biome", ""))
    water_body = str(cell.get("water_body_type", "land"))
    if float(cell.get("ice_thickness_m", 0.0)) > 40.0 or str(cell.get("permafrost_class", "")) in {"continuous", "ice_sheet"}:
        return "ice"
    if bool(cell.get("is_river", False)) or landform in RIVER_LANDFORMS:
        return "river"
    if water_body in MARINE_WATER_TYPES:
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


def _frontier_cell_score(cell: dict[str, Any]) -> float:
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
    coast = 0.54 if water_body in MARINE_WATER_TYPES else 0.0
    desert = _clamp(float(cell.get("seasonal_aridity_index", 0.0)))
    if biome in DESERT_BIOMES:
        desert = max(desert, 0.66)
    forest = 0.58 if biome in DENSE_FOREST_BIOMES else 0.0
    wetland = 0.52 if biome == "wetland" or landform == "wetland" else 0.0
    return _clamp(max(mountain, ice, river, coast, desert, forest, wetland))


def _pair(region_a: int, region_b: int) -> tuple[int, int]:
    return min(region_a, region_b), max(region_a, region_b)


def _frontier_info(border: dict[str, Any], first: dict[str, Any], second: dict[str, Any]) -> dict[str, Any]:
    border_type = str(border.get("type", "open_lowland"))
    if border_type == "open_lowland":
        type_counts = Counter([_frontier_cell_type(first), _frontier_cell_type(second)])
        type_counts.pop("open_lowland", None)
        frontier_type = _primary(type_counts, "terrain_barrier")
    else:
        frontier_type = border_type
    border_score = _clamp(float(border.get("barrier_score", 0.0)))
    local_score = (_frontier_cell_score(first) + _frontier_cell_score(second)) / 2.0
    natural_floor = NATURAL_FRONTIER_THRESHOLD if border_type != "open_lowland" else 0.0
    frontier_index = _clamp(max(border_score * 0.72 + local_score * 0.28, border_score, natural_floor))
    return {
        "id": int(border.get("id", -1)),
        "cell_a": int(border.get("cell_a", -1)),
        "cell_b": int(border.get("cell_b", -1)),
        "region_a": int(border.get("region_a", -1)),
        "region_b": int(border.get("region_b", -1)),
        "type": frontier_type,
        "barrier_score": border_score,
        "frontier_index": frontier_index,
        "length_km": max(0.0, float(border.get("length_km", 0.0))),
    }


def _natural_frontier_replay_valid(payload: dict[str, Any]) -> bool:
    cells = payload.get("cells", [])
    borders = payload.get("borders", [])
    summary = payload.get("summary", {})
    if not isinstance(cells, list) or not cells or not isinstance(borders, list) or not isinstance(summary, dict):
        return False
    if payload.get("natural_frontier_model") != _natural_frontier_model() or summary.get("natural_frontier_model") != NATURAL_FRONTIER_MODEL:
        return False
    cells_by_id = {int(cell.get("id", -1)): cell for cell in cells if isinstance(cell, dict)}
    if len(cells_by_id) != len(cells):
        return False
    expected_cell_index = {cell_id: 0.0 for cell_id in cells_by_id}
    expected_cell_type = {cell_id: "none" for cell_id in cells_by_id}
    border_infos: list[dict[str, Any]] = []
    candidate_ids: set[int] = set()
    for border in borders:
        if not isinstance(border, dict):
            continue
        border_type = str(border.get("type", "open_lowland"))
        if border_type == "open_lowland" and float(border.get("barrier_score", 0.0)) < NATURAL_FRONTIER_THRESHOLD:
            continue
        first = cells_by_id.get(int(border.get("cell_a", -1)))
        second = cells_by_id.get(int(border.get("cell_b", -1)))
        if first is None or second is None:
            continue
        info = _frontier_info(border, first, second)
        border_infos.append(info)
        for cell in (first, second):
            cell_id = int(cell.get("id", -1))
            candidate_ids.add(cell_id)
            if float(info["frontier_index"]) > expected_cell_index[cell_id]:
                expected_cell_index[cell_id] = round(float(info["frontier_index"]), 6)
                expected_cell_type[cell_id] = str(info["type"])

    components = _components(candidate_ids, cells_by_id)
    expected_frontier_id = {cell_id: index for index, component in enumerate(components) for cell_id in component}
    for cell_id, cell in cells_by_id.items():
        if (
            float(cell.get("natural_frontier_index", -1.0)) != expected_cell_index[cell_id]
            or str(cell.get("natural_frontier_type", "")) != expected_cell_type[cell_id]
            or int(cell.get("natural_frontier_id", -2)) != expected_frontier_id.get(cell_id, -1)
        ):
            return False

    settlements = payload.get("settlements", [])
    routes = payload.get("routes", [])
    waterways = payload.get("navigable_waterways", [])
    if not isinstance(settlements, list) or not isinstance(routes, list) or not isinstance(waterways, list):
        return False
    settlements_by_cell: dict[int, list[int]] = {}
    settlement_by_id: dict[int, dict[str, Any]] = {}
    for settlement in settlements:
        settlement_id = int(settlement.get("id", -1))
        cell_id = int(settlement.get("cell_id", -1))
        settlement_by_id[settlement_id] = settlement
        if settlement_id >= 0 and cell_id >= 0:
            settlements_by_cell.setdefault(cell_id, []).append(settlement_id)
    route_ids_by_pair: dict[tuple[int, int], set[int]] = defaultdict(set)
    for route in routes:
        route_id = int(route.get("id", -1))
        source = settlement_by_id.get(int(route.get("from", -1)))
        target = settlement_by_id.get(int(route.get("to", -1)))
        if route_id < 0 or source is None or target is None:
            continue
        region_a = int(source.get("region_id", -1))
        region_b = int(target.get("region_id", -1))
        if region_a >= 0 and region_b >= 0 and region_a != region_b:
            route_ids_by_pair[_pair(region_a, region_b)].add(route_id)
    waterway_by_cell: dict[int, int] = {}
    for waterway in waterways:
        waterway_id = int(waterway.get("id", -1))
        if waterway_id < 0:
            continue
        for cell_id_raw in waterway.get("cell_ids", []):
            waterway_by_cell[int(cell_id_raw)] = waterway_id

    records: list[dict[str, Any]] = []
    for cell_ids in components:
        member_ids = set(cell_ids)
        component_infos = [
            info for info in border_infos if int(info["cell_a"]) in member_ids or int(info["cell_b"]) in member_ids
        ]
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
                for route_id in route_ids_by_pair.get(_pair(int(info["region_a"]), int(info["region_b"])), set())
            }
        )
        settlement_ids = sorted(
            {settlement_id for cell_id in cell_ids for settlement_id in settlements_by_cell.get(cell_id, []) if settlement_id >= 0}
        )
        waterway_ids = sorted({waterway_by_cell[cell_id] for cell_id in cell_ids if cell_id in waterway_by_cell})
        component_cells = [cells_by_id[cell_id] for cell_id in cell_ids]
        border_count = len(component_infos)
        cell_count = len(component_cells)
        records.append(
            {
                "id": len(records),
                "frontier_type": _primary(Counter(str(info["type"]) for info in component_infos), "terrain_barrier"),
                "cell_count": cell_count,
                "cell_ids": cell_ids,
                "border_segment_count": border_count,
                "border_ids": border_ids,
                "region_ids": region_ids,
                "area_km2": round(sum(max(0.0, float(cell.get("area_km2", 0.0))) for cell in component_cells), 6),
                "total_border_length_km": round(sum(float(info["length_km"]) for info in component_infos), 6),
                "mean_barrier_score": round(sum(float(info["barrier_score"]) for info in component_infos) / border_count, 6)
                if border_count
                else 0.0,
                "mean_frontier_index": round(sum(expected_cell_index[cell_id] for cell_id in cell_ids) / cell_count, 6)
                if cell_count
                else 0.0,
                "dominant_landform": _primary(
                    Counter(str(cell.get("landform", "unknown")) for cell in component_cells),
                    "unknown",
                ),
                "dominant_biome": _primary(
                    Counter(str(cell.get("biome", "unknown")) for cell in component_cells),
                    "unknown",
                ),
                "settlement_ids": settlement_ids,
                "route_ids": route_ids,
                "route_crossing_count": len(route_ids),
                "navigable_waterway_ids": waterway_ids,
            }
        )
    if payload.get("natural_frontiers") != records:
        return False
    type_counts = Counter(str(record.get("frontier_type", "terrain_barrier")) for record in records)
    expected_summary: dict[str, Any] = {
        "natural_frontier_model": NATURAL_FRONTIER_MODEL,
        "natural_frontier_count": len(records),
        "natural_frontier_cell_count": len(candidate_ids),
        "natural_frontier_border_segment_count": sum(int(record["border_segment_count"]) for record in records),
        "natural_frontier_total_area_km2": round(sum(float(record["area_km2"]) for record in records), 6),
        "natural_frontier_total_length_km": round(sum(float(record["total_border_length_km"]) for record in records), 6),
        "mean_natural_frontier_index": round(sum(expected_cell_index.values()) / len(cells), 6),
        "mean_natural_frontier_barrier_score": round(
            sum(float(info["barrier_score"]) for info in border_infos) / len(border_infos),
            6,
        )
        if border_infos
        else 0.0,
        "natural_frontier_type_counts": dict(sorted(type_counts.items())),
    }
    for frontier_type in SPECIFIC_FRONTIER_TYPES:
        expected_summary[f"{frontier_type}_frontier_count"] = int(type_counts.get(frontier_type, 0))
    return all(summary.get(key) == value for key, value in expected_summary.items())


def _worldbuilding_model() -> dict[str, Any]:
    return {
        "model_type": WORLDBUILDING_REALISM_MODEL,
        "deterministic": True,
        "check_order": [
            "large_settlement_water_access",
            "route_barrier_avoidance",
            "political_region_connectivity",
            "natural_border_alignment",
            "resource_geology_dependency",
        ],
        "score_model": "bounded_distance_to_closed_target_interval_v1",
        "targets": {
            "large_settlement_water_access": [0.85, 1.0],
            "route_barrier_avoidance": [0.8, 1.0],
            "political_region_connectivity": [0.55, 1.0],
            "natural_border_alignment": [0.4, 1.0],
            "resource_geology_dependency": [0.85, 1.0],
        },
        "large_settlement_model": "top_max_5_or_ceil_quarter_by_descending_score_v1",
        "water_access_model": "river_lake_water_body_runoff_or_adjacent_marine_v1",
        "water_access_runoff_threshold_mm_y": 120.0,
        "route_friction_model": "cost_div_max_one_distance_v1",
        "route_type_friction_thresholds": {
            "coastal_sea": 0.95,
            "river_corridor": 1.10,
            "mountain_pass": 1.75,
            "default": 1.35,
        },
        "high_cost_route_threshold": 1.55,
        "political_connectivity_model": "capital_reachability_on_internal_settlement_route_graph_v1",
        "connected_region_reachability_threshold": 0.6,
        "natural_border_model": "length_weighted_non_open_or_threshold_barrier_fraction_v1",
        "natural_border_barrier_threshold": 0.45,
        "resource_support_model": "resource_specific_geology_and_physical_context_predicates_v1",
        "model_limitation": "internal_generated_evidence_checks_without_external_historical_geographic_calibration",
    }


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _score_range(value: float, target_min: float, target_max: float) -> float:
    if target_min <= value <= target_max:
        return 1.0
    if value < target_min:
        return _clamp(value / target_min) if target_min > 0.0 else 0.0
    remaining = 1.0 - target_max
    return _clamp((1.0 - value) / remaining) if remaining > 0.0 else 0.0


def _add_check(
    checks: list[dict[str, Any]],
    *,
    name: str,
    question: str,
    metric: str,
    value: float,
    target_min: float,
    target_max: float,
    evidence: dict[str, Any],
) -> None:
    rounded_value = round(_clamp(value), 6)
    checks.append(
        {
            "id": len(checks),
            "domain": "worldbuilding",
            "name": name,
            "question": question,
            "metric": metric,
            "value": rounded_value,
            "target_min": round(_clamp(target_min), 6),
            "target_max": round(_clamp(target_max), 6),
            "score": round(_score_range(rounded_value, target_min, target_max), 6),
            "passed": target_min <= rounded_value <= target_max,
            "evidence": evidence,
        }
    )


def _coastal_land(cell: dict[str, Any], cells_by_id: dict[int, dict[str, Any]]) -> bool:
    return any(
        neighbor is not None and str(neighbor.get("water_body_type", "land")) in MARINE_WATER_TYPES
        for neighbor_id in cell.get("neighbors", [])
        for neighbor in [cells_by_id.get(int(neighbor_id))]
    )


def _water_access(cell: dict[str, Any], cells_by_id: dict[int, dict[str, Any]]) -> bool:
    return (
        bool(cell.get("is_river", False))
        or bool(cell.get("is_lake", False))
        or str(cell.get("water_body_type", "land")) in WATER_ACCESS_TYPES
        or float(cell.get("runoff_mm_y", 0.0)) >= 120.0
        or _coastal_land(cell, cells_by_id)
    )


def _route_threshold(route_type: str) -> float:
    return {"coastal_sea": 0.95, "river_corridor": 1.10, "mountain_pass": 1.75}.get(route_type, 1.35)


def _resource_supported(deposit: dict[str, Any], cell: dict[str, Any]) -> bool:
    resource = str(deposit.get("resource", "none"))
    evidence = deposit.get("formation_evidence", {})
    if not isinstance(evidence, dict):
        evidence = {}
    convergent = float(evidence.get("boundary_convergent", cell.get("boundary_convergent", 0.0)))
    divergent = float(evidence.get("boundary_divergent", cell.get("boundary_divergent", 0.0)))
    crust_age = float(evidence.get("crust_age_ma", cell.get("crust_age_ma", 0.0)))
    sediment = float(evidence.get("sediment_thickness_m", cell.get("sediment_thickness_m", 0.0)))
    flow = float(evidence.get("flow_accumulation", cell.get("flow_accumulation", 0.0)))
    fertility = float(evidence.get("fertility", cell.get("fertility", 0.0)))
    salinity = float(evidence.get("salinity_index", cell.get("soil_salinity_index", 0.0)))
    crust = str(deposit.get("host_crust_type", cell.get("crust_type", "")))
    lithology = str(deposit.get("host_lithology", cell.get("lithology", "")))
    landform = str(deposit.get("landform", cell.get("landform", "")))
    water_body = str(cell.get("water_body_type", "land"))
    if resource == "volcanic_arc_metals":
        return crust == "volcanic_arc" or landform == "volcanic_arc" or convergent >= 0.28
    if resource == "craton_iron_gold":
        return crust == "craton" or crust_age >= 1800.0
    if resource == "sedimentary_fuels":
        return crust == "sedimentary_basin" or lithology in {"shale", "sandstone", "limestone"} or sediment >= 1.0 or "basin" in landform
    if resource == "evaporites":
        return landform == "salt_flat" or salinity >= 0.45 or water_body == "saline_basin"
    if resource == "placer_metals":
        return bool(cell.get("is_river", False)) or flow >= 25.0 or convergent >= 0.16
    if resource == "geothermal":
        return divergent >= 0.30 or convergent >= 0.20 or landform in {"volcanic_arc", "rift_valley"} or crust in {"volcanic_arc", "rift_basin"}
    if resource == "fertile_alluvium":
        return landform in {"floodplain", "delta", "river_valley", "alluvial_fan"} or bool(cell.get("is_river", False)) or fertility >= 0.62
    if resource == "coastal_fisheries":
        return water_body in MARINE_WATER_TYPES
    return float(deposit.get("geologic_confidence_index", 0.0)) >= 0.25


def _worldbuilding_replay_valid(payload: dict[str, Any]) -> bool:
    cells = payload.get("cells", [])
    settlements = payload.get("settlements", [])
    routes = payload.get("routes", [])
    regions = payload.get("political_regions", [])
    borders = payload.get("borders", [])
    deposits = payload.get("resource_deposits", [])
    summary = payload.get("summary", {})
    if not all(isinstance(value, list) for value in (cells, settlements, routes, regions, borders, deposits)) or not isinstance(summary, dict):
        return False
    if not cells or payload.get("worldbuilding_realism_model") != _worldbuilding_model() or summary.get("worldbuilding_realism_model") != WORLDBUILDING_REALISM_MODEL:
        return False
    cells_by_id = {int(cell.get("id", -1)): cell for cell in cells if isinstance(cell, dict)}
    if len(cells_by_id) != len(cells):
        return False
    checks: list[dict[str, Any]] = []

    ranked = sorted(settlements, key=lambda item: float(item.get("score", 0.0)), reverse=True)
    target_count = max(1, min(len(ranked), max(5, (len(ranked) + 3) // 4))) if ranked else 0
    top_settlements = ranked[:target_count]
    water_settlements = [
        settlement
        for settlement in top_settlements
        if _water_access(cells_by_id.get(int(settlement.get("cell_id", -1)), {}), cells_by_id)
    ]
    settlement_water_index = len(water_settlements) / len(top_settlements) if top_settlements else 1.0
    _add_check(
        checks,
        name="large_settlement_water_access",
        question="Do large settlements have water access?",
        metric="fraction_top_settlements_with_water_access",
        value=settlement_water_index,
        target_min=0.85,
        target_max=1.0,
        evidence={
            "top_settlement_count": len(top_settlements),
            "water_accessible_top_settlement_count": len(water_settlements),
            "mean_top_settlement_score": round(_mean([float(item.get("score", 0.0)) for item in top_settlements]), 6),
        },
    )

    route_frictions: list[float] = []
    low_barrier_routes = 0
    high_cost_routes = 0
    for route in routes:
        friction = float(route.get("cost", 0.0)) / max(1.0, float(route.get("distance_km", 0.0)))
        route_frictions.append(friction)
        if friction <= _route_threshold(str(route.get("type", "overland"))):
            low_barrier_routes += 1
        if friction > 1.55:
            high_cost_routes += 1
    route_avoidance_index = low_barrier_routes / len(routes) if routes else 1.0
    _add_check(
        checks,
        name="route_barrier_avoidance",
        question="Do routes avoid expensive terrain barriers?",
        metric="fraction_routes_below_type_specific_barrier_cost",
        value=route_avoidance_index,
        target_min=0.8,
        target_max=1.0,
        evidence={
            "route_count": len(routes),
            "low_barrier_route_count": low_barrier_routes,
            "high_cost_route_count": high_cost_routes,
            "mean_route_friction": round(_mean(route_frictions), 6),
            "max_route_friction": round(max(route_frictions), 6) if route_frictions else 0.0,
        },
    )

    route_graph: dict[int, set[int]] = defaultdict(set)
    for route in routes:
        source = int(route.get("from", -1))
        target = int(route.get("to", -1))
        if source >= 0 and target >= 0:
            route_graph[source].add(target)
            route_graph[target].add(source)
    reachable_sum = 0
    settlement_sum = 0
    region_reachability: list[float] = []
    connected_regions = 0
    for region in regions:
        settlement_ids = {int(value) for value in region.get("settlement_ids", [])}
        if not settlement_ids:
            region_reachability.append(1.0)
            connected_regions += 1
            continue
        capital_id = int(region.get("capital_settlement_id", -1))
        if capital_id not in settlement_ids:
            capital_id = next(iter(settlement_ids))
        seen = {capital_id}
        stack = [capital_id]
        while stack:
            current = stack.pop()
            for neighbor in route_graph.get(current, set()):
                if neighbor in settlement_ids and neighbor not in seen:
                    seen.add(neighbor)
                    stack.append(neighbor)
        reachability = len(seen) / len(settlement_ids)
        region_reachability.append(reachability)
        reachable_sum += len(seen)
        settlement_sum += len(settlement_ids)
        if reachability >= 0.6:
            connected_regions += 1
    political_connectivity_index = reachable_sum / settlement_sum if settlement_sum else 1.0
    _add_check(
        checks,
        name="political_region_connectivity",
        question="Do generated political regions originate around connected settlement networks?",
        metric="fraction_region_settlements_reachable_from_capital_by_internal_routes",
        value=political_connectivity_index,
        target_min=0.55,
        target_max=1.0,
        evidence={
            "political_region_count": len(regions),
            "connected_region_count": connected_regions,
            "region_settlement_count": settlement_sum,
            "capital_reachable_settlement_count": reachable_sum,
            "mean_region_capital_reachability": round(_mean(region_reachability), 6),
        },
    )

    total_border_length = 0.0
    natural_border_length = 0.0
    natural_border_count = 0
    border_barrier_scores: list[float] = []
    for border in borders:
        length = max(0.0, float(border.get("length_km", 0.0)))
        barrier_score = _clamp(float(border.get("barrier_score", 0.0)))
        border_barrier_scores.append(barrier_score)
        total_border_length += length
        if str(border.get("type", "open_lowland")) != "open_lowland" or barrier_score >= 0.45:
            natural_border_length += length
            natural_border_count += 1
    natural_border_index = natural_border_length / total_border_length if total_border_length > 0.0 else 1.0
    _add_check(
        checks,
        name="natural_border_alignment",
        question="Do political borders follow real terrain, water, desert, ice, or coastal barriers?",
        metric="length_weighted_fraction_borders_on_natural_barriers",
        value=natural_border_index,
        target_min=0.4,
        target_max=1.0,
        evidence={
            "border_segment_count": len(borders),
            "natural_border_segment_count": natural_border_count,
            "border_total_length_km": round(total_border_length, 6),
            "natural_border_length_km": round(natural_border_length, 6),
            "mean_border_barrier_score": round(_mean(border_barrier_scores), 6),
        },
    )

    resource_counts: Counter[str] = Counter()
    supported_resource_counts: Counter[str] = Counter()
    supported_deposits = 0
    for deposit in deposits:
        cell = cells_by_id.get(int(deposit.get("cell_id", -1)))
        resource = str(deposit.get("resource", "none"))
        resource_counts[resource] += 1
        if cell is not None and _resource_supported(deposit, cell):
            supported_deposits += 1
            supported_resource_counts[resource] += 1
    resource_geology_index = supported_deposits / len(deposits) if deposits else 1.0
    _add_check(
        checks,
        name="resource_geology_dependency",
        question="Do resources depend on geology and causal physical context?",
        metric="fraction_resource_deposits_with_resource_specific_geologic_support",
        value=resource_geology_index,
        target_min=0.85,
        target_max=1.0,
        evidence={
            "resource_deposit_count": len(deposits),
            "geologically_supported_resource_deposit_count": supported_deposits,
            "resource_counts": dict(sorted(resource_counts.items())),
            "supported_resource_counts": dict(sorted(supported_resource_counts.items())),
        },
    )
    if payload.get("worldbuilding_realism_checks") != checks:
        return False
    pass_count = sum(1 for check in checks if bool(check["passed"]))
    expected_summary = {
        "worldbuilding_realism_model": WORLDBUILDING_REALISM_MODEL,
        "large_settlement_water_access_index": round(settlement_water_index, 6),
        "route_barrier_avoidance_index": round(route_avoidance_index, 6),
        "political_region_connectivity_index": round(political_connectivity_index, 6),
        "natural_border_alignment_index": round(natural_border_index, 6),
        "resource_geology_dependency_index": round(resource_geology_index, 6),
        "worldbuilding_realism_check_count": len(checks),
        "worldbuilding_realism_pass_count": pass_count,
        "worldbuilding_realism_pass_fraction": round(pass_count / len(checks), 6) if checks else 0.0,
        "mean_worldbuilding_realism_score": round(sum(float(check["score"]) for check in checks) / len(checks), 6)
        if checks
        else 0.0,
    }
    return all(summary.get(key) == value for key, value in expected_summary.items())


def validate_human_geography_replay(payload: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if not _land_use_replay_valid(payload):
        failures.append("land use zone model or causal replay invalid")
    if not _natural_frontier_replay_valid(payload):
        failures.append("natural frontier model or causal replay invalid")
    if not _worldbuilding_replay_valid(payload):
        failures.append("worldbuilding realism model or causal replay invalid")
    return failures
