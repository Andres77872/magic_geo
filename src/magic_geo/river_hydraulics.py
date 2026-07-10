from __future__ import annotations

from collections import Counter
from typing import Any

from .planet_parameters import surface_gravity_m_s2

WATER_DENSITY_KG_M3 = 1000.0
HYDRAULIC_NAVIGABILITY_THRESHOLD = 0.55
HIGH_SHEAR_STRESS_PA = 120.0
RIVER_CHANNEL_MORPHOLOGY_MODEL = (
    "causal_flow_sediment_wetland_baseflow_channel_morphology_v1"
)
RIVER_HYDRAULICS_MODEL = "manning_blended_diagnostic_river_hydraulics_v1"

ROUGHNESS_BY_CLASS = {
    "small_headwater": 0.045,
    "incised_bedrock_channel": 0.038,
    "braided_sediment_rich_channel": 0.048,
    "deep_alluvial_channel": 0.032,
    "navigable_lowland_channel": 0.030,
    "ephemeral_wadi": 0.052,
    "glacial_outwash_channel": 0.046,
}


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _cell_id(cell: dict[str, Any]) -> int:
    return int(cell.get("id", -1))


def _is_channel(cell: dict[str, Any]) -> bool:
    return bool(cell.get("is_river", False)) and not bool(cell.get("is_water", False))


def _manning_roughness(cell: dict[str, Any]) -> float:
    channel_class = str(cell.get("channel_morphology_class", "small_headwater"))
    base = ROUGHNESS_BY_CLASS.get(channel_class, 0.044)
    sediment = _clamp(float(cell.get("sediment_routing_load_m", 0.0)) / 2.0)
    wetland = _clamp(float(cell.get("wetland_extent_index", 0.0)))
    ice = _clamp(float(cell.get("ice_thickness_m", 0.0)) / 300.0)
    return max(0.022, min(0.080, base + sediment * 0.006 + wetland * 0.004 + ice * 0.010))


def _flow_regime(froude: float, velocity: float, shear_stress: float) -> str:
    if froude >= 1.0:
        return "supercritical"
    if froude >= 0.80:
        return "transitional"
    if velocity >= 2.6 or shear_stress >= HIGH_SHEAR_STRESS_PA:
        return "swift_subcritical"
    return "subcritical"


def _hydraulic_navigability(width: float, depth: float, velocity: float, froude: float, slope_index: float, ice: float) -> float:
    depth_score = _clamp((depth - 1.0) / 3.0)
    width_score = _clamp((width - 25.0) / 90.0)
    velocity_score = _clamp(1.0 - abs(velocity - 1.25) / 2.5)
    regime_score = _clamp(1.0 - max(0.0, froude - 0.45) / 0.75)
    slope_score = _clamp(1.0 - slope_index / 0.65)
    return _clamp(
        depth_score * 0.30
        + width_score * 0.22
        + velocity_score * 0.20
        + regime_score * 0.14
        + slope_score * 0.10
        - ice * 0.18
    )


def _reach_record(system: dict[str, Any], cells: list[dict[str, Any]]) -> dict[str, Any]:
    reach_id = int(system.get("id", -1))
    group_count = len(cells)
    divisor = group_count if group_count else 1
    regime_counts = Counter(str(cell.get("hydraulic_flow_regime", "non_channel")) for cell in cells)
    return {
        "id": reach_id,
        "river_channel_system_id": reach_id,
        "cell_count": group_count,
        "cell_ids": [int(cell.get("id", -1)) for cell in cells],
        "basin_ids": [int(value) for value in system.get("basin_ids", [])],
        "source_cell_id": int(system.get("source_cell_id", -1)),
        "outlet_cell_id": int(system.get("outlet_cell_id", -1)),
        "length_km": round(float(system.get("length_km", 0.0)), 6),
        "area_km2": round(float(system.get("area_km2", 0.0)), 6),
        "dominant_hydraulic_flow_regime": sorted(regime_counts.items(), key=lambda item: (-item[1], item[0]))[0][0]
        if regime_counts
        else "non_channel",
        "mean_hydraulic_radius_m": round(sum(float(cell.get("hydraulic_radius_m", 0.0)) for cell in cells) / divisor, 6),
        "mean_flow_velocity_m_s": round(sum(float(cell.get("flow_velocity_m_s", 0.0)) for cell in cells) / divisor, 6),
        "mean_froude_number": round(sum(float(cell.get("froude_number", 0.0)) for cell in cells) / divisor, 6),
        "mean_bed_shear_stress_pa": round(sum(float(cell.get("bed_shear_stress_pa", 0.0)) for cell in cells) / divisor, 6),
        "mean_manning_roughness_n": round(sum(float(cell.get("manning_roughness_n", 0.0)) for cell in cells) / divisor, 6),
        "mean_channel_capacity_index": round(sum(float(cell.get("channel_capacity_index", 0.0)) for cell in cells) / divisor, 6),
        "mean_hydraulic_navigability_index": round(
            sum(float(cell.get("hydraulic_navigability_index", 0.0)) for cell in cells) / divisor,
            6,
        ),
        "hydraulically_navigable_cell_count": sum(
            1 for cell in cells if float(cell.get("hydraulic_navigability_index", 0.0)) >= HYDRAULIC_NAVIGABILITY_THRESHOLD
        ),
        "supercritical_flow_cell_count": sum(1 for cell in cells if str(cell.get("hydraulic_flow_regime", "")) == "supercritical"),
        "high_shear_stress_cell_count": sum(1 for cell in cells if float(cell.get("bed_shear_stress_pa", 0.0)) >= HIGH_SHEAR_STRESS_PA),
        "hydraulic_flow_regime_counts": dict(sorted(regime_counts.items())),
    }


