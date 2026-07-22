"""Format-specific readers for raster, vector, and archive datasets."""

from __future__ import annotations

import hashlib
import json
import math
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, BinaryIO, Iterator

import struct
from zipfile import BadZipFile, ZipFile

from ..geotiff import GeoTiffError, GeoTiffMetadata, GeoTiffRaster
from ..scaling import fit_power_law
from ._constants import _SHA256_PATTERN
from .errors import CalibrationError
from ._helpers import _comma_separated_floats, _coordinate_system_for_vector, _fibonacci_points, _file_sha256, _next_nonempty_line, _part_ranges, _ring_area_km2, _segment_length_km, _target_text


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
