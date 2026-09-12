"""Atomic annual mirrors of an independently validated native climate budget.

This module does not solve temperature or supply an additional greenhouse,
ecological-stress, or equilibrium-temperature diagnostic. The retained native
coefficients, forcing, graph, trajectory moments and ledger remain authoritative.
"""

from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, localcontext
import math
from typing import Any


ENRICHMENT_MODEL = {
    "model": "native_climate_energy_annual_aggregation_v1",
    "native_budget_model": "native_prescribed_seasonal_energy_v1",
    "ownership": "python_derived_native_budget_mirrors",
    "annual_weighting": "native_monthly_duration_seconds",
    "planetary_weighting": "native_balance_record_area_m2_complete_coverage",
    "compatibility_mean_weighting": "cell_count",
    "coefficient_source": "native_climate_energy_balance_records",
    "net_radiative_flux": "absorbed_shortwave_minus_emitted_longwave",
    "net_heating": "net_radiative_flux_plus_horizontal_heat_convergence",
    "residual_sign": "heat_storage_minus_net_heating",
    "numerical_allowance": "duration_mean_of_native_monthly_balance_tolerance_not_heat_source",
    "native_authority_policy": "preserve_models_coefficients_records_forcing_edges_and_temperature_aliases",
    "legacy_alias_policy": "reject_before_mutation",
    "existing_native_alias_policy": "recompute_only_with_matching_enrichment_model",
    "validation_scope": "native_budget_algebra_and_linkage_not_unexported_trajectory_replay",
}

# Only aliases actually published by the legacy climate_energy module. Generic
# orbital configuration and seasonal diagnostics belong to other producers too.
LEGACY_CELL_ALIASES = frozenset({
    "top_of_atmosphere_insolation_w_m2", "surface_albedo_index",
    "absorbed_shortwave_w_m2", "outgoing_longwave_w_m2",
    "greenhouse_trapping_w_m2", "net_radiative_balance_w_m2",
    "no_greenhouse_equilibrium_temperature_c", "radiative_equilibrium_temperature_c",
    "energy_balance_residual_c", "climate_energy_stress_index", "surface_albedo_regime",
    "seasonal_insolation_range_w_m2", "orbital_insolation_variability_index",
    "peak_seasonal_insolation_w_m2", "low_seasonal_insolation_w_m2",
})
LEGACY_SUMMARY_ALIASES = frozenset({
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
    *{
        f"area_weighted_mean_{field}" for field in (
            "top_of_atmosphere_insolation_w_m2", "absorbed_shortwave_w_m2",
            "outgoing_longwave_w_m2", "greenhouse_trapping_w_m2", "net_radiative_balance_w_m2",
        )
    },
})
ANNUAL_MONTHLY_FIELDS = {
    "annual_absorbed_shortwave_w_m2": "monthly_absorbed_shortwave_w_m2",
    "annual_emitted_longwave_w_m2": "monthly_emitted_longwave_w_m2",
    "annual_horizontal_heat_convergence_w_m2": "monthly_horizontal_heat_convergence_w_m2",
    "annual_heat_storage_tendency_w_m2": "monthly_heat_storage_tendency_w_m2",
    "annual_energy_balance_residual_w_m2": "monthly_balance_residual_w_m2",
    "annual_mean_energy_balance_numerical_allowance_w_m2": "monthly_balance_tolerance_w_m2",
}
CELL_FIELDS = frozenset({
    "effective_toa_albedo", "effective_longwave_emissivity",
    "annual_net_radiative_flux_w_m2", "annual_net_heating_w_m2",
    "annual_mean_abs_energy_balance_residual_w_m2", *ANNUAL_MONTHLY_FIELDS,
})
SUMMARY_FIELDS = frozenset({
    "native_climate_energy_record_count", "native_climate_energy_total_area_m2",
    "native_climate_energy_year_duration_seconds",
    *(f"{prefix}_{field}" for prefix in ("cell_count_mean", "area_weighted_mean") for field in CELL_FIELDS),
})


def _decimal(value: Any, label: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"native climate annual aggregation requires finite numeric {label}")
    try:
        converted = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"native climate annual aggregation cannot represent {label}") from exc
    if not math.isfinite(converted):
        raise ValueError(f"native climate annual aggregation requires finite numeric {label}")
    return Decimal.from_float(converted)


def _finite_float(value: Decimal, label: str) -> float:
    converted = float(value)
    if not math.isfinite(converted):
        raise ValueError(f"native climate annual aggregation cannot represent {label}")
    return converted


