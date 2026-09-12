"""Independent annual air-climate applicability and upstream support checks."""

from __future__ import annotations

from copy import deepcopy
import math

import pytest
from typer.testing import CliRunner

from magic_geo.aquatic_climate_validation import _EXPECTED_MODELS, validate_aquatic_climate_support
from magic_geo.cli import app
from magic_geo.ecosystem_dynamics import enrich_world_with_ecosystem_dynamics
from magic_geo.geo_validation_subsystems import validate_natural_subsystems
from magic_geo.io import write_json
from support.ecology_worlds import current_ecology_world_readonly, historical_ecology_world_readonly
from support.prescribed_natural_public_worlds import (
    current_world_readonly, clear_for_deliberate_upgrade, replay_tail,
)


def aquatic_world(temperature=18.0, **overrides):
    cell = {
        "id": 0, "area_km2": 100.0, "neighbors": [],
        "is_water": True, "is_lake": False,
        "water_body_type": "continental_shelf", "biome": "ocean",
        "temperature_c": temperature, "temperature_monthly_c": [temperature] * 12,
        "runoff_mm_y": 900.0, "ocean_current_temperature_c": 4.5,
        "ocean_current_east": 1.0, "soil_moisture_index": 1.0,
        "fertility": 1.0, "precipitation_mm_y": 1000.0,
        "potential_evapotranspiration_mm_y": 500.0, "growing_season_months": 12,
        **overrides,
    }
    # These mutation controls exercise the historical E4 validator scope.
    return enrich_world_with_ecosystem_dynamics({"cells": [cell],
        "ecosystem_dynamics_model": deepcopy(_EXPECTED_MODELS["heuristic_ecosystem_climate_support_v4"])})


def ecosystem_check(world):
    return next(check for check in validate_natural_subsystems(world)
                if check["name"] == "succession_and_renewable_sources")


def assert_rejected(world, fragment):
    fragments = (fragment,) if isinstance(fragment, str) else fragment
    errors = validate_aquatic_climate_support(world)
    assert any(part in error for error in errors for part in fragments), errors
    check = ecosystem_check(world)
    assert check["status"] == "failed"
    assert any(part in error for error in check["observed"]["errors"] for part in fragments), check["observed"]


MODEL_ERRORS = ("model metadata", "exact ecosystem v4 declaration")
V4_FLAGS = (
    "terrestrial_primary_climate_supported", "primary_productivity_supported",
    "vegetation_biomass_supported", "forest_growth_supported", "vegetation_succession_supported",
    "species_richness_supported", "ecosystem_wildfire_spread_risk_supported",
    "ecosystem_disturbance_pressure_supported", "vegetation_recovery_supported",
)


def remove_v4_availability_from_synthetic_projection(world):
    # These deliberately constructed old-contract inputs exercise validator
    # compatibility. They are not represented as generated historical worlds.
    for cell in world["cells"]:
        for field in V4_FLAGS:
            del cell[field]
    for field in V4_FLAGS:
        del world["summary"][field + "_cell_count"]


@pytest.mark.parametrize("temperature,primary,fishery,derived", [
    (-100.0, False, False, False), (-20.0, False, False, False),
    (-18.0, False, True, False), (-16.0, False, True, False),
    (math.nextafter(-16.0, 0.0), True, True, True), (18.0, True, True, True),
    (math.nextafter(44.0, 0.0), True, True, True), (44.0, True, False, False),
    (48.0, True, False, False), (52.0, False, False, False), (100.0, False, False, False),
])
def test_direct_climate_and_derived_support_are_distinct_and_match_producer(temperature, primary, fishery, derived):
    world = aquatic_world(temperature)
    cell = world["cells"][0]
    assert cell["aquatic_climate_proxy_applicable"] is True
    assert cell["aquatic_primary_climate_supported"] is primary
    assert cell["fishery_climate_supported"] is fishery
    assert cell["fishery_productivity_supported"] is derived
    assert validate_aquatic_climate_support(world) == []
    check = ecosystem_check(world)
    assert check["passed"], check["observed"]
    if not primary:
        assert cell["primary_productivity_index"] == 0.0
    if not derived:
        assert cell["fishery_productivity_index"] == 0.0
        assert not any(record["resource_type"] == "fishery_productivity"
                       for record in world["renewable_resource_records"])


