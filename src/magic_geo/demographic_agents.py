from __future__ import annotations

from typing import Any


ROLE_SEQUENCE = ("farmer", "artisan", "merchant", "soldier", "administrator", "healer")

DEMOGRAPHIC_AGENT_MODEL = (
    "causal_population_economy_logistics_household_firm_demographic_history_v1"
)
INDIVIDUAL_LIFE_EVENT_MODEL = (
    "causal_household_firm_era_sampled_individual_life_event_graph_v1"
)


def _demographic_agent_model() -> dict[str, Any]:
    return {
        "model_type": DEMOGRAPHIC_AGENT_MODEL,
        "deterministic": True,
        "region_order": "ascending_population_region_id_v1",
        "household_model": "normalized_rural_urban_mobile_cohorts_from_final_population_v1",
        "household_risk_model": "hazard_pressure_water_food_market_and_logistics_weighted_indices_v1",
        "firm_model": "positive_final_economy_sector_outputs_with_logistics_and_risk_v1",
        "demographic_history_model": "population_history_steps_with_household_weighted_labor_v1",
        "market_feedback_model": "preclearing_market_exchange_pressure_v1",
        "model_limitation": "representative_aggregate_cohorts_and_firms_without_endogenous_entry_exit_household_formation_or_general_equilibrium",
    }


def _individual_life_event_model() -> dict[str, Any]:
    return {
        "model_type": INDIVIDUAL_LIFE_EVENT_MODEL,
        "deterministic": True,
        "sampling_model": "two_individuals_per_household_cohort_capped_at_six_per_population_region_v1",
        "era_assignment_model": "cyclic_birth_era_and_latest_death_era_v1",
        "lifespan_model": "bounded_mortality_vulnerability_income_life_expectancy_v1",
        "relationship_model": "regional_adjacent_spouse_and_two_predecessor_parent_graph_v1",
        "event_model": "birth_paired_marriage_property_transfer_and_death_events_v1",
        "property_model": "household_share_income_vulnerability_and_recipient_transfer_v1",
        "model_limitation": "small_deterministic_representative_sample_not_a_population_micro_simulation_or_empirical_genealogy",
    }


def _set_demographic_agent_models(world: dict[str, Any]) -> None:
    world["demographic_agent_model"] = _demographic_agent_model()
    world["individual_life_event_model"] = _individual_life_event_model()
    summary = world.setdefault("summary", {})
    summary["demographic_agent_model"] = DEMOGRAPHIC_AGENT_MODEL
    summary["individual_life_event_model"] = INDIVIDUAL_LIFE_EVENT_MODEL


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _by_region(records: list[dict[str, Any]], key: str = "region_id") -> dict[int, dict[str, Any]]:
    indexed: dict[int, dict[str, Any]] = {}
    for record in records:
        region_id = int(record.get(key, -1))
        if region_id >= 0:
            indexed[region_id] = record
    return indexed


def _population_history_by_population_region(world: dict[str, Any]) -> dict[int, dict[str, Any]]:
    histories: dict[int, dict[str, Any]] = {}
    for history in world.get("population_histories", []):
        population_region_id = int(history.get("population_region_id", -1))
        if population_region_id >= 0:
            histories[population_region_id] = history
    return histories


def _economy_by_region(world: dict[str, Any]) -> dict[int, dict[str, Any]]:
    return _by_region(world.get("economy_histories", []), "region_id")


def _final_step(record: dict[str, Any]) -> dict[str, Any]:
    steps = record.get("steps", [])
    if isinstance(steps, list) and steps:
        return steps[-1]
    return {}


def _settlements_by_region(world: dict[str, Any]) -> dict[int, list[int]]:
    grouped: dict[int, list[int]] = {}
    for settlement in world.get("settlements", []):
        settlement_id = int(settlement.get("id", -1))
        region_id = int(settlement.get("region_id", -1))
        if settlement_id >= 0 and region_id >= 0:
            grouped.setdefault(region_id, []).append(settlement_id)
    for settlement_ids in grouped.values():
        settlement_ids.sort()
    return grouped


