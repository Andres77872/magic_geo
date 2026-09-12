"""Historical E4 annual aquatic proxy equations and availability controls."""

from copy import deepcopy
import math

import pytest

from magic_geo.aquatic_climate_validation import _EXPECTED_MODELS
from magic_geo.ecosystem_dynamics import _fishery_productivity, enrich_world_with_ecosystem_dynamics


def aquatic_world(temperature=18.0, water_body="continental_shelf", **overrides):
    # These minimal fixtures retain the E4 numerical equations. Fresh E5
    # source-completeness and aquatic availability use complete retained worlds
    # in test_prescribed_natural_ecosystem and its input/public companions.
    return {"ecosystem_dynamics_model": deepcopy(_EXPECTED_MODELS["heuristic_ecosystem_climate_support_v4"]),
            "cells": [{
        "id": 0,
        # The native is_water mask describes marine water, excluding lakes.
        "is_water": water_body != "fresh_lake",
        "water_body_type": water_body,
        "biome": "lake" if water_body == "fresh_lake" else water_body,
        "temperature_c": temperature,
        "temperature_monthly_c": [temperature] * 12,
        "runoff_mm_y": 225.0,
        "ocean_current_temperature_c": 1.125,
        "ocean_current_east": 0.25,
        "precipitation_mm_y": 600.0,
        "potential_evapotranspiration_mm_y": 1000.0,
        "soil_moisture_index": 0.5,
        "fertility": 0.4,
        "growing_season_months": 9,
        "seasonal_aridity_index": 0.2,
        **overrides,
    }]}


def assert_unsupported(world):
    cell = world["cells"][0]
    assert cell["aquatic_climate_proxy_applicable"] is True
    assert cell["aquatic_primary_climate_supported"] is False
    assert cell["fishery_climate_supported"] is False
    assert cell["fishery_productivity_supported"] is False
    assert cell["primary_productivity_index"] == 0.0
    assert cell["fishery_productivity_index"] == 0.0
    assert world["renewable_resource_records"] == []
    assert world["summary"]["fishery_productivity_resource_count"] == 0
    assert world["summary"]["mean_primary_productivity_index"] == 0.0
    assert world["summary"]["mean_fishery_productivity_index"] == 0.0
    for key in (
        "primary_productivity_index", "vegetation_biomass_index", "species_richness_index",
        "wildfire_spread_risk_index", "ecosystem_disturbance_pressure_index",
        "forest_growth_index", "fishery_productivity_index",
    ):
        assert math.isfinite(cell[key])


@pytest.mark.parametrize("water_body", ["continental_shelf", "fresh_lake"])
@pytest.mark.parametrize("temperature", [-100.0, -20.0, 52.0, 100.0])
def test_no_bonus_can_create_a_resource_outside_both_temperature_supports(water_body, temperature):
    world = aquatic_world(
        temperature, water_body, runoff_mm_y=9000.0, ocean_current_temperature_c=4.5,
        ocean_current_east=1.0, fertility=1.0, soil_moisture_index=1.0,
    )
    assert_unsupported(enrich_world_with_ecosystem_dynamics(world))


@pytest.mark.parametrize("water_body, temperature, expected_primary, expected_fishery", [
    # Marine snapshots preserve the pre-guard formula. Freshwater references
    # use the existing aquatic formula with its 0.12 lake bonus; the native
    # nonmarine lake mask must no longer select the terrestrial formula.
    ("continental_shelf", -15.0, 0.412059, 0.557850),
    ("continental_shelf", 0.0, 0.517941, 0.650100),
    ("continental_shelf", 12.0, 0.602647, 0.723900),
    ("continental_shelf", 18.0, 0.645000, 0.715800),
    ("continental_shelf", 30.0, 0.560294, 0.642000),
    ("continental_shelf", 43.0, 0.468529, 0.562050),
    ("fresh_lake", -15.0, 0.332059, 0.410650),
    ("fresh_lake", 0.0, 0.437941, 0.502900),
    ("fresh_lake", 12.0, 0.522647, 0.576700),
    ("fresh_lake", 18.0, 0.565000, 0.568600),
    ("fresh_lake", 30.0, 0.480294, 0.494800),
    ("fresh_lake", 43.0, 0.388529, 0.414850),
])
def test_supported_annual_climates_preserve_existing_formulas_and_resource_records(
    water_body, temperature, expected_primary, expected_fishery,
):
    world = enrich_world_with_ecosystem_dynamics(aquatic_world(temperature, water_body))
    cell = world["cells"][0]
    assert cell["aquatic_climate_proxy_applicable"] is True
    assert cell["aquatic_primary_climate_supported"] is True
    assert cell["fishery_climate_supported"] is True
    assert cell["fishery_productivity_supported"] is True
    assert cell["primary_productivity_index"] == expected_primary
    assert cell["fishery_productivity_index"] == expected_fishery
    record, = world["renewable_resource_records"]
    assert record["resource_type"] == "fishery_productivity"
    assert record["productivity_index"] == expected_fishery
    assert record["formation_evidence"]["primary_productivity_index"] == expected_primary


