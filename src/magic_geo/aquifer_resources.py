from __future__ import annotations

from copy import deepcopy
from collections import Counter
from typing import Any


MARINE_WATER_TYPES = {"ocean", "continental_shelf", "inland_sea"}
ALLUVIAL_LANDFORMS = {"floodplain", "delta", "river_valley", "coastal_plain", "lacustrine_basin", "glacial_lake"}
GROUNDWATER_RECHARGE_MODEL = "infiltration_bounded_aquifer_recharge_v1"
AQUIFER_RESOURCE_MODEL = "finite_recharge_causal_aquifer_resources_v1"
MIN_RECHARGE_FRACTION = 0.05
MAX_RECHARGE_FRACTION = 0.85
MIN_SYSTEM_PRODUCTIVITY_INDEX = 0.18
MIN_SYSTEM_RECHARGE_MM_Y = 25.0


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _permeability(lithology: str, landform: str) -> float:
    base = {
        "limestone": 0.82,
        "sandstone": 0.76,
        "basalt": 0.44,
        "volcanic": 0.48,
        "granite": 0.30,
        "metamorphic": 0.28,
        "shale": 0.18,
    }.get(lithology, 0.34)
    if landform in {"rift_valley", "glacial_valley"}:
        base += 0.10
    if landform in ALLUVIAL_LANDFORMS:
        base += 0.08
    return _clamp(base)


def _aquifer_class(productivity: float, storage: float, quality: float, recharge_mm_y: float, salinity: float) -> str:
    if quality < 0.34 or salinity >= 0.58:
        return "brackish_or_saline_aquifer"
    if productivity >= 0.66 and quality >= 0.55:
        return "major_fresh_aquifer"
    if storage >= 0.54 and recharge_mm_y < 65.0:
        return "fossil_or_slow_recharge_aquifer"
    if productivity >= 0.38:
        return "local_fresh_aquifer"
    if recharge_mm_y >= 80.0:
        return "perched_recharge_zone"
    return "poor_aquifer"


