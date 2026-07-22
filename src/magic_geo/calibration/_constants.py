"""Module-level constants shared by the submodules."""

from __future__ import annotations

import re


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
