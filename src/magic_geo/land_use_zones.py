from __future__ import annotations

from collections import Counter, deque
from typing import Any


AGRICULTURAL_THRESHOLD = 0.58
MINING_THRESHOLD = 0.52
LAND_USE_ZONE_MODEL = "causal_soil_climate_resource_connected_land_use_zones_v1"
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


def _primary_key(counter: Counter[str], fallback: str) -> str:
    if not counter:
        return fallback
    return sorted(counter.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _agricultural_potential(cell: dict[str, Any]) -> float:
    if bool(cell.get("is_water", False)):
        return 0.0
    fertility = _clamp(float(cell.get("fertility", 0.0)))
    soil_depth = _clamp(float(cell.get("soil_depth_m", 0.0)) / 3.2)
    soil_moisture = _clamp(float(cell.get("soil_moisture_index", 0.0)))
    salinity_penalty = _clamp(float(cell.get("soil_salinity_index", 0.0)))
    erosion_penalty = _clamp(float(cell.get("soil_erodibility_index", 0.0)) * 0.5 + float(cell.get("erosion_rate", 0.0)) / 140.0)
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
    resource = str(cell.get("resource", "none"))
    if resource not in MINING_RESOURCES:
        return 0.0
    cell_id = int(cell.get("id", -1))
    deposit = deposit_by_cell.get(cell_id, {})
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
    settlement_access = _clamp(float(cell.get("settlement_score", 0.0)))
    return _clamp(
        reserve * 0.28
        + viability * 0.24
        + confidence * 0.18
        + accessibility * 0.12
        + geology * 0.10
        + settlement_access * 0.08
        - hazard * 0.12
    )


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
        by_cell.setdefault(int(settlement.get("cell_id", -1)), []).append(int(settlement.get("id", -1)))
    return by_cell


def _routes_by_settlement(world: dict[str, Any]) -> dict[int, set[int]]:
    by_settlement: dict[int, set[int]] = {}
    routes = world.get("routes", [])
    if not isinstance(routes, list):
        return by_settlement
    for route in routes:
        route_id = int(route.get("id", -1))
        for key in ("from", "to"):
            settlement_id = int(route.get(key, -1))
            by_settlement.setdefault(settlement_id, set()).add(route_id)
    return by_settlement


def _zone_records(
    zone_type: str,
    components: list[list[dict[str, Any]]],
    potential_key: str,
    zone_id_key: str,
    settlements_by_cell: dict[int, list[int]],
    routes_by_settlement: dict[int, set[int]],
    deposit_by_cell: dict[int, dict[str, Any]],
) -> list[dict[str, Any]]:
    zones: list[dict[str, Any]] = []
    for component in components:
        zone_id = len(zones)
        for cell in component:
            cell[zone_id_key] = zone_id
        cell_ids = [int(cell.get("id", -1)) for cell in component]
        settlement_ids = sorted({sid for cell_id in cell_ids for sid in settlements_by_cell.get(cell_id, []) if sid >= 0})
        route_ids = sorted({rid for sid in settlement_ids for rid in routes_by_settlement.get(sid, set()) if rid >= 0})
        deposit_ids = sorted(
            {
                int(deposit_by_cell[cell_id].get("id", -1))
                for cell_id in cell_ids
                if cell_id in deposit_by_cell and int(deposit_by_cell[cell_id].get("id", -1)) >= 0
            }
        )
        area_sum = sum(max(0.0, float(cell.get("area_km2", 0.0))) for cell in component)
        potential_sum = sum(float(cell.get(potential_key, 0.0)) for cell in component)
        fertility_sum = sum(_clamp(float(cell.get("fertility", 0.0))) for cell in component)
        resource_counter = Counter(str(cell.get("resource", "none")) for cell in component)
        landform_counter = Counter(str(cell.get("landform", "unknown")) for cell in component)
        biome_counter = Counter(str(cell.get("biome", "unknown")) for cell in component)
        group_count = len(component)
        zones.append(
            {
                "id": zone_id,
                "zone_type": zone_type,
                "cell_count": group_count,
                "cell_ids": cell_ids,
                "area_km2": round(area_sum, 6),
                "mean_potential_index": round(potential_sum / group_count, 6),
                "mean_fertility_index": round(fertility_sum / group_count, 6),
                "dominant_resource": _primary_key(resource_counter, "none"),
                "dominant_landform": _primary_key(landform_counter, "unknown"),
                "dominant_biome": _primary_key(biome_counter, "unknown"),
                "settlement_ids": settlement_ids,
                "route_ids": route_ids,
                "resource_deposit_ids": deposit_ids,
            }
        )
    return zones


def enrich_world_with_land_use_zones(world: dict[str, Any]) -> dict[str, Any]:
    cells = world.get("cells", [])
    if not isinstance(cells, list) or not cells:
        return world

    cells_by_id = {int(cell.get("id", -1)): cell for cell in cells}
    deposits = world.get("resource_deposits", [])
    deposit_by_cell = {
        int(deposit.get("cell_id", -1)): deposit
        for deposit in deposits
        if isinstance(deposit, dict) and int(deposit.get("cell_id", -1)) >= 0
    } if isinstance(deposits, list) else {}
    settlements_by_cell = _settlements_by_cell(world)
    routes_by_settlement = _routes_by_settlement(world)

    agricultural_ids: set[int] = set()
    mining_ids: set[int] = set()
    agricultural_sum = 0.0
    mining_sum = 0.0
    for cell in cells:
        agricultural = _agricultural_potential(cell)
        mining = _mining_potential(cell, deposit_by_cell)
        cell["agricultural_potential_index"] = round(agricultural, 6)
        cell["mining_potential_index"] = round(mining, 6)
        cell["agricultural_zone_id"] = -1
        cell["mining_zone_id"] = -1
        agricultural_sum += agricultural
        mining_sum += mining
        cell_id = int(cell.get("id", -1))
        if agricultural >= AGRICULTURAL_THRESHOLD:
            agricultural_ids.add(cell_id)
        if mining >= MINING_THRESHOLD:
            mining_ids.add(cell_id)

    agricultural_zones = _zone_records(
        "agricultural",
        _connected_components(agricultural_ids, cells_by_id),
        "agricultural_potential_index",
        "agricultural_zone_id",
        settlements_by_cell,
        routes_by_settlement,
        deposit_by_cell,
    )
    mining_zones = _zone_records(
        "mining",
        _connected_components(mining_ids, cells_by_id),
        "mining_potential_index",
        "mining_zone_id",
        settlements_by_cell,
        routes_by_settlement,
        deposit_by_cell,
    )

    summary = world.setdefault("summary", {})
    summary["agricultural_zone_count"] = len(agricultural_zones)
    summary["agricultural_zone_cell_count"] = len(agricultural_ids)
    summary["agricultural_zone_total_area_km2"] = round(
        sum(zone["area_km2"] for zone in agricultural_zones),
        6,
    )
    summary["mean_agricultural_potential_index"] = round(agricultural_sum / len(cells), 6)
    summary["mining_zone_count"] = len(mining_zones)
    summary["mining_zone_cell_count"] = len(mining_ids)
    summary["mining_zone_total_area_km2"] = round(sum(zone["area_km2"] for zone in mining_zones), 6)
    summary["mean_mining_potential_index"] = round(mining_sum / len(cells), 6)
    world["land_use_zone_model"] = {
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
    summary["land_use_zone_model"] = LAND_USE_ZONE_MODEL
    world["agricultural_zones"] = agricultural_zones
    world["mining_zones"] = mining_zones
    return world
