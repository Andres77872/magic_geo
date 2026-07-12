from __future__ import annotations

import math
from collections import Counter, defaultdict
from typing import Any


CONTROL_VOLUME_AREA_MODELS = {
    "fibonacci_sphere": "spherical_voronoi_control_volume_v1",
    "geodesic_icosahedron": "spherical_barycentric_control_volume_v2",
}


Vector = tuple[float, float, float]
Segment = tuple[Vector, Vector]


def _vector(value: Any) -> Vector:
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError("expected a three-component vector")
    result = (float(value[0]), float(value[1]), float(value[2]))
    if not all(math.isfinite(component) for component in result):
        raise ValueError("vector components must be finite")
    return result


def _dot(first: Vector, second: Vector) -> float:
    return sum(left * right for left, right in zip(first, second))


def _cross(first: Vector, second: Vector) -> Vector:
    return (
        first[1] * second[2] - first[2] * second[1],
        first[2] * second[0] - first[0] * second[2],
        first[0] * second[1] - first[1] * second[0],
    )


def _norm(vector: Vector) -> float:
    return math.sqrt(_dot(vector, vector))


def _distance(first: Vector, second: Vector) -> float:
    return math.sqrt(
        sum((left - right) ** 2 for left, right in zip(first, second))
    )


def _triangle_area_steradians(first: Vector, second: Vector, third: Vector) -> float:
    numerator = abs(_dot(first, _cross(second, third)))
    denominator = (
        1.0
        + _dot(first, second)
        + _dot(second, third)
        + _dot(third, first)
    )
    return 2.0 * math.atan2(numerator, denominator)