def _annual_patches(world: dict[str, Any]) -> tuple[dict[int, dict[str, float]], dict[str, Any]]:
    """Accumulate without binary64 product overflow; never mutate the input."""
    records = world["climate_energy_balance_records"]
    with localcontext() as context:
        # Exact products of binary64 inputs span fewer than 2,800 decimal
        # places, including subnormals. Keep small signed budgets even when
        # large opposing terms cancel; a conventional 80-digit context can
        # otherwise erase them before division. Output remains binary64.
        context.prec = 3200
        durations = [_decimal(value, "monthly duration") for value in world["climate_energy_model"]["monthly_duration_seconds"]]
        year = sum(durations, Decimal(0))
        if len(durations) != 12 or any(duration <= 0 for duration in durations):
            raise ValueError("native climate annual aggregation requires twelve positive monthly durations")
        year_float = _finite_float(year, "year duration")
        areas = [_decimal(record["area_m2"], "record area") for record in records]
        if not areas or any(area <= 0 for area in areas):
            raise ValueError("native climate annual aggregation requires positive complete record areas")
        total_area = sum(areas, Decimal(0))
        area_float = _finite_float(total_area, "total physical area")

        def annual(series: list[float]) -> Decimal:
            if not isinstance(series, list) or len(series) != 12:
                raise ValueError("native climate annual aggregation requires twelve monthly values")
            return sum((_decimal(value, "monthly budget") * duration for value, duration in zip(series, durations)), Decimal(0)) / year

        patches: dict[int, dict[str, float]] = {}
        for record in records:
            values = {target: annual(record[source]) for target, source in ANNUAL_MONTHLY_FIELDS.items()}
            values["effective_toa_albedo"] = _decimal(record["top_of_atmosphere_albedo"], "effective TOA albedo")
            values["effective_longwave_emissivity"] = _decimal(record["effective_longwave_emissivity"], "effective longwave emissivity")
            values["annual_net_radiative_flux_w_m2"] = values["annual_absorbed_shortwave_w_m2"] - values["annual_emitted_longwave_w_m2"]
            values["annual_net_heating_w_m2"] = values["annual_net_radiative_flux_w_m2"] + values["annual_horizontal_heat_convergence_w_m2"]
            values["annual_mean_abs_energy_balance_residual_w_m2"] = annual([abs(value) for value in record["monthly_balance_residual_w_m2"]])
            patches[record["cell_id"]] = {key: _finite_float(value, key) for key, value in values.items()}

        summary: dict[str, Any] = {
            "native_climate_energy_record_count": len(records),
            "native_climate_energy_total_area_m2": area_float,
            "native_climate_energy_year_duration_seconds": year_float,
        }
        for field in sorted(CELL_FIELDS):
            # Summaries explicitly aggregate the exported annual mirrors. No
            # display rounding or fallback equal areas enter the physical mean.
            values = [_decimal(patches[record["cell_id"]][field], field) for record in records]
            summary[f"cell_count_mean_{field}"] = _finite_float(sum(values, Decimal(0)) / len(values), field)
            summary[f"area_weighted_mean_{field}"] = _finite_float(
                sum((area * value for area, value in zip(areas, values)), Decimal(0)) / total_area, field,
            )
        return patches, summary


def enrich_world_with_native_climate_energy(world: dict[str, Any]) -> dict[str, Any]:
    """Validate once, prepare every result, then publish additive mirrors."""
    from .native_climate_energy_validation import audit_native_climate_energy

    # This independent audit requires the full, supported native envelope and
    # authoritative linkage to every cell; a summary-only export cannot pass.
    audit_native_climate_energy(world, require_cell_linkage=True)
    cells = world["cells"]
    summary = world.get("summary", {})
    if type(summary) is not dict:
        raise ValueError("native climate annual aggregation requires a summary object when present")
    for location, aliases, values in (
        *((f"cell {cell['id']}", LEGACY_CELL_ALIASES, cell) for cell in cells),
        ("summary", LEGACY_SUMMARY_ALIASES, summary),
    ):
        stale = sorted(aliases.intersection(values))
        if stale:
            raise ValueError(f"native climate annual aggregation rejects stale legacy aliases in {location}: {', '.join(stale)}")
    key = "native_climate_energy_enrichment_model"
    if key in world:
        if world[key] != ENRICHMENT_MODEL:
            raise ValueError("native climate annual aggregation requires its exact known enrichment model")
    elif any(CELL_FIELDS.intersection(cell) for cell in cells) or SUMMARY_FIELDS.intersection(summary):
        raise ValueError("native climate annual aggregation found undeclared native annual aliases")

    patches, summary_patch = _annual_patches(world)
    replacement_model = deepcopy(ENRICHMENT_MODEL)
    # Everything that can fail has completed. Preserve cell dictionaries and
    # all authoritative native objects, including the native Celsius aliases.
    for cell in cells:
        cell.update(patches[cell["id"]])
    summary.update(summary_patch)
    world["summary"] = summary
    world[key] = replacement_model
    return world
