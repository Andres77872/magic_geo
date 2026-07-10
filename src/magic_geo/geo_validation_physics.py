from __future__ import annotations

import math
from collections import Counter
from typing import Any


SOLAR_CONSTANT_W_M2 = 1361.0
STEFAN_BOLTZMANN_W_M2_K4 = 5.670374419e-8
SURFACE_LONGWAVE_EMISSIVITY = 0.96

CRUST_NAMES = (
    "oceanic",
    "continental",
    "transitional",
    "volcanic_arc",
    "craton",
    "orogen",
    "rift_basin",
    "sedimentary_basin",
    "accreted_terrane",
)
LITHOLOGY_NAMES = (
    "basalt",
    "granite",
    "limestone",
    "sandstone",
    "shale",
    "volcanic",
    "metamorphic",
)


def _append_check(
    checks: list[dict[str, Any]],
    *,
    domain: str,
    name: str,
    passed: bool,
    message: str,
    observed: Any,
    expected: Any,
    evidence: dict[str, Any] | None = None,
) -> None:
    checks.append(
        {
            "id": len(checks),
            "domain": domain,
            "name": name,
            "status": "passed" if passed else "failed",
            "passed": passed,
            "severity": "error",
            "message": message,
            "observed": observed,
            "expected": expected,
            "evidence": evidence or {},
        }
    )


def _finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _number(value: Any) -> float | None:
    if not _finite_number(value):
        return None
    return float(value)


