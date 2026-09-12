"""Reef habitat cannot be created by nonthermal bonuses outside its model support."""

from copy import deepcopy
import math

import pytest

from magic_geo.reef_diagnostics import enrich_world_with_reef_diagnostics


def coastal_world(temperature=26.0, **sea_overrides):
    """An intentionally favorable coast exposes an invalid additive baseline."""
    sea = {
        "id": 0, "neighbors": [1], "area_km2": 100.0,
        "lat_deg": 0.0, "lon_deg": 0.0, "is_water": True,
        "water_body_type": "continental_shelf", "water_depth_m": 5.0,
        "temperature_c": temperature, "temperature_monthly_c": [temperature] * 12,
        "fishery_productivity_index": 1.0,
        **sea_overrides,
    }
    land = {
        "id": 1, "neighbors": [0], "area_km2": 100.0,
        "lat_deg": 0.0, "lon_deg": 1.0, "is_water": False,
        "water_body_type": "land", "island_class": "island",
        "volcanic_potential_index": 1.0, "crust_age_ma": 0.0,
    }
    return {
        "cells": [sea, land],
        "coastal_features": [{"id": 0, "cell_id": 1, "wave_energy_index": 0.42}],
    }


def assert_no_reef(world):
    sea = world["cells"][0]
    assert sea["reef_growth_index"] == 0.0
    assert sea["reef_type"] == "none"
    assert sea["reef_system_id"] == -1
    assert world["reef_systems"] == []
    assert world["summary"]["reef_cell_count"] == 0
    assert world["summary"]["reef_total_area_km2"] == 0.0
    # Those favorable inputs still exist; only the unsupported habitat fails.
    assert sea["reef_island_support_index"] > 0.8
    assert sea["reef_wave_exposure_index"] == 0.42


@pytest.mark.parametrize("temperature", [-100.0, 1.0, 4.0, 39.0, 100.0])
def test_nonthermal_bonuses_cannot_create_cold_or_hot_unsupported_reef(temperature):
    assert_no_reef(enrich_world_with_reef_diagnostics(coastal_world(temperature)))


@pytest.mark.parametrize("extreme", [-100.0, 4.0, 39.0, 100.0])
def test_a_valid_annual_mean_cannot_hide_an_unsupported_season(extreme):
    # Even the -100 C case has a mean >4 C; no annual-only gate can catch it.
    monthly = [26.0] * 11 + [extreme]
    annual = math.fsum(monthly) / 12
    assert 4.0 < annual < 39.0
    world = coastal_world(annual, temperature_monthly_c=monthly)
    assert_no_reef(enrich_world_with_reef_diagnostics(world))


@pytest.mark.parametrize("monthly, expected_type", [
    ([5.0, 6.0, 7.0, 8.0, 10.0, 12.0, 12.0, 10.0, 8.0, 7.0, 6.0, 5.0], "cold_water_reef"),
    ([23.0, 23.0, 24.0, 25.0, 27.0, 29.0, 29.0, 27.0, 25.0, 24.0, 23.0, 23.0], "atoll_reef"),
])
def test_supported_cold_and_warm_seasonal_habitats_retain_growth_and_membership(monthly, expected_type):
    world = coastal_world(math.fsum(monthly) / 12, temperature_monthly_c=monthly)
    enrich_world_with_reef_diagnostics(world)
    sea = world["cells"][0]
    assert sea["reef_growth_index"] >= 0.46
    assert sea["reef_type"] == expected_type
    assert sea["reef_system_id"] == 0
    assert world["reef_systems"][0]["cell_ids"] == [0]
    assert world["summary"]["reef_cell_count"] == 1
    assert world["summary"]["reef_total_area_km2"] == 100.0


@pytest.mark.parametrize("monthly", [None, [], [26.0] * 11, "26", ["26"] * 12,
                                          [True] * 12, [math.nan] * 12, [math.inf] * 12])
def test_present_invalid_monthly_data_cannot_fall_back_to_a_valid_annual_mean(monthly):
    assert_no_reef(enrich_world_with_reef_diagnostics(coastal_world(26.0, temperature_monthly_c=monthly)))


def test_annual_only_inputs_remain_supported_and_model_policy_is_declared():
    with_months = coastal_world()
    annual_only = deepcopy(with_months)
    del annual_only["cells"][0]["temperature_monthly_c"]
    enrich_world_with_reef_diagnostics(with_months)
    enrich_world_with_reef_diagnostics(annual_only)
    assert annual_only["reef_systems"] == with_months["reef_systems"]
    assert annual_only["summary"] == with_months["summary"]
    model = annual_only["reef_diagnostics_model"]
    assert model["model"] == "heuristic_coastal_reef_v2"
    assert (model["minimum_temperature_c"], model["maximum_temperature_c"]) == (4.0, 39.0)
    assert model["temperature_bounds"] == "exclusive"
    assert model["missing_monthly_temperature_policy"] == "annual_only_if_field_absent"
    assert model["invalid_monthly_temperature_policy"] == "ineligible"


def test_thermal_gate_does_not_redefine_the_legacy_energy_stress_bleaching_proxy():
    # Remove one bonus so the existing clamp does not saturate both scores.
    calm = enrich_world_with_reef_diagnostics(coastal_world(26.0, fishery_productivity_index=0.0))
    stressed = enrich_world_with_reef_diagnostics(coastal_world(
        26.0, fishery_productivity_index=0.0, climate_energy_stress_index=1.0,
    ))
    assert calm["cells"][0]["reef_bleaching_risk_index"] == 0.0
    assert stressed["cells"][0]["reef_bleaching_risk_index"] == 0.24
    assert calm["cells"][0]["reef_growth_index"] - stressed["cells"][0]["reef_growth_index"] == pytest.approx(0.0384)
    hot = enrich_world_with_reef_diagnostics(coastal_world(
        100.0, climate_energy_stress_index=1.0, seasonal_aridity_index=1.0, ocean_current_temperature_c=5.0,
    ))
    assert_no_reef(hot)
    assert hot["cells"][0]["reef_bleaching_risk_index"] == 1.0


def test_reenrichment_removes_stale_reef_membership_when_season_becomes_ineligible():
    world = enrich_world_with_reef_diagnostics(coastal_world())
    assert world["reef_systems"]
    world["cells"][0]["temperature_monthly_c"][0] = 100.0
    enrich_world_with_reef_diagnostics(world)
    assert_no_reef(world)
    once = deepcopy(world)
    enrich_world_with_reef_diagnostics(world)
    assert world == once
