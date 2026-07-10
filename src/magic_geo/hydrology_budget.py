from __future__ import annotations

import math
from collections import Counter, deque
from typing import Any


MARINE_WATER_TYPES = {"ocean", "continental_shelf", "inland_sea"}
def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _round(value: float) -> float:
    return round(float(value), 6)


def _cell_id(cell: dict[str, Any]) -> int:
    return int(cell.get("id", -1))


def _area(cell: dict[str, Any]) -> float:
    return max(0.0, float(cell.get("area_km2", 0.0)))


def _is_marine(cell: dict[str, Any]) -> bool:
    return str(cell.get("water_body_type", "land")) in MARINE_WATER_TYPES


def _budget_class(cell: dict[str, Any], budget_runoff: float, deficit: float, infiltration: float, actual_et: float) -> str:
    if _is_marine(cell):
        return "marine_budget"
    if deficit >= 250.0 and budget_runoff < 35.0:
        return "water_deficit"
    if budget_runoff >= 250.0 or (budget_runoff >= 100.0 and budget_runoff >= infiltration and budget_runoff >= actual_et * 0.6):
        return "runoff_surplus"
    if infiltration >= actual_et and infiltration >= 50.0:
        return "infiltration_dominated"
    if actual_et >= infiltration * 1.2 and actual_et >= budget_runoff:
        return "evapotranspiration_dominated"
    return "balanced_budget"


def _lat_lon_centroid(cells: list[dict[str, Any]]) -> tuple[float, float]:
    x_sum = 0.0
    y_sum = 0.0
    z_sum = 0.0
    weight_sum = 0.0
    for cell in cells:
        weight = _area(cell) or 1.0
        lat = math.radians(float(cell.get("lat_deg", 0.0)))
        lon = math.radians(float(cell.get("lon_deg", 0.0)))
        cos_lat = math.cos(lat)
        x_sum += math.cos(lon) * cos_lat * weight
        y_sum += math.sin(lon) * cos_lat * weight
        z_sum += math.sin(lat) * weight
        weight_sum += weight
    if weight_sum <= 0.0:
        return 0.0, 0.0
    x = x_sum / weight_sum
    y = y_sum / weight_sum
    z = z_sum / weight_sum
    return _round(math.degrees(math.atan2(z, math.hypot(x, y)))), _round(math.degrees(math.atan2(y, x)))


