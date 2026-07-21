from __future__ import annotations

import math
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


MODEL_TYPE = "exact_directed_reciprocal_control_volume_boundary_segments_v2"
BOUNDARY_CLASS_NAMES = frozenset(
    {"inactive", "convergent", "divergent", "transform"}
)
POLARITY_STATUS_NAMES = frozenset(
    {
        "no_active_convergence",
        "unresolved_missing_opening_crust_state",
        "left_oceanic_only",
        "right_oceanic_only",
        "ambiguous_both_oceanic",
        "unresolved_no_oceanic_side",
    }
)
PHYSICAL_POLARITY_STATUS_NAMES = frozenset(
    {"not_applicable_no_active_convergence", "unknown_unresolved"}
)
BOUNDARY_SIDE_NAMES = frozenset({"left", "right", "none"})
PHYSICAL_BOUNDARY_SIDE_NAMES = frozenset(
    {"left", "right", "none", "unknown"}
)
MATURATION_REFERENCE_TIMESTEP_MA = 5.0
RECIPROCAL_ENDPOINT_TOLERANCE = 1.0e-10
UNIT_SPHERE_VECTOR_NORM_TOLERANCE = 3.0e-12

INTEGER_RECORD_FIELDS = frozenset(
    {
        "segment_id",
        "mesh_segment_id",
        "left_cell_id",
        "right_cell_id",
        "left_edge_index",
        "right_edge_index",
        "left_plate_id",
        "right_plate_id",
        "left_opening_crust_type",
        "left_opening_lithology",
        "right_opening_crust_type",
        "right_opening_lithology",
    }
)
FLOAT_RECORD_FIELDS = frozenset(
    {
        "start_unit_x",
        "start_unit_y",
        "start_unit_z",
        "midpoint_unit_x",
        "midpoint_unit_y",
        "midpoint_unit_z",
        "end_unit_x",
        "end_unit_y",
        "end_unit_z",
        "tangent_unit_x",
        "tangent_unit_y",
        "tangent_unit_z",
        "left_to_right_normal_unit_x",
        "left_to_right_normal_unit_y",
        "left_to_right_normal_unit_z",
        "angular_length_rad",
        "length_km",
        "left_euler_velocity_x_km_per_ma",
        "left_euler_velocity_y_km_per_ma",
        "left_euler_velocity_z_km_per_ma",
        "right_euler_velocity_x_km_per_ma",
        "right_euler_velocity_y_km_per_ma",
        "right_euler_velocity_z_km_per_ma",
        "relative_velocity_x_km_per_ma",
        "relative_velocity_y_km_per_ma",
        "relative_velocity_z_km_per_ma",
        "signed_opening_rate_km_per_ma",
        "signed_convergence_rate_km_per_ma",
        "signed_slip_rate_km_per_ma",
        "signed_opening_index",
        "signed_convergence_index",
        "signed_slip_index",
        "direct_convergent_strength",
        "direct_divergent_strength",
        "direct_transform_strength",
        "left_opening_crust_age_ma",
        "left_opening_crust_thickness_km",
        "left_opening_crust_density_g_cm3",
        "right_opening_crust_age_ma",
        "right_opening_crust_thickness_km",
        "right_opening_crust_density_g_cm3",
        "physical_polarity_confidence",
    }
)
BOOLEAN_RECORD_FIELDS = frozenset(
    {
        "left_opening_crust_state_available",
        "left_opening_oceanic_like",
        "right_opening_crust_state_available",
        "right_opening_oceanic_like",
        "convergence_active",
    }
)
STRING_RECORD_FIELDS = frozenset(
    {
        "direct_boundary_class",
        "polarity_candidate_status",
        "candidate_subducting_side",
        "candidate_overriding_side",
        "physical_polarity_status",
        "physical_polarity_source",
        "physical_subducting_side",
        "physical_overriding_side",
    }
)
RECORD_FIELDS = (
    INTEGER_RECORD_FIELDS
    | FLOAT_RECORD_FIELDS
    | BOOLEAN_RECORD_FIELDS
    | STRING_RECORD_FIELDS
)

