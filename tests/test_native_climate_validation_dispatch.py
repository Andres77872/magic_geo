"""Public native/legacy routing and unavailable-field mutation regressions."""
from __future__ import annotations

from copy import deepcopy
import importlib

import pytest
from typer.testing import CliRunner

from magic_geo.cli import app
from magic_geo.climate_energy_validation_dispatch import (
    climate_energy_validation_mode,
    validate_native_climate_energy_output,
)
from magic_geo.geo_validation_physics import _validate_climate_energy
from magic_geo.geo_validation_subsystems import _validate_ecosystems
from magic_geo.geo_validation import validate_geo_world
from magic_geo.native_climate_energy import enrich_world_with_native_climate_energy
from magic_geo.reef_diagnostics import enrich_world_with_reef_diagnostics
from magic_geo.serialization import CURRENT_WORLD_SCHEMA_VERSION
from support.native_climate_energy import native_climate_world
from support.worlds import cached_legacy_world_readonly


@pytest.fixture(scope="module")
def reference():
    return native_climate_world()


@pytest.fixture
def world(reference):
    return deepcopy(reference)


def physics_check(world):
    checks = []
    _validate_climate_energy(world, checks)
    assert len(checks) == 1
    assert checks[0]["name"] == "climate_energy_balance_replay"
    return checks[0]


def test_genuine_raw_and_enriched_native_physics_preserve_scope_and_values(world):
    for enriched in (False, True):
        if enriched:
            enrich_world_with_native_climate_energy(world)
        before = deepcopy(world)
        assert climate_energy_validation_mode(world) == "native"
        errors, report = validate_native_climate_energy_output(world)
        assert errors == [] and report["full_world_display_fields_linked"]
        check = physics_check(world)
        assert check["passed"], check
        assert check["expected"]["legacy_posthoc_diagnostics_present"] is False
        assert check["expected"]["unexported_thermal_trajectory_replayed"] is False
        assert "unexported_thermal_stage_trajectory" in check["observed"]["unverified"]
        assert world == before


def test_known_legacy_physics_still_replays_original_equations():
    world = cached_legacy_world_readonly("energy_128")
    assert climate_energy_validation_mode(world) == "legacy"
    check = physics_check(world)
    assert check["passed"], check
    assert "maximum_equation_residual" in check["observed"]


@pytest.mark.parametrize("value", [None, [], {}, True, "unknown_v2", {"model": "unknown_v2"}])
@pytest.mark.parametrize("key", ["climate_model", "climate_energy_model"])
def test_present_unknown_declarations_never_become_legacy(key, value):
    world = {key: value}
    with pytest.raises(ValueError, match="unknown or malformed"):
        climate_energy_validation_mode(world)
    assert not physics_check(world)["passed"]


@pytest.mark.parametrize("section", [
    "climate_energy_model", "climate_model", "climate_energy_balance_records",
    "climate_energy_forcing_intervals", "climate_energy_transport_edges", "cells",
])
def test_partial_native_envelope_cannot_fall_back(world, section):
    del world[section]
    assert climate_energy_validation_mode(world) == "native"
    errors, report = validate_native_climate_energy_output(world)
    assert errors and report is None and section in errors[0]
    assert not physics_check(world)["passed"]


@pytest.mark.parametrize("key,value", [
    ("climate_model", "prescribed_seasonal_surface_energy_v999"),
    ("climate_energy_model", "native_prescribed_seasonal_energy_v999"),
    ("climate_energy_model", {"ownership": "native_temperature_producer"}),
    ("climate_model", {"native_temperature_forcing_coupled": True}),
    ("climate_energy_transport_edges", []),
    ("native_climate_energy_enrichment_model", {}),
])
def test_isolated_native_signals_route_to_strict_audit(key, value):
    world = {key: value}
    assert climate_energy_validation_mode(world) == "native"
    assert validate_native_climate_energy_output(world)[0]
    assert not physics_check(world)["passed"]


