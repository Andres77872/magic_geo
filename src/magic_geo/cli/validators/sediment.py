"""Fluvial, hillslope, glacial, and inventory sediment replay checks."""

from __future__ import annotations

import math
from typing import Any

from .._constants import (
    FLUVIAL_SEDIMENT_CLOSED_LAKE_TRAP_FRACTION,
    FLUVIAL_SEDIMENT_INLAND_SEA_DEPOSITION_FRACTION,
    FLUVIAL_SEDIMENT_LAKE_TRAP_FRACTION,
    FLUVIAL_SEDIMENT_MAX_TRANSPORT_CAPACITY_FRACTION,
    FLUVIAL_SEDIMENT_MIN_TRANSPORT_CAPACITY_FRACTION,
    FLUVIAL_SEDIMENT_OPEN_OCEAN_DEPOSITION_FRACTION,
    FLUVIAL_SEDIMENT_ROUTING_MODEL,
    FLUVIAL_SEDIMENT_SHELF_DEPOSITION_FRACTION,
    GLACIAL_SEDIMENT_MOBILE_FRACTION,
    GLACIAL_SEDIMENT_TRANSPORT_MODEL,
    HILLSLOPE_SEDIMENT_LITHOLOGY_RESISTANCE,
    HILLSLOPE_SEDIMENT_MAX_EFFECTIVE_DIFFUSIVITY,
    HILLSLOPE_SEDIMENT_TRANSPORT_MODEL,
    MATURATION_REFERENCE_TIMESTEP_MA,
    SEDIMENT_INVENTORY_MODEL,
)
from ...grounded_ice_validation import MODEL as GROUNDED_ICE_MODEL, TRANSPORT_MODEL as GROUNDED_GLACIAL_MODEL, grounded_ice_version, require_grounded_stage_inputs
from ._shared import _nominal_time_record_valid