@pytest.mark.parametrize("water_body,is_water,is_lake,aquatic,fishery", [
    ("ocean", True, False, True, True),
    ("fresh_lake", False, True, True, True),
    ("fresh_lake", False, False, True, True),
    ("inland_sea", False, False, True, True),
    ("saline_basin", False, True, True, False),
    ("saline_basin", False, False, False, False),
    ("land", False, False, False, False),
])
def test_marine_lake_and_dry_basin_applicability(water_body, is_water, is_lake, aquatic, fishery):
    world = aquatic_world(water_body_type=water_body, is_water=is_water, is_lake=is_lake)
    cell = world["cells"][0]
    assert cell["aquatic_climate_proxy_applicable"] is aquatic
    assert cell["aquatic_primary_climate_supported"] is aquatic
    assert cell["fishery_climate_supported"] is fishery
    assert cell["fishery_productivity_supported"] is fishery
    assert validate_aquatic_climate_support(world) == []


@pytest.mark.parametrize("flag", ["aquatic_climate_proxy_applicable", "aquatic_primary_climate_supported",
                                   "fishery_climate_supported", "fishery_productivity_supported"])
def test_missing_wrong_and_nonboolean_support_flags_are_rejected(flag):
    world = aquatic_world()
    for value in [False, 1, None, "true"]:
        world["cells"][0][flag] = value
        assert_rejected(world, flag)
    del world["cells"][0][flag]
    assert_rejected(world, flag)


@pytest.mark.parametrize("temperature,field", [
    (-100.0, "primary_productivity_index"), (-18.0, "primary_productivity_index"),
    (-18.0, "fishery_productivity_index"), (48.0, "fishery_productivity_index"),
    (100.0, "fishery_productivity_index"),
])
def test_unsupported_positive_estimates_are_rejected_even_below_record_threshold(temperature, field):
    world = aquatic_world(temperature)
    assert world["cells"][0][field] == 0.0
    world["cells"][0][field] = 0.000001
    assert_rejected(world, field)


def test_unsupported_primary_cannot_be_used_as_known_zero_for_a_fishery_record():
    supported = aquatic_world()
    record = next(record for record in supported["renewable_resource_records"]
                  if record["resource_type"] == "fishery_productivity")
    world = aquatic_world(-18.0)
    assert world["cells"][0]["fishery_climate_supported"] is True
    assert world["cells"][0]["aquatic_primary_climate_supported"] is False
    assert world["cells"][0]["fishery_productivity_supported"] is False
    world["renewable_resource_records"] = [deepcopy(record)]
    world["summary"]["renewable_resource_record_count"] = 1
    assert_rejected(world, "fishery record 0")


def test_supported_zero_primary_is_not_treated_as_missing_or_unsupported():
    # Support derives from declared source applicability, not numeric P>0.
    world = aquatic_world()
    world["cells"][0]["primary_productivity_index"] = 0.0
    assert world["cells"][0]["fishery_productivity_supported"] is True
    assert validate_aquatic_climate_support(world) == []


@pytest.mark.parametrize("annual", [None, True, "18", math.nan, math.inf, 10**400])
def test_invalid_annual_source_is_not_coerced_or_recovered_from_months(annual):
    world = aquatic_world(annual, temperature_monthly_c=[18.0] * 12)
    cell = world["cells"][0]
    assert cell["aquatic_primary_climate_supported"] is False
    assert cell["fishery_climate_supported"] is False
    assert cell["fishery_productivity_supported"] is False
    assert validate_aquatic_climate_support(world) == []
    cell["aquatic_primary_climate_supported"] = True
    assert_rejected(world, "aquatic_primary_climate_supported")


@pytest.mark.parametrize("monthly", [None, [], [100.0] * 12, [math.nan] * 12, "unsupported"])
def test_monthly_data_is_not_an_annual_proxy_eligibility_gate(monthly):
    world = aquatic_world(temperature_monthly_c=monthly)
    assert world["cells"][0]["fishery_productivity_supported"] is True
    assert validate_aquatic_climate_support(world) == []