def _dominant(counter: Counter[int | str], fallback: int | str) -> int | str:
    if not counter:
        return fallback
    return sorted(counter.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _region_record(region_id: int, component: list[dict[str, Any]], region_class: str) -> dict[str, Any]:
    divisor = max(1, len(component))
    area_sum = sum(_area(cell) for cell in component)
    centroid_lat, centroid_lon = _lat_lon_centroid(component)
    basin_counts: Counter[int] = Counter(int(cell.get("basin_id", -1)) for cell in component)
    return {
        "id": region_id,
        "region_class": region_class,
        "cell_ids": sorted(_cell_id(cell) for cell in component),
        "cell_count": len(component),
        "area_km2": _round(area_sum),
        "centroid_lat_deg": centroid_lat,
        "centroid_lon_deg": centroid_lon,
        "mean_precipitation_mm_y": _round(sum(float(cell.get("precipitation_mm_y", 0.0)) for cell in component) / divisor),
        "mean_actual_evapotranspiration_mm_y": _round(
            sum(float(cell.get("actual_evapotranspiration_mm_y", 0.0)) for cell in component) / divisor
        ),
        "mean_infiltration_mm_y": _round(sum(float(cell.get("infiltration_mm_y", 0.0)) for cell in component) / divisor),
        "mean_infiltration_capacity_index": _round(
            sum(float(cell.get("infiltration_capacity_index", 0.0)) for cell in component) / divisor
        ),
        "mean_hydrologic_water_balance_mm_y": _round(
            sum(float(cell.get("hydrologic_water_balance_mm_y", 0.0)) for cell in component) / divisor
        ),
        "mean_water_budget_runoff_mm_y": _round(sum(float(cell.get("water_budget_runoff_mm_y", 0.0)) for cell in component) / divisor),
        "mean_hydrologic_deficit_mm_y": _round(sum(float(cell.get("hydrologic_deficit_mm_y", 0.0)) for cell in component) / divisor),
        "mean_runoff_budget_consistency_index": _round(
            sum(float(cell.get("runoff_budget_consistency_index", 0.0)) for cell in component) / divisor
        ),
        "mean_runoff_generation_fraction": _round(sum(float(cell.get("runoff_generation_fraction", 0.0)) for cell in component) / divisor),
        "river_cell_count": sum(1 for cell in component if bool(cell.get("is_river", False))),
        "lake_cell_count": sum(1 for cell in component if bool(cell.get("is_lake", False))),
        "closed_basin_cell_count": sum(1 for cell in component if bool(cell.get("is_closed_basin", False))),
        "dominant_basin_id": int(_dominant(basin_counts, -1)),
    }


def _connected_regions(cells: list[dict[str, Any]], cells_by_id: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    remaining = {_cell_id(cell) for cell in cells}
    records: list[dict[str, Any]] = []
    while remaining:
        start = min(remaining)
        start_cell = cells_by_id[start]
        region_class = str(start_cell.get("hydrologic_budget_class", "balanced_budget"))
        queue: deque[int] = deque([start])
        remaining.remove(start)
        component: list[dict[str, Any]] = []
        while queue:
            cell_id = queue.popleft()
            cell = cells_by_id[cell_id]
            component.append(cell)
            for raw_neighbor_id in cell.get("neighbors", []):
                neighbor_id = int(raw_neighbor_id)
                if neighbor_id not in remaining:
                    continue
                neighbor = cells_by_id.get(neighbor_id)
                if neighbor is None or str(neighbor.get("hydrologic_budget_class", "balanced_budget")) != region_class:
                    continue
                remaining.remove(neighbor_id)
                queue.append(neighbor_id)
        region_id = len(records)
        for cell in component:
            cell["hydrologic_budget_region_id"] = region_id
        records.append(_region_record(region_id, component, region_class))
    return records


def enrich_world_with_hydrology_budget(world: dict[str, Any]) -> dict[str, Any]:
    cells = world.get("cells", [])
    if not isinstance(cells, list) or not cells:
        return world

    aet_sum = 0.0
    infiltration_sum = 0.0
    capacity_sum = 0.0
    balance_sum = 0.0
    budget_runoff_sum = 0.0
    deficit_sum = 0.0
    residual_sum = 0.0
    abs_residual_sum = 0.0
    consistency_sum = 0.0
    runoff_fraction_sum = 0.0
    high_runoff_generation = 0
    deficit_cells = 0
    low_consistency_cells = 0
    total_infiltration_km3 = 0.0
    total_actual_et_km3 = 0.0
    total_budget_runoff_km3 = 0.0
    total_land_precipitation_km3 = 0.0
    total_residual_km3 = 0.0
    hydrologic_pet_sum = 0.0
    class_counts: Counter[str] = Counter()

    for cell in cells:
        area = _area(cell)
        precipitation = max(0.0, float(cell.get("precipitation_mm_y", 0.0)))
        potential_et = max(0.0, float(cell.get("hydrologic_potential_evapotranspiration_mm_y", 0.0)))
        native_runoff = max(0.0, float(cell.get("runoff_mm_y", 0.0)))
        capacity = max(0.0, float(cell.get("infiltration_capacity_index", 0.0)))
        actual_et = max(0.0, float(cell.get("actual_evapotranspiration_mm_y", 0.0)))
        infiltration = max(0.0, float(cell.get("infiltration_mm_y", 0.0)))
        balance = float(cell.get("hydrologic_water_balance_mm_y", 0.0))
        budget_runoff = max(0.0, float(cell.get("water_budget_runoff_mm_y", 0.0)))
        residual = float(cell.get("runoff_budget_residual_mm_y", 0.0))
        consistency = _clamp(float(cell.get("runoff_budget_consistency_index", 0.0)))
        deficit = max(0.0, float(cell.get("hydrologic_deficit_mm_y", 0.0)))
        runoff_fraction = _clamp(float(cell.get("runoff_generation_fraction", 0.0)))
        budget_class = _budget_class(cell, budget_runoff, deficit, infiltration, actual_et)

        cell["hydrologic_budget_class"] = budget_class
        cell["hydrologic_budget_region_id"] = -1

        aet_sum += actual_et
        infiltration_sum += infiltration
        capacity_sum += capacity
        balance_sum += balance
        budget_runoff_sum += budget_runoff
        deficit_sum += deficit
        residual_sum += residual
        abs_residual_sum += abs(residual)
        consistency_sum += consistency
        runoff_fraction_sum += runoff_fraction
        hydrologic_pet_sum += potential_et
        total_infiltration_km3 += infiltration * area * 0.000001
        total_actual_et_km3 += actual_et * area * 0.000001
        total_budget_runoff_km3 += budget_runoff * area * 0.000001
        if not _is_marine(cell):
            total_land_precipitation_km3 += precipitation * area * 0.000001
            total_residual_km3 += residual * area * 0.000001
        high_runoff_generation += 1 if runoff_fraction >= 0.35 else 0
        deficit_cells += 1 if deficit >= 250.0 else 0
        low_consistency_cells += 1 if consistency < 0.60 else 0
        class_counts[budget_class] += 1

    cells_by_id = {_cell_id(cell): cell for cell in cells}
    regions = _connected_regions(cells, cells_by_id)
    divisor = float(len(cells))
    summary = world.setdefault("summary", {})
    summary["mean_actual_evapotranspiration_mm_y"] = _round(aet_sum / divisor)
    summary["mean_hydrologic_potential_evapotranspiration_mm_y"] = _round(hydrologic_pet_sum / divisor)
    summary["mean_infiltration_mm_y"] = _round(infiltration_sum / divisor)
    summary["mean_infiltration_capacity_index"] = _round(capacity_sum / divisor)
    summary["mean_hydrologic_water_balance_mm_y"] = _round(balance_sum / divisor)
    summary["mean_water_budget_runoff_mm_y"] = _round(budget_runoff_sum / divisor)
    summary["mean_hydrologic_deficit_mm_y"] = _round(deficit_sum / divisor)
    summary["mean_runoff_budget_residual_mm_y"] = _round(residual_sum / divisor)
    summary["mean_abs_runoff_budget_residual_mm_y"] = _round(abs_residual_sum / divisor)
    summary["mean_runoff_budget_consistency_index"] = _round(consistency_sum / divisor)
    summary["mean_runoff_generation_fraction"] = _round(runoff_fraction_sum / divisor)
    summary["total_infiltration_km3_y"] = _round(total_infiltration_km3)
    summary["total_actual_evapotranspiration_km3_y"] = _round(total_actual_et_km3)
    summary["total_water_budget_runoff_km3_y"] = _round(total_budget_runoff_km3)
    summary["total_land_precipitation_km3_y"] = _round(total_land_precipitation_km3)
    summary["total_hydrologic_water_budget_residual_km3_y"] = _round(total_residual_km3)
    summary["high_runoff_generation_cell_count"] = high_runoff_generation
    summary["water_budget_deficit_cell_count"] = deficit_cells
    summary["low_runoff_budget_consistency_cell_count"] = low_consistency_cells
    summary["hydrologic_budget_class_counts"] = dict(sorted(class_counts.items()))
    summary["hydrologic_budget_region_count"] = len(regions)
    summary["runoff_surplus_region_count"] = sum(1 for region in regions if region["region_class"] == "runoff_surplus")
    summary["water_deficit_region_count"] = sum(1 for region in regions if region["region_class"] == "water_deficit")
    world["hydrologic_budget_regions"] = regions
    return world