def _validate_fluvial_sediment_routing(
    payload: dict[str, Any],
    summary: dict[str, Any],
    cells_by_id: dict[int, dict[str, Any]],
) -> tuple[list[str], dict[str, dict[int, float]], bool]:
    failures: list[str] = []
    cell_ids = set(cells_by_id)
    volume_fields = (
        "local_source",
        "incoming",
        "outgoing",
        "local_deposition",
        "terminal_land_deposition",
        "marine_deposition",
        "depression_fill",
        "terminal_export",
        "terminal_capture",
    )
    expected = {
        field: {cell_id: 0.0 for cell_id in cell_ids}
        for field in volume_fields
    }
    expected_event_count = {cell_id: 0 for cell_id in cell_ids}
    expected["event_count"] = expected_event_count

    model = payload.get("fluvial_sediment_routing_model", {})
    history = payload.get("fluvial_sediment_routing_history", [])
    model_keys = {
        "model_type",
        "material_unit",
        "routing_graph",
        "transport_capacity_model",
        "depression_deposition_model",
        "land_terminal_model",
        "marine_terminal_model",
        "cell_depth_conversion",
        "source_material_partition_model",
        "source_material_partition_is_coupled_external_state",
        "local_source_is_timestep_scaled_upstream",
        "routing_partition_fractions_timestep_invariant",
        "time_step_convergence_demonstrated",
        "mass_conserving",
        "depression_fill_deposition_is_cross_cut",
        "grain_size_resolved",
        "physical_time_resolved",
        "subcell_channel_geometry_resolved",
        "model_limitation",
        "minimum_transport_capacity_fraction",
        "maximum_transport_capacity_fraction",
        "overflowing_lake_trap_fraction",
        "closed_lake_trap_fraction",
        "open_ocean_deposition_fraction",
        "continental_shelf_deposition_fraction",
        "inland_sea_deposition_fraction",
        "stage_count",
        "total_active_cell_step_count",
        "total_routed_edge_count",
        "total_terminal_allocation_count",
        "total_local_source_volume_km3",
        "total_routed_throughput_volume_km3",
        "total_capacity_deposition_volume_km3",
        "total_depression_fill_deposition_volume_km3",
        "total_lake_trap_deposition_volume_km3",
        "total_terminal_land_deposition_volume_km3",
        "total_marine_deposition_volume_km3",
        "total_terminal_export_volume_km3",
        "total_alluvium_entrainment_volume_km3",
        "total_bedrock_erosion_volume_km3",
        "total_deposition_volume_km3",
        "total_mass_balance_residual_km3",
    }
    if (
        not isinstance(model, dict)
        or not model_keys.issubset(model)
        or not isinstance(history, list)
    ):
        return ["fluvial sediment routing model or history missing"], expected, False

    def volume_close(actual: float, target: float) -> bool:
        return abs(actual - target) <= max(0.001, abs(target) * 2.0e-9)

    def scalar_close(actual: float, target: float) -> bool:
        return abs(actual - target) <= max(0.0000002, abs(target) * 2.0e-8)

    try:
        configured_stage_count = int(
            payload.get("simulation_clock", {}).get(
                "configured_erosion_iteration_count", -1
            )
        )
        nominal_timestep_ma = float(
            payload.get("simulation_clock", {}).get("nominal_timestep_ma", math.nan)
        )
        model_constants = (
            float(model["minimum_transport_capacity_fraction"]),
            float(model["maximum_transport_capacity_fraction"]),
            float(model["overflowing_lake_trap_fraction"]),
            float(model["closed_lake_trap_fraction"]),
            float(model["open_ocean_deposition_fraction"]),
            float(model["continental_shelf_deposition_fraction"]),
            float(model["inland_sea_deposition_fraction"]),
        )
        model_stage_count = int(model["stage_count"])
    except (TypeError, ValueError):
        return ["fluvial sediment routing metadata values invalid"], expected, False
    if (
        model.get("model_type") != FLUVIAL_SEDIMENT_ROUTING_MODEL
        or model.get("material_unit") != "km3"
        or model.get("routing_graph")
        != "erosion_stage_acyclic_hydrologic_flow_to_v1"
        or model.get("transport_capacity_model")
        != "bounded_dimensionless_flow_slope_runoff_river_capacity_fraction_v1"
        or model.get("depression_deposition_model")
        != "explicit_spill_elevation_accommodation_then_capacity_and_lake_trap_v1"
        or model.get("land_terminal_model")
        != "depression_footprint_proportional_accommodation_then_area_weighted_aggradation_v1"
        or model.get("marine_terminal_model")
        != "water_body_class_deposition_then_unresolved_deep_marine_export_v1"
        or model.get("cell_depth_conversion")
        != "volume_km3_times_1000_divided_by_cell_area_km2"
        or model.get("source_material_partition_model")
        != "available_alluvium_after_hillslope_then_bedrock_erosion_v1"
        or model.get("source_material_partition_is_coupled_external_state")
        is not True
        or model.get("local_source_is_timestep_scaled_upstream") is not True
        or model.get("routing_partition_fractions_timestep_invariant") is not True
        or model.get("time_step_convergence_demonstrated") is not False
        or model.get("mass_conserving") is not True
        or model.get("depression_fill_deposition_is_cross_cut") is not True
        or bool(model.get("grain_size_resolved", True))
        or bool(model.get("physical_time_resolved", True))
        or bool(model.get("subcell_channel_geometry_resolved", True))
        or model.get("model_limitation")
        != "dimensionless_capacity_proxy_without_grain_size_calibrated_time_or_subcell_channels"
        or any(
            not scalar_close(actual, target)
            for actual, target in zip(
                model_constants,
                (
                    FLUVIAL_SEDIMENT_MIN_TRANSPORT_CAPACITY_FRACTION,
                    FLUVIAL_SEDIMENT_MAX_TRANSPORT_CAPACITY_FRACTION,
                    FLUVIAL_SEDIMENT_LAKE_TRAP_FRACTION,
                    FLUVIAL_SEDIMENT_CLOSED_LAKE_TRAP_FRACTION,
                    FLUVIAL_SEDIMENT_OPEN_OCEAN_DEPOSITION_FRACTION,
                    FLUVIAL_SEDIMENT_SHELF_DEPOSITION_FRACTION,
                    FLUVIAL_SEDIMENT_INLAND_SEA_DEPOSITION_FRACTION,
                ),
            )
        )
        or configured_stage_count < 0
        or not math.isfinite(nominal_timestep_ma)
        or not 0.0 < nominal_timestep_ma <= MATURATION_REFERENCE_TIMESTEP_MA
        or len(history) != configured_stage_count
        or model_stage_count != len(history)
    ):
        failures.append("fluvial sediment routing metadata invalid")

    stage_required_keys = {
        "id",
        "feedback_stage_id",
        "erosion_iteration",
        "active_cell_step_count",
        "routed_edge_count",
        "land_terminal_count",
        "marine_terminal_count",
        "terminal_allocation_count",
        "accumulation_scale",
        "local_source_volume_km3",
        "routed_throughput_volume_km3",
        "capacity_deposition_volume_km3",
        "depression_fill_deposition_volume_km3",
        "lake_trap_deposition_volume_km3",
        "terminal_land_deposition_volume_km3",
        "marine_deposition_volume_km3",
        "terminal_export_volume_km3",
        "alluvium_entrainment_volume_km3",
        "bedrock_erosion_volume_km3",
        "total_deposition_volume_km3",
        "mass_balance_residual_km3",
        "cell_steps",
        "terminal_allocations",
    }
    step_required_keys = {
        "cell_id",
        "flow_to_cell_id",
        "depression_component_id",
        "depression_sink_cell_id",
        "water_body_type",
        "is_water",
        "is_river",
        "is_lake",
        "lake_overflows",
        "is_land_terminal",
        "is_marine_terminal",
        "cell_area_km2",
        "flow_accumulation",
        "runoff_mm_y",
        "hydrologic_flow_slope",
        "routing_base_elevation_m",
        "spill_elevation_m",
        "local_source_volume_km3",
        "incoming_volume_km3",
        "available_volume_km3",
        "transport_capacity_fraction",
        "depression_accommodation_volume_km3",
        "capacity_deposition_volume_km3",
        "depression_fill_deposition_volume_km3",
        "lake_trap_deposition_volume_km3",
        "marine_deposition_volume_km3",
        "routed_outgoing_volume_km3",
        "terminal_land_storage_volume_km3",
        "terminal_export_volume_km3",
        "local_mass_balance_residual_km3",
    }
    allocation_required_keys = {
        "sink_cell_id",
        "target_cell_id",
        "depression_component_id",
        "target_area_km2",
        "routing_base_elevation_m",
        "spill_elevation_m",
        "prior_local_deposition_volume_km3",
        "accommodation_before_allocation_km3",
        "accommodation_deposition_volume_km3",
        "excess_aggradation_volume_km3",
        "total_deposition_volume_km3",
    }
    total_metrics = {
        "active_cell_step_count": 0,
        "routed_edge_count": 0,
        "terminal_allocation_count": 0,
        "land_terminal_count": 0,
        "marine_terminal_count": 0,
        "local_source_volume_km3": 0.0,
        "routed_throughput_volume_km3": 0.0,
        "capacity_deposition_volume_km3": 0.0,
        "depression_fill_deposition_volume_km3": 0.0,
        "lake_trap_deposition_volume_km3": 0.0,
        "terminal_land_deposition_volume_km3": 0.0,
        "marine_deposition_volume_km3": 0.0,
        "terminal_export_volume_km3": 0.0,
        "total_deposition_volume_km3": 0.0,
        "mass_balance_residual_km3": 0.0,
    }
    feedback_history = payload.get("earth_system_feedback_history", [])
    routing_valid = not failures

    for stage_index, stage in enumerate(history):
        if not isinstance(stage, dict) or not stage_required_keys.issubset(stage):
            failures.append("fluvial sediment routing stage missing fields")
            routing_valid = False
            break
        steps = stage.get("cell_steps", [])
        allocations = stage.get("terminal_allocations", [])
        try:
            accumulation_scale = float(stage["accumulation_scale"])
            stage_id = int(stage["id"])
            feedback_stage_id = int(stage["feedback_stage_id"])
            erosion_iteration = int(stage["erosion_iteration"])
            emitted_stage_counts = {
                key: int(stage[key])
                for key in (
                    "active_cell_step_count",
                    "routed_edge_count",
                    "land_terminal_count",
                    "marine_terminal_count",
                    "terminal_allocation_count",
                )
            }
            emitted_stage_volumes = {
                key: float(stage[key])
                for key in (
                    "local_source_volume_km3",
                    "routed_throughput_volume_km3",
                    "capacity_deposition_volume_km3",
                    "depression_fill_deposition_volume_km3",
                    "lake_trap_deposition_volume_km3",
                    "terminal_land_deposition_volume_km3",
                    "marine_deposition_volume_km3",
                    "terminal_export_volume_km3",
                    "total_deposition_volume_km3",
                    "mass_balance_residual_km3",
                )
            }
        except (TypeError, ValueError):
            failures.append("fluvial sediment routing stage identifiers invalid")
            routing_valid = False
            break
        if (
            not isinstance(steps, list)
            or not isinstance(allocations, list)
            or accumulation_scale < 1.0
            or stage_id != stage_index
            or feedback_stage_id != stage_index + 1
            or erosion_iteration != stage_index + 1
            or not _nominal_time_record_valid(
                stage,
                expected_start_ma=stage_index * nominal_timestep_ma,
                expected_end_ma=(stage_index + 1) * nominal_timestep_ma,
                expected_role="erosion_interval_bulk_fluvial_routing",
            )
        ):
            failures.append("fluvial sediment routing stage sequence invalid")
            routing_valid = False
            break

        incoming_by_cell = {cell_id: 0.0 for cell_id in cell_ids}
        seen_step_ids: set[int] = set()
        participant_ids: set[int] = set()
        terminal_storage_by_sink: dict[int, float] = {}
        local_deposition_by_cell = {cell_id: 0.0 for cell_id in cell_ids}
        stage_metrics = {
            "active_cell_step_count": len(steps),
            "routed_edge_count": 0,
            "land_terminal_count": 0,
            "marine_terminal_count": 0,
            "terminal_allocation_count": 0,
            "local_source_volume_km3": 0.0,
            "routed_throughput_volume_km3": 0.0,
            "capacity_deposition_volume_km3": 0.0,
            "local_depression_fill_volume_km3": 0.0,
            "depression_fill_deposition_volume_km3": 0.0,
            "lake_trap_deposition_volume_km3": 0.0,
            "terminal_land_deposition_volume_km3": 0.0,
            "marine_deposition_volume_km3": 0.0,
            "terminal_export_volume_km3": 0.0,
            "total_deposition_volume_km3": 0.0,
            "mass_balance_residual_km3": 0.0,
        }
        stage_invalid = False
        for step in steps:
            if not isinstance(step, dict) or not step_required_keys.issubset(step):
                stage_invalid = True
                break
            try:
                cell_id = int(step["cell_id"])
                flow_to = int(step["flow_to_cell_id"])
                depression_component_id = int(step["depression_component_id"])
                area_km2 = float(step["cell_area_km2"])
                flow_accumulation = float(step["flow_accumulation"])
                runoff_mm_y = float(step["runoff_mm_y"])
                slope = float(step["hydrologic_flow_slope"])
                routing_base = float(step["routing_base_elevation_m"])
                spill_elevation = float(step["spill_elevation_m"])
                source = float(step["local_source_volume_km3"])
                incoming = float(step["incoming_volume_km3"])
                available = float(step["available_volume_km3"])
                capacity_fraction = float(step["transport_capacity_fraction"])
                accommodation = float(
                    step["depression_accommodation_volume_km3"]
                )
                capacity_deposition = float(
                    step["capacity_deposition_volume_km3"]
                )
                depression_fill = float(
                    step["depression_fill_deposition_volume_km3"]
                )
                lake_trap = float(step["lake_trap_deposition_volume_km3"])
                marine_deposition = float(step["marine_deposition_volume_km3"])
                outgoing = float(step["routed_outgoing_volume_km3"])
                terminal_storage = float(
                    step["terminal_land_storage_volume_km3"]
                )
                terminal_export = float(step["terminal_export_volume_km3"])
                local_residual = float(step["local_mass_balance_residual_km3"])
            except (TypeError, ValueError):
                stage_invalid = True
                break
            numeric_values = (
                area_km2,
                flow_accumulation,
                runoff_mm_y,
                slope,
                routing_base,
                spill_elevation,
                source,
                incoming,
                available,
                capacity_fraction,
                accommodation,
                capacity_deposition,
                depression_fill,
                lake_trap,
                marine_deposition,
                outgoing,
                terminal_storage,
                terminal_export,
                local_residual,
            )
            is_water = bool(step["is_water"])
            is_river = bool(step["is_river"])
            is_lake = bool(step["is_lake"])
            lake_overflows = bool(step["lake_overflows"])
            expected_land_terminal = not is_water and flow_to < 0
            expected_marine_terminal = is_water and flow_to < 0
            final_cell = cells_by_id.get(cell_id)
            if (
                cell_id not in cell_ids
                or cell_id in seen_step_ids
                or final_cell is None
                or area_km2 <= 0.0
                or not scalar_close(area_km2, float(final_cell.get("area_km2", -1.0)))
                or not all(math.isfinite(value) for value in numeric_values)
                or min(
                    flow_accumulation,
                    runoff_mm_y,
                    slope,
                    source,
                    incoming,
                    available,
                    capacity_fraction,
                    accommodation,
                    capacity_deposition,
                    depression_fill,
                    lake_trap,
                    marine_deposition,
                    outgoing,
                    terminal_storage,
                    terminal_export,
                )
                < 0.0
                or bool(step["is_land_terminal"]) != expected_land_terminal
                or bool(step["is_marine_terminal"]) != expected_marine_terminal
                or (flow_to >= 0 and flow_to not in cell_ids)
                or (is_water and flow_to >= 0)
                or not volume_close(incoming, incoming_by_cell[cell_id])
                or not volume_close(available, source + incoming)
            ):
                stage_invalid = True
                break

            seen_step_ids.add(cell_id)
            participant_ids.add(cell_id)
            expected_capacity = 0.0
            expected_accommodation = 0.0
            expected_capacity_deposition = 0.0
            expected_depression_fill = 0.0
            expected_lake_trap = 0.0
            expected_marine_deposition = 0.0
            expected_outgoing = 0.0
            expected_terminal_storage = 0.0
            expected_terminal_export = 0.0
            if expected_marine_terminal:
                water_body = str(step["water_body_type"])
                deposition_fraction = {
                    "continental_shelf": FLUVIAL_SEDIMENT_SHELF_DEPOSITION_FRACTION,
                    "inland_sea": FLUVIAL_SEDIMENT_INLAND_SEA_DEPOSITION_FRACTION,
                }.get(water_body, FLUVIAL_SEDIMENT_OPEN_OCEAN_DEPOSITION_FRACTION)
                expected_marine_deposition = available * deposition_fraction
                expected_terminal_export = available - expected_marine_deposition
                stage_metrics["marine_terminal_count"] += 1
            elif expected_land_terminal:
                expected_terminal_storage = available
                terminal_storage_by_sink[cell_id] = available
                stage_metrics["land_terminal_count"] += 1
            else:
                flow_index = min(
                    1.0,
                    math.sqrt(max(0.0, flow_accumulation) / accumulation_scale),
                )
                slope_index = min(1.0, max(0.0, slope) * 1200.0)
                runoff_index = min(1.0, max(0.0, runoff_mm_y) / 2000.0)
                expected_capacity = min(
                    FLUVIAL_SEDIMENT_MAX_TRANSPORT_CAPACITY_FRACTION,
                    max(
                        FLUVIAL_SEDIMENT_MIN_TRANSPORT_CAPACITY_FRACTION,
                        FLUVIAL_SEDIMENT_MIN_TRANSPORT_CAPACITY_FRACTION
                        + 0.045 * flow_index
                        + 0.025 * slope_index
                        + 0.015 * runoff_index
                        + (0.015 if is_river else 0.0),
                    ),
                )
                if depression_component_id >= 0:
                    expected_accommodation = (
                        max(0.0, spill_elevation - routing_base)
                        * area_km2
                        / 1000.0
                    )
                    expected_depression_fill = min(
                        available, expected_accommodation
                    )
                remaining = available - expected_depression_fill
                expected_capacity_deposition = min(
                    remaining, available * (1.0 - expected_capacity)
                )
                remaining -= expected_capacity_deposition
                if is_lake:
                    lake_fraction = (
                        FLUVIAL_SEDIMENT_LAKE_TRAP_FRACTION
                        if lake_overflows
                        else FLUVIAL_SEDIMENT_CLOSED_LAKE_TRAP_FRACTION
                    )
                    expected_lake_trap = min(
                        remaining,
                        max(
                            0.0,
                            available * lake_fraction
                            - expected_depression_fill
                            - expected_capacity_deposition,
                        ),
                    )
                    remaining -= expected_lake_trap
                expected_outgoing = max(0.0, remaining)
            expected_residual = (
                available
                - expected_capacity_deposition
                - expected_depression_fill
                - expected_lake_trap
                - expected_marine_deposition
                - expected_outgoing
                - expected_terminal_storage
                - expected_terminal_export
            )
            comparisons = (
                (capacity_fraction, expected_capacity),
                (accommodation, expected_accommodation),
                (capacity_deposition, expected_capacity_deposition),
                (depression_fill, expected_depression_fill),
                (lake_trap, expected_lake_trap),
                (marine_deposition, expected_marine_deposition),
                (outgoing, expected_outgoing),
                (terminal_storage, expected_terminal_storage),
                (terminal_export, expected_terminal_export),
                (local_residual, expected_residual),
            )
            if any(not volume_close(actual, target) for actual, target in comparisons):
                stage_invalid = True
                break
            if outgoing > 1.0e-15:
                incoming_by_cell[flow_to] += outgoing
                stage_metrics["routed_edge_count"] += 1
            local_deposition = capacity_deposition + depression_fill + lake_trap
            local_deposition_by_cell[cell_id] = local_deposition
            expected["local_source"][cell_id] += source
            expected["incoming"][cell_id] += incoming
            expected["outgoing"][cell_id] += outgoing
            expected["local_deposition"][cell_id] += local_deposition
            expected["marine_deposition"][cell_id] += marine_deposition
            expected["depression_fill"][cell_id] += depression_fill
            expected["terminal_export"][cell_id] += terminal_export
            expected["terminal_capture"][cell_id] += terminal_storage
            stage_metrics["local_source_volume_km3"] += source
            stage_metrics["routed_throughput_volume_km3"] += outgoing
            stage_metrics["capacity_deposition_volume_km3"] += capacity_deposition
            stage_metrics["local_depression_fill_volume_km3"] += depression_fill
            stage_metrics["lake_trap_deposition_volume_km3"] += lake_trap
            stage_metrics["marine_deposition_volume_km3"] += marine_deposition
            stage_metrics["terminal_export_volume_km3"] += terminal_export

        if not stage_invalid and any(
            incoming > 0.001 and cell_id not in seen_step_ids
            for cell_id, incoming in incoming_by_cell.items()
        ):
            stage_invalid = True

        allocation_groups: dict[int, list[dict[str, Any]]] = {}
        previous_allocation_key = (-1, -1)
        if not stage_invalid:
            for allocation in allocations:
                if (
                    not isinstance(allocation, dict)
                    or not allocation_required_keys.issubset(allocation)
                ):
                    stage_invalid = True
                    break
                try:
                    sink_id = int(allocation["sink_cell_id"])
                    target_id = int(allocation["target_cell_id"])
                    depression_component_id = int(
                        allocation["depression_component_id"]
                    )
                    target_area = float(allocation["target_area_km2"])
                    routing_base = float(allocation["routing_base_elevation_m"])
                    spill_elevation = float(allocation["spill_elevation_m"])
                    prior_local_deposition = float(
                        allocation["prior_local_deposition_volume_km3"]
                    )
                    accommodation_before = float(
                        allocation["accommodation_before_allocation_km3"]
                    )
                    accommodation_deposition = float(
                        allocation["accommodation_deposition_volume_km3"]
                    )
                    excess_aggradation = float(
                        allocation["excess_aggradation_volume_km3"]
                    )
                    total_deposition = float(
                        allocation["total_deposition_volume_km3"]
                    )
                except (TypeError, ValueError):
                    stage_invalid = True
                    break
                target_cell = cells_by_id.get(target_id)
                expected_accommodation = (
                    max(
                        0.0,
                        spill_elevation
                        - routing_base
                        - prior_local_deposition * 1000.0 / target_area,
                    )
                    * target_area
                    / 1000.0
                    if depression_component_id >= 0 and target_area > 0.0
                    else 0.0
                )
                allocation_key = (sink_id, target_id)
                if (
                    sink_id not in terminal_storage_by_sink
                    or target_id not in cell_ids
                    or target_cell is None
                    or allocation_key <= previous_allocation_key
                    or target_area <= 0.0
                    or not all(
                        math.isfinite(value)
                        for value in (
                            target_area,
                            routing_base,
                            spill_elevation,
                            prior_local_deposition,
                            accommodation_before,
                            accommodation_deposition,
                            excess_aggradation,
                            total_deposition,
                        )
                    )
                    or min(
                        prior_local_deposition,
                        accommodation_before,
                        accommodation_deposition,
                        excess_aggradation,
                        total_deposition,
                    )
                    < 0.0
                    or not scalar_close(
                        target_area, float(target_cell.get("area_km2", -1.0))
                    )
                    or not volume_close(
                        prior_local_deposition,
                        local_deposition_by_cell[target_id],
                    )
                    or not volume_close(accommodation_before, expected_accommodation)
                    or not volume_close(
                        total_deposition,
                        accommodation_deposition + excess_aggradation,
                    )
                ):
                    stage_invalid = True
                    break
                previous_allocation_key = allocation_key
                allocation_groups.setdefault(sink_id, []).append(allocation)

        terminal_accommodation_total = 0.0
        if not stage_invalid:
            if set(allocation_groups) != set(terminal_storage_by_sink):
                stage_invalid = True
            for sink_id, group in allocation_groups.items():
                if stage_invalid:
                    break
                storage = terminal_storage_by_sink[sink_id]
                capacities = [
                    float(item["accommodation_before_allocation_km3"])
                    for item in group
                ]
                areas = [float(item["target_area_km2"]) for item in group]
                total_capacity = sum(capacities)
                total_area = sum(areas)
                accommodation_total = min(storage, total_capacity)
                remaining_accommodation = accommodation_total
                last_capacity_index = max(
                    (index for index, value in enumerate(capacities) if value > 1.0e-15),
                    default=-1,
                )
                expected_accommodation_by_target: list[float] = []
                for index, capacity in enumerate(capacities):
                    allocation_volume = 0.0
                    if remaining_accommodation > 0.0 and total_capacity > 0.0 and capacity > 0.0:
                        allocation_volume = (
                            remaining_accommodation
                            if index == last_capacity_index
                            else min(
                                remaining_accommodation,
                                accommodation_total * capacity / total_capacity,
                            )
                        )
                    remaining_accommodation -= allocation_volume
                    expected_accommodation_by_target.append(allocation_volume)
                excess_total = storage - accommodation_total
                remaining_excess = excess_total
                expected_excess_by_target: list[float] = []
                for index, area in enumerate(areas):
                    allocation_volume = (
                        remaining_excess
                        if index + 1 == len(group)
                        else min(
                            remaining_excess,
                            excess_total * area / max(1.0e-15, total_area),
                        )
                    )
                    remaining_excess -= allocation_volume
                    expected_excess_by_target.append(allocation_volume)
                if not volume_close(
                    sum(float(item["total_deposition_volume_km3"]) for item in group),
                    storage,
                ):
                    stage_invalid = True
                    break
                for index, item in enumerate(group):
                    actual_accommodation = float(
                        item["accommodation_deposition_volume_km3"]
                    )
                    actual_excess = float(item["excess_aggradation_volume_km3"])
                    if (
                        not volume_close(
                            actual_accommodation,
                            expected_accommodation_by_target[index],
                        )
                        or not volume_close(
                            actual_excess, expected_excess_by_target[index]
                        )
                    ):
                        stage_invalid = True
                        break
                    target_id = int(item["target_cell_id"])
                    total_deposition = float(item["total_deposition_volume_km3"])
                    expected["terminal_land_deposition"][target_id] += total_deposition
                    expected["depression_fill"][target_id] += actual_accommodation
                    terminal_accommodation_total += actual_accommodation
                    if total_deposition > 1.0e-15:
                        participant_ids.add(target_id)
                        stage_metrics["terminal_allocation_count"] += 1
                stage_metrics["terminal_land_deposition_volume_km3"] += storage

        if stage_invalid:
            failures.append(
                f"fluvial sediment routing stage {stage_index} provenance invalid"
            )
            routing_valid = False
            break

        for cell_id in participant_ids:
            expected_event_count[cell_id] += 1
        stage_metrics["depression_fill_deposition_volume_km3"] = (
            stage_metrics["local_depression_fill_volume_km3"]
            + terminal_accommodation_total
        )
        stage_metrics["total_deposition_volume_km3"] = (
            stage_metrics["capacity_deposition_volume_km3"]
            + stage_metrics["local_depression_fill_volume_km3"]
            + stage_metrics["lake_trap_deposition_volume_km3"]
            + stage_metrics["terminal_land_deposition_volume_km3"]
            + stage_metrics["marine_deposition_volume_km3"]
        )
        stage_metrics["mass_balance_residual_km3"] = abs(
            stage_metrics["local_source_volume_km3"]
            - stage_metrics["total_deposition_volume_km3"]
            - stage_metrics["terminal_export_volume_km3"]
        )
        count_keys = (
            "active_cell_step_count",
            "routed_edge_count",
            "land_terminal_count",
            "marine_terminal_count",
            "terminal_allocation_count",
        )
        volume_keys = (
            "local_source_volume_km3",
            "routed_throughput_volume_km3",
            "capacity_deposition_volume_km3",
            "depression_fill_deposition_volume_km3",
            "lake_trap_deposition_volume_km3",
            "terminal_land_deposition_volume_km3",
            "marine_deposition_volume_km3",
            "terminal_export_volume_km3",
            "total_deposition_volume_km3",
            "mass_balance_residual_km3",
        )
        if any(emitted_stage_counts[key] != stage_metrics[key] for key in count_keys) or any(
            not math.isfinite(emitted_stage_volumes[key])
            or not volume_close(emitted_stage_volumes[key], stage_metrics[key])
            for key in volume_keys
        ):
            failures.append(
                f"fluvial sediment routing stage {stage_index} totals invalid"
            )
            routing_valid = False
            break
        if stage_metrics["mass_balance_residual_km3"] > max(
            0.000001,
            stage_metrics["local_source_volume_km3"] * 1.0e-10,
        ):
            failures.append(
                f"fluvial sediment routing stage {stage_index} does not close"
            )
            routing_valid = False
            break

        for key in total_metrics:
            total_metrics[key] += stage_metrics[key]
        if (
            not isinstance(feedback_history, list)
            or feedback_stage_id >= len(feedback_history)
            or not isinstance(feedback_history[feedback_stage_id], dict)
        ):
            failures.append("fluvial sediment routing feedback link invalid")
            routing_valid = False
            break
        feedback = feedback_history[feedback_stage_id]
        feedback_count_map = {
            "fluvial_sediment_active_cell_step_count": "active_cell_step_count",
            "fluvial_sediment_routed_edge_count": "routed_edge_count",
            "fluvial_sediment_land_terminal_count": "land_terminal_count",
            "fluvial_sediment_marine_terminal_count": "marine_terminal_count",
            "fluvial_sediment_terminal_allocation_count": "terminal_allocation_count",
        }
        feedback_volume_map = {
            "fluvial_sediment_local_source_volume_km3": "local_source_volume_km3",
            "fluvial_sediment_routed_throughput_volume_km3": "routed_throughput_volume_km3",
            "fluvial_sediment_capacity_deposition_volume_km3": "capacity_deposition_volume_km3",
            "fluvial_sediment_depression_fill_deposition_volume_km3": "depression_fill_deposition_volume_km3",
            "fluvial_sediment_lake_trap_deposition_volume_km3": "lake_trap_deposition_volume_km3",
            "fluvial_sediment_terminal_land_deposition_volume_km3": "terminal_land_deposition_volume_km3",
            "fluvial_sediment_marine_deposition_volume_km3": "marine_deposition_volume_km3",
            "fluvial_sediment_terminal_export_volume_km3": "terminal_export_volume_km3",
            "fluvial_sediment_mass_balance_residual_km3": "mass_balance_residual_km3",
        }
        try:
            feedback_counts_match = all(
                int(feedback.get(feedback_key, -1)) == stage_metrics[metric_key]
                for feedback_key, metric_key in feedback_count_map.items()
            )
            feedback_volumes_match = all(
                math.isfinite(float(feedback.get(feedback_key, math.nan)))
                and volume_close(
                    float(feedback.get(feedback_key, math.nan)),
                    stage_metrics[metric_key],
                )
                for feedback_key, metric_key in feedback_volume_map.items()
            )
        except (TypeError, ValueError, OverflowError):
            feedback_counts_match = False
            feedback_volumes_match = False
        if not feedback_counts_match or not feedback_volumes_match:
            failures.append("fluvial sediment routing feedback metrics invalid")
            routing_valid = False
            break

    model_metric_map = {
        "total_active_cell_step_count": "active_cell_step_count",
        "total_routed_edge_count": "routed_edge_count",
        "total_terminal_allocation_count": "terminal_allocation_count",
        "total_local_source_volume_km3": "local_source_volume_km3",
        "total_routed_throughput_volume_km3": "routed_throughput_volume_km3",
        "total_capacity_deposition_volume_km3": "capacity_deposition_volume_km3",
        "total_depression_fill_deposition_volume_km3": "depression_fill_deposition_volume_km3",
        "total_lake_trap_deposition_volume_km3": "lake_trap_deposition_volume_km3",
        "total_terminal_land_deposition_volume_km3": "terminal_land_deposition_volume_km3",
        "total_marine_deposition_volume_km3": "marine_deposition_volume_km3",
        "total_terminal_export_volume_km3": "terminal_export_volume_km3",
        "total_deposition_volume_km3": "total_deposition_volume_km3",
        "total_mass_balance_residual_km3": "mass_balance_residual_km3",
    }
    for model_key, metric_key in model_metric_map.items():
        try:
            actual = float(model.get(model_key, math.nan))
        except (TypeError, ValueError):
            routing_valid = False
            break
        if not math.isfinite(actual):
            routing_valid = False
            break
        target = float(total_metrics[metric_key])
        if (
            model_key
            in {
                "total_active_cell_step_count",
                "total_routed_edge_count",
                "total_terminal_allocation_count",
            }
            and int(actual) != int(target)
        ) or (
            model_key
            not in {
                "total_active_cell_step_count",
                "total_routed_edge_count",
                "total_terminal_allocation_count",
            }
            and not volume_close(actual, target)
        ):
            routing_valid = False
            break
    if not routing_valid and not any(
        "fluvial sediment routing" in failure for failure in failures
    ):
        failures.append("fluvial sediment routing aggregate metadata invalid")

    summary_metric_map = {
        "fluvial_sediment_routing_stage_count": len(history),
        "fluvial_sediment_active_cell_step_count": total_metrics[
            "active_cell_step_count"
        ],
        "fluvial_sediment_routed_edge_count": total_metrics["routed_edge_count"],
        "fluvial_sediment_routed_cell_count": sum(
            1 for count in expected_event_count.values() if count > 0
        ),
        "fluvial_sediment_land_terminal_count": total_metrics[
            "land_terminal_count"
        ],
        "fluvial_sediment_marine_terminal_count": total_metrics[
            "marine_terminal_count"
        ],
        "fluvial_sediment_terminal_capture_cell_count": sum(
            1 for value in expected["terminal_capture"].values() if value > 0.0
        ),
        "fluvial_sediment_terminal_allocation_count": total_metrics[
            "terminal_allocation_count"
        ],
        "fluvial_sediment_local_source_volume_km3": total_metrics[
            "local_source_volume_km3"
        ],
        "fluvial_sediment_routed_throughput_volume_km3": total_metrics[
            "routed_throughput_volume_km3"
        ],
        "fluvial_sediment_capacity_deposition_volume_km3": total_metrics[
            "capacity_deposition_volume_km3"
        ],
        "fluvial_sediment_depression_fill_deposition_volume_km3": total_metrics[
            "depression_fill_deposition_volume_km3"
        ],
        "fluvial_sediment_lake_trap_deposition_volume_km3": total_metrics[
            "lake_trap_deposition_volume_km3"
        ],
        "fluvial_sediment_terminal_land_deposition_volume_km3": total_metrics[
            "terminal_land_deposition_volume_km3"
        ],
        "fluvial_sediment_marine_deposition_volume_km3": total_metrics[
            "marine_deposition_volume_km3"
        ],
        "fluvial_sediment_terminal_export_volume_km3": total_metrics[
            "terminal_export_volume_km3"
        ],
        "fluvial_sediment_total_deposition_volume_km3": total_metrics[
            "total_deposition_volume_km3"
        ],
        "fluvial_sediment_mass_balance_residual_km3": total_metrics[
            "mass_balance_residual_km3"
        ],
    }
    summary_count_keys = {
        "fluvial_sediment_routing_stage_count",
        "fluvial_sediment_active_cell_step_count",
        "fluvial_sediment_routed_edge_count",
        "fluvial_sediment_routed_cell_count",
        "fluvial_sediment_land_terminal_count",
        "fluvial_sediment_marine_terminal_count",
        "fluvial_sediment_terminal_capture_cell_count",
        "fluvial_sediment_terminal_allocation_count",
    }
    for key, target in summary_metric_map.items():
        try:
            actual = float(summary.get(key, math.nan))
        except (TypeError, ValueError):
            routing_valid = False
            break
        if not math.isfinite(actual):
            routing_valid = False
            break
        if (
            key in summary_count_keys
            and int(actual) != int(target)
        ) or (key not in summary_count_keys and not volume_close(actual, float(target))):
            routing_valid = False
            break
    if not routing_valid and not any(
        "fluvial sediment routing" in failure for failure in failures
    ):
        failures.append("fluvial sediment routing summary metrics invalid")

    cell_field_map = {
        "fluvial_sediment_local_source_m": "local_source",
        "fluvial_sediment_routed_incoming_m": "incoming",
        "fluvial_sediment_routed_outgoing_m": "outgoing",
        "fluvial_sediment_local_deposition_m": "local_deposition",
        "fluvial_sediment_terminal_land_deposition_m": "terminal_land_deposition",
        "fluvial_sediment_marine_deposition_m": "marine_deposition",
        "fluvial_sediment_depression_fill_m": "depression_fill",
        "fluvial_sediment_terminal_export_m": "terminal_export",
    }
    for cell_id, cell in cells_by_id.items():
        area_km2 = float(cell.get("area_km2", 0.0))
        if area_km2 <= 0.0:
            routing_valid = False
            break
        for cell_field, volume_field in cell_field_map.items():
            try:
                actual_depth = float(cell.get(cell_field, math.nan))
            except (TypeError, ValueError):
                routing_valid = False
                break
            target_depth = expected[volume_field][cell_id] * 1000.0 / area_km2
            if (
                not math.isfinite(actual_depth)
                or actual_depth < 0.0
                or abs(actual_depth - target_depth)
                > max(0.000001, abs(target_depth) * 2.0e-9)
            ):
                routing_valid = False
                break
        if not routing_valid:
            break
        try:
            capture = float(
                cell.get("fluvial_sediment_terminal_capture_volume_km3", math.nan)
            )
            event_count = int(cell.get("fluvial_sediment_routing_event_count", -1))
        except (TypeError, ValueError):
            routing_valid = False
            break
        if (
            not volume_close(capture, expected["terminal_capture"][cell_id])
            or event_count != expected_event_count[cell_id]
        ):
            routing_valid = False
            break
    if not routing_valid and not any(
        "fluvial sediment routing" in failure for failure in failures
    ):
        failures.append("fluvial sediment routing cumulative cell fields invalid")
    return failures, expected, routing_valid


