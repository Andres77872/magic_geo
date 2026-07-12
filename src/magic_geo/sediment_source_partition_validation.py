from __future__ import annotations

import math
import sys
from collections.abc import Mapping, Sequence
from typing import Any


FLUVIAL_ACTIVE_VOLUME_THRESHOLD_KM3 = 1.0e-15

COMMON_AUDIT_METADATA: dict[str, Any] = {
    "mass_conserving": True,
    "mass_conserving_semantics": (
        "bulk_reference_volume_only_not_dry_rock_mass"
    ),
    "per_cell_source_partition_audit_present": True,
    "source_partition_audit_depth_unit": "m",
    "source_partition_audit_array_index": "cell_id",
    "source_partition_audit_demand_field": (
        "source_production_depth_m_by_cell"
    ),
    "source_partition_audit_is_mass_claim": False,
    "source_partition_audit_is_provenance_claim": False,
}

MODEL_METADATA: dict[str, dict[str, Any]] = {
    "hillslope": {
        "model_key": "hillslope_sediment_transport_model",
        "history_key": "hillslope_sediment_transport_history",
        "model_type": (
            "pairwise_lithology_dependent_volume_conserving_"
            "hillslope_transport_v2"
        ),
        "source_material_partition_model": (
            "available_alluvium_first_then_bedrock_erosion_v1"
        ),
        "erosion_stage_source_partition_order": "hillslope_before_fluvial",
    },
    "fluvial": {
        "model_key": "fluvial_sediment_routing_model",
        "history_key": "fluvial_sediment_routing_history",
        "model_type": "topological_capacity_limited_fluvial_sediment_routing_v1",
        "source_material_partition_model": (
            "available_alluvium_after_hillslope_then_bedrock_erosion_v1"
        ),
        "source_material_partition_is_coupled_external_state": True,
    },
    "glacial": {
        "model_key": "glacial_sediment_transport_model",
        "history_key": "glacial_sediment_transport_history",
        "model_type": "downhill_area_conserving_glacial_sediment_transport_v2",
        "source_material_partition_model": (
            "available_alluvium_first_then_bedrock_erosion_v1"
        ),
    },
}

ARRAY_FIELDS = (
    "source_production_depth_m_by_cell",
    "alluvium_entrainment_depth_m_by_cell",
    "bedrock_erosion_depth_m_by_cell",
)


