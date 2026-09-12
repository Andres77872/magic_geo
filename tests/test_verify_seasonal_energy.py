"""Analytic witnesses and adversarial mutations for the standalone research audit."""
from __future__ import annotations

import copy
import importlib.util
import json
import math
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/research/verify_seasonal_energy.py"
SPEC = importlib.util.spec_from_file_location("verify_seasonal_energy_research", SCRIPT)
assert SPEC and SPEC.loader
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


def equilibrium_witness(method="tr_bdf2", airless=False):
    """Two unequal-area columns at an analytic, nonuniform steady equilibrium.

    Choose temperatures and a graph first; infer constant zero-tilt latitudes
    from the resulting local radiation/transport budget. No climate producer or
    implicit thermal solver is used to make the fixture.
    """
    pressure = 0.0 if airless else 100000.0
    emissivity = 1.0 if airless else 1 / 1.75
    temperatures = [240.0, 230.0] if airless else [290.0, 280.0]
    areas = [1e12, 3e12]
    total_area = math.fsum(areas)
    gravity = 9.80665
    capacity_air = 1004.0 * pressure / gravity
    year = 360.0 * 86400.0
    conductance = 0.0 if airless else 1e12
    convergence = [-conductance * (temperatures[0] - temperatures[1]) / areas[0], conductance * (temperatures[0] - temperatures[1]) / areas[1]]
    maximum_asr = 1361.0 * 0.7 / math.pi
    records = []
    for i, temperature in enumerate(temperatures):
        olr = 5.670374419e-8 * emissivity * temperature**4
        absorbed = olr - convergence[i]
        latitude = math.acos(absorbed / maximum_asr)
        record = {
            "cell_id": i, "latitude_rad": latitude, "prescribed_marine_surface": i == 0,
            "prescribed_water_depth_m": 7.0 if i == 0 else 0.0,
            "interface_elevation_m": 0.0, "area_m2": areas[i],
            "surface_pressure_pa": pressure, "infrared_optical_depth": 0.0 if airless else 1.0,
            "surface_heat_capacity_j_m2_k": 4.1813e6 * 7.0 if i == 0 else 4e6,
            "atmospheric_heat_capacity_j_m2_k": capacity_air,
            "horizontal_conductivity_w_k": 2.2e6 * capacity_air,
            "effective_longwave_emissivity": emissivity,
            "top_of_atmosphere_albedo": 0.3,
            "monthly_boundary_temperature_k": [temperature] * 13,
            "monthly_mean_temperature_k": [temperature] * 12,
            "monthly_mean_fourth_power_temperature_k4": [temperature**4] * 12,
            "monthly_absorbed_shortwave_w_m2": [absorbed] * 12,
            "monthly_emitted_longwave_w_m2": [olr] * 12,
            "monthly_horizontal_heat_convergence_w_m2": [convergence[i]] * 12,
            "monthly_heat_storage_tendency_w_m2": [0.0] * 12,
            "monthly_balance_residual_w_m2": [math.fsum((-absorbed, olr, -convergence[i]))] * 12,
            "monthly_balance_tolerance_w_m2": [1e-7] * 12,
            "annual_net_heating_w_m2": math.fsum((absorbed, -olr, convergence[i])),
            "annual_flux_tolerance_w_m2": 1e-5 + 1e-7,
        }
        record["heat_capacity_j_m2_k"] = record["surface_heat_capacity_j_m2_k"] + capacity_air
        records.append(record)
    radius = math.sqrt(total_area / (4 * math.pi))
    model = {
        **audit.DECLARATIONS, **audit.CONSTANTS,
        "time_method": method,
        "accepted_step_quadrature": "accepted_endpoint" if method == "backward_euler" else "start_stage_endpoint_weights_1_over_2sqrt2_1_over_2sqrt2_1_minus_1_over_sqrt2",
        "tr_bdf2_gamma": 2 - math.sqrt(2),
        "mesh_backend": 0, "transport_model": "symmetric_voronoi_harmonic_interface_conductivity",
        "forcing_refinement_level": 0, "maximum_true_anomaly_step_rad": 2 * math.pi / 768,
        "maximum_interval_fraction_of_year": 1 / 360,
        "year_duration_seconds": year, "requested_year_duration_seconds": year,
        "monthly_duration_seconds": [year / 12] * 12,
        "radius_m": radius, "top_of_atmosphere_albedo": 0.3,
        "stellar_luminosity": 1.0, "orbital_eccentricity": 0.0, "axial_tilt_deg": 0.0,
        "mean_surface_pressure_pa": pressure, "gravity_m_s2": gravity,
        "hydrostatic_profile_temperature_k": 288.15, "reference_infrared_optical_depth": 1.0,
        "greenhouse_factor": 1.0, "atmospheric_diffusivity_m2_s": 2.2e6,
        "marine_mixed_layer_depth_m": 50.0,
        "total_area_m2": total_area,
        "atmospheric_scale_height_m": 287.05 * 288.15 / gravity,
        "area_weighted_mean_surface_pressure_pa": pressure,
        "mean_surface_pressure_residual_pa": 0.0,
        "total_atmospheric_mass_kg": pressure * total_area / gravity,
        "atmospheric_mass_residual_kg": 0.0,
        "atmospheric_scale_height_to_radius": 287.05 * 288.15 / gravity / radius,
        "maximum_interface_elevation_to_radius": 0.0,
        "requested_accuracy": {
            "maximum_numerical_error_fraction": 0.1,
            "required_monthly_refinement_confirmations": 0,
        },
        "accepted_periodic_options": {
            "time_method": method, "phase_tolerance_k": 1e-5,
            "annual_flux_tolerance_w_m2": 1e-5, "relative_tolerance": 0.0,
            "thermal_subdivisions": [2] * 360,
            "step": {"duration_policy": "parent_duration_divided_by_thermal_subdivisions"},
        },
        "achieved": {
            "accepted_steps_per_year": 720,
            "maximum_local_error_ratio": 0.0, "maximum_numerical_error_ratio": 0.0,
            "monthly_refinement_confirmations": 0,
            "maximum_phase_difference_k": 0.0,
            "maximum_annual_net_heating_w_m2": max(abs(r["annual_net_heating_w_m2"]) for r in records),
            "global_annual_net_heating_w": math.fsum(a * r["annual_net_heating_w_m2"] for a, r in zip(areas, records)),
        },
    }
    nodes = [{
        "id": i, "month_index": i // 30, "duration_fraction_of_year": 1 / 360,
        "duration_seconds": 86400.0, "declination_rad": 0.0,
        "inverse_square_distance_factor": 1.0, "thermal_subdivisions": 2,
    } for i in range(360)]
    edges = [] if airless else [{"first_cell_id": 0, "second_cell_id": 1, "conductance_w_k": conductance}]
    return {"climate_energy_model": model, "climate_energy_forcing_intervals": nodes,
            "climate_energy_transport_edges": edges, "climate_energy_balance_records": records}


