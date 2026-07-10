from __future__ import annotations

import math
from typing import Any


POPULATION_HISTORY_MODEL = "causal_era_snapshot_logistic_migration_conflict_population_history_v1"
ECONOMY_HISTORY_MODEL = "causal_population_trade_conflict_treasury_economy_history_v1"


def _population_model() -> dict[str, Any]:
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


def _economy_model() -> dict[str, Any]:
    return {
        "model_type": ECONOMY_HISTORY_MODEL,
        "deterministic": True,
        "trade_model": "incident_friction_discounted_trade_volume_v1",
        "conflict_model": "era_region_force_casualty_logistics_disruption_aggregate_v1",
        "output_model": "agriculture_resource_trade_and_urban_services_sum_v1",
        "revenue_model": "stability_urbanization_tax_and_interregional_trade_v1",
        "cost_model": "administration_army_maintenance_and_conflict_war_cost_v1",
        "treasury_model": "nonnegative_balance_with_explicit_insolvency_adjustment_v1",
        "army_model": "population_pressure_stability_resource_capacity_v1",
        "diagnostic_model": "prosperity_food_trade_dependency_and_military_burden_v1",
        "model_limitation": "aggregate_index_economy_without_prices_inventory_production_functions_agent_equilibrium_or_empirical_calibration",
    }


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _snapshot_population_by_era(payload: dict[str, Any]) -> dict[int, dict[int, float]]:
    by_era: dict[int, dict[int, float]] = {}
    for snapshot in payload.get("territorial_snapshots", []):
        era_id = int(snapshot.get("era_id", -1))
        if era_id < 0:
            continue
        region_populations = by_era.setdefault(era_id, {})
        for region in snapshot.get("regions", []):
            region_id = int(region.get("region_id", -1))
            if region_id >= 0:
                region_populations[region_id] = float(region.get("estimated_population", 0.0))
    return by_era


def _conflict_losses(payload: dict[str, Any]) -> dict[tuple[int, int], float]:
    losses: dict[tuple[int, int], float] = {}
    for conflict in payload.get("conflicts", []):
        era_id = int(conflict.get("era_id", -1))
        region_a = int(conflict.get("region_a", -1))
        region_b = int(conflict.get("region_b", -1))
        casualties = max(0.0, float(conflict.get("estimated_casualties", 0.0)))
        if era_id < 0 or casualties <= 0.0:
            continue
        for region_id in (region_a, region_b):
            if region_id >= 0:
                losses[(era_id, region_id)] = losses.get((era_id, region_id), 0.0) + casualties * 0.5
    return losses


def _snapshot_population(
    snapshots: dict[int, dict[int, float]],
    era_id: int,
    region_id: int,
    fallback: float,
) -> float:
    value = snapshots.get(era_id, {}).get(region_id)
    return fallback if value is None else max(0.0, value)


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
    return math.exp(_clamp(effective_rate * duration_years, -4.0, 4.0))


def _logistic_projection(previous: float, carrying_capacity: float, multiplier: float) -> float:
    if carrying_capacity <= 0.0:
        return max(0.0, previous * multiplier)
    grown = max(0.0, previous * multiplier)
    if grown / carrying_capacity <= 1.0:
        return grown
    return min(grown, carrying_capacity + (grown - carrying_capacity) * 0.32)


