from __future__ import annotations

import math
from collections import Counter
from typing import Any


IGNITION_THRESHOLD = 0.28
SPREAD_THRESHOLD = 0.30
HIGH_FUEL_THRESHOLD = 0.35
HIGH_FIREBREAK_THRESHOLD = 0.55
MAX_EVENT_COUNT = 96
MAX_SPREAD_STEPS = 6
MAX_EVENT_CELLS = 96


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _primary_key(counter: Counter[str], fallback: str) -> str:
    if not counter:
        return fallback
    return sorted(counter.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _neighbors(cell: dict[str, Any], cells_by_id: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    return [cells_by_id[int(neighbor_id)] for neighbor_id in cell.get("neighbors", []) if int(neighbor_id) in cells_by_id]


def _wind_alignment(cell: dict[str, Any], neighbor: dict[str, Any]) -> float:
    lat_a = math.radians(float(cell.get("lat_deg", 0.0)))
    lat_b = math.radians(float(neighbor.get("lat_deg", 0.0)))
    lon_a = math.radians(float(cell.get("lon_deg", 0.0)))
    lon_b = math.radians(float(neighbor.get("lon_deg", 0.0)))
    dlon = lon_b - lon_a
    while dlon > math.pi:
        dlon -= math.tau
    while dlon < -math.pi:
        dlon += math.tau
    east = dlon * math.cos((lat_a + lat_b) * 0.5)
    north = lat_b - lat_a
    length = math.hypot(east, north)
    if length <= 0.0:
        return 0.0
    east /= length
    north /= length
    wind_east = float(cell.get("wind_east", 0.0))
    wind_north = float(cell.get("wind_north", 0.0))
    wind_speed = _clamp(math.hypot(wind_east, wind_north))
    if wind_speed <= 0.0:
        return 0.0
    dot = (wind_east * east + wind_north * north) / max(0.000001, math.hypot(wind_east, wind_north))
    return _clamp((dot + 1.0) * 0.5) * wind_speed


def _fuel_continuity(cell: dict[str, Any], neighbors: list[dict[str, Any]]) -> float:
    if bool(cell.get("is_water", False)):
        return 0.0
    biomass = _clamp(float(cell.get("vegetation_biomass_index", 0.0)))
    primary = _clamp(float(cell.get("primary_productivity_index", 0.0)))
    wildfire = _clamp(float(cell.get("wildfire_spread_risk_index", 0.0)))
    aridity = _clamp(float(cell.get("seasonal_aridity_index", 0.0)))
    wetland = _clamp(float(cell.get("wetland_extent_index", 0.0)))
    ice = _clamp(float(cell.get("ice_thickness_m", 0.0)) / 500.0)
    neighbor_fuel = (
        sum(1 for neighbor in neighbors if float(neighbor.get("vegetation_biomass_index", 0.0)) >= 0.20) / len(neighbors)
        if neighbors
        else 0.0
    )
    forest_bonus = 0.10 if "forest" in str(cell.get("biome", "")) else 0.0
    grass_bonus = 0.08 if str(cell.get("biome", "")) in {"savanna", "temperate_grassland", "mediterranean_scrub"} else 0.0
    return _clamp(
        biomass * 0.32
        + primary * 0.16
        + wildfire * 0.20
        + aridity * 0.14
        + neighbor_fuel * 0.12
        + forest_bonus
        + grass_bonus
        - wetland * 0.18
        - ice * 0.34
    )


def _firebreak(cell: dict[str, Any], neighbors: list[dict[str, Any]], fuel: float) -> float:
    if bool(cell.get("is_water", False)):
        return 1.0
    water_neighbor_fraction = sum(1 for neighbor in neighbors if bool(neighbor.get("is_water", False))) / len(neighbors) if neighbors else 0.0
    wetland = _clamp(float(cell.get("wetland_extent_index", 0.0)))
    river = 0.18 if bool(cell.get("is_river", False)) else 0.0
    floodplain = _clamp(float(cell.get("floodplain_connectivity_index", 0.0))) * 0.12
    ice = _clamp(float(cell.get("ice_thickness_m", 0.0)) / 500.0)
    sparse_fuel = _clamp(1.0 - fuel) * 0.18
    return _clamp(water_neighbor_fraction * 0.34 + wetland * 0.24 + river + floodplain + ice * 0.30 + sparse_fuel)


def _ignition_potential(cell: dict[str, Any], fuel: float, firebreak: float, wind_alignment: float) -> float:
    if bool(cell.get("is_water", False)):
        return 0.0
    wildfire = _clamp(float(cell.get("wildfire_spread_risk_index", 0.0)))
    aridity = _clamp(float(cell.get("seasonal_aridity_index", 0.0)))
    disturbance = _clamp(float(cell.get("ecosystem_disturbance_pressure_index", 0.0)))
    settlement = _clamp(float(cell.get("settlement_score", 0.0)))
    lightning_proxy = _clamp(float(cell.get("climate_energy_stress_index", 0.0))) * 0.06
    ice = _clamp(float(cell.get("ice_thickness_m", 0.0)) / 500.0)
    return _clamp(
        wildfire * 0.34
        + fuel * 0.28
        + aridity * 0.16
        + disturbance * 0.10
        + wind_alignment * 0.08
        + settlement * 0.08
        + lightning_proxy
        - firebreak * 0.18
        - ice * 0.18
    )


def _regime(cell: dict[str, Any], ignition: float, fuel: float, firebreak: float, wind_alignment: float) -> str:
    if bool(cell.get("is_water", False)):
        return "non_burnable_water"
    if str(cell.get("biome", "")) == "ice_cap" or float(cell.get("ice_thickness_m", 0.0)) > 120.0:
        return "ice_or_barren_firebreak"
    if fuel < 0.12:
        return "sparse_fuel"
    if firebreak >= HIGH_FIREBREAK_THRESHOLD:
        return "fragmented_firebreak_mosaic"
    if ignition >= 0.34 and fuel >= HIGH_FUEL_THRESHOLD and wind_alignment >= 0.35:
        return "wind_driven_crown_fire"
    if ignition >= IGNITION_THRESHOLD:
        return "seasonal_surface_fire"
    return "low_fire_activity"


def _spread_probability(source: dict[str, Any], target: dict[str, Any]) -> float:
    if bool(target.get("is_water", False)):
        return 0.0
    if str(target.get("wildfire_disturbance_regime", "")) == "ice_or_barren_firebreak":
        return 0.0
    same_biome = 0.06 if str(source.get("biome", "")) == str(target.get("biome", "")) else 0.0
    downhill_drying = 0.04 if float(target.get("elevation_m", 0.0)) <= float(source.get("elevation_m", 0.0)) else 0.0
    return _clamp(
        float(target.get("wildfire_ignition_potential_index", 0.0)) * 0.26
        + float(target.get("wildfire_fuel_continuity_index", 0.0)) * 0.28
        + _wind_alignment(source, target) * 0.20
        + float(source.get("wildfire_fuel_continuity_index", 0.0)) * 0.08
        + same_biome
        + downhill_drying
        - float(target.get("wildfire_firebreak_index", 0.0)) * 0.22
    )


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


def _mean(cells: list[dict[str, Any]], key: str) -> float:
    return sum(float(cell.get(key, 0.0)) for cell in cells) / len(cells) if cells else 0.0


def _build_history(
    event_id: int,
    ignition_cell: dict[str, Any],
    cells_by_id: dict[int, dict[str, Any]],
    assigned_cell_ids: set[int],
) -> dict[str, Any]:
    ignition_id = int(ignition_cell.get("id", -1))
    burned_ids: set[int] = {ignition_id}
    active_ids: set[int] = {ignition_id}
    step_probabilities: dict[int, float] = {ignition_id: float(ignition_cell.get("wildfire_ignition_potential_index", 0.0))}
    steps: list[dict[str, Any]] = []

    for step_index in range(MAX_SPREAD_STEPS):
        if step_index == 0:
            newly_burned = [ignition_id]
            probabilities = [step_probabilities[ignition_id]]
        else:
            candidate_probabilities: dict[int, float] = {}
            for active_id in active_ids:
                active = cells_by_id.get(active_id)
                if active is None:
                    continue
                for neighbor_id_raw in active.get("neighbors", []):
                    neighbor_id = int(neighbor_id_raw)
                    if neighbor_id in burned_ids or neighbor_id in assigned_cell_ids or neighbor_id not in cells_by_id:
                        continue
                    probability = _spread_probability(active, cells_by_id[neighbor_id])
                    if probability >= SPREAD_THRESHOLD:
                        candidate_probabilities[neighbor_id] = max(candidate_probabilities.get(neighbor_id, 0.0), probability)
            remaining_slots = max(0, MAX_EVENT_CELLS - len(burned_ids))
            selected = sorted(candidate_probabilities.items(), key=lambda item: (-item[1], item[0]))[:remaining_slots]
            newly_burned = sorted(cell_id for cell_id, _probability in selected)
            probabilities = [candidate_probabilities[cell_id] for cell_id in newly_burned]
            if not newly_burned:
                break
            for cell_id in newly_burned:
                burned_ids.add(cell_id)
                step_probabilities[cell_id] = candidate_probabilities[cell_id]
            active_ids = set(newly_burned)

        burned_cells = [cells_by_id[cell_id] for cell_id in sorted(burned_ids)]
        burned_area = sum(max(0.0, float(cell.get("area_km2", 0.0))) for cell in burned_cells)
        mean_probability = sum(probabilities) / len(probabilities) if probabilities else 0.0
        mean_firebreak = _mean([cells_by_id[cell_id] for cell_id in newly_burned], "wildfire_firebreak_index")
        steps.append(
            {
                "step_index": step_index,
                "newly_burned_cell_ids": newly_burned,
                "active_front_cell_ids": sorted(active_ids),
                "cumulative_burned_cell_count": len(burned_ids),
                "burned_area_km2": round(burned_area, 6),
                "mean_spread_probability_index": round(mean_probability, 6),
                "containment_index": round(_clamp(mean_firebreak + (1.0 - mean_probability) * 0.28), 6),
            }
        )

    cells = [cells_by_id[cell_id] for cell_id in sorted(burned_ids)]
    cell_ids = [int(cell.get("id", -1)) for cell in cells]
    area = sum(max(0.0, float(cell.get("area_km2", 0.0))) for cell in cells)
    centroid_lat, centroid_lon = _centroid(cells)
    biome_counts = Counter(str(cell.get("biome", "unknown")) for cell in cells)
    regime_counts = Counter(str(cell.get("wildfire_disturbance_regime", "unknown")) for cell in cells)
    max_probability = max(step_probabilities.values()) if step_probabilities else 0.0
    containment = _clamp(_mean(cells, "wildfire_firebreak_index") * 0.62 + (1.0 - max_probability) * 0.20)
    return {
        "id": event_id,
        "ignition_cell_id": ignition_id,
        "cell_count": len(cells),
        "cell_ids": cell_ids,
        "area_km2": round(area, 6),
        "centroid_lat_deg": centroid_lat,
        "centroid_lon_deg": centroid_lon,
        "dominant_biome": _primary_key(biome_counts, "unknown"),
        "dominant_disturbance_regime": _primary_key(regime_counts, "unknown"),
        "mean_wildfire_spread_risk_index": round(_mean(cells, "wildfire_spread_risk_index"), 6),
        "mean_ignition_potential_index": round(_mean(cells, "wildfire_ignition_potential_index"), 6),
        "mean_fuel_continuity_index": round(_mean(cells, "wildfire_fuel_continuity_index"), 6),
        "mean_wind_alignment_index": round(_mean(cells, "wildfire_wind_alignment_index"), 6),
        "mean_firebreak_index": round(_mean(cells, "wildfire_firebreak_index"), 6),
        "mean_ecosystem_disturbance_pressure_index": round(_mean(cells, "ecosystem_disturbance_pressure_index"), 6),
        "max_spread_probability_index": round(max_probability, 6),
        "containment_index": round(containment, 6),
        "spread_step_count": len(steps),
        "steps": steps,
        "disturbance_regime_counts": dict(sorted(regime_counts.items())),
    }


def enrich_world_with_wildfire_disturbance(world: dict[str, Any]) -> dict[str, Any]:
    cells = world.get("cells", [])
    if not isinstance(cells, list) or not cells:
        return world
    cells_by_id = {int(cell.get("id", -1)): cell for cell in cells if isinstance(cell, dict)}

    ignition_sum = 0.0
    fuel_sum = 0.0
    wind_sum = 0.0
    firebreak_sum = 0.0
    high_ignition_count = 0
    high_fuel_count = 0
    high_firebreak_count = 0
    regime_counts: Counter[str] = Counter()

    for cell in cells:
        neighbors = _neighbors(cell, cells_by_id)
        fuel = _fuel_continuity(cell, neighbors)
        firebreak = _firebreak(cell, neighbors, fuel)
        wind_alignment = max((_wind_alignment(cell, neighbor) for neighbor in neighbors), default=0.0)
        ignition = _ignition_potential(cell, fuel, firebreak, wind_alignment)
        regime = _regime(cell, ignition, fuel, firebreak, wind_alignment)
        cell["wildfire_ignition_potential_index"] = round(ignition, 6)
        cell["wildfire_fuel_continuity_index"] = round(fuel, 6)
        cell["wildfire_wind_alignment_index"] = round(wind_alignment, 6)
        cell["wildfire_firebreak_index"] = round(firebreak, 6)
        cell["wildfire_disturbance_regime"] = regime
        cell["wildfire_spread_history_ids"] = []
        ignition_sum += ignition
        fuel_sum += fuel
        wind_sum += wind_alignment
        firebreak_sum += firebreak
        high_ignition_count += 1 if ignition >= IGNITION_THRESHOLD else 0
        high_fuel_count += 1 if fuel >= HIGH_FUEL_THRESHOLD else 0
        high_firebreak_count += 1 if firebreak >= HIGH_FIREBREAK_THRESHOLD else 0
        regime_counts[regime] += 1

    assigned_cell_ids: set[int] = set()
    candidate_cells = sorted(
        [
            cell
            for cell in cells
            if float(cell.get("wildfire_ignition_potential_index", 0.0)) >= IGNITION_THRESHOLD
            and float(cell.get("wildfire_fuel_continuity_index", 0.0)) >= 0.18
            and str(cell.get("wildfire_disturbance_regime", "")) not in {"non_burnable_water", "ice_or_barren_firebreak"}
        ],
        key=lambda cell: (-float(cell.get("wildfire_ignition_potential_index", 0.0)), int(cell.get("id", -1))),
    )
    histories: list[dict[str, Any]] = []
    for ignition_cell in candidate_cells:
        if len(histories) >= MAX_EVENT_COUNT:
            break
        ignition_id = int(ignition_cell.get("id", -1))
        if ignition_id in assigned_cell_ids:
            continue
        history = _build_history(len(histories), ignition_cell, cells_by_id, assigned_cell_ids)
        histories.append(history)
        for cell_id in history.get("cell_ids", []):
            assigned_cell_ids.add(int(cell_id))
            cell = cells_by_id.get(int(cell_id))
            if cell is not None:
                cell["wildfire_spread_history_ids"].append(int(history["id"]))

    wildfire_cell_ids = {
        int(cell.get("id", -1))
        for cell in cells
        if isinstance(cell.get("wildfire_spread_history_ids", []), list) and cell.get("wildfire_spread_history_ids", [])
    }
    summary = world.setdefault("summary", {})
    cell_count = len(cells)
    summary["wildfire_spread_history_count"] = len(histories)
    summary["wildfire_disturbance_cell_count"] = len(wildfire_cell_ids)
    summary["wildfire_spread_step_count"] = sum(int(history.get("spread_step_count", 0)) for history in histories)
    summary["high_wildfire_ignition_potential_cell_count"] = high_ignition_count
    summary["high_wildfire_fuel_continuity_cell_count"] = high_fuel_count
    summary["high_wildfire_firebreak_cell_count"] = high_firebreak_count
    summary["wildfire_total_burned_area_km2"] = round(sum(float(history.get("area_km2", 0.0)) for history in histories), 6)
    summary["mean_wildfire_ignition_potential_index"] = round(ignition_sum / cell_count, 6)
    summary["mean_wildfire_fuel_continuity_index"] = round(fuel_sum / cell_count, 6)
    summary["mean_wildfire_wind_alignment_index"] = round(wind_sum / cell_count, 6)
    summary["mean_wildfire_firebreak_index"] = round(firebreak_sum / cell_count, 6)
    summary["wildfire_disturbance_regime_counts"] = dict(sorted(regime_counts.items()))
    world["wildfire_spread_histories"] = histories
    return world
