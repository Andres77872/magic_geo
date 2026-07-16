from __future__ import annotations

import hashlib
import heapq
import json
import math
import re
import struct
from bisect import bisect_left
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any, BinaryIO, Iterator
from zipfile import BadZipFile, ZipFile

from .geotiff import GeoTiffError, GeoTiffMetadata, GeoTiffRaster
from .scaling import HACK_FIT_MINIMUM_BASIN_AREA_KM2, fit_power_law


class CalibrationError(ValueError):
    """Raised when a calibration target file is malformed."""


_FIBONACCI_COASTAL_STATISTIC = "fibonacci_coastal_land_fraction"
_FIBONACCI_RELIEF_STATISTICS = {
    "fibonacci_ocean_fraction",
    "fibonacci_mean_land_elevation_m",
    "fibonacci_hypsometric_span_m",
}
_FIBONACCI_WORLDCLIM_STATISTICS = {
    "fibonacci_mean_land_annual_temperature_c",
    "fibonacci_mean_land_annual_precipitation_mm",
    "fibonacci_mean_land_annual_temperature_range_c",
}
_HYDROBASINS_STATISTICS = {
    "hydrobasins_endorheic_basin_fraction",
    "hydrobasins_endorheic_area_fraction",
}
_HYDRORIVERS_STATISTICS = {
    "hydrorivers_hack_fitted_exponent",
    "hydrorivers_hack_fitted_log_rmse",
}
_HYDROBASINS_GENERATED_MIN_CENTROID_LAT_DEG = -60.0
_SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")
_SOURCE_PROVENANCE_FIELDS = (
    "source_url",
    "source_archive_url",
    "source_version",
    "source_license",
    "source_license_url",
    "source_acquired_on",
    "source_citation",
    "source_doi",
    "source_horizontal_crs",
    "source_geographic_coverage",
    "source_vertical_datum",
    "source_native_resolution",
    "source_processing",
    "source_temporal_coverage",
    "source_variable_units",
)


def score_range(value: float, target_min: float, target_max: float) -> float:
    if not all(math.isfinite(item) for item in (value, target_min, target_max)):
        raise CalibrationError("calibration values and target bounds must be finite")
    if target_max < target_min:
        raise CalibrationError("target_max must be greater than or equal to target_min")
    if target_min <= value <= target_max:
        return 1.0
    width = max(1.0e-9, target_max - target_min)
    distance = target_min - value if value < target_min else value - target_max
    return max(0.0, min(1.0, 1.0 - distance / width))


def _target_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        payload = payload.get("targets")
    if not isinstance(payload, list):
        raise CalibrationError("calibration targets must be a list or an object with a 'targets' list")
    for item in payload:
        if not isinstance(item, dict):
            raise CalibrationError("each calibration target must be an object")
    return payload


def load_calibration_targets(path: Path) -> list[dict[str, Any]]:
    return _target_items(json.loads(path.read_text(encoding="utf-8")))


def _source_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        payload = payload.get("sources")
    if not isinstance(payload, list):
        raise CalibrationError("calibration sources must be a list or an object with a 'sources' list")
    for item in payload:
        if not isinstance(item, dict):
            raise CalibrationError("each calibration source must be an object")
    return payload


def load_calibration_sources(path: Path) -> list[dict[str, Any]]:
    sources = _source_items(json.loads(path.read_text(encoding="utf-8")))
    resolved: list[dict[str, Any]] = []
    for source in sources:
        copied = dict(source)
        raw_path = _target_text(copied, "path")
        source_path = Path(raw_path)
        if not source_path.is_absolute():
            source_path = path.parent / source_path
        copied["path"] = str(source_path)
        if "dbf_path" in copied:
            raw_dbf_path = _target_text(copied, "dbf_path")
            dbf_path = Path(raw_dbf_path)
            if not dbf_path.is_absolute():
                dbf_path = path.parent / dbf_path
            copied["dbf_path"] = str(dbf_path)
        if "prj_path" in copied:
            raw_prj_path = _target_text(copied, "prj_path")
            prj_path = Path(raw_prj_path)
            if not prj_path.is_absolute():
                prj_path = path.parent / prj_path
            copied["prj_path"] = str(prj_path)
        resolved.append(copied)
    return resolved


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


def _read_esri_ascii_grid(path: Path) -> list[float]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        lines = path.read_text(encoding="latin-1").splitlines()

    header: dict[str, str] = {}
    data_start = 0
    for index, line in enumerate(lines):
        parts = line.split()
        if len(parts) < 2:
            continue
        key = parts[0].lower()
        if key in {"ncols", "nrows", "xllcorner", "xllcenter", "yllcorner", "yllcenter", "cellsize", "nodata_value"}:
            header[key] = parts[1]
            data_start = index + 1
            if "ncols" in header and "nrows" in header and "cellsize" in header and index >= 5:
                break

    if "ncols" not in header or "nrows" not in header:
        raise CalibrationError(f"{path} is missing ESRI ASCII ncols/nrows headers")

    try:
        ncols = int(float(header["ncols"]))
        nrows = int(float(header["nrows"]))
    except ValueError as exc:
        raise CalibrationError(f"{path} has invalid ESRI ASCII dimensions") from exc

    nodata = float(header.get("nodata_value", "-9999"))
    values: list[float] = []
    raw_value_count = 0
    for line in lines[data_start:]:
        for raw in line.split():
            try:
                value = float(raw)
            except ValueError as exc:
                raise CalibrationError(f"{path} contains a non-numeric raster value") from exc
            raw_value_count += 1
            if value != nodata:
                values.append(value)

    if raw_value_count != ncols * nrows:
        raise CalibrationError(f"{path} raster value count does not match declared ncols/nrows")
    if not values:
        raise CalibrationError(f"{path} has no non-NODATA raster values")
    return values


def _read_geojson_values(path: Path, source: dict[str, Any], statistic: str) -> list[float]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    features = payload.get("features") if isinstance(payload, dict) else None
    if not isinstance(features, list):
        raise CalibrationError(f"{path} is not a GeoJSON FeatureCollection")
    if statistic == "feature_count":
        return [float(len(features))]

    property_name = source.get("property")
    if not isinstance(property_name, str) or not property_name:
        raise CalibrationError("GeoJSON calibration sources require 'property' unless statistic is feature_count")
    values: list[float] = []
    for feature in features:
        if not isinstance(feature, dict):
            continue
        properties = feature.get("properties", {})
        if not isinstance(properties, dict) or property_name not in properties:
            continue
        try:
            values.append(float(properties[property_name]))
        except (TypeError, ValueError) as exc:
            raise CalibrationError(f"GeoJSON property '{property_name}' must be numeric") from exc
    if not values:
        raise CalibrationError(f"{path} has no numeric GeoJSON property values for '{property_name}'")
    return values


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


def _read_shapefile_records(path: Path, coordinate_system: str = "geographic") -> list[dict[str, Any]]:
    data = path.read_bytes()
    if len(data) < 100:
        raise CalibrationError(f"{path} is too small to be an ESRI shapefile")
    try:
        file_code = struct.unpack_from(">i", data, 0)[0]
        file_length_words = struct.unpack_from(">i", data, 24)[0]
        version = struct.unpack_from("<i", data, 28)[0]
        declared_shape_type = struct.unpack_from("<i", data, 32)[0]
    except struct.error as exc:
        raise CalibrationError(f"{path} has a malformed shapefile header") from exc
    if file_code != 9994 or version != 1000:
        raise CalibrationError(f"{path} is not an ESRI shapefile")
    if file_length_words * 2 > len(data):
        raise CalibrationError(f"{path} shapefile length header exceeds file size")

    offset = 100
    records: list[dict[str, Any]] = []
    while offset + 8 <= len(data):
        try:
            _record_number, content_length_words = struct.unpack_from(">2i", data, offset)
        except struct.error as exc:
            raise CalibrationError(f"{path} has a malformed shapefile record header") from exc
        offset += 8
        content_length = content_length_words * 2
        if content_length < 4 or offset + content_length > len(data):
            raise CalibrationError(f"{path} has a malformed shapefile record length")
        record = data[offset:offset + content_length]
        offset += content_length
        try:
            shape_type = struct.unpack_from("<i", record, 0)[0]
        except struct.error as exc:
            raise CalibrationError(f"{path} has a malformed shapefile record") from exc
        if shape_type == 0:
            continue
        if declared_shape_type not in {0, shape_type}:
            raise CalibrationError(f"{path} mixes shapefile shape types")

        feature = {
            "shape_type": shape_type,
            "point_count": 0.0,
            "part_count": 0.0,
            "length_km": 0.0,
            "area_km2": 0.0,
        }
        if shape_type == 1:
            if len(record) < 20:
                raise CalibrationError(f"{path} has a malformed point shapefile record")
            feature["point_count"] = 1.0
        elif shape_type in {3, 5}:
            if len(record) < 44:
                raise CalibrationError(f"{path} has a malformed polyline/polygon shapefile record")
            try:
                min_x, min_y, max_x, max_y = struct.unpack_from("<4d", record, 4)
                part_count, point_count = struct.unpack_from("<2i", record, 36)
            except struct.error as exc:
                raise CalibrationError(f"{path} has malformed shapefile part counts") from exc
            if not all(math.isfinite(value) for value in (min_x, min_y, max_x, max_y)):
                raise CalibrationError(f"{path} has a non-finite shapefile bounding box")
            if max_x < min_x or max_y < min_y:
                raise CalibrationError(f"{path} has an inverted shapefile bounding box")
            parts_offset = 44
            points_offset = parts_offset + part_count * 4
            expected_size = points_offset + point_count * 16
            if part_count <= 0 or point_count < 0 or expected_size > len(record):
                raise CalibrationError(f"{path} has malformed shapefile point data")
            part_indexes = list(struct.unpack_from(f"<{part_count}i", record, parts_offset))
            points = [
                struct.unpack_from("<2d", record, points_offset + index * 16)
                for index in range(point_count)
            ]
            feature["point_count"] = float(point_count)
            feature["part_count"] = float(part_count)
            feature["bbox"] = (float(min_x), float(min_y), float(max_x), float(max_y))
            polygon_parts: list[list[tuple[float, float]]] = []
            for start, end in _part_ranges(part_indexes, point_count):
                part_points = [(float(lon), float(lat)) for lon, lat in points[start:end]]
                for point_index in range(1, len(part_points)):
                    feature["length_km"] += _segment_length_km(
                        part_points[point_index - 1],
                        part_points[point_index],
                        coordinate_system,
                    )
                if shape_type == 5:
                    feature["area_km2"] += _ring_area_km2(part_points, coordinate_system)
                    polygon_parts.append(part_points)
            if shape_type == 5:
                feature["polygon_parts"] = polygon_parts
        elif shape_type == 8:
            if len(record) < 40:
                raise CalibrationError(f"{path} has a malformed multipoint shapefile record")
            try:
                point_count = struct.unpack_from("<i", record, 36)[0]
            except struct.error as exc:
                raise CalibrationError(f"{path} has malformed multipoint count") from exc
            if point_count < 0 or 40 + point_count * 16 > len(record):
                raise CalibrationError(f"{path} has malformed multipoint data")
            feature["point_count"] = float(point_count)
        else:
            raise CalibrationError(f"unsupported shapefile shape type {shape_type}")
        records.append(feature)

    if offset != len(data):
        raise CalibrationError(f"{path} has trailing malformed shapefile bytes")
    if not records:
        raise CalibrationError(f"{path} has no non-null shapefile records")
    return records


