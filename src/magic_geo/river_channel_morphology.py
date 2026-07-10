from __future__ import annotations

import math
from collections import Counter, deque
from typing import Any


LOWLAND_FORMS = {"delta", "floodplain", "river_valley", "coastal_plain", "lacustrine_basin"}
RIVER_CHANNEL_MORPHOLOGY_MODEL = (
    "causal_flow_sediment_wetland_baseflow_channel_morphology_v1"
)
CHANNEL_CLASSES = {
    "non_channel",
    "small_headwater",
    "incised_bedrock_channel",
    "braided_sediment_rich_channel",
    "deep_alluvial_channel",
    "navigable_lowland_channel",
    "ephemeral_wadi",
    "glacial_outwash_channel",
}


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _cell_id(cell: dict[str, Any]) -> int:
    return int(cell.get("id", -1))


def _area(cell: dict[str, Any]) -> float:
    return max(0.0, float(cell.get("area_km2", 0.0)))


def _great_circle_km(a: dict[str, Any], b: dict[str, Any]) -> float:
    radius_km = 6371.0
    lat_a = math.radians(float(a.get("lat_deg", 0.0)))
    lat_b = math.radians(float(b.get("lat_deg", 0.0)))
    dlat = lat_b - lat_a
    dlon = math.radians(float(b.get("lon_deg", 0.0)) - float(a.get("lon_deg", 0.0)))
    hav = math.sin(dlat / 2.0) ** 2 + math.cos(lat_a) * math.cos(lat_b) * math.sin(dlon / 2.0) ** 2
    return 2.0 * radius_km * math.asin(min(1.0, math.sqrt(hav)))


def _downstream_slope(cell: dict[str, Any], cells_by_id: dict[int, dict[str, Any]]) -> tuple[float, float]:
    next_cell = cells_by_id.get(int(cell.get("flow_to", -1)))
    if next_cell is None:
        return 0.0, 0.0
    length_km = _great_circle_km(cell, next_cell)
    if length_km <= 0.0:
        return 0.0, 0.0
    source_elevation = float(
        cell.get(
            "hydrologic_surface_elevation_m",
            cell.get("filled_elevation_m", cell.get("elevation_m", 0.0)),
        )
    )
    target_elevation = float(
        next_cell.get(
            "hydrologic_surface_elevation_m",
            next_cell.get("filled_elevation_m", next_cell.get("elevation_m", 0.0)),
        )
    )
    drop_m = max(0.0, source_elevation - target_elevation)
    return drop_m / max(1.0, length_km * 1000.0), length_km


def _channel_class(
    flow_norm: float,
    runoff_norm: float,
    slope_index: float,
    sediment_index: float,
    floodplain: float,
    depth_m: float,
    width_m: float,
    aridity: float,
    ice: float,
) -> str:
    if ice >= 0.28:
        return "glacial_outwash_channel"
    if aridity >= 0.58 and runoff_norm < 0.22:
        return "ephemeral_wadi"
    if sediment_index >= 0.55 and flow_norm >= 0.18:
        return "braided_sediment_rich_channel"
    if slope_index >= 0.46 and sediment_index < 0.38:
        return "incised_bedrock_channel"
    if depth_m >= 3.2 and floodplain >= 0.45:
        return "deep_alluvial_channel"
    if depth_m >= 1.8 and width_m >= 42.0 and slope_index <= 0.32:
        return "navigable_lowland_channel"
    return "small_headwater"


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


