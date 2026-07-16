from __future__ import annotations

from typing import Any


VALID_TERMINAL_WATER_BODY_TYPES = {
    "ocean",
    "continental_shelf",
    "inland_sea",
    "fresh_lake",
    "saline_basin",
}

# Watersheds use a deliberately different vocabulary from cell water bodies.
# Keep both schemas explicit so a valid closed basin is not rejected merely
# because its terminal land cell is neither a lake nor marked is_closed_basin.
VALID_WATERSHED_OUTLET_TYPES = {
    "ocean",
    "lake",
    "saline_basin",
    "inland_sea",
    "closed_land",
}


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _score_range(value: float, target_min: float, target_max: float) -> float:
    if target_min <= value <= target_max:
        return 1.0
    width = max(1.0e-9, target_max - target_min)
    distance = target_min - value if value < target_min else value - target_max
    return _clamp(1.0 - distance / width)


def _cell_elevation(cell: dict[str, Any]) -> float:
    return float(
        cell.get(
            "hydrologic_surface_elevation_m",
            cell.get("filled_elevation_m", cell.get("elevation_m", 0.0)),
        )
    )


def _has_marine_neighbor(
    cell: dict[str, Any],
    cells_by_id: dict[int, dict[str, Any]],
) -> bool:
    return any(
        bool(cells_by_id[int(neighbor_id)].get("is_water", False))
        for neighbor_id in cell.get("neighbors", [])
        if int(neighbor_id) in cells_by_id
    )


def _delta_terminal_environment(
    cell: dict[str, Any],
    cells_by_id: dict[int, dict[str, Any]],
) -> str:
    """Classify the terminal water setting recognized by derive_landforms."""
    downstream = cells_by_id.get(int(cell.get("flow_to", -1)))
    if downstream is not None:
        if bool(downstream.get("is_lake", False)):
            return "lacustrine"
        if bool(downstream.get("is_water", False)):
            return "marine"
    if _has_marine_neighbor(cell, cells_by_id):
        return "marine"
    return "unrecognized"


def _trace_terminal(
    start_cell: dict[str, Any],
    cells_by_id: dict[int, dict[str, Any]],
    max_steps: int,
) -> tuple[list[int], dict[str, Any], bool]:
    path: list[int] = []
    seen: set[int] = set()
    current = start_cell
    for _ in range(max_steps):
        cell_id = int(current.get("id", -1))
        if cell_id < 0 or cell_id in seen:
            return path, current, True
        path.append(cell_id)
        seen.add(cell_id)
        next_id = int(current.get("flow_to", -1))
        next_cell = cells_by_id.get(next_id)
        if next_cell is None or next_id == cell_id:
            return path, current, False
        current = next_cell
    return path, current, True


def _valid_sink_reason(
    terminal_cell: dict[str, Any],
    watersheds_by_basin_id: dict[int, dict[str, Any]],
) -> str | None:
    water_body_type = str(terminal_cell.get("water_body_type", ""))
    basin_id = int(terminal_cell.get("basin_id", -1))
    watershed = watersheds_by_basin_id.get(basin_id, {})
    outlet_type = str(watershed.get("outlet_type", ""))
    if water_body_type in VALID_TERMINAL_WATER_BODY_TYPES:
        return f"terminal_water_body:{water_body_type}"
    if bool(terminal_cell.get("is_lake", False)):
        return "terminal_cell:is_lake"
    if outlet_type in VALID_WATERSHED_OUTLET_TYPES:
        return f"watershed_outlet:{outlet_type}"
    if bool(watershed.get("is_endorheic", False)):
        return "watershed:is_endorheic"
    if bool(terminal_cell.get("is_closed_basin", False)):
        return "terminal_cell:is_closed_basin"
    return None


def _check_record(
    checks: list[dict[str, Any]],
    *,
    name: str,
    question: str,
    metric: str,
    value: float,
    target_min: float,
    target_max: float,
    evidence: dict[str, Any],
) -> None:
    value = _clamp(value)
    score = _score_range(value, target_min, target_max)
    checks.append(
        {
            "id": len(checks),
            "domain": "hydrology",
            "name": name,
            "question": question,
            "metric": metric,
            "value": round(value, 6),
            "target_min": round(target_min, 6),
            "target_max": round(target_max, 6),
            "score": round(score, 6),
            "passed": target_min <= value <= target_max,
            "evidence": evidence,
        }
    )