def inspect_control_volume_geometry(world: dict[str, Any]) -> dict[str, Any]:
    """Replay native spherical control volumes and reciprocal edge topology."""

    failures: list[str] = []
    mesh_backend = str(world.get("mesh_backend", ""))
    area_model = str(world.get("cell_area_model", ""))
    expected_model = CONTROL_VOLUME_AREA_MODELS.get(mesh_backend)
    if area_model != expected_model:
        failures.append("mesh backend and control-volume area model do not match")

    cells_payload = world.get("cells", [])
    if not isinstance(cells_payload, list) or not cells_payload:
        return {
            "passed": False,
            "failures": failures + ["cells are missing"],
            "metrics": {},
        }

    try:
        radius_km = float(world.get("planet_parameters", {}).get("radius_km"))
    except (TypeError, ValueError):
        radius_km = math.nan
    if not math.isfinite(radius_km) or radius_km <= 0.0:
        failures.append("planet radius is invalid")

    cells_by_id: dict[int, dict[str, Any]] = {}
    positions: dict[int, Vector] = {}
    polygons: dict[int, list[Vector]] = {}
    edge_neighbors: dict[int, list[int]] = {}
    replayed_areas: dict[int, float] = {}
    directed_segments: dict[tuple[int, int], list[Segment]] = defaultdict(list)
    vertex_incidence: Counter[tuple[float, float, float]] = Counter()
    invalid_cell_geometry = False
    maximum_area_error_km2 = 0.0
    maximum_unit_norm_error = 0.0
    clockwise_edge_count = 0

    for index, cell in enumerate(cells_payload):
        if not isinstance(cell, dict):
            invalid_cell_geometry = True
            break
        try:
            cell_id = int(cell.get("id", -1))
            position = _vector(cell.get("position_3d"))
            vertices_payload = cell.get("control_volume_vertices_3d")
            neighbors_payload = cell.get("control_volume_edge_neighbor_ids")
            emitted_area_km2 = float(cell.get("area_km2", math.nan))
            if (
                cell_id != index
                or cell_id in cells_by_id
                or not isinstance(vertices_payload, list)
                or not isinstance(neighbors_payload, list)
                or len(vertices_payload) < 3
                or len(vertices_payload) != len(neighbors_payload)
                or not math.isfinite(emitted_area_km2)
                or emitted_area_km2 <= 0.0
            ):
                raise ValueError("invalid control-volume cell fields")
            vertices = [_vector(vertex) for vertex in vertices_payload]
            neighbors = [int(neighbor_id) for neighbor_id in neighbors_payload]
        except (TypeError, ValueError, OverflowError):
            invalid_cell_geometry = True
            break

        position_norm_error = abs(_norm(position) - 1.0)
        vertex_norm_error = max(abs(_norm(vertex) - 1.0) for vertex in vertices)
        maximum_unit_norm_error = max(
            maximum_unit_norm_error,
            position_norm_error,
            vertex_norm_error,
        )
        if maximum_unit_norm_error > 5.0e-9:
            invalid_cell_geometry = True
            break

        area_steradians = math.fsum(
            _triangle_area_steradians(
                position,
                vertices[vertex_index],
                vertices[(vertex_index + 1) % len(vertices)],
            )
            for vertex_index in range(len(vertices))
        )
        replayed_area_km2 = area_steradians * radius_km * radius_km
        area_error_km2 = abs(replayed_area_km2 - emitted_area_km2)
        maximum_area_error_km2 = max(maximum_area_error_km2, area_error_km2)
        if area_error_km2 > max(0.001, emitted_area_km2 * 2.0e-9):
            invalid_cell_geometry = True
            break

        cells_by_id[cell_id] = cell
        positions[cell_id] = position
        polygons[cell_id] = vertices
        edge_neighbors[cell_id] = neighbors
        replayed_areas[cell_id] = replayed_area_km2
        for vertex in vertices:
            vertex_incidence[tuple(round(component, 10) for component in vertex)] += 1
        for edge_index, neighbor_id in enumerate(neighbors):
            start = vertices[edge_index]
            end = vertices[(edge_index + 1) % len(vertices)]
            directed_segments[(cell_id, neighbor_id)].append((start, end))
            if _dot(position, _cross(start, end)) < -2.0e-12:
                clockwise_edge_count += 1

    if invalid_cell_geometry or len(cells_by_id) != len(cells_payload):
        failures.append("per-cell control-volume geometry is invalid")
    if clockwise_edge_count:
        failures.append("control-volume vertices are not counter-clockwise")

    invalid_edge_neighbor = False
    maximum_bisector_error = 0.0
    maximum_nearest_site_violation = 0.0
    maximum_shared_endpoint_error = 0.0
    unmatched_segment_count = 0
    for (cell_id, neighbor_id), segments in directed_segments.items():
        if (
            neighbor_id not in cells_by_id
            or neighbor_id == cell_id
            or (neighbor_id, cell_id) not in directed_segments
        ):
            invalid_edge_neighbor = True
            continue
        if len(segments) != len(directed_segments[(neighbor_id, cell_id)]):
            invalid_edge_neighbor = True
        if mesh_backend == "fibonacci_sphere":
            position = positions[cell_id]
            neighbor_position = positions[neighbor_id]
            for start, end in segments:
                maximum_bisector_error = max(
                    maximum_bisector_error,
                    abs(_dot(start, position) - _dot(start, neighbor_position)),
                    abs(_dot(end, position) - _dot(end, neighbor_position)),
                )
        reverse_segments = directed_segments[(neighbor_id, cell_id)]
        for start, end in segments:
            endpoint_error = min(
                _distance(start, reverse_end) + _distance(end, reverse_start)
                for reverse_start, reverse_end in reverse_segments
            )
            maximum_shared_endpoint_error = max(
                maximum_shared_endpoint_error, endpoint_error
            )
            if endpoint_error > 5.0e-9:
                unmatched_segment_count += 1
    if invalid_edge_neighbor:
        failures.append("control-volume edge-neighbor topology is invalid")
    if unmatched_segment_count:
        failures.append("reciprocal control-volume edge endpoints do not match")
    if mesh_backend == "fibonacci_sphere" and maximum_bisector_error > 2.0e-9:
        failures.append("Fibonacci control-volume edges are not Voronoi bisectors")
    if mesh_backend == "fibonacci_sphere" and len(cells_by_id) <= 512:
        for cell_id, vertices in polygons.items():
            owner = positions[cell_id]
            for vertex in vertices:
                owner_score = _dot(vertex, owner)
                nearest_score = max(
                    _dot(vertex, candidate) for candidate in positions.values()
                )
                maximum_nearest_site_violation = max(
                    maximum_nearest_site_violation,
                    nearest_score - owner_score,
                )
        if maximum_nearest_site_violation > 2.0e-9:
            failures.append(
                "Fibonacci control-volume vertex is outside its nearest-site cell"
            )

    undirected_edges = {
        (min(cell_id, neighbor_id), max(cell_id, neighbor_id))
        for cell_id, neighbor_id in directed_segments
    }
    topology_invalid = False
    if mesh_backend == "fibonacci_sphere" and len(cells_by_id) == len(cells_payload):
        expected_edge_count = 3 * len(cells_payload) - 6
        expected_vertex_count = 2 * len(cells_payload) - 4
        topology_invalid = (
            len(undirected_edges) != expected_edge_count
            or len(vertex_incidence) != expected_vertex_count
            or any(count != 3 for count in vertex_incidence.values())
            or any(
                len(neighbors) != len(set(neighbors))
                for neighbors in edge_neighbors.values()
            )
        )
    elif mesh_backend == "geodesic_icosahedron" and len(cells_by_id) == len(cells_payload):
        for cell_id, cell in cells_by_id.items():
            primal_neighbors = {int(value) for value in cell.get("neighbors", [])}
            counts = Counter(edge_neighbors[cell_id])
            if set(counts) != primal_neighbors or any(count != 2 for count in counts.values()):
                topology_invalid = True
                break
    if topology_invalid:
        failures.append("control-volume topology does not match its declared mesh model")

    emitted_total_area_km2 = math.fsum(
        float(cell.get("area_km2", 0.0)) for cell in cells_by_id.values()
    )
    replayed_total_area_km2 = math.fsum(replayed_areas.values())
    expected_total_area_km2 = 4.0 * math.pi * radius_km * radius_km
    surface_closure_error_km2 = abs(emitted_total_area_km2 - expected_total_area_km2)
    replay_closure_error_km2 = abs(replayed_total_area_km2 - expected_total_area_km2)
    if (
        not math.isfinite(expected_total_area_km2)
        or surface_closure_error_km2 > max(0.01, expected_total_area_km2 * 2.0e-10)
        or replay_closure_error_km2 > max(0.01, expected_total_area_km2 * 2.0e-9)
    ):
        failures.append("control-volume areas do not close to the spherical surface")

    return {
        "passed": not failures,
        "failures": failures,
        "metrics": {
            "cell_count": len(cells_payload),
            "control_volume_vertex_count": sum(len(value) for value in polygons.values()),
            "control_volume_segment_count": sum(
                len(value) for value in directed_segments.values()
            ) // 2,
            "control_volume_edge_pair_count": len(undirected_edges),
            "maximum_area_replay_error_km2": maximum_area_error_km2,
            "surface_closure_error_km2": surface_closure_error_km2,
            "replayed_surface_closure_error_km2": replay_closure_error_km2,
            "maximum_unit_norm_error": maximum_unit_norm_error,
            "maximum_voronoi_bisector_error": maximum_bisector_error,
            "maximum_nearest_site_violation": maximum_nearest_site_violation,
            "maximum_shared_endpoint_error": maximum_shared_endpoint_error,
        },
    }
