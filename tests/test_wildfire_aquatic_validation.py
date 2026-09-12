"""Historical scalar water exclusions plus current complete-world CLI checks."""

from copy import deepcopy
import math

import pytest
from typer.testing import CliRunner

from magic_geo.cli import app
from magic_geo.geo_validation_subsystems import validate_natural_subsystems
from magic_geo.io import write_json
from magic_geo.wildfire_aquatic_validation import validate_wildfire_aquatic_exclusion
from magic_geo.wildfire_disturbance import enrich_world_with_wildfire_disturbance
from support.ecology_worlds import current_ecology_world_readonly, historical_ecology_world_readonly
from support.prescribed_natural_public_worlds import current_world_readonly


def fire_world(**water_overrides):
    """Explicit historical v2 scalar contract; current parents have other tests."""
    water = {
        "id": 0, "area_km2": 1.0, "neighbors": [],
        "is_water": False, "is_lake": True, "water_body_type": "fresh_lake",
        "biome": "lake", "temperature_c": 18.0,
        "primary_productivity_index": 0.7, "vegetation_biomass_index": 0.0,
        "ecosystem_disturbance_pressure_index": 0.5, "seasonal_aridity_index": 1.0,
        **water_overrides,
    }
    land = {
        **water, "id": 1, "is_lake": False, "is_water": False,
        "water_body_type": "land", "biome": "temperate_forest",
        "vegetation_biomass_index": 1.0, "wildfire_spread_risk_index": 1.0,
        "climate_energy_stress_index": 1.0,
    }
    world = enrich_world_with_wildfire_disturbance({"cells": [water, land]})
    assert world["wildfire_disturbance_model"]["model"] == "heuristic_wildfire_aquatic_exclusion_v2"
    return world


def wildfire_check(world):
    return next(check for check in validate_natural_subsystems(world)
                if check["name"] == "wildfire_inverse_links_and_steps")


def assert_rejected(world, fragment):
    errors = validate_wildfire_aquatic_exclusion(world)
    assert any(fragment in error for error in errors), errors
    check = wildfire_check(world)
    assert not check["passed"]
    assert any(fragment in error for error in check["observed"]["errors"]), check["observed"]


@pytest.mark.parametrize("selector", [
    {"water_body_type": "fresh_lake", "is_lake": True},
    {"water_body_type": "saline_basin", "is_lake": True},
    {"water_body_type": "land", "is_lake": True},
    {"water_body_type": "fresh_lake", "is_lake": False},
    {"water_body_type": "inland_sea", "is_lake": False},
    {"water_body_type": "ocean", "is_lake": False},
    {"water_body_type": "continental_shelf", "is_lake": False},
    {"water_body_type": "land", "is_lake": False, "is_water": True},
])
def test_producer_and_independent_validation_agree_on_each_water_selector(selector):
    world = fire_world(**selector)
    assert validate_wildfire_aquatic_exclusion(world) == []
    assert wildfire_check(world)["passed"]
    world["cells"][0]["wildfire_ignition_potential_index"] = 0.000001
    # Neither this unrelated flag nor stale biome is authoritative habitat.
    world["cells"][0].update(aquatic_climate_proxy_applicable=False, biome="temperate_forest")
    assert_rejected(world, "wildfire aquatic cell 0: wildfire_ignition_potential_index")


@pytest.mark.parametrize("field,valid", [
    ("wildfire_fuel_continuity_index", 0.0),
    ("wildfire_ignition_potential_index", 0.0),
    ("wildfire_firebreak_index", 1.0),
])
@pytest.mark.parametrize("bad", [0.000001, "0", None, False, True, math.nan, math.inf])
def test_aquatic_numeric_policy_is_exact_and_rejects_non_numeric_values(field, valid, bad):
    world = fire_world()
    assert world["cells"][0][field] == valid
    world["cells"][0][field] = bad
    assert_rejected(world, f"wildfire aquatic cell 0: {field}")


@pytest.mark.parametrize("field,value", [
    ("wildfire_disturbance_regime", "seasonal_surface_fire"),
    ("wildfire_disturbance_regime", None),
    ("wildfire_spread_history_ids", [0]),
    ("wildfire_spread_history_ids", None),
    ("wildfire_spread_history_ids", {}),
])
def test_aquatic_regime_and_inverse_history_membership_are_enforced(field, value):
    world = fire_world()
    world["cells"][0][field] = value
    assert_rejected(world, "wildfire aquatic cell 0")


@pytest.mark.parametrize("field", ["ignition_cell_id", "cell_ids", "newly_burned_cell_ids", "active_front_cell_ids"])
def test_every_exported_history_source_or_affected_front_rejects_water(field):
    world = fire_world()
    history, = world["wildfire_spread_histories"]
    if field == "ignition_cell_id":
        history[field] = 0
    elif field == "cell_ids":
        history[field].append(0)
    else:
        history["steps"][0][field].append(0)
    # Keep the aquatic inverse links empty: each forward reference is checked
    # independently, including a front omitted from the history cell list.
    assert world["cells"][0]["wildfire_spread_history_ids"] == []
    assert_rejected(world, "aquatic source cell 0")


def test_dry_saline_land_can_burn_and_general_aquatic_metrics_are_not_zeroed():
    world = fire_world(water_body_type="saline_basin", is_lake=False,
                       vegetation_biomass_index=1.0, wildfire_spread_risk_index=1.0)
    assert world["cells"][0]["wildfire_spread_history_ids"]
    assert validate_wildfire_aquatic_exclusion(world) == []
    world = fire_world()
    world["cells"][0].update(wildfire_wind_alignment_index=0.9,
                            ecosystem_disturbance_pressure_index=0.8, species_richness_index=0.7)
    assert validate_wildfire_aquatic_exclusion(world) == []