def _expected_population_histories(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    populations = payload["population_regions"]
    eras = sorted(payload["historical_eras"], key=lambda era: -float(era.get("start_year_bp", 0.0)))
    if not populations:
        return [], {
            "population_history_count": 0,
            "population_history_step_count": 0,
            "historical_final_population": 0.0,
            "historical_peak_population_pressure": 0.0,
            "max_population_decline_fraction": 0.0,
        }
    snapshots = _snapshot_population_by_era(payload)
    losses = _conflict_losses(payload)
    histories: list[dict[str, Any]] = []
    total_steps = 0
    final_sum = 0.0
    peak_pressure = 0.0
    max_decline = 0.0
    for population in populations:
        region_id = int(population.get("region_id", -1))
        population_id = int(population.get("id", len(histories)))
        carrying_capacity = max(1.0, float(population.get("carrying_capacity", 1.0)))
        base_population = max(0.0, float(population.get("estimated_population", 0.0)))
        growth_rate = float(population.get("growth_rate_per_year", 0.0))
        migration_balance = float(population.get("migration_balance", 0.0))
        hazard = _clamp(float(population.get("hazard_mortality_index", 0.0)), 0.0, 1.0)
        pressure = _clamp(float(population.get("population_pressure", 0.0)), 0.0, 2.5)
        first_era_id = int(eras[0].get("id", -1))
        previous = _snapshot_population(snapshots, first_era_id, region_id, max(1.0, base_population * 0.22))
        steps: list[dict[str, Any]] = []
        peak_population = previous
        for index, era in enumerate(eras):
            era_id = int(era.get("id", index))
            start_year = float(era.get("start_year_bp", 0.0))
            end_year = float(era.get("end_year_bp", start_year))
            duration = max(1.0, abs(start_year - end_year))
            instability = _clamp(float(era.get("mean_instability", 0.0)), 0.0, 1.0)
            projected = _logistic_projection(
                previous,
                carrying_capacity,
                _growth_multiplier(growth_rate, duration, instability, hazard, pressure),
            )
            snapshot_value = _snapshot_population(snapshots, era_id, region_id, projected)
            migration_delta = snapshot_value * migration_balance * 0.035 * (duration / 1000.0)
            conflict_loss = min(max(0.0, losses.get((era_id, region_id), 0.0)), snapshot_value * 0.35)
            end_population = max(0.0, snapshot_value + migration_delta - conflict_loss)
            change = end_population - previous
            pressure_index = _clamp(end_population / carrying_capacity, 0.0, 2.5)
            decline = max(0.0, -change / max(1.0, previous))
            steps.append(
                {
                    "era_id": era_id,
                    "dominant_process": str(era.get("dominant_process", "unknown")),
                    "start_year_bp": start_year,
                    "end_year_bp": end_year,
                    "duration_years": duration,
                    "start_population": round(previous, 6),
                    "end_population": round(end_population, 6),
                    "population_change": round(change, 6),
                    "growth_rate_per_year": round(growth_rate, 8),
                    "migration_delta": round(migration_delta, 6),
                    "conflict_loss": round(conflict_loss, 6),
                    "carrying_capacity": round(carrying_capacity, 6),
                    "carrying_capacity_used_fraction": round(pressure_index, 6),
                    "pressure_index": round(pressure_index, 6),
                    "instability_index": round(instability, 6),
                    "hazard_mortality_index": round(hazard, 6),
                }
            )
            peak_population = max(peak_population, end_population)
            peak_pressure = max(peak_pressure, pressure_index)
            max_decline = max(max_decline, decline)
            previous = end_population
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
                    max((float(step["pressure_index"]) for step in steps), default=0.0), 6
                ),
                "steps": steps,
            }
        )
    return histories, {
        "population_history_count": len(histories),
        "population_history_step_count": total_steps,
        "historical_final_population": round(final_sum, 6),
        "historical_peak_population_pressure": round(peak_pressure, 6),
        "max_population_decline_fraction": round(max_decline, 6),
    }


def _resource_value(resource: str) -> float:
    return {
        "none": 0.08,
        "salt": 0.18,
        "alluvial_gold": 0.34,
        "placer_gold": 0.34,
        "iron": 0.28,
        "copper": 0.32,
        "precious_metals": 0.40,
        "gemstones": 0.42,
        "diamonds": 0.46,
        "coal": 0.30,
        "sedimentary_fuels": 0.38,
        "petroleum": 0.42,
        "geothermal": 0.26,
        "obsidian": 0.20,
        "sulfur": 0.18,
        "fertile_soils": 0.24,
        "timber": 0.20,
    }.get(resource, 0.16)


