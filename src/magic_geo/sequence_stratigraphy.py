from __future__ import annotations

from typing import Any


SYSTEMS_TRACTS = {
    "lowstand_systems_tract",
    "transgressive_systems_tract",
    "highstand_systems_tract",
    "falling_stage_systems_tract",
    "aggradational_systems_tract",
}
SEQUENCE_SURFACES = {
    "none",
    "sequence_boundary",
    "transgressive_surface",
    "maximum_flooding_surface",
    "regressive_surface",
}


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _history_by_basin_id(world: dict[str, Any]) -> dict[int, dict[str, Any]]:
    histories: dict[int, dict[str, Any]] = {}
    for history in world.get("sediment_transport_histories", []):
        basin_id = int(history.get("basin_id", -1))
        if basin_id >= 0:
            histories[basin_id] = history
    return histories


def _classify_systems_tract(step: dict[str, Any], previous_fill: float) -> str:
    deposited = max(0.0, float(step.get("deposited_m", 0.0)))
    accommodation = max(0.0, float(step.get("accommodation_created_m", 0.0)))
    exported = max(0.0, float(step.get("exported_m", 0.0)))
    fill = _clamp(float(step.get("accommodation_fill_fraction", 0.0)), 0.0, 2.5)
    progradation = max(0.0, float(step.get("progradation_distance_km", 0.0)))
    ratio = accommodation / max(0.001, deposited)
    fill_delta = fill - previous_fill

    if ratio >= 1.25 and fill_delta <= 0.08:
        return "transgressive_systems_tract"
    if ratio <= 0.70 and fill_delta < -0.02:
        return "falling_stage_systems_tract"
    if fill >= 0.72 and progradation > 0.0:
        return "highstand_systems_tract"
    if ratio <= 0.90 and (progradation > 0.0 or exported > deposited * 0.45):
        return "lowstand_systems_tract"
    return "aggradational_systems_tract"


def _shoreline_trajectory(step: dict[str, Any], previous_fill: float) -> str:
    progradation = float(step.get("progradation_distance_km", 0.0))
    fill = float(step.get("accommodation_fill_fraction", 0.0))
    fill_delta = fill - previous_fill
    if progradation > 0.05 and fill_delta >= -0.02:
        return "progradational"
    if fill_delta < -0.05:
        return "retrogradational"
    return "aggradational"


def _surface_for_step(
    index: int,
    max_flooding_index: int,
    systems_tract: str,
    accommodation_ratio: float,
    shoreline_trajectory: str,
) -> str:
    if index == 0:
        return "sequence_boundary"
    if index == max_flooding_index:
        return "maximum_flooding_surface"
    if systems_tract == "transgressive_systems_tract":
        return "transgressive_surface"
    if shoreline_trajectory == "progradational" and accommodation_ratio <= 1.05:
        return "regressive_surface"
    return "none"


