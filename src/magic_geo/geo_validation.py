from __future__ import annotations

import math
from collections import Counter, deque
from copy import deepcopy
from typing import Any, Iterable

from .biome_dynamics import enrich_world_with_biome_diagnostics
from .geo_validation_physics import validate_physics_replays
from .geo_validation_subsystems import validate_natural_subsystems


GEO_VALIDATION_SCHEMA_VERSION = 1

GEO_VALIDATION_SCOPE = (
    "natural planet geometry and spatial indices, tectonics and faults, relief, "
    "sea level and ocean circulation, climate, lakes and hydrology, erosion and "
    "sediment, cryosphere, soils, biomes and ecosystems, disturbance, and natural resources"
)

GEO_MODEL_LIMITATIONS = (
    "the simulation clock orders procedural stages but has no calibrated physical duration",
    "the diagnostic atmosphere is not a three-dimensional mass-conserving circulation solver",
    "configured ocean inventory is not a closed total-water partition across ocean, ice, groundwater, lakes, and atmosphere",
    "plate-attached nearest-neighbor crust transport is not mass-conserving",
    "ecosystem, species, wildfire, and resource layers are diagnostic index models rather than calibrated population or process solvers",
    "Earth empirical fit remains a separate calibration verdict from internal contract integrity",
)

CALIBRATION_EXPECTED_METRICS = frozenset(
    {
        "ocean_fraction",
        "mean_land_elevation_m",
        "hypsometric_span_m",
        "global_mean_temperature_c",
        "mean_land_precipitation_mm_y",
        "mean_monthly_temperature_range_c",
        "river_cell_fraction",
        "endorheic_watershed_fraction",
        "desert_land_fraction",
        "ice_land_fraction",
        "forest_land_fraction",
        "coastal_land_fraction",
    }
)

ALLOWED_CRUST_TYPES = frozenset(
    {
        "oceanic", "continental", "transitional", "volcanic_arc", "craton",
        "orogen", "rift_basin", "sedimentary_basin", "accreted_terrane",
    }
)
ALLOWED_BIOMES = frozenset(
    {
        "ocean", "continental_shelf", "lake", "ice_cap", "tundra",
        "boreal_forest", "temperate_forest", "temperate_grassland",
        "mediterranean_scrub", "cold_desert", "hot_desert", "savanna",
        "tropical_seasonal_forest", "tropical_rainforest", "alpine", "wetland",
    }
)

REALISM_FAMILIES = (
    "planet_realism_checks",
    "climate_realism_checks",
    "geology_realism_checks",
    "hydrology_realism_checks",
    "biome_realism_checks",
)

REALISM_EXPECTED_NAMES: dict[str, frozenset[str]] = {
    "planet_realism_checks": frozenset(
        {
            "liquid_water_temperature_window",
            "atmosphere_gravity_stability",
            "rotation_circulation_plausibility",
            "surface_water_inventory",
        }
    ),
    "climate_realism_checks": frozenset(
        {
            "subtropical_dry_belt",
            "equatorial_ocean_humidity",
            "orographic_rain_shadow",
            "continental_interior_extremes",
            "cold_current_coastal_drying",
            "warm_current_climate_moderation",
        }
    ),
    "geology_realism_checks": frozenset(
        {
            "mountain_convergent_alignment",
            "trench_convergent_alignment",
            "oceanic_ridge_divergent_alignment",
            "volcanic_arc_trench_pairing",
            "transform_fault_linearity",
            "hypsometry_bimodality",
        }
    ),
    "hydrology_realism_checks": frozenset(
        {
            "river_terminal_sink_validity",
            "river_downhill_flow",
            "tributary_merge_coherence",
            "delta_lowland_sediment_terminal_water",
            "watershed_divide_alignment",
        }
    ),
    "biome_realism_checks": frozenset(
        {
            "desert_water_deficit_alignment",
            "forest_water_availability_alignment",
            "tundra_cold_altitude_alignment",
            "savanna_seasonality_alignment",
            "mangrove_warm_wet_coast_constraint",
        }
    ),
}

# These checks currently report a perfect score when their candidate set is empty.
# Deep validation treats that state as not-applicable instead of positive evidence.
REALISM_EVIDENCE_REQUIREMENTS: dict[tuple[str, str], tuple[str, ...]] = {
    ("climate_realism_checks", "subtropical_dry_belt"): (
        "subtropical_land_cell_count",
        "reference_land_cell_count",
    ),
    ("climate_realism_checks", "equatorial_ocean_humidity"): (
        "equatorial_ocean_influenced_cell_count",
    ),
    ("climate_realism_checks", "orographic_rain_shadow"): (
        "rain_shadow_candidate_cell_count",
    ),
    ("climate_realism_checks", "continental_interior_extremes"): (
        "interior_land_cell_count",
        "coastal_land_cell_count",
    ),
    ("climate_realism_checks", "cold_current_coastal_drying"): (
        "cold_current_coastal_cell_count",
        "warm_current_coastal_cell_count",
    ),
    ("climate_realism_checks", "warm_current_climate_moderation"): (
        "cold_current_coastal_cell_count",
        "warm_current_coastal_cell_count",
    ),
    ("geology_realism_checks", "mountain_convergent_alignment"): (
        "high_mountain_cell_count",
    ),
    ("geology_realism_checks", "trench_convergent_alignment"): (
        "trench_candidate_cell_count",
    ),
    ("geology_realism_checks", "oceanic_ridge_divergent_alignment"): (
        "shallow_oceanic_high_cell_count",
    ),
    ("geology_realism_checks", "volcanic_arc_trench_pairing"): (
        "volcanic_arc_candidate_cell_count",
        "trench_candidate_cell_count",
    ),
    ("geology_realism_checks", "transform_fault_linearity"): (
        "transform_candidate_cell_count",
    ),
    ("geology_realism_checks", "hypsometry_bimodality"): (
        "land_cell_count",
        "water_cell_count",
    ),
    ("hydrology_realism_checks", "river_terminal_sink_validity"): (
        "river_cell_count",
    ),
    ("hydrology_realism_checks", "river_downhill_flow"): (
        "river_edge_count",
    ),
    ("hydrology_realism_checks", "tributary_merge_coherence"): (
        "river_edge_count",
    ),
    ("hydrology_realism_checks", "delta_lowland_sediment_terminal_water"): (
        "delta_cell_count",
    ),
    ("hydrology_realism_checks", "watershed_divide_alignment"): (
        "watershed_count",
        "boundary_cell_count",
    ),
    ("biome_realism_checks", "desert_water_deficit_alignment"): (
        "desert_cell_count",
    ),
    ("biome_realism_checks", "forest_water_availability_alignment"): (
        "forest_cell_count",
    ),
    ("biome_realism_checks", "tundra_cold_altitude_alignment"): (
        "tundra_cell_count",
    ),
    ("biome_realism_checks", "savanna_seasonality_alignment"): (
        "savanna_cell_count",
    ),
    ("biome_realism_checks", "mangrove_warm_wet_coast_constraint"): (
        "mangrove_cell_count",
    ),
}

REALISM_EVIDENCE_MINIMUM_COUNTS: dict[tuple[str, str, str], int] = {
    (family, name, key): 3
    for (family, name), keys in REALISM_EVIDENCE_REQUIREMENTS.items()
    for key in keys
}
REALISM_EVIDENCE_MINIMUM_COUNTS.update(
    {
        ("geology_realism_checks", "mountain_convergent_alignment", "high_mountain_cell_count"): 5,
        ("geology_realism_checks", "oceanic_ridge_divergent_alignment", "shallow_oceanic_high_cell_count"): 5,
        ("geology_realism_checks", "transform_fault_linearity", "transform_candidate_cell_count"): 5,
        ("hydrology_realism_checks", "watershed_divide_alignment", "boundary_cell_count"): 10,
        ("biome_realism_checks", "mangrove_warm_wet_coast_constraint", "mangrove_cell_count"): 1,
    }
)


def _finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _mean(values: Iterable[float]) -> float:
    materialized = list(values)
    return sum(materialized) / len(materialized) if materialized else 0.0


def _area_weighted_mean(cells: list[dict[str, Any]], field: str) -> float:
    total_area = sum(max(0.0, float(cell.get("area_km2", 0.0))) for cell in cells)
    if total_area <= 0.0:
        return 0.0
    return sum(
        float(cell.get(field, 0.0)) * max(0.0, float(cell.get("area_km2", 0.0)))
        for cell in cells
    ) / total_area


def _check(
    checks: list[dict[str, Any]],
    *,
    domain: str,
    name: str,
    passed: bool | None,
    message: str,
    severity: str = "error",
    observed: Any = None,
    expected: Any = None,
    evidence: dict[str, Any] | None = None,
) -> None:
    status = "not_applicable" if passed is None else ("passed" if passed else "failed")
    checks.append(
        {
            "id": len(checks),
            "domain": domain,
            "name": name,
            "status": status,
            "passed": passed is True,
            "severity": severity,
            "message": message,
            "observed": observed,
            "expected": expected,
            "evidence": evidence or {},
        }
    )


def _planet_value(world: dict[str, Any], name: str, default: float) -> float:
    parameters = world.get("planet_parameters", {})
    if not isinstance(parameters, dict):
        return default
    try:
        value = float(parameters.get(name, default))
    except (TypeError, ValueError):
        return default
    return value if math.isfinite(value) else default


def _connected_count(start: int, adjacency: dict[int, set[int]]) -> int:
    visited: set[int] = set()
    pending = [start]
    while pending:
        cell_id = pending.pop()
        if cell_id in visited:
            continue
        visited.add(cell_id)
        pending.extend(adjacency.get(cell_id, set()) - visited)
    return len(visited)


def _cycle_nodes(flow_to: dict[int, int]) -> set[int]:
    indegree = {cell_id: 0 for cell_id in flow_to}
    for target in flow_to.values():
        if target in indegree:
            indegree[target] += 1
    pending = deque(cell_id for cell_id, degree in indegree.items() if degree == 0)
    while pending:
        cell_id = pending.popleft()
        target = flow_to.get(cell_id, -1)
        if target in indegree:
            indegree[target] -= 1
            if indegree[target] == 0:
                pending.append(target)
    return {cell_id for cell_id, degree in indegree.items() if degree > 0}


