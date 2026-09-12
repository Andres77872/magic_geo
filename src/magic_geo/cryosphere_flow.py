from __future__ import annotations

import math
from typing import Any

from .grounded_ice_validation import APPLICABLE, RAW_THICKNESS, require_grounded_ice
from .planet_parameters import planet_radius_km, surface_gravity_m_s2


ICE_FLOW_REFERENCE_GRAVITY_M_S2 = 9.81


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _great_circle_km(a: dict[str, Any], b: dict[str, Any], radius_km: float) -> float:
    lat_a = math.radians(float(a.get("lat_deg", 0.0)))
    lat_b = math.radians(float(b.get("lat_deg", 0.0)))
    dlat = lat_b - lat_a
    dlon = math.radians(float(b.get("lon_deg", 0.0)) - float(a.get("lon_deg", 0.0)))
    hav = math.sin(dlat / 2.0) ** 2 + math.cos(lat_a) * math.cos(lat_b) * math.sin(dlon / 2.0) ** 2
    return 2.0 * radius_km * math.asin(min(1.0, math.sqrt(hav)))


def _select_flowline_sources(cells: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    candidates = [
        cell
        for cell in cells
        if float(cell.get("ice_thickness_m", 0.0)) > 0.0 and int(cell.get("glacier_flow_to", -1)) >= 0
    ]
    candidates.sort(
        key=lambda cell: (
            float(cell.get("ice_thickness_m", 0.0))
            * (1.0 + float(cell.get("ice_velocity_m_y", 0.0)) / 100.0)
            * (1.0 + float(cell.get("basal_sliding_index", 0.0))),
            float(cell.get("ice_surface_mass_balance_m_y", 0.0)),
        ),
        reverse=True,
    )
    selected: list[dict[str, Any]] = []
    used_sheets: set[int] = set()
    selected_ids: set[int] = set()
    for cell in candidates:
        sheet_id = int(cell.get("ice_sheet_id", -1))
        if sheet_id in used_sheets:
            continue
        selected.append(cell)
        used_sheets.add(sheet_id)
        selected_ids.add(int(cell.get("id", -1)))
        if len(selected) >= limit:
            break
    for cell in candidates:
        if len(selected) >= limit:
            break
        cell_id = int(cell.get("id", -1))
        if cell_id in selected_ids:
            continue
        selected.append(cell)
        selected_ids.add(cell_id)
    return selected


def _follow_flowline(source: dict[str, Any], cells_by_id: dict[int, dict[str, Any]], max_length: int, *, grounded_current: bool = False) -> list[dict[str, Any]]:
    path: list[dict[str, Any]] = []
    seen: set[int] = set()
    current = source
    source_sheet_id = int(source.get("ice_sheet_id", -1))
    for _ in range(max_length):
        if grounded_current and (not current[APPLICABLE] or current[RAW_THICKNESS] <= 0.0):
            break
        cell_id = int(current.get("id", -1))
        if cell_id < 0 or cell_id in seen:
            break
        path.append(current)
        seen.add(cell_id)
        next_id = int(current.get("glacier_flow_to", -1))
        if next_id < 0 or next_id == cell_id:
            break
        next_cell = cells_by_id.get(next_id)
        if next_cell is None:
            break
        if int(next_cell.get("ice_sheet_id", source_sheet_id)) not in {source_sheet_id, -1}:
            break
        current = next_cell
    return path


def enrich_world_with_ice_flowline_history(
    world: dict[str, Any],
    flowline_limit: int = 10,
    max_path_length: int = 48,
) -> dict[str, Any]:
    grounded_current = require_grounded_ice(world)
    cells = world.get("cells", [])
    if not isinstance(cells, list) or not cells:
        return world

    radius_km = planet_radius_km(world)
    gravity_m_s2 = surface_gravity_m_s2(
        world,
        earth_reference_m_s2=ICE_FLOW_REFERENCE_GRAVITY_M_S2,
    )
    cells_by_id = {int(cell.get("id", index)): cell for index, cell in enumerate(cells)}
    for cell in cells:
        cell["ice_flowline_flux_km3_y"] = 0.0
        cell["ice_flowline_driving_stress_kpa"] = 0.0
        cell["ice_flowline_strain_heating_index"] = 0.0
        cell["ice_flowline_path_count"] = 0

    histories: list[dict[str, Any]] = []
    total_step_count = 0
    total_flux_km3_y = 0.0
    total_dynamic_loss_km3_y = 0.0
    total_melt_loss_km3_y = 0.0
    total_erosion_m = 0.0
    total_path_length_km = 0.0
    max_driving_stress_kpa = 0.0
    max_final_flux_km3_y = 0.0
    max_strain_heating_index = 0.0

    for source in _select_flowline_sources(cells, flowline_limit):
        path = _follow_flowline(source, cells_by_id, max_path_length, grounded_current=grounded_current)
        if len(path) < 2:
            continue

        flow_flux_km3_y = 0.0
        path_length_km = 0.0
        history_flux = 0.0
        history_dynamic_loss = 0.0
        history_melt_loss = 0.0
        history_erosion = 0.0
        history_max_stress = 0.0
        history_max_heating = 0.0
        steps: list[dict[str, Any]] = []

        for index, cell in enumerate(path):
            next_cell = path[index + 1] if index + 1 < len(path) else None
            segment_length_km = _great_circle_km(cell, next_cell, radius_km) if next_cell is not None else 0.0
            path_length_km += segment_length_km
            thickness_m = max(0.0, float(cell.get("ice_thickness_m", 0.0)))
            area_km2 = max(1.0, float(cell.get("area_km2", 1.0)))
            velocity_m_y = max(0.0, float(cell.get("ice_velocity_m_y", 0.0)))
            basal_sliding = _clamp(float(cell.get("basal_sliding_index", 0.0)), 0.0, 1.0)
            smb_m_y = float(cell.get("ice_surface_mass_balance_m_y", 0.0))
            start_flux_km3_y = flow_flux_km3_y
            slope = 0.0
            if next_cell is not None and segment_length_km > 0.0:
                slope = max(0.0, (float(cell.get("elevation_m", 0.0)) - float(next_cell.get("elevation_m", 0.0))) / (segment_length_km * 1000.0))
            driving_stress_kpa = 917.0 * gravity_m_s2 * thickness_m * max(0.0002, slope) / 1000.0
            accumulation_flux_km3_y = max(0.0, smb_m_y) * area_km2 / 1000.0
            ablation_loss_km3_y = max(0.0, -smb_m_y) * area_km2 / 1000.0
            dynamic_capacity_km3_y = velocity_m_y * thickness_m * math.sqrt(area_km2) / 1_000_000.0 * (0.55 + basal_sliding)
            available_flux_km3_y = start_flux_km3_y + accumulation_flux_km3_y
            dynamic_flux_km3_y = min(available_flux_km3_y, dynamic_capacity_km3_y)
            dynamic_loss_km3_y = min(dynamic_flux_km3_y * (0.03 + basal_sliding * 0.04), available_flux_km3_y)
            melt_loss_km3_y = min(max(0.0, available_flux_km3_y - dynamic_loss_km3_y), ablation_loss_km3_y)
            if next_cell is None:
                terminal_loss_km3_y = max(0.0, available_flux_km3_y - dynamic_loss_km3_y - melt_loss_km3_y)
                dynamic_loss_km3_y += terminal_loss_km3_y
                dynamic_flux_km3_y = max(dynamic_flux_km3_y, dynamic_loss_km3_y)
                end_flux_km3_y = 0.0
            else:
                end_flux_km3_y = max(0.0, available_flux_km3_y - dynamic_loss_km3_y - melt_loss_km3_y)
            balance_residual_km3_y = available_flux_km3_y - dynamic_loss_km3_y - melt_loss_km3_y - end_flux_km3_y
            strain_heating_index = _clamp(driving_stress_kpa / 450.0 * (velocity_m_y / 220.0) * (0.4 + basal_sliding), 0.0, 1.0)
            erosion_m = max(0.0, float(cell.get("glacial_erosion_m", 0.0))) * (0.25 + 0.75 * strain_heating_index)

            cell["ice_flowline_flux_km3_y"] = round(max(float(cell.get("ice_flowline_flux_km3_y", 0.0)), end_flux_km3_y), 6)
            cell["ice_flowline_driving_stress_kpa"] = round(
                max(float(cell.get("ice_flowline_driving_stress_kpa", 0.0)), driving_stress_kpa),
                6,
            )
            cell["ice_flowline_strain_heating_index"] = round(
                max(float(cell.get("ice_flowline_strain_heating_index", 0.0)), strain_heating_index),
                6,
            )
            cell["ice_flowline_path_count"] = int(cell.get("ice_flowline_path_count", 0)) + 1

            steps.append(
                {
                    "step": index + 1,
                    "cell_id": int(cell.get("id", -1)),
                    "flow_to_cell_id": int(cell.get("glacier_flow_to", -1)),
                    "segment_length_km": round(segment_length_km, 6),
                    "surface_slope": round(slope, 8),
                    "ice_thickness_m": round(thickness_m, 6),
                    "start_flux_km3_y": round(start_flux_km3_y, 6),
                    "accumulation_flux_km3_y": round(accumulation_flux_km3_y, 6),
                    "dynamic_flux_km3_y": round(dynamic_flux_km3_y, 6),
                    "dynamic_loss_km3_y": round(dynamic_loss_km3_y, 6),
                    "melt_loss_km3_y": round(melt_loss_km3_y, 6),
                    "end_flux_km3_y": round(end_flux_km3_y, 6),
                    "balance_residual_km3_y": round(balance_residual_km3_y, 6),
                    "driving_stress_kpa": round(driving_stress_kpa, 6),
                    "basal_sliding_index": round(basal_sliding, 6),
                    "ice_velocity_m_y": round(velocity_m_y, 6),
                    "strain_heating_index": round(strain_heating_index, 6),
                    "glacial_erosion_m": round(erosion_m, 6),
                }
            )
            history_flux += dynamic_flux_km3_y
            history_dynamic_loss += dynamic_loss_km3_y
            history_melt_loss += melt_loss_km3_y
            history_erosion += erosion_m
            history_max_stress = max(history_max_stress, driving_stress_kpa)
            history_max_heating = max(history_max_heating, strain_heating_index)
            flow_flux_km3_y = end_flux_km3_y

        final_flux_km3_y = float(steps[-1]["end_flux_km3_y"]) if steps else 0.0
        total_step_count += len(steps)
        total_flux_km3_y += history_flux
        total_dynamic_loss_km3_y += history_dynamic_loss
        total_melt_loss_km3_y += history_melt_loss
        total_erosion_m += history_erosion
        total_path_length_km += path_length_km
        max_driving_stress_kpa = max(max_driving_stress_kpa, history_max_stress)
        max_final_flux_km3_y = max(max_final_flux_km3_y, final_flux_km3_y)
        max_strain_heating_index = max(max_strain_heating_index, history_max_heating)
        histories.append(
            {
                "id": len(histories),
                "source_cell_id": int(source.get("id", -1)),
                "ice_sheet_id": int(source.get("ice_sheet_id", -1)),
                "flowline_cell_ids": [int(cell.get("id", -1)) for cell in path],
                "time_step_count": len(steps),
                "path_length_km": round(path_length_km, 6),
                "total_dynamic_flux_km3_y": round(history_flux, 6),
                "total_dynamic_loss_km3_y": round(history_dynamic_loss, 6),
                "total_melt_loss_km3_y": round(history_melt_loss, 6),
                "total_glacial_erosion_m": round(history_erosion, 6),
                "max_driving_stress_kpa": round(history_max_stress, 6),
                "max_strain_heating_index": round(history_max_heating, 6),
                "final_ice_flux_km3_y": round(final_flux_km3_y, 6),
                "steps": steps,
            }
        )

    world["ice_flowline_histories"] = histories
    summary = world.setdefault("summary", {})
    summary["ice_flowline_history_count"] = len(histories)
    summary["ice_flowline_step_count"] = total_step_count
    summary["ice_flowline_cell_count"] = sum(1 for cell in cells if int(cell.get("ice_flowline_path_count", 0)) > 0)
    summary["ice_flowline_total_dynamic_flux_km3_y"] = round(total_flux_km3_y, 6)
    summary["ice_flowline_total_dynamic_loss_km3_y"] = round(total_dynamic_loss_km3_y, 6)
    summary["ice_flowline_total_melt_loss_km3_y"] = round(total_melt_loss_km3_y, 6)
    summary["ice_flowline_total_glacial_erosion_m"] = round(total_erosion_m, 6)
    summary["ice_flowline_total_path_length_km"] = round(total_path_length_km, 6)
    summary["ice_flowline_mean_path_length_km"] = round(total_path_length_km / len(histories), 6) if histories else 0.0
    summary["ice_flowline_max_driving_stress_kpa"] = round(max_driving_stress_kpa, 6)
    summary["ice_flowline_max_final_flux_km3_y"] = round(max_final_flux_km3_y, 6)
    summary["ice_flowline_max_strain_heating_index"] = round(max_strain_heating_index, 6)
    return world
