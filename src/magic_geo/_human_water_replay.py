"""Independent historical numerical oracles for human water transport.

Copied from the independently implemented CLI replay, not producer formulas.
Versioned source/output contracts are checked by human_water_transport_validation.
Metadata-only local views permit reuse of these unchanged numerical equations.
"""
from __future__ import annotations
import heapq
import math
from collections import Counter
from typing import Any
from .planet_parameters import planet_radius_km as configured_planet_radius_km

AQUIFER_RESOURCE_MODEL = "finite_recharge_causal_aquifer_resources_v1"

RIVER_CHANNEL_MORPHOLOGY_MODEL = (
    "causal_flow_sediment_wetland_baseflow_channel_morphology_v1"
)

RIVER_CHANNEL_LOWLAND_FORMS = {
    "delta",
    "floodplain",
    "river_valley",
    "coastal_plain",
    "lacustrine_basin",
}

RIVER_HYDRAULICS_MODEL = "manning_blended_diagnostic_river_hydraulics_v1"

NAVIGABILITY_MODEL = "causal_channel_hydraulic_coastal_navigability_v1"

NAVIGABILITY_THRESHOLD = 0.52

NAVIGABILITY_HIGH_HARBOR_THRESHOLD = 0.62

NAVIGABILITY_TRANSPORT_CHOKEPOINT_THRESHOLD = 0.55

NAVIGABILITY_MARINE_WATER_TYPES = {
    "ocean",
    "continental_shelf",
    "inland_sea",
}

PORT_SITE_MODEL = "causal_navigability_coastal_port_site_selection_v1"

PORT_SITE_THRESHOLD = 0.58

PORT_PROTECTED_BAY_THRESHOLD = 0.55

PORT_RIVER_MOUTH_THRESHOLD = 0.50

PORT_STRAIT_ACCESS_THRESHOLD = 0.55

ROUTE_CORRIDOR_MODEL = "causal_feature_weighted_dijkstra_route_corridors_v1"

ROUTE_FEATURE_THRESHOLD = 0.45

ROUTE_MOUNTAIN_LANDFORMS = {
    "mountain",
    "mountain_range",
    "volcanic_arc",
    "highland",
    "ridge",
    "glacial_valley",
}

ROUTE_RIVER_VALLEY_LANDFORMS = {
    "delta",
    "floodplain",
    "river_valley",
    "alluvial_fan",
    "wetland",
}

ROUTE_DESERT_BIOMES = {
    "hot_desert",
    "cold_desert",
    "desert",
    "semi_arid_desert",
}