@pytest.mark.parametrize("temperature, primary_supported, fishery_supported", [
    (-20.0, False, False), (-18.0, False, True), (-16.0, False, True),
    (44.0, True, False), (50.0, True, False), (52.0, False, False),
])
def test_each_proxy_uses_its_own_existing_open_support(temperature, primary_supported, fishery_supported):
    world = enrich_world_with_ecosystem_dynamics(aquatic_world(temperature))
    cell = world["cells"][0]
    assert cell["aquatic_primary_climate_supported"] is primary_supported
    assert cell["fishery_climate_supported"] is fishery_supported
    derived_supported = primary_supported and fishery_supported
    assert cell["fishery_productivity_supported"] is derived_supported
    assert (cell["primary_productivity_index"] > 0.0) is primary_supported
    assert (cell["fishery_productivity_index"] > 0.0) is derived_supported
    if not derived_supported:
        assert world["renewable_resource_records"] == []


def test_unsupported_primary_sentinel_is_not_a_supported_fishery_input():
    world = enrich_world_with_ecosystem_dynamics(aquatic_world(-18.0))
    cell = world["cells"][0]
    assert cell["fishery_climate_supported"] is True
    assert cell["aquatic_primary_climate_supported"] is False
    assert cell["fishery_productivity_supported"] is False
    assert cell["fishery_productivity_index"] == 0.0
    assert world["renewable_resource_records"] == []
    # In contrast, a valid physical zero at a supported temperature is a
    # usable numeric input; the formula's other modeled terms still apply.
    supported = aquatic_world(18.0)["cells"][0]
    assert _fishery_productivity(supported, 0.0) == pytest.approx(0.4965)


@pytest.mark.parametrize("temperature", [None, True, False, "18", {}, [], math.nan, math.inf, -math.inf, 10**400])
@pytest.mark.parametrize("water_body", ["continental_shelf", "fresh_lake"])
def test_invalid_or_nonfinite_annual_inputs_export_unsupported_finite_zero_estimates(temperature, water_body):
    assert_unsupported(enrich_world_with_ecosystem_dynamics(aquatic_world(temperature, water_body)))


def test_missing_annual_temperature_cannot_be_filled_from_monthly_values():
    world = aquatic_world(18.0)
    del world["cells"][0]["temperature_c"]
    assert_unsupported(enrich_world_with_ecosystem_dynamics(world))


def test_annual_support_does_not_invent_a_monthly_freezing_or_ice_veto():
    ordinary = enrich_world_with_ecosystem_dynamics(aquatic_world(0.0))
    seasonal = enrich_world_with_ecosystem_dynamics(aquatic_world(
        0.0, temperature_monthly_c=[-30.0] * 6 + [30.0] * 6, ice_thickness_m=20.0,
    ))
    for key in ("aquatic_primary_climate_supported", "fishery_climate_supported", "fishery_productivity_supported",
                "primary_productivity_index", "fishery_productivity_index"):
        assert seasonal["cells"][0][key] == ordinary["cells"][0][key]
    assert seasonal["renewable_resource_records"] == ordinary["renewable_resource_records"]


def test_non_aquatic_cells_are_distinct_from_unsupported_aquatic_inputs():
    world = aquatic_world(18.0, water_body="land", is_water=False, biome="temperate_forest")
    enrich_world_with_ecosystem_dynamics(world)
    cell = world["cells"][0]
    assert cell["aquatic_climate_proxy_applicable"] is False
    assert cell["aquatic_primary_climate_supported"] is False
    assert cell["fishery_climate_supported"] is False
    assert cell["fishery_productivity_supported"] is False
    assert cell["primary_productivity_index"] == 0.661
    assert cell["fishery_productivity_index"] == 0.0
    assert world["renewable_resource_records"][0]["resource_type"] == "forest_growth"


