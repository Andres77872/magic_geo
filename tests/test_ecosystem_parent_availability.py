"""Producer-only availability checks for the explicit historical ecosystem v4.

Archived cases are unchanged solved-cell input subsets, not complete worlds.
The small controls below isolate existing equations; no downstream fire,
species, crop or physical-habitability claim follows from these support flags.
"""
from copy import deepcopy
import json
import math
from pathlib import Path

import pytest

from magic_geo.ecosystem_dynamics import enrich_world_with_ecosystem_dynamics
from magic_geo.aquatic_climate_validation import _EXPECTED_MODELS


FIXTURE = Path(__file__).parent / "fixtures/terrestrial_primary_support/cells.json"
ARCHIVED = json.loads(FIXTURE.read_text())["cases"]
NEW_FLAGS = (
    "species_richness_supported",
    "ecosystem_wildfire_spread_risk_supported",
    "ecosystem_disturbance_pressure_supported",
    "vegetation_recovery_supported",
)
ALL_FLAGS = (
    "terrestrial_primary_climate_supported", "primary_productivity_supported",
    "vegetation_biomass_supported", "forest_growth_supported",
    "vegetation_succession_supported", *NEW_FLAGS,
)
UNAVAILABLE_FLOATS = (
    "primary_productivity_index", "vegetation_biomass_index", "forest_growth_index",
    "species_richness_index", "wildfire_spread_risk_index",
    "ecosystem_disturbance_pressure_index",
)
POLICIES = {
    "terrestrial_dependency_policy": "biomass_requires_supported_terrestrial_primary_forest_and_succession_require_supported_primary_biomass_and_disturbance",
    "species_richness_availability_policy": "requires_supported_primary_and_terrestrial_biomass_or_aquatic_structural_zero",
    "ecosystem_wildfire_availability_policy": "requires_supported_terrestrial_biomass_aquatic_risk_is_known_zero",
    "ecosystem_disturbance_availability_policy": "requires_supported_ecosystem_wildfire_risk_aquatic_descriptors_remain_applicable",
    "vegetation_recovery_availability_policy": "requires_supported_primary_and_disturbance_and_terrestrial_biomass_or_aquatic_structural_zero",
    "renewable_record_availability_policy": "requires_supported_resource_productivity_primary_disturbance_recovery_and_terrestrial_biomass_or_aquatic_structural_zero",
    "unsupported_parent_estimate_policy": "numeric_zero_with_false_support_flag_not_absence_damage_or_physical_nonburnability",
    "ecosystem_disturbance_input_scope": "static_empirical_fire_frequency_aridity_ecotone_erosion_settlement_wind_descriptors_not_observed_fire_or_final_wildfire_feedback",
    "aquatic_biomass_input_policy": "structural_zero_for_aquatic_richness_recovery_and_renewable_inputs_not_terrestrial_biomass_estimate",
}


def land_cell(temperature=18.0, **overrides):
    cell = {
        "id": 0, "is_water": False, "is_lake": False, "water_body_type": "land",
        "temperature_c": temperature, "biome": "temperate_forest",
        "precipitation_mm_y": 1800.0, "potential_evapotranspiration_mm_y": 800.0,
        "soil_moisture_index": 0.8, "fertility": 0.9, "growing_season_months": 12,
        "soil_organic_matter_fraction": 0.2, "wind_east": 0.2,
    }
    cell.update(overrides)
    return cell


def enrich(*cells):
    world = {"cells": list(cells), "summary": {},
             "ecosystem_dynamics_model": deepcopy(_EXPECTED_MODELS["heuristic_ecosystem_climate_support_v4"])}
    assert enrich_world_with_ecosystem_dynamics(world) is world
    return world