def _primary_key(counter: Counter[str], fallback: str) -> str:
    if not counter:
        return fallback
    return sorted(counter.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _system_length(component: list[dict[str, Any]], member_ids: set[int], cells_by_id: dict[int, dict[str, Any]]) -> float:
    total = 0.0
    for cell in component:
        next_id = int(cell.get("flow_to", -1))
        if next_id in member_ids:
            next_cell = cells_by_id.get(next_id)
            if next_cell is not None:
                total += _great_circle_km(cell, next_cell)
    return total


def enrich_world_with_river_channel_morphology(world: dict[str, Any]) -> dict[str, Any]:
    cells = world.get("cells", [])
    if not isinstance(cells, list) or not cells:
        return world

    cells_by_id = {_cell_id(cell): cell for cell in cells}
    max_flow = max((max(0.0, float(cell.get("flow_accumulation", 0.0))) for cell in cells), default=1.0)
    river_ids: set[int] = set()
    class_counts: Counter[str] = Counter()
    width_sum = 0.0
    depth_sum = 0.0
    discharge_sum = 0.0
    stream_power_sum = 0.0
    slope_sum = 0.0
    navigable_depth_count = 0
    floodplain_connected_count = 0
    high_stream_power_count = 0

    for cell in cells:
        cell["river_channel_width_m"] = 0.0
        cell["river_channel_depth_m"] = 0.0
        cell["bankfull_discharge_m3_s"] = 0.0
        cell["channel_slope_index"] = 0.0
        cell["stream_power_index"] = 0.0
        cell["floodplain_connectivity_index"] = 0.0
        cell["channel_morphology_class"] = "non_channel"
        cell["river_channel_system_id"] = -1
        if not bool(cell.get("is_river", False)) or bool(cell.get("is_water", False)):
            class_counts["non_channel"] += 1
            continue

        cell_id = _cell_id(cell)
        river_ids.add(cell_id)
        flow_norm = _clamp(float(cell.get("flow_accumulation", 0.0)) / max(1.0, max_flow))
        runoff_norm = _clamp(float(cell.get("runoff_mm_y", 0.0)) / 2200.0)
        slope, _ = _downstream_slope(cell, cells_by_id)
        slope_index = _clamp(slope / 0.028)
        routed_sediment = float(
            cell.get(
                "fluvial_sediment_routed_outgoing_m",
                cell.get("sediment_export_m", 0.0),
            )
        )
        sediment_index = _clamp(
            routed_sediment / 85.0 * 0.45
            + float(cell.get("sediment_deposition_m", 0.0)) / 18.0 * 0.35
            + float(cell.get("sediment_thickness_m", 0.0)) / 30.0 * 0.20
        )
        lowland = 1.0 if str(cell.get("landform", "")) in LOWLAND_FORMS else 0.0
        wetland = _clamp(float(cell.get("wetland_extent_index", 0.0)))
        groundwater = _clamp(float(cell.get("baseflow_support_index", 0.0)))
        aridity = _clamp(float(cell.get("seasonal_aridity_index", 0.0)))
        ice = _clamp(float(cell.get("ice_thickness_m", 0.0)) / 450.0)
        floodplain = _clamp(lowland * 0.34 + (1.0 - slope_index) * 0.22 + sediment_index * 0.18 + wetland * 0.14 + groundwater * 0.12)
        discharge = max(
            0.0,
            8.0
            + 4600.0 * (flow_norm**0.82) * (0.30 + runoff_norm * 0.62 + groundwater * 0.08)
            - ice * 420.0
            - aridity * 120.0,
        )
        width = max(
            0.0,
            5.0
            + 210.0 * (flow_norm**0.56) * (0.42 + runoff_norm * 0.36 + floodplain * 0.22)
            + sediment_index * 36.0
            - slope_index * 14.0
            - ice * 18.0,
        )
        depth = max(
            0.0,
            0.35
            + 7.6 * (flow_norm**0.42) * (0.36 + runoff_norm * 0.34 + groundwater * 0.12 + (1.0 - sediment_index) * 0.18)
            + slope_index * 0.55
            - aridity * 0.36
            - ice * 0.45,
        )
        stream_power = _clamp((discharge / 4200.0) * 0.42 + slope_index * 0.34 + runoff_norm * 0.12 + sediment_index * 0.08 + flow_norm * 0.04)
        morphology = _channel_class(flow_norm, runoff_norm, slope_index, sediment_index, floodplain, depth, width, aridity, ice)

        cell["river_channel_width_m"] = round(width, 6)
        cell["river_channel_depth_m"] = round(depth, 6)
        cell["bankfull_discharge_m3_s"] = round(discharge, 6)
        cell["channel_slope_index"] = round(slope_index, 6)
        cell["stream_power_index"] = round(stream_power, 6)
        cell["floodplain_connectivity_index"] = round(floodplain, 6)
        cell["channel_morphology_class"] = morphology

        width_sum += width
        depth_sum += depth
        discharge_sum += discharge
        stream_power_sum += stream_power
        slope_sum += slope_index
        navigable_depth_count += 1 if depth >= 1.8 and width >= 35.0 else 0
        floodplain_connected_count += 1 if floodplain >= 0.45 else 0
        high_stream_power_count += 1 if stream_power >= 0.62 else 0
        class_counts[morphology] += 1

    systems: list[dict[str, Any]] = []
    for component in _connected_components(river_ids, cells_by_id):
        system_id = len(systems)
        member_ids = {_cell_id(cell) for cell in component}
        for cell in component:
            cell["river_channel_system_id"] = system_id
        class_counter = Counter(str(cell.get("channel_morphology_class", "small_headwater")) for cell in component)
        basin_ids = sorted({int(cell.get("basin_id", -1)) for cell in component if int(cell.get("basin_id", -1)) >= 0})
        outlet_candidates = [
            cell
            for cell in component
            if int(cell.get("flow_to", -1)) not in member_ids
        ] or component
        source_cell = max(
            component,
            key=lambda item: (
                float(
                    item.get(
                        "hydrologic_surface_elevation_m",
                        item.get("filled_elevation_m", item.get("elevation_m", 0.0)),
                    )
                ),
                -_cell_id(item),
            ),
        )
        outlet_cell = max(outlet_candidates, key=lambda item: (float(item.get("flow_accumulation", 0.0)), -_cell_id(item)))
        group_count = len(component)
        length_km = _system_length(component, member_ids, cells_by_id)
        systems.append(
            {
                "id": system_id,
                "channel_type": _primary_key(class_counter, "small_headwater"),
                "cell_count": group_count,
                "cell_ids": sorted(member_ids),
                "basin_ids": basin_ids,
                "source_cell_id": _cell_id(source_cell),
                "outlet_cell_id": _cell_id(outlet_cell),
                "length_km": round(length_km, 6),
                "area_km2": round(sum(_area(cell) for cell in component), 6),
                "mean_channel_width_m": round(sum(float(cell.get("river_channel_width_m", 0.0)) for cell in component) / group_count, 6),
                "mean_channel_depth_m": round(sum(float(cell.get("river_channel_depth_m", 0.0)) for cell in component) / group_count, 6),
                "mean_bankfull_discharge_m3_s": round(sum(float(cell.get("bankfull_discharge_m3_s", 0.0)) for cell in component) / group_count, 6),
                "mean_stream_power_index": round(sum(float(cell.get("stream_power_index", 0.0)) for cell in component) / group_count, 6),
                "mean_channel_slope_index": round(sum(float(cell.get("channel_slope_index", 0.0)) for cell in component) / group_count, 6),
                "mean_floodplain_connectivity_index": round(
                    sum(float(cell.get("floodplain_connectivity_index", 0.0)) for cell in component) / group_count,
                    6,
                ),
                "navigable_depth_cell_count": sum(
                    1
                    for cell in component
                    if float(cell.get("river_channel_depth_m", 0.0)) >= 1.8 and float(cell.get("river_channel_width_m", 0.0)) >= 35.0
                ),
                "floodplain_connected_cell_count": sum(
                    1 for cell in component if float(cell.get("floodplain_connectivity_index", 0.0)) >= 0.45
                ),
                "high_stream_power_cell_count": sum(1 for cell in component if float(cell.get("stream_power_index", 0.0)) >= 0.62),
                "channel_morphology_class_counts": dict(sorted(class_counter.items())),
            }
        )

    summary = world.setdefault("summary", {})
    river_count = len(river_ids)
    divisor = river_count if river_count else 1
    world["river_channel_morphology_model"] = {
        "model_type": RIVER_CHANNEL_MORPHOLOGY_MODEL,
        "domain": "is_river_and_not_is_water_cells",
        "flow_normalization_model": "global_max_flow_accumulation_v1",
        "runoff_normalization_mm_y": 2200.0,
        "slope_model": "downstream_conditioned_surface_drop_over_great_circle_distance_v1",
        "slope_normalization": 0.028,
        "planet_radius_km": 6371.0,
        "sediment_model": "routed_outgoing_deposition_and_mobile_thickness_v1",
        "floodplain_model": "lowland_slope_sediment_wetland_baseflow_index_v1",
        "geometry_model": "flow_runoff_floodplain_sediment_slope_baseflow_aridity_ice_v1",
        "stream_power_model": "discharge_slope_runoff_sediment_flow_index_v1",
        "classification_model": "ice_aridity_sediment_slope_depth_width_threshold_tree_v1",
        "system_grouping_model": "undirected_mesh_connected_channel_components_v1",
        "system_length_model": "internal_flow_to_great_circle_edges_v1",
        "deterministic": True,
        "candidate_cell_count": river_count,
        "system_count": len(systems),
        "model_limitation": "empirical_diagnostic_channel_geometry_without_subcell_cross_sections_calibrated_bankfull_frequency_or_transient_morphodynamics",
    }
    summary["river_channel_morphology_model"] = (
        RIVER_CHANNEL_MORPHOLOGY_MODEL
    )
    summary["river_channel_cell_count"] = river_count
    summary["river_channel_system_count"] = len(systems)
    summary["navigable_channel_depth_cell_count"] = navigable_depth_count
    summary["floodplain_connected_channel_cell_count"] = floodplain_connected_count
    summary["high_stream_power_channel_cell_count"] = high_stream_power_count
    summary["total_river_channel_length_km"] = round(sum(float(system.get("length_km", 0.0)) for system in systems), 6)
    summary["mean_river_channel_width_m"] = round(width_sum / divisor, 6) if river_count else 0.0
    summary["mean_river_channel_depth_m"] = round(depth_sum / divisor, 6) if river_count else 0.0
    summary["mean_bankfull_discharge_m3_s"] = round(discharge_sum / divisor, 6) if river_count else 0.0
    summary["mean_stream_power_index"] = round(stream_power_sum / divisor, 6) if river_count else 0.0
    summary["mean_channel_slope_index"] = round(slope_sum / divisor, 6) if river_count else 0.0
    summary["channel_morphology_class_counts"] = dict(sorted(class_counts.items()))
    world["river_channel_systems"] = systems
    return world
