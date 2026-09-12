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


def _validate_history_economy_legacy(payload: dict[str, Any]) -> list[str]:
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


# New availability dispatch and source guards. Historical bodies above are exact.
POPULATION_V2 = "causal_era_snapshot_logistic_migration_conflict_population_history_v2"
ECONOMY_V2 = "causal_population_trade_conflict_treasury_economy_history_v2"
POPULATION_RECORD_ESTIMATES = ("initial_population","final_population","peak_population","carrying_capacity","peak_pressure_index")
POPULATION_STEP_ESTIMATES = ("start_population","end_population","population_change","growth_rate_per_year","migration_delta","conflict_loss","carrying_capacity","carrying_capacity_used_fraction","pressure_index","instability_index","hazard_mortality_index")
POPULATION_SUMMARY_ESTIMATES = ("historical_final_population","historical_peak_population_pressure","max_population_decline_fraction")
ECONOMY_RECORD_ESTIMATES = ("final_gross_output_index","final_treasury_index","peak_gross_output_index","peak_treasury_index","max_army_capacity_population")
ECONOMY_STEP_ESTIMATES = ("population","gross_output_index","agricultural_output_index","resource_output_index","trade_output_index","urban_services_index","treasury_start_index","tax_revenue_index","trade_revenue_index","administration_cost_index","army_maintenance_cost_index","war_cost_index","insolvency_adjustment_index","treasury_end_index","balance_residual_index","army_capacity_population","mobilized_force_population","prosperity_index","food_security_index","trade_dependency_index","military_burden_index","stability_index")
ECONOMY_SUMMARY_ESTIMATES = ("historical_final_gross_output_index","historical_final_treasury_index","historical_total_tax_revenue_index","historical_total_trade_revenue_index","historical_total_war_cost_index","historical_peak_army_capacity_population","mean_historical_prosperity_index","mean_historical_trade_dependency_index","mean_historical_military_burden_index","high_military_burden_economy_step_count")


def _population_v2_model():
    return {**_population_model(), "model_type":POPULATION_V2,
        "source_native_social_availability_model":"native_settlement_source_complete_social_estimates_v1",
        "source_population_region_model":"causal_area_weighted_capacity_occupancy_population_regions_v2",
        "source_historical_event_model":"causal_region_culture_language_trade_site_timeline_v2",
        "source_conflict_model":"causal_border_pair_pressure_trade_conflict_selection_v2",
        "source_territorial_snapshot_model":"causal_era_scaled_spherical_region_territorial_snapshots_v2",
        "initial_population_model":"explicit_first_era_snapshot_without_minimum_population_or_missing_estimate_fallback_v2",
        "growth_model":"native_growth_rate_diagnostic_snapshot_controls_population_v2",
        "snapshot_model":"complete_actual_era_region_snapshot_or_null_never_projected_substitution_v2",
        "carrying_capacity_model":"native_capacity_without_floor_zero_over_zero_pressure_zero_positive_over_zero_unavailable_v2",
        "availability_policy":"per_field_typed_map_null_unavailable_complete_region_era_slots",
        "summary_policy":"complete_estimate_aggregates_or_null_without_partial_population_renormalization"}


def _economy_v2_model():
    return {**_economy_model(), "model_type":ECONOMY_V2,
        "source_native_social_availability_model":"native_settlement_source_complete_social_estimates_v1",
        "source_population_history_model":POPULATION_V2,
        "source_population_region_model":"causal_area_weighted_capacity_occupancy_population_regions_v2",
        "source_historical_event_model":"causal_region_culture_language_trade_site_timeline_v2",
        "source_conflict_model":"causal_border_pair_pressure_trade_conflict_selection_v2",
        "source_territorial_snapshot_model":"causal_era_scaled_spherical_region_territorial_snapshots_v2",
        "source_political_region_model":"causal_capital_barrier_partition_political_regions_v1",
        "source_route_network_model":"causal_endpoint_barrier_ranked_route_network_v1",
        "source_trade_flow_model":"causal_route_endpoint_complement_trade_flows_v1",
        "era_source_policy":"exact_era_id_no_positional_or_missing_source_fallback",
        "availability_policy":"per_field_typed_map_null_unavailable_keep_independent_trade_and_conflict_diagnostics",
        "summary_policy":"complete_estimate_aggregates_or_null_no_partial_record_means",
        "treasury_availability_policy":"actual_initial_population_and_sequential_balance_no_reset_for_unknown_history"}


