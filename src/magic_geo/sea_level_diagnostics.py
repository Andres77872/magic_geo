from __future__ import annotations

import math
from collections import Counter
from typing import Any, Callable


MARINE_WATER_TYPES = {"ocean", "continental_shelf", "inland_sea"}


def _cell_id(cell: dict[str, Any]) -> int:
    return int(cell.get("id", -1))


def _area(cell: dict[str, Any]) -> float:
    return max(0.0, float(cell.get("area_km2", 0.0)))


def _is_land(cell: dict[str, Any]) -> bool:
    return not bool(cell.get("is_water", False))


def _is_marine(cell: dict[str, Any]) -> bool:
    return str(cell.get("water_body_type", "land")) in MARINE_WATER_TYPES


def _dominant_name(cells: list[dict[str, Any]], key: str, default: str = "unknown") -> str:
    counts: Counter[str] = Counter()
    for cell in cells:
        value = str(cell.get(key, default))
        counts[value] += 1
    return counts.most_common(1)[0][0] if counts else default


def _component_cells(
    start_id: int,
    cells_by_id: dict[int, dict[str, Any]],
    visited: set[int],
    predicate: Callable[[dict[str, Any]], bool],
) -> list[dict[str, Any]]:
    stack = [start_id]
    component: list[dict[str, Any]] = []
    visited.add(start_id)
    while stack:
        current_id = stack.pop()
        current = cells_by_id[current_id]
        component.append(current)
        for neighbor_id_raw in current.get("neighbors", []):
            neighbor_id = int(neighbor_id_raw)
            if neighbor_id in visited:
                continue
            neighbor = cells_by_id.get(neighbor_id)
            if neighbor is None or not predicate(neighbor):
                continue
            visited.add(neighbor_id)
            stack.append(neighbor_id)
    return component


def _spherical_centroid(cells: list[dict[str, Any]]) -> tuple[float, float]:
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
    if weight_sum <= 0.0 or (abs(x_sum) + abs(y_sum) + abs(z_sum)) <= 1.0e-12:
        return 0.0, 0.0
    x = x_sum / weight_sum
    y = y_sum / weight_sum
    z = z_sum / weight_sum
    lon = math.degrees(math.atan2(y, x))
    hyp = math.hypot(x, y)
    lat = math.degrees(math.atan2(z, hyp))
    return round(lat, 6), round(lon, 6)


def _landmass_class(area_km2: float) -> str:
    if area_km2 >= 5_000_000.0:
        return "continent"
    if area_km2 >= 500_000.0:
        return "large_island"
    if area_km2 >= 50_000.0:
        return "island"
    return "islet"


