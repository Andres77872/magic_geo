from __future__ import annotations

import math
from typing import Any

from .grounded_ice_validation import STABILITY_MODEL, require_grounded_ice


THRESHOLD_RISK = 0.65


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _history_by_sheet_id(world: dict[str, Any]) -> dict[int, dict[str, Any]]:
    histories: dict[int, dict[str, Any]] = {}
    for history in world.get("ice_sheet_histories", []):
        sheet_id = int(history.get("ice_sheet_id", -1))
        if sheet_id >= 0:
            histories[sheet_id] = history
    return histories


def _cells_by_sheet_id(world: dict[str, Any]) -> dict[int, list[dict[str, Any]]]:
    grouped: dict[int, list[dict[str, Any]]] = {}
    for cell in world.get("cells", []):
        sheet_id = int(cell.get("ice_sheet_id", -1))
        if sheet_id >= 0:
            grouped.setdefault(sheet_id, []).append(cell)
    return grouped


def _marine_margin_fraction(sheet_cells: list[dict[str, Any]], cells_by_id: dict[int, dict[str, Any]]) -> float:
    if not sheet_cells:
        return 0.0
    margin_count = 0
    for cell in sheet_cells:
        neighbors = cell.get("neighbors", [])
        if not isinstance(neighbors, list):
            continue
        for neighbor_id in neighbors:
            neighbor = cells_by_id.get(int(neighbor_id))
            if neighbor is not None and bool(neighbor.get("is_water", False)):
                margin_count += 1
                break
    return _clamp(margin_count / len(sheet_cells))


def _mean_cell_value(cells: list[dict[str, Any]], key: str, default: float = 0.0) -> float:
    if not cells:
        return default
    return sum(float(cell.get(key, default)) for cell in cells) / len(cells)


def _stability_class(index: float) -> str:
    if index >= 0.75:
        return "unstable"
    if index >= 0.50:
        return "threshold_sensitive"
    if index >= 0.25:
        return "sensitive"
    return "stable"


