"""Independent production validation of genuine native certificate fixtures."""
from __future__ import annotations

from copy import deepcopy
import gzip
import hashlib
import json
import math
from pathlib import Path

import pytest

from magic_geo.native_climate_energy_validation import (
    Audit, NativeClimateEnergyValidationError, audit_native_climate_energy,
    validate_native_climate_energy,
)
from support.native_climate_energy import native_climate_certificate, native_climate_world


@pytest.fixture(scope="module")
def reference():
    return native_climate_world()


@pytest.fixture
def world(reference):
    return deepcopy(reference)


def rejected(world, text=""):
    errors = validate_native_climate_energy(world)
    assert len(errors) == 1 and len(errors[0]) <= 523, errors
    assert errors[0].startswith("native climate energy: "), errors
    assert text in errors[0], errors
    with pytest.raises(NativeClimateEnergyValidationError):
        audit_native_climate_energy(world)


def test_genuine_native_full_world_and_unchanged_certificate(world):
    before = deepcopy(world)
    report = audit_native_climate_energy(world)
    assert report["verified"] and report["full_world_display_fields_linked"]
    assert report["cell_count"] == 128 and report["algebraic_checks"] == 12036
    assert report["maximum_replay_errors"]["monthly_horizontal_heat_convergence_w_m2"] < 2e-12
    assert validate_native_climate_energy(world) == []
    assert world == before
    lakes = [i for i, cell in enumerate(world["cells"]) if cell["is_lake"]]
    assert len(lakes) == 2
    assert all(not world["climate_energy_balance_records"][i]["prescribed_marine_surface"] for i in lakes)


@pytest.mark.parametrize("method", ["backward_euler", "tr_bdf2"])
def test_genuine_standalone_certificates_require_explicit_limited_scope(method):
    certificate = native_climate_certificate(method)
    rejected(certificate, "full cell linkage")
    report = audit_native_climate_energy(certificate, require_cell_linkage=False)
    assert report["time_method"] == method and report["algebraic_checks"] == 1948
    assert not report["full_world_display_fields_linked"]
    assert "full_world_display_field_linkage" in report["unverified"]


def test_declared_scope_does_not_claim_unseen_stage_or_orbital_reconstruction(world):
    report = audit_native_climate_energy(world)
    assert set(report["unverified"]) == {
        "orbital_node_generation_from_parameters", "astronomical_quadrature_accuracy",
        "unexported_thermal_stage_trajectory", "adaptive_error_estimates_and_refinement_history",
        "geometric_edge_reconstruction",
    }


@pytest.mark.parametrize("value", [None, [], {}, "legacy", 1, True])
def test_direct_production_entry_does_not_silently_accept_unknown_root(value):
    rejected(value)


@pytest.mark.parametrize("field", ["cells", "climate_model", "planet_parameters", "climate_energy_model",
                                    "climate_energy_forcing_intervals", "climate_energy_transport_edges",
                                    "climate_energy_balance_records"])
def test_full_production_linkage_requires_all_sources(world, field):
    del world[field]
    rejected(world, field)


@pytest.mark.parametrize("path", [
    ("climate_energy_model",), ("climate_model",),
    ("climate_energy_model", "accepted_periodic_options"),
    ("climate_energy_model", "accepted_periodic_options", "step"),
    ("climate_energy_model", "requested_accuracy"),
    ("climate_energy_model", "requested_accuracy", "periodic"),
    ("climate_energy_model", "achieved"),
    ("climate_energy_forcing_intervals", 0), ("climate_energy_transport_edges", 0),
    ("climate_energy_balance_records", 0),
])
@pytest.mark.parametrize("mutation", ["extra", "missing", "shape"])
def test_versioned_native_objects_have_exact_schemas(world, path, mutation):
    parent = world
    for key in path[:-1]:
        parent = parent[key]
    obj = parent[path[-1]]
    if mutation == "extra":
        obj["unrecognized"] = 0
    elif mutation == "missing":
        del obj[next(iter(obj))]
    else:
        parent[path[-1]] = []
    rejected(world)