def assert_unsupported_land(world):
    cell = world["cells"][0]
    assert all(cell[flag] is False for flag in ALL_FLAGS)
    assert all(type(cell[key]) is float and cell[key] == 0.0 for key in UNAVAILABLE_FLOATS)
    assert type(cell["vegetation_recovery_years"]) is int
    assert cell["vegetation_recovery_years"] == 0
    assert cell["vegetation_succession_stage"] == "terrestrial_primary_proxy_unavailable"
    assert world["vegetation_succession_histories"] == []
    assert world["renewable_resource_records"] == []
    assert world["summary"]["high_wildfire_spread_risk_cell_count"] == 0
    assert all(world["summary"][flag + "_cell_count"] == 0 for flag in ALL_FLAGS)
    # Availability does not classify physical fuel or make a fire barrier.
    assert "wildfire_disturbance_regime" not in cell
    assert "wildfire_fuel_continuity_index" not in cell
    assert "wildfire_firebreak_index" not in cell


@pytest.mark.parametrize("case", ARCHIVED, ids=lambda case: case["name"])
def test_actual_archived_inputs_gate_all_parents_without_rewriting_physics(case):
    cell = deepcopy(case["inputs"])
    before = deepcopy(cell)
    world = enrich(cell)
    assert {key: cell[key] for key in before} == before
    if case["name"] in {"persistent_hot_rainforest", "hot_young_forest", "persistent_cold_land"}:
        assert case["expected_v3"]["primary_productivity_index"] > 0.0
        assert_unsupported_land(world)
    else:
        assert {key: cell[key] for key in case["expected_v3"]} == case["expected_v3"]
        assert all(cell[flag] is True for flag in NEW_FLAGS)
    first = deepcopy(world)
    enrich_world_with_ecosystem_dynamics(world)
    assert world == first


@pytest.mark.parametrize("temperature,supported", [
    (math.nextafter(-16.0, -math.inf), False), (-16.0, False),
    (math.nextafter(-16.0, math.inf), True),
    (math.nextafter(52.0, -math.inf), True), (52.0, False),
    (math.nextafter(52.0, math.inf), False), (18.0, True),
])
def test_parent_support_uses_existing_open_input_domain_even_at_roundoff_boundary(temperature, supported):
    world = enrich(land_cell(temperature))
    assert all(world["cells"][0][flag] is supported for flag in ALL_FLAGS)
    if not supported:
        assert_unsupported_land(world)


@pytest.mark.parametrize("temperature", [None, True, False, "18", [], {}, math.nan, math.inf, -math.inf, 10**400])
def test_invalid_annual_input_cannot_leave_additive_richness_or_disturbance(temperature):
    assert_unsupported_land(enrich(land_cell(
        temperature, ecotone_index=1.0, fire_frequency_index=1.0,
        seasonal_aridity_index=1.0, wind_east=1.0, erosion_rate=0.08,
        settlement_score=1.0,
    )))


def test_missing_annual_input_stays_absent_and_unavailable():
    cell = land_cell()
    del cell["temperature_c"]
    assert_unsupported_land(enrich(cell))
    assert "temperature_c" not in cell


def test_supported_land_retains_original_disturbance_forest_history_and_yield_equations():
    world = enrich(land_cell())
    cell = world["cells"][0]
    # Declared original coefficients: P=.966, B=.93032, risk=.22B+.02,
    # D=.42risk. The nonzero D must enter forest (-.16D) and yield (-.18D).
    expected = {
        "primary_productivity_index": 0.966, "vegetation_biomass_index": 0.93032,
        "species_richness_index": 0.77311, "wildfire_spread_risk_index": 0.22467,
        "ecosystem_disturbance_pressure_index": 0.094362,
        "forest_growth_index": 0.890432, "vegetation_recovery_years": 10,
        "vegetation_succession_stage": "mature_closed_canopy",
    }
    assert {key: cell[key] for key in expected} == expected
    assert all(cell[flag] is True for flag in ALL_FLAGS)
    assert len(world["renewable_resource_records"]) == 1
    resource = world["renewable_resource_records"][0]
    assert resource["resource_type"] == "forest_growth"
    assert resource["sustainable_yield_index"] == 0.805101
    assert resource["disturbance_risk_index"] == 0.094362
    history = world["vegetation_succession_histories"][0]
    assert history["steps"][0]["disturbance_pressure_index"] == 0.094362
    assert history["steps"][-1]["disturbance_pressure_index"] == 0.09535