def _exact(a, b):
    if type(a) is not type(b): return False
    if type(b) is dict: return a.keys()==b.keys() and all(_exact(a[k],v) for k,v in b.items())
    if type(b) is list: return len(a)==len(b) and all(_exact(x,y) for x,y in zip(a,b))
    return a==b


def _require(condition, message):
    if not condition: raise ValueError("history/economy availability: " + message)


def _finite(value):
    try: return type(value) in (int,float) and math.isfinite(value)
    except (OverflowError,ValueError): return False


def history_summary_fields(stage):
    if stage=="population":
        return (*POPULATION_SUMMARY_ESTIMATES,"population_history_count","population_history_step_count","population_history_model","population_history_summary_availability","population_history_available_record_count","population_history_available_step_count")
    return (*ECONOMY_SUMMARY_ESTIMATES,"economy_history_count","economy_history_step_count","economy_history_model","economy_history_summary_availability","economy_history_available_record_count","economy_history_available_step_count")


def history_economy_version(world, stage):
    _require(type(world) is dict and stage in ("population","economy"),"world and stage required")
    key=stage+"_history_model"; records=stage+"_histories"; summary=world.get("summary",{})
    _require(type(summary) is dict,"summary object required")
    old=_population_model() if stage=="population" else _economy_model()
    new=_population_v2_model() if stage=="population" else _economy_v2_model()
    own=None
    if key in world:
        own=1 if _exact(world[key],old) else 2 if _exact(world[key],new) else None
        _require(own is not None,"unknown or malformed own "+key)
        _require(_exact(summary.get(key),world[key]["model_type"]),"missing/mismatched own summary identity")
    from .native_social_availability import uses_native_social_availability
    native=uses_native_social_availability(world)
    if own is not None:
        _require((own==2)==native,"own history requires exact native family; explicit upgrade required")
    version=own or (2 if native else 1)
    if own is None and version==2:
        _require(records not in world and not any(k in summary for k in history_summary_fields(stage)),"undeclared existing histories/mirrors require explicit audited clearing")
    if version==1:
        _require(not any(k in summary for k in (stage+"_history_summary_availability",stage+"_history_available_record_count",stage+"_history_available_step_count")) and not any(type(r) is dict and ("estimate_availability" in r or any(type(st) is dict and "estimate_availability" in st for st in r.get("steps",[]))) for r in world.get(records,[])),"availability mirrors require successor own model")
    if stage == "economy" and "population_history_model" in world:
        expected_parent = _population_v2_model() if version == 2 else _population_model()
        _require(_exact(world["population_history_model"], expected_parent)
                 and _exact(summary.get("population_history_model"), expected_parent["model_type"]),
                 "economy history requires its exact population-history parent")
    return version


