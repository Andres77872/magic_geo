from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Mapping
from typing import Any

from .crust_transport_validation import validate_crust_overlap_transport
from .plate_boundary_edge_validation import validate_plate_boundary_edges


MODEL_TYPE = "sparse_membership_class_to_uniform_boundary_plate_pair_candidate_v1"
MAXIMUM_PLATE_COUNT = 256
MAXIMUM_BOUNDARY_SEGMENTS_PER_CELL = 8
MAXIMUM_MEMBERSHIP_CLASSES_PER_CELL = 16384
MAXIMUM_REPLAY_OPERATION_COUNT = 2_147_483_647

PHYSICAL_CONSENSUS_STATUS_ORDER = (
    "not_all_segments_have_active_convergence",
    "all_active_all_physical_polarities_unknown",
    "all_active_mixed_resolved_and_unknown",
    "all_active_resolved_polarities_conflict",
    "all_active_resolved_polarity_uniform",
)
HEURISTIC_CONSENSUS_STATUS_ORDER = (
    "not_all_segments_have_active_convergence",
    "all_active_one_or_more_unique_oceanic_candidates_unavailable",
    "all_active_unique_oceanic_candidates_conflict",
    "all_active_unique_oceanic_candidate_uniform",
)
ASSIGNMENT_STATUS_ORDER = (
    "unknown_nonbinary_membership",
    "unknown_non_distinct_source_plate_pair",
    "unknown_no_same_step_boundary_pair",
    "unknown_no_same_step_endpoint_incidence",
    "unknown_no_uniform_pair_polarity_evidence",
    "uniform_oceanic_side_heuristic_candidate",
    "uniform_resolved_physical_polarity_backed_candidate",
)

MODEL_STRING_VALUES: dict[str, str] = {
    "model_type": MODEL_TYPE,
    "ledger_location": "plate_motion_history[].crust_overlap_candidate_fate_ledger",
    "membership_source_location": (
        "plate_motion_history[].crust_overlap_ledger."
        "coverage_membership_area_class_ledger"
    ),
    "boundary_evidence_location": "plate_motion_history[].boundary_segments",
    "source_plate_id_semantics": (
        "coverage_membership_area_class_ledger.source_plate_ids_at_transport_source_snapshot"
    ),
    "boundary_plate_id_semantics": (
        "boundary_segments.left_plate_id_and_right_plate_id_at_boundary_assignment_snapshot"
    ),
    "assignment_step_linkage": (
        "step_0_source_0_boundary_0_else_source_step_id_minus_1_boundary_step_id"
    ),
    "persistent_pair_id_formula": "256*plate_low_id+plate_high_id",
    "pair_id_semantics": (
        "persistent_unordered_plate_pair_id_not_boundary_pair_evidence_array_index"
    ),
    "pair_grouping": (
        "all_same_step_boundary_segments_grouped_by_sorted_unordered_plate_id_pair"
    ),
    "pair_record_order": (
        "plate_low_id_then_plate_high_id_with_segment_ids_ascending"
    ),
    "class_record_selection": (
        "one_record_per_membership_area_class_with_multiplicity_at_least_2"
    ),
    "class_record_order": "membership_area_class_id_ascending",
    "class_candidate_preference": (
        "uniform_resolved_physical_polarity_else_uniform_oceanic_side_heuristic_"
        "only_when_all_physical_polarities_unknown"
    ),
    "pair_endpoint_incidence_semantics": (
        "destination_cell_id_is_an_endpoint_of_at_least_one_segment_in_the_pair_"
        "not_a_local_atom_or_fragment_to_segment_link"
    ),
    "representative_usage": (
        "membership_area_class_representatives_are_never_used_for_pair_assignment_or_incidence"
    ),
    "candidate_contributor_id_semantics": (
        "global_index_into_coverage_membership_area_class_ledger_contributor_csr_arrays"
    ),
    "candidate_area_semantics": (
        "diagnostic_partition_of_overlap_excess_not_allocated_material_fate_or_transfer"
    ),
    "candidate_area_serialization_model": (
        "general_format_max_digits10_binary64_round_trip_v1"
    ),
    "root_overlap_excess_serialization_model": (
        "general_format_max_digits10_binary64_round_trip_v1_for_per_cell_and_"
        "global_operands"
    ),
    "physical_pair_evidence_provenance_limitation": (
        "pair_evidence_is_not_standalone_per_segment_physical_polarity_source_"
        "and_confidence_are_not_propagated_and_candidate_cannot_promote_or_"
        "replace_upstream_evidence"
    ),
    "operational_cap_semantics": (
        "fail_closed_nonphysical_resource_and_integer_conversion_guards"
    ),
    "deterministic_crosswalk_authority_scope": (
        "serialized_pair_consensus_and_membership_class_diagnostic_mapping_only"
    ),
    "overlap_excess_area_formula": (
        "(multiplicity-1)*coverage_membership_area_class_ledger.area_km2"
    ),
    "area_unit": "km2",
    "candidate_partition_residual_formula": (
        "accounted_overlap_excess_area_km2-crust_overlap_ledger."
        "global_overlap_excess_area_km2"
    ),
    "candidate_partition_residual_acceptance": (
        "accumulated_validated_absolute_destination_binary64_fragment_to_class_"
        "discrepancy_plus_portable_binary64_gamma_upper_envelope_with_exact_"
        "binary64_global_row_replay"
    ),
    "destination_row_discrepancy_acceptance": (
        "binary64_gamma_bound_using_arrangement_fragment_count_class_count_and_"
        "nonnegative_excess_operand_sum"
    ),
    "candidate_partition_tolerance_model": (
        "validated_binary64_fragment_to_class_rows_plus_portable_binary64_"
        "gamma_upper_envelope_v1"
    ),
    "final_long_double_operation_bound": (
        "portable_binary64_gamma_upper_envelope_for_native_long_double_"
        "accumulation_with_explicit_operation_count_and_operand_sum"
    ),
    "physical_resolved_tuple_contract": (
        "resolved_with_supplied_constraint_or_physical_solver_opposite_left_right_"
        "roles_and_confidence_in_open_zero_closed_one"
    ),
    "heuristic_tuple_contract": (
        "left_oceanic_only_or_right_oceanic_only_with_matching_opposite_candidate_roles"
    ),
    "model_limitation": (
        "diagnostic_candidate_crosswalk_only_without_connected_fragment_localization_"
        "physical_fate_slab_geometry_swept_area_or_state_transfer"
    ),
}
MODEL_BOOLEAN_VALUES: dict[str, bool] = {
    "deterministic_crosswalk_authoritative": True,
    "candidate_allocation_authoritative": False,
    "pair_wide_consensus_only": True,
    "destination_endpoint_incidence_resolved": True,
    "pair_evidence_standalone_physical_provenance_complete": False,
    "upstream_segment_physical_source_and_confidence_required_for_interpretation": True,
    "physical_polarity_authoritative": False,
    "physical_polarity_resolved": False,
    "physical_material_fate_authoritative": False,
    "physical_material_fate_resolved": False,
    "slab_selection_authoritative": False,
    "slab_selection_resolved": False,
    "slab_transfer_authoritative": False,
    "slab_transfer_resolved": False,
    "state_mutation_performed": False,
    "crust_material_shadow_mutation_performed": False,
    "crust_reservoir_mutation_performed": False,
    "swept_area_calculated": False,
    "local_segment_link_resolved": False,
    "connected_atom_topology_resolved": False,
    "local_fragment_topology_resolved": False,
}
MODEL_ARRAY_VALUES: dict[str, tuple[str, ...]] = {
    "physical_consensus_status_order": PHYSICAL_CONSENSUS_STATUS_ORDER,
    "heuristic_consensus_status_order": HEURISTIC_CONSENSUS_STATUS_ORDER,
    "assignment_status_order": ASSIGNMENT_STATUS_ORDER,
}
MODEL_FIELDS = (
    frozenset(MODEL_STRING_VALUES)
    | frozenset(MODEL_BOOLEAN_VALUES)
    | frozenset(MODEL_ARRAY_VALUES)
    | {
        "maximum_plate_count",
        "maximum_boundary_segment_count_multiplier",
        "maximum_membership_area_classes_per_cell",
        "maximum_coverage_arrangement_fragments_per_cell",
    }
)