def _validate_navigability(
    payload: dict[str, Any],
    summary: dict[str, Any],
    cells_by_id: dict[int, dict[str, Any]],
) -> list[str]:
    """Replay navigability components, classes, and exact waterway records."""

    failure = ["navigability model or causal replay invalid"]
    model = payload.get("navigability_model", {})
    waterways = payload.get("navigable_waterways", [])
    try:
        metadata_invalid = (
            not isinstance(model, dict)
            or not isinstance(waterways, list)
            or model.get("model_type") != NAVIGABILITY_MODEL
            or model.get("source_channel_model")
            != RIVER_CHANNEL_MORPHOLOGY_MODEL
            or model.get("source_hydraulics_model")
            != RIVER_HYDRAULICS_MODEL
            or model.get("domain") != "all_cells"
            or model.get("flow_normalization_model")
            != "global_max_flow_accumulation_v1"
            or model.get("river_model")
            != "flow_runoff_lowland_relief_sediment_channel_hydraulic_ice_aridity_v1"
            or model.get("coastal_model")
            != "marine_depth_shelf_land_contact_constriction_or_coastal_land_context_v1"
            or model.get("harbor_model")
            != "coastal_protection_river_mouth_relief_settlement_ice_v1"
            or model.get("transport_chokepoint_model")
            != "marine_constriction_and_coastal_navigability_v1"
            or model.get("overall_model")
            != "maximum_component_navigability_v1"
            or model.get("classification_model")
            != "chokepoint_harbor_river_mouth_river_coastal_priority_v1"
            or model.get("system_grouping_model")
            != "undirected_mesh_connected_raw_threshold_components_v1"
            or model.get("link_model")
            != "component_cell_settlement_route_marine_region_watershed_links_v1"
            or abs(
                float(model.get("navigable_threshold", -1.0))
                - NAVIGABILITY_THRESHOLD
            )
            > 1.0e-12
            or abs(
                float(model.get("high_harbor_threshold", -1.0))
                - NAVIGABILITY_HIGH_HARBOR_THRESHOLD
            )
            > 1.0e-12
            or abs(
                float(model.get("transport_chokepoint_threshold", -1.0))
                - NAVIGABILITY_TRANSPORT_CHOKEPOINT_THRESHOLD
            )
            > 1.0e-12
            or model.get("threshold_semantics")
            != "unrounded_pre_serialization_values"
            or model.get("deterministic") is not True
            or model.get("model_limitation")
            != "diagnostic_transport_suitability_without_vessel_classes_seasonal_discharge_bathymetric_channels_or_route_cost_optimization"
            or summary.get("navigability_model") != NAVIGABILITY_MODEL
        )
    except (TypeError, ValueError):
        return failure
    if metadata_invalid:
        return failure

    def clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
        return max(lower, min(upper, value))

    def marine_neighbors(cell: dict[str, Any]) -> list[dict[str, Any]]:
        neighbors: list[dict[str, Any]] = []
        raw_neighbors = cell.get("neighbors", [])
        if not isinstance(raw_neighbors, list):
            raise ValueError("neighbors must be a list")
        for raw_neighbor_id in raw_neighbors:
            neighbor = cells_by_id.get(int(raw_neighbor_id))
            if (
                neighbor is not None
                and str(neighbor.get("water_body_type", "land"))
                in NAVIGABILITY_MARINE_WATER_TYPES
            ):
                neighbors.append(neighbor)
        return neighbors

    def land_neighbors(cell: dict[str, Any]) -> list[dict[str, Any]]:
        neighbors: list[dict[str, Any]] = []
        raw_neighbors = cell.get("neighbors", [])
        if not isinstance(raw_neighbors, list):
            raise ValueError("neighbors must be a list")
        for raw_neighbor_id in raw_neighbors:
            neighbor = cells_by_id.get(int(raw_neighbor_id))
            if neighbor is not None and not bool(neighbor.get("is_water", False)):
                neighbors.append(neighbor)
        return neighbors

    chokepoints = payload.get("marine_chokepoints", [])
    if not isinstance(chokepoints, list):
        return failure
    chokepoint_by_cell = {
        int(chokepoint.get("cell_id", -1)): chokepoint
        for chokepoint in chokepoints
        if isinstance(chokepoint, dict)
        and int(chokepoint.get("cell_id", -1)) >= 0
    }
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

    def river_navigability(cell: dict[str, Any]) -> float:
        if bool(cell.get("is_water", False)) or not bool(
            cell.get("is_river", False)
        ):
            return 0.0
        flow = clamp(
            float(cell.get("flow_accumulation", 0.0)) / max(1.0, max_flow)
        )
        runoff = clamp(float(cell.get("runoff_mm_y", 0.0)) / 900.0)
        lowland = (
            0.22
            if str(cell.get("landform", "")) in RIVER_CHANNEL_LOWLAND_FORMS
            else 0.0
        )
        low_relief = clamp(
            1.0 - abs(float(cell.get("elevation_m", 0.0))) / 1800.0
        )
        sediment_load = clamp(
            float(cell.get("sediment_routing_load_m", 0.0)) / 2.0
        )
        channel_depth = clamp(
            float(cell.get("river_channel_depth_m", 0.0)) / 3.0
        )
        channel_width = clamp(
            float(cell.get("river_channel_width_m", 0.0)) / 80.0
        )
        hydraulic = clamp(
            float(cell.get("hydraulic_navigability_index", 0.0))
        )
        ice_penalty = clamp(
            float(cell.get("ice_thickness_m", 0.0)) / 350.0
        )
        aridity_penalty = (
            clamp(float(cell.get("seasonal_aridity_index", 0.0))) * 0.08
        )
        return clamp(
            flow * 0.24
            + runoff * 0.13
            + low_relief * 0.12
            + lowland
            + sediment_load * 0.06
            + channel_depth * 0.14
            + channel_width * 0.08
            + hydraulic * 0.17
            - ice_penalty * 0.24
            - aridity_penalty
        )

    def coastal_navigability(cell: dict[str, Any]) -> float:
        water_body = str(cell.get("water_body_type", "land"))
        if water_body in NAVIGABILITY_MARINE_WATER_TYPES:
            depth = clamp(float(cell.get("water_depth_m", 0.0)) / 180.0)
            shelf = (
                0.24
                if water_body in {"continental_shelf", "inland_sea"}
                else 0.08
            )
            land_contact = clamp(len(land_neighbors(cell)) / 4.0)
            constriction = clamp(
                float(
                    chokepoint_by_cell.get(
                        int(cell.get("id", -1)), {}
                    ).get("constriction_index", 0.0)
                )
            )
            return clamp(
                depth * 0.30
                + shelf
                + land_contact * 0.20
                + constriction * 0.26
            )

        adjacent_marine = marine_neighbors(cell)
        if not adjacent_marine:
            return 0.0
        neighbor_score = clamp(len(adjacent_marine) / 4.0)
        protected = (
            0.20
            if any(
                str(neighbor.get("water_body_type", ""))
                in {"continental_shelf", "inland_sea"}
                for neighbor in adjacent_marine
            )
            else 0.0
        )
        river_mouth = (
            0.22
            if bool(cell.get("is_river", False))
            or str(cell.get("landform", "")) == "delta"
            else 0.0
        )
        low_relief = clamp(
            1.0 - abs(float(cell.get("elevation_m", 0.0))) / 1200.0
        )
        return clamp(
            neighbor_score * 0.32 + protected + river_mouth + low_relief * 0.18
        )

    def harbor_suitability(
        cell: dict[str, Any], coastal: float
    ) -> float:
        if bool(cell.get("is_water", False)):
            return 0.0
        adjacent_marine = marine_neighbors(cell)
        if not adjacent_marine:
            return 0.0
        protected = (
            0.24
            if any(
                str(neighbor.get("water_body_type", ""))
                in {"continental_shelf", "inland_sea"}
                for neighbor in adjacent_marine
            )
            else 0.0
        )
        river_mouth = (
            0.18
            if bool(cell.get("is_river", False))
            or str(cell.get("landform", "")) == "delta"
            else 0.0
        )
        low_relief = clamp(
            1.0 - abs(float(cell.get("elevation_m", 0.0))) / 900.0
        )
        settlement = clamp(float(cell.get("settlement_score", 0.0)))
        ice_penalty = clamp(
            float(cell.get("ice_thickness_m", 0.0)) / 300.0
        )
        return clamp(
            coastal * 0.32
            + protected
            + river_mouth
            + low_relief * 0.14
            + settlement * 0.18
            - ice_penalty * 0.22
        )

    def transport_chokepoint(
        cell: dict[str, Any], coastal: float
    ) -> float:
        chokepoint = chokepoint_by_cell.get(int(cell.get("id", -1)))
        if chokepoint is None:
            return 0.0
        constriction = clamp(float(chokepoint.get("constriction_index", 0.0)))
        return clamp(constriction * 0.72 + coastal * 0.28)

    def classify(
        river: float, coastal: float, harbor: float, chokepoint: float
    ) -> str:
        if chokepoint >= NAVIGABILITY_TRANSPORT_CHOKEPOINT_THRESHOLD:
            return "transport_chokepoint"
        if harbor >= NAVIGABILITY_HIGH_HARBOR_THRESHOLD:
            return "harbor"
        if river >= NAVIGABILITY_THRESHOLD and coastal >= NAVIGABILITY_THRESHOLD:
            return "river_mouth"
        if river >= NAVIGABILITY_THRESHOLD:
            return "river_corridor"
        if coastal >= NAVIGABILITY_THRESHOLD:
            return "coastal_corridor"
        return "non_navigable"

    expected_by_id: dict[int, dict[str, Any]] = {}
    candidate_ids: set[int] = set()
    class_counts: Counter[str] = Counter()
    river_sum = 0.0
    coastal_sum = 0.0
    harbor_sum = 0.0
    chokepoint_sum = 0.0
    navigability_sum = 0.0
    high_harbor_count = 0
    transport_chokepoint_count = 0
    for cell_id, cell in cells_by_id.items():
        try:
            river = river_navigability(cell)
            coastal = coastal_navigability(cell)
            harbor = harbor_suitability(cell, coastal)
            chokepoint = transport_chokepoint(cell, coastal)
        except (TypeError, ValueError):
            return failure
        navigability = max(river, coastal, harbor, chokepoint)
        nav_class = classify(river, coastal, harbor, chokepoint)
        expected = {
            "river": round(river, 6),
            "coastal": round(coastal, 6),
            "harbor": round(harbor, 6),
            "chokepoint": round(chokepoint, 6),
            "navigability": round(navigability, 6),
            "class": nav_class,
            "waterway_id": -1,
        }
        expected_by_id[cell_id] = expected
        if navigability >= NAVIGABILITY_THRESHOLD:
            candidate_ids.add(cell_id)
        high_harbor_count += int(
            harbor >= NAVIGABILITY_HIGH_HARBOR_THRESHOLD
        )
        transport_chokepoint_count += int(
            chokepoint >= NAVIGABILITY_TRANSPORT_CHOKEPOINT_THRESHOLD
        )
        river_sum += river
        coastal_sum += coastal
        harbor_sum += harbor
        chokepoint_sum += chokepoint
        navigability_sum += navigability
        class_counts[nav_class] += 1
        field_map = {
            "river_navigability_index": "river",
            "coastal_navigability_index": "coastal",
            "harbor_suitability_index": "harbor",
            "transport_chokepoint_index": "chokepoint",
            "navigability_index": "navigability",
        }
        try:
            if any(
                abs(float(cell.get(field, math.inf)) - float(expected[key]))
                > 1.0e-9
                for field, key in field_map.items()
            ) or str(cell.get("navigability_class", "")) != nav_class:
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
            raw_neighbors = cells_by_id[current_id].get("neighbors", [])
            if not isinstance(raw_neighbors, list):
                return failure
            for raw_neighbor_id in raw_neighbors:
                neighbor_id = int(raw_neighbor_id)
                if neighbor_id not in remaining:
                    continue
                remaining.remove(neighbor_id)
                queue.append(neighbor_id)
                component_ids.append(neighbor_id)
        components.append(sorted(component_ids))

    settlements = payload.get("settlements", [])
    routes = payload.get("routes", [])
    if not isinstance(settlements, list) or not isinstance(routes, list):
        return failure
    settlements_by_cell: dict[int, list[int]] = {}
    for settlement in settlements:
        if not isinstance(settlement, dict):
            return failure
        settlements_by_cell.setdefault(
            int(settlement.get("cell_id", -1)), []
        ).append(int(settlement.get("id", -1)))
    routes_by_settlement: dict[int, set[int]] = {}
    for route in routes:
        if not isinstance(route, dict):
            return failure
        route_id = int(route.get("id", -1))
        for key in ("from", "to"):
            settlement_id = int(route.get(key, -1))
            if settlement_id >= 0 and route_id >= 0:
                routes_by_settlement.setdefault(settlement_id, set()).add(
                    route_id
                )

    def waterway_type(component_ids: list[int]) -> str:
        classes = Counter(
            str(expected_by_id[cell_id]["class"])
            for cell_id in component_ids
        )
        if classes.get("transport_chokepoint", 0) > 0:
            return "transport_chokepoint"
        if classes.get("river_mouth", 0) > 0:
            return "river_mouth_corridor"
        if classes.get("harbor", 0) > 0:
            return "harbor_cluster"
        if classes.get("river_corridor", 0) > 0:
            return "river_corridor"
        return "coastal_corridor"

    expected_waterways: list[dict[str, Any]] = []
    for component_ids in components:
        waterway_id = len(expected_waterways)
        for cell_id in component_ids:
            expected_by_id[cell_id]["waterway_id"] = waterway_id
        component = [cells_by_id[cell_id] for cell_id in component_ids]
        settlement_ids = sorted(
            {
                settlement_id
                for cell_id in component_ids
                for settlement_id in settlements_by_cell.get(cell_id, [])
                if settlement_id >= 0
            }
        )
        route_ids = sorted(
            {
                route_id
                for settlement_id in settlement_ids
                for route_id in routes_by_settlement.get(settlement_id, set())
                if route_id >= 0
            }
        )
        group_count = len(component_ids)
        expected_waterways.append(
            {
                "id": waterway_id,
                "waterway_type": waterway_type(component_ids),
                "cell_count": group_count,
                "cell_ids": component_ids,
                "area_km2": round(
                    sum(
                        max(0.0, float(cell.get("area_km2", 0.0)))
                        for cell in component
                    ),
                    6,
                ),
                "mean_navigability_index": round(
                    sum(expected_by_id[cell_id]["navigability"] for cell_id in component_ids)
                    / group_count,
                    6,
                ),
                "mean_river_navigability_index": round(
                    sum(expected_by_id[cell_id]["river"] for cell_id in component_ids)
                    / group_count,
                    6,
                ),
                "mean_coastal_navigability_index": round(
                    sum(expected_by_id[cell_id]["coastal"] for cell_id in component_ids)
                    / group_count,
                    6,
                ),
                "max_harbor_suitability_index": round(
                    max(expected_by_id[cell_id]["harbor"] for cell_id in component_ids),
                    6,
                ),
                "transport_chokepoint_cell_count": sum(
                    expected_by_id[cell_id]["chokepoint"]
                    >= NAVIGABILITY_TRANSPORT_CHOKEPOINT_THRESHOLD
                    for cell_id in component_ids
                ),
                "settlement_ids": settlement_ids,
                "route_ids": route_ids,
                "marine_region_ids": sorted(
                    {
                        int(cell.get("marine_region_id", -1))
                        for cell in component
                        if int(cell.get("marine_region_id", -1)) >= 0
                    }
                ),
                "watershed_ids": sorted(
                    {
                        int(cell.get("basin_id", -1))
                        for cell in component
                        if int(cell.get("basin_id", -1)) >= 0
                    }
                ),
            }
        )

    for cell_id, expected in expected_by_id.items():
        try:
            if int(cells_by_id[cell_id].get("navigable_waterway_id", -2)) != int(
                expected["waterway_id"]
            ):
                return failure
        except (TypeError, ValueError):
            return failure
    if len(waterways) != len(expected_waterways):
        return failure
    for actual, expected in zip(waterways, expected_waterways):
        if not isinstance(actual, dict) or any(
            actual.get(key) != value for key, value in expected.items()
        ):
            return failure
    if (
        int(model.get("candidate_cell_count", -1)) != len(candidate_ids)
        or int(model.get("waterway_count", -1)) != len(expected_waterways)
    ):
        return failure

    count = len(cells_by_id)
    if count <= 0:
        return failure
    expected_summary = {
        "navigability_model": NAVIGABILITY_MODEL,
        "navigable_cell_count": len(candidate_ids),
        "navigable_waterway_count": len(expected_waterways),
        "navigable_waterway_total_area_km2": round(
            sum(record["area_km2"] for record in expected_waterways), 6
        ),
        "mean_navigability_index": round(navigability_sum / count, 6),
        "mean_river_navigability_index": round(river_sum / count, 6),
        "mean_coastal_navigability_index": round(coastal_sum / count, 6),
        "mean_harbor_suitability_index": round(harbor_sum / count, 6),
        "mean_transport_chokepoint_index": round(
            chokepoint_sum / count, 6
        ),
        "high_harbor_suitability_cell_count": high_harbor_count,
        "transport_chokepoint_cell_count": transport_chokepoint_count,
        "navigability_class_counts": dict(sorted(class_counts.items())),
    }
    if any(summary.get(key) != value for key, value in expected_summary.items()):
        return failure
    return []