def _market_pressure_by_region(world: dict[str, Any]) -> dict[int, float]:
    pressure: dict[int, float] = {}
    for market in world.get("market_exchanges", []):
        disruption = _clamp(float(market.get("disruption_risk_index", 0.0)))
        dependency = _clamp(float(market.get("market_access_index", 0.0)))
        value = _clamp(disruption * 0.62 + dependency * 0.18 + float(market.get("friction", 0.0)) * 0.20)
        for key in ("region_from", "region_to"):
            region_id = int(market.get(key, -1))
            if region_id >= 0:
                pressure[region_id] = max(pressure.get(region_id, 0.0), value)
    return pressure


def _logistics_by_region(world: dict[str, Any]) -> dict[int, dict[str, Any]]:
    return _by_region(world.get("logistics_networks", []), "region_id")


def _cohort_specs(urbanization: float, migration_balance: float, pressure: float) -> list[tuple[str, float, float]]:
    migrant_fraction = _clamp(abs(migration_balance) * 0.55 + pressure * 0.035, 0.02, 0.18)
    urban_fraction = _clamp(urbanization, 0.05, 0.88)
    rural_fraction = max(0.05, 1.0 - urban_fraction - migrant_fraction)
    total = rural_fraction + urban_fraction + migrant_fraction
    return [
        ("rural_household", rural_fraction / total, 5.1),
        ("urban_household", urban_fraction / total, 3.8),
        ("mobile_household", migrant_fraction / total, 4.2),
    ]


def _sorted_eras(world: dict[str, Any]) -> list[dict[str, Any]]:
    eras = world.get("historical_eras", [])
    if isinstance(eras, list) and eras:
        return sorted(
            eras,
            key=lambda era: (
                -float(era.get("start_year_bp", 0.0)),
                int(era.get("id", 0)),
            ),
        )
    return [{"id": 0, "start_year_bp": 1.0, "end_year_bp": 0.0, "dominant_process": "undated"}]


def _dominant_firm_sector(region_id: int, firm_agents: list[dict[str, Any]]) -> str:
    region_firms = [firm for firm in firm_agents if int(firm.get("region_id", -1)) == region_id]
    if not region_firms:
        return "subsistence"
    return str(max(region_firms, key=lambda firm: float(firm.get("employment_capacity", 0.0))).get("sector", "subsistence"))


def _person_name(region_id: int, person_index: int, culture_id: int) -> str:
    prefixes = ("Ari", "Bel", "Caro", "Dara", "Eli", "Faro", "Galen", "Hara", "Iri", "Jora")
    suffixes = ("an", "el", "or", "is", "um", "ai", "eth", "un")
    return f"{prefixes[(region_id + person_index) % len(prefixes)]}{suffixes[(culture_id + person_index * 2) % len(suffixes)]}"


