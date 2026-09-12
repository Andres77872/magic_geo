"""Unchanged historical inline navigation/port/corridor CLI checks.

Version dispatch belongs to the caller. These legacy diagnostics retain their
original arithmetic, error messages and ordering, including rounded checks.
"""
from __future__ import annotations

import math
from collections import Counter
from typing import Any

from ...planet_parameters import planet_radius_km as configured_planet_radius_km
from .navigability import _validate_navigability
from .ports import _validate_port_sites
from .corridors import _validate_route_corridors


def _validate_legacy_navigation_port_blocks(
    *, payload, summary, cells_payload, cells_by_id, failures,
    marine_water_types, marine_region_by_id, marine_chokepoint_by_id,
) -> None:
    failures.extend(_validate_navigability(payload, summary, cells_by_id))

    navigable_waterways = payload.get("navigable_waterways", [])
    navigability_summary_keys = {
        "navigability_model",
        "navigable_cell_count",
        "navigable_waterway_count",
        "navigable_waterway_total_area_km2",
        "mean_navigability_index",
        "mean_river_navigability_index",
        "mean_coastal_navigability_index",
        "mean_harbor_suitability_index",
        "mean_transport_chokepoint_index",
        "high_harbor_suitability_cell_count",
        "transport_chokepoint_cell_count",
        "navigability_class_counts",
    }
    if not navigability_summary_keys.issubset(summary):
        failures.append("navigability summary metrics missing")
    if not isinstance(navigable_waterways, list):
        failures.append("navigable_waterways missing")
        navigable_waterways = []
    navigability_cell_keys = {
        "river_navigability_index",
        "coastal_navigability_index",
        "harbor_suitability_index",
        "transport_chokepoint_index",
        "navigability_index",
        "navigability_class",
        "navigable_waterway_id",
    }
    if cells_payload and not navigability_cell_keys.issubset(cells_payload[0]):
        failures.append("navigability cell fields missing")
    allowed_navigability_classes = {
        "non_navigable",
        "river_corridor",
        "coastal_corridor",
        "river_mouth",
        "harbor",
        "transport_chokepoint",
    }
    navigable_candidate_ids: set[int] = set()
    navigability_class_counts: dict[str, int] = {}
    navigability_sum = 0.0
    river_navigability_sum = 0.0
    coastal_navigability_sum = 0.0
    harbor_suitability_sum = 0.0
    transport_chokepoint_sum = 0.0
    navigable_candidate_area = 0.0
    high_harbor_count = 0
    transport_chokepoint_count = 0
    navigability_cell_invalid = False
    for cell in cells_payload:
        cell_id = int(cell.get("id", -1))
        river = float(cell.get("river_navigability_index", -1.0))
        coastal = float(cell.get("coastal_navigability_index", -1.0))
        harbor = float(cell.get("harbor_suitability_index", -1.0))
        chokepoint = float(cell.get("transport_chokepoint_index", -1.0))
        navigability = float(cell.get("navigability_index", -1.0))
        nav_class = str(cell.get("navigability_class", ""))
        waterway_id = int(cell.get("navigable_waterway_id", -2))
        if navigability >= 0.52:
            navigable_candidate_ids.add(cell_id)
            navigable_candidate_area += max(0.0, float(cell.get("area_km2", 0.0)))
        if harbor >= 0.62:
            high_harbor_count += 1
        if chokepoint >= 0.55:
            transport_chokepoint_count += 1
        navigability_class_counts[nav_class] = navigability_class_counts.get(nav_class, 0) + 1
        navigability_sum += navigability
        river_navigability_sum += river
        coastal_navigability_sum += coastal
        harbor_suitability_sum += harbor
        transport_chokepoint_sum += chokepoint
        if (
            not 0.0 <= river <= 1.0
            or not 0.0 <= coastal <= 1.0
            or not 0.0 <= harbor <= 1.0
            or not 0.0 <= chokepoint <= 1.0
            or not 0.0 <= navigability <= 1.0
            or abs(navigability - max(river, coastal, harbor, chokepoint)) > 0.001
            or nav_class not in allowed_navigability_classes
            or waterway_id < -1
            or (bool(cell.get("is_water", False)) and harbor != 0.0)
        ):
            navigability_cell_invalid = True
            break
    if navigability_cell_invalid:
        failures.append("navigability cell fields invalid")
    if int(summary.get("navigable_waterway_count", -1)) != len(navigable_waterways):
        failures.append("navigable_waterway_count does not match navigable_waterways length")
    if int(summary.get("navigable_cell_count", -1)) != len(navigable_candidate_ids):
        failures.append("navigable_cell_count does not match candidate cells")
    if int(summary.get("high_harbor_suitability_cell_count", -1)) != high_harbor_count:
        failures.append("high_harbor_suitability_cell_count does not match cells")
    if int(summary.get("transport_chokepoint_cell_count", -1)) != transport_chokepoint_count:
        failures.append("transport_chokepoint_cell_count does not match cells")
    if navigability_class_counts != {str(key): int(value) for key, value in summary.get("navigability_class_counts", {}).items()}:
        failures.append("navigability_class_counts does not match cells")
    cell_count_divisor = float(len(cells_payload)) if cells_payload else 1.0
    expected_navigability_means = {
        "mean_navigability_index": navigability_sum / cell_count_divisor,
        "mean_river_navigability_index": river_navigability_sum / cell_count_divisor,
        "mean_coastal_navigability_index": coastal_navigability_sum / cell_count_divisor,
        "mean_harbor_suitability_index": harbor_suitability_sum / cell_count_divisor,
        "mean_transport_chokepoint_index": transport_chokepoint_sum / cell_count_divisor,
    }
    for key, expected in expected_navigability_means.items():
        if abs(float(summary.get(key, 0.0)) - expected) > 0.001:
            failures.append(f"{key} does not match cells")
            break
    if abs(float(summary.get("navigable_waterway_total_area_km2", 0.0)) - navigable_candidate_area) > max(
        0.001,
        navigable_candidate_area * 0.0001,
    ):
        failures.append("navigable_waterway_total_area_km2 does not match candidate cells")

    local_settlements_for_navigation = payload.get("settlements", [])
    local_routes_for_navigation = payload.get("routes", [])
    local_settlements_for_navigation = (
        local_settlements_for_navigation if isinstance(local_settlements_for_navigation, list) else []
    )
    local_routes_for_navigation = local_routes_for_navigation if isinstance(local_routes_for_navigation, list) else []
    settlement_by_id_for_navigation = {
        int(settlement.get("id", -1)): settlement
        for settlement in local_settlements_for_navigation
        if isinstance(settlement, dict)
    }
    route_by_id_for_navigation = {
        int(route.get("id", -1)): route for route in local_routes_for_navigation if isinstance(route, dict)
    }
    navigable_waterway_keys = {
        "id",
        "waterway_type",
        "cell_count",
        "cell_ids",
        "area_km2",
        "mean_navigability_index",
        "mean_river_navigability_index",
        "mean_coastal_navigability_index",
        "max_harbor_suitability_index",
        "transport_chokepoint_cell_count",
        "settlement_ids",
        "route_ids",
        "marine_region_ids",
        "watershed_ids",
    }
    if navigable_waterways and not navigable_waterway_keys.issubset(navigable_waterways[0]):
        failures.append("navigable waterway fields missing")
    allowed_waterway_types = {
        "transport_chokepoint",
        "river_mouth_corridor",
        "harbor_cluster",
        "river_corridor",
        "coastal_corridor",
    }
    navigable_waterway_invalid = False
    assigned_navigable_ids: set[int] = set()
    navigable_waterway_area = 0.0
    waterway_ids_seen: set[int] = set()
    for index, waterway in enumerate(navigable_waterways):
        waterway_id = int(waterway.get("id", -1))
        waterway_ids_seen.add(waterway_id)
        cell_ids_for_waterway = waterway.get("cell_ids", [])
        settlement_ids_for_waterway = waterway.get("settlement_ids", [])
        route_ids_for_waterway = waterway.get("route_ids", [])
        marine_region_ids_for_waterway = waterway.get("marine_region_ids", [])
        watershed_ids_for_waterway = waterway.get("watershed_ids", [])
        if (
            not isinstance(cell_ids_for_waterway, list)
            or not isinstance(settlement_ids_for_waterway, list)
            or not isinstance(route_ids_for_waterway, list)
            or not isinstance(marine_region_ids_for_waterway, list)
            or not isinstance(watershed_ids_for_waterway, list)
        ):
            navigable_waterway_invalid = True
            break
        member_ids = [int(cell_id) for cell_id in cell_ids_for_waterway]
        group_cells = [cells_by_id.get(cell_id) for cell_id in member_ids]
        if any(cell is None for cell in group_cells) or not group_cells:
            navigable_waterway_invalid = True
            break
        valid_group_cells = [cell for cell in group_cells if cell is not None]
        member_id_set = {int(cell.get("id", -1)) for cell in valid_group_cells}
        assigned_navigable_ids.update(member_id_set)
        area_sum = sum(max(0.0, float(cell.get("area_km2", 0.0))) for cell in valid_group_cells)
        navigability_group_sum = sum(float(cell.get("navigability_index", 0.0)) for cell in valid_group_cells)
        river_group_sum = sum(float(cell.get("river_navigability_index", 0.0)) for cell in valid_group_cells)
        coastal_group_sum = sum(float(cell.get("coastal_navigability_index", 0.0)) for cell in valid_group_cells)
        harbor_group_max = max((float(cell.get("harbor_suitability_index", 0.0)) for cell in valid_group_cells), default=0.0)
        chokepoint_group_count = sum(
            1 for cell in valid_group_cells if float(cell.get("transport_chokepoint_index", 0.0)) >= 0.55
        )
        settlement_ids = [int(settlement_id) for settlement_id in settlement_ids_for_waterway]
        route_ids = [int(route_id) for route_id in route_ids_for_waterway]
        marine_region_ids_for_record = [int(region_id) for region_id in marine_region_ids_for_waterway]
        watershed_ids_for_record = [int(watershed_id) for watershed_id in watershed_ids_for_waterway]
        expected_marine_region_ids = sorted(
            {
                int(cell.get("marine_region_id", -1))
                for cell in valid_group_cells
                if int(cell.get("marine_region_id", -1)) >= 0
            }
        )
        expected_watershed_ids = sorted(
            {int(cell.get("basin_id", -1)) for cell in valid_group_cells if int(cell.get("basin_id", -1)) >= 0}
        )
        settlement_links_valid = all(
            settlement_id in settlement_by_id_for_navigation
            and int(settlement_by_id_for_navigation[settlement_id].get("cell_id", -1)) in member_id_set
            for settlement_id in settlement_ids
        )
        route_links_valid = all(
            route_id in route_by_id_for_navigation
            and (
                int(route_by_id_for_navigation[route_id].get("from", -1)) in settlement_ids
                or int(route_by_id_for_navigation[route_id].get("to", -1)) in settlement_ids
            )
            for route_id in route_ids
        )
        navigable_waterway_area += float(waterway.get("area_km2", 0.0))
        group_count = len(valid_group_cells)
        if (
            waterway_id != index
            or waterway_id < 0
            or str(waterway.get("waterway_type", "")) not in allowed_waterway_types
            or int(waterway.get("cell_count", -1)) != group_count
            or len(member_ids) != len(member_id_set)
            or not member_id_set.issubset(navigable_candidate_ids)
            or any(int(cell.get("navigable_waterway_id", -1)) != waterway_id for cell in valid_group_cells)
            or abs(float(waterway.get("area_km2", 0.0)) - area_sum) > max(0.001, area_sum * 0.0001)
            or abs(float(waterway.get("mean_navigability_index", 0.0)) - navigability_group_sum / group_count) > 0.001
            or abs(float(waterway.get("mean_river_navigability_index", 0.0)) - river_group_sum / group_count) > 0.001
            or abs(float(waterway.get("mean_coastal_navigability_index", 0.0)) - coastal_group_sum / group_count) > 0.001
            or abs(float(waterway.get("max_harbor_suitability_index", 0.0)) - harbor_group_max) > 0.001
            or int(waterway.get("transport_chokepoint_cell_count", -1)) != chokepoint_group_count
            or marine_region_ids_for_record != expected_marine_region_ids
            or watershed_ids_for_record != expected_watershed_ids
            or not settlement_links_valid
            or not route_links_valid
        ):
            navigable_waterway_invalid = True
            break
    if len(waterway_ids_seen) != len(navigable_waterways):
        failures.append("navigable waterway ids are not unique")
    if navigable_waterway_invalid:
        failures.append("navigable waterway records invalid")
    if assigned_navigable_ids != navigable_candidate_ids:
        failures.append("navigable waterway membership does not match cells")
    if abs(float(summary.get("navigable_waterway_total_area_km2", 0.0)) - navigable_waterway_area) > max(
        0.001,
        navigable_waterway_area * 0.0001,
    ):
        failures.append("navigable_waterway_total_area_km2 does not match waterways")

    failures.extend(_validate_port_sites(payload, summary, cells_by_id))

    port_sites = payload.get("port_sites", [])
    port_site_summary_keys = {
        "port_site_model",
        "port_site_count",
        "port_candidate_cell_count",
        "port_site_total_area_km2",
        "mean_port_suitability_index",
        "mean_protected_bay_index",
        "mean_river_mouth_port_index",
        "mean_strait_access_index",
        "port_settlement_count",
        "port_settlement_with_site_count",
        "protected_bay_port_site_count",
        "river_mouth_port_site_count",
        "strait_port_site_count",
        "port_site_type_counts",
    }
    if not port_site_summary_keys.issubset(summary):
        failures.append("port site summary metrics missing")
    if not isinstance(port_sites, list):
        failures.append("port_sites missing")
        port_sites = []
    port_site_cell_keys = {
        "protected_bay_index",
        "river_mouth_port_index",
        "strait_access_index",
        "port_suitability_index",
        "port_site_type",
        "port_site_id",
    }
    if cells_payload and not port_site_cell_keys.issubset(cells_payload[0]):
        failures.append("port site cell fields missing")
    allowed_port_site_types = {
        "none",
        "protected_bay_port",
        "river_mouth_port",
        "strait_port",
        "harbor_port",
        "coastal_port",
        "port_settlement",
    }
    port_settlement_cell_ids = {
        int(settlement.get("cell_id", -1))
        for settlement in settlement_by_id_for_navigation.values()
        if str(settlement.get("type", "")) == "port"
    }
    port_candidate_ids: set[int] = set()
    assigned_port_ids: set[int] = set()
    protected_bay_sum = 0.0
    river_mouth_port_sum = 0.0
    strait_access_sum = 0.0
    port_suitability_sum = 0.0
    port_site_cell_invalid = False
    for cell in cells_payload:
        cell_id = int(cell.get("id", -1))
        protected_bay = float(cell.get("protected_bay_index", -1.0))
        river_mouth_port = float(cell.get("river_mouth_port_index", -1.0))
        strait_access = float(cell.get("strait_access_index", -1.0))
        port_suitability = float(cell.get("port_suitability_index", -1.0))
        site_type = str(cell.get("port_site_type", ""))
        site_id = int(cell.get("port_site_id", -2))
        is_water = bool(cell.get("is_water", False))
        severe_ice = float(cell.get("ice_thickness_m", 0.0)) >= 80.0 or str(cell.get("biome", "")) == "ice_cap"
        if not is_water and ((port_suitability >= 0.58 and not severe_ice) or cell_id in port_settlement_cell_ids):
            port_candidate_ids.add(cell_id)
        if site_id >= 0:
            assigned_port_ids.add(cell_id)
        protected_bay_sum += protected_bay
        river_mouth_port_sum += river_mouth_port
        strait_access_sum += strait_access
        port_suitability_sum += port_suitability
        if (
            not 0.0 <= protected_bay <= 1.0
            or not 0.0 <= river_mouth_port <= 1.0
            or not 0.0 <= strait_access <= 1.0
            or not 0.0 <= port_suitability <= 1.0
            or site_id < -1
            or site_type not in allowed_port_site_types
            or (is_water and (protected_bay != 0.0 or river_mouth_port != 0.0 or strait_access != 0.0 or port_suitability != 0.0))
            or (is_water and (site_type != "none" or site_id != -1))
            or (site_id == -1 and site_type != "none")
            or (site_id >= 0 and site_type == "none")
        ):
            port_site_cell_invalid = True
            break
    if port_site_cell_invalid:
        failures.append("port site cell fields invalid")
    if int(summary.get("port_site_count", -1)) != len(port_sites):
        failures.append("port_site_count does not match port_sites length")
    if int(summary.get("port_candidate_cell_count", -1)) != len(port_candidate_ids):
        failures.append("port_candidate_cell_count does not match candidate cells")
    expected_port_means = {
        "mean_port_suitability_index": port_suitability_sum / cell_count_divisor,
        "mean_protected_bay_index": protected_bay_sum / cell_count_divisor,
        "mean_river_mouth_port_index": river_mouth_port_sum / cell_count_divisor,
        "mean_strait_access_index": strait_access_sum / cell_count_divisor,
    }
    for key, expected in expected_port_means.items():
        if abs(float(summary.get(key, 0.0)) - expected) > 0.001:
            failures.append(f"{key} does not match cells")
            break

    port_site_keys = {
        "id",
        "cell_id",
        "site_type",
        "area_km2",
        "latitude_deg",
        "longitude_deg",
        "port_suitability_index",
        "protected_bay_index",
        "river_mouth_port_index",
        "strait_access_index",
        "harbor_suitability_index",
        "navigability_index",
        "settlement_ids",
        "port_settlement_ids",
        "route_ids",
        "marine_region_ids",
        "marine_chokepoint_ids",
        "navigable_waterway_ids",
        "landform",
        "biome",
        "water_body_type",
        "is_river",
        "selected_by_port_settlement",
        "selected_by_suitability",
    }
    if port_sites and not port_site_keys.issubset(port_sites[0]):
        failures.append("port site fields missing")
    port_site_invalid = False
    port_site_ids_seen: set[int] = set()
    duplicate_port_site_id = False
    port_type_counts: Counter[str] = Counter()
    port_site_area = 0.0
    port_settlement_count = 0
    port_settlement_with_site_count = 0
    for settlement in settlement_by_id_for_navigation.values():
        if str(settlement.get("type", "")) == "port":
            port_settlement_count += 1
            if int(settlement.get("cell_id", -1)) in port_candidate_ids:
                port_settlement_with_site_count += 1
    for index, site in enumerate(port_sites):
        site_id = int(site.get("id", -1))
        cell_id = int(site.get("cell_id", -1))
        cell = cells_by_id.get(cell_id)
        if site_id in port_site_ids_seen:
            duplicate_port_site_id = True
        port_site_ids_seen.add(site_id)
        if cell is None:
            port_site_invalid = True
            break
        settlement_ids = [int(settlement_id) for settlement_id in site.get("settlement_ids", [])]
        port_settlement_ids = [int(settlement_id) for settlement_id in site.get("port_settlement_ids", [])]
        route_ids = [int(route_id) for route_id in site.get("route_ids", [])]
        marine_region_ids_for_site = [int(region_id) for region_id in site.get("marine_region_ids", [])]
        marine_chokepoint_ids_for_site = [int(chokepoint_id) for chokepoint_id in site.get("marine_chokepoint_ids", [])]
        waterway_ids_for_site = [int(waterway_id) for waterway_id in site.get("navigable_waterway_ids", [])]
        neighbor_cells = [
            cells_by_id.get(int(neighbor_id))
            for neighbor_id in cell.get("neighbors", [])
            if cells_by_id.get(int(neighbor_id)) is not None
        ]
        expected_marine_region_ids = sorted(
            {
                int(neighbor.get("marine_region_id", -1))
                for neighbor in neighbor_cells
                if str(neighbor.get("water_body_type", "land")) in marine_water_types
                and int(neighbor.get("marine_region_id", -1)) >= 0
            }
        )
        expected_marine_chokepoint_ids = sorted(
            {
                int(neighbor.get("marine_chokepoint_id", -1))
                for neighbor in neighbor_cells
                if int(neighbor.get("marine_chokepoint_id", -1)) >= 0
            }
        )
        expected_waterway_ids = sorted(
            {
                int(candidate.get("navigable_waterway_id", -1))
                for candidate in [cell, *neighbor_cells]
                if int(candidate.get("navigable_waterway_id", -1)) >= 0
            }
        )
        settlement_links_valid = all(
            settlement_id in settlement_by_id_for_navigation
            and int(settlement_by_id_for_navigation[settlement_id].get("cell_id", -1)) == cell_id
            for settlement_id in settlement_ids
        )
        port_settlement_links_valid = all(
            settlement_id in settlement_by_id_for_navigation
            and int(settlement_by_id_for_navigation[settlement_id].get("cell_id", -1)) == cell_id
            and str(settlement_by_id_for_navigation[settlement_id].get("type", "")) == "port"
            for settlement_id in port_settlement_ids
        )
        route_links_valid = all(
            route_id in route_by_id_for_navigation
            and (
                int(route_by_id_for_navigation[route_id].get("from", -1)) in settlement_ids
                or int(route_by_id_for_navigation[route_id].get("to", -1)) in settlement_ids
            )
            for route_id in route_ids
        )
        marine_region_links_valid = all(region_id in marine_region_by_id for region_id in marine_region_ids_for_site)
        marine_chokepoint_links_valid = all(
            chokepoint_id in marine_chokepoint_by_id for chokepoint_id in marine_chokepoint_ids_for_site
        )
        waterway_links_valid = all(waterway_id in waterway_ids_seen for waterway_id in waterway_ids_for_site)
        site_type = str(site.get("site_type", ""))
        port_type_counts[site_type] += 1
        port_site_area += float(site.get("area_km2", 0.0))
        severe_ice = float(cell.get("ice_thickness_m", 0.0)) >= 80.0 or str(cell.get("biome", "")) == "ice_cap"
        selected_by_suitability = (
            (
                float(cell.get("port_suitability_index", 0.0)) >= 0.58
                or float(cell.get("harbor_suitability_index", 0.0)) >= 0.62
            )
            and not severe_ice
        )
        if (
            site_id != index
            or site_id < 0
            or cell_id not in port_candidate_ids
            or int(cell.get("port_site_id", -1)) != site_id
            or str(cell.get("port_site_type", "")) != site_type
            or site_type not in allowed_port_site_types
            or site_type == "none"
            or bool(cell.get("is_water", False))
            or abs(float(site.get("area_km2", 0.0)) - max(0.0, float(cell.get("area_km2", 0.0)))) > 0.001
            or abs(float(site.get("latitude_deg", 0.0)) - float(cell.get("lat_deg", 0.0))) > 0.001
            or abs(float(site.get("longitude_deg", 0.0)) - float(cell.get("lon_deg", 0.0))) > 0.001
            or abs(float(site.get("port_suitability_index", 0.0)) - float(cell.get("port_suitability_index", 0.0))) > 0.001
            or abs(float(site.get("protected_bay_index", 0.0)) - float(cell.get("protected_bay_index", 0.0))) > 0.001
            or abs(float(site.get("river_mouth_port_index", 0.0)) - float(cell.get("river_mouth_port_index", 0.0))) > 0.001
            or abs(float(site.get("strait_access_index", 0.0)) - float(cell.get("strait_access_index", 0.0))) > 0.001
            or abs(float(site.get("harbor_suitability_index", 0.0)) - float(cell.get("harbor_suitability_index", 0.0))) > 0.001
            or abs(float(site.get("navigability_index", 0.0)) - float(cell.get("navigability_index", 0.0))) > 0.001
            or marine_region_ids_for_site != expected_marine_region_ids
            or marine_chokepoint_ids_for_site != expected_marine_chokepoint_ids
            or waterway_ids_for_site != expected_waterway_ids
            or bool(site.get("selected_by_port_settlement", False)) != bool(port_settlement_ids)
            or bool(site.get("selected_by_suitability", False)) != selected_by_suitability
            or not settlement_links_valid
            or not port_settlement_links_valid
            or not route_links_valid
            or not marine_region_links_valid
            or not marine_chokepoint_links_valid
            or not waterway_links_valid
        ):
            port_site_invalid = True
            break
    if duplicate_port_site_id:
        failures.append("port site ids are not unique")
    if port_site_invalid:
        failures.append("port site records invalid")
    if assigned_port_ids != port_candidate_ids:
        failures.append("port site membership does not match cells")
    if int(summary.get("port_settlement_count", -1)) != port_settlement_count:
        failures.append("port_settlement_count does not match settlements")
    if int(summary.get("port_settlement_with_site_count", -1)) != port_settlement_with_site_count:
        failures.append("port_settlement_with_site_count does not match settlements")
    if abs(float(summary.get("port_site_total_area_km2", 0.0)) - port_site_area) > max(0.001, port_site_area * 0.0001):
        failures.append("port_site_total_area_km2 does not match records")
    if {str(key): int(value) for key, value in summary.get("port_site_type_counts", {}).items()} != dict(
        sorted(port_type_counts.items())
    ):
        failures.append("port_site_type_counts does not match records")
    for site_type, summary_key in (
        ("protected_bay_port", "protected_bay_port_site_count"),
        ("river_mouth_port", "river_mouth_port_site_count"),
        ("strait_port", "strait_port_site_count"),
    ):
        if int(summary.get(summary_key, -1)) != port_type_counts.get(site_type, 0):
            failures.append(f"{summary_key} does not match records")
            break