def extract_geo_metrics(world: dict[str, Any]) -> dict[str, Any]:
    """Extract compact natural-system observations without reading civilization layers."""
    cells = world.get("cells", [])
    if not isinstance(cells, list) or not cells or not all(isinstance(cell, dict) for cell in cells):
        return {"cell_count": 0}
    land = [cell for cell in cells if not bool(cell.get("is_water", False))]
    total_area = sum(float(cell.get("area_km2", 0.0)) for cell in cells)
    land_area = sum(float(cell.get("area_km2", 0.0)) for cell in land)
    elevations = [float(cell.get("elevation_m", 0.0)) for cell in cells]
    seasonal_range_cells = [
        {
            "area_km2": float(cell.get("area_km2", 0.0)),
            "seasonal_range_c": (
                max(float(value) for value in cell.get("temperature_monthly_c", []))
                - min(float(value) for value in cell.get("temperature_monthly_c", []))
            ),
        }
        for cell in land
        if isinstance(cell.get("temperature_monthly_c"), list)
        and cell.get("temperature_monthly_c")
    ]
    desert_names = {"hot_desert", "cold_desert"}
    forest_names = {
        "boreal_forest",
        "temperate_forest",
        "tropical_rainforest",
        "tropical_seasonal_forest",
    }
    realism_records = [
        record
        for family in REALISM_FAMILIES
        for record in world.get(family, [])
        if isinstance(record, dict)
    ]
    applicable_records = [
        record
        for family in REALISM_FAMILIES
        for record in world.get(family, [])
        if isinstance(record, dict) and _realism_record_applicable(family, record)
    ]
    def realism_value(family: str, name: str) -> float:
        records = world.get(family, [])
        if not isinstance(records, list):
            return 0.0
        record = next(
            (
                candidate
                for candidate in records
                if isinstance(candidate, dict)
                and str(candidate.get("name", "")) == name
            ),
            {},
        )
        value = record.get("value", 0.0) if isinstance(record, dict) else 0.0
        return float(value) if _finite_number(value) else 0.0

    feedback = world.get("earth_system_feedback_history", [])
    plate_history = world.get("plate_motion_history", [])
    plates = world.get("plates", [])
    sediment_inventory = world.get("sediment_inventory_model", {})
    erosion_stage_changes = [
        float(record.get("mean_abs_elevation_change_m_from_previous_stage", 0.0))
        for record in feedback
        if isinstance(record, dict)
        and bool(record.get("erosion_applied", False))
        and _finite_number(record.get("mean_abs_elevation_change_m_from_previous_stage"))
    ] if isinstance(feedback, list) else []
    plate_rotations = [
        float(record.get("cumulative_rotation_deg", 0.0))
        for record in plates
        if isinstance(record, dict)
        and _finite_number(record.get("cumulative_rotation_deg"))
    ] if isinstance(plates, list) else []
    seasonal_area = sum(record["area_km2"] for record in seasonal_range_cells)
    return {
        "cell_count": len(cells),
        "surface_area_km2": round(total_area, 6),
        "land_area_fraction": round(land_area / total_area, 6) if total_area > 0.0 else 0.0,
        "ocean_fraction": round(1.0 - land_area / total_area, 6) if total_area > 0.0 else 0.0,
        "ocean_volume_km3": round(
            sum(
                float(cell.get("area_km2", 0.0)) * float(cell.get("water_depth_m", 0.0)) / 1000.0
                for cell in cells
                if bool(cell.get("is_water", False))
            ),
            6,
        ),
        "global_mean_temperature_c": round(_area_weighted_mean(cells, "temperature_c"), 6),
        "mean_land_temperature_c": round(_area_weighted_mean(land, "temperature_c"), 6) if land else None,
        "mean_land_precipitation_mm_y": round(_area_weighted_mean(land, "precipitation_mm_y"), 6) if land else None,
        "mean_land_runoff_mm_y": round(_area_weighted_mean(land, "runoff_mm_y"), 6) if land else None,
        "mean_land_seasonal_temperature_range_c": round(
            sum(record["seasonal_range_c"] * record["area_km2"] for record in seasonal_range_cells)
            / seasonal_area,
            6,
        ) if seasonal_area > 0.0 else None,
        "minimum_elevation_m": round(min(elevations), 6),
        "maximum_elevation_m": round(max(elevations), 6),
        "elevation_span_m": round(max(elevations) - min(elevations), 6),
        "river_cell_fraction": round(sum(bool(cell.get("is_river", False)) for cell in cells) / len(cells), 6),
        "lake_cell_fraction": round(sum(bool(cell.get("is_lake", False)) for cell in cells) / len(cells), 6),
        "ice_cell_fraction": round(
            sum(
                float(cell.get("ice_thickness_m", 0.0)) > 25.0
                or str(cell.get("biome", "")) == "ice_cap"
                for cell in cells
            )
            / len(cells),
            6,
        ),
        "desert_land_fraction": round(
            sum(str(cell.get("biome", "")) in desert_names for cell in land) / len(land), 6
        )
        if land
        else None,
        "forest_land_fraction": round(
            sum(str(cell.get("biome", "")) in forest_names for cell in land) / len(land), 6
        )
        if land
        else None,
        "biome_class_count": len({str(cell.get("biome", "")) for cell in cells}),
        "continent_landmass_count": len(world.get("landmasses", []))
        if isinstance(world.get("landmasses"), list)
        else 0,
        "simulation_stage_count": len(feedback) if isinstance(feedback, list) else 0,
        "plate_motion_transition_count": sum(
            isinstance(record, dict)
            and str(record.get("stage", "")) == "plate_motion_iteration"
            for record in plate_history
        ) if isinstance(plate_history, list) else 0,
        "mean_plate_cumulative_rotation_deg": round(_mean(plate_rotations), 6),
        "mean_erosion_iteration_elevation_change_m": round(
            _mean(erosion_stage_changes), 6
        ),
        "sediment_gross_mobilization_volume_km3": round(
            float(sediment_inventory.get("gross_mobilization_volume_km3", 0.0))
            if isinstance(sediment_inventory, dict)
            and _finite_number(sediment_inventory.get("gross_mobilization_volume_km3"))
            else 0.0,
            6,
        ),
        "mountain_convergent_alignment": round(
            realism_value("geology_realism_checks", "mountain_convergent_alignment"), 6
        ),
        "valid_river_sink_fraction": round(
            realism_value("hydrology_realism_checks", "river_terminal_sink_validity"), 6
        ),
        "delta_lowland_sediment_terminal_water_index": round(
            realism_value(
                "hydrology_realism_checks",
                "delta_lowland_sediment_terminal_water",
            ),
            6,
        ),
        "realism_record_count": len(realism_records),
        "realism_evidence_coverage_fraction": round(
            len(applicable_records) / len(realism_records), 6
        )
        if realism_records
        else 0.0,
        "applicable_realism_pass_fraction": round(
            sum(_realism_record_range_passed(record) for record in applicable_records)
            / len(applicable_records),
            6,
        )
        if applicable_records
        else 0.0,
        "calibration_pass_fraction": round(
            _calibration_pass_fraction(world), 6
        ),
    }


def _realism_record_applicable(family: str, record: dict[str, Any]) -> bool:
    name = str(record.get("name", ""))
    requirements = REALISM_EVIDENCE_REQUIREMENTS.get((family, name))
    if not requirements:
        return True
    evidence = record.get("evidence", {})
    if not isinstance(evidence, dict):
        return False
    return all(
        _finite_number(evidence.get(key))
        and float(evidence[key])
        >= REALISM_EVIDENCE_MINIMUM_COUNTS.get((family, name, key), 1)
        for key in requirements
    )


def _realism_record_range_passed(record: dict[str, Any]) -> bool:
    value = record.get("value")
    target_min = record.get("target_min")
    target_max = record.get("target_max")
    return (
        _finite_number(value)
        and _finite_number(target_min)
        and _finite_number(target_max)
        and float(target_min) <= float(value) <= float(target_max)
    )


def _calibration_pass_fraction(world: dict[str, Any]) -> float:
    records = world.get("calibration_checks", [])
    if not isinstance(records, list) or not records:
        return 0.0
    valid_records = [record for record in records if isinstance(record, dict)]
    if len(valid_records) != len(records):
        return 0.0
    return sum(_realism_record_range_passed(record) for record in valid_records) / len(valid_records)


def _validate_realism_evidence(
    world: dict[str, Any],
    checks: list[dict[str, Any]],
) -> None:
    summary = world.get("summary", {})
    for family in REALISM_FAMILIES:
        records = world.get(family, [])
        if not isinstance(records, list) or not records:
            _check(
                checks,
                domain="realism_evidence_integrity",
                name=f"{family}_records",
                passed=False,
                message=f"{family} must be a non-empty list",
                observed=len(records) if isinstance(records, list) else type(records).__name__,
                expected="non-empty list",
            )
            continue
        names = [str(record.get("name", "")) for record in records if isinstance(record, dict)]
        ids = [record.get("id") for record in records if isinstance(record, dict)]
        expected_names = REALISM_EXPECTED_NAMES[family]
        registry_passed = (
            len(records) == len(expected_names)
            and set(names) == expected_names
            and len(set(names)) == len(names)
            and all(isinstance(record_id, int) and not isinstance(record_id, bool) for record_id in ids)
            and len(set(ids)) == len(ids)
        )
        _check(
            checks,
            domain="realism_evidence_integrity",
            name=f"{family}.registry",
            passed=registry_passed,
            message="realism family must contain the complete unique check registry",
            observed={"names": names, "ids": ids},
            expected={"names": sorted(expected_names), "count": len(expected_names)},
        )
        prefix = family.removesuffix("_checks")
        object_records = [record for record in records if isinstance(record, dict)]
        recomputed_pass_count = sum(
            _realism_record_range_passed(record) for record in object_records
        )
        finite_scores = [
            float(record["score"])
            for record in object_records
            if _finite_number(record.get("score"))
        ]
        expected_pass_fraction = (
            recomputed_pass_count / len(object_records) if object_records else 0.0
        )
        expected_mean_score = _mean(finite_scores) if finite_scores else 0.0
        summary_integrity = isinstance(summary, dict) and (
            summary.get(f"{prefix}_check_count") == len(object_records)
            and summary.get(f"{prefix}_pass_count") == recomputed_pass_count
            and _finite_number(summary.get(f"{prefix}_pass_fraction"))
            and abs(
                float(summary[f"{prefix}_pass_fraction"])
                - expected_pass_fraction
            )
            <= 1.0e-6
            and len(finite_scores) == len(object_records)
            and _finite_number(summary.get(f"mean_{prefix}_score"))
            and abs(
                float(summary[f"mean_{prefix}_score"]) - expected_mean_score
            )
            <= 1.0e-6
        )
        _check(
            checks,
            domain="realism_evidence_integrity",
            name=f"{family}.summary",
            passed=summary_integrity,
            message="realism family count, pass fraction, and mean score must mirror its records",
            observed={
                "check_count": summary.get(f"{prefix}_check_count")
                if isinstance(summary, dict)
                else None,
                "pass_count": summary.get(f"{prefix}_pass_count")
                if isinstance(summary, dict)
                else None,
                "pass_fraction": summary.get(f"{prefix}_pass_fraction")
                if isinstance(summary, dict)
                else None,
                "mean_score": summary.get(f"mean_{prefix}_score")
                if isinstance(summary, dict)
                else None,
            },
            expected={
                "check_count": len(object_records),
                "pass_count": recomputed_pass_count,
                "pass_fraction": round(expected_pass_fraction, 6),
                "mean_score": round(expected_mean_score, 6),
            },
        )
        for record in records:
            if not isinstance(record, dict):
                _check(
                    checks,
                    domain="realism_evidence_integrity",
                    name=f"{family}.record_shape",
                    passed=False,
                    message="realism records must be objects",
                    observed=type(record).__name__,
                    expected="dict",
                )
                continue
            name = str(record.get("name", "unknown"))
            applicable = _realism_record_applicable(family, record)
            range_passed = _realism_record_range_passed(record)
            declared_passed = record.get("passed")
            score = record.get("score")
            score_consistent = (
                _finite_number(score)
                and 0.0 <= float(score) <= 1.0
                and (
                    (range_passed and abs(float(score) - 1.0) <= 1.0e-6)
                    or (not range_passed and float(score) < 1.0)
                )
            )
            integrity_passed = (
                isinstance(declared_passed, bool)
                and declared_passed == range_passed
                and score_consistent
                and isinstance(record.get("evidence"), dict)
                and _finite_number(record.get("target_min"))
                and _finite_number(record.get("target_max"))
                and float(record["target_min"]) <= float(record["target_max"])
            )
            _check(
                checks,
                domain="realism_evidence_integrity",
                name=f"{family}.{name}",
                passed=integrity_passed,
                message="realism value, target range, declared result, and score must agree",
                observed={
                    "value": record.get("value"),
                    "declared_passed": declared_passed,
                    "score": score,
                },
                expected={
                    "target_min": record.get("target_min"),
                    "target_max": record.get("target_max"),
                    "recomputed_passed": range_passed,
                },
            )
            _check(
                checks,
                domain="realism_evidence",
                name=f"{family}.{name}",
                passed=range_passed if applicable else None,
                severity="warning",
                message=(
                    "realism claim has no eligible evidence; a vacuous score is not a pass"
                    if not applicable
                    else (
                        "realism claim has eligible evidence and meets its declared range"
                        if range_passed
                        else "realism claim has eligible evidence but falls outside its declared range"
                    )
                ),
                observed=record.get("value"),
                expected={
                    "target_min": record.get("target_min"),
                    "target_max": record.get("target_max"),
                },
                evidence=record.get("evidence", {}) if isinstance(record.get("evidence"), dict) else {},
            )


def _validate_earthlike_profile(
    metrics: dict[str, Any],
    checks: list[dict[str, Any]],
) -> None:
    ranges: dict[str, tuple[float, float]] = {
        "ocean_fraction": (0.55, 0.85),
        "global_mean_temperature_c": (8.0, 22.0),
        "mean_land_precipitation_mm_y": (350.0, 1800.0),
        "elevation_span_m": (8000.0, 25000.0),
        "river_cell_fraction": (0.002, 0.08),
        "ice_cell_fraction": (0.005, 0.45),
        "calibration_pass_fraction": (0.75, 1.0),
        "realism_evidence_coverage_fraction": (0.65, 1.0),
        "applicable_realism_pass_fraction": (0.75, 1.0),
    }
    for metric, (lower, upper) in ranges.items():
        value = metrics.get(metric)
        numeric = _finite_number(value)
        _check(
            checks,
            domain="earthlike_profile",
            name=metric,
            passed=numeric and lower <= float(value) <= upper,
            message=f"Earth-like {metric} must fall in the declared broad validation envelope",
            observed=value,
            expected={"minimum": lower, "maximum": upper},
        )
    biome_count = int(metrics.get("biome_class_count", 0))
    _check(
        checks,
        domain="earthlike_profile",
        name="biome_diversity",
        passed=biome_count >= 6,
        message="Earth-like worlds need multiple climate-linked biome classes",
        observed=biome_count,
        expected={"minimum": 6},
    )


