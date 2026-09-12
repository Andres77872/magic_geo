"""Analytical and independent geometric benchmarks, not producer replay alone."""

import math

import pytest

from magic_geo.climate_energy import (
    STEFAN_BOLTZMANN_W_M2_K4,
    SURFACE_LONGWAVE_EMISSIVITY,
    _surface_albedo,
    enrich_world_with_climate_energy_balance,
)
from magic_geo.geo_validation_physics import _validate_climate_energy
from magic_geo.insolation import (
    SOLAR_CONSTANT_W_M2,
    daily_mean_insolation,
    seasonal_insolation_series,
)


FLUX_FIELDS = (
    "top_of_atmosphere_insolation_w_m2", "absorbed_shortwave_w_m2",
    "outgoing_longwave_w_m2", "greenhouse_trapping_w_m2",
    "net_radiative_balance_w_m2",
)


def _unequal_area_world():
    return {
        "planet_parameters": {"axial_tilt_deg": 0.0, "orbital_eccentricity": 0.0},
        "cells": [
            {"id": 0, "area_km2": 1.0, "lat_deg": 0.0, "temperature_c": 10.0,
             "temperature_monthly_c": [10.0] * 12},
            {"id": 1, "area_km2": 3.0, "lat_deg": 60.0, "temperature_c": -10.0,
             "temperature_monthly_c": [-10.0] * 12},
        ],
    }


def test_spatial_flux_means_use_physical_cell_area_and_reject_stale_weights():
    world = enrich_world_with_climate_energy_balance(_unequal_area_world())
    summary = world["summary"]
    assert summary["climate_energy_area_weighted_summary_available"] is True
    assert summary["climate_energy_valid_area_cell_count"] == 2
    assert summary["climate_energy_represented_area_km2"] == 4.0
    # Zero-obliquity daily means at 0° and 60° are S/π and S/(2π).
    assert summary["area_weighted_mean_top_of_atmosphere_insolation_w_m2"] == pytest.approx(
        SOLAR_CONSTANT_W_M2 * 0.625 / math.pi, abs=1.0e-6
    )
    assert summary["mean_top_of_atmosphere_insolation_w_m2"] == pytest.approx(
        SOLAR_CONSTANT_W_M2 * 0.75 / math.pi, abs=1.0e-6
    )
    first, second = world["climate_energy_balance_records"]
    for field in FLUX_FIELDS:
        assert summary[f"area_weighted_mean_{field}"] == pytest.approx(
            first[field] * 0.25 + second[field] * 0.75, abs=5.1e-7
        )
    checks = []
    _validate_climate_energy(world, checks)
    assert all(check["passed"] for check in checks), checks
    # Preserve total area while changing its allocation, so checking only the
    # represented-area counter cannot detect this stale spatial average.
    world["cells"][0]["area_km2"] = 3.0
    world["cells"][1]["area_km2"] = 1.0
    checks = []
    _validate_climate_energy(world, checks)
    assert not all(check["passed"] for check in checks)


def test_flux_area_means_are_invariant_when_a_uniform_cell_is_subdivided():
    coarse = enrich_world_with_climate_energy_balance(_unequal_area_world())
    refined = _unequal_area_world()
    original = refined["cells"].pop(0)
    for cell_id, area in zip((0, 2, 3), (0.25, 0.25, 0.5)):
        refined["cells"].append({**original, "id": cell_id, "area_km2": area})
    enrich_world_with_climate_energy_balance(refined)
    for field in FLUX_FIELDS:
        assert refined["summary"][f"area_weighted_mean_{field}"] == pytest.approx(
            coarse["summary"][f"area_weighted_mean_{field}"], abs=1.0e-6
        )
    assert refined["summary"]["mean_top_of_atmosphere_insolation_w_m2"] != coarse["summary"]["mean_top_of_atmosphere_insolation_w_m2"]


