"""Version routing for independent climate validation, without producer imports.

Native certificates may be raw or enriched. Their physical audit always needs
full cell linkage here; optional Python annual mirrors have a separate scope.
"""
from __future__ import annotations

import math
from typing import Any

from .native_climate_energy_validation import (
    NativeClimateEnergyValidationError,
    audit_native_climate_energy,
)
from .native_climate_energy_enrichment_validation import validate_native_climate_energy_enrichment


_LEGACY_ENERGY_MODEL = {
    "insolation_method": "kepler_equal_time_months_true_anomaly_quadrature_v2",
    "orbital_quadrature": "midpoint_true_anomaly_with_exact_kepler_time_weights",
    "minimum_samples_per_orbit": 768,
    "maximum_true_anomaly_step_rad": 2.0 * math.pi / 768,
    "orbital_eccentricity_range": "[0,1)",
    "calendar": "equal_duration_months_periapsis_at_month_zero_center",
    "solar_longitude_at_periapsis_deg": -75.0,
    "semimajor_axis_au": 1.0,
    "solar_constant_w_m2": 1361.0,
    "daily_rotation_averaged": True,
    "orbital_motion_during_rotation_resolved": False,
    "native_temperature_forcing_coupled": False,
    "albedo_greenhouse_model": "posthoc_empirical_graybody_surface_diagnostic_v2",
    "surface_longwave_emissivity": 0.96,
    "global_energy_conservation_resolved": False,
    "mean_summary_weighting": "cell_count",
    "area_weighted_summary_weighting": "cell_area_km2_complete_coverage_only",
}

_LEGACY_CELL_FIELDS = frozenset({
    "top_of_atmosphere_insolation_w_m2", "surface_albedo_index",
    "absorbed_shortwave_w_m2", "outgoing_longwave_w_m2",
    "greenhouse_trapping_w_m2", "net_radiative_balance_w_m2",
    "no_greenhouse_equilibrium_temperature_c", "radiative_equilibrium_temperature_c",
    "energy_balance_residual_c", "climate_energy_stress_index", "surface_albedo_regime",
    "seasonal_insolation_range_w_m2", "orbital_insolation_variability_index",
    "peak_seasonal_insolation_w_m2", "low_seasonal_insolation_w_m2",
})
_LEGACY_SUMMARY_FIELDS = frozenset({
    "climate_energy_balance_record_count", "mean_top_of_atmosphere_insolation_w_m2",
    "mean_surface_albedo_index", "mean_absorbed_shortwave_w_m2",
    "mean_outgoing_longwave_w_m2", "mean_greenhouse_trapping_w_m2",
    "mean_net_radiative_balance_w_m2", "mean_abs_energy_balance_residual_c",
    "mean_climate_energy_stress_index", "mean_seasonal_insolation_range_w_m2",
    "mean_orbital_insolation_variability_index", "mean_peak_seasonal_insolation_w_m2",
    "mean_low_seasonal_insolation_w_m2", "mean_orbital_distance_factor",
    "high_climate_energy_stress_cell_count", "surface_albedo_regime_counts",
    "climate_energy_valid_area_cell_count", "climate_energy_represented_area_km2",
    "climate_energy_area_weighted_summary_available",
    *(f"area_weighted_mean_{field}" for field in (
        "top_of_atmosphere_insolation_w_m2", "absorbed_shortwave_w_m2",
        "outgoing_longwave_w_m2", "greenhouse_trapping_w_m2", "net_radiative_balance_w_m2",
    )),
})


def climate_energy_validation_mode(world: dict[str, Any]) -> str:
    """Route known or partial native envelopes to the strict physical audit.

    Absent legacy declarations still reach the existing legacy missing-field
    checks. A present unknown declaration never becomes a legacy fallback.
    """
    if not isinstance(world, dict):
        raise ValueError("climate energy validation requires a world object")
    if any(key in world for key in (
        "climate_energy_forcing_intervals", "climate_energy_transport_edges",
        "native_climate_energy_enrichment_model",
    )):
        return "native"
    prefixes = (
        "native_prescribed_seasonal_energy_", "prescribed_seasonal_surface_energy_",
        "periodic_graybody_storage_conservative_transport_",
    )
    for key in ("climate_model", "climate_energy_model"):
        declaration = world.get(key)
        if isinstance(declaration, dict):
            if (
                declaration.get("native_temperature_forcing_coupled") is True
                or declaration.get("ownership") == "native_temperature_producer"
                or declaration.get("temperature_source") == "climate_energy_balance_records_monthly_mean_temperature_k"
            ):
                return "native"
            values = (declaration.get(field) for field in ("model", "model_type", "temperature_model"))
        else:
            values = (declaration,)
        if any(isinstance(value, str) and value.startswith(prefixes) for value in values):
            return "native"
    for key, field, expected in (
        ("climate_model", "model_type", "equilibrium_latitude_circulation_climate_v5"),
        ("climate_energy_model", "albedo_greenhouse_model", "posthoc_empirical_graybody_surface_diagnostic_v2"),
    ):
        if key in world:
            declaration = world[key]
            if not isinstance(declaration, dict) or declaration.get(field) != expected:
                raise ValueError(f"{key}: unknown or malformed climate declaration")
    if "climate_energy_model" in world:
        declaration = world["climate_energy_model"]
        if declaration != _LEGACY_ENERGY_MODEL or any(
            isinstance(expected, (bool, int)) and type(declaration.get(key)) is not type(expected)
            for key, expected in _LEGACY_ENERGY_MODEL.items()
        ):
            raise ValueError("climate_energy_model: unknown or malformed legacy energy declaration")
    return "legacy"


def validate_native_climate_energy_output(world: dict[str, Any]) -> tuple[list[str], dict[str, Any] | None]:
    """Audit the full native output and reject unavailable posthoc aliases."""
    try:
        report = audit_native_climate_energy(world, require_cell_linkage=True)
    except NativeClimateEnergyValidationError as error:
        return [f"native climate energy: {error}"], None
    for cell in world["cells"]:
        stale = sorted(_LEGACY_CELL_FIELDS.intersection(cell))
        if stale:
            return [f"native climate energy: cell {cell['id']} has unavailable legacy posthoc field {stale[0]}"], None
    summary = world.get("summary", {})
    if not isinstance(summary, dict):
        return ["native climate energy: summary must be an object"], None
    stale = sorted(_LEGACY_SUMMARY_FIELDS.intersection(summary))
    if stale:
        return [f"native climate energy: summary has unavailable legacy posthoc field {stale[0]}"], None
    mirror_errors = validate_native_climate_energy_enrichment(world)
    if mirror_errors:
        return mirror_errors, None
    return [], report
