"""Independent thermal eligibility, strict model dispatch, and public reports."""

from __future__ import annotations

from copy import deepcopy
import math

import pytest
from typer.testing import CliRunner

from magic_geo.cli import app
from magic_geo.geo_validation_subsystems import validate_natural_subsystems
from magic_geo.io import write_json
from magic_geo.reef_diagnostics import enrich_world_with_reef_diagnostics
from magic_geo.reef_thermal_validation import validate_reef_thermal_habitat
from support.worlds import cached_legacy_world_readonly, cached_world_readonly


def reef_world() -> dict:
    world = {
        "cells": [
            {
                "id": 0, "neighbors": [1], "area_km2": 100.0,
                "lat_deg": 0.0, "lon_deg": 0.0, "is_water": True,
                "water_body_type": "continental_shelf", "water_depth_m": 5.0,
                "temperature_c": 26.0, "temperature_monthly_c": [26.0] * 12,
                "fishery_productivity_index": 1.0,
            },
            {
                "id": 1, "neighbors": [0], "area_km2": 100.0,
                "lat_deg": 0.0, "lon_deg": 1.0, "is_water": False,
                "water_body_type": "land", "island_class": "island",
                "volcanic_potential_index": 1.0, "crust_age_ma": 0.0,
            },
        ],
        "coastal_features": [{"id": 0, "cell_id": 1, "wave_energy_index": 0.42}],
    }
    enrich_world_with_reef_diagnostics(world)
    assert world["cells"][0]["reef_growth_index"] >= 0.46
    assert world["reef_systems"][0]["cell_ids"] == [0]
    return world


def reef_check(world: dict) -> dict:
    return next(check for check in validate_natural_subsystems(world)
                if check["name"] == "reef_membership_sources_and_ranges")


def assert_thermal_rejection(world: dict) -> None:
    errors = validate_reef_thermal_habitat(world)
    assert any("reef thermal habitat cell 0" in error for error in errors), errors
    check = reef_check(world)
    assert check["status"] == "failed"
    assert any("reef thermal habitat cell 0" in error for error in check["observed"]["errors"])


def test_producer_model_and_valid_reef_pass_independent_subsystem_check():
    world = reef_world()
    assert validate_reef_thermal_habitat(world) == []
    check = reef_check(world)
    assert check["passed"], check["observed"]


@pytest.mark.parametrize("annual", [-100.0, 4.0, 39.0, 100.0, None, "26", True, math.nan, math.inf, 10**400])
def test_tampered_annual_temperature_cannot_keep_valid_reef_membership(annual):
    world = reef_world()
    world["cells"][0]["temperature_c"] = annual
    assert_thermal_rejection(world)


@pytest.mark.parametrize("monthly", [
    None, [], [26.0] * 11, [26.0] * 13, "26", (26.0,) * 12,
])
def test_present_malformed_months_do_not_use_annual_fallback(monthly):
    world = reef_world()
    world["cells"][0]["temperature_monthly_c"] = monthly
    assert_thermal_rejection(world)


@pytest.mark.parametrize("extreme", [-100.0, 4.0, 39.0, 100.0, None, "26", True, math.nan, math.inf, 10**400])
def test_one_bad_month_cannot_hide_behind_a_valid_annual_mean(extreme):
    world = reef_world()
    world["cells"][0]["temperature_monthly_c"][7] = extreme
    assert_thermal_rejection(world)


def test_open_bounds_and_absent_monthly_fallback():
    world = reef_world()
    sea = world["cells"][0]
    sea["temperature_monthly_c"] = [math.nextafter(4.0, 5.0)] * 6 + [math.nextafter(39.0, 38.0)] * 6
    assert validate_reef_thermal_habitat(world) == []
    del sea["temperature_monthly_c"]
    assert validate_reef_thermal_habitat(world) == []
    assert reef_check(world)["passed"]
    sea["temperature_c"] = 39.0
    assert_thermal_rejection(world)


def test_subthreshold_growth_still_requires_thermal_habitat():
    world = reef_world()
    sea = world["cells"][0]
    sea.update(reef_growth_index=0.000001, reef_type="none", reef_system_id=-1)
    world["reef_systems"] = []
    world["summary"].update(reef_system_count=0, reef_cell_count=0, reef_total_area_km2=0)
    sea["temperature_monthly_c"][0] = 100.0
    assert_thermal_rejection(world)
    sea["reef_growth_index"] = 0.0
    assert validate_reef_thermal_habitat(world) == []
    check = reef_check(world)
    assert check["passed"], check["observed"]