def _validate_hillslope_sediment_transport(
    payload: dict[str, Any],
    summary: dict[str, Any],
    cells_by_id: dict[int, dict[str, Any]],
) -> tuple[list[str], dict[str, dict[int, float]], bool]:
    failures: list[str] = []
    cell_ids = set(cells_by_id)
    expected = {
        "production": {cell_id: 0.0 for cell_id in cell_ids},
        "deposition": {cell_id: 0.0 for cell_id in cell_ids},
        "outgoing_edge_count": {cell_id: 0.0 for cell_id in cell_ids},
        "incoming_edge_count": {cell_id: 0.0 for cell_id in cell_ids},
    }
    model = payload.get("hillslope_sediment_transport_model", {})
    history = payload.get("hillslope_sediment_transport_history", [])
    model_keys = {
        "model_type",
        "transport_graph",
        "source_selection",
        "effective_diffusivity_model",
        "source_depth_model",
        "volume_transfer_model",
        "source_material_partition_model",
        "erosion_stage_source_partition_order",
        "configured_hillslope_diffusivity",
        "reference_timestep_ma",
        "nominal_timestep_ma",
        "maturation_timestep_scale",
        "reference_step_response_timestep_scaled",
        "time_step_convergence_demonstrated",
        "maximum_effective_diffusivity",
        "source_lithology_resistance",
        "mass_conserving",
        "physical_time_resolved",
        "shared_boundary_geometry_resolved",
        "regolith_depth_resolved",
        "model_limitation",
        "stage_input_snapshot",
        "stage_count",
        "total_transport_edge_count",
        "total_source_cell_stage_count",
        "total_target_cell_stage_count",
        "total_land_to_land_edge_count",
        "total_land_to_marine_edge_count",
        "total_production_volume_km3",
        "total_deposition_volume_km3",
        "total_alluvium_entrainment_volume_km3",
        "total_bedrock_erosion_volume_km3",
        "total_mass_balance_residual_km3",
        "max_source_production_depth_m",
        "max_target_deposition_depth_m",
        "mean_effective_diffusivity",
    }
    if (
        not isinstance(model, dict)
        or not model_keys.issubset(model)
        or not isinstance(history, list)
    ):
        return ["hillslope sediment transport model or history missing"], expected, False

    def volume_close(actual: float, target: float) -> bool:
        return abs(actual - target) <= max(0.001, abs(target) * 2.0e-9)

    def scalar_close(actual: float, target: float) -> bool:
        return abs(actual - target) <= max(0.0000002, abs(target) * 2.0e-8)

    transport_valid = True
    try:
        configured_diffusivity = float(model["configured_hillslope_diffusivity"])
        reference_timestep_ma = float(model["reference_timestep_ma"])
        nominal_timestep_ma = float(model["nominal_timestep_ma"])
        maturation_timestep_scale = float(model["maturation_timestep_scale"])
        maximum_diffusivity = float(model["maximum_effective_diffusivity"])
        model_stage_count = int(model["stage_count"])
        configured_stage_count = int(
            payload.get("simulation_clock", {}).get(
                "configured_erosion_iteration_count", -1
            )
        )
        clock_nominal_timestep_ma = float(
            payload.get("simulation_clock", {}).get("nominal_timestep_ma", math.nan)
        )
        resistance_payload = model["source_lithology_resistance"]
        resistance_values = {
            key: float(value)
            for key, value in resistance_payload.items()
        }
    except (AttributeError, TypeError, ValueError, OverflowError):
        return ["hillslope sediment transport metadata values invalid"], expected, False
    if (
        model.get("model_type") != HILLSLOPE_SEDIMENT_TRANSPORT_MODEL
        or model.get("transport_graph")
        != "one_directed_transfer_per_eligible_undirected_mesh_edge_v1"
        or model.get("source_selection")
        != "higher_non_marine_cell_to_lower_adjacent_cell"
        or model.get("effective_diffusivity_model")
        != "min_stability_cap_configured_reference_diffusivity_times_maturation_timestep_scale_divided_by_source_lithology_resistance"
        or model.get("source_depth_model")
        != "effective_diffusivity_times_elevation_drop_divided_by_source_neighbor_count"
        or model.get("volume_transfer_model")
        != "source_depth_times_source_area_equals_target_depth_times_target_area"
        or model.get("source_material_partition_model")
        != "available_alluvium_first_then_bedrock_erosion_v1"
        or model.get("erosion_stage_source_partition_order")
        != "hillslope_before_fluvial"
        or model.get("mass_conserving") is not True
        or model.get("reference_step_response_timestep_scaled") is not True
        or model.get("time_step_convergence_demonstrated") is not False
        or model.get("physical_time_resolved") is not False
        or model.get("shared_boundary_geometry_resolved") is not False
        or model.get("regolith_depth_resolved") is not True
        or model.get("model_limitation")
        != "procedural_bulk_transport_without_calibrated_time_shared_boundary_flux_or_grain_classes"
        or model.get("stage_input_snapshot")
        != "complete_cell_elevation_water_lake_lithology_and_sediment_inventory_state_before_transport_v2"
        or not math.isfinite(configured_diffusivity)
        or configured_diffusivity < 0.0
        or not math.isclose(
            reference_timestep_ma,
            MATURATION_REFERENCE_TIMESTEP_MA,
            abs_tol=1.0e-12,
            rel_tol=0.0,
        )
        or not math.isfinite(nominal_timestep_ma)
        or not 0.0 < nominal_timestep_ma <= MATURATION_REFERENCE_TIMESTEP_MA
        or not math.isclose(
            nominal_timestep_ma,
            clock_nominal_timestep_ma,
            abs_tol=1.0e-12,
            rel_tol=1.0e-12,
        )
        or not math.isclose(
            maturation_timestep_scale,
            nominal_timestep_ma / MATURATION_REFERENCE_TIMESTEP_MA,
            abs_tol=1.0e-12,
            rel_tol=1.0e-12,
        )
        or not scalar_close(
            maximum_diffusivity,
            HILLSLOPE_SEDIMENT_MAX_EFFECTIVE_DIFFUSIVITY,
        )
        or set(resistance_values) != set(HILLSLOPE_SEDIMENT_LITHOLOGY_RESISTANCE)
        or any(
            not math.isfinite(resistance_values[key])
            or not scalar_close(resistance_values[key], target)
            for key, target in HILLSLOPE_SEDIMENT_LITHOLOGY_RESISTANCE.items()
        )
        or configured_stage_count < 0
        or len(history) != configured_stage_count
        or model_stage_count != len(history)
    ):
        failures.append("hillslope sediment transport metadata invalid")
        transport_valid = False

    mesh_edges: list[tuple[int, int]] = []
    seen_mesh_edges: set[tuple[int, int]] = set()
    topology_valid = True
    for cell_id in sorted(cell_ids):
        cell = cells_by_id[cell_id]
        neighbors = cell.get("neighbors", [])
        if not isinstance(neighbors, list):
            topology_valid = False
            break
        try:
            neighbor_ids = [int(neighbor_id) for neighbor_id in neighbors]
        except (TypeError, ValueError):
            topology_valid = False
            break
        if len(set(neighbor_ids)) != len(neighbor_ids):
            topology_valid = False
            break
        for neighbor_id in neighbor_ids:
            if neighbor_id not in cell_ids:
                topology_valid = False
                break
            reverse_neighbors = cells_by_id[neighbor_id].get("neighbors", [])
            if cell_id not in reverse_neighbors:
                topology_valid = False
                break
            if neighbor_id > cell_id:
                pair = (cell_id, neighbor_id)
                if pair in seen_mesh_edges:
                    topology_valid = False
                    break
                seen_mesh_edges.add(pair)
                mesh_edges.append(pair)
        if not topology_valid:
            break
    if not topology_valid:
        failures.append("hillslope sediment transport mesh topology invalid")
        return failures, expected, False

    stage_required_keys = {
        "id",
        "feedback_stage_id",
        "erosion_iteration",
        "transport_edge_count",
        "source_cell_count",
        "target_cell_count",
        "land_to_land_edge_count",
        "land_to_marine_edge_count",
        "production_volume_km3",
        "deposition_volume_km3",
        "alluvium_entrainment_volume_km3",
        "bedrock_erosion_volume_km3",
        "mass_balance_residual_km3",
        "max_source_production_depth_m",
        "max_target_deposition_depth_m",
        "mean_effective_diffusivity",
        "input_cell_count",
        "input_cells",
        "edges",
    }
    input_cell_required_keys = {
        "cell_id",
        "lithology",
        "is_water",
        "is_lake",
        "elevation_m",
        "sediment_thickness_m",
    }
    edge_required_keys = {
        "id",
        "mesh_edge_cell_a_id",
        "mesh_edge_cell_b_id",
        "source_cell_id",
        "target_cell_id",
        "source_lithology",
        "source_neighbor_count",
        "source_is_water",
        "target_is_water",
        "target_is_lake",
        "source_area_km2",
        "target_area_km2",
        "source_elevation_m",
        "target_elevation_m",
        "elevation_drop_m",
        "source_lithology_resistance",
        "effective_diffusivity",
        "source_production_depth_m",
        "target_deposition_depth_m",
        "transfer_volume_km3",
        "mass_balance_residual_km3",
    }
    feedback_history = payload.get("earth_system_feedback_history", [])
    total_counts = {
        "transport_edge_count": 0,
        "source_cell_count": 0,
        "target_cell_count": 0,
        "land_to_land_edge_count": 0,
        "land_to_marine_edge_count": 0,
    }
    total_production_volume_km3 = 0.0
    total_deposition_volume_km3 = 0.0
    total_mass_balance_residual_km3 = 0.0
    total_effective_diffusivity = 0.0
    maximum_source_depth_m = 0.0
    maximum_target_depth_m = 0.0
    unique_source_ids: set[int] = set()
    unique_target_ids: set[int] = set()

    for stage_index, stage in enumerate(history):
        if not isinstance(stage, dict) or not stage_required_keys.issubset(stage):
            failures.append("hillslope sediment transport stage missing fields")
            transport_valid = False
            break
        input_cells = stage.get("input_cells", [])
        edges = stage.get("edges", [])
        try:
            stage_id = int(stage["id"])
            feedback_stage_id = int(stage["feedback_stage_id"])
            erosion_iteration = int(stage["erosion_iteration"])
            input_cell_count = int(stage["input_cell_count"])
            emitted_counts = {
                key: int(stage[key])
                for key in total_counts
            }
            emitted_values = {
                key: float(stage[key])
                for key in (
                    "production_volume_km3",
                    "deposition_volume_km3",
                    "mass_balance_residual_km3",
                    "max_source_production_depth_m",
                    "max_target_deposition_depth_m",
                    "mean_effective_diffusivity",
                )
            }
        except (TypeError, ValueError, OverflowError):
            failures.append("hillslope sediment transport stage values invalid")
            transport_valid = False
            break
        if (
            not isinstance(input_cells, list)
            or not isinstance(edges, list)
            or stage_id != stage_index
            or feedback_stage_id != stage_index + 1
            or erosion_iteration != stage_index + 1
            or not _nominal_time_record_valid(
                stage,
                expected_start_ma=stage_index * nominal_timestep_ma,
                expected_end_ma=(stage_index + 1) * nominal_timestep_ma,
                expected_role="erosion_interval_bulk_hillslope_transport",
            )
            or input_cell_count != len(input_cells)
            or input_cell_count != len(cell_ids)
            or any(value < 0 for value in emitted_counts.values())
            or not all(math.isfinite(value) for value in emitted_values.values())
            or any(value < 0.0 for value in emitted_values.values())
        ):
            failures.append("hillslope sediment transport stage sequence invalid")
            transport_valid = False
            break

        input_by_id: dict[int, dict[str, Any]] = {}
        input_invalid = False
        for input_index, input_cell in enumerate(input_cells):
            if (
                not isinstance(input_cell, dict)
                or not input_cell_required_keys.issubset(input_cell)
            ):
                input_invalid = True
                break
            try:
                input_cell_id = int(input_cell["cell_id"])
                elevation_m = float(input_cell["elevation_m"])
                sediment_thickness_m = float(input_cell["sediment_thickness_m"])
            except (TypeError, ValueError, OverflowError):
                input_invalid = True
                break
            lithology = str(input_cell["lithology"])
            if (
                input_cell_id != input_index
                or input_cell_id not in cell_ids
                or input_cell_id in input_by_id
                or lithology not in HILLSLOPE_SEDIMENT_LITHOLOGY_RESISTANCE
                or type(input_cell["is_water"]) is not bool
                or type(input_cell["is_lake"]) is not bool
                or not math.isfinite(elevation_m)
                or not math.isfinite(sediment_thickness_m)
                or sediment_thickness_m < 0.0
            ):
                input_invalid = True
                break
            input_by_id[input_cell_id] = input_cell
        if input_invalid or set(input_by_id) != cell_ids:
            failures.append("hillslope sediment transport input snapshot invalid")
            transport_valid = False
            break

        expected_transfers: list[tuple[int, int, int, int]] = []
        for cell_a_id, cell_b_id in mesh_edges:
            input_a = input_by_id[cell_a_id]
            input_b = input_by_id[cell_b_id]
            elevation_a = float(input_a["elevation_m"])
            elevation_b = float(input_b["elevation_m"])
            source_cell_id = cell_a_id
            target_cell_id = cell_b_id
            if elevation_b > elevation_a:
                source_cell_id = cell_b_id
                target_cell_id = cell_a_id
            source_input = input_by_id[source_cell_id]
            target_input = input_by_id[target_cell_id]
            elevation_drop_m = float(source_input["elevation_m"]) - float(
                target_input["elevation_m"]
            )
            resistance = HILLSLOPE_SEDIMENT_LITHOLOGY_RESISTANCE[
                str(source_input["lithology"])
            ]
            effective_diffusivity = min(
                HILLSLOPE_SEDIMENT_MAX_EFFECTIVE_DIFFUSIVITY,
                max(0.0, configured_diffusivity)
                * maturation_timestep_scale
                / max(1.0e-12, resistance),
            )
            if (
                bool(source_input["is_water"])
                or elevation_drop_m <= 1.0e-12
                or effective_diffusivity <= 0.0
            ):
                continue
            expected_transfers.append(
                (cell_a_id, cell_b_id, source_cell_id, target_cell_id)
            )
        if len(edges) != len(expected_transfers):
            failures.append(
                "hillslope sediment transport edge coverage invalid"
            )
            transport_valid = False
            break

        stage_production_by_cell = {cell_id: 0.0 for cell_id in cell_ids}
        stage_deposition_by_cell = {cell_id: 0.0 for cell_id in cell_ids}
        stage_source_ids: set[int] = set()
        stage_target_ids: set[int] = set()
        stage_land_to_land_count = 0
        stage_land_to_marine_count = 0
        stage_production_volume_km3 = 0.0
        stage_deposition_volume_km3 = 0.0
        stage_effective_diffusivity = 0.0
        edge_invalid = False
        for edge_index, (edge, expected_transfer) in enumerate(
            zip(edges, expected_transfers)
        ):
            if not isinstance(edge, dict) or not edge_required_keys.issubset(edge):
                edge_invalid = True
                break
            try:
                edge_id = int(edge["id"])
                cell_a_id = int(edge["mesh_edge_cell_a_id"])
                cell_b_id = int(edge["mesh_edge_cell_b_id"])
                source_cell_id = int(edge["source_cell_id"])
                target_cell_id = int(edge["target_cell_id"])
                source_neighbor_count = int(edge["source_neighbor_count"])
                numeric_values = {
                    key: float(edge[key])
                    for key in (
                        "source_area_km2",
                        "target_area_km2",
                        "source_elevation_m",
                        "target_elevation_m",
                        "elevation_drop_m",
                        "source_lithology_resistance",
                        "effective_diffusivity",
                        "source_production_depth_m",
                        "target_deposition_depth_m",
                        "transfer_volume_km3",
                        "mass_balance_residual_km3",
                    )
                }
            except (TypeError, ValueError, OverflowError):
                edge_invalid = True
                break
            source_input = input_by_id.get(source_cell_id)
            target_input = input_by_id.get(target_cell_id)
            source_cell = cells_by_id.get(source_cell_id)
            target_cell = cells_by_id.get(target_cell_id)
            if source_input is None or target_input is None or source_cell is None or target_cell is None:
                edge_invalid = True
                break
            source_lithology = str(source_input["lithology"])
            resistance = HILLSLOPE_SEDIMENT_LITHOLOGY_RESISTANCE[
                source_lithology
            ]
            source_area_km2 = float(source_cell.get("area_km2", -1.0))
            target_area_km2 = float(target_cell.get("area_km2", -1.0))
            source_elevation_m = float(source_input["elevation_m"])
            target_elevation_m = float(target_input["elevation_m"])
            elevation_drop_m = source_elevation_m - target_elevation_m
            expected_effective_diffusivity = min(
                HILLSLOPE_SEDIMENT_MAX_EFFECTIVE_DIFFUSIVITY,
                max(0.0, configured_diffusivity)
                * maturation_timestep_scale
                / max(1.0e-12, resistance),
            )
            expected_source_depth_m = (
                expected_effective_diffusivity
                * elevation_drop_m
                / source_neighbor_count
                if source_neighbor_count > 0
                else math.nan
            )
            expected_transfer_volume_km3 = (
                expected_source_depth_m * source_area_km2 / 1000.0
            )
            expected_target_depth_m = (
                expected_transfer_volume_km3 * 1000.0 / target_area_km2
                if target_area_km2 > 0.0
                else math.nan
            )
            expected_deposition_volume_km3 = (
                expected_target_depth_m * target_area_km2 / 1000.0
            )
            expected_residual_km3 = abs(
                expected_transfer_volume_km3
                - expected_deposition_volume_km3
            )
            if (
                edge_id != edge_index
                or (cell_a_id, cell_b_id, source_cell_id, target_cell_id)
                != expected_transfer
                or cell_a_id >= cell_b_id
                or source_cell_id == target_cell_id
                or {source_cell_id, target_cell_id} != {cell_a_id, cell_b_id}
                or str(edge["source_lithology"]) != source_lithology
                or source_neighbor_count
                != len(source_cell.get("neighbors", []))
                or source_neighbor_count <= 0
                or edge.get("source_is_water") is not False
                or bool(source_input["is_water"])
                or type(edge["target_is_water"]) is not bool
                or type(edge["target_is_lake"]) is not bool
                or edge["target_is_water"] is not target_input["is_water"]
                or edge["target_is_lake"] is not target_input["is_lake"]
                or source_area_km2 <= 0.0
                or target_area_km2 <= 0.0
                or elevation_drop_m <= 1.0e-12
                or not all(math.isfinite(value) for value in numeric_values.values())
                or any(
                    value < 0.0
                    for value in (
                        numeric_values["elevation_drop_m"],
                        numeric_values["source_lithology_resistance"],
                        numeric_values["effective_diffusivity"],
                        numeric_values["source_production_depth_m"],
                        numeric_values["target_deposition_depth_m"],
                        numeric_values["transfer_volume_km3"],
                        numeric_values["mass_balance_residual_km3"],
                    )
                )
                or not scalar_close(numeric_values["source_area_km2"], source_area_km2)
                or not scalar_close(numeric_values["target_area_km2"], target_area_km2)
                or not scalar_close(
                    numeric_values["source_elevation_m"], source_elevation_m
                )
                or not scalar_close(
                    numeric_values["target_elevation_m"], target_elevation_m
                )
                or not scalar_close(numeric_values["elevation_drop_m"], elevation_drop_m)
                or not scalar_close(
                    numeric_values["source_lithology_resistance"], resistance
                )
                or not scalar_close(
                    numeric_values["effective_diffusivity"],
                    expected_effective_diffusivity,
                )
                or not scalar_close(
                    numeric_values["source_production_depth_m"],
                    expected_source_depth_m,
                )
                or not scalar_close(
                    numeric_values["target_deposition_depth_m"],
                    expected_target_depth_m,
                )
                or not volume_close(
                    numeric_values["transfer_volume_km3"],
                    expected_transfer_volume_km3,
                )
                or not volume_close(
                    numeric_values["mass_balance_residual_km3"],
                    expected_residual_km3,
                )
            ):
                edge_invalid = True
                break

            stage_source_ids.add(source_cell_id)
            stage_target_ids.add(target_cell_id)
            unique_source_ids.add(source_cell_id)
            unique_target_ids.add(target_cell_id)
            stage_land_to_marine_count += int(bool(target_input["is_water"]))
            stage_land_to_land_count += int(not bool(target_input["is_water"]))
            stage_production_volume_km3 += expected_transfer_volume_km3
            stage_deposition_volume_km3 += expected_deposition_volume_km3
            stage_effective_diffusivity += expected_effective_diffusivity
            stage_production_by_cell[source_cell_id] += expected_source_depth_m
            stage_deposition_by_cell[target_cell_id] += expected_target_depth_m
            expected["production"][source_cell_id] += expected_transfer_volume_km3
            expected["deposition"][target_cell_id] += expected_deposition_volume_km3
            expected["outgoing_edge_count"][source_cell_id] += 1.0
            expected["incoming_edge_count"][target_cell_id] += 1.0
        if edge_invalid:
            failures.append("hillslope sediment transport edge replay invalid")
            transport_valid = False
            break

        stage_counts = {
            "transport_edge_count": len(edges),
            "source_cell_count": len(stage_source_ids),
            "target_cell_count": len(stage_target_ids),
            "land_to_land_edge_count": stage_land_to_land_count,
            "land_to_marine_edge_count": stage_land_to_marine_count,
        }
        stage_residual_km3 = abs(
            stage_production_volume_km3 - stage_deposition_volume_km3
        )
        stage_max_source_depth_m = max(stage_production_by_cell.values(), default=0.0)
        stage_max_target_depth_m = max(stage_deposition_by_cell.values(), default=0.0)
        stage_mean_diffusivity = (
            stage_effective_diffusivity / len(edges) if edges else 0.0
        )
        stage_values = {
            "production_volume_km3": stage_production_volume_km3,
            "deposition_volume_km3": stage_deposition_volume_km3,
            "mass_balance_residual_km3": stage_residual_km3,
            "max_source_production_depth_m": stage_max_source_depth_m,
            "max_target_deposition_depth_m": stage_max_target_depth_m,
            "mean_effective_diffusivity": stage_mean_diffusivity,
        }
        if (
            emitted_counts != stage_counts
            or any(
                not (
                    scalar_close(emitted_values[key], target)
                    if key
                    in {
                        "max_source_production_depth_m",
                        "max_target_deposition_depth_m",
                        "mean_effective_diffusivity",
                    }
                    else volume_close(emitted_values[key], target)
                )
                for key, target in stage_values.items()
            )
            or stage_residual_km3
            > max(0.000001, stage_production_volume_km3 * 1.0e-10)
        ):
            failures.append("hillslope sediment transport stage aggregates invalid")
            transport_valid = False
            break

        for key, value in stage_counts.items():
            total_counts[key] += value
        total_production_volume_km3 += stage_production_volume_km3
        total_deposition_volume_km3 += stage_deposition_volume_km3
        total_mass_balance_residual_km3 += stage_residual_km3
        total_effective_diffusivity += stage_effective_diffusivity
        maximum_source_depth_m = max(
            maximum_source_depth_m, stage_max_source_depth_m
        )
        maximum_target_depth_m = max(
            maximum_target_depth_m, stage_max_target_depth_m
        )

        if (
            not isinstance(feedback_history, list)
            or feedback_stage_id >= len(feedback_history)
            or not isinstance(feedback_history[feedback_stage_id], dict)
        ):
            failures.append("hillslope sediment transport feedback link invalid")
            transport_valid = False
            break
        feedback = feedback_history[feedback_stage_id]
        feedback_count_map = {
            "hillslope_sediment_transport_edge_count": "transport_edge_count",
            "hillslope_sediment_source_cell_count": "source_cell_count",
            "hillslope_sediment_target_cell_count": "target_cell_count",
            "hillslope_sediment_land_to_land_edge_count": "land_to_land_edge_count",
            "hillslope_sediment_land_to_marine_edge_count": "land_to_marine_edge_count",
        }
        feedback_value_map = {
            "hillslope_sediment_production_volume_km3": "production_volume_km3",
            "hillslope_sediment_deposition_volume_km3": "deposition_volume_km3",
            "hillslope_sediment_mass_balance_residual_km3": "mass_balance_residual_km3",
            "max_hillslope_sediment_source_production_depth_m": "max_source_production_depth_m",
            "max_hillslope_sediment_target_deposition_depth_m": "max_target_deposition_depth_m",
            "mean_hillslope_effective_diffusivity": "mean_effective_diffusivity",
        }
        try:
            feedback_counts_match = all(
                int(feedback.get(feedback_key, -1)) == stage_counts[stage_key]
                for feedback_key, stage_key in feedback_count_map.items()
            )
            feedback_values_match = all(
                math.isfinite(float(feedback.get(feedback_key, math.nan)))
                and (
                    scalar_close(
                        float(feedback[feedback_key]), stage_values[stage_key]
                    )
                    if stage_key
                    in {
                        "max_source_production_depth_m",
                        "max_target_deposition_depth_m",
                        "mean_effective_diffusivity",
                    }
                    else volume_close(
                        float(feedback[feedback_key]), stage_values[stage_key]
                    )
                )
                for feedback_key, stage_key in feedback_value_map.items()
            )
        except (TypeError, ValueError, OverflowError):
            feedback_counts_match = False
            feedback_values_match = False
        if not feedback_counts_match or not feedback_values_match:
            failures.append("hillslope sediment transport feedback metrics invalid")
            transport_valid = False
            break

    total_edge_count = total_counts["transport_edge_count"]
    total_mean_diffusivity = (
        total_effective_diffusivity / total_edge_count
        if total_edge_count > 0
        else 0.0
    )
    model_targets: dict[str, float | int] = {
        "total_transport_edge_count": total_counts["transport_edge_count"],
        "total_source_cell_stage_count": total_counts["source_cell_count"],
        "total_target_cell_stage_count": total_counts["target_cell_count"],
        "total_land_to_land_edge_count": total_counts["land_to_land_edge_count"],
        "total_land_to_marine_edge_count": total_counts["land_to_marine_edge_count"],
        "total_production_volume_km3": total_production_volume_km3,
        "total_deposition_volume_km3": total_deposition_volume_km3,
        "total_mass_balance_residual_km3": total_mass_balance_residual_km3,
        "max_source_production_depth_m": maximum_source_depth_m,
        "max_target_deposition_depth_m": maximum_target_depth_m,
        "mean_effective_diffusivity": total_mean_diffusivity,
    }
    model_count_keys = {
        "total_transport_edge_count",
        "total_source_cell_stage_count",
        "total_target_cell_stage_count",
        "total_land_to_land_edge_count",
        "total_land_to_marine_edge_count",
    }
    if transport_valid:
        for key, target in model_targets.items():
            try:
                actual = float(model.get(key, math.nan))
            except (TypeError, ValueError, OverflowError):
                transport_valid = False
                break
            if (
                not math.isfinite(actual)
                or (
                    key in model_count_keys
                    and int(actual) != int(target)
                )
                or (
                    key not in model_count_keys
                    and not (
                        scalar_close(actual, float(target))
                        if key
                        in {
                            "max_source_production_depth_m",
                            "max_target_deposition_depth_m",
                            "mean_effective_diffusivity",
                        }
                        else volume_close(actual, float(target))
                    )
                )
            ):
                transport_valid = False
                break
    if not transport_valid and not failures:
        failures.append("hillslope sediment transport model aggregates invalid")

    summary_targets: dict[str, float | int] = {
        "hillslope_sediment_transport_stage_count": len(history),
        "hillslope_sediment_transport_edge_count": total_counts[
            "transport_edge_count"
        ],
        "hillslope_sediment_source_cell_stage_count": total_counts[
            "source_cell_count"
        ],
        "hillslope_sediment_target_cell_stage_count": total_counts[
            "target_cell_count"
        ],
        "hillslope_sediment_land_to_land_edge_count": total_counts[
            "land_to_land_edge_count"
        ],
        "hillslope_sediment_land_to_marine_edge_count": total_counts[
            "land_to_marine_edge_count"
        ],
        "hillslope_sediment_unique_source_cell_count": len(unique_source_ids),
        "hillslope_sediment_unique_target_cell_count": len(unique_target_ids),
        "hillslope_sediment_production_volume_km3": total_production_volume_km3,
        "hillslope_sediment_deposition_volume_km3": total_deposition_volume_km3,
        "hillslope_sediment_mass_balance_residual_km3": total_mass_balance_residual_km3,
        "max_hillslope_sediment_source_production_depth_m": maximum_source_depth_m,
        "max_hillslope_sediment_target_deposition_depth_m": maximum_target_depth_m,
        "mean_hillslope_sediment_effective_diffusivity": total_mean_diffusivity,
    }
    summary_count_keys = {
        key for key in summary_targets if key.endswith("_count")
    }
    if transport_valid:
        for key, target in summary_targets.items():
            try:
                actual = float(summary.get(key, math.nan))
            except (TypeError, ValueError, OverflowError):
                transport_valid = False
                break
            if (
                not math.isfinite(actual)
                or (key in summary_count_keys and int(actual) != int(target))
                or (
                    key not in summary_count_keys
                    and not (
                        scalar_close(actual, float(target))
                        if key.startswith("max_") or key.startswith("mean_")
                        else volume_close(actual, float(target))
                    )
                )
            ):
                transport_valid = False
                break
    if not transport_valid and not any(
        "hillslope sediment transport" in failure for failure in failures
    ):
        failures.append("hillslope sediment transport summary metrics invalid")

    if transport_valid:
        for cell_id, cell in cells_by_id.items():
            try:
                area_km2 = float(cell.get("area_km2", 0.0))
                actual_production_m = float(
                    cell.get("hillslope_sediment_production_m", math.nan)
                )
                actual_deposition_m = float(
                    cell.get("hillslope_sediment_deposition_m", math.nan)
                )
                actual_net_m = float(
                    cell.get("hillslope_sediment_net_m", math.nan)
                )
                actual_outgoing_count = int(
                    cell.get("hillslope_sediment_outgoing_edge_count", -1)
                )
                actual_incoming_count = int(
                    cell.get("hillslope_sediment_incoming_edge_count", -1)
                )
            except (TypeError, ValueError, OverflowError):
                transport_valid = False
                break
            expected_production_m = (
                expected["production"][cell_id] * 1000.0 / area_km2
                if area_km2 > 0.0
                else math.nan
            )
            expected_deposition_m = (
                expected["deposition"][cell_id] * 1000.0 / area_km2
                if area_km2 > 0.0
                else math.nan
            )
            expected_net_m = expected_deposition_m - expected_production_m
            if (
                area_km2 <= 0.0
                or not all(
                    math.isfinite(value)
                    for value in (
                        actual_production_m,
                        actual_deposition_m,
                        actual_net_m,
                    )
                )
                or any(
                    not scalar_close(actual, target)
                    for actual, target in (
                        (actual_production_m, expected_production_m),
                        (actual_deposition_m, expected_deposition_m),
                        (actual_net_m, expected_net_m),
                    )
                )
                or actual_outgoing_count
                != int(expected["outgoing_edge_count"][cell_id])
                or actual_incoming_count
                != int(expected["incoming_edge_count"][cell_id])
            ):
                transport_valid = False
                break
    if not transport_valid and not any(
        "hillslope sediment transport" in failure for failure in failures
    ):
        failures.append("hillslope sediment transport cumulative cell fields invalid")
    return failures, expected, transport_valid


