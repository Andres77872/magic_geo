from __future__ import annotations

from collections import Counter, deque
from typing import Any


ECOTONE_THRESHOLD = 0.52
MARINE_WATER_TYPES = {"ocean", "continental_shelf", "inland_sea"}


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _primary_key(counter: Counter[str], fallback: str) -> str:
    if not counter:
        return fallback
    return sorted(counter.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _is_coastal_land(cell: dict[str, Any], cells_by_id: dict[int, dict[str, Any]]) -> bool:
    if bool(cell.get("is_water", False)):
        return False
    neighbors = cell.get("neighbors", [])
    if not isinstance(neighbors, list):
        return False
    for neighbor_id_raw in neighbors:
        neighbor = cells_by_id.get(int(neighbor_id_raw))
        if neighbor is None:
            continue
        if str(neighbor.get("water_body_type", "")) in MARINE_WATER_TYPES:
            return True
    return False


def _has_freshwater_neighbor(cell: dict[str, Any], cells_by_id: dict[int, dict[str, Any]]) -> bool:
    neighbors = cell.get("neighbors", [])
    if not isinstance(neighbors, list):
        return False
    for neighbor_id_raw in neighbors:
        neighbor = cells_by_id.get(int(neighbor_id_raw))
        if neighbor is None:
            continue
        if str(neighbor.get("water_body_type", "")) in {"fresh_lake", "lake"} or bool(neighbor.get("is_river", False)):
            return True
    return False


def _score_ecotones(cell: dict[str, Any], cells_by_id: dict[int, dict[str, Any]]) -> dict[str, float]:
    if bool(cell.get("is_water", False)):
        return {}

    biome = str(cell.get("biome", "unknown"))
    ice_thickness = float(cell.get("ice_thickness_m", 0.0))
    if biome == "ice_cap" or ice_thickness > 80.0:
        return {}
    temperature = float(cell.get("temperature_c", 0.0))
    precipitation = max(0.0, float(cell.get("precipitation_mm_y", 0.0)))
    elevation = float(cell.get("elevation_m", 0.0))
    frost_months = int(cell.get("frost_months", 0))
    dry_months = int(cell.get("dry_season_months", 0))
    wet_months = int(cell.get("wet_season_months", 0))
    soil_moisture = _clamp(float(cell.get("soil_moisture_index", 0.0)))
    seasonal_aridity = _clamp(float(cell.get("seasonal_aridity_index", 0.0)))
    aridity = _clamp(float(cell.get("climatic_water_deficit_mm_y", 0.0)) / max(1.0, float(cell.get("potential_evapotranspiration_mm_y", 1.0))))
    orographic = _clamp((float(cell.get("orographic_factor", 1.0)) - 0.9) / 0.55)
    humidity_transport = _clamp(float(cell.get("humidity_transport_index", 0.0)))
    coastal = _is_coastal_land(cell, cells_by_id)
    freshwater = _has_freshwater_neighbor(cell, cells_by_id)
    lowland = 1.0 - _clamp(max(0.0, elevation) / 350.0)
    highland = _clamp((elevation - 700.0) / 2600.0)
    mangrove_gate = coastal and temperature >= 18.0 and frost_months == 0 and elevation <= 80.0 and (
        soil_moisture >= 0.58 or precipitation >= 900.0
    )
    cloud_forest_gate = (
        650.0 <= elevation <= 3300.0
        and 7.0 <= temperature <= 24.0
        and precipitation >= 900.0
        and (wet_months >= 6 or orographic >= 0.30 or humidity_transport >= 0.45)
    )
    alpine_paramo_gate = (
        elevation >= 2200.0
        and -2.5 <= temperature <= 11.0
        and precipitation >= 350.0
        and 1 <= frost_months <= 9
        and ice_thickness <= 80.0
    )

    return {
        "mangrove": 0.0 if not mangrove_gate else _clamp(
            (1.0 if coastal else 0.0) * 0.30
            + _clamp((temperature - 17.0) / 12.0) * 0.20
            + (1.0 if frost_months == 0 else 0.0) * 0.14
            + soil_moisture * 0.18
            + _clamp(precipitation / 1800.0) * 0.10
            + lowland * 0.08
        ),
        "cloud_forest": 0.0 if not cloud_forest_gate else _clamp(
            _clamp((precipitation - 850.0) / 1600.0) * 0.25
            + _clamp(1.0 - abs(temperature - 15.0) / 11.0) * 0.18
            + _clamp((elevation - 800.0) / 1800.0) * 0.18
            + _clamp((2800.0 - elevation) / 1700.0) * 0.08
            + orographic * 0.14
            + humidity_transport * 0.10
            + _clamp(wet_months / 12.0) * 0.07
        ),
        "alpine_paramo": 0.0 if not alpine_paramo_gate else _clamp(
            _clamp((elevation - 2600.0) / 1800.0) * 0.30
            + _clamp(1.0 - abs(temperature - 4.0) / 9.0) * 0.22
            + _clamp((precipitation - 450.0) / 1200.0) * 0.12
            + _clamp((8 - abs(frost_months - 4)) / 8.0) * 0.14
            + (0.12 if biome in {"alpine", "tundra", "temperate_grassland"} else 0.0)
            + highland * 0.10
        ),
        "dry_forest": _clamp(
            _clamp((temperature - 17.0) / 10.0) * 0.18
            + _clamp((precipitation - 450.0) / 900.0) * 0.20
            + _clamp((1400.0 - precipitation) / 900.0) * 0.12
            + _clamp(dry_months / 7.0) * 0.20
            + _clamp(wet_months / 8.0) * 0.12
            + (0.18 if "forest" in biome else 0.0)
        ),
        "mediterranean_scrub": _clamp(
            _clamp(1.0 - abs(temperature - 14.0) / 12.0) * 0.18
            + _clamp((dry_months - 2) / 6.0) * 0.22
            + _clamp((precipitation - 280.0) / 650.0) * 0.16
            + _clamp((1100.0 - precipitation) / 700.0) * 0.12
            + seasonal_aridity * 0.14
            + (0.18 if biome in {"mediterranean_scrub", "temperate_grassland", "temperate_forest"} else 0.0)
        ),
        "swamp": _clamp(
            soil_moisture * 0.30
            + (0.18 if freshwater else 0.0)
            + (0.18 if biome == "wetland" else 0.0)
            + _clamp(wet_months / 10.0) * 0.14
            + _clamp(precipitation / 1600.0) * 0.10
            + lowland * 0.10
        ),
        "taiga": _clamp(
            _clamp(1.0 - abs(temperature - 1.5) / 7.5) * 0.26
            + _clamp((precipitation - 280.0) / 800.0) * 0.16
            + _clamp((frost_months - 3) / 6.0) * 0.20
            + (0.24 if biome == "boreal_forest" else 0.0)
            + _clamp((abs(float(cell.get("lat_deg", 0.0))) - 40.0) / 32.0) * 0.14
        ),
        "cold_steppe": _clamp(
            _clamp(1.0 - abs(temperature - 2.0) / 10.0) * 0.20
            + _clamp((precipitation - 140.0) / 520.0) * 0.18
            + _clamp((620.0 - precipitation) / 520.0) * 0.14
            + aridity * 0.16
            + _clamp((frost_months - 2) / 7.0) * 0.14
            + (0.18 if biome in {"temperate_grassland", "cold_desert", "tundra"} else 0.0)
        ),
        "cold_desert": _clamp(
            _clamp((8.0 - temperature) / 15.0) * 0.22
            + _clamp((260.0 - precipitation) / 260.0) * 0.28
            + aridity * 0.20
            + _clamp(frost_months / 9.0) * 0.12
            + (0.18 if biome == "cold_desert" else 0.0)
        ),
    }


def _select_ecotone(scores: dict[str, float]) -> tuple[str, float]:
    if not scores:
        return "none", 0.0
    ecotone, score = sorted(scores.items(), key=lambda item: (-item[1], item[0]))[0]
    if score < ECOTONE_THRESHOLD:
        return "none", score
    return ecotone, score


def _connected_components(
    candidate_ids: set[int],
    cells_by_id: dict[int, dict[str, Any]],
    ecotone_type: str,
) -> list[list[dict[str, Any]]]:
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
                neighbor = cells_by_id[neighbor_id]
                if str(neighbor.get("biome_ecotone_type", "none")) != ecotone_type:
                    continue
                remaining.remove(neighbor_id)
                queue.append(neighbor_id)
                component_ids.append(neighbor_id)
        components.append([cells_by_id[cell_id] for cell_id in sorted(component_ids)])
    return components


def enrich_world_with_biome_ecotones(world: dict[str, Any]) -> dict[str, Any]:
    cells = world.get("cells", [])
    if not isinstance(cells, list) or not cells:
        return world

    cells_by_id = {int(cell.get("id", -1)): cell for cell in cells}
    type_counts: Counter[str] = Counter()
    candidate_ids_by_type: dict[str, set[int]] = {}
    confidence_sum = 0.0
    ecotone_cell_count = 0

    for cell in cells:
        scores = _score_ecotones(cell, cells_by_id)
        ecotone_type, confidence = _select_ecotone(scores)
        cell["biome_ecotone_type"] = ecotone_type
        cell["biome_ecotone_confidence"] = round(confidence, 6)
        cell["biome_ecotone_region_id"] = -1
        type_counts[ecotone_type] += 1
        confidence_sum += confidence
        if ecotone_type != "none":
            ecotone_cell_count += 1
            candidate_ids_by_type.setdefault(ecotone_type, set()).add(int(cell.get("id", -1)))

    regions: list[dict[str, Any]] = []
    for ecotone_type, candidate_ids in sorted(candidate_ids_by_type.items()):
        for component in _connected_components(candidate_ids, cells_by_id, ecotone_type):
            region_id = len(regions)
            for cell in component:
                cell["biome_ecotone_region_id"] = region_id
            group_count = len(component)
            area_sum = sum(max(0.0, float(cell.get("area_km2", 0.0))) for cell in component)
            confidence_region_sum = sum(float(cell.get("biome_ecotone_confidence", 0.0)) for cell in component)
            temperature_sum = sum(float(cell.get("temperature_c", 0.0)) for cell in component)
            precipitation_sum = sum(float(cell.get("precipitation_mm_y", 0.0)) for cell in component)
            biome_counter = Counter(str(cell.get("biome", "unknown")) for cell in component)
            coastal_count = sum(1 for cell in component if _is_coastal_land(cell, cells_by_id))
            regions.append(
                {
                    "id": region_id,
                    "ecotone_type": ecotone_type,
                    "cell_count": group_count,
                    "cell_ids": [int(cell.get("id", -1)) for cell in component],
                    "area_km2": round(area_sum, 6),
                    "mean_ecotone_confidence": round(confidence_region_sum / group_count, 6),
                    "dominant_biome": _primary_key(biome_counter, "unknown"),
                    "mean_temperature_c": round(temperature_sum / group_count, 6),
                    "mean_precipitation_mm_y": round(precipitation_sum / group_count, 6),
                    "coastal_cell_count": coastal_count,
                }
            )

    summary = world.setdefault("summary", {})
    summary["biome_ecotone_cell_count"] = ecotone_cell_count
    summary["biome_ecotone_region_count"] = len(regions)
    summary["mean_biome_ecotone_confidence"] = round(confidence_sum / len(cells), 6)
    summary["biome_ecotone_type_counts"] = dict(sorted(type_counts.items()))
    summary["mangrove_ecotone_cell_count"] = int(type_counts.get("mangrove", 0))
    summary["cloud_forest_ecotone_cell_count"] = int(type_counts.get("cloud_forest", 0))
    summary["alpine_paramo_ecotone_cell_count"] = int(type_counts.get("alpine_paramo", 0))
    world["biome_ecotone_regions"] = regions
    return world