def enrich_world_with_sequence_stratigraphy(world: dict[str, Any]) -> dict[str, Any]:
    columns = world.get("stratigraphic_columns", [])
    if not isinstance(columns, list):
        return world

    histories_by_basin_id = _history_by_basin_id(world)
    sequence_histories: list[dict[str, Any]] = []
    total_steps = 0
    total_events = 0
    sequence_boundary_count = 0
    transgressive_surface_count = 0
    maximum_flooding_surface_count = 0
    regressive_surface_count = 0
    accommodation_ratio_sum = 0.0
    flooding_index_sum = 0.0
    systems_tract_counts: dict[str, int] = {}
    trajectory_counts: dict[str, int] = {}

    for column in columns:
        basin_id = int(column.get("basin_id", -1))
        transport_history = histories_by_basin_id.get(basin_id)
        source_steps = transport_history.get("steps", []) if isinstance(transport_history, dict) else []
        if not isinstance(source_steps, list):
            source_steps = []

        ratios = [
            max(0.0, float(step.get("accommodation_created_m", 0.0))) / max(0.001, float(step.get("deposited_m", 0.0)))
            for step in source_steps
            if isinstance(step, dict)
        ]
        if len(ratios) > 1:
            post_boundary_ratios = ratios[1:]
            max_ratio = max(post_boundary_ratios, default=0.0)
            max_flooding_index = 1 + post_boundary_ratios.index(max_ratio)
        else:
            max_ratio = max(ratios, default=0.0)
            max_flooding_index = 0 if ratios else -1

        steps: list[dict[str, Any]] = []
        history_surface_counts = {surface: 0 for surface in SEQUENCE_SURFACES}
        history_tract_counts: dict[str, int] = {}
        history_trajectory_counts: dict[str, int] = {}
        previous_fill = 0.0
        history_ratio_sum = 0.0
        history_flooding_sum = 0.0

        for index, source_step in enumerate(source_steps):
            if not isinstance(source_step, dict):
                continue
            deposited = max(0.0, float(source_step.get("deposited_m", 0.0)))
            accommodation = max(0.0, float(source_step.get("accommodation_created_m", 0.0)))
            exported = max(0.0, float(source_step.get("exported_m", 0.0)))
            accommodation_ratio = accommodation / max(0.001, deposited)
            supply_index = _clamp(deposited / max(0.001, deposited + exported + accommodation))
            flooding_index = _clamp(accommodation_ratio / max(1.0, max_ratio))
            systems_tract = _classify_systems_tract(source_step, previous_fill)
            trajectory = _shoreline_trajectory(source_step, previous_fill)
            surface = _surface_for_step(index, max_flooding_index, systems_tract, accommodation_ratio, trajectory)
            fill = float(source_step.get("accommodation_fill_fraction", 0.0))

            steps.append(
                {
                    "step": int(source_step.get("step", index + 1)),
                    "start_age_ma": round(float(source_step.get("start_age_ma", 0.0)), 6),
                    "end_age_ma": round(float(source_step.get("end_age_ma", 0.0)), 6),
                    "facies": str(source_step.get("facies", column.get("dominant_facies", "basin_fill"))),
                    "systems_tract": systems_tract,
                    "sequence_surface": surface,
                    "shoreline_trajectory": trajectory,
                    "accommodation_to_deposition_ratio": round(accommodation_ratio, 6),
                    "sediment_supply_index": round(supply_index, 6),
                    "relative_sea_level_index": round(_clamp(fill / 2.5), 6),
                    "flooding_index": round(flooding_index, 6),
                    "progradation_distance_km": round(max(0.0, float(source_step.get("progradation_distance_km", 0.0))), 6),
                    "preservation_potential": round(_clamp(float(source_step.get("preservation_potential", 0.0))), 6),
                }
            )
            previous_fill = fill
            history_surface_counts[surface] = history_surface_counts.get(surface, 0) + 1
            history_tract_counts[systems_tract] = history_tract_counts.get(systems_tract, 0) + 1
            history_trajectory_counts[trajectory] = history_trajectory_counts.get(trajectory, 0) + 1
            history_ratio_sum += accommodation_ratio
            history_flooding_sum += flooding_index

        dominant_tract = max(history_tract_counts.items(), key=lambda item: item[1])[0] if history_tract_counts else "aggradational_systems_tract"
        dominant_trajectory = (
            max(history_trajectory_counts.items(), key=lambda item: item[1])[0] if history_trajectory_counts else "aggradational"
        )
        event_count = sum(count for surface, count in history_surface_counts.items() if surface != "none")
        sequence_boundary_count += history_surface_counts.get("sequence_boundary", 0)
        transgressive_surface_count += history_surface_counts.get("transgressive_surface", 0)
        maximum_flooding_surface_count += history_surface_counts.get("maximum_flooding_surface", 0)
        regressive_surface_count += history_surface_counts.get("regressive_surface", 0)
        total_events += event_count
        total_steps += len(steps)
        accommodation_ratio_sum += history_ratio_sum
        flooding_index_sum += history_flooding_sum
        for systems_tract, count in history_tract_counts.items():
            systems_tract_counts[systems_tract] = systems_tract_counts.get(systems_tract, 0) + count
        for trajectory, count in history_trajectory_counts.items():
            trajectory_counts[trajectory] = trajectory_counts.get(trajectory, 0) + count

        column["dominant_systems_tract"] = dominant_tract
        column["dominant_shoreline_trajectory"] = dominant_trajectory
        column["sequence_boundary_count"] = history_surface_counts.get("sequence_boundary", 0)
        column["maximum_flooding_surface_count"] = history_surface_counts.get("maximum_flooding_surface", 0)
        column["stratigraphic_sequence_event_count"] = event_count
        column["mean_accommodation_to_deposition_ratio"] = round(history_ratio_sum / len(steps), 6) if steps else 0.0

        sequence_histories.append(
            {
                "id": int(column.get("id", len(sequence_histories))),
                "stratigraphic_column_id": int(column.get("id", len(sequence_histories))),
                "basin_id": basin_id,
                "time_step_count": len(steps),
                "sequence_event_count": event_count,
                "dominant_systems_tract": dominant_tract,
                "dominant_shoreline_trajectory": dominant_trajectory,
                "sequence_boundary_count": history_surface_counts.get("sequence_boundary", 0),
                "transgressive_surface_count": history_surface_counts.get("transgressive_surface", 0),
                "maximum_flooding_surface_count": history_surface_counts.get("maximum_flooding_surface", 0),
                "regressive_surface_count": history_surface_counts.get("regressive_surface", 0),
                "mean_accommodation_to_deposition_ratio": round(history_ratio_sum / len(steps), 6) if steps else 0.0,
                "mean_flooding_index": round(history_flooding_sum / len(steps), 6) if steps else 0.0,
                "systems_tract_counts": dict(sorted(history_tract_counts.items())),
                "shoreline_trajectory_counts": dict(sorted(history_trajectory_counts.items())),
                "steps": steps,
            }
        )

    summary = world.setdefault("summary", {})
    summary["sequence_stratigraphy_history_count"] = len(sequence_histories)
    summary["sequence_stratigraphy_step_count"] = total_steps
    summary["sequence_stratigraphy_event_count"] = total_events
    summary["sequence_boundary_count"] = sequence_boundary_count
    summary["transgressive_surface_count"] = transgressive_surface_count
    summary["maximum_flooding_surface_count"] = maximum_flooding_surface_count
    summary["regressive_surface_count"] = regressive_surface_count
    summary["mean_sequence_accommodation_to_deposition_ratio"] = round(accommodation_ratio_sum / total_steps, 6) if total_steps else 0.0
    summary["mean_sequence_flooding_index"] = round(flooding_index_sum / total_steps, 6) if total_steps else 0.0
    summary["systems_tract_counts"] = dict(sorted(systems_tract_counts.items()))
    summary["shoreline_trajectory_counts"] = dict(sorted(trajectory_counts.items()))
    world["sequence_stratigraphy_histories"] = sequence_histories
    return world
