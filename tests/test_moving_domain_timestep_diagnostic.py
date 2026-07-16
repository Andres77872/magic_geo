from __future__ import annotations

import json
import math
from fractions import Fraction
from pathlib import Path
from unittest import TestCase

from magic_geo.config import WorldConfig, config_to_native, load_config
from magic_geo.native import generate_geo_world


REFINEMENTS = ((5.0, 2), (2.5, 4), (1.25, 8), (0.625, 16))
NOMINAL_HORIZON_MA = 10.0
MESH_BACKENDS = ("fibonacci_sphere", "geodesic_icosahedron")

MATERIAL_BRANCH_FIELDS = (
    "cell_plate_ids",
    "crust_type_by_cell",
    "lithology_by_cell",
)
ROUTING_BRANCH_FIELDS = (
    "is_water",
    "is_river",
    "is_lake",
    "lake_overflows",
    "water_body_type",
    "flow_to_cell_id",
    "depression_component_id",
    "depression_sink_cell_id",
)
FINAL_ROUTING_BRANCH_FIELDS = (
    "is_water",
    "is_river",
    "is_lake",
    "lake_overflows",
    "water_body_type",
    "flow_to",
    "depression_component_id",
    "depression_sink_cell_id",
)

# These fields deliberately span transported crust, thresholded terrain and
# routing, and downstream climate/hydrology.  A decreasing difference in this
# small panel is evidence, not a convergence certificate.
CONTINUOUS_FIELDS = (
    "elevation_m",
    "crust_thickness_km",
    "crust_density",
    "crust_age_ma",
    "sediment_thickness_m",
    "sediment_alluvium_entrainment_m",
    "sediment_bedrock_erosion_m",
    "sediment_export_m",
    "cumulative_tectonic_elevation_change_m",
    "cumulative_crust_transport_distance_km",
    "temperature_c",
    "precipitation_mm_y",
    "runoff_mm_y",
    "water_depth_m",
)
CATEGORICAL_FIELDS = ("plate_id", "crust_type", "is_water", "flow_to")
CRUST_INVENTORY_FIELDS = (
    "crust_volume_km3",
    "density_weighted_crust_volume",
    "crust_age_volume_moment_km3_ma",
)


def _config(
    mesh_backend: str,
    timestep_ma: float,
    iterations: int,
) -> WorldConfig:
    data = load_config(Path("configs/earthlike_seed.yaml")).model_dump(
        mode="python"
    )
    data["run"]["seed"] = 20260711
    data["mesh"]["backend"] = mesh_backend
    data["mesh"]["cell_count"] = 128
    data["tectonics"]["plate_count"] = 8
    data["erosion"]["iterations"] = iterations
    data["erosion"]["maturation_timestep_ma"] = timestep_ma
    data["compute"]["backend"] = "cpu"
    data["compute"]["threads"] = 1
    data["output"]["float_precision"] = 8
    return WorldConfig.model_validate(data)


def _area_weighted_mismatch(left: dict, right: dict, field: str) -> float:
    mismatched_area_km2 = 0.0
    total_area_km2 = 0.0
    for left_cell, right_cell in zip(
        left["cells"], right["cells"], strict=True
    ):
        area_km2 = float(left_cell["area_km2"])
        total_area_km2 += area_km2
        if left_cell[field] != right_cell[field]:
            mismatched_area_km2 += area_km2
    return mismatched_area_km2 / total_area_km2


def _require_exact_int(value: object, context: str) -> int:
    if type(value) is not int:
        raise AssertionError(f"{context} must be an exact integer")
    return value


def _require_exact_bool(value: object, context: str) -> bool:
    if type(value) is not bool:
        raise AssertionError(f"{context} must be an exact boolean")
    return value


