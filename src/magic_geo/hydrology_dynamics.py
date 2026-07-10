from __future__ import annotations

import math
from typing import Any


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _annual_evaporation_loss_km3(basin: dict[str, Any]) -> float:
    lake_area_km2 = max(0.0, float(basin.get("lake_area_km2", 0.0)))
    mean_depth_m = max(0.0, float(basin.get("mean_water_depth_m", 0.0)))
    if lake_area_km2 <= 0.0 or mean_depth_m <= 0.0:
        return 0.0
    evaporation_depth_m = _clamp(0.35 + mean_depth_m / 2500.0, 0.35, 1.20)
    return lake_area_km2 * evaporation_depth_m / 1000.0


def _overflow_stage(spill_volume_km3: float, annual_runoff_km3: float, stage_count: int) -> int:
    if spill_volume_km3 <= 0.0 or stage_count <= 0:
        return 0
    pressure = spill_volume_km3 / max(1.0, annual_runoff_km3)
    return min(stage_count, max(1, int(math.ceil(pressure * stage_count))))


def _great_circle_km(a: dict[str, Any], b: dict[str, Any]) -> float:
    radius_km = 6371.0
    lat_a = math.radians(float(a.get("lat_deg", 0.0)))
    lat_b = math.radians(float(b.get("lat_deg", 0.0)))
    dlat = lat_b - lat_a
    dlon = math.radians(float(b.get("lon_deg", 0.0)) - float(a.get("lon_deg", 0.0)))
    hav = math.sin(dlat / 2.0) ** 2 + math.cos(lat_a) * math.cos(lat_b) * math.sin(dlon / 2.0) ** 2
    return 2.0 * radius_km * math.asin(min(1.0, math.sqrt(hav)))


def _path_length_km(path_cell_ids: list[int], cells_by_id: dict[int, dict[str, Any]], fallback_km: float) -> float:
    length_km = 0.0
    for first_id, second_id in zip(path_cell_ids, path_cell_ids[1:]):
        first = cells_by_id.get(int(first_id))
        second = cells_by_id.get(int(second_id))
        if first is not None and second is not None:
            length_km += _great_circle_km(first, second)
    return length_km if length_km > 0.0 else max(0.0, fallback_km)


def _cell_elevation_m(cell: dict[str, Any] | None) -> float:
    if cell is None:
        return 0.0
    return float(
        cell.get(
            "hydrologic_surface_elevation_m",
            cell.get("filled_elevation_m", cell.get("elevation_m", 0.0)),
        )
    )