@pytest.mark.parametrize("field", [
    "climate_energy_stress_index", "energy_balance_residual_c",
    "greenhouse_trapping_w_m2", "surface_albedo_index", "outgoing_longwave_w_m2",
    "radiative_equilibrium_temperature_c", "seasonal_insolation_range_w_m2",
])
@pytest.mark.parametrize("value", [0.0, None, []])
def test_unavailable_legacy_cell_aliases_are_rejected_even_at_zero(world, field, value):
    world["cells"][0][field] = value
    errors, report = validate_native_climate_energy_output(world)
    assert report is None and field in errors[0]
    assert "unavailable legacy posthoc" in errors[0]


@pytest.mark.parametrize("field", [
    "mean_climate_energy_stress_index", "high_climate_energy_stress_cell_count",
    "mean_abs_energy_balance_residual_c", "climate_energy_balance_record_count",
    "mean_outgoing_longwave_w_m2", "surface_albedo_regime_counts",
    "area_weighted_mean_greenhouse_trapping_w_m2",
])
def test_unavailable_legacy_summary_aliases_are_rejected(world, field):
    world["summary"] = {field: 0}
    errors, report = validate_native_climate_energy_output(world)
    assert report is None and field in errors[0]


@pytest.mark.parametrize("tamper,expected", [
    (lambda w: w.pop("climate_energy_model"), "climate_energy_model"),
    (lambda w: w.pop("climate_model"), "climate_model"),
    (lambda w: w.pop("cells"), "full cell linkage"),
    (lambda w: w.__setitem__("climate_energy_transport_edges", []), "horizontal_heat_convergence"),
    (lambda w: w["climate_energy_model"].__setitem__("model", "native_prescribed_seasonal_energy_v999"), "model"),
    (lambda w: w["climate_energy_balance_records"][0]["monthly_absorbed_shortwave_w_m2"].__setitem__(0, 999.0), "monthly_absorbed_shortwave"),
    (lambda w: w["cells"][0]["temperature_monthly_c"].__setitem__(0, 999.0), "temperature_monthly_c"),
    (lambda w: w["cells"][0].__setitem__("climate_energy_stress_index", []), "climate_energy_stress_index"),
    (lambda w: w.__setitem__("summary", {"mean_climate_energy_stress_index": 0.0}), "mean_climate_energy_stress_index"),
])
def test_public_cli_reports_native_errors_before_eager_legacy_consumers(world, tmp_path, monkeypatch, tamper, expected):
    world["schema_version"] = CURRENT_WORLD_SCHEMA_VERSION
    tamper(world)
    before = deepcopy(world)
    # The genuine fixture is deliberately a certificate/linkage projection,
    # not a complete civilization export. Exercise the public validation gate
    # directly after file decoding, before unrelated missing-family checks.
    module = importlib.import_module("magic_geo.cli.commands.validate")
    monkeypatch.setattr(module, "_load_world_for_cli", lambda _: world)
    path = tmp_path / "native.json"
    path.touch()
    result = CliRunner().invoke(app, ["validate", "--world", str(path)])
    assert result.exit_code == 1 and isinstance(result.exception, SystemExit), result.exception
    failures = result.output.splitlines()
    assert len(failures) == 1 and failures[0].startswith("FAIL native climate energy:"), result.output
    assert expected in failures[0], result.output
    assert world == before


def test_unknown_legacy_energy_extra_model_is_not_accepted():
    world = deepcopy(cached_legacy_world_readonly("energy_128"))
    world["climate_energy_model"]["model"] = "unknown_v999"
    with pytest.raises(ValueError, match="legacy energy declaration"):
        climate_energy_validation_mode(world)