@pytest.mark.parametrize("invalid_area", [None, 0.0, -1.0, True, "3", math.nan, math.inf, 10**400, -(10**400)])
@pytest.mark.parametrize("partial_coverage", [False, True])
def test_incomplete_area_coverage_cannot_publish_a_spatial_flux_mean(invalid_area, partial_coverage):
    world = _unequal_area_world()
    world["cells"][0]["area_km2"] = invalid_area
    if not partial_coverage:
        world["cells"][1].pop("area_km2")
    enrich_world_with_climate_energy_balance(world)
    summary = world["summary"]
    assert summary["climate_energy_area_weighted_summary_available"] is False
    assert summary["climate_energy_valid_area_cell_count"] == int(partial_coverage)
    assert summary["climate_energy_represented_area_km2"] == (3.0 if partial_coverage else 0.0)
    assert all(summary[f"area_weighted_mean_{field}"] is None for field in FLUX_FIELDS)
    checks = []
    _validate_climate_energy(world, checks)
    assert all(check["passed"] for check in checks), checks
    # Substituting a count mean is scientifically wrong even if it is finite.
    summary["area_weighted_mean_top_of_atmosphere_insolation_w_m2"] = summary["mean_top_of_atmosphere_insolation_w_m2"]
    checks = []
    _validate_climate_energy(world, checks)
    assert not all(check["passed"] for check in checks)


def test_unrepresentable_total_area_is_declared_unavailable_without_overflow():
    world = _unequal_area_world()
    for cell in world["cells"]:
        cell["area_km2"] = 1.0e308
    enrich_world_with_climate_energy_balance(world)
    assert world["summary"]["climate_energy_valid_area_cell_count"] == 2
    assert world["summary"]["climate_energy_represented_area_km2"] is None
    assert world["summary"]["climate_energy_area_weighted_summary_available"] is False
    checks = []
    _validate_climate_energy(world, checks)
    assert all(check["passed"] for check in checks), checks


def test_equinox_and_polar_day_night():
    solar = SOLAR_CONSTANT_W_M2
    assert daily_mean_insolation(0.0, 0.0, solar) == pytest.approx(solar / math.pi)
    assert daily_mean_insolation(math.pi / 3, 0.0, solar) == pytest.approx(solar / (2 * math.pi))
    tilt = math.radians(23.5)
    assert daily_mean_insolation(math.pi / 2, tilt, solar) == pytest.approx(solar * math.sin(tilt))
    assert daily_mean_insolation(math.pi / 2, -tilt, solar) == 0.0
    assert daily_mean_insolation(-math.pi / 2, tilt, solar) == 0.0


@pytest.mark.parametrize("latitude,declination", [(0, 90), (70, 23.5), (-70, 23.5), (43, -14), (-20, 70)])
def test_daily_mean_matches_independent_rotation_quadrature(latitude, declination):
    # Integrate dot products of a rotating surface normal and a fixed sun vector.
    phi, delta = math.radians(latitude), math.radians(declination)
    samples = 20000
    numeric = SOLAR_CONSTANT_W_M2 * math.fsum(
        max(0.0, math.cos(phi) * math.cos(2 * math.pi * (i + 0.5) / samples) * math.cos(delta)
            + math.sin(phi) * math.sin(delta))
        for i in range(samples)
    ) / samples
    assert daily_mean_insolation(phi, delta, SOLAR_CONSTANT_W_M2) == pytest.approx(numeric, abs=2e-5)


@pytest.mark.parametrize("eccentricity", [0.0, 0.016, 0.2, 0.8, 0.95, 0.99, 0.999, math.nextafter(1.0, 0.0)])
def test_annual_inverse_square_distance_uses_kepler_time_weighting(eccentricity):
    _, factors = seasonal_insolation_series(0, 1, 23.5, eccentricity, 12)
    expected = 1.0 / math.sqrt((1.0 - eccentricity) * (1.0 + eccentricity))
    assert math.fsum(factors) / 12 == pytest.approx(expected, rel=2e-15)


@pytest.mark.parametrize("tilt,eccentricity", [(0, 0), (23.5, 0.016), (60, 0.2), (90, 0.8), (23.5, 0.95), (90, 0.99)])
def test_global_annual_sunlight_closes_intercepted_solar_power(tilt, eccentricity):
    # Uniform sin(latitude) strips have equal area, independently of the mesh.
    strips = 512
    annual = math.fsum(
        math.fsum(seasonal_insolation_series(math.asin(-1 + 2 * (i + 0.5) / strips), 1, tilt, eccentricity, 12)[0]) / 12
        for i in range(strips)
    ) / strips
    expected = SOLAR_CONSTANT_W_M2 / (4 * math.sqrt(1 - eccentricity**2))
    assert annual == pytest.approx(expected, abs=0.015)


