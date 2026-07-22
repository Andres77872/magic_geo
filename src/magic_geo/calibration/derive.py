"""Deriving target ranges from configured sources."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from ..scaling import HACK_FIT_MINIMUM_BASIN_AREA_KM2
from ._constants import (
    _FIBONACCI_COASTAL_STATISTIC,
    _FIBONACCI_RELIEF_STATISTICS,
    _FIBONACCI_WORLDCLIM_STATISTICS,
    _HYDROBASINS_STATISTICS,
    _HYDRORIVERS_STATISTICS,
    _SOURCE_PROVENANCE_FIELDS,
)
from .errors import CalibrationError
from ._helpers import _coordinate_system_for_vector, _numeric_statistic, _optional_float, _prj_path_for_shapefile, _source_provenance, _target_float, _target_text
from .readers import _dbf_path_for_shapefile, _hydrobasins_catalog_statistic, _hydrorivers_archive_statistic, _read_esri_ascii_grid, _read_geojson_values, _read_shapefile_values
from .sampling import _fibonacci_coastal_land_fraction, _fibonacci_relief_statistic, _fibonacci_worldclim_statistic


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