def require_history_economy_sources(world, *, economy=False):
    from .native_social_availability import require_native_social_availability
    from .civilization_geography_validation import validate_civilization_geography_replay
    from .territorial_geography_validation import validate_territorial_geography_replay
    from .historical_geography_validation import validate_historical_geography_replay
    envelope=require_native_social_availability(world)
    for audit in (validate_historical_geography_replay,validate_civilization_geography_replay,validate_territorial_geography_replay):
        errors=audit(world);_require(not errors,"native source "+(errors[0] if errors else ""))
    eras=world["historical_eras"];populations=world["population_regions"]
    _require(bool(eras) or not populations,"population regions require their actual era grid")
    snapshots={(s["era_id"],r["region_id"]):r for s in world["territorial_snapshots"] for r in s["regions"]}
    _require(len(snapshots)==len(eras)*len(populations) and set(snapshots)=={(e["id"],p["region_id"]) for e in eras for p in populations},"complete actual era-region snapshot grid required")
    for era in eras:
        for key in ("start_year_bp","end_year_bp"):_require(_finite(era.get(key)),"finite era clock required")
        _require(type(era.get("dominant_process")) is str,"era descriptor required")
    if economy:
        from .cli.validators.settlement import _validate_route_network
        from .cli.validators.political import _validate_political_regions,_validate_trade_flows
        by_id={c["id"]:c for c in world["cells"]}
        for audit in (_validate_route_network,_validate_political_regions,_validate_trade_flows):
            errors=audit(world,world["summary"],by_id);_require(not errors,"economic source "+(errors[0] if errors else ""))
        for region in world["political_regions"]:
            _require(type(region.get("dominant_resource")) is str,"explicit political resource descriptor required")
            for key in ("route_count","settlement_count"):_require(type(region.get(key)) is int and region[key]>=0,"typed political source count required")
            _require(_finite(region.get("barrier_pressure")),"finite political barrier pressure required")
        _require(type(world.get("trade_flows")) is list,"explicit trade-flow list required")
        for flow in world["trade_flows"]:
            for key in ("volume_index","friction"):_require(_finite(flow.get(key)),"finite nonboolean trade source required")
            _require(type(flow.get("interregional")) is bool,"typed trade classification required")
    return envelope


def _audit_estimate_maps(records, record_fields, step_fields):
    for record in records:
        _require(type(record) is dict,"history record object required")
        _require(type(record.get("steps")) is list,"explicit step collection required")
        for obj,fields in [(record,record_fields),*((s,step_fields) for s in record["steps"])]:
            _require(type(obj) is dict,"step object required")
            _require(type(obj.get("estimate_availability")) is dict and obj["estimate_availability"].keys()==set(fields),"exact estimate availability map required")
            for key in fields:
                flag=obj["estimate_availability"][key]
                _require(type(flag) is bool and key in obj and (_finite(obj[key]) if flag else obj[key] is None),"typed nullable estimate required: "+key)


def _derive(arguments, formula):
    """Independent nullable arithmetic; source flags have already been replayed."""
    if None in arguments:
        return None
    value = formula(*arguments)
    _require(value is None or _finite(value), "nonfinite independent estimate")
    return value


def _aggregate(values, mode="sum"):
    if None in values:
        return None
    if mode == "max":
        result = max(values, default=0.0)
    elif mode == "mean":
        result = sum(values, 0.0) / len(values) if values else 0.0
    elif mode == "high":
        return len([v for v in values if v >= .65])
    else:
        result = sum(values, 0.0)
    _require(_finite(result), "aggregate overflow")
    return result


def _pack_replay(estimates):
    return {**{key: None if value is None else round(value, 8 if key == "growth_rate_per_year" else 6)
               for key, value in estimates.items()},
            "estimate_availability": {key: value is not None for key, value in estimates.items()}}