def enrich_world_with_hydrology_realism(world: dict[str, Any]) -> dict[str, Any]:
    cells = world.get("cells", [])
    if not isinstance(cells, list) or not cells:
        return world

    watersheds = world.get("watersheds", [])
    if not isinstance(watersheds, list):
        watersheds = []
    cells_by_id = {int(cell.get("id", index)): cell for index, cell in enumerate(cells)}
    watersheds_by_basin_id = {
        int(watershed.get("basin_id", -1)): watershed
        for watershed in watersheds
    }

    river_cells = [cell for cell in cells if bool(cell.get("is_river", False))]
    max_trace_steps = len(cells) + 1
    valid_sink_count = 0
    terminal_cycle_count = 0
    terminal_types: dict[str, int] = {}
    valid_sink_reasons: dict[str, int] = {}
    for river_cell in river_cells:
        _path, terminal_cell, has_cycle = _trace_terminal(
            river_cell,
            cells_by_id,
            max_trace_steps,
        )
        terminal_cycle_count += 1 if has_cycle else 0
        basin_id = int(terminal_cell.get("basin_id", -1))
        terminal_watershed = watersheds_by_basin_id.get(basin_id, {})
        terminal_type = str(
            terminal_watershed.get(
                "outlet_type",
                str(terminal_cell.get("water_body_type", "unknown")),
            )
        )
        terminal_types[terminal_type] = terminal_types.get(terminal_type, 0) + 1
        valid_sink_reason = _valid_sink_reason(terminal_cell, watersheds_by_basin_id)
        if not has_cycle and valid_sink_reason is not None:
            valid_sink_count += 1
            valid_sink_reasons[valid_sink_reason] = (
                valid_sink_reasons.get(valid_sink_reason, 0) + 1
            )
    valid_river_sink_fraction = valid_sink_count / len(river_cells) if river_cells else 1.0

    river_edges: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for river_cell in river_cells:
        next_cell = cells_by_id.get(int(river_cell.get("flow_to", -1)))
        if next_cell is not None:
            river_edges.append((river_cell, next_cell))
    downhill_edge_count = sum(
        1
        for current, downstream in river_edges
        if _cell_elevation(downstream) <= _cell_elevation(current) + 1.0e-6
    )
    downhill_fraction = downhill_edge_count / len(river_edges) if river_edges else 1.0

    monotonic_accumulation_count = sum(
        1
        for current, downstream in river_edges
        if (
            float(downstream.get("flow_accumulation", 0.0))
            >= float(current.get("flow_accumulation", 0.0))
        )
    )
    accumulation_coherence = monotonic_accumulation_count / len(river_edges) if river_edges else 1.0
    no_cycle_fraction = 1.0 - (terminal_cycle_count / len(river_cells) if river_cells else 0.0)
    tributary_merge_coherence = _clamp(accumulation_coherence * 0.75 + no_cycle_fraction * 0.25)

    delta_cells = [cell for cell in cells if str(cell.get("landform", "")) == "delta"]
    delta_terminal_environments = {
        int(cell.get("id", -1)): _delta_terminal_environment(cell, cells_by_id)
        for cell in delta_cells
    }
    lowland_sediment_terminal_water_deltas = [
        cell
        for cell in delta_cells
        if (
            delta_terminal_environments[int(cell.get("id", -1))]
            in {"marine", "lacustrine"}
            and float(cell.get("elevation_m", 0.0)) <= 300.0
            and (
                float(cell.get("sediment_thickness_m", 0.0)) >= 0.5
                or float(cell.get("sediment_deposition_m", 0.0)) >= 0.5
            )
            and (
                bool(cell.get("is_river", False))
                or float(cell.get("runoff_mm_y", 0.0)) > 0.0
            )
        )
    ]
    qualifying_delta_ids = {
        int(cell.get("id", -1)) for cell in lowland_sediment_terminal_water_deltas
    }
    delta_lowland_sediment_terminal_water = (
        len(lowland_sediment_terminal_water_deltas) / len(delta_cells)
        if delta_cells
        else 1.0
    )

    basin_cells: dict[int, list[dict[str, Any]]] = {}
    for cell in cells:
        basin_id = int(cell.get("basin_id", -1))
        if basin_id >= 0:
            basin_cells.setdefault(basin_id, []).append(cell)

    watershed_divide_fractions: list[float] = []
    total_boundary_cell_count = 0
    aligned_boundary_cell_count = 0
    for watershed in watersheds:
        basin_id = int(watershed.get("basin_id", -1))
        basin_group = basin_cells.get(basin_id, [])
        boundary_cells = [
            cells_by_id[int(cell_id)]
            for cell_id in watershed.get("boundary_cell_ids", [])
            if int(cell_id) in cells_by_id
        ]
        if not boundary_cells:
            watershed_divide_fractions.append(1.0)
            continue
        basin_mean_elevation = _mean([_cell_elevation(cell) for cell in basin_group])
        outlet_cell = cells_by_id.get(int(watershed.get("outlet_cell_id", -1)))
        outlet_elevation = _cell_elevation(outlet_cell) if outlet_cell is not None else 0.0
        divide_floor = max(basin_mean_elevation, outlet_elevation)
        aligned_count = sum(1 for cell in boundary_cells if _cell_elevation(cell) >= divide_floor)
        total_boundary_cell_count += len(boundary_cells)
        aligned_boundary_cell_count += aligned_count
        watershed_divide_fractions.append(aligned_count / len(boundary_cells))
    watershed_divide_alignment = _mean(watershed_divide_fractions) if watersheds else 1.0

    checks: list[dict[str, Any]] = []
    _check_record(
        checks,
        name="river_terminal_sink_validity",
        question="Does each river drain to ocean, lake, inland sea, or endorheic basin?",
        metric="fraction_river_cells_reaching_valid_sink",
        value=valid_river_sink_fraction,
        target_min=0.95,
        target_max=1.0,
        evidence={
            "river_cell_count": len(river_cells),
            "valid_sink_river_cell_count": valid_sink_count,
            "terminal_cycle_count": terminal_cycle_count,
            "terminal_type_counts": dict(sorted(terminal_types.items())),
            "valid_sink_reason_counts": dict(sorted(valid_sink_reasons.items())),
        },
    )
    _check_record(
        checks,
        name="river_downhill_flow",
        question="Do river flow links move downhill over the filled surface?",
        metric="fraction_river_edges_with_nonincreasing_filled_elevation",
        value=downhill_fraction,
        target_min=0.95,
        target_max=1.0,
        evidence={
            "river_edge_count": len(river_edges),
            "downhill_river_edge_count": downhill_edge_count,
        },
    )
    _check_record(
        checks,
        name="tributary_merge_coherence",
        question="Do tributaries merge into coherent downstream accumulation networks?",
        metric="accumulation_monotonicity_and_no_cycle_index",
        value=tributary_merge_coherence,
        target_min=0.85,
        target_max=1.0,
        evidence={
            "river_edge_count": len(river_edges),
            "monotonic_accumulation_edge_count": monotonic_accumulation_count,
            "accumulation_coherence_fraction": round(accumulation_coherence, 6),
            "no_cycle_fraction": round(no_cycle_fraction, 6),
        },
    )
    _check_record(
        checks,
        name="delta_lowland_sediment_terminal_water",
        question=(
            "Do deltas appear only in low, sediment-rich river zones terminating "
            "at a marine coast or lake?"
        ),
        metric="fraction_delta_cells_low_sediment_river_at_marine_or_lacustrine_terminal",
        value=delta_lowland_sediment_terminal_water,
        target_min=0.75,
        target_max=1.0,
        evidence={
            "delta_cell_count": len(delta_cells),
            "marine_terminal_delta_count": sum(
                environment == "marine"
                for environment in delta_terminal_environments.values()
            ),
            "lacustrine_terminal_delta_count": sum(
                environment == "lacustrine"
                for environment in delta_terminal_environments.values()
            ),
            "unrecognized_terminal_delta_count": sum(
                environment == "unrecognized"
                for environment in delta_terminal_environments.values()
            ),
            "lowland_sediment_terminal_water_delta_count": len(
                lowland_sediment_terminal_water_deltas
            ),
            "qualifying_marine_terminal_delta_count": sum(
                cell_id in qualifying_delta_ids and environment == "marine"
                for cell_id, environment in delta_terminal_environments.items()
            ),
            "qualifying_lacustrine_terminal_delta_count": sum(
                cell_id in qualifying_delta_ids and environment == "lacustrine"
                for cell_id, environment in delta_terminal_environments.items()
            ),
        },
    )
    _check_record(
        checks,
        name="watershed_divide_alignment",
        question="Do watershed boundaries follow relative topographic divides?",
        metric="mean_fraction_boundary_cells_above_basin_mean_or_outlet",
        value=watershed_divide_alignment,
        target_min=0.55,
        target_max=1.0,
        evidence={
            "watershed_count": len(watersheds),
            "boundary_cell_count": total_boundary_cell_count,
            "aligned_boundary_cell_count": aligned_boundary_cell_count,
        },
    )

    summary = world.setdefault("summary", {})
    pass_count = sum(1 for check in checks if bool(check["passed"]))
    score_sum = sum(float(check["score"]) for check in checks)
    world["hydrology_realism_checks"] = checks
    summary["valid_river_sink_fraction"] = round(valid_river_sink_fraction, 6)
    summary["river_downhill_realism_index"] = round(downhill_fraction, 6)
    summary["tributary_merge_coherence_index"] = round(tributary_merge_coherence, 6)
    summary["delta_lowland_sediment_terminal_water_index"] = round(
        delta_lowland_sediment_terminal_water,
        6,
    )
    summary["watershed_divide_alignment_index"] = round(watershed_divide_alignment, 6)
    summary["hydrology_realism_check_count"] = len(checks)
    summary["hydrology_realism_pass_count"] = pass_count
    summary["hydrology_realism_pass_fraction"] = round(pass_count / len(checks), 6) if checks else 0.0
    summary["mean_hydrology_realism_score"] = round(score_sum / len(checks), 6) if checks else 0.0
    return world