@pytest.mark.parametrize("temperature,supported", [(18.0, True), (100.0, False)])
def test_non_aquatic_primary_uses_its_own_terrestrial_support(temperature, supported):
    for water_body in ["land", "saline_basin"]:
        world = aquatic_world(temperature, is_water=False, is_lake=False, water_body_type=water_body)
        assert world["cells"][0]["aquatic_climate_proxy_applicable"] is False
        assert world["cells"][0]["terrestrial_primary_climate_supported"] is supported
        assert world["cells"][0]["primary_productivity_supported"] is supported
        assert (world["cells"][0]["primary_productivity_index"] > 0.0) is supported
        assert validate_aquatic_climate_support(world) == []


def test_every_model_field_is_required_and_cannot_be_redefined():
    original = aquatic_world()
    for field in original["ecosystem_dynamics_model"]:
        world = deepcopy(original)
        world["ecosystem_dynamics_model"][field] = "unsupported"
        assert_rejected(world, MODEL_ERRORS)
        del world["ecosystem_dynamics_model"][field]
        assert_rejected(world, MODEL_ERRORS)


@pytest.mark.parametrize("model", [None, {}, [], "heuristic_ecosystem_climate_support_v2"])
def test_present_invalid_model_never_falls_back_to_legacy(model):
    world = aquatic_world()
    world["ecosystem_dynamics_model"] = model
    assert_rejected(world, MODEL_ERRORS)


def test_unknown_model_and_extra_metadata_are_rejected():
    world = aquatic_world()
    world["ecosystem_dynamics_model"]["model"] = "future_unknown_v3"
    assert_rejected(world, MODEL_ERRORS)
    world = aquatic_world()
    world["ecosystem_dynamics_model"]["extra_policy"] = True
    assert_rejected(world, "model metadata")


def test_absent_model_preserves_legacy_payloads_without_support_flags():
    world = aquatic_world()
    del world["ecosystem_dynamics_model"]
    assert_rejected(world, "exact ecosystem v4 declaration")
    remove_v4_availability_from_synthetic_projection(world)
    cell = world["cells"][0]
    cell["temperature_c"] = 100.0
    for field in ["aquatic_climate_proxy_applicable", "aquatic_primary_climate_supported",
                  "fishery_climate_supported", "fishery_productivity_supported"]:
        del cell[field]
    assert validate_aquatic_climate_support(world) == []
    check = ecosystem_check(world)
    assert check["passed"], check["observed"]


@pytest.mark.parametrize("water_type,is_water,is_lake", [
    ("ocean", True, False), ("fresh_lake", False, True),
    ("fresh_lake", False, False), ("saline_basin", False, True),
])
def test_v4_keeps_the_shared_aquatic_selector_for_terrestrial_exclusions(water_type, is_water, is_lake):
    world = aquatic_world(water_body_type=water_type, is_water=is_water, is_lake=is_lake,
                          biome="temperate_forest", fire_frequency_index=1.0, wind_east=1.0)
    assert world["ecosystem_dynamics_model"]["model"] == "heuristic_ecosystem_climate_support_v4"
    cell = world["cells"][0]
    for field in ["vegetation_biomass_index", "forest_growth_index", "wildfire_spread_risk_index"]:
        assert cell[field] == 0.0
    assert cell["vegetation_succession_stage"] == "aquatic_primary_productivity"
    assert world["vegetation_succession_histories"] == []
    assert not any(record["resource_type"] == "forest_growth" for record in world["renewable_resource_records"])
    assert validate_aquatic_climate_support(world) == []


@pytest.mark.parametrize("water_type", ["fresh_lake", "saline_basin"])
@pytest.mark.parametrize("field", ["vegetation_biomass_index", "forest_growth_index", "wildfire_spread_risk_index"])
def test_standing_lake_terrestrial_numeric_tampers_are_rejected(water_type, field):
    world = aquatic_world(water_body_type=water_type, is_water=False, is_lake=True)
    for value in [0.000001, False, None, "0"]:
        world["cells"][0][field] = value
        assert_rejected(world, f"aquatic ecology cell 0: {field}")


