"""Coercion, geometry, and statistics helpers shared by the readers."""

from __future__ import annotations

import hashlib
import heapq
import math
from datetime import date
from pathlib import Path
from typing import Any

from bisect import bisect_left

from ._constants import _SHA256_PATTERN, _SOURCE_PROVENANCE_FIELDS
from .errors import CalibrationError


def _target_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        payload = payload.get("targets")
    if not isinstance(payload, list):
        raise CalibrationError("calibration targets must be a list or an object with a 'targets' list")
    for item in payload:
        if not isinstance(item, dict):
            raise CalibrationError("each calibration target must be an object")
    return payload


def _source_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        payload = payload.get("sources")
    if not isinstance(payload, list):
        raise CalibrationError("calibration sources must be a list or an object with a 'sources' list")
    for item in payload:
        if not isinstance(item, dict):
            raise CalibrationError("each calibration source must be an object")
    return payload


def _target_float(target: dict[str, Any], key: str) -> float:
    try:
        value = float(target[key])
    except KeyError as exc:
        raise CalibrationError(f"calibration target missing '{key}'") from exc
    except (TypeError, ValueError) as exc:
        raise CalibrationError(f"calibration target '{key}' must be numeric") from exc
    if not math.isfinite(value):
        raise CalibrationError(f"calibration target '{key}' must be finite")
    return value


def _target_text(target: dict[str, Any], key: str) -> str:
    value = target.get(key)
    if not isinstance(value, str) or not value:
        raise CalibrationError(f"calibration target missing '{key}'")
    return value


def _optional_float(payload: dict[str, Any], key: str, default: float) -> float:
    if key not in payload:
        return default
    try:
        value = float(payload[key])
    except (TypeError, ValueError) as exc:
        raise CalibrationError(f"calibration source '{key}' must be numeric") from exc
    if not math.isfinite(value):
        raise CalibrationError(f"calibration source '{key}' must be finite")
    return value