class _InvalidPartition(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise _InvalidPartition(message)


def _integer(value: Any, field: str) -> int:
    if type(value) is not int:
        raise _InvalidPartition(f"{field} must be an integer")
    return value


def _nonnegative(value: Any, field: str) -> float:
    if type(value) not in (int, float):
        raise _InvalidPartition(f"{field} must be numeric")
    number = float(value)
    if not math.isfinite(number) or number < 0.0:
        raise _InvalidPartition(f"{field} must be finite and nonnegative")
    return number


def _volume_tolerance(values: Sequence[float], *, count: int) -> float:
    operand_sum = math.fsum(abs(value) for value in values)
    scale = max(1.0, *(abs(value) for value in values))
    return max(
        1.0e-7,
        64.0 * math.ulp(scale),
        128.0
        * sys.float_info.epsilon
        * max(1, count)
        * (1.0 + operand_sum),
    )


def _close_volume(actual: float, expected: float, terms: Sequence[float]) -> bool:
    return abs(actual - expected) <= _volume_tolerance(
        [actual, expected, *terms], count=len(terms) + 2
    )


def _depth_partition_close(source: float, alluvium: float, bedrock: float) -> bool:
    return abs(source - alluvium - bedrock) <= max(
        1.0e-12,
        128.0
        * sys.float_info.epsilon
        * (1.0 + abs(source) + abs(alluvium) + abs(bedrock)),
    )


def _depth_replay_close(
    actual: float, expected: float, terms: Sequence[float]
) -> bool:
    operand_sum = math.fsum(abs(value) for value in terms)
    return abs(actual - expected) <= max(
        1.0e-12,
        128.0
        * sys.float_info.epsilon
        * max(1, len(terms) + 2)
        * (1.0 + abs(actual) + abs(expected) + operand_sum),
    )


def _parse_cells(world: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[float]]:
    payload = world.get("cells")
    _require(isinstance(payload, list) and bool(payload), "cells must be nonempty")
    cells: list[dict[str, Any]] = []
    areas: list[float] = []
    for cell_id, item in enumerate(payload):
        _require(isinstance(item, dict), f"cells[{cell_id}] must be an object")
        _require(
            _integer(item.get("id"), f"cells[{cell_id}].id") == cell_id,
            "cells must be canonically cell-id indexed",
        )
        cells.append(item)
        area = _nonnegative(item.get("area_km2"), f"cells[{cell_id}].area_km2")
        _require(area > 0.0, f"cells[{cell_id}].area_km2 must be positive")
        areas.append(area)
    return cells, areas


def _parse_depth_arrays(
    stage: Mapping[str, Any], *, cell_count: int, label: str
) -> tuple[list[float], list[float], list[float]]:
    parsed: list[list[float]] = []
    for field in ARRAY_FIELDS:
        payload = stage.get(field)
        _require(
            isinstance(payload, list) and len(payload) == cell_count,
            f"{label}.{field} must contain exactly cell_count entries",
        )
        parsed.append(
            [
                _nonnegative(value, f"{label}.{field}[{cell_id}]")
                for cell_id, value in enumerate(payload)
            ]
        )
    source, alluvium, bedrock = parsed
    for cell_id, values in enumerate(zip(source, alluvium, bedrock)):
        demand, entrained, eroded = values
        _require(
            _depth_partition_close(demand, entrained, eroded),
            f"{label} cell {cell_id} source demand is not alluvium+bedrock",
        )
    return source, alluvium, bedrock


def _validate_input_cells(
    stage: Mapping[str, Any], *, cell_count: int, label: str
) -> list[float]:
    payload = stage.get("input_cells")
    _require(
        isinstance(payload, list) and len(payload) == cell_count,
        f"{label}.input_cells must contain exactly cell_count entries",
    )
    _require(
        _integer(stage.get("input_cell_count"), f"{label}.input_cell_count")
        == cell_count,
        f"{label}.input_cell_count is invalid",
    )
    sediment_thickness_m: list[float] = []
    for cell_id, item in enumerate(payload):
        _require(isinstance(item, dict), f"{label}.input_cells[{cell_id}] invalid")
        _require(
            _integer(item.get("cell_id"), f"{label}.input_cells[{cell_id}].cell_id")
            == cell_id,
            f"{label}.input_cells are not canonically cell-id indexed",
        )
        sediment_thickness_m.append(
            _nonnegative(
                item.get("sediment_thickness_m"),
                f"{label}.input_cells[{cell_id}].sediment_thickness_m",
            )
        )
    return sediment_thickness_m


def _replay_hillslope_demand(
    stage: Mapping[str, Any], *, cell_count: int, label: str
) -> list[list[float]]:
    payload = stage.get("edges")
    _require(isinstance(payload, list), f"{label}.edges must be a list")
    _require(
        _integer(stage.get("transport_edge_count"), f"{label}.transport_edge_count")
        == len(payload),
        f"{label}.transport_edge_count is invalid",
    )
    contributions: list[list[float]] = [[] for _ in range(cell_count)]
    for edge_id, item in enumerate(payload):
        _require(isinstance(item, dict), f"{label}.edges[{edge_id}] invalid")
        _require(
            _integer(item.get("id"), f"{label}.edges[{edge_id}].id") == edge_id,
            f"{label}.edges ids are not sequential",
        )
        source_id = _integer(
            item.get("source_cell_id"), f"{label}.edges[{edge_id}].source_cell_id"
        )
        target_id = _integer(
            item.get("target_cell_id"), f"{label}.edges[{edge_id}].target_cell_id"
        )
        _require(
            0 <= source_id < cell_count and 0 <= target_id < cell_count,
            f"{label}.edges[{edge_id}] cell link is invalid",
        )
        contributions[source_id].append(
            _nonnegative(
                item.get("source_production_depth_m"),
                f"{label}.edges[{edge_id}].source_production_depth_m",
            )
        )
    return contributions


def _replay_glacial_demand(
    stage: Mapping[str, Any], *, cell_count: int, label: str
) -> list[list[float]]:
    payload = stage.get("transfers")
    _require(isinstance(payload, list), f"{label}.transfers must be a list")
    _require(
        _integer(stage.get("transfer_count"), f"{label}.transfer_count")
        == len(payload),
        f"{label}.transfer_count is invalid",
    )
    contributions: list[list[float]] = [[] for _ in range(cell_count)]
    seen_sources: set[int] = set()
    for transfer_id, item in enumerate(payload):
        _require(isinstance(item, dict), f"{label}.transfers[{transfer_id}] invalid")
        _require(
            _integer(item.get("id"), f"{label}.transfers[{transfer_id}].id")
            == transfer_id,
            f"{label}.transfers ids are not sequential",
        )
        source_id = _integer(
            item.get("source_cell_id"),
            f"{label}.transfers[{transfer_id}].source_cell_id",
        )
        target_id = _integer(
            item.get("target_cell_id"),
            f"{label}.transfers[{transfer_id}].target_cell_id",
        )
        _require(
            0 <= source_id < cell_count and 0 <= target_id < cell_count,
            f"{label}.transfers[{transfer_id}] cell link is invalid",
        )
        _require(source_id not in seen_sources, f"{label} repeats a glacial source")
        seen_sources.add(source_id)
        contributions[source_id].append(
            _nonnegative(
                item.get("source_production_depth_m"),
                f"{label}.transfers[{transfer_id}].source_production_depth_m",
            )
        )
    return contributions


def _validate_fluvial_steps(
    stage: Mapping[str, Any],
    *,
    source: Sequence[float],
    areas: Sequence[float],
    label: str,
) -> tuple[int, float]:
    payload = stage.get("cell_steps")
    _require(isinstance(payload, list), f"{label}.cell_steps must be a list")
    _require(
        _integer(stage.get("active_cell_step_count"), f"{label}.active_cell_step_count")
        == len(payload),
        f"{label}.active_cell_step_count is invalid",
    )
    step_ids: set[int] = set()
    for step_index, item in enumerate(payload):
        _require(isinstance(item, dict), f"{label}.cell_steps[{step_index}] invalid")
        cell_id = _integer(
            item.get("cell_id"), f"{label}.cell_steps[{step_index}].cell_id"
        )
        _require(
            0 <= cell_id < len(source) and cell_id not in step_ids,
            f"{label}.cell_steps cell ids are invalid or repeated",
        )
        step_ids.add(cell_id)
        local_source = _nonnegative(
            item.get("local_source_volume_km3"),
            f"{label}.cell_steps[{step_index}].local_source_volume_km3",
        )
        expected = source[cell_id] * areas[cell_id] / 1000.0
        _require(
            _close_volume(local_source, expected, [local_source, expected]),
            f"{label}.cell_steps[{step_index}] local source disagrees with demand",
        )

    omitted: list[float] = []
    for cell_id, depth in enumerate(source):
        if cell_id in step_ids:
            continue
        volume = depth * areas[cell_id] / 1000.0
        _require(
            volume <= FLUVIAL_ACTIVE_VOLUME_THRESHOLD_KM3,
            f"{label} omits source cell {cell_id} above the routing threshold",
        )
        if volume > 0.0:
            omitted.append(volume)
    return len(omitted), math.fsum(omitted)


def _validate_stage(
    mechanism: str,
    stage: Mapping[str, Any],
    *,
    stage_index: int,
    erosion_iterations: int,
    areas: Sequence[float],
    feedback: Sequence[Any],
) -> dict[str, float | int]:
    label = f"{MODEL_METADATA[mechanism]['history_key']}[{stage_index}]"
    cell_count = _integer(stage.get("cell_count"), f"{label}.cell_count")
    _require(cell_count == len(areas), f"{label}.cell_count is invalid")
    _require(_integer(stage.get("id"), f"{label}.id") == stage_index,
             f"{label}.id is not sequential")
    expected_feedback = stage_index + 1 if mechanism != "glacial" else erosion_iterations + 1
    _require(
        _integer(stage.get("feedback_stage_id"), f"{label}.feedback_stage_id")
        == expected_feedback,
        f"{label}.feedback_stage_id is invalid",
    )
    if mechanism != "glacial":
        _require(
            _integer(stage.get("erosion_iteration"), f"{label}.erosion_iteration")
            == stage_index + 1,
            f"{label}.erosion_iteration is invalid",
        )
    _require(expected_feedback < len(feedback), f"{label} feedback link is absent")
    feedback_record = feedback[expected_feedback]
    _require(isinstance(feedback_record, dict), f"{label} feedback link is malformed")
    _require(
        _integer(feedback_record.get("id"), f"feedback[{expected_feedback}].id")
        == expected_feedback,
        f"{label} feedback id link is invalid",
    )

    source, alluvium, bedrock = _parse_depth_arrays(
        stage, cell_count=cell_count, label=label
    )
    source_terms = [areas[index] * source[index] / 1000.0 for index in range(cell_count)]
    alluvium_terms = [
        areas[index] * alluvium[index] / 1000.0 for index in range(cell_count)
    ]
    bedrock_terms = [
        areas[index] * bedrock[index] / 1000.0 for index in range(cell_count)
    ]
    source_volume = math.fsum(source_terms)
    alluvium_volume = math.fsum(alluvium_terms)
    bedrock_volume = math.fsum(bedrock_terms)
    source_volume_field = (
        "local_source_volume_km3" if mechanism == "fluvial" else "production_volume_km3"
    )
    emitted_source = _nonnegative(stage.get(source_volume_field), f"{label}.{source_volume_field}")
    emitted_alluvium = _nonnegative(
        stage.get("alluvium_entrainment_volume_km3"),
        f"{label}.alluvium_entrainment_volume_km3",
    )
    emitted_bedrock = _nonnegative(
        stage.get("bedrock_erosion_volume_km3"),
        f"{label}.bedrock_erosion_volume_km3",
    )
    for emitted, replayed, terms, name in (
        (emitted_source, source_volume, source_terms, source_volume_field),
        (emitted_alluvium, alluvium_volume, alluvium_terms, "alluvium volume"),
        (emitted_bedrock, bedrock_volume, bedrock_terms, "bedrock volume"),
    ):
        _require(
            _close_volume(emitted, replayed, terms),
            f"{label} {name} does not reconstruct from area*depth/1000",
        )

    omitted_count = 0
    omitted_volume = 0.0
    if mechanism == "hillslope":
        _validate_input_cells(stage, cell_count=cell_count, label=label)
        route_terms = _replay_hillslope_demand(
            stage, cell_count=cell_count, label=label
        )
        replayed_depth = [math.fsum(terms) for terms in route_terms]
    elif mechanism == "glacial":
        _validate_input_cells(stage, cell_count=cell_count, label=label)
        route_terms = _replay_glacial_demand(
            stage, cell_count=cell_count, label=label
        )
        replayed_depth = [math.fsum(terms) for terms in route_terms]
    else:
        route_terms = [[] for _ in range(cell_count)]
        replayed_depth = list(source)
        omitted_count, omitted_volume = _validate_fluvial_steps(
            stage, source=source, areas=areas, label=label
        )

    if mechanism != "fluvial":
        for cell_id, (recorded, replayed) in enumerate(
            zip(source, replayed_depth)
        ):
            _require(
                _depth_replay_close(
                    recorded, replayed, route_terms[cell_id]
                ),
                f"{label} cell {cell_id} demand disagrees with route records",
            )
    return {
        "source_volume_km3": source_volume,
        "alluvium_volume_km3": alluvium_volume,
        "bedrock_volume_km3": bedrock_volume,
        "omitted_threshold_cell_count": omitted_count,
        "omitted_threshold_volume_km3": omitted_volume,
    }


def _validate_alluvium_first_rules(
    world: Mapping[str, Any], *, erosion_iterations: int, cell_count: int
) -> None:
    hillslope_history = world["hillslope_sediment_transport_history"]
    fluvial_history = world["fluvial_sediment_routing_history"]
    for stage_index in range(erosion_iterations):
        hillslope = hillslope_history[stage_index]
        fluvial = fluvial_history[stage_index]
        label = f"erosion source partition[{stage_index}]"
        opening_sediment = _validate_input_cells(
            hillslope, cell_count=cell_count, label=label
        )
        hillslope_source, hillslope_alluvium, _ = _parse_depth_arrays(
            hillslope, cell_count=cell_count, label=label
        )
        fluvial_source, fluvial_alluvium, _ = _parse_depth_arrays(
            fluvial, cell_count=cell_count, label=label
        )
        for cell_id in range(cell_count):
            expected_hillslope = min(
                opening_sediment[cell_id], hillslope_source[cell_id]
            )
            remaining = max(
                0.0, opening_sediment[cell_id] - expected_hillslope
            )
            expected_fluvial = min(remaining, fluvial_source[cell_id])
            _require(
                _depth_replay_close(
                    hillslope_alluvium[cell_id],
                    expected_hillslope,
                    [opening_sediment[cell_id], hillslope_source[cell_id]],
                ),
                f"{label} cell {cell_id} violates hillslope alluvium-first",
            )
            _require(
                _depth_replay_close(
                    fluvial_alluvium[cell_id],
                    expected_fluvial,
                    [remaining, fluvial_source[cell_id]],
                ),
                f"{label} cell {cell_id} violates fluvial alluvium-first",
            )

    glacial = world["glacial_sediment_transport_history"][0]
    label = "glacial source partition[0]"
    opening_sediment = _validate_input_cells(
        glacial, cell_count=cell_count, label=label
    )
    source, alluvium, _ = _parse_depth_arrays(
        glacial, cell_count=cell_count, label=label
    )
    for cell_id in range(cell_count):
        expected = min(opening_sediment[cell_id], source[cell_id])
        _require(
            _depth_replay_close(
                alluvium[cell_id],
                expected,
                [opening_sediment[cell_id], source[cell_id]],
            ),
            f"{label} cell {cell_id} violates alluvium-first",
        )


def validate_sediment_source_partitions(world: Any) -> dict[str, Any]:
    """Replay native per-cell sediment source partitions without coercive fallbacks."""

    failures: list[str] = []
    metrics: dict[str, Any] = {
        "cell_count": 0,
        "hillslope_stage_count": 0,
        "fluvial_stage_count": 0,
        "glacial_stage_count": 0,
        "fluvial_threshold_omitted_cell_count": 0,
        "fluvial_threshold_omitted_volume_km3": 0.0,
    }
    try:
        _require(isinstance(world, Mapping), "world must be an object")
        _, areas = _parse_cells(world)
        metrics["cell_count"] = len(areas)
        clock = world.get("simulation_clock")
        _require(isinstance(clock, dict), "simulation_clock must be an object")
        erosion_iterations = _integer(
            clock.get("configured_erosion_iteration_count"),
            "simulation_clock.configured_erosion_iteration_count",
        )
        _require(erosion_iterations >= 0, "erosion iteration count is negative")
        feedback = world.get("earth_system_feedback_history")
        _require(isinstance(feedback, list), "feedback history must be a list")

        for mechanism, metadata in MODEL_METADATA.items():
            model = world.get(metadata["model_key"])
            history = world.get(metadata["history_key"])
            _require(isinstance(model, dict), f"{metadata['model_key']} must be an object")
            _require(isinstance(history, list), f"{metadata['history_key']} must be a list")
            for key, expected in {**COMMON_AUDIT_METADATA, **{
                field: value
                for field, value in metadata.items()
                if field not in {"model_key", "history_key"}
            }}.items():
                _require(
                    model.get(key) == expected,
                    f"{metadata['model_key']}.{key} is invalid",
                )
            _require(
                _integer(model.get("stage_count"), f"{metadata['model_key']}.stage_count")
                == len(history),
                f"{metadata['model_key']}.stage_count is invalid",
            )
            expected_count = 1 if mechanism == "glacial" else erosion_iterations
            _require(
                len(history) == expected_count,
                f"{metadata['history_key']} length is invalid",
            )
            metrics[f"{mechanism}_stage_count"] = len(history)

            totals = {
                "source": [],
                "alluvium": [],
                "bedrock": [],
            }
            for stage_index, stage in enumerate(history):
                _require(
                    isinstance(stage, dict),
                    f"{metadata['history_key']}[{stage_index}] must be an object",
                )
                replay = _validate_stage(
                    mechanism,
                    stage,
                    stage_index=stage_index,
                    erosion_iterations=erosion_iterations,
                    areas=areas,
                    feedback=feedback,
                )
                totals["source"].append(float(replay["source_volume_km3"]))
                totals["alluvium"].append(float(replay["alluvium_volume_km3"]))
                totals["bedrock"].append(float(replay["bedrock_volume_km3"]))
                if mechanism == "fluvial":
                    metrics["fluvial_threshold_omitted_cell_count"] += int(
                        replay["omitted_threshold_cell_count"]
                    )
                    metrics["fluvial_threshold_omitted_volume_km3"] += float(
                        replay["omitted_threshold_volume_km3"]
                    )

            model_source_field = (
                "total_local_source_volume_km3"
                if mechanism == "fluvial"
                else "total_production_volume_km3"
            )
            for model_field, values in (
                (model_source_field, totals["source"]),
                ("total_alluvium_entrainment_volume_km3", totals["alluvium"]),
                ("total_bedrock_erosion_volume_km3", totals["bedrock"]),
            ):
                emitted = _nonnegative(
                    model.get(model_field), f"{metadata['model_key']}.{model_field}"
                )
                replayed = math.fsum(values)
                _require(
                    _close_volume(emitted, replayed, values),
                    f"{metadata['model_key']}.{model_field} does not mirror history",
                )
        _validate_alluvium_first_rules(
            world,
            erosion_iterations=erosion_iterations,
            cell_count=len(areas),
        )
    except (TypeError, ValueError, OverflowError) as exc:
        failures.append(str(exc))

    return {"passed": not failures, "failures": failures, "metrics": metrics}


__all__ = [
    "COMMON_AUDIT_METADATA",
    "FLUVIAL_ACTIVE_VOLUME_THRESHOLD_KM3",
    "MODEL_METADATA",
    "validate_sediment_source_partitions",
]