@pytest.mark.parametrize("method", ["backward_euler", "tr_bdf2"])
@pytest.mark.parametrize("airless", [False, True])
def test_analytic_unequal_area_equilibrium_and_airless(method, airless):
    report = audit.verify(equilibrium_witness(method, airless))
    assert report["verified"] and report["cell_count"] == 2
    assert report["time_method"] == method
    assert report["algebraic_checks"] > 400
    assert "unexported_thermal_stage_trajectory" in report["unverified"]


@pytest.mark.parametrize("key,value", [
    ("model", "unknown"), ("budget_schema_version", True),
    ("budget_schema_version", 2), ("surface_energy_budget_resolved", 1),
    ("coefficient_source", "current_lake_depth"), ("time_method", "explicit_euler"),
    ("accepted_step_quadrature", "accepted_endpoint"),
    ("stefan_boltzmann_w_m2_k4", 5.0e-8), ("solar_constant_w_m2", True),
    ("forcing_refinement_level", 11), ("forcing_refinement_level", 0.0),
    ("mesh_backend", 2), ("monthly_duration_seconds", [1.0] * 11),
    ("mean_surface_pressure_pa", "100000"), ("gravity_m_s2", 0),
    ("orbital_eccentricity", 1.0), ("stellar_luminosity", -1.0), ("axial_tilt_deg", 91),
])
def test_reject_metadata_contract_mutations(key, value):
    witness = equilibrium_witness()
    witness["climate_energy_model"][key] = value
    with pytest.raises(audit.VerificationError):
        audit.verify(witness)


@pytest.mark.parametrize("key,value", [
    ("id", 1), ("month_index", 1), ("duration_seconds", 86401),
    ("duration_fraction_of_year", 1 / 12), ("declination_rad", 0.1),
    ("inverse_square_distance_factor", 1.01), ("thermal_subdivisions", 3),
    ("thermal_subdivisions", True),
])
def test_reject_changed_shared_source_or_partition(key, value):
    witness = equilibrium_witness()
    witness["climate_energy_forcing_intervals"][0][key] = value
    with pytest.raises(audit.VerificationError):
        audit.verify(witness)