@pytest.fixture(scope="module")
def native_reefs(reference):
    world = deepcopy(reference)
    # Keep every genuine climate input and solved budget unchanged. Add only
    # ecology descriptors, using the retained transport graph for adjacency;
    # the actual shallow marine cells provide warm, eligible reef candidates.
    for cell in world["cells"]:
        cell["neighbors"] = []
        cell["water_body_type"] = (
            "continental_shelf" if cell["is_water"] and cell["water_depth_m"] < 250.0
            else "ocean" if cell["is_water"] else "land"
        )
        cell["fishery_productivity_index"] = 1.0
        if not cell["is_water"]:
            cell.update(island_class="island", volcanic_potential_index=1.0, crust_age_ma=0.0)
    for edge in world["climate_energy_transport_edges"]:
        first, second = edge["first_cell_id"], edge["second_cell_id"]
        world["cells"][first]["neighbors"].append(second)
        world["cells"][second]["neighbors"].append(first)
    enrich_world_with_native_climate_energy(world)
    enrich_world_with_reef_diagnostics(world)
    assert world["reef_systems"], "fixture must exercise record-level omissions"
    return world


def reef_check(world):
    checks = []
    _validate_ecosystems(checks, world, world["cells"], {c["id"]: c for c in world["cells"]}, world["summary"])
    return next(check for check in checks if check["name"] == "reef_membership_sources_and_ranges")


def test_native_reef_consumer_accepts_all_three_declared_bleaching_omissions(native_reefs):
    assert validate_native_climate_energy_output(native_reefs)[0] == []
    assert all("reef_bleaching_risk_index" not in cell for cell in native_reefs["cells"])
    assert all("mean_reef_bleaching_risk_index" not in record for record in native_reefs["reef_systems"])
    assert "mean_reef_bleaching_risk_index" not in native_reefs["summary"]
    check = reef_check(native_reefs)
    assert check["passed"], check


@pytest.mark.parametrize("location", ["cell", "record", "summary"])
@pytest.mark.parametrize("value", [0.0, [], None])
def test_native_reef_consumer_rejects_forbidden_bleaching_fields_without_coercing(native_reefs, location, value):
    world = deepcopy(native_reefs)
    if location == "cell":
        world["cells"][0]["reef_bleaching_risk_index"] = value
    elif location == "record":
        world["reef_systems"][0]["mean_reef_bleaching_risk_index"] = value
    else:
        world["summary"]["mean_reef_bleaching_risk_index"] = value
    check = reef_check(world)
    assert not check["passed"]
    assert any("bleaching" in error for error in check["observed"]["errors"]), check


@pytest.mark.parametrize("location,field", [
    ("cell", "reef_wave_exposure_index"),
    ("record", "mean_reef_sediment_stress_index"),
    ("model", "bleaching_output_policy"),
])
def test_native_reef_omission_does_not_remove_other_requirements(native_reefs, location, field):
    world = deepcopy(native_reefs)
    target = world["cells"][0] if location == "cell" else world["reef_systems"][0] if location == "record" else world["reef_diagnostics_model"]
    del target[field]
    assert not reef_check(world)["passed"]


@pytest.mark.parametrize("location,field", [
    ("cell", "annual_emitted_longwave_w_m2"),
    ("summary", "area_weighted_mean_annual_emitted_longwave_w_m2"),
    ("model", "annual_weighting"),
])
def test_native_public_dispatch_also_checks_optional_annual_mirrors(world, location, field):
    enrich_world_with_native_climate_energy(world)
    if location == "cell":
        world["cells"][0][field] += 0.01
    elif location == "summary":
        world["summary"][field] += 0.01
    else:
        world["native_climate_energy_enrichment_model"][field] = "cell_count"
    errors, report = validate_native_climate_energy_output(world)
    assert report is None and errors
    assert not physics_check(world)["passed"]


