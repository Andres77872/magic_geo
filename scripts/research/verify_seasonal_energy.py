#!/usr/bin/env python3
"""Independent monthly ledger audit for native_prescribed_seasonal_energy_v1.

Uses only Python's standard library, never native/Python climate producer helpers.
Reconstructs physical columns and incident sunlight from the *published* orbital
nodes, and checks moment, graph, storage and annual identities. This is not a
re-integration of unexported thermal stages or an accuracy certificate for the
astronomical quadrature. Published solver tolerances govern convergence only;
they cannot relax the independent algebraic comparisons below.

Numerical comparisons allow 128 binary64 ulps of the relevant parent magnitude
(256 for a summed graph flux). Cancellation-prone residuals use their parent
flux scale, never a relative tolerance on the small residual. Hydrostatic sums
use 60-digit Decimal arithmetic as an independent reference.
"""
from __future__ import annotations

import argparse
from decimal import Decimal, localcontext
import json
import math
from pathlib import Path
from typing import Any


MODEL = "native_prescribed_seasonal_energy_v1"
DECLARATIONS = {
    "model": MODEL,
    "budget_schema_version": 1,
    "ownership": "native_temperature_producer",
    "equation": "C_dT_dt_equals_absorbed_shortwave_minus_effective_longwave_plus_horizontal_heat_convergence",
    "residual_sign": "storage_minus_absorbed_shortwave_plus_longwave_minus_horizontal_convergence",
    "coefficient_model": "prescribed_hydrostatic_gray_marine_land_columns_v1",
    "coefficient_source": "fresh_marine_and_exposed_land_before_flow_lake_and_cryosphere_diagnostics",
    "native_temperature_forcing_coupled": True,
    "surface_energy_budget_resolved": True,
    "coupled_atmosphere_ocean_energy_resolved": False,
    "lake_ice_cloud_biome_feedback_resolved": False,
    "terrain_iterations_are_elapsed_climate_years": False,
    "temperature_interpretation": "prescribed_surface_column_temperature_used_as_near_surface_climate_proxy",
    "precision": "roundtrip_binary64_independent_of_output_float_precision",
    "monthly_error_interpretation": "observed_reconverged_refinement_change_not_absolute_error_certificate",
    "astronomical_refinement_independently_verified_for_this_world": False,
    "calendar": "twelve_equal_elapsed_time_months_periapsis_at_month_zero_center",
    "solar_quadrature": "kepler_true_anomaly_midpoints_time_and_angle_bounded_v2",
    "pressure_formula": "area_mean_normalized_p_mean_exp_minus_interface_elevation_over_scale_height",
    "opacity_formula": "tau_ref_times_greenhouse_times_pressure_over_reference_times_reference_gravity_over_gravity",
    "longwave_formula": "sigma_times_temperature_fourth_moment_divided_by_one_plus_three_tau_over_four",
}
CONSTANTS = {
    "solar_constant_w_m2": 1361.0,
    "solar_longitude_at_periapsis_deg": -75.0,
    "stefan_boltzmann_w_m2_k4": 5.670374419e-8,
    "dry_air_gas_constant_j_kg_k": 287.05,
    "dry_air_heat_capacity_j_kg_k": 1004.0,
    "reference_pressure_pa": 100000.0,
    "reference_gravity_m_s2": 9.80665,
    "land_surface_heat_capacity_j_m2_k": 4.0e6,
    "water_volumetric_heat_capacity_j_m3_k": 4.1813e6,
}
MONTHLY = (
    "monthly_mean_temperature_k", "monthly_mean_fourth_power_temperature_k4",
    "monthly_absorbed_shortwave_w_m2", "monthly_emitted_longwave_w_m2",
    "monthly_horizontal_heat_convergence_w_m2", "monthly_heat_storage_tendency_w_m2",
    "monthly_balance_residual_w_m2", "monthly_balance_tolerance_w_m2",
)