def _primary_key(counter: Counter[str], fallback: str) -> str:
    if not counter:
        return fallback
    return sorted(counter.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _build_aquifer(world: dict[str, Any], *, natural: bool = False) -> dict[str, Any]:
    cells = world.get("cells", [])
    if not isinstance(cells, list) or (not cells and not natural):
        return world

    basin_groups: dict[int, list[dict[str, Any]]] = {}
    class_counts: Counter[str] = Counter()
    aquifer_cell_count = 0
    recharge_cell_count = 0
    high_productivity_count = 0
    stressed_cell_count = 0
    recharge_sum_mm = 0.0
    recharge_sum_km3 = 0.0
    source_infiltration_sum_km3 = 0.0
    vadose_retention_sum_km3 = 0.0
    recharge_residual_sum_km3 = 0.0
    storage_sum = 0.0
    quality_sum = 0.0
    productivity_sum = 0.0
    risk_sum = 0.0

    for cell in cells:
        water_body = str(cell.get("water_body_type", "land"))
        lithology = str(cell.get("lithology", "unknown"))
        landform = str(cell.get("landform", "unknown"))
        area_km2 = max(0.0, float(cell.get("area_km2", 0.0)))
        marine_excluded = water_body in MARINE_WATER_TYPES
        if marine_excluded:
            source_infiltration_mm_y = 0.0
            recharge_fraction = 0.0
            recharge_mm_y = 0.0
            recharge_km3_y = 0.0
            vadose_retention_mm_y = 0.0
            vadose_retention_km3_y = 0.0
            recharge_residual_mm_y = 0.0
            storage = 0.0
            quality = 0.0
            productivity = 0.0
            extraction_risk = 0.0
            aquifer_class = "marine_excluded"
        else:
            permeability = _permeability(lithology, landform)
            sediment = _clamp(float(cell.get("sediment_thickness_m", 0.0)) / 3.0)
            drainage = _clamp(float(cell.get("soil_drainage_index", 0.0)))
            moisture = _clamp(float(cell.get("soil_moisture_index", 0.0)))
            salinity = _clamp(float(cell.get("soil_salinity_index", 0.0)))
            aridity = _clamp(float(cell.get("seasonal_aridity_index", 0.0)))
            ice = _clamp(float(cell.get("ice_thickness_m", 0.0)) / 1600.0)
            flow = _clamp(float(cell.get("flow_accumulation", 0.0)) / 40_000_000.0)
            settlement = 0.0 if natural else _clamp(float(cell.get("settlement_score", 0.0)))
            closed_basin = bool(cell.get("is_closed_basin", False))
            fresh_lake_bonus = 0.16 if water_body == "fresh_lake" else 0.0
            alluvial_bonus = 0.15 if landform in ALLUVIAL_LANDFORMS else 0.0
            source_infiltration_mm_y = max(
                0.0,
                float(cell.get("infiltration_mm_y", 0.0)),
            )
            recharge_fraction = _clamp(
                0.08
                + permeability * 0.45
                + drainage * 0.18
                + sediment * 0.12
                + (0.04 if water_body == "fresh_lake" else 0.0)
                - salinity * 0.10
                - ice * 0.12
                - aridity * 0.06,
                MIN_RECHARGE_FRACTION,
                MAX_RECHARGE_FRACTION,
            )
            recharge_mm_y = source_infiltration_mm_y * recharge_fraction
            recharge_km3_y = recharge_mm_y * area_km2 * 0.000001
            vadose_retention_mm_y = source_infiltration_mm_y - recharge_mm_y
            vadose_retention_km3_y = (
                vadose_retention_mm_y * area_km2 * 0.000001
            )
            recharge_residual_mm_y = (
                source_infiltration_mm_y
                - recharge_mm_y
                - vadose_retention_mm_y
            )
            storage = _clamp(
                0.08
                + permeability * 0.34
                + sediment * 0.26
                + moisture * 0.12
                + alluvial_bonus
                + fresh_lake_bonus * 0.7
                - aridity * 0.10
                - ice * 0.12
            )
            quality = _clamp(
                0.80
                + _clamp(recharge_mm_y / 360.0) * 0.16
                + (0.05 if lithology == "limestone" else 0.0)
                - salinity * 0.50
                - (0.18 if closed_basin else 0.0)
                - (0.18 if water_body == "saline_basin" else 0.0)
                - aridity * 0.08
            )
            extraction_risk = _clamp(
                0.14
                + aridity * 0.30
                + settlement * 0.18
                + (1.0 - _clamp(recharge_mm_y / 240.0)) * 0.20
                + salinity * 0.18
                + ice * 0.10
                + (0.08 if closed_basin else 0.0)
            )
            productivity = _clamp(
                storage * 0.38
                + _clamp(recharge_mm_y / 320.0) * 0.34
                + quality * 0.18
                + flow * 0.08
                - extraction_risk * 0.16
            )
            aquifer_class = _aquifer_class(productivity, storage, quality, recharge_mm_y, salinity)

        cell["groundwater_recharge_source_infiltration_mm_y"] = round(
            source_infiltration_mm_y, 6
        )
        cell["groundwater_recharge_fraction"] = round(recharge_fraction, 6)
        cell["groundwater_recharge_mm_y"] = round(recharge_mm_y, 6)
        cell["groundwater_recharge_km3_y"] = round(recharge_km3_y, 6)
        cell["vadose_zone_retention_mm_y"] = round(vadose_retention_mm_y, 6)
        cell["vadose_zone_retention_km3_y"] = round(
            vadose_retention_km3_y, 6
        )
        cell["groundwater_recharge_mass_balance_residual_mm_y"] = round(
            recharge_residual_mm_y, 10
        )
        cell["aquifer_storage_index"] = round(storage, 6)
        cell["aquifer_quality_index"] = round(quality, 6)
        cell["aquifer_productivity_index"] = round(productivity, 6)
        cell[("aquifer_natural_limitation_index" if natural else "aquifer_extraction_risk_index")] = round(extraction_risk, 6)
        cell["aquifer_class"] = aquifer_class
        cell["aquifer_system_id"] = -1

        class_counts[aquifer_class] += 1
        if aquifer_class != "marine_excluded":
            aquifer_cell_count += 1
            recharge_sum_mm += recharge_mm_y
            recharge_sum_km3 += recharge_km3_y
            source_infiltration_sum_km3 += (
                source_infiltration_mm_y * area_km2 * 0.000001
            )
            vadose_retention_sum_km3 += vadose_retention_km3_y
            recharge_residual_sum_km3 += (
                recharge_residual_mm_y * area_km2 * 0.000001
            )
            storage_sum += storage
            quality_sum += quality
            productivity_sum += productivity
            risk_sum += extraction_risk
            recharge_cell_count += 1 if recharge_mm_y >= 50.0 else 0
            high_productivity_count += 1 if productivity >= 0.65 else 0
            stressed_cell_count += 1 if extraction_risk >= 0.65 else 0
            if (
                productivity >= MIN_SYSTEM_PRODUCTIVITY_INDEX
                or recharge_mm_y >= MIN_SYSTEM_RECHARGE_MM_Y
            ):
                basin_id = int(cell.get("basin_id", -1))
                basin_groups.setdefault(basin_id, []).append(cell)

    systems: list[dict[str, Any]] = []
    for basin_id, group in sorted(basin_groups.items()):
        if not group:
            continue
        system_id = len(systems)
        for cell in group:
            cell["aquifer_system_id"] = system_id
        area_sum = sum(max(0.0, float(cell.get("area_km2", 0.0))) for cell in group)
        recharge_mm_sum = sum(float(cell.get("groundwater_recharge_mm_y", 0.0)) for cell in group)
        recharge_volume_sum = sum(float(cell.get("groundwater_recharge_km3_y", 0.0)) for cell in group)
        storage_group_sum = sum(float(cell.get("aquifer_storage_index", 0.0)) for cell in group)
        quality_group_sum = sum(float(cell.get("aquifer_quality_index", 0.0)) for cell in group)
        productivity_group_sum = sum(float(cell.get("aquifer_productivity_index", 0.0)) for cell in group)
        risk_group_sum = sum(float(cell.get(("aquifer_natural_limitation_index" if natural else "aquifer_extraction_risk_index"), 0.0)) for cell in group)
        class_counter = Counter(str(cell.get("aquifer_class", "unknown")) for cell in group)
        lithology_counter = Counter(str(cell.get("lithology", "unknown")) for cell in group)
        landform_counter = Counter(str(cell.get("landform", "unknown")) for cell in group)
        group_count = len(group)
        systems.append(
            {
                "id": system_id,
                "basin_id": basin_id,
                "aquifer_class": _primary_key(class_counter, "poor_aquifer"),
                "primary_lithology": _primary_key(lithology_counter, "unknown"),
                "dominant_landform": _primary_key(landform_counter, "unknown"),
                "cell_count": group_count,
                "cell_ids": [int(cell.get("id", -1)) for cell in group],
                "area_km2": round(area_sum, 6),
                "mean_groundwater_recharge_mm_y": round(recharge_mm_sum / group_count, 6),
                "total_groundwater_recharge_km3_y": round(recharge_volume_sum, 6),
                "mean_aquifer_storage_index": round(storage_group_sum / group_count, 6),
                "mean_aquifer_quality_index": round(quality_group_sum / group_count, 6),
                "mean_aquifer_productivity_index": round(productivity_group_sum / group_count, 6),
                ("mean_aquifer_natural_limitation_index" if natural else "mean_aquifer_extraction_risk_index"): round(risk_group_sum / group_count, 6),
                "recharge_cell_count": sum(1 for cell in group if float(cell.get("groundwater_recharge_mm_y", 0.0)) >= 50.0),
                "high_productivity_cell_count": sum(1 for cell in group if float(cell.get("aquifer_productivity_index", 0.0)) >= 0.65),
                ("high_natural_limitation_cell_count" if natural else "stressed_cell_count"): sum(1 for cell in group if float(cell.get(("aquifer_natural_limitation_index" if natural else "aquifer_extraction_risk_index"), 0.0)) >= 0.65),
                "closed_basin_fraction": round(sum(1 for cell in group if bool(cell.get("is_closed_basin", False))) / group_count, 6),
                "aquifer_class_counts": dict(sorted(class_counter.items())),
            }
        )

    divisor = aquifer_cell_count if aquifer_cell_count else 1
    world["aquifer_resource_model"] = {
        "model_type": AQUIFER_RESOURCE_MODEL,
        "source_recharge_model": GROUNDWATER_RECHARGE_MODEL,
        "domain": "non_marine_cells",
        "permeability_model": "lithology_with_rift_glacial_and_alluvial_landform_adjustments_v1",
        "storage_model": "permeability_sediment_moisture_alluvium_lake_aridity_ice_v1",
        "quality_model": "recharge_limestone_salinity_closed_basin_aridity_v1",
        "extraction_risk_model": "aridity_settlement_low_recharge_salinity_ice_closed_basin_v1",
        "productivity_model": "storage_recharge_quality_flow_extraction_risk_v1",
        "classification_model": "quality_salinity_productivity_storage_recharge_thresholds_v1",
        "system_grouping_model": "basin_id_over_productivity_or_recharge_eligible_cells_v1",
        "minimum_system_productivity_index": MIN_SYSTEM_PRODUCTIVITY_INDEX,
        "minimum_system_recharge_mm_y": MIN_SYSTEM_RECHARGE_MM_Y,
        "marine_cell_treatment": "zero_properties_marine_excluded_class_and_no_system",
        "deterministic": True,
        "aquifer_cell_count": aquifer_cell_count,
        "system_eligible_cell_count": sum(
            len(group) for group in basin_groups.values()
        ),
        "aquifer_system_count": len(systems),
        "model_limitation": "diagnostic_annual_resource_properties_without_transient_saturated_flow_storage_drawdown_or_geochemistry",
    }
    world["groundwater_recharge_model"] = {
        "model_type": GROUNDWATER_RECHARGE_MODEL,
        "source_field": "infiltration_mm_y",
        "domain": "non_marine_cells",
        "recharge_fraction_model": (
            "lithology_soil_drainage_sediment_lake_salinity_ice_aridity_v1"
        ),
        "minimum_recharge_fraction": MIN_RECHARGE_FRACTION,
        "maximum_recharge_fraction": MAX_RECHARGE_FRACTION,
        "marine_cell_treatment": "zero_source_recharge_and_vadose_retention",
        "mass_conserving_source_partition": True,
        "total_source_infiltration_volume_km3_y": round(
            source_infiltration_sum_km3, 9
        ),
        "total_groundwater_recharge_volume_km3_y": round(
            recharge_sum_km3, 9
        ),
        "total_vadose_zone_retention_volume_km3_y": round(
            vadose_retention_sum_km3, 9
        ),
        "mass_balance_residual_km3_y": round(
            recharge_residual_sum_km3, 12
        ),
        "model_limitation": (
            "annual_diagnostic_partition_without_transient_vadose_storage_or_groundwater_return_flow"
        ),
    }
    world["aquifer_systems"] = systems
    summary = world.setdefault("summary", {})
    summary["aquifer_resource_model"] = AQUIFER_RESOURCE_MODEL
    summary["groundwater_recharge_model"] = GROUNDWATER_RECHARGE_MODEL
    summary["aquifer_cell_count"] = aquifer_cell_count
    summary["aquifer_system_count"] = len(systems)
    summary["groundwater_recharge_cell_count"] = recharge_cell_count
    summary["high_productivity_aquifer_cell_count"] = high_productivity_count
    summary[("high_natural_limitation_aquifer_cell_count" if natural else "groundwater_stressed_cell_count")] = stressed_cell_count
    summary["total_groundwater_recharge_km3_y"] = round(recharge_sum_km3, 6)
    summary["total_groundwater_recharge_source_infiltration_km3_y"] = round(
        source_infiltration_sum_km3, 6
    )
    summary["total_vadose_zone_retention_km3_y"] = round(
        vadose_retention_sum_km3, 6
    )
    summary["groundwater_recharge_mass_balance_residual_km3_y"] = round(
        recharge_residual_sum_km3, 9
    )
    summary["mean_groundwater_recharge_mm_y"] = round(recharge_sum_mm / divisor, 6) if aquifer_cell_count else 0.0
    summary["mean_aquifer_storage_index"] = round(storage_sum / divisor, 6) if aquifer_cell_count else 0.0
    summary["mean_aquifer_quality_index"] = round(quality_sum / divisor, 6) if aquifer_cell_count else 0.0
    summary["mean_aquifer_productivity_index"] = round(productivity_sum / divisor, 6) if aquifer_cell_count else 0.0
    summary[("mean_aquifer_natural_limitation_index" if natural else "mean_aquifer_extraction_risk_index")] = round(risk_sum / divisor, 6) if aquifer_cell_count else 0.0
    summary["aquifer_class_counts"] = dict(sorted(class_counts.items()))
    return world


NATURAL_AQUIFER_POLICY = {'model_type': 'natural_recharge_causal_aquifer_resources_v2',
 'natural_limitation_model': 'aridity_low_recharge_salinity_ice_closed_basin_v1',
 'natural_limitation_field': 'aquifer_natural_limitation_index',
 'productivity_model': 'storage_recharge_quality_flow_natural_limitation_v2',
 'natural_input_policy': 'independent_of_settlement_suitability_population_and_human_records',
 'human_withdrawals_modelled': False,
 'natural_limitation_count_policy': 'summary_raw_and_system_six_decimal_indices_greater_than_or_equal_0_65',
 'model_limitation': 'heuristic_annual_natural_resource_properties_not_measured_storativity_conductivity_potability_or_sustainable_yield'}


def enrich_world_with_aquifer_resources(world: dict[str, Any]) -> dict[str, Any]:
    """Publish an independently audited natural v2 stage; declared v1 stays v1."""
    from .natural_groundwater_validation import (
        NaturalGroundwaterError, natural_groundwater_model_version,
        validate_natural_groundwater_inputs, validate_natural_aquifer_resources,
    )
    version = natural_groundwater_model_version(world, "aquifer")
    if version == 1:
        return _build_aquifer(world)
    validate_natural_groundwater_inputs(world, "aquifer")
    staged = {**world, "cells": [dict(c) for c in world["cells"]], "summary": dict(world.get("summary", {}))}
    for c in staged["cells"]:
        c.pop("aquifer_extraction_risk_index", None)
    staged["summary"].pop("mean_aquifer_extraction_risk_index", None)
    staged["summary"].pop("groundwater_stressed_cell_count", None)
    try:
        _build_aquifer(staged, natural=True)
        staged["aquifer_resource_model"].update(deepcopy(NATURAL_AQUIFER_POLICY))
        staged["aquifer_resource_model"].pop("extraction_risk_model")
        staged["summary"]["aquifer_resource_model"] = NATURAL_AQUIFER_POLICY["model_type"]
        errors = validate_natural_aquifer_resources(staged)
        if errors:
            raise NaturalGroundwaterError(errors[0])
    except (TypeError, KeyError, ValueError, OverflowError, ArithmeticError) as exc:
        if isinstance(exc, NaturalGroundwaterError):
            raise
        raise NaturalGroundwaterError("natural groundwater: malformed or unrepresentable aquifer result") from exc
    cell_fields = ('aquifer_class',
 'aquifer_extraction_risk_index',
 'aquifer_natural_limitation_index',
 'aquifer_productivity_index',
 'aquifer_quality_index',
 'aquifer_storage_index',
 'aquifer_system_id',
 'groundwater_recharge_fraction',
 'groundwater_recharge_km3_y',
 'groundwater_recharge_mass_balance_residual_mm_y',
 'groundwater_recharge_mm_y',
 'groundwater_recharge_source_infiltration_mm_y',
 'vadose_zone_retention_km3_y',
 'vadose_zone_retention_mm_y')
    for original, result in zip(world["cells"], staged["cells"]):
        for key in cell_fields:
            if key in result:
                original[key] = result[key]
            else:
                original.pop(key, None)
    for key in ('aquifer_resource_model', 'aquifer_systems', 'groundwater_recharge_model'):
        world[key] = staged[key]
    summary = world.setdefault("summary", {})
    summary.pop("mean_aquifer_extraction_risk_index", None)
    summary.pop("groundwater_stressed_cell_count", None)
    summary.update(staged["summary"])
    return world
