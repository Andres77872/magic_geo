from __future__ import annotations

from collections import Counter, deque
from typing import Any


MARINE_WATER_TYPES = {"ocean", "continental_shelf", "inland_sea"}
NAVIGABILITY_MODEL = "causal_channel_hydraulic_coastal_navigability_v1"
NAVIGABLE_THRESHOLD = 0.52
HIGH_HARBOR_THRESHOLD = 0.62
TRANSPORT_CHOKEPOINT_THRESHOLD = 0.55
LOWLAND_FORMS = {"delta", "floodplain", "river_valley", "coastal_plain", "lacustrine_basin"}


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _primary_key(counter: Counter[str], fallback: str) -> str:
    if not counter:
        return fallback
    return sorted(counter.items(), key=lambda item: (-item[1], item[0]))[0][0]


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


def _river_navigability(cell: dict[str, Any], max_flow_accumulation: float) -> float:
    if bool(cell.get("is_water", False)) or not bool(cell.get("is_river", False)):
        return 0.0
    flow = _clamp(float(cell.get("flow_accumulation", 0.0)) / max(1.0, max_flow_accumulation))
    runoff = _clamp(float(cell.get("runoff_mm_y", 0.0)) / 900.0)
    lowland = 0.22 if str(cell.get("landform", "")) in LOWLAND_FORMS else 0.0
    low_relief = _clamp(1.0 - abs(float(cell.get("elevation_m", 0.0))) / 1800.0)
    sediment_load = _clamp(float(cell.get("sediment_routing_load_m", 0.0)) / 2.0)
    channel_depth = _clamp(float(cell.get("river_channel_depth_m", 0.0)) / 3.0)
    channel_width = _clamp(float(cell.get("river_channel_width_m", 0.0)) / 80.0)
    hydraulic = _clamp(float(cell.get("hydraulic_navigability_index", 0.0)))
    ice_penalty = _clamp(float(cell.get("ice_thickness_m", 0.0)) / 350.0)
    aridity_penalty = _clamp(float(cell.get("seasonal_aridity_index", 0.0))) * 0.08
    return _clamp(
        flow * 0.24
        + runoff * 0.13
        + low_relief * 0.12
        + lowland
        + sediment_load * 0.06
        + channel_depth * 0.14
        + channel_width * 0.08
        + hydraulic * 0.17
        - ice_penalty * 0.24
        - aridity_penalty
    )


def _coastal_navigability(
    cell: dict[str, Any],
    cells_by_id: dict[int, dict[str, Any]],
    chokepoint_by_cell: dict[int, dict[str, Any]],
) -> float:
    water_body = str(cell.get("water_body_type", "land"))
    if water_body in MARINE_WATER_TYPES:
        depth = _clamp(float(cell.get("water_depth_m", 0.0)) / 180.0)
        shelf = 0.24 if water_body in {"continental_shelf", "inland_sea"} else 0.08
        land_contact = _clamp(len(_land_neighbors(cell, cells_by_id)) / 4.0)
        chokepoint = _clamp(float(chokepoint_by_cell.get(int(cell.get("id", -1)), {}).get("constriction_index", 0.0)))
        return _clamp(depth * 0.30 + shelf + land_contact * 0.20 + chokepoint * 0.26)

    marine_neighbors = _marine_neighbors(cell, cells_by_id)
    if not marine_neighbors:
        return 0.0
    neighbor_score = _clamp(len(marine_neighbors) / 4.0)
    protected = 0.20 if any(str(neighbor.get("water_body_type", "")) in {"continental_shelf", "inland_sea"} for neighbor in marine_neighbors) else 0.0
    river_mouth = 0.22 if bool(cell.get("is_river", False)) or str(cell.get("landform", "")) == "delta" else 0.0
    low_relief = _clamp(1.0 - abs(float(cell.get("elevation_m", 0.0))) / 1200.0)
    return _clamp(neighbor_score * 0.32 + protected + river_mouth + low_relief * 0.18)


def _harbor_suitability(
    cell: dict[str, Any],
    cells_by_id: dict[int, dict[str, Any]],
    coastal_navigability: float,
) -> float:
    if bool(cell.get("is_water", False)):
        return 0.0
    marine_neighbors = _marine_neighbors(cell, cells_by_id)
    if not marine_neighbors:
        return 0.0
    protected = 0.24 if any(str(neighbor.get("water_body_type", "")) in {"continental_shelf", "inland_sea"} for neighbor in marine_neighbors) else 0.0
    river_mouth = 0.18 if bool(cell.get("is_river", False)) or str(cell.get("landform", "")) == "delta" else 0.0
    low_relief = _clamp(1.0 - abs(float(cell.get("elevation_m", 0.0))) / 900.0)
    settlement = _clamp(float(cell.get("settlement_score", 0.0)))
    ice_penalty = _clamp(float(cell.get("ice_thickness_m", 0.0)) / 300.0)
    return _clamp(
        coastal_navigability * 0.32
        + protected
        + river_mouth
        + low_relief * 0.14
        + settlement * 0.18
        - ice_penalty * 0.22
    )