def _validate_glacial_sediment_transport(
    payload: dict[str, Any],
    summary: dict[str, Any],
    cells_by_id: dict[int, dict[str, Any]],
) -> tuple[list[str], dict[str, dict[int, float]], bool]:
    failures: list[str] = []
    cell_ids = set(cells_by_id)
    expected = {
        "production": {cell_id: 0.0 for cell_id in cell_ids},
        "deposition": {cell_id: 0.0 for cell_id in cell_ids},
        "outgoing_transfer_count": {cell_id: 0.0 for cell_id in cell_ids},
        "incoming_transfer_count": {cell_id: 0.0 for cell_id in cell_ids},
    }
    try:
        grounded_current = grounded_ice_version(payload) == 1
    except (ValueError, TypeError, OverflowError) as error:
        return [str(error)], expected, False
    model = payload.get("glacial_sediment_transport_model", {})
    history = payload.get("glacial_sediment_transport_history", [])
    model_keys = {
        "model_type",
        "routing_graph",
        "source_state",
        "erosion_potential_model",
        "mobile_sediment_fraction",
        "source_depth_model",
        "source_material_partition_model",
        "stage_input_snapshot",
        "volume_transfer_model",
        "mass_conserving",
        "finite_sediment_inventory_resolved",
        "terrain_elevation_coupled",
        "earth_system_recomputed_after_transport",
        "physical_time_resolved",
        "multi_step_ice_dynamics_resolved",
        "model_limitation",
        "stage_count",
        "total_transfer_count",
        "total_source_cell_count",
        "total_target_cell_count",
        "total_land_target_transfer_count",
        "total_marine_target_transfer_count",
        "total_production_volume_km3",
        "total_deposition_volume_km3",
        "total_alluvium_entrainment_volume_km3",
        "total_bedrock_erosion_volume_km3",
        "total_mass_balance_residual_km3",
        "total_terrain_volume_change_residual_km3",
        "max_source_production_depth_m",
        "max_target_deposition_depth_m",
    }
    if (
        not isinstance(model, dict)
        or not model_keys.issubset(model)
        or not isinstance(history, list)
    ):
        return ["glacial sediment transport model or history missing"], expected, False

    def volume_close(actual: float, target: float) -> bool:
        return abs(actual - target) <= max(0.001, abs(target) * 2.0e-9)

    def scalar_close(actual: float, target: float) -> bool:
        return abs(actual - target) <= max(0.0000002, abs(target) * 2.0e-8)

    try:
        mobile_fraction = float(model["mobile_sediment_fraction"])
        model_stage_count = int(model["stage_count"])
        radius_km = float(
            payload.get("planet_parameters", {}).get("radius_km", math.nan)
        )
    except (TypeError, ValueError, OverflowError):
        return ["glacial sediment transport metadata values invalid"], expected, False
    transport_valid = True
    if (
        model.get("model_type") != (GROUNDED_GLACIAL_MODEL if grounded_current else GLACIAL_SEDIMENT_TRANSPORT_MODEL)
        or model.get("routing_graph")
        != "single_steepest_downhill_mesh_neighbor_v1"
        or model.get("source_state")
        != "post_erosion_pre_cryosphere_feedback_cell_state_v1"
        or model.get("erosion_potential_model")
        != "ice_thickness_times_local_slope_proxy_bounded_85m_v1"
        or model.get("source_depth_model")
        != "glacial_erosion_potential_times_mobile_sediment_fraction"
        or model.get("source_material_partition_model")
        != "available_alluvium_first_then_bedrock_erosion_v1"
        or model.get("stage_input_snapshot")
        != ("complete_cell_cryosphere_terrain_and_sediment_inventory_before_transport_v3" if grounded_current else "complete_cell_cryosphere_terrain_and_sediment_inventory_before_transport_v2")
        or (grounded_current and model.get("source_grounded_ice_model") != GROUNDED_ICE_MODEL["model_type"])
        or model.get("volume_transfer_model")
        != "source_depth_times_source_area_equals_target_depth_times_target_area"
        or model.get("mass_conserving") is not True
        or model.get("finite_sediment_inventory_resolved") is not True
        or model.get("terrain_elevation_coupled") is not True
        or model.get("earth_system_recomputed_after_transport") is not True
        or model.get("physical_time_resolved") is not False
        or model.get("multi_step_ice_dynamics_resolved") is not False
        or model.get("model_limitation")
        != "single_post_erosion_bulk_transfer_without_calibrated_time_multistep_ice_dynamics_or_grain_classes"
        or not math.isfinite(mobile_fraction)
        or not scalar_close(mobile_fraction, GLACIAL_SEDIMENT_MOBILE_FRACTION)
        or not math.isfinite(radius_km)
        or radius_km <= 0.0
        or len(history) != 1
        or model_stage_count != len(history)
    ):
        failures.append("glacial sediment transport metadata invalid")
        transport_valid = False

    stage_required_keys = {
        "id",
        "feedback_stage_id",
        "transfer_count",
        "source_cell_count",
        "target_cell_count",
        "land_target_transfer_count",
        "marine_target_transfer_count",
        "production_volume_km3",
        "deposition_volume_km3",
        "alluvium_entrainment_volume_km3",
        "bedrock_erosion_volume_km3",
        "mass_balance_residual_km3",
        "terrain_volume_change_residual_km3",
        "max_source_production_depth_m",
        "max_target_deposition_depth_m",
        "input_cell_count",
        "input_cells",
        "transfers",
        "post_transport_elevation_m_by_cell",
    }
    input_required_keys = {
        "cell_id",
        "glacier_flow_to_cell_id",
        "is_water",
        "elevation_m",
        "ice_thickness_m",
        "glacial_erosion_m",
        "sediment_thickness_m",
    }
    if grounded_current:
        input_required_keys.add("is_lake")
    transfer_required_keys = {
        "id",
        "source_cell_id",
        "target_cell_id",
        "target_is_water",
        "source_area_km2",
        "target_area_km2",
        "source_elevation_m",
        "target_elevation_m",
        "elevation_drop_m",
        "source_ice_thickness_m",
        "source_glacial_erosion_m",
        "source_production_depth_m",
        "target_deposition_depth_m",
        "transfer_volume_km3",
        "mass_balance_residual_km3",
    }
    if not history or not isinstance(history[0], dict) or not stage_required_keys.issubset(history[0]):
        failures.append("glacial sediment transport stage missing fields")
        return failures, expected, False
    stage = history[0]
    if grounded_current:
        try:
            require_grounded_stage_inputs(stage)
        except (ValueError, TypeError, OverflowError) as error:
            return [str(error)], expected, False
    input_cells = stage.get("input_cells", [])
    transfers = stage.get("transfers", [])
    post_elevations = stage.get("post_transport_elevation_m_by_cell", [])
    try:
        stage_id = int(stage["id"])
        feedback_stage_id = int(stage["feedback_stage_id"])
        input_cell_count = int(stage["input_cell_count"])
        emitted_counts = {
            key: int(stage[key])
            for key in (
                "transfer_count",
                "source_cell_count",
                "target_cell_count",
                "land_target_transfer_count",
                "marine_target_transfer_count",
            )
        }
        emitted_values = {
            key: float(stage[key])
            for key in (
                "production_volume_km3",
                "deposition_volume_km3",
                "mass_balance_residual_km3",
                "terrain_volume_change_residual_km3",
                "max_source_production_depth_m",
                "max_target_deposition_depth_m",
            )
        }
        configured_erosion_iterations = int(
            payload.get("simulation_clock", {}).get(
                "configured_erosion_iteration_count", -1
            )
        )
        nominal_timestep_ma = float(
            payload.get("simulation_clock", {}).get("nominal_timestep_ma", math.nan)
        )
    except (TypeError, ValueError, OverflowError):
        failures.append("glacial sediment transport stage values invalid")
        return failures, expected, False
    if (
        not isinstance(input_cells, list)
        or not isinstance(transfers, list)
        or not isinstance(post_elevations, list)
        or stage_id != 0
        or feedback_stage_id != configured_erosion_iterations + 1
        or configured_erosion_iterations < 0
        or not math.isfinite(nominal_timestep_ma)
        or not 0.0 < nominal_timestep_ma <= MATURATION_REFERENCE_TIMESTEP_MA
        or not _nominal_time_record_valid(
            stage,
            expected_start_ma=configured_erosion_iterations
            * nominal_timestep_ma,
            expected_end_ma=configured_erosion_iterations * nominal_timestep_ma,
            expected_role="final_cryosphere_coupling_bulk_transport",
        )
        or input_cell_count != len(input_cells)
        or input_cell_count != len(cell_ids)
        or len(post_elevations) != len(cell_ids)
        or any(value < 0 for value in emitted_counts.values())
        or not all(math.isfinite(value) for value in emitted_values.values())
        or any(value < 0.0 for value in emitted_values.values())
    ):
        failures.append("glacial sediment transport stage sequence invalid")
        return failures, expected, False

    input_by_id: dict[int, dict[str, Any]] = {}
    for input_index, input_cell in enumerate(input_cells):
        if not isinstance(input_cell, dict) or not input_required_keys.issubset(input_cell):
            failures.append("glacial sediment transport input snapshot invalid")
            return failures, expected, False
        try:
            cell_id = int(input_cell["cell_id"])
            flow_to = int(input_cell["glacier_flow_to_cell_id"])
            elevation_m = float(input_cell["elevation_m"])
            ice_thickness_m = float(input_cell["ice_thickness_m"])
            glacial_erosion_m = float(input_cell["glacial_erosion_m"])
            sediment_thickness_m = float(input_cell["sediment_thickness_m"])
        except (TypeError, ValueError, OverflowError):
            failures.append("glacial sediment transport input snapshot invalid")
            return failures, expected, False
        if (
            cell_id != input_index
            or cell_id not in cell_ids
            or cell_id in input_by_id
            or type(input_cell["is_water"]) is not bool
            or (grounded_current and type(input_cell["is_lake"]) is not bool)
            or (grounded_current and input_cell["is_water"] and input_cell["is_lake"])
            or not all(
                math.isfinite(value)
                for value in (
                    elevation_m,
                    ice_thickness_m,
                    glacial_erosion_m,
                    sediment_thickness_m,
                )
            )
            or ice_thickness_m < 0.0
            or glacial_erosion_m < 0.0
            or sediment_thickness_m < 0.0
            or flow_to < -1
            or (flow_to >= 0 and flow_to not in cell_ids)
        ):
            failures.append("glacial sediment transport input snapshot invalid")
            return failures, expected, False
        input_by_id[cell_id] = input_cell

    expected_transfers: list[tuple[int, int]] = []
    for cell_id in sorted(cell_ids):
        input_cell = input_by_id[cell_id]
        cell = cells_by_id[cell_id]
        neighbors = cell.get("neighbors", [])
        position = cell.get("position_3d", [])
        if (
            not isinstance(neighbors, list)
            or not isinstance(position, list)
            or len(position) != 3
        ):
            failures.append("glacial sediment transport topology invalid")
            return failures, expected, False
        try:
            neighbor_ids = [int(neighbor_id) for neighbor_id in neighbors]
            source_position = [float(value) for value in position]
            source_elevation_m = float(input_cell["elevation_m"])
            ice_thickness_m = float(input_cell["ice_thickness_m"])
            emitted_flow_to = int(input_cell["glacier_flow_to_cell_id"])
            emitted_erosion_m = float(input_cell["glacial_erosion_m"])
        except (TypeError, ValueError, OverflowError):
            failures.append("glacial sediment transport topology invalid")
            return failures, expected, False
        best_drop_m = 0.0
        expected_flow_to = -1
        for neighbor_id in neighbor_ids:
            if neighbor_id not in cell_ids or cell_id not in cells_by_id[neighbor_id].get("neighbors", []):
                failures.append("glacial sediment transport topology invalid")
                return failures, expected, False
            drop_m = source_elevation_m - float(input_by_id[neighbor_id]["elevation_m"])
            if drop_m > best_drop_m:
                best_drop_m = drop_m
                expected_flow_to = neighbor_id
        expected_erosion_m = 0.0
        if (
            not (bool(input_cell["is_water"]) or (grounded_current and input_cell["is_lake"]))
            and ice_thickness_m > 0.0
            and expected_flow_to >= 0
        ):
            target_position_raw = cells_by_id[expected_flow_to].get("position_3d", [])
            if not isinstance(target_position_raw, list) or len(target_position_raw) != 3:
                failures.append("glacial sediment transport topology invalid")
                return failures, expected, False
            target_position = [float(value) for value in target_position_raw]
            dot = min(
                1.0,
                max(
                    -1.0,
                    sum(
                        source_position[index] * target_position[index]
                        for index in range(3)
                    ),
                ),
            )
            distance_m = max(1.0, math.acos(dot) * radius_km * 1000.0)
            slope = best_drop_m / distance_m
            expected_erosion_m = min(
                85.0,
                max(
                    0.0,
                    (ice_thickness_m / 1000.0)
                    * max(0.0, slope * 900.0)
                    * 12.0,
                ),
            )
        if (
            (bool(input_cell["is_water"]) or (grounded_current and input_cell["is_lake"]))
            and (
                ice_thickness_m > 0.0000002
                or emitted_flow_to != -1
                or emitted_erosion_m > 0.0000002
            )
        ) or (
            not (bool(input_cell["is_water"]) or (grounded_current and input_cell["is_lake"]))
            and ice_thickness_m <= 0.0
            and (emitted_flow_to != -1 or emitted_erosion_m > 0.0000002)
        ) or (
            not (bool(input_cell["is_water"]) or (grounded_current and input_cell["is_lake"]))
            and ice_thickness_m > 0.0
            and (
                emitted_flow_to != expected_flow_to
                or not scalar_close(emitted_erosion_m, expected_erosion_m)
            )
        ):
            failures.append("glacial sediment transport source-state replay invalid")
            return failures, expected, False
        if expected_flow_to >= 0 and expected_erosion_m > 0.0:
            expected_transfers.append((cell_id, expected_flow_to))

    if len(transfers) != len(expected_transfers):
        failures.append("glacial sediment transport transfer coverage invalid")
        return failures, expected, False

    production_depth_by_cell = {cell_id: 0.0 for cell_id in cell_ids}
    deposition_depth_by_cell = {cell_id: 0.0 for cell_id in cell_ids}
    target_ids: set[int] = set()
    land_target_count = 0
    marine_target_count = 0
    production_volume_km3 = 0.0
    deposition_volume_km3 = 0.0
    max_source_depth_m = 0.0
    for transfer_index, (transfer, expected_pair) in enumerate(
        zip(transfers, expected_transfers)
    ):
        if not isinstance(transfer, dict) or not transfer_required_keys.issubset(transfer):
            failures.append("glacial sediment transport transfer replay invalid")
            return failures, expected, False
        try:
            transfer_id = int(transfer["id"])
            source_cell_id = int(transfer["source_cell_id"])
            target_cell_id = int(transfer["target_cell_id"])
            values = {
                key: float(transfer[key])
                for key in (
                    "source_area_km2",
                    "target_area_km2",
                    "source_elevation_m",
                    "target_elevation_m",
                    "elevation_drop_m",
                    "source_ice_thickness_m",
                    "source_glacial_erosion_m",
                    "source_production_depth_m",
                    "target_deposition_depth_m",
                    "transfer_volume_km3",
                    "mass_balance_residual_km3",
                )
            }
        except (TypeError, ValueError, OverflowError):
            failures.append("glacial sediment transport transfer replay invalid")
            return failures, expected, False
        source_input = input_by_id[source_cell_id]
        target_input = input_by_id[target_cell_id]
        source_area_km2 = float(cells_by_id[source_cell_id].get("area_km2", -1.0))
        target_area_km2 = float(cells_by_id[target_cell_id].get("area_km2", -1.0))
        source_elevation_m = float(source_input["elevation_m"])
        target_elevation_m = float(target_input["elevation_m"])
        elevation_drop_m = source_elevation_m - target_elevation_m
        source_ice_thickness_m = float(source_input["ice_thickness_m"])
        source_glacial_erosion_m = float(source_input["glacial_erosion_m"])
        source_depth_m = source_glacial_erosion_m * mobile_fraction
        transfer_volume_km3 = source_depth_m * source_area_km2 / 1000.0
        target_depth_m = transfer_volume_km3 * 1000.0 / target_area_km2
        deposited_volume_km3 = target_depth_m * target_area_km2 / 1000.0
        residual_km3 = abs(transfer_volume_km3 - deposited_volume_km3)
        if (
            transfer_id != transfer_index
            or (source_cell_id, target_cell_id) != expected_pair
            or type(transfer["target_is_water"]) is not bool
            or transfer["target_is_water"] is not target_input["is_water"]
            or source_area_km2 <= 0.0
            or target_area_km2 <= 0.0
            or elevation_drop_m <= 0.0
            or source_ice_thickness_m <= 0.0
            or source_glacial_erosion_m <= 0.0
            or not all(math.isfinite(value) for value in values.values())
            or not scalar_close(values["source_area_km2"], source_area_km2)
            or not scalar_close(values["target_area_km2"], target_area_km2)
            or not scalar_close(values["source_elevation_m"], source_elevation_m)
            or not scalar_close(values["target_elevation_m"], target_elevation_m)
            or not scalar_close(values["elevation_drop_m"], elevation_drop_m)
            or not scalar_close(values["source_ice_thickness_m"], source_ice_thickness_m)
            or not scalar_close(values["source_glacial_erosion_m"], source_glacial_erosion_m)
            or not scalar_close(values["source_production_depth_m"], source_depth_m)
            or not scalar_close(values["target_deposition_depth_m"], target_depth_m)
            or not volume_close(values["transfer_volume_km3"], transfer_volume_km3)
            or not volume_close(values["mass_balance_residual_km3"], residual_km3)
        ):
            failures.append("glacial sediment transport transfer replay invalid")
            return failures, expected, False
        target_ids.add(target_cell_id)
        land_target_count += int(not bool(target_input["is_water"]))
        marine_target_count += int(bool(target_input["is_water"]))
        production_depth_by_cell[source_cell_id] += source_depth_m
        deposition_depth_by_cell[target_cell_id] += target_depth_m
        production_volume_km3 += transfer_volume_km3
        deposition_volume_km3 += deposited_volume_km3
        max_source_depth_m = max(max_source_depth_m, source_depth_m)
        expected["production"][source_cell_id] += transfer_volume_km3
        expected["deposition"][target_cell_id] += deposited_volume_km3
        expected["outgoing_transfer_count"][source_cell_id] += 1.0
        expected["incoming_transfer_count"][target_cell_id] += 1.0

    max_target_depth_m = max(deposition_depth_by_cell.values(), default=0.0)
    residual_km3 = abs(production_volume_km3 - deposition_volume_km3)
    stage_counts = {
        "transfer_count": len(transfers),
        "source_cell_count": len(transfers),
        "target_cell_count": len(target_ids),
        "land_target_transfer_count": land_target_count,
        "marine_target_transfer_count": marine_target_count,
    }
    stage_values = {
        "production_volume_km3": production_volume_km3,
        "deposition_volume_km3": deposition_volume_km3,
        "mass_balance_residual_km3": residual_km3,
        "terrain_volume_change_residual_km3": residual_km3,
        "max_source_production_depth_m": max_source_depth_m,
        "max_target_deposition_depth_m": max_target_depth_m,
    }
    if emitted_counts != stage_counts or any(
        not (
            scalar_close(emitted_values[key], target)
            if key.startswith("max_")
            else volume_close(emitted_values[key], target)
        )
        for key, target in stage_values.items()
    ):
        failures.append("glacial sediment transport stage aggregates invalid")
        return failures, expected, False

    for cell_id in sorted(cell_ids):
        try:
            actual_post_elevation_m = float(post_elevations[cell_id])
        except (TypeError, ValueError, OverflowError, IndexError):
            failures.append("glacial sediment terrain coupling snapshot invalid")
            return failures, expected, False
        expected_post_elevation_m = (
            float(input_by_id[cell_id]["elevation_m"])
            - production_depth_by_cell[cell_id]
            + deposition_depth_by_cell[cell_id]
        )
        if (
            not math.isfinite(actual_post_elevation_m)
            or not scalar_close(actual_post_elevation_m, expected_post_elevation_m)
        ):
            failures.append("glacial sediment terrain coupling snapshot invalid")
            return failures, expected, False

    model_targets: dict[str, float | int] = {
        "total_transfer_count": stage_counts["transfer_count"],
        "total_source_cell_count": stage_counts["source_cell_count"],
        "total_target_cell_count": stage_counts["target_cell_count"],
        "total_land_target_transfer_count": stage_counts[
            "land_target_transfer_count"
        ],
        "total_marine_target_transfer_count": stage_counts[
            "marine_target_transfer_count"
        ],
        "total_production_volume_km3": production_volume_km3,
        "total_deposition_volume_km3": deposition_volume_km3,
        "total_mass_balance_residual_km3": residual_km3,
        "total_terrain_volume_change_residual_km3": residual_km3,
        "max_source_production_depth_m": max_source_depth_m,
        "max_target_deposition_depth_m": max_target_depth_m,
    }
    model_count_keys = {key for key in model_targets if key.endswith("_count")}
    for key, target in model_targets.items():
        try:
            actual = float(model.get(key, math.nan))
        except (TypeError, ValueError, OverflowError):
            transport_valid = False
            break
        if (
            not math.isfinite(actual)
            or (key in model_count_keys and int(actual) != int(target))
            or (
                key not in model_count_keys
                and not (
                    scalar_close(actual, float(target))
                    if key.startswith("max_")
                    else volume_close(actual, float(target))
                )
            )
        ):
            transport_valid = False
            break
    if not transport_valid:
        failures.append("glacial sediment transport model aggregates invalid")
        return failures, expected, False

    feedback_history = payload.get("earth_system_feedback_history", [])
    if (
        not isinstance(feedback_history, list)
        or feedback_stage_id >= len(feedback_history)
        or not isinstance(feedback_history[feedback_stage_id], dict)
    ):
        failures.append("glacial sediment transport feedback link invalid")
        return failures, expected, False
    feedback = feedback_history[feedback_stage_id]
    feedback_count_map = {
        "glacial_sediment_transfer_count": "transfer_count",
        "glacial_sediment_source_cell_count": "source_cell_count",
        "glacial_sediment_target_cell_count": "target_cell_count",
        "glacial_sediment_land_target_transfer_count": "land_target_transfer_count",
        "glacial_sediment_marine_target_transfer_count": "marine_target_transfer_count",
    }
    feedback_value_map = {
        "glacial_sediment_production_volume_km3": "production_volume_km3",
        "glacial_sediment_deposition_volume_km3": "deposition_volume_km3",
        "glacial_sediment_mass_balance_residual_km3": "mass_balance_residual_km3",
        "glacial_sediment_terrain_volume_change_residual_km3": "terrain_volume_change_residual_km3",
        "max_glacial_sediment_source_production_depth_m": "max_source_production_depth_m",
        "max_glacial_sediment_target_deposition_depth_m": "max_target_deposition_depth_m",
    }
    try:
        feedback_valid = (
            feedback.get("stage") == "cryosphere_coupling"
            and feedback.get("cryosphere_applied") is True
            and feedback.get("erosion_applied") is False
            and all(
                int(feedback.get(feedback_key, -1)) == stage_counts[stage_key]
                for feedback_key, stage_key in feedback_count_map.items()
            )
            and all(
                (
                    scalar_close(float(feedback[feedback_key]), stage_values[stage_key])
                    if stage_key.startswith("max_")
                    else volume_close(float(feedback[feedback_key]), stage_values[stage_key])
                )
                for feedback_key, stage_key in feedback_value_map.items()
            )
        )
    except (KeyError, TypeError, ValueError, OverflowError):
        feedback_valid = False
    if not feedback_valid:
        failures.append("glacial sediment transport feedback metrics invalid")
        return failures, expected, False

    summary_targets: dict[str, float | int] = {
        "glacial_sediment_transport_stage_count": 1,
        "glacial_sediment_transfer_count": stage_counts["transfer_count"],
        "glacial_sediment_source_cell_count": stage_counts["source_cell_count"],
        "glacial_sediment_target_cell_count": stage_counts["target_cell_count"],
        "glacial_sediment_land_target_transfer_count": stage_counts[
            "land_target_transfer_count"
        ],
        "glacial_sediment_marine_target_transfer_count": stage_counts[
            "marine_target_transfer_count"
        ],
        "glacial_sediment_production_volume_km3": production_volume_km3,
        "glacial_sediment_deposition_volume_km3": deposition_volume_km3,
        "glacial_sediment_mass_balance_residual_km3": residual_km3,
        "glacial_sediment_terrain_volume_change_residual_km3": residual_km3,
        "max_glacial_sediment_source_production_depth_m": max_source_depth_m,
        "max_glacial_sediment_target_deposition_depth_m": max_target_depth_m,
    }
    summary_count_keys = {key for key in summary_targets if key.endswith("_count")}
    for key, target in summary_targets.items():
        try:
            actual = float(summary.get(key, math.nan))
        except (TypeError, ValueError, OverflowError):
            transport_valid = False
            break
        if (
            not math.isfinite(actual)
            or (key in summary_count_keys and int(actual) != int(target))
            or (
                key not in summary_count_keys
                and not (
                    scalar_close(actual, float(target))
                    if key.startswith("max_")
                    else volume_close(actual, float(target))
                )
            )
        ):
            transport_valid = False
            break
    if not transport_valid:
        failures.append("glacial sediment transport summary metrics invalid")
        return failures, expected, False

    for cell_id, cell in cells_by_id.items():
        try:
            area_km2 = float(cell.get("area_km2", 0.0))
            actual_production_m = float(
                cell.get("glacial_sediment_production_m", math.nan)
            )
            actual_deposition_m = float(
                cell.get("glacial_sediment_deposition_m", math.nan)
            )
            actual_net_m = float(cell.get("glacial_sediment_net_m", math.nan))
            outgoing_count = int(
                cell.get("glacial_sediment_outgoing_transfer_count", -1)
            )
            incoming_count = int(
                cell.get("glacial_sediment_incoming_transfer_count", -1)
            )
        except (TypeError, ValueError, OverflowError):
            transport_valid = False
            break
        expected_production_m = (
            expected["production"][cell_id] * 1000.0 / area_km2
            if area_km2 > 0.0
            else math.nan
        )
        expected_deposition_m = (
            expected["deposition"][cell_id] * 1000.0 / area_km2
            if area_km2 > 0.0
            else math.nan
        )
        if (
            area_km2 <= 0.0
            or not scalar_close(actual_production_m, expected_production_m)
            or not scalar_close(actual_deposition_m, expected_deposition_m)
            or not scalar_close(
                actual_net_m, expected_deposition_m - expected_production_m
            )
            or outgoing_count
            != int(expected["outgoing_transfer_count"][cell_id])
            or incoming_count
            != int(expected["incoming_transfer_count"][cell_id])
        ):
            transport_valid = False
            break
    if not transport_valid:
        failures.append("glacial sediment transport cumulative cell fields invalid")
    return failures, expected, transport_valid


