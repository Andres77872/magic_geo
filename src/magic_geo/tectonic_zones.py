from __future__ import annotations

import math
from collections import Counter, deque
from typing import Any


ZONE_TYPES = ("collision", "subduction", "rift")


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


def _zone_strength(zone_type: str, cell: dict[str, Any]) -> float:
    crust = str(cell.get("crust_type", "unknown"))
    lithology = str(cell.get("lithology", "unknown"))
    landform = str(cell.get("landform", "unknown"))
    convergent = _clamp(float(cell.get("boundary_convergent", 0.0)))
    divergent = _clamp(float(cell.get("boundary_divergent", 0.0)))
    volcanic = _clamp(float(cell.get("volcanic_potential_index", 0.0)))
    orogenic = _clamp(float(cell.get("initial_orogenic_uplift_m", 0.0)) / 2600.0)
    trench = _clamp(abs(float(cell.get("initial_trench_subsidence_m", 0.0))) / 2600.0)
    rift = _clamp(abs(float(cell.get("initial_rift_subsidence_m", 0.0))) / 1200.0)

    if zone_type == "collision":
        return _clamp(
            convergent * 0.58
            + (0.20 if crust == "orogen" else 0.0)
            + (0.10 if lithology == "metamorphic" else 0.0)
            + (0.08 if landform == "mountain_belt" else 0.0)
            + orogenic * 0.12
        )
    if zone_type == "subduction":
        return _clamp(
            convergent * 0.50
            + (0.18 if crust == "volcanic_arc" else 0.0)
            + (0.12 if landform in {"volcanic_arc", "trench"} else 0.0)
            + volcanic * 0.12
            + trench * 0.08
        )
    if zone_type == "rift":
        return _clamp(
            divergent * 0.62
            + (0.18 if crust == "rift_basin" else 0.0)
            + (0.12 if landform == "rift_valley" else 0.0)
            + rift * 0.08
        )
    return 0.0


def _candidate_cells(zone_type: str, cells: list[dict[str, Any]]) -> dict[int, float]:
    candidates: dict[int, float] = {}
    for cell in cells:
        cell_id = int(cell.get("id", -1))
        if cell_id < 0:
            continue
        strength = _zone_strength(zone_type, cell)
        if strength >= 0.34:
            candidates[cell_id] = strength
    return candidates


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


