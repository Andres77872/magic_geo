from __future__ import annotations

import heapq
import math
from collections import Counter, deque
from copy import deepcopy
from typing import Any

from .marine_distance_validation import MODEL, require_marine_distance, source_graph


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


def _temperature_range(cell: dict[str, Any]) -> float:
    values = cell.get("temperature_monthly_c", [])
    if not isinstance(values, list) or not values:
        return 0.0
    temperatures = [float(value) for value in values]
    return max(temperatures) - min(temperatures)


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


def _distance_graph(world: dict[str, Any], cells: list[dict[str, Any]]) -> dict[int, list[tuple[int, float]]]:
    graph: dict[int, list[tuple[int, float]]] = {_cell_id(cell): [] for cell in cells}
    edges = world.get("cell_adjacency_edges", [])
    if isinstance(edges, list) and edges:
        for edge in edges:
            cell_a = int(edge.get("cell_a_id", -1))
            cell_b = int(edge.get("cell_b_id", -1))
            if cell_a not in graph or cell_b not in graph:
                continue
            length = max(0.001, float(edge.get("great_circle_distance_km", 0.0)))
            graph[cell_a].append((cell_b, length))
            graph[cell_b].append((cell_a, length))
    else:
        cells_by_id = {_cell_id(cell): cell for cell in cells}
        for cell in cells:
            cell_id = _cell_id(cell)
            length = max(0.001, float(cell.get("mean_neighbor_edge_length_km", 1.0)))
            for raw_neighbor_id in cell.get("neighbors", []):
                neighbor_id = int(raw_neighbor_id)
                if neighbor_id in cells_by_id:
                    graph[cell_id].append((neighbor_id, length))
    return graph


def _nearest_marine_distances(world: dict[str, Any], cells: list[dict[str, Any]]) -> dict[int, float | None]:
    graph = _distance_graph(world, cells)
    distances = {cell_id: float("inf") for cell_id in graph}
    heap: list[tuple[float, int]] = []
    marine_sources = [_cell_id(cell) for cell in cells if _is_marine(cell)]
    if not marine_sources:
        return dict.fromkeys(graph, None)
    for cell_id in marine_sources:
        if cell_id in distances:
            distances[cell_id] = 0.0
            heapq.heappush(heap, (0.0, cell_id))
    while heap:
        distance, cell_id = heapq.heappop(heap)
        if distance > distances[cell_id]:
            continue
        for neighbor_id, length in graph.get(cell_id, []):
            next_distance = distance + length
            if next_distance < distances[neighbor_id]:
                distances[neighbor_id] = next_distance
                heapq.heappush(heap, (next_distance, neighbor_id))
    if any(not math.isfinite(distance) for distance in distances.values()):
        raise ValueError("marine distance: marine source unreachable in declared graph")
    return distances


def _marine_influence_class(cell: dict[str, Any], distance_km: float | None, continentality: float) -> str:
    if distance_km is None:
        return "no_marine_source"
    if _is_marine(cell):
        return "marine"
    if distance_km <= 250.0 or continentality < 0.24:
        return "coastal"
    if distance_km <= 1000.0 or continentality < 0.45:
        return "maritime_influenced"
    if distance_km <= 2500.0 or continentality < 0.68:
        return "interior"
    return "continental_core"


def _region_record(region_id: int, component: list[dict[str, Any]], region_class: str) -> dict[str, Any]:
    area_km2 = sum(_area(cell) for cell in component)
    divisor = max(1, len(component))
    centroid_lat, centroid_lon = _lat_lon_centroid(component)
    atmospheric_counts = Counter(str(cell.get("atmospheric_cell", "unknown")) for cell in component)
    distances = [cell["distance_to_marine_water_km"] for cell in component if cell["distance_to_marine_water_km"] is not None]
    return {
        "id": region_id,
        "region_class": region_class,
        "cell_ids": sorted(_cell_id(cell) for cell in component),
        "cell_count": len(component),
        "area_km2": _round(area_km2),
        "centroid_lat_deg": centroid_lat,
        "centroid_lon_deg": centroid_lon,
        "mean_distance_to_marine_water_km": _round(sum(distances) / len(distances)) if distances else None,
        "marine_distance_defined_cell_count": len(distances),
        "no_marine_source_cell_count": len(component) - len(distances),
        "mean_continentality_index": _round(sum(float(cell.get("continentality_index", 0.0)) for cell in component) / divisor),
        "mean_oceanic_humidity_availability_index": _round(
            sum(float(cell.get("oceanic_humidity_availability_index", 0.0)) for cell in component) / divisor
        ),
        "mean_temperature_range_c": _round(sum(_temperature_range(cell) for cell in component) / divisor),
        "mean_precipitation_mm_y": _round(sum(float(cell.get("precipitation_mm_y", 0.0)) for cell in component) / divisor),
        "land_cell_count": sum(1 for cell in component if not bool(cell.get("is_water", False))),
        "marine_cell_count": sum(1 for cell in component if _is_marine(cell)),
        "dominant_atmospheric_cell": atmospheric_counts.most_common(1)[0][0] if atmospheric_counts else "unknown",
    }


