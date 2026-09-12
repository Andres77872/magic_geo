"""Historical E4 lake equations and terrestrial exclusion; no default retagging."""

from copy import deepcopy

import pytest

from magic_geo.ecosystem_dynamics import enrich_world_with_ecosystem_dynamics
from magic_geo.aquatic_climate_validation import _EXPECTED_MODELS


def world_with_cell(**overrides):
    # Historical E4 formula controls use their original optional descriptors.
    return {"ecosystem_dynamics_model": deepcopy(_EXPECTED_MODELS["heuristic_ecosystem_climate_support_v4"]), "cells": [{
        "id": 0,
        "is_water": False,
        "is_lake": True,
        "water_body_type": "fresh_lake",
        "biome": "lake",
        "temperature_c": 18.0,
        "runoff_mm_y": 225.0,
        "precipitation_mm_y": 600.0,
        "potential_evapotranspiration_mm_y": 1000.0,
        "soil_moisture_index": 0.5,
        "soil_organic_matter_fraction": 0.3,
        "fertility": 0.4,
        "growing_season_months": 9,
        "seasonal_aridity_index": 0.2,
        "fire_frequency_index": 0.7,
        "wind_east": 0.5,
        **overrides,
    }]}


def assert_no_terrestrial_ecology(world):
    cell, = world["cells"]
    assert cell["aquatic_climate_proxy_applicable"] is True
    for key in ("vegetation_biomass_index", "forest_growth_index", "wildfire_spread_risk_index"):
        assert cell[key] == 0.0
        assert world["summary"]["mean_" + key] == 0.0
    assert cell["vegetation_succession_stage"] == "aquatic_primary_productivity"
    assert world["vegetation_succession_histories"] == []
    assert world["summary"]["vegetation_succession_history_count"] == 0
    assert world["summary"]["vegetation_succession_step_count"] == 0
    assert world["summary"]["forest_growth_resource_count"] == 0
    assert all(record["resource_type"] != "forest_growth" for record in world["renewable_resource_records"])


@pytest.mark.parametrize("water_body, bonus, supports_fishery", [
    ("fresh_lake", 0.12, True),
    ("inland_sea", 0.12, True),
    ("saline_basin", 0.04, False),
])
def test_nonmarine_standing_water_uses_existing_aquatic_productivity(water_body, bonus, supports_fishery):
    world = enrich_world_with_ecosystem_dynamics(world_with_cell(water_body_type=water_body))
    assert_no_terrestrial_ecology(world)
    cell, = world["cells"]
    # Independent reconstruction: optimum primary thermal response, one-quarter
    # normalized runoff, and no ocean current. Land fertility/moisture do not enter.
    primary = 0.12 + bonus + 0.24 + (225.0 / 900.0) * 0.22
    assert cell["primary_productivity_index"] == pytest.approx(primary)
    assert cell["fishery_productivity_supported"] is supports_fishery
    if supports_fishery:
        fishery = 0.18 + 0.34 * primary + 0.20 * 0.25 + 0.12 * (1.0 - 6.0 / 32.0)
        assert cell["fishery_productivity_index"] == pytest.approx(fishery)
        record, = world["renewable_resource_records"]
        assert record["resource_type"] == "fishery_productivity"
        assert record["water_dependency_index"] == pytest.approx(0.5 * 0.45 + 0.30)
        assert record["formation_evidence"]["vegetation_biomass_index"] == 0.0
    else:
        assert cell["fishery_productivity_index"] == 0.0
        assert world["renewable_resource_records"] == []