def _transport_chokepoint(
    cell: dict[str, Any],
    coastal_navigability: float,
    chokepoint_by_cell: dict[int, dict[str, Any]],
) -> float:
    chokepoint = chokepoint_by_cell.get(int(cell.get("id", -1)))
    if chokepoint is None:
        return 0.0
    constriction = _clamp(float(chokepoint.get("constriction_index", 0.0)))
    return _clamp(constriction * 0.72 + coastal_navigability * 0.28)


def _navigability_class(river: float, coastal: float, harbor: float, chokepoint: float) -> str:
    if chokepoint >= TRANSPORT_CHOKEPOINT_THRESHOLD:
        return "transport_chokepoint"
    if harbor >= HIGH_HARBOR_THRESHOLD:
        return "harbor"
    if river >= NAVIGABLE_THRESHOLD and coastal >= NAVIGABLE_THRESHOLD:
        return "river_mouth"
    if river >= NAVIGABLE_THRESHOLD:
        return "river_corridor"
    if coastal >= NAVIGABLE_THRESHOLD:
        return "coastal_corridor"
    return "non_navigable"


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
            for neighbor_id_raw in current.get("neighbors", []):
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
            if settlement_id >= 0 and route_id >= 0:
                by_settlement.setdefault(settlement_id, set()).add(route_id)
    return by_settlement


def _waterway_type(component: list[dict[str, Any]]) -> str:
    classes = Counter(str(cell.get("navigability_class", "non_navigable")) for cell in component)
    if classes.get("transport_chokepoint", 0) > 0:
        return "transport_chokepoint"
    if classes.get("river_mouth", 0) > 0:
        return "river_mouth_corridor"
    if classes.get("harbor", 0) > 0:
        return "harbor_cluster"
    if classes.get("river_corridor", 0) > 0:
        return "river_corridor"
    return "coastal_corridor"


