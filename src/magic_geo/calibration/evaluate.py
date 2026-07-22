"""Scoring a generated world against calibration targets."""

from __future__ import annotations

import math
from typing import Any

from ..scaling import HACK_FIT_MINIMUM_BASIN_AREA_KM2, fit_power_law
from ._constants import _HYDROBASINS_GENERATED_MIN_CENTROID_LAT_DEG
from .errors import CalibrationError
from ._helpers import _target_float, _target_text


def score_range(value: float, target_min: float, target_max: float) -> float:
    if not all(math.isfinite(item) for item in (value, target_min, target_max)):
        raise CalibrationError("calibration values and target bounds must be finite")
    if target_max < target_min:
        raise CalibrationError("target_max must be greater than or equal to target_min")
    if target_min <= value <= target_max:
        return 1.0
    width = max(1.0e-9, target_max - target_min)
    distance = target_min - value if value < target_min else value - target_max
    return max(0.0, min(1.0, 1.0 - distance / width))


def _world_metric_values(world: dict[str, Any]) -> dict[str, float]:
    values: dict[str, float] = {}
    checks = world.get("calibration_checks", [])
    if not isinstance(checks, list):
        raise CalibrationError("world calibration_checks must be a list")
    for check in checks:
        if not isinstance(check, dict):
            raise CalibrationError("each world calibration check must be an object")
        metric = check.get("metric")
        if isinstance(metric, str) and "value" in check:
            try:
                value = float(check["value"])
            except (TypeError, ValueError) as exc:
                raise CalibrationError(f"world calibration metric '{metric}' must be numeric") from exc
            if not math.isfinite(value):
                raise CalibrationError(f"world calibration metric '{metric}' must be finite")
            if metric in values and values[metric] != value:
                raise CalibrationError(f"world calibration metric '{metric}' is duplicated with conflicting values")
            values[metric] = value

    cells = world.get("cells", [])
    if isinstance(cells, list) and cells:
        for cell in cells:
            if not isinstance(cell, dict):
                raise CalibrationError("each world cell must be an object")
        elevation_presence = ["elevation_m" in cell for cell in cells]
        if any(elevation_presence) and not all(elevation_presence):
            raise CalibrationError("world cell elevation_m must be present for every cell or no cells")
        if all(elevation_presence):
            surface_elevations: list[float] = []
            for cell in cells:
                try:
                    elevation = float(cell["elevation_m"])
                except (TypeError, ValueError) as exc:
                    raise CalibrationError("world cell elevation_m must be numeric") from exc
                if not math.isfinite(elevation):
                    raise CalibrationError("world cell elevation_m must be finite")
                surface_elevations.append(elevation)
            nonnegative_elevations = [elevation for elevation in surface_elevations if elevation >= 0.0]
            if not nonnegative_elevations:
                raise CalibrationError("world has no nonnegative surface elevations")
            derived_surface_values = {
                "below_sea_level_surface_fraction": (
                    sum(elevation < 0.0 for elevation in surface_elevations) / len(surface_elevations)
                ),
                "mean_nonnegative_surface_elevation_m": (
                    sum(nonnegative_elevations) / len(nonnegative_elevations)
                ),
                "surface_elevation_span_m": max(surface_elevations) - min(surface_elevations),
            }
            for metric, derived_value in derived_surface_values.items():
                if metric in values and abs(values[metric] - derived_value) > 0.001:
                    raise CalibrationError(f"world calibration metric '{metric}' conflicts with cell-derived value")
                values.setdefault(metric, derived_value)

        initial_age_ledger = world.get("initial_oceanic_crust_age_ledger")
        if initial_age_ledger is not None:
            if not isinstance(initial_age_ledger, dict):
                raise CalibrationError(
                    "world initial_oceanic_crust_age_ledger must be an object"
                )
            ages = initial_age_ledger.get("age_ma_by_cell")
            statuses = initial_age_ledger.get("status_id_by_cell")
            thresholds = initial_age_ledger.get("cdf_thresholds_ma")
            recorded_cdf = initial_age_ledger.get(
                "area_weighted_cdf_le_threshold"
            )
            if (
                not isinstance(ages, list)
                or not isinstance(statuses, list)
                or len(ages) != len(cells)
                or len(statuses) != len(cells)
                or not isinstance(thresholds, list)
                or not isinstance(recorded_cdf, list)
                or len(thresholds) != len(recorded_cdf)
            ):
                raise CalibrationError(
                    "world initial oceanic crust age ledger has invalid cardinality"
                )
            expected_thresholds = [
                20.0,
                40.0,
                60.0,
                80.0,
                100.0,
                120.0,
                140.0,
                160.0,
                180.0,
                200.0,
            ]
            try:
                age_values = [float(value) for value in ages]
                status_values = [int(value) for value in statuses]
                threshold_values = [float(value) for value in thresholds]
                recorded_cdf_values = [float(value) for value in recorded_cdf]
                cell_areas = [float(cell["area_km2"]) for cell in cells]
            except (KeyError, TypeError, ValueError, OverflowError) as exc:
                raise CalibrationError(
                    "world initial oceanic crust age ledger must be numeric"
                ) from exc
            if (
                threshold_values != expected_thresholds
                or any(
                    not math.isfinite(age) or age < 0.0
                    for age in age_values
                )
                or any(status not in range(5) for status in status_values)
                or any(
                    not math.isfinite(area) or area <= 0.0
                    for area in cell_areas
                )
                or any(
                    not math.isfinite(value) or not 0.0 <= value <= 1.0
                    for value in recorded_cdf_values
                )
            ):
                raise CalibrationError(
                    "world initial oceanic crust age ledger values are invalid"
                )
            oceanic_rows = [
                (age, area)
                for age, area, status in zip(
                    age_values,
                    cell_areas,
                    status_values,
                    strict=True,
                )
                if status != 0
            ]
            if not oceanic_rows:
                raise CalibrationError(
                    "world initial oceanic crust age ledger has no oceanic-like cells"
                )
            total_oceanic_area = math.fsum(area for _, area in oceanic_rows)
            mean_age = math.fsum(
                age * area for age, area in oceanic_rows
            ) / total_oceanic_area
            derived_cdf = [
                math.fsum(
                    area
                    for age, area in oceanic_rows
                    if age <= threshold
                )
                / total_oceanic_area
                for threshold in threshold_values
            ]
            recorded_mean = float(
                initial_age_ledger.get("area_weighted_mean_age_ma", math.nan)
            )
            if (
                not math.isfinite(recorded_mean)
                or abs(recorded_mean - mean_age) > 1.0e-9
                or any(
                    abs(recorded - derived) > 1.0e-12
                    for recorded, derived in zip(
                        recorded_cdf_values,
                        derived_cdf,
                        strict=True,
                    )
                )
            ):
                raise CalibrationError(
                    "world initial oceanic crust age ledger summaries conflict with cell-derived values"
                )
            values[
                "initial_oceanic_crust_age_area_weighted_mean_ma"
            ] = mean_age
            for threshold, cdf_value in zip(
                threshold_values,
                derived_cdf,
                strict=True,
            ):
                values[
                    "initial_oceanic_crust_age_area_weighted_cdf_le_"
                    f"{int(threshold)}_ma"
                ] = cdf_value

        annual_land_temperatures: list[float] = []
        annual_land_temperature_ranges: list[float] = []
        annual_land_precipitation: list[float] = []
        for cell in cells:
            if not isinstance(cell, dict):
                raise CalibrationError("each world cell must be an object")
            if bool(cell.get("is_water", False)):
                continue
            monthly = cell.get("temperature_monthly_c")
            if not isinstance(monthly, list) or len(monthly) != 12:
                raise CalibrationError("land cells require twelve monthly temperatures for external climate calibration")
            try:
                monthly_values = [float(value) for value in monthly]
                precipitation = float(cell["precipitation_mm_y"])
            except (KeyError, TypeError, ValueError) as exc:
                raise CalibrationError("world land climate values must be numeric") from exc
            if not all(math.isfinite(value) for value in [*monthly_values, precipitation]):
                raise CalibrationError("world land climate values must be finite")
            annual_land_temperatures.append(sum(monthly_values) / 12.0)
            annual_land_temperature_ranges.append(max(monthly_values) - min(monthly_values))
            annual_land_precipitation.append(precipitation)
        if annual_land_temperatures:
            derived_values = {
                "mean_land_annual_temperature_c": sum(annual_land_temperatures) / len(annual_land_temperatures),
                "mean_land_annual_temperature_range_c": (
                    sum(annual_land_temperature_ranges) / len(annual_land_temperature_ranges)
                ),
                "mean_land_precipitation_mm_y": sum(annual_land_precipitation) / len(annual_land_precipitation),
            }
            for metric, derived_value in derived_values.items():
                if metric in values:
                    if abs(values[metric] - derived_value) > 0.001:
                        raise CalibrationError(
                            f"world calibration metric '{metric}' conflicts with cell-derived value"
                        )
                else:
                    values[metric] = derived_value

    watersheds = world.get("watersheds", [])
    if isinstance(watersheds, list) and watersheds:
        if not all(isinstance(watershed, dict) for watershed in watersheds):
            raise CalibrationError("each world watershed must be an object")
        hack_length_presence = ["main_channel_length_km" in watershed for watershed in watersheds]
        if any(hack_length_presence) and not all(hack_length_presence):
            raise CalibrationError("world watersheds must provide main_channel_length_km consistently")
        if not all(
            "is_endorheic" in watershed and "outlet_type" in watershed
            for watershed in watersheds
        ):
            raise CalibrationError(
                "world watersheds must provide is_endorheic and outlet_type consistently"
            )
        hack_observations: list[tuple[float, float]] = []
        exorheic_backbone_hack_observations: list[tuple[float, float]] = []
        watershed_count = 0
        endorheic_count = 0
        watershed_area = 0.0
        endorheic_area = 0.0
        for watershed in watersheds:
            try:
                area = float(watershed["area_km2"])
            except (KeyError, TypeError, ValueError) as exc:
                raise CalibrationError("world watershed area_km2 must be numeric") from exc
            if not math.isfinite(area) or area <= 0.0:
                raise CalibrationError("world watershed area_km2 must be finite and positive")
            if all(hack_length_presence):
                try:
                    main_channel_length = float(watershed["main_channel_length_km"])
                except (TypeError, ValueError) as exc:
                    raise CalibrationError("world watershed main_channel_length_km must be numeric") from exc
                if not math.isfinite(main_channel_length) or main_channel_length < 0.0:
                    raise CalibrationError(
                        "world watershed main_channel_length_km must be finite and nonnegative"
                    )
                if (
                    main_channel_length > 0.0
                    and area >= HACK_FIT_MINIMUM_BASIN_AREA_KM2
                ):
                    hack_observations.append((area, main_channel_length))
            is_endorheic_raw = watershed["is_endorheic"]
            outlet_type_raw = watershed["outlet_type"]
            if not isinstance(is_endorheic_raw, bool):
                raise CalibrationError(
                    "world watershed is_endorheic must be boolean"
                )
            if not isinstance(outlet_type_raw, str) or not outlet_type_raw:
                raise CalibrationError(
                    "world watershed outlet_type must be a non-empty string"
                )
            is_endorheic = is_endorheic_raw
            outlet_type = outlet_type_raw
            if (outlet_type == "ocean") == is_endorheic:
                raise CalibrationError(
                    "world watershed ocean outlet_type conflicts with is_endorheic"
                )
            if (
                all(hack_length_presence)
                and not is_endorheic
                and outlet_type == "ocean"
                and main_channel_length > 0.0
                and area >= HACK_FIT_MINIMUM_BASIN_AREA_KM2
            ):
                exorheic_backbone_hack_observations.append(
                    (area, main_channel_length)
                )
            watershed_count += 1
            watershed_area += area
            if is_endorheic:
                endorheic_count += 1
                endorheic_area += area
        derived_watershed_values = {
            "endorheic_watershed_fraction": endorheic_count / watershed_count,
            "endorheic_watershed_area_fraction": endorheic_area / watershed_area,
        }
        centroid_presence = ["centroid_lat_deg" in watershed for watershed in watersheds]
        if any(centroid_presence) and not all(centroid_presence):
            raise CalibrationError("world watersheds must provide centroid_lat_deg consistently")
        if all(centroid_presence):
            coverage_watershed_count = 0
            coverage_endorheic_count = 0
            coverage_watershed_area = 0.0
            coverage_endorheic_area = 0.0
            for watershed in watersheds:
                try:
                    centroid_latitude = float(watershed["centroid_lat_deg"])
                except (TypeError, ValueError) as exc:
                    raise CalibrationError("world watershed centroid_lat_deg must be numeric") from exc
                if not math.isfinite(centroid_latitude) or not -90.0 <= centroid_latitude <= 90.0:
                    raise CalibrationError("world watershed centroid_lat_deg must be finite and within [-90, 90]")
                if centroid_latitude < _HYDROBASINS_GENERATED_MIN_CENTROID_LAT_DEG:
                    continue
                area = float(watershed["area_km2"])
                is_endorheic = watershed["is_endorheic"]
                coverage_watershed_count += 1
                coverage_watershed_area += area
                if is_endorheic:
                    coverage_endorheic_count += 1
                    coverage_endorheic_area += area
            if coverage_watershed_count == 0 or coverage_watershed_area <= 0.0:
                raise CalibrationError("world has no watersheds in HydroBASINS non-Antarctic coverage")
            derived_watershed_values.update(
                {
                    "non_antarctic_endorheic_watershed_fraction": (
                        coverage_endorheic_count / coverage_watershed_count
                    ),
                    "non_antarctic_endorheic_watershed_area_fraction": (
                        coverage_endorheic_area / coverage_watershed_area
                    ),
                }
            )
        if len(hack_observations) >= 2:
            try:
                hack_fit = fit_power_law(hack_observations)
            except ValueError as exc:
                raise CalibrationError("world watershed Hack fit is invalid") from exc
            derived_watershed_values.update(
                {
                    "watershed_hack_fitted_exponent": hack_fit.exponent,
                    "watershed_hack_fitted_coefficient": hack_fit.coefficient,
                    "watershed_hack_fitted_log_rmse": hack_fit.log_rmse,
                    "watershed_hack_fitted_observation_count": float(hack_fit.observation_count),
                }
            )
        if (
            len(exorheic_backbone_hack_observations) >= 2
            and len({area for area, _ in exorheic_backbone_hack_observations}) >= 2
        ):
            try:
                exorheic_hack_fit = fit_power_law(
                    exorheic_backbone_hack_observations
                )
            except ValueError as exc:
                raise CalibrationError(
                    "world exorheic watershed-backbone Hack fit is invalid"
                ) from exc
            derived_watershed_values.update(
                {
                    "exorheic_watershed_backbone_hack_fitted_exponent": (
                        exorheic_hack_fit.exponent
                    ),
                    "exorheic_watershed_backbone_hack_fitted_coefficient": (
                        exorheic_hack_fit.coefficient
                    ),
                    "exorheic_watershed_backbone_hack_fitted_log_rmse": (
                        exorheic_hack_fit.log_rmse
                    ),
                    "exorheic_watershed_backbone_hack_fitted_observation_count": float(
                        exorheic_hack_fit.observation_count
                    ),
                }
            )
        for metric, derived_value in derived_watershed_values.items():
            if metric in values:
                if abs(values[metric] - derived_value) > 0.001:
                    raise CalibrationError(
                        f"world calibration metric '{metric}' conflicts with watershed-derived value"
                    )
            else:
                values[metric] = derived_value
    return values