def _dbf_path_for_shapefile(path: Path, source: dict[str, Any]) -> Path:
    explicit = source.get("dbf_path")
    if isinstance(explicit, str) and explicit:
        return Path(explicit)
    return path.with_suffix(".dbf")


def _read_dbf_numeric_columns_from_bytes(
    data: bytes,
    source_label: str,
    property_names: list[str],
    *,
    require_complete_records: bool = False,
) -> dict[str, list[float]]:
    if not property_names or any(not name for name in property_names):
        raise CalibrationError("DBF numeric column names must be non-empty")
    normalized_names = [name.lower() for name in property_names]
    if len(set(normalized_names)) != len(normalized_names):
        raise CalibrationError("DBF numeric column names must be unique")
    if len(data) < 33:
        raise CalibrationError(f"{source_label} is too small to be a DBF file")
    try:
        record_count = struct.unpack_from("<I", data, 4)[0]
        header_length = struct.unpack_from("<H", data, 8)[0]
        record_length = struct.unpack_from("<H", data, 10)[0]
    except struct.error as exc:
        raise CalibrationError(f"{source_label} has a malformed DBF header") from exc
    if header_length < 33 or record_length < 1 or header_length > len(data):
        raise CalibrationError(f"{source_label} has invalid DBF header lengths")

    fields: list[dict[str, Any]] = []
    offset = 32
    found_terminator = False
    while offset < header_length:
        if data[offset] == 0x0D:
            found_terminator = True
            break
        if offset + 32 > header_length:
            raise CalibrationError(f"{source_label} has a truncated DBF field descriptor")
        descriptor = data[offset:offset + 32]
        name = descriptor[:11].split(b"\x00", 1)[0].decode("ascii", errors="ignore").strip()
        field_type = chr(descriptor[11])
        field_length = descriptor[16]
        if not name or field_length <= 0:
            raise CalibrationError(f"{source_label} has an invalid DBF field descriptor")
        fields.append({"name": name, "type": field_type, "length": field_length})
        offset += 32
    if not found_terminator or not fields:
        raise CalibrationError(f"{source_label} has no DBF fields")

    field_offset = 1
    selected: dict[str, tuple[int, dict[str, Any]]] = {}
    for field in fields:
        normalized_field_name = str(field["name"]).lower()
        if normalized_field_name in normalized_names:
            if normalized_field_name in selected:
                raise CalibrationError(f"{source_label} duplicates DBF field '{field['name']}'")
            selected[normalized_field_name] = (field_offset, field)
        field_offset += int(field["length"])
    if field_offset != record_length:
        raise CalibrationError(f"{source_label} DBF field widths do not match its record length")
    for property_name, normalized_name in zip(property_names, normalized_names, strict=True):
        if normalized_name not in selected:
            raise CalibrationError(f"{source_label} has no DBF field named '{property_name}'")
        if selected[normalized_name][1]["type"] not in {"N", "F"}:
            raise CalibrationError(f"DBF field '{property_name}' must be numeric")

    expected_size = header_length + record_count * record_length
    if expected_size > len(data):
        raise CalibrationError(f"{source_label} DBF record data is truncated")
    columns = {property_name: [] for property_name in property_names}
    for index in range(record_count):
        record_offset = header_length + index * record_length
        deletion_flag = data[record_offset:record_offset + 1]
        if deletion_flag == b"*":
            continue
        if deletion_flag != b" ":
            raise CalibrationError(f"{source_label} has an invalid DBF deletion flag in record {index}")
        for property_name, normalized_name in zip(property_names, normalized_names, strict=True):
            selected_offset, selected_field = selected[normalized_name]
            raw = data[
                record_offset + selected_offset:
                record_offset + selected_offset + int(selected_field["length"])
            ]
            try:
                text = raw.decode("ascii").strip()
            except UnicodeDecodeError as exc:
                raise CalibrationError(f"DBF field '{property_name}' contains non-ASCII numeric data") from exc
            if not text:
                if require_complete_records:
                    raise CalibrationError(
                        f"DBF field '{property_name}' is blank in active record {index} of {source_label}"
                    )
                continue
            try:
                columns[property_name].append(float(text))
            except ValueError as exc:
                raise CalibrationError(f"DBF field '{property_name}' contains a non-numeric value") from exc
    for property_name, values in columns.items():
        if not values:
            raise CalibrationError(f"{source_label} has no numeric DBF values for '{property_name}'")
    return columns


def _read_dbf_numeric_values_from_bytes(
    data: bytes,
    source_label: str,
    property_name: str,
) -> list[float]:
    return _read_dbf_numeric_columns_from_bytes(data, source_label, [property_name])[property_name]


def _iter_dbf_numeric_records(
    stream: BinaryIO,
    source_label: str,
    property_names: list[str],
) -> Iterator[dict[str, float]]:
    if not property_names or any(not name for name in property_names):
        raise CalibrationError("DBF numeric column names must be non-empty")
    normalized_names = [name.lower() for name in property_names]
    if len(set(normalized_names)) != len(normalized_names):
        raise CalibrationError("DBF numeric column names must be unique")

    prefix = stream.read(32)
    if len(prefix) != 32:
        raise CalibrationError(f"{source_label} is too small to be a DBF file")
    try:
        record_count = struct.unpack_from("<I", prefix, 4)[0]
        header_length = struct.unpack_from("<H", prefix, 8)[0]
        record_length = struct.unpack_from("<H", prefix, 10)[0]
    except struct.error as exc:
        raise CalibrationError(f"{source_label} has a malformed DBF header") from exc
    if header_length < 33 or record_length < 1:
        raise CalibrationError(f"{source_label} has invalid DBF header lengths")
    header_tail = stream.read(header_length - 32)
    if len(header_tail) != header_length - 32:
        raise CalibrationError(f"{source_label} has a truncated DBF header")
    header = prefix + header_tail

    fields: list[dict[str, Any]] = []
    offset = 32
    found_terminator = False
    while offset < header_length:
        if header[offset] == 0x0D:
            found_terminator = True
            break
        if offset + 32 > header_length:
            raise CalibrationError(f"{source_label} has a truncated DBF field descriptor")
        descriptor = header[offset:offset + 32]
        name = descriptor[:11].split(b"\x00", 1)[0].decode("ascii", errors="ignore").strip()
        field_type = chr(descriptor[11])
        field_length = descriptor[16]
        if not name or field_length <= 0:
            raise CalibrationError(f"{source_label} has an invalid DBF field descriptor")
        fields.append({"name": name, "type": field_type, "length": field_length})
        offset += 32
    if not found_terminator or not fields:
        raise CalibrationError(f"{source_label} has no DBF fields")

    field_offset = 1
    selected: dict[str, tuple[int, dict[str, Any]]] = {}
    for field in fields:
        normalized_field_name = str(field["name"]).lower()
        if normalized_field_name in normalized_names:
            if normalized_field_name in selected:
                raise CalibrationError(f"{source_label} duplicates DBF field '{field['name']}'")
            selected[normalized_field_name] = (field_offset, field)
        field_offset += int(field["length"])
    if field_offset != record_length:
        raise CalibrationError(f"{source_label} DBF field widths do not match its record length")
    for property_name, normalized_name in zip(property_names, normalized_names, strict=True):
        if normalized_name not in selected:
            raise CalibrationError(f"{source_label} has no DBF field named '{property_name}'")
        if selected[normalized_name][1]["type"] not in {"N", "F"}:
            raise CalibrationError(f"DBF field '{property_name}' must be numeric")

    for index in range(record_count):
        record = stream.read(record_length)
        if len(record) != record_length:
            raise CalibrationError(f"{source_label} DBF record data is truncated at record {index}")
        deletion_flag = record[:1]
        if deletion_flag == b"*":
            continue
        if deletion_flag != b" ":
            raise CalibrationError(f"{source_label} has an invalid DBF deletion flag in record {index}")
        values: dict[str, float] = {}
        for property_name, normalized_name in zip(property_names, normalized_names, strict=True):
            selected_offset, selected_field = selected[normalized_name]
            raw = record[selected_offset:selected_offset + int(selected_field["length"])]
            try:
                text = raw.decode("ascii").strip()
            except UnicodeDecodeError as exc:
                raise CalibrationError(f"DBF field '{property_name}' contains non-ASCII numeric data") from exc
            if not text:
                raise CalibrationError(
                    f"DBF field '{property_name}' is blank in active record {index} of {source_label}"
                )
            try:
                values[property_name] = float(text)
            except ValueError as exc:
                raise CalibrationError(f"DBF field '{property_name}' contains a non-numeric value") from exc
        yield values


