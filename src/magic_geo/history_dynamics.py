from __future__ import annotations

import math
from typing import Any


POPULATION_HISTORY_MODEL = "causal_era_snapshot_logistic_migration_conflict_population_history_v1"


def _population_history_model() -> dict[str, Any]:
    return {
        "model_type": POPULATION_HISTORY_MODEL,
        "deterministic": True,
        "era_order": "descending_start_year_bp_v1",
        "initial_population_model": "first_era_territorial_snapshot_or_22_percent_base_v1",
        "growth_model": "bounded_exponential_rate_with_pressure_hazard_instability_drag_v1",
        "carrying_capacity_model": "overshoot_retains_32_percent_excess_v1",
        "snapshot_model": "era_region_territorial_population_override_v1",
        "migration_model": "snapshot_population_times_balance_times_0_035_per_millennium_v1",
        "conflict_loss_model": "half_region_casualties_capped_at_35_percent_snapshot_population_v1",
        "model_limitation": "aggregate_era_projection_without_age_structure_birth_death_cohorts_disease_or_endogenous_migration_feedback",
    }


def _set_population_history_model(world: dict[str, Any]) -> None:
    world["population_history_model"] = _population_history_model()
    world.setdefault("summary", {})["population_history_model"] = POPULATION_HISTORY_MODEL


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _era_sort_key(era: dict[str, Any]) -> float:
    return -float(era.get("start_year_bp", 0.0))


def _snapshot_population_by_era(world: dict[str, Any]) -> dict[int, dict[int, float]]:
    by_era: dict[int, dict[int, float]] = {}
    for snapshot in world.get("territorial_snapshots", []):
        era_id = int(snapshot.get("era_id", -1))
        if era_id < 0:
            continue
        region_populations = by_era.setdefault(era_id, {})
        for region in snapshot.get("regions", []):
            region_id = int(region.get("region_id", -1))
            if region_id >= 0:
                region_populations[region_id] = float(region.get("estimated_population", 0.0))
    return by_era


def _conflict_losses_by_era_region(world: dict[str, Any]) -> dict[tuple[int, int], float]:
    losses: dict[tuple[int, int], float] = {}
    for conflict in world.get("conflicts", []):
        era_id = int(conflict.get("era_id", -1))
        region_a = int(conflict.get("region_a", -1))
        region_b = int(conflict.get("region_b", -1))
        casualties = max(0.0, float(conflict.get("estimated_casualties", 0.0)))
        if era_id < 0 or casualties <= 0.0:
            continue
        split = casualties * 0.5
        if region_a >= 0:
            losses[(era_id, region_a)] = losses.get((era_id, region_a), 0.0) + split
        if region_b >= 0:
            losses[(era_id, region_b)] = losses.get((era_id, region_b), 0.0) + split
    return losses


def _region_snapshot_population(
    snapshot_by_era: dict[int, dict[int, float]],
    era_id: int,
    region_id: int,
    fallback: float,
) -> float:
    value = snapshot_by_era.get(era_id, {}).get(region_id)
    if value is None:
        return fallback
    return max(0.0, value)


def _growth_multiplier(
    growth_rate: float,
    duration_years: float,
    instability: float,
    hazard_mortality: float,
    pressure: float,
) -> float:
    pressure_drag = max(0.0, pressure - 0.85) * 0.00018
    hazard_drag = hazard_mortality * 0.00010
    instability_drag = instability * 0.00014
    effective_rate = _clamp(growth_rate - pressure_drag - hazard_drag - instability_drag, -0.006, 0.008)
    exponent = _clamp(effective_rate * duration_years, -4.0, 4.0)
    return math.exp(exponent)


def _logistic_projection(previous: float, carrying_capacity: float, multiplier: float) -> float:
    if carrying_capacity <= 0.0:
        return max(0.0, previous * multiplier)
    grown = max(0.0, previous * multiplier)
    pressure_ratio = grown / carrying_capacity
    if pressure_ratio <= 1.0:
        return grown
    overshoot = carrying_capacity + (grown - carrying_capacity) * 0.32
    return min(grown, overshoot)