def _validate_port_sites(
    payload: dict[str, Any],
    summary: dict[str, Any],
    cells_by_id: dict[int, dict[str, Any]],
) -> list[str]:
    """Replay port suitability, selection, type priority, records, and links."""

    failure = ["port site model or causal replay invalid"]
    model = payload.get("port_site_model", {})
    sites = payload.get("port_sites", [])
    try:
        metadata_invalid = (
            not isinstance(model, dict)
            or not isinstance(sites, list)
            or model.get("model_type") != PORT_SITE_MODEL
            or model.get("source_navigability_model") != NAVIGABILITY_MODEL
            or model.get("domain") != "all_cells_with_land_only_selection"
            or model.get("protected_bay_model")
            != "marine_contact_protected_water_enclosure_depth_harbor_v1"
            or model.get("river_mouth_model")
            != "river_landform_flow_runoff_delta_harbor_v1"
            or model.get("strait_access_model")
            != "adjacent_marine_chokepoint_constriction_and_coastal_access_v1"
            or model.get("suitability_model")
            != "harbor_bay_river_strait_coastal_settlement_climate_ice_relief_v1"
            or model.get("classification_model")
            != "strait_river_mouth_protected_bay_harbor_coastal_priority_v1"
            or model.get("selection_model")
            != "raw_suitability_without_severe_ice_or_port_settlement_override_v1"
            or model.get("record_order") != "ascending_candidate_cell_id"
            or model.get("link_model")
            != "cell_settlement_route_marine_region_chokepoint_nearby_waterway_links_v1"
            or abs(
                float(model.get("port_site_threshold", -1.0))
                - PORT_SITE_THRESHOLD
            )
            > 1.0e-12
            or abs(
                float(model.get("protected_bay_threshold", -1.0))
                - PORT_PROTECTED_BAY_THRESHOLD
            )
            > 1.0e-12
            or abs(
                float(model.get("river_mouth_threshold", -1.0))
                - PORT_RIVER_MOUTH_THRESHOLD
            )
            > 1.0e-12
            or abs(
                float(model.get("strait_access_threshold", -1.0))
                - PORT_STRAIT_ACCESS_THRESHOLD
            )
            > 1.0e-12
            or model.get("threshold_semantics")
            != "unrounded_pre_serialization_values_except_record_flags_use_serialized_fields"
            or model.get("deterministic") is not True
            or model.get("model_limitation")
            != "diagnostic_port_suitability_without_harbor_bathymetry_tides_waves_sedimentation_engineering_or_economic_optimization"
            or summary.get("port_site_model") != PORT_SITE_MODEL
        )
    except (TypeError, ValueError):
        return failure
    if metadata_invalid:
        return failure

    def clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
        return max(lower, min(upper, value))

    def marine_neighbors(cell: dict[str, Any]) -> list[dict[str, Any]]:
        raw_neighbors = cell.get("neighbors", [])
        if not isinstance(raw_neighbors, list):
            raise ValueError("neighbors must be a list")
        return [
            neighbor
            for raw_neighbor_id in raw_neighbors
            if (neighbor := cells_by_id.get(int(raw_neighbor_id))) is not None
            and str(neighbor.get("water_body_type", "land"))
            in NAVIGABILITY_MARINE_WATER_TYPES
        ]

    def land_neighbor_fraction(cell: dict[str, Any]) -> float:
        raw_neighbors = cell.get("neighbors", [])
        if not isinstance(raw_neighbors, list) or not raw_neighbors:
            return 0.0
        valid = [
            neighbor
            for raw_neighbor_id in raw_neighbors
            if (neighbor := cells_by_id.get(int(raw_neighbor_id))) is not None
        ]
        if not valid:
            return 0.0
        return sum(not bool(neighbor.get("is_water", False)) for neighbor in valid) / len(valid)

    chokepoints = payload.get("marine_chokepoints", [])
    settlements = payload.get("settlements", [])
    routes = payload.get("routes", [])
    if (
        not isinstance(chokepoints, list)
        or not isinstance(settlements, list)
        or not isinstance(routes, list)
    ):
        return failure
    chokepoint_by_id = {
        int(chokepoint.get("id", -1)): chokepoint
        for chokepoint in chokepoints
        if isinstance(chokepoint, dict)
        and int(chokepoint.get("id", -1)) >= 0
    }
    settlements_by_cell: dict[int, list[dict[str, Any]]] = {}
    for settlement in settlements:
        if not isinstance(settlement, dict):
            return failure
        cell_id = int(settlement.get("cell_id", -1))
        if cell_id >= 0:
            settlements_by_cell.setdefault(cell_id, []).append(settlement)
    routes_by_settlement: dict[int, set[int]] = {}
    for route in routes:
        if not isinstance(route, dict):
            return failure
        route_id = int(route.get("id", -1))
        if route_id < 0:
            continue
        for key in ("from", "to"):
            settlement_id = int(route.get(key, -1))
            if settlement_id >= 0:
                routes_by_settlement.setdefault(settlement_id, set()).add(
                    route_id
                )
    port_settlement_cell_ids = {
        cell_id
        for cell_id, local_settlements in settlements_by_cell.items()
        if any(
            str(settlement.get("type", "")) == "port"
            for settlement in local_settlements
        )
    }
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

    def protected_bay(
        cell: dict[str, Any], adjacent_marine: list[dict[str, Any]]
    ) -> float:
        if bool(cell.get("is_water", False)) or not adjacent_marine:
            return 0.0
        contact = clamp(len(adjacent_marine) / 3.0)
        protected = sum(
            str(neighbor.get("water_body_type", ""))
            in {"continental_shelf", "inland_sea"}
            for neighbor in adjacent_marine
        ) / len(adjacent_marine)
        enclosure = sum(
            land_neighbor_fraction(neighbor) for neighbor in adjacent_marine
        ) / len(adjacent_marine)
        shallow = sum(
            clamp(1.0 - float(neighbor.get("water_depth_m", 0.0)) / 260.0)
            for neighbor in adjacent_marine
        ) / len(adjacent_marine)
        harbor = clamp(float(cell.get("harbor_suitability_index", 0.0)))
        return clamp(
            contact * 0.20
            + protected * 0.25
            + enclosure * 0.25
            + shallow * 0.16
            + harbor * 0.14
        )

    def river_mouth(
        cell: dict[str, Any], adjacent_marine: list[dict[str, Any]]
    ) -> float:
        if bool(cell.get("is_water", False)) or not adjacent_marine:
            return 0.0
        landform = str(cell.get("landform", ""))
        if not bool(cell.get("is_river", False)) and landform not in {
            "delta",
            "floodplain",
            "river_valley",
        }:
            return 0.0
        flow = clamp(
            float(cell.get("flow_accumulation", 0.0)) / max(1.0, max_flow)
        )
        runoff = clamp(float(cell.get("runoff_mm_y", 0.0)) / 900.0)
        delta_bonus = (
            0.26
            if landform == "delta"
            else 0.12
            if landform in {"floodplain", "river_valley"}
            else 0.0
        )
        harbor = clamp(float(cell.get("harbor_suitability_index", 0.0)))
        return clamp(
            0.28 + flow * 0.22 + runoff * 0.14 + delta_bonus + harbor * 0.10
        )

    def strait_access(
        cell: dict[str, Any], adjacent_marine: list[dict[str, Any]]
    ) -> float:
        if bool(cell.get("is_water", False)) or not adjacent_marine:
            return 0.0
        best = 0.0
        for neighbor in adjacent_marine:
            chokepoint = chokepoint_by_id.get(
                int(neighbor.get("marine_chokepoint_id", -1))
            )
            if chokepoint is None:
                continue
            constriction = clamp(
                float(chokepoint.get("constriction_index", 0.0))
            )
            if str(chokepoint.get("type", "")) == "strait":
                constriction = max(constriction, 0.60)
            best = max(best, constriction)
        coastal = clamp(float(cell.get("coastal_navigability_index", 0.0)))
        return clamp(best * 0.76 + coastal * 0.24)

    def suitability(
        cell: dict[str, Any], bay: float, mouth: float, strait: float
    ) -> float:
        if bool(cell.get("is_water", False)):
            return 0.0
        harbor = clamp(float(cell.get("harbor_suitability_index", 0.0)))
        coastal = clamp(float(cell.get("coastal_navigability_index", 0.0)))
        settlement = clamp(float(cell.get("settlement_score", 0.0)))
        climate = clamp((float(cell.get("temperature_c", 0.0)) + 8.0) / 30.0)
        ice_penalty = clamp(float(cell.get("ice_thickness_m", 0.0)) / 220.0)
        relief_penalty = clamp(
            (abs(float(cell.get("elevation_m", 0.0))) - 1200.0) / 1800.0
        )
        base = max(harbor, bay, mouth, strait)
        return clamp(
            base * 0.40
            + bay * 0.16
            + mouth * 0.14
            + strait * 0.12
            + coastal * 0.06
            + settlement * 0.06
            + climate * 0.06
            - ice_penalty * 0.32
            - relief_penalty * 0.08
        )

    def site_type(
        bay: float, mouth: float, strait: float, harbor: float, score: float
    ) -> str:
        if strait >= PORT_STRAIT_ACCESS_THRESHOLD:
            return "strait_port"
        if mouth >= PORT_RIVER_MOUTH_THRESHOLD:
            return "river_mouth_port"
        if bay >= PORT_PROTECTED_BAY_THRESHOLD:
            return "protected_bay_port"
        if harbor >= NAVIGABILITY_HIGH_HARBOR_THRESHOLD:
            return "harbor_port"
        if score >= PORT_SITE_THRESHOLD:
            return "coastal_port"
        return "none"

    expected_by_id: dict[int, dict[str, Any]] = {}
    candidate_ids: set[int] = set()
    protected_sum = 0.0
    mouth_sum = 0.0
    strait_sum = 0.0
    suitability_sum = 0.0
    for cell_id, cell in cells_by_id.items():
        try:
            adjacent_marine = marine_neighbors(cell)
            bay = protected_bay(cell, adjacent_marine)
            mouth = river_mouth(cell, adjacent_marine)
            strait = strait_access(cell, adjacent_marine)
            score = suitability(cell, bay, mouth, strait)
            harbor = clamp(float(cell.get("harbor_suitability_index", 0.0)))
            raw_type = site_type(bay, mouth, strait, harbor, score)
            severe_ice = (
                float(cell.get("ice_thickness_m", 0.0)) >= 80.0
                or str(cell.get("biome", "")) == "ice_cap"
            )
        except (TypeError, ValueError):
            return failure
        selected = not bool(cell.get("is_water", False)) and (
            (score >= PORT_SITE_THRESHOLD and not severe_ice)
            or cell_id in port_settlement_cell_ids
        )
        expected_by_id[cell_id] = {
            "bay": round(bay, 6),
            "mouth": round(mouth, 6),
            "strait": round(strait, 6),
            "suitability": round(score, 6),
            "type": raw_type if selected and raw_type != "none" else "none",
            "site_id": -1,
            "selected": selected,
            "severe_ice": severe_ice,
        }
        if selected:
            candidate_ids.add(cell_id)
        protected_sum += bay
        mouth_sum += mouth
        strait_sum += strait
        suitability_sum += score

    expected_sites: list[dict[str, Any]] = []
    for cell_id in sorted(candidate_ids):
        cell = cells_by_id[cell_id]
        expected = expected_by_id[cell_id]
        site_id = len(expected_sites)
        expected["site_id"] = site_id
        if expected["type"] == "none":
            expected["type"] = "port_settlement"
        local_settlements = settlements_by_cell.get(cell_id, [])
        settlement_ids = sorted(
            int(settlement.get("id", -1))
            for settlement in local_settlements
            if int(settlement.get("id", -1)) >= 0
        )
        port_settlement_ids = sorted(
            int(settlement.get("id", -1))
            for settlement in local_settlements
            if str(settlement.get("type", "")) == "port"
            and int(settlement.get("id", -1)) >= 0
        )
        route_ids = sorted(
            {
                route_id
                for settlement_id in settlement_ids
                for route_id in routes_by_settlement.get(settlement_id, set())
            }
        )
        adjacent_marine = marine_neighbors(cell)
        waterway_ids = {int(cell.get("navigable_waterway_id", -1))}
        for raw_neighbor_id in cell.get("neighbors", []):
            neighbor = cells_by_id.get(int(raw_neighbor_id))
            if neighbor is not None:
                waterway_ids.add(int(neighbor.get("navigable_waterway_id", -1)))
        harbor = float(cell.get("harbor_suitability_index", 0.0))
        expected_sites.append(
            {
                "id": site_id,
                "cell_id": cell_id,
                "site_type": expected["type"],
                "area_km2": round(
                    max(0.0, float(cell.get("area_km2", 0.0))), 6
                ),
                "latitude_deg": round(float(cell.get("lat_deg", 0.0)), 6),
                "longitude_deg": round(float(cell.get("lon_deg", 0.0)), 6),
                "port_suitability_index": expected["suitability"],
                "protected_bay_index": expected["bay"],
                "river_mouth_port_index": expected["mouth"],
                "strait_access_index": expected["strait"],
                "harbor_suitability_index": round(harbor, 6),
                "navigability_index": round(
                    float(cell.get("navigability_index", 0.0)), 6
                ),
                "settlement_ids": settlement_ids,
                "port_settlement_ids": port_settlement_ids,
                "route_ids": route_ids,
                "marine_region_ids": sorted(
                    {
                        int(neighbor.get("marine_region_id", -1))
                        for neighbor in adjacent_marine
                        if int(neighbor.get("marine_region_id", -1)) >= 0
                    }
                ),
                "marine_chokepoint_ids": sorted(
                    {
                        int(neighbor.get("marine_chokepoint_id", -1))
                        for neighbor in adjacent_marine
                        if int(neighbor.get("marine_chokepoint_id", -1)) >= 0
                    }
                ),
                "navigable_waterway_ids": sorted(
                    value for value in waterway_ids if value >= 0
                ),
                "landform": str(cell.get("landform", "unknown")),
                "biome": str(cell.get("biome", "unknown")),
                "water_body_type": str(
                    cell.get("water_body_type", "land")
                ),
                "is_river": bool(cell.get("is_river", False)),
                "selected_by_port_settlement": bool(port_settlement_ids),
                "selected_by_suitability": (
                    harbor >= NAVIGABILITY_HIGH_HARBOR_THRESHOLD
                    or expected["suitability"] >= PORT_SITE_THRESHOLD
                )
                and not bool(expected["severe_ice"]),
            }
        )

    field_map = {
        "protected_bay_index": "bay",
        "river_mouth_port_index": "mouth",
        "strait_access_index": "strait",
        "port_suitability_index": "suitability",
    }
    for cell_id, expected in expected_by_id.items():
        cell = cells_by_id[cell_id]
        try:
            if (
                any(
                    abs(float(cell.get(field, math.inf)) - float(expected[key]))
                    > 1.0e-9
                    for field, key in field_map.items()
                )
                or str(cell.get("port_site_type", "")) != expected["type"]
                or int(cell.get("port_site_id", -2)) != expected["site_id"]
            ):
                return failure
        except (TypeError, ValueError):
            return failure
    if len(sites) != len(expected_sites):
        return failure
    for actual, expected in zip(sites, expected_sites):
        if not isinstance(actual, dict) or any(
            actual.get(key) != value for key, value in expected.items()
        ):
            return failure
    if (
        int(model.get("candidate_cell_count", -1)) != len(candidate_ids)
        or int(model.get("site_count", -1)) != len(expected_sites)
    ):
        return failure

    type_counts = Counter(site["site_type"] for site in expected_sites)
    count = len(cells_by_id)
    if count <= 0:
        return failure
    expected_summary = {
        "port_site_model": PORT_SITE_MODEL,
        "port_site_count": len(expected_sites),
        "port_candidate_cell_count": len(candidate_ids),
        "port_site_total_area_km2": round(
            sum(site["area_km2"] for site in expected_sites), 6
        ),
        "mean_port_suitability_index": round(suitability_sum / count, 6),
        "mean_protected_bay_index": round(protected_sum / count, 6),
        "mean_river_mouth_port_index": round(mouth_sum / count, 6),
        "mean_strait_access_index": round(strait_sum / count, 6),
        "port_settlement_count": sum(
            str(settlement.get("type", "")) == "port"
            for local_settlements in settlements_by_cell.values()
            for settlement in local_settlements
        ),
        "port_settlement_with_site_count": sum(
            str(settlement.get("type", "")) == "port"
            and int(settlement.get("cell_id", -1)) in candidate_ids
            for local_settlements in settlements_by_cell.values()
            for settlement in local_settlements
        ),
        "protected_bay_port_site_count": type_counts.get(
            "protected_bay_port", 0
        ),
        "river_mouth_port_site_count": type_counts.get("river_mouth_port", 0),
        "strait_port_site_count": type_counts.get("strait_port", 0),
        "port_site_type_counts": dict(sorted(type_counts.items())),
    }
    if any(summary.get(key) != value for key, value in expected_summary.items()):
        return failure
    return []

