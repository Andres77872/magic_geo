from __future__ import annotations

import math
from typing import Any


EARTH_RADIUS_KM = 6371.0


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _xyz_from_lat_lon(lat_deg: float, lon_deg: float) -> tuple[float, float, float]:
    lat = math.radians(lat_deg)
    lon = math.radians(lon_deg)
    cos_lat = math.cos(lat)
    return cos_lat * math.cos(lon), cos_lat * math.sin(lon), math.sin(lat)


def _normalize(vector: tuple[float, float, float]) -> tuple[float, float, float]:
    x, y, z = vector
    length = math.sqrt(x * x + y * y + z * z)
    if length <= 0.0:
        return 1.0, 0.0, 0.0
    return x / length, y / length, z / length


def _dot(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _add(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    return a[0] + b[0], a[1] + b[1], a[2] + b[2]


def _scale(vector: tuple[float, float, float], factor: float) -> tuple[float, float, float]:
    return vector[0] * factor, vector[1] * factor, vector[2] * factor


def _lat_lon_from_xyz(vector: tuple[float, float, float]) -> tuple[float, float]:
    x, y, z = _normalize(vector)
    return math.degrees(math.asin(_clamp(z, -1.0, 1.0))), math.degrees(math.atan2(y, x))


def _central_angle(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return math.acos(_clamp(_dot(a, b), -1.0, 1.0))


def _triangle_area_steradians(
    a: tuple[float, float, float],
    b: tuple[float, float, float],
    c: tuple[float, float, float],
) -> float:
    numerator = abs(_dot(a, _cross(b, c)))
    denominator = 1.0 + _dot(a, b) + _dot(b, c) + _dot(c, a)
    if numerator <= 0.0 or denominator <= 0.0:
        return 0.0
    return 2.0 * math.atan2(numerator, denominator)


def _local_basis(lat_deg: float, lon_deg: float) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    lat = math.radians(lat_deg)
    lon = math.radians(lon_deg)
    east = (-math.sin(lon), math.cos(lon), 0.0)
    north = (-math.sin(lat) * math.cos(lon), -math.sin(lat) * math.sin(lon), math.cos(lat))
    return _normalize(east), _normalize(north)


def _bearing_deg(
    origin: tuple[float, float, float],
    target: tuple[float, float, float],
    east: tuple[float, float, float],
    north: tuple[float, float, float],
) -> float:
    tangent = _add(target, _scale(origin, -_dot(target, origin)))
    tangent = _normalize(tangent)
    bearing = math.degrees(math.atan2(_dot(tangent, north), _dot(tangent, east)))
    if bearing < 0.0:
        bearing += 360.0
    return bearing


def _edge_class(cell: dict[str, Any], neighbor: dict[str, Any]) -> str:
    if bool(cell.get("is_water", False)) != bool(neighbor.get("is_water", False)):
        return "land_water_transition"
    if int(cell.get("plate_id", -1)) != int(neighbor.get("plate_id", -1)):
        return "tectonic_plate_edge"
    if str(cell.get("water_body_type", "land")) != str(neighbor.get("water_body_type", "land")):
        return "water_body_transition"
    if str(cell.get("biome", "unknown")) != str(neighbor.get("biome", "unknown")):
        return "biome_transition"
    if bool(cell.get("is_water", False)):
        return "open_water_adjacency"
    return "interior_land_adjacency"


def _neighbor_geometry(
    cell: dict[str, Any],
    center: tuple[float, float, float],
    east: tuple[float, float, float],
    north: tuple[float, float, float],
    cells_by_id: dict[int, dict[str, Any]],
) -> list[dict[str, float | int]]:
    records: list[dict[str, float | int]] = []
    for neighbor_id in cell.get("neighbors", []):
        neighbor = cells_by_id.get(int(neighbor_id))
        if neighbor is None:
            continue
        neighbor_xyz = _xyz_from_lat_lon(float(neighbor.get("lat_deg", 0.0)), float(neighbor.get("lon_deg", 0.0)))
        distance = _central_angle(center, neighbor_xyz)
        tangent = _add(neighbor_xyz, _scale(center, -_dot(neighbor_xyz, center)))
        tangent = _normalize(tangent)
        bearing = math.atan2(_dot(tangent, north), _dot(tangent, east))
        if bearing < 0.0:
            bearing += 2.0 * math.pi
        records.append({"neighbor_id": int(neighbor_id), "bearing": bearing, "distance": distance})
    return sorted(records, key=lambda item: float(item["bearing"]))


def _vertex_angles_from_bearings(bearings: list[float], fallback_count: int) -> list[float]:
    if len(bearings) < 3:
        return [2.0 * math.pi * index / fallback_count for index in range(fallback_count)]
    angles: list[float] = []
    for index, bearing in enumerate(bearings):
        next_bearing = bearings[(index + 1) % len(bearings)]
        if index == len(bearings) - 1:
            next_bearing += 2.0 * math.pi
        midpoint = (bearing + next_bearing) * 0.5
        if midpoint >= 2.0 * math.pi:
            midpoint -= 2.0 * math.pi
        angles.append(midpoint)
    return angles


def _target_radius_rad(area_km2: float, vertex_count: int, neighbor_distances: list[float]) -> float:
    vertex_count = max(3, vertex_count)
    planar_factor = max(0.001, vertex_count * math.sin(2.0 * math.pi / vertex_count))
    circumradius_km = math.sqrt(max(1.0, 2.0 * area_km2 / planar_factor))
    radius_rad = circumradius_km / EARTH_RADIUS_KM
    if neighbor_distances:
        sorted_distances = sorted(distance for distance in neighbor_distances if distance > 0.0)
        if sorted_distances:
            median_distance = sorted_distances[len(sorted_distances) // 2]
            radius_rad = min(radius_rad, median_distance * 0.58, sorted_distances[0] * 0.72)
    return _clamp(radius_rad, 0.0001, 0.35)


def _ring_points(
    center: tuple[float, float, float],
    east: tuple[float, float, float],
    north: tuple[float, float, float],
    vertex_angles: list[float],
    radius_rad: float,
) -> list[tuple[float, float, float]]:
    points: list[tuple[float, float, float]] = []
    for angle in vertex_angles:
        tangent = _add(_scale(east, math.cos(angle)), _scale(north, math.sin(angle)))
        point = _add(_scale(center, math.cos(radius_rad)), _scale(tangent, math.sin(radius_rad)))
        points.append(_normalize(point))
    return points


def _ring_perimeter_km(points: list[tuple[float, float, float]]) -> float:
    if len(points) < 2:
        return 0.0
    perimeter = 0.0
    for index, point in enumerate(points):
        perimeter += _central_angle(point, points[(index + 1) % len(points)]) * EARTH_RADIUS_KM
    return perimeter


def _ring_area_km2(center: tuple[float, float, float], points: list[tuple[float, float, float]]) -> float:
    if len(points) < 3:
        return 0.0
    area_steradians = 0.0
    for index, point in enumerate(points):
        area_steradians += _triangle_area_steradians(center, point, points[(index + 1) % len(points)])
    return area_steradians * EARTH_RADIUS_KM * EARTH_RADIUS_KM


def _segment_length_km(segment: tuple[tuple[float, float, float], tuple[float, float, float]] | None) -> float:
    if segment is None:
        return 0.0
    return _central_angle(segment[0], segment[1]) * EARTH_RADIUS_KM


def _fallback_boundary_segment(
    cell_a_xyz: tuple[float, float, float],
    cell_b_xyz: tuple[float, float, float],
) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    midpoint = _normalize(_add(cell_a_xyz, cell_b_xyz))
    tangent = _normalize(_cross(cell_a_xyz, cell_b_xyz))
    half_length_rad = _clamp(_central_angle(cell_a_xyz, cell_b_xyz) * 0.18, 0.0001, 0.08)
    return (
        _normalize(_add(_scale(midpoint, math.cos(half_length_rad)), _scale(tangent, math.sin(half_length_rad)))),
        _normalize(_add(_scale(midpoint, math.cos(half_length_rad)), _scale(tangent, -math.sin(half_length_rad)))),
    )


def _shared_boundary_segment(
    segment_a: tuple[tuple[float, float, float], tuple[float, float, float]] | None,
    segment_b: tuple[tuple[float, float, float], tuple[float, float, float]] | None,
    cell_a_xyz: tuple[float, float, float],
    cell_b_xyz: tuple[float, float, float],
) -> tuple[tuple[float, float, float], tuple[float, float, float], float]:
    if segment_a is None and segment_b is None:
        start, end = _fallback_boundary_segment(cell_a_xyz, cell_b_xyz)
        return start, end, 0.0
    if segment_a is None:
        return segment_b[0], segment_b[1], 0.0  # type: ignore[index]
    if segment_b is None:
        return segment_a[0], segment_a[1], 0.0

    same_orientation = _central_angle(segment_a[0], segment_b[0]) + _central_angle(segment_a[1], segment_b[1])
    reversed_orientation = _central_angle(segment_a[0], segment_b[1]) + _central_angle(segment_a[1], segment_b[0])
    if reversed_orientation < same_orientation:
        segment_b = (segment_b[1], segment_b[0])
        endpoint_mismatch_rad = reversed_orientation * 0.5
    else:
        endpoint_mismatch_rad = same_orientation * 0.5
    return (
        _normalize(_add(segment_a[0], segment_b[0])),
        _normalize(_add(segment_a[1], segment_b[1])),
        endpoint_mismatch_rad * EARTH_RADIUS_KM,
    )


def enrich_world_with_cell_geometry(world: dict[str, Any]) -> dict[str, Any]:
    cells = world.get("cells", [])
    if not isinstance(cells, list) or not cells:
        return world

    cells_by_id = {int(cell.get("id", index)): cell for index, cell in enumerate(cells)}
    total_area_km2 = 0.0
    total_polygon_area_km2 = 0.0
    total_perimeter_km = 0.0
    total_area_error = 0.0
    max_area_error = 0.0
    total_quality = 0.0
    total_vertices = 0
    ring_count = 0
    cell_neighbor_segments: dict[
        tuple[int, int],
        tuple[tuple[float, float, float], tuple[float, float, float]],
    ] = {}
    edge_accumulators: dict[int, dict[str, Any]] = {
        cell_id: {
            "edge_ids": [],
            "length_sum": 0.0,
            "max_length": 0.0,
            "boundary_length_sum": 0.0,
            "boundary_max_length": 0.0,
            "boundary_mismatch_sum": 0.0,
            "boundary_quality_sum": 0.0,
            "tectonic_count": 0,
            "land_water_count": 0,
            "biome_transition_count": 0,
        }
        for cell_id in cells_by_id
    }

    for cell in cells:
        lat_deg = float(cell.get("lat_deg", 0.0))
        lon_deg = float(cell.get("lon_deg", 0.0))
        center = _xyz_from_lat_lon(lat_deg, lon_deg)
        east, north = _local_basis(lat_deg, lon_deg)
        neighbor_records = _neighbor_geometry(cell, center, east, north, cells_by_id)
        bearings = [float(record["bearing"]) for record in neighbor_records]
        distances = [float(record["distance"]) for record in neighbor_records]
        vertex_angles = _vertex_angles_from_bearings(bearings, fallback_count=max(5, len(cell.get("neighbors", [])) or 6))
        area_km2 = max(1.0, float(cell.get("area_km2", 0.0)))
        radius_rad = _target_radius_rad(area_km2, len(vertex_angles), distances)
        ring_xyz = _ring_points(center, east, north, vertex_angles, radius_rad)
        boundary_ring = [[round(lat, 6), round(lon, 6)] for lat, lon in (_lat_lon_from_xyz(point) for point in ring_xyz)]
        polygon_area_km2 = _ring_area_km2(center, ring_xyz)
        perimeter_km = _ring_perimeter_km(ring_xyz)
        area_error_fraction = abs(polygon_area_km2 - area_km2) / area_km2 if area_km2 > 0.0 else 0.0
        compactness = _clamp(4.0 * math.pi * polygon_area_km2 / max(1.0, perimeter_km * perimeter_km), 0.0, 1.0)
        geometry_quality = _clamp((1.0 - min(1.0, area_error_fraction)) * 0.72 + compactness * 0.28, 0.0, 1.0)

        cell["boundary_ring"] = boundary_ring
        cell["boundary_vertex_count"] = len(boundary_ring)
        cell["cell_boundary_perimeter_km"] = round(perimeter_km, 6)
        cell["cell_polygon_area_km2"] = round(polygon_area_km2, 6)
        cell["cell_polygon_area_error_fraction"] = round(area_error_fraction, 6)
        cell["cell_geometry_quality"] = round(geometry_quality, 6)

        cell_id = int(cell.get("id", -1))
        if cell_id >= 0 and len(neighbor_records) >= 3 and len(ring_xyz) == len(neighbor_records):
            for index, record in enumerate(neighbor_records):
                neighbor_id = int(record["neighbor_id"])
                cell_neighbor_segments[(cell_id, neighbor_id)] = (ring_xyz[(index - 1) % len(ring_xyz)], ring_xyz[index])

        total_area_km2 += area_km2
        total_polygon_area_km2 += polygon_area_km2
        total_perimeter_km += perimeter_km
        total_area_error += area_error_fraction
        max_area_error = max(max_area_error, area_error_fraction)
        total_quality += geometry_quality
        total_vertices += len(boundary_ring)
        ring_count += 1

    adjacency_edges: list[dict[str, Any]] = []
    edge_class_counts: dict[str, int] = {}
    edge_length_sum = 0.0
    max_edge_length = 0.0
    boundary_segment_length_sum = 0.0
    max_boundary_segment_length = 0.0
    boundary_segment_mismatch_sum = 0.0
    boundary_segment_quality_sum = 0.0
    tectonic_edge_count = 0
    land_water_edge_count = 0
    biome_transition_edge_count = 0
    seen_edges: set[tuple[int, int]] = set()
    for cell in cells:
        cell_id = int(cell.get("id", -1))
        if cell_id < 0:
            continue
        cell_xyz = _xyz_from_lat_lon(float(cell.get("lat_deg", 0.0)), float(cell.get("lon_deg", 0.0)))
        cell_east, cell_north = _local_basis(float(cell.get("lat_deg", 0.0)), float(cell.get("lon_deg", 0.0)))
        for raw_neighbor_id in cell.get("neighbors", []):
            neighbor_id = int(raw_neighbor_id)
            neighbor = cells_by_id.get(neighbor_id)
            if neighbor is None:
                continue
            edge_key = (min(cell_id, neighbor_id), max(cell_id, neighbor_id))
            if edge_key in seen_edges or edge_key[0] == edge_key[1]:
                continue
            seen_edges.add(edge_key)
            neighbor_xyz = _xyz_from_lat_lon(float(neighbor.get("lat_deg", 0.0)), float(neighbor.get("lon_deg", 0.0)))
            neighbor_east, neighbor_north = _local_basis(float(neighbor.get("lat_deg", 0.0)), float(neighbor.get("lon_deg", 0.0)))
            edge_length_km = _central_angle(cell_xyz, neighbor_xyz) * EARTH_RADIUS_KM
            midpoint_lat, midpoint_lon = _lat_lon_from_xyz(_add(cell_xyz, neighbor_xyz))
            edge_type = _edge_class(cell, neighbor)
            elevation_delta = float(neighbor.get("elevation_m", 0.0)) - float(cell.get("elevation_m", 0.0))
            cell_a_xyz = cell_xyz if cell_id == edge_key[0] else neighbor_xyz
            cell_b_xyz = neighbor_xyz if cell_id == edge_key[0] else cell_xyz
            cell_a_segment = cell_neighbor_segments.get(edge_key)
            cell_b_segment = cell_neighbor_segments.get((edge_key[1], edge_key[0]))
            boundary_start, boundary_end, boundary_mismatch_km = _shared_boundary_segment(
                cell_a_segment,
                cell_b_segment,
                cell_a_xyz,
                cell_b_xyz,
            )
            boundary_segment_length_km = _central_angle(boundary_start, boundary_end) * EARTH_RADIUS_KM
            cell_a_segment_length_km = _segment_length_km(cell_a_segment)
            cell_b_segment_length_km = _segment_length_km(cell_b_segment)
            if cell_a_segment is None:
                cell_a_segment_length_km = boundary_segment_length_km
            if cell_b_segment is None:
                cell_b_segment_length_km = boundary_segment_length_km
            segment_length_ratio_error = abs(cell_a_segment_length_km - cell_b_segment_length_km) / max(
                1.0,
                cell_a_segment_length_km,
                cell_b_segment_length_km,
            )
            boundary_mismatch_ratio = boundary_mismatch_km / max(1.0, boundary_segment_length_km)
            boundary_segment_quality = _clamp(
                1.0 - min(1.0, boundary_mismatch_ratio) * 0.65 - min(1.0, segment_length_ratio_error) * 0.35,
                0.0,
                1.0,
            )
            boundary_start_lat, boundary_start_lon = _lat_lon_from_xyz(boundary_start)
            boundary_end_lat, boundary_end_lon = _lat_lon_from_xyz(boundary_end)
            edge_id = len(adjacency_edges)
            edge_record = {
                "id": edge_id,
                "cell_a_id": edge_key[0],
                "cell_b_id": edge_key[1],
                "edge_class": edge_type,
                "great_circle_distance_km": round(edge_length_km, 6),
                "midpoint_lat_deg": round(midpoint_lat, 6),
                "midpoint_lon_deg": round(midpoint_lon, 6),
                "bearing_a_to_b_deg": round(
                    _bearing_deg(cell_xyz, neighbor_xyz, cell_east, cell_north)
                    if cell_id == edge_key[0]
                    else _bearing_deg(neighbor_xyz, cell_xyz, neighbor_east, neighbor_north),
                    6,
                ),
                "bearing_b_to_a_deg": round(
                    _bearing_deg(neighbor_xyz, cell_xyz, neighbor_east, neighbor_north)
                    if cell_id == edge_key[0]
                    else _bearing_deg(cell_xyz, neighbor_xyz, cell_east, cell_north),
                    6,
                ),
                "elevation_delta_m": round(
                    elevation_delta if cell_id == edge_key[0] else -elevation_delta,
                    6,
                ),
                "plate_boundary": int(cell.get("plate_id", -1)) != int(neighbor.get("plate_id", -1)),
                "land_water_transition": bool(cell.get("is_water", False)) != bool(neighbor.get("is_water", False)),
                "biome_transition": str(cell.get("biome", "unknown")) != str(neighbor.get("biome", "unknown")),
                "boundary_segment_start_lat_deg": round(boundary_start_lat, 6),
                "boundary_segment_start_lon_deg": round(boundary_start_lon, 6),
                "boundary_segment_end_lat_deg": round(boundary_end_lat, 6),
                "boundary_segment_end_lon_deg": round(boundary_end_lon, 6),
                "boundary_segment_length_km": round(boundary_segment_length_km, 6),
                "cell_a_boundary_segment_length_km": round(cell_a_segment_length_km, 6),
                "cell_b_boundary_segment_length_km": round(cell_b_segment_length_km, 6),
                "boundary_segment_mismatch_km": round(boundary_mismatch_km, 6),
                "boundary_segment_quality": round(boundary_segment_quality, 6),
            }
            adjacency_edges.append(edge_record)
            edge_class_counts[edge_type] = edge_class_counts.get(edge_type, 0) + 1
            edge_length_sum += edge_length_km
            max_edge_length = max(max_edge_length, edge_length_km)
            boundary_segment_length_sum += boundary_segment_length_km
            max_boundary_segment_length = max(max_boundary_segment_length, boundary_segment_length_km)
            boundary_segment_mismatch_sum += boundary_mismatch_km
            boundary_segment_quality_sum += boundary_segment_quality
            if bool(edge_record["plate_boundary"]):
                tectonic_edge_count += 1
            if bool(edge_record["land_water_transition"]):
                land_water_edge_count += 1
            if bool(edge_record["biome_transition"]):
                biome_transition_edge_count += 1
            for endpoint_id in edge_key:
                accumulator = edge_accumulators.get(endpoint_id)
                if accumulator is None:
                    continue
                accumulator["edge_ids"].append(edge_id)
                accumulator["length_sum"] += edge_length_km
                accumulator["max_length"] = max(float(accumulator["max_length"]), edge_length_km)
                accumulator["boundary_length_sum"] += boundary_segment_length_km
                accumulator["boundary_max_length"] = max(float(accumulator["boundary_max_length"]), boundary_segment_length_km)
                accumulator["boundary_mismatch_sum"] += boundary_mismatch_km
                accumulator["boundary_quality_sum"] += boundary_segment_quality
                accumulator["tectonic_count"] += 1 if bool(edge_record["plate_boundary"]) else 0
                accumulator["land_water_count"] += 1 if bool(edge_record["land_water_transition"]) else 0
                accumulator["biome_transition_count"] += 1 if bool(edge_record["biome_transition"]) else 0

    for cell_id, cell in cells_by_id.items():
        accumulator = edge_accumulators.get(cell_id, {})
        edge_ids = list(accumulator.get("edge_ids", []))
        edge_count = len(edge_ids)
        cell["cell_adjacency_edge_ids"] = edge_ids
        cell["cell_edge_count"] = edge_count
        cell["mean_neighbor_edge_length_km"] = round(float(accumulator.get("length_sum", 0.0)) / edge_count, 6) if edge_count else 0.0
        cell["max_neighbor_edge_length_km"] = round(float(accumulator.get("max_length", 0.0)), 6)
        cell["mean_neighbor_boundary_segment_length_km"] = round(float(accumulator.get("boundary_length_sum", 0.0)) / edge_count, 6) if edge_count else 0.0
        cell["max_neighbor_boundary_segment_length_km"] = round(float(accumulator.get("boundary_max_length", 0.0)), 6)
        cell["mean_neighbor_boundary_segment_mismatch_km"] = round(float(accumulator.get("boundary_mismatch_sum", 0.0)) / edge_count, 6) if edge_count else 0.0
        cell["mean_neighbor_boundary_segment_quality"] = round(float(accumulator.get("boundary_quality_sum", 0.0)) / edge_count, 6) if edge_count else 0.0
        cell["tectonic_neighbor_edge_count"] = int(accumulator.get("tectonic_count", 0))
        cell["land_water_neighbor_edge_count"] = int(accumulator.get("land_water_count", 0))
        cell["biome_transition_neighbor_edge_count"] = int(accumulator.get("biome_transition_count", 0))

    world["cell_adjacency_edges"] = adjacency_edges
    summary = world.setdefault("summary", {})
    summary["cell_geometry_index"] = "approx_neighbor_bearing_v0"
    summary["cell_geometry_ring_count"] = ring_count
    summary["cell_geometry_total_area_km2"] = round(total_polygon_area_km2, 6)
    summary["cell_geometry_reference_area_km2"] = round(total_area_km2, 6)
    summary["cell_geometry_mean_vertex_count"] = round(total_vertices / ring_count, 6) if ring_count else 0.0
    summary["cell_geometry_mean_perimeter_km"] = round(total_perimeter_km / ring_count, 6) if ring_count else 0.0
    summary["cell_geometry_mean_area_error_fraction"] = round(total_area_error / ring_count, 6) if ring_count else 0.0
    summary["cell_geometry_max_area_error_fraction"] = round(max_area_error, 6)
    summary["cell_geometry_mean_quality"] = round(total_quality / ring_count, 6) if ring_count else 0.0
    edge_count = len(adjacency_edges)
    summary["cell_adjacency_edge_count"] = edge_count
    summary["mean_cell_adjacency_edge_length_km"] = round(edge_length_sum / edge_count, 6) if edge_count else 0.0
    summary["max_cell_adjacency_edge_length_km"] = round(max_edge_length, 6)
    summary["cell_boundary_segment_geometry"] = "approx_neighbor_sector_v0"
    summary["cell_boundary_segment_count"] = edge_count
    summary["mean_cell_boundary_segment_length_km"] = round(boundary_segment_length_sum / edge_count, 6) if edge_count else 0.0
    summary["max_cell_boundary_segment_length_km"] = round(max_boundary_segment_length, 6)
    summary["mean_cell_boundary_segment_mismatch_km"] = round(boundary_segment_mismatch_sum / edge_count, 6) if edge_count else 0.0
    summary["mean_cell_boundary_segment_quality"] = round(boundary_segment_quality_sum / edge_count, 6) if edge_count else 0.0
    summary["tectonic_adjacency_edge_count"] = tectonic_edge_count
    summary["land_water_adjacency_edge_count"] = land_water_edge_count
    summary["biome_transition_adjacency_edge_count"] = biome_transition_edge_count
    summary["cell_adjacency_edge_class_counts"] = dict(sorted(edge_class_counts.items()))
    return world
