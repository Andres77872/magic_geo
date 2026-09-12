"""Versioned ecology support consumes climate, not numerical-solver defects."""
from copy import deepcopy
from unittest.mock import patch

import pytest

from magic_geo.climate_energy import enrich_world_with_climate_energy_balance
from magic_geo.climate_model_dispatch import ecology_uses_native_seasonal_climate
from magic_geo.native_climate_energy import ENRICHMENT_MODEL, enrich_world_with_native_climate_energy
from magic_geo.reef_diagnostics import enrich_world_with_reef_diagnostics
from magic_geo.reef_thermal_validation import validate_reef_thermal_habitat
from magic_geo.wildfire_disturbance import enrich_world_with_wildfire_disturbance
from magic_geo.wildfire_aquatic_validation import validate_wildfire_aquatic_exclusion
from support.native_climate_energy import native_climate_world
from support.fire_worlds import prepare_fire_parents
from test_reef_thermal_habitat import coastal_world
from test_standing_lake_wildfire import cell


PRODUCERS = (enrich_world_with_reef_diagnostics, enrich_world_with_wildfire_disturbance)


def native_contract(world):
    """Dependency-only fixture, not a fabricated numerical certificate.

    The separate real-world test exercises the physical audit upstream. These
    small fixtures isolate exact ecology formulas and dispatch contracts.
    """
    world.update(
        climate_model={
            "model_type": "prescribed_seasonal_surface_energy_v1",
            "temperature_model": "periodic_graybody_storage_conservative_transport_v1",
            "temperature_source": "climate_energy_balance_records_monthly_mean_temperature_k",
            "native_temperature_forcing_coupled": True,
            "imposed_mean_temperature": False, "post_solve_temperature_adjustments": False,
        },
        climate_energy_model={
            "model": "native_prescribed_seasonal_energy_v1", "budget_schema_version": 1,
            "ownership": "native_temperature_producer", "native_temperature_forcing_coupled": True,
        },
        native_climate_energy_enrichment_model=deepcopy(ENRICHMENT_MODEL),
        climate_energy_balance_records=[{"cell_id": c["id"]} for c in world["cells"]],
        climate_energy_forcing_intervals=[{"dependency_fixture": True}],
        climate_energy_transport_edges=[],
    )
    return world


def ecology_snapshot(world):
    return {
        "cells": [{k: v for k, v in c.items() if k.startswith(("reef_", "wildfire_"))} for c in world["cells"]],
        "summary": {k: v for k, v in world["summary"].items() if "reef" in k or "wildfire" in k},
        "reef_systems": world.get("reef_systems"), "wildfire_spread_histories": world.get("wildfire_spread_histories"),
        "reef_model": world.get("reef_diagnostics_model"), "fire_model": world.get("wildfire_disturbance_model"),
    }


def test_native_reef_retires_entire_bleaching_penalty_without_renormalizing():
    source = coastal_world(30.0, fishery_productivity_index=0.0, seasonal_aridity_index=0.8,
                           ocean_current_temperature_c=4.0, climate_energy_stress_index=0.9)
    legacy = enrich_world_with_reef_diagnostics(deepcopy(source))
    native = enrich_world_with_reef_diagnostics(native_contract(deepcopy(source)))
    c = native["cells"][0]
    # All non-bleaching terms are independently reconstructed from the
    # existing coastal descriptors; no weights are divided by a smaller sum.
    expected = min(1.0, max(0.0,
        (1.0 - abs(30.0 - 26.0) / 13.0) * 0.26 + 0.25 + 0.24
        + c["reef_island_support_index"] * 0.15
        + (1.0 - abs(c["reef_wave_exposure_index"] - 0.42) / 0.58) * 0.10
        - c["reef_sediment_stress_index"] * 0.22,
    ))
    assert c["reef_growth_index"] == pytest.approx(expected, abs=5e-7)
    assert c["reef_growth_index"] - legacy["cells"][0]["reef_growth_index"] == pytest.approx(
        0.16 * legacy["cells"][0]["reef_bleaching_risk_index"], abs=1e-6,
    )
    assert native["reef_systems"]
    assert native["reef_diagnostics_model"]["bleaching_estimate_available"] is False
    assert native["reef_diagnostics_model"]["bleaching_model"] == "not_modelled_no_reference_climatology"
    assert all("reef_bleaching_risk_index" not in item for item in native["cells"])
    assert all("mean_reef_bleaching_risk_index" not in record for record in native["reef_systems"])
    assert "mean_reef_bleaching_risk_index" not in native["summary"]
    assert validate_reef_thermal_habitat(native) == []


