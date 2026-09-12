from __future__ import annotations

import copy
import math
from collections import defaultdict
from typing import Any


TERRITORIAL_SNAPSHOT_MODEL = "causal_era_scaled_spherical_region_territorial_snapshots_v1"
AREA_FACTORS = (0.48, 0.78, 0.64, 1.0)
POPULATION_FACTORS = (0.34, 0.58, 0.74, 1.0)
Vector = tuple[float, float, float]


def _model() -> dict[str, Any]:
    return {
        "model_type": TERRITORIAL_SNAPSHOT_MODEL,
        "deterministic": True,
        "base_membership_model": "nonwater_political_region_cells_v1",
        "boundary_cell_model": "water_or_other_region_neighbor_v1",
        "centroid_model": "area_weighted_lat_lon_and_cartesian_center_v1",
        "boundary_ring_model": "tangent_plane_angle_sort_uniform_floor_sample_closed_ring_v1",
        "maximum_boundary_ring_points_before_closure": 64,
        "boundary_cell_sample_model": "record_order_uniform_floor_sample_v1",
        "maximum_boundary_cell_ids": 64,
        "perimeter_model": "great_circle_closed_ring_length_v1",
        "dissolved_area_model": "centered_orthographic_shoelace_proxy_v1",
        "era_area_factors": list(AREA_FACTORS),
        "era_population_factors": list(POPULATION_FACTORS),
        "stability_model": "culture_continuity_conflict_and_era_connectivity_v1",
        "fragmentation_model": "largest_area_share_and_mean_region_conflict_v1",
        "model_limitation": "scaled_static_regions_with_sampled_centroid_ordered_rings_not_exact_dynamic_cell_edge_territories",
    }


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _close(actual: Any, expected: float, tolerance: float) -> bool:
    try:
        return abs(float(actual) - expected) <= tolerance
    except (TypeError, ValueError):
        return False


def _relative_close(actual: Any, expected: float, fraction: float = 0.001) -> bool:
    return _close(actual, expected, max(0.5, abs(expected) * fraction))


def _add(first: Vector, second: Vector) -> Vector:
    return (first[0] + second[0], first[1] + second[1], first[2] + second[2])


def _mul(vector: Vector, scalar: float) -> Vector:
    return (vector[0] * scalar, vector[1] * scalar, vector[2] * scalar)


def _dot(first: Vector, second: Vector) -> float:
    return first[0] * second[0] + first[1] * second[1] + first[2] * second[2]


def _cross(first: Vector, second: Vector) -> Vector:
    return (
        first[1] * second[2] - first[2] * second[1],
        first[2] * second[0] - first[0] * second[2],
        first[0] * second[1] - first[1] * second[0],
    )


def _normalize(vector: Vector) -> Vector:
    length = math.sqrt(_dot(vector, vector))
    return _mul(vector, 1.0 / length) if length > 0.0 else (0.0, 0.0, 0.0)


def _position(cell: dict[str, Any]) -> Vector:
    values = cell.get("position_3d", [])
    if not isinstance(values, list) or len(values) != 3:
        raise ValueError("cell position missing")
    return (float(values[0]), float(values[1]), float(values[2]))


def _axes(weighted_center: Vector) -> tuple[Vector, Vector, Vector]:
    center = _normalize(weighted_center)
    reference = (0.0, 0.0, 1.0) if abs(center[2]) < 0.92 else (0.0, 1.0, 0.0)
    axis_x = _normalize(_cross(reference, center))
    return center, axis_x, _normalize(_cross(center, axis_x))


def _boundary_ring(
    cells_by_id: dict[int, dict[str, Any]],
    boundary_cell_ids: list[int],
    weighted_center: Vector,
) -> list[list[float]]:
    if not boundary_cell_ids:
        return []
    _, axis_x, axis_y = _axes(weighted_center)
    ordered = sorted(
        (
            math.atan2(
                _dot(_position(cells_by_id[cell_id]), axis_y),
                _dot(_position(cells_by_id[cell_id]), axis_x),
            ),
            cell_id,
        )
        for cell_id in boundary_cell_ids
    )
    target = min(64, len(ordered))
    ring: list[list[float]] = []
    for index in range(target):
        ordered_index = math.floor(index * len(ordered) / target)
        cell = cells_by_id[ordered[ordered_index][1]]
        ring.append([float(cell.get("lat_deg", 0.0)), float(cell.get("lon_deg", 0.0))])
    if len(ring) > 2:
        ring.append(ring[0][:])
    return ring