def _read_dbf_numeric_values(path: Path, property_name: str) -> list[float]:
    return _read_dbf_numeric_values_from_bytes(path.read_bytes(), str(path), property_name)


def _read_shapefile_values(path: Path, source: dict[str, Any], statistic: str) -> list[float]:
    if statistic == "feature_count":
        records = _read_shapefile_records(path)
        return [float(len(records))]

    property_name = source.get("property")
    if isinstance(property_name, str) and property_name:
        dbf_path = _dbf_path_for_shapefile(path, source)
        if not dbf_path.exists():
            raise CalibrationError(f"shapefile DBF attribute table does not exist: {dbf_path}")
        return _read_dbf_numeric_values(dbf_path, property_name)

    coordinate_system = _coordinate_system_for_vector(path, source)
    records = _read_shapefile_records(path, coordinate_system)
    metric = str(source.get("geometry_metric", "length_km")).lower()
    metric_aliases = {
        "length": "length_km",
        "total_length_km": "length_km",
        "area": "area_km2",
        "total_area_km2": "area_km2",
        "points": "point_count",
        "parts": "part_count",
    }
    metric = metric_aliases.get(metric, metric)
    if metric not in {"length_km", "area_km2", "point_count", "part_count"}:
        raise CalibrationError(f"unsupported shapefile geometry_metric '{metric}'")
    values = [record[metric] for record in records]
    if not values:
        raise CalibrationError(f"{path} has no shapefile geometry values")
    return values


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


def _fibonacci_coastal_land_fraction(
    path: Path,
    source: dict[str, Any],
) -> tuple[float, dict[str, Any]]:
    cell_count = _optional_int(source, "sample_cell_count", 4096)
    neighbor_count = _optional_int(source, "sample_neighbor_count", 7)
    if cell_count < 128:
        raise CalibrationError("calibration source 'sample_cell_count' must be at least 128")
    if neighbor_count < 4 or neighbor_count >= cell_count:
        raise CalibrationError(
            "calibration source 'sample_neighbor_count' must be at least 4 and smaller than sample_cell_count"
        )

    coordinate_system = _coordinate_system_for_vector(path, source)
    if coordinate_system != "geographic":
        raise CalibrationError(f"{_FIBONACCI_COASTAL_STATISTIC} requires geographic lon/lat polygons")
    features = _read_shapefile_records(path, coordinate_system)
    if any(feature.get("shape_type") != 5 for feature in features):
        raise CalibrationError(f"{_FIBONACCI_COASTAL_STATISTIC} requires a polygon shapefile")

    points = _fibonacci_points(cell_count)
    is_land = [
        any(_point_in_polygon_feature(lon, lat, feature) for feature in features)
        for _x, _y, _z, lon, lat in points
    ]
    land_cell_count = sum(is_land)
    water_cell_count = cell_count - land_cell_count
    if land_cell_count == 0 or water_cell_count == 0:
        raise CalibrationError(
            f"{_FIBONACCI_COASTAL_STATISTIC} requires sampled polygons containing both land and water cells"
        )

    neighbors = _symmetric_nearest_neighbors(points, neighbor_count)
    coastal_land_cell_count = sum(
        1
        for cell_id, land in enumerate(is_land)
        if land and any(not is_land[other_id] for other_id in neighbors[cell_id])
    )
    land_component_sizes = _masked_component_sizes(is_land, neighbors)
    land_water_edge_count = sum(
        1
        for cell_id, linked_cells in enumerate(neighbors)
        for other_id in linked_cells
        if cell_id < other_id and is_land[cell_id] != is_land[other_id]
    )
    value = coastal_land_cell_count / land_cell_count
    return value, {
        "source_sampling_mesh": "fibonacci_sphere_v1",
        "source_sample_cell_count": cell_count,
        "source_sample_neighbor_count": neighbor_count,
        "source_sample_land_cell_count": land_cell_count,
        "source_sample_land_fraction": land_cell_count / cell_count,
        "source_sample_water_cell_count": water_cell_count,
        "source_sample_coastal_land_cell_count": coastal_land_cell_count,
        "source_sample_land_component_count": len(land_component_sizes),
        "source_sample_largest_land_component_cell_count": land_component_sizes[0],
        "source_sample_largest_land_component_fraction": land_component_sizes[0] / land_cell_count,
        "source_sample_land_water_edge_count": land_water_edge_count,
        "source_coast_definition": "land_cell_with_symmetric_one_hop_water_neighbor",
    }


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


def _read_opendap_ascii_grid(
    path: Path,
    variable: str,
) -> tuple[list[list[float]], list[float], list[float]]:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", variable):
        raise CalibrationError("calibration source OPeNDAP 'variable' must be an identifier")
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise CalibrationError(f"{path} is not a UTF-8 OPeNDAP ASCII response") from exc

    grid_pattern = re.compile(rf"^{re.escape(variable)}\.{re.escape(variable)}\[(\d+)\]\[(\d+)\]$")
    grid_header_index = -1
    row_count = 0
    column_count = 0
    for index, line in enumerate(lines):
        match = grid_pattern.fullmatch(line.strip())
        if match is not None:
            grid_header_index = index
            row_count = int(match.group(1))
            column_count = int(match.group(2))
            break
    if grid_header_index < 0:
        raise CalibrationError(f"{path} is missing OPeNDAP grid header '{variable}.{variable}[rows][columns]'")
    if row_count <= 0 or column_count <= 0 or row_count * column_count > 5_000_000:
        raise CalibrationError(f"{path} has invalid or excessive OPeNDAP grid dimensions")

    grid: list[list[float]] = []
    line_index = grid_header_index + 1
    row_pattern = re.compile(r"^\[(\d+)\],\s*(.*)$")
    for expected_row in range(row_count):
        line_index, row_line = _next_nonempty_line(lines, line_index, f"grid row {expected_row}")
        row_match = row_pattern.fullmatch(row_line)
        if row_match is None or int(row_match.group(1)) != expected_row:
            raise CalibrationError(f"{path} has malformed or out-of-order OPeNDAP grid row {expected_row}")
        grid.append(
            _comma_separated_floats(
                row_match.group(2),
                column_count,
                f"{path} OPeNDAP grid row {expected_row}",
            )
        )
        line_index += 1

    def read_coordinate(name: str, expected_count: int, start: int) -> tuple[list[float], int]:
        header_pattern = re.compile(rf"^{re.escape(variable)}\.{name}\[(\d+)\]$")
        header_index = -1
        for index in range(start, len(lines)):
            match = header_pattern.fullmatch(lines[index].strip())
            if match is not None:
                if int(match.group(1)) != expected_count:
                    raise CalibrationError(f"{path} OPeNDAP {name} dimension does not match the grid")
                header_index = index
                break
        if header_index < 0:
            raise CalibrationError(f"{path} is missing OPeNDAP {name} coordinates")
        value_index, value_line = _next_nonempty_line(lines, header_index + 1, f"{name} coordinate values")
        return (
            _comma_separated_floats(value_line, expected_count, f"{path} OPeNDAP {name} coordinates"),
            value_index + 1,
        )

    latitudes, line_index = read_coordinate("lat", row_count, line_index)
    longitudes, _line_index = read_coordinate("lon", column_count, line_index)
    if any(latitudes[index] >= latitudes[index + 1] for index in range(len(latitudes) - 1)):
        raise CalibrationError(f"{path} OPeNDAP latitudes must be strictly increasing")
    if any(longitudes[index] >= longitudes[index + 1] for index in range(len(longitudes) - 1)):
        raise CalibrationError(f"{path} OPeNDAP longitudes must be strictly increasing")
    return grid, latitudes, longitudes


def _nearest_coordinate_index(coordinates: list[float], value: float) -> int:
    upper = bisect_left(coordinates, value)
    if upper <= 0:
        return 0
    if upper >= len(coordinates):
        return len(coordinates) - 1
    lower = upper - 1
    return lower if value - coordinates[lower] <= coordinates[upper] - value else upper