@pytest.mark.parametrize("key,value", [
    ("model", "unknown"), ("budget_schema_version", True), ("budget_schema_version", 2),
    ("precision", "display_precision"), ("native_temperature_forcing_coupled", 1),
    ("stefan_boltzmann_w_m2_k4", 5e-8), ("time_method", {}),
    ("accepted_step_quadrature", "accepted_endpoint"), ("forcing_refinement_level", 11),
    ("forcing_refinement_level", 0.0), ("axial_tilt_deg", 91), ("stellar_luminosity", -1),
    ("maximum_stored_forcing_values", 10), ("mean_surface_pressure_pa", "1"),
    ("gravity_m_s2", 0.0), ("orbital_eccentricity", 1.0),
])
def test_unsupported_metadata_and_input_domains_rejected(world, key, value):
    world["climate_energy_model"][key] = value
    rejected(world)


@pytest.mark.parametrize("key,value", [
    ("maximum_local_error_ratio", 2.0), ("maximum_numerical_error_ratio", 0.5),
    ("monthly_refinement_confirmations", 0), ("completed_physical_solves", 0),
    ("accepted_steps_per_year", True), ("last_physical_solve_warm_started", 0),
    ("total_step_attempts", 10), ("final_partition_year_evaluations", 0),
])
def test_declared_achievements_must_be_internally_valid(world, key, value):
    world["climate_energy_model"]["achieved"][key] = value
    rejected(world, "achieved")


def test_native_numerical_error_fraction_endpoint_one_is_accepted(world):
    world["climate_energy_model"]["requested_accuracy"]["maximum_numerical_error_fraction"] = 1.0
    assert validate_native_climate_energy(world) == []


@pytest.mark.parametrize("value", [0, True, 2**31])
def test_native_signed_solver_limit_schema_is_preserved(world, value):
    world["climate_energy_model"]["accepted_periodic_options"]["step"]["maximum_newton_iterations"] = value
    rejected(world, "maximum_newton_iterations")


@pytest.mark.parametrize("value", [None, [], {}, "300", True, float("nan"), float("inf"), 10**500])
def test_malformed_numerical_cell_record_is_bounded_failure(world, value):
    world["climate_energy_balance_records"][0]["monthly_mean_temperature_k"][0] = value
    rejected(world, "monthly_mean_temperature_k")


@pytest.mark.parametrize("key", [
    "surface_pressure_pa", "infrared_optical_depth", "surface_heat_capacity_j_m2_k",
    "atmospheric_heat_capacity_j_m2_k", "heat_capacity_j_m2_k", "horizontal_conductivity_w_k",
    "effective_longwave_emissivity", "area_m2",
])
def test_independent_column_reconstruction_rejects_changed_coefficients(world, key):
    world["climate_energy_balance_records"][0][key] *= 1.01
    rejected(world)


@pytest.mark.parametrize("key", [
    "monthly_mean_temperature_k", "monthly_mean_fourth_power_temperature_k4",
    "monthly_absorbed_shortwave_w_m2", "monthly_emitted_longwave_w_m2",
    "monthly_horizontal_heat_convergence_w_m2", "monthly_heat_storage_tendency_w_m2",
    "monthly_balance_residual_w_m2", "monthly_boundary_temperature_k",
])
def test_independent_monthly_identities_reject_changed_ledger(world, key):
    world["climate_energy_balance_records"][0][key][0] += 1e6 if "fourth" in key else 0.01
    rejected(world)


@pytest.mark.parametrize("key", ["monthly_mean_temperature_k", "monthly_balance_tolerance_w_m2", "monthly_boundary_temperature_k"])
def test_monthly_and_boundary_coverage_is_exact(world, key):
    world["climate_energy_balance_records"][0][key].pop()
    rejected(world, key)


@pytest.mark.parametrize("key,value", [
    ("id", 1), ("month_index", 1), ("duration_seconds", 1.0),
    ("duration_fraction_of_year", 1.0), ("declination_rad", 0.0),
    ("inverse_square_distance_factor", 2.0), ("thermal_subdivisions", 3),
])
def test_source_node_and_partition_mutations_are_rejected(world, key, value):
    world["climate_energy_forcing_intervals"][0][key] = value
    rejected(world)


