from __future__ import annotations

import heapq
import math
import sys
from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any


MODEL_LITERAL_VALUES: dict[str, Any] = {
    "model_type": "explicit_bedrock_surface_mobile_sediment_interface_v1",
    "elevation_unit": "m",
    "canonical_state_fields": [
        "bedrock_surface_elevation_m",
        "sediment_thickness_m",
    ],
    "derived_surface_field": "elevation_m",
    "bedrock_surface_semantics": (
        "top_of_nonmobile_bedrock_below_mobile_sediment_not_moho_or_"
        "stratigraphic_basement"
    ),
    "interface_equation": (
        "elevation_m=bedrock_surface_elevation_m+sediment_thickness_m"
    ),
    "initialization_equation": (
        "bedrock_surface_elevation_m=elevation_m-sediment_thickness_m"
    ),
    "material_update_equation": (
        "bedrock_surface_elevation_m'=bedrock_surface_elevation_m+"
        "vertical_displacement_m-bedrock_erosion_depth_m;"
        "sediment_thickness_m'=sediment_thickness_m-"
        "alluvium_entrainment_depth_m+deposition_depth_m;"
        "elevation_m'=bedrock_surface_elevation_m'+sediment_thickness_m'"
    ),
    "sea_level_datum_update": (
        "bedrock_surface_elevation_m'=bedrock_surface_elevation_m-"
        "sea_level_adjustment_m;sediment_thickness_m'=sediment_thickness_m"
    ),
    "replay_tolerance_model": (
        "decimal_quantization_forward_error_by_serialized_operand_precision_v1"
    ),
    "canonical_state_serialization_decimal_places": 10,
    "minimum_replay_operand_serialization_decimal_places": 8,
    "authoritative_interface_geometry": True,
    "bedrock_surface_elevation_is_canonical": True,
    "mobile_sediment_thickness_is_canonical": True,
    "surface_elevation_is_derived": True,
    "dry_rock_mass_resolved": False,
    "sediment_density_resolved": False,
    "porosity_resolved": False,
    "compaction_resolved": False,
    "grain_provenance_resolved": False,
    "chemical_weathering_resolved": False,
}

_DYNAMIC_MODEL_FIELDS = {
    "cell_count",
    "maximum_final_closure_residual_m",
    "final_interface_closure_validated",
}

# Canonical cell interface fields and datum/initial operands serialize at ten
# decimal places; hillslope/fluvial/glacial bedrock source arrays serialize at
# no fewer than eight. These evidence precisions are deliberately independent
# of the caller's general display precision (which may be zero).
INTERFACE_STATE_DECIMAL_PRECISION = 10
INTERFACE_REPLAY_INPUT_DECIMAL_PRECISION = 8

INITIAL_ELEVATION_COMPONENT_FIELDS = (
    "initial_isostatic_elevation_m",
    "initial_ridge_uplift_m",
    "initial_orogenic_uplift_m",
    "initial_volcanic_uplift_m",
    "initial_trench_subsidence_m",
    "initial_rift_subsidence_m",
    "initial_transform_fault_relief_m",
    "initial_secondary_roughness_m",
)

FLUVIAL_MIN_TRANSPORT_CAPACITY_FRACTION = 0.90
FLUVIAL_MAX_TRANSPORT_CAPACITY_FRACTION = 0.995
FLUVIAL_LAKE_TRAP_FRACTION = 0.35
FLUVIAL_CLOSED_LAKE_TRAP_FRACTION = 0.65
FLUVIAL_OPEN_OCEAN_DEPOSITION_FRACTION = 0.12
FLUVIAL_SHELF_DEPOSITION_FRACTION = 0.55
FLUVIAL_INLAND_SEA_DEPOSITION_FRACTION = 0.30
FLUVIAL_WATER_BODY_TYPES = {
    "land",
    "ocean",
    "continental_shelf",
    "inland_sea",
    "fresh_lake",
    "saline_basin",
}
NUMERIC_DEPRESSION_DEPTH_TOLERANCE_M = 1.0e-9
NUMERIC_DEPRESSION_MAX_MOBILE_SEDIMENT_M = 5000.0