def enrich_world_with_population_history(world: dict[str, Any]) -> dict[str, Any]:
    populations = world.get("population_regions", [])
    eras = sorted(world.get("historical_eras", []), key=_era_sort_key)
    if not isinstance(populations, list) or not isinstance(eras, list):
        return world
    if not populations:
        world["population_histories"] = []
        summary = world.setdefault("summary", {})
        summary["population_history_count"] = 0
        summary["population_history_step_count"] = 0
        summary["historical_final_population"] = 0.0
        summary["historical_peak_population_pressure"] = 0.0
        summary["max_population_decline_fraction"] = 0.0
        _set_population_history_model(world)
        return world
    if not eras:
        return world

    snapshot_by_era = _snapshot_population_by_era(world)
    conflict_losses = _conflict_losses_by_era_region(world)
    histories: list[dict[str, Any]] = []
    total_steps = 0
    final_sum = 0.0
    peak_pressure = 0.0
    max_decline_fraction = 0.0

    for population in populations:
        region_id = int(population.get("region_id", -1))
        population_id = int(population.get("id", len(histories)))
        carrying_capacity = max(1.0, float(population.get("carrying_capacity", 1.0)))
        base_population = max(0.0, float(population.get("estimated_population", 0.0)))
        growth_rate = float(population.get("growth_rate_per_year", 0.0))
        migration_balance = float(population.get("migration_balance", 0.0))
        hazard_mortality = _clamp(float(population.get("hazard_mortality_index", 0.0)), 0.0, 1.0)
        pressure = _clamp(float(population.get("population_pressure", 0.0)), 0.0, 2.5)

        first_era_id = int(eras[0].get("id", -1))
        previous_population = _region_snapshot_population(
            snapshot_by_era,
            first_era_id,
            region_id,
            max(1.0, base_population * 0.22),
        )
        steps: list[dict[str, Any]] = []
        peak_population = previous_population

        for index, era in enumerate(eras):
            era_id = int(era.get("id", index))
            start_year_bp = float(era.get("start_year_bp", 0.0))
            end_year_bp = float(era.get("end_year_bp", start_year_bp))
            duration_years = max(1.0, abs(start_year_bp - end_year_bp))
            instability = _clamp(float(era.get("mean_instability", 0.0)), 0.0, 1.0)

            start_population = previous_population
            projected_population = _logistic_projection(
                start_population,
                carrying_capacity,
                _growth_multiplier(growth_rate, duration_years, instability, hazard_mortality, pressure),
            )
            snapshot_population = _region_snapshot_population(snapshot_by_era, era_id, region_id, projected_population)
            migration_delta = snapshot_population * migration_balance * 0.035 * (duration_years / 1000.0)
            conflict_loss = min(
                max(0.0, conflict_losses.get((era_id, region_id), 0.0)),
                snapshot_population * 0.35,
            )
            end_population = max(0.0, snapshot_population + migration_delta - conflict_loss)
            population_change = end_population - start_population
            pressure_index = _clamp(end_population / carrying_capacity, 0.0, 2.5)
            carrying_capacity_used_fraction = _clamp(end_population / carrying_capacity, 0.0, 2.5)
            decline_fraction = max(0.0, -population_change / max(1.0, start_population))

            steps.append(
                {
                    "era_id": era_id,
                    "dominant_process": str(era.get("dominant_process", "unknown")),
                    "start_year_bp": start_year_bp,
                    "end_year_bp": end_year_bp,
                    "duration_years": duration_years,
                    "start_population": round(start_population, 6),
                    "end_population": round(end_population, 6),
                    "population_change": round(population_change, 6),
                    "growth_rate_per_year": round(growth_rate, 8),
                    "migration_delta": round(migration_delta, 6),
                    "conflict_loss": round(conflict_loss, 6),
                    "carrying_capacity": round(carrying_capacity, 6),
                    "carrying_capacity_used_fraction": round(carrying_capacity_used_fraction, 6),
                    "pressure_index": round(pressure_index, 6),
                    "instability_index": round(instability, 6),
                    "hazard_mortality_index": round(hazard_mortality, 6),
                }
            )

            peak_population = max(peak_population, end_population)
            peak_pressure = max(peak_pressure, pressure_index)
            max_decline_fraction = max(max_decline_fraction, decline_fraction)
            previous_population = end_population

        final_population = steps[-1]["end_population"] if steps else base_population
        final_sum += float(final_population)
        total_steps += len(steps)
        histories.append(
            {
                "id": population_id,
                "population_region_id": population_id,
                "region_id": region_id,
                "culture_region_id": int(population.get("culture_region_id", -1)),
                "language_region_id": int(population.get("language_region_id", -1)),
                "time_step_count": len(steps),
                "initial_population": steps[0]["start_population"] if steps else round(base_population, 6),
                "final_population": round(float(final_population), 6),
                "peak_population": round(peak_population, 6),
                "carrying_capacity": round(carrying_capacity, 6),
                "peak_pressure_index": round(
                    max((float(step["pressure_index"]) for step in steps), default=0.0),
                    6,
                ),
                "steps": steps,
            }
        )

    world["population_histories"] = histories
    summary = world.setdefault("summary", {})
    summary["population_history_count"] = len(histories)
    summary["population_history_step_count"] = total_steps
    summary["historical_final_population"] = round(final_sum, 6)
    summary["historical_peak_population_pressure"] = round(peak_pressure, 6)
    summary["max_population_decline_fraction"] = round(max_decline_fraction, 6)
    _set_population_history_model(world)
    return world
