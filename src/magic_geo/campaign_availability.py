"""Campaign geometry and conditional operations on audited social inputs.

The complete-input equations are retained from logistics_history. Unknown
capacity propagates only into dependent operations; path geometry stays known.
"""
from __future__ import annotations
from typing import Any
from .planet_parameters import planet_radius_km
from .logistics_availability import _calculate, _aggregate
from .logistics_history import (
    _clamp, _settlement_regions, _border_by_pair, _index_records,
    _border_pair_key, _campaign_endpoint_cells, _shortest_campaign_path,
    _cell_distance_km, _campaign_terrain_cost, _build_tactical_engagements,
    _build_strategic_campaign_plans,
)

MOVEMENT_ESTIMATES = (
    "path_length_km", "path_terrain_cost_index", "path_supply_loss_index", "path_attrition_index",
    "distance_km", "travel_time_days", "force_estimate", "supply_required_index",
    "attrition_risk_index", "logistics_strain_index", "operational_reach_index", "campaign_success_index",
)
SEGMENT_ESTIMATES = (
    "distance_km", "elapsed_days", "terrain_cost_index", "barrier_cost_index",
    "supply_loss_index", "attrition_index", "elevation_gain_m",
)


def _rounded(value):
    return None if value is None else round(value, 6)


def campaign_records(world: dict[str, Any], network_by_region: dict[int, dict[str, Any]]) -> dict[str, Any]:
    radius_km = planet_radius_km(world)
    trade_flows = world["trade_flows"]
    conflicts = [dict(row) for row in world["conflicts"]]
    for row in conflicts:
        for key in ("campaign_movement_id", "tactical_engagement_id", "strategic_campaign_plan_id"):
            row.pop(key, None)
    settlement_regions = _settlement_regions(world)
    borders_by_pair = _border_by_pair(world)
    route_by_id = _index_records(world["routes"])
    regions_by_id = _index_records(world["political_regions"])
    settlements_by_id = _index_records(world["settlements"])
    cells_by_id = _index_records(world["cells"])
    campaign_movements: list[dict[str, Any]] = []
    campaign_path_segments: list[dict[str, Any]] = []
    campaign_front_histories: list[dict[str, Any]] = []
    tactical_engagements: list[dict[str, Any]] = []
    strategic_campaign_plans: list[dict[str, Any]] = []
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
        if existing is None or float(trade.get("volume_index", 0.0)) > float(existing.get("volume_index", 0.0)):
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
            origin_region, target_region, force, defending_force = region_b, region_a, force_b, force_a
        elif outcome == "region_a_victory":
            origin_region, target_region, force, defending_force = region_a, region_b, force_a, force_b
        elif force_b > force_a:
            origin_region, target_region, force, defending_force = region_b, region_a, force_b, force_a
        else:
            origin_region, target_region, force, defending_force = region_a, region_b, force_a, force_b
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
            terrain_cost = _campaign_terrain_cost(first_cell, second_cell, route_type) if first_cell and second_cell else friction
            elevation_gain = max(0.0, float(second_cell.get("elevation_m", 0.0)) - float(first_cell.get("elevation_m", 0.0)))
            water_crossing = bool(first_cell.get("is_water", False)) or bool(second_cell.get("is_water", False))
            barrier_cost = _clamp(terrain_cost * 0.48 + border_barrier * 0.26 + friction * 0.26)
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
        terrain_mean = _clamp(terrain_weighted_sum / max(1.0, path_length)) if segment_geometries else friction
        daily_km = max(6.0, 30.0 * (1.0 - friction * 0.35) * (1.0 - terrain_mean * 0.45))
        travel_time = path_length / daily_km
        duration = max(0.0, float(conflict.get("war_duration_years", 0.0)))
        origin_network = network_by_region.get(origin_region, {})
        army_capacity = origin_network["army_capacity_population"]
        supply_required = _calculate(
            lambda army: _clamp(force / max(1.0, army) * .46 + duration / 900 * .22 + path_length / 8000 * .20 + terrain_mean * .12), army_capacity)
        attrition_risk = _calculate(lambda supply: _clamp(
            _clamp(float(conflict["logistics_strain_index"])) * .42 + friction * .22 + supply * .24 + duration / 1200 * .12), supply_required)
        reach = _calculate(lambda attrition, resilience: _clamp(
            (1 - attrition) * .42 + resilience * .34 + origin_network["transport_efficiency_index"] * .24), attrition_risk, origin_network["logistics_resilience_index"])
        success_base = .70 if outcome in {"region_a_victory", "region_b_victory"} else .50
        success = _calculate(lambda r, a: _clamp(success_base * .45 + r * .34 + (1 - a) * .21), reach, attrition_risk)
        movement_id = len(campaign_movements)
        segment_ids: list[int] = []
        elapsed_days = 0.0
        path_supply_loss_sum = 0.0
        path_attrition_sum = 0.0
        for sequence_index, segment in enumerate(segment_geometries):
            segment_distance = float(segment["distance_km"])
            elapsed_days += segment_distance / daily_km
            terrain_cost = float(segment["terrain_cost_index"])
            supply_loss = _calculate(lambda required: _clamp(
                required * .34 + terrain_cost * .30 + float(segment["barrier_cost_index"]) * .18 + segment_distance / max(1.0, path_length) * .18), supply_required)
            segment_attrition = _calculate(lambda risk, loss: _clamp(risk * .44 + terrain_cost * .26 + loss * .30), attrition_risk, supply_loss)
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
                    "barrier_cost_index": round(float(segment["barrier_cost_index"]), 6),
                    "supply_loss_index": _rounded(supply_loss),
                    "attrition_index": _rounded(segment_attrition),
                    "elevation_gain_m": round(float(segment["elevation_gain_m"]), 6),
                    "water_crossing": bool(segment["water_crossing"]),
                }
            )
            path_supply_loss_sum = _calculate(lambda total, value, distance: total + value * distance, path_supply_loss_sum, supply_loss, segment_distance)
            path_attrition_sum = _calculate(lambda total, value, distance: total + value * distance, path_attrition_sum, segment_attrition, segment_distance)
            campaign_path_terrain_sum += terrain_cost
            campaign_path_supply_loss_sum = _calculate(lambda total, value: total + value, campaign_path_supply_loss_sum, supply_loss)
            campaign_path_attrition_sum = _calculate(lambda total, value: total + value, campaign_path_attrition_sum, segment_attrition)
            high_attrition_path_segments = _calculate(lambda total, value: total + int(value >= .65), high_attrition_path_segments, segment_attrition)
        path_supply_loss = _calculate(lambda total: _clamp(total / max(1.0, path_length)), path_supply_loss_sum) if segment_geometries else supply_required
        path_attrition = _calculate(lambda total: _clamp(total / max(1.0, path_length)), path_attrition_sum) if segment_geometries else attrition_risk
        front_history_id = None
        if success is not None:
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
                        float(campaign_path_segments[segment_ids[step_index - 1]].get("attrition_index", path_attrition))
                        if step_index - 1 < len(segment_ids)
                        else path_attrition
                    )
                    segment_supply_loss = (
                        float(campaign_path_segments[segment_ids[step_index - 1]].get("supply_loss_index", path_supply_loss))
                        if step_index - 1 < len(segment_ids)
                        else path_supply_loss
                    )
                else:
                    segment_attrition = attrition_risk * 0.35
                    segment_supply_loss = supply_required * 0.30
                progress = step_index / max(1, len(path_cell_ids) - 1)
                local_attrition = _clamp(segment_attrition * 0.58 + progress * 0.12 + border_barrier * 0.10)
                attrition_loss = remaining_attacker * local_attrition * 0.018
                defender_loss = remaining_defender * _clamp(local_attrition * 0.014 + success * 0.008)
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
                occupation_control = _clamp(success * 0.34 + supply_integrity * 0.26 + progress * 0.24 + (remaining_attacker / max(1.0, force)) * 0.16)
                front_cell = cells_by_id.get(cell_id, {})
                front_neighbors = [
                    int(neighbor_id)
                    for neighbor_id in front_cell.get("neighbors", [])
                    if int(neighbor_id) in cells_by_id and int(neighbor_id) not in occupied_cell_ids
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
                        "contested": step_index < len(path_cell_ids) - 1 and occupation_control < 0.72,
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
                    "final_occupied_cell_id": occupied_cell_ids[-1] if occupied_cell_ids else -1,
                    "max_supply_line_length_km": round(max_supply_line, 6),
                    "mean_supply_integrity_index": round(supply_integrity_sum / len(front_steps), 6) if front_steps else 0.0,
                    "mean_occupation_control_index": round(control_sum / len(front_steps), 6) if front_steps else 0.0,
                    "outcome_projection": "breakthrough" if success >= 0.66 else ("contested_front" if success >= 0.48 else "stalled"),
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
            "path_supply_loss_index": _rounded(path_supply_loss),
            "path_attrition_index": _rounded(path_attrition),
            "campaign_front_history_id": front_history_id,
            "start_year_bp": round(float(conflict.get("start_year_bp", 0.0)), 6),
            "end_year_bp": round(float(conflict.get("end_year_bp", 0.0)), 6),
            "distance_km": round(path_length, 6),
            "travel_time_days": round(travel_time, 6),
            "force_estimate": round(force, 6),
            "supply_required_index": _rounded(supply_required),
            "attrition_risk_index": _rounded(attrition_risk),
            "logistics_strain_index": round(_clamp(float(conflict.get("logistics_strain_index", 0.0))), 6),
            "operational_reach_index": _rounded(reach),
            "campaign_success_index": _rounded(success),
            "outcome": outcome,
        }
        conflict["campaign_movement_id"] = movement["id"]
        campaign_movements.append(movement)
        travel_time_sum += travel_time
        attrition_sum = _calculate(lambda total, value: total + value, attrition_sum, attrition_risk)
        reach_sum = _calculate(lambda total, value: total + value, reach_sum, reach)
        total_campaign_force += force
        campaign_path_length_sum += path_length
        high_attrition_campaigns = _calculate(lambda total, value: total + int(value >= .65), high_attrition_campaigns, attrition_risk)

    tactical_engagements, tactical_summary = _build_tactical_engagements(
        conflicts,
        campaign_movements,
        campaign_front_histories,
    )
    strategic_campaign_plans, strategic_summary = _build_strategic_campaign_plans(
        conflicts,
        [row for row in campaign_movements if network_by_region[row["target_region_id"]]["logistics_resilience_index"] is not None],
        campaign_front_histories,
        tactical_engagements,
        network_by_region,
    )

    result = {
        "campaign_movements": campaign_movements,
        "campaign_path_segments": campaign_path_segments,
        "campaign_front_histories": campaign_front_histories,
        "tactical_engagements": tactical_engagements,
        "strategic_campaign_plans": strategic_campaign_plans,
        "conflicts": conflicts,
    }
    return _publish_coverage(world, result, network_by_region)