def test_high_obliquity_reverses_annual_pole_equator_insolation():
    def mean(latitude, tilt):
        return math.fsum(seasonal_insolation_series(latitude, 1, tilt, 0, 12)[0]) / 12

    assert mean(0, 23.5) > mean(math.pi / 2, 23.5)
    assert mean(math.pi / 2, 60) > mean(0, 60)
    assert mean(math.pi / 2, 90) == pytest.approx(SOLAR_CONSTANT_W_M2 / math.pi, abs=0.002)
    north, _ = seasonal_insolation_series(math.pi / 2, 1, 23.5, 0, 12)
    south, _ = seasonal_insolation_series(-math.pi / 2, 1, 23.5, 0, 12)
    assert north == pytest.approx(south[6:] + south[:6], abs=1e-10)
    assert north[0] == north[1] == north[10] == north[11] == 0.0


@pytest.mark.parametrize("eccentricity", [0.8, 0.95, 0.99, 0.999, math.nextafter(1.0, 0.0)])
def test_near_parabolic_orbits_retain_analytical_polar_annual_energy(eccentricity):
    # At 90° obliquity the pole's positive zenith factor integrates to 2
    # over one true-anomaly orbit, for every longitude of periapsis.
    complement = math.sqrt((1.0 - eccentricity) * (1.0 + eccentricity))
    expected = SOLAR_CONSTANT_W_M2 / (math.pi * complement)
    for latitude in (-math.pi / 2.0, math.pi / 2.0):
        monthly, _ = seasonal_insolation_series(latitude, 1.0, 90.0, eccentricity, 12)
        assert all(math.isfinite(value) and value >= 0.0 for value in monthly)
        assert math.fsum(monthly) / 12 == pytest.approx(expected, rel=4e-6)


@pytest.mark.parametrize("eccentricity", [-0.01, 1.0, math.inf, math.nan])
def test_invalid_nonelliptic_orbits_fail_instead_of_being_silently_clamped(eccentricity):
    with pytest.raises(ValueError, match="orbital_eccentricity"):
        seasonal_insolation_series(0.0, 1.0, 23.5, eccentricity, 12)


@pytest.mark.parametrize("eccentricity", [0.95, 0.99, math.nextafter(1.0, 0.0)])
def test_extreme_eccentricity_metadata_and_independent_energy_replay(eccentricity):
    world = {
        "planet_parameters": {"orbital_eccentricity": eccentricity},
        "cells": [{"id": 0, "lat_deg": 30.0, "temperature_c": 10.0,
                   "temperature_monthly_c": [10.0] * 12}],
    }
    enrich_world_with_climate_energy_balance(world)
    assert world["climate_energy_balance_records"][0]["orbital_eccentricity"] == eccentricity
    assert world["summary"]["orbital_eccentricity"] == eccentricity
    checks = []
    _validate_climate_energy(world, checks)
    assert all(check["passed"] for check in checks), checks


def test_no_greenhouse_graybody_equilibrium_closes_radiative_flux():
    albedo = 0.22 + 0.055  # Constant mixed-land diagnostic with no clouds.
    absorbed = SOLAR_CONSTANT_W_M2 / math.pi * (1.0 - albedo)
    equilibrium = (
        absorbed / (SURFACE_LONGWAVE_EMISSIVITY * STEFAN_BOLTZMANN_W_M2_K4)
    ) ** 0.25 - 273.15
    world = {
        "planet_parameters": {"greenhouse_factor": 0.0, "atmosphere_pressure_bar": 0.0,
                              "axial_tilt_deg": 0.0, "orbital_eccentricity": 0.0},
        "cells": [{"id": 0, "lat_deg": 0.0, "temperature_c": equilibrium,
                   "temperature_monthly_c": [equilibrium] * 12}],
    }
    enrich_world_with_climate_energy_balance(world)
    record = world["climate_energy_balance_records"][0]
    assert record["radiative_equilibrium_temperature_c"] == pytest.approx(equilibrium, abs=5.1e-7)
    assert record["energy_balance_residual_c"] == 0.0
    assert record["greenhouse_trapping_w_m2"] == 0.0
    assert record["net_radiative_balance_w_m2"] == 0.0
    assert record["absorbed_shortwave_w_m2"] == record["outgoing_longwave_w_m2"]