def test_aquatic_succession_stage_cannot_be_changed_to_terrestrial():
    world = aquatic_world(water_body_type="fresh_lake", is_water=False, is_lake=True)
    world["cells"][0]["vegetation_succession_stage"] = "mid_successional_cover"
    assert_rejected(world, "aquatic ecology cell 0: vegetation_succession_stage")


def terrestrial_records():
    land = aquatic_world(is_water=False, water_body_type="land", biome="temperate_forest",
                         soil_organic_matter_fraction=1.0)
    history = land["vegetation_succession_histories"][0]
    resource = next(record for record in land["renewable_resource_records"] if record["resource_type"] == "forest_growth")
    return history, resource


@pytest.mark.parametrize("water_type", ["fresh_lake", "saline_basin"])
def test_lakes_cannot_claim_terrestrial_histories_or_forest_resources(water_type):
    world = aquatic_world(water_body_type=water_type, is_water=False, is_lake=True)
    history, resource = terrestrial_records()
    world["vegetation_succession_histories"] = [history]
    world["renewable_resource_records"] = [resource]
    assert_rejected(world, "aquatic ecology succession history 0: aquatic source cell 0")
    assert_rejected(world, "aquatic ecology forest record 0: aquatic source cell 0")


def test_dry_saline_basin_retains_terrestrial_ecology():
    world = aquatic_world(water_body_type="saline_basin", is_water=False, is_lake=False,
                          biome="temperate_forest", soil_organic_matter_fraction=1.0,
                          fire_frequency_index=1.0)
    cell = world["cells"][0]
    assert cell["aquatic_climate_proxy_applicable"] is False
    assert cell["vegetation_biomass_index"] > 0
    assert cell["forest_growth_index"] > 0
    assert cell["wildfire_spread_risk_index"] > 0
    assert world["vegetation_succession_histories"]
    assert any(record["resource_type"] == "forest_growth" for record in world["renewable_resource_records"])
    assert validate_aquatic_climate_support(world) == []


def test_known_v2_keeps_its_support_contract_without_claiming_v3_lake_exclusions():
    world = aquatic_world(water_body_type="fresh_lake", is_water=False, is_lake=True)
    world["cells"][0].update(vegetation_biomass_index=0.3, forest_growth_index=0.2,
                            wildfire_spread_risk_index=0.1, vegetation_succession_stage="mid_successional_cover")
    assert validate_aquatic_climate_support(world)
    world["ecosystem_dynamics_model"] = deepcopy(_EXPECTED_MODELS["heuristic_ecosystem_climate_support_v2"])
    assert_rejected(world, "exact ecosystem v4 declaration")
    remove_v4_availability_from_synthetic_projection(world)
    assert validate_aquatic_climate_support(world) == []
    world["cells"][0]["fishery_productivity_supported"] = False
    assert_rejected(world, "fishery_productivity_supported mismatch")


def test_historical_and_current_metadata_policies_cannot_be_mixed():
    world = aquatic_world()
    world["ecosystem_dynamics_model"]["model"] = "heuristic_ecosystem_climate_support_v2"
    assert_rejected(world, MODEL_ERRORS)
    world = aquatic_world()
    del world["ecosystem_dynamics_model"]["aquatic_ecology_policy"]
    assert_rejected(world, "model metadata")


@pytest.fixture(scope="module")
def full_world():
    world = current_world_readonly("full")
    assert world["ecosystem_dynamics_model"]["model"] == "heuristic_ecosystem_climate_support_v5"
    return world


@pytest.fixture(scope="module")
def cold_world():
    """Upgrade a complete retained cold tail; preserve its actual native solve."""
    world = deepcopy(current_ecology_world_readonly("cold"))
    keys = ("climate_model", "climate_energy_model", "climate_energy_balance_records",
            "climate_energy_forcing_intervals", "climate_energy_transport_edges")
    references = {key: world[key] for key in keys}
    before = deepcopy(references)
    clear_for_deliberate_upgrade(world, "full")
    replay_tail(world, "full")
    assert all(world[key] is references[key] and world[key] == before[key] for key in keys)
    assert world["ecosystem_dynamics_model"]["model"] == "heuristic_ecosystem_climate_support_v5"
    return world


