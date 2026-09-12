from __future__ import annotations

import heapq
import math
from typing import Any

from .logistics_exchange_validation import _expected_logistics_exchanges
from .planet_parameters import planet_radius_km


CAMPAIGN_OPERATIONS_MODEL = (
    "causal_conflict_cell_path_front_tactical_strategic_campaign_operations_v1"
)


def _campaign_operations_model() -> dict[str, Any]:
    return {
        "model_type": CAMPAIGN_OPERATIONS_MODEL,
        "deterministic": True,
        "campaign_order": "ascending_conflict_id_v1",
        "endpoint_model": "victor_origin_route_border_contested_capital_fallback_v1",
        "path_model": "cell_graph_dijkstra_distance_terrain_route_mode_cost_v1",
        "segment_model": "terrain_barrier_supply_and_attrition_ledger_v1",
        "front_model": "path_step_force_supply_attrition_occupation_control_v1",
        "tactical_model": "paired_force_supply_counter_maneuver_and_control_replay_v1",
        "strategic_model": "primary_reverse_counter_axis_force_reserve_and_three_decision_points_v1",
        "model_limitation": "single_deterministic_axis_per_conflict_without_adaptive_replanning_uncertainty_simultaneous_fronts_or_observed_calibration",
    }


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _border_pair_key(region_a: int, region_b: int) -> tuple[int, int]:
    return (min(region_a, region_b), max(region_a, region_b))


def _border_by_pair(payload: dict[str, Any]) -> dict[tuple[int, int], dict[str, Any]]:
    best: dict[tuple[int, int], dict[str, Any]] = {}
    for border in payload.get("borders", []):
        region_a = int(border.get("region_a", -1))
        region_b = int(border.get("region_b", -1))
        if region_a < 0 or region_b < 0 or region_a == region_b:
            continue
        key = _border_pair_key(region_a, region_b)
        existing = best.get(key)
        if existing is None or float(border.get("barrier_score", 1.0)) < float(
            existing.get("barrier_score", 1.0)
        ):
            best[key] = border
    return best


def _settlement_regions(payload: dict[str, Any]) -> dict[int, int]:
    regions: dict[int, int] = {}
    for settlement in payload.get("settlements", []):
        settlement_id = int(settlement.get("id", -1))
        region_id = int(settlement.get("region_id", -1))
        if settlement_id >= 0 and region_id >= 0:
            regions[settlement_id] = region_id
    return regions