def enrich_world_with_river_hydraulics(world: dict[str, Any]) -> dict[str, Any]:
    cells = world.get("cells", [])
    if not isinstance(cells, list) or not cells:
        return world

    gravity_m_s2 = surface_gravity_m_s2(world)
    channel_cells: list[dict[str, Any]] = []
    velocity_sum = 0.0
    froude_sum = 0.0
    shear_sum = 0.0
    roughness_sum = 0.0
    radius_sum = 0.0
    capacity_sum = 0.0
    hydraulic_nav_sum = 0.0
    hydraulically_navigable_count = 0
    supercritical_count = 0
    high_shear_count = 0
    regime_counts: Counter[str] = Counter()

    for cell in cells:
        cell["hydraulic_radius_m"] = 0.0
        cell["flow_velocity_m_s"] = 0.0
        cell["froude_number"] = 0.0
        cell["bed_shear_stress_pa"] = 0.0
        cell["manning_roughness_n"] = 0.0
        cell["channel_capacity_index"] = 0.0
        cell["hydraulic_navigability_index"] = 0.0
        cell["hydraulic_flow_regime"] = "non_channel"
        cell["river_hydraulic_reach_id"] = -1
        if not _is_channel(cell):
            regime_counts["non_channel"] += 1
            continue

        width = max(0.0, float(cell.get("river_channel_width_m", 0.0)))
        depth = max(0.0, float(cell.get("river_channel_depth_m", 0.0)))
        discharge = max(0.0, float(cell.get("bankfull_discharge_m3_s", 0.0)))
        slope_index = _clamp(float(cell.get("channel_slope_index", 0.0)))
        slope = max(0.00001, slope_index * 0.028)
        area_m2 = max(0.001, width * depth)
        wetted_perimeter_m = max(0.001, width + 2.0 * depth)
        hydraulic_radius = area_m2 / wetted_perimeter_m
        roughness = _manning_roughness(cell)
        discharge_velocity = discharge / area_m2
        manning_velocity = (hydraulic_radius ** (2.0 / 3.0)) * (slope ** 0.5) / roughness
        velocity = max(0.0, min(12.0, discharge_velocity * 0.55 + manning_velocity * 0.45))
        froude = velocity / max(0.001, (gravity_m_s2 * max(0.001, depth)) ** 0.5)
        shear = WATER_DENSITY_KG_M3 * gravity_m_s2 * hydraulic_radius * slope
        capacity = _clamp((area_m2 / 450.0) * 0.38 + (discharge / 2400.0) * 0.34 + hydraulic_radius / 4.5 * 0.16 + velocity / 4.0 * 0.12)
        ice = _clamp(float(cell.get("ice_thickness_m", 0.0)) / 300.0)
        hydraulic_nav = _hydraulic_navigability(width, depth, velocity, froude, slope_index, ice)
        flow_regime = _flow_regime(froude, velocity, shear)

        cell["hydraulic_radius_m"] = round(hydraulic_radius, 6)
        cell["flow_velocity_m_s"] = round(velocity, 6)
        cell["froude_number"] = round(froude, 6)
        cell["bed_shear_stress_pa"] = round(shear, 6)
        cell["manning_roughness_n"] = round(roughness, 6)
        cell["channel_capacity_index"] = round(capacity, 6)
        cell["hydraulic_navigability_index"] = round(hydraulic_nav, 6)
        cell["hydraulic_flow_regime"] = flow_regime
        cell["river_hydraulic_reach_id"] = int(cell.get("river_channel_system_id", -1))

        channel_cells.append(cell)
        velocity_sum += velocity
        froude_sum += froude
        shear_sum += shear
        roughness_sum += roughness
        radius_sum += hydraulic_radius
        capacity_sum += capacity
        hydraulic_nav_sum += hydraulic_nav
        hydraulically_navigable_count += 1 if hydraulic_nav >= HYDRAULIC_NAVIGABILITY_THRESHOLD else 0
        supercritical_count += 1 if flow_regime == "supercritical" else 0
        high_shear_count += 1 if shear >= HIGH_SHEAR_STRESS_PA else 0
        regime_counts[flow_regime] += 1

    cells_by_id = {_cell_id(cell): cell for cell in cells if isinstance(cell, dict)}
    reaches: list[dict[str, Any]] = []
    for system in world.get("river_channel_systems", []):
        if not isinstance(system, dict):
            continue
        reach_cells = [cells_by_id[int(cell_id)] for cell_id in system.get("cell_ids", []) if int(cell_id) in cells_by_id]
        reach_cells = [cell for cell in reach_cells if _is_channel(cell)]
        if not reach_cells:
            continue
        reaches.append(_reach_record(system, reach_cells))

    summary = world.setdefault("summary", {})
    channel_count = len(channel_cells)
    divisor = channel_count if channel_count else 1
    world["river_hydraulics_model"] = {
        "model_type": RIVER_HYDRAULICS_MODEL,
        "source_channel_model": RIVER_CHANNEL_MORPHOLOGY_MODEL,
        "domain": "is_river_and_not_is_water_cells",
        "cross_section_model": "rectangular_area_and_wetted_perimeter_v1",
        "slope_model": "channel_slope_index_times_0_028_with_1e_5_floor_v1",
        "roughness_model": "morphology_sediment_wetland_ice_bounded_manning_n_v1",
        "velocity_model": "55_percent_discharge_plus_45_percent_manning_bounded_v1",
        "froude_model": "velocity_over_sqrt_gravity_times_depth_v1",
        "shear_model": "density_gravity_hydraulic_radius_slope_v1",
        "capacity_model": "cross_section_discharge_radius_velocity_index_v1",
        "navigability_model": "depth_width_velocity_froude_slope_ice_index_v1",
        "regime_model": "froude_velocity_shear_threshold_tree_v1",
        "reach_model": "one_reach_per_river_channel_system_v1",
        "gravity_m_s2": gravity_m_s2,
        "water_density_kg_m3": WATER_DENSITY_KG_M3,
        "maximum_velocity_m_s": 12.0,
        "hydraulic_navigability_threshold": HYDRAULIC_NAVIGABILITY_THRESHOLD,
        "high_shear_stress_pa": HIGH_SHEAR_STRESS_PA,
        "deterministic": True,
        "candidate_cell_count": channel_count,
        "reach_count": len(reaches),
        "model_limitation": "steady_diagnostic_rectangular_hydraulics_without_solved_continuity_backwater_flood_frequency_or_transient_flow",
    }
    summary["river_hydraulics_model"] = RIVER_HYDRAULICS_MODEL
    summary["river_hydraulic_cell_count"] = channel_count
    summary["river_hydraulic_reach_count"] = len(reaches)
    summary["mean_hydraulic_radius_m"] = round(radius_sum / divisor, 6) if channel_count else 0.0
    summary["mean_flow_velocity_m_s"] = round(velocity_sum / divisor, 6) if channel_count else 0.0
    summary["mean_froude_number"] = round(froude_sum / divisor, 6) if channel_count else 0.0
    summary["mean_bed_shear_stress_pa"] = round(shear_sum / divisor, 6) if channel_count else 0.0
    summary["mean_manning_roughness_n"] = round(roughness_sum / divisor, 6) if channel_count else 0.0
    summary["mean_channel_capacity_index"] = round(capacity_sum / divisor, 6) if channel_count else 0.0
    summary["mean_hydraulic_navigability_index"] = round(hydraulic_nav_sum / divisor, 6) if channel_count else 0.0
    summary["hydraulically_navigable_cell_count"] = hydraulically_navigable_count
    summary["supercritical_flow_cell_count"] = supercritical_count
    summary["high_shear_stress_cell_count"] = high_shear_count
    summary["hydraulic_flow_regime_counts"] = dict(sorted(regime_counts.items()))
    world["river_hydraulic_reaches"] = reaches
    return world
