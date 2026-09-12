"""Independent channel/hydraulic equations retained from CLI replay. No producer imports."""
from __future__ import annotations
import math
from collections import Counter
from typing import Any
from .natural_channel_validation import _output_same
from .planet_parameters import planet_radius_km as configured_planet_radius_km, surface_gravity_m_s2
RIVER_CHANNEL_MORPHOLOGY_MODEL = 'causal_flow_sediment_wetland_baseflow_channel_morphology_v1'
RIVER_CHANNEL_LOWLAND_FORMS = {'floodplain', 'river_valley', 'delta', 'coastal_plain', 'lacustrine_basin'}
RIVER_CHANNEL_CLASSES = {'small_headwater', 'ephemeral_wadi', 'braided_sediment_rich_channel', 'glacial_outwash_channel', 'incised_bedrock_channel', 'navigable_lowland_channel', 'deep_alluvial_channel', 'non_channel'}
RIVER_HYDRAULICS_MODEL = 'manning_blended_diagnostic_river_hydraulics_v1'
RIVER_HYDRAULICS_WATER_DENSITY_KG_M3 = 1000.0
RIVER_HYDRAULICS_NAVIGABILITY_THRESHOLD = 0.55
RIVER_HYDRAULICS_HIGH_SHEAR_STRESS_PA = 120.0
RIVER_HYDRAULICS_ROUGHNESS_BY_CLASS = {'small_headwater': 0.045, 'incised_bedrock_channel': 0.038, 'braided_sediment_rich_channel': 0.048, 'deep_alluvial_channel': 0.032, 'navigable_lowland_channel': 0.03, 'ephemeral_wadi': 0.052, 'glacial_outwash_channel': 0.046}