def _latlon_position(point: list[float]) -> Vector:
    latitude = math.radians(float(point[0]))
    longitude = math.radians(float(point[1]))
    cosine = math.cos(latitude)
    return (cosine * math.cos(longitude), cosine * math.sin(longitude), math.sin(latitude))


def _perimeter(ring: list[list[float]], radius_km: float) -> float:
    total = 0.0
    for index in range(1, len(ring)):
        first = _latlon_position(ring[index - 1])
        second = _latlon_position(ring[index])
        total += math.acos(_clamp(_dot(first, second), -1.0, 1.0)) * radius_km
    return total


def _projected_area(ring: list[list[float]], weighted_center: Vector, radius_km: float) -> float:
    if len(ring) < 4:
        return 0.0
    _, axis_x, axis_y = _axes(weighted_center)
    points = [
        (
            radius_km * _dot(_latlon_position(point), axis_x),
            radius_km * _dot(_latlon_position(point), axis_y),
        )
        for point in ring
    ]
    area = sum(
        points[index - 1][0] * points[index][1] - points[index][0] * points[index - 1][1]
        for index in range(1, len(points))
    )
    return abs(0.5 * area)


def _sample_ids(values: list[int]) -> list[int]:
    if len(values) <= 64:
        return values[:]
    stride = len(values) / 64.0
    return [values[math.floor(stride * index)] for index in range(64)]


def _base_regions(payload: dict[str, Any], *, radius_km: float | None = None) -> tuple[list[dict[str, Any]], float]:
    cells = payload["cells"]
    regions = payload["political_regions"]
    settlements = payload["settlements"]
    cultures = payload["cultures"]
    cells_by_id = {int(cell["id"]): cell for cell in cells}
    region_to_culture = {
        int(culture.get("homeland_region_id", -1)): int(culture["id"])
        for culture in cultures
        if int(culture.get("homeland_region_id", -1)) >= 0
    }
    bases = [
        {
            "region_id": int(region["id"]),
            "capital_settlement_id": int(region.get("capital_settlement_id", -1)),
            "culture_region_id": -1,
            "language_region_id": -1,
            "cell_count": 0,
            "area_km2": 0.0,
            "estimated_population": 0.0,
            "stability_index": 0.0,
            "centroid_lat_deg": 0.0,
            "centroid_lon_deg": 0.0,
            "crosses_antimeridian": False,
            "boundary_perimeter_km": 0.0,
            "dissolved_polygon_area_km2": 0.0,
            "polygon_area_error_fraction": 0.0,
            "compactness_index": 0.0,
            "geometry_quality": 0.0,
            "boundary_cell_ids": [],
            "boundary_ring": [],
        }
        for region in regions
    ]
    centers: list[Vector] = [(0.0, 0.0, 0.0) for _ in regions]
    latitude_weights = [0.0 for _ in regions]
    longitude_weights = [0.0 for _ in regions]
    area_weights = [0.0 for _ in regions]
    for region in regions:
        region_id = int(region["id"])
        culture_id = region_to_culture.get(region_id, -1)
        if 0 <= culture_id < len(cultures):
            bases[region_id]["culture_region_id"] = culture_id
            bases[region_id]["language_region_id"] = int(cultures[culture_id].get("language_region_id", -1))

    land_area = 0.0
    for cell in cells:
        if bool(cell.get("is_water", False)):
            continue
        cell_area = float(cell.get("area_km2", 0.0))
        land_area += cell_area
        region_id = int(cell.get("political_region_id", -1))
        if not 0 <= region_id < len(bases):
            continue
        base = bases[region_id]
        base["cell_count"] += 1
        base["area_km2"] += cell_area
        centers[region_id] = _add(centers[region_id], _mul(_position(cell), cell_area))
        latitude_weights[region_id] += float(cell.get("lat_deg", 0.0)) * cell_area
        longitude_weights[region_id] += float(cell.get("lon_deg", 0.0)) * cell_area
        area_weights[region_id] += cell_area
        if any(
            bool(cells_by_id[int(neighbor_id)].get("is_water", False))
            or int(cells_by_id[int(neighbor_id)].get("political_region_id", -1)) != region_id
            for neighbor_id in cell.get("neighbors", [])
        ):
            base["boundary_cell_ids"].append(int(cell["id"]))

    if radius_km is None:
        radius_km = math.sqrt(float(payload["summary"].get("surface_area_km2", 0.0)) / (4.0 * math.pi))
    for base in bases:
        region_id = int(base["region_id"])
        if area_weights[region_id] > 0.0:
            base["centroid_lat_deg"] = latitude_weights[region_id] / area_weights[region_id]
            base["centroid_lon_deg"] = longitude_weights[region_id] / area_weights[region_id]
        else:
            capital_id = int(regions[region_id].get("capital_settlement_id", -1))
            if 0 <= capital_id < len(settlements):
                capital_cell = cells_by_id[int(settlements[capital_id].get("cell_id", -1))]
                base["centroid_lat_deg"] = float(capital_cell.get("lat_deg", 0.0))
                base["centroid_lon_deg"] = float(capital_cell.get("lon_deg", 0.0))
        boundary_ids = [int(value) for value in base["boundary_cell_ids"]]
        ring = _boundary_ring(cells_by_id, boundary_ids, centers[region_id])
        base["boundary_ring"] = ring
        base["boundary_perimeter_km"] = _perimeter(ring, radius_km)
        base["dissolved_polygon_area_km2"] = _projected_area(ring, centers[region_id], radius_km)
        if float(base["area_km2"]) > 0.0 and float(base["dissolved_polygon_area_km2"]) > 0.0:
            base["polygon_area_error_fraction"] = abs(
                float(base["dissolved_polygon_area_km2"]) - float(base["area_km2"])
            ) / float(base["area_km2"])
        if float(base["boundary_perimeter_km"]) > 0.0 and float(base["dissolved_polygon_area_km2"]) > 0.0:
            base["compactness_index"] = _clamp(
                4.0 * math.pi * float(base["dissolved_polygon_area_km2"])
                / max(1.0, float(base["boundary_perimeter_km"]) ** 2)
            )
        if ring:
            longitudes = [float(point[1]) for point in ring]
            base["crosses_antimeridian"] = max(longitudes) - min(longitudes) > 180.0
        ring_quality = _clamp(len(ring) / 24.0)
        area_quality = _clamp(1.0 - float(base["polygon_area_error_fraction"]))
        base["geometry_quality"] = _clamp(0.62 * area_quality + 0.38 * ring_quality)
        base["boundary_cell_ids"] = _sample_ids(boundary_ids)
    return bases, land_area


