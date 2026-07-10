from __future__ import annotations

from collections import Counter
from typing import Any


CLIMATE_CLASSIFICATION_TYPE = "koppen_geiger_beck_2018_v0"
CLIMATE_CLASSIFICATION_LIMITATION = "single_generated_monthly_climatology_without_observational_ensemble"
CLIMATE_CLASS_NAMES = {
    "Af": "tropical_rainforest",
    "Am": "tropical_monsoon",
    "Aw": "tropical_savanna",
    "BWh": "hot_desert",
    "BWk": "cold_desert",
    "BSh": "hot_steppe",
    "BSk": "cold_steppe",
    "Csa": "temperate_dry_hot_summer",
    "Csb": "temperate_dry_warm_summer",
    "Csc": "temperate_dry_cold_summer",
    "Cwa": "temperate_dry_winter_hot_summer",
    "Cwb": "temperate_dry_winter_warm_summer",
    "Cwc": "temperate_dry_winter_cold_summer",
    "Cfa": "temperate_humid_hot_summer",
    "Cfb": "temperate_humid_warm_summer",
    "Cfc": "temperate_humid_cold_summer",
    "Dsa": "cold_dry_hot_summer",
    "Dsb": "cold_dry_warm_summer",
    "Dsc": "cold_dry_cold_summer",
    "Dsd": "cold_dry_very_cold_winter",
    "Dwa": "cold_dry_winter_hot_summer",
    "Dwb": "cold_dry_winter_warm_summer",
    "Dwc": "cold_dry_winter_cold_summer",
    "Dwd": "cold_dry_winter_very_cold_winter",
    "Dfa": "cold_humid_hot_summer",
    "Dfb": "cold_humid_warm_summer",
    "Dfc": "cold_humid_cold_summer",
    "Dfd": "cold_humid_very_cold_winter",
    "ET": "polar_tundra",
    "EF": "polar_frost",
}


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _monthly_values(cell: dict[str, Any], key: str, fallback: float) -> list[float]:
    values = cell.get(key, [])
    if not isinstance(values, list) or len(values) != 12:
        return [fallback / 12.0 for _ in range(12)]
    return [float(value) for value in values]


def _monthly_components(cell: dict[str, Any], key: str, fallback: float) -> list[float]:
    values = cell.get(key, [])
    if not isinstance(values, list) or len(values) != 12:
        return [fallback for _ in range(12)]
    return [float(value) for value in values]


def _temperature_evaporation_weights(monthly_temperature_c: list[float]) -> list[float]:
    weights = [max(0.05, 1.0 + temperature / 35.0) for temperature in monthly_temperature_c]
    total = sum(weights)
    if total <= 0.0:
        return [1.0 / 12.0 for _ in range(12)]
    return [weight / total for weight in weights]


