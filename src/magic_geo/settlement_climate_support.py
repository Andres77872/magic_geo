"""Versioned annual settlement suitability inputs, after upstream energy audit.

This cheap dependency check is not another physical-energy certificate audit.
The round-trip input is retained because display precision cannot resolve the
open endpoints of the native empirical response.
"""
from __future__ import annotations

from decimal import Decimal, localcontext
import math
from typing import Any

from .climate_model_dispatch import ecology_uses_native_seasonal_climate

SEASONAL_SETTLEMENT_SELECTION_MODEL = "causal_native_score_local_max_separated_settlement_selection_v3"
SETTLEMENT_CLIMATE_SUPPORT_MODEL = {
    "model": "native_annual_settlement_suitability_proxy_support_v1",
    "temperature_input": "settlement_climate_temperature_c_roundtrip_native_annual_temperature",
    "response_center_c": 17.0,
    "response_half_width_c": 31.0,
    "minimum_temperature_c_exclusive": -14.0,
    "maximum_temperature_c_exclusive": 48.0,
    "support_field": "settlement_climate_supported",
    "surface_eligibility": "separate_nonmarine_nonlake_rule",
    "unsupported_score": "unavailable_numeric_zero_after_all_landform_adjustments",
    "neighbor_rule": "unsupported_cells_do_not_suppress_supported_local_maxima",
    "scope": "existing_annual_suitability_proxy_not_human_survival_or_universal_biology",
}


def _number(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("settlement annual temperature requires finite numeric input")
    try:
        result = float(value)
    except (ValueError, OverflowError) as error:
        raise ValueError("settlement annual temperature requires finite numeric input") from error
    if not math.isfinite(result):
        raise ValueError("settlement annual temperature requires finite numeric input")
    return result


def seasonal_settlement_inputs(world: dict[str, Any]) -> dict[int, float] | None:
    """Preflight every dependency before any settlement metadata mutation."""
    if not isinstance(world, dict):
        raise ValueError("settlement support requires a world mapping")
    seasonal = ecology_uses_native_seasonal_climate(world)
    cells = world.get("cells", [])
    if not seasonal:
        if any(isinstance(cell, dict) and any(key in cell for key in (
            "settlement_climate_supported", "settlement_climate_temperature_c",
        )) for cell in cells):
            raise ValueError("legacy settlement inputs contain seasonal applicability fields")
        return None
    model = world["climate_energy_model"]
    durations = model.get("monthly_duration_seconds")
    if not isinstance(durations, list) or len(durations) != 12:
        raise ValueError("settlement support requires twelve retained monthly durations")
    durations = [_number(value) for value in durations]
    year = _number(model.get("year_duration_seconds"))
    if year <= 0 or any(duration <= 0 for duration in durations):
        raise ValueError("settlement support requires positive retained durations")
    records = world["climate_energy_balance_records"]
    by_id = {}
    for record in records:
        cell_id = record.get("cell_id")
        if type(cell_id) is not int or cell_id < 0 or cell_id in by_id:
            raise ValueError("settlement support requires unique native record ids")
        by_id[cell_id] = record
    result = {}
    with localcontext() as context:
        context.prec = 60
        for cell in cells:
            cell_id = cell.get("id")
            if type(cell_id) is not int or cell_id < 0 or cell_id in result or cell_id not in by_id:
                raise ValueError("settlement support requires exact native cell coverage")
            value = _number(cell.get("settlement_climate_temperature_c"))
            monthly = by_id[cell_id].get("monthly_mean_temperature_k")
            if not isinstance(monthly, list) or len(monthly) != 12:
                raise ValueError("settlement support requires twelve retained monthly temperatures")
            monthly = [_number(item) for item in monthly]
            annual = sum((Decimal.from_float(dt) * Decimal.from_float(temp)
                for dt, temp in zip(durations, monthly)), Decimal(0)) / Decimal.from_float(year)
            expected = _number(float(annual - Decimal("273.15")))
            # Independent of display precision and published solver tolerances.
            # Covers represented source arithmetic / long-double accumulation,
            # not uncertainty in the physical or temporal model.
            allowance = 64 * math.ulp(1.0) * max(273.15, abs(expected), abs(value))
            if abs(value - expected) > allowance:
                raise ValueError("settlement annual input disagrees with retained native temperature")
            support = -14.0 < value < 48.0
            if type(cell.get("settlement_climate_supported")) is not bool or cell["settlement_climate_supported"] != support:
                raise ValueError("settlement annual applicability flag disagrees with exact input")
            if not support and _number(cell.get("settlement_score")) != 0.0:
                raise ValueError("unsupported seasonal settlement score must be unavailable zero")
            result[cell_id] = value
    if set(result) != set(by_id):
        raise ValueError("settlement support requires exact native cell coverage")
    return result