class VerificationError(ValueError):
    """A malformed or inconsistent serialized climate witness."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def number(value: Any, path: str, *, positive: bool = False, nonnegative: bool = False) -> float:
    require(type(value) in (int, float), f"{path}: expected a number, without coercion")
    try:
        result = float(value)
    except OverflowError as error:
        raise VerificationError(f"{path}: number exceeds binary64") from error
    require(math.isfinite(result), f"{path}: nonfinite number")
    require(not positive or result > 0.0, f"{path}: expected positive number")
    require(not nonnegative or result >= 0.0, f"{path}: expected nonnegative number")
    return result


def integer(value: Any, path: str, minimum: int = 0) -> int:
    require(type(value) is int and value >= minimum, f"{path}: expected integer >= {minimum}")
    return value


def array(value: Any, size: int, path: str, *, nonnegative: bool = False) -> list[float]:
    require(type(value) is list and len(value) == size, f"{path}: expected {size} values")
    return [number(v, f"{path}[{i}]", nonnegative=nonnegative) for i, v in enumerate(value)]


def finite_tree(value: Any, path: str = "root") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            finite_tree(item, f"{path}.{key}")
    elif isinstance(value, list):
        for i, item in enumerate(value):
            finite_tree(item, f"{path}[{i}]")
    elif isinstance(value, float):
        require(math.isfinite(value), f"{path}: nonfinite JSON number")


def strict_load(path: Path) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            require(key not in result, f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def invalid_constant(token: str) -> None:
        raise VerificationError(f"nonfinite JSON constant: {token}")

    result = json.loads(path.read_text(), object_pairs_hook=pairs, parse_constant=invalid_constant)
    require(type(result) is dict, "root: expected JSON object")
    finite_tree(result)
    return result


class Audit:
    def __init__(self) -> None:
        self.checks = 0
        self.maximum_errors: dict[str, float] = {}

    def close(self, actual: Any, expected: float, path: str, *, parents: tuple[float, ...] = (), ulps: int = 128) -> None:
        actual = number(actual, path)
        require(math.isfinite(expected), f"{path}: independent reference is not representable")
        require(all(math.isfinite(value) for value in parents), f"{path}: independent parent magnitude is not representable")
        scale = max(abs(actual), abs(expected), *(abs(v) for v in parents))
        require(math.isfinite(scale), f"{path}: independent comparison scale is not representable")
        tolerance = ulps * math.ulp(scale)
        error = abs(actual - expected)
        require(math.isfinite(tolerance) and math.isfinite(error), f"{path}: independent comparison error or allowance is not representable")
        require(error <= tolerance, f"{path}: {actual!r} differs from {expected!r} by {error:.9g} (roundoff allowance {tolerance:.9g})")
        self.checks += 1
        category = path.split(".")[-1].split("[")[0]
        self.maximum_errors[category] = max(error, self.maximum_errors.get(category, 0.0))


def incident(latitude: float, declination: float, irradiance: float) -> float:
    """Daily integral of max(0, sin(phi)sin(delta)+cos(phi)cos(delta)cos(h))."""
    offset = math.sin(latitude) * math.sin(declination)
    amplitude = max(0.0, math.cos(latitude) * math.cos(declination))
    if offset >= amplitude:
        return irradiance * max(offset, 0.0)
    if offset <= -amplitude:
        return 0.0
    sunset = math.acos(-offset / amplitude)
    return irradiance / math.pi * (sunset * offset + amplitude * math.sin(sunset))


def verify_world_linkage(payload: dict[str, Any], audit: Audit, model: dict[str, Any],
                         records: list[dict[str, Any]], durations: list[float], year: float) -> None:
    """Link a full world to its retained snapshot without reclassifying lakes."""
    cells = payload["cells"]
    require(type(cells) is list and len(cells) == len(records), "cells: retained record coverage mismatch")
    climate = payload["climate_model"]
    declarations = {
        "model_type": "prescribed_seasonal_surface_energy_v1",
        "temperature_model": "periodic_graybody_storage_conservative_transport_v1",
        "temperature_interpretation": DECLARATIONS["temperature_interpretation"],
        "temperature_source": "climate_energy_balance_records_monthly_mean_temperature_k",
        "temperature_annual_mean": "accepted_month_duration_weighted_mean_kelvin_minus_273_15",
        "native_temperature_forcing_coupled": True,
        "imposed_mean_temperature": False, "post_solve_temperature_adjustments": False,
        "transient_climate_resolved": False, "periodic_seasonal_cycle_resolved": True,
        "prescribed_atmospheric_mass_conserved": True,
        "mass_conserving_atmospheric_circulation": False,
        "lake_ice_cloud_biome_feedback_resolved": False,
        "prescribed_surface_scope": DECLARATIONS["coefficient_source"],
        "greenhouse_factor_interpretation": "reference_infrared_optical_depth_multiplier",
        "thermal_moisture_capacity_model": "bounded_exponential_solved_area_time_mean_temperature_v1",
        "thermal_moisture_capacity_scope": "empirical_global_monthly_precipitation_multiplier",
    }
    require(type(climate) is dict, "climate_model: expected object")
    for key, expected in declarations.items():
        require(type(climate.get(key)) is type(expected) and climate[key] == expected, f"climate_model.{key}: unsupported declaration")
    precision = integer(climate["display_temperature_decimal_places"], "display_temperature_decimal_places")
    require(precision <= 8, "display_temperature_decimal_places: outside native [0,8]")
    require(integer(climate["configured_month_count"], "configured_month_count") == 12, "configured_month_count: expected twelve")

    def rounded(actual: Any, expected: float, path: str, decimals: int) -> None:
        value = number(actual, path)
        allowance = 0.5 * 10.0**-decimals + 64 * math.ulp(max(abs(value), abs(expected), 273.15))
        require(abs(value - expected) <= allowance, f"{path}: does not match retained value at declared display precision")
        audit.checks += 1

    with localcontext() as context:
        context.prec = 60
        d = Decimal.from_float
        annual_kelvin = [sum(d(t) * d(dt) for t, dt in zip(r[MONTHLY[0]], durations)) / d(year) for r in records]
        mean_kelvin = sum(d(r["area_m2"]) * t for r, t in zip(records, annual_kelvin)) / sum(d(r["area_m2"]) for r in records)
        global_celsius = float(mean_kelvin - Decimal("273.15"))
        for i, (cell, record) in enumerate(zip(cells, records)):
            path = f"cell[{i}]"
            require(integer(cell["id"], path + ".id") == i, "cells: noncanonical ID coverage")
            audit.close(record["area_m2"], number(cell["area_km2"], path + ".area_km2", positive=True) * 1e6, path + ".area_m2")
            position = array(cell["position_3d"], 3, path + ".position_3d")
            require(abs(math.hypot(*position) - 1.0) <= 1e-12, path + ": position is not unit spherical geometry")
            geometric_latitude = math.atan2(position[2], math.hypot(position[0], position[1]))
            require(abs(geometric_latitude - record["latitude_rad"]) <= 1e-9, path + ": latitude differs from retained geometry")
            rounded(cell["lat_deg"], math.degrees(record["latitude_rad"]), path + ".lat_deg", 17)
            monthly = array(cell["temperature_monthly_c"], 12, path + ".temperature_monthly_c")
            for month, temperature in enumerate(monthly):
                rounded(temperature, record[MONTHLY[0]][month] - 273.15, path + f".temperature_monthly_c[{month}]", precision)
            rounded(cell["temperature_c"], float(annual_kelvin[i] - Decimal("273.15")), path + ".temperature_c", precision)
            # The captured surface must stay separate from later hydrologic
            # lake flags/depth. Existing marine cells retain their sea datum;
            # dry-at-solve cells are allowed to become standing lakes later.
            if record["prescribed_marine_surface"]:
                require(cell["is_water"] is True, path + ": retained marine cell lost marine classification")
                rounded(cell["water_depth_m"], record["prescribed_water_depth_m"], path + ".water_depth_m", 10)
                rounded(cell["elevation_m"], -record["prescribed_water_depth_m"], path + ".elevation_m", 10)
    audit.close(climate["solved_area_time_mean_temperature_c"], global_celsius, "climate_model.solved_area_time_mean_temperature_c", parents=(float(mean_kelvin),))
    for key, expected in {
        "thermal_moisture_capacity_reference_temperature_c": 15.0,
        "thermal_moisture_capacity_temperature_response_per_c": 0.04,
        "thermal_moisture_capacity_min_factor": 0.35,
        "thermal_moisture_capacity_max_factor": 2.25,
    }.items():
        require(number(climate[key], f"climate_model.{key}") == expected, f"climate_model.{key}: unsupported constant")
    anomaly = 0.04 * (global_celsius - 15.0)
    moisture = 0.35 if anomaly <= math.log(0.35) else 2.25 if anomaly >= math.log(2.25) else math.exp(anomaly)
    audit.close(climate["thermal_moisture_capacity_factor"], moisture, "climate_model.thermal_moisture_capacity_factor")
    audit.close(climate["reference_infrared_optical_depth"], model["reference_infrared_optical_depth"], "climate_model.reference_infrared_optical_depth")
    planet = payload["planet_parameters"]
    for source, target, multiplier in (
        ("radius_km", "radius_m", 1000.0), ("gravity_g", "gravity_m_s2", 9.80665),
        ("atmosphere_pressure_bar", "mean_surface_pressure_pa", 100000.0),
        ("axial_tilt_deg", "axial_tilt_deg", 1.0), ("orbital_eccentricity", "orbital_eccentricity", 1.0),
        ("stellar_luminosity", "stellar_luminosity", 1.0), ("greenhouse_factor", "greenhouse_factor", 1.0),
    ):
        audit.close(model[target], number(planet[source], "planet_parameters." + source) * multiplier, "planet_parameters." + source)


def verify(payload: dict[str, Any]) -> dict[str, Any]:
    """Raise VerificationError on the first failed check; return compact evidence."""
    try:
        return _verify(payload)
    except (KeyError, TypeError, IndexError, OverflowError, ArithmeticError) as error:
        if isinstance(error, VerificationError):
            raise
        raise VerificationError(f"malformed or unrepresentable climate witness: {error}") from error


def _verify(payload: dict[str, Any]) -> dict[str, Any]:
    finite_tree(payload)
    audit = Audit()
    model = payload["climate_energy_model"]
    require(type(model) is dict, "climate_energy_model: expected object")
    for key, expected in DECLARATIONS.items():
        require(type(model.get(key)) is type(expected) and model[key] == expected, f"model.{key}: unsupported declaration")
    for key, expected in CONSTANTS.items():
        require(number(model[key], f"model.{key}") == expected, f"model.{key}: unsupported constant")
    method = model["time_method"]
    require(method in ("backward_euler", "tr_bdf2"), "model.time_method: unsupported method")
    quadrature = "accepted_endpoint" if method == "backward_euler" else "start_stage_endpoint_weights_1_over_2sqrt2_1_over_2sqrt2_1_minus_1_over_sqrt2"
    require(model["accepted_step_quadrature"] == quadrature, "model.accepted_step_quadrature: method mismatch")
    audit.close(model["tr_bdf2_gamma"], 2.0 - math.sqrt(2.0), "model.tr_bdf2_gamma")
    backend = integer(model["mesh_backend"], "model.mesh_backend")
    require(backend in (0, 1), "model.mesh_backend: unsupported backend")
    transport_model = "symmetric_voronoi_harmonic_interface_conductivity" if backend == 0 else "symmetric_cotangent_triangle_mean_conductivity"
    require(model["transport_model"] == transport_model, "model.transport_model: backend mismatch")
    level = integer(model["forcing_refinement_level"], "model.forcing_refinement_level")
    require(level <= 10, "model.forcing_refinement_level: unsupported refinement")
    audit.close(model["maximum_true_anomaly_step_rad"], math.ldexp(2 * math.pi / 768, -level), "model.maximum_true_anomaly_step_rad")
    audit.close(model["maximum_interval_fraction_of_year"], math.ldexp(1 / 360, -level), "model.maximum_interval_fraction_of_year")
    requested_year = number(model["requested_year_duration_seconds"], "model.requested_year_duration_seconds", positive=True)
    year = number(model["year_duration_seconds"], "model.year_duration_seconds", positive=True)
    durations = array(model["monthly_duration_seconds"], 12, "model.monthly_duration_seconds", nonnegative=True)
    radius = number(model["radius_m"], "model.radius_m", positive=True)
    alpha = number(model["top_of_atmosphere_albedo"], "model.top_of_atmosphere_albedo", nonnegative=True)
    require(alpha <= 1, "model.top_of_atmosphere_albedo: outside [0,1]")
    luminosity = number(model["stellar_luminosity"], "model.stellar_luminosity", nonnegative=True)
    eccentricity = number(model["orbital_eccentricity"], "model.orbital_eccentricity", nonnegative=True)
    require(eccentricity < 1, "model.orbital_eccentricity: outside [0,1)")
    tilt = number(model["axial_tilt_deg"], "model.axial_tilt_deg", nonnegative=True)
    require(tilt <= 90, "model.axial_tilt_deg: outside [0,90]")
    options = model["accepted_periodic_options"]
    require(options["time_method"] == method, "accepted_periodic_options.time_method: mismatch")
    require(options["step"]["duration_policy"] == "parent_duration_divided_by_thermal_subdivisions", "accepted_periodic_options.step.duration_policy: unsupported")
    phase_abs = number(options["phase_tolerance_k"], "phase_tolerance_k", positive=True)
    flux_abs = number(options["annual_flux_tolerance_w_m2"], "annual_flux_tolerance_w_m2", positive=True)
    relative = number(options["relative_tolerance"], "relative_tolerance", nonnegative=True)

    nodes = payload["climate_energy_forcing_intervals"]
    require(type(nodes) is list and bool(nodes), "forcing: expected nonempty array")
    require(type(options["thermal_subdivisions"]) is list and len(options["thermal_subdivisions"]) == len(nodes), "accepted partition: source coverage mismatch")
    months: list[list[dict[str, Any]]] = [[] for _ in range(12)]
    previous = 0
    steps = 0
    for i, node in enumerate(nodes):
        require(integer(node["id"], "forcing.id") == i, "forcing.id: not canonical")
        month = integer(node["month_index"], "forcing.month_index")
        require(previous <= month <= previous + 1 and month < 12, "forcing.month_index: not contiguous")
        previous = month
        fraction = number(node["duration_fraction_of_year"], "forcing.duration_fraction_of_year", positive=True)
        require(fraction <= model["maximum_interval_fraction_of_year"] * (1 + 1e-12), "forcing.duration_fraction_of_year: exceeds declared time bound")
        audit.close(node["duration_seconds"], fraction * requested_year, f"forcing[{i}].duration_seconds")
        declination = number(node["declination_rad"], "forcing.declination_rad")
        require(abs(declination) <= math.pi / 2, "forcing.declination_rad: invalid angle")
        number(node["inverse_square_distance_factor"], "forcing.inverse_square_distance_factor", positive=True)
        subdivisions = integer(node["thermal_subdivisions"], "forcing.thermal_subdivisions", 2)
        require(subdivisions & (subdivisions - 1) == 0, "forcing.thermal_subdivisions: not power of two")
        require(type(options["thermal_subdivisions"][i]) is int and options["thermal_subdivisions"][i] == subdivisions, "accepted partition: source mismatch")
        steps += subdivisions
        months[month].append(node)
    for month, entries in enumerate(months):
        require(bool(entries), f"forcing: missing month {month}")
        audit.close(durations[month], math.fsum(n["duration_seconds"] for n in entries), f"model.monthly_duration_seconds[{month}]")
        require(abs(durations[month] - year / 12) <= 1e-10 * year / 12, "forcing: unequal elapsed months")
    audit.close(year, math.fsum(n["duration_seconds"] for n in nodes), "model.year_duration_seconds")
    audit.close(math.fsum(n["duration_fraction_of_year"] for n in nodes), 1.0, "forcing.annual_duration_fraction")
    require(integer(model["achieved"]["accepted_steps_per_year"], "achieved.accepted_steps_per_year") == steps, "achieved.accepted_steps_per_year: partition mismatch")

    records = payload["climate_energy_balance_records"]
    require(type(records) is list and bool(records), "records: expected nonempty array")
    count = len(records)
    areas, elevations = [], []
    for i, record in enumerate(records):
        require(integer(record["cell_id"], "record.cell_id") == i, "record.cell_id: incomplete or unordered coverage")
        areas.append(number(record["area_m2"], f"record[{i}].area_m2", positive=True))
        elevations.append(number(record["interface_elevation_m"], f"record[{i}].interface_elevation_m"))
        latitude = number(record["latitude_rad"], f"record[{i}].latitude_rad")
        require(abs(latitude) <= math.pi / 2, "record.latitude_rad: outside poles")
        require(type(record["prescribed_marine_surface"]) is bool, "record.prescribed_marine_surface: expected boolean")
        depth = number(record["prescribed_water_depth_m"], "record.prescribed_water_depth_m", nonnegative=True)
        require((record["prescribed_marine_surface"] and depth > 0 and elevations[-1] == 0) or (not record["prescribed_marine_surface"] and depth == 0), "record: inconsistent retained surface")
        for key in MONTHLY:
            record_values = array(record[key], 12, f"record[{i}].{key}")
            if key in (MONTHLY[0], MONTHLY[1], MONTHLY[2], MONTHLY[3], MONTHLY[-1]):
                require(all(v >= 0 for v in record_values), f"record[{i}].{key}: negative physical value")
        array(record["monthly_boundary_temperature_k"], 13, f"record[{i}].monthly_boundary_temperature_k", nonnegative=True)
        require(number(record["top_of_atmosphere_albedo"], "record.top_of_atmosphere_albedo") == alpha, "record.top_of_atmosphere_albedo: model mismatch")
    total_area = math.fsum(areas)
    audit.close(model["total_area_m2"], total_area, "model.total_area_m2")
    require(abs(total_area - 4 * math.pi * radius**2) <= 2e-8 * total_area, "model.radius_m: area mismatch")

    pressure = number(model["mean_surface_pressure_pa"], "model.mean_surface_pressure_pa", nonnegative=True)
    gravity = number(model["gravity_m_s2"], "model.gravity_m_s2", positive=True)
    profile = number(model["hydrostatic_profile_temperature_k"], "model.hydrostatic_profile_temperature_k", positive=True)
    tau_ref = number(model["reference_infrared_optical_depth"], "model.reference_infrared_optical_depth", nonnegative=True)
    greenhouse = number(model["greenhouse_factor"], "model.greenhouse_factor", nonnegative=True)
    diffusivity = number(model["atmospheric_diffusivity_m2_s"], "model.atmospheric_diffusivity_m2_s", nonnegative=True)
    mixed_depth = number(model["marine_mixed_layer_depth_m"], "model.marine_mixed_layer_depth_m", positive=True)
    with localcontext() as context:
        context.prec = 60
        d = Decimal.from_float
        area_sum = sum(map(d, areas))
        height = d(287.05) * d(profile) / d(gravity)
        weights = [(-(d(z) - d(min(elevations))) / height).exp() for z in elevations]
        denominator = sum(d(area) * weight for area, weight in zip(areas, weights))
        for i, record in enumerate(records):
            path = f"record[{i}]"
            expected_pressure = float(d(pressure) * area_sum * weights[i] / denominator)
            audit.close(record["surface_pressure_pa"], expected_pressure, path + ".surface_pressure_pa")
            # Exported local pressure is the rounded authoritative coefficient
            # input. Independently checked above, it avoids a circular replay.
            p = d(number(record["surface_pressure_pa"], path + ".surface_pressure_pa", nonnegative=True))
            catm = float(d(1004.0) * p / d(gravity))
            tau = float(d(tau_ref) * d(greenhouse) * p / d(100000.0) * d(9.80665) / d(gravity))
            surface = float(d(4.1813e6) * d(min(record["prescribed_water_depth_m"], mixed_depth))) if record["prescribed_marine_surface"] else 4e6
            audit.close(record["surface_heat_capacity_j_m2_k"], surface, path + ".surface_heat_capacity_j_m2_k")
            audit.close(record["atmospheric_heat_capacity_j_m2_k"], catm, path + ".atmospheric_heat_capacity_j_m2_k")
            audit.close(record["heat_capacity_j_m2_k"], float(d(surface) + d(catm)), path + ".heat_capacity_j_m2_k")
            audit.close(record["infrared_optical_depth"], tau, path + ".infrared_optical_depth")
            audit.close(record["effective_longwave_emissivity"], float(1 / (1 + Decimal(".75") * d(number(record["infrared_optical_depth"], path + ".infrared_optical_depth", nonnegative=True)))), path + ".effective_longwave_emissivity")
            audit.close(record["horizontal_conductivity_w_k"], float(d(diffusivity) * d(catm)), path + ".horizontal_conductivity_w_k")
        pressure_area = sum(d(a) * d(float(r["surface_pressure_pa"])) for a, r in zip(areas, records))
        audit.close(model["atmospheric_scale_height_m"], float(height), "model.atmospheric_scale_height_m")
        audit.close(model["area_weighted_mean_surface_pressure_pa"], float(pressure_area / area_sum), "model.area_weighted_mean_surface_pressure_pa")
        audit.close(model["mean_surface_pressure_residual_pa"], float(pressure_area / area_sum - d(pressure)), "model.mean_surface_pressure_residual_pa", parents=(pressure,))
        mass = float(pressure_area / d(gravity))
        audit.close(model["total_atmospheric_mass_kg"], mass, "model.total_atmospheric_mass_kg")
        audit.close(model["atmospheric_mass_residual_kg"], float((pressure_area - d(pressure) * area_sum) / d(gravity)), "model.atmospheric_mass_residual_kg", parents=(mass,))
    audit.close(model["atmospheric_scale_height_to_radius"], float(height) / radius, "model.atmospheric_scale_height_to_radius")
    audit.close(model["maximum_interface_elevation_to_radius"], max(map(abs, elevations)) / radius, "model.maximum_interface_elevation_to_radius")

    edges = payload["climate_energy_transport_edges"]
    require(type(edges) is list, "transport_edges: expected array")
    adjacency: list[list[tuple[int, float]]] = [[] for _ in records]
    seen = set()
    for edge in edges:
        first = integer(edge["first_cell_id"], "edge.first_cell_id")
        second = integer(edge["second_cell_id"], "edge.second_cell_id")
        require(first < second < count and (first, second) not in seen, "edge: invalid or duplicate canonical pair")
        seen.add((first, second))
        conductance = number(edge["conductance_w_k"], "edge.conductance_w_k", positive=True)
        adjacency[first].append((second, conductance))
        adjacency[second].append((first, conductance))

    max_balance, max_phase = 0.0, 0.0
    annuals = []
    for i, record in enumerate(records):
        path = f"record[{i}]"
        boundaries = record["monthly_boundary_temperature_k"]
        phase = abs(boundaries[-1] - boundaries[0])
        max_phase = max(max_phase, phase)
        phase_tolerance = phase_abs + relative * max(boundaries[-1], boundaries[0])
        require(math.isfinite(phase_tolerance) and phase <= phase_tolerance, path + ": periodic phase does not converge")
        for month in range(12):
            suffix = f"[{month}]"
            mean = record[MONTHLY[0]][month]
            fourth = record[MONTHLY[1]][month]
            require(fourth + 128 * math.ulp(fourth) >= mean**4, path + ": fourth moment violates nonnegative-temperature Jensen bound")
            asr = math.fsum(
                (1 - alpha) * incident(record["latitude_rad"], node["declination_rad"], 1361.0 * luminosity * node["inverse_square_distance_factor"]) * node["duration_seconds"]
                for node in months[month]
            ) / durations[month]
            audit.close(record[MONTHLY[2]][month], asr, path + ".monthly_absorbed_shortwave_w_m2" + suffix)
            olr = 5.670374419e-8 * record["effective_longwave_emissivity"] * fourth
            audit.close(record[MONTHLY[3]][month], olr, path + ".monthly_emitted_longwave_w_m2" + suffix)
            exchanges = [g * (records[j][MONTHLY[0]][month] - mean) / areas[i] for j, g in adjacency[i]]
            transport_scale = math.fsum(g / areas[i] * (abs(records[j][MONTHLY[0]][month]) + abs(mean)) for j, g in adjacency[i])
            convergence = math.fsum(exchanges)
            audit.close(record[MONTHLY[4]][month], convergence, path + ".monthly_horizontal_heat_convergence_w_m2" + suffix, parents=(transport_scale,), ulps=256)
            storage = record["heat_capacity_j_m2_k"] * (boundaries[month + 1] - boundaries[month]) / durations[month]
            audit.close(record[MONTHLY[5]][month], storage, path + ".monthly_heat_storage_tendency_w_m2" + suffix, parents=(record["heat_capacity_j_m2_k"] * max(boundaries[month:month + 2]) / durations[month],))
            # Check residual against exported parents to isolate arithmetic
            # roundoff from the independently checked physical reconstructions.
            parents = tuple(record[key][month] for key in MONTHLY[2:6])
            residual = math.fsum((parents[3], -parents[0], parents[1], -parents[2]))
            audit.close(record[MONTHLY[6]][month], residual, path + ".monthly_balance_residual_w_m2" + suffix, parents=parents)
            max_balance = max(max_balance, abs(record[MONTHLY[6]][month]))
            require(abs(record[MONTHLY[6]][month]) <= record[MONTHLY[7]][month], path + ": residual exceeds declared solver tolerance")
        annual_parents = [math.fsum(record[key][m] * durations[m] for m in range(12)) / year for key in MONTHLY[2:5]]
        annual = math.fsum((annual_parents[0], -annual_parents[1], annual_parents[2]))
        audit.close(record["annual_net_heating_w_m2"], annual, path + ".annual_net_heating_w_m2", parents=tuple(annual_parents))
        mean_tolerance = math.fsum(record[MONTHLY[7]][m] * durations[m] for m in range(12)) / year
        annual_tolerance = flux_abs + relative * max(1.0, annual_parents[0], annual_parents[1], abs(annual_parents[2])) + mean_tolerance
        audit.close(record["annual_flux_tolerance_w_m2"], annual_tolerance, path + ".annual_flux_tolerance_w_m2")
        require(abs(record["annual_net_heating_w_m2"]) <= annual_tolerance, path + ": annual flux does not converge")
        annuals.append(record["annual_net_heating_w_m2"])
    achieved = model["achieved"]
    accuracy = model["requested_accuracy"]
    numerical_fraction = number(accuracy["maximum_numerical_error_fraction"], "requested_accuracy.maximum_numerical_error_fraction", positive=True)
    require(numerical_fraction <= 1, "requested_accuracy.maximum_numerical_error_fraction: must be at most one")
    local_ratio = number(achieved["maximum_local_error_ratio"], "achieved.maximum_local_error_ratio", nonnegative=True)
    numerical_ratio = number(achieved["maximum_numerical_error_ratio"], "achieved.maximum_numerical_error_ratio", nonnegative=True)
    require(numerical_ratio <= numerical_fraction and numerical_ratio <= local_ratio <= 1.0, "achieved: declared adaptive error gates do not pass")
    confirmations = integer(achieved["monthly_refinement_confirmations"], "achieved.monthly_refinement_confirmations")
    required_confirmations = integer(accuracy["required_monthly_refinement_confirmations"], "requested_accuracy.required_monthly_refinement_confirmations")
    require(confirmations >= required_confirmations, "achieved.monthly_refinement_confirmations: insufficient confirmations")
    # These are consistency checks of published achievements. The underlying
    # rejected steps and refinement history are not in the monthly witness.
    audit.close(achieved["maximum_phase_difference_k"], max_phase, "achieved.maximum_phase_difference_k")
    audit.close(achieved["maximum_annual_net_heating_w_m2"], max(map(abs, annuals)), "achieved.maximum_annual_net_heating_w_m2")
    audit.close(achieved["global_annual_net_heating_w"], math.fsum(a * n for a, n in zip(areas, annuals)), "achieved.global_annual_net_heating_w", parents=tuple(a * n for a, n in zip(areas, annuals)))
    for month in range(12):
        exchanges = [areas[i] * r[MONTHLY[4]][month] for i, r in enumerate(records)]
        audit.close(math.fsum(exchanges), 0.0, f"global.horizontal_heat_convergence_w[{month}]", parents=tuple(exchanges), ulps=256)

    world_linked = "cells" in payload
    if world_linked:
        verify_world_linkage(payload, audit, model, records, durations, year)
    unverified = ["orbital_node_generation_from_parameters", "astronomical_quadrature_accuracy",
                  "unexported_thermal_stage_trajectory", "adaptive_error_estimates_and_refinement_history",
                  "geometric_edge_reconstruction"]
    if not world_linked:
        unverified.append("full_world_display_field_linkage")
    return {
        "model": MODEL, "verified": True, "cell_count": count,
        "forcing_interval_count": len(nodes), "transport_edge_count": len(edges),
        "accepted_steps_per_year": steps, "time_method": method,
        "algebraic_checks": audit.checks,
        "maximum_monthly_balance_residual_w_m2": max_balance,
        "maximum_phase_difference_k": max_phase,
        "maximum_replay_errors": audit.maximum_errors,
        "scope": "published_source_nodes_coefficients_and_monthly_ledger_identities",
        "full_world_display_fields_linked": world_linked,
        "unverified": unverified,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("witness", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = verify(strict_load(args.witness))
    except (VerificationError, ValueError, OSError) as error:
        parser.exit(1, f"seasonal energy verification failed: {error}\n")
    encoded = json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.output:
        args.output.write_text(encoded)
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