def _fibonacci_relief_statistic(
    path: Path,
    source: dict[str, Any],
    statistic: str,
) -> tuple[float, dict[str, Any]]:
    cell_count = _optional_int(source, "sample_cell_count", 4096)
    if cell_count < 128:
        raise CalibrationError("calibration source 'sample_cell_count' must be at least 128")
    variable = str(source.get("variable", "z"))
    grid, latitudes, longitudes = _read_opendap_ascii_grid(path, variable)
    if latitudes[0] > -80.0 or latitudes[-1] < 80.0 or longitudes[0] > -170.0 or longitudes[-1] < 170.0:
        raise CalibrationError("matched Fibonacci relief statistics require a global OPeNDAP grid")

    fill_value = _optional_float(source, "fill_value", -99999.0)
    elevations: list[float] = []
    for _x, _y, _z, lon, lat in _fibonacci_points(cell_count):
        row = _nearest_coordinate_index(latitudes, lat)
        column = _nearest_coordinate_index(longitudes, lon)
        elevation = grid[row][column]
        if elevation == fill_value:
            raise CalibrationError(f"{path} has a fill value at a sampled Fibonacci point")
        elevations.append(elevation)

    land_elevations = [elevation for elevation in elevations if elevation >= 0.0]
    ocean_cell_count = cell_count - len(land_elevations)
    if not land_elevations or ocean_cell_count == 0:
        raise CalibrationError("matched Fibonacci relief statistics require both land and ocean samples")
    mean_land_elevation = sum(land_elevations) / len(land_elevations)
    min_elevation = min(elevations)
    max_elevation = max(elevations)
    hypsometric_span = max_elevation - min_elevation
    values = {
        "fibonacci_ocean_fraction": ocean_cell_count / cell_count,
        "fibonacci_mean_land_elevation_m": mean_land_elevation,
        "fibonacci_hypsometric_span_m": hypsometric_span,
    }
    if statistic not in values:
        raise CalibrationError(f"unsupported matched Fibonacci relief statistic '{statistic}'")
    return values[statistic], {
        "source_sampling_mesh": "fibonacci_sphere_v1",
        "source_sample_cell_count": cell_count,
        "source_grid_latitude_count": len(latitudes),
        "source_grid_longitude_count": len(longitudes),
        "source_grid_latitude_min_deg": latitudes[0],
        "source_grid_latitude_max_deg": latitudes[-1],
        "source_grid_longitude_min_deg": longitudes[0],
        "source_grid_longitude_max_deg": longitudes[-1],
        "source_grid_latitude_step_deg": latitudes[1] - latitudes[0],
        "source_grid_longitude_step_deg": longitudes[1] - longitudes[0],
        "source_sample_land_cell_count": len(land_elevations),
        "source_sample_ocean_cell_count": ocean_cell_count,
        "source_sample_ocean_fraction": ocean_cell_count / cell_count,
        "source_sample_mean_land_elevation_m": mean_land_elevation,
        "source_sample_min_elevation_m": min_elevation,
        "source_sample_max_elevation_m": max_elevation,
        "source_sample_hypsometric_span_m": hypsometric_span,
    }


@lru_cache(maxsize=8)
def _worldclim_monthly_samples(
    path_text: str,
    source_sha256: str,
    variable: str,
    cell_count: int,
    value_scale: float,
    value_offset: float,
) -> tuple[tuple[tuple[float | None, ...], ...], GeoTiffMetadata]:
    del source_sha256  # Included in the cache key so replaced archives cannot reuse stale samples.
    path = Path(path_text)
    points = [(point[3], point[4]) for point in _fibonacci_points(cell_count)]
    monthly_samples: list[tuple[float | None, ...]] = []
    first_metadata: GeoTiffMetadata | None = None
    first_signature: tuple[object, ...] | None = None
    try:
        with ZipFile(path) as archive:
            member_names = [name for name in archive.namelist() if not name.endswith("/")]
            for month in range(1, 13):
                suffix = f"_{variable}_{month:02}.tif"
                matches = [name for name in member_names if Path(name).name.lower().endswith(suffix.lower())]
                if len(matches) != 1:
                    raise CalibrationError(
                        f"{path} must contain exactly one WorldClim member ending in '{suffix}'"
                    )
                member = archive.getinfo(matches[0])
                if member.file_size <= 0 or member.file_size > 64 * 1024 * 1024:
                    raise CalibrationError(f"{path} WorldClim member '{matches[0]}' has an invalid size")
                raster = GeoTiffRaster(archive.read(member))
                if first_signature is None:
                    first_signature = raster.grid_signature()
                    first_metadata = raster.metadata
                elif raster.grid_signature() != first_signature:
                    raise CalibrationError(f"{path} WorldClim monthly GeoTIFF grids do not align")
                sampled = raster.sample_lon_lat(points)
                monthly_samples.append(
                    tuple(
                        None if value is None else value * value_scale + value_offset
                        for value in sampled
                    )
                )
    except (BadZipFile, GeoTiffError) as exc:
        raise CalibrationError(f"invalid WorldClim GeoTIFF archive {path}: {exc}") from exc
    if first_metadata is None:
        raise CalibrationError(f"{path} has no WorldClim monthly GeoTIFF members")
    return tuple(monthly_samples), first_metadata


def _fibonacci_worldclim_statistic(
    path: Path,
    source: dict[str, Any],
    statistic: str,
) -> tuple[float, dict[str, Any]]:
    cell_count = _optional_int(source, "sample_cell_count", 4096)
    if cell_count < 128:
        raise CalibrationError("calibration source 'sample_cell_count' must be at least 128")
    expected_variable = (
        "prec"
        if statistic == "fibonacci_mean_land_annual_precipitation_mm"
        else "tavg"
    )
    variable = str(source.get("variable", expected_variable)).lower()
    if variable != expected_variable:
        raise CalibrationError(f"{statistic} requires WorldClim variable '{expected_variable}'")
    value_scale = _optional_float(source, "value_scale", 1.0)
    value_offset = _optional_float(source, "value_offset", 0.0)
    monthly_samples, raster_metadata = _worldclim_monthly_samples(
        str(path),
        _file_sha256(path),
        variable,
        cell_count,
        value_scale,
        value_offset,
    )

    valid_cell_ids = [
        cell_id
        for cell_id in range(cell_count)
        if all(month[cell_id] is not None for month in monthly_samples)
    ]
    if not valid_cell_ids:
        raise CalibrationError(f"{path} has no complete twelve-month WorldClim land samples")
    annual_means: list[float] = []
    annual_totals: list[float] = []
    annual_ranges: list[float] = []
    sampled_values: list[float] = []
    for cell_id in valid_cell_ids:
        values = [float(month[cell_id]) for month in monthly_samples]
        sampled_values.extend(values)
        annual_means.append(sum(values) / 12.0)
        annual_totals.append(sum(values))
        annual_ranges.append(max(values) - min(values))

    mean_annual_temperature = sum(annual_means) / len(annual_means)
    mean_annual_precipitation = sum(annual_totals) / len(annual_totals)
    mean_annual_temperature_range = sum(annual_ranges) / len(annual_ranges)
    values_by_statistic = {
        "fibonacci_mean_land_annual_temperature_c": mean_annual_temperature,
        "fibonacci_mean_land_annual_precipitation_mm": mean_annual_precipitation,
        "fibonacci_mean_land_annual_temperature_range_c": mean_annual_temperature_range,
    }
    metadata: dict[str, Any] = {
        "source_sampling_mesh": "fibonacci_sphere_v1",
        "source_sample_cell_count": cell_count,
        "source_sample_complete_land_cell_count": len(valid_cell_ids),
        "source_sample_complete_land_fraction": len(valid_cell_ids) / cell_count,
        "source_sample_excluded_cell_count": cell_count - len(valid_cell_ids),
        "source_sample_month_count": 12,
        "source_grid_width": raster_metadata.width,
        "source_grid_height": raster_metadata.height,
        "source_grid_origin_lon_deg": raster_metadata.origin_x,
        "source_grid_origin_lat_deg": raster_metadata.origin_y,
        "source_grid_pixel_width_deg": raster_metadata.pixel_width,
        "source_grid_pixel_height_deg": raster_metadata.pixel_height,
        "source_sample_min_value": min(sampled_values),
        "source_sample_max_value": max(sampled_values),
    }
    if variable == "tavg":
        metadata.update(
            {
                "source_sample_mean_land_annual_temperature_c": mean_annual_temperature,
                "source_sample_mean_land_annual_temperature_range_c": mean_annual_temperature_range,
            }
        )
    else:
        metadata["source_sample_mean_land_annual_precipitation_mm"] = mean_annual_precipitation
    return values_by_statistic[statistic], metadata