def test_model_declares_proxy_semantics_and_unsupported_numeric_policy():
    model = enrich_world_with_ecosystem_dynamics(aquatic_world())["ecosystem_dynamics_model"]
    assert model["model"] == "heuristic_ecosystem_climate_support_v4"
    assert model["aquatic_temperature_source"] == "annual_surface_air_climate_proxy"
    assert model["aquatic_selector"] == "is_water_or_is_lake_or_fishery_water_body_type"
    assert model["aquatic_ecology_policy"] == "shared_aquatic_selector_for_primary_and_terrestrial_exclusion"
    assert model["fishery_water_body_types"] == ["continental_shelf", "fresh_lake", "inland_sea", "ocean"]
    assert (model["aquatic_primary_minimum_temperature_c"], model["aquatic_primary_maximum_temperature_c"]) == (-16.0, 52.0)
    assert (model["fishery_minimum_temperature_c"], model["fishery_maximum_temperature_c"]) == (-20.0, 44.0)
    assert model["temperature_bounds"] == "exclusive"
    assert model["support_relationship"] == "fishery_estimate_requires_own_climate_and_supported_primary_input"
    assert model["monthly_temperature_policy"] == "not_used"
    assert model["unsupported_productivity_policy"] == "numeric_zero_with_false_support_flag"
    assert model["unsupported_fishery_record_policy"] == "no_record_without_supported_fishery_productivity"
    assert model["support_scope"] == "empirical_climate_proxy_not_aquatic_survival_limits"


def test_reenrichment_removes_stale_fisheries_and_preserves_idempotence():
    world = enrich_world_with_ecosystem_dynamics(aquatic_world())
    assert world["renewable_resource_records"]
    world["cells"][0]["temperature_c"] = 100.0
    enrich_world_with_ecosystem_dynamics(world)
    assert_unsupported(world)
    once = deepcopy(world)
    enrich_world_with_ecosystem_dynamics(world)
    assert world == once


def test_historical_empty_world_leaves_existing_declaration_unchanged():
    world = {"cells": [],
             "ecosystem_dynamics_model": deepcopy(_EXPECTED_MODELS["heuristic_ecosystem_climate_support_v4"])}
    before = deepcopy(world)
    assert enrich_world_with_ecosystem_dynamics(world) == before


def test_wet_saline_lakes_receive_primary_support_guard_without_classifying_dry_saltflats_as_water():
    wet = enrich_world_with_ecosystem_dynamics(aquatic_world(
        100.0, water_body="saline_basin", is_water=False, is_lake=True,
    ))
    assert_unsupported(wet)
    dry = enrich_world_with_ecosystem_dynamics(aquatic_world(
        100.0, water_body="saline_basin", is_water=False, is_lake=False,
    ))
    assert dry["cells"][0]["aquatic_climate_proxy_applicable"] is False
    assert dry["cells"][0]["terrestrial_primary_climate_supported"] is False
    assert dry["cells"][0]["primary_productivity_supported"] is False
    assert dry["cells"][0]["primary_productivity_index"] == 0.0
    assert dry["cells"][0]["fishery_climate_supported"] is False
    # The saline water type has never been in this generic fishery model.
    supported_wet = enrich_world_with_ecosystem_dynamics(aquatic_world(
        18.0, water_body="saline_basin", is_water=False, is_lake=True,
    ))
    assert supported_wet["cells"][0]["aquatic_primary_climate_supported"] is True
    assert supported_wet["cells"][0]["fishery_climate_supported"] is False
    assert supported_wet["renewable_resource_records"] == []
    supported_dry = enrich_world_with_ecosystem_dynamics(aquatic_world(
        18.0, water_body="saline_basin", is_water=False, is_lake=False,
    ))
    assert supported_dry["cells"][0]["aquatic_climate_proxy_applicable"] is False
    assert supported_dry["cells"][0]["terrestrial_primary_climate_supported"] is True
    assert supported_dry["cells"][0]["primary_productivity_index"] > 0.0