def _enrich_world_with_overflow_channel_history(
    world: dict[str, Any],
    lake_basins: list[dict[str, Any]],
    lake_histories: list[dict[str, Any]],
) -> None:
    cells = world.get("cells", [])
    if not isinstance(cells, list):
        cells = []
    cells_by_id = {int(cell.get("id", index)): cell for index, cell in enumerate(cells)}
    for cell in cells:
        cell["overflow_channel_active"] = False
        cell["overflow_channel_incision_m"] = 0.0
        cell["overflow_channel_sediment_evacuated_km3"] = 0.0
        cell["overflow_channel_avulsion_risk"] = 0.0

    histories_by_lake_id = {int(history.get("lake_basin_id", -1)): history for history in lake_histories}
    channel_histories: list[dict[str, Any]] = []
    total_step_count = 0
    active_channel_count = 0
    avulsion_channel_count = 0
    channel_cell_ids: set[int] = set()
    total_incision_m = 0.0
    max_incision_m = 0.0
    total_sediment_evacuated_km3 = 0.0
    stream_power_sum = 0.0
    stream_power_step_count = 0

    for basin in lake_basins:
        path_cell_ids = [int(cell_id) for cell_id in basin.get("overflow_path_cell_ids", [])]
        if len(path_cell_ids) < 2:
            continue
        lake_basin_id = int(basin.get("id", len(channel_histories)))
        lake_history = histories_by_lake_id.get(lake_basin_id)
        if lake_history is None:
            continue

        segment_count = max(0, len(path_cell_ids) - 1)
        channel_length_km = _path_length_km(
            path_cell_ids,
            cells_by_id,
            float(basin.get("overflow_path_length_km", 0.0)),
        )
        head_cell = cells_by_id.get(path_cell_ids[0])
        tail_cell = cells_by_id.get(path_cell_ids[-1])
        path_drop_m = max(
            0.0,
            _cell_elevation_m(head_cell) - _cell_elevation_m(tail_cell),
            float(basin.get("spill_elevation_m", 0.0)) - _cell_elevation_m(tail_cell),
        )
        if path_drop_m <= 0.0:
            path_drop_m = max(0.0, float(basin.get("max_depression_depth_m", 0.0)) * 0.15)
        bed_slope = path_drop_m / max(1.0, channel_length_km * 1000.0)
        annual_runoff_km3 = max(1.0, float(basin.get("annual_runoff_km3", 0.0)))
        overflow_index = _clamp(float(basin.get("overflow_index", 0.0)), 0.0, 1.0)
        base_avulsion_risk = _clamp(float(basin.get("avulsion_risk", 0.0)), 0.0, 1.0)
        stage_count = max(1, int(basin.get("overflow_stage_count", segment_count)))
        incision_depth_m = max(0.0, float(basin.get("max_depression_depth_m", 0.0)) * 0.01)
        channel_width_m = _clamp(6.0 + math.sqrt(annual_runoff_km3) * 0.18, 6.0, 180.0)

        steps: list[dict[str, Any]] = []
        history_spill_km3 = 0.0
        history_incision_m = 0.0
        history_widening_m = 0.0
        history_sediment_km3 = 0.0
        history_max_stream_power = 0.0
        history_max_avulsion_risk = 0.0
        first_avulsion_year = -1

        for index, lake_step in enumerate(lake_history.get("steps", [])):
            year = int(lake_step.get("year", index + 1))
            spill_volume_km3 = max(0.0, float(lake_step.get("spill_volume_km3", 0.0)))
            overflow_stage = max(0, int(lake_step.get("overflow_stage", 0)))
            spill_pressure = spill_volume_km3 / annual_runoff_km3
            slope_factor = _clamp(bed_slope * 160.0, 0.0, 1.0)
            stage_factor = overflow_stage / stage_count if stage_count > 0 else 0.0
            stream_power_index = (
                _clamp(0.18 * min(1.0, spill_pressure) + 0.48 * slope_factor + 0.22 * stage_factor + 0.12 * overflow_index, 0.0, 1.0)
                if spill_volume_km3 > 0.0
                else 0.0
            )
            start_incision_m = incision_depth_m
            incision_m = 0.0
            bank_widening_m = 0.0
            sediment_evacuated_km3 = 0.0
            step_avulsion_risk = 0.0
            if spill_volume_km3 > 0.0:
                incision_m = _clamp(
                    stream_power_index * (0.04 + min(1.0, spill_pressure) * 0.24) * (1.0 + base_avulsion_risk * 0.65),
                    0.0,
                    1.5,
                )
                bank_widening_m = incision_m * (1.4 + base_avulsion_risk * 2.6 + stage_factor)
                channel_width_m = _clamp(channel_width_m + bank_widening_m, 6.0, 260.0)
                sediment_evacuated_km3 = channel_length_km * channel_width_m * incision_m / 1_000_000.0
                incision_depth_m += incision_m
                step_avulsion_risk = _clamp(
                    base_avulsion_risk * 0.55
                    + stream_power_index * 0.30
                    + min(1.0, incision_depth_m / max(1.0, path_drop_m)) * 0.15,
                    0.0,
                    1.0,
                )
            step_avulsion_triggered = (
                spill_volume_km3 > 0.0
                and step_avulsion_risk >= 0.65
                and overflow_stage >= max(1, stage_count - 1)
            )
            if step_avulsion_triggered and first_avulsion_year < 0:
                first_avulsion_year = year
            if spill_volume_km3 <= 0.0:
                dominant_process = "no_flow"
            elif step_avulsion_triggered:
                dominant_process = "avulsion"
            elif bank_widening_m > incision_m:
                dominant_process = "spillway_widening"
            else:
                dominant_process = "spillway_incision"

            steps.append(
                {
                    "year": year,
                    "start_incision_depth_m": round(start_incision_m, 6),
                    "spill_volume_km3": round(spill_volume_km3, 6),
                    "overflow_stage": overflow_stage,
                    "stream_power_index": round(stream_power_index, 6),
                    "incision_m": round(incision_m, 6),
                    "bank_widening_m": round(bank_widening_m, 6),
                    "channel_width_m": round(channel_width_m, 6),
                    "sediment_evacuated_km3": round(sediment_evacuated_km3, 6),
                    "end_incision_depth_m": round(incision_depth_m, 6),
                    "avulsion_risk": round(step_avulsion_risk, 6),
                    "avulsion_triggered": step_avulsion_triggered,
                    "dominant_process": dominant_process,
                }
            )
            history_spill_km3 += spill_volume_km3
            history_incision_m += incision_m
            history_widening_m += bank_widening_m
            history_sediment_km3 += sediment_evacuated_km3
            history_max_stream_power = max(history_max_stream_power, stream_power_index)
            history_max_avulsion_risk = max(history_max_avulsion_risk, step_avulsion_risk)
            if spill_volume_km3 > 0.0:
                stream_power_sum += stream_power_index
                stream_power_step_count += 1

        for cell_id in path_cell_ids:
            cell = cells_by_id.get(cell_id)
            if cell is None:
                continue
            channel_cell_ids.add(cell_id)
            cell["overflow_channel_active"] = True
            cell["overflow_channel_incision_m"] = round(
                max(float(cell.get("overflow_channel_incision_m", 0.0)), incision_depth_m),
                6,
            )
            cell["overflow_channel_sediment_evacuated_km3"] = round(
                float(cell.get("overflow_channel_sediment_evacuated_km3", 0.0))
                + history_sediment_km3 / max(1, len(path_cell_ids)),
                6,
            )
            cell["overflow_channel_avulsion_risk"] = round(
                max(float(cell.get("overflow_channel_avulsion_risk", 0.0)), history_max_avulsion_risk),
                6,
            )

        total_step_count += len(steps)
        total_incision_m += history_incision_m
        max_incision_m = max(max_incision_m, incision_depth_m)
        total_sediment_evacuated_km3 += history_sediment_km3
        if history_spill_km3 > 0.0:
            active_channel_count += 1
        if first_avulsion_year > 0:
            avulsion_channel_count += 1
        channel_histories.append(
            {
                "id": len(channel_histories),
                "lake_basin_id": lake_basin_id,
                "overflow_path_cell_ids": path_cell_ids,
                "channel_segment_count": segment_count,
                "channel_length_km": round(channel_length_km, 6),
                "path_drop_m": round(path_drop_m, 6),
                "bed_slope": round(bed_slope, 8),
                "time_step_count": len(steps),
                "total_spill_km3": round(history_spill_km3, 6),
                "total_incision_m": round(history_incision_m, 6),
                "final_incision_depth_m": round(incision_depth_m, 6),
                "total_bank_widening_m": round(history_widening_m, 6),
                "total_sediment_evacuated_km3": round(history_sediment_km3, 6),
                "max_stream_power_index": round(history_max_stream_power, 6),
                "max_avulsion_risk": round(history_max_avulsion_risk, 6),
                "avulsion_triggered": first_avulsion_year > 0,
                "first_avulsion_year": first_avulsion_year,
                "steps": steps,
            }
        )

    world["lake_overflow_channel_histories"] = channel_histories
    summary = world.setdefault("summary", {})
    summary["lake_overflow_channel_history_count"] = len(channel_histories)
    summary["lake_overflow_channel_step_count"] = total_step_count
    summary["active_lake_overflow_channel_count"] = active_channel_count
    summary["lake_overflow_channel_cell_count"] = len(channel_cell_ids)
    summary["lake_overflow_channel_avulsion_count"] = avulsion_channel_count
    summary["lake_overflow_total_channel_incision_m"] = round(total_incision_m, 6)
    summary["max_lake_overflow_channel_incision_m"] = round(max_incision_m, 6)
    summary["lake_overflow_total_channel_sediment_evacuated_km3"] = round(total_sediment_evacuated_km3, 6)
    summary["mean_lake_overflow_channel_stream_power_index"] = (
        round(stream_power_sum / stream_power_step_count, 6) if stream_power_step_count > 0 else 0.0
    )


