from __future__ import annotations

import math
from collections import Counter, deque
from typing import Any

from .grounded_ice_validation import APPLICABLE, RAW_THICKNESS, require_grounded_ice


GLACIAL_LANDFORM_TYPES = {
    "none",
    "ice_cap",
    "mountain_glacier",
    "fjord",
    "glacial_valley",
    "glacial_lake",
    "moraine",
}
MARINE_WATER_TYPES = {"ocean", "continental_shelf", "inland_sea"}
FRESHWATER_TYPES = {"fresh_lake", "lake"}


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


def _is_freshwater(cell: dict[str, Any]) -> bool:
    return bool(cell.get("is_lake", False)) or str(cell.get("water_body_type", "land")) in FRESHWATER_TYPES


def _neighbor_cells(cell: dict[str, Any], cells_by_id: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    neighbors = cell.get("neighbors", [])
    if not isinstance(neighbors, list):
        return []
    return [cells_by_id[int(raw_id)] for raw_id in neighbors if int(raw_id) in cells_by_id]


def _neighbor_relief(cell: dict[str, Any], neighbors: list[dict[str, Any]]) -> float:
    elevation = float(cell.get("elevation_m", 0.0))
    relief = 0.0
    for neighbor in neighbors:
        relief = max(relief, abs(elevation - float(neighbor.get("elevation_m", elevation))))
    return _clamp(relief / 1800.0)


def _has_marine_contact(cell: dict[str, Any], neighbors: list[dict[str, Any]]) -> bool:
    return _is_marine(cell) or any(_is_marine(neighbor) for neighbor in neighbors)


def _has_freshwater_contact(cell: dict[str, Any], neighbors: list[dict[str, Any]]) -> bool:
    return _is_freshwater(cell) or bool(cell.get("is_river", False)) or any(
        _is_freshwater(neighbor) or bool(neighbor.get("is_river", False)) for neighbor in neighbors
    )


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


def _dominant(counter: Counter[str], fallback: str) -> str:
    if not counter:
        return fallback
    return sorted(counter.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _ice_cover_type(cell: dict[str, Any], relief_index: float) -> str:
    lat_abs = abs(float(cell.get("lat_deg", 0.0)))
    elevation = max(0.0, float(cell.get("elevation_m", 0.0)))
    ice_thickness = max(0.0, float(cell.get("ice_thickness_m", 0.0)))
    broad_polar_ice = lat_abs >= 60.0 and elevation < 1800.0
    thick_low_relief_ice = lat_abs >= 50.0 and ice_thickness >= 420.0 and relief_index < 0.42 and elevation < 1700.0
    if broad_polar_ice or thick_low_relief_ice:
        return "ice_cap"
    return "mountain_glacier"


def _glacial_landform_type(cell: dict[str, Any], neighbors: list[dict[str, Any]], *, grounded_current: bool = False) -> str:
    landform = str(cell.get("landform", ""))
    if landform in {"fjord", "glacial_valley", "glacial_lake", "moraine"}:
        if grounded_current and (bool(cell.get("is_water", False)) or bool(cell.get("is_lake", False))) and landform not in {"fjord", "glacial_lake"}:
            return "none"
        return landform

    relief = _neighbor_relief(cell, neighbors)
    ice_thickness = max(0.0, float(cell.get("ice_thickness_m", 0.0)))
    moraine_deposition = max(0.0, float(cell.get("moraine_deposition_m", 0.0)))
    deglaciation_age = max(0.0, float(cell.get("deglaciation_age_ka", 0.0)))
    erosion = max(0.0, float(cell.get("glacial_erosion_m", 0.0)))
    runoff = max(0.0, float(cell.get("runoff_mm_y", 0.0)))
    flow_accumulation = max(0.0, float(cell.get("flow_accumulation", 0.0)))
    is_water = bool(cell.get("is_water", False))

    exposed = not is_water and not bool(cell.get("is_lake", False))
    if grounded_current and not exposed:
        # Historical glacial water terrain remains meaningful; present lake
        # or sea ice cannot become a grounded glacier or moraine classifier.
        return "glacial_lake" if _is_freshwater(cell) and (deglaciation_age >= 5.0 or moraine_deposition >= 0.35) else "none"

    if landform == "ice_field" and ice_thickness >= 25.0:
        return _ice_cover_type(cell, relief)
    if ice_thickness >= 25.0 and not is_water:
        return _ice_cover_type(cell, relief)
    if not is_water and moraine_deposition >= 0.65 and deglaciation_age >= 5.0:
        return "moraine"
    if _is_freshwater(cell) and (deglaciation_age >= 5.0 or moraine_deposition >= 0.35 or ice_thickness >= 25.0):
        return "glacial_lake"
    if not is_water and erosion >= 7.0 and relief >= 0.08 and (runoff >= 450.0 or flow_accumulation >= 100_000_000.0):
        return "glacial_valley"
    return "none"


def _glacial_indices(
    cell: dict[str, Any],
    neighbors: list[dict[str, Any]],
    glacial_type: str,
) -> tuple[float, float, float, float]:
    landform = str(cell.get("landform", ""))
    relief = _neighbor_relief(cell, neighbors)
    landform_signal = {
        "ice_field": 0.86,
        "fjord": 0.92,
        "glacial_valley": 0.88,
        "glacial_lake": 0.82,
        "moraine": 0.78,
    }.get(landform, 0.0)
    if glacial_type in GLACIAL_LANDFORM_TYPES - {"none"}:
        landform_signal = max(landform_signal, 0.72)

    ice_thickness = max(0.0, float(cell.get("ice_thickness_m", 0.0)))
    ice_presence = _clamp(ice_thickness / 850.0)
    erosion_raw = _clamp(max(0.0, float(cell.get("glacial_erosion_m", 0.0))) / 75.0)
    deposition_raw = _clamp(max(0.0, float(cell.get("moraine_deposition_m", 0.0))) / 2.2)
    deglaciation = _clamp(max(0.0, float(cell.get("deglaciation_age_ka", 0.0))) / 82.0)
    velocity = _clamp(max(0.0, float(cell.get("ice_velocity_m_y", 0.0))) / 220.0)
    stress = _clamp(max(0.0, float(cell.get("ice_flowline_driving_stress_kpa", 0.0))) / 450.0)
    flowline_presence = _clamp(float(cell.get("ice_flowline_path_count", 0)) / 3.0)
    runoff = _clamp(max(0.0, float(cell.get("runoff_mm_y", 0.0))) / 2200.0)
    flow_accumulation = _clamp(max(0.0, float(cell.get("flow_accumulation", 0.0))) / 1_200_000_000.0)
    water_contact = 1.0 if _has_freshwater_contact(cell, neighbors) or _has_marine_contact(cell, neighbors) else 0.0

    erosion_index = _clamp(
        erosion_raw * 0.42
        + stress * 0.20
        + velocity * 0.12
        + relief * 0.12
        + (0.15 if glacial_type in {"fjord", "glacial_valley", "glacial_lake"} else 0.0)
        + flowline_presence * 0.08
    )
    deposition_index = _clamp(
        deposition_raw * 0.55
        + deglaciation * 0.18
        + (0.22 if glacial_type == "moraine" else 0.0)
        + (0.08 if glacial_type in {"fjord", "glacial_lake"} else 0.0)
    )
    meltwater_index = _clamp(
        runoff * 0.34
        + flow_accumulation * 0.24
        + water_contact * 0.18
        + (0.18 if _is_freshwater(cell) or bool(cell.get("is_river", False)) else 0.0)
        + deglaciation * 0.06
    )
    landform_index = _clamp(
        landform_signal * 0.44
        + ice_presence * 0.20
        + erosion_index * 0.16
        + deposition_index * 0.10
        + meltwater_index * 0.10
    )
    return landform_index, erosion_index, deposition_index, meltwater_index


def _region_record(
    region_id: int,
    component: list[dict[str, Any]],
    glacial_type: str,
    cells_by_id: dict[int, dict[str, Any]],
    *, grounded_current: bool = False,
) -> dict[str, Any]:
    divisor = max(1, len(component))
    centroid_lat, centroid_lon = _lat_lon_centroid(component)
    biome_counts = Counter(str(cell.get("biome", "unknown")) for cell in component)
    landform_counts = Counter(str(cell.get("landform", "unknown")) for cell in component)
    ice_sheet_ids = sorted({int(cell.get("ice_sheet_id", -1)) for cell in component if int(cell.get("ice_sheet_id", -1)) >= 0})
    basin_ids = sorted({int(cell.get("basin_id", -1)) for cell in component if int(cell.get("basin_id", -1)) >= 0})
    return {
        "id": region_id,
        "glacial_landform_type": glacial_type,
        "cell_ids": sorted(_cell_id(cell) for cell in component),
        "cell_count": len(component),
        "area_km2": _round(sum(_area(cell) for cell in component)),
        "centroid_lat_deg": centroid_lat,
        "centroid_lon_deg": centroid_lon,
        "mean_glacial_landform_index": _round(
            sum(float(cell.get("glacial_landform_index", 0.0)) for cell in component) / divisor
        ),
        "mean_glacial_erosion_intensity_index": _round(
            sum(float(cell.get("glacial_erosion_intensity_index", 0.0)) for cell in component) / divisor
        ),
        "mean_glacial_deposition_index": _round(sum(float(cell.get("glacial_deposition_index", 0.0)) for cell in component) / divisor),
        "mean_glacial_meltwater_index": _round(sum(float(cell.get("glacial_meltwater_index", 0.0)) for cell in component) / divisor),
        "mean_ice_thickness_m": _round(sum(float(cell.get("ice_thickness_m", 0.0)) for cell in component) / divisor),
        "mean_glacial_erosion_m": _round(sum(float(cell.get("glacial_erosion_m", 0.0)) for cell in component) / divisor),
        "mean_moraine_deposition_m": _round(sum(float(cell.get("moraine_deposition_m", 0.0)) for cell in component) / divisor),
        "mean_deglaciation_age_ka": _round(sum(float(cell.get("deglaciation_age_ka", 0.0)) for cell in component) / divisor),
        "mean_runoff_mm_y": _round(sum(float(cell.get("runoff_mm_y", 0.0)) for cell in component) / divisor),
        "mean_permafrost_extent_index": _round(
            sum(float(cell.get("permafrost_extent_index", 0.0)) for cell in component) / divisor
        ),
        "ice_covered_cell_count": (
            sum(1 for cell in component if cell[APPLICABLE] and cell[RAW_THICKNESS] > 25.0)
            if grounded_current else
            sum(1 for cell in component if float(cell.get("ice_thickness_m", 0.0)) > 25.0)
        ),
        "river_cell_count": sum(1 for cell in component if bool(cell.get("is_river", False))),
        "lake_cell_count": sum(1 for cell in component if _is_freshwater(cell)),
        "coastal_cell_count": sum(1 for cell in component if _has_marine_contact(cell, _neighbor_cells(cell, cells_by_id))),
        "permafrost_cell_count": sum(1 for cell in component if float(cell.get("permafrost_extent_index", 0.0)) >= 0.45),
        "tundra_cell_count": sum(1 for cell in component if str(cell.get("biome", "")) == "tundra"),
        "linked_ice_sheet_ids": ice_sheet_ids,
        "linked_basin_ids": basin_ids,
        "dominant_biome": _dominant(biome_counts, "unknown"),
        "dominant_landform": _dominant(landform_counts, "unknown"),
    }


def _connected_regions(cells: list[dict[str, Any]], cells_by_id: dict[int, dict[str, Any]], *, grounded_current: bool = False) -> list[dict[str, Any]]:
    candidate_ids = {_cell_id(cell) for cell in cells if str(cell.get("glacial_landform_type", "none")) != "none"}
    remaining = set(candidate_ids)
    records: list[dict[str, Any]] = []
    while remaining:
        start = min(remaining)
        start_cell = cells_by_id[start]
        glacial_type = str(start_cell.get("glacial_landform_type", "none"))
        queue: deque[int] = deque([start])
        remaining.remove(start)
        component: list[dict[str, Any]] = []
        while queue:
            cell_id = queue.popleft()
            cell = cells_by_id[cell_id]
            component.append(cell)
            neighbors = cell.get("neighbors", [])
            if not isinstance(neighbors, list):
                continue
            for raw_neighbor_id in neighbors:
                neighbor_id = int(raw_neighbor_id)
                if neighbor_id not in remaining:
                    continue
                neighbor = cells_by_id.get(neighbor_id)
                if neighbor is None or str(neighbor.get("glacial_landform_type", "none")) != glacial_type:
                    continue
                remaining.remove(neighbor_id)
                queue.append(neighbor_id)
        region_id = len(records)
        for cell in component:
            cell["glacial_landform_system_id"] = region_id
        records.append(_region_record(region_id, component, glacial_type, cells_by_id, grounded_current=grounded_current))
    return records


def enrich_world_with_glacial_landforms(world: dict[str, Any]) -> dict[str, Any]:
    grounded_current = require_grounded_ice(world)
    cells = world.get("cells", [])
    summary = world.setdefault("summary", {})
    if not isinstance(cells, list) or not cells:
        world["glacial_landform_systems"] = []
        summary["glacial_landform_cell_count"] = 0
        summary["glacial_landform_system_count"] = 0
        summary["glacial_landform_area_km2"] = 0.0
        summary["mean_glacial_landform_index"] = 0.0
        summary["mean_glacial_erosion_intensity_index"] = 0.0
        summary["mean_glacial_deposition_index"] = 0.0
        summary["mean_glacial_meltwater_index"] = 0.0
        summary["glacial_landform_type_counts"] = {}
        return world

    cells_by_id = {_cell_id(cell): cell for cell in cells}
    type_counts: Counter[str] = Counter()
    glacial_cell_count = 0
    glacial_area = 0.0
    landform_sum = 0.0
    erosion_sum = 0.0
    deposition_sum = 0.0
    meltwater_sum = 0.0

    for cell in cells:
        neighbors = _neighbor_cells(cell, cells_by_id)
        glacial_type = _glacial_landform_type(cell, neighbors, grounded_current=grounded_current)
        landform_index, erosion_index, deposition_index, meltwater_index = _glacial_indices(cell, neighbors, glacial_type)
        cell["glacial_landform_index"] = _round(landform_index)
        cell["glacial_erosion_intensity_index"] = _round(erosion_index)
        cell["glacial_deposition_index"] = _round(deposition_index)
        cell["glacial_meltwater_index"] = _round(meltwater_index)
        cell["glacial_landform_type"] = glacial_type
        cell["glacial_landform_system_id"] = -1

        if glacial_type != "none":
            glacial_cell_count += 1
            glacial_area += _area(cell)
        landform_sum += landform_index
        erosion_sum += erosion_index
        deposition_sum += deposition_index
        meltwater_sum += meltwater_index
        type_counts[glacial_type] += 1

    systems = _connected_regions(cells, cells_by_id, grounded_current=grounded_current)
    divisor = float(len(cells))
    summary["glacial_landform_cell_count"] = glacial_cell_count
    summary["glacial_landform_system_count"] = len(systems)
    summary["glacial_landform_area_km2"] = _round(glacial_area)
    summary["mean_glacial_landform_index"] = _round(landform_sum / divisor)
    summary["mean_glacial_erosion_intensity_index"] = _round(erosion_sum / divisor)
    summary["mean_glacial_deposition_index"] = _round(deposition_sum / divisor)
    summary["mean_glacial_meltwater_index"] = _round(meltwater_sum / divisor)
    summary["glacial_landform_type_counts"] = dict(sorted(type_counts.items()))
    summary["ice_cap_landform_cell_count"] = int(type_counts.get("ice_cap", 0))
    summary["mountain_glacier_landform_cell_count"] = int(type_counts.get("mountain_glacier", 0))
    summary["fjord_landform_cell_count"] = int(type_counts.get("fjord", 0))
    summary["glacial_valley_landform_cell_count"] = int(type_counts.get("glacial_valley", 0))
    summary["glacial_lake_landform_cell_count"] = int(type_counts.get("glacial_lake", 0))
    summary["moraine_landform_cell_count"] = int(type_counts.get("moraine", 0))
    world["glacial_landform_systems"] = systems
    return world
