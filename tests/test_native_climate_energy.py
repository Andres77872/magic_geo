"""Native annual aggregation arithmetic and authoritative-object protection."""

from copy import deepcopy
from fractions import Fraction
import math

import pytest

from magic_geo.native_climate_energy import (
    CELL_FIELDS, ENRICHMENT_MODEL, LEGACY_CELL_ALIASES, LEGACY_SUMMARY_ALIASES,
    SUMMARY_FIELDS, _annual_patches, enrich_world_with_native_climate_energy,
)
from support.native_climate_energy import native_climate_world


AUTHORITATIVE = (
    "climate_model", "climate_energy_model", "climate_energy_balance_records",
    "climate_energy_forcing_intervals", "climate_energy_transport_edges",
)


def retained_objects(world):
    objects = {}

    def walk(value, path):
        if isinstance(value, (list, dict)):
            objects[path] = id(value)
            entries = value.items() if isinstance(value, dict) else enumerate(value)
            for key, child in entries:
                walk(child, (*path, key))

    for key in AUTHORITATIVE:
        walk(world[key], (key,))
    for index, c in enumerate(world["cells"]):
        walk(c["temperature_monthly_c"], ("cells", index, "temperature_monthly_c"))
    return objects


def aggregation_input():
    """Arithmetic-only input, deliberately not a complete climate certificate.

    Unequal months make a wrong count-mean observable. Live-certificate tests
    below separately exercise the mandatory independent pre-commit audit.
    """
    records = []
    for index, area in enumerate((2.0, 7.0)):
        records.append({
            "cell_id": index, "area_m2": area,
            "top_of_atmosphere_albedo": 0.2 + 0.1 * index,
            "effective_longwave_emissivity": 0.6 - 0.1 * index,
            "monthly_absorbed_shortwave_w_m2": [100.0 + month * 3 + 20 * index for month in range(12)],
            "monthly_emitted_longwave_w_m2": [80.0 + month + 7 * index for month in range(12)],
            "monthly_horizontal_heat_convergence_w_m2": [(-1.0 if index == 0 else 2 / 7) * month for month in range(12)],
            "monthly_heat_storage_tendency_w_m2": [1.0 + month / 10 for month in range(12)],
            "monthly_balance_residual_w_m2": [(-1.0) ** month * month * 1e-8 for month in range(12)],
            "monthly_balance_tolerance_w_m2": [1e-6 + month * 1e-8 for month in range(12)],
        })
    return {
        "climate_energy_model": {"monthly_duration_seconds": [float(i) for i in range(1, 13)]},
        "climate_energy_balance_records": records,
    }


def exact_weighted(values, weights):
    return float(sum((Fraction(value) * Fraction(weight) for value, weight in zip(values, weights)), Fraction()) / sum(map(Fraction, weights)))


def test_unequal_duration_and_area_means_replay_independently_without_count_weighting():
    world = aggregation_input()
    before = deepcopy(world)
    patches, summary = _annual_patches(world)
    assert world == before
    durations = world["climate_energy_model"]["monthly_duration_seconds"]
    records = world["climate_energy_balance_records"]
    for record in records:
        actual = patches[record["cell_id"]]
        assert set(actual) == CELL_FIELDS
        for field in ("absorbed_shortwave", "emitted_longwave", "horizontal_heat_convergence", "heat_storage_tendency"):
            source = record[f"monthly_{field}_w_m2"]
            assert actual[f"annual_{field}_w_m2"] == exact_weighted(source, durations)
            if field == "absorbed_shortwave":
                assert actual[f"annual_{field}_w_m2"] != sum(source) / len(source)
        absorbed = record["monthly_absorbed_shortwave_w_m2"]
        emitted = record["monthly_emitted_longwave_w_m2"]
        transport = record["monthly_horizontal_heat_convergence_w_m2"]
        assert actual["annual_net_radiative_flux_w_m2"] == exact_weighted([a - e for a, e in zip(absorbed, emitted)], durations)
        assert actual["annual_net_heating_w_m2"] == pytest.approx(exact_weighted([a - e + h for a, e, h in zip(absorbed, emitted, transport)], durations), rel=2e-16)
        assert actual["annual_energy_balance_residual_w_m2"] == exact_weighted(record["monthly_balance_residual_w_m2"], durations)
        assert actual["annual_mean_abs_energy_balance_residual_w_m2"] == exact_weighted([abs(v) for v in record["monthly_balance_residual_w_m2"]], durations)
        assert actual["annual_mean_energy_balance_numerical_allowance_w_m2"] == exact_weighted(record["monthly_balance_tolerance_w_m2"], durations)
    assert set(summary) == SUMMARY_FIELDS
    areas = [record["area_m2"] for record in records]
    for field in CELL_FIELDS:
        values = [patches[record["cell_id"]][field] for record in records]
        assert summary[f"area_weighted_mean_{field}"] == exact_weighted(values, areas)
        assert summary[f"cell_count_mean_{field}"] == exact_weighted(values, [1.0, 1.0])
    assert abs(summary["area_weighted_mean_annual_horizontal_heat_convergence_w_m2"]) < 1e-15
    assert summary["cell_count_mean_annual_horizontal_heat_convergence_w_m2"] != 0.0


