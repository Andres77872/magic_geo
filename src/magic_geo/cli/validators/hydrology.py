"""Water-budget, recharge, aquifer, and groundwater-flow replay checks."""

from __future__ import annotations

import math
from collections import Counter
from typing import Any

from .._constants import (
    AQUIFER_MIN_SYSTEM_PRODUCTIVITY_INDEX,
    AQUIFER_MIN_SYSTEM_RECHARGE_MM_Y,
    AQUIFER_RESOURCE_MODEL,
    GROUNDWATER_ALLUVIAL_LANDFORMS,
    GROUNDWATER_FLOW_GRADIENT_SCALE_M,
    GROUNDWATER_FLOW_MAXIMUM_LATERAL_EXPORT_FRACTION,
    GROUNDWATER_FLOW_MINIMUM_RECEIVER_HEAD_DROP_M,
    GROUNDWATER_FLOW_MODEL,
    GROUNDWATER_LITHOLOGY_PERMEABILITY,
    GROUNDWATER_MAX_RECHARGE_FRACTION,
    GROUNDWATER_MIN_RECHARGE_FRACTION,
    GROUNDWATER_RECHARGE_MODEL,
    HYDROLOGIC_CLIMATE_LOSS_FRACTION,
    HYDROLOGIC_INFILTRATION_BASE_SHARE,
    HYDROLOGIC_INFILTRATION_CAPACITY_SHARE,
    HYDROLOGIC_LITHOLOGY_NAMES,
    HYDROLOGIC_LITHOLOGY_PERMEABILITY,
    HYDROLOGIC_MAX_INFILTRATION_CAPACITY,
    HYDROLOGIC_MIN_INFILTRATION_CAPACITY,
    HYDROLOGIC_PET_SCALE_MM_Y_PER_C,
    HYDROLOGIC_PET_TEMPERATURE_OFFSET_C,
    HYDROLOGIC_WATER_BUDGET_MODEL,
    MATURATION_REFERENCE_TIMESTEP_MA,
)
from ._shared import _nominal_time_record_valid