def _replay_snapshots(payload: dict[str, Any]) -> list[dict[str, Any]]:
    eras = payload["historical_eras"]
    cultures = payload["cultures"]
    populations_by_region = {
        int(population["region_id"]): population for population in payload["population_regions"]
    }
    conflict_by_region_era: defaultdict[tuple[int, int], float] = defaultdict(float)
    for conflict in payload["conflicts"]:
        era_id = int(conflict["era_id"])
        conflict_by_region_era[(int(conflict["region_a"]), era_id)] += float(conflict["intensity"])
        conflict_by_region_era[(int(conflict["region_b"]), era_id)] += float(conflict["intensity"])
    bases, land_area = _base_regions(payload)
    snapshots: list[dict[str, Any]] = []
    for era in eras:
        era_id = int(era["id"])
        snapshot: dict[str, Any] = {
            "id": len(snapshots),
            "era_id": era_id,
            "dominant_process": str(era.get("dominant_process", "founding")),
            "region_count": 0,
            "largest_region_id": -1,
            "regions": [],
            "year_bp": 0.5 * (float(era.get("start_year_bp", 0.0)) + float(era.get("end_year_bp", 0.0))),
            "assigned_land_fraction": 0.0,
            "estimated_population": 0.0,
            "largest_region_area_km2": 0.0,
            "fragmentation_index": 0.0,
        }
        conflict_sum = 0.0
        for original_base in bases:
            base = copy.deepcopy(original_base)
            region_id = int(base["region_id"])
            if region_id < 0 or int(base["cell_count"]) == 0:
                continue
            regional_conflict = _clamp(conflict_by_region_era[(region_id, era_id)] / 2.0)
            culture_id = int(base["culture_region_id"])
            continuity = (
                float(cultures[culture_id].get("continuity_index", 0.5))
                if 0 <= culture_id < len(cultures)
                else 0.5
            )
            stability = _clamp(
                0.42
                + 0.42 * continuity
                - 0.30 * regional_conflict
                + 0.10 * float(era.get("mean_connectivity", 0.0))
            )
            factor_index = max(0, min(3, era_id))
            region_area_factor = AREA_FACTORS[factor_index] * (0.82 + 0.18 * stability)
            base["area_km2"] *= region_area_factor
            base["dissolved_polygon_area_km2"] *= region_area_factor
            base["boundary_perimeter_km"] *= math.sqrt(region_area_factor)
            if float(base["area_km2"]) > 0.0 and float(base["dissolved_polygon_area_km2"]) > 0.0:
                base["polygon_area_error_fraction"] = abs(
                    float(base["dissolved_polygon_area_km2"]) - float(base["area_km2"])
                ) / float(base["area_km2"])
            if float(base["boundary_perimeter_km"]) > 0.0 and float(base["dissolved_polygon_area_km2"]) > 0.0:
                base["compactness_index"] = _clamp(
                    4.0 * math.pi * float(base["dissolved_polygon_area_km2"])
                    / max(1.0, float(base["boundary_perimeter_km"]) ** 2)
                )
            ring_quality = _clamp(len(base["boundary_ring"]) / 24.0)
            area_quality = _clamp(1.0 - float(base["polygon_area_error_fraction"]))
            base["geometry_quality"] = _clamp(0.62 * area_quality + 0.38 * ring_quality)
            population = populations_by_region.get(region_id)
            base["estimated_population"] = (
                float(population.get("estimated_population", 0.0)) if population is not None else 0.0
            ) * POPULATION_FACTORS[factor_index] * (0.82 + 0.22 * stability)
            base["stability_index"] = stability
            snapshot["estimated_population"] += float(base["estimated_population"])
            snapshot["assigned_land_fraction"] += float(base["area_km2"])
            if float(base["area_km2"]) > float(snapshot["largest_region_area_km2"]):
                snapshot["largest_region_area_km2"] = float(base["area_km2"])
                snapshot["largest_region_id"] = region_id
            conflict_sum += regional_conflict
            snapshot["regions"].append(base)
        snapshot["region_count"] = len(snapshot["regions"])
        snapshot["assigned_land_fraction"] = (
            _clamp(float(snapshot["assigned_land_fraction"]) / land_area) if land_area > 0.0 else 0.0
        )
        largest_share = (
            float(snapshot["largest_region_area_km2"])
            / (float(snapshot["assigned_land_fraction"]) * land_area)
            if float(snapshot["assigned_land_fraction"]) > 0.0 and land_area > 0.0
            else 0.0
        )
        snapshot["fragmentation_index"] = _clamp(
            (1.0 - largest_share if int(snapshot["region_count"]) > 1 else 0.0) * 0.72
            + (conflict_sum / int(snapshot["region_count"]) if int(snapshot["region_count"]) > 0 else 0.0) * 0.28
        )
        snapshots.append(snapshot)
    return snapshots


