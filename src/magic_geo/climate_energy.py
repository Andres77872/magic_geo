from __future__ import annotations

import math
from collections import Counter
from typing import Any


SOLAR_CONSTANT_W_M2 = 1361.0
STEFAN_BOLTZMANN_W_M2_K4 = 5.670374419e-8
SURFACE_LONGWAVE_EMISSIVITY = 0.96


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _planet_value(planet: Any | None, key: str, default: float) -> float:
    if planet is None:
        return default
    if isinstance(planet, dict):
        raw = planet.get(key, default)
    else:
        raw = getattr(planet, key, default)
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


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
            base = 0.10
            regime = "lake_water"
        elif water_body == "continental_shelf":
            base = 0.08
            regime = "shallow_ocean"
        else:
            base = 0.065
            regime = "open_ocean"
    elif ice > 20.0 or biome == "ice_cap":
        base = 0.58 + _clamp(ice / 2500.0) * 0.12
        regime = "ice_albedo"
    elif biome in {"tundra", "alpine"}:
        base = 0.34 if temperature < -2.0 else 0.28
        regime = "cold_sparse_cover"
    elif biome in {"hot_desert", "cold_desert"}:
        base = 0.36 if biome == "hot_desert" else 0.32
        regime = "arid_high_albedo"
    elif biome in {"savanna", "temperate_grassland", "mediterranean_scrub"}:
        base = 0.21
        regime = "seasonal_grassland"
    elif "forest" in biome:
        base = 0.14 if biome != "tropical_rainforest" else 0.12
        regime = "forest_canopy"
    else:
        base = 0.22
        regime = "mixed_land"

    air_scattering = 0.055
    cloud_albedo = _clamp(precipitation / 2800.0) * 0.055 + max(0.0, float(cell.get("vertical_velocity_index", 0.0))) * 0.018
    dry_brightening = seasonal_aridity * (0.035 if not bool(cell.get("is_water", False)) else 0.0)
    snow_brightening = 0.08 if not bool(cell.get("is_water", False)) and temperature < -3.0 and precipitation >= 250.0 else 0.0
    elevation_brightening = _clamp((elevation - 2600.0) / 2600.0) * 0.035 if elevation > 2600.0 else 0.0
    return _clamp(base + air_scattering + cloud_albedo + dry_brightening + snow_brightening + elevation_brightening, 0.04, 0.86), regime


def _greenhouse_effect_c(cell: dict[str, Any], greenhouse_factor: float, pressure_bar: float) -> float:
    humidity = _clamp(
        float(cell.get("humidity_transport_index", 0.0)) * 0.35
        + (float(cell.get("ocean_current_moisture_factor", 1.0)) - 0.72) / 0.56 * 0.25
        + _clamp(float(cell.get("precipitation_mm_y", 0.0)) / 2600.0) * 0.25
        + _clamp(float(cell.get("vapor_evaporation_mm_y", 0.0)) / 1500.0) * 0.15
    )
    dry_penalty = _clamp(float(cell.get("seasonal_aridity_index", 0.0))) * 2.5
    ice_penalty = _clamp(float(cell.get("ice_thickness_m", 0.0)) / 1800.0) * 3.0
    water_bonus = 1.5 if bool(cell.get("is_water", False)) else 0.0
    pressure_scale = math.sqrt(max(0.0, pressure_bar))
    return max(0.0, (13.5 + humidity * 8.0 + water_bonus - dry_penalty - ice_penalty) * greenhouse_factor * pressure_scale)


def _seasonal_insolation_series(
    lat_rad: float,
    stellar_luminosity: float,
    axial_tilt_deg: float,
    orbital_eccentricity: float,
    months: int,
) -> tuple[list[float], list[float]]:
    eccentricity = _clamp(orbital_eccentricity, 0.0, 0.8)
    tilt_rad = math.radians(_clamp(axial_tilt_deg, 0.0, 90.0))
    tilt_contrast = 1.0 + (_clamp(axial_tilt_deg, 0.0, 90.0) / 90.0 - 23.5 / 90.0) * 0.18
    latitude_factor = 0.46 + 0.72 * max(0.0, math.cos(lat_rad)) * tilt_contrast
    month_count = max(1, months)
    monthly: list[float] = []
    orbital_factors: list[float] = []
    for month in range(month_count):
        season_angle = 2.0 * math.pi * (float(month) - 5.5) / float(month_count)
        declination = tilt_rad * math.cos(season_angle)
        seasonal_latitude_factor = _clamp(1.0 + 0.65 * math.sin(lat_rad) * math.sin(declination), 0.08, 1.92)
        true_anomaly = 2.0 * math.pi * float(month) / float(month_count)
        orbital_distance_au = (1.0 - eccentricity * eccentricity) / max(0.02, 1.0 + eccentricity * math.cos(true_anomaly))
        orbital_factor = 1.0 / max(0.02, orbital_distance_au * orbital_distance_au)
        monthly.append(SOLAR_CONSTANT_W_M2 * stellar_luminosity * latitude_factor * seasonal_latitude_factor * orbital_factor / 4.0)
        orbital_factors.append(orbital_factor)
    return monthly, orbital_factors