@pytest.mark.parametrize("selector", [
    {"is_lake": True, "water_body_type": "saline_basin"},
    {"is_lake": True, "water_body_type": "land"},
    {"is_lake": False, "water_body_type": "fresh_lake"},
    {"is_lake": False, "water_body_type": "inland_sea"},
    {"is_lake": False, "water_body_type": "ocean"},
    {"is_lake": False, "water_body_type": "continental_shelf"},
    {"is_lake": False, "is_water": True, "water_body_type": "land"},
])
def test_every_aquatic_selector_rejects_stale_forest_and_fire_inputs(selector):
    world = enrich_world_with_ecosystem_dynamics(world_with_cell(
        biome="temperate_forest", fertility=1.0, soil_moisture_index=1.0,
        soil_organic_matter_fraction=1.0, fire_frequency_index=1.0,
        seasonal_aridity_index=1.0, wind_east=1.0, **selector,
    ))
    assert_no_terrestrial_ecology(world)
    # This guard does not falsely declare a general aquatic disturbance or
    # species model solved: their separate diagnostic formulas remain active.
    assert world["cells"][0]["ecosystem_disturbance_pressure_index"] > 0.0
    assert world["cells"][0]["species_richness_index"] > 0.0


def test_dry_saline_basin_retains_terrestrial_formulas_and_records():
    land = enrich_world_with_ecosystem_dynamics(world_with_cell(
        is_lake=False, water_body_type="land", biome="temperate_forest",
    ))
    dry = enrich_world_with_ecosystem_dynamics(world_with_cell(
        is_lake=False, water_body_type="saline_basin", biome="temperate_forest",
    ))
    dry_cell, = dry["cells"]
    assert dry_cell["aquatic_climate_proxy_applicable"] is False
    # Captured existing land equation; changing only a dry-basin label cannot
    # switch its physical habitat or suppress terrestrial branches.
    assert dry_cell["primary_productivity_index"] == 0.661
    assert dry_cell["vegetation_biomass_index"] == 0.74772
    assert dry_cell["wildfire_spread_risk_index"] == 0.524498
    for key in ("primary_productivity_index", "vegetation_biomass_index", "forest_growth_index",
                "wildfire_spread_risk_index", "vegetation_succession_stage"):
        assert dry_cell[key] == land["cells"][0][key]
    assert dry["vegetation_succession_histories"] == land["vegetation_succession_histories"]
    assert dry["vegetation_succession_histories"]
    record, = dry["renewable_resource_records"]
    assert record["resource_type"] == "forest_growth"
    assert record["water_dependency_index"] == 0.225


def test_dry_saltflat_is_not_assigned_aquatic_succession():
    world = enrich_world_with_ecosystem_dynamics(world_with_cell(
        is_lake=False, water_body_type="saline_basin", biome="saltflat",
        fertility=0.0, soil_moisture_index=0.0, soil_organic_matter_fraction=0.0,
    ))
    cell, = world["cells"]
    assert cell["aquatic_climate_proxy_applicable"] is False
    assert cell["vegetation_succession_stage"] != "aquatic_primary_productivity"
    assert cell["wildfire_spread_risk_index"] > 0.0
    assert cell["fishery_productivity_supported"] is False


def test_standing_water_results_do_not_depend_on_marine_mask():
    lake = enrich_world_with_ecosystem_dynamics(world_with_cell())
    marine_flag = enrich_world_with_ecosystem_dynamics(world_with_cell(is_water=True))
    lake["cells"][0]["is_water"] = True
    assert lake == marine_flag


def test_reenrichment_removes_terrestrial_history_and_forest_after_inundation():
    world = enrich_world_with_ecosystem_dynamics(world_with_cell(
        is_lake=False, water_body_type="land", biome="temperate_forest",
    ))
    assert world["vegetation_succession_histories"]
    assert world["renewable_resource_records"][0]["resource_type"] == "forest_growth"
    world["cells"][0].update(is_lake=True, water_body_type="saline_basin")
    enrich_world_with_ecosystem_dynamics(world)
    assert_no_terrestrial_ecology(world)
    assert world["renewable_resource_records"] == []
    once = deepcopy(world)
    enrich_world_with_ecosystem_dynamics(world)
    assert world == once