def _ring_matches(actual: Any, expected: list[list[float]]) -> bool:
    return (
        isinstance(actual, list)
        and len(actual) == len(expected)
        and all(
            isinstance(point, list)
            and len(point) == 2
            and _close(point[0], expected_point[0], 0.0002)
            and _close(point[1], expected_point[1], 0.0002)
            for point, expected_point in zip(actual, expected, strict=True)
        )
    )


def _region_matches(actual: dict[str, Any], expected: dict[str, Any]) -> bool:
    exact_keys = (
        "region_id",
        "capital_settlement_id",
        "culture_region_id",
        "language_region_id",
        "cell_count",
        "crosses_antimeridian",
        "boundary_cell_ids",
    )
    if any(actual.get(key) != expected[key] for key in exact_keys):
        return False
    if not _ring_matches(actual.get("boundary_ring"), expected["boundary_ring"]):
        return False
    for key in ("area_km2", "boundary_perimeter_km", "dissolved_polygon_area_km2", "estimated_population"):
        if not _relative_close(actual.get(key), float(expected[key])):
            return False
    return all(
        _close(actual.get(key), float(expected[key]), tolerance)
        for key, tolerance in (
            ("polygon_area_error_fraction", 0.003),
            ("compactness_index", 0.003),
            ("geometry_quality", 0.003),
            ("stability_index", 0.003),
            ("centroid_lat_deg", 0.001),
            ("centroid_lon_deg", 0.001),
        )
    )


