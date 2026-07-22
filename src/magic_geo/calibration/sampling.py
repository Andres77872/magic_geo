"""Fibonacci-sphere sampling of reference datasets."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ._constants import _FIBONACCI_COASTAL_STATISTIC
from .errors import CalibrationError
from ._helpers import _coordinate_system_for_vector, _fibonacci_points, _file_sha256, _masked_component_sizes, _nearest_coordinate_index, _optional_float, _optional_int, _point_in_polygon_feature, _symmetric_nearest_neighbors
from .readers import _read_opendap_ascii_grid, _read_shapefile_records, _worldclim_monthly_samples


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