def _waterway_records(
    components: list[list[dict[str, Any]]],
    settlements_by_cell: dict[int, list[int]],
    routes_by_settlement: dict[int, set[int]],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for component in components:
        waterway_id = len(records)
        for cell in component:
            cell["navigable_waterway_id"] = waterway_id
        cell_ids = [int(cell.get("id", -1)) for cell in component]
        settlement_ids = sorted({sid for cell_id in cell_ids for sid in settlements_by_cell.get(cell_id, []) if sid >= 0})
        route_ids = sorted({rid for sid in settlement_ids for rid in routes_by_settlement.get(sid, set()) if rid >= 0})
        marine_region_ids = sorted(
            {
                int(cell.get("marine_region_id", -1))
                for cell in component
                if int(cell.get("marine_region_id", -1)) >= 0
            }
        )
        watershed_ids = sorted({int(cell.get("basin_id", -1)) for cell in component if int(cell.get("basin_id", -1)) >= 0})
        area_sum = sum(max(0.0, float(cell.get("area_km2", 0.0))) for cell in component)
        navigability_sum = sum(float(cell.get("navigability_index", 0.0)) for cell in component)
        river_sum = sum(float(cell.get("river_navigability_index", 0.0)) for cell in component)
        coastal_sum = sum(float(cell.get("coastal_navigability_index", 0.0)) for cell in component)
        harbor_max = max((float(cell.get("harbor_suitability_index", 0.0)) for cell in component), default=0.0)
        chokepoint_count = sum(1 for cell in component if float(cell.get("transport_chokepoint_index", 0.0)) >= TRANSPORT_CHOKEPOINT_THRESHOLD)
        records.append(
            {
                "id": waterway_id,
                "waterway_type": _waterway_type(component),
                "cell_count": len(component),
                "cell_ids": cell_ids,
                "area_km2": round(area_sum, 6),
                "mean_navigability_index": round(navigability_sum / len(component), 6),
                "mean_river_navigability_index": round(river_sum / len(component), 6),
                "mean_coastal_navigability_index": round(coastal_sum / len(component), 6),
                "max_harbor_suitability_index": round(harbor_max, 6),
                "transport_chokepoint_cell_count": chokepoint_count,
                "settlement_ids": settlement_ids,
                "route_ids": route_ids,
                "marine_region_ids": marine_region_ids,
                "watershed_ids": watershed_ids,
            }
        )
    return records


def enrich_world_with_navigability_diagnostics(world: dict[str, Any]) -> dict[str, Any]:
    cells = world.get("cells", [])
    if not isinstance(cells, list) or not cells:
        return world
    cells_by_id = {int(cell.get("id", -1)): cell for cell in cells if isinstance(cell, dict)}
    chokepoints = world.get("marine_chokepoints", [])
    chokepoint_by_cell = {
        int(chokepoint.get("cell_id", -1)): chokepoint
        for chokepoint in chokepoints
        if isinstance(chokepoint, dict) and int(chokepoint.get("cell_id", -1)) >= 0
    } if isinstance(chokepoints, list) else {}
    max_flow_accumulation = max((max(0.0, float(cell.get("flow_accumulation", 0.0))) for cell in cells), default=1.0)

    candidate_ids: set[int] = set()
    river_sum = 0.0
    coastal_sum = 0.0
    harbor_sum = 0.0
    chokepoint_sum = 0.0
    navigability_sum = 0.0
    class_counts: Counter[str] = Counter()
    high_harbor_count = 0
    transport_chokepoint_count = 0
    for cell in cells:
        river = _river_navigability(cell, max_flow_accumulation)
        coastal = _coastal_navigability(cell, cells_by_id, chokepoint_by_cell)
        harbor = _harbor_suitability(cell, cells_by_id, coastal)
        chokepoint = _transport_chokepoint(cell, coastal, chokepoint_by_cell)
        navigability = max(river, coastal, harbor, chokepoint)
        nav_class = _navigability_class(river, coastal, harbor, chokepoint)
        cell["river_navigability_index"] = round(river, 6)
        cell["coastal_navigability_index"] = round(coastal, 6)
        cell["harbor_suitability_index"] = round(harbor, 6)
        cell["transport_chokepoint_index"] = round(chokepoint, 6)
        cell["navigability_index"] = round(navigability, 6)
        cell["navigability_class"] = nav_class
        cell["navigable_waterway_id"] = -1
        cell_id = int(cell.get("id", -1))
        if navigability >= NAVIGABLE_THRESHOLD:
            candidate_ids.add(cell_id)
        if harbor >= HIGH_HARBOR_THRESHOLD:
            high_harbor_count += 1
        if chokepoint >= TRANSPORT_CHOKEPOINT_THRESHOLD:
            transport_chokepoint_count += 1
        river_sum += river
        coastal_sum += coastal
        harbor_sum += harbor
        chokepoint_sum += chokepoint
        navigability_sum += navigability
        class_counts[nav_class] += 1

    records = _waterway_records(
        _connected_components(candidate_ids, cells_by_id),
        _settlements_by_cell(world),
        _routes_by_settlement(world),
    )

    summary = world.setdefault("summary", {})
    count = len(cells)
    world["navigability_model"] = {
        "model_type": NAVIGABILITY_MODEL,
        "source_channel_model": "causal_flow_sediment_wetland_baseflow_channel_morphology_v1",
        "source_hydraulics_model": "manning_blended_diagnostic_river_hydraulics_v1",
        "domain": "all_cells",
        "flow_normalization_model": "global_max_flow_accumulation_v1",
        "river_model": "flow_runoff_lowland_relief_sediment_channel_hydraulic_ice_aridity_v1",
        "coastal_model": "marine_depth_shelf_land_contact_constriction_or_coastal_land_context_v1",
        "harbor_model": "coastal_protection_river_mouth_relief_settlement_ice_v1",
        "transport_chokepoint_model": "marine_constriction_and_coastal_navigability_v1",
        "overall_model": "maximum_component_navigability_v1",
        "classification_model": "chokepoint_harbor_river_mouth_river_coastal_priority_v1",
        "system_grouping_model": "undirected_mesh_connected_raw_threshold_components_v1",
        "link_model": "component_cell_settlement_route_marine_region_watershed_links_v1",
        "navigable_threshold": NAVIGABLE_THRESHOLD,
        "high_harbor_threshold": HIGH_HARBOR_THRESHOLD,
        "transport_chokepoint_threshold": TRANSPORT_CHOKEPOINT_THRESHOLD,
        "threshold_semantics": "unrounded_pre_serialization_values",
        "deterministic": True,
        "candidate_cell_count": len(candidate_ids),
        "waterway_count": len(records),
        "model_limitation": "diagnostic_transport_suitability_without_vessel_classes_seasonal_discharge_bathymetric_channels_or_route_cost_optimization",
    }
    summary["navigability_model"] = NAVIGABILITY_MODEL
    summary["navigable_cell_count"] = len(candidate_ids)
    summary["navigable_waterway_count"] = len(records)
    summary["navigable_waterway_total_area_km2"] = round(sum(record["area_km2"] for record in records), 6)
    summary["mean_navigability_index"] = round(navigability_sum / count, 6)
    summary["mean_river_navigability_index"] = round(river_sum / count, 6)
    summary["mean_coastal_navigability_index"] = round(coastal_sum / count, 6)
    summary["mean_harbor_suitability_index"] = round(harbor_sum / count, 6)
    summary["mean_transport_chokepoint_index"] = round(chokepoint_sum / count, 6)
    summary["high_harbor_suitability_cell_count"] = high_harbor_count
    summary["transport_chokepoint_cell_count"] = transport_chokepoint_count
    summary["navigability_class_counts"] = dict(sorted(class_counts.items()))
    world["navigable_waterways"] = records
    return world
