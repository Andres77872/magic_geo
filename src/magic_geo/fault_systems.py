from __future__ import annotations

import math
from collections import Counter, deque
from typing import Any


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _round(value: float) -> float:
    return round(float(value), 6)


def _dominant(counter: Counter[str], fallback: str = "unknown") -> str:
    if not counter:
        return fallback
    return sorted(counter.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _xyz_from_lat_lon(lat_deg: float, lon_deg: float) -> tuple[float, float, float]:
    lat = math.radians(lat_deg)
    lon = math.radians(lon_deg)
    cos_lat = math.cos(lat)
    return cos_lat * math.cos(lon), cos_lat * math.sin(lon), math.sin(lat)


def _lat_lon_from_xyz(x: float, y: float, z: float) -> tuple[float, float]:
    length = math.sqrt(x * x + y * y + z * z)
    if length <= 0.0:
        return 0.0, 0.0
    x /= length
    y /= length
    z /= length
    return math.degrees(math.asin(_clamp(z, -1.0, 1.0))), math.degrees(math.atan2(y, x))


def _plate_boundary_fraction(cell: dict[str, Any], edges_by_id: dict[int, dict[str, Any]]) -> float:
    edge_ids = cell.get("cell_adjacency_edge_ids", [])
    if not isinstance(edge_ids, list) or not edge_ids:
        return 0.0
    boundary_count = 0
    valid_count = 0
    for raw_edge_id in edge_ids:
        edge = edges_by_id.get(int(raw_edge_id))
        if not edge:
            continue
        valid_count += 1
        if bool(edge.get("plate_boundary", False)):
            boundary_count += 1
    return float(boundary_count) / float(valid_count) if valid_count else 0.0


def _fault_metrics(cell: dict[str, Any], edges_by_id: dict[int, dict[str, Any]]) -> tuple[float, float, float]:
    transform = _clamp(float(cell.get("boundary_transform", 0.0)))
    convergent = _clamp(float(cell.get("boundary_convergent", 0.0)))
    divergent = _clamp(float(cell.get("boundary_divergent", 0.0)))
    boundary_activity = max(transform, convergent, divergent)
    boundary_fraction = _plate_boundary_fraction(cell, edges_by_id)
    transform_relief = _clamp(abs(float(cell.get("initial_transform_fault_relief_m", 0.0))) / 900.0)
    ruggedness = _clamp(abs(float(cell.get("elevation_m", 0.0)) - float(cell.get("initial_elevation_m", 0.0))) / 1800.0)
    volcanic = _clamp(float(cell.get("volcanic_potential_index", 0.0)))

    slip = _clamp(
        transform * 0.58
        + max(convergent, divergent) * 0.18
        + boundary_fraction * 0.12
        + transform_relief * 0.08
        + ruggedness * 0.04
    )
    hazard = _clamp(slip * 0.56 + convergent * 0.22 + divergent * 0.10 + volcanic * 0.06 + boundary_activity * 0.06)
    recurrence = 0.0 if hazard < 0.08 else 35.0 + (1.0 - hazard) * 965.0
    return slip, hazard, recurrence


def _connected_components(candidate_ids: set[int], cells_by_id: dict[int, dict[str, Any]]) -> list[list[int]]:
    components: list[list[int]] = []
    remaining = set(candidate_ids)
    while remaining:
        start = min(remaining)
        remaining.remove(start)
        queue: deque[int] = deque([start])
        component: list[int] = []
        while queue:
            cell_id = queue.popleft()
            component.append(cell_id)
            cell = cells_by_id.get(cell_id, {})
            for raw_neighbor in cell.get("neighbors", []):
                neighbor_id = int(raw_neighbor)
                if neighbor_id in remaining:
                    remaining.remove(neighbor_id)
                    queue.append(neighbor_id)
        components.append(sorted(component))
    return sorted(components, key=lambda item: (len(item), item[0]), reverse=True)


def _fault_system_record(
    system_id: int,
    cell_ids: list[int],
    cells_by_id: dict[int, dict[str, Any]],
    edges_by_id: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    cell_id_set = set(cell_ids)
    area = 0.0
    slip_sum = 0.0
    hazard_sum = 0.0
    recurrence_sum = 0.0
    x_sum = 0.0
    y_sum = 0.0
    z_sum = 0.0
    boundary_type_counts: Counter[str] = Counter()
    crust_counts: Counter[str] = Counter()
    landform_counts: Counter[str] = Counter()
    plate_ids: set[int] = set()
    boundary_edge_ids: set[int] = set()
    plate_pairs: set[tuple[int, int]] = set()
    boundary_length = 0.0

    for cell_id in cell_ids:
        cell = cells_by_id[cell_id]
        weight = max(0.0, float(cell.get("area_km2", 0.0)))
        area += weight
        slip = float(cell.get("fault_slip_rate_index", 0.0))
        hazard = float(cell.get("seismic_hazard_index", 0.0))
        recurrence = float(cell.get("earthquake_recurrence_interval_y", 0.0))
        slip_sum += slip * weight
        hazard_sum += hazard * weight
        recurrence_sum += recurrence * weight
        boundary_type_counts[str(cell.get("boundary_type", "none"))] += 1
        crust_counts[str(cell.get("crust_type", "unknown"))] += 1
        landform_counts[str(cell.get("landform", "unknown"))] += 1
        plate_id = int(cell.get("plate_id", -1))
        if plate_id >= 0:
            plate_ids.add(plate_id)
        x, y, z = _xyz_from_lat_lon(float(cell.get("lat_deg", 0.0)), float(cell.get("lon_deg", 0.0)))
        x_sum += x * weight
        y_sum += y * weight
        z_sum += z * weight

        for raw_edge_id in cell.get("cell_adjacency_edge_ids", []):
            edge_id = int(raw_edge_id)
            edge = edges_by_id.get(edge_id)
            if not edge or not bool(edge.get("plate_boundary", False)):
                continue
            cell_a = int(edge.get("cell_a_id", -1))
            cell_b = int(edge.get("cell_b_id", -1))
            if cell_a not in cell_id_set and cell_b not in cell_id_set:
                continue
            boundary_edge_ids.add(edge_id)
            edge_a = cells_by_id.get(cell_a)
            edge_b = cells_by_id.get(cell_b)
            if edge_a and edge_b:
                plate_a = int(edge_a.get("plate_id", -1))
                plate_b = int(edge_b.get("plate_id", -1))
                if plate_a >= 0 and plate_b >= 0 and plate_a != plate_b:
                    plate_pairs.add((min(plate_a, plate_b), max(plate_a, plate_b)))

    for edge_id in boundary_edge_ids:
        edge = edges_by_id.get(edge_id, {})
        boundary_length += float(edge.get("boundary_segment_length_km", edge.get("great_circle_distance_km", 0.0)))

    divisor = area if area > 0.0 else float(max(1, len(cell_ids)))
    centroid_lat, centroid_lon = _lat_lon_from_xyz(x_sum, y_sum, z_sum)
    representative_cell_id = max(cell_ids, key=lambda item: (float(cells_by_id[item].get("seismic_hazard_index", 0.0)), -item))
    return {
        "id": system_id,
        "cell_ids": cell_ids,
        "cell_count": len(cell_ids),
        "area_km2": _round(area),
        "boundary_edge_ids": sorted(boundary_edge_ids),
        "boundary_edge_count": len(boundary_edge_ids),
        "boundary_length_km": _round(boundary_length),
        "plate_ids": sorted(plate_ids),
        "plate_pair_ids": [list(pair) for pair in sorted(plate_pairs)],
        "mean_fault_slip_rate_index": _round(slip_sum / divisor),
        "max_fault_slip_rate_index": _round(max(float(cells_by_id[cell_id].get("fault_slip_rate_index", 0.0)) for cell_id in cell_ids)),
        "mean_seismic_hazard_index": _round(hazard_sum / divisor),
        "max_seismic_hazard_index": _round(max(float(cells_by_id[cell_id].get("seismic_hazard_index", 0.0)) for cell_id in cell_ids)),
        "mean_earthquake_recurrence_interval_y": _round(recurrence_sum / divisor),
        "representative_cell_id": representative_cell_id,
        "centroid_lat_deg": _round(centroid_lat),
        "centroid_lon_deg": _round(centroid_lon),
        "dominant_boundary_type": _dominant(boundary_type_counts, "none"),
        "dominant_crust_type": _dominant(crust_counts),
        "dominant_landform": _dominant(landform_counts),
        "transform_fault_cell_count": sum(
            1
            for cell_id in cell_ids
            if float(cells_by_id[cell_id].get("boundary_transform", 0.0)) >= 0.28
            or str(cells_by_id[cell_id].get("boundary_type", "")) == "transform"
        ),
        "convergent_fault_cell_count": sum(1 for cell_id in cell_ids if float(cells_by_id[cell_id].get("boundary_convergent", 0.0)) >= 0.28),
        "divergent_fault_cell_count": sum(1 for cell_id in cell_ids if float(cells_by_id[cell_id].get("boundary_divergent", 0.0)) >= 0.28),
    }


def enrich_world_with_fault_systems(world: dict[str, Any]) -> dict[str, Any]:
    cells = world.get("cells", [])
    if not isinstance(cells, list) or not cells:
        return world
    cells_by_id = {int(cell.get("id", -1)): cell for cell in cells if isinstance(cell, dict)}
    edges = world.get("cell_adjacency_edges", [])
    edges_by_id = {int(edge.get("id", -1)): edge for edge in edges if isinstance(edge, dict)}

    slip_sum = 0.0
    hazard_sum = 0.0
    recurrence_sum = 0.0
    recurrence_count = 0
    high_hazard_count = 0
    candidate_ids: set[int] = set()

    for cell in cells:
        slip, hazard, recurrence = _fault_metrics(cell, edges_by_id)
        cell["fault_slip_rate_index"] = _round(slip)
        cell["seismic_hazard_index"] = _round(hazard)
        cell["earthquake_recurrence_interval_y"] = _round(recurrence)
        cell["fault_system_id"] = -1
        slip_sum += slip
        hazard_sum += hazard
        if recurrence > 0.0:
            recurrence_sum += recurrence
            recurrence_count += 1
        if hazard >= 0.55:
            high_hazard_count += 1
        if slip >= 0.30 or hazard >= 0.35:
            candidate_ids.add(int(cell.get("id", -1)))

    fault_systems = [
        _fault_system_record(index, component, cells_by_id, edges_by_id)
        for index, component in enumerate(_connected_components(candidate_ids, cells_by_id))
        if component
    ]
    for system in fault_systems:
        for cell_id in system["cell_ids"]:
            cells_by_id[cell_id]["fault_system_id"] = int(system["id"])

    cell_count = len(cells)
    summary = world.setdefault("summary", {})
    summary["fault_system_count"] = len(fault_systems)
    summary["fault_system_cell_count"] = sum(int(system["cell_count"]) for system in fault_systems)
    summary["fault_system_total_area_km2"] = _round(sum(float(system["area_km2"]) for system in fault_systems))
    summary["fault_system_boundary_length_km"] = _round(sum(float(system["boundary_length_km"]) for system in fault_systems))
    summary["mean_fault_slip_rate_index"] = _round(slip_sum / cell_count)
    summary["mean_seismic_hazard_index"] = _round(hazard_sum / cell_count)
    summary["high_seismic_hazard_cell_count"] = high_hazard_count
    summary["mean_earthquake_recurrence_interval_y"] = _round(recurrence_sum / recurrence_count) if recurrence_count else 0.0
    world["fault_systems"] = fault_systems
    return world
