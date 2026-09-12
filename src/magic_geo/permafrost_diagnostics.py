from __future__ import annotations

from collections import Counter, deque
from typing import Any


PERMAFROST_THRESHOLD = 0.45


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _monthly_temperatures(cell: dict[str, Any]) -> list[float]:
    values = cell.get("temperature_monthly_c", [])
    if not isinstance(values, list) or len(values) != 12:
        return [float(cell.get("temperature_c", 0.0)) for _ in range(12)]
    return [float(value) for value in values]


def _frost_month_count(cell: dict[str, Any]) -> int:
    # Monthly climate is the source state. A cached biome diagnostic may be
    # absent, or stale if a caller changed climate before re-enriching.
    return sum(temperature < 0.0 for temperature in _monthly_temperatures(cell))


def _permafrost_class(extent: float, ice_thickness_m: float) -> str:
    if extent < 0.15:
        return "no_permafrost"
    if extent < PERMAFROST_THRESHOLD:
        return "seasonal_frost"
    if ice_thickness_m >= 120.0 and extent >= 0.62:
        return "ice_cemented_permafrost"
    if extent >= 0.78:
        return "continuous_permafrost"
    if extent >= 0.62:
        return "discontinuous_permafrost"
    return "sporadic_permafrost"


def _primary_key(counter: Counter[str], fallback: str) -> str:
    if not counter:
        return fallback
    return sorted(counter.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _permafrost_components(cell: dict[str, Any]) -> tuple[float, float, float, str]:
    if bool(cell.get("is_water", False)):
        return 0.0, 0.0, 0.0, "no_permafrost"

    monthly_temperature = _monthly_temperatures(cell)
    annual_temperature = sum(monthly_temperature) / 12.0
    warmest_month = max(monthly_temperature)
    freezing_degree_index = sum(max(0.0, -temperature) for temperature in monthly_temperature) / 12.0
    thawing_degree_index = sum(max(0.0, temperature) for temperature in monthly_temperature) / 12.0
    frost_months = sum(temperature < 0.0 for temperature in monthly_temperature)
    lat_abs = abs(float(cell.get("lat_deg", 0.0))) / 90.0
    elevation = max(0.0, float(cell.get("elevation_m", 0.0)))
    ice_thickness = max(0.0, float(cell.get("ice_thickness_m", 0.0)))
    soil_moisture = _clamp(float(cell.get("soil_moisture_index", 0.0)))
    organic = _clamp(float(cell.get("soil_organic_matter_fraction", 0.0)) / 0.18)
    drainage = _clamp(float(cell.get("soil_drainage_index", 0.0)))
    snow_or_ice = _clamp(ice_thickness / 650.0)
    aridity = _clamp(float(cell.get("seasonal_aridity_index", 0.0)))

    coldness = _clamp((-annual_temperature + 1.5) / 16.0)
    persistent_freeze = _clamp(frost_months / 12.0)
    high_cold = _clamp(elevation / 4200.0)
    summer_thaw_penalty = _clamp((warmest_month - 6.0) / 22.0)
    thaw_penalty = _clamp(thawing_degree_index / 18.0)
    extent = _clamp(
        coldness * 0.34
        + persistent_freeze * 0.24
        + lat_abs * 0.12
        + high_cold * 0.11
        + soil_moisture * 0.08
        + organic * 0.05
        + snow_or_ice * 0.12
        - summer_thaw_penalty * 0.12
        - thaw_penalty * 0.08
        - aridity * 0.06
    )

    if extent < PERMAFROST_THRESHOLD:
        active_layer_depth = 0.0
        ground_ice = 0.0
    else:
        ground_ice = _clamp(
            extent * 0.35
            + soil_moisture * 0.22
            + snow_or_ice * 0.20
            + organic * 0.12
            + (1.0 - drainage) * 0.11
        )
        active_layer_depth = _clamp(
            0.28
            + thawing_degree_index / 5.6
            + drainage * 0.42
            + aridity * 0.26
            - ground_ice * 0.52
            - organic * 0.22
            - snow_or_ice * 0.32,
            0.05,
            4.5,
        )

    return extent, active_layer_depth, ground_ice, _permafrost_class(extent, ice_thickness)


def _connected_components(candidate_ids: set[int], cells_by_id: dict[int, dict[str, Any]]) -> list[list[dict[str, Any]]]:
    components: list[list[dict[str, Any]]] = []
    remaining = set(candidate_ids)
    while remaining:
        start = min(remaining)
        remaining.remove(start)
        queue: deque[int] = deque([start])
        component_ids = [start]
        while queue:
            current_id = queue.popleft()
            current = cells_by_id[current_id]
            neighbors = current.get("neighbors", [])
            if not isinstance(neighbors, list):
                continue
            for neighbor_id_raw in neighbors:
                neighbor_id = int(neighbor_id_raw)
                if neighbor_id not in remaining:
                    continue
                remaining.remove(neighbor_id)
                queue.append(neighbor_id)
                component_ids.append(neighbor_id)
        components.append([cells_by_id[cell_id] for cell_id in sorted(component_ids)])
    return components


def enrich_world_with_permafrost_diagnostics(world: dict[str, Any]) -> dict[str, Any]:
    cells = world.get("cells", [])
    if not isinstance(cells, list) or not cells:
        return world

    cells_by_id = {int(cell.get("id", -1)): cell for cell in cells}
    class_counts: Counter[str] = Counter()
    candidate_ids: set[int] = set()
    extent_sum = 0.0
    active_layer_sum = 0.0
    ground_ice_sum = 0.0
    permafrost_cell_count = 0

    for cell in cells:
        extent, active_layer_depth, ground_ice, permafrost_class = _permafrost_components(cell)
        cell["permafrost_extent_index"] = round(extent, 6)
        cell["active_layer_depth_m"] = round(active_layer_depth, 6)
        cell["ground_ice_content_index"] = round(ground_ice, 6)
        cell["permafrost_class"] = permafrost_class
        cell["permafrost_region_id"] = -1

        extent_sum += extent
        class_counts[permafrost_class] += 1
        if extent >= PERMAFROST_THRESHOLD:
            candidate_ids.add(int(cell.get("id", -1)))
            active_layer_sum += active_layer_depth
            ground_ice_sum += ground_ice
            permafrost_cell_count += 1

    regions: list[dict[str, Any]] = []
    for component in _connected_components(candidate_ids, cells_by_id):
        region_id = len(regions)
        for cell in component:
            cell["permafrost_region_id"] = region_id
        area_sum = sum(max(0.0, float(cell.get("area_km2", 0.0))) for cell in component)
        extent_region_sum = sum(float(cell.get("permafrost_extent_index", 0.0)) for cell in component)
        active_region_sum = sum(float(cell.get("active_layer_depth_m", 0.0)) for cell in component)
        ground_ice_region_sum = sum(float(cell.get("ground_ice_content_index", 0.0)) for cell in component)
        frost_months_sum = sum(_frost_month_count(cell) for cell in component)
        class_counter = Counter(str(cell.get("permafrost_class", "unknown")) for cell in component)
        biome_counter = Counter(str(cell.get("biome", "unknown")) for cell in component)
        group_count = len(component)
        regions.append(
            {
                "id": region_id,
                "cell_count": group_count,
                "cell_ids": [int(cell.get("id", -1)) for cell in component],
                "area_km2": round(area_sum, 6),
                "dominant_permafrost_class": _primary_key(class_counter, "sporadic_permafrost"),
                "dominant_biome": _primary_key(biome_counter, "tundra"),
                "mean_permafrost_extent_index": round(extent_region_sum / group_count, 6),
                "mean_active_layer_depth_m": round(active_region_sum / group_count, 6),
                "mean_ground_ice_content_index": round(ground_ice_region_sum / group_count, 6),
                "mean_frost_months": round(frost_months_sum / group_count, 6),
                "ice_covered_cell_count": sum(1 for cell in component if float(cell.get("ice_thickness_m", 0.0)) > 25.0),
                "permafrost_class_counts": dict(sorted(class_counter.items())),
            }
        )

    summary = world.setdefault("summary", {})
    divisor = float(permafrost_cell_count) if permafrost_cell_count else 1.0
    summary["permafrost_cell_count"] = permafrost_cell_count
    summary["permafrost_region_count"] = len(regions)
    summary["mean_permafrost_extent_index"] = round(extent_sum / len(cells), 6)
    summary["mean_active_layer_depth_m"] = round(active_layer_sum / divisor, 6) if permafrost_cell_count else 0.0
    summary["mean_ground_ice_content_index"] = round(ground_ice_sum / divisor, 6) if permafrost_cell_count else 0.0
    summary["continuous_permafrost_cell_count"] = int(class_counts.get("continuous_permafrost", 0))
    summary["ice_cemented_permafrost_cell_count"] = int(class_counts.get("ice_cemented_permafrost", 0))
    summary["permafrost_class_counts"] = dict(sorted(class_counts.items()))
    world["permafrost_regions"] = regions
    return world