@pytest.mark.parametrize("key", [
    "area_m2", "surface_heat_capacity_j_m2_k", "heat_capacity_j_m2_k",
    "atmospheric_heat_capacity_j_m2_k", "surface_pressure_pa", "infrared_optical_depth",
    "horizontal_conductivity_w_k", "effective_longwave_emissivity", "prescribed_water_depth_m",
])
def test_reject_physical_coefficient_mutations(key):
    witness = equilibrium_witness()
    witness["climate_energy_balance_records"][0][key] *= 1.01
    with pytest.raises(audit.VerificationError):
        audit.verify(witness)


@pytest.mark.parametrize("key", list(audit.MONTHLY[:-1]) + ["monthly_boundary_temperature_k"])
def test_reject_moment_budget_and_boundary_mutations(key):
    witness = equilibrium_witness()
    witness["climate_energy_balance_records"][0][key][0] += 0.01 if "fourth" not in key else 1e6
    with pytest.raises(audit.VerificationError):
        audit.verify(witness)


@pytest.mark.parametrize("key", list(audit.MONTHLY) + ["monthly_boundary_temperature_k"])
def test_reject_truncated_monthly_arrays(key):
    witness = equilibrium_witness()
    witness["climate_energy_balance_records"][0][key].pop()
    with pytest.raises(audit.VerificationError):
        audit.verify(witness)


def test_huge_declared_solver_tolerances_do_not_hide_residual_tamper():
    witness = equilibrium_witness()
    record = witness["climate_energy_balance_records"][0]
    record["monthly_balance_tolerance_w_m2"] = [1e6] * 12
    record["monthly_balance_residual_w_m2"][0] += 1e-4
    with pytest.raises(audit.VerificationError, match="monthly_balance_residual"):
        audit.verify(witness)


@pytest.mark.parametrize("mutation", ["conductance", "duplicate", "self", "missing_record", "reordered_record"])
def test_reject_graph_or_cell_coverage_mutations(mutation):
    witness = equilibrium_witness()
    edges = witness["climate_energy_transport_edges"]
    if mutation == "conductance":
        edges[0]["conductance_w_k"] *= 1.01
    elif mutation == "duplicate":
        edges.append(copy.deepcopy(edges[0]))
    elif mutation == "self":
        edges[0]["second_cell_id"] = 0
    elif mutation == "missing_record":
        witness["climate_energy_balance_records"].pop()
    else:
        witness["climate_energy_balance_records"].reverse()
    with pytest.raises(audit.VerificationError):
        audit.verify(witness)


@pytest.mark.parametrize("text", ['{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}', '{"x":1e999}', '[1,2]', '{"x":1.234,5}'])
def test_strict_json_rejects_ambiguous_or_nonfinite_input(tmp_path, text):
    path = tmp_path / "bad.json"
    path.write_text(text)
    with pytest.raises(ValueError):
        audit.strict_load(path)


def test_finite_json_roundtrip(tmp_path):
    path = tmp_path / "witness.json"
    path.write_text(json.dumps(equilibrium_witness(), allow_nan=False))
    assert audit.verify(audit.strict_load(path))["verified"]


@pytest.mark.parametrize("value", [None, True, "290", float("nan"), float("inf"), 10**500])
def test_reject_untyped_or_unrepresentable_physical_number(value):
    witness = equilibrium_witness()
    witness["climate_energy_balance_records"][0]["monthly_mean_temperature_k"][0] = value
    with pytest.raises(audit.VerificationError):
        audit.verify(witness)


def test_exact_dark_native_input_domain():
    witness = equilibrium_witness()
    model = witness["climate_energy_model"]
    model["stellar_luminosity"] = 0.0
    model["achieved"]["maximum_annual_net_heating_w_m2"] = 0.0
    model["achieved"]["global_annual_net_heating_w"] = 0.0
    for record in witness["climate_energy_balance_records"]:
        for key in audit.MONTHLY[:-1]:
            record[key] = [0.0] * 12
        record["monthly_boundary_temperature_k"] = [0.0] * 13
        record["annual_net_heating_w_m2"] = 0.0
    assert audit.verify(witness)["verified"]


