"""Independent optional replay of Python's native annual energy mirrors.

Call after the native certificate audit. This validates only the additive
aggregation contract; it neither repeats the physical audit nor mutates state.
Exact rational accumulation keeps large products and cancellation independent
of the producer's decimal implementation. Comparisons allow four binary64 ulps
of the independently rounded result, never a producer's solver tolerance.
"""

from __future__ import annotations

from fractions import Fraction
import math
from typing import Any


_MODEL = {
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
_MONTHLY = {
    "annual_absorbed_shortwave_w_m2": "monthly_absorbed_shortwave_w_m2",
    "annual_emitted_longwave_w_m2": "monthly_emitted_longwave_w_m2",
    "annual_horizontal_heat_convergence_w_m2": "monthly_horizontal_heat_convergence_w_m2",
    "annual_heat_storage_tendency_w_m2": "monthly_heat_storage_tendency_w_m2",
    "annual_energy_balance_residual_w_m2": "monthly_balance_residual_w_m2",
    "annual_mean_energy_balance_numerical_allowance_w_m2": "monthly_balance_tolerance_w_m2",
}
_CELL_FIELDS = set(_MONTHLY) | {
    "effective_toa_albedo", "effective_longwave_emissivity",
    "annual_net_radiative_flux_w_m2", "annual_net_heating_w_m2",
    "annual_mean_abs_energy_balance_residual_w_m2",
}
_SUMMARY_FIELDS = {
    "native_climate_energy_record_count", "native_climate_energy_total_area_m2",
    "native_climate_energy_year_duration_seconds",
} | {f"{weight}_{field}" for weight in ("cell_count_mean", "area_weighted_mean") for field in _CELL_FIELDS}


def _require(condition: bool, path: str, message: str) -> None:
    if not condition:
        raise ValueError(f"{path}: {message}")


def _number(value: Any, path: str) -> float:
    _require(type(value) in (int, float), path, "expected finite numeric value")
    try:
        result = float(value)
    except OverflowError as error:
        raise ValueError(f"{path}: value is not representable as binary64") from error
    _require(math.isfinite(result), path, "expected finite numeric value")
    return result


def _fraction(value: Any, path: str) -> Fraction:
    return Fraction.from_float(_number(value, path))


def _check(actual: Any, exact: Fraction, path: str) -> None:
    observed = _fraction(actual, path)
    try:
        expected = float(exact)
    except OverflowError as error:
        raise ValueError(f"{path}: independent aggregate is not representable as binary64") from error
    _require(math.isfinite(expected), path, "independent aggregate must be finite")
    # No absolute floor: a small numerical residual must not accept a much
    # larger tamper merely because the source fluxes are hundreds of W/m².
    allowance = 4 * Fraction.from_float(math.ulp(expected))
    _require(abs(observed - Fraction.from_float(expected)) <= allowance,
             path, "does not match independent native annual aggregation (4 ulps)")


def _verify(world: dict[str, Any]) -> None:
    _require(type(world) is dict, "world", "expected object")
    cells = world.get("cells", [])
    summary = world.get("summary", {})
    key = "native_climate_energy_enrichment_model"
    if key not in world:
        if type(cells) is list:
            for index, cell in enumerate(cells):
                if type(cell) is dict and _CELL_FIELDS.intersection(cell):
                    raise ValueError(f"cells[{index}]: native annual mirrors require their enrichment declaration")
        _require(not (type(summary) is dict and _SUMMARY_FIELDS.intersection(summary)),
                 "summary", "native annual mirrors require their enrichment declaration")
        return  # A genuinely raw native budget has no optional mirrors.

    _require(type(world[key]) is dict and world[key] == _MODEL, key, "unsupported or malformed enrichment declaration")
    _require(type(cells) is list and bool(cells), "cells", "annual enrichment requires full cell coverage")
    _require(type(summary) is dict, "summary", "annual enrichment requires summary object")
    records = world["climate_energy_balance_records"]
    _require(type(records) is list and len(records) == len(cells), "climate_energy_balance_records", "annual enrichment requires complete record coverage")
    durations_raw = world["climate_energy_model"]["monthly_duration_seconds"]
    _require(type(durations_raw) is list and len(durations_raw) == 12, "monthly_duration_seconds", "expected twelve durations")
    durations = [_fraction(value, f"monthly_duration_seconds[{i}]") for i, value in enumerate(durations_raw)]
    _require(all(value > 0 for value in durations), "monthly_duration_seconds", "durations must be positive")
    year = sum(durations, Fraction())
    by_id = {}
    for index, cell in enumerate(cells):
        _require(type(cell) is dict and type(cell.get("id")) is int, f"cells[{index}]", "expected cell with integer id")
        _require(cell["id"] not in by_id, f"cells[{index}].id", "duplicate cell id")
        by_id[cell["id"]] = cell
    areas = []
    exported = {field: [] for field in _CELL_FIELDS}
    seen = set()
    for index, record in enumerate(records):
        path = f"climate_energy_balance_records[{index}]"
        _require(type(record) is dict and type(record.get("cell_id")) is int, path, "expected record with integer cell id")
        cell_id = record["cell_id"]
        _require(cell_id in by_id and cell_id not in seen, path + ".cell_id", "incomplete or duplicate annual coverage")
        seen.add(cell_id)
        cell = by_id[cell_id]
        cell_path = f"cell {cell_id}"
        area = _fraction(record["area_m2"], path + ".area_m2")
        _require(area > 0, path + ".area_m2", "area must be positive")
        areas.append(area)

        def mean(source: str, *, absolute: bool = False) -> Fraction:
            values = record[source]
            _require(type(values) is list and len(values) == 12, path + "." + source, "expected twelve values")
            amounts = [_fraction(value, path + "." + source) for value in values]
            if absolute:
                amounts = [abs(value) for value in amounts]
            return sum((duration * value for duration, value in zip(durations, amounts)), Fraction()) / year

        expected = {target: mean(source) for target, source in _MONTHLY.items()}
        expected["effective_toa_albedo"] = _fraction(record["top_of_atmosphere_albedo"], path + ".top_of_atmosphere_albedo")
        expected["effective_longwave_emissivity"] = _fraction(record["effective_longwave_emissivity"], path + ".effective_longwave_emissivity")
        expected["annual_net_radiative_flux_w_m2"] = expected["annual_absorbed_shortwave_w_m2"] - expected["annual_emitted_longwave_w_m2"]
        expected["annual_net_heating_w_m2"] = expected["annual_net_radiative_flux_w_m2"] + expected["annual_horizontal_heat_convergence_w_m2"]
        # The signed residual's source is the retained native residual. The
        # upstream audit separately verifies storage - (ASR - OLR + H), using
        # its source-scale arithmetic allowance; do not erase that evidence.
        expected["annual_mean_abs_energy_balance_residual_w_m2"] = mean("monthly_balance_residual_w_m2", absolute=True)
        for field in sorted(_CELL_FIELDS):
            _require(field in cell, cell_path + "." + field, "missing annual mirror")
            _check(cell[field], expected[field], cell_path + "." + field)
            exported[field].append(_fraction(cell[field], cell_path + "." + field))

    count = summary.get("native_climate_energy_record_count")
    _require(type(count) is int and count == len(records), "summary.native_climate_energy_record_count", "must match complete record count")
    total_area = sum(areas, Fraction())
    _check(summary.get("native_climate_energy_total_area_m2"), total_area, "summary.native_climate_energy_total_area_m2")
    _check(summary.get("native_climate_energy_year_duration_seconds"), year, "summary.native_climate_energy_year_duration_seconds")
    for field in sorted(_CELL_FIELDS):
        values = exported[field]
        count_mean = sum(values, Fraction()) / len(values)
        area_mean = sum((area * value for area, value in zip(areas, values)), Fraction()) / total_area
        for prefix, expected in (("cell_count_mean", count_mean), ("area_weighted_mean", area_mean)):
            name = f"{prefix}_{field}"
            _check(summary.get(name), expected, "summary." + name)


def validate_native_climate_energy_enrichment(world: dict[str, Any]) -> list[str]:
    """Return at most one bounded failure; raw native state is allowed."""
    try:
        _verify(world)
    except (ValueError, KeyError, TypeError, IndexError, ArithmeticError) as error:
        message = str(error).replace("\n", " ")
        return ["native climate annual enrichment: " + message[:400]]
    return []
