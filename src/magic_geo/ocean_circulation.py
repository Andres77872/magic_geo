from __future__ import annotations

import math
from collections import Counter, deque
from typing import Any


MARINE_WATER_TYPES = {"ocean", "continental_shelf", "inland_sea"}
WARM_CURRENT_THRESHOLD_C = 0.5
COLD_CURRENT_THRESHOLD_C = -0.5
MERIDIONAL_CURRENT_THRESHOLD = 0.08
HIGH_UPWELLING_THRESHOLD = 0.55
EARTH_RADIUS_KM = 6371.0


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


def _xyz(cell: dict[str, Any]) -> tuple[float, float, float]:
    lat = math.radians(float(cell.get("lat_deg", 0.0)))
    lon = math.radians(float(cell.get("lon_deg", 0.0)))
    cos_lat = math.cos(lat)
    return cos_lat * math.cos(lon), cos_lat * math.sin(lon), math.sin(lat)


def _dot(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _normalize(vector: tuple[float, float, float]) -> tuple[float, float, float]:
    length = math.sqrt(_dot(vector, vector))
    if length <= 1.0e-12:
        return 0.0, 0.0, 0.0
    return vector[0] / length, vector[1] / length, vector[2] / length


def _distance_km(a: dict[str, Any], b: dict[str, Any]) -> float:
    cosine = _clamp(_dot(_xyz(a), _xyz(b)), -1.0, 1.0)
    return math.acos(cosine) * EARTH_RADIUS_KM


def _transport_target(
    cell: dict[str, Any],
    cells_by_id: dict[int, dict[str, Any]],
) -> tuple[int, float, float]:
    lat = math.radians(float(cell.get("lat_deg", 0.0)))
    lon = math.radians(float(cell.get("lon_deg", 0.0)))
    center = _xyz(cell)
    east_basis = (-math.sin(lon), math.cos(lon), 0.0)
    north_basis = (-math.sin(lat) * math.cos(lon), -math.sin(lat) * math.sin(lon), math.cos(lat))
    current_east = float(cell.get("ocean_current_east", 0.0))
    current_north = float(cell.get("ocean_current_north", 0.0))
    current_vector = _normalize(
        (
            current_east * east_basis[0] + current_north * north_basis[0],
            current_east * east_basis[1] + current_north * north_basis[1],
            current_east * east_basis[2] + current_north * north_basis[2],
        )
    )
    best_target = -1
    best_alignment = -1.0
    for raw_neighbor_id in cell.get("neighbors", []):
        neighbor = cells_by_id.get(int(raw_neighbor_id))
        if neighbor is None or not _is_marine(neighbor):
            continue
        neighbor_xyz = _xyz(neighbor)
        tangent = _normalize(
            (
                neighbor_xyz[0] - _dot(neighbor_xyz, center) * center[0],
                neighbor_xyz[1] - _dot(neighbor_xyz, center) * center[1],
                neighbor_xyz[2] - _dot(neighbor_xyz, center) * center[2],
            )
        )
        alignment = _dot(current_vector, tangent)
        neighbor_id = _cell_id(neighbor)
        if alignment > best_alignment or (abs(alignment - best_alignment) <= 1.0e-12 and neighbor_id < best_target):
            best_target = neighbor_id
            best_alignment = alignment
    if best_target < 0 or best_alignment <= 0.0:
        return -1, 0.0, 0.0
    return best_target, _clamp(best_alignment), _distance_km(cell, cells_by_id[best_target])


def _regime(temperature_anomaly_c: float, poleward_index: float) -> str:
    if temperature_anomaly_c >= WARM_CURRENT_THRESHOLD_C:
        thermal = "warm"
    elif temperature_anomaly_c <= COLD_CURRENT_THRESHOLD_C:
        thermal = "cold"
    else:
        thermal = "neutral"
    if poleward_index >= MERIDIONAL_CURRENT_THRESHOLD:
        direction = "poleward"
    elif poleward_index <= -MERIDIONAL_CURRENT_THRESHOLD:
        direction = "equatorward"
    else:
        direction = "zonal"
    return f"{thermal}_{direction}_current"


def _centroid(cells: list[dict[str, Any]]) -> tuple[float, float]:
    x_sum = 0.0
    y_sum = 0.0
    z_sum = 0.0
    weight_sum = 0.0
    for cell in cells:
        weight = _area(cell) or 1.0
        x, y, z = _xyz(cell)
        x_sum += x * weight
        y_sum += y * weight
        z_sum += z * weight
        weight_sum += weight
    if weight_sum <= 0.0:
        return 0.0, 0.0
    return (
        _round(math.degrees(math.atan2(z_sum, math.hypot(x_sum, y_sum)))),
        _round(math.degrees(math.atan2(y_sum, x_sum))),
    )


def _connected_systems(
    marine_cells: list[dict[str, Any]],
    cells_by_id: dict[int, dict[str, Any]],
) -> list[list[dict[str, Any]]]:
    remaining = {_cell_id(cell) for cell in marine_cells}
    systems: list[list[dict[str, Any]]] = []
    while remaining:
        start = min(remaining)
        regime = str(cells_by_id[start].get("ocean_current_regime", "neutral_zonal_current"))
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
                if neighbor is None or str(neighbor.get("ocean_current_regime", "")) != regime:
                    continue
                remaining.remove(neighbor_id)
                queue.append(neighbor_id)
        systems.append(component)
    return systems


def _system_record(system_id: int, cells: list[dict[str, Any]], cells_by_id: dict[int, dict[str, Any]]) -> dict[str, Any]:
    divisor = max(1, len(cells))
    cell_ids = sorted(_cell_id(cell) for cell in cells)
    cell_id_set = set(cell_ids)
    centroid_lat, centroid_lon = _centroid(cells)
    water_body_counts = Counter(str(cell.get("water_body_type", "land")) for cell in cells)
    north_count = sum(1 for cell in cells if float(cell.get("lat_deg", 0.0)) > 5.0)
    south_count = sum(1 for cell in cells if float(cell.get("lat_deg", 0.0)) < -5.0)
    hemisphere = "northern" if north_count == len(cells) else ("southern" if south_count == len(cells) else "cross_equatorial")
    target_ids = [int(cell.get("ocean_current_transport_target_cell_id", -1)) for cell in cells]
    return {
        "id": system_id,
        "system_class": str(cells[0].get("ocean_current_regime", "neutral_zonal_current")),
        "hemisphere": hemisphere,
        "cell_ids": cell_ids,
        "cell_count": len(cells),
        "area_km2": _round(sum(_area(cell) for cell in cells)),
        "centroid_lat_deg": centroid_lat,
        "centroid_lon_deg": centroid_lon,
        "marine_region_ids": sorted({int(cell.get("marine_region_id", -1)) for cell in cells if int(cell.get("marine_region_id", -1)) >= 0}),
        "water_body_type_counts": dict(sorted(water_body_counts.items())),
        "dominant_water_body_type": sorted(water_body_counts.items(), key=lambda item: (-item[1], item[0]))[0][0],
        "mean_current_east": _round(sum(float(cell.get("ocean_current_east", 0.0)) for cell in cells) / divisor),
        "mean_current_north": _round(sum(float(cell.get("ocean_current_north", 0.0)) for cell in cells) / divisor),
        "mean_current_speed_index": _round(sum(float(cell.get("ocean_current_speed_index", 0.0)) for cell in cells) / divisor),
        "mean_current_temperature_c": _round(sum(float(cell.get("ocean_current_temperature_c", 0.0)) for cell in cells) / divisor),
        "mean_current_moisture_factor": _round(sum(float(cell.get("ocean_current_moisture_factor", 1.0)) for cell in cells) / divisor),
        "mean_poleward_transport_index": _round(sum(float(cell.get("ocean_current_poleward_index", 0.0)) for cell in cells) / divisor),
        "mean_heat_transport_index": _round(sum(float(cell.get("ocean_heat_transport_index", 0.0)) for cell in cells) / divisor),
        "mean_transport_alignment": _round(sum(float(cell.get("ocean_current_transport_alignment", 0.0)) for cell in cells) / divisor),
        "mean_convergence_index": _round(sum(float(cell.get("ocean_current_convergence_index", 0.0)) for cell in cells) / divisor),
        "mean_upwelling_index": _round(sum(float(cell.get("ocean_upwelling_index", 0.0)) for cell in cells) / divisor),
        "transport_edge_count": sum(1 for target_id in target_ids if target_id >= 0),
        "internal_transport_edge_count": sum(1 for target_id in target_ids if target_id in cell_id_set),
        "external_transport_edge_count": sum(1 for target_id in target_ids if target_id >= 0 and target_id not in cell_id_set),
        "terminal_cell_count": sum(1 for target_id in target_ids if target_id < 0),
        "coastal_cell_count": sum(
            1
            for cell in cells
            if any(
                (neighbor := cells_by_id.get(int(raw_neighbor_id))) is not None and not bool(neighbor.get("is_water", False))
                for raw_neighbor_id in cell.get("neighbors", [])
            )
        ),
        "continental_shelf_cell_count": water_body_counts.get("continental_shelf", 0),
        "warm_current_cell_count": sum(1 for cell in cells if float(cell.get("ocean_current_temperature_c", 0.0)) >= WARM_CURRENT_THRESHOLD_C),
        "cold_current_cell_count": sum(1 for cell in cells if float(cell.get("ocean_current_temperature_c", 0.0)) <= COLD_CURRENT_THRESHOLD_C),
        "poleward_current_cell_count": sum(1 for cell in cells if float(cell.get("ocean_current_poleward_index", 0.0)) >= MERIDIONAL_CURRENT_THRESHOLD),
        "equatorward_current_cell_count": sum(1 for cell in cells if float(cell.get("ocean_current_poleward_index", 0.0)) <= -MERIDIONAL_CURRENT_THRESHOLD),
        "high_upwelling_cell_count": sum(1 for cell in cells if float(cell.get("ocean_upwelling_index", 0.0)) >= HIGH_UPWELLING_THRESHOLD),
    }


def enrich_world_with_ocean_circulation(world: dict[str, Any]) -> dict[str, Any]:
    cells = world.get("cells", [])
    if not isinstance(cells, list) or not cells:
        return world

    cells_by_id = {_cell_id(cell): cell for cell in cells}
    marine_cells = [cell for cell in cells if _is_marine(cell)]
    incoming_counts: Counter[int] = Counter()

    for cell in cells:
        cell["ocean_current_speed_index"] = 0.0
        cell["ocean_current_poleward_index"] = 0.0
        cell["ocean_heat_transport_index"] = 0.0
        cell["ocean_current_transport_alignment"] = 0.0
        cell["ocean_current_transport_target_cell_id"] = -1
        cell["ocean_current_transport_distance_km"] = 0.0
        cell["ocean_current_convergence_index"] = 0.0
        cell["ocean_upwelling_index"] = 0.0
        cell["ocean_current_regime"] = "non_marine"
        cell["ocean_current_system_id"] = -1
        if not _is_marine(cell):
            continue

        current_east = float(cell.get("ocean_current_east", 0.0))
        current_north = float(cell.get("ocean_current_north", 0.0))
        speed = math.sqrt(current_east * current_east + current_north * current_north)
        hemisphere_sign = 1.0 if float(cell.get("lat_deg", 0.0)) >= 0.0 else -1.0
        poleward = _clamp((current_north / max(1.0e-9, speed)) * hemisphere_sign, -1.0, 1.0)
        temperature_anomaly = float(cell.get("ocean_current_temperature_c", 0.0))
        heat_transport = _clamp((temperature_anomaly / 4.5) * poleward, -1.0, 1.0)
        target_id, alignment, distance_km = _transport_target(cell, cells_by_id)

        cell["ocean_current_speed_index"] = _round(speed)
        cell["ocean_current_poleward_index"] = _round(poleward)
        cell["ocean_heat_transport_index"] = _round(heat_transport)
        cell["ocean_current_transport_alignment"] = _round(alignment)
        cell["ocean_current_transport_target_cell_id"] = target_id
        cell["ocean_current_transport_distance_km"] = _round(distance_km)
        cell["ocean_current_regime"] = _regime(temperature_anomaly, poleward)
        if target_id >= 0:
            incoming_counts[target_id] += 1

    for cell in marine_cells:
        marine_neighbors = [
            cells_by_id[int(raw_neighbor_id)]
            for raw_neighbor_id in cell.get("neighbors", [])
            if int(raw_neighbor_id) in cells_by_id and _is_marine(cells_by_id[int(raw_neighbor_id)])
        ]
        outgoing = 1 if int(cell.get("ocean_current_transport_target_cell_id", -1)) >= 0 else 0
        convergence = _clamp(
            (incoming_counts[_cell_id(cell)] - outgoing) / max(1, len(marine_neighbors)),
            -1.0,
            1.0,
        )
        coastal = any(
            (neighbor := cells_by_id.get(int(raw_neighbor_id))) is not None and not bool(neighbor.get("is_water", False))
            for raw_neighbor_id in cell.get("neighbors", [])
        )
        temperature_anomaly = float(cell.get("ocean_current_temperature_c", 0.0))
        poleward = float(cell.get("ocean_current_poleward_index", 0.0))
        coldness = _clamp(-temperature_anomaly / 3.0)
        equatorward = _clamp(-poleward)
        divergence = _clamp(-convergence)
        wind_divergence = _clamp(float(cell.get("wind_divergence_index", 0.0)))
        shelf = 1.0 if str(cell.get("water_body_type", "")) == "continental_shelf" else 0.0
        equatorial = _clamp(1.0 - abs(float(cell.get("lat_deg", 0.0))) / 18.0)
        if coastal:
            upwelling = _clamp(coldness * 0.32 + equatorward * 0.24 + divergence * 0.20 + wind_divergence * 0.12 + shelf * 0.12)
        else:
            upwelling = _clamp(equatorial * 0.24 + divergence * 0.28 + coldness * 0.14 + equatorward * 0.10)
        cell["ocean_current_convergence_index"] = _round(convergence)
        cell["ocean_upwelling_index"] = _round(upwelling)

    components = _connected_systems(marine_cells, cells_by_id)
    systems: list[dict[str, Any]] = []
    for system_id, component in enumerate(components):
        for cell in component:
            cell["ocean_current_system_id"] = system_id
        systems.append(_system_record(system_id, component, cells_by_id))

    transport_edges: list[dict[str, Any]] = []
    for cell in sorted(marine_cells, key=_cell_id):
        target_id = int(cell.get("ocean_current_transport_target_cell_id", -1))
        if target_id < 0:
            continue
        target = cells_by_id[target_id]
        source_system_id = int(cell.get("ocean_current_system_id", -1))
        target_system_id = int(target.get("ocean_current_system_id", -1))
        source_region_id = int(cell.get("marine_region_id", -1))
        target_region_id = int(target.get("marine_region_id", -1))
        transport_edges.append(
            {
                "id": len(transport_edges),
                "source_cell_id": _cell_id(cell),
                "target_cell_id": target_id,
                "source_system_id": source_system_id,
                "target_system_id": target_system_id,
                "source_marine_region_id": source_region_id,
                "target_marine_region_id": target_region_id,
                "great_circle_distance_km": _round(float(cell.get("ocean_current_transport_distance_km", 0.0))),
                "alignment": _round(float(cell.get("ocean_current_transport_alignment", 0.0))),
                "current_speed_index": _round(float(cell.get("ocean_current_speed_index", 0.0))),
                "current_temperature_c": _round(float(cell.get("ocean_current_temperature_c", 0.0))),
                "poleward_transport_index": _round(float(cell.get("ocean_current_poleward_index", 0.0))),
                "heat_transport_index": _round(float(cell.get("ocean_heat_transport_index", 0.0))),
                "upwelling_index": _round(float(cell.get("ocean_upwelling_index", 0.0))),
                "crosses_system_boundary": source_system_id != target_system_id,
                "crosses_marine_region_boundary": source_region_id != target_region_id,
            }
        )

    summary = world.setdefault("summary", {})
    divisor = max(1, len(marine_cells))
    regime_counts = Counter(str(cell.get("ocean_current_regime", "non_marine")) for cell in cells)
    system_class_counts = Counter(str(system["system_class"]) for system in systems)
    summary["ocean_current_cell_count"] = len(marine_cells)
    summary["ocean_current_system_count"] = len(systems)
    summary["ocean_current_transport_edge_count"] = len(transport_edges)
    summary["ocean_current_transport_coverage_fraction"] = _round(len(transport_edges) / divisor)
    summary["ocean_current_total_transport_length_km"] = _round(
        sum(float(edge["great_circle_distance_km"]) for edge in transport_edges)
    )
    summary["ocean_current_total_area_km2"] = _round(sum(_area(cell) for cell in marine_cells))
    summary["mean_ocean_circulation_speed_index"] = _round(
        sum(float(cell.get("ocean_current_speed_index", 0.0)) for cell in marine_cells) / divisor
    )
    summary["mean_ocean_current_transport_alignment"] = _round(
        sum(float(cell.get("ocean_current_transport_alignment", 0.0)) for cell in marine_cells) / divisor
    )
    summary["mean_ocean_current_poleward_index"] = _round(
        sum(float(cell.get("ocean_current_poleward_index", 0.0)) for cell in marine_cells) / divisor
    )
    summary["mean_ocean_heat_transport_index"] = _round(
        sum(float(cell.get("ocean_heat_transport_index", 0.0)) for cell in marine_cells) / divisor
    )
    summary["mean_ocean_current_convergence_index"] = _round(
        sum(float(cell.get("ocean_current_convergence_index", 0.0)) for cell in marine_cells) / divisor
    )
    summary["mean_ocean_upwelling_index"] = _round(
        sum(float(cell.get("ocean_upwelling_index", 0.0)) for cell in marine_cells) / divisor
    )
    summary["warm_ocean_current_cell_count"] = sum(
        1 for cell in marine_cells if float(cell.get("ocean_current_temperature_c", 0.0)) >= WARM_CURRENT_THRESHOLD_C
    )
    summary["cold_ocean_current_cell_count"] = sum(
        1 for cell in marine_cells if float(cell.get("ocean_current_temperature_c", 0.0)) <= COLD_CURRENT_THRESHOLD_C
    )
    summary["poleward_ocean_current_cell_count"] = sum(
        1 for cell in marine_cells if float(cell.get("ocean_current_poleward_index", 0.0)) >= MERIDIONAL_CURRENT_THRESHOLD
    )
    summary["equatorward_ocean_current_cell_count"] = sum(
        1 for cell in marine_cells if float(cell.get("ocean_current_poleward_index", 0.0)) <= -MERIDIONAL_CURRENT_THRESHOLD
    )
    summary["high_ocean_upwelling_cell_count"] = sum(
        1 for cell in marine_cells if float(cell.get("ocean_upwelling_index", 0.0)) >= HIGH_UPWELLING_THRESHOLD
    )
    summary["ocean_current_regime_counts"] = dict(sorted(regime_counts.items()))
    summary["ocean_current_system_class_counts"] = dict(sorted(system_class_counts.items()))
    world["ocean_current_systems"] = systems
    world["ocean_current_transport_edges"] = transport_edges
    return world