def test_supported_zero_biomass_is_a_valid_zero_risk_input():
    world = enrich(land_cell(
        -15.0, biome="cold_desert", precipitation_mm_y=0.0,
        soil_moisture_index=0.0, fertility=0.0, growing_season_months=0,
        soil_organic_matter_fraction=0.0, ice_thickness_m=1200.0, wind_east=0.0,
    ))
    cell = world["cells"][0]
    assert all(cell[flag] is True for flag in ALL_FLAGS)
    for key in ("primary_productivity_index", "vegetation_biomass_index",
                "wildfire_spread_risk_index", "ecosystem_disturbance_pressure_index"):
        assert cell[key] == 0.0
    assert cell["vegetation_recovery_years"] == 68
    assert cell["vegetation_succession_stage"] == "barren_ice"


@pytest.mark.parametrize("selector", [
    {"is_water": True, "water_body_type": "ocean"},
    {"is_lake": True, "water_body_type": "fresh_lake"},
    {"is_lake": True, "water_body_type": "saline_basin"},
    {"water_body_type": "fresh_lake"},
])
@pytest.mark.parametrize("temperature,primary_available", [(18.0, True), (80.0, False), (-18.0, False), (None, False)])
def test_aquatic_structural_risk_zero_and_descriptor_disturbance_do_not_need_primary(selector, temperature, primary_available):
    world = enrich(land_cell(
        temperature, **selector, fire_frequency_index=1.0, wind_east=1.0,
        ecotone_index=0.5, erosion_rate=0.04, settlement_score=0.4,
        seasonal_aridity_index=0.3,
    ))
    cell = world["cells"][0]
    assert cell["vegetation_biomass_supported"] is False
    assert cell["vegetation_biomass_index"] == 0.0
    assert cell["species_richness_supported"] is primary_available
    assert cell["vegetation_recovery_supported"] is primary_available
    assert cell["ecosystem_wildfire_spread_risk_supported"] is True
    assert cell["wildfire_spread_risk_index"] == 0.0
    assert cell["ecosystem_disturbance_pressure_supported"] is True
    # .16*.5 + .14*.5 + .16*.4 + .12*.3 = .25, with no primary dependency.
    assert cell["ecosystem_disturbance_pressure_index"] == 0.25
    assert cell["vegetation_succession_supported"] is False
    assert cell["vegetation_succession_stage"] == "aquatic_primary_productivity"
    assert world["vegetation_succession_histories"] == []
    if primary_available:
        assert cell["species_richness_index"] > 0.0
        assert cell["vegetation_recovery_years"] > 0
    else:
        assert cell["species_richness_index"] == 0.0
        assert type(cell["vegetation_recovery_years"]) is int
        assert cell["vegetation_recovery_years"] == 0
        assert world["renewable_resource_records"] == []


def test_supported_aquatic_recovery_and_renewable_yield_use_structural_zero_biomass():
    world = enrich(land_cell(
        is_water=True, water_body_type="continental_shelf", ecotone_index=0.5,
        erosion_rate=0.04, settlement_score=0.4, seasonal_aridity_index=0.3,
    ))
    cell = world["cells"][0]
    assert cell["vegetation_biomass_supported"] is False
    assert cell["vegetation_succession_supported"] is False
    assert all(cell[flag] is True for flag in NEW_FLAGS)
    assert cell["species_richness_index"] == 0.5204
    assert cell["vegetation_recovery_years"] == 51
    assert len(world["renewable_resource_records"]) == 1
    resource = world["renewable_resource_records"][0]
    assert resource["resource_type"] == "fishery_productivity"
    assert resource["productivity_index"] == 0.5879
    assert resource["sustainable_yield_index"] == 0.396224
    assert resource["regeneration_years"] == 18
    assert resource["disturbance_risk_index"] == 0.25


