from __future__ import annotations

import math
from typing import Any


HIGH_RISK_THRESHOLD = 0.65
EVENT_RISK_THRESHOLD = 0.25
MAX_EVENT_COUNT = 64
REORGANIZATION_STEP_COUNT = 4


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _elevation(cell: dict[str, Any]) -> float:
    return float(
        cell.get(
            "hydrologic_surface_elevation_m",
            cell.get("filled_elevation_m", cell.get("elevation_m", 0.0)),
        )
    )


def _great_circle_km(a: dict[str, Any], b: dict[str, Any]) -> float:
    radius_km = 6371.0
    lat_a = math.radians(float(a.get("lat_deg", 0.0)))
    lat_b = math.radians(float(b.get("lat_deg", 0.0)))
    dlat = lat_b - lat_a
    dlon = math.radians(float(b.get("lon_deg", 0.0)) - float(a.get("lon_deg", 0.0)))
    hav = math.sin(dlat / 2.0) ** 2 + math.cos(lat_a) * math.cos(lat_b) * math.sin(dlon / 2.0) ** 2
    return 2.0 * radius_km * math.asin(min(1.0, math.sqrt(hav)))


def _accumulation_index(cell: dict[str, Any], max_accumulation: float) -> float:
    if max_accumulation <= 0.0:
        return 0.0
    return _clamp(math.log1p(max(0.0, float(cell.get("flow_accumulation", 0.0)))) / math.log1p(max_accumulation))


def _downstream_gradient(cell: dict[str, Any], cells_by_id: dict[int, dict[str, Any]]) -> tuple[float, int]:
    next_id = int(cell.get("flow_to", -1))
    next_cell = cells_by_id.get(next_id)
    if next_cell is None:
        return 0.0, -1
    distance_km = max(0.001, _great_circle_km(cell, next_cell))
    drop_m = max(0.0, _elevation(cell) - _elevation(next_cell))
    return drop_m / (distance_km * 1000.0), next_id


def _sediment_signal(cell: dict[str, Any], max_sediment_signal: float) -> float:
    local = max(0.0, float(cell.get("sediment_deposition_m", 0.0))) + max(
        0.0,
        float(
            cell.get(
                "fluvial_sediment_routed_outgoing_m",
                cell.get("sediment_export_m", 0.0),
            )
        ),
    )
    if max_sediment_signal > 0.0:
        return _clamp(local / max_sediment_signal)
    return _clamp(max(0.0, float(cell.get("sediment_thickness_m", 0.0))) / 250.0)


def _water_adjacency(cell: dict[str, Any], cells_by_id: dict[int, dict[str, Any]]) -> float:
    neighbors = cell.get("neighbors", [])
    if not isinstance(neighbors, list):
        return 0.0
    water_neighbors = 0
    for neighbor_id in neighbors:
        neighbor = cells_by_id.get(int(neighbor_id))
        if neighbor is not None and bool(neighbor.get("is_water", False)):
            water_neighbors += 1
    return _clamp(water_neighbors / max(1, len(neighbors)))


def _landform_avulsion_bonus(cell: dict[str, Any]) -> float:
    landform = str(cell.get("landform", ""))
    if landform in {"delta", "floodplain"}:
        return 0.22
    if landform in {"river_valley", "coastal_plain", "lacustrine_basin"}:
        return 0.12
    return 0.0