def _landmass_record(
    component_id: int,
    component: list[dict[str, Any]],
    cells_by_id: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    cell_ids = sorted(_cell_id(cell) for cell in component)
    area_km2 = sum(_area(cell) for cell in component)
    coastal_cells = 0
    shoreline_edges = 0
    for cell in component:
        water_edges = sum(
            1
            for neighbor_id in cell.get("neighbors", [])
            if (neighbor := cells_by_id.get(int(neighbor_id))) is not None and not _is_land(neighbor)
        )
        if water_edges:
            coastal_cells += 1
            shoreline_edges += water_edges
    centroid_lat, centroid_lon = _spherical_centroid(component)
    return {
        "id": component_id,
        "cell_ids": cell_ids,
        "cell_count": len(component),
        "area_km2": round(area_km2, 6),
        "centroid_lat_deg": centroid_lat,
        "centroid_lon_deg": centroid_lon,
        "mean_elevation_m": round(sum(float(cell.get("elevation_m", 0.0)) for cell in component) / max(1, len(component)), 6),
        "max_elevation_m": round(max(float(cell.get("elevation_m", 0.0)) for cell in component), 6),
        "coastal_cell_count": coastal_cells,
        "shoreline_neighbor_edge_count": shoreline_edges,
        "island_class": _landmass_class(area_km2),
        "dominant_biome": _dominant_name(component, "biome"),
        "dominant_lithology": _dominant_name(component, "lithology"),
    }


def _marine_region_record(
    component_id: int,
    component: list[dict[str, Any]],
    cells_by_id: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    cell_ids = sorted(_cell_id(cell) for cell in component)
    area_km2 = sum(_area(cell) for cell in component)
    water_body_counts = Counter(str(cell.get("water_body_type", "unknown")) for cell in component)
    adjacent_landmass_ids: set[int] = set()
    coastal_cells = 0
    for cell in component:
        cell_has_land = False
        for neighbor_id_raw in cell.get("neighbors", []):
            neighbor = cells_by_id.get(int(neighbor_id_raw))
            if neighbor is None or not _is_land(neighbor):
                continue
            cell_has_land = True
            landmass_id = int(neighbor.get("landmass_id", -1))
            if landmass_id >= 0:
                adjacent_landmass_ids.add(landmass_id)
        if cell_has_land:
            coastal_cells += 1
    connected_to_open_ocean = water_body_counts.get("ocean", 0) > 0
    region_class = "open_ocean" if connected_to_open_ocean else ("inland_sea" if water_body_counts.get("inland_sea", 0) else "continental_shelf")
    centroid_lat, centroid_lon = _spherical_centroid(component)
    return {
        "id": component_id,
        "cell_ids": cell_ids,
        "cell_count": len(component),
        "area_km2": round(area_km2, 6),
        "centroid_lat_deg": centroid_lat,
        "centroid_lon_deg": centroid_lon,
        "region_class": region_class,
        "dominant_water_body_type": water_body_counts.most_common(1)[0][0],
        "water_body_counts": dict(sorted(water_body_counts.items())),
        "mean_water_depth_m": round(sum(float(cell.get("water_depth_m", 0.0)) for cell in component) / max(1, len(component)), 6),
        "max_water_depth_m": round(max(float(cell.get("water_depth_m", 0.0)) for cell in component), 6),
        "coastal_cell_count": coastal_cells,
        "adjacent_landmass_ids": sorted(adjacent_landmass_ids),
        "connected_to_open_ocean": connected_to_open_ocean,
    }


def _continental_shelf_record(
    component_id: int,
    component: list[dict[str, Any]],
    cells_by_id: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    cell_ids = sorted(_cell_id(cell) for cell in component)
    area_km2 = sum(_area(cell) for cell in component)
    adjacent_landmass_ids: set[int] = set()
    adjacent_marine_region_ids: set[int] = set()
    shoreline_edges = 0
    shelf_break_edges = 0
    open_ocean_edges = 0
    inland_sea_edges = 0
    coastal_cells = 0
    shelf_break_cells = 0
    for cell in component:
        cell_has_land = False
        cell_has_shelf_break = False
        marine_region_id = int(cell.get("marine_region_id", -1))
        if marine_region_id >= 0:
            adjacent_marine_region_ids.add(marine_region_id)
        for neighbor_id_raw in cell.get("neighbors", []):
            neighbor = cells_by_id.get(int(neighbor_id_raw))
            if neighbor is None:
                continue
            if _is_land(neighbor):
                shoreline_edges += 1
                cell_has_land = True
                landmass_id = int(neighbor.get("landmass_id", -1))
                if landmass_id >= 0:
                    adjacent_landmass_ids.add(landmass_id)
                continue
            neighbor_water = str(neighbor.get("water_body_type", "land"))
            if neighbor_water in MARINE_WATER_TYPES:
                neighbor_region_id = int(neighbor.get("marine_region_id", -1))
                if neighbor_region_id >= 0:
                    adjacent_marine_region_ids.add(neighbor_region_id)
            if neighbor_water != "continental_shelf" and neighbor_water in MARINE_WATER_TYPES:
                shelf_break_edges += 1
                cell_has_shelf_break = True
                if neighbor_water == "ocean":
                    open_ocean_edges += 1
                elif neighbor_water == "inland_sea":
                    inland_sea_edges += 1
        coastal_cells += 1 if cell_has_land else 0
        shelf_break_cells += 1 if cell_has_shelf_break else 0
    centroid_lat, centroid_lon = _spherical_centroid(component)
    return {
        "id": component_id,
        "cell_ids": cell_ids,
        "cell_count": len(component),
        "area_km2": round(area_km2, 6),
        "centroid_lat_deg": centroid_lat,
        "centroid_lon_deg": centroid_lon,
        "mean_water_depth_m": round(sum(float(cell.get("water_depth_m", 0.0)) for cell in component) / max(1, len(component)), 6),
        "max_water_depth_m": round(max(float(cell.get("water_depth_m", 0.0)) for cell in component), 6),
        "mean_sediment_thickness_m": round(
            sum(float(cell.get("sediment_thickness_m", 0.0)) for cell in component) / max(1, len(component)),
            6,
        ),
        "coastal_cell_count": coastal_cells,
        "shelf_break_cell_count": shelf_break_cells,
        "shoreline_neighbor_edge_count": shoreline_edges,
        "shelf_break_neighbor_edge_count": shelf_break_edges,
        "open_ocean_neighbor_edge_count": open_ocean_edges,
        "inland_sea_neighbor_edge_count": inland_sea_edges,
        "adjacent_landmass_ids": sorted(adjacent_landmass_ids),
        "marine_region_ids": sorted(adjacent_marine_region_ids),
    }


def _marine_chokepoints(
    cells: list[dict[str, Any]],
    cells_by_id: dict[int, dict[str, Any]],
) -> list[dict[str, Any]]:
    chokepoints: list[dict[str, Any]] = []
    for cell in sorted((cell for cell in cells if _is_marine(cell)), key=_cell_id):
        neighbors = [cells_by_id[int(neighbor_id)] for neighbor_id in cell.get("neighbors", []) if int(neighbor_id) in cells_by_id]
        if not neighbors:
            continue
        land_neighbors = [neighbor for neighbor in neighbors if _is_land(neighbor)]
        marine_neighbors = [neighbor for neighbor in neighbors if _is_marine(neighbor)]
        if len(land_neighbors) < 2 or len(marine_neighbors) < 2:
            continue
        constriction = len(land_neighbors) / max(1, len(neighbors))
        adjacent_landmass_ids = sorted(
            {
                int(neighbor.get("landmass_id", -1))
                for neighbor in land_neighbors
                if int(neighbor.get("landmass_id", -1)) >= 0
            }
        )
        if len(adjacent_landmass_ids) < 2 and constriction < 0.5:
            continue
        adjacent_marine_region_ids = sorted(
            {
                int(neighbor.get("marine_region_id", -1))
                for neighbor in marine_neighbors + [cell]
                if int(neighbor.get("marine_region_id", -1)) >= 0
            }
        )
        chokepoint_type = "strait" if len(adjacent_landmass_ids) >= 2 else "marine_narrows"
        width_proxy = float(cell.get("mean_neighbor_edge_length_km", 0.0)) / max(1, len(land_neighbors))
        chokepoint_id = len(chokepoints)
        cell["marine_chokepoint_id"] = chokepoint_id
        chokepoints.append(
            {
                "id": chokepoint_id,
                "cell_id": _cell_id(cell),
                "type": chokepoint_type,
                "marine_region_id": int(cell.get("marine_region_id", -1)),
                "water_body_type": str(cell.get("water_body_type", "unknown")),
                "lat_deg": round(float(cell.get("lat_deg", 0.0)), 6),
                "lon_deg": round(float(cell.get("lon_deg", 0.0)), 6),
                "water_depth_m": round(float(cell.get("water_depth_m", 0.0)), 6),
                "land_neighbor_edge_count": len(land_neighbors),
                "marine_neighbor_edge_count": len(marine_neighbors),
                "constriction_index": round(constriction, 6),
                "width_proxy_km": round(max(0.0, width_proxy), 6),
                "adjacent_landmass_ids": adjacent_landmass_ids,
                "adjacent_marine_region_ids": adjacent_marine_region_ids,
            }
        )
    return chokepoints


def enrich_world_with_sea_level_diagnostics(world: dict[str, Any]) -> dict[str, Any]:
    cells = world.get("cells", [])
    cells_by_id = {_cell_id(cell): cell for cell in cells}

    for cell in cells:
        cell["landmass_id"] = -1
        cell["marine_region_id"] = -1
        cell["marine_chokepoint_id"] = -1
        cell["continental_shelf_id"] = -1
        cell["island_class"] = "water" if not _is_land(cell) else "unassigned"

    landmasses: list[dict[str, Any]] = []
    visited_land: set[int] = set()
    for cell in sorted((cell for cell in cells if _is_land(cell)), key=_cell_id):
        cell_id = _cell_id(cell)
        if cell_id in visited_land:
            continue
        component = _component_cells(cell_id, cells_by_id, visited_land, _is_land)
        landmass_id = len(landmasses)
        record = _landmass_record(landmass_id, component, cells_by_id)
        for component_cell in component:
            component_cell["landmass_id"] = landmass_id
            component_cell["island_class"] = record["island_class"]
        landmasses.append(record)

    marine_regions: list[dict[str, Any]] = []
    visited_marine: set[int] = set()
    for cell in sorted((cell for cell in cells if _is_marine(cell)), key=_cell_id):
        cell_id = _cell_id(cell)
        if cell_id in visited_marine:
            continue
        component = _component_cells(cell_id, cells_by_id, visited_marine, _is_marine)
        marine_region_id = len(marine_regions)
        for component_cell in component:
            component_cell["marine_region_id"] = marine_region_id
        marine_regions.append(_marine_region_record(marine_region_id, component, cells_by_id))

    continental_shelves: list[dict[str, Any]] = []
    visited_shelf: set[int] = set()
    for cell in sorted((cell for cell in cells if str(cell.get("water_body_type", "land")) == "continental_shelf"), key=_cell_id):
        cell_id = _cell_id(cell)
        if cell_id in visited_shelf:
            continue
        component = _component_cells(
            cell_id,
            cells_by_id,
            visited_shelf,
            lambda candidate: str(candidate.get("water_body_type", "land")) == "continental_shelf",
        )
        shelf_id = len(continental_shelves)
        for component_cell in component:
            component_cell["continental_shelf_id"] = shelf_id
        continental_shelves.append(_continental_shelf_record(shelf_id, component, cells_by_id))

    marine_chokepoints = _marine_chokepoints(cells, cells_by_id)

    summary = world.setdefault("summary", {})
    landmass_areas = [float(record["area_km2"]) for record in landmasses]
    marine_region_areas = [float(record["area_km2"]) for record in marine_regions]
    shelf_areas = [float(record["area_km2"]) for record in continental_shelves]
    shelf_cell_count = sum(int(record["cell_count"]) for record in continental_shelves)
    shelf_area = sum(shelf_areas)
    shelf_depth_sum = sum(float(cell.get("water_depth_m", 0.0)) for cell in cells if str(cell.get("water_body_type", "land")) == "continental_shelf")
    summary["landmass_count"] = len(landmasses)
    summary["continent_landmass_count"] = sum(1 for record in landmasses if record["island_class"] == "continent")
    summary["island_landmass_count"] = sum(1 for record in landmasses if record["island_class"] != "continent")
    summary["largest_landmass_area_km2"] = round(max(landmass_areas, default=0.0), 6)
    summary["mean_landmass_area_km2"] = round(sum(landmass_areas) / len(landmass_areas), 6) if landmass_areas else 0.0
    summary["marine_region_count"] = len(marine_regions)
    summary["open_ocean_marine_region_count"] = sum(1 for record in marine_regions if record["region_class"] == "open_ocean")
    summary["inland_sea_marine_region_count"] = sum(1 for record in marine_regions if record["region_class"] == "inland_sea")
    summary["continental_shelf_marine_region_count"] = sum(1 for record in marine_regions if record["region_class"] == "continental_shelf")
    summary["largest_marine_region_area_km2"] = round(max(marine_region_areas, default=0.0), 6)
    summary["continental_shelf_count"] = len(continental_shelves)
    summary["continental_shelf_cell_count"] = shelf_cell_count
    summary["continental_shelf_total_area_km2"] = round(shelf_area, 6)
    summary["largest_continental_shelf_area_km2"] = round(max(shelf_areas, default=0.0), 6)
    summary["mean_continental_shelf_depth_m"] = round(shelf_depth_sum / shelf_cell_count, 6) if shelf_cell_count else 0.0
    summary["continental_shelf_shoreline_edge_count"] = sum(int(record["shoreline_neighbor_edge_count"]) for record in continental_shelves)
    summary["continental_shelf_break_edge_count"] = sum(int(record["shelf_break_neighbor_edge_count"]) for record in continental_shelves)
    summary["marine_chokepoint_count"] = len(marine_chokepoints)
    summary["strait_chokepoint_count"] = sum(1 for record in marine_chokepoints if record["type"] == "strait")
    summary["mean_marine_chokepoint_constriction_index"] = (
        round(sum(float(record["constriction_index"]) for record in marine_chokepoints) / len(marine_chokepoints), 6)
        if marine_chokepoints
        else 0.0
    )

    world["landmasses"] = landmasses
    world["marine_regions"] = marine_regions
    world["continental_shelves"] = continental_shelves
    world["marine_chokepoints"] = marine_chokepoints
    return world