def _hydrobasins_catalog_summary(
    path_text: str,
) -> dict[str, Any]:
    path = Path(path_text)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise CalibrationError(f"{path} HydroBASINS catalog must be an object")
    archives = payload.get("archives")
    if not isinstance(archives, list) or not archives:
        raise CalibrationError(f"{path} HydroBASINS catalog requires a non-empty 'archives' list")
    try:
        level = int(payload["pfafstetter_level"])
    except (KeyError, TypeError, ValueError) as exc:
        raise CalibrationError(f"{path} HydroBASINS catalog requires integer pfafstetter_level") from exc
    if level < 1 or level > 12:
        raise CalibrationError(f"{path} HydroBASINS Pfafstetter level must be between 1 and 12")

    regions: set[str] = set()
    archive_checksums: dict[str, str] = {}
    archive_total_bytes = 0
    endorheic_values: list[int] = []
    basin_areas: list[float] = []
    for archive_record in archives:
        if not isinstance(archive_record, dict):
            raise CalibrationError(f"{path} HydroBASINS archive entries must be objects")
        region = _target_text(archive_record, "region")
        if region in regions:
            raise CalibrationError(f"{path} duplicates HydroBASINS region '{region}'")
        regions.add(region)
        raw_archive_path = Path(_target_text(archive_record, "path"))
        archive_path = raw_archive_path if raw_archive_path.is_absolute() else path.parent / raw_archive_path
        if not archive_path.exists():
            raise CalibrationError(f"HydroBASINS archive does not exist: {archive_path}")
        expected_sha256 = _target_text(archive_record, "sha256")
        if not _SHA256_PATTERN.fullmatch(expected_sha256):
            raise CalibrationError(f"HydroBASINS region '{region}' has an invalid SHA-256")
        actual_sha256 = _file_sha256(archive_path)
        if actual_sha256 != expected_sha256.lower():
            raise CalibrationError(
                f"HydroBASINS archive SHA-256 mismatch for {region}: "
                f"expected {expected_sha256.lower()}, got {actual_sha256}"
            )
        archive_checksums[region] = actual_sha256
        archive_total_bytes += archive_path.stat().st_size
        try:
            with ZipFile(archive_path) as archive:
                matches = [
                    info
                    for info in archive.infolist()
                    if not info.is_dir() and info.filename.lower().endswith(".dbf")
                ]
                if len(matches) != 1:
                    raise CalibrationError(
                        f"HydroBASINS archive {archive_path} must contain exactly one DBF file"
                    )
                member = matches[0]
                if member.file_size <= 0 or member.file_size > 64 * 1024 * 1024:
                    raise CalibrationError(f"HydroBASINS DBF member has an invalid size: {member.filename}")
                dbf_data = archive.read(member)
        except BadZipFile as exc:
            raise CalibrationError(f"invalid HydroBASINS ZIP archive {archive_path}") from exc
        source_label = f"{archive_path}!{member.filename}"
        region_columns = _read_dbf_numeric_columns_from_bytes(
            dbf_data,
            source_label,
            ["ENDO", "SUB_AREA"],
            require_complete_records=True,
        )
        region_endorheic = region_columns["ENDO"]
        region_areas = region_columns["SUB_AREA"]
        for value in region_endorheic:
            if value not in {0.0, 1.0, 2.0}:
                raise CalibrationError(f"{source_label} contains invalid ENDO value {value}")
            endorheic_values.append(int(value))
        for area in region_areas:
            if not math.isfinite(area) or area <= 0.0:
                raise CalibrationError(f"{source_label} contains invalid SUB_AREA value {area}")
            basin_areas.append(area)

    basin_count = len(endorheic_values)
    endorheic_basin_count = sum(value > 0 for value in endorheic_values)
    endorheic_sink_count = sum(value == 2 for value in endorheic_values)
    total_area = sum(basin_areas)
    endorheic_area = sum(
        area for area, endorheic in zip(basin_areas, endorheic_values, strict=True) if endorheic > 0
    )
    if basin_count == 0 or total_area <= 0.0:
        raise CalibrationError(f"{path} HydroBASINS catalog has no basin records")
    combined_digest = hashlib.sha256()
    for region in sorted(archive_checksums):
        combined_digest.update(region.encode("ascii"))
        combined_digest.update(b"\x00")
        combined_digest.update(archive_checksums[region].encode("ascii"))
        combined_digest.update(b"\n")
    return {
        "pfafstetter_level": level,
        "archive_count": len(archives),
        "archive_total_bytes": archive_total_bytes,
        "archive_sha256_by_region": archive_checksums,
        "combined_data_sha256": combined_digest.hexdigest(),
        "basin_count": basin_count,
        "endorheic_basin_count": endorheic_basin_count,
        "endorheic_sink_count": endorheic_sink_count,
        "endorheic_basin_fraction": endorheic_basin_count / basin_count,
        "total_basin_area_km2": total_area,
        "endorheic_basin_area_km2": endorheic_area,
        "endorheic_area_fraction": endorheic_area / total_area,
    }


def _hydrobasins_catalog_statistic(
    path: Path,
    statistic: str,
) -> tuple[float, dict[str, Any]]:
    summary = _hydrobasins_catalog_summary(str(path))
    values = {
        "hydrobasins_endorheic_basin_fraction": summary["endorheic_basin_fraction"],
        "hydrobasins_endorheic_area_fraction": summary["endorheic_area_fraction"],
    }
    metadata = {f"source_{key}": value for key, value in summary.items()}
    metadata["source_sample_record_count"] = summary["basin_count"]
    return float(values[statistic]), metadata


@lru_cache(maxsize=4)
def _hydrorivers_archive_summary(path_text: str, minimum_upstream_area_km2: float) -> dict[str, Any]:
    path = Path(path_text)
    if not math.isfinite(minimum_upstream_area_km2) or minimum_upstream_area_km2 <= 0.0:
        raise CalibrationError("HydroRIVERS minimum_upstream_area_km2 must be finite and positive")
    try:
        with ZipFile(path) as archive:
            matches = [
                info
                for info in archive.infolist()
                if not info.is_dir() and info.filename.lower().endswith(".dbf")
            ]
            if len(matches) != 1:
                raise CalibrationError(f"HydroRIVERS archive {path} must contain exactly one DBF file")
            member = matches[0]
            if member.file_size <= 0 or member.file_size > 2 * 1024 * 1024 * 1024:
                raise CalibrationError(f"HydroRIVERS DBF member has an invalid size: {member.filename}")
            source_label = f"{path}!{member.filename}"
            active_record_count = 0
            terminal_record_count = 0
            exorheic_terminal_record_count = 0
            exorheic_backbone_terminal_record_count = 0
            observations: list[tuple[float, float]] = []
            with archive.open(member) as dbf_stream:
                for record in _iter_dbf_numeric_records(
                    dbf_stream,
                    source_label,
                    [
                        "NEXT_DOWN",
                        "ENDORHEIC",
                        "ORD_CLAS",
                        "UPLAND_SKM",
                        "DIST_UP_KM",
                    ],
                ):
                    active_record_count += 1
                    next_down = record["NEXT_DOWN"]
                    endorheic = record["ENDORHEIC"]
                    order_class = record["ORD_CLAS"]
                    upstream_area = record["UPLAND_SKM"]
                    upstream_distance = record["DIST_UP_KM"]
                    if (
                        not all(
                            math.isfinite(value)
                            for value in (
                                next_down,
                                endorheic,
                                order_class,
                                upstream_area,
                                upstream_distance,
                            )
                        )
                        or next_down < 0.0
                        or not next_down.is_integer()
                        or endorheic not in (0.0, 1.0)
                        or not order_class.is_integer()
                        or order_class < 1.0
                        or upstream_area < 0.0
                        or upstream_distance < 0.0
                    ):
                        raise CalibrationError(f"{source_label} contains invalid HydroRIVERS numeric values")
                    if int(next_down) != 0:
                        continue
                    terminal_record_count += 1
                    if int(endorheic) != 0:
                        continue
                    exorheic_terminal_record_count += 1
                    if int(order_class) != 1:
                        continue
                    exorheic_backbone_terminal_record_count += 1
                    if upstream_area >= minimum_upstream_area_km2 and upstream_distance > 0.0:
                        observations.append((upstream_area, upstream_distance))
    except BadZipFile as exc:
        raise CalibrationError(f"invalid HydroRIVERS ZIP archive {path}") from exc

    if len(observations) < 3 or len({area for area, _ in observations}) < 2:
        raise CalibrationError(
            f"{path} has insufficient HydroRIVERS outlet observations at or above "
            f"{minimum_upstream_area_km2} km2"
        )
    fit = fit_power_law(observations)
    areas = [area for area, _ in observations]
    distances = [distance for _, distance in observations]
    return {
        "archive_member": member.filename,
        "archive_member_uncompressed_bytes": member.file_size,
        "active_reach_record_count": active_record_count,
        "terminal_reach_record_count": terminal_record_count,
        "exorheic_terminal_reach_record_count": exorheic_terminal_record_count,
        "exorheic_backbone_terminal_reach_record_count": (
            exorheic_backbone_terminal_record_count
        ),
        "minimum_upstream_area_km2": minimum_upstream_area_km2,
        "sample_network_count": fit.observation_count,
        "sample_min_upstream_area_km2": min(areas),
        "sample_max_upstream_area_km2": max(areas),
        "sample_min_upstream_distance_km": min(distances),
        "sample_max_upstream_distance_km": max(distances),
        "hack_fitted_exponent": fit.exponent,
        "hack_fitted_coefficient": fit.coefficient,
        "hack_fitted_log_rmse": fit.log_rmse,
        "fit_model": "ordinary_least_squares_log_length_on_log_upstream_area_v1",
        "network_selection": (
            "next_down_zero_endorheic_zero_order_class_one_with_minimum_"
            "upstream_area_v2"
        ),
    }


def _hydrorivers_archive_statistic(
    path: Path,
    statistic: str,
    minimum_upstream_area_km2: float,
) -> tuple[float, dict[str, Any]]:
    summary = _hydrorivers_archive_summary(str(path), minimum_upstream_area_km2)
    values = {
        "hydrorivers_hack_fitted_exponent": summary["hack_fitted_exponent"],
        "hydrorivers_hack_fitted_log_rmse": summary["hack_fitted_log_rmse"],
    }
    metadata = {f"source_{key}": value for key, value in summary.items()}
    metadata["source_sample_record_count"] = summary["sample_network_count"]
    return float(values[statistic]), metadata


def _infer_source_format(path: Path, source: dict[str, Any]) -> str:
    explicit = source.get("format")
    if isinstance(explicit, str) and explicit:
        return explicit.lower()
    suffix = path.suffix.lower()
    if suffix in {".asc", ".ascii"}:
        return "esri_ascii_grid"
    if suffix in {".geojson", ".json"}:
        return "geojson"
    if suffix == ".shp":
        return "shapefile"
    raise CalibrationError(f"cannot infer calibration source format for {path}")


def _source_values(path: Path, source: dict[str, Any], statistic: str) -> tuple[str, list[float]]:
    source_format = _infer_source_format(path, source)
    if source_format in {"esri_ascii_grid", "ascii_grid", "asc"}:
        return "esri_ascii_grid", _read_esri_ascii_grid(path)
    if source_format in {"geojson", "featurecollection"}:
        return "geojson", _read_geojson_values(path, source, statistic)
    if source_format in {"shapefile", "esri_shapefile", "shp"}:
        return "shapefile", _read_shapefile_values(path, source, statistic)
    raise CalibrationError(f"unsupported calibration source format '{source_format}'")