def _enrich_demographic_agents_v1(world: dict[str, Any]) -> dict[str, Any]:
    _set_demographic_agent_models(world)
    population_regions = world.get("population_regions", [])
    if not isinstance(population_regions, list):
        return world

    population_histories = _population_history_by_population_region(world)
    economy_by_region = _economy_by_region(world)
    logistics_by_region = _logistics_by_region(world)
    market_pressure_by_region = _market_pressure_by_region(world)
    settlements_by_region = _settlements_by_region(world)
    regions_by_id = {int(region.get("id", -1)): region for region in world.get("political_regions", [])}

    household_cohorts: list[dict[str, Any]] = []
    firm_agents: list[dict[str, Any]] = []
    demographic_agent_histories: list[dict[str, Any]] = []
    individual_agents: list[dict[str, Any]] = []
    individual_life_events: list[dict[str, Any]] = []

    household_population_total = 0.0
    household_resilience_sum = 0.0
    household_migration_sum = 0.0
    household_consumption_sum = 0.0
    high_vulnerability_households = 0

    for population_region in sorted(population_regions, key=lambda item: int(item.get("id", -1))):
        population_region_id = int(population_region.get("id", -1))
        region_id = int(population_region.get("region_id", -1))
        history = population_histories.get(population_region_id, {})
        economy = economy_by_region.get(region_id, {})
        final_step = _final_step(economy)
        logistics = logistics_by_region.get(region_id, {})
        final_population = max(
            0.0,
            float(history.get("final_population", population_region.get("estimated_population", 0.0))),
        )
        urbanization = _clamp(float(population_region.get("urbanization_fraction", 0.0)))
        migration_balance = float(population_region.get("migration_balance", 0.0))
        pressure = _clamp(float(population_region.get("population_pressure", 0.0)), 0.0, 1.0)
        hazard = _clamp(float(population_region.get("hazard_mortality_index", 0.0)))
        water_security = _clamp(float(population_region.get("water_security_index", 0.0)))
        food_security = _clamp(float(final_step.get("food_security_index", 0.0)))
        prosperity = _clamp(float(final_step.get("prosperity_index", 0.0)))
        trade_dependency = _clamp(float(final_step.get("trade_dependency_index", 0.0)))
        logistics_resilience = _clamp(float(logistics.get("logistics_resilience_index", 0.0)))
        market_pressure = market_pressure_by_region.get(region_id, 0.0)
        cohort_ids: list[int] = []
        allocated_population = 0.0
        specs = _cohort_specs(urbanization, migration_balance, pressure)
        for index, (cohort_type, fraction, household_size) in enumerate(specs):
            if index == len(specs) - 1:
                population = max(0.0, final_population - allocated_population)
            else:
                population = max(0.0, final_population * fraction)
                allocated_population += population
            cohort_modifier = {
                "rural_household": 0.04,
                "urban_household": -0.02,
                "mobile_household": 0.10,
            }[cohort_type]
            vulnerability = _clamp(
                hazard * 0.30
                + pressure * 0.24
                + (1.0 - water_security) * 0.20
                + (1.0 - food_security) * 0.14
                + market_pressure * 0.08
                + cohort_modifier
            )
            migration_propensity = _clamp(
                abs(migration_balance) * 0.38
                + pressure * 0.18
                + vulnerability * 0.22
                + (1.0 - logistics_resilience) * 0.14
                + (0.12 if cohort_type == "mobile_household" else 0.0)
            )
            consumption_pressure = _clamp(pressure * 0.34 + (1.0 - food_security) * 0.24 + (1.0 - prosperity) * 0.18 + trade_dependency * 0.14 + vulnerability * 0.10)
            income = _clamp(prosperity * 0.42 + (1.0 - vulnerability) * 0.22 + urbanization * 0.16 + logistics_resilience * 0.20)
            labor_participation = _clamp(0.43 + prosperity * 0.18 - vulnerability * 0.12 + (0.07 if cohort_type == "urban_household" else 0.0))
            fertility_rate = max(0.0, 0.0007 + (1.0 - urbanization) * 0.0007 + pressure * 0.0004 - vulnerability * 0.00025)
            mortality_risk = _clamp(hazard * 0.44 + vulnerability * 0.38 + pressure * 0.18)
            cohort_id = len(household_cohorts)
            household_cohorts.append(
                {
                    "id": cohort_id,
                    "population_region_id": population_region_id,
                    "region_id": region_id,
                    "culture_region_id": int(population_region.get("culture_region_id", -1)),
                    "language_region_id": int(population_region.get("language_region_id", -1)),
                    "cohort_type": cohort_type,
                    "population": round(population, 6),
                    "household_count": round(population / max(1.0, household_size), 6),
                    "average_household_size": round(household_size, 6),
                    "urbanization_fraction": round(urbanization, 6),
                    "water_security_index": round(water_security, 6),
                    "food_security_index": round(food_security, 6),
                    "income_index": round(income, 6),
                    "consumption_pressure_index": round(consumption_pressure, 6),
                    "vulnerability_index": round(vulnerability, 6),
                    "migration_propensity_index": round(migration_propensity, 6),
                    "fertility_rate_per_year": round(fertility_rate, 8),
                    "mortality_risk_index": round(mortality_risk, 6),
                    "labor_participation_index": round(labor_participation, 6),
                }
            )
            cohort_ids.append(cohort_id)
            household_population_total += population
            household_resilience_sum += 1.0 - vulnerability
            household_migration_sum += migration_propensity
            household_consumption_sum += consumption_pressure
            high_vulnerability_households += 1 if vulnerability >= 0.65 else 0
        population_region["household_cohort_ids"] = cohort_ids
        population_region["household_cohort_count"] = len(cohort_ids)
        population_region["representative_household_population"] = round(sum(float(household_cohorts[cohort_id]["population"]) for cohort_id in cohort_ids), 6)

    firm_productivity_sum = 0.0
    firm_market_dependency_sum = 0.0
    firm_supply_chain_risk_sum = 0.0
    firm_employment_total = 0.0
    for economy in sorted(world.get("economy_histories", []), key=lambda item: int(item.get("region_id", -1))):
        region_id = int(economy.get("region_id", -1))
        if region_id < 0:
            continue
        final_step = _final_step(economy)
        population = max(0.0, float(final_step.get("population", 0.0)))
        gross_output = max(1.0, float(final_step.get("gross_output_index", economy.get("final_gross_output_index", 1.0))))
        prosperity = _clamp(float(final_step.get("prosperity_index", 0.0)))
        trade_dependency = _clamp(float(final_step.get("trade_dependency_index", 0.0)))
        stability = _clamp(float(final_step.get("stability_index", 0.0)))
        military_burden = _clamp(float(final_step.get("military_burden_index", 0.0)))
        logistics = logistics_by_region.get(region_id, {})
        logistics_resilience = _clamp(float(logistics.get("logistics_resilience_index", 0.0)))
        chokepoint = _clamp(float(logistics.get("chokepoint_exposure_index", 0.0)))
        settlement_ids = settlements_by_region.get(region_id, [])
        capital_settlement_id = int(regions_by_id.get(region_id, {}).get("capital_settlement_id", -1))
        sector_outputs = [
            ("agriculture", float(final_step.get("agricultural_output_index", 0.0)), 0.30),
            ("resource", float(final_step.get("resource_output_index", 0.0)), 0.44),
            ("trade", float(final_step.get("trade_output_index", 0.0)), 0.82),
            ("urban_services", float(final_step.get("urban_services_index", 0.0)), 0.56),
            ("administration", float(final_step.get("administration_cost_index", 0.0)), 0.24),
        ]
        firm_ids: list[int] = []
        for index, (sector, output, base_dependency) in enumerate(sector_outputs):
            if output <= 0.0:
                continue
            output_share = _clamp(output / gross_output)
            market_dependency = _clamp(base_dependency * 0.52 + trade_dependency * 0.34 + output_share * 0.14)
            productivity = _clamp(output_share * 0.42 + prosperity * 0.30 + stability * 0.18 + logistics_resilience * 0.10)
            supply_chain_risk = _clamp(chokepoint * 0.32 + market_dependency * 0.26 + (1.0 - logistics_resilience) * 0.24 + military_burden * 0.18)
            employment = population * output_share * (0.30 + productivity * 0.28)
            tax_contribution = output * (0.07 + market_dependency * 0.025) * (1.0 - supply_chain_risk * 0.16)
            settlement_id = capital_settlement_id if index == 0 or not settlement_ids else settlement_ids[index % len(settlement_ids)]
            firm_id = len(firm_agents)
            firm_agents.append(
                {
                    "id": firm_id,
                    "region_id": region_id,
                    "population_region_id": int(economy.get("population_region_id", -1)),
                    "settlement_id": settlement_id,
                    "sector": sector,
                    "output_index": round(max(0.0, output), 6),
                    "employment_capacity": round(employment, 6),
                    "wage_index": round(_clamp(prosperity * 0.45 + productivity * 0.35 + (1.0 - supply_chain_risk) * 0.20), 6),
                    "productivity_index": round(productivity, 6),
                    "market_dependency_index": round(market_dependency, 6),
                    "capital_stock_index": round(_clamp(output / 260.0 * 0.48 + prosperity * 0.26 + logistics_resilience * 0.26), 6),
                    "supply_chain_risk_index": round(supply_chain_risk, 6),
                    "tax_contribution_index": round(tax_contribution, 6),
                }
            )
            firm_ids.append(firm_id)
            firm_productivity_sum += productivity
            firm_market_dependency_sum += market_dependency
            firm_supply_chain_risk_sum += supply_chain_risk
            firm_employment_total += employment
        if region_id in regions_by_id:
            regions_by_id[region_id]["firm_agent_ids"] = firm_ids
            regions_by_id[region_id]["firm_agent_count"] = len(firm_ids)

    demographic_vulnerability_sum = 0.0
    demographic_step_count = 0
    for population_region in sorted(population_regions, key=lambda item: int(item.get("id", -1))):
        population_region_id = int(population_region.get("id", -1))
        region_id = int(population_region.get("region_id", -1))
        history = population_histories.get(population_region_id, {})
        cohort_ids = population_region.get("household_cohort_ids", [])
        cohort_population = max(1.0, sum(float(household_cohorts[cohort_id]["population"]) for cohort_id in cohort_ids if isinstance(cohort_id, int) and 0 <= cohort_id < len(household_cohorts)))
        labor_average = (
            sum(float(household_cohorts[cohort_id]["labor_participation_index"]) * float(household_cohorts[cohort_id]["population"]) for cohort_id in cohort_ids)
            / cohort_population
            if cohort_ids
            else 0.45
        )
        steps: list[dict[str, Any]] = []
        for index, step in enumerate(history.get("steps", [])):
            start_population = max(0.0, float(step.get("start_population", 0.0)))
            end_population = max(0.0, float(step.get("end_population", 0.0)))
            pressure = _clamp(float(step.get("pressure_index", 0.0)))
            hazard = _clamp(float(step.get("hazard_mortality_index", population_region.get("hazard_mortality_index", 0.0))))
            conflict_loss = max(0.0, float(step.get("conflict_loss", 0.0)))
            migration_delta = float(step.get("migration_delta", 0.0))
            loss_fraction = _clamp(conflict_loss / max(1.0, start_population))
            migration_propensity = _clamp(abs(migration_delta) / max(1.0, start_population) * 8.0 + pressure * 0.20 + hazard * 0.18 + loss_fraction * 0.28)
            vulnerability = _clamp(hazard * 0.32 + pressure * 0.26 + loss_fraction * 0.28 + migration_propensity * 0.14)
            working_population = end_population * labor_average
            dependent_population = max(0.0, end_population - working_population)
            consumption_pressure = _clamp(pressure * 0.42 + dependent_population / max(1.0, end_population) * 0.24 + vulnerability * 0.22 + loss_fraction * 0.12)
            steps.append(
                {
                    "era_id": int(step.get("era_id", -1)),
                    "stage_index": index + 1,
                    "start_year_bp": round(float(step.get("start_year_bp", 0.0)), 6),
                    "end_year_bp": round(float(step.get("end_year_bp", 0.0)), 6),
                    "start_population": round(start_population, 6),
                    "end_population": round(end_population, 6),
                    "working_population": round(working_population, 6),
                    "dependent_population": round(dependent_population, 6),
                    "migration_propensity_index": round(migration_propensity, 6),
                    "consumption_pressure_index": round(consumption_pressure, 6),
                    "vulnerability_index": round(vulnerability, 6),
                    "labor_participation_index": round(labor_average, 6),
                }
            )
            demographic_vulnerability_sum += vulnerability
            demographic_step_count += 1
        history_id = len(demographic_agent_histories)
        demographic_agent_histories.append(
            {
                "id": history_id,
                "population_region_id": population_region_id,
                "region_id": region_id,
                "household_cohort_ids": list(cohort_ids),
                "firm_agent_ids": list(regions_by_id.get(region_id, {}).get("firm_agent_ids", [])),
                "step_count": len(steps),
                "final_agent_population": round(float(history.get("final_population", 0.0)), 6),
                "mean_labor_participation_index": round(labor_average, 6),
                "steps": steps,
            }
        )
        population_region["demographic_agent_history_id"] = history_id

    eras = _sorted_eras(world)
    birth_event_count = 0
    death_event_count = 0
    marriage_event_count = 0
    property_transfer_event_count = 0
    individual_lifespan_sum = 0.0
    property_transfer_value_sum = 0.0
    for population_region in sorted(population_regions, key=lambda item: int(item.get("id", -1))):
        population_region_id = int(population_region.get("id", -1))
        region_id = int(population_region.get("region_id", -1))
        culture_id = int(population_region.get("culture_region_id", -1))
        language_id = int(population_region.get("language_region_id", -1))
        cohort_ids = [int(cohort_id) for cohort_id in population_region.get("household_cohort_ids", []) if isinstance(cohort_id, int)]
        if not cohort_ids:
            continue
        history = population_histories.get(population_region_id, {})
        dominant_sector = _dominant_firm_sector(region_id, firm_agents)
        region_person_ids: list[int] = []
        sample_count = min(6, max(2, len(cohort_ids) * 2))
        for index in range(sample_count):
            cohort_id = cohort_ids[index % len(cohort_ids)]
            cohort = household_cohorts[cohort_id]
            cohort_population = max(1.0, float(cohort.get("population", 0.0)))
            household_count = max(1.0, float(cohort.get("household_count", 0.0)))
            fertility = max(0.0, float(cohort.get("fertility_rate_per_year", 0.0)))
            mortality = _clamp(float(cohort.get("mortality_risk_index", 0.0)))
            vulnerability = _clamp(float(cohort.get("vulnerability_index", 0.0)))
            migration = _clamp(float(cohort.get("migration_propensity_index", 0.0)))
            income = _clamp(float(cohort.get("income_index", 0.0)))
            birth_era = eras[index % len(eras)]
            death_era = eras[-1]
            life_expectancy = max(18.0, 78.0 - mortality * 26.0 - vulnerability * 18.0 + income * 10.0)
            birth_year_bp = max(
                float(death_era.get("end_year_bp", 0.0)),
                float(birth_era.get("start_year_bp", 0.0)) - 16.0 - index * 7.0,
            )
            death_year_bp = max(float(death_era.get("end_year_bp", 0.0)), birth_year_bp - life_expectancy)
            household_share = cohort_population / household_count
            property_value = max(0.0, household_share * (0.24 + income * 0.46) * (1.0 - vulnerability * 0.22))
            person_id = len(individual_agents)
            role = ROLE_SEQUENCE[(region_id + index) % len(ROLE_SEQUENCE)]
            if role == "farmer" and dominant_sector != "agriculture" and index % 3 == 0:
                role = dominant_sector
            individual_agents.append(
                {
                    "id": person_id,
                    "population_region_id": population_region_id,
                    "region_id": region_id,
                    "household_cohort_id": cohort_id,
                    "culture_region_id": culture_id,
                    "language_region_id": language_id,
                    "name": _person_name(region_id, index, culture_id),
                    "role": role,
                    "birth_year_bp": round(birth_year_bp, 6),
                    "death_year_bp": round(death_year_bp, 6),
                    "lifespan_years": round(max(0.0, birth_year_bp - death_year_bp), 6),
                    "married_person_id": -1,
                    "parent_person_ids": [],
                    "child_person_ids": [],
                    "property_value_index": round(property_value, 6),
                    "mobility_index": round(migration, 6),
                    "vulnerability_index": round(vulnerability, 6),
                    "event_ids": [],
                    "event_count": 0,
                }
            )
            region_person_ids.append(person_id)
            individual_lifespan_sum += max(0.0, birth_year_bp - death_year_bp)

            birth_event_id = len(individual_life_events)
            individual_life_events.append(
                {
                    "id": birth_event_id,
                    "person_id": person_id,
                    "related_person_id": -1,
                    "population_region_id": population_region_id,
                    "region_id": region_id,
                    "household_cohort_id": cohort_id,
                    "era_id": int(birth_era.get("id", -1)),
                    "event_type": "birth",
                    "year_bp": round(birth_year_bp, 6),
                    "property_value_index": 0.0,
                    "demographic_pressure_index": round(_clamp(fertility * 320.0 + migration * 0.18), 6),
                    "mortality_risk_index": round(mortality, 6),
                    "inheritance_fraction": 0.0,
                }
            )
            individual_agents[person_id]["event_ids"].append(birth_event_id)
            birth_event_count += 1

            if index >= 2:
                parent_ids = [region_person_ids[index - 2]]
                if index >= 3:
                    parent_ids.append(region_person_ids[index - 3])
                individual_agents[person_id]["parent_person_ids"] = parent_ids
                for parent_id in parent_ids:
                    individual_agents[parent_id]["child_person_ids"].append(person_id)

            if index % 2 == 1:
                spouse_id = region_person_ids[index - 1]
                marriage_year = max(death_year_bp, birth_year_bp - 22.0 - vulnerability * 6.0)
                individual_agents[person_id]["married_person_id"] = spouse_id
                individual_agents[spouse_id]["married_person_id"] = person_id
                for participant_id, related_id in ((person_id, spouse_id), (spouse_id, person_id)):
                    marriage_event_id = len(individual_life_events)
                    individual_life_events.append(
                        {
                            "id": marriage_event_id,
                            "person_id": participant_id,
                            "related_person_id": related_id,
                            "population_region_id": population_region_id,
                            "region_id": region_id,
                            "household_cohort_id": int(individual_agents[participant_id]["household_cohort_id"]),
                            "era_id": int(birth_era.get("id", -1)),
                            "event_type": "marriage",
                            "year_bp": round(marriage_year, 6),
                            "property_value_index": 0.0,
                            "demographic_pressure_index": round(_clamp(migration * 0.26 + vulnerability * 0.20), 6),
                            "mortality_risk_index": round(mortality, 6),
                            "inheritance_fraction": 0.0,
                        }
                    )
                    individual_agents[participant_id]["event_ids"].append(marriage_event_id)
                    marriage_event_count += 1

            transfer_year = max(death_year_bp, birth_year_bp - max(1.0, life_expectancy * 0.72))
            recipient_id = region_person_ids[index - 2] if index >= 2 else -1
            transfer_fraction = 0.48 if recipient_id >= 0 else 0.20
            transfer_value = property_value * transfer_fraction
            property_transfer_id = len(individual_life_events)
            individual_life_events.append(
                {
                    "id": property_transfer_id,
                    "person_id": person_id,
                    "related_person_id": recipient_id,
                    "population_region_id": population_region_id,
                    "region_id": region_id,
                    "household_cohort_id": cohort_id,
                    "era_id": int(death_era.get("id", -1)),
                    "event_type": "property_transfer",
                    "year_bp": round(transfer_year, 6),
                    "property_value_index": round(transfer_value, 6),
                    "demographic_pressure_index": round(_clamp(migration * 0.22 + vulnerability * 0.24), 6),
                    "mortality_risk_index": round(mortality, 6),
                    "inheritance_fraction": round(transfer_fraction, 6),
                }
            )
            individual_agents[person_id]["event_ids"].append(property_transfer_id)
            property_transfer_event_count += 1
            property_transfer_value_sum += transfer_value

            death_event_id = len(individual_life_events)
            individual_life_events.append(
                {
                    "id": death_event_id,
                    "person_id": person_id,
                    "related_person_id": -1,
                    "population_region_id": population_region_id,
                    "region_id": region_id,
                    "household_cohort_id": cohort_id,
                    "era_id": int(death_era.get("id", -1)),
                    "event_type": "death",
                    "year_bp": round(death_year_bp, 6),
                    "property_value_index": 0.0,
                    "demographic_pressure_index": round(_clamp(vulnerability * 0.42 + mortality * 0.38), 6),
                    "mortality_risk_index": round(mortality, 6),
                    "inheritance_fraction": 0.0,
                }
            )
            individual_agents[person_id]["event_ids"].append(death_event_id)
            death_event_count += 1
        for person_id in region_person_ids:
            individual_agents[person_id]["event_count"] = len(individual_agents[person_id]["event_ids"])
        population_region["individual_agent_ids"] = region_person_ids
        population_region["individual_agent_count"] = len(region_person_ids)

    world["household_cohorts"] = household_cohorts
    world["firm_agents"] = firm_agents
    world["demographic_agent_histories"] = demographic_agent_histories
    world["individual_agents"] = individual_agents
    world["individual_life_events"] = individual_life_events

    summary = world.setdefault("summary", {})
    household_count = len(household_cohorts)
    firm_count = len(firm_agents)
    individual_count = len(individual_agents)
    life_event_count = len(individual_life_events)
    summary["household_cohort_count"] = household_count
    summary["firm_agent_count"] = firm_count
    summary["demographic_agent_history_count"] = len(demographic_agent_histories)
    summary["demographic_agent_step_count"] = demographic_step_count
    summary["individual_agent_count"] = individual_count
    summary["individual_life_event_count"] = life_event_count
    summary["individual_birth_event_count"] = birth_event_count
    summary["individual_death_event_count"] = death_event_count
    summary["individual_marriage_event_count"] = marriage_event_count
    summary["property_transfer_event_count"] = property_transfer_event_count
    summary["total_household_cohort_population"] = round(household_population_total, 6)
    summary["total_firm_employment_capacity"] = round(firm_employment_total, 6)
    summary["total_property_transfer_value_index"] = round(property_transfer_value_sum, 6)
    summary["mean_household_resilience_index"] = round(household_resilience_sum / household_count, 6) if household_count else 0.0
    summary["mean_household_migration_propensity_index"] = round(household_migration_sum / household_count, 6) if household_count else 0.0
    summary["mean_household_consumption_pressure_index"] = round(household_consumption_sum / household_count, 6) if household_count else 0.0
    summary["mean_firm_productivity_index"] = round(firm_productivity_sum / firm_count, 6) if firm_count else 0.0
    summary["mean_firm_market_dependency_index"] = round(firm_market_dependency_sum / firm_count, 6) if firm_count else 0.0
    summary["mean_firm_supply_chain_risk_index"] = round(firm_supply_chain_risk_sum / firm_count, 6) if firm_count else 0.0
    summary["mean_demographic_vulnerability_index"] = round(demographic_vulnerability_sum / demographic_step_count, 6) if demographic_step_count else 0.0
    summary["mean_individual_lifespan_years"] = round(individual_lifespan_sum / individual_count, 6) if individual_count else 0.0
    summary["high_vulnerability_household_count"] = high_vulnerability_households
    return world



def enrich_world_with_demographic_agents(world: dict[str, Any]) -> dict[str, Any]:
    from .demographic_availability_validation import demographic_version
    if demographic_version(world)==1:
        return _enrich_demographic_agents_v1(world)
    from .demographic_availability import enrich_demographic_availability
    return enrich_demographic_availability(world)