def _trade_by_region(payload: dict[str, Any]) -> dict[int, dict[str, float]]:
    trade: dict[int, dict[str, float]] = {}
    for flow in payload.get("trade_flows", []):
        volume = max(0.0, float(flow.get("volume_index", 0.0)))
        friction = _clamp(float(flow.get("friction", 0.0)), 0.0, 4.0)
        effective_volume = volume / (1.0 + friction * 0.35)
        for key in ("region_from", "region_to"):
            region_id = int(flow.get(key, -1))
            if region_id < 0:
                continue
            record = trade.setdefault(
                region_id,
                {"volume": 0.0, "interregional_volume": 0.0, "friction_sum": 0.0, "count": 0.0},
            )
            record["volume"] += effective_volume
            if bool(flow.get("interregional", False)):
                record["interregional_volume"] += effective_volume
            record["friction_sum"] += friction
            record["count"] += 1.0
    return trade


def _conflicts_by_era_region(payload: dict[str, Any]) -> dict[tuple[int, int], dict[str, float]]:
    records: dict[tuple[int, int], dict[str, float]] = {}
    for conflict in payload.get("conflicts", []):
        era_id = int(conflict.get("era_id", -1))
        if era_id < 0:
            continue
        forces = (
            (int(conflict.get("region_a", -1)), max(0.0, float(conflict.get("region_a_force_estimate", 0.0)))),
            (int(conflict.get("region_b", -1)), max(0.0, float(conflict.get("region_b_force_estimate", 0.0)))),
        )
        intensity = _clamp(float(conflict.get("intensity", 0.0)), 0.0, 1.0)
        logistics = _clamp(float(conflict.get("logistics_strain_index", 0.0)), 0.0, 1.0)
        disruption = _clamp(float(conflict.get("economic_disruption_index", 0.0)), 0.0, 1.0)
        casualties = max(0.0, float(conflict.get("estimated_casualties", 0.0)))
        for region_id, force in forces:
            if region_id < 0:
                continue
            record = records.setdefault(
                (era_id, region_id),
                {"force": 0.0, "casualties": 0.0, "intensity": 0.0, "logistics": 0.0, "disruption": 0.0, "count": 0.0},
            )
            record["force"] += force
            record["casualties"] += casualties * 0.5
            record["intensity"] += intensity
            record["logistics"] += logistics
            record["disruption"] += disruption
            record["count"] += 1.0
    return records


def _snapshot_regions(payload: dict[str, Any]) -> dict[tuple[int, int], dict[str, Any]]:
    records: dict[tuple[int, int], dict[str, Any]] = {}
    for snapshot in payload.get("territorial_snapshots", []):
        era_id = int(snapshot.get("era_id", -1))
        for region in snapshot.get("regions", []):
            region_id = int(region.get("region_id", -1))
            if era_id >= 0 and region_id >= 0:
                records[(era_id, region_id)] = region
    return records