def test_bright_near_parabolic_graybody_has_no_spurious_greenhouse_trapping():
    from magic_geo.config import PlanetConfig

    planet = PlanetConfig(
        stellar_luminosity=100.0,
        axial_tilt_deg=0.0,
        orbital_eccentricity=math.nextafter(1.0, 0.0),
        greenhouse_factor=0.0,
        atmosphere_pressure_bar=0.0,
    )
    eccentricity = planet.orbital_eccentricity
    # Independent zero-obliquity annual mean at the equator, with mixed-land albedo.
    absorbed = (
        SOLAR_CONSTANT_W_M2 * planet.stellar_luminosity * (1.0 - 0.275)
        / (math.pi * math.sqrt((1.0 - eccentricity) * (1.0 + eccentricity)))
    )
    equilibrium = (
        absorbed / (SURFACE_LONGWAVE_EMISSIVITY * STEFAN_BOLTZMANN_W_M2_K4)
    ) ** 0.25 - 273.15
    world = {
        "planet_parameters": planet.model_dump(),
        "cells": [{"id": 0, "area_km2": 1.0, "lat_deg": 0.0,
                   "temperature_c": equilibrium,
                   "temperature_monthly_c": [equilibrium] * 12}],
    }
    enrich_world_with_climate_energy_balance(world, planet)
    record = world["climate_energy_balance_records"][0]
    assert record["absorbed_shortwave_w_m2"] == pytest.approx(absorbed, rel=2.0e-15)
    assert record["greenhouse_trapping_w_m2"] == 0.0
    assert record["energy_balance_residual_c"] == 0.0
    # At terawatt fluxes the direct net-flux subtraction retains a few ulps.
    assert abs(record["net_radiative_balance_w_m2"]) <= 8.0 * math.ulp(absorbed)
    assert world["summary"]["mean_greenhouse_trapping_w_m2"] == 0.0
    assert world["summary"]["area_weighted_mean_greenhouse_trapping_w_m2"] == 0.0
    checks = []
    _validate_climate_energy(world, checks)
    assert all(check["passed"] for check in checks), checks
    # Replay the original failing case away from equilibrium as well.
    world["cells"][0]["temperature_c"] = 10.0
    world["cells"][0]["temperature_monthly_c"] = [10.0] * 12
    enrich_world_with_climate_energy_balance(world, planet)
    checks = []
    _validate_climate_energy(world, checks)
    assert all(check["passed"] for check in checks), checks


def _near_equilibrium_energy_world(stellar_luminosity, eccentricity, offset):
    from magic_geo.config import PlanetConfig

    planet = PlanetConfig(
        stellar_luminosity=stellar_luminosity, axial_tilt_deg=0.0,
        orbital_eccentricity=eccentricity, greenhouse_factor=0.0,
        atmosphere_pressure_bar=0.0,
    )
    cells = []
    for cell_id, latitude, area in ((0, 0.0, 1.0), (1, 60.0, 3.0)):
        absorbed = (
            SOLAR_CONSTANT_W_M2 * stellar_luminosity * (1.0 - 0.275)
            * math.cos(math.radians(latitude))
            / (math.pi * math.sqrt((1.0 - eccentricity) * (1.0 + eccentricity)))
        )
        temperature = (
            absorbed / (SURFACE_LONGWAVE_EMISSIVITY * STEFAN_BOLTZMANN_W_M2_K4)
        ) ** 0.25 - 273.15 + offset
        cells.append({
            "id": cell_id, "area_km2": area, "lat_deg": latitude,
            "temperature_c": temperature, "temperature_monthly_c": [temperature] * 12,
        })
    return enrich_world_with_climate_energy_balance(
        {"planet_parameters": planet.model_dump(), "cells": cells}, planet,
    )


@pytest.mark.parametrize("offset", [0.0, -1.0e-11, 1.0e-11, -1.0e-8, 1.0e-8])
def test_extreme_equilibrium_and_near_equilibrium_replay_preserve_flux_roundoff(offset):
    world = _near_equilibrium_energy_world(100.0, math.nextafter(1.0, 0.0), offset)
    checks = []
    _validate_climate_energy(world, checks)
    assert all(check["passed"] for check in checks), checks


@pytest.mark.parametrize("extreme", [False, True])
@pytest.mark.parametrize("target", ["record", "cell", "count_mean", "area_mean"])
def test_net_roundoff_allowance_rejects_resolvable_flux_tampering(extreme, target):
    world = _near_equilibrium_energy_world(
        100.0 if extreme else 1.0,
        math.nextafter(1.0, 0.0) if extreme else 0.0,
        0.0,
    )
    containers = {
        "record": (world["climate_energy_balance_records"][0], "net_radiative_balance_w_m2"),
        "cell": (world["cells"][0], "net_radiative_balance_w_m2"),
        "count_mean": (world["summary"], "mean_net_radiative_balance_w_m2"),
        "area_mean": (world["summary"], "area_weighted_mean_net_radiative_balance_w_m2"),
    }
    container, field = containers[target]
    container[field] += 1.0 if extreme else 1.0e-4
    checks = []
    _validate_climate_energy(world, checks)
    assert not all(check["passed"] for check in checks), checks
    assert any("net_radiative_balance_w_m2" in violation for check in checks
               for violation in check["evidence"]["violations"])