def _optional_int(payload: dict[str, Any], key: str, default: int) -> int:
    raw = payload.get(key, default)
    if isinstance(raw, bool):
        raise CalibrationError(f"calibration source '{key}' must be an integer")
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise CalibrationError(f"calibration source '{key}' must be an integer") from exc
    if isinstance(raw, float) and not raw.is_integer():
        raise CalibrationError(f"calibration source '{key}' must be an integer")
    if isinstance(raw, str) and str(value) != raw.strip():
        raise CalibrationError(f"calibration source '{key}' must be an integer")
    return value


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source_file:
        for chunk in iter(lambda: source_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_provenance(path: Path, source: dict[str, Any]) -> dict[str, str]:
    actual_sha256 = _file_sha256(path)
    expected_sha256 = source.get("source_sha256")
    if expected_sha256 is not None:
        if not isinstance(expected_sha256, str) or not _SHA256_PATTERN.fullmatch(expected_sha256):
            raise CalibrationError("calibration source 'source_sha256' must be a 64-character hexadecimal digest")
        if actual_sha256 != expected_sha256.lower():
            raise CalibrationError(
                f"calibration source SHA-256 mismatch for {path}: expected {expected_sha256.lower()}, "
                f"got {actual_sha256}"
            )

    metadata = {"source_sha256": actual_sha256}
    for key in _SOURCE_PROVENANCE_FIELDS:
        if key not in source:
            continue
        metadata[key] = _target_text(source, key)

    acquired_on = metadata.get("source_acquired_on")
    if acquired_on is not None:
        try:
            date.fromisoformat(acquired_on)
        except ValueError as exc:
            raise CalibrationError("calibration source 'source_acquired_on' must use YYYY-MM-DD") from exc

    archive_sha256 = source.get("source_archive_sha256")
    if archive_sha256 is not None:
        if not isinstance(archive_sha256, str) or not _SHA256_PATTERN.fullmatch(archive_sha256):
            raise CalibrationError(
                "calibration source 'source_archive_sha256' must be a 64-character hexadecimal digest"
            )
        metadata["source_archive_sha256"] = archive_sha256.lower()
    return metadata


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        raise CalibrationError("cannot compute percentile of empty source values")
    ordered = sorted(values)
    index = fraction * (len(ordered) - 1)
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    weight = index - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _numeric_statistic(values: list[float], statistic: str) -> float:
    if not values:
        raise CalibrationError("calibration source has no numeric values")
    if statistic == "count":
        return float(len(values))
    if statistic == "min":
        return min(values)
    if statistic == "max":
        return max(values)
    if statistic == "mean":
        return sum(values) / len(values)
    if statistic == "sum":
        return sum(values)
    if statistic == "p05":
        return _percentile(values, 0.05)
    if statistic == "p50":
        return _percentile(values, 0.50)
    if statistic == "p95":
        return _percentile(values, 0.95)
    if statistic == "fraction_positive":
        return sum(1 for value in values if value > 0.0) / len(values)
    if statistic == "fraction_nonzero":
        return sum(1 for value in values if value != 0.0) / len(values)
    raise CalibrationError(f"unsupported calibration statistic '{statistic}'")


def _haversine_km(lon_a: float, lat_a: float, lon_b: float, lat_b: float) -> float:
    radius_km = 6371.0
    lat_a_rad = math.radians(lat_a)
    lat_b_rad = math.radians(lat_b)
    d_lat = lat_b_rad - lat_a_rad
    d_lon = math.radians(lon_b - lon_a)
    a = (
        math.sin(d_lat * 0.5) * math.sin(d_lat * 0.5)
        + math.cos(lat_a_rad) * math.cos(lat_b_rad) * math.sin(d_lon * 0.5) * math.sin(d_lon * 0.5)
    )
    return 2.0 * radius_km * math.asin(min(1.0, math.sqrt(a)))


def _projected_ring_area_km2(points: list[tuple[float, float]]) -> float:
    if len(points) < 3:
        return 0.0
    area_m2 = 0.0
    for index, (x_a, y_a) in enumerate(points):
        x_b, y_b = points[(index + 1) % len(points)]
        area_m2 += x_a * y_b - x_b * y_a
    return abs(area_m2) * 0.5 / 1_000_000.0


def _geographic_ring_area_km2(points: list[tuple[float, float]]) -> float:
    if len(points) < 3:
        return 0.0
    mean_lat = sum(lat for _, lat in points) / len(points)
    x_scale = 111.320 * math.cos(math.radians(mean_lat))
    y_scale = 110.574
    area = 0.0
    for index, (lon_a, lat_a) in enumerate(points):
        lon_b, lat_b = points[(index + 1) % len(points)]
        area += (lon_a * x_scale) * (lat_b * y_scale) - (lon_b * x_scale) * (lat_a * y_scale)
    return abs(area) * 0.5


def _segment_length_km(
    point_a: tuple[float, float],
    point_b: tuple[float, float],
    coordinate_system: str,
) -> float:
    x_a, y_a = point_a
    x_b, y_b = point_b
    if coordinate_system == "projected_m":
        return math.hypot(x_b - x_a, y_b - y_a) / 1000.0
    return _haversine_km(x_a, y_a, x_b, y_b)


def _ring_area_km2(points: list[tuple[float, float]], coordinate_system: str) -> float:
    if coordinate_system == "projected_m":
        return _projected_ring_area_km2(points)
    return _geographic_ring_area_km2(points)


def _part_ranges(part_indexes: list[int], point_count: int) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    for index, start in enumerate(part_indexes):
        end = part_indexes[index + 1] if index + 1 < len(part_indexes) else point_count
        if start < 0 or end < start or end > point_count:
            raise CalibrationError("shapefile record has invalid part indexes")
        ranges.append((start, end))
    return ranges


def _point_in_ring(lon: float, lat: float, ring: list[tuple[float, float]]) -> bool:
    if len(ring) < 3:
        return False
    inside = False
    previous_lon, previous_lat = ring[-1]
    for current_lon, current_lat in ring:
        crosses_latitude = (current_lat > lat) != (previous_lat > lat)
        if crosses_latitude:
            crossing_lon = previous_lon + (lat - previous_lat) * (current_lon - previous_lon) / (
                current_lat - previous_lat
            )
            if lon < crossing_lon:
                inside = not inside
        previous_lon, previous_lat = current_lon, current_lat
    return inside


def _point_in_polygon_feature(lon: float, lat: float, feature: dict[str, Any]) -> bool:
    bbox = feature.get("bbox")
    if not isinstance(bbox, tuple) or len(bbox) != 4:
        raise CalibrationError("polygon shapefile feature is missing its bounding box")
    min_lon, min_lat, max_lon, max_lat = bbox
    if lon < min_lon or lon > max_lon or lat < min_lat or lat > max_lat:
        return False

    parts = feature.get("polygon_parts")
    if not isinstance(parts, list):
        raise CalibrationError("polygon shapefile feature is missing polygon parts")
    inside = False
    for ring in parts:
        if _point_in_ring(lon, lat, ring):
            inside = not inside
    return inside


def _fibonacci_points(cell_count: int) -> list[tuple[float, float, float, float, float]]:
    golden_angle = math.pi * (3.0 - math.sqrt(5.0))
    points: list[tuple[float, float, float, float, float]] = []
    for cell_id in range(cell_count):
        z = 1.0 - 2.0 * (cell_id + 0.5) / cell_count
        radius = math.sqrt(max(0.0, 1.0 - z * z))
        theta = golden_angle * cell_id
        x = math.cos(theta) * radius
        y = math.sin(theta) * radius
        points.append((x, y, z, math.degrees(math.atan2(y, x)), math.degrees(math.asin(z))))
    return points


def _symmetric_nearest_neighbors(
    points: list[tuple[float, float, float, float, float]],
    neighbor_count: int,
) -> list[set[int]]:
    neighbors = [set() for _ in points]
    for cell_id, (x_a, y_a, z_a, _lon, _lat) in enumerate(points):
        best: list[tuple[float, int]] = []
        for other_id, (x_b, y_b, z_b, _other_lon, _other_lat) in enumerate(points):
            if cell_id == other_id:
                continue
            score = x_a * x_b + y_a * y_b + z_a * z_b
            if len(best) < neighbor_count:
                heapq.heappush(best, (score, other_id))
            elif score > best[0][0]:
                heapq.heapreplace(best, (score, other_id))
        neighbors[cell_id].update(other_id for _score, other_id in best)

    for cell_id, linked_cells in enumerate(neighbors):
        for other_id in tuple(linked_cells):
            neighbors[other_id].add(cell_id)
    return neighbors


def _masked_component_sizes(mask: list[bool], neighbors: list[set[int]]) -> list[int]:
    visited = [False] * len(mask)
    component_sizes: list[int] = []
    for start, selected in enumerate(mask):
        if not selected or visited[start]:
            continue
        visited[start] = True
        stack = [start]
        component_size = 0
        while stack:
            cell_id = stack.pop()
            component_size += 1
            for other_id in neighbors[cell_id]:
                if mask[other_id] and not visited[other_id]:
                    visited[other_id] = True
                    stack.append(other_id)
        component_sizes.append(component_size)
    return sorted(component_sizes, reverse=True)


def _comma_separated_floats(raw: str, expected_count: int, label: str) -> list[float]:
    parts = [part.strip() for part in raw.split(",") if part.strip()]
    if len(parts) != expected_count:
        raise CalibrationError(f"{label} has {len(parts)} values; expected {expected_count}")
    try:
        values = [float(part) for part in parts]
    except ValueError as exc:
        raise CalibrationError(f"{label} contains a non-numeric value") from exc
    if not all(math.isfinite(value) for value in values):
        raise CalibrationError(f"{label} contains a non-finite value")
    return values


def _next_nonempty_line(lines: list[str], start: int, label: str) -> tuple[int, str]:
    for index in range(start, len(lines)):
        stripped = lines[index].strip()
        if stripped:
            return index, stripped
    raise CalibrationError(f"OPeNDAP ASCII source is missing {label}")


def _nearest_coordinate_index(coordinates: list[float], value: float) -> int:
    upper = bisect_left(coordinates, value)
    if upper <= 0:
        return 0
    if upper >= len(coordinates):
        return len(coordinates) - 1
    lower = upper - 1
    return lower if value - coordinates[lower] <= coordinates[upper] - value else upper


def _normalize_vector_coordinate_system(raw: Any) -> str | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    normalized = raw.strip().lower().replace("-", "_").replace(" ", "_")
    compact = normalized.replace("_", "").replace(":", "")
    geographic_aliases = {
        "geographic",
        "geographic_degrees",
        "degrees",
        "degree",
        "lonlat",
        "lon_lat",
        "latlon",
        "lat_lon",
        "wgs84",
        "wgs_84",
        "epsg4326",
        "epsg4269",
        "epsg4258",
        "epsg4979",
    }
    projected_meter_aliases = {
        "projected",
        "projected_m",
        "projected_meter",
        "projected_meters",
        "projected_metre",
        "projected_metres",
        "cartesian_m",
        "cartesian_meters",
        "meter",
        "meters",
        "metre",
        "metres",
        "epsg3857",
        "epsg3395",
        "epsg6933",
        "epsg3035",
        "epsg3577",
        "epsg5070",
        "epsg2163",
    }
    if normalized in geographic_aliases or compact in geographic_aliases:
        return "geographic"
    if normalized in projected_meter_aliases or compact in projected_meter_aliases:
        return "projected_m"
    raise CalibrationError(
        f"unsupported vector coordinate_system '{raw}'; use geographic/lonlat/wgs84 or projected_m/meters"
    )


def _coordinate_system_from_prj_text(text: str) -> str | None:
    upper = text.upper()
    compact = "".join(upper.split())
    if '"EPSG","3857"' in compact or "EPSG:3857" in compact:
        return "projected_m"
    if '"EPSG","4326"' in compact or "EPSG:4326" in compact:
        return "geographic"
    has_projected_crs = "PROJCS" in upper or "PROJCRS" in upper or "PROJECTEDCRS" in upper
    has_geographic_crs = "GEOGCS" in upper or "GEOGCRS" in upper or "GEODCRS" in upper
    has_meter_units = (
        'UNIT["METRE"' in upper
        or 'UNIT["METER"' in upper
        or 'LENGTHUNIT["METRE"' in upper
        or 'LENGTHUNIT["METER"' in upper
        or '"EPSG","9001"' in compact
    )
    has_degree_units = 'UNIT["DEGREE"' in upper or 'ANGLEUNIT["DEGREE"' in upper or '"EPSG","9122"' in compact
    if has_projected_crs:
        return "projected_m" if has_meter_units or not has_degree_units else None
    if has_geographic_crs:
        return "geographic"
    if has_meter_units and not has_degree_units:
        return "projected_m"
    if has_degree_units:
        return "geographic"
    return None


def _prj_path_for_shapefile(path: Path, source: dict[str, Any]) -> Path:
    explicit = source.get("prj_path")
    if isinstance(explicit, str) and explicit:
        return Path(explicit)
    return path.with_suffix(".prj")


def _coordinate_system_for_vector(path: Path, source: dict[str, Any]) -> str:
    explicit = _normalize_vector_coordinate_system(source.get("coordinate_system"))
    if explicit is not None:
        return explicit

    prj_path = _prj_path_for_shapefile(path, source)
    if prj_path.exists():
        try:
            prj_text = prj_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            prj_text = prj_path.read_text(encoding="latin-1")
        inferred = _coordinate_system_from_prj_text(prj_text)
        if inferred is None:
            raise CalibrationError(f"could not infer vector coordinate system from shapefile projection file: {prj_path}")
        return inferred
    if "prj_path" in source:
        raise CalibrationError(f"shapefile projection file does not exist: {prj_path}")
    return "geographic"