def _validate_geo_world_impl(
    world: dict[str, Any],
    *,
    profile: str = "generic",
) -> dict[str, Any]:
    """Deep validation of natural geography without reading civilization records.

    The report deliberately separates executable-contract integrity from empirical or
    scenario realism. A missing candidate population is `not_applicable`, never a
    successful realism observation.
    """
    checks: list[dict[str, Any]] = []
    if not isinstance(world, dict):
        _check(
            checks,
            domain="contract",
            name="world_object",
            passed=False,
            message="generated world JSON root must be an object",
            observed=type(world).__name__,
            expected="dict",
        )
        return _finalize_report(profile, {}, checks)
    summary = world.get("summary", {})
    cells = world.get("cells", [])
    if not isinstance(summary, dict):
        _check(
            checks,
            domain="contract",
            name="summary_object",
            passed=False,
            message="world.summary must be an object",
            observed=type(summary).__name__,
            expected="dict",
        )
        summary = {}
    if not isinstance(cells, list) or not cells:
        _check(
            checks,
            domain="contract",
            name="cell_payload_available",
            passed=False,
            message="deep geo validation requires output.include_cells=true and a non-empty cell payload",
            observed=len(cells) if isinstance(cells, list) else type(cells).__name__,
            expected="non-empty list",
        )
        return _finalize_report(profile, {}, checks)

    try:
        recorded_cell_count = int(summary.get("cell_count", -1))
    except (TypeError, ValueError, OverflowError):
        recorded_cell_count = -1
    _check(
        checks,
        domain="contract",
        name="cell_count",
        passed=recorded_cell_count == len(cells),
        message="summary cell count must match the exported natural mesh",
        observed={"summary": summary.get("cell_count"), "payload": len(cells)},
        expected="equal",
    )
    planet_parameters = world.get("planet_parameters", {})
    required_planet_parameters = {
        "radius_km",
        "gravity_g",
        "day_length_hours",
        "axial_tilt_deg",
        "orbital_eccentricity",
        "stellar_luminosity",
        "atmosphere_pressure_bar",
        "greenhouse_factor",
        "ocean_fraction_target",
        "ocean_water_inventory_km3",
        "internal_heat",
        "geological_age_ga",
    }
    valid_planet_parameters = (
        isinstance(planet_parameters, dict)
        and required_planet_parameters.issubset(planet_parameters)
        and all(_finite_number(planet_parameters.get(key)) for key in required_planet_parameters)
        and float(planet_parameters.get("radius_km", 0.0)) > 0.0
        and float(planet_parameters.get("gravity_g", 0.0)) > 0.0
        and float(planet_parameters.get("geological_age_ga", 0.0)) > 0.0
    )
    climate_model_present = isinstance(world.get("climate_model"), dict) and bool(world["climate_model"])
    sea_level_model_present = isinstance(world.get("sea_level_model"), dict) and bool(world["sea_level_model"])
    _check(
        checks,
        domain="contract",
        name="explicit_planet_and_physics_models",
        passed=valid_planet_parameters and climate_model_present and sea_level_model_present,
        message="deep validation requires explicit configured planet, climate, and sea-level model metadata",
        observed={
            "planet_parameter_keys": sorted(planet_parameters) if isinstance(planet_parameters, dict) else None,
            "climate_model_present": climate_model_present,
            "sea_level_model_present": sea_level_model_present,
        },
        expected={"planet_parameter_keys": sorted(required_planet_parameters)},
    )
    all_cells_are_objects = all(isinstance(cell, dict) for cell in cells)
    cell_ids = [cell.get("id") for cell in cells if isinstance(cell, dict)]
    integer_ids = all(isinstance(cell_id, int) and not isinstance(cell_id, bool) for cell_id in cell_ids)
    unique_ids = len(set(cell_ids)) == len(cells) if integer_ids and len(cell_ids) == len(cells) else False
    _check(
        checks,
        domain="mesh",
        name="unique_cell_ids",
        passed=all_cells_are_objects and integer_ids and unique_ids,
        message="every mesh cell must have one unique integer id",
        observed={"cell_count": len(cells), "unique_id_count": len(set(cell_ids)) if integer_ids else None},
        expected=len(cells),
    )
    if not all_cells_are_objects or not integer_ids or not unique_ids:
        return _finalize_report(profile, {"cell_count": len(cells)}, checks)

    cells_by_id = {int(cell["id"]): cell for cell in cells}
    required_numeric_fields = (
        "area_km2",
        "lat_deg",
        "lon_deg",
        "elevation_m",
        "water_depth_m",
        "temperature_c",
        "precipitation_mm_y",
        "actual_evapotranspiration_mm_y",
        "infiltration_mm_y",
        "runoff_mm_y",
        "flow_accumulation",
        "hydrologic_surface_elevation_m",
        "initial_crust_age_ma",
        "crust_age_ma",
        "ice_thickness_m",
        "groundwater_recharge_source_infiltration_mm_y",
        "groundwater_recharge_mm_y",
        "groundwater_recharge_km3_y",
        "vadose_zone_retention_mm_y",
        "groundwater_available_volume_km3_y",
        "groundwater_lateral_inflow_km3_y",
        "groundwater_internal_lateral_outflow_km3_y",
        "groundwater_discharge_km3_y",
        "groundwater_retained_storage_km3_y",
    )
    invalid_numeric: Counter[str] = Counter()
    for cell in cells:
        for field in required_numeric_fields:
            if not _finite_number(cell.get(field)):
                invalid_numeric[field] += 1
    _check(
        checks,
        domain="contract",
        name="finite_core_geo_fields",
        passed=not invalid_numeric,
        message="core physical fields must exist and contain finite numbers",
        observed=dict(sorted(invalid_numeric.items())),
        expected="zero invalid values",
    )
    if invalid_numeric:
        return _finalize_report(profile, {"cell_count": len(cells)}, checks)
    invalid_boolean_count = sum(
        not isinstance(cell.get(field), bool)
        for cell in cells
        for field in ("is_water", "is_lake", "is_river")
    )
    invalid_enum_count = sum(
        str(cell.get("crust_type", "")) not in ALLOWED_CRUST_TYPES
        or str(cell.get("biome", "")) not in ALLOWED_BIOMES
        for cell in cells
    )
    negative_state_count = sum(
        float(cell.get(field, 0.0)) < -1.0e-10
        for cell in cells
        for field in (
            "water_depth_m",
            "precipitation_mm_y",
            "actual_evapotranspiration_mm_y",
            "infiltration_mm_y",
            "runoff_mm_y",
            "flow_accumulation",
            "ice_thickness_m",
            "soil_depth_m",
        )
    )
    _check(
        checks,
        domain="contract",
        name="cell_types_enums_and_nonnegative_states",
        passed=invalid_boolean_count == 0 and invalid_enum_count == 0 and negative_state_count == 0,
        message="cell flags must be booleans, natural enums known, and conserved state magnitudes nonnegative",
        observed={
            "invalid_boolean_count": invalid_boolean_count,
            "invalid_enum_count": invalid_enum_count,
            "negative_state_count": negative_state_count,
        },
        expected="zero",
    )

    radius_km = _planet_value(world, "radius_km", 6371.0)
    expected_area = 4.0 * math.pi * radius_km * radius_km
    actual_area = sum(float(cell.get("area_km2", 0.0)) for cell in cells)
    area_error_fraction = abs(actual_area - expected_area) / max(1.0, expected_area)
    _check(
        checks,
        domain="mesh",
        name="spherical_surface_area_closure",
        passed=all(float(cell.get("area_km2", 0.0)) > 0.0 for cell in cells)
        and area_error_fraction <= 2.0e-6,
        message="cell areas must be positive and close to 4*pi*configured_radius^2",
        observed={
            "radius_km": radius_km,
            "area_km2": actual_area,
            "relative_error": area_error_fraction,
        },
        expected={"area_km2": expected_area, "maximum_relative_error": 2.0e-6},
    )
    vector_errors: list[float] = []
    coordinate_vector_errors: list[float] = []
    rounded_positions: set[tuple[float, float, float]] = set()
    invalid_coordinate_count = 0
    for cell in cells:
        vector = cell.get("position_3d")
        if not isinstance(vector, list) or len(vector) != 3 or not all(_finite_number(value) for value in vector):
            vector_errors.append(math.inf)
            coordinate_vector_errors.append(math.inf)
            continue
        vector_errors.append(abs(math.sqrt(sum(float(value) ** 2 for value in vector)) - 1.0))
        latitude = float(cell.get("lat_deg", math.nan))
        longitude = float(cell.get("lon_deg", math.nan))
        if not -90.0 <= latitude <= 90.0 or not -180.0 <= longitude <= 180.0:
            invalid_coordinate_count += 1
            coordinate_vector_errors.append(math.inf)
        else:
            latitude_rad = math.radians(latitude)
            longitude_rad = math.radians(longitude)
            expected_vector = (
                math.cos(latitude_rad) * math.cos(longitude_rad),
                math.cos(latitude_rad) * math.sin(longitude_rad),
                math.sin(latitude_rad),
            )
            coordinate_vector_errors.append(
                max(abs(float(actual) - expected) for actual, expected in zip(vector, expected_vector))
            )
        rounded_positions.add(tuple(round(float(value), 12) for value in vector))
    max_vector_error = max(vector_errors, default=math.inf)
    _check(
        checks,
        domain="mesh",
        name="unit_sphere_positions",
        passed=max_vector_error <= 1.0e-6,
        message="exported cell centers must lie on the unit sphere",
        observed=max_vector_error,
        expected={"maximum_norm_error": 1.0e-6},
    )
    maximum_coordinate_vector_error = max(coordinate_vector_errors, default=math.inf)
    _check(
        checks,
        domain="mesh",
        name="coordinate_position_consistency",
        passed=invalid_coordinate_count == 0
        and maximum_coordinate_vector_error <= 2.0e-6
        and len(rounded_positions) == len(cells),
        message="latitude/longitude must match unique exported unit-sphere positions",
        observed={
            "invalid_coordinate_count": invalid_coordinate_count,
            "maximum_vector_component_error": maximum_coordinate_vector_error,
            "unique_position_count": len(rounded_positions),
        },
        expected={"unique_position_count": len(cells), "maximum_component_error": 2.0e-6},
    )

    adjacency: dict[int, set[int]] = {}
    invalid_neighbor_links = 0
    self_links = 0
    for cell_id, cell in cells_by_id.items():
        raw_neighbors = cell.get("neighbors", [])
        if not isinstance(raw_neighbors, list):
            invalid_neighbor_links += 1
            adjacency[cell_id] = set()
            continue
        neighbors: set[int] = set()
        for raw_neighbor in raw_neighbors:
            if not isinstance(raw_neighbor, int) or raw_neighbor not in cells_by_id:
                invalid_neighbor_links += 1
            elif raw_neighbor == cell_id:
                self_links += 1
            else:
                neighbors.add(raw_neighbor)
        adjacency[cell_id] = neighbors
    asymmetric_links = sum(
        neighbor not in adjacency or cell_id not in adjacency[neighbor]
        for cell_id, neighbors in adjacency.items()
        for neighbor in neighbors
    )
    connected = _connected_count(next(iter(cells_by_id)), adjacency)
    _check(
        checks,
        domain="mesh",
        name="adjacency_graph_integrity",
        passed=invalid_neighbor_links == 0
        and self_links == 0
        and asymmetric_links == 0
        and connected == len(cells),
        message="mesh adjacency must be valid, symmetric, self-loop free, and connected",
        observed={
            "invalid_links": invalid_neighbor_links,
            "self_links": self_links,
            "asymmetric_directed_links": asymmetric_links,
            "connected_cell_count": connected,
        },
        expected={"connected_cell_count": len(cells)},
    )

    mesh_backend = str(world.get("mesh_backend", ""))
    cell_area_model = str(world.get("cell_area_model", ""))
    area_model_valid = False
    maximum_cell_area_error_km2 = math.inf
    face_count = 0
    if mesh_backend == "fibonacci_sphere" and cell_area_model == "equal_area_fibonacci_quadrature_v1":
        expected_cell_area = expected_area / len(cells)
        maximum_cell_area_error_km2 = max(
            abs(float(cell.get("area_km2", 0.0)) - expected_cell_area) for cell in cells
        )
        area_model_valid = maximum_cell_area_error_km2 <= max(0.01, expected_cell_area * 1.0e-8)
    elif mesh_backend == "geodesic_icosahedron" and cell_area_model == "spherical_barycentric_dual_v1":
        faces: set[tuple[int, int, int]] = set()
        for cell_id, neighbors in adjacency.items():
            sorted_neighbors = sorted(neighbors)
            for first_index, first_neighbor in enumerate(sorted_neighbors):
                for second_neighbor in sorted_neighbors[first_index + 1 :]:
                    if second_neighbor in adjacency.get(first_neighbor, set()):
                        faces.add(tuple(sorted((cell_id, first_neighbor, second_neighbor))))
        reconstructed_area_by_cell = {cell_id: 0.0 for cell_id in cells_by_id}
        for first_id, second_id, third_id in faces:
            first = [float(value) for value in cells_by_id[first_id]["position_3d"]]
            second = [float(value) for value in cells_by_id[second_id]["position_3d"]]
            third = [float(value) for value in cells_by_id[third_id]["position_3d"]]
            cross_second_third = (
                second[1] * third[2] - second[2] * third[1],
                second[2] * third[0] - second[0] * third[2],
                second[0] * third[1] - second[1] * third[0],
            )
            determinant = abs(sum(first[index] * cross_second_third[index] for index in range(3)))
            denominator = 1.0 + sum(first[index] * second[index] for index in range(3))
            denominator += sum(second[index] * third[index] for index in range(3))
            denominator += sum(third[index] * first[index] for index in range(3))
            face_area_km2 = 2.0 * math.atan2(determinant, max(1.0e-15, denominator)) * radius_km * radius_km
            share = face_area_km2 / 3.0
            reconstructed_area_by_cell[first_id] += share
            reconstructed_area_by_cell[second_id] += share
            reconstructed_area_by_cell[third_id] += share
        face_count = len(faces)
        maximum_cell_area_error_km2 = max(
            abs(reconstructed_area_by_cell[cell_id] - float(cell.get("area_km2", 0.0)))
            for cell_id, cell in cells_by_id.items()
        )
        expected_face_count = 2 * len(cells) - 4
        area_model_valid = (
            face_count == expected_face_count
            and maximum_cell_area_error_km2
            <= max(0.01, max(float(cell.get("area_km2", 0.0)) for cell in cells) * 1.0e-6)
        )
    _check(
        checks,
        domain="mesh",
        name="native_cell_area_model_replay",
        passed=area_model_valid,
        message="cell areas must independently replay the declared Fibonacci or geodesic spherical area model",
        observed={
            "mesh_backend": mesh_backend,
            "cell_area_model": cell_area_model,
            "face_count": face_count,
            "maximum_cell_area_error_km2": maximum_cell_area_error_km2,
        },
        expected={
            "fibonacci_model": "equal_area_fibonacci_quadrature_v1",
            "geodesic_model": "spherical_barycentric_dual_v1",
        },
    )

    edge_records = world.get("cell_adjacency_edges", [])
    invalid_scaled_edges = 0
    maximum_edge_distance_error_km = 0.0
    actual_edge_pairs: list[tuple[int, int]] = []
    expected_edge_pairs = {
        tuple(sorted((cell_id, neighbor_id)))
        for cell_id, neighbors in adjacency.items()
        for neighbor_id in neighbors
        if cell_id < neighbor_id
    }
    if isinstance(edge_records, list):
        for edge in edge_records:
            if not isinstance(edge, dict):
                invalid_scaled_edges += 1
                continue
            try:
                first_id = int(edge.get("cell_a_id", -1))
                second_id = int(edge.get("cell_b_id", -1))
            except (TypeError, ValueError):
                invalid_scaled_edges += 1
                continue
            first = cells_by_id.get(first_id)
            second = cells_by_id.get(second_id)
            actual_edge_pairs.append(tuple(sorted((first_id, second_id))))
            if first is None or second is None or not _finite_number(edge.get("great_circle_distance_km")):
                invalid_scaled_edges += 1
                continue
            first_vector = first.get("position_3d", [])
            second_vector = second.get("position_3d", [])
            if not (
                isinstance(first_vector, list)
                and isinstance(second_vector, list)
                and len(first_vector) == 3
                and len(second_vector) == 3
            ):
                invalid_scaled_edges += 1
                continue
            central_angle = math.acos(
                max(
                    -1.0,
                    min(
                        1.0,
                        sum(float(left) * float(right) for left, right in zip(first_vector, second_vector)),
                    ),
                )
            )
            expected_distance = central_angle * radius_km
            error = abs(float(edge["great_circle_distance_km"]) - expected_distance)
            maximum_edge_distance_error_km = max(maximum_edge_distance_error_km, error)
            if error > max(0.001, expected_distance * 1.0e-4):
                invalid_scaled_edges += 1
    else:
        invalid_scaled_edges = 1
    actual_edge_pair_set = set(actual_edge_pairs)
    edge_set_matches = (
        len(actual_edge_pairs) == len(actual_edge_pair_set)
        and actual_edge_pair_set == expected_edge_pairs
    )
    _check(
        checks,
        domain="mesh",
        name="configured_radius_distance_scaling",
        passed=bool(edge_records) and invalid_scaled_edges == 0 and edge_set_matches,
        message="natural-system great-circle distances must use the configured planet radius",
        observed={
            "edge_count": len(edge_records) if isinstance(edge_records, list) else None,
            "invalid_edge_count": invalid_scaled_edges,
            "expected_edge_count": len(expected_edge_pairs),
            "unique_recorded_edge_count": len(actual_edge_pair_set),
            "duplicate_edge_count": len(actual_edge_pairs) - len(actual_edge_pair_set),
            "missing_edge_count": len(expected_edge_pairs - actual_edge_pair_set),
            "unexpected_edge_count": len(actual_edge_pair_set - expected_edge_pairs),
            "maximum_distance_error_km": maximum_edge_distance_error_km,
        },
        expected={"radius_km": radius_km, "relative_tolerance": 1.0e-4},
    )

    plates = world.get("plates", [])
    plate_ids = {
        int(plate.get("id", -1))
        for plate in plates
        if isinstance(plate, dict) and isinstance(plate.get("id"), int)
    } if isinstance(plates, list) else set()
    invalid_plate_cells: list[int] = []
    for cell_id, cell in cells_by_id.items():
        try:
            plate_id = int(cell.get("plate_id", -1))
        except (TypeError, ValueError):
            invalid_plate_cells.append(cell_id)
            continue
        if plate_id not in plate_ids:
            invalid_plate_cells.append(cell_id)
    _check(
        checks,
        domain="tectonics",
        name="plate_assignment_coverage",
        passed=bool(plate_ids) and not invalid_plate_cells,
        message="every cell must belong to an exported tectonic plate",
        observed={"plate_count": len(plate_ids), "invalid_cell_count": len(invalid_plate_cells)},
        expected="all cells assigned",
    )
    maximum_planet_crust_age_ma = _planet_value(world, "geological_age_ga", 4.5) * 1000.0
    maximum_generated_crust_age_ma = max(
        max(
            float(cell.get("crust_age_ma", 0.0)),
            float(cell.get("initial_crust_age_ma", 0.0)),
        )
        for cell in cells
    )
    minimum_generated_crust_age_ma = min(
        min(
            float(cell.get("crust_age_ma", 0.0)),
            float(cell.get("initial_crust_age_ma", 0.0)),
        )
        for cell in cells
    )
    _check(
        checks,
        domain="tectonics",
        name="crust_age_within_planet_age",
        passed=minimum_generated_crust_age_ma >= 0.0
        and maximum_generated_crust_age_ma <= maximum_planet_crust_age_ma + 1.0e-6,
        message="generated crust cannot predate the configured planet",
        observed={
            "minimum_crust_age_ma": minimum_generated_crust_age_ma,
            "maximum_crust_age_ma": maximum_generated_crust_age_ma,
        },
        expected={"minimum_crust_age_ma": 0.0, "maximum_crust_age_ma": maximum_planet_crust_age_ma},
    )

    water_cells = [cell for cell in cells if bool(cell.get("is_water", False))]
    ocean_volume = sum(
        float(cell.get("area_km2", 0.0)) * float(cell.get("water_depth_m", 0.0)) / 1000.0
        for cell in water_cells
    )
    target_volume = _planet_value(
        world,
        "ocean_water_inventory_km3",
        float(world.get("sea_level_model", {}).get("ocean_water_inventory_km3", 0.0))
        if isinstance(world.get("sea_level_model"), dict)
        else 0.0,
    )
    volume_tolerance = max(0.01, abs(target_volume) * 1.0e-9)
    invalid_water_depths = sum(float(cell.get("water_depth_m", 0.0)) <= 0.0 for cell in water_cells)
    maximum_marine_depth_elevation_residual_m = max(
        (
            abs(float(cell.get("water_depth_m", 0.0)) + float(cell.get("elevation_m", 0.0)))
            for cell in water_cells
        ),
        default=0.0,
    )
    nonnegative_marine_elevation_count = sum(
        float(cell.get("elevation_m", 0.0)) >= 0.0 for cell in water_cells
    )
    invalid_land_depths = sum(
        abs(float(cell.get("water_depth_m", 0.0))) > 1.0e-6
        for cell in cells
        if not bool(cell.get("is_water", False)) and not bool(cell.get("is_lake", False))
    )
    _check(
        checks,
        domain="sea_level",
        name="ocean_inventory_closure",
        passed=abs(ocean_volume - target_volume) <= volume_tolerance
        and invalid_water_depths == 0
        and invalid_land_depths == 0
        and maximum_marine_depth_elevation_residual_m <= 1.0e-6
        and nonnegative_marine_elevation_count == 0,
        message="connected marine columns must close the configured ocean inventory",
        observed={
            "reconstructed_volume_km3": ocean_volume,
            "target_volume_km3": target_volume,
            "invalid_water_depth_count": invalid_water_depths,
            "nonzero_dry_land_depth_count": invalid_land_depths,
            "maximum_depth_plus_elevation_residual_m": maximum_marine_depth_elevation_residual_m,
            "nonnegative_marine_elevation_count": nonnegative_marine_elevation_count,
        },
        expected={"maximum_absolute_volume_error_km3": volume_tolerance},
    )
    if water_cells:
        water_ids = {int(cell["id"]) for cell in water_cells}
        water_adjacency = {cell_id: adjacency[cell_id] & water_ids for cell_id in water_ids}
        connected_water = _connected_count(next(iter(water_ids)), water_adjacency)
        water_connectivity_passed = connected_water == len(water_ids)
        below_sea_ids = {
            int(cell["id"])
            for cell in cells
            if float(cell.get("elevation_m", 0.0)) < 0.0
        }
        remaining = set(below_sea_ids)
        below_sea_components: list[set[int]] = []
        while remaining:
            start = min(remaining)
            component: set[int] = set()
            pending = [start]
            while pending:
                cell_id = pending.pop()
                if cell_id in component:
                    continue
                component.add(cell_id)
                pending.extend((adjacency.get(cell_id, set()) & below_sea_ids) - component)
            remaining -= component
            below_sea_components.append(component)
        largest_below_sea_component = max(
            below_sea_components,
            key=lambda component: (
                sum(float(cells_by_id[cell_id].get("area_km2", 0.0)) for cell_id in component),
                -min(component),
            ),
            default=set(),
        )
        largest_component_matches = water_ids == largest_below_sea_component
        water_evidence = {
            "connected_water_cell_count": connected_water,
            "water_cell_count": len(water_ids),
            "below_sea_component_count": len(below_sea_components),
            "largest_below_sea_component_cell_count": len(largest_below_sea_component),
            "marine_mask_matches_largest_below_sea_component": largest_component_matches,
        }
    else:
        water_connectivity_passed = target_volume == 0.0
        largest_component_matches = target_volume == 0.0
        water_evidence = {"connected_water_cell_count": 0, "water_cell_count": 0}
    sea_level_model = world.get("sea_level_model", {})
    reconstructed_ocean_area = sum(float(cell.get("area_km2", 0.0)) for cell in water_cells)
    reconstructed_ocean_fraction = reconstructed_ocean_area / max(1.0, actual_area)
    sea_level_model_matches = isinstance(sea_level_model, dict) and (
        int(sea_level_model.get("selected_ocean_cell_count", -1)) == len(water_cells)
        and int(sea_level_model.get("connected_ocean_component_count", -1))
        == (1 if water_cells else 0)
        and abs(float(sea_level_model.get("selected_ocean_area_km2", -1.0)) - reconstructed_ocean_area)
        <= max(0.01, reconstructed_ocean_area * 1.0e-6)
        and abs(float(sea_level_model.get("selected_ocean_volume_km3", -1.0)) - ocean_volume)
        <= volume_tolerance
        and abs(float(sea_level_model.get("selected_ocean_fraction", -1.0)) - reconstructed_ocean_fraction)
        <= 1.0e-6
    )
    _check(
        checks,
        domain="sea_level",
        name="single_connected_ocean",
        passed=water_connectivity_passed and largest_component_matches and sea_level_model_matches,
        message="marine water must be the largest connected below-sea component and match sea-level aggregates",
        observed=water_evidence,
        expected={"marine_component_count": 1 if water_cells else 0, "sea_level_model_matches": True},
    )

    invalid_monthly = 0
    temperature_residual = 0.0
    precipitation_residual = 0.0
    for cell in cells:
        temperatures = cell.get("temperature_monthly_c", [])
        precipitation = cell.get("precipitation_monthly_mm", [])
        winds_east = cell.get("wind_monthly_east", [])
        winds_north = cell.get("wind_monthly_north", [])
        arrays = (temperatures, precipitation, winds_east, winds_north)
        if any(
            not isinstance(values, list)
            or len(values) != 12
            or not all(_finite_number(value) for value in values)
            for values in arrays
        ):
            invalid_monthly += 1
            continue
        temperature_residual = max(
            temperature_residual,
            abs(float(cell.get("temperature_c", 0.0)) - sum(float(value) for value in temperatures) / 12.0),
        )
        precipitation_residual = max(
            precipitation_residual,
            abs(float(cell.get("precipitation_mm_y", 0.0)) - sum(float(value) for value in precipitation)),
        )
    _check(
        checks,
        domain="climate",
        name="monthly_annual_climate_closure",
        passed=invalid_monthly == 0
        and temperature_residual <= 1.0e-3
        and precipitation_residual <= 1.0e-2,
        message="twelve monthly climate values must reconstruct annual temperature and precipitation",
        observed={
            "invalid_cell_count": invalid_monthly,
            "maximum_temperature_residual_c": temperature_residual,
            "maximum_precipitation_residual_mm_y": precipitation_residual,
        },
        expected={"month_count": 12, "temperature_tolerance_c": 1.0e-3, "precipitation_tolerance_mm_y": 1.0e-2},
    )
    climate_model = world.get("climate_model", {})
    base_temperature = float(climate_model.get("base_temperature_c", 15.0)) if isinstance(climate_model, dict) else 15.0
    luminosity = _planet_value(world, "stellar_luminosity", 1.0)
    greenhouse = _planet_value(world, "greenhouse_factor", 1.0)
    pressure = _planet_value(world, "atmosphere_pressure_bar", 1.0)
    expected_global_temperature = (
        base_temperature
        + 38.0 * (luminosity ** 0.25 - 1.0)
        + 11.0 * (greenhouse - 1.0)
        + 4.5 * math.log(max(0.01, pressure))
    )
    observed_global_temperature = _area_weighted_mean(cells, "temperature_c")
    _check(
        checks,
        domain="climate",
        name="configured_global_temperature_response",
        passed=abs(observed_global_temperature - expected_global_temperature) <= 0.35,
        message="area-mean temperature must respond to configured stellar, greenhouse, and pressure forcing",
        observed=observed_global_temperature,
        expected={"temperature_c": expected_global_temperature, "tolerance_c": 0.35},
    )

    land_cells = [cell for cell in cells if not bool(cell.get("is_water", False))]
    water_budget_residual = 0.0
    marine_budget_nonzero = 0
    negative_budget_terms = 0
    for cell in cells:
        terms = [
            float(cell.get("actual_evapotranspiration_mm_y", 0.0)),
            float(cell.get("infiltration_mm_y", 0.0)),
            float(cell.get("runoff_mm_y", 0.0)),
        ]
        negative_budget_terms += sum(value < -1.0e-8 for value in terms)
        if bool(cell.get("is_water", False)):
            marine_budget_nonzero += any(abs(value) > 1.0e-6 for value in terms)
        else:
            water_budget_residual = max(
                water_budget_residual,
                abs(float(cell.get("precipitation_mm_y", 0.0)) - sum(terms)),
            )
    _check(
        checks,
        domain="hydrology",
        name="land_water_budget_closure",
        passed=water_budget_residual <= 2.0e-3
        and marine_budget_nonzero == 0
        and negative_budget_terms == 0,
        message="land precipitation must partition into AET, infiltration, and runoff; marine cells are excluded",
        observed={
            "maximum_cell_residual_mm_y": water_budget_residual,
            "marine_nonzero_partition_count": marine_budget_nonzero,
            "negative_term_count": negative_budget_terms,
        },
        expected={"maximum_cell_residual_mm_y": 2.0e-3},
    )
    recharge_residual = 0.0
    recharge_source_residual = 0.0
    recharge_volume_residual = 0.0
    groundwater_available_residual = 0.0
    groundwater_flow_residual = 0.0
    groundwater_negative_term_count = 0
    total_groundwater_internal_outflow = 0.0
    total_groundwater_lateral_inflow = 0.0
    expected_groundwater_inflow_by_cell: dict[int, float] = {
        cell_id: 0.0 for cell_id in cells_by_id
    }
    invalid_groundwater_links = 0
    marine_groundwater_nonzero_count = 0
    for cell in cells:
        cell_id = int(cell["id"])
        area_km2 = float(cell.get("area_km2", 0.0))
        source_infiltration = float(cell.get("groundwater_recharge_source_infiltration_mm_y", 0.0))
        recharge_mm = float(cell.get("groundwater_recharge_mm_y", 0.0))
        recharge_km3 = float(cell.get("groundwater_recharge_km3_y", 0.0))
        vadose_mm = float(cell.get("vadose_zone_retention_mm_y", 0.0))
        lateral_inflow = float(cell.get("groundwater_lateral_inflow_km3_y", 0.0))
        available = float(cell.get("groundwater_available_volume_km3_y", 0.0))
        internal_outflow = float(cell.get("groundwater_internal_lateral_outflow_km3_y", 0.0))
        discharge = float(cell.get("groundwater_discharge_km3_y", 0.0))
        retained = float(cell.get("groundwater_retained_storage_km3_y", 0.0))
        groundwater_negative_term_count += sum(
            value < -1.0e-10
            for value in (
                source_infiltration,
                recharge_mm,
                recharge_km3,
                vadose_mm,
                lateral_inflow,
                available,
                internal_outflow,
                discharge,
                retained,
            )
        )
        recharge_source_residual = max(
            recharge_source_residual,
            abs(source_infiltration - float(cell.get("infiltration_mm_y", 0.0))),
        )
        recharge_residual = max(
            recharge_residual,
            abs(source_infiltration - recharge_mm - vadose_mm),
        )
        recharge_volume_residual = max(
            recharge_volume_residual,
            abs(recharge_km3 - recharge_mm * area_km2 * 1.0e-6),
        )
        groundwater_available_residual = max(
            groundwater_available_residual,
            abs(available - recharge_km3 - lateral_inflow),
        )
        groundwater_flow_residual = max(
            groundwater_flow_residual,
            abs(available - internal_outflow - discharge - retained),
        )
        total_groundwater_internal_outflow += internal_outflow
        total_groundwater_lateral_inflow += lateral_inflow
        target_id = cell.get("groundwater_flow_to_cell_id", -1)
        if internal_outflow > 1.0e-10:
            if (
                not isinstance(target_id, int)
                or target_id not in cells_by_id
                or float(cells_by_id[target_id].get("groundwater_hydraulic_head_m", math.inf))
                >= float(cell.get("groundwater_hydraulic_head_m", -math.inf))
            ):
                invalid_groundwater_links += 1
            else:
                expected_groundwater_inflow_by_cell[target_id] += internal_outflow
        if bool(cell.get("is_water", False)) and any(
            abs(value) > 1.0e-8
            for value in (
                source_infiltration,
                recharge_mm,
                recharge_km3,
                vadose_mm,
                lateral_inflow,
                available,
                internal_outflow,
                discharge,
                retained,
            )
        ):
            marine_groundwater_nonzero_count += 1
    groundwater_transfer_residual = abs(
        total_groundwater_internal_outflow - total_groundwater_lateral_inflow
    )
    maximum_groundwater_receiver_residual = max(
        abs(
            expected_groundwater_inflow_by_cell[cell_id]
            - float(cell.get("groundwater_lateral_inflow_km3_y", 0.0))
        )
        for cell_id, cell in cells_by_id.items()
    )
    _check(
        checks,
        domain="hydrology",
        name="groundwater_partition_closure",
        passed=recharge_source_residual <= 2.0e-4
        and recharge_residual <= 2.0e-4
        and recharge_volume_residual <= 2.0e-5
        and groundwater_available_residual <= 2.0e-5
        and groundwater_flow_residual <= 2.0e-5
        and groundwater_transfer_residual <= 1.0e-3
        and maximum_groundwater_receiver_residual <= 1.0e-3
        and groundwater_negative_term_count == 0
        and invalid_groundwater_links == 0
        and marine_groundwater_nonzero_count == 0,
        message="infiltration-to-recharge, volume conversion, and groundwater routing partitions must close",
        observed={
            "maximum_source_infiltration_residual_mm_y": recharge_source_residual,
            "maximum_recharge_partition_residual_mm_y": recharge_residual,
            "maximum_recharge_volume_residual_km3_y": recharge_volume_residual,
            "maximum_available_volume_residual_km3_y": groundwater_available_residual,
            "maximum_groundwater_flow_residual_km3_y": groundwater_flow_residual,
            "global_internal_transfer_residual_km3_y": groundwater_transfer_residual,
            "maximum_receiver_inflow_residual_km3_y": maximum_groundwater_receiver_residual,
            "negative_term_count": groundwater_negative_term_count,
            "invalid_groundwater_link_count": invalid_groundwater_links,
            "marine_nonzero_groundwater_count": marine_groundwater_nonzero_count,
        },
        expected={"recharge_tolerance_mm_y": 2.0e-4, "flow_tolerance_km3_y": 2.0e-5},
    )
    hydraulics_model = world.get("river_hydraulics_model", {})
    configured_gravity_m_s2 = _planet_value(world, "gravity_g", 1.0) * 9.80665
    recorded_gravity = (
        hydraulics_model.get("gravity_m_s2") if isinstance(hydraulics_model, dict) else None
    )
    _check(
        checks,
        domain="hydrology",
        name="configured_gravity_propagation",
        passed=_finite_number(recorded_gravity)
        and abs(float(recorded_gravity) - configured_gravity_m_s2) <= 1.0e-9,
        message="river dynamics must use configured relative surface gravity",
        observed=recorded_gravity,
        expected=configured_gravity_m_s2,
    )

    flow_to: dict[int, int] = {}
    invalid_flow_targets = 0
    uphill_flow_links = 0
    nonneighbor_flow_links = 0
    invalid_river_cells = 0
    for cell_id, cell in cells_by_id.items():
        target = cell.get("flow_to", -1)
        if not isinstance(target, int):
            invalid_flow_targets += 1
            continue
        if target >= 0 and target not in cells_by_id:
            invalid_flow_targets += 1
            continue
        flow_to[cell_id] = target
        if bool(cell.get("is_water", False)) and target != -1:
            invalid_flow_targets += 1
        if target >= 0 and target not in adjacency.get(cell_id, set()):
            nonneighbor_flow_links += 1
        if target >= 0 and (
            float(cells_by_id[target].get("hydrologic_surface_elevation_m", 0.0))
            >= float(cell.get("hydrologic_surface_elevation_m", 0.0)) - 1.0e-9
        ):
            uphill_flow_links += 1
        if bool(cell.get("is_river", False)) and (
            bool(cell.get("is_water", False))
            or target < 0
            or float(cell.get("runoff_mm_y", 0.0)) <= 10.0
        ):
            invalid_river_cells += 1
    cycles = _cycle_nodes(flow_to)
    reconstructed_accumulation = {
        cell_id: (
            0.0
            if bool(cell.get("is_water", False))
            else float(cell.get("runoff_mm_y", 0.0)) * float(cell.get("area_km2", 0.0))
        )
        for cell_id, cell in cells_by_id.items()
    }
    indegree = {cell_id: 0 for cell_id in cells_by_id}
    for target in flow_to.values():
        if target >= 0 and target in indegree:
            indegree[target] += 1
    pending = deque(sorted(cell_id for cell_id, degree in indegree.items() if degree == 0))
    processed_flow_count = 0
    while pending:
        cell_id = pending.popleft()
        processed_flow_count += 1
        target = flow_to.get(cell_id, -1)
        if target >= 0 and target in cells_by_id:
            if not bool(cells_by_id[cell_id].get("is_water", False)):
                reconstructed_accumulation[target] += reconstructed_accumulation[cell_id]
            indegree[target] -= 1
            if indegree[target] == 0:
                pending.append(target)
    maximum_accumulation_residual = max(
        abs(reconstructed_accumulation[cell_id] - float(cell.get("flow_accumulation", 0.0)))
        for cell_id, cell in cells_by_id.items()
    )
    maximum_accumulation_scale = max(reconstructed_accumulation.values(), default=1.0)
    output_float_precision = max(0, int(summary.get("output_float_precision", 4)))
    accumulation_quantization_tolerance = (
        actual_area * 0.5 * 10.0 ** (-output_float_precision)
    )
    accumulation_tolerance = max(
        0.001,
        maximum_accumulation_scale * 1.0e-8,
        accumulation_quantization_tolerance,
    )
    watershed_records = world.get("watersheds", [])
    watershed_basin_ids = {
        int(record.get("basin_id", -1))
        for record in watershed_records
        if isinstance(record, dict)
    } if isinstance(watershed_records, list) else set()
    watershed_by_basin = {
        int(record.get("basin_id", -1)): record
        for record in watershed_records
        if isinstance(record, dict)
    } if isinstance(watershed_records, list) else {}
    land_basin_ids = {
        int(cell.get("basin_id", -1))
        for cell in cells
        if not bool(cell.get("is_water", False))
    }
    invalid_terminal_count = 0
    for cell_id, cell in cells_by_id.items():
        if bool(cell.get("is_water", False)):
            continue
        terminal_id = cell_id
        for _ in range(len(cells) + 1):
            next_id = flow_to.get(terminal_id, -1)
            if next_id < 0:
                break
            terminal_id = next_id
        terminal = cells_by_id[terminal_id]
        terminal_watershed = watershed_by_basin.get(
            int(terminal.get("basin_id", -1)), {}
        )
        if not (
            bool(terminal.get("is_water", False))
            or bool(terminal.get("is_lake", False))
            or bool(terminal.get("is_closed_basin", False))
            or (
                isinstance(terminal_watershed, dict)
                and (
                    str(terminal_watershed.get("outlet_type", "")) == "closed_land"
                    or bool(terminal_watershed.get("is_endorheic", False))
                )
            )
        ):
            invalid_terminal_count += 1
    _check(
        checks,
        domain="hydrology",
        name="acyclic_downhill_drainage",
        passed=invalid_flow_targets == 0
        and nonneighbor_flow_links == 0
        and uphill_flow_links == 0
        and not cycles
        and processed_flow_count == len(cells)
        and maximum_accumulation_residual <= accumulation_tolerance
        and invalid_river_cells == 0
        and invalid_terminal_count == 0
        and land_basin_ids == watershed_basin_ids,
        message="drainage must be adjacent, strictly downhill, acyclic, accumulation-conserving, and terminate in valid basins",
        observed={
            "invalid_target_count": invalid_flow_targets,
            "nonneighbor_link_count": nonneighbor_flow_links,
            "uphill_link_count": uphill_flow_links,
            "cycle_cell_count": len(cycles),
            "processed_flow_cell_count": processed_flow_count,
            "maximum_accumulation_residual": maximum_accumulation_residual,
            "accumulation_tolerance": accumulation_tolerance,
            "invalid_river_cell_count": invalid_river_cells,
            "invalid_terminal_count": invalid_terminal_count,
            "land_basin_count": len(land_basin_ids),
            "watershed_basin_count": len(watershed_basin_ids),
        },
        expected="zero",
    )

    sediment_models = (
        "hillslope_sediment_transport_model",
        "fluvial_sediment_routing_model",
        "glacial_sediment_transport_model",
        "sediment_inventory_model",
    )
    sediment_residuals: dict[str, float] = {}
    for model_name in sediment_models:
        model = world.get(model_name, {})
        if not isinstance(model, dict):
            sediment_residuals[f"{model_name}.missing"] = math.inf
            continue
        for field, value in model.items():
            if "residual" in field and _finite_number(value):
                sediment_residuals[f"{model_name}.{field}"] = abs(float(value))
    required_sediment_residual_fields = {
        "hillslope_sediment_transport_model.total_mass_balance_residual_km3",
        "fluvial_sediment_routing_model.total_mass_balance_residual_km3",
        "glacial_sediment_transport_model.total_mass_balance_residual_km3",
        "glacial_sediment_transport_model.total_terrain_volume_change_residual_km3",
        "sediment_inventory_model.gross_throughput_mass_balance_residual_km3",
        "sediment_inventory_model.source_partition_residual_km3",
        "sediment_inventory_model.inventory_mass_balance_residual_km3",
        "sediment_inventory_model.cell_source_partition_residual_km3",
    }
    maximum_sediment_residual = max(sediment_residuals.values(), default=math.inf)
    hillslope_model = world.get("hillslope_sediment_transport_model", {})
    fluvial_model = world.get("fluvial_sediment_routing_model", {})
    glacial_model = world.get("glacial_sediment_transport_model", {})
    inventory_model = world.get("sediment_inventory_model", {})

    def sediment_number(model: Any, field: str) -> float:
        if not isinstance(model, dict) or not _finite_number(model.get(field)):
            return math.nan
        return float(model[field])

    hillslope_production = sediment_number(hillslope_model, "total_production_volume_km3")
    hillslope_deposition = sediment_number(hillslope_model, "total_deposition_volume_km3")
    hillslope_alluvium = sediment_number(hillslope_model, "total_alluvium_entrainment_volume_km3")
    hillslope_bedrock = sediment_number(hillslope_model, "total_bedrock_erosion_volume_km3")
    fluvial_source = sediment_number(fluvial_model, "total_local_source_volume_km3")
    fluvial_deposition = sediment_number(fluvial_model, "total_deposition_volume_km3")
    fluvial_export = sediment_number(fluvial_model, "total_terminal_export_volume_km3")
    fluvial_alluvium = sediment_number(fluvial_model, "total_alluvium_entrainment_volume_km3")
    fluvial_bedrock = sediment_number(fluvial_model, "total_bedrock_erosion_volume_km3")
    glacial_production = sediment_number(glacial_model, "total_production_volume_km3")
    glacial_deposition = sediment_number(glacial_model, "total_deposition_volume_km3")
    glacial_alluvium = sediment_number(glacial_model, "total_alluvium_entrainment_volume_km3")
    glacial_bedrock = sediment_number(glacial_model, "total_bedrock_erosion_volume_km3")
    inventory_gross = sediment_number(inventory_model, "gross_mobilization_volume_km3")
    inventory_deposition = sediment_number(inventory_model, "deposition_volume_km3")
    inventory_export = sediment_number(inventory_model, "terminal_export_volume_km3")
    inventory_alluvium = sediment_number(inventory_model, "alluvium_entrainment_volume_km3")
    inventory_bedrock = sediment_number(inventory_model, "bedrock_erosion_volume_km3")
    inventory_final = sediment_number(inventory_model, "final_mobile_sediment_inventory_volume_km3")
    numeric_partition = (
        inventory_model.get("process_source_partition", {}).get("numeric_breach", {})
        if isinstance(inventory_model, dict)
        and isinstance(inventory_model.get("process_source_partition"), dict)
        else {}
    )
    numeric_gross = sediment_number(numeric_partition, "gross_mobilization_volume_km3")
    reconstructed_sediment_residuals = {
        "hillslope_production_minus_deposition": hillslope_production - hillslope_deposition,
        "hillslope_source_partition": hillslope_production - hillslope_alluvium - hillslope_bedrock,
        "fluvial_source_minus_deposition_export": fluvial_source - fluvial_deposition - fluvial_export,
        "fluvial_source_partition": fluvial_source - fluvial_alluvium - fluvial_bedrock,
        "glacial_production_minus_deposition": glacial_production - glacial_deposition,
        "glacial_source_partition": glacial_production - glacial_alluvium - glacial_bedrock,
        "inventory_gross_minus_deposition_export": inventory_gross - inventory_deposition - inventory_export,
        "inventory_source_partition": inventory_gross - inventory_alluvium - inventory_bedrock,
        "inventory_bedrock_source_minus_final_export": inventory_bedrock - inventory_final - inventory_export,
        "inventory_process_sum": inventory_gross
        - hillslope_production
        - fluvial_source
        - glacial_production
        - numeric_gross,
        "inventory_export_matches_fluvial": inventory_export - fluvial_export,
    }
    history_specs = (
        (
            "hillslope_sediment_transport_history",
            hillslope_model,
            {
                "production_volume_km3": "total_production_volume_km3",
                "deposition_volume_km3": "total_deposition_volume_km3",
                "alluvium_entrainment_volume_km3": "total_alluvium_entrainment_volume_km3",
                "bedrock_erosion_volume_km3": "total_bedrock_erosion_volume_km3",
            },
        ),
        (
            "fluvial_sediment_routing_history",
            fluvial_model,
            {
                "local_source_volume_km3": "total_local_source_volume_km3",
                "total_deposition_volume_km3": "total_deposition_volume_km3",
                "terminal_export_volume_km3": "total_terminal_export_volume_km3",
                "alluvium_entrainment_volume_km3": "total_alluvium_entrainment_volume_km3",
                "bedrock_erosion_volume_km3": "total_bedrock_erosion_volume_km3",
            },
        ),
        (
            "glacial_sediment_transport_history",
            glacial_model,
            {
                "production_volume_km3": "total_production_volume_km3",
                "deposition_volume_km3": "total_deposition_volume_km3",
                "alluvium_entrainment_volume_km3": "total_alluvium_entrainment_volume_km3",
                "bedrock_erosion_volume_km3": "total_bedrock_erosion_volume_km3",
            },
        ),
    )
    for history_name, model, fields in history_specs:
        history = world.get(history_name, [])
        for history_field, model_field in fields.items():
            if not isinstance(history, list) or any(
                not isinstance(record, dict) or not _finite_number(record.get(history_field))
                for record in history
            ):
                reconstructed_sediment_residuals[f"{history_name}.{history_field}"] = math.nan
            else:
                reconstructed_sediment_residuals[f"{history_name}.{history_field}"] = (
                    sum(float(record[history_field]) for record in history)
                    - sediment_number(model, model_field)
                )
    numeric_history = world.get("numeric_depression_fill_history", [])
    if isinstance(numeric_history, list) and all(
        isinstance(record, dict)
        and _finite_number(record.get("applied_breach_excavation_volume_km3"))
        for record in numeric_history
    ):
        reconstructed_sediment_residuals["numeric_history_gross"] = (
            sum(float(record["applied_breach_excavation_volume_km3"]) for record in numeric_history)
            - numeric_gross
        )
    else:
        reconstructed_sediment_residuals["numeric_history_gross"] = math.nan
    reconstructed_cell_inventory = sum(
        float(cell.get("sediment_thickness_m", 0.0))
        * float(cell.get("area_km2", 0.0))
        / 1000.0
        for cell in cells
    )
    reconstructed_sediment_residuals["cell_final_inventory"] = (
        reconstructed_cell_inventory - inventory_final
    )
    negative_sediment_volume_count = sum(
        value < -1.0e-10
        for value in (
            hillslope_production,
            hillslope_deposition,
            hillslope_alluvium,
            hillslope_bedrock,
            fluvial_source,
            fluvial_deposition,
            fluvial_export,
            fluvial_alluvium,
            fluvial_bedrock,
            glacial_production,
            glacial_deposition,
            glacial_alluvium,
            glacial_bedrock,
            inventory_gross,
            inventory_deposition,
            inventory_export,
            inventory_alluvium,
            inventory_bedrock,
            inventory_final,
            numeric_gross,
            reconstructed_cell_inventory,
        )
        if math.isfinite(value)
    )
    sediment_scale = max(
        1.0,
        *(
            abs(value)
            for value in (
                hillslope_production,
                fluvial_source,
                glacial_production,
                inventory_gross,
            )
            if math.isfinite(value)
        ),
    )
    reconstructed_tolerance_km3 = max(0.01, sediment_scale * 1.0e-10)
    cell_inventory_tolerance_km3 = max(
        0.01,
        actual_area * 0.5 * 10.0 ** (-output_float_precision) / 1000.0,
    )
    maximum_reconstructed_residual = max(
        (
            abs(value)
            for key, value in reconstructed_sediment_residuals.items()
            if key != "cell_final_inventory"
        ),
        default=math.inf,
    )
    reconstructed_values_finite = all(
        math.isfinite(value) for value in reconstructed_sediment_residuals.values()
    )
    _check(
        checks,
        domain="sediment",
        name="sediment_mass_conservation",
        passed=required_sediment_residual_fields.issubset(sediment_residuals)
        and maximum_sediment_residual <= reconstructed_tolerance_km3
        and reconstructed_values_finite
        and maximum_reconstructed_residual <= reconstructed_tolerance_km3
        and abs(reconstructed_sediment_residuals["cell_final_inventory"])
        <= cell_inventory_tolerance_km3
        and negative_sediment_volume_count == 0,
        message="reported and independently reconstructed sediment transport/inventory ledgers must close",
        observed={
            "maximum_reported_residual_km3": maximum_sediment_residual,
            "maximum_reconstructed_residual_km3": maximum_reconstructed_residual,
            "reported_residual_count": len(sediment_residuals),
            "missing_required_residuals": sorted(required_sediment_residual_fields - set(sediment_residuals)),
            "negative_volume_count": negative_sediment_volume_count,
            "cell_inventory_residual_km3": reconstructed_sediment_residuals["cell_final_inventory"],
            "cell_inventory_tolerance_km3": cell_inventory_tolerance_km3,
        },
        expected={
            "required_reported_residuals": sorted(required_sediment_residual_fields),
            "maximum_absolute_residual_km3": reconstructed_tolerance_km3,
        },
        evidence={
            "reported_residuals": sediment_residuals,
            "reconstructed_residuals": reconstructed_sediment_residuals,
        },
    )

    clock = world.get("simulation_clock", {})
    erosion_iterations = int(clock.get("configured_erosion_iteration_count", -1)) if isinstance(clock, dict) else -1
    stage_count = int(clock.get("stage_count", -1)) if isinstance(clock, dict) else -1
    feedback = world.get("earth_system_feedback_history", [])
    expected_stage_count = erosion_iterations + 2
    _check(
        checks,
        domain="simulation",
        name="coupled_stage_clock",
        passed=erosion_iterations >= 0
        and stage_count == expected_stage_count
        and isinstance(feedback, list)
        and len(feedback) == stage_count,
        message="simulation clock must contain initial, configured erosion, and final cryosphere stages",
        observed={
            "erosion_iterations": erosion_iterations,
            "stage_count": stage_count,
            "feedback_record_count": len(feedback) if isinstance(feedback, list) else None,
        },
        expected={"stage_count": expected_stage_count},
    )

    energy_records = world.get("climate_energy_balance_records", [])
    energy_cell_ids: set[int] = set()
    invalid_energy_records = 0
    if isinstance(energy_records, list):
        for record in energy_records:
            if not isinstance(record, dict):
                invalid_energy_records += 1
                continue
            try:
                cell_id = int(record.get("cell_id", -1))
            except (TypeError, ValueError):
                invalid_energy_records += 1
                continue
            cell = cells_by_id.get(cell_id)
            required_energy_fields = (
                "top_of_atmosphere_insolation_w_m2",
                "absorbed_shortwave_w_m2",
                "outgoing_longwave_w_m2",
                "greenhouse_trapping_w_m2",
                "net_radiative_balance_w_m2",
                "energy_balance_residual_c",
            )
            if (
                cell is None
                or cell_id in energy_cell_ids
                or any(not _finite_number(record.get(field)) for field in required_energy_fields)
                or abs(float(record.get("temperature_c", math.inf)) - float(cell["temperature_c"])) > 1.0e-3
            ):
                invalid_energy_records += 1
            energy_cell_ids.add(cell_id)
    else:
        invalid_energy_records = 1
    _check(
        checks,
        domain="climate",
        name="climate_energy_record_coverage",
        passed=invalid_energy_records == 0 and energy_cell_ids == set(cells_by_id),
        message="every cell must have one finite climate-energy diagnostic tied to its generated temperature",
        observed={
            "record_count": len(energy_records) if isinstance(energy_records, list) else None,
            "unique_cell_count": len(energy_cell_ids),
            "invalid_record_count": invalid_energy_records,
        },
        expected={"unique_cell_count": len(cells)},
    )

    ice_sheets = world.get("ice_sheets", [])
    ice_sheet_records = {
        int(record.get("id", -1)): record
        for record in ice_sheets
        if isinstance(record, dict) and isinstance(record.get("id"), int)
    } if isinstance(ice_sheets, list) else {}
    invalid_ice_cells = 0
    invalid_glacier_links = 0
    for cell_id, cell in cells_by_id.items():
        ice_thickness = float(cell.get("ice_thickness_m", 0.0))
        ice_sheet_id = cell.get("ice_sheet_id", -1)
        if ice_thickness < 0.0 or (
            ice_thickness > 25.0
            and not bool(cell.get("is_water", False))
            and (not isinstance(ice_sheet_id, int) or ice_sheet_id not in ice_sheet_records)
        ):
            invalid_ice_cells += 1
        glacier_target = cell.get("glacier_flow_to", -1)
        if not isinstance(glacier_target, int):
            invalid_glacier_links += 1
        elif glacier_target >= 0 and (
            glacier_target not in adjacency.get(cell_id, set())
            or ice_thickness <= 0.0
            or float(cells_by_id[glacier_target].get("elevation_m", 0.0))
            > float(cell.get("elevation_m", 0.0)) + 1.0e-6
        ):
            invalid_glacier_links += 1
    invalid_ice_sheet_records = 0
    for sheet_id, record in ice_sheet_records.items():
        members = [
            cell
            for cell in cells
            if int(cell.get("ice_sheet_id", -1)) == sheet_id
            and float(cell.get("ice_thickness_m", 0.0)) > 25.0
            and not bool(cell.get("is_water", False))
        ]
        member_area = sum(float(cell.get("area_km2", 0.0)) for cell in members)
        mean_thickness = (
            sum(
                float(cell.get("ice_thickness_m", 0.0))
                * float(cell.get("area_km2", 0.0))
                for cell in members
            )
            / member_area
            if member_area > 0.0
            else 0.0
        )
        if (
            int(record.get("cell_count", -1)) != len(members)
            or abs(float(record.get("area_km2", -1.0)) - member_area) > max(0.01, member_area * 1.0e-6)
            or abs(float(record.get("mean_ice_thickness_m", -1.0)) - mean_thickness) > 1.0e-3
        ):
            invalid_ice_sheet_records += 1
    _check(
        checks,
        domain="cryosphere",
        name="ice_sheet_and_flow_coherence",
        passed=invalid_ice_cells == 0
        and invalid_glacier_links == 0
        and invalid_ice_sheet_records == 0
        and len(ice_sheet_records) == (len(ice_sheets) if isinstance(ice_sheets, list) else -1),
        message="ice must be nonnegative, assigned to coherent sheets, and flow to lower adjacent cells",
        observed={
            "ice_sheet_count": len(ice_sheet_records),
            "invalid_ice_cell_count": invalid_ice_cells,
            "invalid_glacier_link_count": invalid_glacier_links,
            "invalid_ice_sheet_record_count": invalid_ice_sheet_records,
        },
        expected="zero invalid records",
    )

    soil_profiles = world.get("soil_profiles", [])
    eligible_soil_ids = {
        int(cell["id"])
        for cell in cells
        if str(cell.get("water_body_type", "land")) == "land"
        and str(cell.get("soil_type", "none")) != "none"
        and float(cell.get("soil_depth_m", 0.0)) > 0.0
    }
    soil_cell_ids: set[int] = set()
    soil_profile_id_by_cell: dict[int, int] = {}
    invalid_soil_profiles = 0
    if isinstance(soil_profiles, list):
        for profile_record in soil_profiles:
            if not isinstance(profile_record, dict):
                invalid_soil_profiles += 1
                continue
            try:
                cell_id = int(profile_record.get("cell_id", -1))
            except (TypeError, ValueError):
                invalid_soil_profiles += 1
                continue
            cell = cells_by_id.get(cell_id)
            bounded_values = (
                profile_record.get("drainage_index"),
                profile_record.get("moisture_index"),
                profile_record.get("organic_matter_fraction"),
                profile_record.get("salinity_index"),
                profile_record.get("erodibility_index"),
                profile_record.get("development_index"),
            )
            if (
                cell is None
                or cell_id in soil_cell_ids
                or not _finite_number(profile_record.get("total_depth_m"))
                or float(profile_record["total_depth_m"]) < 0.0
                or not _finite_number(profile_record.get("ph"))
                or not 0.0 <= float(profile_record["ph"]) <= 14.0
                or any(not _finite_number(value) or not 0.0 <= float(value) <= 1.0 for value in bounded_values)
                or abs(float(profile_record["total_depth_m"]) - float(cell.get("soil_depth_m", -1.0))) > 1.0e-5
                or str(profile_record.get("soil_type", "")) != str(cell.get("soil_type", ""))
                or int(profile_record.get("id", -1)) != int(cell.get("soil_profile_id", -2))
            ):
                invalid_soil_profiles += 1
            soil_cell_ids.add(cell_id)
            if isinstance(profile_record.get("id"), int):
                soil_profile_id_by_cell[cell_id] = int(profile_record["id"])
    else:
        invalid_soil_profiles = 1
    invalid_ineligible_soil_state = sum(
        int(cell.get("soil_profile_id", -1)) != -1
        or int(cell.get("soil_horizon_count", 0)) != 0
        for cell_id, cell in cells_by_id.items()
        if cell_id not in eligible_soil_ids
    )
    _check(
        checks,
        domain="soil_biome",
        name="soil_profile_coverage_and_bounds",
        passed=invalid_soil_profiles == 0
        and invalid_ineligible_soil_state == 0
        and soil_cell_ids == eligible_soil_ids,
        message="every eligible land/soil/depth cell must have one bounded soil profile mirroring the cell state",
        observed={
            "eligible_cell_count": len(eligible_soil_ids),
            "profile_cell_count": len(soil_cell_ids),
            "invalid_profile_count": invalid_soil_profiles,
            "invalid_ineligible_cell_count": invalid_ineligible_soil_state,
        },
        expected={"profile_cell_ids": "water_body=land, soil_type!=none, depth>0"},
    )

    biome_diagnostics = world.get("biome_diagnostics", [])
    biome_cell_ids: set[int] = set()
    invalid_biome_diagnostics = 0
    if isinstance(biome_diagnostics, list):
        for diagnostic in biome_diagnostics:
            if not isinstance(diagnostic, dict):
                invalid_biome_diagnostics += 1
                continue
            try:
                cell_id = int(diagnostic.get("cell_id", -1))
            except (TypeError, ValueError):
                invalid_biome_diagnostics += 1
                continue
            cell = cells_by_id.get(cell_id)
            if (
                cell is None
                or cell_id in biome_cell_ids
                or str(diagnostic.get("biome", "")) != str(cell.get("biome", ""))
                or not _finite_number(diagnostic.get("biome_confidence_index"))
                or not 0.0 <= float(diagnostic["biome_confidence_index"]) <= 1.0
            ):
                invalid_biome_diagnostics += 1
            biome_cell_ids.add(cell_id)
    else:
        invalid_biome_diagnostics = 1
    _check(
        checks,
        domain="soil_biome",
        name="biome_diagnostic_coverage",
        passed=invalid_biome_diagnostics == 0 and biome_cell_ids == set(cells_by_id),
        message="every cell must have one bounded biome diagnostic mirroring its assigned biome",
        observed={
            "diagnostic_cell_count": len(biome_cell_ids),
            "invalid_diagnostic_count": invalid_biome_diagnostics,
        },
        expected={"diagnostic_cell_count": len(cells)},
    )

    # Replay the diagnostic producer from its natural inputs.  A shallow mirror
    # check cannot detect a cell biome and its diagnostic label being edited
    # together, while this also verifies all derived water/seasonality fields.
    biome_replay_world: dict[str, Any] = {
        "cells": deepcopy(cells),
        "summary": {},
    }
    enrich_world_with_biome_diagnostics(biome_replay_world)
    expected_biome_diagnostics = biome_replay_world.get("biome_diagnostics", [])
    actual_biome_by_id = {
        int(record.get("id", -1)): record
        for record in biome_diagnostics
        if isinstance(record, dict) and isinstance(record.get("id"), int)
    } if isinstance(biome_diagnostics, list) else {}

    def biome_value_matches(actual: Any, expected: Any) -> bool:
        if isinstance(expected, bool):
            return type(actual) is bool and actual is expected
        if isinstance(expected, (int, float)) and not isinstance(expected, bool):
            return _finite_number(actual) and abs(float(actual) - float(expected)) <= 1.0e-6
        return actual == expected

    invalid_biome_replay_records = 0
    for expected_record in expected_biome_diagnostics:
        record_id = int(expected_record.get("id", -1))
        actual_record = actual_biome_by_id.get(record_id)
        if actual_record is None or any(
            not biome_value_matches(actual_record.get(key), expected_value)
            for key, expected_value in expected_record.items()
        ):
            invalid_biome_replay_records += 1
    biome_cell_output_fields = (
        "potential_evapotranspiration_mm_y",
        "climatic_water_deficit_mm_y",
        "climatic_water_surplus_mm_y",
        "growing_season_months",
        "frost_months",
        "dry_season_months",
        "wet_season_months",
        "fire_frequency_index",
        "biome_confidence_index",
        "ecotone_index",
        "biome_transition_zone",
    )
    invalid_biome_replay_cells = sum(
        any(
            not biome_value_matches(
                cells_by_id[cell_id].get(field),
                expected_cell.get(field),
            )
            for field in biome_cell_output_fields
        )
        for cell_id, expected_cell in {
            int(cell.get("id", -1)): cell
            for cell in biome_replay_world["cells"]
            if isinstance(cell, dict)
        }.items()
        if cell_id in cells_by_id
    )
    expected_biome_summary = biome_replay_world.get("summary", {})
    invalid_biome_summary_fields = [
        key
        for key, expected_value in expected_biome_summary.items()
        if not biome_value_matches(summary.get(key), expected_value)
    ]
    _check(
        checks,
        domain="soil_biome",
        name="biome_diagnostic_causal_replay",
        passed=invalid_biome_replay_records == 0
        and invalid_biome_replay_cells == 0
        and not invalid_biome_summary_fields
        and len(actual_biome_by_id) == len(expected_biome_diagnostics),
        message="biome diagnostics, cell derivatives, and aggregates must replay from climate and soil inputs",
        observed={
            "invalid_record_count": invalid_biome_replay_records,
            "invalid_cell_count": invalid_biome_replay_cells,
            "invalid_summary_fields": invalid_biome_summary_fields,
        },
        expected="exact producer replay within output precision",
    )

    resource_deposits = world.get("resource_deposits", [])
    deposit_ids: set[int] = set()
    invalid_deposits = 0
    if isinstance(resource_deposits, list):
        for deposit in resource_deposits:
            if not isinstance(deposit, dict):
                invalid_deposits += 1
                continue
            deposit_id = deposit.get("id")
            cell_id = deposit.get("cell_id")
            if (
                not isinstance(deposit_id, int)
                or deposit_id in deposit_ids
                or not isinstance(cell_id, int)
                or cell_id not in cells_by_id
                or str(deposit.get("resource", "")) != str(cells_by_id.get(cell_id, {}).get("resource", ""))
                or any(
                    not _finite_number(deposit.get(field))
                    or not 0.0 <= float(deposit[field]) <= 1.0
                    for field in (
                        "reserve_potential_index",
                        "extraction_hazard_index",
                        "renewability_index",
                        "geologic_confidence_index",
                    )
                )
            ):
                invalid_deposits += 1
            if isinstance(deposit_id, int):
                deposit_ids.add(deposit_id)
    else:
        invalid_deposits = 1
    commodity_occurrences = world.get("commodity_occurrences", [])
    invalid_commodity_links = 0
    if isinstance(commodity_occurrences, list):
        invalid_commodity_links = sum(
            not isinstance(record, dict)
            or int(record.get("resource_deposit_id", -1)) not in deposit_ids
            or int(record.get("cell_id", -1)) not in cells_by_id
            for record in commodity_occurrences
        )
    else:
        invalid_commodity_links = 1
    _check(
        checks,
        domain="natural_resources",
        name="deposit_and_commodity_linkage",
        passed=invalid_deposits == 0 and invalid_commodity_links == 0,
        message="natural deposits must mirror source cells and every commodity must link to a valid deposit",
        observed={
            "deposit_count": len(deposit_ids),
            "invalid_deposit_count": invalid_deposits,
            "invalid_commodity_link_count": invalid_commodity_links,
        },
        expected="zero invalid links",
    )

    watersheds_for_graph = world.get("watersheds", [])
    watershed_ids = {
        int(record.get("id", -1))
        for record in watersheds_for_graph
        if isinstance(record, dict) and isinstance(record.get("id"), int)
    } if isinstance(watersheds_for_graph, list) else set()
    river_cell_ids = {
        int(cell["id"]) for cell in cells if bool(cell.get("is_river", False))
    }
    physical_graph_expectations = {
        "plate_graph": {
            "source_ids": plate_ids,
            "node_source_field": "plate_id",
            "edge_fields": ("plate_a", "plate_b"),
            "edge_source_ids": plate_ids,
        },
        "river_graph": {
            "source_ids": river_cell_ids,
            "node_source_field": "cell_id",
            "edge_fields": ("from_cell_id", "to_cell_id"),
            "edge_source_ids": set(cells_by_id),
        },
        "watershed_graph": {
            "source_ids": watershed_ids,
            "node_source_field": "watershed_id",
            "edge_fields": ("watershed_a", "watershed_b"),
            "edge_source_ids": watershed_ids,
        },
    }
    invalid_physical_graphs = 0
    graph_evidence: dict[str, Any] = {}
    for graph_name, expectation in physical_graph_expectations.items():
        expected_source_ids = expectation["source_ids"]
        graph = world.get(graph_name, {})
        graph_shape_valid = (
            isinstance(graph, dict)
            and isinstance(graph.get("nodes"), list)
            and isinstance(graph.get("edges"), list)
        )
        node_ids: list[int] = []
        node_source_ids: list[int] = []
        edge_ids: list[int] = []
        edge_pairs: list[tuple[int, int]] = []
        invalid_edge_semantics = 0
        if graph_shape_valid:
            for node in graph["nodes"]:
                if not isinstance(node, dict):
                    graph_shape_valid = False
                    continue
                try:
                    node_ids.append(int(node.get("id", -1)))
                    node_source_ids.append(int(node.get(expectation["node_source_field"], -1)))
                except (TypeError, ValueError, OverflowError):
                    graph_shape_valid = False
            first_edge_field, second_edge_field = expectation["edge_fields"]
            for edge in graph["edges"]:
                if not isinstance(edge, dict):
                    graph_shape_valid = False
                    continue
                try:
                    edge_id = int(edge.get("id", -1))
                    first_endpoint = int(edge.get(first_edge_field, -1))
                    second_endpoint = int(edge.get(second_edge_field, -1))
                except (TypeError, ValueError, OverflowError):
                    graph_shape_valid = False
                    continue
                edge_ids.append(edge_id)
                edge_pairs.append((first_endpoint, second_endpoint))
                if (
                    first_endpoint == second_endpoint
                    or first_endpoint not in expectation["edge_source_ids"]
                    or second_endpoint not in expectation["edge_source_ids"]
                    or (
                        graph_name == "river_graph"
                        and (
                            first_endpoint not in river_cell_ids
                            or int(cells_by_id[first_endpoint].get("flow_to", -1)) != second_endpoint
                        )
                    )
                ):
                    invalid_edge_semantics += 1
        valid = graph_shape_valid and (
            int(graph.get("node_count", -1)) == len(expected_source_ids)
            and len(graph["nodes"]) == len(expected_source_ids)
            and set(node_ids) == set(range(len(node_ids)))
            and len(node_ids) == len(set(node_ids))
            and set(node_source_ids) == expected_source_ids
            and len(node_source_ids) == len(set(node_source_ids))
            and int(graph.get("edge_count", -1)) == len(graph["edges"])
            and set(edge_ids) == set(range(len(edge_ids)))
            and len(edge_ids) == len(set(edge_ids))
            and len({tuple(sorted(pair)) for pair in edge_pairs}) == len(edge_pairs)
            and invalid_edge_semantics == 0
        )
        invalid_physical_graphs += not valid
        graph_evidence[graph_name] = {
            "expected_node_count": len(expected_source_ids),
            "recorded_node_count": graph.get("node_count") if isinstance(graph, dict) else None,
            "invalid_edge_semantics_count": invalid_edge_semantics,
            "valid": valid,
        }
    _check(
        checks,
        domain="natural_graphs",
        name="physical_graph_coverage",
        passed=invalid_physical_graphs == 0,
        message="plate, river, and watershed graph counts must mirror their natural source records",
        observed=graph_evidence,
        expected="all physical graphs valid",
    )

    watershed_segments = world.get("watershed_boundary_segments", [])
    adjacency_edges_by_id = {
        int(edge.get("id", -1)): edge
        for edge in edge_records
        if isinstance(edge, dict) and isinstance(edge.get("id"), int)
    } if isinstance(edge_records, list) else {}
    basin_to_watershed_id = {
        int(record.get("basin_id", -1)): int(record.get("id", -1))
        for record in watersheds_for_graph
        if isinstance(record, dict)
    } if isinstance(watersheds_for_graph, list) else {}
    expected_boundary_source_ids: set[int] = set()
    for edge_id, edge in adjacency_edges_by_id.items():
        first_cell = cells_by_id.get(int(edge.get("cell_a_id", -1)))
        second_cell = cells_by_id.get(int(edge.get("cell_b_id", -1)))
        if first_cell is None or second_cell is None:
            continue
        first_basin = int(first_cell.get("basin_id", -1))
        second_basin = int(second_cell.get("basin_id", -1))
        if (
            first_basin in basin_to_watershed_id
            and second_basin in basin_to_watershed_id
            and basin_to_watershed_id[first_basin]
            != basin_to_watershed_id[second_basin]
        ):
            expected_boundary_source_ids.add(edge_id)
    recorded_boundary_source_ids: set[int] = set()
    invalid_boundary_segments = 0
    total_boundary_length_km = 0.0
    if isinstance(watershed_segments, list):
        segment_ids: set[int] = set()
        for segment in watershed_segments:
            if not isinstance(segment, dict):
                invalid_boundary_segments += 1
                continue
            try:
                segment_id = int(segment.get("id", -1))
                source_edge_id = int(segment.get("source_edge_id", -1))
                first_cell_id = int(segment.get("cell_a_id", -1))
                second_cell_id = int(segment.get("cell_b_id", -1))
                first_basin = int(segment.get("basin_a_id", -1))
                second_basin = int(segment.get("basin_b_id", -1))
                first_watershed = int(segment.get("watershed_a_id", -1))
                second_watershed = int(segment.get("watershed_b_id", -1))
                length_km = float(segment.get("length_km", math.nan))
                quality = float(segment.get("boundary_segment_quality", math.nan))
            except (TypeError, ValueError, OverflowError):
                invalid_boundary_segments += 1
                continue
            source_edge = adjacency_edges_by_id.get(source_edge_id, {})
            expected_cells = {
                int(source_edge.get("cell_a_id", -1)),
                int(source_edge.get("cell_b_id", -1)),
            }
            if (
                segment_id in segment_ids
                or source_edge_id in recorded_boundary_source_ids
                or source_edge_id not in expected_boundary_source_ids
                or {first_cell_id, second_cell_id} != expected_cells
                or first_basin == second_basin
                or basin_to_watershed_id.get(first_basin) != first_watershed
                or basin_to_watershed_id.get(second_basin) != second_watershed
                or not math.isfinite(length_km)
                or length_km <= 0.0
                or abs(length_km - float(source_edge.get("boundary_segment_length_km", -1.0)))
                > max(0.001, length_km * 1.0e-5)
                or not math.isfinite(quality)
                or not 0.0 <= quality <= 1.0
            ):
                invalid_boundary_segments += 1
            segment_ids.add(segment_id)
            recorded_boundary_source_ids.add(source_edge_id)
            total_boundary_length_km += length_km if math.isfinite(length_km) else 0.0
        if segment_ids != set(range(len(watershed_segments))):
            invalid_boundary_segments += 1
    else:
        invalid_boundary_segments = 1
    boundary_summary_matches = (
        int(summary.get("watershed_cell_edge_boundary_segment_count", -1))
        == (len(watershed_segments) if isinstance(watershed_segments, list) else -1)
        and abs(
            float(summary.get("watershed_cell_edge_boundary_length_km", -1.0))
            - total_boundary_length_km
        )
        <= max(0.01, total_boundary_length_km * 1.0e-6)
    )
    _check(
        checks,
        domain="natural_graphs",
        name="watershed_boundary_ledger",
        passed=invalid_boundary_segments == 0
        and recorded_boundary_source_ids == expected_boundary_source_ids
        and boundary_summary_matches,
        message="watershed boundary segments must exactly mirror cross-basin physical adjacency edges",
        observed={
            "expected_segment_count": len(expected_boundary_source_ids),
            "recorded_segment_count": len(recorded_boundary_source_ids),
            "invalid_segment_count": invalid_boundary_segments,
            "summary_matches": boundary_summary_matches,
        },
        expected="exact source-edge coverage",
    )

    calibration_records = world.get("calibration_checks", [])
    calibration_integrity = isinstance(calibration_records, list)
    calibration_names: list[str] = []
    calibration_ids: list[Any] = []
    recomputed_calibration_pass_count = 0
    if isinstance(calibration_records, list):
        for record in calibration_records:
            if not isinstance(record, dict):
                calibration_integrity = False
                continue
            metric = str(record.get("metric", ""))
            calibration_names.append(metric)
            calibration_ids.append(record.get("id"))
            range_passed = _realism_record_range_passed(record)
            recomputed_calibration_pass_count += range_passed
            calibration_integrity = calibration_integrity and (
                isinstance(record.get("passed"), bool)
                and bool(record["passed"]) == range_passed
                and _finite_number(record.get("score"))
                and 0.0 <= float(record["score"]) <= 1.0
                and isinstance(record.get("dataset"), str)
                and bool(record["dataset"])
                and isinstance(record.get("layer"), str)
                and bool(record["layer"])
            )
    calibration_integrity = calibration_integrity and (
        len(calibration_names) == len(CALIBRATION_EXPECTED_METRICS)
        and set(calibration_names) == CALIBRATION_EXPECTED_METRICS
        and len(set(calibration_names)) == len(calibration_names)
        and all(isinstance(record_id, int) and not isinstance(record_id, bool) for record_id in calibration_ids)
        and len(set(calibration_ids)) == len(calibration_ids)
        and int(summary.get("calibration_check_count", -1)) == len(calibration_names)
        and int(summary.get("calibration_pass_count", -1)) == recomputed_calibration_pass_count
        and abs(
            float(summary.get("calibration_pass_fraction", -1.0))
            - recomputed_calibration_pass_count / max(1, len(calibration_names))
        )
        <= 1.0e-4
    )
    _check(
        checks,
        domain="earth_calibration",
        name="built_in_calibration_integrity",
        passed=calibration_integrity,
        message="built-in Earth comparison records, ranges, declared results, and summary must agree",
        observed={
            "metrics": calibration_names,
            "recomputed_pass_count": recomputed_calibration_pass_count,
            "summary_pass_count": summary.get("calibration_pass_count"),
        },
        expected={"metrics": sorted(CALIBRATION_EXPECTED_METRICS)},
    )

    for replay_check in validate_physics_replays(world):
        replay_check = dict(replay_check)
        replay_check["id"] = len(checks)
        checks.append(replay_check)
    for subsystem_check in validate_natural_subsystems(world):
        subsystem_check = dict(subsystem_check)
        subsystem_check["id"] = len(checks)
        checks.append(subsystem_check)

    _validate_realism_evidence(world, checks)
    metrics = extract_geo_metrics(world)
    if profile == "earthlike":
        _validate_earthlike_profile(metrics, checks)
    elif profile != "generic":
        _check(
            checks,
            domain="contract",
            name="known_validation_profile",
            passed=False,
            message="unknown geo validation profile",
            observed=profile,
            expected=["generic", "earthlike"],
        )
    return _finalize_report(profile, metrics, checks)


