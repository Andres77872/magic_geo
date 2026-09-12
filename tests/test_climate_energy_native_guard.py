"""Legacy diagnostics must not overwrite a native seasonal climate budget."""

from copy import deepcopy

import pytest

from magic_geo.climate_energy import enrich_world_with_climate_energy_balance


def legacy_world():
    return {
        "planet_parameters": {"stellar_luminosity": 1.0, "orbital_eccentricity": 0.016},
        "climate_model": {"model_type": "equilibrium_latitude_circulation_climate_v5"},
        "cells": [{"id": 0, "lat_deg": 30.0, "area_km2": 1.0,
                   "temperature_c": 15.0, "temperature_monthly_c": [15.0] * 12}],
        "summary": {"cell_count": 1},
    }


def assert_protected(world):
    before = deepcopy(world)
    cell_list = world.get("cells")
    model = world.get("climate_energy_model")
    records = world.get("climate_energy_balance_records")
    with pytest.raises(ValueError, match="native seasonal climate requires its native budget and model-aware Python integration"):
        enrich_world_with_climate_energy_balance(world)
    assert world == before
    assert world.get("cells") is cell_list
    assert world.get("climate_energy_model") is model
    assert world.get("climate_energy_balance_records") is records


def test_full_native_envelope_is_rejected_without_mutating_any_retained_state():
    world = legacy_world()
    world.update(
        climate_model={
            "model_type": "prescribed_seasonal_surface_energy_v1",
            "temperature_model": "periodic_graybody_storage_conservative_transport_v1",
            "temperature_source": "climate_energy_balance_records_monthly_mean_temperature_k",
        },
        climate_energy_model={"model": "native_prescribed_seasonal_energy_v1",
                              "ownership": "native_temperature_producer", "native_temperature_forcing_coupled": True},
        climate_energy_forcing_intervals=[{"id": 0, "month_index": 0, "duration_seconds": 1.0}],
        climate_energy_transport_edges=[{"first_cell_id": 0, "second_cell_id": 1, "conductance_w_k": 1.0}],
        climate_energy_balance_records=[{"cell_id": 0, "monthly_mean_temperature_k": [288.15] * 12,
                                        "monthly_balance_residual_w_m2": [0.0] * 12}],
    )
    assert_protected(world)
    assert "surface_albedo_index" not in world["cells"][0]
    assert "mean_climate_energy_stress_index" not in world["summary"]


@pytest.mark.parametrize("marker", [
    {"climate_model": {"model_type": "prescribed_seasonal_surface_energy_v1"}},
    {"climate_model": {"temperature_model": "periodic_graybody_storage_conservative_transport_v1"}},
    {"climate_model": {"temperature_source": "climate_energy_balance_records_monthly_mean_temperature_k"}},
    {"climate_model": {"native_temperature_forcing_coupled": True}},
    {"climate_energy_model": {"model": "native_prescribed_seasonal_energy_v1"}},
    {"climate_energy_model": {"model": "native_prescribed_seasonal_energy_future_v2"}},
    {"climate_energy_model": {"ownership": "native_temperature_producer"}},
    {"climate_energy_model": {"native_temperature_forcing_coupled": True}},
    {"climate_model": "prescribed_seasonal_surface_energy_v1"},
    {"climate_energy_model": "native_prescribed_seasonal_energy_v1"},
    {"climate_energy_forcing_intervals": []},
    {"climate_energy_forcing_intervals": None},
    {"climate_energy_transport_edges": []},
    {"climate_energy_transport_edges": {}},
])
def test_each_partial_native_marker_blocks_legacy_fallback(marker):
    world = legacy_world()
    world.update(marker)
    assert_protected(world)


@pytest.mark.parametrize("cells", [[], None, {}, "omitted"])
@pytest.mark.parametrize("marker", [
    {"climate_energy_model": {"model": "native_prescribed_seasonal_energy_v1"}},
    {"climate_model": {"temperature_model": "periodic_graybody_storage_conservative_transport_v1"}},
    {"climate_energy_forcing_intervals": None},
    {"climate_energy_transport_edges": []},
])
def test_native_guard_runs_before_empty_missing_or_malformed_cell_return(cells, marker):
    world = {"retained_budget": {"do_not_replace": True}, **marker}
    if cells != "omitted":
        world["cells"] = cells
    assert_protected(world)


def test_native_guard_precedes_invalid_cell_or_planet_input_processing():
    class UnreadablePlanet:
        @property
        def stellar_luminosity(self):
            raise AssertionError("native guard must run before legacy planet reads")

    world = {"climate_energy_transport_edges": [], "cells": [None]}
    before = deepcopy(world)
    with pytest.raises(ValueError, match="native seasonal climate requires"):
        enrich_world_with_climate_energy_balance(world, UnreadablePlanet())
    assert world == before


@pytest.mark.parametrize("declaration", [
    None, {}, {"model": "unrelated_diagnostic_v1"},
    {"model": "legacy_empirical", "native_temperature_forcing_coupled": False},
])
def test_unrelated_or_legacy_declarations_keep_existing_enrichment_and_idempotence(declaration):
    world = legacy_world()
    world["climate_energy_model"] = declaration
    enrich_world_with_climate_energy_balance(world)
    assert world["climate_energy_model"]["albedo_greenhouse_model"] == "posthoc_empirical_graybody_surface_diagnostic_v2"
    assert world["climate_energy_model"]["native_temperature_forcing_coupled"] is False
    assert world["climate_energy_balance_records"]
    once = deepcopy(world)
    enrich_world_with_climate_energy_balance(world)
    assert world == once


def test_no_model_and_empty_legacy_world_behavior_is_unchanged():
    world = legacy_world()
    del world["climate_model"]
    enrich_world_with_climate_energy_balance(world)
    assert world["climate_energy_balance_records"]
    for empty in ({}, {"cells": []}, {"cells": None}):
        before = deepcopy(empty)
        assert enrich_world_with_climate_energy_balance(empty) is empty
        assert empty == before
