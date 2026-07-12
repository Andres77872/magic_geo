from __future__ import annotations

import heapq
import math
import sys
from collections.abc import Sequence
from typing import Any


MAXIMUM_CELL_COUNT = 200_000
MAXIMUM_HISTORY_STEP_COUNT = 251
MAXIMUM_NEIGHBORS_PER_CELL = 16
MAXIMUM_BOUNDARY_SEGMENTS_PER_CELL = 8
CONFIGURED_MAXIMUM_AGE_MA = 200.0
CDF_THRESHOLDS_MA = tuple(float(value) for value in range(20, 201, 20))

STATUS_NOT_OCEANIC_LIKE = 0
STATUS_RIDGE_SEED = 1
STATUS_RIDGE_REACHABLE = 2
STATUS_RIDGE_REACHABLE_CEILING_CLAMPED = 3
STATUS_UNRESOLVED_NO_ACTIVE_RIDGE_PATH_CEILING = 4

CRUST_TYPE_COUNT = 9
LITHOLOGY_COUNT = 7


MODEL_LITERAL_VALUES: dict[str, Any] = {
    "model_type": "multi_source_nominal_ridge_graph_travel_time_v1",
    "authority_scope": (
        "deterministic_procedural_initial_oceanic_like_age_field_only"
    ),
    "authoritative_ledger_location": "initial_oceanic_crust_age_ledger",
    "authoritative_age_field_location": (
        "initial_oceanic_crust_age_ledger.age_ma_by_cell"
    ),
    "compatibility_cell_alias_location": (
        "cells[].initial_crust_age_ma_where_status_id_is_not_zero"
    ),
    "compatibility_history_alias_location": (
        "plate_motion_history[0].crust_overlap_ledger.remapped_crust_age_ma_"
        "by_cell_where_status_id_is_not_zero"
    ),
    "compatibility_alias_scope": (
        "oceanic_like_ledger_cells_only_non_oceanic_cell_age_aliases_are_"
        "initialized_by_the_separate_continental_crust_rule"
    ),
    "cell_geometry_source": "cells[].position_3d_area_km2_and_neighbors",
    "boundary_source": "plate_motion_history[0].boundary_segments",
    "provisional_crust_state_source": (
        "initial_identity_overlap_categories_thickness_density_with_age_zero"
    ),
    "provisional_age_for_oceanic_predicate_ma": 0.0,
    "oceanic_like_predicate": (
        "crust_type_0_or_crust_type_2_with_lithology_0_or_crust_type_3_with_"
        "age_le_320_ma_thickness_le_18_km_density_ge_2_84_g_cm3"
    ),
    "eligible_ridge_segment_rule": (
        "direct_divergent_segment_with_both_provisional_opening_sides_"
        "oceanic_like_positive_finite_nominal_opening_rate_and_positive_"
        "finite_length"
    ),
    "nonpositive_nominal_opening_rate_policy": (
        "zero_rate_segment_excluded_negative_rate_invalid_and_components_"
        "without_a_positive_rate_seed_receive_the_model_age_ceiling"
    ),
    "ridge_seed_rule": (
        "sorted_unique_left_and_right_cell_ids_of_eligible_ridge_segments"
    ),
    "representative_full_spreading_rate_formula": (
        "sum(segment_signed_opening_rate_km_per_ma_times_segment_length_km)_"
        "divided_by_sum(segment_length_km)"
    ),
    "representative_rate_accumulation_order": (
        "plate_motion_history_zero_boundary_segments_serialized_order"
    ),
    "representative_half_spreading_rate_factor": 0.5,
    "graph_edge_angle_formula": (
        "atan2(norm(cross(source_position_3d,target_position_3d)),clamp(dot("
        "source_position_3d,target_position_3d),-1,1))"
    ),
    "graph_edge_distance_formula": "radius_km_times_graph_edge_angle_rad",
    "graph_edge_age_increment_formula": (
        "graph_edge_distance_km_divided_by_representative_half_spreading_"
        "rate_km_per_ma"
    ),
    "shortest_path_model": (
        "multi_source_dijkstra_over_oceanic_like_cell_neighbor_graph"
    ),
    "queue_order": "ascending_accumulated_age_ma_then_ascending_cell_id",
    "neighbor_order": "cells[].neighbors_serialized_order",
    "equal_path_tie_rule": (
        "strictly_lower_age_updates_only_first_discovered_equal_age_path_"
        "retained"
    ),
    "non_oceanic_like_age_rule": "exact_zero_ma",
    "reachable_oceanic_like_age_rule": (
        "clamp(shortest_path_graph_age_ma,zero,maximum_model_age_ma)"
    ),
    "unreachable_oceanic_like_age_rule": (
        "maximum_model_age_ma_with_unresolved_no_active_ridge_path_status"
    ),
    "configured_maximum_model_age_ma": CONFIGURED_MAXIMUM_AGE_MA,
    "effective_maximum_age_formula": (
        "min(configured_maximum_model_age_ma,1000_times_geological_age_ga)"
    ),
    "age_unit": "Ma",
    "distance_unit": "km",
    "spreading_rate_unit": "km_per_ma",
    "cell_area_unit": "km2",
    "status_id_order": [
        "not_oceanic_like",
        "ridge_seed",
        "ridge_reachable",
        "ridge_reachable_ceiling_clamped",
        "unresolved_no_active_ridge_path_ceiling",
    ],
    "unclamped_graph_age_unavailable_sentinel": (
        "negative_one_for_non_oceanic_like_or_unreachable_cells"
    ),
    "array_index": "canonical_cell_id",
    "array_serialization_model": "decimal_max_digits10_binary64_round_trip",
    "cdf_threshold_location": (
        "initial_oceanic_crust_age_ledger.cdf_thresholds_ma"
    ),
    "cdf_threshold_selection": (
        "fixed_20_ma_increments_from_20_through_200_for_external_validation_"
        "output_not_generation_input"
    ),
    "cdf_value_location": (
        "initial_oceanic_crust_age_ledger.area_weighted_cdf_le_threshold"
    ),
    "cdf_formula": (
        "sum(cells_area_km2_where_oceanic_like_and_age_ma_le_threshold)_"
        "divided_by_total_oceanic_like_area_km2"
    ),
    "cdf_threshold_comparison": "inclusive_less_than_or_equal",
    "procedural_authority": True,
    "path_decision_witness_exposed": True,
    "independent_replay_inputs_unconditionally_exposed": False,
    "independent_replay_requires_cells_output": True,
    "physical_seafloor_creation_resolved": False,
    "spreading_rate_calibrated": False,
    "local_spreading_rates_resolved": False,
    "ridge_flowlines_resolved": False,
    "subduction_sink_history_resolved": False,
    "convergence_history_resolved": False,
    "seton_2020_age_grid_used_as_generation_input": False,
    "model_limitation": (
        "procedural_graph_distance_age_initialization_using_one_global_"
        "nominal_half_spreading_rate_without_physical_plate_reconstruction_"
        "flowlines_or_crust_creation_and_destruction_history"
    ),
}