def evaluate_calibration_targets(world: dict[str, Any], targets: list[dict[str, Any]]) -> dict[str, Any]:
    values = _world_metric_values(world)
    checks: list[dict[str, Any]] = []
    pass_count = 0
    score_sum = 0.0
    missing_count = 0
    missing_metrics: set[str] = set()

    for target in targets:
        dataset = _target_text(target, "dataset")
        layer = _target_text(target, "layer")
        metric = _target_text(target, "metric")
        source_metric = _target_text(target, "source_metric") if "source_metric" in target else metric
        target_min = _target_float(target, "target_min")
        target_max = _target_float(target, "target_max")
        if target_max < target_min:
            raise CalibrationError(f"target range for '{metric}' is inverted")

        value = values.get(metric)
        missing = value is None
        if missing:
            score = 0.0
            passed = False
            missing_count += 1
            missing_metrics.add(metric)
        else:
            score = round(score_range(value, target_min, target_max), 6)
            passed = target_min <= value <= target_max

        if passed:
            pass_count += 1
        score_sum += score
        source_metadata = {
            key: value
            for key, value in target.items()
            if key.startswith("source_") and key != "source_metric"
        }
        target_metadata = (
            {"tolerance_basis": _target_text(target, "tolerance_basis")}
            if "tolerance_basis" in target
            else {}
        )
        checks.append(
            {
                "id": len(checks),
                "dataset": dataset,
                "layer": layer,
                "metric": metric,
                "source_metric": source_metric,
                "value": value,
                "target_min": target_min,
                "target_max": target_max,
                "score": score,
                "passed": passed,
                "missing_metric": missing,
                "source": str(target.get("source", "external_target")),
                **source_metadata,
                **target_metadata,
            }
        )

    count = len(checks)
    evaluated_count = count - missing_count
    return {
        "summary": {
            "external_calibration_check_count": count,
            "external_calibration_evaluated_metric_count": evaluated_count,
            "external_calibration_pass_count": pass_count,
            "external_calibration_missing_metric_count": missing_count,
            "external_calibration_metric_coverage_fraction": round(evaluated_count / count, 6) if count else 0.0,
            "external_calibration_pass_fraction": round(pass_count / count, 6) if count else 0.0,
            "external_calibration_evaluated_pass_fraction": (
                round(pass_count / evaluated_count, 6) if evaluated_count else 0.0
            ),
            "external_mean_calibration_score": round(score_sum / count, 6) if count else 0.0,
            "external_mean_evaluated_calibration_score": (
                round(score_sum / evaluated_count, 6) if evaluated_count else 0.0
            ),
            "external_calibration_complete": missing_count == 0 and count > 0,
        },
        "available_world_metrics": sorted(values),
        "missing_world_metrics": sorted(missing_metrics),
        "checks": checks,
    }