def _shapefile_coordinate_metadata(path: Path, source: dict[str, Any]) -> dict[str, str]:
    metadata = {"source_coordinate_system": _coordinate_system_for_vector(path, source)}
    prj_path = _prj_path_for_shapefile(path, source)
    if "prj_path" in source or prj_path.exists():
        metadata["source_prj"] = str(prj_path)
    return metadata


def _shapefile_uses_coordinate_system(source: dict[str, Any], statistic: str) -> bool:
    if statistic == "feature_count":
        return False
    property_name = source.get("property")
    return not isinstance(property_name, str) or not property_name


def derive_calibration_targets(sources: list[dict[str, Any]]) -> dict[str, Any]:
    targets: list[dict[str, Any]] = []
    source_summaries: list[dict[str, Any]] = []

    for source in sources:
        dataset = _target_text(source, "dataset")
        layer = _target_text(source, "layer")
        source_metric = _target_text(source, "metric")
        world_metric = _target_text(source, "world_metric") if "world_metric" in source else source_metric
        path = Path(_target_text(source, "path"))
        if not path.exists():
            raise CalibrationError(f"calibration source does not exist: {path}")

        statistic = str(source.get("statistic", "mean")).lower()
        provenance_metadata = _source_provenance(path, source)
        sampling_metadata: dict[str, Any] = {}
        if statistic == _FIBONACCI_COASTAL_STATISTIC:
            source_format = _infer_source_format(path, source)
            if source_format not in {"shapefile", "esri_shapefile", "shp"}:
                raise CalibrationError(f"{_FIBONACCI_COASTAL_STATISTIC} requires a shapefile source")
            source_format = "shapefile"
            value, sampling_metadata = _fibonacci_coastal_land_fraction(path, source)
            values = [value]
        elif statistic in _FIBONACCI_RELIEF_STATISTICS:
            source_format = _infer_source_format(path, source)
            if source_format not in {"opendap_ascii_grid", "opendap_ascii", "dap_ascii"}:
                raise CalibrationError(f"{statistic} requires an OPeNDAP ASCII grid source")
            source_format = "opendap_ascii_grid"
            value, sampling_metadata = _fibonacci_relief_statistic(path, source, statistic)
            values = [value]
        elif statistic in _FIBONACCI_WORLDCLIM_STATISTICS:
            source_format = _infer_source_format(path, source)
            if source_format not in {"worldclim_geotiff_zip", "geotiff_zip"}:
                raise CalibrationError(f"{statistic} requires a WorldClim GeoTIFF ZIP source")
            source_format = "worldclim_geotiff_zip"
            value, sampling_metadata = _fibonacci_worldclim_statistic(path, source, statistic)
            values = [value]
        elif statistic in _HYDROBASINS_STATISTICS:
            source_format = _infer_source_format(path, source)
            if source_format not in {"hydrobasins_archive_catalog", "hydrobasins_catalog"}:
                raise CalibrationError(f"{statistic} requires a HydroBASINS archive catalog")
            source_format = "hydrobasins_archive_catalog"
            value, sampling_metadata = _hydrobasins_catalog_statistic(path, statistic)
            values = [value]
        elif statistic in _HYDRORIVERS_STATISTICS:
            source_format = _infer_source_format(path, source)
            if source_format not in {"hydrorivers_shapefile_zip", "hydrorivers_archive"}:
                raise CalibrationError(f"{statistic} requires a HydroRIVERS shapefile ZIP archive")
            source_format = "hydrorivers_shapefile_zip"
            minimum_upstream_area_km2 = _optional_float(
                source,
                "minimum_upstream_area_km2",
                HACK_FIT_MINIMUM_BASIN_AREA_KM2,
            )
            if abs(minimum_upstream_area_km2 - HACK_FIT_MINIMUM_BASIN_AREA_KM2) > 0.0001:
                raise CalibrationError(
                    "HydroRIVERS minimum_upstream_area_km2 must match the generated "
                    f"Hack-fit floor of {HACK_FIT_MINIMUM_BASIN_AREA_KM2} km2"
                )
            value, sampling_metadata = _hydrorivers_archive_statistic(
                path,
                statistic,
                minimum_upstream_area_km2,
            )
            values = [value]
        else:
            source_format, values = _source_values(path, source, statistic)
        source_metadata = (
            _shapefile_coordinate_metadata(path, source)
            if source_format == "shapefile" and _shapefile_uses_coordinate_system(source, statistic)
            else {}
        )
        source_metadata.update(provenance_metadata)
        source_metadata.update(sampling_metadata)
        if statistic in {
            "feature_count",
            _FIBONACCI_COASTAL_STATISTIC,
            *_FIBONACCI_RELIEF_STATISTICS,
            *_FIBONACCI_WORLDCLIM_STATISTICS,
            *_HYDROBASINS_STATISTICS,
            *_HYDRORIVERS_STATISTICS,
        }:
            value = values[0]
        else:
            value = _numeric_statistic(values, statistic)
        if not math.isfinite(value):
            raise CalibrationError(f"derived source value for '{source_metric}' must be finite")

        if "target_min" in source and "target_max" in source:
            target_min = _target_float(source, "target_min")
            target_max = _target_float(source, "target_max")
        else:
            if "tolerance_abs" in source:
                tolerance = _optional_float(source, "tolerance_abs", 0.0)
                if "tolerance_fraction" in source:
                    tolerance = max(tolerance, abs(value) * _optional_float(source, "tolerance_fraction", 0.0))
            else:
                tolerance = abs(value) * _optional_float(source, "tolerance_fraction", 0.05)
            target_min = value - tolerance
            target_max = value + tolerance

        if target_max < target_min:
            raise CalibrationError(f"derived target range for '{world_metric}' is inverted")
        value = round(value, 12)
        target_min = round(target_min, 12)
        target_max = round(target_max, 12)

        target = {
            "dataset": dataset,
            "layer": layer,
            "metric": world_metric,
            "source_metric": source_metric,
            "target_min": target_min,
            "target_max": target_max,
            "source": str(path),
            "source_format": source_format,
            "source_statistic": statistic,
            "source_value": value,
        }
        target.update(source_metadata)
        if "property" in source:
            target["source_property"] = source["property"]
            if source_format == "shapefile":
                target["source_dbf"] = str(_dbf_path_for_shapefile(path, source))
        if "geometry_metric" in source:
            target["source_geometry_metric"] = source["geometry_metric"]
        if "tolerance_basis" in source:
            target["tolerance_basis"] = _target_text(source, "tolerance_basis")
        targets.append(target)
        summary_metadata: dict[str, Any] = {
            "sha256": provenance_metadata["source_sha256"],
        }
        for key in _SOURCE_PROVENANCE_FIELDS:
            if key in provenance_metadata:
                summary_metadata[key] = provenance_metadata[key]
        if "source_archive_sha256" in provenance_metadata:
            summary_metadata["source_archive_sha256"] = provenance_metadata["source_archive_sha256"]
        if source_metadata:
            if "source_coordinate_system" in source_metadata:
                summary_metadata["coordinate_system"] = source_metadata["source_coordinate_system"]
            if "source_prj" in source_metadata:
                summary_metadata["prj_path"] = source_metadata["source_prj"]
        if sampling_metadata:
            summary_metadata.update(
                {
                    key.removeprefix("source_"): value
                    for key, value in sampling_metadata.items()
                }
            )
        source_summaries.append(
            {
                "dataset": dataset,
                "layer": layer,
                "metric": source_metric,
                "world_metric": world_metric,
                "path": str(path),
                "format": source_format,
                "statistic": statistic,
                "value": value,
                "sample_count": sampling_metadata.get(
                    "source_sample_record_count",
                    sampling_metadata.get("source_sample_cell_count", len(values)),
                ),
                **summary_metadata,
                **(
                    {"property": source["property"], "dbf_path": str(_dbf_path_for_shapefile(path, source))}
                    if "property" in source and source_format == "shapefile"
                    else {}
                ),
                **({"geometry_metric": source["geometry_metric"]} if "geometry_metric" in source else {}),
                **({"tolerance_basis": _target_text(source, "tolerance_basis")} if "tolerance_basis" in source else {}),
            }
        )

    return {
        "summary": {
            "derived_target_count": len(targets),
            "source_count": len(source_summaries),
            "mapped_target_count": sum(1 for target in targets if target["source_metric"] != target["metric"]),
            "unique_world_metric_count": len({str(target["metric"]) for target in targets}),
        },
        "targets": targets,
        "source_summaries": source_summaries,
    }