def full_world_witness(precision=8):
    witness = equilibrium_witness()
    model = witness["climate_energy_model"]
    records = witness["climate_energy_balance_records"]
    mean = sum(r["area_m2"] * r["monthly_mean_temperature_k"][0] for r in records) / model["total_area_m2"] - 273.15
    witness["climate_model"] = {
        "model_type": "prescribed_seasonal_surface_energy_v1",
        "temperature_model": "periodic_graybody_storage_conservative_transport_v1",
        "temperature_interpretation": "prescribed_surface_column_temperature_used_as_near_surface_climate_proxy",
        "temperature_source": "climate_energy_balance_records_monthly_mean_temperature_k",
        "temperature_annual_mean": "accepted_month_duration_weighted_mean_kelvin_minus_273_15",
        "native_temperature_forcing_coupled": True, "imposed_mean_temperature": False,
        "post_solve_temperature_adjustments": False, "transient_climate_resolved": False,
        "periodic_seasonal_cycle_resolved": True, "prescribed_atmospheric_mass_conserved": True,
        "mass_conserving_atmospheric_circulation": False, "lake_ice_cloud_biome_feedback_resolved": False,
        "prescribed_surface_scope": "fresh_marine_and_exposed_land_before_flow_lake_and_cryosphere_diagnostics",
        "greenhouse_factor_interpretation": "reference_infrared_optical_depth_multiplier",
        "thermal_moisture_capacity_model": "bounded_exponential_solved_area_time_mean_temperature_v1",
        "thermal_moisture_capacity_scope": "empirical_global_monthly_precipitation_multiplier",
        "display_temperature_decimal_places": precision, "configured_month_count": 12,
        "solved_area_time_mean_temperature_c": mean, "reference_infrared_optical_depth": 1.0,
        "thermal_moisture_capacity_reference_temperature_c": 15.0,
        "thermal_moisture_capacity_temperature_response_per_c": 0.04,
        "thermal_moisture_capacity_min_factor": 0.35, "thermal_moisture_capacity_max_factor": 2.25,
        "thermal_moisture_capacity_factor": math.exp(0.04 * (mean - 15.0)),
    }
    witness["planet_parameters"] = {
        "radius_km": model["radius_m"] / 1000, "gravity_g": 1.0,
        "atmosphere_pressure_bar": 1.0, "axial_tilt_deg": 0.0,
        "orbital_eccentricity": 0.0, "stellar_luminosity": 1.0, "greenhouse_factor": 1.0,
    }
    witness["cells"] = []
    for i, record in enumerate(records):
        latitude = record["latitude_rad"]
        temperature = record["monthly_mean_temperature_k"][0] - 273.15
        witness["cells"].append({
            "id": i, "position_3d": [math.cos(latitude), 0.0, math.sin(latitude)],
            "area_km2": record["area_m2"] / 1e6, "lat_deg": math.degrees(latitude),
            "temperature_c": round(temperature, precision),
            "temperature_monthly_c": [round(temperature, precision)] * 12,
            "is_water": i == 0, "is_lake": i == 1,
            # Cell1 became a standing lake after the thermal snapshot.
            "water_depth_m": 7.0 if i == 0 else 120.0,
            "elevation_m": -7.0 if i == 0 else 0.0,
        })
    return witness


@pytest.mark.parametrize("precision", [0, 3, 8])
def test_full_world_rounding_and_later_lake_preserves_retained_slab(precision):
    witness = full_world_witness(precision)
    report = audit.verify(witness)
    assert report["full_world_display_fields_linked"] is True
    assert "full_world_display_field_linkage" not in report["unverified"]
    assert witness["cells"][1]["is_lake"] and not witness["climate_energy_balance_records"][1]["prescribed_marine_surface"]


@pytest.mark.parametrize("key,value", [
    ("id", 1), ("area_km2", 1.0), ("position_3d", [0.0, 0.0, 1.0]),
    ("lat_deg", 0.0), ("temperature_c", 30.0), ("temperature_monthly_c", [20.0] * 12),
    ("is_water", False), ("water_depth_m", 8.0), ("elevation_m", -8.0),
])
def test_reject_cell_linkage_mutations(key, value):
    witness = full_world_witness()
    witness["cells"][0][key] = value
    with pytest.raises(audit.VerificationError):
        audit.verify(witness)


@pytest.mark.parametrize("key,value", [
    ("temperature_source", "legacy_energy_diagnostic"), ("post_solve_temperature_adjustments", True),
    ("solved_area_time_mean_temperature_c", 15.0), ("thermal_moisture_capacity_factor", 1.0),
    ("thermal_moisture_capacity_reference_temperature_c", 10.0),
    ("reference_infrared_optical_depth", 0.0), ("display_temperature_decimal_places", True),
])
def test_reject_climate_model_linkage_mutations(key, value):
    witness = full_world_witness()
    witness["climate_model"][key] = value
    with pytest.raises(audit.VerificationError):
        audit.verify(witness)