@pytest.mark.parametrize("target", ["record", "cell", "count_mean"])
def test_stress_roundoff_allowance_rejects_resolvable_stress_tampering(target):
    world = _near_equilibrium_energy_world(100.0, math.nextafter(1.0, 0.0), 0.0)
    containers = {
        "record": (world["climate_energy_balance_records"][0], "climate_energy_stress_index"),
        "cell": (world["cells"][0], "climate_energy_stress_index"),
        "count_mean": (world["summary"], "mean_climate_energy_stress_index"),
    }
    container, field = containers[target]
    container[field] += 0.001
    checks = []
    _validate_climate_energy(world, checks)
    assert not all(check["passed"] for check in checks), checks
    assert any("climate_energy_stress_index" in violation for check in checks
               for violation in check["evidence"]["violations"])


@pytest.mark.parametrize("target_stress", [0.6499994, 0.6499996, 0.6500004])
def test_high_stress_count_uses_published_six_decimal_stress(target_stress):
    absorbed = SOLAR_CONSTANT_W_M2 * (1.0 - 0.275) / math.pi
    radiation_coefficient = SURFACE_LONGWAVE_EMISSIVITY * STEFAN_BOLTZMANN_W_M2_K4
    graybody_kelvin = (absorbed / radiation_coefficient) ** 0.25
    # Solve an ordinary, greenhouse-free warm anomaly for a target just either
    # side of the six-decimal export boundary. No producer replay is used here.
    lower, upper = 0.0, 100.0
    for _ in range(80):
        offset = (lower + upper) / 2.0
        net_loss = radiation_coefficient * (graybody_kelvin + offset)**4 - absorbed
        stress = offset / 28.0 + net_loss / 220.0
        if stress < target_stress:
            lower = offset
        else:
            upper = offset
    world = _near_equilibrium_energy_world(1.0, 0.0, (lower + upper) / 2.0)
    records = world["climate_energy_balance_records"]
    assert records[0]["climate_energy_stress_index"] == round(target_stress, 6)
    published_count = sum(record["climate_energy_stress_index"] >= 0.65 for record in records)
    assert world["summary"]["high_climate_energy_stress_cell_count"] == published_count
    checks = []
    _validate_climate_energy(world, checks)
    assert all(check["passed"] for check in checks), checks
    world["summary"]["high_climate_energy_stress_cell_count"] = published_count + 1
    checks = []
    _validate_climate_energy(world, checks)
    assert not all(check["passed"] for check in checks), checks
    assert any("high_climate_energy_stress_cell_count" in violation for check in checks
               for violation in check["evidence"]["violations"])


def test_energy_enricher_uses_world_planet_and_independent_replay():
    world = {
        "planet_parameters": {"axial_tilt_deg": 90.0, "orbital_eccentricity": 0.2},
        "cells": [{"id": 0, "lat_deg": 90, "temperature_c": -10, "temperature_monthly_c": [-10] * 12}],
    }
    enrich_world_with_climate_energy_balance(world)
    record = world["climate_energy_balance_records"][0]
    expected, _ = seasonal_insolation_series(math.pi / 2, 1, 90, 0.2, 12)
    assert record["monthly_top_of_atmosphere_insolation_w_m2"] == pytest.approx(expected, abs=5.1e-7)
    checks = []
    _validate_climate_energy(world, checks)
    assert all(check["passed"] for check in checks), checks
    world["climate_energy_model"]["native_temperature_forcing_coupled"] = True
    checks = []
    _validate_climate_energy(world, checks)
    assert not all(check["passed"] for check in checks)


@pytest.mark.parametrize("water_body", ["fresh_lake", "saline_basin"])
def test_lake_albedo_uses_standing_water_not_marine_flag(water_body):
    lake = {"is_water": False, "is_lake": True, "water_body_type": water_body,
            "temperature_c": 10.0, "seasonal_aridity_index": 1.0}
    albedo, regime = _surface_albedo(lake)
    assert regime == "lake_water"
    assert albedo == pytest.approx(0.155)  # water + scattering, no land brightening
    lake["ice_thickness_m"] = 200.0
    assert _surface_albedo(lake)[1] == "ice_albedo"
    lake.update(is_lake=False, ice_thickness_m=0.0, biome="salt_flat")
    assert _surface_albedo(lake)[1] != "lake_water"