def test_dry_saline_terrain_is_land_not_a_known_zero_aquatic_risk():
    dry = enrich(land_cell(80.0, water_body_type="saline_basin"))
    assert_unsupported_land(dry)
    wet = enrich(land_cell(80.0, water_body_type="saline_basin", is_lake=True))
    assert wet["cells"][0]["ecosystem_wildfire_spread_risk_supported"] is True
    assert wet["cells"][0]["ecosystem_disturbance_pressure_supported"] is True


def test_stale_flags_values_records_and_counters_rebuild_idempotently():
    world = enrich(land_cell())
    original = deepcopy(world)
    assert world["renewable_resource_records"] and world["vegetation_succession_histories"]
    world["cells"][0]["temperature_c"] = 80.0
    enrich_world_with_ecosystem_dynamics(world)
    assert_unsupported_land(world)
    cold_state = deepcopy(world)
    enrich_world_with_ecosystem_dynamics(world)
    assert world == cold_state
    # Parent flags and diagnostic numbers never feed their own next evaluation.
    for flag in ALL_FLAGS:
        world["cells"][0][flag] = False
    for key in UNAVAILABLE_FLOATS:
        world["cells"][0][key] = 1.0
    world["cells"][0]["temperature_c"] = 18.0
    enrich_world_with_ecosystem_dynamics(world)
    assert world == original


def test_mixed_summary_counts_distinguish_aquatic_structure_and_missing_parents():
    world = enrich(
        land_cell(id=0), land_cell(80.0, id=1),
        land_cell(id=2, is_lake=True, water_body_type="fresh_lake"),
        land_cell(80.0, id=3, is_lake=True, water_body_type="saline_basin"),
    )
    summary = world["summary"]
    assert summary["species_richness_supported_cell_count"] == 2
    assert summary["vegetation_recovery_supported_cell_count"] == 2
    assert summary["ecosystem_wildfire_spread_risk_supported_cell_count"] == 3
    assert summary["ecosystem_disturbance_pressure_supported_cell_count"] == 3
    assert summary["vegetation_biomass_supported_cell_count"] == 1
    # Existing means retain the all-cell denominator, explicitly including
    # unavailable sentinels. They are not means of only supported estimates.
    # Land .7731104 and freshwater .4032, divided by all four cells.
    assert summary["mean_species_richness_index"] == 0.294078
    assert summary["mean_wildfire_spread_risk_index"] == 0.056168
    for flag in ALL_FLAGS:
        assert type(summary[flag + "_cell_count"]) is int


def test_metadata_declares_exact_parent_scope_and_no_final_fire_feedback():
    world = enrich(land_cell())
    model = world["ecosystem_dynamics_model"]
    assert model["model"] == "heuristic_ecosystem_climate_support_v4"
    assert {key: model[key] for key in POLICIES} == POLICIES
    assert model["summary_availability_policy"] == "all_cell_means_include_unavailable_zero_sentinels_with_supported_cell_counts"
    reference = deepcopy(world)
    final_fire = {
        "wildfire_disturbance_regime": "frequent_fire",
        "wildfire_fuel_continuity_index": 1.0, "wildfire_firebreak_index": 0.0,
        "wildfire_ignition_potential_index": 1.0, "wildfire_wind_alignment_index": 1.0,
        "wildfire_spread_history_ids": [123],
    }
    world["cells"][0].update(final_fire)
    world["wildfire_spread_histories"] = [{"marker": "downstream-only"}]
    histories = world["wildfire_spread_histories"]
    enrich_world_with_ecosystem_dynamics(world)
    assert world["wildfire_spread_histories"] is histories
    assert {key: value for key, value in world["cells"][0].items() if key not in final_fire} == reference["cells"][0]
    assert world["summary"] == reference["summary"]
    assert {key: world["cells"][0][key] for key in final_fire} == final_fire