def test_every_metadata_field_is_required_and_exact():
    original = fire_world()
    for field in original["wildfire_disturbance_model"]:
        world = deepcopy(original)
        world["wildfire_disturbance_model"][field] = "unsupported"
        assert_rejected(world, "wildfire aquatic model metadata")
        del world["wildfire_disturbance_model"][field]
        assert_rejected(world, "wildfire aquatic model metadata")


@pytest.mark.parametrize("metadata", [None, [], {}, "heuristic_wildfire_aquatic_exclusion_v2", {"model": []}])
def test_present_malformed_metadata_cannot_take_legacy_path(metadata):
    world = fire_world()
    world["wildfire_disturbance_model"] = metadata
    assert_rejected(world, "wildfire aquatic model metadata")


def test_unknown_model_or_extra_policy_is_refused():
    world = fire_world()
    world["wildfire_disturbance_model"]["model"] = "future_v3"
    assert_rejected(world, "wildfire aquatic model metadata")
    world = fire_world()
    world["wildfire_disturbance_model"]["unclaimed_policy"] = True
    assert_rejected(world, "wildfire aquatic model metadata")


def test_absent_model_retains_only_the_legacy_structural_path():
    world = fire_world(is_lake=False, water_body_type="land", vegetation_biomass_index=1.0,
                       wildfire_spread_risk_index=1.0)
    world["cells"][0].update(is_lake=True, water_body_type="fresh_lake")
    assert_rejected(world, "wildfire aquatic cell 0")
    del world["wildfire_disturbance_model"]
    assert validate_wildfire_aquatic_exclusion(world) == []
    check = wildfire_check(world)
    assert check["passed"], check["observed"]


@pytest.mark.parametrize("mutation", [
    lambda w: w.update(cells=None),
    lambda w: w["cells"].append(None),
    lambda w: w["cells"][0].update(id=[]),
    lambda w: w.update(wildfire_spread_histories=None),
    lambda w: w["wildfire_spread_histories"].append(None),
    lambda w: w["wildfire_spread_histories"][0].update(ignition_cell_id=[]),
    lambda w: w["wildfire_spread_histories"][0].update(cell_ids={}),
    lambda w: w["wildfire_spread_histories"][0].update(steps=[None]),
    lambda w: w["wildfire_spread_histories"][0]["steps"][0].update(active_front_cell_ids={}),
])
def test_helper_handles_malformed_sources_without_crashing(mutation):
    world = fire_world()
    mutation(world)
    assert validate_wildfire_aquatic_exclusion(world)


@pytest.fixture(scope="module")
def full_world():
    world = current_world_readonly("full")
    assert world["ecosystem_dynamics_model"]["model"] == "heuristic_ecosystem_climate_support_v5"
    assert world["wildfire_disturbance_model"]["model"] == "heuristic_wildfire_native_seasonal_prescribed_natural_parent_availability_v7"
    assert any(c["is_lake"] and not c["is_water"] for c in world["cells"])
    assert world["wildfire_spread_histories"], "actual current fixture must have a modeled fire history"
    return world


def invoke_validate(world, tmp_path):
    path = tmp_path / "world.json"
    write_json(path, world)
    result = CliRunner().invoke(app, ["validate", "--world", str(path)])
    assert result.exception is None or isinstance(result.exception, SystemExit), result.exception
    return result


def test_public_cli_accepts_current_and_absent_model_legacy(full_world, tmp_path):
    for legacy in (False, True):
        world = deepcopy(historical_ecology_world_readonly("warm") if legacy else full_world)
        if legacy:
            assert world["wildfire_disturbance_model"]["model"] == "heuristic_wildfire_native_seasonal_v3"
            del world["wildfire_disturbance_model"]
        result = invoke_validate(world, tmp_path)
        assert result.exit_code == 0, result.output


def test_public_cli_rejects_lake_ignition_and_unknown_metadata(full_world, tmp_path):
    world = deepcopy(full_world)
    lake = next(cell for cell in world["cells"] if cell["is_lake"] and not cell["is_water"])
    lake["wildfire_ignition_potential_index"] = 0.000001
    result = invoke_validate(world, tmp_path)
    assert result.exit_code == 1, result.output
    assert f"FAIL wildfire availability: cell {lake['id']}: wildfire_ignition_potential_index" in result.output.splitlines()
    world = deepcopy(full_world)
    world["wildfire_disturbance_model"]["model"] = "unknown_future_v3"
    result = invoke_validate(world, tmp_path)
    assert result.exit_code == 1, result.output
    assert "FAIL prescribed natural wildfire: exact matching fire6/7 declaration required" in result.output.splitlines()


def test_public_cli_rejects_lake_ignition_source_and_active_front(full_world, tmp_path):
    world = deepcopy(full_world)
    lake = next(cell for cell in world["cells"] if cell["is_lake"] and not cell["is_water"])
    history = world["wildfire_spread_histories"][0]
    for field in ("ignition_cell_id", "active_front_cell_ids"):
        changed = deepcopy(world)
        altered = changed["wildfire_spread_histories"][0]
        if field == "ignition_cell_id":
            altered[field] = lake["id"]
        else:
            altered["steps"][0][field].append(lake["id"])
        result = invoke_validate(changed, tmp_path)
        assert result.exit_code == 1, result.output
        # Current replay validates each entire history against supported seeds
        # and front membership. Isolated mutations prove neither link hides
        # behind the other failure.
        expected = "ignition_cell_id" if field == "ignition_cell_id" else "steps"
        assert f"FAIL wildfire availability: history {history['id']}: {expected}" in result.output.splitlines()