MODEL_STRING_VALUES: dict[str, str] = {
    "model_type": MODEL_TYPE,
    "ledger_location": "plate_motion_history[].boundary_segments",
    "record_layout": "flat_record_array_v2",
    "canonical_side_rule": "lower_cell_id_is_left_side",
    "canonical_direction_rule": (
        "left_cell_counter_clockwise_control_volume_edge_start_to_end"
    ),
    "record_order": (
        "left_cell_id_then_left_edge_index_filtered_to_cross_plate_segments"
    ),
    "segment_selection": (
        "one_record_per_cross_plate_reciprocal_control_volume_segment"
    ),
    "mesh_segment_id_semantics": (
        "stable_index_over_all_reciprocal_mesh_segments_in_left_cell_id_then_left_edge_index_order"
    ),
    "segment_id_semantics": (
        "zero_based_contiguous_index_within_each_steps_cross_plate_ledger"
    ),
    "geometry_source": (
        "canonical_spherical_control_volume_vertices_and_reciprocal_edge_neighbor_ids"
    ),
    "segment_curve": "shorter_great_circle_arc",
    "position_unit": "unit_sphere_cartesian",
    "angular_length_unit": "rad",
    "length_unit": "km",
    "velocity_unit": "km_per_Ma_nominal",
    "intrinsic_kinematic_index_unit": (
        "unit_sphere_tangent_velocity_per_intrinsic_angular_speed_unit"
    ),
    "opening_crust_age_unit": "Ma",
    "opening_crust_thickness_unit": "km",
    "opening_crust_density_unit": "g_cm3",
    "reciprocal_mesh_segment_count_cap_formula": (
        "reciprocal_mesh_segment_count_le_8_times_cell_count"
    ),
    "operational_cap_semantics": (
        "nonphysical_fail_closed_resource_and_malformed_geometry_guards"
    ),
    "nominal_velocity_scale_formula": (
        "radius_km*reference_motion_scale_deg_per_reference_step*(pi/180)/reference_timestep_ma"
    ),
    "intrinsic_euler_velocity_formula": (
        "cross(rotation_axis*intrinsic_angular_speed,segment_midpoint_unit)"
    ),
    "intrinsic_angular_speed_snapshot_semantics": (
        "constant_per_plate_across_all_history_steps_including_initial_snapshot"
    ),
    "intrinsic_angular_speed_top_level_cross_check": (
        "plate_motion_history[].plates[].intrinsic_angular_speed_equals_plates[].angular_speed_by_plate_id"
    ),
    "rotation_axis_snapshot_semantics": (
        "constant_per_plate_across_all_history_steps_including_initial_snapshot"
    ),
    "rotation_axis_top_level_cross_check": (
        "plate_motion_history[].plates[].rotation_axis_equals_plates[].axis_by_plate_id"
    ),
    "initial_snapshot_step_rotation_semantics": (
        "zero_state_snapshot_rotation_with_nonzero_intrinsic_angular_speed_allowed"
    ),
    "noninitial_step_rotation_formula": (
        "intrinsic_angular_speed*reference_motion_scale_deg_per_reference_step*maturation_timestep_scale"
    ),
    "assignment_center_snapshot_semantics": (
        "authoritative_root_operand_for_same_step_cell_plate_ids"
    ),
    "cell_plate_assignment_formula": (
        "argmax_dot_cell_position_3d_and_same_step_plate_snapshot_center"
    ),
    "cell_plate_assignment_tie_break": (
        "plate_id_ascending_with_strict_greater_than_update_exact_tie_keeps_lowest_plate_id"
    ),
    "cell_plate_ids_semantics": (
        "derived_from_cell_position_3d_and_same_step_authoritative_plate_snapshot_centers"
    ),
    "boundary_segment_plate_id_semantics": (
        "derived_from_same_step_cell_plate_ids_at_left_and_right_cell_ids"
    ),
    "initial_center_top_level_cross_check": (
        "plate_motion_history_step_0_plate_center_equals_plates_initial_center_by_plate_id"
    ),
    "center_transition_formula": (
        "normalize_rodrigues_rotate_previous_center_about_rotation_axis_by_step_rotation_deg_times_pi_over_180"
    ),
    "final_center_top_level_cross_check": (
        "last_plate_motion_history_plate_center_equals_plates_center_by_plate_id"
    ),
    "nominal_euler_velocity_formula": (
        "intrinsic_euler_velocity*nominal_velocity_scale_km_per_ma"
    ),
    "relative_velocity_formula": "right_euler_velocity-left_euler_velocity",
    "signed_opening_rate_formula": (
        "dot(relative_velocity_km_per_ma,left_to_right_normal_unit)"
    ),
    "signed_convergence_rate_formula": "-signed_opening_rate_km_per_ma",
    "signed_slip_rate_formula": (
        "dot(relative_velocity_km_per_ma,tangent_unit)"
    ),
    "signed_opening_index_formula": (
        "dot(right_intrinsic_euler_velocity-left_intrinsic_euler_velocity,left_to_right_normal_unit)"
    ),
    "signed_convergence_index_formula": "-signed_opening_index",
    "signed_slip_index_formula": (
        "dot(right_intrinsic_euler_velocity-left_intrinsic_euler_velocity,tangent_unit)"
    ),
    "direct_convergent_strength_formula": (
        "clamp(signed_convergence_index*1.25,0,1)"
    ),
    "direct_divergent_strength_formula": (
        "clamp(signed_opening_index*1.25,0,1)"
    ),
    "direct_transform_strength_formula": (
        "clamp((abs(signed_slip_index)-abs(signed_opening_index)*0.35)*1.05,0,1)"
    ),
    "direct_boundary_class_rule": (
        "inactive_if_max_strength_lt_0.08_else_max_strength"
    ),
    "direct_boundary_class_tie_break": (
        "convergent_then_divergent_then_transform"
    ),
    "polarity_convergence_applicability_rule": (
        "direct_convergent_strength_ge_0_08_independent_of_winning_boundary_class"
    ),
    "opening_crust_state_source": (
        "same_step_crust_overlap_ledger_remapped_pre_process_state"
    ),
    "opening_crust_state_availability_rule": (
        "unavailable_iff_age_ma_and_thickness_km_are_both_zero_density_always_positive_available_states_require_positive_thickness"
    ),
    "unavailable_opening_crust_sentinel_semantics": (
        "retained_categorical_and_density_values_are_fixed_shape_unavailable_state_sentinels_not_material_state"
    ),
    "opening_oceanic_like_predicate": (
        "crust_type_0_or_crust_type_2_with_lithology_0_or_crust_type_3_with_age_le_320_ma_thickness_le_18_km_density_ge_2_84_g_cm3"
    ),
    "opening_oceanic_like_evaluation_scope": (
        "available_opening_crust_states_only_unavailable_states_are_false"
    ),
    "candidate_subducting_side_mapping": (
        "left_oceanic_only_to_left_right_oceanic_only_to_right_all_other_statuses_to_none"
    ),
    "candidate_overriding_side_mapping": (
        "left_oceanic_only_to_right_right_oceanic_only_to_left_all_other_statuses_to_none"
    ),
    "candidate_side_semantics": (
        "oceanic_side_heuristic_is_subducting_candidate_and_opposite_side_is_overriding_candidate_not_physical_polarity"
    ),
    "physical_polarity_status_rule": (
        "active_convergence_unknown_unresolved_else_not_applicable_no_active_convergence"
    ),
    "physical_polarity_source_rule": (
        "none_until_supplied_constraint_or_physical_solver_is_implemented"
    ),
    "gpgim_supplied_polarity_convention": (
        "align_supplied_feature_direction_to_canonical_segment_then_left_or_right_names_overriding_side_and_opposite_names_subducting_side"
    ),
    "model_limitation": (
        "kinematic_candidate_evidence_only_without_physical_polarity_slab_geometry_material_fate_or_feedback_into_smoothed_cell_boundary_forcing"
    ),
}
MODEL_FLOAT_FIELDS = frozenset(
    {
        "reciprocal_endpoint_match_tolerance_chord",
        "radius_km",
        "reference_motion_scale_deg_per_reference_step",
        "reference_timestep_ma",
        "nominal_velocity_scale_km_per_ma",
        "direct_boundary_class_inactive_threshold",
        "euler_axis_unit_tolerance",
        "unit_sphere_vector_norm_tolerance",
    }
)
MODEL_INTEGER_FIELDS = frozenset(
    {
        "history_step_count",
        "total_boundary_segment_count",
        "maximum_boundary_segment_count",
        "reciprocal_mesh_segment_count",
        "serialized_float_decimal_significant_digits",
        "maximum_control_volume_segments_per_cell",
        "maximum_reciprocal_mesh_segment_count_multiplier",
        "intrinsic_angular_speed_serialized_significant_digits",
        "rotation_axis_serialized_significant_digits",
        "assignment_center_serialized_significant_digits",
        "top_level_plate_center_serialized_significant_digits",
    }
)
MODEL_BOOLEAN_VALUES: dict[str, bool] = {
    "authoritative_for_segment_geometry": True,
    "authoritative_for_direct_unsmoothed_kinematics": True,
    "reciprocal_segment_identity_resolved": True,
    "opening_remapped_crust_state_recorded": True,
    "smoothed_cell_boundary_forcing_active": True,
    "boundary_segments_drive_smoothed_cell_boundary_forcing": False,
    "nominal_time_calibrated": False,
    "physical_time_resolved": False,
    "physical_plate_velocity_calibrated": False,
    "physical_polarity_unknown_state_explicit": True,
    "polarity_candidate_is_physical_decision": False,
    "physical_subduction_polarity_resolved": False,
    "physical_slab_geometry_resolved": False,
    "slab_selection_resolved": False,
    "slab_transfer_resolved": False,
    "physical_material_fate_resolved": False,
    "boundary_segments_drive_slab_transfers": False,
}
MODEL_FIELDS = frozenset(MODEL_STRING_VALUES) | MODEL_FLOAT_FIELDS | MODEL_INTEGER_FIELDS | frozenset(
    MODEL_BOOLEAN_VALUES
) | {"polarity_candidate_status_order"}