def test_reenrichment_removes_all_stale_bleaching_aliases_and_is_idempotent():
    world = enrich_world_with_reef_diagnostics(coastal_world(30.0))
    assert world["reef_systems"] and "mean_reef_bleaching_risk_index" in world["summary"]
    native_contract(world)
    enrich_world_with_reef_diagnostics(world)
    once = deepcopy(world)
    enrich_world_with_reef_diagnostics(world)
    assert world == once
    assert validate_reef_thermal_habitat(world) == []
    assert all("reef_bleaching_risk_index" not in c for c in world["cells"])
    assert "mean_reef_bleaching_risk_index" not in world["reef_systems"][0]
    assert "mean_reef_bleaching_risk_index" not in world["summary"]


@pytest.mark.parametrize("temperature,months,eligible", [
    (26.0, [26.0] * 12, True), (8.0, [8.0] * 12, True),
    (4.0, [4.0] * 12, False), (39.0, [39.0] * 12, False),
    (26.0, [26.0] * 11 + [100.0], False), (26.0, [], False),
])
def test_native_reef_keeps_existing_thermal_habitat_gate(temperature, months, eligible):
    world = enrich_world_with_reef_diagnostics(native_contract(coastal_world(temperature, temperature_monthly_c=months)))
    assert bool(world["reef_systems"]) is eligible
    assert (world["cells"][0]["reef_growth_index"] > 0.0) is eligible
    assert world["cells"][0]["reef_island_support_index"] > 0.8
    assert validate_reef_thermal_habitat(world) == []


@pytest.mark.parametrize("current_parent", [False, True], ids=["historical_v2_v3", "historical_parent_v4_fire_v5"])
def test_native_wildfire_omits_exact_legacy_stress_weight_and_preserves_other_weights(current_parent):
    source = {"cells": [cell(vegetation_biomass_index=0.4, primary_productivity_index=0.3,
                              wildfire_spread_risk_index=0.2, seasonal_aridity_index=0.3,
                              ecosystem_disturbance_pressure_index=0.4, settlement_score=0.2,
                              climate_energy_stress_index=1.0)]}
    if current_parent:
        prepare_fire_parents(source)
    legacy = enrich_world_with_wildfire_disturbance(deepcopy(source))
    native = enrich_world_with_wildfire_disturbance(native_contract(deepcopy(source)))
    c = native["cells"][0]
    expected = (c["wildfire_spread_risk_index"] * 0.34 + c["wildfire_fuel_continuity_index"] * 0.28 + 0.3 * 0.16
                + c["ecosystem_disturbance_pressure_index"] * 0.10 + c["wildfire_wind_alignment_index"] * 0.08 + 0.2 * 0.08
                - c["wildfire_firebreak_index"] * 0.18)
    assert c["wildfire_ignition_potential_index"] == pytest.approx(expected, abs=1e-6)
    assert legacy["cells"][0]["wildfire_ignition_potential_index"] - c["wildfire_ignition_potential_index"] == pytest.approx(0.06, abs=1e-6)
    assert native["wildfire_disturbance_model"]["lightning_model"] == "not_modelled"
    assert legacy["wildfire_disturbance_model"]["model"] == (
        "heuristic_wildfire_parent_availability_v4" if current_parent else "heuristic_wildfire_aquatic_exclusion_v2"
    )
    assert native["wildfire_disturbance_model"]["model"] == (
        "heuristic_wildfire_native_seasonal_parent_availability_v5" if current_parent else "heuristic_wildfire_native_seasonal_v3"
    )
    assert validate_wildfire_aquatic_exclusion(native) == []


