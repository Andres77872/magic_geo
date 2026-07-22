"""Port-site selection replay checks."""

from __future__ import annotations

import math
from collections import Counter
from typing import Any

from .._constants import (
    NAVIGABILITY_HIGH_HARBOR_THRESHOLD,
    NAVIGABILITY_MARINE_WATER_TYPES,
    NAVIGABILITY_MODEL,
    PORT_PROTECTED_BAY_THRESHOLD,
    PORT_RIVER_MOUTH_THRESHOLD,
    PORT_SITE_MODEL,
    PORT_SITE_THRESHOLD,
    PORT_STRAIT_ACCESS_THRESHOLD,
)


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