def _publish_coverage(world, result, networks):
    movements = result["campaign_movements"]
    segments = result["campaign_path_segments"]
    fronts = result["campaign_front_histories"]
    tactical = result["tactical_engagements"]
    strategic = result["strategic_campaign_plans"]
    complete_conflicts = world["native_social_availability"]["conflict_inference_available"]
    by_conflict = {row["conflict_id"]: row for row in movements}
    for rows, fields in ((movements, MOVEMENT_ESTIMATES), (segments, SEGMENT_ESTIMATES)):
        for row in rows:
            row["estimate_availability"] = {key: row[key] is not None for key in fields}
    for row in movements:
        row["campaign_front_history_available"] = row["campaign_success_index"] is not None
    for rows in (fronts, tactical, strategic):
        for row in rows:
            row["operations_estimate_available"] = True
    for conflict in result["conflicts"]:
        movement = by_conflict.get(conflict["id"])
        front_known = movement is None or movement["campaign_front_history_available"]
        strategic_known = movement is None or (
            front_known and networks[movement["target_region_id"]]["logistics_resilience_index"] is not None)
        flags = {"campaign_movement_id": True, "tactical_engagement_id": front_known,
                 "strategic_campaign_plan_id": strategic_known}
        for key, known in flags.items():
            if key not in conflict:
                conflict[key] = -1 if known else None
        conflict["campaign_link_availability"] = flags
    front_unknown = [row["conflict_id"] for row in movements if not row["campaign_front_history_available"]]
    strategic_unknown = [row["conflict_id"] for row in movements
                         if not row["campaign_front_history_available"]
                         or networks[row["target_region_id"]]["logistics_resilience_index"] is None]
    coverage = {}
    for name, applicable, unavailable, records in (
        ("movement", len(result["conflicts"]), [], movements),
        ("front", len(movements), front_unknown, fronts),
        ("tactical", len(movements), front_unknown, tactical),
        ("strategic", len(movements), strategic_unknown, strategic),
    ):
        coverage[name] = {
            "inference_available": complete_conflicts and not unavailable,
            "applicable_source_count": applicable if complete_conflicts else None,
            "available_source_count": applicable - len(unavailable),
            "recorded_count": len(records), "unavailable_conflict_ids": unavailable,
        }
    result["campaign_operations_availability"] = coverage
    summaries = {}
    flags = {}

    def publish(key, value, family):
        available = coverage[family]["inference_available"] and value is not None
        summaries[key] = value if available else None
        flags[key] = available

    for key, records, family in (
        ("campaign_movement_count", movements, "movement"),
        ("campaign_path_segment_count", segments, "movement"),
        ("campaign_front_history_count", fronts, "front"),
        ("tactical_engagement_count", tactical, "tactical"),
        ("strategic_campaign_plan_count", strategic, "strategic"),
    ):
        publish(key, len(records), family)
        summaries["recorded_" + key] = len(records)
    for key, field, records, family, mean in (
        ("total_campaign_mobilized_population", "force_estimate", movements, "movement", False),
        ("total_campaign_path_length_km", "path_length_km", movements, "movement", False),
        ("mean_campaign_travel_time_days", "travel_time_days", movements, "movement", True),
        ("mean_campaign_attrition_risk_index", "attrition_risk_index", movements, "movement", True),
        ("mean_campaign_operational_reach_index", "operational_reach_index", movements, "movement", True),
        ("mean_campaign_path_length_km", "path_length_km", movements, "movement", True),
        ("mean_campaign_path_terrain_cost_index", "terrain_cost_index", segments, "movement", True),
        ("mean_campaign_path_supply_loss_index", "supply_loss_index", segments, "movement", True),
        ("mean_campaign_path_attrition_index", "attrition_index", segments, "movement", True),
        ("mean_counter_campaign_viability_index", "counter_campaign_viability_index", strategic, "strategic", True),
        ("mean_strategic_plan_confidence_index", "plan_confidence_index", strategic, "strategic", True),
        ("mean_strategic_force_reserve_fraction", "reserve_fraction", strategic, "strategic", True),
    ):
        publish(key, _aggregate(records, field, mean=mean), family)
    front_steps = [step for row in fronts for step in row["steps"]]
    tactical_steps = [step for row in tactical for step in row["steps"]]
    publish("campaign_front_step_count", len(front_steps), "front")
    publish("tactical_engagement_step_count", len(tactical_steps), "tactical")
    publish("strategic_decision_point_count", sum(row["decision_point_count"] for row in strategic), "strategic")
    for key, field, rows, family, mean in (
        ("mean_campaign_front_supply_integrity_index", "supply_integrity_index", front_steps, "front", True),
        ("mean_campaign_front_control_index", "occupation_control_index", front_steps, "front", True),
        ("total_campaign_front_attrition_loss_population", "attrition_loss_population", front_steps, "front", False),
        ("tactical_total_attrition_loss_population", "attrition_loss_population", tactical_steps, "tactical", False),
        ("mean_tactical_counter_maneuver_index", "counter_maneuver_index", tactical_steps, "tactical", True),
        ("mean_tactical_front_pressure_index", "front_pressure_index", tactical_steps, "tactical", True),
        ("mean_tactical_supply_contest_index", "supply_contest_index", tactical_steps, "tactical", True),
    ):
        publish(key, _aggregate(rows, field, mean=mean), family)
    for key, field, rows, family, threshold in (
        ("high_attrition_campaign_count", "attrition_risk_index", movements, "movement", .65),
        ("high_attrition_campaign_path_segment_count", "attrition_index", segments, "movement", .65),
        ("high_pressure_tactical_step_count", "front_pressure_index", tactical_steps, "tactical", .65),
        ("high_escalation_strategic_plan_count", "escalation_risk_index", strategic, "strategic", .65),
    ):
        values = [row[field] for row in rows]
        publish(key, None if any(value is None for value in values) else sum(value >= threshold for value in values), family)
    publish("independent_counter_campaign_plan_count", sum(row["independent_counter_campaign_planned"] for row in strategic), "strategic")
    summaries["campaign_summary_availability"] = flags
    result["summary"] = summaries
    return result