def classify_koppen_geiger(cell: dict[str, Any]) -> str:
    monthly_temperature = _monthly_values(
        cell,
        "temperature_monthly_c",
        float(cell.get("temperature_c", 0.0)) * 12.0,
    )
    monthly_precipitation = [
        max(0.0, value)
        for value in _monthly_values(
            cell,
            "precipitation_monthly_mm",
            float(cell.get("precipitation_mm_y", 0.0)),
        )
    ]
    annual_temperature = sum(monthly_temperature) / 12.0
    annual_precipitation = sum(monthly_precipitation)
    coldest_temperature = min(monthly_temperature)
    hottest_temperature = max(monthly_temperature)
    warm_month_count = sum(1 for temperature in monthly_temperature if temperature > 10.0)

    latitude = float(cell.get("lat_deg", 0.0))
    if latitude >= 0.0:
        summer_indices = {3, 4, 5, 6, 7, 8}
    else:
        summer_indices = {0, 1, 2, 9, 10, 11}
    winter_indices = set(range(12)) - summer_indices
    summer_precipitation = sum(monthly_precipitation[index] for index in summer_indices)
    winter_precipitation = sum(monthly_precipitation[index] for index in winter_indices)

    if annual_precipitation > 0.0 and summer_precipitation / annual_precipitation >= 0.70:
        aridity_threshold = 20.0 * annual_temperature + 280.0
    elif annual_precipitation > 0.0 and winter_precipitation / annual_precipitation >= 0.70:
        aridity_threshold = 20.0 * annual_temperature
    else:
        aridity_threshold = 20.0 * annual_temperature + 140.0
    aridity_threshold = max(0.0, aridity_threshold)
    if annual_precipitation < aridity_threshold:
        moisture_code = "W" if annual_precipitation < aridity_threshold * 0.5 else "S"
        temperature_code = "h" if annual_temperature >= 18.0 else "k"
        return f"B{moisture_code}{temperature_code}"

    if coldest_temperature >= 18.0:
        driest_precipitation = min(monthly_precipitation)
        if driest_precipitation >= 60.0:
            return "Af"
        if driest_precipitation >= 100.0 - annual_precipitation / 25.0:
            return "Am"
        return "Aw"

    if hottest_temperature < 10.0:
        return "ET" if hottest_temperature > 0.0 else "EF"

    main_class = "C" if coldest_temperature > 0.0 else "D"
    summer_values = [monthly_precipitation[index] for index in summer_indices]
    winter_values = [monthly_precipitation[index] for index in winter_indices]
    if (
        winter_precipitation > summer_precipitation
        and min(summer_values) < 40.0
        and min(summer_values) < max(winter_values) / 3.0
    ):
        precipitation_code = "s"
    elif (
        summer_precipitation >= winter_precipitation
        and min(winter_values) < max(summer_values) / 10.0
    ):
        precipitation_code = "w"
    else:
        precipitation_code = "f"

    if hottest_temperature >= 22.0:
        temperature_code = "a"
    elif warm_month_count >= 4:
        temperature_code = "b"
    elif main_class == "D" and coldest_temperature <= -38.0:
        temperature_code = "d"
    else:
        temperature_code = "c"
    return f"{main_class}{precipitation_code}{temperature_code}"


def _cell_seasonality(cell: dict[str, Any]) -> tuple[float, float, float, str]:
    monthly_precipitation = _monthly_values(cell, "precipitation_monthly_mm", float(cell.get("precipitation_mm_y", 0.0)))
    monthly_temperature = _monthly_values(cell, "temperature_monthly_c", float(cell.get("temperature_c", 0.0)) * 12.0)
    evaporation_weights = _temperature_evaporation_weights(monthly_temperature)
    annual_evaporation = max(0.0, float(cell.get("vapor_evaporation_mm_y", 0.0)))
    monthly_evaporation = [annual_evaporation * weight for weight in evaporation_weights]
    annual_precipitation = sum(max(0.0, value) for value in monthly_precipitation)
    mean_monthly_precipitation = annual_precipitation / 12.0
    precipitation_range = max(monthly_precipitation) - min(monthly_precipitation) if monthly_precipitation else 0.0
    monsoon_index = _clamp(precipitation_range / max(1.0, annual_precipitation), 0.0, 1.0)
    annual_deficit = sum(max(0.0, evaporation - precipitation) for evaporation, precipitation in zip(monthly_evaporation, monthly_precipitation))
    seasonal_aridity = _clamp(annual_deficit / max(1.0, annual_precipitation + annual_evaporation), 0.0, 1.0)
    wettest_month = monthly_precipitation.index(max(monthly_precipitation)) + 1 if monthly_precipitation else 1
    lat = float(cell.get("lat_deg", 0.0))
    summer_months = {6, 7, 8} if lat >= 0.0 else {12, 1, 2}
    winter_months = {12, 1, 2} if lat >= 0.0 else {6, 7, 8}
    if annual_precipitation <= 150.0 or seasonal_aridity >= 0.65:
        regime = "arid_seasonal"
    elif monsoon_index >= 0.22 and max(monthly_precipitation) >= mean_monthly_precipitation * 1.65:
        regime = "monsoonal"
    elif wettest_month in winter_months and monsoon_index >= 0.12:
        regime = "winter_wet"
    elif wettest_month in summer_months and monsoon_index >= 0.12:
        regime = "summer_wet"
    else:
        regime = "humid_stable"
    return precipitation_range, seasonal_aridity, monsoon_index, regime