def _validate_hydrologic_water_budget(
    payload: dict[str, Any],
    summary: dict[str, Any],
    cells_by_id: dict[int, dict[str, Any]],
) -> list[str]:
    """Replay every native climate-loss partition before routed hydrology."""

    failure = ["hydrologic water budget model or replay invalid"]
    model = payload.get("hydrologic_water_budget_model", {})
    history = payload.get("hydrologic_water_budget_history", [])
    feedback_history = payload.get("earth_system_feedback_history", [])
    simulation_clock = payload.get("simulation_clock", {})
    if (
        not isinstance(model, dict)
        or not isinstance(history, list)
        or not history
        or not isinstance(feedback_history, list)
        or not isinstance(simulation_clock, dict)
        or model.get("model_type") != HYDROLOGIC_WATER_BUDGET_MODEL
        or model.get("domain") != "non_marine_cells"
        or model.get("execution_order")
        != "climate_then_pet_then_loss_partition_then_runoff_then_flow_routing"
        or model.get("potential_evapotranspiration_model")
        != "max_zero_temperature_plus_offset_times_scale_v1"
        or model.get("climate_loss_model")
        != "min_precipitation_climate_loss_fraction_times_pet_v1"
        or model.get("infiltration_capacity_model")
        != "lithology_sediment_low_relief_frozen_capacity_v1"
        or model.get("infiltration_share_model")
        != "base_share_plus_capacity_share_times_capacity_index_v1"
        or model.get("actual_evapotranspiration_model")
        != "climate_loss_minus_infiltration_v1"
        or model.get("water_balance_equation")
        != "precipitation_minus_actual_evapotranspiration_minus_infiltration"
        or model.get("runoff_equation") != "max_zero_water_balance"
        or model.get("marine_cell_treatment")
        != "excluded_from_land_budget_with_zero_partition_terms"
        or not bool(model.get("runoff_computed_before_flow_routing", False))
        or not bool(model.get("cell_mass_balance_closed", False))
        or bool(model.get("physical_time_resolved", True))
        or model.get("model_limitation")
        != "empirical_annual_loss_partition_without_transient_soil_moisture_groundwater_return_flow_or_calibrated_time"
        or int(model.get("history_stage_count", -1)) != len(history)
        or abs(float(model.get("pet_temperature_offset_c", -1.0)) - HYDROLOGIC_PET_TEMPERATURE_OFFSET_C) > 1.0e-12
        or abs(float(model.get("pet_scale_mm_y_per_c", -1.0)) - HYDROLOGIC_PET_SCALE_MM_Y_PER_C) > 1.0e-12
        or abs(float(model.get("climate_loss_fraction", -1.0)) - HYDROLOGIC_CLIMATE_LOSS_FRACTION) > 1.0e-12
        or abs(float(model.get("infiltration_base_share", -1.0)) - HYDROLOGIC_INFILTRATION_BASE_SHARE) > 1.0e-12
        or abs(float(model.get("infiltration_capacity_share", -1.0)) - HYDROLOGIC_INFILTRATION_CAPACITY_SHARE) > 1.0e-12
        or abs(float(model.get("minimum_infiltration_capacity_index", -1.0)) - HYDROLOGIC_MIN_INFILTRATION_CAPACITY) > 1.0e-12
        or abs(float(model.get("maximum_infiltration_capacity_index", -1.0)) - HYDROLOGIC_MAX_INFILTRATION_CAPACITY) > 1.0e-12
        or {
            str(key): float(value)
            for key, value in model.get("lithology_permeability", {}).items()
        }
        != HYDROLOGIC_LITHOLOGY_PERMEABILITY
        or summary.get("hydrologic_water_budget_model")
        != HYDROLOGIC_WATER_BUDGET_MODEL
        or summary.get("hydrologic_water_budget_execution_order")
        != "climate_then_pet_then_loss_partition_then_runoff_then_flow_routing"
    ):
        return failure

    try:
        nominal_timestep_ma = float(simulation_clock["nominal_timestep_ma"])
        configured_erosion_iterations = int(
            simulation_clock["configured_erosion_iteration_count"]
        )
    except (KeyError, TypeError, ValueError, OverflowError):
        return failure
    if (
        not math.isfinite(nominal_timestep_ma)
        or not 0.0 < nominal_timestep_ma <= MATURATION_REFERENCE_TIMESTEP_MA
        or configured_erosion_iterations < 0
    ):
        return failure

    feedback_by_id = {
        int(step.get("id", -1)): step
        for step in feedback_history
        if isinstance(step, dict)
    }
    if len(feedback_by_id) != len(feedback_history):
        return failure

    array_names = (
        "cell_ids",
        "is_marine_by_cell",
        "lithology_by_cell",
        "cell_area_km2_by_cell",
        "elevation_m_by_cell",
        "temperature_c_by_cell",
        "precipitation_mm_y_by_cell",
        "local_relief_m_by_cell",
        "sediment_thickness_m_by_cell",
        "ice_thickness_m_by_cell",
        "potential_evapotranspiration_mm_y_by_cell",
        "infiltration_capacity_index_by_cell",
        "actual_evapotranspiration_mm_y_by_cell",
        "infiltration_mm_y_by_cell",
        "water_balance_mm_y_by_cell",
        "runoff_mm_y_by_cell",
        "residual_mm_y_by_cell",
    )
    stage_count_by_feedback: Counter[int] = Counter()
    final_stage_by_feedback: dict[int, dict[str, Any]] = {}
    last_stage: dict[str, Any] | None = None
    expected_cell_ids = set(cells_by_id)

    def close(actual: float, expected: float, absolute: float = 1.0e-6) -> bool:
        return abs(actual - expected) <= max(absolute, abs(expected) * 1.0e-9)

    for expected_stage_id, stage in enumerate(history):
        if not isinstance(stage, dict):
            return failure
        try:
            stage_id = int(stage.get("id", -1))
            feedback_stage_id = int(stage.get("feedback_stage_id", -1))
            recomputation_index = int(stage.get("stabilization_recomputation_index", -1))
            cell_count = int(stage.get("cell_count", -1))
            arrays = {name: stage.get(name) for name in array_names}
        except (TypeError, ValueError):
            return failure
        feedback = feedback_by_id.get(feedback_stage_id)
        if (
            stage_id != expected_stage_id
            or feedback is None
            or recomputation_index != stage_count_by_feedback[feedback_stage_id]
            or str(stage.get("stage", "")) != str(feedback.get("stage", ""))
            or int(stage.get("erosion_iteration", -2))
            != int(feedback.get("erosion_iteration", -3))
            or cell_count != len(cells_by_id)
            or any(not isinstance(values, list) or len(values) != cell_count for values in arrays.values())
            or not _nominal_time_record_valid(
                stage,
                expected_start_ma=min(
                    feedback_stage_id,
                    configured_erosion_iterations,
                )
                * nominal_timestep_ma,
                expected_end_ma=min(
                    feedback_stage_id,
                    configured_erosion_iterations,
                )
                * nominal_timestep_ma,
                expected_role="stage_end_stabilization_recomputation_snapshot",
            )
        ):
            return failure
        try:
            cell_ids = [int(value) for value in arrays["cell_ids"]]
            is_marine_values = [int(value) for value in arrays["is_marine_by_cell"]]
            lithology_values = [int(value) for value in arrays["lithology_by_cell"]]
            numeric_arrays = {
                name: [float(value) for value in values]
                for name, values in arrays.items()
                if name not in {"cell_ids", "is_marine_by_cell", "lithology_by_cell"}
            }
        except (TypeError, ValueError):
            return failure
        if set(cell_ids) != expected_cell_ids or len(set(cell_ids)) != cell_count:
            return failure
        position_by_cell_id = {cell_id: position for position, cell_id in enumerate(cell_ids)}
        elevation_by_cell_id = {
            cell_id: numeric_arrays["elevation_m_by_cell"][position]
            for position, cell_id in enumerate(cell_ids)
        }

        land_count = 0
        marine_count = 0
        precipitation_volume = 0.0
        aet_volume = 0.0
        infiltration_volume = 0.0
        runoff_volume = 0.0
        residual_volume = 0.0
        max_abs_residual = 0.0
        for position, cell_id in enumerate(cell_ids):
            cell = cells_by_id[cell_id]
            is_marine = is_marine_values[position]
            lithology = lithology_values[position]
            if is_marine not in {0, 1} or not 0 <= lithology < len(HYDROLOGIC_LITHOLOGY_NAMES):
                return failure
            area = numeric_arrays["cell_area_km2_by_cell"][position]
            elevation = numeric_arrays["elevation_m_by_cell"][position]
            temperature = numeric_arrays["temperature_c_by_cell"][position]
            precipitation = numeric_arrays["precipitation_mm_y_by_cell"][position]
            relief = numeric_arrays["local_relief_m_by_cell"][position]
            sediment = numeric_arrays["sediment_thickness_m_by_cell"][position]
            ice = numeric_arrays["ice_thickness_m_by_cell"][position]
            neighbors = [int(value) for value in cell.get("neighbors", [])]
            if any(neighbor_id not in position_by_cell_id for neighbor_id in neighbors):
                return failure
            neighbor_mean = (
                sum(elevation_by_cell_id[neighbor_id] for neighbor_id in neighbors)
                / len(neighbors)
                if neighbors
                else elevation
            )
            expected_relief = max(0.0, elevation - neighbor_mean)
            if area <= 0.0 or precipitation < 0.0 or sediment < 0.0 or ice < 0.0 or not close(relief, expected_relief, 1.0e-5):
                return failure

            expected_pet = 0.0
            expected_capacity = 0.0
            expected_aet = 0.0
            expected_infiltration = 0.0
            expected_balance = 0.0
            expected_runoff = 0.0
            if not is_marine:
                expected_pet = max(0.0, temperature + HYDROLOGIC_PET_TEMPERATURE_OFFSET_C) * HYDROLOGIC_PET_SCALE_MM_Y_PER_C
                permeability = HYDROLOGIC_LITHOLOGY_PERMEABILITY[
                    HYDROLOGIC_LITHOLOGY_NAMES[lithology]
                ]
                terrain_retention = 1.0 - max(0.0, min(1.0, relief / 2500.0))
                sediment_index = max(0.0, min(1.0, sediment / 3.0))
                frozen_index = max(0.0, min(1.0, (-temperature - 2.0) / 18.0))
                expected_capacity = max(
                    HYDROLOGIC_MIN_INFILTRATION_CAPACITY,
                    min(
                        HYDROLOGIC_MAX_INFILTRATION_CAPACITY,
                        0.62 * permeability
                        + 0.16 * sediment_index
                        + 0.12 * terrain_retention
                        - 0.10 * frozen_index,
                    ),
                )
                climate_loss = min(
                    precipitation,
                    HYDROLOGIC_CLIMATE_LOSS_FRACTION * expected_pet,
                )
                infiltration_share = max(
                    HYDROLOGIC_INFILTRATION_BASE_SHARE,
                    min(
                        HYDROLOGIC_INFILTRATION_BASE_SHARE
                        + HYDROLOGIC_INFILTRATION_CAPACITY_SHARE
                        * HYDROLOGIC_MAX_INFILTRATION_CAPACITY,
                        HYDROLOGIC_INFILTRATION_BASE_SHARE
                        + HYDROLOGIC_INFILTRATION_CAPACITY_SHARE
                        * expected_capacity,
                    ),
                )
                expected_infiltration = climate_loss * infiltration_share
                expected_aet = climate_loss - expected_infiltration
                expected_balance = precipitation - climate_loss
                expected_runoff = max(0.0, expected_balance)
            expected_residual = precipitation - expected_aet - expected_infiltration - expected_runoff if not is_marine else 0.0

            expected_values = {
                "potential_evapotranspiration_mm_y_by_cell": expected_pet,
                "infiltration_capacity_index_by_cell": expected_capacity,
                "actual_evapotranspiration_mm_y_by_cell": expected_aet,
                "infiltration_mm_y_by_cell": expected_infiltration,
                "water_balance_mm_y_by_cell": expected_balance,
                "runoff_mm_y_by_cell": expected_runoff,
                "residual_mm_y_by_cell": expected_residual,
            }
            if any(
                not close(numeric_arrays[name][position], expected)
                for name, expected in expected_values.items()
            ):
                return failure
            if is_marine:
                marine_count += 1
            else:
                land_count += 1
                precipitation_volume += precipitation * area * 1.0e-6
                aet_volume += expected_aet * area * 1.0e-6
                infiltration_volume += expected_infiltration * area * 1.0e-6
                runoff_volume += expected_runoff * area * 1.0e-6
                residual_volume += expected_residual * area * 1.0e-6
                max_abs_residual = max(max_abs_residual, abs(expected_residual))

        aggregate_values = {
            "land_precipitation_volume_km3_y": precipitation_volume,
            "actual_evapotranspiration_volume_km3_y": aet_volume,
            "infiltration_volume_km3_y": infiltration_volume,
            "runoff_volume_km3_y": runoff_volume,
            "mass_balance_residual_km3_y": residual_volume,
            "max_abs_cell_residual_mm_y": max_abs_residual,
        }
        if (
            int(stage.get("land_cell_count", -1)) != land_count
            or int(stage.get("marine_cell_count", -1)) != marine_count
            or land_count + marine_count != cell_count
            or any(
                not close(float(stage.get(name, math.inf)), expected, 1.0e-5)
                for name, expected in aggregate_values.items()
            )
        ):
            return failure
        stage_count_by_feedback[feedback_stage_id] += 1
        final_stage_by_feedback[feedback_stage_id] = stage
        last_stage = stage

    if last_stage is None or sum(stage_count_by_feedback.values()) != len(history):
        return failure
    for feedback_stage_id, feedback in feedback_by_id.items():
        final_stage = final_stage_by_feedback.get(feedback_stage_id)
        expected_count = stage_count_by_feedback[feedback_stage_id]
        if (
            final_stage is None
            or int(feedback.get("hydrologic_water_budget_recompute_count", -1)) != expected_count
            or bool(feedback.get("hydrologic_water_budget_recomputed", False)) != (expected_count > 0)
            or int(feedback.get("hydrology_recompute_count", -1)) != expected_count
        ):
            return failure
        feedback_aggregates = {
            "hydrologic_land_precipitation_volume_km3_y": "land_precipitation_volume_km3_y",
            "hydrologic_actual_evapotranspiration_volume_km3_y": "actual_evapotranspiration_volume_km3_y",
            "hydrologic_infiltration_volume_km3_y": "infiltration_volume_km3_y",
            "hydrologic_runoff_volume_km3_y": "runoff_volume_km3_y",
            "hydrologic_water_budget_residual_km3_y": "mass_balance_residual_km3_y",
            "max_abs_hydrologic_water_budget_cell_residual_mm_y": "max_abs_cell_residual_mm_y",
        }
        if any(
            not close(
                float(feedback.get(feedback_name, math.inf)),
                float(final_stage.get(stage_name, -math.inf)),
                1.0e-5,
            )
            for feedback_name, stage_name in feedback_aggregates.items()
        ):
            return failure

    final_arrays = {name: last_stage[name] for name in array_names}
    final_position = {
        int(cell_id): position
        for position, cell_id in enumerate(final_arrays["cell_ids"])
    }
    lithology_index = {
        name: index for index, name in enumerate(HYDROLOGIC_LITHOLOGY_NAMES)
    }
    final_field_arrays = {
        "hydrologic_potential_evapotranspiration_mm_y": "potential_evapotranspiration_mm_y_by_cell",
        "infiltration_capacity_index": "infiltration_capacity_index_by_cell",
        "actual_evapotranspiration_mm_y": "actual_evapotranspiration_mm_y_by_cell",
        "infiltration_mm_y": "infiltration_mm_y_by_cell",
        "hydrologic_water_balance_mm_y": "water_balance_mm_y_by_cell",
        "water_budget_runoff_mm_y": "runoff_mm_y_by_cell",
        "runoff_mm_y": "runoff_mm_y_by_cell",
        "runoff_budget_residual_mm_y": "residual_mm_y_by_cell",
    }
    for cell_id, cell in cells_by_id.items():
        position = final_position.get(cell_id)
        if position is None:
            return failure
        if (
            int(final_arrays["is_marine_by_cell"][position]) != int(bool(cell.get("is_water", False)))
            or int(final_arrays["lithology_by_cell"][position])
            != lithology_index.get(str(cell.get("lithology", "")), -1)
            or not close(float(final_arrays["cell_area_km2_by_cell"][position]), float(cell.get("area_km2", 0.0)), 1.0e-5)
            or not close(float(final_arrays["elevation_m_by_cell"][position]), float(cell.get("elevation_m", 0.0)), 1.0e-5)
            or not close(float(final_arrays["temperature_c_by_cell"][position]), float(cell.get("temperature_c", 0.0)), 0.001)
            or not close(float(final_arrays["precipitation_mm_y_by_cell"][position]), float(cell.get("precipitation_mm_y", 0.0)), 0.001)
            or not close(float(final_arrays["sediment_thickness_m_by_cell"][position]), float(cell.get("sediment_thickness_m", 0.0)), 0.001)
            or any(
                not close(
                    float(cell.get(cell_field, math.inf)),
                    float(final_arrays[array_name][position]),
                    0.001,
                )
                for cell_field, array_name in final_field_arrays.items()
            )
        ):
            return failure

    final_model_values = {
        "final_history_stage_id": int(last_stage.get("id", -1)),
        "final_land_cell_count": int(last_stage.get("land_cell_count", -1)),
        "final_marine_cell_count": int(last_stage.get("marine_cell_count", -1)),
        "final_land_precipitation_volume_km3_y": float(last_stage.get("land_precipitation_volume_km3_y", 0.0)),
        "final_actual_evapotranspiration_volume_km3_y": float(last_stage.get("actual_evapotranspiration_volume_km3_y", 0.0)),
        "final_infiltration_volume_km3_y": float(last_stage.get("infiltration_volume_km3_y", 0.0)),
        "final_runoff_volume_km3_y": float(last_stage.get("runoff_volume_km3_y", 0.0)),
        "final_mass_balance_residual_km3_y": float(last_stage.get("mass_balance_residual_km3_y", 0.0)),
        "final_max_abs_cell_residual_mm_y": float(last_stage.get("max_abs_cell_residual_mm_y", 0.0)),
    }
    for name, expected in final_model_values.items():
        actual = model.get(name)
        if isinstance(expected, int):
            if int(actual if actual is not None else -1) != expected:
                return failure
        elif not close(float(actual if actual is not None else math.inf), expected, 1.0e-5):
            return failure
    return []


