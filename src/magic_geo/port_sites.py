from __future__ import annotations

from collections import Counter
from typing import Any


MARINE_WATER_TYPES = {"ocean", "continental_shelf", "inland_sea"}
PORT_SITE_MODEL = "causal_navigability_coastal_port_site_selection_v1"
PORT_SITE_THRESHOLD = 0.58
PROTECTED_BAY_THRESHOLD = 0.55
RIVER_MOUTH_THRESHOLD = 0.50
STRAIT_ACCESS_THRESHOLD = 0.55


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _marine_neighbors(cell: dict[str, Any], cells_by_id: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    neighbors: list[dict[str, Any]] = []
    for neighbor_id_raw in cell.get("neighbors", []):
        neighbor = cells_by_id.get(int(neighbor_id_raw))
        if neighbor is not None and str(neighbor.get("water_body_type", "land")) in MARINE_WATER_TYPES:
            neighbors.append(neighbor)
    return neighbors


def _land_neighbor_fraction(cell: dict[str, Any], cells_by_id: dict[int, dict[str, Any]]) -> float:
    neighbor_ids = cell.get("neighbors", [])
    if not isinstance(neighbor_ids, list) or not neighbor_ids:
        return 0.0
    land_count = 0
    valid_count = 0
    for neighbor_id_raw in neighbor_ids:
        neighbor = cells_by_id.get(int(neighbor_id_raw))
        if neighbor is None:
            continue
        valid_count += 1
        if not bool(neighbor.get("is_water", False)):
            land_count += 1
    return land_count / valid_count if valid_count else 0.0


def _protected_bay_index(cell: dict[str, Any], marine_neighbors: list[dict[str, Any]], cells_by_id: dict[int, dict[str, Any]]) -> float:
    if bool(cell.get("is_water", False)) or not marine_neighbors:
        return 0.0
    marine_contact = _clamp(len(marine_neighbors) / 3.0)
    protected_water = sum(
        1 for neighbor in marine_neighbors if str(neighbor.get("water_body_type", "")) in {"continental_shelf", "inland_sea"}
    ) / len(marine_neighbors)
    enclosure = sum(_land_neighbor_fraction(neighbor, cells_by_id) for neighbor in marine_neighbors) / len(marine_neighbors)
    shallow = sum(_clamp(1.0 - float(neighbor.get("water_depth_m", 0.0)) / 260.0) for neighbor in marine_neighbors) / len(
        marine_neighbors
    )
    harbor = _clamp(float(cell.get("harbor_suitability_index", 0.0)))
    return _clamp(marine_contact * 0.20 + protected_water * 0.25 + enclosure * 0.25 + shallow * 0.16 + harbor * 0.14)


def _river_mouth_index(cell: dict[str, Any], marine_neighbors: list[dict[str, Any]], max_flow_accumulation: float) -> float:
    if bool(cell.get("is_water", False)) or not marine_neighbors:
        return 0.0
    landform = str(cell.get("landform", ""))
    if not bool(cell.get("is_river", False)) and landform not in {"delta", "floodplain", "river_valley"}:
        return 0.0
    flow = _clamp(float(cell.get("flow_accumulation", 0.0)) / max(1.0, max_flow_accumulation))
    runoff = _clamp(float(cell.get("runoff_mm_y", 0.0)) / 900.0)
    delta_bonus = 0.26 if landform == "delta" else 0.12 if landform in {"floodplain", "river_valley"} else 0.0
    harbor = _clamp(float(cell.get("harbor_suitability_index", 0.0)))
    return _clamp(0.28 + flow * 0.22 + runoff * 0.14 + delta_bonus + harbor * 0.10)


def _strait_access_index(
    cell: dict[str, Any],
    marine_neighbors: list[dict[str, Any]],
    marine_chokepoint_by_id: dict[int, dict[str, Any]],
) -> float:
    if bool(cell.get("is_water", False)) or not marine_neighbors:
        return 0.0
    best_constriction = 0.0
    for neighbor in marine_neighbors:
        chokepoint_id = int(neighbor.get("marine_chokepoint_id", -1))
        chokepoint = marine_chokepoint_by_id.get(chokepoint_id)
        if chokepoint is None:
            continue
        constriction = _clamp(float(chokepoint.get("constriction_index", 0.0)))
        if str(chokepoint.get("type", "")) == "strait":
            constriction = max(constriction, 0.60)
        best_constriction = max(best_constriction, constriction)
    coastal = _clamp(float(cell.get("coastal_navigability_index", 0.0)))
    return _clamp(best_constriction * 0.76 + coastal * 0.24)


def _port_suitability(
    cell: dict[str, Any],
    protected_bay: float,
    river_mouth: float,
    strait_access: float,
) -> float:
    if bool(cell.get("is_water", False)):
        return 0.0
    harbor = _clamp(float(cell.get("harbor_suitability_index", 0.0)))
    coastal = _clamp(float(cell.get("coastal_navigability_index", 0.0)))
    settlement = _clamp(float(cell.get("settlement_score", 0.0)))
    climate = _clamp((float(cell.get("temperature_c", 0.0)) + 8.0) / 30.0)
    ice_penalty = _clamp(float(cell.get("ice_thickness_m", 0.0)) / 220.0)
    relief_penalty = _clamp((abs(float(cell.get("elevation_m", 0.0))) - 1200.0) / 1800.0)
    base = max(harbor, protected_bay, river_mouth, strait_access)
    return _clamp(
        base * 0.40
        + protected_bay * 0.16
        + river_mouth * 0.14
        + strait_access * 0.12
        + coastal * 0.06
        + settlement * 0.06
        + climate * 0.06
        - ice_penalty * 0.32
        - relief_penalty * 0.08
    )


def _site_type(protected_bay: float, river_mouth: float, strait_access: float, harbor: float, suitability: float) -> str:
    if strait_access >= STRAIT_ACCESS_THRESHOLD:
        return "strait_port"
    if river_mouth >= RIVER_MOUTH_THRESHOLD:
        return "river_mouth_port"
    if protected_bay >= PROTECTED_BAY_THRESHOLD:
        return "protected_bay_port"
    if harbor >= 0.62:
        return "harbor_port"
    if suitability >= PORT_SITE_THRESHOLD:
        return "coastal_port"
    return "none"


def _settlements_by_cell(world: dict[str, Any]) -> dict[int, list[dict[str, Any]]]:
    by_cell: dict[int, list[dict[str, Any]]] = {}
    settlements = world.get("settlements", [])
    if not isinstance(settlements, list):
        return by_cell
    for settlement in settlements:
        if not isinstance(settlement, dict):
            continue
        cell_id = int(settlement.get("cell_id", -1))
        if cell_id >= 0:
            by_cell.setdefault(cell_id, []).append(settlement)
    return by_cell


def _routes_by_settlement(world: dict[str, Any]) -> dict[int, set[int]]:
    by_settlement: dict[int, set[int]] = {}
    routes = world.get("routes", [])
    if not isinstance(routes, list):
        return by_settlement
    for route in routes:
        if not isinstance(route, dict):
            continue
        route_id = int(route.get("id", -1))
        if route_id < 0:
            continue
        for key in ("from", "to"):
            settlement_id = int(route.get(key, -1))
            if settlement_id >= 0:
                by_settlement.setdefault(settlement_id, set()).add(route_id)
    return by_settlement


def _waterway_ids_near_cell(cell: dict[str, Any], cells_by_id: dict[int, dict[str, Any]]) -> list[int]:
    waterway_ids = {int(cell.get("navigable_waterway_id", -1))}
    for neighbor_id_raw in cell.get("neighbors", []):
        neighbor = cells_by_id.get(int(neighbor_id_raw))
        if neighbor is not None:
            waterway_ids.add(int(neighbor.get("navigable_waterway_id", -1)))
    return sorted(waterway_id for waterway_id in waterway_ids if waterway_id >= 0)


def enrich_world_with_port_sites(world: dict[str, Any]) -> dict[str, Any]:
    cells = world.get("cells", [])
    if not isinstance(cells, list) or not cells:
        return world
    cells_by_id = {int(cell.get("id", -1)): cell for cell in cells if isinstance(cell, dict)}
    marine_chokepoints = world.get("marine_chokepoints", [])
    marine_chokepoint_by_id = {
        int(chokepoint.get("id", -1)): chokepoint
        for chokepoint in marine_chokepoints
        if isinstance(chokepoint, dict) and int(chokepoint.get("id", -1)) >= 0
    } if isinstance(marine_chokepoints, list) else {}
    settlements_by_cell = _settlements_by_cell(world)
    routes_by_settlement = _routes_by_settlement(world)
    max_flow_accumulation = max((max(0.0, float(cell.get("flow_accumulation", 0.0))) for cell in cells), default=1.0)

    port_settlement_cell_ids = {
        cell_id
        for cell_id, settlements in settlements_by_cell.items()
        if any(str(settlement.get("type", "")) == "port" for settlement in settlements)
    }
    records: list[dict[str, Any]] = []
    candidate_ids: set[int] = set()
    protected_sum = 0.0
    river_mouth_sum = 0.0
    strait_sum = 0.0
    suitability_sum = 0.0

    for cell in cells:
        marine_neighbors = _marine_neighbors(cell, cells_by_id)
        protected_bay = _protected_bay_index(cell, marine_neighbors, cells_by_id)
        river_mouth = _river_mouth_index(cell, marine_neighbors, max_flow_accumulation)
        strait_access = _strait_access_index(cell, marine_neighbors, marine_chokepoint_by_id)
        suitability = _port_suitability(cell, protected_bay, river_mouth, strait_access)
        harbor = _clamp(float(cell.get("harbor_suitability_index", 0.0)))
        site_type = _site_type(protected_bay, river_mouth, strait_access, harbor, suitability)
        cell["protected_bay_index"] = round(protected_bay, 6)
        cell["river_mouth_port_index"] = round(river_mouth, 6)
        cell["strait_access_index"] = round(strait_access, 6)
        cell["port_suitability_index"] = round(suitability, 6)
        cell["port_site_id"] = -1
        cell_id = int(cell.get("id", -1))
        severe_ice = float(cell.get("ice_thickness_m", 0.0)) >= 80.0 or str(cell.get("biome", "")) == "ice_cap"
        selected = not bool(cell.get("is_water", False)) and (
            (suitability >= PORT_SITE_THRESHOLD and not severe_ice) or cell_id in port_settlement_cell_ids
        )
        cell["port_site_type"] = site_type if selected and site_type != "none" else "none"
        if selected:
            candidate_ids.add(cell_id)
        protected_sum += protected_bay
        river_mouth_sum += river_mouth
        strait_sum += strait_access
        suitability_sum += suitability

    for cell_id in sorted(candidate_ids):
        cell = cells_by_id[cell_id]
        site_id = len(records)
        cell["port_site_id"] = site_id
        if str(cell.get("port_site_type", "none")) == "none":
            cell["port_site_type"] = "port_settlement"
        settlements = settlements_by_cell.get(cell_id, [])
        settlement_ids = sorted(int(settlement.get("id", -1)) for settlement in settlements if int(settlement.get("id", -1)) >= 0)
        port_settlement_ids = sorted(
            int(settlement.get("id", -1))
            for settlement in settlements
            if str(settlement.get("type", "")) == "port" and int(settlement.get("id", -1)) >= 0
        )
        route_ids = sorted({route_id for settlement_id in settlement_ids for route_id in routes_by_settlement.get(settlement_id, set())})
        marine_neighbors = _marine_neighbors(cell, cells_by_id)
        marine_region_ids = sorted(
            {
                int(neighbor.get("marine_region_id", -1))
                for neighbor in marine_neighbors
                if int(neighbor.get("marine_region_id", -1)) >= 0
            }
        )
        marine_chokepoint_ids = sorted(
            {
                int(neighbor.get("marine_chokepoint_id", -1))
                for neighbor in marine_neighbors
                if int(neighbor.get("marine_chokepoint_id", -1)) >= 0
            }
        )
        severe_ice = float(cell.get("ice_thickness_m", 0.0)) >= 80.0 or str(cell.get("biome", "")) == "ice_cap"
        records.append(
            {
                "id": site_id,
                "cell_id": cell_id,
                "site_type": str(cell.get("port_site_type", "none")),
                "area_km2": round(max(0.0, float(cell.get("area_km2", 0.0))), 6),
                "latitude_deg": round(float(cell.get("lat_deg", 0.0)), 6),
                "longitude_deg": round(float(cell.get("lon_deg", 0.0)), 6),
                "port_suitability_index": round(float(cell.get("port_suitability_index", 0.0)), 6),
                "protected_bay_index": round(float(cell.get("protected_bay_index", 0.0)), 6),
                "river_mouth_port_index": round(float(cell.get("river_mouth_port_index", 0.0)), 6),
                "strait_access_index": round(float(cell.get("strait_access_index", 0.0)), 6),
                "harbor_suitability_index": round(harbor := float(cell.get("harbor_suitability_index", 0.0)), 6),
                "navigability_index": round(float(cell.get("navigability_index", 0.0)), 6),
                "settlement_ids": settlement_ids,
                "port_settlement_ids": port_settlement_ids,
                "route_ids": route_ids,
                "marine_region_ids": marine_region_ids,
                "marine_chokepoint_ids": marine_chokepoint_ids,
                "navigable_waterway_ids": _waterway_ids_near_cell(cell, cells_by_id),
                "landform": str(cell.get("landform", "unknown")),
                "biome": str(cell.get("biome", "unknown")),
                "water_body_type": str(cell.get("water_body_type", "land")),
                "is_river": bool(cell.get("is_river", False)),
                "selected_by_port_settlement": bool(port_settlement_ids),
                "selected_by_suitability": (
                    harbor >= 0.62 or float(cell.get("port_suitability_index", 0.0)) >= PORT_SITE_THRESHOLD
                )
                and not severe_ice,
            }
        )

    type_counts = Counter(str(record.get("site_type", "unknown")) for record in records)
    summary = world.setdefault("summary", {})
    count = len(cells)
    world["port_site_model"] = {
        "model_type": PORT_SITE_MODEL,
        "source_navigability_model": "causal_channel_hydraulic_coastal_navigability_v1",
        "domain": "all_cells_with_land_only_selection",
        "protected_bay_model": "marine_contact_protected_water_enclosure_depth_harbor_v1",
        "river_mouth_model": "river_landform_flow_runoff_delta_harbor_v1",
        "strait_access_model": "adjacent_marine_chokepoint_constriction_and_coastal_access_v1",
        "suitability_model": "harbor_bay_river_strait_coastal_settlement_climate_ice_relief_v1",
        "classification_model": "strait_river_mouth_protected_bay_harbor_coastal_priority_v1",
        "selection_model": "raw_suitability_without_severe_ice_or_port_settlement_override_v1",
        "record_order": "ascending_candidate_cell_id",
        "link_model": "cell_settlement_route_marine_region_chokepoint_nearby_waterway_links_v1",
        "port_site_threshold": PORT_SITE_THRESHOLD,
        "protected_bay_threshold": PROTECTED_BAY_THRESHOLD,
        "river_mouth_threshold": RIVER_MOUTH_THRESHOLD,
        "strait_access_threshold": STRAIT_ACCESS_THRESHOLD,
        "threshold_semantics": "unrounded_pre_serialization_values_except_record_flags_use_serialized_fields",
        "deterministic": True,
        "candidate_cell_count": len(candidate_ids),
        "site_count": len(records),
        "model_limitation": "diagnostic_port_suitability_without_harbor_bathymetry_tides_waves_sedimentation_engineering_or_economic_optimization",
    }
    summary["port_site_model"] = PORT_SITE_MODEL
    summary["port_site_count"] = len(records)
    summary["port_candidate_cell_count"] = len(candidate_ids)
    summary["port_site_total_area_km2"] = round(sum(float(record["area_km2"]) for record in records), 6)
    summary["mean_port_suitability_index"] = round(suitability_sum / count, 6)
    summary["mean_protected_bay_index"] = round(protected_sum / count, 6)
    summary["mean_river_mouth_port_index"] = round(river_mouth_sum / count, 6)
    summary["mean_strait_access_index"] = round(strait_sum / count, 6)
    summary["port_settlement_count"] = sum(
        1
        for settlements in settlements_by_cell.values()
        for settlement in settlements
        if str(settlement.get("type", "")) == "port"
    )
    summary["port_settlement_with_site_count"] = sum(
        1
        for settlements in settlements_by_cell.values()
        for settlement in settlements
        if str(settlement.get("type", "")) == "port" and int(settlement.get("cell_id", -1)) in candidate_ids
    )
    summary["protected_bay_port_site_count"] = int(type_counts.get("protected_bay_port", 0))
    summary["river_mouth_port_site_count"] = int(type_counts.get("river_mouth_port", 0))
    summary["strait_port_site_count"] = int(type_counts.get("strait_port", 0))
    summary["port_site_type_counts"] = dict(sorted(type_counts.items()))
    world["port_sites"] = records
    return world