def _expected_population_v2(payload, envelope):
    snapshots = _snapshot_regions(payload)
    eras = sorted(payload["historical_eras"], key=lambda e: -float(e["start_year_bp"]))
    losses = _conflict_losses(payload)
    expected, global_pressure, declines = [], [], []
    for native in payload["population_regions"]:
        region = native["region_id"]
        cap, rate = native["carrying_capacity"], native["growth_rate_per_year"]
        hazard = _derive([native["hazard_mortality_index"]], lambda h: min(1.0, max(0.0, h)))
        start_value = snapshots[(eras[0]["id"],region)]["estimated_population"]
        population_values = [start_value]
        steps = []
        for era in eras:
            era_id = era["id"]
            clock_start, clock_end = float(era["start_year_bp"]), float(era["end_year_bp"])
            duration = max(1.0, abs(clock_start-clock_end))
            snapshot = snapshots[(era_id,region)]["estimated_population"]
            migration = _derive([snapshot,native["migration_balance"]], lambda p,b:p*b*.035*(duration/1000.0))
            casualties = losses.get((era_id,region),0.0) if envelope["conflict_inference_available"] else None
            loss = _derive([snapshot,casualties], lambda p,c:min(max(0.0,c),p*.35))
            end_value = _derive([snapshot,migration,loss], lambda p,m,c:max(0.0,p+m-c))
            change = _derive([end_value,start_value], lambda e,s:e-s)
            utilization = _derive([end_value,cap],lambda p,c:min(2.5,max(0.0,p/c)) if c>0.0 else 0.0 if p==0.0 else None)
            instability = _derive([era["mean_instability"]],lambda x:min(1.0,max(0.0,x)))
            estimates = dict(zip(POPULATION_STEP_ESTIMATES,
                (start_value,end_value,change,rate,migration,loss,cap,utilization,utilization,instability,hazard),strict=True))
            steps.append({"era_id":era_id,"dominant_process":era["dominant_process"],
                "start_year_bp":clock_start,"end_year_bp":clock_end,"duration_years":duration,**_pack_replay(estimates)})
            population_values.append(end_value)
            global_pressure.append(utilization)
            declines.append(_derive([change,start_value],lambda delta,p:max(0.0,-delta/max(1.0,p))))
            start_value = end_value
        expected.append({"id":native["id"],"population_region_id":native["id"],"region_id":region,
            "culture_region_id":native["culture_region_id"],"language_region_id":native["language_region_id"],
            "time_step_count":len(steps),**_pack_replay(dict(zip(POPULATION_RECORD_ESTIMATES,
                (steps[0]["start_population"],steps[-1]["end_population"],_aggregate(population_values,"max"),cap,
                 _aggregate([s["pressure_index"] for s in steps],"max")),strict=True))),"steps":steps})
    summary = _pack_replay(dict(zip(POPULATION_SUMMARY_ESTIMATES,
        (_aggregate([r["final_population"] for r in expected]),_aggregate(global_pressure,"max"),_aggregate(declines,"max")),strict=True)))
    summary["population_history_summary_availability"] = summary.pop("estimate_availability")
    summary.update({"population_history_count":len(expected),"population_history_step_count":sum(len(r["steps"]) for r in expected),
        "population_history_model":POPULATION_V2,
        "population_history_available_record_count":sum(all(r["estimate_availability"].values()) for r in expected),
        "population_history_available_step_count":sum(all(s["estimate_availability"].values()) for r in expected for s in r["steps"])})
    return expected,summary