def _validate_groundwater_recharge(
    payload: dict[str, Any],
    summary: dict[str, Any],
    cells_by_id: dict[int, dict[str, Any]],
) -> list[str]:
    """Replay the infiltration-bounded aquifer/vadose source partition."""

    failure = ["groundwater recharge model or source partition invalid"]
    model = payload.get("groundwater_recharge_model", {})
    if (
        not isinstance(model, dict)
        or model.get("model_type") != GROUNDWATER_RECHARGE_MODEL
        or model.get("source_field") != "infiltration_mm_y"
        or model.get("domain") != "non_marine_cells"
        or model.get("recharge_fraction_model")
        != "lithology_soil_drainage_sediment_lake_salinity_ice_aridity_v1"
        or model.get("marine_cell_treatment")
        != "zero_source_recharge_and_vadose_retention"
        or not bool(model.get("mass_conserving_source_partition", False))
        or model.get("model_limitation")
        != "annual_diagnostic_partition_without_transient_vadose_storage_or_groundwater_return_flow"
        or summary.get("groundwater_recharge_model")
        != GROUNDWATER_RECHARGE_MODEL
        or abs(
            float(model.get("minimum_recharge_fraction", -1.0))
            - GROUNDWATER_MIN_RECHARGE_FRACTION
        )
        > 1.0e-12
        or abs(
            float(model.get("maximum_recharge_fraction", -1.0))
            - GROUNDWATER_MAX_RECHARGE_FRACTION
        )
        > 1.0e-12
    ):
        return failure

    source_volume = 0.0
    recharge_volume = 0.0
    vadose_volume = 0.0
    residual_volume = 0.0
    marine_types = {"ocean", "continental_shelf", "inland_sea"}
    for cell in cells_by_id.values():
        try:
            water_body = str(cell.get("water_body_type", "land"))
            is_marine = water_body in marine_types
            area = max(0.0, float(cell.get("area_km2", 0.0)))
            source = float(
                cell.get("groundwater_recharge_source_infiltration_mm_y", -1.0)
            )
            fraction = float(cell.get("groundwater_recharge_fraction", -1.0))
            recharge = float(cell.get("groundwater_recharge_mm_y", -1.0))
            recharge_km3 = float(cell.get("groundwater_recharge_km3_y", -1.0))
            vadose = float(cell.get("vadose_zone_retention_mm_y", -1.0))
            vadose_km3 = float(cell.get("vadose_zone_retention_km3_y", -1.0))
            residual = float(
                cell.get("groundwater_recharge_mass_balance_residual_mm_y", math.inf)
            )
        except (TypeError, ValueError):
            return failure
        if area <= 0.0:
            return failure

        expected_source = 0.0
        expected_fraction = 0.0
        if not is_marine:
            expected_source = max(0.0, float(cell.get("infiltration_mm_y", 0.0)))
            lithology = str(cell.get("lithology", "unknown"))
            landform = str(cell.get("landform", "unknown"))
            permeability = GROUNDWATER_LITHOLOGY_PERMEABILITY.get(
                lithology, 0.34
            )
            if landform in {"rift_valley", "glacial_valley"}:
                permeability += 0.10
            if landform in GROUNDWATER_ALLUVIAL_LANDFORMS:
                permeability += 0.08
            permeability = max(0.0, min(1.0, permeability))
            drainage = max(
                0.0, min(1.0, float(cell.get("soil_drainage_index", 0.0)))
            )
            sediment = max(
                0.0,
                min(1.0, float(cell.get("sediment_thickness_m", 0.0)) / 3.0),
            )
            salinity = max(
                0.0, min(1.0, float(cell.get("soil_salinity_index", 0.0)))
            )
            ice = max(
                0.0,
                min(1.0, float(cell.get("ice_thickness_m", 0.0)) / 1600.0),
            )
            aridity = max(
                0.0, min(1.0, float(cell.get("seasonal_aridity_index", 0.0)))
            )
            expected_fraction = max(
                GROUNDWATER_MIN_RECHARGE_FRACTION,
                min(
                    GROUNDWATER_MAX_RECHARGE_FRACTION,
                    0.08
                    + permeability * 0.45
                    + drainage * 0.18
                    + sediment * 0.12
                    + (0.04 if water_body == "fresh_lake" else 0.0)
                    - salinity * 0.10
                    - ice * 0.12
                    - aridity * 0.06,
                ),
            )
        expected_recharge = expected_source * expected_fraction
        expected_vadose = expected_source - expected_recharge
        expected_residual = (
            expected_source - expected_recharge - expected_vadose
        )
        expected_recharge_km3 = expected_recharge * area * 1.0e-6
        expected_vadose_km3 = expected_vadose * area * 1.0e-6
        if (
            source < 0.0
            or recharge < 0.0
            or vadose < 0.0
            or recharge > source + 0.001
            or abs(source - expected_source) > 0.001
            or abs(fraction - expected_fraction) > 0.001
            or abs(recharge - expected_recharge) > 0.001
            or abs(vadose - expected_vadose) > 0.001
            or abs(residual - expected_residual) > 1.0e-8
            or abs(recharge_km3 - expected_recharge_km3)
            > max(0.001, expected_recharge_km3 * 0.0001)
            or abs(vadose_km3 - expected_vadose_km3)
            > max(0.001, expected_vadose_km3 * 0.0001)
        ):
            return failure
        if not is_marine:
            source_volume += expected_source * area * 1.0e-6
            recharge_volume += expected_recharge_km3
            vadose_volume += expected_vadose_km3
            residual_volume += expected_residual * area * 1.0e-6

    expected_model = {
        "total_source_infiltration_volume_km3_y": source_volume,
        "total_groundwater_recharge_volume_km3_y": recharge_volume,
        "total_vadose_zone_retention_volume_km3_y": vadose_volume,
        "mass_balance_residual_km3_y": residual_volume,
    }
    if any(
        abs(float(model.get(key, math.inf)) - expected)
        > max(0.001, abs(expected) * 0.0001)
        for key, expected in expected_model.items()
    ):
        return failure
    expected_summary = {
        "total_groundwater_recharge_source_infiltration_km3_y": source_volume,
        "total_groundwater_recharge_km3_y": recharge_volume,
        "total_vadose_zone_retention_km3_y": vadose_volume,
        "groundwater_recharge_mass_balance_residual_km3_y": residual_volume,
    }
    if any(
        abs(float(summary.get(key, math.inf)) - expected)
        > max(0.001, abs(expected) * 0.0001)
        for key, expected in expected_summary.items()
    ):
        return failure
    if abs(
        source_volume - float(summary.get("total_infiltration_km3_y", math.inf))
    ) > max(0.001, source_volume * 0.0001):
        return failure
    return []