def test_finite_weighted_means_survive_intermediate_duration_and_area_product_overflow():
    world = aggregation_input()
    world["climate_energy_model"]["monthly_duration_seconds"] = [1e200] * 12
    for record in world["climate_energy_balance_records"]:
        record["area_m2"] = 1e200 * (record["cell_id"] + 1)
        record["monthly_absorbed_shortwave_w_m2"] = [1e200] * 12
    patches, summary = _annual_patches(world)
    assert math.isinf(1e200 * 1e200)
    assert all(patch["annual_absorbed_shortwave_w_m2"] == 1e200 for patch in patches.values())
    assert summary["area_weighted_mean_annual_absorbed_shortwave_w_m2"] == 1e200
    assert summary["native_climate_energy_total_area_m2"] == 3e200


def test_small_signed_monthly_budget_survives_extreme_cancellation():
    world = aggregation_input()
    world["climate_energy_model"]["monthly_duration_seconds"] = [1.0] * 12
    world["climate_energy_balance_records"][0]["monthly_balance_residual_w_m2"] = [1e300, 1.0, -1e300] + [0.0] * 9
    patches, _ = _annual_patches(world)
    assert patches[0]["annual_energy_balance_residual_w_m2"] == 1 / 12


@pytest.mark.parametrize("mutation", ["area_sum", "duration_sum", "net_heating"])
def test_unrepresentable_export_fails_before_arithmetic_input_mutation(mutation):
    world = aggregation_input()
    if mutation == "area_sum":
        for record in world["climate_energy_balance_records"]:
            record["area_m2"] = 1e308
    elif mutation == "duration_sum":
        world["climate_energy_model"]["monthly_duration_seconds"] = [1e308] * 12
    else:
        record = world["climate_energy_balance_records"][0]
        record["monthly_absorbed_shortwave_w_m2"] = [1e308] * 12
        record["monthly_horizontal_heat_convergence_w_m2"] = [1e308] * 12
    before = deepcopy(world)
    with pytest.raises(ValueError, match="cannot represent"):
        _annual_patches(world)
    assert world == before


@pytest.mark.parametrize("key", ["area_m2", "duration"])
@pytest.mark.parametrize("invalid", [True, None, "2", 0.0, -1.0, float("inf"), 10 ** 400])
def test_invalid_arithmetic_weights_have_no_fallback(key, invalid):
    world = aggregation_input()
    if key == "duration":
        world["climate_energy_model"]["monthly_duration_seconds"][0] = invalid
    else:
        world["climate_energy_balance_records"][0][key] = invalid
    before = deepcopy(world)
    with pytest.raises(ValueError):
        _annual_patches(world)
    assert world == before


def test_real_native_budget_is_preserved_in_value_and_identity_on_success_and_repeat(monkeypatch):
    import magic_geo.native_climate_energy_validation as validation
    original_audit = validation.audit_native_climate_energy
    calls = []

    def audit_once(payload, *, require_cell_linkage):
        calls.append(require_cell_linkage)
        return original_audit(payload, require_cell_linkage=require_cell_linkage)

    monkeypatch.setattr(validation, "audit_native_climate_energy", audit_once)
    world = native_climate_world()
    world["summary"] = {"cell_count": 128, "unrelated_diagnostic": {"retained": True}}
    before = deepcopy(world)
    objects = retained_objects(world)
    cell_list, cell_objects = world["cells"], list(world["cells"])
    summary = world["summary"]
    assert enrich_world_with_native_climate_energy(world) is world
    assert calls == [True]
    for key in AUTHORITATIVE:
        assert world[key] == before[key]
    assert retained_objects(world) == objects
    assert world["cells"] is cell_list
    assert all(actual is original for actual, original in zip(world["cells"], cell_objects))
    assert world["summary"] is summary
    assert world["native_climate_energy_enrichment_model"] == ENRICHMENT_MODEL
    for original, c in zip(before["cells"], world["cells"]):
        assert {key: value for key, value in c.items() if key not in CELL_FIELDS} == original
        assert not LEGACY_CELL_ALIASES.intersection(c)
        assert all(type(c[field]) is float and math.isfinite(c[field]) for field in CELL_FIELDS)
    assert not LEGACY_SUMMARY_ALIASES.intersection(summary)
    assert {key: value for key, value in summary.items() if key not in SUMMARY_FIELDS} == before["summary"]
    once = deepcopy(world)
    enrich_world_with_native_climate_energy(world)
    assert calls == [True, True]
    assert world == once
    assert retained_objects(world) == objects