class _InvalidBoundaryLedger(ValueError):
    pass


@dataclass(frozen=True)
class _MeshSegment:
    mesh_segment_id: int
    left_cell_id: int
    right_cell_id: int
    left_edge_index: int
    right_edge_index: int
    start: tuple[float, float, float]
    end: tuple[float, float, float]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise _InvalidBoundaryLedger(message)


def _integer(value: Any, field: str) -> int:
    if type(value) is not int:
        raise _InvalidBoundaryLedger(f"{field} must be an integer")
    return value


def _number(value: Any, field: str) -> float:
    if type(value) not in (int, float):
        raise _InvalidBoundaryLedger(f"{field} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise _InvalidBoundaryLedger(f"{field} must be finite")
    return number


def _positive(value: Any, field: str) -> float:
    number = _number(value, field)
    _require(number > 0.0, f"{field} must be positive")
    return number


def _vector(value: Any, field: str) -> tuple[float, float, float]:
    _require(
        isinstance(value, list) and len(value) == 3,
        f"{field} must be a three-component array",
    )
    return (
        _number(value[0], f"{field}[0]"),
        _number(value[1], f"{field}[1]"),
        _number(value[2], f"{field}[2]"),
    )


def _add(
    left: tuple[float, float, float],
    right: tuple[float, float, float],
) -> tuple[float, float, float]:
    return (left[0] + right[0], left[1] + right[1], left[2] + right[2])


def _sub(
    left: tuple[float, float, float],
    right: tuple[float, float, float],
) -> tuple[float, float, float]:
    return (left[0] - right[0], left[1] - right[1], left[2] - right[2])


def _mul(
    value: tuple[float, float, float], scalar: float
) -> tuple[float, float, float]:
    return (value[0] * scalar, value[1] * scalar, value[2] * scalar)


def _dot(
    left: tuple[float, float, float],
    right: tuple[float, float, float],
) -> float:
    return left[0] * right[0] + left[1] * right[1] + left[2] * right[2]


def _cross(
    left: tuple[float, float, float],
    right: tuple[float, float, float],
) -> tuple[float, float, float]:
    return (
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    )


def _norm(value: tuple[float, float, float]) -> float:
    return math.sqrt(_dot(value, value))


def _normalize(
    value: tuple[float, float, float], field: str
) -> tuple[float, float, float]:
    length = _norm(value)
    _require(
        math.isfinite(length) and length > 1.0e-15,
        f"{field} cannot be normalized",
    )
    return _mul(value, 1.0 / length)


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _tolerance(*values: float, operations: int = 16) -> float:
    scale = max(1.0, *(abs(value) for value in values))
    operand_sum = math.fsum(abs(value) for value in values)
    return max(
        2.0e-12 * scale,
        256.0
        * sys.float_info.epsilon
        * max(1, operations)
        * (1.0 + operand_sum),
    )


def _close(actual: float, expected: float, *terms: float) -> bool:
    return abs(actual - expected) <= _tolerance(
        actual, expected, *terms, operations=len(terms) + 8
    )


def _ulp_close(actual: float, expected: float, *, ulps: int = 4) -> bool:
    return abs(actual - expected) <= ulps * max(
        math.ulp(actual), math.ulp(expected)
    )


def _rotate_about_axis(
    value: tuple[float, float, float],
    axis: tuple[float, float, float],
    angle_rad: float,
) -> tuple[float, float, float]:
    if angle_rad == 0.0:
        return value
    unit_axis = _normalize(axis, "rotation axis")
    cosine = math.cos(angle_rad)
    sine = math.sin(angle_rad)
    return _normalize(
        _add(
            _add(
                _mul(value, cosine),
                _mul(_cross(unit_axis, value), sine),
            ),
            _mul(unit_axis, _dot(unit_axis, value) * (1.0 - cosine)),
        ),
        "rotated plate center",
    )


def _parse_cells(
    world: Mapping[str, Any],
) -> tuple[
    list[tuple[float, float, float]],
    list[list[tuple[float, float, float]]],
    list[list[int]],
]:
    payload = world.get("cells")
    _require(isinstance(payload, list) and bool(payload), "cells must be nonempty")
    positions: list[tuple[float, float, float]] = []
    vertices_by_cell: list[list[tuple[float, float, float]]] = []
    neighbors_by_edge: list[list[int]] = []
    cell_count = len(payload)
    local_edge_count = 0
    for cell_id, item in enumerate(payload):
        label = f"cells[{cell_id}]"
        _require(isinstance(item, dict), f"{label} must be an object")
        _require(
            _integer(item.get("id"), f"{label}.id") == cell_id,
            "cells must be canonically indexed by cell id",
        )
        position = _vector(item.get("position_3d"), f"{label}.position_3d")
        _require(
            abs(_norm(position) - 1.0) <= UNIT_SPHERE_VECTOR_NORM_TOLERANCE,
            f"{label}.position_3d must be unit length",
        )
        raw_vertices = item.get("control_volume_vertices_3d")
        raw_neighbors = item.get("control_volume_edge_neighbor_ids")
        _require(
            isinstance(raw_vertices, list)
            and isinstance(raw_neighbors, list)
            and len(raw_vertices) >= 3
            and len(raw_vertices) <= 64
            and len(raw_vertices) == len(raw_neighbors),
            f"{label} control-volume ring is malformed",
        )
        local_edge_count += len(raw_vertices)
        _require(
            local_edge_count <= 16 * cell_count,
            "control-volume local edge count cap exceeded",
        )
        vertices = [
            _vector(vertex, f"{label}.control_volume_vertices_3d[{index}]")
            for index, vertex in enumerate(raw_vertices)
        ]
        for index, vertex in enumerate(vertices):
            _require(
                abs(_norm(vertex) - 1.0) <= UNIT_SPHERE_VECTOR_NORM_TOLERANCE,
                f"{label}.control_volume_vertices_3d[{index}] is not unit length",
            )
        edge_neighbors = [
            _integer(value, f"{label}.control_volume_edge_neighbor_ids[{index}]")
            for index, value in enumerate(raw_neighbors)
        ]
        _require(
            all(0 <= neighbor < cell_count and neighbor != cell_id for neighbor in edge_neighbors),
            f"{label} has an invalid control-volume edge neighbor",
        )
        positions.append(position)
        vertices_by_cell.append(vertices)
        neighbors_by_edge.append(edge_neighbors)
    return positions, vertices_by_cell, neighbors_by_edge


def _enumerate_mesh_segments(
    vertices_by_cell: Sequence[Sequence[tuple[float, float, float]]],
    neighbors_by_edge: Sequence[Sequence[int]],
) -> list[_MeshSegment]:
    matched_edges: set[tuple[int, int]] = set()
    segments: list[_MeshSegment] = []
    for left_cell_id, (vertices, edge_neighbors) in enumerate(
        zip(vertices_by_cell, neighbors_by_edge)
    ):
        for left_edge_index, right_cell_id in enumerate(edge_neighbors):
            if right_cell_id < left_cell_id:
                continue
            _require(
                right_cell_id > left_cell_id,
                "self-neighbor control-volume segment is invalid",
            )
            start = vertices[left_edge_index]
            end = vertices[(left_edge_index + 1) % len(vertices)]
            right_vertices = vertices_by_cell[right_cell_id]
            candidates: list[int] = []
            for right_edge_index, reciprocal_id in enumerate(
                neighbors_by_edge[right_cell_id]
            ):
                if reciprocal_id != left_cell_id:
                    continue
                right_start = right_vertices[right_edge_index]
                right_end = right_vertices[
                    (right_edge_index + 1) % len(right_vertices)
                ]
                reverse_error = max(
                    _norm(_sub(start, right_end)),
                    _norm(_sub(end, right_start)),
                )
                if reverse_error <= RECIPROCAL_ENDPOINT_TOLERANCE:
                    candidates.append(right_edge_index)
            _require(
                len(candidates) == 1,
                "control-volume segment does not have exactly one reversed reciprocal",
            )
            right_edge_index = candidates[0]
            _require(
                (left_cell_id, left_edge_index) not in matched_edges
                and (right_cell_id, right_edge_index) not in matched_edges,
                "a control-volume local edge was matched more than once",
            )
            matched_edges.add((left_cell_id, left_edge_index))
            matched_edges.add((right_cell_id, right_edge_index))
            segments.append(
                _MeshSegment(
                    mesh_segment_id=len(segments),
                    left_cell_id=left_cell_id,
                    right_cell_id=right_cell_id,
                    left_edge_index=left_edge_index,
                    right_edge_index=right_edge_index,
                    start=start,
                    end=end,
                )
            )
    expected_local_edges = sum(len(values) for values in neighbors_by_edge)
    _require(
        len(matched_edges) == expected_local_edges
        and 2 * len(segments) == expected_local_edges,
        "control-volume edge reciprocity is incomplete",
    )
    return segments


def _typed_array(
    value: Any,
    *,
    field: str,
    count: int,
    integer: bool,
) -> list[int] | list[float]:
    _require(
        isinstance(value, list) and len(value) == count,
        f"{field} must contain exactly {count} entries",
    )
    if integer:
        return [_integer(item, f"{field}[{index}]") for index, item in enumerate(value)]
    return [_number(item, f"{field}[{index}]") for index, item in enumerate(value)]


def _opening_state_arrays(
    step: Mapping[str, Any], *, cell_count: int, label: str
) -> tuple[
    list[int],
    list[int],
    list[float],
    list[float],
    list[float],
    list[bool],
]:
    ledger = step.get("crust_overlap_ledger")
    _require(isinstance(ledger, dict), f"{label}.crust_overlap_ledger is missing")
    crust_type = _typed_array(
        ledger.get("remapped_crust_type_by_cell"),
        field=f"{label}.crust_overlap_ledger.remapped_crust_type_by_cell",
        count=cell_count,
        integer=True,
    )
    lithology = _typed_array(
        ledger.get("remapped_lithology_by_cell"),
        field=f"{label}.crust_overlap_ledger.remapped_lithology_by_cell",
        count=cell_count,
        integer=True,
    )
    age = _typed_array(
        ledger.get("remapped_crust_age_ma_by_cell"),
        field=f"{label}.crust_overlap_ledger.remapped_crust_age_ma_by_cell",
        count=cell_count,
        integer=False,
    )
    thickness = _typed_array(
        ledger.get("remapped_crust_thickness_km_by_cell"),
        field=f"{label}.crust_overlap_ledger.remapped_crust_thickness_km_by_cell",
        count=cell_count,
        integer=False,
    )
    density = _typed_array(
        ledger.get("remapped_crust_density_by_cell"),
        field=f"{label}.crust_overlap_ledger.remapped_crust_density_by_cell",
        count=cell_count,
        integer=False,
    )
    assert all(isinstance(value, int) for value in crust_type + lithology)
    available: list[bool] = []
    for index in range(cell_count):
        _require(
            0 <= crust_type[index] <= 8,
            f"{label} opening crust type {index} is invalid",
        )
        _require(
            0 <= lithology[index] <= 6,
            f"{label} opening lithology {index} is invalid",
        )
        unavailable = age[index] == 0.0 and thickness[index] == 0.0
        valid_available = (
            age[index] >= 0.0
            and thickness[index] > 0.0
            and density[index] > 0.0
        )
        _require(
            density[index] > 0.0 and (unavailable or valid_available),
            f"{label} opening crust numeric state {index} is neither canonical unavailable nor valid available state",
        )
        available.append(valid_available)
    return crust_type, lithology, age, thickness, density, available


def _is_oceanic(
    crust_type: int,
    lithology: int,
    age_ma: float,
    thickness_km: float,
    density_g_cm3: float,
) -> bool:
    if crust_type == 0:
        return True
    if crust_type == 2:
        return lithology == 0
    if crust_type != 3:
        return False
    return age_ma <= 320.0 and thickness_km <= 18.0 and density_g_cm3 >= 2.84


def _expected_record(
    *,
    segment_id: int,
    segment: _MeshSegment,
    positions: Sequence[tuple[float, float, float]],
    cell_plate_ids: Sequence[int],
    axes: Sequence[tuple[float, float, float]],
    speeds: Sequence[float],
    opening_state: tuple[
        list[int],
        list[int],
        list[float],
        list[float],
        list[float],
        list[bool],
    ],
    radius_km: float,
    reference_motion_scale_deg: float,
    reference_timestep_ma: float,
) -> dict[str, Any]:
    left_id = segment.left_cell_id
    right_id = segment.right_cell_id
    left_plate_id = cell_plate_ids[left_id]
    right_plate_id = cell_plate_ids[right_id]
    midpoint = _normalize(_add(segment.start, segment.end), "segment midpoint")
    edge_cross = _cross(segment.start, segment.end)
    edge_plane_normal = _normalize(edge_cross, "segment edge plane normal")
    _require(
        _dot(positions[left_id], edge_plane_normal) > 0.0,
        "canonical left control-volume edge is not counter-clockwise",
    )
    tangent = _normalize(_cross(edge_plane_normal, midpoint), "segment tangent")
    normal = _normalize(_cross(tangent, midpoint), "segment normal")
    _require(
        _dot(normal, _sub(positions[right_id], positions[left_id])) > 0.0,
        "canonical left CCW segment normal does not point left-to-right",
    )
    angular_length = math.atan2(
        _norm(edge_cross),
        _clamp(_dot(segment.start, segment.end), -1.0, 1.0),
    )
    raw_left_velocity = _cross(_mul(axes[left_plate_id], speeds[left_plate_id]), midpoint)
    raw_right_velocity = _cross(
        _mul(axes[right_plate_id], speeds[right_plate_id]), midpoint
    )
    raw_relative = _sub(raw_right_velocity, raw_left_velocity)
    raw_opening = _dot(raw_relative, normal)
    raw_convergence = -raw_opening
    raw_slip = _dot(raw_relative, tangent)
    velocity_factor = (
        radius_km
        * reference_motion_scale_deg
        * (math.pi / 180.0)
        / reference_timestep_ma
    )
    left_velocity = _mul(raw_left_velocity, velocity_factor)
    right_velocity = _mul(raw_right_velocity, velocity_factor)
    relative_velocity = _sub(right_velocity, left_velocity)
    opening_rate = _dot(relative_velocity, normal)
    convergence_rate = -opening_rate
    slip_rate = _dot(relative_velocity, tangent)
    convergent_strength = _clamp(raw_convergence * 1.25)
    divergent_strength = _clamp(raw_opening * 1.25)
    transform_strength = _clamp(
        (abs(raw_slip) - abs(raw_opening) * 0.35) * 1.05
    )
    maximum_strength = max(
        convergent_strength, divergent_strength, transform_strength
    )
    if maximum_strength < 0.08:
        boundary_class = "inactive"
    elif convergent_strength == maximum_strength:
        boundary_class = "convergent"
    elif divergent_strength == maximum_strength:
        boundary_class = "divergent"
    else:
        boundary_class = "transform"

    crust_type, lithology, age, thickness, density, available = opening_state
    left_available = available[left_id]
    right_available = available[right_id]
    left_oceanic = left_available and _is_oceanic(
        crust_type[left_id],
        lithology[left_id],
        age[left_id],
        thickness[left_id],
        density[left_id],
    )
    right_oceanic = right_available and _is_oceanic(
        crust_type[right_id],
        lithology[right_id],
        age[right_id],
        thickness[right_id],
        density[right_id],
    )
    convergence_active = convergent_strength >= 0.08
    if not convergence_active:
        polarity = "no_active_convergence"
    elif not left_available or not right_available:
        polarity = "unresolved_missing_opening_crust_state"
    elif left_oceanic and not right_oceanic:
        polarity = "left_oceanic_only"
    elif right_oceanic and not left_oceanic:
        polarity = "right_oceanic_only"
    elif left_oceanic and right_oceanic:
        polarity = "ambiguous_both_oceanic"
    else:
        polarity = "unresolved_no_oceanic_side"
    candidate_subducting_side = (
        "left"
        if polarity == "left_oceanic_only"
        else "right"
        if polarity == "right_oceanic_only"
        else "none"
    )
    candidate_overriding_side = (
        "right"
        if candidate_subducting_side == "left"
        else "left"
        if candidate_subducting_side == "right"
        else "none"
    )
    if convergence_active:
        physical_polarity_status = "unknown_unresolved"
        physical_subducting_side = "unknown"
        physical_overriding_side = "unknown"
    else:
        physical_polarity_status = "not_applicable_no_active_convergence"
        physical_subducting_side = "none"
        physical_overriding_side = "none"

    expected: dict[str, Any] = {
        "segment_id": segment_id,
        "mesh_segment_id": segment.mesh_segment_id,
        "left_cell_id": left_id,
        "right_cell_id": right_id,
        "left_edge_index": segment.left_edge_index,
        "right_edge_index": segment.right_edge_index,
        "left_plate_id": left_plate_id,
        "right_plate_id": right_plate_id,
        "angular_length_rad": angular_length,
        "length_km": angular_length * radius_km,
        "signed_opening_rate_km_per_ma": opening_rate,
        "signed_convergence_rate_km_per_ma": convergence_rate,
        "signed_slip_rate_km_per_ma": slip_rate,
        "signed_opening_index": raw_opening,
        "signed_convergence_index": raw_convergence,
        "signed_slip_index": raw_slip,
        "direct_convergent_strength": convergent_strength,
        "direct_divergent_strength": divergent_strength,
        "direct_transform_strength": transform_strength,
        "direct_boundary_class": boundary_class,
        "convergence_active": convergence_active,
        "left_opening_crust_type": crust_type[left_id],
        "left_opening_lithology": lithology[left_id],
        "left_opening_crust_age_ma": age[left_id],
        "left_opening_crust_thickness_km": thickness[left_id],
        "left_opening_crust_density_g_cm3": density[left_id],
        "left_opening_crust_state_available": left_available,
        "left_opening_oceanic_like": left_oceanic,
        "right_opening_crust_type": crust_type[right_id],
        "right_opening_lithology": lithology[right_id],
        "right_opening_crust_age_ma": age[right_id],
        "right_opening_crust_thickness_km": thickness[right_id],
        "right_opening_crust_density_g_cm3": density[right_id],
        "right_opening_crust_state_available": right_available,
        "right_opening_oceanic_like": right_oceanic,
        "polarity_candidate_status": polarity,
        "candidate_subducting_side": candidate_subducting_side,
        "candidate_overriding_side": candidate_overriding_side,
        "physical_polarity_status": physical_polarity_status,
        "physical_polarity_source": "none",
        "physical_subducting_side": physical_subducting_side,
        "physical_overriding_side": physical_overriding_side,
        "physical_polarity_confidence": 0.0,
    }
    for prefix, vector in (
        ("start_unit", segment.start),
        ("midpoint_unit", midpoint),
        ("end_unit", segment.end),
        ("tangent_unit", tangent),
        ("left_to_right_normal_unit", normal),
    ):
        expected[f"{prefix}_x"] = vector[0]
        expected[f"{prefix}_y"] = vector[1]
        expected[f"{prefix}_z"] = vector[2]
    for prefix, vector in (
        ("left_euler_velocity", left_velocity),
        ("right_euler_velocity", right_velocity),
        ("relative_velocity", relative_velocity),
    ):
        expected[f"{prefix}_x_km_per_ma"] = vector[0]
        expected[f"{prefix}_y_km_per_ma"] = vector[1]
        expected[f"{prefix}_z_km_per_ma"] = vector[2]
    return expected


def _compare_record(
    actual: Mapping[str, Any], expected: Mapping[str, Any], *, label: str
) -> float:
    _require(
        set(actual) == RECORD_FIELDS,
        f"{label} fields do not match the canonical boundary-segment schema",
    )
    maximum_residual = 0.0
    for field in INTEGER_RECORD_FIELDS:
        observed = _integer(actual.get(field), f"{label}.{field}")
        _require(observed == expected[field], f"{label}.{field} does not replay")
    for field in BOOLEAN_RECORD_FIELDS:
        _require(
            type(actual.get(field)) is bool,
            f"{label}.{field} must be boolean",
        )
        _require(
            actual[field] is expected[field], f"{label}.{field} does not replay"
        )
    for field in STRING_RECORD_FIELDS:
        observed = actual.get(field)
        _require(type(observed) is str, f"{label}.{field} must be a string")
        if field == "direct_boundary_class":
            _require(observed in BOUNDARY_CLASS_NAMES, f"{label}.{field} is invalid")
        elif field == "polarity_candidate_status":
            _require(observed in POLARITY_STATUS_NAMES, f"{label}.{field} is invalid")
        elif field in {"candidate_subducting_side", "candidate_overriding_side"}:
            _require(observed in BOUNDARY_SIDE_NAMES, f"{label}.{field} is invalid")
        elif field in {"physical_subducting_side", "physical_overriding_side"}:
            _require(
                observed in PHYSICAL_BOUNDARY_SIDE_NAMES,
                f"{label}.{field} is invalid",
            )
        elif field == "physical_polarity_status":
            _require(
                observed in PHYSICAL_POLARITY_STATUS_NAMES,
                f"{label}.{field} is invalid",
            )
        else:
            _require(
                observed == "none",
                f"{label}.{field} is invalid",
            )
        _require(observed == expected[field], f"{label}.{field} does not replay")
    for field in FLOAT_RECORD_FIELDS:
        observed = _number(actual.get(field), f"{label}.{field}")
        wanted = float(expected[field])
        residual = abs(observed - wanted)
        maximum_residual = max(maximum_residual, residual)
        if field == "physical_polarity_confidence":
            _require(
                observed == 0.0,
                f"{label}.{field} must remain exact zero while polarity is unknown",
            )
        else:
            _require(
                _close(observed, wanted),
                f"{label}.{field} does not replay from authoritative inputs",
            )
    return maximum_residual


def _validate_model(
    world: Mapping[str, Any],
    *,
    history_count: int,
    mesh_segment_count: int,
) -> Mapping[str, Any]:
    model = world.get("plate_boundary_segment_model")
    _require(isinstance(model, dict), "plate_boundary_segment_model must be an object")
    _require(
        set(model) == MODEL_FIELDS,
        "plate_boundary_segment_model fields do not match the canonical schema",
    )
    for field, expected in MODEL_STRING_VALUES.items():
        _require(type(model.get(field)) is str, f"model.{field} must be a string")
        _require(model[field] == expected, f"model.{field} is invalid")
    for field, expected in MODEL_BOOLEAN_VALUES.items():
        _require(type(model.get(field)) is bool, f"model.{field} must be boolean")
        _require(model[field] is expected, f"model.{field} is invalid")
    for field in MODEL_FLOAT_FIELDS:
        _number(model.get(field), f"model.{field}")
    for field in MODEL_INTEGER_FIELDS:
        _integer(model.get(field), f"model.{field}")
    _require(
        model.get("polarity_candidate_status_order")
        == [
            "no_active_convergence",
            "unresolved_missing_opening_crust_state",
            "left_oceanic_only",
            "right_oceanic_only",
            "ambiguous_both_oceanic",
            "unresolved_no_oceanic_side",
        ],
        "model.polarity_candidate_status_order is invalid",
    )
    _require(
        _number(
            model["reciprocal_endpoint_match_tolerance_chord"],
            "model.reciprocal_endpoint_match_tolerance_chord",
        )
        == RECIPROCAL_ENDPOINT_TOLERANCE,
        "model reciprocal endpoint tolerance is invalid",
    )
    _require(
        _number(
            model["direct_boundary_class_inactive_threshold"],
            "model.direct_boundary_class_inactive_threshold",
        )
        == 0.08,
        "model direct boundary inactive threshold is invalid",
    )
    _require(
        _number(
            model["euler_axis_unit_tolerance"],
            "model.euler_axis_unit_tolerance",
        )
        == 1.0e-12,
        "model Euler-axis unit tolerance is invalid",
    )
    _require(
        _number(
            model["unit_sphere_vector_norm_tolerance"],
            "model.unit_sphere_vector_norm_tolerance",
        )
        == UNIT_SPHERE_VECTOR_NORM_TOLERANCE,
        "model unit-sphere vector norm tolerance is invalid",
    )
    _require(
        _integer(model["history_step_count"], "model.history_step_count")
        == history_count,
        "plate boundary model history_step_count is invalid",
    )
    _require(
        _integer(
            model["reciprocal_mesh_segment_count"],
            "model.reciprocal_mesh_segment_count",
        )
        == mesh_segment_count,
        "plate boundary model reciprocal mesh segment count is invalid",
    )
    _require(
        _integer(
            model["serialized_float_decimal_significant_digits"],
            "model.serialized_float_decimal_significant_digits",
        )
        == 17,
        "plate boundary model float precision is invalid",
    )
    for precision_field in (
        "intrinsic_angular_speed_serialized_significant_digits",
        "rotation_axis_serialized_significant_digits",
        "assignment_center_serialized_significant_digits",
        "top_level_plate_center_serialized_significant_digits",
    ):
        _require(
            _integer(model[precision_field], f"model.{precision_field}") == 17,
            f"plate boundary model {precision_field} is invalid",
        )
    _require(
        _integer(
            model["maximum_control_volume_segments_per_cell"],
            "model.maximum_control_volume_segments_per_cell",
        )
        == 64,
        "plate boundary model per-cell segment cap is invalid",
    )
    _require(
        _integer(
            model["maximum_reciprocal_mesh_segment_count_multiplier"],
            "model.maximum_reciprocal_mesh_segment_count_multiplier",
        )
        == 8,
        "plate boundary model reciprocal segment multiplier is invalid",
    )
    return model


def validate_plate_boundary_edges(world: Mapping[str, Any]) -> dict[str, Any]:
    """Independently replay exact native plate-boundary control-volume segments.

    The replay deliberately does not read per-cell ``boundary_convergent``,
    ``boundary_divergent``, ``boundary_transform``, or ``boundary_type``.  It
    reconstructs direct segment kinematics from authoritative mesh rings,
    plate-assignment snapshots, Euler axes/speeds, and opening crust state.
    """

    failures: list[str] = []
    metrics: dict[str, Any] = {
        "authoritative_reciprocal_control_volume_geometry_replayed": False,
        "direct_unsmoothed_euler_kinematics_replayed": False,
        "opening_crust_state_and_polarity_candidate_replayed": False,
        "explicit_unknown_physical_polarity_replayed": False,
        "top_level_euler_parameters_cross_checked": False,
        "step_rotations_replayed": False,
        "plate_center_history_replayed": False,
        "cell_plate_assignments_replayed": False,
        "smoothed_cell_boundary_fields_used": False,
        "subduction_polarity_resolved": False,
        "subducted_slab_geometry_resolved": False,
    }
    try:
        _require(isinstance(world, Mapping), "world must be an object")
        positions, vertices_by_cell, neighbors_by_edge = _parse_cells(world)
        mesh_segments = _enumerate_mesh_segments(
            vertices_by_cell, neighbors_by_edge
        )
        cell_count = len(positions)
        _require(
            len(mesh_segments) <= 8 * cell_count,
            "reciprocal mesh segment count cap exceeded",
        )
        history = world.get("plate_motion_history")
        _require(
            isinstance(history, list)
            and bool(history)
            and all(isinstance(step, dict) for step in history),
            "plate_motion_history must be a nonempty list of objects",
        )
        model = _validate_model(
            world,
            history_count=len(history),
            mesh_segment_count=len(mesh_segments),
        )
        planet = world.get("planet_parameters")
        _require(isinstance(planet, dict), "planet_parameters must be an object")
        radius_km = _positive(planet.get("radius_km"), "planet_parameters.radius_km")
        kinematic_model = world.get("plate_kinematic_model")
        _require(
            isinstance(kinematic_model, dict),
            "plate_kinematic_model must be an object",
        )
        reference_motion_scale = _number(
            kinematic_model.get("reference_motion_scale_deg_per_reference_step"),
            "plate_kinematic_model.reference_motion_scale_deg_per_reference_step",
        )
        reference_timestep = _positive(
            kinematic_model.get("reference_timestep_ma"),
            "plate_kinematic_model.reference_timestep_ma",
        )
        _require(
            reference_motion_scale >= 0.0,
            "reference plate motion scale must be nonnegative",
        )
        maturation_timestep_scale = _number(
            kinematic_model.get("maturation_timestep_scale"),
            "plate_kinematic_model.maturation_timestep_scale",
        )
        effective_motion_scale = _number(
            kinematic_model.get("effective_motion_scale_deg_per_step"),
            "plate_kinematic_model.effective_motion_scale_deg_per_step",
        )
        _require(
            maturation_timestep_scale >= 0.0 and effective_motion_scale >= 0.0,
            "plate motion timestep scales must be nonnegative",
        )
        _require(
            _ulp_close(
                effective_motion_scale,
                reference_motion_scale * maturation_timestep_scale,
            ),
            "effective plate motion scale does not replay from reference scaling",
        )
        _require(
            reference_timestep == MATURATION_REFERENCE_TIMESTEP_MA,
            "boundary velocities must use the canonical reference timestep",
        )
        model_radius_km = _positive(model.get("radius_km"), "model.radius_km")
        model_reference_motion_scale = _number(
            model.get("reference_motion_scale_deg_per_reference_step"),
            "model.reference_motion_scale_deg_per_reference_step",
        )
        model_reference_timestep = _positive(
            model.get("reference_timestep_ma"), "model.reference_timestep_ma"
        )
        _require(
            model_radius_km == radius_km,
            "boundary model radius does not mirror planet parameters",
        )
        _require(
            model_reference_motion_scale == reference_motion_scale,
            "boundary model motion scale does not mirror plate kinematics",
        )
        _require(
            model_reference_timestep == reference_timestep,
            "boundary model reference timestep does not mirror plate kinematics",
        )
        expected_velocity_scale = (
            radius_km
            * reference_motion_scale
            * (math.pi / 180.0)
            / reference_timestep
        )
        _require(
            _ulp_close(
                _number(
                    model.get("nominal_velocity_scale_km_per_ma"),
                    "model.nominal_velocity_scale_km_per_ma",
                ),
                expected_velocity_scale,
                ulps=8,
            ),
            "boundary model nominal velocity scale does not replay",
        )

        top_plates = world.get("plates")
        _require(
            isinstance(top_plates, list) and bool(top_plates),
            "top-level plates must be a nonempty list",
        )
        top_axes: list[tuple[float, float, float]] = []
        top_speeds: list[float] = []
        top_initial_centers: list[tuple[float, float, float]] = []
        top_final_centers: list[tuple[float, float, float]] = []
        for plate_id, plate in enumerate(top_plates):
            top_label = f"plates[{plate_id}]"
            _require(isinstance(plate, dict), f"{top_label} must be an object")
            _require(
                _integer(plate.get("id"), f"{top_label}.id") == plate_id,
                "top-level plates must be canonically plate-id indexed",
            )
            axis = _vector(plate.get("axis"), f"{top_label}.axis")
            _require(
                abs(_norm(axis) - 1.0) <= 1.0e-12,
                f"{top_label}.axis must be unit length",
            )
            speed = _number(
                plate.get("angular_speed"), f"{top_label}.angular_speed"
            )
            _require(speed >= 0.0, f"{top_label}.angular_speed is negative")
            initial_center = _vector(
                plate.get("initial_center"), f"{top_label}.initial_center"
            )
            final_center = _vector(
                plate.get("center"), f"{top_label}.center"
            )
            _require(
                abs(_norm(initial_center) - 1.0) <= 1.0e-12
                and abs(_norm(final_center) - 1.0) <= 1.0e-12,
                f"{top_label} centers must be unit length",
            )
            top_axes.append(axis)
            top_speeds.append(speed)
            top_initial_centers.append(initial_center)
            top_final_centers.append(final_center)

        total_boundary_segment_count = 0
        maximum_boundary_segment_count = 0
        maximum_record_residual = 0.0
        class_counts: Counter[str] = Counter()
        polarity_counts: Counter[str] = Counter()
        physical_polarity_counts: Counter[str] = Counter()
        pair_counts = Counter(
            (segment.left_cell_id, segment.right_cell_id)
            for segment in mesh_segments
        )
        duplicate_neighbor_pair_segment_count = sum(
            count - 1 for count in pair_counts.values() if count > 1
        )
        previous_centers: list[tuple[float, float, float]] | None = None

        for step_id, step in enumerate(history):
            label = f"plate_motion_history[{step_id}]"
            _require(
                _integer(step.get("id"), f"{label}.id") == step_id,
                "plate motion history ids must be sequential",
            )
            cell_plate_ids = _typed_array(
                step.get("cell_plate_ids"),
                field=f"{label}.cell_plate_ids",
                count=cell_count,
                integer=True,
            )
            plate_count = _integer(step.get("plate_count"), f"{label}.plate_count")
            _require(
                _integer(step.get("cell_count"), f"{label}.cell_count")
                == cell_count,
                f"{label}.cell_count is invalid",
            )
            _require(plate_count > 1, f"{label}.plate_count must exceed one")
            _require(
                plate_count == len(top_plates),
                f"{label}.plate_count does not mirror top-level plates",
            )
            _require(
                all(0 <= plate_id < plate_count for plate_id in cell_plate_ids),
                f"{label}.cell_plate_ids contains an invalid plate id",
            )
            snapshots = step.get("plates")
            _require(
                isinstance(snapshots, list) and len(snapshots) == plate_count,
                f"{label}.plates must contain exactly plate_count snapshots",
            )
            axes: list[tuple[float, float, float]] = []
            speeds: list[float] = []
            centers: list[tuple[float, float, float]] = []
            snapshot_cell_counts: list[int] = []
            for plate_id, snapshot in enumerate(snapshots):
                snapshot_label = f"{label}.plates[{plate_id}]"
                _require(isinstance(snapshot, dict), f"{snapshot_label} must be an object")
                _require(
                    _integer(snapshot.get("plate_id"), f"{snapshot_label}.plate_id")
                    == plate_id,
                    f"{label}.plates must be canonically plate-id indexed",
                )
                axis = _vector(
                    snapshot.get("rotation_axis"),
                    f"{snapshot_label}.rotation_axis",
                )
                center = _vector(
                    snapshot.get("center"), f"{snapshot_label}.center"
                )
                _require(
                    abs(_norm(axis) - 1.0) <= 1.0e-12,
                    f"{snapshot_label}.rotation_axis must be unit length",
                )
                _require(
                    abs(_norm(center) - 1.0) <= 1.0e-12,
                    f"{snapshot_label}.center must be unit length",
                )
                speed = _number(
                    snapshot.get("intrinsic_angular_speed"),
                    f"{snapshot_label}.intrinsic_angular_speed",
                )
                _require(speed >= 0.0, f"{snapshot_label} speed must be nonnegative")
                _require(
                    axis == top_axes[plate_id],
                    f"{snapshot_label}.rotation_axis does not mirror the top-level plate axis",
                )
                _require(
                    speed == top_speeds[plate_id],
                    f"{snapshot_label}.intrinsic_angular_speed does not mirror the top-level plate speed",
                )
                step_rotation_deg = _number(
                    snapshot.get("step_rotation_deg"),
                    f"{snapshot_label}.step_rotation_deg",
                )
                expected_step_rotation_deg = (
                    0.0 if step_id == 0 else speed * effective_motion_scale
                )
                _require(
                    _ulp_close(
                        step_rotation_deg,
                        expected_step_rotation_deg,
                        ulps=4,
                    ),
                    f"{snapshot_label}.step_rotation_deg does not replay from intrinsic speed and timestep scale",
                )
                expected_center = (
                    top_initial_centers[plate_id]
                    if step_id == 0
                    else _rotate_about_axis(
                        previous_centers[plate_id],
                        axis,
                        step_rotation_deg * (math.pi / 180.0),
                    )
                )
                _require(
                    center == expected_center
                    if step_id == 0
                    else all(
                        _close(center[component], expected_center[component])
                        for component in range(3)
                    ),
                    f"{snapshot_label}.center does not replay from authoritative center history",
                )
                axes.append(axis)
                speeds.append(speed)
                centers.append(center)
                snapshot_cell_counts.append(
                    _integer(
                        snapshot.get("cell_count"),
                        f"{snapshot_label}.cell_count",
                    )
                )

            reconstructed_cell_plate_ids: list[int] = []
            reconstructed_plate_counts = [0] * plate_count
            for position in positions:
                best_score = -2.0
                best_plate_id = 0
                for plate_id, center in enumerate(centers):
                    score = _dot(position, center)
                    if score > best_score:
                        best_score = score
                        best_plate_id = plate_id
                reconstructed_cell_plate_ids.append(best_plate_id)
                reconstructed_plate_counts[best_plate_id] += 1
            _require(
                reconstructed_cell_plate_ids == cell_plate_ids,
                f"{label}.cell_plate_ids do not replay from cell positions and plate centers",
            )
            _require(
                all(count > 0 for count in reconstructed_plate_counts),
                f"{label} contains an empty nearest-center plate domain",
            )
            _require(
                reconstructed_plate_counts == snapshot_cell_counts,
                f"{label} snapshot plate cell counts do not replay",
            )
            previous_centers = centers

            opening_state = _opening_state_arrays(
                step, cell_count=cell_count, label=label
            )
            expected_segments = [
                segment
                for segment in mesh_segments
                if cell_plate_ids[segment.left_cell_id]
                != cell_plate_ids[segment.right_cell_id]
            ]
            records = step.get("boundary_segments")
            _require(
                isinstance(records, list), f"{label}.boundary_segments must be a list"
            )
            _require(
                len(records) == len(expected_segments),
                f"{label}.boundary_segments does not contain exactly every cross-plate reciprocal segment",
            )
            _require(
                _integer(
                    step.get("reciprocal_mesh_segment_count"),
                    f"{label}.reciprocal_mesh_segment_count",
                )
                == len(mesh_segments),
                f"{label}.reciprocal_mesh_segment_count is invalid",
            )
            _require(
                _integer(
                    step.get("boundary_segment_count"),
                    f"{label}.boundary_segment_count",
                )
                == len(expected_segments),
                f"{label}.boundary_segment_count is invalid",
            )
            incident_cell_count = len(
                {
                    cell_id
                    for segment in expected_segments
                    for cell_id in (segment.left_cell_id, segment.right_cell_id)
                }
            )
            _require(
                _integer(
                    step.get("control_volume_boundary_incident_cell_count"),
                    f"{label}.control_volume_boundary_incident_cell_count",
                )
                == incident_cell_count,
                f"{label}.control_volume_boundary_incident_cell_count is invalid",
            )
            for segment_id, (record, segment) in enumerate(
                zip(records, expected_segments)
            ):
                record_label = f"{label}.boundary_segments[{segment_id}]"
                _require(isinstance(record, dict), f"{record_label} must be an object")
                expected = _expected_record(
                    segment_id=segment_id,
                    segment=segment,
                    positions=positions,
                    cell_plate_ids=cell_plate_ids,
                    axes=axes,
                    speeds=speeds,
                    opening_state=opening_state,
                    radius_km=radius_km,
                    reference_motion_scale_deg=reference_motion_scale,
                    reference_timestep_ma=reference_timestep,
                )
                maximum_record_residual = max(
                    maximum_record_residual,
                    _compare_record(record, expected, label=record_label),
                )
                class_counts[str(expected["direct_boundary_class"])] += 1
                polarity_counts[str(expected["polarity_candidate_status"])] += 1
                physical_polarity_counts[
                    str(expected["physical_polarity_status"])
                ] += 1
            total_boundary_segment_count += len(records)
            maximum_boundary_segment_count = max(
                maximum_boundary_segment_count, len(records)
            )

        _require(previous_centers is not None, "plate center history is empty")
        _require(
            previous_centers == top_final_centers,
            "final plate snapshot centers do not mirror top-level plate centers",
        )
        _require(
            _integer(
                model["total_boundary_segment_count"],
                "model.total_boundary_segment_count",
            )
            == total_boundary_segment_count,
            "boundary model total_boundary_segment_count does not replay",
        )
        _require(
            _integer(
                model["maximum_boundary_segment_count"],
                "model.maximum_boundary_segment_count",
            )
            == maximum_boundary_segment_count,
            "boundary model maximum_boundary_segment_count does not replay",
        )
        metrics.update(
            {
                "authoritative_reciprocal_control_volume_geometry_replayed": True,
                "direct_unsmoothed_euler_kinematics_replayed": True,
                "opening_crust_state_and_polarity_candidate_replayed": True,
                "explicit_unknown_physical_polarity_replayed": True,
                "top_level_euler_parameters_cross_checked": True,
                "step_rotations_replayed": True,
                "plate_center_history_replayed": True,
                "cell_plate_assignments_replayed": True,
                "cell_count": cell_count,
                "history_step_count": len(history),
                "mesh_reciprocal_segment_count": len(mesh_segments),
                "duplicate_neighbor_pair_segment_count": duplicate_neighbor_pair_segment_count,
                "total_boundary_segment_count": total_boundary_segment_count,
                "maximum_boundary_segment_count_per_step": maximum_boundary_segment_count,
                "maximum_record_replay_residual": maximum_record_residual,
                "direct_boundary_class_counts": dict(sorted(class_counts.items())),
                "polarity_candidate_status_counts": dict(sorted(polarity_counts.items())),
                "physical_polarity_status_counts": dict(
                    sorted(physical_polarity_counts.items())
                ),
            }
        )
    except (_InvalidBoundaryLedger, KeyError, IndexError, TypeError, ValueError, OverflowError) as exc:
        failures.append(str(exc))
    return {"passed": not failures, "failures": failures, "metrics": metrics}


__all__ = ["validate_plate_boundary_edges"]