@pytest.mark.parametrize("mutation", ["conductance", "duplicate", "self", "missing_record", "reordered_records"])
def test_graph_and_cell_certificate_coverage_is_independent(world, mutation):
    edges = world["climate_energy_transport_edges"]
    if mutation == "conductance":
        edges[0]["conductance_w_k"] *= 1.1
    elif mutation == "duplicate":
        edges.append(deepcopy(edges[0]))
    elif mutation == "self":
        edges[0]["second_cell_id"] = edges[0]["first_cell_id"]
    elif mutation == "missing_record":
        world["climate_energy_balance_records"].pop()
    else:
        world["climate_energy_balance_records"].reverse()
    rejected(world)


def test_inflated_solver_tolerance_cannot_hide_resolvable_residual_tamper(world):
    record = world["climate_energy_balance_records"][0]
    record["monthly_balance_tolerance_w_m2"] = [1e6] * 12
    record["monthly_balance_residual_w_m2"][0] += 1e-4
    rejected(world, "monthly_balance_residual_w_m2")


@pytest.mark.parametrize("parent", [float("inf"), float("nan"), 1e308 * 300.0])
def test_nonfinite_derived_parent_never_creates_infinite_algebraic_allowance(parent):
    with pytest.raises(NativeClimateEnergyValidationError, match="parent magnitude"):
        Audit().close(0.0, 1.0, "finite_net_overflowed_parent", parents=(parent,))


@pytest.mark.parametrize("key,value", [
    ("id", 1), ("position_3d", [0, 0, 1]), ("area_km2", 1.0),
    ("temperature_c", 300.0), ("temperature_monthly_c", [20.0] * 12),
    ("lat_deg", 0.0), ("is_water", 0),
])
def test_final_cell_linkage_cannot_be_changed(world, key, value):
    world["cells"][0][key] = value
    rejected(world)


@pytest.mark.parametrize("key,value", [
    ("temperature_source", "legacy"), ("post_solve_temperature_adjustments", True),
    ("thermal_moisture_capacity_factor", 1.0), ("solved_area_time_mean_temperature_c", 15.0),
    ("precipitation_model", "solved_circulation"), ("precipitation_scale", {}),
    ("seasonal_monsoon_precipitation_strength", 2.0),
])
def test_climate_model_source_precision_and_empirical_scope_are_strict(world, key, value):
    world["climate_model"][key] = value
    rejected(world, "climate_model")


@pytest.mark.parametrize("key", ["radius_km", "gravity_g", "atmosphere_pressure_bar", "axial_tilt_deg",
                                 "orbital_eccentricity", "stellar_luminosity", "greenhouse_factor"])
def test_planet_controls_must_match_retained_certificate(world, key):
    world["planet_parameters"][key] += 0.01
    rejected(world, "planet_parameters")


def test_extra_python_fields_do_not_modify_or_invalidate_native_certificate(world):
    world["native_climate_energy_enrichment_model"] = {"model": "separate_additive_metadata"}
    world["cells"][0]["annual_absorbed_shortwave_w_m2"] = 123.0
    world["summary"] = {"unrelated": 12}
    assert validate_native_climate_energy(world) == []


def test_fixture_content_and_reproducible_gzip_manifests():
    folder = Path(__file__).parent / "fixtures/native_climate_energy"
    for filename in ("world_128.json.gz", "certificate_12_backward_euler.json.gz", "certificate_12_tr_bdf2.json.gz"):
        compressed = (folder / filename).read_bytes()
        manifest = json.loads((folder / (filename + ".manifest.json")).read_text())
        assert compressed[4:8] == b"\0\0\0\0"
        assert hashlib.sha256(compressed).hexdigest() == manifest["gzip_sha256"]
        assert hashlib.sha256(gzip.decompress(compressed)).hexdigest() == manifest["retained_json_sha256"]
        assert manifest["physical_values_recomputed"] is False