def _validate_river_channel_morphology(
    payload: dict[str, Any],
    summary: dict[str, Any],
    cells_by_id: dict[int, dict[str, Any]],
    *, strict: bool = False,
) -> list[str]:
    """Replay causal channel geometry, classes, and connected systems."""

    failure = ["river channel morphology model or causal replay invalid"]
    model = payload.get("river_channel_morphology_model", {})
    systems = payload.get("river_channel_systems", [])
    configured_radius_km = configured_planet_radius_km(payload)
    try:
        metadata_invalid = (
            not isinstance(model, dict)
            or not isinstance(systems, list)
            or model.get("model_type") != RIVER_CHANNEL_MORPHOLOGY_MODEL
            or model.get("domain") != "is_river_and_not_is_water_cells"
            or model.get("flow_normalization_model")
            != "global_max_flow_accumulation_v1"
            or float(model.get("runoff_normalization_mm_y", -1.0)) != 2200.0
            or model.get("slope_model")
            != "downstream_conditioned_surface_drop_over_great_circle_distance_v1"
            or float(model.get("slope_normalization", -1.0)) != 0.028
            or abs(float(model.get("planet_radius_km", -1.0)) - configured_radius_km)
            > 1.0e-12
            or model.get("sediment_model")
            != "routed_outgoing_deposition_and_mobile_thickness_v1"
            or model.get("floodplain_model")
            != "lowland_slope_sediment_wetland_baseflow_index_v1"
            or model.get("geometry_model")
            != "flow_runoff_floodplain_sediment_slope_baseflow_aridity_ice_v1"
            or model.get("stream_power_model")
            != "discharge_slope_runoff_sediment_flow_index_v1"
            or model.get("classification_model")
            != "ice_aridity_sediment_slope_depth_width_threshold_tree_v1"
            or model.get("system_grouping_model")
            != "undirected_mesh_connected_channel_components_v1"
            or model.get("system_length_model")
            != "internal_flow_to_great_circle_edges_v1"
            or model.get("deterministic") is not True
            or model.get("model_limitation")
            != "empirical_diagnostic_channel_geometry_without_subcell_cross_sections_calibrated_bankfull_frequency_or_transient_morphodynamics"
            or summary.get("river_channel_morphology_model")
            != RIVER_CHANNEL_MORPHOLOGY_MODEL
        )
    except (TypeError, ValueError):
        return failure
    if metadata_invalid:
        return failure

    def clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
        return max(lower, min(upper, value))

    def surface_elevation(cell: dict[str, Any]) -> float:
        return float(
            cell.get(
                "hydrologic_surface_elevation_m",
                cell.get("filled_elevation_m", cell.get("elevation_m", 0.0)),
            )
        )

    def great_circle_km(a: dict[str, Any], b: dict[str, Any]) -> float:
        lat_a = math.radians(float(a.get("lat_deg", 0.0)))
        lat_b = math.radians(float(b.get("lat_deg", 0.0)))
        dlat = lat_b - lat_a
        dlon = math.radians(
            float(b.get("lon_deg", 0.0)) - float(a.get("lon_deg", 0.0))
        )
        haversine = (
            math.sin(dlat / 2.0) ** 2
            + math.cos(lat_a)
            * math.cos(lat_b)
            * math.sin(dlon / 2.0) ** 2
        )
        return 2.0 * configured_radius_km * math.asin(
            min(1.0, math.sqrt(haversine))
        )

    def downstream_slope(cell: dict[str, Any]) -> float:
        next_cell = cells_by_id.get(int(cell.get("flow_to", -1)))
        if next_cell is None:
            return 0.0
        length_km = great_circle_km(cell, next_cell)
        if length_km <= 0.0:
            return 0.0
        drop_m = max(0.0, surface_elevation(cell) - surface_elevation(next_cell))
        return drop_m / max(1.0, length_km * 1000.0)

    def classify(
        flow_norm: float,
        runoff_norm: float,
        slope_index: float,
        sediment_index: float,
        floodplain: float,
        depth_m: float,
        width_m: float,
        aridity: float,
        ice: float,
    ) -> str:
        if ice >= 0.28:
            return "glacial_outwash_channel"
        if aridity >= 0.58 and runoff_norm < 0.22:
            return "ephemeral_wadi"
        if sediment_index >= 0.55 and flow_norm >= 0.18:
            return "braided_sediment_rich_channel"
        if slope_index >= 0.46 and sediment_index < 0.38:
            return "incised_bedrock_channel"
        if depth_m >= 3.2 and floodplain >= 0.45:
            return "deep_alluvial_channel"
        if depth_m >= 1.8 and width_m >= 42.0 and slope_index <= 0.32:
            return "navigable_lowland_channel"
        return "small_headwater"

    def primary_key(counter: Counter[str], fallback: str) -> str:
        if not counter:
            return fallback
        return sorted(counter.items(), key=lambda item: (-item[1], item[0]))[
            0
        ][0]

    try:
        max_flow = max(
            (
                max(0.0, float(cell.get("flow_accumulation", 0.0)))
                for cell in cells_by_id.values()
            ),
            default=1.0,
        )
    except (TypeError, ValueError):
        return failure
    candidate_ids = {
        cell_id
        for cell_id, cell in cells_by_id.items()
        if bool(cell.get("is_river", False))
        and not bool(cell.get("is_water", False))
    }
    expected_by_id: dict[int, dict[str, Any]] = {}
    class_counts: Counter[str] = Counter()
    width_sum = 0.0
    depth_sum = 0.0
    discharge_sum = 0.0
    stream_power_sum = 0.0
    slope_sum = 0.0
    navigable_depth_count = 0
    floodplain_connected_count = 0
    high_stream_power_count = 0

    for cell_id, cell in cells_by_id.items():
        if cell_id not in candidate_ids:
            raw = {
                "width": 0.0,
                "depth": 0.0,
                "discharge": 0.0,
                "slope": 0.0,
                "stream_power": 0.0,
                "floodplain": 0.0,
                "class": "non_channel",
                "system_id": -1,
            }
        else:
            try:
                flow_norm = clamp(
                    float(cell.get("flow_accumulation", 0.0))
                    / max(1.0, max_flow)
                )
                runoff_norm = clamp(float(cell.get("runoff_mm_y", 0.0)) / 2200.0)
                slope_index = clamp(downstream_slope(cell) / 0.028)
                routed_sediment = float(
                    cell.get(
                        "fluvial_sediment_routed_outgoing_m",
                        cell.get("sediment_export_m", 0.0),
                    )
                )
                sediment_index = clamp(
                    routed_sediment / 85.0 * 0.45
                    + float(cell.get("sediment_deposition_m", 0.0))
                    / 18.0
                    * 0.35
                    + float(cell.get("sediment_thickness_m", 0.0))
                    / 30.0
                    * 0.20
                )
                lowland = (
                    1.0
                    if str(cell.get("landform", ""))
                    in RIVER_CHANNEL_LOWLAND_FORMS
                    else 0.0
                )
                wetland = clamp(float(cell.get("wetland_extent_index", 0.0)))
                groundwater = clamp(
                    float(cell.get("baseflow_support_index", 0.0))
                )
                aridity = clamp(
                    float(cell.get("seasonal_aridity_index", 0.0))
                )
                ice = clamp(float(cell.get("ice_thickness_m", 0.0)) / 450.0)
                floodplain = clamp(
                    lowland * 0.34
                    + (1.0 - slope_index) * 0.22
                    + sediment_index * 0.18
                    + wetland * 0.14
                    + groundwater * 0.12
                )
                discharge = max(
                    0.0,
                    8.0
                    + 4600.0
                    * (flow_norm**0.82)
                    * (0.30 + runoff_norm * 0.62 + groundwater * 0.08)
                    - ice * 420.0
                    - aridity * 120.0,
                )
                width = max(
                    0.0,
                    5.0
                    + 210.0
                    * (flow_norm**0.56)
                    * (0.42 + runoff_norm * 0.36 + floodplain * 0.22)
                    + sediment_index * 36.0
                    - slope_index * 14.0
                    - ice * 18.0,
                )
                depth = max(
                    0.0,
                    0.35
                    + 7.6
                    * (flow_norm**0.42)
                    * (
                        0.36
                        + runoff_norm * 0.34
                        + groundwater * 0.12
                        + (1.0 - sediment_index) * 0.18
                    )
                    + slope_index * 0.55
                    - aridity * 0.36
                    - ice * 0.45,
                )
                stream_power = clamp(
                    (discharge / 4200.0) * 0.42
                    + slope_index * 0.34
                    + runoff_norm * 0.12
                    + sediment_index * 0.08
                    + flow_norm * 0.04
                )
                channel_class = classify(
                    flow_norm,
                    runoff_norm,
                    slope_index,
                    sediment_index,
                    floodplain,
                    depth,
                    width,
                    aridity,
                    ice,
                )
            except (TypeError, ValueError):
                return failure
            raw = {
                "width": width,
                "depth": depth,
                "discharge": discharge,
                "slope": slope_index,
                "stream_power": stream_power,
                "floodplain": floodplain,
                "class": channel_class,
                "system_id": -1,
            }
            width_sum += width
            depth_sum += depth
            discharge_sum += discharge
            stream_power_sum += stream_power
            slope_sum += slope_index
            navigable_depth_count += int(depth >= 1.8 and width >= 35.0)
            floodplain_connected_count += int(floodplain >= 0.45)
            high_stream_power_count += int(stream_power >= 0.62)

        expected = {
            "width": round(float(raw["width"]), 6),
            "depth": round(float(raw["depth"]), 6),
            "discharge": round(float(raw["discharge"]), 6),
            "slope": round(float(raw["slope"]), 6),
            "stream_power": round(float(raw["stream_power"]), 6),
            "floodplain": round(float(raw["floodplain"]), 6),
            "class": str(raw["class"]),
            "system_id": -1,
        }
        expected_by_id[cell_id] = expected
        class_counts[expected["class"]] += 1
        field_map = {
            "river_channel_width_m": "width",
            "river_channel_depth_m": "depth",
            "bankfull_discharge_m3_s": "discharge",
            "channel_slope_index": "slope",
            "stream_power_index": "stream_power",
            "floodplain_connectivity_index": "floodplain",
        }
        try:
            if any(
                (not _output_same(cell.get(field), expected[key]) if strict else abs(float(cell.get(field, math.inf)) - float(expected[key])) > 1.0e-9)
                for field, key in field_map.items()
            ) or str(cell.get("channel_morphology_class", "")) != expected[
                "class"
            ]:
                return failure
        except (TypeError, ValueError):
            return failure

    components: list[list[int]] = []
    remaining = set(candidate_ids)
    while remaining:
        start = min(remaining)
        remaining.remove(start)
        queue = [start]
        component_ids = [start]
        queue_index = 0
        while queue_index < len(queue):
            current_id = queue[queue_index]
            queue_index += 1
            neighbors = cells_by_id[current_id].get("neighbors", [])
            if not isinstance(neighbors, list):
                return failure
            for raw_neighbor_id in neighbors:
                neighbor_id = int(raw_neighbor_id)
                if neighbor_id not in remaining:
                    continue
                remaining.remove(neighbor_id)
                queue.append(neighbor_id)
                component_ids.append(neighbor_id)
        components.append(sorted(component_ids))

    expected_systems: list[dict[str, Any]] = []
    for component_ids in components:
        system_id = len(expected_systems)
        member_ids = set(component_ids)
        component = [cells_by_id[cell_id] for cell_id in component_ids]
        for cell_id in component_ids:
            expected_by_id[cell_id]["system_id"] = system_id
        class_counter = Counter(
            str(expected_by_id[cell_id]["class"])
            for cell_id in component_ids
        )
        basin_ids = sorted(
            {
                int(cell.get("basin_id", -1))
                for cell in component
                if int(cell.get("basin_id", -1)) >= 0
            }
        )
        outlet_candidates = [
            cell
            for cell in component
            if int(cell.get("flow_to", -1)) not in member_ids
        ] or component
        source_cell = max(
            component,
            key=lambda item: (surface_elevation(item), -int(item.get("id", -1))),
        )
        outlet_cell = max(
            outlet_candidates,
            key=lambda item: (
                float(item.get("flow_accumulation", 0.0)),
                -int(item.get("id", -1)),
            ),
        )
        group_count = len(component_ids)
        length_km = 0.0 + sum(
            great_circle_km(cell, cells_by_id[int(cell.get("flow_to", -1))])
            for cell in component
            if int(cell.get("flow_to", -1)) in member_ids
        )
        expected_systems.append(
            {
                "id": system_id,
                "channel_type": primary_key(
                    class_counter, "small_headwater"
                ),
                "cell_count": group_count,
                "cell_ids": component_ids,
                "basin_ids": basin_ids,
                "source_cell_id": int(source_cell.get("id", -1)),
                "outlet_cell_id": int(outlet_cell.get("id", -1)),
                "length_km": round(length_km, 6),
                "area_km2": round(
                    sum(
                        max(0.0, float(cell.get("area_km2", 0.0)))
                        for cell in component
                    ),
                    6,
                ),
                "mean_channel_width_m": round(
                    sum(expected_by_id[cell_id]["width"] for cell_id in component_ids)
                    / group_count,
                    6,
                ),
                "mean_channel_depth_m": round(
                    sum(expected_by_id[cell_id]["depth"] for cell_id in component_ids)
                    / group_count,
                    6,
                ),
                "mean_bankfull_discharge_m3_s": round(
                    sum(expected_by_id[cell_id]["discharge"] for cell_id in component_ids)
                    / group_count,
                    6,
                ),
                "mean_stream_power_index": round(
                    sum(expected_by_id[cell_id]["stream_power"] for cell_id in component_ids)
                    / group_count,
                    6,
                ),
                "mean_channel_slope_index": round(
                    sum(expected_by_id[cell_id]["slope"] for cell_id in component_ids)
                    / group_count,
                    6,
                ),
                "mean_floodplain_connectivity_index": round(
                    sum(expected_by_id[cell_id]["floodplain"] for cell_id in component_ids)
                    / group_count,
                    6,
                ),
                "navigable_depth_cell_count": sum(
                    expected_by_id[cell_id]["depth"] >= 1.8
                    and expected_by_id[cell_id]["width"] >= 35.0
                    for cell_id in component_ids
                ),
                "floodplain_connected_cell_count": sum(
                    expected_by_id[cell_id]["floodplain"] >= 0.45
                    for cell_id in component_ids
                ),
                "high_stream_power_cell_count": sum(
                    expected_by_id[cell_id]["stream_power"] >= 0.62
                    for cell_id in component_ids
                ),
                "channel_morphology_class_counts": dict(
                    sorted(class_counter.items())
                ),
            }
        )

    for cell_id, expected in expected_by_id.items():
        try:
            if int(cells_by_id[cell_id].get("river_channel_system_id", -2)) != int(
                expected["system_id"]
            ):
                return failure
        except (TypeError, ValueError):
            return failure
    if len(systems) != len(expected_systems):
        return failure
    for actual, expected in zip(systems, expected_systems):
        if (not _output_same(actual, expected)) if strict else (not isinstance(actual, dict) or any(actual.get(key) != value for key, value in expected.items())):
            return failure
    if (
        int(model.get("candidate_cell_count", -1)) != len(candidate_ids)
        or int(model.get("system_count", -1)) != len(expected_systems)
    ):
        return failure

    divisor = len(candidate_ids) if candidate_ids else 1
    expected_summary = {
        "river_channel_morphology_model": RIVER_CHANNEL_MORPHOLOGY_MODEL,
        "river_channel_cell_count": len(candidate_ids),
        "river_channel_system_count": len(expected_systems),
        "navigable_channel_depth_cell_count": navigable_depth_count,
        "floodplain_connected_channel_cell_count": floodplain_connected_count,
        "high_stream_power_channel_cell_count": high_stream_power_count,
        "total_river_channel_length_km": round(
            0.0 + sum(system["length_km"] for system in expected_systems), 6
        ),
        "mean_river_channel_width_m": (
            round(width_sum / divisor, 6) if candidate_ids else 0.0
        ),
        "mean_river_channel_depth_m": (
            round(depth_sum / divisor, 6) if candidate_ids else 0.0
        ),
        "mean_bankfull_discharge_m3_s": (
            round(discharge_sum / divisor, 6) if candidate_ids else 0.0
        ),
        "mean_stream_power_index": (
            round(stream_power_sum / divisor, 6) if candidate_ids else 0.0
        ),
        "mean_channel_slope_index": (
            round(slope_sum / divisor, 6) if candidate_ids else 0.0
        ),
        "channel_morphology_class_counts": dict(sorted(class_counts.items())),
    }
    if any(not _output_same(summary.get(key), value) if strict else summary.get(key) != value for key, value in expected_summary.items()):
        return failure
    return []


