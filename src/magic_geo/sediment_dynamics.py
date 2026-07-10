from __future__ import annotations

import math
from typing import Any


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _column_by_basin_id(world: dict[str, Any]) -> dict[int, dict[str, Any]]:
    columns: dict[int, dict[str, Any]] = {}
    for column in world.get("stratigraphic_columns", []):
        basin_id = int(column.get("basin_id", -1))
        if basin_id >= 0:
            columns[basin_id] = column
    return columns


def _dominant_coastal_trend(world: dict[str, Any]) -> tuple[str, float]:
    coastal_features = world.get("coastal_features", [])
    if not isinstance(coastal_features, list) or not coastal_features:
        return "none", 0.0
    trend_counts: dict[str, int] = {}
    migration_sum = 0.0
    for feature in coastal_features:
        trend = str(feature.get("shoreline_trend", "unknown"))
        trend_counts[trend] = trend_counts.get(trend, 0) + 1
        migration_sum += float(feature.get("migration_rate_m_y", 0.0))
    dominant = max(trend_counts.items(), key=lambda item: item[1])[0]
    return dominant, migration_sum / len(coastal_features)


def _step_facies(column: dict[str, Any] | None, index: int) -> str:
    if not column:
        return "basin_fill"
    layers = column.get("layers", [])
    if isinstance(layers, list) and layers:
        layer = layers[min(index, len(layers) - 1)]
        return str(layer.get("facies", column.get("dominant_facies", "basin_fill")))
    return str(column.get("dominant_facies", "basin_fill"))