LEDGER_FIELDS = frozenset(
    {
        "format",
        "source_plate_assignment_step_id",
        "boundary_plate_assignment_step_id",
        "boundary_pair_evidence",
        "overlap_class_candidates",
        "physical_polarity_backed_candidate_excess_area_km2",
        "oceanic_heuristic_candidate_excess_area_km2",
        "unresolved_candidate_excess_area_km2",
        "accounted_overlap_excess_area_km2",
        "candidate_partition_residual_km2",
    }
)
PAIR_FIELDS = frozenset(
    {
        "pair_id",
        "plate_low_id",
        "plate_high_id",
        "segment_ids",
        "physical_consensus_status",
        "physical_subducting_plate_id",
        "physical_overriding_plate_id",
        "heuristic_consensus_status",
        "heuristic_subducting_plate_id",
        "heuristic_overriding_plate_id",
    }
)
CLASS_FIELDS = frozenset(
    {
        "membership_area_class_id",
        "destination_cell_id",
        "multiplicity",
        "boundary_pair_evidence_id",
        "assignment_status",
        "candidate_subducting_contributor_id",
        "candidate_overriding_contributor_id",
    }
)


class _InvalidCandidateFateLedger(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise _InvalidCandidateFateLedger(message)


def _integer(value: Any, field: str) -> int:
    if type(value) is not int:
        raise _InvalidCandidateFateLedger(f"{field} must be an integer")
    return value


def _number(value: Any, field: str) -> float:
    if type(value) not in (int, float):
        raise _InvalidCandidateFateLedger(f"{field} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise _InvalidCandidateFateLedger(f"{field} must be finite")
    return number


def _binary64_gamma_bound(operation_count: int, operand_sum: float) -> float:
    return _gamma_bound(
        operation_count,
        operand_sum,
        epsilon=math.ulp(1.0),
        label="binary64",
    )


def _portable_accumulation_serialization_tolerance(
    actual: float,
    expected: float,
    *,
    operation_count: int,
    operand_sum: float,
) -> float:
    _require(
        math.isfinite(actual) and math.isfinite(expected),
        "candidate-fate serialized accumulation operands must be finite",
    )
    gamma_bound = _binary64_gamma_bound(operation_count, operand_sum)
    cast_scale = max(abs(actual), abs(expected))
    binary64_cast_allowance = 2.0 * math.ulp(cast_scale)
    tolerance = gamma_bound + binary64_cast_allowance
    _require(
        math.isfinite(tolerance),
        "candidate-fate serialized accumulation tolerance is not finite",
    )
    return math.nextafter(tolerance, math.inf)


def _gamma_bound(
    operation_count: int,
    operand_sum: float,
    *,
    epsilon: float,
    label: str,
) -> float:
    _require(
        type(operation_count) is int
        and 0 <= operation_count <= MAXIMUM_REPLAY_OPERATION_COUNT,
        f"candidate-fate {label} operation count is invalid",
    )
    _require(
        math.isfinite(operand_sum) and operand_sum >= 0.0,
        f"candidate-fate {label} operand sum is invalid",
    )
    scaled_epsilon = operation_count * epsilon
    _require(
        math.isfinite(scaled_epsilon) and scaled_epsilon < 1.0,
        f"candidate-fate {label} gamma is invalid",
    )
    if scaled_epsilon == 0.0:
        return 0.0
    bound = (scaled_epsilon / (1.0 - scaled_epsilon)) * operand_sum
    _require(
        math.isfinite(bound),
        f"candidate-fate {label} gamma bound is not finite",
    )
    return math.nextafter(bound, math.inf)


def _roles_from_sides(record: Mapping[str, Any], *, prefix: str) -> tuple[int, int]:
    subducting_side = record[f"{prefix}_subducting_side"]
    overriding_side = record[f"{prefix}_overriding_side"]
    _require(
        (subducting_side, overriding_side) in (("left", "right"), ("right", "left")),
        f"{prefix} candidate sides are not opposite left/right roles",
    )
    left_plate_id = _integer(record.get("left_plate_id"), "left_plate_id")
    right_plate_id = _integer(record.get("right_plate_id"), "right_plate_id")
    return (
        left_plate_id if subducting_side == "left" else right_plate_id,
        left_plate_id if overriding_side == "left" else right_plate_id,
    )


def _physical_role(record: Mapping[str, Any]) -> tuple[int, int] | None:
    status = record.get("physical_polarity_status")
    source = record.get("physical_polarity_source")
    subducting_side = record.get("physical_subducting_side")
    overriding_side = record.get("physical_overriding_side")
    confidence = _number(
        record.get("physical_polarity_confidence"),
        "physical_polarity_confidence",
    )
    if (
        status == "unknown_unresolved"
        and source == "none"
        and subducting_side == "unknown"
        and overriding_side == "unknown"
        and confidence == 0.0
    ):
        return None
    _require(status == "resolved", "active physical polarity tuple has an invalid status")
    _require(
        source in {"supplied_constraint", "physical_solver"},
        "resolved physical polarity tuple has an invalid source",
    )
    _require(
        0.0 < confidence <= 1.0,
        "resolved physical polarity tuple has an invalid confidence",
    )
    return _roles_from_sides(record, prefix="physical")


def _heuristic_role(record: Mapping[str, Any]) -> tuple[int, int] | None:
    status = record.get("polarity_candidate_status")
    if status == "left_oceanic_only":
        _require(
            record.get("candidate_subducting_side") == "left"
            and record.get("candidate_overriding_side") == "right",
            "left-oceanic heuristic tuple has invalid sides",
        )
    elif status == "right_oceanic_only":
        _require(
            record.get("candidate_subducting_side") == "right"
            and record.get("candidate_overriding_side") == "left",
            "right-oceanic heuristic tuple has invalid sides",
        )
    else:
        return None
    return _roles_from_sides(record, prefix="candidate")


def _expected_pair_record(
    pair: tuple[int, int],
    records: list[Mapping[str, Any]],
) -> dict[str, Any]:
    low, high = pair
    all_active = all(record.get("convergence_active") is True for record in records)
    physical_status = "not_all_segments_have_active_convergence"
    heuristic_status = "not_all_segments_have_active_convergence"
    physical_role: tuple[int, int] | None = None
    heuristic_role: tuple[int, int] | None = None
    if all_active:
        physical_roles = [_physical_role(record) for record in records]
        resolved_physical_roles = [role for role in physical_roles if role is not None]
        if not resolved_physical_roles:
            physical_status = "all_active_all_physical_polarities_unknown"
        elif len(resolved_physical_roles) != len(physical_roles):
            physical_status = "all_active_mixed_resolved_and_unknown"
        elif len(set(resolved_physical_roles)) != 1:
            physical_status = "all_active_resolved_polarities_conflict"
        else:
            physical_status = "all_active_resolved_polarity_uniform"
            physical_role = resolved_physical_roles[0]

        heuristic_roles = [_heuristic_role(record) for record in records]
        available_heuristic_roles = [role for role in heuristic_roles if role is not None]
        if len(available_heuristic_roles) != len(heuristic_roles):
            heuristic_status = (
                "all_active_one_or_more_unique_oceanic_candidates_unavailable"
            )
        elif len(set(available_heuristic_roles)) != 1:
            heuristic_status = "all_active_unique_oceanic_candidates_conflict"
        else:
            heuristic_status = "all_active_unique_oceanic_candidate_uniform"
            heuristic_role = available_heuristic_roles[0]

    return {
        "pair_id": MAXIMUM_PLATE_COUNT * low + high,
        "plate_low_id": low,
        "plate_high_id": high,
        "segment_ids": [
            _integer(record.get("segment_id"), "boundary segment id")
            for record in records
        ],
        "physical_consensus_status": physical_status,
        "physical_subducting_plate_id": -1 if physical_role is None else physical_role[0],
        "physical_overriding_plate_id": -1 if physical_role is None else physical_role[1],
        "heuristic_consensus_status": heuristic_status,
        "heuristic_subducting_plate_id": -1 if heuristic_role is None else heuristic_role[0],
        "heuristic_overriding_plate_id": -1 if heuristic_role is None else heuristic_role[1],
    }


def _compare_exact_record(
    actual: Any,
    expected: dict[str, Any],
    *,
    fields: frozenset[str],
    label: str,
) -> None:
    _require(isinstance(actual, dict), f"{label} must be an object")
    _require(set(actual) == fields, f"{label} fields do not match the canonical schema")
    for field, expected_value in expected.items():
        actual_value = actual[field]
        if isinstance(expected_value, int):
            _require(type(actual_value) is int, f"{label}.{field} must be an integer")
        elif isinstance(expected_value, list):
            _require(
                isinstance(actual_value, list)
                and all(type(value) is int for value in actual_value),
                f"{label}.{field} must be an integer array",
            )
        else:
            _require(isinstance(actual_value, str), f"{label}.{field} must be a string")
        _require(
            actual_value == expected_value,
            f"{label}.{field} does not replay from boundary and membership roots",
        )


def _preflight_resource_caps(world: Mapping[str, Any]) -> None:
    cells = world.get("cells")
    history = world.get("plate_motion_history")
    _require(isinstance(cells, list) and bool(cells), "cells must be a nonempty array")
    _require(isinstance(history, list) and bool(history), "plate motion history must be nonempty")
    cell_count = len(cells)
    for step_id, step in enumerate(history):
        _require(isinstance(step, dict), f"plate_motion_history[{step_id}] must be an object")
        ledger = step.get("crust_overlap_candidate_fate_ledger")
        _require(isinstance(ledger, dict), f"candidate fate ledger {step_id} is missing")
        pairs = ledger.get("boundary_pair_evidence")
        classes = ledger.get("overlap_class_candidates")
        _require(isinstance(pairs, list), f"candidate fate pair table {step_id} must be an array")
        _require(isinstance(classes, list), f"candidate fate class table {step_id} must be an array")
        boundary_segments = step.get("boundary_segments")
        _require(
            isinstance(boundary_segments, list),
            f"boundary segment root {step_id} must be an array",
        )
        overlap = step.get("crust_overlap_ledger")
        _require(
            isinstance(overlap, dict),
            f"crust overlap root {step_id} must be an object",
        )
        membership = overlap.get("coverage_membership_area_class_ledger")
        _require(
            isinstance(membership, dict),
            f"membership class root {step_id} must be an object",
        )
        membership_areas = membership.get("area_km2")
        _require(
            isinstance(membership_areas, list),
            f"membership class areas {step_id} must be an array",
        )
        fragment_counts = overlap.get(
            "coverage_arrangement_fragment_count_by_cell"
        )
        _require(
            isinstance(fragment_counts, list)
            and len(fragment_counts) == cell_count
            and all(
                type(value) is int
                and 1 <= value <= MAXIMUM_MEMBERSHIP_CLASSES_PER_CELL
                for value in fragment_counts
            ),
            f"coverage arrangement fragment counts {step_id} are invalid",
        )
        _require(
            len(boundary_segments) <= MAXIMUM_BOUNDARY_SEGMENTS_PER_CELL * cell_count,
            f"boundary segment root {step_id} exceeds its resource cap",
        )
        _require(
            len(membership_areas) <= MAXIMUM_MEMBERSHIP_CLASSES_PER_CELL * cell_count,
            f"membership class root {step_id} exceeds its resource cap",
        )
        _require(
            len(pairs) <= len(boundary_segments),
            f"candidate fate pair table {step_id} exceeds its resource cap",
        )
        _require(
            len(classes) <= len(membership_areas),
            f"candidate fate class table {step_id} exceeds its resource cap",
        )
        total_segment_ids = 0
        for pair in pairs:
            _require(isinstance(pair, dict), f"candidate fate pair table {step_id} contains a non-object")
            segment_ids = pair.get("segment_ids")
            _require(isinstance(segment_ids, list), f"candidate fate pair segment IDs {step_id} must be arrays")
            total_segment_ids += len(segment_ids)
            _require(
                total_segment_ids <= len(boundary_segments),
                f"candidate fate pair segment IDs {step_id} exceed their resource cap",
            )


def _validate_model(model: Any) -> None:
    _require(isinstance(model, dict), "candidate fate model is missing")
    _require(
        set(model) == MODEL_FIELDS,
        "candidate fate model fields do not match the canonical schema",
    )
    for field, expected in MODEL_STRING_VALUES.items():
        _require(
            model[field] == expected,
            f"candidate fate model {field} is invalid",
        )
    for field, expected in MODEL_BOOLEAN_VALUES.items():
        _require(
            model[field] is expected,
            f"candidate fate model {field} is invalid",
        )
    for field, expected in MODEL_ARRAY_VALUES.items():
        value = model[field]
        _require(
            isinstance(value, list)
            and all(isinstance(item, str) for item in value)
            and tuple(value) == expected,
            f"candidate fate model {field} is invalid",
        )
    integer_values = {
        "maximum_plate_count": MAXIMUM_PLATE_COUNT,
        "maximum_boundary_segment_count_multiplier": (
            MAXIMUM_BOUNDARY_SEGMENTS_PER_CELL
        ),
        "maximum_membership_area_classes_per_cell": (
            MAXIMUM_MEMBERSHIP_CLASSES_PER_CELL
        ),
        "maximum_coverage_arrangement_fragments_per_cell": (
            MAXIMUM_MEMBERSHIP_CLASSES_PER_CELL
        ),
    }
    for field, expected in integer_values.items():
        _require(
            _integer(model[field], f"candidate fate model {field}") == expected,
            f"candidate fate model {field} is invalid",
        )


def validate_crust_overlap_candidate_fate(
    world: dict[str, Any],
) -> dict[str, Any]:
    """Replay the diagnostically authoritative, physically non-authoritative crosswalk.

    Boundary polarity candidates and membership classes are first required to
    pass their independent root replays.  This validator then reconstructs
    every pair consensus and every multiplicity-at-least-two class assignment;
    it never accepts the serialized pair or area summaries as source operands.
    """

    failures: list[str] = []
    metrics: dict[str, Any] = {
        "independent_boundary_root_replay_passed": False,
        "independent_membership_root_replay_passed": False,
        "every_boundary_pair_consensus_replayed": False,
        "every_overlap_excess_class_candidate_replayed": False,
        "overlap_excess_partition_closed": False,
        "physical_material_fate_resolved": False,
        "slab_selection_resolved": False,
        "slab_transfer_resolved": False,
        "state_mutation_performed": False,
        "deterministic_crosswalk_authoritative": False,
        "pair_wide_consensus_only": False,
        "candidate_allocation_authoritative": False,
        "local_segment_link_resolved": False,
        "connected_atom_topology_resolved": False,
        "local_fragment_topology_resolved": False,
        "swept_area_calculated": False,
        "crust_material_shadow_mutation_performed": False,
        "crust_reservoir_mutation_performed": False,
    }
    try:
        _require(isinstance(world, dict), "world must be an object")
        _preflight_resource_caps(world)
        boundary_result = validate_plate_boundary_edges(world)
        transport_result = validate_crust_overlap_transport(world)
        _require(
            isinstance(boundary_result, dict)
            and boundary_result.get("passed") is True,
            "independent boundary root replay did not pass",
        )
        _require(
            isinstance(transport_result, dict)
            and transport_result.get("passed") is True,
            "independent membership root replay did not pass",
        )
        metrics["independent_boundary_root_replay_passed"] = True
        metrics["independent_membership_root_replay_passed"] = True

        model = world.get("crust_overlap_candidate_fate_model")
        _validate_model(model)
        metrics.update(
            {
                field: model[field]
                for field in (
                    "deterministic_crosswalk_authoritative",
                    "pair_wide_consensus_only",
                    "candidate_allocation_authoritative",
                    "local_segment_link_resolved",
                    "connected_atom_topology_resolved",
                    "local_fragment_topology_resolved",
                    "swept_area_calculated",
                    "crust_material_shadow_mutation_performed",
                    "crust_reservoir_mutation_performed",
                )
            }
        )

        history = world.get("plate_motion_history")
        _require(isinstance(history, list) and bool(history), "plate motion history is missing")
        cell_count = len(world["cells"])
        total_pair_count = 0
        total_class_count = 0
        status_counts: dict[str, int] = defaultdict(int)
        physical_area_terms: list[float] = []
        heuristic_area_terms: list[float] = []
        unresolved_area_terms: list[float] = []
        maximum_partition_residual = 0.0
        maximum_validated_fragment_to_class_row_residual_sum = 0.0
        maximum_candidate_partition_bound = 0.0

        for step_id, step in enumerate(history):
            label = f"plate_motion_history[{step_id}]"
            _require(isinstance(step, dict), f"{label} must be an object")
            _require(
                _integer(step.get("id"), f"{label}.id") == step_id,
                f"{label} id is not canonical",
            )
            plate_count = _integer(step.get("plate_count"), f"{label}.plate_count")
            _require(
                2 <= plate_count <= MAXIMUM_PLATE_COUNT,
                f"{label}.plate_count exceeds the persistent pair-id domain",
            )
            ledger = step.get("crust_overlap_candidate_fate_ledger")
            _require(isinstance(ledger, dict), f"{label} candidate fate ledger is missing")
            _require(set(ledger) == LEDGER_FIELDS, f"{label} candidate fate ledger has an invalid schema")
            _require(ledger["format"] == MODEL_TYPE, f"{label} candidate fate ledger format is invalid")
            expected_source_step = 0 if step_id == 0 else step_id - 1
            _require(
                _integer(ledger["source_plate_assignment_step_id"], f"{label}.source_plate_assignment_step_id")
                == expected_source_step,
                f"{label} source plate assignment step does not replay",
            )
            _require(
                _integer(ledger["boundary_plate_assignment_step_id"], f"{label}.boundary_plate_assignment_step_id")
                == step_id,
                f"{label} boundary plate assignment step does not replay",
            )

            boundary_records = step.get("boundary_segments")
            _require(
                isinstance(boundary_records, list)
                and all(isinstance(record, dict) for record in boundary_records),
                f"{label}.boundary_segments must be an object array",
            )
            pair_groups: dict[tuple[int, int], list[Mapping[str, Any]]] = defaultdict(list)
            for segment_id, record in enumerate(boundary_records):
                _require(
                    _integer(record.get("segment_id"), f"{label}.boundary_segments[{segment_id}].segment_id")
                    == segment_id,
                    f"{label} boundary segment IDs are not canonical",
                )
                left_plate = _integer(record.get("left_plate_id"), "left_plate_id")
                right_plate = _integer(record.get("right_plate_id"), "right_plate_id")
                _require(
                    0 <= left_plate < MAXIMUM_PLATE_COUNT
                    and 0 <= right_plate < MAXIMUM_PLATE_COUNT
                    and left_plate != right_plate,
                    f"{label} boundary segment plate pair is invalid",
                )
                pair_groups[tuple(sorted((left_plate, right_plate)))].append(record)

            expected_pair_records = [
                _expected_pair_record(pair, pair_groups[pair])
                for pair in sorted(pair_groups)
            ]
            actual_pair_records = ledger["boundary_pair_evidence"]
            _require(
                isinstance(actual_pair_records, list)
                and len(actual_pair_records) == len(expected_pair_records),
                f"{label} candidate fate pair table is incomplete or duplicated",
            )
            for pair_index, (actual, expected) in enumerate(
                zip(actual_pair_records, expected_pair_records, strict=True)
            ):
                _compare_exact_record(
                    actual,
                    expected,
                    fields=PAIR_FIELDS,
                    label=f"{label}.boundary_pair_evidence[{pair_index}]",
                )
            pair_by_plate_ids = {
                (record["plate_low_id"], record["plate_high_id"]): record
                for record in expected_pair_records
            }
            pair_segments = {
                pair: pair_groups[pair] for pair in pair_groups
            }
            pair_endpoint_cell_ids = {
                pair: {
                    cell_id
                    for record in records
                    for cell_id in (
                        _integer(record.get("left_cell_id"), "left_cell_id"),
                        _integer(record.get("right_cell_id"), "right_cell_id"),
                    )
                }
                for pair, records in pair_segments.items()
            }

            overlap = step.get("crust_overlap_ledger")
            _require(isinstance(overlap, dict), f"{label}.crust_overlap_ledger is missing")
            membership = overlap.get("coverage_membership_area_class_ledger")
            _require(isinstance(membership, dict), f"{label} membership ledger is missing")
            try:
                class_offsets = membership["destination_offsets"]
                class_areas = membership["area_km2"]
                multiplicities = membership["multiplicity"]
                contributor_offsets = membership["contributor_offsets"]
                source_cell_ids = membership["source_cell_ids"]
                source_plate_ids = membership["source_plate_ids"]
                arrangement_fragment_counts = overlap[
                    "coverage_arrangement_fragment_count_by_cell"
                ]
            except KeyError as exc:
                raise _InvalidCandidateFateLedger(
                    f"{label} membership root is missing {exc.args[0]}"
                ) from exc
            _require(
                isinstance(class_offsets, list)
                and len(class_offsets) == cell_count + 1
                and all(type(value) is int for value in class_offsets),
                f"{label} membership destination offsets are invalid",
            )
            _require(
                isinstance(class_areas, list)
                and isinstance(multiplicities, list)
                and len(class_areas) == len(multiplicities)
                and all(type(value) in (int, float) for value in class_areas)
                and all(type(value) is int for value in multiplicities),
                f"{label} membership class columns are invalid",
            )
            class_count = len(class_areas)
            _require(
                isinstance(contributor_offsets, list)
                and len(contributor_offsets) == class_count + 1
                and all(type(value) is int for value in contributor_offsets)
                and isinstance(source_cell_ids, list)
                and isinstance(source_plate_ids, list)
                and len(source_cell_ids) == len(source_plate_ids)
                and all(type(value) is int for value in source_cell_ids)
                and all(type(value) is int for value in source_plate_ids),
                f"{label} membership contributor columns are invalid",
            )
            _require(
                isinstance(arrangement_fragment_counts, list)
                and len(arrangement_fragment_counts) == cell_count
                and all(
                    type(value) is int
                    and 1 <= value <= MAXIMUM_MEMBERSHIP_CLASSES_PER_CELL
                    for value in arrangement_fragment_counts
                ),
                f"{label} coverage arrangement fragment counts are invalid",
            )

            expected_class_records: list[dict[str, Any]] = []
            step_physical_terms: list[float] = []
            step_heuristic_terms: list[float] = []
            step_unresolved_terms: list[float] = []
            step_excess_terms_by_destination: list[list[float]] = [
                [] for _ in range(cell_count)
            ]
            destination_classes = (
                (class_id, destination)
                for destination in range(cell_count)
                for class_id in range(
                    class_offsets[destination], class_offsets[destination + 1]
                )
            )
            for class_id, destination in destination_classes:
                multiplicity = multiplicities[class_id]
                if multiplicity < 2:
                    continue
                begin = contributor_offsets[class_id]
                end = contributor_offsets[class_id + 1]
                contributors = source_cell_ids[begin:end]
                contributor_plates = source_plate_ids[begin:end]
                distinct_plates = sorted(set(contributor_plates))
                pair: tuple[int, int] | None = None
                pair_record: dict[str, Any] | None = None
                status = "unknown_nonbinary_membership"
                evidence_id = -1
                candidate_subducting = -1
                candidate_overriding = -1
                if multiplicity == 2:
                    status = "unknown_non_distinct_source_plate_pair"
                    if len(distinct_plates) == 2:
                        pair = (distinct_plates[0], distinct_plates[1])
                        pair_record = pair_by_plate_ids.get(pair)
                        status = "unknown_no_same_step_boundary_pair"
                        if pair_record is not None:
                            evidence_id = pair_record["pair_id"]
                            incident = destination in pair_endpoint_cell_ids[pair]
                            status = "unknown_no_same_step_endpoint_incidence"
                            if incident:
                                status = "unknown_no_uniform_pair_polarity_evidence"
                                role: tuple[int, int] | None = None
                                if (
                                    pair_record["physical_consensus_status"]
                                    == "all_active_resolved_polarity_uniform"
                                ):
                                    status = "uniform_resolved_physical_polarity_backed_candidate"
                                    role = (
                                        pair_record["physical_subducting_plate_id"],
                                        pair_record["physical_overriding_plate_id"],
                                    )
                                elif (
                                    pair_record["physical_consensus_status"]
                                    == "all_active_all_physical_polarities_unknown"
                                    and pair_record["heuristic_consensus_status"]
                                    == "all_active_unique_oceanic_candidate_uniform"
                                ):
                                    status = "uniform_oceanic_side_heuristic_candidate"
                                    role = (
                                        pair_record["heuristic_subducting_plate_id"],
                                        pair_record["heuristic_overriding_plate_id"],
                                    )
                                if role is not None:
                                    plate_to_contributor = dict(
                                        zip(
                                            contributor_plates,
                                            range(begin, end),
                                            strict=True,
                                        )
                                    )
                                    _require(
                                        set(plate_to_contributor) == set(role),
                                        f"{label} candidate roles do not match class source plates",
                                    )
                                    candidate_subducting = plate_to_contributor[role[0]]
                                    candidate_overriding = plate_to_contributor[role[1]]

                expected_class_records.append(
                    {
                        "membership_area_class_id": class_id,
                        "destination_cell_id": destination,
                        "multiplicity": multiplicity,
                        "boundary_pair_evidence_id": evidence_id,
                        "assignment_status": status,
                        "candidate_subducting_contributor_id": candidate_subducting,
                        "candidate_overriding_contributor_id": candidate_overriding,
                    }
                )
                area = _number(class_areas[class_id], f"{label} membership class area")
                contribution = (multiplicity - 1) * area
                _require(
                    math.isfinite(contribution) and contribution > 0.0,
                    f"{label} membership-class candidate excess area is invalid",
                )
                step_excess_terms_by_destination[destination].append(contribution)
                if status == "uniform_resolved_physical_polarity_backed_candidate":
                    step_physical_terms.append(contribution)
                elif status == "uniform_oceanic_side_heuristic_candidate":
                    step_heuristic_terms.append(contribution)
                else:
                    step_unresolved_terms.append(contribution)
                status_counts[status] += 1

            actual_class_records = ledger["overlap_class_candidates"]
            _require(
                isinstance(actual_class_records, list)
                and len(actual_class_records) == len(expected_class_records),
                f"{label} candidate fate class table is incomplete or duplicated",
            )
            for record_index, (actual, expected) in enumerate(
                zip(actual_class_records, expected_class_records, strict=True)
            ):
                _compare_exact_record(
                    actual,
                    expected,
                    fields=CLASS_FIELDS,
                    label=f"{label}.overlap_class_candidates[{record_index}]",
                )

            expected_totals = (
                math.fsum(step_physical_terms),
                math.fsum(step_heuristic_terms),
                math.fsum(step_unresolved_terms),
            )
            total_fields = (
                "physical_polarity_backed_candidate_excess_area_km2",
                "oceanic_heuristic_candidate_excess_area_km2",
                "unresolved_candidate_excess_area_km2",
            )
            all_step_terms = step_physical_terms + step_heuristic_terms + step_unresolved_terms
            step_operand_sum = math.fsum(abs(value) for value in all_step_terms)
            for field, expected, terms in zip(
                total_fields,
                expected_totals,
                (step_physical_terms, step_heuristic_terms, step_unresolved_terms),
                strict=True,
            ):
                actual = _number(ledger[field], f"{label}.{field}")
                _require(actual >= 0.0, f"{label}.{field} must be nonnegative")
                _require(
                    abs(actual - expected)
                    <= _portable_accumulation_serialization_tolerance(
                        actual,
                        expected,
                        operation_count=len(terms) * 4 + 4,
                        operand_sum=(
                            2.0 * math.fsum(abs(value) for value in terms)
                            + abs(expected)
                        ),
                    ),
                    f"{label}.{field} does not replay from membership-class assignments",
                )
            expected_accounted = math.fsum(expected_totals)
            actual_accounted = _number(
                ledger["accounted_overlap_excess_area_km2"],
                f"{label}.accounted_overlap_excess_area_km2",
            )
            _require(
                actual_accounted >= 0.0,
                f"{label}.accounted_overlap_excess_area_km2 must be nonnegative",
            )
            _require(
                abs(actual_accounted - expected_accounted)
                <= _portable_accumulation_serialization_tolerance(
                    actual_accounted,
                    expected_accounted,
                    operation_count=len(all_step_terms) * 4 + 3,
                    operand_sum=(
                        4.0 * step_operand_sum + abs(expected_accounted)
                    ),
                ),
                f"{label} accounted overlap excess does not replay",
            )
            root_overlap_excess = _number(
                overlap.get("global_overlap_excess_area_km2"),
                f"{label}.crust_overlap_ledger.global_overlap_excess_area_km2",
            )
            root_excess_by_destination_raw = overlap.get(
                "overlap_excess_area_km2_by_cell"
            )
            _require(
                isinstance(root_excess_by_destination_raw, list)
                and len(root_excess_by_destination_raw) == cell_count
                and all(
                    type(value) in (int, float)
                    and math.isfinite(float(value))
                    and float(value) >= 0.0
                    for value in root_excess_by_destination_raw
                ),
                f"{label} root overlap-excess destination array is invalid",
            )
            root_excess_by_destination = [
                float(value) for value in root_excess_by_destination_raw
            ]
            class_excess_by_destination = [
                math.fsum(terms) for terms in step_excess_terms_by_destination
            ]
            membership_row_residuals = [
                abs(reconstructed - recorded)
                for reconstructed, recorded in zip(
                    class_excess_by_destination,
                    root_excess_by_destination,
                    strict=True,
                )
            ]
            for destination, row_discrepancy in enumerate(
                membership_row_residuals
            ):
                row_class_count = (
                    class_offsets[destination + 1] - class_offsets[destination]
                )
                arrangement_fragment_count = arrangement_fragment_counts[
                    destination
                ]
                _require(
                    row_class_count <= arrangement_fragment_count,
                    f"{label} destination {destination} class count exceeds its fragment count",
                )
                row_operation_bound = _binary64_gamma_bound(
                    operation_count=(
                        arrangement_fragment_count * 8
                        + row_class_count * 8
                        + 16
                    ),
                    operand_sum=(
                        abs(class_excess_by_destination[destination])
                        + abs(root_excess_by_destination[destination])
                    ),
                )
                _require(
                    row_discrepancy <= row_operation_bound,
                    f"{label} destination {destination} binary64 fragment-to-class excess discrepancy is invalid",
                )
            validated_fragment_to_class_row_residual_sum = math.fsum(
                membership_row_residuals
            )
            replayed_global_overlap_excess = 0.0
            for recorded_row_excess in root_excess_by_destination:
                replayed_global_overlap_excess += recorded_row_excess
            _require(
                replayed_global_overlap_excess == root_overlap_excess,
                f"{label} global overlap-excess rows do not replay exactly in binary64 order",
            )
            flat_class_excess = math.fsum(all_step_terms)
            expected_residual = expected_accounted - root_overlap_excess
            actual_residual = _number(
                ledger["candidate_partition_residual_km2"],
                f"{label}.candidate_partition_residual_km2",
            )
            residual_tolerance = _portable_accumulation_serialization_tolerance(
                actual_residual,
                expected_residual,
                operation_count=len(all_step_terms) * 4 + 4,
                operand_sum=(
                    4.0 * step_operand_sum
                    + abs(expected_accounted)
                    + abs(root_overlap_excess)
                    + abs(expected_residual)
                ),
            )
            _require(
                abs(actual_residual - expected_residual) <= residual_tolerance,
                f"{label} candidate partition residual does not replay",
            )
            arithmetic_partition_bound = _binary64_gamma_bound(
                operation_count=(
                    class_count * 16 + cell_count * 16 + 64
                ),
                operand_sum=(
                    4.0 * step_operand_sum
                    + abs(expected_accounted)
                    + abs(flat_class_excess)
                    + abs(root_overlap_excess)
                    + validated_fragment_to_class_row_residual_sum
                ),
            )
            _require(
                abs(expected_accounted - flat_class_excess)
                <= arithmetic_partition_bound,
                f"{label} status-partitioned candidate area does not close to all classes",
            )
            partition_closure_tolerance = math.fsum(
                (
                    validated_fragment_to_class_row_residual_sum,
                    arithmetic_partition_bound,
                )
            )
            _require(
                math.isfinite(partition_closure_tolerance)
                and abs(expected_residual) <= partition_closure_tolerance,
                f"{label} independently reconstructed overlap-excess partition does not close",
            )

            total_pair_count += len(expected_pair_records)
            total_class_count += len(expected_class_records)
            physical_area_terms.extend(step_physical_terms)
            heuristic_area_terms.extend(step_heuristic_terms)
            unresolved_area_terms.extend(step_unresolved_terms)
            maximum_partition_residual = max(
                maximum_partition_residual, abs(expected_residual)
            )
            maximum_validated_fragment_to_class_row_residual_sum = max(
                maximum_validated_fragment_to_class_row_residual_sum,
                validated_fragment_to_class_row_residual_sum,
            )
            maximum_candidate_partition_bound = max(
                maximum_candidate_partition_bound,
                partition_closure_tolerance,
            )

        metrics.update(
            {
                "every_boundary_pair_consensus_replayed": True,
                "every_overlap_excess_class_candidate_replayed": True,
                "overlap_excess_partition_closed": True,
                "history_step_count": len(history),
                "boundary_pair_evidence_count": total_pair_count,
                "overlap_class_candidate_count": total_class_count,
                "assignment_status_counts": dict(sorted(status_counts.items())),
                "physical_polarity_backed_candidate_excess_area_km2": math.fsum(physical_area_terms),
                "oceanic_heuristic_candidate_excess_area_km2": math.fsum(heuristic_area_terms),
                "unresolved_candidate_excess_area_km2": math.fsum(unresolved_area_terms),
                "maximum_candidate_partition_residual_km2": maximum_partition_residual,
                "maximum_validated_fragment_to_class_row_residual_sum_km2": (
                    maximum_validated_fragment_to_class_row_residual_sum
                ),
                "maximum_candidate_partition_bound_km2": (
                    maximum_candidate_partition_bound
                ),
            }
        )
    except (
        _InvalidCandidateFateLedger,
        KeyError,
        IndexError,
        TypeError,
        ValueError,
        OverflowError,
    ) as exc:
        failures.append(str(exc))
    return {"passed": not failures, "failures": failures, "metrics": metrics}


__all__ = ["validate_crust_overlap_candidate_fate"]