def enrich_world_with_seasonal_climate_history(world: dict[str, Any]) -> dict[str, Any]:
    cells = world.get("cells", [])
    if not isinstance(cells, list) or not cells:
        return world

    cells_by_atmospheric_cell: dict[str, list[dict[str, Any]]] = {}
    regime_counts: Counter[str] = Counter()
    climate_class_counts: Counter[str] = Counter()
    climate_main_class_counts: Counter[str] = Counter()
    arid_cell_count = 0
    monsoon_index_sum = 0.0
    aridity_index_sum = 0.0

    for cell in cells:
        precipitation_range, seasonal_aridity, monsoon_index, regime = _cell_seasonality(cell)
        cell["seasonal_precipitation_range_mm"] = round(precipitation_range, 6)
        cell["seasonal_aridity_index"] = round(seasonal_aridity, 6)
        cell["cell_monsoon_index"] = round(monsoon_index, 6)
        cell["seasonal_humidity_regime"] = regime
        climate_class = classify_koppen_geiger(cell)
        cell["climate_class"] = climate_class
        regime_counts[regime] += 1
        climate_class_counts[climate_class] += 1
        climate_main_class_counts[climate_class[0]] += 1
        if seasonal_aridity >= 0.45:
            arid_cell_count += 1
        monsoon_index_sum += monsoon_index
        aridity_index_sum += seasonal_aridity
        atmospheric_cell = str(cell.get("atmospheric_cell", "unknown"))
        cells_by_atmospheric_cell.setdefault(atmospheric_cell, []).append(cell)

    histories: list[dict[str, Any]] = []
    total_step_count = 0
    total_precipitation_mm = 0.0
    total_evaporation_mm = 0.0
    total_convergence_mm = 0.0
    total_export_mm = 0.0
    total_deficit_mm = 0.0
    residual_abs_sum = 0.0
    residual_count = 0
    max_storage_mm = 0.0
    max_monsoon_index = 0.0

    for atmospheric_cell, group_cells in sorted(cells_by_atmospheric_cell.items()):
        cell_count = len(group_cells)
        humidity_storage_mm = 0.0
        annual_precipitation = 0.0
        annual_evaporation = 0.0
        annual_convergence = 0.0
        annual_export = 0.0
        annual_deficit = 0.0
        max_history_storage = 0.0
        monthly_precipitation_values: list[float] = []
        monthly_temperature_values: list[float] = []
        steps: list[dict[str, Any]] = []

        for month_index in range(12):
            precipitation_sum = 0.0
            temperature_sum = 0.0
            evaporation_sum = 0.0
            convergence_sum = 0.0
            wind_east_sum = 0.0
            wind_north_sum = 0.0
            wind_speed_sum = 0.0
            vertical_motion_sum = 0.0
            divergence_sum = 0.0
            for cell in group_cells:
                monthly_precipitation = _monthly_values(
                    cell,
                    "precipitation_monthly_mm",
                    float(cell.get("precipitation_mm_y", 0.0)),
                )
                monthly_temperature = _monthly_values(
                    cell,
                    "temperature_monthly_c",
                    float(cell.get("temperature_c", 0.0)) * 12.0,
                )
                evaporation_weights = _temperature_evaporation_weights(monthly_temperature)
                precipitation_sum += max(0.0, monthly_precipitation[month_index])
                temperature_sum += monthly_temperature[month_index]
                evaporation_sum += max(0.0, float(cell.get("vapor_evaporation_mm_y", 0.0))) * evaporation_weights[month_index]
                convergence_sum += max(0.0, float(cell.get("moisture_convergence_mm_y", 0.0))) / 12.0
                monthly_wind_east = _monthly_components(cell, "wind_monthly_east", float(cell.get("wind_east", 0.0)))
                monthly_wind_north = _monthly_components(cell, "wind_monthly_north", float(cell.get("wind_north", 0.0)))
                wind_east = monthly_wind_east[month_index]
                wind_north = monthly_wind_north[month_index]
                wind_east_sum += wind_east
                wind_north_sum += wind_north
                wind_speed_sum += (wind_east * wind_east + wind_north * wind_north) ** 0.5
                vertical_motion_sum += float(cell.get("vertical_velocity_index", 0.0))
                divergence_sum += float(cell.get("wind_divergence_index", 0.0))

            precipitation_mm = precipitation_sum / cell_count
            temperature_c = temperature_sum / cell_count
            evaporation_mm = evaporation_sum / cell_count
            convergence_mm = convergence_sum / cell_count
            wind_east = wind_east_sum / cell_count
            wind_north = wind_north_sum / cell_count
            wind_speed = wind_speed_sum / cell_count
            vertical_motion = vertical_motion_sum / cell_count
            divergence = divergence_sum / cell_count
            start_storage_mm = humidity_storage_mm
            raw_available_mm = start_storage_mm + evaporation_mm + convergence_mm
            vapor_deficit_mm = max(0.0, precipitation_mm - raw_available_mm)
            surplus_mm = max(0.0, raw_available_mm - precipitation_mm)
            export_fraction = _clamp(0.42 + max(0.0, divergence) * 0.22 + wind_speed * 0.08, 0.25, 0.82)
            humidity_export_mm = surplus_mm * export_fraction
            humidity_storage_mm = surplus_mm - humidity_export_mm
            residual_mm = (
                start_storage_mm
                + evaporation_mm
                + convergence_mm
                + vapor_deficit_mm
                - precipitation_mm
                - humidity_export_mm
                - humidity_storage_mm
            )
            monthly_precipitation_values.append(precipitation_mm)
            monthly_temperature_values.append(temperature_c)
            annual_precipitation += precipitation_mm
            annual_evaporation += evaporation_mm
            annual_convergence += convergence_mm
            annual_export += humidity_export_mm
            annual_deficit += vapor_deficit_mm
            max_history_storage = max(max_history_storage, humidity_storage_mm)
            max_storage_mm = max(max_storage_mm, humidity_storage_mm)
            residual_abs_sum += abs(residual_mm)
            residual_count += 1
            steps.append(
                {
                    "month": month_index + 1,
                    "mean_temperature_c": round(temperature_c, 6),
                    "precipitation_mm": round(precipitation_mm, 6),
                    "start_humidity_storage_mm": round(start_storage_mm, 6),
                    "evaporation_mm": round(evaporation_mm, 6),
                    "moisture_convergence_mm": round(convergence_mm, 6),
                    "vapor_deficit_mm": round(vapor_deficit_mm, 6),
                    "humidity_export_mm": round(humidity_export_mm, 6),
                    "end_humidity_storage_mm": round(humidity_storage_mm, 6),
                    "humidity_budget_residual_mm": round(residual_mm, 6),
                    "mean_wind_east": round(wind_east, 6),
                    "mean_wind_north": round(wind_north, 6),
                    "mean_wind_speed_index": round(wind_speed, 6),
                    "mean_vertical_motion_index": round(vertical_motion, 6),
                    "mean_divergence_index": round(divergence, 6),
                    "drying_risk": round(_clamp(vapor_deficit_mm / max(1.0, precipitation_mm + evaporation_mm), 0.0, 1.0), 6),
                }
            )

        precipitation_range = max(monthly_precipitation_values) - min(monthly_precipitation_values)
        monsoon_index = _clamp(precipitation_range / max(1.0, annual_precipitation), 0.0, 1.0)
        max_monsoon_index = max(max_monsoon_index, monsoon_index)
        wettest_month = monthly_precipitation_values.index(max(monthly_precipitation_values)) + 1
        driest_month = monthly_precipitation_values.index(min(monthly_precipitation_values)) + 1
        total_step_count += len(steps)
        total_precipitation_mm += annual_precipitation
        total_evaporation_mm += annual_evaporation
        total_convergence_mm += annual_convergence
        total_export_mm += annual_export
        total_deficit_mm += annual_deficit
        histories.append(
            {
                "id": len(histories),
                "atmospheric_cell": atmospheric_cell,
                "cell_count": cell_count,
                "time_step_count": len(steps),
                "annual_precipitation_mm": round(annual_precipitation, 6),
                "annual_evaporation_mm": round(annual_evaporation, 6),
                "annual_moisture_convergence_mm": round(annual_convergence, 6),
                "annual_humidity_export_mm": round(annual_export, 6),
                "annual_vapor_deficit_mm": round(annual_deficit, 6),
                "max_humidity_storage_mm": round(max_history_storage, 6),
                "mean_temperature_c": round(sum(monthly_temperature_values) / 12.0, 6),
                "wettest_month": wettest_month,
                "driest_month": driest_month,
                "seasonal_precipitation_range_mm": round(precipitation_range, 6),
                "monsoon_index": round(monsoon_index, 6),
                "max_drying_risk": round(max((float(step["drying_risk"]) for step in steps), default=0.0), 6),
                "steps": steps,
            }
        )

    world["climate_seasonal_histories"] = histories
    world["climate_classification"] = {
        "classification_type": CLIMATE_CLASSIFICATION_TYPE,
        "monthly_temperature_field": "temperature_monthly_c",
        "monthly_precipitation_field": "precipitation_monthly_mm",
        "temperate_cold_threshold_c": 0.0,
        "arid_class_precedence": True,
        "includes_water_cells": True,
        "confidence_resolved": False,
        "classification_limitation": CLIMATE_CLASSIFICATION_LIMITATION,
        "available_class_count": len(CLIMATE_CLASS_NAMES),
        "generated_class_count": len(climate_class_counts),
        "classified_cell_count": len(cells),
        "legend": [
            {"code": code, "name": CLIMATE_CLASS_NAMES[code]}
            for code in sorted(CLIMATE_CLASS_NAMES)
        ],
    }
    summary = world.setdefault("summary", {})
    summary["climate_seasonal_history_count"] = len(histories)
    summary["climate_seasonal_step_count"] = total_step_count
    summary["seasonal_humidity_regime_counts"] = dict(sorted(regime_counts.items()))
    summary["climate_class_count"] = len(climate_class_counts)
    summary["climate_class_counts"] = dict(sorted(climate_class_counts.items()))
    summary["climate_main_class_counts"] = dict(sorted(climate_main_class_counts.items()))
    summary["seasonal_aridity_cell_fraction"] = round(arid_cell_count / len(cells), 6)
    summary["mean_cell_monsoon_index"] = round(monsoon_index_sum / len(cells), 6)
    summary["mean_cell_seasonal_aridity_index"] = round(aridity_index_sum / len(cells), 6)
    summary["climate_seasonal_total_precipitation_mm"] = round(total_precipitation_mm, 6)
    summary["climate_seasonal_total_evaporation_mm"] = round(total_evaporation_mm, 6)
    summary["climate_seasonal_total_moisture_convergence_mm"] = round(total_convergence_mm, 6)
    summary["climate_seasonal_total_humidity_export_mm"] = round(total_export_mm, 6)
    summary["climate_seasonal_total_vapor_deficit_mm"] = round(total_deficit_mm, 6)
    summary["climate_seasonal_mean_abs_residual_mm"] = (
        round(residual_abs_sum / residual_count, 6) if residual_count > 0 else 0.0
    )
    summary["max_climate_humidity_storage_mm"] = round(max_storage_mm, 6)
    summary["max_climate_monsoon_index"] = round(max_monsoon_index, 6)
    return world