def invoke_validate(world, tmp_path):
    path = tmp_path / "world.json"
    write_json(path, world)
    result = CliRunner().invoke(app, ["validate", "--world", str(path)])
    assert result.exception is None or isinstance(result.exception, SystemExit), result.exception
    return result


def test_public_cli_accepts_current_and_legacy_payloads(full_world, tmp_path):
    for legacy in (False, True):
        world = deepcopy(historical_ecology_world_readonly("warm") if legacy else full_world)
        if legacy:
            del world["ecosystem_dynamics_model"]
            # This is a projection of an actual complete older ecosystem-v3 /
            # species-v2 world. The current v4/v3 chain requires declarations.
        result = invoke_validate(world, tmp_path)
        assert result.exit_code == 0, result.output


def test_public_cli_keeps_historical_species_dependencies_when_ecosystem_model_is_absent(tmp_path):
    world = deepcopy(historical_ecology_world_readonly("warm"))
    del world["ecosystem_dynamics_model"]
    cell = next(cell for cell in world["cells"] if cell["species_marine_fish_score_supported"])
    del cell["aquatic_primary_climate_supported"]
    result = invoke_validate(world, tmp_path)
    assert result.exit_code == 1, result.output
    expected = f"FAIL species habitat cell {cell['id']}: species_marine_fish_score_supported mismatch"
    assert expected in result.output.splitlines()


def test_public_cli_reports_invalid_model_and_support_flag(full_world, tmp_path):
    world = deepcopy(full_world)
    world["ecosystem_dynamics_model"]["aquatic_temperature_source"] = "measured_water_temperature"
    result = invoke_validate(world, tmp_path)
    assert result.exit_code == 1, result.output
    assert "FAIL prescribed natural ecosystem: ecosystem_dynamics_model.aquatic_temperature_source differs from raw-input replay" in result.output.splitlines()
    world = deepcopy(full_world)
    world["cells"][0]["fishery_productivity_supported"] = not world["cells"][0]["fishery_productivity_supported"]
    result = invoke_validate(world, tmp_path)
    assert result.exit_code == 1, result.output
    assert "FAIL prescribed natural ecosystem: cell 0.fishery_productivity_supported differs from raw-input replay" in result.output.splitlines()


def test_public_cli_rejects_unsupported_parent_fishery_record(full_world, cold_world, tmp_path):
    # Retain an actual complete cold native solution and replay its consumer
    # tail. Certified temperatures and all native certificates are unchanged.
    world = deepcopy(cold_world)
    baseline = invoke_validate(world, tmp_path)
    assert baseline.exit_code == 0, baseline.output
    cell = next(cell for cell in world["cells"]
                if cell["aquatic_climate_proxy_applicable"] and not cell["aquatic_primary_climate_supported"])
    assert not -16.0 < cell["temperature_c"] < 52.0
    assert cell["fishery_productivity_supported"] is False
    assert cell["primary_productivity_index"] == cell["fishery_productivity_index"] == 0.0
    record = deepcopy(next(record for record in full_world["renewable_resource_records"]
                           if record["resource_type"] == "fishery_productivity"))
    record["id"] = max((record["id"] for record in world["renewable_resource_records"]), default=-1) + 1
    record["cell_id"] = cell["id"]
    world["renewable_resource_records"].append(record)
    result = invoke_validate(world, tmp_path)
    assert result.exit_code == 1, result.output
    # E5 independently reconstructs complete source coverage and detects this
    # inserted record before a later per-record label check. The source above
    # is explicitly unsupported, with both unavailable numeric sentinels zero.
    expected = "FAIL prescribed natural ecosystem: renewable_resource_records length differs"
    assert expected in result.output.splitlines()


def test_public_cli_reports_standing_lake_terrestrial_biomass(full_world, tmp_path):
    world = deepcopy(full_world)
    cell = next(cell for cell in world["cells"] if cell["is_lake"] and not cell["is_water"])
    assert cell["vegetation_biomass_index"] == 0.0
    cell["vegetation_biomass_index"] = 0.000001
    result = invoke_validate(world, tmp_path)
    assert result.exit_code == 1, result.output
    expected = f"FAIL prescribed natural ecosystem: cell {cell['id']}.vegetation_biomass_index differs from raw-input replay"
    assert expected in result.output.splitlines()
