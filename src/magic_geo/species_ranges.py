from __future__ import annotations

import math
from collections import Counter, deque
from typing import Any


FOREST_BIOMES = {"tropical_rainforest", "tropical_seasonal_forest", "temperate_forest", "boreal_forest"}
GRASSLAND_BIOMES = {"savanna", "temperate_grassland", "mediterranean_scrub"}
DESERT_BIOMES = {"hot_desert", "cold_desert"}
ALPINE_BIOMES = {"tundra", "alpine", "ice_cap"}
FRESHWATER_TYPES = {"fresh_lake", "inland_sea"}
MARINE_TYPES = {"ocean", "continental_shelf"}
SPECIES_RANGE_THRESHOLD = 0.46

GUILD_METADATA = {
    "canopy_tree": ("terrestrial", "primary_producer"),
    "grassland_grazer": ("terrestrial", "herbivore"),
    "desert_specialist": ("arid", "specialist_consumer"),
    "alpine_tundra_specialist": ("alpine", "specialist_consumer"),
    "wetland_amphibian": ("wetland", "secondary_consumer"),
    "large_predator": ("terrestrial", "apex_predator"),
    "freshwater_fish": ("freshwater", "aquatic_consumer"),
    "marine_fish": ("marine", "aquatic_consumer"),
    "reef_builder": ("reef", "foundation_species"),
    "mangrove_coastal_bird": ("wetland", "mobile_consumer"),
}


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _primary_key(counter: Counter[str], fallback: str) -> str:
    if not counter:
        return fallback
    return sorted(counter.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _temperature_window(temperature_c: float, center: float, half_width: float) -> float:
    return _clamp(1.0 - abs(temperature_c - center) / max(1.0, half_width))


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
            for neighbor_id_raw in current.get("neighbors", []):
                neighbor_id = int(neighbor_id_raw)
                if neighbor_id not in remaining:
                    continue
                remaining.remove(neighbor_id)
                queue.append(neighbor_id)
                component_ids.append(neighbor_id)
        components.append([cells_by_id[cell_id] for cell_id in sorted(component_ids)])
    return components


def _centroid(component: list[dict[str, Any]]) -> tuple[float, float]:
    if not component:
        return 0.0, 0.0
    weight_sum = 0.0
    x_sum = 0.0
    y_sum = 0.0
    z_sum = 0.0
    for cell in component:
        weight = max(0.0, float(cell.get("area_km2", 0.0))) or 1.0
        lat = math.radians(float(cell.get("lat_deg", 0.0)))
        lon = math.radians(float(cell.get("lon_deg", 0.0)))
        cos_lat = math.cos(lat)
        x_sum += math.cos(lon) * cos_lat * weight
        y_sum += math.sin(lon) * cos_lat * weight
        z_sum += math.sin(lat) * weight
        weight_sum += weight
    if weight_sum <= 0.0:
        return 0.0, 0.0
    lon = math.degrees(math.atan2(y_sum / weight_sum, x_sum / weight_sum))
    hyp = math.hypot(x_sum / weight_sum, y_sum / weight_sum)
    lat = math.degrees(math.atan2(z_sum / weight_sum, hyp))
    return round(lat, 6), round(lon, 6)


def _range_fragmentation(component: list[dict[str, Any]]) -> float:
    member_ids = {int(cell.get("id", -1)) for cell in component}
    total_edges = 0
    external_edges = 0
    for cell in component:
        for neighbor_id_raw in cell.get("neighbors", []):
            total_edges += 1
            if int(neighbor_id_raw) not in member_ids:
                external_edges += 1
    edge_fraction = external_edges / total_edges if total_edges else 1.0
    small_range_pressure = 1.0 / max(1.0, float(len(component)))
    return _clamp(edge_fraction * 0.72 + small_range_pressure * 0.28)


def _guild_scores(cell: dict[str, Any]) -> dict[str, float]:
    biome = str(cell.get("biome", "unknown"))
    ecotone = str(cell.get("biome_ecotone_type", "none"))
    water_body = str(cell.get("water_body_type", "land"))
    is_water = bool(cell.get("is_water", False))
    temperature = float(cell.get("temperature_c", 0.0))
    precipitation = max(0.0, float(cell.get("precipitation_mm_y", 0.0)))
    aridity = _clamp(float(cell.get("seasonal_aridity_index", 0.0)))
    moisture = _clamp(float(cell.get("soil_moisture_index", 0.0)))
    primary = _clamp(float(cell.get("primary_productivity_index", 0.0)))
    biomass = _clamp(float(cell.get("vegetation_biomass_index", 0.0)))
    richness = _clamp(float(cell.get("species_richness_index", 0.0)))
    disturbance = _clamp(float(cell.get("ecosystem_disturbance_pressure_index", 0.0)))
    forest_growth = _clamp(float(cell.get("forest_growth_index", 0.0)))
    fishery = _clamp(float(cell.get("fishery_productivity_index", 0.0)))
    wetland = _clamp(float(cell.get("wetland_extent_index", 0.0)))
    reef = _clamp(float(cell.get("reef_growth_index", 0.0)))
    river_channel = _clamp(float(cell.get("river_channel_width_m", 0.0)) / 180.0)
    river_depth = _clamp(float(cell.get("river_channel_depth_m", 0.0)) / 9.0)
    elevation = float(cell.get("elevation_m", 0.0))
    ice = _clamp(float(cell.get("ice_thickness_m", 0.0)) / 800.0)
    permafrost = _clamp(float(cell.get("permafrost_extent_index", 0.0)))
    coastal = _clamp(1.0 - float(cell.get("distance_to_marine_water_km", 9999.0)) / 80.0)
    temp_temperate = _temperature_window(temperature, 18.0, 24.0)
    temp_warm = _temperature_window(temperature, 25.0, 14.0)
    temp_cold = _clamp((8.0 - temperature) / 22.0)

    forest_bonus = 0.24 if biome in FOREST_BIOMES or "forest" in biome else 0.0
    grass_bonus = 0.24 if biome in GRASSLAND_BIOMES else 0.0
    desert_bonus = 0.30 if biome in DESERT_BIOMES else 0.0
    alpine_bonus = 0.28 if biome in ALPINE_BIOMES else 0.0
    freshwater_bonus = 0.30 if water_body in FRESHWATER_TYPES else (0.22 if bool(cell.get("is_river", False)) else 0.0)
    marine_bonus = 0.30 if water_body in MARINE_TYPES else 0.0
    reef_bonus = 0.34 if str(cell.get("reef_type", "none")) != "none" else 0.0
    mangrove_bonus = 0.34 if ecotone == "mangrove" or str(cell.get("wetland_system_type", "")) == "mangrove" else 0.0

    non_water_gate = 0.0 if is_water else 1.0
    scores = {
        "canopy_tree": non_water_gate
        * _clamp(
            forest_bonus
            + primary * 0.24
            + biomass * 0.28
            + forest_growth * 0.20
            + moisture * 0.12
            + temp_temperate * 0.10
            - disturbance * 0.14
            - aridity * 0.08
            - ice * 0.26
        ),
        "grassland_grazer": non_water_gate
        * _clamp(
            grass_bonus
            + primary * 0.24
            + richness * 0.16
            + _clamp(1.0 - abs(aridity - 0.45) / 0.45) * 0.18
            + temp_temperate * 0.12
            + _clamp(1.0 - biomass) * 0.08
            - disturbance * 0.10
            - ice * 0.22
        ),
        "desert_specialist": non_water_gate
        * _clamp(
            desert_bonus
            + aridity * 0.28
            + _clamp(1.0 - moisture) * 0.16
            + _clamp(1.0 - precipitation / 420.0) * 0.14
            + richness * 0.10
            - ice * 0.22
            - wetland * 0.24
        ),
        "alpine_tundra_specialist": non_water_gate
        * _clamp(
            alpine_bonus
            + temp_cold * 0.22
            + _clamp((elevation - 1200.0) / 2600.0) * 0.18
            + permafrost * 0.18
            + richness * 0.12
            - ice * 0.18
        ),
        "wetland_amphibian": _clamp(
            wetland * 0.34
            + _clamp(float(cell.get("wetland_hydrology_index", 0.0))) * 0.18
            + moisture * 0.12
            + richness * 0.14
            + temp_warm * 0.10
            + freshwater_bonus * 0.18
            - aridity * 0.10
        ),
        "large_predator": non_water_gate
        * _clamp(
            richness * 0.28
            + biomass * 0.24
            + primary * 0.18
            + _clamp(1.0 - disturbance) * 0.18
            + forest_bonus * 0.10
            + grass_bonus * 0.10
            - ice * 0.26
        ),
        "freshwater_fish": _clamp(
            freshwater_bonus
            + fishery * 0.30
            + primary * 0.12
            + river_channel * 0.14
            + river_depth * 0.12
            + _temperature_window(temperature, 14.0, 24.0) * 0.10
            - ice * 0.22
        ),
        "marine_fish": _clamp(
            marine_bonus
            + fishery * 0.42
            + primary * 0.14
            + _temperature_window(temperature, 13.0, 24.0) * 0.10
            + (0.08 if water_body == "continental_shelf" else 0.0)
            - ice * 0.18
        ),
        "reef_builder": _clamp(reef_bonus + reef * 0.54 + fishery * 0.10 + temp_warm * 0.08 - ice * 0.22),
        "mangrove_coastal_bird": _clamp(
            mangrove_bonus
            + wetland * 0.22
            + coastal * 0.14
            + richness * 0.12
            + temp_warm * 0.12
            + _clamp(precipitation / 1600.0) * 0.10
            - disturbance * 0.08
        ),
    }
    return {guild: round(score, 6) for guild, score in scores.items()}


def _cell_endemism(cell: dict[str, Any], cells_by_id: dict[int, dict[str, Any]]) -> float:
    biome = str(cell.get("biome", "unknown"))
    neighbors = [
        cells_by_id[int(neighbor_id)]
        for neighbor_id in cell.get("neighbors", [])
        if int(neighbor_id) in cells_by_id
    ]
    same_biome_fraction = (
        sum(1 for neighbor in neighbors if str(neighbor.get("biome", "unknown")) == biome) / len(neighbors)
        if neighbors
        else 0.0
    )
    island_class = str(cell.get("island_class", "mainland"))
    island_score = {
        "islet": 0.42,
        "island": 0.34,
        "large_island": 0.24,
        "continental_island": 0.16,
    }.get(island_class, 0.0)
    ecotone = 0.22 if str(cell.get("biome_ecotone_type", "none")) != "none" else 0.0
    reef = _clamp(float(cell.get("reef_growth_index", 0.0))) * 0.16
    wetland = _clamp(float(cell.get("wetland_extent_index", 0.0))) * 0.12
    elevation = _clamp((float(cell.get("elevation_m", 0.0)) - 1500.0) / 3000.0) * 0.14
    isolation = _clamp(1.0 - same_biome_fraction) * 0.24
    disturbance_penalty = _clamp(float(cell.get("ecosystem_disturbance_pressure_index", 0.0))) * 0.10
    return _clamp(island_score + ecotone + reef + wetland + elevation + isolation - disturbance_penalty)


def _cell_confidence(cell: dict[str, Any]) -> float:
    biome_confidence = _clamp(float(cell.get("biome_confidence_index", 0.0)))
    richness = _clamp(float(cell.get("species_richness_index", 0.0)))
    productivity = _clamp(float(cell.get("primary_productivity_index", 0.0)))
    wetland_or_reef = max(_clamp(float(cell.get("wetland_extent_index", 0.0))), _clamp(float(cell.get("reef_growth_index", 0.0))))
    disturbance = _clamp(float(cell.get("ecosystem_disturbance_pressure_index", 0.0)))
    return _clamp(biome_confidence * 0.30 + richness * 0.22 + productivity * 0.20 + wetland_or_reef * 0.12 + (1.0 - disturbance) * 0.16)


def _mean(component: list[dict[str, Any]], key: str) -> float:
    if not component:
        return 0.0
    return sum(float(cell.get(key, 0.0)) for cell in component) / len(component)


def _linked_ids(component: list[dict[str, Any]], key: str) -> list[int]:
    return sorted({int(cell.get(key, -1)) for cell in component if int(cell.get(key, -1)) >= 0})


def _habitat_evidence(component: list[dict[str, Any]]) -> dict[str, float]:
    cell_count = len(component) or 1
    return {
        "mean_wetland_extent_index": round(_mean(component, "wetland_extent_index"), 6),
        "mean_reef_growth_index": round(_mean(component, "reef_growth_index"), 6),
        "mean_fishery_productivity_index": round(_mean(component, "fishery_productivity_index"), 6),
        "mean_forest_growth_index": round(_mean(component, "forest_growth_index"), 6),
        "river_cell_fraction": round(sum(1 for cell in component if bool(cell.get("is_river", False))) / cell_count, 6),
        "water_cell_fraction": round(sum(1 for cell in component if bool(cell.get("is_water", False))) / cell_count, 6),
        "coastal_cell_fraction": round(
            sum(1 for cell in component if float(cell.get("distance_to_marine_water_km", 9999.0)) <= 80.0) / cell_count,
            6,
        ),
    }


def enrich_world_with_species_ranges(world: dict[str, Any]) -> dict[str, Any]:
    cells = world.get("cells", [])
    if not isinstance(cells, list) or not cells:
        return world

    cells_by_id = {int(cell.get("id", -1)): cell for cell in cells if isinstance(cell, dict)}
    candidate_ids_by_guild: dict[str, set[int]] = {guild: set() for guild in GUILD_METADATA}
    scores_by_cell: dict[int, dict[str, float]] = {}
    dominant_counts: Counter[str] = Counter()
    suitability_sum = 0.0
    endemism_sum = 0.0
    confidence_sum = 0.0

    for cell in cells:
        cell_id = int(cell.get("id", -1))
        scores = _guild_scores(cell)
        scores_by_cell[cell_id] = scores
        dominant_guild, dominant_score = sorted(scores.items(), key=lambda item: (-item[1], item[0]))[0]
        if dominant_score < 0.25:
            dominant_guild = "none"
        endemism = _cell_endemism(cell, cells_by_id)
        confidence = _cell_confidence(cell)
        guild_richness = sum(1 for score in scores.values() if score >= SPECIES_RANGE_THRESHOLD)

        cell["dominant_species_guild"] = dominant_guild
        cell["species_habitat_suitability_index"] = round(dominant_score, 6)
        cell["species_endemism_index"] = round(endemism, 6)
        cell["species_range_fragmentation_index"] = 0.0
        cell["species_composition_confidence_index"] = round(confidence, 6)
        cell["species_guild_richness_count"] = guild_richness
        cell["species_range_record_ids"] = []

        dominant_counts[dominant_guild] += 1
        suitability_sum += dominant_score
        endemism_sum += endemism
        confidence_sum += confidence

        for guild, score in scores.items():
            if score >= SPECIES_RANGE_THRESHOLD and cell_id >= 0:
                candidate_ids_by_guild[guild].add(cell_id)

    records: list[dict[str, Any]] = []
    guild_counts: Counter[str] = Counter()
    habitat_counts: Counter[str] = Counter()
    high_endemism_count = 0
    high_stress_count = 0

    for guild in sorted(GUILD_METADATA):
        habitat_class, trophic_role = GUILD_METADATA[guild]
        for component in _connected_components(candidate_ids_by_guild[guild], cells_by_id):
            record_id = len(records)
            cell_ids = [int(cell.get("id", -1)) for cell in component]
            for cell in component:
                cell["species_range_record_ids"].append(record_id)
            area = sum(max(0.0, float(cell.get("area_km2", 0.0))) for cell in component)
            fragmentation = _range_fragmentation(component)
            mean_endemism = _mean(component, "species_endemism_index")
            mean_confidence = _mean(component, "species_composition_confidence_index")
            mean_disturbance = _mean(component, "ecosystem_disturbance_pressure_index")
            small_range_bonus = _clamp((800000.0 - area) / 800000.0) * 0.18
            record_endemism = _clamp(mean_endemism * 0.72 + fragmentation * 0.18 + small_range_bonus)
            stress = _clamp(mean_disturbance * 0.38 + fragmentation * 0.22 + (1.0 - mean_confidence) * 0.22 + record_endemism * 0.18)
            temperatures = [float(cell.get("temperature_c", 0.0)) for cell in component]
            precipitations = [max(0.0, float(cell.get("precipitation_mm_y", 0.0))) for cell in component]
            centroid_lat, centroid_lon = _centroid(component)
            biome_counts = Counter(str(cell.get("biome", "unknown")) for cell in component)
            ecotone_counts = Counter(str(cell.get("biome_ecotone_type", "none")) for cell in component)
            water_body_counts = Counter(str(cell.get("water_body_type", "land")) for cell in component)

            record = {
                "id": record_id,
                "guild_type": guild,
                "habitat_class": habitat_class,
                "trophic_role": trophic_role,
                "cell_count": len(component),
                "cell_ids": cell_ids,
                "area_km2": round(area, 6),
                "centroid_lat_deg": centroid_lat,
                "centroid_lon_deg": centroid_lon,
                "dominant_biome": _primary_key(biome_counts, "unknown"),
                "dominant_ecotone_type": _primary_key(ecotone_counts, "none"),
                "dominant_water_body_type": _primary_key(water_body_counts, "land"),
                "mean_habitat_suitability_index": round(
                    sum(scores_by_cell[int(cell.get("id", -1))][guild] for cell in component) / len(component),
                    6,
                ),
                "max_habitat_suitability_index": round(
                    max(scores_by_cell[int(cell.get("id", -1))][guild] for cell in component),
                    6,
                ),
                "mean_species_richness_index": round(_mean(component, "species_richness_index"), 6),
                "mean_primary_productivity_index": round(_mean(component, "primary_productivity_index"), 6),
                "mean_disturbance_pressure_index": round(mean_disturbance, 6),
                "mean_composition_confidence_index": round(mean_confidence, 6),
                "mean_temperature_c": round(sum(temperatures) / len(temperatures), 6),
                "mean_precipitation_mm_y": round(sum(precipitations) / len(precipitations), 6),
                "range_fragmentation_index": round(fragmentation, 6),
                "endemism_index": round(record_endemism, 6),
                "conservation_stress_index": round(stress, 6),
                "climate_envelope": {
                    "min_temperature_c": round(min(temperatures), 6),
                    "mean_temperature_c": round(sum(temperatures) / len(temperatures), 6),
                    "max_temperature_c": round(max(temperatures), 6),
                    "min_precipitation_mm_y": round(min(precipitations), 6),
                    "mean_precipitation_mm_y": round(sum(precipitations) / len(precipitations), 6),
                    "max_precipitation_mm_y": round(max(precipitations), 6),
                },
                "habitat_evidence": _habitat_evidence(component),
                "wetland_system_ids": _linked_ids(component, "wetland_system_id"),
                "reef_system_ids": _linked_ids(component, "reef_system_id"),
                "aquifer_system_ids": _linked_ids(component, "aquifer_system_id"),
                "river_basin_ids": _linked_ids(component, "basin_id"),
            }
            records.append(record)
            guild_counts[guild] += 1
            habitat_counts[habitat_class] += 1
            high_endemism_count += 1 if record_endemism >= 0.60 else 0
            high_stress_count += 1 if stress >= 0.60 else 0

    for record in records:
        fragmentation = float(record.get("range_fragmentation_index", 0.0))
        for cell_id in record.get("cell_ids", []):
            cell = cells_by_id.get(int(cell_id))
            if cell is None:
                continue
            cell["species_range_fragmentation_index"] = round(
                max(float(cell.get("species_range_fragmentation_index", 0.0)), fragmentation),
                6,
            )

    range_cell_ids = {
        int(cell.get("id", -1))
        for cell in cells
        if isinstance(cell.get("species_range_record_ids", []), list) and cell.get("species_range_record_ids", [])
    }
    summary = world.setdefault("summary", {})
    cell_count = len(cells)
    summary["species_range_record_count"] = len(records)
    summary["species_range_cell_count"] = len(range_cell_ids)
    summary["terrestrial_species_range_count"] = sum(
        1 for record in records if str(record.get("habitat_class", "")) in {"terrestrial", "arid", "alpine"}
    )
    summary["aquatic_species_range_count"] = sum(
        1 for record in records if str(record.get("habitat_class", "")) in {"freshwater", "marine", "reef"}
    )
    summary["wetland_species_range_count"] = habitat_counts.get("wetland", 0)
    summary["high_endemism_species_range_count"] = high_endemism_count
    summary["high_conservation_stress_species_range_count"] = high_stress_count
    summary["species_range_total_area_km2"] = round(sum(float(record.get("area_km2", 0.0)) for record in records), 6)
    summary["mean_species_habitat_suitability_index"] = round(suitability_sum / cell_count, 6)
    summary["mean_species_endemism_index"] = round(endemism_sum / cell_count, 6)
    summary["mean_species_composition_confidence_index"] = round(confidence_sum / cell_count, 6)
    summary["species_guild_type_counts"] = dict(sorted(guild_counts.items()))
    summary["species_habitat_class_counts"] = dict(sorted(habitat_counts.items()))
    summary["dominant_species_guild_counts"] = dict(sorted(dominant_counts.items()))
    world["species_range_records"] = records
    return world