def _require_finite_float(value: object, context: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AssertionError(f"{context} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise AssertionError(f"{context} must be finite")
    return result


def _validate_refinement_alignment(worlds: list[dict]) -> tuple[float, ...]:
    if len(worlds) != len(REFINEMENTS):
        raise AssertionError("moving-domain refinement count is inconsistent")
    if not worlds or not worlds[0].get("cells"):
        raise AssertionError("moving-domain refinement worlds have no cells")

    reference_cells = worlds[0]["cells"]
    cell_count = len(reference_cells)
    reference_areas: list[float] = []
    for cell_id, cell in enumerate(reference_cells):
        if _require_exact_int(cell.get("id"), f"reference cell {cell_id} id") != cell_id:
            raise AssertionError("reference cells are not in canonical id order")
        area_km2 = _require_finite_float(
            cell.get("area_km2"), f"reference cell {cell_id} area"
        )
        if area_km2 <= 0.0:
            raise AssertionError("reference cell area must be positive")
        reference_areas.append(area_km2)

    for world_index, ((timestep_ma, iterations), world) in enumerate(
        zip(REFINEMENTS, worlds, strict=True)
    ):
        cells = world.get("cells")
        if not isinstance(cells, list) or len(cells) != cell_count:
            raise AssertionError(
                f"refinement world {world_index} does not share the reference mesh"
            )
        for cell_id, (cell, reference_area) in enumerate(
            zip(cells, reference_areas, strict=True)
        ):
            if _require_exact_int(
                cell.get("id"), f"world {world_index} cell {cell_id} id"
            ) != cell_id:
                raise AssertionError("refinement cells are not in canonical id order")
            area_km2 = _require_finite_float(
                cell.get("area_km2"),
                f"world {world_index} cell {cell_id} area",
            )
            if area_km2 != reference_area:
                raise AssertionError("refinement worlds do not share exact cell areas")
            for field in (
                "is_water",
                "is_river",
                "is_lake",
                "lake_overflows",
            ):
                _require_exact_bool(
                    cell.get(field),
                    f"world {world_index} final cell {cell_id} {field}",
                )
            water_body_type = cell.get("water_body_type")
            if not isinstance(water_body_type, str) or not water_body_type:
                raise AssertionError("final routing water-body type is invalid")
            for field in (
                "flow_to",
                "depression_component_id",
                "depression_sink_cell_id",
            ):
                value = _require_exact_int(
                    cell.get(field),
                    f"world {world_index} final cell {cell_id} {field}",
                )
                if field in {"flow_to", "depression_sink_cell_id"} and not (
                    -1 <= value < cell_count
                ):
                    raise AssertionError(f"final routing {field} is out of range")
                if field == "depression_component_id" and not (
                    -1 <= value < cell_count
                ):
                    raise AssertionError("final depression component id is out of range")

        clock = world.get("simulation_clock", {})
        if (
            _require_finite_float(
                clock.get("nominal_timestep_ma"),
                f"world {world_index} nominal timestep",
            )
            != timestep_ma
            or _require_exact_int(
                clock.get("nominal_timed_transition_count"),
                f"world {world_index} transition count",
            )
            != iterations
            or _require_finite_float(
                clock.get("current_nominal_elapsed_time_ma"),
                f"world {world_index} nominal horizon",
            )
            != NOMINAL_HORIZON_MA
        ):
            raise AssertionError("refinement clock metadata is inconsistent")

        plate_history = world.get("plate_motion_history")
        if not isinstance(plate_history, list) or len(plate_history) != iterations + 1:
            raise AssertionError("plate-motion history length is inconsistent")
        for step_index, step in enumerate(plate_history):
            if (
                _require_exact_int(
                    step.get("id"),
                    f"world {world_index} plate step {step_index} id",
                )
                != step_index
                or _require_exact_int(
                    step.get("cell_count"),
                    f"world {world_index} plate step {step_index} cell count",
                )
                != cell_count
                or _require_finite_float(
                    step.get("nominal_elapsed_time_ma"),
                    f"world {world_index} plate step {step_index} time",
                )
                != step_index * timestep_ma
            ):
                raise AssertionError("plate-motion history alignment is inconsistent")
            for field in MATERIAL_BRANCH_FIELDS:
                values = step.get(field)
                if not isinstance(values, list) or len(values) != cell_count:
                    raise AssertionError(
                        f"plate-motion branch field {field} has invalid length"
                    )
                for cell_id, value in enumerate(values):
                    exact = _require_exact_int(
                        value,
                        f"world {world_index} plate step {step_index} "
                        f"cell {cell_id} {field}",
                    )
                    if exact < 0:
                        raise AssertionError(
                            f"plate-motion branch field {field} is negative"
                        )

        routing_history = world.get("fluvial_sediment_routing_history")
        if not isinstance(routing_history, list) or len(routing_history) != iterations:
            raise AssertionError("fluvial routing history length is inconsistent")
        for stage_index, stage in enumerate(routing_history):
            if (
                _require_exact_int(
                    stage.get("id"),
                    f"world {world_index} routing stage {stage_index} id",
                )
                != stage_index
                or _require_exact_int(
                    stage.get("cell_count"),
                    f"world {world_index} routing stage {stage_index} cell count",
                )
                != cell_count
                or _require_exact_int(
                    stage.get("input_cell_count"),
                    f"world {world_index} routing stage {stage_index} input count",
                )
                != cell_count
                or _require_finite_float(
                    stage.get("nominal_interval_start_ma"),
                    f"world {world_index} routing stage {stage_index} start",
                )
                != stage_index * timestep_ma
                or _require_finite_float(
                    stage.get("nominal_interval_end_ma"),
                    f"world {world_index} routing stage {stage_index} end",
                )
                != (stage_index + 1) * timestep_ma
                or _require_finite_float(
                    stage.get("nominal_interval_duration_ma"),
                    f"world {world_index} routing stage {stage_index} duration",
                )
                != timestep_ma
            ):
                raise AssertionError("fluvial routing history alignment is inconsistent")
            inputs = stage.get("input_cells")
            if not isinstance(inputs, list) or len(inputs) != cell_count:
                raise AssertionError("fluvial routing input snapshot is incomplete")
            for cell_id, (input_cell, reference_area) in enumerate(
                zip(inputs, reference_areas, strict=True)
            ):
                if _require_exact_int(
                    input_cell.get("cell_id"),
                    f"world {world_index} routing stage {stage_index} input id",
                ) != cell_id:
                    raise AssertionError(
                        "fluvial routing inputs are not in canonical id order"
                    )
                if _require_finite_float(
                    input_cell.get("cell_area_km2"),
                    f"world {world_index} routing stage {stage_index} "
                    f"cell {cell_id} area",
                ) != reference_area:
                    raise AssertionError("fluvial routing input area is inconsistent")
                for field in (
                    "is_water",
                    "is_river",
                    "is_lake",
                    "lake_overflows",
                ):
                    _require_exact_bool(
                        input_cell.get(field),
                        f"world {world_index} routing stage {stage_index} "
                        f"cell {cell_id} {field}",
                    )
                water_body_type = input_cell.get("water_body_type")
                if not isinstance(water_body_type, str) or not water_body_type:
                    raise AssertionError("routing water-body type is invalid")
                for field in (
                    "flow_to_cell_id",
                    "depression_component_id",
                    "depression_sink_cell_id",
                ):
                    value = _require_exact_int(
                        input_cell.get(field),
                        f"world {world_index} routing stage {stage_index} "
                        f"cell {cell_id} {field}",
                    )
                    if field in {"flow_to_cell_id", "depression_sink_cell_id"}:
                        if not -1 <= value < cell_count:
                            raise AssertionError(f"routing {field} is out of range")
                    elif not -1 <= value < cell_count:
                        raise AssertionError(
                            "routing depression component id is out of range"
                        )

    return tuple(reference_areas)


def _history_wide_discrete_branch_invariant_cell_ids(
    worlds: list[dict],
) -> tuple[int, ...]:
    reference_areas = _validate_refinement_alignment(worlds)
    stable_cell_ids: list[int] = []
    for cell_id in range(len(reference_areas)):
        material_states: set[tuple[int, int, int]] = set()
        routing_states: set[tuple[object, ...]] = set()
        for world in worlds:
            for step in world["plate_motion_history"]:
                material_states.add(
                    tuple(
                        _require_exact_int(
                            step[field][cell_id],
                            f"plate branch {field} for cell {cell_id}",
                        )
                        for field in MATERIAL_BRANCH_FIELDS
                    )
                )
            for stage in world["fluvial_sediment_routing_history"]:
                input_cell = stage["input_cells"][cell_id]
                routing_states.add(
                    tuple(input_cell[field] for field in ROUTING_BRANCH_FIELDS)
                )
            final_cell = world["cells"][cell_id]
            routing_states.add(
                tuple(final_cell[field] for field in FINAL_ROUTING_BRANCH_FIELDS)
            )
        if len(material_states) == 1 and len(routing_states) == 1:
            stable_cell_ids.append(cell_id)
    return tuple(stable_cell_ids)


def _area_weighted_error_partition(
    left: dict,
    right: dict,
    field: str,
    discrete_branch_invariant_cell_ids: tuple[int, ...],
) -> dict[str, float | bool | str]:
    stable_ids = frozenset(discrete_branch_invariant_cell_ids)
    full_area = Fraction(0)
    included_area = Fraction(0)
    excluded_area = Fraction(0)
    full_sse = Fraction(0)
    included_sse = Fraction(0)
    excluded_sse = Fraction(0)
    full_l1_terms: list[float] = []
    included_l1_terms: list[float] = []
    excluded_l1_terms: list[float] = []

    for cell_id, (left_cell, right_cell) in enumerate(
        zip(left["cells"], right["cells"], strict=True)
    ):
        area_km2 = _require_finite_float(
            left_cell.get("area_km2"), f"error cell {cell_id} area"
        )
        if area_km2 != _require_finite_float(
            right_cell.get("area_km2"), f"right error cell {cell_id} area"
        ):
            raise AssertionError("error worlds do not share exact cell areas")
        difference = _require_finite_float(
            left_cell.get(field), f"left error cell {cell_id} {field}"
        ) - _require_finite_float(
            right_cell.get(field), f"right error cell {cell_id} {field}"
        )
        squared_error_term = area_km2 * difference * difference
        absolute_error_term = area_km2 * abs(difference)
        if not math.isfinite(squared_error_term) or not math.isfinite(
            absolute_error_term
        ):
            raise AssertionError("area-weighted error term is not finite")
        area_exact = Fraction.from_float(area_km2)
        sse_exact = Fraction.from_float(squared_error_term)
        full_area += area_exact
        full_sse += sse_exact
        full_l1_terms.append(absolute_error_term)
        if cell_id in stable_ids:
            included_area += area_exact
            included_sse += sse_exact
            included_l1_terms.append(absolute_error_term)
        else:
            excluded_area += area_exact
            excluded_sse += sse_exact
            excluded_l1_terms.append(absolute_error_term)

    if full_area <= 0 or included_area <= 0 or excluded_area <= 0:
        raise AssertionError(
            "discrete-branch-invariant diagnostic requires nonempty included "
            "and excluded area"
        )
    exact_partition_closed = (
        full_area == included_area + excluded_area
        and full_sse == included_sse + excluded_sse
    )
    if not exact_partition_closed:
        raise AssertionError(
            "discrete-branch-invariant exact SSE partition did not close"
        )

    if full_sse > 0:
        included_sse_share = float(included_sse / full_sse)
        excluded_sse_share = float(excluded_sse / full_sse)
    else:
        included_sse_share = 1.0
        excluded_sse_share = 0.0
    return {
        "binary64_squared_error_term_partition_model": (
            "exact_rational_sum_of_each_rounded_binary64_"
            "area_times_squared_difference_term_v1"
        ),
        "full_domain_area_weighted_l1": math.fsum(full_l1_terms)
        / float(full_area),
        "full_domain_area_weighted_l2": math.sqrt(float(full_sse / full_area)),
        "discrete_branch_invariant_area_weighted_l1": math.fsum(
            included_l1_terms
        )
        / float(included_area),
        "discrete_branch_invariant_area_weighted_l2": math.sqrt(
            float(included_sse / included_area)
        ),
        "recorded_discrete_branch_change_area_weighted_l1": math.fsum(
            excluded_l1_terms
        )
        / float(excluded_area),
        "recorded_discrete_branch_change_area_weighted_l2": math.sqrt(
            float(excluded_sse / excluded_area)
        ),
        "full_domain_sse_numerator": float(full_sse),
        "discrete_branch_invariant_included_sse_numerator": float(
            included_sse
        ),
        "recorded_discrete_branch_change_excluded_sse_numerator": float(
            excluded_sse
        ),
        "discrete_branch_invariant_included_sse_share": included_sse_share,
        "recorded_discrete_branch_change_excluded_sse_share": (
            excluded_sse_share
        ),
        "exact_binary64_term_area_and_sse_partition_closed": (
            exact_partition_closed
        ),
        "exact_binary64_term_area_partition_residual_km2": 0.0,
        "exact_binary64_term_sse_partition_residual": 0.0,
    }


def _endpoint_extensives(world: dict) -> dict[str, float]:
    cells = world["cells"]
    return {
        "crust_volume_km3": math.fsum(
            float(cell["area_km2"]) * float(cell["crust_thickness_km"])
            for cell in cells
        ),
        "density_weighted_crust_volume": math.fsum(
            float(cell["area_km2"])
            * float(cell["crust_thickness_km"])
            * float(cell["crust_density"])
            for cell in cells
        ),
        "crust_age_volume_moment_km3_ma": math.fsum(
            float(cell["area_km2"])
            * float(cell["crust_thickness_km"])
            * float(cell["crust_age_ma"])
            for cell in cells
        ),
        "sediment_volume_km3": math.fsum(
            float(cell["area_km2"])
            * float(cell["sediment_thickness_m"])
            / 1000.0
            for cell in cells
        ),
        "surface_water_volume_km3": math.fsum(
            float(cell["area_km2"])
            * max(0.0, float(cell["water_depth_m"]))
            / 1000.0
            for cell in cells
        ),
    }


def _relative_difference(left: float, right: float) -> float:
    return abs(left - right) / max(abs(right), 1.0e-30)


def _maximum_transport_inventory_relative_error(world: dict) -> float:
    maximum = 0.0
    for step in world["plate_motion_history"]:
        ledger = step["crust_overlap_ledger"]
        source = ledger["source_inventory"]
        transported = ledger["transported_inventory"]
        for field in CRUST_INVENTORY_FIELDS:
            maximum = max(
                maximum,
                _relative_difference(
                    float(source[field]),
                    float(transported[field]),
                ),
            )
    return maximum


def _diagnose_backend(worlds: list[dict]) -> dict:
    discrete_branch_invariant_cell_ids = (
        _history_wide_discrete_branch_invariant_cell_ids(worlds)
    )
    stable_id_set = frozenset(discrete_branch_invariant_cell_ids)
    reference_areas = tuple(float(cell["area_km2"]) for cell in worlds[0]["cells"])
    full_area_exact = sum(
        (Fraction.from_float(area) for area in reference_areas), Fraction(0)
    )
    stable_area_exact = sum(
        (
            Fraction.from_float(area)
            for cell_id, area in enumerate(reference_areas)
            if cell_id in stable_id_set
        ),
        Fraction(0),
    )
    excluded_area_exact = full_area_exact - stable_area_exact
    if stable_area_exact <= 0 or excluded_area_exact <= 0:
        raise AssertionError(
            "discrete-branch-invariant cohort must partition nonempty areas"
        )

    adjacent_pair_labels = [
        f"{left_timestep:g}_to_{right_timestep:g}_ma"
        for (left_timestep, _), (right_timestep, _) in zip(
            REFINEMENTS, REFINEMENTS[1:]
        )
    ]
    successive_comparison_labels = [
        f"{adjacent_pair_labels[index + 1]}_over_{adjacent_pair_labels[index]}"
        for index in range(len(adjacent_pair_labels) - 1)
    ]
    continuous: dict[str, dict[str, object]] = {}
    nondecreasing_l2_fields_by_comparison = {
        label: [] for label in successive_comparison_labels
    }
    for field in CONTINUOUS_FIELDS:
        adjacent_errors: list[dict[str, object]] = []
        for pair_index, (left, right) in enumerate(
            zip(worlds, worlds[1:])
        ):
            partition = _area_weighted_error_partition(
                left,
                right,
                field,
                discrete_branch_invariant_cell_ids,
            )
            adjacent_errors.append(
                {
                    "pair": adjacent_pair_labels[pair_index],
                    "left_timestep_ma": REFINEMENTS[pair_index][0],
                    "right_timestep_ma": REFINEMENTS[pair_index + 1][0],
                    **partition,
                }
            )

        full_l1 = [
            float(error["full_domain_area_weighted_l1"])
            for error in adjacent_errors
        ]
        full_l2 = [
            float(error["full_domain_area_weighted_l2"])
            for error in adjacent_errors
        ]
        stable_l1 = [
            float(error["discrete_branch_invariant_area_weighted_l1"])
            for error in adjacent_errors
        ]
        stable_l2 = [
            float(error["discrete_branch_invariant_area_weighted_l2"])
            for error in adjacent_errors
        ]
        full_l1_ratios = [
            full_l1[index + 1] / full_l1[index]
            if full_l1[index] > 0.0
            else None
            for index in range(len(full_l1) - 1)
        ]
        full_l2_ratios = [
            full_l2[index + 1] / full_l2[index]
            if full_l2[index] > 0.0
            else None
            for index in range(len(full_l2) - 1)
        ]
        stable_l1_ratios = [
            stable_l1[index + 1] / stable_l1[index]
            if stable_l1[index] > 0.0
            else None
            for index in range(len(stable_l1) - 1)
        ]
        stable_l2_ratios = [
            stable_l2[index + 1] / stable_l2[index]
            if stable_l2[index] > 0.0
            else None
            for index in range(len(stable_l2) - 1)
        ]
        full_observed_l2_orders = [
            math.log2(full_l2[index] / full_l2[index + 1])
            if full_l2[index] > 0.0 and full_l2[index + 1] > 0.0
            else None
            for index in range(len(full_l2) - 1)
        ]
        stable_observed_l2_orders = [
            math.log2(stable_l2[index] / stable_l2[index + 1])
            if stable_l2[index] > 0.0 and stable_l2[index + 1] > 0.0
            else None
            for index in range(len(stable_l2) - 1)
        ]
        continuous[field] = {
            "primary_error_domain": "full_domain",
            "adjacent_refinement_errors": adjacent_errors,
            "successive_full_domain_l1_error_ratios": full_l1_ratios,
            "successive_full_domain_l2_error_ratios": full_l2_ratios,
            "successive_full_domain_observed_l2_orders": (
                full_observed_l2_orders
            ),
            "successive_discrete_branch_invariant_l1_error_ratios": (
                stable_l1_ratios
            ),
            "successive_discrete_branch_invariant_l2_error_ratios": (
                stable_l2_ratios
            ),
            "successive_discrete_branch_invariant_observed_l2_orders": (
                stable_observed_l2_orders
            ),
        }
        for comparison_index, ratio in enumerate(full_l2_ratios):
            if ratio is not None and ratio >= 1.0:
                nondecreasing_l2_fields_by_comparison[
                    successive_comparison_labels[comparison_index]
                ].append(field)

    categorical = {
        field: {
            "adjacent_area_mismatch_fraction": [
                _area_weighted_mismatch(left, right, field)
                for left, right in zip(worlds, worlds[1:])
            ]
        }
        for field in CATEGORICAL_FIELDS
    }

    extensives = [_endpoint_extensives(world) for world in worlds]
    extensive_differences = {
        field: {
            "adjacent_relative_difference": [
                _relative_difference(left[field], right[field])
                for left, right in zip(extensives, extensives[1:])
            ]
        }
        for field in extensives[0]
    }

    return {
        "cell_count": len(worlds[0]["cells"]),
        "adjacent_pair_labels": adjacent_pair_labels,
        "successive_comparison_labels": successive_comparison_labels,
        "full_domain_errors_are_primary": True,
        "history_wide_discrete_branch_invariant_cohort": {
            "scope": (
                "exact_history_wide_serialized_discrete_material_and_"
                "routing_branch_selectors_across_all_refinement_levels_v1"
            ),
            "selection_uses_error_magnitudes": False,
            "continuous_threshold_branch_stability_resolved": False,
            "material_snapshot_family": "plate_motion_history",
            "material_fields": list(MATERIAL_BRANCH_FIELDS),
            "routing_snapshot_family": (
                "fluvial_sediment_routing_history.input_cells_plus_final_cells"
            ),
            "routing_input_fields": list(ROUTING_BRANCH_FIELDS),
            "routing_final_fields": list(FINAL_ROUTING_BRANCH_FIELDS),
            "predicate": (
                "include_cell_iff_material_signature_set_cardinality_is_one_"
                "and_routing_signature_set_cardinality_is_one_across_every_"
                "snapshot_and_all_four_refinement_levels"
            ),
            "exclusion_rule": (
                "exclude_every_cell_with_any_recorded_discrete_material_or_"
                "routing_branch_change_in_any_snapshot_or_refinement_level"
            ),
            "cell_ids": list(discrete_branch_invariant_cell_ids),
            "cell_count": len(discrete_branch_invariant_cell_ids),
            "excluded_cell_count": (
                len(worlds[0]["cells"])
                - len(discrete_branch_invariant_cell_ids)
            ),
            "area_km2": float(stable_area_exact),
            "excluded_area_km2": float(excluded_area_exact),
            "area_fraction": float(stable_area_exact / full_area_exact),
            "excluded_area_fraction": float(
                excluded_area_exact / full_area_exact
            ),
            "area_partition_exact": (
                full_area_exact == stable_area_exact + excluded_area_exact
            ),
            "interpretation": (
                "attribution_subset_only_full_domain_errors_remain_primary"
            ),
        },
        "continuous": continuous,
        "categorical": categorical,
        "endpoint_extensives": extensives,
        "endpoint_extensive_relative_differences": extensive_differences,
        "nondecreasing_full_domain_l2_fields_by_successive_comparison": (
            nondecreasing_l2_fields_by_comparison
        ),
        "maximum_transport_inventory_relative_error": max(
            _maximum_transport_inventory_relative_error(world)
            for world in worlds
        ),
    }


class MovingDomainTimestepDiagnosticTests(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.worlds = {
            backend: [
                generate_geo_world(
                    config_to_native(
                        _config(backend, timestep_ma, iterations)
                    )
                )
                for timestep_ma, iterations in REFINEMENTS
            ]
            for backend in MESH_BACKENDS
        }

    def test_moving_domain_panel_is_diagnostic_not_a_certificate(self) -> None:
        panel: dict[str, object] = {
            "schema": "moving_domain_timestep_diagnostic_v2",
            "seed": 20260711,
            "nominal_horizon_ma": NOMINAL_HORIZON_MA,
            "refinements": [
                {"timestep_ma": timestep, "iterations": iterations}
                for timestep, iterations in REFINEMENTS
            ],
            "interpretation": "diagnostic_only_not_convergence_certificate",
            "full_domain_errors_are_primary": True,
            "history_wide_discrete_branch_invariant_cohort_is_attribution_only": (
                True
            ),
            "continuous_threshold_and_clamp_branch_stability_resolved": False,
            "time_step_convergence_demonstrated": False,
            "missing_certificate_dimensions": [
                "multi_seed_variance",
                "spatial_refinement",
                "full_domain_categorical_and_routing_topology_convergence",
                "continuous_threshold_and_clamp_branch_stability",
                "global_rigid_rotation_and_permutation_invariance",
            ],
            "mesh_backends": {},
        }

        for backend, worlds in self.worlds.items():
            finest_rotations = {
                int(plate["id"]): float(plate["cumulative_rotation_deg"])
                for plate in worlds[-1]["plates"]
            }
            for (timestep_ma, iterations), world in zip(
                REFINEMENTS, worlds, strict=True
            ):
                clock = world["simulation_clock"]
                self.assertEqual(
                    float(clock["current_nominal_elapsed_time_ma"]),
                    NOMINAL_HORIZON_MA,
                )
                self.assertEqual(
                    float(clock["nominal_timestep_ma"]), timestep_ma
                )
                self.assertEqual(
                    int(clock["nominal_timed_transition_count"]), iterations
                )
                self.assertFalse(clock["time_step_convergence_demonstrated"])
                self.assertFalse(clock["physical_time_resolved"])
                self.assertFalse(clock["nominal_time_calibrated"])
                for plate in world["plates"]:
                    self.assertAlmostEqual(
                        float(plate["cumulative_rotation_deg"]),
                        finest_rotations[int(plate["id"])],
                        delta=2.0e-7,
                    )

            # Confirm that this is a moving-overlap panel, rather than another
            # fixed-domain composition test.
            moving_steps = [
                step
                for world in worlds
                for step in world["plate_motion_history"][1:]
            ]
            self.assertGreater(
                max(
                    max(step["crust_overlap_ledger"]["source_kinematic_distance_km"])
                    for step in moving_steps
                ),
                0.0,
            )
            self.assertTrue(
                any(
                    max(
                        step["crust_overlap_ledger"][
                            "contributor_count_by_cell"
                        ]
                    )
                    > 1
                    for step in moving_steps
                )
            )

            diagnostic = _diagnose_backend(worlds)
            self.assertTrue(diagnostic["full_domain_errors_are_primary"])
            self.assertLessEqual(
                diagnostic["maximum_transport_inventory_relative_error"],
                1.0e-10,
            )
            cohort = diagnostic[
                "history_wide_discrete_branch_invariant_cohort"
            ]
            self.assertFalse(cohort["selection_uses_error_magnitudes"])
            self.assertFalse(
                cohort["continuous_threshold_branch_stability_resolved"]
            )
            self.assertTrue(cohort["area_partition_exact"])
            self.assertGreater(cohort["cell_count"], 0)
            self.assertGreater(cohort["excluded_cell_count"], 0)
            self.assertEqual(
                cohort["cell_count"] + cohort["excluded_cell_count"],
                diagnostic["cell_count"],
            )
            self.assertEqual(
                cohort["cell_ids"],
                list(
                    _history_wide_discrete_branch_invariant_cell_ids(
                        worlds
                    )
                ),
            )
            self.assertGreater(cohort["area_fraction"], 0.0)
            self.assertLess(cohort["area_fraction"], 1.0)
            self.assertAlmostEqual(
                cohort["area_fraction"] + cohort["excluded_area_fraction"],
                1.0,
                delta=1.0e-15,
            )
            for field_metrics in diagnostic["continuous"].values():
                self.assertEqual(
                    field_metrics["primary_error_domain"], "full_domain"
                )
                adjacent_errors = field_metrics[
                    "adjacent_refinement_errors"
                ]
                self.assertEqual(
                    len(adjacent_errors), len(REFINEMENTS) - 1
                )
                for expected_pair, error in zip(
                    diagnostic["adjacent_pair_labels"],
                    adjacent_errors,
                    strict=True,
                ):
                    self.assertEqual(error["pair"], expected_pair)
                    self.assertTrue(
                        error[
                            "exact_binary64_term_area_and_sse_partition_closed"
                        ]
                    )
                    self.assertEqual(
                        error[
                            "exact_binary64_term_area_partition_residual_km2"
                        ],
                        0.0,
                    )
                    self.assertEqual(
                        error[
                            "exact_binary64_term_sse_partition_residual"
                        ],
                        0.0,
                    )
                    for key, value in error.items():
                        if isinstance(value, float):
                            self.assertTrue(math.isfinite(value), msg=key)
                    for key in (
                        "full_domain_area_weighted_l1",
                        "full_domain_area_weighted_l2",
                        "discrete_branch_invariant_area_weighted_l1",
                        "discrete_branch_invariant_area_weighted_l2",
                        "recorded_discrete_branch_change_area_weighted_l1",
                        "recorded_discrete_branch_change_area_weighted_l2",
                        "full_domain_sse_numerator",
                        "discrete_branch_invariant_included_sse_numerator",
                        "recorded_discrete_branch_change_excluded_sse_numerator",
                    ):
                        self.assertGreaterEqual(error[key], 0.0, msg=key)
                    included_share = error[
                        "discrete_branch_invariant_included_sse_share"
                    ]
                    excluded_share = error[
                        "recorded_discrete_branch_change_excluded_sse_share"
                    ]
                    self.assertGreaterEqual(included_share, 0.0)
                    self.assertLessEqual(included_share, 1.0)
                    self.assertGreaterEqual(excluded_share, 0.0)
                    self.assertLessEqual(excluded_share, 1.0)
                    self.assertAlmostEqual(
                        included_share + excluded_share,
                        1.0,
                        delta=1.0e-15,
                    )
                for ratios_key in (
                    "successive_full_domain_l1_error_ratios",
                    "successive_full_domain_l2_error_ratios",
                    "successive_full_domain_observed_l2_orders",
                    "successive_discrete_branch_invariant_l1_error_ratios",
                    "successive_discrete_branch_invariant_l2_error_ratios",
                    "successive_discrete_branch_invariant_observed_l2_orders",
                ):
                    ratios = field_metrics[ratios_key]
                    self.assertEqual(len(ratios), len(REFINEMENTS) - 2)
                    for value in ratios:
                        if value is not None:
                            self.assertTrue(math.isfinite(value))
            for field_metrics in diagnostic["categorical"].values():
                values = field_metrics["adjacent_area_mismatch_fraction"]
                self.assertEqual(len(values), len(REFINEMENTS) - 1)
                for value in values:
                    self.assertGreaterEqual(value, 0.0)
                    self.assertLessEqual(value, 1.0)
            panel["mesh_backends"][backend] = diagnostic

        # Emit one concise machine-readable line for audit capture.  The test
        # does not convert a favorable single-seed ratio into a scientific
        # claim.
        capture = {
            "schema": panel["schema"],
            "interpretation": panel["interpretation"],
            "full_domain_errors_are_primary": True,
            "history_wide_discrete_branch_invariant_cohort_is_attribution_only": (
                True
            ),
            "continuous_threshold_and_clamp_branch_stability_resolved": False,
            "time_step_convergence_demonstrated": False,
            "mesh_backends": {
                backend: {
                    "cell_count": diagnostic["cell_count"],
                    "adjacent_pair_labels": diagnostic[
                        "adjacent_pair_labels"
                    ],
                    "successive_comparison_labels": diagnostic[
                        "successive_comparison_labels"
                    ],
                    "history_wide_discrete_branch_invariant_cohort": {
                        key: diagnostic[
                            "history_wide_discrete_branch_invariant_cohort"
                        ][key]
                        for key in (
                            "cell_count",
                            "excluded_cell_count",
                            "area_fraction",
                            "excluded_area_fraction",
                            "area_partition_exact",
                            "selection_uses_error_magnitudes",
                            "continuous_threshold_branch_stability_resolved",
                        )
                    },
                    "full_domain_adjacent_l2_errors": {
                        field: [
                            error["full_domain_area_weighted_l2"]
                            for error in metrics[
                                "adjacent_refinement_errors"
                            ]
                        ]
                        for field, metrics in diagnostic["continuous"].items()
                    },
                    "successive_full_domain_l2_error_ratios": {
                        field: metrics[
                            "successive_full_domain_l2_error_ratios"
                        ]
                        for field, metrics in diagnostic["continuous"].items()
                    },
                    "successive_discrete_branch_invariant_l2_error_ratios": {
                        field: metrics[
                            "successive_discrete_branch_invariant_l2_error_ratios"
                        ]
                        for field, metrics in diagnostic["continuous"].items()
                    },
                    "discrete_branch_invariant_included_sse_share": {
                        field: [
                            error[
                                "discrete_branch_invariant_included_sse_share"
                            ]
                            for error in metrics[
                                "adjacent_refinement_errors"
                            ]
                        ]
                        for field, metrics in diagnostic["continuous"].items()
                    },
                    "recorded_discrete_branch_change_excluded_sse_share": {
                        field: [
                            error[
                                "recorded_discrete_branch_change_excluded_sse_share"
                            ]
                            for error in metrics[
                                "adjacent_refinement_errors"
                            ]
                        ]
                        for field, metrics in diagnostic["continuous"].items()
                    },
                    "adjacent_categorical_mismatch_fraction": {
                        field: metrics[
                            "adjacent_area_mismatch_fraction"
                        ]
                        for field, metrics in diagnostic["categorical"].items()
                    },
                    "adjacent_extensive_relative_difference": {
                        field: metrics["adjacent_relative_difference"]
                        for field, metrics in diagnostic[
                            "endpoint_extensive_relative_differences"
                        ].items()
                    },
                    "nondecreasing_full_domain_l2_fields_by_successive_comparison": diagnostic[
                        "nondecreasing_full_domain_l2_fields_by_successive_comparison"
                    ],
                    "maximum_transport_inventory_relative_error": diagnostic[
                        "maximum_transport_inventory_relative_error"
                    ],
                }
                for backend, diagnostic in panel["mesh_backends"].items()
            },
        }
        print(
            "MOVING_DOMAIN_TIMESTEP_DIAGNOSTIC="
            + json.dumps(capture, sort_keys=True, separators=(",", ":"))
        )

    def test_v2_alignment_preflight_fails_closed(self) -> None:
        worlds = self.worlds["fibonacci_sphere"]

        def assert_mapping_mutation_rejected(
            mapping: dict,
            key: str,
            corrupted_value: object,
            label: str,
        ) -> None:
            original_value = mapping[key]
            try:
                mapping[key] = corrupted_value
                with self.subTest(label=label):
                    with self.assertRaises(AssertionError):
                        _history_wide_discrete_branch_invariant_cell_ids(
                            worlds
                        )
            finally:
                mapping[key] = original_value

        assert_mapping_mutation_rejected(
            worlds[0]["cells"][0],
            "id",
            1,
            "noncanonical_final_cell_id",
        )
        assert_mapping_mutation_rejected(
            worlds[1]["cells"][0],
            "area_km2",
            float(worlds[1]["cells"][0]["area_km2"]) + 1.0,
            "cross_refinement_cell_area_mismatch",
        )
        assert_mapping_mutation_rejected(
            worlds[2]["plate_motion_history"][1],
            "nominal_elapsed_time_ma",
            1.5,
            "plate_history_timestamp_mismatch",
        )
        assert_mapping_mutation_rejected(
            worlds[3]["fluvial_sediment_routing_history"][0][
                "input_cells"
            ][0],
            "cell_id",
            1,
            "noncanonical_routing_input_id",
        )

        removed_step = worlds[3]["plate_motion_history"].pop()
        try:
            with self.subTest(label="plate_history_length_mismatch"):
                with self.assertRaises(AssertionError):
                    _history_wide_discrete_branch_invariant_cell_ids(worlds)
        finally:
            worlds[3]["plate_motion_history"].append(removed_step)


if __name__ == "__main__":
    import unittest

    unittest.main()