def _validate_aquifer_resources(
    payload: dict[str, Any],
    summary: dict[str, Any],
    cells_by_id: dict[int, dict[str, Any]],
) -> list[str]:
    """Replay aquifer properties, classification, and basin grouping."""

    failure = ["aquifer resource model or causal replay invalid"]
    model = payload.get("aquifer_resource_model", {})
    systems = payload.get("aquifer_systems", [])
    try:
        metadata_invalid = (
            not isinstance(model, dict)
            or not isinstance(systems, list)
            or model.get("model_type") != AQUIFER_RESOURCE_MODEL
            or model.get("source_recharge_model")
            != GROUNDWATER_RECHARGE_MODEL
            or model.get("domain") != "non_marine_cells"
            or model.get("permeability_model")
            != "lithology_with_rift_glacial_and_alluvial_landform_adjustments_v1"
            or model.get("storage_model")
            != "permeability_sediment_moisture_alluvium_lake_aridity_ice_v1"
            or model.get("quality_model")
            != "recharge_limestone_salinity_closed_basin_aridity_v1"
            or model.get("extraction_risk_model")
            != "aridity_settlement_low_recharge_salinity_ice_closed_basin_v1"
            or model.get("productivity_model")
            != "storage_recharge_quality_flow_extraction_risk_v1"
            or model.get("classification_model")
            != "quality_salinity_productivity_storage_recharge_thresholds_v1"
            or model.get("system_grouping_model")
            != "basin_id_over_productivity_or_recharge_eligible_cells_v1"
            or model.get("marine_cell_treatment")
            != "zero_properties_marine_excluded_class_and_no_system"
            or model.get("deterministic") is not True
            or model.get("model_limitation")
            != "diagnostic_annual_resource_properties_without_transient_saturated_flow_storage_drawdown_or_geochemistry"
            or summary.get("aquifer_resource_model")
            != AQUIFER_RESOURCE_MODEL
            or abs(
                float(model.get("minimum_system_productivity_index", -1.0))
                - AQUIFER_MIN_SYSTEM_PRODUCTIVITY_INDEX
            )
            > 1.0e-12
            or abs(
                float(model.get("minimum_system_recharge_mm_y", -1.0))
                - AQUIFER_MIN_SYSTEM_RECHARGE_MM_Y
            )
            > 1.0e-12
        )
    except (TypeError, ValueError):
        return failure
    if metadata_invalid:
        return failure

    marine_types = {"ocean", "continental_shelf", "inland_sea"}

    def clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
        return max(lower, min(upper, value))

    def primary_key(counter: Counter[str], fallback: str) -> str:
        if not counter:
            return fallback
        return sorted(counter.items(), key=lambda item: (-item[1], item[0]))[
            0
        ][0]

    def aquifer_class(
        productivity: float,
        storage: float,
        quality: float,
        recharge_mm_y: float,
        salinity: float,
    ) -> str:
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

    expected_by_id: dict[int, dict[str, Any]] = {}
    basin_groups: dict[int, list[int]] = {}
    class_counts: Counter[str] = Counter()
    aquifer_cell_count = 0
    recharge_cell_count = 0
    high_productivity_count = 0
    stressed_cell_count = 0
    recharge_sum_mm = 0.0
    recharge_sum_km3 = 0.0
    storage_sum = 0.0
    quality_sum = 0.0
    productivity_sum = 0.0
    risk_sum = 0.0

    for cell_id, cell in cells_by_id.items():
        try:
            water_body = str(cell.get("water_body_type", "land"))
            lithology = str(cell.get("lithology", "unknown"))
            landform = str(cell.get("landform", "unknown"))
            area = max(0.0, float(cell.get("area_km2", 0.0)))
            marine_excluded = water_body in marine_types
            if marine_excluded:
                recharge_mm = 0.0
                recharge_km3 = 0.0
                storage = 0.0
                quality = 0.0
                productivity = 0.0
                extraction_risk = 0.0
                expected_class = "marine_excluded"
            else:
                permeability = GROUNDWATER_LITHOLOGY_PERMEABILITY.get(
                    lithology, 0.34
                )
                if landform in {"rift_valley", "glacial_valley"}:
                    permeability += 0.10
                if landform in GROUNDWATER_ALLUVIAL_LANDFORMS:
                    permeability += 0.08
                permeability = clamp(permeability)
                sediment = clamp(
                    float(cell.get("sediment_thickness_m", 0.0)) / 3.0
                )
                drainage = clamp(float(cell.get("soil_drainage_index", 0.0)))
                moisture = clamp(float(cell.get("soil_moisture_index", 0.0)))
                salinity = clamp(float(cell.get("soil_salinity_index", 0.0)))
                aridity = clamp(
                    float(cell.get("seasonal_aridity_index", 0.0))
                )
                ice = clamp(float(cell.get("ice_thickness_m", 0.0)) / 1600.0)
                flow = clamp(
                    float(cell.get("flow_accumulation", 0.0)) / 40_000_000.0
                )
                settlement = clamp(float(cell.get("settlement_score", 0.0)))
                closed_basin = bool(cell.get("is_closed_basin", False))
                source = max(0.0, float(cell.get("infiltration_mm_y", 0.0)))
                recharge_fraction = clamp(
                    0.08
                    + permeability * 0.45
                    + drainage * 0.18
                    + sediment * 0.12
                    + (0.04 if water_body == "fresh_lake" else 0.0)
                    - salinity * 0.10
                    - ice * 0.12
                    - aridity * 0.06,
                    GROUNDWATER_MIN_RECHARGE_FRACTION,
                    GROUNDWATER_MAX_RECHARGE_FRACTION,
                )
                recharge_mm = source * recharge_fraction
                recharge_km3 = recharge_mm * area * 1.0e-6
                alluvial_bonus = (
                    0.15 if landform in GROUNDWATER_ALLUVIAL_LANDFORMS else 0.0
                )
                fresh_lake_bonus = 0.16 if water_body == "fresh_lake" else 0.0
                storage = clamp(
                    0.08
                    + permeability * 0.34
                    + sediment * 0.26
                    + moisture * 0.12
                    + alluvial_bonus
                    + fresh_lake_bonus * 0.7
                    - aridity * 0.10
                    - ice * 0.12
                )
                quality = clamp(
                    0.80
                    + clamp(recharge_mm / 360.0) * 0.16
                    + (0.05 if lithology == "limestone" else 0.0)
                    - salinity * 0.50
                    - (0.18 if closed_basin else 0.0)
                    - (0.18 if water_body == "saline_basin" else 0.0)
                    - aridity * 0.08
                )
                extraction_risk = clamp(
                    0.14
                    + aridity * 0.30
                    + settlement * 0.18
                    + (1.0 - clamp(recharge_mm / 240.0)) * 0.20
                    + salinity * 0.18
                    + ice * 0.10
                    + (0.08 if closed_basin else 0.0)
                )
                productivity = clamp(
                    storage * 0.38
                    + clamp(recharge_mm / 320.0) * 0.34
                    + quality * 0.18
                    + flow * 0.08
                    - extraction_risk * 0.16
                )
                expected_class = aquifer_class(
                    productivity,
                    storage,
                    quality,
                    recharge_mm,
                    salinity,
                )
        except (TypeError, ValueError):
            return failure

        expected = {
            "recharge_mm": round(recharge_mm, 6),
            "recharge_km3": round(recharge_km3, 6),
            "storage": round(storage, 6),
            "quality": round(quality, 6),
            "productivity": round(productivity, 6),
            "risk": round(extraction_risk, 6),
            "class": expected_class,
            "system_id": -1,
        }
        expected_by_id[cell_id] = expected
        class_counts[expected_class] += 1
        try:
            actual_values = (
                float(cell.get("aquifer_storage_index", math.inf)),
                float(cell.get("aquifer_quality_index", math.inf)),
                float(cell.get("aquifer_productivity_index", math.inf)),
                float(cell.get("aquifer_extraction_risk_index", math.inf)),
            )
        except (TypeError, ValueError):
            return failure
        expected_values = (
            expected["storage"],
            expected["quality"],
            expected["productivity"],
            expected["risk"],
        )
        if (
            any(
                abs(actual - target) > 1.0e-9
                for actual, target in zip(actual_values, expected_values)
            )
            or str(cell.get("aquifer_class", "")) != expected_class
        ):
            return failure

        if not marine_excluded:
            aquifer_cell_count += 1
            recharge_sum_mm += recharge_mm
            recharge_sum_km3 += recharge_km3
            storage_sum += storage
            quality_sum += quality
            productivity_sum += productivity
            risk_sum += extraction_risk
            recharge_cell_count += int(recharge_mm >= 50.0)
            high_productivity_count += int(productivity >= 0.65)
            stressed_cell_count += int(extraction_risk >= 0.65)
            if (
                productivity >= AQUIFER_MIN_SYSTEM_PRODUCTIVITY_INDEX
                or recharge_mm >= AQUIFER_MIN_SYSTEM_RECHARGE_MM_Y
            ):
                basin_id = int(cell.get("basin_id", -1))
                basin_groups.setdefault(basin_id, []).append(cell_id)

    expected_systems: list[dict[str, Any]] = []
    for basin_id, group_ids in sorted(basin_groups.items()):
        system_id = len(expected_systems)
        group_cells = [cells_by_id[cell_id] for cell_id in group_ids]
        for cell_id in group_ids:
            expected_by_id[cell_id]["system_id"] = system_id
        group_count = len(group_ids)
        class_counter = Counter(
            str(expected_by_id[cell_id]["class"]) for cell_id in group_ids
        )
        lithology_counter = Counter(
            str(cell.get("lithology", "unknown")) for cell in group_cells
        )
        landform_counter = Counter(
            str(cell.get("landform", "unknown")) for cell in group_cells
        )
        expected_systems.append(
            {
                "id": system_id,
                "basin_id": basin_id,
                "aquifer_class": primary_key(class_counter, "poor_aquifer"),
                "primary_lithology": primary_key(
                    lithology_counter, "unknown"
                ),
                "dominant_landform": primary_key(
                    landform_counter, "unknown"
                ),
                "cell_count": group_count,
                "cell_ids": group_ids,
                "area_km2": round(
                    sum(
                        max(0.0, float(cell.get("area_km2", 0.0)))
                        for cell in group_cells
                    ),
                    6,
                ),
                "mean_groundwater_recharge_mm_y": round(
                    sum(expected_by_id[cell_id]["recharge_mm"] for cell_id in group_ids)
                    / group_count,
                    6,
                ),
                "total_groundwater_recharge_km3_y": round(
                    sum(expected_by_id[cell_id]["recharge_km3"] for cell_id in group_ids),
                    6,
                ),
                "mean_aquifer_storage_index": round(
                    sum(expected_by_id[cell_id]["storage"] for cell_id in group_ids)
                    / group_count,
                    6,
                ),
                "mean_aquifer_quality_index": round(
                    sum(expected_by_id[cell_id]["quality"] for cell_id in group_ids)
                    / group_count,
                    6,
                ),
                "mean_aquifer_productivity_index": round(
                    sum(expected_by_id[cell_id]["productivity"] for cell_id in group_ids)
                    / group_count,
                    6,
                ),
                "mean_aquifer_extraction_risk_index": round(
                    sum(expected_by_id[cell_id]["risk"] for cell_id in group_ids)
                    / group_count,
                    6,
                ),
                "recharge_cell_count": sum(
                    expected_by_id[cell_id]["recharge_mm"] >= 50.0
                    for cell_id in group_ids
                ),
                "high_productivity_cell_count": sum(
                    expected_by_id[cell_id]["productivity"] >= 0.65
                    for cell_id in group_ids
                ),
                "stressed_cell_count": sum(
                    expected_by_id[cell_id]["risk"] >= 0.65
                    for cell_id in group_ids
                ),
                "closed_basin_fraction": round(
                    sum(
                        bool(cell.get("is_closed_basin", False))
                        for cell in group_cells
                    )
                    / group_count,
                    6,
                ),
                "aquifer_class_counts": dict(sorted(class_counter.items())),
            }
        )

    for cell_id, expected in expected_by_id.items():
        try:
            if int(cells_by_id[cell_id].get("aquifer_system_id", -2)) != int(
                expected["system_id"]
            ):
                return failure
        except (TypeError, ValueError):
            return failure

    if len(systems) != len(expected_systems):
        return failure
    for actual, expected in zip(systems, expected_systems):
        if not isinstance(actual, dict) or any(
            actual.get(key) != value for key, value in expected.items()
        ):
            return failure

    expected_model_counts = {
        "aquifer_cell_count": aquifer_cell_count,
        "system_eligible_cell_count": sum(map(len, basin_groups.values())),
        "aquifer_system_count": len(expected_systems),
    }
    if any(
        int(model.get(key, -1)) != expected
        for key, expected in expected_model_counts.items()
    ):
        return failure

    divisor = aquifer_cell_count if aquifer_cell_count else 1
    expected_summary = {
        "aquifer_resource_model": AQUIFER_RESOURCE_MODEL,
        "aquifer_cell_count": aquifer_cell_count,
        "aquifer_system_count": len(expected_systems),
        "groundwater_recharge_cell_count": recharge_cell_count,
        "high_productivity_aquifer_cell_count": high_productivity_count,
        "groundwater_stressed_cell_count": stressed_cell_count,
        "total_groundwater_recharge_km3_y": round(recharge_sum_km3, 6),
        "mean_groundwater_recharge_mm_y": (
            round(recharge_sum_mm / divisor, 6) if aquifer_cell_count else 0.0
        ),
        "mean_aquifer_storage_index": (
            round(storage_sum / divisor, 6) if aquifer_cell_count else 0.0
        ),
        "mean_aquifer_quality_index": (
            round(quality_sum / divisor, 6) if aquifer_cell_count else 0.0
        ),
        "mean_aquifer_productivity_index": (
            round(productivity_sum / divisor, 6) if aquifer_cell_count else 0.0
        ),
        "mean_aquifer_extraction_risk_index": (
            round(risk_sum / divisor, 6) if aquifer_cell_count else 0.0
        ),
        "aquifer_class_counts": dict(sorted(class_counts.items())),
    }
    if any(summary.get(key) != value for key, value in expected_summary.items()):
        return failure
    return []


