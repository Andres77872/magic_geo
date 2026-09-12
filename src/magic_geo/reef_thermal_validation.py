"""Independent validation of the versioned empirical reef thermal contract.

This module does not import reef producer helpers or constants. It checks the
declared habitat prerequisite, not the remaining empirical growth bonuses or a
universal coral-survival law. Payloads predating model metadata retain their
legacy structural validation; a present but invalid declaration is never legacy.
"""

from __future__ import annotations

import math
from typing import Any

from .climate_model_dispatch import ecology_uses_native_seasonal_climate


_EXPECTED_MODEL = {
    "model": "heuristic_coastal_reef_v2",
    "thermal_eligibility": "annual_and_all_monthly_means_inside_existing_suitability_support",
    "minimum_temperature_c": 4.0,
    "maximum_temperature_c": 39.0,
    "temperature_bounds": "exclusive",
    "monthly_temperature_count": 12,
    "missing_monthly_temperature_policy": "annual_only_if_field_absent",
    "invalid_monthly_temperature_policy": "ineligible",
    "bleaching_model": "legacy_energy_aridity_current_proxy_v1",
    "thermal_limits_scope": "empirical_model_support_not_universal_coral_survival_limits",
}
_NATIVE_MODEL = {
    **_EXPECTED_MODEL,
    "model": "heuristic_coastal_reef_native_seasonal_v3",
    "bleaching_model": "not_modelled_no_reference_climatology",
    "bleaching_estimate_available": False,
    "bleaching_output_policy": "omit_cell_record_and_summary_legacy_risk_fields",
    "growth_model": "thermal_habitat_gated_existing_bonuses_without_bleaching_penalty",
    "remaining_growth_weights": "unchanged_without_renormalization",
    "climate_input_policy": "requires_known_native_identity_and_upstream_energy_enrichment",
}


def _native_growth_errors(cells: list[dict[str, Any]]) -> list[str]:
    """Replay v3's declared growth using independently published descriptors."""
    errors = []
    by_id = {cell["id"]: cell for cell in cells if type(cell.get("id")) is int}

    def finite(value: Any) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError
        value = float(value)
        if not math.isfinite(value):
            raise ValueError
        return value

    def bounded(value: Any) -> float:
        value = finite(value)
        return max(0.0, min(1.0, value))

    for cell in cells:
        try:
            neighbors = cell.get("neighbors", [])
            has_land = isinstance(neighbors, list) and any(
                type(neighbor) is int and neighbor in by_id and not bool(by_id[neighbor].get("is_water", False))
                for neighbor in neighbors
            )
            water_type = cell.get("water_body_type", "land")
            marine = isinstance(water_type, str) and water_type in {"ocean", "continental_shelf", "inland_sea"}
            annual = cell.get("temperature_c")
            monthly = cell.get("temperature_monthly_c", [annual] * 12)
            eligible = _inside_thermal_support(annual) and isinstance(monthly, list) and len(monthly) == 12 and all(_inside_thermal_support(value) for value in monthly)
            expected = 0.0
            if bool(cell.get("is_water", False)) and marine and has_land and eligible:
                temperature = (annual - 4.0) / 14.0 * 0.55 if annual < 18.0 else 1.0 - abs(annual - 26.0) / 13.0
                depth = max(0.0, finite(cell.get("water_depth_m", 0.0)))
                if water_type == "continental_shelf": shallow, shelf = bounded(1.0 - max(0.0, depth - 5.0) / 210.0), 0.24
                elif water_type == "inland_sea": shallow, shelf = bounded(0.82 - max(0.0, depth - 5.0) / 260.0), 0.14
                else: shallow, shelf = bounded(0.42 - max(0.0, depth - 25.0) / 360.0), 0.04
                wave = bounded(cell["reef_wave_exposure_index"])
                expected = bounded(
                    bounded(temperature) * 0.26 + shallow * 0.25 + shelf
                    + bounded(cell["reef_island_support_index"]) * 0.15
                    + bounded(1.0 - abs(wave - 0.42) / 0.58) * 0.10
                    + bounded(cell.get("fishery_productivity_index", 0.0)) * 0.08
                    - bounded(cell["reef_sediment_stress_index"]) * 0.22
                    - bounded(finite(cell.get("ice_thickness_m", 0.0)) / 60.0) * 0.54
                )
            actual = cell.get("reef_growth_index")
            if isinstance(actual, bool) or not isinstance(actual, (int, float)) or not 0.0 <= actual <= 1.0 or abs(actual - expected) > 1e-6:
                errors.append(f"reef native cell {cell.get('id')}: growth must omit bleaching without renormalizing weights")
        except (KeyError, TypeError, ValueError, OverflowError):
            errors.append(f"reef native cell {cell.get('id')}: invalid growth replay inputs")
    # Published six-decimal wave/island/sediment rounding propagates at most
    # 0.272e-6 into growth; its own rounding adds 0.5e-6. A 1e-6 bound covers both.
    return errors