def _validate_route_corridors(
    payload: dict[str, Any],
    summary: dict[str, Any],
    cells_by_id: dict[int, dict[str, Any]],
) -> list[str]:
    """Replay feature fields, weighted Dijkstra paths, assignment, and records."""

    failure = ["route corridor model or causal replay invalid"]
    model = payload.get("route_corridor_model", {})
    corridors = payload.get("route_corridors", [])
    routes = payload.get("routes", [])
    settlements = payload.get("settlements", [])
    radius_km = configured_planet_radius_km(payload)
    try:
        metadata_invalid = (
            not isinstance(model, dict)
            or not isinstance(corridors, list)
            or not isinstance(routes, list)
            or not isinstance(settlements, list)
            or model.get("model_type") != ROUTE_CORRIDOR_MODEL
            or model.get("source_navigability_model") != NAVIGABILITY_MODEL
            or model.get("source_port_model") != PORT_SITE_MODEL
            or model.get("source_aquifer_model") != AQUIFER_RESOURCE_MODEL
            or model.get("domain")
            != "all_cells_with_one_path_per_valid_route"
            or model.get("mountain_pass_model")
            != "neighbor_saddle_convergence_landform_relief_elevation_ice_v1"
            or model.get("river_valley_model")
            != "flow_runoff_river_landform_relief_navigability_ice_v1"
            or model.get("coastal_model")
            != "marine_or_coastal_contact_navigability_harbor_port_depth_relief_v1"
            or model.get("oasis_model")
            != "aridity_water_recharge_aquifer_soil_fertility_settlement_ice_v1"
            or model.get("movement_cost_model")
            != "directed_distance_terrain_water_route_type_feature_support_v1"
            or model.get("path_model")
            != "strict_improvement_dijkstra_cost_then_cell_id_heap_v1"
            or model.get("corridor_classification_model")
            != "route_type_preference_then_feature_count_lexical_tie_v1"
            or model.get("cell_assignment_model")
            != "maximum_membership_with_later_route_winning_equal_ties_v1"
            or model.get("record_order")
            != "ascending_route_id_for_valid_endpoints_and_paths"
            or abs(float(model.get("planet_radius_km", -1.0)) - radius_km)
            > 1.0e-9
            or abs(
                float(model.get("feature_threshold", -1.0))
                - ROUTE_FEATURE_THRESHOLD
            )
            > 1.0e-12
            or model.get("threshold_semantics")
            != "serialized_feature_indices"
            or model.get("deterministic") is not True
            or model.get("model_limitation")
            != "diagnostic_static_corridors_without_capacity_congestion_seasonality_construction_cost_network_equilibrium_or_multimodal_scheduling"
            or summary.get("route_corridor_model") != ROUTE_CORRIDOR_MODEL
        )
    except (TypeError, ValueError):
        return failure
    if metadata_invalid:
        return failure

    def clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
        return max(lower, min(upper, value))

    def distance_km(first: dict[str, Any], second: dict[str, Any]) -> float:
        first_lat = math.radians(float(first.get("lat_deg", 0.0)))
        first_lon = math.radians(float(first.get("lon_deg", 0.0)))
        second_lat = math.radians(float(second.get("lat_deg", 0.0)))
        second_lon = math.radians(float(second.get("lon_deg", 0.0)))
        delta_lat = second_lat - first_lat
        delta_lon = second_lon - first_lon
        sin_lat = math.sin(delta_lat * 0.5)
        sin_lon = math.sin(delta_lon * 0.5)
        haversine = (
            sin_lat * sin_lat
            + math.cos(first_lat) * math.cos(second_lat) * sin_lon * sin_lon
        )
        return max(
            0.001,
            radius_km
            * 2.0
            * math.asin(min(1.0, math.sqrt(max(0.0, haversine)))),
        )

    def marine_neighbors(cell: dict[str, Any]) -> list[dict[str, Any]]:
        raw_neighbors = cell.get("neighbors", [])
        if not isinstance(raw_neighbors, list):
            raise ValueError("neighbors must be a list")
        return [
            neighbor
            for raw_neighbor_id in raw_neighbors
            if (neighbor := cells_by_id.get(int(raw_neighbor_id))) is not None
            and str(neighbor.get("water_body_type", "land"))
            in NAVIGABILITY_MARINE_WATER_TYPES
        ]

    def land_neighbors(cell: dict[str, Any]) -> list[dict[str, Any]]:
        raw_neighbors = cell.get("neighbors", [])
        if not isinstance(raw_neighbors, list):
            raise ValueError("neighbors must be a list")
        return [
            neighbor
            for raw_neighbor_id in raw_neighbors
            if (neighbor := cells_by_id.get(int(raw_neighbor_id))) is not None
            and not bool(neighbor.get("is_water", False))
        ]

    def is_coastal(cell: dict[str, Any]) -> bool:
        return (
            str(cell.get("water_body_type", "land"))
            in NAVIGABILITY_MARINE_WATER_TYPES
            or bool(marine_neighbors(cell))
        )

    settlements_by_id = {
        int(settlement.get("id", -1)): settlement
        for settlement in settlements
        if isinstance(settlement, dict)
        and int(settlement.get("id", -1)) >= 0
    }
    if any(not isinstance(settlement, dict) for settlement in settlements):
        return failure
    route_by_id = {
        int(route.get("id", -1)): route
        for route in routes
        if isinstance(route, dict) and int(route.get("id", -1)) >= 0
    }
    if any(not isinstance(route, dict) for route in routes):
        return failure
    oasis_settlement_cell_ids = {
        int(settlement.get("cell_id", -1))
        for settlement in settlements
        if str(settlement.get("type", "")) == "oasis"
        and int(settlement.get("cell_id", -1)) >= 0
    }
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

    def mountain_pass(cell: dict[str, Any]) -> float:
        if bool(cell.get("is_water", False)):
            return 0.0
        elevation = float(cell.get("elevation_m", 0.0))
        neighbors = land_neighbors(cell)
        if not neighbors:
            return 0.0
        elevations = [
            float(neighbor.get("elevation_m", 0.0)) for neighbor in neighbors
        ]
        high_neighbors = [value for value in elevations if value >= 900.0]
        landform = str(cell.get("landform", ""))
        context = max(
            clamp((max(elevations, default=elevation) - 700.0) / 2300.0),
            clamp(float(cell.get("boundary_convergent", 0.0)) * 1.9),
            0.68 if landform in ROUTE_MOUNTAIN_LANDFORMS else 0.0,
        )
        if context <= 0.05 and not high_neighbors:
            return 0.0
        high_mean = (
            sum(high_neighbors) / len(high_neighbors)
            if high_neighbors
            else max(elevations)
        )
        saddle_gap = clamp((high_mean - elevation + 260.0) / 1150.0)
        pass_elevation = clamp((elevation - 180.0) / 1700.0)
        relief_window = clamp((max(elevations) - min(elevations)) / 1900.0)
        ice_penalty = clamp(float(cell.get("ice_thickness_m", 0.0)) / 280.0)
        return clamp(
            context * 0.38
            + saddle_gap * 0.32
            + relief_window * 0.18
            + pass_elevation * 0.12
            - ice_penalty * 0.30
        )

    def river_valley(cell: dict[str, Any]) -> float:
        if bool(cell.get("is_water", False)) and str(
            cell.get("water_body_type", "land")
        ) in NAVIGABILITY_MARINE_WATER_TYPES:
            return 0.0
        landform = str(cell.get("landform", ""))
        flow = clamp(
            float(cell.get("flow_accumulation", 0.0)) / max(1.0, max_flow)
        )
        runoff = clamp(float(cell.get("runoff_mm_y", 0.0)) / 850.0)
        river = 0.34 if bool(cell.get("is_river", False)) else 0.0
        valley = 0.28 if landform in ROUTE_RIVER_VALLEY_LANDFORMS else 0.0
        low_relief = clamp(
            1.0 - abs(float(cell.get("elevation_m", 0.0))) / 1900.0
        )
        navigability = clamp(
            float(cell.get("river_navigability_index", 0.0))
        )
        ice_penalty = clamp(float(cell.get("ice_thickness_m", 0.0)) / 260.0)
        return clamp(
            flow * 0.22
            + runoff * 0.14
            + river
            + valley
            + low_relief * 0.12
            + navigability * 0.16
            - ice_penalty * 0.24
        )

    def coastal(cell: dict[str, Any]) -> float:
        water_body = str(cell.get("water_body_type", "land"))
        adjacent_marine = marine_neighbors(cell)
        if water_body in NAVIGABILITY_MARINE_WATER_TYPES:
            land_contact = clamp(len(land_neighbors(cell)) / 4.0)
            shelf = (
                0.25
                if water_body in {"continental_shelf", "inland_sea"}
                else 0.10
            )
            navigability = clamp(
                float(cell.get("coastal_navigability_index", 0.0))
            )
            chokepoint = clamp(
                float(cell.get("transport_chokepoint_index", 0.0))
            )
            depth_access = clamp(
                1.0 - float(cell.get("water_depth_m", 0.0)) / 700.0
            )
            return clamp(
                shelf
                + land_contact * 0.22
                + navigability * 0.30
                + chokepoint * 0.18
                + depth_access * 0.15
            )
        if not adjacent_marine:
            return 0.0
        marine_contact = clamp(len(adjacent_marine) / 3.0)
        low_relief = clamp(
            1.0 - abs(float(cell.get("elevation_m", 0.0))) / 1200.0
        )
        harbor = clamp(float(cell.get("harbor_suitability_index", 0.0)))
        port = clamp(float(cell.get("port_suitability_index", 0.0)))
        navigability = clamp(
            float(cell.get("coastal_navigability_index", 0.0))
        )
        return clamp(
            marine_contact * 0.24
            + low_relief * 0.18
            + harbor * 0.20
            + port * 0.18
            + navigability * 0.20
        )

    def oasis(cell: dict[str, Any]) -> float:
        if bool(cell.get("is_water", False)):
            return 0.0
        biome = str(cell.get("biome", ""))
        aridity = clamp(float(cell.get("seasonal_aridity_index", 0.0)))
        arid_context = max(
            aridity, 0.72 if biome in ROUTE_DESERT_BIOMES else 0.0
        )
        cell_id = int(cell.get("id", -1))
        if arid_context < 0.45 and cell_id not in oasis_settlement_cell_ids:
            return 0.0
        water_access = max(
            0.85 if bool(cell.get("is_river", False)) else 0.0,
            0.70 if bool(cell.get("is_lake", False)) else 0.0,
            clamp(float(cell.get("runoff_mm_y", 0.0)) / 220.0),
            clamp(float(cell.get("groundwater_recharge_mm_y", 0.0)) / 180.0),
            clamp(float(cell.get("aquifer_productivity_index", 0.0))),
            clamp(float(cell.get("soil_moisture_index", 0.0))),
        )
        fertility = clamp(float(cell.get("fertility", 0.0)))
        settlement = 0.25 if cell_id in oasis_settlement_cell_ids else 0.0
        return clamp(
            arid_context * 0.32
            + water_access * 0.43
            + fertility * 0.12
            + settlement
            - clamp(float(cell.get("ice_thickness_m", 0.0)) / 200.0)
        )

    expected_by_id: dict[int, dict[str, Any]] = {}
    for cell_id, cell in cells_by_id.items():
        try:
            expected_by_id[cell_id] = {
                "mountain": round(mountain_pass(cell), 6),
                "river": round(river_valley(cell), 6),
                "coastal": round(coastal(cell), 6),
                "oasis": round(oasis(cell), 6),
                "corridor": 0.0,
                "type": "none",
                "corridor_id": -1,
            }
        except (TypeError, ValueError):
            return failure

    def feature_values(cell_id: int) -> dict[str, float]:
        expected = expected_by_id[cell_id]
        return {
            "mountain_pass_corridor": float(expected["mountain"]),
            "river_valley_corridor": float(expected["river"]),
            "coastal_corridor": float(expected["coastal"]),
            "oasis_corridor": float(expected["oasis"]),
        }

    def movement_cost(
        current_id: int, neighbor_id: int, route_type: str
    ) -> float:
        current = cells_by_id[current_id]
        neighbor = cells_by_id[neighbor_id]
        distance = distance_km(current, neighbor)
        water_body = str(neighbor.get("water_body_type", "land"))
        is_water = bool(neighbor.get("is_water", False))
        elevation_delta = abs(
            float(neighbor.get("elevation_m", 0.0))
            - float(current.get("elevation_m", 0.0))
        )
        slope = clamp(elevation_delta / 2000.0)
        ice = clamp(float(neighbor.get("ice_thickness_m", 0.0)) / 320.0)
        aridity = clamp(float(neighbor.get("seasonal_aridity_index", 0.0)))
        mountain = clamp(
            (float(neighbor.get("elevation_m", 0.0)) - 1000.0) / 2200.0
        )
        features = feature_values(neighbor_id)
        if route_type == "coastal_sea":
            support = max(
                features["coastal_corridor"],
                float(neighbor.get("navigability_index", 0.0)),
            )
            water_penalty = (
                0.08
                if water_body in NAVIGABILITY_MARINE_WATER_TYPES
                else 0.72
                if is_coastal(neighbor)
                else 1.80
            )
        elif route_type == "river_corridor":
            support = max(
                features["river_valley_corridor"],
                float(neighbor.get("river_navigability_index", 0.0)),
            )
            water_penalty = (
                1.45
                if water_body in NAVIGABILITY_MARINE_WATER_TYPES
                else 0.18
                if bool(neighbor.get("is_river", False))
                else 0.42
            )
        elif route_type == "mountain_pass":
            support = max(
                features["mountain_pass_corridor"],
                features["river_valley_corridor"] * 0.45,
            )
            water_penalty = 1.70 if is_water else 0.20
        else:
            support = max(
                features["river_valley_corridor"] * 0.72,
                features["coastal_corridor"] * 0.62,
                features["oasis_corridor"] * 0.72,
                features["mountain_pass_corridor"] * 0.46,
            )
            water_penalty = (
                1.65
                if water_body in NAVIGABILITY_MARINE_WATER_TYPES
                else 0.20
                if bool(neighbor.get("is_river", False))
                else 0.34
            )
        terrain = (
            0.64
            + slope * 0.42
            + ice * 0.55
            + aridity * 0.18
            + mountain * 0.20
            + water_penalty
            - support * 0.50
        )
        return distance * max(0.12, terrain)

    def shortest_path(start: int, end: int, route_type: str) -> list[int]:
        if start == end and start in cells_by_id:
            return [start]
        if start not in cells_by_id or end not in cells_by_id:
            return []
        queue: list[tuple[float, int]] = [(0.0, start)]
        best_cost = {start: 0.0}
        previous: dict[int, int] = {}
        visited: set[int] = set()
        while queue:
            cost, cell_id = heapq.heappop(queue)
            if cell_id in visited:
                continue
            visited.add(cell_id)
            if cell_id == end:
                break
            raw_neighbors = cells_by_id[cell_id].get("neighbors", [])
            if not isinstance(raw_neighbors, list):
                return []
            for raw_neighbor_id in raw_neighbors:
                neighbor_id = int(raw_neighbor_id)
                if neighbor_id not in cells_by_id:
                    continue
                next_cost = cost + movement_cost(
                    cell_id, neighbor_id, route_type
                )
                if next_cost < best_cost.get(neighbor_id, math.inf):
                    best_cost[neighbor_id] = next_cost
                    previous[neighbor_id] = cell_id
                    heapq.heappush(queue, (next_cost, neighbor_id))
        if end not in best_cost:
            return []
        path = [end]
        while path[-1] != start:
            parent = previous.get(path[-1])
            if parent is None:
                return []
            path.append(parent)
        return list(reversed(path))

    def corridor_type(path: list[int], route_type: str) -> str:
        counts = {
            name: sum(
                feature_values(cell_id)[name] >= ROUTE_FEATURE_THRESHOLD
                for cell_id in path
            )
            for name in (
                "mountain_pass_corridor",
                "river_valley_corridor",
                "coastal_corridor",
                "oasis_corridor",
            )
        }
        if route_type == "coastal_sea" and counts["coastal_corridor"] > 0:
            return "coastal_corridor"
        if route_type == "river_corridor" and counts["river_valley_corridor"] > 0:
            return "river_valley_corridor"
        if route_type == "mountain_pass" and counts["mountain_pass_corridor"] > 0:
            return "mountain_pass_corridor"
        best_type, best_count = sorted(
            counts.items(), key=lambda item: (-item[1], item[0])
        )[0]
        return best_type if best_count > 0 else "overland_corridor"

    expected_route_fields: dict[int, dict[str, Any]] = {}
    expected_corridors: list[dict[str, Any]] = []
    for route_id in sorted(route_by_id):
        route = route_by_id[route_id]
        source = settlements_by_id.get(int(route.get("from", -1)))
        target = settlements_by_id.get(int(route.get("to", -1)))
        if source is None or target is None:
            expected_route_fields[route_id] = {
                "route_corridor_id": -1,
                "route_corridor_type": "none",
                "path_cell_ids": [],
            }
            continue
        start = int(source.get("cell_id", -1))
        end = int(target.get("cell_id", -1))
        route_type = str(route.get("type", "overland"))
        path = shortest_path(start, end, route_type)
        if not path:
            expected_route_fields[route_id] = {
                "route_corridor_id": -1,
                "route_corridor_type": "none",
                "path_cell_ids": [],
            }
            continue
        corridor_id = len(expected_corridors)
        selected_type = corridor_type(path, route_type)
        for cell_id in path:
            support = max(feature_values(cell_id).values())
            membership = clamp(0.35 + support * 0.65)
            if membership >= float(expected_by_id[cell_id]["corridor"]):
                expected_by_id[cell_id]["corridor"] = round(membership, 6)
                expected_by_id[cell_id]["type"] = selected_type
                expected_by_id[cell_id]["corridor_id"] = corridor_id
        expected_route_fields[route_id] = {
            "route_corridor_id": corridor_id,
            "route_corridor_type": selected_type,
            "path_cell_ids": path,
        }
        path_length = sum(
            distance_km(cells_by_id[first], cells_by_id[second])
            for first, second in zip(path, path[1:])
        )
        straight_distance = max(0.001, float(route.get("distance_km", 0.0)))
        feature_counts = {
            name: sum(
                feature_values(cell_id)[name] >= ROUTE_FEATURE_THRESHOLD
                for cell_id in path
            )
            for name in (
                "mountain_pass_corridor",
                "river_valley_corridor",
                "coastal_corridor",
                "oasis_corridor",
            )
        }
        named_count = sum(
            any(
                value >= ROUTE_FEATURE_THRESHOLD
                for value in feature_values(cell_id).values()
            )
            for cell_id in path
        )
        corridor_values = [
            float(expected_by_id[cell_id]["corridor"]) for cell_id in path
        ]
        mountain_values = [feature_values(cell_id)["mountain_pass_corridor"] for cell_id in path]
        river_values = [feature_values(cell_id)["river_valley_corridor"] for cell_id in path]
        coastal_values = [feature_values(cell_id)["coastal_corridor"] for cell_id in path]
        oasis_values = [feature_values(cell_id)["oasis_corridor"] for cell_id in path]
        expected_corridors.append(
            {
                "id": corridor_id,
                "route_id": route_id,
                "route_type": route_type,
                "corridor_type": selected_type,
                "from_settlement_id": int(route.get("from", -1)),
                "to_settlement_id": int(route.get("to", -1)),
                "start_cell_id": start,
                "end_cell_id": end,
                "cell_count": len(path),
                "cell_ids": path,
                "path_length_km": round(path_length, 6),
                "straight_distance_km": round(straight_distance, 6),
                "detour_ratio": round(path_length / straight_distance, 6),
                "mean_route_corridor_index": round(
                    sum(corridor_values) / len(corridor_values), 6
                ),
                "max_route_corridor_index": round(max(corridor_values), 6),
                "mean_mountain_pass_route_index": round(
                    sum(mountain_values) / len(mountain_values), 6
                ),
                "mean_river_valley_route_index": round(
                    sum(river_values) / len(river_values), 6
                ),
                "mean_coastal_route_index": round(
                    sum(coastal_values) / len(coastal_values), 6
                ),
                "mean_oasis_route_index": round(
                    sum(oasis_values) / len(oasis_values), 6
                ),
                "mountain_pass_cell_count": feature_counts[
                    "mountain_pass_corridor"
                ],
                "river_valley_cell_count": feature_counts[
                    "river_valley_corridor"
                ],
                "coastal_cell_count": feature_counts["coastal_corridor"],
                "oasis_cell_count": feature_counts["oasis_corridor"],
                "named_feature_cell_count": named_count,
                "settlement_ids": sorted(
                    {int(route.get("from", -1)), int(route.get("to", -1))}
                    - {-1}
                ),
                "region_ids": sorted(
                    {
                        int(source.get("region_id", -1)),
                        int(target.get("region_id", -1)),
                    }
                    - {-1}
                ),
                "route_ids": [route_id],
                "navigable_waterway_ids": sorted(
                    {
                        int(cells_by_id[cell_id].get("navigable_waterway_id", -1))
                        for cell_id in path
                        if int(
                            cells_by_id[cell_id].get(
                                "navigable_waterway_id", -1
                            )
                        )
                        >= 0
                    }
                ),
                "port_site_ids": sorted(
                    {
                        int(cells_by_id[cell_id].get("port_site_id", -1))
                        for cell_id in path
                        if int(cells_by_id[cell_id].get("port_site_id", -1))
                        >= 0
                    }
                ),
            }
        )

    field_map = {
        "mountain_pass_route_index": "mountain",
        "river_valley_route_index": "river",
        "coastal_route_index": "coastal",
        "oasis_route_index": "oasis",
        "route_corridor_index": "corridor",
    }
    for cell_id, expected in expected_by_id.items():
        cell = cells_by_id[cell_id]
        try:
            if (
                any(
                    abs(float(cell.get(field, math.inf)) - float(expected[key]))
                    > 1.0e-9
                    for field, key in field_map.items()
                )
                or str(cell.get("route_corridor_type", "")) != expected["type"]
                or int(cell.get("route_corridor_id", -2))
                != expected["corridor_id"]
            ):
                return failure
        except (TypeError, ValueError):
            return failure
    for route_id, expected in expected_route_fields.items():
        route = route_by_id[route_id]
        if (
            int(route.get("route_corridor_id", -2))
            != expected["route_corridor_id"]
            or str(route.get("route_corridor_type", ""))
            != expected["route_corridor_type"]
            or [int(value) for value in route.get("path_cell_ids", [])]
            != expected["path_cell_ids"]
        ):
            return failure
    if len(corridors) != len(expected_corridors):
        return failure
    for actual, expected in zip(corridors, expected_corridors):
        if not isinstance(actual, dict) or any(
            actual.get(key) != value for key, value in expected.items()
        ):
            return failure
    if (
        int(model.get("route_count", -1)) != len(route_by_id)
        or int(model.get("corridor_count", -1)) != len(expected_corridors)
    ):
        return failure

    type_counts = Counter(
        corridor["corridor_type"] for corridor in expected_corridors
    )
    cell_count = len(cells_by_id)
    if cell_count <= 0:
        return failure
    expected_summary = {
        "route_corridor_model": ROUTE_CORRIDOR_MODEL,
        "route_corridor_count": len(expected_corridors),
        "route_corridor_cell_count": sum(
            int(expected["corridor_id"]) >= 0
            for expected in expected_by_id.values()
        ),
        "route_corridor_total_path_length_km": round(
            sum(corridor["path_length_km"] for corridor in expected_corridors),
            6,
        ),
        "mean_route_corridor_index": round(
            sum(float(expected["corridor"]) for expected in expected_by_id.values())
            / cell_count,
            6,
        ),
        "mean_mountain_pass_route_index": round(
            sum(float(expected["mountain"]) for expected in expected_by_id.values())
            / cell_count,
            6,
        ),
        "mean_river_valley_route_index": round(
            sum(float(expected["river"]) for expected in expected_by_id.values())
            / cell_count,
            6,
        ),
        "mean_coastal_route_index": round(
            sum(float(expected["coastal"]) for expected in expected_by_id.values())
            / cell_count,
            6,
        ),
        "mean_oasis_route_index": round(
            sum(float(expected["oasis"]) for expected in expected_by_id.values())
            / cell_count,
            6,
        ),
        "route_feature_coverage_index": (
            round(
                sum(
                    corridor["named_feature_cell_count"] > 0
                    for corridor in expected_corridors
                )
                / len(expected_corridors),
                6,
            )
            if expected_corridors
            else 1.0
        ),
        "mountain_pass_route_corridor_count": type_counts.get(
            "mountain_pass_corridor", 0
        ),
        "river_valley_route_corridor_count": type_counts.get(
            "river_valley_corridor", 0
        ),
        "coastal_route_corridor_count": type_counts.get(
            "coastal_corridor", 0
        ),
        "oasis_route_corridor_count": type_counts.get("oasis_corridor", 0),
        "route_corridor_type_counts": dict(sorted(type_counts.items())),
    }
    if any(summary.get(key) != value for key, value in expected_summary.items()):
        return failure
    return []
