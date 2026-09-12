"""Independent settlement applicability replay after native energy validation."""
from fractions import Fraction
import math
from typing import Any
from ...native_climate_energy_enrichment_validation import _MODEL as ENERGY_ENRICHMENT_MODEL

SEASONAL_MODEL = "causal_native_score_local_max_separated_settlement_selection_v3"
LEGACY_MODEL = "causal_native_score_local_max_separated_settlement_selection_v2"
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

def exact_support_declaration(value):
    """The new applicability declaration has an exact typed field contract."""
    return isinstance(value, dict) and value.keys() == SETTLEMENT_CLIMATE_SUPPORT_MODEL.keys() and all(
        type(value[key]) is type(expected) and value[key] == expected
        for key, expected in SETTLEMENT_CLIMATE_SUPPORT_MODEL.items()
    )

def finite(value):
    if type(value) not in (int, float):
        raise ValueError("settlement input is not a finite number")
    try:
        value = float(value)
    except OverflowError as error:
        raise ValueError("settlement input is not a finite number") from error
    if not math.isfinite(value):
        raise ValueError("settlement input is not a finite number")
    return value

def replay_settlement_climate(world):
    if not isinstance(world, dict):
        raise ValueError("settlement replay requires a world mapping")
    own = world.get("settlement_selection_model")
    summary = world.get("summary", {})
    if not isinstance(summary, dict):
        raise ValueError("invalid settlement summary")
    if "settlement_selection_model" in world:
        if not isinstance(own, dict) or own.get("model_type") not in (LEGACY_MODEL, SEASONAL_MODEL):
            raise ValueError("unknown settlement selection identity")
        if summary.get("settlement_selection_model") != own["model_type"]:
            raise ValueError("inconsistent settlement selection identity")
    elif "settlement_selection_model" in summary:
        raise ValueError("orphan settlement selection identity")
    legacy_selection = isinstance(own, dict) and own.get("model_type") == LEGACY_MODEL
    climate = world.get("climate_model")
    energy = world.get("climate_energy_model")
    cells = world.get("cells", [])
    if legacy_selection:
        if not isinstance(cells, list) or any(not isinstance(cell, dict) for cell in cells):
            raise ValueError("invalid settlement cells")
        # Climate and selection have separate version axes. Genuine seasonal
        # selection-v2 archives lack all successor applicability publication.
        if (
            "annual_climate_applicability" in own
            or any(key in world for key in ("native_social_availability_model", "native_social_availability"))
            or any(key in summary for key in (
                "native_social_summary_availability", "recorded_historical_event_count",
                "recorded_ruin_count", "recorded_conflict_count", "recorded_dynasty_count",
                "available_population_region_count", "available_culture_continuity_count",
            ))
            or any(any(key in cell for key in (
                "settlement_climate_supported", "settlement_climate_temperature_c",
            )) for cell in cells)
            or any(
                isinstance(declaration, dict)
                and any(declaration.get(key) == SEASONAL_MODEL for key in (
                    "source_settlement_model", "source_settlement_selection_model",
                ))
                for key, declaration in world.items() if isinstance(key, str) and key.endswith("_model")
            )
        ):
            raise ValueError("mixed settlement versions")
    native = any(key in world for key in ("native_climate_energy_enrichment_model", "climate_energy_forcing_intervals", "climate_energy_transport_edges"))
    for declaration in (climate, energy):
        if isinstance(declaration, dict):
            # Recognize incompatible/future native declarations as native
            # attempts, so contradictory legacy labels cannot bypass checks.
            native |= (
                declaration.get("native_temperature_forcing_coupled") is True
                or declaration.get("ownership") == "native_temperature_producer"
                or declaration.get("temperature_source") == "climate_energy_balance_records_monthly_mean_temperature_k"
                or any(isinstance(declaration.get(key), str) and declaration[key].startswith((
                    "native_prescribed_seasonal_energy_", "prescribed_seasonal_surface_energy_",
                    "periodic_graybody_storage_conservative_transport_",
                )) for key in ("model", "model_type", "temperature_model"))
            )
    if not native:
        if isinstance(own, dict) and own.get("model_type") == SEASONAL_MODEL:
            raise ValueError("settlement-v3 requires native climate")
        if "climate_model" in world and (not isinstance(climate, dict) or climate.get("model_type") != "equilibrium_latitude_circulation_climate_v5"):
            raise ValueError("unknown climate")
        if "climate_energy_model" in world and (not isinstance(energy, dict) or energy.get("albedo_greenhouse_model") != "posthoc_empirical_graybody_surface_diagnostic_v2" or "model" in energy):
            raise ValueError("unknown legacy energy")
        if any(any(k in cell for k in ("settlement_climate_supported", "settlement_climate_temperature_c")) for cell in cells):
            raise ValueError("mixed settlement versions")
        return LEGACY_MODEL, None
    if not isinstance(climate, dict) or not isinstance(energy, dict):
        raise ValueError("missing native identity")
    for declaration, required in ((climate, {
        "model_type": "prescribed_seasonal_surface_energy_v1",
        "temperature_model": "periodic_graybody_storage_conservative_transport_v1",
        "temperature_source": "climate_energy_balance_records_monthly_mean_temperature_k",
        "native_temperature_forcing_coupled": True,
        "imposed_mean_temperature": False, "post_solve_temperature_adjustments": False,
    }), (energy, {"model": "native_prescribed_seasonal_energy_v1", "budget_schema_version": 1,
        "ownership": "native_temperature_producer", "native_temperature_forcing_coupled": True})):
        if any(type(declaration.get(key)) is not type(value) or declaration[key] != value for key, value in required.items()):
            raise ValueError("unsupported native identity")
    if world.get("native_climate_energy_enrichment_model") != ENERGY_ENRICHMENT_MODEL:
        raise ValueError("missing upstream enrichment")
    if not isinstance(world.get("climate_energy_transport_edges"), list):
        raise ValueError("missing retained edges")
    for key in ("cells", "climate_energy_balance_records", "climate_energy_forcing_intervals"):
        if not isinstance(world.get(key), list) or not world[key] or any(not isinstance(item, dict) for item in world[key]):
            raise ValueError("missing retained source records")
    durations = energy.get("monthly_duration_seconds")
    if not isinstance(durations, list) or len(durations) != 12:
        raise ValueError("invalid durations")
    durations = [finite(value) for value in durations]
    year = finite(energy.get("year_duration_seconds"))
    if year <= 0 or any(value <= 0 for value in durations):
        raise ValueError("invalid durations")
    source = {}
    for record in world["climate_energy_balance_records"]:
        i = record.get("cell_id")
        if type(i) is not int or i < 0 or i in source:
            raise ValueError("invalid source ids")
        temperatures = record.get("monthly_mean_temperature_k")
        if not isinstance(temperatures, list) or len(temperatures) != 12:
            raise ValueError("invalid monthly temperatures")
        integral = sum((Fraction(dt) * Fraction(finite(t)) for dt, t in zip(durations, temperatures)), Fraction())
        try:
            source[i] = finite(float(integral / Fraction(year) - Fraction(27315, 100)))
        except OverflowError as error:
            raise ValueError("annual source exceeds finite range") from error
    result = {}
    for cell in cells:
        i = cell.get("id")
        if type(i) is not int or i < 0 or i in result or i not in source:
            raise ValueError("invalid cell ids")
        if legacy_selection:
            result[i] = source[i]
            continue
        value = finite(cell.get("settlement_climate_temperature_c"))
        tolerance = 64 * 2.0**-52 * max(273.15, abs(source[i]), abs(value))
        if abs(value - source[i]) > tolerance:
            raise ValueError("annual source mismatch")
        supported = value > -14 and value < 48
        if type(cell.get("settlement_climate_supported")) is not bool or cell["settlement_climate_supported"] != supported:
            raise ValueError("support mismatch")
        if not supported and finite(cell.get("settlement_score")) != 0:
            raise ValueError("unavailable score is not zero")
        result[i] = value
    if result.keys() != source.keys():
        raise ValueError("incomplete coverage")
    if legacy_selection:
        # All retained native source checks above still apply. The historical
        # selection replay consumes its original temperature_c and equations.
        return LEGACY_MODEL, None
    return SEASONAL_MODEL, result
