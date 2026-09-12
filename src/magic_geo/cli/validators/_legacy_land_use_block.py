"""Unchanged historical CLI land-use checks; current v2 has exact raw replay."""

from __future__ import annotations

from typing import Any


def _validate_legacy_land_use_block(
    payload: dict[str, Any], summary: dict[str, Any],
    cells_payload: list[dict[str, Any]], cells_by_id: dict[int, dict[str, Any]],
    resource_deposits: list[dict[str, Any]], failures: list[str],
) -> None:
    agricultural_zones = payload.get("agricultural_zones", [])
    mining_zones = payload.get("mining_zones", [])
    land_use_summary_keys = {
        "agricultural_zone_count",
        "agricultural_zone_cell_count",
        "agricultural_zone_total_area_km2",
        "mean_agricultural_potential_index",
        "mining_zone_count",
        "mining_zone_cell_count",
        "mining_zone_total_area_km2",
        "mean_mining_potential_index",
    }
    if not land_use_summary_keys.issubset(summary):
        failures.append("land use zone summary metrics missing")
    if not isinstance(agricultural_zones, list):
        failures.append("agricultural_zones missing")
        agricultural_zones = []
    if not isinstance(mining_zones, list):
        failures.append("mining_zones missing")
        mining_zones = []
    land_use_cell_keys = {
        "agricultural_potential_index",
        "mining_potential_index",
        "agricultural_zone_id",
        "mining_zone_id",
    }
    if cells_payload and not land_use_cell_keys.issubset(cells_payload[0]):
        failures.append("land use zone cell fields missing")
    agricultural_candidate_ids: set[int] = set()
    mining_candidate_ids: set[int] = set()
    agricultural_potential_sum = 0.0
    mining_potential_sum = 0.0
    agricultural_candidate_area = 0.0
    mining_candidate_area = 0.0
    land_use_cell_invalid = False
    for cell in cells_payload:
        cell_id = int(cell.get("id", -1))
        agricultural_potential = float(cell.get("agricultural_potential_index", -1.0))
        mining_potential = float(cell.get("mining_potential_index", -1.0))
        agricultural_zone_id = int(cell.get("agricultural_zone_id", -2))
        mining_zone_id = int(cell.get("mining_zone_id", -2))
        is_water = bool(cell.get("is_water", False))
        area = max(0.0, float(cell.get("area_km2", 0.0)))
        agricultural_potential_sum += agricultural_potential
        mining_potential_sum += mining_potential
        if agricultural_potential >= 0.58:
            agricultural_candidate_ids.add(cell_id)
            agricultural_candidate_area += area
        if mining_potential >= 0.52:
            mining_candidate_ids.add(cell_id)
            mining_candidate_area += area
        if (
            not 0.0 <= agricultural_potential <= 1.0
            or not 0.0 <= mining_potential <= 1.0
            or agricultural_zone_id < -1
            or mining_zone_id < -1
            or (is_water and (agricultural_potential != 0.0 or mining_potential != 0.0))
            or (is_water and (agricultural_zone_id != -1 or mining_zone_id != -1))
        ):
            land_use_cell_invalid = True
            break
    if land_use_cell_invalid:
        failures.append("land use zone cell fields invalid")
    if int(summary.get("agricultural_zone_count", -1)) != len(agricultural_zones):
        failures.append("agricultural_zone_count does not match agricultural_zones length")
    if int(summary.get("mining_zone_count", -1)) != len(mining_zones):
        failures.append("mining_zone_count does not match mining_zones length")
    if int(summary.get("agricultural_zone_cell_count", -1)) != len(agricultural_candidate_ids):
        failures.append("agricultural_zone_cell_count does not match candidate cells")
    if int(summary.get("mining_zone_cell_count", -1)) != len(mining_candidate_ids):
        failures.append("mining_zone_cell_count does not match candidate cells")
    cell_count_divisor = float(len(cells_payload)) if cells_payload else 1.0
    if abs(float(summary.get("mean_agricultural_potential_index", 0.0)) - agricultural_potential_sum / cell_count_divisor) > 0.001:
        failures.append("mean_agricultural_potential_index does not match cells")
    if abs(float(summary.get("mean_mining_potential_index", 0.0)) - mining_potential_sum / cell_count_divisor) > 0.001:
        failures.append("mean_mining_potential_index does not match cells")
    if abs(float(summary.get("agricultural_zone_total_area_km2", 0.0)) - agricultural_candidate_area) > max(
        0.001,
        agricultural_candidate_area * 0.0001,
    ):
        failures.append("agricultural_zone_total_area_km2 does not match candidate cells")
    if abs(float(summary.get("mining_zone_total_area_km2", 0.0)) - mining_candidate_area) > max(
        0.001,
        mining_candidate_area * 0.0001,
    ):
        failures.append("mining_zone_total_area_km2 does not match candidate cells")

    local_settlements = payload.get("settlements", [])
    local_routes = payload.get("routes", [])
    local_settlements = local_settlements if isinstance(local_settlements, list) else []
    local_routes = local_routes if isinstance(local_routes, list) else []
    settlement_by_id = {int(settlement.get("id", -1)): settlement for settlement in local_settlements if isinstance(settlement, dict)}
    route_by_id = {int(route.get("id", -1)): route for route in local_routes if isinstance(route, dict)}
    resource_deposit_by_id = {
        int(deposit.get("id", -1)): deposit for deposit in resource_deposits if isinstance(deposit, dict)
    }
    land_use_zone_keys = {
        "id",
        "zone_type",
        "cell_count",
        "cell_ids",
        "area_km2",
        "mean_potential_index",
        "mean_fertility_index",
        "dominant_resource",
        "dominant_landform",
        "dominant_biome",
        "settlement_ids",
        "route_ids",
        "resource_deposit_ids",
    }
    for zones, label in ((agricultural_zones, "agricultural"), (mining_zones, "mining")):
        if zones and not land_use_zone_keys.issubset(zones[0]):
            failures.append(f"{label} zone fields missing")
    land_use_zone_invalid = False
    assigned_agricultural_ids: set[int] = set()
    assigned_mining_ids: set[int] = set()
    agricultural_zone_area = 0.0
    mining_zone_area = 0.0
    for zones, label, potential_key, zone_id_key, candidate_ids, assigned_ids in (
        (
            agricultural_zones,
            "agricultural",
            "agricultural_potential_index",
            "agricultural_zone_id",
            agricultural_candidate_ids,
            assigned_agricultural_ids,
        ),
        (
            mining_zones,
            "mining",
            "mining_potential_index",
            "mining_zone_id",
            mining_candidate_ids,
            assigned_mining_ids,
        ),
    ):
        zone_ids: set[int] = set()
        for index, zone in enumerate(zones):
            zone_id = int(zone.get("id", -1))
            zone_ids.add(zone_id)
            cell_ids_for_zone = zone.get("cell_ids", [])
            settlement_ids_for_zone = zone.get("settlement_ids", [])
            route_ids_for_zone = zone.get("route_ids", [])
            deposit_ids_for_zone = zone.get("resource_deposit_ids", [])
            if (
                not isinstance(cell_ids_for_zone, list)
                or not isinstance(settlement_ids_for_zone, list)
                or not isinstance(route_ids_for_zone, list)
                or not isinstance(deposit_ids_for_zone, list)
            ):
                land_use_zone_invalid = True
                break
            member_ids = [int(cell_id) for cell_id in cell_ids_for_zone]
            group_cells = [cells_by_id.get(cell_id) for cell_id in member_ids]
            if any(cell is None for cell in group_cells) or not group_cells:
                land_use_zone_invalid = True
                break
            valid_group_cells: list[dict[str, Any]] = [cell for cell in group_cells if cell is not None]
            group_count = len(valid_group_cells)
            area_sum = sum(max(0.0, float(cell.get("area_km2", 0.0))) for cell in valid_group_cells)
            potential_sum = sum(float(cell.get(potential_key, 0.0)) for cell in valid_group_cells)
            fertility_sum = sum(max(0.0, min(1.0, float(cell.get("fertility", 0.0)))) for cell in valid_group_cells)
            member_id_set = {int(cell.get("id", -1)) for cell in valid_group_cells}
            assigned_ids.update(member_id_set)
            if label == "agricultural":
                agricultural_zone_area += float(zone.get("area_km2", 0.0))
            else:
                mining_zone_area += float(zone.get("area_km2", 0.0))
            settlement_ids = [int(settlement_id) for settlement_id in settlement_ids_for_zone]
            route_ids = [int(route_id) for route_id in route_ids_for_zone]
            deposit_ids = [int(deposit_id) for deposit_id in deposit_ids_for_zone]
            settlement_links_valid = all(
                settlement_id in settlement_by_id
                and int(settlement_by_id[settlement_id].get("cell_id", -1)) in member_id_set
                for settlement_id in settlement_ids
            )
            route_links_valid = all(
                route_id in route_by_id
                and (
                    int(route_by_id[route_id].get("from", -1)) in settlement_ids
                    or int(route_by_id[route_id].get("to", -1)) in settlement_ids
                )
                for route_id in route_ids
            )
            deposit_links_valid = all(
                deposit_id in resource_deposit_by_id
                and int(resource_deposit_by_id[deposit_id].get("cell_id", -1)) in member_id_set
                for deposit_id in deposit_ids
            )
            if (
                zone_id != index
                or str(zone.get("zone_type", "")) != label
                or zone_id < 0
                or int(zone.get("cell_count", -1)) != group_count
                or len(member_ids) != len(member_id_set)
                or not member_id_set.issubset(candidate_ids)
                or any(int(cell.get(zone_id_key, -1)) != zone_id for cell in valid_group_cells)
                or abs(float(zone.get("area_km2", 0.0)) - area_sum) > max(0.001, area_sum * 0.0001)
                or abs(float(zone.get("mean_potential_index", 0.0)) - potential_sum / group_count) > 0.001
                or abs(float(zone.get("mean_fertility_index", 0.0)) - fertility_sum / group_count) > 0.001
                or not str(zone.get("dominant_resource", "")).strip()
                or not str(zone.get("dominant_landform", "")).strip()
                or not str(zone.get("dominant_biome", "")).strip()
                or not settlement_links_valid
                or not route_links_valid
                or not deposit_links_valid
            ):
                land_use_zone_invalid = True
                break
        if len(zone_ids) != len(zones):
            failures.append(f"{label} zone ids are not unique")
        if land_use_zone_invalid:
            break
    if land_use_zone_invalid:
        failures.append("land use zone records invalid")
    if assigned_agricultural_ids != agricultural_candidate_ids:
        failures.append("agricultural zone membership does not match cells")
    if assigned_mining_ids != mining_candidate_ids:
        failures.append("mining zone membership does not match cells")
    if abs(float(summary.get("agricultural_zone_total_area_km2", 0.0)) - agricultural_zone_area) > max(
        0.001,
        agricultural_zone_area * 0.0001,
    ):
        failures.append("agricultural_zone_total_area_km2 does not match zones")
    if abs(float(summary.get("mining_zone_total_area_km2", 0.0)) - mining_zone_area) > max(
        0.001,
        mining_zone_area * 0.0001,
    ):
        failures.append("mining_zone_total_area_km2 does not match zones")

# End of the unchanged historical inline checks.