def _integer(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _close(
    actual: Any,
    expected: float,
    *,
    absolute: float = 1.0e-6,
    relative: float = 1.0e-8,
) -> bool:
    value = _number(actual)
    return value is not None and abs(value - expected) <= max(
        absolute, abs(expected) * relative
    )


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _planet_value(world: dict[str, Any], key: str, default: float) -> float:
    parameters = world.get("planet_parameters")
    if not isinstance(parameters, dict):
        return default
    value = _number(parameters.get(key))
    return default if value is None else value


def _unit_vector(value: Any, tolerance: float = 0.01) -> bool:
    if not isinstance(value, list) or len(value) != 3:
        return False
    components = [_number(component) for component in value]
    if any(component is None for component in components):
        return False
    length = math.sqrt(sum(float(component) ** 2 for component in components))
    return abs(length - 1.0) <= tolerance


def _record_violation(violations: list[str], message: str) -> None:
    # Reports remain useful on large worlds without copying thousands of errors.
    if len(violations) < 40:
        violations.append(message)


def _validate_plate_aggregates(
    world: dict[str, Any], checks: list[dict[str, Any]]
) -> None:
    cells = world.get("cells")
    plates = world.get("plates")
    summary = world.get("summary")
    violations: list[str] = []
    maximum_residuals = {
        "area_km2": 0.0,
        "mean_crust_age_ma": 0.0,
        "mean_crust_density": 0.0,
        "mean_crust_thickness_km": 0.0,
        "mean_boundary_activity": 0.0,
        "mean_heat_flow_mw_m2": 0.0,
    }

    if not isinstance(cells, list) or not cells or not all(
        isinstance(cell, dict) for cell in cells
    ):
        _record_violation(violations, "cells must be a non-empty list of objects")
        cells = []
    if not isinstance(plates, list) or not plates or not all(
        isinstance(plate, dict) for plate in plates
    ):
        _record_violation(violations, "plates must be a non-empty list of objects")
        plates = []

    plate_ids: list[int] = []
    for index, plate in enumerate(plates):
        plate_id = _integer(plate.get("id"))
        if plate_id is None:
            _record_violation(violations, f"plate[{index}] id is not an integer")
            continue
        plate_ids.append(plate_id)
        if plate_id != index:
            _record_violation(
                violations, f"plate[{index}] id {plate_id} is not sequential"
            )
    if len(set(plate_ids)) != len(plate_ids):
        _record_violation(violations, "plate ids are duplicated")

    aggregates: dict[int, dict[str, Any]] = {
        plate_id: {
            "count": 0,
            "area": 0.0,
            "age": 0.0,
            "density": 0.0,
            "thickness": 0.0,
            "boundary": 0.0,
            "heat": 0.0,
            "crust_area": {name: 0.0 for name in CRUST_NAMES},
            "lithology_area": {name: 0.0 for name in LITHOLOGY_NAMES},
        }
        for plate_id in plate_ids
    }
    internal_heat = _planet_value(world, "internal_heat", 1.0)
    if not math.isfinite(internal_heat) or internal_heat < 0.0:
        _record_violation(violations, "planet internal_heat is not nonnegative")

    for index, cell in enumerate(cells):
        plate_id = _integer(cell.get("plate_id"))
        if plate_id not in aggregates:
            _record_violation(
                violations, f"cell[{index}] has unknown plate_id {plate_id!r}"
            )
            continue
        numeric_fields = (
            "area_km2",
            "crust_age_ma",
            "crust_density",
            "crust_thickness_km",
            "boundary_convergent",
            "boundary_divergent",
            "boundary_transform",
        )
        values = {field: _number(cell.get(field)) for field in numeric_fields}
        if any(value is None for value in values.values()):
            _record_violation(
                violations, f"cell[{index}] has non-finite plate aggregate inputs"
            )
            continue
        area = float(values["area_km2"])
        age = float(values["crust_age_ma"])
        density = float(values["crust_density"])
        thickness = float(values["crust_thickness_km"])
        convergent = float(values["boundary_convergent"])
        divergent = float(values["boundary_divergent"])
        transform = float(values["boundary_transform"])
        if (
            area <= 0.0
            or age < 0.0
            or density <= 0.0
            or thickness <= 0.0
            or any(
                value < 0.0 or value > 1.0
                for value in (convergent, divergent, transform)
            )
        ):
            _record_violation(
                violations, f"cell[{index}] has out-of-range plate aggregate inputs"
            )

        crust = str(cell.get("crust_type", ""))
        lithology = str(cell.get("lithology", ""))
        if crust not in CRUST_NAMES:
            _record_violation(violations, f"cell[{index}] has unknown crust_type")
        if lithology not in LITHOLOGY_NAMES:
            _record_violation(violations, f"cell[{index}] has unknown lithology")
        boundary = max(convergent, divergent, transform)
        oceanic = crust == "oceanic" or (
            crust in {"transitional", "volcanic_arc"}
            and age <= 320.0
            and thickness <= 18.0
            and density >= 2.84
        )
        age_heat = (
            45.0 + 95.0 * math.exp(-age / 60.0)
            if oceanic
            else 38.0 + 34.0 * math.exp(-age / 1400.0)
        )
        boundary_heat = (
            55.0 * divergent
            + 30.0 * convergent
            + 18.0 * transform
            + (24.0 if crust == "volcanic_arc" else 0.0)
        )
        heat = _clamp(internal_heat * (age_heat + boundary_heat), 18.0, 240.0)
        aggregate = aggregates[plate_id]
        aggregate["count"] += 1
        aggregate["area"] += area
        aggregate["age"] += age * area
        aggregate["density"] += density * area
        aggregate["thickness"] += thickness * area
        aggregate["boundary"] += boundary * area
        aggregate["heat"] += heat * area
        if crust in CRUST_NAMES:
            aggregate["crust_area"][crust] += area
        if lithology in LITHOLOGY_NAMES:
            aggregate["lithology_area"][lithology] += area

    required_fields = {
        "id",
        "kind",
        "axis",
        "initial_center",
        "center",
        "angular_speed",
        "cumulative_rotation_deg",
        "crust_density",
        "crust_thickness_km",
        "cell_count",
        "area_km2",
        "mean_crust_age_ma",
        "mean_crust_density",
        "mean_crust_thickness_km",
        "dominant_crust_type",
        "dominant_lithology",
        "mean_boundary_activity",
        "mean_heat_flow_mw_m2",
        "thermal_state",
    }
    geological_age_ma = max(
        0.0, _planet_value(world, "geological_age_ga", 4.5) * 1000.0
    )
    for index, plate in enumerate(plates):
        missing = required_fields - set(plate)
        if missing:
            _record_violation(
                violations,
                f"plate[{index}] is missing fields: {', '.join(sorted(missing))}",
            )
            continue
        plate_id = _integer(plate.get("id"))
        aggregate = aggregates.get(plate_id) if plate_id is not None else None
        if aggregate is None:
            _record_violation(violations, f"plate[{index}] cannot be aggregated")
            continue
        if str(plate.get("kind")) not in {"oceanic", "continental", "mixed"}:
            _record_violation(violations, f"plate[{index}] kind is invalid")
        for vector_field in ("axis", "initial_center", "center"):
            if not _unit_vector(plate.get(vector_field)):
                _record_violation(
                    violations, f"plate[{index}] {vector_field} is not a unit vector"
                )

        positive_fields = (
            "crust_density",
            "crust_thickness_km",
            "area_km2",
            "mean_crust_density",
            "mean_crust_thickness_km",
            "mean_heat_flow_mw_m2",
        )
        for field in positive_fields:
            value = _number(plate.get(field))
            if value is None or value <= 0.0:
                _record_violation(
                    violations, f"plate[{index}] {field} is not finite and positive"
                )
        nonnegative_fields = (
            "angular_speed",
            "cumulative_rotation_deg",
            "mean_crust_age_ma",
        )
        for field in nonnegative_fields:
            value = _number(plate.get(field))
            if value is None or value < 0.0:
                _record_violation(
                    violations, f"plate[{index}] {field} is not finite and nonnegative"
                )
        mean_age = _number(plate.get("mean_crust_age_ma"))
        if mean_age is not None and mean_age > geological_age_ma + 1.0e-4:
            _record_violation(violations, f"plate[{index}] mean crust age exceeds planet age")
        boundary_value = _number(plate.get("mean_boundary_activity"))
        if boundary_value is None or not 0.0 <= boundary_value <= 1.0:
            _record_violation(
                violations, f"plate[{index}] mean boundary activity is out of range"
            )
        heat_value = _number(plate.get("mean_heat_flow_mw_m2"))
        if heat_value is None or not 18.0 <= heat_value <= 240.0:
            _record_violation(violations, f"plate[{index}] heat flow is out of range")

        area = float(aggregate["area"])
        divisor = area if area > 0.0 else 1.0
        expected_values = {
            "area_km2": area,
            "mean_crust_age_ma": float(aggregate["age"]) / divisor,
            "mean_crust_density": float(aggregate["density"]) / divisor,
            "mean_crust_thickness_km": float(aggregate["thickness"]) / divisor,
            "mean_boundary_activity": float(aggregate["boundary"]) / divisor,
            "mean_heat_flow_mw_m2": float(aggregate["heat"]) / divisor,
        }
        tolerances = {
            "area_km2": (1.0, 1.0e-4),
            "mean_crust_age_ma": (0.01, 1.0e-4),
            "mean_crust_density": (0.001, 0.0),
            "mean_crust_thickness_km": (0.01, 0.0),
            "mean_boundary_activity": (0.001, 0.0),
            "mean_heat_flow_mw_m2": (0.01, 1.0e-4),
        }
        for field, expected in expected_values.items():
            actual = _number(plate.get(field))
            residual = math.inf if actual is None else abs(actual - expected)
            maximum_residuals[field] = max(maximum_residuals[field], residual)
            absolute, relative = tolerances[field]
            if not _close(
                plate.get(field), expected, absolute=absolute, relative=relative
            ):
                _record_violation(
                    violations,
                    f"plate[{index}] {field} does not replay from member cells",
                )
        if _integer(plate.get("cell_count")) != aggregate["count"]:
            _record_violation(
                violations, f"plate[{index}] cell_count does not match member cells"
            )
        expected_crust = max(
            CRUST_NAMES, key=lambda name: aggregate["crust_area"][name]
        )
        expected_lithology = max(
            LITHOLOGY_NAMES, key=lambda name: aggregate["lithology_area"][name]
        )
        if plate.get("dominant_crust_type") != expected_crust:
            _record_violation(
                violations, f"plate[{index}] dominant crust type is inconsistent"
            )
        if plate.get("dominant_lithology") != expected_lithology:
            _record_violation(
                violations, f"plate[{index}] dominant lithology is inconsistent"
            )
        if heat_value is not None:
            expected_thermal_state = (
                "hot_active"
                if heat_value >= 95.0
                else ("warm_active" if heat_value >= 65.0 else "cool_stable")
            )
            if plate.get("thermal_state") != expected_thermal_state:
                _record_violation(
                    violations, f"plate[{index}] thermal_state is inconsistent"
                )

    if not isinstance(summary, dict) or _integer(summary.get("plate_count")) != len(
        plates
    ):
        _record_violation(violations, "summary plate_count does not match plates")
    reconstructed_surface_area = sum(
        float(aggregate["area"]) for aggregate in aggregates.values()
    )
    cell_surface_area = sum(
        float(_number(cell.get("area_km2")) or 0.0) for cell in cells
    )
    if not _close(
        reconstructed_surface_area,
        cell_surface_area,
        absolute=0.01,
        relative=1.0e-10,
    ):
        _record_violation(violations, "plate areas do not cover the cell surface")

    _append_check(
        checks,
        domain="tectonics",
        name="plate_aggregate_replay",
        passed=not violations,
        message=(
            "plate counts, areas, area-weighted crust/heat aggregates, categories, "
            "and finite physical fields must replay from assigned cells"
        ),
        observed={
            "cell_count": len(cells),
            "plate_count": len(plates),
            "violation_count": len(violations),
            "maximum_replay_residuals": maximum_residuals,
        },
        expected={
            "all_cells_assigned_once": True,
            "plate_aggregates_match_cells": True,
            "physical_fields_finite_and_nonnegative": True,
        },
        evidence={"violations": violations},
    )


def _surface_albedo(cell: dict[str, Any]) -> tuple[float, str]:
    biome = str(cell.get("biome", "unknown"))
    water_body = str(cell.get("water_body_type", "land"))
    temperature = float(cell.get("temperature_c", 0.0))
    precipitation = float(cell.get("precipitation_mm_y", 0.0))
    seasonal_aridity = _clamp(float(cell.get("seasonal_aridity_index", 0.0)))
    elevation = float(cell.get("elevation_m", 0.0))
    ice = max(0.0, float(cell.get("ice_thickness_m", 0.0)))

    if bool(cell.get("is_water", False)):
        if water_body in {"fresh_lake", "saline_basin", "inland_sea"}:
            base, regime = 0.10, "lake_water"
        elif water_body == "continental_shelf":
            base, regime = 0.08, "shallow_ocean"
        else:
            base, regime = 0.065, "open_ocean"
    elif ice > 20.0 or biome == "ice_cap":
        base = 0.58 + _clamp(ice / 2500.0) * 0.12
        regime = "ice_albedo"
    elif biome in {"tundra", "alpine"}:
        base, regime = (0.34 if temperature < -2.0 else 0.28), "cold_sparse_cover"
    elif biome in {"hot_desert", "cold_desert"}:
        base, regime = (0.36 if biome == "hot_desert" else 0.32), "arid_high_albedo"
    elif biome in {"savanna", "temperate_grassland", "mediterranean_scrub"}:
        base, regime = 0.21, "seasonal_grassland"
    elif "forest" in biome:
        base, regime = (0.14 if biome != "tropical_rainforest" else 0.12), "forest_canopy"
    else:
        base, regime = 0.22, "mixed_land"

    cloud_albedo = _clamp(precipitation / 2800.0) * 0.055 + max(
        0.0, float(cell.get("vertical_velocity_index", 0.0))
    ) * 0.018
    dry_brightening = seasonal_aridity * (
        0.035 if not bool(cell.get("is_water", False)) else 0.0
    )
    snow_brightening = (
        0.08
        if not bool(cell.get("is_water", False))
        and temperature < -3.0
        and precipitation >= 250.0
        else 0.0
    )
    elevation_brightening = (
        _clamp((elevation - 2600.0) / 2600.0) * 0.035
        if elevation > 2600.0
        else 0.0
    )
    return (
        _clamp(
            base
            + 0.055
            + cloud_albedo
            + dry_brightening
            + snow_brightening
            + elevation_brightening,
            0.04,
            0.86,
        ),
        regime,
    )


def _greenhouse_effect_c(
    cell: dict[str, Any], greenhouse_factor: float, pressure_bar: float
) -> float:
    humidity = _clamp(
        float(cell.get("humidity_transport_index", 0.0)) * 0.35
        + (float(cell.get("ocean_current_moisture_factor", 1.0)) - 0.72)
        / 0.56
        * 0.25
        + _clamp(float(cell.get("precipitation_mm_y", 0.0)) / 2600.0) * 0.25
        + _clamp(float(cell.get("vapor_evaporation_mm_y", 0.0)) / 1500.0) * 0.15
    )
    dry_penalty = _clamp(float(cell.get("seasonal_aridity_index", 0.0))) * 2.5
    ice_penalty = _clamp(float(cell.get("ice_thickness_m", 0.0)) / 1800.0) * 3.0
    water_bonus = 1.5 if bool(cell.get("is_water", False)) else 0.0
    return max(
        0.0,
        (
            13.5
            + humidity * 8.0
            + water_bonus
            - dry_penalty
            - ice_penalty
        )
        * greenhouse_factor
        * math.sqrt(max(0.0, pressure_bar)),
    )


def _seasonal_insolation_series(
    latitude_radians: float,
    stellar_luminosity: float,
    axial_tilt_degrees: float,
    orbital_eccentricity: float,
    months: int,
) -> tuple[list[float], list[float]]:
    eccentricity = _clamp(orbital_eccentricity, 0.0, 0.8)
    tilt = _clamp(axial_tilt_degrees, 0.0, 90.0)
    tilt_radians = math.radians(tilt)
    tilt_contrast = 1.0 + (tilt / 90.0 - 23.5 / 90.0) * 0.18
    latitude_factor = 0.46 + 0.72 * max(
        0.0, math.cos(latitude_radians)
    ) * tilt_contrast
    monthly: list[float] = []
    orbital_factors: list[float] = []
    for month in range(max(1, months)):
        season_angle = 2.0 * math.pi * (float(month) - 5.5) / max(1, months)
        declination = tilt_radians * math.cos(season_angle)
        seasonal_latitude_factor = _clamp(
            1.0 + 0.65 * math.sin(latitude_radians) * math.sin(declination),
            0.08,
            1.92,
        )
        true_anomaly = 2.0 * math.pi * float(month) / max(1, months)
        orbital_distance_au = (1.0 - eccentricity * eccentricity) / max(
            0.02, 1.0 + eccentricity * math.cos(true_anomaly)
        )
        orbital_factor = 1.0 / max(
            0.02, orbital_distance_au * orbital_distance_au
        )
        monthly.append(
            SOLAR_CONSTANT_W_M2
            * stellar_luminosity
            * latitude_factor
            * seasonal_latitude_factor
            * orbital_factor
            / 4.0
        )
        orbital_factors.append(orbital_factor)
    return monthly, orbital_factors


def _validate_climate_energy(
    world: dict[str, Any], checks: list[dict[str, Any]]
) -> None:
    cells = world.get("cells")
    records = world.get("climate_energy_balance_records")
    summary = world.get("summary")
    violations: list[str] = []
    maximum_equation_residual = 0.0

    if not isinstance(cells, list) or not cells or not all(
        isinstance(cell, dict) for cell in cells
    ):
        _record_violation(violations, "cells must be a non-empty list of objects")
        cells = []
    if not isinstance(records, list):
        _record_violation(violations, "climate energy records must be a list")
        records = []
    if not isinstance(summary, dict):
        _record_violation(violations, "summary must be an object")
        summary = {}

    cells_by_id: dict[int, dict[str, Any]] = {}
    for index, cell in enumerate(cells):
        cell_id = _integer(cell.get("id"))
        if cell_id is None or cell_id in cells_by_id:
            _record_violation(violations, f"cell[{index}] has invalid or duplicate id")
            continue
        cells_by_id[cell_id] = cell

    first_months = cells[0].get("temperature_monthly_c") if cells else None
    month_count = len(first_months) if isinstance(first_months, list) else 12
    if month_count <= 0:
        month_count = 12
    for index, cell in enumerate(cells):
        monthly_temperature = cell.get("temperature_monthly_c")
        if (
            not isinstance(monthly_temperature, list)
            or len(monthly_temperature) != month_count
            or any(not _finite_number(value) for value in monthly_temperature)
        ):
            _record_violation(
                violations,
                f"cell[{index}] monthly temperature coverage is inconsistent",
            )

    stellar_luminosity = max(0.01, _planet_value(world, "stellar_luminosity", 1.0))
    greenhouse_factor = max(0.0, _planet_value(world, "greenhouse_factor", 1.0))
    pressure_bar = max(0.0, _planet_value(world, "atmosphere_pressure_bar", 1.0))
    axial_tilt = _clamp(_planet_value(world, "axial_tilt_deg", 23.5), 0.0, 90.0)
    eccentricity = _clamp(
        _planet_value(world, "orbital_eccentricity", 0.016), 0.0, 0.8
    )

    required_fields = {
        "id",
        "cell_id",
        "latitude_deg",
        "biome",
        "water_body_type",
        "surface_albedo_regime",
        "stellar_luminosity_factor",
        "planetary_greenhouse_factor",
        "atmosphere_pressure_bar",
        "orbital_eccentricity",
        "mean_orbital_distance_factor",
        "temperature_c",
        "monthly_top_of_atmosphere_insolation_w_m2",
        "top_of_atmosphere_insolation_w_m2",
        "seasonal_insolation_range_w_m2",
        "orbital_insolation_variability_index",
        "peak_seasonal_insolation_w_m2",
        "low_seasonal_insolation_w_m2",
        "surface_albedo_index",
        "absorbed_shortwave_w_m2",
        "outgoing_longwave_w_m2",
        "greenhouse_trapping_w_m2",
        "net_radiative_balance_w_m2",
        "no_greenhouse_equilibrium_temperature_c",
        "radiative_equilibrium_temperature_c",
        "energy_balance_residual_c",
        "climate_energy_stress_index",
    }
    expected_by_cell: dict[int, dict[str, Any]] = {}
    regime_counts: Counter[str] = Counter()
    sums = Counter()
    high_stress_count = 0
    for cell_id, cell in cells_by_id.items():
        try:
            latitude = float(cell["lat_deg"])
            observed_temperature = float(cell["temperature_c"])
            ocean_current_temperature = float(
                cell.get("ocean_current_temperature_c", 0.0)
            )
            albedo, regime = _surface_albedo(cell)
            greenhouse_effect = _greenhouse_effect_c(
                cell, greenhouse_factor, pressure_bar
            )
        except (KeyError, TypeError, ValueError, OverflowError):
            _record_violation(
                violations, f"cell {cell_id} has invalid climate-energy inputs"
            )
            continue
        if not all(
            math.isfinite(value)
            for value in (
                latitude,
                observed_temperature,
                ocean_current_temperature,
                albedo,
                greenhouse_effect,
            )
        ):
            _record_violation(
                violations, f"cell {cell_id} has non-finite climate-energy inputs"
            )
            continue
        monthly, orbital_factors = _seasonal_insolation_series(
            math.radians(latitude),
            stellar_luminosity,
            axial_tilt,
            eccentricity,
            month_count,
        )
        top = sum(monthly) / len(monthly)
        peak = max(monthly)
        low = min(monthly)
        seasonal_range = peak - low
        orbital_variability = _clamp(seasonal_range / max(1.0, top))
        mean_orbital_factor = sum(orbital_factors) / len(orbital_factors)
        absorbed = top * (1.0 - albedo)
        no_greenhouse_c = (
            (absorbed / STEFAN_BOLTZMANN_W_M2_K4) ** 0.25 - 273.15
            if absorbed > 0.0
            else -273.15
        )
        equilibrium_c = (
            no_greenhouse_c
            + greenhouse_effect
            + ocean_current_temperature * 0.35
        )
        observed_kelvin = max(1.0, observed_temperature + 273.15)
        equilibrium_kelvin = max(1.0, equilibrium_c + 273.15)
        outgoing = (
            SURFACE_LONGWAVE_EMISSIVITY
            * STEFAN_BOLTZMANN_W_M2_K4
            * observed_kelvin**4
        )
        equilibrium_longwave = (
            SURFACE_LONGWAVE_EMISSIVITY
            * STEFAN_BOLTZMANN_W_M2_K4
            * equilibrium_kelvin**4
        )
        trapping = max(0.0, equilibrium_longwave - absorbed)
        net = absorbed + trapping - outgoing
        residual_c = observed_temperature - equilibrium_c
        stress = _clamp(abs(residual_c) / 28.0 + abs(net) / 220.0)
        expected = {
            "latitude_deg": latitude,
            "stellar_luminosity_factor": stellar_luminosity,
            "planetary_greenhouse_factor": greenhouse_factor,
            "atmosphere_pressure_bar": pressure_bar,
            "orbital_eccentricity": eccentricity,
            "mean_orbital_distance_factor": mean_orbital_factor,
            "temperature_c": observed_temperature,
            "monthly_top_of_atmosphere_insolation_w_m2": monthly,
            "top_of_atmosphere_insolation_w_m2": top,
            "seasonal_insolation_range_w_m2": seasonal_range,
            "orbital_insolation_variability_index": orbital_variability,
            "peak_seasonal_insolation_w_m2": peak,
            "low_seasonal_insolation_w_m2": low,
            "surface_albedo_index": albedo,
            "absorbed_shortwave_w_m2": absorbed,
            "outgoing_longwave_w_m2": outgoing,
            "greenhouse_trapping_w_m2": trapping,
            "net_radiative_balance_w_m2": net,
            "no_greenhouse_equilibrium_temperature_c": no_greenhouse_c,
            "radiative_equilibrium_temperature_c": equilibrium_c,
            "energy_balance_residual_c": residual_c,
            "climate_energy_stress_index": stress,
            "surface_albedo_regime": regime,
        }
        expected_by_cell[cell_id] = expected
        regime_counts[regime] += 1
        sums["top"] += top
        sums["albedo"] += albedo
        sums["absorbed"] += absorbed
        sums["outgoing"] += outgoing
        sums["trapping"] += trapping
        sums["net"] += net
        sums["residual_abs"] += abs(residual_c)
        sums["stress"] += stress
        sums["seasonal_range"] += seasonal_range
        sums["orbital_variability"] += orbital_variability
        sums["peak"] += peak
        sums["low"] += low
        sums["orbital_factor"] += mean_orbital_factor
        high_stress_count += stress >= 0.65

    seen_cell_ids: set[int] = set()
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            _record_violation(violations, f"energy record[{index}] is not an object")
            continue
        missing = required_fields - set(record)
        if missing:
            _record_violation(
                violations,
                f"energy record[{index}] is missing fields: {', '.join(sorted(missing))}",
            )
            continue
        record_id = _integer(record.get("id"))
        cell_id = _integer(record.get("cell_id"))
        if record_id != index:
            _record_violation(violations, f"energy record[{index}] id is not sequential")
        if cell_id is None or cell_id in seen_cell_ids:
            _record_violation(
                violations, f"energy record[{index}] has invalid or duplicate cell_id"
            )
            continue
        seen_cell_ids.add(cell_id)
        cell = cells_by_id.get(cell_id)
        expected = expected_by_cell.get(cell_id)
        if cell is None or expected is None:
            _record_violation(
                violations, f"energy record[{index}] does not reference a valid cell"
            )
            continue
        if record.get("biome") != str(cell.get("biome", "unknown")):
            _record_violation(violations, f"energy record[{index}] biome is stale")
        if record.get("water_body_type") != str(
            cell.get("water_body_type", "land")
        ):
            _record_violation(
                violations, f"energy record[{index}] water body type is stale"
            )
        if record.get("surface_albedo_regime") != expected["surface_albedo_regime"]:
            _record_violation(
                violations, f"energy record[{index}] albedo regime is inconsistent"
            )

        monthly = record.get("monthly_top_of_atmosphere_insolation_w_m2")
        expected_monthly = expected["monthly_top_of_atmosphere_insolation_w_m2"]
        if (
            not isinstance(monthly, list)
            or len(monthly) != month_count
            or any(not _finite_number(value) or float(value) < 0.0 for value in monthly)
        ):
            _record_violation(
                violations, f"energy record[{index}] monthly insolation is invalid"
            )
        else:
            for actual, expected_value in zip(monthly, expected_monthly):
                residual = abs(float(actual) - float(expected_value))
                maximum_equation_residual = max(
                    maximum_equation_residual, residual
                )
                if not _close(actual, expected_value, absolute=1.1e-6, relative=0.0):
                    _record_violation(
                        violations,
                        f"energy record[{index}] monthly insolation does not replay",
                    )
                    break

        for field, expected_value in expected.items():
            if field in {
                "monthly_top_of_atmosphere_insolation_w_m2",
                "surface_albedo_regime",
            }:
                continue
            residual = (
                math.inf
                if _number(record.get(field)) is None
                else abs(float(record[field]) - float(expected_value))
            )
            maximum_equation_residual = max(maximum_equation_residual, residual)
            if not _close(
                record.get(field), expected_value, absolute=1.1e-6, relative=0.0
            ):
                _record_violation(
                    violations, f"energy record[{index}] {field} does not replay"
                )

        nonnegative_fields = (
            "top_of_atmosphere_insolation_w_m2",
            "seasonal_insolation_range_w_m2",
            "peak_seasonal_insolation_w_m2",
            "low_seasonal_insolation_w_m2",
            "absorbed_shortwave_w_m2",
            "outgoing_longwave_w_m2",
            "greenhouse_trapping_w_m2",
        )
        if any(
            _number(record.get(field)) is None or float(record[field]) < 0.0
            for field in nonnegative_fields
        ):
            _record_violation(
                violations, f"energy record[{index}] contains negative energy flux"
            )
        for field in (
            "surface_albedo_index",
            "orbital_insolation_variability_index",
            "climate_energy_stress_index",
        ):
            value = _number(record.get(field))
            if value is None or not 0.0 <= value <= 1.0:
                _record_violation(
                    violations, f"energy record[{index}] {field} is out of range"
                )

        cell_mirrors = {
            "top_of_atmosphere_insolation_w_m2": "top_of_atmosphere_insolation_w_m2",
            "surface_albedo_index": "surface_albedo_index",
            "absorbed_shortwave_w_m2": "absorbed_shortwave_w_m2",
            "outgoing_longwave_w_m2": "outgoing_longwave_w_m2",
            "greenhouse_trapping_w_m2": "greenhouse_trapping_w_m2",
            "net_radiative_balance_w_m2": "net_radiative_balance_w_m2",
            "no_greenhouse_equilibrium_temperature_c": "no_greenhouse_equilibrium_temperature_c",
            "radiative_equilibrium_temperature_c": "radiative_equilibrium_temperature_c",
            "energy_balance_residual_c": "energy_balance_residual_c",
            "climate_energy_stress_index": "climate_energy_stress_index",
            "seasonal_insolation_range_w_m2": "seasonal_insolation_range_w_m2",
            "orbital_insolation_variability_index": "orbital_insolation_variability_index",
            "peak_seasonal_insolation_w_m2": "peak_seasonal_insolation_w_m2",
            "low_seasonal_insolation_w_m2": "low_seasonal_insolation_w_m2",
        }
        for cell_field, expected_field in cell_mirrors.items():
            if not _close(
                cell.get(cell_field),
                expected[expected_field],
                absolute=1.1e-6,
                relative=0.0,
            ):
                _record_violation(
                    violations,
                    f"cell {cell_id} {cell_field} does not mirror the replay",
                )
        if cell.get("surface_albedo_regime") != expected["surface_albedo_regime"]:
            _record_violation(
                violations, f"cell {cell_id} surface_albedo_regime is inconsistent"
            )

    if seen_cell_ids != set(cells_by_id):
        _record_violation(
            violations,
            "energy records do not provide exactly one record for every cell",
        )

    cell_count = len(cells_by_id)
    divisor = max(1, cell_count)
    expected_summary = {
        "climate_energy_balance_record_count": len(records),
        "mean_top_of_atmosphere_insolation_w_m2": sums["top"] / divisor,
        "mean_surface_albedo_index": sums["albedo"] / divisor,
        "mean_absorbed_shortwave_w_m2": sums["absorbed"] / divisor,
        "mean_outgoing_longwave_w_m2": sums["outgoing"] / divisor,
        "mean_greenhouse_trapping_w_m2": sums["trapping"] / divisor,
        "mean_net_radiative_balance_w_m2": sums["net"] / divisor,
        "mean_abs_energy_balance_residual_c": sums["residual_abs"] / divisor,
        "mean_climate_energy_stress_index": sums["stress"] / divisor,
        "mean_seasonal_insolation_range_w_m2": sums["seasonal_range"] / divisor,
        "mean_orbital_insolation_variability_index": sums[
            "orbital_variability"
        ]
        / divisor,
        "mean_peak_seasonal_insolation_w_m2": sums["peak"] / divisor,
        "mean_low_seasonal_insolation_w_m2": sums["low"] / divisor,
        "mean_orbital_distance_factor": sums["orbital_factor"] / divisor,
        "orbital_eccentricity": eccentricity,
        "high_climate_energy_stress_cell_count": high_stress_count,
    }
    for field, expected in expected_summary.items():
        if field in {
            "climate_energy_balance_record_count",
            "high_climate_energy_stress_cell_count",
        }:
            if _integer(summary.get(field)) != expected:
                _record_violation(
                    violations, f"summary {field} does not mirror energy records"
                )
        elif not _close(summary.get(field), expected, absolute=1.1e-6, relative=0.0):
            _record_violation(
                violations, f"summary {field} does not mirror the energy replay"
            )
    if summary.get("surface_albedo_regime_counts") != dict(
        sorted(regime_counts.items())
    ):
        _record_violation(
            violations, "summary surface_albedo_regime_counts is inconsistent"
        )

    _append_check(
        checks,
        domain="climate",
        name="climate_energy_balance_replay",
        passed=not violations,
        message=(
            "each cell's monthly insolation, albedo, greenhouse, longwave, net "
            "balance, stress, cell mirrors, and global aggregates must replay the producer equations"
        ),
        observed={
            "cell_count": len(cells),
            "record_count": len(records),
            "month_count": month_count,
            "unique_recorded_cell_count": len(seen_cell_ids),
            "violation_count": len(violations),
            "maximum_equation_residual": maximum_equation_residual,
        },
        expected={
            "record_count": len(cells),
            "unique_recorded_cell_count": len(cells),
            "monthly_values_per_record": month_count,
            "equations_and_summary_match": True,
        },
        evidence={"violations": violations},
    )


FEEDBACK_BOOLEAN_FIELDS = frozenset(
    {
        "sea_level_recomputed",
        "climate_recomputed",
        "hydrologic_water_budget_recomputed",
        "hydrology_recomputed",
        "erosion_applied",
        "cryosphere_applied",
        "plate_motion_applied",
        "crust_transport_applied",
        "crust_evolution_applied",
    }
)

FEEDBACK_COUNT_FIELDS = frozenset(
    {
        "sea_level_recompute_count",
        "climate_recompute_count",
        "hydrologic_water_budget_recompute_count",
        "hydrology_recompute_count",
        "numeric_depression_fill_pass_count",
        "numeric_depression_fill_event_count",
        "numeric_depression_fill_cell_application_count",
        "numeric_depression_filled_unique_cell_count",
        "numeric_depression_correction_event_count",
        "numeric_depression_breach_selected_event_count",
        "numeric_depression_breach_excavation_cell_application_count",
        "numeric_depression_breach_deposition_cell_application_count",
        "numeric_depression_temporary_lake_event_count",
        "numeric_depression_temporary_lake_cell_application_count",
        "numeric_depression_temporary_lake_unique_cell_count",
        "fluvial_sediment_active_cell_step_count",
        "fluvial_sediment_routed_edge_count",
        "fluvial_sediment_land_terminal_count",
        "fluvial_sediment_marine_terminal_count",
        "fluvial_sediment_terminal_allocation_count",
        "hillslope_sediment_transport_edge_count",
        "hillslope_sediment_source_cell_count",
        "hillslope_sediment_target_cell_count",
        "hillslope_sediment_land_to_land_edge_count",
        "hillslope_sediment_land_to_marine_edge_count",
        "glacial_sediment_transfer_count",
        "glacial_sediment_source_cell_count",
        "glacial_sediment_target_cell_count",
        "glacial_sediment_land_target_transfer_count",
        "glacial_sediment_marine_target_transfer_count",
        "cell_count",
        "land_cell_count",
        "water_cell_count",
        "river_cell_count",
    }
)

FEEDBACK_VALUE_FIELDS = frozenset(
    {
        "sea_level_adjustment_m",
        "numeric_depression_fill_area_km2",
        "numeric_depression_fill_volume_km3",
        "max_numeric_depression_fill_depth_m",
        "numeric_depression_breach_excavation_volume_km3",
        "numeric_depression_breach_deposition_volume_km3",
        "numeric_depression_correction_mass_balance_residual_km3",
        "numeric_depression_temporary_lake_candidate_area_km2",
        "numeric_depression_temporary_lake_candidate_volume_km3",
        "max_numeric_depression_temporary_lake_depth_m",
        "fluvial_sediment_local_source_volume_km3",
        "fluvial_sediment_routed_throughput_volume_km3",
        "fluvial_sediment_capacity_deposition_volume_km3",
        "fluvial_sediment_depression_fill_deposition_volume_km3",
        "fluvial_sediment_lake_trap_deposition_volume_km3",
        "fluvial_sediment_terminal_land_deposition_volume_km3",
        "fluvial_sediment_marine_deposition_volume_km3",
        "fluvial_sediment_terminal_export_volume_km3",
        "fluvial_sediment_mass_balance_residual_km3",
        "hillslope_sediment_production_volume_km3",
        "hillslope_sediment_deposition_volume_km3",
        "hillslope_sediment_mass_balance_residual_km3",
        "max_hillslope_sediment_source_production_depth_m",
        "max_hillslope_sediment_target_deposition_depth_m",
        "mean_hillslope_effective_diffusivity",
        "glacial_sediment_production_volume_km3",
        "glacial_sediment_deposition_volume_km3",
        "glacial_sediment_mass_balance_residual_km3",
        "glacial_sediment_terrain_volume_change_residual_km3",
        "max_glacial_sediment_source_production_depth_m",
        "max_glacial_sediment_target_deposition_depth_m",
        "sediment_alluvium_entrainment_volume_km3",
        "sediment_bedrock_erosion_volume_km3",
        "sediment_inventory_volume_km3",
        "sediment_source_partition_residual_km3",
        "sediment_inventory_mass_balance_residual_km3",
        "surface_area_km2",
        "ocean_area_km2",
        "ocean_volume_km3",
        "ocean_fraction",
        "mean_elevation_m",
        "mean_land_elevation_m",
        "min_elevation_m",
        "max_elevation_m",
        "mean_temperature_c",
        "mean_precipitation_mm_y",
        "mean_runoff_mm_y",
        "hydrologic_land_precipitation_volume_km3_y",
        "hydrologic_actual_evapotranspiration_volume_km3_y",
        "hydrologic_infiltration_volume_km3_y",
        "hydrologic_runoff_volume_km3_y",
        "hydrologic_water_budget_residual_km3_y",
        "max_abs_hydrologic_water_budget_cell_residual_mm_y",
        "mean_erosion_rate_m_per_step",
        "mean_sediment_thickness_m",
        "mean_cumulative_sediment_production_m",
        "mean_cumulative_sediment_deposition_m",
        "mean_cumulative_sediment_export_m",
        "cumulative_sediment_production_volume_km3",
        "cumulative_sediment_deposition_volume_km3",
        "cumulative_sediment_export_volume_km3",
        "mean_abs_elevation_change_m_from_previous_stage",
        "mean_abs_temperature_change_c_from_previous_stage",
        "mean_abs_precipitation_change_mm_y_from_previous_stage",
        "mean_abs_runoff_change_mm_y_from_previous_stage",
    }
)

FEEDBACK_REQUIRED_FIELDS = frozenset(
    {"id", "stage", "erosion_iteration", "plate_motion_history_id"}
) | FEEDBACK_BOOLEAN_FIELDS | FEEDBACK_COUNT_FIELDS | FEEDBACK_VALUE_FIELDS


def _feedback_close(actual: Any, expected: float) -> bool:
    return _close(actual, expected, absolute=0.01, relative=2.0e-4)


def _validate_feedback_structure(
    world: dict[str, Any], checks: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    clock = world.get("simulation_clock")
    history = world.get("earth_system_feedback_history")
    cells = world.get("cells")
    motion_history = world.get("plate_motion_history")
    violations: list[str] = []

    clock_required = {
        "clock_type",
        "time_unit",
        "physical_time_resolved",
        "clock_limitation",
        "iteration_process_order",
        "geological_age_ga",
        "configured_erosion_iteration_count",
        "configured_cryosphere_coupling_stage_count",
        "cryosphere_coupling_stage_count",
        "feedback_recompute_count",
        "hydrologic_water_budget_recompute_count",
        "stage_count",
        "initial_stage_id",
        "current_stage_id",
        "final_stage_id",
        "final_cryosphere_stage_id",
    }
    if not isinstance(clock, dict):
        _record_violation(violations, "simulation_clock must be an object")
        clock = {}
    else:
        missing = clock_required - set(clock)
        if missing:
            _record_violation(
                violations,
                f"simulation_clock is missing fields: {', '.join(sorted(missing))}",
            )
    if not isinstance(history, list) or not all(
        isinstance(step, dict) for step in history
    ):
        _record_violation(
            violations, "earth_system_feedback_history must be a list of objects"
        )
        history = []
    if not isinstance(cells, list) or not all(isinstance(cell, dict) for cell in cells):
        _record_violation(violations, "cells must be a list of objects")
        cells = []
    if not isinstance(motion_history, list) or not all(
        isinstance(step, dict) for step in motion_history
    ):
        _record_violation(violations, "plate_motion_history must be a list of objects")
        motion_history = []

    erosion_iterations = _integer(clock.get("configured_erosion_iteration_count"))
    configured_cryo = _integer(
        clock.get("configured_cryosphere_coupling_stage_count")
    )
    cryo_count = _integer(clock.get("cryosphere_coupling_stage_count"))
    stage_count = _integer(clock.get("stage_count"))
    expected_stage_count = (
        erosion_iterations + 2 if erosion_iterations is not None else None
    )
    final_id = len(history) - 1
    if (
        clock.get("clock_type") != "coupled_geodynamic_stage_clock_v11"
        or clock.get("time_unit") != "model_step"
        or clock.get("physical_time_resolved") is not False
        or clock.get("clock_limitation")
        != "ordered_process_stages_without_calibrated_physical_duration"
        or not isinstance(clock.get("iteration_process_order"), str)
        or not clock.get("iteration_process_order")
    ):
        _record_violation(violations, "simulation clock metadata is invalid")
    clock_age = _number(clock.get("geological_age_ga"))
    planet_age = _planet_value(world, "geological_age_ga", 4.5)
    if clock_age is None or clock_age < 0.0 or not _close(
        clock_age, planet_age, absolute=1.0e-6, relative=0.0
    ):
        _record_violation(
            violations, "simulation clock geological age does not mirror the planet"
        )
    if erosion_iterations is None or erosion_iterations < 0:
        _record_violation(violations, "configured erosion iteration count is invalid")
    if configured_cryo != 1 or cryo_count != 1:
        _record_violation(violations, "cryosphere stage count must be exactly one")
    if stage_count != expected_stage_count or len(history) != expected_stage_count:
        _record_violation(
            violations, "feedback history length does not match configured stages"
        )
    expected_clock_ids = {
        "initial_stage_id": 0,
        "current_stage_id": final_id,
        "final_stage_id": final_id,
        "final_cryosphere_stage_id": final_id,
    }
    for field, expected in expected_clock_ids.items():
        if _integer(clock.get(field)) != expected:
            _record_violation(violations, f"simulation clock {field} is inconsistent")
    if erosion_iterations is not None and len(motion_history) != erosion_iterations + 1:
        _record_violation(
            violations, "plate motion history length does not match erosion stages"
        )

    previous_sediment = (0.0, 0.0, 0.0)
    for index, step in enumerate(history):
        missing = FEEDBACK_REQUIRED_FIELDS - set(step)
        if missing:
            _record_violation(
                violations,
                f"feedback step[{index}] is missing fields: {', '.join(sorted(missing))}",
            )
            continue
        if _integer(step.get("id")) != index:
            _record_violation(violations, f"feedback step[{index}] id is not sequential")
        if any(type(step.get(field)) is not bool for field in FEEDBACK_BOOLEAN_FIELDS):
            _record_violation(
                violations, f"feedback step[{index}] has non-boolean process flags"
            )
        invalid_counts = [
            field
            for field in FEEDBACK_COUNT_FIELDS
            if _integer(step.get(field)) is None or int(step[field]) < 0
        ]
        if invalid_counts:
            _record_violation(
                violations, f"feedback step[{index}] has invalid count fields"
            )
        if any(not _finite_number(step.get(field)) for field in FEEDBACK_VALUE_FIELDS):
            _record_violation(
                violations, f"feedback step[{index}] has non-finite numeric fields"
            )

        is_initial = index == 0
        is_erosion = (
            erosion_iterations is not None and 1 <= index <= erosion_iterations
        )
        is_cryo = index == final_id and not is_initial
        expected_stage = (
            "initial_climate_hydrology"
            if is_initial
            else ("erosion_iteration" if is_erosion else "cryosphere_coupling")
        )
        expected_iteration = index if is_erosion else -1
        expected_motion_id = index if is_erosion else (0 if is_initial else max(0, index - 1))
        if step.get("stage") != expected_stage:
            _record_violation(violations, f"feedback step[{index}] stage is invalid")
        if _integer(step.get("erosion_iteration")) != expected_iteration:
            _record_violation(
                violations, f"feedback step[{index}] erosion_iteration is invalid"
            )
        if _integer(step.get("plate_motion_history_id")) != expected_motion_id:
            _record_violation(
                violations, f"feedback step[{index}] plate motion link is invalid"
            )
        expected_flags = {
            "erosion_applied": is_erosion,
            "cryosphere_applied": is_cryo,
            "plate_motion_applied": is_erosion,
            "crust_transport_applied": is_erosion,
            "crust_evolution_applied": is_erosion,
        }
        for field, expected in expected_flags.items():
            if step.get(field) is not expected:
                _record_violation(
                    violations, f"feedback step[{index}] {field} is inconsistent"
                )

        recompute_fields = (
            "sea_level_recompute_count",
            "climate_recompute_count",
            "hydrologic_water_budget_recompute_count",
            "hydrology_recompute_count",
        )
        recompute_counts = [_integer(step.get(field)) for field in recompute_fields]
        if (
            any(value is None or value <= 0 for value in recompute_counts)
            or len(set(recompute_counts)) != 1
        ):
            _record_violation(
                violations, f"feedback step[{index}] recompute counts are inconsistent"
            )
        for boolean_field, count_field in (
            ("sea_level_recomputed", "sea_level_recompute_count"),
            ("climate_recomputed", "climate_recompute_count"),
            (
                "hydrologic_water_budget_recomputed",
                "hydrologic_water_budget_recompute_count",
            ),
            ("hydrology_recomputed", "hydrology_recompute_count"),
        ):
            count = _integer(step.get(count_field))
            if step.get(boolean_field) is not (count is not None and count > 0):
                _record_violation(
                    violations,
                    f"feedback step[{index}] {boolean_field} does not mirror its count",
                )
        fill_passes = _integer(step.get("numeric_depression_fill_pass_count"))
        hydrology_recomputes = _integer(step.get("hydrology_recompute_count"))
        if (
            fill_passes is not None
            and hydrology_recomputes is not None
            and hydrology_recomputes != fill_passes + 1
        ):
            _record_violation(
                violations,
                f"feedback step[{index}] hydrology/fill pass counts are inconsistent",
            )
        cell_count = _integer(step.get("cell_count"))
        land_count = _integer(step.get("land_cell_count"))
        water_count = _integer(step.get("water_cell_count"))
        river_count = _integer(step.get("river_cell_count"))
        if (
            cell_count is not None
            and land_count is not None
            and water_count is not None
            and cell_count != land_count + water_count
        ):
            _record_violation(
                violations, f"feedback step[{index}] land/water counts do not close"
            )
        if (
            river_count is not None
            and cell_count is not None
            and river_count > cell_count
        ):
            _record_violation(
                violations, f"feedback step[{index}] river count exceeds cells"
            )

        if is_initial:
            for field in (
                "mean_abs_elevation_change_m_from_previous_stage",
                "mean_abs_temperature_change_c_from_previous_stage",
                "mean_abs_precipitation_change_mm_y_from_previous_stage",
                "mean_abs_runoff_change_mm_y_from_previous_stage",
            ):
                if not _close(step.get(field), 0.0, absolute=0.001, relative=0.0):
                    _record_violation(
                        violations, f"initial feedback step {field} must be zero"
                    )

        sediment = tuple(
            float(step.get(field, math.nan))
            for field in (
                "cumulative_sediment_production_volume_km3",
                "cumulative_sediment_deposition_volume_km3",
                "cumulative_sediment_export_volume_km3",
            )
        )
        if all(math.isfinite(value) and value >= 0.0 for value in sediment):
            if any(
                current + 0.01 < previous
                for current, previous in zip(sediment, previous_sediment)
            ):
                _record_violation(
                    violations,
                    f"feedback step[{index}] cumulative sediment regresses",
                )
            if abs(sediment[0] - sediment[1] - sediment[2]) > max(
                0.01, sediment[0] * 1.0e-6
            ):
                _record_violation(
                    violations,
                    f"feedback step[{index}] cumulative sediment mass does not close",
                )
            previous_sediment = sediment
        else:
            _record_violation(
                violations, f"feedback step[{index}] cumulative sediment is invalid"
            )

    # Replay the final state fields that remain unchanged by natural enrichers.
    if history and cells:
        final = history[-1]
        try:
            cell_count = len(cells)
            land = [cell for cell in cells if not bool(cell.get("is_water", False))]
            surface_area = sum(float(cell["area_km2"]) for cell in cells)
            ocean_area = sum(
                float(cell["area_km2"])
                for cell in cells
                if bool(cell.get("is_water", False))
            )
            ocean_volume = sum(
                float(cell["area_km2"])
                * max(0.0, float(cell.get("water_depth_m", 0.0)))
                / 1000.0
                for cell in cells
                if bool(cell.get("is_water", False))
            )
            divisor = max(1, cell_count)
            expected_final: dict[str, float | int] = {
                "cell_count": cell_count,
                "land_cell_count": len(land),
                "water_cell_count": cell_count - len(land),
                "river_cell_count": sum(
                    bool(cell.get("is_river", False)) for cell in cells
                ),
                "surface_area_km2": surface_area,
                "ocean_area_km2": ocean_area,
                "ocean_volume_km3": ocean_volume,
                "ocean_fraction": ocean_area / max(1.0, surface_area),
                "mean_elevation_m": sum(
                    float(cell.get("elevation_m", 0.0)) for cell in cells
                )
                / divisor,
                "mean_land_elevation_m": sum(
                    float(cell.get("elevation_m", 0.0)) for cell in land
                )
                / max(1, len(land)),
                "min_elevation_m": min(
                    (float(cell.get("elevation_m", 0.0)) for cell in cells),
                    default=0.0,
                ),
                "max_elevation_m": max(
                    (float(cell.get("elevation_m", 0.0)) for cell in cells),
                    default=0.0,
                ),
                "mean_temperature_c": sum(
                    float(cell.get("temperature_c", 0.0)) for cell in cells
                )
                / divisor,
                "mean_precipitation_mm_y": sum(
                    float(cell.get("precipitation_mm_y", 0.0)) for cell in cells
                )
                / divisor,
                "mean_runoff_mm_y": sum(
                    float(cell.get("runoff_mm_y", 0.0)) for cell in cells
                )
                / divisor,
                "mean_erosion_rate_m_per_step": sum(
                    float(cell.get("erosion_rate", 0.0)) for cell in cells
                )
                / divisor,
                "mean_sediment_thickness_m": sum(
                    float(cell.get("sediment_thickness_m", 0.0)) for cell in cells
                )
                / divisor,
                "mean_cumulative_sediment_production_m": sum(
                    float(cell.get("sediment_production_m", 0.0)) for cell in cells
                )
                / divisor,
                "mean_cumulative_sediment_deposition_m": sum(
                    float(cell.get("sediment_deposition_m", 0.0)) for cell in cells
                )
                / divisor,
                "mean_cumulative_sediment_export_m": sum(
                    float(cell.get("sediment_export_m", 0.0)) for cell in cells
                )
                / divisor,
                "cumulative_sediment_production_volume_km3": sum(
                    float(cell.get("sediment_production_m", 0.0))
                    * float(cell.get("area_km2", 0.0))
                    / 1000.0
                    for cell in cells
                ),
                "cumulative_sediment_deposition_volume_km3": sum(
                    float(cell.get("sediment_deposition_m", 0.0))
                    * float(cell.get("area_km2", 0.0))
                    / 1000.0
                    for cell in cells
                ),
                "cumulative_sediment_export_volume_km3": sum(
                    float(cell.get("sediment_export_m", 0.0))
                    * float(cell.get("area_km2", 0.0))
                    / 1000.0
                    for cell in cells
                ),
            }
        except (KeyError, TypeError, ValueError, OverflowError):
            _record_violation(violations, "final cells contain invalid replay fields")
            expected_final = {}
        precision = 4
        world_summary = world.get("summary")
        if isinstance(world_summary, dict):
            candidate_precision = _integer(world_summary.get("output_float_precision"))
            if candidate_precision is not None and 0 <= candidate_precision <= 8:
                precision = candidate_precision
        sediment_volume_tolerance = max(
            0.01, surface_area * 0.5001 * 10.0 ** (-precision) / 1000.0
        ) if expected_final else 0.01
        integer_final_fields = {
            "cell_count",
            "land_cell_count",
            "water_cell_count",
            "river_cell_count",
        }
        for field, expected in expected_final.items():
            if field in integer_final_fields:
                valid = _integer(final.get(field)) == int(expected)
            elif field in {
                "cumulative_sediment_production_volume_km3",
                "cumulative_sediment_deposition_volume_km3",
                "cumulative_sediment_export_volume_km3",
            }:
                valid = _close(
                    final.get(field),
                    expected,
                    absolute=sediment_volume_tolerance,
                    relative=0.0,
                )
            elif field in {"surface_area_km2", "ocean_area_km2", "ocean_volume_km3"}:
                valid = _close(
                    final.get(field), expected, absolute=0.02, relative=1.0e-9
                )
            else:
                valid = _feedback_close(final.get(field), expected)
            if not valid:
                _record_violation(
                    violations, f"final feedback {field} does not replay from cells"
                )

    _append_check(
        checks,
        domain="simulation",
        name="coupled_stage_feedback_replay",
        passed=not violations,
        message=(
            "the simulation clock and every complete feedback stage must follow the "
            "configured initial/erosion/cryosphere sequence and the final stage must replay from cells"
        ),
        observed={
            "configured_erosion_iteration_count": erosion_iterations,
            "clock_stage_count": stage_count,
            "feedback_record_count": len(history),
            "plate_motion_record_count": len(motion_history),
            "violation_count": len(violations),
        },
        expected={
            "feedback_record_count": expected_stage_count,
            "plate_motion_record_count": (
                erosion_iterations + 1 if erosion_iterations is not None else None
            ),
            "complete_stage_records": True,
            "final_stage_matches_cells": True,
        },
        evidence={"violations": violations},
    )
    return history, clock, violations


def _validate_feedback_summary(
    world: dict[str, Any],
    history: list[dict[str, Any]],
    clock: dict[str, Any],
    checks: list[dict[str, Any]],
) -> None:
    summary = world.get("summary")
    violations: list[str] = []
    if not isinstance(summary, dict):
        _record_violation(violations, "summary must be an object")
        summary = {}

    erosion_steps = [
        step for step in history if step.get("erosion_applied") is True
    ]
    cryosphere_steps = [
        step for step in history if step.get("cryosphere_applied") is True
    ]
    count_mirrors = {
        "simulation_clock_stage_count": len(history),
        "simulation_clock_erosion_iteration_count": len(erosion_steps),
        "simulation_clock_cryosphere_coupling_stage_count": len(
            cryosphere_steps
        ),
        "simulation_clock_sea_level_recompute_count": sum(
            _integer(step.get("sea_level_recompute_count")) or 0
            for step in history
        ),
        "simulation_clock_climate_recompute_count": sum(
            _integer(step.get("climate_recompute_count")) or 0
            for step in history
        ),
        "simulation_clock_hydrologic_water_budget_recompute_count": sum(
            _integer(step.get("hydrologic_water_budget_recompute_count")) or 0
            for step in history
        ),
        "simulation_clock_hydrology_recompute_count": sum(
            _integer(step.get("hydrology_recompute_count")) or 0
            for step in history
        ),
    }
    for field, expected in count_mirrors.items():
        if _integer(summary.get(field)) != expected:
            _record_violation(
                violations, f"summary {field} does not mirror feedback history"
            )

    final = history[-1] if history else {}
    try:
        value_mirrors = {
            "mean_erosion_iteration_elevation_change_m": sum(
                float(step["mean_abs_elevation_change_m_from_previous_stage"])
                for step in erosion_steps
            )
            / max(1, len(erosion_steps)),
            "total_feedback_mean_abs_elevation_change_m": sum(
                float(step["mean_abs_elevation_change_m_from_previous_stage"])
                for step in history
            ),
            "final_feedback_mean_abs_temperature_change_c": float(
                final.get("mean_abs_temperature_change_c_from_previous_stage", 0.0)
            ),
            "final_feedback_mean_abs_precipitation_change_mm_y": float(
                final.get(
                    "mean_abs_precipitation_change_mm_y_from_previous_stage", 0.0
                )
            ),
            "final_feedback_mean_abs_runoff_change_mm_y": float(
                final.get("mean_abs_runoff_change_mm_y_from_previous_stage", 0.0)
            ),
        }
    except (KeyError, TypeError, ValueError, OverflowError):
        _record_violation(violations, "feedback summary inputs are non-numeric")
        value_mirrors = {}
    for field, expected in value_mirrors.items():
        if not math.isfinite(expected) or not _feedback_close(
            summary.get(field), expected
        ):
            _record_violation(
                violations, f"summary {field} does not mirror feedback history"
            )

    recomputed_feedback_count = sum(
        (step.get("erosion_applied") is True or step.get("cryosphere_applied") is True)
        and step.get("sea_level_recomputed") is True
        and step.get("climate_recomputed") is True
        and step.get("hydrologic_water_budget_recomputed") is True
        and step.get("hydrology_recomputed") is True
        for step in history
    )
    if _integer(clock.get("feedback_recompute_count")) != recomputed_feedback_count:
        _record_violation(
            violations, "clock feedback_recompute_count does not mirror stages"
        )
    if _integer(clock.get("hydrologic_water_budget_recompute_count")) != count_mirrors[
        "simulation_clock_hydrologic_water_budget_recompute_count"
    ]:
        _record_violation(
            violations,
            "clock hydrologic water-budget recompute count does not mirror stages",
        )

    _append_check(
        checks,
        domain="simulation",
        name="coupled_stage_summary_mirrors",
        passed=not violations,
        message=(
            "simulation-clock counters and summary feedback metrics must be "
            "reconstructed from the exported stage history"
        ),
        observed={
            "summary_count_mirrors": {
                field: summary.get(field) for field in count_mirrors
            },
            "clock_feedback_recompute_count": clock.get(
                "feedback_recompute_count"
            ),
            "violation_count": len(violations),
        },
        expected={
            "summary_count_mirrors": count_mirrors,
            "clock_feedback_recompute_count": recomputed_feedback_count,
        },
        evidence={"violations": violations},
    )


def validate_physics_replays(world: dict[str, Any]) -> list[dict[str, Any]]:
    """Deeply replay natural-system physical aggregate and stage diagnostics.

    The helper intentionally has no dependency on the top-level geo validator so
    it can be composed there or exercised independently.  Malformed payloads are
    reported as failed checks instead of propagating conversion errors.
    """

    checks: list[dict[str, Any]] = []
    if not isinstance(world, dict):
        world = {}
    _validate_plate_aggregates(world, checks)
    _validate_climate_energy(world, checks)
    history, clock, _ = _validate_feedback_structure(world, checks)
    _validate_feedback_summary(world, history, clock, checks)
    return checks


__all__ = ["validate_physics_replays"]