def _index_records(records: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    indexed: dict[int, dict[str, Any]] = {}
    for record in records:
        record_id = int(record.get("id", -1))
        if record_id >= 0:
            indexed[record_id] = record
    return indexed


def _cell_distance_km(
    first: dict[str, Any],
    second: dict[str, Any],
    radius_km: float,
) -> float:
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


def _campaign_terrain_cost(
    cell: dict[str, Any], next_cell: dict[str, Any], route_type: str
) -> float:
    elevation = float(cell.get("elevation_m", 0.0))
    next_elevation = float(next_cell.get("elevation_m", elevation))
    slope_cost = _clamp(abs(next_elevation - elevation) / 2200.0)
    aridity = _clamp(float(next_cell.get("seasonal_aridity_index", 0.0)))
    ice = _clamp(float(next_cell.get("ice_thickness_m", 0.0)) / 1200.0)
    water = bool(next_cell.get("is_water", False))
    landform = str(next_cell.get("landform", ""))
    biome = str(next_cell.get("biome", ""))
    route_type = str(route_type)
    water_cost = 0.18 if route_type == "coastal_sea" else 0.62
    if route_type in {"river", "river_corridor"}:
        water_cost = 0.28
    terrain = 0.18 + slope_cost * 0.30 + aridity * 0.14 + ice * 0.16
    if water:
        terrain += water_cost
    if "mountain" in landform or "glacial_valley" in landform:
        terrain += 0.18
    if "desert" in biome or "desert" in landform:
        terrain += 0.12
    if "forest" in biome or "wetland" in biome:
        terrain += 0.06
    if bool(next_cell.get("is_river", False)) and route_type in {
        "river",
        "river_corridor",
    }:
        terrain -= 0.10
    if route_type == "overland" and not water:
        terrain -= 0.04
    return _clamp(terrain)


def _movement_step_cost(
    cell: dict[str, Any],
    next_cell: dict[str, Any],
    route_type: str,
    radius_km: float,
) -> float:
    distance = _cell_distance_km(cell, next_cell, radius_km)
    terrain = _campaign_terrain_cost(cell, next_cell, route_type)
    water_penalty = 0.0
    if bool(next_cell.get("is_water", False)) and route_type not in {
        "coastal_sea",
        "river",
        "river_corridor",
    }:
        water_penalty = 1.85
    return distance * (0.45 + terrain * 1.65 + water_penalty)


def _shortest_campaign_path(
    start_cell_id: int,
    target_cell_id: int,
    cells_by_id: dict[int, dict[str, Any]],
    route_type: str,
    radius_km: float,
) -> list[int]:
    if start_cell_id == target_cell_id and start_cell_id in cells_by_id:
        return [start_cell_id]
    if start_cell_id not in cells_by_id or target_cell_id not in cells_by_id:
        return []
    queue: list[tuple[float, int]] = [(0.0, start_cell_id)]
    best_cost: dict[int, float] = {start_cell_id: 0.0}
    previous: dict[int, int] = {}
    visited: set[int] = set()
    while queue:
        cost, cell_id = heapq.heappop(queue)
        if cell_id in visited:
            continue
        visited.add(cell_id)
        if cell_id == target_cell_id:
            break
        cell = cells_by_id.get(cell_id)
        if cell is None:
            continue
        for neighbor_id_raw in cell.get("neighbors", []):
            neighbor_id = int(neighbor_id_raw)
            neighbor = cells_by_id.get(neighbor_id)
            if neighbor is None:
                continue
            next_cost = cost + _movement_step_cost(
                cell,
                neighbor,
                route_type,
                radius_km,
            )
            if next_cost < best_cost.get(neighbor_id, float("inf")):
                best_cost[neighbor_id] = next_cost
                previous[neighbor_id] = cell_id
                heapq.heappush(queue, (next_cost, neighbor_id))
    if target_cell_id not in best_cost:
        return []
    path = [target_cell_id]
    while path[-1] != start_cell_id:
        parent = previous.get(path[-1])
        if parent is None:
            return []
        path.append(parent)
    path.reverse()
    return path


def _region_capital_cell(
    region_id: int,
    regions_by_id: dict[int, dict[str, Any]],
    settlements_by_id: dict[int, dict[str, Any]],
) -> int:
    region = regions_by_id.get(region_id, {})
    capital_id = int(region.get("capital_settlement_id", -1))
    capital = settlements_by_id.get(capital_id, {})
    return int(capital.get("cell_id", -1))


def _cell_political_region_id(cell: dict[str, Any]) -> int:
    try:
        return int(cell.get("political_region_id", -1))
    except (TypeError, ValueError):
        return -1


def _append_campaign_target_candidate(
    candidates: list[int],
    cell_id: int,
    start_cell_id: int,
    cells_by_id: dict[int, dict[str, Any]],
) -> None:
    if cell_id in cells_by_id and cell_id != start_cell_id and cell_id not in candidates:
        candidates.append(cell_id)


def _campaign_endpoint_cells(
    conflict: dict[str, Any],
    route: dict[str, Any],
    origin_region: int,
    target_region: int,
    regions_by_id: dict[int, dict[str, Any]],
    settlements_by_id: dict[int, dict[str, Any]],
    settlement_regions: dict[int, int],
    cells_by_id: dict[int, dict[str, Any]],
    radius_km: float,
) -> tuple[int, int]:
    start_cell_id = -1
    for settlement_key in ("from", "to"):
        settlement_id = int(route.get(settlement_key, -1))
        if settlement_regions.get(settlement_id, -1) == origin_region:
            start_cell_id = int(
                settlements_by_id.get(settlement_id, {}).get("cell_id", -1)
            )
            break
    if start_cell_id not in cells_by_id:
        start_cell_id = _region_capital_cell(
            origin_region, regions_by_id, settlements_by_id
        )

    target_candidates: list[int] = []
    contested_cell_id = int(conflict.get("contested_cell_id", -1))
    contested_cell = cells_by_id.get(contested_cell_id)
    if (
        contested_cell is not None
        and _cell_political_region_id(contested_cell) == target_region
    ):
        _append_campaign_target_candidate(
            target_candidates, contested_cell_id, start_cell_id, cells_by_id
        )
    start_cell = cells_by_id.get(start_cell_id, {})
    for neighbor_id_raw in start_cell.get("neighbors", []):
        neighbor_id = int(neighbor_id_raw)
        neighbor = cells_by_id.get(neighbor_id)
        if neighbor is not None and _cell_political_region_id(neighbor) == target_region:
            _append_campaign_target_candidate(
                target_candidates, neighbor_id, start_cell_id, cells_by_id
            )
    for settlement_key in ("from", "to"):
        settlement_id = int(route.get(settlement_key, -1))
        if settlement_regions.get(settlement_id, -1) == target_region:
            target_cell_id = int(
                settlements_by_id.get(settlement_id, {}).get("cell_id", -1)
            )
            _append_campaign_target_candidate(
                target_candidates, target_cell_id, start_cell_id, cells_by_id
            )
    _append_campaign_target_candidate(
        target_candidates,
        _region_capital_cell(target_region, regions_by_id, settlements_by_id),
        start_cell_id,
        cells_by_id,
    )
    if contested_cell is not None:
        _append_campaign_target_candidate(
            target_candidates, contested_cell_id, start_cell_id, cells_by_id
        )
    if not target_candidates and start_cell:
        target_region_cells = [
            (cell_id, cell)
            for cell_id, cell in cells_by_id.items()
            if cell_id != start_cell_id
            and _cell_political_region_id(cell) == target_region
        ]
        if target_region_cells:
            target_cell_id = min(
                target_region_cells,
                key=lambda item: _cell_distance_km(
                    start_cell,
                    item[1],
                    radius_km,
                ),
            )[0]
            _append_campaign_target_candidate(
                target_candidates, target_cell_id, start_cell_id, cells_by_id
            )
    if not target_candidates:
        for neighbor_id_raw in start_cell.get("neighbors", []):
            _append_campaign_target_candidate(
                target_candidates, int(neighbor_id_raw), start_cell_id, cells_by_id
            )
    target_cell_id = target_candidates[0] if target_candidates else -1
    return start_cell_id, target_cell_id


def _build_tactical_engagements(
    conflicts: list[dict[str, Any]],
    campaign_movements: list[dict[str, Any]],
    campaign_front_histories: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, float]]:
    campaigns_by_conflict = {
        int(campaign.get("conflict_id", -1)): campaign
        for campaign in campaign_movements
        if int(campaign.get("conflict_id", -1)) >= 0
    }
    fronts_by_campaign = {
        int(front.get("campaign_movement_id", -1)): front
        for front in campaign_front_histories
        if int(front.get("campaign_movement_id", -1)) >= 0
    }
    tactical_engagements: list[dict[str, Any]] = []
    total_steps = 0
    total_attrition_loss = 0.0
    counter_sum = 0.0
    pressure_sum = 0.0
    supply_contest_sum = 0.0
    high_pressure_steps = 0

    for conflict in sorted(conflicts, key=lambda item: int(item.get("id", -1))):
        conflict_id = int(conflict.get("id", -1))
        campaign = campaigns_by_conflict.get(conflict_id)
        if campaign is None:
            continue
        campaign_id = int(campaign.get("id", -1))
        front = fronts_by_campaign.get(campaign_id)
        if front is None:
            continue
        region_a = int(conflict.get("region_a", -1))
        region_b = int(conflict.get("region_b", -1))
        if region_a < 0 or region_b < 0 or region_a == region_b:
            continue
        origin_region = int(campaign.get("origin_region_id", -1))
        target_region = int(campaign.get("target_region_id", -1))
        steps = front.get("steps", [])
        if not isinstance(steps, list) or not steps:
            continue
        initial_a = max(0.0, float(conflict.get("region_a_force_estimate", 0.0)))
        initial_b = max(0.0, float(conflict.get("region_b_force_estimate", 0.0)))
        casualty_rate = _clamp(float(conflict.get("casualty_rate", 0.0)))
        intensity = _clamp(float(conflict.get("intensity", 0.0)))
        logistics_strain = _clamp(float(conflict.get("logistics_strain_index", 0.0)))
        campaign_success = _clamp(float(campaign.get("campaign_success_index", 0.0)))
        path_cells = [int(cell_id) for cell_id in campaign.get("path_cell_ids", [])]
        engagement_steps: list[dict[str, Any]] = []
        engagement_attrition = 0.0
        engagement_counter_sum = 0.0
        engagement_pressure_sum = 0.0
        engagement_supply_sum = 0.0
        max_pressure = 0.0
        final_a = initial_a
        final_b = initial_b
        for sequence_index, step in enumerate(steps):
            attacking_force = max(
                0.0, float(step.get("attacking_force_estimate", 0.0))
            )
            defending_force = max(
                0.0, float(step.get("defending_force_estimate", 0.0))
            )
            if origin_region == region_a:
                region_a_force = attacking_force
                region_b_force = defending_force
                attacker_supply = _clamp(
                    float(step.get("supply_integrity_index", 0.0))
                )
                region_a_control_signal = _clamp(
                    float(step.get("occupation_control_index", 0.0))
                )
            else:
                region_a_force = defending_force
                region_b_force = attacking_force
                attacker_supply = _clamp(
                    float(step.get("supply_integrity_index", 0.0))
                )
                region_a_control_signal = _clamp(
                    1.0 - float(step.get("occupation_control_index", 0.0))
                )
            defender_supply = _clamp(
                0.76
                - logistics_strain * 0.20
                - sequence_index / max(1, len(steps) - 1) * 0.18
                + (1.0 - campaign_success) * 0.16
            )
            if target_region == region_a:
                region_a_supply = defender_supply
                region_b_supply = attacker_supply
            else:
                region_a_supply = attacker_supply
                region_b_supply = defender_supply
            total_force = max(1.0, region_a_force + region_b_force)
            force_balance = abs(region_a_force - region_b_force) / total_force
            supply_contest = _clamp(
                abs(region_a_supply - region_b_supply) * 0.52
                + logistics_strain * 0.26
                + intensity * 0.22
            )
            front_pressure = _clamp(
                float(step.get("local_attrition_index", 0.0)) * 0.34
                + (1.0 - min(region_a_supply, region_b_supply)) * 0.24
                + intensity * 0.26
                + float(step.get("front_width_index", 0.0)) * 0.16
            )
            counter_maneuver = _clamp(
                (1.0 - force_balance) * 0.32
                + supply_contest * 0.26
                + float(step.get("front_width_index", 0.0)) * 0.22
                + (1.0 - campaign_success) * 0.20
            )
            encirclement_risk = _clamp(
                front_pressure * 0.38
                + counter_maneuver * 0.26
                + force_balance * 0.20
                + (1.0 - min(region_a_supply, region_b_supply)) * 0.16
            )
            withdrawal_pressure = _clamp(
                front_pressure * 0.42
                + supply_contest * 0.28
                + casualty_rate * 0.30
            )
            attrition_loss = max(
                0.0,
                float(step.get("attrition_loss_population", 0.0))
                + total_force
                * (0.0025 + casualty_rate * 0.014 + front_pressure * 0.006),
            )
            control_balance = _clamp(
                region_a_force / total_force * 0.42
                + region_a_supply * 0.18
                + region_a_control_signal * 0.40
            )
            control_region = region_a if control_balance >= 0.50 else region_b
            final_a = region_a_force
            final_b = region_b_force
            engagement_attrition += attrition_loss
            engagement_counter_sum += counter_maneuver
            engagement_pressure_sum += front_pressure
            engagement_supply_sum += supply_contest
            max_pressure = max(max_pressure, front_pressure)
            total_steps += 1
            total_attrition_loss += attrition_loss
            counter_sum += counter_maneuver
            pressure_sum += front_pressure
            supply_contest_sum += supply_contest
            high_pressure_steps += int(front_pressure >= 0.65)
            engagement_steps.append(
                {
                    "sequence_index": sequence_index,
                    "cell_id": int(step.get("cell_id", -1)),
                    "days_elapsed": round(float(step.get("days_elapsed", 0.0)), 6),
                    "region_a_force_estimate": round(region_a_force, 6),
                    "region_b_force_estimate": round(region_b_force, 6),
                    "region_a_supply_integrity_index": round(region_a_supply, 6),
                    "region_b_supply_integrity_index": round(region_b_supply, 6),
                    "front_pressure_index": round(front_pressure, 6),
                    "counter_maneuver_index": round(counter_maneuver, 6),
                    "supply_contest_index": round(supply_contest, 6),
                    "encirclement_risk_index": round(encirclement_risk, 6),
                    "withdrawal_pressure_index": round(withdrawal_pressure, 6),
                    "attrition_loss_population": round(attrition_loss, 6),
                    "control_region_id": control_region,
                    "control_balance_index": round(control_balance, 6),
                }
            )
        step_divisor = max(1, len(engagement_steps))
        winner_region = region_a if final_a >= final_b else region_b
        tactical_outcome = (
            "breakthrough"
            if max_pressure < 0.55 and winner_region == origin_region
            else "counter_maneuver"
            if engagement_counter_sum / step_divisor >= 0.58
            else "attritional_stalemate"
            if max_pressure >= 0.66
            else "contested_advance"
        )
        engagement = {
            "id": len(tactical_engagements),
            "conflict_id": conflict_id,
            "era_id": int(conflict.get("era_id", -1)),
            "campaign_movement_id": campaign_id,
            "campaign_front_history_id": int(front.get("id", -1)),
            "region_a": region_a,
            "region_b": region_b,
            "contested_cell_id": int(conflict.get("contested_cell_id", -1)),
            "battle_cell_ids": path_cells,
            "battle_cell_count": len(path_cells),
            "start_year_bp": round(float(conflict.get("start_year_bp", 0.0)), 6),
            "end_year_bp": round(float(conflict.get("end_year_bp", 0.0)), 6),
            "initial_region_a_force": round(initial_a, 6),
            "initial_region_b_force": round(initial_b, 6),
            "final_region_a_force": round(final_a, 6),
            "final_region_b_force": round(final_b, 6),
            "winner_region_id": winner_region,
            "tactical_outcome": tactical_outcome,
            "max_front_pressure_index": round(max_pressure, 6),
            "mean_counter_maneuver_index": round(
                engagement_counter_sum / step_divisor, 6
            ),
            "mean_supply_contest_index": round(
                engagement_supply_sum / step_divisor, 6
            ),
            "total_attrition_loss_population": round(engagement_attrition, 6),
            "step_count": len(engagement_steps),
            "steps": engagement_steps,
        }
        conflict["tactical_engagement_id"] = engagement["id"]
        tactical_engagements.append(engagement)

    step_divisor = float(total_steps) if total_steps else 1.0
    summary_values = {
        "tactical_engagement_step_count": float(total_steps),
        "tactical_total_attrition_loss_population": total_attrition_loss,
        "mean_tactical_counter_maneuver_index": counter_sum / step_divisor
        if total_steps
        else 0.0,
        "mean_tactical_front_pressure_index": pressure_sum / step_divisor
        if total_steps
        else 0.0,
        "mean_tactical_supply_contest_index": supply_contest_sum / step_divisor
        if total_steps
        else 0.0,
        "high_pressure_tactical_step_count": float(high_pressure_steps),
    }
    return tactical_engagements, summary_values