def enrich_world_with_lake_overflow_history(world: dict[str, Any], simulation_years: int = 12) -> dict[str, Any]:
    lake_basins = world.get("lake_basins", [])
    if not isinstance(lake_basins, list):
        return world
    simulated_lake_basins = [
        basin for basin in lake_basins if int(basin.get("lake_cell_count", 0)) > 0
    ]

    histories: list[dict[str, Any]] = []
    total_step_count = 0
    active_history_count = 0
    avulsion_trigger_count = 0
    total_spill_km3 = 0.0
    total_sink_loss_km3 = 0.0
    max_fill_fraction = 0.0

    for basin in simulated_lake_basins:
        basin_id = int(basin.get("id", len(histories)))
        storage_capacity_km3 = max(0.0, float(basin.get("storage_capacity_km3", 0.0)))
        annual_runoff_km3 = max(0.0, float(basin.get("annual_runoff_km3", 0.0)))
        fill_fraction = max(0.0, float(basin.get("fill_fraction", 0.0)))
        stage_count = max(0, int(basin.get("overflow_stage_count", 0)))
        overflows = bool(basin.get("overflows", False))
        avulsion_risk = _clamp(float(basin.get("avulsion_risk", 0.0)), 0.0, 1.0)
        evaporation_loss_km3 = _annual_evaporation_loss_km3(basin)
        volume_km3 = min(storage_capacity_km3, storage_capacity_km3 * min(fill_fraction, 1.0))

        steps: list[dict[str, Any]] = []
        first_overflow_year = -1
        max_history_fill_fraction = 0.0
        history_spill_km3 = 0.0
        history_sink_loss_km3 = 0.0
        history_avulsion_triggered = False

        for year in range(1, simulation_years + 1):
            start_volume_km3 = volume_km3
            inflow_km3 = annual_runoff_km3
            available_km3 = start_volume_km3 + inflow_km3
            evaporation_km3 = min(evaporation_loss_km3, available_km3)
            available_km3 -= evaporation_km3
            spill_volume_km3 = 0.0
            sink_loss_km3 = 0.0
            if storage_capacity_km3 > 0.0 and available_km3 > storage_capacity_km3:
                excess_km3 = available_km3 - storage_capacity_km3
                if overflows:
                    spill_volume_km3 = excess_km3
                    if first_overflow_year < 0:
                        first_overflow_year = year
                else:
                    sink_loss_km3 = excess_km3
                available_km3 = storage_capacity_km3
            elif storage_capacity_km3 <= 0.0 and available_km3 > 0.0:
                sink_loss_km3 = available_km3
                available_km3 = 0.0

            volume_km3 = max(0.0, available_km3)
            step_fill_fraction = volume_km3 / storage_capacity_km3 if storage_capacity_km3 > 0.0 else 0.0
            stage = _overflow_stage(spill_volume_km3, annual_runoff_km3, stage_count)
            spill_pressure = spill_volume_km3 / max(1.0, annual_runoff_km3)
            step_avulsion_risk = _clamp(avulsion_risk * (0.65 + 0.35 * min(1.0, spill_pressure)), 0.0, 1.0)
            step_avulsion_triggered = spill_volume_km3 > 0.0 and step_avulsion_risk >= 0.65

            history_spill_km3 += spill_volume_km3
            history_sink_loss_km3 += sink_loss_km3
            max_history_fill_fraction = max(max_history_fill_fraction, step_fill_fraction)
            history_avulsion_triggered = history_avulsion_triggered or step_avulsion_triggered
            steps.append(
                {
                    "year": year,
                    "start_volume_km3": round(start_volume_km3, 6),
                    "inflow_km3": round(inflow_km3, 6),
                    "evaporation_loss_km3": round(evaporation_km3, 6),
                    "spill_volume_km3": round(spill_volume_km3, 6),
                    "sink_loss_km3": round(sink_loss_km3, 6),
                    "end_volume_km3": round(volume_km3, 6),
                    "fill_fraction": round(step_fill_fraction, 6),
                    "overflow_stage": stage,
                    "avulsion_risk": round(step_avulsion_risk, 6),
                    "avulsion_triggered": step_avulsion_triggered,
                }
            )

        total_step_count += len(steps)
        total_spill_km3 += history_spill_km3
        total_sink_loss_km3 += history_sink_loss_km3
        max_fill_fraction = max(max_fill_fraction, max_history_fill_fraction)
        if history_spill_km3 > 0.0:
            active_history_count += 1
        if history_avulsion_triggered:
            avulsion_trigger_count += 1
        histories.append(
            {
                "id": basin_id,
                "lake_basin_id": basin_id,
                "depression_policy": str(basin.get("depression_policy", "unknown")),
                "overflows": overflows,
                "simulation_year_count": simulation_years,
                "time_step_count": len(steps),
                "storage_capacity_km3": round(storage_capacity_km3, 6),
                "annual_runoff_km3": round(annual_runoff_km3, 6),
                "total_inflow_km3": round(annual_runoff_km3 * simulation_years, 6),
                "total_spill_km3": round(history_spill_km3, 6),
                "total_sink_loss_km3": round(history_sink_loss_km3, 6),
                "max_fill_fraction": round(max_history_fill_fraction, 6),
                "first_overflow_year": first_overflow_year,
                "avulsion_triggered": history_avulsion_triggered,
                "max_avulsion_risk": round(max((float(step["avulsion_risk"]) for step in steps), default=0.0), 6),
                "overflow_path_cell_ids": list(basin.get("overflow_path_cell_ids", [])),
                "steps": steps,
            }
        )

    world["lake_overflow_histories"] = histories
    summary = world.setdefault("summary", {})
    summary["simulated_lake_basin_count"] = len(simulated_lake_basins)
    summary["lake_overflow_history_count"] = len(histories)
    summary["lake_overflow_history_step_count"] = total_step_count
    summary["lake_overflow_simulation_years"] = simulation_years
    summary["lake_overflow_active_history_count"] = active_history_count
    summary["lake_overflow_avulsion_trigger_count"] = avulsion_trigger_count
    summary["lake_overflow_total_spill_km3"] = round(total_spill_km3, 6)
    summary["lake_overflow_total_sink_loss_km3"] = round(total_sink_loss_km3, 6)
    summary["max_lake_overflow_fill_fraction"] = round(max_fill_fraction, 6)
    _enrich_world_with_overflow_channel_history(world, simulated_lake_basins, histories)
    return world