def _expected_economy_v2(payload, histories, envelope):
    native_by_region = {p["region_id"]:p for p in payload["population_regions"]}
    political_by_region = {p["id"]:p for p in payload["political_regions"]}
    era_by_id = {e["id"]:e for e in payload["historical_eras"]}
    trade_by_region, conflicts, snapshots = _trade_by_region(payload),_conflicts_by_era_region(payload),_snapshot_regions(payload)
    expected, complete_raw_steps = [], []
    for history in histories:
        region = history["region_id"]
        p, political = native_by_region[region],political_by_region[region]
        a = _derive([p["agricultural_capacity_index"]],lambda x:min(1.0,max(0.0,x)))
        w = _derive([p["water_security_index"]],lambda x:min(1.0,max(0.0,x)))
        u = _derive([p["urbanization_fraction"]],lambda x:min(1.0,max(0.0,x)))
        q = _derive([p["population_pressure"]],lambda x:min(2.5,max(0.0,x)))
        resource = _resource_value(political["dominant_resource"])
        barrier = min(1.0,max(0.0,political["barrier_pressure"]))
        settlement_count = max(0.0,float(p["settlement_count"]))
        route_count = max(0.0,float(political["route_count"]))
        trade = trade_by_region.get(region,{"volume":0.0,"interregional_volume":0.0,"friction_sum":0.0,"count":0.0})
        friction = trade["friction_sum"]/trade["count"] if trade["count"]>0.0 else 0.0
        interregional = trade["interregional_volume"]/trade["volume"] if trade["volume"]>0.0 else 0.0
        cash = _derive([history["initial_population"]],lambda p:max(0.0,p/1_000_000.0*.08))
        cash_series, raw_steps, steps = [cash],[],[]
        for population_step in history["steps"]:
            era_id = population_step["era_id"]
            population = _derive([population_step["end_population"]],lambda x:max(0.0,x))
            millions = _derive([population],lambda x:x/1_000_000.0)
            connectivity = _derive([era_by_id[era_id]["mean_connectivity"]],lambda x:min(1.0,max(0.0,x)))
            stability = _derive([snapshots[(era_id,region)]["stability_index"]],lambda x:min(1.0,max(0.0,x)))
            fragmentation = _derive([stability],lambda x:min(1.0,max(0.0,1.0-x)))
            conflict = conflicts.get((era_id,region),{"force":0.0,"logistics":0.0,"disruption":0.0,"count":0.0})
            count = conflict["count"]
            logistics = conflict["logistics"]/count if count>0.0 else 0.0
            disruption = conflict["disruption"]/count if count>0.0 else 0.0
            force = max(0.0,conflict["force"]) if envelope["conflict_inference_available"] else None
            ag = _derive([millions,a,w,q],lambda p,a,w,q:p*a*(.45+w*.85)*(1.0-min(.35,q*.08)))
            mineral = _derive([millions,u],lambda p,u:p*resource*(.45+u*.45+settlement_count*.025))
            trade_output = _derive([connectivity],lambda c:trade["volume"]*(.35+c*.35+interregional*.20)+route_count*1.75)
            services = _derive([millions,u,stability],lambda p,u,s:p*u*(.35+settlement_count*.035+s*.30))
            gdp = _derive([ag,mineral,trade_output,services],lambda a,r,t,s:max(0.0,a+r+t+s))
            tax = _derive([gdp,stability,u],lambda g,s,u:g*(.055+s*.055+u*.025))
            trade_tax = _derive([trade_output],lambda t:t*(.035+interregional*.035)/(1.0+friction*.15))
            army = _derive([population,q,stability],lambda p,q,s:p*(.009+q*.004+s*.003+resource*.002))
            admin = _derive([gdp,fragmentation],lambda g,f:g*(.035+barrier*.025+f*.035))
            maintenance = _derive([army,q],lambda a,q:a/100_000.0*(.045+q*.018))
            war = _derive([force],lambda f:f/100_000.0*(.11+logistics*.10+disruption*.14))
            signed_cash = _derive([cash,tax,trade_tax,admin,maintenance,war],lambda c,t,r,a,m,w:c+t+r-a-m-w)
            insolvency = _derive([signed_cash],lambda x:max(0.0,-x))
            closing_cash = _derive([signed_cash],lambda x:max(0.0,x))
            residual = _derive([cash,tax,trade_tax,insolvency,admin,maintenance,war,closing_cash],lambda c,t,r,i,a,m,w,e:c+t+r+i-a-m-w-e)
            prosperity = _derive([gdp,millions],lambda g,p:min(1.0,max(0.0,(g/max(1.0,p))/1.6)))
            food = _derive([ag,millions],lambda a,p:min(1.0,max(0.0,a/max(1.0,p*.42))))
            dependence = _derive([trade_output,gdp],lambda t,g:min(1.0,max(0.0,t/max(1.0,g))))
            burden = _derive([maintenance,war,tax,trade_tax],lambda m,w,t,r:min(1.0,max(0.0,(m+w)/max(1.0,t+r))))
            values = dict(zip(ECONOMY_STEP_ESTIMATES,(population,gdp,ag,mineral,trade_output,services,cash,tax,trade_tax,
                admin,maintenance,war,insolvency,closing_cash,residual,army,force,prosperity,food,dependence,burden,stability),strict=True))
            steps.append({"era_id":era_id,"dominant_process":population_step["dominant_process"],
                "start_year_bp":float(population_step["start_year_bp"]),"end_year_bp":float(population_step["end_year_bp"]),
                "duration_years":round(max(1.0,float(population_step["duration_years"])),6),**_pack_replay(values)})
            raw_steps.append(values);cash_series.append(closing_cash)
            cash = closing_cash
        estimates = dict(zip(ECONOMY_RECORD_ESTIMATES,(steps[-1]["gross_output_index"],steps[-1]["treasury_end_index"],
            _aggregate([s["gross_output_index"] for s in raw_steps],"max"),_aggregate(cash_series,"max"),
            _aggregate([s["army_capacity_population"] for s in steps],"max")),strict=True))
        expected.append({"id":len(expected),"region_id":region,"population_region_id":history["population_region_id"],
            "culture_region_id":history["culture_region_id"],"language_region_id":history["language_region_id"],
            "dominant_resource":political["dominant_resource"],"time_step_count":len(steps),**_pack_replay(estimates),"steps":steps})
        complete_raw_steps.extend(raw_steps)
    estimates = dict(zip(ECONOMY_SUMMARY_ESTIMATES,(
        _aggregate([r["final_gross_output_index"] for r in expected]),_aggregate([r["final_treasury_index"] for r in expected]),
        _aggregate([s["tax_revenue_index"] for s in complete_raw_steps]),_aggregate([s["trade_revenue_index"] for s in complete_raw_steps]),
        _aggregate([s["war_cost_index"] for s in complete_raw_steps]),_aggregate([s["army_capacity_population"] for s in complete_raw_steps],"max"),
        _aggregate([s["prosperity_index"] for s in complete_raw_steps],"mean"),_aggregate([s["trade_dependency_index"] for s in complete_raw_steps],"mean"),
        _aggregate([s["military_burden_index"] for s in complete_raw_steps],"mean"),_aggregate([s["military_burden_index"] for s in complete_raw_steps],"high")),strict=True))
    summary = _pack_replay(estimates)
    summary["economy_history_summary_availability"] = summary.pop("estimate_availability")
    summary.update({"economy_history_model":ECONOMY_V2,"economy_history_count":len(expected),"economy_history_step_count":len(complete_raw_steps),
        "economy_history_available_record_count":sum(all(r["estimate_availability"].values()) for r in expected),
        "economy_history_available_step_count":sum(all(s["estimate_availability"].values()) for r in expected for s in r["steps"])})
    return expected,summary