@pytest.mark.parametrize("key", ["radius_km", "gravity_g", "atmosphere_pressure_bar", "axial_tilt_deg", "orbital_eccentricity", "stellar_luminosity", "greenhouse_factor"])
def test_reject_planet_control_linkage_mutations(key):
    witness = full_world_witness()
    witness["planet_parameters"][key] += 0.01
    with pytest.raises(audit.VerificationError):
        audit.verify(witness)


@pytest.mark.parametrize("local,numerical", [(99.0, 0.0), (0.2, 0.2), (0.0, 0.01), (-0.01, 0.0), (True, 0.0)])
def test_declared_adaptive_gates_must_pass(local, numerical):
    witness = equilibrium_witness()
    achieved = witness["climate_energy_model"]["achieved"]
    achieved["maximum_local_error_ratio"] = local
    achieved["maximum_numerical_error_ratio"] = numerical
    with pytest.raises(audit.VerificationError):
        audit.verify(witness)


def test_numerical_error_fraction_accepts_native_inclusive_upper_bound():
    witness = equilibrium_witness()
    model = witness["climate_energy_model"]
    model["requested_accuracy"]["maximum_numerical_error_fraction"] = 1.0
    model["achieved"]["maximum_local_error_ratio"] = 1.0
    model["achieved"]["maximum_numerical_error_ratio"] = 1.0
    assert audit.verify(witness)["verified"]


@pytest.mark.parametrize("fraction", [math.nextafter(1.0, math.inf), 1.01])
def test_numerical_error_fraction_rejects_values_above_native_upper_bound(fraction):
    witness = equilibrium_witness()
    witness["climate_energy_model"]["requested_accuracy"]["maximum_numerical_error_fraction"] = fraction
    with pytest.raises(audit.VerificationError, match="maximum_numerical_error_fraction: must be at most one"):
        audit.verify(witness)


def test_declared_monthly_confirmations_cannot_be_missing():
    witness = equilibrium_witness()
    witness["climate_energy_model"]["requested_accuracy"]["required_monthly_refinement_confirmations"] = 2
    with pytest.raises(audit.VerificationError, match="insufficient confirmations"):
        audit.verify(witness)


def test_scientific_claims_exclude_unexported_stage_and_orbital_provenance():
    report = audit.verify(equilibrium_witness())
    assert "orbital_node_generation_from_parameters" in report["unverified"]
    assert "adaptive_error_estimates_and_refinement_history" in report["unverified"]


@pytest.mark.parametrize("parent", [float("inf"), float("-inf"), float("nan")])
def test_nonfinite_derived_parent_cannot_create_unbounded_allowance(parent):
    with pytest.raises(audit.VerificationError, match="parent magnitude is not representable"):
        audit.Audit().close(0.0, 1.0, "probe", parents=(parent,))


def test_finite_operand_storage_scale_overflow_cannot_hide_mismatch():
    capacity, temperature, duration = 1e308, 300.0, 1e6
    assert all(math.isfinite(value) for value in (capacity, temperature, duration))
    # A zero endpoint change can produce finite storage, while the independent
    # parent expression overflows before division. Reject that audit rather
    # than silently giving it an infinite cancellation allowance.
    storage = capacity * (temperature - temperature) / duration
    parent = capacity * temperature / duration
    assert storage == 0.0 and math.isinf(parent)
    with pytest.raises(audit.VerificationError, match="parent magnitude is not representable"):
        audit.Audit().close(storage, 1.0, "storage", parents=(parent,))


def test_finite_operand_transport_scale_overflow_cannot_hide_mismatch():
    conductance, area, temperature = 1e308, 1.0, 300.0
    assert all(math.isfinite(value) for value in (conductance, area, temperature))
    exchange = conductance * (temperature - temperature) / area
    parent = conductance / area * (temperature + temperature)
    assert exchange == 0.0 and math.isinf(parent)
    with pytest.raises(audit.VerificationError, match="parent magnitude is not representable"):
        audit.Audit().close(exchange, 1.0, "transport", parents=(parent,))


def test_finite_inputs_with_overflowing_comparison_error_fail_explicitly():
    with pytest.raises(audit.VerificationError, match="comparison error or allowance is not representable"):
        audit.Audit().close(1e308, -1e308, "probe")


def test_finite_roundoff_allowance_is_unchanged():
    checker = audit.Audit()
    checker.close(1.0 + 128 * math.ulp(1.0), 1.0, "allowed", parents=(1.0,))
    with pytest.raises(audit.VerificationError, match="roundoff allowance"):
        checker.close(1.0 + 129 * math.ulp(1.0), 1.0, "rejected", parents=(1.0,))