def test_declared_native_annual_aliases_are_recomputed_under_explicit_policy():
    world = native_climate_world()
    enrich_world_with_native_climate_energy(world)
    expected = deepcopy(world)
    world["cells"][0]["annual_absorbed_shortwave_w_m2"] = -12345.0
    world["summary"]["area_weighted_mean_annual_absorbed_shortwave_w_m2"] = -12345.0
    enrich_world_with_native_climate_energy(world)
    assert world == expected


def test_real_native_monthly_ledger_replays_annual_mirrors_and_physical_means():
    world = native_climate_world()
    enrich_world_with_native_climate_energy(world)
    durations = world["climate_energy_model"]["monthly_duration_seconds"]
    records = world["climate_energy_balance_records"]
    cells = {c["id"]: c for c in world["cells"]}
    for record in records:
        c = cells[record["cell_id"]]
        for name in ("absorbed_shortwave", "emitted_longwave", "horizontal_heat_convergence", "heat_storage_tendency"):
            assert c[f"annual_{name}_w_m2"] == exact_weighted(record[f"monthly_{name}_w_m2"], durations)
        assert c["annual_energy_balance_residual_w_m2"] == exact_weighted(record["monthly_balance_residual_w_m2"], durations)
        assert c["annual_mean_abs_energy_balance_residual_w_m2"] == exact_weighted([abs(value) for value in record["monthly_balance_residual_w_m2"]], durations)
        assert c["effective_toa_albedo"] == record["top_of_atmosphere_albedo"]
        assert c["effective_longwave_emissivity"] == record["effective_longwave_emissivity"]
    # Seasonal OLR requires mean T^4, not the fourth power of annual mean T.
    record = records[0]
    sigma_epsilon = 5.670374419e-8 * record["effective_longwave_emissivity"]
    actual_olr = cells[record["cell_id"]]["annual_emitted_longwave_w_m2"]
    assert actual_olr == pytest.approx(sigma_epsilon * exact_weighted(record["monthly_mean_fourth_power_temperature_k4"], durations), rel=3e-15)
    assert abs(actual_olr - sigma_epsilon * exact_weighted(record["monthly_mean_temperature_k"], durations) ** 4) > 1.0
    areas = [record["area_m2"] for record in records]
    summary = world["summary"]
    for field in CELL_FIELDS:
        values = [cells[record["cell_id"]][field] for record in records]
        assert summary[f"area_weighted_mean_{field}"] == exact_weighted(values, areas)
        assert summary[f"cell_count_mean_{field}"] == exact_weighted(values, [1.0] * len(records))
    assert summary["native_climate_energy_record_count"] == 128
    assert abs(summary["area_weighted_mean_annual_horizontal_heat_convergence_w_m2"]) < 1e-10


def test_later_omitted_feedback_diagnostics_cannot_change_native_coefficients_or_annual_fluxes():
    world = native_climate_world()
    enrich_world_with_native_climate_energy(world)
    objects = retained_objects(world)
    before = {c["id"]: {field: c[field] for field in CELL_FIELDS} for c in world["cells"]}
    for c in world["cells"]:
        c.update(biome="ice_cap", ice_thickness_m=2000.0,
                 precipitation_mm_y=9000.0, seasonal_aridity_index=1.0,
                 humidity_transport_index=0.0, ocean_current_temperature_c=90.0)
        if not c["is_water"]:
            c["is_lake"] = True
    enrich_world_with_native_climate_energy(world)
    assert retained_objects(world) == objects
    assert {c["id"]: {field: c[field] for field in CELL_FIELDS} for c in world["cells"]} == before