@pytest.fixture(scope="module")
def scoped_geo_world(reference):
    # Provide the existing complete natural-record scaffold to exercise the
    # three top-level climate checks. Only the genuine climate certificate and
    # its linked fields are replaced; unrelated terrain/feedback checks should
    # fail, so this fixture is never asserted to be a valid combined world.
    world = deepcopy(cached_legacy_world_readonly("energy_128"))
    world["summary"] = {
        key: value for key, value in world["summary"].items()
        if key not in {
            "climate_energy_balance_record_count", "mean_top_of_atmosphere_insolation_w_m2",
            "mean_surface_albedo_index", "mean_absorbed_shortwave_w_m2", "mean_outgoing_longwave_w_m2",
            "mean_greenhouse_trapping_w_m2", "mean_net_radiative_balance_w_m2",
            "mean_abs_energy_balance_residual_c", "mean_climate_energy_stress_index",
            "mean_seasonal_insolation_range_w_m2", "mean_orbital_insolation_variability_index",
            "mean_peak_seasonal_insolation_w_m2", "mean_low_seasonal_insolation_w_m2",
            "mean_orbital_distance_factor", "high_climate_energy_stress_cell_count",
            "surface_albedo_regime_counts", "climate_energy_valid_area_cell_count",
            "climate_energy_represented_area_km2", "climate_energy_area_weighted_summary_available",
            *(f"area_weighted_mean_{field}" for field in (
                "top_of_atmosphere_insolation_w_m2", "absorbed_shortwave_w_m2",
                "outgoing_longwave_w_m2", "greenhouse_trapping_w_m2", "net_radiative_balance_w_m2",
            )),
        }
    }
    for cell, source in zip(world["cells"], reference["cells"]):
        for key in (
            "top_of_atmosphere_insolation_w_m2", "surface_albedo_index", "absorbed_shortwave_w_m2",
            "outgoing_longwave_w_m2", "greenhouse_trapping_w_m2", "net_radiative_balance_w_m2",
            "no_greenhouse_equilibrium_temperature_c", "radiative_equilibrium_temperature_c",
            "energy_balance_residual_c", "climate_energy_stress_index", "surface_albedo_regime",
            "seasonal_insolation_range_w_m2", "orbital_insolation_variability_index",
            "peak_seasonal_insolation_w_m2", "low_seasonal_insolation_w_m2",
        ):
            cell.pop(key, None)
        cell.update(deepcopy(source))
    world.update({key: deepcopy(value) for key, value in reference.items() if key != "cells"})
    enrich_world_with_native_climate_energy(world)
    return world


def test_geo_native_contracts_check_linkage_without_claiming_old_temperature_formula(scoped_geo_world):
    report = validate_geo_world(scoped_geo_world)
    checks = {check["name"]: check for check in report["checks"]}
    for key in ("current_climate_model", "native_solved_temperature_linkage", "climate_energy_record_coverage", "climate_energy_balance_replay"):
        assert checks[key]["passed"], checks[key]
    old_formula = checks["configured_global_temperature_response"]
    assert old_formula["status"] == "not_applicable" and not old_formula["passed"]
    assert not report["passed"], "unrelated old terrain/feedback is deliberately inconsistent"


@pytest.mark.parametrize("tamper", [
    lambda w: w["climate_energy_balance_records"].pop(),
    lambda w: w["climate_energy_balance_records"][0]["monthly_boundary_temperature_k"].pop(),
    lambda w: w["cells"][0]["temperature_monthly_c"].__setitem__(0, 999.0),
    lambda w: w["climate_model"].__setitem__("model_type", "prescribed_seasonal_surface_energy_v999"),
])
def test_geo_native_contracts_reject_partial_budget_and_temperature_tampering(scoped_geo_world, tamper):
    world = deepcopy(scoped_geo_world)
    tamper(world)
    report = validate_geo_world(world)
    checks = {check["name"]: check for check in report["checks"]}
    assert not report["passed"]
    for key in ("current_climate_model", "native_solved_temperature_linkage", "climate_energy_record_coverage", "climate_energy_balance_replay"):
        assert not checks[key]["passed"], checks[key]