def enrich_world_with_climate_energy_balance(world: dict[str, Any], planet: Any | None = None) -> dict[str, Any]:
    cells = world.get("cells", [])
    if not isinstance(cells, list) or not cells:
        return world

    stellar_luminosity = max(0.01, _planet_value(planet, "stellar_luminosity", 1.0))
    greenhouse_factor = max(0.0, _planet_value(planet, "greenhouse_factor", 1.0))
    pressure_bar = max(0.0, _planet_value(planet, "atmosphere_pressure_bar", 1.0))
    axial_tilt_degrees = _clamp(_planet_value(planet, "axial_tilt_deg", 23.5), 0.0, 90.0)
    orbital_eccentricity = _clamp(_planet_value(planet, "orbital_eccentricity", 0.016), 0.0, 0.8)
    first_monthly_temperature = cells[0].get("temperature_monthly_c", [])
    month_count = len(first_monthly_temperature) if isinstance(first_monthly_temperature, list) else 12
    if month_count <= 0:
        month_count = 12

    records: list[dict[str, Any]] = []
    regime_counts: Counter[str] = Counter()
    insolation_sum = 0.0
    albedo_sum = 0.0
    absorbed_sum = 0.0
    outgoing_sum = 0.0
    greenhouse_sum = 0.0
    net_sum = 0.0
    residual_abs_sum = 0.0
    stress_sum = 0.0
    seasonal_insolation_range_sum = 0.0
    orbital_variability_sum = 0.0
    peak_insolation_sum = 0.0
    low_insolation_sum = 0.0
    orbital_distance_factor_sum = 0.0
    high_stress_count = 0

    for cell in cells:
        cell_id = int(cell.get("id", len(records)))
        lat_deg = float(cell.get("lat_deg", 0.0))
        lat_rad = math.radians(lat_deg)
        monthly_insolation, orbital_distance_factors = _seasonal_insolation_series(
            lat_rad,
            stellar_luminosity,
            axial_tilt_degrees,
            orbital_eccentricity,
            month_count,
        )
        top_of_atmosphere = sum(monthly_insolation) / len(monthly_insolation)
        peak_insolation = max(monthly_insolation)
        low_insolation = min(monthly_insolation)
        seasonal_range = peak_insolation - low_insolation
        orbital_variability = _clamp(seasonal_range / max(1.0, top_of_atmosphere))
        mean_orbital_distance_factor = sum(orbital_distance_factors) / len(orbital_distance_factors)
        albedo, regime = _surface_albedo(cell)
        absorbed = top_of_atmosphere * (1.0 - albedo)
        no_greenhouse_kelvin = (absorbed / STEFAN_BOLTZMANN_W_M2_K4) ** 0.25 if absorbed > 0.0 else 0.0
        no_greenhouse_c = no_greenhouse_kelvin - 273.15
        greenhouse_effect_c = _greenhouse_effect_c(cell, greenhouse_factor, pressure_bar)
        equilibrium_c = no_greenhouse_c + greenhouse_effect_c + float(cell.get("ocean_current_temperature_c", 0.0)) * 0.35
        observed_c = float(cell.get("temperature_c", 0.0))
        observed_kelvin = max(1.0, observed_c + 273.15)
        equilibrium_kelvin = max(1.0, equilibrium_c + 273.15)
        outgoing = SURFACE_LONGWAVE_EMISSIVITY * STEFAN_BOLTZMANN_W_M2_K4 * observed_kelvin**4
        equilibrium_longwave = SURFACE_LONGWAVE_EMISSIVITY * STEFAN_BOLTZMANN_W_M2_K4 * equilibrium_kelvin**4
        greenhouse_trapping = max(0.0, equilibrium_longwave - absorbed)
        net_balance = absorbed + greenhouse_trapping - outgoing
        residual_c = observed_c - equilibrium_c
        stress = _clamp(abs(residual_c) / 28.0 + abs(net_balance) / 220.0)

        cell["top_of_atmosphere_insolation_w_m2"] = round(top_of_atmosphere, 6)
        cell["surface_albedo_index"] = round(albedo, 6)
        cell["absorbed_shortwave_w_m2"] = round(absorbed, 6)
        cell["outgoing_longwave_w_m2"] = round(outgoing, 6)
        cell["greenhouse_trapping_w_m2"] = round(greenhouse_trapping, 6)
        cell["net_radiative_balance_w_m2"] = round(net_balance, 6)
        cell["no_greenhouse_equilibrium_temperature_c"] = round(no_greenhouse_c, 6)
        cell["radiative_equilibrium_temperature_c"] = round(equilibrium_c, 6)
        cell["energy_balance_residual_c"] = round(residual_c, 6)
        cell["climate_energy_stress_index"] = round(stress, 6)
        cell["surface_albedo_regime"] = regime
        cell["seasonal_insolation_range_w_m2"] = round(seasonal_range, 6)
        cell["orbital_insolation_variability_index"] = round(orbital_variability, 6)
        cell["peak_seasonal_insolation_w_m2"] = round(peak_insolation, 6)
        cell["low_seasonal_insolation_w_m2"] = round(low_insolation, 6)

        regime_counts[regime] += 1
        insolation_sum += top_of_atmosphere
        albedo_sum += albedo
        absorbed_sum += absorbed
        outgoing_sum += outgoing
        greenhouse_sum += greenhouse_trapping
        net_sum += net_balance
        residual_abs_sum += abs(residual_c)
        stress_sum += stress
        seasonal_insolation_range_sum += seasonal_range
        orbital_variability_sum += orbital_variability
        peak_insolation_sum += peak_insolation
        low_insolation_sum += low_insolation
        orbital_distance_factor_sum += mean_orbital_distance_factor
        high_stress_count += 1 if stress >= 0.65 else 0
        records.append(
            {
                "id": len(records),
                "cell_id": cell_id,
                "latitude_deg": round(lat_deg, 6),
                "biome": str(cell.get("biome", "unknown")),
                "water_body_type": str(cell.get("water_body_type", "land")),
                "surface_albedo_regime": regime,
                "stellar_luminosity_factor": round(stellar_luminosity, 6),
                "planetary_greenhouse_factor": round(greenhouse_factor, 6),
                "atmosphere_pressure_bar": round(pressure_bar, 6),
                "orbital_eccentricity": round(orbital_eccentricity, 6),
                "mean_orbital_distance_factor": round(mean_orbital_distance_factor, 6),
                "temperature_c": round(observed_c, 6),
                "monthly_top_of_atmosphere_insolation_w_m2": [round(value, 6) for value in monthly_insolation],
                "top_of_atmosphere_insolation_w_m2": round(top_of_atmosphere, 6),
                "seasonal_insolation_range_w_m2": round(seasonal_range, 6),
                "orbital_insolation_variability_index": round(orbital_variability, 6),
                "peak_seasonal_insolation_w_m2": round(peak_insolation, 6),
                "low_seasonal_insolation_w_m2": round(low_insolation, 6),
                "surface_albedo_index": round(albedo, 6),
                "absorbed_shortwave_w_m2": round(absorbed, 6),
                "outgoing_longwave_w_m2": round(outgoing, 6),
                "greenhouse_trapping_w_m2": round(greenhouse_trapping, 6),
                "net_radiative_balance_w_m2": round(net_balance, 6),
                "no_greenhouse_equilibrium_temperature_c": round(no_greenhouse_c, 6),
                "radiative_equilibrium_temperature_c": round(equilibrium_c, 6),
                "energy_balance_residual_c": round(residual_c, 6),
                "climate_energy_stress_index": round(stress, 6),
            }
        )

    cell_count = len(cells)
    world["climate_energy_balance_records"] = records
    summary = world.setdefault("summary", {})
    summary["climate_energy_balance_record_count"] = len(records)
    summary["mean_top_of_atmosphere_insolation_w_m2"] = round(insolation_sum / cell_count, 6)
    summary["mean_surface_albedo_index"] = round(albedo_sum / cell_count, 6)
    summary["mean_absorbed_shortwave_w_m2"] = round(absorbed_sum / cell_count, 6)
    summary["mean_outgoing_longwave_w_m2"] = round(outgoing_sum / cell_count, 6)
    summary["mean_greenhouse_trapping_w_m2"] = round(greenhouse_sum / cell_count, 6)
    summary["mean_net_radiative_balance_w_m2"] = round(net_sum / cell_count, 6)
    summary["mean_abs_energy_balance_residual_c"] = round(residual_abs_sum / cell_count, 6)
    summary["mean_climate_energy_stress_index"] = round(stress_sum / cell_count, 6)
    summary["mean_seasonal_insolation_range_w_m2"] = round(seasonal_insolation_range_sum / cell_count, 6)
    summary["mean_orbital_insolation_variability_index"] = round(orbital_variability_sum / cell_count, 6)
    summary["mean_peak_seasonal_insolation_w_m2"] = round(peak_insolation_sum / cell_count, 6)
    summary["mean_low_seasonal_insolation_w_m2"] = round(low_insolation_sum / cell_count, 6)
    summary["mean_orbital_distance_factor"] = round(orbital_distance_factor_sum / cell_count, 6)
    summary["orbital_eccentricity"] = round(orbital_eccentricity, 6)
    summary["high_climate_energy_stress_cell_count"] = high_stress_count
    summary["surface_albedo_regime_counts"] = dict(sorted(regime_counts.items()))
    return world