def _build_reorganization_histories(
    events: list[dict[str, Any]],
    cells_by_id: dict[int, dict[str, Any]],
) -> list[dict[str, Any]]:
    histories: list[dict[str, Any]] = []
    for event in events:
        event_id = int(event.get("id", len(histories)))
        event_type = str(event.get("type", ""))
        source_cell_id = int(event.get("source_cell_id", -1))
        target_cell_id = int(event.get("target_cell_id", -1))
        source_cell = cells_by_id.get(source_cell_id, {})
        target_cell = cells_by_id.get(target_cell_id, {})
        risk = _clamp(float(event.get("risk", 0.0)))
        source_flow_to = int(source_cell.get("flow_to", -1))
        projected_flow_to = target_cell_id if event_type == "river_capture_candidate" else source_flow_to
        source_accumulation = max(0.0, float(source_cell.get("flow_accumulation", 0.0)))
        target_accumulation = max(0.0, float(target_cell.get("flow_accumulation", 0.0))) if target_cell else 0.0
        distance_km = max(0.001, float(event.get("target_distance_km", 0.0)))
        if event_type == "river_capture_candidate":
            initial_divide_relief = max(0.0, float(event.get("divide_relief_m", 0.0)))
            initial_gradient = _clamp(
                max(0.0, _elevation(source_cell) - _elevation(target_cell)) / (distance_km * 1000.0)
                if target_cell
                else 0.0,
                0.0,
                0.08,
            )
            process_name = "headward_capture"
        else:
            initial_divide_relief = 0.0
            initial_gradient = _clamp(float(event.get("channel_gradient", 0.0)), 0.0, 0.08)
            process_name = "avulsion_channelization"

        final_divide_relief = max(0.0, initial_divide_relief * (1.0 - risk * 0.48))
        final_gradient = _clamp(initial_gradient + risk * (0.0016 if event_type == "river_capture_candidate" else 0.0009), 0.0, 0.08)
        total_divide_lowering = max(0.0, initial_divide_relief - final_divide_relief)
        sediment_signal = _clamp(float(event.get("sediment_signal", source_cell.get("sediment_thickness_m", 0.0))) / 1.5)
        total_sediment_reworked = _clamp(
            risk * 0.55
            + sediment_signal * 0.24
            + _accumulation_index(source_cell, max(source_accumulation, target_accumulation, 1.0)) * 0.21
        ) * max(0.02, distance_km / 90.0)

        steps: list[dict[str, Any]] = []
        channelization_sum = 0.0
        for index in range(REORGANIZATION_STEP_COUNT):
            stage_index = index + 1
            progress = stage_index / REORGANIZATION_STEP_COUNT
            previous_progress = index / REORGANIZATION_STEP_COUNT
            divide_relief = initial_divide_relief + (final_divide_relief - initial_divide_relief) * progress
            previous_divide_relief = initial_divide_relief + (final_divide_relief - initial_divide_relief) * previous_progress
            divide_lowering = max(0.0, previous_divide_relief - divide_relief)
            channel_gradient = initial_gradient + (final_gradient - initial_gradient) * progress
            channelization = _clamp(risk * (0.38 + progress * 0.48) + sediment_signal * 0.12)
            diversion_probability = _clamp(risk * (0.30 + progress * 0.58) + channelization * 0.10)
            headward_erosion = _clamp(
                risk * progress * (0.72 if event_type == "river_capture_candidate" else 0.30)
                + channel_gradient / 0.08 * 0.18
            )
            avulsion_width = _clamp(
                risk * progress * (0.70 if event_type == "river_avulsion_candidate" else 0.24)
                + sediment_signal * 0.22
                + (1.0 - min(1.0, channel_gradient / 0.02)) * 0.08
            )
            connectivity_change = _clamp(
                diversion_probability * 0.44
                + headward_erosion * 0.24
                + avulsion_width * 0.20
                + (0.12 if int(event.get("source_basin_id", -1)) != int(event.get("target_basin_id", -1)) else 0.0)
            )
            confidence = _clamp(risk * 0.50 + channelization * 0.22 + connectivity_change * 0.18 + progress * 0.10)
            sediment_reworked = total_sediment_reworked / REORGANIZATION_STEP_COUNT * (0.70 + progress * 0.60)
            channelization_sum += channelization
            steps.append(
                {
                    "stage_index": stage_index,
                    "elapsed_years": int(round(progress * 4000.0)),
                    "active_process": process_name,
                    "divide_relief_m": round(divide_relief, 6),
                    "divide_lowering_m": round(divide_lowering, 6),
                    "channel_gradient": round(channel_gradient, 8),
                    "channelization_index": round(channelization, 6),
                    "diversion_probability_index": round(diversion_probability, 6),
                    "sediment_reworking_m": round(sediment_reworked, 6),
                    "capture_headward_erosion_index": round(headward_erosion, 6),
                    "avulsion_belt_width_index": round(avulsion_width, 6),
                    "basin_connectivity_change_index": round(connectivity_change, 6),
                    "reorganization_confidence_index": round(confidence, 6),
                }
            )

        final_probability = float(steps[-1].get("diversion_probability_index", 0.0)) if steps else 0.0
        final_confidence = float(steps[-1].get("reorganization_confidence_index", 0.0)) if steps else 0.0
        histories.append(
            {
                "id": len(histories),
                "river_network_evolution_event_id": event_id,
                "event_type": event_type,
                "source_cell_id": source_cell_id,
                "target_cell_id": target_cell_id,
                "source_basin_id": int(event.get("source_basin_id", -1)),
                "target_basin_id": int(event.get("target_basin_id", -1)),
                "source_flow_to_cell_id": source_flow_to,
                "projected_flow_to_cell_id": projected_flow_to,
                "source_flow_accumulation": round(source_accumulation, 6),
                "target_flow_accumulation": round(target_accumulation, 6),
                "risk_index": round(risk, 6),
                "initial_divide_relief_m": round(initial_divide_relief, 6),
                "final_divide_relief_m": round(final_divide_relief, 6),
                "initial_channel_gradient": round(initial_gradient, 8),
                "final_channel_gradient": round(final_gradient, 8),
                "total_divide_lowering_m": round(sum(float(step.get("divide_lowering_m", 0.0)) for step in steps), 6),
                "mean_channelization_index": round(channelization_sum / len(steps), 6) if steps else 0.0,
                "total_sediment_reworked_m": round(sum(float(step.get("sediment_reworking_m", 0.0)) for step in steps), 6),
                "final_diversion_probability_index": round(final_probability, 6),
                "final_reorganization_confidence_index": round(final_confidence, 6),
                "high_reorganization_pressure": bool(risk >= HIGH_RISK_THRESHOLD or final_probability >= 0.65),
                "step_count": len(steps),
                "steps": steps,
            }
        )
    return histories