def test_zero_growth_cannot_hide_an_existing_thermally_ineligible_membership():
    world = reef_world()
    world["cells"][0].update(reef_growth_index=0.0, temperature_c=100.0)
    assert_thermal_rejection(world)


@pytest.mark.parametrize("field", [
    "model", "thermal_eligibility", "minimum_temperature_c", "maximum_temperature_c",
    "temperature_bounds", "monthly_temperature_count", "missing_monthly_temperature_policy",
    "invalid_monthly_temperature_policy", "bleaching_model", "thermal_limits_scope",
])
def test_each_metadata_field_is_authoritative_and_cannot_be_rewritten(field):
    world = reef_world()
    world["reef_diagnostics_model"][field] = "unsupported"
    assert validate_reef_thermal_habitat(world) == [f"reef thermal model metadata has invalid {field}"]
    assert not reef_check(world)["passed"]
    del world["reef_diagnostics_model"][field]
    assert "metadata" in validate_reef_thermal_habitat(world)[0]
    assert not reef_check(world)["passed"]


@pytest.mark.parametrize("model", [None, [], {}, "heuristic_coastal_reef_v2"])
def test_present_invalid_declaration_never_falls_back_to_legacy(model):
    world = reef_world()
    world["reef_diagnostics_model"] = model
    assert "metadata" in validate_reef_thermal_habitat(world)[0]
    assert not reef_check(world)["passed"]


def test_model_count_type_and_unknown_metadata_are_rejected():
    world = reef_world()
    world["reef_diagnostics_model"]["monthly_temperature_count"] = 12.0
    assert validate_reef_thermal_habitat(world) == ["reef thermal model metadata has invalid monthly_temperature_count"]
    world["reef_diagnostics_model"]["monthly_temperature_count"] = 12
    world["reef_diagnostics_model"]["unsupported_override"] = True
    assert "metadata" in validate_reef_thermal_habitat(world)[0]


def test_absent_model_explicitly_preserves_legacy_structural_compatibility():
    world = reef_world()
    del world["reef_diagnostics_model"]
    world["cells"][0].update(temperature_c=100.0, temperature_monthly_c=None)
    assert validate_reef_thermal_habitat(world) == []
    assert reef_check(world)["passed"]


@pytest.fixture(scope="module")
def full_world():
    return cached_world_readonly("replay_128")


def invoke_validate(world, tmp_path):
    path = tmp_path / "world.json"
    write_json(path, world)
    result = CliRunner().invoke(app, ["validate", "--world", str(path)])
    assert result.exception is None or isinstance(result.exception, SystemExit), result.exception
    return result


def test_public_cli_accepts_current_and_absent_model_legacy(full_world, tmp_path):
    for legacy in (False, True):
        # The native model deliberately omits legacy bleaching estimates.
        # An absent-model compatibility control must retain actual old-model
        # fields rather than stripping the declaration from a native result.
        world = deepcopy(cached_legacy_world_readonly("energy_128") if legacy else full_world)
        if legacy:
            del world["reef_diagnostics_model"]
        result = invoke_validate(world, tmp_path)
        assert result.exit_code == 0, result.output


def test_public_cli_reports_unsupported_reef_metadata(full_world, tmp_path):
    world = deepcopy(full_world)
    world["reef_diagnostics_model"]["minimum_temperature_c"] = -100.0
    result = invoke_validate(world, tmp_path)
    assert result.exit_code == 1, result.output
    assert "FAIL reef thermal model metadata has invalid minimum_temperature_c" in result.output.splitlines()


def test_public_cli_reports_thermally_ineligible_subthreshold_growth(full_world, tmp_path):
    world = deepcopy(full_world)
    cell = next(cell for cell in world["cells"] if cell["reef_growth_index"] == 0.0 and (
        not 4.0 < cell["temperature_c"] < 39.0
        or any(not 4.0 < value < 39.0 for value in cell["temperature_monthly_c"])
    ))
    cell["reef_growth_index"] = 0.1
    world["summary"]["mean_reef_growth_index"] = sum(c["reef_growth_index"] for c in world["cells"]) / len(world["cells"])
    result = invoke_validate(world, tmp_path)
    assert result.exit_code == 1, result.output
    expected = (f"FAIL reef thermal habitat cell {cell['id']}: positive growth or membership "
                "requires annual and all supplied monthly means in (4, 39) C")
    assert expected in result.output.splitlines()
