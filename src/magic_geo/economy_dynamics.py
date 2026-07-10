from __future__ import annotations

from typing import Any


ECONOMY_HISTORY_MODEL = "causal_population_trade_conflict_treasury_economy_history_v1"


def _economy_history_model() -> dict[str, Any]:
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


def _set_economy_history_model(world: dict[str, Any]) -> None:
    world["economy_history_model"] = _economy_history_model()
    world.setdefault("summary", {})["economy_history_model"] = ECONOMY_HISTORY_MODEL


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _resource_value(resource: str) -> float:
    values = {
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
    }
    return values.get(resource, 0.16)


def _trade_by_region(world: dict[str, Any]) -> dict[int, dict[str, float]]:
    trade: dict[int, dict[str, float]] = {}
    for flow in world.get("trade_flows", []):
        volume = max(0.0, float(flow.get("volume_index", 0.0)))
        friction = _clamp(float(flow.get("friction", 0.0)), 0.0, 4.0)
        effective_volume = volume / (1.0 + friction * 0.35)
        for key in ("region_from", "region_to"):
            region_id = int(flow.get(key, -1))
            if region_id < 0:
                continue
            record = trade.setdefault(region_id, {"volume": 0.0, "interregional_volume": 0.0, "friction_sum": 0.0, "count": 0.0})
            record["volume"] += effective_volume
            if bool(flow.get("interregional", False)):
                record["interregional_volume"] += effective_volume
            record["friction_sum"] += friction
            record["count"] += 1.0
    return trade


def _conflict_by_era_region(world: dict[str, Any]) -> dict[tuple[int, int], dict[str, float]]:
    conflicts: dict[tuple[int, int], dict[str, float]] = {}
    for conflict in world.get("conflicts", []):
        era_id = int(conflict.get("era_id", -1))
        if era_id < 0:
            continue
        region_forces = [
            (int(conflict.get("region_a", -1)), max(0.0, float(conflict.get("region_a_force_estimate", 0.0)))),
            (int(conflict.get("region_b", -1)), max(0.0, float(conflict.get("region_b_force_estimate", 0.0)))),
        ]
        intensity = _clamp(float(conflict.get("intensity", 0.0)), 0.0, 1.0)
        logistics = _clamp(float(conflict.get("logistics_strain_index", 0.0)), 0.0, 1.0)
        disruption = _clamp(float(conflict.get("economic_disruption_index", 0.0)), 0.0, 1.0)
        casualties = max(0.0, float(conflict.get("estimated_casualties", 0.0)))
        for region_id, force in region_forces:
            if region_id < 0:
                continue
            record = conflicts.setdefault(
                (era_id, region_id),
                {"force": 0.0, "casualties": 0.0, "intensity": 0.0, "logistics": 0.0, "disruption": 0.0, "count": 0.0},
            )
            record["force"] += force
            record["casualties"] += casualties * 0.5
            record["intensity"] += intensity
            record["logistics"] += logistics
            record["disruption"] += disruption
            record["count"] += 1.0
    return conflicts


def _snapshot_regions(world: dict[str, Any]) -> dict[tuple[int, int], dict[str, Any]]:
    snapshots: dict[tuple[int, int], dict[str, Any]] = {}
    for snapshot in world.get("territorial_snapshots", []):
        era_id = int(snapshot.get("era_id", -1))
        if era_id < 0:
            continue
        for region in snapshot.get("regions", []):
            region_id = int(region.get("region_id", -1))
            if region_id >= 0:
                snapshots[(era_id, region_id)] = region
    return snapshots