@pytest.mark.parametrize("mutation", ["unknown_model", "missing_forcing", "empty_cells", "temperature", "coefficient", "budget"])
def test_real_native_validation_errors_retain_all_objects_and_values(mutation):
    world = native_climate_world()
    if mutation == "unknown_model":
        world["climate_energy_model"]["model"] = "native_prescribed_seasonal_energy_v99"
    elif mutation == "missing_forcing":
        world["climate_energy_forcing_intervals"] = []
    elif mutation == "empty_cells":
        world["cells"] = []
    elif mutation == "temperature":
        world["cells"][0]["temperature_c"] += 10.0
    elif mutation == "coefficient":
        world["climate_energy_balance_records"][0]["top_of_atmosphere_albedo"] = 0.5
    else:
        world["climate_energy_balance_records"][0]["monthly_emitted_longwave_w_m2"][0] += 10.0
    before = deepcopy(world)
    objects = retained_objects(world)
    with pytest.raises(ValueError):
        enrich_world_with_native_climate_energy(world)
    assert world == before
    assert retained_objects(world) == objects


@pytest.mark.parametrize("location,key", [
    ("cell", "climate_energy_stress_index"), ("cell", "energy_balance_residual_c"),
    ("cell", "surface_albedo_index"), ("cell", "greenhouse_trapping_w_m2"),
    ("summary", "mean_climate_energy_stress_index"),
    ("summary", "area_weighted_mean_greenhouse_trapping_w_m2"),
])
def test_known_legacy_alias_is_rejected_not_silently_removed(location, key):
    world = native_climate_world()
    target = world["cells"][0] if location == "cell" else world.setdefault("summary", {})
    target[key] = 0.0
    before = deepcopy(world)
    objects = retained_objects(world)
    with pytest.raises(ValueError, match="rejects stale legacy aliases"):
        enrich_world_with_native_climate_energy(world)
    assert world == before
    assert retained_objects(world) == objects


@pytest.mark.parametrize("mutation", ["undeclared_cell", "undeclared_summary", "unknown_enrichment", "malformed_summary"])
def test_aggregation_policy_errors_are_atomic(mutation):
    world = native_climate_world()
    if mutation == "undeclared_cell":
        world["cells"][0]["annual_absorbed_shortwave_w_m2"] = 123.0
    elif mutation == "undeclared_summary":
        world["summary"] = {"native_climate_energy_record_count": 1}
    elif mutation == "unknown_enrichment":
        world["native_climate_energy_enrichment_model"] = {"model": "unknown"}
    else:
        world["summary"] = None
    before = deepcopy(world)
    objects = retained_objects(world)
    with pytest.raises(ValueError):
        enrich_world_with_native_climate_energy(world)
    assert world == before
    assert retained_objects(world) == objects


def test_aggregation_failure_after_successful_audit_still_publishes_nothing(monkeypatch):
    # Deliberately isolate the commit boundary: the authoritative validator
    # has its own overflow refusal tests, while this exercises a later failure.
    import magic_geo.native_climate_energy_validation as validation
    world = native_climate_world()
    for record in world["climate_energy_balance_records"]:
        record["area_m2"] = 1e308
    called = []

    def checked_once(payload, *, require_cell_linkage):
        assert payload is world and require_cell_linkage is True
        called.append(True)

    monkeypatch.setattr(validation, "audit_native_climate_energy", checked_once)
    before = deepcopy(world)
    objects = retained_objects(world)
    with pytest.raises(ValueError, match="cannot represent total physical area"):
        enrich_world_with_native_climate_energy(world)
    assert called == [True]
    assert world == before
    assert retained_objects(world) == objects


def test_public_energy_dispatch_uses_native_authority_without_reading_legacy_planet_argument():
    from magic_geo.climate_energy import enrich_world_with_climate_energy_balance

    class UnreadableLegacyPlanet:
        @property
        def stellar_luminosity(self):
            raise AssertionError("native energy must not rebuild forcing from a legacy argument")

    world = native_climate_world()
    objects = retained_objects(world)
    assert enrich_world_with_climate_energy_balance(world, UnreadableLegacyPlanet()) is world
    assert world["native_climate_energy_enrichment_model"] == ENRICHMENT_MODEL
    assert retained_objects(world) == objects
    assert not LEGACY_CELL_ALIASES.intersection(world["cells"][0])


@pytest.mark.parametrize("declaration", [ENRICHMENT_MODEL, None, {"model": "native_future_v99"}])
def test_enrichment_declaration_alone_cannot_enter_legacy_fallback(declaration):
    from magic_geo.climate_energy import enrich_world_with_climate_energy_balance

    world = {"native_climate_energy_enrichment_model": deepcopy(declaration),
             "cells": [{"id": 0, "temperature_c": 15.0, "temperature_monthly_c": [15.0] * 12}]}
    before = deepcopy(world)
    with pytest.raises(ValueError, match="native seasonal climate requires its native budget"):
        enrich_world_with_climate_energy_balance(world)
    assert world == before