def _expected_economy_histories(
    payload: dict[str, Any],
    population_histories: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    eras = payload["historical_eras"]
    if not population_histories:
        return [], {
            "economy_history_count": 0,
            "economy_history_step_count": 0,
            "historical_final_gross_output_index": 0.0,
            "historical_final_treasury_index": 0.0,
            "historical_total_tax_revenue_index": 0.0,
            "historical_total_trade_revenue_index": 0.0,
            "historical_total_war_cost_index": 0.0,
            "historical_peak_army_capacity_population": 0.0,
            "mean_historical_prosperity_index": 0.0,
            "mean_historical_trade_dependency_index": 0.0,
            "mean_historical_military_burden_index": 0.0,
            "high_military_burden_economy_step_count": 0,
        }
    population_by_region = {
        int(region.get("region_id", -1)): region for region in payload.get("population_regions", [])
    }
    political_by_region = {
        int(region.get("id", -1)): region for region in payload.get("political_regions", [])
    }
    trade_by_region = _trade_by_region(payload)
    conflicts = _conflicts_by_era_region(payload)
    snapshots = _snapshot_regions(payload)
    histories: list[dict[str, Any]] = []
    step_count = 0
    final_gdp = 0.0
    final_treasury = 0.0
    total_tax = 0.0
    total_trade_revenue = 0.0
    total_war_cost = 0.0
    max_army = 0.0
    prosperity_sum = 0.0
    dependency_sum = 0.0
    burden_sum = 0.0
    high_burden = 0
    for history in population_histories:
        region_id = int(history.get("region_id", -1))
        if region_id < 0:
            continue
        population_region = population_by_region.get(region_id, {})
        political_region = political_by_region.get(region_id, {})
        trade = trade_by_region.get(
            region_id,
            {"volume": 0.0, "interregional_volume": 0.0, "friction_sum": 0.0, "count": 0.0},
        )
        agriculture = _clamp(float(population_region.get("agricultural_capacity_index", 0.0)), 0.0, 1.0)
        water = _clamp(float(population_region.get("water_security_index", 0.0)), 0.0, 1.0)
        urbanization = _clamp(float(population_region.get("urbanization_fraction", 0.0)), 0.0, 1.0)
        pressure = _clamp(float(population_region.get("population_pressure", 0.0)), 0.0, 2.5)
        resource = _resource_value(str(political_region.get("dominant_resource", "none")))
        route_count = max(0.0, float(political_region.get("route_count", 0.0)))
        barrier = _clamp(float(political_region.get("barrier_pressure", 0.0)), 0.0, 1.0)
        settlements = max(
            0.0,
            float(population_region.get("settlement_count", political_region.get("settlement_count", 0.0))),
        )
        average_friction = trade["friction_sum"] / trade["count"] if trade["count"] > 0 else 0.0
        interregional = trade["interregional_volume"] / trade["volume"] if trade["volume"] > 0.0 else 0.0
        steps: list[dict[str, Any]] = []
        previous_treasury = max(0.0, float(history.get("initial_population", 0.0)) / 1_000_000.0 * 0.08)
        peak_gdp = 0.0
        peak_treasury = previous_treasury
        for index, population_step in enumerate(history.get("steps", [])):
            era_id = int(population_step.get("era_id", index))
            end_population = max(0.0, float(population_step.get("end_population", 0.0)))
            population_millions = end_population / 1_000_000.0
            duration = max(1.0, float(population_step.get("duration_years", 1.0)))
            era = eras[index] if index < len(eras) else {}
            connectivity = _clamp(float(era.get("mean_connectivity", 0.0)), 0.0, 1.0)
            instability = _clamp(
                float(population_step.get("instability_index", era.get("mean_instability", 0.0))),
                0.0,
                1.0,
            )
            stability = _clamp(
                float(snapshots.get((era_id, region_id), {}).get("stability_index", 1.0 - instability)),
                0.0,
                1.0,
            )
            fragmentation = _clamp(1.0 - stability, 0.0, 1.0)
            conflict = conflicts.get(
                (era_id, region_id),
                {"force": 0.0, "casualties": 0.0, "intensity": 0.0, "logistics": 0.0, "disruption": 0.0, "count": 0.0},
            )
            conflict_count = conflict["count"]
            conflict_logistics = conflict["logistics"] / conflict_count if conflict_count > 0.0 else 0.0
            conflict_disruption = conflict["disruption"] / conflict_count if conflict_count > 0.0 else 0.0
            agricultural_output = population_millions * agriculture * (0.45 + water * 0.85) * (
                1.0 - min(0.35, pressure * 0.08)
            )
            resource_output = population_millions * resource * (0.45 + urbanization * 0.45 + settlements * 0.025)
            trade_output = trade["volume"] * (0.35 + connectivity * 0.35 + interregional * 0.20) + route_count * 1.75
            urban_services = population_millions * urbanization * (0.35 + settlements * 0.035 + stability * 0.30)
            gross_output = max(0.0, agricultural_output + resource_output + trade_output + urban_services)
            tax_revenue = gross_output * (0.055 + stability * 0.055 + urbanization * 0.025)
            trade_revenue = trade_output * (0.035 + interregional * 0.035) / (1.0 + average_friction * 0.15)
            army_capacity = end_population * (0.009 + pressure * 0.004 + stability * 0.003 + resource * 0.002)
            mobilized = max(0.0, conflict["force"])
            administration = gross_output * (0.035 + barrier * 0.025 + fragmentation * 0.035)
            army_cost = army_capacity / 100_000.0 * (0.045 + pressure * 0.018)
            war_cost = mobilized / 100_000.0 * (0.11 + conflict_logistics * 0.10 + conflict_disruption * 0.14)
            raw_treasury = previous_treasury + tax_revenue + trade_revenue - administration - army_cost - war_cost
            insolvency = max(0.0, -raw_treasury)
            treasury_end = max(0.0, raw_treasury)
            balance_residual = (
                previous_treasury
                + tax_revenue
                + trade_revenue
                + insolvency
                - administration
                - army_cost
                - war_cost
                - treasury_end
            )
            prosperity = _clamp((gross_output / max(1.0, population_millions)) / 1.6, 0.0, 1.0)
            food_security = _clamp(agricultural_output / max(1.0, population_millions * 0.42), 0.0, 1.0)
            trade_dependency = _clamp(trade_output / max(1.0, gross_output), 0.0, 1.0)
            military_burden = _clamp(
                (army_cost + war_cost) / max(1.0, tax_revenue + trade_revenue), 0.0, 1.0
            )
            steps.append(
                {
                    "era_id": era_id,
                    "dominant_process": str(
                        population_step.get("dominant_process", era.get("dominant_process", "unknown"))
                    ),
                    "start_year_bp": float(
                        population_step.get("start_year_bp", era.get("start_year_bp", 0.0))
                    ),
                    "end_year_bp": float(population_step.get("end_year_bp", era.get("end_year_bp", 0.0))),
                    "duration_years": round(duration, 6),
                    "population": round(end_population, 6),
                    "gross_output_index": round(gross_output, 6),
                    "agricultural_output_index": round(agricultural_output, 6),
                    "resource_output_index": round(resource_output, 6),
                    "trade_output_index": round(trade_output, 6),
                    "urban_services_index": round(urban_services, 6),
                    "treasury_start_index": round(previous_treasury, 6),
                    "tax_revenue_index": round(tax_revenue, 6),
                    "trade_revenue_index": round(trade_revenue, 6),
                    "administration_cost_index": round(administration, 6),
                    "army_maintenance_cost_index": round(army_cost, 6),
                    "war_cost_index": round(war_cost, 6),
                    "insolvency_adjustment_index": round(insolvency, 6),
                    "treasury_end_index": round(treasury_end, 6),
                    "balance_residual_index": round(balance_residual, 6),
                    "army_capacity_population": round(army_capacity, 6),
                    "mobilized_force_population": round(mobilized, 6),
                    "prosperity_index": round(prosperity, 6),
                    "food_security_index": round(food_security, 6),
                    "trade_dependency_index": round(trade_dependency, 6),
                    "military_burden_index": round(military_burden, 6),
                    "stability_index": round(stability, 6),
                }
            )
            step_count += 1
            total_tax += tax_revenue
            total_trade_revenue += trade_revenue
            total_war_cost += war_cost
            max_army = max(max_army, army_capacity)
            prosperity_sum += prosperity
            dependency_sum += trade_dependency
            burden_sum += military_burden
            high_burden += int(military_burden >= 0.65)
            peak_gdp = max(peak_gdp, gross_output)
            peak_treasury = max(peak_treasury, treasury_end)
            previous_treasury = treasury_end
        if not steps:
            continue
        final_gdp += float(steps[-1]["gross_output_index"])
        final_treasury += float(steps[-1]["treasury_end_index"])
        histories.append(
            {
                "id": len(histories),
                "region_id": region_id,
                "population_region_id": int(history.get("population_region_id", -1)),
                "culture_region_id": int(history.get("culture_region_id", -1)),
                "language_region_id": int(history.get("language_region_id", -1)),
                "dominant_resource": str(political_region.get("dominant_resource", "none")),
                "time_step_count": len(steps),
                "final_gross_output_index": round(float(steps[-1]["gross_output_index"]), 6),
                "final_treasury_index": round(float(steps[-1]["treasury_end_index"]), 6),
                "peak_gross_output_index": round(peak_gdp, 6),
                "peak_treasury_index": round(peak_treasury, 6),
                "max_army_capacity_population": round(
                    max(float(step["army_capacity_population"]) for step in steps), 6
                ),
                "steps": steps,
            }
        )
    return histories, {
        "economy_history_count": len(histories),
        "economy_history_step_count": step_count,
        "historical_final_gross_output_index": round(final_gdp, 6),
        "historical_final_treasury_index": round(final_treasury, 6),
        "historical_total_tax_revenue_index": round(total_tax, 6),
        "historical_total_trade_revenue_index": round(total_trade_revenue, 6),
        "historical_total_war_cost_index": round(total_war_cost, 6),
        "historical_peak_army_capacity_population": round(max_army, 6),
        "mean_historical_prosperity_index": round(prosperity_sum / step_count, 6) if step_count else 0.0,
        "mean_historical_trade_dependency_index": round(dependency_sum / step_count, 6) if step_count else 0.0,
        "mean_historical_military_burden_index": round(burden_sum / step_count, 6) if step_count else 0.0,
        "high_military_burden_economy_step_count": high_burden,
    }


def _contains_expected(actual: Any, expected: Any) -> bool:
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(
            key in actual and _contains_expected(actual[key], value) for key, value in expected.items()
        )
    if isinstance(expected, list):
        return isinstance(actual, list) and len(actual) == len(expected) and all(
            _contains_expected(actual_item, expected_item)
            for actual_item, expected_item in zip(actual, expected, strict=True)
        )
    return actual == expected


def validate_history_economy_replay(payload: dict[str, Any]) -> list[str]:
    try:
        summary = payload.get("summary", {})
        required_lists = (
            "population_regions",
            "historical_eras",
            "territorial_snapshots",
            "conflicts",
            "trade_flows",
            "political_regions",
            "population_histories",
            "economy_histories",
        )
        valid = isinstance(summary, dict) and all(isinstance(payload.get(name), list) for name in required_lists)
        valid = valid and payload.get("population_history_model") == _population_model()
        valid = valid and payload.get("economy_history_model") == _economy_model()
        valid = valid and summary.get("population_history_model") == POPULATION_HISTORY_MODEL
        valid = valid and summary.get("economy_history_model") == ECONOMY_HISTORY_MODEL
        population_histories, population_summary = _expected_population_histories(payload)
        valid = valid and _contains_expected(payload.get("population_histories"), population_histories)
        valid = valid and all(summary.get(key) == value for key, value in population_summary.items())
        economy_histories, economy_summary = _expected_economy_histories(payload, population_histories)
        valid = valid and _contains_expected(payload.get("economy_histories"), economy_histories)
        valid = valid and all(summary.get(key) == value for key, value in economy_summary.items())
    except (IndexError, KeyError, TypeError, ValueError, ZeroDivisionError, OverflowError):
        valid = False
    return [] if valid else ["population or economy history model causal replay invalid"]