LEDGER_FIELDS = frozenset(
    {
        "source_plate_motion_history_id",
        "cell_count",
        "oceanic_like_cell_count",
        "non_oceanic_like_cell_count",
        "eligible_ridge_segment_count",
        "ridge_seed_cell_count",
        "reachable_oceanic_like_cell_count",
        "unreachable_oceanic_like_cell_count",
        "reachable_ceiling_clamped_cell_count",
        "ceiling_assigned_cell_count",
        "eligible_ridge_total_length_km",
        "opening_rate_length_sum_km2_per_ma",
        "representative_full_spreading_rate_km_per_ma",
        "representative_half_spreading_rate_km_per_ma",
        "maximum_age_ma",
        "oceanic_like_area_km2",
        "area_weighted_mean_age_ma",
        "minimum_oceanic_like_age_ma",
        "maximum_oceanic_like_age_ma",
        "eligible_ridge_segment_ids",
        "ridge_seed_cell_ids",
        "age_ma_by_cell",
        "unclamped_graph_age_ma_by_cell",
        "status_id_by_cell",
        "predecessor_cell_id_by_cell",
        "origin_ridge_seed_cell_id_by_cell",
        "cdf_thresholds_ma",
        "area_weighted_cdf_le_threshold",
    }
)


class _InvalidInitialOceanicCrustAge(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise _InvalidInitialOceanicCrustAge(message)


def _finite(value: Any, field: str) -> float:
    _require(type(value) in (int, float), f"{field} must be numeric")
    result = float(value)
    _require(math.isfinite(result), f"{field} must be finite")
    return result


def _integer(value: Any, field: str) -> int:
    _require(type(value) is int, f"{field} must be an integer")
    return value


def _sequence(value: Any, field: str, *, length: int) -> Sequence[Any]:
    _require(
        isinstance(value, (list, tuple)) and len(value) == length,
        f"{field} must contain exactly {length} values",
    )
    return value


def _close(actual: float, expected: float, *, operations: int = 1) -> bool:
    scale = max(abs(actual), abs(expected))
    ulp = math.ulp(scale)
    # Both sides are binary64 calculations from round-trip inputs.  This
    # envelope covers ordered arithmetic and platform libm variation without
    # introducing a geophysical tolerance.
    bound = max(
        64.0 * ulp,
        min(max(1, operations), MAXIMUM_CELL_COUNT)
        * 8.0
        * sys.float_info.epsilon
        * max(scale, sys.float_info.min),
    )
    return abs(actual - expected) <= bound


def _assert_close(
    actual_value: Any,
    expected: float,
    field: str,
    *,
    operations: int = 1,
) -> float:
    actual = _finite(actual_value, field)
    _require(
        _close(actual, expected, operations=operations),
        f"{field} does not replay",
    )
    return abs(actual - expected)


def _int_array(value: Any, field: str, cell_count: int) -> list[int]:
    raw = _sequence(value, field, length=cell_count)
    return [_integer(item, f"{field}[{index}]") for index, item in enumerate(raw)]


def _float_array(value: Any, field: str, cell_count: int) -> list[float]:
    raw = _sequence(value, field, length=cell_count)
    return [_finite(item, f"{field}[{index}]") for index, item in enumerate(raw)]


def _validate_model(model: Any, maximum_age_ma: float) -> None:
    _require(
        isinstance(model, dict),
        "initial_oceanic_crust_age_model must be an object",
    )
    expected_fields = set(MODEL_LITERAL_VALUES) | {"effective_maximum_age_ma"}
    _require(
        set(model) == expected_fields,
        "initial_oceanic_crust_age_model fields do not match the canonical schema",
    )
    for field, expected in MODEL_LITERAL_VALUES.items():
        actual = model[field]
        if type(expected) is bool:
            _require(
                actual is expected,
                f"initial_oceanic_crust_age_model.{field} is invalid",
            )
        elif type(expected) is float:
            _require(
                _finite(
                    actual, f"initial_oceanic_crust_age_model.{field}"
                )
                == expected,
                f"initial_oceanic_crust_age_model.{field} is invalid",
            )
        else:
            _require(
                actual == expected,
                f"initial_oceanic_crust_age_model.{field} is invalid",
            )
    _assert_close(
        model["effective_maximum_age_ma"],
        maximum_age_ma,
        "initial_oceanic_crust_age_model.effective_maximum_age_ma",
    )


def _provisional_oceanic_like(
    crust_type: int,
    lithology: int,
    thickness_km: float,
    density_g_cm3: float,
) -> bool:
    _require(
        0 <= crust_type < CRUST_TYPE_COUNT,
        "provisional crust type is outside its enum range",
    )
    _require(
        0 <= lithology < LITHOLOGY_COUNT,
        "provisional lithology is outside its enum range",
    )
    _require(thickness_km >= 0.0, "provisional crust thickness is negative")
    _require(density_g_cm3 > 0.0, "provisional crust density is not positive")
    if crust_type == 0:
        return True
    if crust_type == 2:
        return lithology == 0
    if crust_type != 3:
        return False
    return thickness_km <= 18.0 and density_g_cm3 >= 2.84


def _position(cell: Any, cell_id: int) -> tuple[float, float, float]:
    label = f"cells[{cell_id}]"
    _require(isinstance(cell, dict), f"{label} must be an object")
    _require(_integer(cell.get("id"), f"{label}.id") == cell_id, f"{label}.id is not canonical")
    raw = _sequence(cell.get("position_3d"), f"{label}.position_3d", length=3)
    position = tuple(
        _finite(value, f"{label}.position_3d[{axis}]")
        for axis, value in enumerate(raw)
    )
    norm_squared = (
        position[0] * position[0]
        + position[1] * position[1]
        + position[2] * position[2]
    )
    _require(
        abs(norm_squared - 1.0) <= 1.0e-10,
        f"{label}.position_3d is not a unit vector",
    )
    return position


def _great_circle_distance_km(
    radius_km: float,
    first: tuple[float, float, float],
    second: tuple[float, float, float],
) -> float:
    cross_x = first[1] * second[2] - first[2] * second[1]
    cross_y = first[2] * second[0] - first[0] * second[2]
    cross_z = first[0] * second[1] - first[1] * second[0]
    cross_norm = math.sqrt(
        cross_x * cross_x + cross_y * cross_y + cross_z * cross_z
    )
    dot = (
        first[0] * second[0]
        + first[1] * second[1]
        + first[2] * second[2]
    )
    angle = math.atan2(cross_norm, min(1.0, max(-1.0, dot)))
    distance = radius_km * angle
    _require(
        math.isfinite(distance) and distance >= 0.0,
        "initial oceanic crust age graph edge distance is invalid",
    )
    return distance


def _compare_float_array(
    actual: list[float],
    expected: list[float],
    field: str,
    *,
    operations: int,
) -> float:
    maximum_residual = 0.0
    for index, (actual_value, expected_value) in enumerate(
        zip(actual, expected, strict=True)
    ):
        residual = abs(actual_value - expected_value)
        maximum_residual = max(maximum_residual, residual)
        _require(
            _close(actual_value, expected_value, operations=operations),
            f"{field}[{index}] does not replay",
        )
    return maximum_residual


def validate_initial_oceanic_crust_age(world: Any) -> dict[str, Any]:
    """Independently replay the complete procedural initial-age witness."""

    failures: list[str] = []
    metrics: dict[str, Any] = {
        "cell_count": 0,
        "boundary_segment_count": 0,
        "oceanic_like_cell_count": 0,
        "eligible_ridge_segment_count": 0,
        "ridge_seed_cell_count": 0,
        "reachable_oceanic_like_cell_count": 0,
        "unreachable_oceanic_like_cell_count": 0,
        "reachable_ceiling_clamped_cell_count": 0,
        "dijkstra_queue_push_count": 0,
        "maximum_absolute_age_replay_residual_ma": 0.0,
        "maximum_absolute_summary_replay_residual": 0.0,
        "provisional_oceanic_mask_replayed": False,
        "eligible_ridge_segments_replayed": False,
        "representative_spreading_rates_replayed": False,
        "ridge_seed_cells_replayed": False,
        "dijkstra_unclamped_ages_replayed": False,
        "dijkstra_path_witness_replayed": False,
        "clamped_ages_and_status_replayed": False,
        "summary_statistics_replayed": False,
        "cdf_replayed": False,
        "oceanic_cell_aliases_replayed": False,
        "oceanic_history_aliases_replayed": False,
        "procedural_authority": False,
        "physical_seafloor_creation_resolved": False,
        "spreading_rate_calibrated": False,
        "local_spreading_rates_resolved": False,
        "ridge_flowlines_resolved": False,
        "subduction_sink_history_resolved": False,
        "convergence_history_resolved": False,
        "seton_2020_age_grid_used_as_generation_input": False,
    }
    try:
        _require(isinstance(world, dict), "world must be an object")
        cells = world.get("cells")
        history = world.get("plate_motion_history")
        _require(
            isinstance(cells, list) and 0 < len(cells) <= MAXIMUM_CELL_COUNT,
            "cells must be a nonempty bounded array",
        )
        _require(
            isinstance(history, list)
            and 0 < len(history) <= MAXIMUM_HISTORY_STEP_COUNT,
            "plate_motion_history must be a nonempty bounded array",
        )
        cell_count = len(cells)
        metrics["cell_count"] = cell_count

        kinematic = world.get("plate_kinematic_model")
        _require(isinstance(kinematic, dict), "plate_kinematic_model must be an object")
        boundary_model = world.get("plate_boundary_segment_model")
        _require(
            isinstance(boundary_model, dict),
            "plate_boundary_segment_model must be an object",
        )
        radius_km = _finite(
            boundary_model.get("radius_km"),
            "plate_boundary_segment_model.radius_km",
        )
        geological_age_ga = _finite(
            kinematic.get("tectonic_process_geological_age_ga_input"),
            "plate_kinematic_model.tectonic_process_geological_age_ga_input",
        )
        _require(
            100.0 < radius_km <= 100_000.0,
            "planet_parameters.radius_km is outside configured bounds",
        )
        _require(
            0.01 <= geological_age_ga <= 100.0,
            "planet_parameters.geological_age_ga is outside configured bounds",
        )
        maximum_age_ma = max(
            0.0,
            min(CONFIGURED_MAXIMUM_AGE_MA, geological_age_ga * 1000.0),
        )
        _validate_model(world.get("initial_oceanic_crust_age_model"), maximum_age_ma)
        planet = world.get("planet_parameters")
        if planet is not None:
            _require(isinstance(planet, dict), "planet_parameters must be an object")
            _assert_close(
                planet.get("radius_km"),
                radius_km,
                "planet_parameters.radius_km",
            )
            _assert_close(
                planet.get("geological_age_ga"),
                geological_age_ga,
                "planet_parameters.geological_age_ga",
            )

        ledger = world.get("initial_oceanic_crust_age_ledger")
        _require(
            isinstance(ledger, dict),
            "initial_oceanic_crust_age_ledger must be an object",
        )
        _require(
            set(ledger) == LEDGER_FIELDS,
            "initial_oceanic_crust_age_ledger fields do not match the canonical schema",
        )
        _require(
            _integer(
                ledger.get("source_plate_motion_history_id"),
                "initial_oceanic_crust_age_ledger.source_plate_motion_history_id",
            )
            == 0,
            "initial age source history id must be zero",
        )
        _require(
            _integer(ledger.get("cell_count"), "initial age ledger cell_count")
            == cell_count,
            "initial age ledger cell_count does not match cells",
        )

        step_zero = history[0]
        _require(isinstance(step_zero, dict), "plate_motion_history[0] must be an object")
        overlap = step_zero.get("crust_overlap_ledger")
        _require(
            isinstance(overlap, dict),
            "plate_motion_history[0].crust_overlap_ledger must be an object",
        )
        types = _int_array(
            overlap.get("remapped_crust_type_by_cell"),
            "plate_motion_history[0].crust_overlap_ledger.remapped_crust_type_by_cell",
            cell_count,
        )
        lithologies = _int_array(
            overlap.get("remapped_lithology_by_cell"),
            "plate_motion_history[0].crust_overlap_ledger.remapped_lithology_by_cell",
            cell_count,
        )
        history_ages = _float_array(
            overlap.get("remapped_crust_age_ma_by_cell"),
            "plate_motion_history[0].crust_overlap_ledger.remapped_crust_age_ma_by_cell",
            cell_count,
        )
        thicknesses = _float_array(
            overlap.get("remapped_crust_thickness_km_by_cell"),
            "plate_motion_history[0].crust_overlap_ledger.remapped_crust_thickness_km_by_cell",
            cell_count,
        )
        densities = _float_array(
            overlap.get("remapped_crust_density_by_cell"),
            "plate_motion_history[0].crust_overlap_ledger.remapped_crust_density_by_cell",
            cell_count,
        )

        positions: list[tuple[float, float, float]] = []
        areas: list[float] = []
        neighbors: list[list[int]] = []
        total_neighbor_references = 0
        for cell_id, cell in enumerate(cells):
            positions.append(_position(cell, cell_id))
            area = _finite(cell.get("area_km2"), f"cells[{cell_id}].area_km2")
            _require(area >= 0.0, f"cells[{cell_id}].area_km2 is negative")
            areas.append(area)
            raw_neighbors = cell.get("neighbors")
            _require(
                isinstance(raw_neighbors, list)
                and len(raw_neighbors) <= MAXIMUM_NEIGHBORS_PER_CELL,
                f"cells[{cell_id}].neighbors exceeds the operational cap",
            )
            row: list[int] = []
            seen: set[int] = set()
            for edge_index, raw_neighbor in enumerate(raw_neighbors):
                neighbor_id = _integer(
                    raw_neighbor, f"cells[{cell_id}].neighbors[{edge_index}]"
                )
                _require(
                    0 <= neighbor_id < cell_count and neighbor_id != cell_id,
                    f"cells[{cell_id}].neighbors[{edge_index}] is invalid",
                )
                _require(
                    neighbor_id not in seen,
                    f"cells[{cell_id}].neighbors contains a duplicate",
                )
                seen.add(neighbor_id)
                row.append(neighbor_id)
            total_neighbor_references += len(row)
            _require(
                total_neighbor_references
                <= MAXIMUM_NEIGHBORS_PER_CELL * cell_count,
                "cell neighbor graph exceeds the operational cap",
            )
            neighbors.append(row)

        oceanic = [
            _provisional_oceanic_like(
                crust_type,
                lithology,
                thickness,
                density,
            )
            for crust_type, lithology, thickness, density in zip(
                types, lithologies, thicknesses, densities, strict=True
            )
        ]
        oceanic_count = sum(oceanic)
        metrics["oceanic_like_cell_count"] = oceanic_count
        metrics["provisional_oceanic_mask_replayed"] = True

        records = step_zero.get("boundary_segments")
        _require(
            isinstance(records, list),
            "plate_motion_history[0].boundary_segments must be an array",
        )
        _require(
            len(records) <= MAXIMUM_BOUNDARY_SEGMENTS_PER_CELL * cell_count,
            "initial boundary segment array exceeds the operational cap",
        )
        metrics["boundary_segment_count"] = len(records)
        eligible_ids: list[int] = []
        seed_ids: list[int] = []
        length_sum = 0.0
        rate_length_sum = 0.0
        for segment_id, record in enumerate(records):
            label = f"plate_motion_history[0].boundary_segments[{segment_id}]"
            _require(isinstance(record, dict), f"{label} must be an object")
            _require(
                _integer(record.get("segment_id"), f"{label}.segment_id")
                == segment_id,
                f"{label}.segment_id is not canonical",
            )
            left_id = _integer(record.get("left_cell_id"), f"{label}.left_cell_id")
            right_id = _integer(record.get("right_cell_id"), f"{label}.right_cell_id")
            _require(
                0 <= left_id < right_id < cell_count,
                f"{label} cell ids are invalid",
            )
            for side, cell_id in (("left", left_id), ("right", right_id)):
                _require(
                    _integer(
                        record.get(f"{side}_opening_crust_type"),
                        f"{label}.{side}_opening_crust_type",
                    )
                    == types[cell_id],
                    f"{label} {side} opening crust type does not mirror the initial identity state",
                )
                _require(
                    _integer(
                        record.get(f"{side}_opening_lithology"),
                        f"{label}.{side}_opening_lithology",
                    )
                    == lithologies[cell_id],
                    f"{label} {side} opening lithology does not mirror the initial identity state",
                )
                _assert_close(
                    record.get(f"{side}_opening_crust_age_ma"),
                    history_ages[cell_id],
                    f"{label}.{side}_opening_crust_age_ma",
                )
                _assert_close(
                    record.get(f"{side}_opening_crust_thickness_km"),
                    thicknesses[cell_id],
                    f"{label}.{side}_opening_crust_thickness_km",
                )
                _assert_close(
                    record.get(f"{side}_opening_crust_density_g_cm3"),
                    densities[cell_id],
                    f"{label}.{side}_opening_crust_density_g_cm3",
                )
                available = not (
                    history_ages[cell_id] == 0.0 and thicknesses[cell_id] == 0.0
                )
                _require(
                    record.get(f"{side}_opening_crust_state_available")
                    is available,
                    f"{label}.{side}_opening_crust_state_available does not replay",
                )
                _require(
                    record.get(f"{side}_opening_oceanic_like")
                    is oceanic[cell_id],
                    f"{label}.{side}_opening_oceanic_like does not replay "
                    "from the provisional state",
                )

            length = _finite(record.get("length_km"), f"{label}.length_km")
            rate = _finite(
                record.get("signed_opening_rate_km_per_ma"),
                f"{label}.signed_opening_rate_km_per_ma",
            )
            _require(length > 0.0, f"{label}.length_km must be positive")
            relative = tuple(
                _finite(
                    record.get(f"relative_velocity_{axis}_km_per_ma"),
                    f"{label}.relative_velocity_{axis}_km_per_ma",
                )
                for axis in ("x", "y", "z")
            )
            normal = tuple(
                _finite(
                    record.get(f"left_to_right_normal_unit_{axis}"),
                    f"{label}.left_to_right_normal_unit_{axis}",
                )
                for axis in ("x", "y", "z")
            )
            expected_rate = (
                relative[0] * normal[0]
                + relative[1] * normal[1]
                + relative[2] * normal[2]
            )
            _require(
                _close(rate, expected_rate, operations=5),
                f"{label}.signed_opening_rate_km_per_ma does not replay from segment vectors",
            )

            direct_class = record.get("direct_boundary_class")
            _require(
                isinstance(direct_class, str),
                f"{label}.direct_boundary_class must be a string",
            )
            candidate = (
                direct_class == "divergent"
                and oceanic[left_id]
                and oceanic[right_id]
            )
            if not candidate:
                continue
            _require(
                rate >= 0.0,
                f"{label} eligible divergent opening rate is negative",
            )
            if rate == 0.0:
                continue
            eligible_ids.append(segment_id)
            length_sum += length
            rate_length_sum += rate * length
            seed_ids.extend((left_id, right_id))

        eligible_ids.sort()
        seed_ids = sorted(set(seed_ids))
        full_rate = rate_length_sum / length_sum if length_sum > 0.0 else 0.0
        half_rate = 0.5 * full_rate
        _require(
            math.isfinite(half_rate) and half_rate >= 0.0,
            "representative half spreading rate is invalid",
        )
        metrics["eligible_ridge_segment_count"] = len(eligible_ids)
        metrics["ridge_seed_cell_count"] = len(seed_ids)
        metrics["eligible_ridge_segments_replayed"] = True
        metrics["representative_spreading_rates_replayed"] = True
        metrics["ridge_seed_cells_replayed"] = True

        ages = [math.inf if is_oceanic else 0.0 for is_oceanic in oceanic]
        statuses = [STATUS_NOT_OCEANIC_LIKE] * cell_count
        predecessors = [-1] * cell_count
        origins = [-1] * cell_count
        pending: list[tuple[float, int]] = []
        queue_push_count = 0
        if half_rate > 0.0:
            for cell_id in seed_ids:
                _require(oceanic[cell_id], "ridge seed is not provisionally oceanic-like")
                ages[cell_id] = 0.0
                statuses[cell_id] = STATUS_RIDGE_SEED
                origins[cell_id] = cell_id
                heapq.heappush(pending, (0.0, cell_id))
                queue_push_count += 1

        queue_push_cap = total_neighbor_references + len(seed_ids)
        while pending:
            current_age, cell_id = heapq.heappop(pending)
            if current_age != ages[cell_id]:
                continue
            for neighbor_id in neighbors[cell_id]:
                if not oceanic[neighbor_id]:
                    continue
                edge_age = (
                    _great_circle_distance_km(
                        radius_km, positions[cell_id], positions[neighbor_id]
                    )
                    / half_rate
                )
                candidate_age = current_age + edge_age
                _require(
                    math.isfinite(candidate_age) and candidate_age >= 0.0,
                    "initial oceanic crust age Dijkstra candidate is invalid",
                )
                if candidate_age < ages[neighbor_id]:
                    ages[neighbor_id] = candidate_age
                    predecessors[neighbor_id] = cell_id
                    origins[neighbor_id] = origins[cell_id]
                    heapq.heappush(pending, (candidate_age, neighbor_id))
                    queue_push_count += 1
                    _require(
                        queue_push_count <= queue_push_cap,
                        "initial age Dijkstra queue exceeds the graph-derived cap",
                    )
        metrics["dijkstra_queue_push_count"] = queue_push_count

        unclamped = [-1.0] * cell_count
        clamped = [0.0] * cell_count
        reachable_count = 0
        unreachable_count = 0
        ceiling_clamped_count = 0
        for cell_id in range(cell_count):
            if not oceanic[cell_id]:
                continue
            if not math.isfinite(ages[cell_id]):
                clamped[cell_id] = maximum_age_ma
                statuses[cell_id] = STATUS_UNRESOLVED_NO_ACTIVE_RIDGE_PATH_CEILING
                unreachable_count += 1
                continue
            unclamped[cell_id] = ages[cell_id]
            reachable_count += 1
            if ages[cell_id] > maximum_age_ma:
                statuses[cell_id] = STATUS_RIDGE_REACHABLE_CEILING_CLAMPED
                ceiling_clamped_count += 1
            elif statuses[cell_id] != STATUS_RIDGE_SEED:
                statuses[cell_id] = STATUS_RIDGE_REACHABLE
            clamped[cell_id] = min(maximum_age_ma, max(0.0, ages[cell_id]))

        metrics["reachable_oceanic_like_cell_count"] = reachable_count
        metrics["unreachable_oceanic_like_cell_count"] = unreachable_count
        metrics["reachable_ceiling_clamped_cell_count"] = ceiling_clamped_count

        actual_eligible = _int_array(
            ledger.get("eligible_ridge_segment_ids"),
            "initial_oceanic_crust_age_ledger.eligible_ridge_segment_ids",
            len(eligible_ids),
        )
        actual_seeds = _int_array(
            ledger.get("ridge_seed_cell_ids"),
            "initial_oceanic_crust_age_ledger.ridge_seed_cell_ids",
            len(seed_ids),
        )
        _require(actual_eligible == eligible_ids, "eligible ridge segment ids do not replay")
        _require(actual_seeds == seed_ids, "ridge seed cell ids do not replay")

        actual_ages = _float_array(
            ledger.get("age_ma_by_cell"),
            "initial_oceanic_crust_age_ledger.age_ma_by_cell",
            cell_count,
        )
        actual_unclamped = _float_array(
            ledger.get("unclamped_graph_age_ma_by_cell"),
            "initial_oceanic_crust_age_ledger.unclamped_graph_age_ma_by_cell",
            cell_count,
        )
        actual_statuses = _int_array(
            ledger.get("status_id_by_cell"),
            "initial_oceanic_crust_age_ledger.status_id_by_cell",
            cell_count,
        )
        actual_predecessors = _int_array(
            ledger.get("predecessor_cell_id_by_cell"),
            "initial_oceanic_crust_age_ledger.predecessor_cell_id_by_cell",
            cell_count,
        )
        actual_origins = _int_array(
            ledger.get("origin_ridge_seed_cell_id_by_cell"),
            "initial_oceanic_crust_age_ledger.origin_ridge_seed_cell_id_by_cell",
            cell_count,
        )
        residual = max(
            _compare_float_array(
                actual_ages,
                clamped,
                "initial_oceanic_crust_age_ledger.age_ma_by_cell",
                operations=cell_count,
            ),
            _compare_float_array(
                actual_unclamped,
                unclamped,
                "initial_oceanic_crust_age_ledger.unclamped_graph_age_ma_by_cell",
                operations=cell_count,
            ),
        )
        metrics["maximum_absolute_age_replay_residual_ma"] = residual
        _require(actual_statuses == statuses, "initial age status ids do not replay")
        _require(
            actual_predecessors == predecessors,
            "initial age Dijkstra predecessors do not replay",
        )
        _require(actual_origins == origins, "initial age Dijkstra origins do not replay")
        metrics["dijkstra_unclamped_ages_replayed"] = True
        metrics["dijkstra_path_witness_replayed"] = True
        metrics["clamped_ages_and_status_replayed"] = True

        oceanic_area = 0.0
        age_area_sum = 0.0
        minimum_age = math.inf
        maximum_oceanic_age = 0.0
        cdf_area = [0.0] * len(CDF_THRESHOLDS_MA)
        for is_oceanic, area, age in zip(oceanic, areas, clamped, strict=True):
            if not is_oceanic:
                continue
            oceanic_area += area
            age_area_sum += area * age
            minimum_age = min(minimum_age, age)
            maximum_oceanic_age = max(maximum_oceanic_age, age)
            for threshold_index, threshold in enumerate(CDF_THRESHOLDS_MA):
                if age <= threshold:
                    cdf_area[threshold_index] += area
        if oceanic_count == 0:
            minimum_age = 0.0
        mean_age = age_area_sum / oceanic_area if oceanic_area > 0.0 else 0.0
        cdf = (
            [area / oceanic_area for area in cdf_area]
            if oceanic_area > 0.0
            else [0.0] * len(CDF_THRESHOLDS_MA)
        )

        expected_integers = {
            "oceanic_like_cell_count": oceanic_count,
            "non_oceanic_like_cell_count": cell_count - oceanic_count,
            "eligible_ridge_segment_count": len(eligible_ids),
            "ridge_seed_cell_count": len(seed_ids),
            "reachable_oceanic_like_cell_count": reachable_count,
            "unreachable_oceanic_like_cell_count": unreachable_count,
            "reachable_ceiling_clamped_cell_count": ceiling_clamped_count,
            "ceiling_assigned_cell_count": unreachable_count + ceiling_clamped_count,
        }
        for field, expected in expected_integers.items():
            _require(
                _integer(ledger.get(field), f"initial_oceanic_crust_age_ledger.{field}")
                == expected,
                f"initial_oceanic_crust_age_ledger.{field} does not replay",
            )
        expected_scalars = {
            "eligible_ridge_total_length_km": length_sum,
            "opening_rate_length_sum_km2_per_ma": rate_length_sum,
            "representative_full_spreading_rate_km_per_ma": full_rate,
            "representative_half_spreading_rate_km_per_ma": half_rate,
            "maximum_age_ma": maximum_age_ma,
            "oceanic_like_area_km2": oceanic_area,
            "area_weighted_mean_age_ma": mean_age,
            "minimum_oceanic_like_age_ma": minimum_age,
            "maximum_oceanic_like_age_ma": maximum_oceanic_age,
        }
        maximum_summary_residual = 0.0
        for field, expected in expected_scalars.items():
            maximum_summary_residual = max(
                maximum_summary_residual,
                _assert_close(
                    ledger.get(field),
                    expected,
                    f"initial_oceanic_crust_age_ledger.{field}",
                    operations=max(cell_count, len(records)),
                ),
            )
        metrics["maximum_absolute_summary_replay_residual"] = maximum_summary_residual
        metrics["summary_statistics_replayed"] = True

        actual_thresholds = _float_array(
            ledger.get("cdf_thresholds_ma"),
            "initial_oceanic_crust_age_ledger.cdf_thresholds_ma",
            len(CDF_THRESHOLDS_MA),
        )
        _require(
            actual_thresholds == list(CDF_THRESHOLDS_MA),
            "initial age CDF thresholds do not match the fixed selection",
        )
        actual_cdf = _float_array(
            ledger.get("area_weighted_cdf_le_threshold"),
            "initial_oceanic_crust_age_ledger.area_weighted_cdf_le_threshold",
            len(CDF_THRESHOLDS_MA),
        )
        _compare_float_array(
            actual_cdf,
            cdf,
            "initial_oceanic_crust_age_ledger.area_weighted_cdf_le_threshold",
            operations=cell_count,
        )
        metrics["cdf_replayed"] = True

        for cell_id, status in enumerate(statuses):
            if status == STATUS_NOT_OCEANIC_LIKE:
                continue
            _assert_close(
                cells[cell_id].get("initial_crust_age_ma"),
                clamped[cell_id],
                f"cells[{cell_id}].initial_crust_age_ma",
                operations=cell_count,
            )
            _require(
                _close(history_ages[cell_id], clamped[cell_id], operations=cell_count),
                "plate_motion_history[0] oceanic initial age alias does not replay",
            )
        metrics["oceanic_cell_aliases_replayed"] = True
        metrics["oceanic_history_aliases_replayed"] = True

        for field in (
            "procedural_authority",
            "physical_seafloor_creation_resolved",
            "spreading_rate_calibrated",
            "local_spreading_rates_resolved",
            "ridge_flowlines_resolved",
            "subduction_sink_history_resolved",
            "convergence_history_resolved",
            "seton_2020_age_grid_used_as_generation_input",
        ):
            metrics[field] = world["initial_oceanic_crust_age_model"][field]
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        failures.append(str(exc))

    return {"passed": not failures, "failures": failures, "metrics": metrics}


__all__ = [
    "CDF_THRESHOLDS_MA",
    "CONFIGURED_MAXIMUM_AGE_MA",
    "MAXIMUM_CELL_COUNT",
    "MAXIMUM_HISTORY_STEP_COUNT",
    "MODEL_LITERAL_VALUES",
    "STATUS_NOT_OCEANIC_LIKE",
    "STATUS_RIDGE_REACHABLE",
    "STATUS_RIDGE_REACHABLE_CEILING_CLAMPED",
    "STATUS_RIDGE_SEED",
    "STATUS_UNRESOLVED_NO_ACTIVE_RIDGE_PATH_CEILING",
    "validate_initial_oceanic_crust_age",
]
