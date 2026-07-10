from __future__ import annotations

from typing import Any


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = fraction * (len(ordered) - 1)
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    weight = index - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _score_range(value: float, target_min: float, target_max: float) -> float:
    if target_min <= value <= target_max:
        return 1.0
    width = max(1.0e-9, target_max - target_min)
    distance = target_min - value if value < target_min else value - target_max
    return _clamp(1.0 - distance / width)


def _boundary(cell: dict[str, Any], key: str) -> float:
    return _clamp(float(cell.get(key, 0.0)))


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
    score = _score_range(value, target_min, target_max)
    checks.append(
        {
            "id": len(checks),
            "domain": "geology",
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


def _near_convergent(cell: dict[str, Any], cells_by_id: dict[int, dict[str, Any]]) -> bool:
    if _boundary(cell, "boundary_convergent") >= 0.25:
        return True
    return any(
        _boundary(cells_by_id[int(neighbor_id)], "boundary_convergent") >= 0.25
        for neighbor_id in cell.get("neighbors", [])
        if int(neighbor_id) in cells_by_id
    )


def _volcanic_arc_has_trench_pairing(
    cell: dict[str, Any],
    cells_by_id: dict[int, dict[str, Any]],
    trench_ids: set[int],
) -> bool:
    neighbor_ids = {int(neighbor_id) for neighbor_id in cell.get("neighbors", []) if int(neighbor_id) in cells_by_id}
    two_hop_ids = set(neighbor_ids)
    for neighbor_id in neighbor_ids:
        two_hop_ids.update(
            int(next_id)
            for next_id in cells_by_id[neighbor_id].get("neighbors", [])
            if int(next_id) in cells_by_id
        )
    if trench_ids.intersection(two_hop_ids):
        return True
    if _boundary(cell, "boundary_convergent") < 0.25:
        return False
    return any(
        bool(cells_by_id[neighbor_id].get("is_water", False))
        and _boundary(cells_by_id[neighbor_id], "boundary_convergent") >= 0.20
        for neighbor_id in neighbor_ids
    )


def _transform_neighbor_count(cell: dict[str, Any], cells_by_id: dict[int, dict[str, Any]]) -> int:
    return sum(
        1
        for neighbor_id in cell.get("neighbors", [])
        if int(neighbor_id) in cells_by_id
        and (
            _boundary(cells_by_id[int(neighbor_id)], "boundary_transform") >= 0.30
            or str(cells_by_id[int(neighbor_id)].get("boundary_type", "")) == "transform"
        )
    )


def _hypsometry_bimodality_index(cells: list[dict[str, Any]]) -> float:
    elevations = [float(cell.get("elevation_m", 0.0)) for cell in cells]
    if not elevations:
        return 0.0
    land = [cell for cell in cells if not bool(cell.get("is_water", False))]
    water = [cell for cell in cells if bool(cell.get("is_water", False))]
    if not land or not water:
        return 0.0
    overall_mean = sum(elevations) / len(elevations)
    groups = (land, water)
    between_variance = 0.0
    for group in groups:
        group_mean = sum(float(cell.get("elevation_m", 0.0)) for cell in group) / len(group)
        between_variance += len(group) * (group_mean - overall_mean) ** 2
    between_variance /= len(elevations)
    total_variance = sum((elevation - overall_mean) ** 2 for elevation in elevations) / len(elevations)
    return _clamp(between_variance / total_variance if total_variance > 0.0 else 0.0)


def enrich_world_with_geology_realism(world: dict[str, Any]) -> dict[str, Any]:
    cells = world.get("cells", [])
    if not isinstance(cells, list) or not cells:
        return world

    cells_by_id = {int(cell.get("id", -1)): cell for cell in cells}
    land_cells = [cell for cell in cells if not bool(cell.get("is_water", False))]
    land_elevations = [float(cell.get("elevation_m", 0.0)) for cell in land_cells]
    mountain_threshold = max(1600.0, _percentile(land_elevations, 0.88)) if land_elevations else 2000.0
    mountain_cells = [
        cell
        for cell in land_cells
        if float(cell.get("elevation_m", 0.0)) >= mountain_threshold
    ]
    mountain_aligned = [
        cell
        for cell in mountain_cells
        if _boundary(cell, "boundary_convergent") > 0.20 or str(cell.get("crust_type", "")) == "orogen"
    ]
    mountain_alignment = len(mountain_aligned) / len(mountain_cells) if mountain_cells else 1.0

    trench_cells = [
        cell
        for cell in cells
        if str(cell.get("landform", "")) == "trench"
        or (
            bool(cell.get("is_water", False))
            and _boundary(cell, "boundary_convergent") >= 0.45
            and float(cell.get("water_depth_m", 0.0)) >= 700.0
        )
    ]
    trench_alignment = (
        sum(1 for cell in trench_cells if _near_convergent(cell, cells_by_id)) / len(trench_cells)
        if trench_cells
        else 1.0
    )

    oceanic_cells = [
        cell
        for cell in cells
        if bool(cell.get("is_water", False))
        and str(cell.get("water_body_type", "")) in {"ocean", "continental_shelf", "inland_sea"}
        and str(cell.get("crust_type", "")) in {"oceanic", "rift_basin", "transitional"}
    ]
    shallow_depth_threshold = _percentile([float(cell.get("water_depth_m", 0.0)) for cell in oceanic_cells], 0.25)
    shallow_oceanic_highs = [
        cell
        for cell in oceanic_cells
        if float(cell.get("water_depth_m", 0.0)) <= shallow_depth_threshold
    ]
    ridge_alignment = (
        sum(
            1
            for cell in shallow_oceanic_highs
            if _boundary(cell, "boundary_divergent") >= 0.25 or str(cell.get("crust_type", "")) == "rift_basin"
        )
        / len(shallow_oceanic_highs)
        if shallow_oceanic_highs
        else 1.0
    )

    trench_ids = {int(cell.get("id", -1)) for cell in trench_cells}
    volcanic_arc_cells = [
        cell
        for cell in cells
        if str(cell.get("landform", "")) == "volcanic_arc" or str(cell.get("crust_type", "")) == "volcanic_arc"
    ]
    volcanic_arc_pairing = (
        sum(1 for cell in volcanic_arc_cells if _volcanic_arc_has_trench_pairing(cell, cells_by_id, trench_ids))
        / len(volcanic_arc_cells)
        if volcanic_arc_cells
        else 1.0
    )

    transform_cells = [
        cell
        for cell in cells
        if _boundary(cell, "boundary_transform") >= 0.35 or str(cell.get("boundary_type", "")) == "transform"
    ]
    transform_linearity = (
        sum(1 for cell in transform_cells if _transform_neighbor_count(cell, cells_by_id) >= 2) / len(transform_cells)
        if transform_cells
        else 1.0
    )

    hypsometry_bimodality = _hypsometry_bimodality_index(cells)
    summary = world.setdefault("summary", {})
    checks: list[dict[str, Any]] = []
    _check_record(
        checks,
        name="mountain_convergent_alignment",
        question="Do major mountain belts follow convergent boundaries?",
        metric="fraction_high_mountains_near_convergence",
        value=mountain_alignment,
        target_min=0.55,
        target_max=1.0,
        evidence={
            "mountain_threshold_m": round(mountain_threshold, 6),
            "high_mountain_cell_count": len(mountain_cells),
            "aligned_high_mountain_cell_count": len(mountain_aligned),
        },
    )
    _check_record(
        checks,
        name="trench_convergent_alignment",
        question="Are trenches adjacent to convergent or subduction-style boundaries?",
        metric="fraction_trenches_near_convergence",
        value=trench_alignment,
        target_min=0.60,
        target_max=1.0,
        evidence={
            "trench_candidate_cell_count": len(trench_cells),
            "convergent_trench_candidate_count": sum(1 for cell in trench_cells if _near_convergent(cell, cells_by_id)),
        },
    )
    _check_record(
        checks,
        name="oceanic_ridge_divergent_alignment",
        question="Are shallow oceanic ridge candidates associated with divergent boundaries?",
        metric="fraction_shallow_oceanic_highs_near_divergence",
        value=ridge_alignment,
        target_min=0.20,
        target_max=1.0,
        evidence={
            "oceanic_candidate_cell_count": len(oceanic_cells),
            "shallow_oceanic_high_cell_count": len(shallow_oceanic_highs),
            "shallow_depth_threshold_m": round(shallow_depth_threshold, 6),
        },
    )
    _check_record(
        checks,
        name="volcanic_arc_trench_pairing",
        question="Are volcanic arcs paired with nearby trench or convergent oceanic cells?",
        metric="fraction_volcanic_arcs_with_trench_pairing",
        value=volcanic_arc_pairing,
        target_min=0.35,
        target_max=1.0,
        evidence={
            "volcanic_arc_candidate_cell_count": len(volcanic_arc_cells),
            "trench_candidate_cell_count": len(trench_cells),
        },
    )
    _check_record(
        checks,
        name="transform_fault_linearity",
        question="Do transform-fault cells form continuous line-like chains?",
        metric="fraction_transform_cells_with_two_transform_neighbors",
        value=transform_linearity,
        target_min=0.55,
        target_max=1.0,
        evidence={
            "transform_candidate_cell_count": len(transform_cells),
            "linear_transform_candidate_count": sum(
                1 for cell in transform_cells if _transform_neighbor_count(cell, cells_by_id) >= 2
            ),
        },
    )
    _check_record(
        checks,
        name="hypsometry_bimodality",
        question="Does the elevation distribution separate continents and ocean basins?",
        metric="between_land_ocean_elevation_variance_fraction",
        value=hypsometry_bimodality,
        target_min=0.35,
        target_max=1.0,
        evidence={
            "land_cell_count": len(land_cells),
            "water_cell_count": len(cells) - len(land_cells),
            "mean_land_elevation_m": round(
                sum(float(cell.get("elevation_m", 0.0)) for cell in land_cells) / len(land_cells), 6
            )
            if land_cells
            else 0.0,
            "mean_water_elevation_m": round(
                sum(float(cell.get("elevation_m", 0.0)) for cell in cells if bool(cell.get("is_water", False)))
                / max(1, len(cells) - len(land_cells)),
                6,
            ),
        },
    )

    pass_count = sum(1 for check in checks if bool(check["passed"]))
    score_sum = sum(float(check["score"]) for check in checks)
    world["geology_realism_checks"] = checks
    summary["mountain_convergent_alignment"] = round(mountain_alignment, 6)
    summary["trench_convergent_alignment"] = round(trench_alignment, 6)
    summary["oceanic_ridge_divergent_alignment"] = round(ridge_alignment, 6)
    summary["volcanic_arc_trench_pairing"] = round(volcanic_arc_pairing, 6)
    summary["transform_fault_linearity"] = round(transform_linearity, 6)
    summary["hypsometry_bimodality_index"] = round(hypsometry_bimodality, 6)
    summary["geology_realism_check_count"] = len(checks)
    summary["geology_realism_pass_count"] = pass_count
    summary["geology_realism_pass_fraction"] = round(pass_count / len(checks), 6) if checks else 0.0
    summary["mean_geology_realism_score"] = round(score_sum / len(checks), 6) if checks else 0.0
    return world