class _InvalidInterface(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise _InvalidInterface(message)


def _integer(value: Any, field: str) -> int:
    if type(value) is not int:
        raise _InvalidInterface(f"{field} must be an integer")
    return value


def _finite(value: Any, field: str) -> float:
    if type(value) not in (int, float):
        raise _InvalidInterface(f"{field} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise _InvalidInterface(f"{field} must be finite")
    return number


def _nonnegative(value: Any, field: str) -> float:
    number = _finite(value, field)
    if number < 0.0:
        raise _InvalidInterface(f"{field} must be nonnegative")
    return number


def _records(value: Any, field: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, list) or any(
        not isinstance(item, Mapping) for item in value
    ):
        raise _InvalidInterface(f"{field} must be a list of objects")
    return value


def _cell_array(
    record: Mapping[str, Any],
    field: str,
    *,
    cell_count: int,
    nonnegative: bool = False,
) -> list[float]:
    value = record.get(field)
    if not isinstance(value, list) or len(value) != cell_count:
        raise _InvalidInterface(f"{field} must contain one value per cell")
    parser = _nonnegative if nonnegative else _finite
    return [parser(item, field) for item in value]


def _feedback_map(
    records: Sequence[Mapping[str, Any]],
    *,
    label: str,
) -> dict[int, Mapping[str, Any]]:
    result: dict[int, Mapping[str, Any]] = {}
    for record in records:
        feedback_id = _integer(
            record.get("feedback_stage_id"), f"{label}.feedback_stage_id"
        )
        if feedback_id in result:
            raise _InvalidInterface(f"{label} feedback link is not unique")
        result[feedback_id] = record
    return result


def _replay_tolerance(
    *,
    actual: float,
    expected: float,
    operand_sum: float,
    operation_count: int,
    output_precision: int,
) -> float:
    # Initial elevation, plate displacement, stage source depths, and the
    # aggregate datum shifts are serialized independently. Bound their worst
    # case decimal quantization accumulation instead of using a scale-relative
    # tolerance that could hide a large local mutation on an Earth-sized sum.
    if (
        not all(
            math.isfinite(value)
            for value in (actual, expected, operand_sum)
        )
        or operation_count < 0
        or not 0 <= output_precision <= 15
    ):
        raise _InvalidInterface("replay tolerance input is invalid")
    decimal_quantum = 10.0 ** (-output_precision)
    quantization_bound = (
        0.51 * decimal_quantum * max(2, operation_count + 2)
    )
    floating_bound = (
        128.0
        * sys.float_info.epsilon
        * max(2, operation_count + 2)
        * (1.0 + abs(actual) + abs(expected) + operand_sum)
    )
    result = max(5.0e-8, quantization_bound, floating_bound)
    if not math.isfinite(result):
        raise _InvalidInterface("replay tolerance overflowed")
    return result


def validate_sediment_interfaces(world: Any) -> dict[str, Any]:
    """Replay the canonical bedrock/mobile-sediment interface geometry.

    The replay deliberately does not infer sediment dry mass. It reconstructs
    the final bedrock surface from the initial terrain, tectonic displacement,
    bedrock-only erosion, and sea-level datum changes, then independently
    checks the final ``surface = bedrock + mobile thickness`` identity.
    """

    failures: list[str] = []
    metrics: dict[str, Any] = {
        "cell_count": 0,
        "feedback_stage_count": 0,
        "erosion_stage_count": 0,
        "glacial_stage_count": 0,
        "selected_numeric_breach_count": 0,
        "maximum_bedrock_replay_residual_m": math.inf,
        "maximum_mobile_sediment_replay_residual_m": math.inf,
        "maximum_tectonic_cumulative_residual_m": math.inf,
        "maximum_surface_closure_residual_m": math.inf,
        "authoritative_interface_geometry": False,
        "all_native_sediment_mutation_paths_replayed": False,
        "dry_rock_mass_resolved": False,
        "porosity_resolved": False,
        "grain_provenance_resolved": False,
    }
    try:
        _require(isinstance(world, Mapping), "world must be an object")
        model = world.get("sediment_interface_model")
        _require(isinstance(model, Mapping), "sediment interface model missing")
        expected_model_fields = set(MODEL_LITERAL_VALUES) | _DYNAMIC_MODEL_FIELDS
        _require(
            set(model) == expected_model_fields,
            "sediment interface model schema is invalid",
        )
        for field, expected in MODEL_LITERAL_VALUES.items():
            _require(
                model.get(field) == expected,
                f"sediment interface model field {field} is invalid",
            )
        _require(
            model.get("final_interface_closure_validated") is True,
            "native final interface validation flag is invalid",
        )

        cells = _records(world.get("cells"), "cells")
        cell_count = len(cells)
        _require(cell_count > 0, "sediment interface requires cells")
        _require(
            _integer(model.get("cell_count"), "model.cell_count") == cell_count,
            "sediment interface model cell count is invalid",
        )
        cells_by_id: dict[int, Mapping[str, Any]] = {}
        for cell in cells:
            cell_id = _integer(cell.get("id"), "cell.id")
            _require(cell_id not in cells_by_id, "cell IDs are not unique")
            cells_by_id[cell_id] = cell
        _require(
            set(cells_by_id) == set(range(cell_count)),
            "cell IDs must be contiguous",
        )

        summary = world.get("summary")
        _require(isinstance(summary, Mapping), "summary missing")
        output_precision = _integer(
            summary.get("output_float_precision"),
            "summary.output_float_precision",
        )
        _require(
            0 <= output_precision <= 8,
            "output precision is outside the replayable range",
        )
        inventory_model = world.get("sediment_inventory_model")
        _require(
            isinstance(inventory_model, Mapping)
            and inventory_model.get("initial_mobile_sediment_inventory")
            == "zero_depth_all_cells_v1",
            "initial mobile sediment state is not the declared zero state",
        )
        plate_history = _records(
            world.get("plate_motion_history"), "plate_motion_history"
        )
        _require(plate_history, "plate motion history is empty")
        initial_thermal_targets = _cell_array(
            plate_history[0],
            "post_process_local_thermal_subsidence_target_m",
            cell_count=cell_count,
        )

        bedrock = [0.0] * cell_count
        mobile = [0.0] * cell_count
        cumulative_tectonic = [0.0] * cell_count
        operand_sums = [0.0] * cell_count
        operation_counts = [1] * cell_count
        mobile_operand_sums = [0.0] * cell_count
        mobile_operation_counts = [1] * cell_count
        areas = [0.0] * cell_count
        final_bedrock = [0.0] * cell_count
        final_surface = [0.0] * cell_count
        final_mobile = [0.0] * cell_count
        final_cumulative_tectonic = [0.0] * cell_count
        for cell_id in range(cell_count):
            cell = cells_by_id[cell_id]
            initial = _finite(cell.get("initial_elevation_m"), "initial_elevation_m")
            initial_components = [
                _finite(cell.get(field), field)
                for field in INITIAL_ELEVATION_COMPONENT_FIELDS
            ]
            initial_components.append(initial_thermal_targets[cell_id])
            reconstructed_initial = math.fsum(initial_components)
            initial_bound = _replay_tolerance(
                actual=initial,
                expected=reconstructed_initial,
                operand_sum=math.fsum(abs(value) for value in initial_components),
                operation_count=len(initial_components),
                output_precision=INTERFACE_STATE_DECIMAL_PRECISION,
            )
            _require(
                abs(initial - reconstructed_initial) <= initial_bound,
                f"cell {cell_id} initial elevation components do not close",
            )
            bedrock[cell_id] = initial
            operand_sums[cell_id] = abs(initial)
            final_bedrock[cell_id] = _finite(
                cell.get("bedrock_surface_elevation_m"),
                "bedrock_surface_elevation_m",
            )
            final_surface[cell_id] = _finite(
                cell.get("elevation_m"), "elevation_m"
            )
            final_mobile[cell_id] = _nonnegative(
                cell.get("sediment_thickness_m"), "sediment_thickness_m"
            )
            final_cumulative_tectonic[cell_id] = _finite(
                cell.get("cumulative_tectonic_elevation_change_m"),
                "cumulative_tectonic_elevation_change_m",
            )
            areas[cell_id] = _nonnegative(cell.get("area_km2"), "area_km2")
            _require(areas[cell_id] > 0.0, "cell area must be positive")

        feedback = _records(
            world.get("earth_system_feedback_history"),
            "earth_system_feedback_history",
        )
        _require(feedback, "feedback history is empty")
        for expected_id, record in enumerate(feedback):
            _require(
                _integer(record.get("id"), "feedback.id") == expected_id,
                "feedback IDs are not canonical",
            )
        plate_by_id: dict[int, Mapping[str, Any]] = {}
        for record in plate_history:
            record_id = _integer(record.get("id"), "plate_motion.id")
            _require(record_id not in plate_by_id, "plate motion IDs are not unique")
            plate_by_id[record_id] = record

        hillslope = _feedback_map(
            _records(
                world.get("hillslope_sediment_transport_history"),
                "hillslope_sediment_transport_history",
            ),
            label="hillslope",
        )
        fluvial_model = world.get("fluvial_sediment_routing_model")
        _require(
            isinstance(fluvial_model, Mapping)
            and fluvial_model.get("stage_input_snapshot")
            == (
                "complete_cell_hydrology_topology_environment_and_"
                "provisional_surface_v1"
            )
            and fluvial_model.get("stage_input_snapshot_cell_id_indexed")
            is True
            and fluvial_model.get("stage_input_snapshot_used_for_replay")
            is True,
            "fluvial routing input snapshot model is invalid",
        )
        fluvial = _feedback_map(
            _records(
                world.get("fluvial_sediment_routing_history"),
                "fluvial_sediment_routing_history",
            ),
            label="fluvial",
        )
        glacial = _feedback_map(
            _records(
                world.get("glacial_sediment_transport_history"),
                "glacial_sediment_transport_history",
            ),
            label="glacial",
        )
        numeric_by_feedback: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
        for expected_event_id, event in enumerate(_records(
            world.get("numeric_depression_correction_history"),
            "numeric_depression_correction_history",
        )):
            _require(
                _integer(event.get("id"), "numeric.id") == expected_event_id,
                "numeric event IDs are not canonical",
            )
            feedback_id = _integer(
                event.get("feedback_stage_id"), "numeric.feedback_stage_id"
            )
            _require(
                0 <= feedback_id < len(feedback),
                "numeric event feedback link is invalid",
            )
            numeric_by_feedback[feedback_id].append(event)

        erosion_stage_count = 0
        glacial_stage_count = 0
        selected_numeric_breach_count = 0
        consumed_hillslope: set[int] = set()
        consumed_fluvial: set[int] = set()
        consumed_glacial: set[int] = set()

        def apply_bedrock_depths(
            record: Mapping[str, Any], field: str
        ) -> None:
            depths = _cell_array(
                record,
                field,
                cell_count=cell_count,
                nonnegative=True,
            )
            for cell_id, depth in enumerate(depths):
                bedrock[cell_id] -= depth
                operand_sums[cell_id] += abs(depth)
                operation_counts[cell_id] += 1
                _require(
                    math.isfinite(bedrock[cell_id])
                    and math.isfinite(operand_sums[cell_id]),
                    f"{field} bedrock replay overflowed for cell {cell_id}",
                )

        def validate_mobile_snapshot(
            record: Mapping[str, Any], label: str
        ) -> None:
            raw = record.get("input_cells")
            _require(
                isinstance(raw, list) and len(raw) == cell_count,
                f"{label} mobile snapshot coverage is invalid",
            )
            seen: set[int] = set()
            for item in raw:
                _require(
                    isinstance(item, Mapping),
                    f"{label} mobile snapshot item is invalid",
                )
                cell_id = _integer(item.get("cell_id"), f"{label}.cell_id")
                _require(
                    0 <= cell_id < cell_count and cell_id not in seen,
                    f"{label} mobile snapshot IDs are invalid",
                )
                seen.add(cell_id)
                actual = _nonnegative(
                    item.get("sediment_thickness_m"),
                    f"{label}.sediment_thickness_m",
                )
                tolerance = _replay_tolerance(
                    actual=actual,
                    expected=mobile[cell_id],
                    operand_sum=mobile_operand_sums[cell_id],
                    operation_count=mobile_operation_counts[cell_id],
                    output_precision=INTERFACE_REPLAY_INPUT_DECIMAL_PRECISION,
                )
                _require(
                    abs(actual - mobile[cell_id]) <= tolerance,
                    f"{label} mobile snapshot does not replay for cell {cell_id}",
                )
            _require(
                seen == set(range(cell_count)),
                f"{label} mobile snapshot coverage is invalid",
            )

        def apply_mobile_stage(
            alluvium_depths: Sequence[float],
            deposition_depths: Sequence[float],
            deposition_term_counts: Sequence[int],
            label: str,
        ) -> None:
            _require(
                len(alluvium_depths) == cell_count
                and len(deposition_depths) == cell_count
                and len(deposition_term_counts) == cell_count,
                f"{label} mobile update shape is invalid",
            )
            for cell_id in range(cell_count):
                alluvium = _nonnegative(
                    alluvium_depths[cell_id], f"{label}.alluvium"
                )
                deposition = _nonnegative(
                    deposition_depths[cell_id], f"{label}.deposition"
                )
                availability_bound = _replay_tolerance(
                    actual=alluvium,
                    expected=mobile[cell_id],
                    operand_sum=(
                        mobile_operand_sums[cell_id]
                        + abs(alluvium)
                        + abs(mobile[cell_id])
                    ),
                    operation_count=mobile_operation_counts[cell_id] + 2,
                    output_precision=INTERFACE_REPLAY_INPUT_DECIMAL_PRECISION,
                )
                _require(
                    alluvium <= mobile[cell_id] + availability_bound,
                    f"{label} entrainment exceeds opening mobile inventory "
                    f"for cell {cell_id}",
                )
                candidate = mobile[cell_id] - alluvium + deposition
                next_operand_sum = (
                    mobile_operand_sums[cell_id]
                    + abs(alluvium)
                    + abs(deposition)
                )
                next_operation_count = (
                    mobile_operation_counts[cell_id]
                    + 2
                    + max(0, deposition_term_counts[cell_id])
                )
                _require(
                    math.isfinite(candidate)
                    and math.isfinite(next_operand_sum),
                    f"{label} mobile replay overflowed for cell {cell_id}",
                )
                zero_bound = _replay_tolerance(
                    actual=candidate,
                    expected=0.0,
                    operand_sum=next_operand_sum,
                    operation_count=next_operation_count,
                    output_precision=INTERFACE_REPLAY_INPUT_DECIMAL_PRECISION,
                )
                _require(
                    candidate >= -zero_bound,
                    f"{label} overdraws mobile inventory for cell {cell_id}",
                )
                mobile[cell_id] = max(0.0, candidate)
                mobile_operand_sums[cell_id] = next_operand_sum
                mobile_operation_counts[cell_id] = next_operation_count

        def erosion_deposition_depths(
            hillslope_record: Mapping[str, Any],
            fluvial_record: Mapping[str, Any],
        ) -> tuple[list[float], list[int]]:
            deposition = [0.0] * cell_count
            term_counts = [0] * cell_count
            for edge in _records(hillslope_record.get("edges"), "hillslope.edges"):
                source_id = _integer(
                    edge.get("source_cell_id"), "hillslope.source_cell_id"
                )
                target_id = _integer(
                    edge.get("target_cell_id"), "hillslope.target_cell_id"
                )
                _require(
                    0 <= source_id < cell_count and 0 <= target_id < cell_count,
                    "hillslope deposition endpoints are invalid",
                )
                source_area = _nonnegative(
                    edge.get("source_area_km2"), "hillslope.source_area_km2"
                )
                target_area = _nonnegative(
                    edge.get("target_area_km2"), "hillslope.target_area_km2"
                )
                source_depth = _nonnegative(
                    edge.get("source_production_depth_m"),
                    "hillslope.source_production_depth_m",
                )
                emitted_target_depth = _nonnegative(
                    edge.get("target_deposition_depth_m"),
                    "hillslope.target_deposition_depth_m",
                )
                emitted_volume = _nonnegative(
                    edge.get("transfer_volume_km3"),
                    "hillslope.transfer_volume_km3",
                )
                for actual, expected, label in (
                    (source_area, areas[source_id], "hillslope source area"),
                    (target_area, areas[target_id], "hillslope target area"),
                ):
                    bound = _replay_tolerance(
                        actual=actual,
                        expected=expected,
                        operand_sum=abs(actual) + abs(expected),
                        operation_count=2,
                        output_precision=10,
                    )
                    _require(abs(actual - expected) <= bound, f"{label} is invalid")
                expected_volume = source_depth * areas[source_id] / 1000.0
                expected_target_depth = (
                    expected_volume * 1000.0 / areas[target_id]
                )
                for actual, expected, label, precision in (
                    (
                        emitted_volume,
                        expected_volume,
                        "hillslope transfer volume",
                        10,
                    ),
                    (
                        emitted_target_depth,
                        expected_target_depth,
                        "hillslope target deposition depth",
                        INTERFACE_REPLAY_INPUT_DECIMAL_PRECISION,
                    ),
                ):
                    bound = _replay_tolerance(
                        actual=actual,
                        expected=expected,
                        operand_sum=(
                            abs(source_depth)
                            + abs(areas[source_id])
                            + abs(areas[target_id])
                        ),
                        operation_count=4,
                        output_precision=precision,
                    )
                    _require(abs(actual - expected) <= bound, f"{label} is invalid")
                deposition[target_id] += expected_target_depth
                _require(
                    math.isfinite(deposition[target_id]),
                    "hillslope deposition accumulation overflowed",
                )
                term_counts[target_id] += 1

            def require_close(
                actual: float,
                expected: float,
                label: str,
                *,
                precision: int = 10,
                count: int = 8,
            ) -> None:
                bound = _replay_tolerance(
                    actual=actual,
                    expected=expected,
                    operand_sum=abs(actual) + abs(expected),
                    operation_count=count,
                    output_precision=precision,
                )
                _require(
                    abs(actual - expected) <= bound,
                    f"{label} is invalid: actual={actual!r}, "
                    f"expected={expected!r}, bound={bound!r}",
                )

            fluvial_source_depths = _cell_array(
                fluvial_record,
                "source_production_depth_m_by_cell",
                cell_count=cell_count,
                nonnegative=True,
            )
            accumulation_scale = _nonnegative(
                fluvial_record.get("accumulation_scale"),
                "fluvial.accumulation_scale",
            )
            _require(
                accumulation_scale >= 1.0,
                "fluvial accumulation scale is invalid",
            )

            hillslope_input_by_id: dict[int, Mapping[str, Any]] = {}
            for input_cell in _records(
                hillslope_record.get("input_cells"),
                "hillslope.input_cells",
            ):
                input_id = _integer(
                    input_cell.get("cell_id"), "hillslope.input_cell_id"
                )
                _require(
                    0 <= input_id < cell_count
                    and input_id not in hillslope_input_by_id,
                    "hillslope input cell IDs are invalid",
                )
                hillslope_input_by_id[input_id] = input_cell
            _require(
                len(hillslope_input_by_id) == cell_count,
                "hillslope input cell coverage is invalid",
            )

            _require(
                _integer(
                    fluvial_record.get("input_cell_count"),
                    "fluvial.input_cell_count",
                )
                == cell_count,
                "fluvial input cell count is invalid",
            )
            routing_input_by_id: dict[int, dict[str, Any]] = {}
            for expected_cell_id, input_cell in enumerate(
                _records(
                    fluvial_record.get("input_cells"),
                    "fluvial.input_cells",
                )
            ):
                input_id = _integer(
                    input_cell.get("cell_id"), "fluvial.input_cell_id"
                )
                flow_to = _integer(
                    input_cell.get("flow_to_cell_id"),
                    "fluvial.input.flow_to_cell_id",
                )
                depression_component_id = _integer(
                    input_cell.get("depression_component_id"),
                    "fluvial.input.depression_component_id",
                )
                depression_sink_cell_id = _integer(
                    input_cell.get("depression_sink_cell_id"),
                    "fluvial.input.depression_sink_cell_id",
                )
                _require(
                    input_id == expected_cell_id
                    and -1 <= flow_to < cell_count
                    and flow_to != input_id
                    and -1 <= depression_component_id < cell_count
                    and -1 <= depression_sink_cell_id < cell_count,
                    "fluvial routing input topology is invalid",
                )
                water_body = input_cell.get("water_body_type")
                _require(
                    type(water_body) is str
                    and water_body in FLUVIAL_WATER_BODY_TYPES,
                    "fluvial routing input water-body type is invalid",
                )
                boolean_values: dict[str, bool] = {}
                for field in (
                    "is_water",
                    "is_river",
                    "is_lake",
                    "lake_overflows",
                ):
                    value = input_cell.get(field)
                    _require(
                        type(value) is bool,
                        f"fluvial.input.{field} must be boolean",
                    )
                    boolean_values[field] = value
                input_area = _nonnegative(
                    input_cell.get("cell_area_km2"),
                    "fluvial.input.cell_area_km2",
                )
                numeric_values = {
                    "flow_accumulation": _nonnegative(
                        input_cell.get("flow_accumulation"),
                        "fluvial.input.flow_accumulation",
                    ),
                    "runoff_mm_y": _nonnegative(
                        input_cell.get("runoff_mm_y"),
                        "fluvial.input.runoff_mm_y",
                    ),
                    "hydrologic_flow_slope": _nonnegative(
                        input_cell.get("hydrologic_flow_slope"),
                        "fluvial.input.hydrologic_flow_slope",
                    ),
                    "routing_base_elevation_m": _finite(
                        input_cell.get("routing_base_elevation_m"),
                        "fluvial.input.routing_base_elevation_m",
                    ),
                    "spill_elevation_m": _finite(
                        input_cell.get("spill_elevation_m"),
                        "fluvial.input.spill_elevation_m",
                    ),
                }
                require_close(
                    input_area,
                    areas[input_id],
                    "fluvial input cell area",
                )
                hillslope_input = hillslope_input_by_id[input_id]
                _require(
                    type(hillslope_input.get("is_water")) is bool
                    and type(hillslope_input.get("is_lake")) is bool
                    and hillslope_input.get("is_water")
                    is boolean_values["is_water"]
                    and hillslope_input.get("is_lake")
                    is boolean_values["is_lake"],
                    "fluvial routing water state disagrees with stage input",
                )
                routing_input_by_id[input_id] = {
                    "flow_to_cell_id": flow_to,
                    "depression_component_id": depression_component_id,
                    "depression_sink_cell_id": depression_sink_cell_id,
                    "water_body_type": water_body,
                    "cell_area_km2": input_area,
                    **boolean_values,
                    **numeric_values,
                }
            _require(
                len(routing_input_by_id) == cell_count,
                "fluvial routing input coverage is invalid",
            )

            upstream_count = [0] * cell_count
            for input_cell in routing_input_by_id.values():
                receiver = int(input_cell["flow_to_cell_id"])
                if receiver >= 0:
                    upstream_count[receiver] += 1
            ready = [
                cell_id
                for cell_id, count in enumerate(upstream_count)
                if count == 0
            ]
            heapq.heapify(ready)
            flow_order: list[int] = []
            while ready:
                cell_id = heapq.heappop(ready)
                flow_order.append(cell_id)
                receiver = int(
                    routing_input_by_id[cell_id]["flow_to_cell_id"]
                )
                if receiver >= 0:
                    upstream_count[receiver] -= 1
                    if upstream_count[receiver] == 0:
                        heapq.heappush(ready, receiver)
            _require(
                len(flow_order) == cell_count,
                "fluvial routing input graph contains a cycle",
            )
            flow_rank = {
                cell_id: rank for rank, cell_id in enumerate(flow_order)
            }
            incoming_by_cell = [0.0] * cell_count
            local_deposition_by_cell = [0.0] * cell_count
            terminal_storage_by_sink: dict[int, float] = {}
            seen_steps: set[int] = set()
            stage_counts = {
                "active_cell_step_count": 0,
                "routed_edge_count": 0,
                "land_terminal_count": 0,
                "marine_terminal_count": 0,
                "terminal_allocation_count": 0,
            }
            stage_volumes = {
                "local_source_volume_km3": 0.0,
                "routed_throughput_volume_km3": 0.0,
                "capacity_deposition_volume_km3": 0.0,
                "depression_fill_deposition_volume_km3": 0.0,
                "lake_trap_deposition_volume_km3": 0.0,
                "terminal_land_deposition_volume_km3": 0.0,
                "marine_deposition_volume_km3": 0.0,
                "terminal_export_volume_km3": 0.0,
            }
            for cell_id in range(cell_count):
                stage_volumes["local_source_volume_km3"] += (
                    fluvial_source_depths[cell_id]
                    * areas[cell_id]
                    / 1000.0
                )
                _require(
                    math.isfinite(stage_volumes["local_source_volume_km3"]),
                    "fluvial local-source aggregate overflowed",
                )
            previous_step_flow_rank = -1
            for step in _records(
                fluvial_record.get("cell_steps"), "fluvial.cell_steps"
            ):
                cell_id = _integer(step.get("cell_id"), "fluvial.cell_id")
                emitted_flow_to = _integer(
                    step.get("flow_to_cell_id"), "fluvial.flow_to_cell_id"
                )
                emitted_depression_component_id = _integer(
                    step.get("depression_component_id"),
                    "fluvial.depression_component_id",
                )
                emitted_depression_sink_cell_id = _integer(
                    step.get("depression_sink_cell_id"),
                    "fluvial.depression_sink_cell_id",
                )
                _require(
                    0 <= cell_id < cell_count
                    and cell_id not in seen_steps,
                    "fluvial cell-step ID is invalid",
                )
                input_cell = routing_input_by_id[cell_id]
                flow_to = int(input_cell["flow_to_cell_id"])
                depression_component_id = int(
                    input_cell["depression_component_id"]
                )
                depression_sink_cell_id = int(
                    input_cell["depression_sink_cell_id"]
                )
                current_flow_rank = flow_rank[cell_id]
                _require(
                    current_flow_rank > previous_step_flow_rank
                    and emitted_flow_to == flow_to
                    and emitted_depression_component_id
                    == depression_component_id
                    and emitted_depression_sink_cell_id
                    == depression_sink_cell_id,
                    "fluvial cell-step order or input topology is invalid",
                )
                previous_step_flow_rank = current_flow_rank
                seen_steps.add(cell_id)
                for field in (
                    "is_water",
                    "is_river",
                    "is_lake",
                    "lake_overflows",
                    "is_land_terminal",
                    "is_marine_terminal",
                ):
                    _require(
                        type(step.get(field)) is bool,
                        f"fluvial.{field} must be boolean",
                    )
                is_water = bool(input_cell["is_water"])
                is_river = bool(input_cell["is_river"])
                is_lake = bool(input_cell["is_lake"])
                lake_overflows = bool(input_cell["lake_overflows"])
                water_body = input_cell["water_body_type"]
                _require(
                    step.get("water_body_type") == water_body
                    and step["is_water"] is is_water
                    and step["is_river"] is is_river
                    and step["is_lake"] is is_lake
                    and step["lake_overflows"] is lake_overflows,
                    "fluvial cell-step environment disagrees with input",
                )
                expected_land_terminal = not is_water and flow_to < 0
                expected_marine_terminal = is_water and flow_to < 0
                _require(
                    step["is_land_terminal"] is expected_land_terminal
                    and step["is_marine_terminal"] is expected_marine_terminal
                    and not (is_water and flow_to >= 0),
                    "fluvial terminal classification is invalid",
                )

                emitted_area = _nonnegative(
                    step.get("cell_area_km2"), "fluvial.cell_area_km2"
                )
                emitted_flow_accumulation = _nonnegative(
                    step.get("flow_accumulation"),
                    "fluvial.flow_accumulation",
                )
                emitted_runoff = _nonnegative(
                    step.get("runoff_mm_y"), "fluvial.runoff"
                )
                emitted_slope = _nonnegative(
                    step.get("hydrologic_flow_slope"), "fluvial.flow_slope"
                )
                emitted_routing_base = _finite(
                    step.get("routing_base_elevation_m"),
                    "fluvial.routing_base_elevation_m",
                )
                emitted_spill = _finite(
                    step.get("spill_elevation_m"),
                    "fluvial.spill_elevation_m",
                )
                area = float(input_cell["cell_area_km2"])
                flow_accumulation = float(input_cell["flow_accumulation"])
                runoff = float(input_cell["runoff_mm_y"])
                slope = float(input_cell["hydrologic_flow_slope"])
                routing_base = float(input_cell["routing_base_elevation_m"])
                spill = float(input_cell["spill_elevation_m"])
                for actual, expected_value, label in (
                    (emitted_area, area, "fluvial cell-step area"),
                    (
                        emitted_flow_accumulation,
                        flow_accumulation,
                        "fluvial cell-step flow accumulation",
                    ),
                    (emitted_runoff, runoff, "fluvial cell-step runoff"),
                    (emitted_slope, slope, "fluvial cell-step flow slope"),
                    (
                        emitted_routing_base,
                        routing_base,
                        "fluvial cell-step routing base",
                    ),
                    (emitted_spill, spill, "fluvial cell-step spill elevation"),
                ):
                    require_close(
                        actual,
                        expected_value,
                        label,
                        precision=INTERFACE_STATE_DECIMAL_PRECISION,
                    )
                emitted_source = _nonnegative(
                    step.get("local_source_volume_km3"),
                    "fluvial.local_source_volume_km3",
                )
                emitted_incoming = _nonnegative(
                    step.get("incoming_volume_km3"),
                    "fluvial.incoming_volume_km3",
                )
                emitted_available = _nonnegative(
                    step.get("available_volume_km3"),
                    "fluvial.available_volume_km3",
                )
                emitted_capacity_fraction = _nonnegative(
                    step.get("transport_capacity_fraction"),
                    "fluvial.transport_capacity_fraction",
                )
                emitted = {
                    field: _nonnegative(step.get(field), f"fluvial.{field}")
                    for field in (
                        "depression_accommodation_volume_km3",
                        "capacity_deposition_volume_km3",
                        "depression_fill_deposition_volume_km3",
                        "lake_trap_deposition_volume_km3",
                        "marine_deposition_volume_km3",
                        "routed_outgoing_volume_km3",
                        "terminal_land_storage_volume_km3",
                        "terminal_export_volume_km3",
                    )
                }
                emitted_residual = _finite(
                    step.get("local_mass_balance_residual_km3"),
                    "fluvial.local_mass_balance_residual_km3",
                )
                require_close(area, areas[cell_id], "fluvial cell area")
                expected_source = (
                    fluvial_source_depths[cell_id] * areas[cell_id] / 1000.0
                )
                expected_incoming = incoming_by_cell[cell_id]
                expected_available = expected_source + expected_incoming
                _require(
                    expected_available > 1.0e-15,
                    "fluvial cell-step has no active material load",
                )
                require_close(
                    emitted_source, expected_source, "fluvial local source"
                )
                require_close(
                    emitted_incoming, expected_incoming, "fluvial incoming load"
                )
                require_close(
                    emitted_available, expected_available, "fluvial available load"
                )

                expected_capacity_fraction = 0.0
                expected = {field: 0.0 for field in emitted}
                if expected_marine_terminal:
                    stage_counts["marine_terminal_count"] += 1
                    deposition_fraction = {
                        "continental_shelf": FLUVIAL_SHELF_DEPOSITION_FRACTION,
                        "inland_sea": FLUVIAL_INLAND_SEA_DEPOSITION_FRACTION,
                    }.get(
                        water_body,
                        FLUVIAL_OPEN_OCEAN_DEPOSITION_FRACTION,
                    )
                    expected["marine_deposition_volume_km3"] = (
                        expected_available * deposition_fraction
                    )
                    expected["terminal_export_volume_km3"] = (
                        expected_available
                        - expected["marine_deposition_volume_km3"]
                    )
                elif expected_land_terminal:
                    stage_counts["land_terminal_count"] += 1
                    expected["terminal_land_storage_volume_km3"] = (
                        expected_available
                    )
                    terminal_storage_by_sink[cell_id] = expected_available
                else:
                    flow_index = min(
                        1.0,
                        math.sqrt(
                            max(0.0, flow_accumulation) / accumulation_scale
                        ),
                    )
                    slope_index = min(1.0, max(0.0, slope) * 1200.0)
                    runoff_index = min(1.0, max(0.0, runoff) / 2000.0)
                    expected_capacity_fraction = min(
                        FLUVIAL_MAX_TRANSPORT_CAPACITY_FRACTION,
                        max(
                            FLUVIAL_MIN_TRANSPORT_CAPACITY_FRACTION,
                            FLUVIAL_MIN_TRANSPORT_CAPACITY_FRACTION
                            + 0.045 * flow_index
                            + 0.025 * slope_index
                            + 0.015 * runoff_index
                            + (0.015 if is_river else 0.0),
                        ),
                    )
                    if depression_component_id >= 0:
                        expected[
                            "depression_accommodation_volume_km3"
                        ] = (
                            max(0.0, spill - routing_base)
                            * areas[cell_id]
                            / 1000.0
                        )
                        expected[
                            "depression_fill_deposition_volume_km3"
                        ] = min(
                            expected_available,
                            expected[
                                "depression_accommodation_volume_km3"
                            ],
                        )
                    remaining = (
                        expected_available
                        - expected[
                            "depression_fill_deposition_volume_km3"
                        ]
                    )
                    expected["capacity_deposition_volume_km3"] = min(
                        remaining,
                        expected_available
                        * (1.0 - expected_capacity_fraction),
                    )
                    remaining -= expected["capacity_deposition_volume_km3"]
                    if is_lake:
                        lake_fraction = (
                            FLUVIAL_LAKE_TRAP_FRACTION
                            if lake_overflows
                            else FLUVIAL_CLOSED_LAKE_TRAP_FRACTION
                        )
                        expected["lake_trap_deposition_volume_km3"] = min(
                            remaining,
                            max(
                                0.0,
                                expected_available * lake_fraction
                                - expected[
                                    "depression_fill_deposition_volume_km3"
                                ]
                                - expected[
                                    "capacity_deposition_volume_km3"
                                ],
                            ),
                        )
                        remaining -= expected[
                            "lake_trap_deposition_volume_km3"
                        ]
                    expected["routed_outgoing_volume_km3"] = max(
                        0.0, remaining
                    )

                require_close(
                    emitted_capacity_fraction,
                    expected_capacity_fraction,
                    "fluvial capacity fraction",
                    precision=INTERFACE_REPLAY_INPUT_DECIMAL_PRECISION,
                )
                for field, expected_value in expected.items():
                    require_close(
                        emitted[field],
                        expected_value,
                        f"fluvial cell {cell_id} {field}",
                    )
                expected_residual = (
                    expected_available
                    - expected["capacity_deposition_volume_km3"]
                    - expected["depression_fill_deposition_volume_km3"]
                    - expected["lake_trap_deposition_volume_km3"]
                    - expected["marine_deposition_volume_km3"]
                    - expected["routed_outgoing_volume_km3"]
                    - expected["terminal_land_storage_volume_km3"]
                    - expected["terminal_export_volume_km3"]
                )
                require_close(
                    emitted_residual,
                    expected_residual,
                    "fluvial local mass-balance residual",
                )
                outgoing = expected["routed_outgoing_volume_km3"]
                if outgoing > 1.0e-15:
                    _require(flow_to >= 0, "fluvial outgoing receiver is absent")
                    incoming_by_cell[flow_to] += outgoing
                    stage_counts["routed_edge_count"] += 1
                    _require(
                        math.isfinite(incoming_by_cell[flow_to]),
                        "fluvial incoming accumulation overflowed",
                    )
                local_volume = (
                    expected["capacity_deposition_volume_km3"]
                    + expected["depression_fill_deposition_volume_km3"]
                    + expected["lake_trap_deposition_volume_km3"]
                )
                local_deposition_by_cell[cell_id] = local_volume
                total_cell_deposition = (
                    local_volume + expected["marine_deposition_volume_km3"]
                )
                depth = total_cell_deposition * 1000.0 / areas[cell_id]
                _require(math.isfinite(depth), "fluvial deposition overflowed")
                deposition[cell_id] += depth
                _require(
                    math.isfinite(deposition[cell_id]),
                    "fluvial deposition accumulation overflowed",
                )
                term_counts[cell_id] += 5
                stage_counts["active_cell_step_count"] += 1
                stage_volumes["routed_throughput_volume_km3"] += expected[
                    "routed_outgoing_volume_km3"
                ]
                stage_volumes["capacity_deposition_volume_km3"] += expected[
                    "capacity_deposition_volume_km3"
                ]
                stage_volumes[
                    "depression_fill_deposition_volume_km3"
                ] += expected["depression_fill_deposition_volume_km3"]
                stage_volumes["lake_trap_deposition_volume_km3"] += expected[
                    "lake_trap_deposition_volume_km3"
                ]
                stage_volumes["marine_deposition_volume_km3"] += expected[
                    "marine_deposition_volume_km3"
                ]
                stage_volumes["terminal_export_volume_km3"] += expected[
                    "terminal_export_volume_km3"
                ]
                _require(
                    all(math.isfinite(value) for value in stage_volumes.values()),
                    "fluvial stage aggregate overflowed",
                )

            for cell_id, incoming in enumerate(incoming_by_cell):
                source_volume = (
                    fluvial_source_depths[cell_id]
                    * areas[cell_id]
                    / 1000.0
                )
                if cell_id not in seen_steps:
                    _require(
                        source_volume + incoming <= 1.0e-15,
                        "fluvial active cell-step coverage is invalid",
                    )

            terminal_targets_by_sink: dict[int, list[int]] = defaultdict(list)
            for target_id in range(cell_count):
                target_input = routing_input_by_id[target_id]
                target_sink_id = int(
                    target_input["depression_sink_cell_id"]
                )
                if (
                    target_input["is_water"] is False
                    and int(target_input["depression_component_id"]) >= 0
                    and 0 <= target_sink_id < cell_count
                ):
                    terminal_targets_by_sink[target_sink_id].append(target_id)
            expected_allocation_keys: list[tuple[int, int]] = []
            for sink_id in sorted(terminal_storage_by_sink):
                target_ids = terminal_targets_by_sink.get(sink_id, [])
                if not target_ids:
                    target_ids = [sink_id]
                expected_allocation_keys.extend(
                    (sink_id, target_id) for target_id in target_ids
                )

            parsed_groups: dict[int, list[dict[str, float | int]]] = {}
            previous_key = (-1, -1)
            seen_allocation_targets: set[int] = set()
            terminal_accommodation_volume = 0.0
            allocation_records = _records(
                fluvial_record.get("terminal_allocations"),
                "fluvial.terminal_allocations",
            )
            _require(
                len(allocation_records) == len(expected_allocation_keys),
                "fluvial terminal allocation footprint coverage is invalid",
            )
            for allocation_index, allocation in enumerate(allocation_records):
                sink_id = _integer(
                    allocation.get("sink_cell_id"),
                    "fluvial.terminal_allocation.sink_cell_id",
                )
                target_id = _integer(
                    allocation.get("target_cell_id"),
                    "fluvial.terminal_allocation.target_cell_id",
                )
                key = (sink_id, target_id)
                _require(
                    key == expected_allocation_keys[allocation_index]
                    and sink_id in terminal_storage_by_sink
                    and 0 <= target_id < cell_count
                    and target_id not in seen_allocation_targets
                    and key > previous_key,
                    "fluvial terminal allocation links are invalid",
                )
                seen_allocation_targets.add(target_id)
                previous_key = key
                target_area = _nonnegative(
                    allocation.get("target_area_km2"),
                    "fluvial.terminal_allocation.target_area_km2",
                )
                require_close(
                    target_area,
                    areas[target_id],
                    "fluvial allocation target area",
                )
                routing_base = _finite(
                    allocation.get("routing_base_elevation_m"),
                    "fluvial.terminal_allocation.routing_base_elevation_m",
                )
                spill = _finite(
                    allocation.get("spill_elevation_m"),
                    "fluvial.terminal_allocation.spill_elevation_m",
                )
                prior_local = _nonnegative(
                    allocation.get("prior_local_deposition_volume_km3"),
                    "fluvial.terminal_allocation.prior_local_deposition_volume_km3",
                )
                require_close(
                    prior_local,
                    local_deposition_by_cell[target_id],
                    "fluvial allocation prior local deposition",
                )
                depression_component_id = _integer(
                    allocation.get("depression_component_id"),
                    "fluvial.terminal_allocation.depression_component_id",
                )
                _require(
                    -1 <= depression_component_id < cell_count,
                    "fluvial allocation depression component is invalid",
                )
                target_input = routing_input_by_id[target_id]
                is_depression_component_target = (
                    depression_component_id >= 0
                    and target_input["is_water"] is False
                    and target_input["depression_component_id"]
                    == depression_component_id
                    and target_input["depression_sink_cell_id"] == sink_id
                )
                # A dry world can leave its global land sink outside every
                # depression component.  The native router then uses its
                # documented singleton fallback target rather than dropping
                # the terminal load.  Prove that exact fallback shape from the
                # stage input and reconstructed component footprint; do not
                # treat an arbitrary non-component cell as a valid target.
                is_unclassified_land_sink_fallback = (
                    not terminal_targets_by_sink.get(sink_id)
                    and target_id == sink_id
                    and target_input["is_water"] is False
                    and int(target_input["flow_to_cell_id"]) < 0
                    and int(target_input["depression_component_id"]) == -1
                    and int(target_input["depression_sink_cell_id"]) == -1
                    and depression_component_id == -1
                )
                _require(
                    is_depression_component_target
                    or is_unclassified_land_sink_fallback,
                    "fluvial allocation target topology is invalid",
                )
                expected_routing_base = float(
                    target_input["routing_base_elevation_m"]
                )
                expected_spill = float(target_input["spill_elevation_m"])
                require_close(
                    routing_base,
                    expected_routing_base,
                    "fluvial allocation routing-base witness",
                    precision=INTERFACE_STATE_DECIMAL_PRECISION,
                )
                require_close(
                    spill,
                    expected_spill,
                    "fluvial allocation spill-elevation witness",
                    precision=INTERFACE_STATE_DECIMAL_PRECISION,
                )
                expected_capacity = (
                    max(
                        0.0,
                        expected_spill
                        - expected_routing_base
                        - prior_local * 1000.0 / areas[target_id],
                    )
                    * areas[target_id]
                    / 1000.0
                    if depression_component_id >= 0
                    else 0.0
                )
                emitted_capacity = _nonnegative(
                    allocation.get("accommodation_before_allocation_km3"),
                    "fluvial.terminal_allocation.accommodation_before_allocation_km3",
                )
                require_close(
                    emitted_capacity,
                    expected_capacity,
                    "fluvial allocation accommodation capacity",
                )
                parsed_groups.setdefault(sink_id, []).append(
                    {
                        "target_id": target_id,
                        "area": areas[target_id],
                        "capacity": expected_capacity,
                        "emitted_accommodation": _nonnegative(
                            allocation.get(
                                "accommodation_deposition_volume_km3"
                            ),
                            "fluvial.terminal_allocation.accommodation_deposition_volume_km3",
                        ),
                        "emitted_excess": _nonnegative(
                            allocation.get("excess_aggradation_volume_km3"),
                            "fluvial.terminal_allocation.excess_aggradation_volume_km3",
                        ),
                        "emitted_total": _nonnegative(
                            allocation.get("total_deposition_volume_km3"),
                            "fluvial.terminal_allocation.total_deposition_volume_km3",
                        ),
                    }
                )
            _require(
                set(parsed_groups) == set(terminal_storage_by_sink),
                "fluvial terminal allocation sink coverage is invalid",
            )
            for sink_id, group in parsed_groups.items():
                storage = terminal_storage_by_sink[sink_id]
                capacities = [float(item["capacity"]) for item in group]
                target_areas = [float(item["area"]) for item in group]
                # Match the native ordered accumulation over canonical target
                # order because a different summation algorithm can change a
                # min/proportional-allocation branch at large magnitudes.
                total_capacity = 0.0
                total_area = 0.0
                for capacity in capacities:
                    total_capacity += capacity
                for target_area in target_areas:
                    total_area += target_area
                accommodation_total = min(storage, total_capacity)
                remaining_accommodation = accommodation_total
                last_capacity_index = max(
                    (
                        index
                        for index, value in enumerate(capacities)
                        if value > 1.0e-15
                    ),
                    default=-1,
                )
                expected_accommodation: list[float] = []
                for index, capacity in enumerate(capacities):
                    value = 0.0
                    if (
                        remaining_accommodation > 0.0
                        and total_capacity > 0.0
                        and capacity > 0.0
                    ):
                        value = (
                            remaining_accommodation
                            if index == last_capacity_index
                            else min(
                                remaining_accommodation,
                                accommodation_total
                                * capacity
                                / total_capacity,
                            )
                        )
                    remaining_accommodation -= value
                    expected_accommodation.append(value)
                excess_total = storage - accommodation_total
                remaining_excess = excess_total
                expected_excess: list[float] = []
                for index, target_area in enumerate(target_areas):
                    value = (
                        remaining_excess
                        if index + 1 == len(group)
                        else min(
                            remaining_excess,
                            excess_total
                            * target_area
                            / max(1.0e-15, total_area),
                        )
                    )
                    remaining_excess -= value
                    expected_excess.append(value)
                for index, item in enumerate(group):
                    require_close(
                        float(item["emitted_accommodation"]),
                        expected_accommodation[index],
                        "fluvial allocation accommodation deposition",
                    )
                    require_close(
                        float(item["emitted_excess"]),
                        expected_excess[index],
                        "fluvial allocation excess deposition",
                    )
                    expected_total = (
                        expected_accommodation[index] + expected_excess[index]
                    )
                    require_close(
                        float(item["emitted_total"]),
                        expected_total,
                        "fluvial allocation total deposition",
                    )
                    if expected_total > 1.0e-15:
                        stage_counts["terminal_allocation_count"] += 1
                    stage_volumes[
                        "depression_fill_deposition_volume_km3"
                    ] += expected_accommodation[index]
                    terminal_accommodation_volume += expected_accommodation[
                        index
                    ]
                    target_id = int(item["target_id"])
                    depth = expected_total * 1000.0 / areas[target_id]
                    _require(
                        math.isfinite(depth),
                        "fluvial terminal deposition overflowed",
                    )
                    deposition[target_id] += depth
                    _require(
                        math.isfinite(deposition[target_id]),
                        "fluvial terminal deposition accumulation overflowed",
                    )
                    term_counts[target_id] += 1
                stage_volumes[
                    "terminal_land_deposition_volume_km3"
                ] += storage

            for field, expected_count in stage_counts.items():
                _require(
                    _integer(fluvial_record.get(field), f"fluvial.{field}")
                    == expected_count,
                    f"fluvial {field} is invalid",
                )

            fluvial_alluvium_depths = _cell_array(
                fluvial_record,
                "alluvium_entrainment_depth_m_by_cell",
                cell_count=cell_count,
                nonnegative=True,
            )
            fluvial_bedrock_depths = _cell_array(
                fluvial_record,
                "bedrock_erosion_depth_m_by_cell",
                cell_count=cell_count,
                nonnegative=True,
            )
            alluvium_volume = 0.0
            bedrock_volume = 0.0
            for cell_id in range(cell_count):
                alluvium_volume += (
                    fluvial_alluvium_depths[cell_id]
                    * areas[cell_id]
                    / 1000.0
                )
                bedrock_volume += (
                    fluvial_bedrock_depths[cell_id]
                    * areas[cell_id]
                    / 1000.0
                )
            _require(
                math.isfinite(alluvium_volume)
                and math.isfinite(bedrock_volume)
                and all(
                    math.isfinite(value) for value in stage_volumes.values()
                ),
                "fluvial closing aggregate overflowed",
            )
            total_deposition = (
                stage_volumes["capacity_deposition_volume_km3"]
                + stage_volumes["depression_fill_deposition_volume_km3"]
                - terminal_accommodation_volume
                + stage_volumes["lake_trap_deposition_volume_km3"]
                + stage_volumes["terminal_land_deposition_volume_km3"]
                + stage_volumes["marine_deposition_volume_km3"]
            )
            stage_targets = {
                **stage_volumes,
                "alluvium_entrainment_volume_km3": alluvium_volume,
                "bedrock_erosion_volume_km3": bedrock_volume,
                "total_deposition_volume_km3": (
                    stage_volumes["local_source_volume_km3"]
                    - stage_volumes["terminal_export_volume_km3"]
                ),
                "mass_balance_residual_km3": abs(
                    stage_volumes["local_source_volume_km3"]
                    - total_deposition
                    - stage_volumes["terminal_export_volume_km3"]
                ),
            }
            for field, expected_value in stage_targets.items():
                require_close(
                    _nonnegative(fluvial_record.get(field), f"fluvial.{field}"),
                    expected_value,
                    f"fluvial stage {field}",
                    precision=INTERFACE_STATE_DECIMAL_PRECISION,
                    count=cell_count + len(seen_steps) + 8,
                )
            return deposition, term_counts

        def glacial_deposition_depths(
            record: Mapping[str, Any],
        ) -> tuple[list[float], list[int]]:
            deposition = [0.0] * cell_count
            term_counts = [0] * cell_count
            input_by_id: dict[int, Mapping[str, Any]] = {}
            for input_cell in _records(record.get("input_cells"), "glacial.input_cells"):
                source_id = _integer(
                    input_cell.get("cell_id"), "glacial.input_cell_id"
                )
                _require(
                    0 <= source_id < cell_count and source_id not in input_by_id,
                    "glacial input cell IDs are invalid",
                )
                input_by_id[source_id] = input_cell
            for transfer in _records(record.get("transfers"), "glacial.transfers"):
                source_id = _integer(
                    transfer.get("source_cell_id"), "glacial.source_cell_id"
                )
                target_id = _integer(
                    transfer.get("target_cell_id"), "glacial.target_cell_id"
                )
                _require(
                    0 <= source_id < cell_count
                    and 0 <= target_id < cell_count
                    and source_id in input_by_id,
                    "glacial deposition endpoints are invalid",
                )
                _require(
                    _integer(
                        input_by_id[source_id].get("glacier_flow_to_cell_id"),
                        "glacial.glacier_flow_to_cell_id",
                    )
                    == target_id,
                    "glacial transfer disagrees with its source flow target",
                )
                source_area = _nonnegative(
                    transfer.get("source_area_km2"), "glacial.source_area_km2"
                )
                target_area = _nonnegative(
                    transfer.get("target_area_km2"), "glacial.target_area_km2"
                )
                source_depth = _nonnegative(
                    transfer.get("source_production_depth_m"),
                    "glacial.source_production_depth_m",
                )
                emitted_target_depth = _nonnegative(
                    transfer.get("target_deposition_depth_m"),
                    "glacial.target_deposition_depth_m",
                )
                emitted_volume = _nonnegative(
                    transfer.get("transfer_volume_km3"),
                    "glacial.transfer_volume_km3",
                )
                for actual, expected, label in (
                    (source_area, areas[source_id], "glacial source area"),
                    (target_area, areas[target_id], "glacial target area"),
                ):
                    bound = _replay_tolerance(
                        actual=actual,
                        expected=expected,
                        operand_sum=abs(actual) + abs(expected),
                        operation_count=2,
                        output_precision=10,
                    )
                    _require(abs(actual - expected) <= bound, f"{label} is invalid")
                expected_volume = source_depth * areas[source_id] / 1000.0
                expected_target_depth = (
                    expected_volume * 1000.0 / areas[target_id]
                )
                for actual, expected, label, precision in (
                    (
                        emitted_volume,
                        expected_volume,
                        "glacial transfer volume",
                        10,
                    ),
                    (
                        emitted_target_depth,
                        expected_target_depth,
                        "glacial target deposition depth",
                        INTERFACE_REPLAY_INPUT_DECIMAL_PRECISION,
                    ),
                ):
                    bound = _replay_tolerance(
                        actual=actual,
                        expected=expected,
                        operand_sum=(
                            abs(source_depth)
                            + abs(areas[source_id])
                            + abs(areas[target_id])
                        ),
                        operation_count=4,
                        output_precision=precision,
                    )
                    _require(abs(actual - expected) <= bound, f"{label} is invalid")
                deposition[target_id] += expected_target_depth
                _require(
                    math.isfinite(deposition[target_id]),
                    "glacial deposition accumulation overflowed",
                )
                term_counts[target_id] += 1
            return deposition, term_counts

        for feedback_id, record in enumerate(feedback):
            stage = record.get("stage")
            _require(type(stage) is str, "feedback stage must be a string")
            if stage == "initial_climate_hydrology":
                _require(feedback_id == 0, "initial feedback stage is misplaced")
            elif stage == "erosion_iteration":
                erosion_stage_count += 1
                motion_id = _integer(
                    record.get("plate_motion_history_id"),
                    "feedback.plate_motion_history_id",
                )
                _require(motion_id in plate_by_id, "plate motion link is invalid")
                displacement = _cell_array(
                    plate_by_id[motion_id],
                    "tectonic_elevation_change_m_by_cell",
                    cell_count=cell_count,
                )
                expected_motion_statistics = {
                    "mean_tectonic_elevation_change_m": (
                        math.fsum(displacement) / cell_count
                    ),
                    "mean_abs_tectonic_elevation_change_m": (
                        math.fsum(abs(value) for value in displacement)
                        / cell_count
                    ),
                    "max_abs_tectonic_elevation_change_m": max(
                        (abs(value) for value in displacement), default=0.0
                    ),
                }
                for field, expected_statistic in (
                    expected_motion_statistics.items()
                ):
                    actual_statistic = _finite(
                        plate_by_id[motion_id].get(field), f"plate_motion.{field}"
                    )
                    statistic_bound = _replay_tolerance(
                        actual=actual_statistic,
                        expected=expected_statistic,
                        operand_sum=math.fsum(
                            abs(value) for value in displacement
                        ),
                        operation_count=cell_count + 1,
                        output_precision=INTERFACE_STATE_DECIMAL_PRECISION,
                    )
                    _require(
                        abs(actual_statistic - expected_statistic)
                        <= statistic_bound,
                        f"plate motion {field} does not replay",
                    )
                for cell_id, value in enumerate(displacement):
                    bedrock[cell_id] += value
                    cumulative_tectonic[cell_id] += value
                    operand_sums[cell_id] += abs(value)
                    operation_counts[cell_id] += 1
                    _require(
                        math.isfinite(bedrock[cell_id])
                        and math.isfinite(cumulative_tectonic[cell_id])
                        and math.isfinite(operand_sums[cell_id]),
                        "tectonic bedrock replay overflowed",
                    )
                _require(
                    feedback_id in hillslope and feedback_id in fluvial,
                    "erosion stage sediment history links are incomplete",
                )
                validate_mobile_snapshot(
                    hillslope[feedback_id], "hillslope"
                )
                hillslope_alluvium = _cell_array(
                    hillslope[feedback_id],
                    "alluvium_entrainment_depth_m_by_cell",
                    cell_count=cell_count,
                    nonnegative=True,
                )
                fluvial_alluvium = _cell_array(
                    fluvial[feedback_id],
                    "alluvium_entrainment_depth_m_by_cell",
                    cell_count=cell_count,
                    nonnegative=True,
                )
                erosion_deposition, deposition_term_counts = (
                    erosion_deposition_depths(
                        hillslope[feedback_id], fluvial[feedback_id]
                    )
                )
                apply_mobile_stage(
                    [
                        hillslope_alluvium[cell_id]
                        + fluvial_alluvium[cell_id]
                        for cell_id in range(cell_count)
                    ],
                    erosion_deposition,
                    deposition_term_counts,
                    "hillslope/fluvial",
                )
                apply_bedrock_depths(
                    hillslope[feedback_id], "bedrock_erosion_depth_m_by_cell"
                )
                apply_bedrock_depths(
                    fluvial[feedback_id], "bedrock_erosion_depth_m_by_cell"
                )
                consumed_hillslope.add(feedback_id)
                consumed_fluvial.add(feedback_id)
            elif stage == "cryosphere_coupling":
                glacial_stage_count += 1
                _require(
                    feedback_id in glacial,
                    "cryosphere stage glacial history link is incomplete",
                )
                validate_mobile_snapshot(glacial[feedback_id], "glacial")
                glacial_alluvium = _cell_array(
                    glacial[feedback_id],
                    "alluvium_entrainment_depth_m_by_cell",
                    cell_count=cell_count,
                    nonnegative=True,
                )
                glacial_deposition, deposition_term_counts = (
                    glacial_deposition_depths(glacial[feedback_id])
                )
                apply_mobile_stage(
                    glacial_alluvium,
                    glacial_deposition,
                    deposition_term_counts,
                    "glacial",
                )
                apply_bedrock_depths(
                    glacial[feedback_id], "bedrock_erosion_depth_m_by_cell"
                )
                consumed_glacial.add(feedback_id)
            else:
                raise _InvalidInterface(f"unknown feedback stage {stage!r}")

            datum_shift = _finite(
                record.get("sea_level_adjustment_m"),
                "feedback.sea_level_adjustment_m",
            )
            for cell_id in range(cell_count):
                bedrock[cell_id] -= datum_shift
                operand_sums[cell_id] += abs(datum_shift)
                operation_counts[cell_id] += 1
                _require(
                    math.isfinite(bedrock[cell_id])
                    and math.isfinite(operand_sums[cell_id]),
                    "sea-level bedrock replay overflowed",
                )

            for event in numeric_by_feedback.get(feedback_id, []):
                method = event.get("selected_correction_method")
                _require(
                    method in {
                        "mass_conserving_breach",
                        "temporary_numeric_lake",
                    },
                    "numeric correction method is invalid",
                )
                event_cell_ids = event.get("cell_ids")
                event_mobile_before = event.get(
                    "sediment_thickness_before_correction_m_by_cell"
                )
                _require(
                    isinstance(event_cell_ids, list)
                    and isinstance(event_mobile_before, list)
                    and len(event_cell_ids) == len(event_mobile_before),
                    "numeric component mobile snapshot is malformed",
                )
                component_mobile_before: dict[int, float] = {}
                for raw_cell_id, raw_mobile in zip(
                    event_cell_ids, event_mobile_before, strict=True
                ):
                    cell_id = _integer(raw_cell_id, "numeric.cell_id")
                    _require(
                        0 <= cell_id < cell_count
                        and cell_id not in component_mobile_before,
                        "numeric component cell ID is invalid",
                    )
                    actual_mobile = _nonnegative(
                        raw_mobile,
                        "numeric.sediment_thickness_before_correction_m_by_cell",
                    )
                    snapshot_bound = _replay_tolerance(
                        actual=actual_mobile,
                        expected=mobile[cell_id],
                        operand_sum=mobile_operand_sums[cell_id],
                        operation_count=mobile_operation_counts[cell_id],
                        output_precision=(
                            INTERFACE_REPLAY_INPUT_DECIMAL_PRECISION
                        ),
                    )
                    _require(
                        abs(actual_mobile - mobile[cell_id]) <= snapshot_bound,
                        "numeric component mobile snapshot does not replay",
                    )
                    component_mobile_before[cell_id] = actual_mobile
                if method != "mass_conserving_breach":
                    continue
                selected_numeric_breach_count += 1
                cell_ids = event.get("breach_path_cell_ids")
                depths = event.get("breach_bedrock_erosion_depth_m_by_cell")
                excavation_depths = event.get(
                    "breach_excavation_depth_m_by_cell"
                )
                elevations_before = event.get(
                    "breach_elevation_before_m_by_cell"
                )
                target_elevations = event.get(
                    "breach_target_elevation_m_by_cell"
                )
                path_mobile_before = event.get(
                    "breach_sediment_thickness_before_excavation_m_by_cell"
                )
                alluvium_depths = event.get(
                    "breach_alluvium_entrainment_depth_m_by_cell"
                )
                _require(
                    isinstance(cell_ids, list)
                    and isinstance(depths, list)
                    and isinstance(excavation_depths, list)
                    and isinstance(elevations_before, list)
                    and isinstance(target_elevations, list)
                    and isinstance(path_mobile_before, list)
                    and isinstance(alluvium_depths, list)
                    and len(cell_ids) == len(depths)
                    == len(excavation_depths)
                    == len(elevations_before)
                    == len(target_elevations)
                    == len(path_mobile_before)
                    == len(alluvium_depths),
                    "numeric breach bedrock arrays are malformed",
                )
                mobile_source = [0.0] * cell_count
                mobile_deposition = [0.0] * cell_count
                mobile_deposition_term_counts = [0] * cell_count
                seen_path_ids: set[int] = set()
                excavated_path_ids: set[int] = set()
                event_excavation_volume = 0.0
                event_alluvium_volume = 0.0
                event_bedrock_volume = 0.0
                for (
                    raw_cell_id,
                    raw_depth,
                    raw_excavation,
                    raw_elevation_before,
                    raw_target_elevation,
                    raw_mobile_before,
                    raw_alluvium,
                ) in zip(
                    cell_ids,
                    depths,
                    excavation_depths,
                    elevations_before,
                    target_elevations,
                    path_mobile_before,
                    alluvium_depths,
                    strict=True,
                ):
                    cell_id = _integer(raw_cell_id, "breach_path_cell_id")
                    _require(
                        0 <= cell_id < cell_count
                        and cell_id not in seen_path_ids,
                        "numeric breach cell ID is invalid",
                    )
                    seen_path_ids.add(cell_id)
                    actual_mobile = _nonnegative(
                        raw_mobile_before,
                        "breach_sediment_thickness_before_excavation_m_by_cell",
                    )
                    snapshot_bound = _replay_tolerance(
                        actual=actual_mobile,
                        expected=mobile[cell_id],
                        operand_sum=mobile_operand_sums[cell_id],
                        operation_count=mobile_operation_counts[cell_id],
                        output_precision=(
                            INTERFACE_REPLAY_INPUT_DECIMAL_PRECISION
                        ),
                    )
                    _require(
                        abs(actual_mobile - mobile[cell_id]) <= snapshot_bound,
                        "numeric breach path mobile snapshot does not replay",
                    )
                    emitted_alluvium = _nonnegative(
                        raw_alluvium,
                        "breach_alluvium_entrainment_depth_m_by_cell",
                    )
                    emitted_bedrock = _nonnegative(
                        raw_depth, "breach_bedrock_erosion_depth_m_by_cell"
                    )
                    excavation = _nonnegative(
                        raw_excavation, "breach_excavation_depth_m_by_cell"
                    )
                    elevation_before = _finite(
                        raw_elevation_before,
                        "breach_elevation_before_m_by_cell",
                    )
                    target_elevation = _finite(
                        raw_target_elevation,
                        "breach_target_elevation_m_by_cell",
                    )
                    expected_excavation = max(
                        0.0, elevation_before - target_elevation
                    )
                    if (
                        expected_excavation
                        > NUMERIC_DEPRESSION_DEPTH_TOLERANCE_M
                    ):
                        excavated_path_ids.add(cell_id)
                    excavation_bound = _replay_tolerance(
                        actual=excavation,
                        expected=expected_excavation,
                        operand_sum=(
                            abs(elevation_before) + abs(target_elevation)
                        ),
                        operation_count=3,
                        output_precision=10,
                    )
                    _require(
                        abs(excavation - expected_excavation)
                        <= excavation_bound,
                        "numeric breach excavation geometry is invalid",
                    )
                    expected_alluvium = min(
                        mobile[cell_id], expected_excavation
                    )
                    expected_bedrock = max(
                        0.0, expected_excavation - expected_alluvium
                    )
                    for actual, expected, label in (
                        (
                            emitted_alluvium,
                            expected_alluvium,
                            "numeric breach alluvium partition",
                        ),
                        (
                            emitted_bedrock,
                            expected_bedrock,
                            "numeric breach bedrock partition",
                        ),
                    ):
                        partition_bound = _replay_tolerance(
                            actual=actual,
                            expected=expected,
                            operand_sum=(
                                abs(expected_excavation)
                                + abs(mobile[cell_id])
                            ),
                            operation_count=4,
                            output_precision=10,
                        )
                        _require(
                            abs(actual - expected) <= partition_bound,
                            f"{label} is invalid",
                        )
                    mobile_source[cell_id] = expected_alluvium
                    bedrock[cell_id] -= expected_bedrock
                    operand_sums[cell_id] += abs(expected_bedrock)
                    operation_counts[cell_id] += 1
                    _require(
                        math.isfinite(bedrock[cell_id])
                        and math.isfinite(operand_sums[cell_id]),
                        "numeric bedrock replay overflowed",
                    )
                    event_excavation_volume += (
                        expected_excavation * areas[cell_id] / 1000.0
                    )
                    event_alluvium_volume += (
                        expected_alluvium * areas[cell_id] / 1000.0
                    )
                    event_bedrock_volume += (
                        expected_bedrock * areas[cell_id] / 1000.0
                    )

                deposition_cell_ids = event.get("breach_deposition_cell_ids")
                deposition_depths = event.get(
                    "breach_deposition_depth_m_by_cell"
                )
                fill_depths = event.get("fill_depth_m_by_cell")
                _require(
                    isinstance(deposition_cell_ids, list)
                    and isinstance(deposition_depths, list)
                    and isinstance(fill_depths, list)
                    and len(deposition_cell_ids) == len(deposition_depths),
                    "numeric breach deposition arrays are malformed",
                )
                _require(
                    len(fill_depths) == len(event_cell_ids),
                    "numeric breach fill-capacity array is malformed",
                )

                deposition_candidates: list[tuple[int, float]] = []
                total_deposition_capacity = 0.0
                for raw_cell_id, raw_fill_depth in zip(
                    event_cell_ids, fill_depths, strict=True
                ):
                    cell_id = _integer(
                        raw_cell_id, "numeric deposition candidate cell ID"
                    )
                    fill_depth = _nonnegative(
                        raw_fill_depth, "numeric fill_depth_m_by_cell"
                    )
                    if cell_id in excavated_path_ids:
                        continue
                    usable_depth = min(
                        fill_depth,
                        max(
                            0.0,
                            NUMERIC_DEPRESSION_MAX_MOBILE_SEDIMENT_M
                            - mobile[cell_id],
                        ),
                    )
                    if (
                        usable_depth
                        <= NUMERIC_DEPRESSION_DEPTH_TOLERANCE_M
                    ):
                        continue
                    capacity_volume = (
                        usable_depth * areas[cell_id] / 1000.0
                    )
                    _require(
                        math.isfinite(capacity_volume),
                        "numeric deposition capacity overflowed",
                    )
                    deposition_candidates.append((cell_id, capacity_volume))
                    total_deposition_capacity += capacity_volume
                    _require(
                        math.isfinite(total_deposition_capacity),
                        "numeric total deposition capacity overflowed",
                    )
                _require(
                    total_deposition_capacity + 1.0e-9
                    >= event_excavation_volume,
                    "selected numeric breach lacks deposition capacity",
                )

                expected_deposition: list[tuple[int, float, float]] = []
                remaining_deposition_volume = event_excavation_volume
                for candidate_index, (
                    cell_id,
                    capacity_volume,
                ) in enumerate(deposition_candidates):
                    proportional_volume = (
                        event_excavation_volume
                        * capacity_volume
                        / total_deposition_capacity
                        if total_deposition_capacity > 0.0
                        else 0.0
                    )
                    last_candidate = (
                        candidate_index + 1 == len(deposition_candidates)
                    )
                    deposition_volume = min(
                        capacity_volume,
                        remaining_deposition_volume
                        if last_candidate
                        else min(
                            remaining_deposition_volume,
                            proportional_volume,
                        ),
                    )
                    if deposition_volume <= 1.0e-12:
                        continue
                    deposition_depth = (
                        deposition_volume * 1000.0 / areas[cell_id]
                    )
                    _require(
                        math.isfinite(deposition_depth),
                        "numeric deposition depth overflowed",
                    )
                    expected_deposition.append(
                        (cell_id, deposition_depth, deposition_volume)
                    )
                    remaining_deposition_volume = max(
                        0.0,
                        remaining_deposition_volume - deposition_volume,
                    )
                _require(
                    remaining_deposition_volume <= 1.0e-7,
                    "numeric breach deposition capacity was not realized",
                )
                _require(
                    _integer(
                        event.get("breach_deposition_cell_count"),
                        "numeric breach_deposition_cell_count",
                    )
                    == len(expected_deposition)
                    == len(deposition_cell_ids),
                    "numeric breach deposition count is invalid",
                )

                event_deposition_volume = 0.0
                for (
                    raw_cell_id,
                    raw_depth,
                    (expected_cell_id, expected_depth, expected_volume),
                ) in zip(
                    deposition_cell_ids,
                    deposition_depths,
                    expected_deposition,
                    strict=True,
                ):
                    cell_id = _integer(
                        raw_cell_id, "breach_deposition_cell_id"
                    )
                    _require(
                        cell_id == expected_cell_id,
                        "numeric breach deposition order or cell is invalid",
                    )
                    emitted_depth = _nonnegative(
                        raw_depth, "breach_deposition_depth_m_by_cell"
                    )
                    depth_bound = _replay_tolerance(
                        actual=emitted_depth,
                        expected=expected_depth,
                        operand_sum=(
                            abs(expected_depth)
                            + abs(expected_volume)
                            + abs(total_deposition_capacity)
                        ),
                        operation_count=len(deposition_candidates) + 8,
                        output_precision=12,
                    )
                    _require(
                        abs(emitted_depth - expected_depth) <= depth_bound,
                        "numeric breach deposition depth is invalid",
                    )
                    mobile_deposition[cell_id] += expected_depth
                    _require(
                        math.isfinite(mobile_deposition[cell_id]),
                        "numeric deposition accumulation overflowed",
                    )
                    mobile_deposition_term_counts[cell_id] += 1
                    event_deposition_volume += expected_volume
                event_targets = {
                    "breach_deposition_capacity_km3": (
                        total_deposition_capacity
                    ),
                    "applied_breach_excavation_volume_km3": (
                        event_excavation_volume
                    ),
                    "applied_alluvium_entrainment_volume_km3": (
                        event_alluvium_volume
                    ),
                    "applied_bedrock_erosion_volume_km3": (
                        event_bedrock_volume
                    ),
                    "applied_breach_deposition_volume_km3": (
                        event_deposition_volume
                    ),
                    "correction_mass_balance_residual_km3": abs(
                        event_excavation_volume - event_deposition_volume
                    ),
                }
                for field, expected in event_targets.items():
                    actual = _nonnegative(event.get(field), f"numeric.{field}")
                    event_bound = _replay_tolerance(
                        actual=actual,
                        expected=expected,
                        operand_sum=(
                            event_excavation_volume
                            + event_alluvium_volume
                            + event_bedrock_volume
                            + event_deposition_volume
                        ),
                        operation_count=(
                            len(cell_ids) + len(deposition_cell_ids) + 4
                        ),
                        output_precision=10,
                    )
                    _require(
                        abs(actual - expected) <= event_bound,
                        f"numeric {field} is invalid",
                    )
                apply_mobile_stage(
                    mobile_source,
                    mobile_deposition,
                    mobile_deposition_term_counts,
                    "numeric breach",
                )

        _require(
            consumed_hillslope == set(hillslope),
            "unlinked hillslope interface stages are present",
        )
        _require(
            consumed_fluvial == set(fluvial),
            "unlinked fluvial interface stages are present",
        )
        _require(
            consumed_glacial == set(glacial),
            "unlinked glacial interface stages are present",
        )

        maximum_replay_residual = 0.0
        maximum_mobile_replay_residual = 0.0
        maximum_tectonic_cumulative_residual = 0.0
        maximum_closure_residual = 0.0
        for cell_id in range(cell_count):
            replay_residual = abs(final_bedrock[cell_id] - bedrock[cell_id])
            replay_bound = _replay_tolerance(
                actual=final_bedrock[cell_id],
                expected=bedrock[cell_id],
                operand_sum=operand_sums[cell_id],
                operation_count=operation_counts[cell_id],
                output_precision=INTERFACE_REPLAY_INPUT_DECIMAL_PRECISION,
            )
            _require(
                replay_residual <= replay_bound,
                f"cell {cell_id} bedrock surface does not replay",
            )
            mobile_replay_residual = abs(
                final_mobile[cell_id] - mobile[cell_id]
            )
            mobile_replay_bound = _replay_tolerance(
                actual=final_mobile[cell_id],
                expected=mobile[cell_id],
                operand_sum=mobile_operand_sums[cell_id],
                operation_count=mobile_operation_counts[cell_id],
                output_precision=INTERFACE_REPLAY_INPUT_DECIMAL_PRECISION,
            )
            _require(
                mobile_replay_residual <= mobile_replay_bound,
                f"cell {cell_id} mobile sediment does not replay",
            )
            tectonic_cumulative_residual = abs(
                final_cumulative_tectonic[cell_id]
                - cumulative_tectonic[cell_id]
            )
            tectonic_cumulative_bound = _replay_tolerance(
                actual=final_cumulative_tectonic[cell_id],
                expected=cumulative_tectonic[cell_id],
                operand_sum=abs(cumulative_tectonic[cell_id]),
                operation_count=erosion_stage_count + 2,
                output_precision=INTERFACE_STATE_DECIMAL_PRECISION,
            )
            _require(
                tectonic_cumulative_residual <= tectonic_cumulative_bound,
                f"cell {cell_id} cumulative tectonic displacement does not replay",
            )
            closure_residual = abs(
                final_surface[cell_id]
                - final_bedrock[cell_id]
                - final_mobile[cell_id]
            )
            closure_bound = _replay_tolerance(
                actual=final_surface[cell_id],
                expected=final_bedrock[cell_id] + final_mobile[cell_id],
                operand_sum=(
                    abs(final_surface[cell_id])
                    + abs(final_bedrock[cell_id])
                    + final_mobile[cell_id]
                ),
                operation_count=3,
                output_precision=INTERFACE_STATE_DECIMAL_PRECISION,
            )
            _require(
                closure_residual <= closure_bound,
                f"cell {cell_id} surface/interface closure is invalid",
            )
            maximum_replay_residual = max(
                maximum_replay_residual, replay_residual
            )
            maximum_mobile_replay_residual = max(
                maximum_mobile_replay_residual,
                mobile_replay_residual,
            )
            maximum_tectonic_cumulative_residual = max(
                maximum_tectonic_cumulative_residual,
                tectonic_cumulative_residual,
            )
            maximum_closure_residual = max(
                maximum_closure_residual, closure_residual
            )

        native_maximum = _nonnegative(
            model.get("maximum_final_closure_residual_m"),
            "model.maximum_final_closure_residual_m",
        )
        model_bound = _replay_tolerance(
            actual=native_maximum,
            expected=maximum_closure_residual,
            operand_sum=native_maximum + maximum_closure_residual,
            # A maximum selects one already-quantized cell residual; it does
            # not accumulate one rounding error per cell.
            operation_count=4,
            output_precision=INTERFACE_STATE_DECIMAL_PRECISION,
        )
        _require(
            abs(native_maximum - maximum_closure_residual) <= model_bound,
            "native maximum interface closure residual is invalid",
        )

        metrics.update(
            {
                "cell_count": cell_count,
                "feedback_stage_count": len(feedback),
                "erosion_stage_count": erosion_stage_count,
                "glacial_stage_count": glacial_stage_count,
                "selected_numeric_breach_count": (
                    selected_numeric_breach_count
                ),
                "maximum_bedrock_replay_residual_m": (
                    maximum_replay_residual
                ),
                "maximum_mobile_sediment_replay_residual_m": (
                    maximum_mobile_replay_residual
                ),
                "maximum_tectonic_cumulative_residual_m": (
                    maximum_tectonic_cumulative_residual
                ),
                "maximum_surface_closure_residual_m": (
                    maximum_closure_residual
                ),
                "authoritative_interface_geometry": True,
                "all_native_sediment_mutation_paths_replayed": True,
                "dry_rock_mass_resolved": False,
                "porosity_resolved": False,
                "grain_provenance_resolved": False,
            }
        )
    except (
        KeyError,
        TypeError,
        ValueError,
        OverflowError,
        ArithmeticError,
    ) as error:
        failures.append(str(error) or type(error).__name__)

    return {
        "passed": not failures,
        "failures": failures,
        "metrics": metrics,
    }


__all__ = [
    "MODEL_LITERAL_VALUES",
    "validate_sediment_interfaces",
]