@pytest.mark.parametrize("stale", [None, "unavailable", {}, [], 0.0, 1.0])
@pytest.mark.parametrize("current_parent", [False, True], ids=["historical_v3", "historical_parent_fire_v5"])
def test_native_ecology_does_not_read_stale_energy_stress_or_solver_residuals(stale, current_parent):
    world = native_contract(coastal_world(26.0, fishery_productivity_index=0.0))
    world["cells"][1].update(cell(1, neighbors=[0], climate_energy_stress_index=0.0))
    if current_parent:
        prepare_fire_parents(world)
    for producer in PRODUCERS:
        producer(world)
    before = deepcopy(ecology_snapshot(world))
    for c in world["cells"]:
        c["climate_energy_stress_index"] = stale
        c["annual_energy_balance_residual_w_m2"] = 1e12
        c["annual_mean_energy_balance_numerical_allowance_w_m2"] = 1e24
    world["climate_energy_model"]["achieved"] = {"total_step_attempts": 999999, "maximum_step_balance_residual_w_m2": 1e10}
    for record in world["climate_energy_balance_records"]:
        record["monthly_balance_residual_w_m2"] = [1e30] * 12
    for producer in PRODUCERS:
        producer(world)
    assert ecology_snapshot(world) == before
    assert validate_reef_thermal_habitat(world) == []
    assert validate_wildfire_aquatic_exclusion(world) == []


@pytest.mark.parametrize("current_parent", [False, True], ids=["historical_v3", "historical_parent_fire_v5"])
def test_native_fire_still_cannot_cross_standing_water_and_rebuilds_histories(current_parent):
    source = cell(0, neighbors=[1])
    water = cell(1, neighbors=[0, 2], is_lake=True, water_body_type="fresh_lake")
    far = cell(2, neighbors=[1], wildfire_spread_risk_index=0.0, seasonal_aridity_index=0.0,
               ecosystem_disturbance_pressure_index=0.0, settlement_score=0.0,
               fire_frequency_index=0.0)
    world = native_contract({"cells": [source, water, far]})
    if current_parent:
        far["wind_east"] = 0.0
        prepare_fire_parents(world)
    enrich_world_with_wildfire_disturbance(world)
    assert world["wildfire_disturbance_model"]["model"] == (
        "heuristic_wildfire_native_seasonal_parent_availability_v5" if current_parent else "heuristic_wildfire_native_seasonal_v3"
    )
    assert water["wildfire_fuel_continuity_index"] == 0.0
    assert water["wildfire_ignition_potential_index"] == 0.0
    assert water["wildfire_spread_history_ids"] == []
    assert far["wildfire_spread_history_ids"] == []
    assert world["wildfire_spread_histories"][0]["cell_ids"] == [0]
    once = deepcopy(world)
    enrich_world_with_wildfire_disturbance(world)
    assert world == once
    assert validate_wildfire_aquatic_exclusion(world) == []


@pytest.mark.parametrize("producer", PRODUCERS)
@pytest.mark.parametrize("marker", [
    {"climate_model": {"model_type": "prescribed_seasonal_surface_energy_v1"}},
    {"climate_energy_model": {"model": "native_prescribed_seasonal_energy_future_v2"}},
    {"climate_energy_model": {"ownership": "native_temperature_producer"}},
    {"climate_energy_forcing_intervals": []}, {"climate_energy_transport_edges": []},
    {"native_climate_energy_enrichment_model": {}}, {"climate_model": "future"},
    {"climate_model": {}}, {"climate_energy_model": {"model": "unknown"}},
])
def test_partial_or_unknown_climate_models_fail_before_any_ecology_mutation(producer, marker):
    for cells in ([], [cell()]):
        world = {"cells": cells, "summary": {"retained": 17}, **deepcopy(marker)}
        before = deepcopy(world)
        with pytest.raises(ValueError):
            producer(world)
        assert world == before


@pytest.mark.parametrize("producer", PRODUCERS)
@pytest.mark.parametrize("key", ["climate_model", "climate_energy_model", "native_climate_energy_enrichment_model",
                                  "climate_energy_balance_records", "climate_energy_forcing_intervals", "climate_energy_transport_edges"])
def test_native_dependency_sections_cannot_be_dropped_or_malformed(producer, key):
    for malformed in (None, {}, "unknown"):
        world = native_contract({"cells": [cell()]})
        world[key] = malformed
        before = deepcopy(world)
        with pytest.raises(ValueError):
            producer(world)
        assert world == before
    world = native_contract({"cells": [cell()]})
    del world[key]
    before = deepcopy(world)
    with pytest.raises(ValueError):
        producer(world)
    assert world == before