def _validate_groundwater_flow(
    payload: dict[str, Any],
    summary: dict[str, Any],
    cells_by_id: dict[int, dict[str, Any]],
) -> list[str]:
    """Replay deterministic head routing and every local recharge-volume split."""

    failure = ["groundwater flow model or routing replay invalid"]
    model = payload.get("groundwater_flow_model", {})
    if (
        not isinstance(model, dict)
        or model.get("model_type") != GROUNDWATER_FLOW_MODEL
        or model.get("source_field") != "groundwater_recharge_km3_y"
        or model.get("domain") != "non_marine_aquifer_cells"
        or model.get("hydraulic_head_model")
        != "terrain_minus_diagnostic_depth_to_water_v1"
        or model.get("receiver_model")
        != "steepest_head_drop_within_aquifer_system_or_surface_sink_v1"
        or model.get("routing_order")
        != "descending_hydraulic_head_then_cell_id"
        or model.get("lateral_export_model")
        != "bounded_gradient_productivity_storage_extraction_fraction_v1"
        or model.get("surface_discharge_model")
        != "surface_target_export_plus_fraction_of_remaining_volume_v1"
        or model.get("local_mass_balance_equation")
        != "recharge_plus_lateral_inflow_minus_internal_lateral_outflow_minus_discharge_minus_retained_storage"
        or not bool(model.get("mass_conserving", False))
        or not bool(model.get("acyclic_flow_required", False))
        or model.get("model_limitation")
        != "annual_diagnostic_head_and_flux_routing_without_transient_aquifer_storage_or_groundwater_surface_water_feedback"
        or summary.get("groundwater_flow_model") != GROUNDWATER_FLOW_MODEL
        or abs(
            float(model.get("minimum_receiver_head_drop_m", -1.0))
            - GROUNDWATER_FLOW_MINIMUM_RECEIVER_HEAD_DROP_M
        )
        > 1.0e-12
        or abs(
            float(model.get("gradient_scale_m", -1.0))
            - GROUNDWATER_FLOW_GRADIENT_SCALE_M
        )
        > 1.0e-12
        or abs(
            float(model.get("maximum_lateral_export_fraction", -1.0))
            - GROUNDWATER_FLOW_MAXIMUM_LATERAL_EXPORT_FRACTION
        )
        > 1.0e-12
    ):
        return failure

    marine_types = {"ocean", "continental_shelf", "inland_sea"}
    surface_water_types = {"fresh_lake", "saline_basin"}
    flow_regimes = {
        "excluded",
        "recharge_mound",
        "recharge_throughflow",
        "throughflow",
        "discharge_zone",
        "lowland_discharge",
        "stagnant_or_low_yield",
    }

    def clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
        return max(lower, min(upper, value))

    def is_candidate(cell: dict[str, Any]) -> bool:
        return (
            str(cell.get("aquifer_class", "")) != "marine_excluded"
            and str(cell.get("water_body_type", "land")) not in marine_types
        )

    candidate_ids = {
        cell_id for cell_id, cell in cells_by_id.items() if is_candidate(cell)
    }
    if int(model.get("candidate_cell_count", -1)) != len(candidate_ids):
        return failure

    def water_surface_head(cell: dict[str, Any]) -> float:
        elevation = float(cell.get("elevation_m", 0.0))
        if bool(cell.get("is_water", False)):
            return elevation + max(0.0, float(cell.get("water_depth_m", 0.0)))
        return elevation

    def hydraulic_head(cell: dict[str, Any]) -> float:
        if not is_candidate(cell):
            return water_surface_head(cell)
        elevation = float(cell.get("elevation_m", 0.0))
        recharge = clamp(float(cell.get("groundwater_recharge_mm_y", 0.0)) / 360.0)
        storage = clamp(float(cell.get("aquifer_storage_index", 0.0)))
        quality = clamp(float(cell.get("aquifer_quality_index", 0.0)))
        moisture = clamp(float(cell.get("soil_moisture_index", 0.0)))
        aridity = clamp(float(cell.get("seasonal_aridity_index", 0.0)))
        salinity = clamp(float(cell.get("soil_salinity_index", 0.0)))
        extraction_risk = clamp(
            float(cell.get("aquifer_extraction_risk_index", 0.0))
        )
        water_bonus = (
            0.18
            if bool(cell.get("is_lake", False))
            or str(cell.get("water_body_type", "land")) in surface_water_types
            else 0.0
        )
        river_bonus = 0.10 if bool(cell.get("is_river", False)) else 0.0
        saturation = clamp(
            recharge * 0.28
            + storage * 0.26
            + quality * 0.10
            + moisture * 0.18
            + water_bonus
            + river_bonus
            - aridity * 0.12
            - salinity * 0.08
            - extraction_risk * 0.08
        )
        depth_to_water = max(
            0.0,
            12.0
            + (1.0 - saturation) * 210.0
            + aridity * 70.0
            + extraction_risk * 45.0
            - storage * 35.0,
        )
        return elevation - depth_to_water

    heads = {
        cell_id: hydraulic_head(cell) for cell_id, cell in cells_by_id.items()
    }
    flow_to_by_id: dict[int, int] = {}
    gradient_by_id: dict[int, float] = {}
    for cell_id in sorted(candidate_ids):
        cell = cells_by_id[cell_id]
        head = heads[cell_id]
        aquifer_system_id = int(cell.get("aquifer_system_id", -1))
        best_neighbor_id = -1
        best_drop = 0.0
        neighbors = cell.get("neighbors", [])
        if not isinstance(neighbors, list):
            return failure
        for raw_neighbor_id in neighbors:
            neighbor_id = int(raw_neighbor_id)
            neighbor = cells_by_id.get(neighbor_id)
            if neighbor is None:
                return failure
            same_system = (
                neighbor_id in candidate_ids
                and int(neighbor.get("aquifer_system_id", -2))
                == aquifer_system_id
            )
            surface_sink = neighbor_id not in candidate_ids
            if not same_system and not surface_sink:
                continue
            drop = head - heads[neighbor_id]
            if drop > best_drop:
                best_drop = drop
                best_neighbor_id = neighbor_id
        if best_drop >= GROUNDWATER_FLOW_MINIMUM_RECEIVER_HEAD_DROP_M:
            flow_to_by_id[cell_id] = best_neighbor_id
            gradient_by_id[cell_id] = clamp(
                best_drop / GROUNDWATER_FLOW_GRADIENT_SCALE_M
            )
        else:
            flow_to_by_id[cell_id] = -1
            gradient_by_id[cell_id] = 0.0

    available_by_id = {
        cell_id: max(
            0.0,
            float(cells_by_id[cell_id].get("groundwater_recharge_km3_y", 0.0)),
        )
        for cell_id in candidate_ids
    }
    lateral_inflow_by_id = {cell_id: 0.0 for cell_id in candidate_ids}
    lateral_export_by_id = {cell_id: 0.0 for cell_id in candidate_ids}
    internal_outflow_by_id = {cell_id: 0.0 for cell_id in candidate_ids}
    processed_available_by_id: dict[int, float] = {}
    for cell_id in sorted(candidate_ids, key=lambda item: (-heads[item], item)):
        cell = cells_by_id[cell_id]
        available = max(0.0, available_by_id[cell_id])
        processed_available_by_id[cell_id] = available
        gradient = gradient_by_id[cell_id]
        storage = clamp(float(cell.get("aquifer_storage_index", 0.0)))
        productivity = clamp(float(cell.get("aquifer_productivity_index", 0.0)))
        extraction_risk = clamp(
            float(cell.get("aquifer_extraction_risk_index", 0.0))
        )
        export_fraction = clamp(
            0.12
            + gradient * 0.56
            + productivity * 0.18
            + storage * 0.08
            - extraction_risk * 0.12,
            0.0,
            GROUNDWATER_FLOW_MAXIMUM_LATERAL_EXPORT_FRACTION,
        )
        flow_to = flow_to_by_id[cell_id]
        export = available * export_fraction if flow_to >= 0 else 0.0
        lateral_export_by_id[cell_id] = export
        if flow_to in candidate_ids:
            available_by_id[flow_to] += export
            lateral_inflow_by_id[flow_to] += export
            internal_outflow_by_id[cell_id] = export

    def surface_connection(cell: dict[str, Any]) -> float:
        water_body = str(cell.get("water_body_type", "land"))
        connection = 0.0
        if bool(cell.get("is_river", False)):
            connection = max(connection, 0.62)
        if bool(cell.get("is_lake", False)) or water_body in surface_water_types:
            connection = max(connection, 0.56)
        if float(cell.get("wetland_extent_index", 0.0)) >= 0.35:
            connection = max(connection, 0.42)
        if bool(cell.get("is_closed_basin", False)):
            connection = max(connection, 0.24)
        if float(cell.get("distance_to_marine_water_km", 9999.0)) <= 160.0:
            connection = max(connection, 0.28)
        return clamp(connection)

    def flow_regime(
        cell: dict[str, Any],
        gradient: float,
        discharge_mm_y: float,
        spring_index: float,
        flow_to: int,
    ) -> str:
        if not is_candidate(cell):
            return "excluded"
        recharge = float(cell.get("groundwater_recharge_mm_y", 0.0))
        if spring_index >= 0.45 and discharge_mm_y >= 20.0:
            return "discharge_zone"
        if recharge >= 60.0 and gradient >= 0.08 and flow_to >= 0:
            return "recharge_throughflow"
        if recharge >= 60.0:
            return "recharge_mound"
        if gradient >= 0.05 and flow_to >= 0:
            return "throughflow"
        if discharge_mm_y >= 12.0:
            return "lowland_discharge"
        return "stagnant_or_low_yield"

    expected_by_id: dict[int, dict[str, float | int | str]] = {}
    for cell_id, cell in cells_by_id.items():
        if cell_id not in candidate_ids:
            expected_by_id[cell_id] = {
                "head": heads[cell_id],
                "gradient": 0.0,
                "lateral_export": 0.0,
                "lateral_inflow": 0.0,
                "available": 0.0,
                "internal_outflow": 0.0,
                "discharge_mm": 0.0,
                "discharge_km3": 0.0,
                "retained": 0.0,
                "residual": 0.0,
                "flow_to": -1,
                "spring": 0.0,
                "baseflow": 0.0,
                "regime": "excluded",
            }
            continue
        area = max(0.0, float(cell.get("area_km2", 0.0)))
        if area <= 0.0:
            return failure
        available = processed_available_by_id[cell_id]
        export = lateral_export_by_id[cell_id]
        internal_outflow = internal_outflow_by_id[cell_id]
        flow_to = flow_to_by_id[cell_id]
        flow_to_candidate = flow_to in candidate_ids
        gradient = gradient_by_id[cell_id]
        productivity = clamp(float(cell.get("aquifer_productivity_index", 0.0)))
        storage = clamp(float(cell.get("aquifer_storage_index", 0.0)))
        quality = clamp(float(cell.get("aquifer_quality_index", 0.0)))
        extraction_risk = clamp(
            float(cell.get("aquifer_extraction_risk_index", 0.0))
        )
        connection = surface_connection(cell)
        local_available = max(
            0.0,
            available - (export if flow_to >= 0 else 0.0),
        )
        surface_fraction = clamp(
            connection * 0.58
            + (1.0 - gradient) * 0.10
            + productivity * 0.08
            - extraction_risk * 0.12
        )
        if flow_to >= 0 and not flow_to_candidate:
            discharge_km3 = min(
                available,
                export + local_available * surface_fraction,
            )
        else:
            discharge_km3 = min(available, local_available * surface_fraction)
        discharge_mm = discharge_km3 / (area * 1.0e-6)
        spring = clamp(
            discharge_mm / 260.0 * 0.42
            + gradient * 0.20
            + connection * 0.18
            + productivity * 0.12
            + quality * 0.08
        )
        baseflow = clamp(
            discharge_mm / 260.0 * 0.42
            + float(cell.get("groundwater_recharge_mm_y", 0.0))
            / 340.0
            * 0.16
            + storage * 0.16
            + productivity * 0.16
            + (0.12 if bool(cell.get("is_river", False)) else 0.0)
            - extraction_risk * 0.10
        )
        retained = max(
            0.0,
            available - internal_outflow - discharge_km3,
        )
        residual = available - internal_outflow - discharge_km3 - retained
        expected_by_id[cell_id] = {
            "head": heads[cell_id],
            "gradient": gradient,
            "lateral_export": export,
            "lateral_inflow": lateral_inflow_by_id[cell_id],
            "available": available,
            "internal_outflow": internal_outflow,
            "discharge_mm": discharge_mm,
            "discharge_km3": discharge_km3,
            "retained": retained,
            "residual": residual,
            "flow_to": flow_to,
            "spring": spring,
            "baseflow": baseflow,
            "regime": flow_regime(
                cell,
                gradient,
                discharge_mm,
                spring,
                flow_to,
            ),
        }

    field_map = {
        "groundwater_hydraulic_head_m": ("head", 6),
        "groundwater_gradient_index": ("gradient", 6),
        "groundwater_lateral_flow_km3_y": ("lateral_export", 6),
        "groundwater_lateral_inflow_km3_y": ("lateral_inflow", 6),
        "groundwater_available_volume_km3_y": ("available", 6),
        "groundwater_internal_lateral_outflow_km3_y": (
            "internal_outflow",
            6,
        ),
        "groundwater_discharge_mm_y": ("discharge_mm", 6),
        "groundwater_discharge_km3_y": ("discharge_km3", 6),
        "groundwater_retained_storage_km3_y": ("retained", 6),
        "groundwater_flow_mass_balance_residual_km3_y": ("residual", 12),
        "spring_discharge_index": ("spring", 6),
        "baseflow_support_index": ("baseflow", 6),
    }
    for cell_id, cell in cells_by_id.items():
        expected = expected_by_id[cell_id]
        try:
            for field, (expected_key, digits) in field_map.items():
                actual = float(cell.get(field, math.inf))
                target = round(float(expected[expected_key]), digits)
                tolerance = 2.0e-10 if digits == 12 else 2.0e-6
                if abs(actual - target) > tolerance:
                    return failure
            if (
                int(cell.get("groundwater_flow_to_cell_id", -2))
                != int(expected["flow_to"])
                or str(cell.get("groundwater_flow_regime", ""))
                != str(expected["regime"])
                or str(expected["regime"]) not in flow_regimes
            ):
                return failure
        except (TypeError, ValueError):
            return failure

        if cell_id in candidate_ids:
            recharge = float(cell.get("groundwater_recharge_km3_y", 0.0))
            inflow = float(cell.get("groundwater_lateral_inflow_km3_y", 0.0))
            available = float(cell.get("groundwater_available_volume_km3_y", 0.0))
            internal_outflow = float(
                cell.get("groundwater_internal_lateral_outflow_km3_y", 0.0)
            )
            discharge = float(cell.get("groundwater_discharge_km3_y", 0.0))
            retained = float(cell.get("groundwater_retained_storage_km3_y", 0.0))
            residual = float(
                cell.get("groundwater_flow_mass_balance_residual_km3_y", 0.0)
            )
            if (
                abs(available - recharge - inflow) > 3.0e-6
                or abs(
                    available
                    - internal_outflow
                    - discharge
                    - retained
                    - residual
                )
                > 4.0e-6
            ):
                return failure

    def raw_sum(key: str) -> float:
        return sum(
            float(expected_by_id[cell_id][key])
            for cell_id in candidate_ids
        )

    expected_model = {
        "total_source_recharge_volume_km3_y": sum(
            float(cells_by_id[cell_id].get("groundwater_recharge_km3_y", 0.0))
            for cell_id in candidate_ids
        ),
        "total_internal_lateral_inflow_volume_km3_y": raw_sum(
            "lateral_inflow"
        ),
        "total_internal_lateral_outflow_volume_km3_y": raw_sum(
            "internal_outflow"
        ),
        "total_lateral_throughput_volume_km3_y": raw_sum(
            "lateral_export"
        ),
        "total_groundwater_discharge_volume_km3_y": raw_sum(
            "discharge_km3"
        ),
        "total_retained_storage_volume_km3_y": raw_sum("retained"),
        "mass_balance_residual_km3_y": raw_sum("residual"),
    }
    for key, expected in expected_model.items():
        tolerance = 1.0e-8 if key == "mass_balance_residual_km3_y" else 2.0e-5
        if abs(float(model.get(key, math.inf)) - expected) > tolerance:
            return failure
    if abs(
        expected_model["total_internal_lateral_inflow_volume_km3_y"]
        - expected_model["total_internal_lateral_outflow_volume_km3_y"]
    ) > 0.001:
        return failure
    if abs(
        expected_model["total_source_recharge_volume_km3_y"]
        - expected_model["total_groundwater_discharge_volume_km3_y"]
        - expected_model["total_retained_storage_volume_km3_y"]
    ) > 0.001:
        return failure

    expected_summary = {
        "total_groundwater_discharge_km3_y": expected_model[
            "total_groundwater_discharge_volume_km3_y"
        ],
        "total_groundwater_lateral_flow_km3_y": expected_model[
            "total_lateral_throughput_volume_km3_y"
        ],
        "total_groundwater_internal_lateral_flow_km3_y": expected_model[
            "total_internal_lateral_outflow_volume_km3_y"
        ],
        "total_groundwater_retained_storage_km3_y": expected_model[
            "total_retained_storage_volume_km3_y"
        ],
        "groundwater_flow_mass_balance_residual_km3_y": expected_model[
            "mass_balance_residual_km3_y"
        ],
    }
    for key, expected in expected_summary.items():
        tolerance = (
            1.0e-8
            if key == "groundwater_flow_mass_balance_residual_km3_y"
            else 0.00002
        )
        if abs(float(summary.get(key, math.inf)) - expected) > tolerance:
            return failure
    if abs(
        expected_model["total_source_recharge_volume_km3_y"]
        - float(
            payload.get("groundwater_recharge_model", {}).get(
                "total_groundwater_recharge_volume_km3_y",
                math.inf,
            )
        )
    ) > 0.001:
        return failure
    return []
