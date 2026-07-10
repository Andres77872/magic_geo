from __future__ import annotations

from collections import Counter, deque
from typing import Any


KARST_THRESHOLD = 0.45
MARINE_WATER_TYPES = {"ocean", "continental_shelf", "inland_sea"}


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _primary_key(counter: Counter[str], fallback: str) -> str:
    if not counter:
        return fallback
    return sorted(counter.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _carbonate_factor(lithology: str, soil_ph: float) -> float:
    base = {
        "limestone": 1.0,
        "sandstone": 0.18,
        "shale": 0.12,
        "metamorphic": 0.08,
        "volcanic": 0.04,
        "basalt": 0.03,
        "granite": 0.02,
    }.get(lithology, 0.04)
    acidity_bonus = _clamp((7.8 - soil_ph) / 3.0) * 0.12
    return _clamp(base + acidity_bonus)


def _neighbor_relief_index(cell: dict[str, Any], cells_by_id: dict[int, dict[str, Any]]) -> float:
    neighbors = cell.get("neighbors", [])
    if not isinstance(neighbors, list) or not neighbors:
        return 0.0
    elevation = float(cell.get("elevation_m", 0.0))
    max_relief = 0.0
    for neighbor_id in neighbors:
        neighbor = cells_by_id.get(int(neighbor_id))
        if neighbor is None:
            continue
        max_relief = max(max_relief, abs(elevation - float(neighbor.get("elevation_m", 0.0))))
    return _clamp(max_relief / 1800.0)


def _karst_components(cell: dict[str, Any], cells_by_id: dict[int, dict[str, Any]]) -> tuple[float, float, float]:
    water_body = str(cell.get("water_body_type", "land"))
    if bool(cell.get("is_water", False)) or water_body in MARINE_WATER_TYPES:
        return 0.0, 0.0, 0.0

    lithology = str(cell.get("lithology", "unknown"))
    precipitation = max(0.0, float(cell.get("precipitation_mm_y", 0.0)))
    runoff = max(0.0, float(cell.get("runoff_mm_y", 0.0)))
    recharge = max(0.0, float(cell.get("groundwater_recharge_mm_y", 0.0)))
    soil_moisture = _clamp(float(cell.get("soil_moisture_index", 0.0)))
    soil_drainage = _clamp(float(cell.get("soil_drainage_index", 0.0)))
    soil_profile = _clamp(float(cell.get("soil_profile_development_index", 0.0)))
    soil_ph = float(cell.get("soil_ph", 7.0))
    aquifer_productivity = _clamp(float(cell.get("aquifer_productivity_index", 0.0)))
    aquifer_storage = _clamp(float(cell.get("aquifer_storage_index", 0.0)))
    aridity = _clamp(float(cell.get("seasonal_aridity_index", 0.0)))
    ice = _clamp(float(cell.get("ice_thickness_m", 0.0)) / 800.0)
    temperature = float(cell.get("temperature_c", 0.0))
    relief = _neighbor_relief_index(cell, cells_by_id)

    carbonate = _carbonate_factor(lithology, soil_ph)
    water_solution = _clamp(
        _clamp(precipitation / 1800.0) * 0.38
        + _clamp(runoff / 900.0) * 0.18
        + _clamp(recharge / 520.0) * 0.28
        + soil_moisture * 0.16
    )
    thermal_activity = _clamp((temperature + 6.0) / 24.0, 0.18, 1.0)
    karst = _clamp(
        carbonate
        * (
            0.22
            + water_solution * 0.36
            + relief * 0.16
            + soil_drainage * 0.12
            + soil_profile * 0.10
            + aquifer_storage * 0.04
        )
        * thermal_activity
        - aridity * 0.06
        - ice * 0.20
    )
    cave = _clamp(karst * (0.34 + relief * 0.30 + aquifer_storage * 0.22 + soil_profile * 0.14))
    subterranean = _clamp(karst * (0.28 + aquifer_productivity * 0.32 + soil_drainage * 0.22 + relief * 0.18))
    return karst, cave, subterranean


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


def enrich_world_with_karst_diagnostics(world: dict[str, Any]) -> dict[str, Any]:
    cells = world.get("cells", [])
    if not isinstance(cells, list) or not cells:
        return world

    cells_by_id = {int(cell.get("id", -1)): cell for cell in cells}
    karst_sum = 0.0
    cave_sum = 0.0
    subterranean_sum = 0.0
    limestone_land_count = 0
    limestone_karst_count = 0
    candidate_ids: set[int] = set()

    for cell in cells:
        karst, cave, subterranean = _karst_components(cell, cells_by_id)
        cell["karst_potential_index"] = round(karst, 6)
        cell["cave_development_index"] = round(cave, 6)
        cell["subterranean_drainage_fraction"] = round(subterranean, 6)
        cell["karst_system_id"] = -1
        karst_sum += karst
        cave_sum += cave
        subterranean_sum += subterranean

        is_limestone_land = str(cell.get("lithology", "")) == "limestone" and not bool(cell.get("is_water", False))
        if is_limestone_land:
            limestone_land_count += 1
        if karst >= KARST_THRESHOLD:
            cell_id = int(cell.get("id", -1))
            candidate_ids.add(cell_id)
            if is_limestone_land:
                limestone_karst_count += 1

    systems: list[dict[str, Any]] = []
    for component in _connected_components(candidate_ids, cells_by_id):
        system_id = len(systems)
        for cell in component:
            cell["karst_system_id"] = system_id
        area_sum = sum(max(0.0, float(cell.get("area_km2", 0.0))) for cell in component)
        karst_component_sum = sum(float(cell.get("karst_potential_index", 0.0)) for cell in component)
        cave_component_sum = sum(float(cell.get("cave_development_index", 0.0)) for cell in component)
        subterranean_component_sum = sum(float(cell.get("subterranean_drainage_fraction", 0.0)) for cell in component)
        lithology_counter = Counter(str(cell.get("lithology", "unknown")) for cell in component)
        aquifer_counter = Counter(str(cell.get("aquifer_class", "unknown")) for cell in component)
        aquifer_system_ids = sorted(
            {
                int(cell.get("aquifer_system_id", -1))
                for cell in component
                if int(cell.get("aquifer_system_id", -1)) >= 0
            }
        )
        group_count = len(component)
        systems.append(
            {
                "id": system_id,
                "cell_count": group_count,
                "cell_ids": [int(cell.get("id", -1)) for cell in component],
                "area_km2": round(area_sum, 6),
                "dominant_lithology": _primary_key(lithology_counter, "unknown"),
                "primary_aquifer_class": _primary_key(aquifer_counter, "unknown"),
                "aquifer_system_ids": aquifer_system_ids,
                "mean_karst_potential_index": round(karst_component_sum / group_count, 6),
                "mean_cave_development_index": round(cave_component_sum / group_count, 6),
                "mean_subterranean_drainage_fraction": round(subterranean_component_sum / group_count, 6),
                "limestone_cell_fraction": round(
                    sum(1 for cell in component if str(cell.get("lithology", "")) == "limestone") / group_count,
                    6,
                ),
            }
        )

    summary = world.setdefault("summary", {})
    cell_count = len(cells)
    summary["karst_cell_count"] = len(candidate_ids)
    summary["karst_system_count"] = len(systems)
    summary["mean_karst_potential_index"] = round(karst_sum / cell_count, 6)
    summary["mean_cave_development_index"] = round(cave_sum / cell_count, 6)
    summary["mean_subterranean_drainage_fraction"] = round(subterranean_sum / cell_count, 6)
    summary["limestone_karst_cell_fraction"] = (
        round(limestone_karst_count / limestone_land_count, 6) if limestone_land_count else 0.0
    )
    world["karst_systems"] = systems
    return world