def _snapshot_matches(actual: dict[str, Any], expected: dict[str, Any]) -> bool:
    exact_keys = ("id", "era_id", "dominant_process", "region_count", "largest_region_id")
    if any(actual.get(key) != expected[key] for key in exact_keys):
        return False
    actual_regions = actual.get("regions", [])
    expected_regions = expected["regions"]
    if not isinstance(actual_regions, list) or len(actual_regions) != len(expected_regions):
        return False
    if any(
        not _region_matches(actual_region, expected_region)
        for actual_region, expected_region in zip(actual_regions, expected_regions, strict=True)
    ):
        return False
    if not all(
        _close(actual.get(key), float(expected[key]), tolerance)
        for key, tolerance in (
            ("year_bp", 0.001),
            ("assigned_land_fraction", 0.003),
            ("fragmentation_index", 0.003),
        )
    ):
        return False
    return _relative_close(actual.get("estimated_population"), float(expected["estimated_population"])) and _relative_close(
        actual.get("largest_region_area_km2"), float(expected["largest_region_area_km2"])
    )


def _replay_valid(payload: dict[str, Any]) -> bool:
    summary = payload.get("summary", {})
    collection_names = (
        "cells",
        "political_regions",
        "settlements",
        "cultures",
        "historical_eras",
        "population_regions",
        "conflicts",
        "territorial_snapshots",
    )
    collections = [payload.get(name, []) for name in collection_names]
    if not isinstance(summary, dict) or not all(isinstance(value, list) for value in collections):
        return False
    if not all(all(isinstance(record, dict) for record in records) for records in collections):
        return False
    if (
        payload.get("territorial_snapshot_model") != _model()
        or summary.get("territorial_snapshot_model") != TERRITORIAL_SNAPSHOT_MODEL
    ):
        return False
    snapshots = _replay_snapshots(payload)
    actual_snapshots = payload["territorial_snapshots"]
    if len(actual_snapshots) != len(snapshots) or any(
        not _snapshot_matches(actual, expected)
        for actual, expected in zip(actual_snapshots, snapshots, strict=True)
    ):
        return False
    regions = [region for snapshot in snapshots for region in snapshot["regions"]]
    polygon_regions = [region for region in regions if float(region["dissolved_polygon_area_km2"]) > 0.0]
    expected_counts = {
        "territorial_snapshot_count": len(snapshots),
        "snapshot_region_record_count": len(regions),
        "snapshot_polygon_region_count": len(polygon_regions),
    }
    if any(int(summary.get(key, -1)) != value for key, value in expected_counts.items()):
        return False
    expected_means = {
        "mean_snapshot_fragmentation_index": (
            sum(float(snapshot["fragmentation_index"]) for snapshot in snapshots) / len(snapshots)
            if snapshots
            else 0.0
        ),
        "mean_snapshot_polygon_area_error_fraction": (
            sum(float(region["polygon_area_error_fraction"]) for region in polygon_regions) / len(polygon_regions)
            if polygon_regions
            else 0.0
        ),
        "mean_snapshot_compactness_index": (
            sum(float(region["compactness_index"]) for region in polygon_regions) / len(polygon_regions)
            if polygon_regions
            else 0.0
        ),
        "mean_snapshot_geometry_quality": (
            sum(float(region["geometry_quality"]) for region in polygon_regions) / len(polygon_regions)
            if polygon_regions
            else 0.0
        ),
        "mean_snapshot_boundary_perimeter_km": (
            sum(float(region["boundary_perimeter_km"]) for region in polygon_regions) / len(polygon_regions)
            if polygon_regions
            else 0.0
        ),
    }
    return all(
        _relative_close(summary.get(key), value) if "perimeter_km" in key else _close(summary.get(key), value, 0.004)
        for key, value in expected_means.items()
    )


def validate_territorial_geography_replay(payload: dict[str, Any]) -> list[str]:
    try:
        from .native_social_availability import uses_native_social_availability
        if uses_native_social_availability(payload):
            from .native_territorial_availability_validation import validate_native_territorial_availability
            return validate_native_territorial_availability(payload)
        valid = _replay_valid(payload)
    except (IndexError, KeyError, TypeError, ValueError, ZeroDivisionError):
        valid = False
    return [] if valid else ["territorial snapshot model or causal replay invalid"]
