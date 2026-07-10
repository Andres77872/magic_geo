from __future__ import annotations

import math
from typing import Any

from .planet_parameters import planet_radius_km


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _great_circle_km(a: dict[str, Any], b: dict[str, Any], radius_km: float) -> float:
    lat_a = math.radians(float(a.get("lat_deg", 0.0)))
    lat_b = math.radians(float(b.get("lat_deg", 0.0)))
    dlat = lat_b - lat_a
    dlon = math.radians(float(b.get("lon_deg", 0.0)) - float(a.get("lon_deg", 0.0)))
    hav = math.sin(dlat / 2.0) ** 2 + math.cos(lat_a) * math.cos(lat_b) * math.sin(dlon / 2.0) ** 2
    return 2.0 * radius_km * math.asin(min(1.0, math.sqrt(hav)))


def _select_route_sources(cells: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    candidates = [
        cell
        for cell in cells
        if bool(cell.get("is_river", False))
        and int(cell.get("flow_to", -1)) >= 0
        and float(cell.get("fluvial_sediment_routed_outgoing_m", 0.0)) > 0.0
    ]
    if not candidates:
        candidates = [
            cell
            for cell in cells
            if int(cell.get("flow_to", -1)) >= 0
            and float(cell.get("fluvial_sediment_routed_outgoing_m", 0.0)) > 0.0
        ]
    candidates.sort(
        key=lambda cell: (
            float(cell.get("fluvial_sediment_routed_outgoing_m", 0.0))
            * max(1.0, float(cell.get("flow_accumulation", 0.0))) ** 0.25,
            float(cell.get("flow_accumulation", 0.0)),
        ),
        reverse=True,
    )
    selected: list[dict[str, Any]] = []
    used_basins: set[int] = set()
    for cell in candidates:
        basin_id = int(cell.get("basin_id", -1))
        if basin_id in used_basins and len(selected) < max(1, limit // 2):
            continue
        selected.append(cell)
        used_basins.add(basin_id)
        if len(selected) >= limit:
            break
    return selected


def _follow_flow_path(
    source: dict[str, Any],
    cells_by_id: dict[int, dict[str, Any]],
    max_length: int,
) -> list[dict[str, Any]]:
    path: list[dict[str, Any]] = []
    seen: set[int] = set()
    current = source
    for _ in range(max_length):
        cell_id = int(current.get("id", -1))
        if cell_id < 0 or cell_id in seen:
            break
        path.append(current)
        seen.add(cell_id)
        next_id = int(current.get("flow_to", -1))
        if next_id < 0 or next_id == cell_id:
            break
        next_cell = cells_by_id.get(next_id)
        if next_cell is None:
            break
        current = next_cell
    return path


def enrich_world_with_sediment_routing_history(
    world: dict[str, Any],
    route_limit: int = 12,
    max_path_length: int = 72,
) -> dict[str, Any]:
    cells = world.get("cells", [])
    if not isinstance(cells, list) or not cells:
        return world

    radius_km = planet_radius_km(world)
    cells_by_id = {int(cell.get("id", index)): cell for index, cell in enumerate(cells)}
    for cell in cells:
        cell["sediment_routing_load_m"] = 0.0
        cell["sediment_routing_deposition_m"] = 0.0
        cell["sediment_routing_export_m"] = 0.0
        cell["sediment_routing_path_count"] = 0

    histories: list[dict[str, Any]] = []
    total_step_count = 0
    total_local_supply_m = 0.0
    total_deposition_m = 0.0
    total_export_m = 0.0
    total_sink_loss_m = 0.0
    total_path_length_km = 0.0
    max_final_load_m = 0.0
    max_delivery_ratio = 0.0

    for source in _select_route_sources(cells, route_limit):
        path = _follow_flow_path(source, cells_by_id, max_path_length)
        if len(path) < 2:
            continue
        load_m = 0.0
        route_supply_m = 0.0
        route_deposition_m = 0.0
        route_export_m = 0.0
        route_sink_loss_m = 0.0
        path_length_km = 0.0
        steps: list[dict[str, Any]] = []

        for index, cell in enumerate(path):
            cell_id = int(cell.get("id", -1))
            next_cell = path[index + 1] if index + 1 < len(path) else None
            segment_length_km = _great_circle_km(cell, next_cell, radius_km) if next_cell is not None else 0.0
            path_length_km += segment_length_km
            start_load_m = load_m
            local_supply_m = max(0.0, float(cell.get("fluvial_sediment_local_source_m", 0.0)))
            reference_deposition_m = max(
                0.0,
                float(cell.get("fluvial_sediment_local_deposition_m", 0.0))
                + float(cell.get("fluvial_sediment_terminal_land_deposition_m", 0.0))
                + float(cell.get("fluvial_sediment_marine_deposition_m", 0.0)),
            )
            reference_export_m = max(
                0.0,
                float(cell.get("fluvial_sediment_routed_outgoing_m", 0.0)),
            )
            available_m = start_load_m + local_supply_m
            transport_capacity_index = _clamp(
                0.28
                + math.log1p(max(0.0, float(cell.get("flow_accumulation", 0.0)))) / 28.0
                + max(0.0, float(cell.get("runoff_mm_y", 0.0))) / 8000.0
                + (0.12 if bool(cell.get("is_river", False)) else 0.0),
                0.0,
                1.0,
            )
            capacity_m = reference_export_m * (0.55 + transport_capacity_index) + local_supply_m * transport_capacity_index
            deposited_m = min(available_m, reference_deposition_m * (1.0 - transport_capacity_index * 0.45))
            remaining_m = max(0.0, available_m - deposited_m)
            routed_export_m = min(remaining_m, capacity_m)
            excess_m = max(0.0, remaining_m - routed_export_m)
            sink_loss_m = excess_m if next_cell is None else 0.0
            if next_cell is not None:
                deposited_m += excess_m
            end_load_m = 0.0 if next_cell is None else routed_export_m
            delivery_ratio = routed_export_m / max(0.001, available_m)
            local_balance_m = available_m - deposited_m - routed_export_m - sink_loss_m

            cell["sediment_routing_load_m"] = round(max(float(cell.get("sediment_routing_load_m", 0.0)), end_load_m), 6)
            cell["sediment_routing_deposition_m"] = round(
                float(cell.get("sediment_routing_deposition_m", 0.0)) + deposited_m,
                6,
            )
            cell["sediment_routing_export_m"] = round(
                float(cell.get("sediment_routing_export_m", 0.0)) + routed_export_m,
                6,
            )
            cell["sediment_routing_path_count"] = int(cell.get("sediment_routing_path_count", 0)) + 1

            steps.append(
                {
                    "step": index + 1,
                    "cell_id": cell_id,
                    "flow_to_cell_id": int(cell.get("flow_to", -1)),
                    "segment_length_km": round(segment_length_km, 6),
                    "start_load_m": round(start_load_m, 6),
                    "local_supply_m": round(local_supply_m, 6),
                    "deposited_m": round(deposited_m, 6),
                    "routed_export_m": round(routed_export_m, 6),
                    "sink_loss_m": round(sink_loss_m, 6),
                    "end_load_m": round(end_load_m, 6),
                    "local_balance_m": round(local_balance_m, 6),
                    "transport_capacity_index": round(transport_capacity_index, 6),
                    "delivery_ratio": round(delivery_ratio, 6),
                    "is_river": bool(cell.get("is_river", False)),
                    "water_body_type": str(cell.get("water_body_type", "unknown")),
                }
            )
            route_supply_m += local_supply_m
            route_deposition_m += deposited_m
            route_export_m += routed_export_m
            route_sink_loss_m += sink_loss_m
            max_delivery_ratio = max(max_delivery_ratio, delivery_ratio)
            load_m = end_load_m

        final_load_m = float(steps[-1]["end_load_m"]) if steps else 0.0
        max_final_load_m = max(max_final_load_m, final_load_m)
        total_step_count += len(steps)
        total_local_supply_m += route_supply_m
        total_deposition_m += route_deposition_m
        total_export_m += route_export_m
        total_sink_loss_m += route_sink_loss_m
        total_path_length_km += path_length_km
        histories.append(
            {
                "id": len(histories),
                "source_cell_id": int(source.get("id", -1)),
                "basin_id": int(source.get("basin_id", -1)),
                "flow_path_cell_ids": [int(cell.get("id", -1)) for cell in path],
                "time_step_count": len(steps),
                "path_length_km": round(path_length_km, 6),
                "total_local_supply_m": round(route_supply_m, 6),
                "total_deposition_m": round(route_deposition_m, 6),
                "total_routed_export_m": round(route_export_m, 6),
                "total_sink_loss_m": round(route_sink_loss_m, 6),
                "final_sediment_load_m": round(final_load_m, 6),
                "route_delivery_ratio": round(final_load_m / max(0.001, route_supply_m), 6),
                "steps": steps,
            }
        )

    world["sediment_routing_histories"] = histories
    summary = world.setdefault("summary", {})
    summary["sediment_routing_history_count"] = len(histories)
    summary["sediment_routing_step_count"] = total_step_count
    summary["sediment_routing_cell_count"] = sum(1 for cell in cells if int(cell.get("sediment_routing_path_count", 0)) > 0)
    summary["sediment_routing_total_local_supply_m"] = round(total_local_supply_m, 6)
    summary["sediment_routing_total_deposition_m"] = round(total_deposition_m, 6)
    summary["sediment_routing_total_export_m"] = round(total_export_m, 6)
    summary["sediment_routing_total_sink_loss_m"] = round(total_sink_loss_m, 6)
    summary["sediment_routing_total_path_length_km"] = round(total_path_length_km, 6)
    summary["sediment_routing_mean_path_length_km"] = round(total_path_length_km / len(histories), 6) if histories else 0.0
    summary["sediment_routing_max_final_load_m"] = round(max_final_load_m, 6)
    summary["sediment_routing_max_delivery_ratio"] = round(max_delivery_ratio, 6)
    return world