def validate_geo_world(
    world: dict[str, Any],
    *,
    profile: str = "generic",
) -> dict[str, Any]:
    """Validate a natural world and report malformed payloads instead of raising.

    Generated output is normally well typed, but this entry point also validates
    externally supplied JSON.  Any unexpected coercion or shape error is therefore
    a failed contract check, never an exception escaping to the caller.
    """
    try:
        return _validate_geo_world_impl(world, profile=profile)
    except Exception as exc:
        checks: list[dict[str, Any]] = []
        _check(
            checks,
            domain="contract",
            name="malformed_optional_payload",
            passed=False,
            message="natural-world payload contains a malformed value or shape",
            observed={"exception_type": type(exc).__name__, "detail": str(exc)},
            expected="all exported natural fields are type-safe and internally coherent",
        )
        return _finalize_report(profile, {}, checks)


def _finalize_report(
    profile: str,
    metrics: dict[str, Any],
    checks: list[dict[str, Any]],
) -> dict[str, Any]:
    error_failures = [
        check for check in checks if check["status"] == "failed" and check["severity"] == "error"
    ]
    warning_failures = [
        check for check in checks if check["status"] == "failed" and check["severity"] == "warning"
    ]
    not_applicable = [check for check in checks if check["status"] == "not_applicable"]
    passed = [check for check in checks if check["status"] == "passed"]
    domains: dict[str, dict[str, int]] = {}
    for check in checks:
        domain = domains.setdefault(
            str(check["domain"]),
            {"check_count": 0, "passed_count": 0, "failed_count": 0, "not_applicable_count": 0},
        )
        domain["check_count"] += 1
        domain[f"{check['status']}_count"] += 1
    return {
        "schema_version": GEO_VALIDATION_SCHEMA_VERSION,
        "report_type": "geo_world_validation_v1",
        "scope": GEO_VALIDATION_SCOPE,
        "excluded_scope": "settlements, navigation/ports/routes, politics, territory, culture, history, population, economy, conflict, logistics, markets, campaigns, and language",
        "model_limitations": list(GEO_MODEL_LIMITATIONS),
        "profile": profile,
        "passed": not error_failures,
        "summary": {
            "check_count": len(checks),
            "passed_count": len(passed),
            "error_failure_count": len(error_failures),
            "warning_failure_count": len(warning_failures),
            "not_applicable_count": len(not_applicable),
            "domains": domains,
        },
        "metrics": metrics,
        "checks": checks,
    }