def enrich_world_with_sediment_transport_history(world: dict[str, Any], step_count: int = 6) -> dict[str, Any]:
    basins = world.get("sedimentary_basins", [])
    if not isinstance(basins, list):
        return world

    columns = _column_by_basin_id(world)
    coastal_trend, mean_coastal_migration_rate = _dominant_coastal_trend(world)
    histories: list[dict[str, Any]] = []
    total_step_count = 0
    total_input_m = 0.0
    total_deposition_m = 0.0
    total_export_m = 0.0
    total_compaction_m = 0.0
    active_history_count = 0
    max_progradation_distance_km = 0.0
    fill_fraction_sum = 0.0

    for basin in basins:
        basin_record_id = int(basin.get("id", len(histories)))
        drainage_basin_id = int(basin.get("basin_id", -1))
        column = columns.get(drainage_basin_id)
        area_km2 = max(1.0, float(basin.get("area_km2", 1.0)))
        target_thickness_m = max(
            0.05,
            float(basin.get("mean_sediment_thickness_m", 0.0)),
            float((column or {}).get("total_thickness_m", 0.0)),
        )
        subsidence_index = _clamp(float(basin.get("mean_subsidence_index", 0.0)), 0.0, 1.0)
        sediment_flux_index = _clamp(float((column or {}).get("sediment_flux_index", 0.35)), 0.0, 1.0)
        preservation = _clamp(float((column or {}).get("preservation_potential", 0.45)), 0.0, 1.0)
        sequence_phase = str((column or {}).get("sequence_phase", "aggradation"))
        depositional_age_ma = max(1.0, float(basin.get("depositional_age_ma", (column or {}).get("depositional_span_ma", 1.0))))
        duration_ma = depositional_age_ma / max(1, step_count)
        thickness_m = target_thickness_m * 0.18
        accommodation_m = target_thickness_m * (1.0 + subsidence_index * 0.75)
        front_width_km = math.sqrt(area_km2)
        steps: list[dict[str, Any]] = []
        history_input = 0.0
        history_deposition = 0.0
        history_export = 0.0
        history_compaction = 0.0
        history_progradation = 0.0

        for index in range(step_count):
            flux_pulse = 0.75 + sediment_flux_index * 0.60 + (index + 1) / step_count * 0.20
            sediment_input_m = max(0.002, target_thickness_m / step_count * flux_pulse)
            deposition_fraction = _clamp(
                0.34 + subsidence_index * 0.24 + preservation * 0.22 - sediment_flux_index * 0.08,
                0.25,
                0.88,
            )
            deposited_m = sediment_input_m * deposition_fraction
            exported_m = sediment_input_m - deposited_m
            compaction_loss_m = min(thickness_m + deposited_m, deposited_m * (0.035 + (1.0 - preservation) * 0.055))
            accommodation_created_m = target_thickness_m / step_count * (0.35 + subsidence_index * 0.75)
            accommodation_m += accommodation_created_m
            start_thickness_m = thickness_m
            thickness_m = max(0.0, start_thickness_m + deposited_m - compaction_loss_m)
            fill_fraction = _clamp(thickness_m / max(0.001, accommodation_m), 0.0, 2.5)
            progradation_distance_km = max(
                0.0,
                (deposited_m - compaction_loss_m) * area_km2 / max(1.0, front_width_km) * 0.00035,
            )
            if mean_coastal_migration_rate < 0.0:
                progradation_distance_km *= 0.65
            elif coastal_trend in {"prograding", "delta_switching"}:
                progradation_distance_km *= 1.25

            steps.append(
                {
                    "step": index + 1,
                    "start_age_ma": round(max(0.0, depositional_age_ma - index * duration_ma), 6),
                    "end_age_ma": round(max(0.0, depositional_age_ma - (index + 1) * duration_ma), 6),
                    "duration_ma": round(duration_ma, 6),
                    "facies": _step_facies(column, index),
                    "sequence_phase": sequence_phase,
                    "start_sediment_thickness_m": round(start_thickness_m, 6),
                    "sediment_input_m": round(sediment_input_m, 6),
                    "deposited_m": round(deposited_m, 6),
                    "exported_m": round(exported_m, 6),
                    "compaction_loss_m": round(compaction_loss_m, 6),
                    "end_sediment_thickness_m": round(thickness_m, 6),
                    "accommodation_created_m": round(accommodation_created_m, 6),
                    "accommodation_fill_fraction": round(fill_fraction, 6),
                    "progradation_distance_km": round(progradation_distance_km, 6),
                    "sediment_flux_index": round(sediment_flux_index, 6),
                    "subsidence_index": round(subsidence_index, 6),
                    "preservation_potential": round(preservation, 6),
                }
            )
            history_input += sediment_input_m
            history_deposition += deposited_m
            history_export += exported_m
            history_compaction += compaction_loss_m
            history_progradation += progradation_distance_km

        total_step_count += len(steps)
        total_input_m += history_input
        total_deposition_m += history_deposition
        total_export_m += history_export
        total_compaction_m += history_compaction
        fill_fraction_sum += float(steps[-1]["accommodation_fill_fraction"]) if steps else 0.0
        max_progradation_distance_km = max(max_progradation_distance_km, history_progradation)
        if history_deposition > 0.0:
            active_history_count += 1
        histories.append(
            {
                "id": basin_record_id,
                "sedimentary_basin_id": basin_record_id,
                "basin_id": drainage_basin_id,
                "basin_type": str(basin.get("type", "unknown")),
                "dominant_resource": str(basin.get("dominant_resource", "none")),
                "time_step_count": len(steps),
                "area_km2": round(area_km2, 6),
                "initial_sediment_thickness_m": round(steps[0]["start_sediment_thickness_m"] if steps else 0.0, 6),
                "final_sediment_thickness_m": round(thickness_m, 6),
                "total_sediment_input_m": round(history_input, 6),
                "total_deposition_m": round(history_deposition, 6),
                "total_export_m": round(history_export, 6),
                "total_compaction_loss_m": round(history_compaction, 6),
                "total_progradation_distance_km": round(history_progradation, 6),
                "final_accommodation_fill_fraction": round(float(steps[-1]["accommodation_fill_fraction"]) if steps else 0.0, 6),
                "steps": steps,
            }
        )

    world["sediment_transport_histories"] = histories
    summary = world.setdefault("summary", {})
    summary["sediment_transport_history_count"] = len(histories)
    summary["sediment_transport_history_step_count"] = total_step_count
    summary["active_sediment_transport_history_count"] = active_history_count
    summary["sediment_transport_total_input_m"] = round(total_input_m, 6)
    summary["sediment_transport_total_deposition_m"] = round(total_deposition_m, 6)
    summary["sediment_transport_total_export_m"] = round(total_export_m, 6)
    summary["sediment_transport_total_compaction_m"] = round(total_compaction_m, 6)
    summary["sediment_transport_mean_final_fill_fraction"] = round(fill_fraction_sum / len(histories), 6) if histories else 0.0
    summary["sediment_transport_max_progradation_distance_km"] = round(max_progradation_distance_km, 6)
    return world