def _strategic_decision_indices(path_cell_ids: list[int]) -> list[int]:
    if not path_cell_ids:
        return []
    candidate_indices = [0, len(path_cell_ids) // 2, len(path_cell_ids) - 1]
    indices: list[int] = []
    for index in candidate_indices:
        bounded = max(0, min(len(path_cell_ids) - 1, index))
        if bounded not in indices:
            indices.append(bounded)
    return indices


def _build_strategic_campaign_plans(
    conflicts: list[dict[str, Any]],
    campaign_movements: list[dict[str, Any]],
    campaign_front_histories: list[dict[str, Any]],
    tactical_engagements: list[dict[str, Any]],
    network_by_region: dict[int, dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, float]]:
    conflicts_by_id = {
        int(conflict.get("id", -1)): conflict
        for conflict in conflicts
        if int(conflict.get("id", -1)) >= 0
    }
    fronts_by_campaign = {
        int(front.get("campaign_movement_id", -1)): front
        for front in campaign_front_histories
        if int(front.get("campaign_movement_id", -1)) >= 0
    }
    tactical_by_campaign = {
        int(engagement.get("campaign_movement_id", -1)): engagement
        for engagement in tactical_engagements
        if int(engagement.get("campaign_movement_id", -1)) >= 0
    }
    strategic_plans: list[dict[str, Any]] = []
    total_decision_points = 0
    independent_counter_count = 0
    counter_viability_sum = 0.0
    confidence_sum = 0.0
    reserve_fraction_sum = 0.0
    high_escalation_count = 0

    for campaign in sorted(
        campaign_movements, key=lambda item: int(item.get("id", -1))
    ):
        campaign_id = int(campaign.get("id", -1))
        conflict_id = int(campaign.get("conflict_id", -1))
        conflict = conflicts_by_id.get(conflict_id)
        front = fronts_by_campaign.get(campaign_id)
        tactical = tactical_by_campaign.get(campaign_id, {})
        if conflict is None or front is None:
            continue
        primary_region = int(campaign.get("origin_region_id", -1))
        counter_region = int(campaign.get("target_region_id", -1))
        if primary_region < 0 or counter_region < 0 or primary_region == counter_region:
            continue
        primary_axis = [int(cell_id) for cell_id in campaign.get("path_cell_ids", [])]
        if len(primary_axis) < 2:
            continue
        counter_axis = list(reversed(primary_axis))
        primary_network = network_by_region.get(primary_region, {})
        counter_network = network_by_region.get(counter_region, {})
        primary_force = max(0.0, float(campaign.get("force_estimate", 0.0)))
        region_a = int(conflict.get("region_a", -1))
        if primary_region == region_a:
            counter_force_base = max(
                0.0, float(conflict.get("region_b_force_estimate", 0.0))
            )
        else:
            counter_force_base = max(
                0.0, float(conflict.get("region_a_force_estimate", 0.0))
            )
        total_force = max(1.0, primary_force + counter_force_base)
        path_supply_loss = _clamp(float(campaign.get("path_supply_loss_index", 0.0)))
        campaign_attrition = _clamp(float(campaign.get("attrition_risk_index", 0.0)))
        campaign_success = _clamp(float(campaign.get("campaign_success_index", 0.0)))
        primary_logistics = _clamp(
            _clamp(float(campaign.get("operational_reach_index", 0.0))) * 0.42
            + _clamp(float(primary_network.get("logistics_resilience_index", 0.0)))
            * 0.32
            + _clamp(float(primary_network.get("transport_efficiency_index", 0.0)))
            * 0.26
        )
        counter_logistics = _clamp(
            _clamp(float(counter_network.get("logistics_resilience_index", 0.0))) * 0.34
            + _clamp(float(counter_network.get("transport_efficiency_index", 0.0)))
            * 0.26
            + (1.0 - campaign_attrition) * 0.20
            + (1.0 - path_supply_loss) * 0.20
        )
        tactical_counter = _clamp(
            float(tactical.get("mean_counter_maneuver_index", 0.0))
        )
        max_front_pressure = _clamp(
            float(tactical.get("max_front_pressure_index", 0.0))
        )
        counter_viability = _clamp(
            counter_logistics * 0.38
            + tactical_counter * 0.24
            + counter_force_base / total_force * 0.22
            + (1.0 - max_front_pressure) * 0.16
        )
        strategic_initiative = _clamp(
            campaign_success * 0.40
            + primary_logistics * 0.30
            + primary_force / total_force * 0.30
        )
        escalation_risk = _clamp(
            _clamp(float(conflict.get("intensity", 0.0))) * 0.30
            + _clamp(float(conflict.get("economic_disruption_index", 0.0))) * 0.22
            + max_front_pressure * 0.22
            + abs(primary_force - counter_force_base) / total_force * 0.12
            + (1.0 - counter_viability) * 0.14
        )
        reserve_fraction = _clamp(
            0.08 + counter_viability * 0.12 + (1.0 - escalation_risk) * 0.10
        )
        primary_force_allocation = max(
            0.0, primary_force * (1.0 - reserve_fraction * 0.50)
        )
        counter_force_allocation = max(
            0.0, counter_force_base * (0.72 + counter_viability * 0.18)
        )
        reserve_force = max(
            0.0, (primary_force + counter_force_base) * reserve_fraction
        )
        operational_complexity = _clamp(
            len(primary_axis) / 36.0 * 0.20
            + _clamp(float(campaign.get("path_terrain_cost_index", 0.0))) * 0.22
            + path_supply_loss * 0.20
            + max_front_pressure * 0.22
            + (1.0 - min(primary_logistics, counter_logistics)) * 0.16
        )
        confidence = _clamp(
            (primary_logistics + counter_logistics) * 0.17
            + (1.0 - operational_complexity) * 0.26
            + campaign_success * 0.20
            + (1.0 - escalation_risk) * 0.20
        )
        counter_mobilization_days = max(
            0.0,
            float(campaign.get("travel_time_days", 0.0))
            * (0.72 + (1.0 - counter_logistics) * 0.44),
        )
        strategic_posture = (
            "counteroffensive"
            if counter_viability >= 0.62
            else "mobile_defense"
            if counter_viability >= 0.45
            else "delaying_defense"
        )
        decisive_cell_ids = [
            primary_axis[index] for index in _strategic_decision_indices(primary_axis)
        ]
        decision_points: list[dict[str, Any]] = []
        for sequence_index, path_index in enumerate(
            _strategic_decision_indices(primary_axis)
        ):
            progress = path_index / max(1, len(primary_axis) - 1)
            pressure_signal = _clamp(
                max_front_pressure * 0.42
                + progress * 0.20
                + escalation_risk * 0.22
                + (1.0 - counter_logistics) * 0.16
            )
            counter_priority = _clamp(
                counter_viability * 0.40
                + tactical_counter * 0.28
                + (1.0 - progress) * 0.16
                + pressure_signal * 0.16
            )
            supply_risk = _clamp(
                path_supply_loss * 0.38
                + campaign_attrition * 0.26
                + progress * 0.20
                + (1.0 - primary_logistics) * 0.16
            )
            phase = (
                "mobilization"
                if sequence_index == 0
                else "counterstroke"
                if path_index == len(primary_axis) - 1
                else "contested_front"
            )
            decision_points.append(
                {
                    "sequence_index": sequence_index,
                    "cell_id": int(primary_axis[path_index]),
                    "path_index": path_index,
                    "plan_phase": phase,
                    "trigger_pressure_index": round(pressure_signal, 6),
                    "counter_maneuver_priority_index": round(counter_priority, 6),
                    "supply_risk_index": round(supply_risk, 6),
                }
            )
        independent_counter = bool(
            len(counter_axis) >= 2
            and counter_force_allocation > 0.0
            and counter_logistics > 0.0
        )
        plan = {
            "id": len(strategic_plans),
            "conflict_id": conflict_id,
            "era_id": int(conflict.get("era_id", -1)),
            "campaign_movement_id": campaign_id,
            "campaign_front_history_id": int(front.get("id", -1)),
            "tactical_engagement_id": int(tactical.get("id", -1)),
            "primary_region_id": primary_region,
            "counter_region_id": counter_region,
            "primary_objective_cell_id": int(campaign.get("target_cell_id", -1)),
            "counter_objective_cell_id": int(campaign.get("origin_cell_id", -1)),
            "primary_axis_cell_ids": primary_axis,
            "counter_axis_cell_ids": counter_axis,
            "primary_axis_cell_count": len(primary_axis),
            "counter_axis_cell_count": len(counter_axis),
            "decisive_cell_ids": decisive_cell_ids,
            "decisive_cell_count": len(decisive_cell_ids),
            "primary_force_allocation_population": round(primary_force_allocation, 6),
            "counter_force_allocation_population": round(counter_force_allocation, 6),
            "reserve_force_population": round(reserve_force, 6),
            "reserve_fraction": round(reserve_fraction, 6),
            "primary_logistics_score": round(primary_logistics, 6),
            "counter_logistics_score": round(counter_logistics, 6),
            "counter_campaign_viability_index": round(counter_viability, 6),
            "strategic_initiative_index": round(strategic_initiative, 6),
            "escalation_risk_index": round(escalation_risk, 6),
            "operational_complexity_index": round(operational_complexity, 6),
            "plan_confidence_index": round(confidence, 6),
            "expected_campaign_duration_days": round(
                float(campaign.get("travel_time_days", 0.0)), 6
            ),
            "counter_mobilization_days": round(counter_mobilization_days, 6),
            "strategic_posture": strategic_posture,
            "independent_counter_campaign_planned": independent_counter,
            "decision_point_count": len(decision_points),
            "decision_points": decision_points,
        }
        conflict["strategic_campaign_plan_id"] = plan["id"]
        strategic_plans.append(plan)
        total_decision_points += len(decision_points)
        independent_counter_count += int(independent_counter)
        counter_viability_sum += counter_viability
        confidence_sum += confidence
        reserve_fraction_sum += reserve_fraction
        high_escalation_count += int(escalation_risk >= 0.65)

    plan_divisor = float(len(strategic_plans)) if strategic_plans else 1.0
    summary_values = {
        "strategic_decision_point_count": float(total_decision_points),
        "independent_counter_campaign_plan_count": float(independent_counter_count),
        "mean_counter_campaign_viability_index": counter_viability_sum / plan_divisor
        if strategic_plans
        else 0.0,
        "mean_strategic_plan_confidence_index": confidence_sum / plan_divisor
        if strategic_plans
        else 0.0,
        "mean_strategic_force_reserve_fraction": reserve_fraction_sum / plan_divisor
        if strategic_plans
        else 0.0,
        "high_escalation_strategic_plan_count": float(high_escalation_count),
    }
    return strategic_plans, summary_values


def _expected_campaign_operations(
    payload: dict[str, Any],
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[int, dict[str, Any]],
    dict[str, Any],
]:
    routes = payload["routes"]
    trade_flows = payload["trade_flows"]
    conflicts = [dict(conflict) for conflict in payload["conflicts"]]
    for conflict in conflicts:
        conflict.pop("campaign_movement_id", None)
        conflict.pop("tactical_engagement_id", None)
        conflict.pop("strategic_campaign_plan_id", None)
    cells = payload["cells"]
    radius_km = planet_radius_km(payload)
    settlement_regions = _settlement_regions(payload)
    borders_by_pair = _border_by_pair(payload)
    route_by_id = _index_records(routes)
    regions_by_id = _index_records(payload["political_regions"])
    settlements_by_id = _index_records(payload["settlements"])
    cells_by_id = _index_records(cells)
    networks, _, _ = _expected_logistics_exchanges(payload)
    network_by_region = {
        int(network.get("region_id", -1)): network for network in networks
    }

    campaign_movements: list[dict[str, Any]] = []
    campaign_path_segments: list[dict[str, Any]] = []
    campaign_front_histories: list[dict[str, Any]] = []
    travel_time_sum = 0.0
    attrition_sum = 0.0
    reach_sum = 0.0
    total_campaign_force = 0.0
    high_attrition_campaigns = 0
    campaign_path_length_sum = 0.0
    campaign_path_terrain_sum = 0.0
    campaign_path_supply_loss_sum = 0.0
    campaign_path_attrition_sum = 0.0
    high_attrition_path_segments = 0
    campaign_front_step_count = 0
    campaign_front_supply_integrity_sum = 0.0
    campaign_front_control_sum = 0.0
    campaign_front_attrition_loss_sum = 0.0

    trade_by_pair: dict[tuple[int, int], dict[str, Any]] = {}
    for trade in trade_flows:
        region_from = int(trade.get("region_from", -1))
        region_to = int(trade.get("region_to", -1))
        if region_from < 0 or region_to < 0 or region_from == region_to:
            continue
        key = _border_pair_key(region_from, region_to)
        existing = trade_by_pair.get(key)
        if existing is None or float(trade.get("volume_index", 0.0)) > float(
            existing.get("volume_index", 0.0)
        ):
            trade_by_pair[key] = trade

    for conflict in sorted(conflicts, key=lambda item: int(item.get("id", -1))):
        conflict_id = int(conflict.get("id", -1))
        region_a = int(conflict.get("region_a", -1))
        region_b = int(conflict.get("region_b", -1))
        if region_a < 0 or region_b < 0 or region_a == region_b:
            continue
        force_a = max(0.0, float(conflict.get("region_a_force_estimate", 0.0)))
        force_b = max(0.0, float(conflict.get("region_b_force_estimate", 0.0)))
        outcome = str(conflict.get("outcome", "contested"))
        if outcome == "region_b_victory":
            origin_region, target_region, force, defending_force = (
                region_b,
                region_a,
                force_b,
                force_a,
            )
        elif outcome == "region_a_victory":
            origin_region, target_region, force, defending_force = (
                region_a,
                region_b,
                force_a,
                force_b,
            )
        elif force_b > force_a:
            origin_region, target_region, force, defending_force = (
                region_b,
                region_a,
                force_b,
                force_a,
            )
        else:
            origin_region, target_region, force, defending_force = (
                region_a,
                region_b,
                force_a,
                force_b,
            )
        pair_key = _border_pair_key(region_a, region_b)
        trade = trade_by_pair.get(pair_key, {})
        route_id = int(trade.get("route_id", -1))
        route = route_by_id.get(route_id, {})
        route_type = str(route.get("type", "border_crossing"))
        border = borders_by_pair.get(pair_key, {})
        border_id = int(border.get("id", -1))
        border_barrier = _clamp(float(border.get("barrier_score", 0.55)))
        friction = _clamp(float(trade.get("friction", border_barrier)))
        origin_cell_id, target_cell_id = _campaign_endpoint_cells(
            conflict,
            route,
            origin_region,
            target_region,
            regions_by_id,
            settlements_by_id,
            settlement_regions,
            cells_by_id,
            radius_km,
        )
        path_cell_ids = _shortest_campaign_path(
            origin_cell_id,
            target_cell_id,
            cells_by_id,
            route_type,
            radius_km,
        )
        if len(path_cell_ids) < 2:
            path_cell_ids = []
            origin_cell = cells_by_id.get(origin_cell_id, {})
            for neighbor_id_raw in origin_cell.get("neighbors", []):
                neighbor_id = int(neighbor_id_raw)
                if neighbor_id in cells_by_id and neighbor_id != origin_cell_id:
                    target_cell_id = neighbor_id
                    path_cell_ids = [origin_cell_id, target_cell_id]
                    break
        if len(path_cell_ids) < 2:
            continue
        segment_geometries: list[dict[str, Any]] = []
        path_length = 0.0
        terrain_weighted_sum = 0.0
        for first_id, second_id in zip(path_cell_ids, path_cell_ids[1:]):
            first_cell = cells_by_id.get(first_id, {})
            second_cell = cells_by_id.get(second_id, {})
            segment_distance = (
                _cell_distance_km(first_cell, second_cell, radius_km)
                if first_cell and second_cell
                else 0.0
            )
            terrain_cost = (
                _campaign_terrain_cost(first_cell, second_cell, route_type)
                if first_cell and second_cell
                else friction
            )
            elevation_gain = max(
                0.0,
                float(second_cell.get("elevation_m", 0.0))
                - float(first_cell.get("elevation_m", 0.0)),
            )
            water_crossing = bool(first_cell.get("is_water", False)) or bool(
                second_cell.get("is_water", False)
            )
            barrier_cost = _clamp(
                terrain_cost * 0.48 + border_barrier * 0.26 + friction * 0.26
            )
            segment_geometries.append(
                {
                    "from_cell_id": first_id,
                    "to_cell_id": second_id,
                    "distance_km": segment_distance,
                    "terrain_cost_index": terrain_cost,
                    "elevation_gain_m": elevation_gain,
                    "water_crossing": water_crossing,
                    "barrier_cost_index": barrier_cost,
                }
            )
            path_length += segment_distance
            terrain_weighted_sum += terrain_cost * segment_distance
        fallback_distance = max(
            1.0,
            float(trade.get("distance_km", 0.0))
            or float(route.get("distance_km", 0.0))
            or float(border.get("length_km", 0.0)) * 1.6
            or 320.0,
        )
        if path_length <= 0.0:
            path_length = fallback_distance
        terrain_mean = (
            _clamp(terrain_weighted_sum / max(1.0, path_length))
            if segment_geometries
            else friction
        )
        daily_km = max(
            6.0,
            30.0 * (1.0 - friction * 0.35) * (1.0 - terrain_mean * 0.45),
        )
        travel_time = path_length / daily_km
        duration = max(0.0, float(conflict.get("war_duration_years", 0.0)))
        origin_network = network_by_region.get(origin_region, {})
        army_capacity = max(
            1.0, float(origin_network.get("army_capacity_population", 1.0))
        )
        supply_required = _clamp(
            force / army_capacity * 0.46
            + duration / 900.0 * 0.22
            + path_length / 8000.0 * 0.20
            + terrain_mean * 0.12
        )
        attrition_risk = _clamp(
            _clamp(float(conflict.get("logistics_strain_index", 0.0))) * 0.42
            + friction * 0.22
            + supply_required * 0.24
            + duration / 1200.0 * 0.12
        )
        reach = _clamp(
            (1.0 - attrition_risk) * 0.42
            + float(origin_network.get("logistics_resilience_index", 0.0)) * 0.34
            + float(origin_network.get("transport_efficiency_index", 0.0)) * 0.24
        )
        success_base = (
            0.70 if outcome in {"region_a_victory", "region_b_victory"} else 0.50
        )
        success = _clamp(
            success_base * 0.45 + reach * 0.34 + (1.0 - attrition_risk) * 0.21
        )
        movement_id = len(campaign_movements)
        segment_ids: list[int] = []
        elapsed_days = 0.0
        path_supply_loss_sum = 0.0
        path_attrition_sum = 0.0
        for sequence_index, segment in enumerate(segment_geometries):
            segment_distance = float(segment["distance_km"])
            elapsed_days += segment_distance / daily_km
            terrain_cost = float(segment["terrain_cost_index"])
            supply_loss = _clamp(
                supply_required * 0.34
                + terrain_cost * 0.30
                + float(segment["barrier_cost_index"]) * 0.18
                + segment_distance / max(1.0, path_length) * 0.18
            )
            segment_attrition = _clamp(
                attrition_risk * 0.44 + terrain_cost * 0.26 + supply_loss * 0.30
            )
            segment_id = len(campaign_path_segments)
            segment_ids.append(segment_id)
            campaign_path_segments.append(
                {
                    "id": segment_id,
                    "campaign_movement_id": movement_id,
                    "sequence_index": sequence_index,
                    "from_cell_id": int(segment["from_cell_id"]),
                    "to_cell_id": int(segment["to_cell_id"]),
                    "route_mode": route_type,
                    "distance_km": round(segment_distance, 6),
                    "elapsed_days": round(elapsed_days, 6),
                    "terrain_cost_index": round(terrain_cost, 6),
                    "barrier_cost_index": round(
                        float(segment["barrier_cost_index"]), 6
                    ),
                    "supply_loss_index": round(supply_loss, 6),
                    "attrition_index": round(segment_attrition, 6),
                    "elevation_gain_m": round(float(segment["elevation_gain_m"]), 6),
                    "water_crossing": bool(segment["water_crossing"]),
                }
            )
            path_supply_loss_sum += supply_loss * segment_distance
            path_attrition_sum += segment_attrition * segment_distance
            campaign_path_terrain_sum += terrain_cost
            campaign_path_supply_loss_sum += supply_loss
            campaign_path_attrition_sum += segment_attrition
            high_attrition_path_segments += int(segment_attrition >= 0.65)
        path_supply_loss = (
            _clamp(path_supply_loss_sum / max(1.0, path_length))
            if segment_geometries
            else supply_required
        )
        path_attrition = (
            _clamp(path_attrition_sum / max(1.0, path_length))
            if segment_geometries
            else attrition_risk
        )
        front_steps: list[dict[str, Any]] = []
        occupied_cell_ids: list[int] = []
        cumulative_distance = 0.0
        remaining_attacker = force
        remaining_defender = defending_force
        supply_integrity_sum = 0.0
        control_sum = 0.0
        max_supply_line = 0.0
        for step_index, cell_id in enumerate(path_cell_ids):
            if step_index > 0 and step_index - 1 < len(segment_geometries):
                previous_segment = segment_geometries[step_index - 1]
                cumulative_distance += float(previous_segment.get("distance_km", 0.0))
                segment_attrition = (
                    float(
                        campaign_path_segments[segment_ids[step_index - 1]].get(
                            "attrition_index", path_attrition
                        )
                    )
                    if step_index - 1 < len(segment_ids)
                    else path_attrition
                )
                segment_supply_loss = (
                    float(
                        campaign_path_segments[segment_ids[step_index - 1]].get(
                            "supply_loss_index", path_supply_loss
                        )
                    )
                    if step_index - 1 < len(segment_ids)
                    else path_supply_loss
                )
            else:
                segment_attrition = attrition_risk * 0.35
                segment_supply_loss = supply_required * 0.30
            progress = step_index / max(1, len(path_cell_ids) - 1)
            local_attrition = _clamp(
                segment_attrition * 0.58 + progress * 0.12 + border_barrier * 0.10
            )
            attrition_loss = remaining_attacker * local_attrition * 0.018
            defender_loss = remaining_defender * _clamp(
                local_attrition * 0.014 + success * 0.008
            )
            remaining_attacker = max(0.0, remaining_attacker - attrition_loss)
            remaining_defender = max(0.0, remaining_defender - defender_loss)
            if cell_id not in occupied_cell_ids:
                occupied_cell_ids.append(cell_id)
            supply_integrity = _clamp(
                1.0
                - segment_supply_loss * 0.42
                - cumulative_distance / max(1.0, path_length) * 0.28
                + float(origin_network.get("logistics_resilience_index", 0.0)) * 0.18
            )
            occupation_control = _clamp(
                success * 0.34
                + supply_integrity * 0.26
                + progress * 0.24
                + (remaining_attacker / max(1.0, force)) * 0.16
            )
            front_cell = cells_by_id.get(cell_id, {})
            front_neighbors = [
                int(neighbor_id)
                for neighbor_id in front_cell.get("neighbors", [])
                if int(neighbor_id) in cells_by_id
                and int(neighbor_id) not in occupied_cell_ids
            ][:6]
            front_width = _clamp(len(front_neighbors) / 6.0)
            elapsed = travel_time * progress
            max_supply_line = max(max_supply_line, cumulative_distance)
            supply_integrity_sum += supply_integrity
            control_sum += occupation_control
            campaign_front_supply_integrity_sum += supply_integrity
            campaign_front_control_sum += occupation_control
            campaign_front_attrition_loss_sum += attrition_loss
            campaign_front_step_count += 1
            front_steps.append(
                {
                    "sequence_index": step_index,
                    "cell_id": cell_id,
                    "days_elapsed": round(elapsed, 6),
                    "occupied_cell_ids": list(occupied_cell_ids),
                    "occupied_cell_count": len(occupied_cell_ids),
                    "front_line_cell_ids": front_neighbors,
                    "front_line_cell_count": len(front_neighbors),
                    "supply_line_length_km": round(cumulative_distance, 6),
                    "supply_integrity_index": round(supply_integrity, 6),
                    "attacking_force_estimate": round(remaining_attacker, 6),
                    "defending_force_estimate": round(remaining_defender, 6),
                    "attrition_loss_population": round(attrition_loss, 6),
                    "local_attrition_index": round(local_attrition, 6),
                    "occupation_control_index": round(occupation_control, 6),
                    "front_width_index": round(front_width, 6),
                    "contested": step_index < len(path_cell_ids) - 1
                    and occupation_control < 0.72,
                }
            )
        front_history_id = len(campaign_front_histories)
        campaign_front_histories.append(
            {
                "id": front_history_id,
                "campaign_movement_id": movement_id,
                "conflict_id": conflict_id,
                "origin_region_id": origin_region,
                "target_region_id": target_region,
                "attacking_force_initial": round(force, 6),
                "defending_force_initial": round(defending_force, 6),
                "final_attacking_force_estimate": round(remaining_attacker, 6),
                "final_defending_force_estimate": round(remaining_defender, 6),
                "start_year_bp": round(float(conflict.get("start_year_bp", 0.0)), 6),
                "end_year_bp": round(float(conflict.get("end_year_bp", 0.0)), 6),
                "route_mode": route_type,
                "path_cell_ids": path_cell_ids,
                "path_segment_ids": segment_ids,
                "step_count": len(front_steps),
                "captured_cell_count": len(occupied_cell_ids),
                "final_occupied_cell_id": occupied_cell_ids[-1]
                if occupied_cell_ids
                else -1,
                "max_supply_line_length_km": round(max_supply_line, 6),
                "mean_supply_integrity_index": round(
                    supply_integrity_sum / len(front_steps), 6
                )
                if front_steps
                else 0.0,
                "mean_occupation_control_index": round(
                    control_sum / len(front_steps), 6
                )
                if front_steps
                else 0.0,
                "outcome_projection": "breakthrough"
                if success >= 0.66
                else "contested_front"
                if success >= 0.48
                else "stalled",
                "steps": front_steps,
            }
        )
        movement = {
            "id": movement_id,
            "conflict_id": conflict_id,
            "era_id": int(conflict.get("era_id", -1)),
            "origin_region_id": origin_region,
            "target_region_id": target_region,
            "origin_cell_id": origin_cell_id,
            "target_cell_id": target_cell_id,
            "contested_cell_id": int(conflict.get("contested_cell_id", -1)),
            "route_id": route_id,
            "border_id": border_id,
            "path_cell_ids": path_cell_ids,
            "path_cell_count": len(path_cell_ids),
            "path_segment_ids": segment_ids,
            "path_segment_count": len(segment_ids),
            "path_length_km": round(path_length, 6),
            "path_terrain_cost_index": round(terrain_mean, 6),
            "path_supply_loss_index": round(path_supply_loss, 6),
            "path_attrition_index": round(path_attrition, 6),
            "campaign_front_history_id": front_history_id,
            "start_year_bp": round(float(conflict.get("start_year_bp", 0.0)), 6),
            "end_year_bp": round(float(conflict.get("end_year_bp", 0.0)), 6),
            "distance_km": round(path_length, 6),
            "travel_time_days": round(travel_time, 6),
            "force_estimate": round(force, 6),
            "supply_required_index": round(supply_required, 6),
            "attrition_risk_index": round(attrition_risk, 6),
            "logistics_strain_index": round(
                _clamp(float(conflict.get("logistics_strain_index", 0.0))), 6
            ),
            "operational_reach_index": round(reach, 6),
            "campaign_success_index": round(success, 6),
            "outcome": outcome,
        }
        conflict["campaign_movement_id"] = movement["id"]
        campaign_movements.append(movement)
        travel_time_sum += travel_time
        attrition_sum += attrition_risk
        reach_sum += reach
        total_campaign_force += force
        campaign_path_length_sum += path_length
        high_attrition_campaigns += int(attrition_risk >= 0.65)

    tactical_engagements, tactical_summary = _build_tactical_engagements(
        conflicts, campaign_movements, campaign_front_histories
    )
    strategic_campaign_plans, strategic_summary = _build_strategic_campaign_plans(
        conflicts,
        campaign_movements,
        campaign_front_histories,
        tactical_engagements,
        network_by_region,
    )
    campaign_count = len(campaign_movements)
    campaign_segment_count = len(campaign_path_segments)
    campaign_front_count = len(campaign_front_histories)
    summary = {
        "campaign_movement_count": campaign_count,
        "campaign_path_segment_count": campaign_segment_count,
        "campaign_front_history_count": campaign_front_count,
        "tactical_engagement_count": len(tactical_engagements),
        "strategic_campaign_plan_count": len(strategic_campaign_plans),
        "campaign_front_step_count": campaign_front_step_count,
        "tactical_engagement_step_count": int(
            tactical_summary["tactical_engagement_step_count"]
        ),
        "strategic_decision_point_count": int(
            strategic_summary["strategic_decision_point_count"]
        ),
        "total_campaign_mobilized_population": round(total_campaign_force, 6),
        "total_campaign_path_length_km": round(campaign_path_length_sum, 6),
        "mean_campaign_travel_time_days": round(
            travel_time_sum / campaign_count, 6
        )
        if campaign_count
        else 0.0,
        "mean_campaign_attrition_risk_index": round(
            attrition_sum / campaign_count, 6
        )
        if campaign_count
        else 0.0,
        "mean_campaign_operational_reach_index": round(
            reach_sum / campaign_count, 6
        )
        if campaign_count
        else 0.0,
        "mean_campaign_path_length_km": round(
            campaign_path_length_sum / campaign_count, 6
        )
        if campaign_count
        else 0.0,
        "mean_campaign_path_terrain_cost_index": round(
            campaign_path_terrain_sum / campaign_segment_count, 6
        )
        if campaign_segment_count
        else 0.0,
        "mean_campaign_path_supply_loss_index": round(
            campaign_path_supply_loss_sum / campaign_segment_count, 6
        )
        if campaign_segment_count
        else 0.0,
        "mean_campaign_path_attrition_index": round(
            campaign_path_attrition_sum / campaign_segment_count, 6
        )
        if campaign_segment_count
        else 0.0,
        "mean_campaign_front_supply_integrity_index": round(
            campaign_front_supply_integrity_sum / campaign_front_step_count, 6
        )
        if campaign_front_step_count
        else 0.0,
        "mean_campaign_front_control_index": round(
            campaign_front_control_sum / campaign_front_step_count, 6
        )
        if campaign_front_step_count
        else 0.0,
        "total_campaign_front_attrition_loss_population": round(
            campaign_front_attrition_loss_sum, 6
        ),
        "tactical_total_attrition_loss_population": round(
            tactical_summary["tactical_total_attrition_loss_population"], 6
        ),
        "mean_tactical_counter_maneuver_index": round(
            tactical_summary["mean_tactical_counter_maneuver_index"], 6
        ),
        "mean_tactical_front_pressure_index": round(
            tactical_summary["mean_tactical_front_pressure_index"], 6
        ),
        "mean_tactical_supply_contest_index": round(
            tactical_summary["mean_tactical_supply_contest_index"], 6
        ),
        "high_pressure_tactical_step_count": int(
            tactical_summary["high_pressure_tactical_step_count"]
        ),
        "independent_counter_campaign_plan_count": int(
            strategic_summary["independent_counter_campaign_plan_count"]
        ),
        "mean_counter_campaign_viability_index": round(
            strategic_summary["mean_counter_campaign_viability_index"], 6
        ),
        "mean_strategic_plan_confidence_index": round(
            strategic_summary["mean_strategic_plan_confidence_index"], 6
        ),
        "mean_strategic_force_reserve_fraction": round(
            strategic_summary["mean_strategic_force_reserve_fraction"], 6
        ),
        "high_escalation_strategic_plan_count": int(
            strategic_summary["high_escalation_strategic_plan_count"]
        ),
        "high_attrition_campaign_count": high_attrition_campaigns,
        "high_attrition_campaign_path_segment_count": high_attrition_path_segments,
    }
    annotation_keys = (
        "campaign_movement_id",
        "tactical_engagement_id",
        "strategic_campaign_plan_id",
    )
    conflict_annotations = {
        int(conflict.get("id", -1)): {
            key: conflict[key] for key in annotation_keys if key in conflict
        }
        for conflict in conflicts
        if int(conflict.get("id", -1)) >= 0
    }
    return (
        campaign_movements,
        campaign_path_segments,
        campaign_front_histories,
        tactical_engagements,
        strategic_campaign_plans,
        conflict_annotations,
        summary,
    )


def _contains_expected(actual: Any, expected: Any) -> bool:
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(
            key in actual and _contains_expected(actual[key], value)
            for key, value in expected.items()
        )
    if isinstance(expected, list):
        return (
            isinstance(actual, list)
            and len(actual) == len(expected)
            and all(
                _contains_expected(actual_item, expected_item)
                for actual_item, expected_item in zip(actual, expected, strict=True)
            )
        )
    return actual == expected


def validate_campaign_operations_replay(payload: dict[str, Any]) -> list[str]:
    from .logistics_availability_validation import uses_logistics_availability
    try:
        if uses_logistics_availability(payload):
            from .campaign_availability_validation import validate_campaign_availability
            return validate_campaign_availability(payload)
    except (TypeError, ValueError, KeyError, OverflowError):
        return ["campaign operations model or causal replay invalid"]
    try:
        planet_radius_km(payload)
    except ValueError as exc:
        return [f"campaign operations replay rejected: {exc}"]
    try:
        summary = payload.get("summary", {})
        required_lists = (
            "political_regions",
            "routes",
            "trade_flows",
            "conflicts",
            "cells",
            "borders",
            "settlements",
            "economy_histories",
            "campaign_movements",
            "campaign_path_segments",
            "campaign_front_histories",
            "tactical_engagements",
            "strategic_campaign_plans",
        )
        valid = isinstance(summary, dict) and all(
            isinstance(payload.get(name), list) for name in required_lists
        )
        valid = valid and payload.get("campaign_operations_model") == _campaign_operations_model()
        valid = valid and summary.get("campaign_operations_model") == CAMPAIGN_OPERATIONS_MODEL
        (
            movements,
            segments,
            fronts,
            tactical,
            strategic,
            conflict_annotations,
            expected_summary,
        ) = _expected_campaign_operations(payload)
        valid = valid and _contains_expected(payload.get("campaign_movements"), movements)
        valid = valid and _contains_expected(payload.get("campaign_path_segments"), segments)
        valid = valid and _contains_expected(payload.get("campaign_front_histories"), fronts)
        valid = valid and _contains_expected(payload.get("tactical_engagements"), tactical)
        valid = valid and _contains_expected(
            payload.get("strategic_campaign_plans"), strategic
        )
        valid = valid and all(
            summary.get(key) == value for key, value in expected_summary.items()
        )
        conflicts_by_id = {
            int(conflict.get("id", -1)): conflict for conflict in payload["conflicts"]
        }
        valid = valid and all(
            conflict_id in conflicts_by_id
            and _contains_expected(conflicts_by_id[conflict_id], annotations)
            for conflict_id, annotations in conflict_annotations.items()
        )
    except (
        AttributeError,
        IndexError,
        KeyError,
        OverflowError,
        TypeError,
        ValueError,
        ZeroDivisionError,
    ):
        valid = False
    return [] if valid else ["campaign operations model or causal replay invalid"]