def _connected_regions(cells: list[dict[str, Any]], cells_by_id: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    remaining = {_cell_id(cell) for cell in cells}
    records: list[dict[str, Any]] = []
    while remaining:
        start = min(remaining)
        start_cell = cells_by_id[start]
        region_class = str(start_cell.get("marine_influence_class", "unknown"))
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
                if neighbor is None or str(neighbor.get("marine_influence_class", "unknown")) != region_class:
                    continue
                remaining.remove(neighbor_id)
                queue.append(neighbor_id)
        region_id = len(records)
        for cell in component:
            cell["climate_continentality_region_id"] = region_id
        records.append(_region_record(region_id, component, region_class))
    return records


def _build_climate_continentality(world: dict[str, Any]) -> dict[str, Any]:
    cells = world.get("cells", [])
    if not isinstance(cells, list) or not cells:
        return world

    cells_by_id = {_cell_id(cell): cell for cell in cells}
    distances = _nearest_marine_distances(world, cells)
    continentality_sum = 0.0
    humidity_sum = 0.0
    distance_sum = 0.0
    max_continentality = 0.0
    high_continentality = 0
    low_humidity = 0
    class_counts: Counter[str] = Counter()

    for cell in cells:
        cell_id = _cell_id(cell)
        distance_km = distances[cell_id]
        temperature_range = _temperature_range(cell)
        transport = _clamp(float(cell.get("humidity_transport_index", 0.0)))
        distance_term = 1.0 if distance_km is None else _clamp(distance_km / 3000.0)
        temperature_term = _clamp(temperature_range / 34.0)
        continentality = _clamp(distance_term * 0.58 + temperature_term * 0.30 + (1.0 - transport) * 0.12)

        proximity = 0.0 if distance_km is None else math.exp(-distance_km / 1200.0)
        fetch = _clamp(float(cell.get("upwind_ocean_fetch_km", 0.0)) / 2500.0)
        advected = _clamp((float(cell.get("advected_moisture_factor", 1.0)) - 0.65) / 0.85)
        humidity = 0.0 if distance_km is None else _clamp(proximity * 0.36 + fetch * 0.30 + advected * 0.20 + transport * 0.14)
        if _is_marine(cell):
            humidity = max(humidity, 0.75)
            continentality = min(continentality, 0.18)
        influence_class = _marine_influence_class(cell, distance_km, continentality)

        cell["distance_to_marine_water_km"] = _round(distance_km) if distance_km is not None else None
        cell["marine_distance_status"] = "no_marine_source" if distance_km is None else "reachable_marine"
        cell["continentality_index"] = _round(continentality)
        cell["oceanic_humidity_availability_index"] = _round(humidity)
        cell["marine_influence_class"] = influence_class
        cell["climate_continentality_region_id"] = -1

        continentality_sum += continentality
        humidity_sum += humidity
        distance_sum += distance_km if distance_km is not None else 0.0
        max_continentality = max(max_continentality, continentality)
        high_continentality += 1 if continentality >= 0.65 else 0
        low_humidity += 1 if humidity <= 0.25 else 0
        class_counts[influence_class] += 1

    regions = _connected_regions(cells, cells_by_id)
    summary = world.setdefault("summary", {})
    divisor = float(len(cells))
    defined_count = sum(distance is not None for distance in distances.values())
    summary["mean_distance_to_marine_water_km"] = _round(distance_sum / defined_count) if defined_count else None
    summary["marine_distance_defined_cell_count"] = defined_count
    summary["no_marine_source_cell_count"] = len(cells) - defined_count
    summary["mean_continentality_index"] = _round(continentality_sum / divisor)
    summary["max_continentality_index"] = _round(max_continentality)
    summary["high_continentality_cell_count"] = high_continentality
    summary["mean_oceanic_humidity_availability_index"] = _round(humidity_sum / divisor)
    summary["low_oceanic_humidity_availability_cell_count"] = low_humidity
    summary["marine_influence_class_counts"] = dict(sorted(class_counts.items()))
    summary["climate_continentality_region_count"] = len(regions)
    summary["continental_core_region_count"] = sum(1 for region in regions if region["region_class"] == "continental_core")
    summary["maritime_influence_region_count"] = sum(
        1 for region in regions if region["region_class"] in {"marine", "coastal", "maritime_influenced"}
    )
    world["climate_continentality_regions"] = regions
    world["climate_continentality_model"] = deepcopy(MODEL)
    return world


def enrich_world_with_climate_continentality(world: dict[str, Any]) -> dict[str, Any]:
    cells = world.get("cells", [])
    if not isinstance(cells, list) or not cells:
        return world
    if "climate_continentality_model" in world and world["climate_continentality_model"] != MODEL:
        raise ValueError("marine distance: unknown model declaration")
    source_graph(world)
    # Geography may have changed since a previous diagnostic. Rebuild privately
    # from current sources, then validate before publishing any new values.
    staged = {**world, "cells": [dict(c) for c in cells], "summary": dict(world.get("summary", {}))}
    _build_climate_continentality(staged)
    require_marine_distance(staged)
    fields = ("distance_to_marine_water_km", "marine_distance_status", "continentality_index",
              "oceanic_humidity_availability_index", "marine_influence_class", "climate_continentality_region_id")
    for cell, update in zip(cells, staged["cells"], strict=True):
        for field in fields:
            cell[field] = update[field]
    world.setdefault("summary", {}).update(staged["summary"])
    world["climate_continentality_regions"] = staged["climate_continentality_regions"]
    world["climate_continentality_model"] = staged["climate_continentality_model"]
    return world