def _inside_thermal_support(value: Any) -> bool:
    # The bounded comparison also excludes NaN/infinities and avoids converting
    # enormous Python integers to float before rejecting them.
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and 4.0 < value < 39.0
    )


def validate_reef_thermal_habitat(world: dict[str, Any]) -> list[str]:
    """Return metadata/thermal violations for v2, or [] for absent-model legacy."""
    from .reef_port_links_validation import validate_reef_port_links
    link_errors = validate_reef_port_links(world)
    if link_errors:
        return link_errors
    if "reef_diagnostics_model" not in world:
        return []
    try:
        native = ecology_uses_native_seasonal_climate(world)
    except ValueError as error:
        return [f"reef thermal climate dependency: {error}"]
    expected_model = _NATIVE_MODEL if native else _EXPECTED_MODEL
    model = world["reef_diagnostics_model"]
    if not isinstance(model, dict) or model.keys() != expected_model.keys():
        return ["reef thermal model metadata is missing fields, malformed, or unsupported"]
    errors: list[str] = []
    for key, expected in expected_model.items():
        observed = model[key]
        if (
            observed != expected
            or (isinstance(expected, bool) and type(observed) is not bool)
            or (type(expected) is int and type(observed) is not int)
            or (isinstance(expected, float) and (
                not isinstance(observed, (int, float)) or isinstance(observed, bool)
            ))
        ):
            errors.append(f"reef thermal model metadata has invalid {key}")
    if errors:
        return errors

    cells = world.get("cells")
    if not isinstance(cells, list) or any(not isinstance(cell, dict) for cell in cells):
        return ["reef thermal habitat requires a valid cell list"]
    if native:
        for cell in cells:
            if "reef_bleaching_risk_index" in cell:
                errors.append(f"reef native cell {cell.get('id')}: unavailable bleaching risk must be omitted")
        records = world.get("reef_systems")
        if not isinstance(records, list) or any(not isinstance(record, dict) for record in records):
            errors.append("reef native requires a valid reef system list")
        else:
            for record in records:
                if "mean_reef_bleaching_risk_index" in record:
                    errors.append(f"reef native record {record.get('id')}: unavailable bleaching risk must be omitted")
        summary = world.get("summary")
        if not isinstance(summary, dict):
            errors.append("reef native requires a valid summary")
        elif "mean_reef_bleaching_risk_index" in summary:
            errors.append("reef native summary: unavailable bleaching risk must be omitted")
        errors.extend(_native_growth_errors(cells))
    for cell in cells:
        growth = cell.get("reef_growth_index", 0.0)
        if not isinstance(growth, (int, float)) or isinstance(growth, bool) or not 0.0 <= growth <= 1.0:
            errors.append(f"reef thermal habitat cell {cell.get('id')}: invalid reef_growth_index")
            continue
        if (
            growth == 0.0
            and cell.get("reef_system_id", -1) == -1
            and cell.get("reef_type", "none") == "none"
        ):
            continue
        eligible = _inside_thermal_support(cell.get("temperature_c"))
        if "temperature_monthly_c" in cell:
            monthly = cell["temperature_monthly_c"]
            eligible = eligible and (
                isinstance(monthly, list)
                and len(monthly) == 12
                and all(_inside_thermal_support(value) for value in monthly)
            )
        if not eligible:
            errors.append(
                f"reef thermal habitat cell {cell.get('id')}: positive growth or membership "
                "requires annual and all supplied monthly means in (4, 39) C"
            )
    return errors