def _world_metric_values(world: dict[str, Any]) -> dict[str, float]:
    values: dict[str, float] = {}
    checks = world.get("calibration_checks", [])
    if not isinstance(checks, list):
        raise CalibrationError("world calibration_checks must be a list")
    for check in checks:
        if not isinstance(check, dict):
            raise CalibrationError("each world calibration check must be an object")
        metric = check.get("metric")
        if isinstance(metric, str) and "value" in check:
            try:
                value = float(check["value"])
            except (TypeError, ValueError) as exc:
                raise CalibrationError(f"world calibration metric '{metric}' must be numeric") from exc
            if not math.isfinite(value):
                raise CalibrationError(f"world calibration metric '{metric}' must be finite")
            if metric in values and values[metric] != value:
                raise CalibrationError(f"world calibration metric '{metric}' is duplicated with conflicting values")
            values[metric] = value

    cells = world.get("cells", [])
    if isinstance(cells, list) and cells:
        for cell in cells:
            if not isinstance(cell, dict):
                raise CalibrationError("each world cell must be an object")
        elevation_presence = ["elevation_m" in cell for cell in cells]
        if any(elevation_presence) and not all(elevation_presence):
            raise CalibrationError("world cell elevation_m must be present for every cell or no cells")
        if all(elevation_presence):
            surface_elevations: list[float] = []
            for cell in cells:
                try:
                    elevation = float(cell["elevation_m"])
                except (TypeError, ValueError) as exc:
                    raise CalibrationError("world cell elevation_m must be numeric") from exc
                if not math.isfinite(elevation):
                    raise CalibrationError("world cell elevation_m must be finite")
                surface_elevations.append(elevation)
            nonnegative_elevations = [elevation for elevation in surface_elevations if elevation >= 0.0]
            if not nonnegative_elevations:
                raise CalibrationError("world has no nonnegative surface elevations")
            derived_surface_values = {
                "below_sea_level_surface_fraction": (
                    sum(elevation < 0.0 for elevation in surface_elevations) / len(surface_elevations)
                ),
                "mean_nonnegative_surface_elevation_m": (
                    sum(nonnegative_elevations) / len(nonnegative_elevations)
                ),
                "surface_elevation_span_m": max(surface_elevations) - min(surface_elevations),
            }
            for metric, derived_value in derived_surface_values.items():
                if metric in values and abs(values[metric] - derived_value) > 0.001:
                    raise CalibrationError(f"world calibration metric '{metric}' conflicts with cell-derived value")
                values.setdefault(metric, derived_value)

        initial_age_ledger = world.get("initial_oceanic_crust_age_ledger")
        if initial_age_ledger is not None:
            if not isinstance(initial_age_ledger, dict):
                raise CalibrationError(
                    "world initial_oceanic_crust_age_ledger must be an object"
                )
            ages = initial_age_ledger.get("age_ma_by_cell")
            statuses = initial_age_ledger.get("status_id_by_cell")
            thresholds = initial_age_ledger.get("cdf_thresholds_ma")
            recorded_cdf = initial_age_ledger.get(
                "area_weighted_cdf_le_threshold"
            )
            if (
                not isinstance(ages, list)
                or not isinstance(statuses, list)
                or len(ages) != len(cells)
                or len(statuses) != len(cells)
                or not isinstance(thresholds, list)
                or not isinstance(recorded_cdf, list)
                or len(thresholds) != len(recorded_cdf)
            ):
                raise CalibrationError(
                    "world initial oceanic crust age ledger has invalid cardinality"
                )
            expected_thresholds = [
                20.0,
                40.0,
                60.0,
                80.0,
                100.0,
                120.0,
                140.0,
                160.0,
                180.0,
                200.0,
            ]
            try:
                age_values = [float(value) for value in ages]
                status_values = [int(value) for value in statuses]
                threshold_values = [float(value) for value in thresholds]
                recorded_cdf_values = [float(value) for value in recorded_cdf]
                cell_areas = [float(cell["area_km2"]) for cell in cells]
            except (KeyError, TypeError, ValueError, OverflowError) as exc:
                raise CalibrationError(
                    "world initial oceanic crust age ledger must be numeric"
                ) from exc
            if (
                threshold_values != expected_thresholds
                or any(
                    not math.isfinite(age) or age < 0.0
                    for age in age_values
                )
                or any(status not in range(5) for status in status_values)
                or any(
                    not math.isfinite(area) or area <= 0.0
                    for area in cell_areas
                )
                or any(
                    not math.isfinite(value) or not 0.0 <= value <= 1.0
                    for value in recorded_cdf_values
                )
            ):
                raise CalibrationError(
                    "world initial oceanic crust age ledger values are invalid"
                )
            oceanic_rows = [
                (age, area)
                for age, area, status in zip(
                    age_values,
                    cell_areas,
                    status_values,
                    strict=True,
                )
                if status != 0
            ]
            if not oceanic_rows:
                raise CalibrationError(
                    "world initial oceanic crust age ledger has no oceanic-like cells"
                )
            total_oceanic_area = math.fsum(area for _, area in oceanic_rows)
            mean_age = math.fsum(
                age * area for age, area in oceanic_rows
            ) / total_oceanic_area
            derived_cdf = [
                math.fsum(
                    area
                    for age, area in oceanic_rows
                    if age <= threshold
                )
                / total_oceanic_area
                for threshold in threshold_values
            ]
            recorded_mean = float(
                initial_age_ledger.get("area_weighted_mean_age_ma", math.nan)
            )
            if (
                not math.isfinite(recorded_mean)
                or abs(recorded_mean - mean_age) > 1.0e-9
                or any(
                    abs(recorded - derived) > 1.0e-12
                    for recorded, derived in zip(
                        recorded_cdf_values,
                        derived_cdf,
                        strict=True,
                    )
                )
            ):
                raise CalibrationError(
                    "world initial oceanic crust age ledger summaries conflict with cell-derived values"
                )
            values[
                "initial_oceanic_crust_age_area_weighted_mean_ma"
            ] = mean_age
            for threshold, cdf_value in zip(
                threshold_values,
                derived_cdf,
                strict=True,
            ):
                values[
                    "initial_oceanic_crust_age_area_weighted_cdf_le_"
                    f"{int(threshold)}_ma"
                ] = cdf_value

        annual_land_temperatures: list[float] = []
        annual_land_temperature_ranges: list[float] = []
        annual_land_precipitation: list[float] = []
        for cell in cells:
            if not isinstance(cell, dict):
                raise CalibrationError("each world cell must be an object")
            if bool(cell.get("is_water", False)):
                continue
            monthly = cell.get("temperature_monthly_c")
            if not isinstance(monthly, list) or len(monthly) != 12:
                raise CalibrationError("land cells require twelve monthly temperatures for external climate calibration")
            try:
                monthly_values = [float(value) for value in monthly]
                precipitation = float(cell["precipitation_mm_y"])
            except (KeyError, TypeError, ValueError) as exc:
                raise CalibrationError("world land climate values must be numeric") from exc
            if not all(math.isfinite(value) for value in [*monthly_values, precipitation]):
                raise CalibrationError("world land climate values must be finite")
            annual_land_temperatures.append(sum(monthly_values) / 12.0)
            annual_land_temperature_ranges.append(max(monthly_values) - min(monthly_values))
            annual_land_precipitation.append(precipitation)
        if annual_land_temperatures:
            derived_values = {
                "mean_land_annual_temperature_c": sum(annual_land_temperatures) / len(annual_land_temperatures),
                "mean_land_annual_temperature_range_c": (
                    sum(annual_land_temperature_ranges) / len(annual_land_temperature_ranges)
                ),
                "mean_land_precipitation_mm_y": sum(annual_land_precipitation) / len(annual_land_precipitation),
            }
            for metric, derived_value in derived_values.items():
                if metric in values:
                    if abs(values[metric] - derived_value) > 0.001:
                        raise CalibrationError(
                            f"world calibration metric '{metric}' conflicts with cell-derived value"
                        )
                else:
                    values[metric] = derived_value

    watersheds = world.get("watersheds", [])
    if isinstance(watersheds, list) and watersheds:
        if not all(isinstance(watershed, dict) for watershed in watersheds):
            raise CalibrationError("each world watershed must be an object")
        hack_length_presence = ["main_channel_length_km" in watershed for watershed in watersheds]
        if any(hack_length_presence) and not all(hack_length_presence):
            raise CalibrationError("world watersheds must provide main_channel_length_km consistently")
        if not all(
            "is_endorheic" in watershed and "outlet_type" in watershed
            for watershed in watersheds
        ):
            raise CalibrationError(
                "world watersheds must provide is_endorheic and outlet_type consistently"
            )
        hack_observations: list[tuple[float, float]] = []
        exorheic_backbone_hack_observations: list[tuple[float, float]] = []
        watershed_count = 0
        endorheic_count = 0
        watershed_area = 0.0
        endorheic_area = 0.0
        for watershed in watersheds:
            try:
                area = float(watershed["area_km2"])
            except (KeyError, TypeError, ValueError) as exc:
                raise CalibrationError("world watershed area_km2 must be numeric") from exc
            if not math.isfinite(area) or area <= 0.0:
                raise CalibrationError("world watershed area_km2 must be finite and positive")
            if all(hack_length_presence):
                try:
                    main_channel_length = float(watershed["main_channel_length_km"])
                except (TypeError, ValueError) as exc:
                    raise CalibrationError("world watershed main_channel_length_km must be numeric") from exc
                if not math.isfinite(main_channel_length) or main_channel_length < 0.0:
                    raise CalibrationError(
                        "world watershed main_channel_length_km must be finite and nonnegative"
                    )
                if (
                    main_channel_length > 0.0
                    and area >= HACK_FIT_MINIMUM_BASIN_AREA_KM2
                ):
                    hack_observations.append((area, main_channel_length))
            is_endorheic_raw = watershed["is_endorheic"]
            outlet_type_raw = watershed["outlet_type"]
            if not isinstance(is_endorheic_raw, bool):
                raise CalibrationError(
                    "world watershed is_endorheic must be boolean"
                )
            if not isinstance(outlet_type_raw, str) or not outlet_type_raw:
                raise CalibrationError(
                    "world watershed outlet_type must be a non-empty string"
                )
            is_endorheic = is_endorheic_raw
            outlet_type = outlet_type_raw
            if (outlet_type == "ocean") == is_endorheic:
                raise CalibrationError(
                    "world watershed ocean outlet_type conflicts with is_endorheic"
                )
            if (
                all(hack_length_presence)
                and not is_endorheic
                and outlet_type == "ocean"
                and main_channel_length > 0.0
                and area >= HACK_FIT_MINIMUM_BASIN_AREA_KM2
            ):
                exorheic_backbone_hack_observations.append(
                    (area, main_channel_length)
                )
            watershed_count += 1
            watershed_area += area
            if is_endorheic:
                endorheic_count += 1
                endorheic_area += area
        derived_watershed_values = {
            "endorheic_watershed_fraction": endorheic_count / watershed_count,
            "endorheic_watershed_area_fraction": endorheic_area / watershed_area,
        }
        centroid_presence = ["centroid_lat_deg" in watershed for watershed in watersheds]
        if any(centroid_presence) and not all(centroid_presence):
            raise CalibrationError("world watersheds must provide centroid_lat_deg consistently")
        if all(centroid_presence):
            coverage_watershed_count = 0
            coverage_endorheic_count = 0
            coverage_watershed_area = 0.0
            coverage_endorheic_area = 0.0
            for watershed in watersheds:
                try:
                    centroid_latitude = float(watershed["centroid_lat_deg"])
                except (TypeError, ValueError) as exc:
                    raise CalibrationError("world watershed centroid_lat_deg must be numeric") from exc
                if not math.isfinite(centroid_latitude) or not -90.0 <= centroid_latitude <= 90.0:
                    raise CalibrationError("world watershed centroid_lat_deg must be finite and within [-90, 90]")
                if centroid_latitude < _HYDROBASINS_GENERATED_MIN_CENTROID_LAT_DEG:
                    continue
                area = float(watershed["area_km2"])
                is_endorheic = watershed["is_endorheic"]
                coverage_watershed_count += 1
                coverage_watershed_area += area
                if is_endorheic:
                    coverage_endorheic_count += 1
                    coverage_endorheic_area += area
            if coverage_watershed_count == 0 or coverage_watershed_area <= 0.0:
                raise CalibrationError("world has no watersheds in HydroBASINS non-Antarctic coverage")
            derived_watershed_values.update(
                {
                    "non_antarctic_endorheic_watershed_fraction": (
                        coverage_endorheic_count / coverage_watershed_count
                    ),
                    "non_antarctic_endorheic_watershed_area_fraction": (
                        coverage_endorheic_area / coverage_watershed_area
                    ),
                }
            )
        if len(hack_observations) >= 2:
            try:
                hack_fit = fit_power_law(hack_observations)
            except ValueError as exc:
                raise CalibrationError("world watershed Hack fit is invalid") from exc
            derived_watershed_values.update(
                {
                    "watershed_hack_fitted_exponent": hack_fit.exponent,
                    "watershed_hack_fitted_coefficient": hack_fit.coefficient,
                    "watershed_hack_fitted_log_rmse": hack_fit.log_rmse,
                    "watershed_hack_fitted_observation_count": float(hack_fit.observation_count),
                }
            )
        if (
            len(exorheic_backbone_hack_observations) >= 2
            and len({area for area, _ in exorheic_backbone_hack_observations}) >= 2
        ):
            try:
                exorheic_hack_fit = fit_power_law(
                    exorheic_backbone_hack_observations
                )
            except ValueError as exc:
                raise CalibrationError(
                    "world exorheic watershed-backbone Hack fit is invalid"
                ) from exc
            derived_watershed_values.update(
                {
                    "exorheic_watershed_backbone_hack_fitted_exponent": (
                        exorheic_hack_fit.exponent
                    ),
                    "exorheic_watershed_backbone_hack_fitted_coefficient": (
                        exorheic_hack_fit.coefficient
                    ),
                    "exorheic_watershed_backbone_hack_fitted_log_rmse": (
                        exorheic_hack_fit.log_rmse
                    ),
                    "exorheic_watershed_backbone_hack_fitted_observation_count": float(
                        exorheic_hack_fit.observation_count
                    ),
                }
            )
        for metric, derived_value in derived_watershed_values.items():
            if metric in values:
                if abs(values[metric] - derived_value) > 0.001:
                    raise CalibrationError(
                        f"world calibration metric '{metric}' conflicts with watershed-derived value"
                    )
            else:
                values[metric] = derived_value
    return values


