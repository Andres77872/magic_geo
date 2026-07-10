from __future__ import annotations

import math
from collections import Counter, deque
from typing import Any


MARINE_WATER_TYPES = {"ocean", "continental_shelf", "inland_sea"}
WETLAND_TYPES = {
    "none",
    "mangrove",
    "tidal_marsh",
    "delta_wetland",
    "floodplain_wetland",
    "lacustrine_wetland",
    "peatland",
    "freshwater_swamp",
}
WETLAND_THRESHOLD = 0.54


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


def _neighbor_cells(cell: dict[str, Any], cells_by_id: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    neighbors = cell.get("neighbors", [])
    if not isinstance(neighbors, list):
        return []
    return [cells_by_id[int(raw_id)] for raw_id in neighbors if int(raw_id) in cells_by_id]


def _coastal_feature_by_cell(world: dict[str, Any]) -> dict[int, dict[str, Any]]:
    features = world.get("coastal_features", [])
    if not isinstance(features, list):
        return {}
    return {
        int(feature.get("cell_id", -1)): feature
        for feature in features
        if isinstance(feature, dict) and int(feature.get("cell_id", -1)) >= 0
    }


def _is_coastal(cell: dict[str, Any], neighbors: list[dict[str, Any]]) -> bool:
    if bool(cell.get("is_water", False)):
        return False
    return any(_is_marine(neighbor) for neighbor in neighbors)


def _freshwater_contact(cell: dict[str, Any], neighbors: list[dict[str, Any]]) -> bool:
    if bool(cell.get("is_river", False)) or bool(cell.get("is_lake", False)):
        return True
    if str(cell.get("water_body_type", "land")) in {"fresh_lake", "lake"}:
        return True
    for neighbor in neighbors:
        if bool(neighbor.get("is_river", False)) or bool(neighbor.get("is_lake", False)):
            return True
        if str(neighbor.get("water_body_type", "land")) in {"fresh_lake", "lake"}:
            return True
    return False


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


def _wetland_type(
    cell: dict[str, Any],
    neighbors: list[dict[str, Any]],
    coastal_feature: dict[str, Any] | None,
    coastal: bool,
) -> str:
    landform = str(cell.get("landform", ""))
    biome = str(cell.get("biome", ""))
    ecotone = str(cell.get("biome_ecotone_type", "none"))
    soil_type = str(cell.get("soil_type", ""))
    texture = str(cell.get("soil_texture_class", ""))
    temperature = float(cell.get("temperature_c", 0.0))
    frost_months = int(cell.get("frost_months", 0))
    moisture = _clamp(float(cell.get("soil_moisture_index", 0.0)))
    feature_type = str((coastal_feature or {}).get("type", ""))

    if coastal and (ecotone == "mangrove" or (temperature >= 18.0 and frost_months == 0 and moisture >= 0.55)):
        return "mangrove"
    if coastal and feature_type in {"tidal_marsh", "barrier_bar", "delta_lobe"}:
        return "tidal_marsh"
    if landform == "delta" or feature_type == "delta_lobe":
        return "delta_wetland"
    if landform in {"floodplain", "river_valley", "alluvial_fan"}:
        return "floodplain_wetland"
    if landform in {"lacustrine_basin", "glacial_lake"} or any(str(neighbor.get("water_body_type", "")) == "fresh_lake" for neighbor in neighbors):
        return "lacustrine_wetland"
    if soil_type == "wetland" or texture == "peat" or float(cell.get("soil_organic_matter_fraction", 0.0)) >= 0.18:
        return "peatland"
    if biome == "wetland" or ecotone == "swamp":
        return "freshwater_swamp"
    return "freshwater_swamp"


def _wetland_indices(
    cell: dict[str, Any],
    neighbors: list[dict[str, Any]],
    coastal_feature: dict[str, Any] | None,
    coastal: bool,
    freshwater: bool,
) -> tuple[float, float, float, float, float]:
    if _is_marine(cell) or str(cell.get("biome", "")) == "ice_cap":
        return 0.0, 0.0, 0.0, 0.0, 0.0
    soil_moisture = _clamp(float(cell.get("soil_moisture_index", 0.0)))
    drainage_inverse = 1.0 - _clamp(float(cell.get("soil_drainage_index", 0.0)))
    wet_months = _clamp(float(cell.get("wet_season_months", 0)) / 10.0)
    runoff_fraction = _clamp(float(cell.get("runoff_generation_fraction", 0.0)))
    balance = _clamp(float(cell.get("hydrologic_water_balance_mm_y", 0.0)) / 1200.0)
    water_bonus = 0.18 if freshwater else 0.0
    hydrology = _clamp(soil_moisture * 0.24 + drainage_inverse * 0.24 + wet_months * 0.16 + runoff_fraction * 0.16 + balance * 0.12 + water_bonus)

    organic = _clamp(float(cell.get("soil_organic_matter_fraction", 0.0)) / 0.22)
    salinity_penalty = _clamp(float(cell.get("soil_salinity_index", 0.0))) * 0.10
    saturation = _clamp(soil_moisture * 0.38 + drainage_inverse * 0.28 + organic * 0.18 + water_bonus * 0.70 - salinity_penalty)

    landform = str(cell.get("landform", ""))
    biome = str(cell.get("biome", ""))
    ecotone = str(cell.get("biome_ecotone_type", "none"))
    feature_type = str((coastal_feature or {}).get("type", ""))
    ecotone_index = _clamp(
        (0.30 if biome == "wetland" else 0.0)
        + (0.28 if ecotone in {"swamp", "mangrove"} else 0.0)
        + (0.22 if landform in {"delta", "floodplain", "river_valley", "lacustrine_basin", "coastal_plain"} else 0.0)
        + (0.20 if feature_type in {"tidal_marsh", "delta_lobe", "barrier_bar"} else 0.0)
    )

    lake_or_river_neighbors = sum(
        1
        for neighbor in neighbors
        if bool(neighbor.get("is_river", False))
        or bool(neighbor.get("is_lake", False))
        or str(neighbor.get("water_body_type", "land")) == "fresh_lake"
    )
    water_neighbors = sum(1 for neighbor in neighbors if bool(neighbor.get("is_water", False)))
    neighbor_divisor = max(1, len(neighbors))
    connectivity = _clamp(
        (1.0 if bool(cell.get("is_river", False)) or bool(cell.get("is_lake", False)) else 0.0) * 0.18
        + (lake_or_river_neighbors / neighbor_divisor) * 0.34
        + (water_neighbors / neighbor_divisor) * 0.18
        + (0.18 if coastal else 0.0)
        + _clamp(float(cell.get("flow_accumulation", 0.0)) / 25_000_000.0) * 0.12
    )
    extent = _clamp(hydrology * 0.34 + saturation * 0.28 + ecotone_index * 0.22 + connectivity * 0.16)
    return extent, hydrology, saturation, ecotone_index, connectivity


def _region_record(region_id: int, component: list[dict[str, Any]], wetland_type: str) -> dict[str, Any]:
    divisor = max(1, len(component))
    centroid_lat, centroid_lon = _lat_lon_centroid(component)
    basin_ids = sorted({int(cell.get("basin_id", -1)) for cell in component if int(cell.get("basin_id", -1)) >= 0})
    watershed_ids = sorted({int(cell.get("watershed_id", -1)) for cell in component if int(cell.get("watershed_id", -1)) >= 0})
    biome_counts = Counter(str(cell.get("biome", "unknown")) for cell in component)
    landform_counts = Counter(str(cell.get("landform", "unknown")) for cell in component)
    return {
        "id": region_id,
        "wetland_type": wetland_type,
        "cell_ids": sorted(_cell_id(cell) for cell in component),
        "cell_count": len(component),
        "area_km2": _round(sum(_area(cell) for cell in component)),
        "centroid_lat_deg": centroid_lat,
        "centroid_lon_deg": centroid_lon,
        "mean_wetland_extent_index": _round(sum(float(cell.get("wetland_extent_index", 0.0)) for cell in component) / divisor),
        "mean_wetland_hydrology_index": _round(sum(float(cell.get("wetland_hydrology_index", 0.0)) for cell in component) / divisor),
        "mean_wetland_soil_saturation_index": _round(
            sum(float(cell.get("wetland_soil_saturation_index", 0.0)) for cell in component) / divisor
        ),
        "mean_wetland_ecotone_index": _round(sum(float(cell.get("wetland_ecotone_index", 0.0)) for cell in component) / divisor),
        "mean_wetland_connectivity_index": _round(
            sum(float(cell.get("wetland_connectivity_index", 0.0)) for cell in component) / divisor
        ),
        "mean_precipitation_mm_y": _round(sum(float(cell.get("precipitation_mm_y", 0.0)) for cell in component) / divisor),
        "mean_runoff_mm_y": _round(sum(float(cell.get("runoff_mm_y", 0.0)) for cell in component) / divisor),
        "mean_soil_moisture_index": _round(sum(float(cell.get("soil_moisture_index", 0.0)) for cell in component) / divisor),
        "river_cell_count": sum(1 for cell in component if bool(cell.get("is_river", False))),
        "lake_cell_count": sum(1 for cell in component if bool(cell.get("is_lake", False))),
        "coastal_cell_count": sum(1 for cell in component if bool(cell.get("wetland_coastal_flag", False))),
        "delta_cell_count": sum(1 for cell in component if str(cell.get("landform", "")) == "delta"),
        "mangrove_cell_count": sum(1 for cell in component if str(cell.get("wetland_system_type", "")) == "mangrove"),
        "linked_basin_ids": basin_ids,
        "linked_watershed_ids": watershed_ids,
        "dominant_biome": _dominant(biome_counts, "unknown"),
        "dominant_landform": _dominant(landform_counts, "unknown"),
    }


def _connected_regions(cells: list[dict[str, Any]], cells_by_id: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    candidate_ids = {_cell_id(cell) for cell in cells if str(cell.get("wetland_system_type", "none")) != "none"}
    remaining = set(candidate_ids)
    records: list[dict[str, Any]] = []
    while remaining:
        start = min(remaining)
        start_cell = cells_by_id[start]
        wetland_type = str(start_cell.get("wetland_system_type", "none"))
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
                if neighbor is None or str(neighbor.get("wetland_system_type", "none")) != wetland_type:
                    continue
                remaining.remove(neighbor_id)
                queue.append(neighbor_id)
        region_id = len(records)
        for cell in component:
            cell["wetland_system_id"] = region_id
        records.append(_region_record(region_id, component, wetland_type))
    return records


def enrich_world_with_wetland_diagnostics(world: dict[str, Any]) -> dict[str, Any]:
    cells = world.get("cells", [])
    if not isinstance(cells, list) or not cells:
        return world

    cells_by_id = {_cell_id(cell): cell for cell in cells}
    coastal_features = _coastal_feature_by_cell(world)
    wetland_cell_count = 0
    wetland_area = 0.0
    extent_sum = 0.0
    hydrology_sum = 0.0
    saturation_sum = 0.0
    ecotone_sum = 0.0
    connectivity_sum = 0.0
    type_counts: Counter[str] = Counter()

    for cell in cells:
        neighbors = _neighbor_cells(cell, cells_by_id)
        coastal = _is_coastal(cell, neighbors)
        freshwater = _freshwater_contact(cell, neighbors)
        coastal_feature = coastal_features.get(_cell_id(cell))
        extent, hydrology, saturation, ecotone, connectivity = _wetland_indices(cell, neighbors, coastal_feature, coastal, freshwater)
        direct_label = (
            str(cell.get("biome", "")) == "wetland"
            or str(cell.get("biome_ecotone_type", "")) in {"swamp", "mangrove"}
            or str(cell.get("landform", "")) in {"delta", "floodplain", "lacustrine_basin"}
            or str((coastal_feature or {}).get("type", "")) in {"tidal_marsh", "delta_lobe"}
        )
        wetland_type = _wetland_type(cell, neighbors, coastal_feature, coastal) if extent >= WETLAND_THRESHOLD or direct_label else "none"
        if _is_marine(cell) or str(cell.get("biome", "")) == "ice_cap":
            wetland_type = "none"
        cell["wetland_extent_index"] = _round(extent)
        cell["wetland_hydrology_index"] = _round(hydrology)
        cell["wetland_soil_saturation_index"] = _round(saturation)
        cell["wetland_ecotone_index"] = _round(ecotone)
        cell["wetland_connectivity_index"] = _round(connectivity)
        cell["wetland_coastal_flag"] = bool(coastal)
        cell["wetland_system_type"] = wetland_type
        cell["wetland_system_id"] = -1

        if wetland_type != "none":
            wetland_cell_count += 1
            wetland_area += _area(cell)
        extent_sum += extent
        hydrology_sum += hydrology
        saturation_sum += saturation
        ecotone_sum += ecotone
        connectivity_sum += connectivity
        type_counts[wetland_type] += 1

    systems = _connected_regions(cells, cells_by_id)
    summary = world.setdefault("summary", {})
    divisor = float(len(cells))
    wetland_divisor = float(wetland_cell_count) if wetland_cell_count else 1.0
    summary["wetland_cell_count"] = wetland_cell_count
    summary["wetland_system_count"] = len(systems)
    summary["wetland_area_km2"] = _round(wetland_area)
    summary["wetland_area_fraction"] = _round(wetland_area / max(1.0, sum(_area(cell) for cell in cells)))
    summary["mean_wetland_extent_index"] = _round(extent_sum / divisor)
    summary["mean_wetland_hydrology_index"] = _round(hydrology_sum / divisor)
    summary["mean_wetland_soil_saturation_index"] = _round(saturation_sum / divisor)
    summary["mean_wetland_ecotone_index"] = _round(ecotone_sum / divisor)
    summary["mean_wetland_connectivity_index"] = _round(connectivity_sum / divisor)
    summary["mean_wetland_extent_index_over_wetlands"] = _round(
        sum(float(cell.get("wetland_extent_index", 0.0)) for cell in cells if str(cell.get("wetland_system_type", "none")) != "none")
        / wetland_divisor
    )
    summary["wetland_type_counts"] = dict(sorted(type_counts.items()))
    summary["mangrove_wetland_cell_count"] = type_counts.get("mangrove", 0)
    summary["tidal_marsh_wetland_cell_count"] = type_counts.get("tidal_marsh", 0)
    summary["delta_wetland_cell_count"] = type_counts.get("delta_wetland", 0)
    summary["floodplain_wetland_cell_count"] = type_counts.get("floodplain_wetland", 0)
    summary["freshwater_swamp_cell_count"] = type_counts.get("freshwater_swamp", 0)
    world["wetland_systems"] = systems
    return world