def enrich_world_with_ice_sheet_stability(world: dict[str, Any]) -> dict[str, Any]:
    grounded_current = require_grounded_ice(world)
    ice_sheets = world.get("ice_sheets", [])
    if not isinstance(ice_sheets, list):
        return world

    histories_by_sheet_id = _history_by_sheet_id(world)
    sheet_cells_by_id = _cells_by_sheet_id(world)
    cells = world.get("cells", [])
    cells_by_id = {int(cell.get("id", index)): cell for index, cell in enumerate(cells)} if isinstance(cells, list) else {}

    stability_histories: list[dict[str, Any]] = []
    total_step_count = 0
    threshold_event_count = 0
    high_instability_count = 0
    stability_sum = 0.0
    calving_sum = 0.0
    grounding_sum = 0.0
    max_stability = 0.0
    total_calving_loss = 0.0
    total_grounding_retreat = 0.0
    class_counts: dict[str, int] = {}

    for sheet in ice_sheets:
        sheet_id = int(sheet.get("id", len(stability_histories)))
        history = histories_by_sheet_id.get(sheet_id, {})
        steps = history.get("steps", []) if isinstance(history, dict) else []
        if not isinstance(steps, list):
            steps = []
        sheet_cells = sheet_cells_by_id.get(sheet_id, [])
        area_km2 = max(1.0, float(sheet.get("area_km2", 1.0)))
        mean_thickness_m = max(0.0, float(sheet.get("mean_ice_thickness_m", 0.0)))
        basal_sliding = _clamp(float(sheet.get("mean_basal_sliding_index", 0.0)))
        velocity_m_y = max(0.0, float(sheet.get("mean_ice_velocity_m_y", 0.0)))
        accumulation_fraction = _clamp(float(sheet.get("accumulation_area_fraction", 0.0)))
        mean_smb_m_y = float(sheet.get("mean_surface_mass_balance_m_y", 0.0))
        retreat_rate_m_y = max(0.0, float(sheet.get("retreat_rate_m_y", 0.0)))
        equilibrium_line_altitude_m = float(sheet.get("equilibrium_line_altitude_m", 0.0))
        mean_cell_elevation_m = _mean_cell_value(sheet_cells, "elevation_m", equilibrium_line_altitude_m)
        marine_margin = _marine_margin_fraction(sheet_cells, cells_by_id)
        thermal_pressure = _clamp((_mean_cell_value(sheet_cells, "temperature_c", -8.0) + 8.0) / 14.0)
        ela_offset_m = equilibrium_line_altitude_m - mean_cell_elevation_m + (0.5 - accumulation_fraction) * 650.0
        calving_susceptibility = _clamp(
            marine_margin * 0.46
            + min(1.0, velocity_m_y / 220.0) * 0.22
            + basal_sliding * 0.18
            + thermal_pressure * 0.10
            + max(0.0, -mean_smb_m_y) * 0.04
        )
        grounding_instability = _clamp(
            marine_margin * 0.42
            + basal_sliding * 0.22
            + min(1.0, max(0.0, ela_offset_m) / 1400.0) * 0.18
            + min(1.0, retreat_rate_m_y / 85.0) * 0.12
            + thermal_pressure * 0.06
        )

        stability_steps: list[dict[str, Any]] = []
        first_threshold_step = -1
        years_to_threshold = -1.0
        elapsed_years = 0.0
        sheet_threshold_events = 0
        sheet_calving_loss = 0.0
        sheet_grounding_retreat = 0.0
        sheet_stability_sum = 0.0
        sheet_max_stability = 0.0

        for index, step in enumerate(steps):
            duration_years = max(1.0, float(step.get("duration_years", 1.0)))
            surface_balance = float(step.get("surface_balance_km3", 0.0))
            dynamic_loss = max(0.0, float(step.get("dynamic_loss_km3", 0.0)))
            retreat_loss = max(0.0, float(step.get("retreat_loss_km3", 0.0)))
            retreat_distance = max(0.0, float(step.get("retreat_distance_km", 0.0)))
            loss = dynamic_loss + retreat_loss
            mass_balance_ratio = surface_balance / max(1.0, loss)
            deficit_index = _clamp((loss - surface_balance) / max(1.0, loss + abs(surface_balance)))
            area_loss = max(0.0, float(step.get("start_area_km2", 0.0)) - float(step.get("end_area_km2", 0.0)))
            area_loss_fraction = _clamp(area_loss / max(1.0, float(step.get("start_area_km2", area_km2))))
            retreat_pace_index = _clamp((retreat_distance / max(1.0, math.sqrt(area_km2))) * 4.0 + area_loss_fraction * 2.0)
            threshold_index = _clamp(
                deficit_index * 0.42
                + calving_susceptibility * 0.22
                + grounding_instability * 0.20
                + retreat_pace_index * 0.16
            )
            threshold_crossed = threshold_index >= THRESHOLD_RISK
            if threshold_crossed:
                sheet_threshold_events += 1
                if first_threshold_step < 0:
                    first_threshold_step = index + 1
                    years_to_threshold = elapsed_years + duration_years
            projected_calving_loss = loss * calving_susceptibility * marine_margin * 0.18
            projected_grounding_retreat = retreat_distance * grounding_instability * (0.4 + marine_margin * 0.6)

            stability_steps.append(
                {
                    "step": index + 1,
                    "start_age_ka": round(float(step.get("start_age_ka", 0.0)), 6),
                    "end_age_ka": round(float(step.get("end_age_ka", 0.0)), 6),
                    "duration_years": round(duration_years, 6),
                    "mass_balance_ratio": round(mass_balance_ratio, 6),
                    "balance_deficit_index": round(deficit_index, 6),
                    "retreat_pace_index": round(retreat_pace_index, 6),
                    "calving_susceptibility_index": round(calving_susceptibility, 6),
                    "grounding_line_instability_index": round(grounding_instability, 6),
                    "retreat_threshold_index": round(threshold_index, 6),
                    "retreat_threshold_crossed": threshold_crossed,
                    "projected_calving_loss_km3": round(projected_calving_loss, 6),
                    "projected_grounding_line_retreat_km": round(projected_grounding_retreat, 6),
                }
            )
            elapsed_years += duration_years
            sheet_calving_loss += projected_calving_loss
            sheet_grounding_retreat += projected_grounding_retreat
            sheet_stability_sum += threshold_index
            sheet_max_stability = max(sheet_max_stability, threshold_index)

        mean_stability = sheet_stability_sum / len(stability_steps) if stability_steps else 0.0
        stability_class = _stability_class(max(sheet_max_stability, mean_stability))
        class_counts[stability_class] = class_counts.get(stability_class, 0) + 1
        if sheet_max_stability >= THRESHOLD_RISK:
            high_instability_count += 1
        threshold_event_count += sheet_threshold_events
        total_step_count += len(stability_steps)
        stability_sum += mean_stability
        calving_sum += calving_susceptibility
        grounding_sum += grounding_instability
        max_stability = max(max_stability, sheet_max_stability)
        total_calving_loss += sheet_calving_loss
        total_grounding_retreat += sheet_grounding_retreat

        sheet["ice_sheet_stability_index"] = round(mean_stability, 6)
        sheet["ice_sheet_stability_class"] = stability_class
        sheet["calving_susceptibility_index"] = round(calving_susceptibility, 6)
        sheet["grounding_line_instability_index"] = round(grounding_instability, 6)
        sheet["equilibrium_line_offset_m"] = round(ela_offset_m, 6)
        sheet["retreat_threshold_event_count"] = sheet_threshold_events
        sheet["first_retreat_threshold_step"] = first_threshold_step

        stability_histories.append(
            {
                "id": len(stability_histories),
                "ice_sheet_id": sheet_id,
                "time_step_count": len(stability_steps),
                "stability_class": stability_class,
                "mean_stability_index": round(mean_stability, 6),
                "max_stability_index": round(sheet_max_stability, 6),
                "calving_susceptibility_index": round(calving_susceptibility, 6),
                "grounding_line_instability_index": round(grounding_instability, 6),
                "marine_margin_fraction": round(marine_margin, 6),
                "equilibrium_line_offset_m": round(ela_offset_m, 6),
                "retreat_threshold_event_count": sheet_threshold_events,
                "first_retreat_threshold_step": first_threshold_step,
                "years_to_retreat_threshold": round(years_to_threshold, 6) if years_to_threshold >= 0.0 else -1.0,
                "total_projected_calving_loss_km3": round(sheet_calving_loss, 6),
                "total_projected_grounding_line_retreat_km": round(sheet_grounding_retreat, 6),
                "steps": stability_steps,
            }
        )

    if grounded_current:
        world["grounded_ice_stability_model"] = dict(STABILITY_MODEL)
    world["ice_sheet_stability_histories"] = stability_histories
    summary = world.setdefault("summary", {})
    if grounded_current:
        summary["grounded_ice_stability_model"] = STABILITY_MODEL["model_type"]
    history_count = len(stability_histories)
    summary["ice_sheet_stability_history_count"] = history_count
    summary["ice_sheet_stability_step_count"] = total_step_count
    summary["ice_sheet_retreat_threshold_event_count"] = threshold_event_count
    summary["high_ice_sheet_instability_count"] = high_instability_count
    summary["mean_ice_sheet_stability_index"] = round(stability_sum / history_count, 6) if history_count else 0.0
    summary["max_ice_sheet_stability_index"] = round(max_stability, 6)
    summary["mean_calving_susceptibility_index"] = round(calving_sum / history_count, 6) if history_count else 0.0
    summary["mean_grounding_line_instability_index"] = round(grounding_sum / history_count, 6) if history_count else 0.0
    summary["ice_sheet_total_projected_calving_loss_km3"] = round(total_calving_loss, 6)
    summary["ice_sheet_total_projected_grounding_line_retreat_km"] = round(total_grounding_retreat, 6)
    summary["ice_sheet_stability_class_counts"] = dict(sorted(class_counts.items()))
    return world