def _verify_history_publication(payload, stage, records, summary):
    record_fields,step_fields = ((POPULATION_RECORD_ESTIMATES,POPULATION_STEP_ESTIMATES) if stage=="population" else (ECONOMY_RECORD_ESTIMATES,ECONOMY_STEP_ESTIMATES))
    actual = payload.get(stage+"_histories")
    _require(type(actual) is list,"explicit history collection required")
    _audit_estimate_maps(actual,record_fields,step_fields)
    _require(_exact(actual,records),stage+" record/step replay mismatch")
    _require(all(key in payload["summary"] and _exact(payload["summary"][key],value) for key,value in summary.items()),stage+" summary replay mismatch")


def validate_population_history_availability(payload):
    """Independent complete native-v2 → population-history2 numerical replay."""
    try:
        _require(history_economy_version(payload,"population")==2 and "population_history_model" in payload,"explicit population-history2 required")
        envelope = require_history_economy_sources(payload)
        records, summary = _expected_population_v2(payload,envelope)
        _verify_history_publication(payload,"population",records,summary)
        return []
    except (IndexError,KeyError,TypeError,ValueError,ZeroDivisionError,OverflowError):
        return ["population history availability model or independent replay invalid"]


def validate_history_economy_replay(payload: dict[str, Any]) -> list[str]:
    try:
        versions = (history_economy_version(payload,"population"),history_economy_version(payload,"economy"))
        if versions == (1,1):
            return _validate_history_economy_legacy(payload)
        _require(versions==(2,2) and "population_history_model" in payload and "economy_history_model" in payload,"explicit matched history/economy2 required")
        envelope = require_history_economy_sources(payload,economy=True)
        populations,population_summary = _expected_population_v2(payload,envelope)
        _verify_history_publication(payload,"population",populations,population_summary)
        economies,economy_summary = _expected_economy_v2(payload,populations,envelope)
        _verify_history_publication(payload,"economy",economies,economy_summary)
        return []
    except (IndexError,KeyError,TypeError,ValueError,ZeroDivisionError,OverflowError):
        return ["population or economy history model causal replay invalid"]