def _validate_legacy_corridor_block(
    *, payload, summary, cells_payload, cells_by_id, failures, routes, settlements,
) -> None:
    route_radius_km = configured_planet_radius_km(payload)

    def _validator_route_distance_km(first: dict[str, Any], second: dict[str, Any]) -> float:
        first_lat = math.radians(float(first.get("lat_deg", 0.0)))
        first_lon = math.radians(float(first.get("lon_deg", 0.0)))
        second_lat = math.radians(float(second.get("lat_deg", 0.0)))
        second_lon = math.radians(float(second.get("lon_deg", 0.0)))
        delta_lat = second_lat - first_lat
        delta_lon = second_lon - first_lon
        sin_lat = math.sin(delta_lat * 0.5)
        sin_lon = math.sin(delta_lon * 0.5)
        haversine = sin_lat * sin_lat + math.cos(first_lat) * math.cos(second_lat) * sin_lon * sin_lon
        return max(
            0.001,
            route_radius_km
            * 2.0
            * math.asin(min(1.0, math.sqrt(max(0.0, haversine)))),
        )

    failures.extend(_validate_route_corridors(payload, summary, cells_by_id))

    route_corridors = payload.get("route_corridors", [])
    if not isinstance(route_corridors, list):
        failures.append("route_corridors missing or invalid")
        route_corridors = []
    if int(summary.get("route_corridor_count", -1)) != len(route_corridors):
        failures.append("route_corridor_count does not match route_corridors length")
    if int(summary.get("route_corridor_count", -1)) != len(routes):
        failures.append("route_corridor_count should match route count")

    route_corridor_cell_fields = (
        "mountain_pass_route_index",
        "river_valley_route_index",
        "coastal_route_index",
        "oasis_route_index",
        "route_corridor_index",
    )
    route_corridor_cell_invalid = False
    for cell in cells_payload:
        try:
            route_corridor_id = int(cell.get("route_corridor_id", -1))
            route_corridor_type = str(cell.get("route_corridor_type", "none"))
            route_corridor_index = float(cell.get("route_corridor_index", -1.0))
            ranges_valid = all(0.0 <= float(cell.get(field, -1.0)) <= 1.0 for field in route_corridor_cell_fields)
        except (TypeError, ValueError):
            route_corridor_cell_invalid = True
            break
        if (
            not ranges_valid
            or (route_corridor_id < 0 and (route_corridor_type != "none" or abs(route_corridor_index) > 0.001))
            or (route_corridor_id >= 0 and (route_corridor_type == "none" or route_corridor_index <= 0.0))
        ):
            route_corridor_cell_invalid = True
            break
    if route_corridor_cell_invalid:
        failures.append("route corridor cell fields invalid")

    route_corridor_required_fields = {
        "id",
        "route_id",
        "route_type",
        "corridor_type",
        "from_settlement_id",
        "to_settlement_id",
        "start_cell_id",
        "end_cell_id",
        "cell_count",
        "cell_ids",
        "path_length_km",
        "straight_distance_km",
        "detour_ratio",
        "mean_route_corridor_index",
        "max_route_corridor_index",
        "mean_mountain_pass_route_index",
        "mean_river_valley_route_index",
        "mean_coastal_route_index",
        "mean_oasis_route_index",
        "mountain_pass_cell_count",
        "river_valley_cell_count",
        "coastal_cell_count",
        "oasis_cell_count",
        "named_feature_cell_count",
        "settlement_ids",
        "region_ids",
        "route_ids",
        "navigable_waterway_ids",
        "port_site_ids",
    }
    if route_corridors and not route_corridor_required_fields.issubset(route_corridors[0]):
        failures.append("route corridor fields missing")
    route_by_id_for_corridors = {
        int(route.get("id", -1)): route for route in routes if isinstance(route, dict) and int(route.get("id", -1)) >= 0
    }
    settlements_by_id_for_corridors = {
        int(settlement.get("id", -1)): settlement
        for settlement in settlements
        if isinstance(settlement, dict) and int(settlement.get("id", -1)) >= 0
    }
    corridor_by_id = {
        int(corridor.get("id", -1)): corridor
        for corridor in route_corridors
        if isinstance(corridor, dict) and int(corridor.get("id", -1)) >= 0
    }
    route_corridor_invalid = False
    route_corridor_cells: set[int] = set()
    route_corridor_total_path_length = 0.0
    route_feature_covered_count = 0
    route_corridor_type_counter: Counter[str] = Counter()
    for expected_id, corridor in enumerate(route_corridors):
        try:
            corridor_id = int(corridor.get("id", -1))
            route_id = int(corridor.get("route_id", -1))
            route_type = str(corridor.get("route_type", ""))
            corridor_type = str(corridor.get("corridor_type", ""))
            cell_ids_for_corridor = [int(cell_id) for cell_id in corridor.get("cell_ids", [])]
        except (TypeError, ValueError):
            route_corridor_invalid = True
            break
        route = route_by_id_for_corridors.get(route_id)
        source = settlements_by_id_for_corridors.get(int(corridor.get("from_settlement_id", -1)))
        target = settlements_by_id_for_corridors.get(int(corridor.get("to_settlement_id", -1)))
        path_cells = [cells_by_id.get(cell_id) for cell_id in cell_ids_for_corridor]
        if (
            corridor_id != expected_id
            or corridor_id not in corridor_by_id
            or route is None
            or source is None
            or target is None
            or int(route.get("route_corridor_id", -1)) != corridor_id
            or str(route.get("route_corridor_type", "")) != corridor_type
            or [int(cell_id) for cell_id in route.get("path_cell_ids", [])] != cell_ids_for_corridor
            or route_type != str(route.get("type", ""))
            or int(corridor.get("cell_count", -1)) != len(cell_ids_for_corridor)
            or not cell_ids_for_corridor
            or cell_ids_for_corridor[0] != int(corridor.get("start_cell_id", -1))
            or cell_ids_for_corridor[-1] != int(corridor.get("end_cell_id", -1))
            or int(source.get("cell_id", -1)) != int(corridor.get("start_cell_id", -1))
            or int(target.get("cell_id", -1)) != int(corridor.get("end_cell_id", -1))
            or any(cell is None for cell in path_cells)
        ):
            route_corridor_invalid = True
            break
        valid_path_cells = [cell for cell in path_cells if cell is not None]
        adjacent_valid = True
        path_length = 0.0
        for first_id, second_id in zip(cell_ids_for_corridor, cell_ids_for_corridor[1:]):
            first_cell = cells_by_id.get(first_id, {})
            second_cell = cells_by_id.get(second_id, {})
            if second_id not in {int(neighbor_id) for neighbor_id in first_cell.get("neighbors", [])}:
                adjacent_valid = False
                break
            path_length += _validator_route_distance_km(first_cell, second_cell)
        straight_distance = max(0.001, float(route.get("distance_km", 0.0)))
        mountain_count = sum(1 for cell in valid_path_cells if float(cell.get("mountain_pass_route_index", 0.0)) >= 0.45)
        river_count = sum(1 for cell in valid_path_cells if float(cell.get("river_valley_route_index", 0.0)) >= 0.45)
        coastal_count = sum(1 for cell in valid_path_cells if float(cell.get("coastal_route_index", 0.0)) >= 0.45)
        oasis_count = sum(1 for cell in valid_path_cells if float(cell.get("oasis_route_index", 0.0)) >= 0.45)
        feature_counts = {
            "mountain_pass_corridor": mountain_count,
            "river_valley_corridor": river_count,
            "coastal_corridor": coastal_count,
            "oasis_corridor": oasis_count,
        }
        if route_type == "coastal_sea" and coastal_count > 0:
            expected_corridor_type = "coastal_corridor"
        elif route_type == "river_corridor" and river_count > 0:
            expected_corridor_type = "river_valley_corridor"
        elif route_type == "mountain_pass" and mountain_count > 0:
            expected_corridor_type = "mountain_pass_corridor"
        else:
            best_type, best_count = sorted(feature_counts.items(), key=lambda item: (-item[1], item[0]))[0]
            expected_corridor_type = best_type if best_count > 0 else "overland_corridor"
        named_count = sum(
            1
            for cell in valid_path_cells
            if (
                float(cell.get("mountain_pass_route_index", 0.0)) >= 0.45
                or float(cell.get("river_valley_route_index", 0.0)) >= 0.45
                or float(cell.get("coastal_route_index", 0.0)) >= 0.45
                or float(cell.get("oasis_route_index", 0.0)) >= 0.45
            )
        )
        route_corridor_values = [float(cell.get("route_corridor_index", 0.0)) for cell in valid_path_cells]
        mountain_values = [float(cell.get("mountain_pass_route_index", 0.0)) for cell in valid_path_cells]
        river_values = [float(cell.get("river_valley_route_index", 0.0)) for cell in valid_path_cells]
        coastal_values = [float(cell.get("coastal_route_index", 0.0)) for cell in valid_path_cells]
        oasis_values = [float(cell.get("oasis_route_index", 0.0)) for cell in valid_path_cells]
        expected_region_ids = sorted(
            {
                int(source.get("region_id", -1)),
                int(target.get("region_id", -1)),
            }
            - {-1}
        )
        expected_waterway_ids = sorted(
            {
                int(cell.get("navigable_waterway_id", -1))
                for cell in valid_path_cells
                if int(cell.get("navigable_waterway_id", -1)) >= 0
            }
        )
        expected_port_site_ids = sorted(
            {
                int(cell.get("port_site_id", -1))
                for cell in valid_path_cells
                if int(cell.get("port_site_id", -1)) >= 0
            }
        )
        if (
            not adjacent_valid
            or corridor_type != expected_corridor_type
            or abs(float(corridor.get("path_length_km", 0.0)) - path_length) > max(0.001, path_length * 0.0001)
            or abs(float(corridor.get("straight_distance_km", 0.0)) - straight_distance) > max(0.001, straight_distance * 0.0001)
            or abs(float(corridor.get("detour_ratio", 0.0)) - path_length / straight_distance) > 0.001
            or abs(float(corridor.get("mean_route_corridor_index", 0.0)) - sum(route_corridor_values) / len(route_corridor_values)) > 0.001
            or abs(float(corridor.get("max_route_corridor_index", 0.0)) - max(route_corridor_values)) > 0.001
            or abs(float(corridor.get("mean_mountain_pass_route_index", 0.0)) - sum(mountain_values) / len(mountain_values)) > 0.001
            or abs(float(corridor.get("mean_river_valley_route_index", 0.0)) - sum(river_values) / len(river_values)) > 0.001
            or abs(float(corridor.get("mean_coastal_route_index", 0.0)) - sum(coastal_values) / len(coastal_values)) > 0.001
            or abs(float(corridor.get("mean_oasis_route_index", 0.0)) - sum(oasis_values) / len(oasis_values)) > 0.001
            or int(corridor.get("mountain_pass_cell_count", -1)) != mountain_count
            or int(corridor.get("river_valley_cell_count", -1)) != river_count
            or int(corridor.get("coastal_cell_count", -1)) != coastal_count
            or int(corridor.get("oasis_cell_count", -1)) != oasis_count
            or int(corridor.get("named_feature_cell_count", -1)) != named_count
            or [int(value) for value in corridor.get("settlement_ids", [])] != sorted(
                {int(corridor.get("from_settlement_id", -1)), int(corridor.get("to_settlement_id", -1))} - {-1}
            )
            or [int(value) for value in corridor.get("region_ids", [])] != expected_region_ids
            or [int(value) for value in corridor.get("route_ids", [])] != [route_id]
            or [int(value) for value in corridor.get("navigable_waterway_ids", [])] != expected_waterway_ids
            or [int(value) for value in corridor.get("port_site_ids", [])] != expected_port_site_ids
        ):
            route_corridor_invalid = True
            break
        route_corridor_cells.update(cell_ids_for_corridor)
        route_corridor_total_path_length += path_length
        route_feature_covered_count += 1 if named_count > 0 else 0
        route_corridor_type_counter[corridor_type] += 1
    if route_corridor_invalid:
        failures.append("route corridor records invalid")

    for cell in cells_payload:
        route_corridor_id = int(cell.get("route_corridor_id", -1))
        if route_corridor_id >= 0:
            corridor = corridor_by_id.get(route_corridor_id)
            if corridor is None or int(cell.get("id", -1)) not in {int(value) for value in corridor.get("cell_ids", [])}:
                failures.append("route corridor cell id references invalid")
                break
    if int(summary.get("route_corridor_cell_count", -1)) != len(route_corridor_cells):
        failures.append("route_corridor_cell_count does not match exported route paths")
    if abs(float(summary.get("route_corridor_total_path_length_km", 0.0)) - route_corridor_total_path_length) > max(0.001, route_corridor_total_path_length * 0.0001):
        failures.append("route_corridor_total_path_length_km does not match corridor records")
    route_corridor_expected_means = {
        "mean_route_corridor_index": sum(float(cell.get("route_corridor_index", 0.0)) for cell in cells_payload) / len(cells_payload) if cells_payload else 0.0,
        "mean_mountain_pass_route_index": sum(float(cell.get("mountain_pass_route_index", 0.0)) for cell in cells_payload) / len(cells_payload) if cells_payload else 0.0,
        "mean_river_valley_route_index": sum(float(cell.get("river_valley_route_index", 0.0)) for cell in cells_payload) / len(cells_payload) if cells_payload else 0.0,
        "mean_coastal_route_index": sum(float(cell.get("coastal_route_index", 0.0)) for cell in cells_payload) / len(cells_payload) if cells_payload else 0.0,
        "mean_oasis_route_index": sum(float(cell.get("oasis_route_index", 0.0)) for cell in cells_payload) / len(cells_payload) if cells_payload else 0.0,
    }
    for key, expected in route_corridor_expected_means.items():
        if abs(float(summary.get(key, 0.0)) - expected) > 0.001:
            failures.append(f"{key} does not match route corridor cells")
    expected_route_feature_coverage = route_feature_covered_count / len(route_corridors) if route_corridors else 1.0
    if abs(float(summary.get("route_feature_coverage_index", 0.0)) - expected_route_feature_coverage) > 0.001:
        failures.append("route_feature_coverage_index does not match corridor records")
    if summary.get("route_corridor_type_counts", {}) != dict(sorted(route_corridor_type_counter.items())):
        failures.append("route_corridor_type_counts does not match route corridors")
    route_corridor_specific_counts = {
        "mountain_pass_route_corridor_count": route_corridor_type_counter.get("mountain_pass_corridor", 0),
        "river_valley_route_corridor_count": route_corridor_type_counter.get("river_valley_corridor", 0),
        "coastal_route_corridor_count": route_corridor_type_counter.get("coastal_corridor", 0),
        "oasis_route_corridor_count": route_corridor_type_counter.get("oasis_corridor", 0),
    }
    for key, expected in route_corridor_specific_counts.items():
        if int(summary.get(key, -1)) != expected:
            failures.append(f"{key} does not match route corridor type counts")