def evaluate_calibration_targets(world: dict[str, Any], targets: list[dict[str, Any]]) -> dict[str, Any]:
    values = _world_metric_values(world)
    checks: list[dict[str, Any]] = []
    pass_count = 0
    score_sum = 0.0
    missing_count = 0
    missing_metrics: set[str] = set()

    for target in targets:
        dataset = _target_text(target, "dataset")
        layer = _target_text(target, "layer")
        metric = _target_text(target, "metric")
        source_metric = _target_text(target, "source_metric") if "source_metric" in target else metric
        target_min = _target_float(target, "target_min")
        target_max = _target_float(target, "target_max")
        if target_max < target_min:
            raise CalibrationError(f"target range for '{metric}' is inverted")

        value = values.get(metric)
        missing = value is None
        if missing:
            score = 0.0
            passed = False
            missing_count += 1
            missing_metrics.add(metric)
        else:
            score = round(score_range(value, target_min, target_max), 6)
            passed = target_min <= value <= target_max

        if passed:
            pass_count += 1
        score_sum += score
        source_metadata = {
            key: value
            for key, value in target.items()
            if key.startswith("source_") and key != "source_metric"
        }
        target_metadata = (
            {"tolerance_basis": _target_text(target, "tolerance_basis")}
            if "tolerance_basis" in target
            else {}
        )
        checks.append(
            {
                "id": len(checks),
                "dataset": dataset,
                "layer": layer,
                "metric": metric,
                "source_metric": source_metric,
                "value": value,
                "target_min": target_min,
                "target_max": target_max,
                "score": score,
                "passed": passed,
                "missing_metric": missing,
                "source": str(target.get("source", "external_target")),
                **source_metadata,
                **target_metadata,
            }
        )

    count = len(checks)
    evaluated_count = count - missing_count
    return {
        "summary": {
            "external_calibration_check_count": count,
            "external_calibration_evaluated_metric_count": evaluated_count,
            "external_calibration_pass_count": pass_count,
            "external_calibration_missing_metric_count": missing_count,
            "external_calibration_metric_coverage_fraction": round(evaluated_count / count, 6) if count else 0.0,
            "external_calibration_pass_fraction": round(pass_count / count, 6) if count else 0.0,
            "external_calibration_evaluated_pass_fraction": (
                round(pass_count / evaluated_count, 6) if evaluated_count else 0.0
            ),
            "external_mean_calibration_score": round(score_sum / count, 6) if count else 0.0,
            "external_mean_evaluated_calibration_score": (
                round(score_sum / evaluated_count, 6) if evaluated_count else 0.0
            ),
            "external_calibration_complete": missing_count == 0 and count > 0,
        },
        "available_world_metrics": sorted(values),
        "missing_world_metrics": sorted(missing_metrics),
        "checks": checks,
    }


def write_calibration_markdown(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    summary = report.get("summary", {})
    lines = ["# Calibration Report", "", "## Summary", ""]
    for key in [
        "external_calibration_check_count",
        "external_calibration_evaluated_metric_count",
        "external_calibration_pass_count",
        "external_calibration_missing_metric_count",
        "external_calibration_metric_coverage_fraction",
        "external_calibration_pass_fraction",
        "external_calibration_evaluated_pass_fraction",
        "external_mean_calibration_score",
        "external_mean_evaluated_calibration_score",
        "external_calibration_complete",
    ]:
        if key in summary:
            lines.append(f"- `{key}`: {summary[key]}")
    lines.extend(["", "## Checks", ""])
    for check in report.get("checks", []):
        status = "missing" if check.get("missing_metric") else ("pass" if check.get("passed") else "fail")
        source_metric = check.get("source_metric")
        mapping = f", source_metric={source_metric}" if source_metric != check.get("metric") else ""
        provenance = ""
        if check.get("source_version"):
            provenance += f", source_version={check.get('source_version')}"
        if check.get("source_sha256"):
            provenance += f", source_sha256={check.get('source_sha256')}"
        if check.get("tolerance_basis"):
            provenance += f", tolerance_basis={check.get('tolerance_basis')}"
        lines.append(
            f"- `{check.get('metric')}` ({check.get('dataset')}/{check.get('layer')}): {status}, "
            f"value={check.get('value')}, target=[{check.get('target_min')}, {check.get('target_max')}], "
            f"score={check.get('score')}{mapping}{provenance}"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_target_derivation_markdown(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    summary = report.get("summary", {})
    lines = ["# Calibration Target Derivation", "", "## Summary", ""]
    for key in ["derived_target_count", "source_count", "mapped_target_count", "unique_world_metric_count"]:
        if key in summary:
            lines.append(f"- `{key}`: {summary[key]}")
    lines.extend(["", "## Targets", ""])
    for target in report.get("targets", []):
        source_metric = target.get("source_metric")
        mapping = f", source_metric={source_metric}" if source_metric != target.get("metric") else ""
        provenance = ""
        if target.get("source_version"):
            provenance += f", source_version={target.get('source_version')}"
        if target.get("source_sha256"):
            provenance += f", source_sha256={target.get('source_sha256')}"
        if target.get("tolerance_basis"):
            provenance += f", tolerance_basis={target.get('tolerance_basis')}"
        lines.append(
            f"- `{target.get('metric')}` ({target.get('dataset')}/{target.get('layer')}): "
            f"value={target.get('source_value')}, target=[{target.get('target_min')}, {target.get('target_max')}], "
            f"source={target.get('source')}{mapping}{provenance}"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