@pytest.mark.parametrize("producer,key", [(PRODUCERS[0], "reef_diagnostics_model"), (PRODUCERS[1], "wildfire_disturbance_model")])
def test_unknown_ecology_model_cannot_be_overwritten(producer, key):
    world = native_contract({"cells": [cell()]})
    world[key] = {"model": "unsupported"}
    before = deepcopy(world)
    with pytest.raises(ValueError, match="exact known model metadata"):
        producer(world)
    assert world == before


@pytest.mark.parametrize("field,value", [("bleaching_estimate_available", 0), ("monthly_temperature_count", 12.0)])
def test_native_reef_model_does_not_accept_bool_or_integer_lookalikes(field, value):
    world = enrich_world_with_reef_diagnostics(native_contract(coastal_world()))
    world["reef_diagnostics_model"][field] = value
    before = deepcopy(world)
    assert validate_reef_thermal_habitat(world)
    with pytest.raises(ValueError, match="exact known model metadata"):
        enrich_world_with_reef_diagnostics(world)
    assert world == before


@pytest.mark.parametrize("where", ["cell", "record", "summary"])
def test_independent_native_reef_validator_rejects_even_zero_bleaching_estimate(where):
    world = enrich_world_with_reef_diagnostics(native_contract(coastal_world()))
    if where == "cell": world["cells"][0]["reef_bleaching_risk_index"] = 0.0
    elif where == "record": world["reef_systems"][0]["mean_reef_bleaching_risk_index"] = 0.0
    else: world["summary"]["mean_reef_bleaching_risk_index"] = 0.0
    assert any("unavailable bleaching risk must be omitted" in error for error in validate_reef_thermal_habitat(world))


def test_independent_validators_reject_reintroduced_legacy_weights():
    reef = enrich_world_with_reef_diagnostics(native_contract(coastal_world(26.0, fishery_productivity_index=0.0)))
    reef["cells"][0]["reef_growth_index"] -= 0.0384
    assert any("growth must omit bleaching" in error for error in validate_reef_thermal_habitat(reef))
    fire = enrich_world_with_wildfire_disturbance(native_contract({"cells": [cell(wildfire_spread_risk_index=0.2, seasonal_aridity_index=0.3)]}))
    fire["cells"][0]["wildfire_ignition_potential_index"] += 0.06
    assert any("ignition must omit energy stress" in error for error in validate_wildfire_aquatic_exclusion(fire))


def test_real_native_budget_is_verified_upstream_once_and_preserved_by_ecology():
    world = enrich_world_with_native_climate_energy(native_climate_world())
    keys = ("climate_model", "climate_energy_model", "climate_energy_balance_records",
            "climate_energy_forcing_intervals", "climate_energy_transport_edges", "native_climate_energy_enrichment_model")
    before = {key: deepcopy(world[key]) for key in keys}
    pointers = {key: world[key] for key in keys}
    with patch("magic_geo.native_climate_energy_validation.audit_native_climate_energy", side_effect=AssertionError("physical audit must not repeat per ecology enricher")):
        for producer in PRODUCERS:
            producer(world)
    assert all(world[key] is pointers[key] and world[key] == before[key] for key in keys)
    assert validate_reef_thermal_habitat(world) == []
    assert validate_wildfire_aquatic_exclusion(world) == []


def test_explicit_real_legacy_diagnostic_identity_remains_supported():
    world = coastal_world()
    world["cells"][1]["temperature_c"] = 26.0
    world["climate_model"] = {"model_type": "equilibrium_latitude_circulation_climate_v5"}
    enrich_world_with_climate_energy_balance(world)
    assert not ecology_uses_native_seasonal_climate(world)
    for producer in PRODUCERS:
        producer(world)
    assert world["reef_diagnostics_model"]["model"] == "heuristic_coastal_reef_v2"
    assert world["wildfire_disturbance_model"]["model"] == "heuristic_wildfire_aquatic_exclusion_v2"
    assert "reef_bleaching_risk_index" in world["cells"][0]