def _validate_river_hydraulics(
    payload: dict[str, Any],
    summary: dict[str, Any],
    cells_by_id: dict[int, dict[str, Any]],
    *, strict: bool = False,
) -> list[str]:
    """Replay channel hydraulics and one-to-one channel-system reaches."""

    failure = ["river hydraulics model or causal replay invalid"]
    model = payload.get("river_hydraulics_model", {})
    channel_systems = payload.get("river_channel_systems", [])
    reaches = payload.get("river_hydraulic_reaches", [])
    configured_gravity_m_s2 = surface_gravity_m_s2(payload)
    try:
        metadata_invalid = (
            not isinstance(model, dict)
            or not isinstance(channel_systems, list)
            or not isinstance(reaches, list)
            or model.get("model_type") != RIVER_HYDRAULICS_MODEL
            or model.get("source_channel_model")
            != RIVER_CHANNEL_MORPHOLOGY_MODEL
            or model.get("domain") != "is_river_and_not_is_water_cells"
            or model.get("cross_section_model")
            != "rectangular_area_and_wetted_perimeter_v1"
            or model.get("slope_model")
            != "channel_slope_index_times_0_028_with_1e_5_floor_v1"
            or model.get("roughness_model")
            != "morphology_sediment_wetland_ice_bounded_manning_n_v1"
            or model.get("velocity_model")
            != "55_percent_discharge_plus_45_percent_manning_bounded_v1"
            or model.get("froude_model")
            != "velocity_over_sqrt_gravity_times_depth_v1"
            or model.get("shear_model")
            != "density_gravity_hydraulic_radius_slope_v1"
            or model.get("capacity_model")
            != "cross_section_discharge_radius_velocity_index_v1"
            or model.get("navigability_model")
            != "depth_width_velocity_froude_slope_ice_index_v1"
            or model.get("regime_model")
            != "froude_velocity_shear_threshold_tree_v1"
            or model.get("reach_model")
            != "one_reach_per_river_channel_system_v1"
            or abs(
                float(model.get("gravity_m_s2", -1.0))
                - configured_gravity_m_s2
            )
            > 1.0e-12
            or abs(
                float(model.get("water_density_kg_m3", -1.0))
                - RIVER_HYDRAULICS_WATER_DENSITY_KG_M3
            )
            > 1.0e-12
            or float(model.get("maximum_velocity_m_s", -1.0)) != 12.0
            or abs(
                float(model.get("hydraulic_navigability_threshold", -1.0))
                - RIVER_HYDRAULICS_NAVIGABILITY_THRESHOLD
            )
            > 1.0e-12
            or abs(
                float(model.get("high_shear_stress_pa", -1.0))
                - RIVER_HYDRAULICS_HIGH_SHEAR_STRESS_PA
            )
            > 1.0e-12
            or model.get("deterministic") is not True
            or model.get("model_limitation")
            != "steady_diagnostic_rectangular_hydraulics_without_solved_continuity_backwater_flood_frequency_or_transient_flow"
            or summary.get("river_hydraulics_model")
            != RIVER_HYDRAULICS_MODEL
        )
    except (TypeError, ValueError):
        return failure
    if metadata_invalid:
        return failure

    def clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
        return max(lower, min(upper, value))

    def roughness(cell: dict[str, Any]) -> float:
        channel_class = str(
            cell.get("channel_morphology_class", "small_headwater")
        )
        base = RIVER_HYDRAULICS_ROUGHNESS_BY_CLASS.get(channel_class, 0.044)
        sediment = clamp(float(cell.get("sediment_routing_load_m", 0.0)) / 2.0)
        wetland = clamp(float(cell.get("wetland_extent_index", 0.0)))
        ice = clamp(float(cell.get("ice_thickness_m", 0.0)) / 300.0)
        return max(
            0.022,
            min(
                0.080,
                base + sediment * 0.006 + wetland * 0.004 + ice * 0.010,
            ),
        )

    def navigability(
        width: float,
        depth: float,
        velocity: float,
        froude: float,
        slope_index: float,
        ice: float,
    ) -> float:
        depth_score = clamp((depth - 1.0) / 3.0)
        width_score = clamp((width - 25.0) / 90.0)
        velocity_score = clamp(1.0 - abs(velocity - 1.25) / 2.5)
        regime_score = clamp(1.0 - max(0.0, froude - 0.45) / 0.75)
        slope_score = clamp(1.0 - slope_index / 0.65)
        return clamp(
            depth_score * 0.30
            + width_score * 0.22
            + velocity_score * 0.20
            + regime_score * 0.14
            + slope_score * 0.10
            - ice * 0.18
        )

    def flow_regime(froude: float, velocity: float, shear: float) -> str:
        if froude >= 1.0:
            return "supercritical"
        if froude >= 0.80:
            return "transitional"
        if velocity >= 2.6 or shear >= RIVER_HYDRAULICS_HIGH_SHEAR_STRESS_PA:
            return "swift_subcritical"
        return "subcritical"

    candidate_ids = {
        cell_id
        for cell_id, cell in cells_by_id.items()
        if bool(cell.get("is_river", False))
        and not bool(cell.get("is_water", False))
    }
    expected_by_id: dict[int, dict[str, Any]] = {}
    regime_counts: Counter[str] = Counter()
    radius_sum = 0.0
    velocity_sum = 0.0
    froude_sum = 0.0
    shear_sum = 0.0
    roughness_sum = 0.0
    capacity_sum = 0.0
    nav_sum = 0.0
    navigable_count = 0
    supercritical_count = 0
    high_shear_count = 0

    for cell_id, cell in cells_by_id.items():
        if cell_id not in candidate_ids:
            raw = {
                "radius": 0.0,
                "velocity": 0.0,
                "froude": 0.0,
                "shear": 0.0,
                "roughness": 0.0,
                "capacity": 0.0,
                "navigability": 0.0,
                "regime": "non_channel",
                "reach_id": -1,
            }
        else:
            try:
                width = max(0.0, float(cell.get("river_channel_width_m", 0.0)))
                depth = max(0.0, float(cell.get("river_channel_depth_m", 0.0)))
                discharge = max(
                    0.0, float(cell.get("bankfull_discharge_m3_s", 0.0))
                )
                slope_index = clamp(float(cell.get("channel_slope_index", 0.0)))
                slope = max(0.00001, slope_index * 0.028)
                area_m2 = max(0.001, width * depth)
                wetted_perimeter_m = max(0.001, width + 2.0 * depth)
                radius = area_m2 / wetted_perimeter_m
                manning_n = roughness(cell)
                discharge_velocity = discharge / area_m2
                manning_velocity = (
                    radius ** (2.0 / 3.0) * slope**0.5 / manning_n
                )
                velocity = max(
                    0.0,
                    min(
                        12.0,
                        discharge_velocity * 0.55 + manning_velocity * 0.45,
                    ),
                )
                froude = velocity / max(
                    0.001,
                    (
                        configured_gravity_m_s2
                        * max(0.001, depth)
                    )
                    ** 0.5,
                )
                shear = (
                    RIVER_HYDRAULICS_WATER_DENSITY_KG_M3
                    * configured_gravity_m_s2
                    * radius
                    * slope
                )
                capacity = clamp(
                    area_m2 / 450.0 * 0.38
                    + discharge / 2400.0 * 0.34
                    + radius / 4.5 * 0.16
                    + velocity / 4.0 * 0.12
                )
                ice = clamp(float(cell.get("ice_thickness_m", 0.0)) / 300.0)
                nav = navigability(
                    width,
                    depth,
                    velocity,
                    froude,
                    slope_index,
                    ice,
                )
                regime = flow_regime(froude, velocity, shear)
                reach_id = int(cell.get("river_channel_system_id", -1))
            except (TypeError, ValueError):
                return failure
            raw = {
                "radius": radius,
                "velocity": velocity,
                "froude": froude,
                "shear": shear,
                "roughness": manning_n,
                "capacity": capacity,
                "navigability": nav,
                "regime": regime,
                "reach_id": reach_id,
            }
            radius_sum += radius
            velocity_sum += velocity
            froude_sum += froude
            shear_sum += shear
            roughness_sum += manning_n
            capacity_sum += capacity
            nav_sum += nav
            navigable_count += int(
                nav >= RIVER_HYDRAULICS_NAVIGABILITY_THRESHOLD
            )
            supercritical_count += int(regime == "supercritical")
            high_shear_count += int(
                shear >= RIVER_HYDRAULICS_HIGH_SHEAR_STRESS_PA
            )

        expected = {
            "radius": round(float(raw["radius"]), 6),
            "velocity": round(float(raw["velocity"]), 6),
            "froude": round(float(raw["froude"]), 6),
            "shear": round(float(raw["shear"]), 6),
            "roughness": round(float(raw["roughness"]), 6),
            "capacity": round(float(raw["capacity"]), 6),
            "navigability": round(float(raw["navigability"]), 6),
            "regime": str(raw["regime"]),
            "reach_id": int(raw["reach_id"]),
        }
        expected_by_id[cell_id] = expected
        regime_counts[expected["regime"]] += 1
        field_map = {
            "hydraulic_radius_m": "radius",
            "flow_velocity_m_s": "velocity",
            "froude_number": "froude",
            "bed_shear_stress_pa": "shear",
            "manning_roughness_n": "roughness",
            "channel_capacity_index": "capacity",
            "hydraulic_navigability_index": "navigability",
        }
        try:
            if (
                any(
                    (not _output_same(cell.get(field), expected[key]) if strict else abs(float(cell.get(field, math.inf)) - float(expected[key])) > 1.0e-9)
                    for field, key in field_map.items()
                )
                or str(cell.get("hydraulic_flow_regime", ""))
                != expected["regime"]
                or int(cell.get("river_hydraulic_reach_id", -2))
                != expected["reach_id"]
            ):
                return failure
        except (TypeError, ValueError):
            return failure

    expected_reaches: list[dict[str, Any]] = []
    for system in channel_systems:
        if not isinstance(system, dict):
            return failure
        cell_ids = [int(cell_id) for cell_id in system.get("cell_ids", [])]
        reach_cell_ids = [
            cell_id for cell_id in cell_ids if cell_id in candidate_ids
        ]
        if not reach_cell_ids:
            continue
        reach_id = int(system.get("id", -1))
        reach_regime_counts = Counter(
            str(expected_by_id[cell_id]["regime"])
            for cell_id in reach_cell_ids
        )
        group_count = len(reach_cell_ids)
        expected_reaches.append(
            {
                "id": reach_id,
                "river_channel_system_id": reach_id,
                "cell_count": group_count,
                "cell_ids": reach_cell_ids,
                "basin_ids": [
                    int(value) for value in system.get("basin_ids", [])
                ],
                "source_cell_id": int(system.get("source_cell_id", -1)),
                "outlet_cell_id": int(system.get("outlet_cell_id", -1)),
                "length_km": round(float(system.get("length_km", 0.0)), 6),
                "area_km2": round(float(system.get("area_km2", 0.0)), 6),
                "dominant_hydraulic_flow_regime": sorted(
                    reach_regime_counts.items(),
                    key=lambda item: (-item[1], item[0]),
                )[0][0],
                "mean_hydraulic_radius_m": round(
                    sum(expected_by_id[cell_id]["radius"] for cell_id in reach_cell_ids)
                    / group_count,
                    6,
                ),
                "mean_flow_velocity_m_s": round(
                    sum(expected_by_id[cell_id]["velocity"] for cell_id in reach_cell_ids)
                    / group_count,
                    6,
                ),
                "mean_froude_number": round(
                    sum(expected_by_id[cell_id]["froude"] for cell_id in reach_cell_ids)
                    / group_count,
                    6,
                ),
                "mean_bed_shear_stress_pa": round(
                    sum(expected_by_id[cell_id]["shear"] for cell_id in reach_cell_ids)
                    / group_count,
                    6,
                ),
                "mean_manning_roughness_n": round(
                    sum(expected_by_id[cell_id]["roughness"] for cell_id in reach_cell_ids)
                    / group_count,
                    6,
                ),
                "mean_channel_capacity_index": round(
                    sum(expected_by_id[cell_id]["capacity"] for cell_id in reach_cell_ids)
                    / group_count,
                    6,
                ),
                "mean_hydraulic_navigability_index": round(
                    sum(expected_by_id[cell_id]["navigability"] for cell_id in reach_cell_ids)
                    / group_count,
                    6,
                ),
                "hydraulically_navigable_cell_count": sum(
                    expected_by_id[cell_id]["navigability"]
                    >= RIVER_HYDRAULICS_NAVIGABILITY_THRESHOLD
                    for cell_id in reach_cell_ids
                ),
                "supercritical_flow_cell_count": sum(
                    expected_by_id[cell_id]["regime"] == "supercritical"
                    for cell_id in reach_cell_ids
                ),
                "high_shear_stress_cell_count": sum(
                    expected_by_id[cell_id]["shear"]
                    >= RIVER_HYDRAULICS_HIGH_SHEAR_STRESS_PA
                    for cell_id in reach_cell_ids
                ),
                "hydraulic_flow_regime_counts": dict(
                    sorted(reach_regime_counts.items())
                ),
            }
        )

    if len(reaches) != len(expected_reaches):
        return failure
    for actual, expected in zip(reaches, expected_reaches):
        if (not _output_same(actual, expected)) if strict else (not isinstance(actual, dict) or any(actual.get(key) != value for key, value in expected.items())):
            return failure
    if (
        int(model.get("candidate_cell_count", -1)) != len(candidate_ids)
        or int(model.get("reach_count", -1)) != len(expected_reaches)
    ):
        return failure

    divisor = len(candidate_ids) if candidate_ids else 1
    expected_summary = {
        "river_hydraulics_model": RIVER_HYDRAULICS_MODEL,
        "river_hydraulic_cell_count": len(candidate_ids),
        "river_hydraulic_reach_count": len(expected_reaches),
        "mean_hydraulic_radius_m": (
            round(radius_sum / divisor, 6) if candidate_ids else 0.0
        ),
        "mean_flow_velocity_m_s": (
            round(velocity_sum / divisor, 6) if candidate_ids else 0.0
        ),
        "mean_froude_number": (
            round(froude_sum / divisor, 6) if candidate_ids else 0.0
        ),
        "mean_bed_shear_stress_pa": (
            round(shear_sum / divisor, 6) if candidate_ids else 0.0
        ),
        "mean_manning_roughness_n": (
            round(roughness_sum / divisor, 6) if candidate_ids else 0.0
        ),
        "mean_channel_capacity_index": (
            round(capacity_sum / divisor, 6) if candidate_ids else 0.0
        ),
        "mean_hydraulic_navigability_index": (
            round(nav_sum / divisor, 6) if candidate_ids else 0.0
        ),
        "hydraulically_navigable_cell_count": navigable_count,
        "supercritical_flow_cell_count": supercritical_count,
        "high_shear_stress_cell_count": high_shear_count,
        "hydraulic_flow_regime_counts": dict(sorted(regime_counts.items())),
    }
    if any(not _output_same(summary.get(key), value) if strict else summary.get(key) != value for key, value in expected_summary.items()):
        return failure
    return []