def _validate_sediment_inventory(
    payload: dict[str, Any],
    summary: dict[str, Any],
    cells_by_id: dict[int, dict[str, Any]],
) -> tuple[list[str], bool]:
    """Replay the finite mobile-sediment inventory in native stage order."""

    model = payload.get("sediment_inventory_model", {})
    feedback_history = payload.get("earth_system_feedback_history", [])
    numeric_history = payload.get("numeric_depression_correction_history", [])
    hillslope_history = payload.get("hillslope_sediment_transport_history", [])
    fluvial_history = payload.get("fluvial_sediment_routing_history", [])
    glacial_history = payload.get("glacial_sediment_transport_history", [])
    model_keys = {
        "model_type",
        "initial_mobile_sediment_inventory",
        "source_partition_model",
        "erosion_stage_source_partition_order",
        "same_stage_deposition_available_for_entrainment",
        "erosion_source_depths_timestep_scaled_upstream",
        "time_step_convergence_demonstrated",
        "mass_conserving",
        "mass_conserving_semantics",
        "dry_rock_mass_resolved",
        "sediment_density_resolved",
        "porosity_resolved",
        "compaction_resolved",
        "grain_provenance_resolved",
        "chemical_weathering_resolved",
        "physical_time_resolved",
        "model_limitation",
        "stage_count",
        "gross_mobilization_volume_km3",
        "deposition_volume_km3",
        "terminal_export_volume_km3",
        "alluvium_entrainment_volume_km3",
        "bedrock_erosion_volume_km3",
        "final_mobile_sediment_inventory_volume_km3",
        "gross_throughput_mass_balance_residual_km3",
        "source_partition_residual_km3",
        "inventory_mass_balance_residual_km3",
        "cell_alluvium_entrainment_volume_km3",
        "cell_bedrock_erosion_volume_km3",
        "cell_source_partition_residual_km3",
        "process_source_partition",
    }
    histories = (
        feedback_history,
        numeric_history,
        hillslope_history,
        fluvial_history,
        glacial_history,
    )
    if (
        not isinstance(model, dict)
        or not model_keys.issubset(model)
        or any(not isinstance(history, list) for history in histories)
        or not cells_by_id
    ):
        return ["sediment inventory model or provenance missing"], False
    if (
        model.get("model_type") != SEDIMENT_INVENTORY_MODEL
        or model.get("initial_mobile_sediment_inventory")
        != "zero_depth_all_cells_v1"
        or model.get("source_partition_model")
        != "available_alluvium_first_then_bedrock_erosion_v1"
        or model.get("erosion_stage_source_partition_order")
        != "hillslope_then_fluvial"
        or model.get("same_stage_deposition_available_for_entrainment")
        is not False
        or model.get("erosion_source_depths_timestep_scaled_upstream") is not True
        or model.get("time_step_convergence_demonstrated") is not False
        or model.get("mass_conserving") is not True
        or model.get("mass_conserving_semantics")
        != "bulk_reference_volume_only_not_dry_rock_mass"
        or model.get("dry_rock_mass_resolved") is not False
        or model.get("sediment_density_resolved") is not False
        or model.get("porosity_resolved") is not False
        or model.get("compaction_resolved") is not False
        or model.get("grain_provenance_resolved") is not False
        or model.get("chemical_weathering_resolved") is not False
        or model.get("physical_time_resolved") is not False
        or model.get("model_limitation")
        != "bulk_inventory_without_grain_classes_calibrated_time_shared_boundary_flux_or_subcell_channels"
    ):
        return ["sediment inventory metadata invalid"], False

    cell_ids = sorted(cells_by_id)
    cell_id_set = set(cell_ids)
    try:
        areas = {
            cell_id: float(cells_by_id[cell_id]["area_km2"])
            for cell_id in cell_ids
        }
        output_precision = int(summary.get("output_float_precision", 8))
        configured_erosion_iterations = int(
            payload.get("simulation_clock", {}).get(
                "configured_erosion_iteration_count", -1
            )
        )
        model_stage_count = int(model["stage_count"])
    except (KeyError, TypeError, ValueError, OverflowError):
        return ["sediment inventory metadata values invalid"], False
    if (
        any(not math.isfinite(area) or area <= 0.0 for area in areas.values())
        or configured_erosion_iterations < 0
        or len(feedback_history) != configured_erosion_iterations + 2
        or model_stage_count != len(feedback_history)
    ):
        return ["sediment inventory stage metadata invalid"], False

    total_area_km2 = sum(areas.values())
    emitted_depth_quantum_m = (
        10.0 ** (-output_precision) if 0 <= output_precision <= 8 else 1.0e-8
    )
    depth_tolerance_m = 0.000002
    final_depth_tolerance_m = max(
        0.000002, emitted_depth_quantum_m * 0.55
    )
    quantized_volume_tolerance_km3 = (
        total_area_km2 * 5.0e-8 / 1000.0
    )

    def depth_close(actual: float, expected: float, *, final: bool = False) -> bool:
        tolerance = final_depth_tolerance_m if final else depth_tolerance_m
        return math.isfinite(actual) and abs(actual - expected) <= max(
            tolerance, abs(expected) * 2.0e-8
        )

    def volume_close(
        actual: float, expected: float, *, cumulative: bool = False
    ) -> bool:
        base = max(
            0.01,
            quantized_volume_tolerance_km3
            * (len(feedback_history) if cumulative else 2.0),
        )
        return math.isfinite(actual) and abs(actual - expected) <= max(
            base, abs(expected) * 2.0e-9
        )

    def history_by_feedback_id(
        history: list[Any], label: str
    ) -> tuple[dict[int, dict[str, Any]], str | None]:
        indexed: dict[int, dict[str, Any]] = {}
        for item in history:
            if not isinstance(item, dict):
                return {}, f"{label} stage is not an object"
            try:
                feedback_id = int(item["feedback_stage_id"])
            except (KeyError, TypeError, ValueError, OverflowError):
                return {}, f"{label} feedback link invalid"
            if feedback_id in indexed:
                return {}, f"{label} feedback link duplicated"
            indexed[feedback_id] = item
        return indexed, None

    hillslope_by_feedback, indexing_error = history_by_feedback_id(
        hillslope_history, "hillslope inventory"
    )
    if indexing_error is not None:
        return [indexing_error], False
    fluvial_by_feedback, indexing_error = history_by_feedback_id(
        fluvial_history, "fluvial inventory"
    )
    if indexing_error is not None:
        return [indexing_error], False
    glacial_by_feedback, indexing_error = history_by_feedback_id(
        glacial_history, "glacial inventory"
    )
    if indexing_error is not None:
        return [indexing_error], False
    expected_erosion_feedback_ids = set(
        range(1, configured_erosion_iterations + 1)
    )
    final_feedback_id = configured_erosion_iterations + 1
    if (
        set(hillslope_by_feedback) != expected_erosion_feedback_ids
        or set(fluvial_by_feedback) != expected_erosion_feedback_ids
        or set(glacial_by_feedback) != {final_feedback_id}
    ):
        return ["sediment inventory process stage coverage invalid"], False

    events_by_feedback: dict[int, list[dict[str, Any]]] = {
        feedback_id: [] for feedback_id in range(len(feedback_history))
    }
    previous_event_id = -1
    try:
        for event in numeric_history:
            if not isinstance(event, dict):
                raise TypeError
            event_id = int(event["id"])
            feedback_id = int(event["feedback_stage_id"])
            if (
                event_id != previous_event_id + 1
                or feedback_id not in events_by_feedback
            ):
                raise ValueError
            events_by_feedback[feedback_id].append(event)
            previous_event_id = event_id
    except (KeyError, TypeError, ValueError, OverflowError):
        return ["sediment inventory numeric event order invalid"], False

    inventory = {cell_id: 0.0 for cell_id in cell_ids}
    cumulative_alluvium_depth = {cell_id: 0.0 for cell_id in cell_ids}
    cumulative_bedrock_depth = {cell_id: 0.0 for cell_id in cell_ids}
    process_totals = {
        name: {"gross": 0.0, "alluvium": 0.0, "bedrock": 0.0}
        for name in ("hillslope", "fluvial", "glacial", "numeric_breach")
    }
    cumulative_gross_volume_km3 = 0.0
    cumulative_deposition_volume_km3 = 0.0
    cumulative_export_volume_km3 = 0.0
    cumulative_alluvium_volume_km3 = 0.0
    cumulative_bedrock_volume_km3 = 0.0

    def depth_volume(depth_by_cell: dict[int, float]) -> float:
        return sum(
            depth_by_cell[cell_id] * areas[cell_id] / 1000.0
            for cell_id in cell_ids
        )

    def parse_snapshot(
        stage: dict[str, Any], label: str
    ) -> tuple[dict[int, dict[str, Any]], str | None]:
        raw = stage.get("input_cells", [])
        if not isinstance(raw, list) or len(raw) != len(cell_ids):
            return {}, f"{label} inventory snapshot coverage invalid"
        result: dict[int, dict[str, Any]] = {}
        try:
            for item in raw:
                if not isinstance(item, dict):
                    raise TypeError
                cell_id = int(item["cell_id"])
                thickness = float(item["sediment_thickness_m"])
                if (
                    cell_id not in cell_id_set
                    or cell_id in result
                    or thickness < 0.0
                    or not depth_close(thickness, inventory[cell_id])
                ):
                    raise ValueError
                result[cell_id] = item
        except (KeyError, TypeError, ValueError, OverflowError):
            return {}, f"{label} inventory snapshot replay invalid"
        if set(result) != cell_id_set:
            return {}, f"{label} inventory snapshot coverage invalid"
        return result, None

    try:
        for feedback_id, feedback in enumerate(feedback_history):
            if not isinstance(feedback, dict) or int(feedback.get("id", -1)) != feedback_id:
                return ["sediment inventory feedback stage sequence invalid"], False
            stage_alluvium_volume_km3 = 0.0
            stage_bedrock_volume_km3 = 0.0

            if feedback_id in expected_erosion_feedback_ids:
                hillslope = hillslope_by_feedback[feedback_id]
                fluvial = fluvial_by_feedback[feedback_id]
                _, snapshot_error = parse_snapshot(
                    hillslope, "hillslope sediment"
                )
                if snapshot_error is not None:
                    return [snapshot_error], False

                hillslope_source = {cell_id: 0.0 for cell_id in cell_ids}
                hillslope_deposition = {cell_id: 0.0 for cell_id in cell_ids}
                for edge in hillslope.get("edges", []):
                    source_id = int(edge["source_cell_id"])
                    target_id = int(edge["target_cell_id"])
                    hillslope_source[source_id] += float(
                        edge["source_production_depth_m"]
                    )
                    hillslope_deposition[target_id] += float(
                        edge["target_deposition_depth_m"]
                    )

                fluvial_source = {cell_id: 0.0 for cell_id in cell_ids}
                fluvial_deposition = {cell_id: 0.0 for cell_id in cell_ids}
                fluvial_export_volume_km3 = 0.0
                for step in fluvial.get("cell_steps", []):
                    cell_id = int(step["cell_id"])
                    area = areas[cell_id]
                    fluvial_source[cell_id] += (
                        float(step["local_source_volume_km3"]) * 1000.0 / area
                    )
                    local_deposition_volume_km3 = sum(
                        float(step[key])
                        for key in (
                            "capacity_deposition_volume_km3",
                            "depression_fill_deposition_volume_km3",
                            "lake_trap_deposition_volume_km3",
                            "marine_deposition_volume_km3",
                        )
                    )
                    fluvial_deposition[cell_id] += (
                        local_deposition_volume_km3 * 1000.0 / area
                    )
                    fluvial_export_volume_km3 += float(
                        step["terminal_export_volume_km3"]
                    )
                for allocation in fluvial.get("terminal_allocations", []):
                    target_id = int(allocation["target_cell_id"])
                    fluvial_deposition[target_id] += (
                        float(allocation["total_deposition_volume_km3"])
                        * 1000.0
                        / areas[target_id]
                    )

                hillslope_alluvium = {cell_id: 0.0 for cell_id in cell_ids}
                hillslope_bedrock = {cell_id: 0.0 for cell_id in cell_ids}
                fluvial_alluvium = {cell_id: 0.0 for cell_id in cell_ids}
                fluvial_bedrock = {cell_id: 0.0 for cell_id in cell_ids}
                for cell_id in cell_ids:
                    available = inventory[cell_id]
                    hillslope_alluvium[cell_id] = min(
                        available, hillslope_source[cell_id]
                    )
                    available -= hillslope_alluvium[cell_id]
                    hillslope_bedrock[cell_id] = max(
                        0.0,
                        hillslope_source[cell_id] - hillslope_alluvium[cell_id],
                    )
                    fluvial_alluvium[cell_id] = min(
                        available, fluvial_source[cell_id]
                    )
                    available -= fluvial_alluvium[cell_id]
                    fluvial_bedrock[cell_id] = max(
                        0.0, fluvial_source[cell_id] - fluvial_alluvium[cell_id]
                    )
                    cumulative_alluvium_depth[cell_id] += (
                        hillslope_alluvium[cell_id] + fluvial_alluvium[cell_id]
                    )
                    cumulative_bedrock_depth[cell_id] += (
                        hillslope_bedrock[cell_id] + fluvial_bedrock[cell_id]
                    )
                    inventory[cell_id] = max(
                        0.0,
                        available
                        + hillslope_deposition[cell_id]
                        + fluvial_deposition[cell_id],
                    )

                partition_records = (
                    (
                        "hillslope",
                        hillslope,
                        hillslope_source,
                        hillslope_deposition,
                        hillslope_alluvium,
                        hillslope_bedrock,
                    ),
                    (
                        "fluvial",
                        fluvial,
                        fluvial_source,
                        fluvial_deposition,
                        fluvial_alluvium,
                        fluvial_bedrock,
                    ),
                )
                for (
                    process_name,
                    stage,
                    source,
                    deposition,
                    alluvium,
                    bedrock,
                ) in partition_records:
                    gross = depth_volume(source)
                    deposited = depth_volume(deposition)
                    alluvium_volume = depth_volume(alluvium)
                    bedrock_volume = depth_volume(bedrock)
                    if (
                        not volume_close(
                            float(stage["alluvium_entrainment_volume_km3"]),
                            alluvium_volume,
                        )
                        or not volume_close(
                            float(stage["bedrock_erosion_volume_km3"]),
                            bedrock_volume,
                        )
                    ):
                        return [f"{process_name} source partition invalid"], False
                    process_totals[process_name]["gross"] += gross
                    process_totals[process_name]["alluvium"] += alluvium_volume
                    process_totals[process_name]["bedrock"] += bedrock_volume
                    cumulative_gross_volume_km3 += gross
                    cumulative_deposition_volume_km3 += deposited
                    stage_alluvium_volume_km3 += alluvium_volume
                    stage_bedrock_volume_km3 += bedrock_volume
                    cumulative_alluvium_volume_km3 += alluvium_volume
                    cumulative_bedrock_volume_km3 += bedrock_volume
                cumulative_export_volume_km3 += fluvial_export_volume_km3

            elif feedback_id == final_feedback_id:
                glacial = glacial_by_feedback[feedback_id]
                _, snapshot_error = parse_snapshot(glacial, "glacial sediment")
                if snapshot_error is not None:
                    return [snapshot_error], False
                source = {cell_id: 0.0 for cell_id in cell_ids}
                deposition = {cell_id: 0.0 for cell_id in cell_ids}
                for transfer in glacial.get("transfers", []):
                    source[int(transfer["source_cell_id"])] += float(
                        transfer["source_production_depth_m"]
                    )
                    deposition[int(transfer["target_cell_id"])] += float(
                        transfer["target_deposition_depth_m"]
                    )
                alluvium = {cell_id: 0.0 for cell_id in cell_ids}
                bedrock = {cell_id: 0.0 for cell_id in cell_ids}
                for cell_id in cell_ids:
                    alluvium[cell_id] = min(inventory[cell_id], source[cell_id])
                    bedrock[cell_id] = max(
                        0.0, source[cell_id] - alluvium[cell_id]
                    )
                    cumulative_alluvium_depth[cell_id] += alluvium[cell_id]
                    cumulative_bedrock_depth[cell_id] += bedrock[cell_id]
                    inventory[cell_id] = max(
                        0.0,
                        inventory[cell_id]
                        - alluvium[cell_id]
                        + deposition[cell_id],
                    )
                gross = depth_volume(source)
                deposited = depth_volume(deposition)
                alluvium_volume = depth_volume(alluvium)
                bedrock_volume = depth_volume(bedrock)
                if (
                    not volume_close(
                        float(glacial["alluvium_entrainment_volume_km3"]),
                        alluvium_volume,
                    )
                    or not volume_close(
                        float(glacial["bedrock_erosion_volume_km3"]),
                        bedrock_volume,
                    )
                ):
                    return ["glacial source partition invalid"], False
                process_totals["glacial"]["gross"] += gross
                process_totals["glacial"]["alluvium"] += alluvium_volume
                process_totals["glacial"]["bedrock"] += bedrock_volume
                cumulative_gross_volume_km3 += gross
                cumulative_deposition_volume_km3 += deposited
                stage_alluvium_volume_km3 += alluvium_volume
                stage_bedrock_volume_km3 += bedrock_volume
                cumulative_alluvium_volume_km3 += alluvium_volume
                cumulative_bedrock_volume_km3 += bedrock_volume

            for event in events_by_feedback[feedback_id]:
                event_cell_ids = [int(value) for value in event["cell_ids"]]
                event_sediment_before = [
                    float(value)
                    for value in event[
                        "sediment_thickness_before_correction_m_by_cell"
                    ]
                ]
                if len(event_cell_ids) != len(event_sediment_before) or any(
                    not depth_close(actual, inventory[cell_id])
                    for cell_id, actual in zip(
                        event_cell_ids, event_sediment_before, strict=True
                    )
                ):
                    return ["numeric breach component inventory snapshot invalid"], False

                path_ids = [
                    int(value) for value in event["breach_path_cell_ids"]
                ]
                path_before = [
                    float(value)
                    for value in event[
                        "breach_sediment_thickness_before_excavation_m_by_cell"
                    ]
                ]
                excavation = [
                    float(value)
                    for value in event["breach_excavation_depth_m_by_cell"]
                ]
                emitted_alluvium = [
                    float(value)
                    for value in event[
                        "breach_alluvium_entrainment_depth_m_by_cell"
                    ]
                ]
                emitted_bedrock = [
                    float(value)
                    for value in event["breach_bedrock_erosion_depth_m_by_cell"]
                ]
                if not (
                    len(path_ids)
                    == len(path_before)
                    == len(excavation)
                    == len(emitted_alluvium)
                    == len(emitted_bedrock)
                ) or any(
                    not depth_close(actual, inventory[cell_id])
                    for cell_id, actual in zip(path_ids, path_before, strict=True)
                ):
                    return ["numeric breach path inventory snapshot invalid"], False

                selected = (
                    event.get("selected_correction_method")
                    == "mass_conserving_breach"
                )
                event_alluvium_volume_km3 = 0.0
                event_bedrock_volume_km3 = 0.0
                event_gross_volume_km3 = 0.0
                for index, cell_id in enumerate(path_ids):
                    expected_alluvium = (
                        min(inventory[cell_id], excavation[index])
                        if selected
                        else 0.0
                    )
                    expected_bedrock = (
                        max(0.0, excavation[index] - expected_alluvium)
                        if selected
                        else 0.0
                    )
                    if (
                        not depth_close(emitted_alluvium[index], expected_alluvium)
                        or not depth_close(emitted_bedrock[index], expected_bedrock)
                    ):
                        return ["numeric breach source partition invalid"], False
                    if selected:
                        inventory[cell_id] -= expected_alluvium
                        cumulative_alluvium_depth[cell_id] += expected_alluvium
                        cumulative_bedrock_depth[cell_id] += expected_bedrock
                        event_alluvium_volume_km3 += (
                            expected_alluvium * areas[cell_id] / 1000.0
                        )
                        event_bedrock_volume_km3 += (
                            expected_bedrock * areas[cell_id] / 1000.0
                        )
                        event_gross_volume_km3 += (
                            excavation[index] * areas[cell_id] / 1000.0
                        )

                event_deposition_volume_km3 = 0.0
                if selected:
                    for cell_id, depth_m in zip(
                        [
                            int(value)
                            for value in event["breach_deposition_cell_ids"]
                        ],
                        [
                            float(value)
                            for value in event[
                                "breach_deposition_depth_m_by_cell"
                            ]
                        ],
                        strict=True,
                    ):
                        inventory[cell_id] += depth_m
                        event_deposition_volume_km3 += (
                            depth_m * areas[cell_id] / 1000.0
                        )
                if (
                    not volume_close(
                        float(event["applied_alluvium_entrainment_volume_km3"]),
                        event_alluvium_volume_km3,
                    )
                    or not volume_close(
                        float(event["applied_bedrock_erosion_volume_km3"]),
                        event_bedrock_volume_km3,
                    )
                ):
                    return ["numeric breach source partition totals invalid"], False
                process_totals["numeric_breach"]["gross"] += (
                    event_gross_volume_km3
                )
                process_totals["numeric_breach"]["alluvium"] += (
                    event_alluvium_volume_km3
                )
                process_totals["numeric_breach"]["bedrock"] += (
                    event_bedrock_volume_km3
                )
                cumulative_gross_volume_km3 += event_gross_volume_km3
                cumulative_deposition_volume_km3 += event_deposition_volume_km3
                stage_alluvium_volume_km3 += event_alluvium_volume_km3
                stage_bedrock_volume_km3 += event_bedrock_volume_km3
                cumulative_alluvium_volume_km3 += event_alluvium_volume_km3
                cumulative_bedrock_volume_km3 += event_bedrock_volume_km3

            inventory_volume_km3 = depth_volume(inventory)
            source_partition_residual_km3 = abs(
                cumulative_gross_volume_km3
                - cumulative_alluvium_volume_km3
                - cumulative_bedrock_volume_km3
            )
            inventory_residual_km3 = abs(
                cumulative_bedrock_volume_km3
                - inventory_volume_km3
                - cumulative_export_volume_km3
            )
            feedback_targets = {
                "sediment_alluvium_entrainment_volume_km3": (
                    stage_alluvium_volume_km3
                ),
                "sediment_bedrock_erosion_volume_km3": stage_bedrock_volume_km3,
                "sediment_inventory_volume_km3": inventory_volume_km3,
                "sediment_source_partition_residual_km3": (
                    source_partition_residual_km3
                ),
                "sediment_inventory_mass_balance_residual_km3": (
                    inventory_residual_km3
                ),
            }
            if any(
                not volume_close(
                    float(feedback.get(key, math.nan)),
                    target,
                    cumulative=key
                    not in {
                        "sediment_alluvium_entrainment_volume_km3",
                        "sediment_bedrock_erosion_volume_km3",
                    },
                )
                for key, target in feedback_targets.items()
            ):
                return ["sediment inventory feedback replay invalid"], False
    except (KeyError, TypeError, ValueError, OverflowError, ZeroDivisionError):
        return ["sediment inventory provenance values invalid"], False

    final_inventory_volume_km3 = depth_volume(inventory)
    cell_alluvium_volume_km3 = depth_volume(cumulative_alluvium_depth)
    cell_bedrock_volume_km3 = depth_volume(cumulative_bedrock_depth)
    for cell_id in cell_ids:
        cell = cells_by_id[cell_id]
        try:
            emitted_inventory = float(cell["sediment_thickness_m"])
            emitted_alluvium = float(cell["sediment_alluvium_entrainment_m"])
            emitted_bedrock = float(cell["sediment_bedrock_erosion_m"])
        except (KeyError, TypeError, ValueError, OverflowError):
            return ["sediment inventory cumulative cell fields missing"], False
        if (
            not depth_close(emitted_inventory, inventory[cell_id], final=True)
            or not depth_close(
                emitted_alluvium,
                cumulative_alluvium_depth[cell_id],
                final=True,
            )
            or not depth_close(
                emitted_bedrock, cumulative_bedrock_depth[cell_id], final=True
            )
        ):
            return ["sediment inventory cumulative cell fields invalid"], False

    gross_residual_km3 = abs(
        cumulative_gross_volume_km3
        - cumulative_deposition_volume_km3
        - cumulative_export_volume_km3
    )
    source_partition_residual_km3 = abs(
        cumulative_gross_volume_km3
        - cumulative_alluvium_volume_km3
        - cumulative_bedrock_volume_km3
    )
    inventory_residual_km3 = abs(
        cumulative_bedrock_volume_km3
        - final_inventory_volume_km3
        - cumulative_export_volume_km3
    )
    model_targets = {
        "gross_mobilization_volume_km3": cumulative_gross_volume_km3,
        "deposition_volume_km3": cumulative_deposition_volume_km3,
        "terminal_export_volume_km3": cumulative_export_volume_km3,
        "alluvium_entrainment_volume_km3": cumulative_alluvium_volume_km3,
        "bedrock_erosion_volume_km3": cumulative_bedrock_volume_km3,
        "final_mobile_sediment_inventory_volume_km3": (
            final_inventory_volume_km3
        ),
        "gross_throughput_mass_balance_residual_km3": gross_residual_km3,
        "source_partition_residual_km3": source_partition_residual_km3,
        "inventory_mass_balance_residual_km3": inventory_residual_km3,
        "cell_alluvium_entrainment_volume_km3": cell_alluvium_volume_km3,
        "cell_bedrock_erosion_volume_km3": cell_bedrock_volume_km3,
        "cell_source_partition_residual_km3": abs(
            cumulative_gross_volume_km3
            - cell_alluvium_volume_km3
            - cell_bedrock_volume_km3
        ),
    }
    try:
        if any(
            not volume_close(float(model[key]), target, cumulative=True)
            for key, target in model_targets.items()
        ):
            return ["sediment inventory model aggregates invalid"], False
        process_payload = model["process_source_partition"]
        if not isinstance(process_payload, dict) or set(process_payload) != set(
            process_totals
        ):
            return ["sediment inventory process partition missing"], False
        for process_name, totals in process_totals.items():
            record = process_payload[process_name]
            process_residual = abs(
                totals["gross"] - totals["alluvium"] - totals["bedrock"]
            )
            targets = {
                "gross_mobilization_volume_km3": totals["gross"],
                "alluvium_entrainment_volume_km3": totals["alluvium"],
                "bedrock_erosion_volume_km3": totals["bedrock"],
                "source_partition_residual_km3": process_residual,
            }
            if not isinstance(record, dict) or any(
                not volume_close(float(record.get(key, math.nan)), target, cumulative=True)
                for key, target in targets.items()
            ):
                return ["sediment inventory process partition invalid"], False
    except (KeyError, TypeError, ValueError, OverflowError):
        return ["sediment inventory model values invalid"], False

    summary_targets = {
        "sediment_gross_mobilization_volume_km3": cumulative_gross_volume_km3,
        "sediment_alluvium_entrainment_volume_km3": (
            cumulative_alluvium_volume_km3
        ),
        "sediment_bedrock_erosion_volume_km3": cumulative_bedrock_volume_km3,
        "sediment_final_inventory_volume_km3": final_inventory_volume_km3,
        "sediment_source_partition_residual_km3": (
            source_partition_residual_km3
        ),
        "sediment_inventory_mass_balance_residual_km3": inventory_residual_km3,
        "hillslope_sediment_alluvium_entrainment_volume_km3": (
            process_totals["hillslope"]["alluvium"]
        ),
        "hillslope_sediment_bedrock_erosion_volume_km3": (
            process_totals["hillslope"]["bedrock"]
        ),
        "fluvial_sediment_alluvium_entrainment_volume_km3": (
            process_totals["fluvial"]["alluvium"]
        ),
        "fluvial_sediment_bedrock_erosion_volume_km3": (
            process_totals["fluvial"]["bedrock"]
        ),
        "glacial_sediment_alluvium_entrainment_volume_km3": (
            process_totals["glacial"]["alluvium"]
        ),
        "glacial_sediment_bedrock_erosion_volume_km3": (
            process_totals["glacial"]["bedrock"]
        ),
        "numeric_depression_alluvium_entrainment_volume_km3": (
            process_totals["numeric_breach"]["alluvium"]
        ),
        "numeric_depression_bedrock_erosion_volume_km3": (
            process_totals["numeric_breach"]["bedrock"]
        ),
    }
    if (
        summary.get("sediment_inventory_model") != SEDIMENT_INVENTORY_MODEL
        or summary.get("sediment_initial_mobile_inventory_model")
        != "zero_depth_all_cells_v1"
        or summary.get("sediment_source_partition_model")
        != "available_alluvium_first_then_bedrock_erosion_v1"
        or summary.get("sediment_erosion_stage_source_partition_order")
        != "hillslope_then_fluvial"
    ):
        return ["sediment inventory summary metadata invalid"], False
    try:
        if any(
            not volume_close(float(summary.get(key, math.nan)), target, cumulative=True)
            for key, target in summary_targets.items()
        ):
            return ["sediment inventory summary metrics invalid"], False
    except (TypeError, ValueError, OverflowError):
        return ["sediment inventory summary values invalid"], False

    strict_closure_tolerance_km3 = max(
        0.1, quantized_volume_tolerance_km3 * len(feedback_history)
    )
    if (
        gross_residual_km3 > strict_closure_tolerance_km3
        or source_partition_residual_km3 > strict_closure_tolerance_km3
        or inventory_residual_km3 > strict_closure_tolerance_km3
    ):
        return ["sediment inventory conservation residual too large"], False
    return [], True
