from __future__ import annotations

import math
from typing import Any

from .grounded_ice_validation import require_grounded_ice


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def enrich_world_with_ice_sheet_history(world: dict[str, Any], step_count: int = 8) -> dict[str, Any]:
    grounded_current = require_grounded_ice(world)
    ice_sheets = world.get("ice_sheets", [])
    if not isinstance(ice_sheets, list):
        return world

    histories: list[dict[str, Any]] = []
    total_step_count = 0
    total_surface_balance_km3 = 0.0
    total_dynamic_loss_km3 = 0.0
    total_retreat_loss_km3 = 0.0
    total_retreat_distance_km = 0.0
    peak_volume_km3 = 0.0
    final_volume_sum_km3 = 0.0

    for sheet in ice_sheets:
        sheet_id = int(sheet.get("id", len(histories)))
        area_km2 = max(0.0, float(sheet.get("area_km2", 0.0)))
        mean_thickness_m = max(0.0, float(sheet.get("mean_ice_thickness_m", 0.0)))
        current_volume_km3 = area_km2 * mean_thickness_m / 1000.0
        deglaciation_age_ka = max(1.0, float(sheet.get("mean_deglaciation_age_ka", 1.0)))
        duration_ka = deglaciation_age_ka / max(1, step_count)
        surface_mass_balance_m_y = float(sheet.get("mean_surface_mass_balance_m_y", 0.0))
        basal_sliding = _clamp(float(sheet.get("mean_basal_sliding_index", 0.0)), 0.0, 1.0)
        ice_velocity_m_y = max(0.0, float(sheet.get("mean_ice_velocity_m_y", 0.0)))
        retreat_rate_m_y = max(0.0, float(sheet.get("retreat_rate_m_y", 0.0)))
        accumulation_fraction = _clamp(float(sheet.get("accumulation_area_fraction", 0.0)), 0.0, 1.0)
        moraine_deposition_m = max(0.0, float(sheet.get("mean_moraine_deposition_m", 0.0)))

        retreat_stage = str(sheet.get("retreat_stage", "stable"))
        stage_retreat_bias = {
            "advancing": 0.20,
            "stable": 0.55,
            "retreating": 1.00,
            "relict": 1.25,
        }.get(retreat_stage, 0.70)
        initial_multiplier = 1.0 + stage_retreat_bias * (0.20 + max(0.0, 0.85 - accumulation_fraction) * 0.15)
        volume_km3 = current_volume_km3 * initial_multiplier
        working_area_km2 = area_km2 * (1.0 + stage_retreat_bias * 0.08)
        steps: list[dict[str, Any]] = []
        history_surface_balance = 0.0
        history_dynamic_loss = 0.0
        history_retreat_loss = 0.0
        history_retreat_distance = 0.0
        history_peak_volume = volume_km3

        for index in range(step_count):
            start_age_ka = max(0.0, deglaciation_age_ka - index * duration_ka)
            end_age_ka = max(0.0, deglaciation_age_ka - (index + 1) * duration_ka)
            duration_years = max(1.0, (start_age_ka - end_age_ka) * 1000.0)
            climate_warming = (index + 1) / max(1, step_count)
            effective_smb_m_y = surface_mass_balance_m_y - stage_retreat_bias * climate_warming * 0.18
            surface_balance_km3 = effective_smb_m_y * working_area_km2 * duration_years / 1000.0 * 0.035
            velocity_loss_m_y = ice_velocity_m_y * (0.004 + basal_sliding * 0.010)
            negative_smb_loss_m_y = max(0.0, -effective_smb_m_y) * 0.10
            dynamic_loss_km3 = (velocity_loss_m_y + negative_smb_loss_m_y) * working_area_km2 * duration_years / 1000.0 * 0.035
            retreat_distance_km = (retreat_rate_m_y * stage_retreat_bias * duration_years / 1000.0) + (
                max(0.0, 0.60 - accumulation_fraction) * duration_years * 0.000025
            )
            front_width_km = math.sqrt(max(1.0, working_area_km2))
            retreat_loss_km3 = retreat_distance_km * front_width_km * mean_thickness_m / 1000.0 * 0.08

            raw_delta = surface_balance_km3 - dynamic_loss_km3 - retreat_loss_km3
            max_gain = max(1.0, volume_km3 * 0.16)
            max_loss = max(1.0, volume_km3 * 0.22)
            bounded_delta = _clamp(raw_delta, -max_loss, max_gain)
            stabilization_adjustment_km3 = bounded_delta - raw_delta
            end_volume_km3 = max(0.0, volume_km3 + bounded_delta)

            area_loss_fraction = _clamp(retreat_distance_km / max(1.0, front_width_km) * 0.08, 0.0, 0.18)
            if bounded_delta > 0.0 and retreat_stage == "advancing":
                area_loss_fraction = -min(0.04, bounded_delta / max(1.0, volume_km3) * 0.10)
            end_area_km2 = max(area_km2 * 0.10, working_area_km2 * (1.0 - area_loss_fraction))
            step_moraine_m = moraine_deposition_m * (0.35 + 0.65 * min(1.0, retreat_distance_km / 5.0 + dynamic_loss_km3 / max(1.0, volume_km3)))

            steps.append(
                {
                    "step": index + 1,
                    "start_age_ka": round(start_age_ka, 6),
                    "end_age_ka": round(end_age_ka, 6),
                    "duration_years": round(duration_years, 6),
                    "start_area_km2": round(working_area_km2, 6),
                    "end_area_km2": round(end_area_km2, 6),
                    "start_volume_km3": round(volume_km3, 6),
                    "end_volume_km3": round(end_volume_km3, 6),
                    "surface_mass_balance_m_y": round(effective_smb_m_y, 6),
                    "surface_balance_km3": round(surface_balance_km3, 6),
                    "dynamic_loss_km3": round(dynamic_loss_km3, 6),
                    "retreat_loss_km3": round(retreat_loss_km3, 6),
                    "stabilization_adjustment_km3": round(stabilization_adjustment_km3, 6),
                    "retreat_distance_km": round(retreat_distance_km, 6),
                    "basal_sliding_index": round(basal_sliding, 6),
                    "ice_velocity_m_y": round(ice_velocity_m_y, 6),
                    "accumulation_area_fraction": round(accumulation_fraction, 6),
                    "moraine_deposition_m": round(step_moraine_m, 6),
                }
            )

            history_surface_balance += surface_balance_km3
            history_dynamic_loss += dynamic_loss_km3
            history_retreat_loss += retreat_loss_km3
            history_retreat_distance += retreat_distance_km
            history_peak_volume = max(history_peak_volume, end_volume_km3)
            volume_km3 = end_volume_km3
            working_area_km2 = end_area_km2

        final_volume_sum_km3 += volume_km3
        peak_volume_km3 = max(peak_volume_km3, history_peak_volume)
        total_step_count += len(steps)
        total_surface_balance_km3 += history_surface_balance
        total_dynamic_loss_km3 += history_dynamic_loss
        total_retreat_loss_km3 += history_retreat_loss
        total_retreat_distance_km += history_retreat_distance
        histories.append(
            {
                "id": sheet_id,
                "ice_sheet_id": sheet_id,
                "retreat_stage": retreat_stage,
                "time_step_count": len(steps),
                "initial_volume_km3": round(steps[0]["start_volume_km3"] if steps else current_volume_km3, 6),
                "final_volume_km3": round(volume_km3, 6),
                "peak_volume_km3": round(history_peak_volume, 6),
                "total_surface_balance_km3": round(history_surface_balance, 6),
                "total_dynamic_loss_km3": round(history_dynamic_loss, 6),
                "total_retreat_loss_km3": round(history_retreat_loss, 6),
                "total_retreat_distance_km": round(history_retreat_distance, 6),
                "mean_deglaciation_age_ka": round(deglaciation_age_ka, 6),
                "steps": steps,
            }
        )

    world["ice_sheet_histories"] = histories
    summary = world.setdefault("summary", {})
    summary["ice_sheet_history_count"] = len(histories)
    summary["ice_sheet_history_step_count"] = total_step_count
    summary["ice_sheet_history_total_surface_balance_km3"] = round(total_surface_balance_km3, 6)
    summary["ice_sheet_history_total_dynamic_loss_km3"] = round(total_dynamic_loss_km3, 6)
    summary["ice_sheet_history_total_retreat_loss_km3"] = round(total_retreat_loss_km3, 6)
    summary["ice_sheet_history_total_retreat_distance_km"] = round(total_retreat_distance_km, 6)
    summary["ice_sheet_history_peak_volume_km3"] = round(peak_volume_km3, 6)
    summary["ice_sheet_history_final_volume_km3"] = round(final_volume_sum_km3, 6)
    return world