def enrich_world_with_river_network_evolution(world: dict[str, Any]) -> dict[str, Any]:
    cells = world.get("cells", [])
    if not isinstance(cells, list):
        return world

    cells_by_id = {int(cell.get("id", index)): cell for index, cell in enumerate(cells)}
    max_accumulation = max((max(0.0, float(cell.get("flow_accumulation", 0.0))) for cell in cells), default=0.0)
    max_sediment_signal = max(
        (
            max(0.0, float(cell.get("sediment_deposition_m", 0.0)))
            + max(
                0.0,
                float(
                    cell.get(
                        "fluvial_sediment_routed_outgoing_m",
                        cell.get("sediment_export_m", 0.0),
                    )
                ),
            )
            for cell in cells
        ),
        default=0.0,
    )

    candidate_events: list[dict[str, Any]] = []
    capture_candidate_count = 0
    avulsion_candidate_count = 0
    high_capture_count = 0
    high_avulsion_count = 0
    instability_count = 0
    high_instability_count = 0
    capture_sum = 0.0
    avulsion_sum = 0.0
    instability_sum = 0.0
    max_capture = 0.0
    max_avulsion = 0.0
    max_instability = 0.0

    for cell in cells:
        cell["river_capture_risk"] = 0.0
        cell["river_capture_target_cell_id"] = -1
        cell["river_capture_target_basin_id"] = -1
        cell["river_capture_divide_relief_m"] = 0.0
        cell["river_capture_target_distance_km"] = 0.0
        cell["river_avulsion_risk"] = 0.0
        cell["river_network_instability_index"] = 0.0

    for cell in cells:
        if not bool(cell.get("is_river", False)):
            continue

        cell_id = int(cell.get("id", -1))
        basin_id = int(cell.get("basin_id", -1))
        current_elevation = _elevation(cell)
        accumulation_index = _accumulation_index(cell, max_accumulation)
        gradient, downstream_id = _downstream_gradient(cell, cells_by_id)
        low_gradient_index = _clamp(1.0 - gradient / 0.018)
        sediment_index = _sediment_signal(cell, max_sediment_signal)
        water_index = _water_adjacency(cell, cells_by_id)
        overflow_avulsion = _clamp(float(cell.get("overflow_channel_avulsion_risk", 0.0)))
        avulsion_risk = _clamp(
            0.20 * accumulation_index
            + 0.26 * low_gradient_index
            + 0.24 * sediment_index
            + 0.14 * water_index
            + 0.12 * overflow_avulsion
            + _landform_avulsion_bonus(cell)
        )

        best_capture: dict[str, Any] | None = None
        neighbors = cell.get("neighbors", [])
        if isinstance(neighbors, list):
            for neighbor_id in neighbors:
                neighbor = cells_by_id.get(int(neighbor_id))
                if neighbor is None:
                    continue
                target_basin_id = int(neighbor.get("basin_id", -1))
                if basin_id < 0 or target_basin_id < 0 or target_basin_id == basin_id:
                    continue

                target_elevation = _elevation(neighbor)
                distance_km = max(0.001, _great_circle_km(cell, neighbor))
                divide_relief = abs(current_elevation - target_elevation)
                low_divide_index = _clamp(1.0 - divide_relief / 750.0)
                downhill_pull = _clamp((current_elevation - target_elevation + 75.0) / 650.0)
                target_accumulation_index = _accumulation_index(neighbor, max_accumulation)
                target_channel_index = 1.0 if bool(neighbor.get("is_river", False)) else 0.35 if bool(neighbor.get("is_water", False)) else 0.0
                capture_risk = _clamp(
                    0.30 * accumulation_index
                    + 0.30 * low_divide_index
                    + 0.22 * downhill_pull
                    + 0.12 * target_accumulation_index
                    + 0.06 * target_channel_index
                )
                if capture_risk <= 0.0:
                    continue
                if best_capture is None or capture_risk > float(best_capture["risk"]):
                    best_capture = {
                        "risk": capture_risk,
                        "target_cell_id": int(neighbor.get("id", -1)),
                        "target_basin_id": target_basin_id,
                        "divide_relief_m": divide_relief,
                        "target_distance_km": distance_km,
                    }

        capture_risk = float(best_capture["risk"]) if best_capture is not None else 0.0
        instability = max(capture_risk, avulsion_risk)

        cell["river_capture_risk"] = round(capture_risk, 6)
        if best_capture is not None:
            cell["river_capture_target_cell_id"] = int(best_capture["target_cell_id"])
            cell["river_capture_target_basin_id"] = int(best_capture["target_basin_id"])
            cell["river_capture_divide_relief_m"] = round(float(best_capture["divide_relief_m"]), 6)
            cell["river_capture_target_distance_km"] = round(float(best_capture["target_distance_km"]), 6)
        cell["river_avulsion_risk"] = round(avulsion_risk, 6)
        cell["river_network_instability_index"] = round(instability, 6)

        capture_sum += capture_risk
        avulsion_sum += avulsion_risk
        instability_sum += instability
        max_capture = max(max_capture, capture_risk)
        max_avulsion = max(max_avulsion, avulsion_risk)
        max_instability = max(max_instability, instability)
        if capture_risk > 0.0:
            capture_candidate_count += 1
        if capture_risk >= HIGH_RISK_THRESHOLD:
            high_capture_count += 1
        if avulsion_risk > 0.0:
            avulsion_candidate_count += 1
        if avulsion_risk >= HIGH_RISK_THRESHOLD:
            high_avulsion_count += 1
        if instability > 0.0:
            instability_count += 1
        if instability >= HIGH_RISK_THRESHOLD:
            high_instability_count += 1

        if best_capture is not None and capture_risk >= EVENT_RISK_THRESHOLD:
            candidate_events.append(
                {
                    "type": "river_capture_candidate",
                    "source_cell_id": cell_id,
                    "target_cell_id": int(best_capture["target_cell_id"]),
                    "source_basin_id": basin_id,
                    "target_basin_id": int(best_capture["target_basin_id"]),
                    "risk": round(capture_risk, 6),
                    "divide_relief_m": round(float(best_capture["divide_relief_m"]), 6),
                    "target_distance_km": round(float(best_capture["target_distance_km"]), 6),
                    "flow_accumulation": round(float(cell.get("flow_accumulation", 0.0)), 6),
                    "dominant_driver": "low_divide_capture",
                }
            )
        if avulsion_risk >= EVENT_RISK_THRESHOLD:
            candidate_events.append(
                {
                    "type": "river_avulsion_candidate",
                    "source_cell_id": cell_id,
                    "target_cell_id": downstream_id,
                    "source_basin_id": basin_id,
                    "target_basin_id": basin_id,
                    "risk": round(avulsion_risk, 6),
                    "channel_gradient": round(gradient, 8),
                    "sediment_signal": round(sediment_index, 6),
                    "flow_accumulation": round(float(cell.get("flow_accumulation", 0.0)), 6),
                    "dominant_driver": "low_gradient_sediment_avulsion",
                }
            )

    candidate_events.sort(key=lambda event: (-float(event.get("risk", 0.0)), str(event.get("type", "")), int(event.get("source_cell_id", -1))))
    events = candidate_events[:MAX_EVENT_COUNT]
    for index, event in enumerate(events):
        event["id"] = index

    world["river_network_evolution_events"] = events
    reorganization_histories = _build_reorganization_histories(events, cells_by_id)
    world["river_reorganization_histories"] = reorganization_histories
    summary = world.setdefault("summary", {})
    cell_count = len(cells)
    summary["river_capture_candidate_count"] = capture_candidate_count
    summary["high_river_capture_risk_cell_count"] = high_capture_count
    summary["mean_river_capture_risk"] = round(capture_sum / cell_count, 6) if cell_count else 0.0
    summary["max_river_capture_risk"] = round(max_capture, 6)
    summary["river_avulsion_candidate_count"] = avulsion_candidate_count
    summary["high_river_avulsion_risk_cell_count"] = high_avulsion_count
    summary["mean_river_avulsion_risk"] = round(avulsion_sum / cell_count, 6) if cell_count else 0.0
    summary["max_river_avulsion_risk"] = round(max_avulsion, 6)
    summary["river_network_instability_cell_count"] = instability_count
    summary["high_river_network_instability_cell_count"] = high_instability_count
    summary["mean_river_network_instability_index"] = round(instability_sum / cell_count, 6) if cell_count else 0.0
    summary["max_river_network_instability_index"] = round(max_instability, 6)
    summary["river_network_evolution_event_count"] = len(events)
    summary["river_reorganization_history_count"] = len(reorganization_histories)
    summary["river_reorganization_step_count"] = sum(int(history.get("step_count", 0)) for history in reorganization_histories)
    summary["mean_river_reorganization_risk_index"] = (
        round(sum(float(history.get("risk_index", 0.0)) for history in reorganization_histories) / len(reorganization_histories), 6)
        if reorganization_histories
        else 0.0
    )
    summary["mean_river_diversion_probability_index"] = (
        round(sum(float(history.get("final_diversion_probability_index", 0.0)) for history in reorganization_histories) / len(reorganization_histories), 6)
        if reorganization_histories
        else 0.0
    )
    summary["mean_river_reorganization_confidence_index"] = (
        round(sum(float(history.get("final_reorganization_confidence_index", 0.0)) for history in reorganization_histories) / len(reorganization_histories), 6)
        if reorganization_histories
        else 0.0
    )
    summary["total_river_divide_lowering_m"] = round(
        sum(float(history.get("total_divide_lowering_m", 0.0)) for history in reorganization_histories),
        6,
    )
    summary["total_river_sediment_reworked_m"] = round(
        sum(float(history.get("total_sediment_reworked_m", 0.0)) for history in reorganization_histories),
        6,
    )
    summary["high_river_reorganization_pressure_count"] = sum(
        1 for history in reorganization_histories if bool(history.get("high_reorganization_pressure", False))
    )
    return world