def enrich_world_with_economy_history(world: dict[str, Any]) -> dict[str, Any]:
    population_histories = world.get("population_histories", [])
    eras = world.get("historical_eras", [])
    if not isinstance(population_histories, list) or not isinstance(eras, list):
        return world
    if not population_histories:
        world["economy_histories"] = []
        summary = world.setdefault("summary", {})
        summary["economy_history_count"] = 0
        summary["economy_history_step_count"] = 0
        summary["historical_final_gross_output_index"] = 0.0
        summary["historical_final_treasury_index"] = 0.0
        summary["historical_total_tax_revenue_index"] = 0.0
        summary["historical_total_trade_revenue_index"] = 0.0
        summary["historical_total_war_cost_index"] = 0.0
        summary["historical_peak_army_capacity_population"] = 0.0
        summary["mean_historical_prosperity_index"] = 0.0
        summary["mean_historical_trade_dependency_index"] = 0.0
        summary["mean_historical_military_burden_index"] = 0.0
        summary["high_military_burden_economy_step_count"] = 0
        _set_economy_history_model(world)
        return world
    if not eras:
        return world

    population_by_region = {int(region.get("region_id", -1)): region for region in world.get("population_regions", [])}
    political_by_region = {int(region.get("id", -1)): region for region in world.get("political_regions", [])}
    trade_by_region = _trade_by_region(world)
    conflict_by_era_region = _conflict_by_era_region(world)
    snapshot_by_era_region = _snapshot_regions(world)

    histories: list[dict[str, Any]] = []
    step_count = 0
    final_gdp = 0.0
    final_treasury = 0.0
    total_tax_revenue = 0.0
    total_trade_revenue = 0.0
    total_war_cost = 0.0
    max_army_capacity = 0.0
    prosperity_sum = 0.0
    trade_dependency_sum = 0.0
    burden_sum = 0.0
    high_burden_steps = 0

    for history in population_histories:
        region_id = int(history.get("region_id", -1))
        if region_id < 0:
            continue
        population_region = population_by_region.get(region_id, {})
        political_region = political_by_region.get(region_id, {})
        trade = trade_by_region.get(region_id, {"volume": 0.0, "interregional_volume": 0.0, "friction_sum": 0.0, "count": 0.0})

        agricultural_capacity = _clamp(float(population_region.get("agricultural_capacity_index", 0.0)), 0.0, 1.0)
        water_security = _clamp(float(population_region.get("water_security_index", 0.0)), 0.0, 1.0)
        urbanization = _clamp(float(population_region.get("urbanization_fraction", 0.0)), 0.0, 1.0)
        pressure = _clamp(float(population_region.get("population_pressure", 0.0)), 0.0, 2.5)
        resource_value = _resource_value(str(political_region.get("dominant_resource", "none")))
        route_count = max(0.0, float(political_region.get("route_count", 0.0)))
        barrier_pressure = _clamp(float(political_region.get("barrier_pressure", 0.0)), 0.0, 1.0)
        settlement_count = max(0.0, float(population_region.get("settlement_count", political_region.get("settlement_count", 0.0))))
        average_trade_friction = trade["friction_sum"] / trade["count"] if trade["count"] > 0 else 0.0
        interregional_fraction = trade["interregional_volume"] / trade["volume"] if trade["volume"] > 0.0 else 0.0

        steps: list[dict[str, Any]] = []
        previous_treasury = max(0.0, float(history.get("initial_population", 0.0)) / 1_000_000.0 * 0.08)
        peak_gdp = 0.0
        peak_treasury = previous_treasury

        for index, step in enumerate(history.get("steps", [])):
            era_id = int(step.get("era_id", index))
            end_population = max(0.0, float(step.get("end_population", 0.0)))
            population_millions = end_population / 1_000_000.0
            duration_years = max(1.0, float(step.get("duration_years", 1.0)))
            era = eras[index] if index < len(eras) else {}
            era_connectivity = _clamp(float(era.get("mean_connectivity", 0.0)), 0.0, 1.0)
            era_instability = _clamp(float(step.get("instability_index", era.get("mean_instability", 0.0))), 0.0, 1.0)
            snapshot_region = snapshot_by_era_region.get((era_id, region_id), {})
            stability = _clamp(float(snapshot_region.get("stability_index", 1.0 - era_instability)), 0.0, 1.0)
            fragmentation = _clamp(1.0 - stability, 0.0, 1.0)
            conflict = conflict_by_era_region.get(
                (era_id, region_id),
                {"force": 0.0, "casualties": 0.0, "intensity": 0.0, "logistics": 0.0, "disruption": 0.0, "count": 0.0},
            )
            conflict_count = conflict["count"]
            conflict_logistics = conflict["logistics"] / conflict_count if conflict_count > 0.0 else 0.0
            conflict_disruption = conflict["disruption"] / conflict_count if conflict_count > 0.0 else 0.0

            agricultural_output = population_millions * agricultural_capacity * (0.45 + water_security * 0.85) * (1.0 - min(0.35, pressure * 0.08))
            resource_output = population_millions * resource_value * (0.45 + urbanization * 0.45 + settlement_count * 0.025)
            trade_output = trade["volume"] * (0.35 + era_connectivity * 0.35 + interregional_fraction * 0.20) + route_count * 1.75
            urban_services = population_millions * urbanization * (0.35 + settlement_count * 0.035 + stability * 0.30)
            gross_output = max(0.0, agricultural_output + resource_output + trade_output + urban_services)

            tax_revenue = gross_output * (0.055 + stability * 0.055 + urbanization * 0.025)
            trade_revenue = trade_output * (0.035 + interregional_fraction * 0.035) / (1.0 + average_trade_friction * 0.15)
            army_capacity = end_population * (0.009 + pressure * 0.004 + stability * 0.003 + resource_value * 0.002)
            mobilized_force = max(0.0, conflict["force"])
            administration_cost = gross_output * (0.035 + barrier_pressure * 0.025 + fragmentation * 0.035)
            army_maintenance_cost = army_capacity / 100_000.0 * (0.045 + pressure * 0.018)
            war_cost = mobilized_force / 100_000.0 * (0.11 + conflict_logistics * 0.10 + conflict_disruption * 0.14)
            raw_treasury_end = previous_treasury + tax_revenue + trade_revenue - administration_cost - army_maintenance_cost - war_cost
            insolvency_adjustment = max(0.0, -raw_treasury_end)
            treasury_end = max(0.0, raw_treasury_end)
            balance_residual = (
                previous_treasury
                + tax_revenue
                + trade_revenue
                + insolvency_adjustment
                - administration_cost
                - army_maintenance_cost
                - war_cost
                - treasury_end
            )
            prosperity = _clamp((gross_output / max(1.0, population_millions)) / 1.6, 0.0, 1.0)
            food_security = _clamp(agricultural_output / max(1.0, population_millions * 0.42), 0.0, 1.0)
            trade_dependency = _clamp(trade_output / max(1.0, gross_output), 0.0, 1.0)
            military_burden = _clamp((army_maintenance_cost + war_cost) / max(1.0, tax_revenue + trade_revenue), 0.0, 1.0)

            steps.append(
                {
                    "era_id": era_id,
                    "dominant_process": str(step.get("dominant_process", era.get("dominant_process", "unknown"))),
                    "start_year_bp": float(step.get("start_year_bp", era.get("start_year_bp", 0.0))),
                    "end_year_bp": float(step.get("end_year_bp", era.get("end_year_bp", 0.0))),
                    "duration_years": round(duration_years, 6),
                    "population": round(end_population, 6),
                    "gross_output_index": round(gross_output, 6),
                    "agricultural_output_index": round(agricultural_output, 6),
                    "resource_output_index": round(resource_output, 6),
                    "trade_output_index": round(trade_output, 6),
                    "urban_services_index": round(urban_services, 6),
                    "treasury_start_index": round(previous_treasury, 6),
                    "tax_revenue_index": round(tax_revenue, 6),
                    "trade_revenue_index": round(trade_revenue, 6),
                    "administration_cost_index": round(administration_cost, 6),
                    "army_maintenance_cost_index": round(army_maintenance_cost, 6),
                    "war_cost_index": round(war_cost, 6),
                    "insolvency_adjustment_index": round(insolvency_adjustment, 6),
                    "treasury_end_index": round(treasury_end, 6),
                    "balance_residual_index": round(balance_residual, 6),
                    "army_capacity_population": round(army_capacity, 6),
                    "mobilized_force_population": round(mobilized_force, 6),
                    "prosperity_index": round(prosperity, 6),
                    "food_security_index": round(food_security, 6),
                    "trade_dependency_index": round(trade_dependency, 6),
                    "military_burden_index": round(military_burden, 6),
                    "stability_index": round(stability, 6),
                }
            )

            step_count += 1
            total_tax_revenue += tax_revenue
            total_trade_revenue += trade_revenue
            total_war_cost += war_cost
            max_army_capacity = max(max_army_capacity, army_capacity)
            prosperity_sum += prosperity
            trade_dependency_sum += trade_dependency
            burden_sum += military_burden
            if military_burden >= 0.65:
                high_burden_steps += 1
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
                "max_army_capacity_population": round(max(float(step["army_capacity_population"]) for step in steps), 6),
                "steps": steps,
            }
        )

    world["economy_histories"] = histories
    summary = world.setdefault("summary", {})
    summary["economy_history_count"] = len(histories)
    summary["economy_history_step_count"] = step_count
    summary["historical_final_gross_output_index"] = round(final_gdp, 6)
    summary["historical_final_treasury_index"] = round(final_treasury, 6)
    summary["historical_total_tax_revenue_index"] = round(total_tax_revenue, 6)
    summary["historical_total_trade_revenue_index"] = round(total_trade_revenue, 6)
    summary["historical_total_war_cost_index"] = round(total_war_cost, 6)
    summary["historical_peak_army_capacity_population"] = round(max_army_capacity, 6)
    summary["mean_historical_prosperity_index"] = round(prosperity_sum / step_count, 6) if step_count else 0.0
    summary["mean_historical_trade_dependency_index"] = round(trade_dependency_sum / step_count, 6) if step_count else 0.0
    summary["mean_historical_military_burden_index"] = round(burden_sum / step_count, 6) if step_count else 0.0
    summary["high_military_burden_economy_step_count"] = high_burden_steps
    _set_economy_history_model(world)
    return world