def _zone_record(
    zone_id: int,
    zone_type: str,
    cell_ids: list[int],
    strengths: dict[int, float],
    cells_by_id: dict[int, dict[str, Any]],
    edges_by_id: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    cell_id_set = set(cell_ids)
    area = 0.0
    strength_sum = 0.0
    conv_sum = 0.0
    div_sum = 0.0
    transform_sum = 0.0
    elevation_sum = 0.0
    thickness_sum = 0.0
    age_sum = 0.0
    x_sum = 0.0
    y_sum = 0.0
    z_sum = 0.0
    crust_counts: Counter[str] = Counter()
    lithology_counts: Counter[str] = Counter()
    landform_counts: Counter[str] = Counter()
    plate_ids: set[int] = set()
    boundary_edge_ids: set[int] = set()
    plate_pairs: set[tuple[int, int]] = set()
    boundary_length = 0.0

    for cell_id in cell_ids:
        cell = cells_by_id[cell_id]
        weight = max(0.0, float(cell.get("area_km2", 0.0)))
        area += weight
        strength = strengths[cell_id]
        strength_sum += strength * weight
        conv_sum += float(cell.get("boundary_convergent", 0.0)) * weight
        div_sum += float(cell.get("boundary_divergent", 0.0)) * weight
        transform_sum += float(cell.get("boundary_transform", 0.0)) * weight
        elevation_sum += float(cell.get("elevation_m", 0.0)) * weight
        thickness_sum += float(cell.get("crust_thickness_km", 0.0)) * weight
        age_sum += float(cell.get("crust_age_ma", 0.0)) * weight
        crust_counts[str(cell.get("crust_type", "unknown"))] += 1
        lithology_counts[str(cell.get("lithology", "unknown"))] += 1
        landform_counts[str(cell.get("landform", "unknown"))] += 1
        plate_ids.add(int(cell.get("plate_id", -1)))
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
    max_cell_id = max(cell_ids, key=lambda item: (strengths[item], -item))
    return {
        "id": zone_id,
        "zone_type": zone_type,
        "cell_ids": cell_ids,
        "cell_count": len(cell_ids),
        "area_km2": _round(area),
        "boundary_edge_ids": sorted(boundary_edge_ids),
        "boundary_edge_count": len(boundary_edge_ids),
        "boundary_length_km": _round(boundary_length),
        "plate_ids": sorted(plate_id for plate_id in plate_ids if plate_id >= 0),
        "plate_pair_ids": [list(pair) for pair in sorted(plate_pairs)],
        "mean_zone_strength": _round(strength_sum / divisor),
        "max_zone_strength": _round(strengths[max_cell_id]),
        "representative_cell_id": max_cell_id,
        "centroid_lat_deg": _round(centroid_lat),
        "centroid_lon_deg": _round(centroid_lon),
        "mean_boundary_convergent": _round(conv_sum / divisor),
        "mean_boundary_divergent": _round(div_sum / divisor),
        "mean_boundary_transform": _round(transform_sum / divisor),
        "mean_elevation_m": _round(elevation_sum / divisor),
        "mean_crust_thickness_km": _round(thickness_sum / divisor),
        "mean_crust_age_ma": _round(age_sum / divisor),
        "dominant_crust_type": _dominant(crust_counts),
        "dominant_lithology": _dominant(lithology_counts),
        "dominant_landform": _dominant(landform_counts),
        "formation_evidence": {
            "high_convergent_cell_count": sum(
                1 for cell_id in cell_ids if float(cells_by_id[cell_id].get("boundary_convergent", 0.0)) >= 0.34
            ),
            "high_divergent_cell_count": sum(
                1 for cell_id in cell_ids if float(cells_by_id[cell_id].get("boundary_divergent", 0.0)) >= 0.34
            ),
            "orogen_cell_count": sum(1 for cell_id in cell_ids if cells_by_id[cell_id].get("crust_type") == "orogen"),
            "volcanic_arc_cell_count": sum(
                1 for cell_id in cell_ids if cells_by_id[cell_id].get("crust_type") == "volcanic_arc"
            ),
            "rift_basin_cell_count": sum(1 for cell_id in cell_ids if cells_by_id[cell_id].get("crust_type") == "rift_basin"),
        },
    }


def _build_zone_records(
    zone_type: str,
    cells: list[dict[str, Any]],
    cells_by_id: dict[int, dict[str, Any]],
    edges_by_id: dict[int, dict[str, Any]],
) -> list[dict[str, Any]]:
    strengths = _candidate_cells(zone_type, cells)
    components = _connected_components(set(strengths), cells_by_id)
    return [
        _zone_record(index, zone_type, component, strengths, cells_by_id, edges_by_id)
        for index, component in enumerate(components)
    ]


def enrich_world_with_tectonic_zones(world: dict[str, Any]) -> dict[str, Any]:
    cells = world.get("cells", [])
    if not isinstance(cells, list) or not cells:
        return world
    cells_by_id = {int(cell.get("id", -1)): cell for cell in cells if isinstance(cell, dict)}
    edges = world.get("cell_adjacency_edges", [])
    edges_by_id = {int(edge.get("id", -1)): edge for edge in edges if isinstance(edge, dict)}

    for cell in cells:
        cell["collision_zone_id"] = -1
        cell["subduction_zone_id"] = -1
        cell["rift_zone_id"] = -1
        cell["dominant_tectonic_zone_type"] = "none"
        cell["tectonic_zone_strength"] = 0.0

    collision_zones = _build_zone_records("collision", cells, cells_by_id, edges_by_id)
    subduction_zones = _build_zone_records("subduction", cells, cells_by_id, edges_by_id)
    rift_zones = _build_zone_records("rift", cells, cells_by_id, edges_by_id)
    zone_groups = {
        "collision": collision_zones,
        "subduction": subduction_zones,
        "rift": rift_zones,
    }

    tectonic_zones: list[dict[str, Any]] = []
    global_zone_id = 0
    for zone_type in ZONE_TYPES:
        for zone in zone_groups[zone_type]:
            combined = dict(zone)
            combined["id"] = global_zone_id
            combined["local_zone_id"] = zone["id"]
            tectonic_zones.append(combined)
            for cell_id in zone["cell_ids"]:
                cell = cells_by_id[cell_id]
                local_key = f"{zone_type}_zone_id"
                cell[local_key] = int(zone["id"])
                strength = _zone_strength(zone_type, cell)
                if strength > float(cell.get("tectonic_zone_strength", 0.0)):
                    cell["dominant_tectonic_zone_type"] = zone_type
                    cell["tectonic_zone_strength"] = _round(strength)
            global_zone_id += 1

    summary = world.setdefault("summary", {})
    summary["tectonic_zone_count"] = len(tectonic_zones)
    summary["collision_zone_count"] = len(collision_zones)
    summary["subduction_zone_count"] = len(subduction_zones)
    summary["rift_zone_count"] = len(rift_zones)
    summary["collision_zone_cell_count"] = sum(zone["cell_count"] for zone in collision_zones)
    summary["subduction_zone_cell_count"] = sum(zone["cell_count"] for zone in subduction_zones)
    summary["rift_zone_cell_count"] = sum(zone["cell_count"] for zone in rift_zones)
    summary["tectonic_zone_total_area_km2"] = _round(sum(float(zone["area_km2"]) for zone in tectonic_zones))
    summary["tectonic_zone_boundary_length_km"] = _round(sum(float(zone["boundary_length_km"]) for zone in tectonic_zones))
    summary["mean_tectonic_zone_strength"] = _round(
        sum(float(zone["mean_zone_strength"]) for zone in tectonic_zones) / len(tectonic_zones)
    ) if tectonic_zones else 0.0

    world["collision_zones"] = collision_zones
    world["subduction_zones"] = subduction_zones
    world["rift_zones"] = rift_zones
    world["tectonic_zones"] = tectonic_zones
    return world
