"""Waterway navigability replay checks."""

from __future__ import annotations

import math
from collections import Counter
from typing import Any

from .._constants import (
    NAVIGABILITY_HIGH_HARBOR_THRESHOLD,
    NAVIGABILITY_MARINE_WATER_TYPES,
    NAVIGABILITY_MODEL,
    NAVIGABILITY_THRESHOLD,
    NAVIGABILITY_TRANSPORT_CHOKEPOINT_THRESHOLD,
    RIVER_CHANNEL_LOWLAND_FORMS,
    RIVER_CHANNEL_MORPHOLOGY_MODEL,
    RIVER_HYDRAULICS_MODEL,
)


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
